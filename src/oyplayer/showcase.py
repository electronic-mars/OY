"""Showcase: the master screenshots of the player, for the site, the store and design work.

Run as the self-test is run (tools\\selftest.cmd), after creating the empty file
tests\\next-run-showcase. No checks: it paints a few calm landscapes, makes clips of them
with ffmpeg (once, kept in tests\\media\\showcase), stages the main states of the window on
them and captures each into tests\\out\\showcase. Same window rules as the self-test:
monitor 3, silent, no focus, transparent for the mouse.
"""
import random
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtTest import QTest

from .log import log
from .selftest import SelfTest

W, H = 3840, 2160          # painted at twice the clip's size: the slow camera move stays smooth
# scene: sky top -> horizon, glow, ridges far -> near, star count, aurora
SCENES = {
    "dusk": dict(sky=("#0B1030", "#3A2E6E", "#E8774A"), glow="#FFB26B", ridges=("#6F5C9A", "#4B3F78", "#2F2856", "#1D1A3A", "#100E22"),
                 stars=160, aurora=False, amp=0.16),
    "fjord": dict(sky=("#02060F", "#082233", "#14504F"), glow="#5FE3B0", ridges=("#1E4752", "#15343F", "#0D242E", "#07161D", "#030B10"),
                  stars=260, aurora=True, amp=0.2),
    "desert": dict(sky=("#3A6EA5", "#9FC3DA", "#F6D9A8"), glow="#FFF1C9", ridges=("#D9A86C", "#C98E52", "#B0733C", "#8E5A2E", "#6A4122"),
                   stars=0, aurora=False, amp=0.06),
}
# name -> (scene, seconds, full size): only the first one is played on screen
CLIPS = [("Mountain Dusk.mkv", "dusk", 40, True), ("Northern Fjord — Aurora.mkv", "fjord", 2 * 60 + 14, False),
         ("Desert Morning.mp4", "desert", 4 * 60 + 32, False), ("City Lights Timelapse.mkv", "fjord", 3 * 60 + 5, False),
         ("Family Trip 2026.mp4", "desert", 12 * 60 + 40, False), ("Studio Session.mkv", "dusk", 48 * 60 + 5, False)]
SUBTITLE = "The light stayed on the ridge a little longer."


def ridge(rng, n, base, amp):
    """A mountain line: midpoint displacement over n segments, heights as fractions of H."""
    pts = [base + rng.uniform(-amp, amp), base + rng.uniform(-amp, amp)]
    spread = amp
    while len(pts) < n:
        out = []
        for a, b in zip(pts, pts[1:]):
            out += [a, (a + b) / 2 + rng.uniform(-spread, spread)]
        pts = out + [pts[-1]]
        spread *= 0.55
    return pts


def paint(scene, path):
    s, rng = SCENES[scene], random.Random(scene)
    img = QImage(W, H, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    sky = QLinearGradient(0, 0, 0, H * 0.72)
    for at, c in zip((0, 0.55, 1), s["sky"]):
        sky.setColorAt(at, QColor(c))
    p.fillRect(0, 0, W, H, sky)
    for _ in range(s["stars"]):
        c = QColor("#FFFFFF")
        c.setAlphaF(rng.uniform(0.25, 0.9))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        r = rng.uniform(1.2, 3.6)
        p.drawEllipse(QPointF(rng.uniform(0, W), H * 0.55 * rng.random() ** 1.6), r, r)
    if s["aurora"]:
        for k in range(26):
            band = QPainterPath()
            y0 = H * (0.18 + 0.012 * k)
            band.moveTo(-50, y0)
            for i in range(1, 9):
                x = W * i / 8
                band.cubicTo(x - W / 16, y0 + rng.uniform(-180, 180), x - W / 32, y0 + rng.uniform(-180, 180), x, y0 + rng.uniform(-120, 120))
            c = QColor("#58F5B0" if k % 3 else "#9B7BFF")
            c.setAlphaF(0.035)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(c, 2 * (60 - k), Qt.SolidLine, Qt.RoundCap))
            p.drawPath(band)
    glow = QRadialGradient(W * 0.62, H * 0.62, W * 0.42)
    g = QColor(s["glow"])
    g.setAlphaF(0.55)
    glow.setColorAt(0, g)
    g.setAlphaF(0)
    glow.setColorAt(1, g)
    p.fillRect(0, 0, W, H, glow)
    for k, col in enumerate(s["ridges"]):
        heights = ridge(rng, 129, 0.5 + 0.09 * k, s["amp"] * (1 - 0.12 * k))
        shape = QPainterPath(QPointF(0, H))
        for i, h in enumerate(heights):
            shape.lineTo(W * i / (len(heights) - 1), H * h)
        shape.lineTo(W, H)
        shape.closeSubpath()
        fill = QLinearGradient(0, H * 0.4, 0, H)
        fill.setColorAt(0, QColor(col))
        fill.setColorAt(1, QColor(col).darker(140))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill))
        p.drawPath(shape)
    p.end()
    img.save(str(path))


