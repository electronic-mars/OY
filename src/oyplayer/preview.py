"""Frame preview over the seek bar.

A second mpv, hidden — no picture or sound output, software decoding, frames scaled
down — opens the same file and seeks to the keyframe under the pointer. It has its own demuxer, decoder and thread, so the playing
instance is never asked for anything. Measured: 8-16 ms a frame for a 640x360 and a
1080p clip, quick enough to follow the pointer; requests that pile up meanwhile are
dropped for the newest one.
"""
import threading

import mpv
from PySide6.QtCore import Property, QObject, Qt, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from .log import log

WIDTH = 320    # decoded width; QML shows it a little smaller, sharp up to 150 % scaling


class _Provider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image = QImage()

    def requestImage(self, _id, _size, _requested):
        return self.image


class Preview(QObject):
    changed = Signal()
    _ready = Signal(QImage, str, float)     # from the worker thread: frame, file, its time

    def __init__(self):
        super().__init__()
        self.provider = _Provider()
        self._cond = threading.Condition()
        self._want = None              # (path, seconds): only the newest request is served
        self._stop = False
        self._mpv = None
        self._loaded = ""
        self._failed = ""              # a file with no picture to show (sound only, unreadable)
        self._serial = 0
        self._shown = ("", -1.0)
        self._ready.connect(self._show, Qt.QueuedConnection)
        self._thread = threading.Thread(target=self._run, name="preview", daemon=True)
        self._thread.start()

    @Property(str, notify=changed)
    def source(self):
        """The newest frame for QML's Image; a new URL each time, so it is fetched again."""
        return f"image://preview/{self._serial}" if self._serial else ""

    @Property(str, notify=changed)
    def path(self):
        return self._shown[0]

    @Property(float, notify=changed)
    def frameTime(self):
        """Where in the file the shown frame is: the keyframe at or before the pointer."""
        return self._shown[1]

    @Slot(str, float)
    def request(self, path, seconds):
        # A stream would need a second connection for each look: not worth a thumbnail.
        if not path or "://" in path or path == self._failed:
            return
        with self._cond:
            self._want = (path, max(0.0, seconds))
            self._cond.notify()

    def shutdown(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(2)
        # mpv must not be destroyed under a command still running on the worker
        if self._mpv is not None and not self._thread.is_alive():
            self._mpv.terminate()

    @Slot(QImage, str, float)
    def _show(self, image, path, at):
        self.provider.image = image
        self._serial += 1
        self._shown = (path, at)
        self.changed.emit()

    def _run(self):
        while True:
            with self._cond:
                while self._want is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                (path, seconds), self._want = self._want, None
            try:
                self._ready.emit(*self._grab(path, seconds))
            except (TimeoutError, SystemError, RuntimeError, ValueError, AttributeError) as e:
                # what python-mpv raises for a file with no picture or one it cannot read
                log.warning("preview %s at %.1f: %r", path, seconds, e)
                self._failed, self._loaded = path, ""

    def _grab(self, path, seconds):
        if self._mpv is None:
            self._mpv = mpv.MPV(vo="null", ao="null", aid="no", sid="no", pause="yes", hr_seek="no",
                                keep_open="yes", idle="yes", hwdec="no", cache="no",
                                demuxer_readahead_secs=0, vd_lavc_threads=2, vf=f"scale=w={WIDTH}:h=-2",
                                ytdl="no", osc="no", input_default_bindings="no", loglevel="error",
                                sws_allow_zimg="no",    # as the main player: zimg lightens full-range video

                                log_handler=lambda lvl, comp, text: log.warning("preview mpv %s %s: %s",
                                                                                lvl, comp, text.strip()))
        m = self._mpv
        if path != self._loaded:
            with m.prepare_and_wait_for_event("playback_restart", timeout=5):
                m.loadfile(path)
            self._loaded = path
        with m.prepare_and_wait_for_event("playback_restart", timeout=3):
            m.command("seek", seconds, "absolute+keyframes")
        shot = m.command("screenshot-raw", "video")       # bgr0 = QImage's RGB32 in memory
        image = QImage(shot["data"], shot["w"], shot["h"], shot["stride"], QImage.Format_RGB32).copy()
        return image, path, m.time_pos or 0.0
