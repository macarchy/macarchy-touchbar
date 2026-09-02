import gc
import os
import time
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


def test_brightness_slider_reads_sysfs_and_writes_through_logind(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    calls = []
    type(inst).SETTER = staticmethod(lambda *a: calls.append(a) or True)
    s = reg.factory("display.brightness")(host.apis["display"])
    inst.refresh()
    assert abs(s.value - 0.5) < 0.01
    s.rect = __import__("macarchy_dfr.geometry", fromlist=["Rect"]).Rect(0, 8, 400, 44)
    s.on_tap(360, 30)
    inst.writer.drain()
    assert calls[-1] == ("backlight", "apple-panel-bl", 508)


def test_keyboard_slider_writes_through_logind(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    calls = []
    type(inst).SETTER = staticmethod(lambda *a: calls.append(a) or True)
    s = reg.factory("display.keyboard")(host.apis["display"])
    inst.refresh()
    s.rect = __import__("macarchy_dfr.geometry", fromlist=["Rect"]).Rect(0, 8, 400, 44)
    s.on_tap(360, 30)
    inst.writer.drain()
    assert calls[-1] == ("leds", "kbd_backlight", 255)


def test_brightness_writes_leave_the_loop_and_latest_value_wins(tmp_path, monkeypatch):
    reg, host, inst = load(tmp_path, monkeypatch)
    calls = []

    def slow_setter(*a):
        time.sleep(0.05)
        calls.append(a)
        return True
    type(inst).SETTER = staticmethod(slow_setter)

    s = reg.factory("display.brightness")(host.apis["display"])
    inst.refresh()
    s.rect = __import__("macarchy_dfr.geometry", fromlist=["Rect"]).Rect(0, 8, 400, 44)

    api = host.apis["display"]
    fake_now = [0.0]
    api.now = lambda: fake_now[0]

    # rail runs x0=40..x1=360 for this rect (END=40 pad, since min/max icons
    # are set); x = x0 + v * (x1 - x0) hits value v exactly.
    for v in (0.5, 0.75, 1.0):
        fake_now[0] += 1.0      # advance the fake clock: bypass on_drag's 33 ms throttle
        s.on_drag(40 + v * 320, 30)

    inst.writer.drain()
    # the writer thread is slow (mirrors the 44 ms panel write): only the
    # latest requested value is guaranteed to land, superseding whatever
    # queued in front of it while a write was in flight.
    assert len(calls) <= 2
    assert calls[-1][2] == 508


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
