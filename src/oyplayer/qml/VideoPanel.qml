import QtQuick
import QtQuick.Controls

// Video properties, one card instead of a dialog: colour, proportions, zoom and
// rotation, filters. Every control acts at once; nothing to confirm.
Popup {
    id: vp
    padding: 14
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
    background: FloatCard {}

    component Caption: Text {
        color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2
    }
    component ColorRow: Item {
        property string name
        property string label
        width: 300; height: 26
        Text { anchors.verticalCenter: parent.verticalCenter; text: label; width: 96
               color: Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 12 }
        Rail {
            x: 100; width: 156; height: 16; grooveHeight: 5
            anchors.verticalCenter: parent.verticalCenter
            value: (player[name] + 100) / 200
            onMoved: (v) => player.setColor(name, Math.round(v * 200 - 100))
        }
        Text { anchors { right: parent.right; verticalCenter: parent.verticalCenter }
               text: (player[name] > 0 ? "+" : "") + player[name]
               color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 11 }
    }

    contentItem: Column {
        spacing: 8
        Item {
            width: 300; height: 18
            Caption { text: L.t.color_caps; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: L.t.reset; color: resetArea.containsMouse ? Theme.accText : Theme.tx3
                font.family: Theme.uiFont; font.pixelSize: 11
                MouseArea { id: resetArea; anchors.fill: parent; hoverEnabled: true; onClicked: player.resetColors() }
            }
        }
        ColorRow { name: "brightness"; label: L.t.brightness }
        ColorRow { name: "contrast"; label: L.t.contrast }
        ColorRow { name: "saturation"; label: L.t.saturation }

        Item { width: 1; height: 4 }
        Caption { text: L.t.aspect_caps }
        Segmented {
            objectName: "aspectSeg"
            width: 300
            options: [{ value: "-1", text: L.t.aspect_asis }, { value: "4:3", text: "4:3" },
                      { value: "16:9", text: "16:9" }, { value: "2.35:1", text: "2.35" },
                      { value: "fill", text: L.t.aspect_fill }]
            value: player.aspectMode
            onPicked: (v) => player.setAspect(v)
        }

        Item { width: 1; height: 4 }
        Item {
            width: 300; height: 18
            Caption { text: L.t.zoom_caps; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: L.t.reset; color: geoArea.containsMouse ? Theme.accText : Theme.tx3
                font.family: Theme.uiFont; font.pixelSize: 11
                MouseArea { id: geoArea; anchors.fill: parent; hoverEnabled: true; onClicked: player.resetGeometry() }
            }
        }
        Item {
            width: 300; height: 30
            Rail {
                width: 170; height: 16; grooveHeight: 5
                anchors.verticalCenter: parent.verticalCenter
                value: (player.zoom + 1) / 3                  // log2 −1…2 = 50…400 %
                onMoved: (v) => player.setZoom(v * 3 - 1)
            }
            Text { x: 178; anchors.verticalCenter: parent.verticalCenter
                   text: Math.round(Math.pow(2, player.zoom) * 100) + "%"
                   color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 11 }
            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 5
                KeyCap { glyph: Theme.icRotateLeft; glyphSize: 15; width: 28; height: 26; tip: L.t.rotate_left
                         onClicked: player.rotateBy(270) }
                KeyCap { glyph: Theme.icRotateRight; glyphSize: 15; width: 28; height: 26; tip: L.t.rotate_right
                         onClicked: player.rotateBy(90) }
            }
        }

        Item { width: 1; height: 4 }
        Caption { text: L.t.filters_caps }
        Flow {
            width: 300
            spacing: 6
            Repeater {
                model: [{ id: "sharpen", text: L.t.f_sharpen }, { id: "denoise", text: L.t.f_denoise },
                        { id: "deinterlace", text: L.t.f_deinterlace }, { id: "gray", text: L.t.f_gray },
                        { id: "invert", text: L.t.f_invert }]
                Rectangle {
                    readonly property bool on: modelData.id === "deinterlace" ? player.deinterlace
                                                : player.activeFilters.indexOf(modelData.id) >= 0
                    width: chip.implicitWidth + 22; height: 26; radius: 13
                    color: on ? Theme.panelHi : Theme.sunk
                    border.color: on ? Theme.accA(.45) : Theme.line
                    Text { id: chip; anchors.centerIn: parent; text: modelData.text
                           color: parent.on ? Theme.accText : Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: player.toggleFilter(modelData.id) }
                }
            }
        }
    }
}
