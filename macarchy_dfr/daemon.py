"""Wire everything together, or forward a command to the running daemon."""
import json
import os
import shlex
import signal
import sys

from .backlight import BacklightPolicy, BarBacklight
from .bar import Bar
from .config import Config
from .draw import Painter
from .fnkey import FnWatcher, find_keyboard_device
from .hypr import HyprEvents, current_context, Context
from .ipc import USAGE, EngineIpc, IpcServer, client, sock_path
from .log import log
from .loop import EventLoop
from .modules import ModuleHost, Registry, discover
from .output import DrmOutput, HeadlessOutput
from .touch import GestureRecognizer, TouchReader, find_touch_device
from .uinput import VirtualKeyboard
from .widgets import Sprite

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
CFG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "macarchy-dfr", "layouts.toml")
PLUGINS = os.path.join(os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "omarchy", "plugins")
SHELL_JSON = os.path.join(os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "omarchy", "shell.json")


def _shell_json():
    try:
        with open(SHELL_JSON) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def build(loop, output, config, plugins_dir=None, shell_json=None):
    registry = Registry()
    host = ModuleHost(loop, None, registry)
    bar = Bar(output, loop, Painter(output.surface), config, registry, host)
    host.hooks = bar
    specs = discover(os.path.join(ROOT, "modules"), plugins_dir or PLUGINS,
                     _shell_json() if shell_json is None else shell_json)
    for spec in specs:
        host.load(spec)
    bar.reload_config(config)          # widgets can only resolve once modules registered them
    return bar, host


def rediscover(host, internal_dir, plugins_dir, shell_json):
    """Reload every module against the registry as it is NOW: plugins installed
    since the daemon started come up, removed ones go away. Returns the ids loaded."""
    specs = discover(internal_dir, plugins_dir, shell_json)
    wanted = {s.id for s in specs}
    for mid in list(host.specs):
        if mid not in wanted:
            host.unload(mid)
            host.specs.pop(mid, None)
            host.broken.pop(mid, None)
    for spec in specs:
        host.reload(spec)
    return [s.id for s in specs]


def _load_config(path):
    try:
        return Config.load(path)
    except (OSError, ValueError) as e:
        log(f"{path}: {e}; using the shipped layouts")
        return Config.load(os.path.join(ROOT, "config", "layouts.toml"))


def run_daemon(headless=False, config_path=CFG):
    loop = EventLoop()
    if headless:
        output = HeadlessOutput()
    else:
        try:
            output = DrmOutput.open()
        except (OSError, ValueError) as e:
            log(f"cannot open the Touch Bar: {e}")
            return 1
    config = _load_config(config_path)
    bar, host = build(loop, output, config)

    rt = os.path.dirname(sock_path())
    os.makedirs(rt, exist_ok=True)
    pid_path = os.path.join(rt, "daemon.pid")
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    keyboard = VirtualKeyboard() if not headless else None
    bar.keyboard = keyboard
    if not headless:
        s = config.settings
        bar.backlight = BarBacklight(loop, BacklightPolicy(s["dim_after"], s["off_after"]))
        bar.backlight.on_awake_change(lambda awake: bar.set_context(bar.context.replace(awake=awake)) if bar.context else None)

    ctx = {"prev": None}

    def refresh_context():
        ctx["prev"] = current_context(ctx["prev"])
        if bar.backlight:
            ctx["prev"] = ctx["prev"].replace(awake=bar.backlight.awake)
        bar.set_context(ctx["prev"])

    try:
        HyprEvents(loop, refresh_context)
        refresh_context()
    except OSError as e:
        log(f"no Hyprland ({e}); static default layout")
        bar.set_context(Context())

    if not headless:
        path = find_touch_device()
        if path:
            reader = TouchReader.open(path, flip=bool(config.settings.get("touch_flip")))
            rec = GestureRecognizer()
            swallow = {"on": False}

            def deliver(gs):
                for g in gs:
                    if g.kind == "press" and bar.backlight and not bar.backlight.awake:
                        swallow["on"] = True          # a dark bar: the first touch only wakes it
                    if bar.backlight:
                        bar.backlight.touched()
                    if swallow["on"]:
                        if g.kind == "release":
                            swallow["on"] = False
                        continue
                    bar.gesture(g)

            loop.add_fd(reader.fd, lambda: deliver([g for ev in reader.read() for g in rec.feed(ev)]))
            loop.every(0.05, lambda: deliver(rec.tick(loop.now())))
        else:
            log("no Touch Bar touch device found")
        kbd = find_keyboard_device()
        if kbd:
            try:
                FnWatcher(loop, kbd, bar.set_fn)
            except OSError as e:
                log(f"cannot watch {kbd} for Fn ({e})")

    def reload():
        nonlocal config
        config = _load_config(config_path)
        rediscover(host, os.path.join(ROOT, "modules"), PLUGINS, _shell_json())
        bar.reload_config(config)
        return "reloaded"

    ipc = IpcServer(loop, sock_path(), EngineIpc(bar, host, reload).handle)

    mtimes = {}

    def watch_sources():
        changed = False
        for p in [config_path] + [s.path for s in host.specs.values()]:
            try:
                m = os.stat(p).st_mtime
            except OSError:
                m = None
            if p in mtimes and mtimes[p] != m:
                changed = True
            mtimes[p] = m
        if changed:
            log("sources changed; reloading")
            reload()
    watch_sources()
    loop.every(1.0, watch_sources)
    loop.every(0.1, bar.tick)
    # Sprites keep their own fps; the ticker only offers them the clock. Skip
    # the work entirely once the backlight has dimmed: nothing is visible.
    def tick_sprites():
        if bar.backlight and not bar.backlight.awake:
            return
        for w in bar.current_layout().widgets():
            if isinstance(w, Sprite):
                w.tick(loop.now())
    loop.every(1 / 30, tick_sprites)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: loop.stop())
    log("running")
    try:
        loop.run_forever()
    finally:
        for m in list(host.modules):
            host.unload(m)
        ipc.close()
        try:
            os.unlink(pid_path)
        except OSError:
            pass
        if keyboard:
            keyboard.close()
        output.close()
        log("stopped")
    return 0


def main(argv):
    if argv and argv[0] == "daemon":
        headless = "--headless" in argv
        cfg = CFG
        if "--config" in argv:
            i = argv.index("--config")
            if i + 1 >= len(argv):
                print(USAGE, file=sys.stderr)
                return 2
            cfg = argv[i + 1]
        return run_daemon(headless=headless, config_path=cfg)
    return client(argv)
