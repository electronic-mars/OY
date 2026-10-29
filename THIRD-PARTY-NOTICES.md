# OY Player: third-party components

OY Player is distributed under the GNU GPL version 3; its text is in the file `LICENSE`.
The program includes components by other authors. Below is what they are, the licence each is distributed under, and where to get its source code.

| Component | Version in the build | Licence | Source code |
|---|---|---|---|
| FFmpeg: `ffmpeg.exe` and `ffprobe.exe`, the gyan.dev «essentials» build | 8.1.1 | GNU GPL version 3: built with `--enable-gpl --enable-version3`. The licence text is in `licenses/FFmpeg-LICENSE.txt` | https://github.com/FFmpeg/FFmpeg/commit/239f2c733d, build: https://www.gyan.dev/ffmpeg/builds/ |
| libmpv: `libmpv-2.dll`, the shinchiro build | v0.41.0-1104-geb0ee1031 | GNU GPL version 2 or later: the build includes GPL parts | https://github.com/mpv-player/mpv, build: https://github.com/shinchiro/mpv-winbuild-cmake |
| Qt 6 and PySide6 | 6.12.0 | GNU LGPL version 3 | https://code.qt.io/ and https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| python-mpv | 1.0.8 | GNU GPL version 2 or later, or LGPL version 2.1 or later | https://github.com/jaseg/python-mpv |
| Python | 3.14 | Python Software Foundation License | https://www.python.org/downloads/source/ |
| PyInstaller: the bootloader | 6.22.3 | GNU GPL version 2 with the bootloader exception | https://github.com/pyinstaller/pyinstaller |
| IBM Plex Mono: the font of the time scale, numbers and lengths (Regular and Medium, TTF unpacked from the WOFF files of the `@ibm/plex-mono` package) | 2.5.0 | SIL Open Font License 1.1. The licence text is in `_internal/oyplayer/fonts/LICENSE-IBMPlexMono.txt` | https://github.com/IBM/plex |
| Lucide: interface icons, 46 SVG files (the Eject icon is drawn on their grid) | 0.460.0 | ISC. The licence text is in `_internal/oyplayer/icons/LICENSE` | https://github.com/lucide-icons/lucide |

The Qt libraries are linked dynamically and can be replaced with your own builds of the same version: put them in the program's `_internal\PySide6` folder.

If any of these addresses stops working, the source code can be requested from the author of OY Player through Issues at https://github.com/electronic-mars/OY.
