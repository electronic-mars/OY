import QtQuick

// The last run went down (crash.py): said once, calmly, over the foot of the picture. What a
// report would carry is shown as it is; Report opens GitHub's form filled with it, the log
// folder is there to attach the logs. It stays until it is closed or the report is made.
FloatCard {
    id: card
    objectName: "crashCard"
    visible: app.crashLine !== ""
    width: Math.min(460, parent.width - 24)
    height: col.implicitHeight + 28
    Accessible.role: Accessible.AlertMessage
    Accessible.name: L.t.crash_title
    Column {
        id: col
        x: 16; y: 14
        width: parent.width - 32
        spacing: 6
        Text { objectName: "crashTitle"; width: parent.width - closeKey.width - 8; wrapMode: Text.Wrap
               text: L.t.crash_title; color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 13 }
        Text { width: parent.width; wrapMode: Text.Wrap; text: L.t.crash_text; color: Theme.tx2
               font.family: Theme.uiFont; font.pixelSize: 12 }
        Text { objectName: "crashLine"; width: parent.width; wrapMode: Text.WrapAnywhere; text: app.crashLine
               color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 11 }
        Item { width: 1; height: 4 }
        Flow {
            width: parent.width
            spacing: 8
            layoutDirection: Qt.RightToLeft
            PillButton { objectName: "crashReport"; text: L.t.crash_report; accent: true
                         onClicked: { app.openLink(app.crashUrl); app.crashLine = "" } }
            PillButton { objectName: "crashFolder"; text: L.t.crash_folder; onClicked: app.openHome() }
        }
    }
    IconButton {
        id: closeKey
        objectName: "crashClose"
        anchors { right: parent.right; rightMargin: 8; top: parent.top; topMargin: 8 }
        glyph: Theme.icClose
        tip: L.t.crash_close
        onClicked: app.crashLine = ""
    }
}
