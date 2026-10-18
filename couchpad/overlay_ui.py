"""On-screen overlay (PySide6): quick-launch wheel, toasts and the hold ring.

A long-lived child of the daemon, so everything opens instantly. On KDE the
windows are wlr-layer-shell surfaces in the overlay layer (LayerShellQt via
ctypes): they show above fullscreen games, never steal focus (toasts) and
appear on the screen that is in use.

Protocol, one JSON object per line on stdin:
    {"cmd": "show", "items": [{"name", "icon"}...], "sel": null, "accent": "#hex"}
    {"cmd": "select", "i": 2}
    {"cmd": "hide"}
    {"cmd": "osd", "key", "title", "body", "icon", "accent", "progress", "timeout"}
    {"cmd": "hold", "title", "body", "icon", "accent", "duration"}
    {"cmd": "hold_end", "done": true}
    {"cmd": "quit"}
Prints {"event": "ready", "osd": bool} once, then "shown"/"hidden" and the
user's choices in the wheel: {"event": "select"|"launch"|"cancel", "i"}.
"""

import ctypes
import json
import math
import os
import sys

from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, QSocketNotifier, Qt, QTimer,
                            QVariantAnimation)
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

from .qticons import bundled, ensure_icon_theme
from .i18n import _, set_lang

TITLE = "couchpad-wheel"
ACCENT = "#ff6a1f"
CONFIRM_MS = 560                      # launch confirmation, then gone


# ---------------------------------------------------------------------------
# LayerShellQt through ctypes (no Python bindings exist)

class LayerShell:
    TOP, BOTTOM, LEFT, RIGHT = 1, 2, 4, 8
    LAYER_OVERLAY = 3
    KBD_NONE, KBD_EXCLUSIVE, KBD_ON_DEMAND = 0, 1, 2

    def __init__(self):
        self.lib = None
        if os.environ.get("COUCHPAD_NO_LAYER_SHELL") or \
                QApplication.platformName() != "wayland":
            return
        try:
            lib = ctypes.CDLL("libLayerShellQtInterface.so.6")
            self.get = lib._ZN12LayerShellQt6Window3getEP7QWindow
            self.get.restype = ctypes.c_void_p
            self.get.argtypes = [ctypes.c_void_p]
            sig = [ctypes.c_void_p, ctypes.c_int]
            for name, sym in (("layer", "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE"),
                              ("anchors", "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE"),
                              ("keyboard", "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE"),
                              ("exclusive", "_ZN12LayerShellQt6Window16setExclusiveZoneEi")):
                fn = getattr(lib, sym)
                fn.argtypes = sig
                setattr(self, "_" + name, fn)
            self._margins = lib._ZN12LayerShellQt6Window10setMarginsERK8QMargins
            self._margins.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int * 4)]
            self.lib = lib
        except (OSError, AttributeError):
            self.lib = None

    @property
    def ok(self):
        return self.lib is not None

    def setup(self, widget, anchors, keyboard, margins=(0, 0, 0, 0)):
        """Turn a not-yet-shown top-level widget into an overlay surface."""
        import shiboken6
        widget.winId()
        handle = self.get(shiboken6.getCppPointer(widget.windowHandle())[0])
        if not handle:
            return None
        self._layer(handle, self.LAYER_OVERLAY)
        self._anchors(handle, anchors)
        self._exclusive(handle, -1)               # ignore panels
        self._keyboard(handle, keyboard)
        self._margins(handle, ctypes.byref((ctypes.c_int * 4)(*margins)))
        return handle

    def keyboard(self, handle, mode):
        if handle:
            self._keyboard(handle, mode)


# ---------------------------------------------------------------------------
# helpers

def sector_path(cx, cy, r_in, r_out, a0, a1):
    """Ring sector between angles a0..a1 (degrees, 0 = up, clockwise)."""
    path = QPainterPath()
    rect_out = QRectF(cx - r_out, cy - r_out, 2 * r_out, 2 * r_out)
    rect_in = QRectF(cx - r_in, cy - r_in, 2 * r_in, 2 * r_in)
    q0 = 90 - a0                       # Qt: 0 = 3 o'clock, counter-clockwise
    span = -(a1 - a0)
    path.arcMoveTo(rect_out, q0)
    path.arcTo(rect_out, q0, span)
    path.arcTo(rect_in, q0 + span, -span)
    path.closeSubpath()
    return path


