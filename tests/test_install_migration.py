"""The Hyprland migration embedded in install.sh, run against a throwaway HOME.

It edits the user's own config, so the one thing that must never regress is
that it only touches blocks written under an OLD name -- a hand-written
current-name block has to survive untouched.
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migration_source():
    text = open(os.path.join(ROOT, "install.sh")).read()
    return re.search(r"<<'HYPRMIG'\n(.*?)\nHYPRMIG\n", text, re.S).group(1)


def run(home):
    env = dict(os.environ, HOME=str(home))
    env.pop("XDG_CONFIG_HOME", None)
    return subprocess.run([sys.executable, "-c", migration_source()],
                          env=env, capture_output=True, text=True, check=True)


@pytest.fixture
def hypr(tmp_path):
    d = tmp_path / ".config" / "hypr"
    d.mkdir(parents=True)
    return d


def test_current_name_block_is_left_alone(tmp_path, hypr):
    block = '-- ── Touch Bar (macarchy-touchbar)\nfor _, b in ipairs({}) do\nend\n'
    (hypr / "bindings.lua").write_text(block)
    (hypr / "autostart.lua").write_text(
        'o.exec_on_start("systemctl --user start macarchy-touchbar.service")\n')
    run(tmp_path)
    assert (hypr / "bindings.lua").read_text() == block


def test_legacy_block_and_autostart_are_migrated(tmp_path, hypr):
    (hypr / "bindings.lua").write_text(
        '-- ── Touch Bar (macarchy-dfr)\nfor _, b in ipairs({}) do\nend\nkeep = 1\n')
    (hypr / "autostart.lua").write_text(
        'o.exec_on_start("systemctl --user start macarchy-dfr.service")\n')
    run(tmp_path)
    assert (hypr / "bindings.lua").read_text() == "keep = 1\n"
    assert "macarchy-dfr" not in (hypr / "autostart.lua").read_text()
    assert "macarchy-touchbar.service" in (hypr / "autostart.lua").read_text()


def test_missing_hypr_dir_is_not_an_error(tmp_path):
    assert "skipping" in run(tmp_path).stdout
