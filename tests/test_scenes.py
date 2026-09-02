from macarchy_dfr.scenes import Scene, SceneStack
from macarchy_dfr.groups import Group, GroupButton
from macarchy_dfr.layout import Layout, Row


def lay():
    return Layout(Row([]), Row([]))


def test_highest_priority_wins_then_most_recent():
    st = SceneStack(now=lambda: 0.0)
    st.show(Scene("notif", lay(), priority=30))
    st.show(Scene("jarvis", lay(), priority=50))
    st.show(Scene("notif2", lay(), priority=30))
    assert st.top().name == "jarvis"
    st.hide("jarvis")
    assert st.top().name == "notif2"


def test_timeout_expires_and_touch_extends():
    t = [0.0]
    st = SceneStack(now=lambda: t[0])
    st.show(Scene("hud", lay(), priority=20, timeout=1.5))
    assert st.deadline() == 1.5
    t[0] = 1.0; st.touch("hud")
    assert st.deadline() == 2.5
    t[0] = 2.4; assert st.tick(t[0]) is False and st.top()
    t[0] = 2.5; assert st.tick(t[0]) is True and st.top() is None


def test_show_same_name_replaces_and_on_hide_fires():
    gone = []
    st = SceneStack(now=lambda: 0.0)
    st.show(Scene("a", lay(), on_hide=lambda: gone.append("a1")))
    st.show(Scene("a", lay(), on_hide=lambda: gone.append("a2")))
    st.hide("a")
    assert gone == ["a2"] and len(st.scenes) == 0


class Api:
    def __init__(self): self.calls = []; self.open = None
    def open_group(self, n): self.calls.append(("open", n)); self.open = n
    def is_group_open(self, n): return self.open == n
    def slide_into(self, n, x, y): self.calls.append(("slide", n, x, y))
    def measure_text(self, s, size=22): return 10


def test_group_button_opens_and_slides():
    api = Api()
    g = Group("display", icon="brightness_6", items=["display.brightness"], slide_into="display.brightness")
    b = GroupButton(api, g)
    assert b.captures_drag
    b.on_tap(0, 0)
    assert api.calls == [("open", "display")] and b.is_active()
    b.on_drag(50, 30); b.on_drag(60, 30)
    assert api.calls[1:] == [("slide", "display", 50, 30)]


def test_tick_does_not_hide_scene_re_shown_by_on_hide():
    """Expiring scene's on_hide re-entrantly shows a new scene with same name;
    tick() must not hide it (remove by identity, not by name)."""
    t = [0.0]
    gone = []
    st = SceneStack(now=lambda: t[0])

    # Show A first (seq=1), then B (seq=2). Sort key is (-priority, -seq), so B comes first
    # in the sorted list (seq=2 sorts before seq=1 when negated). Both expire at t=1.0.
    def a_hide():
        gone.append("A1")
        st.show(Scene("B", lay(), timeout=5, on_hide=lambda: gone.append("B2")))

    st.show(Scene("A", lay(), timeout=1, on_hide=a_hide))
    st.show(Scene("B", lay(), timeout=1, on_hide=lambda: gone.append("B1")))

    # At time 0: scenes are [B, A] sorted by (-priority, -seq)
    # B has seq=2 (negated: -2), A has seq=1 (negated: -1); -2 < -1, so B is first
    assert st.top().name == "B"

    # Advance to 1.0 and tick: both A and B expire at the same time
    t[0] = 1.0
    st.tick(t[0])

    # B expires first (higher seq, sorted earlier), fires B1.
    # Then A expires, fires A1, which shows new B (timeout=5).
    # The new B (seq=3, timeout=5) should not expire yet, and its on_hide (B2) should not fire.
    assert "B2" not in gone, "New B's on_hide should not have fired"
    assert st.top() is not None and st.top().name == "B", "New B should survive"
    assert gone == ["B1", "A1"], f"Expected ['B1', 'A1'], got {gone}"
