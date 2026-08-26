"""Shared navy, white, and gold application theme."""

STYLESHEET = """
QWidget#AppRoot { background: #F5F6F8; color: #24364A; }
QFrame#TopBar { background: #14263D; }
QLabel#Brand { color: #FFFFFF; font-size: 20px; font-weight: 700; }
QLabel#Firm { color: #C9AE79; font-size: 10px; font-weight: 600; }
QLabel#Title { color: #14263D; font-size: 27px; font-weight: 700; }
QLabel#Subtitle { color: #657386; font-size: 12px; }
QLabel#Section { color: #14263D; font-size: 15px; font-weight: 700; }
QLabel#SettingsSummary { color: #657386; font-size: 11px; padding: 5px 2px; }
QFrame#Card { background: #FFFFFF; border: 1px solid #DCE1E6; border-radius: 10px; }
QLineEdit, QComboBox, QDoubleSpinBox {
    background: #FFFFFF;
    border: 1px solid #C9D0D8;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 26px;
    color: #24364A;
}
QComboBox::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    min-width: 24px;
}
QPushButton { background: #14263D; color: #FFFFFF; border: 0; border-radius: 6px; padding: 10px 18px; font-weight: 700; }
QPushButton:hover { background: #203B5D; }
QPushButton#Secondary { background: #E8EBEF; color: #14263D; }
QPushButton#Gold { background: #B08D57; color: #FFFFFF; }
QTextBrowser { background: #FFFFFF; border: 1px solid #DCE1E6; border-radius: 8px; padding: 12px; }
QProgressBar { border: 1px solid #D0D6DD; border-radius: 5px; background: #FFFFFF; text-align: center; }
QProgressBar::chunk { background: #B08D57; border-radius: 4px; }
"""
