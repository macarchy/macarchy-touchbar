"""Where the daemon's data lives.

modules/, config/layouts.toml and fonts/*.codepoints sit one directory above the
python package. That was already true in a git checkout, and the packaging work
kept it true rather than inventing a second layout: the package installs
macarchy_touchbar/ NEXT TO modules/ and config/ under /usr/share/macarchy-touchbar,
so "one level up from the code" resolves correctly in both.

Co-locating them is what makes arch=('any') honest. Putting the python package in
site-packages instead would bake the building interpreter's version into the
artifact, and a target whose python differs by a minor version gets ImportError
while depends=('python') claims to be satisfied. macarchy-install#16.

$MACARCHY_TOUCHBAR_DATA overrides, and is honoured even when it points nowhere:
someone who sets it meant it, and a silent fallback would hide the typo until the
bar came up with no modules on it.
"""
import os


def data_root():
    return os.environ.get("MACARCHY_TOUCHBAR_DATA") or \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
