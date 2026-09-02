"""One Unix socket, one line in, one line out. The CLI and the modules' verbs."""
import os
import shlex
import socket
import sys

from .touch import Gesture


def sock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(base, "macarchy-dfr", "sock")


class IpcServer:
    def __init__(self, loop, path, handler):
        self.loop, self.path, self.handler = loop, path, handler
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(8)
        self.sock.setblocking(False)
        loop.add_fd(self.sock, self._accept)

    def _accept(self):
        try:
            conn, _ = self.sock.accept()
        except BlockingIOError:
            return
        conn.settimeout(1.0)
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            line = data.decode(errors="replace").strip()
            try:
                reply = self.handler(line)
            except Exception as e:
                reply = f"error: {e!r}"
            conn.sendall((str(reply) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.loop.remove_fd(self.sock)
        self.sock.close()
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def ipc_send(line, path=None, timeout=2.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path or sock_path())
    except OSError as e:
        raise ConnectionError(f"macarchy-dfr is not running ({e})") from e
    s.sendall((line + "\n").encode())
    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return buf.decode(errors="replace").rstrip("\n")


class EngineIpc:
    def __init__(self, bar, host, reload_fn):
        self.bar, self.host, self.reload_fn = bar, host, reload_fn

    def _touch(self, args):
        long = "--long" in args
        pts = [tuple(int(v) for v in a.split(",")) for a in args if "," in a]
        if not pts:
            return "error: touch x,y [x2,y2] [--long]"
        (x, y), rest = pts[0], pts[1:]
        self.bar.gesture(Gesture("press", x, y))
        if rest:
            (x2, y2) = rest[-1]
            for i in (1, 2):
                self.bar.gesture(Gesture("drag", x + (x2 - x) * i // 2, y + (y2 - y) * i // 2))
            self.bar.gesture(Gesture("drag_end", x2, y2))
            x, y = x2, y2
        elif long:
            self.bar.gesture(Gesture("long_press", x, y))
        else:
            self.bar.gesture(Gesture("tap", x, y))
        self.bar.gesture(Gesture("release", x, y))
        return "ok"

    def _status(self):
        lines = [f"layout {self.bar.base_name}", f"group {self.bar.open_group_name or '-'}",
                 "scenes " + (", ".join(s.name for s in self.bar.scenes.scenes) or "-"),
                 "modules " + ", ".join(sorted(self.host.modules))]
        for m, why in self.host.broken.items():
            lines.append(f"broken {m}: {why.splitlines()[0]}")
        return "\n".join(lines)

    def handle(self, line):
        args = shlex.split(line)
        if not args:
            return "error: empty request"
        verb, rest = args[0], args[1:]
        try:
            if verb == "status":
                return self._status()
            if verb == "reload":
                return self.reload_fn()
            if verb == "group" and rest:
                (self.bar.close_group() if rest[0] == "close" else self.bar.open_group(rest[0]))
                return "ok"
            if verb == "screenshot" and rest:
                self.bar.screenshot(rest[0])
                return "ok"
            if verb == "touch":
                return self._touch(rest)
            if verb == "brightness" and rest:
                bl = getattr(self.bar, "backlight", None)
                if not bl:
                    return "error: no backlight"
                bl.set_manual(None if rest[0] == "auto" else int(rest[0]))
                return "ok"
            if rest:
                return self.host.dispatch_ipc(verb, rest[0], rest[1:])
            return f"error: unknown verb {verb}"
        except Exception as e:
            return f"error: {e!r}"


USAGE = ("usage: macarchy-dfr daemon [--headless] [--config <toml>] | status | reload | group <name>|close | "
         "screenshot <png> | touch x,y [x2,y2] [--long] | brightness <n>|auto | <module> <verb> [args]")


def client(argv):
    """The CLI side of `macarchy-dfr <verb> …`. This module imports no engine
    code on purpose: a shell script calls it on every state change, and it has
    to cost a bare interpreter, not cairo and Pango."""
    if not argv:
        print(USAGE)
        return 2
    try:
        # A newline embedded in an argument (a module forwarding text
        # verbatim) would otherwise break the one-line protocol.
        flat = (a.replace("\n", " ").replace("\r", " ") for a in argv)
        print(ipc_send(" ".join(shlex.quote(a) for a in flat)))
        return 0
    except ConnectionError as e:
        print(e, file=sys.stderr)
        return 1
