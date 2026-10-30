import QtQuick

// The internal playlist, docked right, with two more pages kept
// in windows of their own: the viewing history (Ctrl+H) and the radio stations (Ctrl+F2).
// Numbers and durations on (PlayList.ShowNumbers / ShowDuration = 1). The playing row
// carries the orange accent; the selected row is a raised card. Bottom bar = Omega's
// playlist panel: add, remove | repeat, shuffle, save.
Rectangle {
    id: pl
    color: Theme.bg
    property int tab: 0                 // 0 list, 1 history, 2 radio
    property string histSel: ""         // the history row picked (its path)
    property bool adding: false         // the radio's "add a station" form is open
    property int stSel: -1              // the station row picked
    property bool focused: false        // the keyboard works here (Main's area)
    signal addFiles()
    signal saveRequested()
    signal picked()                     // a row was clicked: the list takes the keys

    // The keyboard inside the list, the same on every tab: ↑ ↓ Home End move the choice,
    // Enter plays it, Delete takes it out (the history's row; a station stays).
    function navigate(k) {
        var view = tab === 0 ? list : tab === 1 ? hist : stations
        var n = view.count
        if (n === 0) return
        var cur = tab === 0 ? playlist.selected : tab === 1 ? history.entries.findIndex(e => e.path === histSel) : stSel
        if (k === "enter") {
            if (cur < 0) return
            if (tab === 0) playlist.playIndex(cur)
            else if (tab === 1) playlist.add([histSel], true)
            else playlist.add([radio.stations[cur].file], true)
            return
        }
        if (k === "delete") {
            if (cur < 0) return
            if (tab === 0) actions.run("playlist_remove")
            else if (tab === 1) { history.remove(histSel); histSel = "" }
            return
        }
        var next = k === "home" ? 0 : k === "end" ? n - 1
                 : cur < 0 ? 0 : Math.max(0, Math.min(n - 1, cur + (k === "up" ? -1 : 1)))
        if (tab === 0) playlist.selected = next
        else if (tab === 1) histSel = history.entries[next].path
        else stSel = next
        view.positionViewAtIndex(next, ListView.Contain)
    }

    function fmt(s) {
        s = Math.max(0, Math.floor(s))
        if (s === 0) return ""
        var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (sec < 10 ? "0" : "") + sec
    }

    Rectangle { anchors { left: parent.left; top: parent.top; bottom: parent.bottom } width: 1; color: Theme.lineHi }

    // header: the three pages as small-caps tabs, the chosen one raised, its name in the accent
    Item {
        id: head
        anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: 10; rightMargin: 12 }
        height: 34
        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Repeater {
                model: [L.t.tab_list, L.t.tab_history, L.t.tab_radio]
                Rectangle {
                    objectName: "plTab" + index
                    width: tabText.implicitWidth + 22; height: 24; radius: 6
                    readonly property bool on: pl.tab === index
                    color: on ? Theme.panelHi : "transparent"
                    border.color: on ? Theme.lineHi : "transparent"
                    Text { id: tabText; anchors.centerIn: parent; text: modelData
                           color: parent.on ? Theme.accText : Theme.tx3
                           font.family: Theme.uiFont; font.pixelSize: 10; font.letterSpacing: 1.8 }
                    MouseArea { anchors.fill: parent; onClicked: pl.tab = index }
                }
            }
        }
        Text {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            visible: pl.tab === 0
            text: playlist.count + (playlist.totalDuration > 0 ? " · " + pl.fmt(playlist.totalDuration) : "")
            color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10; font.letterSpacing: 1.2
        }
    }

    // the page, sunk into the body
    Rectangle {   // the keyboard works here: a 2 px ring around the well (WCAG 2.4.7)
        objectName: "listFocus"
        visible: pl.focused
        anchors.fill: well; anchors.margins: -3
        radius: 13; color: "transparent"; border.width: 2; border.color: Theme.acc
    }
    Rectangle {
        id: well
        anchors { left: parent.left; right: parent.right; top: head.bottom; bottom: bar.top; leftMargin: 10; rightMargin: 8; bottomMargin: 6 }
        radius: 10
        color: Theme.well           // sunk into the body: the playing row stands up out of it
        border.color: Theme.line
        clip: true

        // ---- the list
        ListView {
            id: list
            Accessible.role: Accessible.List
            Accessible.name: L.t.act_playlist
            objectName: "playlistView"
            visible: pl.tab === 0
            anchors.fill: parent
            anchors.margins: 4
            model: playlist
            boundsBehavior: Flickable.StopAtBounds
            currentIndex: playlist.selected
            delegate: Rectangle {
                id: row
                objectName: "plRow" + index
                width: ListView.view.width
                height: 52
                radius: 7
                readonly property bool sel: index === playlist.selected
                Accessible.role: Accessible.ListItem
                Accessible.name: title + (duration > 0 ? ", " + pl.fmt(duration) : "") + (playing ? L.t.playing : "")
                Accessible.selected: sel
                Accessible.selectable: true
                Component.onCompleted: playlist.wantThumb(index)
                // the playing row stands up as a key cap (its light, hairline and shadow); the chosen one is outlined
                color: rowArea.containsMouse && !playing ? Qt.rgba(1, 1, 1, Theme.light ? .35 : .025) : "transparent"
                border.color: sel ? Theme.lineHi : "transparent"
                Raised { z: -1; visible: playing; anchors.fill: parent; radius: parent.radius }
                Rectangle {   // the playing row: an accent tab on the left
                    visible: playing
                    x: 0; y: 10; width: 3; height: parent.height - 20; radius: 1.5; color: Theme.acc
                }
                Text {
                    id: num
                    x: 10; width: 22
                    anchors.verticalCenter: parent.verticalCenter
                    text: (index < 9 ? "0" : "") + (index + 1)
                    color: playing ? Theme.accText : Theme.inkDim
                    font.family: Theme.monoFont; font.pixelSize: 11
                }
                Rectangle {   // the file's frame; a sunk tile until it comes (or for sound)
                    id: thumbTile
                    anchors { left: num.right; leftMargin: 10; verticalCenter: parent.verticalCenter }
                    width: 56; height: 32; radius: 6
                    color: Theme.sunk
                    Image {
                        objectName: "plThumb"
                        anchors.fill: parent
                        source: thumb
                        sourceSize: Qt.size(112, 64)
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        smooth: true
                        visible: status === Image.Ready
                    }
                }
                Text {
                    anchors { left: thumbTile.right; leftMargin: 10; right: dur.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                    text: title
                    elide: Text.ElideMiddle
                    color: Theme.tx
                    font.family: Theme.uiFont; font.pixelSize: 13; font.weight: playing ? Font.DemiBold : Font.Normal
                }
                Text {
                    id: dur
                    anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    text: pl.fmt(duration)
                    color: Theme.inkDim; font.family: Theme.monoFont; font.pixelSize: 11
                }
                MouseArea {
                    id: rowArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: { playlist.selected = index; pl.picked() }
                    onDoubleClicked: playlist.playIndex(index)
                }
            }
        }
        Column {
            visible: pl.tab === 0 && playlist.count === 0
            anchors.centerIn: parent
            spacing: 6
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t.pl_empty
                   color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t.pl_drop
                   color: Theme.tx3; opacity: .7; font.family: Theme.uiFont; font.pixelSize: 11 }
        }
        DropArea {
            anchors.fill: parent
            enabled: pl.tab === 0
            onDropped: (d) => { if (d.hasUrls) playlist.add(d.urls, false) }
        }

        // ---- the history: newest first, how much of each was watched
        ListView {
            id: hist
            Accessible.role: Accessible.List
            Accessible.name: L.t.history
            objectName: "historyView"
            visible: pl.tab === 1
            anchors.fill: parent
            anchors.margins: 4
            model: pl.tab === 1 ? history.entries : []
            boundsBehavior: Flickable.StopAtBounds
            delegate: Rectangle {
                width: ListView.view.width
                height: 40
                radius: 6
                readonly property bool sel: modelData.path === pl.histSel
                readonly property bool playing: modelData.path === player.path
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.name + ", " + modelData.when
                Accessible.selected: sel
                Accessible.selectable: true
                color: sel ? Theme.panelHi : (histArea.containsMouse ? Qt.rgba(1, 1, 1, Theme.light ? 0 : .025) : "transparent")
                border.color: sel ? Theme.lineHi : "transparent"
                Rectangle { visible: parent.playing; x: 0; y: 8; width: 3; height: parent.height - 16; radius: 1.5; color: Theme.acc }
                Text {
                    x: 12; y: 5; width: parent.width - 70
                    text: modelData.name; elide: Text.ElideMiddle
                    color: parent.playing ? Theme.tx : Theme.tx2
                    font.family: Theme.uiFont; font.pixelSize: 12
                }
                Text {
                    x: 12; y: 22; width: parent.width - 70
                    text: modelData.when + "  ·  " + modelData.folder; elide: Text.ElideMiddle
                    color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10
                }
                // how far it was watched: a short groove, filled orange
                Rectangle {
                    anchors { right: parent.right; rightMargin: 10; top: parent.top; topMargin: 9 }
                    width: 44; height: 4; radius: 2; color: Theme.sunk
                    Rectangle { width: Math.max(4, parent.width * modelData.frac); height: parent.height; radius: 2
                                color: modelData.frac > .97 ? Theme.tx3 : Theme.acc }
                }
                Text {
                    anchors { right: parent.right; rightMargin: 10; bottom: parent.bottom; bottomMargin: 5 }
                    text: pl.fmt(modelData.dur)
                    color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10
                }
                MouseArea {
                    id: histArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: { pl.histSel = modelData.path; pl.picked() }
                    onDoubleClicked: playlist.add([modelData.path], true)
                }
            }
        }
        Column {
            visible: pl.tab === 1 && hist.count === 0
            anchors.centerIn: parent
            width: parent.width - 40
            spacing: 6
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t.hist_empty
                   color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12 }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                   text: settings.values.history ? L.t.hist_hint : L.t.hist_off
                   color: Theme.tx3; opacity: .7; font.family: Theme.uiFont; font.pixelSize: 11 }
        }

        // ---- the radio: .lau stations from one folder
        Column {
            id: onAir
            visible: pl.tab === 2 && radio.streaming
            x: 12; y: 8; width: parent.width - 24
            spacing: 2
            Text { text: radio.recording ? L.t.on_air_rec : L.t.on_air
                   color: radio.recording ? Theme.accText : Theme.tx3
                   font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2 }
            Text { objectName: "radioNow"; width: parent.width; elide: Text.ElideRight
                   text: radio.nowPlaying !== "" ? radio.nowPlaying : player.title
                   color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 13 }
        }
        ListView {
            id: stations
            Accessible.role: Accessible.List
            Accessible.name: L.t.radio
            objectName: "radioView"
            visible: pl.tab === 2
            anchors { left: parent.left; right: parent.right; top: onAir.visible ? onAir.bottom : parent.top
                      bottom: addForm.visible ? addForm.top : parent.bottom; margins: 4; topMargin: onAir.visible ? 8 : 4 }
            model: pl.tab === 2 ? radio.stations : []
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            delegate: Rectangle {
                width: ListView.view.width
                height: 38
                radius: 6
                readonly property bool playing: modelData.url === player.path
                // as in the list and the history: the raised card is the choice, the orange tab what plays
                readonly property bool sel: index === pl.stSel
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.name + (playing ? L.t.playing : "")
                Accessible.selected: sel
                Accessible.selectable: true
                color: sel ? Theme.panelHi : (stArea.containsMouse ? Qt.rgba(1, 1, 1, Theme.light ? 0 : .025) : "transparent")
                border.color: sel ? Theme.lineHi : "transparent"
                Rectangle { visible: parent.playing; x: 0; y: 8; width: 3; height: parent.height - 16; radius: 1.5; color: Theme.acc }
                Text { x: 12; y: 4; width: parent.width - 20; text: modelData.name; elide: Text.ElideRight
                       color: parent.playing ? Theme.tx : Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 12
                       font.weight: parent.playing ? Font.DemiBold : Font.Normal }
                Text { x: 12; y: 21; width: parent.width - 20; text: modelData.info || modelData.url; elide: Text.ElideRight
                       color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10 }
                MouseArea { id: stArea; anchors.fill: parent; hoverEnabled: true
                            onClicked: { pl.stSel = index; pl.picked() }
                            onDoubleClicked: playlist.add([modelData.file], true) }
            }
        }
        Column {
            visible: pl.tab === 2 && stations.count === 0 && !addForm.visible
            anchors.centerIn: parent
            width: parent.width - 40
            spacing: 6
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t.no_stations
                   color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 12 }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                   text: L.t.stations_hint
                   color: Theme.tx3; opacity: .7; font.family: Theme.uiFont; font.pixelSize: 11 }
        }
        Column {
            id: addForm
            visible: pl.tab === 2 && pl.adding
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
            spacing: 6
            Text { text: L.t.new_station; color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2 }
            Field { id: stUrl; width: parent.width; placeholder: L.t.stream_url }
            Field { id: stName; width: parent.width; placeholder: L.t.st_name }
            Row {
                spacing: 6
                PillButton { text: L.t.add; accent: true
                             onClicked: { radio.addStation(stName.text, stUrl.text); stUrl.text = ""; stName.text = ""; pl.adding = false } }
                PillButton { text: L.t.cancel; onClicked: pl.adding = false }
            }
        }
    }

    // Omega playlist bar (its keys change with the page)
    Item {
        id: bar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 10; rightMargin: 8; bottomMargin: 8 }
        height: 30
        Row {
            visible: pl.tab === 0
            spacing: 5
            KeyCap { objectName: "plAdd"; glyph: Theme.icAdd; glyphSize: 15; width: 28; height: 26; tip: L.t.pl_add
                     onClicked: pl.addFiles() }
            KeyCap { glyph: Theme.icRemove; glyphSize: 15; width: 28; height: 26; tip: L.t.pl_remove
                     objectName: "plRemove"; enabled: playlist.selected >= 0; opacity: enabled ? 1 : .35
                     onClicked: actions.run("playlist_remove") }   // the row, even while the editor is open
        }
        Row {
            visible: pl.tab === 0
            anchors.right: parent.right
            spacing: 5
            KeyCap { glyph: playlist.repeat === 2 ? Theme.icRepeatOne : Theme.icRepeat; glyphSize: 15; width: 28; height: 26
                     latched: playlist.repeat > 0
                     tip: [L.t.rep_off, L.t.rep_list, L.t.rep_one][playlist.repeat]
                     onClicked: actions.run("repeat") }
            KeyCap { glyph: Theme.icShuffle; glyphSize: 15; width: 28; height: 26; latched: playlist.shuffle
                     tip: L.t.act_shuffle; onClicked: actions.run("shuffle") }
            KeyCap { glyph: Theme.icSave; glyphSize: 15; width: 28; height: 26; tip: L.t.pl_save
                     enabled: playlist.count > 0; opacity: enabled ? 1 : .35
                     onClicked: pl.saveRequested() }
        }
        // history: play, take a row out | empty it (twice, so a slip costs nothing)
        Row {
            visible: pl.tab === 1
            spacing: 5
            KeyCap { glyph: Theme.icPlay; glyphSize: 15; width: 28; height: 26; tip: L.t.play
                     enabled: pl.histSel !== ""; opacity: enabled ? 1 : .35
                     onClicked: playlist.add([pl.histSel], true) }
            KeyCap { glyph: Theme.icRemove; glyphSize: 15; width: 28; height: 26; tip: L.t.hist_remove
                     enabled: pl.histSel !== ""; opacity: enabled ? 1 : .35
                     onClicked: { history.remove(pl.histSel); pl.histSel = "" } }
        }
        KeyCap {
            id: clearHist
            visible: pl.tab === 1
            anchors.right: parent.right
            property bool armed: false
            glyph: Theme.icDelete; glyphSize: 15; width: 28; height: 26; latched: armed
            enabled: hist.count > 0; opacity: enabled ? 1 : .35
            tip: armed ? L.t.hist_clear_armed : L.t.hist_clear
            onClicked: { if (armed) { history.clear(); armed = false } else { armed = true; disarm.restart() } }
            Timer { id: disarm; interval: 3000; onTriggered: clearHist.armed = false }
        }
        // radio: the stations' folder, a new station | record
        Row {
            visible: pl.tab === 2
            spacing: 5
            KeyCap { glyph: Theme.icFolder; glyphSize: 15; width: 28; height: 26; tip: L.t.stations_folder
                     onClicked: radio.openDir() }
            KeyCap { glyph: Theme.icAdd; glyphSize: 15; width: 28; height: 26; tip: L.t.add_station; latched: pl.adding
                     onClicked: pl.adding = !pl.adding }
        }
        Row {
            visible: pl.tab === 2
            anchors.right: parent.right
            spacing: 8
            Text { anchors.verticalCenter: parent.verticalCenter; visible: radio.recording
                   text: L.t.rec_caps; color: Theme.accText; font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 2 }
            KeyCap { objectName: "radioRecord"; glyph: Theme.icRecord; glyphSize: 15; width: 28; height: 26
                     latched: radio.recording; enabled: radio.streaming || radio.recording; opacity: enabled ? 1 : .35
                     tip: radio.recording ? L.t.rec_stop : L.t.rec_start
                     onClicked: actions.run("radio_record") }
        }
    }
}
