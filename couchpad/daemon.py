"""couchpad daemon: DualSense couch-gaming helper for KDE Plasma (Wayland)."""

import argparse
import asyncio
import json
import logging
import os
import signal
import shutil
import subprocess
import sys
import threading
import time

import evdev
from evdev import ecodes as e, ff

from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields

from . import __version__, config as config_mod, hidraw, i18n, procs, system, wheel as wheel_mod
from .actions import ACTIONS
from .hdhaptics import HDHaptics
from .lights import Lights
from .engine import EVDEV_BUTTONS, Controller, Mode, Touchpad
from .i18n import _

log = logging.getLogger("couchpad")

SONY = 0x054C
PRODUCTS = {0x0CE6, 0x0DF2}          # DualSense, DualSense Edge
HAT = {(e.ABS_HAT0X, -1): "left", (e.ABS_HAT0X, 1): "right",
       (e.ABS_HAT0Y, -1): "up", (e.ABS_HAT0Y, 1): "down"}
STICKS = {e.ABS_X: "lx", e.ABS_Y: "ly", e.ABS_RX: "rx", e.ABS_RY: "ry"}


def hid_parent(dev_path):
    """Sysfs HID device shared by a controller's gamepad/touchpad/motion nodes."""
    node = os.path.basename(dev_path)
    try:
        return os.path.realpath(f"/sys/class/input/{node}/device/device")
    except OSError:
        return None


# Haptic patterns: (start_ms, strong, weak, length_ms). "weak" is the
# high-frequency side - short, light pulses on it feel like crisp clicks
# rather than a buzz; "strong" adds a deeper thump.
HAPTICS = {
    "tick":      [(0, 0, 0x5000, 22)],                             # hold started
    "progress1": [(0, 0, 0x4000, 18)],
    "progress2": [(0, 0, 0x6000, 20)],
    "progress3": [(0, 0x2000, 0x8000, 22)],
    "fire":      [(0, 0x6000, 0xC000, 35), (90, 0x6000, 0xC000, 35)],  # done: double click
    "cancel":    [(0, 0x3000, 0, 45)],                             # soft dull thump
    "on":        [(0, 0, 0x5000, 25), (110, 0x3000, 0xA000, 35)],  # rising
    "off":       [(0, 0x3000, 0xA000, 35), (110, 0, 0x4000, 25)],  # falling
    "open":      [(0, 0, 0x6000, 25)],
    "detent":    [(0, 0, 0x3800, 12)],                             # wheel sector
    "launch":    [(0, 0x5000, 0xB000, 40)],
    "step":      [(0, 0, 0x4000, 14)],
    "confirm":   [(0, 0x4000, 0x9000, 30)],
}


class Rumble:
    """Plays HAPTICS patterns through the kernel force-feedback device,
    reusing a single effect slot."""

    def __init__(self, dev, loop, enabled, strength=1.0):
        self.dev, self.loop, self.enabled = dev, loop, enabled
        self.strength = max(0.0, min(strength, 3.0))
        self.eid = -1
        self.handles = []

    def play(self, pattern):
        if not self.enabled or self.strength <= 0:
            return
        pulses = HAPTICS.get(pattern)
        if not pulses:
            return
        for h in self.handles:          # a new pattern replaces the old one
            h.cancel()
        self.handles = [self.loop.call_later(at / 1000, self._pulse, strong, weak, ms)
                        for at, strong, weak, ms in pulses]

    def _pulse(self, strong, weak, ms):
        k = self.strength
        eff = ff.Effect(e.FF_RUMBLE, self.eid, 0, ff.Trigger(0, 0), ff.Replay(ms, 0),
                        ff.EffectType(ff_rumble_effect=ff.Rumble(
                            strong_magnitude=min(int(strong * k), 0xFFFF),
                            weak_magnitude=min(int(weak * k), 0xFFFF))))
        try:
            self.eid = self.dev.upload_effect(eff)
            self.dev.write(e.EV_FF, self.eid, 1)
        except OSError as exc:
            log.debug("rumble failed: %s", exc)
            self.enabled = False

    def close(self):
        for h in self.handles:
            h.cancel()
        if self.eid >= 0:
            try:
                self.dev.erase_effect(self.eid)
            except OSError:
                pass
        self.eid = -1


