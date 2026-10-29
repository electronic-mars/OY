"""Skipping openings and end credits.

Marked once in one episode, the opening and the end credits are skipped in every file of
that folder of about the same length. The
opening is a stretch from its start (Alt+E, or the file's start) to its end (Shift+E);
the credits are kept as time before the end (Shift+O), since episodes differ by seconds
and the credits end with the file. Each is skipped once per opening of a file, so seeking
back into it shows it. Skipping the credits goes to the next file the way the end of a
file does.
"""
import json
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from .i18n import tr
from .log import home, log, write_later

TOLERANCE = 180      # seconds: durations are compared in 3-minute steps


def fmt(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


class AutoSkip(QObject):
    changed = Signal()
    toggled = Signal(bool)       # Alt+O: the setting follows

    def __init__(self, player):
        super().__init__()
        self.p = player
        self.enabled = True      # setting "autoskip"
        self._file = home() / "skips.json"
        try:
            self._rules = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._rules = {}
        self._key = ("", 0.0)    # the file and duration the marks were last matched to
        self._done = set()       # what was skipped since this file was opened
        self._start = None       # (path, seconds): a marked start of the opening
        player.changed.connect(self._tick)
        player.positionChanged.connect(self._tick)

    def _state(self):
        s = self.p._state
        return s["path"], s["position"] or 0.0, s["duration"] or 0.0

    def _folder(self, path):
        return str(Path(path).parent) if path and "://" not in path else ""

    def _rule(self):
        """The folder's marks, if they fit the file playing."""
        path, _pos, dur = self._state()
        r = self._rules.get(self._folder(path))
        if not r or not dur:
            return None
        return r if abs(dur - r["dur"]) <= min(TOLERANCE, r["dur"] * 0.25) else None

    @Property("QVariantList", notify=changed)
    def bands(self):
        """[[from, to]] of the file playing that are skipped, for the seek bar."""
        r = self._rule() if self.enabled else None
        if not r:
            return []
        dur = self._state()[2]
        out = [r["open"]] if r.get("open") else []
        if r.get("end"):
            out.append([dur - r["end"], dur])
        return out

    def _tick(self):
        path, pos, dur = self._state()
        if (path, dur) != self._key:       # the duration comes after the path: both decide the marks
            if path != self._key[0]:
                self._done = set()
            self._key = (path, dur)
            self.changed.emit()
        r = self._rule() if self.enabled else None
        if not r:
            return
        op, end = r.get("open"), r.get("end")
        if op and "open" not in self._done and op[0] - 0.25 <= pos < op[1] - 1:
            self._done.add("open")
            log.info("autoskip opening %s -> %.1f", Path(path).name, op[1])
            self.p.seek(op[1])
            self.p.osdMessage.emit(tr("osd_opening_skipped"))
        elif end and "end" not in self._done and dur - end <= pos < dur - 0.5:
            self._done.add("end")
            log.info("autoskip credits %s at %.1f", Path(path).name, pos)
            self.p.osdMessage.emit(tr("osd_credits_skipped"))
            # the end of the file: the next one plays, or the list ends, as after any file. The
            # command itself: python-mpv's seek() adds a precision argument that made this seek
            # stop short of the end, with no end of file (measured)
            self.p.mpv.command("seek", 100, "absolute-percent+exact")

    def _save(self, folder, **marks):
        r = self._rules.setdefault(folder, {})
        r.update(marks, dur=round(self._state()[2], 1))
        log.info("autoskip marks %s: %s", folder, r)
        self._save_all()

    @Slot()
    def markOpeningStart(self):
        path, pos, _dur = self._state()
        if not self._folder(path):
            return
        self._start = (path, pos)
        self.p.osdMessage.emit(tr("osd_opening_start", fmt(pos)))

    @Slot()
    def markOpeningEnd(self):
        path, pos, _dur = self._state()
        folder = self._folder(path)
        if not folder:
            return
        a = self._start[1] if self._start and self._start[0] == path and self._start[1] < pos else 0.0
        self._start = None
        self._done.add("open")          # it is behind us in this file
        self._save(folder, open=[round(a, 1), round(pos, 1)])
        self.p.osdMessage.emit(tr("osd_opening_saved", fmt(a), fmt(pos)))

    @Slot()
    def markCredits(self):
        """'Set beginning of end': from here on is credits; the next file plays."""
        path, pos, dur = self._state()
        folder = self._folder(path)
        if not folder or not dur:
            return
        self._save(folder, end=round(dur - pos, 1))

    @Slot()
    def forget(self):
        folder = self._folder(self._state()[0])
        if self._rules.pop(folder, None) is not None:
            self._save_all()
            self.p.osdMessage.emit(tr("osd_skips_forgotten"))

    def _save_all(self):
        write_later(self._file, json.dumps(self._rules, ensure_ascii=False))
        self.changed.emit()

    @Slot()
    def toggle(self):
        self.setEnabled(not self.enabled)
        self.p.osdMessage.emit(tr("osd_autoskip_on" if self.enabled else "osd_autoskip_off"))
        self.toggled.emit(self.enabled)

    def setEnabled(self, on):
        if on != self.enabled:
            self.enabled = on
            self.changed.emit()

    @Property(bool, notify=changed)
    def on(self):
        return self.enabled

    @Property(bool, notify=changed)
    def marked(self):
        """The folder of the file playing has marks (they may not fit this file's length)."""
        return self._folder(self._state()[0]) in self._rules
