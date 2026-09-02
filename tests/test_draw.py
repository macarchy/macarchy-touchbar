import cairo
import pytest

import macarchy_dfr.draw as draw
from macarchy_dfr.geometry import Rect
from macarchy_dfr.draw import Painter, Theme, icon_codepoint, icon_font_available


def surface():
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 60)


def pixel(s, x, y):
    s.flush()
    d, st = s.get_data(), s.get_stride()
    b, g, r = d[y * st + x * 4: y * st + x * 4 + 3]
    return (r, g, b)


def test_codepoint_lookup():
    assert icon_codepoint("brightness_high") == ""
    with pytest.raises(KeyError):
        icon_codepoint("no_such_icon_xyz")


def test_pill_fills_inside_and_leaves_corners():
    s = surface()
    p = Painter(s)
    p.pill(cairo.Context(s), Rect(10, 8, 100, 44), Theme.PILL)
    assert pixel(s, 60, 30) == (51, 51, 51)
    assert pixel(s, 10, 8) == (0, 0, 0)          # rounded corner stays black


def test_text_is_centered_and_ellipsized():
    s = surface()
    p = Painter(s)
    w = p.text(cairo.Context(s), "12:34", Rect(0, 8, 200, 44))
    assert 40 < w < 120
    assert any(pixel(s, x, 30) != (0, 0, 0) for x in range(80, 120))
    assert all(pixel(s, x, 30) == (0, 0, 0) for x in range(0, 20))
    long = p.text(cairo.Context(s), "x" * 200, Rect(200, 8, 150, 44))
    assert long <= 150


@pytest.mark.skipif(not icon_font_available(), reason="Material Symbols Rounded not installed")
def test_icon_draws_something_white_in_the_middle():
    s = surface()
    p = Painter(s)
    p.icon(cairo.Context(s), "brightness_high", 50, 30)
    assert any(pixel(s, x, 30) != (0, 0, 0) for x in range(38, 62))


def test_missing_icon_falls_back_to_warning_and_never_raises():
    s = surface()
    Painter(s).icon(cairo.Context(s), "no_such_icon_xyz", 50, 30)


def test_icon_never_raises_when_codepoints_file_is_missing(monkeypatch):
    # Fresh checkout: fonts/*.codepoints is git-ignored and may not exist.
    monkeypatch.setattr(draw, "CODEPOINTS", "/nonexistent/MaterialSymbolsRounded.codepoints")
    monkeypatch.setattr(draw, "_codepoints", None)
    s = surface()
    Painter(s).icon(cairo.Context(s), "brightness_high", 50, 30)
    # Direct callers still get a KeyError for an unknown/unloadable name.
    with pytest.raises(KeyError):
        icon_codepoint("brightness_high")
