"""Couchpad control center: `couchpad app [--tray]`."""

import os
import signal
import sys

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..qticons import ensure_icon_theme
from .backend import Backend
from .gamepad import Gamepad
from ..i18n import _

HERE = os.path.dirname(os.path.abspath(__file__))
QML = os.path.join(HERE, "qml", "Main.qml")
ICON = os.path.join(os.path.dirname(HERE), "data", "couchpad.svg")
FONTS = os.path.join(os.path.dirname(HERE), "data", "fonts")
ICONS = os.path.join(os.path.dirname(HERE), "data", "icons")
SOCKET = f"couchpad-app-{os.getuid()}"


class IconProvider(QQuickImageProvider):
    """image://icon/<theme name or path>[?<#rrggbb tint>]"""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, ident, size, requested):
        name, _sep, tint = ident.partition("?")
        side = max(requested.width(), requested.height(), 16)
        if name.startswith(("ph:", "ph-fill:")):        # bundled Phosphor icons
            kind, _sep, base = name.partition(":")
            path = os.path.join(ICONS, base + ("-fill" if kind == "ph-fill" else "") + ".svg")
            pix = QIcon(path).pixmap(QSize(side, side))
            if pix.isNull():
                pix = QPixmap(side, side)
                pix.fill(Qt.GlobalColor.transparent)
            return self._tint(pix, tint or "#f3f1ee", size)
        if name == "couchpad":
            icon = QIcon(ICON)
        elif os.path.isabs(name):
            icon = QIcon(name)
        else:
            icon = QIcon.fromTheme(name)
        if tint and not os.path.isabs(name) and not name.endswith("-symbolic"):
            sym = QIcon.fromTheme(name + "-symbolic")      # flat glyph tints cleanly
            if not sym.isNull():
                icon = sym
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-executable")
        pix = icon.pixmap(QSize(side, side))
        if pix.isNull():                       # unknown icon: blank, not an error
            pix = QPixmap(side, side)
            pix.fill(Qt.GlobalColor.transparent)
        return self._tint(pix, tint, size)

    @staticmethod
    def _tint(pix, tint, size):
        if tint and not pix.isNull():
            img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(img.rect(), QColor(tint))
            p.end()
            pix = QPixmap.fromImage(img)
        if size is not None:
            size.setWidth(pix.width())
            size.setHeight(pix.height())
        return pix


class App(QObject):
    def __init__(self, tray_only):
        super().__init__()
        ensure_icon_theme()
        load_font(QApplication.instance())
        self.backend = Backend()
        self.gamepad = Gamepad()
        self.engine = QQmlApplicationEngine()
        self.engine.addImageProvider("icon", IconProvider())
        ctx = self.engine.rootContext()
        ctx.setContextProperty("backend", self.backend)
        ctx.setContextProperty("gamepad", self.gamepad)
        ctx.setContextProperty("app", self)
        self.window = None
        self.tray = None
        self.quitting = False
        self.server = QLocalServer(self)
        QLocalServer.removeServer(SOCKET)
        self.server.listen(SOCKET)
        self.server.newConnection.connect(self._on_connection)
        self.backend.statusChanged.connect(self._update_tray)
        self.backend.settingsChanged.connect(self._sync_tray)
        self.backend.langChanged.connect(self._retranslate_tray)
        self._sync_tray()
        if not tray_only or self.tray is None:
            self.show()

    # -- window -------------------------------------------------------------------
    def _load(self):
        self.engine.warnings.connect(
            lambda ws: [print("qml:", w.toString(), file=sys.stderr) for w in ws])
        self.engine.load(QUrl.fromLocalFile(QML))
        roots = self.engine.rootObjects()
        if not roots:
            raise SystemExit("couchpad: QML failed to load")
        self.window = roots[0]

    @Slot()
    def show(self):
        if self.window is None:
            self._load()
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    @Slot(int)
    def sendKey(self, key):
        """Gamepad -> key press for popups and lists."""
        if self.window is None:
            return
        target = self.window.activeFocusItem() or self.window
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier))

    @Slot()
    def quit(self):
        self.quitting = True
        self.backend.shutdown()
        self.gamepad.shutdown()
        QApplication.quit()

    def _on_connection(self):
        """Another `couchpad app` started: it sends "show" or "quit"."""
        sock = self.server.nextPendingConnection()
        if not sock:
            return
        sock.waitForReadyRead(300)
        msg = bytes(sock.readAll()).decode(errors="replace").strip()
        sock.disconnectFromServer()
        if msg == "quit":
            self.quit()
        elif msg != "tray":
            self.show()

    # -- tray -----------------------------------------------------------------------
    def _sync_tray(self):
        want = self.backend.cfg.tray and QSystemTrayIcon.isSystemTrayAvailable()
        if want and self.tray is None:
            self.tray = QSystemTrayIcon(QIcon(ICON), self)
            menu = QMenu()
            self.act_open = menu.addAction(QIcon.fromTheme("configure"), _("Открыть Couchpad"))
            self.act_open.triggered.connect(self.show)
            self.act_mouse = menu.addAction(QIcon.fromTheme("input-touchpad"),
                                            _("Мышь с тачпада"))
            self.act_mouse.setCheckable(True)
            self.act_mouse.triggered.connect(lambda on: self.backend.setMouse(on))
            menu.addSeparator()
            self.act_quit = menu.addAction(QIcon.fromTheme("application-exit"), _("Выход"))
            self.act_quit.triggered.connect(self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_click)
            self.tray.show()
            self._update_tray()
        elif not want and self.tray is not None:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None
            if self.window is None or not self.window.isVisible():
                self.quit()

    def _retranslate_tray(self):
        if self.tray is not None:
            self.act_open.setText(_("Открыть Couchpad"))
            self.act_mouse.setText(_("Мышь с тачпада"))
            self.act_quit.setText(_("Выход"))
            self._update_tray()

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window is not None and self.window.isVisible() and self.window.isActive():
                self.window.hide()
            else:
                self.show()

    def _update_tray(self):
        if self.tray is None:
            return
        pad = self.backend.pad
        if not self.backend.daemonRunning:
            tip = _("Couchpad: служба не запущена")
        elif not pad:
            tip = _("Couchpad: геймпад не подключён")
        else:
            bat = pad.get("battery")
            tip = "DualSense · " + (f"{bat}%" if bat is not None else _("заряд неизвестен"))
        self.tray.setToolTip(tip)
        self.tray.setIcon(tray_icon(pad.get("battery") if pad else None,
                                    pad.get("battery_status") == "Charging" if pad else False,
                                    self.backend.mouse, self.backend.daemonRunning and bool(pad)))
        self.act_mouse.setChecked(self.backend.mouse)
        self.act_mouse.setEnabled(self.backend.daemonRunning)


