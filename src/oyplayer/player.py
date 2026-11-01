"""Player state for QML: mirrors mpv properties as Qt properties and runs actions.

mpv reports changes on its own threads; they are funnelled through one queued signal
so every Qt property changes on the GUI thread.
"""
import math
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

from .history import History
from .i18n import dec, tr
from .log import log
from .positions import Positions

# mpv property -> (attribute exposed to QML, value while mpv reports none)
_OBSERVED = {
    "pause": ("paused", True),
    "time-pos": ("position", 0.0),
    "duration": ("duration", 0.0),
    "volume": ("volume", 100.0),
    "mute": ("muted", False),
    "speed": ("speed", 1.0),
    "sub-visibility": ("subVisible", True),
    "media-title": ("title", ""),
    "path": ("path", ""),
    "chapter-list": ("chapters", []),
    "eof-reached": ("eof", False),
    "seekable": ("seekable", False),
    "brightness": ("brightness", 0),
    "contrast": ("contrast", 0),
    "saturation": ("saturation", 0),
    "video-aspect-override": ("aspect", "-1"),
    "panscan": ("panscan", 0.0),
    "video-zoom": ("zoom", 0.0),           # log2: 0 = 100 %, 1 = 200 %
    "video-rotate": ("rotate", 0),
    "deinterlace": ("deinterlace", False),
    "vf": ("vf", []),
    "track-list": ("tracks", []),
    "sid": ("sid", False),
    "secondary-sid": ("sid2", False),
    "sub-delay": ("subDelay", 0.0),
    "sub-scale": ("subScale", 1.0),
    "dwidth": ("videoW", 0),
    "dheight": ("videoH", 0),
    "container-fps": ("fps", 0.0),
    "aid": ("aid", False),
    "audio-delay": ("audioDelay", 0.0),
    "pitch": ("pitch", 1.0),
    "audio-device": ("audioDevice", "auto"),
    "af": ("af", []),
    # where the picture sits in the window (render pixels): the editor draws exactly over it
    "osd-dimensions": ("osd", {}),
    "ab-loop-a": ("loopA", "no"),
    "ab-loop-b": ("loopB", "no"),
}

FF_SPEEDS = (1.0, 1.5, 2.0, 4.0)   # the "fast play" key cycles through these
SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
COLOR_STEP = 5
ZOOM_STEP = 0.1                    # in log2 units, ~7 % per press
PAN_STEP = 0.02
SUB_DELAY_STEP = 0.1
# Picture filters: useful pixel shaders, as mpv/ffmpeg filters (label -> filter).
FILTERS = {
    "sharpen": "lavfi=[unsharp=5:5:0.8:3:3:0.0]",
    "denoise": "lavfi=[hqdn3d=3:2:4:3]",
    "gray": "lavfi=[hue=s=0]",
    "invert": "lavfi=[negate]",
}
ASPECTS = ("-1", "4:3", "16:9", "2.35:1", "fill")
AUDIO_DELAY_STEP = 0.1
PITCH_STEP = 2 ** (1 / 12)         # one semitone
# built-in audio processing as ffmpeg filters (names: i18n am_*)
AUDIO_MODES = {
    "off": "",
    "norm": "lavfi=[dynaudnorm=f=250:g=31]",
    "loudnorm": "lavfi=[loudnorm=I=-16:TP=-1.5:LRA=11]",
    "compressor": "lavfi=[acompressor=threshold=0.089:ratio=4:attack=10:release=200:makeup=2]",
    "leveler": "lavfi=[speechnorm=e=6.25:r=0.00001:l=1]",
}

# A live stream (internet radio) that drops is not a file that ended: it is reconnected, and
# only a station that stays silent is given up on. Nothing downstream (the playlist, «when the
# list ends: shut down») sees a drop as an end.
STREAM_TRIES = 3
STREAM_RETRY_MS = 3000
STREAM_STEADY_MS = 20000      # this long without a drop and the next drop starts counting anew

# mpv's reasons for a file that did not open, in words (i18n keys)
_LOAD_ERRORS = {
    "unrecognized file format": "le_format",
    "no audio or video data played": "le_empty",
    "loading failed": "le_unreadable",
}


