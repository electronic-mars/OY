import QtQuick

// A slider sunk into the body: dark recessed groove, a fill in the accent, a metal cap as thumb.
// While the user drags, the rail shows the drag position, not the model value, so the
// thumb never jumps back under the pointer.
Item {
    id: rail
    property real value: 0                 // 0..1 from the model
    property real grooveHeight: 6
    readonly property bool dragging: area.pressed
    readonly property real shown: dragging ? dragValue : Math.max(0, Math.min(1, value))
    property real dragValue: 0
    property real hoverValue: area.mouseX / width
    readonly property bool hovered: area.containsMouse
    property bool accent: true             // false: the fill is neutral metal (the volume)
    property bool bare: false              // only the pointer's part: the editor draws its own track
    property real pressValue: 0            // where the last press was
    property string name: ""               // for a screen reader: what it sets…
    property string valueText: ""          // …and where it stands, in words
    signal moved(real v)        // while dragging
    signal released(real v)     // on release

    implicitHeight: 16
    Accessible.role: Accessible.Slider
    Accessible.name: rail.name
    Accessible.description: rail.valueText

    // the groove: cut into the body, shade inside along its top, a hairline of light under it
    Rectangle {
        visible: !rail.bare
        anchors.fill: groove; anchors.topMargin: 1; anchors.bottomMargin: -1
        radius: groove.radius; color: Theme.grooveEdge
    }
    Rectangle {
        id: groove
        visible: !rail.bare
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width; height: rail.grooveHeight; radius: height / 2
        color: Theme.groove
        Rectangle {
            anchors.fill: parent; radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(0, 0, 0, Theme.light ? .25 : .6) }
                GradientStop { position: Math.min(1, 2 / Math.max(1, groove.height)); color: "transparent" }
            }
        }
        Rectangle {
            width: Math.max(height, rail.shown * parent.width); height: parent.height; radius: parent.radius
            visible: rail.enabled && rail.shown > 0
            gradient: Gradient {
                GradientStop { position: 0; color: rail.accent ? Theme.acc : Theme.inkDim }
                GradientStop { position: 1; color: rail.accent ? Theme.accDeep : Theme.inkDim }
            }
        }
    }
    // the cap: brushed metal, fine vertical grain, a soft shadow under it
    property int capWidth: 9
    readonly property real capCenter: shown * width
    SoftShadow {
        visible: rail.enabled && !rail.bare
        x: cap.x; y: cap.y; width: cap.width; height: cap.height
        radius: cap.radius; blur: 5; dy: 2; color: Qt.rgba(0, 0, 0, Theme.light ? .25 : .45)
    }
    Rectangle {
        visible: rail.enabled && !rail.bare
        x: cap.x; y: cap.y + 1; width: cap.width; height: cap.height; radius: cap.radius
        color: Qt.rgba(0, 0, 0, .5)
    }
    Rectangle {
        id: cap
        visible: rail.enabled && !rail.bare
        width: rail.capWidth; height: rail.grooveHeight + (rail.capWidth > 9 ? 14 : 12); radius: 3
        x: rail.shown * rail.width - width / 2          // centred on the fill's end, as on the concept
        anchors.verticalCenter: parent.verticalCenter
        gradient: Gradient {
            GradientStop { position: 0; color: "#E3E5E8" }
            GradientStop { position: 1; color: "#A9ADB3" }
        }
        Row {
            x: 1; y: 1
            Repeater {
                model: Math.max(0, cap.width - 2)
                Rectangle { width: 1; height: cap.height - 2; color: index % 2 ? Qt.rgba(0, 0, 0, .06) : Qt.rgba(1, 1, 1, .18) }
            }
        }
        Rectangle { x: 2; width: parent.width - 4; y: 0; height: 1; radius: .5; color: "white" }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        anchors.topMargin: -4; anchors.bottomMargin: -4
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        function at(x) { return Math.max(0, Math.min(1, x / rail.width)) }
        onPressed: (m) => { rail.dragValue = rail.pressValue = at(m.x); rail.moved(rail.dragValue) }
        onPositionChanged: (m) => { if (pressed) { rail.dragValue = at(m.x); rail.moved(rail.dragValue) } }
        onReleased: (m) => rail.released(at(m.x))
        onWheel: (w) => w.accepted = false
    }
}
