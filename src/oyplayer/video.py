"""Video underlay: libmpv draws into the window's own frame before Qt Quick draws the UI.

Everything QML puts in the scene lands on top of the picture, so OSD, fullscreen
panels and the editor's drawing layer need no second window, and
QQuickWindow.grabWindow() captures the video too.

The window is drawn with Direct3D 11, Windows' own way: OpenGL's way to the screen blacked the
window out on each full-screen switch and screen recorders saw black (NVIDIA), and switches
looked slower than in Direct3D players (the owner's comparison). libmpv draws only with
OpenGL, so it draws into a Direct3D texture through WGL_NV_DX_interop2 (NVIDIA, AMD and Intel
drivers have it), copied into the frame under the UI (D3DUnderlay). A machine without it gets
the OpenGL window: mpv draws straight into Qt's framebuffer (VideoUnderlay).

Where the picture sits inside the window is mpv's business (video-margin-ratio-*),
set by the player from the layout.
"""
import ctypes

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QOffscreenSurface, QOpenGLContext
from PySide6.QtQuick import QSGRendererInterface

import mpv

_opengl32 = ctypes.WinDLL("opengl32")
_wglGetProcAddress = _opengl32.wglGetProcAddress
_wglGetProcAddress.restype = ctypes.c_void_p
_wglGetProcAddress.argtypes = [ctypes.c_char_p]
_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.GetProcAddress.restype = ctypes.c_void_p
_kernel32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
_glGetIntegerv = _opengl32.glGetIntegerv
_glGetIntegerv.restype = None
_glGetIntegerv.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
GL_FRAMEBUFFER_BINDING = 0x8CA6
_GL_TESTS_OFF = (0x0B71, 0x0C11, 0x0B90, 0x0BE2, 0x0B44)  # DEPTH, SCISSOR, STENCIL, BLEND, CULL_FACE


def _get_proc_address(_ctx, name):
    # wglGetProcAddress answers only for post-1.1 entry points; the 1.1 core is
    # exported by opengl32.dll itself. Drivers signal "absent" with 0..3 or -1.
    addr = _wglGetProcAddress(name)
    if addr in (None, 0, 1, 2, 3, ctypes.c_void_p(-1).value):
        addr = _kernel32.GetProcAddress(_opengl32._handle, name)
    return addr or 0


_proc_fn = mpv.MpvGlGetProcAddressFn(_get_proc_address)


def _gl_fn(name, res, *args):
    return ctypes.WINFUNCTYPE(res, *args)(_get_proc_address(None, name.encode()))


def dx_interop():
    """Whether the video card's OpenGL can draw into Direct3D 11 textures. Needs a QGuiApplication."""
    surface = QOffscreenSurface()
    surface.create()
    ctx = QOpenGLContext()
    if not ctx.create() or not ctx.makeCurrent(surface):
        return False
    _opengl32.wglGetCurrentDC.restype = ctypes.c_void_p
    ext = _gl_fn("wglGetExtensionsStringARB", ctypes.c_char_p, ctypes.c_void_p)
    found = b"WGL_NV_DX_interop2" in (ext(_opengl32.wglGetCurrentDC()) or b"").split()
    ctx.doneCurrent()
    return found


H, U = ctypes.c_void_p, ctypes.c_uint
GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D = 0x8D40, 0x8CE0, 0x0DE1
WGL_ACCESS_WRITE_DISCARD_NV = 2
D3D11_BIND_SHADER_RESOURCE, D3D11_BIND_RENDER_TARGET = 0x8, 0x20


