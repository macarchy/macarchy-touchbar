import gc
import os
import importlib.util
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import Registry, ModuleHost, ModuleSpec
from tests.test_modules import Hooks


def load(tmp_path, monkeypatch):
    main = tmp_path / "main"; main.mkdir()
    (main / "brightness").write_text("254"); (main / "max_brightness").write_text("508")
    kbd = tmp_path / "kbd"; kbd.mkdir()
    (kbd / "brightness").write_text("0"); (kbd / "max_brightness").write_text("255")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("display_mod", "modules/display/touchbar.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    mod.Module.MAIN_DIR, mod.Module.KBD_DIR = str(main), str(kbd)
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("display", "modules/display/touchbar.py", 10))
    # the loaded instance is a fresh import: patch its class attributes too
    inst = host.modules["display"]
    type(inst).MAIN_DIR, type(inst).KBD_DIR = str(main), str(kbd)
    inst.refresh()
    return reg, host, inst


def test_brightness_slider_reads_sysfs_and_writes_through_omarchy(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    calls = []
    host.apis["display"].run = lambda argv, on_done=None, on_line=None: calls.append((argv, on_done))
    s = reg.factory("display.brightness")(host.apis["display"])
    inst.refresh()
    assert abs(s.value - 0.5) < 0.01
    s.rect = __import__("macarchy_dfr.geometry", fromlist=["Rect"]).Rect(0, 8, 400, 44)
    s.on_tap(360, 30)
    assert calls[0][0] == ["brightnessctl", "-q", "-d", "apple-panel-bl", "set", "100%"]


def test_brightness_slider_coalesces_writes_while_one_is_in_flight(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    calls = []
    host.apis["display"].run = lambda argv, on_done=None, on_line=None: calls.append((argv, on_done))
    # Slider._emit throttles by api.now(); give it a clock that always advances
    # past the 0.05s throttle window so none of the three drags below is dropped.
    counter = {"t": 0.0}
    def fake_now():
        counter["t"] += 0.1
        return counter["t"]
    host.apis["display"].now = fake_now
    s = reg.factory("display.brightness")(host.apis["display"])
    inst.refresh()
    s.rect = __import__("macarchy_dfr.geometry", fromlist=["Rect"]).Rect(0, 8, 400, 44)

    # 40..360 rail: 200 -> 0.5, 280 -> 0.75, 360 -> 1.0.
    s.on_drag(200, 30)
    s.on_drag(280, 30)
    s.on_drag(360, 30)
    assert len(calls) == 1

    calls[0][1](0, "")
    assert len(calls) == 2
    assert calls[1][0] == ["brightnessctl", "-q", "-d", "apple-panel-bl", "set", "100%"]

    calls[1][1](0, "")
    assert len(calls) == 2


def test_auto_button_reflects_als_pid_and_paused_flag(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    b = reg.factory("display.auto")(host.apis["display"])
    inst.refresh(); assert not b.active
    (tmp_path / "omarchy-als.pid").write_text("1"); inst.refresh(); assert b.active
    (tmp_path / "omarchy-als.paused").write_text(""); inst.refresh(); assert not b.active


def test_widgets_are_weakly_held_and_pruned_after_layout_rebuild(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    s = reg.factory("display.brightness")(host.apis["display"])
    assert len(inst.widgets) == 1
    del s
    gc.collect()
    assert len(inst.widgets) == 0
    a = reg.factory("display.brightness")(host.apis["display"])
    b = reg.factory("display.keyboard")(host.apis["display"])
    assert len(inst.widgets) == 2
