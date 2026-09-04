# docs/media

## touchbar.gif

Six frames of the real engine, captured with no Touch Bar involved. The daemon draws
into an in-memory cairo surface (`--headless`), `screenshot` writes that surface out,
and `touch` feeds a synthetic gesture through the same recognizer the hardware uses —
so the bar in the GIF went through exactly the code path the panel does.

To reproduce it, point the daemon's runtime and config at throwaway directories so it
cannot collide with a Touch Bar daemon already running for your session (they would
otherwise bind the same socket):

```bash
rt=$(mktemp -d /tmp/dfr.XXXX)          # must be short: AF_UNIX paths cap at ~108 bytes
cfg=$(mktemp -d) frames=$(mktemp -d)
export XDG_RUNTIME_DIR=$rt XDG_CONFIG_HOME=$cfg XDG_STATE_HOME=$cfg

./bin/macarchy-dfr daemon --headless --config config/layouts.toml &
until [ -S "$rt/macarchy-dfr/sock" ]; do sleep 0.2; done

./bin/macarchy-dfr screenshot "$frames/1.png"
./bin/macarchy-dfr touch 1420,30                      # the media group's pill
./bin/macarchy-dfr screenshot "$frames/2.png"
./bin/macarchy-dfr touch 1557,30                      # display
./bin/macarchy-dfr screenshot "$frames/3.png"
./bin/macarchy-dfr touch 1693,30                      # system
./bin/macarchy-dfr screenshot "$frames/4.png"
./bin/macarchy-dfr touch 70,30                        # the group's close button
./bin/macarchy-dfr screenshot "$frames/5.png"
kill %1
```

With `$XDG_RUNTIME_DIR/hypr` symlinked at the real one, the headless daemon also picks
up the focused window and switches layouts, read-only — that is how the second frame
(the terminal layout) was taken.

Then repeat each frame to give it a dwell time and stitch at a slow frame rate:

```bash
ffmpeg -framerate 2 -i seq/%03d.png \
  -vf "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=none" \
  -loop 0 touchbar.gif
```
