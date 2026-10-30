import QtQuick
import QtQuick.Controls

// The menu a key opens on right click, and the picture's own. The rows are the panel's size, not
// a system menu's: a sign on the left (or the tick of the chosen option), the words, the key that
// does the same on the right; the row under the pointer a raised cap edge in the accent.
// items: [{ text, icon?, keys?, checked?, enabled?, run(), header?, separator?, keepOpen? }]
Popup {
    id: menu
    property var items: []
    property int current: -1        // the highlighted row: under the pointer, or moved to by the keys
    padding: 6
    property int rowWidth: 280
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
        width: menu.rowWidth
        Repeater {
            model: menu.items
            delegate: Item {
                width: menu.rowWidth
                height: modelData.separator ? 11 : (modelData.header ? 28 : 34)
                Accessible.role: modelData.separator ? Accessible.Separator : modelData.header ? Accessible.StaticText : Accessible.MenuItem
                Accessible.name: modelData.text || ""
                Accessible.checkable: modelData.checked !== undefined
                Accessible.checked: !!modelData.checked
                Rectangle {
                    visible: !!modelData.separator
                    anchors.centerIn: parent; width: parent.width - 20; height: 1; color: Theme.line
                }
                Text {
                    visible: !!modelData.header
                    x: 12; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 2
                    text: modelData.header || ""
                    color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10; font.letterSpacing: 2
                }
                Rectangle {
                    visible: !modelData.separator && !modelData.header
                    anchors.fill: parent
                    id: rowBg
                    readonly property bool hot: index === menu.current && itemArea.enabled
                    radius: 8
                    color: hot ? Theme.panelHi : "transparent"
                    border.color: hot ? Theme.lineHi : "transparent"
                    // the sign: the option's own, or a tick for the chosen one
                    Icon {
                        visible: modelData.checked === true || !!modelData.icon
                        x: 12; anchors.verticalCenter: parent.verticalCenter
                        name: modelData.checked === true ? "check" : (modelData.icon || "")
                        size: 16; stroke: modelData.checked === true ? 2.2 : 1.5
                        color: modelData.checked === true || rowBg.hot ? Theme.accText : Theme.tx2
                        opacity: modelData.enabled === false ? .4 : 1
                    }
                    Text {
                        id: rowText
                        x: 38; width: parent.width - x - keysText.implicitWidth - 24
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.text || ""
                        elide: Text.ElideRight
                        color: modelData.enabled === false ? Theme.tx3 : Theme.tx
                        opacity: modelData.enabled === false ? .5 : 1
                        font.family: Theme.uiFont; font.pixelSize: 13
                    }
                    Text {
                        id: keysText
                        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                        text: modelData.keys || ""
                        color: Theme.tx3; opacity: modelData.enabled === false ? .5 : 1
                        font.family: Theme.monoFont; font.pixelSize: 11
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
