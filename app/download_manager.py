from __future__ import annotations

import uuid
from collections import deque
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .workers.download_worker import DownloadWorker


class DownloadManager(QObject):
    """
    Manages a queue of DownloadWorker threads.

    Signals
    -------
    download_added(id, metadata_dict)
    download_progress(id, percent, speed, eta, title, size)
    download_status_changed(id, status)
    download_finished(id)
    download_error(id, message)
    """

    download_added          = Signal(str, dict)
    download_progress       = Signal(str, float, str, str, str, str)
    download_status_changed = Signal(str, str)
    download_finished       = Signal(str)
    download_error          = Signal(str, str)

    def __init__(self, max_concurrent: int = 2) -> None:
        super().__init__()
        self.max_concurrent = max_concurrent
        self._queue: deque[str]               = deque()
        self._active: dict[str, DownloadWorker] = {}
        self._jobs: dict[str, dict]           = {}   # id → full job info

    # ── public ───────────────────────────────────────────
    def add_download(
        self,
        url: str,
        ydl_opts: dict,
        metadata: Optional[dict] = None,
    ) -> str:
        download_id = str(uuid.uuid4())[:8]
        job = {
            "id":       download_id,
            "url":      url,
            "ydl_opts": ydl_opts,
            "metadata": metadata or {},
            "status":   "queued",
        }
        self._jobs[download_id] = job
        self._queue.append(download_id)
        self.download_added.emit(download_id, {**job})
        self._process_queue()
        return download_id

    def cancel_download(self, download_id: str) -> None:
        if download_id in self._active:
            self._active[download_id].cancel()
        else:
            # Remove from pending queue
            self._queue = deque(i for i in self._queue if i != download_id)
            self.download_status_changed.emit(download_id, "cancelled")

    def set_max_concurrent(self, n: int) -> None:
        self.max_concurrent = max(1, n)
        self._process_queue()

    # ── private ──────────────────────────────────────────
    def _process_queue(self) -> None:
        while self._queue and len(self._active) < self.max_concurrent:
            download_id = self._queue.popleft()
            job = self._jobs[download_id]
            worker = DownloadWorker(download_id, job["url"], job["ydl_opts"])

            # Wire signals
            worker.progress_updated.connect(self.download_progress)
            worker.status_changed.connect(self.download_status_changed)
            worker.finished.connect(self._on_worker_finished)
            worker.error.connect(self._on_worker_error)

            self._active[download_id] = worker
            self.download_status_changed.emit(download_id, "downloading")
            worker.start()

    def _on_worker_finished(self, download_id: str) -> None:
        self._active.pop(download_id, None)
        self.download_finished.emit(download_id)
        self._process_queue()

    def _on_worker_error(self, download_id: str, message: str) -> None:
        self._active.pop(download_id, None)
        self.download_error.emit(download_id, message)
        self._process_queue()
