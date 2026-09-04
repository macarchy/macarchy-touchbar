import importlib.util
import json

from macarchy_dfr.geometry import Rect
from macarchy_dfr.loop import EventLoop
from macarchy_dfr.modules import ModuleHost, ModuleSpec, Registry
from tests.test_modules import Hooks

PATH = "modules/media/touchbar.py"
_spec = importlib.util.spec_from_file_location("media_mod", PATH)
media = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(media)

# The two shapes below are verbatim from the real machine on 2026-09-04:
# `omarchy-shell media status` with mpv playing, and with nothing playing.
PLAYING = json.dumps({"hasPlayer": True, "hasMedia": True, "playing": True, "identity": "mpv",
                      "desktopEntry": "mpv", "title": "Judge Test", "artist": "Sine", "album": "",
                      "artUrl": "", "canGoNext": False, "canGoPrevious": False, "canTogglePlaying": True})
IDLE = ('{"hasPlayer":false,"hasMedia":false,"playing":false,"identity":"","desktopEntry":"",'
        '"title":"","artist":"","album":"","artUrl":"","canGoNext":false,"canGoPrevious":false,'
        '"canTogglePlaying":false}')


def props_changed(props, sender=":1.1652"):
    """One `busctl --user --json=short monitor` line, the shape captured from a real mpv."""
    return json.dumps({"type": "signal", "sender": sender, "path": "/org/mpris/MediaPlayer2",
                       "interface": "org.freedesktop.DBus.Properties", "member": "PropertiesChanged",
                       "payload": {"type": "sa{sv}as",
                                   "data": ["org.mpris.MediaPlayer2.Player", props, []]}})


def metadata(length):
    """mpv's once-a-second re-emit: identical but for mpris:length."""
    return {"Metadata": {"type": "a{sv}", "data": {
        "xesam:url": {"type": "s", "data": "av://lavfi:sine=frequency=440"},
        "mpris:trackid": {"type": "o", "data": "/0"},
        "xesam:title": {"type": "s", "data": "Judge Test"},
        "mpris:length": {"type": "x", "data": length}}}}


CHURN1 = props_changed(metadata(2043356))
CHURN2 = props_changed(metadata(3018594))
PAUSED = props_changed({"PlaybackStatus": {"type": "s", "data": "Paused"}})
NAME_GONE = json.dumps({"type": "signal", "sender": "org.freedesktop.DBus", "path": "/org/freedesktop/DBus",
                        "interface": "org.freedesktop.DBus", "member": "NameOwnerChanged",
                        "payload": {"type": "sss",
                                    "data": ["org.mpris.MediaPlayer2.mpv", ":1.1652", ""]}})
VOLUME_OUT = ("Volume: front-left: 39976 /  61% / -12.88 dB,   front-right: 39976 /  61% / -12.88 dB\n"
              "        balance 0.00")


def load():
    reg = Registry()
    host = ModuleHost(EventLoop(), Hooks(), reg)
    host.load(ModuleSpec("media", PATH, 15))
    assert not host.broken, host.broken
    return reg, host, host.modules["media"]


def widgets(reg, host, *names):
    api = host.apis["media"]
    return [reg.factory(f"media.{n}")(api) for n in names]


def test_status_json_reaches_the_label_and_the_playpause_icon():
    reg, host, inst = load()
    label, pp = widgets(reg, host, "now", "playpause")
    inst._on_status(0, PLAYING)
    assert "<b>Judge Test</b>" in label.text and "Sine" in label.text
    assert pp.icon == "pause"


def test_local_art_wins_and_a_remote_cover_is_never_fetched(tmp_path):
    cover = tmp_path / "cover art.png"
    cover.write_bytes(b"x")
    assert media.local_art(f"file://{cover}".replace(" ", "%20")) == str(cover)
    assert media.local_art(f"file://{tmp_path}/gone.png") is None
    assert media.local_art("https://i.scdn.co/image/deadbeef") is None
    assert media.local_art("") is None

    reg, host, inst = load()
    (art,) = widgets(reg, host, "art")
    inst._on_status(0, json.dumps({**json.loads(PLAYING), "artUrl": f"file://{cover}".replace(" ", "%20")}))
    assert art.path == str(cover) and art.width == 56


