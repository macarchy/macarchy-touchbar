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
    assert Button(icon="add").measure() == 130
    assert Button(text="copy").measure() >= 130
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


def test_slider_draw_knob_and_rail():
    s, cr, p = canvas()
    sl = Slider(value=0.5); sl.rect = Rect(0, 8, 400, 44)
    sl.draw(cr, p)
    # Rail runs from 12 to 388 (no icons, so KNOB//2 = 12 padding)
    # With value=0.5, knob centre x = 12 + (388-12)*0.5 = 200, y = 30
    assert px(s, 200, 30) == (255, 255, 255)  # knob is white (FG)
    # Travelled portion (left of knob) at x=100 should be white (accent FG)
    assert px(s, 100, 30) == (255, 255, 255)
    # Untravelled portion (right of knob) at x=300 should be RAIL color
    rail_rgb = tuple(round(c * 255) for c in Theme.RAIL)
    assert px(s, 300, 30) == rail_rgb


def test_meter_draw_bands():
    s, cr, p = canvas()
    m = Meter(width=100, bands=4); m.set_bands([1, 1, 1, 1])
    m.rect = Rect(0, 8, 100, 44)
    m.draw(cr, p)
    # bw = (100 - 3*3) // 4 = 91 // 4 = 22
    # First band centre: x = 0 + 22//2 = 11, y = 30
    assert px(s, 11, 30) == (255, 255, 255)  # band is white (FG)

    # Now test with all bands at 0.0
    s2, cr2, p2 = canvas()
    m.set_bands([0, 0, 0, 0])
    m.draw(cr2, p2)
    # h = max(4, 0) = 4, y = 8 + (44-4)//2 = 28, so band is y=28-32
    # At y=12, we're above the band, should be black
    assert px(s2, 11, 12) == (0, 0, 0)


def test_sprite_draw_no_sheet_and_with_sheet(tmp_path):
    s, cr, p = canvas()
    sp = Sprite(frames=2); sp.rect = Rect(0, 8, 64, 44)
    sp.draw(cr, p)  # Should not raise when no sheet

    # Create a tiny 2-frame PNG: 16x8, left 8x8 red, right 8x8 blue
    sheet_path = tmp_path / "sheet.png"
    sheet_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 16, 8)
    sheet_cr = cairo.Context(sheet_surf)
    # Red frame (left)
    sheet_cr.set_source_rgb(1, 0, 0)
    sheet_cr.rectangle(0, 0, 8, 8)
    sheet_cr.fill()
    # Blue frame (right)
    sheet_cr.set_source_rgb(0, 0, 1)
    sheet_cr.rectangle(8, 0, 8, 8)
    sheet_cr.fill()
    sheet_surf.write_to_png(str(sheet_path))

    # Frame 0: red
    s1, cr1, p1 = canvas()
    sp1 = Sprite(sheet=str(sheet_path), frames=2, frame_w=8, frame_h=8)
    sp1.rect = Rect(0, 8, 64, 44)
    sp1.draw(cr1, p1)
    # Scale: 44 // 8 = 5 (integer upscale)
    # Rect centre: x = 32, y = 30
    assert px(s1, 32, 30) == (255, 0, 0)  # red

    # Frame 1: blue
    s2, cr2, p2 = canvas()
    sp1.tick()
    sp1.draw(cr2, p2)
    assert px(s2, 32, 30) == (0, 0, 255)  # blue


def test_button_icon_size_param():
    # Test that a button with icon_size=48 has more icon pixels than default
    # Draw button with custom size
    s_large, cr_large, p_large = canvas()
    b_large = Button(icon="add", icon_size=48)
    b_large.rect = Rect(10, 0, 130, 60)
    b_large.draw(cr_large, p_large)

    # Draw button with default size
    s_default, cr_default, p_default = canvas()
    b_default = Button(icon="add")
    b_default.rect = Rect(10, 0, 130, 60)
    b_default.draw(cr_default, p_default)

    # Count non-black, non-pill-grey pixels in pill area (10 to 140, 0 to 60)
    pill_grey = (51, 51, 51)
    def count_ink_pixels(surface):
        count = 0
        for y in range(0, 60):
            for x in range(10, 140):
                c = px(surface, x, y)
                if c != (0, 0, 0) and c != pill_grey:
                    count += 1
        return count

    large_pixels = count_ink_pixels(s_large)
    default_pixels = count_ink_pixels(s_default)

    # Larger icon should have more ink
    assert large_pixels > default_pixels


def test_button_with_icon_and_text_honours_tint():
    # Test that a button with icon+text and tint draws the tint color in the icon area
    s, cr, p = canvas()
    b = Button(icon="battery_full", text="66 %", tint=Theme.ACCENT_GREEN)
    b.rect = Rect(10, 0, 130, 60)
    b.draw(cr, p)

    # Check that icon area (x in 20..45, y in 15..45) has greenish pixels
    accent_green_rgb = tuple(round(c * 255) for c in Theme.ACCENT_GREEN)
    pill_grey_rgb = (51, 51, 51)
    green_pixels, pill_pixels = 0, 0
    for y in range(15, 45):
        for x in range(20, 45):
            color = px(s, x, y)
            # Count pixels that are greenish (not pill-grey, not black, not white)
            if color[1] > 150 and color[0] > 50 and color[0] < 150:  # high green, moderate red
                green_pixels += 1
            elif color == pill_grey_rgb:
                pill_pixels += 1
    assert green_pixels > 0, "Should find green-ish pixels in icon area for tinted button"

    # Test that active button with tint shows white icon, not green
    s_active, cr_active, p_active = canvas()
    b_active = Button(icon="battery_full", text="66 %", tint=Theme.ACCENT_GREEN, active=True)
    b_active.rect = Rect(10, 0, 130, 60)
    b_active.draw(cr_active, p_active)

    # Icon area should be mostly white (fill=1.0) or white-green blend, not solid green
    # Count pixels in the core icon area (where the glyph is)
    white_rgb = tuple(round(c * 255) for c in Theme.FG)
    white_pixels, green_pixels = 0, 0
    for y in range(15, 45):
        for x in range(25, 40):  # Core icon area
            color = px(s_active, x, y)
            if color[0] > 200 and color[1] > 200 and color[2] > 200:  # Very white
                white_pixels += 1
            elif color == accent_green_rgb:  # Exact green
                green_pixels += 1
    # With fill=1.0 and white tint, should have mostly white, not exact green
    assert white_pixels > green_pixels, "Active button should show white icon, not green"
