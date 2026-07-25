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

    _REFERENCE_PALM_WIDTH = 0.24

    def __init__(self) -> None:
        self.state = SwipeState.IDLE
        self._axis = ""
        self._pose_frames = 0
        self._pose_dropouts = 0
        self._samples: deque[tuple[float, float, float, float]] = deque()
        self._armed_at = -10.0
        self._cooldown_until = -10.0

    def reset(self) -> None:
        self.state = SwipeState.IDLE
        self._axis = ""
        self._pose_frames = 0
        self._pose_dropouts = 0
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

    @staticmethod
    def _median(values: list[float]) -> float:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) * 0.5

    def _trajectory(self, robust: bool) -> tuple[float, float, float, float, float]:
        """Return displacement, velocity, and elapsed time for recent samples.

        The robust path uses a tiny Theil-Sen estimator: the median of every
        pairwise slope. At webcam frame rates the window contains only a few
        samples, so this rejects a landmark spike without meaningful cost.
        """
        if len(self._samples) < 2:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        samples = list(self._samples)
        elapsed = max(samples[-1][0] - samples[0][0], 1e-4)
        if not robust:
            dx = samples[-1][1] - samples[0][1]
            dy = samples[-1][2] - samples[0][2]
            return dx, dy, dx / elapsed, dy / elapsed, elapsed

        x_slopes: list[float] = []
        y_slopes: list[float] = []
        for later in range(1, len(samples)):
            for earlier in range(later):
                dt = samples[later][0] - samples[earlier][0]
                if dt <= 1e-4:
                    continue
                x_slopes.append((samples[later][1] - samples[earlier][1]) / dt)
                y_slopes.append((samples[later][2] - samples[earlier][2]) / dt)
        if not x_slopes:
            return 0.0, 0.0, 0.0, 0.0, elapsed
        velocity_x = self._median(x_slopes)
        velocity_y = self._median(y_slopes)
        return velocity_x * elapsed, velocity_y * elapsed, velocity_x, velocity_y, elapsed

    def _motion_scale(self, adaptive: bool) -> float:
        if not adaptive or not self._samples:
            return 1.0
        palm_width = self._median([sample[3] for sample in self._samples])
        # Bound adaptation so a momentarily tiny or oversized hand cannot make
        # a shortcut hypersensitive or impossible to complete.
        return max(0.55, min(1.35, palm_width / self._REFERENCE_PALM_WIDTH))

    def process(self, points, timestamp: float, *, pinch_active: bool, tuning: dict[str, float]) -> SwipeResult:
        if not tuning["swipe_enabled"]:
            self.reset()
            return SwipeResult(SwipeState.IDLE)
        if self.state in (SwipeState.FIRED, SwipeState.COOLDOWN):
            if timestamp < self._cooldown_until:
                self.state = SwipeState.COOLDOWN
                return SwipeResult(self.state)
            self.reset()

        if pinch_active:
            self.reset()
            return SwipeResult(SwipeState.IDLE)
        if not self._is_three_finger_pose(points, tuning):
            grace_frames = round(tuning["swipe_pose_grace_frames"])
            if (
                self.state in (SwipeState.ARMED, SwipeState.TRACKING)
                and self._pose_dropouts < grace_frames
            ):
                self._pose_dropouts += 1
                dx, dy, velocity_x, velocity_y, _ = self._trajectory(
                    tuning["swipe_robust_trajectory"] >= 0.5,
                )
                velocity = velocity_x if self._axis == "horizontal" else velocity_y
                return SwipeResult(self.state, dx=dx, dy=dy, velocity=velocity, frames=self._pose_frames)
            self.reset()
            return SwipeResult(SwipeState.IDLE)
        self._pose_dropouts = 0

        x, y = self._three_finger_center(points)
        palm_width = max(self._distance(points[5], points[17]), 0.035)
        if self.state == SwipeState.IDLE:
            self._pose_frames = 1
            self._samples.append((timestamp, x, y, palm_width))
            self.state = SwipeState.ARMED
            self._armed_at = timestamp
            return SwipeResult(self.state, frames=self._pose_frames)

        self._pose_frames += 1
        self._samples.append((timestamp, x, y, palm_width))
        while self._samples and timestamp - self._samples[0][0] > tuning["swipe_window_seconds"]:
            self._samples.popleft()
        dx, dy, velocity_x, velocity_y, _ = self._trajectory(
            tuning["swipe_robust_trajectory"] >= 0.5,
        )
        if self._pose_frames < round(tuning["swipe_min_hold_frames"]):
            return SwipeResult(self.state, dx=dx, dy=dy, frames=self._pose_frames)

        motion_scale = self._motion_scale(tuning["swipe_scale_adaptation"] >= 0.5)
        arm_distance = tuning["swipe_arm_distance"] * motion_scale
        fire_distance = tuning["swipe_fire_distance"] * motion_scale
        horizontal_valid = abs(dy) <= tuning["swipe_vertical_tolerance"] * motion_scale
        vertical_valid = abs(dx) <= tuning["swipe_horizontal_tolerance"] * motion_scale
        if self.state == SwipeState.ARMED:
            absolute_dx = abs(dx)
            absolute_dy = abs(dy)
            if absolute_dx >= absolute_dy and absolute_dx >= arm_distance and horizontal_valid:
                self.state, self._axis = SwipeState.TRACKING, "horizontal"
            elif absolute_dy > absolute_dx and absolute_dy >= arm_distance and vertical_valid:
                self.state, self._axis = SwipeState.TRACKING, "vertical"
            elif timestamp - self._armed_at > tuning["swipe_window_seconds"] * 1.5:
                # A user commonly presents the three-finger pose, pauses, and
                # only then starts moving. Keep the valid pose armed while
                # rebasing the rolling motion origin so that pause does not
                # create a flickering IDLE window or stale displacement.
                self._samples.clear()
                self._samples.append((timestamp, x, y, palm_width))
                self._pose_frames = 1
                self._armed_at = timestamp
                return SwipeResult(SwipeState.ARMED, frames=self._pose_frames)
            return SwipeResult(self.state, dx=dx, dy=dy, frames=self._pose_frames)

        primary_delta = dx if self._axis == "horizontal" else dy
        orthogonal_valid = horizontal_valid if self._axis == "horizontal" else vertical_valid
        velocity = velocity_x if self._axis == "horizontal" else velocity_y
        if not orthogonal_valid:
            self.reset()
            return SwipeResult(SwipeState.IDLE, dx=dx, dy=dy, velocity=velocity, frames=self._pose_frames)
        if abs(primary_delta) >= fire_distance and abs(velocity) >= tuning["swipe_min_velocity"]:
            if self._axis == "horizontal":
                direction = "right" if dx > 0 else "left"
            else:
                direction = "down" if dy > 0 else "up"
            self.state = SwipeState.FIRED
            self._cooldown_until = timestamp + tuning["swipe_cooldown_seconds"]
            return SwipeResult(self.state, direction, dx, dy, velocity, self._pose_frames)
        return SwipeResult(self.state, dx=dx, dy=dy, velocity=velocity, frames=self._pose_frames)
