from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def contains(self, px, py):
        return self.x <= px < self.right and self.y <= py < self.bottom

    def union(self, o):
        x, y = min(self.x, o.x), min(self.y, o.y)
        return Rect(x, y, max(self.right, o.right) - x, max(self.bottom, o.bottom) - y)
