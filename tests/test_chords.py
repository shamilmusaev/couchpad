import unittest

from couchpad import actions
from fakes import make_controller


def chord(ctl, button, t=0.0):
    ctl.button("share", True, t)
    ctl.button(button, True, t + 0.05)
    ctl.button(button, False, t + 0.1)
    ctl.button("share", False, t + 0.15)


class Catalogue(unittest.TestCase):
    def test_defaults_are_valid(self):
        for b, a in actions.DEFAULT_CHORDS.items():
            self.assertIn(b, actions.CHORD_BUTTONS)
            self.assertIn(a, actions.ACTIONS)
        self.assertEqual(set(actions.DEFAULT_CHORDS), set(actions.CHORD_BUTTONS))

    def test_overrides_filtered(self):
        eff = actions.chords({"square": "mute", "circle": "mute", "l1": "nope"})
        self.assertEqual(eff["square"], "mute")
        self.assertNotIn("circle", eff, "fixed chords can't be remapped")
        self.assertEqual(eff["l1"], actions.DEFAULT_CHORDS["l1"])

    def test_daemon_runs_every_action(self):
        from couchpad.daemon import ControllerActions, Services
        for name in actions.ACTIONS:
            if name == "mouse_toggle":
                continue
            self.assertTrue(name in ControllerActions.KEY_ACTIONS or
                            (name in ControllerActions.THREADED and hasattr(Services, name)), name)


class Remap(unittest.TestCase):
    def test_remapped_chord(self):
        ctl, out, acts, mode = make_controller(chords={"square": "screenshot"})
        chord(ctl, "square")
        self.assertEqual(acts.ran, ["screenshot"])

    def test_live_change(self):
        ctl, out, acts, mode = make_controller()
        chord(ctl, "l3")
        ctl.cfg.chords = {"l3": "mute"}
        chord(ctl, "l3", 2)
        self.assertEqual(acts.ran, ["control_center", "mute"])

    def test_none(self):
        ctl, out, acts, mode = make_controller(chords={"cross": "none"})
        chord(ctl, "cross")
        self.assertEqual(acts.ran, [])

    def test_mouse_toggle_chord(self):
        ctl, out, acts, mode = make_controller(chords={"r2": "mouse_toggle"})
        chord(ctl, "r2")
        self.assertTrue(mode.mouse)
        chord(ctl, "r2", 2)
        self.assertFalse(mode.mouse)

    def test_remapped_volume_repeats(self):
        ctl, out, acts, mode = make_controller(chords={"r3": "volume_up"})
        ctl.button("share", True, 0)
        ctl.button("r3", True, 0.05)
        t = 0.05
        while t < 1.0:
            ctl.tick(t)
            t += 0.01
        self.assertGreater(acts.ran.count("volume_up"), 3)

    def test_run_action(self):
        ctl, out, acts, mode = make_controller()
        ctl.run_action("overview")
        ctl.run_action("none")
        ctl.run_action("mouse_toggle")
        self.assertEqual(acts.ran, ["overview"])
        self.assertTrue(mode.mouse)


class HoldRing(unittest.TestCase):
    def test_fires(self):
        ctl, out, acts, mode = make_controller(long_press=1.0)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0.05)
        t = 0.05
        while t < 1.2:
            ctl.tick(t)
            t += 0.01
        self.assertEqual(acts.holds, [("start", "force_close"), ("end", True)])

    def test_let_go_early(self):
        ctl, out, acts, mode = make_controller(long_press=1.0)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0.05)
        ctl.tick(0.3)
        ctl.button("triangle", False, 0.4)
        self.assertEqual(acts.holds, [("start", "force_close"), ("end", False)])

    def test_share_released_early(self):
        ctl, out, acts, mode = make_controller(long_press=1.0)
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.05)
        ctl.button("share", False, 0.2)
        ctl.button("circle", False, 0.3)
        self.assertEqual(acts.holds, [("start", "minimize"), ("end", False)],
                         "exactly one end, then the switcher opens")
        self.assertEqual(acts.switches, ["open"])

    def test_quick_circle_ends_ring(self):
        ctl, out, acts, mode = make_controller()
        chord(ctl, "circle")
        self.assertEqual(acts.holds[-1], ("end", False))

    def test_reset_ends_ring(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0.05)
        ctl.reset()
        self.assertEqual(acts.holds[-1], ("end", False))

    def test_wheel_has_no_ring(self):
        ctl, out, acts, mode = make_controller()
        chord(ctl, "r1")
        self.assertEqual(acts.holds, [])


if __name__ == "__main__":
    unittest.main()
