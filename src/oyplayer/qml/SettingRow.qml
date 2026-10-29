import QtQuick

// One setting: name, one sentence of explanation, and its control on the right
// (or under the text when `below` — for wide controls, so the text never starves).
Item {
    id: row
    property string title
    property string hint
    property bool below: false
    default property alias control: slot.data
    // a screen reader reads the group's name and explanation with the control inside it
    Accessible.role: Accessible.Grouping
    Accessible.name: row.title
    Accessible.description: row.hint
    width: parent ? parent.width : 400
    height: below ? texts.height + slot.childrenRect.height + 26 : Math.max(texts.height, slot.childrenRect.height) + 22

    Column {
        id: texts
        x: 16; y: 11
        width: row.below ? row.width - 32 : row.width - 32 - slot.childrenRect.width - 16
        spacing: 3
        Text { width: parent.width; text: row.title; color: Theme.tx; wrapMode: Text.Wrap
               font.family: Theme.uiFont; font.pixelSize: 14 }
        Text { width: parent.width; visible: row.hint !== ""; text: row.hint; color: Theme.tx2; wrapMode: Text.Wrap
               font.family: Theme.uiFont; font.pixelSize: 12; lineHeight: 1.1 }
    }
    Item {
        id: slot
        x: row.below ? 16 : row.width - 16 - childrenRect.width
        y: row.below ? texts.y + texts.height + 10 : (row.height - childrenRect.height) / 2
        width: row.below ? row.width - 32 : childrenRect.width
        height: childrenRect.height
    }
    Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 1; rightMargin: 1 }
                height: 1; color: Theme.line }
}
