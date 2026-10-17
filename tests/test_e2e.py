"""End-to-end: fake DualSense (uinput) -> real daemon -> real uinput output.

The fake controller and the daemon's output devices are disabled in KWin
for the duration of the test, so nothing reaches the real desktop.
Needs the couchpad udev rule (test devices readable) and /dev/uinput.
"""

import asyncio
import os
import select
import threading
import time
import unittest

import evdev
from evdev import UInput, AbsInfo, ecodes as e

from couchpad.config import Config
from couchpad.daemon import Daemon
from couchpad.system import UinputOutput

PREFIX = "couchpad-test DualSense"


def kwin_disable(path):
    """Tell KWin to ignore a device (returns False if KWin isn't there)."""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        node = os.path.basename(path)
        for _ in range(50):
            names = bus.call_sync(
                "org.kde.KWin", "/org/kde/KWin/InputDevice",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.kde.KWin.InputDeviceManager", "devicesSysNames")),
                None, 0, 1000, None).unpack()[0]
            if node in names:
                bus.call_sync("org.kde.KWin", f"/org/kde/KWin/InputDevice/{node}",
                              "org.freedesktop.DBus.Properties", "Set",
                              GLib.Variant("(ssv)", ("org.kde.KWin.InputDevice", "enabled",
                                                     GLib.Variant("b", False))),
                              None, 0, 1000, None)
                return True
            time.sleep(0.05)
    except Exception:
        return False
    return False


