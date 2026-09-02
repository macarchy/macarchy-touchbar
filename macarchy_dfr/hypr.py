"""Hyprland: what is focused (queries) and when it changes (event socket)."""
import json
import os
import socket
from dataclasses import dataclass, replace

from .log import log

EVENTS = ("activewindow>>", "workspace>>", "openwindow>>", "closewindow>>", "movewindow>>", "focusedmon>>")


@dataclass(frozen=True)
class Context:
    cls: str = ""
    title: str = ""
    workspace: int = 0
    occupied: tuple = ()
    fn: bool = False
    awake: bool = True

    def replace(self, **kw):
        return replace(self, **kw)


def hypr_dir():
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    base = os.path.join(xdg, "hypr")
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if sig and os.path.isdir(os.path.join(base, sig)):
        return os.path.join(base, sig)
    try:
        cands = [os.path.join(base, d) for d in os.listdir(base)]
        cands = [c for c in cands if os.path.exists(os.path.join(c, ".socket.sock"))]
        return max(cands, key=os.path.getmtime)
    except (OSError, ValueError):
        return None


def hypr_query(cmd):
    d = hypr_dir()
    if not d:
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(os.path.join(d, ".socket.sock"))
        s.sendall(f"j/{cmd}".encode())
        buf = b""
        while chunk := s.recv(65536):
            buf += chunk
        s.close()
        return json.loads(buf.decode())
    except (OSError, ValueError):
        return None


def current_context(prev=None):
    win = hypr_query("activewindow") or {}
    ws = hypr_query("activeworkspace") or {}
    cls, title = win.get("class") or "", win.get("title") or ""
    if not cls and (ws.get("windows") or 0) > 0 and prev is not None:
        cls, title = prev.cls, prev.title        # Hyprland's transient null focus
    active = ws.get("id") or 0
    occupied = sorted({w["id"] for w in (hypr_query("workspaces") or [])
                       if isinstance(w.get("id"), int) and w["id"] > 0 and (w.get("windows") or 0) > 0}
                      | ({active} if active > 0 else set()))
    return Context(cls, title, active, tuple(occupied),
                   fn=prev.fn if prev else False, awake=prev.awake if prev else True)


def parse_events(buf):
    *lines, rest = buf.split(b"\n")
    return [l.decode(errors="replace") for l in lines], rest


class HyprEvents:
    def __init__(self, loop, on_change, debounce=0.08):
        self.loop, self.on_change, self.debounce = loop, on_change, debounce
        self.buf = b""
        self._timer = None
        d = hypr_dir()
        if not d:
            raise OSError("no Hyprland instance")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(os.path.join(d, ".socket2.sock"))
        self.sock.setblocking(False)
        loop.add_fd(self.sock, self._readable)

    def _readable(self):
        try:
            data = self.sock.recv(65536)
        except BlockingIOError:
            return
        if not data:
            log("Hyprland event socket closed")
            self.loop.remove_fd(self.sock)
            return
        lines, self.buf = parse_events(self.buf + data)
        if any(l.startswith(EVENTS) for l in lines) and self._timer is None:
            self._timer = self.loop.after(self.debounce, self._fire)

    def _fire(self):
        self._timer = None
        self.on_change()
