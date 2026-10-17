import QtQuick

Rectangle {
    id: card
    default property alias content: inner.data
    property int padding: 22
    property bool hoverable: false
    property alias hovered: hover.hovered
    color: Theme.surface
    radius: Theme.radius
    border.color: hover.hovered && hoverable ? Theme.border : "transparent"
    border.width: 1
    implicitHeight: inner.childrenRect.height + padding * 2
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }

    HoverHandler { id: hover }
    Item {
        id: inner
        anchors.fill: parent
        anchors.margins: card.padding
    }
}
