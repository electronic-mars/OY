import QtQuick

// A row of options sunk into the body; the chosen one is a raised cap, as the panel's keys.
Rectangle {
    id: seg
    property var options: []          // [{ value, text, enabled? }]
    property var value
    signal picked(var value)
    height: 28
    radius: 8
    color: Theme.sunk
    border.color: Theme.line
    Row {
        anchors.fill: parent
        anchors.margins: 2
        Repeater {
            model: seg.options
            Rectangle {
                width: (seg.width - 4) / seg.options.length
                height: seg.height - 4
                radius: 6
                readonly property bool on: modelData.value === seg.value
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.text
                Accessible.checkable: true
                Accessible.checked: on
                Accessible.onPressAction: if (modelData.enabled !== false) seg.picked(modelData.value)
                color: "transparent"
                Raised { z: -1; visible: parent.on; anchors.fill: parent; radius: parent.radius }
                Text {
                    anchors.centerIn: parent
                    text: modelData.text
                    color: parent.on ? Theme.tx : Theme.tx3
                    opacity: modelData.enabled === false ? .45 : 1
                    font.family: Theme.uiFont; font.pixelSize: 11
                }
                MouseArea { anchors.fill: parent; enabled: modelData.enabled !== false; onClicked: seg.picked(modelData.value) }
            }
        }
    }
}
