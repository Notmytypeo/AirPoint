import unittest
from types import SimpleNamespace

from app.camera_worker import CameraWorker, StartupActivationGate
from app.gestures import GestureAction, HandObservation, Landmark


def fake_result(name="Right"):
    point = SimpleNamespace(x=0.1, y=0.2, z=0.0)
    category = SimpleNamespace(category_name=name, display_name="")
    return SimpleNamespace(hand_landmarks=[[point] * 21], handedness=[[category]])


def duplicate_handedness_result():
    category = SimpleNamespace(category_name="Left", display_name="")
    left_side = [SimpleNamespace(x=0.20, y=0.2, z=0.0)] * 21
    right_side = [SimpleNamespace(x=0.80, y=0.2, z=0.0)] * 21
    return SimpleNamespace(hand_landmarks=[left_side, right_side], handedness=[[category], [category]])


class FakeCapture:
    def __init__(self, values=None, accepted=True):
        self.values = dict(values or {})
        self.accepted = accepted
        self.writes = []

    def get(self, property_id):
        return self.values.get(property_id, -1.0)

    def set(self, property_id, value):
        self.writes.append((property_id, value))
        if self.accepted:
            self.values[property_id] = float(value)
        return self.accepted


FAKE_CV2 = SimpleNamespace(
    CAP_PROP_BUFFERSIZE=1,
    CAP_PROP_FOURCC=2,
    CAP_PROP_FRAME_WIDTH=3,
    CAP_PROP_FRAME_HEIGHT=4,
    CAP_PROP_FPS=5,
    CAP_PROP_AUTOFOCUS=6,
    CAP_PROP_FOCUS=7,
    VideoWriter_fourcc=lambda *_args: 99,
)


