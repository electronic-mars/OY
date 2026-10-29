import QtQuick
import QtQuick.Controls

// File info as a card over the picture: the file, then each stream, in plain rows.
Popup {
    id: info
    property var sections: []
    anchors.centerIn: Overlay.overlay
    width: 460
    height: Math.min(parent ? parent.height - 120 : 500, body.implicitHeight + head.height + 34)   // padding 2 × 14, the gap under the head 6
    padding: 14
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    // the name at once; ffprobe's rows come from a thread of their own (fileInfoReady)
    onAboutToShow: sections = player.fileInfo()
    Connections {
        target: player
        function onFileInfoReady(path, rows) { if (info.visible && path === player.path) info.sections = rows }
    }
    background: FloatCard {}

    function asText() {
        var out = []
        for (var i = 0; i < sections.length; i++) {
            out.push(sections[i].title)
            for (var j = 0; j < sections[i].rows.length; j++)
                out.push("  " + sections[i].rows[j].k + ": " + sections[i].rows[j].v)
        }
        return out.join("\n")
    }

    contentItem: Item {
        Item {
            id: head
            width: parent.width; height: 26
            Text { anchors.verticalCenter: parent.verticalCenter; text: L.t.info_caps
                   color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2 }
            Text {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: L.t.copy; color: copyArea.containsMouse ? Theme.accText : Theme.tx3
                font.family: Theme.uiFont; font.pixelSize: 11
                MouseArea { id: copyArea; anchors.fill: parent; hoverEnabled: true
                            onClicked: { clip.text = info.asText(); clip.selectAll(); clip.copy(); player.osdMessage(L.t.copied) } }
            }
            TextEdit { id: clip; visible: false }
        }
        Flickable {
            anchors { left: parent.left; right: parent.right; top: head.bottom; topMargin: 6; bottom: parent.bottom }
            contentHeight: body.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: body
                width: parent.width
                spacing: 10
                Repeater {
                    model: info.sections
                    Column {
                        width: body.width
                        spacing: 3
                        Text { text: modelData.title; color: Theme.accText; font.family: Theme.uiFont; font.pixelSize: 12; font.weight: Font.DemiBold }
                        Repeater {
                            model: modelData.rows
                            Row {
                                spacing: 10
                                Text { width: 130; text: modelData.k; color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12 }
                                Text { width: body.width - 140; text: modelData.v; color: Theme.tx; wrapMode: Text.WrapAnywhere
                                       font.family: Theme.uiFont; font.pixelSize: 12 }
                            }
                        }
                    }
                }
            }
        }
    }
}
