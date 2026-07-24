import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import startup


class StartupTests(unittest.TestCase):
    def test_packaged_command_launches_minimized(self):
        command = startup.startup_command(
            Path(r"C:\Program Files\AirPoint\AirPoint.exe"),
            frozen=True,
        )

        self.assertEqual(command, r'"C:\Program Files\AirPoint\AirPoint.exe" --minimized')

    def test_source_command_prefers_pythonw_and_main_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            python = scripts / "python.exe"
            pythonw = scripts / "pythonw.exe"
            pythonw.touch()

            command = startup.startup_command(
                python,
                frozen=False,
                project_root=root,
            )

        self.assertIn(str(pythonw), command)
        self.assertIn(str(root / "main.py"), command)
        self.assertTrue(command.endswith("--minimized"))

    def test_startup_is_disabled_on_unsupported_platforms(self):
        with patch.object(startup.sys, "platform", "darwin"):
            self.assertFalse(startup.startup_supported())
            self.assertFalse(startup.is_startup_enabled())

    def test_enabling_startup_writes_the_current_command(self):
        key = object()
        key_context = MagicMock()
        key_context.__enter__.return_value = key
        registry = SimpleNamespace(
            HKEY_CURRENT_USER=1,
            KEY_SET_VALUE=2,
            REG_SZ=3,
            CreateKeyEx=MagicMock(return_value=key_context),
            SetValueEx=MagicMock(),
        )

        with (
            patch.object(startup.sys, "platform", "win32"),
            patch.object(startup, "winreg", registry),
            patch.object(startup, "startup_command", return_value="airpoint --minimized"),
            patch.object(startup, "legacy_startup_shortcut", return_value=None),
        ):
            startup.set_startup_enabled(True)

        registry.SetValueEx.assert_called_once_with(
            key,
            startup.APP_NAME,
            0,
            registry.REG_SZ,
            "airpoint --minimized",
        )

    def test_disabling_startup_removes_registry_and_legacy_shortcut(self):
        key = object()
        key_context = MagicMock()
        key_context.__enter__.return_value = key
        registry = SimpleNamespace(
            HKEY_CURRENT_USER=1,
            KEY_SET_VALUE=2,
            OpenKey=MagicMock(return_value=key_context),
            DeleteValue=MagicMock(),
        )

        with tempfile.TemporaryDirectory() as directory:
            shortcut = Path(directory) / "AirPoint.lnk"
            shortcut.touch()
            with (
                patch.object(startup.sys, "platform", "win32"),
                patch.object(startup, "winreg", registry),
                patch.object(startup, "legacy_startup_shortcut", return_value=shortcut),
            ):
                startup.set_startup_enabled(False)

            self.assertFalse(shortcut.exists())

        registry.DeleteValue.assert_called_once_with(key, startup.APP_NAME)


if __name__ == "__main__":
    unittest.main()
