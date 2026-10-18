import unittest

from evdev import ecodes as e

from fakes import make_controller


def press(ctl, name, t, hold=0.05):
    ctl.button(name, True, t)
    ctl.button(name, False, t + hold)


def hold_until(ctl, start, end, step=0.01):
    t = start
    while t <= end + 1e-9:
        ctl.tick(t)
        t += step


class ShareDoubleTap(unittest.TestCase):
    def test_single_tap_does_nothing(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0)
        hold_until(ctl, 0, 2)
        self.assertFalse(mode.mouse)
        self.assertEqual(acts.modes, [])

    def test_double_tap_toggles_on_and_off(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0.0)
        press(ctl, "share", 0.2)
        self.assertTrue(mode.mouse)
        press(ctl, "share", 1.0)
        press(ctl, "share", 1.2)
        self.assertFalse(mode.mouse)
        self.assertEqual(acts.modes, [True, False])

    def test_triple_tap_toggles_once(self):
        ctl, out, acts, mode = make_controller()
        for t in (0.0, 0.2, 0.4):
            press(ctl, "share", t)
        self.assertEqual(acts.modes, [True])

    def test_four_taps_toggle_twice(self):
        ctl, out, acts, mode = make_controller()
        for t in (0.0, 0.2, 0.4, 0.6):
            press(ctl, "share", t)
        self.assertEqual(acts.modes, [True, False])

    def test_slow_double_tap_ignored(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0.0)
        press(ctl, "share", 0.6)
        self.assertFalse(mode.mouse)

    def test_long_press_is_not_a_tap(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0.0, hold=0.6)
        press(ctl, "share", 0.8)
        self.assertFalse(mode.mouse)

    def test_chord_breaks_double_tap(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0.0)
        ctl.button("share", True, 0.15)
        press(ctl, "square", 0.2)
        ctl.button("share", False, 0.3)
        press(ctl, "share", 0.4)
        self.assertFalse(mode.mouse)
        self.assertEqual(acts.ran, ["keyboard"])

    def test_repeated_press_events_ignored(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0.0)
        ctl.button("share", True, 0.01)    # duplicate
        ctl.button("share", False, 0.05)
        ctl.button("share", False, 0.06)   # duplicate
        press(ctl, "share", 0.2)
        self.assertTrue(mode.mouse)


