import QtQuick

// One-of-N picker with a sliding highlight. model: [{value, label, icon?}]
FocusScope {
    id: seg
    property var model: []
    property var current
    property real radius: Theme.radiusSmall
    property bool stretch: false          // share the given width equally
    signal picked(var value)
    activeFocusOnTab: true
    implicitHeight: 44
    implicitWidth: stretch ? 240 : row.implicitWidth + 8
    readonly property int index: {
        for (var i = 0; i < model.length; i++) if (model[i].value === current) return i
        return 0
    }
    function padLeft() { if (index > 0) picked(model[index - 1].value) }
    function padRight() { if (index < model.length - 1) picked(model[index + 1].value) }
    Keys.onLeftPressed: padLeft()
    Keys.onRightPressed: padRight()

    Rectangle {
        anchors.fill: parent
        radius: seg.radius
        color: Theme.surface2
        border.color: Theme.border
        FocusRing { target: seg }
    }
    Rectangle {
        id: hl
        property Item tgt: rep.count > seg.index ? rep.itemAt(seg.index) : null
        x: tgt ? tgt.x + 4 : 4
        y: 4
        width: tgt ? tgt.width : 0
        height: seg.height - 8
        radius: seg.radius - 3
        color: Theme.accent
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    }
    Row {
        id: row
        x: 4
        anchors.verticalCenter: parent.verticalCenter
        Repeater {
            id: rep
            model: seg.model
            delegate: Item {
                width: seg.stretch ? (seg.width - 8) / seg.model.length
                                   : lbl.implicitWidth + (ic.visible ? 26 : 0) + 32
                height: seg.height - 8
                Row {
                    anchors.centerIn: parent
                    spacing: 8
                    Icon {
                        id: ic
                        visible: !!modelData.icon
                        name: modelData.icon || ""
                        size: 18
                        anchors.verticalCenter: parent.verticalCenter
                        mono: true
                        monoColor: index === seg.index ? "#ffffff" : Theme.textDim
                    }
                    Text {
                        id: lbl
                        text: modelData.label
                        anchors.verticalCenter: parent.verticalCenter
                        color: index === seg.index ? "white" : ma.containsMouse ? Theme.text : Theme.textDim
                        font.pixelSize: Theme.fontBody - 1
                        font.weight: index === seg.index ? Font.DemiBold : Font.Normal
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                    }
                }
                MouseArea {
                    id: ma
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { seg.forceActiveFocus(); seg.picked(modelData.value) }
                }
            }
        }
    }
}
