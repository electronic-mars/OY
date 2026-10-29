"""Editing (SPEC §7): cut pieces out of what is playing, join them, save with ffmpeg.

The edit is a list of fragments (file, start, end) played back by the same mpv: no
timeline and no second engine. Saving copies the streams when it can (LosslessCut's way:
fast and without loss) and re-encodes otherwise. A copied fragment can only start on a
keyframe, so in that mode a fragment's start is the keyframe at or before its mark, and
the strip and the preview show that start: what is seen is what is saved.
The source files are never written to.
"""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from .i18n import dec, tr
from .log import log
from .playlist import to_path

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")
_NO_WINDOW = subprocess.CREATE_NO_WINDOW
COPY_EXT = {".mp4", ".mkv", ".mov", ".m4v", ".webm"}   # a copy keeps the source's container
END_SLACK = 0.1   # preview: the last frame of a fragment starts about a frame before its end
MIN_LEN = 0.1
UNDO_STEPS = 100
UNDO_MERGE = 1.0  # seconds: a drag's calls this close together are one undo step
# Drawings over the picture (M7). Sizes are fractions of the picture's height, the same in
# NoteLayer.qml and in render_note(), so the saved frame matches the screen.
NOTE_SECONDS = 4.0
NOTE_MIN = 0.2       # the shortest a drawing's interval gets (the timeline's drag keeps the same)
STROKE = 0.007
TEXT_SIZE = 0.065
HEAD = 0.035
TEXT_FONT = "Segoe UI Variable Text"


def explain(stderr_lines, final):
    """What a failed ffmpeg run means for the person, and what to do about it."""
    text = " ".join(stderr_lines).lower()
    if "no space left" in text:
        return tr("err_no_space")
    if "permission denied" in text or "access is denied" in text:
        return tr("err_no_access", final.parent.name or final.parent)
    if "invalid argument" in text and len(str(final)) > 240:
        return tr("err_long_path")
    return tr("err_ffmpeg")


def fmt(s):
    s = max(0.0, s)
    return f"{int(s // 60)}:{s % 60:04.1f}"


