import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Modal dialogs: app picker, custom wheel item, service log.
Item {
    id: dlg
    anchors.fill: parent
    z: 1500
    readonly property bool open: apps.visible || custom.visible || log.visible
    function pickApp() { backend.loadApps(); search.text = ""; apps.open() }
    function customItem() { cName.text = ""; cTarget.text = ""; cIcon.text = ""; custom.open() }
    function showLog() { logText.text = backend.logText(); log.open() }
    function closeAll() { apps.close(); custom.close(); log.close() }

    component Sheet: Popup {
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        dim: true
        padding: 26
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle {
            color: Qt.rgba(0, 0, 0, 0.55)
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal }
            NumberAnimation { property: "scale"; from: 0.94; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: Theme.fast }
            NumberAnimation { property: "scale"; to: 0.97; duration: Theme.fast }
        }
        background: Rectangle {
            radius: 20
            color: "#1d1c21"
            border.color: Theme.borderStrong
        }
    }

    component Field: TextField {
        id: tf
        property real radius: Theme.radiusSmall
        Layout.fillWidth: true
        implicitHeight: 44
        color: Theme.text
        placeholderTextColor: Theme.textFaint
        font.pixelSize: Theme.fontBody
        selectByMouse: true
        leftPadding: 14
        background: Rectangle {
            radius: tf.radius
            color: Theme.surface2
            border.color: tf.activeFocus ? Theme.accent : Theme.border
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
    }

    Sheet {
        id: apps
        width: Math.min(640, dlg.width - 80)
        height: Math.min(680, dlg.height - 80)
        onOpened: search.forceActiveFocus()
        ColumnLayout {
            anchors.fill: parent
            spacing: 14
            Text { text: L.t("Добавить в колесо"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
            Field {
                id: search
                placeholderText: L.t("Поиск приложения…")
                Keys.onDownPressed: list.forceActiveFocus()
                Keys.onReturnPressed: if (list.count) { backend.wheelAddApp(list.model[0].id); apps.close() }
            }
            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 2
                activeFocusOnTab: true
                keyNavigationEnabled: true
                highlightMoveDuration: Theme.fast
                model: {
                    var q = search.text.toLowerCase()
                    return backend.apps.filter(function (a) { return !q || a.name.toLowerCase().indexOf(q) >= 0 || a.id.toLowerCase().indexOf(q) >= 0 })
                }
                ScrollBar.vertical: ScrollBar {}
                Keys.onReturnPressed: { backend.wheelAddApp(model[currentIndex].id); apps.close() }
                Keys.onSpacePressed: { backend.wheelAddApp(model[currentIndex].id); apps.close() }
                function padAccept() { backend.wheelAddApp(model[currentIndex].id); apps.close() }
                highlight: Rectangle { radius: 10; color: Theme.accentSoft; border.color: Theme.alpha(Theme.accent, 0.5) }
                delegate: Item {
                    width: list.width - 12
                    height: 52
                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        color: ma.containsMouse ? Theme.surface2 : "transparent"
                    }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 12
                        spacing: 14
                        Icon { name: modelData.icon || "application-x-executable"; size: 32; anchors.verticalCenter: parent.verticalCenter }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.name; color: Theme.text; font.pixelSize: 15 }
                            Text { text: modelData.id; color: Theme.textFaint; font.pixelSize: 11 }
                        }
                    }
                    MouseArea {
                        id: ma
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { backend.wheelAddApp(modelData.id); apps.close() }
                    }
                }
                BusyIndicator { anchors.centerIn: parent; running: backend.apps.length === 0; visible: running }
            }
        }
    }

    Sheet {
        id: custom
        width: Math.min(560, dlg.width - 80)
        onOpened: cName.forceActiveFocus()
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text { text: L.t("Ссылка или команда"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: L.t("Ссылка (https://…, steam://…) откроется в своём приложении; всё остальное выполнится как команда.")
                color: Theme.textDim; font.pixelSize: 13
            }
            Field { id: cName; placeholderText: L.t("Название, например «YouTube»") }
            Field { id: cTarget; placeholderText: L.t("https://youtube.com/tv  или  команда") }
            Field { id: cIcon; placeholderText: L.t("Иконка (имя из темы, необязательно)") }
            RowLayout {
                Layout.topMargin: 6
                Layout.alignment: Qt.AlignRight
                spacing: 10
                CButton { text: L.t("Отмена"); kind: "ghost"; onClicked: custom.close() }
                CButton {
                    text: L.t("Добавить"); kind: "accent"
                    enabled: cTarget.text.trim() !== ""
                    onClicked: { backend.wheelAddCustom(cName.text, cTarget.text, cIcon.text); custom.close() }
                }
            }
        }
    }

    Sheet {
        id: log
        width: dlg.width - 120
        height: dlg.height - 120
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Text { text: L.t("Журнал службы"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold; Layout.fillWidth: true }
                CButton { text: L.t("Обновить"); iconName: "ph:arrows-clockwise"; onClicked: logText.text = backend.logText() }
                CButton { text: L.t("Закрыть"); kind: "ghost"; onClicked: log.close() }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                TextArea {
                    id: logText
                    readOnly: true
                    wrapMode: TextEdit.NoWrap
                    color: Theme.textDim
                    font.family: Theme.mono
                    font.pixelSize: 12
                    selectByMouse: true
                    background: Rectangle { radius: 10; color: "#121114" }
                    onTextChanged: Qt.callLater(function () { cursorPosition = length })
                }
            }
        }
    }
}
