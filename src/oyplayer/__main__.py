"""OY Player entry point.  python -m oyplayer [file] | --selftest <media> <outdir>"""
import locale
import logging
import os
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]
if getattr(sys, "frozen", False):
    # the built program carries libmpv beside its libraries and its own ffmpeg and ffprobe
    BASE = Path(sys._MEIPASS)
    os.environ["PATH"] = os.pathsep.join([str(BASE), str(BASE / "ffmpeg"), os.environ["PATH"]])
else:
    os.environ["PATH"] = str(ROOT / "vendor" / "mpv") + os.pathsep + os.environ["PATH"]
# Python slots run inside Qt's render pass; with the threaded render loop the render
# thread and the GUI thread deadlock on the GIL (measured: a silent hang).
os.environ["QSG_RENDER_LOOP"] = "basic"
# Direct3D 11 (video.py): Qt waits on DXGI's frame latency object before each frame, and across
# a full-screen switch it is not signalled: Qt sat out its 1 s timeout (2 of 4 switches, measured)
os.environ["QT_D3D_MAX_FRAME_LATENCY"] = "0"
# The flip-model swap chain leaves a grown window's old frame unscaled in its corner on black
# until the next present; the legacy blit model does it less (curtain.py covers the rest)
os.environ["QT_D3D_NO_FLIP"] = "1"
# Menus and popups are drawn entirely by us; the Basic style is the one that lets them be.
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

from PySide6.QtCore import Property, QObject, QStandardPaths, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402   (the tray icon is a widget)

from . import __version__  # noqa: E402
from .i18n import lang  # noqa: E402
from .log import flush_writes, home, log, setup  # noqa: E402


class AppInfo(QObject):
    """Small facts QML needs that are not player state."""

    changed = Signal()

    def __init__(self, settings, selftest=False):
        super().__init__()
        self._settings = settings
        self._selftest = selftest
        settings.changed.connect(lambda _k: self.changed.emit())

    @Property(bool, constant=True)
    def selftest(self):
        # A self-test window must not take focus: it would swallow whatever the user is
        # typing elsewhere at that moment (observed: a stray "M" muted a run).
        return self._selftest

    @Property(str, notify=changed)
    def screenshotDir(self):
        pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        return (os.environ.get("OY_SHOTS") or self._settings["shotDir"]
                or str(Path(pics) / "OY Player"))

    @Property(bool, constant=True)
    def systemLight(self):
        """Windows app theme: AppsUseLightTheme = 1 means light."""
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
        except OSError:
            return False

    @Slot(QObject, result="QVariantList")
    def workArea(self, window):
        """Work area (logical px) of the monitor the window is on. QML's Screen.desktop-
        Available* is the whole virtual desktop: a fit to it spilled onto other monitors."""
        # The scale factor comes from the same screen: QML's Screen.devicePixelRatio
        # reported the primary monitor's 1.25 for a window on a 1.0 monitor (measured).
        s = window.screen()
        g = s.availableGeometry()
        return [g.x(), g.y(), g.width(), g.height(), s.devicePixelRatio()]

    @Slot()
    def openScreenshotDir(self):
        Path(self.screenshotDir).mkdir(parents=True, exist_ok=True)
        os.startfile(self.screenshotDir)

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def homeDir(self):
        return str(home())

    # ---- file types: only ever on the person's click in the settings
    @Property(bool, notify=changed)
    def fileTypes(self):
        from . import assoc
        return assoc.registered()

    @Slot(bool, bool)
    def registerFileTypes(self, audio, openWindows=True):
        from . import assoc
        assoc.register(notify=not self._selftest, audio=audio)
        self.changed.emit()
        if not openWindows:
            return
        if self._selftest:
            log.info("self-test: Windows' default apps page not opened")
        else:
            assoc.open_default_apps()

    @Slot()
    def unregisterFileTypes(self):
        from . import assoc
        assoc.unregister(notify=not self._selftest)
        self.changed.emit()


