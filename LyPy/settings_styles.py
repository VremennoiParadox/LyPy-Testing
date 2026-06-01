"""Qt stylesheets for the inline settings panel (portable, no platform APIs)."""

PANEL_SS = """
QWidget#settingsPanel {
    background: transparent;
}

QScrollArea#settingsScroll {
    background: transparent;
    border: none;
}
QScrollArea#settingsScroll > QWidget > QWidget#settingsScrollContent {
    background: transparent;
}

QLabel#sectionTitle {
    color: rgba(255,255,255,0.45);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    padding: 16px 0 6px 0;
    background: transparent;
}

QFrame#settingsDivider {
    background: rgba(255,255,255,0.08);
    max-height: 1px;
    min-height: 1px;
    border: none;
}

QLabel#settingLabel {
    color: rgba(255,255,255,0.88);
    font-size: 13px;
    background: transparent;
}

QLabel#valueLabel {
    color: rgba(255,255,255,0.55);
    font-size: 12px;
    font-weight: 500;
    min-width: 40px;
    background: transparent;
}

QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255,255,255,0.10);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: rgba(255,255,255,0.92);
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: rgba(255,255,255,0.55);
    border-radius: 2px;
}

QCheckBox#switchCheck {
    spacing: 10px;
    color: rgba(255,255,255,0.88);
    font-size: 13px;
}
QCheckBox#switchCheck::indicator {
    width: 42px;
    height: 24px;
    border-radius: 12px;
    background: rgba(255,255,255,0.18);
}
QCheckBox#switchCheck::indicator:checked {
    background: rgba(30, 215, 96, 0.85);
}
QCheckBox#switchCheck::indicator:unchecked:hover {
    background: rgba(255,255,255,0.26);
}
QCheckBox#switchCheck::indicator:checked:hover {
    background: rgba(30, 215, 96, 1.0);
}

QPushButton#collapseHeader {
    background: transparent;
    border: none;
    color: rgba(255,255,255,0.45);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-align: left;
    padding: 16px 0 6px 0;
}
QPushButton#collapseHeader:hover {
    color: rgba(255,255,255,0.65);
}

QLineEdit#settingsField {
    color: rgba(255,255,255,0.95);
    background: rgba(0,0,0,0.22);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
    selection-background-color: rgba(30,215,96,0.35);
}
QLineEdit#settingsField:focus {
    border-color: rgba(255,255,255,0.18);
}

QLabel#fieldCaption {
    color: rgba(255,255,255,0.50);
    font-size: 11px;
    background: transparent;
}

QPushButton#backBtn {
    background: transparent;
    color: rgba(255,255,255,0.65);
    border: none;
    font-size: 22px;
    padding: 0;
}
QPushButton#backBtn:hover { color: #fff; }

QPushButton#textAction {
    background: transparent;
    border: none;
    color: rgba(255,255,255,0.50);
    font-size: 12px;
    padding: 6px 10px;
}
QPushButton#textAction:hover {
    color: rgba(255,255,255,0.90);
}

QPushButton#textActionDanger {
    background: transparent;
    border: none;
    color: rgba(255,120,120,0.55);
    font-size: 12px;
    padding: 6px 10px;
}
QPushButton#textActionDanger:hover {
    color: rgba(255,100,100,0.95);
}

QPushButton#linkAction {
    background: transparent;
    border: none;
    color: rgba(255,255,255,0.45);
    font-size: 12px;
    text-align: left;
    padding: 8px 0;
}
QPushButton#linkAction:hover {
    color: rgba(255,255,255,0.80);
}
"""
