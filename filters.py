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
    def __init__(self, dead_zone: float = 0.0022) -> None:
        # Lower cutoff stabilizes a resting hand; higher beta quickly opens the
        # filter during intentional motion. The radial dead zone removes the
        # final few pixels of physiological hand tremor without axis bias.
        self.x = OneEuroFilter(min_cutoff=0.85, beta=1.0)
        self.y = OneEuroFilter(min_cutoff=0.85, beta=1.0)
        self.dead_zone = dead_zone
        self._last_output: tuple[float, float] | None = None

    def apply(self, x: float, y: float, timestamp: float) -> tuple[float, float]:
        filtered = (self.x(x, timestamp), self.y(y, timestamp))
        if self._last_output is None:
            self._last_output = filtered
            return filtered

        dx = filtered[0] - self._last_output[0]
        dy = filtered[1] - self._last_output[1]
        distance = math.hypot(dx, dy)
        if distance <= self.dead_zone:
            return self._last_output

        movement = (distance - self.dead_zone) / distance
        output = (
            self._last_output[0] + dx * movement,
            self._last_output[1] + dy * movement,
        )
        self._last_output = output
        return output

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()
        self._last_output = None
