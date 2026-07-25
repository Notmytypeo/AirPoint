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


def natural_three_finger_pose():
    """A less idealized pose with close fingers and a relaxed thumb."""
    coordinates = [
        (0.50, 0.90),
        (0.39, 0.78), (0.32, 0.67), (0.27, 0.61), (0.23, 0.67),
        (0.40, 0.66), (0.39, 0.50), (0.41, 0.37), (0.44, 0.25),
        (0.49, 0.63), (0.49, 0.45), (0.50, 0.30), (0.51, 0.17),
        (0.58, 0.66), (0.59, 0.50), (0.59, 0.37), (0.58, 0.25),
        (0.66, 0.71), (0.66, 0.74), (0.67, 0.77), (0.66, 0.80),
    ]
    return tuple(Landmark(x, y) for x, y in coordinates)


def move_three_fingers(points, dx=0.0, dy=0.0):
    moved = list(points)
    for index in range(len(moved)):
        point = moved[index]
        moved[index] = Landmark(point.x + dx, point.y + dy, point.z)
    return tuple(moved)


def scale_hand(points, factor):
    wrist = points[0]
    return tuple(
        Landmark(
            wrist.x + (point.x - wrist.x) * factor,
            wrist.y + (point.y - wrist.y) * factor,
            point.z * factor,
        )
        for point in points
    )


def open_little_finger(points):
    opened = list(points)
    mcp = points[17]
    opened[18] = Landmark(mcp.x, mcp.y - 0.14)
    opened[19] = Landmark(mcp.x + 0.01, mcp.y - 0.28)
    opened[20] = Landmark(mcp.x + 0.02, mcp.y - 0.42)
    return tuple(opened)


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

    def test_natural_close_finger_pose_fires_in_all_directions(self):
        self.points = natural_three_finger_pose()
        for dx, dy, expected in (
            (0.15, 0.0, "right"),
            (-0.15, 0.0, "left"),
            (0.0, -0.15, "up"),
            (0.0, 0.15, "down"),
        ):
            with self.subTest(direction=expected):
                self.detector.reset()
                self.assertEqual(
                    self._arm_and_track(dx=dx * 0.47, dy=dy * 0.47).state,
                    SwipeState.TRACKING,
                )
                result = self._frame(0.12, dx=dx, dy=dy)
                self.assertEqual(result.direction, expected)

    def test_open_palm_is_not_accepted_as_three_finger_pose(self):
        self.assertFalse(
            self.detector._is_three_finger_pose(
                open_little_finger(self.points),
                self.tuning,
            )
        )

    def test_stationary_pose_remains_armed_until_motion_starts(self):
        for frame in range(15):
            result = self._frame(frame * 0.03)
        self.assertEqual(result.state, SwipeState.ARMED)
        for timestamp, dx in ((0.45, 0.02), (0.48, 0.07), (0.51, 0.15), (0.54, 0.18)):
            result = self._frame(timestamp, dx=dx)
        self.assertEqual(result.direction, "right")

    def test_vertical_swipe_uses_the_larger_axis_when_both_cross_arm_distance(self):
        self._frame(0.00)
        self._frame(0.03, dx=0.01, dy=-0.02)
        self._frame(0.06, dx=0.02, dy=-0.04)
        tracking = self._frame(0.09, dx=0.065, dy=-0.08)
        fired = self._frame(0.12, dx=0.07, dy=-0.15)
        self.assertEqual(tracking.state, SwipeState.TRACKING)
        self.assertEqual(fired.direction, "up")

    def test_scale_adaptation_keeps_a_farther_hand_swipe_usable(self):
        far_points = scale_hand(self.points, 0.5)

        def run(adaptive):
            detector = ThreeFingerSwipeDetector()
            tuning = normalized_tuning({
                "swipe_enabled": 1.0,
                "swipe_scale_adaptation": adaptive,
            })
            result = None
            frames = (
                (0.00, 0.0),
                (0.03, 0.007),
                (0.06, 0.014),
                (0.09, 0.045),
                (0.12, 0.075),
            )
            for timestamp, dx in frames:
                result = detector.process(
                    move_three_fingers(far_points, dx=dx),
                    timestamp,
                    pinch_active=False,
                    tuning=tuning,
                )
            return result

        self.assertEqual(run(1.0).direction, "right")
        self.assertEqual(run(0.0).direction, "")

    def test_swipe_timing_is_consistent_at_15_30_and_60_fps(self):
        for fps in (15, 30, 60):
            with self.subTest(fps=fps):
                detector = ThreeFingerSwipeDetector()
                frame_count = round(0.20 * fps)
                direction = ""
                for frame in range(frame_count + 1):
                    progress = frame / frame_count
                    result = detector.process(
                        move_three_fingers(self.points, dx=0.15 * progress),
                        frame / fps,
                        pinch_active=False,
                        tuning=self.tuning,
                    )
                    direction = result.direction or direction
                self.assertEqual(direction, "right")

    def test_robust_trajectory_rejects_one_large_landmark_spike(self):
        for timestamp, dx in ((0.00, 0.0), (0.03, 0.005), (0.06, 0.010), (0.09, 0.015)):
            self._frame(timestamp, dx=dx)
        spike = self._frame(0.12, dx=0.20)
        self.assertNotEqual(spike.state, SwipeState.FIRED)
        self.assertEqual(spike.direction, "")

    def test_one_pose_dropout_does_not_cancel_an_active_swipe(self):
        self.assertEqual(self._arm_and_track().state, SwipeState.TRACKING)
        dropout = self.detector.process(
            open_little_finger(move_three_fingers(self.points, dx=0.09)),
            0.10,
            pinch_active=False,
            tuning=self.tuning,
        )
        fired = self._frame(0.12, dx=0.15)
        self.assertEqual(dropout.state, SwipeState.TRACKING)
        self.assertEqual(fired.direction, "right")

    def test_pose_grace_is_bounded_to_one_frame_by_default(self):
        self.assertEqual(self._arm_and_track().state, SwipeState.TRACKING)
        invalid = open_little_finger(move_three_fingers(self.points, dx=0.09))
        first = self.detector.process(invalid, 0.10, pinch_active=False, tuning=self.tuning)
        second = self.detector.process(invalid, 0.11, pinch_active=False, tuning=self.tuning)
        self.assertEqual(first.state, SwipeState.TRACKING)
        self.assertEqual(second.state, SwipeState.IDLE)

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
