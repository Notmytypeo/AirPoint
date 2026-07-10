from __future__ import annotations

import ctypes
from ctypes import wintypes
import platform


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUT_UNION)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


def disable_background_throttling() -> bool:
    """Keep gesture inference at HighQoS when the window is minimized."""
    if platform.system() != "Windows":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.SetProcessInformation.restype = wintypes.BOOL
        process_power_throttling = 4
        execution_speed = 0x1
        ignore_timer_resolution = 0x4
        state = PROCESS_POWER_THROTTLING_STATE(
            Version=1,
            ControlMask=execution_speed | ignore_timer_resolution,
            StateMask=0,
        )
        return bool(
            kernel32.SetProcessInformation(
                kernel32.GetCurrentProcess(),
                process_power_throttling,
                ctypes.byref(state),
                ctypes.sizeof(state),
            )
        )
    except (AttributeError, OSError):
        return False


def enable_tracking_priority() -> bool:
    """Favor camera/inference work over background tasks, including on battery."""
    if platform.system() != "Windows":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        kernel32.SetThreadPriority.restype = wintypes.BOOL
        above_normal_priority_class = 0x00008000
        thread_priority_above_normal = 1
        process_ok = kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), above_normal_priority_class)
        thread_ok = kernel32.SetThreadPriority(kernel32.GetCurrentThread(), thread_priority_above_normal)
        return bool(process_ok and thread_ok)
    except (AttributeError, OSError):
        return False


