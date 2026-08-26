"""Shared navy, white, and gold application theme."""

STYLESHEET = """
QWidget#AppRoot { background: #F5F6F8; color: #24364A; }
QFrame#TopBar { background: #14263D; }
QLabel#Brand { color: #FFFFFF; font-size: 20px; font-weight: 700; }
QLabel#Firm { color: #C9AE79; font-size: 10px; font-weight: 600; }
QLabel#Workspace { color: #F0D49A; font-size: 10px; font-weight: 700; }
QLabel#Title { color: #14263D; font-size: 27px; font-weight: 700; }
QLabel#Subtitle { color: #657386; font-size: 12px; }
QLabel#Section { color: #14263D; font-size: 15px; font-weight: 700; }
QLabel#Eyebrow { color: #B08D57; font-size: 10px; font-weight: 700; }
QLabel#FieldHelp { color: #7A8796; font-size: 11px; }
QLabel#SettingsSummary { color: #657386; font-size: 11px; padding: 5px 2px; }
QFrame#Card { background: #FFFFFF; border: 1px solid #DCE1E6; border-radius: 12px; }
QFrame#DeepPanel { background: #14263D; border: 1px solid #203B5D; border-radius: 10px; }
QFrame#ComparePanel { background: #FFFFFF; border: 1px solid #C9AE79; border-radius: 10px; }
QFrame#DeepPanel QLabel#Section { color: #FFFFFF; font-size: 17px; }
QFrame#DeepPanel QLabel#Subtitle { color: #C8D1DC; line-height: 1.3; }
QFrame#DeepPanel QLabel#DeepFeatures { color: #E7ECF2; font-size: 11px; line-height: 1.5; padding-top: 5px; }
QFrame#ComparePanel QLabel#Section { color: #14263D; font-size: 17px; }
QFrame#ComparePanel QLabel#DeepFeatures { color: #6E5A35; font-size: 11px; padding-top: 5px; }
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #C9D0D8;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 26px;
    color: #24364A;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #B08D57; }
QComboBox::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    min-width: 24px;
}
QPlainTextEdit#ResearchQuery {
    min-height: 104px;
    font-size: 16px;
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
QPushButton { background: #14263D; color: #FFFFFF; border: 0; border-radius: 6px; padding: 10px 18px; font-weight: 700; }
QPushButton:hover { background: #203B5D; }
QPushButton#Secondary { background: #E8EBEF; color: #14263D; }
QPushButton#Gold { background: #B08D57; color: #FFFFFF; }
QPushButton#DeepAction { background: #FFFFFF; color: #14263D; }
QPushButton#DeepAction:hover { background: #F0D49A; }
QPushButton#CompareAction { background: #B08D57; color: #FFFFFF; }
QPushButton#CompareAction:hover { background: #987744; }
QPushButton#Settings { background: transparent; color: #657386; border: 1px solid #D7DDE3; padding: 8px 14px; }
QPushButton#Settings:hover { background: #FFFFFF; color: #14263D; }
QTextBrowser { background: #FFFFFF; border: 1px solid #DCE1E6; border-radius: 8px; padding: 12px; }
QProgressBar { border: 1px solid #D0D6DD; border-radius: 5px; background: #FFFFFF; text-align: center; }
QProgressBar::chunk { background: #B08D57; border-radius: 4px; }
"""
