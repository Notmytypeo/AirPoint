import unittest
from types import SimpleNamespace

from app.camera_worker import CameraWorker, StartupActivationGate


def fake_result(name="Right"):
    point = SimpleNamespace(x=0.1, y=0.2, z=0.0)
    category = SimpleNamespace(category_name=name, display_name="")
    return SimpleNamespace(hand_landmarks=[[point] * 21], handedness=[[category]])


class CameraWorkerTests(unittest.TestCase):
    def test_handedness_is_preserved_when_swap_is_off(self):
        hands = CameraWorker._to_hands(fake_result("Right"), False)
        self.assertEqual(hands[0].handedness, "Right")

    def test_handedness_is_reversed_when_swap_is_on(self):
        hands = CameraWorker._to_hands(fake_result("Right"), True)
        self.assertEqual(hands[0].handedness, "Left")

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

if __name__ == "__main__":
    unittest.main()
