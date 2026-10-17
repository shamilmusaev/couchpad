import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property alias text: t.text
    property alias subtitle: s.text
    spacing: 4
    Layout.fillWidth: true
    Text {
        id: t
        color: Theme.text
        font.pixelSize: Theme.fontH2
        font.weight: Font.DemiBold
    }
    Text {
        id: s
        visible: text !== ""
        color: Theme.textDim
        font.pixelSize: Theme.fontSmall + 1
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
