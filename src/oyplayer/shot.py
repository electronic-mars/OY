"""The screenshot editor: the frame shown, as a still picture to draw on with the editor's
tools (NoteLayer, DrawBar), then saved to the screenshots folder, copied to the clipboard,
or closed and dropped.

A drawing here is the editor's drawing without a file and an interval: the same kinds,
points as fractions of the picture, sizes as fractions of its height, painted into the
picture by editor.paint_note(), so what is saved is what was seen.
"""
import copy
import itertools
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage, QPainter

from .editor import LOGO_H, UNDO_MERGE, UNDO_STEPS, paint_note
from .i18n import tr
from .log import log

_grabs = itertools.count()


class ShotEditor(QObject):
    changed = Signal()
    opened = Signal()           # a new frame in the editor: its window comes up
    message = Signal(str)       # undo, copy, a picture that cannot be read: said in the window
    saved = Signal(str)         # the saved file: its name and «Open the folder» for 3 s

    def __init__(self, player, settings, folder):
        super().__init__()
        self.p, self.settings, self.folder = player, settings, folder
        self._active, self._src, self._name = False, "", ""
        self._notes, self._sel, self._undo, self._redo, self._merge = [], -1, [], [], None

    @Slot()
    def open(self):
        """The frame shown now becomes the picture; the drawings of the last one are gone."""
        if not self.p.hasFile:
            return
        src = Path(tempfile.gettempdir()) / f"oyplayer_shot_{next(_grabs)}.png"
        self.p.grab_frame(src)
        if QImage(str(src)).isNull():
            log.warning("shot: no frame in %s", src)
            self.p.osdMessage.emit(tr("osd_shot_none"))
            return
        self._drop_file()
        self._src, self._name = str(src), self.p.shot_name()
        self._notes, self._sel, self._undo, self._redo, self._merge = [], -1, [], [], None
        self._active = True
        log.info("shot editor: %s", self._name)
        self.changed.emit()
        self.opened.emit()

    @Slot()
    def close(self):
        """Closed without saving: the picture and its drawings are dropped."""
        if not self._active:
            return
        self._active = False
        self._drop_file()
        self._src, self._notes, self._sel = "", [], -1
        self.changed.emit()

    def _drop_file(self):
        if self._src:
            Path(self._src).unlink(missing_ok=True)

    @Property(bool, notify=changed)
    def active(self):
        return self._active

    @Property(str, notify=changed)
    def source(self):
        return QUrl.fromLocalFile(self._src).toString() if self._src else ""

    @Property(str, notify=changed)
    def name(self):
        return self._name

    @Property("QVariantList", notify=changed)
    def notes(self):
        return [dict(n, i=i) for i, n in enumerate(self._notes)]

    @Property(int, notify=changed)
    def noteSel(self):
        return self._sel

    # ---- the picture with its drawings
    def picture(self):
        img = QImage(self._src).convertToFormat(QImage.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        for n in self._notes:
            paint_note(p, n, (0, 0, img.width(), img.height()))
        p.end()
        return img.convertToFormat(QImage.Format_RGB32)

    @Slot(result=str)
    def save(self):
        """Into the screenshots folder, in the settings' format; a second save of the same
        picture gets a number instead of writing over the first."""
        if not self._active:
            return ""
        ext = "jpg" if self.settings["shotFormat"] == "jpg" else "png"
        folder = Path(self.folder())
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{self._name}.{ext}"
        k = 2
        while target.exists():
            target, k = folder / f"{self._name} ({k}).{ext}", k + 1
        self.picture().save(str(target), ext.upper(), self.settings["shotQuality"] if ext == "jpg" else -1)
        log.info("shot editor saved %s", target)
        self.saved.emit(str(target))
        return str(target)

    @Slot()
    def copy(self):
        if self._active:
            QGuiApplication.clipboard().setImage(self.picture())
            self.message.emit(tr("osd_shot_copied"))

    # ---- undo: every change keeps the state it replaced, under a name said in the window
    def _mark(self, what, merge=None):
        now = time.monotonic()
        if merge is not None and self._merge and self._merge[0] == merge and now - self._merge[1] < UNDO_MERGE:
            self._merge = (merge, now)
            return
        self._merge = (merge, now) if merge is not None else None
        self._undo.append((what, copy.deepcopy((self._notes, self._sel))))
        del self._undo[:-UNDO_STEPS]
        self._redo.clear()

    def _swap(self, src, dst, done, nothing):
        if not src:
            self.message.emit(tr(nothing))
            return
        what, state = src.pop()
        dst.append((what, copy.deepcopy((self._notes, self._sel))))
        self._notes, self._sel = state
        self._merge = None
        self.message.emit(tr(done, what))
        self.changed.emit()

    @Slot()
    def undo(self):
        self._swap(self._undo, self._redo, "osd_undone", "osd_nothing_undo")

    @Slot()
    def redo(self):
        self._swap(self._redo, self._undo, "osd_redone", "osd_nothing_redo")

    # ---- drawings: the editor's calls (NoteLayer and DrawBar make them), without times
    @Slot(str, "QVariantList", str, float, result=int)
    def addNote(self, kind, pts, color, size):
        self._mark(tr("undo_add", tr("note_" + kind)))
        self._notes.append({"kind": kind, "color": color, "size": size, "text": "",
                            "pts": [[float(x), float(y)] for x, y in pts]})
        self._sel = len(self._notes) - 1
        self.changed.emit()
        return self._sel

    @Slot(str, result=int)
    def addImage(self, url):
        """A picture over the shot: upper right, LOGO_H of its height, proportions kept."""
        src = QUrl(url).toLocalFile() if "://" in url else url
        img, shot = QImage(src), QImage(self._src)
        if img.isNull():
            self.message.emit(tr("osd_no_image"))
            return -1
        wf = LOGO_H * img.width() / img.height() * shot.height() / max(1, shot.width())
        self._mark(tr("undo_add", tr("note_image")))
        self._notes.append({"kind": "image", "color": "#FFFFFF", "text": "", "src": src, "opacity": 1.0,
                            "pts": [[0.97 - wf, 0.04], [0.97, 0.04 + LOGO_H]]})
        self._sel = len(self._notes) - 1
        self.changed.emit()
        return self._sel

    @Slot(int, float)
    def setNoteOpacity(self, i, v):
        if self._notes[i].get("opacity", 1.0) != v:
            self._mark(tr("undo_opacity"))
            self._notes[i]["opacity"] = v
            self.changed.emit()

    @Slot(int, "QVariantList")
    def setNotePoints(self, i, pts):
        self._mark(tr("undo_move", tr("note_" + self._notes[i]["kind"])), merge=("pts", i))
        self._notes[i]["pts"] = [[float(x), float(y)] for x, y in pts]
        self.changed.emit()

    @Slot(int, str)
    def setNoteText(self, i, text):
        """An empty text takes the text drawing away; the first text is part of making it."""
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
            self._sel = -1
        self.changed.emit()

    @Slot(int, str)
    def setNoteColor(self, i, color):
        if color != self._notes[i]["color"]:
            self._mark(tr("undo_color", tr("note_" + self._notes[i]["kind"])))
            self._notes[i]["color"] = color
            self.changed.emit()

    @Slot(int, float)
    def setNoteSize(self, i, size):
        if size != self._notes[i].get("size", 1.0):
            self._mark(tr("undo_size", tr("note_" + self._notes[i]["kind"])))
            self._notes[i]["size"] = size
            self.changed.emit()

    @Slot(int)
    def selectNote(self, i):
        if i != self._sel:
            self._sel = i
            self.changed.emit()

    @Slot()
    def removeSelected(self):
        if 0 <= self._sel < len(self._notes):
            self._mark(tr("undo_delete", tr("note_" + self._notes[self._sel]["kind"])))
            del self._notes[self._sel]
            self._sel = -1
            self.changed.emit()
