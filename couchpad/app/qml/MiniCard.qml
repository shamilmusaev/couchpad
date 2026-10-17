import QtQuick
import QtQuick.Layouts

// Small shortcut card under the hero's side card.
Rectangle {
    id: mc
    property string title
    property string sub
    property string icon: ""
    property string swatch: ""
    signal clicked()
    function padAccept() { clicked() }
    activeFocusOnTab: true
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Layout.fillWidth: true
    Layout.preferredHeight: 92
    radius: 16
    color: ma.containsMouse ? Theme.surface2 : Theme.surface
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    FocusRing { target: mc }
    Rectangle {
        visible: mc.swatch !== ""
        x: 16; y: 16
        width: 20; height: 20; radius: 10
        color: mc.swatch || "transparent"
        border.color: Qt.rgba(1, 1, 1, 0.2)
    }
    Icon {
        visible: mc.swatch === "" && mc.icon !== ""
        x: 16; y: 16
        name: mc.icon
        size: 20
        mono: true
        monoColor: Theme.text
    }
    Column {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 16
        spacing: 2
        Text { text: mc.title; color: Theme.text; font.pixelSize: 14; font.weight: Font.Medium }
        Text { text: mc.sub; color: Theme.textDim; font.pixelSize: 12 }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { mc.forceActiveFocus(); mc.clicked() }
    }
}
