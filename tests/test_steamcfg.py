import os
import shutil
import tempfile
import unittest

from couchpad import steamcfg

DATA = os.path.join(os.path.dirname(__file__), "data", "desktop_ps5.vdf")


class SteamDesktopLayout(unittest.TestCase):
    def setUp(self):
        self.steam = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.steam)
        d = os.path.join(self.steam, "steamapps", "common", "Steam Controller Configs",
                         "123", "config", "413080")
        os.makedirs(d)
        self.dev = os.path.join(d, "DS0102030405ab.vdf")
        self.tpl = os.path.join(d, "controller_ps5.vdf")
        self.other = os.path.join(d, "controller_neptune.vdf")
        for p in (self.dev, self.tpl, self.other):
            shutil.copy(DATA, p)
        with open(DATA) as f:
            self.original = f.read()

    def read(self, p):
        with open(p) as f:
            return f.read()

    def test_fixture_has_bindings(self):
        self.assertIn('key_press ESCAPE', self.original)
        self.assertIn('mouse_button LEFT', self.original)

    def test_neutralize_strips_only_bindings(self):
        changed = steamcfg.neutralize(self.steam)
        self.assertEqual(sorted(changed), sorted([self.dev, self.tpl]))
        text = self.read(self.dev)
        self.assertNotIn('"binding"', text)
        self.assertIn(steamcfg.MARK, text)
        self.assertEqual(text.count("{"), text.count("}"))
        self.assertEqual(text.count("{"), self.original.count("{"))
        self.assertIn('"controller_type"\t\t"controller_ps5"', text)
        # absolute_mouse / joystick_mouse groups move the cursor on their
        # own, so no group may stay active.
        self.assertNotIn("active", text)
        self.assertIn('"mode"\t\t"absolute_mouse"', text, "groups kept, just inactive")
        self.assertEqual(self.read(self.other), self.original, "Steam Deck layout untouched")

    def test_idempotent_and_backup_kept(self):
        steamcfg.neutralize(self.steam)
        self.assertEqual(steamcfg.neutralize(self.steam), [])
        self.assertEqual(self.read(self.dev + steamcfg.BACKUP_SUFFIX), self.original)

    def test_restore(self):
        steamcfg.neutralize(self.steam)
        restored = steamcfg.restore(self.steam)
        self.assertEqual(sorted(restored), sorted([self.dev, self.tpl]))
        self.assertEqual(self.read(self.dev), self.original)
        self.assertFalse(os.path.exists(self.dev + steamcfg.BACKUP_SUFFIX))

    def test_upgrades_v1_neutral_file(self):
        v1 = steamcfg.BINDING_RE.sub("", self.original).replace(
            '"description"\t\t"#SettingsController_AutosaveDescription"',
            '"description"\t\t"couchpad: neutral desktop layout"')
        shutil.copy(self.dev, self.dev + steamcfg.BACKUP_SUFFIX)
        with open(self.dev, "w") as f:
            f.write(v1)
        self.assertFalse(steamcfg.is_neutral(v1))
        steamcfg.neutralize(self.steam)
        self.assertTrue(steamcfg.is_neutral(self.read(self.dev)))
        self.assertEqual(self.read(self.dev + steamcfg.BACKUP_SUFFIX), self.original)

    def test_status(self):
        self.assertEqual(set(steamcfg.status(self.steam).values()), {False})
        steamcfg.neutralize(self.steam)
        self.assertEqual(set(steamcfg.status(self.steam).values()), {True})

    def test_steam_rewrote_file_gets_new_backup_not_overwritten(self):
        steamcfg.neutralize(self.steam)
        with open(self.dev, "w") as f:          # Steam regenerated defaults
            f.write(self.original)
        steamcfg.neutralize(self.steam)
        self.assertEqual(self.read(self.dev + steamcfg.BACKUP_SUFFIX), self.original)
        self.assertTrue(steamcfg.is_neutral(self.read(self.dev)))


if __name__ == "__main__":
    unittest.main()
