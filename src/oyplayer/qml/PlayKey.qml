import QtQuick
import QtQuick.Shapes

// The play key, the same in every skin (the owner chose it from Gemini's variants): graphite lit
// from behind. A knob (the owner's variant C2 of 02.11): a graphite bezel, a lit ring in the accent
// in its groove, brightest at the top, and a dome inside it, lighter in the middle and darker at
// the edge; a faint warm halo round it, the sign in the accent. A click plays or pauses, the right
// button opens a file.
Item {
    id: pk
    property bool playing: false
    property string tip: ""
    property string name: ""
    readonly property bool second: true        // the right button opens a file (the hint says so)
    readonly property bool flat: false         // a cap, never a printed sign
    signal clicked()
    signal rightClicked()

    readonly property string sign: playing ? Theme.icPause : Theme.icPlay
    // the triangle stands by its weight, as the owner's sample does (02.11): its box's middle 13%
    // of its width right of the key's; the icon already draws it 1/24 of its size right
    readonly property real signShift: playing ? 0 : Math.round((width + 2 * grow) * .36) / 24
    width: Theme.keyPlay
    height: Theme.keyPlay

    Accessible.role: Accessible.Button
    Accessible.name: pk.name
    Accessible.onPressAction: pk.clicked()

    // a disc filled from the middle (a touch above it, where the light falls) to the edge
    component Disc: Shape {
        id: disc
        property real radius
        property color inner
        property color outer
        property real lift: 0
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: disc.width / 2; centerY: disc.height / 2 - disc.lift
                focalX: centerX; focalY: centerY
                centerRadius: disc.radius
                GradientStop { position: 0; color: disc.inner }
                GradientStop { position: 1; color: disc.outer }
            }
            PathAngleArc { centerX: disc.width / 2; centerY: disc.height / 2
                           radiusX: disc.radius; radiusY: disc.radius; startAngle: 0; sweepAngle: 360 }
        }
    }
    // the knob is drawn this much past its place on every side: it fills the ring the panel's
    // well had round it, which read as an outline (the owner, 02.11); the lamp in Settings keeps 0
    property real grow: 4
    readonly property real u: art.width / 46       // the mock's pixel (C2, 02.11), drawn at 46
    Item {
        id: art
        anchors.fill: parent; anchors.margins: -pk.grow
        // a faint warm halo round the key, and its own dark shadow under it
        SoftShadow { anchors.fill: parent; radius: width / 2; blur: 12; dy: 0; color: Theme.accA(.14) }
        SoftShadow { anchors.fill: parent; radius: width / 2; blur: 5; dy: 2 * pk.u; color: Qt.rgba(0, 0, 0, Theme.light ? .18 : .45) }
        Item {
            id: knob
            anchors.fill: parent
            scale: rimArea.pressed ? .96 : 1
            // the bezel: graphite lit from above
            Rectangle {
                anchors.fill: parent; radius: width / 2
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.light ? Theme.capTop : "#3A3E45" }
                    GradientStop { position: 1; color: Theme.light ? Theme.capBot : "#17191D" }
                }
            }
            // the lit ring in the bezel's groove, brightest at the top
            Item {
                anchors.fill: parent; anchors.margins: 3.5 * pk.u
                SoftShadow { anchors.fill: parent; radius: width / 2; blur: 4; dy: 0; color: Theme.accA(.30) }
                Rectangle {
                    anchors.fill: parent; radius: width / 2
                    gradient: Gradient {
                        GradientStop { position: 0; color: Theme.accHi }
                        GradientStop { position: .5; color: Theme.accA(.7) }
                        GradientStop { position: 1; color: Theme.accA(.35) }
                    }
                }
            }
            // the face: a dome, lighter where the light falls, darker at its edge
            Item {
                id: face
                anchors.fill: parent; anchors.margins: 5 * pk.u
                readonly property real r: width / 2
                Disc { radius: face.r; lift: face.r * .24
                       inner: Theme.light ? (rimArea.containsMouse ? "#FFFFFF" : Theme.capTop)
                                          : (rimArea.containsMouse ? "#4D525B" : "#444850")
                       outer: Theme.light ? Theme.capBot : "#141619" }
                // the barest glow behind the sign
                Disc { radius: face.r * .6
                       inner: Theme.accA(rimArea.containsMouse ? .09 : .05)
                       outer: Theme.accA(0) }
            }
            Icon { objectName: "sign"; anchors.centerIn: parent; anchors.horizontalCenterOffset: pk.signShift
                   name: pk.sign; solid: true; size: Math.round(art.width * .36); color: Theme.accText }
        }
    }
    MouseArea { id: rimArea; anchors.fill: art; hoverEnabled: true; acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: (m) => m.button === Qt.RightButton ? pk.rightClicked() : pk.clicked() }
    Tip { text: pk.tip; shown: rimArea.containsMouse && !rimArea.pressed }
}
