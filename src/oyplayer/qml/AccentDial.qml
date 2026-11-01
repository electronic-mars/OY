import QtQuick

// The one colour, picked the way an old radio is tuned: a needle over a glass scale with
// the colours printed on it as stations, names staggered above and below as on an old
// dial. The needle can stop anywhere; near a station it settles on it. The yellow stretch
// is printed "EDITING": that colour belongs to the editor, so the needle will not stay there.
// While the needle moves, the whole player takes the colour (Theme.tuning); on release it
// is kept (setting "accent").
Item {
    id: dial
    height: 64

    // [place on the scale, hue] (OKLCH); the scale runs on stations, not on degrees, so every
    // station gets the same room and the narrow orange-red stretch is as easy to hit as blue
    readonly property var knots: [[0, 10], [0.5, 28], [1.5, 44], [2.5, 62], [3, 72], [4, 118], [4.5, 142],
                                  [5.5, 182], [6.5, 232], [7.5, 266], [8.5, 300], [9.5, 345], [10, 370]]
    readonly property var stations: [[0.5, L.t.dial_red], [1.5, L.t.dial_orange], [2.5, L.t.dial_amber], [4.5, L.t.dial_green],
                                     [5.5, L.t.dial_teal], [6.5, L.t.dial_sky], [7.5, L.t.dial_blue], [8.5, L.t.dial_lilac],
                                     [9.5, L.t.dial_raspberry]]
    readonly property real zoneA: 3     // the editor's yellow
    readonly property real zoneB: 4
    readonly property real units: 10
    // the lightness and chroma of the default orange: every station is as bright as it is
    readonly property real tuneL: 0.683
    readonly property real tuneC: 0.185

    function hueAt(u) {
        for (var i = 1; i < knots.length; i++)
            if (u <= knots[i][0]) {
                var a = knots[i - 1], b = knots[i]
                return (a[1] + (b[1] - a[1]) * (u - a[0]) / (b[0] - a[0])) % 360
            }
        return knots[knots.length - 1][1] % 360
    }
    function placeOf(h) {
        if (h < knots[0][1]) h += 360
        for (var i = 1; i < knots.length; i++)
            if (h <= knots[i][1]) {
                var a = knots[i - 1], b = knots[i]
                return a[0] + (b[0] - a[0]) * (h - a[1]) / (b[1] - a[1])
            }
        return units
    }
    // the colour at a place; the orange station is the original orange to the digit
    function colorAt(u) {
        if (Math.abs(u - 1.5) < 1e-6) return Theme.accentDefault
        return Theme.oklch(tuneL, tuneC, hueAt(u)).toString()
    }
    // where a released needle stays: on a station near it, never in the editor's yellow
    function settle(u) {
        var best = stations[0][0]
        for (var i = 0; i < stations.length; i++)
            if (Math.abs(stations[i][0] - u) < Math.abs(best - u)) best = stations[i][0]
        return Math.abs(best - u) < 0.2 || (u > zoneA - 0.1 && u < zoneB + 0.1) ? best : u
    }
    function tuneTo(u, done) {
        var c = colorAt(Math.max(0, Math.min(units, u)))
        if (done) { settings.set("accent", c); Theme.tuning = "" }
        else Theme.tuning = c
    }

    // a colour property turns the setting's text into a colour for Theme.lch
    readonly property color tunedColor: Theme.tuning !== "" ? Theme.tuning : settings.values.accent
    readonly property real needle: placeOf(Theme.lch(tunedColor)[2])

    Row {
        anchors.fill: parent
        spacing: 12
        // the lamp: the play key as it will look
        KeyCap { id: lamp; round: true; accent: true; glyph: Theme.icPlay; solid: true; glyphShift: 1.5; anchors.verticalCenter: parent.verticalCenter }

        Rectangle {
            id: glass
            objectName: "accentGlass"
            width: parent.width - lamp.width - 12
            height: parent.height
            radius: 8
            color: Theme.sunk
            border.color: Theme.line
            readonly property real x0: 10                   // the scale inside the glass
            readonly property real w: width - 20
            function xOf(u) { return x0 + u / dial.units * w }

            // inner shadow along the top: the glass sits in the panel
            Rectangle {
                x: 1; y: 1; width: parent.width - 2; height: 8; radius: 7
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(0, 0, 0, Theme.light ? .12 : .35) }
                    GradientStop { position: 1; color: "transparent" }
                }
            }

            // the band of colours, the ticks, the editor's stretch
            Canvas {
                id: band
                anchors.fill: parent
                readonly property var key: [width, Theme.light, Theme.tx3]
                onKeyChanged: requestPaint()
                onPaint: {
                    var g = getContext("2d")
                    g.reset()
                    var x0 = glass.x0, w = glass.w, y = 27, h = 9
                    for (var x = 0; x < w; x++) {
                        var u = x / w * dial.units
                        g.fillStyle = u >= dial.zoneA && u < dial.zoneB ? Theme.editYellow
                                                                         : Theme.oklch(dial.tuneL, dial.tuneC, dial.hueAt(u))
                        g.fillRect(x0 + x, y, 1, h)
                    }
                    // the editor's stretch: hatched, as a band reserved on a real dial
                    var za = glass.xOf(dial.zoneA), zb = glass.xOf(dial.zoneB)
                    g.save()
                    g.beginPath(); g.rect(za, y, zb - za, h); g.clip()
                    g.strokeStyle = Qt.rgba(0, 0, 0, .35); g.lineWidth = 1.5
                    for (var s = za - h; s < zb; s += 5) { g.beginPath(); g.moveTo(s, y + h); g.lineTo(s + h, y); g.stroke() }
                    g.restore()
                    // ticks: every quarter between stations, taller at the stations
                    g.fillStyle = Theme.tx3
                    for (var q = 0; q <= dial.units * 4; q++) {
                        var uq = q / 4
                        if (uq > dial.zoneA && uq < dial.zoneB) continue
                        var tall = dial.stations.some(st => Math.abs(st[0] - uq) < 1e-6)
                        var tx = Math.round(glass.xOf(uq))
                        g.globalAlpha = tall ? .9 : .45
                        g.fillRect(tx, tall ? 20 : 23, 1, tall ? 6 : 3)
                        g.fillRect(tx, y + h + 1, 1, tall ? 5 : 2)
                    }
                }
            }

            // the names in their order on the scale, staggered: below the band, above, below…
            Repeater {
                model: dial.stations.concat([[3.5, L.t.edit_caps]]).sort((a, b) => a[0] - b[0])
                Text {
                    objectName: "accentStation" + index
                    readonly property real u: modelData[0]
                    readonly property bool zone: u > dial.zoneA && u < dial.zoneB
                    readonly property bool tuned: !zone && Math.abs(dial.needle - u) < 0.06
                    x: Math.max(4, Math.min(glass.width - 4 - width, glass.xOf(u) - width / 2))
                    y: zone || index % 2 === 1 ? 6 : 44
                    text: modelData[1]
                    color: zone ? Theme.oklch(Theme.light ? .7 : .85, .17, 88) : tuned ? Theme.tx : Theme.tx3
                    font.family: Theme.uiFont; font.pixelSize: 9; font.letterSpacing: 1.6
                    font.weight: tuned ? Font.DemiBold : Font.Normal
                }
            }

            // the needle: over the ticks and the band, not over the names, so the chosen one reads
            Rectangle {
                objectName: "accentNeedle"
                x: Math.round(glass.xOf(dial.needle)) - 1
                y: 17; width: 3; height: 27; radius: 1
                color: Qt.rgba(0, 0, 0, .45)
                Rectangle { x: 1; width: 1; height: parent.height; color: Theme.tx }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.SizeHorCursor
                function at(mx) { return Math.max(0, Math.min(dial.units, (mx - glass.x0) / glass.w * dial.units)) }
                onPressed: (m) => dial.tuneTo(at(m.x), false)
                onPositionChanged: (m) => { if (pressed) dial.tuneTo(at(m.x), false) }
                onReleased: (m) => dial.tuneTo(dial.settle(at(m.x)), true)
                // the wheel goes from station to station
                onWheel: (w) => {
                    var st = dial.stations.map(s => s[0]), i = 0
                    for (var k = 0; k < st.length; k++) if (Math.abs(st[k] - dial.needle) < Math.abs(st[i] - dial.needle)) i = k
                    i = Math.max(0, Math.min(st.length - 1, i + (w.angleDelta.y < 0 ? 1 : -1)))
                    dial.tuneTo(st[i], true)
                }
            }
        }
    }
}
