import QtQuick
import QtQuick.Layouts

PageBase {
    id: pg
    readonly property var s: root.s
    readonly property string mode: !s.rumble ? "off" : s.haptics === "rumble" ? "rumble" : "hd"

    // HD haptics: keep the controller's haptics channel awake while this page
    // is open, so "Try it" clicks play at once and short ones aren't lost.
    Timer {
        running: pg.current && pg.mode === "hd" && root.visible
        interval: 2000
        repeat: true
        triggeredOnStart: true
        onTriggered: backend.warmHaptics()
    }

    Card {
        Layout.fillWidth: true
        ColumnLayout {
            width: parent.width
            spacing: 14
            SectionTitle {
                text: L.t("Тип отклика")
                subtitle: L.t("Щелчки при удержании, переключении окон, выборе в колесе и громкости")
            }
            Segmented {
                Layout.fillWidth: true
                stretch: true
                model: [{value: "off", label: L.t("Выключен"), icon: "ph:speaker-slash"},
                        {value: "rumble", label: L.t("Вибрация"), icon: "ph:game-controller"},
                        {value: "hd", label: L.t("HD-хаптика"), icon: "ph:speaker-high"}]
                current: pg.mode
                onPicked: (v) => {
                    backend.set("rumble", v !== "off")
                    if (v !== "off") backend.set("haptics", v === "hd" ? "auto" : "rumble")
                }
            }
            Rectangle {
                visible: pg.mode === "hd"
                Layout.fillWidth: true
                implicitHeight: hint.implicitHeight + 24
                radius: 12
                color: Theme.alpha(Theme.warn, 0.1)
                border.color: Theme.alpha(Theme.warn, 0.4)
                Text {
                    id: hint
                    anchors.fill: parent
                    anchors.margins: 12
                    wrapMode: Text.WordWrap
                    text: L.t("Экспериментально: звуковые катушки DualSense по Bluetooth (протокол SAxense). ") +
                          L.t("Если щелчков не слышно или есть помехи — выберите «Вибрация».")
                    color: Theme.text
                    font.pixelSize: 13
                }
            }
            SettingRow {
                enabled: pg.mode !== "off"
                opacity: enabled ? 1 : 0.5
                title: L.t("Сила")
                icon: "ph:speaker-high"
                CSlider {
                    from: 0.1; to: 3; stepSize: 0.1
                    value: s.haptic_strength
                    format: function (v) { return Math.round(v * 100) + "%" }
                    onMoved: backend.set("haptic_strength", value)
                }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        enabled: pg.mode !== "off" && root.connected
        opacity: enabled ? 1 : 0.5
        ColumnLayout {
            width: parent.width
            spacing: 14
            SectionTitle { text: L.t("Попробовать"); subtitle: L.t("Нажмите — геймпад отзовётся этим щелчком") }
            GridLayout {
                Layout.fillWidth: true
                columns: Math.max(3, Math.floor(width / 170))
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    model: backend.hapticPatterns
                    CButton {
                        Layout.fillWidth: true
                        text: modelData.label
                        onPressed: backend.testHaptic(modelData.name)   // on press: no release lag
                    }
                }
            }
            CButton {
                text: L.t("Проиграть все")
                kind: "accent"
                iconName: "ph:play"
                onPressed: backend.testHaptic("demo")
            }
        }
    }
}
