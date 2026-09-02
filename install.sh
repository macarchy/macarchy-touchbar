#!/usr/bin/env bash
# Install macarchy-dfr: the daemon that owns the Touch Bar. Re-run to update.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ${1:-} == --uninstall ]]; then
	systemctl --user disable --now macarchy-dfr.service 2>/dev/null || true
	rm -f "$HOME/.config/systemd/user/macarchy-dfr.service" "$HOME/.local/bin/macarchy-dfr"
	systemctl --user daemon-reload
	pkexec bash -c 'systemctl unmask tiny-dfr; systemctl enable --now tiny-dfr'
	echo "macarchy-dfr removed; tiny-dfr is back. Your layouts.toml was kept."
	exit 0
fi

# 1. packages (aarch64: everything here is in extra)
need=()
for p in python-cairo python-gobject papirus-icon-theme brightnessctl; do
	pacman -Qi "$p" >/dev/null 2>&1 || need+=("$p")
done
if ((${#need[@]})); then
	pkexec pacman -S --needed --noconfirm "${need[@]}"
fi

# 2. Material Symbols Rounded (variable font, 15 MB, Apache 2.0) — not committed
base='https://raw.githubusercontent.com/google/material-design-icons/master/variablefont'
mkdir -p fonts "$HOME/.local/share/fonts"
[[ -s fonts/MaterialSymbolsRounded.ttf ]] || curl -fsSL "$base/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf" -o fonts/MaterialSymbolsRounded.ttf
[[ -s fonts/MaterialSymbolsRounded.codepoints ]] || curl -fsSL "$base/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.codepoints" -o fonts/MaterialSymbolsRounded.codepoints
cp fonts/MaterialSymbolsRounded.ttf "$HOME/.local/share/fonts/"
fc-cache -f >/dev/null

# 3. hardware access without root: video group for card3, uinput for the keyboard; tiny-dfr out of the way
pkexec bash -c "
	usermod -aG video $USER
	install -m 644 '$PWD/udev/70-macarchy-dfr.rules' /etc/udev/rules.d/
	udevadm control --reload && udevadm trigger --subsystem-match=misc
	systemctl disable --now tiny-dfr 2>/dev/null; systemctl mask tiny-dfr
"

# 4. CLI symlink, config, user unit
mkdir -p "$HOME/.local/bin" "$HOME/.config/macarchy-dfr" "$HOME/.config/systemd/user"
ln -sf "$PWD/bin/macarchy-dfr" "$HOME/.local/bin/macarchy-dfr"
[[ -e "$HOME/.config/macarchy-dfr/layouts.toml" ]] || cp config/layouts.toml "$HOME/.config/macarchy-dfr/"
cp systemd/macarchy-dfr.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable macarchy-dfr.service

if id -nG | grep -qw video; then
	systemctl --user restart macarchy-dfr.service
	echo "macarchy-dfr is running."
else
	echo "You were added to the 'video' group: log out and back in, then macarchy-dfr starts with your session."
fi
