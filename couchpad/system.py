"""Everything that touches the real system: uinput, D-Bus, KWin, Steam."""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import Future

from evdev import UInput, ecodes as e

from . import procs

log = logging.getLogger("couchpad")

MOUSE_BUTTONS = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
KEYS = [e.KEY_LEFTALT, e.KEY_LEFTSHIFT, e.KEY_TAB, e.KEY_ESC, e.KEY_ENTER,
        e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_LEFTMETA,
        e.KEY_BACK, e.KEY_FORWARD, e.KEY_VOLUMEUP, e.KEY_VOLUMEDOWN,
        e.KEY_PLAYPAUSE, e.KEY_NEXTSONG, e.KEY_PREVIOUSSONG, e.KEY_SYSRQ,
        e.KEY_MUTE, e.KEY_MICMUTE]


class FastUInput(UInput):
    """python-evdev waits up to 2 s per device for its /dev node to become
    readable, which it never is for us. We only write, so skip that."""

    def _find_device(self, fd):
        return None


class UinputOutput:
    """Virtual mouse + keyboard. Everything pressed is tracked so it can
    be released on shutdown (no stuck Alt after a crash or restart)."""

    def __init__(self, name="couchpad"):
        self.mouse = FastUInput(
            {e.EV_KEY: list(MOUSE_BUTTONS.values()),
             e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL,
                        e.REL_WHEEL_HI_RES, e.REL_HWHEEL_HI_RES]},
            name=f"{name} mouse", vendor=0x1209, product=0xc0c1, version=1)
        self.kbd = FastUInput({e.EV_KEY: KEYS}, name=f"{name} keyboard",
                          vendor=0x1209, product=0xc0c2, version=1)
        self.pressed = set()   # (device, code)
        self.dirty = set()
        self.wheel = [0, 0]

    def _write(self, dev, etype, code, value):
        dev.write(etype, code, value)
        self.dirty.add(dev)

    def key(self, code, down):
        self._press(self.kbd, code, down)

    def tap(self, code):
        self.key(code, True)
        self.sync()
        self.key(code, False)

    def mouse_button(self, name, down):
        self._press(self.mouse, MOUSE_BUTTONS[name], down)

    def _press(self, dev, code, down):
        k = (id(dev), code)
        if down:
            self.pressed.add(k)
        elif k in self.pressed:
            self.pressed.discard(k)
        else:
            return
        self._write(dev, e.EV_KEY, code, 1 if down else 0)

    def mouse_move(self, dx, dy):
        if dx:
            self._write(self.mouse, e.EV_REL, e.REL_X, dx)
        if dy:
            self._write(self.mouse, e.EV_REL, e.REL_Y, dy)

    def scroll(self, v, h):
        """Hi-res units (120 per notch); legacy notches emitted alongside."""
        for i, (val, hi, lo) in enumerate(((v, e.REL_WHEEL_HI_RES, e.REL_WHEEL),
                                           (h, e.REL_HWHEEL_HI_RES, e.REL_HWHEEL))):
            if not val:
                continue
            self._write(self.mouse, e.EV_REL, hi, val)
            self.wheel[i] += val
            notches = int(self.wheel[i] / 120)
            if notches:
                self.wheel[i] -= notches * 120
                self._write(self.mouse, e.EV_REL, lo, notches)

    def sync(self):
        for dev in self.dirty:
            dev.syn()
        self.dirty.clear()

    def release_all(self):
        for dev in (self.mouse, self.kbd):
            for k in [k for k in self.pressed if k[0] == id(dev)]:
                dev.write(e.EV_KEY, k[1], 0)
                self.pressed.discard(k)
            dev.syn()

    def close(self):
        try:
            self.release_all()
        finally:
            self.mouse.close()
            self.kbd.close()


# ---------------------------------------------------------------------------
# D-Bus (GLib main loop in a background thread)

