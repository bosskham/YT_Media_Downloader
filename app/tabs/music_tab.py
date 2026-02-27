from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Optional

# Serializes ALL faster-whisper operations (construction + transcribe).
# ctranslate2 / CUDA is not safe to run on multiple threads simultaneously:
# two concurrent .transcribe() calls on the same GPU will crash the process.
# The lock also prevents the tqdm partial-init race on PyInstaller builds.
_whisper_model_lock: threading.Lock = threading.Lock()

# Cached WhisperModel instances keyed by (model_size, device, compute_type).
# Avoids reloading model weights (~seconds) on every song.
_whisper_model_cache: dict = {}

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..download_manager import DownloadManager
from ..settings import Settings
from ..workers.info_worker import InfoWorker

# ── constants ─────────────────────────────────────────────────────────────────

AUDIO_FORMATS  = ["mp3", "flac", "aac", "opus", "m4a"]
AUDIO_QUALITIES = ["320", "256", "192", "128", "96"]

MUSIC_URL_PLACEHOLDERS = {
    "single":   "https://music.youtube.com/watch?v=… or YouTube URL",
    "artist":   "https://music.youtube.com/channel/… or YouTube channel URL",
    "album":    "https://music.youtube.com/playlist?list=… (album playlist)",
    "playlist": "https://music.youtube.com/playlist?list=… or YouTube playlist",
}

# ── helpers ───────────────────────────────────────────────────────────────────

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


def _fmt_dur(secs: int | None) -> str:
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _build_audio_postprocessors(codec: str, quality: str, embed_thumb: bool) -> list[dict]:
    pp = [{"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": quality}]
    if embed_thumb:
        pp.append({"key": "EmbedThumbnail"})
    pp.append({"key": "FFmpegMetadata", "add_metadata": True})
    return pp


def _vtt_to_lrc(vtt_text: str, lang: str) -> str:
    """Convert WebVTT subtitle text to LRC format with optional romanization."""
    lrc_lines: list[str] = []
    seen: set[str] = set()
    for block in re.split(r'\n\n+', vtt_text.strip()):
        block_lines = block.strip().splitlines()
        ts_idx = next((i for i, l in enumerate(block_lines) if '-->' in l), None)
        if ts_idx is None:
            continue
        m = re.match(r'(?:(\d+):)?(\d+):(\d{2})\.(\d{3})', block_lines[ts_idx])
        if not m:
            continue
        h       = int(m.group(1) or 0)
        mi      = int(m.group(2))
        s       = int(m.group(3))
        ms      = int(m.group(4))
        total_s = h * 3600 + mi * 60 + s + ms / 1000
        raw = " ".join(block_lines[ts_idx + 1:])
        # Strip YouTube karaoke inline timestamps (<00:00:01.234>) and HTML tags
        raw = re.sub(r'<\d+:\d+:\d+\.\d+>', '', raw)
        raw = re.sub(r'<[^>]+>', '', raw).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        lrc_m  = int(total_s) // 60
        lrc_s  = total_s % 60
        ts     = f"[{lrc_m:02d}:{lrc_s:05.2f}]"
        romaji = _romanize_text(raw, lang)
        if romaji and romaji != raw:
            lrc_lines.append(f"{ts}{raw} ♪ {romaji}")
        else:
            lrc_lines.append(f"{ts}{raw}")
    return "\n".join(lrc_lines)


