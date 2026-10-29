import QtQuick

// A card that floats over the window (menus, settings, the picture's card, the file's info):
// rounded, a soft wide shadow under it instead of a hard dark rim, as the concept's tool card.
Rectangle {
    id: card
    color: Theme.card
    radius: 12
    border.color: Theme.lineHi
    SoftShadow {
        z: -1
        anchors.fill: parent
        radius: card.radius; blur: 14; dy: 6
        color: Qt.rgba(0, 0, 0, Theme.light ? .18 : .45)
    }
}
