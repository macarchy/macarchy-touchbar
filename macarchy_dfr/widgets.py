"""The widgets. Each one draws inside its rect and reacts to gestures.

Draw is pure: no I/O, no subprocess. Anything a widget needs to know, it was
told before (set_text, set_value) or reads from its module through api.
"""
from .draw import Theme
from .geometry import Rect


class Widget:
    stretch = 0
    captures_drag = False

    def __init__(self, api=None, **params):
        self.api = api
        self.params = params
        self.rect = None
        self.pressed = False
        self.stretch = int(params.get("stretch", type(self).stretch))

    def measure(self):
        return 64

    def draw(self, cr, painter):
        pass

    def on_press(self, x, y): pass
    def on_tap(self, x, y): pass
    def on_long_press(self, x, y): pass
    def on_drag(self, x, y): pass
    def on_drag_end(self, x, y): pass
    def on_release(self): pass

    def invalidate(self):
        if self.api:
            self.api.invalidate(self)

    def _pill_color(self):
        return Theme.PILL_PRESSED if self.pressed else Theme.PILL


class Button(Widget):
    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.icon, self.text = p.get("icon"), p.get("text")
        self.run, self.keys, self.group = p.get("run"), p.get("keys"), p.get("group")
        self.close = bool(p.get("close", False))
        self.active = bool(p.get("active", False))
        self.badge = p.get("badge")
        self.tint = p.get("tint")
        self.width = p.get("width")
        self._on_tap = p.get("on_tap")
        self._on_long = p.get("on_long_press")
        self._text_w = None

    def measure(self):
        if self.width:
            return int(self.width)
        if self.text:
            if self._text_w is None and self.api is not None:
                self._text_w = self.api.measure_text(self.text)
            return max(64, (self._text_w or 60) + 32 + (30 if self.icon else 0))
        return 64

    def draw(self, cr, painter):
        r = self.rect
        accent = self.tint or Theme.ACCENT_BLUE
        color = Theme.PILL_PRESSED if self.pressed else (accent if self.active else Theme.PILL)
        painter.pill(cr, r, color)
        cx = r.x + r.w / 2
        if self.icon and self.text:
            painter.icon(cr, self.icon, r.x + 28, r.y + r.h / 2, fill=1.0 if self.active else 0.0)
            painter.text(cr, self.text, Rect(r.x + 48, r.y, r.w - 56, r.h), align="left")
        elif self.icon:
            painter.icon(cr, self.icon, cx, r.y + r.h / 2, fill=1.0 if self.active else 0.0,
                         tint=(self.tint if (self.tint and not self.active) else Theme.FG))
        elif self.text:
            painter.text(cr, self.text, r)
        if self.badge:
            bx, by = r.right - 10, r.y + 10
            cr.set_source_rgb(*Theme.ACCENT_RED)
            cr.arc(bx, by, 6 if self.badge is True else 9, 0, 6.2832)
            cr.fill()
            if self.badge is not True:
                painter.text(cr, str(self.badge), Rect(bx - 9, by - 9, 18, 18), size=12)

    def on_tap(self, x, y):
        if self._on_tap:
            self._on_tap()
        elif self.run:
            self.api.run_detached(self.run)
        elif self.keys:
            self.api.keys(self.keys)
        elif self.group:
            self.api.open_group(self.group)
        elif self.close:
            self.api.close_group()

    def on_long_press(self, x, y):
        if self._on_long:
            self._on_long()


class Label(Widget):
    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.text = str(p.get("text", ""))
        self.width = p.get("width")
        self.align = p.get("align", "center")
        self.size = int(p.get("size", Theme.TEXT_PT))
        self.color = p.get("color", Theme.FG)
        self.markup = bool(p.get("markup", False))

    def measure(self):
        if self.width:
            return int(self.width)
        if self.api is not None:
            return self.api.measure_text(self.text, self.size) + 16
        return 8 * len(self.text) + 16

    def set_text(self, s):
        s = str(s)
        if s != self.text:
            self.text = s
            self.invalidate()

    def draw(self, cr, painter):
        painter.text(cr, self.text, self.rect, align=self.align, color=self.color,
                     size=self.size, markup=self.markup)


class Spacer(Widget):
    stretch = 1

    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.width = p.get("width")
        if self.width:
            self.stretch = 0

    def measure(self):
        return int(self.width or 0)


class Image(Widget):
    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.path = p.get("path")
        self.width = int(p.get("width", 44))
        self.radius = int(p.get("radius", Theme.RADIUS))

    def measure(self):
        return self.width

    def set_path(self, path):
        if path != self.path:
            self.path = path
            self.invalidate()

    def draw(self, cr, painter):
        if not (self.path and painter.image(cr, self.path, self.rect, self.radius)):
            painter.pill(cr, self.rect, Theme.PILL)
