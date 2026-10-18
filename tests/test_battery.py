import unittest

from couchpad.config import Config
from couchpad.daemon import Daemon
from fakes import FakeOut


class ChargeToasts(unittest.TestCase):
    def daemon(self):
        d = Daemon(Config(), dry=True, use_bus=False, out=FakeOut())
        got = []
        d.services.notify = lambda key, title, *a, **k: got.append(title)
        return d, got

    def test_cable_in_and_full(self):
        d, got = self.daemon()
        d._charge_change("pad", 60, "Discharging")       # state at connect: quiet
        self.assertEqual(got, [])
        d._charge_change("pad", 60, "Charging")
        d._charge_change("pad", 61, "Charging")          # no repeat while charging
        d._charge_change("pad", 100, "Full")
        self.assertEqual(len(got), 2, got)
        self.assertIn("60%", got[0])
        self.assertEqual(d.events[-2:], ["charging", "charged"])

    def test_already_charging_at_connect_is_quiet(self):
        d, got = self.daemon()
        d._charge_change("pad", 40, "Charging")
        d._charge_change("pad", 41, "Charging")
        self.assertEqual(got, [])


class TrayIcon(unittest.TestCase):
    def test_charging_badge_changes_icon(self):
        from fakes import qt_app
        qt_app()
        from couchpad.app.main import tray_icon
        a = tray_icon(75, True, False, True).pixmap(64, 64).toImage()
        b = tray_icon(75, False, False, True).pixmap(64, 64).toImage()
        self.assertNotEqual(a, b)
        # the badge sits bottom-right: that corner is green only while charging
        self.assertGreater(a.pixelColor(43, 43).green(), 150)


if __name__ == "__main__":
    unittest.main()
