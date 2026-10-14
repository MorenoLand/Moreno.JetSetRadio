# File formats

What is known about the game's data files so far. All offsets are in bytes; the executable image is big-endian PowerPC, the
archive tables are little-endian, and most data blobs are big-endian.

## AFS archives

The game data lives in `DATA_BE/JETRADIO/*.AFS`. An archive is:

```
0x00  "AFS\0"
0x04  u32  number of members              (little endian)
0x08  n x { u32 offset, u32 size }        (little endian)
...   zero padding; the first member starts at 0x80000
```

Members are aligned to 0x800 and are not named; they are addressed by index. A member can have size 0.
The executable keeps a table that names each archive and its member count (see Partitions below).

Archives come in language variants that carry a prefix: none (the base set), `E_`, `F_`, `G_`, `S_`. The `U_*` archives are
not used by the executable.

## Partitions and load lists

Every archive is a numbered partition (0 to 81). Six tables in the executable list the 82 partitions for each language slot
(unprefixed, `E_`, `G_`, `F_`, `S_`, and `E_` again); the partition number is the same in every slot, only the file name changes.
`tools/manifest.py` writes them to `partitions.tsv`.

What each member is, and where it is loaded, is not in the archives. It is in the executable, as "load lists": runs of 0x20-byte
records, each ending the list with a record whose first word is `0x52`:

| Word | Meaning |
| --- | --- |
| 0 | partition number |
| 1 | member index |
| 2 | destination in the game's memory window (0 = none) |
| 3 | descriptor pointer (textures only) |
| 4 | descriptor count (textures only) |
| 5 | type |
| 6 | tag for sound banks (`SOSB`, `SMSB`, `SMPB`, `SFPB`, `SFOB`) |
| 7 | flags |

Types: 0 and 1 texture packs, 2 and 3 plain data, 4 and 5 sound banks, 6 `PLAY` (character model container), 7 `PTEX`
(character texture container), 8 `XTFE` (effect textures). `tools/manifest.py` writes the lists to `load_lists.tsv`.

## Pointers and `.OFS` files

Data that contains pointers stores them as Dreamcast addresses (`0x8C000000` and up, big endian). A blob is meant to sit at a
fixed address: the destination in its load record maps to a base address by

```
base = 0x8C000000 | (destination & 0x01FFFFFF)        # destination 0x20F00000 -> base 0x8CF00000
```

and a pointer `p` inside the blob refers to byte `p - base` of the blob. Pointers that point outside the blob refer to other
blobs loaded in the same scene.

A `.OFS` file next to an archive lists which words are pointers: an array of little-endian u32, ascending, each an absolute
offset into the `.AFS` file. When there is no `.OFS`, every word in `0x8C800000..0x8CFFFFFF` is treated as a pointer.

## Textures

Texture packs hold Dreamcast PVR textures: a sequence of blocks, each

```
"GBIX"  u32 length (8)  u32 global index  u32 index again
"PVRT"  u32 length      u8 pixel format   u8 data format   u16 pad   u16 width   u16 height   data...
```

All little endian. Pixel formats are the usual PVR ones (ARGB1555, RGB565, ARGB4444, YUV422, bump, 4 and 8 bit palette). Data
formats seen as mip-mapped: 0x02, 0x04, 0x11 and 0x12. Vector-quantised data has a 256-entry codebook of 8 bytes before the
indices; pixels are stored in Morton (twiddled) order.

The length in a `PVRT` header is sometimes wrong (larger than the texture), and the blocks of a pack are 0x20-aligned, so a pack
is read by finding every `GBIX` block that is followed by `PVRT`, and a texture ends at the earlier of its stated length and
the start of the next block. Small vector-quantised textures (data formats 0x10 and 0x11) use 16, 32, 64, 128 or 256 code book
entries depending on the width and on whether mip maps are present.

### Texture lists and bindings

A model refers to a texture by a number (the 13-bit id of its texture chunk). The number is a slot of a texture list: a header
`{array pointer, count}` in the executable's data. Which pack texture fills which slot is stored in the executable, per pack,
as a *descriptor*:

- type 1 (most stage packs): pairs of `(patch array, address)`. A patch array is a list of `(list header, slot)` entries ending
  with a zero header; `address` is where one texture of the pack sits once the pack is loaded.
