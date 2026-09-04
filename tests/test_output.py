import os
import cairo
import pytest
from macarchy_dfr.geometry import Rect
from macarchy_dfr.output import HeadlessOutput, DrmOutput, card_candidates, _find_card


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


@pytest.mark.skipif(os.environ.get("MACARCHY_DFR_HW_TESTS") != "1", reason="set MACARCHY_DFR_HW_TESTS=1 with the daemon stopped to test the real Touch Bar")
def test_drm_output_opens_and_flushes():
    out = DrmOutput.open()
    assert (out.width, out.height) == (2008, 60)
    out.blank()
    out.close()


def test_card_candidates_tries_the_stable_by_path_link_first_and_lists_every_card(tmp_path):
    dri = tmp_path / "dri"
    (dri / "by-path").mkdir(parents=True)
    for n in (0, 2, 3):
        (dri / f"card{n}").write_text("")
    (dri / "renderD128").write_text("")
    os.symlink(dri / "card2", dri / "by-path" / "platform-228200000.display-pipe-card")

    got = card_candidates(str(dri))

    assert got[0].endswith("display-pipe-card")                     # stable name, no node number
    assert [os.path.realpath(p) for p in got] == [
        str(dri / "card2"), str(dri / "card0"), str(dri / "card3")]  # card2 not visited twice


class _FakeMode:
    def __init__(self, h, v):
        self.hdisplay, self.vdisplay = h, v


class _FakeConn:
    def __init__(self, connector_id, mode, connection=1):
        self.connector_id, self.encoder_id, self.connection = connector_id, connector_id + 1, connection
        self.modes, self.count_modes = [mode], 1 if mode else 0


class _FakeLib:
    """Just enough of libdrm: one connector per card, keyed by fd."""

    def __init__(self, cards):
        self.cards = cards                                  # fd -> _FakeConn or None

    def drmModeGetResources(self, fd):
        conn = self.cards[fd]
        if conn is None:
            return None
        return _contents(_contents_obj(count_connectors=1, connectors=[conn.connector_id]))

    def drmModeGetConnector(self, fd, conn_id):
        return _contents(self.cards[fd])


def _contents_obj(**kw):
    return type("O", (), kw)()


def _contents(obj):
    return _contents_obj(contents=obj)


def test_find_card_skips_the_main_panel_and_picks_the_touch_bar():
    # The bug: card numbers move between boots. Here the Touch Bar is card2
    # and the 2560x1600 internal panel is card3 -- the old hardcoded node.
    fds = {"/dev/dri/card0": 10, "/dev/dri/card2": 11, "/dev/dri/card3": 12}
    lib = _FakeLib({10: None,                                    # render-only: no resources
                    11: _FakeConn(39, _FakeMode(60, 2008)),      # the Touch Bar
                    12: _FakeConn(47, _FakeMode(2560, 1600))})   # the internal panel
    closed = []

    fd, path, conn = _find_card(lib, list(fds), opener=fds.get, closer=closed.append)

    assert (path, fd, conn.connector_id) == ("/dev/dri/card2", 11, 39)
    assert closed == [10, 12] or closed == [10]                  # never leaks the cards it rejects


def test_find_card_says_what_it_looked_at_when_no_touch_bar_is_present():
    lib = _FakeLib({12: _FakeConn(47, _FakeMode(2560, 1600))})
    with pytest.raises(OSError) as e:
        _find_card(lib, ["/dev/dri/card3"], opener=lambda p: 12, closer=lambda fd: None)
    assert "2560x1600" in str(e.value) and "card3" in str(e.value)
