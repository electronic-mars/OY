"""Viewing history.

A file gets into the history once it has been watched past 30 seconds or to its end; the newest comes first, each file once, with where it was
left. Streams stay out: the radio has its own list.
"""
import json
import time
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from .i18n import tr
from .log import home, write_later

KEEP = 500
WATCHED = 30.0


class History(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.enabled = True          # setting "history"
        self._file = home() / "history.json"
        try:
            self._items = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._items = []

    def note(self, path, pos, dur):
        if not self.enabled or not path or "://" in path:
            return
        ended = dur > 0 and pos >= dur - 2
        if pos < WATCHED and not ended:
            return
        self._items = [i for i in self._items if i["path"] != path]
        self._items.insert(0, {"path": path, "at": round(time.time()), "pos": round(pos, 1),
                               "dur": round(dur, 1)})
        del self._items[KEEP:]
        self._save()

    def _save(self):
        write_later(self._file, json.dumps(self._items, ensure_ascii=False))
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def entries(self):
        """For the list: name, folder, when, how much of it was watched (0..1)."""
        today = date.today()
        out = []
        for i in self._items:
            t = datetime.fromtimestamp(i["at"])
            days = (today - t.date()).days
            when = (t.strftime("%H:%M") if days == 0 else tr("yesterday", t.strftime("%H:%M")) if days == 1
                    else t.strftime(tr("date_short" if t.year == today.year else "date_long")))
            p = Path(i["path"])
            out.append({"path": i["path"], "name": p.name, "folder": str(p.parent), "when": when,
                        "frac": min(1.0, i["pos"] / i["dur"]) if i["dur"] else 0.0,
                        "dur": i["dur"]})
        return out

    @Slot(str)
    def remove(self, path):
        self._items = [i for i in self._items if i["path"] != path]
        self._save()

    @Slot()
    def clear(self):
        self._items = []
        self._save()
