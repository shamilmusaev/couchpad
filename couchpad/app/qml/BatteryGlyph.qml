import QtQuick

Item {
    id: bg
    property int level: 0
    property bool charging: false
    readonly property color fill: charging ? Theme.ok : level <= 15 ? Theme.danger : level <= 30 ? Theme.warn : Theme.ok
    width: 30; height: 15
    Rectangle {
        width: 27; height: 15; radius: 4
        color: "transparent"
        border.color: Theme.textDim
        border.width: 1.5
        Rectangle {
            x: 3; y: 3
            height: 9; radius: 2
            width: Math.max(2, 21 * bg.level / 100)
            color: bg.fill
            Behavior on width { NumberAnimation { duration: Theme.slow } }
        }
    }
    Rectangle { x: 27; y: 5; width: 3; height: 5; radius: 1; color: Theme.textDim }
    Text {
        visible: bg.charging
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: -2
        text: "⚡"
        color: "white"
        font.pixelSize: 11
    }
}
