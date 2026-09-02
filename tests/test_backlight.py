from macarchy_dfr.backlight import BacklightPolicy, BarBacklight
from macarchy_dfr.loop import EventLoop


def test_policy_follows_main_then_dims_then_turns_off():
    p = BacklightPolicy(dim_after=60, off_after=300)
    assert p.level(0.5, 0) == 0.5
    assert p.level(0.1, 0) == 0.25
    assert abs(p.level(1.0, 60) - 0.15) < 1e-9
    assert p.level(1.0, 300) == 0.0
    assert BacklightPolicy(off_after=0).level(1.0, 99999) > 0
    assert p.level(0.5, 0, manual=80) == 0.8


def test_bar_backlight_writes_only_on_change(tmp_path):
    main = tmp_path / "main"; main.mkdir()
    (main / "brightness").write_text("254"); (main / "max_brightness").write_text("508")
    t = [0.0]
    writes = []
    loop = EventLoop(now=lambda: t[0])
    bl = BarBacklight(loop, BacklightPolicy(dim_after=10, off_after=20), bar_max=255,
                      main_dir=str(main), write=lambda n: writes.append(n), now=lambda: t[0])
    bl.poll(); bl.poll()
    assert writes == [127]
    t[0] = 10; bl.poll(); assert writes[-1] == int(255 * 0.5 * 0.15)
    t[0] = 20; bl.poll(); assert writes[-1] == 0 and not bl.awake
    bl.touched(); bl.poll(); assert bl.awake and writes[-1] == 127
