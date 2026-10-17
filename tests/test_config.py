import os
import tempfile
import tomllib
import unittest

from couchpad import config


class ConfigTests(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_missing_file_gives_defaults(self):
        cfg = config.load("/nonexistent/couchpad.toml")
        self.assertEqual(cfg.long_press, 1.5)
        self.assertTrue(cfg.grab_touchpad)

    def test_overrides_and_types(self):
        cfg = config.load(self.write("long_press = 2\npointer_speed = 1.5\n"
                                     "natural_scroll = false\nkeyboard = 'plasma'\n"))
        self.assertEqual(cfg.long_press, 2.0)
        self.assertIsInstance(cfg.long_press, float)
        self.assertEqual(cfg.pointer_speed, 1.5)
        self.assertFalse(cfg.natural_scroll)
        self.assertEqual(cfg.keyboard, "plasma")

    def test_bad_values_ignored(self):
        cfg = config.load(self.write("long_press = 'abc'\nkeyboard = 'nope'\nfoo = 1\n"))
        self.assertEqual(cfg.long_press, 1.5)
        self.assertEqual(cfg.keyboard, "auto")
        self.assertEqual(cfg.extra, {"foo": 1})

    def test_default_file_is_valid_and_matches_defaults(self):
        data = tomllib.loads(config.DEFAULT_FILE)
        defaults = config.Config()
        for key, value in data.items():
            self.assertEqual(getattr(defaults, key), value, key)


class SaveTests(unittest.TestCase):
    def test_roundtrip(self):
        fd, path = tempfile.mkstemp(suffix=".toml")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        cfg = config.Config(long_press=2.5, light_mode="rainbow", light_color="#abcdef",
                            natural_scroll=False, chords={"square": "mute"},
                            wheel=[{"app": "hydra"}, {"name": 'Big "P"', "open": "steam://x"}])
        cfg.extra["future_key"] = 3
        config.save(cfg, path)
        back = config.load(path)
        self.assertEqual(back.long_press, 2.5)
        self.assertEqual(back.light_mode, "rainbow")
        self.assertEqual(back.light_color, "#abcdef")
        self.assertFalse(back.natural_scroll)
        self.assertEqual(back.chords, {"square": "mute"})
        self.assertEqual(back.wheel, cfg.wheel)
        self.assertEqual(back.extra, {"future_key": 3}, "unknown keys survive a save")

    def test_validation(self):
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w") as f:
            f.write('light_mode = "disco"\nlight_color = "red"\nlight_brightness = 7\n'
                    'player_leds = "x"\nchords = 5\nwheel = "nope"\nidle_off = -3\n')
        self.addCleanup(os.unlink, path)
        cfg = config.load(path)
        d = config.Config()
        self.assertEqual(cfg.light_mode, d.light_mode)
        self.assertEqual(cfg.light_color, d.light_color)
        self.assertEqual(cfg.light_brightness, 1.0)
        self.assertEqual(cfg.player_leds, "auto")
        self.assertEqual(cfg.chords, {})
        self.assertEqual(cfg.wheel, [])
        self.assertEqual(cfg.idle_off, 0.0)

    def test_save_is_atomic_and_creates_dirs(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "sub", "config.toml")
        config.save(config.Config(), path)
        self.assertTrue(os.path.exists(path))
        self.assertEqual([n for n in os.listdir(os.path.dirname(path))], ["config.toml"])


if __name__ == "__main__":
    unittest.main()
