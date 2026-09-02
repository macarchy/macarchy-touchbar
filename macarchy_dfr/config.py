"""layouts.toml v2: items, groups, layouts. Composition only; behaviour lives in modules."""
import re
import tomllib

from .groups import Group, GroupButton
from .layout import Layout, Row
from .widgets import BrokenWidget

DEFAULTS = {"dim_after": 60, "off_after": 300, "group_timeout": 15, "hud": True, "touch_flip": False}


class Config:
    def __init__(self, data):
        self.settings = {**DEFAULTS, **data.get("settings", {})}
        self.items = {}
        for name, item in data.get("items", {}).items():
            if "widget" not in item:
                raise ValueError(f"[items.{name}] has no widget")
            self.items[name] = dict(item)
        self.groups = {}
        for name, g in data.get("groups", {}).items():
            self.groups[name] = Group(name, icon=g.get("icon"), text=g.get("text"), items=g.get("items", []),
                                      slide_into=g.get("slide_into"),
                                      timeout=g.get("timeout", self.settings["group_timeout"]))
        layouts = data.get("layouts", {})
        self.fn = layouts.get("fn", {}).get("buttons") if "fn" in layouts else None
        self.layouts = []
        for name, lay in layouts.items():
            if name in ("fn", "default"):
                continue
            pattern = lay.get("match", name)
            self.layouts.append((name, re.compile(pattern, re.IGNORECASE),
                                 list(lay.get("left", [])), list(lay.get("right", []))))
        if "default" not in layouts:
            raise ValueError("[layouts.default] is required")
        d = layouts["default"]
        self.layouts.append(("default", None, list(d.get("left", [])), list(d.get("right", []))))

    @classmethod
    def parse(cls, text):
        return cls(tomllib.loads(text))

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(tomllib.load(f))

    def pick(self, cls, title):
        for name, rx, left, right in self.layouts:
            # The last entry is always [layouts.default], whose rx is None.
            if rx is None or rx.search(cls or "") or rx.search(title or ""):
                return name, left, right


class Resolver:
    def __init__(self, config, registry, api_for):
        self.config, self.registry, self.api_for = config, registry, api_for

    def _make(self, ref, params):
        module_id, _, _name = ref.rpartition(".")
        try:
            factory = self.registry.factory(ref)
        except KeyError:
            w = BrokenWidget(f"unknown widget {ref}")
            w._ref = ref
            return w
        try:
            w = factory(self.api_for(module_id), **params)
        except Exception as e:      # a module's factory must not take the bar down
            w = BrokenWidget(f"{ref}: {e!r}")
        w._ref = ref
        return w

    def widget(self, ref, _seen=()):
        if ref.startswith("group:"):
            g = self.config.groups.get(ref[6:])
            if not g:
                w = BrokenWidget(ref)
                w._ref = ref
                return w
            w = GroupButton(self.api_for("core"), g)
            w._ref = ref
            return w
        if ref in self.config.items:
            params = dict(self.config.items[ref])
            fallback = params.pop("fallback", None)
            w = self._make(params.pop("widget"), params)
            # An item whose module is absent (an optional plugin) may name a stand-in.
            if isinstance(w, BrokenWidget) and fallback and fallback not in _seen and fallback != ref:
                fw = self.widget(fallback, _seen + (ref,))
                fw._ref = ref
                return fw
            w._ref = ref
            return w
        if "." in ref:
            return self._make(ref, {})
        w = BrokenWidget(f"unknown item {ref}")
        w._ref = ref
        return w

    def row(self, refs):
        return Row([self.widget(r) for r in refs])

    def group_row(self, name):
        g = self.config.groups[name]
        close = self._make("core.button", {"icon": "close", "close": True})
        return Row([close] + [self.widget(r) for r in g.items])

    def layout(self, cls, title):
        _name, left, right = self.config.pick(cls, title)
        return Layout(self.row(left), self.row(right))
