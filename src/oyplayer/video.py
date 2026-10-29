"""Video underlay: libmpv draws into the window's own frame before Qt Quick draws the UI.

Everything QML puts in the scene lands on top of the picture, so OSD, fullscreen
panels and the editor's drawing layer need no second window. Python owns no GL
object here: mpv draws into whatever framebuffer Qt has bound for the pass, which
also makes QQuickWindow.grabWindow() capture the video.

Where the picture sits inside the window is mpv's business (video-margin-ratio-*),
set by the player from the layout.
"""
import ctypes

from PySide6.QtCore import QObject, Qt, Signal

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
GL_VIEWPORT = 0x0BA2
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


class VideoUnderlay(QObject):
    """Binds one mpv instance to one QQuickWindow. All GL work runs on Qt's render thread."""

    ready = Signal()        # render context exists: files may be loaded from now on
    frameReady = Signal()   # mpv has a new frame (emitted from an mpv thread)

    def __init__(self, window, player):
        super().__init__()
        self._win = window
        self._player = player
        self._ctx = None
        self.frameReady.connect(window.update, Qt.QueuedConnection)
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

    def _render(self):
        if self._ctx is None:
            return
        self._win.beginExternalCommands()
        vp = (ctypes.c_int * 4)()
        _glGetIntegerv(GL_VIEWPORT, vp)
        fbo = ctypes.c_int()
        _glGetIntegerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(fbo))
        # Qt's scene graph leaves depth/scissor/stencil tests and masks set for its own
        # pass; with them mpv's frame never reaches the pixels (measured: a black
        # window at 30 renders/s). mpv expects plain default state.
        for cap in _GL_TESTS_OFF:
            _opengl32.glDisable(cap)
        _opengl32.glColorMask(1, 1, 1, 1)
        _opengl32.glDepthMask(1)
        self._ctx.render(flip_y=True, opengl_fbo={"w": vp[2], "h": vp[3], "fbo": fbo.value})
        self._win.endExternalCommands()

    def _free(self):
        # Runs on the render thread with the GL context current, as mpv requires.
        # The owner must therefore destroy the window before terminating mpv.
        if self._ctx is not None:
            self._ctx.free()
            self._ctx = None
