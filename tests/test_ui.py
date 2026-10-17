"""Control center + overlay, offscreen: QML loads cleanly on every page,
settings edits persist, overlay protocol behaves."""

import os
import tempfile
import unittest

from PySide6.QtCore import QEventLoop, QTimer

from couchpad import config
from fakes import qt_app as app


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class Sandbox(unittest.TestCase):
    def setUp(self):
        app()
        from couchpad.app import backend
        self.backend_mod = backend
        self.dir = tempfile.mkdtemp()
        old = (config.CONFIG_PATH, backend.AUTOSTART, backend.daemon_call)

        def restore():
            config.CONFIG_PATH, backend.AUTOSTART, backend.daemon_call = old
        # Registered first, so it runs after every other cleanup (Backend
        # shutdowns flush pending saves - they must still go to the sandbox).
        self.addCleanup(restore)
        config.CONFIG_PATH = os.path.join(self.dir, "config.toml")
        backend.AUTOSTART = os.path.join(self.dir, "autostart.desktop")
        backend.daemon_call = lambda cmd, timeout=0: None      # never touch a real daemon


class BackendTests(Sandbox):
    def test_set_saves_and_validates(self):
        b = self.backend_mod.Backend()
        self.addCleanup(b.shutdown)
        b.set("pointer_speed", 1.7)
        b.set("light_mode", "disco")             # invalid -> default
        b.set("nonexistent", 1)
        b.set("wheel", "x")                      # protected
        b._save()
        cfg = config.load()
        self.assertEqual(cfg.pointer_speed, 1.7)
        self.assertEqual(cfg.light_mode, "static")

    def test_tray_autostart_file(self):
        b = self.backend_mod.Backend()
        self.addCleanup(b.shutdown)
        b.set("tray", True)
        b._save()
        self.assertTrue(os.path.exists(self.backend_mod.AUTOSTART))
        b.set("tray", False)
        b._save()
        self.assertFalse(os.path.exists(self.backend_mod.AUTOSTART))

    def test_chords(self):
        b = self.backend_mod.Backend()
        self.addCleanup(b.shutdown)
        b.setChord("square", "mute")
        b.setChord("circle", "mute")             # fixed: ignored
        b.setChord("l1", "battery")              # default: not stored
        self.assertEqual(b.cfg.chords, {"square": "mute"})
        rows = {r["button"]: r for r in b.chords}
        self.assertTrue(rows["square"]["custom"])
        self.assertTrue(rows["circle"]["fixed"])
        b.resetChords()
        self.assertEqual(b.cfg.chords, {})

    def test_wheel_editing(self):
        b = self.backend_mod.Backend()
        self.addCleanup(b.shutdown)
        n = len(b.wheelItems)
        self.assertTrue(b.wheelIsDefault)
        b.wheelAddCustom("YouTube", "https://youtube.com/tv", "")
        self.assertFalse(b.wheelIsDefault)
        items = b.wheelItems
        self.assertEqual(len(items), n + 1)
        self.assertEqual(items[-1]["kind"], "open")
        b.wheelMove(len(items) - 1, -1)
        self.assertEqual(b.wheelItems[-2]["name"], "YouTube")
        b.wheelRemove(len(items) - 2)
        self.assertEqual(len(b.wheelItems), n)
        b.wheelAddCustom("x", "echo hi", "")
        self.assertEqual(b.cfg.wheel[-1], {"name": "x", "exec": "echo hi"})
        while len(b.wheelItems) < 8:
            b.wheelAddCustom("f", "true", "")
        got = []
        b.toast.connect(lambda *a: got.append(a))
        b.wheelAddCustom("over", "true", "")
        self.assertEqual(len(b.wheelItems), 8)
        self.assertTrue(got, "user is told the wheel is full")
        b.wheelReset()
        self.assertTrue(b.wheelIsDefault)

    def test_installed_apps(self):
        apps = self.backend_mod.installed_apps()
        if not apps:
            self.skipTest("no .desktop applications on this machine")
        self.assertTrue(all({"id", "name", "icon"} <= set(a) for a in apps))


class QmlTests(Sandbox):
    def test_every_page_loads_without_warnings(self):
        from couchpad.app import main as m
        warnings = []
        m.SOCKET = "couchpad-test-%d" % os.getpid()
        a = m.App(tray_only=True)
        a.engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        a.show()
        w = a.window
        for page in range(8):
            w.setProperty("page", page)
            spin(250)
            img = w.grabWindow()
            self.assertFalse(img.isNull())
        # gamepad navigation walks the focus chain and pages
        for d in ("right", "down", "down", "up", "left", "next", "prev", "menu", "back"):
            w.padNav(d)
            spin(20)
        a.gamepad.shutdown()
        a.backend.shutdown()
        w.close()
        self.assertEqual(warnings, [])


class OverlayTests(unittest.TestCase):
    def setUp(self):
        app()

    def test_toast_and_hold(self):
        from couchpad.overlay_ui import Toast
        t = Toast(shell=None)
        t.toast({"title": "Hello", "body": "world", "icon": "input-gaming", "progress": 50})
        self.assertTrue(t.isVisible())
        t.hold({"title": "Закрыть игру", "duration": 0.5})
        self.assertEqual(t.ring, 0.0)
        spin(300)
        self.assertGreater(t.ring, 0.2)
        t.hold_end(True)
        self.assertTrue(t.ring_done)
        spin(1100)
        self.assertFalse(t.isVisible(), "hides after completing")

    def test_hold_cancel_before_shown(self):
        from couchpad.overlay_ui import Toast
        t = Toast(shell=None)
        t.hold({"title": "x", "duration": 1.5})
        t.hold_end(False)
        spin(400)
        self.assertFalse(t.isVisible(), "quick press never flashes the ring")

    def test_wheel_keyboard(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        from couchpad.overlay_ui import Wheel
        w = Wheel(shell=None)
        got = []
        w.emit = got.append
        w.show_items([{"name": str(i)} for i in range(4)], None, "#ff0000")

        def key(k):
            w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))
        key(Qt.Key.Key_Right)
        key(Qt.Key.Key_Right)
        key(Qt.Key.Key_Left)
        key(Qt.Key.Key_Return)
        key(Qt.Key.Key_Escape)
        self.assertEqual(got, [{"event": "select", "i": 0}, {"event": "select", "i": 1},
                               {"event": "select", "i": 0}, {"event": "launch", "i": 0},
                               {"event": "cancel"}])
        w.close_animated()
        spin(300)
        self.assertFalse(w.isVisible())


class Cli(unittest.TestCase):
    def test_app_flags_reach_the_app(self):
        """`couchpad app --tray` must not be eaten by the daemon's argparse."""
        from couchpad import daemon
        from couchpad.app import main as m
        seen = []
        real = m.main
        m.main = lambda argv=(): seen.append(list(argv)) or 0
        try:
            self.assertEqual(daemon.main(["app", "--tray"]), 0)
            self.assertEqual(daemon.main(["app"]), 0)
        finally:
            m.main = real
        self.assertEqual(seen, [["--tray"], []])

    def test_unknown_app_flag(self):
        from couchpad.app import main as m
        self.assertEqual(m.main(["--bogus"]), 2)

    def test_quit_without_instance(self):
        app()
        from couchpad.app import main as m
        old = m.SOCKET
        m.SOCKET = "couchpad-test-none-%d" % os.getpid()
        try:
            self.assertEqual(m.quit_running(timeout=0.5), 0)
        finally:
            m.SOCKET = old


if __name__ == "__main__":
    unittest.main()
