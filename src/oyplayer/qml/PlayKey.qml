import QtQuick

// The play key, the same in every skin (the owner chose it from Gemini's variants): graphite lit
// from behind — a thin rim in the accent fading downwards, a soft glow round it, the sign in the
// accent. A click plays or pauses, the right button opens a file.
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
    readonly property real signShift: playing ? 0 : 1.5
    width: Theme.keyPlay
    height: Theme.keyPlay

    Accessible.role: Accessible.Button
    Accessible.name: pk.name
    Accessible.onPressAction: pk.clicked()

    SoftShadow { anchors.fill: parent; radius: width / 2; blur: 12; dy: 0; color: Theme.accA(.28) }
    Rectangle {
        anchors.fill: parent; radius: width / 2
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.accHi }
            GradientStop { position: .5; color: Theme.accA(.6) }
            GradientStop { position: 1; color: Theme.accA(.2) }
        }
    }
    Rectangle {
        anchors.fill: parent; anchors.margins: 1.5; radius: width / 2
        scale: rimArea.pressed ? .96 : 1
        gradient: Gradient {
            GradientStop { position: 0; color: rimArea.containsMouse ? Theme.capHiTop : Theme.capTop }
            GradientStop { position: 1; color: Theme.light ? Theme.capBot : "#1B1E24" }
        }
        Icon { objectName: "sign"; anchors.centerIn: parent; anchors.horizontalCenterOffset: pk.signShift
               name: pk.sign; solid: true; size: Math.round(pk.width * .36); color: Theme.accText }
    }
    MouseArea { id: rimArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: (m) => m.button === Qt.RightButton ? pk.rightClicked() : pk.clicked() }
    Tip { text: pk.tip; shown: rimArea.containsMouse && !rimArea.pressed }
}
