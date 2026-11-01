import QtQuick

// A Lucide sign (icons.py), drawn for the pixels it takes on this screen, in any colour.
// Stroke is in Lucide's 24-unit grid: 1.5 is the panel's line, as in the concept.
Image {
    id: ic
    property string name: ""
    property color color: Theme.glyph
    property int size: 16
    property real stroke: 1.5
    property bool solid: false          // a filled figure: the play and pause signs
    width: size; height: size
    sourceSize: Qt.size(size, size)
    source: name !== "" ? "image://icon/" + name + "/" + String(color).slice(1) + "/" + stroke + (solid ? "/solid" : "") : ""
    fillMode: Image.PreserveAspectFit
    smooth: true
}
