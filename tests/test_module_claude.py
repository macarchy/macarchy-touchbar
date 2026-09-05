import os
import time

from macarchy_touchbar.draw import Theme
from macarchy_touchbar.loop import EventLoop
from macarchy_touchbar.modules import Registry, ModuleHost, ModuleSpec
from tests.test_modules import Hooks


def load(tmp_path, **sessions):
    d = tmp_path / "macarchy-claude"
    d.mkdir(exist_ok=True)
    for name, pct in sessions.items():
        (d / name).write_text(f"{pct}\n")
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("claude", "modules/claude/touchbar.py", 25))
    inst = host.modules["claude"]; type(inst).DIR = str(d)
    return reg, host, inst, d


def button(reg, host, inst):
    b = reg.factory("claude.context")(host.apis["claude"])
    inst.refresh()
    return b


def test_percentage_and_tint_track_the_fullest_session(tmp_path):
    reg, host, inst, d = load(tmp_path, s1=42)
    b = button(reg, host, inst)
    assert b.text == "42 %" and b.tint == Theme.ACCENT_GREEN and b.badge is None

    (d / "s1").write_text("70"); inst.refresh()
    assert b.text == "70 %" and b.tint == Theme.ACCENT_ORANGE

    (d / "s1").write_text("91"); inst.refresh()
    assert b.text == "91 %" and b.tint == Theme.ACCENT_RED


def test_a_fleet_shows_the_worst_one_and_counts_the_rest(tmp_path):
    reg, host, inst, d = load(tmp_path, s1=12, s2=88, s3=40)
    b = button(reg, host, inst)
    assert b.text == "88 %" and b.badge == "3"


def test_dead_sessions_are_swept_and_the_button_goes_quiet(tmp_path):
    reg, host, inst, d = load(tmp_path, s1=55)
    b = button(reg, host, inst)
    assert b.text == "55 %"

    stale = time.time() - 120
    os.utime(d / "s1", (stale, stale))
    inst.refresh()
    assert not (d / "s1").exists()
    assert b.text is None and b.tint is None and b.badge is None


def test_unreadable_files_are_ignored_not_fatal(tmp_path):
    reg, host, inst, d = load(tmp_path, s1=30)
    (d / "s2").write_text("not a number")
    b = button(reg, host, inst)
    assert b.text == "30 %" and b.badge is None


def test_no_runtime_dir_means_no_reading(tmp_path, monkeypatch):
    reg, host, inst, d = load(tmp_path, s1=30)
    type(inst).DIR = None
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert inst.state() == (None, 0)
