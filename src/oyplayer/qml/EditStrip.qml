import QtQuick

// The editor's deck, one row under its tracks (the concept): marks and cuts, the
// transport, the time to the hundredth; what the edit will be and how it is saved, Cancel and
// Save on the right. The fragments themselves are blocks on the timeline's clip track; between
// the two groups the strip says when it is saving or why saving failed.
Item {
    id: strip
    height: Theme.keyPlay
    property bool focused: false        // the keyboard works on the fragments (Main's area)
    signal picked()                     // a fragment was chosen: the strip takes the keys

    // The keyboard on the fragments: ← → Home End choose one (its first frame shows), Ctrl+← →
    // move it earlier or later in the edit, Enter plays the edit from it, Delete takes it out.
    function navigate(k) {
        var n = frags.length, cur = editor.selected
        if (n === 0) return
        if (k === "enter") { if (cur >= 0) editor.playFrom(cur); return }
        if (k === "delete") { if (cur >= 0) editor.removeSelected(); return }
        if (k === "earlier" || k === "later") {
            if (cur >= 0) editor.move(cur, Math.max(0, Math.min(n - 1, cur + (k === "earlier" ? -1 : 1))))
            return
        }
        editor.select(k === "home" ? 0 : k === "end" ? n - 1
                      : cur < 0 ? 0 : Math.max(0, Math.min(n - 1, cur + (k === "left" ? -1 : 1))))
    }

    function fmt(s) {
        s = Math.max(0, s)
        var m = Math.floor(s / 60), r = s - m * 60
        return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1)
    }

    readonly property var frags: editor.fragments
    // while the edit plays: how much of it has played
    readonly property real played: {
        var row = editor.previewing
        if (row < 0 || row >= frags.length) return 0
        var s = 0
        for (var k = 0; k < row; k++) s += frags[k].dur
        return s + Math.max(0, Math.min(frags[row].dur, player.position - frags[row].from))
    }
    readonly property int gap: Theme.tier ? 8 : 6

    // a group in a frame of its own (Argon's v1): the cuts, what goes into the file, the codec
    component Box: Rectangle {
        height: Theme.keyH + 8
        anchors.verticalCenter: parent.verticalCenter
        radius: Theme.keyRadius + 3
        color: Theme.card; border.color: Theme.lineHi
    }

    component Sep: Item {
        width: [6, 10, 22][Theme.tier]; height: 24
        anchors.verticalCenter: parent.verticalCenter
        Rectangle { anchors.centerIn: parent; width: 1; height: parent.height; color: Theme.rule }
    }

    Row {
        id: tools
        anchors.verticalCenter: parent.verticalCenter
        spacing: strip.gap
        // the edit holds the whole file; these take away. Read as a ruler: |← ✂ →| (council 3),
        // printed keys in one capsule with the bin (Argon's v1, 01.11)
        Box {
            id: cuts
            objectName: "cutCapsule"
            width: cutRow.width + 8
            Row {
                id: cutRow
                anchors.centerIn: parent
                spacing: 2
                KeyCap { objectName: "editIn"; flat: true; glyph: "arrow-left-to-line"; tip: L.t.es_in
                         anchors.verticalCenter: parent.verticalCenter; onClicked: actions.run("mark_in") }
                KeyCap { objectName: "editCut"; flat: true; glyph: Theme.icCut; tip: L.t.es_cut
                         caption: strip.width >= 1000 ? L.t.es_cut_word : ""
                         anchors.verticalCenter: parent.verticalCenter; onClicked: actions.run("cut_out") }
                KeyCap { objectName: "editOut"; flat: true; glyph: "arrow-right-to-line"; tip: L.t.es_out
                         anchors.verticalCenter: parent.verticalCenter; onClicked: actions.run("mark_out") }
                Rectangle { width: 1; height: 20; color: Theme.rule; anchors.verticalCenter: parent.verticalCenter }
                KeyCap { objectName: "editDelete"; flat: true; glyph: Theme.icDelete; tip: L.t.es_clear; enabled: strip.frags.length > 0
                         second: true
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: editor.removeSelected()
                         onRightClicked: editor.clear() }
            }
        }
        Sep {}
        // frame by frame: only where the row has the room (Ctrl+← → do it in any window)
        KeyCap { objectName: "editFrameBack"; glyph: "step-back"; tip: L.t.t_frame_back; enabled: player.hasFile
                 visible: Theme.tier === 2
                 anchors.verticalCenter: parent.verticalCenter; onClicked: actions.run("frame_backward") }
        PlayKey { objectName: "editPlay"; anchors.verticalCenter: parent.verticalCenter
                  playing: player.hasFile && !player.paused
                  name: (player.paused || !player.hasFile ? L.t.t_play : L.t.t_pause).replace(/\s*\([^)]*\)/g, "")
                  tip: player.paused || !player.hasFile ? L.t.t_play : L.t.t_pause
                  onClicked: actions.run("play_pause") }
        KeyCap { objectName: "editFrame"; glyph: Theme.icFrame; tip: L.t.t_frame; enabled: player.hasFile
                 visible: Theme.tier === 2
                 anchors.verticalCenter: parent.verticalCenter; onClicked: actions.run("frame_forward") }
        Sep {}
        LcdTime { objectName: "editLcd"; fine: true; anchors.verticalCenter: parent.verticalCenter
                  position: player.position; duration: player.duration }
    }

    // ---- between the groups: nothing while there is nothing to say (the fragments are on the
    // clip track), a hint while the edit is empty, the progress while saving, a failure's reason
    Item {
        id: middle
        anchors { left: tools.right; leftMargin: 16; right: infoBox.left; rightMargin: 16
                  top: parent.top; bottom: parent.bottom; topMargin: 4; bottomMargin: 4 }
        Text {
            visible: !editor.edited && editor.previewing < 0 && !editor.exporting && editor.error === ""
            anchors.fill: parent
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            text: L.t.es_hint
            color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 11
        }
        // the result playing: where in the finished video, its pieces' joints; a click goes there
        Rectangle {
            id: resultBar
            objectName: "resultBar"
            visible: editor.previewing >= 0 && !editor.exporting
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
            height: 14; radius: 7
            color: Theme.groove; border.color: Theme.line
            Rectangle {
                x: 2; y: 2; height: parent.height - 4; radius: 5
                width: editor.total > 0 ? Math.min(1, strip.played / editor.total) * (parent.width - 4) : 0
                color: Theme.acc
            }
            Repeater {
                model: strip.frags.length > 1 ? strip.frags.length - 1 : 0
                Rectangle {
                    readonly property real at: strip.frags.slice(0, index + 1).reduce((a, f) => a + f.dur, 0)
                    x: 2 + at / Math.max(0.001, editor.total) * (resultBar.width - 4) - 1
                    y: -3; width: 2; height: resultBar.height + 6; color: Theme.tx2
                }
            }
            MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                        onClicked: (m) => editor.playAtEdit(Math.max(0, m.x - 8) / (resultBar.width - 4) * editor.total) }
        }
        // saving: a progress groove
        Rectangle {
            visible: editor.exporting
            anchors.fill: parent
            radius: 8
            color: Theme.groove; border.color: Theme.line
            Rectangle {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 4 }
                width: editor.progress * (parent.width - 8)
                visible: width > 2
                radius: 5
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accHi }
                    GradientStop { position: 1; color: Theme.acc }
                }
            }
            Text {
                anchors.centerIn: parent
                text: L.t.es_saving.arg(Math.round(editor.progress * 100))
                color: Theme.tx; style: Text.Outline; styleColor: Theme.bg
                font.family: Theme.uiFont; font.pixelSize: 12
            }
        }
        // a failed save stays said, with what to do, until a click or the next try
        Rectangle {
            objectName: "editError"
            visible: editor.error !== "" && !editor.exporting
            anchors.fill: parent
            radius: 8
            color: Theme.groove; border.color: Theme.accText
            Text {
                id: errText
                anchors { fill: parent; leftMargin: 10; rightMargin: 26 }
                verticalAlignment: Text.AlignVCenter
                text: editor.error
                elide: Text.ElideRight
                color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 12
            }
            Icon {
                anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                name: Theme.icCancel; size: 12; stroke: 2; color: Theme.tx3
            }
            MouseArea { id: errArea; anchors.fill: parent; hoverEnabled: true; onClicked: editor.clearError() }
            Tip { text: editor.error + "\n" + L.t.click_dismiss; shown: errArea.containsMouse && errText.truncated }
        }
    }

    // ---- what goes into the file, in one line in a frame (the blind comparison: the edit's state
    // must read without opening anything): «0:25.0 • 2 fragments · LOSSLESS»; when «without
    // loss» was chosen and cannot be, the reason under it
    Box {
        id: infoBox
        objectName: "infoBox"
        anchors { right: saveRow.left; rightMargin: strip.gap; verticalCenter: parent.verticalCenter }
        width: info.width + 24
        Column {
            id: info
            anchors.centerIn: parent
            spacing: 1
            Row {
                spacing: 4
                Text {
                    objectName: "editTotal"
                    // while the edit plays: time played / length
                    text: editor.previewing >= 0 ? strip.fmt(strip.played) + " / " + strip.fmt(editor.total) : strip.fmt(editor.total)
                    color: Theme.tx; font.family: Theme.monoFont; font.pixelSize: 13; font.weight: Font.Medium
                }
                Text {
                    objectName: "editSummary"
                    anchors.baseline: parent.children[0].baseline
                    // in a narrower window, or while the result plays (its bar takes the room): the length and the mode
                    visible: strip.frags.length > 0 && strip.width >= 1000 && editor.previewing < 0
                    text: "•  " + strip.frags.length + " " + L.plural(strip.frags.length, L.t.frag_forms) + "  ·"
                    color: Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 11
                }
                Text {
                    objectName: "editMode"
                    anchors.baseline: parent.children[0].baseline
                    text: strip.frags.length === 0 ? L.t.edit_caps : { copy: L.t.lossless_caps, h264: "H.264", h265: "H.265" }[editor.mode]
                    color: strip.frags.length > 0 && editor.lossless ? Theme.accText : Theme.tx3
                    font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: .8
                }
            }
            Row {
                spacing: 8
                Text {
                    objectName: "editReason"
                    visible: strip.frags.length > 0 && editor.reason !== ""
                    text: editor.reason.toUpperCase()
                    color: Theme.tx3
                    font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: .8
                }
            }
        }
        HoverHandler { id: infoHover }
        Tip { text: editor.note; shown: infoHover.hovered && editor.note !== "" }
    }

    Row {
        id: saveRow
        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
        spacing: strip.gap
        // what saving will really do: «Lossless» goes off while it cannot be (the setting stays,
        // and comes back into force when the drawings or the other format are gone)
        Box {
            width: codecRow.width + 20
            Row {
                id: codecRow
                anchors.centerIn: parent
                spacing: 10
                Text { objectName: "codecTitle"; text: L.t.es_codec.toUpperCase(); color: Theme.tx3
                       visible: strip.width >= 1000
                       anchors.verticalCenter: parent.verticalCenter
                       font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: .8 }
                Segmented {
                    objectName: "editCodec"
                    width: [130, 150, 186][Theme.tier]
                    value: editor.mode
                    options: [{ value: "copy", text: L.t.lossless, enabled: editor.canCopy },
                              { value: "h264", text: "H.264" }, { value: "h265", text: "H.265" }]
                    anchors.verticalCenter: parent.verticalCenter
                    onPicked: (x) => settings.set("exportCodec", x)
                }
            }
        }
        // the finished video, always from its start (again: stop)
        // the words only where the row has the room (the middle keeps its say: progress, a failure)
        KeyCap { objectName: "editPreview"; glyph: "eye"; caption: strip.width >= 1000 ? L.t.es_result : ""
                 latched: editor.previewing >= 0
                 tip: L.t.es_preview; enabled: strip.frags.length > 0
                 anchors.verticalCenter: parent.verticalCenter
                 onClicked: actions.run("edit_preview") }
        // saves at once beside the source; «Save as…» on the right button
        KeyCap { objectName: "editSave"; accent: true
                 glyph: editor.exporting ? Theme.icCancel : "upload"
                 caption: editor.exporting ? L.t.cancel : L.t.es_export
                 latched: editor.exporting
                 second: !editor.exporting
                 tip: editor.exporting ? L.t.es_cancel_save : L.t.es_save
                 enabled: editor.exporting || editor.edited
                 anchors.verticalCenter: parent.verticalCenter
                 onClicked: editor.exporting ? editor.cancelExport() : actions.run("edit_save")
                 onRightClicked: actions.run("edit_save_as") }
        KeyCap { visible: editor.saved !== "" && !editor.exporting; glyph: Theme.icFolder
                 tip: L.t.es_reveal; anchors.verticalCenter: parent.verticalCenter
                 onClicked: editor.revealSaved() }
    }
}
