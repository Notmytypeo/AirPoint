import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.application import GestureStatusOverlay, MainWindow
from app.camera_worker import CameraWorker
from app.tuning import normalized_tuning


class GestureStatusOverlayTests(unittest.TestCase):
    def test_target_position_matches_bottom_left_taskbar_anchor(self):
        geometry = QRect(0, 0, 1920, 1080)
        badge_size = QSize(166, 28)

        self.assertEqual(GestureStatusOverlay.target_position(geometry, badge_size), (14, 1042))


class MainWindowTaskbarTests(unittest.TestCase):
    def test_external_launch_restores_hidden_window_through_tray_path(self):
        window = SimpleNamespace(
            isVisible=Mock(return_value=False),
            _show_from_tray=Mock(),
        )

        MainWindow._activate_from_external_launch(window)

        window._show_from_tray.assert_called_once_with()

    def test_external_launch_restores_minimized_window_and_preview(self):
        window = SimpleNamespace(
            isVisible=Mock(return_value=True),
            isMinimized=Mock(return_value=True),
            windowState=Mock(return_value=Qt.WindowMinimized),
            showMaximized=Mock(),
            showNormal=Mock(),
            worker=SimpleNamespace(set_preview_enabled=Mock()),
            raise_=Mock(),
            activateWindow=Mock(),
        )

        MainWindow._activate_from_external_launch(window)

        window.showNormal.assert_called_once_with()
        window.worker.set_preview_enabled.assert_called_once_with(True)
        window.raise_.assert_called_once_with()
        window.activateWindow.assert_called_once_with()

    def test_enabling_control_keeps_main_window_visible(self):
        window = SimpleNamespace(
            control_active=False,
            worker=SimpleNamespace(set_enabled=Mock()),
            _update_activate_style=Mock(),
            _apply_activation_window_behavior=Mock(),
        )
        with patch("app.application.QTimer.singleShot") as delayed_action:
            MainWindow._toggle_control(window)
        self.assertTrue(window.control_active)
        window.worker.set_enabled.assert_called_once_with(True)
        window._apply_activation_window_behavior.assert_called_once_with()
        delayed_action.assert_not_called()

    def test_gesture_activation_keeps_main_window_visible(self):
        window = SimpleNamespace(
            control_active=False,
            _update_activate_style=Mock(),
            _apply_activation_window_behavior=Mock(),
        )
        with patch("app.application.QTimer.singleShot") as delayed_action:
            MainWindow._startup_gesture_activated(window)
        self.assertTrue(window.control_active)
        window._apply_activation_window_behavior.assert_called_once_with()
        delayed_action.assert_not_called()

    def test_activation_visibility_policy_supports_all_three_choices(self):
        keep = SimpleNamespace(
            control_active=True,
            _activation_behavior="keep_open",
            showMinimized=Mock(),
            _hide_to_tray=Mock(return_value=True),
        )
        MainWindow._apply_activation_window_behavior(keep)
        keep.showMinimized.assert_not_called()
        keep._hide_to_tray.assert_not_called()

        minimize = SimpleNamespace(
            control_active=True,
            _activation_behavior="minimize_to_taskbar",
            showMinimized=Mock(),
            _hide_to_tray=Mock(return_value=True),
        )
        MainWindow._apply_activation_window_behavior(minimize)
        minimize.showMinimized.assert_called_once_with()

        tray = SimpleNamespace(
            control_active=True,
            _activation_behavior="hide_to_tray",
            showMinimized=Mock(),
            _hide_to_tray=Mock(return_value=True),
        )
        MainWindow._apply_activation_window_behavior(tray)
        tray._hide_to_tray.assert_called_once_with()
        tray.showMinimized.assert_not_called()

    def test_unavailable_tray_falls_back_to_taskbar_minimize(self):
        window = SimpleNamespace(
            control_active=True,
            _activation_behavior="hide_to_tray",
            showMinimized=Mock(),
            _hide_to_tray=Mock(return_value=False),
        )
        MainWindow._apply_activation_window_behavior(window)
        window.showMinimized.assert_called_once_with()

    def test_disabling_control_does_not_change_window_visibility(self):
        window = SimpleNamespace(
            control_active=True,
            worker=SimpleNamespace(set_enabled=Mock()),
            _update_activate_style=Mock(),
            _apply_activation_window_behavior=Mock(),
        )
        MainWindow._toggle_control(window)
        self.assertFalse(window.control_active)
        window._apply_activation_window_behavior.assert_not_called()

    def test_activation_behavior_migrates_legacy_and_repairs_invalid_value(self):
        class Settings:
            def __init__(self, values):
                self.values = dict(values)

            def value(self, key):
                return self.values.get(key)

            def setValue(self, key, value):
                self.values[key] = value

        legacy_settings = Settings({"minimize_on_activation": True})
        legacy = SimpleNamespace(settings=legacy_settings)
        self.assertEqual(
            MainWindow._load_activation_behavior(legacy),
            "minimize_to_taskbar",
        )
        invalid_settings = Settings({"window/activation_behavior": "disappear"})
        invalid = SimpleNamespace(settings=invalid_settings)
        self.assertEqual(MainWindow._load_activation_behavior(invalid), "keep_open")

    def test_active_tray_mode_close_hides_without_shutdown(self):
        event = SimpleNamespace(ignore=Mock(), accept=Mock())
        window = SimpleNamespace(
            _force_quit=False,
            control_active=True,
            _activation_behavior="hide_to_tray",
            _hide_to_tray=Mock(return_value=True),
            _shutdown=Mock(),
        )
        MainWindow.closeEvent(window, event)
        event.ignore.assert_called_once_with()
        event.accept.assert_not_called()
        window._shutdown.assert_not_called()

    def test_tray_toggle_uses_the_same_activation_policy_path(self):
        window = SimpleNamespace(_toggle_control=Mock())
        MainWindow._toggle_control_from_tray(window)
        window._toggle_control.assert_called_once_with()

    def test_preview_slot_is_acknowledged_even_if_display_fails(self):
        window = SimpleNamespace(
            camera_view=SimpleNamespace(
                set_frame=Mock(side_effect=RuntimeError("paint failed"))
            ),
            worker=SimpleNamespace(acknowledge_preview=Mock()),
        )
        with self.assertRaisesRegex(RuntimeError, "paint failed"):
            MainWindow._display_frame(window, QImage())
        window.worker.acknowledge_preview.assert_called_once_with()

    def test_shutdown_does_not_accept_close_until_worker_stops(self):
        event = SimpleNamespace(ignore=Mock(), accept=Mock())
        window = SimpleNamespace(
            _force_quit=True,
            control_active=True,
            _activation_behavior="keep_open",
            _shutdown_complete=False,
            _shutdown_in_progress=False,
            _shutdown_close_requested=False,
            _shutdown_poll_scheduled=False,
            worker=SimpleNamespace(
                set_enabled=Mock(),
                set_preview_enabled=Mock(),
                stop=Mock(return_value=False),
            ),
            gesture_overlay=SimpleNamespace(close=Mock()),
            _tray_icon=None,
            _show_error=Mock(),
            _update_activate_style=Mock(),
            activate_button=SimpleNamespace(
                setEnabled=Mock(),
                setText=Mock(),
            ),
            _schedule_shutdown_poll=Mock(),
        )
        window._shutdown = lambda: MainWindow._shutdown(window)
        MainWindow.closeEvent(window, event)
        event.ignore.assert_called_once_with()
        event.accept.assert_not_called()
        self.assertFalse(window._shutdown_complete)
        self.assertTrue(window._shutdown_in_progress)
        self.assertTrue(window._shutdown_close_requested)
        window._schedule_shutdown_poll.assert_called_once_with()
        window.activate_button.setEnabled.assert_called_once_with(False)
        window._show_error.assert_called_once()
        window.worker.stop.assert_called_once_with(timeout_ms=0)

    def test_shutdown_poll_finalizes_and_retries_the_close(self):
        window = SimpleNamespace(
            _shutdown_poll_scheduled=True,
            _shutdown_complete=False,
            _shutdown_close_requested=True,
            worker=SimpleNamespace(isRunning=Mock(return_value=False)),
            _finalize_shutdown=Mock(),
            close=Mock(),
        )
        with patch("app.application.QTimer.singleShot") as single_shot:
            MainWindow._poll_shutdown(window)
        window._finalize_shutdown.assert_called_once_with()
        single_shot.assert_called_once_with(0, window.close)

    def test_pointer_profile_migrates_both_historical_speed_floor_values(self):
        class Settings:
            def __init__(self):
                self.values = {
                    "developer/pointer_response_revision": 0,
                    "developer/precision_speed_floor": 0.55,
                }

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        window = SimpleNamespace(settings=Settings())
        MainWindow._repair_pointer_response_profile(window)
        self.assertEqual(
            window.settings.values["developer/precision_speed_floor"],
            0.70,
        )

    def test_normalized_sibling_developer_values_update_controls_and_storage(self):
        class Settings:
            def __init__(self):
                self.values = {}

            def setValue(self, key, value):
                self.values[key] = value

        active = SimpleNamespace(blockSignals=Mock(), setValue=Mock())
        idle = SimpleNamespace(blockSignals=Mock(), setValue=Mock())
        worker = SimpleNamespace(set_tuning=Mock())
        window = SimpleNamespace(
            _developer_tuning=normalized_tuning(
                {"inference_active_fps": 30, "inference_idle_fps": 30}
            ),
            _developer_inputs={
                "inference_active_fps": active,
                "inference_idle_fps": idle,
            },
            settings=Settings(),
            worker=worker,
        )
        MainWindow._developer_value_changed(window, "inference_active_fps", 15)
        self.assertEqual(window._developer_tuning["inference_idle_fps"], 15)
        idle.setValue.assert_called_with(15)
        self.assertEqual(
            window.settings.values["developer/inference_idle_fps"],
            15,
        )
        worker.set_tuning.assert_called_once()


class MainWindowQtIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        existing = QApplication.instance()
        if existing is not None and not isinstance(existing, QApplication):
            raise unittest.SkipTest(
                "A non-GUI QCoreApplication already owns this test process."
            )
        cls.app = existing or QApplication([])

    def test_real_developer_controls_stay_synced_after_coupled_edit(self):
        class MemorySettings:
            def __init__(self):
                self.values = {}

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

            def remove(self, key):
                self.values.pop(key, None)

        settings = MemorySettings()
        with (
            patch("app.application.QSettings", return_value=settings),
            patch("app.application.is_startup_enabled", return_value=False),
            patch.object(GestureStatusOverlay, "show"),
            patch.object(CameraWorker, "start"),
            patch.object(CameraWorker, "stop", return_value=True),
        ):
            window = MainWindow()
            active = window._developer_inputs["inference_active_fps"]
            idle = window._developer_inputs["inference_idle_fps"]
            idle.setValue(30)
            active.setValue(15)
            self.app.processEvents()
            self.assertEqual(active.value(), 15)
            self.assertEqual(idle.value(), 15)
            self.assertEqual(settings.values["developer/inference_idle_fps"], 15)
            window.activation_behavior_select.setCurrentIndex(
                window.activation_behavior_select.findData("hide_to_tray")
            )
            window._set_external_activation_available(False)
            self.assertEqual(window._activation_behavior, "keep_open")
            hide_index = window.activation_behavior_select.findData("hide_to_tray")
            self.assertFalse(
                window.activation_behavior_select.model().item(hide_index).isEnabled()
            )
            window._force_quit = True
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
