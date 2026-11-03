import QtQuick

// A screenshot just saved: its file's name and «Open the folder» (Explorer, the file chosen in
// it), for 3 s; the pointer over it holds it.
FloatCard {
    id: toast
    objectName: "shotToast"
    property string path: ""
    readonly property string fileName: path.substring(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1)
    function show(p) { path = p; opacity = 1; hold.restart() }
    width: Math.min(row.implicitWidth + 24, parent.width - 24)
    height: 44
    opacity: 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 200 } }
    Timer { id: hold; interval: 3000; onTriggered: if (hover.hovered) restart(); else toast.opacity = 0 }
    HoverHandler { id: hover }
    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        x: 12
        spacing: 12
        Icon { anchors.verticalCenter: parent.verticalCenter; name: Theme.icCamera; size: 16; color: Theme.tx2 }
        Text {
            objectName: "shotToastName"
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, toast.parent.width - 24 - 24 - 16 - 24 - openKey.width)
            elide: Text.ElideMiddle
            text: toast.fileName
            color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 13
        }
        PillButton {
            id: openKey
            objectName: "shotToastOpen"
            anchors.verticalCenter: parent.verticalCenter
            text: L.t.open_folder
            onClicked: { app.revealFile(toast.path); toast.opacity = 0 }
        }
    }
}
