import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var st: gamepad.state

    Card {
        Layout.fillWidth: true
        implicitHeight: 470
        visible: gamepad.connected
        RowLayout {
            anchors.fill: parent
            spacing: 28
            PadArt {
                Layout.fillWidth: true
                Layout.fillHeight: true
                showInput: true
                input: pg.st
                light: root.pad.light ? Qt.rgba(root.pad.light[0] / 255, root.pad.light[1] / 255, root.pad.light[2] / 255, 1) : "#3d7bff"
                lit: !!root.pad.light
            }
            ColumnLayout {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                spacing: 16
                Repeater {
                    model: [{t: L.t("Левый стик"), x: "lx", y: "ly"}, {t: L.t("Правый стик"), x: "rx", y: "ry"}]
                    RowLayout {
                        spacing: 16
                        Rectangle {
                            width: 96; height: 96; radius: 48
                            color: Theme.surface2; border.color: Theme.border
                            Rectangle { anchors.centerIn: parent; width: 1; height: parent.height - 16; color: Theme.border }
                            Rectangle { anchors.centerIn: parent; height: 1; width: parent.width - 16; color: Theme.border }
                            Rectangle {
                                width: 18; height: 18; radius: 9
                                color: Theme.accent
                                x: 39 + (pg.st[modelData.x] || 0) * 39
                                y: 39 + (pg.st[modelData.y] || 0) * 39
                            }
                        }
                        Column {
                            spacing: 4
                            Text { text: modelData.t; color: Theme.text; font.pixelSize: 15; font.weight: Font.Medium }
                            Text {
                                text: "X " + (pg.st[modelData.x] || 0).toFixed(2) + "   Y " + (pg.st[modelData.y] || 0).toFixed(2)
                                color: Theme.textDim; font.pixelSize: 13; font.family: Theme.mono
                            }
                        }
                    }
                }
                Repeater {
                    model: [{t: "L2", k: "l2"}, {t: "R2", k: "r2"}]
                    RowLayout {
                        spacing: 12
                        Text { text: modelData.t; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.preferredWidth: 26 }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 12; radius: 6
                            color: Theme.surface2
                            Rectangle {
                                height: parent.height; radius: 6
                                width: parent.width * (pg.st[modelData.k] || 0)
                                color: Theme.accent
                            }
                        }
                        Text { text: Math.round((pg.st[modelData.k] || 0) * 100) + "%"; color: Theme.textDim; font.pixelSize: 13; Layout.preferredWidth: 40 }
                    }
                }
                Text {
                    text: L.t("Касаний: ") + (pg.st.touch ? pg.st.touch.length : 0) + (pg.st.click ? L.t(" · нажат") : "")
                    color: Theme.textDim
                    font.pixelSize: 13
                }
                Item { Layout.fillHeight: true }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: L.t("Кнопки подсвечиваются на рисунке. Если стик «ползёт» в покое, увеличьте мёртвую зону на вкладке «Мышь».")
                    color: Theme.textFaint
                    font.pixelSize: 12
                }
            }
        }
    }
    Card {
        Layout.fillWidth: true
        visible: !gamepad.connected
        implicitHeight: 260
        Column {
            anchors.centerIn: parent
            spacing: 12
            Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "ph:game-controller"; size: 64; mono: true }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t("Геймпад не найден"); color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: L.t("Включите DualSense кнопкой PS"); color: Theme.textDim; font.pixelSize: 14 }
        }
    }
}
