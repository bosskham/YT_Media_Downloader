from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget, QMessageBox,
)

from ..download_manager import DownloadManager
from ..settings import Settings
from ..workers.info_worker import InfoWorker

# ── helpers ───────────────────────────────────────────────────────────────────

VIDEO_QUALITIES = [
    ("Best (Auto)",   "bestvideo+bestaudio/best"),
    ("4K (2160p)",    "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]"),
    ("2K (1440p)",    "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440]"),
    ("1080p FHD",     "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"),
    ("720p HD",       "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"),
    ("480p",          "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]"),
    ("360p",          "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]"),
    ("Audio only",    "bestaudio/best"),
]

VIDEO_FORMATS = ["mp4", "mkv", "webm"]


def _safe_folder(name: str, max_len: int = 60) -> str:
    """Strip characters invalid in folder names and trim to max_len."""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()[:max_len]


def _make_nav_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("role", "nav")
    btn.setCheckable(True)
    return btn


def _make_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    return sep


def _output_row(initial: str) -> tuple[QHBoxLayout, QLineEdit, QPushButton]:
    row = QHBoxLayout()
    edit = QLineEdit(initial)
    edit.setPlaceholderText("Output directory…")
    browse = QPushButton("Browse…")
    browse.setProperty("role", "secondary")
    browse.setMinimumWidth(90)
    row.addWidget(edit)
    row.addWidget(browse)
    return row, edit, browse


# ── sub-tab: Single video ─────────────────────────────────────────────────────

