from __future__ import annotations

import math
import time


class LowPassFilter:
    def __init__(self) -> None:
        self.value: float | None = None

    def filter(self, value: float, alpha: float) -> float:
        if self.value is None:
            self.value = value
        else:
            self.value = alpha * value + (1.0 - alpha) * self.value
        return self.value

    def reset(self) -> None:
        self.value = None


class OneEuroFilter:
    """Adaptive low-pass filter: stable at rest, responsive during fast motion."""

    def __init__(self, min_cutoff: float = 1.3, beta: float = 0.035, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._signal = LowPassFilter()
        self._derivative = LowPassFilter()
        self._last_raw: float | None = None
        self._last_time: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def __call__(self, value: float, timestamp: float | None = None) -> float:
        now = timestamp if timestamp is not None else time.monotonic()
        if self._last_time is None or self._last_raw is None:
            self._last_time = now
            self._last_raw = value
            return self._signal.filter(value, 1.0)

        dt = min(max(now - self._last_time, 1.0 / 240.0), 0.2)
        derivative = (value - self._last_raw) / dt
        edx = self._derivative.filter(derivative, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        result = self._signal.filter(value, self._alpha(cutoff, dt))
        self._last_time = now
        self._last_raw = value
        return result

    def reset(self) -> None:
        self._signal.reset()
        self._derivative.reset()
        self._last_raw = None
        self._last_time = None


class PointFilter:
    def __init__(
        self,
        dead_zone: float = 0.0031,
        lookahead_frames: float = 1.0,
        min_cutoff: float = 0.70,
        beta: float = 0.90,
        prediction_cap: float = 0.014,
        precision_step: float = 0.012,
        precision_speed_floor: float = 0.55,
        confidence_floor: float = 0.45,
        jump_threshold: float = 0.095,
    ) -> None:
        # Lower cutoff stabilizes a resting hand; higher beta quickly opens the
        # filter during intentional motion. The radial dead zone removes the
        # final few pixels of physiological hand tremor without axis bias.
        self.x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.dead_zone = dead_zone
        # A tiny constant-velocity extrapolation offsets the filter's normal
        # phase lag by about one camera frame. It is capped so sudden hand
        # stops, detector jumps, and low-FPS frames cannot overshoot far.
        self.lookahead_frames = max(0.0, min(1.0, lookahead_frames))
        self.prediction_cap = max(0.0, prediction_cap)
        self.precision_step = max(0.0, precision_step)
        self.precision_speed_floor = max(0.0, min(1.0, precision_speed_floor))
        self.confidence_floor = max(0.0, min(0.95, confidence_floor))
        self.jump_threshold = max(0.01, jump_threshold)
        self._last_base: tuple[float, float] | None = None
        self._last_time: float | None = None
        self._velocity = (0.0, 0.0)
        self._last_measurement: tuple[float, float] | None = None
        self._measurement_velocity = (0.0, 0.0)
        self._rejected_measurement: tuple[float, float] | None = None
        self._input_offset = (0.0, 0.0)

    def configure(
        self,
        *,
        dead_zone: float,
        lookahead_frames: float,
        min_cutoff: float,
        beta: float,
        prediction_cap: float,
        precision_step: float,
        precision_speed_floor: float,
        confidence_floor: float,
        jump_threshold: float,
    ) -> None:
        self.dead_zone = max(0.0, dead_zone)
        self.lookahead_frames = max(0.0, min(1.0, lookahead_frames))
        self.x.min_cutoff = self.y.min_cutoff = max(0.01, min_cutoff)
        self.x.beta = self.y.beta = max(0.0, beta)
        self.prediction_cap = max(0.0, prediction_cap)
        self.precision_step = max(0.0, precision_step)
        self.precision_speed_floor = max(0.0, min(1.0, precision_speed_floor))
        self.confidence_floor = max(0.0, min(0.95, confidence_floor))
        self.jump_threshold = max(0.01, jump_threshold)

    def apply(
        self,
        x: float,
        y: float,
        timestamp: float,
        precision_factor: float = 0.0,
        confidence: float | None = None,
    ) -> tuple[float, float]:
        """Apply filtering to pointer coordinates.

        precision_factor: 0.0 = normal tracking, 1.0 = maximum slowdown
        (finger is about to make pinch contact).  The effective step cap
        and prediction are scaled continuously between these extremes.

        confidence: MediaPipe hand confidence in the 0–1 range. Low-confidence
        samples are blended toward the last trusted measurement, while a single
        large innovation is rejected. A second movement in the same direction
        is accepted so deliberate fast pointer motion remains responsive.
        """
        measurement = (x - self._input_offset[0], y - self._input_offset[1])
        confidence_enabled = confidence is not None
        quality = 1.0 if confidence is None else max(0.0, min(1.0, confidence))
        if self._last_measurement is not None:
            previous = self._last_measurement
            expected = (
                previous[0] + self._measurement_velocity[0],
                previous[1] + self._measurement_velocity[1],
            )
            innovation = math.hypot(measurement[0] - expected[0], measurement[1] - expected[1])
            # High-confidence tracking is allowed a wider movement envelope;
            # uncertain classification becomes more conservative immediately.
            jump_limit = self.jump_threshold * (0.65 + 0.35 * quality)
            consistent_motion = False
            if self._rejected_measurement is not None:
                prior_dx = self._rejected_measurement[0] - previous[0]
                prior_dy = self._rejected_measurement[1] - previous[1]
                next_dx = measurement[0] - self._rejected_measurement[0]
                next_dy = measurement[1] - self._rejected_measurement[1]
                consistent_motion = prior_dx * next_dx + prior_dy * next_dy > 0.0
            if confidence_enabled and innovation > jump_limit and not consistent_motion:
                self._rejected_measurement = measurement
                self._velocity = (self._velocity[0] * 0.55, self._velocity[1] * 0.55)
                return self._last_base if self._last_base is not None else previous
            self._rejected_measurement = None
            if confidence_enabled:
                span = max(1e-6, 1.0 - self.confidence_floor)
                normalized_quality = max(0.0, min(1.0, (quality - self.confidence_floor) / span))
                blend = 0.35 + 0.65 * normalized_quality
                measurement = (
                    previous[0] + (measurement[0] - previous[0]) * blend,
                    previous[1] + (measurement[1] - previous[1]) * blend,
                )

        filtered = (self.x(measurement[0], timestamp), self.y(measurement[1], timestamp))
        if self._last_base is None:
            self._last_base = filtered
            self._last_time = timestamp
            self._last_measurement = measurement
            return filtered

        assert self._last_measurement is not None
        measured_step = (
            measurement[0] - self._last_measurement[0],
            measurement[1] - self._last_measurement[1],
        )
        self._measurement_velocity = (
            self._measurement_velocity[0] * 0.45 + measured_step[0] * 0.55,
            self._measurement_velocity[1] * 0.45 + measured_step[1] * 0.55,
        )
        self._last_measurement = measurement

        dx = filtered[0] - self._last_base[0]
        dy = filtered[1] - self._last_base[1]
        distance = math.hypot(dx, dy)
        precision_active = precision_factor > 0.0
        if precision_active and distance > 0.0:
            # Graduated cap: full precision_step at factor=0, down to the
            # configured speed floor at factor=1. The dead-zone floor keeps a
            # deliberately slow approach from being discarded as hand tremor.
            effective_step = self.precision_step * (
                1.0 - (1.0 - self.precision_speed_floor) * precision_factor
            )
            effective_step = max(effective_step, self.dead_zone * 2.1)
            if distance > effective_step:
                scale = effective_step / distance
                dx *= scale
                dy *= scale
                filtered = (self._last_base[0] + dx, self._last_base[1] + dy)
                distance = effective_step
        if distance <= self.dead_zone:
            self._velocity = (self._velocity[0] * 0.45, self._velocity[1] * 0.45)
            self._last_time = timestamp
            return self._last_base

        movement = (distance - self.dead_zone) / distance
        base = (
            self._last_base[0] + dx * movement,
            self._last_base[1] + dy * movement,
        )
        # Damped velocity keeps the one-frame lookahead from responding to a
        # single noisy landmark jump while still cancelling normal filter lag.
        step_x = base[0] - self._last_base[0]
        step_y = base[1] - self._last_base[1]
        self._velocity = (
            self._velocity[0] * 0.42 + step_x * 0.58,
            self._velocity[1] * 0.42 + step_y * 0.58,
        )
        # Fade prediction out as precision_factor rises — the pointer should
        # converge on the target, not coast past it.
        lookahead = self.lookahead_frames * (1.0 - precision_factor) if precision_active else self.lookahead_frames
        predicted_dx = max(-self.prediction_cap, min(self.prediction_cap, self._velocity[0] * lookahead))
        predicted_dy = max(-self.prediction_cap, min(self.prediction_cap, self._velocity[1] * lookahead))
        self._last_base = base
        self._last_time = timestamp
        return (
            max(0.0, min(1.0, base[0] + predicted_dx)),
            max(0.0, min(1.0, base[1] + predicted_dy)),
        )

    def reanchor(self, x: float, y: float, timestamp: float) -> None:
        """Keep the current cursor position while rebasing to a new hand pose.

        A click pinch naturally changes the fingertip position. When the pinch
        releases, treating that new pose as the continuation of the old one
        makes the cursor jump. Re-anchoring turns the difference into a local
        clutch offset, so only movement *after* release moves the pointer.
        """
        target = self._last_base if self._last_base is not None else (x, y)
        self._input_offset = (x - target[0], y - target[1])
        self.x.reset()
        self.y.reset()
        self.x(target[0], timestamp)
        self.y(target[1], timestamp)
        self._last_base = target
        self._last_time = timestamp
        self._last_measurement = target
        self._measurement_velocity = (0.0, 0.0)
        self._velocity = (0.0, 0.0)
        self._rejected_measurement = None

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()
        self._last_base = None
        self._last_time = None
        self._velocity = (0.0, 0.0)
        self._last_measurement = None
        self._measurement_velocity = (0.0, 0.0)
        self._rejected_measurement = None
        self._input_offset = (0.0, 0.0)
