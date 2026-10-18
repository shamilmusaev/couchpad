"""Pure input logic: no devices, no D-Bus, no real clock.

`Controller` turns DualSense button/stick events into gestures and, in mouse
mode, into mouse/keyboard output. `Touchpad` turns raw multitouch frames into
pointer motion, taps, clicks and scrolling. Both talk to the outside world
only through the `Output` and `Actions` objects they are given, which makes
them fully testable with fakes and an injected time value.
"""

import math
from evdev import ecodes as e

from .actions import REPEATING as REPEATING_CHORDS, chords as chord_map
from .i18n import _

# Abstract button names used by the engine.
BUTTONS = ("cross", "circle", "triangle", "square", "l1", "r1", "l2", "r2",
           "share", "options", "ps", "l3", "r3", "up", "down", "left", "right")

EVDEV_BUTTONS = {
    e.BTN_SOUTH: "cross", e.BTN_EAST: "circle", e.BTN_NORTH: "triangle",
    e.BTN_WEST: "square", e.BTN_TL: "l1", e.BTN_TR: "r1", e.BTN_TL2: "l2",
    e.BTN_TR2: "r2", e.BTN_SELECT: "share", e.BTN_START: "options",
    e.BTN_MODE: "ps", e.BTN_THUMBL: "l3", e.BTN_THUMBR: "r3",
}

# Share + button -> action name (on press) comes from actions.chords(cfg.chords).
# ○ / △ are short/long presses and R1 is the wheel; those are handled here.

DPAD = ("up", "down", "left", "right")

# Mouse mode: button -> ("mouse", name) | ("key", code) | ("action", name)
MOUSE_MODE_MAP = {
    "cross": ("mouse", "left"),
    "r2": ("mouse", "left"),
    "circle": ("mouse", "right"),
    "l2": ("mouse", "right"),
    "square": ("mouse", "middle"),
    "triangle": ("action", "keyboard"),
    "l1": ("key", e.KEY_BACK),
    "r1": ("mouse", "right"),
    "up": ("key", e.KEY_UP),
    "down": ("key", e.KEY_DOWN),
    "left": ("key", e.KEY_LEFT),
    "right": ("key", e.KEY_RIGHT),
    "options": ("key", e.KEY_LEFTMETA),
    "l3": ("key", e.KEY_ENTER),
    "r3": ("key", e.KEY_ESC),
}


class Mode:
    """State shared by every connected controller."""

    def __init__(self):
        self.mouse = False
        self.wheel = False        # quick-launch wheel on screen


