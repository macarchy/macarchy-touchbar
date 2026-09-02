# fonts/

Icon font used by `macarchy_dfr/draw.py`, downloaded at setup time (not committed —
15 MB, `fonts/*.ttf` and `fonts/*.codepoints` are git-ignored).

## Material Symbols Rounded

Source: [google/material-design-icons](https://github.com/google/material-design-icons)
(Apache License 2.0), variable font build.

```bash
mkdir -p fonts && cd fonts
base='https://raw.githubusercontent.com/google/material-design-icons/master/variablefont'
curl -fsSL "$base/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf" -o MaterialSymbolsRounded.ttf
curl -fsSL "$base/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.codepoints" -o MaterialSymbolsRounded.codepoints
mkdir -p ~/.local/share/fonts && cp MaterialSymbolsRounded.ttf ~/.local/share/fonts/ && fc-cache -f
fc-list | grep -c "Material Symbols Rounded"
```

`install.sh` (task 20) will repeat these steps for a fresh install. The `.codepoints`
file maps icon names (e.g. `brightness_high`) to hex codepoints, read by
`icon_codepoint()` in `macarchy_dfr/draw.py`.
