APP_STYLE = """
/* ───────────── Base & Typography ───────────── */
* {
    color: #F1F5F9;
    font-family: "Segoe UI Variable Text", "Segoe UI", -apple-system, system-ui, sans-serif;
    font-size: 12px;
}
QMainWindow, QWidget#root { 
    background: #000000; 
}

/* ───────────── Sidebar ───────────── */
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0F1322, stop:1 #080A12);
    border-right: 1px solid rgba(255, 255, 255, 0.05);
}
QLabel#brand {
    color: #FFFFFF; 
    font-size: 20px; 
    font-weight: 750; 
    letter-spacing: -0.2px;
}
QLabel#brandMeta {
    color: #6366F1; 
    font-size: 9px; 
    font-weight: 800; 
    letter-spacing: 1.5px;
}
QLabel#brandMark {
    background: transparent;
}
QLabel#eyebrow {
    color: #475569; 
    font-size: 10px; 
    font-weight: 800; 
    letter-spacing: 1.5px;
}
QLabel#versionFooter {
    color: #334155; 
    font-size: 9px; 
    letter-spacing: 0.5px;
}

/* ───────────── Cards & Containers ───────────── */
QFrame#sideCard {
    background: #111625;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
}
QFrame#controlCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #111625, stop:1 #0D111D);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
}
QFrame#activationCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(79, 70, 229, 0.08), stop:1 #0D111D);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
}
QFrame#activationCard[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(52, 211, 153, 0.08), stop:1 #0D111D);
    border-color: rgba(52, 211, 153, 0.15);
}
QFrame#activationCard[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(251, 191, 36, 0.08), stop:1 #0D111D);
    border-color: rgba(251, 191, 36, 0.15);
}
QFrame#cameraStage {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(79, 70, 229, 0.08), stop:1 #080B13);
    border: 1px solid #4F46E5;
    border-radius: 14px;
}
QFrame#cameraStage[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(52, 211, 153, 0.08), stop:1 #080B13);
    border-color: #34D399;
}
QFrame#cameraStage[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(251, 191, 36, 0.08), stop:1 #080B13);
    border-color: #FBBF24;
}

/* ───────────── Tabs ───────────── */
QPushButton#workspaceTab, QPushButton#developerTab {
    background: #0E1320;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    color: #64748B;
    min-width: 138px;
    height: 36px;
    min-height: 36px;
    padding: 0 16px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#workspaceTab:hover, QPushButton#developerTab:hover {
    color: #94A3B8;
    background: rgba(255, 255, 255, 0.03);
    border-color: rgba(255, 255, 255, 0.05);
}
QPushButton#workspaceTab[selected="true"], QPushButton#developerTab[selected="true"] {
    color: #FFFFFF;
    background: #1A2140;
    border: 1px solid #4F46E5;
}
QPushButton#workspaceTab[selected="true"]:hover, QPushButton#developerTab[selected="true"]:hover {
    background: #1A2140;
    border: 1px solid #4F46E5;
    color: #FFFFFF;
}

/* ───────────── Typography & Headings ───────────── */
QLabel#title {
    color: #FFFFFF; 
    font-size: 26px; 
    font-weight: 750; 
    letter-spacing: -0.5px;
}
QLabel#subtitle { 
    color: #94A3B8; 
    font-size: 13px; 
}
QLabel#sectionTitle { 
    color: #F8FAFC; 
    font-size: 13px; 
    font-weight: 700; 
    letter-spacing: 0.1px;
}
QLabel#muted { 
    color: #64748B; 
    font-size: 11px; 
}

/* ───────────── Camera Stage ───────────── */
QLabel#stageTitle { 
    color: #F8FAFC; 
    font-size: 13px; 
    font-weight: 700; 
}
QLabel#stageHint { 
    color: #64748B; 
    font-size: 11px; 
}
QLabel#recordingDot {
    background-color: #EF4444;
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
    margin-top: 1px;
    margin-left: 2px;
}
QLabel#cameraBadge {
    color: #38BDF8; 
    background: rgba(14, 165, 233, 0.1);
    border: 1px solid rgba(14, 165, 233, 0.2);
    border-radius: 6px; 
    padding: 4px 10px;
    font-size: 10px; 
    font-weight: 800; 
    letter-spacing: 0.8px;
}
QLabel#cameraView {
    background: #05070B;
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 10px;
    color: #475569;
}

/* ───────────── Status Pills ───────────── */
QLabel#gesturePill {
    background: #1E1B4B;
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 8px;
    padding: 6px 14px;
    color: #C7D2FE;
    font-size: 11px;
    font-weight: 700;
}
QLabel#performancePill {
    background: #082F49;
    border: 1px solid rgba(14, 165, 233, 0.3);
    border-radius: 8px;
    padding: 6px 12px;
    color: #38BDF8;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.5px;
}
QLabel#handOn { 
    color: #10B981; 
    font-size: 12px; 
    font-weight: 750; 
}
QLabel#handOff { 
    color: #475569; 
    font-size: 12px; 
    font-weight: 500; 
}

/* ───────────── Buttons ───────────── */
QPushButton {
    background: #1E293B;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    min-height: 36px;
    padding: 0 16px;
    color: #F1F5F9;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover { 
    background: #334155; 
    border-color: rgba(255, 255, 255, 0.15); 
}
QPushButton:pressed { 
    background: #0F172A; 
}

QPushButton#sidebarToggle {
    background: #1E293B;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    color: #F1F5F9;
    font-size: 16px;
    font-weight: bold;
    min-height: 38px;
    min-width: 38px;
    max-height: 38px;
    max-width: 38px;
    padding: 0;
}
QPushButton#sidebarToggle:hover {
    background: #334155;
    border-color: rgba(255, 255, 255, 0.15);
}
QPushButton#sidebarToggle:checked {
    background: #1A2140;
    border-color: #4F46E5;
}

QPushButton#themeToggle {
    background: #1E293B;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    color: #F1F5F9;
    font-size: 16px;
    min-height: 38px;
    min-width: 38px;
    max-height: 38px;
    max-width: 38px;
    padding: 0;
}
QPushButton#themeToggle:hover {
    background: #334155;
    border-color: rgba(255, 255, 255, 0.15);
}

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4F46E5, stop:1 #06B6D4);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #FFFFFF;
    min-height: 42px;
    padding: 0 20px;
    font-size: 13px;
    font-weight: 700;
    border-radius: 10px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366F1, stop:1 #22D3EE);
    border-color: rgba(255, 255, 255, 0.25);
}
QPushButton#primary[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #065F46, stop:1 #059669);
    border-color: #34D399;
    color: #FFFFFF;
}
QPushButton#primary[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #92400E, stop:1 #D97706);
    border-color: #FBBF24;
    color: #FFFFFF;
}

/* ───────────── Inputs ───────────── */
QComboBox {
    background: #111625;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    min-height: 32px;
    padding: 0 12px;
    color: #F1F5F9;
    font-size: 12px;
}
QComboBox:hover { 
    border-color: rgba(255, 255, 255, 0.18); 
}
QComboBox::drop-down { 
    border: none; 
    width: 28px; 
}
QComboBox QAbstractItemView {
    background: #111625; 
    border: 1px solid rgba(255, 255, 255, 0.1);
    selection-background-color: #4F46E5;
    selection-color: #FFFFFF;
}

QDoubleSpinBox {
    background: #111625;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    min-height: 28px;
    padding: 0 6px;
    color: #38BDF8;
    font-size: 11px;
    font-weight: 700;
}
QDoubleSpinBox:hover, QDoubleSpinBox:focus { 
    border-color: #6366F1; 
}

QCheckBox { 
    color: #94A3B8; 
    font-size: 11px; 
    spacing: 7px; 
}
QCheckBox::indicator {
    width: 15px; 
    height: 15px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    background: #111625;
}
QCheckBox::indicator:hover { 
    border-color: #6366F1; 
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4F46E5, stop:1 #6366F1);
    border-color: #818CF8;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #1E293B;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366F1, stop:1 #06B6D4);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #4F46E5;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { 
    background: #F8FAFC; 
    border-color: #06B6D4;
}

QLabel#valueBadge {
    color: #38BDF8;
    background: #082F49;
    border: 1px solid rgba(14, 165, 233, 0.3);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 750;
}
QLabel#rangeHint {
    color: #475569;
    font-size: 9px;
    font-weight: 600;
}

/* ───────────── Gesture Guide ───────────── */
QFrame#gestureRow { 
    background: transparent; 
    border: none; 
}
QFrame#gestureRow:hover { 
    background: rgba(255, 255, 255, 0.02); 
    border-radius: 8px; 
}
QLabel#gestureIcon {
    background: #1E293B;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    color: #38BDF8;
    font-size: 11px;
    font-weight: 800;
}
QLabel#gestureName { 
    color: #E2E8F0; 
    font-size: 12px; 
    font-weight: 650; 
}
QLabel#gestureHint { 
    color: #64748B; 
    font-size: 10px; 
}

/* ───────────── Developer Panel ───────────── */
QFrame#developerPanel {
    background: #090C15;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
}
QFrame#developerRow {
    background: #111625;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
}
QFrame#developerRow:hover {
    background: #161D30;
    border-color: rgba(255, 255, 255, 0.1);
}
QLabel#developerGroup {
    color: #6366F1;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding-top: 8px;
}
QLabel#developerName { 
    color: #E2E8F0; 
    font-size: 11px; 
    font-weight: 650; 
}
QLabel#developerHint { 
    color: #64748B; 
    font-size: 9.5px; 
}

QScrollArea#developerScroll, QScrollArea#developerScroll > QWidget, QWidget#developerBody { 
    background: transparent; 
}
QFrame#developerNotice {
    background: #082F49;
    border: 1px solid rgba(14, 165, 233, 0.2);
    border-radius: 8px;
}
QLabel#developerNoticeText { 
    color: #38BDF8; 
    font-size: 11px; 
}

/* ───────────── Error Banner ───────────── */
QFrame#errorFrame {
    background: #3F1621;
    border: 1px solid #991B1B;
    border-left: 4px solid #EF4444;
    border-radius: 8px;
}
QLabel#errorText {
    color: #FECACA;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#errorDismiss {
    background: transparent;
    border: none;
    color: #EF4444;
    font-size: 14px;
    font-weight: 750;
    min-height: 20px;
    min-width: 24px;
    padding: 0;
}
QPushButton#errorDismiss:hover { 
    color: #FCA5A5; 
}

/* ───────────── Progress & Scrollbars ───────────── */
QProgressBar {
    border: none;
    background: #1E293B;
    height: 4px;
    border-radius: 2px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366F1, stop:1 #06B6D4);
    border-radius: 2px;
}
QScrollBar:vertical {
    background: transparent; 
    width: 6px; 
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { 
    background: #475569; 
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    height: 0; 
}
"""

