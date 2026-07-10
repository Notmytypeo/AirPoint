APP_STYLE = """
* {
    color: #EEF1F6;
}
QMainWindow, QWidget#root { background: #0B0D12; }
QFrame#sidebar { background: #11141B; border-right: 1px solid #242936; }
QLabel#brand { font-size: 21px; font-weight: 700; letter-spacing: 0.5px; }
QLabel#brandMark { background: #8B7CFF; color: white; border-radius: 10px; font-size: 18px; font-weight: 800; }
QLabel#eyebrow { color: #8B93A6; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#title { font-size: 28px; font-weight: 650; }
QLabel#subtitle { color: #939BAC; font-size: 13px; }
QFrame#card, QFrame#previewCard { background: #141820; border: 1px solid #272C39; border-radius: 16px; }
QFrame#previewCard { background: #10131A; }
QLabel#sectionTitle { font-size: 14px; font-weight: 650; }
QLabel#muted { color: #8F97A9; font-size: 12px; }
QLabel#cameraView { background: #0D1016; border-radius: 12px; color: #7D8494; }
QLabel#gesturePill { background: #202532; border: 1px solid #303748; border-radius: 13px; padding: 6px 12px; font-size: 12px; font-weight: 600; }
QLabel#handOn { color: #94F6D1; font-weight: 650; }
QLabel#handOff { color: #6F7686; }
QPushButton {
    background: #202532; border: 1px solid #303748; border-radius: 10px;
    min-height: 40px; padding: 0 16px; font-size: 13px; font-weight: 600;
}
QPushButton:hover { background: #292F3D; border-color: #3A4254; }
QPushButton:pressed { background: #1C202B; }
QPushButton#primary { background: #8B7CFF; border: none; color: white; min-height: 44px; font-size: 14px; }
QPushButton#primary:hover { background: #9B8FFF; }
QPushButton#primary[active="true"] { background: #26352F; color: #94F6D1; border: 1px solid #3E6657; }
QComboBox {
    background: #1B1F29; border: 1px solid #303646; border-radius: 9px;
    min-height: 38px; padding: 0 12px; color: #E7EAF0;
}
QComboBox::drop-down { border: none; width: 30px; }
QComboBox QAbstractItemView { background: #1B1F29; border: 1px solid #303646; selection-background-color: #6659D9; }
QCheckBox { color: #AEB5C4; font-size: 12px; spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #41485A; border-radius: 5px; background: #1B1F29; }
QCheckBox::indicator:checked { background: #8B7CFF; border-color: #8B7CFF; }
QSlider::groove:horizontal { height: 5px; background: #2B303C; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #8B7CFF; border-radius: 2px; }
QSlider::handle:horizontal { background: #F4F1FF; width: 16px; margin: -6px 0; border-radius: 8px; }
QLabel#valueBadge { color: #BEB6FF; background: #29243E; border-radius: 8px; padding: 4px 8px; font-weight: 650; }
QFrame#gestureRow { background: transparent; border: none; }
QLabel#gestureIcon { background: #222734; border-radius: 9px; color: #B9B2FF; font-weight: 700; }
QLabel#gestureName { font-size: 12px; font-weight: 600; }
QLabel#gestureHint { color: #798193; font-size: 10px; }
QLabel#errorBanner { background: #382126; color: #FFB6C1; border: 1px solid #66343D; border-radius: 9px; padding: 9px 12px; }
QProgressBar { border: none; background: #252A36; height: 4px; border-radius: 2px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #8B7CFF; border-radius: 2px; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #363C4A; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
