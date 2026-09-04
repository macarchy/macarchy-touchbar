# macarchy-dfr

A Python daemon that owns the MacBook Touch Bar on Linux, drawing every pixel itself instead of leaning on tiny-dfr's built-in function-key strip. It reads Hyprland's focused window to switch layouts, and modules (built in or dropped in as Omarchy shell plugins) supply the widgets, groups and scenes that fill them.

## Install

```
./install.sh
```

This installs the system packages the daemon needs (`python-cairo`, `python-gobject`, `papirus-icon-theme`, `brightnessctl`), downloads the Material Symbols Rounded font it draws icons with, grants hardware access without root (adds you to the `video` group for the Touch Bar's DRM card, installs a udev rule for `/dev/uinput`), disables and masks `tiny-dfr` so it stops fighting over the display, migrates the Hyprland config off the old daemon (removes the `omarchy-dfr` Touch Bar binding block from `~/.config/hypr/bindings.lua` and points `~/.config/hypr/autostart.lua` at the `macarchy-dfr` user service instead of `omarchy-dfr daemon`, printing what it changed and reloading Hyprland — a no-op once done), symlinks the `macarchy-dfr` CLI into `~/.local/bin`, copies `config/layouts.toml` to `~/.config/macarchy-dfr/layouts.toml` (only if that file doesn't already exist — your edits are never overwritten), and installs + enables the `macarchy-dfr.service` systemd user unit. Re-run it any time to update.

```
./install.sh --uninstall
```

Stops and removes the service and CLI symlink, then unmasks and re-enables `tiny-dfr`. Your `layouts.toml` is left in place.

## layouts.toml

`~/.config/macarchy-dfr/layouts.toml` is watched by the daemon and reloaded within a second of being saved. It has three kinds of table:

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
from macarchy_dfr.widgets import Button


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
macarchy-dfr daemon [--headless]        # run the daemon (normally via the systemd unit)
macarchy-dfr status                     # current layout, open group, active scenes, loaded modules
macarchy-dfr reload                     # re-read layouts.toml and every module (also picks up plugins installed or removed since start)
macarchy-dfr group <name>|close         # open or close a group
macarchy-dfr screenshot <png>           # dump the current bar to a PNG
macarchy-dfr touch x,y [x2,y2] [--long] # inject a synthetic touch (tap, drag, or long-press)
macarchy-dfr brightness <n>|auto        # set or hand back panel brightness
macarchy-dfr <module> <verb> [args]     # dispatch a module-registered IPC verb
```

## Verifying without eyes

The daemon can be driven and inspected entirely from the terminal, which matters because the Touch Bar itself can't be screenshotted by normal tools:

- `macarchy-dfr daemon --headless` runs the full engine against an in-memory surface instead of the real DRM output — useful under a test harness or when the physical bar is in use by something else.
- `macarchy-dfr screenshot out.png` renders whatever the bar (headless or real) currently shows to a PNG you can open normally.
- `macarchy-dfr touch x,y [x2,y2] [--long]` injects a synthetic touch gesture — a tap, a drag between two points, or a long-press — so a module's behavior can be exercised without physically touching the hardware.

## Hardware tests

Most of the test suite runs against fakes and needs nothing special. Two tests touch the real Touch Bar hardware (the Touch Bar’s DRM card, `/dev/uinput`) and are skipped by default:

```
MACARCHY_DFR_HW_TESTS=1 python3 -m pytest tests/ -q
```

Stop the daemon first (`systemctl --user stop macarchy-dfr.service`) — the DRM test needs exclusive access to the display.

## Known deviations from the spec (lot 1)

- `api.icon` / `api.text` / `api.image` are not implemented: modules compose `Button`, `Label`, `Image` and the widgets draw through the `Painter`, so nothing needs a drawing API on `Api`.
- A module marked broken at runtime is reported by `macarchy-dfr status` and in the journal, but its already-built widgets keep drawing normally instead of showing ⚠. The ⚠ fallback exists (`BrokenWidget`) and covers widgets that fail to resolve or build; swapping live widgets out on a runtime failure lands in a later lot.
- The grid values shipped differ from the spec's, after calibration on the hardware on 2026-09-02: pills are 60 px (the full height of the bar) rather than 44, glyphs 36 px rather than 24, and buttons 130 px wide. Radius 6, outer margin 8 and 6 px spacing are unchanged.
- The Jarvis button shows the state and the punctual emotions the FSM sends; the QML mascot's own moods (dnd, low battery, night) are not mirrored on the bar.
- Sprites draw at integer scale 1 — 56 px on the button and in the scene — rather than the spec's 40/54 px, superseded by lot 1's 60 px pills.
- A hot takeover restores the fish's sheet from the state file at load, but not the scene: the scene itself only reappears on the next state transition.

## Design docs

The full specification and the plan this was built from live under [`docs/superpowers/specs`](docs/superpowers/specs) and [`docs/superpowers/plans`](docs/superpowers/plans).

## Releases

Versions are derived from [Conventional Commits](https://www.conventionalcommits.org)
by release-please: pushing to `main` keeps a release PR up to date, and merging
it tags `vX.Y.Z`. PRs land squash-merged, so it is the **PR title** that decides
the bump — `fix:` patch, `feat:` minor, `feat!:` major.

## License

MIT — see [LICENSE](LICENSE).