- type 0 (the later stages): pairs of `(record, address array)`. A record is `(list header, count)`; the addresses fill slots
  `0 .. count - 1` of that list.

The load address of a pack is not the destination of its load record, so the base is found by trying each texture start of the
member and keeping the one that puts the most addresses on texture starts. Packs of areas replace one another in the same
slots, so a stage uses one area pack for each slot.

Each object has its own list. The executable keeps, per stage, arrays of object pointers (in the host form `0x20xxxxxx`)
directly followed by an array of list headers of the same length; entry `i` of the second array is the list of object `i`.

### Material colours

A material chunk in a polygon list carries its colour as a 32-bit field. Because the list is made of 16-bit units the halves
are exchanged: read as a big-endian word the value is `0xGGBBAARR`. Colours in the vertex list are plain `0xAARRGGBB`.

## Object placement

A stage archive holds object trees modelled around their own origin (their evaluation flags usually say "ignore position,
rotation and scale"). The game places them from lists of entries, in the archive itself:

```
s32 id            -1 = unused, below -1 = end of a run
f32 x, y, z
s32 rx, ry, rz    65536 per turn
...               10 or 13 words per entry in all
```

An id selects an object pointer in an object table and a texture list in a parallel list table, both in the executable's data.
Entry lists are reached through a block table (one pointer per sector of the stage, 63 to 72 of them): either each pointer
leads to a null-terminated array of entry pointers, or to entries laid out one after another. The addresses of the block,
object and list tables are those of the retail executable and are listed in `tools/layout.py`.

The placement matrix is `T * Rz * Ry * Rx` (the point is turned about X first). Objects with their own rotation use the same
order, or Y, X, Z when the evaluation flag `0x20` is set.

Besides these lists, the game creates **props** as tasks when the player enters a block (traffic cones, bicycles, signs, bins). Their
entries have the same first seven words and ten or more in all; the object and list tables are indexed by a type number
(28 types in stage 1, up to 92 in stage 2). `tools/layout.py` reads them like the other families.

The objects of the family with no list table (stage 1: the fourth family of `layout.FAMILIES`) hold only volume chunks: convex
columns of 100 to 800 units, up to 750 units tall, placed once or up to 38 times. They are not walls the skater collides with (on
the street of stage 1 they cover a quarter of the ground, and across sidewalks and trees they blocked where nothing is drawn).
They behave like the zones of the stage's sectors; what the game uses them for is not known.

Vehicles come from the mission sets (see "Mission blocks"). Some trees are collision meshes drawn in flat debug colours; they are
left out of the exported stages.

## Character containers

`PLAY`, `PTEX` and `XTFE` start with `{tag, offset A, offset B}`; offsets are relative to the start of the member and are turned
into pointers by adding the member's address. The tags are stored in the file as `YALP`, `XETP` and `XTFE`.

`PLAY`: table A is a list of `{kind, offset}` pairs ending with kind 0. Kinds 1 and 2 are object trees (kind 1 five times, the
same figure in different states, kind 2 once), 3 is an array of 176 motion pointers for the first kind 1 tree, 4 an array of
three for the kind 2 tree, 5 and 6 are structures not read yet, 7 a list.

Table B is made of records of 35 words, ended by a record whose first word is negative (there is one record per container):

| Words | Content |
| --- | --- |
| 0 | a number (0) |
| 1 to 24 | six groups of four pointers; each group repeats one pointer (the five trees and the effect tree) |
| 25, 26 | the motion array of kind 3 and the three motions of kind 4 |
| 27, 28 | kind 5 (twice) |
| 29 | kind 6 |
| 30 to 33 | four small tables of motion numbers: `1 1 5 5 7 7`, `11 11 11 12 12 12`, `10 13 15 24`, `3 14 17 21` (Beat); what selects them is not known |
| 34 | kind 7 |

The game's loader turns the offsets into pointers by adding the address of the member and treats a zero pointer in these
records as an error. Between the small tables and the structure of kind 6 lie records that start `0x25110002, 0xFFFFFFFF` and
carry lists of frame numbers and float triples tagged `0xFF02`; they are not decoded.

Object trees use the Ninja object layout: flags, model pointer, position, angles and scale (three floats each), child and
sibling pointers (0x34 bytes). A model starts with its vertex list and polygon list pointers.

## Models

A model is a Ninja chunk model: a vertex list and a polygon list. Models in this game use only a few chunk types.

Vertex list: 32-bit words, ended by a word whose low byte is `0xFF`. Each chunk is

```
word 0   size << 16 | flags << 8 | type       size = number of words that follow
word 1   count << 16 | index offset
...      count vertices
```

Types 34 (position, 12 bytes per vertex), 35 (position and a colour word, 16), 41 (position and normal, 24) and 42 (position,
normal and a colour word, 28) occur. Strips refer to vertices by `index offset + n`.

Polygon list: 16-bit units, ended by `0xFF`. A header is `type | flags << 8`.

| Type | Meaning | Length in 16-bit units |
| --- | --- | --- |
| 0 to 5 | bits chunks (type 1 sets the alpha blend modes from the flags) | 1 |
| 8, 9 | texture id in the second word, bits 0 to 12 | 2 |
| 16 to 23 | material; one `0xAARRGGBB` word each for diffuse, ambient, specular as selected by bits 0 to 2 of `type - 16` | 2 + size |
| 56 to 58 | volume chunks (seen only as type 56, triangles of three indices); the models that carry them are large zone columns, see below | 2 + size |
| 64 | strip, no texture coordinates | 2 + size |
| 65 | strip with texture coordinates in 1/256 units | 2 + size |
| 66 | strip with texture coordinates in 1/1024 units | 2 + size |

`size` is the second 16-bit word and counts the units after it. A strip chunk has a word `userOffset << 14 | strip count` and then
the strips: a signed 16-bit length (negative means reversed winding), then per vertex a 16-bit index, a signed `u` and `v` for
types 65 and 66, and `userOffset` user-flag words.

### Shared vertices

Objects of a tree do not each have their own vertex numbers. The game keeps the vertices of the objects it has drawn in one
buffer indexed by the numbers of the vertex lists (`index offset + n`), and the strips of an object may use vertices an earlier
object of the same tree wrote there. Objects are drawn parent first, children before siblings. This is how the limbs of a
character are joined to the body: a strip of the thigh refers to vertices of the hip. Reading each model on its own leaves out
about a quarter of the triangles of a character. `ninja.read_tree` reads a tree in drawing order and records, for each vertex,
the object that wrote it, so that a skinned mesh can follow the objects.

## Object motions

Characters, the garage figures, the title and the loading screen are moved by motions of one layout (not a list of keyframes
per channel). A motion is a header of `u16 flags` (`0x0011`, or `0x0015` with scale), `u16 frames` and a `u32` pointer to a key
table. The table has one entry per object of the tree it is made for, in drawing order, and sits right before the header:

```
u32 mask       0x01 position keys, 0x10 angle keys, 0x04 scale keys
u32 position   frames * 3 floats
u32 angles     frames * 3 s16, 65536 per turn
u32 scale      frames * 3 floats
```

A channel that is missing keeps the value of the object. The key data lies before the table. In the character containers the
pointers are offsets into the member, in the scene blocks absolute addresses. Frames run at 30 per second.

When a motion is played by an engine that keeps the last value of a channel nobody sets, every channel has to be written, the
missing ones with the value of the object; otherwise whatever the previous motion left on a joint stays there.

### Character motions

A character has 176 motions of 2 to 160 frames. The root object of most of them has no angle channel, in the others the root
carries an angle of half a turn. The motions come in pairs of which the second has that half turn: the figure is the same, but it
faces the other way, which is how the game skates backwards. Motions without the half turn face the way the skater moves (the
rest pose faces +Z). A few start with 0 and end with a half turn (turn arounds: 1, 4, 89, 90) and 33 and 34 are a quarter turn
either way. Ranges seen in the data of Beat (all characters share the numbering):

| Motions | Looks like |
| --- | --- |
| 0 to 3 | standing, small weight shifts (0 and 2 face forward, 1 turns round, 3 is the backwards one) |
| 4 to 7 | getting up, crouching |
| 8, 9 | leaning back, arms forward |
| 10 to 12 | crouch that rises, balance recovery |
| 13 to 15 | a fall and the way up again (49, 64 and 68 frames) |
| 16 to 27 | tumbling, lying on the ground, getting up |
| 28, 51, 60 to 65, 68 to 71 | one push of 28 frames and the glide that follows (forward); 66, 67 and 83 to 86 the backwards ones |
| 29 to 50 | groups of four to six short motions with a 14 or 16 frame loop in a deep skating crouch (29 to 32 backwards, 35 to 50 forward) |
| 53 to 59 | standing with a gesture, 20 frames each |
| 76, 77, 91 to 96 | landing from a height, falling flat, sliding, getting up |
| 97 to 112 | deep crouch (the pairs 97/98, 99/100 ...) |
| 113 to 118 | strides, in pairs (113/114, 115/116, 117/118) |
| 119 to 126 | 48 frame spins (half and full turns, both ways) |
| 127 to 141 | grinding: groups of three (12 frame start, 59 frame loop, 4 frame end) |
| 142 to 175 | tricks and graffiti, 10 to 81 frames |

The three motions of kind 4 (176 to 178) are made for the second tree and are not played on the figure. This table was made by
looking at the motions, and the game's own table of what plays when was not found; the port picks from it (see
[screens.md](screens.md)).