BUS_NAME = "org.couchpad.Daemon"
OBJ_PATH = "/org/couchpad"
IFACE_XML = f"""
<node>
  <interface name='{BUS_NAME}'>
    <method name='KWinReply'>
      <arg type='s' name='token' direction='in'/>
      <arg type='s' name='payload' direction='in'/>
    </method>
    <method name='Command'>
      <arg type='s' name='cmd' direction='in'/>
      <arg type='s' name='result' direction='out'/>
    </method>
  </interface>
</node>"""


class Bus:
    def __init__(self, on_command=None, name=BUS_NAME):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.name = name
        self.has_owner = False
        self.on_command = on_command
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.waiting = {}
        self.notify_ids = {}
        self.ctx = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.ctx, False)
        self.owned = threading.Event()
        self._clean_stale_scripts()
        self.thread = threading.Thread(target=self._run, daemon=True, name="dbus")
        self.thread.start()
        if not self.owned.wait(3):
            log.warning("could not own %s on the session bus", self.name)

    @staticmethod
    def _clean_stale_scripts(max_age=60):
        rundir = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "couchpad")
        try:
            names = os.listdir(rundir)
        except OSError:
            return
        now = time.time()
        for n in names:
            path = os.path.join(rundir, n)
            try:
                if n.startswith("kwin-") and now - os.path.getmtime(path) > max_age:
                    os.unlink(path)
            except OSError:
                pass

    def _run(self):
        Gio, GLib = self.Gio, self.GLib
        self.ctx.push_thread_default()
        node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        self.conn.register_object(OBJ_PATH, node.interfaces[0], self._call, None, None)

        def acquired(*_):
            self.has_owner = True
            self.owned.set()

        def lost(*_):
            log.warning("lost bus name %s (another couchpad running?)", self.name)
            self.has_owner = False
            self.owned.set()

        Gio.bus_own_name_on_connection(self.conn, self.name,
                                       Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                                       acquired, lost)
        self.loop.run()

    def _call(self, conn, sender, path, iface, method, params, inv):
        args = params.unpack()
        if method == "KWinReply":
            fut = self.waiting.pop(args[0], None)
            if fut and not fut.done():
                try:
                    fut.set_result(json.loads(args[1]))
                except ValueError:
                    fut.set_result(None)
            inv.return_value(None)
        elif method == "Command":
            try:
                result = self.on_command(args[0]) if self.on_command else "no handler"
            except Exception as exc:          # never kill the bus thread
                result = f"error: {exc}"
            inv.return_value(self.GLib.Variant("(s)", (str(result),)))

    def call(self, dest, path, iface, method, sig=None, args=(), timeout=2000):
        GLib = self.GLib
        params = GLib.Variant(sig, tuple(args)) if sig else None
        res = self.conn.call_sync(dest, path, iface, method, params, None,
                                  self.Gio.DBusCallFlags.NONE, timeout, None)
        return res.unpack() if res is not None else None

    def has_name(self, name):
        try:
            return bool(self.call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                  "org.freedesktop.DBus", "NameHasOwner", "(s)",
                                  (name,))[0])
        except Exception:
            return False

    # -- notifications -------------------------------------------------------
    def notify(self, key, title, body="", icon="input-gaming", timeout=2500):
        GLib = self.GLib
        if icon.startswith("ph:"):          # our bundled icons mean nothing to KDE
            icon = "input-gaming"
        try:
            nid = self.call(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "Notify", "(susssasa{sv}i)",
                ("Couchpad", self.notify_ids.get(key, 0), icon, title, body, [],
                 {"transient": GLib.Variant("b", True),
                  "urgency": GLib.Variant("y", 1)}, timeout))[0]
            self.notify_ids[key] = nid
        except Exception as exc:
            log.debug("notify failed: %s", exc)

    # -- KWin ------------------------------------------------------------------
    def kwin_available(self):
        return self.has_name("org.kde.KWin")

    def kwin_eval(self, body, timeout=1.5):
        """Run JS in KWin. `body` may call report(obj); returns obj or None."""
        token = uuid.uuid4().hex
        rundir = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "couchpad")
        os.makedirs(rundir, mode=0o700, exist_ok=True)
        path = os.path.join(rundir, f"kwin-{token}.js")
        name = f"couchpad-{token}"
        js = ("function report(o) { callDBus(%s, %s, %s, 'KWinReply', %s, "
              "JSON.stringify(o)); }\ntry {\n%s\n} catch (err) { "
              "report({error: String(err)}); }\n") % (
            json.dumps(self.name), json.dumps(OBJ_PATH), json.dumps(BUS_NAME),
            json.dumps(token), body)
        with open(path, "w") as f:
            f.write(js)
        fut = Future()
        self.waiting[token] = fut
        try:
            sid = self.call("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting",
                            "loadScript", "(ss)", (path, name))[0]
            if sid < 0:
                return None
            self.call("org.kde.KWin", f"/Scripting/Script{sid}",
                      "org.kde.kwin.Script", "run")
            return fut.result(timeout)
        except Exception as exc:
            log.warning("kwin script failed: %s", exc)
            return None
        finally:
            self.waiting.pop(token, None)
            try:
                self.call("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting",
                          "unloadScript", "(s)", (name,))
            except Exception:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass

    def kwin_input_enabled(self, sysname, value=None):
        """Read (value=None) or set KWin's 'enabled' flag for an input device."""
        GLib = self.GLib
        path = f"/org/kde/KWin/InputDevice/{sysname}"
        args = ("org.kde.KWin.InputDevice", "enabled")
        if value is None:
            return self.call("org.kde.KWin", path, "org.freedesktop.DBus.Properties",
                             "Get", "(ss)", args)[0]
        self.call("org.kde.KWin", path, "org.freedesktop.DBus.Properties", "Set",
                  "(ssv)", args + (GLib.Variant("b", bool(value)),))

    def kwin_shortcut(self, name):
        self.call("org.kde.kglobalaccel", "/component/kwin",
                  "org.kde.kglobalaccel.Component", "invokeShortcut", "(s)", (name,))

    def close(self):
        self.loop.quit()


