"""Every frame Windows composes on one monitor, as a screen recorder sees it (DXGI Desktop
Duplication), for the self-test: a window change that shows a frame of neither state, for a
frame or two, is found here; grabs of the screen every 19 ms caught one about half the time.

    python -m oyplayer.framecap DISPLAY3 <out dir>

Prints «ready», captures until a line comes on stdin, then prints one JSON line. With a still
picture, a state shown 100 ms or more is a real one; any shorter frame unlike all of them is a
glitch. The glitches are tiled into <out dir>/framecap.png.
"""
import ctypes
import json
import sys
import threading
import time
import uuid
from ctypes import wintypes as W

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

P = ctypes.c_void_p
WAIT_TIMEOUT = 0x887A0027
SMALL = 480


def call(ptr, index, argtypes, *args, res=ctypes.c_long):
    vtbl = ctypes.cast(P(ptr), ctypes.POINTER(ctypes.POINTER(P)))[0]
    return ctypes.WINFUNCTYPE(res, P, *argtypes)(vtbl[index])(ptr, *args)


class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        u = uuid.UUID(s)
        super().__init__(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))


class OUTDESC(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar * 32), ("rect", W.RECT), ("attached", W.BOOL), ("rot", ctypes.c_uint), ("mon", P)]


class TEX2D(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint) for n in ("w", "h", "mips", "array", "fmt", "count", "quality",
                                            "usage", "bind", "cpu", "misc")]


class MAPPED(ctypes.Structure):
    _fields_ = [("data", P), ("pitch", ctypes.c_uint), ("depth", ctypes.c_uint)]


def duplicate(name):
    """(D3D device context, duplication, staging texture, width, height) for the output `name`."""
    dxgi, d3d11 = ctypes.WinDLL("dxgi"), ctypes.WinDLL("d3d11")
    fac = P()
    dxgi.CreateDXGIFactory1(ctypes.byref(GUID("770aae78-f26f-4dba-a829-253c83d1b387")), ctypes.byref(fac))
    i = 0
    while True:
        ad = P()
        if call(fac.value, 12, [ctypes.c_uint, ctypes.POINTER(P)], i, ctypes.byref(ad)) != 0:   # EnumAdapters1
            raise RuntimeError(f"no output {name}")
        j = 0
        while True:
            out = P()
            if call(ad.value, 7, [ctypes.c_uint, ctypes.POINTER(P)], j, ctypes.byref(out)) != 0:  # EnumOutputs
                break
            d = OUTDESC()
            call(out.value, 7, [ctypes.POINTER(OUTDESC)], ctypes.byref(d))                       # GetDesc
            if d.name.endswith(name):
                dev, ctx, fl = P(), P(), ctypes.c_uint()
                d3d11.D3D11CreateDevice.argtypes = [P, ctypes.c_uint, P, ctypes.c_uint, P, ctypes.c_uint,
                                                    ctypes.c_uint, ctypes.POINTER(P), ctypes.POINTER(ctypes.c_uint),
                                                    ctypes.POINTER(P)]
                d3d11.D3D11CreateDevice(ad.value, 0, None, 0, None, 0, 7, ctypes.byref(dev), ctypes.byref(fl),
                                        ctypes.byref(ctx))
                out1, dupl = P(), P()
                call(out.value, 0, [ctypes.POINTER(GUID), ctypes.POINTER(P)],
                     ctypes.byref(GUID("00cddea8-939b-4b83-a340-a685226666cc")), ctypes.byref(out1))
                hr = call(out1.value, 22, [P, ctypes.POINTER(P)], dev.value, ctypes.byref(dupl))   # DuplicateOutput
                if hr != 0:
                    raise RuntimeError(f"DuplicateOutput {hr & 0xFFFFFFFF:#x}")
                w, h = d.rect.right - d.rect.left, d.rect.bottom - d.rect.top
                staging = P()
                call(dev.value, 5, [ctypes.POINTER(TEX2D), P, ctypes.POINTER(P)],                 # CreateTexture2D
                     ctypes.byref(TEX2D(w, h, 1, 1, 87, 1, 0, 3, 0, 0x20000, 0)), None, ctypes.byref(staging))
                return ctx.value, dupl.value, staging.value, w, h
            j += 1
        i += 1


