from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from ..settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._s = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load()

    # ── setup ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ── General ──────────────────────────────────────
        gen = QGroupBox("General")
        gen_l = QVBoxLayout(gen)
        gen_l.setSpacing(12)

        # Output directory
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output directory:"))
        self._out_edit = QLineEdit()
        out_row.addWidget(self._out_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setProperty("role", "secondary")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(browse_btn)
        gen_l.addLayout(out_row)

        # Max concurrent
        conc_row = QHBoxLayout()
        conc_row.addWidget(QLabel("Max concurrent downloads:"))
        self._conc_spin = QSpinBox()
        self._conc_spin.setRange(1, 5)
        self._conc_spin.setFixedWidth(80)
        conc_row.addWidget(self._conc_spin)
        conc_row.addStretch()
        gen_l.addLayout(conc_row)

        # Browser cookies (age-restricted / sign-in required videos)
        ck_row = QHBoxLayout()
        ck_row.addWidget(QLabel("Browser cookies (age-restricted videos):"))
        self._cookies_browser = QComboBox()
        self._cookies_browser.addItems([
            "None (disabled)", "Chrome", "Chromium", "Firefox", "Edge", "Brave", "Opera", "Vivaldi",
        ])
        ck_row.addWidget(self._cookies_browser)
        ck_row.addStretch()
        gen_l.addLayout(ck_row)

        ck_note = QLabel("Note: Chrome must be closed first. Use a cookies file to avoid this.")
        ck_note.setProperty("role", "muted")
        gen_l.addWidget(ck_note)

        # Cookies file (Netscape format — takes priority over browser cookies)
        ckf_row = QHBoxLayout()
        ckf_row.addWidget(QLabel("Cookies file (overrides browser above):"))
        self._cookies_file = QLineEdit()
        self._cookies_file.setPlaceholderText("Path to cookies.txt (Netscape format)…")
        ckf_row.addWidget(self._cookies_file)
        ckf_browse = QPushButton("Browse…")
        ckf_browse.setProperty("role", "secondary")
        ckf_browse.setFixedWidth(90)
        ckf_browse.clicked.connect(self._browse_cookies)
        ckf_row.addWidget(ckf_browse)
        gen_l.addLayout(ckf_row)

        root.addWidget(gen)

        # ── Video ────────────────────────────────────────
        vid = QGroupBox("Video")
        vid_l = QVBoxLayout(vid)
        vid_l.setSpacing(12)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Default container:"))
        self._vid_fmt = QComboBox()
        self._vid_fmt.addItems(["mp4", "mkv", "webm"])
        fmt_row.addWidget(self._vid_fmt)
        fmt_row.addStretch()
        vid_l.addLayout(fmt_row)

        root.addWidget(vid)

        # ── Music ────────────────────────────────────────
        mus = QGroupBox("Music")
        mus_l = QVBoxLayout(mus)
        mus_l.setSpacing(12)

        afmt_row = QHBoxLayout()
        afmt_row.addWidget(QLabel("Default audio format:"))
        self._aud_fmt = QComboBox()
        self._aud_fmt.addItems(["mp3", "flac", "aac", "opus", "m4a"])
        afmt_row.addWidget(self._aud_fmt)
        afmt_row.addStretch()
        mus_l.addLayout(afmt_row)

        aqlt_row = QHBoxLayout()
        aqlt_row.addWidget(QLabel("Default audio quality (kbps):"))
        self._aud_quality = QComboBox()
        self._aud_quality.addItems(["320", "256", "192", "128", "96"])
        aqlt_row.addWidget(self._aud_quality)
        aqlt_row.addStretch()
        mus_l.addLayout(aqlt_row)

        self._embed_thumb  = QCheckBox("Embed thumbnail")
        self._embed_meta   = QCheckBox("Embed metadata")
        self._fetch_lyrics = QCheckBox("Fetch and embed lyrics")
        self._playlist_sub = QCheckBox("Save playlist tracks in sub-folder")

        mus_l.addWidget(self._embed_thumb)
        mus_l.addWidget(self._embed_meta)
        mus_l.addWidget(self._fetch_lyrics)
        mus_l.addWidget(self._playlist_sub)

        # Whisper model (used when YouTube has no subtitles)
        wm_row = QHBoxLayout()
        wm_row.addWidget(QLabel("Whisper model (lyrics transcription fallback):"))
        self._whisper_model = QComboBox()
        self._whisper_model.addItems(["tiny", "base", "small", "medium", "large", "turbo"])
        wm_row.addWidget(self._whisper_model)
        wm_note = QLabel("larger = slower but more accurate")
        wm_note.setProperty("role", "muted")
        wm_row.addWidget(wm_note)
        wm_row.addStretch()
        mus_l.addLayout(wm_row)

        root.addWidget(mus)

        # ── Buttons ──────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _load(self) -> None:
        self._out_edit.setText(self._s.get("output_dir", ""))
        self._conc_spin.setValue(self._s.get("max_concurrent", 2))

        idx = self._vid_fmt.findText(self._s.get("video_format", "mp4"))
        self._vid_fmt.setCurrentIndex(max(0, idx))

        idx = self._aud_fmt.findText(self._s.get("audio_format", "mp3"))
        self._aud_fmt.setCurrentIndex(max(0, idx))

        idx = self._aud_quality.findText(str(self._s.get("audio_quality", "320")))
        self._aud_quality.setCurrentIndex(max(0, idx))

        self._embed_thumb.setChecked(self._s.get("embed_thumbnail", True))
        self._embed_meta.setChecked(self._s.get("embed_metadata", True))
        self._fetch_lyrics.setChecked(self._s.get("fetch_lyrics", True))
        self._playlist_sub.setChecked(self._s.get("playlist_subfolder", True))
        idx = self._whisper_model.findText(self._s.get("whisper_model", "base"))
        self._whisper_model.setCurrentIndex(max(0, idx))

        _browser_map = {"": 0, "chrome": 1, "chromium": 2, "firefox": 3,
                        "edge": 4, "brave": 5, "opera": 6, "vivaldi": 7}
        self._cookies_browser.setCurrentIndex(
            _browser_map.get(self._s.get("cookies_from_browser", ""), 0)
        )
        self._cookies_file.setText(self._s.get("cookies_file", ""))

    def _save(self) -> None:
        self._s.update({
            "output_dir":        self._out_edit.text().strip(),
            "max_concurrent":    self._conc_spin.value(),
            "video_format":      self._vid_fmt.currentText(),
            "audio_format":      self._aud_fmt.currentText(),
            "audio_quality":     self._aud_quality.currentText(),
            "embed_thumbnail":   self._embed_thumb.isChecked(),
            "embed_metadata":    self._embed_meta.isChecked(),
            "fetch_lyrics":      self._fetch_lyrics.isChecked(),
            "playlist_subfolder": self._playlist_sub.isChecked(),
            "whisper_model":     self._whisper_model.currentText(),
            "cookies_from_browser": (
                "" if self._cookies_browser.currentIndex() == 0
                else self._cookies_browser.currentText().lower()
            ),
            "cookies_file": self._cookies_file.text().strip(),
        })
        self.accept()

    # ── private ──────────────────────────────────────────
    def _browse_cookies(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cookies file", str(Path.home()), "Text files (*.txt);;All files (*)"
        )
        if path:
            self._cookies_file.setText(path)

    def _browse_output(self) -> None:
        current = self._out_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "Select output directory", current
        )
        if path:
            self._out_edit.setText(path)
