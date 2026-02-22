from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
    QSizePolicy,
)


class DownloadCard(QFrame):
    """A single card in the download queue."""

    cancel_requested = Signal(str)  # download_id

    _THUMB_W = 80
    _THUMB_H = 45

    def __init__(self, download_id: str, metadata: dict, parent=None) -> None:
        super().__init__(parent)
        self.download_id = download_id
        self._metadata = metadata
        self._nam: QNetworkAccessManager | None = None
        self.setProperty("role", "card")
        self._build_ui()
        self._apply_metadata()

    # ── setup ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.setFixedHeight(76)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedSize(self._THUMB_W, self._THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setProperty("role", "thumb-placeholder")
        self._thumb.setText("...")
        root.addWidget(self._thumb)

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.setContentsMargins(0, 0, 0, 0)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._title_lbl = QLabel("Loading…")
        self._title_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        self._title_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        title_row.addWidget(self._title_lbl)

        self._badge = QLabel("Queued")
        self._badge.setProperty("role", "badge-queued")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(self._badge)

        info_col.addLayout(title_row)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        info_col.addWidget(self._progress)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        self._speed_lbl = QLabel("")
        self._speed_lbl.setProperty("role", "muted")

        self._eta_lbl = QLabel("")
        self._eta_lbl.setProperty("role", "muted")

        self._size_lbl = QLabel("")
        self._size_lbl.setProperty("role", "muted")

        stats_row.addWidget(self._speed_lbl)
        stats_row.addWidget(self._eta_lbl)
        stats_row.addWidget(self._size_lbl)
        stats_row.addStretch()
        info_col.addLayout(stats_row)

        root.addLayout(info_col)

        # Cancel / remove button
        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setProperty("role", "icon")
        self._cancel_btn.setFixedSize(32, 32)
        self._cancel_btn.setToolTip("Cancel / Remove")
        self._cancel_btn.clicked.connect(self._on_cancel)
        root.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignTop)

    def _apply_metadata(self) -> None:
        title = self._metadata.get("title", self._metadata.get("url", "…"))
        self._title_lbl.setText(self._elide(title, 60))
        thumb_url = self._metadata.get("thumbnail", "")
        if thumb_url:
            self._load_thumbnail(thumb_url)

    # ── public slots ─────────────────────────────────────
    def update_progress(
        self,
        percent: float,
        speed: str,
        eta: str,
        current_title: str,
        size: str,
    ) -> None:
        if current_title:
            self._title_lbl.setText(self._elide(current_title, 60))
        self._progress.setValue(int(percent))
        self._speed_lbl.setText(speed)
        self._eta_lbl.setText(f"ETA {eta}" if eta != "–" else "")
        self._size_lbl.setText(size)

    def set_status(self, status: str) -> None:
        badge_map = {
            "queued":      ("Queued",      "badge-queued"),
            "downloading": ("Downloading", "badge-downloading"),
            "processing":  ("Processing",  "badge-processing"),
            "lyrics":      ("Lyrics…",     "badge-lyrics"),
            "done":        ("Done",        "badge-done"),
            "error":       ("Error",       "badge-error"),
            "cancelled":   ("Cancelled",   "badge-cancelled"),
        }
        text, role = badge_map.get(status, (status.title(), "badge-queued"))
        self._badge.setText(text)
        self._badge.setProperty("role", role)
        # Force style refresh
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

        if status == "done":
            self._progress.setValue(100)
            self._progress.setProperty("role", "success")
            self._progress.style().unpolish(self._progress)
            self._progress.style().polish(self._progress)
            self._speed_lbl.setText("")
            self._eta_lbl.setText("")
            self._cancel_btn.setToolTip("Remove")
        elif status == "error":
            self._progress.setProperty("role", "error")
            self._progress.style().unpolish(self._progress)
            self._progress.style().polish(self._progress)
        elif status == "cancelled":
            self._cancel_btn.setToolTip("Remove")

    def set_error(self, message: str) -> None:
        self.set_status("error")
        self._title_lbl.setText(f"Error: {self._elide(message, 55)}")
        self._title_lbl.setToolTip(message)
        self._speed_lbl.setText("")
        self._eta_lbl.setText("")

    # ── private ──────────────────────────────────────────
    def _on_cancel(self) -> None:
        self.cancel_requested.emit(self.download_id)
        self.deleteLater()

    def _load_thumbnail(self, url: str) -> None:
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_thumb_reply)
        self._nam.get(QNetworkRequest(QUrl(url)))

    def _on_thumb_reply(self, reply) -> None:
        data = reply.readAll()
        if data:
            px = QPixmap()
            if px.loadFromData(data):
                px = px.scaled(
                    self._THUMB_W,
                    self._THUMB_H,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Centre-crop
                x = (px.width()  - self._THUMB_W) // 2
                y = (px.height() - self._THUMB_H) // 2
                px = px.copy(x, y, self._THUMB_W, self._THUMB_H)
                self._thumb.setPixmap(px)
                self._thumb.setText("")
        reply.deleteLater()

    @staticmethod
    def _elide(text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else text[:max_chars - 1] + "…"
