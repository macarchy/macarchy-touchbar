"""core: the toolkit as widgets any layout can name, plus the clock and the focused app."""
import time

from macarchy_dfr.geometry import Rect
from macarchy_dfr.widgets import Button, Image, Label, Meter, Slider, Spacer, Sprite


class Clock(Label):
    def __init__(self, api=None, **p):
        self.fmt = p.pop("format", "%H:%M")
        super().__init__(api, text=time.strftime(self.fmt), width=p.pop("width", 100), **p)
        if api:
            api.every(1, self._tick)

    def _tick(self):
        self.set_text(time.strftime(self.fmt))


class App(Button):
    def __init__(self, api=None, **p):
        super().__init__(api, width=p.pop("width", 260), **p)
        self.icon_path = None
        if api:
            api.on_context(self._ctx)
            if api.context:
                self._ctx(api.context)

    def _ctx(self, ctx):
        self.text = ctx.title or ctx.cls
        self.icon_path = self.api.app_icon_path(ctx.cls) if ctx.cls else None
        self.invalidate()

    def draw(self, cr, painter):
        r = self.rect
        painter.pill(cr, r, self._pill_color())
        x = r.x + 10
        if self.icon_path and painter.image(cr, self.icon_path, Rect(r.x + 8, r.y + (r.h - 40) / 2, 40, 40), radius=6):
            x = r.x + 56
        painter.text(cr, self.text or "", Rect(x, r.y, r.right - x - 8, r.h), align="left")

    def on_tap(self, x, y):
        pass


class Module:
    def setup(self, api):
        for name, cls in (("button", Button), ("label", Label), ("spacer", Spacer), ("image", Image),
                          ("slider", Slider), ("meter", Meter), ("sprite", Sprite), ("clock", Clock), ("app", App)):
            api.widget(name, cls)
        api.ipc("ping", lambda *a: "pong")
