"""DualSense lightbar, player LEDs and mic LED.

The lightbar goes through the kernel's LED class device
(/sys/.../leds/inputN:rgb:indicator, writable for the logged-in user on
Bazzite/SteamOS), so the driver always knows the colour. The player and
mic LEDs aren't writable there, so they are set with a minimal output report
over hidraw that only touches those two fields.
"""

import colorsys
import glob
import logging
import math
import os
import struct
import zlib

log = logging.getLogger("couchpad")

MODES = ("off", "static", "breathe", "rainbow", "battery", "steam")
ANIMATED = {"breathe", "rainbow"}
FLASH_TIME = 0.45                  # s, flash fades out over this
KEEP_EVERY = 8.0                   # s, re-assert (Steam may repaint the bar)

# Output report 0x31 over Bluetooth / 0x02 over USB
VALID1_MIC_LED = 0x01
VALID1_PLAYER_LEDS = 0x10
PLAYER_LED_INSTANT = 0x20
BATTERY_LEDS = (0x00, 0x04, 0x0A, 0x0E, 0x1B, 0x1F)   # 0..5 lit, centred


def hex_rgb(s, fallback=(30, 107, 255)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError, IndexError):
        return fallback


def rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def battery_color(cap):
    """Red at 10 % -> yellow -> green from 70 %."""
    k = min(max((cap - 10) / 60.0, 0.0), 1.0)
    r, g, b = colorsys.hsv_to_rgb(k * 0.33, 1.0, 1.0)
    return (r * 255, g * 255, b * 255)


def scale(rgb, k):
    return tuple(c * k for c in rgb)


