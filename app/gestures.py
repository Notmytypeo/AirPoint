from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import math
from statistics import median

from .filters import PointFilter
from .swipe import SwipeResult, SwipeState, ThreeFingerSwipeDetector
from .tuning import normalized_tuning



@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class HandObservation:
    handedness: str
    landmarks: tuple[Landmark, ...]
    world_landmarks: tuple[Landmark, ...] | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class GestureAction:
    kind: str
    x: int | None = None
    y: int | None = None
    amount: int = 0


@dataclass(frozen=True)
class GestureFrame:
    actions: tuple[GestureAction, ...]
    gesture: str
    right_hand: bool
    left_hand: bool
    paused: bool


def _distance(a: Landmark, b: Landmark) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _angle(a: Landmark, b: Landmark, c: Landmark) -> float:
    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)
    denominator = math.hypot(*ab) * math.hypot(*cb)
    if denominator < 1e-8:
        return 0.0
    cosine = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / denominator))
    return math.degrees(math.acos(cosine))


def _angle_3d(a: Landmark, b: Landmark, c: Landmark) -> float:
    """Joint angle that remains reliable when the hand turns sideways."""
    ab = (a.x - b.x, a.y - b.y, a.z - b.z)
    cb = (c.x - b.x, c.y - b.y, c.z - b.z)
    denominator = math.sqrt(sum(value * value for value in ab) * sum(value * value for value in cb))
    if denominator < 1e-8:
        return 0.0
    cosine = max(-1.0, min(1.0, sum(first * second for first, second in zip(ab, cb)) / denominator))
    return math.degrees(math.acos(cosine))


def _finger_extended(points: tuple[Landmark, ...], mcp: int, pip: int, dip: int, tip: int) -> bool:
    straight = _angle(points[mcp], points[pip], points[dip]) > 145 and _angle(points[pip], points[dip], points[tip]) > 135
    reach = _distance(points[tip], points[0]) > _distance(points[pip], points[0]) * 1.08
    return straight and reach


def _finger_raised(
    points: tuple[Landmark, ...],
    mcp: int,
    pip: int,
    dip: int,
    tip: int,
    world_points: tuple[Landmark, ...] | None = None,
) -> bool:
    """Tolerant raised-finger test for navigation poses, including side views."""
    angle_points = world_points if world_points is not None and len(world_points) >= 21 else points
    straight = (
        _angle_3d(angle_points[mcp], angle_points[pip], angle_points[dip]) > 122
        and _angle_3d(angle_points[pip], angle_points[dip], angle_points[tip]) > 108
    )
    reach = _distance(points[tip], points[0]) > _distance(points[pip], points[0]) * 1.02
    return straight and reach


def is_fist(points: tuple[Landmark, ...]) -> bool:
    if len(points) < 21:
        return False
    extended = [
        _finger_extended(points, 5, 6, 7, 8),
        _finger_extended(points, 9, 10, 11, 12),
        _finger_extended(points, 13, 14, 15, 16),
        _finger_extended(points, 17, 18, 19, 20),
    ]
    compact = sum(_distance(points[tip], points[0]) < _distance(points[pip], points[0]) * 1.22 for pip, tip in ((6, 8), (10, 12), (14, 16), (18, 20)))
    return not any(extended) and compact >= 3


def is_open_palm(points: tuple[Landmark, ...]) -> bool:
    if len(points) < 21:
        return False
    return all(
        _finger_extended(points, *finger)
        for finger in ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
    )


def is_right_click_pose(points: tuple[Landmark, ...]) -> bool:
    """Middle-thumb contact is a right click only with the other fingers open."""
    if len(points) < 21:
        return False
    return all(
        _finger_extended(points, *finger)
        for finger in (
            (5, 6, 7, 8),
            (13, 14, 15, 16),
            (17, 18, 19, 20),
        )
    )


def is_two_finger_scroll_pose(
    points: tuple[Landmark, ...],
    world_points: tuple[Landmark, ...] | None = None,
) -> bool:
    """Index and middle are raised while ring and little fingers are folded."""
    if len(points) < 21:
        return False
    raised = (
        _finger_raised(points, 5, 6, 7, 8, world_points),
        _finger_raised(points, 9, 10, 11, 12, world_points),
        _finger_extended(points, 13, 14, 15, 16),
        _finger_extended(points, 17, 18, 19, 20),
    )
    palm_width = max(_distance(points[5], points[17]), 0.035)
    fingers_together = _distance(points[8], points[12]) / palm_width < 1.00
    return raised[0] and raised[1] and not raised[2] and not raised[3] and fingers_together


