"""One selectors loop for everything: fds, timers, child processes.

Modules never block; whatever they need to wait on goes through here.
"""
import heapq
import os
import selectors
import subprocess
import time
import itertools

from .log import log


class Timer:
    def __init__(self, loop, when, fn, period):
        self.loop, self.when, self.fn, self.period = loop, when, fn, period
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class EventLoop:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.sel = selectors.DefaultSelector()
        self.timers = []
        self._seq = itertools.count()
        self.soon = []
        self.running = False
        self.children = {}

    def add_fd(self, fd, callback):
        self.sel.register(fd, selectors.EVENT_READ, callback)

    def remove_fd(self, fd):
        try:
            self.sel.unregister(fd)
        except (KeyError, ValueError):
            pass

    def _push(self, timer):
        heapq.heappush(self.timers, (timer.when, next(self._seq), timer))

    def after(self, seconds, fn):
        t = Timer(self, self.now() + seconds, fn, None)
        self._push(t)
        return t

    def every(self, seconds, fn):
        t = Timer(self, self.now() + seconds, fn, seconds)
        self._push(t)
        return t

    def call_soon(self, fn):
        self.soon.append(fn)

    def run(self, argv, on_done=None, on_line=None):
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError as e:
            log(f"cannot run {argv[0]}: {e}")
            if on_done:
                self.call_soon(lambda: on_done(-1, ""))
            return None
        os.set_blocking(proc.stdout.fileno(), False)
        state = {"buf": "", "out": [], "timer": None, "on_done_called": False}

        def readable():
            try:
                chunk = proc.stdout.read()
            except BlockingIOError:
                return
            if chunk:
                state["buf"] += chunk
                *lines, state["buf"] = state["buf"].split("\n")
                for line in lines:
                    state["out"].append(line + "\n")
                    if on_line:
                        on_line(line)
                return
            # EOF
            if state["buf"]:
                state["out"].append(state["buf"])
                if on_line:
                    on_line(state["buf"])
            self.remove_fd(proc.stdout)
            rc = proc.poll()
            if rc is not None:
                # Child already exited
                if not state["on_done_called"]:
                    state["on_done_called"] = True
                    self.children.pop(proc.pid, None)
                    if on_done:
                        on_done(rc, "".join(state["out"]))
            else:
                # Child still running, set up a reap timer
                def check():
                    if state["on_done_called"]:
                        return
                    rc = proc.poll()
                    if rc is not None:
                        # Child exited
                        # Cancel before calling out: an on_done that raises
                        # must not leave this timer repeating forever.
                        state["on_done_called"] = True
                        self.children.pop(proc.pid, None)
                        state["timer"].cancel()
                        if on_done:
                            on_done(rc, "".join(state["out"]))

                state["timer"] = self.every(0.2, check)

        self.add_fd(proc.stdout, readable)
        self.children[proc.pid] = proc
        return proc

    def _next_timeout(self):
        while self.timers and self.timers[0][2].cancelled:
            heapq.heappop(self.timers)
        if self.soon:
            return 0
        if not self.timers:
            return None
        return max(0.0, self.timers[0][0] - self.now())

    def step(self, timeout=None):
        t = self._next_timeout()
        if timeout is not None:
            t = timeout if t is None else min(t, timeout)
        for key, _ in self.sel.select(t):
            try:
                key.data()
            except Exception as e:      # a callback must never kill the loop
                log("fd callback failed:", repr(e))
        while self.soon:
            fn = self.soon.pop(0)
            try:
                fn()
            except Exception as e:
                log("call_soon failed:", repr(e))
        now = self.now()
        while self.timers and self.timers[0][0] <= now:
            _, _, timer = heapq.heappop(self.timers)
            if timer.cancelled:
                continue
            try:
                timer.fn()
            except Exception as e:
                log("timer failed:", repr(e))
            if timer.period and not timer.cancelled:
                timer.when = now + timer.period
                self._push(timer)

    def run_forever(self):
        self.running = True
        while self.running:
            self.step()

    def stop(self):
        self.running = False
