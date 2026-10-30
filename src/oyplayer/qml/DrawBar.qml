import QtQuick

// The editor's drawing tools, a card in the picture's upper left corner (the Braun concept):
// pick and move, pencil, rectangle, arrow, text, a logo; four inks (a logo chosen: its opacity);
// the turn and the frame; undo, redo; delete the chosen drawing. The tool in use is pressed in,
// its sign in the accent.
Rectangle {
    id: bar
    property string tool: "select"
    property color ink: "#F26A21"
    signal toolPicked(string tool)
    signal inkPicked(color ink)
    signal imageRequested()
    readonly property var chosen: editor.noteSel >= 0 && editor.noteSel < editor.notes.length ? editor.notes[editor.noteSel] : null
    readonly property bool logo: chosen !== null && chosen.kind === "image"

    readonly property bool full: Theme.tier === 2
    width: row.width + (full ? 12 : 10)
    height: full ? 44 : 36
    radius: 12
    color: Qt.rgba(Theme.bg.r, Theme.bg.g, Theme.bg.b, .92)
    border.color: Theme.lineHi
    // a close shadow: the card lies over the picture, a wide one would grey what is drawn under it
    SoftShadow { z: -1; anchors.fill: parent; radius: bar.radius; blur: 6; dy: 2; color: Qt.rgba(0, 0, 0, .35) }

    component Key: KeyCap { width: bar.full ? 34 : 30; height: bar.full ? 32 : 28; glyphSize: 16
                            anchors.verticalCenter: parent.verticalCenter }
    component Sep: Rectangle { width: 1; height: 20; color: Theme.rule; anchors.verticalCenter: parent.verticalCenter }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: bar.full ? 6 : 5
        Key { objectName: "drawSelect"; glyph: Theme.icSelect; chosen: bar.tool === "select"
              tip: L.t.draw_select; onClicked: bar.toolPicked("select") }
        Key { objectName: "drawPen"; glyph: Theme.icPen; chosen: bar.tool === "pen"
              tip: L.t.draw_pen; onClicked: bar.toolPicked("pen") }
        Key { objectName: "drawRect"; glyph: Theme.icRect; chosen: bar.tool === "rect"
              tip: L.t.draw_rect; onClicked: bar.toolPicked("rect") }
        Key { objectName: "drawArrow"; glyph: Theme.icArrow; chosen: bar.tool === "arrow"
              tip: L.t.draw_arrow; onClicked: bar.toolPicked("arrow") }
        Key { objectName: "drawText"; glyph: Theme.icText; chosen: bar.tool === "text"
              tip: L.t.draw_text; onClicked: bar.toolPicked("text") }
        Key { objectName: "drawImage"; glyph: "image-plus"; tip: L.t.draw_image; onClicked: bar.imageRequested() }
        Sep {}
        // a logo chosen: how much it shows through, in place of the inks
        Repeater {
            model: bar.logo ? [1.0, 0.6, 0.3] : []
            Rectangle {
                objectName: "opacity" + index
                anchors.verticalCenter: parent.verticalCenter
                width: 22; height: 22; radius: 11
                color: "transparent"
                border.color: Math.abs(bar.chosen.opacity - modelData) < 0.01 ? Theme.tx : "transparent"
                border.width: 2
                Rectangle { anchors.centerIn: parent; width: 14; height: 14; radius: 7; color: "white"; opacity: modelData
                            border.color: Theme.lineHi }
                MouseArea { id: opArea; anchors.fill: parent; hoverEnabled: true
                            onClicked: editor.setNoteOpacity(editor.noteSel, modelData) }
                Tip { text: L.t.opacity_tip.arg(Math.round(modelData * 100)); shown: opArea.containsMouse }
            }
        }
        Repeater {
            model: bar.logo ? [] : ["#F26A21", "#FFFFFF", "#FFD60A", "#1C1F24"]
            Rectangle {
                objectName: "ink" + index
                anchors.verticalCenter: parent.verticalCenter
                width: 22; height: 22; radius: 11
                color: "transparent"
                // the chosen ink: a neutral ring with a gap, so it reads on any ink and any accent
                // (the editor's yellow ring on the yellow ink was 1.1:1)
                border.color: Qt.colorEqual(bar.ink, modelData) ? Theme.tx : "transparent"
                border.width: 2
                Rectangle { anchors.centerIn: parent; width: 14; height: 14; radius: 7; color: modelData
                            border.color: Theme.lineHi }
                MouseArea { anchors.fill: parent; onClicked: bar.inkPicked(modelData) }
            }
        }
        Sep {}
        // the whole edit: a quarter turn, and the frame (as it is, or 16:9 for a phone video)
        Key { objectName: "drawRotate"; glyph: Theme.icRotateRight; latched: editor.rotation !== 0
              tip: L.t.draw_rotate; onClicked: actions.run("edit_rotate") }
        Key { id: frameKey; objectName: "drawFrame"; glyph: "rectangle-horizontal"; latched: editor.frame !== "asis"
              held: frameMenu.visible
              tip: L.t.draw_frame
              onClicked: {
                  frameMenu.items = [{ header: L.t.m_frame }].concat(["asis", "blur", "crop"].map(f => (
                      { text: L.t["frame_" + f], checked: editor.frame === f, run: () => editor.setFrame(f) })))
                  frameMenu.open()
              }
              BraunMenu { id: frameMenu; objectName: "frameMenu"; y: parent.height + 8; margins: 8 } }
        Sep {}
        Key { objectName: "drawUndo"; glyph: "undo-2"; tip: L.t.draw_undo; onClicked: actions.run("edit_undo") }
        Key { objectName: "drawRedo"; glyph: "redo-2"; tip: L.t.draw_redo; onClicked: actions.run("edit_redo") }
        Key { objectName: "drawDelete"; glyph: Theme.icDelete; tip: L.t.draw_delete
              enabled: editor.noteSel >= 0
              onClicked: actions.run("remove_selected") }
    }
}