Camera paths are a plainer record `{u32 data, u32 frames, u16 0x01C1, u16 interpolation}`; `data` points to four channel
pointers (position, target, roll, field of view) followed by four counts. Position and target have 16-byte keys
`{frame, x, y, z}`, roll and field of view 8-byte keys `{frame, angle}`. The counts of the two angle channels are not reliable;
their keys run to the last frame.

## Menu data blocks

The title, loading, garage, game and tutorial screens each have one block loaded at a fixed address. The block starts with a
table of pointers: object trees, motions, camera paths and sprites, in an order only the drawing code knows. A sprite is a
header `{u32 element, u32 1, ... six floats of 1.0 ...}` that points to an element:

```
u32 texture << 16 | attributes
f32 x, y, width, height        in a 640 x 480 picture
f32 0
f32 pivot x, pivot y
u32 colour * 4                 ARGB per corner
f32 u0, v0, u1, v1             rectangle of the texture, 0 to 1
```

The texture number is a slot of the texture list the drawing code sets before it draws the sprite. See
[screens.md](screens.md) for the screens.

## Sound

`CUSTOM/MUSIC.ARC`, `SOUNDS.ARC`, `IMAGES.ARC` and `FONTS.ARC` are containers of the Xbox 360 release: `ARCB`, a big endian
`u16` count, and `count` entries of 0x48 bytes (a 64-byte name, `u32` offset, `u32` size, big endian). The entries are scrambled
with a byte stream: the minimal standard generator `x' = 48271 * x mod (2^31 - 1)` seeded with the count, each byte XORed with
`(x' + x' / 255) & 0xFF`. The members are stored as they are; the music and the sound effects are Ogg Vorbis.