def mix(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def perceptual(level):
    """Brightness slider 0..1 -> LED duty (the eye is far from linear)."""
    return level ** 2.0


def build_led_report(bluetooth, player=None, mic=None, seq=0):
    """Output report that changes only the player LEDs and/or mic LED."""
    flags = (VALID1_PLAYER_LEDS if player is not None else 0) | (
        VALID1_MIC_LED if mic is not None else 0)
    if bluetooth:
        # 0x31, sequence << 4, tag 0x10, then the common block (as hid-playstation)
        r = bytearray(78)
        r[0], r[1], r[2] = 0x31, (seq & 0x0F) << 4, 0x10
        c = 3
    else:
        r = bytearray(48)
        r[0] = 0x02
        c = 1
    r[c + 1] = flags
    if mic is not None:
        r[c + 8] = 1 if mic else 0
    if player is not None:
        r[c + 43] = (player & 0x1F) | PLAYER_LED_INSTANT
    if bluetooth:
        r[-4:] = struct.pack("<I", zlib.crc32(b"\xa2" + bytes(r[:-4])))
    return bytes(r)


def find_lightbar(hid_path):
    """The rgb LED below one controller's HID device."""
    if not hid_path:
        return None
    hits = sorted(glob.glob(os.path.join(hid_path, "leds", "*:rgb:indicator")))
    return hits[0] if hits else None


class Lights:
    """Computes and writes one controller's light state. `tick(now)` is
    called by the daemon at FPS while `animating()` and on every change."""

    FPS = 25

    def __init__(self, cfg, hid_path=None, hidraw=None, bluetooth=True,
                 battery=lambda: None, led_dir=None, writer=None):
        self.cfg = cfg
        self.led = led_dir or find_lightbar(hid_path)
        self.hidraw = hidraw
        self.bluetooth = bluetooth
        self.battery = battery           # () -> (capacity, status) | None
        self.writer = writer             # tests: callable(kind, value)
        self.mouse = False
        self.flash_color = None
        self.flash_t = -1e9
        self.preview = None              # (rgb, until) from the control center
        self.last = None
        self.last_t = -1e9
        self.leds_sent = None
        self.bat = None
        self.bat_t = -1e9
        self.seq = 0
        self.failed = False
        self.retry_at = 0.0               # LED not writable yet (udev ACL lags)
        self.warned = False
        self.primed = False               # class brightness set to full once

    # -- inputs ---------------------------------------------------------------
    def set_mouse(self, on):
        self.mouse = on

    def flash(self, color, now):
        if self.cfg.light_flash and self.cfg.light_mode != "steam":
            self.flash_color = hex_rgb(color) if isinstance(color, str) else color
            self.flash_t = now

    def show_preview(self, color, now, seconds=4.0):
        self.preview = (hex_rgb(color), now + seconds)

    def reload(self):
        self.last = None             # force a write with the new settings
        self.leds_sent = None

    # -- state ----------------------------------------------------------------
    def animating(self, now):
        cfg = self.cfg
        if cfg.light_mode == "steam":
            return False
        if now - self.flash_t < FLASH_TIME or (self.preview and now < self.preview[1]):
            return True
        if self.mouse and cfg.light_mouse_color:
            return False
        if cfg.light_mode in ANIMATED:
            return True
        return cfg.light_mode == "battery" and self._battery(now)[1] == "Charging"

    def _battery(self, now):
        if now - self.bat_t > 20:
            self.bat_t = now
            try:
                self.bat = self.battery()
            except Exception:
                self.bat = None
        return self.bat or (None, None)

    def color(self, now):
        """Lightbar colour (0..255 floats) for this moment, or None to leave
        the bar alone (mode "steam")."""
        cfg = self.cfg
        if cfg.light_mode == "steam":
            return None
        level = perceptual(cfg.light_brightness)
        if self.preview and now < self.preview[1]:
            return scale(self.preview[0], level)
        self.preview = None
        mode = cfg.light_mode
        if self.mouse and cfg.light_mouse_color:
            base = hex_rgb(cfg.light_mouse_color)
        elif mode == "off":
            base = (0, 0, 0)
        elif mode == "static":
            base = hex_rgb(cfg.light_color)
        elif mode == "breathe":
            period = 4.0 / cfg.light_speed
            k = 0.5 - 0.5 * math.cos(2 * math.pi * (now % period) / period)
            base = scale(hex_rgb(cfg.light_color), 0.08 + 0.92 * k * k)
        elif mode == "rainbow":
            hue = (now * cfg.light_speed / 12.0) % 1.0
            base = tuple(c * 255 for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0))
        else:                                       # battery
            cap, status = self._battery(now)
            base = battery_color(cap) if cap is not None else hex_rgb(cfg.light_color)
            if status == "Charging":
                period = 3.0
                k = 0.5 - 0.5 * math.cos(2 * math.pi * (now % period) / period)
                base = scale(base, 0.25 + 0.75 * k)
        rgb = scale(base, level)
        age = now - self.flash_t
        if self.flash_color and age < FLASH_TIME:
            k = 1.0 - age / FLASH_TIME
            rgb = mix(rgb, scale(self.flash_color, max(level, 0.5)), k * k)
        return rgb

    def player_mask(self, now):
        mode = self.cfg.player_leds
        if mode == "off":
            return 0
        if mode == "mouse":
            return 0x04 if self.mouse else 0
        if mode == "battery":
            cap = self._battery(now)[0]
            return BATTERY_LEDS[0 if cap is None else min(5, max(1, math.ceil(cap / 20)))]
        return None                                 # auto: leave to the driver

    def mic(self):
        return self.mouse if self.cfg.mic_led == "mouse" else None

    # -- output ---------------------------------------------------------------
    def tick(self, now):
        if self.failed or now < self.retry_at:
            return
        rgb = self.color(now)
        if rgb is not None:
            if not self.primed:
                if not self._write_file("brightness", "255", now):
                    return
                self.primed = True
            value = tuple(int(round(min(max(c, 0), 255))) for c in rgb)
            if value != self.last or now - self.last_t > KEEP_EVERY:
                if self._write_file("multi_intensity", "%d %d %d" % value, now):
                    self.last, self.last_t = value, now
        leds = (self.player_mask(now), self.mic())
        if leds != self.leds_sent and leds != (None, None):
            self.leds_sent = leds
            self._write_hid(build_led_report(self.bluetooth, leds[0], leds[1], self.seq))
            self.seq += 1

    def _write_file(self, name, value, now=0.0):
        """True when written. A freshly connected pad's LED only becomes
        writable once udev has applied its rule, so failures retry."""
        if self.writer:
            self.writer(name, value)
            return True
        if not self.led:
            return False
        try:
            with open(os.path.join(self.led, name), "w") as f:
                f.write(value)
            return True
        except FileNotFoundError:
            self.failed = True            # the controller is gone
        except OSError as exc:
            if not self.warned:
                log.warning("lightbar %s: %s (retrying)", self.led, exc)
                self.warned = True
            self.retry_at = now + 2.0
        return False

    def _write_hid(self, report):
        if self.writer:
            self.writer("hid", report)
            return
        if not self.hidraw:
            return
        try:
            fd = os.open(self.hidraw, os.O_WRONLY)
            try:
                os.write(fd, report)
            finally:
                os.close(fd)
        except OSError as exc:
            log.debug("player LEDs via %s: %s", self.hidraw, exc)
