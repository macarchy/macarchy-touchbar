"""Where the daemon looks for modules/, config/ and fonts/.

It used to be one directory above the python package — true in a git checkout,
where that is the repo root, and false in every other layout. A system package
puts macarchy_touchbar/ in site-packages/, so `ROOT` became
/usr/lib/pythonX.Y/site-packages/ and the daemon looked for modules/ there.
macarchy-install#16.

The checkout fallback is the one that must never break: ./install.sh symlinks
bin/macarchy-touchbar out of the repo and everything still has to resolve.
"""
import os

import pytest

from macarchy_touchbar import paths


def test_the_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MACARCHY_TOUCHBAR_DATA", str(tmp_path))
    assert paths.data_root() == str(tmp_path)


def test_the_packaged_directory_is_used_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("MACARCHY_TOUCHBAR_DATA", raising=False)
    packaged = tmp_path / "usr" / "share" / "macarchy-touchbar"
    (packaged / "modules").mkdir(parents=True)
    monkeypatch.setattr(paths, "PACKAGED", str(packaged))
    assert paths.data_root() == str(packaged)


def test_the_checkout_is_the_fallback(tmp_path, monkeypatch):
    # No env var, no packaged directory: the repo root, exactly as before.
    monkeypatch.delenv("MACARCHY_TOUCHBAR_DATA", raising=False)
    monkeypatch.setattr(paths, "PACKAGED", str(tmp_path / "nowhere"))
    assert os.path.isdir(os.path.join(paths.data_root(), "modules"))


def test_a_checkout_really_resolves_layouts_toml(monkeypatch):
    # The bug from the other side: a root that resolves but holds no config.
    monkeypatch.delenv("MACARCHY_TOUCHBAR_DATA", raising=False)
    assert os.path.isfile(os.path.join(paths.data_root(), "config", "layouts.toml"))


def test_an_env_var_pointing_nowhere_is_still_honoured(tmp_path, monkeypatch):
    # Explicit beats clever: if someone sets it, they meant it, and a silent
    # fallback to the checkout would hide their typo until the daemon drew a
    # bar with no modules on it.
    missing = tmp_path / "gone"
    monkeypatch.setenv("MACARCHY_TOUCHBAR_DATA", str(missing))
    assert paths.data_root() == str(missing)
