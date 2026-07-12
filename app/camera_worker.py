from __future__ import annotations

import math
import platform
import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .gestures import GestureEngine, HandObservation, Landmark, is_fist
from .model_manager import ensure_hand_model
from .system_control import InputController, enable_tracking_priority
from .tuning import normalized_tuning


HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)

CAPTURE_WIDTH = 960
CAPTURE_HEIGHT = 540
CAPTURE_FPS = 60
INFERENCE_WIDTH = 512
PREVIEW_WIDTH = 768
PREVIEW_FPS = 45
TELEMETRY_FPS = 15


class StartupActivationGate:
    def __init__(self, hold_seconds: float = 0.35) -> None:
        self.hold_seconds = hold_seconds
        self.fists_since: float | None = None
        self.qualified = False
        self.consumed = False

    def consume(self) -> None:
        self.consumed = True
        self.fists_since = None
        self.qualified = False

    def update(self, both_visible: bool, right_fist: bool, left_fist: bool, timestamp: float) -> tuple[bool, str]:
        if self.consumed:
            return False, "Ready · activate when comfortable"
        if not both_visible:
            self.fists_since = None
            self.qualified = False
            return False, "Startup · show both hands"
        if self.qualified:
            if not right_fist and not left_fist:
                self.consume()
                return True, "Gesture control activated"
            return False, "Release both fists to activate"
        if right_fist and left_fist:
            if self.fists_since is None:
                self.fists_since = timestamp
            if timestamp - self.fists_since >= self.hold_seconds:
                self.qualified = True
                return False, "Release both fists to activate"
            return False, "Hold both fists…"
        self.fists_since = None
        return False, "Startup · make both fists together"


