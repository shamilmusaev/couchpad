import QtQuick

// "Share + ✕" style button badge.
Row {
    property string button
    property string glyph
    property bool share: true
    spacing: 6
    Rectangle {
        visible: parent.share
        width: 62; height: 30; radius: 15
        color: Theme.surface2; border.color: Theme.border
        Text { anchors.centerIn: parent; text: "Share +"; color: Theme.textDim; font.pixelSize: 12; font.weight: Font.Medium }
    }
    Rectangle {
        width: Math.max(30, g.implicitWidth + 16); height: 30; radius: 15
        color: Theme.alpha(Theme.glyphColor(parent.button), 0.16)
        border.color: Theme.alpha(Theme.glyphColor(parent.button), 0.5)
        Text {
            id: g
            anchors.centerIn: parent
            text: parent.parent.glyph
            color: Theme.glyphColor(parent.parent.button)
            font.pixelSize: text.length > 2 ? 12 : 15
            font.weight: Font.Bold
        }
    }
}
