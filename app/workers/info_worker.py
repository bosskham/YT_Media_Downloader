from __future__ import annotations

import yt_dlp
from PySide6.QtCore import QThread, Signal


class InfoWorker(QThread):
    """Fetches video/playlist info without downloading."""

    info_ready = Signal(dict)   # info_dict from yt-dlp
    error = Signal(str)

    def __init__(self, url: str, flat: bool = True) -> None:
        super().__init__()
        self.url = url
        # flat playlist extraction is faster (no video page visits)
        self._flat = flat

    def run(self) -> None:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist" if self._flat else False,
            "skip_download": True,
            "encoding": "utf-8",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if info:
                self.info_ready.emit(info)
            else:
                self.error.emit("No information found for this URL.")
        except yt_dlp.utils.DownloadError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Unexpected error: {exc}")
