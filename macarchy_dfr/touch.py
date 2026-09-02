"""Raw evdev for the Touch Bar's touch surface, and the gestures on top of it.

We do not use libinput: it does not exist for a bare touch surface off seat0,
and the multitouch B protocol is a dozen lines. Only slot 0 (the first finger)
is followed; a second finger is ignored.
"""
import os
import struct
import time
from dataclasses import dataclass
from fcntl import ioctl

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x2f, 0x35, 0x36, 0x39
_FMT = "llHHi"
_SZ = struct.calcsize(_FMT)


def _eviocgabs(code):
    # _IOR('E', 0x40 + code, struct input_absinfo[24 bytes])
    return (2 << 30) | (24 << 16) | (0x45 << 8) | (0x40 + code)


@dataclass(frozen=True)
class TouchEvent:
    kind: str
    x: int
    y: int
    t: float


def find_touch_device():
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return None
    for block in blocks:
        if "Touch Bar" not in block or "Virtual" in block:
            continue
        for tok in block.split():
            if tok.startswith("event"):
                return f"/dev/input/{tok}"
    return None


class TouchReader:
    def __init__(self, fd, xrange, yrange, width=2008, height=60, flip=False):
        self.fd, self.w, self.h, self.flip = fd, width, height, flip
        self.xmin, self.xmax = xrange
        self.ymin, self.ymax = yrange
        self.slot = 0
        self.down = False
        self.x = self.y = 0
        self.pending = None      # 'down' | 'move' | 'up' to emit at SYN
        self.buf = b""

    @classmethod
    def open(cls, path, **kw):
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        ranges = []
        for code in (ABS_MT_POSITION_X, ABS_MT_POSITION_Y):
            info = bytearray(24)
            ioctl(fd, _eviocgabs(code), info)
            _v, lo, hi, *_ = struct.unpack("6i", info)
            ranges.append((lo, hi))
        return cls(fd, ranges[0], ranges[1], **kw)

    def _scale(self):
        x = (self.x - self.xmin) * (self.w - 1) // max(1, self.xmax - self.xmin)
        y = (self.y - self.ymin) * (self.h - 1) // max(1, self.ymax - self.ymin)
        if self.flip:
            x = self.w - 1 - x
        return x, y

    def feed(self, data):
        # The evdev timestamp is CLOCK_REALTIME; every deadline in the daemon
        # (GestureRecognizer.tick, the loop's timers) runs on time.monotonic().
        # Stamp the events on that clock instead, or long-press never fires.
        out = []
        t = time.monotonic()
        self.buf += data
        while len(self.buf) >= _SZ:
            _sec, _usec, typ, code, val = struct.unpack(_FMT, self.buf[:_SZ])
            self.buf = self.buf[_SZ:]
            if typ == EV_ABS and code == ABS_MT_SLOT:
                self.slot = val
            elif self.slot != 0:
                continue
            elif typ == EV_ABS and code == ABS_MT_TRACKING_ID:
                if val >= 0 and not self.down:
                    self.down, self.pending = True, "down"
                elif val < 0 and self.down:
                    self.down, self.pending = False, "up"
            elif typ == EV_ABS and code == ABS_MT_POSITION_X:
                self.x = val
                self.pending = self.pending or ("move" if self.down else None)
            elif typ == EV_ABS and code == ABS_MT_POSITION_Y:
                self.y = val
                self.pending = self.pending or ("move" if self.down else None)
            elif typ == EV_SYN and self.pending:
                x, y = self._scale()
                out.append(TouchEvent(self.pending, x, y, t))
                self.pending = None
        return out

    def read(self):
        try:
            return self.feed(os.read(self.fd, _SZ * 64))
        except BlockingIOError:
            return []


@dataclass(frozen=True)
class Gesture:
    kind: str
    x: int
    y: int


class GestureRecognizer:
    def __init__(self, tap_s=0.3, long_s=0.5, slop=12):
        self.tap_s, self.long_s, self.slop = tap_s, long_s, slop
        self.origin = None
        self.dragging = False
        self.long_fired = False
        self.last = None

    def deadline(self):
        if self.origin and not self.dragging and not self.long_fired:
            return self.origin.t + self.long_s
        return None

    def feed(self, ev):
        out = []
        if ev.kind == "down":
            self.origin, self.dragging, self.long_fired, self.last = ev, False, False, ev
            out.append(Gesture("press", ev.x, ev.y))
        elif ev.kind == "move" and self.origin:
            self.last = ev
            if self.dragging or max(abs(ev.x - self.origin.x), abs(ev.y - self.origin.y)) > self.slop:
                self.dragging = True
                out.append(Gesture("drag", ev.x, ev.y))
        elif ev.kind == "up" and self.origin:
            if self.dragging:
                out.append(Gesture("drag_end", ev.x, ev.y))
            elif not self.long_fired and ev.t - self.origin.t < self.tap_s:
                out.append(Gesture("tap", ev.x, ev.y))
            out.append(Gesture("release", ev.x, ev.y))
            self.origin = None
            self.dragging = False
        return out

    def tick(self, now):
        d = self.deadline()
        if d is not None and now >= d:
            self.long_fired = True
            return [Gesture("long_press", self.last.x, self.last.y)]
        return []