def test_no_player_blanks_everything_instead_of_raising():
    reg, host, inst = load()
    label, art, pp = widgets(reg, host, "now", "art", "playpause")
    inst._on_status(0, PLAYING)
    inst._on_status(1, "")                      # omarchy-shell missing or failing
    assert (label.text, art.path, art.width, pp.icon) == ("", None, 0, "play_arrow")
    inst._on_status(0, IDLE)                    # nothing playing
    assert (label.text, art.path, art.width, pp.icon) == ("", None, 0, "play_arrow")
    inst._on_status(0, "not json at all")
    assert label.text == ""


def test_mpv_metadata_churn_collapses_to_one_refresh():
    """The fork-per-second regression: without fingerprint() this costs ~3600 omarchy-shell runs an hour."""
    _reg, host, inst = load()
    calls = []
    inst.api.after = lambda s, fn: calls.append((s, fn))
    inst.on_line(CHURN1)
    assert len(calls) == 1
    inst._pending = False                       # isolate the content filter from the burst coalescer
    inst.on_line(CHURN2)
    assert len(calls) == 1                      # same content but for mpris:length: no second fork
    inst.on_line(PAUSED)
    assert len(calls) == 2                      # a real change still gets through


def test_a_player_appearing_is_not_mistaken_for_metadata():
    assert media.fingerprint(NAME_GONE) is not None
    assert media.fingerprint(NAME_GONE) != media.fingerprint(CHURN1)
    assert media.fingerprint("}{ not json") is None


def test_volume_parse_and_the_pressed_slider_guard():
    reg, host, inst = load()
    (s,) = widgets(reg, host, "volume")
    inst._on_volume(0, VOLUME_OUT)
    assert abs(s.value - 0.61) < 1e-6
    s.pressed = True
    inst._on_volume(0, VOLUME_OUT.replace("61%", "10%"))
    assert abs(s.value - 0.61) < 1e-6           # a poll never fights a finger mid-drag
    inst._on_volume(0, "")
    assert abs(s.value - 0.61) < 1e-6


def test_polling_stops_when_the_group_is_shut():
    _reg, host, inst = load()
    runs = []
    inst.api.run = lambda argv, on_done=None, on_line=None: runs.append(argv)
    inst.poll_volume()                          # no volume widget alive
    assert runs == []


def test_a_drag_is_coalesced_to_one_pactl_in_flight():
    _reg, host, inst = load()
    runs = []
    inst.api.run = lambda argv, on_done=None, on_line=None: runs.append((argv, on_done))
    inst.sink = "audio_effect.j493-convolver"
    inst.set_volume(0.10)
    inst.set_volume(0.20)
    inst.set_volume(0.30)
    assert len(runs) == 1 and runs[0][0][-1] == "10%"
    runs[0][1](0, "")                           # the first pactl returns
    assert len(runs) == 2 and runs[1][0][-1] == "30%"   # the latest value wins, the middle one is dropped
    runs[1][1](0, "")
    assert len(runs) == 2                       # nothing left wanted


def test_ipc_status_answers_without_a_screenshot():
    reg, host, inst = load()
    assert inst.ipc_status() == "no player"
    (s,) = widgets(reg, host, "volume")
    inst._on_status(0, PLAYING)
    inst._on_volume(0, VOLUME_OUT)
    inst.sink = "audio_effect.j493-convolver"
    out = inst.ipc_status()
    assert "Judge Test" in out and "Playing" in out and "61 %" in out and "convolver" in out


def test_the_slider_moves_a_real_percentage_end_to_end():
    """The gesture the group's slide_into lands on: a drag has to become a pactl."""
    reg, host, inst = load()
    (s,) = widgets(reg, host, "volume")
    runs = []
    inst.api.run = lambda argv, on_done=None, on_line=None: runs.append(argv)
    inst.sink = "test-sink"
    s.rect = Rect(0, 0, 400, 60)
    s.on_tap(360, 30)                           # rail is x0=40..x1=360 with both end icons
    assert runs and runs[-1] == ["pactl", "set-sink-volume", "test-sink", "100%"]
