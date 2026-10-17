import QtQuick
import QtQuick.Layouts

// Title + subtitle on the left, a control on the right.
RowLayout {
    id: row
    property string title
    property string subtitle
    property string icon
    default property alias control: slot.data
    spacing: 16
    Layout.fillWidth: true
    Layout.minimumHeight: 52

    Rectangle {
        visible: row.icon !== ""
        width: 40; height: 40; radius: 12
        color: Theme.surface2
        Layout.alignment: Qt.AlignVCenter
        Icon { anchors.centerIn: parent; name: row.icon; size: 20; mono: true; monoColor: Theme.text }
    }
    ColumnLayout {
        spacing: 3
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        Text {
            text: row.title
            color: Theme.text
            font.pixelSize: Theme.fontBody
            font.weight: Font.Medium
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            visible: row.subtitle !== ""
            text: row.subtitle
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
    Item {
        id: slot
        Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
        implicitWidth: childrenRect.width
        implicitHeight: childrenRect.height
    }
}