def make_media(folder):
    """The clips, made once: a painted frame with a slow camera move, silent sound."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, scene, secs, full in CLIPS:
        out = folder / name
        if out.exists():
            continue
        png = folder / f"{scene}.png"
        if not png.exists():
            paint(scene, png)
        if full:      # one picture in, the camera move makes every frame of it
            src = ["-i", str(png)]
            vf = (f"zoompan=z='1+0.00025*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                  f":d={secs * 25}:s=1920x1080:fps=25,format=yuv420p")
            size = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        else:
            src = ["-loop", "1", "-framerate", "1", "-i", str(png)]
            vf, size = "scale=320:-2,format=yuv420p", ["-c:v", "libx264", "-preset", "ultrafast"]
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + src + ["-f", "lavfi", "-i",
                        "anullsrc=r=48000:cl=stereo", "-t", str(secs), "-vf", vf] + size
                       + ["-c:a", "aac", "-b:a", "32k", "-shortest", str(out)],
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        log.info("showcase clip %s", out.name)
    srt = folder / (Path(CLIPS[0][0]).stem + ".srt")
    if not srt.exists():
        srt.write_text(f"1\n00:00:02,000 --> 00:00:38,000\n{SUBTITLE}\n", encoding="utf-8")


class Showcase(SelfTest):
    def __init__(self, app, win, player, playlist, actions, args, settings, editor, preview, m8=None):
        QObject.__init__(self)
        self.app, self.win, self.p, self.pl, self.a = app, win, player, playlist, actions
        self.settings, self.ed, self.pv, self.m8, self.icy = settings, editor, preview, m8 or {}, None
        self.dir, self.out = Path(args[0]), Path(args[1]) / "showcase"
        self.out.mkdir(parents=True, exist_ok=True)
        self.failures, self.result, self.steps = [], 1, []

    def shot(self, name):
        super().shot(name)
        print(f"SHOWCASE shot {name}.png", flush=True)

    def park(self):
        """The pointer on the title's middle: no key, row or bar lights up under it."""
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, 16))

    def place_window(self):
        """1600 x 900 in the middle of its monitor, the same for every capture."""
        self.win.setProperty("width", 1600)
        self.win.setProperty("height", 900)
        g = self.win.screen().availableGeometry()
        self.win.setPosition(g.x() + (g.width() - 1600) // 2, g.y() + (g.height() - 900) // 2)

    def start(self):
        QTimer.singleShot(240000, self._watchdog)
        make_media(self.dir)
        for k, v in (("lang", "en"), ("subLang", "eng,en"), ("fitWindow", False), ("series", False),
                     ("autoskip", False), ("theme", "dark"), ("accent", "#F26A21")):
            self.settings.set(k, v)
        self.place_window()

        def key(name, mods=Qt.NoModifier):
            return lambda: self.key(name, mods)

        def seek(t):
            return lambda: self.p.seek(t)

        def ui(name):
            return lambda: self.click(name)

        def shot(name):
            return lambda: (self.park(), QTimer.singleShot(300, lambda: self.shot(name)))

        def subs(on):
            # subtitles in the plain shots; where a card or the editor lies over the picture they would be cut
            return lambda: setattr(self.p.mpv, "sub_visibility", on)

        files = [str(self.dir / c[0]) for c in CLIPS]
        self.steps = [
            (0, lambda: (self.pl.clear(), self.pl.add(files, True))), (3000, lambda: setattr(self.p.mpv, "pause", True)),
            (0, lambda: self.p.setVolume(72)),          # as on the concept: the volume cap stands inside its groove
            (0, seek(12.0)), (900, shot("01-hero")),
            (600, lambda: self.show_list(True)), (900, shot("02-playlist")),
            (600, lambda: self.show_list(False)), (600, lambda: QTest.mouseMove(self.win, self.rail_pt(0.66))),
            (1200, lambda: self.shot("03-seek-preview")),
            # the editor: two fragments, three drawings on the first one, yellow while editing
            (0, self.park), (0, subs(False)), (300, key("E", Qt.ControlModifier)), (600, seek(4.0)), (500, key("I")), (0, seek(16.0)),
            (500, key("O")), (0, seek(21.0)), (500, key("I")), (0, seek(29.0)), (500, key("O")),
            # as on the concept: a rectangle round the summit, an arrow at it, the words above
            (0, seek(9.0)), (900, ui("drawRect")), (300, lambda: self.drag([(0.36, 0.37), (0.51, 0.45), (0.66, 0.53)])),
            (400, ui("drawArrow")), (300, lambda: self.drag([(0.74, 0.24), (0.71, 0.3), (0.67, 0.36)])),
            (400, ui("drawText")), (0, lambda: self.ed.selectNote(-1)), (300, lambda: self.click_item(self.find_item("ink1"))),
            (300, lambda: self.click_layer(0.6, 0.12)),
            (400, lambda: self.type_text("Summit at dusk")),
            (300, lambda: self.type_text("\r", Qt.Key_Return)), (400, ui("drawSelect")),
            # their times as on the concept: 6-14, 8-16, 10-20
            (300, lambda: [self.ed.setNoteRange(i, a, b) for i, (a, b) in enumerate(((6, 14), (8, 16), (10, 20)))]),
            (300, lambda: (self.ed.selectNote(0), self.p.seek(12.0))),
            (900, shot("04-editor")),
            (600, self.ed.close), (600, key("F10")), (800, lambda: self.click_item(self.find_item("nav1"))),
            (900, shot("05-settings-window")), (600, key("Esc")),
            (0, subs(True)), (600, lambda: (self.settings.set("accent", "#3C9D5B"), self.show_list(True))),
            (900, shot("06-accent-green")),
            (600, lambda: (self.settings.set("accent", "#F26A21"), self.settings.set("theme", "light"))),
            (1000, shot("07-cream")),
            (600, lambda: (self.settings.set("theme", "dark"), self.show_list(False))), (0, subs(False)), (700, ui("keyVideo")),
            (900, shot("08-picture-card")), (600, key("Esc")),
            (600, key("Enter")), (1500, lambda: QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() - 40))),
            (700, lambda: self.shot("09-fullscreen")), (600, key("Esc")),
            (0, subs(True)), (1200, lambda: (self.place_window(), self.settings.set("lang", "uk"), self.show_list(True))),
            (1200, shot("10-ukrainian")),
            (600, lambda: self.settings.set("lang", "en")), (300, self.finish),
        ]
        self._next()

    def finish(self):
        self.result = 1 if self.failures else 0
        print(f"SHOWCASE DONE {len(list(self.out.glob('*.png')))} shots in {self.out}, failed steps {self.failures}",
              flush=True)
        log.info("SHOWCASE DONE")
        self.win.close()


