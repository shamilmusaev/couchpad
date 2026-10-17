import QtQuick
import QtQuick.Shapes

// Live DualSense, Sterling Silver, front view. Mirrors the real pad:
// buttons press in, sticks tilt, triggers travel, fingers show on the
// touchpad, the light bar glows in its real colour and the whole pad leans
// with the accelerometer.
Item {
    id: art
    property color light: "#3d7bff"
    property bool lit: true
    property var input: ({})            // gamepad.state
    property bool showInput: false
    property bool tilt: showInput
    readonly property var b: input && input.buttons ? input.buttons : ({})
    implicitWidth: 600
    implicitHeight: 400

    function on(name) { return showInput && b[name] === true }
    function axis(name) { return showInput && input[name] ? input[name] : 0 }

    // motion: show movement, then settle back to the resting pose
    readonly property real pitch: tilt ? (input.pitch || 0) : 0
    readonly property real roll: tilt ? (input.roll || 0) : 0
    property real basePitch: pitch
    property real baseRoll: roll
    Behavior on basePitch { NumberAnimation { duration: 2200; easing.type: Easing.OutCubic } }
    Behavior on baseRoll { NumberAnimation { duration: 2200; easing.type: Easing.OutCubic } }

    // Sterling Silver palette
    readonly property color hi: "#f4f5f7"
    readonly property color mid: "#cfd2d7"
    readonly property color lo: "#9a9ea6"
    readonly property color rim: "#7c8088"
    readonly property color core: "#2a2b30"
    readonly property color coreLo: "#141518"
    readonly property color ink: "#6b6e76"
    readonly property color pressed: Theme.accent

    // inner grip edges + belly arch, shared by the shell and the dark core
    readonly property string belly:
        "C 452 316 432 292 400 284 C 360 270 240 270 200 284 C 168 292 148 316 130 345 "
    readonly property string outline:
        "M 160 40 C 230 30 370 30 440 40 C 500 46 545 62 566 100 " +
        "C 588 140 598 220 596 290 C 594 340 584 386 545 392 C 512 397 488 375 470 345 " +
        belly +
        "C 112 375 88 397 55 392 C 16 386 6 340 4 290 C 2 220 12 140 34 100 C 55 62 100 46 160 40 Z"

    Item {
        id: canvas
        width: 600; height: 400
        anchors.centerIn: parent
        scale: Math.min(art.width / 600, art.height / 400)
        transform: [
            Rotation { origin.x: 300; origin.y: 200; axis { x: 1; y: 0; z: 0 }
                       angle: Math.max(-28, Math.min(28, (art.pitch - art.basePitch) * 0.9)) },
            Rotation { origin.x: 300; origin.y: 200; axis { x: 0; y: 1; z: 0 }
                       angle: Math.max(-28, Math.min(28, (art.roll - art.baseRoll) * 0.9)) },
            Rotation { origin.x: 300; origin.y: 200
                       angle: Math.max(-10, Math.min(10, (art.roll - art.baseRoll) * -0.25)) }
        ]

        Glow {          // light bar spilling onto the surface behind
            x: 120; y: -50; width: 360; height: 240
            visible: art.lit
            color: art.light
            strength: 0.5
        }

        // ---- triggers and bumpers (behind the shell) ---------------------------
        Repeater {
            model: [{n: "l2", x: 86}, {n: "r2", x: 424}]
            Item {
                x: modelData.x; y: 2 + art.axis(modelData.n) * 9
                width: 90; height: 50
                Rectangle {
                    anchors.fill: parent
                    radius: 20
                    gradient: Gradient {
                        GradientStop { position: 0; color: art.hi }
                        GradientStop { position: 1; color: art.lo }
                    }
                    border.color: art.rim
                }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 10
                    width: parent.width - 34; height: 4; radius: 2
                    color: Qt.rgba(0, 0, 0, 0.12)
                    Rectangle {
                        height: parent.height; radius: 2
                        width: parent.width * art.axis(modelData.n)
                        color: art.pressed
                    }
                }
            }
        }
        Repeater {
            model: [{n: "l1", x: 74, r: -7}, {n: "r1", x: 416, r: 7}]
            Rectangle {
                readonly property bool down: art.on(modelData.n)   // changes only on press/release
                x: modelData.x; y: down ? 37 : 32
                width: 110; height: 20; radius: 10
                rotation: modelData.r
                gradient: Gradient {
                    GradientStop { position: 0; color: parent.down ? art.pressed : art.hi }
                    GradientStop { position: 1; color: parent.down ? Qt.darker(art.pressed, 1.3) : art.mid }
                }
                border.color: art.rim
                Behavior on y { NumberAnimation { duration: 60 } }
            }
        }

        // ---- shell ---------------------------------------------------------------
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {         // silver body
                strokeColor: art.rim
                strokeWidth: 1.6
                fillGradient: LinearGradient {
                    x1: 140; y1: 30; x2: 470; y2: 400
                    GradientStop { position: 0.0; color: art.hi }
                    GradientStop { position: 0.5; color: art.mid }
                    GradientStop { position: 1.0; color: art.lo }
                }
                PathSvg { path: art.outline }
            }
            ShapePath {         // dark core: around the sticks and down between the grips
                strokeColor: "#0e0f11"
                strokeWidth: 1
                fillGradient: LinearGradient {
                    x1: 300; y1: 150; x2: 300; y2: 360
                    GradientStop { position: 0; color: art.core }
                    GradientStop { position: 1; color: art.coreLo }
                }
                PathSvg {
                    path: "M 176 150 L 424 150 C 444 190 450 252 470 345 " + art.belly +
                          "C 150 252 156 190 176 150 Z"
                }
            }
            ShapePath {         // sheen along the top edge
                strokeColor: Qt.rgba(1, 1, 1, 0.65)
                strokeWidth: 2
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathSvg { path: "M 64 92 C 96 58 130 48 168 44 M 432 44 C 470 48 504 58 536 92" }
            }
            ShapePath {         // soft highlight on the left grip
                strokeColor: "transparent"
                fillColor: Qt.rgba(1, 1, 1, 0.18)
                PathSvg { path: "M 36 150 C 46 112 70 90 100 80 C 70 112 56 160 52 220 C 50 260 52 300 44 330 C 30 290 28 200 36 150 Z" }
            }
            ShapePath {         // shade on the right grip
                strokeColor: "transparent"
                fillColor: Qt.rgba(0, 0, 0, 0.10)
                PathSvg { path: "M 566 150 C 580 200 586 260 584 320 C 582 360 570 384 545 390 C 566 360 572 300 568 240 C 566 200 562 170 556 140 Z" }
            }
        }

        // ---- touchpad + light bar --------------------------------------------------
        Item {
            id: pad
            x: 190; y: 40; width: 220; height: 116
            readonly property bool down: art.on("pad") || (art.showInput && art.input.click === true)
            scale: down ? 0.985 : 1
            Behavior on scale { NumberAnimation { duration: 60 } }
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: art.rim
                    strokeWidth: 1.2
                    fillGradient: LinearGradient {
                        x1: 0; y1: 0; x2: 0; y2: 116
                        GradientStop { position: 0; color: pad.down ? art.mid : "#fbfbfc" }
                        GradientStop { position: 1; color: pad.down ? art.lo : "#d9dce0" }
                    }
                    // wider at the top, rounded bottom corners
                    PathSvg { path: "M 10 2 L 210 2 Q 219 2 218 12 L 211 102 Q 210 114 198 114 L 22 114 Q 10 114 9 102 L 2 12 Q 1 2 10 2 Z" }
                }
            }
            Repeater {
                model: art.showInput && art.input.touch ? art.input.touch : []
                Item {
                    x: 12 + modelData.x * (pad.width - 24) - 18
                    y: 6 + modelData.y * (pad.height - 14) - 18
                    width: 36; height: 36
                    Glow { anchors.fill: parent; anchors.margins: -10; color: art.pressed; strength: 0.7 }
                    Rectangle { anchors.centerIn: parent; width: 14; height: 14; radius: 7; color: "white"; border.color: art.pressed; border.width: 3 }
                }
            }
        }
        Shape {             // light bar: two strips hugging the touchpad
            id: bar
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            readonly property string strips: "M 186 46 C 190 80 192 118 197 152 M 414 46 C 410 80 408 118 403 152"
            ShapePath {
                strokeColor: art.lit ? Theme.alpha(art.light, 0.35) : "transparent"
                strokeWidth: 11; capStyle: ShapePath.RoundCap; fillColor: "transparent"
                PathSvg { path: bar.strips }
            }
            ShapePath {
                strokeColor: art.lit ? Qt.lighter(art.light, 1.3) : "#a7abb2"
                strokeWidth: 3.5; capStyle: ShapePath.RoundCap; fillColor: "transparent"
                PathSvg { path: bar.strips }
            }
        }

        // ---- create / options ------------------------------------------------------
        Repeater {
            model: [{n: "share", x: 160, r: -18}, {n: "options", x: 428, r: 18}]
            Rectangle {
                x: modelData.x; y: 54; width: 12; height: 26; radius: 6
                rotation: modelData.r
                readonly property bool down: art.on(modelData.n)
                color: down ? art.pressed : art.mid
                border.color: art.rim
                scale: down ? 0.88 : 1
            }
        }

        // ---- d-pad -------------------------------------------------------------------
        Repeater {
            model: [{n: "up", r: 0}, {n: "right", r: 90}, {n: "down", r: 180}, {n: "left", r: 270}]
            Item {
                id: key
                readonly property bool down: art.on(modelData.n)
                x: 112 - 17; y: 140 - 17 - 32
                width: 34; height: 34
                transform: Rotation { origin.x: 17; origin.y: 49; angle: modelData.r }
                scale: down ? 0.9 : 1
                Behavior on scale { NumberAnimation { duration: 60 } }
                Shape {
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: art.rim
                        strokeWidth: 1.2
                        fillGradient: LinearGradient {
                            x1: 0; y1: 0; x2: 0; y2: 34
                            GradientStop { position: 0; color: key.down ? art.pressed : art.hi }
                            GradientStop { position: 1; color: key.down ? Qt.darker(art.pressed, 1.25) : art.mid }
                        }
                        PathSvg { path: "M 5 6 Q 5 1 10 1 L 24 1 Q 29 1 29 6 L 29 22 L 17 33 L 5 22 Z" }
                    }
                    ShapePath {     // arrow mark
                        strokeColor: "transparent"
                        fillColor: key.down ? "white" : art.ink
                        PathSvg { path: "M 17 8 L 22 15 L 12 15 Z" }
                    }
                }
            }
        }

        // ---- face buttons ------------------------------------------------------------
        Repeater {
            model: [{n: "triangle", x: 488, y: 104}, {n: "circle", x: 524, y: 140},
                    {n: "cross", x: 488, y: 176}, {n: "square", x: 452, y: 140}]
            Item {
                id: face
                readonly property bool down: art.on(modelData.n)
                x: modelData.x - 17; y: modelData.y - 17; width: 34; height: 34
                scale: down ? 0.88 : 1
                Behavior on scale { NumberAnimation { duration: 60 } }
                Glow { anchors.fill: parent; anchors.margins: -14; visible: face.down; color: art.pressed; strength: 0.6 }
                Rectangle {
                    anchors.fill: parent
                    radius: 17
                    gradient: Gradient {
                        GradientStop { position: 0; color: face.down ? art.pressed : art.hi }
                        GradientStop { position: 1; color: face.down ? Qt.darker(art.pressed, 1.3) : art.mid }
                    }
                    border.color: art.rim
                }
                Shape {         // engraved symbol
                    id: sym
                    anchors.centerIn: parent
                    width: 14; height: 14
                    preferredRendererType: Shape.CurveRenderer
                    readonly property color ink: face.down ? "white" : art.ink
                    ShapePath {
                        strokeColor: sym.ink; strokeWidth: 1.8; fillColor: "transparent"
                        capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                        PathSvg {
                            path: modelData.n === "triangle" ? "M 7 1 L 13.5 12.5 L 0.5 12.5 Z"
                                : modelData.n === "circle" ? "M 7 0.5 A 6.5 6.5 0 1 1 6.99 0.5 Z"
                                : modelData.n === "cross" ? "M 1.5 1.5 L 12.5 12.5 M 12.5 1.5 L 1.5 12.5"
                                : "M 1.5 1.5 L 12.5 1.5 L 12.5 12.5 L 1.5 12.5 Z"
                        }
                    }
                }
            }
        }

        // ---- speaker, sticks, PS, mute -----------------------------------------------
        Grid {
            x: 300 - (7 * 3 + 6 * 4) / 2; y: 168
            columns: 7; spacing: 4
            Repeater { model: 21; Rectangle { width: 3; height: 3; radius: 1.5; color: "#47484e" } }
        }
        Repeater {
            model: [{n: "l3", ax: "lx", ay: "ly", x: 220}, {n: "r3", ax: "rx", ay: "ry", x: 380}]
            Item {
                id: stick
                x: modelData.x - 40; y: 182; width: 80; height: 80
                // square stick range -> round travel, so the cap stays in its well
                readonly property real rx: art.axis(modelData.ax)
                readonly property real ry: art.axis(modelData.ay)
                readonly property real len: Math.max(1, Math.sqrt(rx * rx + ry * ry))
                readonly property real dx: rx / len
                readonly property real dy: ry / len
                readonly property bool down: art.on(modelData.n)
                Rectangle {     // well
                    anchors.fill: parent; radius: 40
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#0c0d0f" }
                        GradientStop { position: 1; color: "#1d1e22" }
                    }
                    border.color: "#3a3b41"
                }
                Item {          // cap leans with the stick
                    width: 58; height: 58
                    x: 11 + stick.dx * 12
                    y: 11 + stick.dy * 12
                    scale: stick.down ? 0.92 : 1
                    Rectangle {
                        anchors.fill: parent; radius: 29
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#45464c" }
                            GradientStop { position: 1; color: "#1c1d21" }
                        }
                        border.color: stick.down ? art.pressed : "#55565d"
                        border.width: stick.down ? 3 : 1.4
                    }
                    Rectangle {     // concave top
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: -stick.dx * 3
                        anchors.verticalCenterOffset: -stick.dy * 3
                        width: 38; height: 38; radius: 19
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#1c1d21" }
                            GradientStop { position: 1; color: "#303136" }
                        }
                    }
                    Rectangle {     // grip ring
                        anchors.centerIn: parent
                        width: 48; height: 48; radius: 24
                        color: "transparent"
                        border.color: Qt.rgba(1, 1, 1, 0.06)
                        border.width: 3
                    }
                    Rectangle {
                        visible: Math.abs(stick.dx) + Math.abs(stick.dy) > 0.15
                        width: 6; height: 6; radius: 3
                        color: art.pressed
                        x: 26 + stick.dx * 15
                        y: 26 + stick.dy * 15
                    }
                }
            }
        }
        Text {          // PS button
            anchors.horizontalCenter: canvas.horizontalCenter
            y: 210
            text: "PS"
            color: art.on("ps") ? art.pressed : "#9a9ca3"
            font.pixelSize: 16
            font.weight: Font.Black
            font.italic: true
            font.letterSpacing: -1
        }
        Rectangle {     // mute
            anchors.horizontalCenter: canvas.horizontalCenter
            y: 242; width: 30; height: 8; radius: 4
            color: "#35363b"
            border.color: "#4a4b51"
        }
    }
}
