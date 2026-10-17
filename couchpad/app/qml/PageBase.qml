import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Flickable {
    id: page
    property int index
    readonly property bool current: root.page === index
    readonly property bool isPageFlick: true
    default property alias body: col.data
    property bool showTitle: true
    property real shift: current ? 0 : 24
    anchors.fill: parent
    contentWidth: width
    contentHeight: col.y + col.implicitHeight + 40
    boundsBehavior: Flickable.StopAtBounds
    flickDeceleration: 4000
    clip: true
    opacity: current ? 1 : 0
    visible: opacity > 0.01
    enabled: current
    Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    Behavior on shift { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
        contentItem: Rectangle { implicitWidth: 6; radius: 3; color: Theme.alpha(Theme.text, 0.18) }
    }
    function scrollTo(y) { scroller.to = y; scroller.restart() }
    NumberAnimation { id: scroller; target: page; property: "contentY"; duration: Theme.normal; easing.type: Easing.OutCubic }
    onCurrentChanged: if (current) contentY = 0

    ColumnLayout {
        id: head
        visible: page.showTitle
        x: 16
        y: 4 + page.shift
        width: page.width - 56
        spacing: 6
        Text {
            text: root.pages[page.index].title
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: 32
            font.weight: Font.DemiBold
        }
        Text {
            text: root.pages[page.index].sub
            color: Theme.textDim
            font.family: Theme.font
            font.pixelSize: 15
        }
    }
    ColumnLayout {
        id: col
        x: 16
        y: (page.showTitle ? head.height + 28 : 0) + 4 + page.shift
        width: page.width - 56
        spacing: Theme.gap
    }
}
