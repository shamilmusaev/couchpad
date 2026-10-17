import asyncio
import unittest

from evdev import ecodes as e

from couchpad.daemon import HAPTICS, Rumble
from fakes import make_controller


def hold_until(ctl, start, end, step=0.01):
    t = start
    while t <= end + 1e-9:
        ctl.tick(t)
        t += step


class EngineFeedback(unittest.TestCase):
    def test_hold_gives_rising_ticks_then_fire(self):
        ctl, out, acts, mode = make_controller(long_press=1.5)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0)
        hold_until(ctl, 0, 1.6)
        self.assertEqual(acts.fb, ["tick", "progress1", "progress2", "progress3", "fire"])

    def test_released_early_no_fire(self):
        ctl, out, acts, mode = make_controller(long_press=1.5)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0)
        hold_until(ctl, 0, 0.5)
        ctl.button("triangle", False, 0.5)
        self.assertNotIn("fire", acts.fb)
        self.assertEqual(acts.fb, ["tick", "progress1"])

    def test_wheel_detents(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        for x, y in ((0, -1), (0, -1), (1, 0), (0, 1)):
            ctl.axis("rx", x, 0.2)
            ctl.axis("ry", y, 0.2)
        ctl.button("r1", False, 0.5)
        self.assertEqual(acts.fb[0], "open")
        # up -> (up-right diagonal) -> right -> down: one click per sector passed
        self.assertEqual(acts.fb.count("detent"), 4, acts.fb)
        self.assertEqual(acts.fb[-1], "launch")

    def test_wheel_cancel_thump(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        ctl.button("circle", True, 0.2)
        self.assertEqual(acts.fb[-1], "cancel")


class FakeFF:
    def __init__(self):
        self.uploads = []
        self.plays = []
        self.erased = []

    def upload_effect(self, eff):
        self.uploads.append(eff)
        return 3 if eff.id == -1 else eff.id

    def write(self, etype, code, value):
        self.plays.append((etype, code, value))

    def erase_effect(self, eid):
        self.erased.append(eid)


class RumbleDevice(unittest.TestCase):
    def run_pattern(self, *names, strength=1.0, wait=0.4):
        async def go():
            dev = FakeFF()
            r = Rumble(dev, asyncio.get_running_loop(), True, strength)
            for n in names:
                r.play(n)
            await asyncio.sleep(wait)
            r.close()
            return dev
        return asyncio.run(go())

    def test_patterns_are_short_and_valid(self):
        for name, pulses in HAPTICS.items():
            for at, strong, weak, ms in pulses:
                self.assertLessEqual(ms, 60, name)
                self.assertTrue(0 <= strong <= 0xFFFF and 0 <= weak <= 0xFFFF, name)
                self.assertLess(at, 300, name)

    def test_single_slot_reused(self):
        dev = self.run_pattern("fire")
        self.assertEqual(len(dev.uploads), 2)
        self.assertEqual(dev.uploads[0].id, -1)
        self.assertEqual(dev.uploads[1].id, 3, "second pulse reuses the slot")
        self.assertEqual(dev.plays, [(e.EV_FF, 3, 1)] * 2)
        self.assertEqual(dev.erased, [3])

    def test_strength_scales_and_clamps(self):
        dev = self.run_pattern("launch", strength=2.0)
        self.assertEqual(dev.uploads[0].u.ff_rumble_effect.weak_magnitude,
                         min(0xB000 * 2, 0xFFFF))
        dev = self.run_pattern("launch", strength=0.5)
        self.assertEqual(dev.uploads[0].u.ff_rumble_effect.weak_magnitude, 0xB000 // 2)

    def test_zero_strength_is_silent(self):
        dev = self.run_pattern("fire", strength=0)
        self.assertEqual(dev.plays, [])

    def test_new_pattern_replaces_pending_pulses(self):
        dev = self.run_pattern("fire", "detent")
        self.assertEqual(len(dev.plays), 1, "fire's second pulse was cancelled")

    def test_unknown_pattern_ignored(self):
        dev = self.run_pattern("nope")
        self.assertEqual(dev.plays, [])


if __name__ == "__main__":
    unittest.main()
