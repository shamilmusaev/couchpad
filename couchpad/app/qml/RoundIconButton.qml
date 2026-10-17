import QtQuick

// 44 px round icon button for the top bar. `on` = accent dot.
Rectangle {
    id: b
    property string icon
    property bool on: false
    property color swatch: "transparent"
    signal clicked()
    width: 44; height: 44; radius: 22
    color: ma.containsMouse ? Theme.surface2 : Theme.surface
    border.color: on ? Theme.alpha(Theme.accent, 0.6) : Theme.border
    opacity: enabled ? 1 : 0.45
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Icon {
        anchors.centerIn: parent
        name: b.icon
        size: 20
        mono: true
        monoColor: b.on ? Theme.accent : Theme.text
    }
    Rectangle {           // status dot (like the notification dot in the reference)
        visible: b.on || b.swatch.a > 0
        x: parent.width - 13; y: 6
        width: 9; height: 9; radius: 5
        color: b.swatch.a > 0 ? b.swatch : Theme.accent
        border.color: Theme.bg
        border.width: 2
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: b.clicked()
    }
}
