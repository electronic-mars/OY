import QtQuick

// A text field sunk into the body; commits on Enter or when it loses focus.
Rectangle {
    id: f
    property alias text: input.text
    property bool multiline: false
    property string placeholder: ""
    signal committed(string text)
    height: multiline ? 96 : 30
    radius: 7
    color: Theme.sunk
    border.color: input.activeFocus ? Theme.accA(.6) : Theme.line
    clip: true
    TextEdit {
        id: input
        anchors.fill: parent
        anchors.margins: 8
        color: Theme.tx
        font.family: f.multiline ? "Consolas" : Theme.uiFont
        font.pixelSize: 12
        wrapMode: TextEdit.Wrap
        selectByMouse: true
        selectionColor: Theme.acc
        Keys.onReturnPressed: (e) => { if (f.multiline) e.accepted = false; else { f.committed(text); focus = false } }
        onActiveFocusChanged: if (!activeFocus) f.committed(text)
    }
    Text {
        visible: input.text === "" && !input.activeFocus
        anchors.fill: parent; anchors.margins: 8
        text: f.placeholder; color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12
    }
}
