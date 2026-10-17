import QtQuick

Item {
    id: ring
    property int level: 0
    property bool charging: false
    property real shown: level
    readonly property color col: charging ? Theme.ok : level <= 15 ? Theme.danger : level <= 30 ? Theme.warn : Theme.ok
    width: 96; height: 96
    Behavior on shown { NumberAnimation { duration: 900; easing.type: Easing.OutCubic } }
    onShownChanged: cv.requestPaint()
    onColChanged: cv.requestPaint()
    Canvas {
        id: cv
        anchors.fill: parent
        antialiasing: true
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var c = width / 2, r = c - 7
            ctx.lineWidth = 9
            ctx.lineCap = "round"
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.08)
            ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.stroke()
            ctx.strokeStyle = ring.col
            ctx.beginPath()
            ctx.arc(c, c, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.max(0.01, ring.shown / 100))
            ctx.stroke()
        }
    }
    Column {
        anchors.centerIn: parent
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Math.round(ring.shown) + "%"
            color: Theme.text
            font.pixelSize: 22
            font.weight: Font.Bold
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: ring.charging ? L.t("⚡ зарядка") : L.t("заряд")
            color: Theme.textDim
            font.pixelSize: 11
        }
    }
}
