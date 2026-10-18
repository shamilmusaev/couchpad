import struct
import threading
import time
import unittest

from couchpad import hdhaptics as hd
from fakes import make_controller


def saxense_crc32(data):
    """Bit-by-bit CRC from SAxense.c (seed ~0xEADA2D49 = the 0xA2 byte)."""
    crc = ~0xEADA2D49 & 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1) & 0xFFFFFFFF)
    return ~crc & 0xFFFFFFFF


class Report(unittest.TestCase):
    def test_layout(self):
        frames = bytes(range(64))
        r = hd.build_report(frames, 7)
        self.assertEqual(len(r), 142, "report id + 141 bytes, as the HID descriptor says")
        self.assertEqual(r[0], 0x32)
        self.assertEqual(r[1], 0x00)
        self.assertEqual(r[2:4], bytes((0x91, 7)))
        self.assertEqual(r[4:11], bytes((0xFE, 0, 0, 0, 0, 0xFF, 7)))
        self.assertEqual(r[11:13], bytes((0x92, 64)))
        self.assertEqual(r[13:77], frames)
        self.assertEqual(r[77:138], bytes(61))

    def test_crc_matches_saxense(self):
        for counter in (0, 1, 200):
            r = hd.build_report(bytes((i * 7) & 0xFF for i in range(64)), counter)
            self.assertEqual(struct.unpack("<I", r[-4:])[0], saxense_crc32(r[:-4]))

    def test_counter_wraps(self):
        self.assertEqual(hd.build_report(bytes(64), 0x1FF)[10], 0xFF)


class Arm(unittest.TestCase):
    def test_layout(self):
        r = hd.build_arm_report(5)
        self.assertEqual(len(r), 78)
        self.assertEqual(r[0], 0x31)
        self.assertEqual(r[1], 0x50)
        self.assertEqual(r[2], 0x10, "tag byte before the common block")
        c = r[3:]
        self.assertEqual(c[0], 0, "no rumble flags: they leave audio-haptics mode")
        self.assertEqual(c[1], 0x02 | 0x20 | 0x40)
        self.assertEqual(c[2:4], bytes(2), "motors untouched")
        self.assertEqual(c[36], 0, "no motor power reduction")
        self.assertEqual(c[39], 1, "haptic low-pass filter on")
        self.assertEqual(c[38], 0, "lights untouched")
        self.assertEqual(c[40:45], bytes(5))

    def test_crc(self):
        r = hd.build_arm_report()
        self.assertEqual(struct.unpack("<I", r[-4:])[0], saxense_crc32(r[:-4]))


class Waveforms(unittest.TestCase):
    def test_library_sane(self):
        lib = hd.library()
        for name in ("tick", "progress1", "progress2", "progress3", "fire", "cancel",
                     "on", "off", "open", "detent", "step", "launch", "confirm"):
            w = lib[name]
            self.assertTrue(w, name)
            self.assertLessEqual(max(abs(v) for v in w), 1.0 + 1e-9, name)
            self.assertLess(len(w) / hd.RATE, 0.2, f"{name} too long")
            self.assertLess(abs(w[0]), 0.05, f"{name} starts with a hard edge")
            self.assertLess(abs(w[-1]), 0.05, f"{name} ends with a hard edge")

    def test_progress_rises(self):
        lib = hd.library()
        peaks = [max(abs(v) for v in lib[f"progress{i}"]) for i in (1, 2, 3)]
        self.assertEqual(peaks, sorted(peaks))

    def test_pan(self):
        self.assertEqual(hd.pan_gains(0), (1.0, 1.0))
        l, r = hd.pan_gains(1)
        self.assertGreater(r, l)
        self.assertEqual(r, 1.0)
        l, r = hd.pan_gains(-1)
        self.assertGreater(l, r)
        self.assertEqual(hd.pan_gains(5), hd.pan_gains(1))

    def test_int8(self):
        self.assertEqual(hd.to_int8(0), 0)
        self.assertEqual(hd.to_int8(1), 127)
        self.assertEqual(hd.to_int8(-1), 0x81)
        self.assertEqual(hd.to_int8(3), 127, "clipped, never wraps")


