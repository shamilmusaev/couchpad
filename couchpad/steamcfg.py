"""Neutralise Steam's *Desktop Configuration* for PlayStation controllers.

On the desktop Steam maps the DualSense to keyboard/mouse (Share = Escape,
Cross = Enter, touchpad = always-on mouse...). That fights with couchpad, so
we strip every binding from the desktop layout and keep a backup. Game
layouts are not touched. Steam must not be running while this happens,
otherwise it writes its in-memory copy back on exit.
"""

import glob
import os
import re
import shutil

STEAM = os.path.expanduser("~/.local/share/Steam")
DESKTOP_APPID = "413080"
BACKUP_SUFFIX = ".couchpad-backup"
MARK = "couchpad: neutral desktop layout v2"
BINDING_RE = re.compile(r'^(\s*)"binding"\s+"[^"]*"\s*\n', re.M)
DESC_RE = re.compile(r'^(\s*"description"\s+)"[^"]*"', re.M)
# Which groups (touchpad = absolute_mouse, stick = joystick_mouse...) are
# active. Those modes move the cursor even without any binding, so the
# active list has to go too.
SOURCES_RE = re.compile(r'("group_source_bindings"\s*\{)[^{}]*(\})')


def desktop_files(steam=STEAM):
    pattern = os.path.join(steam, "steamapps", "common", "Steam Controller Configs",
                           "*", "config", DESKTOP_APPID, "*.vdf")
    out = []
    for path in sorted(glob.glob(pattern)):
        name = os.path.basename(path)
        # controller_ps5*.vdf templates and DS<mac>.vdf per-device autosaves
        if name.startswith(("controller_ps5", "controller_ps4", "DS")):
            out.append(path)
    return out


def neutralize_text(text):
    text = BINDING_RE.sub("", text)
    text = SOURCES_RE.sub(lambda m: m.group(1) + "\n\t\t" + m.group(2), text)
    text = DESC_RE.sub(lambda m: f'{m.group(1)}"{MARK}"', text, count=1)
    return text


def is_neutral(text):
    if MARK not in text or BINDING_RE.search(text):
        return False
    return all(not m.group(0)[len('"group_source_bindings"'):].strip(" \t\n{}")
               for m in SOURCES_RE.finditer(text))


def neutralize(steam=STEAM):
    changed = []
    for path in desktop_files(steam):
        with open(path) as f:
            text = f.read()
        if is_neutral(text):
            continue
        backup = path + BACKUP_SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        tmp = path + ".couchpad-tmp"
        with open(tmp, "w") as f:
            f.write(neutralize_text(text))
        os.replace(tmp, path)
        changed.append(path)
    return changed


def restore(steam=STEAM):
    restored = []
    for backup in glob.glob(os.path.join(
            steam, "steamapps", "common", "Steam Controller Configs", "*", "config",
            DESKTOP_APPID, "*" + BACKUP_SUFFIX)):
        path = backup[:-len(BACKUP_SUFFIX)]
        os.replace(backup, path)
        restored.append(path)
    return restored


def status(steam=STEAM):
    result = {}
    for path in desktop_files(steam):
        with open(path) as f:
            result[path] = is_neutral(f.read())
    return result
