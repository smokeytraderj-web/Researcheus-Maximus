"""Shared editorial navy, warm-white, and restrained-gold application theme."""

STYLESHEET = """
QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 13px; }
QWidget#AppRoot { background: #FFFFFF; color: #1B2A4A; }
QFrame#TopBar { background: #1B2A4A; border-bottom: 2px solid #BFA054; }
QLabel#Brand { color: #FFFFFF; font-family: Georgia, "Times New Roman", serif; font-size: 18px; font-weight: 700; }
QFrame#BrandDivider { background: #46567A; }
QLabel#Firm { color: #D8BF7D; font-size: 9px; font-weight: 700; letter-spacing: 0.3px; }
QLabel#Title { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 30px; font-weight: 700; }
QLabel#Subtitle { color: #657386; font-size: 12px; }
QLabel#Section { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 18px; font-weight: 700; }
QLabel#PrimaryTitle { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 19px; font-weight: 700; }
QLabel#Eyebrow { color: #A7863F; font-size: 10px; font-weight: 700; }
QLabel#FieldHelp { color: #718096; font-size: 11px; }
QLabel#SettingsSummary { color: #64748B; font-size: 11px; padding: 6px 2px; }
QFrame#Card, QFrame#PrimaryPanel, QFrame#ToolPanel {
    background: #FFFFFF;
    border: 1px solid #D8DEE8;
    border-radius: 9px;
}
QFrame#PrimaryPanel { border-top: 3px solid #BFA054; }
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
    background: #FBFCFE;
    border: 1px solid #CBD4E1;
    border-radius: 7px;
    padding: 6px 10px;
    min-height: 28px;
    color: #1B2A4A;
    selection-background-color: #D9C58E;
}
QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover { border-color: #AAB6C6; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { background: #FFFFFF; border: 2px solid #BFA054; }
QComboBox::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    min-width: 24px;
}
QPlainTextEdit#DeepResearchQuery {
    min-height: 150px;
    font-size: 15px;
    padding: 10px 12px;
}
QPlainTextEdit#ComparisonQuery {
    min-height: 150px;
    font-size: 15px;
    padding: 10px 12px;
}
QPlainTextEdit#ModificationRequest {
    min-height: 66px;
    font-size: 13px;
    padding: 8px 10px;
}
QPushButton { background: #1B2A4A; color: #FFFFFF; border: 1px solid #1B2A4A; border-radius: 7px; padding: 11px 20px; font-weight: 700; }
QPushButton:hover { background: #273A60; border-color: #273A60; }
QPushButton:pressed { background: #13203A; }
QPushButton#Secondary { background: #FFFFFF; color: #1B2A4A; border: 1px solid #CBD4E1; }
QPushButton#Secondary:hover { background: #F5F7FA; border-color: #AAB6C6; }
QPushButton#Gold { background: #BFA054; color: #FFFFFF; border: 1px solid #BFA054; }
QPushButton#Gold:hover { background: #A88742; border-color: #A88742; }
QPushButton#ToolAction { background: #F4F6F9; color: #1B2A4A; border: 1px solid #D8DEE8; padding: 9px 15px; }
QPushButton#ToolAction:hover { background: #E9EDF3; }
QPushButton#Settings { background: transparent; color: #F2E9D3; border: 1px solid #71809A; padding: 7px 14px; }
QPushButton#Settings:hover { background: #FFFFFF; color: #1B2A4A; border-color: #FFFFFF; }
QTextBrowser { background: #FFFFFF; border: 1px solid #D8DEE8; border-radius: 9px; padding: 14px; }
QProgressBar { border: 1px solid #D0D6DD; border-radius: 5px; background: #FFFFFF; text-align: center; }
QProgressBar::chunk { background: #BFA054; border-radius: 4px; }
"""
