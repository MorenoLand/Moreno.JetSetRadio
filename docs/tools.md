# Tools

The repository contains no game data. These tools read your own copy of the game and write only into `build/` and `assets/`,
both ignored by git. Python 3.11 or newer; standard library only.

## stfs.py

Lists and unpacks an Xbox 360 STFS package, the container the game is distributed in.

```
python tools/stfs.py PACKAGE
python tools/stfs.py PACKAGE --extract DIR
python tools/stfs.py PACKAGE --extract DIR --only "DATA_BE/JETRADIO/*.AFS"
```

`PACKAGE` is the long hex-named file inside `<title id>/000D0000/`. Without `--extract` it prints the header and the file list.
`--only` takes a glob on the path inside the package and can be repeated. Paths that would leave `DIR` are refused.

The unpacked game has these parts:

| Path | Contents |
| --- | --- |
| `default.xex` | the executable |
| `DATA_BE/JETRADIO/` | `.AFS` archives and `.OFS` index files, the game data |
| `DATA_BE/VIDEOS/` | `.wmv` movies and `.srt` subtitles |
| `CUSTOM/` | `.ARC` archives, `STRINGS.STR`, instruction and credits text |

## xex.py

Unpacks an XEX2 executable: decrypts it, decompresses it and checks the result.

```
python tools/xex.py build/xbla/default.xex --out build/exe
```

| Output | Contents |
| --- | --- |
| `image.bin` | the executable as it sits in memory, to be loaded at `0x82000000` (big-endian PowerPC) |
| `functions.tsv` | function table: address, size in bytes, prolog length |
| `imports.tsv` | import slots and thunks: address, kind, library, ordinal |
| `xex_info.json` | headers, sections, import counts and the results of the checks |

It checks the SHA-1 of every compressed block, that the page types match the sections, and that the function table agrees with the
code. The exit code is 0 only if all of those pass. The per-page digests stored in the file are not checked.

## manifest.py

Reads the archive partition tables and the load lists out of the unpacked image (see [formats.md](formats.md)).

```
python tools/manifest.py build/exe/image.bin --out build/exe
```

| Output | Contents |
| --- | --- |
| `partitions.tsv` | slot, partition number, archive name, member count |
| `load_lists.tsv` | list address, record index, partition, member, destination, base address, descriptor, count, type, tag, flags |

The addresses it reads are those of the retail executable; it stops with an error if the image looks different.

## afs.py, pvr.py

```
python tools/afs.py build/xbla/DATA_BE/JETRADIO/STAGE1.AFS            # list members
python tools/pvr.py build/xbla/DATA_BE/JETRADIO/STAGE1TXP_ALL.AFS --check   # decode every texture, report problems
python tools/pvr.py build/xbla/DATA_BE/JETRADIO/STAGE1TXP_ALL.AFS --out build/tex   # write PNG files
```

## texbind.py

Prints, for a texture list, the pack texture that fills each slot (see [formats.md](formats.md)). Needs `build/exe` and the
unpacked package.

```
python tools/texbind.py --list 82CB5808
```

## layout.py

Prints how many objects of each stage have a placement and the extent they cover (see [formats.md](formats.md)). The
tables it reads are in the executable image.

```
python tools/layout.py --stage 1
```

## mission.py

Prints, per stage, the mission sets that belong to it and its vehicle spawn points (see [formats.md](formats.md)); `cans()` reads
the spray can records.

```
python tools/mission.py --stage 1
```

## extract.py

Converts stage geometry into glTF files under `assets/models/` and writes `assets/index.json`, which the viewer reads. Next to
each stage it writes lineups of the vehicles (`stage<N>_vehicles.glb`) and of the people (`stage<N>_people.glb`) of the stage,
and `assets/stages.json` with the place where the missions of each stage begin.

```
python tools/extract.py                # stages 1 2 3 5 6
python tools/extract.py --stage 3      # one stage (the last stage has no placement tables yet: --stage last)
```

Options: `--game DIR` (unpacked package, default `build/xbla`), `--exe DIR` (default `build/exe`), `--out DIR` (default
`assets`), `--flip-z` to mirror the geometry.

Besides `stage<N>.glb` it writes `stage<N>_zones.glb` for the stages that have volume chunks (types 56 to 58 in the objects of
the placement family with no texture list; stages 1, 2 and 5): large convex columns, not walls (see formats.md), kept for
inspection, and `assets/stages.json` with the places missions start at and the spray cans.

## interface.py

Writes the menu screens: the title, the garage, the loading screen and the in-game display. The 3D parts become glTF files
with a joint hierarchy, a skin and animations; the 2D parts become sheets and a list of sprites.

```
python tools/interface.py
```

| Output | Contents |
| --- | --- |
| `assets/models/title.glb`, `loading.glb`, `garage.glb` | the 3D parts; one animation per object motion |
| `assets/ui/<screen>_<n>.png` | the texture sheets of each screen |
| `assets/screens.json` | per screen: trees and their animations, cameras, camera slots, sprites (position, size, texture rectangle) |

