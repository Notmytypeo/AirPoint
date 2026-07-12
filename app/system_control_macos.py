"""macOS input controller using Quartz / CoreGraphics.

Drop-in replacement for the Windows InputController — same public interface,
backed by Apple's CoreGraphics event APIs and Accessibility framework.

Requires: pyobjc-framework-Quartz, pyobjc-framework-ApplicationServices
macOS permissions: Accessibility (System Settings → Privacy & Security → Accessibility)
"""
from __future__ import annotations

import platform
import subprocess
import time


def _lazy_quartz():
    """Import Quartz on first use so the module can be imported on any platform."""
    import Quartz
    return Quartz


def _lazy_appservices():
    import ApplicationServices
    return ApplicationServices


# ── macOS key codes ──────────────────────────────────────────────────
# Virtual key codes used by CGEventCreateKeyboardEvent.
_KC_TAB = 0x30
_KC_SPACE = 0x31
_KC_D = 0x02
_KC_F = 0x03
_KC_F3 = 0x63
_KC_F11 = 0x67
_KC_UP = 0x7E
_KC_DOWN = 0x7F
_KC_LEFT = 0x7B
_KC_RIGHT = 0x7C

# NX media key codes (for volume via system-defined events)
_NX_KEYTYPE_SOUND_UP = 0
_NX_KEYTYPE_SOUND_DOWN = 1

# CGEvent flag masks
_FLAG_CMD = 0x00100000   # kCGEventFlagMaskCommand
_FLAG_SHIFT = 0x00020000  # kCGEventFlagMaskShift
_FLAG_CTRL = 0x00040000   # kCGEventFlagMaskControl
_FLAG_ALT = 0x00080000    # kCGEventFlagMaskAlternate


def disable_background_throttling() -> bool:
    """No-op on macOS — macOS manages this differently via App Nap."""
    return False


def enable_tracking_priority() -> bool:
    """No-op on macOS — not needed for gesture tracking performance."""
    return False