def load_icon(spec, size):
    if not spec:
        return None
    if spec.startswith(("ph:", "ph-fill:")):
        spec = bundled(spec)
    icon = QIcon(spec) if os.path.isabs(spec) else QIcon.fromTheme(spec)
    if icon.isNull() and os.path.isabs(spec):
        for ext in (".png", ".svg", ".xpm"):
            if os.path.exists(spec + ext):
                icon = QIcon(spec + ext)
                break
    if icon.isNull():
        return None
    return icon.pixmap(size, size)


def tinted(spec, size, color):
    """Theme icon as a flat silhouette in one colour (symbolic variant first:
    a coloured icon would turn into a blob)."""
    pix = None
    if spec and not os.path.isabs(spec) and not spec.startswith("ph") \
            and not spec.endswith("-symbolic"):
        pix = load_icon(spec + "-symbolic", size)
    pix = pix or load_icon(spec, size)
    if pix is None:
        return None
    img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(img.rect(), color)
    p.end()
    return QPixmap.fromImage(img)


def color(spec, fallback=ACCENT):
    c = QColor(spec or fallback)
    return c if c.isValid() else QColor(fallback)


def font(px, weight=QFont.Weight.Normal):
    f = QFont()
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def anim(duration, curve, on_value, start=0.0, end=1.0):
    a = QVariantAnimation()
    a.setDuration(duration)
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.setEasingCurve(curve)
    a.valueChanged.connect(on_value)
    return a


# ---------------------------------------------------------------------------
# Quick-launch wheel

