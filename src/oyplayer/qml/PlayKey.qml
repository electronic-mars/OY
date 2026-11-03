import QtQuick
import QtQuick.Shapes

// The play key, the same in every skin (the owner chose it from Gemini's variants): graphite lit
// from behind. A knob (the owner's variant E of 03.11): a graphite bezel, a lit ring in the accent
// in its groove, brightest at the top, and inside it the face of Master Audio Switcher's knob; a
// faint warm halo round it, the sign in the accent. A click plays or pauses, the right
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
    // the sign at the mock's size (19 of 46 px for the bare triangle; the icon's own stroke adds a
    // little, hence .373)
    readonly property real signShift: playing ? 0 : Math.round((width + 2 * grow) * .373) / 24
    width: Theme.keyPlay
    height: Theme.keyPlay

    Accessible.role: Accessible.Button
    Accessible.name: pk.name
    Accessible.onPressAction: pk.clicked()

    // a disc filled from a point (by default its middle, a touch above with `lift`) out to its edge;
    // `cx`, `cy` place that point as a share of the box, `reach` is how far the colours run (in
    // radii), `middle` an optional colour at `mid` of the way
    component Disc: Shape {
        id: disc
        property real radius
        property color inner
        property color outer
        property color middle: "transparent"
        property real mid: -1
        property real lift: 0
        property real cx: .5
        property real cy: .5
        property real reach: 1
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: disc.width * disc.cx; centerY: disc.height * disc.cy - disc.lift
                focalX: centerX; focalY: centerY
                centerRadius: disc.radius * disc.reach
                GradientStop { position: 0; color: disc.inner }
                // without a middle colour this stop sits on the last one and changes nothing
                GradientStop { position: disc.mid >= 0 ? disc.mid : 1; color: disc.mid >= 0 ? disc.middle : disc.outer }
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
            // the face: the inner disc of Master Audio Switcher's knob (its app.css, the owner's
            // variant E of 03.11), lighter up and to the left of the middle, darker to every edge,
            // a hairline of light along its top inside
            Item {
                id: face
                anchors.fill: parent; anchors.margins: 5 * pk.u
                readonly property real r: width / 2
                Disc { radius: face.r; cx: .36; cy: .26; reach: 2.4; mid: .48
                       inner: Theme.light ? (rimArea.containsMouse ? "#F2F0EA" : "#E4E1DA")
                                          : (rimArea.containsMouse ? "#3A4048" : "#33383F")
                       middle: Theme.light ? "#D2CFC7" : "#23272C"
                       outer: Theme.light ? "#BEBAB1" : "#191C20" }
                Shape {
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: "transparent"; strokeWidth: Math.max(1, .6 * pk.u)
                        strokeColor: Qt.rgba(1, 1, 1, Theme.light ? .5 : .13); capStyle: ShapePath.RoundCap
                        PathAngleArc { centerX: face.r; centerY: face.r; radiusX: face.r - .6 * pk.u; radiusY: radiusX
                                       startAngle: 215; sweepAngle: 110 }
                    }
                }
                // what is left of the sign's glow (halved, 03.11): a breath of the accent behind it
                Disc { radius: face.r * .55
                       inner: Theme.accA(rimArea.containsMouse ? .10 : .06)
                       outer: Theme.accA(0) }
            }
            Icon { objectName: "sign"; anchors.centerIn: parent; anchors.horizontalCenterOffset: pk.signShift
                   name: pk.sign; solid: true; size: Math.round(art.width * .373); color: Theme.accText }
        }
    }
    MouseArea { id: rimArea; anchors.fill: art; hoverEnabled: true; acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: (m) => m.button === Qt.RightButton ? pk.rightClicked() : pk.clicked() }
    Tip { text: pk.tip; shown: rimArea.containsMouse && !rimArea.pressed }
}
