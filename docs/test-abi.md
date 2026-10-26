# What the emulator tests can rely on

The tests in `tests/emu` drive the ROM in `rp6502-emu` and check what it did.
This is the contract between the game and those tests: what the game prints,
the probe block it keeps up to date, and the rules a test follows so that it
survives changes to the code, the XRAM layout and the graphics.

## Running them

`cmake --workflow --preset check` configures, builds and runs every test.
`ctest --preset cc65/Release -L emu` runs only the emulator tests, and `-R
emu.walk` runs one. Each test runs in `build/cc65/release/test/<name>/`, which
is also where its `shot` screenshots land.

A script test is a `.txt` file of emulator commands, described in the
[emulator manual](https://picocomputer.github.io/emu.html). A Python test is a
`.py` file that drives the emulator through `rp6502.Emu`, from the SDK's
`tools/rp6502.py`, with the helpers in `tests/emu/petscii.py`. Add either to
the list in `tests/emu/CMakeLists.txt`.

## Names, never addresses

Every address in a test is a name from `robots.sym`, which the build writes
beside the ROM:

- RAM: the game's own labels, such as `UNIT_TYPE+1`, `AMMO_PISTOL` or `MAP`.
- XRAM: the `XRAM_` names from `src/xram.h`, such as
  `xram:XRAM_PROBE+PROBE_PLAYER_X`, `xram:XRAM_OPL+$B0` or
  `xram:XRAM_CHARS+5*SCR_STRIDE+4*2`. Expressions take no spaces.

RAM labels move whenever the code above them changes size, and XRAM ones
whenever `xram_layout_t` changes, so a literal address is a test that breaks
for no reason. `robots.sym` holds the program's symbols, not the linker's:
`__GAMEZP_START__` is not there, but `SOURCE`, the first label of
`GAMEZEROPAGE`, is.

## Checkpoints

The game prints nothing. It marks the moments to synchronise on in the probe's
`PROBE_CHECK` byte instead, and a test waits for one with
`wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU`:

| Value | When |
|---|---|
| `PROBE_AT_MENU` | The intro menu is up and reading keys. Set each time it is shown. |
| `PROBE_AT_PLAY` | A level has loaded and play begins. Set at the start of every game; the probe already holds the level and the player's start square. |
| `PROBE_AT_AI60`, `PROBE_AT_AI300` | The main loop has run 60 or 300 times since play began, and the probe already holds that pass's state. |

Each is written once, where it is reached, and stays until the next, so the
same wait twice in a row needs another checkpoint between them -- as a game
and its return to the menu always provide. Before the first menu the byte is
`PROBE_AT_NONE`, 0. Synchronise on a checkpoint, or on another probe field with
`wait xram:...`, before reading anything. A frame count from boot is not a
reference point: how long booting takes is the host's business.

## The probe block

`update_probe()` in `src/main.c` writes the probe at `XRAM_PROBE` once per
pass of the main loop and of the intro menu. It is 32 bytes; the ones not
listed are zero. The offsets are the `PROBE_` names in `src/probe.h`:

| Offset | Name | Holds |
|---|---|---|
| 0-1 | `PROBE_MAGIC` | `'P'`, `'R'` (`PROBE_MAGIC_0`, `PROBE_MAGIC_1`) |
| 2 | `PROBE_STATE` | `PROBE_STATE_BOOT` 0, `_TITLE` 1, `_PLAYING` 2, `_DEAD` 3, `_WON` 4 |
| 3 | `PROBE_LEVEL` | 0-17, level-a to level-r |
| 4 | `PROBE_PLAYER_X` | the player's square |
| 5 | `PROBE_PLAYER_Y` | |
| 6 | `PROBE_HEALTH` | `UNIT_HEALTH[0]`, 12 when full |
| 7 | `PROBE_ROBOTS` | live units in slots 1-27 |
| 8 | `PROBE_RNG` | `RANDOM`, the low byte of the game's random number generator |
| 9 | `PROBE_FRAME` | passes of the main loop, wrapping at 256 |
| 10 | `PROBE_WINDOW_X` | the map window's top left corner |
| 11 | `PROBE_WINDOW_Y` | |
| 12-13 | `PROBE_UNITS_LO`, `_HI` | a checksum of every live unit's type and position |
| 14 | `PROBE_VISIBLE` | units drawn over the terrain by the last redraw, a shorting water droid counted though its tile, 87, draws nothing |
| 15 | `PROBE_WEAPON_ITEM` | `SELECTED_WEAPON` in the low nibble, `SELECTED_ITEM` in the high |
| 16 | `PROBE_LOADS` | images read from `ROM:images` since boot, wrapping |
| 17 | `PROBE_UNITS` | unit sprites the playfield shows |
| 18 | `PROBE_ANIM` | steps of the animated tiles' group A, the water's, every thirty AI ticks, wrapping |
| 19 | `PROBE_PENDING` | 1 while a load or a sprite change is still on its way to the screen, a jump's blackout and the live map included |
| 20 | `PROBE_BLANK` | window cells showing black while their tile loads |
| 21 | `PROBE_OVERRUN` | vblanks that came more than a frame after the last, wrapping |
| 22 | `PROBE_LIVEMAP` | the live map: 0 off, 1 up, 2 up with the robots |
| 23 | `PROBE_CHECK` | the last checkpoint reached, `PROBE_AT_*`; see Checkpoints. Not written by `update_probe()` |

The game writes the magic and `PROBE_STATE_BOOT` first thing in `main()`.
The state is `PROBE_STATE_TITLE` at the menu until the first game starts;
after a game the menu keeps reporting how that game ended, a quit from the
pause as a death.

The probe is not refreshed while the game-over box and the statistics screen
wait for a key, so a test checks the ending once it is back at `PROBE_AT_MENU`. Nor is
it while a transporter dematerializes the player: `DEMATERIALIZE` holds the
game for 64 ticks, as 2.1's does.

## Determinism

The game's random number generator starts from zero at power-on and is never
reseeded, as in 2.1, and the emulator runs exactly the frames a script asks
for, so a script gives the same result every run.
Memory is the exception: the emulator fills RAM and XRAM with random values,
with a new seed each run, to find reads of memory nothing wrote. When a test
fails, its status line shows `MEMSEED`; add `--memseed <value>` to the test's
arguments to run it again with the same memory.

A value with a phase, such as the music's eight-frame rows or the water's
thirty-tick step, is read in the middle of a phase, never on its edge.

The emulator finishes a `READ_XRAM` the moment a script starts it, so the
playfield's loads never back up on their own there. Two RAM bytes make them:
`view_budget` caps the loads started a frame (255 by default, 0 for none), and
`view_lag` set to 1 holds every load in flight until the next VSYNC. Both are
in BSS, which the C runtime clears, so poke them after `PROBE_AT_PLAY`. Wait for
`PROBE_PENDING` to read 0 before checking what the playfield shows. It is
written at the start of a tick, before that tick's redraw, so a check made
right after a redraw reads the same flags from RAM instead, as `settle` in
`tests/emu/petscii.py` does.

## Labels

Every emulator test has the label `emu`. The ones that also read what is on
screen -- sprite records, text cells, palettes, plane configs, the live map --
have `screen` too, and change when the graphics do. The rest check only game
state: the probe, RAM and the OPL2.

`tests/emu/render.py` is the one that checks the playfield against the map: it
works out from RAM and from `assets/gen` what every sprite should show and
reads back the cache to compare, so it follows the art and the layout without
being told. It also follows a jump of the window a frame at a time, with
`view_lag` set so that a load started before the blackout would be counted by
the time the playfield is first seen dark. `tests/emu/livemap.py` does the
same for the live map: it reads the whole map back square by square when it
opens, and every frame while a door opens and closes by the player, checks the
dots as he walks with it up, and checks the playfield whole when it closes.
`PROBE_PENDING` reads 1 for as long as the live map is up, since the
playfield is waiting to come back. `tests/emu/effects.py` reads all six
palettes back and compares them with a model of the Amiga's fade, frame by
frame through a flash, and checks the shake, the marquee and the keys.
`tests/emu/title.py` checks the intro picture with each difficulty's eyes, its
palette and the menu's cells, and `tests/emu/cursor.py` the cursor's icons and
the magnifier a frame at a time through three searches, with one between them
under the live map.

What came from X16 2.1 is checked against 2.1's own files: `x16()` in
`tests/emu/petscii.py` reads them from `assets/src/x16/`, as `gen()` reads
`assets/gen`. `tests/emu/levels.py` boots all eighteen maps and checks each
one's name on the menu and its start square against them, and
`tests/emu/difficulty.py` checks easy, normal and hard on two maps against a
model of `SET_DIFF_LEVEL` run on them. `menu()` in `petscii.py` chooses a level
and a difficulty on the intro menu, `start()` starts it, and `boot()` does
both.

The intro fades in before `PROBE_AT_MENU`, fifteen frames, and a level fades
out and in before `PROBE_AT_PLAY`, thirty, so a test synchronised on those
checkpoints finds the screen ready and the keys read. Anything already running
before a fade -- the intro's song, the clock -- has moved on by then.
`ANIM_STATE` has not: the animated tiles step only in the AI's passes, so not
on the menu or during a fade, nor while the game waits in the pause, the
elevator panel or a transport. The probe is written just before
`PROBE_AT_MENU`, so it already holds how the last game ended.
