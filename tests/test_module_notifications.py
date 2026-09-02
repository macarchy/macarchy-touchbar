import importlib.util

from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import Registry, ModuleHost, ModuleSpec
from tests.test_modules import Hooks

DBUS = '''method call time=1.0 sender=:1.5 -> destination=:1.2 serial=9 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "Signal"
   string "signal-desktop"
   uint32 0
   string "Alice"
   string "On mange où ?"
   array [
   ]
   array [
      dict entry(
         string "urgency"
         variant             byte 1
      )
   ]
   int32 -1
'''

DBUS_ESCAPE = '''method call time=2.0 sender=:1.5 -> destination=:1.2 serial=10 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "Mail"
   string "mail-app"
   uint32 0
   string "Bob"
   string "Read <b>& reply"
   array [
   ]
   array [
   ]
   int32 -1
'''


def test_parser_yields_one_notification_per_notify_call():
    spec = importlib.util.spec_from_file_location("notif", "modules/notifications/touchbar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod.NotifyParser()
    out = [n for line in DBUS.splitlines() if (n := p.feed(line))]
    assert out == [{"app": "Signal", "icon": "signal-desktop", "summary": "Alice",
                    "body": "On mange où ?", "urgency": 1}]


def test_a_notification_shows_the_scene():
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("notifications", "modules/notifications/touchbar.py", 30))
    inst = host.modules["notifications"]
    for line in DBUS.splitlines():
        inst.on_line(line)
    assert ("show", "notification") in host.hooks.calls
    lay = inst.scene(host.apis["notifications"])
    assert lay.left.widgets[0].close and "Alice" in lay.left.widgets[-1].text


def test_setup_does_not_spawn_synchronously():
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("notifications", "modules/notifications/touchbar.py", 30))
    assert "notifications" not in host.broken


def test_notification_body_markup_is_escaped():
    reg = Registry(); host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("notifications", "modules/notifications/touchbar.py", 30))
    inst = host.modules["notifications"]
    for line in DBUS_ESCAPE.splitlines():
        inst.on_line(line)
    lay = inst.scene(host.apis["notifications"])
    text = lay.left.widgets[-1].text
    assert "&lt;b&gt;&amp;" in text
