import QtQuick

// In-app toasts (bottom right).
Item {
    id: host
    anchors.fill: parent
    z: 2000
    function push(title, body, kind) {
        toastModel.append({title: title, body: body || "", kind: kind || "info", born: Date.now()})
        if (toastModel.count > 4) toastModel.remove(0)
    }
    ListModel { id: toastModel }
    Column {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 24
        anchors.bottomMargin: 64
        spacing: 10
        Repeater {
            model: toastModel
            delegate: Rectangle {
                id: t
                width: 360
                height: col.implicitHeight + 28
                radius: 14
                color: "#232227"
                border.color: Theme.alpha(kc, 0.55)
                readonly property color kc: kind === "ok" ? Theme.ok : kind === "warn" ? Theme.warn : kind === "error" ? Theme.danger : Theme.accent
                opacity: 0
                property real slide: 40
                transform: Translate { x: t.slide }
                Component.onCompleted: appear.start()
                ParallelAnimation {
                    id: appear
                    NumberAnimation { target: t; property: "opacity"; to: 1; duration: Theme.normal }
                    NumberAnimation { target: t; property: "slide"; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
                }
                SequentialAnimation {
                    running: true
                    PauseAnimation { duration: body ? 3800 : 2800 }
                    ParallelAnimation {
                        NumberAnimation { target: t; property: "opacity"; to: 0; duration: Theme.normal }
                        NumberAnimation { target: t; property: "slide"; to: 40; duration: Theme.normal }
                    }
                    ScriptAction { script: { for (var i = 0; i < toastModel.count; i++) if (toastModel.get(i).born === born) { toastModel.remove(i); break } } }
                }
                Rectangle { x: 0; width: 4; height: parent.height - 24; y: 12; radius: 2; color: t.kc }
                Column {
                    id: col
                    x: 18; y: 14
                    width: parent.width - 32
                    spacing: 3
                    Text { text: title; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; width: parent.width }
                    Text { visible: body !== ""; text: body; color: Theme.textDim; font.pixelSize: 13; wrapMode: Text.WordWrap; width: parent.width }
                }
            }
        }
    }
}
