"""Self-test: drives the real window through the real gestures and checks mpv's state.

Clicks go through QTest into the QML MouseAreas, keys through the same event filter a
user's keyboard reaches, so a passing run means the path people use works. Every step
logs a SELFCHECK line; captures are taken with PrintWindow (what the compositor shows).
"""
import ctypes
from ctypes import wintypes
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import winreg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QMetaObject, QObject, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent, QMouseEvent, QWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QSystemTrayIcon

from .i18n import EN, UK
from .log import log

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from wincap import capture  # noqa: E402

VK = {"Space": 0x20, "M": 0x4D, "S": 0x53, "Right": 0x27, "Enter": 0x0D, "Esc": 0x1B, "Up": 0x26,
      "P": 0x50, "PageDown": 0x22, "PageUp": 0x21, "Delete": 0x2E, "R": 0x52,
      "NP+": 0x6B, "2": 0x32, "1": 0x31, "=": 0xBB, "Q": 0x51, "`": 0xC0, "/": 0xBF, "I": 0x49, "K": 0x4B, "F12": 0x7B,
      "E": 0x45, "O": 0x4F, "X": 0x58, "\\": 0xDC, "Down": 0x28,
      "H": 0x48, "Z": 0x5A, "Y": 0x59, "F2": 0x71, "F10": 0x79, "End": 0x23, "MediaPlay": 0xB3, "Tab": 0x09,
      "[": 0xDB, "]": 0xDD, "F6": 0x75, "Home": 0x24, "Left": 0x25, "V": 0x56}
# a Ukrainian word ("Film"), written as escapes: names and typed text must survive in Cyrillic
CYRILLIC = "\u0424\u0456\u043b\u044c\u043c"
SCRATCH = r"Software\OYPlayerSelftest"     # the file types test writes here, and deletes it
ICY_METAINT = 8192