def tray_icon(level, charging, mouse, connected):
    """App icon with a battery bar along the bottom and a dot for mouse mode."""
    size = 64
    pix = QIcon(ICON).pixmap(size, size)
    img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not connected:
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.fillRect(img.rect(), QColor(0, 0, 0, 110))          # faded when idle
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    elif level is not None:
        col = QColor("#2ecc71") if charging or level > 30 else \
            QColor("#f5b400") if level > 15 else QColor("#ff4d5e")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 12, 18, 230))
        p.drawRoundedRect(6, 50, 52, 12, 6, 6)
        p.setBrush(col)
        p.drawRoundedRect(8, 52, max(4, int(48 * level / 100)), 8, 4, 4)
    if connected and mouse:
        p.setPen(QColor(10, 12, 18))
        p.setBrush(QColor("#ff6a1f"))
        p.drawEllipse(44, 2, 18, 18)
    p.end()
    return QIcon(QPixmap.fromImage(img))


def load_font(app):
    """Inter for the UI, JetBrains Mono for numbers and codes (both OFL,
    bundled, both with Cyrillic)."""
    QFontDatabase.addApplicationFont(os.path.join(FONTS, "JetBrainsMono.ttf"))
    if QFontDatabase.addApplicationFont(os.path.join(FONTS, "Inter.ttf")) >= 0:
        f = QFont("Inter")
        f.setPixelSize(15)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(f)


def tell_running(msg):
    """Hand `msg` to a running instance. False if there is none."""
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if not sock.waitForConnected(300):
        return False
    sock.write(msg.encode())
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def main(argv=()):
    """couchpad app [--tray | --quit]"""
    argv = list(argv)
    unknown = [a for a in argv if a not in ("--tray", "--quit")]
    if unknown:
        print("usage: couchpad app [--tray | --quit]", file=sys.stderr)
        return 2
    tray_only = "--tray" in argv
    if "--quit" in argv:
        return quit_running()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Couchpad")
    app.setOrganizationName("couchpad")
    app.setDesktopFileName("couchpad")
    app.setWindowIcon(QIcon(ICON))
    load_font(app)
    ensure_icon_theme()
    # A second launch raises the running window; a --tray launch (login,
    # installer) leaves a running instance alone.
    if tell_running("tray" if tray_only else "show"):
        return 0
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    ctl = App(tray_only)
    # SIGTERM (logout, installer) quits through Qt so pending saves flush.
    signal.signal(signal.SIGTERM, lambda *a: QTimer.singleShot(0, ctl.quit))
    wake = QTimer(interval=500)          # lets Python run signal handlers
    wake.timeout.connect(lambda: None)
    wake.start()
    app.aboutToQuit.connect(ctl.backend.shutdown)
    if ctl.tray is None:
        app.setQuitOnLastWindowClosed(True)
    return app.exec()


def quit_running(timeout=5.0):
    """Ask a running control center to quit and wait until it has."""
    import time
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    if not tell_running("quit"):
        return 0
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        sock = QLocalSocket()
        sock.connectToServer(SOCKET)
        if not sock.waitForConnected(100):
            return 0
        sock.abort()
        time.sleep(0.1)
    return 1
