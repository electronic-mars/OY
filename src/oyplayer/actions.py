"""Every user command has one name and one owner: buttons, keys and the self-test all
call Actions.run(name), so a gesture can never reach a command by two paths.

Keys are matched by Windows virtual-key code, not by the character typed, so they
work the same under any layout, Cyrillic too (S stays S).
"""
from PySide6.QtCore import Property, QEvent, QObject, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .i18n import tr
from .log import log
from .player import (AUDIO_DELAY_STEP, COLOR_STEP, PAN_STEP, PITCH_STEP, SUB_DELAY_STEP,
                     ZOOM_STEP)

SEEK_STEP = 5.0
JUMP_STEP = 30.0
VOLUME_STEP = 5.0

# key string -> action. Modifier order is canonical: Ctrl+Alt+Shift+Key.
DEFAULT_KEYS = {
    "F2": "open_file",
    "Space": "play_pause",
    "Alt+V": "stop",
    "Ctrl+X": "fast_play",
    "Right": "seek_forward", "Left": "seek_backward",
    "Shift+Right": "jump_forward", "Shift+Left": "jump_backward",
    "Ctrl+Right": "frame_forward", "Ctrl+Left": "frame_backward",
    "BkSp": "rewind",
    "Up": "volume_up", "Down": "volume_down",
    "M": "mute",
    "S": "subtitles",
    "Enter": "fullscreen",
    "F12": "screenshot",
    "A": "on_top",
    "End": "minimize",
    "Esc": "close",
    "PageDown": "next", "PageUp": "prev",
    "P": "playlist",
    "Insert": "add_files", "Shift+Insert": "add_folder",
    "Delete": "remove_selected", "Shift+Delete": "clear_playlist",
    "Ctrl+Up": "move_up", "Ctrl+Down": "move_down",
    "Ctrl+Home": "sort",
    "R": "repeat", "Shift+R": "repeat_file",
    "Ctrl+Enter": "play_selected",
    # picture
    "Shift+`": "aspect_default", "Shift+1": "aspect_16_9", "Shift+2": "aspect_4_3",
    "Shift+3": "aspect_fill", "Shift+4": "aspect_fill", "Shift+5": "aspect_235", "NP.": "aspect_cycle",
    "=": "zoom_in", "-": "zoom_out", "Alt+`": "reset_geometry",
    "NP4": "pan_left", "NP6": "pan_right", "NP8": "pan_up", "NP2": "pan_down",
    "Shift+NP+": "brightness_up", "Shift+NP-": "brightness_down",
    "Ctrl+NP+": "contrast_up", "Ctrl+NP-": "contrast_down",
    "Alt+NP+": "saturation_up", "Alt+NP-": "saturation_down", "NP*": "reset_colors",
    "Alt+1": "scale_50", "Alt+2": "scale_100", "Alt+3": "scale_150", "Alt+4": "scale_200",
    "Home": "scale_100",
    "Q": "tech_osd", "Shift+V": "video_panel",
    "Ctrl+F12": "screenshot_clipboard", "Ctrl+S": "screenshot_folder",
    # subtitles
    "Shift+S": "load_subtitles", "Shift+/": "cycle_subtitles", "Alt+S": "subtitle_menu",
    "Alt+Right": "sub_later", "Alt+Left": "sub_earlier",
    "Ctrl+,": "sub_slower", "Ctrl+.": "sub_faster",
    # sound
    "Shift+A": "load_audio", "/": "cycle_audio", "Alt+A": "audio_menu",
    "NP-": "audio_earlier", "NP+": "audio_later",
    "Alt+I": "file_info",
    "F10": "settings",
    "L": "resume",
    "\\": "ab_loop",
    # the editor (new in OY Player; LosslessCut's I and O)
    "Ctrl+E": "edit_mode", "I": "mark_in", "O": "mark_out", "X": "cut_out",
    "Shift+Space": "edit_preview", "Ctrl+Shift+S": "edit_save",
    # the editor's drawings: through those on the frame; [ and ] are a drawing's I and O
    "Tab": "note_next", "Shift+Tab": "note_prev", "[": "note_in", "]": "note_out",
    # the keyboard's area: the playlist, the edit strip, the commands (Windows' pane key; Tab
    # belongs to the drawings)
    "F6": "area_next", "Shift+F6": "area_prev",
    "Ctrl+Z": "edit_undo", "Ctrl+Y": "edit_redo",
    # skipping openings and credits: O and E belong to the editor, so the opening's start is Alt+E
    "Alt+E": "skip_open_start", "Shift+E": "skip_open_end", "Shift+O": "skip_credits",
    "Alt+O": "autoskip",
    "Ctrl+H": "history", "Ctrl+F2": "radio", "Shift+T": "scheduler",
    # a keyboard's media keys, while the player has the focus (everywhere: setting)
    "MediaPlay": "play_pause", "MediaNext": "next", "MediaPrev": "prev", "MediaStop": "stop",
}