def why_not_opened(path, error):
    if "://" not in path and path and not Path(path).exists():
        return tr("le_gone")
    if error in _LOAD_ERRORS:
        return tr(_LOAD_ERRORS[error])
    return tr("le_unreadable_why", error) if error else tr("le_unreadable")


class Player(QObject):
    changed = Signal()                      # any property but the position: QML binds through notify=changed
    # The position changes on every frame (25-60 times a second); with its own signal only
    # the bindings that show it are re-read, not every binding to the player.
    positionChanged = Signal()
    _fromMpv = Signal(str, object)
    osdMessage = Signal(str)
    eofReached = Signal()                   # keep-open=yes: the file ended, mpv holds the last frame
    loadFailed = Signal(str, str)           # a file did not open: path, why in words
    _endFile = Signal(str)                  # mpv's end-file with reason error, onto the GUI thread
    fileInfoReady = Signal(str, "QVariantList")   # ffprobe's rows for a file (Alt+I)
    _infoRead = Signal(str, object)

    def __init__(self, mpv_player):
        super().__init__()
        self.mpv = mpv_player
        self._state = {attr: default for attr, default in _OBSERVED.values()}
        self._defaults = dict(self._state)
        # mpv reads the override back as a number (4:3 -> 1.333, none -> -2), so the
        # mode the user picked is kept here.
        self._aspect = "-1"
        self.positions = Positions()
        self.history = History()
        self._last = ("", 0.0, 0.0)     # path, position, duration of what is playing
        self._loading = False           # a file was opened and is not set up yet
        self._resumeArmed = False
        self._noResume = ""             # a file opened at a set position (openAt)
        self._sizedPath = ""            # the file the mirrored picture size belongs to
        self._setup0 = None             # (path, tracks and volume it started with, had its own volume)
        self.auto_resume = False        # setting "resume"
        self.hwdec_enabled = True       # setting "hwdec"
        self.remember_setup = True      # setting "fileMemory"
        self.general_volume = 100.0     # what files without a volume of their own play at
        self._opening = ""              # what was last asked to open (mpv's end-file does not say)
        self._streamTries = 0
        self._streamRetry = QTimer(self, singleShot=True, interval=STREAM_RETRY_MS, timeout=self._reconnect)
        self._streamSteady = QTimer(self, singleShot=True, interval=STREAM_STEADY_MS,
                                    timeout=self._stream_steady)
        self._endFile.connect(self._on_end_file, Qt.QueuedConnection)
        self._infoRead.connect(self._on_info, Qt.QueuedConnection)
        self.mpv.register_event_callback(self._mpv_event)
        self._fromMpv.connect(self._apply, Qt.QueuedConnection)
        for prop, (attr, _d) in _OBSERVED.items():
            self.mpv.observe_property(prop, lambda _n, v, a=attr: self._fromMpv.emit(a, v))

    @Slot(str, object)
    def _apply(self, attr, value):
        unset = value is None
        if unset:
            value = self._defaults[attr]
        if self._state.get(attr) != value:
            self._state[attr] = value
            if attr == "path" and value and value != self._sizedPath:
                # The previous file's picture size must not be taken for the new one's. Only
                # a different file clears it: reopening the same file passes through an empty
                # path, and mpv does not report the unchanged size again (measured: Alt+1
                # found a size of 0 after a row was replayed).
                self._state["videoW"] = self._state["videoH"] = 0
                self._sizedPath = value
            (self.positionChanged if attr == "position" else self.changed).emit()
            if attr == "eof" and value:
                if self._live():
                    self._stream_lost()
                else:
                    self.eofReached.emit()
            # Loading the next file first unsets the old position and duration, then the
            # path changes: an unset value must not overwrite where the old file was left.
            if not unset or attr == "path":
                self._track_position(attr, value)

    def _mirror(name, notify=changed):  # noqa: N805 - class-body property factory
        return Property("QVariant", lambda self: self._state[name], notify=notify)

    paused = _mirror("paused")
    position = _mirror("position", positionChanged)
    duration = _mirror("duration")
    volume = _mirror("volume")
    muted = _mirror("muted")
    speed = _mirror("speed")
    subVisible = _mirror("subVisible")
    title = _mirror("title")
    path = _mirror("path")
    chapters = _mirror("chapters")
    brightness = _mirror("brightness")
    contrast = _mirror("contrast")
    saturation = _mirror("saturation")
    aspect = _mirror("aspect")
    panscan = _mirror("panscan")
    zoom = _mirror("zoom")
    rotate = _mirror("rotate")
    deinterlace = _mirror("deinterlace")
    tracks = _mirror("tracks")
    sid = _mirror("sid")
    sid2 = _mirror("sid2")
    subDelay = _mirror("subDelay")
    subScale = _mirror("subScale")
    videoW = _mirror("videoW")
    videoH = _mirror("videoH")
    fps = _mirror("fps")
    aid = _mirror("aid")
    audioDelay = _mirror("audioDelay")
    pitch = _mirror("pitch")
    audioDevice = _mirror("audioDevice")
    osd = _mirror("osd")
    del _mirror

    def _loop_point(self, name):
        v = self._state[name]
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else -1.0

    @Property(float, notify=changed)
    def loopA(self):
        """A-B repeat: where the stretch starts, -1 while not set."""
        return self._loop_point("loopA")

    @Property(float, notify=changed)
    def loopB(self):
        return self._loop_point("loopB")

    @Property("QVariantList", notify=changed)
    def audioTracks(self):
        out = []
        for t in self._state["tracks"]:
            if t.get("type") != "audio":
                continue
            ch = t.get("demux-channel-count")
            parts = [t.get("title") or t.get("lang") or tr("track", t["id"]), t.get("codec", "")]
            if ch:
                parts.append({1: tr("mono"), 2: tr("stereo"), 6: "5.1", 8: "7.1"}.get(ch, tr("channels_n", ch)))
            out.append({"id": t["id"], "title": "  ·  ".join(p for p in parts if p),
                        "external": t.get("external", False)})
        return out

    @Property(str, notify=changed)
    def audioMode(self):
        # Read from mpv, not from the mirrored state: a menu built right after a change
        # would otherwise show the previous mode (the observer event is still queued).
        graph = next((f.get("params", {}).get("graph", "") for f in (self.mpv["af"] or [])
                      if f.get("label") == "norm"), "")
        return next((k for k, flt in AUDIO_MODES.items() if flt and graph and graph in flt), "off")

    @Property("QVariantList", notify=changed)
    def activeFilters(self):
        return [f["label"] for f in self._state["vf"] if f.get("label") in FILTERS]

    @Property(str, notify=changed)
    def aspectMode(self):
        return self._aspect

    @Property("QVariantList", notify=changed)
    def subTracks(self):
        return [{"id": t["id"], "title": t.get("title") or t.get("lang") or tr("track", t["id"]),
                 "lang": t.get("lang", ""), "external": t.get("external", False)}
                for t in self._state["tracks"] if t.get("type") == "sub"]

    @Property(bool, notify=changed)
    def hasFile(self):
        return bool(self._state["path"])

    def _track_position(self, attr, value):
        if attr == "position" and self._state["path"]:
            self._last = (self._state["path"], value, self._state["duration"])
        elif attr == "path":
            self._loading = bool(value)
            self._resumeArmed = bool(value) and value != self._noResume
            self._noResume = ""
        elif attr == "duration" and value and self._loading:
            # The duration comes once the file is open and mpv has picked its tracks.
            self._loading = False
            self._restore()
            if self._resumeArmed and self.auto_resume:
                self.resumePosition()
            self._resumeArmed = False

    # ---- what each file was left with
    def _setup(self):
        """The file's tracks and volume as kept per file: a track of the file by its id, one
        loaded from beside it by the file it came from, none as False."""
        tracks = self.mpv.track_list or []
        out = {"volume": round(self.mpv.volume, 1)}
        for kind, prop in (("audio", "aid"), ("sub", "sid")):
            cur = getattr(self.mpv, prop)    # the runtime property: m["aid"] reads the option
            t = next((t for t in tracks if t["type"] == kind and t["id"] == cur), None)
            out[prop] = False if t is None else t.get("external-filename") if t.get("external") else t["id"]
        return out

    def _restore(self):
        path = self._state["path"]
        kept = self.positions.setup(path) if self.remember_setup else {}
        tracks = self.mpv.track_list or []
        for kind, prop, add in (("audio", "aid", "audio-add"), ("sub", "sid", "sub-add")):
            want = kept.get(prop)
            if want is None:
                continue
            if want is False:
                self.mpv[prop] = "no"
            elif isinstance(want, int):
                if any(t["type"] == kind and t["id"] == want and not t.get("external") for t in tracks):
                    self.mpv[prop] = want
            else:
                t = next((t for t in tracks if t["type"] == kind and t.get("external-filename") == want), None)
                if t:
                    self.mpv[prop] = t["id"]
                elif Path(want).exists():
                    self.mpv.command(add, want, "select")
        if self.remember_setup:
            # A file without a volume of its own plays at the general one, also right after
            # a file that had its own.
            self.mpv.volume = kept.get("volume", self.general_volume)
        if kept:
            log.info("restored for %s: %s", Path(path).name, kept)
        # What the file starts with; whatever differs when it is left was the person's doing.
        self._setup0 = (path, {**self._setup(), **kept}, "volume" in kept)

    def _leave(self):
        """Keep what the file being left was set to, before the next load resets it."""
        path = self._state["path"]
        # mpv keeps A-B points as options and would carry them into the next file
        self.mpv["ab-loop-a"] = "no"
        self.mpv["ab-loop-b"] = "no"
        if not path or not self.remember_setup:
            self.general_volume = self.mpv.volume    # nothing per file: the volume is simply the volume
        # A file left before it finished opening has nothing new: what was kept for it stays.
        if not self._setup0 or self._setup0[0] != path:
            return
        _path, start, own_volume = self._setup0
        self._setup0 = None
        changed = {}
        if self.remember_setup:
            now = self._setup()
            changed = {k: v for k, v in now.items() if v != start[k]}
            # Turning the volume up or down on a file with no volume of its own is the level
            # wanted from now on: the next files get it too.
            if "volume" in changed and not own_volume:
                self.general_volume = now["volume"]
            # a file with a volume of its own hands the next one the general volume at once,
            # not after its first moments
            if own_volume:
                self.mpv.volume = self.general_volume
        pos, dur = (self._last[1], self._last[2]) if self._last[0] == path else (0.0, 0.0)
        self.positions.remember(path, pos, dur, changed)
        self.history.note(path, pos, dur)

    @Slot()
    def resumePosition(self):
        pos = self.positions.position(self._state["path"])
        if pos:
            self.seek(pos)
            s = int(pos)
            self.osdMessage.emit(tr("osd_resume", f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"))
        else:
            self.osdMessage.emit(tr("osd_no_position"))

    def saveSession(self):
        self._leave()

    # ---- files that do not open, streams that drop ----------------------
    def _mpv_event(self, event):
        # mpv's thread. Compared through as_dict: comparing event ids does not match in
        # python-mpv 1.0.8 (measured), the dict carries the plain names.
        d = event.as_dict()
        if d.get("event") == b"end-file" and d.get("reason") == b"error":
            self._endFile.emit((d.get("file_error") or b"").decode("utf-8", "replace"))

    @Slot(str)
    def _on_end_file(self, error):
        path = self._opening
        if "://" in path:
            log.warning("stream did not open %s: %s", path, error)
            self._stream_lost(path)
            return
        why = why_not_opened(path, error)
        log.warning("not opened %s: %s (%s)", path, why, error)
        self.osdMessage.emit(tr("osd_not_opened", Path(path).name or path, why))
        self.loadFailed.emit(path, why)

    def _live(self):
        """A stream with no end of its own: an end of file there is a dropped connection."""
        path = self._state["path"] or ""
        return "://" in path and not (self._state["seekable"] and self._state["duration"])

    def _stream_lost(self, path=""):
        url = path or self._state["path"] or self._opening
        self._streamSteady.stop()
        if self._streamTries < STREAM_TRIES:
            self._streamTries += 1
            self._opening = url
            log.warning("stream lost %s, reconnect %d/%d", url, self._streamTries, STREAM_TRIES)
            self.osdMessage.emit(tr("osd_stream_retry", self._streamTries, STREAM_TRIES))
            self._streamRetry.start()
        else:
            self._streamTries = 0
            log.warning("stream given up %s", url)
            self.mpv.pause = True
            self.osdMessage.emit(tr("osd_stream_gone"))

    def _reconnect(self):
        log.info("reconnect %s", self._opening)
        self.mpv.loadfile(self._opening)
        self.mpv.pause = False
        self._streamSteady.start()

    def _stream_steady(self):
        self._streamTries = 0

    def _opened(self, url):
        self._opening = url
        self._streamTries = 0
        self._streamRetry.stop()
        self._streamSteady.stop()

    # ---- actions -------------------------------------------------------
    @Slot(str)
    def open(self, url):
        log.info("open %s", url)
        self._opened(url)
        self._leave()
        self.mpv.loadfile(url)
        self.mpv.pause = False

    @Slot(str, float)
    def openAt(self, url, seconds):
        """Open at a position (the editor's fragments): the resume jump stays out of it."""
        log.info("open %s at %.2f", url, seconds)
        self._opened(url)
        self._leave()
        self._noResume = url
        self.mpv.loadfile(url, start=f"{seconds:.3f}")

    @Slot()
    def abLoop(self):
        """Replay A-B: the first press sets A here, the second B, the third ends it."""
        if not self._state["path"]:
            return
        self.mpv.command("ab-loop")
        a, b = self.mpv["ab-loop-a"], self.mpv["ab-loop-b"]

        def fmt(s):
            s = int(s)
            return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
        if a == "no":
            self.osdMessage.emit(tr("osd_ab_off"))
        elif b == "no":
            self.osdMessage.emit(tr("osd_ab_start", fmt(a)))
        else:
            self.osdMessage.emit(tr("osd_ab", fmt(a), fmt(b)))

    @Slot()
    def togglePause(self):
        if self._state["path"]:
            self.mpv.cycle("pause")

    @Slot(float)
    def seek(self, seconds):
        if self._state["path"]:
            self.mpv.seek(max(0.0, seconds), "absolute+exact")

    @Slot(float, bool)
    def scrub(self, seconds, exact):
        """Dragging the seek bar: the keyframe near the pointer while moving, fast; the exact
        frame on release. An exact seek decodes from the keyframe up to the frame, on every move
        of the mouse. Asynchronous: a paused player held the mouse up to 0.2 s per move waiting
        for mpv (measured); and the release goes the same way, so mpv takes it after the moves
        (a synchronous seek overtook them, and the last keyframe won)."""
        if self._state["path"]:
            self.mpv.command_async("seek", max(0.0, seconds), "absolute+exact" if exact else "absolute+keyframes")

    @Slot(float)
    def seekRelative(self, seconds):
        if self._state["path"]:
            self.mpv.seek(seconds, "relative")

    @Slot()
    def frameStep(self):
        if self._state["path"]:
            self.mpv.frame_step()

    @Slot()
    def frameBackStep(self):
        if self._state["path"]:
            self.mpv.frame_back_step()

    @Slot()
    def cycleFastPlay(self):
        cur = self._state["speed"]
        nxt = next((s for s in FF_SPEEDS if s > cur + 1e-6), FF_SPEEDS[0])
        self.mpv.speed = nxt
        self.osdMessage.emit(tr("osd_speed", dec(f"{nxt:g}")))

    @Slot()
    def toggleSubs(self):
        self.mpv.cycle("sub-visibility")

    @Slot()
    def toggleMute(self):
        self.mpv.cycle("mute")

    @Slot(float)
    def setVolume(self, v):
        self.mpv.volume = max(0.0, min(200.0, v))

    @Slot(float)
    def changeVolume(self, delta):
        self.setVolume(self._state["volume"] + delta)
        self.osdMessage.emit(tr("osd_volume", round(self.mpv.volume)))

    @Slot(str)
    def screenshot(self, folder):
        if not self._state["path"]:
            return
        Path(folder).mkdir(parents=True, exist_ok=True)
        stem = Path(self._state["path"]).stem
        pos = self._state["position"] or 0.0
        target = Path(folder) / f"{stem}_{int(pos // 3600):02d}-{int(pos % 3600 // 60):02d}-{pos % 60:06.3f}.png"
        self.mpv.screenshot_to_file(str(target), "video")
        log.info("screenshot %s", target)
        self.osdMessage.emit(tr("osd_shot_saved"))

    @Slot()
    def screenshotToClipboard(self):
        if not self._state["path"]:
            return
        from tempfile import gettempdir
        from PySide6.QtGui import QGuiApplication, QImage
        tmp = Path(gettempdir()) / "oyplayer_clip.png"
        self.mpv.command("screenshot-to-file", str(tmp), "video")
        QGuiApplication.clipboard().setImage(QImage(str(tmp)))
        tmp.unlink(missing_ok=True)
        self.osdMessage.emit(tr("osd_shot_clipboard"))

    @Slot(float)
    def setSpeed(self, v):
        self.mpv.speed = v
        self.osdMessage.emit(tr("osd_speed", dec(f"{v:g}")))

    # ---- picture: colour, geometry, filters
    @Slot(str, int)
    def setColor(self, name, value):
        self.mpv[name] = max(-100, min(100, int(value)))

    @Slot(str, int)
    def changeColor(self, name, delta):
        self.setColor(name, self._state[name] + delta)
        self.osdMessage.emit(f"{tr(name)} {int(self.mpv[name]):+d}")

    @Slot()
    def resetColors(self):
        for n in ("brightness", "contrast", "saturation"):
            self.mpv[n] = 0
        self.osdMessage.emit(tr("osd_colors_reset"))

    @Slot(str)
    def setAspect(self, mode):
        # "fill" = by width/by height: fill the area and crop the overflow.
        self.mpv["panscan"] = 1.0 if mode == "fill" else 0.0
        self.mpv["video-aspect-override"] = "no" if mode in ("fill", "-1") else mode
        self._aspect = mode
        self.changed.emit()
        names = {"-1": tr("aspect_asis"), "fill": tr("aspect_fill")}
        self.osdMessage.emit(tr("osd_aspect", names.get(mode, mode)))

    @Slot()
    def cycleAspect(self):
        cur = self.aspectMode
        self.setAspect(ASPECTS[(ASPECTS.index(cur) + 1) % len(ASPECTS)] if cur in ASPECTS else ASPECTS[0])

    @Slot(float)
    def setZoom(self, log2zoom):
        self.mpv["video-zoom"] = max(-1.0, min(2.0, log2zoom))
        self.osdMessage.emit(tr("osd_zoom", round(2 ** self.mpv["video-zoom"] * 100)))

    @Slot(float)
    def changeZoom(self, delta):
        self.setZoom(self._state["zoom"] + delta)

    @Slot(float, float)
    def pan(self, dx, dy):
        self.mpv["video-pan-x"] = self.mpv["video-pan-x"] + dx
        self.mpv["video-pan-y"] = self.mpv["video-pan-y"] + dy

    @Slot()
    def resetGeometry(self):
        self.mpv["video-zoom"] = 0.0
        self.mpv["video-pan-x"] = 0.0
        self.mpv["video-pan-y"] = 0.0
        self.mpv["video-rotate"] = 0
        self.setAspect("-1")

    @Slot(int)
    def rotateBy(self, degrees):
        self.mpv["video-rotate"] = (self._state["rotate"] + degrees) % 360

    def _software_filters(self):
        return bool(self.mpv["deinterlace"]) or any(
            f.get("label") in FILTERS or f.get("label") == "edview" for f in (self.mpv["vf"] or []))

    def setEditView(self, graph):
        """The editor's turn and frame on screen: one lavfi graph under the label «edview»
        ("" takes it away). The same graph is what saving runs, so what shows is what is saved."""
        shown = any(f.get("label") == "edview" for f in (self.mpv["vf"] or []))
        if not shown and not graph:
            return                  # nothing to take away: the decoder is left alone (a reset loses the seek)
        if shown:
            self.mpv.command("vf", "remove", "@edview")
        if graph:
            if self.hwdec_enabled:
                self.mpv["hwdec"] = "auto-copy-safe"     # software filters need the frames in memory
            # %n% quotes the graph by its length: its brackets and commas stay inside
            self.mpv.command("vf", "add", f"@edview:lavfi=graph=%{len(graph)}%{graph}")
        elif self.hwdec_enabled and not self._software_filters():
            self.mpv["hwdec"] = "auto-safe"

    @Slot(str)
    def toggleFilter(self, label):
        # Hardware-decoded frames live in GPU memory, where ffmpeg's software filters
        # cannot take them (measured: nvdec + hue -> "Impossible to convert between
        # the formats"). Copy-back decoding goes first, before the filter is added, and
        # full hardware decoding returns once no filter is left.
        if self.hwdec_enabled:
            self.mpv["hwdec"] = "auto-copy-safe"
        if label == "deinterlace":
            self.mpv.cycle("deinterlace")
        else:
            self.mpv.command("vf", "toggle", f"@{label}:{FILTERS[label]}")
        if self.hwdec_enabled and not self._software_filters():
            self.mpv["hwdec"] = "auto-safe"

    # ---- subtitles
    @Slot("QVariant")
    def setSid(self, sid):
        self.mpv["sid"] = sid if sid not in (None, -1) else "no"

    @Slot("QVariant")
    def setSid2(self, sid):
        self.mpv["secondary-sid"] = sid if sid not in (None, -1) else "no"

    @Slot()
    def cycleSub(self):
        self.mpv.cycle("sub")
        title = next((t["title"] for t in self.subTracks if t["id"] == self.mpv.sid), tr("subs_off"))
        self.osdMessage.emit(tr("osd_subs", title))

    @Slot(str)
    def addSubtitle(self, url):
        from .playlist import to_path
        self.mpv.command("sub-add", to_path(url), "select")
        self.osdMessage.emit(tr("osd_subs_loaded"))

    @Slot(float)
    def changeSubDelay(self, delta):
        self.mpv["sub-delay"] = round(self._state["subDelay"] + delta, 3)
        self.osdMessage.emit(tr("osd_sub_delay", dec(f"{self.mpv['sub-delay']:+.1f}")))

    @Slot(float)
    def changeSubScale(self, delta):
        self.mpv["sub-scale"] = max(0.3, min(3.0, round(self._state["subScale"] + delta, 2)))
        self.osdMessage.emit(tr("osd_sub_scale", round(self.mpv["sub-scale"] * 100)))

    @Slot(float)
    def changeSubSpeed(self, factor):
        # make subtitles slower/faster: stretch subtitle timing (wrong-fps subs)
        self.mpv["sub-speed"] = round(self.mpv["sub-speed"] * factor, 4)
        self.osdMessage.emit(tr("osd_sub_speed", dec(f"{self.mpv['sub-speed']:.3f}")))

    @Slot()
    def copySubtitle(self):
        from PySide6.QtGui import QGuiApplication
        text = self.mpv.sub_text or ""
        QGuiApplication.clipboard().setText(text)
        self.osdMessage.emit(tr("osd_sub_copied" if text else "osd_no_sub_line"))

    # ---- sound
    @Slot("QVariant")
    def setAid(self, aid):
        self.mpv["aid"] = aid if aid not in (None, -1) else "no"

    @Slot()
    def cycleAudio(self):
        self.mpv.cycle("audio")
        cur = self.mpv.aid
        title = next((t["title"] for t in self.audioTracks if t["id"] == cur), tr("no_sound"))
        self.osdMessage.emit(tr("osd_audio", title))

    @Slot(str)
    def addAudio(self, url):
        from .playlist import to_path
        self.mpv.command("audio-add", to_path(url), "select")
        self.osdMessage.emit(tr("osd_audio_loaded"))

    @Slot(float)
    def changeAudioDelay(self, delta):
        self.mpv["audio-delay"] = round(self._state["audioDelay"] + delta, 3)
        self.osdMessage.emit(tr("osd_audio_delay", dec(f"{self.mpv['audio-delay']:+.1f}")))

    @Slot(float)
    def changePitch(self, factor):
        self.mpv["pitch"] = max(0.5, min(2.0, self.mpv["pitch"] * factor))
        semis = round(12 * math.log2(self.mpv["pitch"]))
        self.osdMessage.emit(tr("osd_pitch", f"{semis:+d}") if semis else tr("act_pitch_reset"))

    @Slot()
    def resetPitch(self):
        self.mpv["pitch"] = 1.0
        self.osdMessage.emit(tr("act_pitch_reset"))

    @Slot(str)
    def setAudioMode(self, mode, quiet=False):
        mode = mode if mode in AUDIO_MODES else "off"
        flt = AUDIO_MODES[mode]
        if any(f.get("label") == "norm" for f in (self.mpv["af"] or [])):
            self.mpv.command("af", "remove", "@norm")
        if flt:
            self.mpv.command("af", "add", f"@norm:{flt}")
        if not quiet:
            self.osdMessage.emit(tr("osd_audio_mode", tr("am_" + mode)))

    @Slot(result="QVariantList")
    def audioDevices(self):
        return [{"name": d["name"], "description": d["description"]}
                for d in self.mpv.audio_device_list if d["name"] != "openal"]

    @Slot(str)
    def setAudioDevice(self, name):
        self.mpv["audio-device"] = name

    @Slot(result="QVariantList")
    def fileInfo(self):
        """File info: sections of (label, value) rows from ffprobe.
        ffprobe runs off the GUI thread (a file on a network disk that went away held the
        window up to 20 s): the card opens with the name at once, fileInfoReady brings the rest."""
        path = self._state["path"]
        if not path:
            return []
        threading.Thread(target=self._read_info, args=(path,), daemon=True).start()
        return [{"title": tr("info_file"), "rows": [{"k": tr("info_name"), "v": Path(path).name if "://" not in path else path},
                                                {"k": tr("info_details"), "v": tr("info_reading")}]}]

    def _read_info(self, path):
        from . import info
        try:
            sections = info.probe_sections(path)
        except Exception:           # noqa: BLE001 - a timeout or a file gone: the card says so
            log.exception("file info %s", path)
            sections = [{"title": tr("info_file"), "rows": [{"k": tr("info_path"), "v": path},
                                                         {"k": tr("info_details"), "v": tr("le_unreadable")}]}]
        self._infoRead.emit(path, sections)

    @Slot(str, object)
    def _on_info(self, path, sections):
        self.fileInfoReady.emit(path, sections)

    @Slot(result=str)
    def techInfo(self):
        """The video technical OSD (Q): what is playing and how it is being decoded."""
        if not self._state["path"]:
            return ""
        m = self.mpv

        def get(name, default=None):
            # m["x"] reads mpv's options; these are runtime properties (m.x).
            try:
                v = getattr(m, name.replace("-", "_"))
            except (AttributeError, RuntimeError, TypeError):
                return default
            return default if v is None else v

        vp, ap = get("video-params", {}), get("audio-params", {})
        lines = [Path(self._state["path"]).name, tr("tech_container", get("file-format", "?"))]
        if vp:
            fps = get("container-fps", 0) or 0
            lines.append(tr("tech_video", f"{get('video-codec', '?')}  {vp.get('w')}×{vp.get('h')}  "
                            + tr("fps", dec(f"{fps:.3f}")) + f"  {vp.get('pixelformat', '')}"))
            vbr = get("video-bitrate")
            lines.append("  " + tr("tech_bitrate", tr("kbps", f"{vbr / 1000:.0f}") if vbr else "—"))
            lines.append("  " + tr("tech_decode", get("hwdec-current", "no"), get("frame-drop-count", 0)))
        if ap:
            abr = get("audio-bitrate")
            lines.append(tr("tech_audio", f"{get('audio-codec-name', '?')}  " + tr("hz", ap.get("samplerate"))
                            + f"  {ap.get('hr-channels') or ap.get('channel-count')}"
                            + ("  " + tr("kbps", f"{abr / 1000:.0f}") if abr else "")))
        return "\n".join(lines)

    @Slot(float, float, float)
    def setVideoMargins(self, top, bottom, right):
        """Fractions of the window the picture must keep clear (title bar, panel, playlist)."""
        self.mpv["video-margin-ratio-top"] = top
        self.mpv["video-margin-ratio-bottom"] = bottom
        self.mpv["video-margin-ratio-right"] = right
