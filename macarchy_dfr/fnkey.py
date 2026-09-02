"""The Fn key on the internal keyboard, straight from evdev."""
import os
import struct

KEY_FN = 0x1d0
_FMT = "llHHi"
_SZ = struct.calcsize(_FMT)


def find_keyboard_device():
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return None
    for block in blocks:
        if "MTP keyboard" not in block:
            continue
        for tok in block.split():
            if tok.startswith("event"):
                return f"/dev/input/{tok}"
    return None


def parse_fn(data):
    out = []
    for i in range(0, len(data) - _SZ + 1, _SZ):
        _s, _u, typ, code, val = struct.unpack(_FMT, data[i:i + _SZ])
        if typ == 1 and code == KEY_FN and val in (0, 1):
            out.append(val == 1)
    return out


class FnWatcher:
    def __init__(self, loop, path, on_fn):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.on_fn = on_fn
        loop.add_fd(self.fd, self._readable)

    def _readable(self):
        try:
            data = os.read(self.fd, _SZ * 64)
        except BlockingIOError:
            return
        for down in parse_fn(data):
            self.on_fn(down)
