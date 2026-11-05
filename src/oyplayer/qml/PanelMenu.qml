import QtQuick
import QtQuick.Controls

// The menu a key opens on right click, and the picture's own. The rows are the panel's size, not
// a system menu's: a sign on the left (or the tick of the chosen option), the words, the key that
// does the same on the right in a small sunk key; the row under the pointer framed in the accent
// (the owner's pick of Argon's variants, 03.11). With `wells` every row sits in its own sunk well
// and the chosen one is framed too (the scheduler's); `lcd` puts a time on the LCD's glass instead
// of the keys.
// items: [{ text, icon?, keys?, lcd?, checked?, enabled?, run(), header?, separator?, keepOpen? }]
Popup {
    id: menu
    property var items: []
    property int current: -1        // the highlighted row: under the pointer, or moved to by the keys
    padding: 6
    property int rowWidth: 280
    // a language's longer words widen the menu rather than lose their ends
    readonly property int fitWidth: Math.min(440, items.reduce((w, it) => it.text && !it.header && !it.separator
        ? Math.max(w, Math.ceil(rowFont.advanceWidth(it.text) + 38 + 26
                                + (it.keys ? keyFont.advanceWidth(it.keys) + 20 : it.lcd ? 56 : 0))) : w, rowWidth))
    FontMetrics { id: rowFont; font.family: Theme.uiFont; font.pixelSize: menu.wells ? 12 : 13 }
    FontMetrics { id: keyFont; font.family: Theme.monoFont; font.pixelSize: 11 }
    property bool wells: false
    property real maxHeight: 0      // a long list (the languages) scrolls past this height; 0: none
    // opened, a list that scrolls shows its chosen row
    onOpened: {
        current = -1
        column.forceLayout()                 // the rows made a moment ago have no places yet
        var i = items.findIndex(it => it.checked === true), h = flick.implicitHeight   // laid out yet or not
        flick.contentY = i < 0 || flick.contentHeight <= h + 1 ? 0
            : Math.max(0, Math.min(rows.itemAt(i).y - (h - rows.itemAt(i).height) / 2, flick.contentHeight - h))
    }
    // the keys move the highlight past the edge of a scrolled list: the list follows
    onCurrentChanged: {
        var it = current < 0 ? null : rows.itemAt(current)
        if (!it || !flick.interactive) return
        if (it.y < flick.contentY) flick.contentY = it.y
        else if (it.y + it.height > flick.contentY + flick.height) flick.contentY = it.y + it.height - flick.height
    }

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
    contentItem: Flickable {
        id: flick
        implicitWidth: menu.fitWidth
        implicitHeight: menu.maxHeight > 0 ? Math.min(column.implicitHeight, menu.maxHeight) : column.implicitHeight
        contentWidth: menu.fitWidth; contentHeight: column.implicitHeight
        interactive: contentHeight > height + 1
        clip: interactive
        boundsBehavior: Flickable.StopAtBounds
        ScrollIndicator.vertical: ScrollIndicator {}
        Column {
            id: column
            width: menu.fitWidth
            spacing: menu.wells ? 3 : 0
            Repeater {
                id: rows
                model: menu.items
                delegate: Item {
                    width: menu.fitWidth
                    height: modelData.separator ? 11 : (modelData.header ? 26 : menu.wells ? 30 : 34)
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
                        anchors.left: parent.left; anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 2
                        text: modelData.header || ""
                        color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10; font.letterSpacing: 2 * Theme.track
                    }
                    Rectangle {
                        visible: !modelData.separator && !modelData.header
                        anchors.fill: parent
                        id: rowBg
                        readonly property bool hot: index === menu.current && itemArea.enabled
                        readonly property bool framed: hot || menu.wells && modelData.checked === true
                        radius: 8
                        color: hot ? Theme.panelHi : menu.wells ? Theme.sunk : "transparent"
                        border.color: framed ? Theme.accA(.75) : menu.wells ? Theme.line : "transparent"
                        // the sign: the option's own, or a tick for the chosen one
                        Icon {
                            visible: modelData.checked === true || !!modelData.icon
                            anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                            name: modelData.checked === true ? "check" : (modelData.icon || "")
                            size: 16; stroke: modelData.checked === true ? 2.2 : 1.5
                            color: modelData.checked === true || rowBg.hot ? Theme.accText : Theme.tx2
                            opacity: modelData.enabled === false ? .4 : 1
                        }
                        Text {
                            id: rowText
                            anchors.left: parent.left; anchors.leftMargin: 38
                            width: parent.width - 38 - (keysCap.visible ? keysCap.width : lcdGlass.visible ? lcdGlass.width : 0) - 24
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.text || ""
                            elide: Text.ElideRight
                            color: modelData.enabled === false ? Theme.tx3 : Theme.tx
                            opacity: modelData.enabled === false ? .5 : 1
                            font.family: Theme.uiFont; font.pixelSize: menu.wells ? 12 : 13
                        }
                        // the key that does the same, on a small sunk cap
                        Rectangle {
                            id: keysCap
                            objectName: visible ? "menuKeys" : ""
                            visible: !!modelData.keys
                            anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                            width: keysText.implicitWidth + 12; height: 22; radius: 5
                            color: Theme.sunk; border.color: Theme.line
                            opacity: modelData.enabled === false ? .5 : 1
                            Text { id: keysText; anchors.centerIn: parent; text: modelData.keys || ""
                                   color: rowBg.hot ? Theme.tx2 : Theme.tx3; font.family: Theme.monoFont; font.pixelSize: 11 }
                        }
                        // a time on the panel's LCD glass
                        Rectangle {
                            id: lcdGlass
                            visible: !!modelData.lcd
                            anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                            width: lcdFigures.width + 10; height: 20; radius: 4
                            border.color: Theme.lcdBezel
                            gradient: Gradient {
                                GradientStop { position: 0; color: Theme.lcdHi }
                                GradientStop { position: .5; color: Theme.lcd }
                                GradientStop { position: 1; color: Theme.lcdLo }
                            }
                            LcdTime.Segments { id: lcdFigures; anchors.centerIn: parent; h: 11; text: modelData.lcd || "" }
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
}
