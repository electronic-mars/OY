import QtQuick

// A button with words on it: a raised cap like the panel's keys, the accent when it is the one to press.
Rectangle {
    id: b
    property string text
    property bool accent: false
    property string icon: ""            // a Lucide sign before the words, as MAS's buttons have
    signal clicked()
    width: content.implicitWidth + 24; height: 28; radius: 8
    Accessible.role: Accessible.Button
    Accessible.name: b.text
    Accessible.onPressAction: if (b.enabled) b.clicked()
    opacity: enabled ? 1 : .4
    color: "transparent"
    Raised { z: -1; anchors.fill: parent; radius: b.radius; accent: b.accent; hovered: area.containsMouse; pressed: area.pressed }
    Row {
        id: content
        anchors.centerIn: parent
        spacing: 6
        Icon { visible: b.icon !== ""; anchors.verticalCenter: parent.verticalCenter; name: b.icon; size: 14
               color: b.accent ? Theme.inkOnAcc : Theme.tx }
        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            text: b.text
            color: b.accent ? Theme.inkOnAcc : Theme.tx
            font.family: Theme.uiFont; font.pixelSize: 12
        }
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; onClicked: b.clicked() }
}