class SingleVideoWidget(QWidget):
    def __init__(self, manager: DownloadManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._info_worker: Optional[InfoWorker] = None
        self._fetch_timer = QTimer(self)
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.timeout.connect(self._auto_fetch)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(12)

        # URL row
        url_row = QHBoxLayout()
        url_lbl = QLabel("URL:")
        url_lbl.setFixedWidth(36)
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self._url_edit.textChanged.connect(self._on_url_changed)
        self._fetch_btn = QPushButton("Fetch info")
        self._fetch_btn.setProperty("role", "secondary")
        self._fetch_btn.clicked.connect(self._do_fetch)
        url_row.addWidget(url_lbl)
        url_row.addWidget(self._url_edit)
        url_row.addWidget(self._fetch_btn)
        root.addLayout(url_row)

        # Info preview card
        self._info_card = QFrame()
        self._info_card.setProperty("role", "card")
        self._info_card.setFixedHeight(56)
        self._info_card.hide()
        ic_lay = QHBoxLayout(self._info_card)
        ic_lay.setContentsMargins(12, 8, 12, 8)
        self._info_title = QLabel("")
        self._info_title.setStyleSheet("font-weight: 600;")
        self._info_dur = QLabel("")
        self._info_dur.setProperty("role", "muted")
        ic_lay.addWidget(self._info_title)
        ic_lay.addStretch()
        ic_lay.addWidget(self._info_dur)
        root.addWidget(self._info_card)

        # Options row
        opts_row = QHBoxLayout()

        opts_row.addWidget(QLabel("Quality:"))
        self._quality_combo = QComboBox()
        for label, _ in VIDEO_QUALITIES:
            self._quality_combo.addItem(label)
        opts_row.addWidget(self._quality_combo)

        opts_row.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        self._format_combo.addItems(VIDEO_FORMATS)
        opts_row.addWidget(self._format_combo)

        opts_row.addStretch()
        root.addLayout(opts_row)

        # Output dir
        out_lbl = QLabel("Save to:")
        root.addWidget(out_lbl)
        out_row, self._out_edit, browse_btn = _output_row(
            self._settings.get("output_dir", "")
        )
        browse_btn.clicked.connect(self._browse)
        root.addLayout(out_row)

        root.addStretch()

        # Download button
        self._dl_btn = QPushButton("⬇  Download")
        self._dl_btn.setFixedHeight(42)
        self._dl_btn.clicked.connect(self._download)
        root.addWidget(self._dl_btn)

        # Seed initial combo values from settings
        idx = self._format_combo.findText(self._settings.get("video_format", "mp4"))
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

    def _on_url_changed(self, text: str) -> None:
        if text.strip().startswith("http"):
            self._fetch_timer.start(1200)

    def _auto_fetch(self) -> None:
        if self._url_edit.text().strip():
            self._do_fetch()

    def _do_fetch(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("Fetching…")
        self._info_card.hide()
        worker = InfoWorker(url, flat=False)
        worker.info_ready.connect(self._on_info)
        worker.error.connect(self._on_fetch_error)
        worker.finished.connect(lambda: self._fetch_btn.setEnabled(True))
        worker.finished.connect(lambda: self._fetch_btn.setText("Fetch info"))
        self._info_worker = worker
        worker.start()

    def _on_info(self, info: dict) -> None:
        title = info.get("title", "Unknown title")
        dur = info.get("duration_string") or _fmt_dur(info.get("duration", 0))
        thumb = info.get("thumbnail", "")
        self._info_title.setText(title[:70])
        self._info_dur.setText(dur)
        self._info_card.show()
        self._current_info = info

    def _on_fetch_error(self, msg: str) -> None:
        self._fetch_btn.setText("Fetch info")
        self._fetch_btn.setEnabled(True)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Output directory", self._out_edit.text() or str(Path.home())
        )
        if path:
            self._out_edit.setText(path)

    def _download(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a URL first.")
            return
        quality_fmt = VIDEO_QUALITIES[self._quality_combo.currentIndex()][1]
        container   = self._format_combo.currentText()
        out_dir     = self._out_edit.text().strip() or self._settings.get("output_dir")
        os.makedirs(out_dir, exist_ok=True)

        ydl_opts = {
            "format":               quality_fmt,
            "merge_output_format":  container,
            "outtmpl":              os.path.join(out_dir, "%(title)s.%(ext)s"),
            "noplaylist":           True,
            "quiet":                True,
            "no_warnings":          True,
        }
        info = getattr(self, "_current_info", {})
        metadata = {
            "title":     info.get("title", url),
            "thumbnail": info.get("thumbnail", ""),
        }
        self._manager.add_download(url, ydl_opts, metadata)


# ── sub-tab: Playlist / Channel (shared logic) ───────────────────────────────

class PlaylistWidget(QWidget):
    def __init__(
        self,
        manager: DownloadManager,
        settings: Settings,
        mode: str = "playlist",   # "playlist" | "channel"
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._mode = mode
        self._entries: list[dict] = []
        self._collection_title: str = ""
        self._info_worker: Optional[InfoWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(12)

        placeholder = {
            "playlist": "https://www.youtube.com/playlist?list=…",
            "channel":  "https://www.youtube.com/@ChannelName or /channel/…",
        }[self._mode]

        # URL row (full width)
        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(placeholder)
        self._fetch_btn = QPushButton("Fetch videos")
        self._fetch_btn.setProperty("role", "secondary")
        self._fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(self._url_edit)
        url_row.addWidget(self._fetch_btn)
        root.addLayout(url_row)

        # Status label (full width)
        self._status_lbl = QLabel("Enter a URL and click 'Fetch videos' to list available videos.")
        self._status_lbl.setProperty("role", "muted")
        root.addWidget(self._status_lbl)

        # ── Horizontal split: controls (left) | video list (right) ───────────
        body = QHBoxLayout()
        body.setSpacing(16)

        # Left: options + output + download
        left = QVBoxLayout()
        left.setSpacing(10)

        # Select all / none bar
        sel_row = QHBoxLayout()
        self._sel_all_btn = QPushButton("Select all")
        self._sel_all_btn.setProperty("role", "secondary")
        self._sel_all_btn.setFixedHeight(28)
        self._sel_all_btn.clicked.connect(self._select_all)
        self._sel_none_btn = QPushButton("Select none")
        self._sel_none_btn.setProperty("role", "secondary")
        self._sel_none_btn.setFixedHeight(28)
        self._sel_none_btn.clicked.connect(self._select_none)
        sel_row.addWidget(self._sel_all_btn)
        sel_row.addWidget(self._sel_none_btn)
        sel_row.addStretch()
        self._sel_count_lbl = QLabel("")
        self._sel_count_lbl.setProperty("role", "muted")
        sel_row.addWidget(self._sel_count_lbl)
        left.addLayout(sel_row)

        # Options row
        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Quality:"))
        self._quality_combo = QComboBox()
        for label, _ in VIDEO_QUALITIES:
            self._quality_combo.addItem(label)
        opts_row.addWidget(self._quality_combo)
        opts_row.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        self._format_combo.addItems(VIDEO_FORMATS)
        opts_row.addWidget(self._format_combo)
        opts_row.addStretch()
        left.addLayout(opts_row)

        self._subfolder_chk = QCheckBox("Save in sub-folder")
        self._subfolder_chk.setChecked(True)
        left.addWidget(self._subfolder_chk)

        # Output dir
        out_row, self._out_edit, browse_btn = _output_row(
            self._settings.get("output_dir", "")
        )
        browse_btn.clicked.connect(self._browse)
        left.addLayout(out_row)

        left.addStretch()

        # Download button
        self._dl_btn = QPushButton("⬇  Download selected")
        self._dl_btn.setFixedHeight(42)
        self._dl_btn.clicked.connect(self._download_selected)
        left.addWidget(self._dl_btn)

        body.addLayout(left, 2)

        # Right: video list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.itemChanged.connect(self._update_sel_count)
        body.addWidget(self._list, 3)

        root.addLayout(body)

    # ── slots ─────────────────────────────────────────────
    def _fetch(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        self._list.clear()
        self._entries = []
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("Fetching…")
        self._status_lbl.setText("Fetching video list…")

        worker = InfoWorker(url, flat=True)
        worker.info_ready.connect(self._on_info)
        worker.error.connect(self._on_fetch_error)
        worker.finished.connect(lambda: (
            self._fetch_btn.setEnabled(True),
            self._fetch_btn.setText("Fetch videos"),
        ))
        self._info_worker = worker
        worker.start()

    def _on_info(self, info: dict) -> None:
        entries = info.get("entries", [])
        if not entries and info.get("_type") == "video":
            entries = [info]
        self._entries = [e for e in entries if e]
        self._collection_title = info.get("title", "")
        self._list.clear()
        for entry in self._entries:
            title = entry.get("title") or entry.get("id", "Unknown")
            dur   = _fmt_dur(entry.get("duration", 0))
            item  = QListWidgetItem(f"{title}  [{dur}]")
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        n = len(self._entries)
        ptype = "channel" if self._mode == "channel" else "playlist"
        self._status_lbl.setText(
            f"Found {n} video{'s' if n != 1 else ''} in {ptype}: "
            f"{self._collection_title}"
        )
        self._update_sel_count()

    def _on_fetch_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")

    def _select_all(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _update_sel_count(self) -> None:
        total = self._list.count()
        checked = sum(
            1 for i in range(total)
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        )
        self._sel_count_lbl.setText(f"{checked} / {total} selected")

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Output directory", self._out_edit.text() or str(Path.home())
        )
        if path:
            self._out_edit.setText(path)

    def _download_selected(self) -> None:
        selected = [
            (i, self._entries[i])
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if not selected:
            QMessageBox.warning(self, "Nothing selected", "Please select at least one video.")
            return

        quality_fmt = VIDEO_QUALITIES[self._quality_combo.currentIndex()][1]
        container   = self._format_combo.currentText()
        out_dir     = self._out_edit.text().strip() or self._settings.get("output_dir")
        use_sub     = self._subfolder_chk.isChecked()
        os.makedirs(out_dir, exist_ok=True)

        for list_idx, entry in selected:
            num       = list_idx + 1
            video_url = entry.get("url") or entry.get("webpage_url") or entry.get("id", "")
            if not video_url.startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_url}"
            title = entry.get("title", "Unknown")
            thumb = entry.get("thumbnail", "")
            if use_sub:
                sub = _safe_folder(self._collection_title) or "playlist"
                tpl = os.path.join(out_dir, sub, f"{num:02d}. %(title)s.%(ext)s")
            else:
                tpl = os.path.join(out_dir, f"{num:02d}. %(title)s.%(ext)s")

            ydl_opts = {
                "format":               quality_fmt,
                "merge_output_format":  container,
                "outtmpl":              tpl,
                "noplaylist":           True,
                "quiet":                True,
                "no_warnings":          True,
            }
            self._manager.add_download(
                video_url, ydl_opts, {"title": title, "thumbnail": thumb}
            )


# ── NavBar (pill nav for sub-tabs) ───────────────────────────────────────────

class NavBar(QWidget):
    def __init__(self, labels: list[str], stack: QStackedWidget, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, label in enumerate(labels):
            btn = _make_nav_btn(label)
            btn.setChecked(i == 0)
            self._group.addButton(btn, i)
            lay.addWidget(btn)
            btn.clicked.connect(lambda _, idx=i: stack.setCurrentIndex(idx))
        lay.addStretch()


# ── VideoTab (main tab) ───────────────────────────────────────────────────────

class VideoTab(QWidget):
    def __init__(self, manager: DownloadManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._manager  = manager
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(12)

        # Description
        desc = QLabel("Download YouTube videos in your preferred quality and format.")
        desc.setProperty("role", "muted")
        root.addWidget(desc)

        root.addWidget(_make_sep())

        # Stack
        self._stack = QStackedWidget()
        single_w   = SingleVideoWidget(self._manager, self._settings)
        playlist_w = PlaylistWidget(self._manager, self._settings, mode="playlist")
        channel_w  = PlaylistWidget(self._manager, self._settings, mode="channel")
        self._stack.addWidget(single_w)
        self._stack.addWidget(playlist_w)
        self._stack.addWidget(channel_w)

        # NavBar above stack
        nav = NavBar(["Single Video", "Playlist", "Channel"], self._stack)
        root.addWidget(nav)
        root.addWidget(self._stack)


# ── utility ───────────────────────────────────────────────────────────────────

def _fmt_dur(secs: int | None) -> str:
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
