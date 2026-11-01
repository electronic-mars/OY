import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

// Main window: the Omega skin's layout (title bar, timeline with a time scale, one row of
// keys) in the default skin. The picture is drawn by mpv underneath this scene; the window
// only tells mpv how much of the height the title bar and panel keep clear.
Window {
    id: win
    width: 960; height: 620
    minimumWidth: 760; minimumHeight: 380
    visible: false   // shown from Python once placed on its screen
    color: "black"
    title: player.title !== "" ? player.title + " — OY Player" : "OY Player"
    flags: Qt.Window | Qt.FramelessWindowHint | (onTop ? Qt.WindowStaysOnTopHint : 0)
           | (app.selftest ? Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput : 0)

    // setting "onTop": never | always | while a file plays
    readonly property bool onTop: settings.values.onTop === "always"
                                  || (settings.values.onTop === "playing" && player.hasFile && !player.paused)
    Binding { target: Theme; property: "light"
              value: settings.values.theme === "light" || (settings.values.theme === "system" && app.systemLight) }
    Binding { target: Theme; property: "skin"; value: skins.look }
    // the one colour: the player's own (or the settings' dial while it turns); yellow while
    // editing, so the mode can be seen at a glance
    Binding { target: Theme; property: "accent"
              value: editor.active ? Theme.editYellow : (Theme.tuning !== "" ? Theme.tuning : settings.values.accent) }
    readonly property bool fs: visibility === Window.FullScreen
    readonly property int titleH: 32
    // editing, the panel is the editor's tracks (they grow by a track for each drawing overlapping
    // others) over its own row of keys, which stands in for the player's
    readonly property int stripH: editor.active ? 6 + timeline.height + 10 + editStrip.height + editFoot - (58 + Theme.keyPlay + deckFoot) : 0
    // the playing file's drawings for the timeline, as text: a new list only when a drawing
    // really changed, not on each position or choice, so a bar is not rebuilt under the
    // pointer (a hover, a double click)
    readonly property string playingPath: player.path
    readonly property string laneNotes: JSON.stringify(editor.active ? editor.notes.filter(n => n.path === playingPath) : [])
    property string drawTool: "select"          // the editor's drawing tool and ink
    property color drawInk: "#F26A21"
    property real drawSize: 1
    // the scale (44 and its margins), the keys (as tall as the play key) and the foot under them
    readonly property int deckFoot: Theme.tier === 2 ? 14 : 8
    readonly property int editFoot: Theme.tier === 2 ? 14 : 10
    readonly property int panelH: 58 + Theme.keyPlay + deckFoot + stripH
    // the keys' size step by the window's width: compact in the narrowest window, the concept's
    // full-size caps from 1400 px
    Binding { target: Theme; property: "tier"; value: win.width >= 1400 ? 2 : win.width >= 940 ? 1 : 0 }
    // the panel's side margin and the space between keys: the concept's 24 and 8, tighter in the
    // narrowest window, where every key must still fit
    readonly property int edge: Theme.tier ? 24 : 12
    property bool chromeAwake: true            // fullscreen: panels shown after a mouse move
    property real pointerY: -1                 // where the pointer is over the picture (full screen: the title bar)
    // a click on the picture (setting "leftClick" or "middleClick"): the title bar, the panel and
    // the list step aside, windowed or full screen, until the next such click (or Esc)
    property bool uiHidden: false
    // Going in or out of full screen the panels and the title bar step aside at the click and stay
    // away for the whole change: Windows grows the window in more than one step, and panels kept
    // until it was full size rode up the middle of the screen (the owner). The picture's layout
    // follows the window's real size, not Windows' «full screen» state (reported before or after
    // the size, by direction).
    property int fsPending: 0                            // 1 going full screen, -1 leaving it
    // (a window covering its monitor is 1 px taller than it: snap.py)
    readonly property bool fullSized: width >= screen.width && height >= screen.height
    readonly property bool fsLook: fsPending !== 0 ? fullSized : fs
    // The panels' fade is off for the whole change, switched before fsPending and back after it:
    // a Behavior's «enabled» bound to fsPending itself may update after the opacity it guards, and
    // then the panel faded out over the grown window (the owner's phone videos)
    property bool fsInstant: false
    // fsPending first: leaving, the panels come back in the very frame the window shrinks, not
    // fading in over a window that has already changed (the owner saw it as a second jerk)
    function fsSettled() { fsPending = 0; fsInstant = false }
    function fsCheck() {
        if ((fsPending > 0 && fs && fullSized) || (fsPending < 0 && !fs && !fullSized)) fsSettled()
    }
    Timer { id: fsSettle; interval: 1500; onTriggered: win.fsSettled() }   // a change that never came
    readonly property bool chromeShown: fsPending === 0 && (!fsLook || chromeAwake) && !uiHidden
    readonly property bool bare: fsLook || uiHidden    // the picture takes the whole window
    property bool playlistShown: false
    // The area the keyboard works in: "list" (the playlist, any tab), "strip" (the edit's
    // fragments) or "" (the commands). F6 / Shift+F6 or a click in an area gives it the keys;
    // its arrows, Home, End, Enter and Delete go to it before the commands (Actions' filter,
    // the same path as the open menu's keys). An area that goes away gives the keys back.
    property string area: ""
    onPlaylistShownChanged: if (!playlistShown && area === "list") area = ""
    onChromeShownChanged: {
        if (fs || fsPending || width >= screen.width)
            console.info("panels", chromeShown ? "shown" : "hidden", "fs", fs, "pending", fsPending, "size", width + "x" + height)
        if (!chromeShown && area === "list") area = ""
    }
    Connections { target: editor; function onChanged() { if (!editor.active && win.area === "strip") win.area = "" } }
    // a row holds its frame and a whole file name; one width whatever the window's (the window's
    // own width is set from it by Alt+1 and the fit to a picture)
    readonly property int playlistW: 350
    // windowed: the playlist takes its own column; fullscreen: it lies over the picture
    readonly property int sideW: playlistShown && !bare ? playlistW : 0

    function updateMargins() {
        if (bare) player.setVideoMargins(0, 0, 0)
        else player.setVideoMargins(titleH / height, panelH / height, sideW / width)
    }
    onHeightChanged: { fsCheck(); updateMargins() }
    onWidthChanged: { fsCheck(); updateMargins() }
    onSideWChanged: updateMargins()
    onPanelHChanged: updateMargins()
    onBareChanged: updateMargins()
    // full screen from the mouse (the middle button, a double click) opens on the bare picture;
    // from a key or the title bar the panels show for a moment, as they always did
    property bool quietFs: false
    property real quietUntil: 0                          // the window's own moves while it grows are no wake
    onFsChanged: {
        fsCheck()
        updateMargins()
        // leaving needs no wake: the window shows its panels anyway, and a wake while it is still
        // full size would show them there
        if (fs && quietFs) { sleepTimer.stop(); chromeAwake = false } else if (fs) wake()
        quietFs = false
    }
    onUiHiddenChanged: updateMargins()
    // the editor's panel is its work surface: it does not step aside
    Connections { target: editor; function onChanged() { if (editor.active) win.uiHidden = false } }
    function mouseAction(a) {
        if (a === "chrome" && !editor.active) uiHidden = !uiHidden
        else if (a === "chrome" || a === "pause") actions.run("play_pause")
        else if (a === "fullscreen") {
            quietFs = !fs
            if (quietFs) {
                chromeAwake = false; sleepTimer.stop(); quietUntil = Date.now() + 2000
                videoArea.restAt = videoArea.lastGlobal       // where the hand rests
            }
            actions.run("fullscreen")
        }
    }
    Component.onCompleted: updateMargins()

    function toggleFullscreen() {
        fsInstant = true
        fsPending = fs ? -1 : 1
        fsSettle.restart()
        updateMargins()
        curtain.cover(!fs)      // the screen held still until the window has its new frame (curtain.py)
        if (fs) showNormal(); else showFullScreen()
    }
    // one sign for «a menu or card is open»: Esc closes it first, the fullscreen panels stay
    // while it is open, and the hints of the keys under it keep quiet (Tip.qml)
    readonly property var menus: [subsMenu, speedMenu, audioMenu, pictureMenu, schedMenu, skipMenu]
    readonly property var popups: menus.concat([videoPanel, infoPanel, settingsPanel])
    readonly property bool menuOpen: menus.some(m => m.visible)        // it takes the arrows and Enter
    readonly property bool popupOpen: popups.some(p => p.visible)
    onPopupOpenChanged: wake()
    function wake() {
        if (Date.now() < quietUntil) return
        chromeAwake = true; sleepTimer.restart()
    }
    Timer {
        id: sleepTimer; interval: 2500
        onTriggered: if (win.fs && !win.popupOpen && !panelHover.hovered && !titleHover.hovered && !playlistHover.hovered)
                         win.chromeAwake = false
    }

    Connections {
        target: actions
        function onOpenFileRequested() { openDialog.open() }
        function onToggleFullscreenRequested() { win.toggleFullscreen() }
        function onOnTopToggled() { settings.set("onTop", settings.values.onTop === "never" ? "always" : "never") }
        function onMinimizeRequested() { win.showMinimized() }
        // Esc, one thing per press: an open menu or card, a countdown to sleep or shutdown,
        // fullscreen, the editor (the edit stays; Ctrl+E brings it back), and last the player.
        function onCloseRequested() {
            console.info("close requested: open", win.popups.filter(p => p.visible).map(p => p.objectName),
                         "fullscreen", win.fs)
            if (win.popupOpen) win.popups.forEach(p => p.close())
            else if (scheduler.countdown > 0) scheduler.abort()
            else if (win.uiHidden) win.uiHidden = false
            else if (win.fs) win.toggleFullscreen()
            else if (editor.active && win.drawTool !== "select") win.drawTool = "select"   // a drawing tool first
            else if (editor.active) editor.close()
            else win.close()
        }
        function onMenuKey(k) { win.menus.find(m => m.visible).navigate(k) }
        function onAreaKey(k) { (win.area === "list" ? playlistPanel : editStrip).navigate(k) }
        // a press anywhere else (the picture, the panel, a menu) gives the keys back to the commands;
        // the fragments' area is the editor's row and its tracks
        function onPressedAt(x, y) {
            var items = win.area === "list" ? [playlistPanel] : win.area === "strip" ? [editStrip, timeline] : []
            if (items.length && !items.some(it => it.contains(it.mapFromItem(null, x, y)))) win.area = ""
        }
        function onAreaRequested(step) {
            var all = [""]
            if (win.playlistShown && win.chromeShown) all.push("list")
            if (editor.active) all.push("strip")
            win.area = all[(all.indexOf(win.area) + step + all.length) % all.length]
        }
        function onScreenshotRequested() { player.screenshot(app.screenshotDir) }
        // P is the List: with History or Radio open it turns to the List rather than closing
        function onTogglePlaylistRequested() {
            if (win.playlistShown && playlistPanel.tab !== 0) playlistPanel.tab = 0
            else win.playlistShown = !win.playlistShown
        }
        function onAddFilesRequested() { addDialog.open() }
        function onAddFolderRequested() { folderDialog.open() }
        function onWindowScaleRequested(f) { win.scaleTo(f) }
        function onTechOsdToggled() { techOsd.visible = !techOsd.visible }
        function onVideoPanelToggled() { videoPanel.visible ? videoPanel.close() : videoPanel.open() }
        function onLoadSubtitlesRequested() { subsDialog.open() }
        function onSubtitleMenuRequested() { win.openSubsMenu() }
        function onScreenshotFolderRequested() { app.openScreenshotDir() }
        function onLoadAudioRequested() { audioDialog.open() }
        function onAudioMenuRequested() { win.openAudioMenu() }
        function onFileInfoRequested() { if (player.hasFile) infoPanel.open() }
        function onSettingsRequested() { settingsPanel.visible ? settingsPanel.close() : settingsPanel.open() }
        function onHistoryRequested() { win.showPage(1) }
        function onRadioRequested() { win.showPage(2) }
        function onSchedulerRequested() { win.openSchedMenu() }
    }
    // Ctrl+H and Ctrl+F2 open their page of the playlist panel, or close the panel on it
    function showPage(n) {
        if (playlistShown && playlistPanel.tab === n) playlistShown = false
        else { playlistPanel.tab = n; playlistShown = true }
    }

    // scheduler: pick what, then when; picking "when" sets it going
    function schedItems() {
        var acts = ["pause", "close", "sleep", "shutdown"]
        var it = [{ header: L.t.m_what }]
        for (var i = 0; i < acts.length; i++) {
            let a = acts[i], what = L.t["sch_" + a]
            it.push({ text: what.charAt(0).toUpperCase() + what.slice(1), checked: scheduler.action === a, keepOpen: true,
                      run: () => { scheduler.setAction(a); schedMenu.items = win.schedItems() } })
        }
        it.push({ separator: true }, { header: L.t.m_when },
                { text: L.t.m_after_file, checked: scheduler.when === "file", run: () => scheduler.arm("file", 0) },
                { text: L.t.m_after_list, checked: scheduler.when === "list", run: () => scheduler.arm("list", 0) })
        var mins = [[15, L.t.m_in15], [30, L.t.m_in30], [60, L.t.m_in60], [90, L.t.m_in90], [120, L.t.m_in120]]
        for (var m = 0; m < mins.length; m++) {
            let n = mins[m][0]
            it.push({ text: mins[m][1], run: () => scheduler.arm("timer", n) })
        }
        if (scheduler.when !== "")
            it.push({ separator: true }, { header: L.t.m_now }, { text: scheduler.summary, enabled: false },
                    { text: L.t.cancel, run: () => scheduler.cancel() })
        return it
    }
    // While editing the panel's keys are hidden: the scheduler and on top are in the title bar
    // (the owner chose it over the edit strip, 01.11), the menu drops down from there
    function openSchedMenu() {
        schedMenu.items = schedItems()
        if (!editor.active) return popMenu(schedMenu, clockKey)
        const p = titleClock.mapToItem(null, 0, titleClock.height + 6)
        popMenu(schedMenu, null, Qt.point(p.x, p.y))
    }

    // the opening and the credits, marked on the seek bar's right button (or by keys)
    function openSkipMenu() {
        skipMenu.items = [
            { header: L.t.m_skip },
            { text: L.t.m_open_start, enabled: player.hasFile, run: () => actions.run("skip_open_start") },
            { text: L.t.m_open_end, enabled: player.hasFile, run: () => actions.run("skip_open_end") },
            { text: L.t.m_credits, enabled: player.hasFile, run: () => actions.run("skip_credits") },
            { separator: true },
            { text: L.t.m_skip_on, checked: autoskip.on, run: () => actions.run("autoskip") },
            { text: L.t.m_forget, enabled: autoskip.marked, run: () => autoskip.forget() }]
        skipMenu.open()
    }

    // "Scale 50…200 %": the picture at that share of its own pixels, the window around it.
    // After a resize the window may hang past its monitor's edge: pull it back inside.
    function keepOnScreen() {
        var a = app.workArea(win)
        x = Math.max(a[0], Math.min(x, a[0] + a[2] - width))
        y = Math.max(a[1], Math.min(y, a[1] + a[3] - height))
    }
    function scaleTo(f, quiet) {
        if (!player.videoW || fs) return
        var a = app.workArea(win), dpr = a[4]
        if (visibility === Window.Maximized) showNormal()
        // never larger than the monitor's work area, whatever was asked for
        width = Math.min(a[2], Math.max(minimumWidth, Math.round(player.videoW * f / dpr) + sideW))
        height = Math.min(a[3], Math.max(minimumHeight, Math.round(player.videoH * f / dpr) + titleH + panelH))
        if (!quiet) player.osdMessage(L.t.osd_win_size.arg(Math.round(f * 100)))
    }

    function subsItems() {
        var it = [{ header: L.t.m_subs },
                  { text: L.t.off, checked: player.sid === false, run: () => player.setSid(-1) }]
        var tr = player.subTracks
        for (var i = 0; i < tr.length; i++) {
            let id = tr[i].id
            it.push({ text: tr[i].title + (tr[i].external ? L.t.external : ""), checked: player.sid === id,
                      run: () => player.setSid(id) })
        }
        it.push({ separator: true }, { header: L.t.m_subs2 },
                { text: L.t.off, checked: player.sid2 === false, run: () => player.setSid2(-1) })
        for (var j = 0; j < tr.length; j++) {
            let id2 = tr[j].id
            it.push({ text: tr[j].title, checked: player.sid2 === id2, run: () => player.setSid2(id2) })
        }
        it.push({ separator: true },
                { text: L.t.m_load_subs, run: () => subsDialog.open() },
                { text: L.t.m_sub_earlier, keepOpen: true, run: () => actions.run("sub_earlier") },
                { text: L.t.m_sub_later, keepOpen: true, run: () => actions.run("sub_later") },
                { text: L.t.m_sub_bigger, keepOpen: true, run: () => player.changeSubScale(0.1) },
                { text: L.t.m_sub_smaller, keepOpen: true, run: () => player.changeSubScale(-0.1) },
                { text: L.t.m_sub_copy, run: () => player.copySubtitle() })
        return it
    }
    // A menu opens over its key, or, when it comes from the picture's menu or its key is not on
    // the panel, where the picture was clicked (or in the picture's middle, from a key press)
    function popMenu(menu, key, at) {
        if (!at && (!key || !key.visible))
            at = Qt.point(videoArea.x + videoArea.width / 2 - 125, videoArea.y + videoArea.height / 2 - 120)
        if (at) {
            menu.parent = Overlay.overlay
            menu.x = Math.max(8, Math.min(at.x, win.width - menu.rowWidth - 20))
            menu.y = Math.max(8, Math.min(at.y, win.height - menu.implicitHeight - 8))
        } else {
            menu.parent = key
            menu.x = 0
            menu.y = Qt.binding(() => -menu.implicitHeight - 12)
        }
        menu.open()
    }
    // the subtitles have no key on the panel: S turns them on and off, Alt+S and the picture's
    // menu open this one
    function openSubsMenu(at) { subsMenu.items = subsItems(); popMenu(subsMenu, null, at) }
    function openPictureMenu(at) {
        pictureMenu.items = [
            { text: L.t.act_open_file + "…", icon: Theme.icFolder, keys: "F2", run: () => actions.run("open_file") },
            { separator: true },
            { text: L.t.cm_speed, icon: Theme.icFastForward, keys: "Ctrl+X", enabled: player.hasFile, run: () => win.openSpeedMenu(at) },
            { text: L.t.cm_subs, icon: Theme.icCaptions, keys: "Alt+S", enabled: player.hasFile, run: () => win.openSubsMenu(at) },
            { text: L.t.cm_sound, icon: Theme.icVolume, keys: "Alt+A", run: () => win.openAudioMenu(at) },
            { text: L.t.act_video_panel, icon: Theme.icVideo, keys: "Shift+V", enabled: player.hasFile, run: () => videoPanel.open() },
            { separator: true },
            { text: L.t.cm_shot, icon: Theme.icCamera, keys: "F12", enabled: player.hasFile, run: () => actions.run("screenshot") },
            { text: L.t.act_file_info, icon: Theme.icInfo, keys: "Alt+I", enabled: player.hasFile, run: () => actions.run("file_info") }]
        popMenu(pictureMenu, null, at)
    }
    function openAudioMenu(at) {
        var it = [{ header: L.t.m_audio }], tr = player.audioTracks
        for (var i = 0; i < tr.length; i++) {
            let id = tr[i].id
            it.push({ text: tr[i].title + (tr[i].external ? L.t.external : ""), checked: player.aid === id,
                      run: () => player.setAid(id) })
        }
        it.push({ text: L.t.m_load_audio, run: () => audioDialog.open() },
                { separator: true }, { header: L.t.m_processing })
        var modes = ["off", "norm", "loudnorm", "compressor", "leveler"]
        for (var m = 0; m < modes.length; m++) {
            let id2 = modes[m]
            it.push({ text: L.t["am_" + id2], checked: player.audioMode === id2, run: () => settings.set("audioMode", id2) })
        }
        it.push({ separator: true }, { header: L.t.m_device })
        var devs = player.audioDevices()
        for (var d = 0; d < devs.length; d++) {
            let name = devs[d].name
            it.push({ text: name === "auto" ? L.t.as_windows : devs[d].description,
                      checked: player.audioDevice === name, run: () => settings.set("audioDevice", name) })
        }
        it.push({ separator: true },
                { text: L.t.m_audio_earlier, keepOpen: true, run: () => actions.run("audio_earlier") },
                { text: L.t.m_audio_later, keepOpen: true, run: () => actions.run("audio_later") },
                { text: L.t.act_pitch_up, keepOpen: true, run: () => actions.run("pitch_up") },
                { text: L.t.act_pitch_down, keepOpen: true, run: () => actions.run("pitch_down") },
                { text: L.t.act_pitch_reset, run: () => actions.run("pitch_reset") })
        audioMenu.items = it
        popMenu(audioMenu, soundKey, at)
    }
    function openSpeedMenu(at) {
        var speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4], it = [{ header: L.t.m_speed }]
        for (var i = 0; i < speeds.length; i++) {
            let s = speeds[i]
            it.push({ text: String(s).replace(".", L.t.dec) + "×", checked: Math.abs(player.speed - s) < 0.001, run: () => player.setSpeed(s) })
        }
        speedMenu.items = it
        popMenu(speedMenu, ffKey, at)
    }
    Connections {
        target: player
        function onOsdMessage(text) { osd.show(text) }
    }

    FileDialog {
        id: openDialog
        title: L.t.act_open_file
        fileMode: FileDialog.OpenFiles
        nameFilters: win.mediaFilters
        onAccepted: playlist.add(selectedFiles, true)
    }
    readonly property var mediaFilters: [L.t.f_media + " (*.mkv *.mp4 *.avi *.mov *.wmv *.webm *.flv *.m4v *.ts *.m2ts *.mpg *.mpeg *.3gp *.ogv *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.wav *.wma *.lau)", L.t.f_all + " (*)"]
    FileDialog {
        id: addDialog
        title: L.t.d_add
        fileMode: FileDialog.OpenFiles
        nameFilters: win.mediaFilters
        onAccepted: playlist.add(selectedFiles, false)
    }
    FolderDialog {
        id: folderDialog
        title: L.t.d_add_folder
        onAccepted: playlist.add([selectedFolder], !player.hasFile)
    }
    FileDialog {
        id: subsDialog
        title: L.t.act_load_subtitles
        nameFilters: [L.t.f_subs + " (*.srt *.ass *.ssa *.sub *.idx *.vtt *.sup *.smi *.txt)", L.t.f_all + " (*)"]
        onAccepted: player.addSubtitle(selectedFile.toString())
    }
    FileDialog {
        id: audioDialog
        title: L.t.act_load_audio
        nameFilters: [L.t.f_sound + " (*.mka *.ac3 *.dts *.aac *.m4a *.mp3 *.flac *.opus *.ogg *.wav *.eac3 *.thd)", L.t.f_all + " (*)"]
        onAccepted: player.addAudio(selectedFile.toString())
    }
    FileDialog {
        id: editSaveDialog
        title: L.t.d_save_edit
        fileMode: FileDialog.SaveFile
        nameFilters: [L.t.f_video + " (*.mp4 *.mkv *.mov *.webm)", L.t.f_all + " (*)"]
        onAccepted: editor.exportTo(selectedFile.toString())
    }
    Connections {
        target: editor
        function onSaveRequested() {
            var url = "file:///" + editor.suggestedPath().replace(/\\/g, "/")
            editSaveDialog.currentFolder = url.substring(0, url.lastIndexOf("/"))
            editSaveDialog.selectedFile = url
            editSaveDialog.open()
        }
    }
    FileDialog {
        id: saveDialog
        title: L.t.d_save_list
        fileMode: FileDialog.SaveFile
        defaultSuffix: "m3u8"
        nameFilters: [L.t.f_playlist + " (*.m3u8)"]
        onAccepted: playlist.save(selectedFile.toString())
    }

    // ---------- the mouse's other buttons, anywhere in the window (the keys take only the left
    // and right ones): the middle one as set (full screen), back and forward seek or change the file
    Item {
        anchors.fill: parent
        TapHandler {
            objectName: "otherButtons"
            acceptedButtons: Qt.MiddleButton | Qt.BackButton | Qt.ForwardButton
            onTapped: (ev, button) => {
                if (button === Qt.MiddleButton) { win.mouseAction(settings.values.middleClick); return }
                var fwd = button === Qt.ForwardButton, side = settings.values.sideButtons
                if (side === "seek") actions.run(fwd ? "seek_forward" : "seek_backward")
                else if (side === "track") actions.run(fwd ? "next" : "prev")
            }
        }
    }

    // ---------- the video area: a click as set (hides the panels), drag moves the window,
    // double click = fullscreen
    MouseArea {
        id: videoArea
        anchors.fill: parent
        anchors.topMargin: win.bare ? 0 : win.titleH
        anchors.bottomMargin: win.bare ? 0 : win.panelH
        anchors.rightMargin: win.sideW
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: win.fs && !win.chromeAwake ? Qt.BlankCursor : Qt.ArrowCursor
        property point pressAt
        property bool moved: false
        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); moved = false }
        // the panels wake on a real move of the pointer, not on the window changing size under
        // a still pointer (going full screen sends a move of its own)
        // Full screen, a hand resting on the mouse (after the middle button, say) must not bring the
        // panels back: there they wake after a deliberate move, 24 px from where the pointer rested
        property point lastGlobal
        property point restAt
        onPositionChanged: (m) => {
            var g = mapToGlobal(m.x, m.y)
            win.pointerY = m.y + y
            var far = win.fsLook ? Math.abs(g.x - restAt.x) + Math.abs(g.y - restAt.y) > 24
                                 : Math.abs(g.x - lastGlobal.x) + Math.abs(g.y - lastGlobal.y) > 2
            // while the window grows (the quiet second) its moves only say where the hand rests
            if (Date.now() < win.quietUntil) restAt = g
            else if (far) { win.wake(); restAt = g }
            lastGlobal = g
            if (pressed && !moved && !win.fs
                    && Math.abs(m.x - pressAt.x) + Math.abs(m.y - pressAt.y) > 6) {
                moved = true
                win.startSystemMove()
            }
        }
        // a pause answers at once (a double click undoes it); hiding the panels waits out a
        // double click, so a double click does not flash them away and back
        readonly property string click: settings.values.leftClick === "chrome" && editor.active ? "pause" : settings.values.leftClick
        onClicked: (m) => {
            if (moved) return
            if (m.button === Qt.RightButton) { win.openPictureMenu(Qt.point(m.x + x, m.y + y)); return }
            if (!player.hasFile) { actions.run("open_file"); return }      // the empty window: a click opens
            if (click === "pause") actions.run("play_pause")
            else if (click === "chrome") clickTimer.restart()
        }
        Timer { id: clickTimer; interval: Qt.styleHints.mouseDoubleClickInterval; onTriggered: win.mouseAction("chrome") }
        onDoubleClicked: (m) => {
            if (m.button !== Qt.LeftButton || !player.hasFile) return
            clickTimer.stop()
            var dc = settings.values.doubleClick
            if (dc === "none") return
            if (click === "pause") actions.run("play_pause")
            if (dc === "pause") actions.run("play_pause")
            else win.mouseAction("fullscreen")
        }
        onWheel: (w) => {
            var up = w.angleDelta.y > 0, seekWheel = settings.values.wheel === "seek"
            if (w.modifiers & Qt.ControlModifier) actions.run(up ? "zoom_in" : "zoom_out")
            else if ((w.modifiers & Qt.AltModifier) ? !seekWheel : seekWheel) actions.run(up ? "seek_forward" : "seek_backward")
            else actions.run(up ? "volume_up" : "volume_down")
        }
    }

    // a picture dropped on the frame while editing is a logo; anything else goes to the list
    readonly property var imageExts: ["png", "jpg", "jpeg", "webp", "bmp", "gif"]
    DropArea {
        anchors.fill: parent
        onDropped: (d) => {
            if (!d.hasUrls) return
            var u = d.urls[0].toString(), ext = u.substring(u.lastIndexOf(".") + 1).toLowerCase()
            if (editor.active && win.imageExts.indexOf(ext) >= 0) editor.addImage(u)
            else playlist.add(d.urls, true)
        }
    }
    FileDialog {
        id: imageDialog
        title: L.t.d_image
        nameFilters: [L.t.f_images + " (*.png *.jpg *.jpeg *.webp *.bmp *.gif)", L.t.f_all + " (*)"]
        onAccepted: editor.addImage(selectedFile.toString())
    }

    // ---------- the editor's drawings, exactly over the picture (mpv reports where it is,
    // in render pixels, with zoom and the panel margins already applied)
    NoteLayer {
        id: noteLayer
        objectName: "noteLayer"
        // not "osd": an id of that name (the OSD text) would win over the property
        readonly property var dims: player.osd
        readonly property real k: dims.w ? dims.w / win.width : 1
        visible: editor.active && player.hasFile && dims.w > 0
        x: visible ? dims.ml / k : 0
        y: visible ? dims.mt / k : 0
        width: visible ? (dims.w - dims.ml - dims.mr) / k : 0
        height: visible ? (dims.h - dims.mt - dims.mb) / k : 0
        tool: win.drawTool
        ink: win.drawInk
        size: win.drawSize
        lit: timeline.lit
        topClear: drawBar.visible ? drawBar.y + drawBar.height - y : 0
    }

    // ---------- empty state
    // a film over the name, and F2 drawn as the key it is (Gemini's empty state)
    Column {
        visible: !player.hasFile
        anchors.centerIn: videoArea
        spacing: 10
        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "film"; size: 32; stroke: 1.5; color: Theme.tx3; opacity: .6
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "OY PLAYER"
            color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 22; font.letterSpacing: 8
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 7
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: L.t.drop_hint
                color: Theme.tx3; opacity: .7; font.family: Theme.uiFont; font.pixelSize: 13
            }
            Rectangle {
                objectName: "dropKey"
                anchors.verticalCenter: parent.verticalCenter
                width: f2.implicitWidth + 12; height: 20; radius: 4
                color: Theme.capTop; border.color: Theme.lineHi
                Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 2; radius: 4
                            color: Theme.capShadow }
                Text { id: f2; anchors.centerIn: parent; anchors.verticalCenterOffset: -1; text: "F2"
                       color: Theme.tx2; font.family: Theme.monoFont; font.pixelSize: 11; font.weight: Font.DemiBold }
            }
        }
    }

    // ---------- sound without a picture (the radio, a music file): what is playing, instead of black
    Column {
        objectName: "soundOnly"
        visible: player.hasFile && player.tracks.length > 0 && !player.tracks.some(t => t.type === "video")
        anchors.centerIn: videoArea
        width: Math.min(560, videoArea.width - 60)
        spacing: 10
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: radio.streaming ? (radio.recording ? L.t.radio_rec_caps : L.t.radio_caps) : L.t.sound_caps
            color: radio.recording ? Theme.accText : Theme.tx3
            font.family: Theme.uiFont; font.pixelSize: 12; font.letterSpacing: 6
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
            text: radio.nowPlaying !== "" ? radio.nowPlaying : player.title
            color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 24
        }
    }

    // ---------- OSD
    // a message stays as long as it takes to read: 1.4 s up to about 30 letters, about 5 s for an
    // error that says what to do; it wraps instead of running off the window, and lies over
    // the drawing bar (z 5) that would otherwise hide it in the editor
    Text {
        id: osd
        objectName: "osd"
        x: 18; y: (win.bare ? 0 : win.titleH) + 14 + (editor.active && win.chromeShown ? 44 : 0)   // under the tool card
        z: 6
        width: win.width - 36
        wrapMode: Text.WordWrap
        color: "white"; style: Text.Outline; styleColor: "black"
        font.family: Theme.uiFont; font.pixelSize: 20
        opacity: 0
        function show(t) {
            text = t; opacity = 1
            osdTimer.interval = Math.max(1400, Math.min(7000, (t.length - 10) * 50))
            osdTimer.restart()
        }
        Timer { id: osdTimer; interval: 1400; onTriggered: osd.opacity = 0 }
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    DrawBar {
        id: drawBar
        objectName: "drawBar"
        z: 5        // its hints rise over the title bar
        visible: editor.active && win.chromeShown
        // centred over the picture (the window, while the picture is not known); a skin may put
        // it in the picture's upper left corner instead (Theme.drawCentred)
        readonly property int inset: Theme.tier === 2 ? 16 : 8
        x: Theme.drawCentred ? (noteLayer.visible ? noteLayer.x + (noteLayer.width - width) / 2 : (videoArea.width - width) / 2)
                             : (noteLayer.visible ? noteLayer.x : 0) + inset
        y: (noteLayer.visible ? noteLayer.y : win.bare ? 0 : win.titleH) + inset
        tool: win.drawTool
        ink: win.drawInk
        size: win.drawSize
        onSizePicked: (v) => {
            win.drawSize = v
            if (editor.noteSel >= 0 && editor.notes[editor.noteSel].kind !== "image") editor.setNoteSize(editor.noteSel, v)
        }
        onToolPicked: (t) => win.drawTool = t
        onImageRequested: imageDialog.open()
        onInkPicked: (c) => {
            win.drawInk = c
            if (editor.noteSel >= 0) editor.setNoteColor(editor.noteSel, c.toString())
        }
    }

    // ---------- technical OSD (Q)
    Rectangle {
        id: techOsd
        objectName: "techOsd"
        visible: false
        x: 14; y: (win.bare ? 0 : win.titleH) + 48
        width: techText.implicitWidth + 20; height: techText.implicitHeight + 14
        radius: 8; color: Qt.rgba(0, 0, 0, .6)
        Text {
            id: techText
            x: 10; y: 7
            color: "#E9ECF1"; font.family: "Consolas"; font.pixelSize: 12; lineHeight: 1.15
        }
        Timer { interval: 500; repeat: true; triggeredOnStart: true; running: techOsd.visible
                onTriggered: techText.text = player.techInfo() }
    }

    // ---------- title bar (the editor's badge | the title | minimise, maximise, close)
    Rectangle {
        id: titleBar
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: win.titleH
        color: Theme.title
        // full screen: the window's keys only when the pointer goes up to them (they read as
        // marks in the picture's corner otherwise)
        opacity: win.chromeShown && (!win.fsLook || win.pointerY < 64 || titleHover.hovered) ? 1 : 0
        visible: opacity > 0
        // going full screen the panels vanish at once, not while the window grows
        Behavior on opacity { enabled: !win.fsInstant; NumberAnimation { duration: 180 } }
        Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.line }
        HoverHandler { id: titleHover }
        DragHandler {
            target: null
            onActiveChanged: if (active && !win.fs) win.startSystemMove()
        }
        TapHandler { onDoubleTapped: win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized() }

        Row {
            anchors { left: parent.left; leftMargin: 6; verticalCenter: parent.verticalCenter }
            spacing: 2
            IconButton { id: titleClock; objectName: "titleScheduler"; visible: editor.active
                         glyph: Theme.icClock; latched: scheduler.when !== ""
                         tip: scheduler.when !== "" ? scheduler.summary : L.t.t_scheduler
                         onClicked: win.openSchedMenu() }
            IconButton { objectName: "titleOnTop"; visible: editor.active
                         glyph: win.onTop ? Theme.icPinned : Theme.icPin; latched: win.onTop
                         tip: L.t.t_on_top; onClicked: actions.run("on_top") }
            // editing: the mode says itself in the title bar, in its yellow (the concept)
            Rectangle {
                objectName: "editBadge"
                visible: editor.active
                anchors.verticalCenter: parent.verticalCenter
                width: badgeText.implicitWidth + 30; height: 18; radius: 4
                color: badgeArea.containsMouse ? Theme.accHi : Theme.acc
                Text { id: badgeText; x: 7; anchors.verticalCenter: parent.verticalCenter; text: L.t.edit_caps; color: Theme.inkOnAcc
                       font.family: Theme.uiFont; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.4 }
                // where the mode is named, it is left: a click on the badge closes the editor
                Icon { anchors { right: parent.right; rightMargin: 5; verticalCenter: parent.verticalCenter }
                       name: Theme.icClose; size: 11; stroke: 2.2; color: Theme.inkOnAcc }
                MouseArea { id: badgeArea; anchors.fill: parent; hoverEnabled: true; onClicked: editor.close() }
                Tip { text: L.t.es_close_tip; shown: badgeArea.containsMouse; under: true }
            }
        }
        Text {
            id: windowTitleText
            objectName: "windowTitle"
            anchors.centerIn: parent
            width: parent.width - 260
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideMiddle
            text: player.title !== "" ? player.title : "OY Player"
            color: Theme.tx3
            // a name to read, not to spell out: 12 px, letters barely apart
            font.family: Theme.uiFont; font.pixelSize: 12; font.letterSpacing: .2
            font.capitalization: player.title !== "" ? Font.MixedCase : Font.AllUppercase
        }
        // editing: the picture's size and frame rate beside the name (Argon's v1, 01.11)
        Rectangle {
            objectName: "titleFormat"
            // where the name leaves it the room before the playlist key
            visible: editor.active && player.videoW > 0 && x + width + 8 <= winKeys.x
            x: windowTitleText.x + (windowTitleText.width + windowTitleText.contentWidth) / 2 + 8
            anchors.verticalCenter: parent.verticalCenter
            width: formatText.implicitWidth + 12; height: 17; radius: 4
            color: Theme.panelHi; border.color: Theme.lineHi
            Text {
                id: formatText
                anchors.centerIn: parent
                text: player.videoW + "×" + player.videoH + (player.fps > 0 ? " • " + Math.round(player.fps) + "fps" : "")
                color: Theme.tx2; font.family: Theme.monoFont; font.pixelSize: 10
            }
        }
        // the window's own keys as wide as Windows' (46 px), the bar's full height
        Row {
            id: winKeys
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            // editing: the panel's playlist key is hidden, the playlist opens from here
            Rectangle {
                objectName: "titlePlaylist"
                visible: editor.active
                anchors.verticalCenter: parent.verticalCenter
                width: plRow.width + 16; height: 24; radius: 6
                color: plArea.containsMouse ? Theme.card : "transparent"
                border.color: plArea.containsMouse ? Theme.line : "transparent"
                Row {
                    id: plRow
                    anchors.centerIn: parent
                    spacing: 6
                    Icon { anchors.verticalCenter: parent.verticalCenter; name: Theme.icList; size: 14
                           color: win.playlistShown ? Theme.accText : plArea.containsMouse ? Theme.tx : Theme.tx3 }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: L.t.tl_playlist
                           color: win.playlistShown ? Theme.accText : plArea.containsMouse ? Theme.tx : Theme.tx2
                           font.family: Theme.uiFont; font.pixelSize: 12 }
                    Rectangle {
                        visible: playlist.count > 0
                        anchors.verticalCenter: parent.verticalCenter
                        width: plCount.implicitWidth + 8; height: 15; radius: 3; color: Theme.panelHi
                        Text { id: plCount; anchors.centerIn: parent; text: playlist.count
                               color: Theme.tx2; font.family: Theme.monoFont; font.pixelSize: 10 }
                    }
                }
                MouseArea { id: plArea; anchors.fill: parent; hoverEnabled: true; onClicked: actions.run("playlist") }
                Tip { text: L.t.t_playlist; shown: plArea.containsMouse; under: true }
            }
            Item { visible: editor.active; width: 6; height: 1 }
            IconButton { width: 46; height: win.titleH; radius: 0
                         glyph: Theme.icMin; tip: L.t.t_minimize; onClicked: actions.run("minimize") }
            // Windows 11 shows its Snap Layouts on this key (snap.py answers the hit test)
            IconButton { width: 46; height: win.titleH; radius: 0
                         objectName: "keyMax"; glyph: win.visibility === Window.Maximized || win.fs ? Theme.icRestore : Theme.icMax
                         tip: win.fs ? L.t.t_window : win.visibility === Window.Maximized ? L.t.t_restore : L.t.t_maximize
                         onClicked: win.fs ? win.toggleFullscreen() : (win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized()) }
            IconButton { width: 46; height: win.titleH; radius: 0
                         glyph: Theme.icClose; danger: true; tip: L.t.t_close; onClicked: win.close() }
        }
    }

    // ---------- playlist (right column; over the picture in fullscreen)
    PlaylistPanel {
        id: playlistPanel
        objectName: "playlistPanel"
        visible: win.playlistShown && win.chromeShown
        anchors { right: parent.right; top: titleBar.bottom; bottom: panel.top }
        width: win.playlistW
        focused: win.area === "list"
        onPicked: win.area = "list"
        onAddFiles: actions.run("add_files")
        onSaveRequested: saveDialog.open()
        HoverHandler { id: playlistHover }
    }

    // ---------- control panel
    Rectangle {
        id: panel
        objectName: "panel"
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: win.panelH
        opacity: win.chromeShown ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { enabled: !win.fsInstant; NumberAnimation { duration: 180 } }
        color: Theme.deck
        Rectangle { anchors { left: parent.left; right: parent.right; top: parent.top } height: 1; color: Theme.rule }
        Rectangle { anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 1 } height: 1
                    color: Qt.rgba(1, 1, 1, Theme.light ? .7 : .04) }
        HoverHandler { id: panelHover }

        Timeline {
            id: timeline
            objectName: "timeline"
            anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: win.edge + (Theme.tier ? 0 : 2); rightMargin: win.edge + (Theme.tier ? 0 : 2); topMargin: 6 }
            position: player.position
            duration: player.duration
            chapters: player.chapters
            loopA: player.loopA
            loopB: player.loopB
            previewOn: settings.values.preview && player.hasFile && player.path.indexOf("://") < 0
            previewSource: preview.path === player.path ? preview.source : ""
            onHoverAt: (s) => preview.request(player.path, s)
            // through playingPath: the editor's lists follow the playing file, which it does not signal
            bands: editor.active && win.playingPath !== "" ? editor.bands : []
            elsewhere: editor.active && win.playingPath !== "" ? editor.elsewhere : []
            onElsewherePicked: (row) => editor.select(row)
            editing: editor.active
            fragSel: editor.selected
            fragInfo: editor.active ? editor.fragments : []
            fragFocus: win.area === "strip"
            onFragPicked: (row) => { editor.select(row); win.area = "strip" }
            noteLane: editor.active
            notes: JSON.parse(win.laneNotes)
            noteSel: editor.noteSel
            noteHot: noteLayer.hot
            onNotePicked: (i) => editor.selectNote(i)
            onNoteRanges: (r) => editor.setNoteRanges(r)
            // while dragging: the nearest keyframe, fast; the exact frame on release
            onSeekTo: (s, final) => player.scrub(s, final)
            skips: autoskip.bands
            onMenuRequested: win.openSkipMenu()
            onWheelStep: (a) => actions.run(a)
            PanelMenu { id: skipMenu; objectName: "skipMenu"; x: 40; y: -implicitHeight - 10; margins: 8 }
        }

        EditStrip {
            id: editStrip
            objectName: "editStrip"
            visible: editor.active
            focused: win.area === "strip"
            onPicked: win.area = "strip"
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: win.edge; rightMargin: win.edge; bottomMargin: win.editFoot }
        }

        Item {
            id: keys
            objectName: "panelKeys"
            visible: !editor.active             // editing, the editor's own row stands here
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: win.edge; rightMargin: win.edge; bottomMargin: win.deckFoot }
            height: Theme.keyPlay
            // one step between every two things on the panel, whatever they are (the owner: gaps that
            // jump about read as disorder); the order is the concept's: settings, the transport, the
            // sound, the time, the screenshot and the editor; the navigation on the right
            readonly property int step: [8, 10, 12][Theme.tier]
            readonly property color wellColour: Qt.tint(Theme.deck, Theme.sunk)     // the sunk tone, opaque

            // the wells the keys sit in (Theme.wellStyle). The transport's (the default, Gemini's first
            // concept): one sunk groove from the play key to the editor's, the play key at its round
            // head in a dark ring; the deck's: the play key and the speed key sunk together, as the
            // keys under the screen of Master Audio Switcher
            Rectangle {
                objectName: "transportWell"
                visible: Theme.wellStyle === "transport"
                x: leftKeys.x + playKey.x + playKey.width / 2; y: (parent.height - height) / 2
                width: editKey.x + editKey.width + 6 - playKey.x - playKey.width / 2; height: Theme.keyH + 10
                radius: Theme.keyRadius + 4
                color: keys.wellColour
                border.color: Theme.line
            }
            // solid, so that it hides the groove's edge; no hairline: round the key it read as an
            // outline (the owner)
            Rectangle {
                visible: Theme.wellStyle === "transport"
                x: leftKeys.x + playKey.x - 4; y: leftKeys.y + playKey.y - 4
                width: playKey.width + 8; height: width; radius: width / 2
                color: keys.wellColour
            }
            Rectangle {
                visible: Theme.wellStyle === "deck"
                x: leftKeys.x + playKey.x - 5; y: leftKeys.y + playKey.y - 5
                width: ffKey.x + ffKey.width - playKey.x + 10; height: playKey.height + 10
                radius: Theme.keyRadius + 4
                color: Theme.sunk
                border.color: Theme.line
            }
            Row {
                id: leftKeys
                anchors.verticalCenter: parent.verticalCenter
                spacing: keys.step
                // on the left (the default skin, the owner's choice), or by the list's key (a skin: Theme.settingsRight)
                SettingsKey { onRight: false }
                // nothing loaded: mpv is not paused then, but the key offers to play (the list, or
                // a file); a file to open on its right button (the open key is gone: F2 too)
                PlayKey { id: playKey; objectName: "keyPlay"
                          anchors.verticalCenter: parent.verticalCenter
                          playing: player.hasFile && !player.paused
                          name: (player.paused || !player.hasFile ? L.t.t_play : L.t.t_pause).replace(/\s*\([^)]*\)/g, "")
                          tip: (player.paused || !player.hasFile ? L.t.t_play : L.t.t_pause) + L.t.t_open_menu
                          onClicked: actions.run("play_pause")
                          onRightClicked: actions.run("open_file") }
                KeyCap { id: ffKey; objectName: "keyFast"; enabled: player.hasFile
                         glyph: Theme.icFastForward; latched: player.speed > 1.001
                         second: true; held: speedMenu.visible
                         onRightClicked: win.openSpeedMenu()
                         tip: (player.speed > 1.001 ? L.t.t_speed.arg(String(player.speed).replace(".", L.t.dec)) : L.t.t_fast)
                              + L.t.t_speed_menu
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("fast_play") }
                KeyCap { id: soundKey; objectName: "keySound"
                         second: true; held: audioMenu.visible
                         onRightClicked: win.openAudioMenu()
                         glyph: player.muted ? Theme.icMute : Theme.icVolume; latched: player.muted
                         tip: (player.muted ? L.t.t_unmute : L.t.t_mute) + L.t.t_sound_menu
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("mute")
                         WheelHandler { onWheel: (w) => actions.run(w.angleDelta.y > 0 ? "volume_up" : "volume_down") } }
                Knob {
                    objectName: "volumeKnob"
                    visible: Theme.volumeStyle === "knob"
                    anchors.verticalCenter: parent.verticalCenter
                    value: player.volume / 100
                    name: L.t.volume
                    valueText: Math.round(player.volume) + "%"
                    onMoved: (v) => player.setVolume(v * 100)
                    WheelHandler { onWheel: (w) => actions.run(w.angleDelta.y > 0 ? "volume_up" : "volume_down") }
                }
                Rail {
                    id: volume
                    objectName: "volume"
                    visible: Theme.volumeStyle === "rail"
                    width: Theme.tier ? 88 : 84; height: 16; grooveHeight: 4; capWidth: 8
                    anchors.verticalCenter: parent.verticalCenter
                    value: player.volume / 100
                    accent: false               // the accent is the play key and the position only
                    name: L.t.volume
                    valueText: Math.round(player.volume) + " %"
                    onMoved: (v) => player.setVolume(v * 100)
                    Tip { text: Math.round(player.volume) + "%"; shown: volume.hovered || volume.dragging }
                    WheelHandler { onWheel: (w) => actions.run(w.angleDelta.y > 0 ? "volume_up" : "volume_down") }
                }
                LcdTime {
                    id: lcdTime
                    objectName: "lcdTime"
                    anchors.verticalCenter: parent.verticalCenter
                    position: player.position
                    duration: player.duration
                    speed: player.hasFile ? player.speed : 1
                    onSpeedReset: player.setSpeed(1)
                }
                KeyCap { objectName: "keyShot"; glyph: Theme.icCamera; tip: L.t.t_shot
                         second: true
                         enabled: player.hasFile; anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("screenshot")
                         onRightClicked: actions.run("screenshot_clipboard") }
                KeyCap { id: editKey; objectName: "keyEdit"; glyph: Theme.icCut; latched: editor.active
                         enabled: player.hasFile || editor.active
                         tip: L.t.t_edit
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("edit_mode") }
            }

            // the settings key, where the skin puts it: one of the two shows, and has the name
            component SettingsKey: KeyCap {
                property bool onRight
                visible: Theme.settingsRight === onRight
                objectName: visible ? "keySettings" : ""
                glyph: Theme.icSettings; tip: L.t.t_settings
                latched: settingsPanel.visible
                anchors.verticalCenter: parent.verticalCenter
                onClicked: actions.run("settings")
            }
            SettingsKey {
                onRight: true
                anchors { right: rightKeys.left; rightMargin: keys.step * 2; verticalCenter: parent.verticalCenter }
            }
            Row {
                id: rightKeys
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: keys.step
                // the scheduler and on top, keys of the panel in every skin (they were marks in the
                // title bar), apart from the list's keys
                KeyCap { id: clockKey; objectName: "keyScheduler"; glyph: Theme.icClock; latched: scheduler.when !== ""
                         held: schedMenu.visible
                         tip: scheduler.when !== "" ? scheduler.summary : L.t.t_scheduler
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: win.openSchedMenu()
                         PanelMenu { id: schedMenu; objectName: "schedMenu"; y: -implicitHeight - 10; margins: 8 } }
                KeyCap { objectName: "keyOnTop"; glyph: win.onTop ? Theme.icPinned : Theme.icPin; latched: win.onTop
                         tip: L.t.t_on_top
                         anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("on_top") }
                Item { width: keys.step; height: 1 }
                // previous and next: only with more than one file in the list (PageUp, PageDown, the
                // media keys and the mouse's side buttons do it always)
                KeyCap { id: prevKey; objectName: "keyPrev"; glyph: Theme.icPrev; tip: L.t.t_prev
                         visible: playlist.count > 1; anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("prev") }
                // the list open: the round key stays pressed in, its sign in the accent (the concept)
                KeyCap { id: listKey; objectName: "keyPlaylist"; round: true; glyph: Theme.icList; latched: win.playlistShown
                         chosen: win.playlistShown
                         tip: L.t.t_playlist; onClicked: actions.run("playlist") }
                KeyCap { id: nextKey; objectName: "keyNext"; glyph: Theme.icNext; tip: L.t.t_next
                         visible: playlist.count > 1; anchors.verticalCenter: parent.verticalCenter
                         onClicked: actions.run("next") }
            }
        }
    }

    PanelMenu { id: subsMenu; objectName: "subsMenu"; margins: 8 }
    PanelMenu { id: speedMenu; objectName: "speedMenu"; margins: 8 }
    PanelMenu { id: audioMenu; objectName: "audioMenu"; margins: 8 }
    // the picture's right button: everything that left the panel, within one click
    PanelMenu { id: pictureMenu; objectName: "pictureMenu"; margins: 8 }
    // the picture card stands over the deck in the window's middle (its key left the panel:
    // Shift+V and the picture's menu open it)
    VideoPanel { id: videoPanel; objectName: "videoPanel"; parent: Overlay.overlay; margins: 8
                 x: (win.width - width) / 2
                 y: win.height - (win.bare ? 0 : win.panelH) - height - 12 }
    InfoPanel { id: infoPanel; objectName: "infoPanel"; parent: Overlay.overlay }
    SettingsPanel { id: settingsPanel; objectName: "settingsPanel"; parent: Overlay.overlay }

    // sleep or shutdown is coming (scheduler, or the setting for the end of the list):
    // the time left, and the way out (the button or Esc)
    Rectangle {
        id: powerBanner
        objectName: "powerBanner"
        visible: scheduler.countdown > 0
        z: 10
        anchors.horizontalCenter: videoArea.horizontalCenter
        y: (win.bare ? 0 : win.titleH) + 54
        width: bannerRow.implicitWidth + 32; height: 52; radius: 12
        color: Theme.card; border.color: Theme.acc
        Rectangle { anchors.fill: parent; anchors.margins: -1; z: -1; radius: 13; color: Qt.rgba(0, 0, 0, .35) }
        Row {
            id: bannerRow
            anchors.centerIn: parent
            spacing: 16
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: (scheduler.pending === "shutdown" ? L.t.cd_shutdown : L.t.cd_sleep).arg(scheduler.countdown)
                color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 15
            }
            PillButton { objectName: "powerCancel"; anchors.verticalCenter: parent.verticalCenter
                         text: L.t.cd_cancel; accent: true; onClicked: scheduler.abort() }
        }
    }

    // setting "fitWindow": a new file sizes the window to its picture,
    // shrunk to fit the screen's work area.
    Connections {
        target: player
        function onChanged() {
            // both sides of the new picture must be known: dwidth arrives before dheight
            if (player.videoW > 0 && player.videoH > 0 && player.hasFile && player.path !== win.fittedPath) {
                win.fittedPath = player.path
                // While editing, fragments of different files follow each other: the window
                // must not jump to each file's size.
                if (settings.values.fitWindow && !win.fs && win.visibility !== Window.Maximized && !editor.active) {
                    var area = app.workArea(win), dpr = area[4]
                    var fits = Math.min((area[2] - 40 - win.sideW) * dpr / player.videoW,
                                        (area[3] - 40 - win.titleH - win.panelH) * dpr / player.videoH)
                    // its own size, but no narrower than the window can be: a small picture grows to
                    // the window's least width, edge to edge with the panel, instead of standing
                    // between black bars (as long as it fits the screen)
                    var f = Math.min(fits, Math.max(1, (win.minimumWidth - win.sideW) * dpr / player.videoW))
                    win.scaleTo(f, true)
                    win.keepOnScreen()
                    console.info("fit", player.videoW + "x" + player.videoH, "area", area, "f", f.toFixed(3),
                                 "window", win.width + "x" + win.height, "at", win.x + "," + win.y)
                }
            }
        }
    }
    property string fittedPath: ""

    // ---------- frameless window: resize from the edges
    Repeater {
        model: [
            { e: Qt.LeftEdge, x: 0, y: 6, w: 5, h: -12, c: Qt.SizeHorCursor },
            { e: Qt.RightEdge, x: -5, y: 6, w: 5, h: -12, c: Qt.SizeHorCursor },
            { e: Qt.TopEdge, x: 6, y: 0, w: -12, h: 4, c: Qt.SizeVerCursor },
            { e: Qt.BottomEdge, x: 6, y: -4, w: -12, h: 4, c: Qt.SizeVerCursor },
            { e: Qt.TopEdge | Qt.LeftEdge, x: 0, y: 0, w: 8, h: 8, c: Qt.SizeFDiagCursor },
            { e: Qt.TopEdge | Qt.RightEdge, x: -8, y: 0, w: 8, h: 8, c: Qt.SizeBDiagCursor },
            { e: Qt.BottomEdge | Qt.LeftEdge, x: 0, y: -8, w: 8, h: 8, c: Qt.SizeBDiagCursor },
            { e: Qt.BottomEdge | Qt.RightEdge, x: -8, y: -8, w: 8, h: 8, c: Qt.SizeFDiagCursor }
        ]
        MouseArea {
            visible: !win.fs && win.visibility !== Window.Maximized
            x: modelData.x < 0 ? win.width + modelData.x : modelData.x
            y: modelData.y < 0 ? win.height + modelData.y : modelData.y
            width: modelData.w <= 0 ? win.width + modelData.w : modelData.w
            height: modelData.h <= 0 ? win.height + modelData.h : modelData.h
            cursorShape: modelData.c
            onPressed: win.startSystemResize(modelData.e)
        }
    }
}
