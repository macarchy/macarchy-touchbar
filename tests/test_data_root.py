"""Where the daemon looks for modules/, config/ and fonts/.

The data sits one directory above the python package. That was already true in a
git checkout; the packaging work kept it true rather than adding a second layout,
by installing macarchy_touchbar/ NEXT TO modules/ and config/ under
/usr/share/macarchy-touchbar. macarchy-install#16.

The checkout case is the one that must never break: ./install.sh symlinks
bin/macarchy-touchbar out of the repo and everything still has to resolve.
"""
import os
import subprocess
import sys

from macarchy_touchbar import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MACARCHY_TOUCHBAR_DATA", str(tmp_path))
    assert paths.data_root() == str(tmp_path)


def test_an_env_var_pointing_nowhere_is_still_honoured(tmp_path, monkeypatch):
    # Explicit beats clever: a silent fallback would hide the typo until the bar
    # came up with no modules on it.
    missing = tmp_path / "gone"
    monkeypatch.setenv("MACARCHY_TOUCHBAR_DATA", str(missing))
    assert paths.data_root() == str(missing)


def test_the_data_sits_beside_the_code(monkeypatch):
    monkeypatch.delenv("MACARCHY_TOUCHBAR_DATA", raising=False)
    root = paths.data_root()
    assert os.path.isdir(os.path.join(root, "modules"))
    assert os.path.isfile(os.path.join(root, "config", "layouts.toml"))
    assert os.path.isdir(os.path.join(root, "macarchy_touchbar"))


def test_a_package_layout_resolves_the_same_way(tmp_path, monkeypatch):
    # Simulate /usr/share/macarchy-touchbar: the python package beside the data.
    # No special case in data_root() is what makes the two layouts one rule.
    monkeypatch.delenv("MACARCHY_TOUCHBAR_DATA", raising=False)
    share = tmp_path / "share" / "macarchy-touchbar"
    (share / "macarchy_touchbar").mkdir(parents=True)
    (share / "modules").mkdir()
    (share / "macarchy_touchbar" / "paths.py").write_text(
        (ROOT / "macarchy_touchbar" / "paths.py").read_text()
        if hasattr(ROOT, "__truediv__") else
        open(os.path.join(ROOT, "macarchy_touchbar", "paths.py")).read())
    (share / "macarchy_touchbar" / "__init__.py").write_text("")
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from macarchy_touchbar.paths import data_root; print(data_root())" % str(share)],
        capture_output=True, text=True, env={k: v for k, v in os.environ.items()
                                             if k != "MACARCHY_TOUCHBAR_DATA"})
    assert out.stdout.strip() == str(share), out.stderr


def test_the_launcher_finds_the_tree_in_a_packaged_layout(tmp_path):
    # bin/macarchy-touchbar sits in /usr/bin once packaged, so "one level up" is
    # /usr and useless — it has to search. This is the bootstrap that makes the
    # single rule above work from an installed binary.
    launcher = open(os.path.join(ROOT, "bin", "macarchy-touchbar")).read()
    assert "/usr/share/macarchy-touchbar" in launcher
    assert "MACARCHY_TOUCHBAR_DATA" in launcher