Music file names are the names of the original's streams with the ending changed (`ROCK_M.ADX` is `ROCK_M.OGG`). The executable
keeps the stream names in a table of 24-byte records at `0x82C910C8`, in alphabetical order, and starts a track by its number.

### Sound banks

`SND_SE.AFS` and `E_SND_SE.AFS` hold, after five Ogg streams, the one-shot banks (`SOSB`, members 5 to 66), the sequence banks
(`SMSB`, `SMPB`) and two more. A bank is little endian: `{"SOSB", u32 version (2), u32 size, u32 count, u32 offsets[count]}`, and
each offset leads to a 64-byte record `"SOSP" ... "ENDP"`:

| Offset | Size | Content |
| --- | --- | --- |
| +4 | 2 | bits 0 to 2: bits 16 to 18 of the sample offset; bits 7 and 8: format (0 16-bit, 1 8-bit, 2 4-bit ADPCM); bit 9: loops |
| +6 | 2 | low 16 bits of the sample offset (from the start of the bank) |
| +8, +10 | 2, 2 | loop start and end, in samples |
| +16 | 2 | pitch: bits 0 to 9 fraction, bits 11 to 14 octave (bit 14 set: below the base rate) |
| +23 | 1 | level, low four bits: steps of 3 dB below full |
| +52 | 2 | length in samples |

