"""Scheduler: after this file, after the list or in N minutes, pause, close
the player, put the computer to sleep or shut it down. One-shot; the setting
"onListEnd" is the standing version for the end of the list.

Sleep and shutdown come after a visible countdown that can be cancelled. In a self-test
the power actions are only recorded: `power` is replaced before anything can call it.
"""
import ctypes
import subprocess

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .i18n import tr
from .log import log

GRACE = 30           # seconds of countdown before sleep or shutdown


def windows_power(action):
    if action == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)
    elif action == "sleep":
        ctypes.WinDLL("powrprof").SetSuspendState(False, False, False)


class Scheduler(QObject):
    changed = Signal()
    closeRequested = Signal()

    def __init__(self, player, playlist, dry_run):
        super().__init__()
        self.p = player
        self.powered = []            # dry run: what would have been done
        self.power = self.powered.append if dry_run else windows_power
        self.grace = GRACE
        self.list_end = "stop"       # setting "onListEnd"
        self._action = "pause"
        self._when = ""              # "" | file | list | timer
        self._pending = ""           # the action counting down
        self._count = 0
        self._timer = QTimer(self, singleShot=True, timeout=lambda: self._fire("timer"))
        self._tick = QTimer(self, interval=1000, timeout=self._countdown)
        self._clock = QTimer(self, interval=1000, timeout=self.changed.emit)   # the remaining time shown
        player.eofReached.connect(lambda: self._fire("file"))
        playlist.listEnded.connect(self._list_ended)

    # ---- what QML shows
    @Property(str, notify=changed)
    def action(self):
        return self._action

    @Property(str, notify=changed)
    def when(self):
        return self._when

    @Property(int, notify=changed)
    def countdown(self):
        return self._count

    @Property(str, notify=changed)
    def pending(self):
        return self._pending

    @Property(str, notify=changed)
    def summary(self):
        if not self._when:
            return ""
        what = tr("sch_" + self._action)
        if self._when == "timer":
            s = max(0, self._timer.remainingTime() // 1000)
            return tr("sch_in", f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}", what)
        return tr("sch_after_file" if self._when == "file" else "sch_after_list", what)

    # ---- setting it up
    @Slot(str)
    def setAction(self, action):
        self._action = action
        self.changed.emit()

    @Slot(str, float)
    def arm(self, when, minutes=0.0):
        self._when = when
        self._timer.stop()
        self._clock.stop()
        if when == "timer":
            self._timer.start(round(minutes * 60000))
            self._clock.start()
        log.info("scheduler armed: %s %s %.2f min", self._action, when, minutes)
        self.p.osdMessage.emit(tr("osd_scheduler", self.summary[0].lower() + self.summary[1:]))
        self.changed.emit()

    @Slot()
    def cancel(self):
        self._when = ""
        self._timer.stop()
        self._clock.stop()
        self.abort()
        self.changed.emit()

    @Slot()
    def abort(self):
        """Stop a countdown to sleep or shutdown."""
        if self._pending:
            log.info("scheduler: %s cancelled", self._pending)
            self.p.osdMessage.emit(tr("osd_cancelled"))
        self._pending, self._count = "", 0
        self._tick.stop()
        self.changed.emit()

    # ---- running it
    def _list_ended(self):
        if self._when in ("list", "file"):
            self._fire("list")
        elif self.list_end != "stop":
            self._do(self.list_end)

    def _fire(self, event):
        # "after this file" also holds when the file was the list's last one
        if self._when == event or (event == "list" and self._when == "file"):
            action = self._action
            self._when = ""
            self._clock.stop()
            self._do(action)

    def _do(self, action):
        log.info("scheduler: %s", action)
        if action == "pause":
            self.p.mpv.pause = True
            self.p.osdMessage.emit(tr("osd_scheduler", tr("sch_pause")))
        elif action == "close":
            self.closeRequested.emit()
        else:
            self._pending, self._count = action, self.grace
            self._tick.start()
        self.changed.emit()

    def _countdown(self):
        self._count -= 1
        if self._count <= 0:
            action, self._pending = self._pending, ""
            self._tick.stop()
            log.info("scheduler: power %s", action)
            self.power(action)
        self.changed.emit()