class _IcyHandler(BaseHTTPRequestHandler):
    """A radio station as Icecast/SHOUTcast serve one: an endless MP3 stream at its bitrate,
    with the track's title (ICY StreamTitle) between blocks when the player asks for it."""

    def do_GET(self):
        data, meta = self.server.mp3, self.headers.get("Icy-MetaData") == "1"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("icy-name", "oy test radio")
        if meta:
            self.send_header("icy-metaint", str(ICY_METAINT))
        self.end_headers()
        title = b"StreamTitle='oy test - track 1';"
        block = title + bytes(-len(title) % 16)
        block = bytes([len(block) // 16]) + block
        pos, sent, t0 = 0, 0, time.monotonic()
        try:
            while not self.server.stopping and not self.server.drop:
                chunk = data[pos:pos + ICY_METAINT]
                chunk += data[:ICY_METAINT - len(chunk)]
                pos = (pos + ICY_METAINT) % len(data)
                self.wfile.write(chunk + (block if meta else b""))
                sent += len(chunk)
                # a few seconds ahead, then at 128 kbit/s, as a live station sends
                ahead = sent - 16000 * (time.monotonic() - t0) - 64000
                if ahead > 0:
                    time.sleep(ahead / 16000)
        except OSError:
            pass                    # the player went away
        # the drop is one: this connection ends, the player's reconnect gets a stream again (a
        # flag cleared by the test 400 ms later was missed by a handler asleep between blocks)
        self.server.drop = False

    def log_message(self, *args):
        pass


def start_icy(mp3):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _IcyHandler)
    srv.mp3, srv.stopping, srv.drop, srv.daemon_threads = mp3, False, False, True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# The update checks sign with a throwaway key, never the release key: its public half and
# its signature of UPD_PAYLOAD (made once with the cryptography package).
UPD_PUB = bytes.fromhex(
    "2a5a91a75d04c28892631505c19aa0bdde815c6451eef9e41a55139cad864fb2"
    "314b021745d19c305071607d107385999fe073ac7692b0c0eaae02634171e7c2")
UPD_SIG = ("253aa4970519038bc02ca648f9201601ca7d1d924f9f3f1a784e031e10c0ffda"
           "089b9c7fed2397bb94e6c4510f285793fe60088f259563181a18b0b2bd045e82")
UPD_PAYLOAD = b"OY Player self-test installer\r\n" * 4000


class _FilesHandler(BaseHTTPRequestHandler):
    """A release page on 127.0.0.1: path -> bytes."""

    def do_GET(self):
        body = self.server.files.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def reg_exists(path):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
        return True
    except FileNotFoundError:
        return False


def reg_values(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return {winreg.EnumValue(k, i)[0]: winreg.EnumValue(k, i)[1] for i in range(winreg.QueryInfoKey(k)[1])}
    except FileNotFoundError:
        return None


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                       capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(r.stdout or "{}")


def frame_hashes(path, ss=None, n=50):
    """md5 of the first n decoded pictures (from ss): equal lists = the same pixels."""
    r = subprocess.run(["ffmpeg", "-v", "error"] + (["-ss", str(ss)] if ss is not None else [])
                       + ["-i", str(path), "-map", "0:v:0", "-frames:v", str(n), "-f", "framemd5", "-"],
                       capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return [ln.rsplit(",", 1)[1].strip() for ln in r.stdout.splitlines() if ln and not ln.startswith("#")]


class SelfTest(QObject):
    def __init__(self, app, win, player, playlist, actions, args, settings=None, editor=None, preview=None, m8=None):
        """args: <media> <outdir> [more media]; without more media, the other clips
        next to <media> are used, so the playlist steps always have two files."""
        super().__init__()
        self.app, self.win, self.p, self.pl, self.a = app, win, player, playlist, actions
        self.settings = settings
        self.ed = editor
        self.pv = preview
        self.m8 = m8 or {}
        self.icy = None
        self.media, self.out = str(Path(args[0]).resolve()), Path(args[1])
        extra = [str(Path(m).resolve()) for m in args[2:]]
        if not extra:
            extra = [str(f) for f in sorted(Path(self.media).parent.iterdir())
                     if f.suffix in (".mp4", ".mkv") and str(f) != self.media][:1]
        self.medias = [self.media] + extra
        self.out.mkdir(parents=True, exist_ok=True)
        self.failures = []
        self.result = 1
        self.steps = []

    # ---- helpers
    def check(self, name, ok, detail=""):
        log.info("SELFCHECK %s %s %s", "PASS" if ok else "FAIL", name, detail)
        print(f"SELFCHECK {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
        if not ok:
            self.failures.append(name)

    def shot(self, name):
        img = capture(int(self.win.winId()))
        img.save(str(self.out / f"{name}.png"))

    def key(self, name, mods=Qt.NoModifier):
        vk = VK[name]
        for t in (QEvent.KeyPress, QEvent.KeyRelease):
            ev = QKeyEvent(t, 0, mods, 0, vk, 0, "")
            QGuiApplication.sendEvent(self.win, ev)

    def click(self, object_name, at=None, double=False):
        item = self.win.findChild(QObject, object_name)
        c = item.mapToScene(QPointF(*(at or (item.width() / 2, item.height() / 2))))
        pt = QPoint(int(c.x()), int(c.y()))
        if double:
            QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, pt)
        else:
            QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, pt)

    def check_on_own_screen(self, name):
        area, g = self.win.screen().availableGeometry(), self.win.geometry()
        self.check(name, area.contains(g), f"window={g.getRect()} area={area.getRect()}")

    def find_item(self, name, item=None):
        item = item or self.win.contentItem()
        if item.objectName() == name:
            return item
        for child in item.childItems():
            hit = self.find_item(name, child)
            if hit is not None:
                return hit
        return None

    def near_accent(self, color):
        """A colour of the accent's family (its hue, within a few degrees): the accent itself or
        its lighter shade for signs and words."""
        c, a = QColor(color), QColor(self.settings["accent"])
        return c.hsvSaturation() > 60 and min(abs(c.hue() - a.hue()), 360 - abs(c.hue() - a.hue())) <= 20

    def click_item(self, item, at=None):
        c = item.mapToScene(QPointF(*(at or (item.width() / 2, item.height() / 2))))
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def until(self, cond, timeout=60.0, poll=200):
        """A step that waits (re-queues itself) until cond() holds or the time is up."""
        deadline = []

        def step():
            if not deadline:
                deadline.append(time.monotonic() + timeout)
            if not cond() and time.monotonic() < deadline[0]:
                self.steps.insert(0, (poll, step))
        step.__name__ = "until"
        return step

    def st(self, k):
        return self.p._state[k]

    def _watchdog(self):
        # A stuck run must not leave a window behind: the venv's python.exe is a launcher,
        # and killing it from outside leaves this process (and its window) running.
        log.error("SELFCHECK FAIL watchdog: run did not finish, remaining steps %d", len(self.steps))
        print("SELFCHECK FAIL watchdog", flush=True)
        os._exit(2)

    # ---- the run: a list of (delay ms, step) executed in order
    def start(self):
        QTimer.singleShot(540000, self._watchdog)
        # the checks read English words, whatever Windows speaks; the track languages to match
        self.settings.set("lang", "en")
        self.settings.set("audioLang", "eng,en")
        self.settings.set("subLang", "eng,en")
        # the list as it was before 0.11.2 (opened files join it): the older checks build lists so;
        # the new default (only the opened file) is checked in fb4
        self.list_default = self.settings["openAdds"]
        self.settings.set("openAdds", True)
        # the quick part, run every time: the strings, open, play, pause, seek, keys, full screen
        smoke = [
            (0, self.s_lang_open), (700, self.s_lang_page), (500, self.s_lang_uk), (500, self.s_lang_uk_chk),
            (500, self.s_lang_en_chk),
            (0, self.s_open), (2500, self.s_playing), (0, self.s_click_pause),
            (400, self.s_paused), (0, self.s_key_space), (400, self.s_resumed),
            (0, self.s_seek), (600, self.s_seeked), (0, self.s_keys_misc), (500, self.s_misc_done),
            (0, self.s_fast), (300, self.s_fast_done), (0, self.s_shot), (800, self.s_shot_done),
            (0, self.s_fullscreen), (900, self.s_fs_shown), (3200, self.s_fs_hidden),
            (0, self.s_esc), (800, self.s_windowed),
        ]
        base = [
            (0, self.s_pl_show), (600, self.s_pl_shown), (0, self.s_pl_next), (1500, self.s_pl_nexted),
            (0, self.s_pl_prev), (1500, self.s_pl_preved), (0, self.s_pl_eof), (3000, self.s_pl_eofed),
            (0, self.s_pl_repeat_one), (3000, self.s_pl_repeated), (0, self.s_pl_delete),
            (700, self.s_pl_deleted), (0, self.s_pl_dclick), (1500, self.s_pl_dclicked),
            (0, self.s_v_open), (600, self.s_v_opened), (0, self.s_v_keys), (500, self.s_v_keyed),
            (0, self.s_v_filter), (1200, self.s_v_filtered), (0, self.s_v_esc), (400, self.s_v_closed),
            (0, self.s_sub_load), (1200, self.s_sub_loaded), (0, self.s_sub_seek), (900, self.s_sub_seen), (900, lambda: None),
            (0, self.s_sub_menu), (700, self.s_sub_menued),
            (0, self.s_tech), (900, self.s_teched), (0, self.s_scale), (900, self.s_scaled),
            (0, self.s_a_open), (2000, self.s_a_opened), (600, self.s_a_cycled), (1200, self.s_a_added),
            (900, self.s_a_mode), (900, self.s_a_menu), (700, self.s_a_menued), (0, self.s_info),
            (1200, self.s_infoed),
            (0, self.s_set_open), (700, self.s_set_opened), (500, self.s_set_keys_shot),
            (0, self.s_capture), (300, self.s_captured), (500, self.s_rebound),
            (0, self.s_theme), (800, self.s_themed), (0, self.s_ontop), (700, self.s_ontop_paused),
            (700, self.s_ontop_done), (0, self.s_resume_prep), (1500, self.s_resume_away),
            (2000, self.s_resume_back), (2500, self.s_resumed_chk), (0, self.s_set_esc), (500, self.s_set_closed),
        ]
        long_mkv, clip = str(Path(self.media).parent / "test_long.mkv"), self.media

        def seek(t):
            return lambda: self.p.seek(t)

        def key(name):
            return lambda: self.key(name)
        editor = [
            # M6: the editor. test_long.mkv is playing (left by the resume steps).
            (0, self.s_ed_open), (700, self.s_ed_key), (700, self.s_ed_opened),
            ] + self.keep_steps([(12.0, 24.5), (41.0, 47.0)]) + [(0, self.s_ed_marked),
            (0, lambda: self.pl.add([clip], True)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            ] + self.keep_steps([(2.0, 3.0), (4.0, 6.0)]) + [(0, self.s_ed_cut),
            (0, self.s_ed_undo), (300, self.s_ed_undone), (300, self.s_ed_redone),
            (0, self.s_ed_prev), (600, self.s_ed_prev_key), (1700, self.s_ed_prev_mid), (2600, self.s_ed_prev_end),
            (0, self.s_ed_drag), (300, lambda: self.key("Left", Qt.ControlModifier | Qt.ShiftModifier)),
            (300, lambda: self.key("Left", Qt.ControlModifier | Qt.ShiftModifier)), (600, self.s_ed_dragged),
            (0, self.s_ed_mixed), (500, self.until(lambda: not self.ed.exporting)), (0, self.s_ed_mixed_done),
            (0, self.s_ed_del_first), (500, lambda: self.key("Delete")),
            (500, self.s_ed_del_last), (500, lambda: self.key("Delete")), (500, self.s_ed_deleted),
            (0, self.s_ed_copy), (500, self.until(lambda: not self.ed.exporting)), (0, self.s_ed_copy_done),
            (0, self.s_ed_cancel_prep), (0, lambda: self.pl.add([str(Path(self.media).parent / "test1080.mkv")], True)),
            (1800, lambda: self.a.run("edit_whole")), (0, lambda: self.pl.add([long_mkv], True)),
            (1800, lambda: self.a.run("edit_whole")), (0, self.s_ed_cancel_start),
            (300, self.until(lambda: self.ed.progress > 0.05 or not self.ed.exporting, 30, 100)),
            (0, self.s_ed_cancel_click), (300, self.until(lambda: not self.ed.exporting, 8, 100)), (0, self.s_ed_cancelled),
            (0, self.s_ed_settings), (700, self.s_ed_settings_nav), (600, self.s_ed_settings_shot),
            (0, lambda: self.key("Esc")), (500, lambda: self.key("Esc")), (600, self.s_ed_closed),
        ]

        def ui(name):
            return lambda: self.click(name)
        draw = [
            # M7: drawings over the picture, on test_long.mkv: a new edit of one fragment, 12-24.5 s
            (0, self.s_dr_open), (700, self.s_dr_key), (600, key("I")), (300, self.until(lambda: not self.ed.pending, 10, 50)),
            (0, seek(24.5)), (500, key("O")),
            (0, seek(13.0)), (900, self.s_dr_opened),
            (0, ui("drawRect")), (300, lambda: self.drag([(0.2, 0.2), (0.35, 0.35), (0.5, 0.5)])),
            (500, self.s_dr_rect_done),
            (0, ui("drawArrow")), (300, lambda: self.drag([(0.62, 0.75), (0.75, 0.55), (0.85, 0.35)])),
            (300, ui("drawPen")), (300, lambda: self.drag([(0.1, 0.9), (0.15, 0.8), (0.2, 0.9), (0.25, 0.8), (0.3, 0.9)])),
            (300, ui("drawText")), (300, lambda: self.click_layer(0.06, 0.62)), (400, lambda: self.type_text(CYRILLIC)),
            (300, lambda: self.type_text("\r", Qt.Key_Return)), (500, self.s_dr_typed),
            (0, lambda: self.key("Z", Qt.ControlModifier)), (300, self.s_dr_undone),
            (0, lambda: self.key("Y", Qt.ControlModifier)), (300, self.s_dr_redone),
            (0, ui("drawSelect")), (300, lambda: self.click_layer(0.35, 0.2)), (400, self.s_dr_selected),
            (0, self.s_dr_range), (500, self.s_dr_ranged),
            (0, self.s_dr_away), (900, self.s_dr_outside), (400, self.s_dr_outside_cmp),
            (0, lambda: self.p.seek(15.0)), (700, lambda: self.click_layer(0.2, 0.85)), (300, lambda: self.key("Delete")),
            (400, self.s_dr_deleted), (0, lambda: self.drag([(0.35, 0.2), (0.38, 0.23), (0.40, 0.25)])), (400, self.s_dr_moved),
            (0, self.s_dr_export), (500, self.until(lambda: not self.ed.exporting)), (0, self.s_dr_export_done),
            (0, lambda: self.key("Esc")), (600, self.s_dr_closed),
        ]

        def hover(frac):
            return lambda: QTest.mouseMove(self.win, self.rail_pt(frac))
        mem, mem2 = str(self.out / "memory.mkv"), str(self.out / "memory2.mp4")
        ideas = [
            # Ideas: the frame under the pointer over the seek bar, on test_long.mkv (keyframes
            # every 10 s) while it plays
            # first a second of plain playing, as the measure of what this machine drops anyway
            (0, self.s_pv_start), (1000, self.s_pv_control), (0, hover(0.10)), (150, hover(0.18)), (150, hover(0.33)),
            (150, hover(0.47)), (150, hover(0.25)), (500, self.s_pv_played), (200, self.s_pv_shown),
            (0, hover(0.75)), (700, self.s_pv_moved),
            (0, self.s_pv_off), (500, self.s_pv_off_chk),
            # A-B repeat: \ sets A, \ sets B, \ ends it
            (0, self.s_ab_prep), (500, key("\\")), (0, seek(40.0)), (500, key("\\")), (0, seek(38.5)),
            # the OSD line is in the photo, gone (1.6 s) before the pixel comparison
            (700, lambda: self.shot("27_ab_loop")), (1300, self.s_ab_set), (400, self.s_ab_cmp), (3500, self.s_ab_looped), (0, key("\\")), (400, self.s_ab_off),
            (0, key("\\")), (0, lambda: self.pl.add([clip], True)), (1800, self.s_ab_next_file),
            # sound track, subtitles and volume kept for each file (fresh copies: no history yet)
            # (a key per step: two presses in one step would read the same not yet updated volume)
            (0, self.s_mem_prep), (1800, self.s_mem_change), (200, key("Down")), (200, key("Down")),
            (500, self.s_mem_leave), (1800, self.s_mem_other)] + [(150, key("Up"))] * 4 + [
            (500, lambda: self.pl.add([mem], True)), (1800, self.s_mem_back),
            (0, self.s_mem_off), (1800, key("Up")), (150, key("Up")), (300, self.s_mem_off_back), (1800, self.s_mem_off_chk),
        ]

        def keym(name, mods):
            return lambda: self.key(name, mods)
        m8 = [
            # M8: a series in a folder of its own (links to test_long.mkv, 90 s): one opened
            # episode brings the next ones; the opening and the credits marked in one are skipped
            # in the others
            (0, self.s_ser_prep), (2000, self.s_ser_added),
            (0, seek(5.0)), (500, keym("E", Qt.AltModifier)), (0, seek(15.0)), (500, keym("E", Qt.ShiftModifier)),
            (300, self.s_skip_marked), (0, seek(80.0)), (500, keym("O", Qt.ShiftModifier)), (2000, self.s_skip_credits),
            (0, seek(4.0)), (1800, self.s_skip_opening), (0, seek(84.0)), (1800, self.s_skip_next),
            (0, self.s_skip_menu), (600, self.s_skip_menued),
            (0, keym("O", Qt.AltModifier)), (300, self.s_skip_off), (1800, self.s_skip_off_chk), (0, keym("O", Qt.AltModifier)),
            # the viewing history: what was watched in this run, newest first; a double click plays it
            (0, keym("H", Qt.ControlModifier)), (700, self.s_hist_shown), (1800, self.s_hist_played),
            # the scheduler: the clock in the title bar; shutdown is only recorded in a self-test
            (0, self.s_sch_open), (600, self.s_sch_menu), (400, self.s_sch_when), (400, self.s_sch_armed),
            (1500, self.s_sch_counting), (2600, self.s_sch_powered),
            (0, self.s_sch_cancel_prep), (1500, self.s_sch_cancel_click), (2600, self.s_sch_cancelled),
            (0, self.s_sch_timer), (2800, self.s_sch_timer_chk),
            (0, self.s_sch_list_end), (1800, lambda: self.p.seek(18.5)), (2000, self.s_sch_list_counting),
            # the 3 s countdown ends about 2.6 s after this step: measured 0.09 s before the check, and
            # once 0.2 s after it (a failure): the check waits for it, up to 3 s more
            (2600, self.until(lambda: len(self.sch.powered) >= 2, 3.0, 100)), (0, self.s_sch_list_powered),
            # internet radio: a station file for a stream served here (ICY, like a real station)
            (0, self.s_radio_prep), (0, keym("F2", Qt.ControlModifier)), (700, self.s_radio_listed),
            (3500, self.s_radio_playing), (0, lambda: self.click_item(self.find_item("radioRecord"))),
            (3000, lambda: self.click_item(self.find_item("radioRecord"))), (800, self.s_radio_recorded),
            # one player: a second start hands its file to this one and leaves
            (0, self.s_inst_send), (500, self.until(lambda: self.inst_proc.poll() is not None, 20, 200)),
            (1500, self.s_inst_done),
            # the notification-area icon: minimising hides into it, a click brings the window back
            (0, self.s_tray_on), (700, self.s_tray_shown), (0, key("End")), (900, self.s_tray_hidden),
            (900, self.s_tray_back), (500, self.s_tray_middle), (500, self.s_media_prep),
            # media keys: in the window, and (setting) from anywhere
            (0, key("MediaPlay")), (500, self.s_media_local), (0, self.s_media_global), (500, self.s_media_global_chk),
            # file types: only by the settings' button, here into a scratch registry key
            (0, self.s_assoc_prep), (700, self.s_assoc_nav), (700, self.s_assoc_shot), (300, self.s_assoc_on),
            (700, self.s_assoc_registered), (500, self.s_assoc_removed),
            (0, lambda: self.settings_page(0, "setSeries")), (900, lambda: self.shot("m8_10_settings_playback")),
            (0, lambda: self.settings_page(2, "setRadioDir")), (900, lambda: self.shot("m8_11_settings_radio")),
            (0, lambda: self.settings_page(4, "setGlobalMedia")), (900, lambda: self.shot("m8_12_settings_keys")),
            (0, lambda: self.key("Esc")), (500, self.s_about), (600, self.s_about_shot),
        ]
        # A long file playing: what the editor, drawing and ideas blocks start from in a full
        # run (the resume steps leave it). The later blocks prepare their own.
        long_playing = [(0, lambda: self.pl.add([long_mkv], True)), (1800, lambda: None)]
        blocks = {
            "base": lambda: base,                # playlist, video card, subtitles, sound, settings
            "editor": lambda: editor,            # M6: cut, join, preview, save
            "draw": lambda: draw,                # M7: drawings over the picture
            "ideas": lambda: ideas,              # frame preview, A-B, per-file memory
            "m8": lambda: m8,                    # series, skips, history, scheduler, radio, tray, file types
            "fb1": self.fb1_steps,     # feedback 1: the time scale, screenshot colours, hints
            "fb2": self.fb2_steps,     # feedback 2 (UI/UX council 1, stages 1 and 2)
            "fb3": self.fb3_steps,     # release blockers: failures said, streams reconnected
            "st1": self.st1_steps,     # stage 1: nothing slow on the GUI thread
            "st3": self.st3_steps,     # stage 3: keyboard areas and the screen reader
            "st4": self.st4_steps,     # stage 4: the Braun panel, an honest edit
            "tails": self.tails_steps,     # the tails of stages 1-4
            "fb4": self.fb4_steps,     # feedback 4 (0.11.1): the mouse, settings, the picture card
            "upd": self.upd_steps,     # the update from the release page
        }
        # tests\next-run-focus (used up like next-run-exe): the quick part and only the blocks it
        # names; empty, the quick part alone. Without it, everything.
        focus_file = Path(self.media).parent.parent / "next-run-focus"
        if focus_file.exists():
            names = focus_file.read_text(encoding="utf-8").split()
            focus_file.unlink()
            unknown = [n for n in names if n not in blocks]
            self.check("the focus file names known blocks", not unknown, f"unknown={unknown} known={list(blocks)}")
            self.run_name = "+".join(["smoke"] + [n for n in blocks if n in names])
        else:
            names = list(blocks)
            self.run_name = "full"
        self.steps = list(smoke)
        for name, make in blocks.items():
            if name in names:
                if self.run_name != "full" and name in ("editor", "draw", "ideas"):
                    self.steps += long_playing
                if self.run_name != "full" and name.startswith(("fb", "st", "tails", "upd")) and "m8" not in names:
                    self.steps += [(0, self.s_m8_state)]
                self.steps += make()
        self.steps.append((0, self.s_finish))
        self._next()

    def s_m8_state(self):
        """What the later blocks find after M8 in a full run: the scheduler and the test station."""
        self.sch = self.m8["scheduler"]
        if self.icy is None:
            self.s_radio_prep()

    def _next(self):
        if not self.steps:
            return
        delay, fn = self.steps.pop(0)
        QTimer.singleShot(delay, lambda: self._step(fn))

    def _step(self, fn):
        try:
            fn()
        except Exception:
            log.exception("SELFCHECK FAIL step %s raised", fn.__name__)
            self.failures.append(fn.__name__)
        self._next()

    # ---- the interface's language: English and Ukrainian, switched in the settings on the fly
    def s_lang_open(self):
        pairs = [k for k in EN if sorted(re.findall(r"%\d", EN[k])) != sorted(re.findall(r"%\d", UK[k]))]
        self.check("English and Ukrainian have the same strings with the same placeholders",
                   EN.keys() == UK.keys() and not pairs,
                   f"only EN={sorted(EN.keys() - UK.keys())} only UK={sorted(UK.keys() - EN.keys())} placeholders={pairs}")
        self.click("keySettings")

    def s_lang_page(self):
        self.click_item(self.find_item("nav1"))

    def s_lang_uk(self):
        self.lang_en = (self.find_text(EN["s_caps"]), self.find_item("keyPlay").property("tip"))
        self.pick_lang("Українська")

    def pick_lang(self, name):
        """The language list opened, then its row clicked, as a person picks a language."""
        self.click_item(self.find_item("setLang"))
        QTimer.singleShot(250, lambda: self.click_item(self.find_text(name)))

    def _lang_shows(self, d):
        tray = [a.text() for a in self.m8["tray"].menu.actions() if a.text()]
        return {"settings title": self.find_text(d["s_caps"]) is not None,
                "section": self.find_text(d["p_window"]) is not None,
                "language row": self.find_text(d["s_lang"]) is not None,
                "play key": self.find_item("keyPlay").property("tip").startswith(d["t_play"]),
                "drop hint": self.find_text(d["drop_hint"]) is not None,
                "key editor": self.a.bindable()[0]["title"] == d["act_play_pause"],
                "tray": tray[:1] == [d["tray_show"]]}

    def s_lang_uk_chk(self):
        shows = self._lang_shows(UK)
        self.check("a click on «Ukrainian» shows the window in Ukrainian at once (QML and Python texts)",
                   self.settings["lang"] == "uk" and all(shows.values()) and self.lang_en[0] is not None
                   and self.lang_en[1].startswith(EN["t_play"]), f"lang={self.settings['lang']} {shows} en={self.lang_en}")
        self.shot("00_lang_uk")
        self.pick_lang("English")

    def s_lang_en_chk(self):
        shows = self._lang_shows(EN)
        self.check("a click on «English» brings the English texts back",
                   self.settings["lang"] == "en" and all(shows.values()), f"lang={self.settings['lang']} {shows}")
        self.shot("00_lang_en")
        panel = self.win.findChild(QObject, "settingsPanel")
        panel.setProperty("section", 0)      # the settings steps later start from the first section
        QMetaObject.invokeMethod(panel, "close")

    def s_open(self):
        self.pl.clear()
        self.pl.add(self.medias, True)

    def s_playing(self):
        self.shot("01_playing")
        self.check("plays", self.st("position") > 1.0 and not self.st("paused"),
                   f"pos={self.st('position'):.2f} vo={self.p.mpv.current_vo} hwdec={self.p.mpv.hwdec_current}")
        self.check("duration", self.st("duration") > 5, f"dur={self.st('duration')}")
        self.check_on_own_screen("window fitted to the video stays on its monitor")

    def s_click_pause(self):
        self.click("keyPlay")

    def s_paused(self):
        self.check("click play key pauses", self.st("paused") is True)
        self.shot("02_paused")

    def s_key_space(self):
        self.key("Space")

    def s_resumed(self):
        self.check("Space resumes", self.st("paused") is False)

    def s_seek(self):
        self.p.seek(3.0)

    def s_seeked(self):
        # 3 s + Right (5 s) stays inside any clip longer than ~9 s: past the end mpv
        # (keep-open) lands on the last keyframe instead.
        self.check("seek to 3s", abs(self.st("position") - 3.0) < 1.0, f"pos={self.st('position'):.2f}")
        self.vol0 = self.st("volume")
        self.muted0 = self.st("muted")
        self.key("M")
        self.key("S")
        self.key("Up")
        self.key("Right")

    def s_keys_misc(self):
        pass

    def s_misc_done(self):
        self.check("M toggles mute", self.st("muted") is (not self.muted0))
        self.check("S hides subtitles", self.st("subVisible") is False)
        self.check("Up raises volume", self.st("volume") > self.vol0 or self.vol0 >= 100,
                   f"{self.vol0}->{self.st('volume')}")
        self.check("Right seeks +5s", self.st("position") > 7.0, f"pos={self.st('position'):.2f}")
        self.shot("03_muted_nosubs")
        self.key("M")
        self.key("S")

    def s_fast(self):
        self.a.run("fast_play")

    def s_fast_done(self):
        self.check("fast play 1.5x", abs(self.st("speed") - 1.5) < 1e-6, f"speed={self.st('speed')}")
        self.p.mpv.speed = 1.0

    def s_shot(self):
        self.shots_before = set(Path(self.out / "shots").glob("*.png"))
        self.p.screenshot(str(self.out / "shots"))

    def s_shot_done(self):
        new = set(Path(self.out / "shots").glob("*.png")) - self.shots_before
        self.check("screenshot file", len(new) == 1, ", ".join(p.name for p in new))

    def s_fullscreen(self):
        self.key("Enter")

    def s_fs_shown(self):
        self.check("Enter = fullscreen", self.win.property("fs") is True)
        self.shot("04_fullscreen_chrome")
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))

    def s_fs_hidden(self):
        # The self-test window is transparent for input, so the owner's real pointer
        # cannot hover it; the only pointer is the test's own, parked mid-picture.
        self.check("fullscreen chrome hides", self.win.property("chromeAwake") is False)
        self.shot("05_fullscreen_clean")

    def s_esc(self):
        self.key("Esc")

    def s_windowed(self):
        self.check("Esc leaves fullscreen, keeps window", self.win.property("fs") is False and self.win.isVisible())
        self.shot("06_windowed")

    # ---- M2: playlist
    def s_pl_show(self):
        self.key("P")

    def s_pl_shown(self):
        right = self.p.mpv["video-margin-ratio-right"]
        self.check("P shows playlist, picture moves aside",
                   self.win.property("playlistShown") is True and right > 0.2, f"margin-right={right:.3f}")
        self.check("playlist has both files", self.pl.count == len(self.medias) == 2, f"count={self.pl.count}")
        self.shot("07_playlist")

    def s_pl_next(self):
        self.key("PageDown")

    def s_pl_nexted(self):
        self.check("PageDown plays next", self.pl.current == 1 and self.st("path") == self.medias[1],
                   f"current={self.pl.current} path={Path(self.st('path')).name}")

    def s_pl_prev(self):
        self.key("PageUp")

    def s_pl_preved(self):
        self.check("PageUp plays previous", self.pl.current == 0 and self.st("path") == self.medias[0],
                   f"current={self.pl.current}")

    def s_pl_eof(self):
        self.p.seek(self.st("duration") - 0.8)

    def s_pl_eofed(self):
        self.check("end of file plays next", self.pl.current == 1 and self.st("path") == self.medias[1],
                   f"current={self.pl.current}")

    def s_pl_repeat_one(self):
        self.key("R", Qt.ShiftModifier)
        QTimer.singleShot(300, lambda: self.p.seek(self.st("duration") - 0.8))

    def s_pl_repeated(self):
        self.check("Shift+R repeats the file", self.pl.repeat == 2 and self.pl.current == 1
                   and self.st("position") < 3.0, f"repeat={self.pl.repeat} pos={self.st('position'):.2f}")
        self.key("R", Qt.ShiftModifier)

    def s_pl_delete(self):
        self.click("playlistView", at=(40, 4 + 15))     # first row
        self.key("Delete")

    def s_pl_deleted(self):
        saved = json.loads((Path(os.environ.get("OY_HOME", "")) / "playlist.json").read_text(encoding="utf-8"))             if os.environ.get("OY_HOME") else {"items": []}
        self.check("click row + Delete removes it", self.pl.count == 1 and self.pl.current == 0,
                   f"count={self.pl.count} current={self.pl.current}")
        self.check("playlist saved to disk", len(saved["items"]) == 1, f"saved={len(saved['items'])}")
        self.shot("08_playlist_one")

    def s_pl_dclick(self):
        self.a.run("stop")
        self.click("playlistView", at=(40, 4 + 15), double=True)

    def s_pl_dclicked(self):
        self.check("double click plays the row", self.pl.current == 0 and self.st("paused") is False,
                   f"paused={self.st('paused')}")

    # ---- M3: picture and subtitles
    def s_v_open(self):
        self.key("V", Qt.ShiftModifier)

    def s_v_opened(self):
        self.check("video key opens the picture card", self.win.findChild(QObject, "videoPanel").property("visible") is True)
        self.shot("09_video_panel")

    def s_v_keys(self):
        self.b0 = self.st("brightness")
        self.key("NP+", Qt.ShiftModifier)
        self.key("2", Qt.ShiftModifier)
        self.key("=")

    def s_v_keyed(self):
        self.check("Shift+NP+ brightness +5", self.st("brightness") == self.b0 + 5, f"{self.b0}->{self.st('brightness')}")
        self.check("Shift+2 aspect 4:3", self.p.aspectMode in ("4:3", "1.333333"), f"aspect={self.p.aspectMode!r}")
        self.check("= zooms in", self.st("zoom") > 0.05, f"zoom={self.st('zoom'):.2f}")

    def s_v_filter(self):
        self.p.toggleFilter("gray")

    def s_v_filtered(self):
        self.check("grey filter on, still playing", "gray" in self.p.activeFilters and self.st("position") > 0
                   and not self.st("paused"), f"filters={self.p.activeFilters} hwdec={self.p.mpv.hwdec_current}")
        self.shot("10_gray_43_zoom")
        self.p.toggleFilter("gray")
        self.p.resetColors()
        self.p.resetGeometry()

    def s_v_esc(self):
        self.key("Esc")

    def s_v_closed(self):
        panel = self.win.findChild(QObject, "videoPanel")
        self.check("Esc closes the card, not the player",
                   panel.property("visible") is False and self.win.isVisible(),
                   f"card visible={panel.property('visible')} window visible={self.win.isVisible()}")

    def s_sub_load(self):
        srt = Path(self.media).with_suffix(".srt")
        second = self.out / "second.srt"      # a second track, so secondary subtitles have one
        second.write_text("1\n00:00:00,500 --> 00:00:30,000\nSecond track\n", encoding="utf-8")
        self.p.addSubtitle(str(second))
        self.p.addSubtitle(str(srt))

    def s_sub_loaded(self):
        subs = self.p.subTracks
        self.check("subtitle file loads and is selected", len(subs) >= 1 and self.st("sid") is not False,
                   f"tracks={[t['title'] for t in subs]} sid={self.st('sid')}")
        other = [t["id"] for t in subs if t["id"] != self.st("sid")]
        self.p.setSid2(other[0] if other else -1)
        self.key("Right", Qt.AltModifier)

    def s_sub_seek(self):
        self.p.mpv.pause = True
        self.p.seek(2.0)     # test720.srt line 1 (1-6 s) and second.srt (0.5-30 s) both on screen

    def s_sub_seen(self):
        # Pixels, not state: subtitles once were "selected" and drawn under the panel.
        self.with_subs = capture(int(self.win.winId()))
        self.with_subs.save(str(self.out / "11a_subs_render.png"))
        self.p.mpv["sub-visibility"] = False
        self.p.mpv["secondary-sub-visibility"] = False
        QTimer.singleShot(500, self._sub_diff)

    def _sub_diff(self):
        without = capture(int(self.win.winId()))
        changed = sum(1 for y in range(40, without.height() - 120, 3) for x in range(0, without.width() - 330, 3)
                      if self.with_subs.pixel(x, y) != without.pixel(x, y))
        self.check("subtitles visible on the picture", changed > 300, f"changed sample pixels={changed}")
        self.p.mpv["sub-visibility"] = True
        self.p.mpv["secondary-sub-visibility"] = True
        self.p.mpv.pause = False

    def s_sub_menu(self):
        self.check("secondary subtitles selectable", self.st("sid2") is not False, f"sid2={self.st('sid2')}")
        self.check("Alt+Right delays subtitles", abs(self.st("subDelay") - 0.1) < 1e-6, f"delay={self.st('subDelay')}")
        self.key("S", Qt.AltModifier)          # no key on the panel: Alt+S and the picture's menu

    def s_sub_menued(self):
        menu = self.win.findChild(QObject, "subsMenu")
        self.check("Alt+S opens the subtitle menu", menu.property("visible") is True)
        self.shot("11_subs_menu")
        self.key("Esc")
        self.p.setSid2(-1)

    def s_tech(self):
        self.key("Q")

    def s_teched(self):
        osd = self.win.findChild(QObject, "techOsd")
        info = self.p.techInfo()
        self.check("Q shows technical OSD", osd.property("visible") is True and "Video:" in info,
                   info.splitlines()[2] if len(info.splitlines()) > 2 else info)
        self.shot("12_tech_osd")
        self.key("Q")

    def s_scale(self):
        self.key("1", Qt.AltModifier)

    def s_scaled(self):
        want_w = round(self.st("videoW") * 0.5 / self.win.devicePixelRatio()) + self.win.property("sideW")
        self.check("Alt+1 sizes the window to a 50 % picture", abs(self.win.width() - max(want_w, 760)) <= 2,
                   f"w={self.win.width()} want={want_w}")
        self.shot("13_scale50")

    # ---- M4: sound and file info
    def s_a_open(self):
        self.multi = str(Path(self.media).parent / "test_multi.mkv")
        self.pl.add([self.multi], True)

    def s_a_opened(self):
        tr = self.p.audioTracks
        self.check("two audio tracks listed", len(tr) == 2 and self.st("aid") == 1,
                   f"tracks={[t['title'] for t in tr]} aid={self.st('aid')}")
        self.key("/")
        self.key("NP+")

    def s_a_cycled(self):
        self.check("/ switches audio track", self.st("aid") == 2, f"aid={self.st('aid')}")
        self.check("NP+ delays sound", abs(self.st("audioDelay") - 0.1) < 1e-6, f"delay={self.st('audioDelay')}")
        self.p.addAudio(str(Path(self.media).parent / "test_multi.extra.opus"))

    def s_a_added(self):
        tr = self.p.audioTracks
        self.check("external audio file loads and is selected", len(tr) == 3 and self.st("aid") == 3,
                   f"tracks={len(tr)} aid={self.st('aid')}")
        self.pos0 = self.st("position")
        self.p.setAudioMode("loudnorm")
        self.p.changePitch(2 ** (1 / 12))
        self.p.setVolume(180)

    def s_a_mode(self):
        self.check("EBU R128 normalisation on, still playing",
                   self.p.audioMode == "loudnorm" and self.st("position") > self.pos0 + 0.3,
                   f"mode={self.p.audioMode} pos {self.pos0:.2f}->{self.st('position'):.2f}")
        self.check("pitch one semitone up", abs(self.st("pitch") - 2 ** (1 / 12)) < 1e-3, f"pitch={self.st('pitch'):.4f}")
        self.check("volume above 100 % (boost to 180)", abs(self.st("volume") - 180) < 0.5, f"volume={self.st('volume')}")
        self.p.resetPitch()
        self.p.setAudioMode("off")
        self.p.setVolume(100)
        item = self.win.findChild(QObject, "keySound")
        c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.win, Qt.RightButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_a_menu(self):
        self.check("right click on sound key opens audio menu",
                   self.win.findChild(QObject, "audioMenu").property("visible") is True)
        self.shot("14_audio_menu")
        self.key("Esc")

    def s_a_menued(self):
        self.check("Esc closes the menu, player stays", self.win.isVisible()
                   and self.win.findChild(QObject, "audioMenu").property("visible") is False)

    def s_info(self):
        self.key("I", Qt.AltModifier)

    def s_infoed(self):
        panel = self.win.findChild(QObject, "infoPanel")
        secs = panel.property("sections") or []
        titles = [x["title"] for x in secs]
        rows = {r["k"]: r["v"] for r in secs[0]["rows"]} if secs else {}
        self.check("Alt+I shows file info with every stream",
                   panel.property("visible") is True and "Audio #2" in titles and rows.get("Title") == "Test film",
                   f"sections={titles}")
        self.shot("15_file_info")
        self.key("Esc")

    # ---- M5: settings
    def s_set_open(self):
        self.click("keySettings")

    def s_set_opened(self):
        panel = self.win.findChild(QObject, "settingsPanel")
        self.check("settings key opens settings", panel.property("visible") is True)
        self.shot("16_settings_playback")
        # Repeater delegates inside a popup are found by walking the visual item tree
        # (the overlay layer is under the window's content item), not the QObject tree.
        nav = self.find_item("nav4")
        c = nav.mapToScene(QPointF(nav.width() / 2, nav.height() / 2))
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_set_keys_shot(self):
        self.check("section switch", self.win.findChild(QObject, "settingsPanel").property("section") == 4)
        self.shot("17_settings_controls")

    def s_capture(self):
        self.captured = []
        self.a.keyCaptured.connect(self.captured.append)
        self.a.startCapture()
        self.key("K", Qt.ControlModifier)

    def s_captured(self):
        self.check("key editor captures the next key instead of acting", self.captured == ["Ctrl+K"],
                   f"captured={self.captured}")
        self.a.keyCaptured.disconnect(self.captured.append)
        self.settings.set("keys", {"Ctrl+K": "screenshot", "F12": ""})
        self.done = []
        self.a.performed.connect(self.done.append)
        self.key("K", Qt.ControlModifier)
        self.key("F12")

    def s_rebound(self):
        self.check("rebound key runs its action, removed key does nothing",
                   self.done.count("screenshot") == 1 and "F12" not in self.a.keysFor("screenshot"),
                   f"performed={self.done} keys={self.a.keysFor('screenshot')}")
        self.a.performed.disconnect(self.done.append)
        self.settings.set("keys", {})
        self.key("Esc")

    def _panel_pixel(self):
        img = capture(int(self.win.winId()))
        return img.pixelColor(img.width() - 40, img.height() - 60)

    def s_theme(self):
        self.dark_px = self._panel_pixel()
        self.settings.set("theme", "light")

    def s_themed(self):
        light_px = self._panel_pixel()
        self.check("light theme turns the body cream", light_px.lightness() > 180 and self.dark_px.lightness() < 80,
                   f"dark={self.dark_px.name()} light={light_px.name()}")
        self.shot("18_light_theme")
        self.settings.set("theme", "dark")

    def _topmost(self):
        return bool(self.win.flags() & Qt.WindowStaysOnTopHint)

    def s_ontop(self):
        self.p.mpv.pause = False
        self.settings.set("onTop", "playing")

    def s_ontop_paused(self):
        self.top_playing = self._topmost()
        self.p.mpv.pause = True

    def s_ontop_done(self):
        self.check("on top only while playing", self.top_playing and not self._topmost(),
                   f"playing={self.top_playing} paused={self._topmost()}")
        self.settings.set("onTop", "never")
        self.p.mpv.pause = False

    def s_resume_prep(self):
        # Only files longer than a minute are remembered, so this step uses a 90 s clip.
        self.settings.set("resume", True)
        self.pl.add([str(Path(self.media).parent / "test_long.mkv")], True)
        QTimer.singleShot(1200, lambda: self.p.seek(40.0))

    def s_resume_away(self):
        self.left_at = self.st("position")
        self.resume_row = self.pl.current
        self.pl.playIndex(0)

    def s_resume_back(self):
        self.pl.playIndex(self.resume_row)

    def s_resumed_chk(self):
        self.check("resume continues where the file was left", abs(self.st("position") - self.left_at) < 3.0,
                   f"left={self.left_at:.1f} now={self.st('position'):.1f}")
        self.check_on_own_screen("window still on its monitor after several fits")
        self.settings.set("resume", False)
        self.click("keySettings")

    def s_set_esc(self):
        self.key("Esc")

    def s_set_closed(self):
        saved = json.loads((Path(os.environ["OY_HOME"]) / "settings.json").read_text(encoding="utf-8"))
        self.check("Esc closes settings, player stays; settings on disk",
                   self.win.findChild(QObject, "settingsPanel").property("visible") is False
                   and self.win.isVisible() and saved.get("theme") == "dark" and saved.get("resume") is False,
                   f"saved theme={saved.get('theme')} resume={saved.get('resume')}")

    # ---- M6: editing
    def keep_steps(self, ranges):
        """Steps that leave these pieces of the playing file in the edit, as a person makes
        them: I at the first start, O at the last end, then for each gap X at its start, X at
        its end and Delete on the piece between (the one before the piece X chose)."""
        def at(t, key):
            return [(0, lambda: self.p.seek(t)), (500, lambda: self.key(key))]

        def drop():
            self.ed.select(self.ed.selected - 1)
            self.key("Delete")
        pend = self.until(lambda: not self.ed.pending, 10, 50)
        steps = at(ranges[0][0], "I") + [(300, pend)] + at(ranges[-1][1], "O") + [(300, pend)]
        for (_a, b), (c, _d) in zip(ranges, ranges[1:]):
            steps += at(b, "X") + [(300, pend)] + at(c, "X") + [(300, pend), (300, drop), (300, pend)]
        return steps

    def frags(self):
        # A mark is the shown frame's time: O after a seek to 24.5 s in a 25 fps clip is
        # the frame at 24.52 s. Tenths are what the checks compare.
        return [(f["name"], round(f["from"], 1), round(f["end"], 1)) for f in self.ed.fragments]

    def s_ed_open(self):
        self.p.mpv.pause = True
        self.p.seek(30.0)
        # the test's own pointer is still on the settings key: its hint would sit in the captures
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))

    def s_ed_key(self):
        self.pos0, self.size0 = self.st("position"), (self.win.width(), self.win.height())
        self.key("E", Qt.ControlModifier)

    def s_ed_opened(self):
        strip = self.win.findChild(QObject, "editStrip")
        self.check("Ctrl+E opens the editor on the same file and position",
                   self.ed.active and strip.property("visible") is True
                   and Path(self.st("path")).name == "test_long.mkv" and abs(self.st("position") - self.pos0) < 0.2,
                   f"pos {self.pos0:.2f}->{self.st('position'):.2f}")
        bottom = self.p.mpv["video-margin-ratio-bottom"]
        self.check("window keeps its size, the picture makes room for the strip",
                   (self.win.width(), self.win.height()) == self.size0
                   and abs(bottom - self.win.property("panelH") / self.win.height()) < 0.002,
                   f"size={self.size0} panelH={self.win.property('panelH')} margin={bottom:.3f}")
        self.shot("19_editor_open")

    def s_ed_marked(self):
        # Copy mode: a fragment starts on the keyframe at or before its mark (keyframes
        # every 10 s in test_long.mkv), and that is what the strip shows.
        self.check("I, O and two cuts with Delete leave two pieces; without loss every border moved to its keyframe",
                   self.frags() == [("test_long.mkv", 10.0, 20.0), ("test_long.mkv", 40.0, 47.0)]
                   and self.ed.lossless and abs(self.ed.total - 17.0) < 0.05
                   and [[round(x, 1) for x in b[:2]] for b in self.ed.bands] == [[10.0, 20.0], [40.0, 47.0]],
                   f"frags={self.frags()} total={self.ed.total:.2f}")

    def s_ed_cut(self):
        self.check("another file joins the edit whole and is trimmed and cut the same way",
                   self.frags()[2:] == [("test720.mp4", 2.0, 3.0), ("test720.mp4", 4.0, 6.0)] and len(self.frags()) == 4,
                   f"frags={self.frags()}")
        self.check("files of different formats: saving will re-encode, exact marks",
                   not self.ed.lossless and "different formats" in self.ed.note
                   and self.frags()[0] == ("test_long.mkv", 10.0, 20.0), f"note={self.ed.note}")
        self.check("the window did not jump to the new file's size while editing",
                   (self.win.width(), self.win.height()) == self.size0, f"size={(self.win.width(), self.win.height())}")
        self.shot("20_editor_fragments")

    def s_ed_undo(self):
        self.osd_seen = []
        self.p.osdMessage.connect(self.osd_seen.append)
        self.cut_frags = self.frags()
        self.key("Z", Qt.ControlModifier)

    def s_ed_undone(self):
        self.check("Ctrl+Z puts the deleted piece back and says what was undone",
                   self.frags()[2:] == [("test720.mp4", 2.0, 3.0), ("test720.mp4", 3.0, 4.0), ("test720.mp4", 4.0, 6.0)]
                   and self.osd_seen[-1:] and self.osd_seen[-1].startswith("Undone:"),
                   f"frags={self.frags()} osd={self.osd_seen}")
        self.key("Y", Qt.ControlModifier)

    def s_ed_redone(self):
        self.check("Ctrl+Y takes it out again", self.frags() == self.cut_frags
                   and self.osd_seen[-1:] and self.osd_seen[-1].startswith("Redone:"),
                   f"frags={self.frags()} osd={self.osd_seen}")
        self.p.osdMessage.disconnect(self.osd_seen.append)

    def s_ed_prev(self):
        self.click_frag(2)          # shows the fragment's first frame

    def s_ed_prev_key(self):
        self.check("click on a fragment shows its start", self.ed.selected == 2 and abs(self.st("position") - 2.0) < 0.2
                   and self.st("paused") is True, f"pos={self.st('position'):.2f}")
        # Space after a click on a fragment plays the edit from that fragment (Shift+Space
        # always starts at the first one)
        self.key("Space")

    def s_ed_prev_mid(self):
        # 2-3 s played, the cut 3-4 s skipped: the preview is in the next fragment
        self.check("preview skips the cut piece", self.ed.previewing == 3 and 4.0 <= self.st("position") < 6.0,
                   f"previewing={self.ed.previewing} pos={self.st('position'):.2f}")
        self.shot("21_editor_preview")

    def s_ed_prev_end(self):
        self.check("preview stops after the last fragment", self.ed.previewing == -1 and self.st("paused") is True
                   and 5.5 < self.st("position") <= 6.05, f"pos={self.st('position'):.2f}")

    def click_frag(self, row):
        """A click on a fragment's block on the clip track; one in another file is chosen as the
        line «N fragments in …» does it (its file opens), and the keys go to the fragments."""
        block = self.find_item(f"frag{row}")
        if block is not None:
            self.click_item(block)
        else:
            self.ed.select(row)
            self.win.setProperty("area", "strip")

    def s_ed_drag(self):
        self.click_frag(2)          # then Ctrl+Shift+← twice: to the front of the edit

    def s_ed_dragged(self):
        self.check("Ctrl+Shift+← moves the chosen fragment earlier in the edit, to the front",
                   self.frags()[0] == ("test720.mp4", 2.0, 3.0) and self.ed.selected == 0, f"frags={self.frags()}")

    def _sources(self):
        return {p: (os.stat(p).st_size, os.stat(p).st_mtime_ns) for p in {f["path"] for f in self.ed.frags}}

    def _out_check(self, name, path, want):
        info = ffprobe(path)
        kinds = sorted(s["codec_type"] for s in info.get("streams", []))
        dur = float(info.get("format", {}).get("duration", 0))
        self.check(name, path.exists() and abs(dur - want) <= 0.5 and kinds == ["audio", "video"]
                   and not list(self.out.glob("*.part.*")),
                   f"duration={dur:.2f} want={want:.2f} streams={kinds} saved={self.ed.saved and Path(self.ed.saved).name}")
        return info

    def s_ed_mixed(self):
        self.src0 = self._sources()
        self.want = self.ed.total
        self.ed.exportTo(str(self.out / "edit_mixed.mp4"))

    def s_ed_mixed_done(self):
        info = self._out_check("saved a join of two files: length = sum of fragments, picture and sound",
                               self.out / "edit_mixed.mp4", self.want)
        v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
        self.check("different formats re-encoded to H.264 at the larger frame",
                   self.ed.lastLossless is False and v.get("codec_name") == "h264" and v.get("width") == 1280,
                   f"codec={v.get('codec_name')} {v.get('width')}x{v.get('height')}")
        self.check("source files untouched", self._sources() == self.src0)

    def s_ed_del_first(self):
        self.click_frag(0)

    def s_ed_del_last(self):
        self.click_frag(len(self.ed.frags) - 1)

    def s_ed_deleted(self):
        self.check("click a fragment + Delete removes it (not a playlist row)",
                   self.frags() == [("test_long.mkv", 10.0, 20.0), ("test_long.mkv", 40.0, 47.0)]
                   and self.ed.lossless, f"frags={self.frags()} playlist={self.pl.count}")

    def s_ed_copy(self):
        src = self.ed.frags[0]["path"]
        before = self._sources()
        self.ed.exportTo(src)
        self.check("saving over a source file is refused", not self.ed.exporting and self._sources() == before,
                   f"exporting={self.ed.exporting}")
        self.want = self.ed.total
        self.ed.exportTo(str(self.out / "edit_copy.mkv"))

    def s_ed_copy_done(self):
        out = self.out / "edit_copy.mkv"
        info = self._out_check("saved without re-encoding: length = sum of fragments", out, self.want)
        src = str(Path(self.media).parent / "test_long.mkv")
        v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
        sv = next(s for s in ffprobe(src)["streams"] if s["codec_type"] == "video")
        same = frame_hashes(out) == frame_hashes(src, 10.0) != []
        self.check("copy mode leaves the codec alone: the same pictures, bit for bit",
                   self.ed.lastLossless is True and same
                   and [v.get(k) for k in ("codec_name", "profile", "width")] == [sv.get(k) for k in ("codec_name", "profile", "width")],
                   f"identical first 50 frames={same} codec={v.get('codec_name')} {v.get('profile')}")

    def s_ed_cancel_prep(self):
        self.settings.set("exportCodec", "h265")
        self.ed.frags = []

    def s_ed_cancel_start(self):
        self.check("H.265 chosen: re-encoding", self.ed.note == "re-encoding to H.265" and len(self.ed.frags) == 2,
                   f"note={self.ed.note} frags={self.frags()}")
        self.cancel_out = self.out / "edit_cancel.mp4"
        self.ed.exportTo(str(self.cancel_out))

    def s_ed_cancel_click(self):
        self.part_seen = self.cancel_out.with_name("edit_cancel.part.mp4").exists()
        self.cancel_at = self.ed.progress
        self.shot("22_editor_saving")
        self.click("editSave")       # while saving, the save key is the cancel key

    def s_ed_cancelled(self):
        self.check("cancel stops the save and removes the unfinished file",
                   self.part_seen and 0 < self.cancel_at < 1 and not self.ed.exporting
                   and not self.cancel_out.exists() and not list(self.out.glob("*.part.*")),
                   f"part seen={self.part_seen} at {self.cancel_at:.0%} final exists={self.cancel_out.exists()}")
        self.settings.set("exportCodec", "copy")

    def s_ed_settings(self):
        self.a.run("settings")          # editing, the editor's row stands where the Settings key was

    def s_ed_settings_nav(self):
        nav = self.find_item("nav5")
        self.click_item(nav)

    def s_ed_settings_shot(self):
        self.check("settings: export codec in «Screenshots and editing»", self.find_item("setExportCodec") is not None
                   and self.find_item("setExportCodec").property("value") == "copy")
        self.shot("23_settings_editing")

    def s_ed_closed(self):
        self.check("Esc closes settings, then the editor; the player stays",
                   not self.ed.active and self.win.isVisible()
                   and self.win.property("panelH") == 66 + self.find_item("keyPlay").height()
                   and len(self.ed.frags) == 2, f"active={self.ed.active} panelH={self.win.property('panelH')}")

    # ---- M7: drawings over the picture
    def layer_pt(self, nx, ny):
        layer = self.find_item("noteLayer")
        c = layer.mapToScene(QPointF(nx * layer.width(), ny * layer.height()))
        return QPoint(round(c.x()), round(c.y()))

    def click_layer(self, nx, ny):
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, self.layer_pt(nx, ny))

    def drag(self, pts):
        """Press, move through the points, release: a pointer stroke over the picture."""
        QTest.mousePress(self.win, Qt.LeftButton, Qt.NoModifier, self.layer_pt(*pts[0]))
        for a, b in zip(pts, pts[1:]):
            for k in range(1, 5):
                QTest.mouseMove(self.win, self.layer_pt(a[0] + (b[0] - a[0]) * k / 4, a[1] + (b[1] - a[1]) * k / 4))
        QTest.mouseRelease(self.win, Qt.LeftButton, Qt.NoModifier, self.layer_pt(*pts[-1]))

    def type_text(self, text, key=None):
        """Typed characters, through the same window and event filter as a keyboard's."""
        for ch in text:
            code = key or (ord(ch.upper()) if ch.isalpha() else 0)
            for t in (QEvent.KeyPress, QEvent.KeyRelease):
                QGuiApplication.sendEvent(self.win, QKeyEvent(t, code, Qt.NoModifier, 0, 0, 0, ch))

    @staticmethod
    def score(a, b, x, y, r=2):
        """How much picture b differs from a around (x, y): the largest mean channel
        difference in a small square (a line can sit a pixel off)."""
        best = 0
        for yy in range(int(y) - r, int(y) + r + 1):
            for xx in range(int(x) - r, int(x) + r + 1):
                if 0 <= xx < min(a.width(), b.width()) and 0 <= yy < min(a.height(), b.height()):
                    p, q = a.pixelColor(xx, yy), b.pixelColor(xx, yy)
                    best = max(best, (abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())) / 3)
        return best

    def rect_points(self, x0, y0, x1, y1):
        """Points on a rectangle's outline, and inside it away from the outline."""
        edge = [(x0 + (x1 - x0) * f, y0) for f in (.25, .5, .75)] + [(x0, y0 + (y1 - y0) * f) for f in (.3, .7)] \
            + [(x1, y0 + (y1 - y0) * .5), (x0 + (x1 - x0) * .5, y1)]
        inside = [(x0 + (x1 - x0) * f, y0 + (y1 - y0) * g) for f, g in ((.3, .3), (.5, .5), (.7, .6))]
        return edge, inside

    def screen_scores(self, before, after, pts):
        dpr = self.win.devicePixelRatio()
        return [round(self.score(before, after, self.layer_pt(*p).x() * dpr, self.layer_pt(*p).y() * dpr)) for p in pts]

    def s_dr_open(self):
        self.ed.frags = []
        self.p.mpv.pause = True
        self.p.seek(12.0)
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))

    def s_dr_key(self):
        self.key("E", Qt.ControlModifier)

    def s_dr_opened(self):
        layer = self.find_item("noteLayer")
        side = self.win.property("sideW")
        aw, ah = self.win.width() - side, self.win.height() - self.win.property("titleH") - self.win.property("panelH")
        s = min(aw / 640, ah / 360)
        want = ((aw - 640 * s) / 2, self.win.property("titleH") + (ah - 360 * s) / 2, 640 * s, 360 * s)
        got = (layer.x(), layer.y(), layer.width(), layer.height())
        log.info("osd-dimensions %s", self.p._state["osd"])
        self.check("drawing tools shown; the drawing layer lies exactly over the picture",
                   self.find_item("drawBar").isVisible() and all(abs(g - w) <= 2 for g, w in zip(got, want)),
                   f"layer={tuple(round(v) for v in got)} picture={tuple(round(v) for v in want)}")
        self.bare = capture(int(self.win.winId()))

    def s_dr_rect_done(self):
        n = self.ed.notes[0] if self.ed.notes else {}
        pts = [[round(v, 2) for v in p] for p in n.get("pts", [])]
        self.check("rectangle tool: a drag makes a rectangle on this file, on screen from now for 4 s",
                   len(self.ed.notes) == 1 and n["kind"] == "rect" and Path(n["path"]).name == "test_long.mkv"
                   and abs(n["a"] - 13.0) < 0.05 and abs(n["b"] - 17.0) < 0.05 and pts == [[0.2, 0.2], [0.5, 0.5]],
                   f"note={n.get('kind')} {n.get('a', 0):.2f}-{n.get('b', 0):.2f} pts={pts}")
        edge, inside = self.rect_points(0.2, 0.2, 0.5, 0.5)
        now = capture(int(self.win.winId()))
        e, i = self.screen_scores(self.bare, now, edge), self.screen_scores(self.bare, now, inside)
        self.check("the rectangle is drawn on the picture: its outline changed, inside did not",
                   min(e) > 40 and max(i) < 10, f"outline={e} inside={i}")

    def s_dr_typed(self):
        kinds = [n["kind"] for n in self.ed.notes]
        text = next((n["text"] for n in self.ed.notes if n["kind"] == "text"), None)
        self.check("arrow, pencil and typed text are added", kinds == ["rect", "arrow", "pen", "text"] and text == CYRILLIC,
                   f"kinds={kinds} text={text!r} pen points={len(self.ed.notes[2]['pts']) if len(kinds) > 2 else 0}")
        self.shot("24_drawings")

    def s_dr_undone(self):
        kinds = [n["kind"] for n in self.ed.notes]
        self.check("Ctrl+Z takes the typed text drawing away in one step", kinds == ["rect", "arrow", "pen"],
                   f"kinds={kinds}")

    def s_dr_redone(self):
        kinds = [n["kind"] for n in self.ed.notes]
        text = next((n["text"] for n in self.ed.notes if n["kind"] == "text"), None)
        self.check("Ctrl+Y brings it back with its text", kinds == ["rect", "arrow", "pen", "text"] and text == CYRILLIC,
                   f"kinds={kinds} text={text!r}")

    def s_dr_selected(self):
        self.check("pick tool: a click on the rectangle chooses it", self.ed.noteSel == 0, f"noteSel={self.ed.noteSel}")

    def s_dr_range(self):
        bar = self.find_item("noteBar0")
        lane_w = bar.parentItem().width()
        self.range_px = 2.0 / self.st("duration") * lane_w        # two seconds longer
        a = bar.mapToScene(QPointF(bar.width() - 1, bar.height() / 2))
        QTest.mousePress(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(round(a.x()), round(a.y())))
        for k in range(1, 6):
            QTest.mouseMove(self.win, QPoint(round(a.x() + self.range_px * k / 5), round(a.y())))
        QTest.mouseRelease(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(round(a.x() + self.range_px), round(a.y())))

    def s_dr_ranged(self):
        n = self.ed.notes[0]
        self.check("dragging the end of its bar on the timeline lengthens its interval",
                   abs(n["a"] - 13.0) < 0.05 and abs(n["b"] - 19.0) < 0.4, f"interval={n['a']:.2f}-{n['b']:.2f}")
        self.shot("25_drawing_interval")

    def s_dr_away(self):
        self.ed.selectNote(-1)
        self.p.seek(21.0)          # after every drawing's interval
        # off the bar the drag ended on: a bar under the pointer shows its drawing, faded (fb2)
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))

    def s_dr_outside(self):
        layer = self.find_item("noteLayer")
        self.away_shown = layer.property("shownKey")
        self.with_layer = capture(int(self.win.winId()))
        layer.setOpacity(0)

    def s_dr_outside_cmp(self):
        without = capture(int(self.win.winId()))
        self.find_item("noteLayer").setOpacity(1)
        changed = sum(1 for y in range(40, without.height() - 160, 3) for x in range(0, without.width() - 330, 3)
                      if self.with_layer.pixel(x, y) != without.pixel(x, y))
        self.check("outside their intervals the drawings are not on screen", self.away_shown == "" and changed == 0,
                   f"shown={self.away_shown!r} changed pixels={changed}")

    def s_dr_deleted(self):
        kinds = [n["kind"] for n in self.ed.notes]
        self.check("click a drawing + Delete removes it, the fragment stays", kinds == ["rect", "arrow", "text"]
                   and len(self.ed.frags) == 1, f"kinds={kinds} fragments={len(self.ed.frags)}")

    def s_dr_moved(self):
        pts = [[round(v, 2) for v in p] for p in self.ed.notes[0]["pts"]]
        self.check("dragging a drawing moves it", pts == [[0.25, 0.25], [0.55, 0.55]], f"pts={pts}")

    def s_dr_export(self):
        self.check("drawings over saved pictures: saving re-encodes", not self.ed.lossless and "drawings" in self.ed.note,
                   f"note={self.ed.note}")
        self.want = self.ed.total
        self.ed.exportTo(str(self.out / "edit_drawn.mp4"))

    def _frame(self, path, t, name):
        png = self.out / name
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t}", "-i", str(path), "-frames:v", "1", str(png)],
                       creationflags=subprocess.CREATE_NO_WINDOW)
        return QImage(str(png))

    @staticmethod
    def ink_distance(img, x, y, ink, r=2):
        """How far the closest pixel around (x, y) is from the ink colour (mean channel
        difference): a drawn line is near 0 even after the encoder blurs its colour a little."""
        best = 255
        for yy in range(int(y) - r, int(y) + r + 1):
            for xx in range(int(x) - r, int(x) + r + 1):
                if 0 <= xx < img.width() and 0 <= yy < img.height():
                    c = img.pixelColor(xx, yy)
                    best = min(best, (abs(c.red() - ink[0]) + abs(c.green() - ink[1]) + abs(c.blue() - ink[2])) / 3)
        return round(best)

    def s_dr_export_done(self):
        out = self.out / "edit_drawn.mp4"
        self._out_check("saved with drawings: length = sum of fragments", out, self.want)
        # The first fragment starts at 12.0 s of the file, so the saved 4.0 s is the file's
        # 16.0 s (rectangle on screen 13-19 s) and the saved 9.0 s its 21.0 s (none). The
        # test picture moves, so the check is the rectangle's own orange along its outline,
        # all of it at 4 s, and not at 9 s or inside it (a moving stripe may pass one point).
        on, off = self._frame(out, 4.0, "drawn_4s.png"), self._frame(out, 9.0, "drawn_9s.png")
        x0, y0, x1, y1 = (v for p in self.ed.notes[0]["pts"] for v in p)
        edge, inside = self.rect_points(x0, y0, x1, y1)
        orange = (0xF2, 0x6A, 0x21)

        def dist(img, pts):
            return [self.ink_distance(img, x * img.width(), y * img.height(), orange) for x, y in pts]
        e_on, i_on, e_off = dist(on, edge), dist(on, inside), dist(off, edge)
        self.check("the saved file has the rectangle where it was drawn, and only in its interval",
                   # drawn outline measured ≤ 31 from orange, the test picture's nearest (yellow) 63
                   max(e_on) < 45 and sum(d < 45 for d in i_on) <= 1 and sum(d < 45 for d in e_off) <= 1,
                   f"distance to orange: outline at 4 s={e_on} inside={i_on} outline at 9 s={e_off}")

    def s_dr_closed(self):
        self.check("Esc closes the editor; drawings and fragments stay for next time",
                   not self.ed.active and len(self.ed.notes) == 3 and len(self.ed.frags) == 1
                   and not self.find_item("noteLayer").isVisible() and not self.find_item("drawBar").isVisible())

    # ---- ideas: frame preview, A-B repeat, tracks and volume per file
    def rail_pt(self, frac):
        rail = self.find_item("seekRail")
        c = rail.mapToScene(QPointF(frac * rail.width(), rail.height() / 2))
        return QPoint(round(c.x()), round(c.y()))

    def region(self, img, item):
        """The part of a window capture an item covers."""
        dpr = self.win.devicePixelRatio()
        c = item.mapToScene(QPointF(0, 0))
        return img.copy(QRect(round(c.x() * dpr), round(c.y() * dpr),
                              round(item.width() * dpr), round(item.height() * dpr)))

    @staticmethod
    def closer(img, right, wrong, step=2):
        """Where two reference frames clearly differ (the test picture is mostly still): how far
        img is from the right one and from the wrong one there (mean channel difference)."""
        def dist(p, q):
            return abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())
        d_right = d_wrong = n = 0
        for y in range(0, img.height(), step):
            for x in range(0, img.width(), step):
                r, w, p = right.pixelColor(x, y), wrong.pixelColor(x, y), img.pixelColor(x, y)
                if dist(r, w) > 90:
                    n += 1
                    d_right += dist(p, r)
                    d_wrong += dist(p, w)
        return d_right / max(1, 3 * n), d_wrong / max(1, 3 * n), n

    def pv_drops(self):
        return (self.p.mpv.frame_drop_count or 0) + (self.p.mpv.decoder_frame_drop_count or 0)

    def s_pv_start(self):
        self.p.mpv.pause = False
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))
        self.pv_path = self.st("path")
        self.pv_mark = (time.monotonic(), self.st("position"), self.pv_drops())

    def s_pv_control(self):
        self.pv_ctrl = self.pv_drops() - self.pv_mark[2]
        self.pv_mark = (time.monotonic(), self.st("position"), self.pv_drops())

    def s_pv_played(self):
        # measured before the test's own heavy work (ffmpeg, pixel loops) blocks this thread
        t0, pos0, drops0 = self.pv_mark
        elapsed, played, drops = time.monotonic() - t0, self.st("position") - pos0, self.pv_drops() - drops0
        self.check("the playing file plays on undisturbed while frames are previewed",
                   self.st("path") == self.pv_path and not self.st("paused") and played > elapsed - 0.3
                   and drops <= self.pv_ctrl, f"{played:.2f} s played in {elapsed:.2f} s, dropped frames {drops} "
                                              f"(the same time without the preview: {self.pv_ctrl})")

    def pv_frames(self, at):
        """The frame the preview holds and the frame on screen, both at the preview's size."""
        img = self.pv.provider.image
        screen = self.region(capture(int(self.win.winId())), self.find_item("seekPreviewFrame"))
        return img, screen.scaled(img.width(), img.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def pv_ref(self, at, img):
        return self._frame(self.pv_path, at, f"preview_{int(at)}s.png").scaled(
            img.width(), img.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def s_pv_shown(self):
        card, frame = self.find_item("seekPreview"), self.find_item("seekPreviewFrame")
        at = self.pv.frameTime
        self.check("hovering the seek bar shows a frame from there: the keyframe at or before the pointer",
                   card.isVisible() and frame.isVisible() and self.pv.path == self.pv_path and abs(at - 20.0) < 0.05,
                   f"card={card.isVisible()} frame={frame.isVisible()} file={Path(self.pv.path).name} frame at {at:.2f} s")
        self.pv20 = self.pv_frames(at)
        self.shot("26_preview")

    def s_pv_moved(self):
        at = self.pv.frameTime
        img60, screen60 = self.pv_frames(at)
        img20, screen20 = self.pv20
        ref20, ref60 = self.pv_ref(20.0, img20), self.pv_ref(60.0, img20)
        for name, im in (("pv20_preview", img20), ("pv20_screen", screen20), ("pv60_preview", img60),
                         ("pv60_screen", screen60)):
            im.save(str(self.out / f"{name}.png"))
        # each picture against the file's frames at 20 s and at 60 s (ffmpeg): far nearer its own
        dists = [self.closer(img20, ref20, ref60), self.closer(screen20, ref20, ref60),
                 self.closer(img60, ref60, ref20), self.closer(screen60, ref60, ref20)]
        self.check("the preview is the file's frame at that place, and it is what the screen shows",
                   abs(at - 60.0) < 0.05 and all(r < w / 3 and n > 200 for r, w, n in dists),
                   "distance to its own frame / to the other (pixels compared): 20 s preview, screen; 60 s preview, screen = "
                   + ", ".join(f"{r:.0f}/{w:.0f} ({n})" for r, w, n in dists))

    def s_pv_off(self):
        self.settings.set("preview", False)
        QTest.mouseMove(self.win, self.rail_pt(0.5))

    def s_pv_off_chk(self):
        self.check("with the setting off, hovering shows the time only",
                   self.find_item("seekPreview").isVisible() and not self.find_item("seekPreviewFrame").isVisible())
        self.settings.set("preview", True)
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))

    def s_ab_prep(self):
        self.p.mpv.pause = True
        self.p.seek(30.0)

    def s_ab_set(self):
        a, b = self.p.loopA, self.p.loopB
        self.check("\\ sets A, the next \\ sets B", abs(a - 30.0) < 0.1 and abs(b - 40.0) < 0.1, f"A={a:.2f} B={b:.2f}")
        self.ab_with = capture(int(self.win.winId()))
        for name in ("loopBand", "loopA", "loopB"):
            self.find_item(name).setOpacity(0)

    def s_ab_cmp(self):
        without = capture(int(self.win.winId()))
        for name in ("loopBand", "loopA", "loopB"):
            self.find_item(name).setOpacity(1)
        dpr, rail = self.win.devicePixelRatio(), self.find_item("seekRail")
        xa = self.find_item("loopA").mapToScene(QPointF(0, 0)).x()
        xb = self.find_item("loopB").mapToScene(QPointF(0, 0)).x()
        # the lettered flags rise 12 px above the rail
        top, bottom = rail.mapToScene(QPointF(0, -14)).y(), rail.mapToScene(QPointF(0, rail.height() + 3)).y()
        band = rail.mapToScene(QPointF(0, 1)).y()
        w, h = self.ab_with, without

        def changed(x0, x1, y0, y1):
            return sum(1 for y in range(round(y0 * dpr), round(y1 * dpr)) for x in range(round(x0 * dpr), round(x1 * dpr))
                       if w.pixel(x, y) != h.pixel(x, y))
        near_a, near_b = changed(xa - 2, xa + 10, top, bottom), changed(xb - 10, xb + 2, top, bottom)
        between = changed(xa + 12, xb - 12, band, band + 3)
        total = sum(1 for y in range(0, w.height(), 2) for x in range(0, w.width(), 2) if w.pixel(x, y) != h.pixel(x, y))
        inside = sum(1 for y in range(0, w.height(), 2) for x in range(0, w.width(), 2)
                     if top * dpr <= y < bottom * dpr and w.pixel(x, y) != h.pixel(x, y))
        self.check("A and B are marked on the seek bar, and the stretch between them; nothing else changes",
                   near_a > 8 and near_b > 8 and between > 8 and total == inside,
                   f"changed pixels: at A {near_a}, at B {near_b}, between {between}, outside the bar {total - inside}")
        self.p.mpv.pause = False

    def s_ab_looped(self):
        # 3.5 s from 38.5 s would be 42 s; with the repeat it went back to A
        self.check("playback repeats the stretch from A to B", not self.st("paused") and 30.0 <= self.st("position") < 38.4,
                   f"pos={self.st('position'):.2f}")

    def s_ab_off(self):
        self.check("the third \\ ends the repeat", self.p.loopA == -1 and self.p.loopB == -1,
                   f"A={self.p.loopA} B={self.p.loopB}")

    def s_ab_next_file(self):
        self.check("a new file starts with no A-B repeat of the old one",
                   Path(self.st("path")).name == Path(self.media).name and self.p.loopA == -1
                   and self.p.mpv["ab-loop-a"] == "no", f"A={self.p.mpv['ab-loop-a']}")

    def s_mem_prep(self):
        shutil.copy(Path(self.media).parent / "test_multi.mkv", self.out / "memory.mkv")
        shutil.copy(self.media, self.out / "memory2.mp4")
        self.pl.add([str(self.out / "memory.mkv")], True)

    def s_mem_change(self):
        self.mem_auto = (self.st("aid"), self.st("sid"))
        self.mem_vol0 = self.st("volume")
        self.key("/")
        self.key("/", Qt.ShiftModifier)

    def s_mem_leave(self):
        self.mem_path = self.st("path")
        self.mem_want = (self.st("aid"), self.st("sid"), self.st("volume"))
        self.check("in a file, / and Shift+/ switch sound and subtitles, Down lowers the volume",
                   self.mem_want[0] != self.mem_auto[0] and self.mem_want[1] != self.mem_auto[1]
                   and abs(self.mem_want[2] - (self.mem_vol0 - 10)) < 0.5,
                   f"tracks {self.mem_auto} -> {self.mem_want[:2]}, volume {self.mem_vol0} -> {self.mem_want[2]}")
        self.pl.add([str(self.out / "memory2.mp4")], True)

    def s_mem_other(self):
        self.check("another file gets its own tracks and the volume just set",
                   self.st("aid") == 1 and abs(self.st("volume") - self.mem_want[2]) < 0.5,
                   f"aid={self.st('aid')} volume={self.st('volume')}")

    def s_mem_back(self):
        saved = json.loads((Path(os.environ["OY_HOME"]) / "positions.json").read_text(encoding="utf-8"))
        rec = saved.get(self.mem_path, {})
        now = (self.st("aid"), self.st("sid"), self.st("volume"))
        self.check("the file opens again with its sound track, subtitles and volume, kept on disk",
                   now[:2] == self.mem_want[:2] and abs(now[2] - self.mem_want[2]) < 0.5
                   and (rec.get("aid"), rec.get("sid"), rec.get("volume")) == self.mem_want,
                   f"now={now} want={self.mem_want} saved={rec} (the other file was left at {self.p.general_volume})")
        self.shot("28_file_memory")

    def s_mem_off(self):
        self.settings.set("fileMemory", False)
        self.pl.add([str(self.out / "memory2.mp4")], True)

    def s_mem_off_back(self):
        self.mem_vol_off = self.st("volume")      # louder than memory.mkv was left at
        self.pl.add([str(self.out / "memory.mkv")], True)

    def s_mem_off_chk(self):
        self.check("with the setting off, the file opens with mpv's choice and the current volume",
                   self.st("aid") == self.mem_auto[0] and abs(self.st("volume") - self.mem_vol_off) < 0.5,
                   f"aid={self.st('aid')} volume={self.st('volume')} (before {self.mem_vol_off})")
        self.settings.set("fileMemory", True)

    # ---- M8
    def find_text(self, text, item=None):
        """A visible Text whose words start with `text` (menu rows have no names)."""
        item = item or self.win.contentItem()
        if item.isVisible() and str(item.property("text") or "").startswith(text) and \
                item.metaObject().className().startswith("QQuickText"):
            return item
        for child in item.childItems():
            hit = self.find_text(text, child)
            if hit is not None:
                return hit
        return None

    def name(self):
        return Path(self.st("path") or "").name

    def s_ser_prep(self):
        d = (self.out / "series").resolve()
        d.mkdir(exist_ok=True)
        src = Path(self.media).parent / "test_long.mkv"
        names = ["Show S01E00 Preview.mkv", "Show S01E01.mkv", "Show S01E02.mkv", "Show S01E03.mkv", CYRILLIC + ".mkv"]
        for n in names:
            try:
                os.link(src, d / n)
            except OSError:
                shutil.copy(src, d / n)
        self.ep = [str(d / n) for n in names[1:4]]
        self.settings.set("series", True)
        self.pl.add([self.ep[0]], True)

    def s_ser_added(self):
        paths = [i["path"] for i in self.pl.items]
        start = paths.index(self.ep[0]) if self.ep[0] in paths else -1
        self.check("an opened episode brings the next ones of its series, and only those",
                   start >= 0 and paths[start:] == self.ep and self.name() == "Show S01E01.mkv",
                   f"list ends with {[Path(p).name for p in paths[-4:]]}, playing {self.name()}")

    def s_skip_marked(self):
        b = self.m8["autoskip"].bands
        self.check("Alt+E and Shift+E mark the opening, and the seek bar shows it",
                   len(b) == 1 and abs(b[0][0] - 5.5) < 1 and abs(b[0][1] - 15.5) < 1, f"bands={b}")

    def s_skip_credits(self):
        self.check("Shift+O marks the credits and goes on to the next episode",
                   self.name() == "Show S01E02.mkv", f"playing {self.name()}, bands={self.m8['autoskip'].bands}")

    def s_skip_opening(self):
        pos = self.st("position")
        self.shot("m8_01_autoskip")
        self.check("in the next episode the opening is skipped (played from 4 s, jumped at 5.5 s)",
                   self.name() == "Show S01E02.mkv" and 15.0 <= pos < 19.0, f"pos={pos:.1f}")

    def s_skip_next(self):
        self.check("in the next episode the credits are skipped: the one after it plays",
                   self.name() == "Show S01E03.mkv", f"playing {self.name()} at {self.st('position'):.1f}")

    def s_skip_menu(self):
        rail = self.find_item("seekRail")
        c = rail.mapToScene(QPointF(rail.width() * 0.3, rail.height() / 2))
        QTest.mouseClick(self.win, Qt.RightButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_skip_menued(self):
        self.check("right click on the seek bar opens the menu for the opening and credits",
                   self.win.findChild(QObject, "skipMenu").property("visible") is True)
        self.shot("m8_02_skip_menu")
        self.key("Esc")

    def s_skip_off(self):
        self.check("Alt+O turns skipping off (the setting follows)",
                   self.settings["autoskip"] is False and self.m8["autoskip"].bands == [], f"setting={self.settings['autoskip']}")
        self.p.seek(4.0)

    def s_skip_off_chk(self):
        pos = self.st("position")
        self.check("with skipping off the opening plays", 5.0 <= pos < 8.0, f"pos={pos:.1f}")

    def s_hist_shown(self):
        names = [Path(e["path"]).name for e in self.m8["history"].entries]
        view = self.find_item("historyView")
        self.check("Ctrl+H shows the history: the files watched, newest first",
                   self.win.property("playlistShown") is True and view is not None and view.isVisible()
                   and names[:2] == ["Show S01E02.mkv", "Show S01E01.mkv"] and view.property("count") == len(names),
                   f"history={names[:4]} rows={view.property('count') if view else None}")
        self.shot("m8_03_history")
        c = view.mapToScene(QPointF(view.width() / 2, 60))      # the second row
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_hist_played(self):
        self.check("a double click in the history plays that file", self.name() == "Show S01E01.mkv", f"playing {self.name()}")

    def s_sch_open(self):
        self.sch = self.m8["scheduler"]
        self.sch.grace = 3                   # 30 s in use; a test waits 3
        self.click("keyScheduler")

    def s_sch_menu(self):
        self.check("the clock in the title bar opens the scheduler",
                   self.win.findChild(QObject, "schedMenu").property("visible") is True)
        self.shot("m8_04_scheduler")
        self.click_item(self.find_text("Shut down the computer"))

    def s_sch_when(self):
        self.click_item(self.find_text("After this file"))

    def s_sch_armed(self):
        self.check("picking what and when sets the scheduler going; the clock is lit",
                   self.sch.when == "file" and self.sch.action == "shutdown"
                   and self.win.findChild(QObject, "keyScheduler").property("latched") is True,
                   f"when={self.sch.when} action={self.sch.action} summary={self.sch.summary}")
        self.p.seek(self.st("duration") - 1.0)

    def s_sch_counting(self):
        banner = self.win.findChild(QObject, "powerBanner")
        self.check("at the end of the file a countdown to shutdown is shown",
                   self.sch.countdown > 0 and banner.property("visible") is True and self.sch.powered == [],
                   f"countdown={self.sch.countdown} pending={self.sch.pending}")
        self.shot("m8_05_power_banner")

    def s_sch_powered(self):
        self.check("after the countdown the computer would be shut down (recorded, not done)",
                   self.sch.powered == ["shutdown"] and self.sch.countdown == 0 and self.sch.when == ""
                   and self.win.findChild(QObject, "powerBanner").property("visible") is False,
                   f"powered={self.sch.powered}")

    def s_sch_cancel_prep(self):
        self.sch.setAction("sleep")
        self.sch.arm("file", 0)
        self.p.seek(self.st("duration") - 1.0)
        self.p.mpv.pause = False            # keep-open paused it at the end

    def s_sch_cancel_click(self):
        self.cancel_seen = self.sch.countdown > 0 and self.sch.pending == "sleep"
        self.click("powerCancel")

    def s_sch_cancelled(self):
        self.check("the countdown's button cancels sleep", self.cancel_seen and self.sch.powered == ["shutdown"]
                   and self.sch.countdown == 0, f"powered={self.sch.powered}")

    def s_sch_timer(self):
        self.p.seek(10.0)
        self.p.mpv.pause = False
        self.sch.setAction("pause")
        self.sch.arm("timer", 0.03)          # 1.8 s

    def s_sch_timer_chk(self):
        self.check("in N minutes: the timer pauses playback", self.st("paused") is True and self.sch.when == ""
                   and self.st("position") < self.st("duration") - 2,
                   f"paused={self.st('paused')} at {self.st('position'):.1f} when={self.sch.when}")
        self.p.mpv.pause = False

    def s_sch_list_end(self):
        self.settings.set("onListEnd", "shutdown")
        while self.pl.repeat != 0:
            self.pl.cycleRepeat()
        if self.pl.shuffle:
            self.pl.toggleShuffle()
        self.pl.add([self.media], True)      # 20 s, the list's last row

    def s_sch_list_counting(self):
        self.list_count = (self.sch.countdown, self.sch.pending)

    def s_sch_list_powered(self):
        self.check("the setting 'when the list has played: shut down' counts down and would shut down",
                   self.list_count[0] > 0 and self.list_count[1] == "shutdown" and self.sch.powered == ["shutdown", "shutdown"],
                   f"countdown seen={self.list_count} powered={self.sch.powered}")
        self.settings.set("onListEnd", "stop")

    def s_radio_prep(self):
        from .radio import write_lau
        mp3 = self.out / "radio_src.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                        "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)], timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        self.icy = start_icy(mp3.read_bytes())
        rdir = self.out / "radio"
        rdir.mkdir(exist_ok=True)
        self.station = f"http://127.0.0.1:{self.icy.server_port}/stream"
        write_lau(rdir, CYRILLIC + " radio", self.station)
        self.settings.set("radioDir", str(rdir))
        self.settings.set("radioRecDir", str(self.out / "rec"))

    def s_radio_listed(self):
        view = self.find_item("radioView")
        panel = self.win.findChild(QObject, "playlistPanel")
        self.check("Ctrl+F2 shows the radio page with the station from its .lau file",
                   panel.property("tab") == 2 and view.property("count") == 1, f"rows={view.property('count')}")
        c = view.mapToScene(QPointF(view.width() / 2, 19))
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_radio_playing(self):
        r = self.m8["radio"]
        self.check("a double click plays the station; what it announces is shown",
                   self.st("path") == self.station and r.streaming and r.nowPlaying == "oy test - track 1"
                   and self.st("position") > 0.5,
                   f"path={self.st('path')} now={r.nowPlaying!r} pos={self.st('position'):.1f}")
        self.shot("m8_06_radio")

    def s_radio_recorded(self):
        files = list((self.out / "rec").glob("*")) if (self.out / "rec").is_dir() else []
        info = ffprobe(files[0]) if len(files) == 1 else {}
        st = (info.get("streams") or [{}])[0]
        dur = float(info.get("format", {}).get("duration", 0))
        self.check("the record key writes the stream to a file, as it came (MP3)",
                   len(files) == 1 and st.get("codec_name") == "mp3" and dur >= 2.0
                   and files[0].name.startswith(CYRILLIC + " radio ") and not self.m8["radio"].recording,
                   f"files={[f.name for f in files]} codec={st.get('codec_name')} dur={dur:.1f}")

    def s_inst_send(self):
        handed = self.out / "handed.mp4"
        shutil.copy(self.media, handed)
        self.handed = str(handed.resolve())
        if getattr(sys, "frozen", False):
            cmd, cwd = [sys.executable, self.handed], None
        else:
            cmd, cwd = [sys.executable, "-m", "oyplayer", self.handed], str(Path(__file__).resolve().parents[1])
        # should it fail to hand over, its own window must not disturb either
        env = dict(os.environ, OY_SCREEN="3")
        self.inst_t0 = time.monotonic()
        self.inst_proc = subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=subprocess.CREATE_NO_WINDOW)

    def s_inst_done(self):
        code = self.inst_proc.poll()
        took = time.monotonic() - self.inst_t0 - 1.5
        if code is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.inst_proc.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        own_log = (Path(os.environ["OY_HOME"]) / "oyplayer.log").read_text(encoding="utf-8", errors="replace")
        playing = self.st("path") or ""
        self.check("a second start hands its file to the running player and leaves",
                   code == 0 and playing and Path(playing).resolve() == Path(self.handed)
                   and "placed on" in own_log.splitlines()[0],
                   f"exit={code} after about {took:.1f} s, playing {Path(playing).name}")

    def s_tray_on(self):
        self.settings.set("tray", "minimize")
        # a station row was clicked above: the list has the keys and End is its last row
        # (stage 3); End minimises once the keys are the commands' again
        self.win.setProperty("area", "")

    def s_tray_shown(self):
        t = self.m8["tray"]
        g = t.icon.geometry()
        self.check("the tray icon is shown", QSystemTrayIcon.isSystemTrayAvailable() and t.icon.isVisible(),
                   f"geometry={g.getRect()}")

    def s_tray_hidden(self):
        self.check("minimising hides the window into the tray", not self.win.isVisible(),
                   f"states={self.win.windowStates()} visibility={self.win.visibility()}")
        self.m8["tray"].icon.activated.emit(QSystemTrayIcon.Trigger)

    def s_tray_back(self):
        self.check("a click on the icon brings the window back",
                   self.win.isVisible() and not self.win.windowStates() & Qt.WindowMinimized)
        self.paused0 = self.st("paused")
        self.m8["tray"].icon.activated.emit(QSystemTrayIcon.MiddleClick)

    def s_tray_middle(self):
        self.check("the middle button on the icon pauses", self.st("paused") is (not self.paused0))
        self.settings.set("tray", "off")
        self.check("tray off takes the icon away", not self.m8["tray"].icon.isVisible())
        self.p.mpv.pause = False

    def s_media_prep(self):
        self.paused0 = self.p.mpv.pause      # mpv's own value: the mirror lags a turn behind a change

    def s_media_local(self):
        self.check("the media Play/Pause key pauses", self.p.mpv.pause is (not self.paused0))
        self.p.mpv.pause = False

    def s_media_global(self):
        self.settings.set("globalMedia", True)
        self.held = list(self.m8["keys"].held)
        self.paused0 = self.p.mpv.pause
        # what Windows sends when the key is pressed in another program
        ctypes.windll.user32.PostMessageW(int(self.win.winId()), 0x0312, 1, 0)

    def s_media_global_chk(self):
        toggled = self.p.mpv.pause is (not self.paused0)
        self.settings.set("globalMedia", False)
        self.check("with the setting, media keys reach the player from any program; off gives them back",
                   1 in self.held and toggled and self.m8["keys"].held == [],
                   f"held={self.held} toggled={toggled}")
        self.p.mpv.pause = False

    def _real_assoc(self):
        return (reg_exists(r"Software\Classes\OYPlayer.media"), reg_exists(r"Software\Classes\OYPlayer.radio"),
                reg_exists(r"Software\OYPlayer"), (reg_values(r"Software\RegisteredApplications") or {}).get("OY Player"),
                reg_values(r"Software\Classes\.mkv\OpenWithProgids"))

    def s_assoc_prep(self):
        from . import assoc
        self.assoc = assoc
        self.real0 = self._real_assoc()
        self.assoc_saved = (assoc.CLASSES, assoc.APP_KEY, assoc.REGISTERED)
        assoc.CLASSES, assoc.APP_KEY, assoc.REGISTERED = (SCRATCH + r"\Classes", SCRATCH + r"\App",
                                                          SCRATCH + r"\RegisteredApplications")
        self.key("F10")

    def s_assoc_nav(self):
        self.click_item(self.find_item("nav1"))

    def scroll_to(self, name):
        flick, item = self.find_item("settingsFlick"), self.find_item(name)
        y = item.mapToItem(flick.property("contentItem"), QPointF(0, 0)).y()
        flick.setProperty("contentY", max(0.0, min(y - 120, flick.property("contentHeight") - flick.height())))

    def s_assoc_shot(self):
        self.scroll_to("setAssocOn")

    def s_assoc_on(self):
        self.shot("m8_08_settings_windows")
        self.click_item(self.find_item("setAssocOn"))

    def s_assoc_registered(self):
        a = self.assoc
        cmd = reg_values(rf"{a.CLASSES}\OYPlayer.media\shell\open\command") or {}
        fa = reg_values(rf"{a.APP_KEY}\Capabilities\FileAssociations") or {}
        self.check("the button registers OY Player for video, audio and .lau (in a scratch key here)",
                   cmd.get("") == a.command() and "OYPlayer.media" in (reg_values(rf"{a.CLASSES}\.mkv\OpenWithProgids") or {})
                   and fa.get(".lau") == "OYPlayer.radio" and fa.get(".mp4") == "OYPlayer.media"
                   and (reg_values(a.REGISTERED) or {}).get("OY Player") == rf"{a.APP_KEY}\Capabilities"
                   and self.m8["info"].fileTypes is True,
                   f"types={len(fa)} command={cmd.get('', '')[:60]}")
        self.shot("m8_09_settings_registered")
        self.click_item(self.find_item("setAssocOff"))

    def s_assoc_removed(self):
        a = self.assoc
        gone = not reg_exists(rf"{a.CLASSES}\OYPlayer.media") and not reg_exists(a.APP_KEY) \
            and "OYPlayer.media" not in (reg_values(rf"{a.CLASSES}\.mkv\OpenWithProgids") or {}) \
            and "OY Player" not in (reg_values(a.REGISTERED) or {}) and self.m8["info"].fileTypes is False
        from .assoc import _delete_tree
        _delete_tree(SCRATCH)
        a.CLASSES, a.APP_KEY, a.REGISTERED = self.assoc_saved
        real = self._real_assoc()
        self.check("'Remove' takes it all back; the scratch key is deleted and the real file types are untouched",
                   gone and not reg_exists(SCRATCH) and real == self.real0, f"real before={self.real0} after={real}")

    def settings_page(self, n, name):
        self.click_item(self.find_item(f"nav{n}"))
        QTimer.singleShot(300, lambda: self.scroll_to(name))

    def s_about(self):
        self.win.findChild(QObject, "settingsPanel").setProperty("visible", True)
        QTimer.singleShot(200, lambda: self.click_item(self.find_item("nav6")))

    def s_about_shot(self):
        page = self.find_item("aboutPage")
        self.check("About is the settings' last section: what this is and its version; the title bar has no About key",
                   page is not None and page.isVisible() and self.find_item("keyAbout") is None)
        self.shot("m8_15_about")
        self.key("Esc")

    def s_finish(self):
        if self.icy:
            self.icy.stopping = True
            self.icy.shutdown()
        self.result = 1 if self.failures else 0
        line = f"SELFCHECK RESULT {'PASS' if not self.failures else 'FAIL'} run={self.run_name} failures={self.failures}"
        print(line, flush=True)
        log.info(line)          # the built program has no console: its log is where the result is read
        self.win.close()

    # ---- feedback 1 (the owner's look at the stable copy): the round keys' bevel, screenshot
    # colours, the time scale, the one colour and the editor's yellow, hints inside the window
    def fb1_steps(self):
        bars, full = str(self.out / "bars709.mp4"), str(self.out / "bars709full.mp4")
        long_mkv = str(Path(self.media).parent / "test_long.mkv")
        return [
            (0, self.s_fb_prep),
            # the time scale, on test720.mp4 (20 s) and test_long.mkv (90 s)
            (0, lambda: self.pl.add([self.media], True)), (1800, lambda: self.s_fb_scale(10)),
            (0, lambda: self.pl.add([long_mkv], True)), (1800, lambda: self.s_fb_scale(10)), (0, self.s_fb_ruler),
            # screenshot colours on SMPTE bars, limited range, then full range
            (0, lambda: self.pl.add([bars], True)), (1500, self.s_fb_bars_seek), (900, lambda: self.key("F12")),
            (900, lambda: self.s_fb_bars(bars, "limited")), (0, self.s_fb_caps),
            (0, lambda: self.pl.add([full], True)), (1500, self.s_fb_bars_seek), (900, lambda: self.key("F12")),
            (900, lambda: self.s_fb_bars(full, "full")),
            # every hint, whole inside the window
            (0, lambda: self.s_fb_tips("the panel and the title bar")),
            (0, lambda: self.s_fb_rclick("keySound")), (900, self.s_fb_tip_menu), (0, lambda: self.key("Esc")),
            (400, lambda: QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))),
            # the one colour: the settings' dial, then the panel; the editor turns it yellow
            (0, lambda: self.key("F10")), (700, lambda: self.click_item(self.find_item("nav1"))),
            (300, lambda: self.scroll_to("setAccent")), (400, self.s_fb_tune), (600, self.s_fb_tuned),
            (0, lambda: self.key("Esc")), (600, self.s_fb_accent_panel),
            (0, lambda: self.key("E", Qt.ControlModifier)), (900, self.s_fb_edit_yellow),
            (0, lambda: self.s_fb_tips("the editor's strip and drawing tools")),
            (0, lambda: self.settings.set("theme", "light")), (700, lambda: self.shot("fb1_07_edit_light")),
            (0, lambda: self.settings.set("theme", "dark")), (0, lambda: self.key("Esc")), (900, self.s_fb_edit_left),
            (0, lambda: self.settings.set("accent", "#F26A21")), (600, self.s_fb_accent_back),
        ]

    @staticmethod
    def oklch_of(c):
        """[L, C, h] of a QColor (OKLCH), the space the accent's shades are made in."""
        def lin(v):
            v /= 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = lin(c.red()), lin(c.green()), lin(c.blue())
        lc = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
        mc = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
        sc = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
        a = 1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc
        bb = 0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc
        return (0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc, math.hypot(a, bb),
                math.degrees(math.atan2(bb, a)) % 360)

    def scene_rect(self, item):
        dpr = self.win.devicePixelRatio()
        c = item.mapToScene(QPointF(0, 0))
        return c.x() * dpr, c.y() * dpr, item.width() * dpr, item.height() * dpr

    def s_fb_prep(self):
        QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))
        # SMPTE RP 219 bars, tagged BT.709: limited range (most video) and full range (screen captures)
        for name, pix, rng in (("bars709.mp4", "yuv420p", "tv"), ("bars709full.mp4", "yuvj420p", "pc")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "smptehdbars=size=1280x720:rate=25",
                            "-t", "3", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", pix,
                            "-colorspace", "bt709", "-color_range", rng, str(self.out / name)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def s_fb_scale(self, max_step):
        """The scale over the seek bar: labels at a constant round step, one format, each
        centred on its mark (or pushed in at an end), none overlapping or cut; minor ticks."""
        dur, marks = self.st("duration") or 0, self.find_item("scaleMarks")
        labels = sorted((it for it in marks.childItems() if it.objectName().startswith("scaleLabel")),
                        key=lambda it: int(it.objectName()[10:]))
        texts = [it.property("text") for it in labels]
        secs = [int(t[:2]) * 60 + int(t[3:]) for t in texts if re.fullmatch(r"\d\d:\d\d", t)]
        step = secs[1] - secs[0] if len(secs) > 1 else 0
        w, bad = marks.width(), []
        for i, it in enumerate(labels):
            x, lw = it.x(), it.width()
            mark = i * step / dur * w if dur else 0
            # centred on its mark; at an end it may stand half out into the panel's margin, or be pushed in
            if x < -lw / 2 - 1 or x + lw > w + lw / 2 + 1 or (abs(x + lw / 2 - mark) > 1 and x > 0.5 and x + lw < w - 0.5):
                bad.append(f"{texts[i]}@{x:.0f}")
            if i and x < labels[i - 1].x() + labels[i - 1].width() + 4:
                bad.append(f"{texts[i]} overlaps")
        # minor ticks on the screen: columns of the tick row that differ from the gap under it
        img = capture(int(self.win.winId()))
        mx, my, mw, _mh = self.scene_rect(marks)
        tick_row, gap_row = int(my + marks.height()) - 2, int(my + marks.height()) + 1
        cols = [x for x in range(int(mx), int(mx + mw)) if max(
            abs(a - b) for a, b in zip(img.pixelColor(x, tick_row).getRgb()[:3],
                                       img.pixelColor(x, gap_row).getRgb()[:3])) > 10]
        # a tick never runs into a label (the colon and a tick once read «;»): 2 px of air
        top = marks.property("tickTop")
        touching = [it.property("text") for it in labels if it.isVisible() and it.y() + it.height() > top - 2]
        ticks = len([x for i, x in enumerate(cols) if i == 0 or x - cols[i - 1] > 1])
        ok = (len(secs) == len(texts) >= 5 and 0 < step <= max_step and not bad and not touching
              and secs == [i * step for i in range(len(secs))] and ticks > 2 * len(texts))
        self.check(f"the time scale of a {dur:.0f} s file: a label every {step} s, one format, none cut, overlapping or touching a tick, minor ticks between",
                   ok, f"labels={len(texts)} {texts[:3]}…{texts[-2:]} ticks on screen={ticks} bad={bad} touching={touching}")
        self.shot(f"fb1_02_scale_{dur:.0f}s")

    def s_fb_ruler(self):
        """The step adapts to the file's length, at the width of the owner's window
        (1280 px; the scale is 28 px narrower): 30 s on 3:40, labels three labels' width apart."""
        tl, w, out = self.find_item("timeline"), 1252.0, {}
        for dur, lw in ((220, 28), (1800, 28), (7200, 38)):
            r = QMetaObject.invokeMethod(tl, "rulerFor", Qt.DirectConnection, Q_RETURN_ARG("QVariant"),
                                         Q_ARG("QVariant", float(dur)), Q_ARG("QVariant", float(w)), Q_ARG("QVariant", lw))
            out[dur] = (r.property("step").toInt(), r.property("minor").toInt())
        gap = {d: s * w / d for d, (s, _m) in out.items()}
        self.check("on longer files the scale steps out: 30 s on 3:40, 5 minutes on half an hour, a quarter of an hour on two hours",
                   out[220][0] == 30 and out[1800][0] == 300 and 600 <= out[7200][0] <= 900
                   and all(90 <= g <= 260 for g in gap.values()),
                   f"width={w:.0f} (step, minor)={out} px between labels={ {d: round(g) for d, g in gap.items()} }")

    def s_fb_bars_seek(self):
        self.p.mpv.pause = True
        self.p.mpv.command("seek", 1, "absolute+exact")

    def s_fb_bars(self, clip, rng):
        """The F12 file and the window against ffmpeg's BT.709 decode of the same frame."""
        shots = Path(os.environ["OY_SHOTS"])
        shot = max((f for f in shots.glob(Path(clip).stem + "_*.png")), key=lambda f: f.stat().st_mtime, default=None)
        ref_png = self.out / (Path(clip).stem + "_ref.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", clip, "-frames:v", "1", "-vf",
                        f"scale=in_color_matrix=bt709:in_range={'pc' if rng == 'full' else 'tv'}:out_range=pc,format=rgb24",
                        str(ref_png)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        ref, win = QImage(str(ref_png)), capture(int(self.win.winId()))
        d = self.p._state["osd"] or {}
        k = win.width() / d["w"] if d.get("w") else 1
        px, py = d.get("ml", 0) * k, d.get("mt", 0) * k
        pw, ph = (d.get("w", 0) - d.get("ml", 0) - d.get("mr", 0)) * k, (d.get("h", 0) - d.get("mt", 0) - d.get("mb", 0)) * k
        # the 40 % grey, the seven 75 % bars, black and white of the bottom row
        pts = [(0.06, 0.3)] + [(0.125 + (i + 0.5) * 0.75 / 7, 0.3) for i in range(7)] + [(0.3, 0.92), (0.6, 0.92)]

        def at(img, x0, y0, w, h):
            out = []
            for fx, fy in pts:
                acc = [0, 0, 0]
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        c = img.pixelColor(int(x0 + fx * w) + dx, int(y0 + fy * h) + dy)
                        acc = [acc[0] + c.red(), acc[1] + c.green(), acc[2] + c.blue()]
                out.append(tuple(round(v / 25) for v in acc))
            return out

        def diff(a, b):
            return max(abs(p - q) for u, v in zip(a, b) for p, q in zip(u, v))
        r = at(ref, 0, 0, ref.width(), ref.height())
        f = at(QImage(str(shot)), 0, 0, ref.width(), ref.height()) if shot else []
        s = at(win, px, py, pw, ph)
        chunks = []
        if shot:
            data, pos = shot.read_bytes(), 8
            while pos < len(data):
                n, typ = struct.unpack(">I4s", data[pos:pos + 8])
                chunks.append(typ.decode())
                pos += 12 + n
        if rng == "limited":
            self.check("a screenshot carries no colour tags, so viewers show it as the window does (no cICP, gAMA, cHRM)",
                       shot is not None and not set(chunks) & {"cICP", "gAMA", "cHRM", "sRGB", "iCCP"}, f"chunks={chunks}")
        self.check(f"the screenshot has the frame's colours (ffmpeg BT.709), {rng} range",
                   bool(f) and diff(f, r) <= 4, f"max difference={diff(f, r) if f else '-'} grey40 ref={r[0]} file={f[0] if f else '-'}")
        self.check(f"the window shows the same colours, {rng} range", diff(s, r) <= 4,
                   f"max difference={diff(s, r)} cyan ref={r[3]} window={s[3]}")
        if rng == "limited":
            self.shot("fb1_03_bars")

    def s_fb_caps(self):
        """The round keys' bevel stays inside the circle: row by row, what is drawn over the panel
        is no wider than the circle there (the straight line of before was 20 px against 15)."""
        img, bad = capture(int(self.win.winId())), []
        for name in ("keyPlay", "keyPlaylist"):
            x0, y0, w, _h = self.scene_rect(self.find_item(name))
            r, cx = w / 2, x0 + w / 2
            for row in range(6):
                y = int(y0) + row
                bg = img.pixelColor(int(x0) - 8, y).getRgb()[:3]
                # what is lighter than the panel there: the cap and its light (its shadow is darker)
                xs = [x for x in range(int(x0) - 2, int(x0 + w) + 2)
                      if sum(img.pixelColor(x, y).getRgb()[:3]) - sum(bg) > 18]
                # a filled, smoothed circle touches a row as wide as its chord at the row's lower edge
                chord = 2 * math.sqrt(max(0.0, r * r - (r - row - 1) ** 2))
                if xs and xs[-1] - xs[0] + 1 > chord + 1.5:
                    bad.append(f"{name} row {row}: {xs[-1] - xs[0] + 1} px > circle {chord:.1f}")
        self.check("the light on the round keys follows the rim and does not stick out", not bad, f"{bad}")

    def tip_keys(self, item=None, out=None):
        """Everything visible with a hint of its own (key caps, title-bar buttons)."""
        item, out = item or self.win.contentItem(), [] if out is None else out
        if not item.isVisible() or item.opacity() < 0.5:
            return out
        tip = item.property("tip")
        if isinstance(tip, str) and tip and item.isEnabled():
            out.append(item)
        for child in item.childItems():
            self.tip_keys(child, out)
        return out

    def s_fb_tips(self, where):
        keys, self.tips_bad, self.tips_seen = self.tip_keys(), [], 0
        seq = []
        for k in keys:
            seq += [(0, lambda k=k: QTest.mouseMove(self.win, self.center_of(k))), (700, lambda k=k: self.s_fb_tip(k))]
        seq += [(0, lambda: QTest.mouseMove(self.win, QPoint(self.win.width() // 2, self.win.height() // 3))),
                (300, lambda: self.check(f"every hint of {where} shows whole inside the window ({len(keys)} keys)",
                                         self.tips_seen == len(keys) >= 10 and not self.tips_bad,
                                         f"shown={self.tips_seen} bad={self.tips_bad}"))]
        self.steps[0:0] = seq

    def center_of(self, item):
        c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        return QPoint(round(c.x()), round(c.y()))

    def visible_tips(self, item=None, out=None):
        item, out = item or self.win.contentItem(), [] if out is None else out
        if item.objectName() == "tip" and item.isVisible() and item.opacity() > 0.9:
            out.append(item)
        for child in item.childItems():
            self.visible_tips(child, out)
        return out

    def s_fb_rclick(self, name):
        pt = self.center_of(self.find_item(name))
        QTest.mouseMove(self.win, pt)
        QTest.mouseClick(self.win, Qt.RightButton, Qt.NoModifier, pt)

    def s_fb_tip_menu(self):
        """The pointer stays on the key whose menu it opened: its hint must not cover the menu."""
        menu, tips = self.win.findChild(QObject, "audioMenu"), self.visible_tips()
        self.check("a key's hint does not lie over the menu the key opened",
                   menu is not None and menu.property("visible") is True and not tips,
                   f"menu open={menu.property('visible') if menu else None} hints shown={[t.property('text') for t in tips]}")
        self.shot("fb1_09_menu_no_hint")

    def s_fb_tip(self, key):
        tips, want = self.visible_tips(), key.property("tip")
        if len(tips) != 1 or tips[0].property("text") != want:
            self.tips_bad.append(f"{want!r}: {[t.property('text') for t in tips]}")
            return
        self.tips_seen += 1
        t = tips[0]
        c = t.mapToScene(QPointF(0, 0))
        text = t.property("text")
        if c.x() < 0 or c.y() < 0 or c.x() + t.width() > self.win.width() or c.y() + t.height() > self.win.height() \
                or not text.strip() or "undefined" in text or "NaN" in text:
            self.tips_bad.append(f"{text!r} at {c.x():.0f},{c.y():.0f} {t.width():.0f}x{t.height():.0f}")
        if key.objectName() == "keyAbout":
            self.shot("fb1_04_tip_about")
        if key.objectName() == "editSave":
            self.shot("fb1_08_tip_edit")

    def s_fb_tune(self):
        """A click on the dial at the green station, as a person tunes it."""
        glass = self.find_item("accentGlass")
        self.accent0 = self.settings["accent"]
        c = glass.mapToScene(QPointF(10 + 4.5 / 10 * (glass.width() - 20), glass.height() / 2))
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(round(c.x()), round(c.y())))

    def s_fb_tuned(self):
        hue = self.oklch_of(QColor(self.settings["accent"]))[2]
        self.check("the dial tunes the player's colour: a click near the green station settles on it",
                   self.accent0 == "#F26A21" and abs(hue - 142) < 3, f"accent {self.accent0} -> {self.settings['accent']} hue={hue:.1f}")
        # what is printed on the dial: names whole inside the glass, apart in their row; the needle on green
        glass = self.find_item("accentGlass")
        names = [(it.x(), it.y(), it.width(), it.property("text")) for it in glass.childItems()
                 if it.objectName().startswith("accentStation")]
        bad = [n[3] for n in names if n[0] < 0 or n[0] + n[2] > glass.width()]
        bad += [f"{a[3]}/{b[3]}" for i, a in enumerate(names) for b in names[i + 1:]
                if a[1] == b[1] and a[0] < b[0] + b[2] + 4 and b[0] < a[0] + a[2] + 4]
        needle = next(it for it in glass.childItems() if it.objectName() == "accentNeedle")
        want = 10 + 4.5 / 10 * (glass.width() - 20)
        self.check("the dial's names are whole and apart, and its needle stands on the chosen station",
                   len(names) == 10 and not bad and abs(needle.x() + 1 - want) <= 2,
                   f"needle at {needle.x() + 1:.0f}, green station at {want:.0f}; bad={bad}")
        self.shot("fb1_05_accent_dial")

    def chrome_hues(self, img):
        """Hues of the strongly coloured pixels of the title bar and the panel (not the picture)."""
        hues, titleH, panelH = [], 32, self.win.property("panelH")
        dpr = self.win.devicePixelRatio()
        rows = list(range(0, int(titleH * dpr))) + list(range(int(img.height() - panelH * dpr), img.height()))
        for y in rows[::2]:
            for x in range(0, img.width(), 2):
                L, C, h = self.oklch_of(img.pixelColor(x, y))
                if C > 0.1 and L > 0.45:
                    hues.append(h)
        return hues

    def key_hue(self, img, name="keyPlay"):
        x0, y0, w, h = self.scene_rect(self.find_item(name))
        return self.oklch_of(img.pixelColor(int(x0 + w / 2), int(y0 + h * 0.82)))

    def s_fb_accent_panel(self):
        img = capture(int(self.win.winId()))
        hues, key = self.chrome_hues(img), self.key_hue(img)
        orange = sum(1 for h in hues if 30 <= h <= 62)
        green = sum(1 for h in hues if 125 <= h <= 160)
        self.check("the whole panel takes the colour: the play key, the seek bar and the volume are green, nothing is orange",
                   abs(key[2] - 142) < 10 and orange == 0 and green > 200,
                   f"play key hue={key[2]:.0f} green pixels={green} orange={orange}")
        self.shot("fb1_01_green")

    def s_fb_edit_yellow(self):
        img = capture(int(self.win.winId()))
        hues, key = self.chrome_hues(img), self.key_hue(img, "editPlay")      # the editor's own row
        green = sum(1 for h in hues if 125 <= h <= 160)
        yellow = sum(1 for h in hues if 75 <= h <= 100)
        self.check("the editor turns the colour yellow: the play key, the seek bar, the strip; no green left",
                   # a few: ClearType's coloured fringes on the title's letters (native text), not a key
                   self.ed.active and 80 <= key[2] <= 98 and green < 40 and yellow > 200,
                   f"play key hue={key[2]:.0f} yellow pixels={yellow} green={green}")
        self.shot("fb1_06_edit_yellow")

    def s_fb_edit_left(self):
        key = self.key_hue(capture(int(self.win.winId())))
        self.check("leaving the editor brings the player's own colour back", not self.ed.active and abs(key[2] - 142) < 10,
                   f"play key hue={key[2]:.0f}")

    def s_fb_accent_back(self):
        key = self.key_hue(capture(int(self.win.winId())))
        self.check("the orange station gives back the original orange", abs(key[2] - 44) < 6, f"play key hue={key[2]:.0f}")

    # ---- feedback 2: the UI/UX council's stage 1 (states that tell the truth, menus on the
    # keyboard, one selection in the editor) and stage 2 (the drawings' tracks on the timeline)
    FILE_KEYS = ("keyShot", "keyEdit")

    def fb2_steps(self):
        folder = Path(self.media).parent
        long_mkv, multi = str(folder / "test_long.mkv"), str(folder / "test_multi.mkv")

        def key(name, mods=Qt.NoModifier):
            return lambda: self.key(name, mods)

        def seek(t):
            return lambda: self.p.seek(t)

        def ui(name):
            return lambda: self.click(name)

        def draw(pts):
            return lambda: self.drag(pts)
        return [
            # no file: «play» on the play key, and the keys that need a file are off. mpv is not
            # paused when nothing is loaded (as at start), so the file is stopped while playing.
            (0, self.park), (0, lambda: setattr(self.p.mpv, "pause", True)), (600, self.s_fb2_with_file),
            (0, lambda: setattr(self.p.mpv, "pause", False)), (300, lambda: self.p.mpv.command("stop")),
            (900, self.s_fb2_no_file),
            # the subtitles key is lit only while a track is shown
            (0, lambda: self.pl.add([long_mkv], True)), (1800, lambda: self.s_fb2_subs("a file without subtitles", False)),
            (0, lambda: self.pl.add([multi], True)), (1800, self.s_fb2_subs_pick),
            (600, lambda: self.s_fb2_subs("a subtitle track shown", True)),
            # an open menu takes the arrows and Enter: nothing changes under it
            (0, self.s_fb2_menu_open), (600, self.s_fb2_menu_prep), (200, key("Down")), (200, key("Down")),
            (200, key("Up")), (200, key("Right")), (500, self.s_fb2_menu_keys), (0, key("Enter")),
            (600, self.s_fb2_menu_enter),
            # Esc in fullscreen: the menu first, then fullscreen; the panels stay while a menu is open
            (0, key("Enter")), (900, key("S", Qt.AltModifier)), (0, self.park), (3300, self.s_fb2_fs_menu),
            # (the second Esc only in fullscreen: out of it, Esc would close the player and end the run)
            (0, key("Esc")), (600, self.s_fb2_fs_esc), (0, lambda: self.win.property("fs") and self.key("Esc")),
            (900, self.s_fb2_fs_left),
            # the editor: three fragments of test_long.mkv; after O the last one is chosen
            (0, lambda: self.pl.add([long_mkv], True)), (1800, self.s_fb2_ed_prep), (0, key("E", Qt.ControlModifier)),
            (700, lambda: None)] + self.keep_steps([(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]) + [
            (0, lambda: self.ed.select(2)),
            # the edit's preview starts at the first fragment, from its key and from Shift+Space ...
            (300, ui("editPreview")), (800, lambda: self.s_fb2_preview("the preview key", 0)),
            (0, key("Space", Qt.ShiftModifier)), (400, key("Space", Qt.ShiftModifier)),
            (800, lambda: self.s_fb2_preview("Shift+Space", 0)), (0, key("Space", Qt.ShiftModifier)),
            # ... and a click on a fragment, then Space, plays the edit from that fragment
            (400, lambda: self.click_item(self.find_item("frag1"))), (600, key("Space")),
            (800, lambda: self.s_fb2_preview("a click on the second fragment, then Space,", 1)),
            (0, key("Space", Qt.ShiftModifier)),
            # the playlist's «−» takes out a playlist row, also while the editor is open
            (300, lambda: self.show_list(True)), (700, self.s_fb2_minus), (500, self.s_fb2_minus_done),
            (0, lambda: self.show_list(False)),
            # a drawing over a fragment: saving cannot copy; the strip says so, and why
            (300, seek(15.0)), (600, ui("drawRect")), (300, draw([(0.1, 0.15), (0.2, 0.25), (0.3, 0.35)])),
            (300, ui("drawSelect")), (500, self.s_fb2_reason), (0, self.s_fb2_reason_click), (500, self.s_fb2_reason_kept),
            # the chosen ink's ring is neutral, not the editor's yellow
            (0, self.s_fb2_ring),
            # one selection: a drawing or a fragment; Delete takes out the one chosen
            (0, lambda: self.click_layer(0.2, 0.15)), (400, self.s_fb2_sel_note),
            (0, lambda: self.click_item(self.find_item("frag0"))), (400, self.s_fb2_sel_frag),
            (0, key("Delete")), (400, self.s_fb2_sel_deleted),
            # on the cream body the accent's signs are dark enough to read: the editor's yellow, then orange
            (0, self.park), (0, lambda: self.settings.set("theme", "light")),
            (800, lambda: self.s_fb2_acc_text("drawSelect", "the editor's yellow")),
            (0, key("E", Qt.ControlModifier)), (0, lambda: self.show_list(True)),
            (900, lambda: self.s_fb2_acc_text("keyPlaylist", "orange")), (0, lambda: self.show_list(False)),
            (0, lambda: self.settings.set("theme", "dark")), (0, key("E", Qt.ControlModifier)),
            # the drawings' tracks: four drawings with one interval (32-36 s), and a very short one
            # (under the drawing tools' card, from 0.22 of the picture's height down)
            (700, self.s_fb2_lay_prep),
            (600, ui("drawRect")), (300, draw([(0.36, 0.22), (0.41, 0.3), (0.46, 0.4)])),
            (300, ui("drawArrow")), (300, draw([(0.55, 0.4), (0.58, 0.3), (0.62, 0.22)])),
            (300, ui("drawPen")), (300, draw([(0.69, 0.22), (0.72, 0.32), (0.75, 0.22), (0.78, 0.32)])),
            (300, ui("drawText")), (300, lambda: self.click_layer(0.86, 0.3)), (400, lambda: self.type_text("Label")),
            (300, lambda: self.type_text("\r", Qt.Key_Return)),
            (300, ui("drawRect")), (0, seek(45.0)), (700, draw([(0.1, 0.8), (0.15, 0.85), (0.2, 0.9)])),
            (300, ui("drawSelect")), (300, self.s_fb2_lay_short), (0, seek(34.5)), (0, self.park),
            (900, self.s_fb2_lay_tracks), (500, self.s_fb2_lay_bars),
            # the frame and the bars point at each other
            (0, lambda: self.find_item("noteLayer").setOpacity(0)), (400, self.s_fb2_bare),
            (0, lambda: QTest.mouseMove(self.win, self.bar_pt(1, 0.75))), (800, self.s_fb2_hover_bar),
            (0, lambda: QTest.mouseMove(self.win, self.layer_pt(0.585, 0.31))), (600, self.s_fb2_hover_frame),
            (0, self.park), (300, lambda: self.ed.selectNote(-1)), (500, self.s_fb2_frame_off),
            (0, lambda: self.ed.selectNote(0)), (500, self.s_fb2_frame_on),
            # a double click on a bar goes to the drawing's start
            (0, seek(38.0)), (600, lambda: self.click_bar(2, double=True)), (700, self.s_fb2_dclick),
            # an end dragged with Alt does not stick; its time shows at once and the frame follows it
            (0, lambda: self.ed.selectNote(0)), (0, seek(37.0)),
            (700, lambda: self.bar_drag(self.bar_pt(0, 1.0, -2), 0.6 * self.px_per_s(), Qt.AltModifier, release=False)),
            (700, self.s_fb2_drag_live), (0, lambda: self.mouse("release", self.drag_last, Qt.AltModifier)),
            (400, self.s_fb2_drag_alt),
            # without Alt an end sticks to the position (and to the ends of drawings and fragments)
            (0, seek(38.0)), (700, lambda: self.bar_drag(self.bar_pt(0, 1.0, -2), 1.2 * self.px_per_s())),
            (500, self.s_fb2_drag_snap),
            # grabbing: the middle of a 2 px bar moves it; 3 px outside a bar's end still takes that end
            (0, seek(60.0)), (700, self.s_fb2_zone_prep), (0, lambda: self.bar_drag(self.bar_pt(4, 0.5), 20)),
            (400, self.s_fb2_zone_mid), (0, lambda: self.bar_drag(self.bar_pt(1, 1.0, 3), 8)), (400, self.s_fb2_zone_end),
            # Shift drags the drawings of the same interval together
            (0, self.s_fb2_group_prep),
            (0, lambda: self.bar_drag(self.bar_pt(2, 0.6), 2.0 * self.px_per_s(), Qt.ShiftModifier)),
            (500, self.s_fb2_group),
            # Tab and Shift+Tab go through the drawings on the frame; [ and ] set the chosen one's ends
            (0, seek(35.0)), (700, self.s_fb2_tab),
            (0, seek(34.5)), (600, key("[")), (0, seek(37.0)), (600, key("]")), (300, self.s_fb2_brackets),
            # a file without drawings: the lane is empty, without a line across it
            (0, lambda: self.pl.add([self.media], True)), (1800, self.s_fb2_lane_empty),
            (0, key("Esc")), (600, self.park),
        ]

    def park(self):
        """The test's pointer off every key, bar and drawing: no hint or hover in the captures."""
        QTest.mouseMove(self.win, QPoint(self.win.width() - 30, self.win.height() // 3))

    def show_list(self, on):
        """The playlist panel shown on its first page (the list), or hidden: set, not toggled."""
        self.win.findChild(QObject, "playlistPanel").setProperty("tab", 0)
        self.win.setProperty("playlistShown", on)

    def mouse(self, kind, pt, mods=Qt.NoModifier):
        """A mouse event with keys held (QTest's moves carry none)."""
        t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}[kind]
        ev = QMouseEvent(t, QPointF(pt), QPointF(self.win.mapToGlobal(pt)), Qt.NoButton if kind == "move" else Qt.LeftButton,
                         Qt.NoButton if kind == "release" else Qt.LeftButton, mods)
        QGuiApplication.sendEvent(self.win, ev)

    @staticmethod
    def cdist(c, ref):
        """Mean channel difference of a pixel from a colour (QColor or (r, g, b))."""
        r = ref.getRgb()[:3] if isinstance(ref, QColor) else ref
        return (abs(c.red() - r[0]) + abs(c.green() - r[1]) + abs(c.blue() - r[2])) / 3

    @staticmethod
    def contrast(c1, c2):
        """WCAG contrast ratio of two colours."""
        def lum(c):
            def ch(v):
                v /= 255
                return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
            return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())
        hi, lo = sorted((lum(c1), lum(c2)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    def mean_diff(self, a, b):
        return sum(self.cdist(a.pixelColor(x, y), b.pixelColor(x, y))
                   for y in range(min(a.height(), b.height())) for x in range(min(a.width(), b.width()))) \
            / max(1, min(a.width(), b.width()) * min(a.height(), b.height()))

    def inside_window(self, item):
        c = item.mapToScene(QPointF(0, 0))
        return item.width() > 0 and c.x() >= 0 and c.y() >= 0 and c.x() + item.width() <= self.win.width() \
            and c.y() + item.height() <= self.win.height()

    def max_light(self, img, item):
        x0, y0, w, h = self.scene_rect(item)
        return max(self.oklch_of(img.pixelColor(x, y))[0]
                   for y in range(int(y0) + 2, int(y0 + h) - 2) for x in range(int(x0) + 2, int(x0 + w) - 2))

    def s_fb2_with_file(self):
        img = capture(int(self.win.winId()))
        self.play_ref = self.region(img, self.find_item("keyPlay"))
        self.lit_ref = {n: round(self.max_light(img, it), 2) for n in self.FILE_KEYS if (it := self.find_item(n))}

    def s_fb2_no_file(self):
        img = capture(int(self.win.winId()))
        diff = self.mean_diff(self.region(img, self.find_item("keyPlay")), self.play_ref)
        self.check("without a file the play key shows «play», as when paused, not «pause»", not self.p.hasFile and diff < 4,
                   f"has file={self.p.hasFile} mpv paused={self.p.mpv.pause} difference from the paused key={diff:.1f}")
        dim = {n: round(self.max_light(img, it), 2) for n in self.FILE_KEYS if (it := self.find_item(n))}
        off = [n for n in self.FILE_KEYS if (it := self.find_item(n)) and not it.isEnabled()]
        on = [n for n in ("keyPlay", "keySound", "keySettings", "keyPlaylist") if self.find_item(n).isEnabled()]
        self.check("without a file the keys that need one are off and look it; play, sound, settings and the playlist stay on",
                   len(off) == len(dim) == len(self.lit_ref) == len(self.FILE_KEYS)
                   and all(dim[n] < self.lit_ref[n] - 0.25 for n in dim) and all(v > 0.75 for v in self.lit_ref.values())
                   and len(on) == 4,
                   f"off={off} brightest pixel: without a file={dim} with one={self.lit_ref} on={on}")
        self.shot("fb2_01_no_file")

    def accent_px(self, img, item):
        """Pixels of a key in a strong colour (a sign or rim in the accent)."""
        x0, y0, w, h = self.scene_rect(item)
        return sum(1 for y in range(int(y0), int(y0 + h)) for x in range(int(x0), int(x0 + w))
                   if self.oklch_of(img.pixelColor(x, y))[1] > 0.08)

    def s_fb2_subs(self, what, lit):
        shown = self.st("subVisible") and self.st("sid") is not False
        self.check(f"subtitles {'on' if lit else 'off'} with {what}, and no subtitles key on the panel (the menu has them)",
                   self.find_item("keySubs") is None and shown is lit,
                   f"sid={self.st('sid')} shown={self.st('subVisible')}")

    def s_fb2_subs_pick(self):
        tracks = self.p.subTracks
        self.p.setSid(tracks[0]["id"] if tracks else -1)

    def s_fb2_menu_open(self):
        self.p.mpv.pause = True
        self.key("S", Qt.AltModifier)

    def s_fb2_menu_prep(self):
        self.menu_before = (self.p.mpv.volume, self.p.mpv.time_pos)

    def s_fb2_menu_keys(self):
        menu, img = self.win.findChild(QObject, "subsMenu"), capture(int(self.win.winId()))
        vol, pos = self.p.mpv.volume, self.p.mpv.time_pos
        dpr = self.win.devicePixelRatio()

        def ground(text):           # a row's own ground, right of its words
            row = text.parentItem()
            c = row.mapToScene(QPointF(row.width() - 8, row.height() / 2))
            return self.oklch_of(img.pixelColor(int(c.x() * dpr), int(c.y() * dpr)))[0]
        off = self.find_text("Off")
        track = self.find_text(self.p.subTracks[0]["title"]) if self.p.subTracks else None
        lit = (ground(off), ground(track)) if off and track else (0, 0)
        self.check("an open menu takes ↑ and ↓ (its highlight moves) and →: the volume and the position under it stay",
                   menu.property("visible") is True and menu.property("current") == 1 and lit[0] > lit[1] + 0.02
                   and abs(vol - self.menu_before[0]) < 0.01 and abs(pos - self.menu_before[1]) < 0.05,
                   f"highlighted row={menu.property('current')} ground of «Off» / the track={lit[0]:.3f} / {lit[1]:.3f} "
                   f"volume {self.menu_before[0]} -> {vol}, position {self.menu_before[1]:.2f} -> {pos:.2f}")
        self.shot("fb2_02_menu_keys")

    def s_fb2_menu_enter(self):
        menu = self.win.findChild(QObject, "subsMenu")
        self.check("Enter runs the highlighted item («Off») and closes the menu; fullscreen stays off",
                   menu.property("visible") is False and self.st("sid") is False and self.win.property("fs") is False,
                   f"menu open={menu.property('visible')} sid={self.st('sid')} fullscreen={self.win.property('fs')}")
        self.s_fb2_subs("subtitles turned off in its menu", False)

    def s_fb2_fs_menu(self):
        img, menu = capture(int(self.win.winId())), self.win.findChild(QObject, "subsMenu")
        x0, y0, w, h = self.scene_rect(self.find_item("panel"))
        # the panel's own ground under the keys, where the picture would show if it had gone
        off = max(self.cdist(img.pixelColor(int(x0 + w * f), int(y0 + h - 3)), (0x1C, 0x1F, 0x24))
                  for f in (0.45, 0.5, 0.55, 0.6, 0.65))
        self.check("fullscreen: while a menu is open the panels stay (3 s without a move)",
                   self.win.property("fs") is True and menu.property("visible") is True
                   and self.win.property("chromeAwake") is True and off < 12,
                   f"fullscreen={self.win.property('fs')} menu={menu.property('visible')} "
                   f"awake={self.win.property('chromeAwake')} panel ground off by {off:.0f}")
        self.shot("fb2_03_fullscreen_menu")

    def s_fb2_fs_esc(self):
        menu = self.win.findChild(QObject, "subsMenu")
        self.check("Esc in fullscreen closes the open menu first; fullscreen stays",
                   menu.property("visible") is False and self.win.property("fs") is True,
                   f"menu open={menu.property('visible')} fullscreen={self.win.property('fs')}")

    def s_fb2_fs_left(self):
        self.check("the next Esc leaves fullscreen, the player stays", self.win.property("fs") is False and self.win.isVisible(),
                   f"fullscreen={self.win.property('fs')} window shown={self.win.isVisible()}")

    def s_fb2_ed_prep(self):
        self.p.mpv.pause = True
        self.ed.frags = []
        self.ed._notes, self.ed._noteSel = [], -1      # an edit of its own: none of the earlier drawings
        self.ed.changed.emit()
        self.settings.set("exportCodec", "copy")

    def s_fb2_preview(self, how, row):
        f = self.ed.frags[row] if row < len(self.ed.frags) else None
        pos = self.st("position")
        self.check(f"{how} plays the edit from fragment {row + 1}",
                   f is not None and self.ed.previewing == row and self.ed._from(f) - 0.1 <= pos < f["end"] and not self.st("paused"),
                   f"previewing={self.ed.previewing} pos={pos:.2f} fragments={self.frags()}")

    def s_fb2_minus(self):
        self.pl.add([self.media], False)
        self.pl.selected = self.pl.count - 1
        self.minus0 = (self.pl.count, len(self.ed.frags), len(self.ed.notes))
        key = next((k for k in self.tip_keys() if k.property("tip") == "Remove from the list (Delete)"), None)
        if key is not None:
            self.click_item(key)

    def s_fb2_minus_done(self):
        now = (self.pl.count, len(self.ed.frags), len(self.ed.notes))
        self.check("the playlist's «−» takes out the playlist row, not a fragment of the open edit",
                   now == (self.minus0[0] - 1, self.minus0[1], self.minus0[2]),
                   f"(rows, fragments, drawings) {self.minus0} -> {now}")

    def seg_ground(self, img, seg, k):
        """How light option k of the codec row (three options) is above its words: the chosen
        one is a raised cap."""
        x0, y0, w, h = self.scene_rect(seg)
        n = 3
        return self.oklch_of(img.pixelColor(int(x0 + w * (k + 0.5) / n), int(y0 + 5 * self.win.devicePixelRatio())))[0]

    def s_fb2_reason(self):
        img, seg = capture(int(self.win.winId())), self.find_item("editCodec")
        g = [self.seg_ground(img, seg, k) for k in range(3)]
        mode, why = self.find_item("editMode"), self.find_item("editReason")
        texts = (mode.property("text") if mode else None, why.property("text") if why else None)
        whole = all(it is not None and it.isVisible() and self.inside_window(it) for it in (mode, why))
        self.check("a drawing over a fragment: the codec row shows H.264 chosen, «Lossless» goes off, the strip says why",
                   len(self.ed.notes) == 1 and g[1] > g[0] + 0.02 and g[1] > g[2] + 0.02
                   and texts == ("H.264", "HAS DRAWINGS") and whole and self.settings["exportCodec"] == "copy",
                   f"option grounds={[round(v, 3) for v in g]} under the length={texts} whole={whole} "
                   f"setting={self.settings['exportCodec']}")
        self.shot("fb2_04_reason")

    def s_fb2_reason_click(self):
        self.settings.set("exportCodec", "h264")
        seg = self.find_item("editCodec")
        self.click_item(seg, (seg.width() / 6, seg.height() / 2))

    def s_fb2_reason_kept(self):
        self.check("a click on «Lossless» while it cannot be has no effect", self.settings["exportCodec"] == "h264",
                   f"setting={self.settings['exportCodec']}")
        self.settings.set("exportCodec", "copy")

    def s_fb2_ring(self):
        img = capture(int(self.win.winId()))
        x0, y0, _w, h = self.scene_rect(self.find_item("ink0"))
        dpr = self.win.devicePixelRatio()
        ring = self.oklch_of(img.pixelColor(int(x0 + 1 * dpr), int(y0 + h / 2)))
        gap = self.oklch_of(img.pixelColor(int(x0 + 3 * dpr), int(y0 + h / 2)))
        self.check("the chosen ink's ring is neutral (the text colour) with a gap to the ink, not the editor's yellow",
                   ring[1] < 0.05 and ring[0] > 0.8 and gap[0] < 0.5,
                   f"ring L,C={ring[0]:.2f},{ring[1]:.3f} gap L={gap[0]:.2f}")

    def s_fb2_sel_note(self):
        self.check("a click on a drawing chooses it, and no fragment stays chosen",
                   self.ed.noteSel == 0 and self.ed.selected == -1, f"drawing={self.ed.noteSel} fragment={self.ed.selected}")

    def s_fb2_sel_frag(self):
        self.check("a click on a fragment chooses it, and no drawing stays chosen",
                   self.ed.selected == 0 and self.ed.noteSel == -1, f"fragment={self.ed.selected} drawing={self.ed.noteSel}")

    def s_fb2_sel_deleted(self):
        self.check("Delete then takes out the chosen fragment, not the drawing",
                   len(self.ed.frags) == 2 and len(self.ed.notes) == 1, f"fragments={self.frags()} drawings={len(self.ed.notes)}")

    def s_fb2_acc_text(self, name, what):
        img, key = capture(int(self.win.winId())), self.find_item(name)
        ink = key.property("ink")
        x0, y0, w, h = self.scene_rect(key)
        cap = img.pixelColor(int(x0 + 4), int(y0 + h / 2))       # the cap beside its sign
        best = max(self.contrast(img.pixelColor(x, y), cap)
                   for y in range(int(y0) + 3, int(y0 + h) - 3) for x in range(int(x0) + 3, int(x0 + w) - 3))
        body = QColor("#EDEAE3")
        L = self.oklch_of(ink)[0]
        self.check(f"cream body: a lit key's sign in {what} reads (OKLCH L at most 0.50, 4.5:1 on the body)",
                   self.settings["theme"] == "light" and (key.property("latched") or key.property("chosen")) is True
                   and L <= 0.505
                   and self.contrast(ink, body) >= 4.5 and best >= 3.5,
                   f"sign {ink.name()} L={L:.3f}, {self.contrast(ink, body):.2f}:1 on the body, darkest on its cap {best:.2f}:1")
        self.shot(f"fb2_05_light_{name}")

    # the drawings' lane
    def lane(self):
        return self.find_item("noteBar0").parentItem()

    def px_per_s(self):
        return self.lane().width() / self.st("duration")

    def lane_x(self, t):
        """The capture column of time t on the drawings' lane."""
        return self.lane().mapToScene(QPointF(t * self.px_per_s(), 0)).x() * self.win.devicePixelRatio()

    def bar_pt(self, i, frac=0.5, dx=0.0):
        """A point on drawing i's bar: at frac of its width, dx pixels further."""
        bar = self.find_item(f"noteBar{i}")
        c = bar.mapToScene(QPointF(bar.width() * frac + dx, bar.height() / 2))
        return QPoint(round(c.x()), round(c.y()))

    def bar_mid(self, i):
        bar = self.find_item(f"noteBar{i}")
        return int(bar.mapToScene(QPointF(0, bar.height() / 2)).y() * self.win.devicePixelRatio())

    def click_bar(self, i, double=False):
        pt = self.bar_pt(i, 0.75)
        if double:
            QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, pt)
        else:
            QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, pt)

    def bar_drag(self, start, dx, mods=Qt.NoModifier, release=True, steps=5):
        self.drag_start = start
        self.mouse("press", start, mods)
        for k in range(1, steps + 1):
            self.drag_last = QPoint(start.x() + round(dx * k / steps), start.y())
            self.mouse("move", self.drag_last, mods)
        if release:
            self.mouse("release", self.drag_last, mods)

    @staticmethod
    def span_of(text):
        """(start, end, length) read from the times shown for a drawing: «0:32.0 – 0:36.0 · 4.0 s»."""
        m = re.fullmatch(r"(\d+):(\d\d\.\d) – (\d+):(\d\d\.\d) · (\d+\.\d) s", text or "")
        return (int(m[1]) * 60 + float(m[2]), int(m[3]) * 60 + float(m[4]), float(m[5])) if m else None

    def s_fb2_lay_prep(self):
        self.ed._notes, self.ed._noteSel = [], -1
        self.ed.changed.emit()
        self.p.mpv.pause = True
        self.p.seek(32.0)

    def s_fb2_lay_short(self):
        self.ed.setNoteRange(len(self.ed.notes) - 1, 45.0, 45.1)

    def s_fb2_lay_tracks(self):
        bars = [self.find_item(f"noteBar{i}") for i in range(5)]
        if None in bars:
            self.check("four drawings with one interval lie on four tracks", False, f"bars={bars}")
            return
        img, dpr = capture(int(self.win.winId())), self.win.devicePixelRatio()
        top = self.lane().mapToScene(QPointF(0, 0)).y() * dpr
        x, free = int(self.lane_x(34.0)), int(self.lane_x(28.0))
        # down the lane through the bars' common middle: one run of bar pixels per track
        rows = [self.cdist(img.pixelColor(x, y), img.pixelColor(free, y)) > 8
                for y in range(int(top) - 1, int(top + self.lane().height() * dpr))]
        runs = sum(1 for k, r in enumerate(rows) if r and (k == 0 or not rows[k - 1]))
        ys = [round(b.y()) for b in bars[:4]]
        picked = []
        for i in range(4):
            self.click_bar(i)
            picked.append(self.ed.noteSel)
        self.click_bar(0)
        self.check("four drawings with one interval lie on four tracks of the lane, and a click on each chooses it",
                   len(set(ys)) == 4 and runs == 4 and picked == [0, 1, 2, 3],
                   f"kinds={[n['kind'] for n in self.ed.notes]} bar y={ys} runs of bar pixels down the lane={runs} "
                   f"chosen by clicks={picked}")

    def s_fb2_lay_bars(self):
        img = self.lay_drawn = capture(int(self.win.winId()))
        dpr = self.win.devicePixelRatio()
        x0, x1, xb = self.lane_x(32.0), self.lane_x(36.0), int(self.lane_x(35.2))   # xb: a bar's body, right of its signs
        y0, y1 = self.bar_mid(0), self.bar_mid(1)
        sel, body = self.oklch_of(img.pixelColor(xb, y0)), self.oklch_of(img.pixelColor(xb, y1))
        ink = self.cdist(img.pixelColor(xb, y1), (0xF2, 0x6A, 0x21))
        bar0 = self.find_item("noteBar0")
        ring_y = int(bar0.mapToScene(QPointF(0, 0)).y() * dpr)          # the chosen bar's top edge
        ring = max(self.oklch_of(img.pixelColor(xb, y))[0] for y in range(ring_y - 1, ring_y + 2))
        words = sum(1 for y in range(y1 - 4, y1 + 5) for x in range(int(x0 + 12 * dpr), int(x0 + 40 * dpr))
                    if self.cdist(img.pixelColor(x, y), img.pixelColor(xb, y1)) > 60)
        self.check("the bars are in the drawing's own ink with its times written on them; the chosen one is ringed in white",
                   ink < 30 and ring > 0.9 and words >= 8,
                   f"bar off the ink by {ink:.0f} chosen bar's edge L={ring:.2f} written pixels={words}")
        ground = img.pixelColor(int(self.lane_x(28.0)), y1)
        cols = [x for x in range(int(x0) - 8, int(x1) + 9) if self.cdist(img.pixelColor(x, y1), ground) > 6]
        y4, x45 = self.bar_mid(4), self.lane_x(45.0)
        ground4 = img.pixelColor(int(self.lane_x(43.0)), y4)
        short = [x for x in range(int(x45) - 8, int(x45) + 9) if self.cdist(img.pixelColor(x, y4), ground4) > 6]
        self.check("a bar lies exactly over its interval (±1 px); a drawing of 0.1 s is 2 px",
                   bool(cols) and abs(cols[0] - round(x0)) <= 1 and abs(cols[-1] + 1 - round(x1)) <= 1
                   and bool(short) and 2 <= short[-1] - short[0] + 1 <= 3 and abs(short[0] - round(x45)) <= 1,
                   f"bar {cols[0] if cols else '-'}-{cols[-1] + 1 if cols else '-'} for {round(x0)}-{round(x1)}; short bar {short[0] if short else '-'} +{short[-1] - short[0] + 1 if short else 0} px "
                   f"at {round(x45)}")
        label = self.find_item("noteSpanLabel")
        text = label.property("text") if label else None
        lx, ly, lw, lh = self.scene_rect(label) if label else (0, 0, 0, 0)
        lit = sum(1 for y in range(int(ly), int(ly + lh)) for x in range(int(lx), int(lx + lw))
                  if self.oklch_of(img.pixelColor(x, y))[0] > 0.75)
        rail = self.find_item("seekRail")
        r0, r1 = (int(rail.mapToScene(QPointF(0, v)).y() * dpr) for v in (0, rail.height()))
        line = sum(1 for y in range(r0, r1) if self.cdist(img.pixelColor(round(x0), y), img.pixelColor(round(x0) - 4, y)) > 10)
        # the scale's own labels it lies over are not left cut in half beside it
        tag = self.scene_rect(label.parentItem()) if label else (0, 0, 0, 0)
        cut = [it.property("text") for it in self.find_item("scaleMarks").childItems()
               if it.objectName().startswith("scaleLabel") and it.isVisible()
               and self.scene_rect(it)[0] < tag[0] + tag[2] and self.scene_rect(it)[0] + self.scene_rect(it)[2] > tag[0]]
        self.check("the chosen drawing's times show on the scale at once, in tenths, between lines up from its ends",
                   text == "0:32.0 – 0:36.0 · 4.0 s" and label.isVisible() and self.inside_window(label) and lit > 15
                   and line >= (r1 - r0) * 0.6 and not cut,
                   f"label={text!r} at {lx:.0f},{ly:.0f} {lw:.0f}x{lh:.0f} light pixels={lit}; "
                   f"line through the seek bar on {line} of {r1 - r0} rows; scale labels under it, cut={cut}")
        self.shot("fb2_10_layers")

    def s_fb2_bare(self):
        self.lay_bare = capture(int(self.win.winId()))
        self.find_item("noteLayer").setOpacity(1)

    def layer_box(self, pts, pad):
        """A drawing's box on the capture (as NoteLayer's box()), grown by pad pixels."""
        layer, dpr = self.find_item("noteLayer"), self.win.devicePixelRatio()
        lw = max(1.5, 0.007 * layer.height())
        c = layer.mapToScene(QPointF(0, 0))
        xs, ys = [c.x() + x * layer.width() for x, _ in pts], [c.y() + y * layer.height() for _, y in pts]
        return [v * dpr for v in (min(xs) - lw - pad, min(ys) - lw - pad, max(xs) + lw + pad, max(ys) + lw + pad)]

    def s_fb2_hover_bar(self):
        img = capture(int(self.win.winId()))
        edge, _inside = self.rect_points(0.36, 0.22, 0.46, 0.4)
        before, now = self.screen_scores(self.lay_bare, self.lay_drawn, edge), self.screen_scores(self.lay_bare, img, edge)
        # the hovered arrow gets an outline around its box
        a0, b0, a1, b1 = self.layer_box([(0.55, 0.4), (0.62, 0.22)], 2)
        o0, p0, o1, p1 = self.layer_box([(0.55, 0.4), (0.62, 0.22)], 7)
        ring = sum(1 for y in range(int(p0), int(p1)) for x in range(int(o0), int(o1))
                   if not (a0 <= x <= a1 and b0 <= y <= b1) and self.cdist(img.pixelColor(x, y), self.lay_drawn.pixelColor(x, y)) > 25)
        self.check("hovering a bar outlines its drawing on the frame and dims the others",
                   sum(now) < 0.6 * sum(before) and ring > 20,
                   f"the rectangle's outline against the bare frame {before} -> {now}; the arrow's outline: {ring} pixels changed")
        self.shot("fb2_11_hover_bar")

    def s_fb2_hover_frame(self):
        img, y, x = capture(int(self.win.winId())), self.bar_mid(1), int(self.lane_x(35.2))
        before, now = self.oklch_of(self.lay_drawn.pixelColor(x, y))[0], self.oklch_of(img.pixelColor(x, y))[0]
        self.check("hovering a drawing on the frame lights its bar", now > before + 0.03, f"bar L {before:.2f} -> {now:.2f}")
        self.shot("fb2_12_hover_frame")

    def s_fb2_frame_off(self):
        self.frame_off = capture(int(self.win.winId()))

    def s_fb2_frame_on(self):
        img = capture(int(self.win.winId()))
        x0, y0, x1, _y1 = self.layer_box([(0.36, 0.22), (0.46, 0.4)], 4)
        dark = dash = 0
        for y in range(int(y0) - 2, int(y0) + 3):
            for x in range(int(x0), int(x1)):
                on, off = self.oklch_of(img.pixelColor(x, y)), self.oklch_of(self.frame_off.pixelColor(x, y))
                dark += on[0] < 0.35 and off[0] > 0.6
                dash += on[0] > 0.85 and on[1] < 0.06 and off[1] > 0.1
        self.check("the chosen drawing's frame is double, a dark line under light dashes: seen on a light picture",
                   dark >= 15 and dash >= 8, f"dark pixels={dark} light dash pixels={dash}")
        self.shot("fb2_13_frame")

    def s_fb2_dclick(self):
        pos = self.st("position")
        self.check("a double click on a bar goes to the drawing's start", abs(pos - 32.0) < 0.1 and self.ed.noteSel == 2,
                   f"pos={pos:.2f} chosen={self.ed.noteSel}")

    def s_fb2_drag_live(self):
        label = self.find_item("noteSpanLabel")
        span, pos = self.span_of(label.property("text") if label else ""), self.p.mpv.time_pos or 0.0
        n = self.ed.notes[0]
        want = n["b"] + (self.drag_last.x() - self.drag_start.x()) / self.px_per_s()
        self.check("while an end is dragged its time shows at once and the frame follows it",
                   span is not None and abs(span[1] - want) < 0.06 and abs(span[2] - (want - n["a"])) < 0.06
                   and abs(pos - want) < 0.1, f"shown={span} want end {want:.2f}, frame at {pos:.2f}")
        self.shot("fb2_14_drag_end")

    def s_fb2_drag_alt(self):
        b = self.ed.notes[0]["b"]
        self.check("with Alt the end does not stick to the position nearby", 36.45 < b < 36.75,
                   f"end={b:.2f} (position 37.0, 0.4 s away)")

    def s_fb2_drag_snap(self):
        b = self.ed.notes[0]["b"]
        self.check("without Alt a dragged end sticks to the position", abs(b - 38.0) < 0.02, f"end={b:.3f} (position 38.0)")

    def s_fb2_zone_prep(self):
        self.zone0 = [(n["a"], n["b"]) for n in self.ed.notes]

    def s_fb2_zone_mid(self):
        (a0, b0), n = self.zone0[4], self.ed.notes[4]
        d = 20 / self.px_per_s()
        self.check("the middle of a 2 px bar moves the drawing (both ends), it does not take an end",
                   abs(n["a"] - a0 - d) < 0.06 and abs(n["b"] - b0 - d) < 0.06,
                   f"{a0:.2f}-{b0:.2f} -> {n['a']:.2f}-{n['b']:.2f}, moved by {d:.2f} s")

    def s_fb2_zone_end(self):
        (a0, b0), n = self.zone0[1], self.ed.notes[1]
        d = 8 / self.px_per_s()
        self.check("3 px outside a bar's end still takes that end", abs(n["a"] - a0) < 0.01 and abs(n["b"] - b0 - d) < 0.06,
                   f"{a0:.2f}-{b0:.2f} -> {n['a']:.2f}-{n['b']:.2f}")

    def s_fb2_group_prep(self):
        self.group0 = [(n["a"], n["b"]) for n in self.ed.notes]

    def s_fb2_group(self):
        now = [(n["a"], n["b"]) for n in self.ed.notes]
        d2, d3 = now[2][0] - self.group0[2][0], now[3][0] - self.group0[3][0]
        self.check("Shift drags the drawings of the same interval together; the others stay",
                   self.group0[2] == self.group0[3] and now[2] == now[3] and 1.8 <= d2 <= 2.2 and abs(d2 - d3) < 1e-6
                   and now[0] == self.group0[0] and now[1] == self.group0[1],
                   f"before={[tuple(round(v, 2) for v in p) for p in self.group0[:4]]} "
                   f"after={[tuple(round(v, 2) for v in p) for p in now[:4]]}")

    def s_fb2_tab(self):
        self.ed.selectNote(1)
        seen = []
        for mods in (Qt.NoModifier, Qt.NoModifier, Qt.NoModifier, Qt.ShiftModifier):
            self.key("Tab", mods)
            seen.append(self.ed.noteSel)
        self.check("Tab and Shift+Tab go through the drawings on the frame", seen == [2, 3, 0, 3], f"from 1: {seen}")

    def s_fb2_brackets(self):
        n = self.ed.notes[3]
        self.check("[ and ] set the chosen drawing's start and end to the frame shown",
                   self.ed.noteSel == 3 and abs(n["a"] - 34.5) < 0.06 and abs(n["b"] - 37.0) < 0.06,
                   f"chosen={self.ed.noteSel} interval={n['a']:.2f}-{n['b']:.2f}")

    def s_fb2_lane_empty(self):
        img, rail = capture(int(self.win.winId())), self.find_item("seekRail")
        x0, y0, w, h = self.scene_rect(rail)
        xs = range(int(x0) + 10, int(x0 + w) - 10, 7)
        means = [sum(sum(img.pixelColor(x, y).getRgb()[:3]) for x in xs) / (3 * len(xs))
                 for y in range(int(y0 + h) + 1, int(y0 + h) + 14)]
        mid = sorted(means)[len(means) // 2]
        lines = [round(m - mid, 1) for m in means if abs(m - mid) > 3]
        self.check("a file without drawings: the drawings' lane is empty, without a line across it",
                   self.ed.active and not any(n["path"] == self.st("path") for n in self.ed.notes) and not lines,
                   f"rows off the others: {lines}")
        self.shot("fb2_15_lane_empty")

    # ---- release blockers (production analysis 23.10.2026): a failure is said in words and
    # blocks nothing; a dropped station is reconnected, never taken for the end of the list
    def fb3_steps(self):
        folder = Path(self.media).parent
        return [
            # a save onto a file another program holds open: said on the strip, editor not blocked
            (0, self.s_fb3_busy_prep), (1800, self.s_fb3_busy_save),
            (500, self.until(lambda: not self.ed.exporting, 60)), (300, self.s_fb3_busy_failed),
            (0, lambda: self.click_item(self.find_item("editError"))), (300, self.s_fb3_busy_retry),
            (500, self.until(lambda: not self.ed.exporting, 60)), (300, self.s_fb3_busy_saved),
            # files that do not open are passed over, each with its reason
            (0, lambda: self.s_fb3_bad_prep(folder)),
            (2500, self.until(lambda: Path(self.st("path") or "").name == "test1080.mkv", 10)),
            (300, self.s_fb3_bad_done),
            # a station that drops: reconnected, «when the list ends: shut down» does not start
            (0, self.s_fb3_drop_prep), (3500, self.s_fb3_drop_cut), (400, lambda: None),
            (0, self.until(lambda: any(m.startswith("The connection to the station dropped") for m in self.said[self.osd0:]), 20)),
            (300, self.s_fb3_drop_said),
            (0, self.until(lambda: self.st("path") == self.station and not self.st("eof")
                           and self.st("position") > 1.0, 20)),
            (300, self.s_fb3_drop_back),
        ]

    def s_fb3_busy_prep(self):
        self.said = []                 # this block's OSD messages (the editor block disconnects its own)
        self.p.osdMessage.connect(self.said.append)
        self.ed.frags, self.ed._notes = [], []
        self.ed.changed.emit()
        self.busy_target = self.out / "busy.mp4"
        self.busy_target.write_bytes(b"held open by another program")
        self.busy = open(self.busy_target, "rb")   # as a player or a messenger holds a file
        self.pl.add([self.media], True)

    def s_fb3_busy_save(self):
        if not self.ed.active:
            self.a.run("edit_mode")
        self.a.run("edit_whole")
        self.ed.exportTo(str(self.busy_target))

    def s_fb3_busy_failed(self):
        bar = self.find_item("editError")
        self.check("a save onto a file open elsewhere: says so and what to do, on the strip, and saving is free again",
                   not self.ed.exporting and "is open in another program" in self.ed.error
                   and bar is not None and bar.property("visible") is True
                   and any("is open in another program" in m for m in self.said)
                   and not (self.out / "busy.part.mp4").exists(),
                   f"exporting={self.ed.exporting} error={self.ed.error!r} osd={self.said}")
        self.shot("fb3_01_busy_error")
        self.busy.close()

    def s_fb3_busy_retry(self):
        self.check("a click takes the failure off the strip", self.ed.error == ""
                   and self.find_item("editError").property("visible") is False, f"error={self.ed.error!r}")
        self.ed.exportTo(str(self.busy_target))

    def s_fb3_busy_saved(self):
        size = self.busy_target.stat().st_size
        self.check("once the file is free, the same save goes through",
                   self.ed.saved == str(self.busy_target) and self.ed.error == "" and size > 10000,
                   f"saved={self.ed.saved!r} size={size}")

    def s_fb3_bad_prep(self, folder):
        if self.ed.active:
            self.a.run("edit_mode")
        self.settings.set("onListEnd", "stop")
        broken = self.out / "broken.mp4"
        broken.write_bytes(b"not a video at all")
        self.osd0 = len(self.said)
        self.pl.add([str(broken), str(self.out / "gone.mkv"), str(folder / "test1080.mkv")], True)

    def s_fb3_bad_done(self):
        said = self.said[self.osd0:]
        self.check("files that do not open are passed over, each said with its reason",
                   Path(self.st("path") or "").name == "test1080.mkv"
                   and "Could not open “broken.mp4”: the format is not recognized" in said
                   and any(m.startswith("Could not open “gone.mkv”: the file is not there") for m in said),
                   f"path={self.st('path')} osd={said}")
        self.shot("fb3_02_not_opened")

    def s_fb3_drop_prep(self):
        self.settings.set("onListEnd", "shutdown")
        self.powered0 = list(self.sch.powered)
        self.ended = 0
        self.pl.listEnded.connect(self._fb3_ended)
        self.pl.add([self.station], True)

    def _fb3_ended(self):
        self.ended += 1

    def s_fb3_drop_cut(self):
        self.check("the station plays before the line drops", self.st("path") == self.station
                   and self.st("position") > 0.5, f"path={self.st('path')} pos={self.st('position'):.1f}")
        self.osd0 = len(self.said)
        self.icy.drop = True

    def s_fb3_drop_said(self):
        self.check("a dropped station is said and reconnected, not taken for the end of the list",
                   any(m.startswith("The connection to the station dropped") for m in self.said[self.osd0:])
                   and self.ended == 0 and self.sch.powered == self.powered0 and self.sch.countdown == 0,
                   f"ended={self.ended} powered={self.sch.powered} osd={self.said[self.osd0:]}")
        self.shot("fb3_03_reconnecting")

    def s_fb3_drop_back(self):
        self.check("after the reconnect the station plays on",
                   self.st("path") == self.station and not self.st("eof") and self.ended == 0
                   and self.sch.powered == self.powered0, f"pos={self.st('position'):.1f} ended={self.ended}")
        self.pl.listEnded.disconnect(self._fb3_ended)
        self.p.osdMessage.disconnect(self.said.append)
        self.settings.set("onListEnd", "stop")

    # ---- stage 1 («everything flies»): nothing slow on the GUI thread, which also draws the
    # picture (QSG_RENDER_LOOP=basic). Each slow call is measured as it is (STAGE1 MEASURE lines),
    # then made deterministically slow (a sleep in front of it) and the gesture that starts it
    # must still return at once: a gesture that waits for it freezes the picture.
    FAST_MS = 100        # Apple's budget for the main thread per discrete action

    def st1_steps(self):
        long_mkv = str(Path(self.media).parent / "test_long.mkv")
        folder = str(Path(self.media).parent)

        def seek(t):
            return lambda: self.p.seek(t)

        def pending():
            return self.until(lambda: not getattr(self.ed, "pending", False), 15, 100)
        return [
            # the editor: O, X and «whole file» ask ffprobe for the keyframe and the file's format
            (0, lambda: self.s_st1_prep(long_mkv)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            (0, seek(35.0)), (600, self.s_st1_o_real), (0, seek(55.0)), (600, self.s_st1_o_real2),
            (0, seek(53.0)), (600, self.s_st1_x_real), (0, pending()), (0, self.s_st1_real_done),
            (0, seek(75.0)), (600, self.s_st1_o_slow), (150, lambda: self.shot("st1_01_fragment_pending")),
            (0, pending()), (0, self.s_st1_o_done), (0, seek(63.0)), (600, self.s_st1_x_slow), (0, pending()),
            (0, self.s_st1_x_done), (0, self.s_st1_whole_slow), (0, pending()), (0, self.s_st1_whole_done),
            # Alt+I: the card opens at once, ffprobe's rows follow
            (0, self.s_st1_info_real), (800, lambda: self.key("Esc")), (400, self.s_st1_info_slow),
            (100, lambda: self.shot("st1_02_info_reading")),
            (0, self.until(lambda: len(self.find_info().property("sections") or []) > 1, 10, 100)),
            (0, self.s_st1_info_done), (300, lambda: self.key("Esc")),
            # a folder and the next episodes are read off the GUI thread
            (400, lambda: self.s_st1_folder_real(folder)), (0, lambda: self.s_st1_folder_slow(folder)),
            (0, self.until(lambda: self.pl.count > self.n0, 10, 100)), (0, self.s_st1_folder_done),
            (0, self.s_st1_series_slow), (0, self.until(lambda: self.st("path") == self.media, 10, 100)),
            (1200, self.s_st1_series_done),
            # the first save with H.264: the NVIDIA encoder check and the drawings' PNGs
            (0, lambda: self.s_st1_nv_prep(long_mkv)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            (0, seek(4.0)), (600, lambda: self.key("O")), (0, pending()), (0, self.s_st1_nv_real),
            (300, self.until(lambda: not self.ed.exporting, 60)), (0, self.s_st1_nv_slow),
            (300, self.until(lambda: not self.ed.exporting, 60)), (0, self.s_st1_nv_done),
            # settings, positions and history: written off the GUI thread
            (0, self.s_st1_json_real), (300, self.s_st1_json_slow),
            (2500, self.s_st1_json_done),
            # dragging the seek bar: fast keyframe seeks while moving, one exact seek on release
            (0, lambda: self.pl.add([long_mkv], True)), (1800, self.s_st1_scrub), (900, self.s_st1_scrubbed),
            # plain playing: the position alone changes; nothing else is re-read 25 times a second
            (0, lambda: setattr(self.p.mpv, "pause", False)), (800, self.s_st1_sig_start), (2000, self.s_st1_sig_done),
        ]

    def find_info(self):
        return self.win.findChild(QObject, "infoPanel")

    def timed(self, fn):
        t = time.perf_counter()
        fn()
        return (time.perf_counter() - t) * 1000

    def slow(self, mod, name, delay=0.4):
        orig = getattr(mod, name)

        def late(*a, **k):
            time.sleep(delay)
            return orig(*a, **k)
        setattr(mod, name, late)
        self.unpatch.append((mod, name, orig))

    def restore(self):
        while self.unpatch:
            mod, name, orig = self.unpatch.pop()
            setattr(mod, name, orig)

    def s_st1_prep(self, path):
        self.unpatch = []
        self.st1 = {}
        if self.ed.active:
            self.ed.close()
        self.ed.frags, self.ed._notes = [], []
        self.ed.setCodec("copy")
        self.ed._probes.clear()
        self.pl.add([path], True)

    def st1_key(self, name):
        """How long a key of the edit takes to return."""
        return self.timed(lambda: self.key(name))

    def s_st1_o_real(self):
        if not self.ed.active:
            self.a.run("edit_mode")
        self.st1["o_first"] = self.st1_key("I")      # the file comes in whole, I at 35: format and keyframe

    def s_st1_o_real2(self):
        self.st1["o_next"] = self.st1_key("O")       # O at 55: nothing to read

    def s_st1_x_real(self):
        self.st1["x"] = self.st1_key("X")            # X at 53: the keyframe alone

    def s_st1_real_done(self):
        log.info("STAGE1 MEASURE editor O first=%.0f ms O next=%.0f ms X=%.0f ms",
                 self.st1["o_first"], self.st1["o_next"], self.st1["x"])

    def s_st1_o_slow(self):
        from . import editor as editor_mod
        self.slow(editor_mod, "keyframe_before")
        self.slow(editor_mod, "probe")
        self.ed._probes.clear()
        self.ed.frags = []                           # the file comes in again, unread
        self.st1["o_slow"] = self.st1_key("X")       # at 75
        frags = self.ed.fragments
        self.st1["o_shown"] = len(frags) == 2 and bool(frags[-1].get("pending"))

    def s_st1_o_done(self):
        self.restore()
        f = self.ed.fragments[-1]
        self.check("X with a slow ffprobe on a file not yet read: the pieces are on the strip at once, marked as "
                   "being read; the cut moves to its keyframe later",
                   self.st1["o_slow"] < self.FAST_MS and self.st1["o_shown"] and abs(f["from"] - 70.0) < 0.05
                   and not f.get("pending"),
                   f"O took {self.st1['o_slow']:.0f} ms shown={self.st1['o_shown']} from={f['from']:.2f}")

    def s_st1_x_slow(self):
        from . import editor as editor_mod
        self.slow(editor_mod, "keyframe_before")
        self.st1["x_slow"] = self.st1_key("X")     # at 63, inside 0-70: the piece after it begins at the keyframe 60

    def s_st1_x_done(self):
        self.restore()
        tail = [f for f in self.ed.fragments if abs(f["end"] - 70.0) < 0.2]
        self.check("X with a slow ffprobe returns at once; the piece after the cut gets its keyframe",
                   self.st1["x_slow"] < self.FAST_MS and len(tail) == 1 and abs(tail[0]["from"] - 60.0) < 0.05,
                   f"X took {self.st1['x_slow']:.0f} ms tail={tail}")

    def s_st1_whole_slow(self):
        from . import editor as editor_mod
        self.slow(editor_mod, "keyframe_before")
        self.slow(editor_mod, "probe")
        self.ed._probes.clear()
        self.n0 = len(self.ed.frags)
        self.st1["whole"] = self.timed(lambda: self.a.run("edit_whole"))

    def s_st1_whole_done(self):
        self.restore()
        f = self.ed.fragments[-1]
        self.check("«whole file» with a slow ffprobe returns at once",
                   self.st1["whole"] < self.FAST_MS and len(self.ed.frags) == self.n0 + 1 and f["from"] == 0.0
                   and abs(f["end"] - 90.0) < 0.5,
                   f"took {self.st1['whole']:.0f} ms fragment={f}")
        self.ed.frags = []
        self.ed.close()

    def s_st1_info_real(self):
        t = self.timed(lambda: self.key("I", Qt.AltModifier))
        log.info("STAGE1 MEASURE Alt+I %.0f ms", t)

    def s_st1_info_slow(self):
        from . import info
        self.slow(info, "probe_sections", 0.8)
        self.st1["info"] = self.timed(lambda: self.key("I", Qt.AltModifier))
        self.st1["info_open"] = self.find_info().property("visible") is True

    def s_st1_info_done(self):
        self.restore()
        titles = [x["title"] for x in self.find_info().property("sections") or []]
        self.check("Alt+I with a slow ffprobe opens the card at once, the streams follow",
                   self.st1["info"] < self.FAST_MS and self.st1["info_open"] and "Video" in titles,
                   f"took {self.st1['info']:.0f} ms sections={titles}")
        self.shot("st1_03_info_read")

    def s_st1_folder_real(self, folder):
        self.pl.clear()
        t = self.timed(lambda: self.pl.add([folder], False))
        log.info("STAGE1 MEASURE folder add %.0f ms (%s)", t, folder)

    def s_st1_folder_slow(self, folder):
        from . import playlist as playlist_mod
        self.slow(playlist_mod, "expand")
        self.n0 = self.pl.count
        self.st1["folder"] = self.timed(lambda: self.pl.add([folder], False))

    def s_st1_folder_done(self):
        self.restore()
        self.check("a folder read slowly: adding it returns at once, its files follow",
                   self.st1["folder"] < self.FAST_MS and self.pl.count > self.n0,
                   f"took {self.st1['folder']:.0f} ms count {self.n0}->{self.pl.count}")

    def s_st1_series_slow(self):
        from . import series
        self.pl.clear()
        self.pl.series = True
        self.slow(series, "following")
        self.st1["series"] = self.timed(lambda: self.pl.add([self.media], True))

    def s_st1_series_done(self):
        self.restore()
        self.check("one file opened with the next episodes looked up slowly: it plays at once",
                   self.st1["series"] < self.FAST_MS and self.st("position") > 0.3,
                   f"took {self.st1['series']:.0f} ms pos={self.st('position'):.2f}")
        self.pl.series = self.settings["series"]

    def s_st1_nv_prep(self, path):
        self.ed.frags = []
        self.pl.add([path], True)

    def s_st1_nv_real(self):
        from . import editor as editor_mod
        self.ed.setCodec("h264")
        editor_mod._hw_ok.clear()
        t = self.timed(lambda: self.ed.exportTo(str(self.out / "st1_nv_real.mp4")))
        log.info("STAGE1 MEASURE first H.264 save (encoder check) %.0f ms", t)

    def s_st1_nv_slow(self):
        from . import editor as editor_mod
        self.slow(editor_mod, "encoder_args")
        self.st1["nv"] = self.timed(lambda: self.ed.exportTo(str(self.out / "st1_nv_slow.mp4")))

    def s_st1_nv_done(self):
        self.restore()
        self.check("saving with a slow encoder check returns at once and the file is saved",
                   self.st1["nv"] < self.FAST_MS and (self.out / "st1_nv_slow.mp4").exists() and not self.ed.error,
                   f"took {self.st1['nv']:.0f} ms error={self.ed.error!r}")
        self.ed.setCodec(self.settings["exportCodec"])
        self.ed.frags = []
        self.ed.close()

    def s_st1_json_real(self):
        step = self.settings["seekStep"]
        t = self.timed(lambda: self.settings.set("seekStep", step + 1))
        self.settings.set("seekStep", step)
        log.info("STAGE1 MEASURE settings write %.1f ms", t)

    def s_st1_json_slow(self):
        orig = Path.write_text
        home = Path(os.environ["OY_HOME"])

        def late(path, *a, **k):
            if path.parent == home and path.suffix == ".tmp":
                time.sleep(0.3)
            return orig(path, *a, **k)
        Path.write_text = late
        self.unpatch.append((Path, "write_text", orig))
        self.step0 = self.settings["jumpStep"]
        self.st1["set"] = self.timed(lambda: self.settings.set("jumpStep", self.step0 + 1))
        other = str(Path(self.media).parent / "test1080.mkv")
        self.st1["leave"] = self.timed(lambda: self.p.open(other))

    def s_st1_json_done(self):
        self.restore()
        saved = json.loads((Path(os.environ["OY_HOME"]) / "settings.json").read_text(encoding="utf-8"))
        self.check("a slow disk: a setting and leaving a file return at once, the setting is written",
                   self.st1["set"] < self.FAST_MS and self.st1["leave"] < self.FAST_MS
                   and saved.get("jumpStep") == self.step0 + 1,
                   f"setting {self.st1['set']:.0f} ms, leaving a file {self.st1['leave']:.0f} ms, "
                   f"saved jumpStep={saved.get('jumpStep')}")
        self.settings.set("jumpStep", self.step0)

    def s_st1_scrub(self):
        m, seeks = self.p.mpv, []
        m.pause = True                 # the position checked is where the release put it
        command0, async0 = m.command, m.command_async     # python-mpv's seek() is a seek command too

        def record(call):
            def run(name, *a, **k):
                if name == "seek":
                    seeks.append(" ".join(str(x) for x in a[1:]))
                return call(name, *a, **k)
            return run
        m.command, m.command_async = record(command0), record(async0)
        t, moves = time.perf_counter(), []
        self.mouse("press", self.rail_pt(0.2))
        for i in range(1, 21):
            moves.append(self.timed(lambda: self.mouse("move", self.rail_pt(0.2 + 0.02 * i))))
            self.app.processEvents()
        self.mouse("release", self.rail_pt(0.6))
        self.st1["drag_ms"] = (time.perf_counter() - t) * 1000
        self.st1["move_ms"] = max(moves)
        del m.command, m.command_async
        self.seeks = seeks

    def s_st1_scrubbed(self):
        exact = [s for s in self.seeks if "exact" in s]
        log.info("STAGE1 MEASURE seek bar drag of 21 moves (paused): %d seeks, %d exact, %.0f ms in all, "
                 "the slowest move %.0f ms", len(self.seeks), len(exact), self.st1["drag_ms"], self.st1["move_ms"])
        self.check("dragging the seek bar: keyframe seeks while moving, one exact seek on release, no move waits",
                   len(self.seeks) >= 21 and exact == [self.seeks[-1]] and self.st1["move_ms"] < self.FAST_MS
                   and abs(self.st("position") - 0.6 * self.st("duration")) < 0.5,
                   f"seeks={self.seeks[:3]}…{self.seeks[-2:]} slowest move {self.st1['move_ms']:.0f} ms "
                   f"pos={self.st('position'):.2f}")

    def s_st1_sig_start(self):
        self.st1["changed"] = 0
        self.st1["calls"] = 0
        self.tl0 = self.find_item("timeline").property("position")

        def count():
            self.st1["changed"] += 1
        self.st1_count = count
        self.p.changed.connect(count)

        def prof(frame, event, _arg):
            if event == "call" and frame.f_code.co_filename.endswith("player.py"):
                self.st1["calls"] += 1
        sys.setprofile(prof)

    def s_st1_sig_done(self):
        sys.setprofile(None)
        self.p.changed.disconnect(self.st1_count)
        tl = self.find_item("timeline").property("position")
        log.info("STAGE1 MEASURE 2 s of playing: Player.changed %d, calls into player.py %d",
                 self.st1["changed"], self.st1["calls"])
        self.check("plain playing: the general change signal stays quiet, the timeline still moves",
                   self.st1["changed"] <= 4 and tl - self.tl0 > 1.0,
                   f"changed={self.st1['changed']} calls={self.st1['calls']} timeline {self.tl0:.2f}->{tl:.2f}")

    # ---- stage 3: keyboard, focus and the screen reader. The keyboard goes to an area (F6 or
    # a click in it: the playlist, the edit strip) before the commands; a screen reader reads
    # what Qt's accessibility tree says (QAccessible, the tree Windows' UI Automation gets).
    def st3_steps(self):
        long_mkv = str(Path(self.media).parent / "test_long.mkv")

        def key(name, mods=Qt.NoModifier):
            return lambda: self.key(name, mods)
        return [
            (0, lambda: self.s_st3_prep(long_mkv)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            (300, self.s_st3_tree), (0, self.s_st3_rows),
            # the playlist from the keyboard
            (0, key("F6")), (300, self.s_st3_list_focused), (0, key("Down")), (200, self.s_st3_list_down),
            (0, key("End")), (200, self.s_st3_list_end), (0, key("Home")), (200, self.s_st3_list_home),
            (0, key("Down")), (0, key("Enter")), (1500, self.s_st3_list_enter),
            (0, key("Delete")), (300, self.s_st3_list_delete),
            # the history and the radio answer the same keys
            (0, self.s_st3_hist_prep), (500, key("Down")), (200, self.s_st3_hist_down),
            (0, lambda: self.plp().setProperty("tab", 0)),
            # the edit strip: F6 moves on to it
            (0, self.s_st3_strip_prep), (0, self.until(lambda: not self.ed.pending, 10, 100)),
            (300, key("F6")), (300, self.s_st3_strip_focused), (0, key("Home")), (300, self.s_st3_strip_home), (0, key("Right")),
            (300, self.s_st3_strip_right), (0, key("Enter")), (600, self.s_st3_strip_enter),
            (0, key("Delete")), (300, self.s_st3_strip_delete),
            # F6 once more: back to the commands, the arrows are the volume again
            (0, key("F6")), (200, self.s_st3_back), (0, key("Down")), (300, self.s_st3_back_volume),
            # a click on a row gives the list the keys
            (0, self.s_st3_click_row), (300, key("Down")), (300, self.s_st3_clicked),
            (0, self.s_st3_done),
        ]

    def plp(self):
        return self.win.findChild(QObject, "playlistPanel")

    def a11y(self):
        """The window's accessibility tree, flattened: (role, name, description, state, object)."""
        from PySide6.QtGui import QAccessible
        out = []

        def walk(i, depth):
            if i is None or not i.isValid() or depth > 60:
                return
            out.append((i.role(), i.text(QAccessible.Name) or "", i.text(QAccessible.Description) or "",
                        i.state(), i.object()))
            for k in range(i.childCount()):
                walk(i.child(k), depth + 1)
        walk(QAccessible.queryAccessibleInterface(self.win), 0)
        return out

    def s_st3_prep(self, path):
        if self.ed.active:
            self.ed.close()
        self.ed.frags, self.ed._notes = [], []
        self.pl.clear()
        self.pl.add([path] + self.medias, True)
        self.win.setProperty("playlistShown", True)
        self.plp().setProperty("tab", 0)

    def s_st3_tree(self):
        from PySide6.QtGui import QAccessible
        tree = self.a11y()
        keys = [(r, n) for r, n, _d, s, o in tree
                if o is not None and o.metaObject().className().startswith("KeyCap") and not s.invisible]
        unnamed = [n for r, n in keys if r != QAccessible.Button or not n.strip()]
        seek = [(r, n, d) for r, n, d, _s, o in tree if o is not None and o.objectName() == "seekRail"]
        tips = [n for _r, n, _d, _s, o in tree if o is not None and o.objectName() == "tip"]
        self.check("a screen reader finds every key on the panel as a button with its name",
                   len(keys) >= 12 and not unnamed and any(n == "Play" or n == "Pause" for _r, n in keys),
                   f"keys={len(keys)} unnamed={unnamed[:5]} names={[n for _r, n in keys][:12]}")
        self.check("the seek bar is a slider named «Position» that says where it is",
                   len(seek) == 1 and seek[0][0] == QAccessible.Slider and seek[0][1] == "Position" and "/" in seek[0][2],
                   f"seek={seek}")
        self.check("hover hints are not read out on their own", not tips, f"tips={tips[:3]}")

    def s_st3_rows(self):
        from PySide6.QtGui import QAccessible
        self.pl.selected = 1
        rows = [(n, s.selected) for r, n, _d, s, o in self.a11y() if r == QAccessible.ListItem and not s.invisible]
        names = [n for n, _s in rows]
        self.check("the playlist's rows are list items named by their file, the chosen one selected",
                   len(rows) >= 3 and any(n.startswith("test_long.mkv") for n in names)
                   and [n for n, s in rows if s] == [names[1]],
                   f"rows={rows[:4]}")

    def s_st3_list_focused(self):
        ring = self.find_item("listFocus")
        self.check("F6 gives the playlist the keys, and a ring shows it",
                   self.win.property("area") == "list" and ring is not None and ring.property("visible") is True,
                   f"area={self.win.property('area')!r} ring={ring is not None and ring.property('visible')}")
        self.shot("st3_01_list_focused")
        self.vol0 = self.p.mpv.volume

    def s_st3_list_down(self):
        self.check("↓ in the focused list chooses the next row, the volume stays",
                   self.pl.selected == 2 and self.p.mpv.volume == self.vol0,
                   f"selected={self.pl.selected} volume {self.vol0}->{self.p.mpv.volume}")

    def s_st3_list_end(self):
        self.check("End chooses the last row (the window is not minimised)",
                   self.pl.selected == self.pl.count - 1 and not (self.win.windowState() & Qt.WindowMinimized),
                   f"selected={self.pl.selected} of {self.pl.count}")

    def s_st3_list_home(self):
        self.check("Home chooses the first row (the window keeps its size)", self.pl.selected == 0,
                   f"selected={self.pl.selected}")

    def s_st3_list_enter(self):
        self.check("Enter plays the chosen row, not full screen",
                   self.pl.current == 1 and self.st("path") == self.pl.items[1]["path"] and not self.win.property("fs"),
                   f"current={self.pl.current} path={Path(self.st('path') or '').name} fs={self.win.property('fs')}")
        self.n0 = self.pl.count

    def s_st3_list_delete(self):
        self.check("Delete takes the chosen row out of the list", self.pl.count == self.n0 - 1,
                   f"count {self.n0}->{self.pl.count}")

    def s_st3_hist_prep(self):
        self.plp().setProperty("tab", 1)
        self.plp().setProperty("histSel", "")

    def s_st3_hist_down(self):
        first = (self.m8["history"].entries or [{}])[0].get("path", "")
        self.check("the history answers the same keys: ↓ chooses its first row",
                   bool(first) and self.plp().property("histSel") == first,
                   f"histSel={self.plp().property('histSel')!r} first={first!r}")

    def s_st3_strip_prep(self):
        self.a.run("edit_mode")
        self.ed.frags = []
        self.a.run("edit_whole")
        self.a.run("edit_whole")

    def s_st3_strip_focused(self):
        ring = self.find_item("stripFocus")
        self.check("F6 from the list moves the keys to the edit strip, with its ring",
                   self.win.property("area") == "strip" and ring is not None and ring.property("visible") is True,
                   f"area={self.win.property('area')!r}")
        self.shot("st3_02_strip_focused")
        self.pos0 = self.st("position")

    def s_st3_strip_home(self):
        self.check("Home in the focused strip chooses the first fragment (the window keeps its size)",
                   self.ed.selected == 0, f"selected={self.ed.selected}")

    def s_st3_strip_right(self):
        self.check("→ in the focused strip chooses the next fragment, the picture does not jump 5 s",
                   self.ed.selected == 1, f"selected={self.ed.selected}")

    def s_st3_strip_enter(self):
        self.check("Enter plays the edit from the chosen fragment", self.ed.previewing == 1 and not self.win.property("fs"),
                   f"previewing={self.ed.previewing} fs={self.win.property('fs')}")
        self.p.mpv.pause = True

    def s_st3_strip_delete(self):
        self.check("Delete takes the chosen fragment out", len(self.ed.frags) == 1, f"fragments={len(self.ed.frags)}")

    def s_st3_back(self):
        self.check("F6 past the last area gives the keys back to the commands", self.win.property("area") == "",
                   f"area={self.win.property('area')!r}")
        self.vol0 = self.p.mpv.volume

    def s_st3_back_volume(self):
        self.check("then ↓ is the volume again", self.p.mpv.volume < self.vol0, f"volume {self.vol0}->{self.p.mpv.volume}")
        self.key("Up")

    def s_st3_click_row(self):
        self.ed.close()
        self.plp().setProperty("tab", 0)
        self.pl.selected = 0
        row = self.find_item("plRow0")
        self.click_item(row)
        self.vol0 = self.p.mpv.volume

    def s_st3_clicked(self):
        self.check("a click on a row gives the list the keys: ↓ moves the choice, not the volume",
                   self.win.property("area") == "list" and self.pl.selected == 1 and self.p.mpv.volume == self.vol0,
                   f"area={self.win.property('area')!r} selected={self.pl.selected} volume {self.vol0}->{self.p.mpv.volume}")

    def s_st3_done(self):
        self.win.setProperty("area", "")
        self.win.setProperty("playlistShown", False)

    # ---- stage 4: the Braun panel (council stage 3) and an honest edit (council stage 4, the
    # blind comparison): one colour, one meaning; what goes into the file is seen before saving
    def st4_steps(self):
        long_mkv = str(Path(self.media).parent / "test_long.mkv")

        def seek(t):
            return lambda: self.p.seek(t)
        return [
            (0, lambda: self.s_st4_prep(long_mkv)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            (0, seek(75.0)), (600, self.s_st4_panel), (0, self.s_st4_menu), (400, self.s_st4_menu_key),
            (0, lambda: self.key("Esc")), (300, self.s_st4_edit_prep), (0, seek(35.0)), (600, self.s_st4_keys),
            ] + self.keep_steps([(25.0, 35.0), (45.0, 55.0)]) + [
            (600, self.s_st4_preview), (900, self.s_st4_previewing), (0, self.s_st4_close_x), (400, self.s_st4_closed),
            # saving: Ctrl+Shift+S saves beside the source at once, no dialog
            (0, self.s_st4_save), (0, self.until(lambda: not self.ed.exporting, 60)),
            (300, self.s_st4_saved),
            (0, self.s_st4_done),
        ]

    def s_st4_prep(self, path):
        if self.ed.active:
            self.ed.close()
        self.ed.frags, self.ed._notes = [], []
        self.win.setProperty("playlistShown", False)
        self.pl.add([path], True)

    def item_ink(self, name):
        return QColor(self.find_item(name).property("ink"))

    def s_st4_panel(self):
        img = capture(int(self.win.winId()))
        self.shot("st4_01_panel")
        vol = self.region(img, self.find_item("volume"))
        coloured = sum(1 for y in range(vol.height()) for x in range(vol.width())
                       if self.oklch_of(vol.pixelColor(x, y))[1] > 0.1)
        self.check("the volume is filled in neutral metal: the accent is only the play key and the position",
                   coloured == 0, f"coloured pixels in the volume={coloured}")
        self.p.mpv.mute = True           # the sound key latches: checked in the next step
        gone = [n for n in ("keyEject", "keyFrame", "keyVideo", "keySubs") if self.find_item(n) is not None]
        prev = self.find_item("keyPrev")
        self.check("the panel without Open, Frame, Video and Subtitles (the picture's menu has them); "
                   "previous/next only with more than one file in the list",
                   not gone and self.find_item("keySubs") is None and prev.isVisible() == (self.pl.count > 1),
                   f"left on the panel={gone} prev shown={prev.isVisible()} list={self.pl.count}")
        names = ("keySettings", "keyPlay", "keyFast", "keySound", "keyShot", "keyEdit", "keyPrev", "keyPlaylist", "keyNext")
        caps = {n: self.find_item(n).property("flat") for n in names}
        self.check("every key of the panel is a rubber cap (the Braun concept)",
                   all(v is False for v in caps.values()), f"flat={caps}")
        keys, shot = self.find_item("keyPlay").parentItem().parentItem(), self.find_item("keyShot")
        lcd, vol, edit = self.find_item("lcdTime"), self.find_item("volume"), self.find_item("keyEdit")
        order = sorted(("keySettings", "keyPlay", "keyFast", "keySound", "volume", "lcdTime", "keyShot", "keyEdit"),
                       key=lambda n: self.find_item(n).mapToScene(QPointF(0, 0)).x())
        rules = [c for row in keys.childItems() for c in row.childItems() if c.isVisible() and c.width() <= 1.5 and c.height() > 10]
        after = lcd.mapToScene(QPointF(0, 0)).x() - vol.mapToScene(QPointF(vol.width(), 0)).x()
        self.check("the concept's order: settings first, play, fast, the sound, the time right after it, the screenshot, "
                   "the editor; groups apart by air, no rules; the glass as high as the caps",
                   order == ["keySettings", "keyPlay", "keyFast", "keySound", "volume", "lcdTime", "keyShot", "keyEdit"]
                   and not rules and after <= 24 and lcd.height() == shot.height(),
                   f"order={order} rules={len(rules)} volume->time={after:.0f} lcd={lcd.height()} caps={shot.height()}")
        txt = lcd.property("text") if lcd else ""
        self.check("the time reads as the scale does: 01:15 / 01:30, and a click is said to switch it",
                   re.fullmatch(r"01:1\d / 01:30", txt or "") is not None and "Click" in (lcd.property("tip") or ""),
                   f"lcd={txt!r} tip={lcd and lcd.property('tip')!r}")
        second = {n: self.find_item(n).property("second") for n in ("keyPlay", "keyFast", "keySound", "keyShot")}
        tips = {n: self.find_item(n).property("tip") for n in second}
        self.check("keys with a second action on the right button carry a corner mark and say so",
                   all(v is True for v in second.values()) and all("right click" in t for t in tips.values()),
                   f"second={second} tips={tips}")
        title = self.find_item("windowTitle")
        self.check("the file's name in the title bar: 12 px, letters not spread out",
                   title is not None and title.property("font").pixelSize() == 12
                   and title.property("font").letterSpacing() <= 0.3, f"title={title is not None}")

    def s_st4_menu(self):
        snd = self.find_item("keySound")
        lamp = self.find_item("lamp", snd)
        acc = QColor(self.win.findChild(QObject, "keyPlaylist").property("ink"))
        self.check("a latched key shows its sign in the accent, with no lamp beside it",
                   snd.property("latched") is True and lamp is None
                   and QColor(snd.property("ink")) != QColor(self.find_item("keyShot").property("ink"))
                   and self.near_accent(snd.property("ink")),
                   f"latched={snd.property('latched')} lamp={lamp is not None} "
                   f"ink={QColor(snd.property('ink')).name()} plain={QColor(self.find_item('keyShot').property('ink')).name()} "
                   f"list={acc.name()}")
        self.shot("st4_02_lamp")
        self.p.mpv.mute = False
        self.win.openSpeedMenu(None)

    def s_st4_menu_key(self):
        self.check("the key whose menu is open stays pressed in", self.find_item("keyFast").property("down") is True,
                   f"down={self.find_item('keyFast').property('down')}")

    def s_st4_edit_prep(self):
        # an ordinary window, wide enough for the fragments' words (a narrow one hides the
        # shift beside the range: there is no room for both)
        self.win.setWidth(1280)
        self.a.run("edit_mode")
        self.st4_osd = []
        self.p.osdMessage.connect(self.st4_osd.append)

    def s_st4_keys(self):
        keys = [self.find_item(n) for n in ("editIn", "editCut", "editOut", "editDelete")]
        signs = [k.property("glyph") for k in keys]
        self.check("the edit holds the whole file at once; nothing to save yet",
                   self.frags() == [("test_long.mkv", 0.0, 90.0)] and not self.ed.edited
                   and self.find_item("editSave").isEnabled() is False, f"frags={self.frags()} edited={self.ed.edited}")
        self.check("the strip's keys read as a ruler |← ✂ →| and a bin, signs not letters; their hints say what they take away",
                   signs == ["arrow-left-to-line", "scissors", "arrow-right-to-line", "trash-2"]
                   and all(k.property("label") == "" and k.property("caption") == "" for k in keys)
                   and all(k.property("tip") for k in keys),
                   f"signs={signs} tips={[k.property('tip') for k in keys]}")
        res = self.find_item("editPreview")
        self.check("the finished video's key says «Result»", res.property("caption") == "Result"
                   and res.property("glyph") == "clapperboard", f"caption={res.property('caption')!r}")

    def s_st4_preview(self):
        frags = self.ed.fragments
        lead = self.find_item("bandLead0")
        self.check("without loss the borders sit on keyframes (I at 25, X at 45 -> 20 and 40): what shows is what is "
                   "saved, nothing hatched before a piece, the OSD says so",
                   self.frags() == [("test_long.mkv", 20.0, 30.0), ("test_long.mkv", 40.0, 55.0)]
                   and (lead is None or lead.property("visible") is False or lead.property("width") <= 2)
                   and any("keyframe" in m for m in self.st4_osd),
                   f"frags={self.frags()} lead={lead and lead.property('width')} osd={self.st4_osd}")
        summary = self.find_item("editSummary")
        outside = [self.find_item(f"outside{i}") for i in range(3)]
        self.check("what stays out of the file is veiled on the timeline (before, between and after the fragments)",
                   all(o is not None and o.property("visible") is True for o in outside),
                   f"outside={[o is not None for o in outside]}")
        line = (summary.property("text") if summary else "") + (self.find_item("editMode").property("text") or "")
        self.check("one line says what goes into the file: «To the file: 2 fragments · LOSSLESS»",
                   summary is not None and summary.property("visible") is True and line == "To the file: 2 fragments · LOSSLESS",
                   f"line={line!r} fragments={len(frags)}")
        head = self.find_item("codecTitle")
        seg = self.find_item("editCodec")
        cut = [t for t in self.texts_in(seg) if t.property("implicitWidth") > t.parent().property("width") - 4]
        self.check("the codec choice is titled «Encoding» and no option is cut off",
                   head is not None and head.property("text") == "Encoding" and not cut,
                   f"title={head and head.property('text')!r} cut={[t.property('text') for t in cut]}")
        self.shot("st4_03_edit")
        self.a.run("edit_preview")

    def texts_in(self, item):
        out = []
        for c in item.childItems():
            if c.metaObject().className() == "QQuickText":
                out.append(c)
            out += self.texts_in(c)
        return out

    def s_st4_previewing(self):
        total = self.find_item("editTotal")
        bar = self.find_item("resultBar")
        self.check("the result plays from its start: its length reads as time played / length, a bar shows where in it",
                   total is not None and re.fullmatch(r"0:\d\d\.\d / 0:25\.0", total.property("text") or "") is not None
                   and self.ed.previewing == 0 and bar is not None and bar.property("visible") is True,
                   f"total={total and total.property('text')!r} previewing={self.ed.previewing} "
                   f"bar={bar is not None and bar.property('visible')}")
        self.shot("st4_04_previewing")
        self.a.run("edit_preview")

    def s_st4_close_x(self):
        self.ed.select(1)
        x = self.find_item("fragClose1")
        self.n0 = len(self.ed.frags)
        self.st4_x = x is not None and x.property("visible") is True and self.find_item("fragClose0") is not None \
            and self.find_item("fragClose0").property("visible") is False
        if x is not None:
            self.click_item(x)

    def s_st4_closed(self):
        self.check("the chosen fragment has a small × that takes it out", self.st4_x and len(self.ed.frags) == self.n0 - 1,
                   f"x shown only on it={self.st4_x} fragments {self.n0}->{len(self.ed.frags)}")

    def s_st4_save(self):
        self.asked, self.ran = [], []
        self.ed.saveRequested.connect(self._st4_asked)
        self.a.performed.connect(self.ran.append)
        self.want_saved = self.ed.suggestedPath()
        self.key("S", Qt.ControlModifier | Qt.ShiftModifier)
        self.st4_started = self.ed.exporting
        # at once, in the same step: the built exe once finished this short save within 100 ms,
        # and the right button then asked where to save (a file dialog on the test machine)
        if self.st4_started:
            self.s_st4_save_as()

    def _st4_asked(self):
        self.asked.append(1)

    def s_st4_save_as(self):
        # the right button asks where to save; tried while this save runs, so that no file
        # dialog opens on the test machine (asking is refused while a save runs)
        key = self.find_item("editSave")
        c = key.mapToScene(QPointF(key.width() / 2, key.height() / 2))
        QTest.mouseClick(self.win, Qt.RightButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))

    def s_st4_saved(self):
        self.ed.saveRequested.disconnect(self._st4_asked)
        self.a.performed.disconnect(self.ran.append)
        out = Path(self.want_saved)
        self.check("Ctrl+Shift+S saves beside the source at once, under a new name, without asking; "
                   "the right button is «Save as»",
                   self.st4_started and not self.asked and out.parent == Path(self.media).parent
                   and out.exists() and self.ed.saved == str(out) and "edit_save_as" in self.ran
                   and "right click" in (self.find_item("editSave").property("tip") or ""),
                   f"started={self.st4_started} asked={self.asked} saved={self.ed.saved!r} want={out.name!r} "
                   f"ran={self.ran} tip={self.find_item('editSave').property('tip')!r}")
        out.unlink(missing_ok=True)      # the test media folder stays as it was

    def s_st4_done(self):
        self.p.osdMessage.disconnect(self.st4_osd.append)
        self.ed.frags = []
        self.ed.close()

    # ---- the tails of stages 1-4: numbers and other files on the timeline, the keyframe
    # said after O, the LCD in the cream theme, solid transport signs, 10 px scale labels,
    # Settings apart from the navigation, P from History, Snap Layouts on the maximize key
    # ---- feedback 4 (0.11.1): what a person does with the mouse, which the keyboard checks
    # above never touched (the picture card's sliders set nothing for a release)
    def fb4_steps(self):
        return [
            (0, self.s_fb4_list_one), (1500, lambda: self.pl.add([self.medias[-1]], True)), (1500, self.s_fb4_list_one_chk),
            (0, lambda: self.show_list(False)), (300, lambda: self.pl.add([str(Path(self.media).parent / "test_long.mkv")], True)),
            # the picture's place is known once mpv has drawn the opened file
            (1800, self.until(lambda: "ml" in (self.st("osd") or {}), 3, 100)), (0, self.s_fb4_fit),
            (0, self.s_fb4_prep), (1500, lambda: self.key("V", Qt.ShiftModifier)), (600, self.s_fb4_rail),
            (400, self.s_fb4_railed), (0, lambda: self.key("Esc")),
            (400, self.s_fb4_left), (500, self.s_fb4_paused), (0, lambda: self.settings.set("leftClick", "chrome")),
            (300, self.s_fb4_left), (900, self.s_fb4_hidden), (0, self.s_fb4_left), (900, self.s_fb4_shown),
            (0, lambda: self.settings.set("leftClick", "pause")),
            (0, lambda: setattr(self.p.mpv, "pause", True)),
            (300, lambda: self.s_fb4_button(Qt.MiddleButton)), (300, lambda: self.s_fb4_nudge(0)), (600, self.s_fb4_full),
            # a real move inside the two quiet seconds; past them, a hand resting there (8 px), then a move
            (0, self.s_fb4_quiet_move), (300, self.s_fb4_quiet),
            (0, self.until(lambda: time.monotonic() - self.click_t > 2.2, 3, 20)),
            (0, lambda: self.s_fb4_nudge(68)), (400, self.s_fb4_still_bare),
            (0, lambda: self.s_fb4_nudge(120)), (400, self.s_fb4_woken),
            (0, lambda: self.s_fb4_button(Qt.MiddleButton)), (900, self.s_fb4_windowed),
            # leaving from the bare picture: no full-screen frame with the panels
            (0, self.s_fb4_watch_panels), (0, lambda: self.s_fb4_button(Qt.MiddleButton)),
            (900, lambda: self.s_fb4_button(Qt.MiddleButton)), (900, self.s_fb4_left_bare),
            # every frame Windows composes, in and out: none of neither state (the owner's slow-motion videos)
            (0, self.s_fb4_cap_start), (300, lambda: self.s_fb4_button(Qt.MiddleButton)),
            (900, lambda: self.s_fb4_button(Qt.MiddleButton)), (900, self.s_fb4_cap_check),
            (0, self.s_fb4_back), (700, self.until(lambda: self.st("position") < self.pos0 - 2, 3.0, 100)),
            (0, self.s_fb4_backed),
            (0, lambda: self.click("keySettings")), (600, lambda: self.settings_page(1, "setLang")),
            (700, self.s_fb4_settings), (0, self.s_fb4_lang),
            (500, self.s_fb4_lang_menu), (500, self.s_fb4_reset), (300, self.s_fb4_reset2), (300, self.s_fb4_reset_done),
            (0, lambda: self.key("Esc")), (300, self.s_fb4_thumb),
            (0, self.s_fb4_ed_prep), (1500, lambda: self.key("E", Qt.ControlModifier)), (600, lambda: self.key("R", Qt.ControlModifier)),
            (1200, self.s_fb4_turned), (0, lambda: self.ed.setFrame("blur")), (1200, self.s_fb4_framed),
            (0, self.s_fb4_logo), (800, self.s_fb4_logo_shown), (0, self.s_fb4_save_framed),
            (500, self.until(lambda: not self.ed.exporting, 90)), (0, self.s_fb4_saved_framed),
            (0, lambda: self.key("Z", Qt.ControlModifier)), (0, lambda: self.key("Z", Qt.ControlModifier)),
            (0, lambda: self.key("Z", Qt.ControlModifier)), (1200, self.s_fb4_undone),
            (0, lambda: self.ed.close()), (900, self.s_fb4_ed_closed),
        ]

    def s_fb4_list_one(self):
        self.settings.set("openAdds", self.list_default)
        self.pl.add([self.media], True)

    def s_fb4_fit(self):
        osd = self.st("osd") or {}
        self.check("a picture narrower than the window's least width grows to it: edge to edge with the panel, no side bars",
                   self.win.width() == self.win.property("minimumWidth") and osd.get("ml", 9) <= 1 and osd.get("mr", 9) <= 1,
                   f"window={self.win.width()}x{self.win.height()} bars left={osd.get('ml')} right={osd.get('mr')}")

    def s_fb4_list_one_chk(self):
        clear = self.find_item("plClear")
        self.check("by default an opened file replaces the list: it holds only what plays; the list has a «Clear» key",
                   self.list_default is False and self.pl.count == 1 and clear is not None,
                   f"default joins={self.list_default} rows={self.pl.count} clear key={clear is not None}")
        self.settings.set("openAdds", True)

    def s_fb4_prep(self):
        if self.ed.active:
            self.ed.close()
        self.win.setWidth(1280)
        self.win.setHeight(760)
        self.win.setProperty("playlistShown", False)
        self.pl.add([self.media], True)

    def s_fb4_rail(self):
        rail = self.find_item("rail_brightness")
        self.rail_mid = rail is not None and abs(rail.property("shown") - 0.5) < 0.02 if self.st("brightness") == 0 else None
        self.click_item(rail, (rail.width() * 0.75, rail.height() / 2))

    def s_fb4_railed(self):
        b = self.st("brightness")
        self.check("the picture card's brightness slider: at 0 its cap stands in the middle, a click at 3/4 sets +50",
                   self.rail_mid is not False and 45 <= b <= 55, f"middle={self.rail_mid} brightness={b}")
        self.shot("fb4_01_brightness")
        self.p.resetColors()

    def video_point(self):
        return QPoint(self.win.width() // 2, self.win.height() // 3)

    def s_fb4_left(self):
        self.paused0 = self.st("paused")
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, self.video_point())

    def s_fb4_paused(self):
        self.check("a click on the picture pauses (the default) and the panels stay",
                   self.st("paused") is (not self.paused0) and self.win.property("uiHidden") is False,
                   f"paused {self.paused0}->{self.st('paused')} hidden={self.win.property('uiHidden')}")
        self.p.mpv.pause = self.paused0

    def s_fb4_hidden(self):
        panel = self.win.findChild(QObject, "panel")
        self.check("with «hide panels» set, a click hides them, the picture takes the window, playback goes on",
                   self.win.property("uiHidden") is True and panel.property("visible") is False
                   and self.st("paused") == self.paused0, f"hidden={self.win.property('uiHidden')} "
                   f"panel={panel.property('visible')} paused {self.paused0}->{self.st('paused')}")
        self.shot("fb4_02_hidden")

    def s_fb4_shown(self):
        self.check("the next click brings them back", self.win.property("uiHidden") is False
                   and self.win.findChild(QObject, "panel").property("visible") is True)

    def s_fb4_button(self, button):
        self.click_t = time.monotonic()
        QTest.mouseClick(self.win, button, Qt.NoModifier, self.video_point())
        # at once, before the window has grown: the picture is already laid out for full screen
        self.margin_at_click = (self.p.mpv["video-margin-ratio-top"], self.p.mpv["video-margin-ratio-bottom"])
        self.panels_at_click = self.win.property("chromeShown")
        # the panel and the title bar gone at once, not fading out over the window as it grows
        self.opacity_at_click = (self.find_item("panel").opacity(), self.find_item("windowTitle").parentItem().opacity())


    def s_fb4_full(self):
        self.check("the middle button goes full screen (the default) on the bare picture: no panels, and the picture "
                   "laid out once, for full screen, at the click (no jerk)",
                   self.win.property("fs") is True and self.win.property("chromeShown") is False
                   and self.margin_at_click == (0.0, 0.0) and self.panels_at_click is False
                   and self.opacity_at_click == (0.0, 0.0),
                   f"fs={self.win.property('fs')} panels={self.win.property('chromeShown')} "
                   f"at the click: margins={self.margin_at_click} panels={self.panels_at_click} "
                   f"opacity (panel, title)={self.opacity_at_click}")
        self.shot("fb4_05_fullscreen_bare")
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(self.win.winId())), ctypes.byref(r))
        g, dpr = self.win.screen().geometry(), self.win.screen().devicePixelRatio()
        mon = (round(g.width() * dpr), round(g.height() * dpr))
        if self.win.property("videoD3D"):
            self.check("full screen through Direct3D covers the monitor exactly (Windows draws no outline then)",
                       (r.right - r.left, r.bottom - r.top) == mon,
                       f"window={r.right - r.left}x{r.bottom - r.top} monitor={mon[0]}x{mon[1]}")
        else:
            self.check("full screen through OpenGL is 1 px taller than the monitor: never an exact cover, which "
                       "NVIDIA's OpenGL takes past the desktop (a blackout, black in screen capture)",
                       (r.right - r.left, r.bottom - r.top) == (mon[0], mon[1] + 1),
                       f"window={r.right - r.left}x{r.bottom - r.top} monitor={mon[0]}x{mon[1]}")
            self.check("full screen has no Windows outline round the black, nor rounded corners (switched off, accepted)",
                       self.win.property("outlineOff") is True, f"outlineOff={self.win.property('outlineOff')}")
        # paused, one frame is drawn after the window grows: it must be drawn at the new size
        osd, dpr = self.st("osd") or {}, self.win.effectiveDevicePixelRatio()
        want = (round(self.win.width() * dpr), round(self.win.height() * dpr))
        self.check("a paused picture is drawn at the full screen's size, not the window's it had (the owner's screenshots)",
                   self.st("paused") is True and (osd.get("w"), osd.get("h")) == want,
                   f"paused={self.st('paused')} drawn={osd.get('w')}x{osd.get('h')} window={want[0]}x{want[1]}")

    def s_fb4_nudge(self, d):
        c = self.video_point()
        QTest.mouseMove(self.win, QPoint(c.x() + d, c.y()))

    def s_fb4_still_bare(self):
        self.check("full screen: a hand resting on the mouse (a few pixels) does not bring the panels back",
                   self.win.property("chromeShown") is False, f"panels={self.win.property('chromeShown')}")

    def s_fb4_woken(self):
        title = self.find_item("windowTitle").parentItem()
        self.check("a real move brings the panel; the window's keys at the top only when the pointer goes up there",
                   self.win.property("chromeShown") is True and title.property("opacity") == 0,
                   f"panels={self.win.property('chromeShown')} title opacity={title.property('opacity')}")
        self.shot("fb4_09_fullscreen_woken")

    def s_fb4_quiet_move(self):
        self.quiet_move_at = time.monotonic() - self.click_t
        self.s_fb4_nudge(60)

    def s_fb4_quiet(self):
        self.check("for two seconds after the middle button even a real move does not bring the panels",
                   self.win.property("chromeShown") is False and self.quiet_move_at < 2.0,
                   f"panels={self.win.property('chromeShown')} moved at {self.quiet_move_at:.2f} s")

    def s_fb4_watch_panels(self):
        self.panel_changes = []
        # (panels shown, the window still at the screen's full size) as each change happens
        self.win.chromeShownChanged.connect(lambda: self.panel_changes.append(
            (self.win.property("chromeShown"), self.win.property("fullSized"))))
        # and how visible the panel is a moment after it comes back: at once, not fading in
        self.panel_back = None
        self.win.chromeShownChanged.connect(lambda: QTimer.singleShot(
            40, lambda: setattr(self, "panel_back", self.find_item("panel").opacity())))

    def s_fb4_windowed(self):
        self.check("and back to the window, with its outline and round corners again",
                   self.win.property("fs") is False
                   and (self.win.property("videoD3D") or self.win.property("outlineOff") is False),
                   f"outlineOff={self.win.property('outlineOff')}")

    def s_fb4_cap_start(self):
        # Desktop Duplication in a process of its own, so as not to slow the window it watches;
        # the built program carries no Python to run it
        self.cap = None
        if getattr(sys, "frozen", False):
            return
        self.p.mpv.pause = True     # a still picture: each composed frame is one state or a glitch
        self.cap = subprocess.Popen([sys.executable, "-m", "oyplayer.framecap", "DISPLAY3", str(self.out)],
                                    cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True)
        self.cap.stdout.readline()  # «ready»

    def s_fb4_cap_check(self):
        if self.cap is None:
            print("  (the composed frames are not watched in the built program)")
            return
        out, _ = self.cap.communicate("stop\n", timeout=30)
        res = json.loads(out.strip().splitlines()[-1])
        self.check("in and out of full screen Windows composes no frame of neither state: no old picture in the "
                   "corner of the grown window, nor a big one cut by the small window (framecap.png if any)",
                   res["glitches"] == [] and res["states"] >= 2,
                   f"frames={res['frames']} states={res['states']} glitches at {res['glitches']} s")

    def s_fb4_left_bare(self):
        self.check("in and out of full screen the panels step aside at the click, before the window grows, and come "
                   "back at once once it is small again",
                   self.panel_changes == [(False, False), (True, False)] and self.panel_back == 1.0
                   and self.win.property("fs") is False and self.win.property("chromeShown") is True,
                   f"panels changed (shown, full size)={self.panel_changes} panel 40 ms after={self.panel_back} "
                   f"fs={self.win.property('fs')} panels={self.win.property('chromeShown')}")

    def s_fb4_back(self):
        self.p.seek(10.0)
        QTimer.singleShot(500, lambda: setattr(self, "pos0", self.st("position")))
        QTimer.singleShot(520, lambda: self.s_fb4_button(Qt.BackButton))

    def s_fb4_backed(self):
        self.check("the mouse's back button seeks back (the default)", self.st("position") < self.pos0 - 2,
                   f"{self.pos0:.1f}->{self.st('position'):.1f}")

    def s_fb4_settings(self):
        sp, x = self.win.findChild(QObject, "settingsPanel"), self.find_item("settingsClose")
        card = sp.property("contentItem")
        tl = card.mapToScene(QPointF(card.width(), 0))
        c = x.mapToScene(QPointF(x.width(), 0))
        self.check("the settings' close key is in the card's upper right corner",
                   abs(c.x() - tl.x()) <= 16 and abs(c.y() - tl.y()) <= 16,
                   f"key's corner {c.x():.0f},{c.y():.0f} card's {tl.x():.0f},{tl.y():.0f}")
        self.shot("fb4_03_settings_window")

    def s_fb4_lang(self):
        self.lang0 = self.settings["lang"]
        self.click_item(self.find_item("setLang"))

    def s_fb4_lang_menu(self):
        menu = self.win.findChild(QObject, "choiceMenu")
        items = menu.property("items") if menu else []
        items = items.toVariant() if hasattr(items, "toVariant") else items
        names = [i.get("text") for i in items] if items else []
        self.check("the language is a list: Windows' own and each language by its own name",
                   menu is not None and menu.property("visible") is True and "English" in names and "Українська" in names
                   and len(names) == 3, f"menu={menu is not None and menu.property('visible')} names={names}")
        self.shot("fb4_04_lang_list")
        if menu is not None:
            QMetaObject.invokeMethod(menu, "close")      # Esc would close the settings as well
        self.settings.set("lang", self.lang0)

    def s_fb4_reset(self):
        self.settings.set("fitWindow", False)
        self.settings.set("onTop", "always")
        self.click_item(self.find_item("resetSection"))

    def s_fb4_reset2(self):
        self.reset_armed = self.settings["fitWindow"] is False and self.find_item("resetSection").property("armed") is True
        self.click_item(self.find_item("resetSection"))

    def s_fb4_reset_done(self):
        self.check("«Defaults» asks for a second press, then puts the section back (window fit on, on top never), "
                   "the language stays", self.reset_armed and self.settings["fitWindow"] is True
                   and self.settings["onTop"] == "never" and self.settings["lang"] == self.lang0,
                   f"armed first={self.reset_armed} fit={self.settings['fitWindow']} onTop={self.settings['onTop']}")

    def s_fb4_ed_prep(self):
        self.ed.frags, self.ed._notes = [], []
        self.ed._rotate, self.ed._frame = 0, "asis"
        self.p.mpv.pause = True
        self.pl.add([self.media], True)          # test720.mp4: 1280×720

    def edview(self):
        return any(f.get("label") == "edview" for f in (self.p.mpv["vf"] or []))

    def s_fb4_turned(self):
        self.check("Ctrl+R turns the picture a quarter: on screen 720×1280, by a filter of the edit",
                   self.ed.rotation == 90 and self.edview() and (self.st("videoW"), self.st("videoH")) == (720, 1280),
                   f"rotation={self.ed.rotation} view={self.edview()} shown={self.st('videoW')}x{self.st('videoH')}")
        self.shot("fb4_06_turned")

    def s_fb4_framed(self):
        self.check("16:9 over a blurred copy: the turned picture stands in a 1280×720 frame",
                   self.ed.frame == "blur" and (self.st("videoW"), self.st("videoH")) == (1280, 720),
                   f"frame={self.ed.frame} shown={self.st('videoW')}x{self.st('videoH')}")
        self.shot("fb4_07_blur_frame")

    def s_fb4_logo(self):
        img = QImage(64, 32, QImage.Format_ARGB32)
        img.fill(QColor(255, 0, 0, 255))
        self.logo_png = self.out / "logo.png"
        img.save(str(self.logo_png))
        self.logo_i = self.ed.addImage(str(self.logo_png))

    def s_fb4_logo_shown(self):
        n = self.ed.notes[self.logo_i] if 0 <= self.logo_i < len(self.ed.notes) else {}
        logo = self.find_item(f"logo{self.logo_i}")
        img = capture(int(self.win.winId()))
        mid = logo.mapToScene(QPointF(logo.width() / 2, logo.height() / 2)) if logo is not None else QPointF()
        dpr = self.win.devicePixelRatio()
        px = img.pixelColor(int(mid.x() * dpr), int(mid.y() * dpr))
        self.check("the logo shows on the frame as it is (red here), not only in the saved file",
                   logo is not None and logo.property("progress") == 1.0 and px.red() > 180 and px.green() < 90,
                   f"loaded={logo and logo.property('progress')} source={logo and logo.property('source')} pixel={px.name()}")
        self.check("a logo goes to the upper right, 15 % of the frame high, over the whole file; saving says why it re-encodes",
                   n.get("kind") == "image" and abs(n["pts"][1][1] - n["pts"][0][1] - 0.15) < 0.01 and n["pts"][1][0] > 0.9
                   and n["a"] == 0 and logo is not None and logo.isVisible()
                   and self.ed.reason == "has a logo" and not self.ed.lossless,
                   f"note={n} shown={logo is not None and logo.isVisible()} reason={self.ed.reason!r}")
        self.shot("fb4_08_logo")

    def s_fb4_save_framed(self):
        self.ed.frags = [dict(self.ed.frags[0], start=2.0, end=4.0)]
        self.ed._ask(self.ed.frags[0]["path"], 2.0)    # a fragment set by hand: its keyframe is not read yet
        self.ed.changed.emit()
        self.framed_out = self.out / "framed.mp4"
        self.ed.exportTo(str(self.framed_out))

    def s_fb4_saved_framed(self):
        info = ffprobe(self.framed_out) if self.framed_out.exists() else {}
        v = next((x for x in info.get("streams", []) if x["codec_type"] == "video"), {})
        frame = self.out / "framed.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(self.framed_out), "-frames:v", "1", str(frame)],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        img = QImage(str(frame))
        n = self.ed.notes[self.logo_i]
        at = QPoint(int((n["pts"][0][0] + n["pts"][1][0]) / 2 * img.width()), int((n["pts"][0][1] + n["pts"][1][1]) / 2 * img.height())) \
            if not img.isNull() else QPoint()
        c = img.pixelColor(at) if not img.isNull() else QColor()
        self.check("saved turned, in a 16:9 frame over the blur, with the logo where it was shown",
                   (v.get("width"), v.get("height")) == (1280, 720) and c.red() > 180 and c.green() < 90 and c.blue() < 90,
                   f"saved={v.get('width')}x{v.get('height')} logo pixel={c.name() if c.isValid() else None} at {at.x()},{at.y()}")

    def s_fb4_undone(self):
        self.check("Ctrl+Z takes back the logo, the frame and the turn, one step each",
                   self.ed.rotation == 0 and self.ed.frame == "asis" and not any(n["kind"] == "image" for n in self.ed.notes)
                   and not self.edview(), f"rotation={self.ed.rotation} frame={self.ed.frame} view={self.edview()}")

    def s_fb4_ed_closed(self):
        self.check("closing the editor leaves the picture as the file has it",
                   not self.edview() and (self.st("videoW"), self.st("videoH")) == (1280, 720),
                   f"view={self.edview()} shown={self.st('videoW')}x{self.st('videoH')}")

    def s_fb4_thumb(self):
        thumbs = sorted((self.out / "home" / "thumbs").glob("*.png"))
        img = QImage(str(thumbs[0])) if thumbs else QImage()
        self.check("the playlist's frames have round corners (transparent in the corner, whole in the middle)",
                   not img.isNull() and img.pixelColor(1, 1).alpha() == 0 and img.pixelColor(2, 2).alpha() == 0
                   and img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255,
                   f"thumbs={len(thumbs)} corner={img.pixelColor(1, 1).alpha() if not img.isNull() else None}")

    def tails_steps(self):
        long_mkv = str(Path(self.media).parent / "test_long.mkv")

        def seek(t):
            return lambda: self.p.seek(t)

        return [
            (0, lambda: self.s_st4_prep(long_mkv)), (1800, lambda: setattr(self.p.mpv, "pause", True)),
            (0, self.s_tl_edit)] + self.keep_steps([(25.0, 35.0), (45.0, 55.0)]) + [(400, self.s_tl_marks),
            (0, lambda: self.pl.add([self.media], True)), (1500, self.s_tl_other), (1500, self.s_tl_other_done),
            (0, self.s_tl_panel), (0, lambda: self.win.setWidth(760)), (500, self.s_tl_narrow),
            (0, lambda: self.settings.set("theme", "light")), (700, self.s_tl_lcd),
            (0, lambda: self.settings.set("theme", "dark")), (0, lambda: QMetaObject.invokeMethod(self.win, "showPage", Q_ARG("QVariant", 1))),
            (300, lambda: self.key("P")), (300, self.s_tl_list), (0, self.s_tl_snap), (800, self.s_tl_snapped),
            (800, self.s_tl_done),
        ]

    def s_tl_edit(self):
        self.win.setWidth(1280)
        self.a.run("edit_mode")
        self.tl_osd = []
        self.p.osdMessage.connect(self.tl_osd.append)

    def s_tl_marks(self):
        said = [m for m in self.tl_osd if "keyframe" in m]
        self.check("without loss a border moves to the keyframe, and the OSD says where: I at 25 -> 0:20.0",
                   any("0:20.0" in m for m in said), f"osd={self.tl_osd}")
        nums = [self.find_item(f"bandNum{i}") for i in range(2)]
        self.check("the fragments' blocks on the clip track carry their numbers 1 and 2",
                   all(n is not None and n.property("visible") is True for n in nums)
                   and [n.property("text") for n in nums] == ["1", "2"],
                   f"nums={[n and (n.property('visible'), n.property('text')) for n in nums]}")
        marks = self.find_item("scaleMarks")
        hit = []
        for n in (n for n in nums if n is not None):
            nx = n.mapToScene(QPointF(0, 0)).x()
            for it in marks.childItems():
                if it.objectName().startswith("scaleLabel") and it.property("visible"):
                    lx, ly = it.mapToScene(QPointF(0, 0)).x(), it.mapToScene(QPointF(0, 0)).y()
                    ny = n.mapToScene(QPointF(0, 0)).y()
                    if lx < nx + n.width() + 2 and nx < lx + it.width() + 2 and ly < ny + n.height() and ny < ly + it.height():
                        hit.append(it.property("text"))
        self.check("a fragment's number does not cover a scale label", not hit, f"covered={hit}")
        self.shot("tl_01_numbers")

    def s_tl_other(self):
        tag = self.find_item("otherFrags")
        self.tl_other = tag is not None and tag.property("visible") is True \
            and "2 fragments" in (tag.property("text") or "") and "test_long.mkv" in (tag.property("text") or "")
        self.check("with another file playing, the timeline says the edit's fragments are in another file, and which",
                   self.tl_other, f"tag={tag is not None and (tag.property('visible'), tag.property('text'))!r}")
        self.shot("tl_02_other_file")
        if tag is not None:
            self.click_item(tag)

    def s_tl_other_done(self):
        self.check("a click on that line opens the file with the fragments", self.name() == "test_long.mkv",
                   f"playing {self.name()}")
        self.p.osdMessage.disconnect(self.tl_osd.append)
        self.ed.frags = []
        self.ed.close()

    def s_tl_panel(self):
        play, prev, nxt, ff = (self.find_item(n) for n in ("keyPlay", "keyPrev", "keyNext", "keyFast"))
        g = lambda k: k.property("glyph")
        sign = self.find_item("sign", play)
        self.check("the transport signs are one family of line icons (Lucide), play and pause filled and drawn sharp",
                   g(play) in ("play", "pause") and play.property("solid") is True and g(prev) == "skip-back"
                   and g(nxt) == "skip-forward" and g(ff) == "fast-forward" and sign is not None
                   and sign.property("progress") == 1.0 and sign.property("source").toString().startswith("image://icon/"),
                   f"play={g(play)!r} prev={g(prev)!r} next={g(nxt)!r} "
                   f"sign={sign is not None and (sign.property('progress'), sign.property('source').toString())}")
        font = self.find_item("scaleMarks").property("font")
        self.check("the time scale's labels are 10 px of IBM Plex Mono", font.pixelSize() == 10 and font.family() == "IBM Plex Mono",
                   f"px={font.pixelSize()} family={font.family()!r}")
        import ctypes
        pref = ctypes.c_int(0)
        ctypes.WinDLL("dwmapi").DwmGetWindowAttribute(ctypes.c_void_p(int(self.win.winId())), 33, ctypes.byref(pref), 4)
        self.check("the window asks Windows 11 for rounded corners (DWMWCP_ROUND)", pref.value == 2, f"corner preference={pref.value}")
        gaps = self.panel_gaps()
        self.check("one step between every two things on the panel, settings first",
                   gaps and max(gaps) - min(gaps) <= 1 and min(gaps) >= 8, f"gaps={gaps}")
        self.shot("tl_03_panel")

    def panel_gaps(self):
        """The space between each two neighbours in the panel's left row (keys, slider, time)."""
        row = self.find_item("keySettings").parentItem()
        items = sorted((c for c in row.childItems() if c.isVisible() and c.width() > 0), key=lambda c: c.x())
        return [round(b.x() - (a.x() + a.width()), 1) for a, b in zip(items, items[1:])]

    def s_tl_narrow(self):
        ed, st, play, prev, lst = (self.find_item(n) for n in ("keyEdit", "keySettings", "keyPlay", "keyPrev", "keyPlaylist"))
        right = prev if prev.isVisible() else lst
        free = right.mapToScene(QPointF(0, 0)).x() - ed.mapToScene(QPointF(ed.width(), 0)).x()
        gaps = self.panel_gaps()
        self.check("in a 760 px window the step stays one and nothing runs into anything",
                   self.win.width() == 760 and free > 4 and gaps and max(gaps) - min(gaps) <= 1 and min(gaps) >= 6,
                   f"width={self.win.width()} free={free} gaps={gaps}")
        self.shot("tl_04_narrow")
        self.win.setWidth(1280)

    def s_tl_lcd(self):
        img = capture(int(self.win.winId()))
        self.shot("tl_05_lcd_light")
        lcd = self.find_item("lcdTime")
        r = self.region(img, lcd)
        dpr = self.win.devicePixelRatio()
        glass = self.oklch_of(r.pixelColor(round(5 * dpr), r.height() // 2))
        want = self.oklch_of(QColor("#9FA89A"))
        ink = min(self.oklch_of(r.pixelColor(x, y))[0] for y in range(r.height()) for x in range(r.width()))
        self.check("in the cream theme the time sits in the same grey-green glass, its figures dark",
                   abs(glass[0] - want[0]) < 0.06 and abs(glass[2] - want[2]) < 25 and ink < 0.4,
                   f"glass L={glass[0]:.2f} h={glass[2]:.0f} want L={want[0]:.2f} h={want[2]:.0f} darkest L={ink:.2f}")

    def s_tl_list(self):
        panel = self.win.findChild(QObject, "playlistPanel")
        self.check("P with History open turns to the List and keeps the panel open",
                   self.win.property("playlistShown") is True and panel.property("tab") == 0,
                   f"shown={self.win.property('playlistShown')} tab={panel.property('tab')}")
        self.show_list(False)

    def s_tl_snap(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32")
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.SendMessageW.restype = ctypes.c_ssize_t
        hwnd, dpr = int(self.win.winId()), self.win.devicePixelRatio()
        key = self.find_item("keyMax")

        def lp(item):
            c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            pt = wintypes.POINT(round(c.x() * dpr), round(c.y() * dpr))
            u.ClientToScreen(hwnd, ctypes.byref(pt))
            return ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
        on = u.SendMessageW(hwnd, 0x84, 0, lp(key)) if key is not None else 0          # WM_NCHITTEST
        hot = key is not None and key.property("hot") is True
        off = u.SendMessageW(hwnd, 0x84, 0, lp(self.find_item("windowTitle")))
        cold = key is not None and key.property("hot") is False
        maxbox = bool(u.GetWindowLongW(hwnd, -16) & 0x10000)                          # WS_MAXIMIZEBOX
        self.check("Windows is told the maximize key is a maximize button (HTMAXBUTTON): Snap Layouts open on it",
                   on == 9 and off != 9 and hot and cold and maxbox,
                   f"on key={on} on title={off} lit={hot} unlit={cold} maximize box={maxbox}")
        if on == 9:
            # posted, as a real click arrives (Qt filters mouse messages only off the queue; a
            # sent WM_NCLBUTTONDOWN reached Windows' modal button tracking and hung the test).
            # Should the filter miss them anyway, a mouse release ends that tracking.
            u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            u.PostMessageW(hwnd, 0xA1, 9, lp(key))       # WM_NCLBUTTONDOWN / UP on HTMAXBUTTON
            u.PostMessageW(hwnd, 0xA2, 9, lp(key))
            self.snap_rescue = threading.Timer(3.0, lambda: u.PostMessageW(hwnd, 0x0202, 0, 0))   # WM_LBUTTONUP
            self.snap_rescue.start()

    def s_tl_snapped(self):
        rescue = getattr(self, "snap_rescue", None)
        if rescue is not None:
            rescue.cancel()
        self.check("a click on it still maximizes the window", self.win.visibility() == QWindow.Maximized,
                   f"visibility={self.win.visibility()}")
        self.win.showNormal()

    def s_tl_done(self):
        self.check_on_own_screen("after the maximize test the window is back on its own screen")

    # ---- the update (updater.py, update.py): a release page on 127.0.0.1 stands in for GitHub,
    # and a throwaway key for the release key
    def upd_steps(self):
        up = self.m8["updater"]

        def wait(*states):
            return self.until(lambda: up.state in states, 15, 100)

        def press():
            self.click_item(self.find_item("updateKey"))
        return [
            (0, self.s_up_core), (0, self.s_up_serve), (0, self.s_about), (600, press), (0, wait("available")),
            (300, self.s_up_found), (0, press), (0, wait("installing", "failed")), (300, self.s_up_installed),
            # the key comes back from hidden ("installing"): its row is laid out on the next frame
            (0, lambda: self.s_up_feed("forged")), (300, press), (0, wait("available")), (300, press),
            (0, wait("failed")), (300, self.s_up_forged),
            (0, lambda: self.s_up_feed("same")), (0, press), (0, wait("current", "failed")), (300, self.s_up_current),
            (0, lambda: self.s_up_feed("down")), (0, press), (0, wait("failed")), (300, self.s_up_offline),
            (0, self.s_up_done),
        ]

    def up_text(self):
        return self.find_item("updateText").property("text")

    def s_up_core(self):
        from . import __version__, update
        from .settings import DEFAULTS
        self.check("versions compare as numbers: 0.11.0 > 0.10.0 > 0.9.9, 1.0 > 0.99.9, not newer than itself",
                   update.is_newer("0.11.0", "0.10.0") and not update.is_newer("0.9.9", "0.10.0")
                   and update.is_newer("v1.0", "0.99.9") and not update.is_newer(__version__, __version__))
        refused = []
        for url in ("http://github.com/electronic-mars/OY", "https://example.com/latest.json"):
            try:
                update._allow(url)
            except ValueError:
                refused.append(url)
        self.check("updates come only over https and only from GitHub", len(refused) == 2
                   and update._allow(update.FEED) == update.FEED, f"refused={refused}")
        self.check("the player carries the release key's public half, not the self-test's",
                   len(update.PUBLIC_KEY) == 64 and update.PUBLIC_KEY != UPD_PUB)
        self.up_saved = (update.FEED, update._allow, update.PUBLIC_KEY)
        update.PUBLIC_KEY = UPD_PUB
        f = self.out / "upd_payload.bin"
        f.write_bytes(UPD_PAYLOAD)
        good = update.verify(f, bytes.fromhex(UPD_SIG))
        f.write_bytes(UPD_PAYLOAD[:500] + b"X" + UPD_PAYLOAD[501:])
        changed = update.verify(f, bytes.fromhex(UPD_SIG))
        short = update.verify(f, bytes.fromhex(UPD_SIG)[:63])
        self.check("Windows accepts the signed file and refuses it with one byte changed or a cut signature",
                   good and not changed and not short, f"signed={good} changed={changed} cut={short}")
        self.check("the daily look is on by default and does not run in a self-test",
                   DEFAULTS["updateCheck"] is True and not self.m8["updater"]._auto.isActive())

    def s_up_serve(self):
        from . import __version__, update
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _FilesHandler)
        base = f"http://127.0.0.1:{srv.server_port}"

        def feed(version, file):
            return json.dumps({"version": version, "platforms": {"windows-x86_64": {
                "url": f"{base}/{file}", "signature": UPD_SIG}}}).encode()
        srv.files = {"/latest.json": feed("99.0.0", "setup.exe"), "/forged.json": feed("99.0.0", "forged.exe"),
                     "/same.json": feed(__version__, "setup.exe"), "/setup.exe": UPD_PAYLOAD,
                     "/forged.exe": UPD_PAYLOAD[:500] + b"X" + UPD_PAYLOAD[501:]}
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.up_srv, self.up_base = srv, base
        update.FEED = f"{base}/latest.json"
        update._allow = lambda url: url          # the stand-in page is plain http on 127.0.0.1

    def s_up_feed(self, name):
        from . import update
        up = self.m8["updater"]
        update.FEED = "http://127.0.0.1:9/latest.json" if name == "down" else f"{self.up_base}/{name}.json"
        up.installer, up._found = None, None     # back to before any look, as a fresh start
        up._set(state="idle", detail="", percent=0, offered="")

    def s_up_found(self):
        nav = self.find_item("nav6")
        sign = next((c for c in nav.childItems() if c.property("name") == "info"), None) if nav else None
        self.check("a newer version on the release page: About says so and offers to update",
                   self.up_text() == EN["up_available"].replace("%1", "99.0.0")
                   and self.find_item("updateKey").property("text") == EN["up_install"],
                   f"text={self.up_text()!r} key={self.find_item('updateKey').property('text')!r}")
        self.check("and the settings' About section is lit in the accent, no dot anywhere",
                   sign is not None and self.near_accent(sign.property("color")),
                   f"nav={nav is not None} sign={sign and QColor(sign.property('color')).name()}")
        self.shot("upd_available")

    def s_up_installed(self):
        from .log import home
        up = self.m8["updater"]
        path = home() / "update" / "update-setup.exe"
        self.check("Update downloads the installer beside the settings, checks its signature and hands it on",
                   up.state == "installing" and up.installer == path and path.exists()
                   and path.stat().st_size == len(UPD_PAYLOAD) and up.percent == 100
                   and not path.with_suffix(".exe.part").exists(),
                   f"state={up.state} detail={up.detail} installer={up.installer} percent={up.percent}")
        self.check("and says the player will start again", self.up_text() == EN["up_installing"], repr(self.up_text()))

    def s_up_forged(self):
        from .log import home
        up = self.m8["updater"]
        self.check("an installer the release key did not sign is refused, said in words and deleted",
                   up.state == "failed" and up.detail == "signature" and self.up_text() == EN["up_f_signature"]
                   and up.installer is None and not (home() / "update" / "update-setup.exe").exists(),
                   f"state={up.state} detail={up.detail} text={self.up_text()!r}")
        self.shot("upd_forged")

    def s_up_current(self):
        up = self.m8["updater"]
        self.check("the same version on the release page: About says this is the newest",
                   up.state == "current" and self.up_text() == EN["up_current"],
                   f"state={up.state} detail={up.detail} text={self.up_text()!r}")

    def s_up_offline(self):
        up = self.m8["updater"]
        self.check("no connection: About says so in words and offers to try again",
                   up.state == "failed" and up.detail == "network" and self.up_text() == EN["up_f_network"]
                   and self.find_item("updateKey").property("text") == EN["up_retry"],
                   f"state={up.state} detail={up.detail} text={self.up_text()!r}")

    def s_up_done(self):
        from . import update
        update.FEED, update._allow, update.PUBLIC_KEY = self.up_saved
        self.up_srv.shutdown()
        up = self.m8["updater"]
        up.installer, up._found = None, None
        up._set(state="idle", detail="", percent=0, offered="")
        self.key("Esc")
