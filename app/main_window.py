from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from .download_manager import DownloadManager
from .settings import Settings, resource_path
from .tabs.music_tab import MusicTab
from .tabs.video_tab import VideoTab
from .theme import ThemeManager
from .widgets.about_dialog import AboutDialog
from .widgets.download_queue import DownloadQueueWidget
from .widgets.settings_dialog import SettingsDialog


class HeaderWidget(QFrame):
    """Top header bar with logo, title, and actions."""

    def __init__(self, theme: ThemeManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._theme    = theme
        self._settings = settings
        self.setProperty("role", "header")
        self.setFixedHeight(60)
        self._build_ui()
        self._theme.theme_changed.connect(self._on_theme_changed)

    def _build_ui(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(10)

        # App icon / title
        icon_lbl = QLabel("▶")
        icon_lbl.setProperty("role", "header-icon")
        lay.addWidget(icon_lbl)

        title = QLabel("YT Media Downloader")
        title.setProperty("role", "heading")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        lay.addWidget(title)

        lay.addStretch()

        # Theme toggle
        self._theme_btn = QPushButton("☀  Light")
        self._theme_btn.setProperty("role", "secondary")
        self._theme_btn.setFixedHeight(34)
        self._theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self._theme_btn)

        # Settings button
        self._settings_btn = QPushButton("⚙  Settings")
        self._settings_btn.setProperty("role", "secondary")
        self._settings_btn.setFixedHeight(34)
        self._settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(self._settings_btn)

        # About button
        self._about_btn = QPushButton("ℹ  About")
        self._about_btn.setProperty("role", "secondary")
        self._about_btn.setFixedHeight(34)
        self._about_btn.clicked.connect(self._open_about)
        lay.addWidget(self._about_btn)

    def set_parent_window(self, win: "MainWindow") -> None:
        self._parent_window = win

    def _toggle_theme(self) -> None:
        self._theme.toggle()

    def _on_theme_changed(self, theme: str) -> None:
        if theme == "dark":
            self._theme_btn.setText("☀  Light")
        else:
            self._theme_btn.setText("🌙  Dark")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        dlg.exec()

    def _open_about(self) -> None:
        dlg = AboutDialog(self)
        dlg.exec()


class MainWindow(QMainWindow):
    def __init__(self, theme: ThemeManager, settings: Settings) -> None:
        super().__init__()
        self._theme    = theme
        self._settings = settings
        self._manager  = DownloadManager(
            max_concurrent=settings.get("max_concurrent", 2)
        )
        self.setWindowTitle("YT Media Downloader")
        self.setMinimumSize(820, 640)
        self.resize(1280, 800)
        # Window icon (title bar + taskbar) — works in dev and PyInstaller bundle
        _icon_path = resource_path("icon.ico")
        if _icon_path.exists():
            self.setWindowIcon(QIcon(str(_icon_path)))
        self._build_ui()
        # Keep manager concurrent in sync with settings changes
        self._theme.theme_changed.connect(self._on_theme_changed)

    # ── setup ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Header
        self._header = HeaderWidget(self._theme, self._settings)
        root_lay.addWidget(self._header)

        # Splitter: main tabs (left) + download queue (right)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        root_lay.addWidget(self._splitter)

        # ── Left: tab widget ──────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._video_tab = VideoTab(self._manager, self._settings)
        self._music_tab = MusicTab(self._manager, self._settings)

        self._tabs.addTab(self._video_tab, "  Video  ")
        self._tabs.addTab(self._music_tab, "  Music  ")
        self._splitter.addWidget(self._tabs)

        # ── Right: download queue (~33%) ──────────────────
        self._queue_widget = DownloadQueueWidget(self._manager)
        self._queue_widget.setMinimumWidth(260)
        self._splitter.addWidget(self._queue_widget)

        # Default split ratio ~67 / 33
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([860, 420])

        # Status bar
        self.statusBar().showMessage("Ready")
        self._manager.download_added.connect(
            lambda _id, _job: self.statusBar().showMessage(
                f"Download added: {_job.get('metadata', {}).get('title', _job['url'])}"
            )
        )
        self._manager.download_finished.connect(
            lambda _id: self.statusBar().showMessage("Download complete ✓")
        )
        self._manager.download_error.connect(
            lambda _id, msg: self.statusBar().showMessage(f"Error: {msg[:80]}")
        )

    def _on_theme_changed(self, _: str) -> None:
        # Force header to repaint with new stylesheet
        self._header.update()
