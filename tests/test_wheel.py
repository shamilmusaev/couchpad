import os
import tempfile
import unittest

from couchpad import wheel
from fakes import make_controller


def hold_until(ctl, start, end, step=0.01):
    t = start
    while t <= end + 1e-9:
        ctl.tick(t)
        t += step


def open_wheel(ctl, t=0.0):
    ctl.button("share", True, t)
    ctl.button("r1", True, t + 0.05)
    hold_until(ctl, t + 0.05, t + 0.5)


class Gesture(unittest.TestCase):
    def test_quick_press_opens_wheel_no_screenshot(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        self.assertEqual(acts.wheel_events, [("open", None)], "opens immediately")
        ctl.button("r1", False, 0.1)
        ctl.button("share", False, 0.12)
        hold_until(ctl, 0.1, 1.0)
        self.assertEqual(acts.ran, [], "never a screenshot")
        self.assertTrue(mode.wheel, "quick press leaves the wheel open to pick")

    def test_share_l2_is_screenshot(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("l2", True, 0.05)
        ctl.button("l2", False, 0.1)
        ctl.button("share", False, 0.15)
        self.assertEqual(acts.ran, ["screenshot"])
        self.assertEqual(acts.wheel_events, [])

    def test_hold_opens_wheel(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        self.assertEqual(acts.wheel_events, [("open", None)])
        self.assertTrue(mode.wheel)
        self.assertEqual(acts.ran, [])

    def test_right_stick_selects_and_release_launches(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.axis("rx", 1.0, 0.6)          # right -> sector 1 of 6? 90deg / 60 = 1.5 -> 2
        ctl.axis("ry", 0.0, 0.6)
        ctl.axis("rx", 0.0, 0.7)          # stick back to centre keeps selection
        ctl.button("r1", False, 0.8)
        self.assertIn(("select", 2), acts.wheel_events)
        self.assertEqual(acts.wheel_events[-1], ("launch", 2))
        self.assertFalse(mode.wheel)
        self.assertEqual(acts.ran, [], "no screenshot after a wheel")

    def test_up_is_first_item(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.axis("ry", -1.0, 0.6)
        ctl.button("r1", False, 0.7)
        self.assertEqual(acts.wheel_events[-1], ("launch", 0))

    def test_left_stick_ignored(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.axis("lx", 1.0, 0.6)
        ctl.axis("ly", -1.0, 0.6)
        ctl.button("r1", False, 0.7)
        self.assertEqual(acts.wheel_events, [("open", None)])

    def test_release_without_selection_keeps_wheel_open(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.button("r1", False, 0.7)
        ctl.button("share", False, 0.75)
        self.assertTrue(mode.wheel, "stays open for mouse / stick + ✕")
        ctl.axis("rx", 1.0, 1.0)
        ctl.button("cross", True, 1.1)
        self.assertEqual(acts.wheel_events[-1], ("launch", 2))
        ctl.button("cross", False, 1.2)
        self.assertEqual(out.clicks(), [])

    def test_sticky_wheel_circle_closes(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.button("r1", False, 0.7)
        ctl.button("share", False, 0.75)
        ctl.button("circle", True, 1.0)
        ctl.button("circle", False, 1.1)
        self.assertFalse(mode.wheel)
        self.assertEqual(acts.wheel_events[-1], ("cancel", None))
        # pad is back to normal afterwards
        ctl.button("share", True, 2.0)
        ctl.button("share", False, 2.05)
        ctl.button("share", True, 2.2)
        ctl.button("share", False, 2.25)
        self.assertTrue(mode.mouse)

    def test_mouse_click_in_window_launches(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.button("r1", False, 0.7)
        ctl.wheel_external("select", 4)
        ctl.wheel_external("launch", 4)
        self.assertEqual(acts.wheel_events[-1], ("launch", 4))
        self.assertFalse(mode.wheel)

    def test_mouse_click_while_r1_held(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.wheel_external("launch", 1)
        ctl.button("r1", False, 0.8)
        ctl.button("share", False, 0.85)
        self.assertEqual([e for e in acts.wheel_events if e[0] == "launch"], [("launch", 1)])
        self.assertEqual(acts.ran, [], "no screenshot")

    def test_escape_in_window_cancels(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.button("r1", False, 0.7)
        ctl.wheel_external("cancel")
        self.assertFalse(mode.wheel)
        ctl.wheel_external("launch", 1)          # stale click: ignored
        self.assertNotIn(("launch", 1), acts.wheel_events)

    def test_touchpad_mouse_works_while_open(self):
        from fakes import Finger
        from couchpad.engine import Touchpad
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        tp = Touchpad(ctl.cfg, mode, out)
        open_wheel(ctl)
        Finger(tp).swipe((500, 500), (900, 500), 30)
        self.assertGreater(out.dx, 50)

    def test_circle_cancels_and_r1_release_is_swallowed(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        open_wheel(ctl)
        ctl.axis("rx", 1.0, 0.6)
        ctl.button("circle", True, 0.7)
        ctl.button("circle", False, 0.75)
        ctl.button("r1", False, 0.8)
        ctl.button("share", False, 0.85)
        self.assertEqual(acts.wheel_events[-1], ("cancel", None))
        self.assertEqual(acts.ran, [])
        self.assertEqual(out.clicks(), [], "circle must not right-click")

    def test_cross_launches(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.axis("ry", 1.0, 0.6)            # down -> item 3 of 6
        ctl.button("cross", True, 0.7)
        self.assertEqual(acts.wheel_events[-1], ("launch", 3))
        ctl.button("cross", False, 0.75)
        ctl.button("r1", False, 0.8)
        self.assertEqual([e for e in acts.wheel_events if e[0] == "launch"], [("launch", 3)])

    def test_dpad_steps(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        for t in (0.6, 0.7, 0.8):
            ctl.button("right", True, t)
            ctl.button("right", False, t + 0.02)
        ctl.button("left", True, 0.9)
        ctl.button("r1", False, 1.0)
        self.assertEqual(acts.wheel_events[-1], ("launch", 1))

    def test_share_released_first_still_works(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.button("share", False, 0.6)
        ctl.axis("rx", -1.0, 0.7)            # left -> 270deg -> item 5 of 6
        ctl.button("r1", False, 0.8)
        self.assertEqual(acts.wheel_events[-1], ("launch", 5))

    def test_share_released_early_wheel_still_works(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        ctl.button("share", False, 0.1)
        ctl.axis("rx", 1.0, 0.3)
        ctl.button("r1", False, 0.5)
        self.assertEqual(acts.wheel_events[-1], ("launch", 2))
        self.assertEqual(acts.ran, [])

    def test_no_pointer_or_scroll_while_open(self):
        ctl, out, acts, mode = make_controller()
        mode.mouse = True
        open_wheel(ctl)
        ctl.axis("rx", 1.0, 0.6)
        ctl.axis("lx", 1.0, 0.6)
        hold_until(ctl, 0.6, 1.2, step=0.008)
        self.assertEqual((out.dx, out.vs, out.hs), (0, 0, 0))

    def test_empty_wheel(self):
        ctl, out, acts, mode = make_controller()
        acts.wheel_n = 0
        open_wheel(ctl)
        self.assertFalse(mode.wheel)
        ctl.button("r1", False, 0.7)
        self.assertEqual(acts.ran, [])

    def test_wheel_ui_mouse_hit_test(self):
        from PySide6.QtCore import QPointF
        from couchpad.overlay_ui import Wheel
        from fakes import qt_app
        qt_app()
        w = Wheel()
        w.items = [{"name": str(i)} for i in range(8)]
        w.resize(1000, 1000)
        cx = cy = 500
        r = 1000 * 0.36 * 0.68
        self.assertEqual(w.sector_at(QPointF(cx, cy - r)), 0)
        self.assertEqual(w.sector_at(QPointF(cx + r, cy)), 2)
        self.assertEqual(w.sector_at(QPointF(cx, cy + r)), 4)
        self.assertIsNone(w.sector_at(QPointF(cx + 5, cy + 5)), "centre")
        self.assertIsNone(w.sector_at(QPointF(5, 5)), "far outside")
        got = []
        w.emit = got.append
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QEvent
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(cx + r, cy), QPointF(cx + r, cy),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        w.mousePressEvent(ev)
        self.assertEqual(got, [{"event": "launch", "i": 2}])

    def test_reset_closes_wheel(self):
        ctl, out, acts, mode = make_controller()
        open_wheel(ctl)
        ctl.reset()
        self.assertFalse(mode.wheel)
        self.assertEqual(acts.wheel_events[-1], ("cancel", None))


class Sector(unittest.TestCase):
    def test_directions_8(self):
        self.assertEqual(wheel.sector(0, -1, 8), 0)      # up
        self.assertEqual(wheel.sector(0.7, -0.7, 8), 1)
        self.assertEqual(wheel.sector(1, 0, 8), 2)       # right
        self.assertEqual(wheel.sector(0, 1, 8), 4)       # down
        self.assertEqual(wheel.sector(-1, 0, 8), 6)      # left
        self.assertEqual(wheel.sector(-0.7, -0.7, 8), 7)

    def test_deadzone_and_empty(self):
        self.assertIsNone(wheel.sector(0.2, 0.2, 8))
        self.assertIsNone(wheel.sector(1, 0, 0))

    def test_boundaries_wrap(self):
        self.assertEqual(wheel.sector(-0.1, -1, 4), 0)
        self.assertEqual(wheel.sector(0.1, -1, 4), 0)


class Items(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(os.path.join(self.dir, "hydra.desktop"), "w") as f:
            f.write("[Desktop Entry]\nName=Hydra\nIcon=/x/hydra\nExec=hydra\n"
                    "[Desktop Action new]\nName=Other\n")
        with open(os.path.join(self.dir, "ru.desktop"), "w") as f:
            f.write("[Desktop Entry]\nName=Files\nName[ru]=Файлы\nIcon=folder\n")

    def test_resolve(self):
        items = wheel.resolve([{"app": "hydra"}, {"app": "missing"}, {"app": "ru"},
                               {"name": "BP", "open": "steam://open/bigpicture"},
                               {"name": "nothing"}, "junk"], dirs=[self.dir])
        self.assertEqual([i["name"] for i in items], ["Hydra", "Файлы", "BP"])
        self.assertEqual(items[0]["icon"], "/x/hydra")

    def test_custom_name_wins(self):
        items = wheel.resolve([{"app": "hydra", "name": "Гидра"}], dirs=[self.dir])
        self.assertEqual(items[0]["name"], "Гидра")

    def test_max_items(self):
        items = wheel.resolve([{"exec": f"true {i}"} for i in range(12)], dirs=[self.dir])
        self.assertEqual(len(items), wheel.MAX_ITEMS)

    @unittest.skipUnless(wheel.find_desktop("hydra"), "Hydra not installed here")
    def test_default_set_on_this_machine(self):
        items = wheel.resolve([])
        names = [i["name"] for i in items]
        self.assertIn("Hydra", names)
        self.assertIn("Big Picture", names)

    def test_launch_argv(self):
        self.assertEqual(wheel.launch_argv({"app": "hydra"}), ["gtk-launch", "hydra"])
        self.assertEqual(wheel.launch_argv({"open": "https://x"}), ["xdg-open", "https://x"])
        self.assertEqual(wheel.launch_argv({"exec": "echo hi"}), ["sh", "-c", "echo hi"])

    def test_launch_detaches(self):
        calls = []
        wheel.launch({"app": "hydra", "name": "Hydra"},
                     popen=lambda argv, **kw: calls.append((argv, kw)))
        argv, kw = calls[0]
        self.assertTrue(kw["start_new_session"])


if __name__ == "__main__":
    unittest.main()
