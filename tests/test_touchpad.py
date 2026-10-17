import unittest

from fakes import Finger, make_touchpad


class Pointer(unittest.TestCase):
    def test_move_right(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.swipe((500, 500), (900, 500), 40)
        f.frame(s0=None)
        self.assertGreater(out.dx, 100)
        self.assertEqual(out.dy, 0)

    def test_move_up_left(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.swipe((900, 800), (600, 500), 40)
        self.assertLess(out.dx, -50)
        self.assertLess(out.dy, -50)

    def test_no_jump_on_touch_down(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(100, 100))
        f.frame(s0=None)
        f.frame(s0=(1800, 1000))     # new touch far away
        f.frame(s0=(1800, 1000))
        self.assertEqual((out.dx, out.dy), (0, 0))

    def test_nothing_when_mouse_mode_off(self):
        tp, out, mode = make_touchpad()
        mode.mouse = False
        f = Finger(tp)
        f.swipe((500, 500), (900, 500), 40)
        f.frame(s0=None)
        f.frame(s0=(500, 500), click=True)
        f.frame(s0=(500, 500), click=False)
        f.frame(s0=None)
        self.assertEqual(out.log, [])

    def test_acceleration(self):
        slow_tp, slow, _ = make_touchpad()
        Finger(slow_tp).swipe((200, 500), (1200, 500), 250)   # ~1 s
        fast_tp, fast, _ = make_touchpad()
        Finger(fast_tp).swipe((200, 500), (1200, 500), 25)    # ~0.1 s
        self.assertGreater(fast.dx, slow.dx * 1.8)

    def test_no_accel_option_is_linear(self):
        a_tp, a, _ = make_touchpad(pointer_accel=0.0, pointer_smoothing=0.0)
        Finger(a_tp).swipe((200, 500), (1200, 500), 250)
        b_tp, b, _ = make_touchpad(pointer_accel=0.0, pointer_smoothing=0.0)
        Finger(b_tp).swipe((200, 500), (1200, 500), 25)
        self.assertAlmostEqual(a.dx, b.dx, delta=3)

    def test_speed_setting_scales(self):
        a_tp, a, _ = make_touchpad(pointer_speed=1.0)
        Finger(a_tp).swipe((200, 500), (1200, 500), 250)
        b_tp, b, _ = make_touchpad(pointer_speed=2.0)
        Finger(b_tp).swipe((200, 500), (1200, 500), 250)
        self.assertAlmostEqual(b.dx / a.dx, 2.0, delta=0.1)

    def test_tiny_moves_accumulate(self):
        tp, out, mode = make_touchpad(pointer_smoothing=0.0)
        f = Finger(tp)
        x = 500
        f.frame(s0=(x, 500))
        for _ in range(200):
            x += 1
            f.frame(dt=0.02, s0=(x, 500))
        # 200 units at the slow gain of 0.45 px/unit
        self.assertAlmostEqual(out.dx, 90, delta=3)

    def test_slow_precise_motion_is_never_lost(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.swipe((500, 500), (520, 500), 20, dt=0.03)
        self.assertGreaterEqual(out.dx, 6)

    def test_lifting_one_of_two_fingers_does_not_jump(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(500, 500), s1=(1500, 500))
        f.frame(s0=(500, 500), s1=(1500, 500))
        f.frame(s1=None)                      # s0 stays
        f.frame(s0=(500, 500))
        f.frame(s0=(500, 500))
        self.assertEqual((out.dx, out.dy), (0, 0))

    def test_new_tracking_id_on_same_slot_resets(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(100, 100))
        f.frame(s0=(100, 100))
        # Kernel reuses slot 0 with a new tracking id in a single frame.
        f.t += 0.004
        from evdev import ecodes as e
        tp.event(e.EV_ABS, e.ABS_MT_SLOT, 0, f.t)
        tp.event(e.EV_ABS, e.ABS_MT_TRACKING_ID, 99, f.t)
        tp.event(e.EV_ABS, e.ABS_MT_POSITION_X, 1700, f.t)
        tp.event(e.EV_ABS, e.ABS_MT_POSITION_Y, 900, f.t)
        tp.event(e.EV_SYN, e.SYN_REPORT, 0, f.t)
        f.frame(s0=(1700, 900))
        self.assertEqual((out.dx, out.dy), (0, 0))


class Taps(unittest.TestCase):
    def test_tap_left_click(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500))
        f.frame(dt=0.05, s0=(805, 502))
        f.frame(dt=0.05, s0=None)
        self.assertEqual(out.clicks(), [("left", True), ("left", False)])

    def test_two_finger_tap_right_click(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(600, 500), s1=(1000, 500))
        f.frame(dt=0.05, s0=(600, 500), s1=(1000, 500))
        f.frame(dt=0.03, s0=None, s1=None)
        self.assertEqual(out.clicks(), [("right", True), ("right", False)])

    def test_three_finger_tap_middle(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(400, 500), s1=(800, 500), s2=(1200, 500))
        f.frame(dt=0.05, s0=None, s1=None, s2=None)
        self.assertEqual(out.clicks(), [("middle", True), ("middle", False)])

    def test_long_touch_is_not_a_tap(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500))
        f.frame(dt=0.4, s0=(800, 500))
        f.frame(s0=None)
        self.assertEqual(out.clicks(), [])

    def test_swipe_is_not_a_tap(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.swipe((800, 500), (1000, 500), 10)
        f.frame(s0=None)
        self.assertEqual(out.clicks(), [])

    def test_tap_to_click_can_be_disabled(self):
        tp, out, mode = make_touchpad(tap_to_click=False)
        f = Finger(tp)
        f.frame(s0=(800, 500))
        f.frame(dt=0.05, s0=None)
        self.assertEqual(out.clicks(), [])


class PhysicalClick(unittest.TestCase):
    def test_click_and_drag(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500))
        f.frame(s0=(800, 500), click=True)
        self.assertEqual(out.buttons, {"left"})
        f.swipe((800, 500), (1100, 500), 30)
        self.assertGreater(out.dx, 50)
        self.assertEqual(out.buttons, {"left"}, "held during drag")
        f.frame(s0=(1100, 500), click=False)
        f.frame(s0=None)
        self.assertEqual(out.clicks(), [("left", True), ("left", False)],
                         "no extra tap click after a physical click")

    def test_quick_physical_click_no_double(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500), click=True)
        f.frame(dt=0.05, s0=(800, 500), click=False)
        f.frame(dt=0.02, s0=None)
        self.assertEqual(out.clicks(), [("left", True), ("left", False)])

    def test_two_finger_click_is_right(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(600, 500), s1=(1000, 500))
        f.frame(s0=(600, 500), s1=(1000, 500), click=True)
        f.frame(dt=0.3, s0=(600, 500), s1=(1000, 500), click=False)
        f.frame(s0=None, s1=None)
        self.assertEqual(out.clicks(), [("right", True), ("right", False)])

    def test_mode_off_while_clicked_releases(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500), click=True)
        mode.mouse = False
        f.frame(s0=(800, 500))
        self.assertEqual(out.buttons, set())

    def test_reset_releases(self):
        tp, out, mode = make_touchpad()
        f = Finger(tp)
        f.frame(s0=(800, 500), click=True)
        tp.reset()
        self.assertEqual(out.buttons, set())