def place_on_screen(app, win, number):
    """Centre the window on Windows display N (\\\\.\\DISPLAYN); self-tests run on display 3
    so they stay off the monitors the owner works on. Unknown N: leave it where it is."""
    if not number:
        return
    screen = next((s for s in app.screens() if s.name().endswith(f"DISPLAY{number}")), None)
    if screen is None:
        log.info("screen DISPLAY%s not found, staying on the primary", number)
        return
    g = screen.availableGeometry()
    win.setScreen(screen)
    win.setPosition(g.x() + (g.width() - win.width()) // 2, g.y() + (g.height() - win.height()) // 2)
    log.info("placed on %s", screen.name())


def main(argv):
    if argv[1:2] == ["--unregister"]:      # the uninstaller takes the file types back
        from .assoc import unregister
        unregister()
        return 0
    # the showcase (master screenshots) runs under the self-test's rules: monitor 3, silent, no focus
    showcase = len(argv) >= 4 and argv[1] == "--showcase"
    selftest = len(argv) >= 4 and argv[1] == "--selftest" or showcase
    app = QApplication(argv)
    app.setApplicationName("OY Player")
    app.setOrganizationName("oyplayer")

    from . import instance
    from .settings import Settings, apply
    settings = Settings()
    files = [] if selftest else [a if "://" in a else str(Path(a).resolve()) for a in argv[1:]]
    # One player: a second start hands its files to the first one and leaves, before
    # it opens the log the first one is writing
    if not selftest and settings["singleInstance"] and instance.send(files):
        os._exit(0)
    log_path = setup()
    locale.setlocale(locale.LC_NUMERIC, "C")   # mpv parses numbers with the C locale
    app.setWindowIcon(QIcon(str(PKG / "oyplayer.ico")))

    import mpv
    from .actions import Actions
    from .autoskip import AutoSkip
    from .editor import Editor
    from .hotkeys import MediaKeys
    from .snap import SnapKey
    from .player import Player
    from .playlist import Playlist
    from .preview import Preview
    from .radio import Radio
    from .scheduler import Scheduler
    from .tray import Tray
    from .curtain import Curtain
    from .video import D3DUnderlay, VideoUnderlay, dx_interop
    # OY_VIDEO=gl: the OpenGL window, as on a machine without the interop (self-test comparisons)
    d3d = os.environ.get("OY_VIDEO") != "gl" and dx_interop()
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11 if d3d
                                else QSGRendererInterface.GraphicsApi.OpenGL)

    def mpv_log(level, component, text):
        if level in ("fatal", "error", "warn"):
            log.warning("mpv %s %s: %s", level, component, text.strip())

    # sub_use_margins=no: with video-margin-ratio set, mpv otherwise places text subtitles
    # at the window's edges — under our title bar and control panel (measured: invisible).
    # A screenshot must look as the frame does in the window (measured on SMPTE bars against
    # ffmpeg's BT.709 decode): mpv's own colour tags (cICP with the BT.709 curve, gAMA, cHRM)
    # make colour-managed viewers show the file darker (Chromium: 40 % grey 99 -> 90), and
    # zimg converts full-range video lighter than the window shows it (grey 100 -> 108,
    # black -> 0,7,0); swscale matches the window to a unit.
    core = mpv.MPV(vo="libmpv", hwdec="auto-safe", keep_open="yes", idle="yes",
                   osc="no", input_default_bindings="no", input_vo_keyboard="no",
                   sub_use_margins="no", volume_max=200,
                   screenshot_tag_colorspace="no", sws_allow_zimg="no",
                   log_handler=mpv_log, loglevel="warn")
    if selftest:
        core["ao"] = "null"   # test clips carry a test tone; a self-test must stay silent
    player = Player(core)
    playlist = Playlist(player)
    editor = Editor(player)
    autoskip = AutoSkip(player)
    radio = Radio(player)
    # a self-test only records the power actions it triggers
    scheduler = Scheduler(player, playlist, dry_run=selftest)
    actions = Actions(player, playlist, editor, autoskip, radio)
    preview = Preview()
    info = AppInfo(settings, selftest=selftest)
    server = instance.Server()
    from .updater import Updater
    updater = Updater(busy=lambda: editor.exporting)   # quitting would cut a save short

    def on_setting(key):
        apply(settings, key, core, actions)
        if key in (None, "lang"):
            lang.set(settings["lang"])
        if key in (None, "audioMode"):
            player.setAudioMode(settings["audioMode"], quiet=key is None)
        player.auto_resume = settings["resume"]
        player.remember_setup = settings["fileMemory"]
        if key is None:
            player.general_volume = float(settings["volume"])
        player.hwdec_enabled = settings["hwdec"]
        playlist.adds = settings["openAdds"]
        if key in (None, "exportCodec"):
            editor.setCodec(settings["exportCodec"])
        playlist.series = settings["series"]
        autoskip.setEnabled(settings["autoskip"])
        player.history.enabled = settings["history"]
        scheduler.list_end = settings["onListEnd"]
        if key in (None, "radioDir", "radioRecDir"):
            radio.folder, radio.rec_folder = settings["radioDir"], settings["radioRecDir"]
            radio.changed.emit()
        updater.setAuto(settings["updateCheck"] and not selftest)
    on_setting(None)
    settings.changed.connect(on_setting)
    autoskip.toggled.connect(lambda on: settings.set("autoskip", on))
    # texts made in Python are made again in the new language
    for texts in (player.changed, editor.changed, scheduler.changed, radio.changed, player.history.changed,
                  actions.keysChanged):
        lang.changed.connect(texts)

    # Text through Windows' own hinting, as other programs draw it: Qt's default (distance
    # fields) keeps the letters' outlines soft at 11-13 px
    QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.NativeTextRendering)
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("player", player)
    ctx.setContextProperty("actions", actions)
    ctx.setContextProperty("playlist", playlist)
    ctx.setContextProperty("app", info)
    ctx.setContextProperty("settings", settings)
    ctx.setContextProperty("editor", editor)
    ctx.setContextProperty("preview", preview)
    ctx.setContextProperty("autoskip", autoskip)
    ctx.setContextProperty("history", player.history)
    ctx.setContextProperty("radio", radio)
    ctx.setContextProperty("scheduler", scheduler)
    ctx.setContextProperty("i18n", lang)
    ctx.setContextProperty("updater", updater)
    engine.addImageProvider("preview", preview.provider)
    from PySide6.QtGui import QFontDatabase
    for font in (PKG / "fonts").glob("*.ttf"):      # IBM Plex Mono: the scale, numbers and lengths
        QFontDatabase.addApplicationFont(str(font))
    from .icons import IconProvider
    icons = IconProvider()          # held here: the engine does not keep the Python object alive
    engine.addImageProvider("icon", icons)
    engine.load(QUrl.fromLocalFile(str(PKG / "qml" / "Main.qml")))
    if not engine.rootObjects():
        log.error("QML failed to load")
        return 1
    win = engine.rootObjects()[0]
    actions.window = win
    win.installEventFilter(actions)
    place_on_screen(app, win, os.environ.get("OY_SCREEN") or ("3" if info.selftest else ""))
    win.show()
    log.info("video through %s", "Direct3D 11" if d3d else "OpenGL")
    win.setProperty("videoD3D", d3d)
    underlay = (D3DUnderlay if d3d else VideoUnderlay)(win, core)
    curtain = Curtain(win)
    ctx.setContextProperty("curtain", curtain)
    tray = Tray(win, actions, player, app.windowIcon())
    keys = MediaKeys(win, actions)
    snap = SnapKey(win, cover_fix=not d3d)  # noqa: F841 - the filter lives as long as the window

    def on_window_setting(key):
        if key in (None, "tray"):
            tray.setMode(settings["tray"])
        if key in (None, "globalMedia"):
            keys.setGlobal(settings["globalMedia"])
    on_window_setting(None)
    settings.changed.connect(on_window_setting)
    # "close the player" from the scheduler or the setting "onListEnd"
    scheduler.closeRequested.connect(win.close)

    def handed_over(more):
        # a second start: its files play here, and the window comes forward (from the tray too)
        if more:
            playlist.add(more, True)
        tray.showWindow()
    server.filesReceived.connect(handed_over)
    if not selftest:
        updater.readyToInstall.connect(app.quit)     # the installer starts on the way out
    log.info("started, log %s", log_path)

    test = None
    if showcase:
        from .showcase import Showcase
        test = Showcase(app, win, player, playlist, actions, argv[2:], settings, editor, preview)
        underlay.ready.connect(test.start)
    elif selftest:
        from .selftest import SelfTest
        test = SelfTest(app, win, player, playlist, actions, argv[2:], settings, editor, preview,
                        m8=dict(autoskip=autoskip, radio=radio, scheduler=scheduler, tray=tray,
                                keys=keys, info=info, history=player.history, updater=updater))
        underlay.ready.connect(test.start)
    elif files:
        underlay.ready.connect(lambda: playlist.add(files, True))

    code = app.exec()
    tray.icon.hide()          # leaving through os._exit would leave the icon behind
    keys.setGlobal(False)
    radio.stopRecording()     # the recording ends with what has arrived
    editor.shutdown()         # an unfinished save is stopped and its partial file removed
    preview.shutdown()
    playlist.flush()          # a change from the last half second is still on its timer
    player.saveSession()      # where the current file was left, its tracks and volume
    settings.set("volume", round(player.general_volume))
    flush_writes()            # settings, positions, history and the list are on the disk
    # mpv's render context must be freed (on the render thread, as the window goes)
    # before mpv itself is terminated.
    del engine
    core.terminate()
    if updater.installer:
        # everything is written and closed: the installer may replace the player's files
        # and start it again
        from . import update
        update.install(updater.installer)
    result = test.result if test else code
    log.info("exit %s", result)
    logging.shutdown()
    # Everything that matters is closed and written. Letting the interpreter tear down
    # the remaining Qt wrappers in arbitrary order crashed the process after a clean
    # exit (measured: segfault after "exit 0"); leave without that teardown.
    os._exit(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
