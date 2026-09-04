"""The PKGBUILD must land everything install.sh lands.

Two install channels that drift apart are worse than one: the package would
install cleanly and be missing a file nobody notices until the daemon needs it.
So this reads both and asserts they agree on WHAT is installed, not on where —
install.sh works in $HOME, the package works in /usr. macarchy-install#16.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKGBUILD = (ROOT / "PKGBUILD").read_text()
# Comments mention every artefact by name, so a substring match over the whole
# file passes even when the install line is gone. Match the code.
PKG_CODE = "\n".join(l for l in PKGBUILD.splitlines() if not l.lstrip().startswith("#"))
INSTALL = (ROOT / "install.sh").read_text()

# What install.sh actually COPIES onto the machine. The package must carry each
# one too; only the destination differs ($HOME versus /usr).
INSTALLED = [
    "bin/macarchy-touchbar",
    "udev/70-macarchy-touchbar.rules",
    "modules-load.d/macarchy-touchbar.conf",
    "systemd/macarchy-touchbar.service",
    "MaterialSymbolsRounded",
]

# What install.sh does NOT copy, because the daemon reads it in place from the
# checkout: the python package itself, modules/ and config/. That asymmetry IS
# the packaging bug — a package has nowhere to read "in place" from, which is
# why paths.data_root() exists. So the PKGBUILD must carry them and install.sh
# never will.
USED_IN_PLACE = ["macarchy_touchbar", "modules", "config"]
ARTEFACTS = INSTALLED + USED_IN_PLACE


def test_the_package_carries_everything_install_sh_does():
    missing = [a for a in ARTEFACTS if a not in PKG_CODE]
    assert not missing, f"install.sh installs {missing}; PKGBUILD does not mention them"


def test_install_sh_still_installs_what_this_test_claims():
    # The other half of the drift guard: if install.sh stops shipping one of
    # these, the list above is stale and the first assertion checks a fiction.
    for a in INSTALLED:
        stem = a.split("/")[-1]
        assert stem in INSTALL, f"{a} is in INSTALLED but install.sh no longer mentions it"


def test_the_in_place_data_really_is_read_through_data_root():
    # USED_IN_PLACE is only correct while the daemon resolves those directories
    # rather than assuming the checkout. If that regressed, the package would
    # ship files nothing reads.
    daemon = (ROOT / "macarchy_touchbar" / "daemon.py").read_text()
    assert "data_root()" in daemon
    assert 'os.path.dirname(os.path.dirname(os.path.abspath(__file__)))' not in daemon


def test_the_font_is_pinned_with_a_checksum():
    # install.sh curls it from master, unpinned: the file changed between 2 Sep
    # and 5 Sep. A package must be reproducible, so the URL carries a commit and
    # the source carries a real sha256 rather than SKIP.
    assert re.search(r"raw\.githubusercontent\.com/google/material-design-icons/[0-9a-f]{40}/", PKG_CODE)
    sums = re.search(r"sha256sums=\((.*?)\)", PKG_CODE, re.S).group(1).split()
    assert len(sums) == 3, "expected three sources: the tarball, the font and its codepoints"
    assert any(re.fullmatch(r"'[0-9a-f]{64}'", s) for s in sums), "the font must carry a real checksum"


def test_site_packages_is_derived_not_hardcoded():
    # It carries the interpreter version (python3.14 today).
    # No site-packages at all now: the python package is co-located with its
    # data under /usr/share, which is what keeps arch=('any') honest.
    assert "sysconfig" not in PKG_CODE
    assert "site-packages" not in PKG_CODE
    assert not re.search(r"python3\.\d", PKG_CODE)


def test_the_package_is_arch_independent():
    assert "arch=('any')" in PKG_CODE


def test_pkgver_is_maintained_by_release_please():
    # Without the marker, release-please stops bumping pkgver and a release
    # ships a package whose version is the previous tag's — silently.
    assert "x-release-please-version" in PKG_CODE
    cfg = json.loads((ROOT / "release-please-config.json").read_text())
    assert "PKGBUILD" in cfg["packages"]["."]["extra-files"]


def test_the_codepoints_are_shipped_and_not_skipped():
    # draw.py:57 opens them; they are gitignored so they are absent from the
    # release tarball. A `|| true` here would ship a bar with no icons.
    assert "codepoints" in PKG_CODE
    assert "|| true" not in PKG_CODE, "a silent skip in package()"


def test_the_package_job_lives_where_it_will_actually_fire():
    # A `release: [published]` trigger never fires on the real path: release-please
    # creates the Release with GITHUB_TOKEN, and GitHub raises no workflow run from
    # a GITHUB_TOKEN event. The job has to hang off release-please's own output.
    assert not (ROOT / ".github" / "workflows" / "package.yml").exists()
    wf = (ROOT / ".github" / "workflows" / "release-please.yml").read_text()
    assert "release_created" in wf
    assert "types: [published]" not in wf


def test_the_upload_globs_and_clobbers():
    wf = (ROOT / ".github" / "workflows" / "release-please.yml").read_text()
    assert "*.pkg.tar.*" in wf, "hardcoding an extension uploads nothing when PKGEXT differs"
    assert "--clobber" in wf, "a re-run must replace the asset, not fail"


def test_the_package_job_builds_the_tag_not_the_branch():
    # Without an explicit ref a manual re-run checks out the default branch and
    # clobbers an old release with a package built from a different tag.
    wf = (ROOT / ".github" / "workflows" / "release-please.yml").read_text()
    assert "ref: ${{ needs.release-please.outputs.tag_name" in wf
    assert "github-cli" in wf, "gh lives on the runner, not inside the container"
    assert "pacman -Syu" in wf, "a partial upgrade reads as a build bug"


def test_the_unit_is_repointed_away_from_HOME():
    # The shipped unit says %h/.local/bin/… because install.sh symlinks there; a
    # package install writes nothing into $HOME, so shipping it verbatim gives
    # 203/EXEC and ten restarts from a package that installed perfectly.
    assert "%h/" in (ROOT / "systemd" / "macarchy-touchbar.service").read_text()
    assert "sed 's|%h/" in PKG_CODE and "/usr/bin/" in PKG_CODE


def test_there_is_a_scriptlet_for_what_pacman_cannot_do():
    # usermod -aG video, modprobe uinput and masking tiny-dfr are install.sh's
    # non-file half. pacman does none of it; silence would leave a blank bar.
    assert "install=macarchy-touchbar.install" in PKG_CODE
    s = (ROOT / "macarchy-touchbar.install").read_text()
    for step in ("video", "uinput", "tiny-dfr"):
        assert step in s
