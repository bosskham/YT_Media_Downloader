"""
fix_covers.py — Batch crop embedded album art to square for existing audio files.

Usage:
    python fix_covers.py "C:\\Music"
    python fix_covers.py "C:\\Music" --dry-run   # preview without changing files

Supports: .mp3, .flac, .m4a, .aac
Requires: mutagen, Pillow  (pip install mutagen Pillow)
"""
import argparse
import io
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

try:
    import mutagen
except ImportError:
    sys.exit("mutagen is required: pip install mutagen")


SUPPORTED = {".mp3", ".flac", ".m4a", ".aac"}


def _crop_square(data: bytes) -> tuple[bytes, str] | None:
    """
    Center-crop image bytes to square.
    Returns (cropped_bytes, format_str) or None if already square / error.
    """
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w == h:
            return None  # already square
        size = min(w, h)
        left = (w - size) // 2
        top  = (h - size) // 2
        img  = img.crop((left, top, left + size, top + size))
        fmt  = img.format or "JPEG"
        buf  = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue(), f"{w}x{h} → {size}x{size}"
    except Exception as exc:
        print(f"    [!] image error: {exc}", file=sys.stderr)
        return None


def fix_mp3(path: Path, dry_run: bool) -> bool:
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        try:
            audio = ID3(str(path))
        except ID3NoHeaderError:
            return False
        frames = audio.getall("APIC")
        if not frames:
            return False
        changed = False
        for frame in frames:
            result = _crop_square(frame.data)
            if result:
                cropped, info = result
                print(f"  mp3  {info}  {path.name}")
                if not dry_run:
                    frame.data = cropped
                    changed = True
        if changed:
            audio.save(str(path))
        return changed
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def fix_flac(path: Path, dry_run: bool) -> bool:
    from mutagen.flac import FLAC
    try:
        audio = FLAC(str(path))
        if not audio.pictures:
            return False
        changed = False
        for pic in audio.pictures:
            result = _crop_square(pic.data)
            if result:
                cropped, info = result
                print(f"  flac {info}  {path.name}")
                if not dry_run:
                    pic.data = cropped
                    changed = True
        if changed:
            audio.save()
        return changed
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def fix_m4a(path: Path, dry_run: bool) -> bool:
    from mutagen.mp4 import MP4, MP4Cover
    try:
        audio = MP4(str(path))
        covr = audio.get("covr")
        if not covr:
            return False
        changed = False
        new_covers = []
        for cover in covr:
            result = _crop_square(bytes(cover))
            if result:
                cropped, info = result
                print(f"  m4a  {info}  {path.name}")
                if not dry_run:
                    new_covers.append(MP4Cover(cropped, imageformat=MP4Cover.FORMAT_JPEG))
                    changed = True
                else:
                    new_covers.append(cover)
            else:
                new_covers.append(cover)
        if changed:
            audio["covr"] = new_covers
            audio.save()
        return changed
    except Exception as exc:
        print(f"    [!] {path.name}: {exc}", file=sys.stderr)
        return False


def process_dir(root: Path, dry_run: bool) -> None:
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED)
    if not files:
        print("No supported audio files found.")
        return

    total = len(files)
    fixed = 0
    skipped = 0

    print(f"Scanning {total} file(s) in {root}")
    if dry_run:
        print("  (dry-run — no files will be modified)")
    print()

    for i, path in enumerate(files, 1):
        ext = path.suffix.lower()
        try:
            if ext == ".mp3":
                changed = fix_mp3(path, dry_run)
            elif ext == ".flac":
                changed = fix_flac(path, dry_run)
            elif ext in (".m4a", ".aac"):
                changed = fix_m4a(path, dry_run)
            else:
                changed = False

            if changed:
                fixed += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"  [!] {path.name}: {exc}", file=sys.stderr)
            skipped += 1

        # Progress every 50 files
        if i % 50 == 0:
            print(f"  ... {i}/{total}")

    print()
    action = "Would fix" if dry_run else "Fixed"
    print(f"Done. {action} {fixed} file(s), {skipped} already square or skipped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch crop embedded album art to square.")
    parser.add_argument("directory", help="Root directory to scan recursively")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying any files")
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    process_dir(root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
