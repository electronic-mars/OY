import QtQuick
import QtQuick.Controls

// About (the title bar's first button): what this is, which version, where it keeps its things.
Popup {
    id: about
    anchors.centerIn: Overlay.overlay
    width: 380
    padding: 18
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: FloatCard {}
    contentItem: Column {
        spacing: 8
        Row {
            spacing: 12
            Rectangle {   // the program's mark: the round orange key
                width: 34; height: 34; radius: 17; color: Theme.acc
                Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: 1; name: Theme.icPlay; solid: true
                       size: 15; color: Theme.inkOnAcc }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "OY PLAYER"; color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 15; font.letterSpacing: 4 }
                Text { text: L.t.about_version.arg(app.version); color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 11 }
            }
        }
        Text { width: about.availableWidth; wrapMode: Text.Wrap; color: Theme.tx2; lineHeight: 1.15
               font.family: Theme.uiFont; font.pixelSize: 12
               text: L.t.about_text }
        Text { width: about.availableWidth; wrapMode: Text.WrapAnywhere; color: Theme.tx3
               font.family: Theme.uiFont; font.pixelSize: 11
               text: L.t.about_home.arg(app.homeDir) }
    }
}
