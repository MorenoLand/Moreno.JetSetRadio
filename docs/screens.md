# Screens

How the front end is put together, as far as it is known. Everything here is read from the game's own data and from the
tables of its executable (addresses of the retail image, `0x82......`).

The screens are drawn on a 640 x 480 picture; sprite positions below are in that picture. The angle of a camera is stored as
the horizontal angle of that picture (65536 units per turn); the port uses the matching vertical angle so that a wider window
shows more at the sides.

## Start-up

The PC release starts four tasks one after the other: the rating screen (`esrb.png` on black; `cesa.png` and `PSE_J.png` on white
in the Japanese region), the "Sega Heritage" film (`Heritage.ogv`, `Heritage_4_3.ogv` for a 4:3 window) and the logo of the port
(`blit_big.png`) and a notice about graffiti (the crossed out figures and the text, cut by `tools/pcdata.py` from the
console game's logo pack `U_SEGALOGO.AFS`). Fades are 30 frames at 60 a second (1/30 of the alpha a frame), the rating screen stays 90 frames (120 outside
Japan) and the logo 60. A button skips a step. The pictures and films are not in the console release: `tools/pcdata.py` copies them
from the PC folder, and `scripts/screens/intro.gd` shows them before the title. Without them the title starts directly.

## Demonstration

After 20 seconds on "press start" the title plays one of the game's recorded demonstrations (`PLAYDEMO.AFS` of the PC release,
written by `tools/demos.py`): a stage with the skater driven by recorded input instead of the pad (stick angle and strength,
jump and boost as button bits). Any button returns to the title. Only the first demonstration is known to be stage 1; the
other four start in places of other stages and are not used.

## Title

Block `E_TITLE.AFS` member 0 at `0x8CF00000`.

| Slot | Content |
| --- | --- |
| `0x00` | camera path, 260 frames; the camera does not move (position -10.6, 28.2, 605.0, looking at 3.2, 4.5, -2.2, angle 100 degrees) |
| `0x04` `0x08` `0x0C` `0x10` | object trees: the logo (22 objects), the trade mark, the small print, the mascot |
| `0x14` ... `0x20` | their motions, 260 frames each: the logo is assembled from pieces |
| `0x24` | camera set-up: angle at +0x1C, near and far planes at +0x20 and +0x24 |
| `0x28` ... `0x3C` | sprites: "NEW GAME", the logo, "PRESS START BUTTON" (two places), "LOAD", "TUTORIAL" |

The trees are drawn 5 units in front of the camera and scaled down: translation (-10.6, 28.15, 600.0), scale 0.017. Once the
intro is over the game draws only the first tree, moved to y 30.15 and scaled 0.0085. The trees use the 128 x 128 texture of
`TITLE.AFS`; the sprites use the 512 x 512 sheet of `SEGALOGO.AFS` member 2. The title starts stream 0x9D (`ROCK_M`).

## Loading

Block `E_LOAD.AFS` member 0 at `0x8CF70000`: slots 0 and 2 are object trees (20 and 21 objects), slots 1 and 3 their motions of
101 frames, played in a loop. The camera is the identity with an angle of 0x3C71 (85 degrees), the trees 80 units away. Neither
tree has textures: the yellow figure and the blue rings are one tree, the letters of "NOW LOADING" the other.

## Garage

Block `E_GARAGE.AFS` member 1 at `0x8C800000`. The start of the block is a table of 0x4C0 bytes of pointers; tables in the
executable select from it:

| Table | Content |
| --- | --- |
| slot 0 | the room (one tree), textured by the list `0x82D62650` |
| `0x82D7CDFC` | per character, a slot with its tree (slots `0x1F8` to `0x230` of the block) |
| `0x82D7CDC0` | per character, a slot with an object record: where it stands (position at +8, angles at +0x14) |
| `0x82D7CD48` | per character, the texture list patch array |
| `0x82D7CEB0`, `0x82D7CEEC` | per character, two idle motions (slots `0x268` and `0x290`) |
| `0x82CEB368`, `0x82CEB3A4` | per selection slot, an object record: camera position, camera target |
| `0x82CEB3E0` | per character, its selection slot |
| `0x82CEB2F0`, `0x82CEB32C` | per character, slots of the name plate and of the small name tag (sprites) |

There are 15 garage characters. Ids 0 to 9 are the ten skaters in the order Beat, Gum, Tab, Combo, Slate, Piranha, Cube, Mew,
Yo-Yo, Garam (the names are at `0x82D846D8`; the ids are those of the character containers of `PLAYER.AFS`); 10 to 14 are the
rivals. The cursor visits the selection slots in order. The game draws the room, then every character with its texture list,
the camera moving between the slot positions. `E_GARAGE.AFS` member 0 has the six sheets (the map of Tokyo-to, the name
plates, the rival plates, the street / system / graffiti / radio titles, the second map and a text page).

