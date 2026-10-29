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
    def __init__(self, app, win, player, playlist, actions, args, settings, editor, preview):
        QObject.__init__(self)
        self.app, self.win, self.p, self.pl, self.a = app, win, player, playlist, actions
        self.settings, self.ed, self.pv, self.m8, self.icy = settings, editor, preview, {}, None
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