class Wheel(QWidget):
    def __init__(self, shell=None):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.shell = shell
        self.handle = None
        self.items = []
        self.icons = []
        self.sel = None
        self.accent = QColor(ACCENT)
        self.emit = lambda obj: None
        self.t_open = 1.0                     # 0..1 open animation
        self.hl = None                        # highlighted angle (animated)
        self.hl_from = self.hl_to = 0.0
        self.pop = {}                         # item -> 0..1 selection pop
        self.open_anim = anim(220, QEasingCurve.Type.OutCubic, self._set_open)
        self.hl_anim = anim(110, QEasingCurve.Type.OutCubic, self._set_hl)
        self.pop_timer = QTimer(self, interval=16, timeout=self._step_pop)
        self.closing = False
        self.close_anim = anim(130, QEasingCurve.Type.InCubic, self._set_open, 1.0, 0.0)
        self.close_anim.finished.connect(self._really_hide)
        self.launching = False                # confirm animation running
        self.t_confirm = 0.0
        self.confirm_anim = anim(CONFIRM_MS, QEasingCurve.Type.Linear, self._set_confirm)
        self.confirm_anim.finished.connect(self._really_hide)
        if shell and shell.ok:
            self.handle = shell.setup(self, LayerShell.TOP | LayerShell.BOTTOM
                                      | LayerShell.LEFT | LayerShell.RIGHT,
                                      LayerShell.KBD_EXCLUSIVE)

    # -- protocol -------------------------------------------------------------
    def show_items(self, items, sel, accent=None):
        self.close_anim.stop()
        self.confirm_anim.stop()
        self.closing = self.launching = False
        self.t_confirm = 0.0
        self.items = items
        self.icons = [load_icon(it.get("icon"), 96) for it in items]
        self.accent = color(accent)
        self.sel = None
        self.hl = None
        self.pop = {}
        if self.handle:
            self.show()
        else:
            self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.open_anim.stop()
        self.open_anim.start()
        self.select(sel)

    def select(self, i):
        if i == self.sel or (i is not None and not 0 <= i < len(self.items)):
            return
        self.sel = i
        if i is not None:
            target = i * 360.0 / max(1, len(self.items))
            if self.hl is None:
                self.hl = target
            else:
                d = (target - self.hl + 540) % 360 - 180          # shortest way round
                self.hl_from, self.hl_to = self.hl, self.hl + d
                self.hl_anim.stop()
                self.hl_anim.start()
            self.pop[i] = self.pop.get(i, 0.0)
            self.pop_timer.start()
        self.update()

    def close_animated(self):
        if not self.isVisible() or self.closing:
            return
        self.closing = True
        self.open_anim.stop()
        self.close_anim.setStartValue(self.t_open)
        self.close_anim.start()

    def confirm(self, i):
        """Launch picked: flash the sector, ripple out, then fade away."""
        if not self.isVisible() or self.closing or not self.items:
            return
        if i is not None and 0 <= i < len(self.items):
            self.sel = i
            self.hl = i * 360.0 / len(self.items)      # no glide: it is the pick
            self.hl_anim.stop()
            self.pop[i] = 1.0
        self.closing = self.launching = True
        self.open_anim.stop()
        self.t_open = 1.0
        self.confirm_anim.start()

    def _really_hide(self):
        self.closing = self.launching = False
        self.t_confirm = 0.0
        self.hide()

    # -- animation ------------------------------------------------------------
    def _set_open(self, v):
        self.t_open = v
        self.update()

    def _set_confirm(self, v):
        self.t_confirm = v
        self.update()

    def _set_hl(self, v):
        self.hl = self.hl_from + (self.hl_to - self.hl_from) * v
        self.update()

    def _step_pop(self):
        busy = False
        for i in list(self.pop):
            goal = 1.0 if i == self.sel else 0.0
            v = self.pop[i] + (goal - self.pop[i]) * 0.3
            if abs(v - goal) < 0.01:
                v = goal
            else:
                busy = True
            self.pop[i] = v
            if v == 0.0 and goal == 0.0:
                del self.pop[i]
        if not busy:
            self.pop_timer.stop()
        self.update()

    # -- geometry / input -----------------------------------------------------
    def geometry_info(self):
        cx, cy = self.width() / 2, self.height() / 2
        r_out = min(self.width(), self.height()) * 0.36
        return cx, cy, r_out * 0.36, r_out

    def sector_at(self, pos):
        n = len(self.items)
        cx, cy, r_in, r_out = self.geometry_info()
        dx, dy = pos.x() - cx, pos.y() - cy
        r = math.hypot(dx, dy)
        if not n or r < r_in or r > r_out * 1.25:
            return None
        angle = math.degrees(math.atan2(dx, -dy)) % 360
        step = 360.0 / n
        return int(((angle + step / 2) % 360) // step)

    def mouseMoveEvent(self, ev):
        if self.closing:
            return
        i = self.sector_at(ev.position())
        if i is not None and i != self.sel:
            self.select(i)
            self.emit({"event": "select", "i": i})

    def mousePressEvent(self, ev):
        if self.closing:
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            i = self.sector_at(ev.position())
            if i is not None:
                self.emit({"event": "launch", "i": i})
            else:
                self.emit({"event": "cancel"})
        elif ev.button() == Qt.MouseButton.RightButton:
            self.emit({"event": "cancel"})

    def keyPressEvent(self, ev):
        if self.closing:
            return
        k = ev.key()
        n = len(self.items)
        if k == Qt.Key.Key_Escape:
            self.emit({"event": "cancel"})
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.sel is not None:
            self.emit({"event": "launch", "i": self.sel})
        elif n and k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab,
                         Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            d = 1 if k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab) else -1
            i = 0 if self.sel is None else (self.sel + d) % n
            self.select(i)
            self.emit({"event": "select", "i": i})

    # -- painting -------------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # launch confirmation: flash (f), pulse (bump), then exit (e)
        c = self.t_confirm if self.launching else 0.0
        f = 1 - (1 - min(1.0, c / 0.28)) ** 3
        bump = math.sin(math.pi * min(1.0, c / 0.42)) if self.launching else 0.0
        x = max(0.0, min(1.0, (c - 0.5) / 0.5))
        e = x * x * (3 - 2 * x)
        t = self.t_open * (1 - e)
        p.fillRect(self.rect(), QColor(8, 7, 9, int(160 * t)))
        n = len(self.items)
        if not n:
            return
        cx, cy, r_in, r_out = self.geometry_info()
        p.translate(cx, cy)
        s = (0.9 + 0.1 * self.t_open) * (1 + 0.06 * e)
        p.scale(s, s)
        p.translate(-cx, -cy)
        p.setOpacity(t)
        acc = self.accent

        # soft glow behind the ring
        glow = QRadialGradient(QPointF(cx, cy), r_out * 1.35)
        g = QColor(acc)
        g.setAlpha(38)
        glow.setColorAt(0.55, g)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), r_out * 1.35, r_out * 1.35)

        # ring base
        base = QRadialGradient(QPointF(cx, cy), r_out)
        base.setColorAt(0.3, QColor(36, 35, 40, 245))
        base.setColorAt(1.0, QColor(24, 23, 27, 242))
        ring = QPainterPath()
        ring.addEllipse(QPointF(cx, cy), r_out, r_out)
        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), r_in, r_in)
        p.setBrush(base)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1.5))
        p.drawPath(ring.subtracted(hole))

        step = 360.0 / n
        # highlight (glides between sectors)
        if self.hl is not None and self.sel is not None:
            a0, a1 = self.hl - step / 2 + 1.5, self.hl + step / 2 - 1.5
            path = sector_path(cx, cy, r_in + 6, r_out - 6 + 10 * bump, a0, a1)
            mid = math.radians(self.hl)
            gx, gy = cx + r_out * math.sin(mid), cy - r_out * math.cos(mid)
            grad = QLinearGradient(QPointF(cx, cy), QPointF(gx, gy))
            c0 = QColor(acc)
            c0.setAlpha(90)
            c1 = QColor(acc)
            c1.setAlpha(230)
            grad.setColorAt(0, c0)
            grad.setColorAt(1, c1)
            p.setBrush(grad)
            p.setPen(QPen(acc.lighter(150), 2))
            p.drawPath(path)
            if self.launching:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), int(200 * f)))
                p.drawPath(path)                                # fills solid
                p.setBrush(QColor(255, 255, 255, int(90 * bump)))
                p.drawPath(path)                                # white flash
                rp = min(1.0, c / 0.7)
                grow = 1 - (1 - rp) ** 2
                ripple = sector_path(cx, cy, r_in + 6, r_out - 6 + r_out * 0.32 * grow,
                                     a0 - 5 * grow, a1 + 5 * grow)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), int(220 * (1 - rp))),
                              1 + 3 * (1 - rp)))
                p.drawPath(ripple)

        # separators
        p.setPen(QPen(QColor(255, 255, 255, 18), 1.2))
        for i in range(n):
            a = math.radians(i * step + step / 2)
            p.drawLine(QPointF(cx + r_in * math.sin(a), cy - r_in * math.cos(a)),
                       QPointF(cx + r_out * math.sin(a), cy - r_out * math.cos(a)))

        r_mid = (r_in + r_out) / 2
        for i, item in enumerate(self.items):
            k = self.pop.get(i, 0.0)
            picked = self.launching and i == self.sel
            dim = 1.0 if picked or not self.launching else 1 - 0.7 * f
            mid = math.radians(i * step)
            ix = cx + r_mid * math.sin(mid)
            iy = cy - r_mid * math.cos(mid)
            size = (r_out - r_in) * (0.40 + 0.10 * k) * (1 + (0.22 * bump if picked else 0))
            pix = self.icons[i]
            if pix:
                p.setOpacity(t * dim * (0.75 + 0.25 * k))
                p.drawPixmap(QRectF(ix - size / 2, iy - size / 2 - 12, size, size), pix,
                             QRectF(pix.rect()))
            else:
                p.setOpacity(t * dim)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(acc))
                p.drawEllipse(QPointF(ix, iy - 12), size / 2.4, size / 2.4)
                p.setPen(QColor(255, 255, 255))
                p.setFont(font(size / 2.2, QFont.Weight.Bold))
                p.drawText(QRectF(ix - size / 2, iy - 12 - size / 2, size, size),
                           Qt.AlignmentFlag.AlignCenter, item.get("name", "?")[:1].upper())
            p.setOpacity(t * dim)
            p.setPen(QColor(255, 255, 255, 170 + int(85 * k)))
            p.setFont(font(15 + 2 * k, QFont.Weight.DemiBold if k > 0.5 else QFont.Weight.Normal))
            p.drawText(QRectF(ix - 120, iy + size / 2 - 6, 240, 28),
                       Qt.AlignmentFlag.AlignCenter, item.get("name", ""))

        # centre
        p.setOpacity(t)
        p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 170), 2))
        hub = QRadialGradient(QPointF(cx, cy), r_in)
        hub.setColorAt(0, QColor(40, 39, 44, 250))
        hub.setColorAt(1, QColor(22, 21, 25, 250))
        p.setBrush(hub)
        p.drawEllipse(QPointF(cx, cy), r_in - 12, r_in - 12)
        label = self.items[self.sel]["name"] if self.sel is not None else _("Выберите")
        p.setPen(QColor(255, 255, 255))
        p.setFont(font(min(26, r_in * 0.2), QFont.Weight.Bold))
        p.drawText(QRectF(cx - r_in + 18, cy - 44, 2 * r_in - 36, 52),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, label)
        if self.launching:
            self._paint_check(p, cx, cy + 30, min(19, r_in * 0.15), c, f, acc)
            return
        p.setPen(QColor(170, 166, 174))
        p.setFont(font(min(14, r_in * 0.11)))
        p.drawText(QRectF(cx - r_in, cy + 10, 2 * r_in, 44), Qt.AlignmentFlag.AlignCenter,
                   _("любой стик · ✕ / L3 / R3 — запуск\n○ — закрыть"))

    def _paint_check(self, p, x, y, r, c, f, acc):
        """Accent disc with a check mark that draws itself, and \"Launch\"."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc)
        rr = r * (0.6 + 0.4 * f)
        p.drawEllipse(QPointF(x, y), rr, rr)
        pts = [QPointF(x - r * 0.45, y + r * 0.02), QPointF(x - r * 0.1, y + r * 0.36),
               QPointF(x + r * 0.5, y - r * 0.32)]
        k = max(0.0, min(1.0, (c - 0.08) / 0.3))         # stroke progress
        path = QPainterPath(pts[0])
        if k < 0.4:
            a = k / 0.4
            path.lineTo(pts[0] + (pts[1] - pts[0]) * a)
        else:
            a = (k - 0.4) / 0.6
            path.lineTo(pts[1])
            path.lineTo(pts[1] + (pts[2] - pts[1]) * a)
        pen = QPen(QColor(255, 255, 255), max(2.0, r * 0.2))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if k > 0:
            p.drawPath(path)
        p.setPen(QColor(170, 166, 174))
        p.setFont(font(r * 0.95, QFont.Weight.DemiBold))
        p.drawText(QRectF(x - 120, y + r + 4, 240, r * 2), Qt.AlignmentFlag.AlignCenter,
                   _("Запуск"))


# ---------------------------------------------------------------------------
# Toasts and the hold ring

class Toast(QWidget):
    W, H = 460, 96
    MARGIN_TOP = 36

    def __init__(self, shell=None):
        super().__init__()
        self.setWindowTitle("couchpad-osd")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.handle = None
        if shell and shell.ok:
            self.handle = shell.setup(self, LayerShell.TOP, LayerShell.KBD_NONE,
                                      (0, self.MARGIN_TOP, 0, 0))
        self.msg = {}
        self.icon = None
        self.accent = QColor(ACCENT)
        self.t = 0.0                    # appear 0..1
        self.bump = 0.0                 # content refresh pulse
        self.ring = None                # hold: progress 0..1 (None = toast)
        self.ring_done = False
        self.appear = anim(240, QEasingCurve.Type.OutCubic, self._set_t)
        self.vanish = anim(260, QEasingCurve.Type.InCubic, self._set_t, 1.0, 0.0)
        self.vanish.finished.connect(self.hide)
        self.bump_anim = anim(320, QEasingCurve.Type.OutCubic, self._set_bump, 1.0, 0.0)
        self.ring_anim = anim(1000, QEasingCurve.Type.Linear, self._set_ring)
        self.ring_anim.finished.connect(self._ring_full)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.fade_out)
        self.delay = QTimer(self, singleShot=True, timeout=self._show_now)

    # -- protocol -------------------------------------------------------------
    def toast(self, msg):
        self.delay.stop()
        self.ring_anim.stop()
        self.ring = None
        self._set_content(msg)
        timeout = msg.get("timeout") or (2600 if msg.get("body") else 1800)
        self.hide_timer.start(int(timeout))

    def hold(self, msg):
        """Progress ring for a Share + ○/△ hold. Shown after a short delay so
        quick presses (the window switcher) don't flash it."""
        self.hide_timer.stop()
        self.ring_anim.stop()
        self.ring = 0.0
        self.ring_done = False
        self.pending = msg
        duration = max(0.3, float(msg.get("duration") or 1.5))
        lead = min(0.2, duration * 0.2)
        self.ring_anim.setDuration(int(duration * 1000))
        self.ring_anim.setStartValue(0.0)
        self.ring_anim.setEndValue(1.0)
        self.ring_anim.start()
        self.delay.start(int(lead * 1000))

    def _show_now(self):
        if self.ring is not None:
            self._set_content(self.pending)

    def hold_end(self, done):
        self.delay.stop()
        if self.ring is None:
            return
        if done:
            self.ring_anim.stop()
            self.ring = 1.0
            self.ring_done = True
            self.update()
            self.hide_timer.start(650)
        else:
            self.ring_anim.stop()
            self.ring = None
            if self.isVisible():
                self.fade_out()

    def _ring_full(self):
        self.update()

    def _set_content(self, msg):
        self.msg = msg
        self.accent = color(msg.get("accent"))
        self.icon = (tinted(msg.get("icon") or "ph:game-controller", 30, QColor(255, 255, 255))
                     or tinted("ph:game-controller", 30, QColor(255, 255, 255)))
        if self.isVisible() and not self.vanish.state() == QVariantAnimation.State.Running:
            self.bump_anim.stop()
            self.bump_anim.start()
            self.update()
            return
        self.vanish.stop()
        self.show()
        self.raise_()
        self.appear.setStartValue(self.t)
        self.appear.start()

    def fade_out(self):
        self.appear.stop()
        self.vanish.setStartValue(self.t)
        self.vanish.start()

    def _set_t(self, v):
        self.t = v
        self.update()

    def _set_bump(self, v):
        self.bump = v
        self.update()

    def _set_ring(self, v):
        if self.ring is not None and not self.ring_done:
            self.ring = v
            self.update()

    # -- painting -------------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = self.t
        p.setOpacity(t)
        p.translate(0, -14 * (1 - t))
        acc = self.accent
        card = QRectF(8, 6, self.W - 16, self.H - 16)
        path = QPainterPath()
        path.addRoundedRect(card, card.height() / 2, card.height() / 2)
        # shadow
        for i, a in ((6, 18), (3, 30)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(card.adjusted(-i, -i + 3, i, i + 3), card.height() / 2 + i,
                              card.height() / 2 + i)
        bg = QLinearGradient(card.topLeft(), card.bottomLeft())
        bg.setColorAt(0, QColor(38, 37, 42, 246))
        bg.setColorAt(1, QColor(26, 25, 29, 246))
        p.setBrush(bg)
        edge = QColor(255, 255, 255, 18)
        edge.setAlpha(int(18 + 120 * self.bump))
        p.setPen(QPen(edge, 1.4))
        p.drawPath(path)

        # icon disc
        r = (card.height() - 24) / 2
        c = QPointF(card.left() + 12 + r, card.center().y())
        disc = QRadialGradient(c - QPointF(r * 0.4, r * 0.5), r * 2)
        disc.setColorAt(0, acc.lighter(135))
        disc.setColorAt(1, acc.darker(130))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(disc)
        p.drawEllipse(c, r, r)
        if self.ring is not None:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 40), 4))
            rr = r + 5
            p.drawEllipse(c, rr, rr)
            pen = QPen(QColor(255, 255, 255) if self.ring_done else acc.lighter(160), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), 90 * 16,
                      int(-self.ring * 360 * 16))
        if self.ring_done:
            pen = QPen(QColor(255, 255, 255), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            tick = QPainterPath(c + QPointF(-r * 0.38, 0))
            tick.lineTo(c + QPointF(-r * 0.08, r * 0.3))
            tick.lineTo(c + QPointF(r * 0.42, -r * 0.32))
            p.drawPath(tick)
        elif self.icon:
            s = 30
            p.drawPixmap(QRectF(c.x() - s / 2, c.y() - s / 2, s, s), self.icon,
                         QRectF(self.icon.rect()))

        # text
        x = c.x() + r + 16
        w = card.right() - 26 - x
        title = self.msg.get("title", "")
        body = self.msg.get("body", "")
        progress = self.msg.get("progress")
        p.setPen(QColor(255, 255, 255))
        p.setFont(font(19, QFont.Weight.DemiBold))
        ty = card.top() + (16 if (body or progress is not None) else card.height() / 2 - 14)
        p.drawText(QRectF(x, ty, w, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(w)))
        if progress is not None:
            bar = QRectF(x, ty + 36, w, 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(bar, 4, 4)
            k = min(max(float(progress), 0.0), 100.0) / 100.0
            fill = QRectF(bar.left(), bar.top(), max(8.0, bar.width() * k), bar.height())
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            grad.setColorAt(0, acc.darker(110))
            grad.setColorAt(1, acc.lighter(140))
            p.setBrush(grad)
            p.drawRoundedRect(fill, 4, 4)
            if body:
                p.setPen(QColor(190, 186, 194))
                p.setFont(font(13))
                p.drawText(QRectF(x, ty - 2, w, 28),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, body)
        elif body:
            p.setPen(QColor(190, 186, 194))
            p.setFont(font(14))
            p.drawText(QRectF(x, ty + 28, w, 24),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(body, Qt.TextElideMode.ElideRight, int(w)))


# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv[:1])
    app.setApplicationName("couchpad-overlay")
    app.setDesktopFileName("couchpad-wheel")
    app.setQuitOnLastWindowClosed(False)
    ensure_icon_theme()
    fonts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fonts")
    if QFontDatabase.addApplicationFont(os.path.join(fonts, "Inter.ttf")) >= 0:
        app.setFont(QFont("Inter"))
    shell = LayerShell()
    wheel = Wheel(shell)
    toast = Toast(shell)
    buf = b""

    def emit(obj):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()
    wheel.emit = emit

    def handle(msg):
        cmd = msg.get("cmd")
        if msg.get("lang"):
            set_lang(msg["lang"])
        if cmd == "show":
            wheel.show_items(msg.get("items", []), msg.get("sel"), msg.get("accent"))

            def shown():
                scr = (wheel.screen() or app.primaryScreen()).geometry()
                emit({"event": "shown",
                      "geo": [scr.x(), scr.y(), wheel.width(), wheel.height()]})
            QTimer.singleShot(60, shown)          # after the compositor sized it
        elif cmd == "select":
            wheel.select(msg.get("i"))
        elif cmd == "hide":
            if msg.get("launch") is not None:
                wheel.confirm(msg["launch"])
            else:
                wheel.close_animated()
            emit({"event": "hidden"})
        elif cmd == "osd":
            toast.toast(msg)
        elif cmd == "hold":
            toast.hold(msg)
        elif cmd == "hold_end":
            toast.hold_end(bool(msg.get("done")))
        elif cmd == "quit":
            app.quit()

    def readable():
        nonlocal buf
        data = os.read(sys.stdin.fileno(), 65536)
        if not data:
            app.quit()
            return
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            handle(msg)

    notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(readable)
    emit({"event": "ready", "osd": shell.ok})
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
