from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
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
TELEMETRY_FPS = 10


class AdaptiveInferenceScheduler:
    """Back-pressure and cadence control for asynchronous neural inference.

    Camera capture stays warm at the device rate, while only useful frames are
    submitted to MediaPipe.  This prevents a fast webcam from building latency
    and saves CPU when no accepted hand has been visible recently.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_submission = -10.0
        self._active_until = -10.0
        self._last_target_fps = 0.0

    def reset(self) -> None:
        with self._lock:
            self._next_submission = -10.0
            self._active_until = -10.0
            self._last_target_fps = 0.0

    def observe(self, hands_present: bool, timestamp: float, tuning: dict[str, float]) -> None:
        if not hands_present:
            return
        with self._lock:
            self._active_until = max(
                self._active_until,
                timestamp + tuning["inference_activity_hold"],
            )

    def target_fps(self, timestamp: float, tuning: dict[str, float]) -> float:
        active_fps = max(1.0, tuning["inference_active_fps"])
        if tuning["adaptive_inference"] < 0.5:
            return active_fps
        with self._lock:
            active = timestamp <= self._active_until
        if active:
            return active_fps
        return min(active_fps, max(1.0, tuning["inference_idle_fps"]))

    def should_submit(self, timestamp: float, busy: bool, tuning: dict[str, float]) -> bool:
        if busy:
            return False
        target_fps = self.target_fps(timestamp, tuning)
        interval = 1.0 / target_fps
        with self._lock:
            if abs(target_fps - self._last_target_fps) > 1e-6:
                self._next_submission = timestamp
                self._last_target_fps = target_fps
            if timestamp + 1e-9 < self._next_submission:
                return False
            self._next_submission += interval
            # Do not try to replay a large backlog after camera reconnects or
            # the process wakes from sleep. One fresh frame is sufficient.
            if self._next_submission <= timestamp:
                self._next_submission = timestamp + interval
        return True


class FaceOverlapFilter:
    """Reject new hand candidates contained by a detected face region.

    MediaPipe can occasionally fit a plausible hand skeleton to eyes, glasses,
    a nose, and a mouth. A fresh face-region match invalidates even a continuous
    hand track so handedness continuity cannot whitelist that false skeleton.
    """

    def __init__(
        self,
        continuity_seconds: float = 0.30,
        continuity_distance: float = 0.20,
        containment_points: int = 16,
    ) -> None:
        self.continuity_seconds = continuity_seconds
        self.continuity_distance = continuity_distance
        self.containment_points = containment_points
        self._accepted: dict[str, tuple[float, float, float]] = {}
        self._pending_since: dict[str, float] = {}
        self._verification_progress: dict[str, tuple[float, int]] = {}
        self._verification_lock = threading.Lock()
        self._verification_requested = False

    def configure(
        self,
        continuity_seconds: float,
        continuity_distance: float,
        containment_points: int,
    ) -> None:
        self.continuity_seconds = max(0.01, float(continuity_seconds))
        self.continuity_distance = max(0.01, float(continuity_distance))
        self.containment_points = max(1, min(21, int(round(containment_points))))

    def reset(self) -> None:
        self._accepted.clear()
        self._pending_since.clear()
        self._verification_progress.clear()
        with self._verification_lock:
            self._verification_requested = False

    def verification_requested(self) -> bool:
        with self._verification_lock:
            return self._verification_requested

    def clear_verification_request(self) -> None:
        with self._verification_lock:
            self._verification_requested = False

    @staticmethod
    def _center(hand: HandObservation) -> tuple[float, float]:
        points = hand.landmarks
        indices = (0, 5, 9, 13, 17) if len(points) >= 18 else tuple(range(len(points)))
        if not indices:
            return 0.0, 0.0
        return (
            sum(points[index].x for index in indices) / len(indices),
            sum(points[index].y for index in indices) / len(indices),
        )

    def _contained_by_face(
        self,
        hand: HandObservation,
        face_regions: tuple[tuple[float, float, float, float], ...],
    ) -> bool:
        if len(hand.landmarks) < 21:
            return False
        for left, top, width, height in face_regions:
            right = left + width
            bottom = top + height

            def inside(index: int) -> bool:
                point = hand.landmarks[index]
                return left <= point.x <= right and top <= point.y <= bottom

            inside_count = sum(inside(index) for index in range(21))
            palm_inside = sum(inside(index) for index in (0, 5, 9, 13, 17))
            if inside_count >= self.containment_points and palm_inside >= 4 and inside(0):
                return True
        return False

    def apply(
        self,
        hands: tuple[HandObservation, ...],
        face_regions: tuple[tuple[float, float, float, float], ...],
        timestamp: float,
        scan_captured_at: float | None = None,
    ) -> tuple[HandObservation, ...]:
        verified_at = math.inf if scan_captured_at is None else scan_captured_at
        visible = {hand.handedness.lower() for hand in hands}
        for key in tuple(self._pending_since):
            if key not in visible:
                self._pending_since.pop(key, None)
                self._verification_progress.pop(key, None)
        accepted: list[HandObservation] = []
        for hand in hands:
            key = hand.handedness.lower()
            center_x, center_y = self._center(hand)
            previous = self._accepted.get(key)
            continuous = (
                previous is not None
                and timestamp - previous[2] <= self.continuity_seconds
                and math.hypot(center_x - previous[0], center_y - previous[1]) <= self.continuity_distance
            )
            # A fresh face match always wins over handedness continuity. A
            # face-shaped skeleton can appear close enough to a previously
            # accepted real hand to inherit that track; invalidate the track
            # so it must pass the normal two-scan quarantine after it leaves
            # the face region. Retaining the first pending timestamp avoids
            # turning a persistent false-positive into an 8-16 FPS Haar load.
            if self._contained_by_face(hand, face_regions):
                self._accepted.pop(key, None)
                self._pending_since.setdefault(key, timestamp)
                self._verification_progress.pop(key, None)
                continue

            # A newly appearing skeleton is quarantined until at least one
            # face scan *captured* after it appeared has completed. Comparing
            # capture time (not future completion time) prevents a slow,
            # already-stale scan from validating a newer candidate.
            if not continuous:
                pending_since = self._pending_since.setdefault(key, timestamp)
                if verified_at + 1e-9 < pending_since:
                    with self._verification_lock:
                        self._verification_requested = True
                    continue
                if scan_captured_at is not None:
                    previous_scan, confirmations = self._verification_progress.get(
                        key,
                        (-math.inf, 0),
                    )
                    if verified_at > previous_scan + 1e-9:
                        confirmations += 1
                        self._verification_progress[key] = (
                            verified_at,
                            confirmations,
                        )
                    # Two independent successful source frames prevent a single
                    # Haar false-negative from permanently continuity-
                    # whitelisting a face-shaped skeleton.
                    if confirmations < 2:
                        with self._verification_lock:
                            self._verification_requested = True
                        continue
            accepted.append(hand)
            self._accepted[key] = (center_x, center_y, timestamp)
            self._pending_since.pop(key, None)
            self._verification_progress.pop(key, None)
        return tuple(accepted)


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
    gesture_changed = Signal(str)
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
        self._preview_delivery_pending = False
        self._startup_gate = StartupActivationGate()
        self._lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._release_pending = False
        self._release_thread: threading.Thread | None = None
        self._controller: InputController | None = None
        self._inference_busy = False
        self._last_inference_timestamp = 0
        self._configuration_revision = 0
        self._gesture_revision = 0
        self._control_generation = 0
        self._autofocus = True
        self._manual_focus = 128
        self._focus_lock = False
        self._focus_revision = 0

    def set_enabled(self, enabled: bool) -> None:
        changed = False
        with self._lock:
            enabled = bool(enabled)
            changed = self._enabled != enabled
            self._enabled = enabled
            if changed:
                self._control_generation += 1
            if enabled:
                self._startup_gate.consume()
        if changed and not enabled:
            self._queue_input_release()

    def set_sensitivity(self, sensitivity: float) -> None:
        with self._lock:
            if self._sensitivity != sensitivity:
                self._sensitivity = sensitivity
                self._configuration_revision += 1

    def set_camera(self, index: int) -> None:
        changed = False
        with self._lock:
            index = int(index)
            changed = self._camera_index != index
            self._camera_index = index
            if changed:
                self._control_generation += 1
                self._gesture_revision += 1
        if changed:
            self._queue_input_release()

    def set_swap_hands(self, swap: bool) -> None:
        changed = False
        with self._lock:
            swap = bool(swap)
            changed = self._swap_hands != swap
            self._swap_hands = swap
            if changed:
                self._control_generation += 1
                self._gesture_revision += 1
                self._configuration_revision += 1
        if changed:
            self._queue_input_release()

    def set_left_handed(self, left_handed: bool) -> None:
        changed = False
        with self._lock:
            left_handed = bool(left_handed)
            changed = self._left_handed != left_handed
            if changed:
                self._left_handed = left_handed
                self._control_generation += 1
                self._gesture_revision += 1
                self._configuration_revision += 1
        if changed:
            self._queue_input_release()

    def set_tuning(self, tuning: dict[str, float]) -> None:
        with self._lock:
            normalized = normalized_tuning(tuning)
            if self._tuning != normalized:
                self._tuning = normalized
                self._configuration_revision += 1

    def set_preview_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._preview_enabled = enabled

    def acknowledge_preview(self) -> None:
        """Release the single UI-preview slot after the GUI consumes a frame."""
        with self._lock:
            self._preview_delivery_pending = False

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

    def stop(self, timeout_ms: int = 0) -> bool:
        """Request a safe stop and optionally wait for the QThread to exit.

        A zero timeout is a request-only operation: it never enters
        ``QThread.wait`` and is therefore safe to call from the GUI thread.
        Callers that are already outside the GUI thread may opt into a bounded
        synchronous wait by passing a positive timeout.
        """
        with self._lock:
            self._running = False
            self._enabled = False
            self._control_generation += 1
            self._startup_gate.consume()
        self.requestInterruption()
        self._queue_input_release()
        timeout_ms = max(0, int(timeout_ms))
        if timeout_ms == 0:
            return not self.isRunning()
        return bool(self.wait(timeout_ms))

    @staticmethod
    def _enable_windows_auto_exposure(capture, cv2) -> bool:
        """Restore DirectShow's driver-managed exposure after camera probing.

        DirectShow represents automatic exposure as 0.75. Unsupported cameras
        simply reject the property, so failure is safe and non-fatal.
        """
        try:
            return bool(capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75))
        except Exception:
            return False

    @staticmethod
    def _updated_face_scan_state(
        current_regions: tuple[tuple[float, float, float, float], ...],
        current_regions_at: float,
        current_verified_capture_at: float,
        regions: tuple[tuple[float, float, float, float], ...],
        scan_captured_at: float,
        completed_at: float,
        max_age: float,
        enabled: bool,
        succeeded: bool,
    ) -> tuple[
        tuple[tuple[float, float, float, float], ...],
        float,
        float,
    ]:
        """Resolve an async face result without validating failed scans."""
        if not succeeded:
            return current_regions, current_regions_at, current_verified_capture_at
        if not enabled:
            return (), -10.0, -10.0
        if regions:
            return regions, scan_captured_at, scan_captured_at
        if completed_at - current_regions_at > max_age:
            return (), current_regions_at, scan_captured_at
        return current_regions, current_regions_at, scan_captured_at

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

    def _release_all_inputs(self, timeout_seconds: float | None = None) -> bool:
        """Serialize emergency input release after disable/loss/switch."""
        with self._lock:
            self._release_pending = True
        if timeout_seconds is None:
            acquired = self._dispatch_lock.acquire()
        else:
            acquired = self._dispatch_lock.acquire(
                timeout=max(0.0, float(timeout_seconds))
            )
        if not acquired:
            return False
        try:
            return self._drain_pending_release_locked()
        finally:
            self._dispatch_lock.release()

    def _queue_input_release(self) -> None:
        """Request release without ever blocking the UI/control caller."""
        with self._lock:
            self._release_pending = True
            release_thread = self._release_thread
            if release_thread is not None and release_thread.is_alive():
                return
            release_thread = threading.Thread(
                target=self._run_queued_input_release,
                name="AirPointInputRelease",
                daemon=True,
            )
            self._release_thread = release_thread
        release_thread.start()

    def _run_queued_input_release(self) -> None:
        """Consume queued releases, retrying transient controller failures."""
        retry_delay = 0.02
        while True:
            failed = False
            try:
                with self._dispatch_lock:
                    self._drain_pending_release_locked()
            except Exception:
                # The drain helper restores the pending bit. Keep this daemon
                # worker alive so a stalled/disabled camera is not required to
                # provide the next retry.
                failed = True
            with self._lock:
                if not self._release_pending:
                    self._release_thread = None
                    return
            if failed:
                # Bounded exponential backoff avoids a hot loop when an input
                # backend is temporarily unavailable.
                time.sleep(retry_delay)
                retry_delay = min(0.25, retry_delay * 2.0)
            else:
                retry_delay = 0.02

    def _drain_pending_release_locked(self) -> bool:
        """Drain a requested release while the dispatch lock is owned."""
        with self._lock:
            pending = self._release_pending
            self._release_pending = False
        if not pending:
            return True
        try:
            if self._controller is not None:
                self._controller.release_all()
            return True
        except Exception:
            with self._lock:
                self._release_pending = True
            raise

    def _invalidate_inflight_actions(self) -> None:
        """Reject old callbacks, then release any input they may have latched."""
        with self._lock:
            self._control_generation += 1
        self._queue_input_release()

    def _dispatch(self, actions) -> None:
        """Dispatch unconditional cleanup/status actions in serialized order."""
        with self._dispatch_lock:
            self._drain_pending_release_locked()
            try:
                self._dispatch_actions(actions)
            finally:
                self._drain_pending_release_locked()

    def _dispatch_if_current(self, actions, generation: int) -> bool:
        """Dispatch gestures only while their control snapshot is still valid."""
        with self._dispatch_lock:
            self._drain_pending_release_locked()
            with self._lock:
                current = self._enabled and self._control_generation == generation
            if not current:
                return False
            try:
                self._dispatch_actions(actions)
            except BaseException:
                with self._lock:
                    if (
                        not self._enabled
                        or self._control_generation != generation
                    ):
                        self._release_pending = True
                try:
                    self._drain_pending_release_locked()
                except Exception:
                    # Preserve the original dispatch exception.
                    pass
                raise
            with self._lock:
                still_current = (
                    self._enabled
                    and self._control_generation == generation
                )
                if not still_current:
                    self._release_pending = True
            # A disable/switch may have happened during a slow optional
            # accessibility lookup. Undo any button it latched before
            # releasing the dispatch lock.
            self._drain_pending_release_locked()
            return still_current

    def _center_pointer_if_current(self, generation: int) -> None:
        with self._dispatch_lock:
            self._drain_pending_release_locked()
            with self._lock:
                current = self._enabled and self._control_generation == generation
            if current and self._controller is not None:
                try:
                    self._controller.center_pointer()
                finally:
                    self._drain_pending_release_locked()

    def _dispatch_actions(self, actions) -> None:
        if self._controller is None:
            return
        with self._lock:
            adjustable_control_detection = self._tuning["adjustable_control_detection"] >= 0.5
        for action in actions:
            if action.kind == "move" and action.x is not None and action.y is not None:
                self._controller.move(action.x, action.y)
            elif action.kind == "pinch_start":
                if adjustable_control_detection:
                    self._controller.begin_context_pinch()
                else:
                    self._controller.cancel_context_pinch()
            elif action.kind == "pinch_move" and action.x is not None and action.y is not None:
                if adjustable_control_detection:
                    self._controller.move_context_pinch(action.x, action.y)
            elif action.kind == "pinch_cancel":
                self._controller.cancel_context_pinch()
            elif action.kind == "left_click":
                self._controller.complete_context_pinch()
            elif action.kind == "right_click":
                self._controller.right_click()
            elif action.kind == "middle_click":
                self._controller.middle_click()
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
        face_filter = FaceOverlapFilter()
        inference_scheduler = AdaptiveInferenceScheduler()
        result_lock = threading.Lock()
        latest_hands: tuple[HandObservation, ...] = ()
        latest_paused = False
        latest_face_regions: tuple[tuple[float, float, float, float], ...] = ()
        latest_face_regions_at = -10.0
        latest_face_scan_captured_at = -10.0
        last_error_emitted: dict[str, float] = {}

        def emit_error_throttled(message: str, key: str, cooldown: float = 10.0) -> None:
            now_time = time.monotonic()
            if now_time - last_error_emitted.get(key, 0.0) >= cooldown:
                self.error.emit(message)
                last_error_emitted[key] = now_time

        callback_state = {
            "previous_enabled": False,
            "fps_time": time.monotonic(),
            "frame_count": 0,
            "fps": 0.0,
            "last_telemetry": 0.0,
            "previous_gesture": None,
            "configured_revision": -1,
            "gesture_revision": -1,
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
                    gesture_revision = self._gesture_revision
                    control_generation = self._control_generation
                    preview_enabled = self._preview_enabled

                hands = self._to_hands(result, swap_hands)
                face_filter.configure(
                    tuning["face_track_grace"],
                    tuning["face_track_distance"],
                    round(tuning["face_containment_points"]),
                )
                with result_lock:
                    face_regions = (
                        latest_face_regions
                        if now - latest_face_regions_at <= tuning["face_region_max_age"]
                        else ()
                    )
                    face_scan_captured_at = latest_face_scan_captured_at
                if (
                    tuning["face_filter_enabled"] >= 0.5
                    and face_detection_available
                ):
                    hands = face_filter.apply(
                        hands,
                        face_regions,
                        now,
                        scan_captured_at=face_scan_captured_at,
                    )
                inference_scheduler.observe(bool(hands), now, tuning)
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
                            self._control_generation += 1
                            control_generation = self._control_generation
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
                gesture_identity_changed = gesture_revision != callback_state["gesture_revision"]
                if enabled_changed or gesture_identity_changed:
                    self._dispatch(
                        engine.reset(
                            keep_pause=gesture_identity_changed and not enabled_changed
                        )
                    )
                    if gesture_identity_changed:
                        face_filter.reset()
                    if enabled_changed and enabled:
                        self._center_pointer_if_current(control_generation)
                    callback_state["previous_enabled"] = enabled
                    callback_state["gesture_revision"] = gesture_revision

                if enabled:
                    gesture_frame = engine.process(hands, now)
                    self._dispatch_if_current(
                        gesture_frame.actions,
                        control_generation,
                    )
                    gesture = gesture_frame.gesture
                    paused = gesture_frame.paused
                else:
                    gesture = startup_label
                    paused = False

                if gesture != callback_state["previous_gesture"]:
                    self.gesture_changed.emit(gesture)
                    callback_state["previous_gesture"] = gesture

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
                min_hand_detection_confidence=0.58,
                min_hand_presence_confidence=0.55,
                min_tracking_confidence=0.50,
                result_callback=on_result,
            )
            landmarker = HandLandmarker.create_from_options(options)

            cascade_root = getattr(getattr(cv2, "data", None), "haarcascades", "")
            frontal_face_detector = cv2.CascadeClassifier(
                str(cascade_root) + "haarcascade_frontalface_default.xml"
            )
            glasses_eye_detector = cv2.CascadeClassifier(
                str(cascade_root) + "haarcascade_eye_tree_eyeglasses.xml"
            )
            if frontal_face_detector.empty():
                frontal_face_detector = None
            if glasses_eye_detector.empty():
                glasses_eye_detector = None
            face_detection_available = (
                frontal_face_detector is not None
                or glasses_eye_detector is not None
            )
            if not face_detection_available:
                emit_error_throttled(
                    "Face rejection is unavailable; hand tracking will continue without it.",
                    "face_filter_unavailable",
                    cooldown=60.0,
                )
        except Exception as exc:
            emit_error_throttled(f"Could not initialize hand tracking: {exc}", "init")
            return

        def detect_face_regions(gray, min_neighbors: int) -> tuple[tuple[float, float, float, float], ...]:
            """Run both classical cascades off the latency-sensitive camera loop."""
            scan_height, scan_width = gray.shape[:2]
            regions: list[tuple[float, float, float, float]] = []

            if frontal_face_detector is not None:
                minimum_face = max(48, round(scan_width * 0.14))
                for x, y, box_width, box_height in frontal_face_detector.detectMultiScale(
                    gray,
                    scaleFactor=1.10,
                    minNeighbors=min_neighbors,
                    minSize=(minimum_face, minimum_face),
                ):
                    pad_x = round(box_width * 0.08)
                    pad_top = round(box_height * 0.06)
                    pad_bottom = round(box_height * 0.12)
                    left = max(0, x - pad_x)
                    top = max(0, y - pad_top)
                    right_edge = min(scan_width, x + box_width + pad_x)
                    bottom = min(scan_height, y + box_height + pad_bottom)
                    regions.append((
                        left / scan_width,
                        top / scan_height,
                        (right_edge - left) / scan_width,
                        (bottom - top) / scan_height,
                    ))

            # Glasses can weaken a frontal-face cascade while making the
            # eye/frame pattern distinctive. Only pay for the fallback when
            # the faster frontal cascade found nothing.
            if not regions and glasses_eye_detector is not None:
                minimum_eye = max(20, round(scan_width * 0.04))
                for x, y, box_width, box_height in glasses_eye_detector.detectMultiScale(
                    gray,
                    scaleFactor=1.10,
                    minNeighbors=min_neighbors,
                    minSize=(minimum_eye, minimum_eye),
                ):
                    left = max(0, round(x - 2.0 * box_width))
                    top = max(0, round(y - 0.8 * box_height))
                    right_edge = min(scan_width, round(x + 3.0 * box_width))
                    bottom = min(scan_height, round(y + 4.8 * box_height))
                    regions.append((
                        left / scan_width,
                        top / scan_height,
                        (right_edge - left) / scan_width,
                        (bottom - top) / scan_height,
                    ))
            return tuple(regions)

        face_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="AirPointFace")
        face_future: Future | None = None
        face_future_captured_at = -10.0
        capture = None
        active_camera = -1
        next_preview = -10.0
        last_preview_fps = 0.0
        cached_clahe = None
        cached_clahe_clip = -1.0
        applied_focus_revision = -1
        last_face_scan = -10.0

        try:
            while self._running and not self.isInterruptionRequested():
                with self._lock:
                    enabled = self._enabled
                    camera_index = self._camera_index
                    preview_enabled = self._preview_enabled
                    inference_busy = self._inference_busy
                    tuning = self._tuning

                if camera_index != active_camera:
                    # The callback owns gesture/filter state until it clears
                    # this flag. Waiting avoids one stale old-camera action and
                    # prevents a capture-thread reset racing callback filtering.
                    if inference_busy or (face_future is not None and not face_future.done()):
                        time.sleep(0.001)
                        continue
                    if face_future is not None:
                        # The completed result belongs to the old camera.
                        try:
                            face_future.result()
                        except Exception:
                            pass
                        face_future = None
                    if capture is not None:
                        capture.release()
                    self._dispatch(engine.reset(keep_pause=True))
                    self._release_all_inputs()
                    _backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_DSHOW
                    capture = cv2.VideoCapture(camera_index, _backend)
                    using_windows_dshow = platform.system() == "Windows" and capture.isOpened()
                    if not capture.isOpened():
                        capture.release()
                        capture = cv2.VideoCapture(camera_index)
                        using_windows_dshow = False
                    # MJPEG avoids the low-FPS uncompressed mode many Windows
                    # webcams select at HD resolutions.
                    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
                    capture.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)
                    if using_windows_dshow:
                        self._enable_windows_auto_exposure(capture, cv2)
                    active_camera = camera_index
                    applied_focus_revision = -1
                    with result_lock:
                        latest_hands = ()
                        latest_paused = False
                        latest_face_regions = ()
                        latest_face_regions_at = -10.0
                        latest_face_scan_captured_at = -10.0
                    face_filter.reset()
                    inference_scheduler.reset()
                    if not capture.isOpened():
                        emit_error_throttled(
                            f"Camera {camera_index + 1} is unavailable. Choose another camera or check "
                            f"{'System Settings → Privacy → Camera' if platform.system() == 'Darwin' else 'Windows privacy settings'}.",
                            f"camera_{camera_index}"
                        )
                        active_camera = -1
                        time.sleep(0.5)
                        continue

                assert capture is not None
                ok, frame = capture.read()
                if not ok:
                    emit_error_throttled("Camera frame was lost. Reconnecting…", "frame_lost")
                    # Invalidate any callback that still owns a result from
                    # the failed capture before releasing latched input.
                    self._invalidate_inflight_actions()
                    capture.release()
                    active_camera = -1
                    time.sleep(0.2)
                    continue

                # Query live processing settings and reserve an asynchronous
                # inference slot only when its target cadence is due.
                inference_now = time.monotonic()
                with self._lock:
                    busy = self._inference_busy
                    tuning = self._tuning
                    submit_inference = inference_scheduler.should_submit(
                        inference_now,
                        busy,
                        tuning,
                    )
                    if submit_inference:
                        self._inference_busy = True
                    clahe_clip = tuning["inference_clahe_clip"]
                    focus_revision = self._focus_revision

                if focus_revision != applied_focus_revision:
                    applied_focus_revision = self._apply_focus(capture, cv2)

                height, width = frame.shape[:2]

                if face_future is not None and face_future.done():
                    completed_at = time.monotonic()
                    scan_succeeded = True
                    try:
                        regions = face_future.result()
                    except Exception as exc:
                        scan_succeeded = False
                        regions = ()
                        emit_error_throttled(f"Face filter error: {exc}", "face_filter")
                    face_future = None
                    if scan_succeeded:
                        face_filter.clear_verification_request()
                    with result_lock:
                        (
                            latest_face_regions,
                            latest_face_regions_at,
                            latest_face_scan_captured_at,
                        ) = self._updated_face_scan_state(
                            latest_face_regions,
                            latest_face_regions_at,
                            latest_face_scan_captured_at,
                            regions,
                            face_future_captured_at,
                            completed_at,
                            tuning["face_region_max_age"],
                            tuning["face_filter_enabled"] >= 0.5,
                            scan_succeeded,
                        )

                if submit_inference:
                    inference_width = max(1, round(tuning["inference_width"]))
                    if width > inference_width:
                        inference_height = max(1, round(height * inference_width / width))
                        inference_frame = cv2.resize(
                            frame,
                            (inference_width, inference_height),
                            interpolation=cv2.INTER_AREA,
                        )
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

                    scan_now = time.monotonic()
                    face_verification_requested = face_filter.verification_requested()
                    if (
                        tuning["face_filter_enabled"] >= 0.5
                        and (
                            face_verification_requested
                            or scan_now - last_face_scan >= tuning["face_scan_interval"]
                        )
                        and face_future is None
                        and face_detection_available
                    ):
                        face_scan_width = max(1, round(tuning["face_scan_width"]))
                        scan_source = inference_frame
                        if inference_frame.shape[1] > face_scan_width:
                            face_scan_height = max(
                                1,
                                round(inference_frame.shape[0] * face_scan_width / inference_frame.shape[1]),
                            )
                            scan_source = cv2.resize(
                                inference_frame,
                                (face_scan_width, face_scan_height),
                                interpolation=cv2.INTER_AREA,
                            )
                        gray = cv2.cvtColor(scan_source, cv2.COLOR_BGR2GRAY)
                        min_neighbors = max(1, round(tuning["face_min_neighbors"]))
                        face_future = face_executor.submit(
                            detect_face_regions,
                            gray.copy(),
                            min_neighbors,
                        )
                        face_future_captured_at = scan_now
                        face_filter.clear_verification_request()
                        last_face_scan = scan_now
                    elif tuning["face_filter_enabled"] < 0.5:
                        with result_lock:
                            latest_face_regions = ()
                            latest_face_regions_at = -10.0
                            latest_face_scan_captured_at = -10.0

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
                preview_fps = max(1.0, tuning["preview_fps"])
                if abs(preview_fps - last_preview_fps) > 1e-6:
                    next_preview = now
                    last_preview_fps = preview_fps
                if preview_enabled and now + 1e-9 >= next_preview:
                    with self._lock:
                        deliver_preview = not self._preview_delivery_pending
                        if deliver_preview:
                            self._preview_delivery_pending = True
                    if deliver_preview:
                        with result_lock:
                            hands = latest_hands
                            paused = latest_paused
                        preview_width = max(1, round(tuning["preview_width"]))
                        if width > preview_width:
                            preview_height = max(1, round(height * preview_width / width))
                            preview_frame = cv2.resize(
                                frame,
                                (preview_width, preview_height),
                                interpolation=cv2.INTER_LINEAR,
                            )
                        else:
                            preview_frame = frame
                        preview_frame = cv2.flip(preview_frame, 1)
                        self._draw_overlay(preview_frame, hands, enabled and not paused)
                        preview = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
                        h, w, channels = preview.shape
                        image = QImage(preview.data, w, h, channels * w, QImage.Format_RGB888).copy()
                        self.frame_ready.emit(image)
                    preview_interval = 1.0 / preview_fps
                    next_preview += preview_interval
                    if next_preview <= now:
                        next_preview = now + preview_interval
        except Exception as exc:
            emit_error_throttled(f"Tracking stopped unexpectedly: {exc}", "crash")
        finally:
            with self._lock:
                self._enabled = False
                self._control_generation += 1
            if capture is not None:
                capture.release()
            try:
                # Closing the asynchronous landmarker drains its callback
                # pipeline. Release inputs last so no late callback can latch
                # a button again during teardown.
                landmarker.close()
            finally:
                try:
                    face_executor.shutdown(wait=True, cancel_futures=True)
                finally:
                    self._release_all_inputs()