LIGHT_STYLE = """
/* ───────────── Base & Typography ───────────── */
* {
    color: #0F172A;
    font-family: "Segoe UI Variable Text", "Segoe UI", -apple-system, system-ui, sans-serif;
    font-size: 12px;
}
QMainWindow, QWidget#root { 
    background: #F8FAFC; 
}

/* ───────────── Sidebar Panel ───────────── */
QFrame#sidebarPanel {
    background: transparent;
    border: none;
}

/* ───────────── Cards & Containers ───────────── */
QFrame#sideCard {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}
QFrame#controlCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FFFFFF, stop:1 #F1F5F9);
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}
QFrame#activationCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(79, 70, 229, 0.05), stop:1 #FFFFFF);
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}
QFrame#activationCard[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(16, 185, 129, 0.05), stop:1 #FFFFFF);
    border-color: rgba(16, 185, 129, 0.25);
}
QFrame#activationCard[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(245, 158, 11, 0.05), stop:1 #FFFFFF);
    border-color: rgba(245, 158, 11, 0.25);
}
QFrame#cameraStage {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(79, 70, 229, 0.05), stop:1 #FFFFFF);
    border: 1px solid #CBD5E1;
    border-radius: 14px;
}
QFrame#cameraStage[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(16, 185, 129, 0.05), stop:1 #FFFFFF);
    border-color: #10B981;
}
QFrame#cameraStage[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(245, 158, 11, 0.05), stop:1 #FFFFFF);
    border-color: #F59E0B;
}

/* ───────────── Tabs ───────────── */
QPushButton#workspaceTab, QPushButton#developerTab {
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    color: #475569;
    min-width: 138px;
    height: 36px;
    min-height: 36px;
    padding: 0 16px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#workspaceTab:hover, QPushButton#developerTab:hover {
    color: #0F172A;
    background: #E2E8F0;
    border-color: #CBD5E1;
}
QPushButton#workspaceTab[selected="true"], QPushButton#developerTab[selected="true"] {
    color: #4F46E5;
    background: #EEF2F6;
    border: 1px solid #4F46E5;
}
QPushButton#workspaceTab[selected="true"]:hover, QPushButton#developerTab[selected="true"]:hover {
    background: #EEF2F6;
    border: 1px solid #4F46E5;
    color: #4F46E5;
}

/* ───────────── Typography & Headings ───────────── */
QLabel#title {
    color: #0F172A; 
    font-size: 26px; 
    font-weight: 750; 
    letter-spacing: -0.5px;
}
QLabel#subtitle { 
    color: #475569; 
    font-size: 13px; 
}
QLabel#sectionTitle { 
    color: #0F172A; 
    font-size: 13px; 
    font-weight: 700; 
    letter-spacing: 0.1px;
}
QLabel#muted { 
    color: #64748B; 
    font-size: 11px; 
}

/* ───────────── Camera Stage ───────────── */
QLabel#stageTitle { 
    color: #0F172A; 
    font-size: 13px; 
    font-weight: 700; 
}
QLabel#stageHint { 
    color: #64748B; 
    font-size: 11px; 
}
QLabel#recordingDot {
    background-color: #EF4444;
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
    margin-top: 1px;
    margin-left: 2px;
}
QLabel#cameraBadge {
    color: #0284C7; 
    background: rgba(2, 132, 199, 0.08);
    border: 1px solid rgba(2, 132, 199, 0.18);
    border-radius: 6px; 
    padding: 4px 10px;
    font-size: 10px; 
    font-weight: 800; 
    letter-spacing: 0.8px;
}
QLabel#cameraView {
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    color: #64748B;
}

/* ───────────── Status Pills ───────────── */
QLabel#gesturePill {
    background: #EEF2F6;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 6px 14px;
    color: #4F46E5;
    font-size: 11px;
    font-weight: 700;
}
QLabel#performancePill {
    background: #E0F2FE;
    border: 1px solid #BAE6FD;
    border-radius: 8px;
    padding: 6px 12px;
    color: #0284C7;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.5px;
}
QLabel#handOn { 
    color: #10B981; 
    font-size: 12px; 
    font-weight: 750; 
}
QLabel#handOff { 
    color: #94A3B8; 
    font-size: 12px; 
    font-weight: 500; 
}

/* ───────────── Buttons ───────────── */
QPushButton {
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    min-height: 36px;
    padding: 0 16px;
    color: #0F172A;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover { 
    background: #E2E8F0; 
    border-color: #94A3B8; 
}
QPushButton:pressed { 
    background: #CBD5E1; 
}

QPushButton#sidebarToggle {
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    color: #0F172A;
    font-size: 16px;
    font-weight: bold;
    min-height: 38px;
    min-width: 38px;
    max-height: 38px;
    max-width: 38px;
    padding: 0;
}
QPushButton#sidebarToggle:hover {
    background: #E2E8F0;
    border-color: #94A3B8;
}
QPushButton#sidebarToggle:checked {
    background: #EEF2F6;
    border-color: #4F46E5;
}

QPushButton#themeToggle {
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    color: #0F172A;
    font-size: 16px;
    min-height: 38px;
    min-width: 38px;
    max-height: 38px;
    max-width: 38px;
    padding: 0;
}
QPushButton#themeToggle:hover {
    background: #E2E8F0;
    border-color: #94A3B8;
}

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4F46E5, stop:1 #06B6D4);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #FFFFFF;
    min-height: 42px;
    padding: 0 20px;
    font-size: 13px;
    font-weight: 700;
    border-radius: 10px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366F1, stop:1 #22D3EE);
    border-color: rgba(255, 255, 255, 0.25);
}
QPushButton#primary[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #059669, stop:1 #10B981);
    border-color: #34D399;
    color: #FFFFFF;
}
QPushButton#primary[paused="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #D97706, stop:1 #F59E0B);
    border-color: #FBBF24;
    color: #FFFFFF;
}

/* ───────────── Inputs ───────────── */
QComboBox {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    min-height: 32px;
    padding: 0 12px;
    color: #0F172A;
    font-size: 12px;
}
QComboBox:hover { 
    border-color: #94A3B8; 
}
QComboBox::drop-down { 
    border: none; 
    width: 28px; 
}
QComboBox QAbstractItemView {
    background: #FFFFFF; 
    border: 1px solid #CBD5E1;
    selection-background-color: #4F46E5;
    selection-color: #FFFFFF;
}

QDoubleSpinBox {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    min-height: 28px;
    padding: 0 6px;
    color: #0284C7;
    font-size: 11px;
    font-weight: 700;
}
QDoubleSpinBox:hover, QDoubleSpinBox:focus { 
    border-color: #4F46E5; 
}

QCheckBox { 
    color: #475569; 
    font-size: 11px; 
    spacing: 7px; 
}
QCheckBox::indicator {
    width: 15px; 
    height: 15px;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:hover { 
    border-color: #4F46E5; 
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4F46E5, stop:1 #6366F1);
    border-color: #4F46E5;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #E2E8F0;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4F46E5, stop:1 #06B6D4);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #4F46E5;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { 
    background: #F8FAFC; 
    border-color: #06B6D4;
}

QLabel#valueBadge {
    color: #0284C7;
    background: #E0F2FE;
    border: 1px solid #BAE6FD;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 750;
}
QLabel#rangeHint {
    color: #64748B;
    font-size: 9px;
    font-weight: 600;
}

/* ───────────── Developer Panel ───────────── */
QFrame#developerRow {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}
QFrame#developerRow:hover {
    background: #F8FAFC;
    border-color: #CBD5E1;
}
QLabel#developerGroup {
    color: #4F46E5;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding-top: 8px;
}
QLabel#developerName { 
    color: #0F172A; 
    font-size: 11px; 
    font-weight: 650; 
}
QLabel#developerHint { 
    color: #64748B; 
    font-size: 9.5px; 
}

QScrollArea#developerScroll, QScrollArea#developerScroll > QWidget, QWidget#developerBody { 
    background: transparent; 
}
QFrame#developerNotice {
    background: #E0F2FE;
    border: 1px solid #BAE6FD;
    border-radius: 8px;
}
QLabel#developerNoticeText { 
    color: #0284C7; 
    font-size: 11px; 
}

/* ───────────── Error Banner ───────────── */
QFrame#errorFrame {
    background: #FEE2E2;
    border: 1px solid #EF4444;
    border-left: 4px solid #EF4444;
    border-radius: 8px;
}
QLabel#errorText {
    color: #991B1B;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#errorDismiss {
    background: transparent;
    border: none;
    color: #EF4444;
    font-size: 14px;
    font-weight: 750;
    min-height: 20px;
    min-width: 24px;
    padding: 0;
}
QPushButton#errorDismiss:hover { 
    color: #B91C1C; 
}

/* ───────────── Progress & Scrollbars ───────────── */
QProgressBar {
    border: none;
    background: #E2E8F0;
    height: 4px;
    border-radius: 2px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4F46E5, stop:1 #06B6D4);
    border-radius: 2px;
}
QScrollBar:vertical {
    background: transparent; 
    width: 6px; 
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { 
    background: #94A3B8; 
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    height: 0; 
}
"""
