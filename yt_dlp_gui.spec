# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 6.x spec file for YT-DLP GUI
#
# Build command (run from project root):
#   pyinstaller yt_dlp_gui.spec
#
# Prerequisites:
#   pip install pyinstaller==6.14.2
#   pip install "yt-dlp[default]"   ← installs yt-dlp-ejs (JS challenge solver scripts)
#   Place ffmpeg.exe and ffprobe.exe into bin/ before building.
#
# Runtime requirement (NOT bundled — must be installed on the target machine):
#   Node.js LTS  https://nodejs.org  (needed for YouTube JS challenge / age-restricted videos)
#   Node.js is ~50 MB standalone and is a system-level dependency; bundle it separately
#   if you need a fully self-contained distribution.
#
# Optional packages (include them in your venv before building to bundle them):
#   pip install faster-whisper pykakasi pypinyin unidecode
#   pip install torch --index-url https://download.pytorch.org/whl/cu121  # CUDA
#
# Output: dist/YT-DLP-GUI/  (one-dir bundle)
# ─────────────────────────────────────────────────────────────────────────────

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

# ── Icon ─────────────────────────────────────────────────────────────────────
_icon_file = ROOT / "icon.ico"
if not _icon_file.exists():
    print("[WARN] icon.ico not found — exe will use the default PyInstaller icon.")
_icon_str = str(_icon_file) if _icon_file.exists() else None

# ── Static data files ─────────────────────────────────────────────────────────
from PyInstaller.utils.hooks import collect_data_files

_datas = []
if _icon_file.exists():
    _datas.append((str(_icon_file), "."))

# pykakasi dictionary files (kanji/kana conversion tables)
try:
    import pykakasi  # noqa: F401
    _datas += collect_data_files("pykakasi")
    print("[INFO] pykakasi data files collected.")
except Exception:
    pass

# yt-dlp-ejs JavaScript challenge solver scripts
# These JS files are loaded at runtime by yt-dlp to solve YouTube's n-challenge
# and signature challenge (used for age-restricted / protected videos).
try:
    import yt_dlp_ejs  # noqa: F401
    _datas += collect_data_files("yt_dlp_ejs")
    print("[INFO] yt-dlp-ejs data files collected.")
except Exception:
    print("[WARN] yt-dlp-ejs not installed — JS challenge solving will not be bundled.")
    print("       Run: pip install \"yt-dlp[default]\"")

# ── FFmpeg binaries ───────────────────────────────────────────────────────────
_bins = []
for _name in ("ffmpeg.exe", "ffprobe.exe"):
    _src = ROOT / "bin" / _name
    if _src.exists():
        _bins.append((str(_src), "bin"))
    else:
        print(f"[WARN] bin/{_name} not found — FFmpeg will NOT be bundled.")

# ── Hidden imports ────────────────────────────────────────────────────────────
_hidden = [
    # ── yt-dlp ────────────────────────────────────────────────────────────────
    "yt_dlp",
    "yt_dlp.networking",
    "yt_dlp.networking.common",
    "yt_dlp.networking.impersonate",
    "yt_dlp.networking._urllib",
    "yt_dlp.postprocessor",
    "yt_dlp.postprocessor.ffmpeg",
    "yt_dlp.postprocessor.embedthumbnail",
    "yt_dlp.postprocessor.modify_chapters",
    "yt_dlp.extractor",
    "yt_dlp.extractor.youtube",
    # ── yt-dlp-ejs (JS challenge solver — installed via yt-dlp[default]) ──────
    "yt_dlp_ejs",
    # ── Pillow (thumbnail crop-to-square) ─────────────────────────────────────
    "PIL",
    "PIL.Image",
    # ── yt-dlp[default] dependencies ──────────────────────────────────────────
    "websockets",           # async websocket support
    "brotli",               # brotli content-encoding decompression
    "Cryptodome",           # pycryptodomex: AES decryption for some extractors
    "Cryptodome.Cipher",
    "Cryptodome.Cipher.AES",
    # ── PySide6 network (thumbnail loading) ───────────────────────────────────
    "PySide6.QtNetwork",
    # ── mutagen ───────────────────────────────────────────────────────────────
    "mutagen",
    "mutagen.id3",
    "mutagen.flac",
    "mutagen.mp4",
    "mutagen.mp3",
    "mutagen.ogg",
    "mutagen.oggvorbis",
    # ── tqdm (used by ctranslate2/faster-whisper; disabled_tqdm needs _lock) ──
    "tqdm",
    "tqdm.auto",
    "tqdm.std",
    "tqdm.utils",
    # ── stdlib extras sometimes missed by the analyser ────────────────────────
    "urllib.request",
    "http.cookiejar",
    "xml.etree.ElementTree",
    "email.mime.multipart",
]

