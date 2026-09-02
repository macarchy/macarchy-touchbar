from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import Registry, ModuleHost, ModuleSpec, Api
from macarchy_dfr.widgets import Button, Label, Slider
from macarchy_dfr.hypr import Context
from tests.test_modules import Hooks


def load_core():
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("core", "modules/core/touchbar.py", 0))
    assert "core" not in host.broken, host.broken
    return reg, host


def test_core_registers_the_toolkit():
    reg, host = load_core()
    assert isinstance(reg.factory("core.button")(None, icon="add"), Button)
    assert isinstance(reg.factory("core.slider")(None), Slider)
    clock = reg.factory("core.clock")(host.apis["core"])
    assert isinstance(clock, Label) and len(clock.text) == 5 and clock.text[2] == ":"
    assert host.dispatch_ipc("core", "ping", []) == "pong"


def test_app_widget_follows_context():
    reg, host = load_core()
    hooks = host.hooks
    listeners = []
    hooks.on_context = listeners.append
    app = reg.factory("core.app")(host.apis["core"])
    for fn in listeners:
        fn(Context("kitty", "shell — ~", 1, (1,), False, True))
    assert app.text == "shell — ~"
