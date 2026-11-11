# OY Player

A free video player for Windows 10 and 11 that also cuts and annotates.

**[Download](https://github.com/electronic-mars/OY/releases/latest)** · [Website](https://electronic-mars.github.io/#oy-player) · [Ways to say thanks](https://electronic-mars.github.io/#support)

![OY Player playing films: a file is dragged into the empty window and starts; seeking along the bar shows a frame of where you would land; a right-click on the speed button picks 2x; the timer is set to «In 30 minutes»; a right-click on the video opens Subtitles… and picks 日本語. The films behind are sped-up cuts of Tears of Steel and Big Buck Bunny](docs/demo/plays.gif)

<sub>Tears of Steel and Big Buck Bunny © Blender Foundation, [mango.blender.org](https://mango.blender.org/) and [peach.blender.org](https://peach.blender.org/), licensed under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).</sub>

> **Status:** stable release (see the latest version on the Releases page). The interface is in 39 languages (as Windows speaks, or chosen in the settings). See [CHANGELOG.md](CHANGELOG.md).

## What it does

- **Watch.** Local files and streams through libmpv, with hardware decoding. A frame of where you would land shows above the seek bar; **Ctrl+X** plays fast, **Q** shows the decoder and other technical details.
- **Series.** Open one episode and the next ones, named the same but for the number, line up after it in the playlist.
- **Skip the opening and credits.** Mark them once (**Alt+E** and **Shift+E** for the opening, **Shift+O** for the credits); from then on they are skipped in every file of that folder of about the same length.
- **Cut.** Press **Ctrl+E**, then **I** and **O** to cut off the start and the end, **X** to split, **Delete** to take a piece out. Saving copies the streams without re-encoding where it can. Pieces from several files make one video, and an upright phone video can sit in a 16:9 frame over a blurred copy of itself.
- **Draw.** A pencil, rectangles, circles, arrows, text and pictures over the video, in six inks and three widths. Each drawing has its own time on the timeline, and saving puts them into the clip.
- **A key for every command**, and any of them can be changed in Settings › Controls › Keys.
- **39 languages.** In Arabic, Persian and Hebrew the window mirrors.
- **No ads, no telemetry, no account.** Once a day it looks for a new version and installs it only when you press «Update and restart». Licensed under the [GNU GPL v3](LICENSE).

| A free video player for Windows that also cuts and annotates | Plays nearly any format, with no ads and no account |
|---|---|
| ![The player paused on Ice Moon Crash: two astronauts run from an explosion on an icy moon, Saturn in the sky, the seek bar and controls below](docs/screenshots/crash.webp) | ![The player paused on Forest Goddess: a woman crowned with antlers leaps at an orc in a forest of giant mushrooms](docs/screenshots/goddess.webp) |
| **Cut the clip and draw over it: a circle, an arrow and text, each with its own time** | **Take a still, ring it, point at it, write on it, then copy or save** |
| ![The editor (Ctrl+E) on a frame of Tears of Steel: a yellow ellipse around a robot leaping out of smoke, a red arrow and the caption «Incoming!», each on its own track of the timeline below](docs/screenshots/editor.webp) | ![A still of Tears of Steel in the screenshot editor: a red circle around the robot, a white arrow and the caption «Behind you!», with Copy, Save and Close](docs/screenshots/shot-editor.webp) |
| **Pause, close the player, or put the computer to sleep or shut it down: after this file, when the list ends, or in 15 minutes to 2 hours** | **Pick the audio track or load one from a file, even out the volume, choose the device, move the sound earlier or later, change the pitch** |
| ![The timer menu over a frame of Tears of Steel: what to do (pause, close the player, put the computer to sleep, shut it down) and when (after this file, when the list ends, in 15 minutes up to 2 hours)](docs/screenshots/schedule.webp) | ![The sound menu over a frame of Tears of Steel: the audio track and loading one from a file, normalization, EBU R128, compressor and speech leveler, the output device, sound earlier or later by 0.1 s, pitch up and down](docs/screenshots/sound.webp) |
| **Open one episode, the next ones line up** | **Draw on the video, each drawing with its own time** |
| ![The player with the playlist open: three episodes of a mini-series, each with a frame, its number and its length, the first one playing](docs/screenshots/series-playlist.webp) | ![The editor on a cartoon of Mars and Saturn: an orange box around two astronauts, an arrow and the yellow caption «Next stop: Saturn», each with its own time on the timeline](docs/screenshots/draw.webp) |

![Editing a cartoon of Mars and Saturn: Ctrl+E opens the editor, I cuts off the start, the playhead is scrolled back and forth along the timeline, O cuts off the end, then a yellow circle, a red arrow and the white caption «Next stop: Saturn» are drawn over the picture, each on its own track, and the clip is saved](docs/demo/edit.gif)

![Screenshots of a frame: in Tears of Steel a frame is taken, an orange circle, a yellow arrow and the caption «Target locked» are drawn on it and it is saved and closed; the next file opens, and a frame of Big Buck Bunny gets a red box and the caption «Thumbnail: this one»](docs/demo/shot.gif)

<sub>Tears of Steel and Big Buck Bunny © Blender Foundation, [mango.blender.org](https://mango.blender.org/) and [peach.blender.org](https://peach.blender.org/), licensed under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).</sub>

**[Everything it does, with the key for each →](FEATURES.md)**

## Download

Installers are attached to the [GitHub releases](https://github.com/electronic-mars/OY/releases). The installer is per-user and needs no administrator rights. It is not code-signed yet, so Windows SmartScreen will ask for confirmation on first start. After that the player updates itself: when a new version is out, About › Update and restart installs it.

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

## Ways to say thanks

OY Player is free and made by one developer in their spare time. If it saves you time, there are a few ways to help it grow:

**[Ways to say thanks →](https://electronic-mars.github.io/#support)**

A star on GitHub, a bug report or an idea in the [issues](https://github.com/electronic-mars/OY/issues) is thanks too.

## Third-party components

FFmpeg, libmpv, Qt and others are listed with their licences and sources in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
