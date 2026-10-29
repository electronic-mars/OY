import QtQuick
import QtQuick.Controls

// The menu a key opens on right click.
// items: [{ text, checked?, enabled?, run(), header?, separator? }]
Popup {
    id: menu
    property var items: []
    property int current: -1        // the highlighted row: under the pointer, or moved to by the keys
    padding: 5
    onOpened: current = -1

    // ↑ ↓ Home End move the highlight past headers, separators and items that are off; Enter
    // runs the highlighted item (the window's key filter hands these keys to an open menu)
    function navigate(k) {
        var rows = []
        for (var i = 0; i < items.length; i++)
            if (!items[i].header && !items[i].separator && items[i].enabled !== false) rows.push(i)
        if (!rows.length) return
        var at = rows.indexOf(current)
        if (k === "down") current = rows[at < 0 ? 0 : Math.min(rows.length - 1, at + 1)]
        else if (k === "up") current = rows[at < 0 ? rows.length - 1 : Math.max(0, at - 1)]
        else if (k === "home") current = rows[0]
        else if (k === "end") current = rows[rows.length - 1]
        else if (k === "enter" && at >= 0) run(items[current])
    }
    function run(it) { var f = it.run; if (!it.keepOpen) close(); if (f) f() }
    modal: false
    focus: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: FloatCard {}
    contentItem: Column {
        width: 250
        Repeater {
            model: menu.items
            delegate: Item {
                width: 250
                height: modelData.separator ? 9 : (modelData.header ? 24 : 28)
                Accessible.role: modelData.separator ? Accessible.Separator : modelData.header ? Accessible.StaticText : Accessible.MenuItem
                Accessible.name: modelData.text || ""
                Accessible.checkable: modelData.checked !== undefined
                Accessible.checked: !!modelData.checked
                Rectangle {
                    visible: !!modelData.separator
                    anchors.centerIn: parent; width: parent.width - 16; height: 1; color: Theme.line
                }
                Text {
                    visible: !!modelData.header
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    text: modelData.header || ""
                    color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2
                }
                Rectangle {
                    visible: !modelData.separator && !modelData.header
                    anchors.fill: parent
                    radius: 6
                    color: index === menu.current && itemArea.enabled ? Theme.panelHi : "transparent"
                    Rectangle {   // LED dot for the chosen option
                        visible: modelData.checked === true
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: 6; height: 6; radius: 3; color: Theme.acc
                    }
                    Text {
                        x: 24; width: parent.width - 32
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.text || ""
                        elide: Text.ElideRight
                        color: modelData.enabled === false ? Theme.tx3 : Theme.tx
                        opacity: modelData.enabled === false ? .5 : 1
                        font.family: Theme.uiFont; font.pixelSize: 12
                    }
                    MouseArea {
                        id: itemArea
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: modelData.enabled !== false
                        onContainsMouseChanged: menu.current = containsMouse ? index : (menu.current === index ? -1 : menu.current)
                        onClicked: menu.run(modelData)
                    }
                }
            }
        }
    }
}
