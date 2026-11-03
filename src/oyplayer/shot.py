"""The screenshot editor: the frame shown, as a still picture to draw on with the editor's
tools (NoteLayer, DrawBar), then saved to the screenshots folder, copied to the clipboard,
or closed and dropped.

A drawing here is the editor's drawing without a file and an interval: the same kinds,
points as fractions of the picture, sizes as fractions of its height, painted into the
picture by editor.paint_note(), so what is saved is what was seen.
"""
import copy
import itertools
import threading
from pathlib import Path

from PySide6.QtCore import Property, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider

from .editor import LOGO_H, NoteEdits, paint_note
from .i18n import tr
from .log import log

_grabs = itertools.count()


class _Provider(QQuickImageProvider):
    """The frame for the window's Image: from memory, no file written or read."""
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image = QImage()

    def requestImage(self, _id, _size, _requested):
        return self.image


class ShotEditor(NoteEdits):
    changed = Signal()
    opened = Signal()           # a new frame in the editor: its window comes up
    message = Signal(str)       # undo, copy, a picture that cannot be read: said in the window
    saved = Signal(str)         # the saved file: its name and «Open the folder» for 3 s (from the writer's thread)

    def __init__(self, player, settings, folder):
        super().__init__()
        self.p, self.settings, self.folder = player, settings, folder
        self._active, self._img, self._src, self._name = False, QImage(), "", ""
        self.provider = _Provider()
        self._writers = []          # saves still being written: waited for on the way out
        self._notes, self._noteSel, self._undo, self._redo, self._merge = [], -1, [], [], None

    @Slot()
    def open(self):
        """The frame shown now becomes the picture. While drawings are on the last one, the
        window only comes forward: a second press of the key must not wipe them."""
        if not self.p.hasFile:
            return
        if self._active and self._notes:
            self.opened.emit()
            return
        try:
            img = self.p.grab_frame()
        except Exception as e:      # mpv has no frame to give (audio only, still loading)
            log.warning("shot: no frame: %s", e)
            img = QImage()
        if img.isNull():
            self.p.osdMessage.emit(tr("osd_shot_none"))
            return
        self._img = self.provider.image = img
        self._src, self._name = f"image://shot/{next(_grabs)}", self.p.shot_name()
        self._notes, self._noteSel, self._undo, self._redo, self._merge = [], -1, [], [], None
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
        self._img = self.provider.image = QImage()
        self._src, self._notes, self._noteSel = "", [], -1
        self.changed.emit()

    @Property(bool, notify=changed)
    def active(self):
        return self._active

    @Property(str, notify=changed)
    def source(self):
        return self._src

    @Property(str, notify=changed)
    def name(self):
        return self._name

    @Property("QVariantList", notify=changed)
    def notes(self):
        return [dict(n, i=i) for i, n in enumerate(self._notes)]

    @Property(int, notify=changed)
    def noteSel(self):
        return self._noteSel

    # ---- the picture with its drawings
    def picture(self):
        img = self._img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        for n in self._notes:
            paint_note(p, n, (0, 0, img.width(), img.height()))
        p.end()
        return img.convertToFormat(QImage.Format_RGB32)

    @Slot(result=str)
    def save(self):
        """Into the screenshots folder, in the settings' format; a second save of the same
        picture gets a number instead of writing over the first. Written in a thread: a 4K PNG
        takes 0.6 s even at this compression (1.9 s at Qt's default), the window goes on."""
        if not self._active:
            return ""
        ext = "jpg" if self.settings["shotFormat"] == "jpg" else "png"
        folder = Path(self.folder())
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{self._name}.{ext}"
        k = 2
        while target.exists():
            target, k = folder / f"{self._name} ({k}).{ext}", k + 1
        target.touch()      # the name is taken now, before the thread writes it
        img, quality = self.picture(), self.settings["shotQuality"] if ext == "jpg" else 50

        def write():
            if img.save(str(target), ext.upper(), quality):
                log.info("shot editor saved %s", target)
                self.saved.emit(str(target))
            else:       # a full or read-only drive: no empty file left with the name
                log.warning("shot editor could not write %s", target)
                target.unlink(missing_ok=True)
                self.message.emit(tr("osd_shot_failed"))
        self._writers = [t for t in self._writers if t.is_alive()]
        self._writers.append(threading.Thread(target=write))
        self._writers[-1].start()
        return str(target)

    def wait(self):
        """The app leaves with os._exit, which would cut a save short."""
        for t in self._writers:
            t.join()

    @Slot()
    def copy(self):
        if self._active:
            QGuiApplication.clipboard().setImage(self.picture())
            self.message.emit(tr("osd_shot_copied"))

    # ---- undo: every change keeps the state it replaced, under a name said in the window
    def _snap(self):
        return copy.deepcopy((self._notes, self._noteSel))

    def _swap(self, src, dst, done, nothing):
        if not src:
            self.message.emit(tr(nothing))
            return
        what, state = src.pop()
        dst.append((what, self._snap()))
        self._notes, self._noteSel = state
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
        self._noteSel = len(self._notes) - 1
        self.changed.emit()
        return self._noteSel

    @Slot(str, result=int)
    def addImage(self, url):
        """A picture over the shot: upper right, LOGO_H of its height, proportions kept."""
        src = QUrl(url).toLocalFile() if "://" in url else url
        img, shot = QImage(src), self._img
        if img.isNull():
            self.message.emit(tr("osd_no_image"))
            return -1
        wf = LOGO_H * img.width() / img.height() * shot.height() / max(1, shot.width())
        self._mark(tr("undo_add", tr("note_image")))
        self._notes.append({"kind": "image", "color": "#FFFFFF", "text": "", "src": src, "opacity": 1.0,
                            "pts": [[0.97 - wf, 0.04], [0.97, 0.04 + LOGO_H]]})
        self._noteSel = len(self._notes) - 1
        self.changed.emit()
        return self._noteSel

    @Slot(int)
    def selectNote(self, i):
        if i != self._noteSel:
            self._noteSel = i
            self.changed.emit()

    @Slot()
    def removeSelected(self):
        if 0 <= self._noteSel < len(self._notes):
            self._mark(tr("undo_delete", tr("note_" + self._notes[self._noteSel]["kind"])))
            del self._notes[self._noteSel]
            self._noteSel = -1
            self.changed.emit()