def capture(name, stop):
    """[(seconds, small image, full image)] of every composed frame until `stop` is set."""
    ctx, dupl, staging, w, h = duplicate(name)
    tex2d = GUID("6f15aaf2-d208-4e89-9ab4-489535d34f9c")
    info = (ctypes.c_ubyte * 64)()
    frames = []
    t0 = time.perf_counter()
    print("ready", flush=True)
    while not stop.is_set():
        res = P()
        hr = call(dupl, 8, [ctypes.c_uint, P, ctypes.POINTER(P)], 50, info, ctypes.byref(res))  # AcquireNextFrame
        if hr & 0xFFFFFFFF == WAIT_TIMEOUT:
            continue
        if ctypes.c_uint.from_buffer(info, 16).value:      # AccumulatedFrames: 0 is a pointer move only
            tex = P()
            call(res.value, 0, [ctypes.POINTER(GUID), ctypes.POINTER(P)], ctypes.byref(tex2d), ctypes.byref(tex))
            call(ctx, 47, [P, P], staging, tex.value, res=None)                                 # CopyResource
            m = MAPPED()
            call(ctx, 14, [P, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(MAPPED)],
                 staging, 0, 1, 0, ctypes.byref(m))                                             # Map
            raw = ctypes.string_at(m.data, m.pitch * h)
            full = QImage(raw, w, h, m.pitch, QImage.Format_RGB32).copy()
            frames.append((time.perf_counter() - t0, full.scaledToWidth(SMALL, Qt.FastTransformation), full))
            call(ctx, 15, [P, ctypes.c_uint], staging, 0, res=None)                             # Unmap
            call(tex.value, 2, [], res=ctypes.c_ulong)
        call(res.value, 2, [], res=ctypes.c_ulong)
        call(dupl, 14, [])                                                                      # ReleaseFrame
    return frames


def differ(a, b):
    """Share of sampled pixels clearly unlike between two small frames."""
    n = bad = 0
    for y in range(2, a.height(), 6):
        for x in range(2, a.width(), 6):
            p, q = a.pixel(x, y), b.pixel(x, y)
            n += 1
            bad += max(abs((p >> s & 255) - (q >> s & 255)) for s in (0, 8, 16)) > 48
    return bad / n


def main():
    name, out = sys.argv[1], sys.argv[2]
    QGuiApplication([])
    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()), daemon=True).start()
    frames = capture(name, stop)
    shown = [(frames[k + 1][0] if k + 1 < len(frames) else 1e9) - f[0] for k, f in enumerate(frames)]
    states = [f[1] for f, d in zip(frames, shown) if d >= 0.1]
    glitches = [(k, f[0], f[1]) for k, (f, d) in enumerate(zip(frames, shown))
                if d < 0.1 and all(differ(f[1], s) > 0.01 for s in states)]
    if glitches:
        # each glitch between the frames before and after it, one row each
        h = glitches[0][2].height()
        sheet = QImage(SMALL * 3, h * len(glitches), QImage.Format_RGB32)
        sheet.fill(QColor("gray"))
        p = QPainter(sheet)
        p.setPen(QColor("yellow"))
        for row, (k, _t, _im) in enumerate(glitches):
            for col, n in enumerate((k - 1, k, k + 1)):
                if 0 <= n < len(frames):
                    p.drawImage(SMALL * col, h * row, frames[n][1])
                    p.drawText(SMALL * col + 4, h * row + 14, f"#{n} {frames[n][0]:.3f} s"
                               + (" glitch" if n == k else ""))
        p.end()
        sheet.save(out + "\\framecap.png")
        frames[glitches[0][0]][2].save(out + "\\framecap_full.png")     # the first glitch at full size
    print(json.dumps({"frames": len(frames), "states": len(states),
                      "glitches": [round(t, 3) for _k, t, _im in glitches]}), flush=True)


if __name__ == "__main__":
    main()