class Scroll(unittest.TestCase):
    def two_finger(self, tp, dy=0, dx=0, steps=30):
        f = Finger(tp)
        for i in range(steps + 1):
            f.frame(s0=(600 + dx * i // steps, 600 + dy * i // steps),
                    s1=(1000 + dx * i // steps, 600 + dy * i // steps))
        f.frame(s0=None, s1=None)

    def test_natural_fingers_up_scrolls_down(self):
        tp, out, mode = make_touchpad(natural_scroll=True)
        self.two_finger(tp, dy=-300)
        self.assertLess(out.vs, -200)
        self.assertEqual(out.dx, 0, "no pointer motion while scrolling")
        self.assertEqual(out.dy, 0)
        self.assertEqual(out.clicks(), [], "a scroll is not a tap")

    def test_traditional_fingers_up_scrolls_up(self):
        tp, out, mode = make_touchpad(natural_scroll=False)
        self.two_finger(tp, dy=-300)
        self.assertGreater(out.vs, 200)

    def test_horizontal(self):
        tp, out, mode = make_touchpad(natural_scroll=True)
        self.two_finger(tp, dx=-300)
        self.assertGreater(out.hs, 200)

    def test_scroll_speed(self):
        a_tp, a, _ = make_touchpad(scroll_speed=1.0)
        self.two_finger(a_tp, dy=-300)
        b_tp, b, _ = make_touchpad(scroll_speed=2.0)
        self.two_finger(b_tp, dy=-300)
        self.assertAlmostEqual(b.vs / a.vs, 2.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
