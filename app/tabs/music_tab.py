from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

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


def _build_output_template(
    out_dir: str,
    num: int,
    title: str,
    artist: str,
    collection_title: str,
    collection_type: str,
) -> str:
    """
    Build the yt-dlp outtmpl path based on collection type.

    Album / EP  →  out_dir / Artist / AlbumTitle / 01. %(title)s.%(ext)s
    Single      →  out_dir / Artist / Singles    / %(title)s.%(ext)s
    Artist      →  out_dir / Artist / %(album)s  / %(title)s.%(ext)s
    Playlist    →  out_dir / PlaylistName         / 01. %(title)s.%(ext)s
    """
    artist_f  = _safe_folder(artist)  or "Unknown Artist"
    album_f   = _safe_folder(collection_title) or "Unknown Album"
    ctype     = collection_type.lower()

    if ctype in ("album", "ep"):
        return os.path.join(out_dir, artist_f, album_f, f"{num:02d}. %(title)s.%(ext)s")

    if ctype == "single":
        return os.path.join(out_dir, artist_f, "Singles", "%(title)s.%(ext)s")

    if ctype == "artist":
        # Each track may belong to a different album — use yt-dlp's %(album)s field.
        # Fall back to 'Unknown Album' if the field is empty.
        return os.path.join(out_dir, artist_f, "%(album|Unknown Album)s", "%(title)s.%(ext)s")

    # playlist (or any other type) — flat under the playlist name
    return os.path.join(out_dir, album_f, f"{num:02d}. %(title)s.%(ext)s")


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


def _vtt_to_lrc(vtt_text: str, lang: str = "") -> str:
    """Convert WebVTT subtitle text to LRC format."""
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


