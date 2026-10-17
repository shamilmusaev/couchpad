import QtQuick

// Hue ring + centre swatch. `value` in, `picked(color)` out.
FocusScope {
    id: cp
    property color value: "#ff6a1f"
    signal picked(color c)
    property real radius: width / 2
    readonly property real hue: Math.max(0, value.hsvHue)
    readonly property real sat: value.hsvSaturation
    activeFocusOnTab: true
    implicitWidth: 236
    implicitHeight: 236
    function setHue(h) { picked(Qt.hsva((h + 1) % 1, sat < 0.05 ? 1 : sat, 1, 1)) }
    function padLeft() { setHue(hue - 1 / 72) }
    function padRight() { setHue(hue + 1 / 72) }
    Keys.onLeftPressed: padLeft()
    Keys.onRightPressed: padRight()

    Canvas {
        id: wheel
        anchors.fill: parent
        antialiasing: true
        renderStrategy: Canvas.Immediate
        onPaint: {
            var ctx = getContext("2d")
            var c = width / 2, ro = c - 4, ri = c - 34
            ctx.reset()
            for (var a = 0; a < 360; a += 1) {
                var a0 = (a - 90.6) * Math.PI / 180, a1 = (a - 89) * Math.PI / 180
                ctx.beginPath()
                ctx.arc(c, c, ro, a0, a1)
                ctx.arc(c, c, ri, a1, a0, true)
                ctx.closePath()
                ctx.fillStyle = Qt.hsva(a / 360, 1, 1, 1)
                ctx.fill()
            }
        }
    }
    // knob
    Rectangle {
        readonly property real ang: (cp.hue * 360 - 90) * Math.PI / 180
        readonly property real rr: cp.width / 2 - 19
        x: cp.width / 2 + rr * Math.cos(ang) - width / 2
        y: cp.height / 2 + rr * Math.sin(ang) - height / 2
        width: 30; height: 30; radius: 15
        color: Qt.hsva(cp.hue, 1, 1, 1)
        border.color: "white"
        border.width: 4
        scale: drag.pressed ? 1.15 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
    }
    // centre swatch with glow
    Rectangle {
        anchors.centerIn: parent
        width: parent.width - 96; height: width; radius: width / 2
        color: cp.value
        border.color: Theme.alpha("#ffffff", 0.25)
        border.width: 2
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Text {
            anchors.centerIn: parent
            text: Theme.hex(cp.value).toUpperCase()
            color: cp.value.hslLightness > 0.62 ? "#141316" : "white"
            font.pixelSize: 15
            font.weight: Font.DemiBold
            font.family: Theme.mono
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -5
        radius: width / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.accentText
        opacity: cp.activeFocus && root.padActive ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    MouseArea {
        id: drag
        anchors.fill: parent
        cursorShape: Qt.CrossCursor
        function pick(m) {
            var dx = m.x - width / 2, dy = m.y - height / 2
            if (Math.sqrt(dx * dx + dy * dy) < width / 2 - 52 && !pressed) return
            var h = (Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360
            cp.setHue(h / 360)
        }
        onPressed: (m) => { cp.forceActiveFocus(); pick(m) }
        onPositionChanged: (m) => { if (pressed) pick(m) }
    }
}
