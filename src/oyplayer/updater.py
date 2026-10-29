"""The update in the player: one small state for the About panel and the work behind it.

States: idle, checking, current, available, downloading, verifying, installing, failed.
"failed" carries its reason (network, http NNN, release, signature, busy, or an error's
name), which the panel says in words.

The daily look happens by itself (setting "updateCheck") and only tells: the About key
gets a dot. Installing is always the person's click, because a player that restarts on
its own in the middle of a film is not an update anybody wants. The work itself
(feed, signature, download, installer) is update.py.
"""
import threading

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from . import __version__, update
from .log import log

FIRST_LOOK_MS = 60 * 1000             # after the start has settled
DAILY_MS = 24 * 60 * 60 * 1000


class Updater(QObject):
    changed = Signal()
    # the installer is downloaded and signed by us: the player quits, and main() starts
    # the installer once everything is written
    readyToInstall = Signal()

    def __init__(self, busy=lambda: False):
        """busy(): something the quit would cut short (an edit being saved)."""
        super().__init__()
        self._busy = busy
        self._lock = threading.Lock()
        self._s = {"state": "idle", "detail": "", "percent": 0, "offered": ""}
        self._found = None
        self.installer = None
        self._auto = QTimer(self)
        self._auto.timeout.connect(self._daily)

    def _set(self, **fields):
        with self._lock:
            self._s.update(fields)
        self.changed.emit()        # from a worker thread too: QML gets it queued

    def _get(self, k):
        with self._lock:
            return self._s[k]

    @Property(str, notify=changed)
    def state(self):
        return self._get("state")

    @Property(str, notify=changed)
    def detail(self):
        return self._get("detail")

    @Property(int, notify=changed)
    def percent(self):
        return self._get("percent")

    @Property(str, notify=changed)
    def offered(self):
        return self._get("offered")

    def setAuto(self, on):
        if not on:
            self._auto.stop()
        elif not self._auto.isActive():
            self._auto.start(FIRST_LOOK_MS)

    def _daily(self):
        self._auto.setInterval(DAILY_MS)
        if self.state in ("idle", "failed", "current"):
            self._check(manual=False)

    @Slot()
    def check(self):
        if self.state not in ("downloading", "verifying", "installing", "checking"):
            self._check(manual=True)

    def _check(self, manual):
        if manual:
            self._set(state="checking", detail="", percent=0)

        def work():
            try:
                found = update.latest()
            except Exception as e:
                log.warning("update: could not ask about updates: %s", e)
                # a look nobody asked for fails quietly; the next one is tomorrow
                return self._set(state="failed", detail=self.why(e)) if manual else None
            if not update.is_newer(found["version"], __version__):
                log.info("update: %s is the newest version (offered %s)", __version__, found["version"])
                return self._set(state="current", detail="") if manual else None
            log.info("update: %s is available, this is %s", found["version"], __version__)
            self._found = found
            self._set(state="available", detail="", offered=found["version"])
        threading.Thread(target=work, daemon=True, name="oy-update").start()

    @Slot()
    def install(self):
        if not self._found or self.state not in ("available", "failed"):
            return
        if self._busy():
            return self._set(state="failed", detail="busy")
        self._set(state="downloading", detail="", percent=0)
        threading.Thread(target=self._install, args=(self._found,), daemon=True, name="oy-update").start()

    def _install(self, found):
        def progress(got, total):
            if total:       # without a length there is no honest percentage
                self._set(percent=min(100, round(got * 100 / total)))
        try:
            path = update.download(found["url"], progress)
        except Exception as e:
            log.warning("update: the download failed: %s", e)
            return self._set(state="failed", detail=self.why(e))
        self._set(state="verifying", percent=100)
        try:
            signature = bytes.fromhex(found["signature"])
        except ValueError:
            signature = b""
        if not update.verify(path, signature):
            # something calls itself our release and is not: it must never run
            log.error("update: %s is not signed by the release key, deleted", path)
            path.unlink(missing_ok=True)
            return self._set(state="failed", detail="signature")
        log.info("update: %s is signed by the release key", path)
        self.installer = path
        self._set(state="installing")
        self.readyToInstall.emit()

    @staticmethod
    def why(e):
        """A reason short enough for the panel and specific enough to act on."""
        import socket
        import urllib.error
        if isinstance(e, urllib.error.HTTPError):
            return f"http {e.code}"
        if isinstance(e, (urllib.error.URLError, socket.timeout, ConnectionError)):
            return "network"
        if isinstance(e, (ValueError, KeyError)):
            return "release"          # our own refusal of the feed; the log has the specifics
        return type(e).__name__
