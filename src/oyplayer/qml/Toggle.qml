import QtQuick

// MAS switch: an orange track with a white knob when on, a recessed grey one when off.
Item {
    id: t
    property bool checked: false
    property string name: ""            // for a screen reader; SettingRow's title when left empty
    signal toggled(bool on)
    width: 46; height: 26
    Accessible.role: Accessible.CheckBox
    Accessible.name: t.name || (t.parent && t.parent.parent && t.parent.parent.title !== undefined ? t.parent.parent.title : "")
    Accessible.checkable: true
    Accessible.checked: t.checked
    Accessible.onToggleAction: t.toggled(!t.checked)
    Accessible.onPressAction: t.toggled(!t.checked)
    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: t.checked ? Theme.acc : Theme.sunk
        border.color: t.checked ? Qt.rgba(0, 0, 0, .15) : Theme.line
        Behavior on color { ColorAnimation { duration: 120 } }
        Rectangle {
            width: 20; height: 20; radius: 10
            y: 3; x: t.checked ? parent.width - width - 3 : 3
            color: "#F7F7F7"
            border.color: Qt.rgba(0, 0, 0, .2)
            Behavior on x { NumberAnimation { duration: 120 } }
        }
    }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: t.toggled(!t.checked) }
}