def is_zoom_pinch_pose(points: tuple[Landmark, ...]) -> bool:
    """Index may be pinched; at least two free fingers must remain open."""
    if len(points) < 21:
        return False

    def finger_is_free(mcp: int, pip: int, dip: int, tip: int) -> bool:
        # Deliberately more tolerant than the open-palm classifier: during a
        # pinch the other fingers are often naturally curved, not ruler-straight.
        joint_open = _angle(points[mcp], points[pip], points[dip]) > 112
        tip_open = _angle(points[pip], points[dip], points[tip]) > 105
        reaches_out = _distance(points[tip], points[0]) > _distance(points[pip], points[0]) * 0.98
        return joint_open and tip_open and reaches_out

    free_count = sum(
        finger_is_free(*finger)
        for finger in ((9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
    )
    return free_count >= 2


class GestureEngine:
    """Deterministic gesture state machine, independent from camera and UI code."""

    def __init__(self) -> None:
        self.sensitivity = 1.0
        self.screen = (0, 0, 1920, 1080)
        self.left_handed = False
        self.tuning = normalized_tuning()
        self.paused = False
        self._filter = PointFilter()
        self._pinch_drag_filter = PointFilter()
        self._index_pinched = False
        self._middle_pinched = False
        self._left_index_pinched = False
        self._pinch_filtered: dict[str, float] = {}
        self._pinch_history: dict[str, deque[float]] = {}
        self._pinch_candidate_since: dict[str, float] = {}
        self._pinch_release_since: dict[str, float] = {}
        self._zoom_mode = False
        self._zoom_last_distance: float | None = None
        self._zoom_smoothed_distance: float | None = None
        self._zoom_reference_distance = 0.0
        self._zoom_accumulator = 0.0
        self._zoom_last_emit = -10.0
        self._dragging = False
        self._drag_start_point: tuple[float, float] | None = None
        self._drag_started_at = -10.0
        self._drag_moved = False
        self._last_index_release = -10.0
        self._last_right_click = -10.0
        self._fist_since: float | None = None
        self._fist_latched = False
        self._left_fist_last_seen = -10.0
        self._volume_y: float | None = None
        self._scroll_y: float | None = None
        self._two_finger_scroll_y: float | None = None
        self._two_finger_scroll_x: float | None = None
        self._two_finger_scroll_last_emit = -10.0
        self._pointer_resume_at = -10.0
        self._last_pointer_point: Landmark | None = None
        self._pinch_offset = (0.0, 0.0)
        self._missing_since: float | None = None
        self._swipes = {"right": ThreeFingerSwipeDetector(), "left": ThreeFingerSwipeDetector()}
        self._configure_filters()

    def _configure_filters(self) -> None:
        settings = self.tuning
        for motion_filter in (self._filter, self._pinch_drag_filter):
            motion_filter.configure(
                dead_zone=settings["pointer_dead_zone"],
                lookahead_frames=settings["prediction_frames"],
                min_cutoff=settings["pointer_min_cutoff"],
                beta=settings["pointer_beta"],
                prediction_cap=settings["prediction_cap"],
                precision_step=settings["precision_step"],
                precision_speed_floor=settings["precision_speed_floor"],
                precision_release_seconds=settings["precision_release_seconds"],
                confidence_floor=settings["pointer_confidence_floor"],
                jump_threshold=settings["pointer_jump_threshold"],
                prediction_reversal_guard=settings["prediction_reversal_guard"] >= 0.5,
            )

    def configure(
        self,
        sensitivity: float,
        screen: tuple[int, int, int, int],
        left_handed: bool = False,
        tuning: dict[str, float] | None = None,
    ) -> None:
        self.sensitivity = max(0.5, min(1.8, sensitivity))
        self.screen = screen
        self.left_handed = left_handed
        if tuning is not None:
            normalized = normalized_tuning(tuning)
            if normalized != self.tuning:
                self.tuning = normalized
                self._configure_filters()

    def reset(self, keep_pause: bool = False) -> tuple[GestureAction, ...]:
        actions: list[GestureAction] = []
        if self._dragging:
            actions.append(GestureAction("left_up"))
        if self._index_pinched:
            actions.append(GestureAction("pinch_cancel"))
        paused = self.paused if keep_pause else False
        sensitivity = self.sensitivity
        screen = self.screen
        left_handed = self.left_handed
        tuning = self.tuning
        self.__init__()  # type: ignore[misc]
        self.paused = paused
        self.configure(sensitivity, screen, left_handed, tuning)
        return tuple(actions)

    def set_paused(self, paused: bool) -> tuple[GestureAction, ...]:
        actions: list[GestureAction] = []
        if paused and self._dragging:
            actions.append(GestureAction("left_up"))
        if self._index_pinched:
            actions.append(GestureAction("pinch_cancel"))
        self.paused = paused
        self._dragging = False
        self._drag_start_point = None
        self._drag_moved = False
        self._index_pinched = False
        self._middle_pinched = False
        self._left_index_pinched = False
        self._pinch_filtered.clear()
        self._pinch_history.clear()
        self._pinch_candidate_since.clear()
        self._pinch_release_since.clear()
        self._zoom_mode = False
        self._zoom_last_distance = None
        self._zoom_smoothed_distance = None
        self._zoom_reference_distance = 0.0
        self._zoom_accumulator = 0.0
        self._volume_y = None
        self._scroll_y = None
        self._two_finger_scroll_y = None
        self._two_finger_scroll_x = None
        self._two_finger_scroll_last_emit = -10.0
        self._left_fist_last_seen = -10.0
        self._last_pointer_point = None
        self._pinch_offset = (0.0, 0.0)
        self._missing_since = None
        for detector in self._swipes.values():
            detector.reset()
        self._filter.reset()
        self._pinch_drag_filter.reset()
        return tuple(actions)

    @staticmethod
    def _find(hands: tuple[HandObservation, ...], name: str) -> HandObservation | None:
        return next((hand for hand in hands if hand.handedness.lower() == name.lower()), None)

    @staticmethod
    def _normalized_distance(points: tuple[Landmark, ...], tip: int, include_depth: bool) -> float:
        def distance(a: Landmark, b: Landmark) -> float:
            if include_depth:
                return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)
            return math.hypot(a.x - b.x, a.y - b.y)

        palm_scale = max(
            distance(points[5], points[17]),
            distance(points[0], points[9]) * 0.72,
            0.035,
        )
        return distance(points[4], points[tip]) / palm_scale

    def _pinch_ratio(self, hand: HandObservation | tuple[Landmark, ...], tip: int) -> float:
        """Blend calibrated 2D contact with world-depth geometry when present.

        Image landmarks remain the stable contact signal for a head-on pinch;
        MediaPipe world landmarks add depth separation so an edge-on projected
        overlap does not become a false pinch. A blend avoids making click
        recognition depend entirely on the noisier depth estimate.
        """
        if not isinstance(hand, HandObservation):
            return self._normalized_distance(hand, tip, include_depth=False)

        image_ratio = self._normalized_distance(hand.landmarks, tip, include_depth=False)
        if hand.world_landmarks is None or len(hand.world_landmarks) < 21:
            return image_ratio
        world_ratio = self._normalized_distance(hand.world_landmarks, tip, include_depth=True)
        image_palm_width = _distance(hand.landmarks[5], hand.landmarks[17])
        image_palm_length = _distance(hand.landmarks[0], hand.landmarks[9])
        # A sideways hand collapses its image width, making 2D contact less
        # dependable. MediaPipe's depth estimate can also become noisy in this
        # pose, however, so a clearly visible fingertip contact must still be
        # allowed through instead of making clicks impossible at thumb edge.
        side_on = image_palm_width < max(0.035, image_palm_length * 0.62)
        if side_on and image_ratio <= self.tuning["pinch_contact"] * 1.30:
            return image_ratio
        blend = min(0.55, self.tuning["pinch_3d_blend"] + (0.22 if side_on else 0.0))
        return image_ratio * (1.0 - blend) + world_ratio * blend

    def _stable_pinch(self, key: str, ratio: float, was_pinched: bool, timestamp: float) -> bool:
        """Fast median-plus-low-pass pinch channel with hysteresis."""
        history = self._pinch_history.setdefault(key, deque(maxlen=3))
        history.append(ratio)
        # The 3-sample median ignores a one-frame landmark jump, while the raw
        # value is retained until the history is warm so a first real contact
        # remains immediate.
        median_ratio = median(history) if len(history) == 3 else ratio
        previous = self._pinch_filtered.get(key, median_ratio)
        # Deliberately light smoothing: enough to settle frame noise without
        # adding a noticeable hold before a gesture begins.
        alpha = self.tuning["pinch_alpha_contact"] if median_ratio < previous else self.tuning["pinch_alpha_release"]
        filtered = previous * (1.0 - alpha) + median_ratio * alpha
        self._pinch_filtered[key] = filtered

        if was_pinched:
            self._pinch_candidate_since.pop(key, None)
            # A deep current contact wins over a trailing median window. This
            # prevents a brief outward wobble from releasing a held pinch.
            if ratio <= self.tuning["pinch_deep_contact"]:
                self._pinch_release_since.pop(key, None)
                return True
            # A clearly open current pose must release immediately; the median
            # may still contain the two preceding contact frames.
            if ratio >= self.tuning["pinch_clear_release"]:
                self._pinch_release_since.pop(key, None)
                return False
            if filtered < self.tuning["pinch_hold_release"]:
                self._pinch_release_since.pop(key, None)
                return True
            # A clearly open finger should release immediately; only ambiguous
            # values near the boundary receive a short dropout grace period.
            release_since = self._pinch_release_since.setdefault(key, timestamp)
            if timestamp - release_since < self.tuning["pinch_release_grace"]:
                return True
            self._pinch_release_since.pop(key, None)
            return False

        self._pinch_release_since.pop(key, None)
        # A cold signal can trust a deep contact immediately. Once warm, the
        # median requires the contact to survive one additional frame, which
        # removes isolated detector spikes with only a single-frame cost.
        if len(history) < 3 and ratio <= self.tuning["pinch_deep_contact"]:
            self._pinch_candidate_since.pop(key, None)
            return True
        # A very close contact still needs one follow-up frame once the signal
        # is warm: this blocks isolated landmark spikes while cutting normal
        # pinch recognition from roughly two frames to one.
        if ratio <= self.tuning["pinch_deep_contact"]:
            # A second close sample within the short median window is enough
            # for an immediate response. A lone deep sample after an open hand
            # still waits for one follow-up frame, rejecting detector spikes.
            if sum(sample <= self.tuning["pinch_contact"] for sample in history) >= 2:
                self._pinch_candidate_since.pop(key, None)
                return True
            candidate_since = self._pinch_candidate_since.setdefault(key, timestamp)
            if timestamp - candidate_since >= 0.010:
                self._pinch_candidate_since.pop(key, None)
                return True
            return False
        if ratio >= self.tuning["pinch_contact"] or filtered >= self.tuning["pinch_contact"]:
            self._pinch_candidate_since.pop(key, None)
            return False
        # Strong fingertip contact remains single-frame responsive. A shallow
        # boundary contact must persist briefly before it becomes a click.
        if filtered <= self.tuning["pinch_confirm"]:
            self._pinch_candidate_since.pop(key, None)
            return True
        candidate_since = self._pinch_candidate_since.setdefault(key, timestamp)
        if timestamp - candidate_since >= 0.010:
            self._pinch_candidate_since.pop(key, None)
            return True
        return False

    def _clear_pinch_signal(self, key: str) -> None:
        self._pinch_filtered.pop(key, None)
        self._pinch_history.pop(key, None)
        self._pinch_candidate_since.pop(key, None)
        self._pinch_release_since.pop(key, None)

    def _process_app_swipes(
        self,
        hands: tuple[HandObservation, ...],
        timestamp: float,
        physical_pinch: dict[str, bool],
    ) -> tuple[SwipeResult | None, str]:
        """Track independent raw three-finger swipes from either physical hand."""
        debug = ""
        visible = {hand.handedness.lower() for hand in hands}
        for name, detector in self._swipes.items():
            if name not in visible:
                detector.reset()
        for hand in hands:
            detector = self._swipes.get(hand.handedness.lower())
            if detector is None:
                continue
            result = detector.process(
                hand.landmarks,
                timestamp,
                pinch_active=physical_pinch.get(hand.handedness.lower(), False) or self._dragging,
                tuning=self.tuning,
            )
            if self.tuning["swipe_debug"] and result.state in (SwipeState.ARMED, SwipeState.TRACKING):
                debug = result.debug_text
            if result.state == SwipeState.FIRED:
                return result, debug
        return None, debug

    def _map_pointer(
        self,
        point: Landmark,
        timestamp: float,
        motion_filter: PointFilter | None = None,
        precision_factor: float = 0.0,
        confidence: float = 1.0,
    ) -> tuple[int, int]:
        # The camera frame is mirrored before inference, so x maps naturally.
        # Amplify the central hand workspace so reaching every screen edge does
        # not require shoulder/arm travel. The motion filter still absorbs the
        # extra gain from natural fingertip tremor.
        zoom = self.tuning["workspace_base_gain"] + self.sensitivity * self.tuning["workspace_sensitivity_gain"]
        nx = 0.5 + (point.x - 0.5) * zoom
        ny = 0.5 + (point.y - 0.5) * zoom
        margin_x = margin_y = self.tuning["workspace_margin"]
        nx = max(0.0, min(1.0, (nx - margin_x) / (1.0 - 2 * margin_x)))
        ny = max(0.0, min(1.0, (ny - margin_y) / (1.0 - 2 * margin_y)))
        sx, sy = (motion_filter or self._filter).apply(
            nx, ny, timestamp, precision_factor=precision_factor, confidence=confidence,
        )
        left, top, width, height = self.screen
        return round(left + sx * max(1, width - 1)), round(top + sy * max(1, height - 1))

    @staticmethod
    def _two_hand_pinch_distance(right: HandObservation, left: HandObservation) -> float:
        right_x = (right.landmarks[4].x + right.landmarks[8].x) * 0.5
        right_y = (right.landmarks[4].y + right.landmarks[8].y) * 0.5
        left_x = (left.landmarks[4].x + left.landmarks[8].x) * 0.5
        left_y = (left.landmarks[4].y + left.landmarks[8].y) * 0.5
        return math.hypot(right_x - left_x, right_y - left_y)

    def process(self, hands: tuple[HandObservation, ...], timestamp: float) -> GestureFrame:
        # These local names describe roles: `right` is the dominant pointer
        # hand and `left` is the support/modifier hand. Left-handed mode mirrors
        # those roles without altering the camera's physical handedness labels.
        dominant_name = "Left" if self.left_handed else "Right"
        support_name = "Right" if self.left_handed else "Left"
        right = self._find(hands, dominant_name)
        left = self._find(hands, support_name)
        actions: list[GestureAction] = []

        if right is None:
            swipe_result, _ = self._process_app_swipes(hands, timestamp, {})
            if swipe_result is not None:
                action = {"right": "app_next", "left": "app_previous", "up": "task_view", "down": "show_desktop"}[swipe_result.direction]
                actions.append(GestureAction(action))
                gesture = swipe_result.debug_text if self.tuning["swipe_debug"] else (
                    {"right": "Next application", "left": "Previous application", "up": "Task View", "down": "Show desktop"}[swipe_result.direction]
                )
                return GestureFrame(tuple(actions), gesture, False, left is not None, self.paused)
            if self._zoom_mode:
                actions.append(GestureAction("pinch_cancel"))
                self._zoom_mode = False
                self._zoom_last_distance = None
                self._zoom_smoothed_distance = None
                self._zoom_accumulator = 0.0
                self._left_index_pinched = False
            if self._missing_since is None:
                self._missing_since = timestamp
            if timestamp - self._missing_since > 0.18:
                if self._dragging:
                    actions.append(GestureAction("left_up"))
                if self._index_pinched:
                    actions.append(GestureAction("pinch_cancel"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
                self._index_pinched = False
                self._middle_pinched = False
                self._clear_pinch_signal("index")
                self._clear_pinch_signal("middle")
                self._volume_y = None
                self._scroll_y = None
                self._two_finger_scroll_y = None
                self._two_finger_scroll_x = None
                self._last_pointer_point = None
                self._pinch_offset = (0.0, 0.0)
                self._pointer_resume_at = -10.0
                self._filter.reset()
                self._pinch_drag_filter.reset()
            return GestureFrame(tuple(actions), f"Show your {dominant_name.lower()} hand", False, left is not None, self.paused)
        self._missing_since = None

        points = right.landmarks
        raw_index_thumb_contact = self._pinch_ratio(right, 8) < self.tuning["pinch_contact"]
        raw_fist = is_fist(points)
        # A closed-finger index-thumb pinch is deliberately a valid left-click
        # pose. Keep raw_fist for pause detection, but do not let it swallow
        # the dominant-hand click before the pinch state machine sees it.
        fist = raw_fist and not raw_index_thumb_contact
        support_fist = left is not None and is_fist(left.landmarks)
        both_fists = raw_fist and support_fist
        two_finger_scroll = is_two_finger_scroll_pose(points, right.world_landmarks)
        if not two_finger_scroll:
            self._two_finger_scroll_y = None
            self._two_finger_scroll_x = None
            self._two_finger_scroll_last_emit = -10.0
        # Pausing is deliberately a two-fist gesture. While paused, only the
        # dominant pointer hand needs to make a fist to resume, which makes the
        # rule mirror naturally in left-handed mode.
        pause_pose = both_fists if not self.paused else raw_fist
        if pause_pose:
            if self._fist_since is None:
                self._fist_since = timestamp
            if timestamp - self._fist_since >= self.tuning["pause_hold_seconds"] and not self._fist_latched:
                self._fist_latched = True
                actions.extend(self.set_paused(not self.paused))
                actions.append(GestureAction("pause_changed", amount=int(self.paused)))
        else:
            self._fist_since = None
            self._fist_latched = False

        if fist:
            if self._dragging:
                actions.append(GestureAction("left_up"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            if self._index_pinched:
                actions.append(GestureAction("pinch_cancel"))
                self._index_pinched = False
            if not pause_pose:
                label = "Paused · hold your active fist to resume" if self.paused else "Show both fists to pause"
            else:
                hold_label = "Hold your active fist…" if self.paused else "Hold both fists…"
                label = hold_label if not self._fist_latched else ("Paused" if self.paused else "Control resumed")
            return GestureFrame(tuple(actions), label, True, left is not None, self.paused)
        if self.paused:
            self._two_finger_scroll_y = None
            self._two_finger_scroll_x = None
            return GestureFrame(tuple(actions), "Paused · hold your active fist to resume", True, left is not None, True)

        index_ratio = self._pinch_ratio(right, 8)
        middle_ratio = self._pinch_ratio(right, 12)
        index_now = self._stable_pinch("index", index_ratio, self._index_pinched, timestamp)
        middle_contact = self._stable_pinch("middle", middle_ratio, self._middle_pinched, timestamp)
        # Continue filtering middle contact even when its pose is invalid, but
        # only expose it as a right click while index, ring and little fingers
        # are all clearly open. This rejects fist-like false right clicks.
        middle_now = middle_contact and is_right_click_pose(points)
        left_index_now = False
        if left is not None:
            left_index_ratio = self._pinch_ratio(left, 8)
            left_index_now = self._stable_pinch("support_index", left_index_ratio, self._left_index_pinched, timestamp)
        else:
            self._clear_pinch_signal("support_index")
        left_open = left is not None and is_open_palm(left.landmarks)
        left_zoom_fingers_open = left is not None and is_zoom_pinch_pose(left.landmarks)
        right_zoom_fingers_open = is_zoom_pinch_pose(right.landmarks)
        raw_left_fist = left is not None and is_fist(left.landmarks)
        if raw_left_fist and not left_zoom_fingers_open:
            self._left_fist_last_seen = timestamp
        left_fist = (
            left is not None
            and not left_zoom_fingers_open
            and (raw_left_fist or timestamp - self._left_fist_last_seen <= 0.18)
        )

        # Check raw three-finger swipes before the open-palm volume gate. Any
        # actual pinch still blocks swiping and gives existing modes priority.
        physical_pinch = {
            dominant_name.lower(): index_now or middle_now,
            support_name.lower(): left_index_now,
        }
        swipe_result, swipe_debug = self._process_app_swipes(hands, timestamp, physical_pinch)
        if swipe_result is not None:
            action = {"right": "app_next", "left": "app_previous", "up": "task_view", "down": "show_desktop"}[swipe_result.direction]
            actions.append(GestureAction(action))
            self._index_pinched = index_now
            self._middle_pinched = middle_now
            self._left_index_pinched = left_index_now
            gesture = swipe_result.debug_text if self.tuning["swipe_debug"] else (
                {"right": "Next application", "left": "Previous application", "up": "Task View", "down": "Show desktop"}[swipe_result.direction]
            )
            return GestureFrame(tuple(actions), gesture, True, left is not None, False)
        dominant_swipe_active = self._swipes[dominant_name.lower()].state in (
            SwipeState.ARMED,
            SwipeState.TRACKING,
        )
        if dominant_swipe_active:
            self._index_pinched = False
            self._middle_pinched = False
            self._left_index_pinched = left_index_now
            self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            gesture = swipe_debug or "Three-finger swipe · move up, down, left, or right"
            return GestureFrame(tuple(actions), gesture, True, left is not None, False)

        both_index_pinched = left is not None and index_now and left_index_now
        both_zoom_ready = (
            both_index_pinched
            and right_zoom_fingers_open
            and left_zoom_fingers_open
        )
        if both_zoom_ready or self._zoom_mode:
            # If the left hand disappears entirely during a zoom, exit zoom
            # immediately so the right-hand pinch is not trapped in limbo.
            if self._zoom_mode and left is None:
                self._zoom_mode = False
                self._zoom_last_distance = None
                self._zoom_smoothed_distance = None
                self._zoom_reference_distance = 0.0
                self._zoom_accumulator = 0.0
                self._left_index_pinched = False
                self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
                # Fall through to normal pointer/click handling below.
            elif both_zoom_ready:
                if not self._zoom_mode:
                    if self._dragging:
                        actions.append(GestureAction("left_up"))
                    if self._index_pinched:
                        actions.append(GestureAction("pinch_cancel"))
                    self._dragging = False
                    self._drag_start_point = None
                    self._drag_moved = False
                    self._zoom_mode = True
                    assert right is not None and left is not None
                    self._zoom_last_distance = self._two_hand_pinch_distance(right, left)
                    self._zoom_smoothed_distance = self._zoom_last_distance
                    self._zoom_reference_distance = self._zoom_last_distance
                    self._zoom_accumulator = 0.0
                    self._zoom_last_emit = timestamp
                else:
                    assert right is not None and left is not None
                    distance = self._two_hand_pinch_distance(right, left)
                    if self._zoom_smoothed_distance is None:
                        self._zoom_smoothed_distance = distance
                    else:
                        previous = self._zoom_smoothed_distance
                        smoothing = self.tuning["zoom_smoothing"]
                        self._zoom_smoothed_distance = previous * (1.0 - smoothing) + distance * smoothing
                        self._zoom_accumulator += self._zoom_smoothed_distance - previous
                    self._zoom_last_distance = distance
                    step = max(0.018, min(0.035, self._zoom_reference_distance * self.tuning["zoom_step_factor"]))
                    self._zoom_accumulator = max(-3 * step, min(3 * step, self._zoom_accumulator))
                    if abs(self._zoom_accumulator) >= step and timestamp - self._zoom_last_emit >= self.tuning["zoom_emit_interval"]:
                        direction = 1 if self._zoom_accumulator > 0 else -1
                        actions.append(GestureAction("zoom", amount=direction))
                        self._zoom_accumulator -= direction * step
                        self._zoom_last_emit = timestamp
                gesture = "Zoom in" if actions and actions[-1].kind == "zoom" and actions[-1].amount > 0 else "Zoom out" if actions and actions[-1].kind == "zoom" and actions[-1].amount < 0 else "Zoom · move hands apart or together"
                self._index_pinched = index_now
                self._left_index_pinched = left_index_now
                self._middle_pinched = middle_now
                self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
                return GestureFrame(tuple(actions), gesture, True, True, False)

            self._index_pinched = index_now
            self._left_index_pinched = left_index_now
            self._middle_pinched = middle_now
            self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            if index_now or left_index_now:
                return GestureFrame(tuple(actions), "Zoom complete · release both pinches", True, left is not None, False)
            self._zoom_mode = False
            self._zoom_last_distance = None
            self._zoom_smoothed_distance = None
            self._zoom_reference_distance = 0.0
            self._zoom_accumulator = 0.0
            return GestureFrame(tuple(actions), "Zoom complete", True, left is not None, False)

        if both_index_pinched and not left_fist:
            if self._index_pinched:
                actions.append(GestureAction("pinch_cancel"))
            self._index_pinched = index_now
            self._left_index_pinched = left_index_now
            self._middle_pinched = middle_now
            self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            return GestureFrame(tuple(actions), "Zoom pose · keep other three fingers open", True, True, False)

        # A left fist reserves the right index pinch for vertical scrolling.
        if left_fist:
            if self._dragging:
                actions.append(GestureAction("left_up"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            if self._index_pinched and self._scroll_y is None:
                actions.append(GestureAction("pinch_cancel"))
            self._middle_pinched = middle_now
            self._volume_y = None
            if index_now or self._index_pinched:
                self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            if index_now:
                current_y = points[8].y
                if self._scroll_y is None:
                    self._scroll_y = current_y
                else:
                    step = self.tuning["scroll_step"] / self.sensitivity
                    delta = self._scroll_y - current_y
                    amount = int(delta / step)
                    if amount:
                        amount = max(-3, min(3, amount))
                        actions.append(GestureAction("scroll", amount=amount))
                        self._scroll_y -= amount * step
                gesture = "Scroll up" if actions and actions[-1].amount > 0 else "Scroll down" if actions and actions[-1].amount < 0 else "Scroll · move pinched hand"
            else:
                self._scroll_y = None
                gesture = "Scroll mode · pinch index + thumb"
            self._index_pinched = index_now
            self._left_index_pinched = left_index_now
            return GestureFrame(tuple(actions), gesture, True, True, False)

        # Open left palm reserves index pinch for volume and prevents a left click.
        if left_open and (index_now or self._index_pinched):
            if self._dragging:
                actions.append(GestureAction("left_up"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            if self._index_pinched and self._volume_y is None:
                actions.append(GestureAction("pinch_cancel"))
            self._middle_pinched = middle_now
            if index_now or self._index_pinched:
                self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            if index_now:
                current_y = points[8].y
                if self._volume_y is None:
                    self._volume_y = current_y
                else:
                    step = self.tuning["volume_step"] / self.sensitivity
                    delta = self._volume_y - current_y
                    amount = int(delta / step)
                    if amount:
                        amount = max(-3, min(3, amount))
                        actions.append(GestureAction("volume", amount=amount))
                        self._volume_y -= amount * step
                gesture = "Volume up" if actions and actions[-1].amount > 0 else "Volume down" if actions and actions[-1].amount < 0 else "Volume · move pinched hand"
            else:
                self._volume_y = None
                gesture = "Volume mode · pinch index + thumb"
            self._index_pinched = index_now
            self._left_index_pinched = left_index_now
            return GestureFrame(tuple(actions), gesture, True, True, False)

        # A deliberate two-finger pose scrolls without requiring the support
        # hand. Folding the other fingers keeps it distinct from an open palm,
        # either pinch, and ordinary pointer tracking.
        if two_finger_scroll:
            if self._dragging:
                actions.append(GestureAction("left_up"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            if self._index_pinched:
                actions.append(GestureAction("pinch_cancel"))
            self._index_pinched = False
            self._middle_pinched = False
            self._left_index_pinched = left_index_now
            self._volume_y = None
            self._scroll_y = None
            self._pointer_resume_at = timestamp + self.tuning["gesture_settle_delay"]
            current_x = (points[8].x + points[12].x) * 0.5
            current_y = (points[8].y + points[12].y) * 0.5
            if self._two_finger_scroll_y is None or self._two_finger_scroll_x is None:
                self._two_finger_scroll_x = current_x
                self._two_finger_scroll_y = current_y
                self._two_finger_scroll_last_emit = timestamp
            else:
                horizontal_delta = current_x - self._two_finger_scroll_x
                vertical_delta = self._two_finger_scroll_y - current_y
                horizontal = abs(horizontal_delta) > abs(vertical_delta)
                delta = horizontal_delta if horizontal else vertical_delta
                dead_zone = self.tuning["two_finger_dead_zone"] / self.sensitivity
                if abs(delta) < dead_zone:
                    # Slowly follow harmless drift while the hand is centered.
                    self._two_finger_scroll_x = self._two_finger_scroll_x * 0.92 + current_x * 0.08
                    self._two_finger_scroll_y = self._two_finger_scroll_y * 0.92 + current_y * 0.08
                else:
                    strength = min(3, 1 + int((abs(delta) - dead_zone) / 0.035))
                    interval = {1: 0.055, 2: 0.045, 3: 0.035}[strength]
                    if timestamp - self._two_finger_scroll_last_emit >= interval:
                        direction = 1 if delta > 0 else -1
                        actions.append(GestureAction("scroll_horizontal" if horizontal else "scroll", amount=direction * strength))
                        self._two_finger_scroll_last_emit = timestamp
            if actions and actions[-1].kind in ("scroll", "scroll_horizontal"):
                if actions[-1].kind == "scroll_horizontal":
                    gesture = "Two-finger scroll right" if actions[-1].amount > 0 else "Two-finger scroll left"
                else:
                    gesture = "Two-finger scroll up" if actions[-1].amount > 0 else "Two-finger scroll down"
            else:
                gesture = "Two-finger scroll · move in any direction"
            return GestureFrame(tuple(actions), gesture, True, left is not None, False)

        self._volume_y = None
        self._scroll_y = None
        was_index_pinched = self._index_pinched
        was_middle_pinched = self._middle_pinched
        dragging_before = self._dragging
        completed_double_click = False

        pinch_started = (index_now and not was_index_pinched) or (middle_now and not was_middle_pinched)
        if pinch_started and self._last_pointer_point is not None:
            self._pinch_offset = (
                self._last_pointer_point.x - points[8].x,
                self._last_pointer_point.y - points[8].y,
            )
        if index_now and not was_index_pinched and not middle_now:
            self._pinch_drag_filter.reset()

        if middle_now and not was_middle_pinched and not index_now and timestamp - self._last_right_click > self.tuning["right_click_cooldown"]:
            actions.append(GestureAction("right_click"))
            self._last_right_click = timestamp

        if index_now and not was_index_pinched and not middle_now:
            if timestamp - self._last_index_release <= self.tuning["double_click_window"]:
                self._dragging = True
                self._drag_start_point = (points[8].x, points[8].y)
                self._drag_started_at = timestamp
                self._drag_moved = False
                actions.append(GestureAction("left_down"))
                self._last_index_release = -10.0
            else:
                actions.append(GestureAction("pinch_start"))
        elif not index_now and was_index_pinched:
            if self._dragging:
                actions.append(GestureAction("left_up"))
                completed_double_click = not self._drag_moved and timestamp - self._drag_started_at <= self.tuning["double_click_window"]
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            else:
                actions.append(GestureAction("left_click"))
                self._last_index_release = timestamp

        pinch_released = (was_index_pinched and not index_now) or (was_middle_pinched and not middle_now)
        if pinch_released:
            self._pointer_resume_at = timestamp + self.tuning["click_settle_delay"]

        drag_started = self._dragging and not dragging_before
        if self._dragging and index_now and not drag_started:
            if self._drag_start_point is not None and not self._drag_moved:
                travel = math.hypot(
                    points[8].x - self._drag_start_point[0],
                    points[8].y - self._drag_start_point[1],
                )
                self._drag_moved = travel >= self.tuning["drag_start_distance"]
            drag_point = Landmark(
                points[8].x + self._pinch_offset[0],
                points[8].y + self._pinch_offset[1],
                points[8].z,
            )
            if self._drag_moved:
                pointer_x, pointer_y = self._map_pointer(drag_point, timestamp, confidence=right.confidence)
                actions.append(GestureAction("move", pointer_x, pointer_y))
                self._last_pointer_point = drag_point
        elif index_now and not middle_now and not drag_started:
            drag_point = Landmark(
                points[8].x + self._pinch_offset[0],
                points[8].y + self._pinch_offset[1],
                points[8].z,
            )
            pointer_x, pointer_y = self._map_pointer(
                drag_point, timestamp, self._pinch_drag_filter, confidence=right.confidence,
            )
            actions.append(GestureAction("pinch_move", pointer_x, pointer_y))
        elif not index_now and not middle_now and not was_index_pinched and not was_middle_pinched and timestamp >= self._pointer_resume_at:
            # Graduated slowdown: the pointer decelerates linearly as the
            # finger approaches the pinch contact threshold. This keeps
            # normal navigation quick while making small targets easier to
            # acquire just before the click is committed.
            precision_factor = 0.0
            if self.tuning["precision_enabled"] >= 0.5 and index_ratio < self.tuning["precision_ratio"]:
                outer = self.tuning["precision_ratio"]
                inner = self.tuning["pinch_contact"]
                span = outer - inner
                if span > 0.01:
                    # 1.0 at the contact edge, 0.0 at the outer boundary.
                    proximity = max(0.0, min(1.0, (outer - index_ratio) / span))
                    precision_factor = proximity
                else:
                    precision_factor = 1.0
            pointer_x, pointer_y = self._map_pointer(
                points[8],
                timestamp,
                precision_factor=precision_factor,
                confidence=right.confidence,
            )
            actions.append(GestureAction("move", pointer_x, pointer_y))
            self._last_pointer_point = points[8]
            self._pinch_offset = (0.0, 0.0)

        self._index_pinched = index_now
        self._middle_pinched = middle_now
        self._left_index_pinched = left_index_now

        if completed_double_click:
            gesture = "Double click"
        elif self._dragging:
            gesture = "Dragging · release to drop"
        elif index_now:
            gesture = "Pointer locked · left pinch"
        elif middle_now:
            gesture = "Pointer locked · right click"
        elif timestamp < self._pointer_resume_at:
            gesture = "Pointer settling"
        elif swipe_debug:
            gesture = swipe_debug
        else:
            gesture = "Pointer tracking"
        return GestureFrame(tuple(actions), gesture, True, left is not None, False)
