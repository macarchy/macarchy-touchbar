import gc

from macarchy_touchbar.loop import EventLoop
from macarchy_touchbar.modules import Registry, ModuleHost, ModuleSpec
from macarchy_touchbar.draw import Theme
from tests.test_modules import Hooks


def load(tmp_path, capacity="55", status="Discharging", end="80", empty="11520", full="0"):
    bat = tmp_path / "bat"; bat.mkdir(exist_ok=True)
    (bat / "capacity").write_text(capacity); (bat / "status").write_text(status)
    (bat / "charge_control_end_threshold").write_text(end)
    (bat / "time_to_empty_now").write_text(empty); (bat / "time_to_full_now").write_text(full)
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("system", "modules/system/touchbar.py", 20))
    inst = host.modules["system"]; type(inst).BAT = str(bat); inst.refresh()
    return reg, host, inst


def test_battery_text_icon_and_tint(tmp_path):
    reg, host, inst = load(tmp_path)
    b = reg.factory("system.battery")(host.apis["system"]); inst.refresh()
    assert b.text == "55 %" and b.icon == "battery_4_bar" and b.tint == Theme.ACCENT_GREEN
    assert b.measure() == 130
    load(tmp_path, "15", "Discharging"); inst.refresh()
    assert b.tint == Theme.ACCENT_RED and b.icon == "battery_1_bar"
    load(tmp_path, "35", "Discharging"); inst.refresh()
    assert b.tint == Theme.ACCENT_ORANGE and b.icon == "battery_2_bar"
    load(tmp_path, "90", "Charging"); inst.refresh()
    assert b.tint == Theme.ACCENT_GREEN and b.icon == "battery_charging_full"


def test_charge_limit_button_reads_threshold(tmp_path):
    reg, host, inst = load(tmp_path, end="80")
    b = reg.factory("system.charge_limit")(host.apis["system"]); inst.refresh()
    assert b.active
    load(tmp_path, end="100"); inst.refresh()
    assert not b.active


def test_battery_long_press_shows_a_scene(tmp_path):
    reg, host, inst = load(tmp_path)
    b = reg.factory("system.battery")(host.apis["system"])
    b.on_long_press(0, 0)
    assert ("show", "battery") in host.hooks.calls


def test_battery_scene_text(tmp_path):
    reg, host, inst = load(tmp_path, "55", "Discharging", end="80", empty="11520", full="0")
    layout = inst.battery_scene(host.apis["system"])
    text = layout.left.widgets[0].text
    assert "55 %" in text and "3 h 12" in text and "limite 80 %" in text

    reg, host, inst = load(tmp_path, "90", "Charging", end="80", empty="0", full="600")
    layout = inst.battery_scene(host.apis["system"])
    text = layout.left.widgets[0].text
    assert "0 h 10" in text and "avant la charge complète" in text

    reg, host, inst = load(tmp_path, "55", "Discharging", end="100", empty="0", full="0")
    layout = inst.battery_scene(host.apis["system"])
    text = layout.left.widgets[0].text
    assert "—" in text and "limite" not in text


def test_widgets_are_weakly_held_and_pruned_after_gc(tmp_path):
    reg, host, inst = load(tmp_path)
    b = reg.factory("system.battery")(host.apis["system"])
    assert len(inst.widgets) == 1
    del b
    gc.collect()
    assert len(inst.widgets) == 0
