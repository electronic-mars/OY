import QtQuick

// Omega's timeline: a scale of time marks above a thick seek groove, chapter notches,
// the A-B repeat, and the time (with the frame) under the pointer while hovering.
// Editing (the Braun concept): a column of track names on the left; the groove becomes the
// «Clip» track, the file's fragments as blocks where they lie and what stays out hatched; a
// track of bars in their ink for the drawings; a playhead through all of them.
Item {
    id: tl
    property real position: 0
    property real duration: 0
    property var chapters: []
    property real loopA: -1         // A-B repeat points, -1 while not set
    property real loopB: -1
    property bool previewOn: false  // show the frame under the pointer
    property string previewSource: ""
    signal hoverAt(real seconds)    // the pointer is over this time: a frame is wanted
    property var bands: []          // editor: [from, end, mark, number] of this file's fragments
    property var elsewhere: []      // editor: [row, file name] of the fragments in other files
    signal elsewherePicked(int row)
    // what lies over the scale's labels (fragment numbers, the other files' line): [x0, x1]
    readonly property var covers: otherTag.visible ? [[otherTag.x, otherTag.x + otherTag.width]] : []
    function covered(x, w) {
        return covers.some(c => x < c[1] + 3 && c[0] < x + w + 3)
    }
    property int fragSel: -1        // editor: the chosen fragment (its row in the edit)
    readonly property color clipGround: Theme.light ? "#CFC8B8" : "#191B1F"
    property var fragInfo: []       // editor: the edit's fragments (name, range, shift, pending), by row
    property bool fragFocus: false  // editor: the keyboard works on the fragments
    signal fragPicked(int row)      // a click on a fragment's block
    // editor: the column of track names; everything else is drawn right of it
    readonly property int gutter: editing ? (Theme.tier ? 112 : 84) + 12 : 0
    readonly property int pitch: Theme.tier === 2 ? 26 : 20     // editor: a drawings' track, bar and air
    readonly property int railGap: editing && Theme.tier === 2 ? 6 : 2
    readonly property int barH: Theme.tier === 2 ? 16 : 14
    readonly property int clipH: Theme.tier === 2 ? 32 : 30
    readonly property int laneRows: noteLane && notes.length ? layout.count : 0
    property real markIn: -1        // editor: the pending start mark
    property bool editing: false    // the editor is open
    // editor: the stretches of this file that stay out of the saved file (veiled on the groove)
    readonly property var outside: {
        if (!editing || !bands.length || !(duration > 0)) return []
        var spans = bands.map(b => [b[0], b[1]]).sort((p, q) => p[0] - q[0]), out = [], t = 0
        for (var k = 0; k < spans.length; k++) {
            if (spans[k][0] > t + 0.05) out.push([t, spans[k][0]])
            t = Math.max(t, spans[k][1])
        }
        if (duration > t + 0.05) out.push([t, duration])
        return out
    }
    property bool noteLane: false   // editor: a lane under the groove with the drawings' intervals
    property var notes: []          // [{i, a, b, kind, color, text}] of this file
    property int noteSel: -1
    property int noteHot: -1        // the drawing under the pointer on the frame: its bar lights up
    property int barHover: -1       // the drawing whose bar is under the pointer
    readonly property int lit: drag ? drag.i : barHover     // ... or dragged: the frame outlines it
    property var skips: []          // [from, to] that are skipped: the opening, the credits
    signal seekTo(real seconds, bool final)
    signal notePicked(int i)
    signal noteRanges(var ranges)   // [[i, a, b], …]: a drag let go (with Shift, a few drawings)
    signal menuRequested()          // right button: marking the opening and the credits

    // under everything else, so it only gets the right button (the rail takes the left)
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        onClicked: tl.menuRequested()
    }

    // the scale (24) and the groove (16), or editing: the clip track (32) and the drawings' tracks
    implicitHeight: editing ? 24 + railGap + clipH + (laneRows ? 6 + laneRows * pitch : 4) : 44

    // One format for the whole file, as the scale is written: 00:10, or 0:00:10 when the file
    // runs an hour or more.
    function fmt(s) {
        s = Math.max(0, Math.floor(s))
        var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60
        var two = (n) => (n < 10 ? "0" : "") + n
        return (duration >= 3600 ? h + ":" : "") + two(m) + ":" + two(sec)
    }
    // The labelled step: the shortest round step whose labels, centred on their marks, stand
    // well apart (three labels' width: the concept's 5 s on 40 s across a wide window), split by
    // minor ticks. The first and last label are pushed in from the ends.
    function rulerFor(dur, w, labelW) {
        var steps = [[1, 5], [2, 4], [5, 5], [10, 5], [15, 3], [30, 3], [60, 6], [120, 4], [300, 5],
                     [600, 5], [900, 3], [1800, 3], [3600, 4], [7200, 4], [14400, 4]]
        if (!(dur > 0) || !(w > 0)) return { step: 0, minor: 1 }
        for (var i = 0; i < steps.length - 1; i++)
            if (steps[i][0] * w / dur >= labelW * 3 + 8) break
        return { step: steps[i][0], minor: steps[i][1] }
    }
    TextMetrics { id: labelMetrics; font: marks.font; text: tl.duration >= 3600 ? "0:00:00" : "00:00" }
    readonly property var ruler: rulerFor(duration, marks.width, Math.ceil(labelMetrics.advanceWidth))

    function px(t) { return t / duration * area.width }
    // a drawing's times are shown in tenths, as the editor's marks: 0:13.0
    function tenths(s) {
        s = Math.round(Math.max(0, s) * 10) / 10
        var m = Math.floor(s / 60), r = s - m * 60
        return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1)
    }

    // The drawings on tracks: each in the first of up to four tracks where it overlaps no other
    // (taken in order of their starts), so drawings that share an interval lie one above the
    // other; more than four at once share the track that frees up first. Laid out from the
    // model, which changes when a drag is let go: a bar never jumps track under the pointer.
    readonly property var layout: {
        var ends = [], track = {}
        var order = notes.slice().sort((p, q) => p.a - q.a || p.i - q.i)
        for (var k = 0; k < order.length; k++) {
            var n = order[k], t = 0
            while (t < ends.length && ends[t] > n.a) t++
            if (t === 4) {
                t = 0
                for (var j = 1; j < 4; j++) if (ends[j] < ends[t]) t = j
            }
            ends[t] = Math.max(ends[t] || 0, n.b)
            track[n.i] = t
        }
        return { track: track, count: Math.max(1, ends.length) }
    }

    // A bar being dragged: {i, mode (a | b | move), group (the drawings that go along), da, db
    // (how far its start and end have gone), …}. The bars follow it; the model changes on release.
    property var drag: null
    function startDrag(n, mode, x, together) {
        // Shift: every drawing of the same interval goes along
        var group = [n.i].concat(together ? notes.filter(q => q.i !== n.i && q.a === n.a && q.b === n.b).map(q => q.i) : [])
        // what an end sticks to: the position, the other drawings' ends, the fragments' ends
        var stops = [position, 0, duration]
        for (var k = 0; k < notes.length; k++)
            if (group.indexOf(notes[k].i) < 0) stops.push(notes[k].a, notes[k].b)
        for (var f = 0; f < bands.length; f++) stops.push(bands[f][0], bands[f][1])
        drag = { i: n.i, a0: n.a, b0: n.b, mode: mode, x0: x, group: group, stops: stops, da: 0, db: 0, moved: false }
    }
    function dragTo(x, free) {
        var d = drag, dt = (x - d.x0) / area.width * duration, a = d.a0, b = d.b0
        if (d.mode === "a") a = Math.max(0, Math.min(b - 0.2, a + dt))
        else if (d.mode === "b") b = Math.min(duration, Math.max(a + 0.2, b + dt))
        else { var s = Math.max(-a, Math.min(duration - b, dt)); a += s; b += s }
        if (!free) {           // Alt: no sticking
            var near = 6 / area.width * duration
            var stick = (t) => d.stops.reduce((best, c) => Math.abs(c - t) < Math.abs(best - t) ? c : best, Infinity)
            var sa = stick(a) - a, sb = stick(b) - b
            sa = Math.abs(sa) < near ? sa : 0
            sb = Math.abs(sb) < near ? sb : 0
            if (d.mode === "a") a = Math.min(b - 0.2, a + sa)
            else if (d.mode === "b") b = Math.max(a + 0.2, b + sb)
            else {
                var m = sa === 0 ? sb : sb === 0 ? sa : Math.abs(sa) < Math.abs(sb) ? sa : sb
                a += m; b += m
            }
        }
        drag = Object.assign({}, d, { da: a - d.a0, db: b - d.b0, moved: true })
        // the frame follows the end (a moved bar: its start), exactly: the drawing is set to that
        // frame, so a keyframe seconds away would mislead (the seek bar's drag takes keyframes)
        seekTo(d.mode === "b" ? b : a, true)
    }
    function endDrag() {
        var d = drag
        drag = null
        if (!d.moved) { notePicked(d.i); return }
        noteRanges(d.group.map(i => { var q = notes.find(n => n.i === i); return [i, q.a + d.da, q.b + d.db] }))
    }
    // the drawing whose times are shown: dragged, else under the pointer, else the chosen one
    readonly property var span: {
        var i = drag ? drag.i : barHover >= 0 ? barHover : noteSel
        var n = noteLane ? notes.find(q => q.i === i) : undefined
        if (!n || !(duration > 0)) return null
        var moved = drag !== null && drag.group.indexOf(i) >= 0
        return { a: n.a + (moved ? drag.da : 0), b: n.b + (moved ? drag.db : 0), track: layout.track[i] || 0 }
    }

    // editor: the tracks' names, each level with its track
    Item {
        id: trackNames          // not "names": an id of that name would win over otherTag's property
        visible: tl.editing && tl.duration > 0
        width: tl.gutter - 12; height: tl.height
        component TrackName: Row {
            property string icon: ""
            property string word: ""
            property bool on: false
            spacing: 8
            height: 16
            Icon { anchors.verticalCenter: parent.verticalCenter; name: parent.icon; size: 14
                   color: parent.on ? Theme.glyph : Theme.inkDim }
            Text { anchors.verticalCenter: parent.verticalCenter; text: parent.word
                   color: parent.on ? Theme.glyph : Theme.inkDim; font.family: Theme.uiFont; font.pixelSize: 12 }
        }
        TrackName { objectName: "trackClip"; y: rail.y + (rail.height - height) / 2; icon: "film"; word: L.t.tl_clip
                    on: tl.fragSel >= 0 }
        Repeater {
            model: tl.laneRows
            TrackName {
                objectName: "trackName" + index
                readonly property var kinds: tl.notes.filter(n => (tl.layout.track[n.i] || 0) === index).map(n => n.kind)
                                                   .filter((k, i, a) => a.indexOf(k) === i)
                readonly property string kind: kinds.length === 1 ? kinds[0] : ""
                y: lane.y + index * tl.pitch + (tl.pitch - 4 - height) / 2
                icon: ({ arrow: Theme.icArrow, rect: Theme.icRect, pen: Theme.icPen, text: Theme.icText })[kind] || Theme.icPen
                word: ({ arrow: L.t.tl_arrow, rect: L.t.tl_rect, pen: L.t.tl_pen, text: L.t.tl_text })[kind] || L.t.tl_drawings
                on: tl.span !== null && tl.span.track === index
            }
        }
    }
    Item {
        id: area
        x: tl.gutter
        width: tl.width - tl.gutter; height: tl.height
    Item {
        id: marks
        objectName: "scaleMarks"
        readonly property font font: Qt.font({ family: Theme.monoFont, pixelSize: 10, letterSpacing: .2 })
        anchors { left: parent.left; right: parent.right; top: parent.top }
        // labels in the top 13 px, then a gap, then the ticks: 8 px at a label, 4 px between
        height: 24
        readonly property int tickTop: 16
        Canvas {
            id: ticks
            anchors.fill: parent
            readonly property var key: [tl.ruler.step, tl.ruler.minor, tl.duration, width, Theme.inkDim]
            onKeyChanged: requestPaint()
            onPaint: {
                var g = getContext("2d")
                g.reset()
                if (!(tl.ruler.step > 0)) return
                var d = tl.ruler.step / tl.ruler.minor, n = Math.floor(tl.duration / d + 1e-6)
                g.fillStyle = Theme.inkDim
                for (var i = 0; i <= n; i++) {
                    var major = i % tl.ruler.minor === 0
                    g.globalAlpha = major ? 1 : .55
                    g.fillRect(Math.min(width - 1, Math.round(i * d / tl.duration * width)), major ? marks.tickTop : height - 4, 1,
                               major ? height - marks.tickTop : 4)
                }
            }
        }
        Repeater {
            model: tl.ruler.step > 0 ? Math.floor(tl.duration / tl.ruler.step + 1e-6) + 1 : 0
            Text {
                objectName: "scaleLabel" + index
                // centred on its mark, pushed in at the ends
                readonly property real over: Theme.tier ? width / 2 : 0     // the panel's 24 px margin holds half a label
                x: Math.max(-over, Math.min(marks.width - width + over, index * tl.ruler.step / tl.duration * marks.width - width / 2))
                text: tl.fmt(index * tl.ruler.step)
                color: Theme.inkDim
                font: marks.font
                // a drawing's times lie over the scale: a label they would cut in half steps aside
                visible: (!spanTag.visible || x + width < spanTag.x - 3 || x > spanTag.x + spanTag.width + 3)
                         && !tl.covered(x, width)
            }
        }
        // editor: the edit has fragments in another file; a click opens it at the first of them
        Text {
            id: otherTag
            objectName: "otherFrags"
            readonly property int n: tl.elsewhere.length
            readonly property var names: tl.elsewhere.map(e => e[1]).filter((v, i, a) => a.indexOf(v) === i)
            visible: tl.editing && n > 0
            anchors.right: parent.right
            y: -1
            text: L.t.tl_elsewhere.arg(n + " " + L.plural(n, L.t.frag_forms)).arg(names[0] || "")
                  + (names.length > 1 ? L.t.and_more : "") + "  →"
            color: otherArea.containsMouse ? Theme.tx : Theme.accText
            font.family: Theme.uiFont; font.pixelSize: 10; font.weight: Font.DemiBold
            MouseArea { id: otherArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: tl.elsewherePicked(tl.elsewhere[0][0]) }
            Tip { text: L.t.tl_other_tip; shown: otherArea.containsMouse }
        }
    }

    // A-B repeat: the stretch that plays over and over, a light bar over the groove (under
    // the cap, so the position stays readable); its ends are drawn after the rail
    Rectangle {
        objectName: "loopBand"
        visible: tl.loopA >= 0 && tl.loopB > tl.loopA && tl.duration > 0
        x: tl.loopA / tl.duration * rail.width
        width: Math.max(2, (tl.loopB - tl.loopA) / tl.duration * rail.width)
        y: rail.y + 1; height: 3; radius: 1.5
        color: Theme.tx; opacity: .6
    }
    Rectangle {
        objectName: "clipTrack"
        z: -2
        visible: tl.editing && tl.duration > 0
        x: 0; y: rail.y; width: rail.width; height: rail.height
        radius: 6
        color: tl.clipGround
        border.color: Theme.line
        clip: true
        // the concept's hatch along the whole track; the fragments' blocks lie over it, see-through
        Canvas {
            anchors.fill: parent
            readonly property var key: [width, height, Theme.light]
            onKeyChanged: requestPaint()
            onPaint: {
                var g = getContext("2d")
                g.reset()
                g.strokeStyle = Theme.light ? "#C2BAA9" : "#22252A"
                g.lineWidth = 1.4
                for (var x = -height; x < width; x += 10) { g.beginPath(); g.moveTo(x, height); g.lineTo(x + height, 0); g.stroke() }
            }
        }
    }
    Rail {
        id: rail
        objectName: "seekRail"
        anchors { left: parent.left; right: parent.right; top: marks.bottom; topMargin: tl.railGap }
        height: tl.editing ? tl.clipH : 16
        grooveHeight: 6
        capWidth: 12
        bare: tl.editing
        enabled: tl.duration > 0
        value: tl.duration > 0 ? tl.position / tl.duration : 0
        name: L.t.position
        valueText: tl.fmt(tl.position) + " / " + tl.fmt(tl.duration)
        onMoved: (v) => tl.seekTo(v * tl.duration, false)
        onReleased: (v) => {
            // editing: a click (not a drag) on a fragment's block chooses it, which shows its start
            var t = v * tl.duration, b = tl.bands.find(q => t >= q[0] && t <= q[1])
            if (tl.editing && b && Math.abs(v - rail.pressValue) * rail.width < 4) tl.fragPicked(b[3] - 1)
            else tl.seekTo(t, true)
        }
        onHoverValueChanged: if (hovered && tl.previewOn) tl.hoverAt(hoverValue * tl.duration)
        onHoveredChanged: if (hovered && tl.previewOn) tl.hoverAt(hoverValue * tl.duration)
    }
    // the position as a tuning needle: from the ticks (under the labels, never through them)
    // down to the cap, with a small head
    Item {
        objectName: "needle"
        visible: rail.enabled && tl.editing
        x: Math.round(rail.shown * rail.width) - 1
        y: marks.tickTop
        z: 1            // over the scale and the fragments' blocks: it is where the picture is
        Rectangle { width: 2; height: rail.y + rail.height - parent.y; radius: 1; color: Theme.acc }
        Canvas {
            x: -3; y: -1; width: 8; height: 5
            readonly property color c: Theme.acc
            onCChanged: requestPaint()
            onPaint: { var g = getContext("2d"); g.reset(); g.fillStyle = c; g.beginPath()
                       g.moveTo(0, 0); g.lineTo(8, 0); g.lineTo(4, 5); g.closePath(); g.fill() }
        }
    }
    // ... and on down through the drawings' tracks, under their bars and their words
    Rectangle {
        visible: rail.enabled && tl.editing && lane.visible
        z: -0.5
        x: Math.round(rail.shown * rail.width) - 1
        y: rail.y + rail.height
        width: 2; height: lane.y + lane.height - y; radius: 1
        color: Theme.acc
    }
    // each end: a tick through the groove with a lettered flag on top, both flags facing
    // into the stretch (it sits over the time scale, so it gets its own ground)
    Repeater {
        model: [["A", tl.loopA], ["B", tl.loopB]]
        Item {
            objectName: "loop" + modelData[0]
            visible: modelData[1] >= 0 && tl.duration > 0
            x: modelData[1] / tl.duration * rail.width
            y: rail.y - 3
            Rectangle { x: -1; width: 2; height: rail.height + 5; color: Theme.tx }
            Rectangle {
                x: modelData[0] === "A" ? -1 : -width + 1; y: -9
                width: 11; height: 11; radius: 2
                color: Theme.tx
                Text { anchors.centerIn: parent; text: modelData[0]; color: Theme.bg
                       font.family: Theme.uiFont; font.pixelSize: 9; font.weight: Font.Bold }
            }
        }
    }
    // what autoskip jumps over: the groove there is veiled, with a bracket at each end
    Repeater {
        model: tl.duration > 0 ? tl.skips : []
        Item {
            objectName: "skipBand" + index
            x: modelData[0] / tl.duration * rail.width
            width: Math.max(3, (modelData[1] - modelData[0]) / tl.duration * rail.width)
            y: rail.y + (rail.height - 9) / 2; height: 9
            Rectangle { anchors.fill: parent; radius: 3; color: Theme.light ? Qt.rgba(0, 0, 0, .28) : Qt.rgba(1, 1, 1, .3) }
            Rectangle { width: 2; height: parent.height; color: Theme.tx2 }
            Rectangle { x: parent.width - 2; width: 2; height: parent.height; color: Theme.tx2 }
        }
    }
    Repeater {
        model: tl.duration > 0 ? tl.chapters : []
        Rectangle {
            x: modelData.time / tl.duration * rail.width - 1
            y: rail.y + 1; width: 2; height: 3; color: Theme.tx2
        }
    }
    // editor: what stays out of the file is veiled, as the skipped opening is: then the accent
    // on the groove means «goes into the file»
    Repeater {
        model: tl.outside
        Item {
            objectName: "outside" + index
            x: modelData[0] / tl.duration * rail.width
            width: Math.max(2, (modelData[1] - modelData[0]) / tl.duration * rail.width)
            y: rail.y + 1; height: rail.height - 2
            clip: true
            // what stays out of the file: the track's hatch, a shade deeper
            Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, Theme.light ? .06 : .12) }
        }
    }
    // editor: what of this file goes into the edit, a block on the clip track for each fragment
    // with its number in the edit and its times; a copied fragment begins at the keyframe before
    // its mark, and that lead is hatched. Clicking a block chooses the fragment.
    Repeater {
        model: tl.duration > 0 ? tl.bands : []
        Rectangle {
            id: block
            readonly property int row: modelData[3] - 1
            readonly property var info: tl.fragInfo[row] || ({})
            objectName: "frag" + row
            readonly property bool sel: row === tl.fragSel
            Accessible.role: Accessible.ListItem
            Accessible.name: L.t.es_frag_n.arg(row + 1).arg(info.name || "").arg(info.range || "")
            Accessible.selected: sel
            Accessible.selectable: true
            x: modelData[0] / tl.duration * rail.width
            width: Math.max(2, (modelData[1] - modelData[0]) / tl.duration * rail.width)
            y: rail.y; height: rail.height
            radius: 6
            color: Theme.accA(sel ? .28 : .16)
            border.width: sel ? 2 : 1
            border.color: Theme.acc
            Item {
                objectName: "bandLead" + index
                visible: modelData[2] > modelData[0] + 0.05
                x: 2; y: 2
                width: visible ? (modelData[2] - modelData[0]) / tl.duration * rail.width : 0
                height: parent.height - 4; clip: true
                Row {
                    spacing: 2
                    Repeater { model: Math.ceil(parent.parent.width / 3) + 1
                               Rectangle { width: 1; height: block.height; color: Theme.accA(.6) } }
                }
            }
            // a grip at each end
            Rectangle { x: 3; y: 6; width: 3; height: parent.height - 12; radius: 1.5; color: Theme.acc }
            Rectangle { x: parent.width - 6; y: 6; width: 3; height: parent.height - 12; radius: 1.5; color: Theme.acc }
            // the keyframe is read by a thread of its own, and until then the start may move: a
            // bar that runs without an end along the block's foot
            Item {
                objectName: "fragPending"
                visible: !!block.info.pending
                id: pendingBar
                x: 8; width: parent.width - 16; y: parent.height - 4; height: 2; clip: true
                Rectangle {
                    id: runner
                    width: Math.max(8, pendingBar.width / 3); height: 2; radius: 1; color: Theme.acc
                    NumberAnimation on x {
                        running: pendingBar.visible; loops: Animation.Infinite; duration: 900
                        from: -runner.width * 0.5; to: pendingBar.width
                    }
                }
            }
            HoverHandler { id: blockHover }
            Tip { text: (block.info.name || "") + "   " + (block.info.range || "") + "   ·   " + L.t.es_order
                        + (block.info.pending ? "   ·   " + L.t.es_seeking_kf : "")
                  shown: blockHover.hovered }
        }
    }
    // the blocks' words on plates of the block's own colour, over the lines that run down the
    // track (the playhead, a drawing's times): a line passes behind the words, never through them
    Repeater {
        model: tl.duration > 0 ? tl.bands : []
        Item {
            id: words
            readonly property int row: modelData[3] - 1
            readonly property var info: tl.fragInfo[row] || ({})
            readonly property bool sel: row === tl.fragSel
            readonly property color fill: Qt.tint(tl.clipGround, Theme.accA(sel ? .28 : .16))
            z: 1
            x: modelData[0] / tl.duration * rail.width
            width: Math.max(2, (modelData[1] - modelData[0]) / tl.duration * rail.width)
            y: rail.y; height: rail.height
            Rectangle {
                visible: wordRow.visible
                x: wordRow.x - 3; y: wordRow.y - 1; width: wordRow.width + 6; height: wordRow.height + 2
                radius: 3; color: words.fill
            }
            Row {
                id: wordRow
                x: 12; anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                visible: words.width > 40
                Text {
                    objectName: "bandNum" + index
                    text: String(modelData[3])
                    color: Theme.accText; font.family: Theme.monoFont; font.pixelSize: 11; font.weight: Font.Medium
                }
                Text {
                    visible: words.width > 200
                    text: tl.fmt(modelData[0]) + "–" + tl.fmt(modelData[1])
                    color: Theme.glyph; font.family: Theme.monoFont; font.pixelSize: 11
                }
            }
            // a copied fragment begins at the keyframe before its mark: by how much, in grey
            Rectangle {
                visible: shiftText.visible
                x: shiftText.x - 3; y: shiftText.y - 1; width: shiftText.width + 6; height: shiftText.height + 2
                radius: 3; color: words.fill
            }
            Text {
                id: shiftText
                objectName: "fragShift" + words.row
                visible: (words.info.shift || 0) > 0.05 && words.width >= 110
                anchors { right: parent.right; rightMargin: words.sel ? 30 : 12; verticalCenter: parent.verticalCenter }
                text: "−" + L.num(words.info.shift || 0, 1) + " " + L.t.sec
                color: Theme.tx3; font.family: Theme.uiFont; font.pixelSize: 10
            }
            // the chosen fragment: a small × takes it out of the edit
            Rectangle {
                objectName: "fragClose" + words.row
                visible: words.sel && words.width >= 90
                anchors { right: parent.right; rightMargin: 9; verticalCenter: parent.verticalCenter }
                width: 16; height: 16; radius: 4
                color: closeArea.containsMouse ? Theme.accA(.35) : words.fill
                Icon { anchors.centerIn: parent; name: Theme.icCancel; size: 11; stroke: 2
                       color: closeArea.containsMouse ? Theme.tx : Theme.tx2 }
                MouseArea { id: closeArea; anchors.fill: parent; hoverEnabled: true; onClicked: editor.removeSelected() }
                Tip { text: L.t.es_remove; shown: closeArea.containsMouse }
                Accessible.role: Accessible.Button
                Accessible.name: L.t.es_remove_n.arg(words.row + 1)
                Accessible.onPressAction: editor.removeSelected()
            }
        }
    }
    // the keyboard works on the fragments (F6, a click on one): a 2 px ring round the clip track
    Rectangle {
        objectName: "stripFocus"
        visible: tl.editing && tl.fragFocus
        x: -3; y: rail.y - 3; width: rail.width + 6; height: rail.height + 6
        radius: 9; color: "transparent"; border.width: 2; border.color: Theme.acc
    }
    // editor: no start mark yet, so a fragment begins at the file's start: a pale dashed I there
    Item {
        id: markGhost
        objectName: "markGhost"
        readonly property string tip: L.t.tl_no_in
        visible: tl.editing && tl.markIn < 0 && tl.duration > 0
        x: 0; y: rail.y - 3; width: 10; height: rail.height + 5
        Column {
            spacing: 2
            Repeater { model: 5; Rectangle { width: 2; height: 2; color: Theme.tx3 } }
        }
        Text { x: 3; y: -6; text: "I"; color: Theme.tx3
               font.family: Theme.uiFont; font.pixelSize: 9; font.weight: Font.Bold }
        HoverHandler { id: ghostHover }
        Tip { text: markGhost.tip; shown: ghostHover.hovered }
    }
    Item {
        visible: tl.markIn >= 0 && tl.duration > 0
        x: tl.markIn / tl.duration * rail.width
        y: rail.y - 3
        Rectangle { x: -1; width: 2; height: rail.height + 5; color: Theme.acc }
        Text { x: 3; y: -6; text: "I"; color: Theme.accText
               font.family: Theme.uiFont; font.pixelSize: 9; font.weight: Font.Bold }
    }
    // editor: when each drawing is on screen, a bar on its track in the drawing's own ink, with
    // its times (a text's words first); the chosen one ringed in white. Drag a bar to move it in
    // time, its ends to lengthen or shorten it.
    Item {
        id: lane
        objectName: "noteLane"
        visible: tl.noteLane && tl.duration > 0
        anchors { left: parent.left; right: parent.right; top: rail.bottom; topMargin: 6 }
        height: tl.laneRows * tl.pitch
        Repeater {
            model: tl.notes
            Item {
                id: nb
                objectName: "noteBar" + modelData.i
                readonly property bool sel: modelData.i === tl.noteSel
                readonly property bool hot: barArea.containsMouse || modelData.i === tl.noteHot
                readonly property bool moving: tl.drag !== null && tl.drag.group.indexOf(modelData.i) >= 0
                readonly property real a: moving ? modelData.a + tl.drag.da : modelData.a
                readonly property real b: moving ? modelData.b + tl.drag.db : modelData.b
                // exactly over [a, b], at least 2 px
                x: Math.round(tl.px(a))
                width: Math.max(2, Math.round(tl.px(b)) - x)
                y: (tl.layout.track[modelData.i] || 0) * tl.pitch + (tl.pitch - tl.barH - 4) / 2
                height: tl.barH
                z: sel ? 2 : hot ? 1 : 0
                // dark words on a light ink, light ones on a dark ink
                readonly property color ink: modelData.color
                readonly property bool lightInk: 0.2126 * ink.r + 0.7152 * ink.g + 0.0722 * ink.b > 0.45
                Rectangle {     // the chosen one: a white ring round the bar, a dark one round that
                    visible: nb.sel
                    anchors.fill: parent; anchors.margins: -3
                    radius: height / 2; color: "transparent"; border.width: 1.5; border.color: Qt.rgba(0, 0, 0, .6)
                }
                Rectangle {
                    visible: nb.sel
                    anchors.fill: parent; anchors.margins: -1.5
                    radius: height / 2; color: "transparent"; border.width: 1.5; border.color: "white"
                }
                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    // white ink reads as the concept's cream bar, not as a hole in the panel
                    color: Qt.colorEqual(nb.ink, "#FFFFFF") ? "#E9E6DF" : nb.ink
                    border.width: nb.sel || nb.lightInk ? 0 : 1
                    border.color: Theme.lineHi
                    Rectangle { anchors.fill: parent; radius: parent.radius; color: "white"; opacity: nb.hot && !nb.sel ? .18 : 0 }
                }
                Rectangle { visible: nb.sel; x: 5; y: 3; width: 2; height: parent.height - 6; radius: 1; color: Qt.rgba(0.11, 0.12, 0.14, .75) }
                Rectangle { visible: nb.sel; x: parent.width - 7; y: 3; width: 2; height: parent.height - 6; radius: 1; color: Qt.rgba(0.11, 0.12, 0.14, .75) }
                Text {
                    x: 12; width: parent.width - 20; anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight
                    text: (modelData.kind === "text" && modelData.text ? modelData.text + " · " : "") + tl.fmt(nb.a) + "–" + tl.fmt(nb.b)
                    color: nb.lightInk ? "#1C1F24" : "#F3F1EC"
                    font.family: Theme.monoFont; font.pixelSize: 10
                    visible: parent.width > 40
                }
                MouseArea {
                    id: barArea
                    // an end is taken 4 px outside the bar and up to 5 px inside it; the middle
                    // always moves the drawing, however narrow the bar
                    anchors { fill: parent; leftMargin: -4; rightMargin: -4; topMargin: -1; bottomMargin: -1 }
                    hoverEnabled: true
                    readonly property real edge: 4 + Math.min(5, Math.floor(nb.width / 3))
                    function zone(mx) { return mx < edge ? "a" : mx > width - edge ? "b" : "move" }
                    cursorShape: zone(mouseX) === "move" ? Qt.SizeAllCursor : Qt.SizeHorCursor
                    onContainsMouseChanged: tl.barHover = containsMouse ? modelData.i : (tl.barHover === modelData.i ? -1 : tl.barHover)
                    onPressed: (m) => tl.startDrag(modelData, zone(m.x), mapToItem(lane, m.x, 0).x, m.modifiers & Qt.ShiftModifier)
                    onPositionChanged: (m) => { if (pressed && tl.drag) tl.dragTo(mapToItem(lane, m.x, 0).x, m.modifiers & Qt.AltModifier) }
                    onReleased: if (tl.drag) tl.endDrag()
                    onDoubleClicked: tl.seekTo(modelData.a, true)       // to the drawing's start
                }
            }
        }
    }
    // the drawing whose times are shown: a line up from each end to the scale, and on the
    // scale between them its times in tenths and its length (live while it is dragged)
    Repeater {
        model: tl.span ? 2 : 0
        Rectangle {
            objectName: "noteSpanLine" + index
            z: 0.5          // over the blocks, under their words (a layer of their own, on plates)
            x: index ? Math.round(tl.px(tl.span.b)) - 1 : Math.round(tl.px(tl.span.a))     // over the bar's end columns
            y: marks.height
            width: 1
            height: lane.y + tl.span.track * tl.pitch + (tl.pitch - tl.barH - 4) / 2 - y
            color: Theme.tx; opacity: .7
        }
    }
    Rectangle {
        id: spanTag
        visible: tl.span !== null
        readonly property real mid: tl.span ? (tl.px(tl.span.a) + tl.px(tl.span.b)) / 2 : 0
        x: Math.max(0, Math.min(area.width - width, mid - width / 2))
        width: spanText.implicitWidth + 10; height: 14
        radius: 3
        color: Theme.card; border.color: Theme.lineHi
        Text {
            id: spanText
            objectName: "noteSpanLabel"
            anchors.centerIn: parent
            text: tl.span ? tl.tenths(tl.span.a) + " – " + tl.tenths(tl.span.b) + " · "
                            + L.num(tl.span.b - tl.span.a, 1) + " " + L.t.sec : ""
            color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 10
        }
    }
    // time under the pointer, with its frame above it
    Rectangle {
        id: hoverCard
        objectName: "seekPreview"
        readonly property bool pic: tl.previewOn && tl.previewSource !== ""
        visible: rail.hovered && tl.duration > 0
        x: Math.max(0, Math.min(area.width - width, rail.hoverValue * rail.width - width / 2))
        y: -height - 4
        width: pic ? frame.width + 8 : hoverLabel.implicitWidth + 12
        height: pic ? frame.height + 26 : 20
        radius: 5
        color: Theme.card; border.color: Theme.lineHi
        Image {
            id: frame
            objectName: "seekPreviewFrame"
            visible: hoverCard.pic
            x: 4; y: 4
            width: 224
            height: sourceSize.width > 0 ? Math.round(width * sourceSize.height / sourceSize.width) : 126
            source: tl.previewOn ? tl.previewSource : ""
            cache: false
        }
        Text {
            id: hoverLabel
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 3 }
            text: tl.fmt(rail.hoverValue * tl.duration)
            color: Theme.tx; font.family: Theme.uiFont; font.pixelSize: 11
        }
    }
    }
}
