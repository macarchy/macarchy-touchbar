import cairo
from macarchy_dfr.bar import Bar
from macarchy_dfr.config import Config
from macarchy_dfr.draw import Painter
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import Registry, ModuleHost
from macarchy_dfr.output import HeadlessOutput
from macarchy_dfr.touch import Gesture
from macarchy_dfr.widgets import Button, Slider, Spacer, Label
from macarchy_dfr.hypr import Context

TOML = '''
[items.a]
widget = "core.button"
icon = "add"
[groups.g]
icon = "brightness_6"
items = ["core.slider"]
slide_into = "core.slider"
timeout = 2
[layouts.default]
left = ["a", "core.spacer"]
right = ["group:g", "core.clock"]
[layouts.term]
match = "kitty"
left = ["a"]
right = ["core.clock"]
'''


def make_bar(t):
    reg = Registry()
    reg.register("core", "button", Button)
    reg.register("core", "spacer", Spacer)
    reg.register("core", "slider", Slider)
    reg.register("core", "clock", lambda api, **p: Label(api, text="12:34", width=100))
    out = HeadlessOutput()
    loop = EventLoop(now=lambda: t[0])
    host = ModuleHost(loop, None, reg)
    bar = Bar(out, loop, Painter(out.surface), Config.parse(TOML), reg, host, now=lambda: t[0])
    host.hooks = bar
    bar.set_context(Context(cls="zen", title="", workspace=1, occupied=[1], fn=False, awake=True))
    return bar, out, loop


def test_context_picks_layout_and_redraw_flushes():
    t = [0.0]
    bar, out, loop = make_bar(t)
    assert len(bar.current_layout().left.widgets) == 2
    loop.step(timeout=0); assert out.flushes >= 1
    bar.set_context(Context("kitty", "", 1, [1], False, True))
    assert len(bar.current_layout().left.widgets) == 1


def test_tap_opens_group_and_close_button_closes_it():
    t = [0.0]
    bar, out, loop = make_bar(t)
    gb = bar.current_layout().right.widgets[0]
    x = gb.rect.x + 5
    bar.gesture(Gesture("press", x, 30)); assert gb.pressed
    bar.gesture(Gesture("tap", x, 30)); bar.gesture(Gesture("release", x, 30))
    assert bar.is_group_open("g") and not gb.pressed
    close = bar.current_layout().left.widgets[0]
    assert isinstance(bar.current_layout().left.widgets[1], Slider)
    cx = close.rect.x + 5
    bar.gesture(Gesture("press", cx, 30)); bar.gesture(Gesture("tap", cx, 30)); bar.gesture(Gesture("release", cx, 30))
    assert not bar.is_group_open("g")


def test_group_times_out_only_without_interaction():
    t = [0.0]
    bar, out, loop = make_bar(t)
    bar.open_group("g")
    t[0] = 1.5; bar.tick(); assert bar.is_group_open("g")
    slider = bar.current_layout().left.widgets[1]
    bar.gesture(Gesture("press", slider.rect.x + 30, 30)); bar.gesture(Gesture("release", slider.rect.x + 30, 30))
    t[0] = 3.0; bar.tick(); assert bar.is_group_open("g")       # extended by the touch
    t[0] = 5.1; bar.tick(); assert not bar.is_group_open("g")


def test_slide_into_transfers_the_drag_to_the_slider():
    t = [0.0]
    bar, out, loop = make_bar(t)
    gb = bar.current_layout().right.widgets[0]
    x = gb.rect.x + 5
    bar.gesture(Gesture("press", x, 30))
    bar.gesture(Gesture("drag", x + 20, 30))
    assert bar.is_group_open("g")
    slider = bar.current_layout().left.widgets[1]
    bar.gesture(Gesture("drag", slider.rect.x + slider.rect.w - 12, 30))
    bar.gesture(Gesture("drag_end", slider.rect.x + slider.rect.w - 12, 30))
    assert slider.value == 1.0


def test_scene_takes_the_bar_and_a_stray_tap_dismisses_it():
    t = [0.0]
    bar, out, loop = make_bar(t)
    from macarchy_dfr.layout import Layout, Row
    bar.show_scene("m", "s", lambda api: Layout(Row([Label(None, text="hello", width=200)]), Row([])),
                   priority=50, timeout=None, dismissable=True)
    assert isinstance(bar.current_layout().left.widgets[0], Label)
    bar.gesture(Gesture("press", 1500, 30)); bar.gesture(Gesture("tap", 1500, 30)); bar.gesture(Gesture("release", 1500, 30))
    assert not isinstance(bar.current_layout().left.widgets[0], Label)


def test_fn_layer_and_screenshot(tmp_path):
    t = [0.0]
    bar, out, loop = make_bar(t)
    bar.set_fn(True)
    assert bar.current_layout() is bar.fn_layout
    bar.set_fn(False)
    bar.screenshot(str(tmp_path / "s.png"))
    assert cairo.ImageSurface.create_from_png(str(tmp_path / "s.png")).get_width() == 2008
