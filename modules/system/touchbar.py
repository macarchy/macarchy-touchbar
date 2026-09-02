"""system: battery, lock, charge limit, screenshot."""
import os
import weakref

from macarchy_dfr.layout import Layout, Row
from macarchy_dfr.widgets import Button, Label


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip() or default
    except OSError:
        return default


def _int(path, default=0):
    try:
        return int(_read(path, str(default)))
    except ValueError:
        return default


class Module:
    BAT = "/sys/class/power_supply/macsmc-battery"

    def setup(self, api):
        self.api = api
        self.widgets = weakref.WeakSet()
        api.widget("battery", self.battery)
        api.widget("lock", lambda api, **p: Button(api, icon="lock", run="omarchy system lock", **p))
        api.widget("charge_limit", self.charge_limit)
        api.widget("screenshot", lambda api, **p: Button(api, icon="photo_camera", run="omarchy capture screenshot", **p))
        api.scene("battery", self.battery_scene)
        api.every(10, self.refresh)
        api.watch_file(os.path.join(self.BAT, "status"), self.refresh)

    def state(self):
        cap = _int(f"{self.BAT}/capacity", 0)
        status = _read(f"{self.BAT}/status", "Unknown")
        limit = _int(f"{self.BAT}/charge_control_end_threshold", 100)
        return cap, status, limit

    def refresh(self):
        cap, status, limit = self.state()
        theme = self.api.theme
        if status == "Charging":
            icon, tint = "battery_charging_full", theme.ACCENT_GREEN
        elif cap < 10:
            icon, tint = "battery_alert", theme.ACCENT_RED
        else:
            icon = "battery_full" if cap >= 95 else f"battery_{max(1, min(6, round(cap / 100 * 7)))}_bar"
            # Tint by charge: green >= 50%, orange 20-50%, red < 20%
            if cap >= 50:
                tint = theme.ACCENT_GREEN
            elif cap >= 20:
                tint = theme.ACCENT_ORANGE
            else:
                tint = theme.ACCENT_RED
        for w in list(self.widgets):
            kind = w.params.get("_kind")
            if kind == "battery":
                changed = (w.text, w.icon, w.tint) != (f"{cap} %", icon, tint)
                w.text, w.icon, w.tint = f"{cap} %", icon, tint
                if changed:
                    w.invalidate()
            elif kind == "limit" and w.active != (limit <= 80):
                w.active = limit <= 80
                w.invalidate()

    def battery(self, api, **p):
        w = Button(api, icon="battery_full", text="…", _kind="battery",
                   on_long_press=lambda: api.show_scene("battery", priority=40, timeout=4), **p)
        self.widgets.add(w)
        return w

    def battery_scene(self, api):
        cap, status, limit = self.state()
        secs = _int(f"{self.BAT}/time_to_full_now" if status == "Charging" else f"{self.BAT}/time_to_empty_now", 0)
        h, m = divmod(secs // 60, 60)
        when = f"{h} h {m:02d}" if secs else "—"
        text = (f"{cap} % · {when} avant la charge complète" if status == "Charging"
                else f"{cap} % · {when} restantes")
        if limit <= 80:
            text += f" · limite {limit} %"
        return Layout(Row([Label(api, text=text, stretch=1, align="left")]), Row([]))

    def charge_limit(self, api, **p):
        def tap():
            api.run_detached("omarchy-battery-limit toggle")
            api.after(1.0, self.refresh)
        w = Button(api, icon="battery_saver", on_tap=tap, _kind="limit", **p)
        self.widgets.add(w)
        return w
