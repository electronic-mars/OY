"""Playlist: what plays next, kept across runs.

Behaviour: opening a file adds it to the list and plays it
(PlayList.AddInsteadReplacing=1); at the end of a file the next one plays
(OnDone.PlayDoneOnFileEnd=1); Repeat loops the list, Repeat file loops one file.
Durations come from ffprobe in the background; a row on screen asks for a small frame of its
file (ffmpeg, cached in <home>/thumbs by path, size and time of change).
"""
import hashlib
import json
import random
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, Qt, QTimer, QUrl, Signal,
                            Slot)
from PySide6.QtGui import QImage, QPainter, QPainterPath

from .i18n import tr
from .log import home, log, write_later

MEDIA_EXT = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".ts", ".m2ts",
             ".mts", ".mpg", ".mpeg", ".vob", ".3gp", ".ogv", ".rm", ".rmvb", ".divx", ".asf",
             ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".ape", ".wv",
             ".mka", ".ac3", ".dts", ".mpc", ".tta", ".alac", ".aiff", ".mid", ".midi"}
REPEAT_OFF, REPEAT_ALL, REPEAT_ONE = 0, 1, 2
_FFPROBE = shutil.which("ffprobe")
_FFMPEG = shutil.which("ffmpeg")


def to_path(url):
    """QUrl or text; file:///D:/x.mkv -> D:\\x.mkv; anything else (http, etc.) stays as it is."""
    if isinstance(url, QUrl):
        return str(Path(url.toLocalFile())) if url.isLocalFile() else url.toString()
    if url.startswith("file:"):
        p = unquote(urlparse(url).path)
        return str(Path(p.lstrip("/") if re.match(r"^/[A-Za-z]:", p) else p))
    return url


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def expand(paths):
    """Files stay; folders become their media files, naturally sorted (ep2 before ep10)."""
    out = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files = [f for f in path.rglob("*") if f.suffix.lower() in MEDIA_EXT and f.is_file()]
            out += [str(f) for f in sorted(files, key=lambda f: natural_key(str(f)))]
        else:
            out.append(str(p))
    return out


def named_file(path):
    """A path that names a media file or a station by itself: added without asking the disk."""
    return "://" in path or Path(path).suffix.lower() in MEDIA_EXT or path.lower().endswith(".lau")


