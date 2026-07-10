from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .gestures import GestureEngine, HandObservation, Landmark, is_fist
from .model_manager import ensure_hand_model
from .system_control import InputController, enable_tracking_priority


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

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self._enabled = False
        self._camera_index = 0
        self._sensitivity = 1.0
        self._swap_hands = True
        self._left_handed = False
        self._preview_enabled = True
        self._startup_gate = StartupActivationGate()
        self._lock = threading.Lock()
        self._controller: InputController | None = None

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            if enabled:
                self._startup_gate.consume()

    def set_sensitivity(self, sensitivity: float) -> None:
        with self._lock:
            self._sensitivity = sensitivity

    def set_camera(self, index: int) -> None:
        with self._lock:
            self._camera_index = index

    def set_swap_hands(self, swap: bool) -> None:
        with self._lock:
            self._swap_hands = swap

    def set_left_handed(self, left_handed: bool) -> None:
        with self._lock:
            self._left_handed = left_handed

    def set_preview_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._preview_enabled = enabled

    def stop(self) -> None:
        self._running = False
        self.wait(2500)

    @staticmethod
    def _to_hands(result, swap_hands: bool = False) -> tuple[HandObservation, ...]:
        hands: list[HandObservation] = []
        for i, landmarks in enumerate(result.hand_landmarks):
            if i >= len(result.handedness) or not result.handedness[i]:
                continue
            category = result.handedness[i][0]
            name = getattr(category, "category_name", None) or getattr(category, "display_name", "")
            if swap_hands:
                name = "Left" if str(name).lower() == "right" else "Right" if str(name).lower() == "left" else name
            points = tuple(Landmark(float(p.x), float(p.y), float(p.z)) for p in landmarks)
            hands.append(HandObservation(str(name), points))
        return tuple(hands)

    @staticmethod
    def _draw_overlay(frame, hands: tuple[HandObservation, ...], enabled: bool) -> None:
        import cv2

        height, width = frame.shape[:2]
        for hand in hands:
            points = [(round(p.x * width), round(p.y * height)) for p in hand.landmarks]
            color = (124, 251, 204) if hand.handedness.lower() == "right" else (255, 195, 112)
            for start, end in HAND_CONNECTIONS:
                cv2.line(frame, points[start], points[end], color, 2, cv2.LINE_AA)
            for index, point in enumerate(points):
                radius = 5 if index in (4, 8, 12) else 3
                cv2.circle(frame, point, radius, (245, 248, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, point, radius + 1, color, 1, cv2.LINE_AA)
            label_at = points[0]
            cv2.putText(frame, hand.handedness.upper(), (label_at[0] - 14, label_at[1] + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

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
                for _ in range(abs(action.amount)):
                    self._controller.volume(action.amount)
            elif action.kind == "scroll":
                self._controller.scroll(action.amount)
            elif action.kind == "zoom":
                self._controller.zoom(action.amount)
            elif action.kind == "pause_changed":
                self.paused_changed.emit(bool(action.amount))

    def run(self) -> None:
        enable_tracking_priority()
        engine = GestureEngine()
        result_lock = threading.Lock()
        latest_hands: tuple[HandObservation, ...] = ()
        latest_paused = False
        callback_state = {
            "previous_enabled": False,
            "previous_left_handed": False,
            "fps_time": time.monotonic(),
            "frame_count": 0,
            "fps": 0.0,
            "last_telemetry": 0.0,
        }

        def on_result(result, _output_image, _timestamp_ms: int) -> None:
            nonlocal latest_hands, latest_paused
            now = time.monotonic()
            with self._lock:
                enabled = self._enabled
                sensitivity = self._sensitivity
                swap_hands = self._swap_hands
                left_handed = self._left_handed
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
                engine.configure(sensitivity, self._controller.screen_bounds(), left_handed)

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
                min_hand_detection_confidence=0.62,
                min_hand_presence_confidence=0.58,
                min_tracking_confidence=0.62,
                result_callback=on_result,
            )
            landmarker = HandLandmarker.create_from_options(options)
        except Exception as exc:
            self.error.emit(f"Could not initialize hand tracking: {exc}")
            return

        capture = None
        active_camera = -1
        last_preview = 0.0

        try:
            while self._running:
                with self._lock:
                    enabled = self._enabled
                    camera_index = self._camera_index
                    preview_enabled = self._preview_enabled

                if camera_index != active_camera:
                    if capture is not None:
                        capture.release()
                    capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
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
                    with result_lock:
                        latest_hands = ()
                        latest_paused = False
                    if not capture.isOpened():
                        self.error.emit(f"Camera {camera_index + 1} is unavailable. Choose another camera or check Windows privacy settings.")
                        time.sleep(0.5)
                        continue

                ok, frame = capture.read()
                if not ok:
                    self.error.emit("Camera frame was lost. Reconnecting…")
                    capture.release()
                    active_camera = -1
                    time.sleep(0.2)
                    continue

                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                if width > INFERENCE_WIDTH:
                    inference_height = max(1, round(height * INFERENCE_WIDTH / width))
                    inference_frame = cv2.resize(frame, (INFERENCE_WIDTH, inference_height), interpolation=cv2.INTER_AREA)
                else:
                    inference_frame = frame
                rgb = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
                timestamp_ms = time.monotonic_ns() // 1_000_000
                landmarker.detect_async(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
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
                    self._draw_overlay(preview_frame, hands, enabled and not paused)
                    preview = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
                    h, w, channels = preview.shape
                    image = QImage(preview.data, w, h, channels * w, QImage.Format_RGB888).copy()
                    self.frame_ready.emit(image)
                    last_preview = now
        except Exception as exc:
            self.error.emit(f"Tracking stopped unexpectedly: {exc}")
        finally:
            if self._controller is not None:
                self._controller.release_all()
            if capture is not None:
                capture.release()
            landmarker.close()
