import os
import sys
import time
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


def test_run_with_missing_binary_does_not_raise_and_reports_failure():
    loop = EventLoop()
    rec = []
    result = loop.run(["/nonexistent/bin/xyz"], on_done=lambda rc, out: rec.append((rc, out)))
    assert result is None
    loop.step(timeout=0)
    assert rec == [(-1, "")]


def test_exception_isolation():
    """Exceptions in callbacks must not kill the loop or subsequent callbacks."""
    loop = EventLoop()

    # Set up a raising fd callback, timer, and call_soon
    r, w = os.pipe()
    got = []

    def bad_fd():
        got.append("bad_fd")
        raise ValueError("fd error")

    def bad_timer():
        got.append("bad_timer")
        raise ValueError("timer error")

    def bad_soon():
        got.append("bad_soon")
        raise ValueError("soon error")

    # Write data to make r readable
    os.write(w, b"x")
    loop.add_fd(r, bad_fd)
    loop.after(0, bad_timer)
    loop.call_soon(bad_soon)

    # Now add well-behaved callbacks
    loop.after(0, lambda: got.append("good_timer"))
    loop.call_soon(lambda: got.append("good_soon"))

    # Step should not raise even though some callbacks do
    loop.step(timeout=0.1)

    # Clean up
    os.close(r)
    os.close(w)

    # Verify that bad callbacks fired and were caught
    assert "bad_fd" in got
    assert "bad_timer" in got
    assert "bad_soon" in got
    # And good callbacks also fired
    assert "good_timer" in got
    assert "good_soon" in got


def test_run_nonblocking_reap():
    """Child that closes stdout but keeps running must not block the loop."""
    loop = EventLoop()
    lines, done = [], []
    start = time.monotonic()
    step_times = []

    # Spawn a child that closes stdout but keeps running for 0.3s
    loop.run(
        [sys.executable, "-c", "import os,sys,time; os.close(1); time.sleep(0.3)"],
        on_line=lines.append,
        on_done=lambda rc, out: done.append((rc, out))
    )

    # Step repeatedly with 0.05s timeout, measure each step
    for _ in range(50):
        step_start = time.monotonic()
        loop.step(timeout=0.05)
        step_end = time.monotonic()
        step_times.append(step_end - step_start)

        if done:
            break

    elapsed = time.monotonic() - start

    # Verify:
    # 1. No step took longer than 0.2s (it shouldn't block for 0.3s)
    max_step = max(step_times)
    assert max_step < 0.2, f"step took {max_step}s, should be < 0.2s"

    # 2. on_done was called exactly once
    assert len(done) == 1, f"on_done called {len(done)} times, should be 1"

    # 3. Return code is 0
    rc, output = done[0]
    assert rc == 0, f"rc is {rc}, should be 0"

    # 4. The whole thing completed within ~1s (not just waiting for child)
    assert elapsed < 1.0, f"took {elapsed}s, should be < 1s"
