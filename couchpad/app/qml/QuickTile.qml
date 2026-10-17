import QtQuick
import QtQuick.Layouts

// Big focusable action tile.
Rectangle {
    id: tile
    property string icon
    property string label
    property string sub: ""
    property bool active: false
    property bool mono: true
    signal clicked()
    function padAccept() { clicked() }
    activeFocusOnTab: true
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Layout.fillWidth: true
    implicitHeight: 104
    radius: Theme.radius
    color: active ? Theme.accentSoft : ma.pressed ? Theme.surface2 : ma.containsMouse ? Theme.surface2 : Theme.surface
    border.color: active ? Theme.alpha(Theme.accent, 0.6) : "transparent"
    scale: ma.pressed ? 0.97 : 1
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on scale { NumberAnimation { duration: Theme.fast } }
    FocusRing { target: tile }
    Column {
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        Icon { name: tile.icon; size: 26; mono: tile.mono; monoColor: Theme.text }
        Text { text: tile.label; color: Theme.text; font.pixelSize: Theme.fontBody - 1; font.weight: Font.Medium; width: tile.width - 36; elide: Text.ElideRight }
        Text { visible: tile.sub !== ""; text: tile.sub; color: Theme.textDim; font.pixelSize: 12; width: tile.width - 36; elide: Text.ElideRight }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { tile.forceActiveFocus(); tile.clicked() }
    }
}
