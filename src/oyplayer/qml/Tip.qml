import QtQuick
import QtQuick.Controls

// Hover hint for the item it is declared in, after a short delay so passing the mouse over
// a row of keys does not flash a hint per key. It is shown on the window's overlay, so no
// clipping parent cuts it: above its item, or under it when there is no room above (the
// title bar), and always whole inside the window. Being on the overlay it would also lie over
// an open menu or card, so while one is open (Main's popupOpen) only the keys inside it show
// their hints.
Rectangle {
    id: tip
    objectName: "tip"
    property alias text: label.text
    property bool shown: false
    property bool under: false          // under the item when there is room (title bar keys)
    property Item owner: null           // the item it belongs to
    visible: opacity > 0
    Accessible.ignored: true            // the item it belongs to carries the same words as its name
    opacity: 0
    z: 1000
    color: Theme.card
    border.color: Theme.lineHi
    radius: 6
    width: label.width + 16
    height: label.implicitHeight + 8

    Component.onCompleted: owner = parent
    // where it goes; false when it must stay hidden (a menu or card is open over its key)
    function place() {
        if (!owner || !Overlay.overlay) return false
        if (parent !== Overlay.overlay) parent = Overlay.overlay
        var home = owner                    // the open popup the key belongs to, if any
        while (home && home.parent !== parent) home = home.parent
        // the window's one sign for «a menu or card is open» (Esc and fullscreen use it too)
        if (!home && Window.window && Window.window.popupOpen) return false
        var p = owner.mapToItem(parent, 0, 0), m = 4
        var above = p.y - height - 6, below = p.y + owner.height + 6
        var fitsBelow = below + height <= parent.height - m
        y = (under || above < m) && fitsBelow ? below : Math.max(m, above)
        x = Math.max(m, Math.min(parent.width - m - width, p.x + (owner.width - width) / 2))
        return true
    }
    onWidthChanged: if (opacity > 0 && !place()) opacity = 0

    TextMetrics { id: line; font: label.font; text: label.text }
    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(Math.ceil(line.advanceWidth) + 1, 420)    // a long hint wraps
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        color: Theme.tx
        font.family: Theme.uiFont
        font.pixelSize: 12
    }
    Timer { id: delay; interval: 500; onTriggered: if (tip.place()) tip.opacity = 1 }
    onShownChanged: { if (shown) delay.restart(); else { delay.stop(); opacity = 0 } }
    Behavior on opacity { NumberAnimation { duration: 120 } }
}
