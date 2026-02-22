Place FFmpeg binaries here before building with PyInstaller
=============================================================

Required files
--------------
  ffmpeg.exe    – main FFmpeg executable
  ffprobe.exe   – FFmpeg probe tool (used by yt-dlp for format detection)

Where to get them
-----------------
  Download a pre-built Windows build from:
    https://www.gyan.dev/ffmpeg/builds/          (recommended "release essentials" build)
    https://github.com/BtbN/FFmpeg-Builds/releases

  Extract the archive and copy ffmpeg.exe and ffprobe.exe from the bin/ folder
  inside the archive into THIS directory.

At runtime
----------
  The app calls resource_path("bin") to locate this folder regardless of
  whether it is running from source or as a compiled PyInstaller executable.
  yt-dlp's ffmpeg_location option is set automatically when the folder exists.
