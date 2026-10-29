"""Draws OY Player's icon (src/oyplayer/oyplayer.ico): the panel's round orange play key
on a graphite body. One drawing per size, so 16 px is drawn for 16 px, not scaled down.

    .venv\\Scripts\\python.exe tools\\make_icon.py

Small sizes are stored as 32-bit bitmaps (every reader takes those), 256 px as PNG.
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPolygonF

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
OUT = Path(__file__).resolve().parents[1] / "src" / "oyplayer" / "oyplayer.ico"


def draw(s):
    img = QImage(s, s, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    body = QRectF(s * .04, s * .04, s * .92, s * .92)
    g = QLinearGradient(0, body.top(), 0, body.bottom())
    g.setColorAt(0, QColor("#30353D"))
    g.setColorAt(1, QColor("#1A1D22"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(body, s * .22, s * .22)
    d = s * .64
    disc = QRectF((s - d) / 2, (s - d) / 2, d, d)
    g = QLinearGradient(0, disc.top(), 0, disc.bottom())
    g.setColorAt(0, QColor("#FF8442"))
    g.setColorAt(1, QColor("#E85F18"))
    p.setBrush(g)
    p.drawEllipse(disc)
    t = s * .25                       # the triangle's height, a little right of centre (optical)
    cx, cy = s / 2 + t * .1, s / 2
    p.setBrush(QColor("#140702"))
    p.drawPolygon(QPolygonF([QPointF(cx - t * .45, cy - t / 2), QPointF(cx + t * .55, cy),
                             QPointF(cx - t * .45, cy + t / 2)]))
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
