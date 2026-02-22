"""
YT-DLP GUI — entry point
Run:  python main.py
"""
from __future__ import annotations

import sys
import io
import os

# Force UTF-8 for all I/O on Windows (compiled exe defaults to cp1252 otherwise).
os.environ.setdefault("PYTHONUTF8", "1")
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.settings import get_settings, resource_path
from app.theme import ThemeManager


def main() -> None:
    # High-DPI support (Qt 6 enables it by default; explicit on Qt 5)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("YT-DLP GUI")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("YT-DLP GUI")

    # App icon — used by taskbar, alt-tab, and all child dialogs.
    # resource_path works both in dev (project root) and PyInstaller bundle.
    _icon_path = resource_path("icon.ico")
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    settings  = get_settings()
    theme_mgr = ThemeManager(app)

    # Apply saved theme preference
    saved_theme = settings.get("theme", "dark")
    if saved_theme != "dark":
        theme_mgr.toggle()

    def _save_theme(theme: str) -> None:
        settings.set("theme", theme)

    theme_mgr.theme_changed.connect(_save_theme)

    win = MainWindow(theme_mgr, settings)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
