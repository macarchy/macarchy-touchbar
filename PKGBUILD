# Maintainer: Philippe Matray <phmatray@gmail.com>
#
# Installs system-wide what ./install.sh installs into $HOME. The two channels
# are kept honest by tests/test_pkgbuild.py, which fails if either grows a file
# the other does not carry.
pkgname=macarchy-touchbar
# Rewritten from the tag by the packaging job before makepkg runs, so the built
# package can never disagree with the release it is attached to. The value here
# is the fallback for a manual `makepkg` from a checkout; release-please used to
# maintain it through extra-files, which made it fail to build a release PR at all
# ("unexpected token '(' at 6:32"). One less coupling.
pkgver=0.4.0
pkgrel=1
pkgdesc="A Touch Bar daemon for MacBooks on Linux — draws every pixel over DRM, follows the focused app, takes modules"
arch=('any')
url="https://github.com/macarchy/macarchy-touchbar"
license=('MIT')
install=macarchy-touchbar.install
depends=('python' 'python-cairo' 'python-gobject' 'brightnessctl')
optdepends=('papirus-icon-theme: application icons on the bar'
            'tiny-dfr: what install.sh --uninstall hands the bar back to')
# install.sh:27 curls this from master, unpinned -- the file changed between
# 2 Sep and 5 Sep 2026. A package has to be reproducible, so the commit is
# pinned and the checksum is real.
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz"
        "MaterialSymbolsRounded.ttf::https://raw.githubusercontent.com/google/material-design-icons/0cbb08816df07faaae3dca060d4ebb10b66c214f/variablefont/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf"
        "MaterialSymbolsRounded.codepoints::https://raw.githubusercontent.com/google/material-design-icons/0cbb08816df07faaae3dca060d4ebb10b66c214f/variablefont/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.codepoints")
sha256sums=('SKIP'
            '24f9f678388abc5a0e2c5bf722eeab7aea08a0a058459920d5eb117bf0f8557b'
            'cbea7bfbd34d1d4f8dd2628c34587e447f935cf4f2219b264988da48736eca75')

package() {
  cd "$srcdir/$pkgname-$pkgver"

  install -Dm755 bin/macarchy-touchbar "$pkgdir/usr/bin/macarchy-touchbar"

  # Code and data together under /usr/share, NOT the python package in
  # site-packages. site-packages would bake the BUILDING interpreter's version
  # into an arch=('any') artifact: this is built in a container whose python is
  # routinely ahead of Asahi's, and the target would then get ImportError while
  # depends=('python') claims to be satisfied. Co-located, "one directory above
  # the package" resolves in both layouts and there is one rule, not two.
  install -d "$pkgdir/usr/share/$pkgname"
  cp -r macarchy_touchbar modules config "$pkgdir/usr/share/$pkgname/"

  install -Dm644 "$srcdir/MaterialSymbolsRounded.ttf" \
    "$pkgdir/usr/share/fonts/TTF/MaterialSymbolsRounded.ttf"
  # draw.py:57 opens this. It is gitignored, so it is NOT in the release tarball
  # and has to come from the same pinned commit as the font. No `|| true`: a
  # missing codepoints file means a bar with no icons, and the build should say
  # so rather than ship one.
  install -Dm644 "$srcdir/MaterialSymbolsRounded.codepoints" \
    "$pkgdir/usr/share/$pkgname/fonts/MaterialSymbolsRounded.codepoints"

  install -Dm644 udev/70-macarchy-touchbar.rules \
    "$pkgdir/usr/lib/udev/rules.d/70-macarchy-touchbar.rules"
  install -Dm644 modules-load.d/macarchy-touchbar.conf \
    "$pkgdir/usr/lib/modules-load.d/macarchy-touchbar.conf"
  # The shipped unit says ExecStart=%h/.local/bin/… because install.sh symlinks
  # the CLI there. A package install never writes into $HOME, so shipping it
  # verbatim would give 203/EXEC, ten restarts to StartLimitBurst, and an
  # OnFailure toast -- from a package that installed perfectly.
  sed 's|%h/\.local/bin/|/usr/bin/|' systemd/macarchy-touchbar.service \
    > "$srcdir/macarchy-touchbar.service.pkg"
  grep -q '^ExecStart=/usr/bin/' "$srcdir/macarchy-touchbar.service.pkg"   # or fail the build
  install -Dm644 "$srcdir/macarchy-touchbar.service.pkg" \
    "$pkgdir/usr/lib/systemd/user/macarchy-touchbar.service"

  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}
