"""
PyInstaller runtime hook — force UTF-8 stdio before any app code runs.
Referenced in yt_dlp_gui.spec via runtime_hooks=[].
"""
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")

for _s in (sys.stdout, sys.stderr):
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Pre-import tqdm fully in the main thread so it is cached in sys.modules
# before any worker threads start.  ctranslate2/faster-whisper import tqdm
# lazily; if two lyrics threads race to import it simultaneously inside a
# PyInstaller bundle the class can be partially initialised, leaving
# ctranslate2's disabled_tqdm stub without _lock →
# AttributeError("type object 'disabled_tqdm' has no attribute '_lock'").
try:
    import tqdm          # noqa: F401
    import tqdm.auto     # noqa: F401
    import tqdm.std      # noqa: F401
    import tqdm.utils    # noqa: F401
except Exception:
    pass
