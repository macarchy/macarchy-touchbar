import struct
from macarchy_dfr.hypr import parse_events, Context, current_context
from macarchy_dfr.fnkey import parse_fn


def test_parse_events_keeps_partial_tail():
    lines, rest = parse_events(b"activewindow>>kitty,shell\nworkspace>>2\nopenwin")
    assert lines == ["activewindow>>kitty,shell", "workspace>>2"] and rest == b"openwin"


def test_current_context_filters_transient_null_window(monkeypatch):
    import macarchy_dfr.hypr as h
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
