import QtQuick

// Theme icon through the Python image provider; `tint` paints it one colour.
Item {
    property string name: ""
    property string tint: ""
    property bool mono: false             // flat glyph in monoColor (themes differ a lot)
    property color monoColor: Theme.textDim
    readonly property string effTint: tint || (mono ? Theme.hex(monoColor) : "")
    property int size: 22
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    Image {
        anchors.fill: parent
        sourceSize: Qt.size(parent.size * 2, parent.size * 2)
        smooth: true
        fillMode: Image.PreserveAspectFit
        source: parent.name ? "image://icon/" + parent.name + (parent.effTint ? "?" + parent.effTint : "") : ""
    }
}
