"""Reads the DualSense inside the control center: live state for the tester
page and D-pad / ✕ / ○ / L1 / R1 navigation of the window itself.

Only reads (never grabs), so the daemon and games keep working.
"""

import math
import os
import select
import struct
import threading
import time

import evdev
from evdev import ecodes as e
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .. import hidraw
from ..daemon import PRODUCTS, SONY, hid_parent
from ..engine import EVDEV_BUTTONS

HAT = {(e.ABS_HAT0X, -1): "left", (e.ABS_HAT0X, 1): "right",
       (e.ABS_HAT0Y, -1): "up", (e.ABS_HAT0Y, 1): "down"}
AXES = {e.ABS_X: "lx", e.ABS_Y: "ly", e.ABS_RX: "rx", e.ABS_RY: "ry",
        e.ABS_Z: "l2", e.ABS_RZ: "r2"}
NAV_REPEAT_DELAY, NAV_REPEAT = 0.38, 0.11


ACCEL_OFFSET = 21          # int16 x, y, z inside the report's common block


def tilt_from_report(report):
    """(pitch, roll) in degrees from a DualSense input report's
    accelerometer; 0, 0 = lying flat. None for other reports."""
    if not report:
        return None
    if report[0] == hidraw.BT_REPORT and len(report) >= 2 + ACCEL_OFFSET + 6:
        c = report[2:]
    elif report[0] == hidraw.USB_REPORT and len(report) >= 1 + ACCEL_OFFSET + 6:
        c = report[1:]
    else:
        return None
    ax, ay, az = struct.unpack_from("<hhh", c, ACCEL_OFFSET)
    if ax == ay == az == 0:
        return None
    pitch = math.degrees(math.atan2(az, ay))
    roll = math.degrees(math.atan2(-ax, math.hypot(ay, az)))
    return max(-60.0, min(60.0, pitch)), max(-60.0, min(60.0, roll))


def find_pad():
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.info.vendor == SONY and dev.info.product in PRODUCTS
                and not dev.name.endswith(("Touchpad", "Motion Sensors"))):
            return dev
        dev.close()
    return None


