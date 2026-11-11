"""An OpenGL context of the player's own, made with Windows' calls on a hidden window.

libmpv draws with OpenGL into a Direct3D texture (video.py); the window itself is Direct3D's.
Qt's way to such a context (QOffscreenSurface and QOpenGLContext) took 350 ms of every start
on the GUI thread and cannot run beside it (measured: it waits for that thread's messages).
Windows' own calls load the video card's driver in 280 ms on any thread, and a second context
then takes 20 ms: the question «can this card draw into Direct3D textures» is asked on a
thread of its own while the player starts, and the context mpv draws with is made after it.
"""
import ctypes
import threading
from ctypes import wintypes as W

_user32, _gdi32, _opengl32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("opengl32")
_user32.CreateWindowExW.restype = W.HWND
_user32.CreateWindowExW.argtypes = ([W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD] + [ctypes.c_int] * 4
                                    + [W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID])
_user32.GetDC.restype = W.HDC
_user32.GetDC.argtypes = [W.HWND]
_user32.ReleaseDC.argtypes = [W.HWND, W.HDC]
_user32.DestroyWindow.argtypes = [W.HWND]
_opengl32.wglCreateContext.restype = W.HANDLE
_opengl32.wglCreateContext.argtypes = [W.HDC]
_opengl32.wglMakeCurrent.argtypes = [W.HDC, W.HANDLE]
_opengl32.wglDeleteContext.argtypes = [W.HANDLE]
_opengl32.wglGetProcAddress.restype = ctypes.c_void_p
_opengl32.wglGetProcAddress.argtypes = [ctypes.c_char_p]
PFD_DRAW_TO_WINDOW, PFD_SUPPORT_OPENGL, PFD_DOUBLEBUFFER = 0x4, 0x20, 0x1


class _PIXELFORMAT(ctypes.Structure):
    _fields_ = ([("size", W.WORD), ("version", W.WORD), ("flags", W.DWORD), ("type", ctypes.c_byte),
                 ("color_bits", ctypes.c_byte)] + [(f"b{i}", ctypes.c_byte) for i in range(18)]
                + [("layer_mask", W.DWORD), ("visible_mask", W.DWORD), ("damage_mask", W.DWORD)])


_gdi32.ChoosePixelFormat.argtypes = [W.HDC, ctypes.POINTER(_PIXELFORMAT)]
_gdi32.SetPixelFormat.argtypes = [W.HDC, ctypes.c_int, ctypes.POINTER(_PIXELFORMAT)]


class Context:
    """A context on a hidden window of the thread that makes it; that thread uses and frees it."""

    def __init__(self):
        self._hwnd = _user32.CreateWindowExW(0, "STATIC", "", 0, 0, 0, 1, 1, None, None, None, None)
        self._dc = _user32.GetDC(self._hwnd)
        pfd = _PIXELFORMAT(size=ctypes.sizeof(_PIXELFORMAT), version=1, color_bits=32,
                           flags=PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER)
        _gdi32.SetPixelFormat(self._dc, _gdi32.ChoosePixelFormat(self._dc, ctypes.byref(pfd)), ctypes.byref(pfd))
        self._rc = _opengl32.wglCreateContext(self._dc)

    def make_current(self):
        _opengl32.wglMakeCurrent(self._dc, self._rc)

    def done_current(self):
        _opengl32.wglMakeCurrent(None, None)

    def dx_interop(self):
        """Whether it can draw into Direct3D 11 textures (current context). Without a video card
        driver Windows' own OpenGL has no extensions at all: no such entry point, the answer is no."""
        addr = _opengl32.wglGetProcAddress(b"wglGetExtensionsStringARB")
        if not addr:
            return False
        extensions = ctypes.WINFUNCTYPE(ctypes.c_char_p, W.HDC)(addr)(self._dc) or b""
        return b"WGL_NV_DX_interop2" in extensions.split()

    def free(self):
        self.done_current()
        _opengl32.wglDeleteContext(self._rc)
        _user32.ReleaseDC(self._hwnd, self._dc)
        _user32.DestroyWindow(self._hwnd)


class Probe(threading.Thread):
    """Asks the video card, beside the start: by the time the window is made the answer is there,
    and the driver is loaded for the context mpv will draw with."""

    def __init__(self):
        super().__init__(daemon=True)
        self._found = False
        self.start()

    def run(self):
        ctx = Context()
        ctx.make_current()
        self._found = ctx.dx_interop()
        ctx.free()

    def dx_interop(self):
        self.join()
        return self._found
