import unittest

from app.gestures import GestureEngine, HandObservation, Landmark


def open_hand(handedness="Right"):
    # Synthetic straight fingers, with a separated thumb. Geometry is sufficient
    # for deterministic state-machine tests and is not intended as camera data.
    coordinates = [
        (0.50, 0.90),
        (0.39, 0.78), (0.32, 0.67), (0.25, 0.59), (0.17, 0.53),
        (0.40, 0.66), (0.39, 0.49), (0.38, 0.35), (0.37, 0.20),
        (0.49, 0.63), (0.49, 0.44), (0.49, 0.28), (0.49, 0.12),
        (0.58, 0.66), (0.60, 0.49), (0.61, 0.35), (0.62, 0.21),
        (0.66, 0.71), (0.70, 0.57), (0.73, 0.46), (0.75, 0.35),
    ]
    return HandObservation(handedness, tuple(Landmark(x, y) for x, y in coordinates))


def with_point(hand, index, x, y):
    points = list(hand.landmarks)
    points[index] = Landmark(x, y)
    return HandObservation(hand.handedness, tuple(points))


def shift_hand(hand, dx=0.0, dy=0.0):
    return HandObservation(
        hand.handedness,
        tuple(Landmark(point.x + dx, point.y + dy, point.z) for point in hand.landmarks),
    )


def index_pinched_hand(handedness, dx=0.0, dy=0.0):
    hand = shift_hand(open_hand(handedness), dx, dy)
    thumb = hand.landmarks[4]
    return with_point(hand, 8, thumb.x + 0.01, thumb.y)


def ring_pinched_hand(handedness="Right"):
    hand = open_hand(handedness)
    thumb = hand.landmarks[4]
    return with_point(hand, 16, thumb.x + 0.01, thumb.y)


def with_confidence(hand, confidence):
    return HandObservation(
        hand.handedness,
        hand.landmarks,
        hand.world_landmarks,
        confidence,
    )


def move_pinching_fingertips(hand, dy):
    points = list(hand.landmarks)
    points[4] = Landmark(points[4].x, points[4].y + dy, points[4].z)
    points[8] = Landmark(points[8].x, points[8].y + dy, points[8].z)
    return HandObservation(hand.handedness, tuple(points))


def index_pinched_with_free_fingers_folded(handedness, dx=0.0):
    hand = shift_hand(fist(handedness), dx=dx)
    thumb = hand.landmarks[4]
    return with_point(hand, 8, thumb.x + 0.01, thumb.y)


def index_released_with_free_fingers_folded(handedness, dx=0.0):
    closed = shift_hand(fist(handedness), dx=dx)
    opened = shift_hand(open_hand(handedness), dx=dx)
    points = list(closed.landmarks)
    points[5:9] = opened.landmarks[5:9]
    return HandObservation(handedness, tuple(points))


def middle_pinched_with_other_fingers_folded(handedness, dx=0.0):
    hand = shift_hand(fist(handedness), dx=dx)
    thumb = hand.landmarks[4]
    return with_point(hand, 12, thumb.x + 0.01, thumb.y)


def index_pinched_with_one_free_finger_folded(handedness, dx=0.0):
    pinched = index_pinched_hand(handedness, dx=dx)
    folded = shift_hand(fist(handedness), dx=dx)
    points = list(pinched.landmarks)
    points[17:21] = folded.landmarks[17:21]
    return HandObservation(handedness, tuple(points))


def index_pinched_with_only_one_free_finger(handedness, dx=0.0):
    pinched = index_pinched_hand(handedness, dx=dx)
    folded = index_pinched_with_free_fingers_folded(handedness, dx=dx)
    points = list(folded.landmarks)
    points[9:13] = pinched.landmarks[9:13]
    return HandObservation(handedness, tuple(points))


def fist_with_index_touching_thumb(handedness="Left"):
    hand = fist(handedness)
    thumb = hand.landmarks[4]
    return with_point(hand, 8, thumb.x + 0.01, thumb.y)


def fist_with_one_finger_tracking_open(handedness="Left"):
    closed = fist(handedness)
    opened = open_hand(handedness)
    points = list(closed.landmarks)
    points[9:13] = opened.landmarks[9:13]
    return HandObservation(handedness, tuple(points))


def fist(handedness="Right"):
    hand = open_hand(handedness)
    points = list(hand.landmarks)
    for pip, dip, tip in ((6, 7, 8), (10, 11, 12), (14, 15, 16), (18, 19, 20)):
        base = points[pip - 1]
        points[pip] = Landmark(base.x, base.y - 0.04)
        points[dip] = Landmark(base.x + 0.035, base.y)
        points[tip] = Landmark(base.x + 0.02, base.y + 0.08)
    return HandObservation(handedness, tuple(points))


def two_finger_hand(handedness="Right"):
    opened = open_hand(handedness)
    folded = fist(handedness)
    points = list(opened.landmarks)
    points[13:21] = folded.landmarks[13:21]
    return HandObservation(handedness, tuple(points))


def three_finger_swipe_hand(handedness="Left", dx=0.0, dy=0.0):
    hand = open_hand(handedness)
    points = list(hand.landmarks)
    points[4] = Landmark(0.45, 0.79)
    points[18] = Landmark(0.66, 0.74)
    points[19] = Landmark(0.67, 0.77)
    points[20] = Landmark(0.66, 0.80)
    for index in range(len(points)):
        point = points[index]
        points[index] = Landmark(point.x + dx, point.y + dy, point.z)
    return HandObservation(handedness, tuple(points))


def action_kinds(frame):
    return [action.kind for action in frame.actions]


class GestureEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = GestureEngine()
        self.engine.configure(1.0, (0, 0, 1920, 1080))

    def test_pointer_moves_with_right_hand(self):
        frame = self.engine.process((open_hand(),), 1.0)
        self.assertIn("move", action_kinds(frame))

    def test_enabled_support_three_finger_swipe_switches_application_without_pointer_suppression(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), tuning={"swipe_enabled": 1.0})
        dominant = open_hand("Right")
        self.engine.process((dominant, three_finger_swipe_hand(dx=0.0)), 1.00)
        self.engine.process((dominant, three_finger_swipe_hand(dx=0.01)), 1.03)
        self.engine.process((dominant, three_finger_swipe_hand(dx=0.02)), 1.06)
        tracking = self.engine.process((dominant, three_finger_swipe_hand(dx=0.07)), 1.09)
        fired = self.engine.process((dominant, three_finger_swipe_hand(dx=0.15)), 1.12)
        self.assertIn("move", action_kinds(tracking))
        self.assertIn("app_next", action_kinds(fired))
        self.assertNotIn("move", action_kinds(fired))

    def test_dominant_three_finger_swipe_switches_applications(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), tuning={"swipe_enabled": 1.0})
        frames = []
        for timestamp, dx in ((1.00, 0.0), (1.03, 0.01), (1.06, 0.02), (1.09, 0.07)):
            frames.append(self.engine.process((three_finger_swipe_hand("Right", dx=dx),), timestamp))
        frame = self.engine.process((three_finger_swipe_hand("Right", dx=0.15),), 1.12)
        self.assertTrue(all("move" not in action_kinds(item) for item in frames))
        self.assertIn("app_next", action_kinds(frame))

    def test_pointer_reaches_screen_edges_from_compact_hand_workspace(self):
        right_edge = GestureEngine()
        right_edge.configure(1.0, (0, 0, 1920, 1080))
        x, _ = right_edge._map_pointer(Landmark(0.78, 0.5), 1.0)
        bottom_edge = GestureEngine()
        bottom_edge.configure(1.0, (0, 0, 1920, 1080))
        _, y = bottom_edge._map_pointer(Landmark(0.5, 0.78), 1.0)
        self.assertEqual(x, 1919)
        self.assertEqual(y, 1079)

    def test_middle_pinch_right_clicks_only_once_while_held(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 12, thumb.x + 0.01, thumb.y)
        first = self.engine.process((pinched,), 1.0)
        held = self.engine.process((pinched,), 1.1)
        self.assertIn("right_click", action_kinds(first))
        self.assertNotIn("move", action_kinds(first))
        self.assertNotIn("right_click", action_kinds(held))
        self.assertNotIn("move", action_kinds(held))

    def test_middle_thumb_contact_in_a_closed_hand_never_right_clicks(self):
        closed_contact = middle_pinched_with_other_fingers_folded("Right")
        frame = self.engine.process((closed_contact,), 1.0)
        self.assertNotIn("right_click", action_kinds(frame))

    def test_closed_finger_index_pinch_still_left_clicks(self):
        pinched = index_pinched_with_free_fingers_folded("Right")
        released = index_released_with_free_fingers_folded("Right")
        contact = self.engine.process((pinched,), 1.0)
        clicked = self.engine.process((released,), 1.1)
        self.assertIn("pinch_start", action_kinds(contact))
        self.assertIn("left_click", action_kinds(clicked))

    def test_index_pinch_release_left_clicks(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        contact = self.engine.process((pinched,), 1.0)
        held = self.engine.process((pinched,), 1.05)
        dropout_guard = self.engine.process((hand,), 1.1)
        released = self.engine.process((hand,), 1.14)
        self.assertNotIn("left_click", action_kinds(contact))
        self.assertIn("move vertically to scroll", contact.gesture)
        self.assertNotIn("move", action_kinds(contact))
        self.assertNotIn("pinch_move", action_kinds(held))
        self.assertNotIn("left_click", action_kinds(dropout_guard))
        self.assertIn("left_click", action_kinds(released))
        self.assertNotIn("move", action_kinds(released))

    def test_one_hand_pinch_scrolls_up_and_consumes_the_click(self):
        pinched = index_pinched_hand("Right")
        frames = [
            self.engine.process((shift_hand(pinched, dy=dy),), timestamp)
            for timestamp, dy in (
                (1.00, 0.000),
                (1.04, -0.012),
                (1.08, -0.028),
                (1.12, -0.050),
            )
        ]
        scrolls = [
            action
            for frame in frames
            for action in frame.actions
            if action.kind == "scroll"
        ]
        released = self.engine.process((open_hand("Right"),), 1.20)
        self.assertTrue(scrolls)
        self.assertTrue(all(action.amount > 0 for action in scrolls))
        self.assertNotIn("left_click", action_kinds(released))
        self.assertEqual(self.engine._last_index_release, -10.0)

    def test_one_hand_pinch_scrolls_down(self):
        pinched = index_pinched_hand("Right")
        frames = [
            self.engine.process((shift_hand(pinched, dy=dy),), timestamp)
            for timestamp, dy in (
                (1.00, 0.000),
                (1.04, 0.012),
                (1.08, 0.028),
                (1.12, 0.050),
            )
        ]
        amounts = [
            action.amount
            for frame in frames
            for action in frame.actions
            if action.kind == "scroll"
        ]
        self.assertTrue(amounts)
        self.assertTrue(all(amount < 0 for amount in amounts))

    def test_pinch_scroll_is_consistent_at_15_30_and_60_fps(self):
        totals = []
        for fps in (15, 30, 60):
            engine = GestureEngine()
            engine.configure(1.0, (0, 0, 1920, 1080))
            pinched = index_pinched_hand("Right")
            total = 0
            duration = 0.40
            for index in range(round(duration * fps) + 1):
                progress = index / (duration * fps)
                frame = engine.process(
                    (shift_hand(pinched, dy=-0.12 * progress),),
                    1.0 + index / fps,
                )
                total += sum(
                    action.amount
                    for action in frame.actions
                    if action.kind == "scroll"
                )
            totals.append(total)
        self.assertTrue(all(total > 0 for total in totals))
        self.assertLessEqual(max(totals) - min(totals), 1)

    def test_slow_pinch_scroll_arms_consistently_at_15_30_and_60_fps(self):
        totals = []
        for fps in (15, 30, 60):
            engine = GestureEngine()
            engine.configure(1.0, (0, 0, 1920, 1080))
            pinched = index_pinched_hand("Right")
            total = 0
            for index in range(fps + 1):
                frame = engine.process(
                    (shift_hand(pinched, dy=-0.06 * index / fps),),
                    1.0 + index / fps,
                )
                total += sum(
                    action.amount
                    for action in frame.actions
                    if action.kind == "scroll"
                )
            totals.append(total)
        self.assertTrue(all(total > 0 for total in totals))
        self.assertLessEqual(max(totals) - min(totals), 1)

    def test_left_handed_mode_mirrors_one_hand_pinch_scroll(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        pinched = index_pinched_hand("Left")
        frames = [
            self.engine.process((shift_hand(pinched, dy=dy),), timestamp)
            for timestamp, dy in (
                (1.00, 0.000),
                (1.04, -0.012),
                (1.08, -0.028),
                (1.12, -0.050),
            )
        ]
        self.assertTrue(
            any(
                action.kind == "scroll" and action.amount > 0
                for frame in frames
                for action in frame.actions
            )
        )

    def test_pinch_scroll_rejects_stationary_jitter_and_fingertip_motion(self):
        pinched = index_pinched_hand("Right")
        jitter_frames = [
            self.engine.process((shift_hand(pinched, dx=dx, dy=dy),), timestamp)
            for timestamp, dx, dy in (
                (1.00, 0.000, 0.000),
                (1.04, 0.004, -0.005),
                (1.08, -0.004, 0.004),
                (1.12, 0.003, -0.003),
                (1.16, 0.000, 0.000),
            )
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in jitter_frames))

        engine = GestureEngine()
        engine.configure(1.0, (0, 0, 1920, 1080))
        fingertip_frames = [
            engine.process((move_pinching_fingertips(pinched, dy),), timestamp)
            for timestamp, dy in (
                (2.00, 0.000),
                (2.04, -0.025),
                (2.08, -0.050),
                (2.12, -0.080),
            )
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in fingertip_frames))

    def test_horizontal_and_diagonal_first_pinch_never_become_scroll(self):
        for name, shifts in (
            ("horizontal", ((0.00, 0.00), (0.02, 0.00), (0.04, 0.00), (0.07, 0.00))),
            ("diagonal", ((0.00, 0.00), (0.02, -0.02), (0.04, -0.04), (0.07, -0.07))),
        ):
            with self.subTest(name=name):
                engine = GestureEngine()
                engine.configure(1.0, (0, 0, 1920, 1080))
                pinched = index_pinched_hand("Right")
                frames = [
                    engine.process((shift_hand(pinched, dx=dx, dy=dy),), 1.0 + index * 0.04)
                    for index, (dx, dy) in enumerate(shifts)
                ]
                self.assertFalse(any("scroll" in action_kinds(frame) for frame in frames))
                self.assertTrue(any("pinch_start" in action_kinds(frame) for frame in frames))

    def test_pinch_scroll_rejects_single_frame_jump_and_low_confidence(self):
        pinched = index_pinched_hand("Right")
        frames = (
            self.engine.process((pinched,), 1.00),
            self.engine.process((shift_hand(pinched, dy=-0.20),), 1.04),
            self.engine.process((pinched,), 1.08),
            self.engine.process((shift_hand(pinched, dy=-0.01),), 1.12),
        )
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in frames))

        engine = GestureEngine()
        engine.configure(1.0, (0, 0, 1920, 1080))
        low_confidence_frames = [
            engine.process(
                (with_confidence(shift_hand(pinched, dy=dy), 0.30),),
                2.0 + index * 0.04,
            )
            for index, dy in enumerate((0.0, -0.02, -0.04, -0.07))
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in low_confidence_frames))

    def test_pinch_scroll_requires_two_meaningful_directional_segments(self):
        pinched = index_pinched_hand("Right")
        frames = [
            self.engine.process((shift_hand(pinched, dy=dy),), timestamp)
            for timestamp, dy in (
                (1.00, 0.000),
                (1.04, 0.000),
                (1.08, 0.000),
                (1.12, -0.040),
                (1.16, -0.040),
            )
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in frames))

    def test_stationary_hold_can_still_transition_to_scroll_without_click(self):
        pinched = index_pinched_hand("Right")
        frames = [
            self.engine.process((pinched,), 1.00),
            self.engine.process((pinched,), 1.20),
            self.engine.process((pinched,), 1.36),
            self.engine.process((shift_hand(pinched, dy=-0.018),), 1.40),
            self.engine.process((shift_hand(pinched, dy=-0.040),), 1.44),
            self.engine.process((shift_hand(pinched, dy=-0.065),), 1.48),
        ]
        released = self.engine.process((open_hand("Right"),), 1.56)
        self.assertTrue(
            any(
                action.kind == "scroll" and action.amount > 0
                for frame in frames
                for action in frame.actions
            )
        )
        self.assertTrue(
            any("pinch_cancel" in action_kinds(frame) for frame in frames)
        )
        self.assertNotIn("left_click", action_kinds(released))

    def test_disabling_pinch_scroll_live_stops_an_active_scroll(self):
        pinched = index_pinched_hand("Right")
        for index, dy in enumerate((0.0, -0.012, -0.028, -0.050)):
            self.engine.process(
                (shift_hand(pinched, dy=dy),),
                1.0 + index * 0.04,
            )
        self.assertTrue(self.engine._pinch_scroll_active)
        self.engine.configure(
            1.0,
            (0, 0, 1920, 1080),
            tuning={"pinch_scroll_enabled": 0.0},
        )
        frames = [
            self.engine.process(
                (shift_hand(pinched, dy=dy),),
                timestamp,
            )
            for timestamp, dy in ((1.16, -0.08), (1.28, -0.12))
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in frames))

    def test_second_pinch_vertical_motion_remains_drag_not_scroll(self):
        hand = open_hand("Right")
        pinched = index_pinched_hand("Right")
        self.engine.process((pinched,), 1.00)
        self.engine.process((hand,), 1.10)
        second = self.engine.process((pinched,), 1.30)
        dragged = self.engine.process((shift_hand(pinched, dy=-0.08),), 1.38)
        dropout_guard = self.engine.process((hand,), 1.46)
        released = self.engine.process((hand,), 1.50)
        self.assertIn("left_down", action_kinds(second))
        self.assertIn("move", action_kinds(dragged))
        self.assertNotIn("scroll", action_kinds(dragged))
        self.assertNotIn("left_up", action_kinds(dropout_guard))
        self.assertIn("left_up", action_kinds(released))

    def test_sustained_scroll_pose_loss_is_consumed_until_release(self):
        pinched = index_pinched_hand("Right")
        for timestamp, dy in ((1.00, 0.0), (1.04, -0.012), (1.08, -0.028)):
            self.engine.process((shift_hand(pinched, dy=dy),), timestamp)
        active = self.engine.process((shift_hand(pinched, dy=-0.05),), 1.12)
        self.assertIn("scroll", action_kinds(active))
        invalid_pose = index_pinched_with_only_one_free_finger("Right")
        self.engine.process((shift_hand(invalid_pose, dy=-0.06),), 1.16)
        consumed = self.engine.process((shift_hand(invalid_pose, dy=-0.07),), 1.28)
        released = self.engine.process((open_hand("Right"),), 1.36)
        self.assertNotIn("scroll", action_kinds(consumed))
        self.assertNotIn("left_click", action_kinds(released))

    def test_consumed_scroll_survives_long_tracking_dropout_until_clear(self):
        pinched = index_pinched_hand("Right")
        for timestamp, dy in (
            (1.00, 0.000),
            (1.04, -0.012),
            (1.08, -0.028),
            (1.12, -0.050),
        ):
            active = self.engine.process(
                (shift_hand(pinched, dy=dy),),
                timestamp,
            )
        self.assertIn("scroll", action_kinds(active))

        missing = (
            self.engine.process((), 1.16),
            self.engine.process((), 1.40),
        )
        returned_closed = (
            self.engine.process((shift_hand(pinched, dy=-0.050),), 1.44),
            self.engine.process((shift_hand(pinched, dy=-0.050),), 1.48),
        )
        observed_clear = (
            self.engine.process((open_hand("Right"),), 1.52),
            self.engine.process((open_hand("Right"),), 1.60),
        )
        protected_kinds = [
            kind
            for frame in (*missing, *returned_closed, *observed_clear)
            for kind in action_kinds(frame)
        ]
        self.assertNotIn("left_click", protected_kinds)
        self.assertNotIn("left_down", protected_kinds)
        self.assertNotIn("pinch_start", protected_kinds)
        self.assertFalse(self.engine._pinch_scroll_suppress_click)

        fresh_contact = (
            self.engine.process((pinched,), 1.80),
            self.engine.process((pinched,), 1.84),
            self.engine.process((pinched,), 2.20),
        )
        fresh_release = (
            self.engine.process((open_hand("Right"),), 2.24),
            self.engine.process((open_hand("Right"),), 2.32),
        )
        self.assertTrue(
            any(
                "pinch_start" in action_kinds(frame)
                for frame in fresh_contact
            )
        )
        self.assertTrue(
            any(
                "left_click" in action_kinds(frame)
                for frame in fresh_release
            )
        )

    def test_pinch_scroll_burst_is_capped(self):
        pinched = index_pinched_hand("Right")
        frames = (
            self.engine.process((pinched,), 1.00),
            self.engine.process((shift_hand(pinched, dy=-0.02),), 1.04),
            self.engine.process((shift_hand(pinched, dy=-0.04),), 1.08),
            self.engine.process((shift_hand(pinched, dy=-0.11),), 1.12),
        )
        amounts = [
            abs(action.amount)
            for frame in frames
            for action in frame.actions
            if action.kind == "scroll"
        ]
        self.assertTrue(amounts)
        self.assertLessEqual(max(amounts), 2)

    def test_ring_thumb_pinch_middle_clicks_once_and_rejects_closed_hand(self):
        pinched = ring_pinched_hand("Right")
        first = self.engine.process((pinched,), 1.00)
        held = self.engine.process((pinched,), 1.08)
        released = self.engine.process((open_hand("Right"),), 1.16)
        self.assertIn("middle_click", action_kinds(first))
        self.assertNotIn("middle_click", action_kinds(held))
        self.assertNotIn("middle_click", action_kinds(released))

        engine = GestureEngine()
        engine.configure(1.0, (0, 0, 1920, 1080))
        closed = fist("Right")
        thumb = closed.landmarks[4]
        closed_contact = with_point(closed, 16, thumb.x + 0.01, thumb.y)
        frame = engine.process((closed_contact,), 2.0)
        self.assertNotIn("middle_click", action_kinds(frame))

    def test_invalid_or_disabled_ring_contact_does_not_freeze_pointer(self):
        opened = open_hand("Right")
        folded = fist("Right")
        points = list(opened.landmarks)
        points[9:13] = folded.landmarks[9:13]
        points[16] = Landmark(points[4].x + 0.01, points[4].y)
        invalid_contact = HandObservation("Right", tuple(points))
        frames = (
            self.engine.process((invalid_contact,), 1.00),
            self.engine.process((shift_hand(invalid_contact, dx=0.01),), 1.08),
        )
        self.assertTrue(all("move" in action_kinds(frame) for frame in frames))
        self.assertTrue(all("middle_click" not in action_kinds(frame) for frame in frames))

        disabled = GestureEngine()
        disabled.configure(
            1.0,
            (0, 0, 1920, 1080),
            tuning={"ring_pinch_middle_click": 0.0},
        )
        valid_contact = ring_pinched_hand("Right")
        self.assertIn("move", action_kinds(disabled.process((valid_contact,), 2.0)))
        self.assertIn(
            "move",
            action_kinds(disabled.process((shift_hand(valid_contact, dx=0.01),), 2.08)),
        )

    def test_click_contacts_do_not_retrigger_after_pose_flicker(self):
        middle = open_hand("Right")
        thumb = middle.landmarks[4]
        middle = with_point(middle, 12, thumb.x + 0.01, thumb.y)
        folded = fist("Right")
        middle_invalid_points = list(middle.landmarks)
        middle_invalid_points[17:21] = folded.landmarks[17:21]
        middle_invalid = HandObservation("Right", tuple(middle_invalid_points))
        middle_frames = (
            self.engine.process((middle,), 1.00),
            self.engine.process((middle_invalid,), 1.10),
            self.engine.process((middle,), 1.50),
        )
        self.assertEqual(
            sum("right_click" in action_kinds(frame) for frame in middle_frames),
            1,
        )

        engine = GestureEngine()
        engine.configure(1.0, (0, 0, 1920, 1080))
        ring = ring_pinched_hand("Right")
        ring_invalid_points = list(ring.landmarks)
        ring_invalid_points[9:13] = folded.landmarks[9:13]
        ring_invalid = HandObservation("Right", tuple(ring_invalid_points))
        ring_frames = (
            engine.process((ring,), 2.00),
            engine.process((ring_invalid,), 2.10),
            engine.process((ring,), 2.60),
        )
        self.assertEqual(
            sum("middle_click" in action_kinds(frame) for frame in ring_frames),
            1,
        )

    def test_one_clear_index_dropout_does_not_create_false_double_click(self):
        pinched = index_pinched_hand("Right")
        opened = open_hand("Right")
        frames = (
            self.engine.process((pinched,), 1.00),
            self.engine.process((pinched,), 1.04),
            self.engine.process((opened,), 1.08),
            self.engine.process((pinched,), 1.12),
        )
        kinds = [kind for frame in frames for kind in action_kinds(frame)]
        self.assertNotIn("left_click", kinds)
        self.assertNotIn("left_down", kinds)
        self.assertNotIn("left_up", kinds)

    def test_pinch_survives_edge_on_collapsed_palm_width(self):
        hand = index_pinched_hand("Right")
        points = list(hand.landmarks)
        points[17] = Landmark(points[5].x + 0.02, points[5].y, points[5].z)
        edge_on = HandObservation("Right", tuple(points))
        frame = self.engine.process((edge_on,), 1.0)
        self.assertTrue(self.engine._index_pinched)
        self.assertNotIn("left_click", action_kinds(frame))

    def test_3d_depth_separation_rejects_a_projected_edge_on_false_pinch(self):
        self.engine.configure(
            1.0,
            (0, 0, 1920, 1080),
            tuning={"pinch_3d_blend": 0.45},
        )
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        image_points = list(hand.landmarks)
        image_points[8] = Landmark(thumb.x, thumb.y)
        world_points = list(hand.landmarks)
        world_points[8] = Landmark(thumb.x, thumb.y, 0.40)
        projected_overlap = HandObservation("Right", tuple(image_points), tuple(world_points))
        self.assertGreater(self.engine._pinch_ratio(projected_overlap, 8), self.engine.tuning["pinch_contact"])

    def test_3d_hybrid_keeps_a_real_front_facing_pinch_responsive(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        image_points = list(hand.landmarks)
        image_points[8] = Landmark(thumb.x, thumb.y)
        world_points = list(hand.landmarks)
        world_points[8] = Landmark(thumb.x, thumb.y, 0.01)
        real_contact = HandObservation("Right", tuple(image_points), tuple(world_points))
        self.assertLess(self.engine._pinch_ratio(real_contact, 8), self.engine.tuning["pinch_contact"])

    def test_clear_thumb_edge_contact_is_not_blocked_by_noisy_depth(self):
        hand = open_hand("Right")
        image_points = list(hand.landmarks)
        image_points[17] = Landmark(image_points[5].x + 0.02, image_points[5].y)
        thumb = image_points[4]
        image_points[8] = Landmark(thumb.x + 0.01, thumb.y)
        world_points = list(hand.landmarks)
        world_points[8] = Landmark(thumb.x + 0.01, thumb.y, 0.40)
        thumb_edge_contact = HandObservation("Right", tuple(image_points), tuple(world_points))
        self.assertLess(self.engine._pinch_ratio(thumb_edge_contact, 8), self.engine.tuning["pinch_contact"])

    def test_borderline_pinch_requires_brief_stable_confirmation(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        borderline = with_point(hand, 8, thumb.x + 0.0875, thumb.y)  # ratio 0.33
        first = self.engine.process((borderline,), 1.0)
        confirmed = self.engine.process((borderline,), 1.02)
        self.assertNotIn("pinch_start", action_kinds(first))
        self.assertTrue(self.engine._index_pinched)
        self.assertIn("move vertically to scroll", confirmed.gesture)

    def test_threshold_jitter_does_not_create_a_false_pinch(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        inside = with_point(hand, 8, thumb.x + 0.0875, thumb.y)  # ratio 0.33
        outside = with_point(hand, 8, thumb.x + 0.094, thumb.y)  # ratio 0.36
        frames = (
            self.engine.process((inside,), 1.0),
            self.engine.process((outside,), 1.04),
            self.engine.process((inside,), 1.08),
        )
        self.assertFalse(any("pinch_start" in action_kinds(frame) for frame in frames))

    def test_single_pinch_distance_outlier_is_rejected_after_signal_warmup(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        open_ratio = with_point(hand, 8, thumb.x + 0.11, thumb.y)
        outlier = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((open_ratio,), 1.0)
        self.engine.process((open_ratio,), 1.04)
        spike = self.engine.process((outlier,), 1.08)
        self.assertNotIn("pinch_start", action_kinds(spike))

    def test_held_pinch_survives_landmark_jitter_and_releases_cleanly(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        deep = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        borderline_release = with_point(hand, 8, thumb.x + 0.143, thumb.y)  # ratio 0.55
        started = self.engine.process((deep,), 1.0)
        noisy_frames = [
            self.engine.process((borderline_release,), timestamp)
            for timestamp in (1.04, 1.08, 1.12)
        ]
        recovered = self.engine.process((deep,), 1.16)
        released = self.engine.process((hand,), 1.24)
        self.assertIn("move vertically to scroll", started.gesture)
        self.assertFalse(any("left_click" in action_kinds(frame) for frame in noisy_frames))
        self.assertNotIn("left_click", action_kinds(recovered))
        self.assertIn("left_click", action_kinds(released))

    def test_lost_hand_cancels_context_pinch(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((pinched,), 1.0)
        self.engine.process((), 1.05)
        lost = self.engine.process((), 1.25)
        self.assertIn("pinch_cancel", action_kinds(lost))

    def test_pointer_waits_for_settling_window_after_click(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((hand,), 0.8)
        self.engine.process((pinched,), 1.0)
        released = self.engine.process((hand,), 1.1)
        settling = self.engine.process((hand,), 1.124)
        resumed = self.engine.process((hand,), 1.126)
        self.assertNotIn("move", action_kinds(released))
        self.assertNotIn("move", action_kinds(settling))
        self.assertIn("move", action_kinds(resumed))

    def test_second_index_pinch_starts_drag_and_release_stops(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((pinched,), 1.0)
        self.engine.process((hand,), 1.1)
        second = self.engine.process((pinched,), 1.35)
        held = self.engine.process((shift_hand(pinched, dx=0.04),), 1.42)
        dropout_guard = self.engine.process((hand,), 1.5)
        released = self.engine.process((hand,), 1.54)
        self.assertIn("left_down", action_kinds(second))
        self.assertNotIn("move", action_kinds(second))
        self.assertIn("move", action_kinds(held))
        self.assertNotIn("left_up", action_kinds(dropout_guard))
        self.assertIn("left_up", action_kinds(released))
        self.assertNotIn("move", action_kinds(released))

    def test_second_index_pinch_without_movement_double_clicks(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((pinched,), 1.0)
        self.engine.process((hand,), 1.1)
        second = self.engine.process((pinched,), 1.32)
        held = self.engine.process((pinched,), 1.38)
        dropout_guard = self.engine.process((hand,), 1.45)
        released = self.engine.process((hand,), 1.49)
        self.assertIn("left_down", action_kinds(second))
        self.assertNotIn("move", action_kinds(held))
        self.assertNotIn("left_up", action_kinds(dropout_guard))
        self.assertIn("left_up", action_kinds(released))
        self.assertEqual(released.gesture, "Double click")

    def test_two_hand_pinches_expanding_zoom_in(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        started = self.engine.process((right, left), 1.0)
        expanded = self.engine.process((shift_hand(right, dx=0.06), shift_hand(left, dx=-0.06)), 1.15)
        zoom_actions = [action for action in expanded.actions if action.kind == "zoom"]
        self.assertNotIn("pinch_start", action_kinds(started))
        self.assertNotIn("scroll", action_kinds(started))
        self.assertNotIn("scroll", action_kinds(expanded))
        self.assertEqual(len(zoom_actions), 1)
        self.assertEqual(zoom_actions[0].amount, 1)
        self.assertGreater(zoom_actions[0].amount, 0)

    def test_two_hand_pinches_contracting_zoom_out(self):
        right = index_pinched_hand("Right", dx=0.24)
        left = index_pinched_hand("Left", dx=-0.24)
        self.engine.process((right, left), 1.0)
        contracted = self.engine.process((shift_hand(right, dx=-0.07), shift_hand(left, dx=0.07)), 1.15)
        zoom_actions = [action for action in contracted.actions if action.kind == "zoom"]
        self.assertEqual(len(zoom_actions), 1)
        self.assertLess(zoom_actions[0].amount, 0)

    def test_zoom_accepts_one_naturally_folded_free_finger(self):
        right = index_pinched_with_one_free_finger_folded("Right", dx=0.18)
        left = index_pinched_with_one_free_finger_folded("Left", dx=-0.18)
        self.engine.process((right, left), 1.0)
        expanded = self.engine.process(
            (shift_hand(right, dx=0.06), shift_hand(left, dx=-0.06)),
            1.15,
        )
        zoom_actions = [action for action in expanded.actions if action.kind == "zoom"]
        self.assertEqual([action.amount for action in zoom_actions], [1])
        self.assertNotIn("scroll", action_kinds(expanded))

    def test_zoom_rejects_pose_with_only_one_free_finger(self):
        right = index_pinched_with_only_one_free_finger("Right", dx=0.18)
        left = index_pinched_with_only_one_free_finger("Left", dx=-0.18)
        started = self.engine.process((right, left), 1.0)
        expanded = self.engine.process(
            (shift_hand(right, dx=0.08), shift_hand(left, dx=-0.08)),
            1.15,
        )
        self.assertNotIn("zoom", action_kinds(started))
        self.assertNotIn("zoom", action_kinds(expanded))
        self.assertNotIn("pinch_start", action_kinds(started))

    def test_gradual_expansion_produces_smooth_zoom_in(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        self.engine.process((right, left), 1.0)
        actions = []
        for timestamp, shift in ((1.03, 0.012), (1.06, 0.024), (1.10, 0.036), (1.14, 0.05)):
            frame = self.engine.process(
                (shift_hand(right, dx=shift), shift_hand(left, dx=-shift)),
                timestamp,
            )
            actions.extend(action for action in frame.actions if action.kind == "zoom")
        self.assertTrue(actions)
        self.assertTrue(all(action.amount == 1 for action in actions))

    def test_zoom_ignores_small_two_hand_jitter(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        self.engine.process((right, left), 1.0)
        actions = []
        for timestamp, shift in ((1.10, 0.004), (1.20, -0.004), (1.30, 0.006), (1.40, -0.006)):
            frame = self.engine.process(
                (shift_hand(right, dx=shift), shift_hand(left, dx=-shift)),
                timestamp,
            )
            actions.extend(action for action in frame.actions if action.kind == "zoom")
        self.assertEqual(actions, [])

    def test_zoom_rate_limits_large_motion_to_single_steps(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        expanded_hands = (shift_hand(right, dx=0.08), shift_hand(left, dx=-0.08))
        self.engine.process((right, left), 1.0)
        first = self.engine.process(expanded_hands, 1.10)
        limited = self.engine.process(expanded_hands, 1.14)
        resumed = self.engine.process(expanded_hands, 1.20)
        first_zoom = [action for action in first.actions if action.kind == "zoom"]
        resumed_zoom = [action for action in resumed.actions if action.kind == "zoom"]
        self.assertEqual([action.amount for action in first_zoom], [1])
        self.assertNotIn("zoom", action_kinds(limited))
        self.assertLessEqual(len(resumed_zoom), 1)
        self.assertTrue(all(action.amount == 1 for action in resumed_zoom))

    def test_zoom_scales_across_different_initial_hand_spacings(self):
        for spacing, expansion in ((0.10, 0.04), (0.30, 0.05)):
            with self.subTest(spacing=spacing):
                engine = GestureEngine()
                engine.configure(1.0, (0, 0, 1920, 1080))
                right = index_pinched_hand("Right", dx=spacing)
                left = index_pinched_hand("Left", dx=-spacing)
                engine.process((right, left), 1.0)
                frame = engine.process(
                    (shift_hand(right, dx=expansion), shift_hand(left, dx=-expansion)),
                    1.15,
                )
                zoom_actions = [action for action in frame.actions if action.kind == "zoom"]
                self.assertEqual([action.amount for action in zoom_actions], [1])

    def test_tiny_reversal_after_zoom_in_does_not_zoom_out(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        self.engine.process((right, left), 1.0)
        expanded = self.engine.process(
            (shift_hand(right, dx=0.08), shift_hand(left, dx=-0.08)),
            1.10,
        )
        reversed_slightly = self.engine.process(
            (shift_hand(right, dx=0.074), shift_hand(left, dx=-0.074)),
            1.20,
        )
        self.assertIn("zoom", action_kinds(expanded))
        zoom_actions = [action for action in reversed_slightly.actions if action.kind == "zoom"]
        self.assertTrue(all(action.amount > 0 for action in zoom_actions))

    def test_zoom_requires_both_pinches_to_release_before_clicks_resume(self):
        right = index_pinched_hand("Right", dx=0.18)
        left = index_pinched_hand("Left", dx=-0.18)
        self.engine.process((right, left), 1.0)
        one_released = self.engine.process((right, shift_hand(open_hand("Left"), dx=-0.18)), 1.1)
        both_released = self.engine.process((shift_hand(open_hand("Right"), dx=0.18), shift_hand(open_hand("Left"), dx=-0.18)), 1.2)
        self.assertNotIn("left_click", action_kinds(one_released))
        self.assertNotIn("pinch_start", action_kinds(one_released))
        self.assertNotIn("left_click", action_kinds(both_released))

    def test_folded_free_fingers_trigger_neither_zoom_scroll_nor_click(self):
        right = index_pinched_with_free_fingers_folded("Right", dx=0.18)
        left = index_pinched_with_free_fingers_folded("Left", dx=-0.18)
        frame = self.engine.process((right, left), 1.0)
        self.assertNotIn("zoom", action_kinds(frame))
        self.assertNotIn("scroll", action_kinds(frame))
        self.assertNotIn("pinch_start", action_kinds(frame))

    def test_open_left_palm_reserves_index_pinch_for_volume(self):
        right = open_hand("Right")
        thumb = right.landmarks[4]
        pinched = with_point(right, 8, thumb.x + 0.01, thumb.y)
        left = open_hand("Left")
        start = self.engine.process((pinched, left), 1.0)
        moved = with_point(pinched, 8, pinched.landmarks[8].x, pinched.landmarks[8].y - 0.08)
        volume = self.engine.process((moved, left), 1.1)
        self.assertNotIn("left_click", action_kinds(start))
        self.assertIn("volume", action_kinds(volume))

    def test_left_fist_and_right_index_pinch_scrolls_up(self):
        right = open_hand("Right")
        thumb = right.landmarks[4]
        pinched = with_point(right, 8, thumb.x + 0.01, thumb.y)
        left = fist("Left")
        start = self.engine.process((pinched, left), 1.0)
        moved = with_point(pinched, 8, pinched.landmarks[8].x, pinched.landmarks[8].y - 0.08)
        scrolled = self.engine.process((moved, left), 1.1)
        scroll_actions = [action for action in scrolled.actions if action.kind == "scroll"]
        self.assertNotIn("left_click", action_kinds(start))
        self.assertEqual(len(scroll_actions), 1)
        self.assertGreater(scroll_actions[0].amount, 0)

    def test_left_fist_and_right_index_pinch_scrolls_down(self):
        right = open_hand("Right")
        thumb = right.landmarks[4]
        pinched = with_point(right, 8, thumb.x + 0.01, thumb.y)
        left = fist("Left")
        self.engine.process((pinched, left), 1.0)
        moved = with_point(pinched, 8, pinched.landmarks[8].x, pinched.landmarks[8].y + 0.08)
        scrolled = self.engine.process((moved, left), 1.1)
        scroll_actions = [action for action in scrolled.actions if action.kind == "scroll"]
        self.assertEqual(len(scroll_actions), 1)
        self.assertLess(scroll_actions[0].amount, 0)

    def test_left_fist_without_right_pinch_does_not_scroll(self):
        frame = self.engine.process((open_hand("Right"), fist("Left")), 1.0)
        self.assertNotIn("scroll", action_kinds(frame))

    def test_two_finger_pose_scrolls_up_and_suppresses_pointer(self):
        hand = two_finger_hand("Right")
        started = self.engine.process((hand,), 1.0)
        moved = self.engine.process((shift_hand(hand, dy=-0.08),), 1.1)
        scroll_actions = [action for action in moved.actions if action.kind == "scroll"]
        self.assertNotIn("move", action_kinds(started))
        self.assertNotIn("move", action_kinds(moved))
        self.assertEqual(len(scroll_actions), 1)
        self.assertGreater(scroll_actions[0].amount, 0)

    def test_two_finger_pose_scrolls_down(self):
        hand = two_finger_hand("Right")
        self.engine.process((hand,), 1.0)
        moved = self.engine.process((shift_hand(hand, dy=0.08),), 1.1)
        scroll_actions = [action for action in moved.actions if action.kind == "scroll"]
        self.assertEqual(len(scroll_actions), 1)
        self.assertLess(scroll_actions[0].amount, 0)

    def test_held_two_finger_position_scrolls_continuously(self):
        hand = two_finger_hand("Right")
        held_down = shift_hand(hand, dy=0.08)
        self.engine.process((hand,), 1.0)
        frames = [
            self.engine.process((held_down,), timestamp)
            for timestamp in (1.10, 1.20, 1.30, 1.40)
        ]
        amounts = [
            action.amount
            for frame in frames
            for action in frame.actions
            if action.kind == "scroll"
        ]
        self.assertGreaterEqual(len(amounts), 4)
        self.assertTrue(all(amount < 0 for amount in amounts))

    def test_held_two_finger_position_can_reverse_continuous_direction(self):
        hand = two_finger_hand("Right")
        self.engine.process((hand,), 1.0)
        down = self.engine.process((shift_hand(hand, dy=0.08),), 1.1)
        up = self.engine.process((shift_hand(hand, dy=-0.08),), 1.2)
        self.assertTrue(any(action.kind == "scroll" and action.amount < 0 for action in down.actions))
        self.assertTrue(any(action.kind == "scroll" and action.amount > 0 for action in up.actions))

    def test_two_finger_scroll_dead_zone_rejects_stationary_jitter(self):
        hand = two_finger_hand("Right")
        self.engine.process((hand,), 1.0)
        frames = [
            self.engine.process((shift_hand(hand, dy=dy),), timestamp)
            for timestamp, dy in ((1.2, 0.008), (1.4, -0.009), (1.6, 0.01), (1.8, -0.007))
        ]
        self.assertFalse(any("scroll" in action_kinds(frame) for frame in frames))

    def test_open_hand_does_not_trigger_two_finger_scroll(self):
        first = self.engine.process((open_hand("Right"),), 1.0)
        moved = self.engine.process((shift_hand(open_hand("Right"), dy=-0.08),), 1.1)
        self.assertNotIn("scroll", action_kinds(first))
        self.assertNotIn("scroll", action_kinds(moved))
        self.assertIn("move", action_kinds(moved))

    def test_left_handed_mode_uses_left_hand_for_pointer_and_click(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        left = open_hand("Left")
        pointer = self.engine.process((left,), 1.0)
        thumb = left.landmarks[4]
        pinched = with_point(left, 8, thumb.x + 0.01, thumb.y)
        contact = self.engine.process((pinched,), 1.1)
        released = self.engine.process((left,), 1.2)
        self.assertIn("move", action_kinds(pointer))
        self.assertIn("move vertically to scroll", contact.gesture)
        self.assertIn("left_click", action_kinds(released))

    def test_left_handed_mode_keeps_closed_index_click_and_guards_right_click(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        pinched = index_pinched_with_free_fingers_folded("Left")
        released = index_released_with_free_fingers_folded("Left")
        contact = self.engine.process((pinched,), 1.0)
        clicked = self.engine.process((released,), 1.1)
        self.assertIn("pinch_start", action_kinds(contact))
        self.assertIn("left_click", action_kinds(clicked))

        self.engine.reset()
        closed_middle_contact = middle_pinched_with_other_fingers_folded("Left")
        right_click = self.engine.process((closed_middle_contact,), 2.0)
        self.assertNotIn("right_click", action_kinds(right_click))

    def test_left_handed_mode_mirrors_support_hand_scroll(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        left = index_pinched_hand("Left")
        right = fist("Right")
        self.engine.process((left, right), 1.0)
        moved = with_point(left, 8, left.landmarks[8].x, left.landmarks[8].y - 0.08)
        frame = self.engine.process((moved, right), 1.1)
        self.assertIn("scroll", action_kinds(frame))
        self.assertNotIn("left_click", action_kinds(frame))

    def test_left_handed_mode_two_finger_scroll_uses_left_hand(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        hand = two_finger_hand("Left")
        self.engine.process((hand,), 1.0)
        moved = self.engine.process((shift_hand(hand, dy=-0.08),), 1.1)
        self.assertIn("scroll", action_kinds(moved))

    def test_two_finger_scroll_accepts_a_side_view_using_world_landmarks(self):
        hand = two_finger_hand("Right")
        image_points = list(hand.landmarks)
        # The projected PIP/DIP joints bend when the hand is viewed from the
        # side, while the world landmarks retain the true raised-finger pose.
        image_points[7] = Landmark(0.55, 0.49)
        image_points[11] = Landmark(0.65, 0.44)
        side_view = HandObservation("Right", tuple(image_points), hand.landmarks)
        self.engine.process((side_view,), 1.0)

        moved_image = tuple(Landmark(point.x, point.y - 0.08, point.z) for point in image_points)
        moved_world = tuple(Landmark(point.x, point.y - 0.08, point.z) for point in hand.landmarks)
        moved = self.engine.process((HandObservation("Right", moved_image, moved_world),), 1.1)
        self.assertIn("scroll", action_kinds(moved))

    def test_two_finger_pose_scrolls_horizontally(self):
        hand = two_finger_hand("Right")
        self.engine.process((hand,), 1.0)
        moved = self.engine.process((shift_hand(hand, dx=0.08),), 1.12)
        horizontal = [action for action in moved.actions if action.kind == "scroll_horizontal"]
        self.assertEqual(len(horizontal), 1)
        self.assertGreater(horizontal[0].amount, 0)

    def test_left_handed_mode_mirrors_volume_and_right_click(self):
        self.engine.configure(1.0, (0, 0, 1920, 1080), left_handed=True)
        left = index_pinched_hand("Left")
        right = open_hand("Right")
        self.engine.process((left, right), 1.0)
        moved = with_point(left, 8, left.landmarks[8].x, left.landmarks[8].y - 0.08)
        volume = self.engine.process((moved, right), 1.1)
        self.assertIn("volume", action_kinds(volume))
        self.engine.reset()
        left = open_hand("Left")
        thumb = left.landmarks[4]
        middle_pinched = with_point(left, 12, thumb.x + 0.01, thumb.y)
        right_click = self.engine.process((middle_pinched,), 2.0)
        self.assertIn("right_click", action_kinds(right_click))

    def test_reset_preserves_left_handed_configuration(self):
        self.engine.configure(1.25, (10, 20, 1600, 900), left_handed=True)
        self.engine.reset()
        frame = self.engine.process((open_hand("Left"),), 1.0)
        self.assertTrue(self.engine.left_handed)
        self.assertEqual(self.engine.sensitivity, 1.25)
        self.assertEqual(self.engine.screen, (10, 20, 1600, 900))
        self.assertIn("move", action_kinds(frame))

    def test_left_fist_scrolls_even_when_folded_index_touches_thumb(self):
        right = index_pinched_hand("Right")
        left = fist_with_index_touching_thumb("Left")
        self.engine.process((right, left), 1.0)
        moved = with_point(right, 8, right.landmarks[8].x, right.landmarks[8].y - 0.08)
        frame = self.engine.process((moved, left), 1.1)
        self.assertIn("scroll", action_kinds(frame))
        self.assertNotIn("zoom", action_kinds(frame))

    def test_scroll_survives_one_frame_left_fist_classification_flicker(self):
        right = index_pinched_hand("Right")
        self.engine.process((right, fist("Left")), 1.0)
        moved = with_point(right, 8, right.landmarks[8].x, right.landmarks[8].y - 0.08)
        frame = self.engine.process((moved, fist_with_one_finger_tracking_open("Left")), 1.1)
        self.assertIn("scroll", action_kinds(frame))

    def test_single_fist_does_not_pause_control(self):
        closed = fist("Right")
        self.engine.process((closed,), 1.0)
        frame = self.engine.process((closed,), 1.75)
        self.assertNotIn("pause_changed", action_kinds(frame))
        self.assertFalse(frame.paused)
        self.assertEqual(frame.gesture, "Show both fists to pause")

    def test_both_fists_pause_and_active_fist_resumes(self):
        right = fist("Right")
        left = fist("Left")
        self.engine.process((right, left), 1.0)
        paused = self.engine.process((right, left), 1.75)
        held = self.engine.process((right, left), 2.0)
        self.assertIn("pause_changed", action_kinds(paused))
        self.assertTrue(paused.paused)
        self.assertNotIn("pause_changed", action_kinds(held))
        self.engine.process((open_hand("Right"), open_hand("Left")), 2.1)
        self.engine.process((right, open_hand("Left")), 2.2)
        resumed = self.engine.process((right, open_hand("Left")), 2.95)
        self.assertIn("pause_changed", action_kinds(resumed))
        self.assertFalse(resumed.paused)

    def test_paused_support_hand_fist_does_not_resume_control(self):
        self.engine.set_paused(True)
        self.engine.process((open_hand("Right"), fist("Left")), 1.0)
        still_paused = self.engine.process((open_hand("Right"), fist("Left")), 1.8)
        self.assertNotIn("pause_changed", action_kinds(still_paused))
        self.assertTrue(still_paused.paused)

    def test_lost_hand_releases_active_drag(self):
        hand = open_hand()
        thumb = hand.landmarks[4]
        pinched = with_point(hand, 8, thumb.x + 0.01, thumb.y)
        self.engine.process((pinched,), 1.0)
        self.engine.process((hand,), 1.1)
        self.engine.process((pinched,), 1.3)
        self.engine.process((), 1.35)
        released = self.engine.process((), 1.6)
        self.assertIn("left_up", action_kinds(released))

if __name__ == "__main__":
    unittest.main()
