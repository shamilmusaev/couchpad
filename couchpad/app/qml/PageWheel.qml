import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var items: backend.wheelItems
    property int hot: -1

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.gap

        Card {
            Layout.preferredWidth: 400
            Layout.alignment: Qt.AlignTop
            implicitHeight: 440
            Item {
                id: wheel
                width: 340; height: 340
                anchors.horizontalCenter: parent.horizontalCenter
                readonly property real r: 120
                Rectangle {
                    anchors.centerIn: parent
                    width: 300; height: 300; radius: 150
                    color: "#18171b"
                    border.color: Theme.border
                    Rectangle {
                        anchors.centerIn: parent
                        width: 104; height: 104; radius: 52
                        color: Theme.surface2
                        border.color: Theme.alpha(Theme.accent, 0.6)
                        Text {
                            anchors.centerIn: parent
                            width: 92
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: pg.hot >= 0 && pg.items[pg.hot] ? pg.items[pg.hot].name : "Share + R1"
                            color: Theme.text
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                    }
                }
                Repeater {
                    model: pg.items
                    Item {
                        readonly property real ang: (index * 360 / pg.items.length - 90) * Math.PI / 180
                        x: wheel.width / 2 + wheel.r * Math.cos(ang) - 28
                        y: wheel.height / 2 + wheel.r * Math.sin(ang) - 28
                        width: 56; height: 56
                        scale: pg.hot === index ? 1.18 : 1
                        Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutBack } }
                        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        Icon { anchors.centerIn: parent; name: modelData.icon || "application-x-executable"; size: 46 }
                    }
                }
            }
            Text {
                anchors.top: wheel.bottom
                anchors.topMargin: 14
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: L.t("Наведите правым стиком и отпустите R1.\nПервый пункт — сверху, дальше по часовой.")
                color: Theme.textDim
                font.pixelSize: 13
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            ColumnLayout {
                width: parent.width
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    SectionTitle {
                        text: L.t("Приложения · ") + pg.items.length + " / 8"
                        subtitle: backend.wheelIsDefault ? L.t("Сейчас — набор по умолчанию") : L.t("Ваш набор")
                    }
                    CButton {
                        visible: !backend.wheelIsDefault
                        text: L.t("По умолчанию")
                        kind: "ghost"
                        iconName: "ph:arrow-counter-clockwise"
                        onClicked: backend.wheelReset()
                    }
                }
                Repeater {
                    model: pg.items
                    Rectangle {
                        id: row
                        Layout.fillWidth: true
                        height: 60
                        radius: 12
                        color: hov.hovered || pg.hot === index ? Theme.surface2 : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        HoverHandler { id: hov; onHoveredChanged: pg.hot = hovered ? index : (pg.hot === index ? -1 : pg.hot) }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 8
                            spacing: 14
                            Text { text: index + 1; color: Theme.textFaint; font.pixelSize: 13; Layout.preferredWidth: 14 }
                            Icon { name: modelData.icon || "application-x-executable"; size: 34 }
                            ColumnLayout {
                                spacing: 1
                                Layout.fillWidth: true
                                Text { text: modelData.name; color: Theme.text; font.pixelSize: 15; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text {
                                    text: (modelData.kind === "app" ? L.t("приложение · ") : modelData.kind === "open" ? L.t("ссылка · ") : L.t("команда · ")) + modelData.value
                                    color: Theme.textDim; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true
                                }
                            }
                            CButton {
                                text: "↑"; kind: "ghost"; implicitWidth: 40; leftPadding: 0; rightPadding: 0
                                enabled: index > 0
                                onClicked: backend.wheelMove(index, -1)
                                onActiveFocusChanged: if (activeFocus) pg.hot = index
                            }
                            CButton {
                                text: "↓"; kind: "ghost"; implicitWidth: 40; leftPadding: 0; rightPadding: 0
                                enabled: index < pg.items.length - 1
                                onClicked: backend.wheelMove(index, 1)
                                onActiveFocusChanged: if (activeFocus) pg.hot = index
                            }
                            CButton {
                                text: L.t("Убрать"); kind: "danger"
                                onClicked: backend.wheelRemove(index)
                                onActiveFocusChanged: if (activeFocus) pg.hot = index
                            }
                        }
                    }
                }
                Text {
                    visible: pg.items.length === 0
                    text: L.t("Колесо пустое — добавьте приложения.")
                    color: Theme.textDim
                    font.pixelSize: 14
                }
                RowLayout {
                    Layout.topMargin: 8
                    spacing: 10
                    CButton {
                        text: L.t("Добавить приложение")
                        kind: "accent"
                        iconName: "ph:plus"
                        enabled: pg.items.length < 8
                        onClicked: dialogs.pickApp()
                    }
                    CButton {
                        text: L.t("Ссылка или команда")
                        iconName: "ph:link"
                        enabled: pg.items.length < 8
                        onClicked: dialogs.customItem()
                    }
                }
            }
        }
    }
}
