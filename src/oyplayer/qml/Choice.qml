import QtQuick

// A choice from a list that may grow long (the language): a field sunk into the body with the
// chosen option's name and a chevron; a click opens the options under it as a menu.
Rectangle {
    id: ch
    property var options: []          // [{ value, text }]
    property var value
    signal picked(var value)
    height: 30
    radius: 7
    color: area.containsMouse || menu.visible ? Theme.card : Theme.sunk
    border.color: menu.visible ? Theme.accA(.6) : Theme.line
    Accessible.role: Accessible.ComboBox
    Accessible.name: current.text
    Accessible.onPressAction: menu.open()

    readonly property var chosen: options.find(o => o.value === value)
    Text {
        id: current
        anchors { left: parent.left; leftMargin: 10; right: chevron.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
        text: ch.chosen ? ch.chosen.text : ""
        elide: Text.ElideRight
        color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 12
    }
    Icon {
        id: chevron
        anchors { right: parent.right; rightMargin: 9; verticalCenter: parent.verticalCenter }
        name: "chevron-down"; size: 14; stroke: 2; color: Theme.tx3
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
            menu.items = ch.options.map(o => ({ text: o.text, checked: o.value === ch.value, run: () => ch.picked(o.value) }))
            menu.open()
        }
    }
    BraunMenu { id: menu; objectName: "choiceMenu"; y: ch.height + 4; rowWidth: ch.width - 10 }
    // the settings closed or turned to another section: the list goes with them
    onVisibleChanged: if (!visible) menu.close()
}
