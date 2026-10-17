import os
import struct
import unittest
import zlib

from couchpad import lights
from couchpad.config import Config


def make(**cfg):
    writes = []
    c = Config(**cfg)
    bat = {"v": (80, "Discharging")}
    lb = lights.Lights(c, writer=lambda kind, v: writes.append((kind, v)),
                       battery=lambda: bat["v"], led_dir="/fake")
    return lb, c, writes, bat


def rgb(writes):
    vals = [v for k, v in writes if k == "multi_intensity"]
    return tuple(int(x) for x in vals[-1].split()) if vals else None


class Colors(unittest.TestCase):
    def test_hex(self):
        self.assertEqual(lights.hex_rgb("#ff8000"), (255, 128, 0))
        self.assertEqual(lights.hex_rgb("junk"), (30, 107, 255))
        self.assertEqual(lights.rgb_hex((255, 128.4, -3)), "#ff8000")

    def test_battery_gradient(self):
        r, g, b = lights.battery_color(10)
        self.assertGreater(r, 200)
        self.assertLess(g, 30)
        r, g, b = lights.battery_color(90)
        self.assertGreater(g, 200)
        self.assertLess(r, 30)


class Modes(unittest.TestCase):
    def test_static_scaled_by_brightness(self):
        lb, c, w, _ = make(light_mode="static", light_color="#ff0000", light_brightness=1.0)
        lb.tick(0)
        self.assertEqual(rgb(w), (255, 0, 0))
        c.light_brightness = 0.5
        lb.tick(1)
        self.assertEqual(rgb(w), (64, 0, 0), "perceptual curve: 0.5 -> 25 %")

    def test_writes_only_on_change(self):
        lb, c, w, _ = make(light_mode="static")
        lb.tick(0)
        lb.tick(0.1)
        lb.tick(0.2)
        self.assertEqual(sum(1 for k, _ in w if k == "multi_intensity"), 1)
        lb.tick(lights.KEEP_EVERY + 1)
        self.assertEqual(sum(1 for k, _ in w if k == "multi_intensity"), 2, "re-asserted")

    def test_off_and_steam(self):
        lb, c, w, _ = make(light_mode="off")
        lb.tick(0)
        self.assertEqual(rgb(w), (0, 0, 0))
        lb, c, w, _ = make(light_mode="steam")
        lb.tick(0)
        self.assertIsNone(rgb(w), "steam mode never writes")
        self.assertFalse(lb.animating(0))

    def test_breathe_varies_and_animates(self):
        lb, c, w, _ = make(light_mode="breathe", light_color="#00ff00", light_brightness=1)
        self.assertTrue(lb.animating(0))
        seen = set()
        for i in range(40):
            lb.tick(i * 0.1)
            seen.add(rgb(w)[1])
        self.assertGreater(max(seen) - min(seen), 150)

    def test_rainbow_cycles(self):
        lb, c, w, _ = make(light_mode="rainbow", light_brightness=1)
        colors = set()
        for i in range(12):
            lb.tick(i)
            colors.add(rgb(w))
        self.assertGreater(len(colors), 8)

    def test_battery_mode(self):
        lb, c, w, bat = make(light_mode="battery", light_brightness=1)
        lb.tick(0)
        r, g, b = rgb(w)
        self.assertGreater(g, r)
        self.assertFalse(lb.animating(1))
        bat["v"] = (15, "Charging")
        lb.bat_t = -1e9
        self.assertTrue(lb.animating(100), "charging pulses")

    def test_mouse_color_overrides(self):
        lb, c, w, _ = make(light_mode="rainbow", light_mouse_color="#ffffff", light_brightness=1)
        lb.set_mouse(True)
        lb.tick(0)
        self.assertEqual(rgb(w), (255, 255, 255))
        self.assertFalse(lb.animating(0), "solid while in mouse mode")

    def test_mouse_color_empty_keeps_mode(self):
        lb, c, w, _ = make(light_mode="static", light_color="#0000ff", light_mouse_color="",
                           light_brightness=1)
        lb.set_mouse(True)
        lb.tick(0)
        self.assertEqual(rgb(w), (0, 0, 255))

    def test_flash_fades(self):
        lb, c, w, _ = make(light_mode="static", light_color="#000000", light_brightness=1)
        lb.tick(0)
        lb.flash("#ff0000", 10.0)
        self.assertTrue(lb.animating(10.1))
        lb.tick(10.0)
        self.assertGreater(rgb(w)[0], 200)
        lb.tick(10.0 + lights.FLASH_TIME + 0.01)
        self.assertEqual(rgb(w), (0, 0, 0))

    def test_flash_disabled(self):
        lb, c, w, _ = make(light_mode="static", light_color="#000000", light_flash=False)
        lb.flash("#ff0000", 0)
        lb.tick(0)
        self.assertEqual(rgb(w), (0, 0, 0))

    def test_preview(self):
        lb, c, w, _ = make(light_mode="static", light_color="#000000", light_brightness=1)
        lb.show_preview("#00ff00", 0, seconds=2)
        lb.tick(1)
        self.assertEqual(rgb(w), (0, 255, 0))
        lb.tick(3)
        self.assertEqual(rgb(w), (0, 0, 0))


