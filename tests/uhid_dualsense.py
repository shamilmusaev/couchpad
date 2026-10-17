"""A virtual Bluetooth DualSense made with /dev/uhid.

The kernel's real hid-playstation driver binds to it, so it produces the
same gamepad / touchpad / motion evdev nodes, hidraw node, battery and LEDs
as the physical controller. Used by the live acceptance test.
"""

import os
import select
import struct
import threading
import time
import zlib

UHID_DESTROY, UHID_START, UHID_STOP, UHID_OPEN, UHID_CLOSE, UHID_OUTPUT = 1, 2, 3, 4, 5, 6
UHID_GET_REPORT, UHID_GET_REPORT_REPLY = 9, 10
UHID_CREATE2, UHID_INPUT2 = 11, 12
UHID_SET_REPORT, UHID_SET_REPORT_REPLY = 13, 14
EVENT_SIZE = 4 + 4372
BUS_BLUETOOTH = 0x05

RDESC = os.path.join(os.path.dirname(__file__), "data", "dualsense_bt.rdesc")

# Buttons: (byte index in buttons[], mask)
BUTTONS = {
    "square": (0, 0x10), "cross": (0, 0x20), "circle": (0, 0x40), "triangle": (0, 0x80),
    "l1": (1, 0x01), "r1": (1, 0x02), "l2": (1, 0x04), "r2": (1, 0x08),
    "share": (1, 0x10), "options": (1, 0x20), "l3": (1, 0x40), "r3": (1, 0x80),
    "ps": (2, 0x01), "pad": (2, 0x02),
}
DPAD = {None: 8, "up": 0, "right": 2, "down": 4, "left": 6}


def with_crc(seed, data):
    crc = zlib.crc32(bytes([seed]) + bytes(data))
    return bytes(data) + struct.pack("<I", crc)


