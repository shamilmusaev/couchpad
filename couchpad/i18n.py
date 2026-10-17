"""Russian / English. Russian text is the key; EN maps it to English.

`set_lang("auto" | "ru" | "en")` once the config is known; `_()` then
translates. QML gets the same table through the control center backend.
"""

import os

_lang = "ru"


def detect():
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "")
    return "ru" if loc.lower().startswith(("ru", "be", "uk", "kk")) else "en"


def set_lang(choice):
    global _lang
    _lang = detect() if choice not in ("ru", "en") else choice
    return _lang


def lang():
    return _lang


def _(text):
    return EN.get(text, text) if _lang == "en" else text


from .i18n_en import EN  # noqa: E402  (the big table lives in its own file)
