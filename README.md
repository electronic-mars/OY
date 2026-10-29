# OY Player

A free, open-source video player for Windows 10 and 11 that also cuts the video you are watching.

- **Watch:** local files and streams through libmpv, with hardware decoding, a playlist that finds the next episodes, skipping of openings and credits, and a key for every command.
- **Cut:** mark a piece with I and O and save it losslessly, without re-encoding; join pieces from several files.
- **Draw:** put text, arrows, rectangles or a pencil line over the picture for a chosen time range, and save it into the clip.

No ads, no telemetry, no account. Licensed under the [GNU GPL v3](LICENSE).

> **Status:** preview. The interface is in English and Ukrainian (as Windows speaks, or chosen in the settings). See [CHANGELOG.md](CHANGELOG.md).

## Download

Installers are attached to the [GitHub releases](https://github.com/electronic-mars/OY/releases). The installer is per-user and needs no administrator rights. It is not code-signed yet, so Windows SmartScreen will ask for confirmation on first start.

## Build from source

Needs Windows 10 or 11, Python 3.14, and:

- `vendor/mpv/libmpv-2.dll` from a [shinchiro mpv build](https://github.com/shinchiro/mpv-winbuild-cmake);
- `ffmpeg` and `ffprobe` on the PATH (the build looks in `C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin` or `OY_FFMPEG_DIR`);
- for the installer, Inno Setup 6.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-build.txt
OYPlayer.cmd
tools\build.cmd
```

`OYPlayer.cmd` runs the player from source; `tools\build.cmd` builds `dist\OYPlayer\` and the installer.

## Third-party components

FFmpeg, libmpv, Qt and others are listed with their licences and sources in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
