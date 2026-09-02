"""display: brightness and keyboard sliders, night light, auto-brightness."""
import os
import weakref

from macarchy_dfr.widgets import Button, Slider


def _read(path, default=0):
    try:
        with open(path) as f:
            return int(f.read().strip() or default)
    except (OSError, ValueError):
        return default


class Module:
    MAIN_DIR = "/sys/class/backlight/apple-panel-bl"
    KBD_DIR = "/sys/class/leds/kbd_backlight"
    RUNTIME = None

    def setup(self, api):
        self.api = api
        self.widgets = weakref.WeakSet()
        self.night = False
        self.auto = False
        api.widget("brightness", self.brightness)
        api.widget("keyboard", self.keyboard)
        api.widget("nightlight", self.nightlight)
        api.widget("auto", self.autobright)
        api.watch_file(os.path.join(self.MAIN_DIR, "brightness"), self.refresh)
        api.watch_file(os.path.join(self.KBD_DIR, "brightness"), self.refresh)
        api.every(5, self.refresh)
        api.every(30, self.poll_night)
        api.after(0, self.poll_night)

    def _runtime(self):
        return self.RUNTIME or os.environ.get("XDG_RUNTIME_DIR") or "/tmp"

    def refresh(self):
        main = _read(f"{self.MAIN_DIR}/brightness") / max(1, _read(f"{self.MAIN_DIR}/max_brightness", 1))
        kbd = _read(f"{self.KBD_DIR}/brightness") / max(1, _read(f"{self.KBD_DIR}/max_brightness", 255))
        rt = self._runtime()
        self.auto = os.path.exists(f"{rt}/omarchy-als.pid") and not os.path.exists(f"{rt}/omarchy-als.paused")
        for w in list(self.widgets):
            if w.params.get("_kind") == "brightness" and not w.pressed:
                w.set_value(main)
            elif w.params.get("_kind") == "keyboard" and not w.pressed:
                w.set_value(kbd)
            elif w.params.get("_kind") == "auto" and w.active != self.auto:
                w.active = self.auto
                w.invalidate()
            elif w.params.get("_kind") == "night" and w.active != self.night:
                w.active = self.night
                w.invalidate()

    def poll_night(self):
        def done(rc, out):
            try:
                self.night = int(out.strip()) < 6000
            except ValueError:
                self.night = False
            self.refresh()
        self.api.run(["hyprctl", "hyprsunset", "temperature"], on_done=done)

    def brightness(self, api, **p):
        w = Slider(api, min_icon="brightness_low", max_icon="brightness_high", _kind="brightness",
                   on_change=lambda v: api.run_detached(f"omarchy-brightness-display --no-osd {int(round(v * 100))}%"), **p)
        self.widgets.add(w)
        return w

    def keyboard(self, api, **p):
        mx = _read(f"{self.KBD_DIR}/max_brightness", 255)
        w = Slider(api, min_icon="keyboard", max_icon="keyboard", _kind="keyboard",
                   on_change=lambda v: api.run_detached(f"brightnessctl -q -d kbd_backlight set {int(round(v * mx))}"), **p)
        self.widgets.add(w)
        return w

    def nightlight(self, api, **p):
        def tap():
            api.run_detached("omarchy toggle nightlight")
            api.after(1.0, self.poll_night)
        w = Button(api, icon="bedtime", tint=api.theme.ACCENT_ORANGE, on_tap=tap, _kind="night", **p)
        self.widgets.add(w)
        return w

    def autobright(self, api, **p):
        def tap():
            api.run_detached("omarchy-als toggle")
            api.after(0.5, self.refresh)
        w = Button(api, icon="brightness_auto", on_tap=tap, _kind="auto", **p)
        self.widgets.add(w)
        return w
