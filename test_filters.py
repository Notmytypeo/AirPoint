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

    def test_point_filter_reset_accepts_new_position(self):
        smoothing = PointFilter()
        smoothing.apply(0.1, 0.1, 0.0)
        smoothing.apply(0.11, 0.1, 0.1)
        smoothing.reset()
        self.assertEqual(smoothing.apply(0.9, 0.8, 1.0), (0.9, 0.8))


if __name__ == "__main__":
    unittest.main()
