import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Button {
    id: b
    property string kind: "normal"         // normal | accent | ghost | danger
    property string iconName: ""
    property real radius: Theme.radiusSmall
    function padAccept() { clicked() }
    implicitHeight: 42
    leftPadding: 18
    rightPadding: 18
    font.pixelSize: Theme.fontBody - 1
    font.weight: Font.Medium
    hoverEnabled: true

    background: Rectangle {
        radius: b.radius
        color: {
            if (!b.enabled) return Theme.surface2
            if (b.kind === "accent") return b.down ? Qt.darker(Theme.accent, 1.2) : b.hovered ? Qt.lighter(Theme.accent, 1.12) : Theme.accent
            if (b.kind === "danger") return b.down ? Qt.darker(Theme.danger, 1.3) : b.hovered ? Theme.alpha(Theme.danger, 0.32) : Theme.alpha(Theme.danger, 0.18)
            if (b.kind === "ghost") return b.down ? Theme.surface2 : b.hovered ? Theme.surfaceHover : "transparent"
            return b.down ? Theme.surface : b.hovered ? Theme.surfaceHover : Theme.surface2
        }
        border.color: b.kind === "ghost" || b.kind === "normal" ? Theme.border : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        scale: b.down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
        FocusRing { target: b }
    }
    contentItem: RowLayout {
        spacing: 8
        opacity: b.enabled ? 1 : 0.45
        Icon {
            visible: b.iconName !== ""
            name: b.iconName
            size: 18
            mono: true
            monoColor: b.kind === "accent" ? "#ffffff" : b.kind === "danger" ? "#ff8f8c" : Theme.text
        }
        Text {
            text: b.text
            font: b.font
            color: b.kind === "accent" ? "white" : b.kind === "danger" ? "#ff8f8c" : Theme.text
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
