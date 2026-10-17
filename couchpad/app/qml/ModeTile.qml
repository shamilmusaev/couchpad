import QtQuick
import QtQuick.Layouts

Rectangle {
    id: t
    property string icon
    property string label
    property string sub
    property bool selected: false
    property var swatch: null              // optional gradient preview colours
    signal clicked()
    function padAccept() { clicked() }
    activeFocusOnTab: true
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Layout.fillWidth: true
    implicitHeight: 84
    radius: 14
    color: selected ? Theme.accentSoft : ma.containsMouse ? Theme.surfaceHover : Theme.surface2
    border.color: selected ? Theme.accent : Theme.border
    border.width: selected ? 2 : 1
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    FocusRing { target: t }
    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12
        Rectangle {
            width: 40; height: 40; radius: 20
            color: Theme.bg
            border.color: Theme.border
            gradient: t.swatch ? grad : null
            Gradient {
                id: grad
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: t.swatch ? t.swatch[0] : "black" }
                GradientStop { position: 0.5; color: t.swatch && t.swatch.length > 2 ? t.swatch[1] : (t.swatch ? t.swatch[0] : "black") }
                GradientStop { position: 1; color: t.swatch ? t.swatch[t.swatch.length - 1] : "black" }
            }
            Icon { anchors.centerIn: parent; name: t.swatch ? "" : t.icon; size: 22; visible: !t.swatch; mono: true; monoColor: Theme.text }
        }
        ColumnLayout {
            spacing: 2
            Layout.fillWidth: true
            Text { text: t.label; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
            Text { text: t.sub; color: Theme.textDim; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { t.forceActiveFocus(); t.clicked() }
    }
}
