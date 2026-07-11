import unittest

from app.system_control import InputController, disable_background_throttling, enable_tracking_priority


class RecordingMouseController(InputController):
    def __init__(self):
        self.events = []
        self.key_events = []

    def _mouse(self, flags: int, x: int = 0, y: int = 0, mouse_data: int = 0) -> None:
        self.events.append((flags, mouse_data))

    def _key(self, key: int, key_up: bool = False) -> None:
        self.key_events.append((key, key_up))


class RecordingContextController(InputController):
    def __init__(self, target):
        self.target = target
        self._left_held = False
        self._context_drag_axis = None
        self._context_drag_bounds = None
        self._context_drag_anchor = (0, 0)
        self.mouse_events = []
        self.moves = []

    def _cursor_position(self):
        return 50, 30

    def _detect_adjustable_axis(self, x, y):
        return self.target

    def _mouse(self, flags: int, x: int = 0, y: int = 0, mouse_data: int = 0) -> None:
        self.mouse_events.append(flags)

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))


class SystemControlTests(unittest.TestCase):
    def test_background_throttling_can_be_disabled_on_windows(self):
        self.assertTrue(disable_background_throttling())

    def test_tracking_priority_can_be_enabled_on_windows(self):
        self.assertTrue(enable_tracking_priority())

    def test_scroll_wheel_direction_and_step_count(self):
        controller = RecordingMouseController()
        controller.scroll(2)
        controller.scroll(-1)
        self.assertEqual(
            controller.events,
            [
                (controller.MOUSEEVENTF_WHEEL, 120),
                (controller.MOUSEEVENTF_WHEEL, 120),
                (controller.MOUSEEVENTF_WHEEL, -120),
            ],
        )

    def test_center_pointer_uses_virtual_screen_center(self):
        controller = RecordingContextController(None)
        controller.screen_bounds = lambda: (-1920, 0, 3840, 1080)
        controller.center_pointer()
        self.assertEqual(controller.moves, [(0, 540)])

    def test_zoom_uses_balanced_control_wheel_events(self):
        controller = RecordingMouseController()
        controller.zoom(2)
        controller.zoom(-1)
        self.assertEqual(
            controller.key_events,
            [
                (controller.VK_CONTROL, False),
                (controller.VK_CONTROL, True),
                (controller.VK_CONTROL, False),
                (controller.VK_CONTROL, True),
            ],
        )
        self.assertEqual(
            controller.events,
            [
                (controller.MOUSEEVENTF_WHEEL, 120),
                (controller.MOUSEEVENTF_WHEEL, 120),
                (controller.MOUSEEVENTF_WHEEL, -120),
            ],
        )

    def test_horizontal_slider_drag_locks_vertical_axis(self):
        controller = RecordingContextController(("horizontal", (10, 20, 110, 40)))
        self.assertTrue(controller.begin_context_pinch())
        controller.move_context_pinch(95, 300)
        controller.complete_context_pinch()
        self.assertEqual(controller.moves, [(95, 30)])
        self.assertEqual(controller.mouse_events, [controller.MOUSEEVENTF_LEFTDOWN, controller.MOUSEEVENTF_LEFTUP])

    def test_vertical_scrollbar_drag_locks_horizontal_axis(self):
        controller = RecordingContextController(("vertical", (40, 10, 60, 210)))
        self.assertTrue(controller.begin_context_pinch())
        controller.move_context_pinch(500, 180)
        controller.complete_context_pinch()
        self.assertEqual(controller.moves, [(50, 180)])

    def test_non_adjustable_target_falls_back_to_click(self):
        controller = RecordingContextController(None)
        self.assertFalse(controller.begin_context_pinch())
        controller.move_context_pinch(90, 90)
        controller.complete_context_pinch()
        self.assertEqual(controller.moves, [])
        self.assertEqual(controller.mouse_events, [controller.MOUSEEVENTF_LEFTDOWN, controller.MOUSEEVENTF_LEFTUP])

if __name__ == "__main__":
    unittest.main()
