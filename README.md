# YT Media Downloader

A desktop app for downloading YouTube videos and music, with a proper music-library workflow on top: square album art, tags, artist discographies, and synchronized lyrics. It's a friendly [PySide6](https://doc.qt.io/qtforpython-6/) front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp) and FFmpeg.

[![Latest release](https://img.shields.io/github/v/release/bosskham/YT_Media_Downloader)](https://github.com/bosskham/YT_Media_Downloader/releases/latest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

- [Features](#features)
- [Install (for users)](#install-for-users)
- [Using the app](#using-the-app)
- [Where your files go](#where-your-files-go)
- [Settings](#settings)
- [Troubleshooting](#troubleshooting)
- [How it works (for contributors)](#how-it-works-for-contributors)
- [Run from source](#run-from-source) · [Build the exe](#build-the-exe)
- [Known gaps](#known-gaps) · [License and credits](#license-and-credits)

---

## Features

**Video**
- Single videos, whole playlists, or an entire channel, with a checklist so you pick what to download.
- Quality from 360p up to 4K (or audio only), saved as MP4, MKV or WebM.

**Music**
- Audio as MP3, FLAC, AAC, Opus or M4A at 96 to 320 kbps.
- Cover art is cropped to a square and embedded, and tags are written to the file.
- **Artist tab:** paste a YouTube Music artist link and queue their whole discography, organized into `Albums & EPs` and `Singles` folders.
- **Lyrics tab:** transcribe songs with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) into time-synced (LRC) lyrics, with romanization for Japanese, Chinese and Korean.
- **Fix Covers** and **Metadata** tabs repair music you already have, with no re-download.

**Everywhere**
- A download queue with progress, speed, ETA, cancel, and configurable parallelism (1 to 5).
- Dark and light themes.
- FFmpeg is bundled, so there's nothing else to set up.

---

## Install (for users)

1. Open the [latest release](https://github.com/bosskham/YT_Media_Downloader/releases/latest) and download **`YT.Media.Downloader.zip`** (about 200 MB).
2. Extract the zip anywhere you like. Keep the folder intact, because the app needs the `_internal` folder next to the exe.
3. Run **`YT-DLP-GUI.exe`**.

That's it. Windows SmartScreen may warn about an unrecognized app because the exe isn't code-signed. Choose **More info → Run anyway**.

**Optional, but needed for some videos:** install [Node.js](https://nodejs.org) (LTS). YouTube protects some videos, including age-restricted ones, with JavaScript challenges that yt-dlp solves using Node. Without Node, most videos still work. Age-restricted ones will fail.

**Age-restricted or members-only videos** also need you to be signed in. See [Cookies](#cookies-age-restricted-videos).

---

## Using the app

The window has two main tabs on the left (**Video** and **Music**) and the **download queue** on the right. Every tab works the same way: paste a URL, adjust options, click download, and watch the job appear in the queue.

### Video tab

| Sub-tab | What it does |
|---|---|
| **Single Video** | Paste a URL. Choose quality and container, then download. |
| **Playlist** | Paste a playlist URL and click **Fetch videos**. Tick the videos you want, then download. |
| **Channel** | Same as Playlist, but for a channel (`youtube.com/@Name` or `/channel/…`). |

### Music tab

| Sub-tab | What it does |
|---|---|
| **Single Track** | One song from a YouTube or YouTube Music URL. |
| **Artist** | Paste an artist's `music.youtube.com/channel/UC…` URL and click **Fetch discography**. Tick the albums, EPs and singles you want, and each is downloaded as a numbered release with the correct release cover art and the *album artist* tag. |
| **Album** | Paste an album playlist URL (`music.youtube.com/playlist?list=…`). Choose tracks, then download. |
| **Playlist** | Same as Album, for any YouTube or YouTube Music playlist. |
| **Lyrics** | Pick a folder of audio files. Each is transcribed with faster-whisper and the lyrics are embedded. |
| **Fix Covers** | Pick a folder of music you already have. Finds each album's `00. *.jpg` cover file and embeds it into every track in that folder. |
| **Metadata** | Pick a local album folder, paste its YouTube Music URL, and write correct title / artist / album / year / track number tags, with no re-download. |

> **Getting the Artist URL:** on YouTube Music, open the artist's page, click the channel name, and copy the address (it looks like `https://music.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx`). Only this `/channel/UC…` format is supported.

### The Lyrics tab

1. **Browse** to a folder and click **Scan**. The audio files are listed.
2. Pick a **Model**: `tiny`, `base`, `small`, `medium`, `large` or `turbo`. Bigger models are more accurate but slower. Tick **Romanize (ja / zh / ko)** if you want romanized lines.
3. Click **Transcribe All** (there's a **Cancel** button too). The first time you use a model, the app offers to download it from Hugging Face. Models are not bundled.
4. Each file is transcribed **on the CPU** and saved as synced `[mm:ss.xx]` lyrics. With romanization on, each line becomes `original ♪ romanized`.

Lyrics are stored in the file's tags: `USLT` for MP3, `LYRICS` for FLAC and `©lyr` for M4A/AAC. Downloads do **not** fetch lyrics automatically. Use the Lyrics tab afterward.

### The Metadata tab (matching rule)

Tracks are matched **by position**: the first track on the URL is the first file in the folder, sorted by filename. If the URL has a different number of tracks than the folder has files, the app stops and warns you instead of guessing. Make sure the URL and the folder are the same release.

### The queue

Each download is a card with a status badge: **Queued → Downloading → Processing → Done**, or **Error** / **Cancelled**. The **✕** button cancels a running job or removes a finished one, and **Clear completed** tidies the list. On the Artist tab you'll also see **Lyrics…** while the release cover and album-artist tag are being finalized.

---

## Where your files go

The default output folder is `Downloads\YT-DLP`. You can change it in **Settings**, or per download on each tab.

```text
Video / Single track            <output>/<title>.<ext>

Album / Playlist tabs           <output>/<Album or Playlist>/01. <title>.mp3
                                <output>/<Album or Playlist>/00. <Album or Playlist>.jpg   ← cover file

Artist tab                      <output>/<Artist>/Albums & EPs/<Album>/01. <title>.mp3
                                <output>/<Artist>/Singles/<Single>/01. <title>.mp3
```

The `00. … .jpg` file is a copy of the square album art. It's what the **Fix Covers** tab (and `embed_covers.py`) looks for. Turn off **Save playlist tracks in sub-folder** in Settings to save everything flat.

---

## Settings

Open **⚙ Settings** in the header. Values are saved to `%USERPROFILE%\.config\yt_dlp_gui\settings.json`.

| Setting | Default | Notes |
|---|---|---|
| Output directory | `Downloads\YT-DLP` | Where downloads go. |
| Max concurrent downloads | 2 | Range 1 to 5. |
| Default container | mp4 | mp4 / mkv / webm. |
| Default audio format | mp3 | mp3 / flac / aac / opus / m4a. |
| Default audio quality | 320 | 320 / 256 / 192 / 128 / 96 kbps. |
| Embed thumbnail | on | Embeds a square-cropped cover. |
| Embed metadata | on | Writes tags via FFmpeg. |
| Save playlist tracks in sub-folder | on | Uses the folder layout above. |
| Whisper model | base | Default model for the Lyrics tab. |
| Browser cookies / Cookies file | off | See below. |

### Cookies (age-restricted videos)

Some videos need you to be signed in. Two options:

- **Browser cookies:** choose Chrome, Chromium, Firefox, Edge, Brave, Opera or Vivaldi. The app reads the login from that browser. Close Chrome first, or extraction may fail.
- **Cookies file:** export a Netscape-format `cookies.txt` (for example with a browser extension) and select it. It takes priority over the browser setting.

> ⚠️ A cookies file contains your **live login session**. Treat it like a password, and never commit it, post it, or share it. This repo's `.gitignore` excludes `*cookies*.txt` for that reason.

---

## Troubleshooting

| Problem | Try this |
|---|---|
| "Sign in to confirm your age" or a JavaScript-challenge error | Install [Node.js](https://nodejs.org), then set a cookies source in Settings. |
| Browser cookie extraction fails | Close the browser fully, or use a cookies file instead. |
| A video that used to work now fails | YouTube changes often. Update yt-dlp (`pip install -U yt-dlp` if running from source, or grab the newest release). |
| Cover art isn't square | Make sure **Embed thumbnail** is on. For existing files, use **Fix Covers** or `fix_covers.py`. |
| Metadata tab says "Track count mismatch" | The URL and folder aren't the same release, or files are missing. Fix the folder first. |
| Lyrics tab is slow | Transcription runs on the CPU. Use a smaller model (`tiny` / `base`). |
| Artist tab: "Could not find a channel ID" | Use the `/channel/UC…` URL, not a `/browse/…` one. |
| Something else | Run from source (below), where errors print to the console, and open an issue. |

---

## How it works (for contributors)

### The big picture

```text
 ┌────────────────────────── MainWindow ───────────────────────────┐
 │  VideoTab / MusicTab (sub-tabs)      DownloadQueueWidget        │
 │        │  builds ydl_opts                     ▲ cards           │
 └────────┼──────────────────────────────────────┼─────────────────┘
          ▼                                      │ Qt signals
   DownloadManager  ── queue + max_concurrent ───┤
          │ spawns one per job                   │
          ▼                                      │
   DownloadWorker (QThread) ── yt_dlp.YoutubeDL ─┘
          │   progress_hook / postprocessor_hook
          └─ post-download callbacks (Artist tab) run on daemon threads
```

1. A **tab** collects the URL and options and builds a plain yt-dlp options dict (`ydl_opts`).
2. It hands that to `DownloadManager.add_download(url, ydl_opts, metadata)`. The manager keeps a FIFO queue and starts at most `max_concurrent` workers.
3. Each **`DownloadWorker`** is a `QThread` that runs `yt_dlp.YoutubeDL` and turns yt-dlp's hooks into Qt signals (`progress_updated`, `status_changed`, `finished`, `error`).
4. **`DownloadQueueWidget`** listens to the manager's signals and shows a **`DownloadCard`** per job.

The tabs never touch yt-dlp threads directly. Everything crosses the thread boundary as a Qt signal.

### Project layout

```text
main.py                    Entry point (UTF-8 setup, theme, MainWindow)
app/
  main_window.py           Header + splitter: tabs (left) | queue (right)
  download_manager.py      Queue + concurrency control
  settings.py              JSON settings singleton + resource_path()
  theme.py                 Dark/light stylesheets (ThemeManager)
  tabs/
    video_tab.py           Single Video · Playlist · Channel
    music_tab.py           All Music sub-tabs + tag/cover/lyrics helpers (large file)
  widgets/                 DownloadCard, DownloadQueueWidget, SettingsDialog, AboutDialog
  workers/
    download_worker.py     DownloadWorker: yt-dlp run, hooks, cover crop, post-download callbacks
    info_worker.py         InfoWorker: metadata lookup without downloading
bin/                       Bundled ffmpeg.exe / ffprobe.exe
rthook_utf8.py             PyInstaller runtime hook (UTF-8 stdio, tqdm pre-import)
yt_dlp_gui.spec            PyInstaller build
fix_covers.py              Standalone: crop embedded art to square (mp3/flac/m4a/aac)
embed_covers.py            Standalone: embed "00. *.jpg" into audio files
```

### Design notes worth knowing

- **Private option keys.** `DownloadWorker` pops three keys off `ydl_opts` before calling yt-dlp, since they are *ours*, not yt-dlp's: `_lyrics_callback` (a function run per finished file), `_target_codec`, and `_sidecar_dest` (base path for the `00. …` cover file). If you add a key with this style, pop it too.
- **Cover art.** yt-dlp downloads the thumbnail, and on the `EmbedThumbnail` "started" hook the worker crops it to a centered square *in place*, so yt-dlp embeds the square version. For the first track of a collection it also saves a `.jpg` copy as the `00. …` cover file. The **Artist tab** is the exception: its `_lyrics_callback` replaces each track's cover with the release-level art from `ytmusicapi`, and writes the `albumartist` tag.
- **Status flow with callbacks.** With a `_lyrics_callback`, the worker emits `status_changed("lyrics")`, then `finished` right away (freeing the download slot), and the last callback thread emits `status_changed("done")`. The worker keeps a strong reference to itself (`_w = self`) inside those threads so it isn't garbage-collected after `finished`. `DownloadQueueWidget._on_finished` intentionally does nothing, and "done" comes from `status_changed`.
- **Tags** are written with `mutagen` by `_write_tags()`: `title, artist, albumartist, album, year, tracknumber, totaltracks, genre` for MP3 (ID3), FLAC (Vorbis) and M4A/AAC (MP4 atoms).
- **JS challenges.** Every yt-dlp call sets `"js_runtimes": {"node": {}}`. Don't restrict `extractor_args` `player_client`. It breaks age-restricted downloads.
- **Cookies** are injected in `DownloadWorker.run()`: `cookies_file` wins over `cookies_from_browser`.
- **FFmpeg** is found through `resource_path("bin")`, which works from source and inside the PyInstaller bundle. If `bin/` is missing, yt-dlp falls back to `PATH`.
- **UTF-8 on Windows** is handled in three layers (`rthook_utf8.py`, `main.py`, and `opts["encoding"] = "utf-8"`) because the frozen exe defaults to cp1252. A windowed build has no stdio, so the hook swaps in a UTF-8 sink.
- **Romanization** modules are imported lazily and failures are caught broadly (`except Exception`). `pykakasi` needs its dictionary data files bundled, which the spec does with `collect_data_files`.

---

## Run from source

Requires **Windows**, **Python 3.12+**, and (for age-restricted videos) **Node.js**.

```bash
git clone https://github.com/bosskham/YT_Media_Downloader.git
cd YT_Media_Downloader

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

python main.py
```

`requirements.txt` includes `Pillow` (cover cropping, which is silently skipped without it) and `yt-dlp[default]` (the JS challenge solver scripts). The repo ships `bin/ffmpeg.exe` and `bin/ffprobe.exe`, so no separate FFmpeg install is needed.

### Standalone scripts

```bash
python fix_covers.py   "C:\Music" --dry-run   # crop embedded art to square
python embed_covers.py "C:\Music" --dry-run   # embed "00. *.jpg" files
```

Drop `--dry-run` to apply the changes.

## Build the exe

```bash
pip install -r requirements.txt
pyinstaller yt_dlp_gui.spec
```

Output is a one-folder bundle in `dist/YT-DLP-GUI/`. Zip it for release (rename the folder to `YT Media Downloader` first). Set `console=True` in the spec while debugging so you can see output. Keep it `False` for release builds.

## Contributing

Issues and pull requests are welcome. For changes, please:

- Keep the existing style. Type-hinted, `from __future__ import annotations`, small helpers, and comments that explain *why*.
- Test with a real download for the tab you touched, both from source and (if it affects packaging) from a built exe.
- Never commit cookies, tokens or downloaded media.

## Known gaps

Honest notes so nobody is surprised:

- The **"Fetch and embed lyrics"** checkbox in Settings is saved but not wired to anything yet. Lyrics only come from the **Lyrics** tab.
- Whisper runs on the **CPU** only (`int8`), so large models are slow.
- The Metadata tab matches tracks **by position only**.
- `music_tab.py` is large (about 2,500 lines) and would benefit from being split per sub-tab.
- The About dialog and app metadata still say "YT-DLP GUI, version 1.0.0", and the exe and settings folder keep the old name.
- Windows only for now.

## License and credits

Licensed under the [Apache License 2.0](LICENSE).

Made by **Boromey Han** (aka 1ClickDev · dashNdot).

Built on the shoulders of [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org), [PySide6 / Qt](https://doc.qt.io/qtforpython-6/), [mutagen](https://github.com/quodlibet/mutagen), [ytmusicapi](https://github.com/sigma67/ytmusicapi), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Pillow](https://python-pillow.org), and [pykakasi](https://github.com/miurahr/pykakasi) / pypinyin / unidecode for romanization. FFmpeg is bundled under its own license terms.

**Please use this tool responsibly.** Download only content you have the right to save, and respect the terms of service and copyright laws that apply to you.
