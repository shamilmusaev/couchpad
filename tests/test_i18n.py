"""Every user-visible Russian string has an English translation."""

import glob
import os
import re
import unittest

from couchpad import actions, i18n, system, wheel
from couchpad.i18n_en import EN

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "couchpad")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def source_strings():
    out = set()
    for f in glob.glob(os.path.join(ROOT, "app", "qml", "*.qml")):
        out |= {m.group(1).replace("\\n", "\n")
                for m in re.finditer(r'L\.t\("((?:[^"\\]|\\.)*)"\)', read(f))}
    for f in glob.glob(os.path.join(ROOT, "*.py")) + glob.glob(os.path.join(ROOT, "app", "*.py")):
        out |= {m.group(1).replace("\\n", "\n")
                for m in re.finditer(r'\b_\("((?:[^"\\]|\\.)*)"\)', read(f))}
    out |= {v[0] for v in actions.ACTIONS.values()}
    out |= {v[0] for v in actions.FIXED_CHORDS.values()}
    out |= set(system.STATUS_RU.values())
    out |= {it["name"] for it in wheel.DEFAULT_ITEMS if re.search("[А-я]", it.get("name", ""))}
    return {s for s in out if re.search("[А-Яа-яЁё]", s)}


class Coverage(unittest.TestCase):
    def test_everything_translated(self):
        missing = sorted(source_strings() - set(EN))
        self.assertEqual(missing, [], "add these to couchpad/i18n_en.py")

    def test_no_cyrillic_in_english(self):
        bad = {k: v for k, v in EN.items() if re.search("[А-Яа-яЁё]", v)}
        self.assertEqual(bad, {})

    def test_placeholders_match(self):
        for k, v in EN.items():
            self.assertEqual(re.findall(r"\{\w+\}", k), re.findall(r"\{\w+\}", v), k)


class Switching(unittest.TestCase):
    def tearDown(self):
        i18n.set_lang("ru")

    def test_set_lang(self):
        self.assertEqual(i18n.set_lang("en"), "en")
        self.assertEqual(i18n._("Мышь включена"), "Mouse on")
        self.assertEqual(i18n._("непереведённое"), "непереведённое")
        i18n.set_lang("ru")
        self.assertEqual(i18n._("Мышь включена"), "Мышь включена")

    def test_auto(self):
        old = os.environ.get("LANG")
        try:
            os.environ["LANG"] = "en_GB.UTF-8"
            os.environ.pop("LC_ALL", None)
            os.environ.pop("LC_MESSAGES", None)
            self.assertEqual(i18n.set_lang("auto"), "en")
            os.environ["LANG"] = "ru_RU.UTF-8"
            self.assertEqual(i18n.set_lang("auto"), "ru")
        finally:
            if old is not None:
                os.environ["LANG"] = old

    def test_default_wheel_names_follow_language(self):
        i18n.set_lang("en")
        names = [it["name"] for it in wheel.resolve([{"name": "Файлы", "exec": "true"}])]
        self.assertEqual(names, ["Файлы"], "user-given names are never translated")


if __name__ == "__main__":
    unittest.main()