def _fetch_album_art(url: str, title: str, artist: str) -> bytes | None:
    """
    Fetch the original square album art for a song.

    Sources tried in order:
      1. iTunes Search API  — free, no auth, always returns square art (1200×1200)
      2. ytmusicapi search  — YouTube Music catalog (unauthenticated; often works)
      3. ytmusicapi watch_playlist — exact video match (fails for some videos without auth)

    Returns raw JPEG bytes or None if all sources fail.
    """
    import sys, json, re as _re
    import urllib.request as _ur, urllib.parse as _up

    # ── 1. iTunes Search API (most reliable — free, no auth) ──────────────────
    if title:
        try:
            query     = _up.quote_plus(f"{title} {artist}".strip())
            itunes_url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=5"
            req = _ur.Request(itunes_url, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            results = data.get("results", [])
            if results:
                art_url = results[0].get("artworkUrl100", "")
                if art_url:
                    # Replace 100x100bb with 1200x1200bb for maximum resolution
                    art_url = art_url.replace("100x100bb", "1200x1200bb")
                    req2 = _ur.Request(art_url, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req2, timeout=15) as r2:
                        img = r2.read()
                    print(f"[cover-art] iTunes: {len(img):,} bytes", file=sys.stderr, flush=True)
                    return img
        except Exception as exc:
            print(f"[cover-art] iTunes failed: {exc!r}", file=sys.stderr, flush=True)

    # ── 2+3. ytmusicapi fallback ───────────────────────────────────────────────
    try:
        from ytmusicapi import YTMusic
    except ImportError:
        return None

    yt = YTMusic()
    thumb_url: str | None = None

    # 2. Search by title + artist
    if title:
        try:
            query   = f"{title} {artist}".strip()
            results = yt.search(query, filter="songs", limit=3)
            if results:
                thumbs = results[0].get("thumbnails", [])
                if thumbs:
                    thumb_url = thumbs[-1]["url"]
                    print(f"[cover-art] ytmusicapi search: query={query!r}", file=sys.stderr, flush=True)
        except Exception as exc:
            print(f"[cover-art] ytmusicapi search failed: {exc!r}", file=sys.stderr, flush=True)

    # 3. Exact video match via watch_playlist
    if not thumb_url:
        _m = _re.search(r'(?:v=|youtu\.be/|/v/|/embed/)([A-Za-z0-9_-]{11})', url)
        if _m:
            try:
                wp = yt.get_watch_playlist(videoId=_m.group(1))
                if wp and wp.get("tracks"):
                    thumbs = wp["tracks"][0].get("thumbnail", [])
                    if thumbs:
                        thumb_url = thumbs[-1]["url"]
                        print("[cover-art] ytmusicapi watch_playlist", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[cover-art] ytmusicapi watch_playlist failed: {exc!r}", file=sys.stderr, flush=True)

    if not thumb_url:
        print("[cover-art] all sources failed", file=sys.stderr, flush=True)
        return None

    # Upscale lh3.googleusercontent.com URLs to 1200×1200
    thumb_url = _re.sub(r'=w\d+-h\d+.*$', '=w1200-h1200-l90-rj', thumb_url)
    try:
        req = _ur.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=15) as r:
            img = r.read()
        print(f"[cover-art] ytmusicapi: {len(img):,} bytes", file=sys.stderr, flush=True)
        return img
    except Exception as exc:
        print(f"[cover-art] ytmusicapi download failed: {exc!r}", file=sys.stderr, flush=True)
        return None


def _embed_cover(filepath: str, img_bytes: bytes) -> None:
    """Embed album art bytes into an audio file, replacing any existing cover."""
    import sys
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, APIC, ID3NoHeaderError
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()
            audio.delall("APIC")
            audio.add(APIC(encoding=0, mime="image/jpeg", type=3, desc="Cover", data=img_bytes))
            audio.save(filepath)
            print(f"[ytmusic-art] saved APIC cover to {filepath!r}", file=sys.stderr, flush=True)
        elif ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(filepath)
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = img_bytes
            audio.add_picture(pic)
            audio.save()
            print(f"[ytmusic-art] saved FLAC cover to {filepath!r}", file=sys.stderr, flush=True)
        elif ext in (".m4a", ".aac", ".mp4"):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(filepath)
            audio["covr"] = [MP4Cover(img_bytes, MP4Cover.FORMAT_JPEG)]
            audio.save()
            print(f"[ytmusic-art] saved M4A cover to {filepath!r}", file=sys.stderr, flush=True)
        else:
            print(f"[ytmusic-art] unsupported ext {ext!r} — skipping", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"[ytmusic-art] embed error: {exc!r}", file=sys.stderr, flush=True)


# ── ytmusicapi lyrics — commented out (ytmusicapi still used for artist tab + cover art) ──────
# def _ytmusicapi_lyrics(url: str) -> str | None:
#     import sys, re as _re
#     try:
#         from ytmusicapi import YTMusic
#     except ImportError:
#         return None
#     _m = _re.search(r'(?:v=|youtu\.be/|/v/|/embed/)([A-Za-z0-9_-]{11})', url)
#     if not _m:
#         return None
#     video_id = _m.group(1)
#     try:
#         yt = YTMusic()
#         wp = yt.get_watch_playlist(videoId=video_id)
#         browse_id = wp.get("lyrics") if wp else None
#         if not browse_id:
#             return None
#         lyrics_data = yt.get_lyrics(browse_id, timestamps=True)
#         if not lyrics_data:
#             return None
#         source         = lyrics_data.get("source", "")
#         has_timestamps = lyrics_data.get("hasTimestamps", False)
#         lyrics_content = lyrics_data.get("lyrics")
#         if has_timestamps and isinstance(lyrics_content, list):
#             lrc_lines: list[str] = []
#             for line in lyrics_content:
#                 if isinstance(line, dict):
#                     start_ms = line.get("startMs", "0") or "0"
#                     text     = (line.get("lyric") or line.get("text") or "").strip()
#                 else:
#                     start_ms = str(getattr(line, "startMs", None) or "0")
#                     text     = (getattr(line, "text", None) or getattr(line, "lyric", None) or "").strip()
#                 if not text:
#                     continue
#                 start_s = int(start_ms) / 1000
#                 m_val, s_val = divmod(start_s, 60)
#                 lrc_lines.append(f"[{int(m_val):02d}:{s_val:05.2f}]{text}")
#             if lrc_lines:
#                 return "\n".join(lrc_lines)
#         if isinstance(lyrics_content, str) and lyrics_content.strip():
#             return lyrics_content.strip()
#         return None
#     except Exception as exc:
#         print(f"[ytmusic] error: {exc!r}", file=sys.stderr, flush=True)
#         return None


# ── syncedlyrics — commented out (not installed) ──────────────────────────────
# def _syncedlyrics_search(title: str, artist: str) -> str | None:
#     import sys
#     try:
#         import syncedlyrics
#     except ImportError:
#         return None
#     query = f"{title} {artist}".strip()
#     try:
#         lrc = syncedlyrics.search(query)
#         return lrc or None
#     except Exception as exc:
#         print(f"[lyrics] syncedlyrics error: {exc!r}", file=sys.stderr, flush=True)
#         return None


def _detect_script(text: str) -> str:
    """Return 'ja', 'zh', 'ko', 'other', or 'latin' from dominant Unicode block."""
    kana = cjk = hangul = other_nl = 0
    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x30FF:   kana    += 1   # Hiragana / Katakana
        elif 0x4E00 <= cp <= 0x9FFF: cjk     += 1   # CJK unified
        elif 0xAC00 <= cp <= 0xD7AF: hangul  += 1   # Hangul
        elif cp > 0x02FF and not ch.isspace(): other_nl += 1
    total_nl = kana + cjk + hangul + other_nl
    if total_nl == 0:
        return "latin"
    if kana or (kana + cjk > hangul + other_nl): return "ja"
    if cjk:    return "zh"
    if hangul: return "ko"
    return "other"


def _romanize_line(text: str, script: str) -> str | None:
    """Romanize one line; return None if unavailable or identical to input."""
    if script == "ja":
        try:
            import pykakasi
            kks = pykakasi.kakasi()
            r = " ".join(d["hepburn"] for d in kks.convert(text) if d["hepburn"]).strip()
            return r or None
        except Exception:
            pass
    if script == "zh":
        try:
            from pypinyin import lazy_pinyin, Style
            r = " ".join(lazy_pinyin(text, style=Style.TONE)).strip()
            return r or None
        except Exception:
            pass
    if script in ("ko", "other"):
        try:
            from unidecode import unidecode
            r = unidecode(text).strip()
            return r or None
        except Exception:
            pass
    return None


def _romanize_lyrics(lrc: str) -> str:
    """
    Walk each LRC / plain-text line. For non-Latin lines append ' ♪ <romanized>'.
    LRC timestamps are stripped for detection but preserved in output.
    """
    out: list[str] = []
    for line in lrc.splitlines():
        body = re.sub(r'^\[\d+:\d+\.\d+\]', '', line).strip()
        script = _detect_script(body)
        if script == "latin" or not body:
            out.append(line)
            continue
        romaji = _romanize_line(body, script)
        out.append(f"{line} ♪ {romaji}" if (romaji and romaji != body) else line)
    return "\n".join(out)


# ── faster-whisper transcription (Tier 1 fallback when YouTube has no subtitles) ─────────────

import threading as _threading

_whisper_model_lock  = _threading.Lock()
_whisper_model_cache: dict[str, object] = {}   # model_name → WhisperModel instance


def _is_whisper_model_cached(model_name: str) -> bool:
    """Return True if the model files are already on disk (no download needed)."""
    try:
        from faster_whisper.utils import get_assets_path
        import huggingface_hub
        cache = huggingface_hub.constants.HF_HUB_CACHE
        repo   = f"Systran/faster-whisper-{model_name}"
        model_dir = os.path.join(cache, "models--" + repo.replace("/", "--"))
        return os.path.isdir(model_dir)
    except Exception:
        return False


def _transcribe_with_whisper(filepath: str, model_name: str) -> str | None:
    """
    Transcribe audio with faster-whisper and return an LRC string, or None on failure.
    The model is cached in _whisper_model_cache after first load.
    """
    import sys
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[whisper] faster-whisper not installed — skipping", file=sys.stderr, flush=True)
        return None

    print(f"[whisper] transcribing {os.path.basename(filepath)!r} model={model_name!r}",
          file=sys.stderr, flush=True)
    try:
        with _whisper_model_lock:
            if model_name not in _whisper_model_cache:
                print(f"[whisper] loading model {model_name!r}…", file=sys.stderr, flush=True)
                _whisper_model_cache[model_name] = WhisperModel(
                    model_name, device="cpu", compute_type="int8"
                )
            model = _whisper_model_cache[model_name]

        segments, info = model.transcribe(filepath, beam_size=5, word_timestamps=False)
        lrc_lines: list[str] = []
        for seg in segments:
            m_val = int(seg.start // 60)
            s_val = seg.start % 60
            text  = seg.text.strip()
            if text:
                lrc_lines.append(f"[{m_val:02d}:{s_val:05.2f}]{text}")

        if not lrc_lines:
            print("[whisper] transcription produced no segments", file=sys.stderr, flush=True)
            return None

        print(f"[whisper] {len(lrc_lines)} segments  lang={info.language!r}",
              file=sys.stderr, flush=True)
        return "\n".join(lrc_lines)
    except Exception as exc:
        print(f"[whisper] transcription error: {exc!r}", file=sys.stderr, flush=True)
        return None


def _whisper_model_setting() -> str:
    """Read the whisper model name from Settings (defaults to 'base')."""
    try:
        from ..settings import get_settings
        return get_settings().get("whisper_model", "base")
    except Exception:
        return "base"


def _read_tags_from_file(filepath: str) -> tuple[str, str]:
    """Read (title, artist) from embedded audio metadata. Returns ('', '') on failure."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3
            tags   = ID3(filepath)
            return str(tags.get("TIT2") or ""), str(tags.get("TPE1") or "")
        if ext == ".flac":
            from mutagen.flac import FLAC
            tags   = FLAC(filepath)
            return (tags.get("title") or [""])[0], (tags.get("artist") or [""])[0]
        if ext in (".m4a", ".aac", ".mp4"):
            from mutagen.mp4 import MP4
            tags   = MP4(filepath)
            return (tags.get("\xa9nam") or [""])[0], (tags.get("\xa9ART") or [""])[0]
    except Exception:
        pass
    return "", ""


def _fetch_and_embed_lyrics(
    filepath: str,
    url: str,
    title: str,
    artist: str,
    embed_cover: bool = False,
    fetch_lyrics: bool = True,
) -> None:
    """
    Post-download callback: fetch & embed cover art + lyrics.
    Cover art : iTunes Search API (square 1200×1200) overwrites yt-dlp's 16:9 thumbnail.
    Lyrics    : Tier 0 — YouTube VTT subtitles
                Tier 1 — faster-whisper transcription (fallback)
    Romanize  : pykakasi (Japanese → hepburn romaji) appended per line.
    fetch_lyrics=False → cover-art-only mode.
    title/artist empty → read from embedded tags (playlist/album downloads).
    """
    import sys

    # For playlist/album downloads title & artist aren't known at queue time —
    # read them from the metadata that yt-dlp already embedded.
    if not title or not artist:
        _t, _a = _read_tags_from_file(filepath)
        title  = title  or _t
        artist = artist or _a

    print(f"[post-dl] filepath={filepath!r}", file=sys.stderr, flush=True)
    print(f"[post-dl] title={title!r}  artist={artist!r}  embed_cover={embed_cover}  fetch_lyrics={fetch_lyrics}",
          file=sys.stderr, flush=True)

    # Cover art: iTunes Search API → ytmusicapi search → ytmusicapi watch_playlist
    if embed_cover:
        cover = _fetch_album_art(url, title, artist)
        if cover:
            _embed_cover(filepath, cover)

    if not fetch_lyrics:
        return

    # Tier 0: YouTube VTT subtitles / caption tracks
    lrc: str | None = _youtube_lyrics(url) if url else None

    # Tier 1: faster-whisper transcription (when YouTube has no subtitles)
    if not lrc:
        whisper_model = _whisper_model_setting()
        lrc = _transcribe_with_whisper(filepath, whisper_model)

    # Romanize Japanese lyrics (original ♪ romaji per line)
    if lrc:
        lrc = _romanize_lyrics(lrc)
        print(f"[lyrics] {len(lrc)} chars — embedding…", file=sys.stderr, flush=True)
        _embed_lyrics(filepath, lrc, title, artist)
    else:
        print("[lyrics] no lyrics found", file=sys.stderr, flush=True)


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
            _t, _a, _u, _c = title, artist, url, embed_thumb
            ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u, c=_c: _fetch_and_embed_lyrics(fp, u, t, a, embed_cover=c)
            ydl_opts["_target_codec"]    = codec
        elif embed_thumb:
            # No lyrics, but still replace yt-dlp's 16:9 thumbnail with proper album art
            _t, _a, _u = title, artist, url
            ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u: _fetch_and_embed_lyrics(fp, u, t, a, embed_cover=True, fetch_lyrics=False)
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
        self._collection_type:  str = mode   # overwritten by _on_info
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
        # Strip YouTube Music playlist-type prefix: "Album - Title", "Playlist - Title", etc.
        # Capture the prefix so _download_selected can pick the right folder structure.
        raw_title = info.get("title", "")
        m = re.match(r'^(Album|Playlist|Artist|EP|Single|Mix)\s*[-–—]\s*', raw_title)
        self._collection_type  = m.group(1).lower() if m else self._mode   # "album","ep","single",…
        self._collection_title = raw_title[m.end():].strip() if m else raw_title
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
                tpl = _build_output_template(
                    out_dir, num, title, artist,
                    self._collection_title, self._collection_type,
                )
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

            if fetch_lyr and title:
                _t, _a, _u, _c = title, artist, video_url, embed_thumb
                ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u, c=_c: _fetch_and_embed_lyrics(fp, u, t, a, embed_cover=c)
                ydl_opts["_target_codec"]    = codec
            elif embed_thumb:
                # No lyrics, but still replace yt-dlp's 16:9 thumbnail with proper album art
                _t, _a, _u = title, artist, video_url
                ydl_opts["_lyrics_callback"] = lambda fp, t=_t, a=_a, u=_u: _fetch_and_embed_lyrics(fp, u, t, a, embed_cover=True, fetch_lyrics=False)
                ydl_opts["_target_codec"]    = codec

            self._manager.add_download(
                video_url, ydl_opts, {"title": title, "thumbnail": thumb}
            )


# ── Whisper model download dialog ────────────────────────────────────────────

class _WhisperDownloadThread(QThread):
    """Downloads a faster-whisper model from HuggingFace in a background thread."""
    progress = Signal(str)
    finished_ok = Signal()
    error = Signal(str)

    def __init__(self, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self._model = model_name

    def run(self) -> None:
        try:
            from faster_whisper import WhisperModel
            self.progress.emit(f"Downloading faster-whisper model '{self._model}'…")
            WhisperModel(self._model, device="cpu", compute_type="int8")
            self.finished_ok.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class _WhisperModelDialog(QDialog):
    """
    Shown when the selected faster-whisper model is not cached locally.
    Offers to download it or cancel (in which case transcription is skipped).
    """
    def __init__(self, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Whisper Model Required")
        self.setMinimumWidth(420)
        self._model  = model_name
        self._thread: _WhisperDownloadThread | None = None
        self._ok     = False

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        self._lbl = QLabel(
            f"The faster-whisper model <b>{model_name}</b> is not cached locally.\n"
            "Download it now? (Required for lyrics transcription.)"
        )
        self._lbl.setWordWrap(True)
        lay.addWidget(self._lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Download")
        btns.accepted.connect(self._start_download)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _start_download(self) -> None:
        self._ok_btn.setEnabled(False)
        self._bar.setVisible(True)
        self._lbl.setText(f"Downloading '{self._model}'…")
        self._thread = _WhisperDownloadThread(self._model, self)
        self._thread.finished_ok.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self) -> None:
        self._ok = True
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._lbl.setText(f"Download failed:\n{msg}")
        self._bar.setVisible(False)
        self._ok_btn.setEnabled(True)

    def model_ready(self) -> bool:
        return self._ok


def _check_whisper_model(model_name: str, parent=None) -> bool:
    """
    Ensure the whisper model is on disk. Shows a download dialog if not.
    Returns True if the model is ready, False if user cancelled or download failed.
    """
    if _is_whisper_model_cached(model_name):
        return True
    dlg = _WhisperModelDialog(model_name, parent)
    dlg.exec()
    return dlg.model_ready()


# ── Artist discography fetch thread ──────────────────────────────────────────

class _ArtistFetchThread(QThread):
    """Fetch an artist's full discography (Albums + EPs + Singles) via ytmusicapi."""
    result_ready = Signal(dict)   # {"artist_name": str, "releases": list[dict]}
    error        = Signal(str)

    def __init__(self, channel_url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = channel_url

    def run(self) -> None:
        import sys, re as _re
        import yt_dlp

        # Extract UC… channel ID.  Only the /channel/UC… URL format is reliable.
        # The /browse/MPADU… format embeds a different internal ID and is not
        # guaranteed to work — guide users to use the /channel/ URL instead.
        m = _re.search(r'(UC[A-Za-z0-9_-]{22})', self._url)
        if not m:
            self.error.emit(
                f"Could not find a channel ID in:\n{self._url}\n\n"
                "Use the artist channel URL in this format:\n"
                "  https://music.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxxx\n\n"
                "On YouTube Music: open the artist page → click the channel name "
                "→ copy the URL from your browser's address bar."
            )
            return
        channel_id = m.group(1)
        print(f"[artist] fetching discography  channelId={channel_id!r}",
              file=sys.stderr, flush=True)

        # ── Stage 1: ytmusicapi ───────────────────────────────────────────────
        # Always try ytmusicapi first — it gives artist name and Album/EP/Single
        # type labels that yt-dlp cannot provide.  get_artist() itself is reliable;
        # only get_artist_albums() is broken in ytmusicapi 1.11.x (parser bug).
        artist_name  = ""
        type_hints:  dict[str, str] = {}   # lower(title) → "album"|"ep"|"single"
        ytm_releases: list[dict]    = []
        need_full_list = False             # True when get_artist_albums() failed

        try:
            from ytmusicapi import YTMusic
            ytm  = YTMusic()
            data = ytm.get_artist(channel_id)
            artist_name = data.get("name", "")

            def _thumb_yt(thumbs) -> str:
                return (thumbs or [{}])[-1].get("url", "")

            def _release_yt(item: dict, default_type: str) -> dict | None:
                pl = item.get("audioPlaylistId") or item.get("playlistId", "")
                if not pl:
                    return None
                title = item.get("title", "Unknown")
                rtype = item.get("type", default_type).lower()
                type_hints[title.lower()] = rtype
                return {
                    "title":        title,
                    "type":         rtype,
                    "year":         item.get("year", ""),
                    "playlist_url": f"https://music.youtube.com/playlist?list={pl}",
                    "artist":       artist_name,
                    "thumbnail":    _thumb_yt(item.get("thumbnails")),
                }

            def _fetch_section(section_key: str, default_type: str) -> tuple[list[dict], bool]:
                """Returns (releases, got_full_list)."""
                section = data.get(section_key) or {}
                params  = section.get("params")
                if params:
                    try:
                        items = ytm.get_artist_albums(channel_id, params)
                        print(f"[artist] ytmusicapi {section_key}: {len(items)} (full)",
                              file=sys.stderr, flush=True)
                        return [r for item in items
                                if (r := _release_yt(item, default_type))], True
                    except Exception as exc:
                        print(f"[artist] get_artist_albums({section_key}) failed: {exc!r}",
                              file=sys.stderr, flush=True)
                        # Fall through — use the preview results as type-hint seed
                else:
                    # No params → preview IS the complete list (artist has few releases)
                    items = section.get("results", [])
                    return [r for item in items
                            if (r := _release_yt(item, default_type))], True

                # get_artist_albums failed: harvest the preview as type hints only
                for item in section.get("results", []):
                    t = item.get("title", "")
                    if t:
                        type_hints[t.lower()] = item.get("type", default_type).lower()
                return [], False

            alb, alb_full = _fetch_section("albums",  "Album")
            sng, sng_full = _fetch_section("singles", "Single")
            ytm_releases  = alb + sng
            need_full_list = not (alb_full and sng_full)

        except ImportError:
            print("[artist] ytmusicapi not installed — falling back to yt-dlp only",
                  file=sys.stderr, flush=True)
            need_full_list = True
        except Exception as exc:
            print(f"[artist] ytmusicapi error: {exc!r}", file=sys.stderr, flush=True)
            need_full_list = True

        # ── Stage 2: yt-dlp fallback (full list) ─────────────────────────────
        # ytmusicapi's get_artist_albums() parser is broken in v1.11.x, so we
        # fall back to yt-dlp to enumerate all release playlists.
        #
        # Strategy (try in order until one succeeds):
        #   A. /releases tab  — exists on most artist channels
        #   B. /playlists tab — always exists; filter to OLAK5uy_ IDs which are
        #      YouTube Music's official album/EP/single release playlists
        #
        # Type info comes from the ytmusicapi seed (type_hints) collected above.
        yt_releases: list[dict] = []

        def _parse_entries(info: dict) -> list[dict]:
            """Convert yt-dlp flat-extract entries into release dicts."""
            result = []
            ch = (info.get("channel") or info.get("uploader") or "")
            nonlocal artist_name
            if not artist_name and ch:
                artist_name = ch
            for entry in (info.get("entries") or []):
                if not entry:
                    continue
                title = entry.get("title") or "Unknown"
                pl_id = entry.get("id") or ""
                if not pl_id:
                    continue
                thumbs = entry.get("thumbnails") or []
                thumb  = thumbs[-1].get("url", "") if thumbs else ""
                year   = str(entry.get("release_year") or entry.get("year") or "")
                rtype  = type_hints.get(title.lower(), "album")
                result.append({
                    "title":        title,
                    "type":         rtype,
                    "year":         year,
                    "playlist_url": f"https://www.youtube.com/playlist?list={pl_id}",
                    "artist":       artist_name,
                    "thumbnail":    thumb,
                })
            return result

        if need_full_list:
            ydl_opts = {
                "extract_flat": "in_playlist",
                "quiet":        True,
                "no_warnings":  True,
            }

            # ── A: /releases tab ─────────────────────────────────────────────
            releases_url = f"https://www.youtube.com/channel/{channel_id}/releases"
            print(f"[artist] yt-dlp try /releases: {releases_url}",
                  file=sys.stderr, flush=True)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(releases_url, download=False)
                yt_releases = _parse_entries(info or {})
                print(f"[artist] /releases tab: {len(yt_releases)} entries",
                      file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[artist] /releases tab error: {exc!r}", file=sys.stderr, flush=True)

            # ── B: /playlists tab (filter to OLAK5uy_ official release IDs) ─
            if not yt_releases:
                playlists_url = f"https://www.youtube.com/channel/{channel_id}/playlists"
                print(f"[artist] yt-dlp try /playlists: {playlists_url}",
                      file=sys.stderr, flush=True)
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(playlists_url, download=False)
                    all_pl = _parse_entries(info or {})
                    # OLAK5uy_ prefix = YouTube Music official release playlists
                    # (albums, EPs, singles) — filter out fan/topic playlists
                    yt_releases = [
                        r for r in all_pl
                        if r["playlist_url"].split("list=")[-1].startswith("OLAK5uy_")
                    ]
                    print(
                        f"[artist] /playlists tab: {len(all_pl)} total, "
                        f"{len(yt_releases)} OLAK5uy_ releases",
                        file=sys.stderr, flush=True,
                    )
                except Exception as exc:
                    print(f"[artist] /playlists tab error: {exc!r}",
                          file=sys.stderr, flush=True)

        # ── Merge results ─────────────────────────────────────────────────────
        # Prefer yt-dlp list (complete) when it found more than ytmusicapi did.
        if len(yt_releases) > len(ytm_releases):
            releases = yt_releases
            print(f"[artist] using yt-dlp list ({len(yt_releases)} releases)",
                  file=sys.stderr, flush=True)
        else:
            releases = ytm_releases
            print(f"[artist] using ytmusicapi list ({len(ytm_releases)} releases)",
                  file=sys.stderr, flush=True)

        if not releases:
            self.error.emit(
                f"No releases found for channel {channel_id}.\n\n"
                "Make sure the URL is a valid YouTube Music artist channel."
            )
            return

        print(f"[artist] {len(releases)} releases for {artist_name!r}",
              file=sys.stderr, flush=True)
        self.result_ready.emit({"artist_name": artist_name, "releases": releases})


# ── Artist widget ─────────────────────────────────────────────────────────────

class ArtistWidget(QWidget):
    """
    Artist tab: fetches a YouTube Music artist's discography via ytmusicapi and
    presents Albums / EPs / Singles as checkable items.

    Each selected release is downloaded as a full playlist with proper structure:
        out_dir / ArtistName / AlbumTitle  / 01. track.mp3   (Album / EP)
        out_dir / ArtistName / Singles     / track.mp3        (Single)
    """

    def __init__(self, manager: DownloadManager, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._manager       = manager
        self._settings      = settings
        self._releases: list[dict] = []
        self._artist_name:  str = ""
        self._fetch_thread: Optional[_ArtistFetchThread] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(10)

        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(
            "https://music.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxxx"
        )
        self._fetch_btn = QPushButton("Fetch discography")
        self._fetch_btn.setProperty("role", "secondary")
        self._fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(self._url_edit)
        url_row.addWidget(self._fetch_btn)
        root.addLayout(url_row)

        self._status_lbl = QLabel(
            "Paste a music.youtube.com/channel/UC… URL and click 'Fetch discography'."
        )
        self._status_lbl.setProperty("role", "muted")
        root.addWidget(self._status_lbl)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ── Left: controls ────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)

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
        self._dl_btn = QPushButton("⬇  Download selected")
        self._dl_btn.setFixedHeight(42)
        self._dl_btn.clicked.connect(self._download_selected)
        left.addWidget(self._dl_btn)

        body.addLayout(left, 2)

        # ── Right: release list ───────────────────────────
        self._list = QListWidget()
        self._list.itemChanged.connect(self._update_count)
        body.addWidget(self._list, 3)

        root.addLayout(body)

    def _fetch(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        self._list.clear()
        self._releases = []
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("Fetching…")
        self._status_lbl.setText("Fetching discography…")
        thread = _ArtistFetchThread(url)
        thread.result_ready.connect(self._on_result)
        thread.error.connect(self._on_error)
        thread.finished.connect(lambda: (
            self._fetch_btn.setEnabled(True),
            self._fetch_btn.setText("Fetch discography"),
        ))
        self._fetch_thread = thread
        thread.start()

    def _on_result(self, data: dict) -> None:
        self._artist_name = data["artist_name"]
        self._releases    = data["releases"]
        self._list.clear()
        for rel in self._releases:
            rtype = {"album": "Album", "ep": "EP", "single": "Single"}.get(
                rel["type"], rel["type"].capitalize()
            )
            year  = f"  ({rel['year']})" if rel["year"] else ""
            item  = QListWidgetItem(f"[{rtype}]  {rel['title']}{year}")
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        n = len(self._releases)
        self._status_lbl.setText(
            f"Found {n} release{'s' if n != 1 else ''} for {self._artist_name}"
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
            QMessageBox.warning(self, "Nothing selected", "Select at least one release.")
            return

        codec       = self._fmt_combo.currentText()
        quality     = self._q_combo.currentText().split()[0]
        embed_thumb = self._thumb_chk.isChecked()
        fetch_lyr   = self._lyrics_chk.isChecked()
        out_dir     = self._out_edit.text().strip() or self._settings.get("output_dir")
        os.makedirs(out_dir, exist_ok=True)

        for idx in selected_idx:
            rel      = self._releases[idx]
            rtype    = rel["type"].lower()   # "album" | "ep" | "single"
            pl_url   = rel["playlist_url"]
            thumb    = rel["thumbnail"]
            artist_f = _safe_folder(self._artist_name) or "Unknown Artist"
            title_f  = _safe_folder(rel["title"])       or "Unknown"

            # Folder structure based on release type
            if rtype == "single":
                tpl = os.path.join(
                    out_dir, artist_f, "Singles", "%(title)s.%(ext)s"
                )
            else:
                # Album / EP — numbered tracks using yt-dlp's playlist_index
                tpl = os.path.join(
                    out_dir, artist_f, title_f,
                    "%(playlist_index)02d. %(title)s.%(ext)s"
                )

            ydl_opts = {
                "format":         "bestaudio/best",
                "postprocessors": _build_audio_postprocessors(codec, quality, embed_thumb),
                "writethumbnail": embed_thumb,
                "outtmpl":        tpl,
                "noplaylist":     False,   # download the whole release playlist
                "quiet":          True,
                "no_warnings":    True,
                "js_runtimes":    {"node": {}},
            }

            # Title/artist not known per-track at queue time;
            # _fetch_and_embed_lyrics will read them from embedded metadata.
            if fetch_lyr or embed_thumb:
                _c, _fl = embed_thumb, fetch_lyr
                ydl_opts["_lyrics_callback"] = (
                    lambda fp, c=_c, fl=_fl:
                    _fetch_and_embed_lyrics(fp, "", "", "", embed_cover=c, fetch_lyrics=fl)
                )
                ydl_opts["_target_codec"] = codec

            self._manager.add_download(
                pl_url, ydl_opts,
                {"title": f"{self._artist_name} — {rel['title']}", "thumbnail": thumb},
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
        self._stack.addWidget(ArtistWidget(self._manager, self._settings))
        self._stack.addWidget(CollectionWidget(self._manager, self._settings, mode="album"))
        self._stack.addWidget(CollectionWidget(self._manager, self._settings, mode="playlist"))

        nav = NavBar(["Single Track", "Artist", "Album", "Playlist"], self._stack)
        root.addWidget(nav)
        root.addWidget(self._stack)
