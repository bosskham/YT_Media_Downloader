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