class CameraWorkerTests(unittest.TestCase):
    def test_focus_lock_forces_manual_focus_and_clamps_its_value(self):
        worker = CameraWorker()
        worker.set_focus(True, 999, True)
        self.assertFalse(worker._autofocus)
        self.assertTrue(worker._focus_lock)
        self.assertEqual(worker._manual_focus, 255)
        self.assertEqual(worker._focus_revision, 1)

    def test_capture_fps_change_reopens_camera_and_clamps_value(self):
        worker = CameraWorker()
        original_revision = worker._camera_revision

        worker.set_capture_fps(240)

        self.assertEqual(worker._capture_fps, 120)
        self.assertEqual(worker._camera_revision, original_revision + 1)

    def test_capture_configuration_applies_and_reports_requested_fps(self):
        capture = FakeCapture()

        status = CameraWorker._configure_capture(capture, FAKE_CV2, 30)

        self.assertIn((FAKE_CV2.CAP_PROP_FPS, 30), capture.writes)
        self.assertEqual(status["requested_fps"], 30)
        self.assertAlmostEqual(status["reported_fps"], 30.0)
        self.assertTrue(status["fps_accepted"])

    def test_manual_focus_is_applied_after_autofocus_is_disabled(self):
        worker = CameraWorker()
        worker.set_focus(False, 180, False)
        capture = FakeCapture({
            FAKE_CV2.CAP_PROP_AUTOFOCUS: 1.0,
            FAKE_CV2.CAP_PROP_FOCUS: 100.0,
        })
        statuses = []
        worker.focus_status.connect(statuses.append)

        worker._apply_focus(capture, FAKE_CV2)

        self.assertEqual(
            capture.writes[-2:],
            [(FAKE_CV2.CAP_PROP_AUTOFOCUS, 0), (FAKE_CV2.CAP_PROP_FOCUS, 180)],
        )
        self.assertEqual(capture.get(FAKE_CV2.CAP_PROP_FOCUS), 180.0)
        self.assertTrue(statuses[-1]["manual_supported"])
        self.assertTrue(statuses[-1]["applied"])

    def test_unsupported_focus_driver_is_reported_instead_of_silently_ignored(self):
        worker = CameraWorker()
        capture = FakeCapture(accepted=False)
        statuses = []
        worker.focus_status.connect(statuses.append)

        worker._apply_focus(capture, FAKE_CV2)

        self.assertFalse(statuses[-1]["manual_supported"])
        self.assertFalse(statuses[-1]["autofocus_supported"])
        self.assertIn("does not expose focus controls", statuses[-1]["message"])

    def test_orientation_distinguishes_front_and_hand_specific_edges(self):
        points = [Landmark(0.0, 0.0, 0.0) for _ in range(21)]
        points[5] = Landmark(1.0, 0.0, 0.0)
        points[17] = Landmark(0.0, 1.0, 0.0)
        front = HandObservation("Right", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(front)[0], "PALM FRONT")

        points[5] = Landmark(0.0, 1.0, 0.0)
        points[17] = Landmark(0.0, 0.0, 1.0)
        right_edge = HandObservation("Right", tuple(points), tuple(points))
        left_edge = HandObservation("Left", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(right_edge)[0], "THUMB EDGE")
        self.assertEqual(CameraWorker._hand_orientation(left_edge)[0], "PINKY EDGE")

    def test_orientation_covers_diagonal_and_vertical_edge_states(self):
        points = [Landmark(0.0, 0.0, 0.0) for _ in range(21)]
        # Cross((0, 1, 0), (-.8, 0, .6)) gives the normalized
        # front-right normal (.6, 0, .8) for the right hand.
        points[5] = Landmark(0.0, 1.0, 0.0)
        points[17] = Landmark(-0.8, 0.0, 0.6)
        diagonal = HandObservation("Right", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(diagonal)[0], "FRONT-RIGHT EDGE")

        # Cross((1, 0, 0), (0, 0, 1)) points straight upward in image space.
        points[5] = Landmark(1.0, 0.0, 0.0)
        points[17] = Landmark(0.0, 0.0, 1.0)
        up = HandObservation("Left", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(up)[0], "UP EDGE")

    def test_handedness_is_preserved_when_swap_is_off(self):
        hands = CameraWorker._to_hands(fake_result("Right"), False)
        self.assertEqual(hands[0].handedness, "Right")

    def test_handedness_is_reversed_when_swap_is_on(self):
        hands = CameraWorker._to_hands(fake_result("Right"), True)
        self.assertEqual(hands[0].handedness, "Left")

    def test_duplicate_handedness_is_spatially_repaired_for_mirrored_preview(self):
        hands = CameraWorker._to_hands(duplicate_handedness_result(), False)
        self.assertEqual([hand.handedness for hand in hands], ["Right", "Left"])

    def test_startup_activation_requires_hold_then_both_release(self):
        gate = StartupActivationGate(hold_seconds=0.35)
        self.assertFalse(gate.update(True, True, True, 1.0)[0])
        self.assertFalse(gate.update(True, True, True, 1.2)[0])
        qualified = gate.update(True, True, True, 1.36)
        self.assertFalse(qualified[0])
        self.assertIn("Release both fists", qualified[1])
        self.assertFalse(gate.update(True, False, True, 1.4)[0])
        activated = gate.update(True, False, False, 1.45)
        self.assertTrue(activated[0])
        self.assertTrue(gate.consumed)

    def test_startup_activation_cannot_run_twice(self):
        gate = StartupActivationGate(hold_seconds=0.1)
        gate.update(True, True, True, 1.0)
        gate.update(True, True, True, 1.11)
        self.assertTrue(gate.update(True, False, False, 1.2)[0])
        self.assertFalse(gate.update(True, True, True, 2.0)[0])
        self.assertFalse(gate.update(True, False, False, 2.2)[0])

    def test_losing_a_hand_resets_startup_hold(self):
        gate = StartupActivationGate(hold_seconds=0.35)
        gate.update(True, True, True, 1.0)
        gate.update(False, False, False, 1.3)
        self.assertFalse(gate.update(True, True, True, 1.4)[0])
        self.assertFalse(gate.qualified)

    def test_manual_activation_consumes_startup_gesture(self):
        gate = StartupActivationGate()
        gate.consume()
        self.assertFalse(gate.update(True, True, True, 1.0)[0])
        self.assertTrue(gate.consumed)

    def test_resuming_control_centers_the_pointer(self):
        class Controller:
            def __init__(self):
                self.center_calls = 0

            def center_pointer(self):
                self.center_calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("pause_changed", amount=1), GestureAction("pause_changed", amount=0)))
        self.assertEqual(controller.center_calls, 1)

    def test_app_switch_actions_use_the_platform_switch_seam(self):
        class Controller:
            def __init__(self):
                self.directions = []
                self.task_view_calls = 0
                self.desktop_calls = 0

            def switch_application(self, direction):
                self.directions.append(direction)

            def task_view(self):
                self.task_view_calls += 1

            def show_desktop(self):
                self.desktop_calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("app_next"), GestureAction("app_previous"), GestureAction("task_view"), GestureAction("show_desktop")))
        self.assertEqual(controller.directions, [1, -1])
        self.assertEqual(controller.task_view_calls, 1)
        self.assertEqual(controller.desktop_calls, 1)

if __name__ == "__main__":
    unittest.main()
