"""
embed_covers.py — Batch-embed cover art from yt-dlp playlist sidecars into audio files.

When yt-dlp downloads a playlist with --write-thumbnail, it saves a playlist-level
thumbnail as "00. <playlist title>.jpg" in the album folder. This file is never deleted
(unlike per-track thumbnails) and always contains the correct release artwork.

This script finds every such "00. *.jpg" sidecar and embeds it as album art into all
.mp3 / .flac / .m4a / .aac files in the same folder.

Usage:
    python embed_covers.py "C:\\Music\\YOASOBI"
    python embed_covers.py "C:\\Music" --dry-run   # preview without changing files

Requires: mutagen  (pip install mutagen)
"""
import argparse
import os
import sys
from pathlib import Path

try:
    import mutagen  # noqa: F401
except ImportError:
    sys.exit("mutagen is required: pip install mutagen")


AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac"}


def _find_cover_sidecar(folder: Path) -> Path | None:
    """Return the '00. *.jpg' playlist thumbnail in folder, or None."""
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.name.startswith("00.") and f.suffix.lower() == ".jpg":
            return f
    return None


def _embed_mp3(path: Path, img_bytes: bytes, dry_run: bool) -> bool:
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError
    try:
        try:
            audio = ID3(str(path))
        except ID3NoHeaderError:
            audio = ID3()
        if not dry_run:
            audio.delall("APIC")
            audio.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=img_bytes))
            audio.save(str(path))
        return True
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def _embed_flac(path: Path, img_bytes: bytes, dry_run: bool) -> bool:
    from mutagen.flac import FLAC, Picture
    try:
        audio = FLAC(str(path))
        if not dry_run:
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = img_bytes
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
        return True
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def _embed_m4a(path: Path, img_bytes: bytes, dry_run: bool) -> bool:
    from mutagen.mp4 import MP4, MP4Cover
    try:
        audio = MP4(str(path))
        if not dry_run:
            audio["covr"] = [MP4Cover(img_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
        return True
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def _embed_cover(path: Path, img_bytes: bytes, dry_run: bool) -> bool:
    ext = path.suffix.lower()
    if ext == ".mp3":
        return _embed_mp3(path, img_bytes, dry_run)
    if ext == ".flac":
        return _embed_flac(path, img_bytes, dry_run)
    if ext in (".m4a", ".aac"):
        return _embed_m4a(path, img_bytes, dry_run)
    return False


def process_folder(folder: Path, dry_run: bool) -> tuple[int, int]:
    """Embed cover into all audio files in folder. Returns (done, errors)."""
    cover = _find_cover_sidecar(folder)
    if not cover:
        return 0, 0

    audio_files = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    )
    if not audio_files:
        return 0, 0

    with open(cover, "rb") as fh:
        img_bytes = fh.read()

    done = errors = 0
    tag = "(dry-run) " if dry_run else ""
    print(f"\n  {tag}Cover: {cover.name}  →  {len(audio_files)} file(s)")
    for af in audio_files:
        ok = _embed_cover(af, img_bytes, dry_run)
        if ok:
            print(f"    {'would embed' if dry_run else '✓'} {af.name}")
            done += 1
        else:
            errors += 1
    return done, errors


def process_dir(root: Path, dry_run: bool) -> None:
    total_done = total_errors = folders = 0

    print(f"Scanning {root}")
    if dry_run:
        print("  (dry-run — no files will be modified)")

    for dirpath, dirnames, _ in os.walk(root):
        dirnames.sort()
        d, e = process_folder(Path(dirpath), dry_run)
        if d or e:
            folders += 1
            total_done   += d
            total_errors += e

    print()
    action = "Would embed" if dry_run else "Embedded"
    print(f"Done. {action} cover art in {total_done} file(s) across {folders} folder(s).", end="")
    if total_errors:
        print(f"  {total_errors} error(s).")
    else:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed cover art from yt-dlp '00. *.jpg' sidecars into audio files."
    )
    parser.add_argument("directory", help="Root directory to scan recursively")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would change without modifying files")
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    process_dir(root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
