from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About YT-DLP GUI")
        self.setMinimumWidth(460)
        self.setMaximumWidth(460)
        self.setSizeGripEnabled(False)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 28)
        root.setSpacing(0)

        # ── App identity ──────────────────────────────────
        app_icon = QLabel("▶")
        app_icon.setProperty("role", "about-icon")
        app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(app_icon)

        root.addSpacing(10)

        app_name = QLabel("YT-DLP GUI")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_name.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(app_name)

        version = QLabel("Version 1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setProperty("role", "muted")
        root.addWidget(version)

        root.addSpacing(6)

        desc = QLabel("A modern YouTube video & music downloader\npowered by yt-dlp and PySide6.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setProperty("role", "muted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addSpacing(24)

        # ── Divider ───────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        root.addSpacing(20)

        # ── Developer credit ──────────────────────────────
        dev_label = QLabel("Developer")
        dev_label.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        dev_label.setProperty("role", "muted")
        root.addWidget(dev_label)

        root.addSpacing(10)

        # Name + aka
        name_row = QHBoxLayout()
        name_lbl = QLabel("Boromey Han")
        name_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        aka_lbl = QLabel("aka 1ClickDev · dashNdot")
        aka_lbl.setProperty("role", "muted")
        aka_lbl.setStyleSheet("font-size: 12px; padding-top: 3px;")
        name_row.addWidget(name_lbl)
        name_row.addSpacing(8)
        name_row.addWidget(aka_lbl)
        name_row.addStretch()
        root.addLayout(name_row)

        root.addSpacing(6)

        bio = QLabel("Software Engineer · AI-Powered Desktop Apps\nFull Stack Web Developer · Creator of WTN Suite")
        bio.setProperty("role", "muted")
        bio.setWordWrap(True)
        root.addWidget(bio)

        root.addSpacing(14)

        # Links
        links_row = QHBoxLayout()
        links_row.setSpacing(8)

        for text, url in [
            ("🌐  boromeyhan.me",     "https://boromeyhan.me"),
            ("⌥  GitHub",             "https://github.com/bosskham"),
            ("✉  contact@boromeyhan.me", "mailto:contact@boromeyhan.me"),
        ]:
            btn = QPushButton(text)
            btn.setProperty("role", "secondary")
            btn.setFixedHeight(30)
            btn.setStyleSheet("font-size: 12px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_row.addWidget(btn)

        links_row.addStretch()
        root.addLayout(links_row)

        root.addSpacing(24)

        # ── Divider ───────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        root.addSpacing(16)

        # ── Powered by ────────────────────────────────────
        powered_label = QLabel("Powered by")
        powered_label.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        powered_label.setProperty("role", "muted")
        root.addWidget(powered_label)

        root.addSpacing(8)

        libs_row = QHBoxLayout()
        libs_row.setSpacing(8)
        for lib, url in [
            ("yt-dlp",   "https://github.com/yt-dlp/yt-dlp"),
            ("PySide6",  "https://doc.qt.io/qtforpython/"),
            ("mutagen",  "https://github.com/quodlibet/mutagen"),
            ("FFmpeg",   "https://ffmpeg.org"),
        ]:
            btn = QPushButton(lib)
            btn.setProperty("role", "secondary")
            btn.setFixedHeight(28)
            btn.setStyleSheet("font-size: 12px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            libs_row.addWidget(btn)
        libs_row.addStretch()
        root.addLayout(libs_row)

        root.addSpacing(24)

        # ── Close button ──────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(38)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)
