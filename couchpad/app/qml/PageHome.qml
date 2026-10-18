import QtQuick
import QtQuick.Layouts

PageBase {
    id: home
    showTitle: false
    readonly property var pad: root.pad
    readonly property bool connected: root.connected
    readonly property bool hasBattery: connected && pad.battery !== null && pad.battery !== undefined
    readonly property color lightColor: pad.light && (pad.light[0] + pad.light[1] + pad.light[2]) > 0
                                        ? Qt.rgba(pad.light[0] / 255, pad.light[1] / 255, pad.light[2] / 255, 1)
                                        : "#8a8790"
    readonly property bool lit: !!pad.light && (pad.light[0] + pad.light[1] + pad.light[2]) > 0

    // ---------------------------------------------------------------- hero
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.gap

        RoundClip {
            id: hero
            Layout.fillWidth: true
            Layout.preferredHeight: 360
            radius: Theme.radius

            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "#1b1a1e" }
                    GradientStop { position: 1; color: "#26252a" }
                }
            }
            // lightbar glow behind the controller
            Glow {
                width: hero.height * 1.5
                height: hero.height * 1.1
                x: art.x + art.width / 2 - width / 2
                y: art.y + art.height * 0.3 - height / 2
                color: home.lightColor
                strength: home.connected && home.lit ? 0.42 : 0.08
                Behavior on strength { NumberAnimation { duration: Theme.slow } }
            }
            PadArt {
                id: art
                width: Math.min(hero.width * 0.5, 470)
                height: width * 0.66
                x: hero.width - width - 30
                y: (hero.height - height) / 2 + 14 + floatY
                property real floatY: 0
                light: home.lightColor
                lit: home.connected && home.lit
                input: gamepad.state
                showInput: gamepad.connected
                opacity: home.connected ? 1 : 0.4
                Behavior on opacity { NumberAnimation { duration: Theme.slow } }
                SequentialAnimation on floatY {
                    running: home.connected && home.current
                    loops: Animation.Infinite
                    NumberAnimation { from: 0; to: -7; duration: 2600; easing.type: Easing.InOutSine }
                    NumberAnimation { from: -7; to: 0; duration: 2600; easing.type: Easing.InOutSine }
                }
            }
            Row {           // tags
                x: 26; y: 24
                spacing: 8
                Repeater {
                    model: home.connected
                           ? [home.pad.bluetooth ? "Bluetooth" : "USB",
                              home.pad.touchpad === "hidraw" ? L.t("Тачпад через hidraw") : L.t("Тачпад"),
                              home.pad.hd_haptics ? L.t("HD-хаптика") : L.t("Вибрация")]
                           : [backend.daemonRunning ? L.t("Служба работает") : L.t("Служба выключена")]
                    Rectangle {
                        height: 30
                        width: tag.implicitWidth + 26
                        radius: 15
                        color: Qt.rgba(1, 1, 1, 0.07)
                        Text {
                            id: tag
                            anchors.centerIn: parent
                            text: modelData
                            color: Theme.text
                            font.pixelSize: 13
                        }
                    }
                }
            }
            Column {
                x: 30
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 30
                spacing: 8
                Text {
                    text: home.connected ? "DualSense" : L.t("Геймпад не подключён")
                    color: "white"
                    font.pixelSize: home.connected ? 54 : 38
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.5
                }
                Text {
                    text: !backend.daemonRunning ? L.t("Запустите службу, чтобы работали жесты")
                          : home.connected ? (home.hasBattery ? home.pad.battery + "% · " : "")
                                             + ({Charging: L.t("заряжается"), Full: L.t("заряжен"), Discharging: L.t("от батареи")}[home.pad.battery_status] || "")
                          : L.t("Нажмите кнопку PS на геймпаде")
                    color: Theme.textDim
                    font.pixelSize: 17
                }
                CButton {
                    visible: !backend.daemonRunning
                    kind: "accent"
                    text: L.t("Запустить службу")
                    onClicked: backend.service("start")
                }
            }
        }

        // mouse mode card + two shortcuts
        ColumnLayout {
            Layout.preferredWidth: 300
            Layout.maximumWidth: 300
            Layout.fillWidth: false
            Layout.preferredHeight: 360
            spacing: 14

            Rectangle {
                id: mouseCard
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Theme.radius
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: backend.mouse ? "#b8410c" : "#2a292e" }
                    GradientStop { position: 1; color: backend.mouse ? "#ff6a1f" : "#34333a" }
                }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 10
                    Text {
                        text: L.t("Мышь с тачпада")
                        color: "white"
                        font.pixelSize: 26
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: backend.mouse ? L.t("Тачпад ведёт курсор, ✕ или R2 — клик, ○ или R1 — правый клик.")
                                            : L.t("Геймпад управляет игрой. Включите, чтобы пользоваться рабочим столом с дивана.")
                        color: Qt.rgba(1, 1, 1, 0.8)
                        font.pixelSize: 14
                        lineHeight: 1.15
                    }
                    Item { Layout.fillHeight: true }
                    Text {
                        text: L.t("или дважды нажмите Share")
                        color: Qt.rgba(1, 1, 1, 0.6)
                        font.pixelSize: 13
                    }
                    Rectangle {
                        id: mouseBtn
                        Layout.fillWidth: true
                        height: 52
                        radius: 14
                        activeFocusOnTab: true
                        enabled: backend.daemonRunning && home.connected
                        opacity: enabled ? 1 : 0.5
                        function padAccept() { backend.setMouse(!backend.mouse) }
                        Keys.onReturnPressed: padAccept()
                        Keys.onSpacePressed: padAccept()
                        color: mma.pressed ? Qt.rgba(0, 0, 0, 0.5) : mma.containsMouse ? Qt.rgba(0, 0, 0, 0.38) : Qt.rgba(0, 0, 0, 0.28)
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        FocusRing { target: mouseBtn }
                        Text {
                            anchors.centerIn: parent
                            text: backend.mouse ? L.t("Выключить") : L.t("Включить")
                            color: "white"
                            font.pixelSize: 17
                            font.weight: Font.Medium
                        }
                        MouseArea {
                            id: mma
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: mouseBtn.padAccept()
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                MiniCard {
                    title: L.t("Подсветка")
                    sub: ({off: L.t("выключена"), static: L.t("цвет"), breathe: L.t("дыхание"), rainbow: L.t("радуга"),
                           battery: L.t("по заряду"), steam: L.t("как в Steam")})[root.s.light_mode] || ""
                    swatch: root.s.light_mode === "static" || root.s.light_mode === "breathe" ? root.s.light_color : ""
                    onClicked: root.go(1)
                }
                MiniCard {
                    title: L.t("Колесо")
                    sub: backend.wheelItems.length + L.t(" прил.")
                    icon: "ph:circles-three-plus"
                    onClicked: root.go(4)
                }
            }
        }
    }

    // ------------------------------------------------------------ quick actions
    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: 8
        Text { text: L.t("Быстрые действия"); color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
        Text {
            text: L.t("Все сочетания")
            color: allMa.containsMouse ? Theme.accent : Theme.textDim
            font.pixelSize: 14
            MouseArea { id: allMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.go(2) }
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: 4
        columnSpacing: 14
        rowSpacing: 14
        Repeater {
            model: [
                {a: "keyboard", i: "ph:keyboard", t: L.t("Клавиатура"), s: "Steam / Plasma"},
                {a: "overview", i: "ph:squares-four", t: L.t("Обзор окон"), s: ""},
                {a: "show_desktop", i: "ph:desktop", t: L.t("Рабочий стол"), s: ""},
                {a: "screenshot", i: "ph:camera", t: L.t("Скриншот"), s: ""},
                {a: "big_picture", i: "ph:arrows-out", t: "Big Picture", s: "Steam"},
                {a: "battery", i: "ph:battery-high", t: L.t("Заряд на экран"), s: ""},
                {a: "display_monitor", i: "ph:monitor", t: L.t("Только монитор"), s: "", ds: true},
                {a: "display_tv", i: "ph:television", t: L.t("Только телевизор"), s: "", ds: true}
            ]
            QuickTile {
                visible: !modelData.ds || backend.displaySwitcher
                icon: modelData.i
                label: modelData.t
                sub: root.chordFor(modelData.a) || modelData.s
                onClicked: backend.runAction(modelData.a)
            }
        }
    }

    // ---------------------------------------------------------------- gestures
    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: 8
        Text { text: L.t("Главные жесты"); color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
        Text {
            text: L.t("Проверить геймпад")
            color: testMa.containsMouse ? Theme.accent : Theme.textDim
            font.pixelSize: 14
            MouseArea { id: testMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.go(6) }
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: 4
        columnSpacing: 14
        rowSpacing: 14
        Repeater {
            model: [
                {g: "×2", b: "share", t: L.t("Мышь с тачпада"), d: L.t("Дважды нажать Share")},
                {g: "○", b: "circle", t: L.t("Окна и рабочий стол"), d: L.t("Нажать — Alt+Tab, держать — свернуть игру")},
                {g: "△", b: "triangle", t: L.t("Закрыть игру"), d: L.t("Держать ") + (root.s.long_press || 1.5).toFixed(1) + L.t(" с — принудительно")},
                {g: "R1", b: "r1", t: L.t("Колесо запуска"), d: L.t("Выбор правым стиком")}
            ]
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 196
                radius: Theme.radius
                color: Theme.surface
                Text {
                    x: 22; y: 14
                    text: modelData.g
                    color: modelData.b === "share" || modelData.b === "r1" ? Theme.text : Theme.glyphColor(modelData.b)
                    font.pixelSize: 64
                    font.weight: Font.Light
                    opacity: 0.9
                }
                Text {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 20
                    text: "Share +"
                    visible: modelData.b !== "share"
                    color: Theme.textFaint
                    font.pixelSize: 13
                }
                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 22
                    spacing: 4
                    Text { text: modelData.t; color: Theme.text; font.pixelSize: 16; font.weight: Font.Medium }
                    Text { text: modelData.d; color: Theme.textDim; font.pixelSize: 13; wrapMode: Text.WordWrap; width: parent.width }
                }
            }
        }
    }
}
