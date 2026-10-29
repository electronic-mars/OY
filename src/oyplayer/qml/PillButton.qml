import QtQuick

// A button with words on it: a raised cap like the panel's keys, the accent when it is the one to press.
Rectangle {
    id: b
    property string text
    property bool accent: false
    signal clicked()
    width: label.implicitWidth + 24; height: 28; radius: 8
    Accessible.role: Accessible.Button
    Accessible.name: b.text
    Accessible.onPressAction: if (b.enabled) b.clicked()
    opacity: enabled ? 1 : .4
    color: "transparent"
    Raised { z: -1; anchors.fill: parent; radius: b.radius; accent: b.accent; hovered: area.containsMouse; pressed: area.pressed }
    Text {
        id: label
        anchors.centerIn: parent
        text: b.text
        color: b.accent ? Theme.inkOnAcc : Theme.tx
        font.family: Theme.uiFont; font.pixelSize: 12
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; onClicked: b.clicked() }
}
