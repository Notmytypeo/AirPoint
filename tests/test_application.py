import unittest

from PySide6.QtCore import QRect, QSize

from app.application import GestureStatusOverlay


class GestureStatusOverlayTests(unittest.TestCase):
    def test_target_position_matches_bottom_left_taskbar_anchor(self):
        geometry = QRect(0, 0, 1920, 1080)
        badge_size = QSize(166, 28)

        self.assertEqual(GestureStatusOverlay.target_position(geometry, badge_size), (14, 1042))


if __name__ == "__main__":
    unittest.main()
