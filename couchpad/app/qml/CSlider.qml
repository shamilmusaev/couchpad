import QtQuick
import QtQuick.Controls.Basic

// Slider with a value bubble; `format(v)` makes the label.
Slider {
    id: sl
    property var format: function (v) { return v.toFixed(2) }
    property real radius: 10
    implicitWidth: 300
    implicitHeight: 40
    padding: 0
    function padLeft() { decrease(); moved() }
    function padRight() { increase(); moved() }

    background: Item {
        x: sl.leftPadding
        width: sl.availableWidth - 84
        height: sl.height
        Rectangle {
            id: track
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: 6
            radius: 3
            color: Theme.surface2
            Rectangle {
                width: sl.visualPosition * parent.width
                height: parent.height
                radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Qt.darker(Theme.accent, 1.25) }
                    GradientStop { position: 1; color: Theme.accent }
                }
            }
        }
        FocusRing { target: sl; anchors.margins: -6 }
    }
    handle: Rectangle {
        x: sl.leftPadding + sl.visualPosition * (sl.availableWidth - 84 - width)
        anchors.verticalCenter: parent.verticalCenter
        width: 22; height: 22; radius: 11
        color: "white"
        border.color: Theme.accent
        border.width: sl.pressed ? 6 : 3
        scale: sl.pressed ? 1.15 : (hover.hovered ? 1.07 : 1)
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
        Behavior on border.width { NumberAnimation { duration: Theme.fast } }
        HoverHandler { id: hover }
    }
    Text {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 76
        horizontalAlignment: Text.AlignRight
        text: sl.format(sl.value)
        color: sl.pressed ? Theme.accentText : Theme.textDim
        font.pixelSize: Theme.fontSmall + 1
        font.weight: Font.Medium
        font.features: { "tnum": 1 }
    }
}