The sample rate is `((pitch & 0x3FF | 0x400) * 44100 >> 10)` shifted by the octave. The ADPCM is decoded low nibble first with a
step that starts at 127 and is multiplied by 230 230 230 230 307 409 512 614 over 256 after every nibble (between 127 and 24576);
the difference of a nibble is `(2n + 1) * step / 8` with the sign in bit 3, truncated toward zero. The executable's decoder is at
`0x824ED6D0`, the record reader at `0x824ED990`.

A sound is started with a bank number below 8 and a sound number (`0x824ED098`). The bank a list loads into is the byte at +0x1C
of its load record (sound lists carry bank 0 to 6, or 255 for the lists that take the next free one). `0x82D79938` is a table of
the 78 sound lists: list 0 is the common bank (member 5, bank 0), then the first bank of each character (even members 6 to 34,
16 sounds, bank 1) and the second (6 and the odd members 9 to 35, 15 sounds, bank 2). The sound manager (`0x823651C0`) takes a
kind and a sound number; the kind selects the bank and a static record (`0x82363560`).

## Mission blocks

`MISSIONDATA.AFS` and `MISSIONSET.AFS` members are chains of blocks, loaded at base addresses `0x8CDE0000` and `0x8CDE6000`.
Data blocks start with `JMDc` and version 2, with the next block's pointer at `+0xEC`. Set blocks start with `JMSc` and
version 1, with the next pointer at `+0x50`. A zero next pointer ends the chain.

A data block holds about 40 words from `+0x08`; the word at `+0x14` is the mission type (0 to 9). Further out are vectors at
`+0x70`, `+0xA4` and `+0xB0`, and four pointers (`+0xBC`, `+0xC0`, `+0xC4`, `+0xC8`) to arrays of 12-byte elements.

A set block has pointers at `+0x10` to `+0x48`. The ones at `+0x18`, `+0x1C`, `+0x20`, `+0x24`, `+0x28`, `+0x30` and `+0x44` point
to arrays of record pointers that end with a null pointer.

Some members (tagged `JMSb`, and four of the data members) were left as raw little-endian data.

### What is known inside a block

The word at `+0x10` of a data block is the number of the set member the mission uses in most stages (for stage 1 the data
members 0 to 11 name the sets 1 to 8, 0, 40, 41 and 42). It is not reliable for every stage, so `tools/mission.py` gives a set
to the stage whose placed objects lie closest to nearly all of its spawn records.

| Block | Offset | Content |
| --- | --- | --- |
| data | `+0x70` | where the mission starts (three floats); the point most missions of a stage share is the start of the stage |
| data | `+0xA4` | what the mission's camera looks at |
| set | `+0x34` | table of sector entries; each is a null-terminated array of pointers to **vehicle spawn records** |
| set | `+0x38` | like `+0x34`, 16-byte entries `{x, y, z, flag}` (positions of things placed by the mission) |
| set | `+0x3C` | 20-byte entries `{x, y, z, flag, handle}` |
| set | `+0x40` | 24-byte entries `{x, y, z, flag, type, handle}` |
| set | `+0x2C` | table of sectors filled in by the game while running (empty in the file) |
| data | `+0x5C` | list of commands, 8 words each, ended by a zero command; the mission runner switches on the first word |

A vehicle spawn record is

```
s32 type          index into the stage's vehicle tables
f32 x, y, z
s32 rx, ry, rz   65536 per turn
...
u32 handle        filled in by the game
```

Vehicle types select a model from tables in the executable (high detail, low detail, texture list; a second set follows).

## People of the stages

`ENEMY.AFS` holds pairs of members: a texture pack (even) and a model blob (odd). Four of the blobs (members 47, 49, 51 and 53,
loaded at `0x20AD0000`) are the people of the stages: 17 to 23 object trees of eleven parts each, 64 to 100 triangles, about 16
units tall, each with its own face and clothing sheet (128x128). A table in the executable gives the model and the texture
list for every character type. The trees are in their rest pose; motions and the code that places people were not decoded.

Not decoded yet: motions, where people are spawned, and the sound bank layouts.

