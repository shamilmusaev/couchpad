"""Touchpad fallback straight from the DualSense HID input report.

Used when the kernel's touchpad evdev node isn't readable (no udev rule).
The hidraw node already has user access on Bazzite, and reading it does not
disturb Steam (every opener gets its own copy of each report).
"""

import os

from evdev import ecodes as e

BT_REPORT = 0x31      # Bluetooth full report: [0x31, seq, common...]
USB_REPORT = 0x01     # USB report: [0x01, common...]
TOUCH_OFFSET = 32     # inside the common part
BUTTONS_OFFSET = 7
PAD_CLICK = 0x02      # buttons[2]


def parse(report):
    """-> (points, click) or None. points: [(id, x, y) | None, ...] x2."""
    if not report:
        return None
    if report[0] == BT_REPORT and len(report) >= 2 + TOUCH_OFFSET + 8:
        c = report[2:]
    elif report[0] == USB_REPORT and len(report) >= 1 + TOUCH_OFFSET + 8:
        c = report[1:]
    else:
        return None
    points = []
    for i in range(2):
        b = c[TOUCH_OFFSET + 4 * i: TOUCH_OFFSET + 4 * i + 4]
        if b[0] & 0x80:
            points.append(None)
        else:
            x = b[1] | ((b[2] & 0x0F) << 8)
            y = (b[2] >> 4) | (b[3] << 4)
            points.append((b[0] & 0x7F, x, y))
    click = bool(c[BUTTONS_OFFSET + 2] & PAD_CLICK)
    return points, click


class HidrawTouch:
    """Feeds a `Touchpad` engine with synthetic MT events from reports."""

    def __init__(self, touchpad):
        self.tp = touchpad
        self.last = None     # (points, click)
        self.ids = [None, None]

    def feed(self, report, t):
        parsed = parse(report)
        if parsed is None or parsed == self.last:
            return
        points, click = parsed
        last_points, last_click = self.last or ([None, None], False)
        self.last = parsed
        ev = self.tp.event
        for slot, (pt, old) in enumerate(zip(points, last_points)):
            if pt == old:
                continue
            ev(e.EV_ABS, e.ABS_MT_SLOT, slot, t)
            if pt is None:
                ev(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1, t)
                self.ids[slot] = None
                continue
            if self.ids[slot] != pt[0]:
                self.ids[slot] = pt[0]
                ev(e.EV_ABS, e.ABS_MT_TRACKING_ID, pt[0], t)
            ev(e.EV_ABS, e.ABS_MT_POSITION_X, pt[1], t)
            ev(e.EV_ABS, e.ABS_MT_POSITION_Y, pt[2], t)
        if click != last_click:
            ev(e.EV_KEY, e.BTN_LEFT, int(click), t)
        ev(e.EV_SYN, e.SYN_REPORT, 0, t)


def hidraw_node(hid_dir):
    try:
        names = os.listdir(os.path.join(hid_dir, "hidraw"))
    except OSError:
        return None
    return f"/dev/{names[0]}" if names else None


def touchpad_sysname(hid_dir):
    """eventN of the kernel touchpad node for this controller (for KWin)."""
    base = os.path.join(hid_dir, "input")
    try:
        inputs = os.listdir(base)
    except OSError:
        return None
    for inp in inputs:
        try:
            with open(os.path.join(base, inp, "name")) as f:
                if not f.read().strip().endswith("Touchpad"):
                    continue
            for entry in os.listdir(os.path.join(base, inp)):
                if entry.startswith("event"):
                    return entry
        except OSError:
            continue
    return None
