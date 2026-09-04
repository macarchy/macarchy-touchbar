import os
import pytest
from macarchy_touchbar.uinput import key_code, VirtualKeyboard


def test_key_names_in_every_spelling():
    assert key_code("LeftCtrl") == key_code("KEY_LEFTCTRL") == 29
    assert key_code("VolumeUp") == 115 and key_code("F1") == 59 and key_code("T") == 20
    assert key_code("PreviousSong") == 165 and key_code("MicMute") == 248
    with pytest.raises(KeyError):
        key_code("NoSuchKey")


@pytest.mark.skipif(os.environ.get("MACARCHY_TOUCHBAR_HW_TESTS") != "1", reason="set MACARCHY_TOUCHBAR_HW_TESTS=1 with the daemon stopped to test the real Touch Bar")
def test_virtual_keyboard_creates_and_presses():
    kb = VirtualKeyboard()
    assert kb.available
    kb.press(["LeftCtrl", "T"])
    kb.close()


def test_unavailable_uinput_is_not_fatal(tmp_path):
    kb = VirtualKeyboard(path=str(tmp_path / "nope"))
    assert not kb.available
    kb.press(["A"])          # logs, no exception


def test_write_error_does_not_escape():
    """os.write() on a read-only fd raises OSError; press() must not escape."""
    kb = VirtualKeyboard.__new__(VirtualKeyboard)
    kb.available = True
    r, w = os.pipe()
    kb.fd = r  # read end is read-only; writing raises EBADF
    try:
        kb.press(["A"])  # logs error, no exception
    finally:
        os.close(r)
        os.close(w)
