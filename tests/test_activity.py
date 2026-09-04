import os

from macarchy_dfr.activity import ActivityWatcher, find_activity_devices
from macarchy_dfr.loop import EventLoop

PROC = """\
I: Bus=0019 Vendor=05ac Product=0354 Version=0240
N: Name="Apple MTP keyboard"
H: Handlers=sysrq kbd leds event1

I: Bus=0019 Vendor=05ac Product=0354 Version=0240
N: Name="Apple MTP multi-touch"
H: Handlers=mouse0 event2

I: Bus=001c Vendor=0000 Product=0000 Version=0000
N: Name="Mac14,7 Touch Bar"
H: Handlers=mouse1 event3
"""


def test_finds_trackpad_and_keyboard_but_not_the_bar_itself(tmp_path):
    devs = tmp_path / "devices"
    devs.write_text(PROC)
    # The Touch Bar has its own reader; watching it here would double-count.
    assert find_activity_devices(procfile=str(devs)) == ["/dev/input/event2", "/dev/input/event1"]


def test_missing_procfile_is_not_fatal(tmp_path):
    assert find_activity_devices(procfile=str(tmp_path / "nope")) == []


def _pipe():
    r, w = os.pipe()
    os.set_blocking(r, False)
    return r, w


def test_traffic_on_the_trackpad_counts_as_activity():
    t = [0.0]
    loop = EventLoop(now=lambda: t[0])
    hits = []
    r, w = _pipe()
    ActivityWatcher(loop, [r], lambda: hits.append(t[0]), cooldown=2.0)
    os.write(w, b"\0" * 64)
    loop.step(timeout=0)
    assert hits == [0.0]


def test_a_moving_finger_does_not_wake_the_loop_every_report():
    """The trackpad reports at ~100 Hz; the idle policy works in minutes."""
    t = [0.0]
    loop = EventLoop(now=lambda: t[0])
    hits = []
    r, w = _pipe()
    ActivityWatcher(loop, [r], lambda: hits.append(t[0]), cooldown=2.0)
    for _ in range(100):
        os.write(w, b"\0" * 64)
        loop.step(timeout=0)
        t[0] += 0.01
    assert hits == [0.0]                      # one report, not a hundred
    t[0] += 2.0
    loop.step(timeout=0)                      # cooldown expires, fd comes back
    os.write(w, b"\0" * 64)
    loop.step(timeout=0)
    assert len(hits) == 2


def test_a_device_that_goes_away_stops_being_watched():
    t = [0.0]
    loop = EventLoop(now=lambda: t[0])
    hits = []
    r, w = _pipe()
    watcher = ActivityWatcher(loop, [r], lambda: hits.append(1), cooldown=2.0)
    os.close(w)                               # unplugged: EOF, forever readable
    loop.step(timeout=0)
    assert hits == [] and watcher.fds == []
    loop.step(timeout=0)                      # would spin if still registered


def test_an_unreadable_device_is_skipped_not_fatal(tmp_path):
    loop = EventLoop()
    watcher = ActivityWatcher.open(loop, [str(tmp_path / "absent")], lambda: None)
    assert watcher.fds == []
