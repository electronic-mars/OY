import QtQuick

// The volume as a knob (a skin's part, Theme.volumeStyle "knob"): Master Audio Switcher's, small —
// a graphite knob, its notch turned to the volume, the percent beside it. Drag up or right for louder; the wheel is the panel's, as on the rail.
Item {
    id: knob
    property real value: 0               // 0..1, as the rail's
    property string valueText: ""
    property string name: ""
    readonly property bool hovered: area.containsMouse
    readonly property bool dragging: area.pressed
    signal moved(real v)

    Accessible.role: Accessible.Dial
    Accessible.name: knob.name
    Accessible.description: knob.valueText

    readonly property real shown: Math.max(0, Math.min(1, value))
    readonly property int dial: Theme.keyH
    width: dial + 6 + percent.implicitWidth
    height: dial

    Item {
        id: face
        width: knob.dial; height: knob.dial
        SoftShadow { anchors.centerIn: parent; width: cap.width; height: cap.height; radius: width / 2
                     blur: 4; dy: 2; color: Qt.rgba(0, 0, 0, .45) }
        Rectangle {
            id: cap
            anchors.centerIn: parent
            width: Math.round(face.width * .8); height: width; radius: width / 2
            border.color: Qt.rgba(1, 1, 1, Theme.light ? .5 : .15)
            gradient: Gradient {
                GradientStop { position: 0; color: area.containsMouse ? Theme.capHiTop : Theme.capTop }
                GradientStop { position: 1; color: Theme.capBot }
            }
            rotation: -135 + knob.shown * 270
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: 2
                        width: 1.5; height: parent.height * .3; radius: .75; color: Theme.tx }
        }
    }
    Text {
        id: percent
        x: knob.dial + 6; anchors.verticalCenter: parent.verticalCenter
        text: knob.valueText
        color: area.containsMouse ? Theme.tx : Theme.tx2
        font.family: Theme.monoFont; font.pixelSize: 11
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.SizeVerCursor
        property real from: 0
        property point at
        onPressed: (m) => { from = knob.shown; at = Qt.point(m.x, m.y) }
        // 120 px of travel from silence to full
        onPositionChanged: (m) => { if (pressed) knob.moved(Math.max(0, Math.min(1, from + ((m.x - at.x) - (m.y - at.y)) / 120))) }
        onWheel: (w) => w.accepted = false
    }
}
