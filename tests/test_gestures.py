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
        for timestamp, dx in ((1.00, 0.0), (1.03, 0.01), (1.06, 0.02), (1.09, 0.07)):
            self.engine.process((three_finger_swipe_hand("Right", dx=dx),), timestamp)
        frame = self.engine.process((three_finger_swipe_hand("Right", dx=0.15),), 1.12)
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
        released = self.engine.process((hand,), 1.1)
        self.assertNotIn("left_click", action_kinds(contact))
        self.assertIn("pinch_start", action_kinds(contact))
        self.assertNotIn("move", action_kinds(contact))
        self.assertIn("pinch_move", action_kinds(held))
        self.assertIn("left_click", action_kinds(released))
        self.assertNotIn("move", action_kinds(released))

    def test_pinch_survives_edge_on_collapsed_palm_width(self):
        hand = index_pinched_hand("Right")
        points = list(hand.landmarks)
        points[17] = Landmark(points[5].x + 0.02, points[5].y, points[5].z)
        edge_on = HandObservation("Right", tuple(points))
        frame = self.engine.process((edge_on,), 1.0)
        self.assertIn("pinch_start", action_kinds(frame))

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

    def test_borderline_pinch_requires_brief_stable_confirmation(self):
        hand = open_hand("Right")
        thumb = hand.landmarks[4]
        borderline = with_point(hand, 8, thumb.x + 0.0875, thumb.y)  # ratio 0.33
        first = self.engine.process((borderline,), 1.0)
        confirmed = self.engine.process((borderline,), 1.04)
        self.assertNotIn("pinch_start", action_kinds(first))
        self.assertIn("pinch_start", action_kinds(confirmed))

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
        self.assertIn("pinch_start", action_kinds(started))
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
        settling = self.engine.process((hand,), 1.149)
        resumed = self.engine.process((hand,), 1.151)
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
        released = self.engine.process((hand,), 1.5)
        self.assertIn("left_down", action_kinds(second))
        self.assertNotIn("move", action_kinds(second))
        self.assertIn("move", action_kinds(held))
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
        released = self.engine.process((hand,), 1.45)
        self.assertIn("left_down", action_kinds(second))
        self.assertNotIn("move", action_kinds(held))
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
        self.assertIn("pinch_start", action_kinds(contact))
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
