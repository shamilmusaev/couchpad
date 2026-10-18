"""DualSense HD haptics over Bluetooth: synthesised waveforms streamed as
haptic "audio" through the hidraw node.

Wire protocol (output report 0x32) as reverse-engineered by SAxense,
MPL-2.0 - https://apps.sdore.me/SAxense - https://github.com/egormanga/SAxense

Report 0x32 is 141 bytes of data after the report id (142 written to
hidraw, as the controller's HID descriptor says). It carries one packet
0x11 (control, with a running
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
REPORT_SIZE = 142                  # report id + 141 data bytes (CRC in the last 4)
RATE = 3000
FRAMES = 32                        # stereo frames per report
PERIOD = FRAMES / RATE             # 10.67 ms
# The controller gates its haptics channel when the stream stops and fades
# it back in when it restarts: a 16 ms click right after a pause got lost
# in that ramp (only every second or third step of the window switcher was
# felt). So a cold start leads with ~64 ms of silence, and after the last
# click the stream keeps running silence for KEEPALIVE seconds, which keeps
# the channel warm for the next step.
PREROLL = 6                        # silent reports before a click after a pause
TAIL = 4                           # minimum silent reports after the last sample
KEEPALIVE = 3.0                    # s of silence streamed after the last click


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
    """frames: 64 bytes (int8 L/R interleaved) -> 142-byte report."""
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

def _click(freq, cycles, amp, attack_ms=1.0, fade_ms=3.0, freq_end=None):
    """A few full-scale sine periods with soft edges: what a voice-coil
    actuator turns into a crisp, strong tap. (A long exponential decay looks
    nice on paper but carries almost no energy - it was barely felt.)"""
    f_end = freq if freq_end is None else freq_end
    ms = cycles * 1000.0 / ((freq + f_end) / 2)
    n = max(2, int(RATE * ms / 1000))
    att = max(1, int(RATE * attack_ms / 1000))
    fade = max(1, int(RATE * fade_ms / 1000))
    out, phase = [], 0.0
    for i in range(n):
        f = freq + (f_end - freq) * i / n
        phase += 2 * math.pi * f / RATE
        env = 1.0
        if i < att:
            env *= 0.5 - 0.5 * math.cos(math.pi * i / att)
        if i >= n - fade:
            env *= 0.5 - 0.5 * math.cos(math.pi * (n - 1 - i) / fade)
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


def _level(wave, peak):
    """Scale to an exact peak, so every pattern sits where it is meant to."""
    top = max(abs(v) for v in wave) or 1.0
    return [v * peak / top for v in wave]


def _swell(freq, ms, amp, rise=0.6, freq_end=None):
    """A tone that swells in and fades out (a soft "whoosh")."""
    n = int(RATE * ms / 1000)
    f_end = freq if freq_end is None else freq_end
    out, phase = [], 0.0
    for i in range(n):
        x = i / n
        f = freq + (f_end - freq) * x
        phase += 2 * math.pi * f / RATE
        env = math.sin(math.pi * min(1.0, x / rise) / 2) if x < rise else \
            0.5 + 0.5 * math.cos(math.pi * (x - rise) / (1 - rise))
        out.append(amp * env * math.sin(phase))
    return out


def library():
    """Each cue has its own character, so the hands can tell them apart.
    Peaks: 1.0 = full scale at 100 % strength."""
    return {
        # hold Share + ○ / △: three rising ticks, then a heavy double knock
        "tick":      _level(_click(120, 2, 1, fade_ms=4), 0.75),
        "progress1": _level(_click(150, 2, 1), 0.65),
        "progress2": _level(_click(190, 3, 1), 0.85),
        "progress3": _level(_click(240, 4, 1), 1.00),
        "fire":      _level(_seq((0, _click(100, 3, 1, fade_ms=5)), (0, _click(250, 4, 0.6)),
                                 (90, _click(100, 3, 1, fade_ms=5)), (90, _click(250, 4, 0.6))), 1.00),
        # soft drop: a falling wobble
        "cancel":    _level(_click(180, 6, 1, attack_ms=4, fade_ms=12, freq_end=90), 0.80),
        # mouse mode: rising / falling chirp ending in a tap
        "on":        _level(_seq((0, _click(110, 10, 1, attack_ms=6, fade_ms=4, freq_end=260)),
                                 (70, _click(260, 3, 1))), 1.00),
        "off":       _level(_seq((0, _click(260, 3, 1)),
                                 (25, _click(260, 10, 1, attack_ms=4, fade_ms=10, freq_end=110))), 0.90),
        # wheel / switcher opens: a swell
        "open":      _level(_swell(150, 90, 1, rise=0.5, freq_end=220), 0.85),
        # wheel sectors / volume: a tiny bright ratchet tooth
        "detent":    _level(_click(300, 2, 1, attack_ms=0.5, fade_ms=2), 0.80),
        # window switcher step: a "tock" with a faint echo
        "step":      _level(_seq((0, _click(180, 3, 1)), (32, _click(180, 2, 0.35))), 0.95),
        # wheel launch: a bass boom with a click on top
        "launch":    _level(_seq((0, _click(85, 4, 1, fade_ms=8)), (0, _click(270, 4, 0.55))), 1.00),
        # switcher confirm: a bright double tap
        "confirm":   _level(_seq((0, _click(250, 3, 1)), (40, _click(280, 3, 1))), 1.00),
    }


def shape(v, k):
    """Strength k (0..3): a soft saturation that keeps peaks at full scale
    while k > 1 fattens the waveform towards a square wave, the most energy
    a voice coil can be given."""
    x = v * k
    return math.tanh(1.3 * x) / math.tanh(1.3)


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

    def __init__(self, node, strength=1.0, writer=None, keepalive=KEEPALIVE):
        self.node = node
        self.keepalive = max(TAIL, int(keepalive / PERIOD))   # in reports
        self.streaming = False              # channel warm: no lead-in needed
        self.warm_t = 0.0                   # last warm() call
        self.strength = max(0.0, min(strength, 3.0))
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
            if not self.left and not self.streaming:
                self.preroll = PREROLL * FRAMES
            start = self.preroll                # never inside the lead-in silence
            need = start + len(wave)
            if len(self.left) < need:
                pad = need - len(self.left)
                self.left += [0.0] * pad
                self.right += [0.0] * pad
            for i, v in enumerate(wave):
                v = shape(v, k)
                self.left[start + i] += v * gl
                self.right[start + i] += v * gr
            self.cv.notify()
        return True

    def warm(self):
        """Start the stream (silence) ahead of a likely click, so the click
        doesn't wait for the controller to wake its haptics channel."""
        if self.failed or self.strength <= 0:
            return False
        with self.cv:
            if self.streaming or self.left:
                self.warm_t = time.monotonic()      # just extend the keepalive
                return True
            self.left = [0.0] * (PREROLL * FRAMES)
            self.right = [0.0] * (PREROLL * FRAMES)
            self.preroll = PREROLL * FRAMES       # an early click still waits for it
            self.warm_t = time.monotonic()
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
            self.streaming = True
            while silent < self.keepalive:
                with self.cv:
                    if not self.alive:
                        return
                    l, self.left = self.left[:FRAMES], self.left[FRAMES:]
                    r, self.right = self.right[:FRAMES], self.right[FRAMES:]
                    self.preroll = max(0, self.preroll - FRAMES)
                    if any(l) or any(r) or self.left or self.warm_t > nxt - PERIOD:
                        silent = 0
                    else:
                        silent += 1
                    if silent >= self.keepalive:
                        self.streaming = False      # a new click gets a lead-in
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
                        self.streaming = False
                    break
                self.counter = (self.counter + 1) & 0xFF
                nxt += PERIOD
                delay = nxt - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -0.1:          # fell far behind: resync
                    nxt = time.monotonic()