# What the key editor shows, in the order a person looks for things (titles: i18n act_*).
BINDABLE = (
    "play_pause", "stop", "open_file", "seek_forward", "seek_backward", "jump_forward",
    "jump_backward", "frame_forward", "frame_backward", "rewind", "fast_play", "volume_up",
    "volume_down", "mute", "fullscreen", "minimize", "on_top", "close", "settings", "next", "prev",
    "playlist", "add_files", "add_folder", "remove_selected", "playlist_remove", "clear_playlist",
    "move_up", "move_down", "sort", "repeat", "repeat_file", "shuffle", "play_selected",
    "screenshot", "screenshot_clipboard", "screenshot_folder", "video_panel", "tech_osd",
    "file_info", "aspect_default", "aspect_16_9", "aspect_4_3", "aspect_235", "aspect_fill",
    "aspect_cycle", "zoom_in", "zoom_out", "reset_geometry", "pan_left", "pan_right", "pan_up",
    "pan_down", "brightness_up", "brightness_down", "contrast_up", "contrast_down", "saturation_up",
    "saturation_down", "reset_colors", "scale_50", "scale_100", "scale_150", "scale_200",
    "subtitles", "cycle_subtitles", "load_subtitles", "subtitle_menu", "sub_later", "sub_earlier",
    "sub_slower", "sub_faster", "cycle_audio", "load_audio", "audio_menu", "audio_earlier",
    "audio_later", "pitch_up", "pitch_down", "pitch_reset", "resume", "ab_loop", "edit_mode",
    "mark_in", "mark_out", "cut_out", "edit_whole", "edit_preview", "edit_save", "edit_save_as",
    "area_next", "area_prev", "note_next", "note_prev", "note_in", "note_out", "edit_undo",
    "edit_redo", "skip_open_start", "skip_open_end", "skip_credits", "autoskip", "history", "radio",
    "radio_record", "scheduler",
)

# Held keys repeat these; everything else fires once per press.
_REPEATABLE = {"seek_forward", "seek_backward", "volume_up", "volume_down", "edit_undo", "edit_redo",
               "frame_forward", "frame_backward", "zoom_in", "zoom_out",
               "pan_left", "pan_right", "pan_up", "pan_down",
               "brightness_up", "brightness_down", "contrast_up", "contrast_down",
               "saturation_up", "saturation_down", "sub_later", "sub_earlier",
               "audio_earlier", "audio_later"}

# Keys an open menu takes (its highlight, Enter runs the item); ← and → do nothing there, so
# nothing changes under the menu either.
_MENU_KEYS = {0x26: "up", 0x28: "down", 0x24: "home", 0x23: "end", 0x0D: "enter", 0x25: "", 0x27: ""}
# what an area with the keyboard takes before the commands (Main's `area`): a list goes up and
# down, the edit strip left and right; the other keys stay commands (← → seek over the list)
_AREA_KEYS = {
    "list": {0x26: "up", 0x28: "down", 0x24: "home", 0x23: "end", 0x0D: "enter", 0x2E: "delete"},
    "strip": {0x25: "left", 0x27: "right", 0x24: "home", 0x23: "end", 0x0D: "enter", 0x2E: "delete"},
}

_VK_NAMES = {0x20: "Space", 0x0D: "Enter", 0x1B: "Esc", 0x08: "BkSp", 0x09: "Tab",
             0x21: "PageUp", 0x22: "PageDown", 0x23: "End", 0x24: "Home",
             0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
             0x2D: "Insert", 0x2E: "Delete",
             0x6A: "NP*", 0x6B: "NP+", 0x6D: "NP-", 0x6E: "NP.", 0x6F: "NP/",
             0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
             0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}
_VK_NAMES.update({0x30 + i: str(i) for i in range(10)})
_VK_NAMES.update({0x41 + i: chr(0x41 + i) for i in range(26)})
_VK_NAMES.update({0x60 + i: f"NP{i}" for i in range(10)})
_VK_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(12)})
_VK_NAMES.update({0xB0: "MediaNext", 0xB1: "MediaPrev", 0xB2: "MediaStop", 0xB3: "MediaPlay"})


