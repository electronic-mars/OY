import QtQuick

// Position / duration in an LCD window: pale grey-green glass, near-black seven-segment
// figures leaning a little, and the faint shadow of the unlit segments behind them, which is
// what gives a real LCD away. Click switches between elapsed and remaining time.
// The format is the scale's: 01:15 / 01:30, hours only for a file of an hour or more; the
// length is smaller; with nothing loaded, --:--. The same glass sits in the cream body.
Rectangle {
    id: lcd
    property real position: 0
    property real duration: 0
    property bool remaining: false
    property bool fine: false           // the editor's: the position to the hundredth, no length
    property real speed: 1              // not 1: «×1,5» after the length; a click on it goes back to 1×
    signal speedReset()
    readonly property bool fast: Math.abs(speed - 1) > 0.001 && !fine
    readonly property string tip: L.t.lcd_tip

    readonly property bool hours: duration >= 3600
    function fmt(s) {
        s = Math.max(0, Math.floor(s))
        var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60
        var two = (n) => (n < 10 ? "0" : "") + n
        return (hours ? h + ":" : "") + two(m) + ":" + two(sec)
    }
    readonly property string now: duration > 0 ? (remaining ? "-" : "") + fmt(remaining ? duration - position : position) : "--:--"
    readonly property string total: duration > 0 ? fmt(duration) : "--:--"
    readonly property string hundredths: "." + String(Math.floor(position * 100) % 100).padStart(2, "0")
    readonly property string text: fine ? now + hundredths : now + " / " + total

    // the figures: the position as tall as half the window, the length two thirds of that
    readonly property int big: Math.round(height * .54)
    readonly property int small: Math.round(big * .66)

    width: figures.width + (Theme.tier ? 24 : 14)     // the narrowest window: every pixel counts
    height: Theme.keyH
    radius: 5
    border.color: Theme.lcdBezel
    gradient: Gradient {
        GradientStop { position: 0; color: Theme.lcdHi }
        GradientStop { position: .5; color: Theme.lcd }
        GradientStop { position: 1; color: Theme.lcdLo }
    }
    // recessed: inner shadow at the top, a hairline of light at the bottom
    Rectangle {
        x: 1; y: 1; width: parent.width - 2; height: 5; radius: 3
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(0, 0, 0, .3) }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Rectangle { x: 3; width: parent.width - 6; y: parent.height - 2; height: 1; color: Qt.rgba(1, 1, 1, .25) }

    // Seven segments on a canvas: a, b, c, d, e, f, g as on a calculator; ":" "." "/" "-" too.
    // Every digit place shows all seven segments faintly; the lit ones are full ink.
    component Segments: Canvas {
        id: seg
        property string text: ""
        property int h: 16
        readonly property real w: h * .56
        readonly property real t: h * .14
        readonly property real lean: Math.tan(7 * Math.PI / 180)
        readonly property var lit: ({ "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
                                      "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g" })
        function advance(ch) {
            return ch in lit ? w + h * .2 : ch === ":" ? t + h * .24 : ch === "." ? t + h * .2 : ch === "/" ? w * .7 + h * .25 : h * .3
        }
        width: Math.ceil(text.split("").reduce((a, ch) => a + advance(ch), 0) + h * lean)
        height: h
        onTextChanged: requestPaint()
        onHChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"), g = t * .2, x = 0
            c.reset()
            c.setTransform(1, 0, -lean, 1, h * lean, 0)
            c.fillStyle = Theme.lcdInk
            function poly(pts, on) {
                c.globalAlpha = on ? 1 : .08
                c.beginPath()
                c.moveTo(pts[0][0], pts[0][1])
                for (var i = 1; i < pts.length; i++) c.lineTo(pts[i][0], pts[i][1])
                c.closePath()
                c.fill()
            }
            for (var k = 0; k < text.length; k++) {
                var ch = text[k]
                if (ch in lit) {
                    var hs = (y) => [[x + g + t / 2, y], [x + g + t, y - t / 2], [x + w - g - t, y - t / 2], [x + w - g - t / 2, y],
                                     [x + w - g - t, y + t / 2], [x + g + t, y + t / 2]]
                    var vs = (cx, y1, y2) => [[cx, y1 + g], [cx + t / 2, y1 + g + t / 2], [cx + t / 2, y2 - g - t / 2], [cx, y2 - g],
                                              [cx - t / 2, y2 - g - t / 2], [cx - t / 2, y1 + g + t / 2]]
                    var s = { a: hs(t / 2), g: hs(h / 2), d: hs(h - t / 2), b: vs(x + w - t / 2, t / 2, h / 2),
                              c: vs(x + w - t / 2, h / 2, h - t / 2), e: vs(x + t / 2, h / 2, h - t / 2), f: vs(x + t / 2, t / 2, h / 2) }
                    for (var n in s) poly(s[n], lit[ch].indexOf(n) >= 0)
                } else if (ch === ":") {
                    poly([[x, h * .28], [x + t, h * .28], [x + t, h * .28 + t], [x, h * .28 + t]], true)
                    poly([[x, h * .64], [x + t, h * .64], [x + t, h * .64 + t], [x, h * .64 + t]], true)
                } else if (ch === ".") {
                    poly([[x, h - t], [x + t, h - t], [x + t, h], [x, h]], true)
                } else if (ch === "/") {
                    poly([[x, h], [x + t * .9, h], [x + w * .7, 0], [x + w * .7 - t * .9, 0]], true)
                }
                x += advance(ch)
            }
        }
    }

    Row {
        id: figures
        anchors.centerIn: parent
        spacing: lcd.fine ? 0 : Math.round(lcd.small * .35)
        Segments { objectName: "lcdNow"; text: lcd.now; h: lcd.big }
        Segments { visible: !lcd.fine; anchors.bottom: parent.bottom; text: "/"; h: lcd.small }
        Segments { objectName: "lcdTotal"; visible: !lcd.fine; anchors.bottom: parent.bottom; text: lcd.total; h: lcd.small }
        Segments { visible: lcd.fine; anchors.bottom: parent.bottom; text: lcd.duration > 0 ? lcd.hundredths : ""; h: lcd.small }
        Text {
            id: speedMark
            objectName: "lcdSpeed"
            visible: lcd.fast
            anchors.bottom: parent.bottom
            text: "×" + String(Math.round(lcd.speed * 100) / 100).replace(".", L.t.dec)
            color: Theme.lcdInk; font.family: Theme.monoFont; font.pixelSize: lcd.small; font.weight: Font.DemiBold
        }
    }
    MouseArea { id: lcdArea; anchors.fill: parent; hoverEnabled: true; onClicked: lcd.remaining = !lcd.remaining }
    MouseArea {
        id: speedArea
        visible: lcd.fast
        x: figures.x + speedMark.x - 4; y: 0; width: speedMark.width + 8; height: parent.height
        hoverEnabled: true
        onClicked: lcd.speedReset()
    }
    Tip { text: lcd.tip; shown: lcdArea.containsMouse && !lcdArea.pressed && !speedArea.containsMouse }
    Tip { text: L.t.t_speed_reset; shown: speedArea.containsMouse && !speedArea.pressed }
    Accessible.role: Accessible.StaticText
    Accessible.name: (lcd.remaining ? L.t.lcd_remaining : L.t.lcd_elapsed).arg(lcd.now).arg(lcd.total)
}
