import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

// Settings: six sections instead of fifteen pages, and About. Each row is a name, one sentence
// and one control (MAS). Changes apply at once; there is no OK/Apply.
Popup {
    id: sp
    property int section: 0
    readonly property var v: settings.values
    anchors.centerIn: Overlay.overlay
    width: Math.min(780, (parent ? parent.width : 800) - 40)
    height: Math.min(600, (parent ? parent.height : 640) - 40)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onClosed: actions.stopCapture()
    background: FloatCard { color: Theme.bg; radius: 14 }

    readonly property var sections: [
        { title: L.t.p_playback, icon: Theme.icPlay }, { title: L.t.p_window, icon: Theme.icWindow },
        { title: L.t.p_sound, icon: Theme.icVolume }, { title: L.t.p_subs, icon: Theme.icCaptions },
        { title: L.t.p_controls, icon: Theme.icKeyboard }, { title: L.t.p_shots, icon: Theme.icCamera },
        { title: L.t.about, icon: Theme.icInfo }]
    // what «Defaults» puts back in each section (the language, the key list and the file types
    // in Windows are left as they are: each has its own way back)
    readonly property var sectionKeys: [
        ["resume", "fileMemory", "openAdds", "series", "autoskip", "onListEnd", "history", "hwdec"],
        ["theme", "accent", "onTop", "fitWindow", "singleInstance", "updateCheck", "tray"],
        ["audioDevice", "channels", "passthrough", "audioMode", "maxVolume", "audioLang", "radioDir", "radioRecDir"],
        ["subsOn", "subScale", "subLang", "subFolders"],
        ["wheel", "leftClick", "middleClick", "doubleClick", "sideButtons", "preview", "globalMedia", "seekStep", "jumpStep"],
        ["shotFormat", "shotQuality", "shotDir", "exportCodec", "mpvOptions"],
        []]

    component Card: Rectangle {
        default property alias rows: col.data
        width: parent ? parent.width : 400
        height: col.height
        radius: 12; color: Theme.card; border.color: Theme.line
        Column { id: col; width: parent.width }
    }
    component Caption: Text {
        leftPadding: 4; topPadding: 6
        color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10; font.letterSpacing: 2.2
    }

    contentItem: Item {
        // ---- navigation (MAS tabs, vertical)
        Rectangle {
            id: nav
            width: 208; height: parent.height
            color: "transparent"
            Text { x: 20; y: 18; text: L.t.s_caps; color: Theme.tx2
                   font.family: Theme.uiFont; font.pixelSize: 11; font.letterSpacing: 2.6 }
            Rectangle {
                x: 12; y: 46; width: parent.width - 20; height: navCol.height + 8
                radius: 11; color: Theme.sunk
                Column {
                    id: navCol
                    x: 4; y: 4; width: parent.width - 8; spacing: 2
                    Repeater {
                        model: sp.sections
                        Rectangle {
                            objectName: "nav" + index
                            width: navCol.width; height: 38; radius: 8
                            readonly property bool on: sp.section === index
                            color: on ? Theme.panelHi : "transparent"
                            border.color: on ? Theme.lineHi : "transparent"
                            // About in the accent while a newer version waits
                            Icon { x: 12; anchors.verticalCenter: parent.verticalCenter; name: modelData.icon
                                   size: 16; color: parent.on || (index === 6 && updater.state === "available") ? Theme.accText : Theme.tx3 }
                            Text { x: 38; anchors.verticalCenter: parent.verticalCenter; text: modelData.title
                                   font.family: Theme.uiFont; font.pixelSize: 13; color: parent.on ? Theme.tx : Theme.tx2 }
                            MouseArea { anchors.fill: parent; onClicked: { actions.stopCapture(); sp.section = index; flick.contentY = 0 } }
                        }
                    }
                }
            }
            // the section back to its defaults: a second press within three seconds does it
            Rectangle {
                id: resetKey
                objectName: "resetSection"
                property bool armed: false
                visible: sp.sectionKeys[sp.section].length > 0
                x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                width: resetRow.implicitWidth + 20; height: 28; radius: 7
                color: resetArea.containsMouse ? Theme.card : "transparent"
                border.color: armed ? Theme.accA(.6) : resetArea.containsMouse ? Theme.line : "transparent"
                Row {
                    id: resetRow
                    anchors.centerIn: parent
                    spacing: 6
                    Icon { anchors.verticalCenter: parent.verticalCenter; name: Theme.icRotateLeft; size: 13
                           color: resetKey.armed ? Theme.accText : Theme.tx3 }
                    Text { anchors.verticalCenter: parent.verticalCenter
                           text: resetKey.armed ? L.t.reset_again : L.t.reset_section
                           color: resetKey.armed ? Theme.accText : resetArea.containsMouse ? Theme.tx : Theme.tx2
                           font.family: Theme.uiFont; font.pixelSize: 12 }
                }
                MouseArea {
                    id: resetArea; anchors.fill: parent; hoverEnabled: true
                    onClicked: {
                        if (!resetKey.armed) { resetKey.armed = true; disarm.restart(); return }
                        resetKey.armed = false
                        sp.sectionKeys[sp.section].forEach(k => settings.reset(k))
                    }
                }
                Timer { id: disarm; interval: 3000; onTriggered: resetKey.armed = false }
                Connections { target: sp; function onSectionChanged() { resetKey.armed = false } }
                Tip { text: L.t.reset_section_tip; shown: resetArea.containsMouse && !resetKey.armed }
            }
        }

        // ---- the section's name, and the way out in the corner, where a window has it
        Text {
            id: pageTitle
            anchors { left: nav.right; leftMargin: 4; top: parent.top; topMargin: 15 }
            text: sp.sections[sp.section].title
            color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 16; font.weight: Font.DemiBold
        }
        IconButton {
            objectName: "settingsClose"
            anchors { right: parent.right; rightMargin: 10; top: parent.top; topMargin: 10 }
            width: 32; height: 28
            glyph: Theme.icClose
            tip: L.t.t_close; onClicked: sp.close()
        }

        // ---- the section
        Flickable {
            id: flick
            objectName: "settingsFlick"
            anchors { left: nav.right; right: parent.right; top: parent.top; bottom: parent.bottom
                      topMargin: 46; bottomMargin: 14; rightMargin: 14 }
            contentHeight: pages.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Item {
                id: pages
                width: flick.width - 10
                height: [p0, p1, p2, p3, p4, p5, p6][sp.section].height

                // 1. Playback
                Column {
                    id: p0; visible: sp.section === 0; width: parent.width; spacing: 10
                    Caption { text: L.t.c_opening }
                    Card {
                        SettingRow { title: L.t.s_resume
                                     hint: L.t.s_resume_h
                                     Toggle { objectName: "setResume"; checked: sp.v.resume; onToggled: (on) => settings.set("resume", on) } }
                        SettingRow { title: L.t.s_memory
                                     hint: L.t.s_memory_h
                                     Toggle { objectName: "setFileMemory"; checked: sp.v.fileMemory; onToggled: (on) => settings.set("fileMemory", on) } }
                        SettingRow { title: L.t.s_opened; below: true
                                     hint: L.t.s_opened_h
                                     Segmented { width: 320; value: sp.v.openAdds
                                                 options: [{ value: false, text: L.t.o_replace_list }, { value: true, text: L.t.o_add_list }]
                                                 onPicked: (x) => settings.set("openAdds", x) } }
                    }
                    Caption { text: L.t.c_series }
                    Card {
                        SettingRow { title: L.t.s_series
                                     hint: L.t.s_series_h
                                     Toggle { objectName: "setSeries"; checked: sp.v.series; onToggled: (on) => settings.set("series", on) } }
                        SettingRow { title: L.t.s_skip
                                     hint: L.t.s_skip_h
                                     Toggle { objectName: "setAutoskip"; checked: sp.v.autoskip; onToggled: (on) => settings.set("autoskip", on) } }
                    }
                    Caption { text: L.t.c_list_end }
                    Card {
                        SettingRow { title: L.t.s_list_end; below: true
                                     hint: L.t.s_list_end_h
                                     Segmented { objectName: "setListEnd"; width: parent.width; value: sp.v.onListEnd
                                                 options: [{ value: "stop", text: L.t.o_stop }, { value: "close", text: L.t.o_close },
                                                           { value: "sleep", text: L.t.o_sleep }, { value: "shutdown", text: L.t.o_shutdown }]
                                                 onPicked: (x) => settings.set("onListEnd", x) } }
                    }
                    Caption { text: L.t.c_history }
                    Card {
                        SettingRow { title: L.t.s_history
                                     hint: L.t.s_history_h
                                     Toggle { checked: sp.v.history; onToggled: (on) => settings.set("history", on) } }
                    }
                    Caption { text: L.t.c_decoding }
                    Card {
                        SettingRow { title: L.t.s_hwdec
                                     hint: L.t.s_hwdec_h
                                     Toggle { checked: sp.v.hwdec; onToggled: (on) => settings.set("hwdec", on) } }
                    }
                }

                // 2. Window
                Column {
                    id: p1; visible: sp.section === 1; width: parent.width; spacing: 10
                    Caption { text: L.t.c_view }
                    Card {
                        SettingRow { title: L.t.s_lang; below: true; hint: ""
                                     Choice { objectName: "setLang"; width: 260; value: sp.v.lang
                                              options: [{ value: "", text: L.t.as_windows }].concat(
                                                           i18n.languages.map(l => ({ value: l.code, text: l.name })))
                                              onPicked: (x) => settings.set("lang", x) } }
                        SettingRow { title: L.t.s_theme; below: true; hint: ""
                                     Segmented { objectName: "setTheme"; width: 360; value: sp.v.theme
                                                 options: [{ value: "system", text: L.t.as_windows }, { value: "dark", text: L.t.o_dark }, { value: "light", text: L.t.o_light }]
                                                 onPicked: (x) => settings.set("theme", x) } }
                        SettingRow { title: L.t.s_accent; below: true
                                     hint: L.t.s_accent_h
                                     AccentDial { objectName: "setAccent"; width: parent.width } }
                        SettingRow { title: L.t.act_on_top; below: true
                                     hint: L.t.s_on_top_h
                                     Segmented { width: 400; value: sp.v.onTop
                                                 options: [{ value: "never", text: L.t.o_never }, { value: "always", text: L.t.o_always }, { value: "playing", text: L.t.o_playing }]
                                                 onPicked: (x) => settings.set("onTop", x) } }
                        SettingRow { title: L.t.s_fit
                                     hint: L.t.s_fit_h
                                     Toggle { checked: sp.v.fitWindow; onToggled: (on) => settings.set("fitWindow", on) } }
                    }
                    Caption { text: L.t.c_system }
                    Card {
                        SettingRow { title: L.t.s_single
                                     hint: L.t.s_single_h
                                     Toggle { checked: sp.v.singleInstance; onToggled: (on) => settings.set("singleInstance", on) } }
                        SettingRow { title: L.t.s_update
                                     hint: L.t.s_update_h
                                     Toggle { objectName: "setUpdate"; checked: sp.v.updateCheck; onToggled: (on) => settings.set("updateCheck", on) } }
                        SettingRow { title: L.t.s_tray; below: true
                                     hint: L.t.s_tray_h
                                     Segmented { objectName: "setTray"; width: 400; value: sp.v.tray
                                                 options: [{ value: "off", text: L.t.o_no }, { value: "on", text: L.t.o_yes }, { value: "minimize", text: L.t.o_to_tray }]
                                                 onPicked: (x) => settings.set("tray", x) } }
                    }
                    Caption { text: L.t.c_default }
                    Card {
                        SettingRow { title: L.t.s_types; below: true
                                     hint: app.fileTypes
                                           ? L.t.s_types_on_h
                                           : L.t.s_types_off_h
                                     Row { spacing: 8
                                           PillButton { objectName: "setAssocOn"; text: app.fileTypes ? L.t.b_windows_settings : L.t.b_offer
                                                        accent: !app.fileTypes; onClicked: app.registerFileTypes(sp.v.assocAudio, true) }
                                           PillButton { objectName: "setAssocOff"; text: L.t.b_remove; visible: app.fileTypes
                                                        onClicked: app.unregisterFileTypes() } } }
                        // offered already: the new choice reaches Windows at once
                        SettingRow { title: L.t.s_assoc_audio; hint: L.t.s_assoc_audio_h
                                     Toggle { objectName: "setAssocAudio"; checked: sp.v.assocAudio
                                              onToggled: (on) => { settings.set("assocAudio", on)
                                                                   if (app.fileTypes) app.registerFileTypes(on, false) } } }
                    }
                }

                // 3. Sound
                Column {
                    id: p2; visible: sp.section === 2; width: parent.width; spacing: 10
                    Caption { text: L.t.c_output }
                    Card {
                        SettingRow { title: L.t.s_device; below: true; hint: L.t.s_device_h
                                     Column {
                                         width: parent.width; spacing: 2
                                         Repeater {
                                             model: player.audioDevices()
                                             Rectangle {
                                                 width: parent.width; height: 30; radius: 6
                                                 readonly property bool on: sp.v.audioDevice === modelData.name
                                                 color: on ? Theme.panelHi : "transparent"
                                                 border.color: on ? Theme.lineHi : "transparent"
                                                 Rectangle { visible: parent.on; x: 10; anchors.verticalCenter: parent.verticalCenter
                                                             width: 6; height: 6; radius: 3; color: Theme.acc }
                                                 Text { x: 24; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 30; elide: Text.ElideRight
                                                        text: modelData.name === "auto" ? L.t.as_windows : modelData.description
                                                        color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 12 }
                                                 MouseArea { anchors.fill: parent; onClicked: settings.set("audioDevice", modelData.name) }
                                             }
                                         }
                                     } }
                        SettingRow { title: L.t.s_channels; below: true; hint: L.t.s_channels_h
                                     Segmented { width: 360; value: sp.v.channels
                                                 options: [{ value: "auto-safe", text: L.t.aspect_asis }, { value: "stereo", text: L.t.o_stereo }, { value: "5.1", text: "5.1" }, { value: "7.1", text: "7.1" }]
                                                 onPicked: (x) => settings.set("channels", x) } }
                        SettingRow { title: L.t.s_passthrough
                                     hint: L.t.s_passthrough_h
                                     Toggle { checked: sp.v.passthrough; onToggled: (on) => settings.set("passthrough", on) } }
                    }
                    Caption { text: L.t.c_volume }
                    Card {
                        SettingRow { title: L.t.s_processing; below: true
                                     hint: L.t.s_processing_h
                                     Segmented { width: parent.width; value: sp.v.audioMode
                                                 options: [{ value: "off", text: L.t.o_off }, { value: "norm", text: L.t.o_norm }, { value: "loudnorm", text: "EBU R128" },
                                                           { value: "compressor", text: L.t.am_compressor }, { value: "leveler", text: L.t.o_speech }]
                                                 onPicked: (x) => settings.set("audioMode", x) } }
                        SettingRow { title: L.t.s_max_volume; below: true
                                     hint: L.t.s_max_volume_h
                                     Segmented { width: 320; value: sp.v.maxVolume
                                                 options: [{ value: 100, text: "100 %" }, { value: 130, text: "130 %" }, { value: 150, text: "150 %" }, { value: 200, text: "200 %" }]
                                                 onPicked: (x) => settings.set("maxVolume", x) } }
                        SettingRow { title: L.t.s_audio_lang; below: true
                                     hint: L.t.s_audio_lang_h
                                     Field { width: parent.width; text: sp.v.audioLang; onCommitted: (t) => settings.set("audioLang", t) } }
                    }
                    Caption { text: L.t.c_radio }
                    Card {
                        SettingRow { title: L.t.s_radio_dir; below: true
                                     hint: L.t.s_radio_dir_h.arg(radio.dir)
                                     Row { spacing: 6
                                           KeyCap { objectName: "setRadioDir"; glyph: Theme.icChooseDir; glyphSize: 15; width: 30; height: 26; tip: L.t.choose_folder; onClicked: radioFolder.open() }
                                           KeyCap { glyph: Theme.icFolder; glyphSize: 15; width: 30; height: 26; tip: L.t.open_folder; onClicked: radio.openDir() } } }
                        SettingRow { title: L.t.s_rec_dir; below: true
                                     hint: L.t.s_rec_dir_h.arg(radio.recDir)
                                     Row { spacing: 6
                                           KeyCap { glyph: Theme.icChooseDir; glyphSize: 15; width: 30; height: 26; tip: L.t.choose_folder; onClicked: recFolder.open() } } }
                    }
                }

                // 4. Subtitles
                Column {
                    id: p3; visible: sp.section === 3; width: parent.width; spacing: 10
                    Caption { text: L.t.c_display }
                    Card {
                        SettingRow { title: L.t.s_subs_on; hint: L.t.s_subs_on_h
                                     Toggle { checked: sp.v.subsOn; onToggled: (on) => settings.set("subsOn", on) } }
                        SettingRow { title: L.t.s_sub_size; hint: L.t.s_sub_size_h
                                     Stepper { value: Math.round(sp.v.subScale * 100); step: 10; from: 50; to: 250; suffix: " %"
                                               onChangedTo: (x) => settings.set("subScale", x / 100) } }
                    }
                    Caption { text: L.t.c_search }
                    Card {
                        SettingRow { title: L.t.s_sub_lang; below: true; hint: L.t.s_sub_lang_h
                                     Field { width: parent.width; text: sp.v.subLang; onCommitted: (t) => settings.set("subLang", t) } }
                        SettingRow { title: L.t.s_sub_dirs; below: true
                                     hint: L.t.s_sub_dirs_h
                                     Field { width: parent.width; text: sp.v.subFolders; onCommitted: (t) => settings.set("subFolders", t) } }
                    }
                }

                // 5. Controls
                Column {
                    id: p4; visible: sp.section === 4; width: parent.width; spacing: 10
                    Caption { text: L.t.c_mouse }
                    Card {
                        SettingRow { title: L.t.s_left; below: true; hint: L.t.s_left_h
                                     Segmented { objectName: "setLeftClick"; width: 360; value: sp.v.leftClick
                                                 options: [{ value: "chrome", text: L.t.o_chrome }, { value: "pause", text: L.t.o_pause }, { value: "none", text: L.t.o_nothing }]
                                                 onPicked: (x) => settings.set("leftClick", x) } }
                        SettingRow { title: L.t.s_double; below: true; hint: ""
                                     Segmented { width: 360; value: sp.v.doubleClick
                                                 options: [{ value: "fullscreen", text: L.t.act_fullscreen }, { value: "pause", text: L.t.o_pause }, { value: "none", text: L.t.o_nothing }]
                                                 onPicked: (x) => settings.set("doubleClick", x) } }
                        SettingRow { title: L.t.s_middle; below: true; hint: ""
                                     Segmented { objectName: "setMiddleClick"; width: parent.width; value: sp.v.middleClick
                                                 options: [{ value: "fullscreen", text: L.t.act_fullscreen }, { value: "chrome", text: L.t.o_chrome },
                                                           { value: "pause", text: L.t.o_pause }, { value: "none", text: L.t.o_nothing }]
                                                 onPicked: (x) => settings.set("middleClick", x) } }
                        SettingRow { title: L.t.s_side; below: true; hint: L.t.s_side_h
                                     Segmented { objectName: "setSideButtons"; width: 400; value: sp.v.sideButtons
                                                 options: [{ value: "seek", text: L.t.o_seek }, { value: "track", text: L.t.o_track }, { value: "none", text: L.t.o_nothing }]
                                                 onPicked: (x) => settings.set("sideButtons", x) } }
                        SettingRow { title: L.t.s_wheel; below: true
                                     hint: L.t.s_wheel_h
                                     Segmented { width: 300; value: sp.v.wheel
                                                 options: [{ value: "volume", text: L.t.volume }, { value: "seek", text: L.t.o_seek }]
                                                 onPicked: (x) => settings.set("wheel", x) } }
                        SettingRow { title: L.t.s_preview
                                     hint: L.t.s_preview_h
                                     Toggle { objectName: "setPreview"; checked: sp.v.preview; onToggled: (on) => settings.set("preview", on) } }
                    }
                    Caption { text: L.t.c_keyboard }
                    Card {
                        SettingRow { title: L.t.s_media_keys
                                     hint: L.t.s_media_keys_h
                                     Toggle { objectName: "setGlobalMedia"; checked: sp.v.globalMedia; onToggled: (on) => settings.set("globalMedia", on) } }
                    }
                    Caption { text: L.t.c_seeking }
                    Card {
                        SettingRow { title: L.t.s_seek_step; hint: L.t.s_seek_step_h
                                     Stepper { value: sp.v.seekStep; from: 1; to: 60; suffix: " " + L.t.sec; onChangedTo: (x) => settings.set("seekStep", x) } }
                        SettingRow { title: L.t.s_jump; hint: L.t.s_jump_h
                                     Stepper { value: sp.v.jumpStep; step: 5; from: 5; to: 600; suffix: " " + L.t.sec; onChangedTo: (x) => settings.set("jumpStep", x) } }
                    }
                    Item {
                        width: parent.width; height: 26
                        Caption { text: L.t.c_keys; anchors.bottom: parent.bottom }
                        Text {
                            anchors { right: parent.right; rightMargin: 4; bottom: parent.bottom }
                            text: L.t.keys_reset; color: resetKeys.containsMouse ? Theme.accText : Theme.tx3
                            font.family: Theme.uiFont; font.pixelSize: 11
                            MouseArea { id: resetKeys; anchors.fill: parent; hoverEnabled: true; onClicked: settings.set("keys", {}) }
                        }
                    }
                    Card {
                        id: keyCard
                        property string capturingFor: ""
                        Connections {
                            target: actions
                            function onKeyCaptured(k) {
                                if (keyCard.capturingFor === "" || k === "") { keyCard.capturingFor = ""; return }
                                var ov = Object.assign({}, sp.v.keys)
                                ov[k] = keyCard.capturingFor
                                settings.set("keys", ov)
                                keyCard.capturingFor = ""
                            }
                        }
                        Repeater {
                            model: (L.lang, actions.bindable())
                            Item {
                                width: keyCard.width; height: 34
                                Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: modelData.title
                                       color: Theme.tx2; font.family: Theme.uiFont; font.pixelSize: 12 }
                                Row {
                                    anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                    spacing: 4
                                    Repeater {
                                        model: (actions.keysVersion, actions.keysFor(modelData.id))
                                        Rectangle {
                                            width: chip.implicitWidth + 26; height: 24; radius: 6
                                            color: Theme.sunk; border.color: Theme.line
                                            Text { id: chip; x: 8; anchors.verticalCenter: parent.verticalCenter; text: modelData
                                                   color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 11 }
                                            Icon { anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                                                   name: Theme.icCancel; size: 11; stroke: 2
                                                   color: xArea.containsMouse ? Theme.accText : Theme.tx3
                                                   MouseArea { id: xArea; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
                                                               onClicked: {
                                                                   var ov = Object.assign({}, sp.v.keys)
                                                                   if (actions.isDefaultKey(modelData)) ov[modelData] = ""; else delete ov[modelData]
                                                                   settings.set("keys", ov)
                                                               } } }
                                        }
                                    }
                                    Rectangle {
                                        readonly property bool waiting: keyCard.capturingFor === modelData.id
                                        width: addText.implicitWidth + 16; height: 24; radius: 6
                                        color: waiting ? Theme.acc : "transparent"
                                        border.color: waiting ? Theme.acc : Theme.line
                                        Text { id: addText; anchors.centerIn: parent
                                               text: parent.waiting ? L.t.press_key : "+"
                                               color: parent.waiting ? Theme.inkOnAcc : Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 11 }
                                        MouseArea { anchors.fill: parent
                                                    onClicked: { keyCard.capturingFor = modelData.id; actions.startCapture() } }
                                    }
                                }
                                Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.line }
                            }
                        }
                    }
                }

                // 6. Screenshots (and advanced)
                Column {
                    id: p5; visible: sp.section === 5; width: parent.width; spacing: 10
                    Caption { text: L.t.c_shots }
                    Card {
                        SettingRow { title: L.t.s_folder; below: true; hint: app.screenshotDir
                                     Row { spacing: 6
                                           KeyCap { glyph: Theme.icChooseDir; glyphSize: 15; width: 30; height: 26; tip: L.t.choose_folder; onClicked: shotFolder.open() }
                                           KeyCap { glyph: Theme.icFolder; glyphSize: 15; width: 30; height: 26; tip: L.t.open_folder; onClicked: app.openScreenshotDir() } } }
                        SettingRow { title: L.t.s_format; below: true; hint: L.t.s_format_h
                                     Segmented { width: 220; value: sp.v.shotFormat
                                                 options: [{ value: "png", text: "PNG" }, { value: "jpg", text: "JPG" }]
                                                 onPicked: (x) => settings.set("shotFormat", x) } }
                        SettingRow { visible: sp.v.shotFormat === "jpg"; height: visible ? implicitHeight : 0
                                     title: L.t.s_jpg; hint: ""
                                     Stepper { value: sp.v.shotQuality; step: 5; from: 50; to: 100; suffix: " %"
                                               onChangedTo: (x) => settings.set("shotQuality", x) } }
                    }
                    Caption { text: L.t.edit_caps }
                    Card {
                        SettingRow { title: L.t.s_export; below: true
                                     hint: L.t.s_export_h
                                     Segmented { objectName: "setExportCodec"; width: 360; value: sp.v.exportCodec
                                                 options: [{ value: "copy", text: L.t.lossless }, { value: "h264", text: "H.264" }, { value: "h265", text: "H.265" }]
                                                 onPicked: (x) => settings.set("exportCodec", x) } }
                    }
                    Caption { text: L.t.c_advanced }
                    Card {
                        SettingRow { title: L.t.s_mpv; below: true
                                     hint: L.t.s_mpv_h
                                     Field { width: parent.width; multiline: true; text: sp.v.mpvOptions
                                             placeholder: "deband=yes\nscale=ewa_lanczossharp"
                                             onCommitted: (t) => settings.set("mpvOptions", t) } }
                    }
                }

                // 7. About
                Column {
                    id: p6; visible: sp.section === 6; width: parent.width; spacing: 10
                    Card { AboutPage { objectName: "aboutPage"; width: parent.width } }
                }
            }
        }
    }
    FolderDialog { id: shotFolder; title: L.t.d_shots
                   onAccepted: settings.set("shotDir", selectedFolder.toString().replace("file:///", "")) }
    FolderDialog { id: radioFolder; title: L.t.d_radio
                   onAccepted: settings.set("radioDir", decodeURIComponent(selectedFolder.toString().replace("file:///", ""))) }
    FolderDialog { id: recFolder; title: L.t.d_rec
                   onAccepted: settings.set("radioRecDir", decodeURIComponent(selectedFolder.toString().replace("file:///", ""))) }
}
