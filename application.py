from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QLockFile, QSettings, QSize
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from .camera_worker import CameraWorker
from .styles import APP_STYLE
from .system_control import disable_background_throttling


def label(text: str = "", object_name: str = "") -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


class CameraView(QLabel):
    def __init__(self) -> None:
        super().__init__("Starting camera…")
        self.setObjectName("cameraView")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(620, 420)
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
        # FastTransformation avoids a costly high-quality rescale on every
        # camera frame; the source is already sized for the preview.
        self.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.FastTransformation))


class GestureRow(QFrame):
    def __init__(self, symbol: str, name: str, hint: str) -> None:
        super().__init__()
        self.setObjectName("gestureRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 5, 0, 5)
        row.setSpacing(10)
        icon = label(symbol, "gestureIcon")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignCenter)
        row.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label(name, "gestureName"))
        self.hint_label = label(hint, "gestureHint")
        text.addWidget(self.hint_label)
        row.addLayout(text, 1)

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AirPoint · Gesture Control")
        self.setMinimumSize(1120, 720)
        self.resize(1240, 790)
        self.settings = QSettings("AirPoint", "GestureControl")
        self.control_active = False
        self._last_paused = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())
        outer.addWidget(self._build_content(), 1)

        self.worker = CameraWorker()
        self.worker.frame_ready.connect(self.camera_view.set_frame)
        self.worker.telemetry.connect(self._update_telemetry)
        self.worker.error.connect(self._show_error)
        self.worker.model_progress.connect(self._model_progress)
        self.worker.paused_changed.connect(self._paused_changed)
        self.worker.startup_activated.connect(self._startup_gesture_activated)

        saved_sensitivity = int(self.settings.value("sensitivity", 100))
        saved_camera = int(self.settings.value("camera", 0))
        saved_swap_value = self.settings.value("swap_hands", True)
        saved_swap = saved_swap_value if isinstance(saved_swap_value, bool) else str(saved_swap_value).lower() == "true"
        saved_left_value = self.settings.value("left_handed", False)
        saved_left = saved_left_value if isinstance(saved_left_value, bool) else str(saved_left_value).lower() == "true"
        self.sensitivity.setValue(saved_sensitivity)
        self.camera_select.setCurrentIndex(max(0, min(2, saved_camera)))
        self.swap_hands.setChecked(saved_swap)
        self.left_handed.setChecked(saved_left)
        self._sensitivity_changed(saved_sensitivity)
        self.worker.set_camera(self.camera_select.currentIndex())
        self.worker.set_swap_hands(saved_swap)
        self.worker.set_left_handed(saved_left)
        self.worker.start()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(292)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(24, 23, 24, 22)
        layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = label("A", "brandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(38, 38)
        brand_row.addWidget(mark)
        brand_row.addWidget(label("AirPoint", "brand"))
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(11)

        layout.addWidget(label("GESTURE GUIDE", "eyebrow"))
        guide = QFrame()
        guide.setObjectName("card")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(14, 10, 14, 10)
        guide_layout.setSpacing(1)
        guide_layout.addWidget(GestureRow("L", "Left click", "Index + thumb pinch"))
        guide_layout.addWidget(GestureRow("R", "Right click", "Middle + thumb pinch"))
        guide_layout.addWidget(GestureRow("2×", "Double click / drag", "Repeat index pinch · release / move"))
        guide_layout.addWidget(GestureRow("■", "Pause / resume", "Hold a fist for 0.7 seconds"))
        self.volume_guide = GestureRow("♪", "System volume", "Left palm + right index pinch")
        self.scroll_guide = GestureRow("↕", "Scroll", "Left fist + right index pinch")
        guide_layout.addWidget(self.volume_guide)
        guide_layout.addWidget(self.scroll_guide)
        guide_layout.addWidget(GestureRow("Ⅱ", "Two-finger scroll", "Index + middle · move vertically"))
        guide_layout.addWidget(GestureRow("↔", "Zoom", "Pinch both hands · apart / together"))
        layout.addWidget(guide)

        layout.addStretch()
        safety = QFrame()
        safety.setObjectName("card")
        safety_layout = QVBoxLayout(safety)
        safety_layout.setContentsMargins(15, 13, 15, 13)
        safety_layout.setSpacing(5)
        safety_layout.addWidget(label("Safety first", "sectionTitle"))
        note = label("Control starts off. At startup, hold both fists together for a moment and release—or use the activate button.", "muted")
        note.setWordWrap(True)
        safety_layout.addWidget(note)
        layout.addWidget(safety)

        footer = label("LOCAL PROCESSING  •  CAMERA STAYS ON DEVICE", "eyebrow")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 23, 28, 25)
        layout.setSpacing(17)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("CAMERA CONTROL", "eyebrow"))
        titles.addWidget(label("Move naturally. Point precisely.", "title"))
        self.pointer_subtitle = label("Your right index finger steers the pointer.", "subtitle")
        titles.addWidget(self.pointer_subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.fps_label = label("— FPS", "gesturePill")
        header.addWidget(self.fps_label, 0, Qt.AlignBottom)
        layout.addLayout(header)

        self.error_banner = label("", "errorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        layout.addWidget(self.error_banner)

        preview_card = QFrame()
        preview_card.setObjectName("previewCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(10)
        self.camera_view = CameraView()
        preview_layout.addWidget(self.camera_view, 1)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(8, 0, 8, 2)
        self.right_status = label("●  Right hand", "handOff")
        self.left_status = label("●  Left hand", "handOff")
        self.gesture_status = label("Initializing tracking…", "gesturePill")
        status_row.addWidget(self.right_status)
        status_row.addSpacing(13)
        status_row.addWidget(self.left_status)
        status_row.addStretch()
        status_row.addWidget(self.gesture_status)
        preview_layout.addLayout(status_row)
        layout.addWidget(preview_card, 1)

        controls = QHBoxLayout()
        controls.setSpacing(13)
        controls.addWidget(self._build_setup_card(), 2)
        controls.addWidget(self._build_sensitivity_card(), 3)
        self.activate_button = QPushButton("Activate gesture control")
        self.activate_button.setObjectName("primary")
        self.activate_button.setMinimumWidth(215)
        self.activate_button.clicked.connect(self._toggle_control)
        controls.addWidget(self.activate_button, 0, Qt.AlignVCenter)
        layout.addLayout(controls)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.hide()
        layout.addWidget(self.download_progress)
        return content

    def _build_setup_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        copy.addWidget(label("Camera", "sectionTitle"))
        copy.addWidget(label("Choose an input device", "muted"))
        row.addLayout(copy)
        row.addStretch()
        self.swap_hands = QCheckBox("Swap L/R")
        self.swap_hands.setToolTip("Reverse the left and right labels for mirrored camera drivers")
        self.swap_hands.toggled.connect(self._swap_hands_changed)
        row.addWidget(self.swap_hands)
        self.left_handed = QCheckBox("Left-handed")
        self.left_handed.setToolTip("Use the left hand for pointer and click gestures, and the right hand for support gestures")
        self.left_handed.toggled.connect(self._left_handed_changed)
        row.addWidget(self.left_handed)
        self.camera_select = QComboBox()
        self.camera_select.addItems(["Camera 1", "Camera 2", "Camera 3"])
        self.camera_select.setMinimumWidth(112)
        self.camera_select.currentIndexChanged.connect(self._camera_changed)
        row.addWidget(self.camera_select)
        return card

    def _build_sensitivity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        copy.addWidget(label("Pointer sensitivity", "sectionTitle"))
        copy.addWidget(label("Lower is steadier · higher reaches faster", "muted"))
        row.addLayout(copy)
        self.sensitivity = QSlider(Qt.Horizontal)
        self.sensitivity.setAccessibleName("Pointer sensitivity slider")
        self.sensitivity.setAccessibleDescription("Horizontal adjustable pointer sensitivity")
        self.sensitivity.setRange(50, 180)
        self.sensitivity.setSingleStep(5)
        self.sensitivity.setMinimumWidth(150)
        self.sensitivity.valueChanged.connect(self._sensitivity_changed)
        row.addWidget(self.sensitivity, 1)
        self.sensitivity_value = label("1.00×", "valueBadge")
        self.sensitivity_value.setAlignment(Qt.AlignCenter)
        self.sensitivity_value.setFixedWidth(55)
        row.addWidget(self.sensitivity_value)
        return card

    def _toggle_control(self) -> None:
        self.control_active = not self.control_active
        self.worker.set_enabled(self.control_active)
        self.activate_button.setProperty("active", self.control_active)
        self.activate_button.style().unpolish(self.activate_button)
        self.activate_button.style().polish(self.activate_button)
        self.activate_button.setText("Gesture control active" if self.control_active else "Activate gesture control")

    def _startup_gesture_activated(self) -> None:
        self.control_active = True
        self.activate_button.setProperty("active", True)
        self.activate_button.style().unpolish(self.activate_button)
        self.activate_button.style().polish(self.activate_button)
        self.activate_button.setText("Gesture control active")

    def _camera_changed(self, index: int) -> None:
        if not hasattr(self, "worker"):
            return
        self.settings.setValue("camera", index)
        self.worker.set_camera(index)
        self.camera_view.setText("Connecting to camera…")
        self.error_banner.hide()

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

    def _left_handed_changed(self, checked: bool) -> None:
        self.settings.setValue("left_handed", checked)
        dominant = "left" if checked else "right"
        support = "right" if checked else "left"
        self.pointer_subtitle.setText(f"Your {dominant} index finger steers the pointer.")
        self.volume_guide.set_hint(f"{support.title()} palm + {dominant} index pinch")
        self.scroll_guide.set_hint(f"{support.title()} fist + {dominant} index pinch")
        if hasattr(self, "worker"):
            self.worker.set_left_handed(checked)

    def _update_telemetry(self, data: dict) -> None:
        self.error_banner.hide()
        self.right_status.setObjectName("handOn" if data["right"] else "handOff")
        self.left_status.setObjectName("handOn" if data["left"] else "handOff")
        for widget in (self.right_status, self.left_status):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.gesture_status.setText(data["gesture"])
        self.fps_label.setText(f"{data['fps']:.0f} FPS" if data["fps"] else "WARMING UP")

    def _paused_changed(self, paused: bool) -> None:
        self._last_paused = paused
        if self.control_active:
            self.activate_button.setText("Paused · hold fist to resume" if paused else "Gesture control active")

    def _show_error(self, message: str) -> None:
        self.error_banner.setText(message)
        self.error_banner.show()

    def _model_progress(self, value: int) -> None:
        self.download_progress.show()
        self.download_progress.setValue(value)
        self.gesture_status.setText(f"Preparing hand model · {value}%")
        if value >= 100:
            self.download_progress.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.control_active = False
        self.worker.set_enabled(False)
        self.worker.stop()
        event.accept()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "worker"):
            # Tracking continues while minimized, but camera drawing, QImage
            # copies, scaling, and telemetry repaints are suspended.
            self.worker.set_preview_enabled(not self.isMinimized())


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
        QMessageBox.information(None, "AirPoint is already running", "AirPoint already has an open window.")
        return 0

    disable_background_throttling()
    window = MainWindow()
    if "--minimized" in sys.argv:
        window.worker.set_preview_enabled(False)
        window.showMinimized()
    else:
        window.show()
    result = app.exec()
    instance_lock.unlock()
    return result
