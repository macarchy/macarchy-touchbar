"""The widgets. Each one draws inside its rect and reacts to gestures.

Draw is pure: no I/O, no subprocess. Anything a widget needs to know, it was
told before (set_text, set_value) or reads from its module through api.
"""
import cairo
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
    WIDTH = 130

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
            return max(self.WIDTH, (self._text_w or 60) + 32 + (30 if self.icon else 0))
        return self.WIDTH

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


class Slider(Widget):
    stretch = 1
    captures_drag = True
    KNOB = 28
    RAIL = 8
    END = 40

    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.min_icon, self.max_icon = p.get("min_icon"), p.get("max_icon")
        self.width = p.get("width")
        self.value = float(p.get("value", 0.0))
        self.on_change = p.get("on_change")
        self.accent = p.get("accent", Theme.FG)
        self._last_emit = -1.0
        if self.width:
            self.stretch = 0

    def measure(self):
        return int(self.width or 0)

    def _rail(self):
        r = self.rect
        pad = self.END if (self.min_icon or self.max_icon) else self.KNOB // 2
        return r.x + pad, r.right - pad

    def _value_at(self, x):
        x0, x1 = self._rail()
        return min(1.0, max(0.0, (x - x0) / max(1, x1 - x0)))

    def set_value(self, v):
        v = min(1.0, max(0.0, float(v)))
        if abs(v - self.value) > 1e-4:
            self.value = v
            self.invalidate()

    def _emit(self, force):
        now = self.api.now() if (self.api and hasattr(self.api, "now")) else None
        if not force and now is not None and now - self._last_emit < 0.05:
            return
        if now is not None:
            self._last_emit = now
        if self.on_change:
            self.on_change(self.value)

    def on_press(self, x, y):
        self.set_value(self._value_at(x))

    def on_tap(self, x, y):
        self.set_value(self._value_at(x))
        self._emit(True)

    def on_drag(self, x, y):
        self.set_value(self._value_at(x))
        self._emit(False)

    def on_drag_end(self, x, y):
        self.set_value(self._value_at(x))
        self._emit(True)

    def draw(self, cr, painter):
        r = self.rect
        cy = r.y + r.h / 2
        x0, x1 = self._rail()
        if self.min_icon:
            painter.icon(cr, self.min_icon, r.x + self.END / 2, cy, size=20, tint=Theme.FG_DIM)
        if self.max_icon:
            painter.icon(cr, self.max_icon, r.right - self.END / 2, cy, size=20, tint=Theme.FG_DIM)
        painter.pill(cr, Rect(x0, int(cy - self.RAIL / 2), x1 - x0, self.RAIL), Theme.RAIL, radius=4)
        kx = x0 + (x1 - x0) * self.value
        painter.pill(cr, Rect(x0, int(cy - self.RAIL / 2), int(kx - x0), self.RAIL), self.accent, radius=4)
        cr.set_source_rgb(*Theme.FG)
        cr.arc(kx, cy, self.KNOB / 2, 0, 6.2832)
        cr.fill()


class Meter(Widget):
    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.width = int(p.get("width", 200))
        self.bands = [float(p.get("level", 0.0))] * int(p.get("bands", 1))

    def measure(self):
        return self.width

    def set_level(self, v):
        self.set_bands([v] * len(self.bands))

    def set_bands(self, values):
        values = [min(1.0, max(0.0, float(v))) for v in values]
        if values != self.bands:
            self.bands = values
            self.invalidate()

    def draw(self, cr, painter):
        r = self.rect
        n = max(1, len(self.bands))
        gap = 3
        bw = max(2, (r.w - gap * (n - 1)) // n)
        for i, v in enumerate(self.bands):
            h = max(4, int((r.h - 8) * v))
            painter.pill(cr, Rect(r.x + i * (bw + gap), r.y + (r.h - h) // 2, bw, h), Theme.FG, radius=min(3, bw // 2))


class BrokenWidget(Widget):
    def __init__(self, reason="", api=None, **p):
        super().__init__(api, **p)
        self.reason = reason

    def draw(self, cr, painter):
        painter.pill(cr, self.rect, Theme.PILL)
        painter.icon(cr, "warning", self.rect.x + self.rect.w / 2, self.rect.y + self.rect.h / 2,
                     tint=Theme.ACCENT_AMBER)


class Sprite(Widget):
    def __init__(self, api=None, **p):
        super().__init__(api, **p)
        self.sheet = None
        self.frames = int(p.get("frames", 1))
        self.fps = int(p.get("fps", 8))
        self.frame_w, self.frame_h = int(p.get("frame_w", 72)), int(p.get("frame_h", 56))
        self.scale = p.get("scale")
        self.width = int(p.get("width", 64))
        self.frame = 0
        self._surface = None
        if p.get("sheet"):
            self.set_sheet(p["sheet"], self.frames, self.fps)

    def measure(self):
        return self.width

    def set_sheet(self, path, frames, fps=None):
        try:
            self._surface = cairo.ImageSurface.create_from_png(path)
        except Exception:
            self._surface = None
        self.sheet, self.frames, self.frame = path, max(1, int(frames)), 0
        if fps:
            self.fps = int(fps)
        self.invalidate()

    def tick(self):
        if self.frames > 1:
            self.frame = (self.frame + 1) % self.frames
            self.invalidate()

    def draw(self, cr, painter):
        r = self.rect
        if self._surface is None:
            return
        scale = float(self.scale) if self.scale else (44 / self.frame_h if self.frame_h > 44 else max(1, 44 // self.frame_h))
        w, h = self.frame_w * scale, self.frame_h * scale
        cr.save()
        cr.translate(r.x + (r.w - w) / 2, r.y + (r.h - h) / 2)
        cr.scale(scale, scale)
        cr.set_source_surface(self._surface, -self.frame * self.frame_w, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.rectangle(0, 0, self.frame_w, self.frame_h)
        cr.fill()
        cr.restore()
