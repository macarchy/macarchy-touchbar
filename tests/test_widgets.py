import cairo
from macarchy_dfr.geometry import Rect
from macarchy_dfr.draw import Painter, Theme
from macarchy_dfr.widgets import Widget, Button, Label, Spacer, Image


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
    assert px(s, 20, 12) != (51, 51, 51)


def test_label_set_text_invalidates_only_on_change():
    api = FakeApi()
    lab = Label(api, text="a")
    lab.set_text("a"); lab.set_text("b")
    assert api.invalidated == [lab]


def test_spacer_and_image_defaults():
    assert Spacer().stretch == 1 and Spacer().measure() == 0
    assert Spacer(width=20).stretch == 0 and Spacer(width=20).measure() == 20
    assert Image().measure() == 44
