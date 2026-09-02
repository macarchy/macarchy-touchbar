"""The bar: which layout is showing, who gets the finger, what gets redrawn."""
import shlex
import subprocess
import time

import cairo

from .config import Resolver
from .draw import Theme
from .geometry import Rect
from .layout import Layout, Row
from .log import log
from .scenes import Scene, SceneStack
from .widgets import Button

REDRAW_MIN_INTERVAL = 1 / 30


class Bar:
    def __init__(self, output, loop, painter, config, registry, host, now=time.monotonic):
        self.output, self.loop, self.painter = output, loop, painter
        self.registry, self.host, self.now = registry, host, now
        self.keyboard = None
        self.backlight = None
        self.context = None
        self._context_listeners = []
        self.scenes = SceneStack(now)
        self.open_group_name = None
        self._group_layout = None
        self._group_last_touch = 0.0
        self.fn_down = False
        self.base = Layout(Row([]), Row([]))
        self.base_name = None
        self.fn_layout = None
        self._dirty = None
        self._scheduled = False
        self._last_draw = float("-inf")
        self._pressed = None
        self._capture = None
        self.reload_config(config)

    # --- config / context ----------------------------------------------------
    def _api_for(self, module_id):
        return self.host.apis.get(module_id) if self.host else None

    def reload_config(self, config):
        self.config = config
        self.resolver = Resolver(config, self.registry, lambda mid: self._api_for(mid) or self)
        self.fn_layout = Layout(self.resolver.row(config.fn) if config.fn else
                                Row([Button(None, text=f"F{i}", keys=[f"F{i}"], stretch=1) for i in range(1, 13)]),
                                Row([]))
        self.base_name = None
        self.close_group()
        self._rebuild_base()
        self._layout_now()

    def _rebuild_base(self):
        cls = self.context.cls if self.context else ""
        title = self.context.title if self.context else ""
        name, _l, _r = self.config.pick(cls, title)
        if name != self.base_name:
            self.base_name = name
            self.base = self.resolver.layout(cls, title)
            if self.open_group_name and self._group_layout:
                self._group_layout = Layout(self._group_layout.left, self.base.right)
            self.invalidate(None)
        self._layout_now()

    def set_context(self, ctx):
        old = self.context
        self.context = ctx
        if old is None or (old.cls, old.title) != (ctx.cls, ctx.title):
            if old is not None and old.cls != ctx.cls:
                self.close_group()
            self._rebuild_base()
        if old is None or old.fn != ctx.fn:
            self.set_fn(ctx.fn)
        for fn in self._context_listeners:
            fn(ctx)
        self._layout_now()

    def on_context(self, fn):
        self._context_listeners.append(fn)

    def off_context(self, fn):
        if fn in self._context_listeners:
            self._context_listeners.remove(fn)

    def set_fn(self, down):
        if down != self.fn_down:
            self.fn_down = down
            self.invalidate(None)
        self._layout_now()

    # --- display stack ---------------------------------------------------------
    def current_layout(self):
        if self.fn_down:
            return self.fn_layout
        top = self.scenes.top()
        if top:
            return top.layout
        if self.open_group_name and self._group_layout:
            return self._group_layout
        return self.base

    def show_scene(self, module_id, name, factory, priority=50, timeout=None, dismissable=True,
                   on_hide=None):
        layout = factory(self._api_for(module_id))
        self.scenes.show(Scene(name, layout, priority, timeout, dismissable, on_hide))
        self.invalidate(None)
        self._layout_now()

    def hide_scene(self, name):
        self.scenes.hide(name)
        self.invalidate(None)
        self._layout_now()

    def open_group(self, name):
        if name not in self.config.groups:
            return
        self.open_group_name = name
        self._group_layout = Layout(self.resolver.group_row(name), self.base.right)
        self._group_last_touch = self.now()
        self.invalidate(None)
        self._layout_now()

    def close_group(self):
        if self.open_group_name:
            self.open_group_name = None
            self._group_layout = None
            self.invalidate(None)
        self._layout_now()

    def is_group_open(self, name):
        return self.open_group_name == name

    def slide_into(self, name, x, y):
        if name not in self.config.groups:
            return
        self.open_group(name)
        self._layout_now()
        target = self.config.groups[name].slide_into
        for w in self._group_layout.left.widgets:
            if getattr(w, "_ref", None) == target:
                self._capture = w
                w.pressed = True
                w.on_press(x, y)
                break

    def tick(self):
        now = self.now()
        if self.scenes.tick(now):
            self.invalidate(None)
        if self.open_group_name:
            g = self.config.groups[self.open_group_name]
            if g.timeout and now - self._group_last_touch >= g.timeout:
                self.close_group()

    # --- drawing -------------------------------------------------------------
    def _layout_now(self):
        self.current_layout().layout(self.output.width)

    def invalidate(self, widget=None):
        rect = widget.rect if (widget is not None and widget.rect) else Rect(0, 0, self.output.width, self.output.height)
        self._dirty = rect if self._dirty is None else self._dirty.union(rect)
        if not self._scheduled:
            self._scheduled = True
            wait = max(0.0, REDRAW_MIN_INTERVAL - (self.now() - self._last_draw))
            if wait == 0:
                self.loop.call_soon(self.redraw)
            else:
                self.loop.after(wait, self.redraw)

    def redraw(self):
        self._scheduled = False
        rect, self._dirty = self._dirty, None
        if rect is None:
            return
        self._last_draw = self.now()
        self._layout_now()
        cr = cairo.Context(self.output.surface)
        cr.rectangle(rect.x, rect.y, rect.w, rect.h)
        cr.clip()
        cr.set_source_rgb(*Theme.BG)
        cr.paint()
        for w in self.current_layout().widgets():
            if w.rect and w.rect.w and (w.rect.x < rect.right and rect.x < w.rect.right):
                cr.save()
                try:
                    w.draw(cr, self.painter)
                except Exception as e:
                    log("draw failed:", type(w).__name__, repr(e))
                finally:
                    cr.restore()
        self.output.flush(rect)

    def screenshot(self, path):
        if self._dirty:
            self.redraw()
        self.output.save_png(path)

    # --- touch -----------------------------------------------------------------
    def gesture(self, g):
        top = self.scenes.top()
        if top:
            self.scenes.touch(top.name)
        if self.open_group_name:
            self._group_last_touch = self.now()
        if g.kind == "press":
            self._layout_now()
            w = self.current_layout().hit(g.x, g.y)
            self._pressed, self._capture = w, None
            if w:
                w.pressed = True
                w.on_press(g.x, g.y)
                self.invalidate(w)
        elif g.kind in ("tap", "long_press"):
            w = self._pressed
            if w and w.rect and w.rect.contains(g.x, g.y):
                (w.on_tap if g.kind == "tap" else w.on_long_press)(g.x, g.y)
            elif w is None and g.kind == "tap" and top and top.dismissable:
                self.hide_scene(top.name)
        elif g.kind == "drag":
            target = self._capture or (self._pressed if self._pressed and self._pressed.captures_drag else None)
            if target:
                target.on_drag(g.x, g.y)
                self.invalidate(target)
        elif g.kind == "drag_end":
            target = self._capture or (self._pressed if self._pressed and self._pressed.captures_drag else None)
            if target:
                target.on_drag_end(g.x, g.y)
                self.invalidate(target)
        elif g.kind == "release":
            seen = []
            for w in (self._pressed, self._capture):
                if w and not any(w is s for s in seen):
                    seen.append(w)
                    w.pressed = False
                    w.on_release()
                    self.invalidate(w)
            self._pressed = self._capture = None

    def keys(self, names):
        if self.keyboard:
            self.keyboard.press(names)
        else:
            log("no virtual keyboard; dropped", names)

    # --- fallback api (Bar is the api for widgets whose module has none) -------
    def run_detached(self, cmd):
        subprocess.Popen(shlex.split(cmd) if isinstance(cmd, str) else cmd,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def measure_text(self, s, size=22):
        return self.painter.measure_text(s, size)
