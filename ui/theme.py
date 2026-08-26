"""Shared editorial navy, warm-white, and restrained-gold application theme."""

STYLESHEET = """
QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 13px; }
QWidget#AppRoot { background: #FFFFFF; color: #1B2A4A; }
QScrollArea#IntakeScroll, QScrollArea#IntakeScroll > QWidget > QWidget { background: #FFFFFF; border: 0; }
QFrame#TopBar { background: #1B2A4A; border-bottom: 2px solid #BFA054; }
QLabel#Brand { color: #FFFFFF; font-family: Georgia, "Times New Roman", serif; font-size: 19px; font-weight: 700; }
QLabel#Firm { color: #D8BF7D; font-size: 9px; font-weight: 700; letter-spacing: 0.3px; }
QLabel#Workspace { color: #F2E9D3; font-size: 9px; font-weight: 700; }
QLabel#Title { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 30px; font-weight: 700; }
QLabel#Subtitle { color: #657386; font-size: 12px; }
QLabel#Section { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 18px; font-weight: 700; }
QLabel#PrimaryTitle { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 19px; font-weight: 700; }
QLabel#Eyebrow { color: #A7863F; font-size: 10px; font-weight: 700; }
QLabel#FieldHelp { color: #718096; font-size: 11px; }
QLabel#SettingsSummary { color: #64748B; font-size: 11px; padding: 6px 2px; }
QFrame#HeroPanel { background: #1B2A4A; border: 1px solid #1B2A4A; border-radius: 10px; }
QFrame#HeroRule { background: #BFA054; border: 0; }
QLabel#HeroEyebrow { color: #E1C77F; font-size: 10px; font-weight: 700; letter-spacing: 0.4px; }
QLabel#HeroTitle { color: #FFFFFF; font-family: Georgia, "Times New Roman", serif; font-size: 42px; font-weight: 700; }
QLabel#HeroSubtitle { color: #E8EDF5; font-size: 15px; }
QLabel#ResearchPaths { color: #9A7A35; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; padding-top: 6px; }
QLabel#ModeNumber { color: #A7863F; font-family: Georgia, "Times New Roman", serif; font-size: 16px; font-weight: 700; }
QLabel#ModeTitle { color: #1B2A4A; font-family: Georgia, "Times New Roman", serif; font-size: 23px; font-weight: 700; }
QLabel#ModeDescription { color: #526176; font-size: 13px; }
QLabel#ModeHint { color: #718096; font-size: 11px; }
QFrame#Card, QFrame#PrimaryPanel, QFrame#ToolPanel, QFrame#PrimaryModePanel, QFrame#ModePanel {
    background: #FFFFFF;
    border: 1px solid #D8DEE8;
    border-radius: 9px;
}
QFrame#PrimaryPanel, QFrame#PrimaryModePanel, QFrame#ModePanel { border-top: 3px solid #BFA054; }
QFrame#ModePanel { min-height: 168px; }
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
QPlainTextEdit#ResearchQuery {
    min-height: 132px;
    font-size: 16px;
    padding: 15px 17px;
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
QPushButton#ModeLink {
    background: transparent;
    color: #1B2A4A;
    border: 0;
    padding: 6px 0;
    text-align: left;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#ModeLink:hover { color: #A7863F; }
QPushButton#Settings { background: transparent; color: #F2E9D3; border: 1px solid #71809A; padding: 7px 14px; }
QPushButton#Settings:hover { background: #FFFFFF; color: #1B2A4A; border-color: #FFFFFF; }
QTextBrowser { background: #FFFFFF; border: 1px solid #D8DEE8; border-radius: 9px; padding: 14px; }
QProgressBar { border: 1px solid #D0D6DD; border-radius: 5px; background: #FFFFFF; text-align: center; }
QProgressBar::chunk { background: #BFA054; border-radius: 4px; }
"""