def probe_duration(path):
    if not _FFPROBE or not Path(path).is_file():
        return 0.0
    try:
        r = subprocess.run([_FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return float(r.stdout.strip() or 0)
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0


def make_thumb(path, dur):
    """A frame a tenth of the way in, 128 px wide with rounded corners (a PNG: Qt does not clip a
    picture to its frame's radius), as a file URL; "" for a stream, a sound file or anything
    ffmpeg cannot read."""
    f = Path(path)
    if not _FFMPEG or "://" in path or not f.is_file():
        return ""
    st = f.stat()
    out = home() / "thumbs" / (hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20] + ".png")
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        frame = out.with_suffix(".bmp")
        try:
            subprocess.run([_FFMPEG, "-v", "error", "-nostdin", "-ss", f"{dur * 0.1:.2f}", "-i", path, "-frames:v", "1",
                            "-vf", "scale=128:72:force_original_aspect_ratio=increase,crop=128:72", "-y", str(frame)],
                           capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        except (subprocess.TimeoutExpired, OSError):
            return ""
        img = QImage(str(frame))
        frame.unlink(missing_ok=True)
        if img.isNull():
            return ""
        rounded = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        rounded.fill(Qt.GlobalColor.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, img.width(), img.height(), 9, 9)      # 4 px at the row's 56 px
        p.setClipPath(clip)
        p.drawImage(0, 0, img)
        p.end()
        rounded.save(str(out))
    return QUrl.fromLocalFile(str(out)).toString() if out.is_file() else ""


class Playlist(QAbstractListModel):
    PathRole, TitleRole, DurationRole, PlayingRole, ThumbRole = range(Qt.UserRole + 1, Qt.UserRole + 6)

    changed = Signal()
    _durationReady = Signal(str, float)
    _thumbReady = Signal(str, str)
    _expanded = Signal(object, bool)        # a folder's files, read off the GUI thread; play
    _found = Signal(str, object)            # an opened episode and the ones after it

    listEnded = Signal()

    def __init__(self, player):
        super().__init__()
        self.p = player
        self.adds = True            # setting "openAdds": opening adds to the list
        self.series = True          # setting "series": an opened episode brings the next ones
        self.items = []            # dicts: path, title, duration
        self._current = -1
        self._repeat = REPEAT_OFF
        self._shuffle = False
        self._order = []           # play order when shuffled (indices into items)
        self._selected = -1        # the row the user picked; Delete / Ctrl+arrows act on it
        self._file = home() / "playlist.json"
        self._saveTimer = QTimer(self, singleShot=True, interval=500, timeout=self._save_state)
        self._pool = ThreadPoolExecutor(max_workers=2)
        # Folders and the next episodes are read by a thread of their own, in order: a folder
        # of thousands of files or a network path that went away must not hold the picture.
        self._reader = ThreadPoolExecutor(max_workers=1)
        self._durationReady.connect(self._set_duration, Qt.QueuedConnection)
        self._thumbReady.connect(self._set_thumb, Qt.QueuedConnection)
        self._thumbing = set()     # files whose frame was asked for in this run
        self._expanded.connect(self._insert, Qt.QueuedConnection)
        self._found.connect(self._add_following, Qt.QueuedConnection)
        self.p.eofReached.connect(self._on_eof)
        self.p.loadFailed.connect(self._on_failed)
        self._failed = 0           # files in a row that did not open
        self._load()

    # ---- model
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def roleNames(self):
        return {self.PathRole: b"path", self.TitleRole: b"title",
                self.DurationRole: b"duration", self.PlayingRole: b"playing", self.ThumbRole: b"thumb"}

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        it = self.items[index.row()]
        return {self.PathRole: it["path"], self.TitleRole: it["title"],
                self.DurationRole: it["duration"],
                self.PlayingRole: index.row() == self._current,
                self.ThumbRole: it.get("thumb", ""),
                Qt.DisplayRole: it["title"]}.get(role)

    # ---- properties for QML
    @Property(int, notify=changed)
    def current(self):
        return self._current

    @Property(int, notify=changed)
    def count(self):
        return len(self.items)

    @Property(int, notify=changed)
    def repeat(self):
        return self._repeat

    @Property(bool, notify=changed)
    def shuffle(self):
        return self._shuffle

    def _get_selected(self):
        return self._selected

    def _set_selected(self, row):
        if row != self._selected:
            self._selected = row
            self.changed.emit()

    selected = Property(int, _get_selected, _set_selected, notify=changed)

    @Property(float, notify=changed)
    def totalDuration(self):
        return sum(i["duration"] for i in self.items)

    # ---- editing
    def _item(self, path):
        if path.lower().endswith(".lau"):
            # a radio station file: the list keeps its address under the station's name
            from .radio import read_lau
            st = read_lau(path)
            if st:
                return {"path": st["url"], "title": st["name"], "duration": 0.0}
        title = Path(path).name if "://" not in path else path
        return {"path": path, "title": title, "duration": 0.0}

    @Slot("QVariantList", bool)
    def add(self, urls, play=True):
        """Files go in at once; a folder's files follow when the reading thread has them."""
        paths = [to_path(u) for u in urls]
        if all(named_file(p) for p in paths):
            self._insert(paths, play)
        else:
            self._reader.submit(lambda: self._expanded.emit(expand(paths), play))

    @Slot(object, bool)
    def _insert(self, paths, play):
        if not paths:
            return
        if play and not self.adds:
            self.clear()            # setting: opening replaces the list
        first = len(self.items)
        self.beginInsertRows(QModelIndex(), first, first + len(paths) - 1)
        self.items += [self._item(p) for p in paths]
        self.endInsertRows()
        self._reshuffle()
        for p in paths:
            self._pool.submit(lambda p=p: self._durationReady.emit(p, probe_duration(p)))
        log.info("playlist add %d (now %d)", len(paths), len(self.items))
        if play and self.series and len(paths) == 1:
            # setting "series": one opened episode brings the ones after it
            self._reader.submit(self._following, paths[0])
        if play:
            self.playIndex(first)
        self._changed()

    def _following(self, path):
        from . import series
        self._found.emit(path, series.following(path))

    @Slot(str, object)
    def _add_following(self, path, later):
        known = {i["path"] for i in self.items}
        later = [p for p in later if p not in known]
        if path in known and later:
            self._insert(later, False)

    @Slot(int)
    def remove(self, row):
        if not 0 <= row < len(self.items):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.items[row]
        self.endRemoveRows()
        if row < self._current:
            self._current -= 1
        elif row == self._current:
            self._current = -1        # the playing file keeps playing, it just left the list
        self._reshuffle()
        self._changed()

    @Slot()
    def clear(self):
        self.beginResetModel()
        self.items = []
        self._current = -1
        self.endResetModel()
        self._reshuffle()
        self._changed()

    @Slot(int, int)
    def move(self, row, delta):
        to = row + delta
        if not (0 <= row < len(self.items) and 0 <= to < len(self.items)):
            return
        self.beginMoveRows(QModelIndex(), row, row, QModelIndex(), to + 1 if delta > 0 else to)
        self.items.insert(to, self.items.pop(row))
        self.endMoveRows()
        if self._current in (row, to):
            self._current = to if self._current == row else row
        self._reshuffle()
        self._changed()

    @Slot()
    def sortByName(self):
        playing = self.items[self._current]["path"] if self._current >= 0 else None
        self.beginResetModel()
        self.items.sort(key=lambda i: natural_key(i["title"]))
        self.endResetModel()
        self._current = next((n for n, i in enumerate(self.items) if i["path"] == playing), -1)
        self._reshuffle()
        self._changed()

    @Slot(str)
    def save(self, url):
        path = Path(to_path(url))
        lines = ["#EXTM3U"]
        for i in self.items:
            lines.append(f"#EXTINF:{int(i['duration']) or -1},{i['title']}")
            lines.append(i["path"])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("playlist saved %s", path)

    # ---- playing
    @Slot(int)
    def playIndex(self, row):
        if not 0 <= row < len(self.items):
            return
        old = self._current
        self._current = row
        self.p.open(self.items[row]["path"])
        for r in {old, row} - {-1}:
            if r < len(self.items):
                self.dataChanged.emit(self.index(r), self.index(r), [self.PlayingRole])
        self._changed()

    def _step(self, direction):
        if not self.items:
            return
        if self._shuffle and self._current in self._order:
            pos = self._order.index(self._current) + direction
            if 0 <= pos < len(self._order):
                self.playIndex(self._order[pos])
            elif self._repeat == REPEAT_ALL:
                self._reshuffle()
                self.playIndex(self._order[0] if direction > 0 else self._order[-1])
            return
        nxt = self._current + direction
        if 0 <= nxt < len(self.items):
            self.playIndex(nxt)
        elif self._repeat == REPEAT_ALL:
            self.playIndex(0 if direction > 0 else len(self.items) - 1)

    @Slot()
    def next(self):
        self._step(+1)

    @Slot()
    def prev(self):
        self._step(-1)

    @Slot()
    def cycleRepeat(self):
        self._repeat = (self._repeat + 1) % 3
        self.p.osdMessage.emit(tr(("osd_repeat_off", "osd_repeat_list", "osd_repeat_file")[self._repeat]))
        self._changed()

    @Slot()
    def toggleRepeatFile(self):
        self._repeat = REPEAT_OFF if self._repeat == REPEAT_ONE else REPEAT_ONE
        self.p.osdMessage.emit(tr("osd_repeat_file" if self._repeat == REPEAT_ONE else "osd_repeat_off"))
        self._changed()

    @Slot()
    def toggleShuffle(self):
        self._shuffle = not self._shuffle
        self._reshuffle()
        self.p.osdMessage.emit(tr("osd_shuffle_on" if self._shuffle else "osd_shuffle_off"))
        self._changed()

    def _reshuffle(self):
        # The playing file stays first, so turning shuffle on does not jump elsewhere.
        rest = [i for i in range(len(self.items)) if i != self._current]
        random.shuffle(rest)
        self._order = ([self._current] if self._current >= 0 else []) + rest

    def _on_failed(self, path, _why):
        """A file that does not open is passed over, as a file that ended would be. A list
        where nothing opens stops once round; that is not «the list has played»: it must not
        start «when the list ends: shut down»."""
        if not (0 <= self._current < len(self.items)) or self.items[self._current]["path"] != path:
            return
        self._failed += 1
        if self._failed >= len(self.items) or self._repeat == REPEAT_ONE:
            log.info("playlist: nothing here opens, stopped")
            self._failed = 0
            return
        before = self._current
        self.next()
        if self._current == before:
            self._failed = 0

    def _on_eof(self):
        self._failed = 0
        if self._repeat == REPEAT_ONE:
            self.p.seek(0.0)
            self.p.mpv.pause = False
            return
        before = self._current
        self.next()
        if self._current == before:
            log.info("playlist end")
            self.listEnded.emit()

    @Slot(int)
    def wantThumb(self, row):
        """A row came on screen: its frame, once per file and run, from the pool."""
        if not 0 <= row < len(self.items):
            return
        it = self.items[row]
        path = it["path"]
        if path in self._thumbing or "://" in path:
            return
        self._thumbing.add(path)
        self._pool.submit(lambda: self._thumbReady.emit(path, make_thumb(path, it["duration"] or probe_duration(path))))

    def _set_thumb(self, path, url):
        for n, it in enumerate(self.items):
            if it["path"] == path and it.get("thumb", "") != url:
                it["thumb"] = url
                self.dataChanged.emit(self.index(n), self.index(n), [self.ThumbRole])

    # ---- persistence
    def _set_duration(self, path, dur):
        for n, it in enumerate(self.items):
            if it["path"] == path and it["duration"] != dur:
                it["duration"] = dur
                self.dataChanged.emit(self.index(n), self.index(n), [self.DurationRole])
        self._changed()

    def _changed(self):
        self.changed.emit()
        self._saveTimer.start()     # coalesce: a folder of 500 files arrives as 500 durations

    def flush(self):
        """Write a pending change now (called on exit)."""
        if self._saveTimer.isActive():
            self._saveTimer.stop()
            self._save_state()

    def _save_state(self):
        data = {"items": self.items, "current": self._current,
                "repeat": self._repeat, "shuffle": self._shuffle}
        write_later(self._file, json.dumps(data, ensure_ascii=False))

    def _load(self):
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.items = [i for i in data.get("items", []) if isinstance(i, dict) and "path" in i]
        self._repeat = data.get("repeat", REPEAT_OFF)
        self._shuffle = data.get("shuffle", False)
        # Not resumed automatically: the list comes back, the
        # player starts idle, and the last file is marked so Play/Next continue from it.
        self._current = data.get("current", -1) if self.items else -1
        self._reshuffle()
