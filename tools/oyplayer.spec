# PyInstaller: OY Player as a folder (onedir): dist\OYPlayer\OYPlayer.exe + _internal\.
# Built by tools\build.cmd. Carries libmpv and its own ffmpeg and ffprobe (the editor, file
# information and durations need them), so the installed player depends on nothing else.
import os
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
# the real programs, not chocolatey's shims (which only start them)
FFMPEG = Path(os.environ.get("OY_FFMPEG_DIR") or r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin")
for exe in ("ffmpeg.exe", "ffprobe.exe"):
    assert (FFMPEG / exe).stat().st_size > 1_000_000, f"{FFMPEG / exe} is not a full ffmpeg build"

# Qt Quick modules OY Player does not use: dropped from the QML plugins PyInstaller collects
UNUSED = ("QtWebEngine", "QtWebView", "QtWebChannel", "QtWebSockets", "Qt3D", "QtQuick3D", "QtCharts",
          "QtDataVisualization", "QtGraphs", "QtLocation", "QtPositioning", "QtMultimedia", "QtSensors",
          "QtTextToSpeech", "QtRemoteObjects", "QtScxml", "QtNfc", "QtBluetooth", "QtSerialPort",
          "QtQuick/VirtualKeyboard", "Qt5Compat", "QtQuick/Scene2D", "QtQuick/Scene3D", "QtQuick/Timeline", "QtQuick/Particles",
          "QtQuick/Controls/Fusion", "QtQuick/Controls/Imagine", "QtQuick/Controls/Material",
          "QtQuick/Controls/Universal", "QtQuick/Controls/FluentWinUI3", "QtQuick/Controls/Windows",
          "QtQuick/Pdf", "QtPdf", "QtSpatialAudio", "QtStateMachine", "QtInsightTracker", "QtQuickEffectMaker",
          "QtQuick/Effects", "QtQuick/Shapes/DesignHelpers", "QtCanvasPainter")

a = Analysis(
    [str(ROOT / "tools" / "oyplayer_main.py")],
    pathex=[str(SRC), str(ROOT / "tools")],
    binaries=[(str(ROOT / "vendor" / "mpv" / "libmpv-2.dll"), "."),
              (str(FFMPEG / "ffmpeg.exe"), "ffmpeg"), (str(FFMPEG / "ffprobe.exe"), "ffmpeg")],
    datas=[(str(SRC / "oyplayer" / "qml"), "oyplayer/qml"),
           (str(SRC / "oyplayer" / "icons"), "oyplayer/icons"),
           (str(SRC / "oyplayer" / "fonts"), "oyplayer/fonts"),
           (str(SRC / "oyplayer" / "skins"), "oyplayer/skins"),       # the sealed skins (skins.py)
           (str(SRC / "oyplayer" / "oyplayer.ico"), "oyplayer")],
    hiddenimports=["wincap"],          # the self-test's window capture (tools\wincap.py)
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtMultimedia", "PySide6.QtPdf"],
)


# ...and the Qt libraries only those plugins load (Qt6WebEngineCore alone is 194 MB)
UNUSED_DLLS = ("Qt6WebEngine", "Qt6WebView", "Qt6WebChannel", "Qt6WebSockets", "Qt63D", "Qt6Quick3D",
               "Qt6Charts", "Qt6DataVisualization", "Qt6Graphs", "Qt6Location", "Qt6Positioning",
               "Qt6Multimedia", "Qt6Sensors", "Qt6TextToSpeech", "Qt6RemoteObjects", "Qt6Scxml",
               "Qt6StateMachine", "Qt6VirtualKeyboard", "Qt6Pdf", "Qt6SpatialAudio", "Qt6QuickTimeline",
               "Qt6QuickParticles", "Qt6QuickEffects", "Qt6Nfc", "Qt6Bluetooth", "Qt6SerialPort",
               "Qt6QuickControls2Fusion", "Qt6QuickControls2Imagine", "Qt6QuickControls2Material",
               "Qt6QuickControls2Universal", "Qt6QuickControls2FluentWinUI3", "Qt6QuickControls2Windows",
               # loaded by nothing in the build (no DLL or pyd names it)
               "Qt6ShaderTools",
               # OpenSSL from whatever was on PATH (Git for Windows): Qt's network uses Schannel;
               # Python's own libssl-3.dll and libcrypto-3.dll stay
               "libcrypto-3-x64", "libssl-3-x64")
# Qt plugins and data nothing here uses: the QML debugger, Qt's translations (no Qt dialog is
# shown; the interface carries its own words, i18n.py), the Direct2D platform (the window is drawn
# with Direct3D 11 or OpenGL, video.py), the
# OpenSSL TLS backend, the virtual keyboard, picture formats other than PNG, JPEG, ICO, SVG
UNUSED_PATHS = ("PySide6/translations/", "plugins/qmltooling/", "plugins/platforms/qdirect2d",
                "plugins/tls/qopensslbackend", "plugins/platforminputcontexts/qtvirtualkeyboard",
                *(f"plugins/imageformats/q{f}." for f in ("gif", "icns", "pdf", "tga", "tiff", "wbmp", "webp")))


def used(entry):
    path = entry[0].replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    return (not any(f"qml/{n}" in path for n in UNUSED) and not name.startswith(UNUSED_DLLS)
            and not any(p in path for p in UNUSED_PATHS))


a.datas = [d for d in a.datas if used(d)]
a.binaries = [b for b in a.binaries if used(b)]

# The version resource: the file's properties, Task Manager and antivirus heuristics read it
# (an empty one counts against an unsigned program)
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "oyplayer" / "__init__.py").read_text()).group(1)
NUMS = (tuple(int(x) for x in VERSION.split(".")) + (0, 0, 0, 0))[:4]
STRINGS = {"CompanyName": "Oleksandr Kyrychenko", "FileDescription": "OY Player — video player",
           "FileVersion": VERSION, "InternalName": "OYPlayer", "LegalCopyright": "© Oleksandr Kyrychenko, GPL v3",
           "OriginalFilename": "OYPlayer.exe", "ProductName": "OY Player", "ProductVersion": VERSION}
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS),
    kids=[StringFileInfo([StringTable("041904B0", [StringStruct(k, v) for k, v in STRINGS.items()])]),
          VarFileInfo([VarStruct("Translation", [0x0419, 1200])])])

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OYPlayer", console=False,
          icon=str(SRC / "oyplayer" / "oyplayer.ico"), upx=False, version=version)
coll = COLLECT(exe, a.binaries, a.datas, name="OYPlayer", upx=False)
