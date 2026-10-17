import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var s: root.s

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 6
            SectionTitle { text: L.t("Тачпад") }
            SettingRow {
                title: L.t("Скорость курсора"); icon: "ph:hand-pointing"
                CSlider { from: 0.3; to: 3; stepSize: 0.05; value: s.pointer_speed
                    format: function (v) { return "×" + v.toFixed(2) }
                    onMoved: backend.set("pointer_speed", value) }
            }
            SettingRow {
                title: L.t("Ускорение"); subtitle: L.t("Быстрый взмах уносит курсор дальше (0 — линейно)"); icon: "ph:trend-up"
                CSlider { from: 0; to: 3; stepSize: 0.1; value: s.pointer_accel
                    format: function (v) { return v.toFixed(1) }
                    onMoved: backend.set("pointer_accel", value) }
            }
            SettingRow {
                title: L.t("Сглаживание"); subtitle: L.t("Убирает дрожание, но добавляет инерцию"); icon: "ph:wave-sine"
                CSlider { from: 0; to: 0.8; stepSize: 0.05; value: s.pointer_smoothing
                    format: function (v) { return Math.round(v * 100) + "%" }
                    onMoved: backend.set("pointer_smoothing", value) }
            }
            SettingRow {
                title: L.t("Скорость прокрутки"); subtitle: L.t("Прокрутка — двумя пальцами"); icon: "ph:arrows-down-up"
                CSlider { from: 0.3; to: 3; stepSize: 0.05; value: s.scroll_speed
                    format: function (v) { return "×" + v.toFixed(2) }
                    onMoved: backend.set("scroll_speed", value) }
            }
            Divider {}
            SettingRow {
                title: L.t("Естественная прокрутка"); subtitle: L.t("Как на телефоне: контент едет за пальцами"); icon: "ph:hand-swipe-right"
                CSwitch { checked: s.natural_scroll; onToggled: backend.set("natural_scroll", checked) }
            }
            SettingRow {
                title: L.t("Клик касанием"); subtitle: L.t("Один палец — левый, два — правый, три — средний"); icon: "ph:hand-tap"
                CSwitch { checked: s.tap_to_click; onToggled: backend.set("tap_to_click", checked) }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 6
            SectionTitle { text: L.t("Стики"); subtitle: L.t("Левый стик — курсор, правый — прокрутка") }
            SettingRow {
                title: L.t("Скорость курсора стиком"); icon: "ph:game-controller"
                CSlider { from: 300; to: 3000; stepSize: 50; value: s.stick_pointer_speed
                    format: function (v) { return Math.round(v) + L.t(" px/с") }
                    onMoved: backend.set("stick_pointer_speed", value) }
            }
            SettingRow {
                title: L.t("Скорость прокрутки стиком"); icon: "ph:arrows-down-up"
                CSlider { from: 300; to: 4000; stepSize: 50; value: s.stick_scroll_speed
                    format: function (v) { return "×" + (v / 1800).toFixed(2) }
                    onMoved: backend.set("stick_scroll_speed", value) }
            }
            SettingRow {
                title: L.t("Мёртвая зона"); subtitle: L.t("Больше — если курсор ползёт сам"); icon: "ph:crosshair"
                CSlider { from: 0.04; to: 0.35; stepSize: 0.01; value: s.stick_deadzone
                    format: function (v) { return Math.round(v * 100) + "%" }
                    onMoved: backend.set("stick_deadzone", value) }
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
                title: L.t("Включать мышь после «свернуть игру»")
                subtitle: L.t("Share + ○ (удержание) сразу делает тачпад мышью")
                icon: "ph:arrow-line-down"
                CSwitch { checked: s.mouse_on_after_minimize; onToggled: backend.set("mouse_on_after_minimize", checked) }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 12
            SectionTitle { text: L.t("Кнопки в режиме мыши") }
            GridLayout {
                Layout.fillWidth: true
                columns: width > 700 ? 3 : 2
                columnSpacing: 24
                rowSpacing: 10
                Repeater {
                    model: [
                        {b: "cross", g: "✕", t: L.t("левый клик")}, {b: "circle", g: "○", t: L.t("правый клик")},
                        {b: "square", g: "□", t: L.t("средний клик")}, {b: "triangle", g: "△", t: L.t("клавиатура")},
                        {b: "r2", g: "R2", t: L.t("левый клик")}, {b: "l2", g: "L2", t: L.t("правый клик")},
                        {b: "l1", g: "L1", t: L.t("назад")}, {b: "r1", g: "R1", t: L.t("вперёд")},
                        {b: "up", g: "↕↔", t: L.t("стрелки")}, {b: "options", g: "Options", t: L.t("меню KDE")},
                        {b: "l3", g: "L3", t: "Enter"}, {b: "r3", g: "R3", t: "Esc"}
                    ]
                    RowLayout {
                        spacing: 10
                        Glyph { share: false; button: modelData.b; glyph: modelData.g; Layout.preferredWidth: 76 }
                        Text { text: modelData.t; color: Theme.text; font.pixelSize: 14 }
                    }
                }
            }
        }
    }
}