class InputController:
    """Small Windows SendInput wrapper with no extra runtime dependency."""

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    MOUSEEVENTF_ABSOLUTE = 0x8000
    KEYEVENTF_KEYUP = 0x0002
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF
    VK_CONTROL = 0x11

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("AirPoint input control currently supports Windows only.")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._left_held = False
        self._context_drag_axis: str | None = None
        self._context_drag_bounds: tuple[int, int, int, int] | None = None
        self._context_drag_anchor = (0, 0)

    def _mouse(self, flags: int, x: int = 0, y: int = 0, mouse_data: int = 0) -> None:
        event = INPUT(type=self.INPUT_MOUSE, mi=MOUSEINPUT(x, y, ctypes.c_ulong(mouse_data).value, flags, 0, None))
        self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))

    def _key(self, key: int, key_up: bool = False) -> None:
        flags = self.KEYEVENTF_KEYUP if key_up else 0
        event = INPUT(type=self.INPUT_KEYBOARD, ki=KEYBDINPUT(key, 0, flags, 0, None))
        self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))

    def move(self, x: int, y: int) -> None:
        virtual_x = self.user32.GetSystemMetrics(76)
        virtual_y = self.user32.GetSystemMetrics(77)
        virtual_w = max(1, self.user32.GetSystemMetrics(78) - 1)
        virtual_h = max(1, self.user32.GetSystemMetrics(79) - 1)
        absolute_x = round((x - virtual_x) * 65535 / virtual_w)
        absolute_y = round((y - virtual_y) * 65535 / virtual_h)
        self._mouse(self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE | self.MOUSEEVENTF_VIRTUALDESK, absolute_x, absolute_y)

    def screen_bounds(self) -> tuple[int, int, int, int]:
        return (
            self.user32.GetSystemMetrics(76),
            self.user32.GetSystemMetrics(77),
            self.user32.GetSystemMetrics(78),
            self.user32.GetSystemMetrics(79),
        )

    def center_pointer(self) -> None:
        left, top, width, height = self.screen_bounds()
        self.move(left + width // 2, top + height // 2)

    def left_click(self) -> None:
        self._mouse(self.MOUSEEVENTF_LEFTDOWN)
        self._mouse(self.MOUSEEVENTF_LEFTUP)

    def right_click(self) -> None:
        self._mouse(self.MOUSEEVENTF_RIGHTDOWN)
        self._mouse(self.MOUSEEVENTF_RIGHTUP)

    def left_down(self) -> None:
        if not self._left_held:
            self._mouse(self.MOUSEEVENTF_LEFTDOWN)
            self._left_held = True

    def left_up(self) -> None:
        if self._left_held:
            self._mouse(self.MOUSEEVENTF_LEFTUP)
            self._left_held = False

    def _cursor_position(self) -> tuple[int, int]:
        point = POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def _detect_adjustable_axis(self, x: int, y: int) -> tuple[str, tuple[int, int, int, int]] | None:
        try:
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                control = auto.ControlFromPoint(x, y)
                for _ in range(6):
                    if control is None:
                        break
                    if control.ControlType in (
                        auto.ControlType.SliderControl,
                        auto.ControlType.ScrollBarControl,
                        auto.ControlType.ThumbControl,
                    ):
                        rectangle = control.BoundingRectangle
                        if rectangle.width <= 0 or rectangle.height <= 0:
                            return None
                        orientation = control.Orientation
                        if orientation == auto.OrientationType.Horizontal:
                            axis = "horizontal"
                        elif orientation == auto.OrientationType.Vertical:
                            axis = "vertical"
                        else:
                            axis = "horizontal" if rectangle.width >= rectangle.height else "vertical"
                        return axis, (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom)
                    control = control.GetParentControl()
                return self._detect_msaa_axis(x, y)
        except Exception:
            return None
        return None

    @staticmethod
    def _detect_msaa_axis(x: int, y: int) -> tuple[str, tuple[int, int, int, int]] | None:
        try:
            import comtypes.client
            from comtypes import POINTER
            from comtypes.automation import VARIANT

            comtypes.client.GetModule("oleacc.dll")
            from comtypes.gen.Accessibility import IAccessible

            oleacc = ctypes.OleDLL("oleacc")
            oleacc.AccessibleObjectFromPoint.argtypes = [
                POINT,
                POINTER(POINTER(IAccessible)),
                POINTER(VARIANT),
            ]
            oleacc.AccessibleObjectFromPoint.restype = wintypes.HRESULT
            accessible = POINTER(IAccessible)()
            child = VARIANT()
            result = oleacc.AccessibleObjectFromPoint(POINT(x, y), ctypes.byref(accessible), ctypes.byref(child))
            if result != 0 or not accessible:
                return None

            role_scrollbar = 0x03
            role_slider = 0x33
            for _ in range(6):
                role = accessible.accRole(child)
                if role in (role_scrollbar, role_slider):
                    left, top, width, height = accessible.accLocation(child)
                    if width <= 0 or height <= 0:
                        return None
                    axis = "horizontal" if width >= height else "vertical"
                    return axis, (left, top, left + width, top + height)
                parent = accessible.accParent
                if not parent:
                    break
                accessible = parent.QueryInterface(IAccessible)
                child = VARIANT(0)
        except Exception:
            return None
        return None

    def begin_context_pinch(self) -> bool:
        x, y = self._cursor_position()
        target = self._detect_adjustable_axis(x, y)
        self._context_drag_axis = None
        self._context_drag_bounds = None
        self._context_drag_anchor = (x, y)
        if target is None:
            return False
        self._context_drag_axis, self._context_drag_bounds = target
        self.left_down()
        return True

    def move_context_pinch(self, x: int, y: int) -> bool:
        if self._context_drag_axis is None or self._context_drag_bounds is None:
            return False
        left, top, right, bottom = self._context_drag_bounds
        if self._context_drag_axis == "horizontal":
            x = max(left, min(right - 1, x))
            y = self._context_drag_anchor[1]
        else:
            x = self._context_drag_anchor[0]
            y = max(top, min(bottom - 1, y))
        self.move(x, y)
        return True

    def complete_context_pinch(self) -> None:
        if self._context_drag_axis is not None:
            self.left_up()
            self._context_drag_axis = None
            self._context_drag_bounds = None
        else:
            self.left_click()

    def cancel_context_pinch(self) -> None:
        self.left_up()
        self._context_drag_axis = None
        self._context_drag_bounds = None

    def volume(self, direction: int) -> None:
        key = self.VK_VOLUME_UP if direction > 0 else self.VK_VOLUME_DOWN
        self._key(key)
        self._key(key, key_up=True)

    def scroll(self, amount: int) -> None:
        wheel_delta = 120 if amount > 0 else -120
        for _ in range(abs(amount)):
            self._mouse(self.MOUSEEVENTF_WHEEL, mouse_data=wheel_delta)

    def zoom(self, amount: int) -> None:
        wheel_delta = 120 if amount > 0 else -120
        self._key(self.VK_CONTROL)
        try:
            for _ in range(abs(amount)):
                self._mouse(self.MOUSEEVENTF_WHEEL, mouse_data=wheel_delta)
        finally:
            self._key(self.VK_CONTROL, key_up=True)

    def release_all(self) -> None:
        self.cancel_context_pinch()
        self.left_up()
