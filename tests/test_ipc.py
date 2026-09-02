import os
import pytest
from macarchy_dfr.ipc import IpcServer, ipc_send, EngineIpc
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.touch import Gesture
from macarchy_dfr.scenes import Scene
from macarchy_dfr.layout import Layout, Row


def test_round_trip_over_unix_socket(tmp_path):
    loop = EventLoop()
    path = str(tmp_path / "sock")
    srv = IpcServer(loop, path, lambda line: f"got {line}")
    import threading
    t = threading.Thread(target=lambda: [loop.step(timeout=0.2) for _ in range(10)])
    t.start()
    assert ipc_send("hello world", path) == "got hello world"
    t.join()
    srv.close()


class FakeBar:
    def __init__(self): self.gestures = []; self.open = None
    def gesture(self, g): self.gestures.append(g.kind)
    def open_group(self, n): self.open = n
    def close_group(self): self.open = None
    def screenshot(self, p): open(p, "w").write("png")
    def current_layout(self): from macarchy_dfr.layout import Layout, Row; return Layout(Row([]), Row([]))
    base_name = "default"; open_group_name = None
    class scenes: scenes = []


class FakeHost:
    modules = {"core": 1}; broken = {}
    def dispatch_ipc(self, m, v, a): return f"{m}:{v}:{a}"


def test_engine_verbs(tmp_path):
    bar, host = FakeBar(), FakeHost()
    e = EngineIpc(bar, host, reload_fn=lambda: "reloaded")
    assert e.handle("touch 100,30") == "ok" and bar.gestures == ["press", "tap", "release"]
    bar.gestures.clear()
    assert e.handle("touch 100,30 300,30") == "ok" and bar.gestures == ["press", "drag", "drag", "drag_end", "release"]
    bar.gestures.clear()
    assert e.handle("touch 100,30 --long") == "ok" and bar.gestures == ["press", "long_press", "release"]
    assert e.handle("group media") == "ok" and bar.open == "media"
    assert e.handle("group close") == "ok" and bar.open is None
    assert e.handle("reload") == "reloaded"
    p = str(tmp_path / "s.png"); assert e.handle(f"screenshot {p}") == "ok" and os.path.exists(p)
    assert e.handle("jarvis state listening") == "jarvis:state:['listening']"
    assert "layout" in e.handle("status")
    assert e.handle("").startswith("error")


def test_ipc_send_absent_daemon(tmp_path):
    path = str(tmp_path / "absent")
    with pytest.raises(ConnectionError):
        ipc_send("status", path)


def test_engine_handle_malformed_input(tmp_path):
    bar, host = FakeBar(), FakeHost()
    e = EngineIpc(bar, host, reload_fn=lambda: "reloaded")
    result = e.handle("touch abc,30")
    assert result.startswith("error")
    assert bar.gestures == []


def test_engine_status_with_real_scenes(tmp_path):
    bar = FakeBar()
    bar.scenes = type('obj', (), {'scenes': [Scene("hud", Layout(Row([]), Row([])), priority=20)]})()
    host = FakeHost()
    e = EngineIpc(bar, host, reload_fn=lambda: "reloaded")
    result = e.handle("status")
    assert "scenes hud" in result


import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cli_client_runs_with_the_gui_libraries_blocked(tmp_path):
    """The FSM calls the CLI on every transition: it must cost a bare interpreter, not cairo + Pango.
    `sys.modules[name] = None` makes `import name` raise, so any engine import would be a traceback."""
    code = ("import sys, runpy; sys.modules['cairo'] = None; sys.modules['gi'] = None; "
            "sys.argv = ['macarchy-dfr', 'status']; runpy.run_path(%r, run_name='__main__')"
            % os.path.join(ROOT, "bin", "macarchy-dfr"))
    env = dict(os.environ, XDG_RUNTIME_DIR=str(tmp_path))          # no daemon socket there
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert "Traceback" not in r.stderr, r.stderr
    assert r.returncode == 1 and "not running" in r.stderr


def test_client_prints_usage_without_arguments():
    from macarchy_dfr.ipc import client, USAGE
    assert client([]) == 2
    assert "daemon" in USAGE
