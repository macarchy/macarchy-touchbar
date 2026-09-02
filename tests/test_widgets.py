import cairo
from macarchy_dfr.geometry import Rect
from macarchy_dfr.draw import Painter, Theme
from macarchy_dfr.widgets import Widget, Button, Label, Spacer, Image, Slider, Meter, Sprite


class FakeApi:
    def __init__(self):
        self.calls, self.invalidated = [], []
    def run_detached(self, cmd): self.calls.append(("run", cmd))
    def keys(self, names): self.calls.append(("keys", list(names)))
    def open_group(self, name): self.calls.append(("group", name))
    def close_group(self): self.calls.append(("close",))
    def invalidate(self, w=None): self.invalidated.append(w)
    def measure_text(self, s, size=Theme.TEXT_PT):
        # Simple approximation: ~7 pixels per character at size 22
        return len(s) * size // 3


def canvas():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 60)
    return s, cairo.Context(s), Painter(s)


def px(s, x, y):
    s.flush(); d, st = s.get_data(), s.get_stride()
    b, g, r = d[y * st + x * 4: y * st + x * 4 + 3]
    return (r, g, b)


def test_button_measures_by_content():
    assert Button(icon="add").measure() == 64
    assert Button(text="copy").measure() >= 64
    assert Button(icon="add", width=120).measure() == 120


def test_button_tap_routes_run_keys_group_close():
    api = FakeApi()
    Button(api, run="omarchy menu").on_tap(0, 0)
    Button(api, keys=["LeftCtrl", "T"]).on_tap(0, 0)
    Button(api, group="media").on_tap(0, 0)
    Button(api, close=True).on_tap(0, 0)
    assert api.calls == [("run", "omarchy menu"), ("keys", ["LeftCtrl", "T"]), ("group", "media"), ("close",)]


def test_button_draws_pill_pressed_and_active():
    s, cr, p = canvas()
    b = Button(icon="add"); b.rect = Rect(10, 8, 64, 44)
    b.draw(cr, p)
    assert px(s, 20, 12) == (51, 51, 51)
    b.pressed = True; b.draw(cr, p)
    assert px(s, 20, 12) == (102, 102, 102)
    b.pressed = False; b.active = True; b.draw(cr, p)
    accent_blue_rgb = tuple(round(c * 255) for c in Theme.ACCENT_BLUE)
    assert px(s, 20, 12) == accent_blue_rgb


def test_button_on_tap_takes_priority():
    api = FakeApi()
    cb_called = []
    def cb():
        cb_called.append(True)
    b = Button(api, on_tap=cb, run="x", keys=["A"], group="g", close=True)
    b.on_tap(0, 0)
    assert cb_called == [True]
    assert api.calls == []


def test_button_badge_rendering():
    accent_red_rgb = tuple(round(c * 255) for c in Theme.ACCENT_RED)

    # Test badge=True (point badge)
    s, cr, p = canvas()
    b = Button(icon="add", badge=True)
    b.rect = Rect(10, 8, 64, 44)
    b.draw(cr, p)
    badge_cx, badge_cy = b.rect.right - 10, b.rect.y + 10
    center_pixel = px(s, badge_cx, badge_cy)
    # Center pixel should be red (allow ±1 rounding tolerance on blue channel)
    assert center_pixel[0] == accent_red_rgb[0] and center_pixel[1] == accent_red_rgb[1] and abs(center_pixel[2] - accent_red_rgb[2]) <= 1

    # Test badge=3 (count badge)
    s2, cr2, p2 = canvas()
    b2 = Button(icon="add", badge=3)
    b2.rect = Rect(10, 8, 64, 44)
    b2.draw(cr2, p2)
    badge_cx, badge_cy = b2.rect.right - 10, b2.rect.y + 10
    center_pixel = px(s2, badge_cx, badge_cy)
    # Center pixel should not be pure red anymore (digit covers it)
    # Allow ±1 tolerance
    assert not (center_pixel[0] == accent_red_rgb[0] and center_pixel[1] == accent_red_rgb[1] and abs(center_pixel[2] - accent_red_rgb[2]) <= 1)
    # Pixel 8px to the left should still be red (outside digit area)
    left_pixel = px(s2, badge_cx - 8, badge_cy)
    assert left_pixel[0] == accent_red_rgb[0] and left_pixel[1] == accent_red_rgb[1] and abs(left_pixel[2] - accent_red_rgb[2]) <= 1


def test_label_set_text_invalidates_only_on_change():
    api = FakeApi()
    lab = Label(api, text="a")
    lab.set_text("a"); lab.set_text("b")
    assert api.invalidated == [lab]


def test_spacer_and_image_defaults():
    assert Spacer().stretch == 1 and Spacer().measure() == 0
    assert Spacer(width=20).stretch == 0 and Spacer(width=20).measure() == 20
    assert Image().measure() == 44


def test_slider_maps_x_to_value_and_reports_end():
    seen = []
    s = Slider(on_change=seen.append); s.rect = Rect(100, 8, 300, 44)   # rail 100..400
    s.on_press(100, 30)
    assert s.value == 0.0
    s.on_drag(250, 30)
    assert abs(s.value - 0.5) < 0.01
    s.on_drag_end(400, 30)
    assert s.value == 1.0 and seen[-1] == 1.0 and len(seen) >= 2


def test_slider_with_icons_reserves_end_zones():
    s = Slider(min_icon="brightness_low", max_icon="brightness_high")
    s.rect = Rect(0, 8, 400, 44)                       # active rail 40..360
    s.on_tap(40, 30);  assert s.value == 0.0
    s.on_tap(360, 30); assert s.value == 1.0
    s.on_tap(0, 30);   assert s.value == 0.0           # clamped, no exception


def test_slider_throttles_drag_callbacks():
    t = [0.0]
    class Api(FakeApi):
        def now(self): return t[0]
        def measure_text(self, s, size=22): return 10
    seen = []
    s = Slider(Api(), on_change=seen.append); s.rect = Rect(0, 8, 400, 44)
    s.on_press(0, 30)
    for i in range(10):
        t[0] = i * 0.01                                # 10 moves in 0.1 s
        s.on_drag(10 * i, 30)
    assert len(seen) <= 3


def test_meter_bands_and_sprite_frames():
    m = Meter(bands=4); m.set_bands([0, 0.5, 1, 0.2])
    assert m.bands == [0, 0.5, 1, 0.2]
    sp = Sprite(frames=3, fps=4)
    assert sp.frame == 0
    sp.tick(); sp.tick(); sp.tick()
    assert sp.frame == 0                               # wraps
