pragma Singleton
import QtQuick

// Warm graphite + one orange accent. Nothing else is coloured unless it
// means something (battery, danger, the user's lightbar colour).
QtObject {
    readonly property string font: "Inter"
    readonly property string mono: "JetBrains Mono"

    readonly property color accent: "#ff6a1f"
    readonly property color accentHover: "#ff7f3d"
    readonly property color accentSoft: Qt.rgba(1, 0.416, 0.122, 0.14)
    readonly property color accentText: "#ff8a4c"

    readonly property color bg: "#141316"
    readonly property color sidebar: "#141316"
    readonly property color surface: "#1d1c20"
    readonly property color surface2: "#262529"
    readonly property color surfaceHover: "#2e2d32"
    readonly property color border: "#2a292e"
    readonly property color borderStrong: "#3a393f"
    readonly property color text: "#f3f1ee"
    readonly property color textDim: "#9c99a0"
    readonly property color textFaint: "#66636b"
    readonly property color ok: "#4cc38a"
    readonly property color warn: "#f2b84b"
    readonly property color danger: "#f0524f"

    readonly property int radius: 20
    readonly property int radiusSmall: 12
    readonly property int gap: 20

    readonly property int fontH1: 30
    readonly property int fontH2: 19
    readonly property int fontBody: 15
    readonly property int fontSmall: 13

    readonly property int fast: 140
    readonly property int normal: 220
    readonly property int slow: 420

    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
    function hex(c) {
        function h(v) { var s = Math.round(v * 255).toString(16); return s.length < 2 ? "0" + s : s }
        return "#" + h(c.r) + h(c.g) + h(c.b)
    }
    // PlayStation face buttons, muted to sit on graphite
    function glyphColor(b) {
        return ({cross: "#8fb0e8", circle: "#e88a8a", triangle: "#7fcfb4", square: "#d9a0c8"})[b] || "#c9c6cc"
    }
}
