import os
import sys
from macarchy_dfr.loop import EventLoop


def test_fd_callback_fires_when_readable():
    loop = EventLoop()
    r, w = os.pipe()
    got = []
    loop.add_fd(r, lambda: got.append(os.read(r, 10)))
    os.write(w, b"hi")
    loop.step(timeout=0.1)
    assert got == [b"hi"]


def test_timers_fire_in_order_and_every_repeats():
    t = [0.0]
    loop = EventLoop(now=lambda: t[0])
    order = []
    loop.after(0.5, lambda: order.append("b"))
    loop.after(0.1, lambda: order.append("a"))
    tick = loop.every(0.2, lambda: order.append("tick"))
    t[0] = 0.15; loop.step(timeout=0)
    t[0] = 0.25; loop.step(timeout=0)
    t[0] = 0.45; loop.step(timeout=0)
    tick.cancel()
    t[0] = 1.0; loop.step(timeout=0)
    assert order == ["a", "tick", "tick", "b"]


def test_run_streams_lines_and_reports_completion():
    loop = EventLoop()
    lines, done = [], []
    loop.run([sys.executable, "-c", "print('one'); print('two')"],
             on_line=lines.append, on_done=lambda rc, out: done.append((rc, out)))
    for _ in range(50):
        loop.step(timeout=0.05)
        if done:
            break
    assert lines == ["one", "two"] and done == [(0, "one\ntwo\n")]
