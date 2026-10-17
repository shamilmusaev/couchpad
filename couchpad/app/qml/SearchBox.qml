import QtQuick
import QtQuick.Controls.Basic

// Settings search: type, pick a result, land on its page.
Item {
    id: sb
    property var index: []
    signal chosen(int page)
    readonly property bool open: results.visible
    height: 48

    readonly property var hits: {
        var q = field.text.trim().toLowerCase()
        if (!q) return []
        return index.filter(function (e) { return e.t.toLowerCase().indexOf(q) >= 0 }).slice(0, 7)
    }

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: Theme.surface
        border.color: field.activeFocus ? Theme.alpha(Theme.accent, 0.6) : Theme.border
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        Icon {
            id: glass
            x: 16
            anchors.verticalCenter: parent.verticalCenter
            name: "ph:magnifying-glass"
            size: 18
            mono: true
        }
        TextField {
            id: field
            anchors.left: glass.right
            anchors.right: parent.right
            anchors.leftMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            placeholderText: L.t("Поиск по настройкам")
            placeholderTextColor: Theme.textFaint
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: 15
            background: Item {}
            activeFocusOnTab: false
            Keys.onDownPressed: if (sb.hits.length) list.forceActiveFocus()
            Keys.onReturnPressed: if (sb.hits.length) sb.pick(0)
            Keys.onEscapePressed: { text = ""; focus = false }
        }
    }
    function pick(i) {
        var p = hits[i].p
        field.text = ""
        field.focus = false
        chosen(p)
    }

    Rectangle {
        id: results
        visible: sb.hits.length > 0
        y: sb.height + 8
        width: sb.width
        height: list.contentHeight + 12
        radius: 14
        color: "#1f1e23"
        border.color: Theme.borderStrong
        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 6
            interactive: false
            model: sb.hits
            keyNavigationEnabled: true
            Keys.onReturnPressed: sb.pick(currentIndex)
            Keys.onEscapePressed: field.forceActiveFocus()
            highlight: Rectangle { radius: 10; color: Theme.accentSoft }
            highlightMoveDuration: 80
            delegate: Item {
                width: list.width
                height: 42
                Text {
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.t
                    color: Theme.text
                    font.family: Theme.font
                    font.pixelSize: 14
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.pages[modelData.p].title
                    color: Theme.textFaint
                    font.family: Theme.font
                    font.pixelSize: 12
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: list.currentIndex = index
                    onClicked: sb.pick(index)
                }
            }
        }
    }
}
