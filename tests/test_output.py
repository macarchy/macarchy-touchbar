import os
import cairo
import pytest
from macarchy_dfr.geometry import Rect
from macarchy_dfr.output import HeadlessOutput, DrmOutput


def test_headless_surface_is_landscape_and_png_round_trips(tmp_path):
    out = HeadlessOutput()
    assert (out.width, out.height) == (2008, 60)
    cr = cairo.Context(out.surface)
    cr.set_source_rgb(1, 0, 0)
    cr.rectangle(0, 0, 10, 60)
    cr.fill()
    out.flush(Rect(0, 0, 10, 60))
    assert out.flushes == 1 and out.last_rect == Rect(0, 0, 10, 60)
    png = tmp_path / "bar.png"
    out.save_png(str(png))
    img = cairo.ImageSurface.create_from_png(str(png))
    assert (img.get_width(), img.get_height()) == (2008, 60)


def test_rotate_maps_landscape_pixel_to_portrait_row():
    # (x, y) in the 2008x60 scene lands at column (H-1-y)?? no: at row x, column y
    # after a +90° rotation with translate(W,0): scene (x, y) -> buffer (W-1-y, x)
    out = HeadlessOutput()
    cr = cairo.Context(out.surface)
    cr.set_source_rgb(1, 1, 1)
    cr.rectangle(100, 5, 1, 1)
    cr.fill()
    portrait = out.rotated()            # 64 x 2008 ARGB32 surface, same helper DrmOutput uses
    data, stride = portrait.get_data(), portrait.get_stride()
    px = lambda col, row: data[row * stride + col * 4: row * stride + col * 4 + 3]
    assert px(60 - 1 - 5, 100) == b"\xff\xff\xff"


@pytest.mark.skipif(not os.access("/dev/dri/card3", os.W_OK), reason="needs the Touch Bar and DRM master")
def test_drm_output_opens_and_flushes():
    out = DrmOutput.open()
    assert (out.width, out.height) == (2008, 60)
    out.blank()
    out.close()