class Services:
    """Actions shared by all controllers. Slow work runs in a thread."""

    def __init__(self, daemon):
        self.d = daemon
        self.cfg = daemon.cfg
        self.wheel_items = []
        self.wheel_ui = None
        self.wheel_exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wheel")
        self.minimized = None     # internal id of the window we minimized
        self.auto_mouse = False   # mouse mode was switched on by minimize
        self.kb_watching = False
        self.kb_pending = False
        self.kb_lock = threading.Lock()
        self.overlay_lock = threading.Lock()
        self.switcher_watching = False

    def notify(self, key, title, body="", icon="ph:game-controller", accent=None, progress=None):
        """On-screen toast (overlay) or, without one, a KDE notification."""
        if not self.cfg.notifications or self.d.dry:
            return
        msg = {"cmd": "osd", "key": key, "title": title, "body": body, "icon": icon,
               "accent": accent or self.accent(), "progress": progress}

        def send():
            ui = self._overlay()
            if self.cfg.osd and ui and ui.send(msg) and ui.osd:
                return
            if self.d.bus:
                text = body if progress is None or not body else f"{progress}% · {body}"
                self.d.bus.notify(key, title, text, icon)
        self.wheel_exec.submit(self._guard, send)

    def accent(self):
        return "#ff6a1f"            # the control center's accent

    def hold(self, action, seconds):
        if not self.cfg.hold_osd or self.d.dry:
            return
        title, body, icon, accent = {
            "minimize": (_("Свернуть игру"), _("Держите Share + ○"), "ph:arrow-line-down", None),
            "force_close": (_("Закрыть игру"), _("Держите Share + △"), "ph:x-circle", "#ff4545"),
        }[action]
        self._overlay_send({"cmd": "hold", "title": title, "body": body, "icon": icon,
                            "accent": accent or self.accent(), "duration": seconds})

    def hold_end(self, done):
        if self.cfg.hold_osd and not self.d.dry:
            self._overlay_send({"cmd": "hold_end", "done": done})

    def _overlay(self):
        with self.overlay_lock:          # input loop and worker thread both get here
            if self.wheel_ui is None and os.environ.get("WAYLAND_DISPLAY"):
                self.wheel_ui = wheel_mod.WheelUI(self._wheel_ui_event)
            return self.wheel_ui

    def _overlay_send(self, msg):
        if self.d.dry or not os.environ.get("WAYLAND_DISPLAY"):
            return
        ui = self._overlay()
        self.wheel_exec.submit(self._guard, ui.send, msg)

    def background(self, fn, *args):
        self.d.loop.run_in_executor(None, self._guard, fn, *args)

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except Exception:
            log.exception("action %s failed", fn.__name__)

    def kde(self):
        return not self.d.dry and self.d.bus is not None and self.d.bus.kwin_available()

    # -- actions ---------------------------------------------------------------
    def minimize(self, ctl_actions):
        if self.d.dry:
            self.d.record("minimize")
            return
        if not self.kde():
            self.notify("act", _("Свернуть можно только на рабочем столе KDE"),
                        icon="ph:warning")
            return
        self.d.record("minimize")
        res = self.d.bus.kwin_eval(system.MINIMIZE_JS)
        if not res or not res.get("ok"):
            self.notify("act", _("Нечего сворачивать"), icon="ph:info")
            return
        self.minimized = res.get("id")
        log.info("minimized %r", res.get("caption"))
        if self.cfg.mouse_on_after_minimize and not self.d.mode.mouse:
            self.auto_mouse = True
            self.d.call_soon(self.d.set_mouse, True)
        self.notify("act", _("Свёрнуто: ") + (res.get("caption") or _("окно")),
                    _("Share + ○ — вернуться к окнам"), "ph:arrow-line-down")

    def force_close(self, ctl_actions):
        if self.d.dry:
            self.d.record("force_close")
            return
        self.d.record("force_close")
        table = procs.read_table()
        target = None
        if self.kde():
            win = self.d.bus.kwin_eval(system.ACTIVE_WINDOW_JS)
            log.info("active window: %s", win)
            if win and not win.get("none") and not win.get("special"):
                target = procs.find_target(table, int(win.get("pid") or 0))
                if target is None:
                    self.notify("act", _("Это окно закрывать нельзя"),
                                win.get("caption", ""), "ph:warning")
                    return
            elif win is None:
                target = procs.latest_steam_game(table)
        else:
            target = procs.latest_steam_game(table)
        if target is None:
            self.notify("act", _("Нет активной игры"), icon="ph:info")
            return
        root, kind, label = target
        n = procs.kill_tree(root, kind)
        log.info("force-closed %s (%s, root %d, %d procs)", label, kind, root, n)
        self.notify("act", _("Закрыто: ") + label, _("принудительно, процессов: {n}").format(n=n),
                    "ph:x-circle", "#ff4545")

    def keyboard(self, ctl_actions):
        if self.d.dry:
            self.d.record("keyboard")
            return
        self.d.record("keyboard")
        mode = self.cfg.keyboard
        if mode in ("auto", "steam") and system.steam_running():
            if self.kde():
                res = self.d.bus.kwin_eval(system.STEAM_KEYBOARD_CLOSE)
                if res and res.get("closed"):
                    return          # the watcher restores mouse mode
            if system.open_steam_keyboard():
                if self.kde():
                    self._watch_steam_keyboard()
                return
        if mode in ("auto", "plasma") and self.d.bus:
            try:
                kb = ("org.kde.KWin", "/VirtualKeyboard",
                      "org.freedesktop.DBus.Properties")
                avail = self.d.bus.call(*kb, "Get", "(ss)",
                                        ("org.kde.kwin.VirtualKeyboard", "available"))[0]
                if avail:
                    visible = self.d.bus.call(*kb, "Get", "(ss)",
                                              ("org.kde.kwin.VirtualKeyboard", "visible"))[0]
                    if visible:
                        self.d.bus.call(*kb, "Set", "(ssv)",
                                        ("org.kde.kwin.VirtualKeyboard", "active",
                                         self.d.bus.GLib.Variant("b", False)))
                    else:
                        self.d.bus.call("org.kde.KWin", "/VirtualKeyboard",
                                        "org.kde.kwin.VirtualKeyboard", "forceActivate")
                    return
            except Exception as exc:
                log.debug("plasma keyboard failed: %s", exc)
        self.notify("act", _("Экранная клавиатура недоступна"),
                    _("Запустите Steam или включите Plasma Keyboard"), "ph:warning")

    # -- quick-launch wheel ------------------------------------------------------
    def wheel(self, event, i=None):
        """Called from the input loop; UI traffic goes through one worker
        thread so messages keep their order."""
        if event == "open":
            self.wheel_items = wheel_mod.resolve(self.cfg.wheel)
            if not self.wheel_items:
                self.notify("wheel", _("Колесо пустое"),
                            _("Добавьте приложения в панели Couchpad"), "ph:circles-three-plus")
                return 0
            self.d.record("wheel_open")
            items = [{"name": it["name"], "icon": it["icon"]} for it in self.wheel_items]
            self._wheel_send({"cmd": "show", "items": items, "sel": None,
                              "accent": self.accent()})
            return len(self.wheel_items)
        if event == "select":
            self._wheel_send({"cmd": "select", "i": i})
        elif event == "launch":
            self._wheel_send({"cmd": "hide"})
            item = self.wheel_items[i]
            self.d.record(f"wheel_launch:{item['name']}")
            if not self.d.dry:
                self.wheel_exec.submit(self._guard, wheel_mod.launch, item)
        elif event == "cancel":
            self.d.record("wheel_cancel")
            self._wheel_send({"cmd": "hide"})
        return None

    def _wheel_send(self, msg):
        if self.d.dry:
            return
        ui = self._overlay()
        if ui is not None:
            self.wheel_exec.submit(self._guard, ui.send, msg)

    def warm_up_wheel(self):
        if self.d.dry or not os.environ.get("WAYLAND_DISPLAY"):
            return
        self.wheel_exec.submit(self._guard, lambda: self._overlay().warm_up())

    def _wheel_ui_event(self, msg):
        """From the UI reader thread: hand mouse choices to the controller
        that has the wheel open."""
        def apply():
            for pad in self.d.pads.values():
                if pad.ctl and pad.ctl.wheel:
                    pad.ctl.wheel_external(msg["event"], msg.get("i"))
                    return
        self.d.call_soon(apply)

    def _watch_steam_keyboard(self):
        """Steam drives its keyboard with the touchpad and sticks, so pause
        mouse mode while it is open and bring it back afterwards. Also keep
        the keyboard on screen. Re-opening it while a watcher is still
        winding down is picked up via kb_pending."""
        with self.kb_lock:
            self.kb_pending = True
            if self.kb_watching:
                return
            self.kb_watching = True
        resume = None
        try:
            while not self.d.stopping:
                with self.kb_lock:
                    if not self.kb_pending:
                        self.kb_watching = False
                        break
                    self.kb_pending = False
                if not self._wait_keyboard_open():
                    continue
                if resume is None:
                    resume = self.d.mode.mouse
                    if resume:
                        self.d.call_soon(self.d.set_mouse, False, True)
                self._follow_keyboard()
        finally:
            with self.kb_lock:
                self.kb_watching = False
            if resume:
                self.d.call_soon(self.d.set_mouse, True, True)

    def _wait_keyboard_open(self):
        for _i in range(30):                     # up to ~3 s to appear
            res = self.d.bus.kwin_eval(system.STEAM_KEYBOARD_FIT)
            if res and res.get("open"):
                if res.get("moved"):
                    log.info("Steam keyboard moved back on screen")
                return True
            time.sleep(0.1)
        return False

    def _follow_keyboard(self):
        failures = 0
        while failures < 10 and not self.d.stopping:
            time.sleep(0.25)
            res = self.d.bus.kwin_eval(system.STEAM_KEYBOARD_FIT)
            if res is None:
                failures += 1
                continue
            failures = 0
            if res.get("moved"):
                log.info("Steam keyboard moved back on screen")
            if not res.get("open"):
                return

    # -- monitor / TV (the separate display-switcher program) --------------------
    def _display(self, mode):
        self.d.record(f"display_{mode}")
        if self.d.dry:
            return
        exe = shutil.which("display-switcher") or os.path.expanduser("~/.local/bin/display-switcher")
        if not os.path.exists(exe):
            self.notify("act", _("display-switcher не установлен"), icon="ph:warning")
            return
        # It shows its own fade + card; don't wait for it.
        subprocess.Popen([exe, mode], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        log.info("display-switcher %s", mode)

    def display_monitor(self, ctl_actions):
        self._display("monitor")

    def display_tv(self, ctl_actions):
        self._display("tv")

    def overview(self, ctl_actions):
        if self.d.dry:
            self.d.record("overview")
            return
        if self.kde():
            self.d.bus.kwin_shortcut("Overview")

    def battery(self, ctl_actions):
        info = system.battery(ctl_actions.uniq)
        if self.d.dry:
            self.d.record("battery")
            return
        self.show_battery(info)

    def show_battery(self, info, title="DualSense"):
        if not info:
            self.notify("bat", _("Заряд геймпада неизвестен"), icon="ph:battery-warning")
            return
        cap, status = info
        icon = system.battery_icon(cap, status)
        accent = "#ff4545" if cap <= 15 and status != "Charging" else \
            "#f5b400" if cap <= 30 and status != "Charging" else "#2ecc71"
        self.notify("bat", f"{title} · {cap}%", _(system.STATUS_RU.get(status, status)),
                    icon, accent, cap)

    def _kwin_action(self, name, js, ok_text=None, icon=None):
        self.d.record(name)
        if self.d.dry or not self.kde():
            return None
        res = self.d.bus.kwin_eval(js)
        if res and res.get("ok") and ok_text:
            self.notify("act", ok_text, res.get("caption", ""), icon)
        return res

    def show_desktop(self, ctl_actions):
        self._kwin_action("show_desktop", system.SHOW_DESKTOP_JS)

    def close_window(self, ctl_actions):
        res = self._kwin_action("close_window", system.CLOSE_WINDOW_JS,
                                _("Окно закрыто"), "ph:x-square")
        if res is not None and not res.get("ok"):
            self.notify("act", _("Нечего закрывать"), icon="ph:info")

    def fullscreen(self, ctl_actions):
        self._kwin_action("fullscreen", system.FULLSCREEN_JS)

    def big_picture(self, ctl_actions):
        self.d.record("big_picture")
        if not self.d.dry:
            wheel_mod.launch({"name": "Big Picture", "open": "steam://open/bigpicture"})

    def control_center(self, ctl_actions):
        self.d.record("control_center")
        if self.d.dry:
            return
        system.open_control_center()
        if self.kde():
            for _i in range(20):                 # bring it to the front once mapped
                time.sleep(0.15)
                res = self.d.bus.kwin_eval(system.ACTIVATE_APP_JS)
                if res and res.get("ok"):
                    break

    def power_off(self, ctl_actions):
        self.d.record("power_off")
        if self.d.dry:
            return
        self.notify("conn", _("Геймпад выключается"), _("Нажмите PS, чтобы включить"), "ph:power")
        time.sleep(0.6)
        if not system.bluetooth_disconnect(ctl_actions.uniq):
            self.notify("conn", _("Не удалось выключить геймпад"), _("Он подключён не по Bluetooth?"),
                        "ph:warning")

    def none(self, ctl_actions):
        pass

    def watch_switcher(self, ctl):
        """While our Alt+Tab is open, check that KWin's switcher really is.
        If KWin closed it by itself (focus change, a click...), our Alt would
        stay pressed and every key would become Alt+key: let go of it."""
        if self.d.dry or not self.kde() or self.switcher_watching:
            return
        self.switcher_watching = True

        def watch():
            misses = 0
            try:
                time.sleep(0.6)                  # let the switcher appear
                while ctl.alt_tab and not self.d.stopping:
                    res = self.d.bus.kwin_eval(system.TABBOX_JS)
                    misses = misses + 1 if res is not None and not res.get("open") else 0
                    if misses >= 2:
                        log.warning("window switcher closed by KWin: releasing Alt")
                        self.d.call_soon(ctl.switcher_gone)
                        return
                    time.sleep(0.3)
            finally:
                self.switcher_watching = False
        self.background(watch)

    def after_switch(self, cancelled):
        """Alt-Tab finished: if the user went back to the game we minimized,
        undo the automatic mouse mode."""
        if cancelled or not self.auto_mouse or not self.minimized or self.d.dry:
            return

        def check():
            time.sleep(0.25)
            win = self.d.bus.kwin_eval(system.ACTIVE_WINDOW_JS) if self.kde() else None
            if win and win.get("id") == self.minimized:
                self.auto_mouse = False
                self.minimized = None
                self.d.call_soon(self.d.set_mouse, False)
        self.background(check)


class ControllerActions:
    """The `actions` object one Controller engine talks to."""

    KEY_ACTIONS = {
        "volume_up": e.KEY_VOLUMEUP, "volume_down": e.KEY_VOLUMEDOWN,
        "mute": e.KEY_MUTE, "mic_mute": e.KEY_MICMUTE,
        "media_play_pause": e.KEY_PLAYPAUSE, "media_next": e.KEY_NEXTSONG,
        "media_previous": e.KEY_PREVIOUSSONG, "screenshot": e.KEY_SYSRQ,
    }
    THREADED = {"minimize", "force_close", "keyboard", "overview", "battery",
                "display_monitor", "display_tv", "show_desktop", "close_window",
                "fullscreen", "big_picture", "control_center", "power_off", "none"}
    # lightbar flash per action
    FLASH = {"force_close": "#ff2020", "minimize": "#ffffff", "screenshot": "#ffffff",
             "close_window": "#ff6a3d"}

    def __init__(self, services, rumble, uniq, pad=None):
        self.s = services
        self.rumble = rumble
        self.uniq = uniq
        self.pad = pad

    def run(self, action, ctl):
        log.info("action: %s [pad %s]", action, self.uniq)
        if action in self.FLASH:
            self.flash(self.FLASH[action])
        out = self.s.d.out
        if action in self.KEY_ACTIONS:
            out.tap(self.KEY_ACTIONS[action])
            out.sync()
            self.s.d.record(action)
        elif action in self.THREADED:
            self.s.background(getattr(self.s, action), self)
        else:
            log.warning("unknown action %s", action)

    def flash(self, color):
        if self.pad and self.pad.lights:
            self.pad.lights.flash(color, time.monotonic())
            self.s.d.kick_lights()

    def hold(self, action, seconds):
        self.s.hold(action, seconds)

    def hold_end(self, done):
        self.s.hold_end(done)

    def warm_haptics(self):
        if self.pad and self.pad.hd:
            self.pad.hd.warm()

    def feedback(self, kind, pan=0.0):
        if kind == "launch":
            self.flash("#ffffff")
        hd = self.pad.hd if self.pad else None
        if hd and hd.play(kind, pan):
            return
        if self.rumble:
            self.rumble.play(kind)

    def hint(self, text):
        self.s.notify("hint", text)

    def mouse_mode(self, on, quiet=False):
        log.info("mouse mode %s%s [pad %s]", "on" if on else "off",
                 " (quiet)" if quiet else "", self.uniq)
        self.s.d.record("mouse_on" if on else "mouse_off")
        if not on and not quiet:
            self.s.auto_mouse = False
        self.s.d.on_mouse_mode(on)
        if quiet:
            return
        self.feedback("on" if on else "off")
        self.s.notify("mouse", _("Мышь включена") if on else _("Мышь выключена"),
                      _("Тачпад — курсор · Share ×2 — выключить") if on
                      else _("Share ×2 — включить снова"),
                      "ph:hand-pointing" if on else "ph:hand-pointing",
                      (self.s.cfg.light_mouse_color or None) if on else None)

    def wheel(self, event, i=None):
        return self.s.wheel(event, i)

    def switcher_opened(self, ctl=None):
        log.info("window switcher opened [pad %s]", self.uniq)
        self.s.d.record("switcher_open")
        if ctl is not None:
            self.s.watch_switcher(ctl)

    def switcher_step(self, reverse):
        self.s.d.record("switcher_back" if reverse else "switcher_next")

    def after_switch(self, cancelled):
        log.info("window switcher %s [pad %s]", "cancelled" if cancelled else "confirmed",
                 self.uniq)
        self.s.d.record("switcher_cancel" if cancelled else "switcher_confirm")
        self.s.after_switch(cancelled)


class Pad:
    """One physical controller: its gamepad node and (optional) touchpad."""

    def __init__(self, daemon, key):
        self.d = daemon
        self.key = key
        self.gamepad = None
        self.touchpad = None
        self.tasks = []
        self.rumble = None
        self.ctl = None
        self.tp = None
        self.uniq = ""
        self.hid = None           # hidraw touchpad fallback
        self.hid_fd = None
        self.kwin_off = None      # KWin touchpad device we disabled
        self.hd = None            # HD haptics over Bluetooth
        self.lights = None
        self.bluetooth = False
        self.last_input = time.monotonic()

    def _make_hd(self, dev):
        cfg = self.d.cfg
        if self.d.dry or not cfg.rumble or cfg.haptics not in ("auto", "hd"):
            return None
        if dev.info.bustype != 0x05:      # report 0x32 is the Bluetooth path
            return None
        node = hidraw.hidraw_node(self.key)
        if not node or not os.access(node, os.W_OK):
            return None
        log.info("HD haptics via %s", node)
        return HDHaptics(node, cfg.haptic_strength)

    # -- hidraw touchpad fallback (no udev rule installed) ----------------------
    def attach_hidraw(self):
        node = hidraw.hidraw_node(self.key)
        if not node:
            return False
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            log.debug("hidraw %s: %s", node, exc)
            return False
        self.hid_fd = fd
        self.tp = Touchpad(self.d.cfg, self.d.mode, self.d.out)
        self.hid = hidraw.HidrawTouch(self.tp)
        self.d.loop.add_reader(fd, self._hid_read)
        log.info("touchpad via %s (fallback)", node)
        self.ensure_kwin_off()
        for delay in (0.5, 1.5, 3.0):
            self.d.loop.call_later(delay, self.ensure_kwin_off)
        return True

    def ensure_kwin_off(self):
        """Keep KDE from also driving the cursor with this touchpad. The
        kernel creates the touchpad node a little after the gamepad node and
        KWin registers it later still, so this is retried on every rescan."""
        bus = self.d.bus
        if self.hid is None or self.kwin_off or not bus or not self.d.cfg.grab_touchpad:
            return
        sysname = hidraw.touchpad_sysname(self.key)
        if not sysname:
            return
        try:
            if bus.kwin_input_enabled(sysname):
                bus.kwin_input_enabled(sysname, False)
            self.kwin_off = sysname
            log.info("KWin touchpad %s disabled while couchpad runs", sysname)
        except Exception as exc:
            log.debug("KWin touchpad %s not ready: %s", sysname, exc)

    def _hid_read(self):
        t = time.monotonic()
        try:
            while True:
                report = os.read(self.hid_fd, 128)
                if not report:
                    raise OSError("eof")
                self.hid.feed(report, t)
            if self.tp and self.tp.slots:
                self.last_input = t
        except BlockingIOError:
            pass
        except OSError:
            self.detach_hidraw()

    def detach_hidraw(self):
        if self.hid_fd is None:
            return
        try:
            self.d.loop.remove_reader(self.hid_fd)
        except Exception:
            pass
        try:
            os.close(self.hid_fd)
        except OSError:
            pass
        self.hid_fd = None
        self.hid = None
        if self.tp:
            self.tp.reset()
            self.tp = None
        if self.kwin_off and self.d.bus:
            try:
                self.d.bus.kwin_input_enabled(self.kwin_off, True)
            except Exception:
                pass   # device already gone with the controller
        self.kwin_off = None

    def attach(self, dev, role):
        if role == "gamepad":
            self.gamepad = dev
            self.uniq = dev.uniq
            self.rumble = Rumble(dev, self.d.loop, self.d.cfg.rumble and not self.d.dry,
                                 self.d.cfg.haptic_strength)
            self.hd = self._make_hd(dev)
            self.bluetooth = dev.info.bustype == 0x05
            self.last_input = time.monotonic()
            if not self.d.dry:
                node = hidraw.hidraw_node(self.key)
                uniq = dev.uniq
                self.lights = Lights(self.d.cfg, self.key,
                                     node if node and os.access(node, os.W_OK) else None,
                                     self.bluetooth, lambda: system.battery(uniq))
                self.lights.set_mouse(self.d.mode.mouse)
                # The driver paints the bar on connect and Steam may follow:
                # re-apply a few times.
                for delay in (0.0, 1.0, 3.0, 6.0):
                    self.d.loop.call_later(delay, self._relight)
            acts = ControllerActions(self.d.services, self.rumble, dev.uniq, self)
            self.ctl = Controller(self.d.cfg, self.d.mode, self.d.out, acts)
            self.absinfo = {code: dev.absinfo(code) for code in STICKS}
            self.hat = {e.ABS_HAT0X: 0, e.ABS_HAT0Y: 0}
            self.frame_keys = []
            self.tasks.append(self.d.loop.create_task(self._read(dev, self._gamepad_event)))
            log.info("gamepad %s (%s)", dev.path, dev.name)
        else:
            self.detach_hidraw()      # the real evdev node wins
            self.touchpad = dev
            x = dev.absinfo(e.ABS_MT_POSITION_X)
            y = dev.absinfo(e.ABS_MT_POSITION_Y)
            self.tp = Touchpad(self.d.cfg, self.d.mode, self.d.out,
                               width=x.max + 1, height=y.max + 1)
            if self.d.cfg.grab_touchpad:
                try:
                    dev.grab()
                except OSError as exc:
                    log.warning("cannot grab touchpad %s: %s", dev.path, exc)
            self.tasks.append(self.d.loop.create_task(self._read(dev, self._touch_event)))
            log.info("touchpad %s (%s)", dev.path, dev.name)

    async def _read(self, dev, handler):
        try:
            async for ev in dev.async_read_loop():
                handler(ev)
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            self.d.detach(self, dev)

    def _relight(self):
        if self.lights:
            self.lights.reload()
            self.d.kick_lights()

    def remake_hd(self):
        if self.hd:
            self.hd.close()
        self.hd = self._make_hd(self.gamepad) if self.gamepad else None

    def _gamepad_event(self, ev):
        t = time.monotonic()
        ctl = self.ctl
        if ev.type == e.EV_KEY and ev.code in EVDEV_BUTTONS:
            if ev.value in (0, 1):
                self.frame_keys.append((EVDEV_BUTTONS[ev.code], ev.value == 1))
                self.last_input = t
            return
        if ev.type == e.EV_SYN and ev.code == e.SYN_REPORT:
            self.flush_keys(t)
        elif ev.type == e.EV_ABS:
            if ev.code in self.hat:
                old = self.hat[ev.code]
                if old:
                    self.frame_keys.append((HAT[(ev.code, old)], False))
                self.hat[ev.code] = ev.value
                if ev.value:
                    self.frame_keys.append((HAT[(ev.code, ev.value)], True))
            elif ev.code in STICKS:
                ai = self.absinfo[ev.code]
                mid = (ai.max + ai.min) / 2
                v = (ev.value - mid) / ((ai.max - ai.min) / 2)
                if abs(v) > 0.3:
                    self.last_input = t
                ctl.axis(STICKS[ev.code], max(-1.0, min(1.0, v)), t)
        self.d.kick()

    def flush_keys(self, t):
        """Buttons that change in one report arrive in key-code order
        (○ before Share). Apply Share presses first and Share releases last
        so "Share + ○ together" is always a chord."""
        keys, self.frame_keys = self.frame_keys, []
        keys.sort(key=lambda k: (0 if k[0] == "share" and k[1] else
                                 2 if k[0] == "share" else 1))
        for name, pressed in keys:
            self.ctl.button(name, pressed, t)

    def _touch_event(self, ev):
        self.last_input = time.monotonic()
        if self.tp:
            self.tp.event(ev.type, ev.code, ev.value, ev.timestamp())

    def remove(self, dev):
        if dev is self.gamepad:
            self.detach_hidraw()
            if self.hd:
                self.hd.close()
                self.hd = None
            if self.ctl:
                self.ctl.reset()
            if self.rumble:
                self.rumble.close()
            self.gamepad = self.ctl = self.rumble = self.lights = None
        elif dev is self.touchpad:
            if self.tp:
                self.tp.reset()
            try:
                dev.ungrab()
            except OSError:
                pass
            self.touchpad = self.tp = None
        try:
            dev.close()
        except OSError:
            pass

    def empty(self):
        return self.gamepad is None and self.touchpad is None


class Daemon:
    def __init__(self, cfg, dry=False, match_name=None, out=None, use_bus=True):
        self.cfg = cfg
        self.dry = dry
        self.match_name = match_name
        self.mode = Mode()
        self.out = out
        self.use_bus = use_bus
        self.bus = None
        self.pads = {}            # hid parent -> Pad
        self.paths = {}           # device path -> Pad
        self.loop = None
        self.wake = None
        self.services = Services(self)
        self.events = []          # dry-run action log
        self.stopping = False
        self.battery_warned = {}
        self.light_wake = None
        self.config_mtime = None

    # -- helpers used by Services / engine --------------------------------------
    def record(self, what):
        self.events.append(what)
        del self.events[:-50]
        if self.dry:
            log.info("dry action: %s", what)

    def call_soon(self, fn, *args):
        self.loop.call_soon_threadsafe(fn, *args)

    def set_mouse(self, on, quiet=False):
        for pad in self.pads.values():
            if pad.ctl:
                pad.ctl.set_mouse(on, quiet)
                return
        if self.mode.mouse != on:
            self.mode.mouse = on
            self.on_mouse_mode(on)

    def kick_lights(self):
        if self.light_wake and not self.light_wake.is_set():
            self.loop.call_soon_threadsafe(self.light_wake.set)

    def on_mouse_mode(self, on):
        for pad in self.pads.values():
            if pad.lights:
                pad.lights.set_mouse(on)
        self.kick_lights()
        if not on:
            for pad in self.pads.values():
                if pad.tp:
                    pad.tp.reset()
            self.out.release_all()

    def kick(self):
        if self.wake and not self.wake.is_set():
            self.wake.set()

    # -- devices ---------------------------------------------------------------
    def classify(self, dev):
        if self.match_name:
            if not dev.name.startswith(self.match_name):
                return None
        elif dev.info.vendor != SONY or dev.info.product not in PRODUCTS:
            return None
        if dev.name.endswith("Motion Sensors"):
            return None
        return "touchpad" if dev.name.endswith("Touchpad") else "gamepad"

    def scan(self):
        for path in evdev.list_devices():
            if path in self.paths:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            role = self.classify(dev)
            if role is None:
                dev.close()
                continue
            key = hid_parent(path) or dev.uniq or path
            pad = self.pads.get(key)
            if pad is None:
                pad = self.pads[key] = Pad(self, key)
            if (role == "gamepad" and pad.gamepad) or (role == "touchpad" and pad.touchpad):
                dev.close()
                continue
            pad.attach(dev, role)
            self.paths[path] = pad
            if role == "gamepad" and not self.dry:
                self.services.show_battery(system.battery(dev.uniq), _("DualSense подключён"))
        if not self.match_name:
            for pad in self.pads.values():
                if pad.gamepad and not pad.touchpad and pad.hid is None:
                    pad.attach_hidraw()
                pad.ensure_kwin_off()

    def detach(self, pad, dev):
        path = getattr(dev, "path", None)
        self.paths.pop(path, None)
        was_gamepad = dev is pad.gamepad
        pad.remove(dev)
        if pad.empty():
            self.pads.pop(pad.key, None)
        if was_gamepad:
            log.info("gamepad removed")
            if not self.stopping:
                self.services.notify("conn", _("DualSense отключён"), "", "ph:game-controller",
                                     "#8a93a6")
            if not any(p.ctl for p in self.pads.values()) and self.mode.mouse:
                self.mode.mouse = False
                self.out.release_all()

    async def udev_watch(self):
        try:
            import pyudev
        except ImportError:
            pyudev = None
        if pyudev is None:
            while True:
                await asyncio.sleep(2)
                self.scan()
        ctx = pyudev.Context()
        mon = pyudev.Monitor.from_netlink(ctx)
        mon.filter_by("input")
        mon.start()
        changed = asyncio.Event()

        def readable():
            while mon.poll(timeout=0):
                changed.set()
        self.loop.add_reader(mon.fileno(), readable)
        while True:
            try:
                await asyncio.wait_for(changed.wait(), timeout=10)
                # Give udev a moment to apply the uaccess ACL.
                await asyncio.sleep(0.4)
            except asyncio.TimeoutError:
                pass
            changed.clear()
            self.scan()

    async def ticker(self):
        while True:
            fast = False
            now = time.monotonic()
            for pad in list(self.pads.values()):
                if pad.ctl:
                    pad.ctl.tick(now)
                    fast = fast or pad.ctl.needs_fast_tick()
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), 0.008 if fast else 0.25)
            except asyncio.TimeoutError:
                pass

    async def light_loop(self):
        self.light_wake = asyncio.Event()
        while True:
            now = time.monotonic()
            fast = False
            for pad in list(self.pads.values()):
                if pad.lights:
                    try:
                        pad.lights.tick(now)
                    except Exception:
                        log.exception("lights")
                        pad.lights = None
                        continue
                    fast = fast or pad.lights.animating(now)
            self.light_wake.clear()
            try:
                await asyncio.wait_for(self.light_wake.wait(), 1 / 25 if fast else 1.0)
            except asyncio.TimeoutError:
                pass

    async def config_watch(self):
        """Pick up config.toml changes (control center or hand edits)."""
        while True:
            await asyncio.sleep(1.5)
            try:
                mtime = os.stat(config_mod.CONFIG_PATH).st_mtime_ns
            except OSError:
                mtime = None
            if self.config_mtime is None:
                self.config_mtime = mtime or 0
            elif mtime != self.config_mtime:
                self.config_mtime = mtime
                self.reload()

    def reload(self):
        try:
            new = config_mod.load()
        except Exception as exc:
            log.warning("config not reloaded: %s", exc)
            self.services.notify("cfg", _("Ошибка в config.toml"), str(exc)[:80], "ph:warning")
            return False
        old_haptics = (self.cfg.rumble, self.cfg.haptics, self.cfg.haptic_strength)
        for f in fields(config_mod.Config):
            setattr(self.cfg, f.name, getattr(new, f.name))
        i18n.set_lang(self.cfg.language)
        for pad in self.pads.values():
            if pad.rumble:
                pad.rumble.enabled = self.cfg.rumble and not self.dry
                pad.rumble.strength = max(0.0, min(self.cfg.haptic_strength, 3.0))
            if (self.cfg.rumble, self.cfg.haptics, self.cfg.haptic_strength) != old_haptics:
                pad.remake_hd()
            if pad.lights:
                pad.lights.reload()
        self.kick_lights()
        log.info("config reloaded")
        return True

    async def battery_watch(self):
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            for pad in list(self.pads.values()):
                if not pad.gamepad:
                    continue
                if (self.cfg.idle_off > 0 and pad.bluetooth and pad.ctl
                        and now - pad.last_input > self.cfg.idle_off * 60):
                    log.info("idle for %.0f min: switching the pad off", self.cfg.idle_off)
                    pad.last_input = now
                    self.services.background(self.services.power_off, pad.ctl.actions)
                    continue
                info = system.battery(pad.uniq)
                if not info:
                    continue
                cap, status = info
                level = 10 if cap <= 10 else 20 if cap <= 20 else None
                warned = self.battery_warned.get(pad.uniq)
                if status != "Discharging" or level is None:
                    self.battery_warned.pop(pad.uniq, None)
                elif warned != level:
                    self.battery_warned[pad.uniq] = level
                    self.services.notify("bat", _("Геймпад садится · {cap}%").format(cap=cap),
                                         _("Поставьте его на зарядку"), "ph:battery-warning",
                                         "#ff4545", cap)

    # -- control (couchpad ctl ...) ------------------------------------------
    def command(self, cmd):
        fut = asyncio.run_coroutine_threadsafe(self._command(cmd), self.loop)
        return fut.result(2)

    async def _command(self, cmd):
        parts = cmd.split()
        if not parts:
            return "empty"
        if parts[0] == "status":
            return json.dumps(self.status())
        if parts[0] == "reload":
            return "ok" if self.reload() else "error"
        if parts[0] == "light-preview" and len(parts) == 2:
            now = time.monotonic()
            for p in self.pads.values():
                if p.lights:
                    p.lights.show_preview(parts[1], now)
            self.kick_lights()
            return "ok"
        if parts[0] == "osd" and len(parts) >= 2:
            self.services.notify("test", cmd.split(None, 1)[1], _("Так выглядят сообщения"),
                                 "ph:game-controller")
            return "ok"
        if parts[0] == "action" and len(parts) == 2 and parts[1] in ACTIONS:
            name = parts[1]
            ctl = next((p.ctl for p in self.pads.values() if p.ctl), None)
            if name == "mouse_toggle":
                self.set_mouse(not self.mode.mouse)
            elif ctl:
                ctl.run_action(name)
            elif name in ControllerActions.THREADED:
                self.services.background(getattr(self.services, name),
                                         ControllerActions(self.services, None, ""))
            else:
                return "no controller"
            return "ok"
        if parts[0] == "mouse" and len(parts) == 2:
            on = {"on": True, "off": False, "toggle": not self.mode.mouse}.get(parts[1])
            if on is None:
                return "usage: mouse on|off|toggle"
            self.set_mouse(on)
            return "mouse " + ("on" if self.mode.mouse else "off")
        if parts[0] == "haptic-warm":
            # the control center's Feedback page keeps the channel awake
            n = sum(1 for p in self.pads.values() if p.hd and p.hd.warm())
            return f"warm {n}"
        if parts[0] == "haptic" and len(parts) == 2:
            # feel the patterns: couchpad haptic demo | couchpad haptic fire
            names = list(HAPTICS) if parts[1] == "demo" else [parts[1]]
            if any(n not in HAPTICS for n in names):
                return "patterns: " + " ".join(HAPTICS)
            pads = [p for p in self.pads.values() if p.ctl]
            for k, name in enumerate(names):
                for pad in pads:
                    self.loop.call_later(k * 1.2, pad.ctl.actions.feedback, name)
            return " ".join(names)
        if parts[0] == "wheel-items":
            # tests: temporarily replace the wheel items ("reset" = config)
            rest = cmd.split(None, 1)[1] if len(parts) > 1 else "reset"
            if rest == "reset":
                self.cfg.wheel = config_mod.load().wheel
            else:
                self.cfg.wheel = json.loads(rest)
            return "ok"
        if parts[0] == "wheel-state":
            ui = self.services.wheel_ui
            return json.dumps({"open": self.mode.wheel,
                               "shown": bool(ui and ui.state["shown"]),
                               "geo": ui.state["geo"] if ui else None,
                               "overlay": bool(ui and ui.osd)})
        if parts[0] == "clear-events":
            self.events.clear()
            return "ok"
        return "unknown command"

    def status(self):
        pads = []
        for p in self.pads.values():
            if not p.gamepad:
                continue
            bat = system.battery(p.uniq)
            pads.append({
                "uniq": p.uniq, "name": p.gamepad.name, "gamepad": p.gamepad.path,
                "touchpad": p.touchpad.path if p.touchpad else ("hidraw" if p.hid else None),
                "bluetooth": p.bluetooth,
                "battery": bat[0] if bat else None,
                "battery_status": bat[1] if bat else None,
                "hd_haptics": bool(p.hd and not p.hd.failed),
                "lightbar": bool(p.lights and p.lights.led),
                "light": list(p.lights.last) if p.lights and p.lights.last else None,
                "idle": round(time.monotonic() - p.last_input),
            })
        return {"version": __version__, "mouse": self.mode.mouse, "wheel": self.mode.wheel,
                "controllers": pads, "overlay": bool(self.services.wheel_ui and
                                                     self.services.wheel_ui.osd),
                "events": self.events[-50:]}

    # -- main --------------------------------------------------------------------
    async def run(self, stop=None):
        self.loop = asyncio.get_running_loop()
        self.wake = asyncio.Event()
        if self.out is None:
            self.out = system.UinputOutput()
        if self.use_bus:
            try:
                self.bus = system.Bus(on_command=self.command)
            except Exception as exc:
                log.warning("no session bus: %s", exc)
        if stop is None:
            stop = asyncio.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                self.loop.add_signal_handler(sig, stop.set)
        self.scan()
        tasks = [self.loop.create_task(c) for c in
                 (self.udev_watch(), self.ticker(), self.battery_watch(),
                  self.light_loop(), self.config_watch())]
        self.services.warm_up_wheel()
        log.info("couchpad running (session: %s)", system.session_kind())
        await stop.wait()
        self.shutdown(tasks)

    def shutdown(self, tasks=()):
        self.stopping = True
        for t in tasks:
            t.cancel()
        for pad in list(self.pads.values()):
            pad.detach_hidraw()
            for dev in (pad.gamepad, pad.touchpad):
                if dev:
                    for task in pad.tasks:
                        task.cancel()
                    pad.remove(dev)
        self.pads.clear()
        if self.services.wheel_ui:
            self.services.wheel_ui.close()
        if self.out:
            self.out.close()
        if self.bus:
            self.bus.close()
        log.info("couchpad stopped")


