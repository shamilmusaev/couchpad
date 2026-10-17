import QtQuick
import QtQuick.Layouts

// Row of colour presets. `none` adds an "off" swatch (value "").
FocusScope {
    id: sw
    property var colors: ["#1e6bff", "#00b7ff", "#00e0a4", "#3ad14a", "#ffd200", "#ff6a1f", "#ff3b30", "#ffffff"]
    property string current: ""
    property bool none: false
    signal picked(string c)
    readonly property var all: none ? [""].concat(colors) : colors
    property int idx: Math.max(0, all.indexOf(current.toLowerCase()))
    activeFocusOnTab: true
    Layout.fillWidth: true
    implicitWidth: 300
    implicitHeight: row.implicitHeight
    function padLeft() { picked(all[Math.max(0, idx - 1)]) }
    function padRight() { picked(all[Math.min(all.length - 1, idx + 1)]) }
    Keys.onLeftPressed: padLeft()
    Keys.onRightPressed: padRight()
    Flow {
        id: row
        width: sw.width
        spacing: 10
        Repeater {
            model: sw.all
            Rectangle {
                readonly property bool sel: sw.current.toLowerCase() === modelData
                width: 34; height: 34; radius: 17
                color: modelData || "transparent"
                border.color: sel ? "white" : modelData ? Theme.alpha("#ffffff", 0.15) : Theme.borderStrong
                border.width: sel ? 3 : 1
                scale: sel ? 1.12 : ma.containsMouse ? 1.08 : 1
                Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutBack } }
                Text { visible: !modelData; anchors.centerIn: parent; text: "∅"; color: Theme.textDim; font.pixelSize: 16 }
                MouseArea {
                    id: ma
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { sw.forceActiveFocus(); sw.picked(modelData) }
                }
            }
        }
    }
    Rectangle {
        anchors.fill: row
        anchors.margins: -6
        radius: 22
        color: "transparent"
        border.width: 2
        border.color: Theme.accentText
        opacity: sw.activeFocus && root.padActive ? 1 : 0
    }
}
