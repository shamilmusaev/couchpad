import QtQuick
import QtQuick.Shapes

// Clips children to a rounded rectangle without shaders: square clip plus
// four corner caps painted in the page background (`bg`). Works with every
// scene graph backend, including software rendering.
Item {
    id: rc
    property real radius: Theme.radius
    property color bg: Theme.bg
    default property alias content: inner.data
    Item {
        id: inner
        anchors.fill: parent
        clip: true
    }
    Repeater {
        model: 4
        Shape {
            readonly property bool isRight: index === 1 || index === 2
            readonly property bool isBottom: index >= 2
            x: isRight ? rc.width - rc.radius : 0
            y: isBottom ? rc.height - rc.radius : 0
            width: rc.radius
            height: rc.radius
            preferredRendererType: Shape.CurveRenderer
            // corner rotated so the cap always sits in the outer corner
            transform: Rotation {
                origin.x: rc.radius / 2
                origin.y: rc.radius / 2
                angle: index * 90
            }
            ShapePath {
                strokeWidth: -1
                fillColor: rc.bg
                startX: 0; startY: 0
                PathLine { x: rc.radius; y: 0 }
                PathArc { x: 0; y: rc.radius; radiusX: rc.radius; radiusY: rc.radius; direction: PathArc.Counterclockwise }
                PathLine { x: 0; y: 0 }
            }
        }
    }
}
