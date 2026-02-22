from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..download_manager import DownloadManager
from .download_card import DownloadCard


class DownloadQueueWidget(QFrame):
    """Scrollable list of download cards wired to a DownloadManager."""

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._cards: dict[str, DownloadCard] = {}
        self.setProperty("role", "panel")
        self._build_ui()
        self._wire_signals()

    # ── setup ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(42)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Download Queue")
        title.setStyleSheet("font-weight: 700; font-size: 13px;")
        h_lay.addWidget(title)
        h_lay.addStretch()

        self._count_lbl = QLabel("0 items")
        self._count_lbl.setProperty("role", "muted")
        h_lay.addWidget(self._count_lbl)

        clear_btn = QPushButton("Clear completed")
        clear_btn.setProperty("role", "secondary")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_completed)
        h_lay.addWidget(clear_btn)

        root.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        # Empty state
        self._empty_lbl = QLabel("No downloads yet – paste a URL above and click Download")
        self._empty_lbl.setProperty("role", "muted")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.insertWidget(0, self._empty_lbl)

        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll)

    def _wire_signals(self) -> None:
        m = self._manager
        m.download_added.connect(self._on_added)
        m.download_progress.connect(self._on_progress)
        m.download_status_changed.connect(self._on_status)
        m.download_finished.connect(self._on_finished)
        m.download_error.connect(self._on_error)

    # ── slots ─────────────────────────────────────────────
    def _on_added(self, download_id: str, job: dict) -> None:
        self._empty_lbl.hide()
        meta = job.get("metadata", {})
        card = DownloadCard(download_id, meta)
        card.cancel_requested.connect(self._on_card_cancel)
        # Insert before the trailing stretch (last item)
        pos = self._list_layout.count() - 1
        self._list_layout.insertWidget(pos, card)
        self._cards[download_id] = card
        self._update_count()

    def _on_progress(
        self,
        download_id: str,
        percent: float,
        speed: str,
        eta: str,
        title: str,
        size: str,
    ) -> None:
        card = self._cards.get(download_id)
        if card:
            card.update_progress(percent, speed, eta, title, size)

    def _on_status(self, download_id: str, status: str) -> None:
        card = self._cards.get(download_id)
        if card:
            card.set_status(status)

    def _on_finished(self, download_id: str) -> None:
        pass  # "done" badge is set via status_changed("done") from the worker

    def _on_error(self, download_id: str, message: str) -> None:
        card = self._cards.get(download_id)
        if card:
            card.set_error(message)

    def _on_card_cancel(self, download_id: str) -> None:
        self._manager.cancel_download(download_id)
        self._cards.pop(download_id, None)
        self._update_count()
        if not self._cards:
            self._empty_lbl.show()

    # ── private ──────────────────────────────────────────
    def _clear_completed(self) -> None:
        done_statuses = {"done", "error", "cancelled"}
        to_remove = []
        for dl_id, card in self._cards.items():
            badge_text = card._badge.text()
            if badge_text in {"Done", "Error", "Cancelled"}:
                to_remove.append(dl_id)
        for dl_id in to_remove:
            card = self._cards.pop(dl_id)
            card.deleteLater()
        self._update_count()
        if not self._cards:
            self._empty_lbl.show()

    def _update_count(self) -> None:
        n = len(self._cards)
        self._count_lbl.setText(f"{n} item{'s' if n != 1 else ''}")
