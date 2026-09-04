"""Where the daemon's data lives.

modules/, config/layouts.toml and fonts/*.codepoints used to be found at
`os.path.dirname(os.path.dirname(__file__))` — one directory above the python
package. That is the repo root in a git checkout and nothing useful anywhere
else: installed as a system package, macarchy_touchbar/ sits in site-packages/,
so the daemon looked for modules/ in /usr/lib/pythonX.Y/site-packages/.
macarchy-install#16.

Three candidates, in order:

  1. $MACARCHY_TOUCHBAR_DATA — honoured even when it does not exist. Someone who
     sets it meant it, and falling back would hide their typo until the bar came
     up empty.
  2. /usr/share/macarchy-touchbar — a package's data, used only if really there.
  3. the checkout root — the old behaviour, and still the common one.
"""
import os

PACKAGED = "/usr/share/macarchy-touchbar"
_CHECKOUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root():
    override = os.environ.get("MACARCHY_TOUCHBAR_DATA")
    if override:
        return override
    if os.path.isdir(os.path.join(PACKAGED, "modules")):
        return PACKAGED
    return _CHECKOUT
