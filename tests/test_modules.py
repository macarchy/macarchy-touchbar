import json
import os
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import discover, Registry, ModuleHost, Api

GOOD = '''
class Module:
    def setup(self, api):
        self.api = api
        api.widget("thing", lambda api, **p: ("thing", p))
        api.ipc("ping", lambda *a: "pong " + " ".join(a))
        api.every(10, self.tick)
    def tick(self): pass
'''
BAD = '''
class Module:
    def setup(self, api):
        raise RuntimeError("boom")
'''
FLAKY = '''
class Module:
    def setup(self, api):
        api.widget("w", lambda api, **p: 1)
        api.ipc("die", lambda *a: 1 / 0)
'''
SETUP_THEN_RAISE = '''
class Module:
    def setup(self, api):
        api.widget("w", lambda api, **p: 1)
        raise RuntimeError("late boom")
'''
CTX_AND_SCENE = '''
class Module:
    def setup(self, api):
        api.scene("s", lambda api, **p: ("scene", p))
        api.on_context(lambda ctx: None)
        api.show_scene("s")
'''


def plugin(tmp, pid, code, kinds=("touchbar-module",)):
    d = tmp / pid; d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"id": pid, "kinds": list(kinds),
                                                  "entryPoints": {"touchbarModule": "touchbar.py"}}))
    (d / "touchbar.py").write_text(code)
    return d


class Hooks:
    context = None
    painter = None
    def __init__(self): self.calls = []
    def invalidate(self, w=None): self.calls.append(("inv", w))
    def show_scene(self, *a, **k): self.calls.append(("show", a[1]))
    def hide_scene(self, n): self.calls.append(("hide", n))
    def on_context(self, fn): pass
    def off_context(self, fn): self.calls.append(("off_context", fn))
    def keys(self, names): self.calls.append(("keys", names))
    def open_group(self, n): pass
    def close_group(self): pass
    def is_group_open(self, n): return False
    def slide_into(self, n, x, y): pass


def test_discover_internal_and_enabled_external(tmp_path):
    internal = tmp_path / "internal"; plugins = tmp_path / "plugins"
    plugin(internal, "core", GOOD)
    plugin(plugins, "macarchy.jarvis", GOOD)
    plugin(plugins, "macarchy.off", GOOD)                       # not enabled in shell.json
    plugin(plugins, "macarchy.svc", GOOD, kinds=("service",))   # wrong kind
    shell = {"plugins": [{"id": "macarchy.jarvis"}, {"id": "macarchy.svc"}]}
    specs = discover(str(internal), str(plugins), shell)
    assert [s.id for s in specs] == ["core", "macarchy.jarvis"]


def test_load_registers_widgets_and_ipc_and_isolates_failures(tmp_path):
    plugin(tmp_path, "good", GOOD); plugin(tmp_path, "bad", BAD); plugin(tmp_path, "flaky", FLAKY)
    shell = {"plugins": [{"id": "good"}, {"id": "bad"}, {"id": "flaky"}]}
    specs = discover(str(tmp_path / "none"), str(tmp_path), shell)
    reg, host = Registry(), ModuleHost(EventLoop(), Hooks(), Registry())
    host.registry = reg
    for s in specs:
        host.load(s)
    assert reg.factory("good.thing")(None, a=1) == ("thing", {"a": 1})
    assert host.dispatch_ipc("good", "ping", ["x"]) == "pong x"
    assert "bad" in host.broken and "boom" in host.broken["bad"]
    assert host.dispatch_ipc("flaky", "die", []).startswith("error")
    assert "flaky" in host.broken
    host.unload("good")
    import pytest
    with pytest.raises(KeyError):
        reg.factory("good.thing")


def test_api_state_dir_and_now(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    host = ModuleHost(EventLoop(), Hooks(), Registry())
    api = Api(host, "x.y")
    assert api.state_dir == str(tmp_path / "macarchy-dfr" / "x.y") and os.path.isdir(api.state_dir)
    assert isinstance(api.now(), float)


def test_load_rolls_back_on_failed_setup(tmp_path):
    plugin(tmp_path, "partial", SETUP_THEN_RAISE)
    shell = {"plugins": [{"id": "partial"}]}
    specs = discover(str(tmp_path / "none"), str(tmp_path), shell)
    host = ModuleHost(EventLoop(), Hooks(), Registry())
    host.load(specs[0])
    assert "partial" in host.broken
    assert host.registry.names("partial") == []
    assert "partial" not in host.modules


def test_unload_releases_context_listener_and_hides_scene(tmp_path):
    plugin(tmp_path, "ctxmod", CTX_AND_SCENE)
    shell = {"plugins": [{"id": "ctxmod"}]}
    specs = discover(str(tmp_path / "none"), str(tmp_path), shell)
    hooks = Hooks()
    host = ModuleHost(EventLoop(), hooks, Registry())
    host.load(specs[0])
    host.unload("ctxmod")
    off_calls = [c for c in hooks.calls if c[0] == "off_context"]
    assert len(off_calls) == 1 and callable(off_calls[0][1])
    assert ("hide", "s") in hooks.calls


def test_discover_skips_external_manifest_without_id(tmp_path):
    plugins = tmp_path / "plugins"
    d = plugins / "noid"; d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"kinds": ["touchbar-module"],
                                                  "entryPoints": {"touchbarModule": "touchbar.py"}}))
    (d / "touchbar.py").write_text(GOOD)
    shell = {"plugins": [{"id": "noid"}]}
    specs = discover(str(tmp_path / "none"), str(plugins), shell)
    assert specs == []
