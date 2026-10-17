"""DualSense HD haptics over Bluetooth: synthesised waveforms streamed as
haptic "audio" through the hidraw node.

Wire protocol (output report 0x32) as reverse-engineered by SAxense,
MPL-2.0 - https://apps.sdore.me/SAxense - https://github.com/egormanga/SAxense

Each 141-byte report carries one packet 0x11 (control, with a running
counter) and one packet 0x12 with 32 stereo frames of signed 8-bit PCM at
3 kHz (10.67 ms of signal), followed by a CRC32 seeded with 0xA2.
"""

import logging
import math
import os
import struct
import threading
import time
import zlib

log = logging.getLogger("couchpad")

REPORT_ID = 0x32
REPORT_SIZE = 141
RATE = 3000
FRAMES = 32                        # stereo frames per report
PERIOD = FRAMES / RATE             # 10.67 ms
PREROLL = 2                        # silent reports before a click (no crackle)
TAIL = 4                           # silent reports after the last sample


# Output report 0x31 (Bluetooth, 78 bytes): id, sequence << 4, tag 0x10, then
# the common block from byte 3 (struct dualsense_output_report_bt).
ARM_SIZE = 78
VALID1_AUDIO_MUTE = 0x02       # apply mute control (byte 9) -> unmute haptics
VALID1_HAPTIC_LPF = 0x20       # apply haptic low-pass filter (byte 39)
VALID1_MOTOR_POWER = 0x40      # apply motor power reduction (byte 36)


def build_arm_report(seq=0):
    """Put the actuators back into audio-haptics mode at full power.

    Rumble requests (valid_flag0 bits) from the kernel driver or Steam switch
    the DualSense to rumble emulation and it stays there, silently ignoring
    report 0x32. valid_flag0 stays 0 here; only mute, motor power and the
    haptics low-pass filter are set, so lights/triggers/volume are untouched.
    """
    r = bytearray(ARM_SIZE)
    r[0] = 0x31
    r[1] = (seq & 0x0F) << 4
    r[2] = 0x10                                        # tag, required
    c = 3
    r[c + 0] = 0x00                                    # valid_flag0: no rumble
    r[c + 1] = VALID1_AUDIO_MUTE | VALID1_HAPTIC_LPF | VALID1_MOTOR_POWER
    r[c + 9] = 0x00                                    # mute control: nothing muted
    r[c + 36] = 0x00                                   # motor power reduction: none
    r[c + 39] = 0x01                                   # haptic low-pass filter on
    r[-4:] = struct.pack("<I", zlib.crc32(b"\xa2" + bytes(r[:-4])))
    return bytes(r)


def build_report(frames, counter):
    """frames: 64 bytes (int8 L/R interleaved) -> 141-byte report."""
    body = bytearray(REPORT_SIZE - 1 - 4)
    body[0] = 0x00                                     # tag/seq
    body[1], body[2] = 0x80 | 0x11, 7                  # packet 0x11, sized
    body[3:10] = bytes((0b11111110, 0, 0, 0, 0, 0xFF, counter & 0xFF))
    body[10], body[11] = 0x80 | 0x12, FRAMES * 2       # packet 0x12, sized
    body[12:12 + FRAMES * 2] = frames
    head = bytes([REPORT_ID]) + bytes(body)
    return head + struct.pack("<I", zlib.crc32(b"\xa2" + head))


# --------------------------------------------------------------------------
# Waveforms (floats in -1..1, mono; panned at play time)

def _burst(freq, ms, amp, attack_ms=1.5, decay=None, freq_end=None):
    """Sine burst with a raised-cosine attack and exponential decay.
    The DualSense actuators respond best roughly between 80 and 320 Hz."""
    n = max(1, int(RATE * ms / 1000))
    att = max(1, int(RATE * attack_ms / 1000))
    decay = decay if decay is not None else 4.6 / (ms / 1000)   # -40 dB at the end
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = freq if freq_end is None else freq + (freq_end - freq) * i / n
        phase += 2 * math.pi * f / RATE
        env = math.exp(-decay * t)
        if i < att:
            env *= 0.5 - 0.5 * math.cos(math.pi * i / att)
        out.append(amp * env * math.sin(phase))
    return out


def _seq(*parts):
    """(offset_ms, samples) pairs mixed into one waveform."""
    length = max(int(RATE * off / 1000) + len(s) for off, s in parts)
    out = [0.0] * length
    for off, s in parts:
        o = int(RATE * off / 1000)
        for i, v in enumerate(s):
            out[o + i] += v
    return out


