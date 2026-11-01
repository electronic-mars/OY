import QtQuick

// Drawings over the picture (SPEC §7): text, arrows, rectangles and pencil lines, each on
// screen for its interval of the file. The layer lies exactly over the picture and keeps
// points as fractions of it, so a drawing stays on its spot of the frame at any window
// size; sizes are fractions of the picture's height, the same as editor.py's render_note()
// uses for the saved file.
Item {
    id: layer
    property string tool: "select"          // select | text | arrow | rect | pen
    property color ink: "#F26A21"
    property real size: 1                   // the line: thin .6, medium 1, thick 1.6 (the draw bar)
    property real topClear: 0               // the draw bar lies over the picture down to here
    readonly property real lw: Math.max(1.5, 0.007 * height)
    readonly property int textPx: Math.max(6, Math.round(0.065 * height))
    property var draft: null                // the drawing under the pointer, not yet added
    property int lit: -1                    // the drawing whose bar is under the pointer (or dragged)
    // the drawing under the pointer here: its bar on the timeline lights up
    readonly property int hot: hover.hovered ? hit(hover.point.position.x, hover.point.position.y) : -1
    HoverHandler { id: hover }

    // the playing file's drawings whose interval holds the position; the chosen one and the
    // one whose bar is pointed at also outside their interval, faded, so their ends can be set
    // on the timeline
    // read from Python when the edit changes, not on every frame with the position
    readonly property var allNotes: editor.notes
    readonly property var shown: {
        var out = [], all = allNotes, t = player.position
        for (var k = 0; k < all.length; k++) {
            var n = all[k]
            if (n.path !== player.path) continue
            var inside = t >= n.a && t <= n.b
            if (inside || n.i === editor.noteSel || n.i === lit) out.push(Object.assign({ ghost: !inside }, n))
        }
        return out
    }
    readonly property string shownKey: shown.map(n => n.i + (n.ghost ? "g" : "")).join(",")
    onShownKeyChanged: canvas.requestPaint()
    onLitChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    Connections { target: editor; function onChanged() { canvas.requestPaint() } }

    FontMetrics { id: fm; font.family: Theme.uiFont; font.pixelSize: layer.textPx; font.weight: Font.DemiBold }

    function px(p) { return Qt.point(p[0] * width, p[1] * height) }
    function box(n) {
        if (n.kind === "text") {
            var a = px(n.pts[0])
            return Qt.rect(a.x, a.y, Math.max(fm.advanceWidth(n.text), textPx), fm.height)
        }
        var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9
        for (var k = 0; k < n.pts.length; k++) {
            var q = px(n.pts[k])
            x0 = Math.min(x0, q.x); y0 = Math.min(y0, q.y); x1 = Math.max(x1, q.x); y1 = Math.max(y1, q.y)
        }
        var w = lw * (n.size || 1)
        return Qt.rect(x0 - w, y0 - w, x1 - x0 + 2 * w, y1 - y0 + 2 * w)
    }
    // the topmost shown drawing under a point, or -1
    function hit(x, y) {
        for (var k = shown.length - 1; k >= 0; k--) {
            var b = box(shown[k])
            if (x >= b.x - 6 && x <= b.x + b.width + 6 && y >= b.y - 6 && y <= b.y + b.height + 6) return shown[k].i
        }
        return -1
    }
    function clamp(m) { return [Math.max(0, Math.min(1, m.x / width)), Math.max(0, Math.min(1, m.y / height))] }

    // pictures (a logo) are images over the frame, under the drawn lines; the chosen one has a
    // corner to size it by, its proportions kept
    Repeater {
        model: layer.shown.filter(n => n.kind === "image")
        Image {
            id: logoImg
            objectName: "logo" + modelData.i
            // not `layer`: inside a delegate that name is the Item's own «layer» group (no width),
            // which wins over the root's id here
            readonly property Item area: parent
            readonly property var pts: modelData.pts
            x: pts[0][0] * area.width; y: pts[0][1] * area.height
            width: (pts[1][0] - pts[0][0]) * area.width; height: (pts[1][1] - pts[0][1]) * area.height
            source: "file:///" + modelData.src.replace(/\\/g, "/")
            opacity: (modelData.opacity === undefined ? 1 : modelData.opacity) * (modelData.ghost ? .35 : 1)
            fillMode: Image.Stretch
            smooth: true; mipmap: true
            Rectangle {
                objectName: "logoCorner"
                visible: modelData.i === editor.noteSel && !modelData.ghost
                x: parent.width - 6; y: parent.height - 6; width: 12; height: 12; radius: 3
                color: "#EDEAE3"; border.color: Qt.rgba(0, 0, 0, .85)
                MouseArea {
                    anchors.fill: parent; anchors.margins: -4
                    cursorShape: Qt.SizeFDiagCursor
                    property var from: null
                    onPressed: (m) => { from = { pts: modelData.pts.map(q => [q[0], q[1]]), x: mapToItem(logoImg.area, m.x, m.y).x } }
                    onPositionChanged: (m) => {
                        if (!from) return
                        var p0 = from.pts[0], p1 = from.pts[1], k = (p1[1] - p0[1]) / Math.max(1e-6, p1[0] - p0[0])
                        var x1 = Math.max(p0[0] + 0.02, Math.min(1, p1[0] + (mapToItem(logoImg.area, m.x, m.y).x - from.x) / logoImg.area.width))
                        editor.setNotePoints(modelData.i, [p0, [x1, p0[1] + (x1 - p0[0]) * k]])
                    }
                    onReleased: from = null
                }
            }
        }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        function draw(ctx, n) {
            // a bar pointed at: the other drawings step back to 40 %
            ctx.globalAlpha = (n.ghost ? .35 : 1) * (layer.lit >= 0 && n.i !== layer.lit ? .4 : 1)
            ctx.strokeStyle = ctx.fillStyle = n.color
            ctx.lineWidth = layer.lw * (n.size || 1)
            ctx.lineCap = ctx.lineJoin = "round"
            var p = n.pts.map(layer.px)
            if (n.kind === "rect") {
                ctx.strokeRect(Math.min(p[0].x, p[1].x), Math.min(p[0].y, p[1].y),
                               Math.abs(p[1].x - p[0].x), Math.abs(p[1].y - p[0].y))
            } else if (n.kind === "pen") {
                ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y)
                for (var k = 1; k < p.length; k++) ctx.lineTo(p[k].x, p[k].y)
                ctx.stroke()
            } else if (n.kind === "arrow") {
                var dx = p[1].x - p[0].x, dy = p[1].y - p[0].y, d = Math.max(1e-6, Math.hypot(dx, dy))
                var ux = dx / d, uy = dy / d, len = Math.max(4 * ctx.lineWidth, 0.035 * layer.height * (n.size || 1)), half = len * .55
                var bx = p[1].x - ux * len, by = p[1].y - uy * len
                ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y); ctx.lineTo(bx, by); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(p[1].x, p[1].y)
                ctx.lineTo(bx - uy * half, by + ux * half); ctx.lineTo(bx + uy * half, by - ux * half)
                ctx.closePath(); ctx.fill()
            } else if (n.kind === "text" && n.i !== input.note) {
                ctx.font = "600 " + layer.textPx + "px \"" + Theme.uiFont + "\""
                ctx.textBaseline = "alphabetic"
                ctx.strokeStyle = Qt.color(n.color).hslLightness < .24 ? Qt.rgba(1, 1, 1, .59) : Qt.rgba(0, 0, 0, .59)
                ctx.strokeText(n.text, p[0].x, p[0].y + fm.ascent)
                ctx.fillText(n.text, p[0].x, p[0].y + fm.ascent)
            }
        }
        // a frame around a drawing, dark under light so it reads on white, yellow and black:
        // dashed for the chosen drawing, solid for the one whose bar is pointed at
        function frame(ctx, n, dashed) {
            var b = layer.box(n)
            var x = Math.round(b.x - 4), y = Math.round(b.y - 4), w = Math.round(b.width + 8), h = Math.round(b.height + 8)
            ctx.globalAlpha = 1
            ctx.setLineDash([]); ctx.lineWidth = 2; ctx.strokeStyle = Qt.rgba(0, 0, 0, .85)
            ctx.strokeRect(x, y, w, h)
            ctx.setLineDash(dashed ? [4, 3] : []); ctx.lineWidth = 1; ctx.strokeStyle = "#EDEAE3"
            ctx.strokeRect(x + .5, y + .5, w - 1, h - 1)
            ctx.setLineDash([])
        }
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            for (var k = 0; k < layer.shown.length; k++) draw(ctx, layer.shown[k])
            if (layer.draft) draw(ctx, layer.draft)
            var lit = layer.shown.find(n => n.i === layer.lit && n.i !== editor.noteSel)
            if (lit) frame(ctx, lit, false)
            var sel = layer.shown.find(n => n.i === editor.noteSel)
            if (sel && sel.i !== input.note) frame(ctx, sel, true)
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: layer.tool === "select" ? Qt.ArrowCursor : Qt.CrossCursor
        property var moving: null               // {i, from: [x, y], pts}
        onPressed: (m) => {
            var p = layer.clamp(m)
            if (layer.tool === "select") {
                var i = layer.hit(m.x, m.y)
                editor.selectNote(i)
                // nothing here: the click belongs to the picture below (pause, window drag, fullscreen)
                if (i < 0) { m.accepted = false; return }
                // a copy: what editor.notes gives is a live view, it would move along with the drag
                moving = { i: i, from: p, pts: editor.notes[i].pts.map(q => [q[0], q[1]]) }
            } else if (layer.tool === "text") {
                if (!player.paused) player.togglePause()   // a drawing belongs to the frame it is drawn on
                input.start(editor.addNote("text", [p], layer.ink.toString(), 1))
            } else {
                if (!player.paused) player.togglePause()
                layer.draft = { kind: layer.tool, color: layer.ink.toString(), size: layer.size, pts: [p, p], text: "", i: -1 }
            }
        }
        onPositionChanged: (m) => {
            var p = layer.clamp(m)
            if (moving) {
                var dx = p[0] - moving.from[0], dy = p[1] - moving.from[1]
                editor.setNotePoints(moving.i, moving.pts.map(q => [q[0] + dx, q[1] + dy]))
            } else if (layer.draft) {
                var d = layer.draft, last = d.pts[d.pts.length - 1]
                if (d.kind !== "pen") d.pts[1] = p
                else if (Math.hypot((p[0] - last[0]) * width, (p[1] - last[1]) * height) > 3) d.pts.push(p)
                canvas.requestPaint()
            }
        }
        onReleased: {
            var d = layer.draft
            layer.draft = null
            moving = null
            if (!d) return
            var b = layer.box(d)
            // a click without a drag is not a drawing
            var w = 2 * layer.lw * d.size
            if (b.width - w > 4 || b.height - w > 4) editor.addNote(d.kind, d.pts, d.color, d.size)
            canvas.requestPaint()
        }
        onDoubleClicked: (m) => {
            var i = layer.hit(m.x, m.y)
            if (layer.tool === "select" && i >= 0 && editor.notes[i].kind === "text") input.start(i)
        }
        onWheel: (w) => w.accepted = false
    }

    // the chosen drawing: its name and times on a plate of the accent over it (Argon's v1, 01.11),
    // and a rectangle's corners, an arrow's ends to take and move
    readonly property var chosen: shown.find(n => n.i === editor.noteSel && !n.ghost) || null
    function mmss(t) {
        var s = Math.max(0, Math.round(t)), two = (v) => (v < 10 ? "0" : "") + v
        return two(Math.floor(s / 60)) + ":" + two(s % 60)
    }
    Rectangle {
        objectName: "noteLabel"
        readonly property rect b: layer.chosen ? layer.box(layer.chosen) : Qt.rect(0, 0, 0, 0)
        visible: layer.chosen !== null && input.note < 0
        x: Math.max(0, Math.min(layer.width - width, b.x - 4))
        // over the frame round the drawing; under it where the draw bar or the picture's top would hide it
        y: b.y - 4 - height - 4 >= layer.topClear ? b.y - 4 - height - 4 : b.y + b.height + 8
        width: labelText.implicitWidth + 14; height: 18; radius: 4
        color: Theme.acc
        Text {
            id: labelText
            anchors.centerIn: parent
            text: layer.chosen ? (L.t["tl_" + layer.chosen.kind] || L.t.tl_drawings) + " • "
                                 + layer.mmss(layer.chosen.a) + "–" + layer.mmss(layer.chosen.b) : ""
            color: Theme.inkOnAcc; font.family: Theme.uiFont; font.pixelSize: 11; font.weight: Font.DemiBold
        }
    }
    Repeater {
        // [which point's x, which point's y]: a rectangle's four corners, an arrow's two ends
        model: !layer.chosen || input.note >= 0 ? []
               : layer.chosen.kind === "rect" ? [[0, 0], [1, 0], [0, 1], [1, 1]]
               : layer.chosen.kind === "arrow" ? [[0, 0], [1, 1]] : []
        Rectangle {
            objectName: "noteHandle" + index
            readonly property var n: layer.chosen
            x: n.pts[modelData[0]][0] * layer.width - 4
            y: n.pts[modelData[1]][1] * layer.height - 4
            width: 8; height: 8
            color: "#FFFFFF"; border.color: Qt.rgba(0, 0, 0, .85)
            MouseArea {
                anchors.fill: parent; anchors.margins: -5
                cursorShape: Qt.CrossCursor
                onPositionChanged: (m) => {
                    if (!pressed) return
                    var p = layer.clamp(mapToItem(layer, m.x, m.y)), n = parent.n
                    var pts = n.pts.map(q => [q[0], q[1]])
                    pts[modelData[0]][0] = p[0]
                    pts[modelData[1]][1] = p[1]
                    editor.setNotePoints(n.i, pts)
                }
            }
        }
    }

    // typing a text drawing in place
    TextInput {
        id: input
        property int note: -1
        visible: note >= 0
        width: Math.max(implicitWidth, layer.textPx)
        font: fm.font
        color: note >= 0 ? editor.notes[note].color : "white"
        selectByMouse: true
        function start(i) {
            if (i < 0) return
            note = i
            var p = layer.px(editor.notes[i].pts[0])
            x = p.x; y = p.y
            text = editor.notes[i].text
            forceActiveFocus()
            selectAll()
            canvas.requestPaint()
        }
        function finish() {
            if (note < 0) return
            var i = note
            note = -1
            focus = false
            editor.setNoteText(i, text)
        }
        onAccepted: finish()
        onActiveFocusChanged: if (!activeFocus) finish()
        Keys.onEscapePressed: {
            text = editor.notes[note].text      // back to what it was; an empty new text goes away
            finish()
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -4
            color: "transparent"; border.color: "#EDEAE3"; radius: 3; opacity: .7
        }
    }
}