def _com(ptr, index, res, *args):
    """The method at `index` of the COM object at `ptr`."""
    vtbl = ctypes.cast(ctypes.c_void_p(ptr), ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(res, ctypes.c_void_p, *args)(vtbl[index])


def _release(ptr):
    _com(ptr, 2, U)(ptr)


class _TEX2D(ctypes.Structure):
    _fields_ = [(n, U) for n in ("w", "h", "mips", "array", "fmt", "count", "quality",
                                 "usage", "bind", "cpu", "misc")]


class _BOX(ctypes.Structure):
    _fields_ = [(n, U) for n in ("left", "top", "front", "right", "bottom", "back")]


class D3DUnderlay(QObject):
    """The Direct3D 11 window's underlay: mpv draws with its own OpenGL context into a Direct3D
    texture of the frame's size, copied into the frame before Qt Quick draws the UI. All of it
    runs on the render thread (the GUI thread: the basic render loop)."""

    ready = Signal()
    frameReady = Signal()

    def __init__(self, window, player):
        super().__init__()
        self._win = window
        self._player = player
        self._ctx = None
        self._tex = None        # (w, h, format, D3D texture, GL texture, interop handle)
        self._fbo = U(0)
        self._surface = QOffscreenSurface()     # made on the GUI thread, as Qt requires
        self._surface.create()
        self.frameReady.connect(window.update, Qt.QueuedConnection)
        window.beforeRenderPassRecording.connect(self._render, Qt.DirectConnection)
        window.sceneGraphInvalidated.connect(self._free, Qt.DirectConnection)

    def _init_ctx(self):
        self._gl = QOpenGLContext()
        self._gl.create()
        self._gl.makeCurrent(self._surface)
        f = self._f = {
            "open": _gl_fn("wglDXOpenDeviceNV", H, H),
            "close": _gl_fn("wglDXCloseDeviceNV", ctypes.c_int, H),
            "reg": _gl_fn("wglDXRegisterObjectNV", H, H, H, U, U, U),
            "unreg": _gl_fn("wglDXUnregisterObjectNV", ctypes.c_int, H, H),
            "lock": _gl_fn("wglDXLockObjectsNV", ctypes.c_int, H, ctypes.c_int, ctypes.POINTER(H)),
            "unlock": _gl_fn("wglDXUnlockObjectsNV", ctypes.c_int, H, ctypes.c_int, ctypes.POINTER(H)),
            "genfb": _gl_fn("glGenFramebuffers", None, ctypes.c_int, ctypes.POINTER(U)),
            "bindfb": _gl_fn("glBindFramebuffer", None, U, U),
            "fbtex": _gl_fn("glFramebufferTexture2D", None, U, U, U, U, ctypes.c_int),
        }
        ri = self._win.rendererInterface()
        self._dev = int(ri.getResource(self._win, QSGRendererInterface.Resource.DeviceResource))
        self._dc = int(ri.getResource(self._win, QSGRendererInterface.Resource.DeviceContextResource))
        self._hdev = f["open"](H(self._dev))
        f["genfb"](1, ctypes.byref(self._fbo))
        self._ctx = mpv.MpvRenderContext(
            self._player, "opengl", opengl_init_params={"get_proc_address": _proc_fn})
        self._ctx.update_cb = self.frameReady.emit
        self.ready.emit()

    def _drop_texture(self):
        _w, _h, _fmt, d3d, gltex, hobj = self._tex
        self._f["unreg"](self._hdev, hobj)
        _opengl32.glDeleteTextures(1, ctypes.byref(U(gltex)))
        _release(d3d)
        self._tex = None

    def _texture(self, w, h, fmt):
        # the frame's own size and format: CopySubresourceRegion copies only between alike textures
        if self._tex:
            self._drop_texture()
        desc = _TEX2D(w, h, 1, 1, fmt, 1, 0, 0, D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE, 0, 0)
        d3d = ctypes.c_void_p()
        _com(self._dev, 5, ctypes.c_long, ctypes.POINTER(_TEX2D), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            self._dev, ctypes.byref(desc), None, ctypes.byref(d3d))                 # CreateTexture2D
        gltex = U()
        _opengl32.glGenTextures(1, ctypes.byref(gltex))
        hobj = self._f["reg"](self._hdev, d3d, gltex.value, GL_TEXTURE_2D, WGL_ACCESS_WRITE_DISCARD_NV)
        self._f["bindfb"](GL_FRAMEBUFFER, self._fbo.value)
        self._f["fbtex"](GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, gltex.value, 0)
        self._tex = (w, h, fmt, d3d.value, gltex.value, hobj)

    def _render(self):
        self._win.beginExternalCommands()
        if self._ctx is None:
            self._init_ctx()
        # the texture the pass draws into (the window's back buffer, or grabWindow's target): its
        # size is the frame's real one, so a resized window gets the picture at its new size at once
        rtv = ctypes.c_void_p()
        _com(self._dc, 89, None, U, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)(
            self._dc, 1, ctypes.byref(rtv), None)                                   # OMGetRenderTargets
        target = ctypes.c_void_p()
        _com(rtv.value, 7, None, ctypes.POINTER(ctypes.c_void_p))(rtv.value, ctypes.byref(target))  # GetResource
        _release(rtv.value)
        td = _TEX2D()
        _com(target.value, 10, None, ctypes.POINTER(_TEX2D))(target.value, ctypes.byref(td))         # GetDesc
        self._gl.makeCurrent(self._surface)
        if not self._tex or self._tex[:3] != (td.w, td.h, td.fmt):
            self._texture(td.w, td.h, td.fmt)
        objs = (H * 1)(self._tex[5])
        self._f["lock"](self._hdev, 1, objs)
        self._f["bindfb"](GL_FRAMEBUFFER, self._fbo.value)
        _opengl32.glViewport(0, 0, td.w, td.h)
        # a Direct3D texture's first row is the top: no flip
        self._ctx.render(flip_y=False, opengl_fbo={"w": td.w, "h": td.h, "fbo": self._fbo.value})
        self._f["unlock"](self._hdev, 1, objs)
        self._gl.doneCurrent()
        box = _BOX(0, 0, 0, td.w, td.h, 1)
        _com(self._dc, 46, None, ctypes.c_void_p, U, U, U, U, ctypes.c_void_p, U, ctypes.POINTER(_BOX))(
            self._dc, target.value, 0, 0, 0, 0, self._tex[3], 0, ctypes.byref(box))  # CopySubresourceRegion
        _release(target.value)
        self._win.endExternalCommands()

    def _free(self):
        # mpv frees its GL objects with its context current; the window goes before mpv terminates
        if self._ctx is not None:
            self._gl.makeCurrent(self._surface)
            self._ctx.free()
            self._ctx = None
            if self._tex:
                self._drop_texture()
            self._f["close"](self._hdev)
            self._gl.doneCurrent()


class VideoUnderlay(QObject):
    """The OpenGL window's underlay: binds one mpv instance to one QQuickWindow. All GL work runs
    on Qt's render thread."""

    ready = Signal()        # render context exists: files may be loaded from now on
    frameReady = Signal()   # mpv has a new frame (emitted from an mpv thread)

    def __init__(self, window, player):
        super().__init__()
        self._win = window
        self._player = player
        self._ctx = None
        self._size = (0, 0)
        self.frameReady.connect(window.update, Qt.QueuedConnection)
        window.beforeSynchronizing.connect(self._sync, Qt.DirectConnection)
        window.beforeRendering.connect(self._init_ctx, Qt.DirectConnection)
        window.beforeRenderPassRecording.connect(self._render, Qt.DirectConnection)
        window.sceneGraphInvalidated.connect(self._free, Qt.DirectConnection)

    def _init_ctx(self):
        if self._ctx is not None:
            return
        self._win.beginExternalCommands()
        self._ctx = mpv.MpvRenderContext(
            self._player, "opengl", opengl_init_params={"get_proc_address": _proc_fn})
        self._ctx.update_cb = self.frameReady.emit
        self._win.endExternalCommands()
        self.ready.emit()

    def _sync(self):
        # The frame's size in device pixels, read while the GUI thread waits for the sync. Not
        # GL_VIEWPORT: when mpv draws, the pass's viewport is not set yet and still holds the last
        # frame's, so the first frame after a resize came out at the old size in the lower left
        # corner, and stayed so on a paused video (the owner's full-screen screenshots).
        dpr = self._win.effectiveDevicePixelRatio()
        self._size = (round(self._win.width() * dpr), round(self._win.height() * dpr))

    def _render(self):
        if self._ctx is None:
            return
        self._win.beginExternalCommands()
        fbo = ctypes.c_int()
        _glGetIntegerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(fbo))
        # Qt's scene graph leaves depth/scissor/stencil tests and masks set for its own
        # pass; with them mpv's frame never reaches the pixels (measured: a black
        # window at 30 renders/s). mpv expects plain default state.
        for cap in _GL_TESTS_OFF:
            _opengl32.glDisable(cap)
        _opengl32.glColorMask(1, 1, 1, 1)
        _opengl32.glDepthMask(1)
        w, h = self._size
        _opengl32.glViewport(0, 0, w, h)
        self._ctx.render(flip_y=True, opengl_fbo={"w": w, "h": h, "fbo": fbo.value})
        self._win.endExternalCommands()

    def _free(self):
        # Runs on the render thread with the GL context current, as mpv requires.
        # The owner must therefore destroy the window before terminating mpv.
        if self._ctx is not None:
            self._ctx.free()
            self._ctx = None