def wait_path(ui, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        for p in evdev.list_devices():
            try:
                d = evdev.InputDevice(p)
            except OSError:
                continue
            ok = d.name == ui.name
            d.close()
            if ok:
                return p
        time.sleep(0.05)
    return None


def make_gamepad():
    stick = AbsInfo(128, 0, 255, 0, 0, 0)
    hat = AbsInfo(0, -1, 1, 0, 0, 0)
    caps = {
        e.EV_KEY: [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL,
                   e.BTN_TR, e.BTN_TL2, e.BTN_TR2, e.BTN_SELECT, e.BTN_START,
                   e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
        e.EV_ABS: [(e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_RX, stick),
                   (e.ABS_RY, stick), (e.ABS_Z, AbsInfo(0, 0, 255, 0, 0, 0)),
                   (e.ABS_RZ, AbsInfo(0, 0, 255, 0, 0, 0)),
                   (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
        e.EV_FF: [e.FF_RUMBLE],
    }
    return UInput(caps, name=f"{PREFIX} Wireless Controller", vendor=0x1209,
                  product=0x0001, max_effects=16)


def make_touchpad():
    caps = {
        e.EV_KEY: [e.BTN_LEFT, e.BTN_TOUCH, e.BTN_TOOL_FINGER, e.BTN_TOOL_DOUBLETAP],
        e.EV_ABS: [(e.ABS_X, AbsInfo(0, 0, 1919, 0, 0, 0)),
                   (e.ABS_Y, AbsInfo(0, 0, 1079, 0, 0, 0)),
                   (e.ABS_MT_SLOT, AbsInfo(0, 0, 1, 0, 0, 0)),
                   (e.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
                   (e.ABS_MT_POSITION_X, AbsInfo(0, 0, 1919, 0, 0, 0)),
                   (e.ABS_MT_POSITION_Y, AbsInfo(0, 0, 1079, 0, 0, 0))],
    }
    return UInput(caps, name=f"{PREFIX} Wireless Controller Touchpad",
                  vendor=0x1209, product=0x0001,
                  input_props=[e.INPUT_PROP_POINTER, e.INPUT_PROP_BUTTONPAD])


class Recorder(threading.Thread):
    def __init__(self, path):
        super().__init__(daemon=True)
        self.dev = evdev.InputDevice(path)
        self.events = []
        self.lock = threading.Lock()
        self.running = True
        self.start()

    def run(self):
        while self.running:
            r, _, _ = select.select([self.dev.fd], [], [], 0.05)
            if r:
                try:
                    for ev in self.dev.read():
                        with self.lock:
                            self.events.append((ev.type, ev.code, ev.value))
                except OSError:
                    return

    def take(self):
        with self.lock:
            evs, self.events = self.events, []
        return evs

    def stop(self):
        self.running = False
        self.join(1)
        self.dev.close()


def rel_sum(evs, code):
    return sum(v for t, c, v in evs if t == e.EV_REL and c == code)


def keys(evs):
    return [(c, v) for t, c, v in evs if t == e.EV_KEY]


@unittest.skipUnless(os.access("/dev/uinput", os.W_OK), "no /dev/uinput access")
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = UinputOutput(name="couchpad-test-out")
        mpath = wait_path(cls.out.mouse)
        kpath = wait_path(cls.out.kbd)
        if not (mpath and kpath and os.access(mpath, os.R_OK)):
            cls.out.close()
            raise unittest.SkipTest("output devices not readable (udev rule missing)")
        cls.kwin = all(kwin_disable(p) for p in (mpath, kpath))
        cls.mouse = Recorder(mpath)
        cls.kbd = Recorder(kpath)
        cls.pad = make_gamepad()
        cls.tp = make_touchpad()
        cls.pad_path = wait_path(cls.pad)
        cls.tp_path = wait_path(cls.tp)
        for p in (cls.pad_path, cls.tp_path):
            kwin_disable(p)
        cfg = Config(long_press=1.0, notifications=False, rumble=False)
        cls.daemon = Daemon(cfg, dry=True, match_name=PREFIX, out=cls.out, use_bus=False)
        cls.ready = threading.Event()

        def runner():
            async def main():
                cls.stop = asyncio.Event()
                cls.loop = asyncio.get_running_loop()
                cls.ready.set()
                await cls.daemon.run(stop=cls.stop)
            asyncio.run(main())
        cls.thread = threading.Thread(target=runner, daemon=True)
        cls.thread.start()
        cls.ready.wait(3)
        cls.wait_for(lambda: len(cls.daemon.paths) == 2, 3)

    @classmethod
    def tearDownClass(cls):
        cls.loop.call_soon_threadsafe(cls.stop.set)
        cls.thread.join(3)
        for r in (cls.mouse, cls.kbd):
            r.stop()
        for u in (cls.pad, cls.tp):
            try:
                u.close()
            except Exception:
                pass

    @staticmethod
    def wait_for(cond, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return cond()

    def setUp(self):
        self.set_mouse(False)
        time.sleep(0.1)
        self.mouse.take()
        self.kbd.take()
        self.daemon.events.clear()

    # -- helpers ---------------------------------------------------------------
    def set_mouse(self, on):
        self.loop.call_soon_threadsafe(self.daemon.set_mouse, on)
        self.wait_for(lambda: self.daemon.mode.mouse == on)

    def btn(self, code, value, pad=None):
        pad = pad or self.pad
        pad.write(e.EV_KEY, code, value)
        pad.syn()

    def press(self, code, hold=0.05):
        self.btn(code, 1)
        time.sleep(hold)
        self.btn(code, 0)

    def touch(self, x, y, slot=0, tid=None):
        self.tp.write(e.EV_ABS, e.ABS_MT_SLOT, slot)
        if tid is not None:
            self.tp.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, tid)
        self.tp.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
        self.tp.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
        self.tp.syn()

    def lift(self, slot=0):
        self.tp.write(e.EV_ABS, e.ABS_MT_SLOT, slot)
        self.tp.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)
        self.tp.syn()

    def double_tap_share(self):
        self.press(e.BTN_SELECT, 0.05)
        time.sleep(0.1)
        self.press(e.BTN_SELECT, 0.05)

    # -- tests ---------------------------------------------------------------------
    def test_01_devices_found_and_touchpad_grabbed(self):
        self.assertEqual(len(self.daemon.pads), 1, "gamepad+touchpad grouped")
        pad = next(iter(self.daemon.pads.values()))
        self.assertIsNotNone(pad.gamepad)
        self.assertIsNotNone(pad.touchpad)
        probe = evdev.InputDevice(self.tp_path)
        with self.assertRaises(OSError):
            probe.grab()            # already grabbed by the daemon
        probe.close()

    def test_02_double_tap_share_toggles(self):
        self.double_tap_share()
        self.assertTrue(self.wait_for(lambda: self.daemon.mode.mouse))
        time.sleep(0.6)
        self.double_tap_share()
        self.assertTrue(self.wait_for(lambda: not self.daemon.mode.mouse))
        self.assertEqual(self.daemon.events, ["mouse_on", "mouse_off"])

    def test_03_touchpad_moves_pointer(self):
        self.set_mouse(True)
        self.touch(500, 500, tid=1)
        for i in range(1, 41):
            time.sleep(0.004)
            self.touch(500 + i * 10, 500)
        self.lift()
        time.sleep(0.2)
        evs = self.mouse.take()
        self.assertGreater(rel_sum(evs, e.REL_X), 100)
        self.assertEqual(rel_sum(evs, e.REL_Y), 0)
        self.assertEqual(keys(evs), [], "a swipe is not a click")

    def test_04_touchpad_ignored_when_mouse_off(self):
        self.touch(500, 500, tid=2)
        for i in range(1, 30):
            time.sleep(0.004)
            self.touch(500 + i * 10, 500)
        self.lift()
        time.sleep(0.2)
        self.assertEqual(self.mouse.take(), [])

    def test_05_tap_clicks(self):
        self.set_mouse(True)
        self.touch(800, 500, tid=3)
        time.sleep(0.05)
        self.lift()
        time.sleep(0.2)
        self.assertEqual(keys(self.mouse.take()), [(e.BTN_LEFT, 1), (e.BTN_LEFT, 0)])

    def test_06_two_finger_scroll(self):
        self.set_mouse(True)
        self.touch(600, 700, slot=0, tid=4)
        self.touch(1000, 700, slot=1, tid=5)
        for i in range(1, 31):
            time.sleep(0.004)
            self.tp.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
            self.tp.write(e.EV_ABS, e.ABS_MT_POSITION_Y, 700 - i * 10)
            self.tp.write(e.EV_ABS, e.ABS_MT_SLOT, 1)
            self.tp.write(e.EV_ABS, e.ABS_MT_POSITION_Y, 700 - i * 10)
            self.tp.syn()
        self.lift(0)
        self.lift(1)
        time.sleep(0.2)
        evs = self.mouse.take()
        self.assertLess(rel_sum(evs, e.REL_WHEEL_HI_RES), -200)
        self.assertLess(rel_sum(evs, e.REL_WHEEL), -1, "legacy notches too")
        self.assertEqual(rel_sum(evs, e.REL_X), 0)

    def test_07_alt_tab(self):
        self.btn(e.BTN_SELECT, 1)
        self.press(e.BTN_EAST, 0.1)
        self.btn(e.BTN_SELECT, 0)
        time.sleep(0.1)
        evs = keys(self.kbd.take())
        self.assertEqual(evs, [(e.KEY_LEFTALT, 1), (e.KEY_TAB, 1), (e.KEY_TAB, 0)])
        self.pad.write(e.EV_ABS, e.ABS_HAT0X, 1)
        self.pad.syn()
        self.pad.write(e.EV_ABS, e.ABS_HAT0X, 0)
        self.pad.syn()
        time.sleep(0.05)
        self.press(e.BTN_SOUTH)
        time.sleep(0.1)
        evs = keys(self.kbd.take())
        self.assertEqual(evs, [(e.KEY_TAB, 1), (e.KEY_TAB, 0), (e.KEY_LEFTALT, 0)])
        self.assertEqual(self.daemon.events, ["switcher_open", "switcher_confirm"],
                         "plain alt-tab: no other action")

    def test_08_long_share_circle_minimizes(self):
        self.btn(e.BTN_SELECT, 1)
        self.btn(e.BTN_EAST, 1)
        time.sleep(1.3)          # long_press = 1.0 in this test
        self.btn(e.BTN_EAST, 0)
        self.btn(e.BTN_SELECT, 0)
        time.sleep(0.2)
        self.assertTrue(self.wait_for(lambda: "minimize" in self.daemon.events))
        self.assertEqual(keys(self.kbd.take()), [], "no alt-tab after long press")

    def test_09_long_share_triangle_force_close(self):
        self.btn(e.BTN_SELECT, 1)
        self.btn(e.BTN_NORTH, 1)
        time.sleep(0.5)
        self.assertEqual(self.daemon.events, [])
        time.sleep(0.8)
        self.btn(e.BTN_NORTH, 0)
        self.btn(e.BTN_SELECT, 0)
        self.assertTrue(self.wait_for(lambda: self.daemon.events == ["force_close"]))

    def test_10_volume_chord(self):
        self.btn(e.BTN_SELECT, 1)
        self.pad.write(e.EV_ABS, e.ABS_HAT0Y, -1)
        self.pad.syn()
        time.sleep(0.05)
        self.pad.write(e.EV_ABS, e.ABS_HAT0Y, 0)
        self.pad.syn()
        self.btn(e.BTN_SELECT, 0)
        time.sleep(0.1)
        self.assertEqual(keys(self.kbd.take()), [(e.KEY_VOLUMEUP, 1), (e.KEY_VOLUMEUP, 0)])

    def test_11_left_stick_pointer(self):
        self.set_mouse(True)
        self.pad.write(e.EV_ABS, e.ABS_X, 255)
        self.pad.syn()
        time.sleep(0.5)
        self.pad.write(e.EV_ABS, e.ABS_X, 128)
        self.pad.syn()
        time.sleep(0.1)
        dx = rel_sum(self.mouse.take(), e.REL_X)
        self.assertGreater(dx, 400)
        self.assertLess(dx, 1000)

    def test_12_mouse_off_releases_held_button(self):
        self.set_mouse(True)
        self.btn(e.BTN_TR2, 1)
        time.sleep(0.05)
        self.set_mouse(False)
        time.sleep(0.05)
        self.btn(e.BTN_TR2, 0)
        time.sleep(0.1)
        self.assertEqual(keys(self.mouse.take()), [(e.BTN_LEFT, 1), (e.BTN_LEFT, 0)])

    def test_13_unplug_releases_and_replug_works(self):
        cls = type(self)
        self.set_mouse(True)
        self.btn(e.BTN_SOUTH, 1)
        time.sleep(0.05)
        cls.pad.close()
        self.assertTrue(self.wait_for(lambda: not self.daemon.mode.mouse, 3))
        self.assertEqual(keys(self.mouse.take()), [(e.BTN_LEFT, 1), (e.BTN_LEFT, 0)])
        cls.pad = make_gamepad()
        cls.pad_path = wait_path(cls.pad)
        kwin_disable(cls.pad_path)
        self.assertTrue(self.wait_for(
            lambda: any(p.gamepad for p in self.daemon.pads.values()), 5),
            "hot-plugged controller picked up")
        time.sleep(0.2)
        self.double_tap_share()
        self.assertTrue(self.wait_for(lambda: self.daemon.mode.mouse))

    def test_15_same_frame_chord(self):
        """Share and ○ changing in one report (kernel sends ○ first)."""
        self.pad.write(e.EV_KEY, e.BTN_EAST, 1)
        self.pad.write(e.EV_KEY, e.BTN_SELECT, 1)
        self.pad.syn()
        time.sleep(1.3)
        self.pad.write(e.EV_KEY, e.BTN_EAST, 0)
        self.pad.write(e.EV_KEY, e.BTN_SELECT, 0)
        self.pad.syn()
        self.assertTrue(self.wait_for(lambda: "minimize" in self.daemon.events))
        self.assertEqual(keys(self.kbd.take()), [])

    def test_16_same_frame_release_after_short_chord(self):
        self.btn(e.BTN_SELECT, 1)
        self.btn(e.BTN_EAST, 1)
        time.sleep(0.1)
        self.pad.write(e.EV_KEY, e.BTN_EAST, 0)
        self.pad.write(e.EV_KEY, e.BTN_SELECT, 0)
        self.pad.syn()
        time.sleep(0.1)
        evs = keys(self.kbd.take())
        self.assertEqual(evs[:1], [(e.KEY_LEFTALT, 1)], "switcher opened")
        self.press(e.BTN_EAST)            # cancel
        time.sleep(0.1)
        self.assertIn((e.KEY_LEFTALT, 0), keys(self.kbd.take()))

    def test_14_status_command(self):
        import json
        fut = asyncio.run_coroutine_threadsafe(self.daemon._command("status"), self.loop)
        st = json.loads(fut.result(2))
        self.assertEqual(len(st["controllers"]), 1)
        fut = asyncio.run_coroutine_threadsafe(self.daemon._command("mouse toggle"), self.loop)
        self.assertEqual(fut.result(2), "mouse on")


if __name__ == "__main__":
    unittest.main()
