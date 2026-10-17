import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 1320
    height: 860
    minimumWidth: 1040
    minimumHeight: 680
    visible: false
    title: "Couchpad"
    color: Theme.bg
    font.family: Theme.font

    property int page: 0
    property bool popupOpen: false
    property bool padActive: false            // last input came from the gamepad
    readonly property var s: backend.settings
    readonly property var pad: backend.pad
    readonly property bool connected: !!pad.uniq
    readonly property var pages: [
        {title: L.t("Главная"), icon: "ph:house", sub: ""},
        {title: L.t("Подсветка"), icon: "ph:sun", sub: L.t("Световая полоса и индикаторы DualSense")},
        {title: L.t("Сочетания"), icon: "ph:keyboard", sub: L.t("Что делает Share + кнопка")},
        {title: L.t("Мышь"), icon: "ph:mouse-simple", sub: L.t("Тачпад и стики в режиме мыши")},
        {title: L.t("Колесо"), icon: "ph:circles-three-plus", sub: L.t("Быстрый запуск по Share + R1")},
        {title: L.t("Отклик"), icon: "ph:speaker-high", sub: L.t("Вибрация и HD-хаптика")},
        {title: L.t("Тест геймпада"), icon: "ph:game-controller", sub: L.t("Кнопки, стики, курки и тачпад вживую")},
        {title: L.t("Система"), icon: "ph:gear-six", sub: L.t("Служба, сообщения, Steam и прочее")}
    ]
    readonly property int mainPages: 6        // the rest sit at the bottom of the sidebar

    // search index: words -> page
    readonly property var searchIndex: [
        {t: L.t("Цвет подсветки"), p: 1}, {t: L.t("Яркость подсветки"), p: 1}, {t: L.t("Дыхание / радуга"), p: 1},
        {t: L.t("Подсветка по заряду"), p: 1}, {t: L.t("Индикаторы игрока"), p: 1}, {t: L.t("Светодиод микрофона"), p: 1},
        {t: L.t("Share + кнопка"), p: 2}, {t: L.t("Время удержания"), p: 2}, {t: L.t("Двойное нажатие Share"), p: 2},
        {t: L.t("Скорость курсора"), p: 3}, {t: L.t("Ускорение"), p: 3}, {t: L.t("Прокрутка"), p: 3}, {t: L.t("Клик касанием"), p: 3},
        {t: L.t("Мёртвая зона стика"), p: 3}, {t: L.t("Приложения в колесе"), p: 4}, {t: L.t("Вибрация"), p: 5},
        {t: L.t("HD-хаптика"), p: 5}, {t: L.t("Проверка кнопок"), p: 6}, {t: L.t("Служба и автозапуск"), p: 7},
        {t: L.t("Значок в трее"), p: 7}, {t: L.t("Сообщения поверх игр"), p: 7}, {t: L.t("Экранная клавиатура"), p: 7},
        {t: L.t("Выключать геймпад без дела"), p: 7}, {t: L.t("Раскладка Steam"), p: 7}, {t: L.t("Журнал службы"), p: 7}
    ]

    Binding { target: L; property: "en"; value: backend.translations }
    Binding { target: L; property: "lang"; value: backend.lang }

    onClosing: (close) => {
        if (backend.settings.tray) {
            close.accepted = false
            root.hide()
        }
    }

    function go(i) {
        if (i < 0 || i >= pages.length || i === page) return
        page = i
    }
    function toast(title, body, kind) { toasts.push(title, body, kind) }
    function chordFor(action) {
        var c = backend.chords
        for (var i = 0; i < c.length; i++) if (c[i].action === action) return "Share + " + c[i].glyph
        return ""
    }

    Connections {
        target: backend
        function onToast(title, body, kind) { root.toast(title, body, kind) }
    }

    // ---------------------------------------------------------------- gamepad
    readonly property bool navOn: root.active && !backend.mouse
    onNavOnChanged: gamepad.setNavigation(navOn)
    // live controller picture (touch + motion are read only while it shows)
    readonly property bool liveInput: root.visible && (page === 0 || page === 1 || page === 6)
    onLiveInputChanged: gamepad.setLive(liveInput)
    Connections {
        target: gamepad
        function onNav(dir) { root.padNav(dir) }
    }
    MouseArea {      // any mouse use hides the gamepad focus ring
        anchors.fill: parent
        z: 1000
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
        onPositionChanged: root.padActive = false
    }

    function focusables(item, out) {
        if (!item || !item.visible || !item.enabled) return out
        if (item.activeFocusOnTab && item.width > 0) out.push(item)
        for (var i = 0; i < item.children.length; i++) focusables(item.children[i], out)
        return out
    }
    function padNav(dir) {
        padActive = true
        var it = root.activeFocusItem
        if (popupOpen || dialogs.open || search.open) {
            var keys = {up: Qt.Key_Up, down: Qt.Key_Down, left: Qt.Key_Backtab, right: Qt.Key_Tab,
                        accept: Qt.Key_Return, back: Qt.Key_Escape}
            if (keys[dir] !== undefined) app.sendKey(keys[dir])
            return
        }
        switch (dir) {
        case "prev": go(page - 1); focusFirst(); return
        case "next": go(page + 1); focusFirst(); return
        case "menu": navList.forceActiveFocus(); return
        case "back":
            if (it && isInside(it, content)) navList.forceActiveFocus()
            return
        case "up":
        case "down":
            if (!it || it === root.contentItem) { focusFirst(); return }
            if (isInside(it, navList)) {
                go(page + (dir === "down" ? 1 : -1))
                return
            }
            var next = it.nextItemInFocusChain(dir === "down")
            var guard = 0
            while (next && (isInside(next, navList) || isInside(next, topBar)) && guard++ < 200)
                next = next.nextItemInFocusChain(dir === "down")
            if (next) next.forceActiveFocus(dir === "down" ? Qt.TabFocusReason : Qt.BacktabFocusReason)
            return
        case "left":
            if (it && it.padLeft) it.padLeft()
            else if (it && isInside(it, content)) navList.forceActiveFocus()
            return
        case "right":
            if (it && it.padRight) it.padRight()
            else if (it && isInside(it, navList)) focusFirst()
            return
        case "accept":
            if (!it) return
            if (isInside(it, navList)) { focusFirst(); return }
            if (it.padAccept) it.padAccept()
            else if (it.clicked) it.clicked()
            return
        }
    }
    function isInside(item, ancestor) {
        for (var p = item; p; p = p.parent) if (p === ancestor) return true
        return false
    }
    function focusFirst() {
        Qt.callLater(function () {
            var list = focusables(stack.children[page], [])
            if (list.length) list[0].forceActiveFocus(Qt.TabFocusReason)
        })
    }
    // keep the focused control on screen
    onActiveFocusItemChanged: {
        var it = activeFocusItem
        if (!it) return
        for (var p = it.parent; p; p = p.parent) {
            if (p.isPageFlick) {
                var pos = it.mapToItem(p.contentItem, 0, 0)
                var top = pos.y - 24, bottom = pos.y + it.height + 24
                if (top < p.contentY) p.scrollTo(Math.max(0, top))
                else if (bottom > p.contentY + p.height) p.scrollTo(Math.min(p.contentHeight - p.height, bottom - p.height))
                return
            }
        }
    }

    // ------------------------------------------------------------------ layout
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // sidebar ---------------------------------------------------------------
        Item {
            Layout.fillHeight: true
            Layout.preferredWidth: 244

            Row {
                id: logo
                x: 34; y: 34
                spacing: 12
                Image {
                    source: "../../data/couchpad.svg"
                    sourceSize: Qt.size(64, 64)
                    width: 32; height: 32
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "COUCHPAD"
                    color: Theme.text
                    font.family: Theme.font
                    font.pixelSize: 19
                    font.weight: Font.Bold
                    font.letterSpacing: 1.6
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            FocusScope {
                id: navList
                anchors.top: logo.bottom
                anchors.topMargin: 44
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: padCard.top
                anchors.bottomMargin: 20
                activeFocusOnTab: true
                Keys.onUpPressed: root.go(root.page - 1)
                Keys.onDownPressed: root.go(root.page + 1)
                Keys.onRightPressed: root.focusFirst()
                Keys.onReturnPressed: root.focusFirst()

                // active marker on the window edge
                Rectangle {
                    id: marker
                    readonly property Item tgt: root.page < root.mainPages ? navTop.children[root.page]
                                                                           : navBottom.children[root.page - root.mainPages]
                    x: 0
                    width: 3
                    height: 26
                    radius: 2
                    color: Theme.accent
                    y: tgt ? tgt.y + (tgt.parent ? tgt.parent.y : 0) + (tgt.height - height) / 2 : 0
                    Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    radius: 14
                    color: "transparent"
                    border.color: Theme.accentText
                    border.width: 1.5
                    visible: navList.activeFocus && root.padActive
                }

                component NavItem: Item {
                    id: ni
                    property int idx
                    readonly property bool current: root.page === idx
                    width: navList.width
                    height: 48
                    Row {
                        x: 34
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 14
                        Rectangle {
                            width: 32; height: 32; radius: 10
                            color: ni.current ? Theme.accentSoft : nma.containsMouse ? Theme.surface2 : Theme.surface
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                            Icon {
                                anchors.centerIn: parent
                                name: root.pages[ni.idx].icon
                                size: 18
                                mono: true
                                monoColor: ni.current ? Theme.accent : Theme.textDim
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.pages[ni.idx].title
                            color: ni.current ? Theme.accent : nma.containsMouse ? Theme.text : "#d6d3d8"
                            font.family: Theme.font
                            font.pixelSize: 15
                            font.weight: ni.current ? Font.DemiBold : Font.Normal
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                        }
                    }
                    MouseArea {
                        id: nma
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.go(ni.idx)
                    }
                }

                Column {
                    id: navTop
                    width: parent.width
                    spacing: 4
                    Repeater { model: root.mainPages; NavItem { idx: index } }
                }
                Column {
                    id: navBottom
                    anchors.bottom: parent.bottom
                    width: parent.width
                    spacing: 4
                    Repeater { model: root.pages.length - root.mainPages; NavItem { idx: root.mainPages + index } }
                }
            }

            // controller card
            Rectangle {
                id: padCard
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 24
                height: 96
                radius: 18
                color: Theme.surface
                border.color: Theme.border
                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Text {
                        text: !backend.daemonRunning ? L.t("Служба выключена") : root.connected ? "DualSense" : L.t("Нет геймпада")
                        color: Theme.text; font.family: Theme.font; font.pixelSize: 15; font.weight: Font.Medium
                    }
                    Text {
                        text: root.connected ? (pad.bluetooth ? "Bluetooth" : "USB") + (backend.mouse ? L.t(" · мышь") : "")
                                             : backend.daemonRunning ? L.t("Нажмите PS") : L.t("Включите в «Система»")
                        color: Theme.textDim; font.family: Theme.font; font.pixelSize: 12
                    }
                    Rectangle {
                        visible: root.connected && pad.battery !== undefined && pad.battery !== null
                        width: padCard.width - 36; height: 4; radius: 2
                        color: Theme.surface2
                        Rectangle {
                            height: parent.height; radius: 2
                            width: parent.width * (pad.battery || 0) / 100
                            color: pad.battery_status === "Charging" || (pad.battery || 0) > 30 ? Theme.ok
                                   : (pad.battery || 0) > 15 ? Theme.warn : Theme.danger
                            Behavior on width { NumberAnimation { duration: Theme.slow } }
                        }
                    }
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18
                    anchors.top: parent.top
                    anchors.topMargin: 20
                    visible: root.connected && pad.battery !== undefined && pad.battery !== null
                    text: (pad.battery || 0) + "%"
                    color: Theme.text; font.family: Theme.font; font.pixelSize: 15; font.weight: Font.DemiBold
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.go(6)
                }
            }
        }

        // content ----------------------------------------------------------------
        Item {
            id: content
            Layout.fillWidth: true
            Layout.fillHeight: true

            // top bar: search + status
            Item {
                id: topBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: 16
                anchors.rightMargin: 40
                height: 100
                z: 10

                SearchBox {
                    id: search
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(460, parent.width - 400)
                    index: root.searchIndex
                    onChosen: (p) => { root.go(p); root.focusFirst() }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    RoundIconButton {
                        icon: "ph:hand-pointing"
                        on: backend.mouse
                        enabled: backend.daemonRunning && root.connected
                        onClicked: backend.setMouse(!backend.mouse)
                    }
                    RoundIconButton {
                        icon: "ph:sun"
                        swatch: root.pad.light ? Qt.rgba(root.pad.light[0] / 255, root.pad.light[1] / 255, root.pad.light[2] / 255, 1) : "transparent"
                        onClicked: root.go(1)
                    }
                    Rectangle {
                        height: 44
                        width: pill.implicitWidth + 32
                        radius: 22
                        color: Theme.surface
                        border.color: Theme.border
                        Row {
                            id: pill
                            anchors.centerIn: parent
                            spacing: 10
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                anchors.verticalCenter: parent.verticalCenter
                                color: !backend.daemonRunning ? Theme.danger : root.connected ? Theme.ok : Theme.warn
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: !backend.daemonRunning ? L.t("Служба выключена") : root.connected ? "DualSense" : L.t("Ожидание геймпада")
                                color: Theme.text; font.family: Theme.font; font.pixelSize: 14; font.weight: Font.Medium
                            }
                            BatteryGlyph {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: root.connected && pad.battery !== null && pad.battery !== undefined
                                level: pad.battery || 0
                                charging: pad.battery_status === "Charging"
                            }
                        }
                    }
                }
            }

            Item {
                id: stack
                anchors.top: topBar.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: hintBar.top
                clip: true
                PageHome { index: 0 }
                PageLights { index: 1 }
                PageChords { index: 2 }
                PageMouse { index: 3 }
                PageWheel { index: 4 }
                PageHaptics { index: 5 }
                PageTester { index: 6 }
                PageSystem { index: 7 }
            }

            // gamepad hints
            Item {
                id: hintBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: gamepad.connected ? 52 : 0
                visible: height > 0
                Behavior on height { NumberAnimation { duration: Theme.normal } }
                Row {
                    anchors.right: parent.right
                    anchors.rightMargin: 40
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 26
                    Repeater {
                        model: [{g: "L1 R1", t: L.t("Разделы")}, {g: "✕", t: L.t("Выбрать"), c: "cross"}, {g: "○", t: L.t("Назад"), c: "circle"}]
                        Row {
                            spacing: 8
                            Rectangle {
                                width: Math.max(24, gl.implicitWidth + 12); height: 24; radius: 12
                                color: Theme.surface2
                                anchors.verticalCenter: parent.verticalCenter
                                Text {
                                    id: gl
                                    anchors.centerIn: parent
                                    text: modelData.g
                                    color: modelData.c ? Theme.glyphColor(modelData.c) : Theme.text
                                    font.family: Theme.font; font.pixelSize: 12; font.weight: Font.Bold
                                }
                            }
                            Text { text: modelData.t; color: Theme.textDim; font.family: Theme.font; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
        }
    }

    Dialogs { id: dialogs }
    Toasts { id: toasts }
}
