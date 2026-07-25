import unittest

from app.gestures import GestureEngine
from app.tuning import DEFAULT_TUNING, DEVELOPER_PARAMETERS, normalized_tuning


class TuningTests(unittest.TestCase):
    def test_parameter_defaults_are_complete_and_valid(self):
        self.assertEqual(set(DEFAULT_TUNING), {parameter.key for parameter in DEVELOPER_PARAMETERS})
        for parameter in DEVELOPER_PARAMETERS:
            self.assertLessEqual(parameter.minimum, parameter.default)
            self.assertLessEqual(parameter.default, parameter.maximum)
            self.assertGreater(parameter.step, 0)

    def test_tuning_values_are_bounded(self):
        tuned = normalized_tuning({"pointer_dead_zone": 9, "pinch_contact": -1, "unknown": 2})
        parameters = {parameter.key: parameter for parameter in DEVELOPER_PARAMETERS}
        self.assertEqual(tuned["pointer_dead_zone"], parameters["pointer_dead_zone"].maximum)
        self.assertEqual(tuned["pinch_contact"], parameters["pinch_contact"].minimum)
        self.assertNotIn("unknown", tuned)

    def test_engine_applies_live_filter_tuning(self):
        engine = GestureEngine()
        tuning = normalized_tuning({
            "pointer_dead_zone": 0.01,
            "prediction_frames": 0.4,
            "prediction_reversal_guard": 0.0,
            "precision_step": 0.008,
            "precision_release_seconds": 0.12,
        })
        engine.configure(1.0, (0, 0, 1920, 1080), tuning=tuning)
        self.assertEqual(engine._filter.dead_zone, 0.01)
        self.assertEqual(engine._filter.lookahead_frames, 0.4)
        self.assertFalse(engine._filter.prediction_reversal_guard)
        self.assertEqual(engine._filter.precision_step, 0.008)
        self.assertEqual(engine._filter.precision_release_seconds, 0.12)

    def test_precision_speed_cap_has_a_safe_minimum(self):
        tuned = normalized_tuning({"precision_step": 0.001})
        self.assertEqual(tuned["precision_step"], 0.006)

    def test_relational_repairs_match_developer_control_precision(self):
        tuned = normalized_tuning(
            {
                "pinch_scroll_activation_distance": 0.018,
                "pinch_scroll_dead_zone": 0.020,
            }
        )
        self.assertEqual(tuned["pinch_scroll_dead_zone"], 0.008)

    def test_coupled_tuning_values_keep_safe_relationships(self):
        tuned = normalized_tuning({
            "inference_active_fps": 20,
            "inference_idle_fps": 30,
            "pinch_deep_contact": 0.45,
            "pinch_contact": 0.30,
            "pinch_confirm": 0.50,
            "pinch_hold_release": 0.25,
            "pinch_clear_release": 0.35,
            "pinch_scroll_activation_distance": 0.02,
            "pinch_scroll_dead_zone": 0.02,
            "pinch_scroll_step": 0.01,
            "pinch_scroll_arm_delay": 0.18,
            "pinch_scroll_classify_timeout": 0.15,
        })
        self.assertLessEqual(tuned["inference_idle_fps"], tuned["inference_active_fps"])
        self.assertLessEqual(tuned["pinch_deep_contact"], tuned["pinch_confirm"])
        self.assertLessEqual(tuned["pinch_confirm"], tuned["pinch_contact"])
        self.assertLessEqual(tuned["pinch_contact"], tuned["pinch_hold_release"])
        self.assertLessEqual(tuned["pinch_hold_release"], tuned["pinch_clear_release"])
        self.assertLessEqual(
            tuned["pinch_scroll_dead_zone"],
            tuned["pinch_scroll_activation_distance"] * 0.45,
        )
        self.assertGreaterEqual(
            tuned["pinch_scroll_classify_timeout"],
            tuned["pinch_scroll_arm_delay"] + 0.05,
        )
        self.assertEqual(tuned["pinch_scroll_step"], 0.01)


if __name__ == "__main__":
    unittest.main()
