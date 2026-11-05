import QtQuick
import QtQuick.Dialogs

// The screenshot editor (setting «shotMode» = edit): the frame, the editor's drawing card over
// it, and Copy, Save, Close at the foot. Closed, the picture and what was drawn on it are dropped.
// A window of its own (loaded beside Main.qml, not inside it), so its keys' names are not the
// player window's children.
Window {
    id: sw
    objectName: "shotWindow"
    property Window main: null                  // the player's window (set from Python)
    visible: false
    width: 1100; height: 760
    minimumWidth: 640; minimumHeight: 420
    title: L.t.shot_title + " — OY Player"
    color: Theme.bg
    flags: Qt.Window | (app.selftest ? Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput : 0)
    LayoutMirroring.enabled: L.rtl              // a language written right to left (as Main)
    LayoutMirroring.childrenInherit: true
    readonly property bool popupOpen: false    // Tip asks the window whether a card is open
    property string drawTool: "select"
    property color drawInk: "#F26A21"
    property real drawSize: 1

    // over the player's window, on its screen, whole inside its work area
    function openOver(main) {
        var a = app.workArea(main)
        width = Math.min(1100, a[2] - 40); height = Math.min(760, a[3] - 40)
        x = Math.max(a[0], Math.min(a[0] + a[2] - width, main.x + (main.width - width) / 2))
        y = Math.max(a[1], Math.min(a[1] + a[3] - height, main.y + (main.height - height) / 2))
        drawTool = "select"
        show(); raise()
        if (!app.selftest) requestActivate()
    }
    onClosing: shot.close()
    // the player's window closed: this one goes too, or it would keep the program running
    Connections { target: sw.main; function onClosing() { sw.close() } }
    // a caption being typed counts in what is saved or copied, as with Enter
    function save() { noteLayer.commitText(); shot.save() }
    function copy() { noteLayer.commitText(); shot.copy() }
    Connections { target: shot; function onOpened() { sw.openOver(sw.main) }
                  function onMessage(t) { msg.show(t) } function onSaved(p) { toast.show(p) } }

    // the keys of the card and the foot; while a caption is typed they are the text's
    Shortcut { enabled: !noteLayer.typing; sequences: [StandardKey.Undo]; onActivated: shot.undo() }
    Shortcut { enabled: !noteLayer.typing; sequences: [StandardKey.Redo, "Ctrl+Shift+Z"]; onActivated: shot.redo() }
    Shortcut { enabled: !noteLayer.typing; sequences: [StandardKey.Copy]; onActivated: sw.copy() }
    Shortcut { sequences: [StandardKey.Save]; onActivated: sw.save() }
    Shortcut { enabled: !noteLayer.typing; sequences: [StandardKey.Delete]; onActivated: shot.removeSelected() }
    Shortcut { enabled: !noteLayer.typing; sequence: "Esc"
               onActivated: { if (shot.noteSel >= 0) shot.selectNote(-1); else sw.close() } }

    // ---------- the picture, as large as fits, the drawings exactly over it
    Item {
        id: stage
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: foot.top
                  topMargin: drawBar.height + 24; leftMargin: 16; rightMargin: 16; bottomMargin: 8 }
        Image {
            id: pic
            objectName: "shotPicture"
            anchors.fill: parent
            source: shot.source
            fillMode: Image.PreserveAspectFit
            cache: false
            smooth: true; mipmap: true
        }
        NoteLayer {
            id: noteLayer
            objectName: "shotLayer"
            ed: shot
            still: true
            x: (pic.width - pic.paintedWidth) / 2
            y: (pic.height - pic.paintedHeight) / 2
            width: pic.paintedWidth; height: pic.paintedHeight
            tool: sw.drawTool
            ink: sw.drawInk
            size: sw.drawSize
        }
        DropArea {
            anchors.fill: parent
            onDropped: (d) => { if (d.hasUrls) shot.addImage(d.urls[0].toString()) }
        }
    }

    DrawBar {
        id: drawBar
        objectName: "shotDrawBar"
        ed: shot
        still: true
        anchors.horizontalCenter: parent.horizontalCenter
        y: 12
        tool: sw.drawTool
        ink: sw.drawInk
        size: sw.drawSize
        onToolPicked: (t) => sw.drawTool = t
        onImageRequested: imageDialog.open()
        onInkPicked: (c) => {
            sw.drawInk = c
            if (shot.noteSel >= 0) shot.setNoteColor(shot.noteSel, c.toString())
        }
        onSizePicked: (v) => {
            sw.drawSize = v
            if (shot.noteSel >= 0 && shot.notes[shot.noteSel].kind !== "image") shot.setNoteSize(shot.noteSel, v)
        }
    }
    FileDialog {
        id: imageDialog
        title: L.t.d_image
        nameFilters: [L.t.f_images + " (*.png *.jpg *.jpeg *.webp *.bmp *.gif)", L.t.f_all + " (*)"]
        onAccepted: shot.addImage(selectedFile.toString())
    }

    // ---------- the foot: the frame's name; copy, save, close
    Item {
        id: foot
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 52
        Text {
            objectName: "shotName"
            anchors { left: parent.left; leftMargin: 16; right: buttons.left; rightMargin: 16; verticalCenter: parent.verticalCenter }
            elide: Text.ElideMiddle
            text: shot.name
            color: Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 12
        }
        Row {
            id: buttons
            anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
            spacing: 8
            PillButton { objectName: "shotCopy"; text: L.t.shot_copy; onClicked: sw.copy() }
            PillButton { objectName: "shotSave"; text: L.t.shot_save; accent: true; onClicked: sw.save() }
            PillButton { objectName: "shotClose"; text: L.t.shot_close; onClicked: sw.close() }
        }
    }

    // ---------- what was done: undo, copy; a save's file and its folder
    Text {
        id: msg
        objectName: "shotMessage"
        anchors { left: parent.left; leftMargin: 18; bottom: foot.top; bottomMargin: 12 }
        color: "white"; style: Text.Outline; styleColor: "black"
        font.family: Theme.uiFont; font.pixelSize: 16
        opacity: 0
        function show(t) { text = t; opacity = 1; msgTimer.restart() }
        Timer { id: msgTimer; interval: 1600; onTriggered: msg.opacity = 0 }
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
    ShotToast {
        id: toast
        anchors { horizontalCenter: parent.horizontalCenter; bottom: foot.top; bottomMargin: 12 }
    }
}
