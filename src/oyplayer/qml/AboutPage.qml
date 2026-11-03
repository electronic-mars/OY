import QtQuick

// About (the settings' last section): what this is, which version, where it keeps its things,
// the update, and the way to the site and to thanking the author. The owner's pick of Argon's
// variants (03.11): a card in a frame of the accent, the play key itself as the program's mark.
Column {
    id: about
    readonly property real availableWidth: width - 2 * padding
    property real padding: 18
    // the project's page; the thanks lead to its support section until there is a page of their own
    readonly property string site: "https://github.com/electronic-mars/OY"
    spacing: 10
    // the site and the thanks, each on its own line as the update is: a sentence, its key
    component LinkRow: Row {
        property alias hint: hintText.text
        property alias keyText: keyButton.text
        property alias keyName: keyButton.objectName
        property alias accent: keyButton.accent
        signal clicked()
        width: about.availableWidth
        spacing: 10
        Text { id: hintText; width: parent.width - keyButton.width - parent.spacing
               anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap; color: Theme.tx2
               font.family: Theme.uiFont; font.pixelSize: 12 }
        PillButton { id: keyButton; anchors.verticalCenter: parent.verticalCenter; onClicked: parent.clicked() }
    }
    Item { width: 1; height: about.padding - about.spacing }
    Column {
        x: about.padding
        width: about.availableWidth
        spacing: 10
        Row {
            spacing: 16
            // the program's mark: the panel's own play key (a click plays, as there)
            PlayKey { objectName: "aboutKey"; grow: 0; width: 52; height: 52
                      anchors.verticalCenter: parent.verticalCenter
                      playing: player.hasFile && !player.paused; name: "OY Player"
                      onClicked: actions.run("play_pause") }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text { text: "OY PLAYER"; color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 20; font.letterSpacing: 5 }
                Text { textFormat: Text.StyledText; color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12
                       text: L.t.about_version.arg("<font color='" + Theme.accText + "'>" + app.version + "</font>") }
            }
        }
        Rectangle { width: about.availableWidth; height: 1; color: Theme.accA(.35) }
        Text { width: about.availableWidth; wrapMode: Text.Wrap; color: Theme.tx2; lineHeight: 1.15
               font.family: Theme.uiFont; font.pixelSize: 12
               text: L.t.about_text }
        Text { width: about.availableWidth; wrapMode: Text.WrapAnywhere; color: Theme.tx3
               font.family: Theme.uiFont; font.pixelSize: 11
               text: L.t.about_home.arg(app.homeDir) }
        Rectangle { width: about.availableWidth; height: 1; color: Theme.accA(.35) }
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
        Rectangle { width: about.availableWidth; height: 1; color: Theme.accA(.35) }
        LinkRow { hint: L.t.about_site_h; keyName: "aboutSite"; keyText: L.t.about_site
                  onClicked: Qt.openUrlExternally(about.site) }
        LinkRow { hint: L.t.about_thanks_h; keyName: "aboutThanks"; keyText: L.t.about_thanks; accent: true
                  onClicked: Qt.openUrlExternally(about.site + "#support") }
    }
    Item { width: 1; height: about.padding - about.spacing }
}