class PlayerLeds(unittest.TestCase):
    def hid(self, w):
        return [v for k, v in w if k == "hid"]

    def test_auto_sends_nothing(self):
        lb, c, w, _ = make()
        lb.tick(0)
        self.assertEqual(self.hid(w), [])

    def test_battery_leds(self):
        lb, c, w, _ = make(player_leds="battery")
        lb.tick(0)
        rep = self.hid(w)[-1]
        self.assertEqual(rep[3 + 43] & 0x1F, lights.BATTERY_LEDS[4])     # 80 %
        lb.tick(1)
        self.assertEqual(len(self.hid(w)), 1, "unchanged -> not resent")

    def test_mouse_leds_and_mic(self):
        lb, c, w, _ = make(player_leds="mouse", mic_led="mouse")
        lb.tick(0)
        lb.set_mouse(True)
        lb.tick(1)
        rep = self.hid(w)[-1]
        self.assertEqual(rep[3 + 43] & 0x1F, 0x04)
        self.assertEqual(rep[3 + 8], 1)
        self.assertEqual(rep[3 + 1], lights.VALID1_PLAYER_LEDS | lights.VALID1_MIC_LED)


class Report(unittest.TestCase):
    def test_bt_report(self):
        r = lights.build_led_report(True, player=0x04, mic=None, seq=3)
        self.assertEqual(len(r), 78)
        self.assertEqual(r[0], 0x31)
        self.assertEqual(r[1], 0x30)
        self.assertEqual(r[2], 0x10, "tag")
        self.assertEqual(r[3], 0, "no rumble flags")
        self.assertEqual(r[4], lights.VALID1_PLAYER_LEDS)
        self.assertEqual(r[3 + 43], 0x04 | lights.PLAYER_LED_INSTANT)
        self.assertEqual(struct.unpack("<I", r[-4:])[0], zlib.crc32(b"\xa2" + r[:-4]))

    def test_usb_report(self):
        r = lights.build_led_report(False, player=None, mic=True)
        self.assertEqual(len(r), 48)
        self.assertEqual(r[0], 0x02)
        self.assertEqual(r[2], lights.VALID1_MIC_LED)
        self.assertEqual(r[1 + 8], 1)


class Retry(unittest.TestCase):
    def test_permission_error_retries(self):
        import tempfile
        d = tempfile.mkdtemp()
        for n in ("brightness", "multi_intensity"):
            open(os.path.join(d, n), "w").close()
            os.chmod(os.path.join(d, n), 0o444)
        lb = lights.Lights(Config(light_mode="static", light_color="#ff0000", light_brightness=1),
                           led_dir=d)
        if os.access(os.path.join(d, "brightness"), os.W_OK):
            self.skipTest("running as root")
        lb.tick(0)
        self.assertFalse(lb.failed, "not permanent")
        self.assertEqual(lb.retry_at, 2.0)
        for n in ("brightness", "multi_intensity"):
            os.chmod(os.path.join(d, n), 0o644)
        lb.tick(1)                        # still waiting
        with open(os.path.join(d, "multi_intensity")) as f:
            self.assertEqual(f.read(), "")
        lb.tick(2.5)
        with open(os.path.join(d, "multi_intensity")) as f:
            self.assertEqual(f.read(), "255 0 0")


if __name__ == "__main__":
    unittest.main()