## Characters

`PLAYER.AFS` holds, for each character, a `PLAY` container (five trees, 176 motions) and a `PTEX` container (textures). The load
lists in the executable give the order of the characters: member 8 (Beat), 12, 6, 4, 2, 14, 22, 0 (Mew), 32, 18, then the rivals
28, 24, 26, 30, 10 and 20. Tree 0 is the figure with its outline shell (inverted faces, drawn single sided), trees 1 to 3 are
variants for other states.

The motions come in forward and backward pairs (see [formats.md](formats.md#character-motions)); the game's table of which one
plays when was not found. The port picks by looking: 0 standing, 53 to 59 idle gestures, 60 and 62 the push, 38 and 46 gliding
and boosting, 8 braking, 97 in the air (142 leans far back), 10 landing, 13 and 14 falling.

## Stage

Stages are read as described in [formats.md](formats.md). The start of a stage is the point most of its missions share
(`+0x70` of the mission data); when nothing is under it the other places missions start at are tried, then the nearest floor.
The skater collides with the stage's own triangles, seen from both sides, except the cut-out cards of tree leaves. Slopes steeper
than 46 degrees are walls. The game's own collision data was not found; the volume chunks in the stage files are zones (columns
up to 750 units tall that tile the stage) and do not collide (`F1` shows them as red glass).

The controls are an approximation of the game's, with its own motions. The stick turns the skater towards the direction it points
in, relative to the camera; the camera swings round behind the skater. `Shift` (button X) boosts, `Space` (button A) jumps, `Q`
`E` `R` `F` (right stick) move the camera, `M`, `Tab` or `Y` in the garage opens the map of areas, `Esc` goes back. A hit on a
wall at speed knocks the skater down. Spray cans float along the streets, walkways and stairs; touching one takes it (the count is in the `F1` text). Rails are not placed: the data for them was not found. `F1` shows the debug text (with what the skater last ran into) and the zones; with it on `[`
and `]` step through the motions.

The sky is the stage's backdrop trees, scaled up and kept on the camera. Which texture list each of them uses comes from the
call that sets the sky up in the stage's start routine, not from the object tables (`SKY_LISTS` in `tools/extract.py`). The light
is the garage's: a blue-grey ambient colour and one white directional light from above the camera.

## Sound

Title music is stream 0x9D (`ROCK_M`). The garage and stage tracks, and which of the system effects is the cursor, the confirm and
the back sound, are a choice made here and not data of the game.

The 59 files of `SOUNDS.ARC` are renders of the sound sets the retail build plays by (set, sound) number: `e_se_seq`
(19 sounds of the common bank, `SND_SE.AFS` member 5), `sys_se` (16, the menu), and a few per stage. Listening showed that
`e_se_seq` holds events of the world (a barking dog, gunfire and the like), not the skater's own sounds; picking jump, landing,
fall and boost from it was wrong and those effects are now silent. The skater's sounds are in sample banks (`SOSB`, AICA ADPCM)
that the retail build decodes itself. `tools/sosb.py --export` decodes them the way the build does (see formats.md): the common bank
and the two banks of every character, 259 different sounds. Sounds 0 to 9 and 14 of the character banks are the same for all
characters, the rest are the character's voice. Which sound is the jump, the landing, the roll and so on is not known yet.

With F1 on, `,` and `.` step through the sounds of the common bank and of the chosen character's banks (shown as bank and sound
number with the length) and then through the effect files; `/` plays the current one again. The names to put in
`scripts/core/sound.gd` are the `JUMP`, `LAND`, `FALL` and `BOOST` constants. There is no rolling or push sound yet.

## Menus of the PC release

The title shows the game's demonstration (the recorded input of `PLAYDEMO`) in a window behind the logo, a second
transparent window holds the logo trees. Menu: NEW GAME, LOAD, TUTORIAL, ACHIEVEMENTS, LEADERBOARDS, HELP & OPTIONS,
BONUS, EXIT GAME in the menu font (`mainmenu`), the spray can as cursor. NEW GAME and LOAD lead to ten save slots on the
green zigzag picture (`slots.gd`); a new game plays the opening strip (`cutscene.gd`, `DEMO30`) before the garage. The
other entries open a list of the PC release's texts (`pages.gd`). The loading screen shows `loading_EN.png` on black.
The head-up display of a stage is `hud.gd`: the bar, "points" with the score and the time as orange digits.
