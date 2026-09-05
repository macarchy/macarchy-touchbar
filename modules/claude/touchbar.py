"""claude: how full the Claude Code context window is.

Each running status line (macarchy-core's `claude-statusline.sh`) drops its
context percentage in `$XDG_RUNTIME_DIR/macarchy-claude/<session id>` on every
render. This reads them back, so the sessions you are *not* looking at still
tell you when they are about to compact.
"""
import glob
import os
import time
import weakref

from macarchy_touchbar.widgets import Button

# A live status line rewrites its file on every render, so anything older than
# this belongs to a session that has exited. tmpfs clears the rest at logout.
FRESH = 90


class Module:
    DIR = None  # tests point this somewhere writable

    def setup(self, api):
        self.api = api
        self.widgets = weakref.WeakSet()
        api.widget("context", self.context)
        api.every(5, self.refresh)

    def dir(self):
        if self.DIR:
            return self.DIR
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        return os.path.join(runtime, "macarchy-claude") if runtime else None

    def state(self):
        """(fullest session's percentage, live session count), sweeping the dead."""
        d = self.dir()
        if not d:
            return None, 0
        now, live = time.time(), []
        for path in glob.glob(os.path.join(d, "*")):
            try:
                if now - os.path.getmtime(path) > FRESH:
                    os.unlink(path)
                    continue
                with open(path) as f:
                    live.append(int(f.read().strip()))
            except (OSError, ValueError):
                continue
        return (max(live) if live else None), len(live)

    def refresh(self):
        pct, count = self.state()
        theme = self.api.theme
        if pct is None:
            text = tint = badge = None
        else:
            text = f"{pct} %"
            if pct >= 85:
                tint = theme.ACCENT_RED
            elif pct >= 60:
                tint = theme.ACCENT_ORANGE
            else:
                tint = theme.ACCENT_GREEN
            # Only worth saying how many when it is more than the one in front of you.
            badge = str(count) if count > 1 else None
        for w in list(self.widgets):
            if (w.text, w.tint, w.badge) != (text, tint, badge):
                w.text, w.tint, w.badge = text, tint, badge
                w.invalidate()

    def context(self, api, **p):
        w = Button(api, icon="data_usage", **p)
        self.widgets.add(w)
        self.refresh()
        return w
