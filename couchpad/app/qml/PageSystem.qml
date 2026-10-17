import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var s: root.s
    onCurrentChanged: if (current) { backend.refreshService(); backend.refreshSteam() }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                Rectangle {
                    width: 14; height: 14; radius: 7
                    color: backend.daemonRunning ? Theme.ok : Theme.danger
                }
                SectionTitle {
                    text: backend.daemonRunning ? L.t("Служба работает") : L.t("Служба остановлена")
                    subtitle: L.t("couchpad.service — жесты, мышь, подсветка, колесо. Работает в фоне, окно для неё не нужно.")
                }
            }
            RowLayout {
                spacing: 10
                CButton { visible: !backend.daemonRunning; text: L.t("Запустить"); kind: "accent"; iconName: "ph:play"; onClicked: backend.service("start") }
                CButton { visible: backend.daemonRunning; text: L.t("Перезапустить"); iconName: "ph:arrows-clockwise"; onClicked: backend.service("restart") }
                CButton { visible: backend.daemonRunning; text: L.t("Остановить"); kind: "danger"; onClicked: backend.service("stop") }
            }
            Divider {}
            SettingRow {
                title: L.t("Запускать при входе в систему")
                icon: "ph:rocket-launch"
                CSwitch { checked: backend.autostart; onToggled: backend.service(checked ? "enable" : "disable") }
            }
            SettingRow {
                title: L.t("Значок в трее")
                subtitle: L.t("Заряд геймпада и режим мыши рядом с часами; закрытие окна сворачивает в трей")
                icon: "ph:bell"
                CSwitch { checked: s.tray; onToggled: backend.set("tray", checked) }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 6
            SectionTitle { text: L.t("Сообщения") }
            SettingRow {
                title: L.t("Показывать сообщения")
                subtitle: L.t("Заряд, режим мыши, «игра закрыта» и т. п.")
                icon: "ph:bell"
                CSwitch { checked: s.notifications; onToggled: backend.set("notifications", checked) }
            }
            SettingRow {
                enabled: s.notifications
                opacity: enabled ? 1 : 0.5
                title: L.t("Поверх игр")
                subtitle: L.t("Свои подсказки вверху экрана, видны даже в полноэкранной игре. Выключено — уведомления KDE")
                icon: "ph:monitor"
                CSwitch { checked: s.osd; onToggled: backend.set("osd", checked) }
            }
            RowLayout {
                Layout.leftMargin: 56
                CButton { text: L.t("Показать пример"); iconName: "ph:play"; enabled: backend.daemonRunning; onClicked: backend.testOsd() }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 6
            SectionTitle { text: L.t("Поведение") }
            SettingRow {
                title: L.t("Язык")
                subtitle: "Русский · English"
                icon: "ph:translate"
                CCombo {
                    model: [{value: "auto", label: L.t("Как в системе")}, {value: "ru", label: "Русский"},
                            {value: "en", label: "English"}]
                    current: s.language
                    onPicked: (v) => backend.set("language", v)
                }
            }
            SettingRow {
                title: L.t("Экранная клавиатура")
                subtitle: L.t("Что открывать по Share + □")
                icon: "ph:keyboard"
                CCombo {
                    model: [{value: "auto", label: L.t("Steam, если запущен")}, {value: "steam", label: L.t("Только Steam")},
                            {value: "plasma", label: "Plasma Keyboard"}]
                    current: s.keyboard
                    onPicked: (v) => backend.set("keyboard", v)
                }
            }
            SettingRow {
                title: L.t("Выключать геймпад без дела")
                subtitle: L.t("Если ни одна кнопка не нажималась столько минут (только Bluetooth)")
                icon: "ph:power"
                CSlider {
                    from: 0; to: 60; stepSize: 5
                    value: s.idle_off
                    format: function (v) { return v < 1 ? L.t("никогда") : Math.round(v) + L.t(" мин") }
                    onMoved: backend.set("idle_off", value)
                }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 10
            SectionTitle {
                text: L.t("Раскладка Steam на рабочем столе")
                subtitle: L.t("Steam сам превращает DualSense в мышь и клавиатуру (Share = Esc, ✕ = Enter) и мешает жестам. ") +
                          L.t("Нейтральная раскладка отключает это только на рабочем столе; игры не затрагиваются.")
            }
            RowLayout {
                spacing: 12
                Rectangle {
                    width: stTxt.implicitWidth + 24; height: 32; radius: 16
                    color: backend.steamLayout === "neutral" ? Theme.alpha(Theme.ok, 0.15) : Theme.alpha(Theme.warn, 0.15)
                    border.color: backend.steamLayout === "neutral" ? Theme.alpha(Theme.ok, 0.5) : Theme.alpha(Theme.warn, 0.5)
                    Text {
                        id: stTxt
                        anchors.centerIn: parent
                        text: ({neutral: L.t("Нейтральная — не мешает"), steam: L.t("Steam управляет геймпадом"), none: L.t("Steam не найден")})[backend.steamLayout] || "…"
                        color: Theme.text; font.pixelSize: 13
                    }
                }
                CButton {
                    visible: backend.steamLayout === "steam"
                    text: backend.busy ? L.t("Подождите…") : L.t("Сделать нейтральной")
                    kind: "accent"
                    enabled: !backend.busy
                    onClicked: backend.setSteamLayout(true)
                }
                CButton {
                    visible: backend.steamLayout === "neutral"
                    text: backend.busy ? L.t("Подождите…") : L.t("Вернуть как было")
                    enabled: !backend.busy
                    onClicked: backend.setSteamLayout(false)
                }
            }
            Text {
                text: L.t("Steam закроется на несколько секунд и запустится снова.")
                color: Theme.textFaint; font.pixelSize: 12
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 10
            SectionTitle { text: L.t("Для опытных") }
            RowLayout {
                spacing: 10
                CButton { text: L.t("Журнал службы"); iconName: "ph:list"; onClicked: dialogs.showLog() }
                CButton { text: L.t("Открыть config.toml"); iconName: "ph:file-text"; onClicked: backend.openConfig() }
            }
            Text {
                text: L.t("Правки в ") + backend.configPath + L.t(" применяются сразу, перезапуск не нужен.")
                color: Theme.textFaint; font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    Card {
        Layout.fillWidth: true
        RowLayout {
            width: parent.width
            spacing: 18
            Icon { name: "couchpad"; size: 64 }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text { text: "Couchpad " + backend.version; color: Theme.text; font.pixelSize: 18; font.weight: Font.Bold }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: L.t("DualSense как пульт для ПК с дивана: KDE Plasma, Wayland, Bazzite. Лицензия MIT.\n") +
                          L.t("HD-хаптика по Bluetooth — по протоколу SAxense (MPL-2.0).")
                    color: Theme.textDim; font.pixelSize: 13
                }
            }
            CButton { text: "GitHub"; iconName: "ph:github-logo"; onClicked: backend.openUrl(backend.repoUrl) }
            CButton { text: "SAxense"; kind: "ghost"; onClicked: backend.openUrl("https://apps.sdore.me/SAxense") }
        }
    }
}