def key_name(vk, mods):
    name = _VK_NAMES.get(vk)
    if name is None:
        return None
    prefix = ""
    if mods & Qt.ControlModifier:
        prefix += "Ctrl+"
    if mods & Qt.AltModifier:
        prefix += "Alt+"
    if mods & Qt.ShiftModifier:
        prefix += "Shift+"
    return prefix + name


class Actions(QObject):
    openFileRequested = Signal()
    addFilesRequested = Signal()
    addFolderRequested = Signal()
    togglePlaylistRequested = Signal()
    windowScaleRequested = Signal(float)
    techOsdToggled = Signal()
    videoPanelToggled = Signal()
    loadSubtitlesRequested = Signal()
    subtitleMenuRequested = Signal()
    screenshotFolderRequested = Signal()
    loadAudioRequested = Signal()
    audioMenuRequested = Signal()
    fileInfoRequested = Signal()
    toggleFullscreenRequested = Signal()
    onTopToggled = Signal()
    minimizeRequested = Signal()
    closeRequested = Signal()
    screenshotRequested = Signal()
    performed = Signal(str)    # for the self-test and the log
    menuKey = Signal(str)      # up | down | home | end | enter, for the open menu
    areaKey = Signal(str)      # up | down | left | right | home | end | enter | delete, for the area
    areaRequested = Signal(int)    # F6 / Shift+F6: the next or previous area takes the keys
    pressedAt = Signal(float, float)   # a mouse press in the window (scene x, y): outside the area it ends it
    keyCaptured = Signal(str)
    keysChanged = Signal()
    settingsRequested = Signal()
    historyRequested = Signal()
    radioRequested = Signal()
    schedulerRequested = Signal()

    def __init__(self, player, playlist, editor, autoskip, radio):
        super().__init__()
        self.p = player
        self.pl = playlist
        self.ed = editor
        self.keys = dict(DEFAULT_KEYS)
        self.seek_step, self.jump_step = SEEK_STEP, JUMP_STEP
        self.capturing = False
        self._keys_version = 0
        self.window = None    # set once QML has created it; window state is read from it
        self._table = {
            "open_file": self.openFileRequested.emit,
            "play_pause": self._play_pause,
            "stop": self._stop,
            "fast_play": player.cycleFastPlay,
            "seek_forward": lambda: player.seekRelative(self.seek_step),
            "seek_backward": lambda: player.seekRelative(-self.seek_step),
            "jump_forward": lambda: player.seekRelative(self.jump_step),
            "jump_backward": lambda: player.seekRelative(-self.jump_step),
            "frame_forward": player.frameStep,
            "frame_backward": player.frameBackStep,
            "rewind": lambda: player.seek(0.0),
            "volume_up": lambda: player.changeVolume(VOLUME_STEP),
            "volume_down": lambda: player.changeVolume(-VOLUME_STEP),
            "mute": player.toggleMute,
            "subtitles": player.toggleSubs,
            "fullscreen": self.toggleFullscreenRequested.emit,
            "screenshot": self.screenshotRequested.emit,
            "on_top": self.onTopToggled.emit,
            "minimize": self.minimizeRequested.emit,
            "close": self._close,
            "next": playlist.next,
            "prev": playlist.prev,
            "playlist": self.togglePlaylistRequested.emit,
            "add_files": self.addFilesRequested.emit,
            "add_folder": self.addFolderRequested.emit,
            # with the editor open, Delete takes out the chosen fragment or drawing, not a
            # playlist row; the playlist's own «−» always takes out its row
            "remove_selected": lambda: editor.removeSelected() if editor.active
                                       else playlist.remove(playlist.selected),
            "playlist_remove": lambda: playlist.remove(playlist.selected),
            "clear_playlist": playlist.clear,
            "move_up": lambda: self._move(-1),
            "move_down": lambda: self._move(+1),
            "sort": playlist.sortByName,
            "repeat": playlist.cycleRepeat,
            "repeat_file": playlist.toggleRepeatFile,
            "shuffle": playlist.toggleShuffle,
            "play_selected": lambda: playlist.playIndex(playlist.selected),
            "aspect_default": lambda: player.setAspect("-1"),
            "aspect_16_9": lambda: player.setAspect("16:9"),
            "aspect_4_3": lambda: player.setAspect("4:3"),
            "aspect_235": lambda: player.setAspect("2.35:1"),
            "aspect_fill": lambda: player.setAspect("fill"),
            "aspect_cycle": player.cycleAspect,
            "zoom_in": lambda: player.changeZoom(ZOOM_STEP),
            "zoom_out": lambda: player.changeZoom(-ZOOM_STEP),
            "reset_geometry": player.resetGeometry,
            "pan_left": lambda: player.pan(-PAN_STEP, 0), "pan_right": lambda: player.pan(PAN_STEP, 0),
            "pan_up": lambda: player.pan(0, -PAN_STEP), "pan_down": lambda: player.pan(0, PAN_STEP),
            "brightness_up": lambda: player.changeColor("brightness", COLOR_STEP),
            "brightness_down": lambda: player.changeColor("brightness", -COLOR_STEP),
            "contrast_up": lambda: player.changeColor("contrast", COLOR_STEP),
            "contrast_down": lambda: player.changeColor("contrast", -COLOR_STEP),
            "saturation_up": lambda: player.changeColor("saturation", COLOR_STEP),
            "saturation_down": lambda: player.changeColor("saturation", -COLOR_STEP),
            "reset_colors": player.resetColors,
            "scale_50": lambda: self.windowScaleRequested.emit(0.5),
            "scale_100": lambda: self.windowScaleRequested.emit(1.0),
            "scale_150": lambda: self.windowScaleRequested.emit(1.5),
            "scale_200": lambda: self.windowScaleRequested.emit(2.0),
            "tech_osd": self.techOsdToggled.emit,
            "video_panel": self.videoPanelToggled.emit,
            "screenshot_clipboard": player.screenshotToClipboard,
            "screenshot_folder": self.screenshotFolderRequested.emit,
            "load_subtitles": self.loadSubtitlesRequested.emit,
            "cycle_subtitles": player.cycleSub,
            "subtitle_menu": self.subtitleMenuRequested.emit,
            "sub_later": lambda: player.changeSubDelay(SUB_DELAY_STEP),
            "sub_earlier": lambda: player.changeSubDelay(-SUB_DELAY_STEP),
            "sub_slower": lambda: player.changeSubSpeed(0.99),
            "sub_faster": lambda: player.changeSubSpeed(1.01),
            "load_audio": self.loadAudioRequested.emit,
            "cycle_audio": player.cycleAudio,
            "audio_menu": self.audioMenuRequested.emit,
            "audio_earlier": lambda: player.changeAudioDelay(-AUDIO_DELAY_STEP),
            "audio_later": lambda: player.changeAudioDelay(AUDIO_DELAY_STEP),
            "pitch_up": lambda: player.changePitch(PITCH_STEP),
            "pitch_down": lambda: player.changePitch(1 / PITCH_STEP),
            "pitch_reset": player.resetPitch,
            "file_info": self.fileInfoRequested.emit,
            "settings": self.settingsRequested.emit,
            "resume": player.resumePosition,
            "ab_loop": player.abLoop,
            "edit_mode": editor.toggle,
            "mark_in": editor.setIn,
            "mark_out": editor.setOut,
            "cut_out": editor.cutOut,
            "edit_whole": editor.addWhole,
            "edit_preview": editor.togglePreview,
            "edit_save": editor.saveHere,
            "edit_save_as": editor.requestSave,
            "area_next": lambda: self.areaRequested.emit(1),
            "area_prev": lambda: self.areaRequested.emit(-1),
            "note_next": lambda: editor.cycleNote(1),
            "note_prev": lambda: editor.cycleNote(-1),
            "note_in": lambda: editor.setNoteEnd("a"),
            "note_out": lambda: editor.setNoteEnd("b"),
            "edit_undo": editor.undo,
            "edit_redo": editor.redo,
            "skip_open_start": autoskip.markOpeningStart,
            "skip_open_end": autoskip.markOpeningEnd,
            "skip_credits": autoskip.markCredits,
            "autoskip": autoskip.toggle,
            "history": self.historyRequested.emit,
            "radio": self.radioRequested.emit,
            "radio_record": radio.toggleRecording,
            "scheduler": self.schedulerRequested.emit,
        }

    def _play_pause(self):
        # Nothing loaded: continue the list where it was left, or ask for a file. Right after a
        # click on a fragment of the edit, the edit plays from that fragment on.
        if self.p.hasFile:
            if not (self.ed.active and self.ed.playCued()):
                self.p.togglePause()
        elif self.pl.count:
            self.pl.playIndex(max(0, self.pl.current))
        else:
            self.openFileRequested.emit()

    def _move(self, delta):
        row = self.pl.selected
        self.pl.move(row, delta)
        if 0 <= row + delta < self.pl.count:
            self.pl.selected = row + delta

    def _stop(self):
        # pause and return to the beginning, the file stays loaded
        self.p.mpv.pause = True
        self.p.seek(0.0)

    def _close(self):
        # Esc closes the player. The window knows what has to go first (an open menu or
        # card, fullscreen, the editor) and closes one thing per press.
        self.closeRequested.emit()

    @Slot(str)
    def run(self, name):
        fn = self._table.get(name)
        if fn is None:
            log.warning("unknown action %s", name)
            return
        log.info("action %s", name)
        try:
            fn()
        except Exception:
            # One failing command must not take the keyboard with it: an exception
            # escaping eventFilter aborts the rest of the input being processed.
            log.exception("action %s failed", name)
            return
        self.performed.emit(name)

    # ---- configuration (settings) and the key editor
    def configure(self, overrides, seek_step, jump_step):
        """overrides: key -> action; an empty action removes that default binding."""
        self.keys = dict(DEFAULT_KEYS)
        for k, a in overrides.items():
            if a:
                self.keys[k] = a
            else:
                self.keys.pop(k, None)
        self.seek_step, self.jump_step = float(seek_step), float(jump_step)
        self._keys_version += 1
        self.keysChanged.emit()

    @Property(int, notify=keysChanged)
    def keysVersion(self):
        """Bumps on every rebinding, so QML bindings over keysFor() re-evaluate."""
        return self._keys_version

    @Slot(str, result=bool)
    def isDefaultKey(self, key):
        return key in DEFAULT_KEYS

    @Slot(str, result=str)
    def actionFor(self, key):
        action = self.keys.get(key, "")
        return tr("act_" + action) if action in BINDABLE else ""

    @Slot(str, result="QStringList")
    def keysFor(self, action):
        return sorted(k for k, a in self.keys.items() if a == action)

    @Slot(result="QVariantList")
    def bindable(self):
        return [{"id": a, "title": tr("act_" + a)} for a in BINDABLE]

    @Slot()
    def startCapture(self):
        self.capturing = True

    @Slot()
    def stopCapture(self):
        self.capturing = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            self.pressedAt.emit(event.position().x(), event.position().y())
            return False
        if event.type() != QEvent.KeyPress:
            return False
        if self.capturing:
            # The key editor asked for the next key: report it instead of acting on it.
            # Bare modifiers are not a key on their own.
            if event.nativeVirtualKey() in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                return True
            if event.nativeVirtualKey() == 0x1B:     # Esc cancels, it is not bound
                self.capturing = False
                self.keyCaptured.emit("")
                return True
            name = key_name(event.nativeVirtualKey(), event.modifiers())
            if name:
                self.capturing = False
                self.keyCaptured.emit(name)
            return True
        # Typing in a text field (settings, editor captions) is text, not commands. The
        # field is asked of the window the key came to: QGuiApplication.focusObject() only
        # knows the active window, and a self-test window is never active.
        focus = obj.activeFocusItem() if hasattr(obj, "activeFocusItem") else QGuiApplication.focusObject()
        if focus is not None and focus.metaObject().className() in ("QQuickTextEdit", "QQuickTextInput"):
            return False
        if self.window is not None and self.window.property("menuOpen"):
            nav = _MENU_KEYS.get(event.nativeVirtualKey())
            if nav is not None:
                if nav:
                    self.menuKey.emit(nav)
                return True
        area = self.window.property("area") if self.window is not None else ""
        # the fragments on the clip track: Ctrl+Shift+← → move the chosen one in the edit's order
        mods = event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier)
        if area == "strip" and mods == Qt.ShiftModifier | Qt.ControlModifier and event.nativeVirtualKey() in (0x25, 0x27):
            self.areaKey.emit("earlier" if event.nativeVirtualKey() == 0x25 else "later")
            return True
        if area and not mods:
            nav = _AREA_KEYS.get(area, {}).get(event.nativeVirtualKey())
            if nav:
                self.areaKey.emit(nav)
                return True
        name = self.keys.get(key_name(event.nativeVirtualKey(), event.modifiers()))
        if name is None:
            return False
        if not event.isAutoRepeat() or name in _REPEATABLE:
            self.run(name)
        return True
