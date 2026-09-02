import re

import pytest

from macarchy_dfr.config import Config, Resolver
from macarchy_dfr.widgets import Button, BrokenWidget
from macarchy_dfr.groups import GroupButton

TOML = '''
[settings]
group_timeout = 9

[items.newtab]
widget = "core.button"
icon = "add"
keys = ["LeftCtrl", "T"]

[groups.display]
icon = "brightness_6"
items = ["display.brightness", "newtab"]
slide_into = "display.brightness"

[layouts.default]
left = ["newtab", "core.spacer"]
right = ["group:display", "core.clock"]

[layouts.browser]
match = "firefox|zen"
left = ["newtab"]
right = ["core.clock"]

[layouts.fn]
buttons = ["fn1"]
[items.fn1]
widget = "core.button"
text = "F1"
keys = ["F1"]
'''


class Registry:
    def factory(self, ref):
        return {"core.button": Button, "core.clock": lambda api, **p: Button(api, text="12:34"),
                "core.spacer": lambda api, **p: Button(api, text=" ")}[ref]


def test_parse_merges_settings_and_orders_layouts():
    c = Config.parse(TOML)
    assert c.settings["group_timeout"] == 9 and c.settings["dim_after"] == 60
    assert [n for n, *_ in c.layouts] == ["browser", "default"]
    assert c.fn == ["fn1"]
    assert c.groups["display"].slide_into == "display.brightness"


def test_pick_matches_class_or_title_then_default():
    c = Config.parse(TOML)
    assert c.pick("zen", "")[0] == "browser"
    assert c.pick("kitty", "Mozilla Firefox")[0] == "browser"
    assert c.pick("kitty", "shell")[0] == "default"


def test_resolver_builds_widgets_groups_and_broken_refs():
    c = Config.parse(TOML)
    r = Resolver(c, Registry(), api_for=lambda mid: None)
    assert isinstance(r.widget("newtab"), Button) and r.widget("newtab").keys == ["LeftCtrl", "T"]
    assert isinstance(r.widget("group:display"), GroupButton)
    assert isinstance(r.widget("display.brightness"), BrokenWidget)
    assert isinstance(r.widget("nope"), BrokenWidget)
    lay = r.layout("zen", "")
    assert len(lay.left.widgets) == 1 and len(lay.right.widgets) == 1
    row = r.group_row("display")
    assert row.widgets[0].close and len(row.widgets) == 3


def test_missing_default_layout_is_an_error():
    with pytest.raises(ValueError):
        Config.parse('[layouts.x]\nleft=[]\nright=[]\n')


def test_real_layouts_toml_resolves_terminal_and_fn():
    c = Config.load("config/layouts.toml")
    assert c.pick("kitty", "")[0] == "terminal"
    assert len(c.fn) == 12
