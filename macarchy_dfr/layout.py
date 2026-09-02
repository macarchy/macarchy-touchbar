"""Horizontal distribution of widgets along the 2008 px bar.

Fixed widgets get what they measured; elastic ones (stretch > 0) share what is
left by weight. Nothing ever overlaps: when fixed widths alone overflow, the
trailing widgets get zero width and are not drawn.
"""
from .geometry import Rect

GAP, MARGIN, PILL_Y, PILL_H = 6, 8, 2, 56


def distribute(widths, stretches, total, gap=GAP, margin=MARGIN, y=PILL_Y, h=PILL_H):
    n = len(widths)
    if n == 0:
        return []
    avail = total - 2 * margin - gap * (n - 1)
    fixed = sum(w for w, s in zip(widths, stretches) if s == 0)
    weight = sum(s for s in stretches if s > 0)
    spare = max(0, avail - fixed)
    out, x, budget = [], margin, avail
    for w, s in zip(widths, stretches):
        want = w if s == 0 else (spare * s) // weight
        got = want if (s == 0 and want <= budget) else (min(want, budget) if s > 0 else 0)
        out.append(Rect(x, y, got, h))
        x += got + (gap if got else 0)
        budget -= got
    return out


class Row:
    def __init__(self, widgets):
        self.widgets = list(widgets)
        self.rects = []
        self.x0 = 0

    def fixed_width(self):
        ws = [w.measure() for w in self.widgets if w.stretch == 0]
        return sum(ws) + GAP * max(0, len(self.widgets) - 1) + 2 * MARGIN

    def layout(self, x0, width):
        self.x0 = x0
        rects = distribute([w.measure() for w in self.widgets],
                           [w.stretch for w in self.widgets], width)
        self.rects = [Rect(r.x + x0, r.y, r.w, r.h) for r in rects]
        for w, r in zip(self.widgets, self.rects):
            w.rect = r

    def hit(self, x, y):
        for w, r in zip(self.widgets, self.rects):
            if r.w and r.contains(x, y):
                return w
        return None


class Layout:
    def __init__(self, left, right):
        self.left, self.right = left, right

    @property
    def rows(self):
        return (self.left, self.right)

    def layout(self, width):
        rw = min(self.right.fixed_width(), width) if self.right.widgets else 0
        self.right.layout(width - rw, rw)
        # the two rows share one gap, not two margins, where they meet
        self.left.layout(0, width - rw + (2 * MARGIN - GAP if rw else 0))

    def hit(self, x, y):
        return self.left.hit(x, y) or self.right.hit(x, y)

    def widgets(self):
        return self.left.widgets + self.right.widgets
