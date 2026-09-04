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
    missing = [a for a in ARTEFACTS if a not in PKGBUILD]
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
    assert re.search(r"raw\.githubusercontent\.com/google/material-design-icons/[0-9a-f]{40}/", PKGBUILD)
    sums = re.search(r"sha256sums=\((.*?)\)", PKGBUILD, re.S).group(1).split()
    assert len(sums) == 3, "expected three sources: the tarball, the font and its codepoints"
    assert any(re.fullmatch(r"'[0-9a-f]{64}'", s) for s in sums), "the font must carry a real checksum"


def test_site_packages_is_derived_not_hardcoded():
    # It carries the interpreter version (python3.14 today).
    assert "python3." not in PKGBUILD.replace("python3 ", "")
    assert "sysconfig" in PKGBUILD


def test_the_package_is_arch_independent():
    assert "arch=('any')" in PKGBUILD


def test_pkgver_is_maintained_by_release_please():
    # Without the marker, release-please stops bumping pkgver and a release
    # ships a package whose version is the previous tag's — silently.
    assert "x-release-please-version" in PKGBUILD
    cfg = json.loads((ROOT / "release-please-config.json").read_text())
    assert "PKGBUILD" in cfg["packages"]["."]["extra-files"]


def test_the_codepoints_are_shipped_and_not_skipped():
    # draw.py:57 opens them; they are gitignored so they are absent from the
    # release tarball. A `|| true` here would ship a bar with no icons.
    assert "codepoints" in PKGBUILD
    code = [l for l in PKGBUILD.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in code if "|| true" in l], "a silent skip in package()"


def test_the_workflow_only_runs_on_a_published_release():
    # The PKGBUILD's source is the release tarball, which does not exist before
    # the tag does — a push or pull_request trigger could only ever fail.
    wf = (ROOT / ".github" / "workflows" / "package.yml").read_text()
    assert "release:" in wf and "types: [published]" in wf
    code = [l for l in wf.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in code if l.strip() in ("push:", "pull_request:")]


def test_the_upload_globs_and_clobbers():
    wf = (ROOT / ".github" / "workflows" / "package.yml").read_text()
    assert "*.pkg.tar.*" in wf, "hardcoding an extension uploads nothing when PKGEXT differs"
    assert "--clobber" in wf, "a re-run must replace the asset, not fail"
