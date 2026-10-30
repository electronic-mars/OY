import QtQuick

// A rubber key cap: light along its top, a soft shadow under it; travels down 1px when pressed.
// `latched` keys stand as the others with their sign in the accent (subtitles on, sound off…).
// `accent` is the one coloured key on the panel, as on a Braun calculator.
// The sign is a Lucide icon by name (icons.py), drawn for the screen's own pixels.
Item {
    id: key
    property string glyph: ""          // the icon's name: "play", "captions"…
    property string label: ""          // a letter printed on the cap (the editor's I and O)
    property string caption: ""        // words beside the sign: a wide key (the editor's Save, Cancel)
    property bool solid: false         // a filled figure (play, pause)
    property real glyphShift: 0        // to the optical centre: a triangle looks left of centre
    property bool latched: false
    property bool round: false
    property bool accent: false
    property string tip: ""
    property int glyphSize: round ? Theme.keyIconRound : Theme.keyIcon
    property string name: ""            // what a screen reader calls it, when the hint does not say
    // a sign printed on the body, without a cap (the settings' small keys keep their caps)
    property bool flat: false
    property bool second: false         // a second action on the right button (its hint says so)
    property bool held: false           // its menu is open: the key stays pressed in
    property bool chosen: false         // the tool in use (drawing): pressed in, its sign in the accent
    signal clicked()
    signal rightClicked()

    // For a screen reader: a button named by its hint without the key in brackets
    // ("Play (Space)" is read «Play»), pressed in when latched.
    Accessible.role: Accessible.Button
    Accessible.name: key.name || key.tip.replace(/\s*\([^)]*\)/g, "").trim() || key.label
    Accessible.checkable: key.latched
    Accessible.checked: key.latched
    Accessible.onPressAction: if (key.enabled) key.clicked()

    width: caption !== "" ? captionRow.implicitWidth + 28 : round ? Theme.keyRound : Theme.keyW
    height: round ? Theme.keyRound : Theme.keyH
    opacity: enabled ? 1 : .35          // off: a key with nothing to act on (no file, nothing chosen)

    readonly property bool down: area.pressed || held || chosen
    // one colour, one meaning: the accent is the play key and the position; a key that is on
    // (latched) or the tool in use (chosen) shows its sign in the accent, no lamp beside it
    readonly property color ink: accent ? Theme.inkOnAcc : chosen || latched ? Theme.accText : Theme.glyph

    readonly property real r: round ? width / 2 : Theme.keyRadius
    readonly property bool raised: !flat && !down
    // As the concept's CSS: a soft shadow (0 3px 6px; the play key 0 4px 10px), a dark hairline
    // under the lower edge, a light one along the top inside the contour. The light is a lighter
    // copy of the cap's shape in the key's own place with the cap a pixel lower over it, so it
    // follows the rim and thins out round the corners instead of standing as a straight stripe;
    // the dark hairline is a copy a pixel under the cap.
    SoftShadow {
        visible: key.raised
        anchors.fill: parent
        radius: key.r
        blur: key.accent ? 10 : 6
        dy: key.accent ? 4 : 3
        color: Qt.rgba(0, 0, 0, key.accent ? .3 : .22)
    }
    Rectangle {
        visible: key.raised
        anchors.fill: parent; anchors.topMargin: key.accent ? 3 : 2; anchors.bottomMargin: key.accent ? -3 : -2
        radius: key.r
        color: key.accent ? Qt.rgba(0, 0, 0, .45) : Theme.capShadow
    }
    Rectangle {
        visible: key.raised
        anchors.fill: parent
        radius: key.r
        color: key.accent ? Qt.tint(Theme.accTop, Qt.rgba(1, 1, 1, .3)) : Qt.tint(Theme.capTop, Qt.rgba(1, 1, 1, Theme.light ? .9 : .1))
    }
    // pressed in: the cap sinks into a dark well of its own outline, so the key keeps its whole
    // shape (a cap moved down over nothing read as a key cut off along its top)
    Rectangle {
        visible: key.down && !key.flat
        anchors.fill: parent; anchors.bottomMargin: -1
        radius: key.r
        color: key.accent ? Qt.rgba(0, 0, 0, .45) : Theme.capShadow
    }
    Rectangle {
        id: cap
        anchors.fill: parent
        anchors.topMargin: key.flat ? 0 : key.down ? 2 : 1
        anchors.bottomMargin: key.flat ? 0 : -1
        radius: key.r
        border.width: key.flat ? 1 : 0
        border.color: area.containsMouse || area.pressed || key.held ? Theme.line : "transparent"
        // a printed sign has no cap: a card shows under the pointer, a sunk one while pressed
        color: !key.flat ? "transparent" : area.pressed || key.held ? Theme.sunk
               : area.containsMouse ? Theme.card : "transparent"
        gradient: key.flat ? undefined : capGradient
        Gradient {
            id: capGradient
            GradientStop { position: 0; color: key.accent ? (area.containsMouse ? Theme.accHi : Theme.accTop)
                                                  : key.down ? Theme.capDnTop
                                                  : area.containsMouse ? Theme.capHiTop : Theme.capTop }
            GradientStop { position: key.accent ? .55 : 1; color: key.accent ? (key.down ? Theme.accDeep : Theme.acc)
                                                  : key.down ? Theme.capDnBot
                                                  : area.containsMouse ? Theme.capHiBot : Theme.capBot }
            GradientStop { position: 1; color: key.accent ? Theme.accDeep
                                                  : key.down ? Theme.capDnBot
                                                  : area.containsMouse ? Theme.capHiBot : Theme.capBot }
        }
        Row {
            id: captionRow
            visible: key.caption !== ""
            anchors.centerIn: parent
            spacing: 8
            Icon { visible: key.glyph !== ""; anchors.verticalCenter: parent.verticalCenter
                   name: key.glyph; size: 16; color: key.flat ? Theme.tx2 : key.ink }
            Text { anchors.verticalCenter: parent.verticalCenter; text: key.caption
                   color: key.flat ? (area.containsMouse ? Theme.tx : Theme.inkDim) : key.ink
                   font.family: Theme.uiFont; font.pixelSize: 13; font.weight: key.flat ? Font.Medium : Font.DemiBold }
        }
        Icon {
            objectName: "sign"
            visible: key.glyph !== "" && key.caption === ""
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: key.glyphShift
            name: key.glyph
            solid: key.solid
            size: key.glyphSize
            color: key.ink
        }
        Text {
            visible: key.label !== ""
            anchors.centerIn: parent
            text: key.label
            font.family: Theme.uiFont; font.pixelSize: 13; font.weight: Font.DemiBold
            color: key.ink
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: (m) => m.button === Qt.RightButton ? key.rightClicked() : key.clicked()
    }
    // hidden while pressed: a press may open a menu, and the hint must not stay over it
    Tip { text: key.tip; shown: area.containsMouse && !area.pressed && key.tip !== "" }
}