class VirtualDualSense:
    def __init__(self, mac=(0x02, 0x00, 0x00, 0xC0, 0xC0, 0x01), name="DualSense Wireless Controller"):
        self.mac = mac
        self.fd = os.open("/dev/uhid", os.O_RDWR)
        self.lock = threading.Lock()
        self.buttons = set()
        self.dpad = None
        self.sticks = [128, 128, 128, 128]
        self.touch = [None, None]        # (id, x, y)
        self.seq = 0
        self.outputs = []             # output reports the host sent us
        self.started = threading.Event()
        self.opened = threading.Event()
        self.running = True
        with open(RDESC, "rb") as f:
            rdesc = f.read()
        uniq = ":".join(f"{b:02x}" for b in reversed(mac)).encode()
        create = struct.pack("<I128s64s64sHHIIII4096s", UHID_CREATE2, name.encode(),
                             b"couchpad-uhid", uniq, len(rdesc), BUS_BLUETOOTH,
                             0x054C, 0x0CE6, 0x8100, 0, rdesc)
        os.write(self.fd, create.ljust(EVENT_SIZE, b"\0"))
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # -- kernel -> device -----------------------------------------------------
    def _feature(self, rnum):
        if rnum == 0x09:          # pairing info: MAC
            data = bytes([0x09]) + bytes(self.mac) + bytes(9)
            return with_crc(0xA3, data[:16])
        if rnum == 0x20:          # firmware info
            buf = bytearray(60)
            buf[0] = 0x20
            struct.pack_into("<I", buf, 24, 0x00000415)    # hardware version
            struct.pack_into("<I", buf, 28, 0x01000032)    # firmware version
            struct.pack_into("<H", buf, 44, 0x0630)        # update version
            return with_crc(0xA3, buf)
        if rnum == 0x05:          # calibration (plausible, non-zero ranges)
            buf = bytearray(37)
            buf[0] = 0x05
            vals = [0, 0, 0,                   # gyro bias
                    8000, -8000, 8000, -8000, 8000, -8000,   # gyro plus/minus
                    540, 540,                  # gyro speed plus/minus
                    8192, -8192, 8192, -8192, 8192, -8192]   # accel
            struct.pack_into("<" + "h" * len(vals), buf, 1, *vals)
            return with_crc(0xA3, buf)
        return None

    def _loop(self):
        while self.running:
            r, _, _ = select.select([self.fd], [], [], 0.1)
            if not r:
                continue
            try:
                ev = os.read(self.fd, EVENT_SIZE)
            except OSError:
                return
            etype = struct.unpack_from("<I", ev)[0]
            if etype == UHID_OUTPUT:
                # struct uhid_output_req { __u8 data[4096]; __u16 size; __u8 rtype; }
                size = struct.unpack_from("<H", ev, 4 + 4096)[0]
                self.outputs.append(bytes(ev[4:4 + size]))
            elif etype == UHID_START:
                self.started.set()
            elif etype == UHID_OPEN:
                self.opened.set()
            elif etype == UHID_GET_REPORT:
                rid, rnum, _rtype = struct.unpack_from("<IBB", ev, 4)
                data = self._feature(rnum)
                if data is None:
                    reply = struct.pack("<IIHH", UHID_GET_REPORT_REPLY, rid, 5, 0)
                else:
                    reply = struct.pack("<IIHH", UHID_GET_REPORT_REPLY, rid, 0, len(data)) + data
                with self.lock:
                    os.write(self.fd, reply.ljust(EVENT_SIZE, b"\0"))
            elif etype == UHID_SET_REPORT:
                rid = struct.unpack_from("<I", ev, 4)[0]
                reply = struct.pack("<IIH", UHID_SET_REPORT_REPLY, rid, 0)
                with self.lock:
                    os.write(self.fd, reply.ljust(EVENT_SIZE, b"\0"))

    # -- device -> kernel -------------------------------------------------------
    def report(self):
        c = bytearray(72)
        c[0:4] = bytes(self.sticks)
        c[6] = self.seq & 0xFF
        b = [DPAD[self.dpad], 0, 0, 0]
        for name in self.buttons:
            i, m = BUTTONS[name]
            b[i] |= m
        c[7:11] = bytes(b)
        for i, pt in enumerate(self.touch):
            o = 32 + 4 * i
            if pt is None:
                c[o] = 0x80
            else:
                tid, x, y = pt
                c[o] = tid & 0x7F
                c[o + 1] = x & 0xFF
                c[o + 2] = ((x >> 8) & 0x0F) | ((y & 0x0F) << 4)
                c[o + 3] = y >> 4
        c[52] = 0x08              # battery 80 %, discharging
        self.seq += 1
        return with_crc(0xA1, bytes([0x31, 0x10]) + bytes(c))   # 78 bytes

    def send(self):
        data = self.report()
        ev = struct.pack("<IH", UHID_INPUT2, len(data)) + data
        with self.lock:
            os.write(self.fd, ev.ljust(EVENT_SIZE, b"\0"))

    # Convenience --------------------------------------------------------------
    def press(self, *names):
        self.buttons.update(names)
        self.send()

    def release(self, *names):
        self.buttons.difference_update(names)
        self.send()

    def tap(self, name, hold=0.06):
        self.press(name)
        time.sleep(hold)
        self.release(name)

    def hold(self, names, seconds):
        self.press(*names)
        end = time.time() + seconds
        while time.time() < end:      # keep reports flowing like real hardware
            time.sleep(0.02)
            self.send()
        self.release(*names)

    def swipe(self, start, end, steps=40, dt=0.006, tid=1):
        for i in range(steps + 1):
            x = round(start[0] + (end[0] - start[0]) * i / steps)
            y = round(start[1] + (end[1] - start[1]) * i / steps)
            self.touch[0] = (tid, x, y)
            self.send()
            time.sleep(dt)
        self.touch[0] = None
        self.send()

    def close(self):
        self.running = False
        self.thread.join(1)
        try:
            os.write(self.fd, struct.pack("<I", UHID_DESTROY).ljust(EVENT_SIZE, b"\0"))
        finally:
            os.close(self.fd)
