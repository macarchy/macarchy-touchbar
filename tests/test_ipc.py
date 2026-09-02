import os
from macarchy_dfr.ipc import IpcServer, ipc_send, EngineIpc
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.touch import Gesture


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
