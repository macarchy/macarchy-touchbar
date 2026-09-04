"""media: what is playing, its cover, and the output volume.

Three decisions a later reader would otherwise re-litigate:

(a) Now Playing is read from `omarchy-shell media status`, not from a second
    MPRIS client of our own. The Omarchy shell already runs one and already
    picks the active player; playerctl is not installed on this aarch64 box,
    and reading the shell's choice is what stops the bar and the on-screen
    OSD ever naming different players.
(b) Metadata is PUSHED, not polled. Now Playing sits on the default bar, so
    it has to be right the instant a track changes, and a poll would be
    either late or a fork a second. `busctl --user --json=short monitor`
    prints exactly ONE JSON line per signal, which is why it is used here
    rather than the dbus-monitor of modules/notifications/touchbar.py: the
    same long-lived-line-stream + respawn shape, minus the state machine
    that dbus-monitor's multi-line text needs.
(c) The volume level is POLLED, because the slider only exists on the bar
    while the media group is open -- see poll_volume's own guard.
"""
import json
import os
import re
import urllib.parse
import weakref

from gi.repository import GLib

from macarchy_dfr.widgets import Button, Image, Label, Slider

# Both matches on one invocation: the property churn of whatever is playing,
# and players appearing/disappearing (a fresh mpv emits nothing until it does).
MONITOR = [
    "busctl", "--user", "--json=short", "monitor",
    "--match=type='signal',interface='org.freedesktop.DBus.Properties',"
    "member='PropertiesChanged',path='/org/mpris/MediaPlayer2'",
    "--match=type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
    "member='NameOwnerChanged',arg0namespace='org.mpris.MediaPlayer2'",
]
# No -q here. -q is omarchy-shell's quiet best-effort mode and it SUPPRESSES
# stdout (`if (( !QUIET )) && [[ -n $output ]]; then echo`), so `omarchy-shell
# -q media status` answers an empty string with rc 0 forever. -q is right only
# for the fire-and-forget action calls below.
STATUS = ["omarchy-shell", "media", "status"]
_RE_PCT = re.compile(r"(\d+)%")


def fingerprint(line):
    """What in this signal could change the bar, or None if the line is unreadable.

    Measured against a real mpv on 2026-09-04: on a playing track it re-emits
    Metadata once a second with only mpris:length growing. Without this
    filter every one of those costs an omarchy-shell fork -- about 3600 an
    hour of playback. None means "unreadable, assume something moved".
    """
    try:
        msg = json.loads(line)
        data = msg["payload"]["data"]
        if msg["member"] == "NameOwnerChanged":
            return ("owner", data[0], bool(data[2]))
        props = dict(data[1])
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    meta = props.get("Metadata")
    if isinstance(meta, dict) and isinstance(meta.get("data"), dict):
        props["Metadata"] = dict(meta, data={k: v for k, v in meta["data"].items() if k != "mpris:length"})
    props.pop("Position", None)
    return (msg["sender"], json.dumps(props, sort_keys=True))


def local_art(url):
    """The path behind a file:// cover that exists, else None.

    Spotify and Firefox publish https covers; fetching one would put the
    network -- plus a cache directory, a timeout and an eviction policy -- on
    the render path for a 56 px sleeve. api.app_icon_path is the answer for
    those.
    """
    if not url or not url.startswith("file://"):
        return None
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    return path if os.path.exists(path) else None


