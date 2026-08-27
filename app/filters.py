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
        precision_release_seconds: float = 0.07,
        confidence_floor: float = 0.25,
        jump_threshold: float = 0.095,
        prediction_reversal_guard: bool = True,
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
        self.precision_release_seconds = max(0.02, min(0.30, precision_release_seconds))
        self.confidence_floor = max(0.0, min(0.95, confidence_floor))
        self.jump_threshold = max(0.01, jump_threshold)
        self.prediction_reversal_guard = bool(prediction_reversal_guard)
        self._last_base: tuple[float, float] | None = None
        self._last_output: tuple[float, float] | None = None
        self._last_time: float | None = None
        self._velocity = (0.0, 0.0)
        self._last_measurement: tuple[float, float] | None = None
        self._last_measurement_time: float | None = None
        self._measurement_velocity = (0.0, 0.0)
        self._rejected_measurement: tuple[float, float] | None = None
        self._precision_memory = 0.0
        self._precision_time: float | None = None

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
        precision_release_seconds: float,
        confidence_floor: float,
        jump_threshold: float,
        prediction_reversal_guard: bool,
    ) -> None:
        self.dead_zone = max(0.0, dead_zone)
        self.lookahead_frames = max(0.0, min(1.0, lookahead_frames))
        self.x.min_cutoff = self.y.min_cutoff = max(0.01, min_cutoff)
        self.x.beta = self.y.beta = max(0.0, beta)
        self.prediction_cap = max(0.0, prediction_cap)
        self.precision_step = max(0.0, precision_step)
        self.precision_speed_floor = max(0.0, min(1.0, precision_speed_floor))
        self.precision_release_seconds = max(0.02, min(0.30, precision_release_seconds))
        self.confidence_floor = max(0.0, min(0.95, confidence_floor))
        self.jump_threshold = max(0.01, jump_threshold)
        self.prediction_reversal_guard = bool(prediction_reversal_guard)

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
        measurement = (x, y)
        confidence_enabled = confidence is not None
        quality = 1.0 if confidence is None else max(0.0, min(1.0, confidence))
        if self._last_measurement is not None:
            previous = self._last_measurement
            measurement_dt = min(
                max(
                    timestamp - self._last_measurement_time
                    if self._last_measurement_time is not None
                    else 1.0 / 60.0,
                    1.0 / 240.0,
                ),
                0.2,
            )
            expected = (
                previous[0] + self._measurement_velocity[0] * measurement_dt,
                previous[1] + self._measurement_velocity[1] * measurement_dt,
            )
            innovation = math.hypot(measurement[0] - expected[0], measurement[1] - expected[1])
            # Only uncertain landmark samples need jump rejection. Handedness
            # scores from a clear, well-lit hand are routinely above 0.7, so
            # treating them as direct measurements avoids an added frame of lag.
            jump_limit = self.jump_threshold * (0.65 + 0.35 * quality)
            consistent_motion = False
            if self._rejected_measurement is not None:
                prior_dx = self._rejected_measurement[0] - previous[0]
                prior_dy = self._rejected_measurement[1] - previous[1]
                next_dx = measurement[0] - self._rejected_measurement[0]
                next_dy = measurement[1] - self._rejected_measurement[1]
                consistent_motion = prior_dx * next_dx + prior_dy * next_dy > 0.0
            uncertain_sample = quality < 0.72
            if confidence_enabled and uncertain_sample and innovation > jump_limit and not consistent_motion:
                self._rejected_measurement = measurement
                self._velocity = (self._velocity[0] * 0.55, self._velocity[1] * 0.55)
                # Prediction is part of the position already emitted to the
                # operating system. Holding the internal, unpredicted base
                # would make a rejected observation pull the cursor backward.
                if self._last_output is not None:
                    return self._last_output
                return self._last_base if self._last_base is not None else previous
            self._rejected_measurement = None
            if confidence_enabled:
                span = max(1e-6, 1.0 - self.confidence_floor)
                normalized_quality = max(0.0, min(1.0, (quality - self.confidence_floor) / span))
                # Retain responsiveness for usable low-confidence samples;
                # the jump gate above handles the genuinely suspicious ones.
                blend = 0.70 + 0.30 * normalized_quality
                measurement = (
                    previous[0] + (measurement[0] - previous[0]) * blend,
                    previous[1] + (measurement[1] - previous[1]) * blend,
                )

        filtered = (self.x(measurement[0], timestamp), self.y(measurement[1], timestamp))
        if self._last_base is None:
            self._last_base = filtered
            self._last_output = filtered
            self._last_time = timestamp
            self._last_measurement = measurement
            self._last_measurement_time = timestamp
            return filtered

        assert self._last_measurement is not None
        measurement_dt = min(
            max(
                timestamp - self._last_measurement_time
                if self._last_measurement_time is not None
                else 1.0 / 60.0,
                1.0 / 240.0,
            ),
            0.2,
        )
        measured_step = (
            measurement[0] - self._last_measurement[0],
            measurement[1] - self._last_measurement[1],
        )
        instantaneous_velocity = (
            measured_step[0] / measurement_dt,
            measured_step[1] / measurement_dt,
        )
        # Match the previous 0.55 update weight at 60 FPS while keeping the
        # velocity estimate stable when frames are early, late, or dropped.
        velocity_alpha = 1.0 - 0.45 ** (measurement_dt * 60.0)
        self._measurement_velocity = (
            self._measurement_velocity[0] * (1.0 - velocity_alpha)
            + instantaneous_velocity[0] * velocity_alpha,
            self._measurement_velocity[1] * (1.0 - velocity_alpha)
            + instantaneous_velocity[1] * velocity_alpha,
        )
        self._last_measurement = measurement
        self._last_measurement_time = timestamp

        dx = filtered[0] - self._last_base[0]
        dy = filtered[1] - self._last_base[1]
        distance = math.hypot(dx, dy)
        # Fade precision mode out instead of removing the speed cap in one
        # frame. This prevents a separated fingertip from making the cursor
        # abruptly catch up after the controlled final approach.
        elapsed = 0.0 if self._precision_time is None else max(0.0, min(0.05, timestamp - self._precision_time))
        self._precision_time = timestamp
        if precision_factor >= self._precision_memory:
            self._precision_memory = precision_factor
        else:
            self._precision_memory = max(
                precision_factor,
                self._precision_memory - elapsed / self.precision_release_seconds,
            )
        precision_factor = self._precision_memory
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
            self._last_output = self._last_base
            return self._last_output

        movement = (distance - self.dead_zone) / distance
        base = (
            self._last_base[0] + dx * movement,
            self._last_base[1] + dy * movement,
        )
        # Damped velocity keeps the one-frame lookahead from responding to a
        # single noisy landmark jump while still cancelling normal filter lag.
        step_x = base[0] - self._last_base[0]
        step_y = base[1] - self._last_base[1]
        previous_velocity = self._velocity
        self._velocity = (
            self._velocity[0] * 0.42 + step_x * 0.58,
            self._velocity[1] * 0.42 + step_y * 0.58,
        )
        # Fade prediction out as precision_factor rises — the pointer should
        # converge on the target, not coast past it.
        lookahead = self.lookahead_frames * (1.0 - precision_factor) if precision_active else self.lookahead_frames
        if self.prediction_reversal_guard:
            previous_speed = math.hypot(*previous_velocity)
            current_speed = math.hypot(step_x, step_y)
            if previous_speed <= 1e-6 or current_speed <= 1e-6:
                lookahead = 0.0
            else:
                alignment = (
                    previous_velocity[0] * step_x + previous_velocity[1] * step_y
                ) / (previous_speed * current_speed)
                # Prediction is useful for coherent motion, but becomes
                # overshoot when the hand stops or reverses direction.
                speed_consistency = min(1.0, current_speed / previous_speed)
                lookahead *= max(0.0, min(1.0, alignment)) * speed_consistency
        predicted_dx = max(-self.prediction_cap, min(self.prediction_cap, self._velocity[0] * lookahead))
        predicted_dy = max(-self.prediction_cap, min(self.prediction_cap, self._velocity[1] * lookahead))
        self._last_base = base
        self._last_time = timestamp
        self._last_output = (
            max(0.0, min(1.0, base[0] + predicted_dx)),
            max(0.0, min(1.0, base[1] + predicted_dy)),
        )
        return self._last_output

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()
        self._last_base = None
        self._last_output = None
        self._last_time = None
        self._velocity = (0.0, 0.0)
        self._last_measurement = None
        self._last_measurement_time = None
        self._measurement_velocity = (0.0, 0.0)
        self._rejected_measurement = None
        self._precision_memory = 0.0
        self._precision_time = None
