import QtQuick
import QtQuick.Layouts

PageBase {
    id: lights
    readonly property var s: root.s
    readonly property string mode: s.light_mode || "static"
    readonly property bool animated: mode === "breathe" || mode === "rainbow"
    readonly property bool usesColor: mode === "static" || mode === "breathe"

    // live preview colour of the illustration
    property real phase: 0
    NumberAnimation on phase {
        running: lights.current && (lights.animated || lights.mode === "battery")
        from: 0; to: 1; duration: 12000; loops: Animation.Infinite
    }
    function batteryColor(cap) {
        var k = Math.min(Math.max((cap - 10) / 60, 0), 1)
        return Qt.hsva(k * 0.33, 1, 1, 1)
    }
    readonly property color preview: {
        var lvl = 0.25 + 0.75 * (s.light_brightness || 0)
        if (mode === "off" || mode === "steam") return "#2c2b30"
        if (mode === "rainbow") return Qt.hsva((phase * (s.light_speed || 1) * 12 / 12) % 1, 1, lvl, 1)
        if (mode === "battery") return batteryColor(root.pad.battery !== undefined && root.pad.battery !== null ? root.pad.battery : 80)
        var c = Qt.color(s.light_color || "#1e6bff")
        if (mode === "breathe") {
            var period = 4 / (s.light_speed || 1)
            var k = 0.5 - 0.5 * Math.cos(2 * Math.PI * ((phase * 12) % period) / period)
            return Qt.hsva(c.hsvHue, c.hsvSaturation, Math.max(0.1, k * c.hsvValue * lvl), 1)
        }
        return Qt.hsva(c.hsvHue, c.hsvSaturation, c.hsvValue * lvl, 1)
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.gap

        // preview -----------------------------------------------------------
        Card {
            Layout.preferredWidth: 420
            Layout.alignment: Qt.AlignTop
            implicitHeight: 440
            clip: true
            Glow {
                x: -22; y: -60
                width: parent.width + 44
                height: 380
                color: lights.preview
                strength: lights.mode === "off" || lights.mode === "steam" ? 0.05 : 0.35
            }
            ColumnLayout {
                anchors.fill: parent
                spacing: 18
                PadArt {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 250
                    light: lights.preview
                    lit: lights.mode !== "off" && lights.mode !== "steam"
                    input: gamepad.state
                    showInput: gamepad.connected
                }
                Text {
                    text: ({off: L.t("Подсветка выключена"), static: L.t("Постоянный цвет"), breathe: L.t("Плавное дыхание"),
                            rainbow: L.t("Радуга по кругу"), battery: L.t("Цвет показывает заряд"),
                            steam: L.t("Подсветкой управляет Steam")})[lights.mode]
                    color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: lights.mode === "battery" ? L.t("Зелёный — полный, жёлтый — половина, красный — пора заряжать. Во время зарядки пульсирует.")
                          : lights.mode === "steam" ? L.t("Couchpad не трогает полосу: цвет задают Steam и игры.")
                          : s.light_mouse_color ? L.t("В режиме мыши полоса меняет цвет — сразу видно, что тачпад стал мышью.")
                          : L.t("Цвет меняется на геймпаде сразу.")
                    color: Theme.textDim; font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
                Item { Layout.fillHeight: true }
            }
        }

        // controls ------------------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.gap

            Rectangle {         // mouse-mode colour is what the pad shows right now
                visible: backend.mouse && !!s.light_mouse_color && lights.mode !== "steam"
                Layout.fillWidth: true
                implicitHeight: warnRow.implicitHeight + 28
                radius: Theme.radius
                color: Theme.accentSoft
                border.color: Theme.alpha(Theme.accent, 0.45)
                RowLayout {
                    id: warnRow
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12
                    Icon { name: "ph:info"; size: 20; mono: true; monoColor: Theme.accent }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: L.t("Сейчас включён режим мыши, и полоса горит цветом режима мыши. Выбранный цвет вернётся, когда мышь выключится.")
                        color: Theme.text
                        font.pixelSize: 14
                    }
                    CButton {
                        text: L.t("Не менять цвет в режиме мыши")
                        onClicked: backend.set("light_mouse_color", "")
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                ColumnLayout {
                    width: parent.width
                    spacing: 14
                    SectionTitle { text: L.t("Режим") }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: width > 560 ? 3 : 2
                        columnSpacing: 10
                        rowSpacing: 10
                        Repeater {
                            model: [
                                {v: "static", t: L.t("Цвет"), d: L.t("один цвет всегда"), sw: null},
                                {v: "breathe", t: L.t("Дыхание"), d: L.t("плавно гаснет и загорается"), sw: null},
                                {v: "rainbow", t: L.t("Радуга"), d: L.t("медленно по кругу"), sw: ["#ff3b30", "#3ad14a", "#1e6bff"]},
                                {v: "battery", t: L.t("По заряду"), d: L.t("зелёный → красный"), sw: ["#ff3b30", "#ffd200", "#3ad14a"]},
                                {v: "off", t: L.t("Выключена"), d: L.t("полоса не горит"), sw: ["#000000"]},
                                {v: "steam", t: L.t("Как в Steam"), d: L.t("не вмешиваться"), sw: null}
                            ]
                            ModeTile {
                                label: modelData.t
                                sub: modelData.d
                                selected: lights.mode === modelData.v
                                swatch: modelData.sw ? modelData.sw
                                        : modelData.v === "steam" ? null
                                        : [s.light_color, modelData.v === "breathe" ? "#000000" : s.light_color, s.light_color]
                                icon: "ph:steam-logo"
                                onClicked: backend.set("light_mode", modelData.v)
                            }
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                visible: lights.usesColor
                RowLayout {
                    width: parent.width
                    spacing: 26
                    ColorPicker {
                        value: s.light_color || "#1e6bff"
                        onPicked: (c) => { backend.set("light_color", Theme.hex(c)); backend.previewLight(Theme.hex(c)) }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        SectionTitle { text: L.t("Цвет"); subtitle: L.t("Крутите кольцо мышью или ←/→ на геймпаде") }
                        Swatches {
                            current: s.light_color || ""
                            onPicked: (c) => { backend.set("light_color", c); backend.previewLight(c) }
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                visible: lights.mode !== "off" && lights.mode !== "steam"
                ColumnLayout {
                    width: parent.width
                    spacing: 6
                    SettingRow {
                        title: L.t("Яркость")
                        icon: "ph:sun"
                        CSlider {
                            from: 0.05; to: 1; stepSize: 0.05
                            value: s.light_brightness
                            format: function (v) { return Math.round(v * 100) + "%" }
                            onMoved: backend.set("light_brightness", value)
                        }
                    }
                    SettingRow {
                        visible: lights.animated
                        title: L.t("Скорость")
                        icon: "ph:gauge"
                        CSlider {
                            from: 0.25; to: 3; stepSize: 0.25
                            value: s.light_speed
                            format: function (v) { return "×" + v.toFixed(2).replace(/\.?0+$/, "") }
                            onMoved: backend.set("light_speed", value)
                        }
                    }
                    Divider {}
                    SettingRow {
                        title: L.t("Вспышки на действиях")
                        subtitle: L.t("Красная — игра закрыта, белая — свёрнута, скриншот или запуск из колеса")
                        icon: "ph:lightning"
                        CSwitch {
                            checked: s.light_flash
                            onToggled: backend.set("light_flash", checked)
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                visible: lights.mode !== "steam"
                ColumnLayout {
                    width: parent.width
                    spacing: 14
                    SectionTitle { text: L.t("Режим мыши"); subtitle: L.t("Цвет полосы, пока тачпад работает мышью (∅ — не менять)") }
                    Swatches {
                        none: true
                        current: s.light_mouse_color || ""
                        colors: ["#ffffff", "#ff6a1f", "#ffd200", "#00e0a4", "#00b7ff", "#ff3b30"]
                        onPicked: (c) => backend.set("light_mouse_color", c)
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                ColumnLayout {
                    width: parent.width
                    spacing: 6
                    SettingRow {
                        title: L.t("Индикаторы игрока")
                        subtitle: L.t("Пять точек под тачпадом")
                        icon: "ph:dots-three"
                        CCombo {
                            model: [{value: "auto", label: L.t("Как задаёт система")}, {value: "battery", label: L.t("Показывают заряд")},
                                    {value: "mouse", label: L.t("Горят в режиме мыши")}, {value: "off", label: L.t("Выключены")}]
                            current: s.player_leds
                            onPicked: (v) => backend.set("player_leds", v)
                        }
                    }
                    SettingRow {
                        title: L.t("Светодиод микрофона")
                        subtitle: L.t("Оранжевая полоска на кнопке Mute")
                        icon: "ph:microphone"
                        CCombo {
                            model: [{value: "auto", label: L.t("Показывает Mute")}, {value: "mouse", label: L.t("Горит в режиме мыши")}]
                            current: s.mic_led
                            onPicked: (v) => backend.set("mic_led", v)
                        }
                    }
                }
            }
        }
    }
}
