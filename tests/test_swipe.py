import unittest

from app.gestures import Landmark
from app.swipe import SwipeState, ThreeFingerSwipeDetector
from app.tuning import normalized_tuning


def three_finger_pose():
    coordinates = [
        (0.50, 0.90),
        (0.39, 0.78), (0.32, 0.67), (0.25, 0.59), (0.45, 0.79),
        (0.40, 0.66), (0.39, 0.49), (0.38, 0.35), (0.37, 0.20),
        (0.49, 0.63), (0.49, 0.44), (0.49, 0.28), (0.49, 0.12),
        (0.58, 0.66), (0.60, 0.49), (0.61, 0.35), (0.62, 0.21),
        (0.66, 0.71), (0.66, 0.74), (0.67, 0.77), (0.66, 0.80),
    ]
    return tuple(Landmark(x, y) for x, y in coordinates)


def move_three_fingers(points, dx=0.0, dy=0.0):
    moved = list(points)
    for index in range(len(moved)):
        point = moved[index]
        moved[index] = Landmark(point.x + dx, point.y + dy, point.z)
    return tuple(moved)


def with_pose_dropout(points):
    moved = list(points)
    moved[20] = Landmark(0.66, 0.48)
    return tuple(moved)


class SwipeDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = ThreeFingerSwipeDetector()
        self.tuning = normalized_tuning({"swipe_enabled": 1.0})
        self.points = three_finger_pose()

    def _frame(self, timestamp, dx=0.0, dy=0.0, pinch_active=False):
        return self.detector.process(
            move_three_fingers(self.points, dx, dy),
            timestamp,
            pinch_active=pinch_active,
            tuning=self.tuning,
        )

    def _arm_and_track(self, dx=0.07, dy=0.0):
        self._frame(0.00)
        self._frame(0.03, dx=dx * 0.15, dy=dy * 0.15)
        self._frame(0.06, dx=dx * 0.30, dy=dy * 0.30)
        return self._frame(0.09, dx=dx, dy=dy)

    def test_right_and_left_swipes_switch_applications(self):
        self.assertEqual(self._arm_and_track().state, SwipeState.TRACKING)
        right = self._frame(0.12, dx=0.15)
        self.assertEqual(right.direction, "right")

        self.detector.reset()
        self.assertEqual(self._arm_and_track(dx=-0.07).state, SwipeState.TRACKING)
        left = self._frame(0.12, dx=-0.15)
        self.assertEqual(left.direction, "left")

    def test_up_and_down_swipes_have_distinct_actions(self):
        self.assertEqual(self._arm_and_track(dx=0.0, dy=-0.07).state, SwipeState.TRACKING)
        up = self._frame(0.12, dy=-0.15)
        self.assertEqual(up.direction, "up")

        self.detector.reset()
        self.assertEqual(self._arm_and_track(dx=0.0, dy=0.07).state, SwipeState.TRACKING)
        down = self._frame(0.12, dy=0.15)
        self.assertEqual(down.direction, "down")

    def test_vertical_swipe_wins_when_vertical_motion_has_horizontal_drift(self):
        self._frame(0.00)
        self._frame(0.03, dx=0.008, dy=-0.012)
        self._frame(0.06, dx=0.018, dy=-0.030)
        tracking = self._frame(0.09, dx=0.040, dy=-0.070)
        self.assertEqual(tracking.state, SwipeState.TRACKING)

        fired = self._frame(0.12, dx=0.075, dy=-0.150)
        self.assertEqual(fired.direction, "up")

    def test_one_frame_pose_dropout_does_not_cancel_vertical_swipe(self):
        self.assertEqual(self._arm_and_track(dx=0.0, dy=-0.07).state, SwipeState.TRACKING)
        dropped = self.detector.process(
            with_pose_dropout(move_three_fingers(self.points, dy=-0.09)),
            0.10,
            pinch_active=False,
            tuning=self.tuning,
        )
        self.assertEqual(dropped.state, SwipeState.TRACKING)

        fired = self._frame(0.13, dy=-0.16)
        self.assertEqual(fired.direction, "up")

    def test_pinch_and_diagonal_motion_cancel_the_gesture(self):
        self._frame(0.00)
        cancelled = self._frame(0.03, pinch_active=True)
        self.assertEqual(cancelled.state, SwipeState.IDLE)
        self._frame(0.10)
        diagonal = self._frame(0.13, dx=0.08, dy=0.10)
        self.assertEqual(diagonal.state, SwipeState.ARMED)

    def test_cooldown_prevents_repeat_fire(self):
        self._arm_and_track()
        self._frame(0.12, dx=0.15)
        cooldown = self._frame(0.20, dx=0.30)
        self.assertEqual(cooldown.state, SwipeState.COOLDOWN)


if __name__ == "__main__":
    unittest.main()
