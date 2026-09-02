import os

import macarchy_dfr.daemon as daemon
from macarchy_dfr.daemon import build, main
from macarchy_dfr.config import Config
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.output import HeadlessOutput
from macarchy_dfr.hypr import Context

from tests.test_modules import GOOD, Hooks, plugin
from macarchy_dfr.daemon import rediscover
from macarchy_dfr.modules import ModuleHost, Registry


def test_build_wires_internal_modules_and_default_layout(tmp_path):
    loop, out = EventLoop(), HeadlessOutput()
    cfg = Config.load("config/layouts.toml")
    bar, host = build(loop, out, cfg, plugins_dir=str(tmp_path), shell_json={"plugins": []})
    assert {"core", "display", "system", "notifications"} <= set(host.modules)
    assert not host.broken, host.broken
    bar.set_context(Context("kitty", "shell", 1, (1,), False, True))
    assert bar.base_name == "terminal"
    bar.redraw()
    assert out.flushes >= 1
    bar.screenshot(str(tmp_path / "bar.png"))
    assert os.path.getsize(tmp_path / "bar.png") > 1000


def test_main_config_without_value_does_not_raise_or_start_daemon(monkeypatch):
    def _fail(*a, **kw):
        raise AssertionError("run_daemon must not be called when --config has no value")
    monkeypatch.setattr(daemon, "run_daemon", _fail)
    assert main(["daemon", "--config"]) == 2


def test_rediscover_loads_new_plugins_and_drops_removed_ones(tmp_path):
    plugins = tmp_path / "plugins"
    host = ModuleHost(EventLoop(), Hooks(), Registry())
    shell = {"plugins": [{"id": "one"}, {"id": "two"}]}
    internal = str(tmp_path / "no-internal-modules")
    plugin(plugins, "one", GOOD)
    assert rediscover(host, internal, str(plugins), shell) == ["one"]
    plugin(plugins, "two", GOOD)                                  # installed after the daemon started
    assert rediscover(host, internal, str(plugins), shell) == ["one", "two"]
    import shutil; shutil.rmtree(plugins / "one")
    assert rediscover(host, internal, str(plugins), shell) == ["two"]
    assert "one" not in host.modules and "one" not in host.specs
