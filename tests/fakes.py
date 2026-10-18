from evdev import ecodes as e

from couchpad.config import Config
from couchpad.engine import Controller, Mode, Touchpad


class FakeOut:
    def __init__(self):
        self.log = []
        self.keys = set()
        self.buttons = set()
        self.dx = self.dy = 0
        self.vs = self.hs = 0

    def key(self, code, down):
        (self.keys.add if down else self.keys.discard)(code)
        self.log.append(("key", code, down))

    def tap(self, code):
        self.key(code, True)
        self.key(code, False)

    def mouse_button(self, name, down):
        (self.buttons.add if down else self.buttons.discard)(name)
        self.log.append(("btn", name, down))

    def mouse_move(self, dx, dy):
        self.dx += dx
        self.dy += dy
        self.log.append(("move", dx, dy))

    def scroll(self, v, h):
        self.vs += v
        self.hs += h
        self.log.append(("scroll", v, h))

    def sync(self):
        pass

    def release_all(self):
        for k in list(self.keys):
            self.key(k, False)
        for b in list(self.buttons):
            self.mouse_button(b, False)

    def clicks(self):
        return [(n, d) for kind, n, d in self.log if kind == "btn"]

    def taps(self, code):
        return sum(1 for x in self.log if x == ("key", code, True))


class FakeActions:
    def __init__(self):
        self.ran = []
        self.fb = []
        self.pans = []
        self.hints = []
        self.modes = []
        self.switches = []
        self.wheel_events = []
        self.wheel_n = 6
        self.holds = []

    def hold(self, action, seconds):
        self.holds.append(("start", action))

    def hold_end(self, done):
        self.holds.append(("end", done))

    def run(self, action, ctl):
        self.ran.append(action)

    def feedback(self, kind, pan=0.0):
        self.fb.append(kind)
        self.pans.append(pan)

    def hint(self, text):
        self.hints.append(text)

    def mouse_mode(self, on, quiet=False):
        self.modes.append(on)

    def wheel(self, event, i=None):
        self.wheel_events.append((event, i))
        return self.wheel_n if event == "open" else None

    def switcher_opened(self):
        self.switches.append("open")

    def switcher_step(self, reverse):
        self.switches.append("back" if reverse else "next")

    def after_switch(self, cancelled):
        self.switches.append(cancelled)


def make_controller(**cfg):
    c = Config(**cfg)
    mode = Mode()
    out = FakeOut()
    acts = FakeActions()
    return Controller(c, mode, out, acts), out, acts, mode


def make_touchpad(**cfg):
    c = Config(**cfg)
    mode = Mode()
    mode.mouse = True
    out = FakeOut()
    return Touchpad(c, mode, out), out, mode


class Finger:
    """Drive a Touchpad with realistic evdev MT frames."""

    def __init__(self, tp):
        self.tp = tp
        self.t = 100.0
        self.next_id = 1

    def frame(self, dt=0.004, **slots):
        """slots: s0=(x, y) | None (lift) ; click=True/False"""
        self.t += dt
        click = slots.pop("click", None)
        for name, pos in slots.items():
            slot = int(name[1:])
            self.tp.event(e.EV_ABS, e.ABS_MT_SLOT, slot, self.t)
            if pos is None:
                self.tp.event(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1, self.t)
                continue
            if slot not in self.tp.slots:
                self.tp.event(e.EV_ABS, e.ABS_MT_TRACKING_ID, self.next_id, self.t)
                self.next_id += 1
            self.tp.event(e.EV_ABS, e.ABS_MT_POSITION_X, pos[0], self.t)
            self.tp.event(e.EV_ABS, e.ABS_MT_POSITION_Y, pos[1], self.t)
        if click is not None:
            self.tp.event(e.EV_KEY, e.BTN_LEFT, int(click), self.t)
        self.tp.event(e.EV_SYN, e.SYN_REPORT, 0, self.t)

    def swipe(self, start, end, steps, dt=0.004, slot="s0"):
        for i in range(steps + 1):
            x = start[0] + (end[0] - start[0]) * i / steps
            y = start[1] + (end[1] - start[1]) * i / steps
            self.frame(dt, **{slot: (round(x), round(y))})


def qt_app():
    """Offscreen QApplication without leaking QT_QPA_PLATFORM to children
    (other tests spawn real windows)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test", "-platform", "offscreen"])
