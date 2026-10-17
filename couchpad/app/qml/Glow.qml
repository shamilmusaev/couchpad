import QtQuick
import QtQuick.Shapes

// Soft radial glow (no hard edge).
Shape {
    id: g
    property color color: Theme.accent
    property real strength: 0.45
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
        strokeWidth: -1
        fillGradient: RadialGradient {
            centerX: g.width / 2; centerY: g.height / 2
            centerRadius: Math.min(g.width, g.height) / 2
            focalX: centerX; focalY: centerY
            GradientStop { position: 0.0; color: Theme.alpha(g.color, g.strength) }
            GradientStop { position: 0.45; color: Theme.alpha(g.color, g.strength * 0.35) }
            GradientStop { position: 1.0; color: Theme.alpha(g.color, 0) }
        }
        PathAngleArc {
            centerX: g.width / 2; centerY: g.height / 2
            radiusX: g.width / 2; radiusY: g.height / 2
            startAngle: 0; sweepAngle: 360
        }
    }
}
