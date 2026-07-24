from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - exercised on non-Windows builds
    winreg = None


APP_NAME = "AirPoint"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_supported() -> bool:
    return sys.platform == "win32" and winreg is not None


def startup_command(
    executable: Path | None = None,
    *,
    frozen: bool | None = None,
    project_root: Path | None = None,
) -> str:
    """Build the minimized command stored in the current user's Run key."""
    executable = Path(executable or sys.executable)
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        arguments = [str(executable), "--minimized"]
    else:
        python = executable
        pythonw = python.with_name("pythonw.exe")
        if python.name.lower() == "python.exe" and pythonw.exists():
            python = pythonw
        root = project_root or Path(__file__).resolve().parent.parent
        arguments = [str(python), str(root / "main.py"), "--minimized"]
    return subprocess.list2cmdline(arguments)


def legacy_startup_shortcut() -> Path | None:
    app_data = os.environ.get("APPDATA")
    if not app_data:
        return None
    return Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"


def is_startup_enabled() -> bool:
    if not startup_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _value_type = winreg.QueryValueEx(key, APP_NAME)
            if str(value).strip():
                return True
    except OSError:
        pass
    shortcut = legacy_startup_shortcut()
    return bool(shortcut and shortcut.exists())


def set_startup_enabled(enabled: bool) -> None:
    if not startup_supported():
        raise OSError("Launch at startup is currently available on Windows only.")

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
    else:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass

    # Older AirPoint versions used a Startup-folder shortcut. Remove it when
    # the user changes this setting so Windows never launches two instances.
    shortcut = legacy_startup_shortcut()
    if shortcut and shortcut.exists():
        shortcut.unlink()
