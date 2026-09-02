import struct
import time

from macarchy_dfr.touch import TouchReader, TouchEvent, GestureRecognizer

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x2f, 0x35, 0x36, 0x39
BTN_TOUCH = 0x14a


def ev(typ, code, val, t=1.0):
    sec, usec = int(t), int((t % 1) * 1e6)
    return struct.pack("llHHi", sec, usec, typ, code, val)


def finger(x, y, tid=7, t=1.0):
    return (ev(EV_ABS, ABS_MT_SLOT, 0, t) + ev(EV_ABS, ABS_MT_TRACKING_ID, tid, t)
            + ev(EV_ABS, ABS_MT_POSITION_X, x, t) + ev(EV_ABS, ABS_MT_POSITION_Y, y, t)
            + ev(EV_KEY, BTN_TOUCH, 1, t) + ev(EV_SYN, 0, 0, t))


def lift(t=1.2):
    return ev(EV_ABS, ABS_MT_TRACKING_ID, -1, t) + ev(EV_KEY, BTN_TOUCH, 0, t) + ev(EV_SYN, 0, 0, t)


def test_reader_scales_axes_and_emits_down_move_up():
    r = TouchReader(None, xrange=(0, 20000), yrange=(0, 600))
    evs = r.feed(finger(10000, 300))
    assert [(e.kind, e.x, e.y) for e in evs] == [("down", 1003, 29)]
    evs = r.feed(ev(EV_ABS, ABS_MT_POSITION_X, 15000, 1.1) + ev(EV_SYN, 0, 0, 1.1))
    assert evs[0].kind == "move" and evs[0].x == 1505 and evs[0].y == 29
    assert r.feed(lift())[0].kind == "up"


def test_reader_flip_mirrors_x():
    r = TouchReader(None, xrange=(0, 20000), yrange=(0, 600), flip=True)
    assert r.feed(finger(0, 0))[0].x == 2007


def test_second_finger_is_ignored():
    r = TouchReader(None, xrange=(0, 20000), yrange=(0, 600))
    r.feed(finger(1000, 300))
    second = (ev(EV_ABS, ABS_MT_SLOT, 1) + ev(EV_ABS, ABS_MT_TRACKING_ID, 8)
              + ev(EV_ABS, ABS_MT_POSITION_X, 19000) + ev(EV_SYN, 0, 0))
    assert r.feed(second) == []


def g(kinds):
    return [x.kind for x in kinds]


def test_tap_is_press_then_tap_then_release():
    rec = GestureRecognizer()
    out = rec.feed(TouchEvent("down", 100, 30, 0.0))
    out += rec.feed(TouchEvent("up", 103, 31, 0.2))
    assert g(out) == ["press", "tap", "release"]


def test_slow_release_without_motion_is_long_press_from_tick():
    rec = GestureRecognizer()
    rec.feed(TouchEvent("down", 100, 30, 0.0))
    assert rec.deadline() == 0.5
    assert g(rec.tick(0.49)) == []
    assert g(rec.tick(0.5)) == ["long_press"]
    assert g(rec.feed(TouchEvent("up", 100, 30, 0.9))) == ["release"]   # no tap after long_press


def test_motion_beyond_slop_becomes_drag_and_cancels_long_press():
    rec = GestureRecognizer()
    rec.feed(TouchEvent("down", 100, 30, 0.0))
    assert g(rec.feed(TouchEvent("move", 105, 30, 0.1))) == []          # within slop
    out = rec.feed(TouchEvent("move", 120, 30, 0.2))
    assert g(out) == ["drag"] and rec.dragging and rec.deadline() is None
    assert g(rec.feed(TouchEvent("move", 140, 30, 0.3))) == ["drag"]
    assert g(rec.feed(TouchEvent("up", 140, 30, 0.4))) == ["drag_end", "release"]


def test_reader_stamps_events_on_the_monotonic_clock():
    """The evdev timestamp is CLOCK_REALTIME; the loop's deadlines are monotonic."""
    r = TouchReader(None, xrange=(0, 20000), yrange=(0, 600))
    rec = GestureRecognizer()
    for ev_ in r.feed(finger(10000, 300, t=1.0)):
        rec.feed(ev_)
    assert abs(rec.deadline() - time.monotonic()) < 1.0
    assert g(rec.tick(time.monotonic() + 0.6)) == ["long_press"]