class Module:
    def setup(self, api):
        self.api = api
        self.widgets = weakref.WeakSet()
        self.state = {}
        self.sink = None
        self._stopped = self._pending = False
        self._last_sig = None
        self._awake = True
        self._want = None
        self._busy = False
        api.widget("now", self.now_playing)
        api.widget("art", self.art)
        api.widget("playpause", self.playpause)
        api.widget("volume", self.volume)
        api.ipc("status", self.ipc_status)
        api.on_context(self.on_ctx)
        api.every(2, self.poll_volume)
        # Nothing spawns synchronously: tests/test_daemon.py loads every
        # internal module against the shipped config on a runner with no
        # busctl and asserts `not host.broken`.
        api.after(0, self.start)
        api.after(0, self.refresh)

    def teardown(self):
        self._stopped = True        # Api._teardown already kills children and timers

    # --- widget factories ----------------------------------------------------
    def now_playing(self, api, **p):
        # Label, not Button: Button.measure() caches _text_w and never clears
        # it when .text changes (macarchy_dfr/widgets.py), and this text
        # changes per track. Label.set_text invalidates on a real change only.
        p.setdefault("stretch", 1)
        p.setdefault("align", "left")
        w = Label(api, markup=True, _kind="now", **p)
        self.widgets.add(w)
        api.after(0, self.apply)
        return w

    def art(self, api, **p):
        # width 0 until a track has a cover: Image with path=None draws a bare
        # grey pill, while a zero-width widget is genuinely gone (distribute()
        # hands it a 0-wide rect, Row.hit and Bar.redraw skip rect.w == 0, and
        # it eats no gap).
        w = Image(api, width=0, _kind="art", **p)
        self.widgets.add(w)
        api.after(0, self.apply)
        return w

    def playpause(self, api, **p):
        # XF86AudioPlay is already bound to `omarchy-shell media playPause` in
        # /usr/share/omarchy/default/hypr/bindings/media.lua, so this is the
        # same action one hop shorter; it is a module widget only because the
        # icon has to show play/pause state. -q IS right here: fire-and-forget.
        w = Button(api, icon="play_arrow", icon_size=46, _kind="playpause",
                   on_tap=lambda: api.run_detached(["omarchy-shell", "-q", "media", "playPause"]), **p)
        self.widgets.add(w)
        api.after(0, self.apply)
        return w

    def volume(self, api, **p):
        w = Slider(api, min_icon="volume_down", max_icon="volume_up", _kind="volume",
                   on_change=self.set_volume, **p)
        self.widgets.add(w)
        # A factory only runs when Bar.reload_config or Bar.open_group rebuilds
        # the row, so this call IS the group-opened event: the fresh slider
        # knows nothing yet and the 2 s timer would leave it at 0 until then.
        api.after(0, self.poll_volume)
        return w

    # --- the doorbell --------------------------------------------------------
    def start(self):
        if self._stopped:
            return

        def on_done(rc, out):
            if self._stopped:
                return                      # torn down: never respawn busctl
            if rc == -1:
                self.api.log("busctl could not be started")
                return                      # no busctl (CI): give up quietly
            self.api.after(5, self.start)
        self.api.run(MONITOR, on_line=self.on_line, on_done=on_done)

    def on_line(self, line):
        sig = fingerprint(line)
        if sig is not None and sig == self._last_sig:
            return                          # mpv's 1 Hz mpris:length re-emit
        self._last_sig = sig
        if self._pending:
            return                          # one refresh serves a whole burst
        self._pending = True
        self.api.after(0.15, self.refresh)

    def refresh(self):
        self._pending = False
        if not self._awake:
            return
        self.api.run(STATUS, on_done=self._on_status)

    def _on_status(self, rc, out):
        # The shell restarts often and its IpcHandler is not a documented API:
        # a bad answer must blank the label, not break the bar.
        try:
            self.state = json.loads(out) if (rc == 0 and out.strip()) else {}
        except ValueError:
            self.state = {}
        self.apply()

    def on_ctx(self, ctx):
        # Context.awake goes False when the backlight turns the bar off after
        # 300 s without a touch (macarchy_dfr/backlight.py), so a track playing
        # all evening on a dark bar costs nothing.
        if ctx.awake and not self._awake:
            self.refresh()
        self._awake = ctx.awake

    def apply(self):
        st = self.state
        title = GLib.markup_escape_text(st.get("title") or "")
        artist = GLib.markup_escape_text(st.get("artist") or "")
        text = ""
        if title:
            text = f"<b>{title}</b>" + (f"  <span foreground='#999999'>{artist}</span>" if artist else "")
        path = local_art(st.get("artUrl"))
        if not path and title:
            path = self.api.app_icon_path(st.get("desktopEntry") or st.get("identity") or "", 48)
        icon = "pause" if st.get("playing") else "play_arrow"
        relayout = False
        for w in list(self.widgets):
            kind = w.params.get("_kind")
            if kind == "now":
                w.set_text(text)
            elif kind == "art":
                width = 56 if path else 0
                if w.width != width:
                    w.width = width
                    relayout = True
                w.set_path(path)
            elif kind == "playpause" and w.icon != icon:
                w.icon = icon
                w.invalidate()
        if relayout:
            # No argument on purpose: a widget whose measure() changed moves
            # its neighbours, and Bar.redraw relayouts everything but repaints
            # only the dirty rect -- a widget-scoped invalidate would leave the
            # neighbours drawn at their old x.
            self.api.invalidate()

    # --- volume --------------------------------------------------------------
    def poll_volume(self):
        if not any(w.params.get("_kind") == "volume" for w in list(self.widgets)):
            return          # group shut, row freed, weakset pruned: one iteration all day
        # The default sink here is audio_effect.j493-convolver, a DSP filter
        # chain; omarchy-audio-output-sink follows it down to the physical sink
        # and is what omarchy-audio-output-volume itself calls, so the slider
        # and the XF86Audio keys always move the same level. Re-resolving every
        # poll rather than caching once is deliberate: the answer changes when
        # playback starts or stops or headphones are plugged, and this only
        # runs while the group is open.
        self.api.run(["omarchy-audio-output-sink"], on_done=self._on_sink)

    def _on_sink(self, rc, out):
        name = out.strip().split("\n")[0] if rc == 0 else ""
        if name:
            self.sink = name
            # slide_into puts a finger on the slider the instant the group
            # opens, which can be before this first answer: without the flush
            # a drag that ended already would be dropped, _want and all.
            self._flush()
        if self.sink:
            self.api.run(["pactl", "get-sink-volume", self.sink], on_done=self._on_volume)

    def _on_volume(self, rc, out):
        # "Volume: front-left: 39976 /  61% / -12.88 dB,   front-right: …" -> 61
        m = _RE_PCT.search((out or "").split("\n", 1)[0])
        if not m:
            return
        v = int(m.group(1)) / 100
        for w in list(self.widgets):
            if w.params.get("_kind") == "volume" and not w.pressed:
                w.set_value(v)      # display's guard: a poll never fights a finger mid-drag

    def set_volume(self, v):
        self._want = v
        self._flush()

    def _flush(self):
        # Slider._emit lets a value through every 33 ms, so a write per emit
        # would put ~30 pactls a second in flight during one drag and they can
        # land out of order, leaving the level wrong at drag-end. This is the
        # loop-side twin of display's BrightnessWriter, without a thread
        # because pactl is milliseconds rather than the panel's 44 ms.
        # Unlike omarchy-audio-output-volume it does not unmute first: dragging
        # a muted sink moves an inaudible level, and a second fork per step is
        # the reason it does not.
        if self._busy or self._want is None or not self.sink:
            return
        v, self._want, self._busy = self._want, None, True

        def done(rc, out):
            self._busy = False
            self._flush()
        self.api.run(["pactl", "set-sink-volume", self.sink, f"{round(v * 100)}%"], on_done=done)

    # --- eyeless verification: `macarchy-dfr media status` -------------------
    def ipc_status(self, *_a):
        st = self.state
        if not st.get("hasPlayer"):
            return "no player"
        pct = "—"
        for w in list(self.widgets):
            if w.params.get("_kind") == "volume":
                pct = f"{round(w.value * 100)} %"
                break
        return (f"{st.get('identity') or '?'} · {'Playing' if st.get('playing') else 'Paused'} · "
                f"{st.get('title') or '—'} — {st.get('artist') or '—'} · vol {pct} · sink {self.sink or '—'}")
