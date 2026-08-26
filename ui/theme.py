"""Shared editorial navy, warm-white, and restrained-gold application theme."""

STYLESHEET = """
QWidget { font-family: "Segoe UI", Arial, sans-serif; }
QWidget#AppRoot { background: #F6F4EF; color: #1B2B45; }
QFrame#TopBar { background: #1B2B49; border-bottom: 1px solid #C49A3A; }
QLabel#Brand { color: #FFFFFF; font-family: Georgia, "Times New Roman", serif; font-size: 17px; font-weight: 700; }
QLabel#Firm { color: #D4B865; font-size: 9px; font-weight: 600; }
QLabel#Workspace { color: #F1E7C8; font-size: 9px; font-weight: 600; }
QLabel#Title { color: #1B2B49; font-family: Georgia, "Times New Roman", serif; font-size: 27px; font-weight: 700; }
QLabel#Subtitle { color: #657386; font-size: 12px; }
QLabel#Section { color: #1B2B49; font-family: Georgia, "Times New Roman", serif; font-size: 16px; font-weight: 700; }
QLabel#PrimaryTitle { color: #1B2B49; font-family: Georgia, "Times New Roman", serif; font-size: 18px; font-weight: 700; }
QLabel#Eyebrow { color: #B58C34; font-size: 10px; font-weight: 700; }
QLabel#FieldHelp { color: #7A8796; font-size: 11px; }
QLabel#SettingsSummary { color: #657386; font-size: 11px; padding: 5px 2px; }
QFrame#HeroPanel { background: #1B2B49; border-radius: 2px; }
QFrame#HeroRule { background: #D1AA45; border: 0; }
QLabel#HeroEyebrow { color: #E3C363; font-size: 10px; font-weight: 700; }
QLabel#HeroTitle { color: #FFFFFF; font-family: Georgia, "Times New Roman", serif; font-size: 31px; font-weight: 700; }
QLabel#HeroSubtitle { color: #EEF1F6; font-size: 12px; }
QLabel#ResearchPaths { color: #B58C34; font-size: 10px; font-weight: 700; padding-top: 3px; }
QLabel#ModeNumber { color: #B58C34; font-family: Georgia, "Times New Roman", serif; font-size: 14px; font-weight: 700; }
QLabel#ModeTitle { color: #1B2B49; font-family: Georgia, "Times New Roman", serif; font-size: 18px; font-weight: 700; }
QLabel#ModeDescription { color: #627087; font-size: 11px; }
QLabel#ModeHint { color: #7A8796; font-size: 10px; }
QFrame#Card, QFrame#PrimaryPanel, QFrame#ToolPanel, QFrame#PrimaryModePanel, QFrame#ModePanel {
    background: #FFFFFF;
    border: 1px solid #DED9CF;
    border-radius: 3px;
}
QFrame#PrimaryPanel, QFrame#PrimaryModePanel, QFrame#ModePanel { border-top: 3px solid #C39A3D; }
QFrame#ModePanel { min-height: 118px; }
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #C8CED7;
    border-radius: 3px;
    padding: 4px 8px;
    min-height: 26px;
    color: #1B2B45;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #B58C34; }
QComboBox::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    min-width: 24px;
}
QPlainTextEdit#ResearchQuery {
    min-height: 80px;
    font-size: 14px;
    padding: 10px 12px;
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
QPushButton { background: #1B2B49; color: #FFFFFF; border: 0; border-radius: 3px; padding: 10px 18px; font-weight: 700; }
QPushButton:hover { background: #294367; }
QPushButton#Secondary { background: #E8EBEF; color: #1B2B49; }
QPushButton#Gold { background: #B9914C; color: #FFFFFF; }
QPushButton#Gold:hover { background: #9E783B; }
QPushButton#ToolAction { background: #EEF1F4; color: #1B2B49; padding: 8px 14px; }
QPushButton#ToolAction:hover { background: #E2E7EC; }
QPushButton#ModeLink {
    background: transparent;
    color: #1B2B49;
    border: 0;
    padding: 4px 0;
    text-align: left;
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 700;
}
QPushButton#ModeLink:hover { color: #B58C34; }
QPushButton#Settings { background: transparent; color: #F2E6C5; border: 1px solid #7B879B; padding: 6px 12px; }
QPushButton#Settings:hover { background: #FFFFFF; color: #1B2B49; }
QTextBrowser { background: #FFFFFF; border: 1px solid #DCE1E6; border-radius: 8px; padding: 12px; }
QProgressBar { border: 1px solid #D0D6DD; border-radius: 5px; background: #FFFFFF; text-align: center; }
QProgressBar::chunk { background: #B9914C; border-radius: 4px; }
"""
