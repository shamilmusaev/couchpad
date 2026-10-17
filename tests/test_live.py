"""Live acceptance test against the *running* couchpad service.

A virtual DualSense is created through /dev/uhid, so the kernel's real
hid-playstation driver handles it exactly like the physical controller. We
then press buttons / touch the pad and check the real effects in KWin:
cursor position, window minimised, process killed, Steam keyboard shown.

It moves the real cursor (and puts it back) and only ever minimises or
kills its own throw-away kdialog windows. Opt-in:

    COUCHPAD_LIVE=1 python3 -m unittest tests.test_live -v
"""

import json
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from couchpad import system  # noqa: E402

LIVE = os.environ.get("COUCHPAD_LIVE") == "1"


def couchpad(*args):
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "couchpad", *args],
                       capture_output=True, text=True, env=env, timeout=10)
    return r.stdout.strip()


def status():
    return json.loads(couchpad("status"))


@unittest.skipUnless(LIVE, "set COUCHPAD_LIVE=1 (touches the real desktop)")
class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from uhid_dualsense import VirtualDualSense
        if subprocess.run(["systemctl", "--user", "is-active", "-q", "couchpad"]).returncode:
            raise unittest.SkipTest("couchpad.service is not running")
        cls.bus = system.Bus(name=f"org.couchpad.Live{os.getpid()}")
        couchpad("mouse", "off")
        cls.v = VirtualDualSense()
        assert cls.v.started.wait(3)
        cls.uniq = None
        for _ in range(100):
            cls.v.send()
            time.sleep(0.03)
            ctls = status()["controllers"]
            if len(ctls) >= 2 and all(c["touchpad"] for c in ctls):
                cls.uniq = ctls[-1]["uniq"]
                break
        assert cls.uniq, "service did not pick up the virtual controller"
        time.sleep(3.5)      # let the delayed KWin touchpad disabling run

    @classmethod
    def tearDownClass(cls):
        couchpad("mouse", "off")
        cls.v.close()
        cls.bus.close()

    # -- helpers ---------------------------------------------------------------
    def cursor(self):
        p = self.bus.kwin_eval("report({x: workspace.cursorPos.x, y: workspace.cursorPos.y});")
        return p["x"], p["y"]

    def window(self, title):
        p = subprocess.Popen(["kdialog", "--title", title, "--msgbox", "couchpad live test"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        js = ("var l = workspace.windowList(), f = null;"
              "for (var i = 0; i < l.length; i++) if (l[i].pid == %d) f = l[i];"
              "if (f) { workspace.activeWindow = f; }"
              "report({found: !!f, active: !!f && workspace.activeWindow == f});") % p.pid
        for _ in range(100):
            r = self.bus.kwin_eval(js)
            if r and r.get("active"):
                return p
            time.sleep(0.05)
        self.fail("could not activate test window")

    def win_state(self, pid):
        return self.bus.kwin_eval(
            "var l = workspace.windowList(), f = null;"
            "for (var i = 0; i < l.length; i++) if (l[i].pid == %d) f = l[i];"
            "report(f ? {exists: true, minimized: f.minimized} : {exists: false});" % pid)

    def double_tap(self):
        self.v.tap("share")
        time.sleep(0.1)
        self.v.tap("share")
        time.sleep(0.2)

    def wait(self, cond, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        return cond()

    # -- tests -------------------------------------------------------------------
    def test_1_touchpad_inert_when_mouse_off(self):
        """KDE must not move the cursor with the pad on its own either."""
        self.assertFalse(status()["mouse"])
        before = self.cursor()
        self.v.swipe((600, 500), (1300, 500))
        time.sleep(0.2)
        self.assertEqual(self.cursor(), before)

    def test_2_double_tap_then_touchpad_moves_cursor(self):
        self.double_tap()
        self.assertTrue(self.wait(lambda: status()["mouse"]))
        x0, y0 = self.cursor()
        going_right = x0 < 1500
        a, b = ((500, 540), (900, 540)) if going_right else ((900, 540), (500, 540))
        self.v.swipe(a, b, steps=50, dt=0.008)
        time.sleep(0.2)
        x1, y1 = self.cursor()
        self.assertGreater(abs(x1 - x0), 60, (x0, x1))
        self.assertEqual(x1 > x0, going_right)
        self.assertLess(abs(y1 - y0), 5)
        self.v.swipe(b, a, steps=50, dt=0.008)          # put it back
        time.sleep(0.2)
        self.double_tap()
        self.assertTrue(self.wait(lambda: not status()["mouse"]))

    def test_3_long_share_circle_minimizes(self):
        p = self.window("couchpad-live-minimize")
        self.v.hold(("share", "circle"), 3.4)
        self.assertTrue(self.wait(lambda: (self.win_state(p.pid) or {}).get("minimized")),
                        self.win_state(p.pid))
        time.sleep(0.5)
        self.assertFalse(status()["mouse"], "minimize must not switch the touchpad on")

    def test_4_long_share_triangle_force_closes(self):
        p = self.window("couchpad-live-close")
        self.v.hold(("share", "triangle"), 3.4)
        self.assertTrue(self.wait(lambda: p.poll() is not None, 5), "process still alive")
        self.assertFalse(self.win_state(p.pid)["exists"])
        time.sleep(0.5)
        self.assertFalse(status()["mouse"], "Share+triangle must not switch the touchpad on")

    def test_5_short_share_triangle_does_not_close(self):
        p = self.window("couchpad-live-keep")
        self.v.hold(("share", "triangle"), 1.0)
        time.sleep(3)
        self.assertIsNone(p.poll(), "short press must not kill")
        self.assertFalse(status()["mouse"])

    def test_6_steam_keyboard_toggle(self):
        if not system.steam_running():
            self.skipTest("Steam not running")
        visible = lambda: self.bus.kwin_eval(system.STEAM_KEYBOARD_VISIBLE)["open"]
        self.assertFalse(visible())
        self.v.press("share")
        self.v.tap("square")
        self.v.release("share")
        self.assertTrue(self.wait(visible, 5), "keyboard did not open")
        time.sleep(0.5)
        self.v.press("share")
        self.v.tap("square")
        self.v.release("share")
        self.assertTrue(self.wait(lambda: not visible(), 5), "keyboard did not close")

    def test_6b_steam_keyboard_pulled_back_on_screen(self):
        """Steam may place the keyboard for another screen (monitor <-> TV)."""
        if not system.steam_running():
            self.skipTest("Steam not running")
        self.v.press("share")
        self.v.tap("square")
        self.v.release("share")
        visible = lambda: self.bus.kwin_eval(system.STEAM_KEYBOARD_VISIBLE)["open"]
        self.assertTrue(self.wait(visible, 5))
        time.sleep(0.5)
        push = system.STEAM_KEYBOARD_JS % (
            "var a = workspace.clientArea(KWin.MaximizeArea, k), g = k.frameGeometry;"
            "k.frameGeometry = {x: g.x, y: a.y + a.height - g.height / 3,"
            " width: g.width, height: g.height}; report({ok: true});")
        self.bus.kwin_eval(push)
        inside = system.STEAM_KEYBOARD_JS % (
            "var a = workspace.clientArea(KWin.MaximizeArea, k), g = k.frameGeometry;"
            "report({ok: g.y >= a.y - 1 && g.y + g.height <= a.y + a.height + 1});")
        try:
            self.assertTrue(self.wait(lambda: self.bus.kwin_eval(inside)["ok"], 3),
                            "keyboard not moved back on screen")
        finally:
            self.v.press("share")
            self.v.tap("square")
            self.v.release("share")
            self.wait(lambda: not visible(), 5)

    def test_7_alt_tab_open_and_cancel_restores_focus(self):
        p = self.window("couchpad-live-alttab")
        self.v.press("share")
        self.v.tap("circle")
        self.v.release("share")
        time.sleep(0.6)
        self.v.send()
        self.v.tap("circle")                 # cancel
        time.sleep(0.4)
        active = self.bus.kwin_eval("report({pid: workspace.activeWindow ? "
                                    "workspace.activeWindow.pid : 0});")
        self.assertEqual(active["pid"], p.pid, "cancel keeps the original window")

    def test_9_force_close_kills_whole_steam_game_tree(self):
        # Looks like Steam's launcher: argv[0] = .../reaper, "SteamLaunch AppId=N".
        script = ("kdialog --title couchpad-live-game --msgbox game & "
                  "sleep 300 & wait")
        reaper = subprocess.Popen(["/tmp/fake/reaper", "-c", script, "SteamLaunch",
                                   "AppId=999999", "--", "game.exe"],
                                  executable="/bin/sh", stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (reaper.poll() is None and reaper.kill(), reaper.wait()))
        from couchpad import procs
        game = None
        for _ in range(100):
            kids = procs.descendants(procs.read_table(), reaper.pid)
            t = procs.read_table()
            game = next((k for k in kids if t.get(k, {}).get("comm") == "kdialog"), None)
            if game:
                break
            time.sleep(0.05)
        self.assertIsNotNone(game)
        js = ("var l = workspace.windowList(), f = null;"
              "for (var i = 0; i < l.length; i++) if (l[i].pid == %d) f = l[i];"
              "if (f) workspace.activeWindow = f; report({ok: !!f});") % game
        self.assertTrue(self.wait(lambda: self.bus.kwin_eval(js)["ok"]))
        time.sleep(0.3)
        self.v.hold(("share", "triangle"), 3.4)
        self.assertTrue(self.wait(lambda: reaper.poll() is not None, 5), "reaper still alive")
        t = procs.read_table()
        self.assertTrue(game not in t or t[game]["state"] == "Z", "game process survived")
        self.assertFalse([k for k in procs.descendants(t, reaper.pid)])

    # -- quick-launch wheel ---------------------------------------------------------
    def wheel_items(self, n=4):
        import tempfile
        d = tempfile.mkdtemp(prefix="couchpad-wheel-")
        items = [{"name": f"T{i}", "icon": "dialog-information", "exec": f"touch {d}/{i}"}
                 for i in range(n)]
        couchpad("wheel-items", json.dumps(items))
        self.addCleanup(couchpad, "wheel-items", "reset")
        return d

    def wheel_state(self):
        """The wheel is a layer-shell overlay: KWin scripts can't see it by
        caption, so ask the service what the overlay reported."""
        st = json.loads(couchpad("wheel-state"))
        x, y, w, h = st.get("geo") or (0, 0, 0, 0)
        return {"shown": st["shown"], "open": st["open"], "overlay": st["overlay"],
                "x": x, "y": y, "w": w, "h": h}

    def close_wheel_if_open(self):
        if self.wheel_state()["open"]:
            self.v.tap("circle")
        self.v.release("r1", "share")
        self.set_rstick(128, 128)

    def open_wheel(self):
        self.addCleanup(self.close_wheel_if_open)
        self.v.press("share")
        time.sleep(0.05)
        self.v.press("r1")
        self.assertTrue(self.wait(lambda: self.wheel_state()["shown"], 3), "wheel not shown")

    def set_rstick(self, x, y):
        self.v.sticks[2], self.v.sticks[3] = x, y
        self.v.send()

    def test_a_wheel_stick_select_and_launch(self):
        d = self.wheel_items()
        self.open_wheel()
        st = self.wheel_state()
        self.assertTrue(st["overlay"], "wheel must be a layer-shell overlay (above everything)")
        self.set_rstick(255, 128)                  # right -> item 1 of 4
        time.sleep(0.2)
        self.set_rstick(128, 128)
        self.v.release("r1")
        self.v.release("share")
        self.assertTrue(self.wait(lambda: os.path.exists(f"{d}/1"), 3), os.listdir(d))
        self.assertEqual(sorted(os.listdir(d)), ["1"])
        self.assertTrue(self.wait(lambda: not self.wheel_state()["shown"], 3))
        self.assertFalse(json.loads(couchpad("wheel-state"))["open"])

    def test_b_wheel_quick_press_and_screenshot_moved(self):
        from couchpad import procs
        spectacle = lambda: {p for p, i in procs.read_table().items()
                             if i["comm"] == "spectacle" and i.get("state") != "Z"}
        before = spectacle()
        d = self.wheel_items()
        self.addCleanup(self.close_wheel_if_open)
        self.v.press("share")
        self.v.tap("r1", hold=0.08)              # quick press: wheel, no screenshot
        self.v.release("share")
        self.assertTrue(self.wait(lambda: self.wheel_state()["shown"], 3))
        time.sleep(1.0)
        self.assertEqual(spectacle() - before, set(), "quick Share+R1 took a screenshot")
        self.close_wheel_if_open()
        self.v.press("share")
        self.v.tap("l2")                         # Share + L2 = screenshot
        self.v.release("share")
        try:
            self.assertTrue(self.wait(lambda: spectacle() - before, 5), "no screenshot")
            self.assertEqual(os.listdir(d), [])
        finally:
            time.sleep(1.0)
            for pid in spectacle() - before:
                os.kill(pid, 15)

    def test_c_wheel_cancel_with_circle(self):
        d = self.wheel_items()
        self.open_wheel()
        self.set_rstick(128, 0)
        time.sleep(0.15)
        self.v.tap("circle")
        self.v.release("r1")
        self.v.release("share")
        self.set_rstick(128, 128)
        self.assertTrue(self.wait(lambda: not self.wheel_state()["shown"], 3))
        time.sleep(0.5)
        self.assertEqual(os.listdir(d), [])

    def test_d_wheel_mouse_click(self):
        d = self.wheel_items()
        self.open_wheel()
        self.v.release("r1")                       # nothing picked: stays open
        self.v.release("share")
        time.sleep(0.3)
        self.assertTrue(self.wheel_state()["shown"])
        couchpad("mouse", "on")
        self.addCleanup(couchpad, "mouse", "off")
        st = self.wheel_state()
        # item 2 of 4 = bottom sector
        tx = st["x"] + st["w"] / 2
        ty = st["y"] + st["h"] / 2 + min(st["w"], st["h"]) * 0.36 * 0.68
        for _ in range(12):                         # steer with the touchpad
            cx, cy = self.cursor()
            dx, dy = tx - cx, ty - cy
            if abs(dx) < 25 and abs(dy) < 25:
                break
            k = 0.9
            sx = max(-700, min(700, dx * k))
            sy = max(-400, min(400, dy * k))
            self.v.swipe((960, 540), (960 + int(sx), 540 + int(sy)), steps=60, dt=0.012)
            time.sleep(0.15)
        cx, cy = self.cursor()
        self.assertLess(abs(tx - cx) + abs(ty - cy), 60, (cx, cy, tx, ty))
        self.v.touch[0] = (9, 960, 540)            # tap = left click
        self.v.send()
        time.sleep(0.05)
        self.v.touch[0] = None
        self.v.send()
        self.assertTrue(self.wait(lambda: os.path.exists(f"{d}/2"), 3), os.listdir(d))
        self.assertTrue(self.wait(lambda: not self.wheel_state()["shown"], 3))

    def test_e_wheel_over_big_picture(self):
        if not system.steam_running():
            self.skipTest("Steam not running")
        d = self.wheel_items()
        subprocess.Popen(["steam", "steam://open/bigpicture"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: subprocess.Popen(["steam", "steam://close/bigpicture"],
                                                 stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL))
        bp = ("var a = workspace.activeWindow; report({fs: !!a && a.fullScreen &&"
              " String(a.resourceClass) == 'steam'});")
        self.assertTrue(self.wait(lambda: self.bus.kwin_eval(bp)["fs"], 15),
                        "Big Picture did not open fullscreen")
        time.sleep(1.0)
        self.open_wheel()
        st = self.wheel_state()
        # layer-shell overlay layer is above fullscreen windows by protocol
        self.assertTrue(st["shown"] and st["overlay"], f"wheel not above Big Picture: {st}")
        self.set_rstick(128, 255)                  # down -> item 2
        time.sleep(0.2)
        self.v.release("r1")
        self.v.release("share")
        self.set_rstick(128, 128)
        self.assertTrue(self.wait(lambda: os.path.exists(f"{d}/2"), 3))

    def hd_reports(self):
        import struct as st
        import zlib
        out = [r for r in self.v.outputs if r and r[0] == 0x32]
        for r in out:
            self.assertEqual(len(r), 141)
            self.assertEqual(st.unpack("<I", r[-4:])[0], zlib.crc32(b"\xa2" + r[:-4]))
        return out

    def test_f_hd_haptics_on_wheel_and_switcher(self):
        from couchpad import config
        cfg = config.load()
        if not cfg.rumble or cfg.haptics == "rumble":
            self.skipTest("HD haptics are switched off in config.toml")
        self.wheel_items(6)
        self.v.outputs.clear()
        self.open_wheel()
        for x, y in ((128, 0), (255, 128), (128, 255)):
            self.set_rstick(x, y)
            time.sleep(0.15)
        self.v.tap("circle")
        self.v.release("r1", "share")
        self.set_rstick(128, 128)
        time.sleep(0.3)
        reps = self.hd_reports()
        self.assertGreater(len(reps), 10, "no HD haptic reports reached the pad")
        signal = [r for r in reps if any(r[13:77])]
        self.assertGreaterEqual(len(signal), 4, "open + 3 detents + cancel")
        # right-stick 'right' click must be louder on the right actuator
        lr = [(max(abs(int.from_bytes(r[13 + i:14 + i], "big", signed=True)) for i in range(0, 64, 2)),
               max(abs(int.from_bytes(r[14 + i:15 + i], "big", signed=True)) for i in range(0, 64, 2)))
              for r in signal]
        self.assertTrue(any(rr > 2 * l for l, rr in lr), lr)
        # switcher
        p = self.window("couchpad-live-hd")
        self.v.outputs.clear()
        self.v.press("share")
        self.v.tap("circle")
        self.v.release("share")
        time.sleep(0.3)
        self.v.dpad = "right"; self.v.send(); time.sleep(0.05)
        self.v.dpad = None; self.v.send(); time.sleep(0.2)
        self.v.tap("circle")
        time.sleep(0.3)
        signal = [r for r in self.hd_reports() if any(r[13:77])]
        self.assertGreaterEqual(len(signal), 3, "open + step + cancel")

    def test_g_lightbar_reaches_the_pad(self):
        """The kernel turns our LED class write into an output report."""
        def lightbar_reports():
            out = []
            for r in list(self.v.outputs):
                # 0x31, seq, tag, common: valid_flag1 bit 2 = light bar
                if len(r) >= 78 and r[0] == 0x31 and r[4] & 0x04:
                    out.append(tuple(r[3 + 44:3 + 47]))
            return out
        self.v.outputs.clear()
        self.assertEqual(couchpad("light-preview", "#ff0000"), "ok")
        self.assertTrue(self.wait(lambda: any(r > 60 and g == 0 and b == 0
                                              for r, g, b in lightbar_reports()), 3),
                        lightbar_reports())
        self.v.outputs.clear()
        couchpad("light-preview", "#00ff00")
        self.assertTrue(self.wait(lambda: any(g > 60 and r == 0 for r, g, b in lightbar_reports()), 3))

    def test_h_chord_runs_remapped_action(self):
        """Share + R2 (default: mute) arrives as KEY_MUTE through the daemon."""
        couchpad("clear-events")
        self.v.press("share")
        self.v.tap("r2")
        self.v.release("share")
        self.assertTrue(self.wait(lambda: "mute" in status()["events"], 3), status()["events"])
        # restore the volume state
        self.v.press("share")
        self.v.tap("r2")
        self.v.release("share")
        time.sleep(0.3)

    def test_8_alt_tab_switches_window(self):
        a = self.window("couchpad-live-a")
        b = self.window("couchpad-live-b")         # b is active now
        self.v.press("share")
        self.v.tap("circle")                 # opens switcher, selects previous (a)
        self.v.release("share")
        time.sleep(0.6)
        self.v.tap("cross")                  # confirm
        time.sleep(0.5)
        active = self.bus.kwin_eval("report({pid: workspace.activeWindow ? "
                                    "workspace.activeWindow.pid : 0});")
        self.assertEqual(active["pid"], a.pid)


if __name__ == "__main__":
    unittest.main()
