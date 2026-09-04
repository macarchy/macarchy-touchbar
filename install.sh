#!/usr/bin/env bash
# Install macarchy-dfr: the daemon that owns the Touch Bar. Re-run to update.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ${1:-} == --uninstall ]]; then
	systemctl --user disable --now macarchy-dfr.service 2>/dev/null || true
	rm -f "$HOME/.config/systemd/user/macarchy-dfr.service" "$HOME/.local/bin/macarchy-dfr"
	systemctl --user daemon-reload
	pkexec bash -c 'systemctl unmask tiny-dfr || true; systemctl enable --now tiny-dfr || true' || true
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

# 3. hardware access without root: video group for the Touch Bar's DRM card,
#    uinput for the keyboard; tiny-dfr out of the way
pkexec bash -c "
	usermod -aG video $USER
	install -m 644 '$PWD/udev/70-macarchy-dfr.rules' /etc/udev/rules.d/
	install -m 644 '$PWD/modules-load.d/macarchy-dfr.conf' /etc/modules-load.d/
	modprobe uinput
	udevadm control --reload && udevadm trigger --subsystem-match=misc
	systemctl disable --now tiny-dfr 2>/dev/null; systemctl mask tiny-dfr
"

# 3b. Hyprland: drop the old omarchy-dfr bindings, autostart the user service instead
python3 - <<'HYPRMIG'
import os

home = os.path.expanduser("~")
changed = []

bindings = os.path.join(home, ".config", "hypr", "bindings.lua")
MARK = "-- ── Touch Bar (omarchy-dfr)"
try:
    lines = open(bindings).read().splitlines(keepends=True)
except OSError:
    lines = []
start = next((i for i, l in enumerate(lines) if l.strip() == MARK), None)
if start is not None:
    stop = next((j for j in range(start + 1, len(lines)) if lines[j].strip() == "end"), None)
    if stop is None:
        changed.append(f"{bindings}: omarchy-dfr block found but no closing 'end'; left alone")
    else:
        del lines[start:stop + 1]
        with open(bindings, "w") as f:
            f.write("".join(lines))
        changed.append(f"{bindings}: removed the omarchy-dfr Touch Bar bindings")

autostart = os.path.join(home, ".config", "hypr", "autostart.lua")
OLD = 'o.exec_on_start("omarchy-dfr daemon")'
NEW = 'o.exec_on_start("systemctl --user start macarchy-dfr.service")'
COMMENT = ("-- The Touch Bar (macarchy-dfr): a systemd user service, so it restarts "
           "on failure and logs to the journal.")
try:
    lines = open(autostart).read().splitlines(keepends=True)
except OSError:
    lines = []
i = next((k for k, l in enumerate(lines) if OLD in l), None)
if i is not None:
    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    lines[i] = indent + NEW + "\n"
    if i and lines[i - 1].lstrip().startswith("--"):
        lines[i - 1] = indent + COMMENT + "\n"
    with open(autostart, "w") as f:
        f.write("".join(lines))
    changed.append(f"{autostart}: autostart the macarchy-dfr user service")

else:
    # Nothing to migrate: a machine that never ran omarchy-dfr. The unit is
    # enabled and starts with graphical-session.target anyway, but the
    # explicit line is what the rest of the setup (and its doctor) expects.
    text = "".join(lines)
    if NEW not in text:
        with open(autostart, "a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "")
                    + COMMENT + "\n" + NEW + "\n")
        changed.append(f"{autostart}: autostart the macarchy-dfr user service")

print("\n".join(changed) if changed else "Hyprland config: nothing to migrate.")
HYPRMIG
command -v hyprctl >/dev/null 2>&1 && hyprctl reload >/dev/null 2>&1 || true

# 4. CLI symlink, config, user unit
mkdir -p "$HOME/.local/bin" "$HOME/.config/macarchy-dfr" "$HOME/.config/systemd/user"
ln -sf "$PWD/bin/macarchy-dfr" "$HOME/.local/bin/macarchy-dfr"
[[ -e "$HOME/.config/macarchy-dfr/layouts.toml" ]] || cp config/layouts.toml "$HOME/.config/macarchy-dfr/"
cp systemd/macarchy-dfr.service systemd/macarchy-dfr-failed.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable macarchy-dfr.service

if id -nG | grep -qw video; then
	systemctl --user restart macarchy-dfr.service
	echo "macarchy-dfr is running."
else
	echo "You were added to the 'video' group: log out and back in, then macarchy-dfr starts with your session."
fi