def ctl(args):
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    try:
        res = bus.call_sync(system.BUS_NAME, system.OBJ_PATH, system.BUS_NAME,
                            "Command", GLib.Variant("(s)", (" ".join(args),)),
                            None, 0, 3000, None)
    except GLib.Error as exc:
        print("couchpad is not running:", exc.message, file=sys.stderr)
        return 1
    print(res.unpack()[0])
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["app"]:
        # the control center has its own flags (--tray, --quit)
        from .app.main import main as app_main
        return app_main(argv[1:])
    p = argparse.ArgumentParser(prog="couchpad")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="log window/system actions instead of doing them")
    p.add_argument("--match-name", help=argparse.SUPPRESS)   # tests
    p.add_argument("--write-config", action="store_true",
                   help="create ~/.config/couchpad/config.toml with defaults")
    p.add_argument("--version", action="version", version=f"couchpad {__version__}")
    p.add_argument("ctl", nargs="*",
                   help="app [--tray] | status | mouse on|off|toggle | reload | action NAME | "
                        "haptic demo|NAME | steam-layout status|neutral|restore")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    if a.ctl and a.ctl[0] == "steam-layout":
        from . import steamcfg
        sub = a.ctl[1] if len(a.ctl) > 1 else "status"
        if sub in ("neutral", "restore") and system.steam_running():
            print("Steam is running: quit it first (steam -shutdown)", file=sys.stderr)
            return 1
        if sub == "neutral":
            print("\n".join(steamcfg.neutralize()) or "already neutral")
        elif sub == "restore":
            print("\n".join(steamcfg.restore()) or "nothing to restore")
        else:
            for path, neutral in steamcfg.status().items():
                print("neutral " if neutral else "steam   ", path)
        return 0
    if a.ctl:
        return ctl(a.ctl)
    if a.write_config:
        path = config_mod.CONFIG_PATH
        if os.path.exists(path):
            print("exists:", path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(config_mod.DEFAULT_FILE)
            print("written:", path)
        return 0
    cfg = config_mod.load()
    i18n.set_lang(cfg.language)
    asyncio.run(Daemon(cfg, dry=a.dry_run, match_name=a.match_name).run())
    return 0
