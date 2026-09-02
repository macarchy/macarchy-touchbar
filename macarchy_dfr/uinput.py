"""A uinput keyboard that declares every key up front, so nothing is ever
'added later' and silently dropped (tiny-dfr's frozen capabilities)."""
import os
import re
import struct
import time
from fcntl import ioctl

from .log import log

HEADER = "/usr/include/linux/input-event-codes.h"
EV_SYN, EV_KEY = 0, 1
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405c5503          # _IOW('U', 3, struct uinput_setup[92 bytes])
BUS_VIRTUAL = 0x06
KEY_MAX = 0x2ff

_codes = None


def _load():
    global _codes
    if _codes is None:
        _codes = {}
        with open(HEADER) as f:
            for m in re.finditer(r"^#define (KEY_|BTN_)(\w+)\s+(0x[0-9a-fA-F]+|\d+)", f.read(), re.M):
                _codes[(m.group(1) + m.group(2)).upper()] = int(m.group(3), 0)
    return _codes


def key_code(name):
    codes = _load()
    n = name.upper()
    if n in codes:
        return codes[n]
    if "KEY_" + n in codes:
        return codes["KEY_" + n]
    raise KeyError(name)


class VirtualKeyboard:
    def __init__(self, path="/dev/uinput", name="macarchy-dfr keyboard"):
        self.fd = None
        self.available = False
        try:
            self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            for code in range(1, KEY_MAX + 1):
                ioctl(self.fd, UI_SET_KEYBIT, code)
            setup = struct.pack("HHHH80sI", BUS_VIRTUAL, 0x05ac, 0x0dfa, 1, name.encode(), 0)
            ioctl(self.fd, UI_DEV_SETUP, setup)
            ioctl(self.fd, UI_DEV_CREATE)
            self.available = True
            time.sleep(0.2)             # let the compositor pick the device up
        except OSError as e:
            log(f"uinput unavailable ({e}); key buttons will do nothing")
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

    def _emit(self, typ, code, val):
        os.write(self.fd, struct.pack("llHHi", 0, 0, typ, code, val))

    def press(self, names):
        if not self.available:
            log("dropped keys", names)
            return
        try:
            codes = [key_code(n) for n in names]
        except KeyError as e:
            log("unknown key", e)
            return
        for c in codes:
            self._emit(EV_KEY, c, 1)
        self._emit(EV_SYN, 0, 0)
        for c in reversed(codes):
            self._emit(EV_KEY, c, 0)
        self._emit(EV_SYN, 0, 0)

    def close(self):
        if self.fd is not None:
            try:
                ioctl(self.fd, UI_DEV_DESTROY)
            finally:
                os.close(self.fd)
                self.fd = None
                self.available = False
