"""The Touch Bar's own backlight: follows the main panel, dims, sleeps."""
import os
import subprocess
import time

from .log import log


class BacklightPolicy:
    def __init__(self, dim_after=60, off_after=300, dim_level=0.15):
        self.dim_after, self.off_after, self.dim_level = dim_after, off_after, dim_level

    def level(self, main_fraction, idle_seconds, manual=None):
        base = manual / 100 if manual is not None else min(1.0, max(0.25, main_fraction))
        if self.off_after and idle_seconds >= self.off_after:
            return 0.0
        if self.dim_after and idle_seconds >= self.dim_after:
            return base * self.dim_level
        return base


def brightnessctl(dev):
    def write(n):
        subprocess.Popen(["brightnessctl", "-q", "-d", dev, "set", str(int(n))],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return write


class BarBacklight:
    def __init__(self, loop, policy, bar_dev="228600000.dsi.0", bar_max=None,
                 main_dir="/sys/class/backlight/apple-panel-bl", write=None, now=time.monotonic):
        self.loop, self.policy, self.now = loop, policy, now
        self.main_dir = main_dir
        self.write = write or brightnessctl(bar_dev)
        self.bar_max = bar_max or self._read(f"/sys/class/backlight/{bar_dev}/max_brightness", 255)
        self.last_touch = now()
        self.manual = None
        self.last_written = None
        self.awake = True
        self._listeners = []
        if loop:
            loop.every(2.0, self.poll)

    @staticmethod
    def _read(path, default):
        try:
            with open(path) as f:
                return int(f.read().strip() or default)
        except (OSError, ValueError):
            return default

    def on_awake_change(self, fn):
        self._listeners.append(fn)

    def touched(self):
        self.last_touch = self.now()
        self.poll()

    def set_manual(self, pct):
        self.manual = pct
        self.poll()

    def poll(self):
        cur = self._read(os.path.join(self.main_dir, "brightness"), 128)
        mx = self._read(os.path.join(self.main_dir, "max_brightness"), 255)
        lvl = self.policy.level(cur / max(1, mx), self.now() - self.last_touch, self.manual)
        n = int(self.bar_max * lvl)
        if n != self.last_written:
            self.last_written = n
            self.write(n)
        awake = n > 0
        if awake != self.awake:
            self.awake = awake
            for fn in self._listeners:
                fn(awake)
