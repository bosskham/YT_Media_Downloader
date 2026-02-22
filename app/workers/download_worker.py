from __future__ import annotations

import os
import re
import threading

import yt_dlp
from PySide6.QtCore import QThread, Signal

from ..settings import resource_path


def _fmt_speed(bps: float | None) -> str:
    if not bps:
        return "–"
    if bps < 1_024:
        return f"{bps:.0f} B/s"
    if bps < 1_048_576:
        return f"{bps/1024:.1f} KB/s"
    return f"{bps/1_048_576:.1f} MB/s"


def _fmt_eta(secs: int | None) -> str:
    if secs is None:
        return "–"
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_size(b: int | None) -> str:
    if not b:
        return ""
    if b < 1_048_576:
        return f"{b/1024:.1f} KB"
    if b < 1_073_741_824:
        return f"{b/1_048_576:.1f} MB"
    return f"{b/1_073_741_824:.2f} GB"


class DownloadWorker(QThread):
    """
    QThread that runs a yt-dlp download session.

    Signals
    -------
    progress_updated(id, percent, speed, eta, current_title, size_str)
    status_changed(id, status)   – 'downloading' | 'processing' | 'cancelled'
    finished(id)
    error(id, message)
    """

    progress_updated = Signal(str, float, str, str, str, str)
    status_changed   = Signal(str, str)
    finished         = Signal(str)
    error            = Signal(str, str)

    def __init__(
        self,
        download_id: str,
        url: str,
        ydl_opts: dict,
    ) -> None:
        super().__init__()
        self.download_id = download_id
        self.url = url
        self.ydl_opts = ydl_opts
        self._cancel_event = threading.Event()

    # ── public ───────────────────────────────────────────
    def cancel(self) -> None:
        self._cancel_event.set()

    # ── QThread entry point ──────────────────────────────
    def run(self) -> None:
        # Tracks the last filepath seen after each postprocessor (= final audio file).
        final_filepath: list[str] = []
        # Fallback: raw downloaded file before postprocessing (from progress hook)
        pre_dl_path: list[str] = []

        def progress_hook(d: dict) -> None:
            if self._cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled()

            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                percent = (downloaded / total * 100) if total else 0
                speed   = _fmt_speed(d.get("speed"))
                eta     = _fmt_eta(d.get("eta"))
                title   = d.get("info_dict", {}).get("title", "")
                size    = _fmt_size(total)
                self.progress_updated.emit(
                    self.download_id, percent, speed, eta, title, size
                )
            elif status == "finished":
                self.status_changed.emit(self.download_id, "processing")
                # Capture the downloaded filename as a fallback for lyrics
                fn = d.get("filename", "")
                if fn:
                    if pre_dl_path:
                        pre_dl_path[0] = fn
                    else:
                        pre_dl_path.append(fn)

        def postprocessor_hook(d: dict) -> None:
            if self._cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            if d.get("status") == "finished":
                self.status_changed.emit(self.download_id, "downloading")
                # Capture the actual output filepath after each postprocessor
                import sys as _sys
                info = d.get("info_dict", {})
                fp = (info.get("filepath")
                      or info.get("__last_modified_file")
                      or "")
                print(f"[worker] postprocessor finished: pp={d.get('postprocessor')}  fp={fp!r}", file=_sys.stderr, flush=True)
                if fp:
                    if final_filepath:
                        final_filepath[0] = fp
                    else:
                        final_filepath.append(fp)

        opts = {
            **self.ydl_opts,
            "progress_hooks":      [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
        }
        # Pop private keys before passing to yt-dlp (not valid yt-dlp options)
        lyrics_callback = opts.pop("_lyrics_callback", None)
        target_codec    = opts.pop("_target_codec", None)

        # Force UTF-8 output from yt-dlp (Windows defaults to cp1252 in compiled exe)
        opts.setdefault("encoding", "utf-8")

        # Point yt-dlp at the bundled FFmpeg binaries when they exist.
        # resource_path("bin") works both in dev and in the PyInstaller bundle.
        ffmpeg_dir = resource_path("bin")
        if ffmpeg_dir.is_dir():
            opts.setdefault("ffmpeg_location", str(ffmpeg_dir))

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            if not self._cancel_event.is_set():
                if lyrics_callback:
                    import sys as _sys
                    fp = final_filepath[0] if final_filepath else ""
                    print(f"[worker] final_filepath={final_filepath}  pre_dl_path={pre_dl_path}", file=_sys.stderr, flush=True)
                    if not fp and pre_dl_path and target_codec:
                        from pathlib import Path as _Path
                        fp = str(_Path(pre_dl_path[0]).with_suffix(f".{target_codec}"))
                        print(f"[worker] fallback filepath={fp!r}", file=_sys.stderr, flush=True)
                    if fp:
                        print(f"[worker] launching lyrics thread for {fp!r}", file=_sys.stderr, flush=True)
                        # Show "Lyrics…" badge; daemon thread flips to "done" when finished.
                        # Capture `self` so the worker QObject stays alive until the thread exits.
                        self.status_changed.emit(self.download_id, "lyrics")
                        _id = self.download_id
                        def _do_lyrics(cb=lyrics_callback, path=fp, sid=_id, _w=self):
                            cb(path)
                            _w.status_changed.emit(sid, "done")
                        threading.Thread(target=_do_lyrics, daemon=True).start()
                    else:
                        print("[worker] ERROR: no filepath for lyrics callback", file=_sys.stderr, flush=True)
                        self.status_changed.emit(self.download_id, "done")
                else:
                    self.status_changed.emit(self.download_id, "done")
                # Always emit finished immediately so the next queued download can start
                self.finished.emit(self.download_id)
            else:
                self.status_changed.emit(self.download_id, "cancelled")
        except yt_dlp.utils.DownloadCancelled:
            self.status_changed.emit(self.download_id, "cancelled")
        except yt_dlp.utils.DownloadError as exc:
            # Strip ANSI codes that yt-dlp sometimes includes
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
            self.error.emit(self.download_id, msg)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(self.download_id, f"Unexpected error: {exc}")
