import QtQuick

// A row of options sunk into the body; the chosen one is a raised cap, as the panel's keys.
Rectangle {
    id: seg
    property var options: []          // [{ value, text, enabled? }]
    property var value
    signal picked(var value)
    // equal parts while each option's words fit in one; else each its words and a share of the rest
    readonly property var parts: {
        var n = options.length, room = width - 4, needs = options.map(o => fm.advanceWidth(o.text) + 16)
        if (Math.max(...needs) <= room / n) return needs.map(() => room / n)
        var rest = Math.max(0, room - needs.reduce((a, b) => a + b, 0)) / n
        return needs.map(w => w + rest)
    }
    FontMetrics { id: fm; font.family: Theme.uiFont; font.pixelSize: 11 }
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
                width: seg.parts[index] || 0
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