## Spray cans

The mission set blocks (`JMSc`, see "Mission blocks") have three tables of sector entries, at `+0x38`, `+0x3C` and `+0x40`. Each
entry leads to a null-terminated array of pointers to records. The game makes one pickup task (size `0xD0`) for every record
of the first table (`0x82383588`; update `0x823758D0`, draw `0x82375608`):

| Offset | Size | Content |
| --- | --- | --- |
| +0 | 12 | x, y, z |
| +12 | 4 | kind: 0 is the small yellow can, anything else the larger teal one |

A small can is a sphere of radius 5 that comes back 3600 updates after it was touched; a large one has radius 7.5 and is taken for
good. They spin once in 29 frames. The models, the spin motions and the picture are not in the stage files: the objects are in the
`main` block of `PLAYER.AFS` (member 16, loaded at `0x8C8E1000`; the small can at `0x8C8E1AEC` with its motion at `0x8C8EADD0`, the
large one at `0x8C8E283C` and `0x8C8EAE98`), drawn with the first picture of the `XTFE` block after it (member 17, a 256x256
sheet of item faces). Each mission set has cans of its own; `tools/mission.py` joins them (`stages.json`, `cans`).

`XTFE` is `{tag, offset of the picture lists, count, offset of an array of count offsets}`; the entries of the array are the picture
lists the item tasks pick by number (the cans use 8 to 11).

The two other tables are 20-byte records `{x, y, z, kind, taken}` (tasks `0x82386718`) and 24-byte records
`{x, y, z, kind, type, taken}` (tasks `0x82385EE8`). The types (10 to 14, 44 to 48, 78 to 82) select a flag in the saved progress
when the item is taken. The 24-byte records are the Graffiti Souls (the missions ask to collect them all). The 20-byte table is
not placed (it is drawn as a flat grey can). The souls are placed in the stages (`items_b`, `items_c` in `stages.json`, models `item_b0`, `item_b1`,
`item_c` in `items.glb`) and taken for good.

## Picture-strip scenes (`DEMO30.AFS`)

The story scenes of the opening are data blocks at `0x8C800000` (member 0 of the archive; member 1 holds one picture per
page). The block starts with three pointers: the end of the subtitle records, a block with the three page pointers
followed by the subtitle records, and a table of texture lists. Each page is a tree of quads lying flat on a grey table
(one picture quad pair and a large untextured square) and has its own camera path (the record with tag `0x01C1`, see
Menu data blocks); the page lasts as many frames (30 a second) as its camera path.

Subtitle records are 28 bytes, big endian: `0`, `4`, page, first frame, text pointer, length in frames, language
(0 Japanese in Shift JIS, 1 English, 2 German, 3 French, 4 Spanish); `$n` is a line break. After the lines come records
of type 13 and 16 that end the scene. The scenes `DEMO31` .. `DEMO35` have another layout and are not read.

## Bitmap fonts (PC release)

`CUSTOM/FONTS.ARC` holds 13 fonts, little endian: `FNT1`, line height, three more metrics, the size of the picture,
the number of table entries plus one, a table from UTF-16 code to glyph number plus one (`u16`), the glyphs (12 bytes:
`i16` x offset, `u16` advance, `u16` left, top, right, bottom) and the picture (two bytes a pixel: luminance, then
alpha). The advance of the italic menu font is not the width of a letter: letters are drawn as wide as their rectangle.

## Graffiti spots

A spot is a record of the stage archive that no table points at. Words (big endian): `+0x00` size class (2 square, 3
wide), `+0x04` position, `+0x1C` scale (1, 1, 1), `+0x58` eight points of its volume, `+0xE8` mask of the pictures that may
be drawn, `+0xEC` pointer to the standing points (0x20 bytes each, first three floats the position) with the count at
`+0xF0`, `+0xF4` pointer to 0xB0 byte stroke records with the count at `+0xF8`, `+0xFC` an object tree whose first piece
is the frame of the spot and the second the quad for the picture. The pictures are 16 bit ARGB 4-4-4-4 words without a
header in `E_GRF.AFS` members 5 to 115: 37 each of 256 x 256, 256 x 128 and 128 x 128 pixels (by member size).
