import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: sw
    padding: 0
    spacing: 0
    implicitWidth: 52
    implicitHeight: 30
    property real radius: 15
    function padAccept() { toggle(); toggled() }
    indicator: Rectangle {
        width: 52; height: 30; radius: 15
        color: sw.checked ? Theme.accent : Theme.surface2
        border.color: sw.checked ? Qt.lighter(Theme.accent, 1.2) : Theme.borderStrong
        Behavior on color { ColorAnimation { duration: Theme.normal } }
        Rectangle {
            width: 22; height: 22; radius: 11
            y: 4
            x: sw.checked ? 26 : 4
            color: "white"
            scale: sw.pressed ? 0.88 : 1
            Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
            Behavior on scale { NumberAnimation { duration: Theme.fast } }
        }
        FocusRing { target: sw }
    }
    contentItem: Item {}
}