ACTIVE_WINDOW_JS = """
var w = workspace.activeWindow;
if (!w) { report({none: true}); }
else report({pid: w.pid, cls: String(w.resourceClass), caption: String(w.caption),
             id: String(w.internalId), special: !!(w.desktopWindow || w.dock ||
             w.specialWindow), minimized: !!w.minimized});
"""

MINIMIZE_JS = """
var w = workspace.activeWindow;
if (!w || w.desktopWindow || w.dock || !w.minimizable) { report({ok: false}); }
else { var info = {ok: true, id: String(w.internalId), caption: String(w.caption)};
       w.minimized = true; report(info); }
"""


# Steam's on-screen keyboard: a keep-above, taskbar-less, non-normal window of
# the steam client (the caption is localised, so don't match on it).
STEAM_KEYBOARD_JS = """
var l = workspace.windowList(), k = null;
for (var i = 0; i < l.length; i++) {
  var w = l[i];
  if (String(w.resourceClass) == "steam" && !w.normalWindow && w.keepAbove &&
      w.skipTaskbar && !w.deleted) { k = w; }
}
%s
"""
STEAM_KEYBOARD_CLOSE = STEAM_KEYBOARD_JS % (
    "if (k) { k.closeWindow(); report({closed: true}); } else report({closed: false});")
