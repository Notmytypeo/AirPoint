from __future__ import annotations

from dataclasses import dataclass
import math

from .filters import PointFilter


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class HandObservation:
    handedness: str
    landmarks: tuple[Landmark, ...]


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


def _finger_extended(points: tuple[Landmark, ...], mcp: int, pip: int, dip: int, tip: int) -> bool:
    straight = _angle(points[mcp], points[pip], points[dip]) > 145 and _angle(points[pip], points[dip], points[tip]) > 135
    reach = _distance(points[tip], points[0]) > _distance(points[pip], points[0]) * 1.08
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


def is_two_finger_scroll_pose(points: tuple[Landmark, ...]) -> bool:
    """Index and middle are raised while ring and little fingers are folded."""
    if len(points) < 21:
        return False
    extended = (
        _finger_extended(points, 5, 6, 7, 8),
        _finger_extended(points, 9, 10, 11, 12),
        _finger_extended(points, 13, 14, 15, 16),
        _finger_extended(points, 17, 18, 19, 20),
    )
    palm_width = max(_distance(points[5], points[17]), 0.035)
    fingers_together = _distance(points[8], points[12]) / palm_width < 0.75
    return extended[0] and extended[1] and not extended[2] and not extended[3] and fingers_together


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
        self.paused = False
        self._filter = PointFilter()
        self._pinch_drag_filter = PointFilter()
        self._index_pinched = False
        self._middle_pinched = False
        self._left_index_pinched = False
        self._pinch_filtered: dict[str, float] = {}
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
        self._two_finger_scroll_last_emit = -10.0
        self._pointer_resume_at = -10.0
        self._last_pointer_point: Landmark | None = None
        self._pinch_offset = (0.0, 0.0)
        self._missing_since: float | None = None

    def configure(
        self,
        sensitivity: float,
        screen: tuple[int, int, int, int],
        left_handed: bool = False,
    ) -> None:
        self.sensitivity = max(0.5, min(1.8, sensitivity))
        self.screen = screen
        self.left_handed = left_handed

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
        self.__init__()
        self.paused = paused
        self.configure(sensitivity, screen, left_handed)
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
        self._two_finger_scroll_last_emit = -10.0
        self._left_fist_last_seen = -10.0
        self._last_pointer_point = None
        self._pinch_offset = (0.0, 0.0)
        self._filter.reset()
        self._pinch_drag_filter.reset()
        return tuple(actions)

    @staticmethod
    def _find(hands: tuple[HandObservation, ...], name: str) -> HandObservation | None:
        return next((hand for hand in hands if hand.handedness.lower() == name.lower()), None)

    @staticmethod
    def _pinch_ratio(points: tuple[Landmark, ...], tip: int) -> float:
        # Preserve the original 2D fingertip detector. Palm length is only a
        # fallback when projected palm width collapses in an edge-on view.
        palm_scale = max(
            _distance(points[5], points[17]),
            _distance(points[0], points[9]) * 0.72,
            0.035,
        )
        return _distance(points[4], points[tip]) / palm_scale

    def _stable_pinch(self, key: str, ratio: float, was_pinched: bool, timestamp: float) -> bool:
        """Low-latency pinch hysteresis with protection from landmark flicker."""
        previous = self._pinch_filtered.get(key, ratio)
        # Contact gets slightly more weight than release so real pinches feel
        # immediate while a single outward landmark jump cannot end a hold.
        alpha = 0.68 if ratio < previous else 0.58
        filtered = previous * (1.0 - alpha) + ratio * alpha
        self._pinch_filtered[key] = filtered

        if was_pinched:
            self._pinch_candidate_since.pop(key, None)
            if filtered < 0.50:
                self._pinch_release_since.pop(key, None)
                return True
            # A clearly open finger should release immediately; only ambiguous
            # values near the boundary receive a short dropout grace period.
            if ratio >= 0.75 and filtered >= 0.58:
                self._pinch_release_since.pop(key, None)
                return False
            release_since = self._pinch_release_since.setdefault(key, timestamp)
            if timestamp - release_since < 0.075:
                return True
            self._pinch_release_since.pop(key, None)
            return False

        self._pinch_release_since.pop(key, None)
        # Raw deep contact is trusted immediately even when the preceding open
        # frame keeps the smoothed value temporarily above the boundary.
        if ratio <= 0.30:
            self._pinch_candidate_since.pop(key, None)
            return True
        if ratio >= 0.34 or filtered >= 0.34:
            self._pinch_candidate_since.pop(key, None)
            return False
        # Strong fingertip contact remains single-frame responsive. A shallow
        # boundary contact must persist briefly before it becomes a click.
        if filtered <= 0.32:
            self._pinch_candidate_since.pop(key, None)
            return True
        candidate_since = self._pinch_candidate_since.setdefault(key, timestamp)
        if timestamp - candidate_since >= 0.025:
            self._pinch_candidate_since.pop(key, None)
            return True
        return False

    def _clear_pinch_signal(self, key: str) -> None:
        self._pinch_filtered.pop(key, None)
        self._pinch_candidate_since.pop(key, None)
        self._pinch_release_since.pop(key, None)

    def _map_pointer(self, point: Landmark, timestamp: float, motion_filter: PointFilter | None = None) -> tuple[int, int]:
        # The camera frame is mirrored before inference, so x maps naturally.
        # Amplify the central hand workspace so reaching every screen edge does
        # not require shoulder/arm travel. The motion filter still absorbs the
        # extra gain from natural fingertip tremor.
        zoom = 0.84 + self.sensitivity * 0.48
        nx = 0.5 + (point.x - 0.5) * zoom
        ny = 0.5 + (point.y - 0.5) * zoom
        margin_x, margin_y = 0.14, 0.15
        nx = max(0.0, min(1.0, (nx - margin_x) / (1.0 - 2 * margin_x)))
        ny = max(0.0, min(1.0, (ny - margin_y) / (1.0 - 2 * margin_y)))
        sx, sy = (motion_filter or self._filter).apply(nx, ny, timestamp)
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
                self._last_pointer_point = None
                self._pinch_offset = (0.0, 0.0)
                self._filter.reset()
                self._pinch_drag_filter.reset()
            return GestureFrame(tuple(actions), f"Show your {dominant_name.lower()} hand", False, left is not None, self.paused)
        self._missing_since = None

        points = right.landmarks
        fist = is_fist(points)
        two_finger_scroll = is_two_finger_scroll_pose(points)
        if not two_finger_scroll:
            self._two_finger_scroll_y = None
            self._two_finger_scroll_last_emit = -10.0
        if fist:
            if self._fist_since is None:
                self._fist_since = timestamp
            if timestamp - self._fist_since >= 0.7 and not self._fist_latched:
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
            label = "Hold…" if not self._fist_latched else ("Paused" if self.paused else "Control resumed")
            return GestureFrame(tuple(actions), label, True, left is not None, self.paused)
        if self.paused:
            self._two_finger_scroll_y = None
            return GestureFrame(tuple(actions), "Paused · hold a fist to resume", True, left is not None, True)

        index_ratio = self._pinch_ratio(points, 8)
        middle_ratio = self._pinch_ratio(points, 12)
        index_now = self._stable_pinch("index", index_ratio, self._index_pinched, timestamp)
        middle_now = self._stable_pinch("middle", middle_ratio, self._middle_pinched, timestamp)
        left_index_now = False
        if left is not None:
            left_index_ratio = self._pinch_ratio(left.landmarks, 8)
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

        both_index_pinched = left is not None and index_now and left_index_now
        both_zoom_ready = (
            both_index_pinched
            and right_zoom_fingers_open
            and left_zoom_fingers_open
        )
        if both_zoom_ready or self._zoom_mode:
            if both_zoom_ready:
                if not self._zoom_mode:
                    if self._dragging:
                        actions.append(GestureAction("left_up"))
                    if self._index_pinched:
                        actions.append(GestureAction("pinch_cancel"))
                    self._dragging = False
                    self._drag_start_point = None
                    self._drag_moved = False
                    self._zoom_mode = True
                    self._zoom_last_distance = self._two_hand_pinch_distance(right, left)
                    self._zoom_smoothed_distance = self._zoom_last_distance
                    self._zoom_reference_distance = self._zoom_last_distance
                    self._zoom_accumulator = 0.0
                    self._zoom_last_emit = timestamp
                else:
                    distance = self._two_hand_pinch_distance(right, left)
                    if self._zoom_smoothed_distance is None:
                        self._zoom_smoothed_distance = distance
                    else:
                        previous = self._zoom_smoothed_distance
                        self._zoom_smoothed_distance = previous * 0.45 + distance * 0.55
                        self._zoom_accumulator += self._zoom_smoothed_distance - previous
                    self._zoom_last_distance = distance
                    step = max(0.018, min(0.035, self._zoom_reference_distance * 0.055))
                    self._zoom_accumulator = max(-3 * step, min(3 * step, self._zoom_accumulator))
                    if abs(self._zoom_accumulator) >= step and timestamp - self._zoom_last_emit >= 0.09:
                        direction = 1 if self._zoom_accumulator > 0 else -1
                        actions.append(GestureAction("zoom", amount=direction))
                        self._zoom_accumulator -= direction * step
                        self._zoom_last_emit = timestamp
                gesture = "Zoom in" if actions and actions[-1].kind == "zoom" and actions[-1].amount > 0 else "Zoom out" if actions and actions[-1].kind == "zoom" and actions[-1].amount < 0 else "Zoom · move hands apart or together"
                self._index_pinched = index_now
                self._left_index_pinched = left_index_now
                self._middle_pinched = middle_now
                self._pointer_resume_at = timestamp + 0.1
                return GestureFrame(tuple(actions), gesture, True, True, False)

            self._index_pinched = index_now
            self._left_index_pinched = left_index_now
            self._middle_pinched = middle_now
            self._pointer_resume_at = timestamp + 0.1
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
            self._pointer_resume_at = timestamp + 0.1
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
                self._pointer_resume_at = timestamp + 0.1
            if index_now:
                current_y = points[8].y
                if self._scroll_y is None:
                    self._scroll_y = current_y
                else:
                    step = 0.026 / self.sensitivity
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
        if left_open:
            if self._dragging:
                actions.append(GestureAction("left_up"))
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            if self._index_pinched and self._volume_y is None:
                actions.append(GestureAction("pinch_cancel"))
            self._middle_pinched = middle_now
            if index_now or self._index_pinched:
                self._pointer_resume_at = timestamp + 0.1
            if index_now:
                current_y = points[8].y
                if self._volume_y is None:
                    self._volume_y = current_y
                else:
                    step = 0.027 / self.sensitivity
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
            self._pointer_resume_at = timestamp + 0.1
            current_y = (points[8].y + points[12].y) * 0.5
            if self._two_finger_scroll_y is None:
                self._two_finger_scroll_y = current_y
                self._two_finger_scroll_last_emit = timestamp
            else:
                delta = self._two_finger_scroll_y - current_y
                dead_zone = 0.024 / self.sensitivity
                if abs(delta) < dead_zone:
                    # Slowly follow harmless drift while the hand is centered.
                    self._two_finger_scroll_y = self._two_finger_scroll_y * 0.92 + current_y * 0.08
                else:
                    strength = min(3, 1 + int((abs(delta) - dead_zone) / 0.035))
                    interval = {1: 0.11, 2: 0.085, 3: 0.065}[strength]
                    if timestamp - self._two_finger_scroll_last_emit >= interval:
                        direction = 1 if delta > 0 else -1
                        actions.append(GestureAction("scroll", amount=direction * strength))
                        self._two_finger_scroll_last_emit = timestamp
            if actions and actions[-1].kind == "scroll":
                gesture = "Two-finger scroll up" if actions[-1].amount > 0 else "Two-finger scroll down"
            else:
                gesture = "Two-finger scroll · move vertically"
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

        if middle_now and not was_middle_pinched and not index_now and timestamp - self._last_right_click > 0.32:
            actions.append(GestureAction("right_click"))
            self._last_right_click = timestamp

        if index_now and not was_index_pinched and not middle_now:
            if timestamp - self._last_index_release <= 0.5:
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
                completed_double_click = not self._drag_moved and timestamp - self._drag_started_at <= 0.5
                self._dragging = False
                self._drag_start_point = None
                self._drag_moved = False
            else:
                actions.append(GestureAction("left_click"))
                self._last_index_release = timestamp

        pinch_released = (was_index_pinched and not index_now) or (was_middle_pinched and not middle_now)
        if pinch_released:
            self._pointer_resume_at = timestamp + 0.085

        drag_started = self._dragging and not dragging_before
        if self._dragging and index_now and not drag_started:
            if self._drag_start_point is not None and not self._drag_moved:
                travel = math.hypot(
                    points[8].x - self._drag_start_point[0],
                    points[8].y - self._drag_start_point[1],
                )
                self._drag_moved = travel >= 0.018
            drag_point = Landmark(
                points[8].x + self._pinch_offset[0],
                points[8].y + self._pinch_offset[1],
                points[8].z,
            )
            if self._drag_moved:
                pointer_x, pointer_y = self._map_pointer(drag_point, timestamp)
                actions.append(GestureAction("move", pointer_x, pointer_y))
                self._last_pointer_point = drag_point
        elif index_now and not middle_now and not drag_started:
            drag_point = Landmark(
                points[8].x + self._pinch_offset[0],
                points[8].y + self._pinch_offset[1],
                points[8].z,
            )
            pointer_x, pointer_y = self._map_pointer(drag_point, timestamp, self._pinch_drag_filter)
            actions.append(GestureAction("pinch_move", pointer_x, pointer_y))
        elif not index_now and not middle_now and not was_index_pinched and not was_middle_pinched and timestamp >= self._pointer_resume_at:
            pointer_x, pointer_y = self._map_pointer(points[8], timestamp)
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
        else:
            gesture = "Pointer tracking"
        return GestureFrame(tuple(actions), gesture, True, left is not None, False)
