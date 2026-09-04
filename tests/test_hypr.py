import os
import struct
from macarchy_touchbar.hypr import parse_events, Context, current_context
from macarchy_touchbar.fnkey import parse_fn, FnWatcher, _SZ


def test_parse_events_keeps_partial_tail():
    lines, rest = parse_events(b"activewindow>>kitty,shell\nworkspace>>2\nopenwin")
    assert lines == ["activewindow>>kitty,shell", "workspace>>2"] and rest == b"openwin"


def test_current_context_filters_transient_null_window(monkeypatch):
    import macarchy_touchbar.hypr as h
    answers = {"activewindow": {}, "activeworkspace": {"id": 3, "windows": 2},
               "workspaces": [{"id": 3, "windows": 2}, {"id": 5, "windows": 0}, {"id": -99, "windows": 1}]}
    monkeypatch.setattr(h, "hypr_query", lambda cmd: answers[cmd])
    prev = Context("kitty", "shell", 3, (3,), fn=True, awake=False)
    ctx = current_context(prev)
    assert (ctx.cls, ctx.title) == ("kitty", "shell") and ctx.occupied == (3,)
    assert ctx.fn is True and ctx.awake is False


def test_parse_fn_reports_press_and_release_only():
    ev = lambda code, val: struct.pack("llHHi", 0, 0, 1, code, val)
    data = ev(0x1d0, 1) + ev(0x1d0, 2) + ev(30, 1) + ev(0x1d0, 0)
    assert parse_fn(data) == [True, False]


def test_fn_watcher_reads_events_and_closes_on_eof(monkeypatch):
    """Test FnWatcher reads events from pipe and removes itself on EOF."""
    from unittest.mock import MagicMock

    # Create a pipe for simulating keyboard input
    r_fd, w_fd = os.pipe()
    os.set_blocking(r_fd, False)

    # Create a mock loop
    loop = MagicMock()
    registered_callbacks = {}

    def mock_add_fd(fd, cb):
        registered_callbacks[fd] = cb

    def mock_remove_fd(fd):
        del registered_callbacks[fd]

    loop.add_fd = mock_add_fd
    loop.remove_fd = mock_remove_fd

    # Track callback invocations
    on_fn_calls = []

    def on_fn(down):
        on_fn_calls.append(down)

    # Create watcher using from_fd
    watcher = FnWatcher.from_fd(loop, r_fd, on_fn)

    # Write a KEY_FN press event (0x1d0 = KEY_FN, val=1 = press)
    ev = lambda code, val: struct.pack("llHHi", 0, 0, 1, code, val)
    data = ev(0x1d0, 1)
    os.write(w_fd, data)

    # Step the loop by calling the registered callback
    assert r_fd in registered_callbacks
    registered_callbacks[r_fd]()

    # Verify on_fn was called with True (press)
    assert on_fn_calls == [True]

    # Close the write end to simulate EOF
    os.close(w_fd)

    # Step the loop again
    registered_callbacks[r_fd]()

    # Verify fd was removed from loop and watcher.fd is None
    assert r_fd not in registered_callbacks
    assert watcher.fd is None
