"""The interface's signs: Lucide icons (ISC, icons/LICENSE) drawn for the exact pixels they
take on screen, in any colour. A font's signs at 11-15 px came out squeezed and fuzzy; an SVG
rendered at the requested size (Qt multiplies it by the screen's scaling) stays sharp.

QML: image://icon/<name>/<colour as rrggbb or aarrggbb>[/<stroke width>][/solid]
(Icon.qml builds it). Stroke widths are in Lucide's 24-unit grid; "solid" fills the figure."""
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

DIR = Path(__file__).with_name("icons")


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._svg = {}

    def requestImage(self, id_, _size, requested):
        name, colour, *rest = id_.split("/")
        stroke = next((r for r in rest if r != "solid"), "1.5")
        if name not in self._svg:
            self._svg[name] = (DIR / f"{name}.svg").read_text(encoding="utf-8")
        c = QColor("#" + colour)
        svg = self._svg[name].replace('stroke-width="2"', f'stroke-width="{stroke}"').replace("currentColor", c.name())
        if "solid" in rest:
            svg = svg.replace('fill="none"', f'fill="{c.name()}"', 1)
        w = requested.width() if requested.width() > 0 else 24
        h = requested.height() if requested.height() > 0 else w
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(c.alphaF())
        QSvgRenderer(QByteArray(svg.encode())).render(p)
        p.end()
        return img
