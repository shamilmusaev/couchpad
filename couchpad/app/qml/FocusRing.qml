import QtQuick

// Glowing outline for keyboard / gamepad focus.
Rectangle {
    property Item target: parent
    property bool shown: target.visualFocus === true || (target.activeFocus && root.padActive)
    anchors.fill: parent
    anchors.margins: -4
    radius: (target.radius !== undefined ? target.radius : Theme.radiusSmall) + 4
    color: "transparent"
    border.width: 2
    border.color: Theme.accentText
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
}
