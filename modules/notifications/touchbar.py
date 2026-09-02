"""notifications: mirror desktop notifications onto the bar for a few seconds.

Omarchy's shell owns org.freedesktop.Notifications, so we observe it with
dbus-monitor instead of serving it.
"""
import re

from gi.repository import GLib

from macarchy_dfr.layout import Layout, Row
from macarchy_dfr.widgets import Button, Image, Label

NOTIFY_MATCH = "interface='org.freedesktop.Notifications',member='Notify'"
_RE_STRING = re.compile(r'^\s+string "(.*)"$')
_RE_BYTE = re.compile(r"^\s+variant\s+byte (\d+)")


class NotifyParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active, self.strings, self.urgency, self.expect_urgency = False, [], 1, False

    def feed(self, line):
        if line.startswith("method call") and "member=Notify" in line:
            self.reset()
            self.active = True
            return None
        if not self.active:
            return None
        m = _RE_STRING.match(line)
        if m:
            if len(self.strings) < 4:
                self.strings.append(m.group(1))
            elif m.group(1) == "urgency":
                self.expect_urgency = True
            return None
        m = _RE_BYTE.match(line)
        if m and self.expect_urgency:
            self.urgency, self.expect_urgency = int(m.group(1)), False
            return None
        if line.startswith("   int32"):
            app, icon, summary, body = (self.strings + ["", "", "", ""])[:4]
            self.active = False
            if not (summary or body):
                return None
            return {"app": app, "icon": icon, "summary": summary, "body": body, "urgency": self.urgency}
        return None


class Module:
    def setup(self, api):
        self.api = api
        self.parser = NotifyParser()
        self.current = None
        api.scene("notification", self.scene)
        api.after(0, self.start)

    def start(self):
        def on_done(rc, out):
            if rc == -1:
                self.api.log("dbus-monitor could not be started")
                return
            self.api.after(5, self.start)
        self.api.run(["dbus-monitor", "--session", NOTIFY_MATCH], on_line=self.on_line, on_done=on_done)

    def on_line(self, line):
        n = self.parser.feed(line)
        if n:
            n["summary"] = GLib.markup_escape_text(n["summary"])
            n["body"] = GLib.markup_escape_text(n["body"])
            self.current = n
            self.api.show_scene("notification", priority=30, timeout=10 if n["urgency"] >= 2 else 5)

    def scene(self, api):
        n = self.current or {}
        icon = api.app_icon_path(n.get("icon") or n.get("app") or "", 32)
        summary, body = n.get("summary", ""), n.get("body", "")
        text = f"<b>{summary}</b>" + (f"  <span foreground='#999999'>{body}</span>" if body else "")
        widgets = [Button(api, icon="close", close=True, on_tap=lambda: api.hide_scene("notification"))]
        if icon:
            widgets.append(Image(api, path=icon, width=44))
        if n.get("urgency", 1) >= 2:
            widgets.append(Button(api, icon="priority_high", tint=api.theme.ACCENT_RED, active=True, width=44))
        widgets.append(Label(api, text=text, markup=True, stretch=1, align="left"))
        return Layout(Row(widgets), Row([]))
