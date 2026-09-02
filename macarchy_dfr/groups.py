"""Control Strip groups: a button that expands the left zone into its items."""
from .widgets import Button


class Group:
    def __init__(self, name, icon=None, items=(), slide_into=None, timeout=15, text=None):
        self.name, self.icon, self.text = name, icon, text
        self.items, self.slide_into, self.timeout = list(items), slide_into, float(timeout)


class GroupButton(Button):
    def __init__(self, api, group, **p):
        super().__init__(api, icon=group.icon, text=group.text, **p)
        self.group = group
        self.captures_drag = bool(group.slide_into)
        self._slid = False

    def is_active(self):
        return bool(self.api and self.api.is_group_open(self.group.name))

    def draw(self, cr, painter):
        self.active = self.is_active()
        super().draw(cr, painter)

    def on_press(self, x, y):
        self._slid = False

    def on_tap(self, x, y):
        self.api.open_group(self.group.name)

    def on_drag(self, x, y):
        if self.group.slide_into and not self._slid:
            self._slid = True
            self.api.slide_into(self.group.name, x, y)