def probe(path):
    """What saving needs to know about a file."""
    r = subprocess.run([_FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True, encoding="utf-8", timeout=20,
                       creationflags=_NO_WINDOW)
    data = json.loads(r.stdout or "{}")
    streams, fmt_ = data.get("streams", []), data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fps = v.get("avg_frame_rate", "0/0")
    return {
        "duration": float(fmt_.get("duration") or 0),
        # ffprobe and the concat demuxer count from the container's first timestamp,
        # mpv and ffmpeg's -ss from the file's start (MPEG-TS starts at ~1.4 s, not 0).
        "start": float(fmt_.get("start_time") or 0),
        "w": v.get("width", 0), "h": v.get("height", 0),
        "fps": fps if fps not in ("0/0", "") else v.get("r_frame_rate", "25/1"),
        "audio": len(audio),
        "layout": (audio[0].get("channel_layout") or "stereo") if audio else "",
        # files joined by copying must match in all of these
        "sig": [v.get(k) for k in ("codec_name", "profile", "width", "height", "pix_fmt")]
               + [[a.get(k) for k in ("codec_name", "sample_rate", "channels")] for a in audio],
    }


def keyframe_before(path, t, start=0.0):
    """The video keyframe at or before t: where a copied fragment really begins."""
    for begin in (max(0.0, t - 30), None):     # a 30 s window first, then from the top
        window = f"{start + begin:.3f}%{start + t + 0.001:.3f}" if begin is not None else f"%{start + t + 0.001:.3f}"
        r = subprocess.run([_FFPROBE, "-v", "error", "-select_streams", "v:0", "-read_intervals", window,
                            "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW)
        keys = [float(p) - start for p, _, f in (ln.partition(",") for ln in r.stdout.split())
                if "K" in f and p not in ("", "N/A") and float(p) - start <= t + 0.001]
        if keys:
            return max(keys)
    return 0.0


def render_note(n, size, box, path):
    """One drawing as a transparent PNG the size of the saved frame; box = (x, y, w, h) of
    the picture inside it (a smaller file in the join is centred, with bars around it)."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPolygonF

    x0, y0, pw, ph = box
    img = QImage(size[0], size[1], QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    color, lw = QColor(n["color"]), max(1.5, STROKE * ph)
    pen = QPen(color, lw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    pts = [QPointF(x0 + x * pw, y0 + y * ph) for x, y in n["pts"]]
    if n["kind"] == "text":
        font = QFont(TEXT_FONT)
        font.setPixelSize(max(6, round(TEXT_SIZE * ph)))
        font.setWeight(QFont.DemiBold)
        shape = QPainterPath()
        shape.addText(pts[0].x(), pts[0].y() + QFontMetricsF(font).ascent(), font, n["text"])
        p.strokePath(shape, QPen(outline(color), lw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(shape, color)
    elif n["kind"] == "rect":
        p.setPen(pen)
        p.drawRect(QRectF(pts[0], pts[1]).normalized())
    elif n["kind"] == "pen":
        p.setPen(pen)
        p.drawPolyline(QPolygonF(pts))
    elif n["kind"] == "arrow":
        tip, base, left, right = arrow_head(pts[0], pts[1], max(4 * lw, HEAD * ph))
        p.setPen(pen)
        p.drawLine(pts[0], base)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([tip, left, right]))
    p.end()
    img.save(str(path))


def outline(color):
    """Text keeps a thin contrasting edge, so it reads on any picture."""
    from PySide6.QtGui import QColor
    return QColor(255, 255, 255, 150) if color.lightness() < 60 else QColor(0, 0, 0, 150)


def arrow_head(a, b, length):
    """Tip, base centre and the two back corners of an arrow from a to b (as NoteLayer.qml)."""
    from PySide6.QtCore import QPointF
    dx, dy = b.x() - a.x(), b.y() - a.y()
    d = max(1e-6, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / d, dy / d
    base = QPointF(b.x() - ux * length, b.y() - uy * length)
    half = length * 0.55
    return b, base, QPointF(base.x() - uy * half, base.y() + ux * half), QPointF(base.x() + uy * half, base.y() - ux * half)


_hw_ok = {}


def encoder_args(codec):
    """H.264 / H.265 on the NVIDIA encoder when the card takes the job, else x264 / x265."""
    hw = {"h264": "h264_nvenc", "h265": "hevc_nvenc"}[codec]
    if hw not in _hw_ok:
        r = subprocess.run([_FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=s=256x144:d=0.1",
                            "-c:v", hw, "-f", "null", "-"], capture_output=True, timeout=30,
                           creationflags=_NO_WINDOW)
        _hw_ok[hw] = r.returncode == 0
        log.info("encoder %s %s", hw, "available" if _hw_ok[hw] else "not available")
    tag = ["-tag:v", "hvc1"] if codec == "h265" else []    # players on phones and Macs want hvc1
    if _hw_ok[hw]:
        return ["-c:v", hw, "-preset", "p5", "-rc", "vbr", "-cq", "21" if codec == "h264" else "24",
                "-b:v", "0"] + tag
    if codec == "h264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    return ["-c:v", "libx265", "-preset", "fast", "-crf", "24"] + tag


class Editor(QObject):
    changed = Signal()
    saveRequested = Signal()          # QML asks where to save
    _progressed = Signal(float)
    _done = Signal(bool, str)
    _found = Signal(str, float, float, object)   # path, start, keyframe, probe: from the reading thread

    def __init__(self, player):
        super().__init__()
        self.p = player
        self._active = False
        self.frags = []              # dicts: path, start, end, aid
        # one choice for the whole edit: a fragment (_selected) or a drawing (_noteSel), never both
        self._selected = -1
        self._cue = -1               # a fragment just clicked: Space plays the edit from it
        # drawings: kind (text|arrow|rect|pen), path, a, b (seconds of that file), color,
        # pts (fractions of the picture), text
        self._notes = []
        self._noteSel = -1
        self._in = None              # (path, seconds) of the pending start mark
        self.codec = "copy"          # setting "exportCodec": copy | h264 | h265
        self._probes = {}
        # ffprobe runs off the GUI thread, which also draws the picture: a fragment is on the
        # strip at once and its keyframe (where a copied fragment really begins) follows.
        self._kfs = {}               # (path, start) -> the keyframe at or before start
        self._said, self._told = None, False     # the last O's (path, start, end), and whether the OSD said it
        self._asked = set()          # (path, start) being read
        self._reader = ThreadPoolExecutor(max_workers=1)
        self._queued = ""            # a save asked for while keyframes were still being read
        self._preview = -1           # fragment the preview is playing; -1 = off
        self._armed = False          # the preview has seen the player inside that fragment
        self._proc = None
        self._thread = None
        self._cancelled = False
        self._progress = 0.0
        self._saved = ""
        self._error = ""             # why the last save failed, shown on the strip until the next try
        self.lastLossless = None     # how the last save was made (the self-test reads it)
        self._undo = []              # (what, state before it), newest last
        self._redo = []
        self._merge = None           # (key, time) of the last merging change
        self._progressed.connect(self._set_progress, Qt.QueuedConnection)
        self._done.connect(self._finished, Qt.QueuedConnection)
        self._found.connect(self._on_found, Qt.QueuedConnection)
        player.changed.connect(self._follow)
        player.positionChanged.connect(self._follow)

    # ---- state for QML
    @Property(bool, notify=changed)
    def active(self):
        return self._active

    @Property(int, notify=changed)
    def selected(self):
        return self._selected

    @Property(float, notify=changed)
    def markIn(self):
        return self._in[1] if self._in and self._in[0] == self.p.path else -1.0

    def _why_not_copy(self):
        """What keeps the edit from being saved by copying; empty when nothing does."""
        if self._overlaid():
            return tr("why_drawings")
        if len({json.dumps(self._probes[f["path"]]["sig"]) for f in self.frags if f["path"] in self._probes}) > 1:
            return tr("why_formats")
        return ""

    @Property(bool, notify=changed)
    def overlaid(self):
        """Drawings lie over some fragment: they are burnt into the saved picture."""
        return self._overlaid()

    @Property(bool, notify=changed)
    def canCopy(self):
        return not self._why_not_copy()

    @Property(bool, notify=changed)
    def lossless(self):
        """Saving will copy: copy mode, no drawing over the saved pictures, and every file
        can be joined to the others as is."""
        return self.codec == "copy" and self.canCopy

    @Property(str, notify=changed)
    def mode(self):
        """How saving will really go: the setting, or H.264 when copying cannot be."""
        return "copy" if self.lossless else "h264" if self.codec == "copy" else self.codec

    @Property(str, notify=changed)
    def reason(self):
        """Why «without loss» was chosen and will not be (shown under the edit's length)."""
        return self._why_not_copy() if self.codec == "copy" else ""

    def _notes_in(self, f, notes=None):
        return [n for n in (self._notes if notes is None else notes)
                if n["path"] == f["path"] and n["a"] < f["end"] and n["b"] > f["start"]]

    def _overlaid(self):
        return any(self._notes_in(f) for f in self.frags)

    def _kf(self, f):
        """The keyframe at or before the fragment's start; None while it is being read."""
        return self._kfs.get((f["path"], f["start"]))

    def _from(self, f):
        kf = self._kf(f)
        return kf if self.lossless and kf is not None else f["start"]

    @Property("QVariantList", notify=changed)
    def fragments(self):
        return [{"name": Path(f["path"]).name, "path": f["path"], "from": self._from(f), "end": f["end"],
                 "dur": f["end"] - self._from(f), "range": f"{fmt(self._from(f))}–{fmt(f['end'])}",
                 "pending": self._kf(f) is None,
                 # a copied fragment begins this much before its mark (at the keyframe)
                 "shift": f["start"] - self._from(f)}
                for f in self.frags]

    @Property("QVariantList", notify=changed)
    def bands(self):
        """The playing file's fragments, for its timeline: [from, end, mark, number in the edit]."""
        return [[self._from(f), f["end"], f["start"], n + 1] for n, f in enumerate(self.frags) if f["path"] == self.p.path]

    @Property("QVariantList", notify=changed)
    def elsewhere(self):
        """The edit's fragments in files other than the playing one: [row, file name]."""
        return [[n, Path(f["path"]).name] for n, f in enumerate(self.frags) if f["path"] != self.p.path]

    @Property(float, notify=changed)
    def total(self):
        return sum(f["end"] - self._from(f) for f in self.frags)

    @Property(str, notify=changed)
    def note(self):
        if not self.frags:
            return ""
        if self.lossless:
            return tr("note_lossless")
        if self.codec == "copy":
            return tr("note_reencode_why", tr("note_drawings_over") if self._overlaid() else tr("why_formats"))
        return tr("note_reencode", {"h264": "H.264", "h265": "H.265"}[self.codec])

    @Property(int, notify=changed)
    def previewing(self):
        return self._preview

    @Property(bool, notify=changed)
    def pending(self):
        """Some fragment's keyframe is still being read."""
        return any(self._kf(f) is None for f in self.frags)

    @Property(bool, notify=changed)
    def exporting(self):
        return self._thread is not None or bool(self._queued)

    @Property(float, notify=changed)
    def progress(self):
        return self._progress

    @Property(str, notify=changed)
    def saved(self):
        return self._saved

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Slot()
    def clearError(self):
        self._error = ""
        self.changed.emit()

    def _tools(self):
        """ffmpeg and ffprobe are there; when not, the person is told why nothing happens."""
        if _FFMPEG and _FFPROBE:
            return True
        log.warning("editor: ffmpeg=%s ffprobe=%s", _FFMPEG, _FFPROBE)
        self.p.osdMessage.emit(tr("no_ffmpeg"))
        return False

    @Property("QVariantList", notify=changed)
    def notes(self):
        return [dict(n, i=i) for i, n in enumerate(self._notes)]

    @Property(int, notify=changed)
    def noteSel(self):
        return self._noteSel

    def _probe(self, path):
        """Off the GUI thread only (saving): the format, read now when not read yet."""
        return self._probes.get(path) or probe(path)

    def _ask(self, path, start):
        key = (path, start)
        if key not in self._kfs and key not in self._asked:
            self._asked.add(key)
            self._reader.submit(self._read, path, start)

    def _read(self, path, start):
        """The reading thread: the file's format (once) and the keyframe at or before start."""
        pr, kf = self._probes.get(path), start
        try:
            pr = pr or probe(path)
            kf = keyframe_before(path, start, pr["start"])
        except Exception:           # noqa: BLE001 - a file that cannot be read starts where it was cut
            log.exception("editor: reading %s failed", path)
        self._found.emit(path, start, kf, pr)

    @Slot(str, float, float, object)
    def _on_found(self, path, start, kf, pr):
        if pr:
            self._probes[path] = pr
        self._kfs[(path, start)] = kf
        self._asked.discard((path, start))
        if self._said and self._said[:2] == (path, start):
            self._say_kf()
        self.changed.emit()
        if self._queued and not self.pending:
            url, self._queued = self._queued, ""
            self.exportTo(url)

    def setCodec(self, codec):
        self.codec = codec
        self.changed.emit()

    def _choose(self, frag=-1, note=-1):
        self._selected, self._noteSel, self._cue = frag, note, -1

    # ---- undo: every change keeps the state it replaced, under a name for the OSD
    def _snap(self):
        return copy.deepcopy((self.frags, self._notes, self._in, self._selected, self._noteSel))

    def _push(self, what, state, merge=None):
        """merge: a key; calls with the same key in quick succession (a drag) are one step."""
        now = time.monotonic()
        if merge is not None and self._merge and self._merge[0] == merge and now - self._merge[1] < UNDO_MERGE:
            self._merge = (merge, now)
            return
        self._merge = (merge, now) if merge is not None else None
        self._undo.append((what, state))
        del self._undo[:-UNDO_STEPS]
        self._redo.clear()

    def _mark(self, what, merge=None):
        self._push(what, self._snap(), merge)

    def _swap(self, src, dst, done, nothing):
        if not src:
            self.p.osdMessage.emit(tr(nothing))
            return
        what, state = src.pop()
        dst.append((what, self._snap()))
        self.frags, self._notes, self._in, self._selected, self._noteSel = state
        self._preview, self._merge, self._active, self._cue = -1, None, True, -1
        for f in self.frags:
            self._ask(f["path"], f["start"])
        log.info("edit %s %s", done, what)
        self.p.osdMessage.emit(tr(done, what))
        self.changed.emit()

    @Slot()
    def undo(self):
        self._swap(self._undo, self._redo, "osd_undone", "osd_nothing_undo")

    @Slot()
    def redo(self):
        self._swap(self._redo, self._undo, "osd_redone", "osd_nothing_redo")

    # ---- editing
    @Slot()
    def toggle(self):
        if self._active:
            self.close()
        elif self.p.hasFile:
            self._active = True
            self.changed.emit()

    @Slot()
    def close(self):
        self._preview = -1
        self._active = False
        self.changed.emit()

    def _here(self):
        """The playing file and position, opening the editor on the way (LosslessCut: I and
        O work from the player)."""
        if not self.p.hasFile:
            return None, 0.0
        if not self._active:
            self._active = True
        return self.p.path, float(self.p.position or 0.0)

    def _fragment(self, path, start, end):
        aid = self.p.aid
        # The sound track that was heard is the one re-encoded; external tracks are not in the file.
        track = next((t for t in self.p.tracks if t.get("type") == "audio" and t.get("id") == aid), {})
        self._ask(path, start)
        return {"path": path, "start": start, "end": end, "aid": 0 if track.get("external") or not aid else aid - 1}

    def _length(self, path):
        return (self._probes.get(path) or {}).get("duration") or self.p.duration

    @Slot()
    def setIn(self):
        path, t = self._here()
        if path:
            self._mark(tr("undo_in", fmt(t)))
            self._in = (path, t)
            self._cue = -1           # a new mark: Space plays the file again
            self.p.osdMessage.emit(tr("osd_in", fmt(t)))
            self.changed.emit()

    def _range(self):
        path, t = self._here()
        if not path:
            return None
        start = self._in[1] if self._in and self._in[0] == path else 0.0
        self._in = None
        if t - start < MIN_LEN:
            self.p.osdMessage.emit(tr("osd_end_before_start"))
            self.changed.emit()
            return None
        return path, start, t

    @Slot()
    def setOut(self):
        """O: the range from the start mark (or the file's beginning) becomes a fragment."""
        if not self._tools():
            return
        before = self._snap()
        r = self._range()
        if r:
            self._push(tr("undo_fragment", fmt(r[1]), fmt(r[2])), before)
            self.frags.append(self._fragment(*r))
            self._choose(frag=len(self.frags) - 1)
            log.info("edit add %s %.2f-%.2f", Path(r[0]).name, r[1], r[2])
            self._said = r
            self._say_kf()
            self.changed.emit()

    def _say_kf(self):
        """The OSD after O; a copied fragment that begins at an earlier keyframe says so once
        the keyframe is known (it is read on its own thread)."""
        path, start, end = self._said
        kf = self._kfs.get((path, start))
        if kf is None and self.lossless:
            if not self._told:
                self._told = True
                self.p.osdMessage.emit(tr("osd_fragment", fmt(start), fmt(end)))
            return
        shift = start - kf if self.lossless else 0
        more = tr("osd_from_keyframe", dec(f"{shift:.1f}")) if shift > 0.05 else ""
        if more or not self._told:
            self.p.osdMessage.emit(tr("osd_fragment", fmt(start), fmt(end)) + more)
        self._said, self._told = None, False

    @Slot()
    def cutOut(self):
        """X: take the range out of this file's fragments, splitting one if the range is
        inside it. A file with no fragment yet counts as kept whole."""
        if not self._tools():
            return
        before = self._snap()
        r = self._range()
        if not r:
            return
        path, a, b = r
        self._push(tr("undo_cut", fmt(a), fmt(b)), before)
        if not any(f["path"] == path for f in self.frags):
            self.frags.append(self._fragment(path, 0.0, self._length(path)))
        out = []
        for f in self.frags:
            if f["path"] != path or f["end"] <= a or f["start"] >= b:
                out.append(f)
                continue
            if f["start"] < a - MIN_LEN:
                out.append(dict(f, end=a))
            if f["end"] > b + MIN_LEN:
                out.append(self._fragment(path, b, f["end"]) | {"aid": f["aid"]})
        self.frags = out
        self._selected = min(self._selected, len(out) - 1)
        log.info("edit cut %s %.2f-%.2f -> %d fragments", Path(path).name, a, b, len(out))
        self.p.osdMessage.emit(tr("osd_cut", fmt(a), fmt(b)))
        self.changed.emit()

    @Slot()
    def addWhole(self):
        path, _t = self._here()
        if path and self._tools():
            self._mark(tr("undo_whole"))
            self.frags.append(self._fragment(path, 0.0, self._length(path)))
            self._choose(frag=len(self.frags) - 1)
            self.changed.emit()

    # ---- drawings over the picture
    @Slot(str, "QVariantList", str, result=int)
    def addNote(self, kind, pts, color):
        """A drawing on the playing file, on screen from now for NOTE_SECONDS; its ends are
        moved on the timeline."""
        path, t = self._here()
        if not path:
            return -1
        end = min(t + NOTE_SECONDS, self.p.duration or t + NOTE_SECONDS)
        self._mark(tr("undo_add", tr("note_" + kind)))
        self._notes.append({"kind": kind, "path": path, "a": t, "b": max(end, t + NOTE_MIN), "color": color,
                            "pts": [[float(x), float(y)] for x, y in pts], "text": ""})
        self._choose(note=len(self._notes) - 1)
        log.info("note %s at %.2f in %s", kind, t, Path(path).name)
        self.changed.emit()
        return self._noteSel

    @Slot(int, "QVariantList")
    def setNotePoints(self, i, pts):
        self._mark(tr("undo_move", tr("note_" + self._notes[i]["kind"])), merge=("pts", i))
        self._notes[i]["pts"] = [[float(x), float(y)] for x, y in pts]
        self.changed.emit()

    @Slot(int, str)
    def setNoteText(self, i, text):
        """An empty text takes the text drawing away. The first text is part of making the
        drawing: one undo takes the new text drawing away whole."""
        old = self._notes[i]["text"]
        if text.strip():
            if text == old:
                return
            if old:
                self._mark(tr("undo_text"))
            self._notes[i]["text"] = text
        else:
            if old:
                self._mark(tr("undo_delete", tr("note_text")))
            elif self._undo and self._undo[-1][0] == tr("undo_add", tr("note_text")):
                self._undo.pop()     # a text drawing left empty was never made
            del self._notes[i]
            self._noteSel = -1
        self.changed.emit()

    @Slot(int, float, float)
    def setNoteRange(self, i, a, b):
        self.setNoteRanges([[i, a, b]])

    @Slot("QVariantList")
    def setNoteRanges(self, ranges):
        """[[i, a, b], …]: drawings dragged on the timeline (with Shift, a few together); the
        first one becomes the chosen drawing. One drag is one undo step."""
        ids = tuple(int(r[0]) for r in ranges)
        self._mark(tr("undo_time", tr("note_" + self._notes[ids[0]]["kind"]) if len(ids) == 1 else tr("note_drawings")),
                   merge=("range", ids))
        for i, a, b in ranges:
            self._notes[int(i)].update(a=float(a), b=float(b))
        self._choose(note=ids[0])
        self.changed.emit()

    @Slot(int, str)
    def setNoteColor(self, i, color):
        if color == self._notes[i]["color"]:
            return
        self._mark(tr("undo_color", tr("note_" + self._notes[i]["kind"])))
        self._notes[i]["color"] = color
        self.changed.emit()

    @Slot(int)
    def selectNote(self, i):
        """A drawing chosen (-1: none); choosing one lets go of the chosen fragment."""
        if i >= 0 and (self._noteSel, self._selected) != (i, -1):
            self._choose(note=i)
            self.changed.emit()
        elif i < 0 <= self._noteSel:
            self._noteSel = -1
            self.changed.emit()

    @Slot(int)
    def cycleNote(self, step):
        """Tab / Shift+Tab: the next or the previous drawing on the frame shown."""
        if not self._active:
            return
        t = float(self.p.position or 0.0)
        here = [i for i, n in enumerate(self._notes) if n["path"] == self.p.path and n["a"] <= t <= n["b"]]
        if not here:
            self.p.osdMessage.emit(tr("osd_no_drawings"))
        elif self._noteSel in here:
            self.selectNote(here[(here.index(self._noteSel) + step) % len(here)])
        else:
            self.selectNote(here[0 if step > 0 else -1])

    @Slot(str)
    def setNoteEnd(self, end):
        """[ and ]: the chosen drawing starts ("a") or ends ("b") at the frame shown, as I and O
        do for a fragment. An end that would cross the other one takes the drawing along."""
        if not self._active:
            return
        i = self._noteSel
        if not 0 <= i < len(self._notes) or self._notes[i]["path"] != self.p.path:
            self.p.osdMessage.emit(tr("osd_pick_drawing"))
            return
        n, t = self._notes[i], float(self.p.position or 0.0)
        self._mark(tr("undo_time", tr("note_" + n["kind"])))
        length = n["b"] - n["a"]
        if end == "a":
            n["a"] = t
            if n["b"] < t + NOTE_MIN:
                n["b"] = min(t + length, self.p.duration or t + length)
        else:
            n["b"] = t
            if n["a"] > t - NOTE_MIN:
                n["a"] = max(0.0, t - length)
        self.p.osdMessage.emit(tr("osd_drawing", fmt(n["a"]), fmt(n["b"])))
        self.changed.emit()

    @Slot()
    def removeSelected(self):
        """Delete: the chosen drawing if there is one, else the chosen fragment."""
        if 0 <= self._noteSel < len(self._notes):
            self._mark(tr("undo_delete", tr("note_" + self._notes[self._noteSel]["kind"])))
            del self._notes[self._noteSel]
            self._noteSel = -1
            self.changed.emit()
        elif 0 <= self._selected < len(self.frags):
            f = self.frags[self._selected]
            self._mark(tr("undo_delete_fragment", fmt(self._from(f)), fmt(f["end"])))
            del self.frags[self._selected]
            self._selected = min(self._selected, len(self.frags) - 1)
            self._preview = -1
            self.changed.emit()

    @Slot(int, int)
    def move(self, row, to):
        """Drag on the strip. Always announces a change: the strip rebuilds its blocks,
        which also puts a block dropped where it was back in place."""
        if 0 <= row < len(self.frags) and 0 <= to < len(self.frags) and row != to:
            self._mark(tr("undo_order"))
            self.frags.insert(to, self.frags.pop(row))
            self._choose(frag=to)
            log.info("edit move %d -> %d", row, to)
        self.changed.emit()

    @Slot(int)
    def select(self, row):
        """A click on a fragment shows its first frame; Space then plays the edit from it."""
        if 0 <= row < len(self.frags):
            self._choose(frag=row)
            self._cue = row
            self._show(row, play=False)
            self.changed.emit()

    @Slot()
    def clear(self):
        if self.frags or self._in:
            self._mark(tr("undo_clear"))
        self.frags, self._selected, self._cue, self._in, self._preview = [], -1, -1, None, -1
        self.changed.emit()

    # ---- preview: only the fragments, in order
    def _show(self, row, play):
        f = self.frags[row]
        if f["path"] == self.p.path:
            self.p.seek(self._from(f))
        else:
            self.p.openAt(f["path"], self._from(f))
        self.p.mpv.pause = not play

    def _play(self, row):
        if row >= len(self.frags):
            self._preview = -1
            self.p.mpv.pause = True
            self.p.osdMessage.emit(tr("osd_preview_over"))
        else:
            self._preview, self._armed = row, False
            self._choose(frag=row)
            self._show(row, play=True)
        self.changed.emit()

    @Slot(int)
    def playFrom(self, row):
        """Enter on a chosen fragment: the edit plays from it, on into the next ones."""
        if 0 <= row < len(self.frags):
            self._play(row)

    @Slot()
    def togglePreview(self):
        """Shift+Space and the strip's key: the whole edit, from its first fragment."""
        if self._preview >= 0:
            self._preview = -1
            self.p.mpv.pause = True
            self.changed.emit()
        elif self.frags:
            self._play(0)

    @Slot(result=bool)
    def playCued(self):
        """Space right after a click on a fragment (the player still inside it): the edit plays
        from there, on into the next fragments. False when there is no such fragment."""
        row, self._cue = self._cue, -1
        if self._preview >= 0 or not 0 <= row < len(self.frags):
            return False
        f, pos = self.frags[row], float(self.p.position or 0.0)
        if f["path"] != self.p.path or not self._from(f) - 0.05 <= pos < f["end"] - END_SLACK:
            return False
        self._preview, self._armed = row, False
        self.p.mpv.pause = False
        self.changed.emit()
        return True

    def _follow(self):
        if self._preview < 0:
            return
        f = self.frags[self._preview]
        pos = self.p.position or 0.0
        if self.p.path != f["path"]:
            return
        if not self._armed:
            # After a jump the old position is still reported for a moment: only a position
            # seen inside the fragment arms the end check.
            self._armed = self._from(f) - 0.5 <= pos < f["end"] - END_SLACK
        elif pos >= f["end"] - END_SLACK or self.p._state["eof"]:
            self._play(self._preview + 1)

    # ---- saving
    @Slot(result=str)
    def suggestedPath(self):
        if not self.frags:
            return ""
        src = Path(self.frags[0]["path"])
        ext = (src.suffix.lower() if src.suffix.lower() in COPY_EXT else ".mkv") if self.lossless else ".mp4"
        word = tr("edit_suffix")
        n, out = 1, src.with_name(f"{src.stem} ({word}){ext}")
        while out.exists():
            n += 1
            out = src.with_name(f"{src.stem} ({word} {n}){ext}")
        return str(out)

    @Slot()
    def requestSave(self):
        """«Save as…»: QML asks where (the save key's right button)."""
        if self.frags and not self.exporting:
            self.saveRequested.emit()

    @Slot()
    def saveHere(self):
        """Ctrl+Shift+S and the save key: at once, beside the first fragment's file, under a
        name that is not taken (the source is never written to)."""
        if self.frags and not self.exporting:
            self.exportTo(self.suggestedPath())

    @Slot(str)
    def exportTo(self, url):
        if not self.frags or self.exporting or not self._tools():
            return
        final = Path(to_path(url))
        if any(final.resolve() == Path(f["path"]).resolve() for f in self.frags):
            self.p.osdMessage.emit(tr("osd_no_overwrite"))
            return
        self._preview = -1
        self._cancelled, self._progress, self._saved, self._error = False, 0.0, "", ""
        if self.pending:
            self._queued = url         # saved as soon as the last keyframe is known
            self.changed.emit()
            return
        part = final.with_name(final.stem + ".part" + final.suffix)
        self.lastLossless = self.lossless
        # The command (ffprobe for a format not read, the encoder check, the drawings' PNGs)
        # is made in the export thread: none of it may hold the picture still.
        job = (self.lossless, "h264" if self.codec == "copy" else self.codec,
               [dict(f, kf=self._kf(f)) for f in self.frags], copy.deepcopy(self._notes))
        self._part = part
        self._thread = threading.Thread(target=self._run, args=(job, part, final, self.total), daemon=True)
        self._thread.start()
        self.changed.emit()

    def _command(self, job, part, work):
        lossless, codec, frags, notes = job
        cmd = self._copy_command(work, frags) if lossless else self._encode_command(codec, work, frags, notes)
        cmd = [_FFMPEG, "-hide_banner", "-nostdin", "-v", "error", "-y"] + cmd + ["-progress", "pipe:1", "-nostats", str(part)]
        log.info("export %s: %s", "copy" if lossless else "encode", subprocess.list2cmdline(cmd))
        return cmd

    def _copy_command(self, work, frags):
        lines = []
        for f in frags:
            s = self._probe(f["path"])["start"]
            lines += ["file '" + f["path"].replace("\\", "/").replace("'", "'\\''") + "'",
                      f"inpoint {s + f['kf']:.6f}", f"outpoint {s + f['end']:.6f}"]
        (work / "list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # all the video and every sound track; subtitles and attachments do not survive the join
        return ["-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
                "-map", "0:v:0?", "-map", "0:a?", "-c", "copy"]

    def _encode_command(self, codec, work, frags, notes):
        probes = [self._probe(f["path"]) for f in frags]
        ref = max(probes, key=lambda p: p["w"] * p["h"])     # the largest picture sets the frame
        w, h = ref["w"] // 2 * 2, ref["h"] // 2 * 2
        layout = next((p["layout"] for p in probes if p["audio"]), "")
        args, chains, pads, layers = [], [], "", []
        for i, (f, pr) in enumerate(zip(frags, probes)):
            args += ["-ss", f"{f['start']:.3f}", "-to", f"{f['end']:.3f}", "-i", f["path"]]
            chain = (f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={ref['fps']},format=yuv420p")
            # Drawings: a PNG per drawing over the picture as it sits in the saved frame,
            # shown between its times counted from the fragment's start (input -ss resets t).
            r = min(w / pr["w"], h / pr["h"]) if pr["w"] and pr["h"] else 1
            pw, ph = round(pr["w"] * r), round(pr["h"] * r)
            label = f"[s{i}]"
            for k, n in enumerate(self._notes_in(f, notes)):
                png = work / f"note{len(layers)}.png"
                render_note(n, (w, h), ((w - pw) // 2, (h - ph) // 2, pw, ph), png)
                layers.append(png)
                chains.append(f"{chain}{label}")
                chain = (f"{label}[{len(frags) + len(layers) - 1}:v]overlay=0:0:"
                         f"enable='between(t,{n['a'] - f['start']:.3f},{n['b'] - f['start']:.3f})'")
                label = f"[s{i}_{k}]"
            chains.append(f"{chain}[v{i}]")
            pads += f"[v{i}]"
            if layout:
                if pr["audio"]:
                    chains.append(f"[{i}:a:{min(f['aid'], pr['audio'] - 1)}]"
                                  f"aformat=sample_rates=48000:channel_layouts={layout}[a{i}]")
                else:   # a file without sound gets silence, so the join keeps its sound in step
                    chains.append(f"anullsrc=r=48000:cl={layout}:d={f['end'] - f['start']:.3f}[a{i}]")
                pads += f"[a{i}]"
        for png in layers:
            args += ["-i", str(png)]
        graph = ";".join(chains) + f";{pads}concat=n={len(frags)}:v=1:a={1 if layout else 0}[v]" + ("[a]" if layout else "")
        args += ["-filter_complex", graph, "-map", "[v]"] + encoder_args(codec)
        if layout:
            args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
        return args

    def _run(self, job, part, final, total):
        """The export thread. It always reports back: a thread that died silently would leave
        the editor «saving» for good (measured before: a busy target did exactly that)."""
        ok, why = False, ""
        work = Path(tempfile.mkdtemp(prefix="oyedit_"))
        try:
            ok, why = self._export(self._command(job, part, work), part, final, work, total)
        except Exception as e:      # noqa: BLE001 - the boundary: report anything, block nothing
            log.exception("export crashed")
            why = tr("err_save_failed", type(e).__name__)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self._done.emit(ok, str(final) if ok else ("" if self._cancelled else why))

    def _export(self, cmd, part, final, work, total):
        if self._cancelled:            # cancelled while the command was being made
            return False, ""
        err = work / "ffmpeg.err"
        with open(err, "w", encoding="utf-8") as e:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=e, text=True,
                                          encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
            for line in self._proc.stdout:
                key, _, val = line.strip().partition("=")
                if key == "out_time_us" and val.lstrip("-").isdigit() and total > 0:
                    self._progressed.emit(min(1.0, max(0.0, int(val) / 1e6 / total)))
            self._proc.wait()
        ok = self._proc.returncode == 0 and not self._cancelled
        msg = err.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        why = ""
        if ok:
            try:
                os.replace(part, final)
            except OSError as e:
                # the target is open in another program (a player, a messenger's upload)
                log.warning("export: cannot replace %s: %s", final, e)
                ok, why = False, tr("err_file_open", final.name)
        elif not self._cancelled:
            log.warning("ffmpeg: %s", " | ".join(msg[-5:]))
            why = explain(msg, final)
        if not ok:
            for _ in range(20):      # a killed ffmpeg's file handle can outlive it for a moment
                try:
                    part.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.1)
        return ok, why

    @Slot(float)
    def _set_progress(self, v):
        self._progress = v
        self.changed.emit()

    @Slot(bool, str)
    def _finished(self, ok, text):
        self._thread.join()
        self._thread = self._proc = None
        if ok:
            self._saved = text
            log.info("export saved %s", text)
            self.p.osdMessage.emit(tr("osd_saved", Path(text).name))
        elif self._cancelled:
            log.info("export cancelled, partial file removed")
            self.p.osdMessage.emit(tr("osd_save_cancelled"))
        else:
            log.warning("export failed: %s", text)
            self._error = tr("err_not_saved", text)
            self.p.osdMessage.emit(self._error)
        self.changed.emit()

    @Slot()
    def cancelExport(self):
        if self._queued:
            self._queued = ""
            self.p.osdMessage.emit(tr("osd_save_cancelled"))
            self.changed.emit()
        if self._thread is not None:
            self._cancelled = True
        if self._proc is not None:
            # The whole tree: ffmpeg from chocolatey is a shim that runs the real ffmpeg.exe,
            # and terminating the shim alone left the encode running (measured).
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self._proc.pid)], capture_output=True,
                           creationflags=_NO_WINDOW)

    def shutdown(self):
        """On exit: a half-written file must not stay behind."""
        thread = self._thread
        self.cancelExport()
        if thread is not None:
            thread.join(10)

    @Slot()
    def revealSaved(self):
        if self._saved:
            subprocess.Popen(["explorer", "/select,", self._saved])
