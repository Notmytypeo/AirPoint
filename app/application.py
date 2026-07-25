from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QLockFile, QSettings, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QVariantAnimation, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QImage, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
    QSystemTrayIcon,
    QGraphicsOpacityEffect,
)

from .camera_worker import CameraWorker
from .startup import is_startup_enabled, set_startup_enabled, startup_supported
from .styles import APP_STYLE
from .system_control import disable_background_throttling
from .single_instance import ActivationServer, request_activation
from .tuning import DEVELOPER_PARAMETERS, normalized_tuning


def label(text: str = "", object_name: str = "") -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def asset_path(name: str) -> Path:
    """Resolve packaged and source-tree assets from the same location."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "assets" / name
    return Path(__file__).with_name("assets") / name


class CameraView(QLabel):
    def __init__(self) -> None:
        super().__init__("Starting camera…")
        self.setObjectName("cameraView")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image: QImage | None = None

    def set_frame(self, image: QImage) -> None:
        self._image = image
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._image is None:
            return
        pixmap = QPixmap.fromImage(self._image)
        # Preserve the full camera frame; hand gestures at the edges must not
        # disappear because a preview panel crops or zooms the image.
        self.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.FastTransformation))


class GestureRow(QFrame):
    def __init__(self, symbol: str, name: str, hint: str) -> None:
        super().__init__()
        self.setObjectName("gestureRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)
        icon = label(symbol, "gestureIcon")
        icon.setFixedSize(30, 30)
        icon.setAlignment(Qt.AlignCenter)
        row.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(name, "gestureName"))
        self.hint_label = label(hint, "gestureHint")
        text.addWidget(self.hint_label)
        row.addLayout(text, 1)

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)


class GestureStatusOverlay(QLabel):
    """Click-through gesture badge anchored over the primary taskbar."""

    LEFT_MARGIN = 14
    BOTTOM_MARGIN = 10
    TOPMOST_REFRESH_MS = 200

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(28)
        self.setStyleSheet(
            """
            QLabel {
                background: #1E1B4B;
                border: 1px solid rgba(99, 102, 241, 0.65);
                border-radius: 8px;
                padding: 0 14px;
                color: #C7D2FE;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )
        self.set_status(text)

        app = QApplication.instance()
        if app is not None:
            app.primaryScreenChanged.connect(self._reposition)
            app.applicationStateChanged.connect(self._keep_on_top)

        # Windows Explorer periodically promotes the taskbar within the
        # topmost-window band when focus changes. Refreshing our no-activate
        # z-order keeps the badge visible without intercepting user input.
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(self.TOPMOST_REFRESH_MS)
        self._topmost_timer.timeout.connect(self._keep_on_top)
        self._topmost_timer.start()

    @classmethod
    def target_position(cls, screen_geometry, badge_size):
        """Return the bottom-left taskbar position used by the status badge."""
        return (
            screen_geometry.left() + cls.LEFT_MARGIN,
            screen_geometry.bottom() - cls.BOTTOM_MARGIN - badge_size.height() + 1,
        )

    def set_status(self, text: str) -> None:
        if self.text() != text:
            super().setText(text)
            self.adjustSize()
        self._reposition()

    def _reposition(self, *_args) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        x, y = self.target_position(screen.geometry(), self.size())
        self.move(x, y)

    def _keep_on_top(self, *_args) -> None:
        if not self.isVisible():
            return
        self._reposition()
        self.raise_()
        if sys.platform == "win32":
            # HWND_TOPMOST plus SWP_NOACTIVATE keeps the badge above the
            # taskbar without pulling focus away from the current app.
            try:
                import ctypes

                ctypes.windll.user32.SetWindowPos(
                    ctypes.c_void_p(int(self.winId())),
                    ctypes.c_void_p(-1),
                    0,
                    0,
                    0,
                    0,
                    0x0001 | 0x0002 | 0x0010 | 0x0040 | 0x0200,
                )
            except (AttributeError, OSError):
                pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._keep_on_top()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AirPoint · Gesture Control")
        self.setWindowIcon(QIcon(str(asset_path("airpoint-logo.svg"))))
        self.setMinimumSize(1160, 800)
        self.resize(1380, 900)
        self.settings = QSettings("AirPoint", "GestureControl")
        self._repair_unsafe_pinch_profile()
        self._repair_handedness_default()
        self._repair_pointer_response_profile()
        self._repair_swipe_pose_profile()
        self._activation_behavior = self._load_activation_behavior()
        # Load theme setting (default to True: dark mode)
        saved_theme_value = self.settings.value("dark_mode", True)
        self.dark_mode = saved_theme_value if isinstance(saved_theme_value, bool) else str(saved_theme_value).lower() == "true"

        self.control_active = False
        self._last_paused = False
        self._developer_tuning = self._load_developer_tuning()
        self._developer_inputs: dict[str, QDoubleSpinBox | QCheckBox] = {}
        self._developer_cards: dict[str, QFrame] = {}
        self._developer_group_headings: dict[str, QLabel] = {}
        self._focus_updating = False
        self._startup_updating = False
        self._last_hand_state: tuple[bool, bool] | None = None
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_toggle_action: QAction | None = None
        self._tray_notice_shown = False
        self._restore_maximized = False
        self._external_activation_available = True
        self._force_quit = False
        self._shutdown_complete = False
        self._shutdown_in_progress = False
        self._shutdown_close_requested = False
        self._shutdown_poll_scheduled = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_content(), 1)
        self._apply_theme()
        self.gesture_overlay = GestureStatusOverlay(self.gesture_status.text())
        self.gesture_overlay.show()

        self.worker = CameraWorker()
        self.worker.frame_ready.connect(self._display_frame)
        self.worker.telemetry.connect(self._update_telemetry)
        self.worker.gesture_changed.connect(self._gesture_changed)
        self.worker.error.connect(self._show_error)
        self.worker.model_progress.connect(self._model_progress)
        self.worker.paused_changed.connect(self._paused_changed)
        self.worker.startup_activated.connect(self._startup_gesture_activated)
        self.worker.focus_locked.connect(self._focus_locked_by_camera)

        saved_sensitivity = int(self.settings.value("sensitivity", 100))
        saved_camera = int(self.settings.value("camera", 0))
        saved_swap_value = self.settings.value("swap_hands", True)
        saved_swap = saved_swap_value if isinstance(saved_swap_value, bool) else str(saved_swap_value).lower() == "true"
        saved_left_value = self.settings.value("left_handed", False)
        saved_left = saved_left_value if isinstance(saved_left_value, bool) else str(saved_left_value).lower() == "true"
        saved_autofocus_value = self.settings.value("autofocus", True)
        saved_autofocus = saved_autofocus_value if isinstance(saved_autofocus_value, bool) else str(saved_autofocus_value).lower() == "true"
        saved_focus = max(0, min(255, int(self.settings.value("manual_focus", 128))))
        saved_focus_lock_value = self.settings.value("focus_lock", False)
        saved_focus_lock = saved_focus_lock_value if isinstance(saved_focus_lock_value, bool) else str(saved_focus_lock_value).lower() == "true"
        self.sensitivity.setValue(saved_sensitivity)
        self.camera_select.setCurrentIndex(max(0, min(2, saved_camera)))
        self.swap_hands.setChecked(saved_swap)
        self.left_handed.setChecked(saved_left)
        self._focus_updating = True
        self.autofocus.setChecked(saved_autofocus and not saved_focus_lock)
        self.manual_focus.setValue(saved_focus)
        self.focus_lock.setChecked(saved_focus_lock)
        self._focus_updating = False
        self._startup_updating = True
        self.launch_at_startup.setChecked(is_startup_enabled())
        self._startup_updating = False
        self._refresh_focus_controls()
        self._sensitivity_changed(saved_sensitivity)
        self.worker.set_camera(self.camera_select.currentIndex())
        self.worker.set_swap_hands(saved_swap)
        self.worker.set_left_handed(saved_left)
        self.worker.set_focus(self.autofocus.isChecked(), self.manual_focus.value(), self.focus_lock.isChecked())
        self.worker.set_tuning(self._developer_tuning)
        # Let run() show and register the main window with the Windows taskbar
        # before the packaged MediaPipe/OpenCV imports begin on the worker.
        # Those imports can briefly monopolize startup on a cold executable.
        QTimer.singleShot(0, self.worker.start)

    def _load_activation_behavior(self) -> str:
        """Load a stable setting while migrating the former boolean option."""
        allowed = {"keep_open", "minimize_to_taskbar", "hide_to_tray"}
        saved = self.settings.value("window/activation_behavior")
        if saved is None:
            legacy = self.settings.value("minimize_on_activation")
            if legacy is None:
                behavior = "keep_open"
            else:
                legacy_enabled = legacy if isinstance(legacy, bool) else str(legacy).lower() == "true"
                behavior = "minimize_to_taskbar" if legacy_enabled else "keep_open"
        else:
            behavior = str(saved)
        if behavior not in allowed:
            behavior = "keep_open"
        self.settings.setValue("window/activation_behavior", behavior)
        self.settings.setValue("window/activation_behavior_revision", 1)
        return behavior

    def _repair_unsafe_pinch_profile(self) -> None:
        """Migrate only stale strict pinch values from the 3D-only revision."""
        revision = int(self.settings.value("developer/pinch_profile_revision", 0))
        if revision >= 3:
            return
        safe_minimums = {
            "pinch_deep_contact": 0.30,
            "pinch_contact": 0.34,
            "pinch_confirm": 0.32,
            "pinch_hold_release": 0.50,
            "pinch_alpha_contact": 0.70,
        }
        for key, safe_value in safe_minimums.items():
            saved = self.settings.value(f"developer/{key}")
            try:
                current = float(saved)
            except (TypeError, ValueError):
                continue
            if current < safe_value:
                self.settings.setValue(f"developer/{key}", safe_value)
        self.settings.setValue("developer/pinch_profile_revision", 3)

    def _repair_handedness_default(self) -> None:
        """Migrate the old, inverted mirrored-camera default once.

        The camera feed is already mirrored before MediaPipe sees it, so
        MediaPipe's original handedness is correct. Users can still opt in to
        Swap L/R if a specific external camera requires it.
        """
        revision = int(self.settings.value("handedness_mapping_revision", 0))
        if revision < 2:
            self.settings.setValue("swap_hands", True)
            self.settings.setValue("handedness_mapping_revision", 2)

    def _repair_pointer_response_profile(self) -> None:
        """Update only untouched legacy defaults to the lower-latency profile."""
        revision = int(self.settings.value("developer/pointer_response_revision", 0))
        if revision >= 5:
            return
        legacy_to_faster = (
            ("pointer_min_cutoff", 0.70, 0.90),
            ("pointer_beta", 0.90, 1.15),
            ("prediction_cap", 0.014, 0.018),
            # Keep both historical steps: an untouched 0.55 profile migrates
            # through 0.65 to the current 0.70 default.
            ("precision_speed_floor", 0.55, 0.65),
            ("precision_speed_floor", 0.65, 0.70),
            ("pointer_confidence_floor", 0.45, 0.25),
            ("inference_clahe_clip", 1.60, 0.00),
            ("precision_step", 0.012, 0.013),
            ("two_finger_dead_zone", 0.024, 0.018),
            ("pinch_alpha_contact", 0.78, 0.90),
            ("pinch_3d_blend", 0.15, 0.08),
            ("click_settle_delay", 0.050, 0.025),
            ("gesture_settle_delay", 0.10, 0.04),
        )
        for key, legacy_value, improved_value in legacy_to_faster:
            saved = self.settings.value(f"developer/{key}")
            if saved is None:
                self.settings.setValue(f"developer/{key}", improved_value)
                continue
            try:
                if abs(float(saved) - legacy_value) < 1e-6:
                    self.settings.setValue(f"developer/{key}", improved_value)
            except (TypeError, ValueError):
                pass
        if self.settings.value("developer/precision_release_seconds") is None:
            self.settings.setValue("developer/precision_release_seconds", 0.07)
        self.settings.setValue("developer/pointer_response_revision", 5)

    def _repair_swipe_pose_profile(self) -> None:
        """Migrate only untouched 1.4.0 swipe-pose defaults.

        The former thresholds expected an unusually wide finger fan and a
        tightly tucked thumb. Real hands commonly keep the three raised
        fingers closer together and the thumb relaxed, so those defaults made
        a valid gesture appear disabled. Explicitly customized values are
        preserved.
        """
        revision = int(self.settings.value("developer/swipe_pose_revision", 0))
        if revision >= 1:
            return
        legacy_to_reliable = (
            ("swipe_extension_angle", 118.0, 108.0),
            ("swipe_thumb_fold_limit", 1.45, 1.85),
            ("swipe_min_spread", 0.85, 0.42),
        )
        for key, legacy_value, reliable_value in legacy_to_reliable:
            saved = self.settings.value(f"developer/{key}")
            if saved is None:
                continue
            try:
                if abs(float(saved) - legacy_value) < 1e-6:
                    self.settings.setValue(f"developer/{key}", reliable_value)
            except (TypeError, ValueError):
                pass
        self.settings.setValue("developer/swipe_pose_revision", 1)

    def _load_developer_tuning(self) -> dict[str, float]:
        saved_values: dict[str, float] = {}
        for parameter in DEVELOPER_PARAMETERS:
            saved = self.settings.value(f"developer/{parameter.key}")
            if saved is None:
                continue
            try:
                saved_values[parameter.key] = float(saved)
            except (TypeError, ValueError):
                continue
        normalized = normalized_tuning(saved_values)
        # Persist any relational repairs so the controls, storage, and live
        # worker all expose the exact same effective values.
        for key, value in normalized.items():
            self.settings.setValue(f"developer/{key}", value)
        return normalized

    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebarPanel")
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(322)
        
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(6, 0, 6, 16)
        layout.setSpacing(10)
        
        self.activation_card = self._build_activation_card()
        self.setup_card = self._build_setup_card()
        self.sensitivity_card = self._build_sensitivity_card()
        
        for card in (self.activation_card, self.setup_card, self.sensitivity_card):
            card.setFixedWidth(310)
            
        layout.addWidget(self.activation_card)
        layout.addWidget(self.setup_card)
        layout.addWidget(self.sensitivity_card)
        
        tabs_layout = QVBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(8)
        
        self.workspace_tab = QPushButton("Workspace")
        self.workspace_tab.setObjectName("workspaceTab")
        self.workspace_tab.setProperty("selected", True)
        self.workspace_tab.clicked.connect(lambda: self._switch_tab(0))
        
        self.developer_tab = QPushButton("Developer calibration")
        self.developer_tab.setObjectName("developerTab")
        self.developer_tab.setProperty("selected", False)
        self.developer_tab.clicked.connect(lambda: self._switch_tab(1))
        
        tabs_layout.addWidget(self.workspace_tab)
        tabs_layout.addWidget(self.developer_tab)
        layout.addLayout(tabs_layout)
        
        layout.addStretch(1)
        
        return self.sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.sidebar_toggle = QPushButton("☰")
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setCheckable(True)
        self.sidebar_toggle.setChecked(True)
        self.sidebar_toggle.setFixedSize(38, 38)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        header.addWidget(self.sidebar_toggle, 0, Qt.AlignVCenter)

        logo = QLabel()
        logo.setObjectName("titleLogo")
        logo.setPixmap(QPixmap(str(asset_path("airpoint-logo.svg"))))
        logo.setScaledContents(True)
        logo.setFixedSize(38, 38)
        header.addWidget(logo, 0, Qt.AlignVCenter)

        titles_widget = QWidget()
        titles_layout = QVBoxLayout(titles_widget)
        titles_layout.setContentsMargins(0, 0, 0, 0)
        titles_layout.setSpacing(2)
        titles_layout.addWidget(label("AirPoint Control", "title"))
        self.pointer_subtitle = label("Right index finger controls the pointer.", "subtitle")
        titles_layout.addWidget(self.pointer_subtitle)
        header.addWidget(titles_widget, 0, Qt.AlignVCenter)

        header.addStretch()

        self.theme_toggle = QPushButton()
        self.theme_toggle.setObjectName("themeToggle")
        self.theme_toggle.setFixedSize(38, 38)
        self.theme_toggle.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_toggle, 0, Qt.AlignVCenter)

        self.fps_label = label("WARMING UP", "performancePill")
        header.addWidget(self.fps_label, 0, Qt.AlignVCenter)

        layout.addLayout(header)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_workspace_page())
        self.pages.addWidget(self._build_developer_page())
        body_layout.addWidget(self.pages, 1)

        layout.addLayout(body_layout, 1)

        return content

    def _toggle_sidebar(self, checked: bool) -> None:
        if not hasattr(self, "_sidebar_anim"):
            self._sidebar_anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
            self._sidebar_anim.setDuration(250)
            self._sidebar_anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        self._sidebar_anim.stop()
        if checked:
            self.sidebar.show()
            self._sidebar_anim.setStartValue(self.sidebar.width())
            self._sidebar_anim.setEndValue(322)
            self._sidebar_anim.start()
        else:
            self._sidebar_anim.setStartValue(self.sidebar.width())
            self._sidebar_anim.setEndValue(0)
            
            def on_finished():
                if not self.sidebar_toggle.isChecked():
                    self.sidebar.hide()
            try:
                self._sidebar_anim.finished.disconnect()
            except TypeError:
                pass
            self._sidebar_anim.finished.connect(on_finished)
            self._sidebar_anim.start()

    def _toggle_theme(self) -> None:
        # Create full-screen screenshot overlay for smooth cross-fade transition
        screenshot = self.grab()
        overlay = QLabel(self)
        overlay.setPixmap(screenshot)
        overlay.setGeometry(self.rect())
        overlay.show()
        overlay.raise_()
        
        # Apply the theme change on the actual window underneath
        self.dark_mode = not self.dark_mode
        self.settings.setValue("dark_mode", self.dark_mode)
        self._apply_theme()
        
        # Create opacity fade-out animation for the overlay
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        
        self._theme_anim = QPropertyAnimation(effect, b"opacity")
        self._theme_anim.setDuration(400)
        self._theme_anim.setStartValue(1.0)
        self._theme_anim.setEndValue(0.0)
        self._theme_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._theme_anim.finished.connect(overlay.deleteLater)
        self._theme_anim.start()

    def _apply_theme(self) -> None:
        from .styles import APP_STYLE, LIGHT_STYLE
        if self.dark_mode:
            QApplication.instance().setStyleSheet(APP_STYLE)
            self.theme_toggle.setText("☀️")
            self.theme_toggle.setToolTip("Switch to light mode")
        else:
            QApplication.instance().setStyleSheet(LIGHT_STYLE)
            self.theme_toggle.setText("🌙")
            self.theme_toggle.setToolTip("Switch to dark mode")

    def _switch_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.workspace_tab.setProperty("selected", index == 0)
        self.developer_tab.setProperty("selected", index == 1)
        self.workspace_tab.style().unpolish(self.workspace_tab)
        self.workspace_tab.style().polish(self.workspace_tab)
        self.developer_tab.style().unpolish(self.developer_tab)
        self.developer_tab.style().polish(self.developer_tab)

    def _build_workspace_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.error_frame = QFrame()
        self.error_frame.setObjectName("errorFrame")
        error_row = QHBoxLayout(self.error_frame)
        error_row.setContentsMargins(12, 8, 8, 8)
        error_row.setSpacing(8)
        self.error_text = label("", "errorText")
        self.error_text.setWordWrap(True)
        error_row.addWidget(self.error_text, 1)
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setObjectName("errorDismiss")
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.clicked.connect(self.error_frame.hide)
        error_row.addWidget(dismiss_btn, 0, Qt.AlignTop)
        self.error_frame.hide()
        layout.addWidget(self.error_frame)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("cameraStage")
        self.preview_card.setProperty("active", False)
        self.preview_card.setProperty("paused", False)
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 14)
        preview_layout.setSpacing(12)
        stage_header = QHBoxLayout()
        stage_header.setContentsMargins(0, 0, 0, 0)
        stage_header.setSpacing(8)
        
        self.stage_title = label("Live Camera", "stageTitle")
        stage_header.addWidget(self.stage_title, 0, Qt.AlignVCenter)
        
        self.recording_dot = QLabel()
        self.recording_dot.setObjectName("recordingDot")
        self.recording_dot.setFixedSize(10, 10)
        self.recording_dot.hide()
        stage_header.addWidget(self.recording_dot, 0, Qt.AlignVCenter)
        
        # Setup blinking animation for red recording dot
        effect = QGraphicsOpacityEffect(self.recording_dot)
        self.recording_dot.setGraphicsEffect(effect)
        
        self.dot_anim_group = QSequentialAnimationGroup(self)
        
        fade_out = QPropertyAnimation(effect, b"opacity")
        fade_out.setDuration(600)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.1)
        fade_out.setEasingCurve(QEasingCurve.InOutQuad)
        
        fade_in = QPropertyAnimation(effect, b"opacity")
        fade_in.setDuration(600)
        fade_in.setStartValue(0.1)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.dot_anim_group.addAnimation(fade_out)
        self.dot_anim_group.addAnimation(fade_in)
        self.dot_anim_group.setLoopCount(-1)
        
        stage_header.addStretch(1)
        
        # Middle status pill
        self.gesture_status = label("Starting camera", "gesturePill")
        self.gesture_status.setAlignment(Qt.AlignCenter)
        stage_header.addWidget(self.gesture_status, 0, Qt.AlignVCenter)
        
        stage_header.addStretch(1)
        
        # Right side camera badge
        self.camera_badge = label("CAMERA 1", "cameraBadge")
        stage_header.addWidget(self.camera_badge, 0, Qt.AlignVCenter)
        preview_layout.addLayout(stage_header)
        
        self.camera_view = CameraView()
        preview_layout.addWidget(self.camera_view, 1)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(6, 4, 6, 4)
        self.right_status = label("●  Right hand", "handOff")
        self.left_status = label("●  Left hand", "handOff")
        status_row.addStretch()
        status_row.addWidget(self.left_status)
        status_row.addSpacing(13)
        status_row.addWidget(self.right_status)
        status_row.addStretch()
        preview_layout.addLayout(status_row)

        layout.addWidget(self.preview_card, 1)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.hide()
        layout.addWidget(self.download_progress)
        return content

    def _build_activation_card(self) -> QFrame:
        self.activation_card = QFrame()
        self.activation_card.setObjectName("activationCard")
        self.activation_card.setProperty("active", False)
        self.activation_card.setProperty("paused", False)
        layout = QVBoxLayout(self.activation_card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(label("Gesture control", "sectionTitle"))
        layout.addWidget(label("Start or pause hand control", "muted"))
        layout.addWidget(label("When control starts", "muted"))
        self.activation_behavior_select = QComboBox()
        self.activation_behavior_select.addItem("Keep window open", "keep_open")
        self.activation_behavior_select.addItem("Minimize to taskbar", "minimize_to_taskbar")
        self.activation_behavior_select.addItem("Hide to notification area", "hide_to_tray")
        selected = self.activation_behavior_select.findData(self._activation_behavior)
        self.activation_behavior_select.setCurrentIndex(max(0, selected))
        self.activation_behavior_select.setToolTip(
            "Choose what happens to this window after hand control becomes active"
        )
        self.activation_behavior_select.currentIndexChanged.connect(
            self._activation_behavior_changed
        )
        layout.addWidget(self.activation_behavior_select)
        layout.addStretch()
        self.activate_button = QPushButton("Enable control")
        self.activate_button.setObjectName("primary")
        self.activate_button.clicked.connect(self._toggle_control)
        layout.addWidget(self.activate_button)
        return self.activation_card

    def _build_setup_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("controlCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        top = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(1)
        copy.addWidget(label("Camera", "sectionTitle"))
        copy.addWidget(label("Input and hand preference", "muted"))
        top.addLayout(copy)
        top.addStretch()
        self.camera_select = QComboBox()
        self.camera_select.addItems(["Camera 1", "Camera 2", "Camera 3"])
        self.camera_select.setMinimumWidth(112)
        self.camera_select.currentIndexChanged.connect(self._camera_changed)
        top.addWidget(self.camera_select)
        layout.addLayout(top)
        preferences = QHBoxLayout()
        preferences.setSpacing(16)
        self.swap_hands = QCheckBox("Swap L/R")
        self.swap_hands.setToolTip("Reverse the left and right labels for mirrored camera drivers")
        self.swap_hands.toggled.connect(self._swap_hands_changed)
        preferences.addWidget(self.swap_hands)
        self.left_handed = QCheckBox("Left-handed")
        self.left_handed.setToolTip("Use the left hand for pointer and click gestures, and the right hand for support gestures")
        self.left_handed.toggled.connect(self._left_handed_changed)
        preferences.addWidget(self.left_handed)
        preferences.addStretch()
        layout.addLayout(preferences)

        focus_row = QHBoxLayout()
        focus_row.setSpacing(12)
        self.autofocus = QCheckBox("Auto focus")
        self.autofocus.setToolTip("Let the camera continuously adjust lens focus")
        self.autofocus.toggled.connect(self._autofocus_changed)
        focus_row.addWidget(self.autofocus)
        self.focus_lock = QCheckBox("Lock focus")
        self.focus_lock.setToolTip("Freeze the lens at its current focus distance")
        self.focus_lock.toggled.connect(self._focus_lock_changed)
        focus_row.addWidget(self.focus_lock)
        focus_row.addStretch()
        layout.addLayout(focus_row)

        self.launch_at_startup = QCheckBox("Launch at startup")
        self.launch_at_startup.setToolTip("Start AirPoint minimized when you sign in to Windows")
        self.launch_at_startup.setEnabled(startup_supported())
        if not startup_supported():
            self.launch_at_startup.setToolTip("Launch at startup is currently available on Windows only")
        self.launch_at_startup.toggled.connect(self._launch_at_startup_changed)
        layout.addWidget(self.launch_at_startup)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(12)
        manual_row.addWidget(label("Manual focus", "muted"))
        self.manual_focus = QSlider(Qt.Horizontal)
        self.manual_focus.setRange(0, 255)
        self.manual_focus.setSingleStep(1)
        self.manual_focus.setAccessibleName("Manual camera focus")
        self.manual_focus.setToolTip("Lens focus value used when Auto focus is off")
        self.manual_focus.valueChanged.connect(self._manual_focus_changed)
        manual_row.addWidget(self.manual_focus, 1)
        self.focus_value = label("128", "valueBadge")
        self.focus_value.setAlignment(Qt.AlignCenter)
        self.focus_value.setFixedWidth(42)
        manual_row.addWidget(self.focus_value)
        layout.addLayout(manual_row)
        return card

    def _build_sensitivity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("controlCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        copy.addWidget(label("Pointer sensitivity", "sectionTitle"))
        copy.addWidget(label("Lower is steadier · higher reaches faster", "muted"))
        layout.addLayout(copy)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        slider_col = QVBoxLayout()
        slider_col.setSpacing(2)
        self.sensitivity = QSlider(Qt.Horizontal)
        self.sensitivity.setAccessibleName("Pointer sensitivity slider")
        self.sensitivity.setAccessibleDescription("Horizontal adjustable pointer sensitivity")
        self.sensitivity.setRange(50, 180)
        self.sensitivity.setSingleStep(5)
        self.sensitivity.valueChanged.connect(self._sensitivity_changed)
        slider_col.addWidget(self.sensitivity)

        range_row = QHBoxLayout()
        range_row.setContentsMargins(2, 0, 2, 0)
        range_row.addWidget(label("0.5×", "rangeHint"))
        range_row.addStretch()
        range_row.addWidget(label("1.8×", "rangeHint"))
        slider_col.addLayout(range_row)
        
        controls_row.addLayout(slider_col, 1)

        self.sensitivity_value = label("1.00×", "valueBadge")
        self.sensitivity_value.setAlignment(Qt.AlignCenter)
        self.sensitivity_value.setFixedWidth(55)
        controls_row.addWidget(self.sensitivity_value, 0, Qt.AlignTop)

        layout.addLayout(controls_row)
        return card

    def _build_developer_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("developerPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(16)

        top = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(1)
        copy.addWidget(label("Developer calibration", "sectionTitle"))
        copy.addWidget(label("Live values are saved locally. Hover a control for its effect; Reset restores proven defaults.", "muted"))
        top.addLayout(copy)
        top.addStretch()
        self.developer_view_select = QComboBox()
        self.developer_view_select.addItem("Recommended controls", "recommended")
        self.developer_view_select.addItem("All advanced controls", "all")
        saved_view = str(self.settings.value("developer/view", "recommended"))
        view_index = self.developer_view_select.findData(saved_view)
        self.developer_view_select.setCurrentIndex(max(0, view_index))
        self.developer_view_select.setToolTip(
            "Recommended shows everyday tuning; All exposes every bounded algorithm control"
        )
        self.developer_view_select.currentIndexChanged.connect(self._developer_view_changed)
        top.addWidget(self.developer_view_select)
        reset = QPushButton("Reset defaults")
        reset.clicked.connect(self._reset_developer_tuning)
        top.addWidget(reset)
        layout.addLayout(top)

        running_note = QFrame()
        running_note.setObjectName("developerNotice")
        note_layout = QHBoxLayout(running_note)
        note_layout.setContentsMargins(10, 7, 10, 7)
        note_layout.addWidget(label("Camera tracking remains active in the background while you calibrate. Changes apply live on the next tracking frame.", "developerNoticeText"))
        layout.addWidget(running_note)

        scroll = QScrollArea()
        scroll.setObjectName("developerScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("developerBody")
        body_layout = QGridLayout(body)
        body_layout.setContentsMargins(0, 0, 10, 0)
        body_layout.setHorizontalSpacing(12)
        body_layout.setVerticalSpacing(12)

        row = 0
        groups: dict[str, list] = {}
        for parameter in DEVELOPER_PARAMETERS:
            groups.setdefault(parameter.group, []).append(parameter)

        # Keep related controls together. A two-column grid makes every row
        # balanced, while a lone setting spans the row instead of leaving a
        # large grey gap beside it.
        for group, parameters in groups.items():
            if row:
                row += 1
            heading = label(group.upper(), "developerGroup")
            self._developer_group_headings[group] = heading
            body_layout.addWidget(heading, row, 0, 1, 2)
            row += 1
            for index, parameter in enumerate(parameters):
                is_last_single = len(parameters) % 2 == 1 and index == len(parameters) - 1
                if is_last_single:
                    body_layout.addWidget(self._developer_control(parameter), row, 0, 1, 2)
                    row += 1
                    continue
                column = index % 2
                body_layout.addWidget(self._developer_control(parameter), row, column)
                if column == 1:
                    row += 1
        body_layout.setColumnStretch(0, 1)
        body_layout.setColumnStretch(1, 1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self._developer_view_changed(self.developer_view_select.currentIndex())
        return page

    def _developer_view_changed(self, index: int) -> None:
        mode = self.developer_view_select.itemData(index)
        if mode not in {"recommended", "all"}:
            mode = "recommended"
        self.settings.setValue("developer/view", mode)
        recommended = {
            "pointer_min_cutoff",
            "pointer_beta",
            "pointer_dead_zone",
            "workspace_margin",
            "precision_enabled",
            "inference_active_fps",
            "inference_idle_fps",
            "preview_fps",
            "face_filter_enabled",
            "face_scan_interval",
            "pinch_contact",
            "pinch_release_grace",
            "double_click_window",
            "drag_start_distance",
            "pause_hold_seconds",
            "scroll_step",
            "volume_step",
            "two_finger_dead_zone",
            "pinch_scroll_enabled",
            "pinch_scroll_activation_distance",
            "pinch_scroll_step",
            "ring_pinch_middle_click",
            "adjustable_control_detection",
            "zoom_step_factor",
            "swipe_enabled",
        }
        visible_keys = set(self._developer_cards) if mode == "all" else recommended
        for key, card in self._developer_cards.items():
            card.setVisible(key in visible_keys)
        for group, heading in self._developer_group_headings.items():
            group_keys = {
                parameter.key
                for parameter in DEVELOPER_PARAMETERS
                if parameter.group == group
            }
            heading.setVisible(bool(group_keys & visible_keys))

    def _developer_control(self, parameter) -> QFrame:
        card = QFrame()
        card.setObjectName("developerRow")
        card.setToolTip(parameter.description)
        self._developer_cards[parameter.key] = card
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        copy.addWidget(label(parameter.label, "developerName"))
        description = label(parameter.description, "developerHint")
        description.setWordWrap(True)
        copy.addWidget(description)
        row.addLayout(copy, 1)
        if parameter.kind == "toggle":
            checkbox = QCheckBox()
            is_checked = self._developer_tuning[parameter.key] >= 0.5
            checkbox.setChecked(is_checked)
            self._update_toggle_checkbox(checkbox, is_checked, animate=False)
            checkbox.setToolTip(parameter.description)
            checkbox.toggled.connect(lambda checked, key=parameter.key, cb=checkbox: [
                self._developer_value_changed(key, 1.0 if checked else 0.0),
                self._update_toggle_checkbox(cb, checked, animate=True)
            ])
            self._developer_inputs[parameter.key] = checkbox
            row.addWidget(checkbox)
        else:
            spinbox = QDoubleSpinBox()
            spinbox.setRange(parameter.minimum, parameter.maximum)
            spinbox.setSingleStep(parameter.step)
            spinbox.setDecimals(parameter.decimals)
            spinbox.setValue(self._developer_tuning[parameter.key])
            spinbox.setToolTip(parameter.description)
            spinbox.setMinimumWidth(78)
            spinbox.valueChanged.connect(lambda value, key=parameter.key: self._developer_value_changed(key, value))
            self._developer_inputs[parameter.key] = spinbox
            row.addWidget(spinbox)
        return card

    def _update_toggle_checkbox(self, checkbox: QCheckBox, checked: bool, animate: bool = True) -> None:
        target_color = QColor("#10B981") if checked else QColor("#EF4444")
        target_text = "Enabled" if checked else "Disabled"
        checkbox.setText(target_text)
        
        if not animate:
            checkbox.setStyleSheet(f"color: {target_color.name()}; font-weight: 750;")
            return
            
        anim_name = f"_anim_{id(checkbox)}"
        if hasattr(self, anim_name):
            getattr(self, anim_name).stop()
            
        start_color = QColor("#EF4444") if checked else QColor("#10B981")
        
        anim = QVariantAnimation(self)
        anim.setDuration(300)
        anim.setStartValue(start_color)
        anim.setEndValue(target_color)
        anim.setEasingCurve(QEasingCurve.OutQuad)
        anim.valueChanged.connect(lambda val, cb=checkbox: cb.setStyleSheet(f"color: {val.name()}; font-weight: 750;"))
        setattr(self, anim_name, anim)
        anim.start()

    def _developer_value_changed(self, key: str, value: float) -> None:
        candidate = dict(self._developer_tuning)
        candidate[key] = value
        normalized = normalized_tuning(candidate)
        changed_keys = {
            parameter_key
            for parameter_key, normalized_value in normalized.items()
            if abs(normalized_value - self._developer_tuning.get(parameter_key, normalized_value)) > 1e-9
        }
        changed_keys.add(key)
        self._developer_tuning = normalized
        for changed_key in changed_keys:
            normalized_value = normalized[changed_key]
            self.settings.setValue(f"developer/{changed_key}", normalized_value)
            control = self._developer_inputs.get(changed_key)
            if control is None:
                continue
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                checked = normalized_value >= 0.5
                control.setChecked(checked)
                self._update_toggle_checkbox(control, checked, animate=False)
            else:
                control.setValue(normalized_value)
            control.blockSignals(False)
        if hasattr(self, "worker"):
            self.worker.set_tuning(self._developer_tuning)

    def _reset_developer_tuning(self) -> None:
        self._developer_tuning = normalized_tuning()
        for parameter in DEVELOPER_PARAMETERS:
            self.settings.remove(f"developer/{parameter.key}")
            control = self._developer_inputs[parameter.key]
            control.blockSignals(True)
            if parameter.kind == "toggle":
                assert isinstance(control, QCheckBox)
                checked = parameter.default >= 0.5
                control.setChecked(checked)
                self._update_toggle_checkbox(control, checked, animate=False)
            else:
                assert isinstance(control, QDoubleSpinBox)
                control.setValue(parameter.default)
            control.blockSignals(False)
        if hasattr(self, "worker"):
            self.worker.set_tuning(self._developer_tuning)

    def _update_activate_style(self) -> None:
        self.activate_button.setProperty("active", self.control_active)
        self.activate_button.setProperty("paused", self.control_active and self._last_paused)
        self.activate_button.style().unpolish(self.activate_button)
        self.activate_button.style().polish(self.activate_button)
        if hasattr(self, "preview_card"):
            self.preview_card.setProperty("active", self.control_active)
            self.preview_card.setProperty("paused", self.control_active and self._last_paused)
            self.preview_card.style().unpolish(self.preview_card)
            self.preview_card.style().polish(self.preview_card)
        if hasattr(self, "activation_card"):
            self.activation_card.setProperty("active", self.control_active)
            self.activation_card.setProperty("paused", self.control_active and self._last_paused)
            self.activation_card.style().unpolish(self.activation_card)
            self.activation_card.style().polish(self.activation_card)
            
        # Blinking red dot logic
        if hasattr(self, "recording_dot"):
            if self.control_active:
                self.recording_dot.show()
                if self._last_paused:
                    # When paused, stop blinking and keep solid red
                    if hasattr(self, "dot_anim_group"):
                        self.dot_anim_group.stop()
                    effect = self.recording_dot.graphicsEffect()
                    if effect:
                        effect.setOpacity(1.0)
                else:
                    # When active (and not paused), blink/pulse
                    if hasattr(self, "dot_anim_group") and self.dot_anim_group.state() != QPropertyAnimation.Running:
                        self.dot_anim_group.start()
            else:
                self.recording_dot.hide()
                if hasattr(self, "dot_anim_group"):
                    self.dot_anim_group.stop()

        if self._tray_toggle_action is not None:
            self._tray_toggle_action.setText("Pause control" if self.control_active else "Resume control")

        if not self.control_active:
            self.activate_button.setText("Enable control")
        elif self._last_paused:
            self.activate_button.setText("Paused · hold fist to resume")
        else:
            self.activate_button.setText("Control active")

    def _activation_behavior_changed(self, index: int) -> None:
        behavior = self.activation_behavior_select.itemData(index)
        if behavior not in {"keep_open", "minimize_to_taskbar", "hide_to_tray"}:
            behavior = "keep_open"
        if behavior == "hide_to_tray" and not self._external_activation_available:
            behavior = "keep_open"
            keep_index = self.activation_behavior_select.findData("keep_open")
            self.activation_behavior_select.blockSignals(True)
            self.activation_behavior_select.setCurrentIndex(max(0, keep_index))
            self.activation_behavior_select.blockSignals(False)
        self._activation_behavior = str(behavior)
        self.settings.setValue("window/activation_behavior", self._activation_behavior)
        if (
            self._activation_behavior != "hide_to_tray"
            and self._tray_icon is not None
            and self.isVisible()
        ):
            self._tray_icon.hide()

    def _set_external_activation_available(self, available: bool) -> None:
        """Disable unrecoverable tray hiding if relaunch activation is absent."""
        self._external_activation_available = bool(available)
        hide_index = self.activation_behavior_select.findData("hide_to_tray")
        model = self.activation_behavior_select.model()
        if hide_index >= 0 and hasattr(model, "item"):
            item = model.item(hide_index)
            if item is not None:
                item.setEnabled(self._external_activation_available)
        if not self._external_activation_available:
            if self._activation_behavior == "hide_to_tray":
                keep_index = self.activation_behavior_select.findData("keep_open")
                self.activation_behavior_select.setCurrentIndex(max(0, keep_index))
            self._show_error(
                "Automatic restore from a second launch is unavailable. "
                "Notification-area hiding is disabled for this session."
            )

    def _ensure_tray_icon(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        if self._tray_icon is not None:
            return True

        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("AirPoint Gesture Control")
        menu = QMenu(self)
        open_action = QAction("Open AirPoint", self)
        open_action.triggered.connect(self._show_from_tray)
        menu.addAction(open_action)
        self._tray_toggle_action = QAction("Pause control", self)
        self._tray_toggle_action.triggered.connect(self._toggle_control_from_tray)
        menu.addAction(self._tray_toggle_action)
        menu.addSeparator()
        quit_action = QAction("Quit AirPoint", self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        self._tray_icon = tray
        return True

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _hide_to_tray(self) -> bool:
        if not self._ensure_tray_icon():
            return False
        assert self._tray_icon is not None
        self._restore_maximized = self.isMaximized()
        self.worker.set_preview_enabled(False)
        self._tray_icon.show()
        self.hide()
        if not self._tray_notice_shown:
            self._tray_icon.showMessage(
                "AirPoint is still tracking",
                "Use the notification-area icon to open AirPoint, pause control, or quit.",
                QSystemTrayIcon.MessageIcon.Information,
                3500,
            )
            self._tray_notice_shown = True
        return True

    def _show_from_tray(self, *_args) -> None:
        if self._restore_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        if not self._shutdown_in_progress:
            self.worker.set_preview_enabled(True)
        self.raise_()
        self.activateWindow()

    def _activate_from_external_launch(self) -> None:
        """Restore and focus this window when a second launcher connects."""
        if not self.isVisible():
            if getattr(self, "_shutdown_in_progress", False):
                self.showNormal()
                self.raise_()
                self.activateWindow()
            else:
                self._show_from_tray()
            return
        if self.isMinimized():
            was_maximized = bool(self.windowState() & Qt.WindowMaximized)
            if was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            if not getattr(self, "_shutdown_in_progress", False):
                self.worker.set_preview_enabled(True)
        self.raise_()
        self.activateWindow()

    def _toggle_control_from_tray(self, *_args) -> None:
        # Keep tray and main-button activation behavior identical, including
        # the selected keep/minimize/hide policy when tracking resumes.
        self._toggle_control()

    def _quit_from_tray(self, *_args) -> None:
        self._force_quit = True
        self._shutdown_close_requested = True
        if not self._shutdown():
            # Show the non-interactive stopping state without restarting
            # preview work or making the dying QThread resumable.
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _apply_activation_window_behavior(self) -> None:
        if not self.control_active:
            return
        if self._activation_behavior == "minimize_to_taskbar":
            self.showMinimized()
        elif self._activation_behavior == "hide_to_tray":
            if not self._hide_to_tray():
                # Never make the application unrecoverable on systems without
                # a notification area; taskbar minimization is the safe fallback.
                self.showMinimized()

    def _toggle_control(self) -> None:
        if getattr(self, "_shutdown_in_progress", False) or getattr(
            self,
            "_shutdown_complete",
            False,
        ):
            return
        was_active = self.control_active
        self.control_active = not self.control_active
        self.worker.set_enabled(self.control_active)
        self._update_activate_style()
        if self.control_active and not was_active:
            self._apply_activation_window_behavior()

    def _startup_gesture_activated(self) -> None:
        if getattr(self, "_shutdown_in_progress", False) or getattr(
            self,
            "_shutdown_complete",
            False,
        ):
            return
        was_active = self.control_active
        self.control_active = True
        self._update_activate_style()
        if not was_active:
            self._apply_activation_window_behavior()

    def _camera_changed(self, index: int) -> None:
        if not hasattr(self, "worker"):
            return
        self.settings.setValue("camera", index)
        self.worker.set_camera(index)
        self.camera_badge.setText(f"CAMERA {index + 1}")
        self.camera_view.setText("Connecting to camera…")
        self.error_frame.hide()

    def _sensitivity_changed(self, value: int) -> None:
        amount = value / 100.0
        self.sensitivity_value.setText(f"{amount:.2f}×")
        self.settings.setValue("sensitivity", value)
        if hasattr(self, "worker"):
            self.worker.set_sensitivity(amount)

    def _swap_hands_changed(self, checked: bool) -> None:
        self.settings.setValue("swap_hands", checked)
        if hasattr(self, "worker"):
            self.worker.set_swap_hands(checked)

    def _refresh_focus_controls(self) -> None:
        locked = self.focus_lock.isChecked()
        automatic = self.autofocus.isChecked()
        self.manual_focus.setEnabled(not automatic and not locked)
        self.focus_value.setText("LOCK" if locked else str(self.manual_focus.value()))

    def _push_focus_settings(self) -> None:
        self.settings.setValue("autofocus", self.autofocus.isChecked())
        self.settings.setValue("manual_focus", self.manual_focus.value())
        self.settings.setValue("focus_lock", self.focus_lock.isChecked())
        self._refresh_focus_controls()
        if hasattr(self, "worker"):
            self.worker.set_focus(self.autofocus.isChecked(), self.manual_focus.value(), self.focus_lock.isChecked())

    def _autofocus_changed(self, checked: bool) -> None:
        if self._focus_updating:
            return
        if checked and self.focus_lock.isChecked():
            self._focus_updating = True
            self.focus_lock.setChecked(False)
            self._focus_updating = False
        self._push_focus_settings()

    def _focus_lock_changed(self, checked: bool) -> None:
        if self._focus_updating:
            return
        if checked and self.autofocus.isChecked():
            self._focus_updating = True
            self.autofocus.setChecked(False)
            self._focus_updating = False
        self._push_focus_settings()

    def _manual_focus_changed(self, _value: int) -> None:
        if not self._focus_updating:
            self._push_focus_settings()

    def _launch_at_startup_changed(self, checked: bool) -> None:
        if self._startup_updating:
            return
        try:
            set_startup_enabled(checked)
        except OSError as exc:
            self._startup_updating = True
            self.launch_at_startup.setChecked(is_startup_enabled())
            self._startup_updating = False
            self.error_text.setText(f"Could not update launch at startup: {exc}")
            self.error_frame.show()

    def _focus_locked_by_camera(self, value: int) -> None:
        self._focus_updating = True
        self.manual_focus.setValue(value)
        self._focus_updating = False
        self.settings.setValue("manual_focus", value)
        self._refresh_focus_controls()

    def _left_handed_changed(self, checked: bool) -> None:
        self.settings.setValue("left_handed", checked)
        dominant = "left" if checked else "right"
        support = "right" if checked else "left"
        self.pointer_subtitle.setText(f"Your {dominant} index finger steers the pointer.")
        if hasattr(self, "volume_guide"):
            self.volume_guide.set_hint(f"{support.title()} palm + {dominant} index pinch")
        if hasattr(self, "scroll_guide"):
            self.scroll_guide.set_hint(f"{support.title()} fist + {dominant} index pinch")
        if hasattr(self, "worker"):
            self.worker.set_left_handed(checked)

    def _update_telemetry(self, data: dict) -> None:
        if self.error_frame.isVisible():
            self.error_frame.hide()

        hand_state = (bool(data["right"]), bool(data["left"]))
        if hand_state != self._last_hand_state:
            self._last_hand_state = hand_state
            self.right_status.setObjectName("handOn" if hand_state[0] else "handOff")
            self.left_status.setObjectName("handOn" if hand_state[1] else "handOff")
            for widget in (self.right_status, self.left_status):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        self._set_gesture_status(str(data["gesture"]))
        fps_text = f"{data['fps']:.0f} FPS" if data["fps"] else "WARMING UP"
        if self.fps_label.text() != fps_text:
            self.fps_label.setText(fps_text)

    def _display_frame(self, image: QImage) -> None:
        try:
            self.camera_view.set_frame(image)
        finally:
            # Never permanently consume the worker's one-frame backpressure
            # slot if a transient Qt paint/conversion error occurs.
            self.worker.acknowledge_preview()

    def _paused_changed(self, paused: bool) -> None:
        self._last_paused = paused
        self._update_activate_style()

    def _gesture_changed(self, gesture: str) -> None:
        self._set_gesture_status(gesture)

    def _set_gesture_status(self, gesture: str) -> None:
        if self.gesture_status.text() != gesture:
            self.gesture_status.setText(gesture)
        if self.gesture_overlay.text() != gesture:
            self.gesture_overlay.set_status(gesture)

    def _show_error(self, message: str) -> None:
        self.error_text.setText(message)
        self.error_frame.show()

    def _model_progress(self, value: int) -> None:
        self.download_progress.show()
        self.download_progress.setValue(value)
        self._set_gesture_status(f"Preparing hand model · {value}%")
        if value >= 100:
            self.download_progress.hide()

    def _shutdown(self) -> bool:
        if self._shutdown_complete:
            return True
        if self._shutdown_in_progress:
            return False
        self._shutdown_in_progress = True
        self.control_active = False
        self.worker.set_enabled(False)
        self.worker.set_preview_enabled(False)
        self._update_activate_style()
        self.activate_button.setEnabled(False)
        self.activate_button.setText("Stopping...")
        # Stop is deliberately request-only here. Camera/model cleanup can
        # take time, so the GUI remains responsive and polls the QThread
        # asynchronously instead of entering a multi-second wait.
        if not self.worker.stop(timeout_ms=0):
            self._show_error(
                "AirPoint is waiting for the camera worker to stop safely. "
                "The window will close automatically when cleanup finishes."
            )
            self._schedule_shutdown_poll()
            return False
        self._finalize_shutdown()
        return True

    def _finalize_shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self.gesture_overlay.close()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        self._shutdown_complete = True
        self._shutdown_in_progress = False

    def _schedule_shutdown_poll(self) -> None:
        if self._shutdown_poll_scheduled or self._shutdown_complete:
            return
        self._shutdown_poll_scheduled = True
        QTimer.singleShot(250, self._poll_shutdown)

    def _poll_shutdown(self) -> None:
        self._shutdown_poll_scheduled = False
        if self._shutdown_complete:
            return
        if self.worker.isRunning():
            self._schedule_shutdown_poll()
            return
        self._finalize_shutdown()
        if self._shutdown_close_requested:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._force_quit
            and self.control_active
            and self._activation_behavior == "hide_to_tray"
            and self._hide_to_tray()
        ):
            event.ignore()
            return
        self._shutdown_close_requested = True
        if self._shutdown():
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "worker"):
            # Tracking continues while minimized, but camera drawing, QImage
            # copies, scaling, and telemetry repaints are suspended.
            self.worker.set_preview_enabled(
                not self._shutdown_in_progress and not self.isMinimized()
            )


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AirPoint")
    app.setOrganizationName("AirPoint")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    # Prevent duplicate camera/inference pipelines from competing for CPU and
    # webcam bandwidth when the launcher is double-clicked more than once.
    lock_path = str(Path(tempfile.gettempdir()) / "AirPoint-GestureControl.lock")
    instance_lock = QLockFile(lock_path)
    if not instance_lock.tryLock(100):
        if not request_activation():
            QMessageBox.information(
                None,
                "AirPoint is already running",
                "AirPoint is running, but its window could not be restored automatically. "
                "Open it from the taskbar or notification area.",
            )
        return 0

    # Listen before constructing the relatively heavy camera UI. Connections
    # queue until the event loop starts, eliminating the launch-time race.
    activation_server = ActivationServer(parent=app)
    activation_available = activation_server.listen()
    try:
        disable_background_throttling()
        window = MainWindow()
        window._set_external_activation_available(activation_available)
        activation_server.activation_requested.connect(window._activate_from_external_launch)
        if "--minimized" in sys.argv:
            window.worker.set_preview_enabled(False)
            window.showMinimized()
        elif "--maximized" in sys.argv:
            window.showMaximized()
        else:
            window.show()
        return app.exec()
    finally:
        activation_server.close()
        instance_lock.unlock()
