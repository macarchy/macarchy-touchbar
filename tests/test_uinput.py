import os
import pytest
from macarchy_dfr.uinput import key_code, VirtualKeyboard


def test_key_names_in_every_spelling():
    assert key_code("LeftCtrl") == key_code("KEY_LEFTCTRL") == 29
    assert key_code("VolumeUp") == 115 and key_code("F1") == 59 and key_code("T") == 20
    assert key_code("PreviousSong") == 165 and key_code("MicMute") == 248
    with pytest.raises(KeyError):
        key_code("NoSuchKey")


@pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK), reason="needs /dev/uinput")
def test_virtual_keyboard_creates_and_presses():
    kb = VirtualKeyboard()
    assert kb.available
    kb.press(["LeftCtrl", "T"])
    kb.close()


def test_unavailable_uinput_is_not_fatal(tmp_path):
    kb = VirtualKeyboard(path=str(tmp_path / "nope"))
    assert not kb.available
    kb.press(["A"])          # logs, no exception
