"""The notification-area icon.

Setting "tray": off | on (an icon beside the taskbar button) | minimize (minimising hides
the window into the icon). A click shows or hides the window, the middle button pauses,
the right one opens the menu.
"""
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import lang, tr
from .log import log


class Tray(QObject):
    def __init__(self, win, actions, player, icon):
        super().__init__()
        self.win, self.a, self.p = win, actions, player
        self.mode = "off"
        self.icon = QSystemTrayIcon(icon, self)
        self.icon.setToolTip("OY Player")
        self.menu = QMenu()
        self._items = []             # (action, i18n key): renamed when the language changes
        for key, fn in (("tray_show", self.toggleWindow),
                        ("act_play_pause", lambda: actions.run("play_pause")),
                        ("tray_next", lambda: actions.run("next")),
                        ("tray_prev", lambda: actions.run("prev")),
                        ("act_mute", lambda: actions.run("mute")),
                        (None, None),
                        ("tray_exit", win.close)):
            if key is None:
                self.menu.addSeparator()
            else:
                item = self.menu.addAction(tr(key))
                item.triggered.connect(fn)
                self._items.append((item, key))
        lang.changed.connect(lambda: [item.setText(tr(key)) for item, key in self._items])
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        win.windowStateChanged.connect(self._state)
        self._title = ""
        player.changed.connect(self._tip)

    def setMode(self, mode):
        self.mode = mode
        self.icon.setVisible(mode != "off")
        if mode == "off" and not self.win.isVisible():
            self.showWindow()        # never leave a hidden window without its way back
        log.info("tray %s", mode)

    def _tip(self):
        title = self.p._state["title"] or ""
        if title != self._title:
            self._title = title
            self.icon.setToolTip(f"{title} — OY Player" if title else "OY Player")

    def _state(self, state):
        log.info("window state %s", state)
        if self.mode == "minimize" and state & Qt.WindowMinimized:
            # after the minimise has finished: hidden inside its own state change, the window
            # came straight back as normal (measured: Minimized, then NoState 4 ms later)
            QTimer.singleShot(0, self._hide_if_minimized)

    def _hide_if_minimized(self):
        if self.win.windowStates() & Qt.WindowMinimized:
            self.win.hide()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggleWindow()
        elif reason == QSystemTrayIcon.MiddleClick:
            self.a.run("play_pause")

    def toggleWindow(self):
        if self.win.isVisible() and not self.win.windowStates() & Qt.WindowMinimized:
            self.win.hide()
        else:
            self.showWindow()

    def showWindow(self):
        self.win.setWindowStates(self.win.windowStates() & ~Qt.WindowMinimized)
        self.win.show()
        self.win.raise_()
        if not self.win.flags() & Qt.WindowDoesNotAcceptFocus:     # a self-test window never takes focus
            self.win.requestActivate()
