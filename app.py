"""Technical Analyst Agent desktop entry point."""

from __future__ import annotations

import sys

from security.certificates import configure_certificate_trust


def main() -> int:
    # Configure native certificate trust before network libraries are imported.
    configure_certificate_trust()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    from ui.main_window import MainWindow
    from ui.theme import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName("Technical Analyst Agent")
    app.setOrganizationName("Gottfried & Somberg Wealth Management")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