def _youtube_lyrics(url: str) -> str | None:
    """
    Fetch synced lyrics from the YouTube/YouTube Music video's subtitle tracks.
    Prefers manually-uploaded tracks (official lyrics); falls back to auto-generated
    captions (Google ASR). Returns LRC-formatted text or None.
    """
    import sys
    try:
        import yt_dlp
    except ImportError:
        return None

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "js_runtimes": {"node": {}},
    }
    from ..settings import get_settings as _gs
    _cfg = _gs()
    _ck_file = _cfg.get("cookies_file", "")
    _browser  = _cfg.get("cookies_from_browser", "")
    if _ck_file:
        opts["cookiefile"] = _ck_file
    elif _browser:
        opts["cookiesfrombrowser"] = (_browser,)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        print(f"[yt-lyrics] extract error: {exc!r}", file=sys.stderr, flush=True)
        return None

    manual = info.get("subtitles", {})
    auto   = info.get("automatic_captions", {})
    print(f"[yt-lyrics] manual={list(manual.keys())}  auto={list(auto.keys())[:8]}",
          file=sys.stderr, flush=True)

    # Manual tracks first (official/licensed lyrics), then auto-captions
    candidates: list[tuple[str, list[dict], bool]] = [
        (lang, tracks, True)  for lang, tracks in manual.items()
    ] + [
        (lang, tracks, False) for lang, tracks in auto.items() if lang not in manual
    ]

    if not candidates:
        print("[yt-lyrics] no subtitle tracks available", file=sys.stderr, flush=True)
        return None

    for lang, tracks, is_manual in candidates:
        track = next((t for t in tracks if t.get("ext") == "vtt"), tracks[0] if tracks else None)
        if not track:
            continue
        sub_url = track.get("url", "")
        if not sub_url:
            continue
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                content = ydl.urlopen(sub_url).read().decode("utf-8", errors="replace")
            lrc = _vtt_to_lrc(content, lang)
            if lrc:
                src = "manual" if is_manual else "auto-caption"
                print(f"[yt-lyrics] got lyrics via {src}  lang={lang!r}", file=sys.stderr, flush=True)
                return lrc
        except Exception as exc:
            print(f"[yt-lyrics] fetch error lang={lang!r}: {exc!r}", file=sys.stderr, flush=True)
            continue

    print("[yt-lyrics] no usable subtitle content found", file=sys.stderr, flush=True)
    return None


def _romanize_text(text: str, lang: str) -> str:
    """
    Convert text to a Latin/romanized form for the given ISO language code.
    Returns the original string unchanged for already-Latin scripts.
    """
    if not text or not lang:
        return text
    base_lang = lang.split("-")[0].lower()
    # Latin-script languages need no conversion
    _LATIN = {"en", "es", "fr", "de", "pt", "it", "nl", "pl", "sv", "ro",
              "ca", "la", "af", "cy", "id", "ms", "tr", "vi"}
    if base_lang in _LATIN:
        return text
    if base_lang == "ja":
        try:
            import pykakasi
            kks = pykakasi.kakasi()
            return " ".join(d["hepburn"] for d in kks.convert(text) if d["hepburn"]).strip() or text
        except Exception:
            pass
    if base_lang in ("zh", "zh-cn", "zh-tw", "yue"):
        try:
            from pypinyin import lazy_pinyin, Style
            return " ".join(lazy_pinyin(text, style=Style.TONE)).strip() or text
        except Exception:
            pass
    # Korean + Arabic + Thai + everything else → unidecode approximation
    try:
        from unidecode import unidecode
        return unidecode(text)
    except Exception:
        pass
    return text


