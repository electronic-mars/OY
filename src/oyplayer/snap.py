"""Snap Layouts on our own maximize key. The title bar is drawn by QML, so Windows 11 does not
know where its maximize button is and shows no layouts on hover. Here the window answers
WM_NCHITTEST over that key with HTMAXBUTTON; the mouse over it then arrives as non-client
messages, so its hover and click are handled here too. Qt runs the filter on mouse messages
only as they leave the queue: a WM_NCLBUTTONDOWN sent with SendMessage skips it, and Windows'
own button tracking then waits for a mouse release (the selftest posts them).
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QMetaObject, QObject, QPointF

WM_NCHITTEST, WM_NCMOUSEMOVE, WM_NCMOUSELEAVE = 0x0084, 0x00A0, 0x02A2
WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK = 0x00A1, 0x00A2, 0x00A3
HTMAXBUTTON = 9
GWL_STYLE, WS_MAXIMIZEBOX = -16, 0x00010000
TME_LEAVE, TME_NONCLIENT = 0x02, 0x10


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("hwndTrack", wintypes.HWND), ("dwHoverTime", wintypes.DWORD)]


user32 = ctypes.WinDLL("user32")
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
dwmapi = ctypes.WinDLL("dwmapi")
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2


def round_corners(hwnd):
    """Windows 11 rounds the frameless window's corners as its own (not when maximized or
    fullscreen), the way the panel's keys and cards are rounded. Older Windows ignores it."""
    pref = ctypes.c_int(DWMWCP_ROUND)
    return dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                                        ctypes.byref(pref), ctypes.sizeof(pref)) == 0


class SnapKey(QAbstractNativeEventFilter):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.hwnd = int(win.winId())
        self.key = win.findChild(QObject, "keyMax")
        round_corners(self.hwnd)
        QCoreApplication.instance().installNativeEventFilter(self)

    def _maxbox(self):
        # the layouts are offered only to a window with a maximize box; Qt rebuilds the style
        # of a frameless window without it (flags, maximize), so it is put back on every hover
        style = user32.GetWindowLongW(self.hwnd, GWL_STYLE)
        if not style & WS_MAXIMIZEBOX:
            user32.SetWindowLongW(self.hwnd, GWL_STYLE, style | WS_MAXIMIZEBOX)

    def _over(self, lparam):
        if self.win.property("fs") or not self.key.property("visible"):
            return False
        pt = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        user32.ScreenToClient(self.hwnd, ctypes.byref(pt))
        dpr = self.win.devicePixelRatio()
        c = self.key.mapToScene(QPointF(0, 0))
        x, y = pt.x / dpr - c.x(), pt.y / dpr - c.y()
        return 0 <= x < self.key.width() and 0 <= y < self.key.height()

    def _hot(self, on):
        if self.key.property("hot") != on:
            self.key.setProperty("hot", on)

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != self.hwnd:
            return False, 0
        m, on_key = msg.message, msg.wParam == HTMAXBUTTON
        if m == WM_NCHITTEST:
            over = self._over(msg.lParam)
            self._hot(over)
            if over:
                self._maxbox()
                return True, HTMAXBUTTON
        elif m == WM_NCMOUSEMOVE and on_key:
            # a leave is reported only when asked for, once per entry
            tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE | TME_NONCLIENT, self.hwnd, 0)
            user32.TrackMouseEvent(ctypes.byref(tme))
        elif m == WM_NCMOUSELEAVE:
            self._hot(False)
        elif m in (WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK) and on_key:
            return True, 0          # Windows' own button tracking would maximize behind QML's back
        elif m == WM_NCLBUTTONUP and on_key:
            QMetaObject.invokeMethod(self.key, "clicked")
            return True, 0
        return False, 0