class Features(Showcase):
    """FEATURES.md's pictures: one capture per feature group, into tests\\out\\showcase. Run like
    the showcase, with the empty file tests\\next-run-features instead. The run's home, its
    screenshots and the clips are under the run's own folder in LOCALAPPDATA (selftest.cmd), so no
    path of the working copy shows in a list or the settings."""

    def rclick(self, name=None, pt=None):
        if pt is None:
            item = self.find_item(name)
            c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            pt = QPoint(int(c.x()), int(c.y()))
        QTest.mouseClick(self.win, Qt.RightButton, Qt.NoModifier, pt)

    def esc(self):
        self.key("Esc")

    def radio_prep(self):
        """Three stations in the stations folder; the first is a tone served here the way a
        station serves its stream, so it can be on the air."""
        from .radio import write_lau
        from .selftest import start_icy
        mp3 = self.out / "radio_src.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                        "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)], timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        self.icy = start_icy(mp3.read_bytes())
        rdir = Path(self.m8["radio"].dir)
        rdir.mkdir(parents=True, exist_ok=True)
        self.station = write_lau(rdir, "Test Tone Radio", f"http://127.0.0.1:{self.icy.server_port}/stream")
        write_lau(rdir, "Second Test Stream", "http://127.0.0.1:9/second")
        write_lau(rdir, "Third Test Stream", "http://127.0.0.1:9/third")
        self.m8["radio"].changed.emit()

    def phone_prep(self):
        """An upright clip, as a phone films: for the editor's 16:9 frame."""
        self.phone = str(self.dir / "Phone Video.mp4")
        if not Path(self.phone).exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "25", "-i", str(self.dir / "dusk.png"),
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "8",
                            "-vf", "crop=ih*9/16:ih,scale=1080:1920,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                            "-c:a", "aac", "-shortest", self.phone], timeout=120, creationflags=subprocess.CREATE_NO_WINDOW, check=True)

    def hide_rows(self, name, x0, y0, x1, y1):
        """This computer's sound devices are named in the menu and the settings: pixelated in the picture."""
        path = str(self.out / f"{name}.png")
        img = QImage(path)
        box = img.copy(x0, y0, x1 - x0, y1 - y0)
        small = box.scaled(max(1, box.width() // 12), max(1, box.height() // 12))
        p = QPainter(img)
        p.drawImage(x0, y0, small.scaled(box.width(), box.height()))
        p.end()
        img.save(path)

    def history_prep(self, files):
        h = self.m8["history"]
        for f, (_, _, secs, _) in reversed(list(zip(files, CLIPS))):
            h.note(f, secs * 0.6, secs)

    def scroll(self, y):
        flick = self.find_item("settingsFlick")
        flick.setProperty("contentY", max(0.0, min(y, flick.property("contentHeight") - flick.height())))

    def draw_shot(self):
        self.click_sw("drawRect")
        self.drag_sw([(0.36, 0.37), (0.51, 0.45), (0.66, 0.53)])
        self.click_sw("drawArrow")
        self.drag_sw([(0.80, 0.18), (0.74, 0.28), (0.67, 0.36)])
        self.click_sw("drawText")
        self.drag_sw([(0.56, 0.14)])
        self.type_sw("Summit")
        self.click_sw("drawSelect")
        sw = self.shot_window()
        QTest.mouseMove(sw, QPoint(sw.width() // 2, 12))

    def start(self):
        QTimer.singleShot(420000, self._watchdog)
        make_media(self.dir)
        for k, v in (("lang", "en"), ("subLang", "eng,en"), ("fitWindow", False), ("series", False),
                     ("autoskip", False), ("theme", "dark"), ("accent", "#F26A21")):
            self.settings.set(k, v)
        self.place_window()
        files = [str(self.dir / c[0]) for c in CLIPS]
        set_ = self.settings.set

        def run(name):
            return lambda: self.a.run(name)

        def shot(name):
            # captured 400 ms after the pointer is parked: the next step waits for it (below)
            f = lambda: (self.park(), QTimer.singleShot(400, lambda: self.shot(name)))
            f.is_shot = True
            return f

        def subs(on):
            return lambda: setattr(self.p.mpv, "sub_visibility", on)

        def section(n, name, y=0.0):
            return [(0, lambda: self.click_item(self.find_item(f"nav{n}"))), (300, lambda: self.scroll(y)),
                    (700, shot(name))]

        def tab(n):     # the list, history or radio page of the playlist panel
            return lambda: (self.find_item("playlistPanel").setProperty("tab", n),
                            self.win.setProperty("playlistShown", True))

        def again():    # the clips in the list again, paused on the same frame; the list shown, so its rows ask for their frames
            return [(0, tab(0)), (0, lambda: (self.pl.clear(), self.pl.add(files, True))),
                    (3000, lambda: setattr(self.p.mpv, "pause", True)), (0, lambda: self.p.seek(12.0))]

        self.steps_raw = [
            (0, lambda: (self.pl.clear(), self.pl.add(files, True))), (3000, lambda: setattr(self.p.mpv, "pause", True)),
            (0, lambda: self.p.setVolume(72)), (0, lambda: self.history_prep(files)), (0, self.radio_prep), (0, self.phone_prep),
            (0, lambda: self.p.seek(12.0)), (1200, shot("watch-dark")),
            (0, lambda: set_("theme", "light")), (1200, shot("watch-light")), (0, lambda: set_("theme", "dark")),
            (800, lambda: QTest.mouseMove(self.win, self.rail_pt(0.66))), (1200, lambda: self.shot("watch-seek-preview")),
            (0, self.park), (300, lambda: self.rclick(pt=QPoint(self.win.width() * 2 // 3, self.win.height() // 3))),
            (700, shot("menu-picture")), (0, self.esc),
            (400, lambda: self.rclick("keyFast")), (700, shot("menu-speed")), (0, self.esc),
            (400, run("subtitle_menu")), (700, shot("menu-subtitles")), (0, self.esc),
            (400, run("audio_menu")), (700, shot("menu-sound")), (0, lambda: self.hide_rows("menu-sound", 228, 578, 500, 640)),
            (0, self.esc),
            (400, lambda: self.rclick(pt=self.rail_pt(0.5))), (700, shot("menu-skip")), (0, self.esc),
            (400, run("scheduler")), (700, shot("menu-scheduler")), (0, self.esc),
            (0, subs(False)), (400, run("video_panel")), (900, shot("card-picture")), (0, self.esc),
            (400, run("file_info")), (1500, shot("card-file-info")), (0, self.esc),
            (400, run("tech_osd")), (900, shot("watch-tech-osd")), (0, run("tech_osd")), (0, subs(True)),
            (400, lambda: self.p.seek(8.0)), (500, run("ab_loop")), (0, lambda: self.p.seek(20.0)), (500, run("ab_loop")),
            (0, lambda: self.p.seek(12.0)), (800, shot("watch-ab-repeat")), (0, run("ab_loop")),
            (600, tab(0)), (2500, shot("list-playlist")),
            (0, tab(1)), (1500, shot("list-history")),
            (0, tab(2)), (1000, lambda: self.pl.add([str(self.station)], True)), (6000, shot("list-radio")),
        ] + again() + [
            (0, tab(0)), (0, lambda: self.win.setProperty("playlistShown", False)),
            (500, lambda: self.pl.add(["https://www.youtube.com/watch?v=aqz-KE-bpKQ"], True)),
            (1200, shot("web-link-ask")), (0, lambda: self.click("webDismiss")),
            # the editor: the whole file, cut at 16 and 21 s, the middle piece taken out; three drawings
            (600, self.park), (0, subs(False)), (300, run("edit_mode")), (800, lambda: self.p.seek(16.0)),
            (600, run("cut_out")), (0, lambda: self.p.seek(21.0)), (600, run("cut_out")),
            (600, lambda: (self.ed.select(1), self.ed.removeSelected())),
            (0, lambda: self.p.seek(9.0)), (900, lambda: self.click("drawRect")),
            (300, lambda: self.drag([(0.36, 0.37), (0.51, 0.45), (0.66, 0.53)])),
            (400, lambda: self.click("drawArrow")), (300, lambda: self.drag([(0.74, 0.24), (0.71, 0.3), (0.67, 0.36)])),
            (400, lambda: self.click("drawText")), (0, lambda: self.ed.selectNote(-1)),
            (300, lambda: self.click_item(self.find_item("ink1"))), (300, lambda: self.click_layer(0.6, 0.12)),
            (400, lambda: self.type_text("Summit at dusk")), (300, lambda: self.type_text("\r", Qt.Key_Return)),
            (400, lambda: self.click("drawSelect")),
            (300, lambda: [self.ed.setNoteRange(i, a, b) for i, (a, b) in enumerate(((6, 14), (8, 16), (10, 20)))]),
            (300, lambda: (self.ed.selectNote(0), self.p.seek(12.0))), (1200, shot("editor-dark")),
            (0, lambda: set_("theme", "light")), (1200, shot("editor-light")), (0, lambda: set_("theme", "dark")),
            # a phone's upright video in a 16:9 frame over a blurred copy of itself
            (600, self.ed.close), (300, lambda: self.pl.add([self.phone], True)), (2500, lambda: setattr(self.p.mpv, "pause", True)),
            (0, lambda: self.p.seek(3.0)), (300, run("edit_mode")), (800, lambda: self.ed.setFrame("blur")),
            (1500, lambda: self.p.seek(3.0)), (1500, shot("editor-frame-16x9")),
            (0, self.ed.undo), (600, self.ed.close),
        ] + again() + [
            (0, lambda: self.win.setProperty("playlistShown", False)), (0, subs(True)),
            # the screenshot editor, then a screenshot saved to the folder
            (600, lambda: set_("shotMode", "edit")), (300, run("screenshot")), (1200, self.draw_shot),
            (800, lambda: self.shot_sw("screenshot-editor")), (0, lambda: self.click_sw("shotClose")),
            (600, lambda: set_("shotMode", "file")), (300, run("screenshot")), (900, lambda: self.shot("screenshot-saved")),
            # settings, section by section
            (3000, subs(False)), (500, run("settings")),
        ] + section(0, "settings-playback") + section(1, "settings-general") \
            + section(1, "settings-general-windows", 520) + section(2, "settings-appearance") \
            + section(2, "settings-appearance-skins", 520) + section(3, "settings-sound") + [(0, lambda: self.hide_rows("settings-sound", 650, 322, 900, 382))] \
            + section(4, "settings-subtitles") + section(5, "settings-controls") \
            + section(5, "settings-controls-keys", 760) + section(6, "settings-screenshots-editing") \
            + section(7, "settings-about") + [
            (0, lambda: set_("theme", "light")), (0, lambda: self.click_item(self.find_item("nav2"))),
            (900, shot("settings-appearance-light")), (0, lambda: set_("theme", "dark")), (300, self.esc), (0, subs(True)),
            # skins and the accent, with the list open
            # a new skin or language rebuilds the panel: the list is filled again so its rows show their frames
            (600, lambda: set_("skin", "classic")), (800, lambda: None), *again(), (1500, shot("skin-classic")),
            (0, lambda: set_("skin", "studio")), (800, lambda: None), *again(), (1500, shot("skin-studio")),
            (0, lambda: set_("skin", "default")), (800, lambda: None), *again(), (0, lambda: set_("accent", "#3C9D5B")), (1500, shot("accent-green")),
            (0, lambda: set_("accent", "#F26A21")),
            # languages: one written right to left, one east Asian
            (600, lambda: set_("lang", "ar")), (800, lambda: None), *again(), (1500, shot("lang-arabic")),
            (0, lambda: set_("lang", "ja")), (800, lambda: None), *again(), (1500, shot("lang-japanese")),
            (0, lambda: set_("lang", "en")), (600, self.finish),
        ]
        self.steps = [(max(d, 700) if k and getattr(self.steps_raw[k - 1][1], "is_shot", False) else d, f)
                      for k, (d, f) in enumerate(self.steps_raw)]
        self._next()

    def finish(self):
        if self.icy:
            self.icy.stopping = True
        super().finish()