class Controller:
    REPEAT_DELAY = 0.40
    REPEAT_RATE = 0.12

    def __init__(self, cfg, mode, out, actions):
        self.cfg = cfg
        self.mode = mode
        self.out = out
        self.actions = actions
        self.held = set()             # buttons physically held
        self.consumed = set()         # presses whose release we must swallow
        self.mouse_held = {}          # button -> output it produced
        self.share_down_t = None
        self.share_chorded = False
        self.last_tap_t = None
        self.long = None              # {"button", "action", "t", "fired"}
        self.repeat = None            # {"button", "action", "next"}
        self.alt_tab = False
        self.alt_tab_t = 0.0
        self.axes = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0}
        self.stick_latch = 0          # alt-tab stick flick hysteresis
        self.acc = [0.0, 0.0, 0.0, 0.0]   # sub-unit remainders x, y, vs, hs
        self.last_tick = None
        self.press_t = {}
        self.wheel = None             # {"n": items, "sel": index | None}
        self.dpad_free = (-1e9, None)  # (time, direction) the d-pad was last let go

    # Share pressed this soon after ○/△ still counts as "Share + ○/△".
    LATE_SHARE = 0.15

    # ---------------------------------------------------------------- input
    def button(self, name, pressed, t):
        if pressed:
            if name in self.held:
                return
            self.held.add(name)
            self.press_t[name] = t
        else:
            if name not in self.held:
                return
            self.held.discard(name)

        if name == "share":
            self._share(pressed, t)
            return

        if name in DPAD and not pressed and not any(d in self.held for d in DPAD):
            self.dpad_free = (t, name)

        if self.wheel and name not in self.consumed:
            # The wheel owns the pad while it is open (Share may still be held).
            if pressed and not self._dpad_echo(name, t):
                self._wheel_button(name)
            return

        if pressed and self.share_down_t is not None:
            self.share_chorded = True
            self.last_tap_t = None
            self.consumed.add(name)
            self._chord(name, t)
            return

        if not pressed and name in self.consumed:
            self.consumed.discard(name)
            self._chord_release(name, t)
            return

        if self.alt_tab:
            if pressed and not self._dpad_echo(name, t):
                self._alt_tab_button(name, t)
            return

        if self.mode.mouse:
            self._mouse_button(name, pressed)

    def axis(self, name, value, t):
        """Sticks normalised to -1..1."""
        self.axes[name] = value
        if self.wheel:
            self._wheel_aim()
            return
        if self.alt_tab and name == "lx":
            if self.stick_latch == 0 and abs(value) > 0.6:
                self.stick_latch = 1 if value > 0 else -1
                self._alt_tab_step(reverse=value < 0, t=t)
            elif abs(value) < 0.3:
                self.stick_latch = 0

    # ------------------------------------------------------------ share
    def _share(self, pressed, t):
        cfg = self.cfg
        if pressed:
            self.share_down_t = t
            self.share_chorded = False
            self.actions.warm_haptics()     # every gesture starts here
            self._late_chord(t)
            return
        down_t, self.share_down_t = self.share_down_t, None
        if self.long and not self.long["fired"]:
            # Long press needs Share held the whole time.
            if self.long["action"] == "minimize":
                self.long["share_released"] = True
                self._hold_end(False)       # becomes the window switcher
            else:
                self._hold_end(False)
                self.long = None
                self.actions.feedback("cancel")
        if self.repeat:
            self.repeat = None
        if self.share_chorded or down_t is None or t - down_t > cfg.tap_max:
            self.last_tap_t = None
            return
        if self.last_tap_t is not None and t - self.last_tap_t <= cfg.double_tap_window:
            self.last_tap_t = None
            self.set_mouse(not self.mode.mouse)
        else:
            self.last_tap_t = t

    def _late_chord(self, t):
        """○/△ went down a moment before Share (pressed together): treat it
        as the chord anyway, undoing what the early press did."""
        if self.alt_tab:
            return
        for name in ("circle", "triangle"):
            if (name in self.held and name not in self.consumed
                    and t - self.press_t.get(name, -1e9) <= self.LATE_SHARE):
                target = self.mouse_held.pop(name, None)
                if target:
                    self._emit(target, False)
                self.share_chorded = True
                self.last_tap_t = None
                self.consumed.add(name)
                self._chord(name, t)
                return

    def _chord(self, name, t):
        if name == "circle":
            if self.alt_tab:
                self._alt_tab_step(reverse=False, t=t)
                return
            self._hold(name, "minimize", t)
            return
        if name == "triangle":
            self._hold(name, "force_close", t)
            return
        if name == "r1":
            if self.alt_tab:
                return
            # Opens at once and stays open: aim with either stick, ✕ / L3 / R3 launch.
            self.long = {"button": name, "action": "wheel", "t": t, "fired": True}
            self._wheel_open()
            if not self.wheel:
                self.long = None
            return
        action = chord_map(self.cfg.chords).get(name)
        if action is None or action == "none":
            return
        if action == "mouse_toggle":
            self.set_mouse(not self.mode.mouse)
            return
        if action in REPEATING_CHORDS:
            self.actions.feedback("detent")
        self._do(action)
        if action in REPEATING_CHORDS:
            self.repeat = {"button": name, "action": action,
                           "next": t + self.REPEAT_DELAY}

    def _hold(self, name, action, t):
        self._hold_end(False)
        self.long = {"button": name, "action": action, "t": t, "fired": False}
        self.actions.feedback("tick")
        self.actions.hold(action, self.cfg.long_press)

    def _hold_end(self, done, long=None):
        """Tell the progress ring whether a pending hold fired or was let go."""
        long = long or self.long
        if long and long["action"] in ("minimize", "force_close") and not long.get("ended"):
            long["ended"] = True
            self.actions.hold_end(done)

    def _chord_release(self, name, t):
        if self.repeat and self.repeat["button"] == name:
            self.repeat = None
        if not self.long or self.long["button"] != name:
            return
        long, self.long = self.long, None
        if long["action"] == "wheel":
            return                      # releasing R1 picks nothing: ✕ / L3 / R3 do
        if long["fired"]:
            return
        self._hold_end(False, long)
        if long["action"] == "minimize":
            self._alt_tab_open(t)
        elif long["action"] == "force_close":
            self.actions.hint(_("Удерживайте Share + △ {s} с, чтобы закрыть игру").format(
                s=f"{self.cfg.long_press:g}"))

    # ---------------------------------------------------------- alt-tab
    def _alt_tab_open(self, t):
        self._release_mouse_outputs()
        self.alt_tab = True
        self.alt_tab_t = t
        self.actions.switcher_opened(self)
        self.actions.feedback("open")
        self.out.key(e.KEY_LEFTALT, True)
        self.out.sync()
        self.out.tap(e.KEY_TAB)
        self.out.sync()

    def _alt_tab_step(self, reverse, t):
        self.alt_tab_t = t
        self.actions.switcher_step(reverse)
        self.actions.feedback("step", -0.8 if reverse else 0.8)
        if reverse:
            self.out.key(e.KEY_LEFTSHIFT, True)
            self.out.sync()
            self.out.tap(e.KEY_TAB)
            self.out.sync()
            self.out.key(e.KEY_LEFTSHIFT, False)
        else:
            self.out.tap(e.KEY_TAB)
        self.out.sync()

    def _alt_tab_close(self, cancel):
        if not self.alt_tab:
            return
        self.actions.feedback("cancel" if cancel else "confirm")
        if cancel:
            self.out.tap(e.KEY_ESC)
        self.out.key(e.KEY_LEFTALT, False)
        self.out.sync()
        self.alt_tab = False
        self.stick_latch = 0
        self.actions.after_switch(cancelled=cancel)

    # The DualSense d-pad is a rocker: pressing → often reports →↓ for a few
    # milliseconds, and a quick press can bounce. In menus that step, only a
    # press from "nothing held" counts.
    DPAD_BOUNCE = 0.05

    def _dpad_echo(self, name, t):
        if name not in DPAD:
            return False
        if any(d in self.held for d in DPAD if d != name):
            return True                         # diagonal while rocking
        last_t, last = self.dpad_free
        return name == last and t - last_t < self.DPAD_BOUNCE   # contact bounce

    def switcher_gone(self):
        """KWin closed its switcher by itself: release Alt, send nothing else."""
        if not self.alt_tab:
            return
        self.out.key(e.KEY_LEFTALT, False)
        self.out.key(e.KEY_LEFTSHIFT, False)
        self.out.sync()
        self.alt_tab = False
        self.stick_latch = 0
        self.actions.after_switch(cancelled=True)

    def _alt_tab_button(self, name, t):
        if name in ("right", "down", "r1"):
            self._alt_tab_step(False, t)
        elif name in ("left", "up", "l1"):
            self._alt_tab_step(True, t)
        elif name in ("cross", "r2"):
            self._alt_tab_close(cancel=False)
            self.consumed.add(name)   # don't leak the release into mouse mode
        elif name in ("circle", "l2"):
            self._alt_tab_close(cancel=True)
            self.consumed.add(name)

    # ------------------------------------------------------------ wheel
    def _wheel_open(self):
        self._release_mouse_outputs()
        n = self.actions.wheel("open")
        if not n:
            return
        self.wheel = {"n": n, "sel": None}
        self.mode.wheel = True
        self.actions.feedback("open")
        self._wheel_aim()

    def _wheel_aim(self):
        from .wheel import sector
        w = self.wheel
        # Either stick aims; the one pushed further wins.
        x, y = max(((self.axes["lx"], self.axes["ly"]), (self.axes["rx"], self.axes["ry"])),
                   key=lambda v: math.hypot(*v))
        i = sector(x, y, w["n"])
        if i is not None and i != w["sel"]:
            w["sel"] = i
            self.actions.feedback("detent", self._wheel_pan(i))
            self.actions.wheel("select", i)

    def _wheel_pan(self, i):
        """Click on the side of the controller where the sector is."""
        return math.sin(math.radians(i * 360.0 / self.wheel["n"]))

    def _wheel_step(self, d):
        w = self.wheel
        w["sel"] = 0 if w["sel"] is None else (w["sel"] + d) % w["n"]
        self.actions.feedback("detent", self._wheel_pan(w["sel"]))
        self.actions.wheel("select", w["sel"])

    def _wheel_button(self, name):
        if name in ("right", "down"):
            self._wheel_step(1)
        elif name in ("left", "up"):
            self._wheel_step(-1)
        elif name in ("cross", "l3", "r3", "r2"):
            if self.wheel["sel"] is None:
                return                  # nothing aimed yet
            self._wheel_close(launch=True)
            self.consumed.add(name)
        elif name in ("circle", "l2"):
            self._wheel_close(launch=False)
            self.consumed.add(name)

    def wheel_external(self, event, i=None):
        """Mouse/keyboard input from the wheel window itself."""
        if not self.wheel:
            return
        if event == "select" and i is not None:
            self.wheel["sel"] = i
        elif event == "launch" and i is not None:
            self.wheel["sel"] = i
            self._wheel_close(launch=True)
        elif event == "cancel":
            self._wheel_close(launch=False)

    def _wheel_close(self, launch):
        if not self.wheel:
            return
        w, self.wheel = self.wheel, None
        self.mode.wheel = False
        if launch and w["sel"] is not None:
            self.actions.feedback("launch")
            self.actions.wheel("launch", w["sel"])
        else:
            self.actions.feedback("cancel")
            self.actions.wheel("cancel")
        # R1 may still be held after ✕/○: forget it.
        if self.long and self.long.get("action") == "wheel":
            self.long = None

    # ------------------------------------------------------- mouse mode
    def set_mouse(self, on, quiet=False):
        if on == self.mode.mouse:
            return
        if not on:
            self._release_mouse_outputs()
        self.mode.mouse = on
        if quiet:
            self.actions.mouse_mode(on, quiet=True)
        else:
            self.actions.mouse_mode(on)

    def _mouse_button(self, name, pressed):
        target = MOUSE_MODE_MAP.get(name)
        if target is None:
            return
        kind, what = target
        if pressed:
            if kind == "action":
                self._do(what)
                return
            self.mouse_held[name] = target
            self._emit(target, True)
        else:
            target = self.mouse_held.pop(name, None)
            if target:
                self._emit(target, False)

    def _emit(self, target, down):
        kind, what = target
        if kind == "mouse":
            self.out.mouse_button(what, down)
        else:
            self.out.key(what, down)
        self.out.sync()

    def _release_mouse_outputs(self):
        for target in self.mouse_held.values():
            kind, what = target
            if kind == "mouse":
                self.out.mouse_button(what, False)
            else:
                self.out.key(what, False)
        if self.mouse_held:
            self.out.sync()
        self.mouse_held.clear()

    # ----------------------------------------------------------- timing
    def needs_fast_tick(self):
        if self.long or self.repeat:
            return True
        if self.mode.mouse and not self.alt_tab and not self.wheel:
            dz = self.cfg.stick_deadzone
            return any(math.hypot(self.axes[a], self.axes[b]) > dz
                       for (a, b), _idx, _speed in self._stick_roles())
        return False

    def _stick_roles(self):
        """Which sticks drive the mouse: cfg.stick_mouse = both | scroll | off."""
        cfg = self.cfg
        roles = []
        if cfg.stick_mouse == "both":
            roles.append((("lx", "ly"), 0, cfg.stick_pointer_speed))
        if cfg.stick_mouse in ("both", "scroll"):
            roles.append((("rx", "ry"), 2, cfg.stick_scroll_speed))
        return roles

    def tick(self, t):
        dt = 0.0 if self.last_tick is None else min(max(t - self.last_tick, 0.0), 0.05)
        self.last_tick = t
        cfg = self.cfg

        if self.long and not self.long["fired"]:
            elapsed = t - self.long["t"]
            if self.long.get("share_released"):
                pass        # will become a short press on release
            elif elapsed < cfg.long_press:
                # three rising ticks spread over the hold
                step = int(elapsed / cfg.long_press * 4)
                if 1 <= step <= 3 and step > self.long.get("ticks", 0):
                    self.long["ticks"] = step
                    self.actions.feedback(f"progress{step}")
            else:
                self.long["fired"] = True
                self._hold_end(True)
                self.actions.feedback("fire")
                self._do(self.long["action"])

        if self.repeat and t >= self.repeat["next"]:
            self.actions.feedback("detent")
            self._do(self.repeat["action"])
            self.repeat["next"] = t + self.REPEAT_RATE

        if self.alt_tab and t - self.alt_tab_t >= cfg.alt_tab_timeout:
            self._alt_tab_close(cancel=False)

        if self.mode.mouse and not self.alt_tab and not self.wheel and dt > 0:
            self._sticks(dt)

    def _sticks(self, dt):
        cfg = self.cfg
        moved = False
        for (ax, ay), idx, speed in self._stick_roles():
            x, y = self.axes[ax], self.axes[ay]
            m = math.hypot(x, y)
            if m <= cfg.stick_deadzone:
                continue
            k = min((m - cfg.stick_deadzone) / (1 - cfg.stick_deadzone), 1.0)
            v = speed * k * k * dt / m
            if idx == 0:
                self.acc[0] += x * v
                self.acc[1] += y * v
                dx, dy = int(self.acc[0]), int(self.acc[1])
                self.acc[0] -= dx
                self.acc[1] -= dy
                if dx or dy:
                    self.out.mouse_move(dx, dy)
                    moved = True
            else:
                self.acc[2] += -y * v      # stick up = scroll up
                self.acc[3] += x * v
                vs, hs = int(self.acc[2]), int(self.acc[3])
                self.acc[2] -= vs
                self.acc[3] -= hs
                if vs or hs:
                    self.out.scroll(vs, hs)
                    moved = True
        if moved:
            self.out.sync()

    # ----------------------------------------------------------- helpers
    def run_action(self, action):
        """Run a catalogue action as if its chord had been pressed."""
        if action == "mouse_toggle":
            self.set_mouse(not self.mode.mouse)
        elif action != "none":
            self._do(action)

    def _do(self, action):
        if action in ("minimize", "force_close"):
            self._alt_tab_close(cancel=True)
        self.actions.run(action, self)

    def reset(self):
        """Controller disconnected: never leave anything pressed."""
        self._release_mouse_outputs()
        self._alt_tab_close(cancel=False)
        self._wheel_close(launch=False)
        self._hold_end(False)
        self.held.clear()
        self.consumed.clear()
        self.long = None
        self.repeat = None
        self.share_down_t = None


