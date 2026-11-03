"""Draws OY Player's icon (src/oyplayer/oyplayer.ico): the panel's play key (the knob of variant E,
03.11: a graphite bezel, a ring in the accent, the face of Master Audio Switcher's knob, the orange
sign) without its bezel, round and as wide as the icon (the owner, 03.11: a square body round it took room in the
tray and the taskbar). One drawing per size, so 16 px is drawn for 16 px, not scaled down.

    .venv\\Scripts\\python.exe tools\\make_icon.py

Small sizes are stored as 32-bit bitmaps (every reader takes those), 256 px as PNG.
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPolygonF, QRadialGradient

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
OUT = Path(__file__).resolve().parents[1] / "src" / "oyplayer" / "oyplayer.ico"


def draw(s):
    img = QImage(s, s, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    small = s <= 32
    k = s                             # the knob, as PlayKey draws it at 46 px, edge to edge
    c = s / 2

    def disc(d, brush):
        p.setBrush(brush)
        p.drawEllipse(QRectF(c - d / 2, c - d / 2, d, d))

    # no graphite bezel: on a dark taskbar it vanished and the ring read smaller; the ring is the edge
    ring = k
    g = QLinearGradient(0, c - ring / 2, 0, c + ring / 2)
    g.setColorAt(0, QColor("#FF9A55"))
    g.setColorAt(1, QColor("#B8501A"))
    disc(ring, g)
    # the face: Master Audio Switcher's inner disc, lit up and to the left of its middle
    # the ring as thick as the key draws it only at 256: smaller, a pixel line would vanish
    face = (k * (1 - 4 / 46) if s > 64 else
            ring - 2 * max(2.5, s * .06) if not small else ring - 2 * max(2, s * .1))
    x0 = c - face / 2
    g = QRadialGradient(QPointF(x0 + face * .36, x0 + face * .26), face * 1.2)
    g.setColorAt(0, QColor("#33383F"))
    g.setColorAt(.48, QColor("#23272C"))
    g.setColorAt(1, QColor("#191C20"))
    disc(face, g)
    # the sign as on the key: 40% of the face high, set by its weight a touch right of the middle;
    # smaller sizes larger, or it is a speck
    h = face * (.396 if s > 64 else .46 if s > 32 else .56)
    w = h * .778
    cx = c + face * .04
    p.setBrush(QColor("#F26A21"))
    p.drawPolygon(QPolygonF([QPointF(cx - w / 2, c - h / 2), QPointF(cx + w / 2, c),
                             QPointF(cx - w / 2, c + h / 2)]))
    p.end()
    return img.convertToFormat(QImage.Format_ARGB32)


def dib(img):
    s = img.width()
    rows = [bytes(img.constScanLine(y))[:s * 4] for y in range(s)]
    mask_row = ((s + 31) // 32) * 4
    header = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + b"".join(reversed(rows)) + bytes(mask_row * s)


def png(img):
    buf = QByteArray()
    dev = QBuffer(buf)
    dev.open(QIODevice.WriteOnly)
    img.save(dev, "PNG")
    return bytes(buf)


def main():
    QGuiApplication(sys.argv)
    blobs = [(s, png(draw(s)) if s >= 256 else dib(draw(s))) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(blobs))
    offset = len(head) + 16 * len(blobs)
    entries, data = b"", b""
    for s, blob in blobs:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    OUT.write_bytes(head + entries + data)
    print(OUT, len(head + entries + data), "bytes")


if __name__ == "__main__":
    main()