class ShareCircle(unittest.TestCase):
    def test_short_press_opens_alt_tab(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1, hold=0.2)
        self.assertTrue(ctl.alt_tab)
        self.assertIn(e.KEY_LEFTALT, out.keys)
        self.assertEqual(out.taps(e.KEY_TAB), 1)
        ctl.button("share", False, 0.5)
        self.assertTrue(ctl.alt_tab, "switcher stays open after Share release")

    def test_navigation_and_confirm(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        press(ctl, "right", 0.5)
        press(ctl, "right", 0.7)
        press(ctl, "left", 0.9)
        self.assertEqual(out.taps(e.KEY_TAB), 4)
        self.assertEqual(out.taps(e.KEY_LEFTSHIFT), 1)
        press(ctl, "cross", 1.2)
        self.assertFalse(ctl.alt_tab)
        self.assertNotIn(e.KEY_LEFTALT, out.keys)
        self.assertEqual(acts.switches, ["open", "next", "next", "back", False])
        self.assertEqual(out.taps(e.KEY_ESC), 0)

    def test_shift_is_released_after_reverse_step(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        press(ctl, "up", 0.3)
        self.assertNotIn(e.KEY_LEFTSHIFT, out.keys)
        self.assertIn(e.KEY_LEFTALT, out.keys)

    def test_cancel_with_circle(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        press(ctl, "circle", 0.5)
        self.assertFalse(ctl.alt_tab)
        self.assertEqual(out.taps(e.KEY_ESC), 1)
        self.assertEqual(out.keys, set())
        self.assertEqual(acts.switches, ["open", True])

    def test_share_circle_again_steps(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        press(ctl, "circle", 0.4, hold=0.1)
        hold_until(ctl, 0.4, 4.0)
        ctl.button("share", False, 4.1)
        self.assertEqual(out.taps(e.KEY_TAB), 2)
        self.assertNotIn("minimize", acts.ran, "no long press while switcher is open")
        self.assertTrue(ctl.alt_tab)

    def test_timeout_confirms(self):
        ctl, out, acts, mode = make_controller(alt_tab_timeout=5)
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        hold_until(ctl, 0.2, 5.0)
        self.assertTrue(ctl.alt_tab)
        hold_until(ctl, 5.0, 5.4)
        self.assertFalse(ctl.alt_tab)
        self.assertEqual(out.keys, set())

    def test_activity_extends_timeout(self):
        ctl, out, acts, mode = make_controller(alt_tab_timeout=5)
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        hold_until(ctl, 0.2, 4.0)
        press(ctl, "right", 4.0)
        hold_until(ctl, 4.0, 8.5)
        self.assertTrue(ctl.alt_tab)

    def test_stick_flick_steps_once_per_flick(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        for v in (0.2, 0.7, 0.9, 1.0, 0.8):
            ctl.axis("lx", v, 0.3)
        ctl.axis("lx", 0.0, 0.4)
        ctl.axis("lx", -0.9, 0.5)
        self.assertEqual(out.taps(e.KEY_TAB), 3)
        self.assertEqual(out.taps(e.KEY_LEFTSHIFT), 1)

    def test_long_press_minimizes(self):
        ctl, out, acts, mode = make_controller(long_press=3.0)
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.1)
        hold_until(ctl, 0.1, 3.0)
        self.assertNotIn("minimize", acts.ran)
        hold_until(ctl, 3.0, 3.2)
        self.assertEqual(acts.ran, ["minimize"])
        self.assertIn("fire", acts.fb)
        ctl.button("circle", False, 3.5)
        ctl.button("share", False, 3.6)
        hold_until(ctl, 3.6, 8)
        self.assertEqual(acts.ran, ["minimize"])
        self.assertFalse(ctl.alt_tab)
        self.assertEqual(out.keys, set())

    def test_almost_long_press_is_alt_tab(self):
        ctl, out, acts, mode = make_controller(long_press=3.0)
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.1)
        hold_until(ctl, 0.1, 3.0)
        ctl.button("circle", False, 3.0)
        self.assertEqual(acts.ran, [])
        self.assertTrue(ctl.alt_tab)

    def test_share_release_cancels_long_press(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.1)
        hold_until(ctl, 0.1, 1.0)
        ctl.button("share", False, 1.0)
        hold_until(ctl, 1.0, 5.0)
        self.assertEqual(acts.ran, [])
        ctl.button("circle", False, 5.0)
        self.assertTrue(ctl.alt_tab)

    def test_simultaneous_press_is_chord(self):
        # Same HID report: kernel order is circle (305) then share (314).
        ctl, out, acts, mode = make_controller()
        ctl.button("circle", True, 0)
        ctl.button("share", True, 0)
        hold_until(ctl, 0, 3.2)
        self.assertEqual(acts.ran, ["minimize"])

    def test_share_slightly_late_is_still_chord(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("triangle", True, 0)
        ctl.button("share", True, 0.1)
        hold_until(ctl, 0.1, 3.2)
        self.assertEqual(acts.ran, ["force_close"])

    def test_late_chord_undoes_mouse_click(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("circle", True, 0)
        self.assertEqual(out.buttons, {"right"})
        ctl.button("share", True, 0.05)
        self.assertEqual(out.buttons, set())
        ctl.button("circle", False, 0.2)
        ctl.button("share", False, 0.3)
        self.assertTrue(ctl.alt_tab, "short chord -> switcher")
        self.assertEqual(out.clicks(), [("right", True), ("right", False)])

    def test_late_share_is_not_a_double_tap(self):
        ctl, out, acts, mode = make_controller()
        press(ctl, "share", 0.0)
        ctl.button("circle", True, 0.15)
        press(ctl, "share", 0.2)
        self.assertFalse(mode.mouse)

    def test_circle_long_before_share_is_not_chord(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("circle", True, 0)
        ctl.button("share", True, 0.3)
        hold_until(ctl, 0.3, 4)
        ctl.button("circle", False, 4)
        ctl.button("share", False, 4.1)
        self.assertEqual(acts.ran, [])
        self.assertFalse(ctl.alt_tab)


class DefaultHold(unittest.TestCase):
    def test_default_long_press_is_short(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0)
        hold_until(ctl, 0, 1.4)
        self.assertEqual(acts.ran, [])
        hold_until(ctl, 1.4, 1.6)
        self.assertEqual(acts.ran, ["force_close"])


class ShareTriangle(unittest.TestCase):
    def test_hold_force_closes(self):
        ctl, out, acts, mode = make_controller(long_press=3.0)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0.1)
        hold_until(ctl, 0.1, 3.05)
        self.assertEqual(acts.ran, [])
        hold_until(ctl, 3.05, 3.2)
        self.assertEqual(acts.ran, ["force_close"])
        hold_until(ctl, 3.2, 10)
        self.assertEqual(acts.ran, ["force_close"], "fires exactly once")

    def test_short_press_only_hints(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "triangle", 0.1, hold=1.0)
        hold_until(ctl, 0.1, 5)
        self.assertEqual(acts.ran, [])
        self.assertEqual(len(acts.hints), 1)

    def test_share_release_cancels(self):
        ctl, out, acts, mode = make_controller(long_press=3.0)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0.1)
        hold_until(ctl, 0.1, 2.0)
        ctl.button("share", False, 2.0)
        hold_until(ctl, 2.0, 6)
        ctl.button("triangle", False, 6)
        self.assertEqual(acts.ran, [])
        self.assertIn("cancel", acts.fb)

    def test_configurable_duration(self):
        ctl, out, acts, mode = make_controller(long_press=1.5)
        ctl.button("share", True, 0)
        ctl.button("triangle", True, 0)
        hold_until(ctl, 0, 1.6)
        self.assertEqual(acts.ran, ["force_close"])

    def test_force_close_closes_switcher_first(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("triangle", True, 0.5)
        hold_until(ctl, 0.5, 3.6)
        self.assertEqual(acts.ran, ["force_close"])
        self.assertFalse(ctl.alt_tab)
        self.assertNotIn(e.KEY_LEFTALT, out.keys)


class OtherChords(unittest.TestCase):
    def test_chord_table(self):
        expected = {"square": "keyboard", "up": "volume_up", "down": "volume_down",
                    "left": "display_monitor", "right": "display_tv",
                    "cross": "media_play_pause", "l2": "screenshot",
                    "l1": "battery", "options": "overview"}
        for button, action in expected.items():
            ctl, out, acts, mode = make_controller()
            ctl.button("share", True, 0)
            press(ctl, button, 0.1)
            ctl.button("share", False, 0.3)
            self.assertEqual(acts.ran, [action], button)

    def test_volume_repeats_while_held(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("up", True, 0.1)
        hold_until(ctl, 0.1, 1.0)
        ctl.button("up", False, 1.0)
        hold_until(ctl, 1.0, 2.0)
        n = acts.ran.count("volume_up")
        # 1 immediate + repeats from 0.5 s every 0.12 s until 1.0 s
        self.assertGreaterEqual(n, 4)
        self.assertLessEqual(n, 7)

    def test_chord_release_not_leaked_to_mouse_mode(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("share", True, 0)
        ctl.button("cross", True, 0.1)
        ctl.button("share", False, 0.2)
        ctl.button("cross", False, 0.3)
        self.assertEqual(out.clicks(), [])
        self.assertEqual(acts.ran, ["media_play_pause"])


class MouseMode(unittest.TestCase):
    def test_buttons_ignored_when_off(self):
        ctl, out, acts, mode = make_controller()
        for b in ("cross", "circle", "r2", "up", "options"):
            press(ctl, b, 0)
        self.assertEqual(out.log, [])
        self.assertEqual(acts.ran, [])

    def test_mapping(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("cross", True, 0)
        self.assertEqual(out.buttons, {"left"})
        ctl.button("cross", False, 0.1)
        press(ctl, "circle", 0.2)
        press(ctl, "l2", 0.3)
        press(ctl, "r2", 0.4)
        press(ctl, "square", 0.5)
        self.assertEqual(out.clicks(), [
            ("left", True), ("left", False), ("right", True), ("right", False),
            ("right", True), ("right", False), ("left", True), ("left", False),
            ("middle", True), ("middle", False)])
        press(ctl, "up", 0.6)
        press(ctl, "options", 0.7)
        press(ctl, "r3", 0.8)
        self.assertEqual(out.taps(e.KEY_UP), 1)
        self.assertEqual(out.taps(e.KEY_LEFTMETA), 1)
        self.assertEqual(out.taps(e.KEY_ESC), 1)
        press(ctl, "triangle", 0.9)
        self.assertEqual(acts.ran, ["keyboard"])

    def test_turning_off_releases_held_buttons(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("cross", True, 0)
        ctl.button("right", True, 0)
        press(ctl, "share", 0.1)
        press(ctl, "share", 0.3)
        self.assertFalse(mode.mouse)
        self.assertEqual(out.buttons, set())
        self.assertEqual(out.keys, set())
        ctl.button("cross", False, 0.5)    # release after mode off: no output
        self.assertEqual(out.clicks(), [("left", True), ("left", False)])

    def test_sticks_off_by_default(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.axis("lx", 1.0, 0)
        ctl.axis("ry", -1.0, 0)
        self.assertFalse(ctl.needs_fast_tick())
        t = 0.0
        while t < 0.5:
            ctl.tick(t)
            t += 0.01
        self.assertEqual((out.dx, out.dy, out.vs, out.hs), (0, 0, 0, 0))

    def test_scroll_only(self):
        ctl, out, acts, mode = make_controller(stick_mouse="scroll")
        mode.mouse = True
        ctl.axis("lx", 1.0, 0)
        ctl.axis("ry", -1.0, 0)
        t = 0.0
        while t < 0.5:
            ctl.tick(t)
            t += 0.01
        self.assertEqual((out.dx, out.dy), (0, 0))
        self.assertGreater(out.vs, 0)

    def test_r2_left_r1_right_click(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("r2", True, 0)
        ctl.button("r2", False, 0.1)
        ctl.button("r1", True, 0.2)
        ctl.button("r1", False, 0.3)
        self.assertEqual(out.clicks(), [("left", True), ("left", False),
                                        ("right", True), ("right", False)])

    def test_left_stick_moves_pointer(self):
        ctl, out, acts, mode = make_controller(stick_mouse="both")
        mode.mouse = True
        ctl.axis("lx", 1.0, 0)
        self.assertTrue(ctl.needs_fast_tick())
        hold_until(ctl, 0, 1.0, step=0.008)
        self.assertGreater(out.dx, 1000)
        self.assertLess(out.dx, 1600)
        self.assertEqual(out.dy, 0)

    def test_stick_deadzone(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.axis("lx", 0.08, 0)
        ctl.axis("ly", -0.05, 0)
        self.assertFalse(ctl.needs_fast_tick())
        hold_until(ctl, 0, 1.0, step=0.008)
        self.assertEqual(out.log, [])

    def test_stick_small_deflection_is_slow(self):
        ctl, out, acts, mode = make_controller(stick_mouse="both")
        mode.mouse = True
        ctl.axis("lx", 0.3, 0)
        hold_until(ctl, 0, 1.0, step=0.008)
        self.assertGreater(out.dx, 10)
        self.assertLess(out.dx, 150)

    def test_right_stick_scrolls(self):
        ctl, out, acts, mode = make_controller(stick_mouse="both")
        mode.mouse = True
        ctl.axis("ry", -1.0, 0)       # push up
        hold_until(ctl, 0, 0.5, step=0.008)
        self.assertGreater(out.vs, 600)
        self.assertEqual(out.dx, 0)

    def test_sticks_idle_when_mouse_off(self):
        ctl, out, acts, mode = make_controller()
        ctl.axis("lx", 1.0, 0)
        self.assertFalse(ctl.needs_fast_tick())
        hold_until(ctl, 0, 1.0)
        self.assertEqual(out.log, [])

    def test_alt_tab_confirm_does_not_click(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        press(ctl, "cross", 0.5)
        self.assertEqual(out.clicks(), [])
        self.assertFalse(ctl.alt_tab)
        press(ctl, "cross", 0.8)
        self.assertEqual(out.clicks(), [("left", True), ("left", False)])

    def test_alt_tab_releases_held_mouse_buttons(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("r2", True, 0)
        ctl.button("share", True, 0.1)
        press(ctl, "circle", 0.2)
        self.assertEqual(out.buttons, set())

    def test_reset_releases_everything(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        ctl.button("cross", True, 0)
        ctl.button("share", True, 0.1)
        press(ctl, "circle", 0.2)
        ctl.reset()
        self.assertEqual(out.keys, set())
        self.assertEqual(out.buttons, set())
        self.assertFalse(ctl.alt_tab)


class DpadRocker(unittest.TestCase):
    """A rocker d-pad reports diagonals and bounces; menus must step once."""

    def open_switcher(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        return ctl, out, acts

    def test_diagonal_while_pressing_right_is_one_step(self):
        ctl, out, acts = self.open_switcher()
        ctl.button("right", True, 0.50)
        ctl.button("down", True, 0.505)       # rocker tips into →↓
        ctl.button("down", False, 0.51)
        ctl.button("right", False, 0.60)
        self.assertEqual(acts.switches, ["open", "next"])
        self.assertEqual(out.taps(e.KEY_TAB), 2, "open + one step")

    def test_bounce_is_one_step(self):
        ctl, out, acts = self.open_switcher()
        ctl.button("right", True, 0.50)
        ctl.button("right", False, 0.52)
        ctl.button("right", True, 0.53)       # contact bounce
        ctl.button("right", False, 0.60)
        self.assertEqual(acts.switches, ["open", "next"])

    def test_separate_presses_still_step(self):
        ctl, out, acts = self.open_switcher()
        for t in (0.5, 0.8, 1.1):
            ctl.button("right", True, t)
            ctl.button("right", False, t + 0.08)
        ctl.button("left", True, 1.4)
        ctl.button("left", False, 1.45)
        self.assertEqual(acts.switches, ["open", "next", "next", "next", "back"])

    def test_wheel_diagonal_is_one_detent(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        ctl.button("right", True, 0.3)
        ctl.button("down", True, 0.305)
        ctl.button("down", False, 0.31)
        ctl.button("right", False, 0.4)
        self.assertEqual([e for e, i in acts.wheel_events if e == "select"], ["select"])


class SwitcherGone(unittest.TestCase):
    def test_kwin_closing_the_switcher_releases_alt(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        press(ctl, "circle", 0.1)
        ctl.button("share", False, 0.2)
        self.assertIn(e.KEY_LEFTALT, out.keys)
        ctl.switcher_gone()
        self.assertNotIn(e.KEY_LEFTALT, out.keys)
        self.assertFalse(ctl.alt_tab)
        self.assertEqual(out.taps(e.KEY_ESC), 0, "nothing else is sent")
        self.assertEqual(acts.switches[-1], True, "reported as cancelled")
        ctl.switcher_gone()                    # harmless twice
        press(ctl, "right", 0.5)               # d-pad is free again
        self.assertEqual(out.taps(e.KEY_TAB), 1)


if __name__ == "__main__":
    unittest.main()
