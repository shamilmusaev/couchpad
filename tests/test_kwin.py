"""Live KWin checks on a throw-away window (never the user's own windows)."""

import os
import subprocess
import time
import unittest

from couchpad import procs, system


def kwin_up():
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        return bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                             "org.freedesktop.DBus", "NameHasOwner",
                             GLib.Variant("(s)", ("org.kde.KWin",)),
                             None, 0, 1000, None).unpack()[0]
    except Exception:
        return False


BY_PID_JS = """
var found = null;
var list = workspace.windowList();
for (var i = 0; i < list.length; i++) {
  if (list[i].pid == %d) { found = list[i]; break; }
}
%s
"""


@unittest.skipUnless(kwin_up() and os.environ.get("WAYLAND_DISPLAY"), "no KWin session")
class KWinLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bus = system.Bus(name=f"org.couchpad.Test{os.getpid()}")
        assert cls.bus.has_owner

    @classmethod
    def tearDownClass(cls):
        cls.bus.close()

    def spawn_window(self):
        p = subprocess.Popen(["kdialog", "--title", "couchpad-test-window",
                              "--msgbox", "couchpad test window"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        for _ in range(100):
            info = self.by_pid(p.pid, "report(found ? {pid: found.pid} : {none: true});")
            if info and not info.get("none"):
                return p
            time.sleep(0.05)
        self.fail("test window never appeared")

    def by_pid(self, pid, body):
        return self.bus.kwin_eval(BY_PID_JS % (pid, body))

    def test_active_window_query_shape(self):
        info = self.bus.kwin_eval(system.ACTIVE_WINDOW_JS)
        self.assertIsNotNone(info, "KWin script did not reply")
        self.assertNotIn("error", info)
        if not info.get("none"):
            for key in ("pid", "cls", "caption", "id", "special", "minimized"):
                self.assertIn(key, info)

    def test_minimize_api(self):
        p = self.spawn_window()
        js = ("if (!found || !found.minimizable) report({ok: false}); else {"
              " found.minimized = true; report({ok: true, min: found.minimized,"
              " id: String(found.internalId)}); }")
        res = self.by_pid(p.pid, js)
        self.assertEqual(res.get("ok"), True, res)
        self.assertTrue(res["min"])
        self.assertTrue(res["id"].startswith("{"), res["id"])
        state = self.by_pid(p.pid, "report({min: found.minimized});")
        self.assertTrue(state["min"])

    def test_force_close_window_process(self):
        p = self.spawn_window()
        target = procs.find_target(procs.read_table(), p.pid)
        self.assertEqual(target[:2], (p.pid, "process"))
        procs.kill_tree(*target[:2])
        self.assertIsNotNone(p.wait(timeout=5))
        for _ in range(40):
            info = self.by_pid(p.pid, "report({gone: !found});")
            if info and info["gone"]:
                break
            time.sleep(0.05)
        self.assertTrue(info["gone"])

    def test_script_errors_are_reported_not_hung(self):
        t = time.time()
        res = self.bus.kwin_eval("undefinedFunctionXYZ();")
        self.assertIn("error", res)
        self.assertLess(time.time() - t, 1.0)

    def test_script_files_cleaned_up(self):
        rundir = os.path.join(os.environ["XDG_RUNTIME_DIR"], "couchpad")
        before = set(os.listdir(rundir)) if os.path.isdir(rundir) else set()
        for _ in range(5):
            self.assertEqual(self.bus.kwin_eval("report({x: 1});"), {"x": 1})
        self.assertEqual(set(os.listdir(rundir)) - before, set())

    def test_stale_scripts_removed(self):
        rundir = os.path.join(os.environ["XDG_RUNTIME_DIR"], "couchpad")
        os.makedirs(rundir, exist_ok=True)
        old = os.path.join(rundir, "kwin-stale-test.js")
        with open(old, "w") as f:
            f.write("//")
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        system.Bus._clean_stale_scripts()
        self.assertFalse(os.path.exists(old))

    def test_daemon_name_not_stolen(self):
        # A second bridge must not take over a running daemon's bus name.
        self.assertNotEqual(self.bus.name, system.BUS_NAME)


if __name__ == "__main__":
    unittest.main()
