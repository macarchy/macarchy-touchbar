"""Any hand on the machine counts as activity, not just a finger on the bar.

The backlight policy sleeps the Touch Bar after a stretch of idleness, and
idleness used to mean "nobody touched the Touch Bar" -- so it went dark while
the user was plainly working, and only a blind poke at a dark bar brought it
back. These watchers feed the same idle timer from the trackpad and the
keyboard, the way the main panel's own backlight behaves.
"""
import os

from .log import log

# The Touch Bar's own touch device is read by TouchReader, which already feeds
# the idle timer; watching it here as well would just double-count.
ACTIVITY_DEVICES = ("Apple MTP multi-touch", "Apple MTP keyboard")

_READ_SIZE = 4096
_DRAIN_LIMIT = 64          # a device streaming flat out must not trap the loop


def find_activity_devices(names=ACTIVITY_DEVICES, procfile="/proc/bus/input/devices"):
    """Event device paths for the input we treat as "the user is here"."""
    try:
        with open(procfile) as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return []
    found = {}
    for block in blocks:
        for name in names:
            if f'Name="{name}"' not in block:
                continue
            for tok in block.split():
                if tok.startswith("event"):
                    found.setdefault(name, f"/dev/input/{tok}")
                    break
    return [found[n] for n in names if n in found]


class ActivityWatcher:
    """Report that the user is present, without waking on every single report."""

    def __init__(self, loop, fds, on_activity, cooldown=2.0):
        self.loop, self.on_activity, self.cooldown = loop, on_activity, cooldown
        self.fds = list(fds)
        for fd in self.fds:
            loop.add_fd(fd, self._reader(fd))

    @classmethod
    def open(cls, loop, paths, on_activity, cooldown=2.0):
        fds = []
        for path in paths:
            try:
                fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC))
            except OSError as e:
                log(f"activity: cannot watch {path} ({e})")
        return cls(loop, fds, on_activity, cooldown)

    def close(self):
        for fd in list(self.fds):
            self._drop(fd)

    def _reader(self, fd):
        return lambda: self._readable(fd)

    def _readable(self, fd):
        if not self._drain(fd):
            return
        self.on_activity()
        # A finger crossing the trackpad reports at ~100 Hz, and every report
        # would wake the loop to learn something we already know. Stop
        # listening for a moment instead: the kernel keeps buffering, and the
        # next drain still says the user is here. The policy works in minutes.
        self.loop.remove_fd(fd)
        self.loop.after(self.cooldown, self._resumer(fd))

    def _resumer(self, fd):
        def resume():
            if fd in self.fds:
                self.loop.add_fd(fd, self._reader(fd))
        return resume

    def _drain(self, fd):
        for _ in range(_DRAIN_LIMIT):
            try:
                data = os.read(fd, _READ_SIZE)
            except BlockingIOError:
                return True
            except OSError as e:
                self._drop(fd, str(e))
                return False
            if not data:
                self._drop(fd, "EOF")
                return False
        return True

    def _drop(self, fd, why=None):
        if why:
            log(f"activity: {fd} stopped ({why})")
        self.loop.remove_fd(fd)
        if fd in self.fds:
            self.fds.remove(fd)
        try:
            os.close(fd)
        except OSError:
            pass
