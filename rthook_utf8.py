"""
PyInstaller runtime hook — force UTF-8 stdio before any app code runs.
Referenced in yt_dlp_gui.spec via runtime_hooks=[].
"""
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8:replace")

# In windowed (console=False) PyInstaller builds on Windows, sys.stdout/stderr
# may be None or NullWriter objects that still encode text using the system
# locale (cp1252) before discarding it.  Writing CJK/emoji characters (e.g.
# Japanese song titles) to a cp1252 stream raises:
#   UnicodeEncodeError: 'charmap' codec can't encode character …
#
# Fix:
#   • Real console (console=True build): fileno() succeeds → reconfigure UTF-8.
#   • No console (console=False build):  fileno() raises → replace the stream
#     with an open(os.devnull) using UTF-8 so all prints succeed silently.

def _fix_stream(stream):
    # Check whether this is a real, working console stream.
    try:
        if stream is not None and stream.fileno() >= 0:
            # Real console — just reconfigure the encoding.
            stream.reconfigure(encoding="utf-8", errors="replace")
            return stream
    except Exception:
        pass
    # No console or broken stream — replace with a UTF-8 null sink.
    try:
        return open(os.devnull, "w", encoding="utf-8", errors="replace")
    except Exception:
        return stream  # last resort: leave as-is


sys.stdout = _fix_stream(sys.stdout)
sys.stderr = _fix_stream(sys.stderr)
