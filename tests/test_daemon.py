import os

from macarchy_dfr.daemon import build
from macarchy_dfr.config import Config
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.output import HeadlessOutput
from macarchy_dfr.hypr import Context


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
