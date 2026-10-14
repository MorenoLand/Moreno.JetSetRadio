# Jet Set Radio

A port of Jet Set Radio (the Xbox 360 arcade release) to Redot / Godot. It reads the game's files from your own copy of the game;
no game data is included in this repository.

Work in progress. The front end runs (title, garage, area map, loading) and you can skate around a stage as any of the ten
characters; missions, tricks and graffiti are not there yet.

## What is here

- `tools/stfs.py` unpacks the Xbox 360 package.
- `tools/xex.py` unpacks the game executable into a memory image and function table.
- `tools/manifest.py` reads the archive partition tables and load lists from that image.
- `tools/afs.py`, `tools/pvr.py`, `tools/ninja.py` and `tools/glb.py` read archives, textures and models and write glTF.
- `tools/texbind.py` works out which pack texture goes into which slot of a texture list.
- `tools/layout.py` reads where each object of a stage is placed; `tools/mission.py` reads where the missions put vehicles.
- `tools/extract.py` converts the stage geometry into `assets/`.
- `tools/interface.py` and `tools/skaters.py` convert the menu screens and the characters, `tools/items.py` the spray cans; `tools/audio.py` and `tools/sosb.py` extract the music and sound.
- `tools/motion.py`, `tools/rig.py`, `tools/scene.py` and `tools/arc.py` are the libraries behind them.
- `tools/ghidra/` has the scripts that set the image up for analysis in Ghidra.
- [docs/formats.md](docs/formats.md) describes what is known about the data files, [docs/screens.md](docs/screens.md) how the
  screens are put together.
- `scenes/main.tscn` is the start scene; it starts the game when extracted assets exist (`-- --viewer` opens the model viewer).

See [docs/tools.md](docs/tools.md) for usage.

## Setup

Python 3.11 or newer and Redot 26.2. The tools use the standard library only.

```
python tools/stfs.py "path/to/package" --extract build/xbla
python tools/xex.py build/xbla/default.xex --out build/exe
python tools/manifest.py build/exe/image.bin --out build/exe
python tools/extract.py
python tools/interface.py
python tools/skaters.py
python tools/items.py
python tools/graffiti.py                      # the pictures that can be sprayed
python tools/gestures.py "path/to/PC release"   # the spraying gestures (optional)
python tools/audio.py
python tools/sosb.py --export
python tools/pcdata.py "path/to/PC release"      # logos, rating screens, menu art, menu texts (strings.json) and videos (optional)
python tools/demos.py "path/to/PC release"       # the recorded demonstrations that play on the title (optional)
python tools/fnt.py "path/to/PC release/CUSTOM/FONTS.ARC"   # menu and subtitle fonts (optional)
python tools/comic.py --demo 30                  # the picture-strip scene of the opening (optional)
```

These write into `build/` and `assets/`, which are ignored by git. Then open this folder with Redot and run the main scene.

## Playing

| Input | Action |
| --- | --- |
| arrow keys / W A S D, or the left stick | move the cursor, skate |
| Enter / Space, or A | confirm, jump |
| Shift, or X | boost |
| C or Z, or the right shoulder button | spray (near a graffiti spot) |
| Escape / Backspace, or B | back |
| Q / E, R / F, right stick, right mouse button | turn the camera in a stage |
| M, Tab or Y | in the garage: choose the area on the map (F1 + confirm does too) |
| F1 | debug: text strip, zone volumes, what the skater ran into |
| `[` `]` | with F1 on: step through the character's motions in a stage |
| `,` `.` `/` | with F1 on: sound test, previous / next / again of the bank sounds and effect files |

Arguments after `--` for testing: `--screen=title|garage|loading|stage`, `--stage=N`, `--character=ID`, `--keys=confirm@1.5,...`
(presses), `--hold=up@4` (holds an action from then on), `--shot=PATH --wait=SECONDS`, `--spawn=X,Y,Z[,YAW]`, `--debug` (starts with F1 on), `--trace`
(prints the skater's position every half second). Setting `JETSET_ASSETS` to a folder uses the exported files from there.

## Viewer

| Input | Action |
| --- | --- |
| W A S D, Q / E | move, down / up (Shift is faster) |
| arrow keys, or drag with a mouse button | look |
| number keys, `[` `]` or the list at the top right | switch stage |
| R | reset the view |
| B | show or hide the far backdrop |
| C | draw both sides of every face |
| T | textures on or off |
| F1 | show or hide the key help |

## Tests

```
redot --headless --path . -s res://tests/smoke_boot.gd
```
