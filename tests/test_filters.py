import math
import unittest

from app.filters import OneEuroFilter, PointFilter


class OneEuroFilterTests(unittest.TestCase):
    def test_constant_input_stays_constant(self):
        smoothing = OneEuroFilter()
        values = [smoothing(0.4, i / 30) for i in range(30)]
        self.assertTrue(all(abs(value - 0.4) < 1e-9 for value in values))

    def test_reset_accepts_new_position_immediately(self):
        smoothing = OneEuroFilter()
        smoothing(0.1, 0.0)
        smoothing(0.1, 0.1)
        smoothing.reset()
        self.assertEqual(smoothing(0.9, 1.0), 0.9)


class PointFilterTests(unittest.TestCase):
    def test_micro_tremor_is_held_at_the_last_output(self):
        smoothing = PointFilter()
        first = smoothing.apply(0.5, 0.5, 0.0)
        outputs = [
            smoothing.apply(0.5 + offset, 0.5 - offset, index / 60)
            for index, offset in enumerate((0.0005, -0.0007, 0.0009, -0.0004), start=1)
        ]
        self.assertTrue(all(output == first for output in outputs))

    def test_intentional_motion_passes_through(self):
        smoothing = PointFilter()
        smoothing.apply(0.2, 0.2, 0.0)
        output = None
        for index in range(1, 9):
            output = smoothing.apply(0.2 + index * 0.05, 0.2, index / 60)
        self.assertGreater(output[0], 0.45)

    def test_one_frame_lookahead_reduces_filter_lag_during_motion(self):
        smoothing = PointFilter()
        smoothing.apply(0.2, 0.5, 0.0)
        first = smoothing.apply(0.3, 0.5, 1 / 60)
        second = smoothing.apply(0.4, 0.5, 2 / 60)
        self.assertGreater(second[0] - first[0], 0.0)
        self.assertLessEqual(second[0], 1.0)

    def test_lookahead_does_not_move_a_stationary_cursor(self):
        smoothing = PointFilter()
        first = smoothing.apply(0.5, 0.5, 0.0)
        held = smoothing.apply(0.5, 0.5, 1 / 60)
        self.assertEqual(first, held)

    def test_stationary_noise_damps_prediction_velocity(self):
        smoothing = PointFilter()
        smoothing.apply(0.3, 0.5, 0.0)
        moving = smoothing.apply(0.4, 0.5, 1 / 60)
        settled = smoothing.apply(0.4, 0.5, 2 / 60)
        self.assertLessEqual(abs(settled[0] - 0.4), abs(moving[0] - 0.4))

    def test_precision_mode_limits_approach_speed_and_disables_prediction(self):
        smoothing = PointFilter()
        smoothing.apply(0.2, 0.5, 0.0)
        precise = smoothing.apply(0.8, 0.5, 1 / 60, precision_factor=1.0)
        # Full precision keeps a visible movement budget above the tremor
        # dead zone instead of stalling at the target.
        self.assertLessEqual(precise[0] - 0.2, 0.012)
        self.assertGreater(precise[0], 0.2)

    def test_full_precision_step_is_not_swallowed_by_the_dead_zone(self):
        smoothing = PointFilter(dead_zone=0.0031, precision_step=0.006, precision_speed_floor=0.35)
        smoothing.apply(0.2, 0.5, 0.0)
        precise = smoothing.apply(0.8, 0.5, 1 / 60, precision_factor=1.0)
        self.assertGreater(precise[0] - 0.2, 0.003)

    def test_graduated_precision_is_faster_than_full_precision(self):
        full = PointFilter()
        full.apply(0.2, 0.5, 0.0)
        full_out = full.apply(0.8, 0.5, 1 / 60, precision_factor=1.0)

        half = PointFilter()
        half.apply(0.2, 0.5, 0.0)
        half_out = half.apply(0.8, 0.5, 1 / 60, precision_factor=0.5)

        self.assertGreater(half_out[0], full_out[0])

    def test_point_filter_reset_accepts_new_position(self):
        smoothing = PointFilter()
        smoothing.apply(0.1, 0.1, 0.0)
        smoothing.apply(0.11, 0.1, 0.1)
        smoothing.reset()
        self.assertEqual(smoothing.apply(0.9, 0.8, 1.0), (0.9, 0.8))

    def test_confidence_aware_filter_rejects_a_single_large_jump(self):
        smoothing = PointFilter(jump_threshold=0.06)
        smoothing.apply(0.4, 0.4, 0.0, confidence=0.8)
        held = smoothing.apply(0.85, 0.85, 1 / 60, confidence=0.55)
        self.assertLess(math.hypot(held[0] - 0.4, held[1] - 0.4), 0.01)
        recovered = smoothing.apply(0.405, 0.4, 2 / 60, confidence=0.8)
        self.assertLess(math.hypot(recovered[0] - 0.4, recovered[1] - 0.4), 0.03)

    def test_consistent_fast_motion_is_accepted_after_jump_confirmation(self):
        smoothing = PointFilter(jump_threshold=0.06)
        smoothing.apply(0.2, 0.5, 0.0, confidence=0.9)
        rejected = smoothing.apply(0.45, 0.5, 1 / 60, confidence=0.9)
        accepted = smoothing.apply(0.7, 0.5, 2 / 60, confidence=0.9)
        self.assertLess(rejected[0], 0.23)
        self.assertGreater(accepted[0], rejected[0] + 0.02)

    def test_low_confidence_measurements_move_more_cautiously(self):
        high_confidence = PointFilter(jump_threshold=0.2)
        low_confidence = PointFilter(jump_threshold=0.2)
        high_confidence.apply(0.4, 0.5, 0.0, confidence=1.0)
        low_confidence.apply(0.4, 0.5, 0.0, confidence=1.0)
        high = high_confidence.apply(0.46, 0.5, 1 / 60, confidence=1.0)
        low = low_confidence.apply(0.46, 0.5, 1 / 60, confidence=0.45)
        self.assertGreater(high[0], low[0])


if __name__ == "__main__":
    unittest.main()
