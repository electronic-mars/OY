import QtQuick

// Flat title-bar button (MAS .iconbtn): no cap, a card appears under it on hover.
Rectangle {
    id: b
    property string glyph: ""           // a Lucide icon's name (Icon.qml)
    property bool latched: false
    property bool danger: false
    property string tip: ""
    property bool hot: false            // the pointer is over it as Windows' button (snap.py)
    readonly property bool lit: area.containsMouse || hot
    signal clicked()
    width: 28; height: 24; radius: 6
    Accessible.role: Accessible.Button
    Accessible.name: b.tip.replace(/\s*\([^)]*\)/g, "").trim()
    Accessible.onPressAction: b.clicked()
    color: lit ? (danger ? Qt.rgba(1, .42, .42, .15) : Theme.card) : "transparent"
    border.color: lit ? (danger ? Qt.rgba(1, .42, .42, .35) : Theme.line) : "transparent"
    Icon {
        objectName: "sign"
        anchors.centerIn: parent
        name: b.glyph
        size: 14
        color: b.latched ? Theme.accText : b.lit ? (b.danger ? "#FF6B6B" : Theme.tx) : Theme.tx3
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; onClicked: b.clicked() }
    Tip { text: b.tip; shown: area.containsMouse && !area.pressed && b.tip !== ""; under: true }
}
