# macarchy-touchbar

![macarchy-touchbar driving the Touch Bar: the default layout, the terminal layout, and the media, display and system groups opening in place](docs/media/touchbar.gif)

<sub>Every frame above is the daemon's own output — `daemon --headless`, `screenshot out.png`, `touch x,y`, stitched with ffmpeg. In order: `[layouts.default]`, the same bar with a terminal focused (`copy / paste / clear`), then the media, display and system groups expanding into the left zone. The frames are not one chronological run — the default-layout frame was captured separately, with no Hyprland, which is why its clock reads a minute later than the rest.</sub>

A Python daemon that owns the MacBook Touch Bar on Linux, drawing every pixel itself instead of leaning on tiny-dfr's built-in function-key strip. It reads Hyprland's focused window to switch layouts, and modules (built in or dropped in as Omarchy shell plugins) supply the widgets, groups and scenes that fill them.

## Coming from tiny-dfr

[tiny-dfr](https://github.com/AsahiLinux/tiny-dfr) is the reason this hardware works at
all on Linux, and everything here stands on the ground it broke. macarchy-touchbar does not
replace it upstream — it takes the panel over on one machine, and `install.sh` masks
tiny-dfr so the two never fight over the display.

If you have been carrying a patched tiny-dfr fork around because you wanted one more
button on the bar, this section is for you.

### What you get

- **The bar is composed, not configured.** The daemon opens the Touch Bar's DRM card,
  drives its own 64-px-wide dumb buffer and draws every pixel with cairo: pills,
  Material Symbols glyphs, app icons, sliders, meters, animated sprites. A widget is a
  Python object with `measure()`, `draw()` and gesture handlers — not an entry in a
  fixed vocabulary.
- **The row follows the focused window.** A `[layouts.<name>]` table takes a `match`
  regex tried against the focused window's class and title, read live off Hyprland's
  event socket. A terminal gets `copy / paste / clear`, a browser gets `back / forward
  / reload / new tab / close tab`, anything else falls through to `[layouts.default]`.
- **Groups, scenes and a module API.** A `[groups.*]` table folds a pile of buttons
  behind one pill that expands in place (and can be slid into with a single drag). A
  scene takes the whole bar for a few seconds — an incoming notification, a battery
  readout. A module is a directory with a `manifest.json` and a `touchbar.py` that
  registers widgets, scenes, timers, subprocesses and its own CLI verbs.
- **It can be driven and screenshotted with no hardware at all.** `daemon --headless`
  runs the whole engine against an in-memory surface, `screenshot` dumps that to a PNG,
  and `touch x,y` injects a synthetic gesture. The animation at the top of this page was
  made that way, on a laptop whose real Touch Bar was busy being used.

### What you give up

Worth being clear-eyed about before you mask tiny-dfr:

- **It is Python, not Rust.** The runtime is `python-cairo` + `python-gobject`, and
  every redraw and every touch goes through the interpreter. It is a daemon drawing a
  2008×60 strip at up to 30 fps, not a hot loop — but it is not a small static binary
  either.
- **Per-app layouts need Hyprland.** The focused-window lookup speaks Hyprland's IPC
  socket and nothing else. Without it the daemon still runs: it logs `no Hyprland (…);
  static default layout` and comes up on `[layouts.default]`, with modules, groups,
  scenes, sliders, touch, the CLI, and the Fn layer (read straight from evdev, not from
  the compositor) all working. What you lose is exactly the `match` regexes, the
  `core.app` widget, and the night-light button's *state* — the `display` module polls
  `hyprctl hyprsunset temperature` to know whether to light up, though its tap action is
  a plain shell command. The coupling is confined: Hyprland lives in one module
  (`macarchy_touchbar/hypr.py`, used only by `daemon.py`) plus a single `hyprctl` call in
  `modules/display/touchbar.py`. `install.sh` has a Hyprland migration step too, and it
  skips itself with a printed note when you have no `~/.config/hypr`.
- **It masks tiny-dfr.** Only one process can drive that CRTC, so `install.sh` runs
  `systemctl disable --now tiny-dfr` then `systemctl mask tiny-dfr`. The daemon's own
  message for a failed `drmModeSetCrtc` says as much: `SetCrtc failed (is tiny-dfr still
  running?)`.
- **The shipped layout is wired for Omarchy.** Most buttons in `config/layouts.toml`
  shell out to `omarchy …`, `macarchy-als` or `macarchy-battery-limit`. They are only
  `run = "…"` strings and the engine does not care what you point them at — but out of
  the box on a non-Omarchy system, several of them will do nothing.
- **It is very new, and it has exactly one test machine.** The first commit in this
  repository is dated 2026-09-02. Everything has been calibrated against a single
  MacBook Pro (13-inch, M2, 2022) running Asahi Linux — the buffer stride, the pill
  geometry, the `MTP keyboard` name the Fn watcher looks for. tiny-dfr has years of
  other people's hardware behind it; this has days and one laptop.
- **It runs in your session, not as root.** `install.sh` adds you to `video` for the
  DRM card and installs a udev rule for `/dev/uinput`, then runs the daemon as a systemd
  *user* unit. That is a different trust model from a root system service — arguably
  better, certainly different.

### Trying it is reversible

This is the part worth knowing before anything else:

```
./install.sh --uninstall
```

stops and disables the user service, removes it and the `macarchy-touchbar` symlink, then
`systemctl unmask tiny-dfr` and `systemctl enable --now tiny-dfr`. One command and you
are back on tiny-dfr. Your `~/.config/macarchy-touchbar/layouts.toml` is left alone, so
re-running `./install.sh` picks up exactly where you left off.

What `--uninstall` does *not* undo: the udev rule in `/etc/udev/rules.d/`,
`/etc/modules-load.d/macarchy-touchbar.conf`, your membership in the `video` group, and the
Hyprland autostart line — all harmless to leave behind, all one `rm` away.

### The thing you forked tiny-dfr for: one more button

**A button that runs a command** is one table in `~/.config/macarchy-touchbar/layouts.toml`
plus its name in a layout. Save the file; the daemon notices within a second.

```toml
[items.notes]
widget = "core.button"
icon = "edit_note"                  # any Material Symbols name
run  = "kitty -e nvim ~/notes.md"

[layouts.default]
left  = ["menu", "notes", "core.spacer"]
right = ["group:system", "core.clock", "system.battery"]
```

`core.button` also takes `text`, `keys = ["LeftCtrl", "T"]` (evdev names without the
`KEY_` prefix, sent through uinput), `icon_size`, `width`, `stretch`, `tint`, `badge`
and `active`.

**A button that runs your own code** needs a module: a directory with two files. Put it
in `modules/`, or ship it as an Omarchy shell plugin under `~/.config/omarchy/plugins/`
— where it additionally has to declare `"kinds": ["touchbar-module"]` and be enabled in
`shell.json`.

`modules/hello/manifest.json`

```json
{ "schemaVersion": 1, "id": "hello", "name": "Hello", "kinds": ["touchbar-module"],
  "entryPoints": { "touchbarModule": "touchbar.py" }, "touchbarModule": { "apiVersion": 1, "order": 50 } }
```

`modules/hello/touchbar.py`

```python
from macarchy_touchbar.widgets import Button


class Module:
    def setup(self, api):
        api.widget("hi", lambda api, **p: Button(
            api, icon="mood", text="hi", on_tap=lambda: api.log("tapped"), **p))
```

Then `macarchy-touchbar reload`, and `"hello.hi"` becomes a reference any layout or group can
name — directly in a `left`/`right` list, or through an `[items.*]` table that passes it
parameters:

```toml
[layouts.default]
left = ["hello.hi", "core.spacer"]
```

That is the entire contract for a button. Everything else grows off the same `api`
object — timers, file watches, subprocesses, full-bar scenes, IPC verbs, the
focused-window context — and [Writing a module](#writing-a-module) below lists all of
it.

## Install

```
./install.sh
```

This installs the system packages the daemon needs (`python-cairo`, `python-gobject`, `papirus-icon-theme`, `brightnessctl`), downloads the Material Symbols Rounded font it draws icons with, grants hardware access without root (adds you to the `video` group for the Touch Bar's DRM card, installs a udev rule for `/dev/uinput`), disables and masks `tiny-dfr` so it stops fighting over the display, migrates the Hyprland config off any earlier release of this daemon (removes the Touch Bar binding block it used to write into `~/.config/hypr/bindings.lua` and points `~/.config/hypr/autostart.lua` at the `macarchy-touchbar.service` user unit instead of launching the daemon directly, printing what it changed and reloading Hyprland — a no-op once done, and skipped entirely if you have no `~/.config/hypr`), symlinks the `macarchy-touchbar` CLI into `~/.local/bin`, copies `config/layouts.toml` to `~/.config/macarchy-touchbar/layouts.toml` (only if that file doesn't already exist — your edits are never overwritten), and installs + enables the `macarchy-touchbar.service` systemd user unit. Re-run it any time to update.

```
./install.sh --uninstall
```

Stops and removes the service and CLI symlink, then unmasks and re-enables `tiny-dfr`. Your `layouts.toml` is left in place.

## layouts.toml

`~/.config/macarchy-touchbar/layouts.toml` is watched by the daemon and reloaded within a second of being saved. It has three kinds of table:

- **`[items.<name>]`** — one bar entry: a `widget` (either a built-in like `core.button` or a `"<module>.<widget>"` reference) plus that widget's parameters (`icon`, `run`, etc). `fallback = "<item>"` names another item to draw instead when this one's widget module isn't loaded (an optional plugin).
- **`[groups.<name>]`** — a named group of items that opens into its own row when tapped, with its own `icon` and ordered `items` list.
- **`[layouts.<name>]`** — a full bar: `left` and `right` lists of references (an item name, a `"<module>.<widget>"`, or `"group:<name>"`), and an optional `match` regex against the focused window's class that selects this layout automatically; `layouts.default` is used when nothing else matches.

```toml
[items.screenshot]
widget = "system.screenshot"

[groups.system]
icon = "settings"
items = ["screenshot", "clipboard", "system.lock"]

[layouts.default]
left  = ["menu", "core.spacer"]
right = ["group:system", "core.clock"]
```

## claude.context — the agent you are not watching

`claude.context` is a readout of how full the Claude Code context window is.
macarchy-core's status line drops each session's percentage in
`$XDG_RUNTIME_DIR/macarchy-claude/<session id>` as it renders; the module reads
them back every five seconds, shows the *fullest* one and sweeps the files of
sessions that have exited. Green under 60 %, orange, then red at 85 %, where a
compaction is close. Running several sessions at once, the pill carries a badge
with how many are alive — the number that matters when three agents are working
in branches you cannot see.

```toml
[items.claude]
widget = "claude.context"

[layouts.default]
right = ["claude", "core.clock"]
```

With no status line running the pill stays a plain icon, so it costs nothing to
leave in the layout.

## Writing a module

A module lives in its own directory with a `manifest.json`:

```json
{ "schemaVersion": 1, "id": "example", "name": "Example",
  "kinds": ["touchbar-module"],
  "entryPoints": { "touchbarModule": "touchbar.py" },
  "touchbarModule": { "apiVersion": 1, "order": 50 } }
```

`touchbar.py` exports a `Module` class with a `setup` method that receives an `api` object:

```python
from macarchy_touchbar.widgets import Button


class Module:
    def setup(self, api):
        def factory(api=None, **p):
            return Button(api, text="Hi", icon="mood", run="notify-send hi", **p)

        api.widget("hello", factory)
        api.ipc("ping", lambda *a: "pong")
        api.log("hello module ready")
```

Built-in modules live under `modules/`; drop-in ones are discovered the same way Omarchy shell plugins are, from `~/.config/omarchy/plugins`, and must be enabled in `shell.json` to load. For a reference external module, see [`~/Work/jarvis/plugin/touchbar.py`](https://github.com/macarchy/jarvis/blob/main/plugin/touchbar.py) (github.com/macarchy/jarvis): a `Sprite` in a pill, a scene, and six IPC verbs.

`api` calls:

| call | what it does |
| --- | --- |
| `widget(name, factory)` | register a widget factory as `"<module>.<name>"` |
| `scene(name, factory)` | register a full-screen scene |
| `show_scene(name, priority=50, timeout=None, dismissable=True)` | display a registered scene |
| `hide_scene(name)` | dismiss it |
| `every(seconds, fn)` | repeating timer |
| `after(seconds, fn)` | one-shot timer |
| `watch_file(path, fn)` | call `fn` when a file's mtime changes (polled once a second) |
| `watch_fd(fd, fn)` | call `fn` when a file descriptor is readable |
| `run(argv, on_done=None, on_line=None)` | run a subprocess under the event loop |
| `run_detached(cmd)` | fire-and-forget a subprocess outside the loop |
| `ipc(verb, fn)` | register a CLI/IPC verb as `"<module> <verb>"` |
| `context` | the current focused-window `Context` |
| `on_context(fn)` | subscribe to context changes |
| `keys(names)` | request uinput keys be sent |
| `invalidate(widget=None)` | request a redraw |
| `open_group(name)` / `close_group()` / `is_group_open(name)` | drive group state |
| `slide_into(name, x, y)` | animate a group open from a touch point |
| `wake()` | light the bar as a touch would (a scene taking a dark bar) |
| `measure_text(s, size=...)` | text width in pixels, for layout math |
| `app_icon_path(cls, size=32)` | resolve an app icon path from its window class |
| `theme` | the shared `Theme` (colors, sizes) |
| `log(*a)` | log tagged with the module id |
| `state_dir` | a per-module writable directory under `XDG_STATE_HOME` |
| `now()` | monotonic clock, for animation timing |

`Sprite` (a strip of frames, one row, played at its own fps) takes a few widget parameters worth calling out: `pill=True` draws a button pill behind the strip that lights while pressed; `on_tap` / `on_long_press` are callbacks, like `Button`'s; `fps` (a float) is the playback rate; `frames=0` (the default) reads the frame count off the sheet's width instead of a fixed number, so a regenerated sheet with more frames never shows holes.

## CLI

```
macarchy-touchbar daemon [--headless]        # run the daemon (normally via the systemd unit)
macarchy-touchbar status                     # current layout, open group, active scenes, loaded modules
macarchy-touchbar reload                     # re-read layouts.toml and every module (also picks up plugins installed or removed since start)
macarchy-touchbar group <name>|close         # open or close a group
macarchy-touchbar screenshot <png>           # dump the current bar to a PNG
macarchy-touchbar touch x,y [x2,y2] [--long] # inject a synthetic touch (tap, drag, or long-press)
macarchy-touchbar brightness <n>|auto        # set or hand back panel brightness
macarchy-touchbar <module> <verb> [args]     # dispatch a module-registered IPC verb
```

## Verifying without eyes

The daemon can be driven and inspected entirely from the terminal, which matters because the Touch Bar itself can't be screenshotted by normal tools:

- `macarchy-touchbar daemon --headless` runs the full engine against an in-memory surface instead of the real DRM output — useful under a test harness or when the physical bar is in use by something else.
- `macarchy-touchbar screenshot out.png` renders whatever the bar (headless or real) currently shows to a PNG you can open normally.
- `macarchy-touchbar touch x,y [x2,y2] [--long]` injects a synthetic touch gesture — a tap, a drag between two points, or a long-press — so a module's behavior can be exercised without physically touching the hardware.
- Modules answer for themselves: `macarchy-touchbar media status` prints the player, the track and the volume the bar is showing as one line.

## Hardware tests

Most of the test suite runs against fakes and needs nothing special. Two tests touch the real Touch Bar hardware (the Touch Bar’s DRM card, `/dev/uinput`) and are skipped by default:

```
MACARCHY_TOUCHBAR_HW_TESTS=1 python3 -m pytest tests/ -q
```

Stop the daemon first (`systemctl --user stop macarchy-touchbar.service`) — the DRM test needs exclusive access to the display.

## Known deviations from the spec (lot 1)

- `api.icon` / `api.text` / `api.image` are not implemented: modules compose `Button`, `Label`, `Image` and the widgets draw through the `Painter`, so nothing needs a drawing API on `Api`.
- A module marked broken at runtime is reported by `macarchy-touchbar status` and in the journal, but its already-built widgets keep drawing normally instead of showing ⚠. The ⚠ fallback exists (`BrokenWidget`) and covers widgets that fail to resolve or build; swapping live widgets out on a runtime failure lands in a later lot.
- The grid values shipped differ from the spec's, after calibration on the hardware on 2026-09-02: pills are 60 px (the full height of the bar) rather than 44, glyphs 36 px rather than 24, and buttons 130 px wide. Radius 6, outer margin 8 and 6 px spacing are unchanged.
- The Jarvis button shows the state and the punctual emotions the FSM sends; the QML mascot's own moods (dnd, low battery, night) are not mirrored on the bar.
- Sprites draw at integer scale 1 — 56 px on the button and in the scene — rather than the spec's 40/54 px, superseded by lot 1's 60 px pills.
- A hot takeover restores the fish's sheet from the state file at load, but not the scene: the scene itself only reappears on the next state transition.

## Known deviations from the spec (lot 3)

Lot 3 is the `media` module: `media.now` and `media.art` sit on the default bar (Now Playing, with the cover or the player's app icon), and the media group holds `media.playpause` and a `media.volume` slider you can slide straight into from the group button. Now Playing is read from `omarchy-shell media status` — the shell's own MPRIS client, which already picks the active player — pushed by a `busctl --user monitor` doorbell; the volume is polled with `pactl`, but only while the group is open. `playerctl` and `cava` are deliberately **not** dependencies.

- **The auto-popping volume/brightness HUD scene was not built.** The only keyboard `/proc/bus/input/devices` lists on this machine is `Apple MTP keyboard`: Mac14,7 has no physical volume or brightness keys (the F-row *is* the Touch Bar), so the spec's trigger "while those keys are pressed" has no source. `Bar.current_layout()` returns `scenes.top().layout`, so a priority-20 scene replaces the whole bar and covers the very slider it was fired from; and `omarchy-audio-output-volume` already ends in `omarchy-osd -i volume-high -p N`, so it would be a second copy of a display that exists. The trigger to add it is an external keyboard with a real media row, and it is then a `pactl subscribe` doorbell plus `api.show_scene`, with this module's volume `Slider` as the scene body. `[settings] hud` stays inert, exactly as it is today.
- **The spectrum analyser was not built.** `cava` is not installed here, it needs a continuous FFT process and a 30 fps full-width repaint of a 2008×60 buffer against a daemon whose `activity.py` and `backlight.py` exist to *stop* drawing. `Meter.set_bands` already takes the data, so add it gated on the media group being open and the backlight awake.
- **No draggable timeline.** The `Scrubber` widget is lot 4, and MPRIS never signals `Position` — reading it means a subprocess a second for as long as anything plays.
- **The title does not scroll and `prev`/`next` never grey out.** `Painter.text` ellipsizes by default; a marquee would be a permanent 30 fps invalidation of the widest widget on the bar. `canGoNext` / `canGoPrevious` are in the status JSON, but `Button` has no disabled state — that lands with the first engine-side one, not before.
- **Upgrading:** `install.sh` never overwrites an existing `~/.config/macarchy-touchbar/layouts.toml`, so the media group, `slide_into = "media.volume"` and the `media.art` / `media.now` entries in the `left` rows have to be copied across by hand from `config/layouts.toml`.

## Design docs

The full specification and the plan this was built from live under [`docs/superpowers/specs`](docs/superpowers/specs) and [`docs/superpowers/plans`](docs/superpowers/plans).

## Releases

Versions are derived from [Conventional Commits](https://www.conventionalcommits.org)
by release-please: pushing to `main` keeps a release PR up to date, and merging
it tags `vX.Y.Z`. PRs land squash-merged, so it is the **PR title** that decides
the bump — `fix:` patch, `feat:` minor, `feat!:` major.

## License

MIT — see [LICENSE](LICENSE).