class Streaming(unittest.TestCase):
    def setUp(self):
        self.reports = []
        self.lock = threading.Lock()

        def writer(r):
            with self.lock:
                self.reports.append((time.monotonic(), r))
        self.h = hd.HDHaptics("/nonexistent", writer=writer)
        self.addCleanup(self.h.close)

    def wait_idle(self, timeout=2):
        end = time.time() + timeout
        last = -1
        while time.time() < end:
            time.sleep(0.1)
            with self.lock:
                n = len(self.reports)
            if n == last:
                return
            last = n

    def hd(self):
        return [(t, r) for t, r in self.reports if r[0] == 0x32]

    def samples(self):
        out = []
        for _, r in self.hd():
            fr = r[13:77]
            out += [(int.from_bytes(fr[i:i + 1], "big", signed=True),
                     int.from_bytes(fr[i + 1:i + 2], "big", signed=True))
                    for i in range(0, 64, 2)]
        return out

    def test_idle_sends_nothing(self):
        time.sleep(0.2)
        self.assertEqual(self.reports, [])

    def test_every_burst_starts_by_arming_audio_haptics(self):
        self.h.play("tick")
        self.wait_idle()
        self.h.play("tick")
        self.wait_idle()
        kinds = [r[0] for _, r in self.reports]
        self.assertEqual(kinds[0], 0x31)
        self.assertEqual(kinds.count(0x31), 2, "re-armed for each burst")
        second = kinds.index(0x31, 1)
        self.assertTrue(all(k == 0x32 for k in kinds[1:second]))

    def test_click_is_wrapped_in_silence(self):
        self.assertTrue(self.h.play("detent"))
        self.wait_idle()
        s = self.samples()
        self.assertTrue(all(v == (0, 0) for v in s[:hd.PREROLL * hd.FRAMES]), "pre-roll")
        self.assertTrue(all(v == (0, 0) for v in s[-hd.TAIL * hd.FRAMES:]), "tail")
        self.assertTrue(any(v != (0, 0) for v in s))
        n = len(self.hd())
        self.assertLessEqual(n, hd.PREROLL + 2 + hd.TAIL + 1)

    def test_paced_at_3khz(self):
        self.h.play("open")
        self.wait_idle()
        times = [t for t, _ in self.hd()]
        span = times[-1] - times[0]
        expected = (len(times) - 1) * hd.PERIOD
        self.assertAlmostEqual(span, expected, delta=0.02)

    def test_counter_increments(self):
        self.h.play("fire")
        self.wait_idle()
        counters = [r[10] for _, r in self.hd()]
        self.assertEqual(counters, list(range(len(counters))))

    def test_pan_right(self):
        self.h.play("step", pan=1.0)
        self.wait_idle()
        s = self.samples()
        left = max(abs(a) for a, b in s)
        right = max(abs(b) for a, b in s)
        self.assertGreater(right, left * 2)

    def test_overlapping_clicks_mix(self):
        self.h.play("detent")
        self.h.play("detent")
        self.wait_idle()
        peak = max(abs(a) for a, b in self.samples())
        self.assertGreater(peak, 0.5 * 127 * 1.5, "two clicks add up")

    def test_second_click_never_lands_in_lead_in(self):
        self.h.play("detent")
        self.h.play("tick")
        self.wait_idle()
        s = self.samples()
        self.assertTrue(all(v == (0, 0) for v in s[:hd.PREROLL * hd.FRAMES]))

    def test_strength(self):
        self.h.strength = 0.5
        self.h.play("launch")
        self.wait_idle()
        self.assertLess(max(abs(a) for a, b in self.samples()), 70)

    def test_unknown_or_zero_strength(self):
        self.assertFalse(self.h.play("nope"))
        self.h.strength = 0
        self.assertFalse(self.h.play("tick"))

    def test_write_error_disables_and_falls_back(self):
        def boom(r):
            raise OSError("gone")
        h = hd.HDHaptics("/x", writer=boom)
        self.addCleanup(h.close)
        self.assertTrue(h.play("tick"))
        time.sleep(0.2)
        self.assertTrue(h.failed)
        self.assertFalse(h.play("tick"), "caller falls back to rumble")


class EngineClicks(unittest.TestCase):
    def test_switcher_clicks(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.1)
        ctl.button("circle", False, 0.2)
        ctl.button("share", False, 0.3)
        ctl.button("right", True, 0.5)
        ctl.button("right", False, 0.55)
        ctl.button("left", True, 0.6)
        ctl.button("left", False, 0.65)
        ctl.button("cross", True, 0.8)
        kinds = [k for k in acts.fb if k not in ("tick",)]
        self.assertEqual(kinds, ["open", "step", "step", "confirm"])
        steps = [p for k, p in zip(acts.fb, acts.pans) if k == "step"]
        self.assertGreater(steps[0], 0, "Tab = right side")
        self.assertLess(steps[1], 0, "Shift+Tab = left side")

    def test_switcher_cancel_click(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("circle", True, 0.1)
        ctl.button("circle", False, 0.2)
        ctl.button("share", False, 0.3)
        ctl.button("circle", True, 0.5)
        self.assertEqual(acts.fb[-1], "cancel")

    def test_wheel_detent_panned_to_sector(self):
        ctl, out, acts, mode = make_controller()      # 6 items
        ctl.button("share", True, 0)
        ctl.button("r1", True, 0.05)
        ctl.axis("rx", 1.0, 0.2)                      # right -> sector 2 (120 deg)
        ctl.axis("rx", -1.0, 0.3)                     # left -> sector 5 (300 deg)
        pans = [p for k, p in zip(acts.fb, acts.pans) if k == "detent"]
        self.assertGreater(pans[0], 0.5)
        self.assertLess(pans[1], -0.5)

    def test_volume_ticks(self):
        ctl, out, acts, mode = make_controller()
        ctl.button("share", True, 0)
        ctl.button("up", True, 0.1)
        t = 0.1
        while t < 1.0:
            ctl.tick(t)
            t += 0.01
        self.assertEqual(acts.fb.count("detent"), acts.ran.count("volume_up"))


class Descriptor(unittest.TestCase):
    def test_sizes_match_the_controllers_hid_descriptor(self):
        """Output report sizes from a real DualSense (Bluetooth) descriptor."""
        import os
        path = os.path.join(os.path.dirname(__file__), "data", "dualsense_bt.rdesc")
        with open(path, "rb") as f:
            d = f.read()
        sizes, i, rid, size, count = {}, 0, None, 0, 0
        while i < len(d):
            b = d[i]
            n = (0, 1, 2, 4)[b & 3]
            tag, val = b & 0xFC, int.from_bytes(d[i + 1:i + 1 + n], "little")
            i += 1 + n
            if tag == 0x84:
                rid = val
            elif tag == 0x74:
                size = val
            elif tag == 0x94:
                count = val
            elif tag == 0x90:                      # Output item
                sizes[rid] = size * count // 8
        self.assertEqual(len(hd.build_report(bytes(64), 0)), 1 + sizes[0x32])
        self.assertEqual(len(hd.build_arm_report()), 1 + sizes[0x31])
        from couchpad import lights
        self.assertEqual(len(lights.build_led_report(True, player=1)), 1 + sizes[0x31])


if __name__ == "__main__":
    unittest.main()