STEAM_KEYBOARD_VISIBLE = STEAM_KEYBOARD_JS % "report({open: !!k});"
# Steam sometimes places its keyboard for another screen (e.g. after
# switching monitor <-> TV), leaving the bottom rows off-screen. Only move
# it into the work area of its screen: Steam keeps the height fixed and lays
# the keys out to the window, so any resize squashes the labels.
STEAM_KEYBOARD_FIT = STEAM_KEYBOARD_JS % """
if (!k) { report({open: false}); } else {
  var a = workspace.clientArea(KWin.MaximizeArea, k), g = k.frameGeometry;
  var x = Math.max(a.x, Math.min(g.x, a.x + a.width - g.width));
  var y = Math.max(a.y, Math.min(g.y, a.y + a.height - g.height));
  var moved = Math.abs(x - g.x) > 1 || Math.abs(y - g.y) > 1;
  if (moved) k.frameGeometry = {x: x, y: y, width: g.width, height: g.height};
  report({open: true, moved: moved});
}"""


# KWin's task switcher is an internal window (no process, no class) that
# exists only while it is open.
TABBOX_JS = """
var l = workspace.stackingOrder, open = false;
for (var i = 0; i < l.length; i++) {
  var w = l[i];
  if (w.pid == -1 && String(w.resourceClass) == "" && !w.deleted && !w.hidden) open = true;
}
report({open: open});
"""

SHOW_DESKTOP_JS = """
workspace.showingDesktop = !workspace.showingDesktop;
report({ok: true, showing: workspace.showingDesktop});
"""

CLOSE_WINDOW_JS = """
var w = workspace.activeWindow;
if (!w || w.desktopWindow || w.dock || !w.closeable) { report({ok: false}); }
else { var c = String(w.caption); w.closeWindow(); report({ok: true, caption: c}); }
"""

FULLSCREEN_JS = """
var w = workspace.activeWindow;
if (!w || !w.fullScreenable) { report({ok: false}); }
else { w.fullScreen = !w.fullScreen; report({ok: true, on: w.fullScreen}); }
"""

# The control center's window (app id "couchpad"): unminimize and focus it.
ACTIVATE_APP_JS = """
var l = workspace.windowList(), hit = null;
for (var i = 0; i < l.length; i++) {
  if (String(l[i].resourceClass) == "couchpad" && l[i].normalWindow) hit = l[i];
}
if (!hit) { report({ok: false}); }
else { hit.minimized = false; workspace.activeWindow = hit; report({ok: true}); }
"""

STATUS_RU = {"Charging": "заряжается", "Full": "заряжен", "Discharging": "от батареи",
             "Not charging": "не заряжается"}


def battery_icon(cap, status=None):
    if status == "Charging":
        return "ph:battery-charging"
    return "ph:battery-" + ("high" if cap > 60 else "medium" if cap > 30 else
                            "low" if cap > 12 else "warning")


def open_control_center():
    """Start the control center (or raise the running one)."""
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_root
    subprocess.Popen([sys.executable, "-W", "ignore", "-m", "couchpad", "app"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=env)


def bluetooth_disconnect(mac):
    """Disconnecting a DualSense over Bluetooth switches it off."""
    if not mac or not shutil.which("bluetoothctl"):
        return False
    try:
        r = subprocess.run(["bluetoothctl", "disconnect", mac.upper()], timeout=8,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def session_kind():
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gamescope" in desk:
        return "gamescope"
    return "kde" if "kde" in desk else "other"


def steam_running():
    for info in procs.read_table().values():
        if (info["comm"] == "steam" and info["uid"] == os.getuid()
                and info.get("state") != "Z"):        # ignore zombies
            return True
    return False


def open_steam_keyboard():
    steam = shutil.which("steam")
    if not steam:
        return False
    subprocess.Popen([steam, "steam://open/keyboard"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return True


def battery(uniq):
    base = "/sys/class/power_supply"
    try:
        names = os.listdir(base)
    except OSError:
        return None
    for name in names:
        if name.startswith("ps-controller-battery") and (not uniq or uniq.lower() in name.lower()):
            try:
                with open(f"{base}/{name}/capacity") as f:
                    cap = int(f.read())
                with open(f"{base}/{name}/status") as f:
                    status = f.read().strip()
                return cap, status
            except (OSError, ValueError):
                return None
    return None
