import QtQuick

// − value + : for small whole numbers (seconds, percent).
Row {
    id: st
    property int value: 0
    property int step: 1
    property int from: 0
    property int to: 100
    property string suffix: ""
    signal changedTo(int v)
    spacing: 4
    KeyCap { glyph: Theme.icRemove; glyphSize: 15; width: 28; height: 26; name: L.t.less.arg(st.value + st.suffix); enabled: st.value > st.from; opacity: enabled ? 1 : .35
             onClicked: st.changedTo(Math.max(st.from, st.value - st.step)) }
    Rectangle {
        width: 64; height: 26; radius: 6; color: Theme.sunk; border.color: Theme.line
        Text { anchors.centerIn: parent; text: st.value + st.suffix; color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 12 }
    }
    KeyCap { glyph: Theme.icAdd; glyphSize: 15; width: 28; height: 26; name: L.t.more.arg(st.value + st.suffix); enabled: st.value < st.to; opacity: enabled ? 1 : .35
             onClicked: st.changedTo(Math.min(st.to, st.value + st.step)) }
}
