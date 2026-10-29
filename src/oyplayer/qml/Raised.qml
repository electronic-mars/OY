import QtQuick

// The raised face of a button with words and of a chosen option: the key cap's soft shadow,
// its dark hairline under the lower edge and its light along the top, both following the
// rounded contour; pressed, it sinks a pixel and loses them.
Item {
    id: r
    property real radius: 8
    property bool accent: false
    property bool hovered: false
    property bool pressed: false
    SoftShadow {
        visible: !r.pressed
        anchors.fill: parent
        radius: r.radius; blur: 5; dy: 2
        color: Qt.rgba(0, 0, 0, Theme.light ? .12 : .25)
    }
    Rectangle {
        visible: !r.pressed
        anchors.fill: parent; anchors.topMargin: 2; anchors.bottomMargin: -2
        radius: r.radius; color: r.accent ? Qt.rgba(0, 0, 0, .4) : Theme.capShadow
    }
    Rectangle {
        visible: !r.pressed
        anchors.fill: parent
        radius: r.radius
        color: r.accent ? Qt.tint(Theme.accTop, Qt.rgba(1, 1, 1, .3)) : Qt.tint(Theme.capTop, Qt.rgba(1, 1, 1, Theme.light ? .9 : .1))
    }
    Rectangle {
        anchors.fill: parent; anchors.topMargin: r.pressed ? 2 : 1; anchors.bottomMargin: r.pressed ? -2 : -1
        radius: r.radius
        gradient: Gradient {
            GradientStop { position: 0; color: r.accent ? (r.hovered ? Theme.accHi : Theme.accTop)
                                                       : r.pressed ? Theme.capDnTop : r.hovered ? Theme.capHiTop : Theme.capTop }
            GradientStop { position: 1; color: r.accent ? (r.pressed ? Theme.accDeep : Theme.acc)
                                                       : r.pressed ? Theme.capDnBot : r.hovered ? Theme.capHiBot : Theme.capBot }
        }
    }
}
