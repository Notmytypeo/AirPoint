from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math


class SwipeState(str, Enum):
    IDLE = "idle"
    ARMED = "armed"
    TRACKING = "tracking"
    FIRED = "fired"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class SwipeResult:
    state: SwipeState
    direction: str = ""
    dx: float = 0.0
    dy: float = 0.0
    velocity: float = 0.0
    frames: int = 0

    @property
    def debug_text(self) -> str:
        return f"3-finger swipe {self.state.value} · dx {self.dx:+.3f} · dy {self.dy:+.3f} · v {self.velocity:+.2f} · {self.frames}f"


class ThreeFingerSwipeDetector:
    """Raw non-dominant-hand three-finger swipe state machine.

    Pose: index, middle, and ring fingers extended; thumb and little finger
    folded. Motion uses the raw centroid of those three fingertips, never the
    One Euro cursor position.
    """

    def __init__(self) -> None:
        self.state = SwipeState.IDLE
        self._axis = ""
        self._pose_frames = 0
        self._samples: deque[tuple[float, float, float]] = deque()
        self._armed_at = -10.0
        self._cooldown_until = -10.0

    def reset(self) -> None:
        self.state = SwipeState.IDLE
        self._axis = ""
        self._pose_frames = 0
        self._samples.clear()
        self._armed_at = -10.0

    @staticmethod
    def _distance(a, b) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)

    @classmethod
    def _finger_extended(cls, points, mcp: int, pip: int, dip: int, tip: int, extension_angle: float) -> bool:
        def angle(a, b, c) -> float:
            ab = (a.x - b.x, a.y - b.y)
            cb = (c.x - b.x, c.y - b.y)
            denominator = math.hypot(*ab) * math.hypot(*cb)
            if denominator < 1e-8:
                return 0.0
            cosine = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / denominator))
            return math.degrees(math.acos(cosine))

        straight = (
            angle(points[mcp], points[pip], points[dip]) > extension_angle
            and angle(points[pip], points[dip], points[tip]) > extension_angle - 12
        )
        reaches_out = cls._distance(points[tip], points[0]) > cls._distance(points[pip], points[0]) * 0.98
        return straight and reaches_out

    @classmethod
    def _is_three_finger_pose(cls, points, tuning: dict[str, float]) -> bool:
        extension_angle = tuning["swipe_extension_angle"]
        index = cls._finger_extended(points, 5, 6, 7, 8, extension_angle)
        middle = cls._finger_extended(points, 9, 10, 11, 12, extension_angle)
        ring = cls._finger_extended(points, 13, 14, 15, 16, extension_angle)
        little = cls._finger_extended(points, 17, 18, 19, 20, extension_angle)
        palm_width = max(cls._distance(points[5], points[17]), 0.035)
        spread = cls._distance(points[8], points[16]) / palm_width
        thumb_folded = cls._distance(points[4], points[0]) / palm_width < tuning["swipe_thumb_fold_limit"]
        return index and middle and ring and not little and thumb_folded and spread >= tuning["swipe_min_spread"]

    @staticmethod
    def _three_finger_center(points) -> tuple[float, float]:
        return (
            (points[8].x + points[12].x + points[16].x) / 3.0,
            (points[8].y + points[12].y + points[16].y) / 3.0,
        )

    def process(self, points, timestamp: float, *, pinch_active: bool, tuning: dict[str, float]) -> SwipeResult:
        if not tuning["swipe_enabled"]:
            self.reset()
            return SwipeResult(SwipeState.IDLE)
        if self.state in (SwipeState.FIRED, SwipeState.COOLDOWN):
            if timestamp < self._cooldown_until:
                self.state = SwipeState.COOLDOWN
                return SwipeResult(self.state)
            self.reset()

        if pinch_active or not self._is_three_finger_pose(points, tuning):
            self.reset()
            return SwipeResult(SwipeState.IDLE)

        x, y = self._three_finger_center(points)
        if self.state == SwipeState.IDLE:
            self._pose_frames = 1
            self._samples.append((timestamp, x, y))
            self.state = SwipeState.ARMED
            self._armed_at = timestamp
            return SwipeResult(self.state, frames=self._pose_frames)

        self._pose_frames += 1
        self._samples.append((timestamp, x, y))
        while self._samples and timestamp - self._samples[0][0] > tuning["swipe_window_seconds"]:
            self._samples.popleft()
        start_time, start_x, start_y = self._samples[0]
        elapsed = max(timestamp - start_time, 1e-4)
        dx, dy = x - start_x, y - start_y
        if self._pose_frames < round(tuning["swipe_min_hold_frames"]):
            return SwipeResult(self.state, dx=dx, dy=dy, frames=self._pose_frames)

        horizontal_valid = abs(dy) <= tuning["swipe_vertical_tolerance"]
        vertical_valid = abs(dx) <= tuning["swipe_horizontal_tolerance"]
        if self.state == SwipeState.ARMED:
            if abs(dx) >= tuning["swipe_arm_distance"] and horizontal_valid:
                self.state, self._axis = SwipeState.TRACKING, "horizontal"
            elif abs(dy) >= tuning["swipe_arm_distance"] and vertical_valid:
                self.state, self._axis = SwipeState.TRACKING, "vertical"
            elif timestamp - self._armed_at > tuning["swipe_window_seconds"] * 1.5:
                self.reset()
                return SwipeResult(SwipeState.IDLE, dx=dx, dy=dy, frames=self._pose_frames)
            return SwipeResult(self.state, dx=dx, dy=dy, frames=self._pose_frames)

        primary_delta = dx if self._axis == "horizontal" else dy
        orthogonal_valid = horizontal_valid if self._axis == "horizontal" else vertical_valid
        velocity = primary_delta / elapsed
        if not orthogonal_valid:
            self.reset()
            return SwipeResult(SwipeState.IDLE, dx=dx, dy=dy, velocity=velocity, frames=self._pose_frames)
        if abs(primary_delta) >= tuning["swipe_fire_distance"] and abs(velocity) >= tuning["swipe_min_velocity"]:
            if self._axis == "horizontal":
                direction = "right" if dx > 0 else "left"
            else:
                direction = "down" if dy > 0 else "up"
            self.state = SwipeState.FIRED
            self._cooldown_until = timestamp + tuning["swipe_cooldown_seconds"]
            return SwipeResult(self.state, direction, dx, dy, velocity, self._pose_frames)
        return SwipeResult(self.state, dx=dx, dy=dy, velocity=velocity, frames=self._pose_frames)