def _transcribe_with_whisper(filepath: str, model_size: str = "base") -> str | None:
    """
    Transcribe an audio file and romanize each segment.
    Uses faster-whisper as primary engine (no HF token / pyannote required).
    Falls back to whisperX if faster-whisper is not importable.
    Returns LRC-formatted text or None on failure.
    """
    import sys, os as _os
    print(f"[whisper] transcribing {filepath!r}  model={model_size!r}", file=sys.stderr, flush=True)

    # Ensure bundled ffmpeg is on PATH (needed by both faster-whisper and whisperX)
    from ..settings import resource_path as _rp
    _ffmpeg_dir = _rp("bin")
    if _ffmpeg_dir.is_dir():
        _os.environ["PATH"] = str(_ffmpeg_dir) + _os.pathsep + _os.environ.get("PATH", "")

    # Detect device
    try:
        import torch
        device       = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
    except ImportError:
        device, compute_type = "cpu", "int8"
    print(f"[whisper] device={device}  compute_type={compute_type}", file=sys.stderr, flush=True)

    segments_raw: list[dict] = []
    lang = ""

    # ── Primary: faster-whisper (no pyannote / no HF token required) ──────────
    try:
        from faster_whisper import WhisperModel
        # Only use the model if it is already cached locally.
        # Loading an uncached model triggers a silent ~145 MB download that makes
        # the card appear stuck in "Lyrics…" for several minutes with no feedback.
        import os as _os2
        from pathlib import Path as _Path2
        _hf_home = _Path2(_os2.environ.get("HF_HOME",
                          _Path2.home() / ".cache" / "huggingface"))
        _model_cache = _hf_home / "hub" / f"models--Systran--faster-whisper-{model_size}"
        if not _model_cache.exists():
            print(f"[whisper] model '{model_size}' not cached at {_model_cache} — skipping", file=sys.stderr, flush=True)
            return None
        with _whisper_model_lock:
            # Load model once; reuse cached instance for subsequent songs.
            _key = (model_size, device, compute_type)
            if _key not in _whisper_model_cache:
                _whisper_model_cache[_key] = WhisperModel(
                    model_size, device=device, compute_type=compute_type
                )
            model = _whisper_model_cache[_key]
            # Hold the lock for the full transcription: ctranslate2/CUDA is not
            # thread-safe — two concurrent .transcribe() calls crash the process.
            segs, info = model.transcribe(filepath, beam_size=5)
            lang = info.language or ""
            # Consume the lazy generator inside the lock.
            segments_raw = [{"start": s.start, "text": s.text} for s in segs]
        print(f"[whisper] faster-whisper  language={lang!r}  segments={len(segments_raw)}", file=sys.stderr, flush=True)
    except ImportError:
        # ── Fallback: whisperX (needs pyannote + HF token on first run) ───────
        try:
            import whisperx
            model  = whisperx.load_model(model_size, device=device, compute_type=compute_type)
            audio  = whisperx.load_audio(filepath)
            result = model.transcribe(audio, batch_size=16 if device == "cuda" else 4)
            lang   = result.get("language", "")
            segments_raw = [
                {"start": s.get("start", 0), "text": s.get("text", "")}
                for s in result.get("segments", [])
            ]
            print(f"[whisper] whisperX  language={lang!r}  segments={len(segments_raw)}", file=sys.stderr, flush=True)
        except ImportError:
            print("[whisper] neither faster-whisper nor whisperX installed — skipping", file=sys.stderr, flush=True)
            return None
        except Exception as exc:
            print(f"[whisper] whisperX error: {exc!r}", file=sys.stderr, flush=True)
            return None
    except Exception as exc:
        print(f"[whisper] faster-whisper error: {exc!r}", file=sys.stderr, flush=True)
        return None

    if not segments_raw:
        return None

    lrc_lines: list[str] = []
    for seg in segments_raw:
        start = float(seg.get("start", 0))
        text  = seg.get("text", "").strip()
        if not text:
            continue
        m  = int(start // 60)
        s  = start % 60
        ts = f"[{m:02d}:{s:05.2f}]"
        romaji = _romanize_text(text, lang)
        if romaji and romaji != text:
            lrc_lines.append(f"{ts}{text} ♪ {romaji}")
        else:
            lrc_lines.append(f"{ts}{text}")

    lrc = "\n".join(lrc_lines)
    print(f"[whisper] built {len(lrc_lines)} LRC lines", file=sys.stderr, flush=True)
    return lrc or None


def _fetch_and_embed_lyrics(filepath: str, url: str, title: str, artist: str, whisper_model: str = "base") -> None:
    """Fetches lyrics (YouTube subtitles → local transcription) and embeds via mutagen."""
    import sys
    print(f"[lyrics] filepath={filepath!r}", file=sys.stderr, flush=True)
    print(f"[lyrics] title={title!r}  artist={artist!r}", file=sys.stderr, flush=True)

    # Tier 0: YouTube subtitle / caption tracks (official lyrics or Google ASR)
    lrc: str | None = _youtube_lyrics(url) if url else None

    # Tier 1: faster-whisper / whisperX local transcription
    if not lrc and whisper_model:
        lrc = _transcribe_with_whisper(filepath, whisper_model)

    if lrc:
        print(f"[lyrics] found {len(lrc)} chars — embedding…", file=sys.stderr, flush=True)
        _embed_lyrics(filepath, lrc, title, artist)
    else:
        print("[lyrics] no lyrics found anywhere", file=sys.stderr, flush=True)


def _embed_lyrics(filepath: str, lyrics: str, title: str, artist: str) -> None:
    import sys
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, USLT, Encoding, ID3NoHeaderError
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()
            audio.delall("USLT")
            audio.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text=lyrics))
            audio.save(filepath)
            print(f"[lyrics] saved USLT to {filepath!r}", file=sys.stderr, flush=True)
        elif ext == ".flac":
            from mutagen.flac import FLAC
            audio = FLAC(filepath)
            audio["LYRICS"] = lyrics
            audio.save()
            print(f"[lyrics] saved FLAC lyrics to {filepath!r}", file=sys.stderr, flush=True)
        elif ext in (".m4a", ".aac", ".mp4"):
            from mutagen.mp4 import MP4
            audio = MP4(filepath)
            audio["\xa9lyr"] = lyrics
            audio.save()
            print(f"[lyrics] saved M4A lyrics to {filepath!r}", file=sys.stderr, flush=True)
        else:
            print(f"[lyrics] unsupported ext {ext!r} — skipping embed", file=sys.stderr, flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[lyrics] embed error: {exc!r}", file=sys.stderr, flush=True)


# ── Whisper model check / download dialog ────────────────────────────────────

_NO_LYRICS = object()   # sentinel: user chose Ignore — proceed with download but no lyrics


def _is_whisper_model_cached(model_size: str) -> bool:
    """Returns True if the faster-whisper model files are already cached locally."""
    import os as _os
    from pathlib import Path as _Path
    _hf = _Path(_os.environ.get("HF_HOME", _Path.home() / ".cache" / "huggingface"))
    return (_hf / "hub" / f"models--Systran--faster-whisper-{model_size}").exists()


class _WhisperDownloadThread(QThread):
    """Downloads a faster-whisper model with byte-level progress reporting."""
    progress = Signal(int, str)   # (percent 0-100, status_text)
    done     = Signal(bool, str)  # (success, error_message)

    def __init__(self, model_size: str, parent=None) -> None:
        super().__init__(parent)
        self._model_size = model_size

    def run(self) -> None:
        try:
            _sig  = self.progress
            _size = self._model_size

            # Try progress-tracked download via huggingface_hub + tqdm.
            # Both are guaranteed to be present when faster-whisper is installed.
            try:
                from tqdm import tqdm as _BaseTqdm
                from huggingface_hub import snapshot_download

                class _ProgressTqdm(_BaseTqdm):
                    def update(self, n=1):
                        super().update(n)
                        if self.total and self.total > 0:
                            pct  = min(98, int(100 * self.n / self.total))
                            mb_n = self.n       / 1_048_576
                            mb_t = self.total   / 1_048_576
                            _sig.emit(pct, f"Downloading… {mb_n:.1f} / {mb_t:.1f} MB")

                _sig.emit(0, "Connecting…")
                snapshot_download(
                    f"Systran/faster-whisper-{_size}",
                    max_workers=1,          # sequential → clean per-file progress
                    tqdm_class=_ProgressTqdm,
                )
            except ImportError:
                # huggingface_hub / tqdm missing — fall back, no progress
                _sig.emit(0, "Downloading model…")
                from faster_whisper import WhisperModel
                WhisperModel(_size, device="cpu", compute_type="int8")
                self.done.emit(True, "")
                return

            _sig.emit(99, "Initializing model…")
            from faster_whisper import WhisperModel
            WhisperModel(_size, device="cpu", compute_type="int8")
            self.done.emit(True, "")
        except Exception as exc:
            self.done.emit(False, str(exc))


class _WhisperModelDialog(QDialog):
    """
    Shown when the faster-whisper model is not cached locally.
    Buttons: Download / Ignore / Cancel
    Call result_choice() after exec() → "download" | "ignore" | "cancel"
    """

    def __init__(self, model_size: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Whisper Model Not Found")
        self.setMinimumWidth(440)
        self._model_size = model_size
        self._choice = "cancel"
        self._thread: _WhisperDownloadThread | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        self._label = QLabel(
            f"The <b>faster-whisper '{model_size}'</b> model is not downloaded.\n\n"
            "It is used to transcribe lyrics when YouTube subtitles are unavailable.\n\n"
            "<b>Download</b> — download the model now, then fetch lyrics as usual.\n"
            "<b>Ignore</b> — proceed with the download but skip lyrics entirely.\n"
            "<b>Cancel</b> — do not start the download."
        )
        self._label.setWordWrap(True)
        lay.addWidget(self._label)

        self._prog = QProgressBar()
        self._prog.setRange(0, 100)
        self._prog.setValue(0)
        self._prog.hide()
        lay.addWidget(self._prog)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._btn_dl     = QPushButton("Download model")
        self._btn_ignore = QPushButton("Ignore")
        self._btn_cancel = QPushButton("Cancel")
        btn_row.addWidget(self._btn_dl)
        btn_row.addWidget(self._btn_ignore)
        btn_row.addWidget(self._btn_cancel)
        lay.addLayout(btn_row)

        self._btn_dl.clicked.connect(self._start_download)
        self._btn_ignore.clicked.connect(self._ignore)
        self._btn_cancel.clicked.connect(self._cancel)

    # ── slots ──────────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        self._btn_dl.setEnabled(False)
        self._btn_ignore.setEnabled(False)
        self._prog.show()
        self._prog.setValue(0)
        self._status.setText("Connecting…")
        self._thread = _WhisperDownloadThread(self._model_size, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_progress(self, pct: int, text: str) -> None:
        self._prog.setValue(pct)
        self._status.setText(text)

    def _on_done(self, success: bool, error: str) -> None:
        if success:
            self._prog.setValue(100)
            self._choice = "download"
            self.accept()
        else:
            self._prog.hide()
            self._status.setText(f"Download failed: {error}")
            self._btn_dl.setEnabled(True)
            self._btn_ignore.setEnabled(True)
            self._btn_cancel.setEnabled(True)

    def _ignore(self) -> None:
        self._choice = "ignore"
        self.accept()

    def _cancel(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
        self._choice = "cancel"
        self.reject()

    def closeEvent(self, event) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
        self._choice = "cancel"
        super().closeEvent(event)

    def result_choice(self) -> str:
        return self._choice


def _check_whisper_model(parent: QWidget, model_size: str):
    """
    Ensure the whisper model is ready.  Must be called from the main thread.

    Returns:
        model_size (str) — model cached or just downloaded; use full lyrics pipeline
        _NO_LYRICS       — user chose Ignore; proceed with download, no lyrics at all
        None             — user cancelled; abort the download entirely
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return model_size   # faster-whisper not installed; skip dialog, pipeline handles it

    if not model_size or _is_whisper_model_cached(model_size):
        return model_size   # already ready; no dialog needed

    dlg = _WhisperModelDialog(model_size, parent)
    dlg.exec()
    choice = dlg.result_choice()
    if choice == "cancel":
        return None
    if choice == "ignore":
        return _NO_LYRICS
    return model_size   # "download" — model now cached


# ── options row shared widget ─────────────────────────────────────────────────

class MusicOptionsRow(QWidget):
    """Reusable audio format / quality / extras row."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(AUDIO_FORMATS)
        lay.addWidget(self._fmt_combo)

        lay.addWidget(QLabel("Quality:"))
        self._q_combo = QComboBox()
        self._q_combo.addItems([f"{q} kbps" for q in AUDIO_QUALITIES])
        lay.addWidget(self._q_combo)

        self._thumb_chk   = QCheckBox("Embed thumbnail")
        self._meta_chk    = QCheckBox("Embed metadata")
        self._lyrics_chk  = QCheckBox("Fetch lyrics")

        self._thumb_chk.setChecked(settings.get("embed_thumbnail", True))
        self._meta_chk.setChecked(settings.get("embed_metadata", True))
        self._lyrics_chk.setChecked(settings.get("fetch_lyrics", True))

        lay.addWidget(self._thumb_chk)
        lay.addWidget(self._meta_chk)
        lay.addWidget(self._lyrics_chk)
        lay.addStretch()

        # Seed from settings
        idx = self._fmt_combo.findText(settings.get("audio_format", "mp3"))
        self._fmt_combo.setCurrentIndex(max(0, idx))
        idx = self._q_combo.findText(f"{settings.get('audio_quality', '320')} kbps")
        self._q_combo.setCurrentIndex(max(0, idx))

    @property
    def codec(self) -> str:
        return self._fmt_combo.currentText()

    @property
    def quality(self) -> str:
        return self._q_combo.currentText().split()[0]

    @property
    def embed_thumbnail(self) -> bool:
        return self._thumb_chk.isChecked()

    @property
    def embed_metadata(self) -> bool:
        return self._meta_chk.isChecked()

    @property
    def fetch_lyrics(self) -> bool:
        return self._lyrics_chk.isChecked()


# ── sub-tab: Single track ────────────────────────────────────────────────────

class SingleTrackWidget(QWidget):
    def __init__(self, manager: DownloadManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._manager  = manager
        self._settings = settings
        self._current_info: dict = {}
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
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(MUSIC_URL_PLACEHOLDERS["single"])
        self._url_edit.textChanged.connect(self._on_url_changed)
        self._fetch_btn = QPushButton("Fetch info")
        self._fetch_btn.setProperty("role", "secondary")
        self._fetch_btn.clicked.connect(self._do_fetch)
        url_row.addWidget(self._url_edit)
        url_row.addWidget(self._fetch_btn)
        root.addLayout(url_row)

        # Info preview card
        self._info_card = QFrame()
        self._info_card.setProperty("role", "card")
        self._info_card.hide()
        ic_lay = QVBoxLayout(self._info_card)
        ic_lay.setContentsMargins(12, 10, 12, 10)
        ic_lay.setSpacing(4)
        self._info_title  = QLabel("")
        self._info_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        self._info_artist = QLabel("")
        self._info_artist.setProperty("role", "muted")
        ic_lay.addWidget(self._info_title)
        ic_lay.addWidget(self._info_artist)
        root.addWidget(self._info_card)

        # Options
        self._opts = MusicOptionsRow(self._settings)
        root.addWidget(self._opts)

        # Output
        out_row = QHBoxLayout()
        self._out_edit = QLineEdit(self._settings.get("output_dir", ""))
        self._out_edit.setPlaceholderText("Output directory…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setProperty("role", "secondary")
        browse_btn.setMinimumWidth(90)
        browse_btn.clicked.connect(self._browse)
        out_row.addWidget(self._out_edit)
        out_row.addWidget(browse_btn)
        root.addLayout(out_row)

        root.addStretch()

        # Download
        self._dl_btn = QPushButton("⬇  Download")
        self._dl_btn.setFixedHeight(42)
        self._dl_btn.clicked.connect(self._download)
        root.addWidget(self._dl_btn)

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
        worker = InfoWorker(url, flat=False)
        worker.info_ready.connect(self._on_info)
        worker.error.connect(lambda _: None)
        worker.finished.connect(lambda: (
            self._fetch_btn.setEnabled(True),
            self._fetch_btn.setText("Fetch info"),
        ))
        self._info_worker = worker
        worker.start()

    def _on_info(self, info: dict) -> None:
        self._current_info = info
        title  = info.get("track") or info.get("title", "Unknown title")
        artist = info.get("artist") or info.get("uploader", "")
        album  = info.get("album", "")
        parts  = [artist, album]
        self._info_title.setText(title[:70])
        self._info_artist.setText("  ·  ".join(p for p in parts if p))
        self._info_card.show()

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

        codec       = self._opts.codec
        quality     = self._opts.quality
        embed_thumb = self._opts.embed_thumbnail
        fetch_lyr   = self._opts.fetch_lyrics
        out_dir     = self._out_edit.text().strip() or self._settings.get("output_dir")
        os.makedirs(out_dir, exist_ok=True)

        info     = self._current_info
        title    = info.get("track") or info.get("title", "")
        artist   = info.get("artist") or info.get("uploader", "")
        thumb    = info.get("thumbnail", "")

        ydl_opts = {
            "format":          "bestaudio/best",
            "postprocessors":  _build_audio_postprocessors(codec, quality, embed_thumb),
            "writethumbnail":  embed_thumb,
            "outtmpl":         os.path.join(out_dir, "%(title)s.%(ext)s"),
            "noplaylist":      True,
            "quiet":           True,
            "no_warnings":     True,
            # Use Node.js for YouTube JS challenge solving (signature + n-challenge).
            # Let yt-dlp use its default client list — restricting clients limits available formats.
            "js_runtimes":     {"node": {}},
        }

        if fetch_lyr and title:
            _t, _a, _u = title, artist, url
            _m = self._settings.get("whisper_model", "base")
            _m = _check_whisper_model(self, _m)
            if _m is None:          # user cancelled → abort
                return
            if _m is not _NO_LYRICS:  # user didn't ignore → set up lyrics
                ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u, m=_m: _fetch_and_embed_lyrics(fp, u, t, a, m)
                ydl_opts["_target_codec"]    = codec

        self._manager.add_download(
            url, ydl_opts, {"title": title or url, "thumbnail": thumb}
        )


# ── sub-tab: Collection (Playlist / Album / Artist) ──────────────────────────

class CollectionWidget(QWidget):
    """Used for Playlist, Album, and Artist sub-tabs."""

    def __init__(
        self,
        manager: DownloadManager,
        settings: Settings,
        mode: str,   # "playlist" | "album" | "artist"
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager  = manager
        self._settings = settings
        self._mode     = mode
        self._entries: list[dict] = []
        self._collection_title: str = ""
        self._info_worker: Optional[InfoWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(10)

        # URL row (full width)
        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(MUSIC_URL_PLACEHOLDERS.get(self._mode, "URL…"))
        self._fetch_btn = QPushButton("Fetch tracks")
        self._fetch_btn.setProperty("role", "secondary")
        self._fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(self._url_edit)
        url_row.addWidget(self._fetch_btn)
        root.addLayout(url_row)

        # Status (full width)
        self._status_lbl = QLabel("Enter a URL and click 'Fetch tracks'.")
        self._status_lbl.setProperty("role", "muted")
        root.addWidget(self._status_lbl)

        # ── Horizontal split: controls (left) | track list (right) ───────────
        body = QHBoxLayout()
        body.setSpacing(16)

        # Left: select bar + options + output + download
        left = QVBoxLayout()
        left.setSpacing(10)

        # Select bar
        sel_row = QHBoxLayout()
        sel_all  = QPushButton("Select all")
        sel_none = QPushButton("Select none")
        for btn in (sel_all, sel_none):
            btn.setProperty("role", "secondary")
            btn.setFixedHeight(28)
            sel_row.addWidget(btn)
        sel_all.clicked.connect(self._select_all)
        sel_none.clicked.connect(self._select_none)
        sel_row.addStretch()
        self._sel_lbl = QLabel("")
        self._sel_lbl.setProperty("role", "muted")
        sel_row.addWidget(self._sel_lbl)
        left.addLayout(sel_row)

        # Audio options — two compact rows to fit in the narrow left column
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(AUDIO_FORMATS)
        idx = self._fmt_combo.findText(self._settings.get("audio_format", "mp3"))
        self._fmt_combo.setCurrentIndex(max(0, idx))
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addWidget(QLabel("Quality:"))
        self._q_combo = QComboBox()
        self._q_combo.addItems([f"{q} kbps" for q in AUDIO_QUALITIES])
        idx = self._q_combo.findText(f"{self._settings.get('audio_quality', '320')} kbps")
        self._q_combo.setCurrentIndex(max(0, idx))
        fmt_row.addWidget(self._q_combo)
        fmt_row.addStretch()
        left.addLayout(fmt_row)

        chk_row = QHBoxLayout()
        self._thumb_chk  = QCheckBox("Embed thumbnail")
        self._meta_chk   = QCheckBox("Embed metadata")
        self._lyrics_chk = QCheckBox("Fetch lyrics")
        self._thumb_chk.setChecked(self._settings.get("embed_thumbnail", True))
        self._meta_chk.setChecked(self._settings.get("embed_metadata", True))
        self._lyrics_chk.setChecked(self._settings.get("fetch_lyrics", True))
        chk_row.addWidget(self._thumb_chk)
        chk_row.addWidget(self._meta_chk)
        chk_row.addWidget(self._lyrics_chk)
        chk_row.addStretch()
        left.addLayout(chk_row)

        # Sub-folder option
        self._subfolder_chk = QCheckBox("Save tracks in sub-folder")
        self._subfolder_chk.setChecked(self._settings.get("playlist_subfolder", True))
        left.addWidget(self._subfolder_chk)

        # Output dir
        out_row = QHBoxLayout()
        self._out_edit = QLineEdit(self._settings.get("output_dir", ""))
        self._out_edit.setPlaceholderText("Output directory…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setProperty("role", "secondary")
        browse_btn.setMinimumWidth(90)
        browse_btn.clicked.connect(self._browse)
        out_row.addWidget(self._out_edit)
        out_row.addWidget(browse_btn)
        left.addLayout(out_row)

        left.addStretch()

        # Download
        self._dl_btn = QPushButton("⬇  Download selected")
        self._dl_btn.setFixedHeight(42)
        self._dl_btn.clicked.connect(self._download_selected)
        left.addWidget(self._dl_btn)

        body.addLayout(left, 2)

        # Right: track list
        self._list = QListWidget()
        self._list.itemChanged.connect(self._update_count)
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
        self._status_lbl.setText("Fetching track list…")
        worker = InfoWorker(url, flat=True)
        worker.info_ready.connect(self._on_info)
        worker.error.connect(self._on_error)
        worker.finished.connect(lambda: (
            self._fetch_btn.setEnabled(True),
            self._fetch_btn.setText("Fetch tracks"),
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
        for i, entry in enumerate(self._entries, 1):
            title  = entry.get("title") or entry.get("id", "Unknown")
            artist = entry.get("artist") or entry.get("uploader", "")
            dur    = _fmt_dur(entry.get("duration", 0))
            text   = f"{i:02d}. {title}"
            if artist:
                text += f"  —  {artist}"
            if dur:
                text += f"  [{dur}]"
            item = QListWidgetItem(text)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        n = len(self._entries)
        label = {"playlist": "playlist", "album": "album", "artist": "channel"}.get(self._mode, "collection")
        self._status_lbl.setText(
            f"Found {n} track{'s' if n != 1 else ''} in {label}: {self._collection_title}"
        )
        self._update_count()

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")

    def _select_all(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _update_count(self) -> None:
        total   = self._list.count()
        checked = sum(
            1 for i in range(total)
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        )
        self._sel_lbl.setText(f"{checked} / {total} selected")

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Output directory", self._out_edit.text() or str(Path.home())
        )
        if path:
            self._out_edit.setText(path)

    def _download_selected(self) -> None:
        selected_idx = [
            i for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if not selected_idx:
            QMessageBox.warning(self, "Nothing selected", "Please select at least one track.")
            return

        codec       = self._fmt_combo.currentText()
        quality     = self._q_combo.currentText().split()[0]
        embed_thumb = self._thumb_chk.isChecked()
        fetch_lyr   = self._lyrics_chk.isChecked()
        out_dir     = self._out_edit.text().strip() or self._settings.get("output_dir")
        use_sub     = self._subfolder_chk.isChecked()
        os.makedirs(out_dir, exist_ok=True)

        # Check whisper model once before queuing any tracks.
        _whisper_m = self._settings.get("whisper_model", "base")
        if fetch_lyr:
            _whisper_m = _check_whisper_model(self, _whisper_m)
            if _whisper_m is None:   # user cancelled → abort
                return

        for idx in selected_idx:
            num   = idx + 1
            entry = self._entries[idx]
            video_url = entry.get("url") or entry.get("webpage_url") or entry.get("id", "")
            if not video_url.startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_url}"

            title  = entry.get("title", "Unknown")
            artist = entry.get("artist") or entry.get("uploader", "")
            thumb  = entry.get("thumbnail", "")

            if use_sub:
                sub = _safe_folder(self._collection_title) or "music"
                tpl = os.path.join(out_dir, sub, f"{num:02d}. %(title)s.%(ext)s")
            else:
                tpl = os.path.join(out_dir, f"{num:02d}. %(title)s.%(ext)s")

            ydl_opts = {
                "format":          "bestaudio/best",
                "postprocessors":  _build_audio_postprocessors(codec, quality, embed_thumb),
                "writethumbnail":  embed_thumb,
                "outtmpl":         tpl,
                "noplaylist":      True,
                "quiet":           True,
                "no_warnings":     True,
                # Use Node.js for YouTube JS challenge solving (signature + n-challenge).
                # Let yt-dlp use its default client list — restricting clients limits available formats.
                "js_runtimes":     {"node": {}},
            }

            if fetch_lyr and title and _whisper_m is not _NO_LYRICS:
                _t, _a, _u = title, artist, video_url
                _m = _whisper_m
                ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u, m=_m: _fetch_and_embed_lyrics(fp, u, t, a, m)
                ydl_opts["_target_codec"]    = codec

            self._manager.add_download(
                video_url, ydl_opts, {"title": title, "thumbnail": thumb}
            )


# ── NavBar ────────────────────────────────────────────────────────────────────

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


# ── MusicTab ──────────────────────────────────────────────────────────────────

class MusicTab(QWidget):
    def __init__(self, manager: DownloadManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._manager  = manager
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(12)

        desc = QLabel(
            "Download music with embedded metadata, album art, and synchronized lyrics."
        )
        desc.setProperty("role", "muted")
        root.addWidget(desc)

        root.addWidget(_make_sep())

        # Stacked sub-tabs
        self._stack = QStackedWidget()
        self._stack.addWidget(SingleTrackWidget(self._manager, self._settings))
        self._stack.addWidget(CollectionWidget(self._manager, self._settings, mode="artist"))
        self._stack.addWidget(CollectionWidget(self._manager, self._settings, mode="album"))
        self._stack.addWidget(CollectionWidget(self._manager, self._settings, mode="playlist"))

        nav = NavBar(["Single Track", "Artist", "Album", "Playlist"], self._stack)
        root.addWidget(nav)
        root.addWidget(self._stack)