The addresses of the executable's tables that tell which tree, texture list and motion belong together are constants at the top
of the script; [screens.md](screens.md) says what they are.

## skaters.py

Writes the 16 characters of `PLAYER.AFS` as skinned glTF files with their 176 motions (`m000`, `m001` ...). Every motion
keys every joint (a channel the game leaves out is written with the object's own value), so that switching between motions in an
engine that keeps the last value does not leave a joint where the previous motion put it.

```
python tools/skaters.py              # assets/models/skaters/<name>.glb and assets/skaters.json
python tools/skaters.py --only 7     # one character by id
```

The character ids and the order of the containers come from the load lists in the executable.

## items.py

Writes `assets/models/items.glb`: the two spray cans (`can0`, `can1`) with their spin (`spin0`, `spin1`).

```
python tools/items.py
```

## sosb.py

Decodes the one-shot sound banks of `E_SND_SE.AFS` (`SND_SE.AFS` with `--archive`). `--export` writes the common bank and the banks of
the characters as WAV files to `assets/audio/sfx/` and lists them in `assets/audio/sfx.json`; without it a bank is listed on the
console and written with `--out`.

```
python tools/sosb.py --export
python tools/sosb.py --member 5 --out build/sfx
```

## motion.py, rig.py, scene.py

Libraries used by the scripts above: `motion.py` reads object motions and camera paths, `rig.py` writes a tree as a skinned mesh,
`scene.py` reads the pointer table at the start of a menu data block (trees, motions, camera paths, sprites).

## arc.py, audio.py

`arc.py` lists and extracts the `ARCB` containers of the `CUSTOM` folder; `audio.py` writes the music and the sound effects as
Ogg files under `assets/audio/` and an index `assets/audio.json`.

```
python tools/arc.py build/xbla/CUSTOM/MUSIC.ARC            # list
python tools/audio.py                                      # assets/audio/music, assets/audio/sounds
```

## spots.py / graffiti.py

`spots.py` finds the graffiti spots of the stages (their layout is in the header of the tool); `extract.py` writes them to
`assets/stages.json` (`spots`: size class, position, the points the skater stands on while spraying, the quad the picture
is drawn on). `graffiti.py` writes the 111 pictures of `E_GRF.AFS` as PNG files and `assets/graffiti.json`. In a stage,
the skater presses spray near a spot (`C`, `Z` or the right shoulder button) and the picture appears when the points are done.

## gestures.py

Reads the tables of the spraying gestures, the per character parameters (size class of the gestures, most spray cans) and the
spraying motion numbers from the PC release's executable and writes `assets/gestures.json`. The code that uses them is
described in the header of the tool; `scripts/game/stage.gd` ports the state machine.

```
python tools/gestures.py "path/to/PC release"
```

## fnt.py

Reads the bitmap fonts (`FNT1`) of the PC release's `FONTS.ARC` and writes `assets/fonts/<name>.png` (white letters, dark
edge) and `<name>.json` (line height, `glyphs`: character code to x offset, advance, rectangle). See the header of the
tool for the layout. `scripts/core/bitmap_text.gd` draws text with them.

```
python tools/fnt.py "path/to/PC release/CUSTOM/FONTS.ARC"
```

## comic.py

Exports the picture-strip scenes of the story (`DEMO30.AFS`, the opening): one node per page of the strip in
`assets/models/comic_30.glb`, the camera path of each page and the subtitle lines (five languages) in
`assets/comic.json`. `scripts/screens/cutscene.gd` plays it.

```
python tools/comic.py --demo 30
```

## ghidra/

Ghidra scripts for the unpacked image. Import `image.bin` as a raw binary at `0x82000000` with the language
`PowerPC:BE:64:A2ALT-32addr`, set it up, store the analysis options, and only then analyse. That is three runs of
`analyzeHeadless`:

```
analyzeHeadless build/ghidra jsr -import build/exe/image.bin -loader BinaryLoader -loader-baseAddr 0x82000000 \
	-processor PowerPC:BE:64:A2ALT-32addr -scriptPath tools/ghidra -noanalysis \
	-preScript SetupImage.java build/exe/functions.tsv build/exe/imports.tsv \
	-preScript AnalysisOptions.java
analyzeHeadless build/ghidra jsr -process image.bin
analyzeHeadless build/ghidra jsr -process image.bin -noanalysis -scriptPath tools/ghidra -postScript NameFromStrings.java
```

| Script | What it does |
| --- | --- |
| `SetupImage.java` | splits the image into one memory block per PE section, creates the functions from `functions.tsv`, names the import slots and thunks `<library>_<ordinal>` |
| `AnalysisOptions.java` | turns off the non-returning function analyzer, which otherwise deletes the code of about a fifth of the functions; the setting only applies to the next run, hence the separate analysis step |
| `NameFromStrings.java` | run after analysis; names functions after `Class::method` assertion strings and `name: ...` trace messages they use |

Ghidra's stock PowerPC definition does not know the Xbox 360's VMX128 vector instructions, so functions that use them are only
partly disassembled.
