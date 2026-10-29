"""Media keys: play/pause, next, previous and stop on a keyboard's media
keys. While the player has the focus they arrive as ordinary keys (actions.py); with the
setting "globalMedia" they reach it from any program, as RegisterHotKey hotkeys. Other
programs (a music player, a browser) then no longer get them, so it is off by default.
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

from .log import log

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
KEYS = {1: (0xB3, "play_pause"), 2: (0xB0, "next"), 3: (0xB1, "prev"), 4: (0xB2, "stop")}
user32 = ctypes.WinDLL("user32")
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]


class MediaKeys(QAbstractNativeEventFilter):
    def __init__(self, win, actions):
        super().__init__()
        self.win, self.a = win, actions
        self.hwnd = 0
        self.active = False
        self.held = []               # the hotkeys Windows gave us

    def setGlobal(self, on):
        if on == self.active:
            return
        self.active = on
        app = QCoreApplication.instance()
        if on:
            self.hwnd = int(self.win.winId())
            for hid, (vk, _name) in KEYS.items():
                if user32.RegisterHotKey(self.hwnd, hid, MOD_NOREPEAT, vk):
                    self.held.append(hid)
                else:
                    log.warning("media key %#x is taken by another program", vk)
            # every window message passes the filter: it is there only while it is needed
            app.installNativeEventFilter(self)
        else:
            for hid in self.held:
                user32.UnregisterHotKey(self.hwnd, hid)
            self.held = []
            app.removeNativeEventFilter(self)
        log.info("global media keys %s (%d held)", "on" if on else "off", len(self.held))

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.hWnd == self.hwnd and msg.wParam in KEYS:
            self.a.run(KEYS[msg.wParam][1])
            return True, 0
        return False, 0
