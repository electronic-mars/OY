import QtQuick

// A soft shadow without an effect pass, as CSS draws `0 dy blur colour`: rounded rectangles a
// pixel apart, each a little transparent, so the dark falls off over `blur` pixels around the
// shape's edge. Lay it under the shape with the same size and radius.
Item {
    id: sh
    property real radius: 0
    property int blur: 6
    property real dy: 3
    property color color: Qt.rgba(0, 0, 0, .22)
    // each layer's share, so that where all of them overlap the shadow has the full alpha
    readonly property real layerAlpha: 1 - Math.pow(1 - color.a, 1 / Math.max(1, blur))
    Repeater {
        model: Math.max(1, sh.blur)
        Rectangle {
            readonly property real e: index - (sh.blur - 1) / 2      // from inside the edge to outside it
            x: -e; y: sh.dy - e
            width: sh.width + 2 * e; height: sh.height + 2 * e
            radius: Math.max(0, sh.radius + e)
            color: Qt.rgba(sh.color.r, sh.color.g, sh.color.b, sh.layerAlpha)
        }
    }
}
