from macarchy_dfr.geometry import Rect
from macarchy_dfr.layout import distribute, Row, Layout


class W:
    def __init__(self, width=0, stretch=0):
        self._w, self.stretch, self.rect = width, stretch, None
    def measure(self):
        return self._w


def test_rect_contains_and_union():
    r = Rect(10, 8, 100, 44)
    assert r.contains(10, 8) and r.contains(109, 51) and not r.contains(110, 8)
    assert r.union(Rect(200, 0, 10, 60)) == Rect(10, 0, 200, 60)


def test_fixed_widths_are_laid_left_to_right_with_gap_and_margin():
    rects = distribute([100, 50], [0, 0], total=2008)
    assert rects[0] == Rect(8, 8, 100, 44)
    assert rects[1] == Rect(8 + 100 + 6, 8, 50, 44)


def test_elastic_widgets_share_the_remainder_by_stretch():
    rects = distribute([100, 0, 0], [0, 1, 3], total=8 + 100 + 6 + 400 + 6 + 8)
    assert rects[1].w == 100 and rects[2].w == 300


def test_overflow_never_overlaps_and_drops_from_the_end():
    rects = distribute([1000, 1000, 1000], [0, 0, 0], total=2008)
    assert rects[0].w == 1000 and rects[1].w == 1000
    assert rects[2].w == 0                      # dropped: zero width, never drawn


def test_layout_gives_right_row_its_measure_and_left_the_rest():
    left = Row([W(100), W(0, 1)])
    right = Row([W(120), W(120)])
    lay = Layout(left, right)
    lay.layout(2008)
    assert right.rects[0].x == 2008 - 8 - 120 - 6 - 120
    assert left.rects[1].right == right.rects[0].x - 6
    assert lay.hit(right.rects[1].x + 5, 30) is right.widgets[1]
    assert lay.hit(3, 30) is None