def library():
    return {
        # hold Share+O / Share+Triangle
        "tick":      _burst(190, 22, 0.45),
        "progress1": _burst(170, 20, 0.40),
        "progress2": _burst(190, 22, 0.60),
        "progress3": _burst(210, 24, 0.80),
        "fire":      _seq((0, _burst(230, 32, 1.0)), (85, _burst(260, 36, 1.0))),
        # generic
        "cancel":    _burst(95, 55, 0.75, attack_ms=4),
        "on":        _seq((0, _burst(160, 24, 0.55)), (95, _burst(250, 30, 0.85))),
        "off":       _seq((0, _burst(250, 30, 0.75)), (95, _burst(160, 24, 0.50))),
        # wheel / switcher
        "open":      _burst(140, 70, 0.55, attack_ms=12, freq_end=210),
        "detent":    _burst(220, 14, 0.50, attack_ms=0.8),
        "step":      _burst(200, 16, 0.60, attack_ms=0.8),
        "launch":    _seq((0, _burst(260, 30, 1.0)), (0, _burst(110, 60, 0.45, attack_ms=3))),
        "confirm":   _burst(240, 30, 0.85),
    }


def pan_gains(pan):
    """pan -1 (left) .. +1 (right) -> (left, right) gains. Centre = full on
    both sides; fully panned keeps a quarter on the far side so the click
    still feels whole."""
    pan = max(-1.0, min(1.0, pan))
    return 1.0 - 0.75 * max(0.0, pan), 1.0 - 0.75 * max(0.0, -pan)


def to_int8(v):
    return max(-127, min(127, int(round(v * 127)))) & 0xFF


class HDHaptics:
    """Streams mixed waveforms to one controller from a background thread.
    Silent when idle: reports are only sent while something plays."""

    def __init__(self, node, strength=1.0, writer=None):
        self.node = node
        self.strength = max(0.0, min(strength, 2.0))
        self.lib = library()
        self.left, self.right = [], []      # pending mix (floats)
        self.preroll = 0                    # silent samples still at the head
        self.cv = threading.Condition()
        self.counter = 0
        self.alive = True
        self.failed = False
        self._fd = None
        self._writer = writer               # tests: callable(report_bytes)
        self.thread = threading.Thread(target=self._run, daemon=True, name="hdhaptics")
        self.thread.start()

    # -- API ---------------------------------------------------------------
    def play(self, name, pan=0.0):
        wave = self.lib.get(name)
        if wave is None or self.failed or self.strength <= 0:
            return False
        gl, gr = pan_gains(pan)
        k = self.strength
        with self.cv:
            if not self.left:
                self.preroll = PREROLL * FRAMES
            start = self.preroll                # never inside the lead-in silence
            need = start + len(wave)
            if len(self.left) < need:
                pad = need - len(self.left)
                self.left += [0.0] * pad
                self.right += [0.0] * pad
            for i, v in enumerate(wave):
                self.left[start + i] += v * gl * k
                self.right[start + i] += v * gr * k
            self.cv.notify()
        return True

    def close(self):
        with self.cv:
            self.alive = False
            self.cv.notify()
        self.thread.join(1)
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass

    # -- streaming ------------------------------------------------------------
    def _write(self, report):
        if self._writer:
            self._writer(report)
            return
        if self._fd is None:
            self._fd = os.open(self.node, os.O_WRONLY)
        os.write(self._fd, report)

    def _run(self):
        while True:
            with self.cv:
                while self.alive and not self.left:
                    self.cv.wait()
                if not self.alive:
                    return
            try:
                self._write(build_arm_report(self.counter))
            except OSError as exc:
                log.warning("HD haptics disabled (%s): %s", self.node, exc)
                self.failed = True
                with self.cv:
                    self.left, self.right = [], []
                continue
            nxt = time.monotonic()
            silent = 0
            while silent < TAIL:
                with self.cv:
                    if not self.alive:
                        return
                    l, self.left = self.left[:FRAMES], self.left[FRAMES:]
                    r, self.right = self.right[:FRAMES], self.right[FRAMES:]
                    self.preroll = max(0, self.preroll - FRAMES)
                if any(l) or any(r) or self.left:
                    silent = 0
                else:
                    silent += 1
                l += [0.0] * (FRAMES - len(l))
                r += [0.0] * (FRAMES - len(r))
                frames = bytes(b for pair in zip(l, r) for b in (to_int8(pair[0]), to_int8(pair[1])))
                try:
                    self._write(build_report(frames, self.counter))
                except OSError as exc:
                    log.warning("HD haptics disabled (%s): %s", self.node, exc)
                    self.failed = True
                    with self.cv:
                        self.left, self.right = [], []
                    break
                self.counter = (self.counter + 1) & 0xFF
                nxt += PERIOD
                delay = nxt - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -0.1:          # fell far behind: resync
                    nxt = time.monotonic()