class Gamepad(QObject):
    stateChanged = Signal()
    connectedChanged = Signal()
    nav = Signal(str)                    # up/down/left/right/accept/back/prev/next/menu
    _event = Signal(str, bool)
    _connected = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self._blank()
        self._dirty = False
        self._is_connected = False
        self.navigation = True           # set from QML: window active, mouse mode off
        self.live = False                # tester page visible
        self.held = {}
        self.lock = threading.Lock()
        self.alive = True
        self._event.connect(self._on_button)
        self._connected.connect(self._set_connected)
        self.flush = QTimer(self, interval=33, timeout=self._flush)
        self.flush.start()
        self.repeat = QTimer(self, interval=20, timeout=self._repeat)
        self.repeat.start()
        threading.Thread(target=self._run, daemon=True, name="gamepad").start()

    @staticmethod
    def _blank():
        return {"buttons": {}, "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "l2": 0.0,
                "r2": 0.0, "touch": [], "click": False, "pitch": 0.0, "roll": 0.0}

    # -- QML API ----------------------------------------------------------------
    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._is_connected

    @Slot(bool)
    def setNavigation(self, on):
        self.navigation = on
        if not on:
            self.held.clear()

    @Slot(bool)
    def setLive(self, on):
        self.live = on

    # -- reader thread ----------------------------------------------------------
    def _run(self):
        while self.alive:
            dev = find_pad()
            if dev is None:
                time.sleep(2)
                continue
            self._connected.emit(True)
            try:
                self._read(dev)
            except OSError:
                pass
            finally:
                try:
                    dev.close()
                except OSError:
                    pass
            self._connected.emit(False)
            with self.lock:
                self._state = self._blank()
                self._dirty = True
            time.sleep(1)

    def _read(self, dev):
        absinfo = {c: dev.absinfo(c) for c in AXES if c in dict(
            dev.capabilities().get(e.EV_ABS, []))}
        hid_fd = None
        node = hidraw.hidraw_node(hid_parent(dev.path) or "")
        if node:
            try:
                hid_fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                hid_fd = None
        hat = {e.ABS_HAT0X: 0, e.ABS_HAT0Y: 0}
        try:
            while self.alive:
                fds = [dev.fd] + ([hid_fd] if hid_fd is not None and self.live else [])
                r, _w, _x = select.select(fds, [], [], 0.5)
                if hid_fd is not None and hid_fd in r:
                    self._read_touch(hid_fd)
                if dev.fd not in r:
                    continue
                for ev in dev.read():
                    if ev.type == e.EV_KEY and ev.code in EVDEV_BUTTONS and ev.value in (0, 1):
                        name = EVDEV_BUTTONS[ev.code]
                        self._button(name, ev.value == 1)
                    elif ev.type == e.EV_ABS and ev.code in hat:
                        old = hat[ev.code]
                        if old:
                            self._button(HAT[(ev.code, old)], False)
                        hat[ev.code] = ev.value
                        if ev.value:
                            self._button(HAT[(ev.code, ev.value)], True)
                    elif ev.type == e.EV_ABS and ev.code in absinfo:
                        ai = absinfo[ev.code]
                        name = AXES[ev.code]
                        if name in ("l2", "r2"):
                            v = (ev.value - ai.min) / max(1, ai.max - ai.min)
                        else:
                            mid = (ai.max + ai.min) / 2
                            v = max(-1.0, min(1.0, (ev.value - mid) / ((ai.max - ai.min) / 2)))
                        with self.lock:
                            self._state[name] = v
                            self._dirty = True
                        if name == "ly":
                            self._stick_nav(v)
        finally:
            if hid_fd is not None:
                os.close(hid_fd)

    def _read_touch(self, fd):
        """Touch points and the accelerometer from the newest input report."""
        last = None
        try:
            while True:
                rep = os.read(fd, 128)
                if not rep:
                    break
                last = rep
        except BlockingIOError:
            pass
        parsed = hidraw.parse(last) if last else None
        if parsed:
            points, click = parsed
            touch = [{"x": p[1] / 1919.0, "y": p[2] / 1079.0} for p in points if p]
            tilt = tilt_from_report(last)
            with self.lock:
                if touch != self._state["touch"] or click != self._state["click"]:
                    self._state["touch"] = touch
                    self._state["click"] = click
                    self._dirty = True
                if tilt:
                    # light low-pass: steady picture, still follows the hands
                    pitch = self._state["pitch"] * 0.8 + tilt[0] * 0.2
                    roll = self._state["roll"] * 0.8 + tilt[1] * 0.2
                    if abs(pitch - self._state["pitch"]) > 0.05 or abs(roll - self._state["roll"]) > 0.05:
                        self._state["pitch"], self._state["roll"] = pitch, roll
                        self._dirty = True

    def _button(self, name, pressed):
        with self.lock:
            b = dict(self._state["buttons"])
            b[name] = pressed
            self._state["buttons"] = b
            self._dirty = True
        self._event.emit(name, pressed)

    stick_dir = 0

    def _stick_nav(self, v):
        d = -1 if v < -0.6 else 1 if v > 0.6 else 0
        if abs(v) < 0.35:
            d = 0
        elif d == 0:
            return
        if d != self.stick_dir:
            self.stick_dir = d
            if d:
                self._event.emit("stick_up" if d < 0 else "stick_down", True)
            else:
                self._event.emit("stick_up", False)
                self._event.emit("stick_down", False)

    # -- main thread ------------------------------------------------------------
    NAV = {"up": "up", "down": "down", "left": "left", "right": "right",
           "stick_up": "up", "stick_down": "down", "cross": "accept", "circle": "back",
           "l1": "prev", "r1": "next", "options": "menu"}
    REPEATS = {"up", "down", "left", "right", "stick_up", "stick_down"}

    def _on_button(self, name, pressed):
        if not pressed:
            self.held.pop(name, None)
            return
        if not self.navigation or name not in self.NAV:
            return
        # Share held = a daemon chord, not navigation.
        if self._state["buttons"].get("share"):
            return
        self.nav.emit(self.NAV[name])
        if name in self.REPEATS:
            self.held[name] = time.monotonic() + NAV_REPEAT_DELAY

    def _repeat(self):
        now = time.monotonic()
        for name, t in list(self.held.items()):
            if now >= t and self.navigation:
                self.held[name] = now + NAV_REPEAT
                self.nav.emit(self.NAV[name])

    def _flush(self):
        with self.lock:
            if not self._dirty:
                return
            self._dirty = False
            self._state = dict(self._state)
        self.stateChanged.emit()

    def _set_connected(self, on):
        if on != self._is_connected:
            self._is_connected = on
            self.connectedChanged.emit()

    def shutdown(self):
        self.alive = False
