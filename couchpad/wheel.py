"""Quick-launch wheel: item list, .desktop lookup, launching, UI process."""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from . import i18n
from .i18n import _

log = logging.getLogger("couchpad")

# Used when config.toml has no [[wheel]] entries. Missing apps are skipped.
DEFAULT_ITEMS = [
    {"app": "hydra"},
    {"name": "Big Picture", "icon": "steam", "open": "steam://open/bigpicture"},
    {"app": "net.lutris.Lutris"},
    {"app": "org.mozilla.firefox"},
    {"app": "com.google.Chrome"},
    {"app": "org.kde.dolphin", "name": "Файлы"},
    {"app": "org.kde.discover", "name": "Магазин"},
    {"app": "systemsettings", "name": "Настройки"},
]

MAX_ITEMS = 8


def app_dirs():
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    dirs = [data_home] + os.environ.get(
        "XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    dirs += [os.path.expanduser("~/.local/share/flatpak/exports/share"),
             "/var/lib/flatpak/exports/share"]
    seen, out = set(), []
    for d in dirs:
        path = os.path.join(d, "applications")
        if d and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def find_desktop(app_id, dirs=None):
    name = app_id if app_id.endswith(".desktop") else app_id + ".desktop"
    for d in dirs or app_dirs():
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    return None


def read_desktop(path, lang=None):
    """Name/Icon from the [Desktop Entry] group (localized name preferred)."""
    entry, group = {}, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("["):
                group = line
                continue
            if group != "[Desktop Entry]" or "=" not in line:
                continue
            k, v = line.split("=", 1)
            entry.setdefault(k.strip(), v.strip())
    lang = lang or i18n.lang()
    name = entry.get(f"Name[{lang}]") or entry.get("Name") or os.path.basename(path)
    return {"name": name, "icon": entry.get("Icon", ""),
            "hidden": entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true"}


def resolve(items, dirs=None):
    """Config entries -> [{"name", "icon", "app"|"open"|"exec"}], skipping
    apps that aren't installed."""
    out = []
    for raw in items or DEFAULT_ITEMS:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if raw in DEFAULT_ITEMS and item.get("name"):
            item["name"] = _(item["name"])
        if item.get("app"):
            path = find_desktop(item["app"], dirs)
            if not path:
                continue
            info = read_desktop(path)
            item.setdefault("name", info["name"])
            item.setdefault("icon", info["icon"])
            item["app"] = os.path.basename(path)[:-len(".desktop")]
        elif not (item.get("open") or item.get("exec")):
            continue
        item.setdefault("name", item.get("open") or item.get("exec"))
        item.setdefault("icon", "")
        out.append(item)
        if len(out) == MAX_ITEMS:
            break
    return out


def launch_argv(item):
    if item.get("app"):
        return ["gtk-launch", item["app"]]
    if item.get("open"):
        if item["open"].startswith("steam://") and shutil.which("steam"):
            return ["steam", item["open"]]
        return ["xdg-open", item["open"]]
    if item.get("exec"):
        return ["sh", "-c", item["exec"]]
    return None


def launch(item, popen=subprocess.Popen):
    argv = launch_argv(item)
    if not argv:
        return False
    popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, start_new_session=True)
    log.info("wheel launched %s: %s", item.get("name"), " ".join(argv))
    return True


def sector(x, y, n, deadzone=0.55):
    """Stick position -> item index (0 = up, clockwise) or None."""
    import math
    if n <= 0 or math.hypot(x, y) < deadzone:
        return None
    angle = math.degrees(math.atan2(x, -y)) % 360      # 0 = up, clockwise
    step = 360.0 / n
    return int(((angle + step / 2) % 360) // step)


class WheelUI:
    """Keeps the PySide6 overlay process (wheel, toasts, hold ring) alive and
    talks to it."""

    def __init__(self, on_event=None):
        self.proc = None
        self.lock = threading.Lock()
        self.on_event = on_event
        self.osd = False          # overlay can show toasts above everything
        self.failed_t = -1e9      # don't respawn a crashing overlay in a loop
        self.state = {"shown": False, "geo": None}   # as the overlay reports it

    def _ensure(self):
        if self.proc and self.proc.poll() is None:
            return True
        if time.monotonic() - self.failed_t < 10:
            return False
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-W", "ignore", "-m", "couchpad.overlay_ui"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, env=env)
            line = self.proc.stdout.readline()
            if "ready" not in line:
                self.failed_t = time.monotonic()
            # Drain later status lines so the pipe can never fill up.
            threading.Thread(target=self._drain, args=(self.proc, self.on_event, self.state),
                             daemon=True).start()
            try:
                self.osd = bool(json.loads(line).get("osd"))
            except ValueError:
                self.osd = False
            return "ready" in line
        except OSError as exc:
            log.warning("wheel UI failed: %s", exc)
            return False

    @staticmethod
    def _drain(proc, on_event, state):
        """Read status lines (keeps the pipe from filling), track whether the
        wheel is on screen and forward the user's mouse/keyboard choices."""
        try:
            for line in proc.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                ev = msg.get("event")
                if ev in ("shown", "hidden"):
                    state["shown"] = ev == "shown"
                    state["geo"] = msg.get("geo")
                elif on_event and ev in ("select", "launch", "cancel"):
                    on_event(msg)
        except (OSError, ValueError):
            pass

    def send(self, msg):
        """True if the overlay took the message."""
        with self.lock:
            if msg.get("cmd") in ("select", "hide", "hold_end") and not (
                    self.proc and self.proc.poll() is None):
                return False
            if not self._ensure():
                return False
            try:
                msg = dict(msg, lang=i18n.lang())
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()
                return True
            except (BrokenPipeError, OSError):
                self.proc = None
                return False

    def warm_up(self):
        with self.lock:
            self._ensure()

    def close(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write('{"cmd": "quit"}\n')
                    self.proc.stdin.flush()
                    self.proc.wait(2)
                except Exception:
                    self.proc.kill()
            self.proc = None