class CameraWorker(QThread):
    frame_ready = Signal(QImage)
    telemetry = Signal(dict)
    error = Signal(str)
    model_progress = Signal(int)
    paused_changed = Signal(bool)
    startup_activated = Signal()
    focus_locked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self._enabled = False
        self._camera_index = 0
        self._sensitivity = 1.0
        # The preview is a mirror. Reverse MediaPipe's camera-relative label
        # so the displayed and gesture labels match the user's own left/right.
        self._swap_hands = True
        self._left_handed = False
        self._tuning = normalized_tuning()
        self._preview_enabled = True
        self._startup_gate = StartupActivationGate()
        self._lock = threading.Lock()
        self._controller: InputController | None = None
        self._inference_busy = False
        self._last_inference_timestamp = 0
        self._configuration_revision = 0
        self._autofocus = True
        self._manual_focus = 128
        self._focus_lock = False
        self._focus_revision = 0

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            if enabled:
                self._startup_gate.consume()

    def set_sensitivity(self, sensitivity: float) -> None:
        with self._lock:
            if self._sensitivity != sensitivity:
                self._sensitivity = sensitivity
                self._configuration_revision += 1

    def set_camera(self, index: int) -> None:
        with self._lock:
            self._camera_index = index

    def set_swap_hands(self, swap: bool) -> None:
        with self._lock:
            self._swap_hands = swap

    def set_left_handed(self, left_handed: bool) -> None:
        with self._lock:
            if self._left_handed != left_handed:
                self._left_handed = left_handed
                self._configuration_revision += 1

    def set_tuning(self, tuning: dict[str, float]) -> None:
        with self._lock:
            normalized = normalized_tuning(tuning)
            if self._tuning != normalized:
                self._tuning = normalized
                self._configuration_revision += 1

    def set_preview_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._preview_enabled = enabled

    def set_focus(self, autofocus: bool, manual_focus: int, focus_lock: bool) -> None:
        """Queue UVC focus settings for application on the camera thread."""
        with self._lock:
            autofocus = bool(autofocus) and not bool(focus_lock)
            manual_focus = max(0, min(255, int(manual_focus)))
            focus_lock = bool(focus_lock)
            if (self._autofocus, self._manual_focus, self._focus_lock) != (autofocus, manual_focus, focus_lock):
                self._autofocus = autofocus
                self._manual_focus = manual_focus
                self._focus_lock = focus_lock
                self._focus_revision += 1

    def stop(self) -> None:
        self._running = False
        self.wait(2500)

    @staticmethod
    def _to_hands(result, swap_hands: bool = False) -> tuple[HandObservation, ...]:
        if not result or not hasattr(result, "hand_landmarks"):
            return ()
        detected: list[tuple[str, tuple[Landmark, ...], tuple[Landmark, ...] | None, float]] = []
        world_landmarks_list = getattr(result, "hand_world_landmarks", None) or []
        for i, landmarks in enumerate(result.hand_landmarks):
            if i >= len(result.handedness) or not result.handedness[i]:
                continue
            category = result.handedness[i][0]
            name = getattr(category, "category_name", None) or getattr(category, "display_name", "")
            confidence = max(0.0, min(1.0, float(getattr(category, "score", 1.0) or 0.0)))
            points = tuple(Landmark(float(p.x), float(p.y), float(p.z)) for p in landmarks)
            
            world_points = None
            if i < len(world_landmarks_list) and world_landmarks_list[i]:
                world_points = tuple(Landmark(float(p.x), float(p.y), float(p.z)) for p in world_landmarks_list[i])
                
            detected.append((str(name), points, world_points, confidence))

        # MediaPipe occasionally assigns the same handedness to both hands in
        # dim/low-FPS frames. For a mirrored preview, the smaller wrist x is
        # the physical right hand; spatially resolve only this duplicate case.
        if len(detected) == 2 and detected[0][0].lower() == detected[1][0].lower():
            ordered = sorted(range(2), key=lambda index: detected[index][1][0].x)
            repaired = ["", ""]
            repaired[ordered[0]] = "Right"
            repaired[ordered[1]] = "Left"
            detected = [
                (repaired[index], points, world, confidence)
                for index, (_, points, world, confidence) in enumerate(detected)
            ]

        hands: list[HandObservation] = []
        for name, points, world_points, confidence in detected:
            if swap_hands:
                name = "Left" if name.lower() == "right" else "Right" if name.lower() == "left" else name
            hands.append(HandObservation(name, points, world_points, confidence))
        return tuple(hands)

    @staticmethod
    def _hand_orientation(hand: HandObservation) -> tuple[str, tuple[int, int, int]]:
        """Return a camera-relative palm orientation and its BGR preview color."""
        points = hand.world_landmarks or hand.landmarks
        if len(points) < 18:
            return "TRACKING", (180, 180, 180)

        wrist, index_base, little_base = points[0], points[5], points[17]
        ax, ay, az = index_base.x - wrist.x, index_base.y - wrist.y, index_base.z - wrist.z
        bx, by, bz = little_base.x - wrist.x, little_base.y - wrist.y, little_base.z - wrist.z
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        magnitude = math.sqrt(nx * nx + ny * ny + nz * nz)
        if magnitude < 1e-6:
            return "TRACKING", (180, 180, 180)
        nx, ny, nz = nx / magnitude, ny / magnitude, nz / magnitude
        abs_x, abs_y, abs_z = abs(nx), abs(ny), abs(nz)

        # OpenCV uses BGR. Labels are camera-relative and work for both hands.
        colors = {
            "PALM FRONT": (124, 251, 204), "PALM BACK": (188, 105, 255),
            "THUMB EDGE": (70, 180, 255), "PINKY EDGE": (255, 210, 75),
            "UP EDGE": (60, 235, 255), "DOWN EDGE": (80, 80, 255),
            "FRONT-RIGHT EDGE": (255, 155, 80), "FRONT-LEFT EDGE": (210, 85, 255),
            "FRONT-UP EDGE": (120, 245, 190), "FRONT-DOWN EDGE": (225, 160, 80),
        }
        if abs_z >= 0.82:
            # The index-to-little-finger cross product reverses between hands.
            # Normalize its sign against the final, mirror-relative hand label.
            palm_front = nz > 0 if hand.handedness.lower() == "right" else nz < 0
            label = "PALM FRONT" if palm_front else "PALM BACK"
        elif abs_x >= 0.82:
            thumb_side = nx > 0 if hand.handedness.lower() == "right" else nx < 0
            label = "THUMB EDGE" if thumb_side else "PINKY EDGE"
        elif abs_y >= 0.82:
            label = "UP EDGE" if ny < 0 else "DOWN EDGE"
        elif abs_z >= abs_x and abs_z >= abs_y:
            if abs_x >= abs_y:
                label = "FRONT-RIGHT EDGE" if nx > 0 else "FRONT-LEFT EDGE"
            else:
                label = "FRONT-UP EDGE" if ny < 0 else "FRONT-DOWN EDGE"
        elif abs_x >= abs_y:
            thumb_side = nx > 0 if hand.handedness.lower() == "right" else nx < 0
            label = "THUMB EDGE" if thumb_side else "PINKY EDGE"
        else:
            label = "UP EDGE" if ny < 0 else "DOWN EDGE"
        return label, colors[label]

    @staticmethod
    def _draw_overlay(frame, hands: tuple[HandObservation, ...], enabled: bool) -> None:
        import cv2

        height, width = frame.shape[:2]
        for hand in hands:
            points = [(round(p.x * width), round(p.y * height)) for p in hand.landmarks]
            orientation, color = CameraWorker._hand_orientation(hand)
            # The orientation is already fully included in the label below;
            # keep the legacy edge suffix disabled to avoid duplicate text.
            turned = False
            for start, end in HAND_CONNECTIONS:
                cv2.line(frame, points[start], points[end], color, 2, cv2.LINE_AA)
            for index, point in enumerate(points):
                radius = 5 if index in (4, 8, 12) else 3
                cv2.circle(frame, point, radius, (245, 248, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, point, radius + 1, color, 1, cv2.LINE_AA)
            label_at = points[0]
            # Keep the existing text rendering path while showing the precise
            # camera-relative orientation beside the handedness label.
            hand = HandObservation(
                hand.handedness.upper() + " / " + orientation,
                hand.landmarks,
                hand.world_landmarks,
                hand.confidence,
            )
            state = " · EDGE" if turned else ""
            cv2.putText(frame, hand.handedness.upper() + state, (label_at[0] - 14, label_at[1] + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        state_text = "CONTROL ON" if enabled else "PREVIEW"
        state_color = (124, 251, 204) if enabled else (174, 180, 194)
        cv2.rectangle(frame, (18, 18), (130, 49), (23, 26, 34), -1)
        cv2.putText(frame, state_text, (31, 39), cv2.FONT_HERSHEY_SIMPLEX, 0.48, state_color, 1, cv2.LINE_AA)

    def _dispatch(self, actions) -> None:
        if self._controller is None:
            return
        for action in actions:
            if action.kind == "move" and action.x is not None and action.y is not None:
                self._controller.move(action.x, action.y)
            elif action.kind == "pinch_start":
                self._controller.begin_context_pinch()
            elif action.kind == "pinch_move" and action.x is not None and action.y is not None:
                self._controller.move_context_pinch(action.x, action.y)
            elif action.kind == "pinch_cancel":
                self._controller.cancel_context_pinch()
            elif action.kind == "left_click":
                self._controller.complete_context_pinch()
            elif action.kind == "right_click":
                self._controller.right_click()
            elif action.kind == "left_down":
                self._controller.left_down()
            elif action.kind == "left_up":
                self._controller.left_up()
            elif action.kind == "volume":
                direction = 1 if action.amount > 0 else -1
                for _ in range(abs(action.amount)):
                    self._controller.volume(direction)
            elif action.kind == "scroll":
                self._controller.scroll(action.amount)
            elif action.kind == "scroll_horizontal":
                self._controller.scroll_horizontal(action.amount)
            elif action.kind == "zoom":
                self._controller.zoom(action.amount)
            elif action.kind == "app_next":
                self._controller.switch_application(1)
            elif action.kind == "app_previous":
                self._controller.switch_application(-1)
            elif action.kind == "task_view":
                self._controller.task_view()
            elif action.kind == "show_desktop":
                self._controller.show_desktop()
            elif action.kind == "pause_changed":
                if not action.amount:
                    self._controller.center_pointer()
                self.paused_changed.emit(bool(action.amount))

    def _apply_focus(self, capture, cv2) -> int:
        """Apply the latest focus mode on the capture-owning thread."""
        with self._lock:
            autofocus = self._autofocus
            manual_focus = self._manual_focus
            focus_lock = self._focus_lock
            revision = self._focus_revision

        if focus_lock:
            # Freeze the value currently chosen by the lens, then switch the
            # driver to manual mode. Some UVC cameras do not expose this read;
            # in that case the current manual slider value is retained.
            current = capture.get(cv2.CAP_PROP_FOCUS)
            if 0.0 <= current <= 255.0:
                manual_focus = round(current)
                with self._lock:
                    self._manual_focus = manual_focus
                self.focus_locked.emit(manual_focus)
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            capture.set(cv2.CAP_PROP_FOCUS, manual_focus)
        elif autofocus:
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        else:
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            capture.set(cv2.CAP_PROP_FOCUS, manual_focus)
        return revision

    def run(self) -> None:
        enable_tracking_priority()
        engine = GestureEngine()
        result_lock = threading.Lock()
        latest_hands: tuple[HandObservation, ...] = ()
        latest_paused = False
        last_error_emitted: dict[str, float] = {}

        def emit_error_throttled(message: str, key: str, cooldown: float = 10.0) -> None:
            now_time = time.monotonic()
            if now_time - last_error_emitted.get(key, 0.0) >= cooldown:
                self.error.emit(message)
                last_error_emitted[key] = now_time

        callback_state = {
            "previous_enabled": False,
            "previous_left_handed": False,
            "fps_time": time.monotonic(),
            "frame_count": 0,
            "fps": 0.0,
            "last_telemetry": 0.0,
            "configured_revision": -1,
            "configured_screen": None,
            "screen": (0, 0, 1920, 1080),
            "next_screen_refresh": 0.0,
        }

        def on_result(result, _output_image, _timestamp_ms: int) -> None:
            try:
                nonlocal latest_hands, latest_paused
                now = time.monotonic()
                with self._lock:
                    enabled = self._enabled
                    sensitivity = self._sensitivity
                    swap_hands = self._swap_hands
                    left_handed = self._left_handed
                    tuning = self._tuning
                    configuration_revision = self._configuration_revision
                    preview_enabled = self._preview_enabled

                hands = self._to_hands(result, swap_hands)
                startup_label = "Ready · activate when comfortable"
                if not enabled:
                    right_hand = next((hand for hand in hands if hand.handedness.lower() == "right"), None)
                    left_hand = next((hand for hand in hands if hand.handedness.lower() == "left"), None)
                    both_visible = right_hand is not None and left_hand is not None
                    right_is_fist = right_hand is not None and is_fist(right_hand.landmarks)
                    left_is_fist = left_hand is not None and is_fist(left_hand.landmarks)
                    with self._lock:
                        activated, startup_label = self._startup_gate.update(
                            both_visible, right_is_fist, left_is_fist, now
                        )
                        if activated:
                            self._enabled = True
                            enabled = True
                    if activated:
                        self.startup_activated.emit()
                if self._controller is not None:
                    # Display metrics and filter configuration do not change
                    # every camera frame. Refresh them only when needed so
                    # the callback can spend its time on landmark processing.
                    if now >= callback_state["next_screen_refresh"]:
                        callback_state["screen"] = self._controller.screen_bounds()
                        callback_state["next_screen_refresh"] = now + 1.0
                    if (
                        configuration_revision != callback_state["configured_revision"]
                        or callback_state["screen"] != callback_state["configured_screen"]
                    ):
                        engine.configure(sensitivity, callback_state["screen"], left_handed, tuning)
                        callback_state["configured_revision"] = configuration_revision
                        callback_state["configured_screen"] = callback_state["screen"]

                enabled_changed = enabled != callback_state["previous_enabled"]
                handed_mode_changed = left_handed != callback_state["previous_left_handed"]
                if enabled_changed or handed_mode_changed:
                    self._dispatch(engine.reset(keep_pause=handed_mode_changed and not enabled_changed))
                    if enabled_changed and enabled and self._controller is not None:
                        self._controller.center_pointer()
                    callback_state["previous_enabled"] = enabled
                    callback_state["previous_left_handed"] = left_handed

                if enabled:
                    gesture_frame = engine.process(hands, now)
                    self._dispatch(gesture_frame.actions)
                    gesture = gesture_frame.gesture
                    paused = gesture_frame.paused
                else:
                    gesture = startup_label
                    paused = False

                callback_state["frame_count"] += 1
                elapsed = now - callback_state["fps_time"]
                if elapsed >= 0.75:
                    callback_state["fps"] = callback_state["frame_count"] / elapsed
                    callback_state["fps_time"] = now
                    callback_state["frame_count"] = 0

                with result_lock:
                    latest_hands = hands
                    latest_paused = paused

                if preview_enabled and now - callback_state["last_telemetry"] >= 1.0 / TELEMETRY_FPS:
                    self.telemetry.emit({
                        "gesture": gesture,
                        "right": any(hand.handedness.lower() == "right" for hand in hands),
                        "left": any(hand.handedness.lower() == "left" for hand in hands),
                        "fps": callback_state["fps"],
                        "paused": paused,
                        "enabled": enabled,
                    })
                    callback_state["last_telemetry"] = now
            except Exception as exc:
                emit_error_throttled(f"Callback error: {exc}", "callback_err")
            finally:
                with self._lock:
                    self._inference_busy = False

        try:
            import cv2
            import mediapipe as mp

            cv2.setUseOptimized(True)
            cv2.setNumThreads(2)
            self._controller = InputController()
            model_path = ensure_hand_model(self.model_progress.emit)
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            RunningMode = mp.tasks.vision.RunningMode

            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=RunningMode.LIVE_STREAM,
                num_hands=2,
                min_hand_detection_confidence=0.48,
                min_hand_presence_confidence=0.45,
                min_tracking_confidence=0.50,
                result_callback=on_result,
            )
            landmarker = HandLandmarker.create_from_options(options)
        except Exception as exc:
            emit_error_throttled(f"Could not initialize hand tracking: {exc}", "init")
            return

        capture = None
        active_camera = -1
        last_preview = 0.0
        cached_clahe = None
        cached_clahe_clip = -1.0
        applied_focus_revision = -1

        try:
            while self._running:
                with self._lock:
                    enabled = self._enabled
                    camera_index = self._camera_index
                    preview_enabled = self._preview_enabled

                if camera_index != active_camera:
                    if capture is not None:
                        capture.release()
                    _backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_DSHOW
                    capture = cv2.VideoCapture(camera_index, _backend)
                    if not capture.isOpened():
                        capture.release()
                        capture = cv2.VideoCapture(camera_index)
                    # MJPEG avoids the low-FPS uncompressed mode many Windows
                    # webcams select at HD resolutions.
                    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
                    capture.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)
                    active_camera = camera_index
                    applied_focus_revision = -1
                    with result_lock:
                        latest_hands = ()
                        latest_paused = False
                    if not capture.isOpened():
                        emit_error_throttled(
                            f"Camera {camera_index + 1} is unavailable. Choose another camera or check "
                            f"{'System Settings → Privacy → Camera' if platform.system() == 'Darwin' else 'Windows privacy settings'}.",
                            f"camera_{camera_index}"
                        )
                        time.sleep(0.5)
                        continue

                assert capture is not None
                ok, frame = capture.read()
                if not ok:
                    emit_error_throttled("Camera frame was lost. Reconnecting…", "frame_lost")
                    capture.release()
                    active_camera = -1
                    time.sleep(0.2)
                    continue

                # Query busy status
                with self._lock:
                    busy = self._inference_busy
                    if not busy:
                        self._inference_busy = True
                    clahe_clip = self._tuning["inference_clahe_clip"]
                    focus_revision = self._focus_revision

                if focus_revision != applied_focus_revision:
                    applied_focus_revision = self._apply_focus(capture, cv2)

                height, width = frame.shape[:2]

                if not busy:
                    if width > INFERENCE_WIDTH:
                        inference_height = max(1, round(height * INFERENCE_WIDTH / width))
                        inference_frame = cv2.resize(frame, (INFERENCE_WIDTH, inference_height), interpolation=cv2.INTER_AREA)
                    else:
                        inference_frame = frame
                    if clahe_clip > 0.05:
                        if cached_clahe is None or abs(cached_clahe_clip - clahe_clip) > 1e-6:
                            cached_clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
                            cached_clahe_clip = clahe_clip
                        lab = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2LAB)
                        lab[:, :, 0] = cached_clahe.apply(lab[:, :, 0])
                        inference_frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
                    inference_frame = cv2.flip(inference_frame, 1)
                    rgb = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
                    
                    timestamp_ms = time.monotonic_ns() // 1_000_000
                    with self._lock:
                        if timestamp_ms <= self._last_inference_timestamp:
                            timestamp_ms = self._last_inference_timestamp + 1
                        self._last_inference_timestamp = timestamp_ms

                    try:
                        landmarker.detect_async(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
                    except Exception as exc:
                        with self._lock:
                            self._inference_busy = False
                        emit_error_throttled(f"Inference error: {exc}", "inference_err")

                now = time.monotonic()
                if preview_enabled and now - last_preview >= 1.0 / PREVIEW_FPS:
                    with result_lock:
                        hands = latest_hands
                        paused = latest_paused
                    if width > PREVIEW_WIDTH:
                        preview_height = max(1, round(height * PREVIEW_WIDTH / width))
                        preview_frame = cv2.resize(frame, (PREVIEW_WIDTH, preview_height), interpolation=cv2.INTER_LINEAR)
                    else:
                        preview_frame = frame
                    preview_frame = cv2.flip(preview_frame, 1)
                    self._draw_overlay(preview_frame, hands, enabled and not paused)
                    preview = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
                    h, w, channels = preview.shape
                    image = QImage(preview.data, w, h, channels * w, QImage.Format_RGB888).copy()
                    self.frame_ready.emit(image)
                    last_preview = now
        except Exception as exc:
            emit_error_throttled(f"Tracking stopped unexpectedly: {exc}", "crash")
        finally:
            if self._controller is not None:
                self._controller.release_all()
            if capture is not None:
                capture.release()
            landmarker.close()
