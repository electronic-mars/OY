pragma Singleton
import QtQuick

// Braun: graphite body, a single accent, recessed controls.
// Values transcribed from Master Audio Switcher (MAS/src/mas/ui/app.css) so the two
// programs read as one family; the light theme is the cream body.
QtObject {
    property bool light: false

    // The one colour (setting "accent", orange by default; the editor's yellow while editing),
    // set from Main. Its shades keep the old orange's lightness steps in OKLCH, so any choice
    // reads as the same rubber and the default gives back #F57A38, #FF8442 and #D2561A.
    property color accent: accentDefault
    readonly property string accentDefault: "#F26A21"
    readonly property string editYellow: "#F2C230"
    property string tuning: ""          // the settings' dial while it is being turned
    readonly property var accLch: lch(accent)
    readonly property color acc: accent
    readonly property color accTop:  shade(.028)    // an accent key's top
    readonly property color accHi:   shade(.058)    // ... under the pointer; where a fill starts
    readonly property color accDeep: shade(-.077)   // pressed in
    readonly property color inkOnAcc: "#1C1F24"         // the concept's accent ink, on any accent
    // on the cream body the accent itself is too pale for glyphs and words (orange 2.6:1,
    // the editor's yellow 1.3:1): there they take its hue at OKLCH L 0.50 at most, 4.5:1 and up
    readonly property color accText: light ? oklch(Math.min(.5, accLch[0]), accLch[1], accLch[2]) : acc
    function accA(a) { return Qt.rgba(acc.r, acc.g, acc.b, a) }
    function shade(dL) { return oklch(accLch[0] + dL, accLch[1] * .92, accLch[2]) }

    // OKLCH (Björn Ottosson): [L, C, h] of a colour, and the colour of [L, C, h] with its
    // chroma reduced until it fits sRGB
    function lch(c) {
        function lin(v) { return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
        var r = lin(c.r), g = lin(c.g), b = lin(c.b)
        var l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
        var m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
        var s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
        var A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
        var B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
        return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, Math.sqrt(A * A + B * B),
                (Math.atan2(B, A) * 180 / Math.PI + 360) % 360]
    }
    function oklch(L, C, h) {
        function enc(v) { v = Math.max(0, Math.min(1, v)); return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055 }
        var a = h * Math.PI / 180, rgb
        for (C = Math.max(0, C); ; C -= 0.004) {
            var A = C * Math.cos(a), B = C * Math.sin(a)
            var l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3)
            var m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3)
            var s = Math.pow(L - 0.0894841775 * A - 1.2914855480 * B, 3)
            rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                   -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                   -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]
            if (C <= 0 || rgb.every(v => v > -0.0005 && v < 1.0005)) break
        }
        return Qt.rgba(enc(rgb[0]), enc(rgb[1]), enc(rgb[2]), 1)
    }

    // The Braun concept (docs/screens/master/concept): a graphite or warm cream body, rubber
    // caps a step lighter than it, warm grey signs, one accent.
    readonly property color bg:       light ? "#E4DED0" : "#1C1F24"
    readonly property color panelHi:  light ? "#E9E3D6" : "#22252A"
    readonly property color card:     light ? "#F3EFE6" : "#191C21"
    readonly property color line:     light ? Qt.rgba(0, 0, 0, .10) : Qt.rgba(1, 1, 1, .065)
    readonly property color lineHi:   light ? Qt.rgba(0, 0, 0, .17) : Qt.rgba(1, 1, 1, .12)
    // warm greys, as the concept's ink, each as light as the cool one it replaces (the contrasts stay)
    readonly property color tx:       light ? "#2B2D31" : "#E8E5DE"
    readonly property color tx2:      light ? "#5F5B54" : "#A29E96"
    readonly property color tx3:      light ? "#625D55" : "#8F8B83"
    readonly property color deck:     light ? "#DCD5C5" : "#202328"     // the control deck and the list's pane
    readonly property color title:    light ? "#EAE5D9" : "#17191D"
    readonly property color rule:     light ? "#C8C0AF" : "#2E333A"     // a group's hairline
    readonly property color sunk:    light ? Qt.rgba(0, 0, 0, .13) : Qt.rgba(0, 0, 0, .45)
    readonly property color groove:   light ? "#B9B09F" : "#111316"
    readonly property color grooveEdge: light ? Qt.rgba(1, 1, 1, .55) : Qt.rgba(1, 1, 1, .06)
    // the scale's labels and ticks, the volume's fill: a warm grey a step under the signs
    readonly property color inkDim:   light ? "#847E73" : "#7F7C76"
    readonly property color well:     light ? "#D6CEBE" : "#17191D"     // a list sunk into the body
    // Key caps: bevel on top, shadow below, like rubber keys on a remote.
    readonly property color capTop:   light ? "#F6F2EA" : "#30343A"
    readonly property color capBot:   light ? "#EAE4D8" : "#282B31"
    readonly property color capHiTop: light ? "#FFFFFF" : "#383C43"
    readonly property color capHiBot: light ? "#F1ECE2" : "#2D3137"
    readonly property color capDnTop: light ? "#EAE4D8" : "#282B31"
    readonly property color capDnBot: light ? "#F6F2EA" : "#30343A"
    readonly property color glyph:    light ? "#2B2D31" : "#C9C6BF"
    // LCD glass: pale grey-green with near-black segments; unlit segments show faintly.
    // The same glass sits in the cream body, in a darker bezel.
    readonly property color lcdHi:    "#A9B2A3"
    readonly property color lcd:      "#9FA89A"
    readonly property color lcdLo:    "#96A091"
    readonly property color lcdInk:   "#1E2420"
    readonly property color lcdBezel: light ? "#6E685D" : "#0E1012"

    readonly property string uiFont: "Segoe UI Variable Text"
    readonly property string monoFont: "IBM Plex Mono"        // fonts/, loaded by __main__

    // The panel's keys come in three sizes by the window's width (Main sets `tier`): the narrow
    // window (760 px) keeps the old compact caps, a wide one gets the concept's 40 × 36 caps.
    property int tier: 1
    readonly property int keyW: [30, 36, 40][tier]
    readonly property int keyH: [28, 32, 36][tier]
    readonly property int keyRound: 40
    readonly property int keyPlay: [40, 46, 52][tier]
    readonly property int keyRadius: [6, 7, 8][tier]
    readonly property int keyIcon: [16, 17, 18][tier]
    readonly property int keyIconRound: 18
    readonly property color capShadow: light ? "#B3AA98" : "#0F1114"

    // Lucide signs by name (icons.py draws them); play and pause are filled figures
    readonly property string icPlay: "play"
    readonly property string icPause: "pause"
    readonly property string icFastForward: "fast-forward"
    readonly property string icFrame: "step-forward"
    readonly property string icEject: "eject"
    readonly property string icCaptions: "captions"
    readonly property string icVolume: "volume-2"
    readonly property string icMute: "volume-x"
    readonly property string icCamera: "camera"
    readonly property string icVideo: "video"
    readonly property string icSettings: "settings"
    readonly property string icPrev: "skip-back"
    readonly property string icNext: "skip-forward"
    readonly property string icList: "list-video"
    readonly property string icInfo: "info"
    readonly property string icClock: "clock"
    readonly property string icPin: "pin"
    readonly property string icPinned: "pin"
    // the editor
    readonly property string icCut: "scissors"
    readonly property string icWhole: "scan"
    readonly property string icPreview: "eye"
    readonly property string icSave: "save"
    readonly property string icCancel: "x"
    readonly property string icFolder: "folder-open"
    readonly property string icChooseDir: "folder"
    readonly property string icDelete: "trash-2"
    readonly property string icSelect: "mouse-pointer-2"
    readonly property string icText: "type"
    readonly property string icArrow: "move-up-right"
    readonly property string icRect: "square"
    readonly property string icPen: "pencil"
    // the playlist and the settings
    readonly property string icAdd: "plus"
    readonly property string icRemove: "minus"
    readonly property string icRepeat: "repeat"
    readonly property string icRepeatOne: "repeat-1"
    readonly property string icShuffle: "shuffle"
    readonly property string icRecord: "circle-dot"
    readonly property string icRotateLeft: "rotate-ccw"
    readonly property string icRotateRight: "rotate-cw"
    readonly property string icWindow: "app-window"
    readonly property string icKeyboard: "keyboard"
    // the window
    readonly property string icMin: "minus"
    readonly property string icMax: "square"
    readonly property string icRestore: "copy"
    readonly property string icClose: "x"
}
