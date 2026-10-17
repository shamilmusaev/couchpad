import os
import tempfile
import unittest

from couchpad import hidraw
from fakes import make_touchpad


def report(points=(None, None), click=False, usb=False):
    common = bytearray(70)
    common[0:4] = bytes([130, 125, 127, 123])
    common[7] = 0x08                    # d-pad neutral
    if click:
        common[9] |= hidraw.PAD_CLICK
    for i, pt in enumerate(points):
        o = hidraw.TOUCH_OFFSET + 4 * i
        if pt is None:
            common[o] = 0x80
        else:
            tid, x, y = pt
            common[o] = tid & 0x7F
            common[o + 1] = x & 0xFF
            common[o + 2] = ((x >> 8) & 0x0F) | ((y & 0x0F) << 4)
            common[o + 3] = (y >> 4) & 0xFF
    if usb:
        return bytes([0x01]) + bytes(common[:63])
    return bytes([0x31, 0x10]) + bytes(common[:76])


class Parse(unittest.TestCase):
    def test_idle_report_from_real_controller(self):
        # captured from the user's DualSense over Bluetooth
        r = bytearray(78)
        r[0], r[2:6] = 0x31, bytes([130, 125, 127, 123])
        r[9] = 0x08
        r[34] = r[38] = 0x80
        self.assertEqual(hidraw.parse(bytes(r)), ([None, None], False))

    def test_coordinates_roundtrip_extremes(self):
        for x, y in ((0, 0), (1919, 1079), (1000, 517), (255, 256)):
            pts, click = hidraw.parse(report(((5, x, y), None)))
            self.assertEqual(pts[0], (5, x, y))

    def test_click_and_usb(self):
        pts, click = hidraw.parse(report(((1, 10, 20), (2, 30, 40)), click=True, usb=True))
        self.assertTrue(click)
        self.assertEqual(pts, [(1, 10, 20), (2, 30, 40)])

    def test_garbage(self):
        self.assertIsNone(hidraw.parse(b""))
        self.assertIsNone(hidraw.parse(b"\x31\x00\x01"))
        self.assertIsNone(hidraw.parse(bytes([0x05]) + bytes(80)))


class FeedEngine(unittest.TestCase):
    def setUp(self):
        self.tp, self.out, self.mode = make_touchpad()
        self.h = hidraw.HidrawTouch(self.tp)
        self.t = 0.0

    def feed(self, *a, **k):
        self.t += 0.004
        self.h.feed(report(*a, **k), self.t)

    def test_swipe_moves_pointer(self):
        for i in range(40):
            self.feed(((7, 500 + i * 10, 500), None))
        self.feed()
        self.assertGreater(self.out.dx, 100)
        self.assertEqual(self.out.dy, 0)
        self.assertEqual(self.out.clicks(), [])

    def test_duplicate_reports_ignored(self):
        self.feed(((7, 500, 500), None))
        for _ in range(50):
            self.feed(((7, 500, 500), None))
        self.assertEqual(self.out.log, [])

    def test_tap(self):
        self.feed(((3, 800, 400), None))
        self.t += 0.05
        self.feed()
        self.assertEqual(self.out.clicks(), [("left", True), ("left", False)])

    def test_new_touch_id_no_jump(self):
        self.feed(((3, 100, 100), None))
        self.feed(((3, 100, 100), None))
        self.feed(((4, 1800, 1000), None))   # new finger, same report slot
        self.feed(((4, 1800, 1000), None))
        self.assertEqual((self.out.dx, self.out.dy), (0, 0))

    def test_physical_click_drag(self):
        self.feed(((3, 800, 400), None))
        self.feed(((3, 800, 400), None), click=True)
        self.assertEqual(self.out.buttons, {"left"})
        for i in range(20):
            self.feed(((3, 800 + i * 10, 400), None), click=True)
        self.feed(((3, 1000, 400), None), click=False)
        self.assertEqual(self.out.buttons, set())
        self.assertGreater(self.out.dx, 30)

    def test_two_finger_scroll(self):
        for i in range(30):
            self.feed(((1, 600, 700 - i * 10), (2, 1000, 700 - i * 10)))
        self.feed()
        self.assertLess(self.out.vs, -200)
        self.assertEqual(self.out.dx, 0)


class Sysfs(unittest.TestCase):
    def test_lookup(self):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/hidraw/hidraw6")
        os.makedirs(f"{d}/input/input34/event256")
        os.makedirs(f"{d}/input/input32/event30")
        with open(f"{d}/input/input34/name", "w") as f:
            f.write("DualSense Wireless Controller Touchpad\n")
        with open(f"{d}/input/input32/name", "w") as f:
            f.write("DualSense Wireless Controller\n")
        self.assertEqual(hidraw.hidraw_node(d), "/dev/hidraw6")
        self.assertEqual(hidraw.touchpad_sysname(d), "event256")
        self.assertIsNone(hidraw.hidraw_node("/nonexistent"))


if __name__ == "__main__":
    unittest.main()
