import QtQuick
import QtQuick.Controls.Basic

// model: [{value, label, icon?}]; `current` = selected value.
ComboBox {
    id: cb
    property var current
    property real radius: Theme.radiusSmall
    signal picked(var value)
    textRole: "label"
    valueRole: "value"
    implicitWidth: 260
    implicitHeight: 42
    font.pixelSize: Theme.fontBody - 1
    currentIndex: {
        var m = model || []
        for (var i = 0; i < m.length; i++) if (m[i].value === current) return i
        return 0
    }
    onActivated: (i) => picked(valueAt(i))
    function padLeft() { if (currentIndex > 0) { currentIndex--; picked(valueAt(currentIndex)) } }
    function padRight() { if (currentIndex < count - 1) { currentIndex++; picked(valueAt(currentIndex)) } }
    function padAccept() { popup.open() }

    background: Rectangle {
        radius: cb.radius
        color: cb.hovered ? Theme.surfaceHover : Theme.surface2
        border.color: cb.popup.visible ? Theme.accent : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        FocusRing { target: cb }
    }
    contentItem: Row {
        leftPadding: 14
        spacing: 10
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            visible: cb.currentIndex >= 0 && !!cb.model[cb.currentIndex] && !!cb.model[cb.currentIndex].icon
            name: visible ? cb.model[cb.currentIndex].icon : ""
            size: 18
            mono: true
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: cb.width - 70
            text: cb.displayText
            font: cb.font
            color: Theme.text
            elide: Text.ElideRight
        }
    }
    indicator: Text {
        x: cb.width - width - 14
        anchors.verticalCenter: parent.verticalCenter
        text: "⌄"
        color: Theme.textDim
        font.pixelSize: 18
        rotation: cb.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.fast } }
    }
    delegate: ItemDelegate {
        id: d
        width: cb.popup.width - 12
        x: 6
        height: 40
        highlighted: cb.highlightedIndex === index
        contentItem: Row {
            spacing: 10
            Icon { anchors.verticalCenter: parent.verticalCenter; visible: !!modelData.icon; name: modelData.icon || ""; size: 18; mono: true }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.label
                color: cb.currentIndex === index ? Theme.accentText : Theme.text
                font.pixelSize: Theme.fontBody - 1
                font.weight: cb.currentIndex === index ? Font.DemiBold : Font.Normal
            }
        }
        background: Rectangle {
            radius: 8
            color: d.highlighted ? Theme.surfaceHover : "transparent"
        }
    }
    popup: Popup {
        y: cb.height + 6
        width: Math.max(cb.width, 300)
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 420)
        padding: 6
        onOpened: root.popupOpen = true
        onClosed: root.popupOpen = false
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.fast; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 100 } }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: cb.popup.visible ? cb.delegateModel : null
            currentIndex: cb.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: 12
            color: "#232227"
            border.color: Theme.borderStrong
        }
    }
}
