"""Internet radio.

Stations are .lau files in one folder: the stream's address on the first line, the
station's page on the second, then "-----" and tags (name:, mt: format, br: bitrate,
co: country). They come in UTF-16 with a BOM or in the ANSI code page; both are read.
Recording is mpv's stream-record: the stream's packets as they arrive, without
re-encoding, into a file named after the station and the time.
"""
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QStandardPaths, Qt, Signal, Slot

from .i18n import tr
from .log import home, log

# the stream's codec -> the container its packets are written into
_EXT = {"mp3": ".mp3", "aac": ".aac", "vorbis": ".ogg", "opus": ".ogg", "flac": ".flac"}


def read_lau(path):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251")
    lines = [ln.strip() for ln in text.splitlines()]
    if not lines or "://" not in lines[0]:
        return None
    head, tags = lines, {}
    if "-----" in lines:
        head = lines[:lines.index("-----")]
        for ln in lines[lines.index("-----") + 1:]:
            k, sep, v = ln.partition(":")
            if sep:
                tags[k.strip().lower()] = v.strip()
    return {"url": lines[0], "page": next((ln for ln in head[1:] if "://" in ln), ""),
            "name": tags.get("name") or Path(path).stem, "tags": tags, "file": str(path)}


def write_lau(folder, name, url):
    """The station file's own layout, in UTF-16 with a BOM as its newer files are."""
    safe = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip() or "station"
    path = Path(folder) / f"{safe}.lau"
    path.write_text(f"{url}\r\n\r\n-----\r\nname:{name}\r\n", encoding="utf-16")
    return path


class Radio(QObject):
    changed = Signal()
    _meta = Signal(object)

    def __init__(self, player):
        super().__init__()
        self.p = player
        self.folder = ""             # setting "radioDir"; "" = <home>\Radio
        self.rec_folder = ""         # setting "radioRecDir"; "" = Music\OY Player
        self._recording = ""         # the file being written
        self._rec_start = 0.0
        self._icy = ""
        self._meta.connect(self._on_meta, Qt.QueuedConnection)
        player.mpv.observe_property("metadata", lambda _n, v: self._meta.emit(v))
        player.changed.connect(self._follow)
        self._path = ""

    @Property(str, notify=changed)
    def dir(self):
        return self.folder or str(home() / "Radio")

    @Property(str, notify=changed)
    def recDir(self):
        music = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        return self.rec_folder or str(Path(music) / "OY Player")

    @Property("QVariantList", notify=changed)
    def stations(self):
        d = Path(self.dir)
        if not d.is_dir():
            return []
        out = []
        for f in sorted(d.glob("*.lau"), key=lambda f: f.stem.lower()):
            st = read_lau(f)
            if st:
                t = st["tags"]
                st["info"] = "  ·  ".join(x for x in (t.get("mt", ""), t.get("br", "") and tr("kbps", t["br"]),
                                                       t.get("co", "")) if x)
                del st["tags"]
                out.append(st)
        return out

    @Property(str, notify=changed)
    def nowPlaying(self):
        """The track the station announces (ICY StreamTitle)."""
        return self._icy

    @Property(bool, notify=changed)
    def recording(self):
        return bool(self._recording)

    @Property(str, notify=changed)
    def recordingFile(self):
        return self._recording

    @Property(bool, notify=changed)
    def streaming(self):
        return "://" in (self.p._state["path"] or "")

    def _on_meta(self, meta):
        icy = (meta or {}).get("icy-title", "")
        if icy != self._icy:
            self._icy = icy
            log.info("radio now playing: %s", icy)
            self.changed.emit()

    def _follow(self):
        path = self.p._state["path"] or ""
        if path != self._path:
            self._path = path
            if self._recording:      # another file or station: that recording is finished
                self.stopRecording()
            self.changed.emit()

    @Slot()
    def openDir(self):
        import os
        Path(self.dir).mkdir(parents=True, exist_ok=True)
        os.startfile(self.dir)

    @Slot(str, str)
    def addStation(self, name, url):
        if "://" not in url:
            self.p.osdMessage.emit(tr("osd_need_url"))
            return
        Path(self.dir).mkdir(parents=True, exist_ok=True)
        log.info("radio station added: %s", write_lau(self.dir, name or url, url))
        self.changed.emit()

    @Slot()
    def toggleRecording(self):
        if self._recording:
            self.stopRecording()
        elif self.streaming:
            self.startRecording()
        else:
            self.p.osdMessage.emit(tr("osd_rec_only"))

    def startRecording(self):
        codec = self.p.mpv.audio_codec_name or ""
        url = self.p._state["path"]
        # named after the station, as its .lau calls it; a stream opened by address by its title
        title = next((s["name"] for s in self.stations if s["url"] == url), self.p._state["title"] or "radio")
        name = "".join("_" if c in '<>:"/\\|?*' else c for c in title)[:80]
        Path(self.recDir).mkdir(parents=True, exist_ok=True)
        target = Path(self.recDir) / f"{name} {time.strftime('%Y-%m-%d %H-%M-%S')}{_EXT.get(codec, '.mka')}"
        self.p.mpv["stream-record"] = str(target)
        self._recording, self._rec_start = str(target), time.monotonic()
        log.info("radio recording %s (%s)", target, codec)
        self.p.osdMessage.emit(tr("osd_rec_started"))
        self.changed.emit()

    @Slot()
    def stopRecording(self):
        if not self._recording:
            return
        self.p.mpv["stream-record"] = ""
        log.info("radio recording stopped after %.1f s: %s", time.monotonic() - self._rec_start, self._recording)
        self._recording = ""
        self.p.osdMessage.emit(tr("osd_rec_saved"))
        self.changed.emit()