class Touchpad:
    """Multitouch frames -> pointer. Coordinates are raw touchpad units."""

    def __init__(self, cfg, mode, out, width=1920, height=1080):
        self.cfg = cfg
        self.mode = mode
        self.out = out
        self.width = width
        self.height = height
        self.slot = 0
        self.slots = {}           # slot -> dict(x, y, px, py, new)
        self.pending = {}         # slot -> dict of updates in this frame
        self.click_down = None    # value of BTN_LEFT in current frame
        self.clicked_button = None
        self.session = None       # tap tracking from first touch to release
        self.prev_count = 0
        self.last_t = None
        self.fdx = self.fdy = 0.0
        self.rem = [0.0, 0.0, 0.0, 0.0]
        self.suppress_until = 0.0

    # Raw evdev events ---------------------------------------------------
    def event(self, etype, code, value, t):
        if etype == e.EV_ABS:
            if code == e.ABS_MT_SLOT:
                self.slot = value
            elif code == e.ABS_MT_TRACKING_ID:
                self.pending.setdefault(self.slot, {})["id"] = value
            elif code == e.ABS_MT_POSITION_X:
                self.pending.setdefault(self.slot, {})["x"] = value
            elif code == e.ABS_MT_POSITION_Y:
                self.pending.setdefault(self.slot, {})["y"] = value
        elif etype == e.EV_KEY and code == e.BTN_LEFT:
            self.click_down = bool(value)
        elif etype == e.EV_SYN and code == e.SYN_REPORT:
            self.frame(t)

    # One complete frame -------------------------------------------------
    def frame(self, t):
        for slot, upd in self.pending.items():
            if "id" in upd and upd["id"] < 0:
                self.slots.pop(slot, None)
                continue
            s = self.slots.get(slot)
            if s is None or "id" in upd:
                s = {"x": upd.get("x", s["x"] if s else 0),
                     "y": upd.get("y", s["y"] if s else 0), "new": True}
                s["px"], s["py"] = s["x"], s["y"]
                s["sx"], s["sy"] = s["x"], s["y"]
                self.slots[slot] = s
            else:
                s["x"] = upd.get("x", s["x"])
                s["y"] = upd.get("y", s["y"])
        self.pending = {}

        dt = 0.008 if self.last_t is None else min(max(t - self.last_t, 0.002), 0.05)
        self.last_t = t
        count = len(self.slots)

        self._track_session(count, t)

        click = self.click_down
        self.click_down = None
        if not self.mode.mouse:
            self._release_click()
            self._remember_positions()
            self.prev_count = count
            return

        if click is True and self.clicked_button is None:
            self.clicked_button = "right" if count >= 2 else "left"
            self.out.mouse_button(self.clicked_button, True)
            if self.session:
                self.session["clicked"] = True
        elif click is False:
            self._release_click()

        if count != self.prev_count:
            # Finger added/removed: positions jump, skip this frame.
            self.fdx = self.fdy = 0.0
            if count < self.prev_count:
                self.suppress_until = t + 0.06
        elif count == 1 and t >= self.suppress_until:
            s = next(iter(self.slots.values()))
            if not s["new"]:
                self._pointer(s["x"] - s["px"], s["y"] - s["py"], dt)
        elif count == 2:
            a, b = self.slots.values()
            if not a["new"] and not b["new"]:
                dx = ((a["x"] - a["px"]) + (b["x"] - b["px"])) / 2
                dy = ((a["y"] - a["py"]) + (b["y"] - b["py"])) / 2
                self._scroll(dx, dy)

        self._remember_positions()
        self.prev_count = count
        self.out.sync()

    def _remember_positions(self):
        for s in self.slots.values():
            s["px"], s["py"] = s["x"], s["y"]
            s["new"] = False

    def _release_click(self):
        if self.clicked_button is not None:
            self.out.mouse_button(self.clicked_button, False)
            self.clicked_button = None
            self.out.sync()

    # Pointer ballistics ---------------------------------------------------
    def _pointer(self, dx, dy, dt):
        cfg = self.cfg
        a = cfg.pointer_smoothing
        self.fdx = a * self.fdx + (1 - a) * dx
        self.fdy = a * self.fdy + (1 - a) * dy
        dx, dy = self.fdx, self.fdy
        speed = math.hypot(dx, dy) / dt          # units per second
        # ~0.45 px/unit at slow speed; up to ~4x faster for quick swipes.
        gain = 0.45 * cfg.pointer_speed * (
            1.0 + cfg.pointer_accel * min(max(speed - 1500.0, 0.0) / 5000.0, 3.0))
        self.rem[0] += dx * gain
        self.rem[1] += dy * gain
        ix, iy = int(self.rem[0]), int(self.rem[1])
        self.rem[0] -= ix
        self.rem[1] -= iy
        if ix or iy:
            self.out.mouse_move(ix, iy)

    def _scroll(self, dx, dy):
        cfg = self.cfg
        # Wheel: +v = scroll up, +h = scroll right. Natural scrolling moves
        # the content with the fingers (fingers up -> scroll down).
        sign = 1.0 if cfg.natural_scroll else -1.0
        # 1 notch (120 hi-res units) per ~90 units of finger travel.
        k = 120.0 / 90.0 * cfg.scroll_speed
        self.rem[2] += sign * dy * k
        self.rem[3] += -sign * dx * k
        vs, hs = int(self.rem[2]), int(self.rem[3])
        self.rem[2] -= vs
        self.rem[3] -= hs
        if vs or hs:
            self.out.scroll(vs, hs)

    # Tap to click -----------------------------------------------------------
    def _track_session(self, count, t):
        s = self.session
        if count and s is None:
            self.session = s = {"t": t, "max": count, "moved": 0.0,
                                "clicked": False}
        if s is None:
            return
        s["max"] = max(s["max"], count)
        for sl in self.slots.values():
            s["moved"] = max(s["moved"], math.hypot(sl["x"] - sl["sx"],
                                                     sl["y"] - sl["sy"]))
        if count == 0:
            self.session = None
            cfg = self.cfg
            if (self.mode.mouse and cfg.tap_to_click and not s["clicked"]
                    and self.clicked_button is None
                    and t - s["t"] <= cfg.tap_time and s["moved"] <= cfg.tap_move):
                button = {1: "left", 2: "right"}.get(s["max"], "middle")
                self.out.mouse_button(button, True)
                self.out.sync()
                self.out.mouse_button(button, False)

    def reset(self):
        self._release_click()
        self.slots.clear()
        self.pending.clear()
        self.session = None
        self.prev_count = 0
