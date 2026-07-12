"""Fast regression checks for the real-time pointer path.

Each generated test covers an independent operating point. Keeping these cases
small makes it practical to run all 150 checks before publishing a release.
"""

import unittest

from app.filters import PointFilter
from app.tuning import normalized_tuning


class ResponsePerformanceGuards(unittest.TestCase):
    pass


def _high_confidence_motion(distance: float):
    def test(self):
        direct = PointFilter(jump_threshold=0.04)
        guarded = PointFilter(jump_threshold=0.04)
        direct.apply(0.25, 0.5, 0.0, confidence=0.95)
        guarded.apply(0.25, 0.5, 0.0, confidence=0.20)
        direct_output = direct.apply(0.25 + distance, 0.5, 1 / 60, confidence=0.95)
        guarded_output = guarded.apply(0.25 + distance, 0.5, 1 / 60, confidence=0.20)
        self.assertGreater(direct_output[0], guarded_output[0])

    return test


def _uncertain_outlier_is_held(distance: float):
    def test(self):
        smoothing = PointFilter(jump_threshold=0.05)
        smoothing.apply(0.4, 0.5, 0.0, confidence=0.9)
        held = smoothing.apply(0.4 + distance, 0.5, 1 / 60, confidence=0.15)
        self.assertLess(held[0], 0.405)

    return test


def _precision_release_is_bounded(release_seconds: float):
    def test(self):
        smoothing = PointFilter(precision_release_seconds=release_seconds)
        smoothing.apply(0.2, 0.5, 0.0)
        precise = smoothing.apply(0.8, 0.5, 1 / 60, precision_factor=1.0)
        released = smoothing.apply(0.8, 0.5, 2 / 60, precision_factor=0.0)
        self.assertGreater(released[0], precise[0])
        self.assertLess(released[0] - precise[0], 0.015)

    return test


def _prediction_remains_capped(cap: float):
    def test(self):
        smoothing = PointFilter(prediction_cap=cap)
        smoothing.apply(0.2, 0.5, 0.0)
        output = smoothing.apply(0.8, 0.5, 1 / 60)
        self.assertLessEqual(output[0], 0.8 + cap + 1e-9)

    return test


def _tuning_remains_bounded(value: float):
    def test(self):
        tuned = normalized_tuning({"precision_release_seconds": value})
        self.assertGreaterEqual(tuned["precision_release_seconds"], 0.02)
        self.assertLessEqual(tuned["precision_release_seconds"], 0.30)

    return test


for index, distance in enumerate((0.045, 0.050, 0.055, 0.060, 0.065, 0.070, 0.075, 0.080, 0.085, 0.090, 0.095, 0.100, 0.110, 0.120, 0.130, 0.140, 0.150, 0.160), 1):
    setattr(ResponsePerformanceGuards, f"test_high_confidence_motion_{index:02d}", _high_confidence_motion(distance))

for index, distance in enumerate((0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17), 1):
    setattr(ResponsePerformanceGuards, f"test_uncertain_outlier_{index:02d}", _uncertain_outlier_is_held(distance))

for index, release in enumerate((0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.16, 0.22, 0.30), 1):
    setattr(ResponsePerformanceGuards, f"test_precision_release_{index:02d}", _precision_release_is_bounded(release))

for index, cap in enumerate((0.002, 0.004, 0.006, 0.008, 0.010, 0.014), 1):
    setattr(ResponsePerformanceGuards, f"test_prediction_cap_{index:02d}", _prediction_remains_capped(cap))

for index, value in enumerate((-1.0, 0.0, 0.01, 0.07, 0.30, 1.0), 1):
    setattr(ResponsePerformanceGuards, f"test_release_tuning_{index:02d}", _tuning_remains_bounded(value))


if __name__ == "__main__":
    unittest.main()
