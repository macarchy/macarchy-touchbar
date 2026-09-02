"""Modules: discovered through the Omarchy plugin registry, loaded in-process,
kept at arm's length behind an Api object and a try/except on every call."""
import importlib.util
import json
import os
import shlex
import subprocess
import time
import traceback
from dataclasses import dataclass

from .draw import Theme
from .log import log

KIND = "touchbar-module"


@dataclass
class ModuleSpec:
    id: str
    path: str
    order: int = 50


def _read_manifest(d):
    try:
        with open(os.path.join(d, "manifest.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def discover(internal_dir, plugins_dir, shell_json):
    specs = []
    for d in sorted(os.listdir(internal_dir)) if os.path.isdir(internal_dir) else []:
        m = _read_manifest(os.path.join(internal_dir, d))
        if m:
            entry = m.get("entryPoints", {}).get("touchbarModule", "touchbar.py")
            specs.append(ModuleSpec(m.get("id", d), os.path.join(internal_dir, d, entry),
                                    m.get("touchbarModule", {}).get("order", 10)))
    enabled = {p.get("id") for p in (shell_json or {}).get("plugins", []) if p.get("id")}
    for d in sorted(os.listdir(plugins_dir)) if os.path.isdir(plugins_dir) else []:
        if d.startswith("."):
            continue
        m = _read_manifest(os.path.join(plugins_dir, d))
        mid = m.get("id") if m else None
        if not m or KIND not in m.get("kinds", []) or not mid or mid not in enabled:
            continue
        entry = m.get("entryPoints", {}).get("touchbarModule")
        if not entry or ".." in entry or entry.startswith("/"):
            continue
        specs.append(ModuleSpec(mid, os.path.join(plugins_dir, d, entry),
                                m.get("touchbarModule", {}).get("order", 50)))
    specs.sort(key=lambda s: s.order)
    return specs


class Registry:
    def __init__(self):
        self._f = {}

    def register(self, module_id, name, factory):
        self._f[f"{module_id}.{name}"] = factory

    def factory(self, ref):
        return self._f[ref]

    def names(self, module_id):
        return [k for k in self._f if k.startswith(module_id + ".")]

    def drop(self, module_id):
        for k in self.names(module_id):
            del self._f[k]


class Api:
    def __init__(self, host, module_id):
        self.host, self.id = host, module_id
        self.theme = Theme
        self._timers, self._fds, self._ipc, self._scenes = [], [], {}, {}
        self._procs = []
        self._shown, self._ctx_listeners = set(), []
        self.state_dir = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                                      "macarchy-dfr", module_id)
        os.makedirs(self.state_dir, exist_ok=True)

    # registration
    def widget(self, name, factory):
        self.host.registry.register(self.id, name, factory)

    def scene(self, name, factory):
        self._scenes[name] = factory

    def show_scene(self, name, priority=50, timeout=None, dismissable=True):
        self._shown.add(name)
        self.host.hooks.show_scene(self.id, name, self._scenes[name], priority=priority,
                                   timeout=timeout, dismissable=dismissable,
                                   on_hide=lambda: self._shown.discard(name))

    def hide_scene(self, name):
        self._shown.discard(name)
        self.host.hooks.hide_scene(name)

    def ipc(self, verb, fn):
        self._ipc[verb] = fn

    # time and I/O
    def _g(self, fn):
        return lambda *a: self.host.guard(self.id, fn, *a)

    def every(self, s, fn):
        t = self.host.loop.every(s, self._g(fn)); self._timers.append(t); return t

    def after(self, s, fn):
        t = self.host.loop.after(s, self._g(fn)); self._timers.append(t); return t

    def watch_fd(self, fd, fn):
        self.host.loop.add_fd(fd, self._g(fn)); self._fds.append(fd)

    def watch_file(self, path, fn):
        """Poll mtime every second: sysfs has no inotify, and one poll is simpler than two paths."""
        state = {"m": None}
        def check():
            try:
                m = os.stat(path).st_mtime
            except OSError:
                m = None
            if m != state["m"]:
                state["m"] = m
                fn()
        return self.every(1.0, check)

    def run(self, argv, on_done=None, on_line=None):
        proc = self.host.loop.run(argv, on_done=self._g(on_done) if on_done else None,
                                  on_line=self._g(on_line) if on_line else None)
        if proc is not None:
            self._procs.append(proc)
        return proc

    def run_detached(self, cmd):
        subprocess.Popen(shlex.split(cmd) if isinstance(cmd, str) else cmd,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def now(self):
        return time.monotonic()

    # bar
    @property
    def context(self):
        return self.host.hooks.context

    def on_context(self, fn):
        w = self._g(fn)
        self._ctx_listeners.append(w)
        self.host.hooks.on_context(w)

    def keys(self, names):
        self.host.hooks.keys(list(names))

    def invalidate(self, widget=None):
        self.host.hooks.invalidate(widget)

    def open_group(self, name):
        self.host.hooks.open_group(name)

    def close_group(self):
        self.host.hooks.close_group()

    def is_group_open(self, name):
        return self.host.hooks.is_group_open(name)

    def slide_into(self, name, x, y):
        self.host.hooks.slide_into(name, x, y)

    def wake(self):
        self.host.hooks.wake()

    # drawing
    def measure_text(self, s, size=Theme.TEXT_PT):
        p = self.host.hooks.painter
        return p.measure_text(s, size) if p else 8 * len(s)

    def app_icon_path(self, cls, size=32):
        p = self.host.hooks.painter
        return p.app_icon_path(cls, size) if p else None

    def log(self, *a):
        log(f"[{self.id}]", *a)

    def _teardown(self):
        """Release everything the module took from the engine. Idempotent."""
        for t in self._timers:
            t.cancel()
        self._timers.clear()
        for fd in self._fds:
            self.host.loop.remove_fd(fd)
        self._fds.clear()
        for proc in self._procs:
            if proc.poll() is None:
                if proc.stdout:
                    self.host.loop.remove_fd(proc.stdout)
                try:
                    proc.terminate()
                except OSError:
                    pass
                try:
                    proc.stdout.close()
                except (OSError, AttributeError):
                    pass
            self.host.loop.children.pop(proc.pid, None)
        self._procs.clear()
        off_context = getattr(self.host.hooks, "off_context", None)
        if off_context:
            for w in self._ctx_listeners:
                off_context(w)
        self._ctx_listeners.clear()
        for name in list(self._shown):
            self.host.hooks.hide_scene(name)
        self._shown.clear()


class ModuleHost:
    def __init__(self, loop, hooks, registry):
        self.loop, self.hooks, self.registry = loop, hooks, registry
        self.modules, self.apis, self.specs = {}, {}, {}
        self.broken = {}

    def guard(self, module_id, fn, *a):
        try:
            return fn(*a)
        except Exception as e:
            self.broken[module_id] = f"{e!r}\n{traceback.format_exc()}"
            log(f"module {module_id} failed:", repr(e))
            self.hooks.invalidate(None)
            return None

    def load(self, spec):
        self.specs[spec.id] = spec
        self.broken.pop(spec.id, None)
        api = Api(self, spec.id)
        self.apis[spec.id] = api
        try:
            ms = importlib.util.spec_from_file_location(f"macarchy_dfr_module_{spec.id.replace('.', '_')}", spec.path)
            mod = importlib.util.module_from_spec(ms)
            ms.loader.exec_module(mod)
            inst = mod.Module()
            inst.setup(api)
            self.modules[spec.id] = inst
            log(f"module {spec.id}: {', '.join(self.registry.names(spec.id)) or 'no widgets'}")
        except Exception as e:
            self.broken[spec.id] = f"{e!r}\n{traceback.format_exc()}"
            log(f"module {spec.id} failed to load:", repr(e))
            self.registry.drop(spec.id)
            self.modules.pop(spec.id, None)
            api._teardown()
            self.apis.pop(spec.id, None)

    def unload(self, module_id):
        inst = self.modules.pop(module_id, None)
        if inst and hasattr(inst, "teardown"):
            self.guard(module_id, inst.teardown)
        api = self.apis.pop(module_id, None)
        if api:
            api._teardown()
        self.registry.drop(module_id)

    def reload(self, spec):
        self.unload(spec.id)
        self.load(spec)

    def dispatch_ipc(self, module_id, verb, args):
        api = self.apis.get(module_id)
        if not api or verb not in api._ipc:
            return f"error: no verb {verb} in {module_id}"
        try:
            out = api._ipc[verb](*args)
            return "ok" if out is None else str(out)
        except Exception as e:
            self.broken[module_id] = repr(e)
            log(f"module {module_id} ipc {verb} failed:", repr(e))
            return f"error: {e!r}"