# ── Optional: faster-whisper + romanization libs ──────────────────────────────
# Each block is conditional: only added when the package is actually installed
# in the build venv.  Missing packages are skipped gracefully.

try:
    import faster_whisper  # noqa: F401
    _hidden += [
        "faster_whisper",
        "faster_whisper.audio",
        "faster_whisper.transcribe",
        "faster_whisper.tokenizer",
        "faster_whisper.utils",
        "faster_whisper.vad",
        "ctranslate2",
        "tokenizers",
        "huggingface_hub",
        "huggingface_hub.file_download",
    ]
    print("[INFO] faster-whisper found — will be bundled.")
except ImportError:
    print("[INFO] faster-whisper not installed — transcription fallback will not be bundled.")

try:
    import pykakasi  # noqa: F401
    _hidden += ["pykakasi"]
    print("[INFO] pykakasi found — will be bundled.")
except ImportError:
    print("[INFO] pykakasi not installed — Japanese romanization will not be bundled.")

try:
    import pypinyin  # noqa: F401
    _hidden += ["pypinyin"]
    print("[INFO] pypinyin found — will be bundled.")
except ImportError:
    print("[INFO] pypinyin not installed — Chinese romanization will not be bundled.")

try:
    import unidecode  # noqa: F401
    _hidden += ["unidecode"]
    print("[INFO] unidecode found — will be bundled.")
except ImportError:
    print("[INFO] unidecode not installed — fallback romanization will not be bundled.")

try:
    import torch  # noqa: F401
    _hidden += ["torch", "torch.cuda"]
    print("[INFO] torch found — will be bundled (adds ~1-2 GB).")
except ImportError:
    print("[INFO] torch not installed — CUDA acceleration will not be bundled.")

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=_bins,
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "rthook_utf8.py")],
    excludes=[
        # Not used by this app — save space
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        # numpy is kept: faster-whisper depends on it
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ── EXE ───────────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YT-DLP-GUI",
    icon=_icon_str,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "Qt6*.dll",
        "ffmpeg.exe",    # UPX can corrupt FFmpeg — always exclude
        "ffprobe.exe",
    ],
    console=False,        # set False for release (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ── COLLECT (one-dir bundle) ──────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "Qt6*.dll",
        "ffmpeg.exe",
        "ffprobe.exe",
    ],
    name="YT-DLP-GUI",
)

# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL — one-file build
# ─────────────────────────────────────────────────────────────────────────────
# Replace the EXE + COLLECT blocks above with:
#
#   exe = EXE(
#       pyz, a.scripts, a.binaries, a.datas, [],
#       name="YT-DLP-GUI", icon=_icon_str,
#       debug=False, strip=False, upx=True,
#       upx_exclude=["ffmpeg.exe", "ffprobe.exe"],
#       console=False, runtime_tmpdir=None,
#   )
#
# Note: --onefile re-extracts everything to %TEMP% on every launch (~2-3s extra
# startup) and requires write access to the temp folder.
# ─────────────────────────────────────────────────────────────────────────────
