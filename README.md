# OY Player

A free, open-source video player for Windows 10 and 11 that also cuts the video you are watching.

- **Watch:** local files and streams through libmpv, with hardware decoding, a playlist that finds the next episodes, skipping of openings and credits, and a key for every command.
- **Cut:** mark a piece with I and O and save it losslessly, without re-encoding; join pieces from several files.
- **Draw:** put text, arrows, rectangles or a pencil line over the picture for a chosen time range, and save it into the clip.

No ads, no telemetry, no account. Licensed under the [GNU GPL v3](LICENSE).

> **Status:** preview. The interface is in 39 languages (as Windows speaks, or chosen in the settings). See [CHANGELOG.md](CHANGELOG.md).

## Download

Installers are attached to the [GitHub releases](https://github.com/electronic-mars/OY/releases). The installer is per-user and needs no administrator rights. It is not code-signed yet, so Windows SmartScreen will ask for confirmation on first start. After that the player updates itself: when a new version is out, About › Update and restart installs it.

## Is it safe?

Windows SmartScreen warns about the installer because it is not code-signed yet: a signing certificate costs money every year, and OY Player is a one-developer open-source project. The warning says Windows does not know the publisher; it does not mean anything was found in the file. To install anyway, choose «More info», then «Run anyway».

You do not have to take that on trust:

- **It is built in public.** Every release is built from this source code by [GitHub Actions](.github/workflows/release.yml) on a clean Windows machine, not on a developer's PC. Each release page links to the run that built it in the repository's [Actions](https://github.com/electronic-mars/OY/actions) tab.
- **Check the file you downloaded.** Each release page shows the installer's SHA-256. In PowerShell:

  ```powershell
  Get-FileHash .\OYPlayer-X.Y.Z-setup.exe -Algorithm SHA256
  ```

  The hash must match the one on the release page.
- **Ask the antivirus engines.** Each release page links to VirusTotal by that hash. If VirusTotal has not seen the file yet, the link offers to upload it instead: you can upload the installer you downloaded and get the scan of exactly those bytes.
- **It keeps to itself.** No telemetry, no ads, no account. The only thing the player asks the internet for on its own is the version file of the latest release on GitHub, once a day, to tell you an update is out.

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

## Support

OY Player is made by one developer in their spare time. Donations are not set up yet; until then, a star on GitHub, a bug report or an idea in the [issues](https://github.com/electronic-mars/OY/issues) is the best thanks.

## Third-party components

FFmpeg, libmpv, Qt and others are listed with their licences and sources in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
