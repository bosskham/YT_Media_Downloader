from __future__ import annotations

import os
import re
import threading

import yt_dlp
from PySide6.QtCore import QThread, Signal

from ..settings import resource_path


def _crop_thumbnail_square(thumb_path: str) -> None:
    """Center-crop a thumbnail to square in-place using Pillow.
    Called before EmbedThumbnail runs so yt-dlp embeds the cropped version.
    """
    import sys
    try:
        from PIL import Image
        img = Image.open(thumb_path)
        w, h = img.size
        if w == h:
            return   # Already square — nothing to do
        size = min(w, h)
        left = (w - size) // 2
        top  = (h - size) // 2
        img  = img.crop((left, top, left + size, top + size))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        ext = os.path.splitext(thumb_path)[1].lower()
        fmt = "WEBP" if ext == ".webp" else "JPEG"
        img.save(thumb_path, format=fmt, quality=95)
        print(f"[thumbnail] cropped {w}x{h} → {size}x{size}  ({thumb_path!r})",
              file=sys.stderr, flush=True)
    except ImportError:
        pass  # Pillow not installed — skip crop
    except Exception as exc:
        print(f"[thumbnail] crop error: {exc!r}", file=sys.stderr, flush=True)


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
        # Collects the final audio filepath for every track after all postprocessors
        # finish (detected by FFmpegMetadata "finished" event, which is always last).
        # Single-track downloads produce 1 entry; playlist downloads produce N entries.
        final_filepaths: list[str] = []
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

            # Crop thumbnail BEFORE EmbedThumbnail reads it from disk.
            # "started" fires synchronously just before pp.run() — so we modify
            # the file on disk and EmbedThumbnail picks up our cropped version.
            if d.get("status") == "started" and d.get("postprocessor") == "EmbedThumbnail":
                import sys as _sys
                info = d.get("info_dict", {})
                thumb = (info.get("__thumbnail_filename")
                         or next((t.get("filepath", "") for t in
                                  reversed(info.get("thumbnails", []))
                                  if t.get("filepath")), ""))
                if thumb and os.path.isfile(thumb):
                    _crop_thumbnail_square(thumb)
                    # Copy cropped thumbnail to sidecar before EmbedThumbnail deletes it
                    if sidecar_dest:
                        import shutil as _sh
                        ext  = os.path.splitext(thumb)[1]
                        dest = sidecar_dest + ext
                        try:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            _sh.copy2(thumb, dest)
                            print(f"[sidecar] wrote {dest!r}", file=sys.stderr, flush=True)
                        except Exception as exc:
                            print(f"[sidecar] copy failed: {exc!r}", file=sys.stderr, flush=True)
                return

            if d.get("status") == "finished":
                self.status_changed.emit(self.download_id, "downloading")
                import sys as _sys
                pp   = d.get("postprocessor", "")
                info = d.get("info_dict", {})
                fp   = (info.get("filepath")
                        or info.get("__last_modified_file")
                        or "")
                print(f"[worker] postprocessor finished: pp={pp}  fp={fp!r}", file=_sys.stderr, flush=True)
                # FFmpegMetadata is always the last postprocessor in our chain.
                # Collect one entry per track here so playlist downloads get all tracks.
                if fp and pp == "FFmpegMetadata":
                    final_filepaths.append(fp)

        opts = {
            **self.ydl_opts,
            "progress_hooks":      [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
        }
        # Pop private keys before passing to yt-dlp (not valid yt-dlp options)
        lyrics_callback = opts.pop("_lyrics_callback", None)
        target_codec    = opts.pop("_target_codec", None)
        sidecar_dest    = opts.pop("_sidecar_dest", "")

        # Force UTF-8 output from yt-dlp (Windows defaults to cp1252 in compiled exe)
        opts.setdefault("encoding", "utf-8")

        # Use Node.js for YouTube JS challenge solving (signature + n-challenge).
        opts.setdefault("js_runtimes", {"node": {}})

        # Cookies — needed for age-restricted / sign-in required videos.
        # cookies_file (Netscape format) takes priority over browser extraction.
        from ..settings import get_settings as _gs
        _cfg = _gs()
        _ck_file = _cfg.get("cookies_file", "")
        _browser  = _cfg.get("cookies_from_browser", "")
        if _ck_file:
            opts.setdefault("cookiefile", _ck_file)
        elif _browser:
            opts.setdefault("cookiesfrombrowser", (_browser,))

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
                    fps = list(final_filepaths)
                    print(f"[worker] final_filepaths={fps}  pre_dl_path={pre_dl_path}", file=_sys.stderr, flush=True)
                    # Fallback for builds where FFmpegMetadata hook doesn't fire
                    if not fps and pre_dl_path and target_codec:
                        from pathlib import Path as _Path
                        fb = str(_Path(pre_dl_path[0]).with_suffix(f".{target_codec}"))
                        print(f"[worker] fallback filepath={fb!r}", file=_sys.stderr, flush=True)
                        fps = [fb]
                    if fps:
                        print(f"[worker] launching lyrics threads for {len(fps)} file(s)", file=_sys.stderr, flush=True)
                        # Show "Lyrics…" badge; last thread to finish flips to "done".
                        # Capture `self` so the worker QObject stays alive until all threads exit.
                        self.status_changed.emit(self.download_id, "lyrics")
                        _id     = self.download_id
                        _remain = [len(fps)]
                        _lock   = threading.Lock()
                        _w      = self

                        def _do_lyrics(cb, path, sid, w, remain, lock):
                            try:
                                cb(path)
                            except Exception as exc:
                                import sys as _sys
                                print(f"[worker] lyrics thread error: {exc!r}", file=_sys.stderr, flush=True)
                            finally:
                                with lock:
                                    remain[0] -= 1
                                    if remain[0] == 0:
                                        w.status_changed.emit(sid, "done")

                        for _fp in fps:
                            threading.Thread(
                                target=_do_lyrics,
                                args=(lyrics_callback, _fp, _id, _w, _remain, _lock),
                                daemon=True,
                            ).start()
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
