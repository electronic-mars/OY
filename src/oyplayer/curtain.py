"""A still copy of the monitor over everything while the window goes full screen and back.

After a window changes size Windows composes it at least once with its old picture, unscaled,
in its upper left corner, the rest of it showing what lay under it or black, until the program
presents a frame of the new size: going full screen the window seemed to jump into the corner
first (the owner's slow-motion videos; every composed frame of display 3: 8 of 8 switches in,
3 of 3 out). No wait lets a program get there first: changing just after a composition, with a
whole period to draw, still lost 8 of 8. The curtain shows the screen as it was until the new
frame has been composed once, so only the two states are ever seen (0 of 6, 0 of 3), some
40 ms later.
"""
import ctypes
from ctypes import wintypes as W

from PySide6.QtCore import QObject, QTimer, Slot

u32 = ctypes.WinDLL("user32")
g32 = ctypes.WinDLL("gdi32")
dwmapi = ctypes.WinDLL("dwmapi")

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
u32.DefWindowProcW.restype = ctypes.c_ssize_t
u32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.CreateWindowExW.restype = W.HWND
u32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
u32.GetDC.restype = W.HDC
u32.GetDC.argtypes = [W.HWND]
u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
u32.UpdateLayeredWindow.argtypes = [W.HWND, W.HDC, ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), W.HDC,
                                    ctypes.POINTER(W.POINT), W.COLORREF, ctypes.c_void_p, W.DWORD]
u32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
u32.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
u32.MonitorFromWindow.restype = W.HMONITOR
u32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
g32.CreateCompatibleDC.restype = W.HDC
g32.CreateCompatibleDC.argtypes = [W.HDC]
g32.CreateCompatibleBitmap.restype = W.HBITMAP
g32.CreateCompatibleBitmap.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int]
g32.SelectObject.restype = W.HGDIOBJ
g32.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
g32.DeleteObject.argtypes = [W.HGDIOBJ]
g32.DeleteDC.argtypes = [W.HDC]
g32.BitBlt.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HDC, ctypes.c_int,
                       ctypes.c_int, W.DWORD]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("proc", WNDPROC), ("cls", ctypes.c_int), ("wnd", ctypes.c_int),
                ("inst", W.HINSTANCE), ("icon", W.HICON), ("cursor", W.HANDLE), ("bg", W.HBRUSH),
                ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]


u32.GetMonitorInfoW.argtypes = [W.HMONITOR, ctypes.POINTER(MONITORINFO)]
WS_POPUP = 0x80000000
# layered, topmost, no taskbar button, never active, clicks pass through
WS_EX = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000 | 0x00000020
SRCCOPY, ULW_ALPHA, MONITOR_DEFAULTTONEAREST = 0x00CC0020, 2, 2
HWND_TOPMOST = W.HWND(-1)
SWP_NOACTIVATE, SWP_SHOWWINDOW, SW_HIDE = 0x10, 0x40, 0

_proc = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))
CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITaskbarList2 = "{602D4995-B13A-429b-A66E-1935E44F4317}"


def _taskbar():
    """ITaskbarList2, through which the shell is told at once that a window is going full screen."""
    ole = ctypes.OleDLL("ole32")
    clsid, iid = (ctypes.c_byte * 16)(), (ctypes.c_byte * 16)()
    ole.CLSIDFromString(CLSID_TaskbarList, clsid)
    ole.CLSIDFromString(IID_ITaskbarList2, iid)
    tb = ctypes.c_void_p()
    ole.CoCreateInstance(clsid, None, 1, iid, ctypes.byref(tb))    # CLSCTX_INPROC_SERVER
    vtbl = ctypes.cast(tb, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[3])(tb)              # HrInit
    return tb, ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, W.HWND, W.BOOL)(vtbl[8])  # MarkFullscreenWindow
u32.RegisterClassW(ctypes.byref(WNDCLASSW(0, _proc, 0, 0, None, None, None, None, None, "OYCurtain")))


class Curtain(QObject):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.hwnd = u32.CreateWindowExW(WS_EX, "OYCurtain", "", WS_POPUP, 0, 0, 1, 1, None, None, None, None)
        self.full = None        # the state the window is going to; None: the curtain is down
        self.taskbar, self.mark = _taskbar()
        win.frameSwapped.connect(self._swapped)
        # never a still screen for long, whatever happens to the window
        self.limit = QTimer(self, singleShot=True, interval=500, timeout=self.down)

    @Slot(bool)
    def cover(self, full):
        """Freeze the window's monitor as it is now; down once the window, `full` screen or not,
        has drawn a frame at its new size and Windows has composed it."""
        mi = MONITORINFO(ctypes.sizeof(MONITORINFO))
        u32.GetMonitorInfoW(u32.MonitorFromWindow(int(self.win.winId()), MONITOR_DEFAULTTONEAREST),
                            ctypes.byref(mi))
        r = mi.rcMonitor
        x, y, w, h = r.left, r.top, r.right - r.left, r.bottom - r.top
        screen = u32.GetDC(None)
        mem = g32.CreateCompatibleDC(screen)
        bmp = g32.CreateCompatibleBitmap(screen, w, h)
        old = g32.SelectObject(mem, bmp)
        g32.BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY)
        u32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(W.POINT(x, y)), ctypes.byref(W.SIZE(w, h)), mem,
                                ctypes.byref(W.POINT(0, 0)), 0, ctypes.byref(BLENDFUNCTION(0, 0, 255, 0)), ULW_ALPHA)
        u32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        g32.SelectObject(mem, old)
        g32.DeleteObject(bmp)
        g32.DeleteDC(mem)
        u32.ReleaseDC(None, screen)
        # The taskbar and other always-on-top bars (a dock) stand over a full-screen window until
        # the shell has noticed it: told now, they step back under the curtain (every composed
        # frame of display 3: the dock over the picture for a frame, 4 of 5 entries)
        self.mark(self.taskbar, int(self.win.winId()), full)
        self.full = full
        self.limit.start()

    def _swapped(self):
        if self.full is not None and self.win.property("fullSized") == self.full:
            for _ in range(2):      # the new frame on the screen, and the bars gone, before the curtain goes
                dwmapi.DwmFlush()
            self.down()

    def down(self):
        u32.ShowWindow(self.hwnd, SW_HIDE)
        self.full = None
        self.limit.stop()
