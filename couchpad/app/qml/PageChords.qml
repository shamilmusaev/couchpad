import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var s: root.s
    readonly property var actionModel: backend.actions.map(function (a) {
        return {value: a.name, label: a.label, icon: a.icon}
    })

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                SectionTitle {
                    text: L.t("Share + кнопка")
                    subtitle: L.t("Зажмите Share и нажмите кнопку. ○, △ и R1 закреплены за главными функциями.")
                }
                CButton {
                    text: L.t("Сбросить")
                    kind: "ghost"
                    iconName: "ph:arrow-counter-clockwise"
                    enabled: backend.chords.some(function (c) { return c.custom })
                    onClicked: { backend.resetChords(); root.toast(L.t("Сочетания сброшены"), "", "ok") }
                }
            }
            Item { height: 6; width: 1 }
            Repeater {
                model: backend.chords
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Divider { visible: index > 0; opacity: 0.6 }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: 56
                        spacing: 16
                        Glyph { button: modelData.button; glyph: modelData.glyph; Layout.preferredWidth: 120 }
                        Icon { name: modelData.icon; size: 22; mono: true; monoColor: Theme.text }
                        ColumnLayout {
                            spacing: 2
                            Layout.fillWidth: true
                            Text {
                                text: modelData.label
                                color: Theme.text
                                font.pixelSize: Theme.fontBody
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: modelData.custom
                                text: L.t("изменено")
                                color: Theme.accentText
                                font.pixelSize: 12
                            }
                        }
                        CCombo {
                            visible: !modelData.fixed
                            implicitWidth: 300
                            model: pg.actionModel
                            current: modelData.action
                            onPicked: (v) => backend.setChord(modelData.button, v)
                        }
                        Row {
                            visible: modelData.fixed
                            spacing: 6
                            Icon { name: "ph:lock-simple"; size: 16; mono: true; anchors.verticalCenter: parent.verticalCenter; opacity: 0.6 }
                            Text { text: L.t("закреплено"); color: Theme.textFaint; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 6
            SectionTitle { text: L.t("Тайминги") }
            SettingRow {
                title: L.t("Удержание Share + ○ / △")
                subtitle: L.t("Сколько держать, чтобы свернуть или закрыть игру")
                icon: "ph:timer"
                CSlider {
                    from: 0.5; to: 3; stepSize: 0.1
                    value: s.long_press
                    format: function (v) { return v.toFixed(1) + L.t(" с") }
                    onMoved: backend.set("long_press", value)
                }
            }
            SettingRow {
                title: L.t("Двойное нажатие Share")
                subtitle: L.t("Пауза между нажатиями для режима мыши")
                icon: "ph:mouse-simple"
                CSlider {
                    from: 0.25; to: 0.8; stepSize: 0.05
                    value: s.double_tap_window
                    format: function (v) { return Math.round(v * 1000) + L.t(" мс") }
                    onMoved: backend.set("double_tap_window", value)
                }
            }
            SettingRow {
                title: L.t("Переключатель окон закрывается сам")
                subtitle: L.t("Через столько секунд без нажатий выбирается текущее окно")
                icon: "ph:stack"
                CSlider {
                    from: 3; to: 30; stepSize: 1
                    value: s.alt_tab_timeout
                    format: function (v) { return Math.round(v) + L.t(" с") }
                    onMoved: backend.set("alt_tab_timeout", value)
                }
            }
            SettingRow {
                title: L.t("Кольцо прогресса при удержании")
                subtitle: L.t("Показывает на экране, сколько ещё держать")
                icon: "ph:arrows-clockwise"
                CSwitch {
                    checked: s.hold_osd
                    onToggled: backend.set("hold_osd", checked)
                }
            }
        }
    }
}