class InputController:
    """macOS input controller using Quartz CoreGraphics events.

    Same public interface as the Windows InputController so that the rest
    of the application works without any changes.
    """

    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("This macOS InputController can only run on macOS.")
        Q = _lazy_quartz()
        self._Q = Q
        self._left_held = False
        self._context_drag_axis: str | None = None
        self._context_drag_bounds: tuple[int, int, int, int] | None = None
        self._context_drag_anchor = (0, 0)
        # Cache the main display ID
        self._main_display = Q.CGMainDisplayID()

    # ── Mouse helpers ────────────────────────────────────────────────

    def _post_mouse(self, event_type: int, x: float, y: float, button: int = 0) -> None:
        Q = self._Q
        point = Q.CGPoint(x, y)
        event = Q.CGEventCreateMouseEvent(None, event_type, point, button)
        Q.CGEventPost(Q.kCGHIDEventTap, event)

    def _cursor_position(self) -> tuple[int, int]:
        """Get current cursor position (top-left origin)."""
        Q = self._Q
        event = Q.CGEventCreate(None)
        point = Q.CGEventGetLocation(event)
        return int(point.x), int(point.y)

    # ── Keyboard helpers ─────────────────────────────────────────────

    def _key(self, key_code: int, key_down: bool = True, flags: int = 0) -> None:
        Q = self._Q
        event = Q.CGEventCreateKeyboardEvent(None, key_code, key_down)
        if flags:
            Q.CGEventSetFlags(event, flags | Q.CGEventGetFlags(event))
        Q.CGEventPost(Q.kCGHIDEventTap, event)

    def _key_tap(self, key_code: int, flags: int = 0) -> None:
        """Press and release a key."""
        self._key(key_code, key_down=True, flags=flags)
        self._key(key_code, key_down=False, flags=flags)

    # ── Public interface (matches Windows InputController) ───────────

    def move(self, x: int, y: int) -> None:
        Q = self._Q
        self._post_mouse(Q.kCGEventMouseMoved, x, y)

    def screen_bounds(self) -> tuple[int, int, int, int]:
        Q = self._Q
        bounds = Q.CGDisplayBounds(self._main_display)
        return (
            int(bounds.origin.x),
            int(bounds.origin.y),
            int(bounds.size.width),
            int(bounds.size.height),
        )

    def center_pointer(self) -> None:
        left, top, width, height = self.screen_bounds()
        self.move(left + width // 2, top + height // 2)

    def left_click(self) -> None:
        Q = self._Q
        x, y = self._cursor_position()
        self._post_mouse(Q.kCGEventLeftMouseDown, x, y, Q.kCGMouseButtonLeft)
        self._post_mouse(Q.kCGEventLeftMouseUp, x, y, Q.kCGMouseButtonLeft)

    def right_click(self) -> None:
        Q = self._Q
        x, y = self._cursor_position()
        self._post_mouse(Q.kCGEventRightMouseDown, x, y, Q.kCGMouseButtonRight)
        self._post_mouse(Q.kCGEventRightMouseUp, x, y, Q.kCGMouseButtonRight)

    def left_down(self) -> None:
        if not self._left_held:
            Q = self._Q
            x, y = self._cursor_position()
            self._post_mouse(Q.kCGEventLeftMouseDown, x, y, Q.kCGMouseButtonLeft)
            self._left_held = True

    def left_up(self) -> None:
        if self._left_held:
            Q = self._Q
            x, y = self._cursor_position()
            self._post_mouse(Q.kCGEventLeftMouseUp, x, y, Q.kCGMouseButtonLeft)
            self._left_held = False

    def volume(self, direction: int) -> None:
        """Change system volume using AppleScript (most reliable method)."""
        script = (
            'set volume output volume ((output volume of (get volume settings)) + 6.25)'
            if direction > 0
            else 'set volume output volume ((output volume of (get volume settings)) - 6.25)'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=2,
            )
        except Exception:
            pass

    def scroll(self, amount: int) -> None:
        Q = self._Q
        wheel_delta = 3 if amount > 0 else -3
        for _ in range(abs(amount)):
            event = Q.CGEventCreateScrollWheelEvent(
                None, Q.kCGScrollEventUnitLine, 1, wheel_delta,
            )
            Q.CGEventPost(Q.kCGHIDEventTap, event)

    def scroll_horizontal(self, amount: int) -> None:
        """Horizontal scroll using CGScrollWheelEvent with two axes."""
        Q = self._Q
        wheel_delta = -3 if amount > 0 else 3
        for _ in range(abs(amount)):
            event = Q.CGEventCreateScrollWheelEvent(
                None, Q.kCGScrollEventUnitLine, 2, 0, wheel_delta,
            )
            Q.CGEventPost(Q.kCGHIDEventTap, event)

    def zoom(self, amount: int) -> None:
        """Zoom via Cmd+scroll (Cmd instead of Ctrl on macOS)."""
        Q = self._Q
        wheel_delta = 3 if amount > 0 else -3
        for _ in range(abs(amount)):
            event = Q.CGEventCreateScrollWheelEvent(
                None, Q.kCGScrollEventUnitLine, 1, wheel_delta,
            )
            Q.CGEventSetFlags(event, _FLAG_CMD)
            Q.CGEventPost(Q.kCGHIDEventTap, event)

    def switch_application(self, direction: int) -> None:
        """Cmd+Tab (next) or Cmd+Shift+Tab (previous) on macOS."""
        flags = _FLAG_CMD
        if direction < 0:
            flags |= _FLAG_SHIFT
        self._key_tap(_KC_TAB, flags=flags)

    def task_view(self) -> None:
        """Open Mission Control (Ctrl+Up on macOS)."""
        self._key_tap(_KC_UP, flags=_FLAG_CTRL)

    def show_desktop(self) -> None:
        """Show Desktop via F11."""
        self._key_tap(_KC_F11)

    # ── Context-aware pinch (slider/scrollbar detection) ─────────────

    def _detect_adjustable_axis(self, x: int, y: int) -> tuple[str, tuple[int, int, int, int]] | None:
        """Detect sliders/scrollbars under the cursor via macOS Accessibility API."""
        try:
            Q = self._Q
            AS = _lazy_appservices()
            system_element = AS.AXUIElementCreateSystemWide()
            err, element = AS.AXUIElementCopyElementAtPosition(
                system_element, float(x), float(y), None,
            )
            if err != 0 or element is None:
                return None

            adjustable_roles = {"AXSlider", "AXScrollBar"}
            for _ in range(6):
                err, role = AS.AXUIElementCopyAttributeValue(element, "AXRole", None)
                if err == 0 and role in adjustable_roles:
                    err, pos = AS.AXUIElementCopyAttributeValue(element, "AXPosition", None)
                    err2, size = AS.AXUIElementCopyAttributeValue(element, "AXSize", None)
                    if err == 0 and err2 == 0:
                        px, py = int(pos.x), int(pos.y)
                        sw, sh = int(size.width), int(size.height)
                        if sw <= 0 or sh <= 0:
                            return None
                        axis = "horizontal" if sw >= sh else "vertical"
                        return axis, (px, py, px + sw, py + sh)
                    return None
                err, parent = AS.AXUIElementCopyAttributeValue(element, "AXParent", None)
                if err != 0 or parent is None:
                    break
                element = parent
        except Exception:
            pass
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

    def release_all(self) -> None:
        self.cancel_context_pinch()
        self.left_up()
