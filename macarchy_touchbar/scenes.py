"""Scenes: a module borrowing the whole bar, with a priority and a timeout."""


class Scene:
    def __init__(self, name, layout, priority=50, timeout=None, dismissable=True, on_hide=None):
        self.name, self.layout, self.priority = name, layout, priority
        self.timeout, self.dismissable, self.on_hide = timeout, dismissable, on_hide
        self.shown_at = 0.0
        self.seq = 0


class SceneStack:
    def __init__(self, now):
        self.now = now
        self.scenes = []
        self._seq = 0

    def _sort(self):
        self.scenes.sort(key=lambda s: (-s.priority, -s.seq))

    def show(self, scene):
        # Remove scene with same name without firing on_hide
        for s in list(self.scenes):
            if s.name == scene.name:
                self.scenes.remove(s)
        self._seq += 1
        scene.seq, scene.shown_at = self._seq, self.now()
        self.scenes.append(scene)
        self._sort()

    def _remove(self, scene):
        """Remove scene by identity and fire its on_hide."""
        if scene in self.scenes:
            self.scenes.remove(scene)
            if scene.on_hide:
                scene.on_hide()

    def hide(self, name):
        for s in list(self.scenes):
            if s.name == name:
                self._remove(s)

    def touch(self, name):
        for s in self.scenes:
            if s.name == name:
                s.shown_at = self.now()

    def top(self):
        return self.scenes[0] if self.scenes else None

    def deadline(self):
        ds = [s.shown_at + s.timeout for s in self.scenes if s.timeout]
        return min(ds) if ds else None

    def tick(self, now):
        before = self.top()
        for s in list(self.scenes):
            # Skip entries no longer in self.scenes (may have been removed re-entrantly)
            if s not in self.scenes:
                continue
            if s.timeout and now >= s.shown_at + s.timeout:
                self._remove(s)
        return self.top() is not before
