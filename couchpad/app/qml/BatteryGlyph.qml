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
    Icon {
        visible: bg.charging
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: -2
        name: "ph-fill:lightning"; size: 13; tint: "#ffffff"
    }
    SequentialAnimation on opacity {          // breathes while charging
        running: bg.charging && bg.visible
        loops: Animation.Infinite
        onStopped: bg.opacity = 1
        NumberAnimation { to: 0.55; duration: 900; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
    }
}
