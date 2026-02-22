from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def resource_path(relative: str = "") -> Path:
    """
    Resolve the absolute path to a bundled resource.

    * Development  : resolves relative to the project root
                     (parent of the ``app/`` package directory).
    * PyInstaller  : resolves relative to ``sys._MEIPASS`` — the directory
                     where the frozen bundle is extracted at runtime.

    Parameters
    ----------
    relative:
        Path string relative to the project / bundle root, e.g. ``"bin"``.
        Pass nothing (or ``""``) to get the root directory itself.

    Returns
    -------
    Path
        Absolute ``pathlib.Path`` to the resource.
        Convert to ``str`` when passing to C-level APIs or yt-dlp options.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running as a PyInstaller bundle
        base = Path(sys._MEIPASS)
    else:
        # Running from source: app/settings.py → parent = app/ → parent = project root
        base = Path(__file__).resolve().parent.parent
    return (base / relative) if relative else base

_CONFIG_DIR = Path.home() / ".config" / "yt_dlp_gui"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_DEFAULTS: dict[str, Any] = {
    "output_dir": str(Path.home() / "Downloads" / "YT-DLP"),
    "theme": "dark",
    "max_concurrent": 2,
    # Video
    "video_format": "mp4",
    "video_quality": "bestvideo+bestaudio/best",
    # Music
    "audio_format": "mp3",
    "audio_quality": "320",
    # Music extras
    "embed_thumbnail": True,
    "embed_metadata": True,
    "fetch_lyrics": True,
    "whisper_model": "base",   # tiny | base | small | medium | large
    # Playlist
    "playlist_subfolder": True,
}


class Settings:
    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._load()

    # ── public ───────────────────────────────────────────
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)
        self._save()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    # ── private ──────────────────────────────────────────
    def _load(self) -> None:
        if _CONFIG_FILE.exists():
            try:
                loaded = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                self._data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


# Singleton instance
_instance: Settings | None = None


def get_settings() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
