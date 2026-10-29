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
        Rectangle { width: about.availableWidth; height: 1; color: Theme.rule }
        // the update (updater.py): a sentence on the left, the one thing to press on the right
        Row {
            width: about.availableWidth
            spacing: 10
            Text {
                objectName: "updateText"
                width: parent.width - (updateKey.visible ? updateKey.width + parent.spacing : 0)
                anchors.verticalCenter: parent.verticalCenter
                wrapMode: Text.Wrap; color: Theme.tx2
                font.family: Theme.uiFont; font.pixelSize: 12
                text: {
                    const d = updater.detail
                    switch (updater.state) {
                    case "checking": return L.t.up_checking
                    case "current": return L.t.up_current
                    case "available": return L.t.up_available.arg(updater.offered)
                    case "downloading": return L.t.up_downloading.arg(updater.percent)
                    case "verifying": return L.t.up_verifying
                    case "installing": return L.t.up_installing
                    case "failed":
                        if (d === "network") return L.t.up_f_network
                        if (d === "signature") return L.t.up_f_signature
                        if (d === "release") return L.t.up_f_release
                        if (d === "busy") return L.t.up_f_busy
                        if (d.startsWith("http ")) return L.t.up_f_http.arg(d.slice(5))
                        return L.t.up_f_other.arg(d)
                    }
                    return L.t.up_idle
                }
            }
            PillButton {
                id: updateKey
                objectName: "updateKey"
                anchors.verticalCenter: parent.verticalCenter
                visible: ["idle", "current", "available", "failed"].includes(updater.state)
                accent: updater.state === "available"
                text: updater.state === "available" ? L.t.up_install
                    : updater.state === "failed" ? L.t.up_retry : L.t.up_check
                // after a found version a retry is the install again, otherwise the look again
                onClicked: updater.state === "available" || updater.state === "failed" && updater.offered !== ""
                           ? updater.install() : updater.check()
            }
        }
        Rectangle {     // how far the download is
            visible: updater.state === "downloading"
            width: about.availableWidth; height: 3; radius: 1.5; color: Theme.groove
            Rectangle { width: parent.width * updater.percent / 100; height: parent.height; radius: 1.5; color: Theme.acc }
        }
    }
}
