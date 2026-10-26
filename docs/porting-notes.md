# Porting notes

The game logic was converted from David Murray's Commander X16 sources: the
pre-release of 19 September 2022, as published in
[zeropolis79/PETSCIIRobots-X16](https://github.com/zeropolis79/PETSCIIRobots-X16).
The line numbers these notes and the source cite are in those files. The
RP6502 version now follows the later version 2.1 build, which has no source;
the files it takes from that build are in `assets/src/x16/`. These notes call
the first "the X16" or "the pre-release", and the second "2.1". The converter
was checked by rebuilding the pre-release binaries from its sources byte for
byte, and retired once the logic was converted. `src/` is the RP6502 version:
his game logic converted from those sources, the Amiga version's art and live
map, 2.1's maps and its reworking of much of that art, the MS-DOS version's
sound, and new code for everything else. Every difference from the X16 sources
is deliberate, and this file records it.

The game's own text is the X16's, but for the welcome: WELCOME TO
RP6502-ROBOTS! where the X16's said X16-ROBOTS (`src/game/messages.s`).

## What came across unchanged

These are the original instructions, converted from ACME to ca65 and then
adapted only where the RP6502 forced it.

| `src/game/` | from the pre-release's `BACKGROUND_TASKS.ASM` | |
|---|---|---|
| `background_tasks.s` `GET_TILE_FROM_MAP`, `PLOT_TILE_TO_MAP` | 2176–2212 | map read/write |
| `background_tasks.s` `REQUEST_WALK_UP/DOWN/LEFT/RIGHT` | 2306–2417 | one square, bounds and tile attributes |
| `background_tasks.s` `CHECK_FOR_UNIT` | 2422–2440 | occupancy, slots 0–27 only |
| `background_tasks.s` `GENERATE_RANDOM_NUMBER` | 231–237 | an 8-bit LFSR, `EOR #$1D`, now 2.1's 16-bit one; see "Water, as X16 2.1 has it" |

### Changes forced by the target

- **The map pointer.** The X16 uses zero page `$04/$05` as scratch. cc65's
  runtime owns those, so the port uses a named `MAP_PTR` allocated in the
  `ZEROPAGE` segment. Same two bytes, same use.
- **Zero page in general.** The X16 assigns fixed addresses (`TILE` = `$23`,
  `MAP_X` = `$26`, …). Under cc65 the linker allocates them; `src/game/capi.s`
  exports the C-visible aliases and `game.h` declares them with `#pragma zpsym`
  so cc65 emits zero-page addressing rather than absolute.
- **`MAP` alignment.** `GET_TILE_FROM_MAP` composes the address arithmetically
  — `ORA MAP_X` into a zero low byte, `ADC #>MAP` into the high byte — so `MAP`
  must start on a page boundary and `#>MAP` must be a link-time constant.
  `src/rp6502.cfg` adds an aligned `LEVELDATA` segment, and
  `globals.s` carries `.assert (MAP .MOD 256) = 0` so a future rearrangement
  fails the build instead of quietly reading the wrong tiles.
  `LEVELDATA` is placed *after* the loaded segments: it is `bss`, so it is not
  in the output file, and `rp6502_executable()` loads that file at a fixed
  address — putting an unwritten segment first shifts the code out from under
  the load address.

### Behaviour kept on purpose

- **The walk bounds are equality tests.** `CMP #122 / BEQ` blocks a unit
  standing exactly on column 122 and lets one at 123 keep going. No shipped
  level starts a unit outside the bounds, so it never fires; changing it would
  be a behaviour change, not a fix.
- **The tile test is `(attrib & MOVE_TYPE) == MOVE_TYPE`**, not a bare `AND`. A
  unit that can both walk and hover needs a tile that permits both.
- **`CHECK_FOR_UNIT` stops at 28**, so weapons fire (28–31), doors (32–47) and
  hidden objects (48–63) are invisible to it. That is what lets the player walk
  onto a door tile or over a key.

## What was replaced rather than ported

The presentation and I/O are new code, because nothing about VERA, the KERNAL
or ZSOUND survives the move.

The table is the X16-style presentation this port first had; *The Amiga
look*, near the end, replaced its picture-making rows with the Amiga version's
art, and *X16 2.1's art and maps*, after it, some of that art with 2.1's.

| X16 | RP6502 |
|---|---|
| VERA layer 1 text mode, 128-wide tilemap | VGA mode 1, 40×30 character plane, stride 80 |
| VERA layer 0 320×240 4bpp bitmap | VGA mode 3 on plane 0 |
| 4 VERA sprites, one 64×32 | 6 mode 5 sprites, all 32×32 — a sprite array is square-only, so each 64×32 HUD icon is two sprites |
| VERA palette offset 1 | each mode 5 sprite carries its own `palette_ptr` |
| `L1_HSCROLL_L` screen shake | the mode 1 config's `x_pos_px` |
| KERNAL `GETIN`, PETSCII codes | the RIA's 32-byte USB HID keycode bit array |
| `LOAD_PAYLOAD` and six uploader `.PRG`s | `rp6502_asset()` plus `read_xram()` |
| CINV IRQ chain plus a VERA line IRQ | polling `RIA.vsync` as a counter delta |
| ZSOUND, YM2151, VERA PCM | the RIA's OPL2, playing the MS-DOS version's AdLib effects |

Reading `RIA.vsync` as a delta rather than a change flag also fixes something:
the X16's IRQ-driven `UPDATE_GAME_CLOCK` simply lost a tick whenever a frame
overran.

## Bugs in the original

Four were found while converting it, and none is left:

- `x16Robots.ASM:2091` — `STA $E3C9,X` inside `SEARCH_OBJECT`, a PET-era
  leftover with an unconstrained X. Ignored on the X16 because `$E3C9` is ROM;
  on the RP6502 it is RAM. Deleted.
- `SOBJ20`–`SOBJ22` fall on into the next item's compare with whatever A the
  display routine left. They return now.
- `EXEC05`/`EXEC06` fall through, so "cycle map" also runs the difficulty test,
  and `IRQ20` has `STA KEYSOFF` commented out, so `KEYSOFF` free-runs. Both
  went with the code that holds them: the intro menu is C here, and the
  interrupt is the port's own.

## The whole of BACKGROUND_TASKS.ASM

`src/game/background_tasks.s` is the complete file — the dispatcher and all 24
unit types — converted from ACME to ca65 and its zero page ported. It is the
only part of the port that came
across whole, because it is the part David Murray deliberately kept
machine-independent across the C64, PET, VIC-20 and X16.

`src/game/window.s` and `src/game/transporter.s` hold the routines the AI calls
that lived in the X16's machine-specific file but are pure logic:
`CACULATE_AND_REDRAW`, `MAP_PRE_CALCULATE`, `CHECK_FOR_WINDOW_REDRAW`, and
`DEMATERIALIZE`. `src/game/platform_bridge.s` forwards the rest to C.

### Zero page belongs to the game, and the linker enforces it

The ported assembly names the addresses David Murray gave it -- `$02/$03` for
the message pointer, `$04/$05` for the map pointer, `$23-$3B` for everything
else. `src/rp6502.cfg` gives the game that range as its own memory area
and starts cc65's runtime zero page at `$3C`:

    GAMEZP:   file = "", define = yes, start = $0002, size = $003A;
    ZP:       file = "", define = yes, start = $003C, size = $00C4;

so `$04` in the ported code is `$04`, and `src/game/background_tasks.s` and
`src/game/items.s` are the unedited conversion apart from the platform calls.
cc65's runtime turns out to need only 26 bytes, so there is room to spare.

It was not always done this way, and the detour is worth recording. The first
attempt translated the game's zero page onto named variables instead, and the
substitution covered only the direct forms -- `LDA $04`, `STA $04` -- missing
the sixteen **indirect** ones, `LDA ($04),Y`. The result stored through the new
pointer and read through cc65's `$04`, so `GET_TILE_FROM_MAP` returned whatever
the C runtime had left lying there.

That does not present as a bad address. The player simply stops walking, because
the tile lookup returns a number whose attributes say the way is blocked -- and
the map, the unit arrays and `TILE_ATTRIB` all check out against their source
files while you look for it.

`globals.s` pins each address with `.assert`, so the layout is checked every
build, and `tests/source/verify_source.py` checks the partition and the
assertions are still there. Both were verified by breaking them.

Owning the range means owning its startup. cc65's `zerobss` clears the BSS
segment and a zeropage segment is not part of it, so `GAMEZP` came up holding
whatever the SRAM held. Everything in it is written before it is read but one:
`SCREEN_SHAKE`, which the VSYNC interrupt reads from the moment `main()` enables
the interrupt, and that is before any game code has touched it. A stale `$38`
put the character plane four pixels left on alternate frames -- the intro menu's
text and, later, the tile window blurring against a bitmap plane that held
still.

Only on hardware. `ram[]` in the emulator is a C array with static storage, so
it starts zeroed and the fault could not happen there, which is a general shape
worth remembering: the emulator hands the program a clean machine, and a Pico
or a Pocket hands it the last one's leavings. `globals.s` now zeroes the whole
area from a `.constructor`, spanning it with the linker's own
`__GAMEZP_START__` and `__GAMEZP_SIZE__` rather than repeating the addresses.
`tests/emu/gamezp.txt` fills the page with `$FF` before the ROM's startup runs
and watches the plane hold still for a full shake cycle.

The emulator stopped handing out a clean machine in v0.41: RAM and XRAM now
start filled at random, with a new seed every run unless `--memseed` gives one,
so a read of memory nobody wrote fails in the emulator too, and the failing
run's status line says which seed reproduces it. The tests run with the random
fill. The poke in `gamezp.txt` still makes the page the same dirty page every
time; it starts at `SOURCE`, the first label of `GAMEZEROPAGE`, because
`robots.sym` holds the program's symbols and not the linker's.

### A fixed bug

`DEMATERIALIZE` (`x16Robots.ASM:4817`) loads X with 40 as a VERA register value
and then, still holding 40, does `STA UNIT_TIMER_A,X` — so it sets slot 40's
timer instead of its own. Slot 40 is in the 32-47 band, which holds doors and
elevators, so on the X16 a transporter in use nudges whatever door occupies that
slot. The surrounding code says plainly what was meant, and the 40 is an
artifact of VERA writes this port does not have, so it was `LDX UNIT` here.
2.1's `DEMATERIALIZE`, which the port now follows, runs to its end inside one
AI pass and stores no timer at all, so the store and its fix are gone; see
"Dematerializing" under "X16 2.1's art and maps".

### Water, as X16 2.1 has it

Four of 2.1's changes to the AI are about water, and they come as one, since
each leans on the others. Each is marked 2.1 at its site, with its address.

- **The random numbers** are 2.1's `GENERATE_RANDOM_NUMBER` ($1399): a 16-bit
  LFSR in `RANDOM` and `RANDOM+1`, eight steps of `ASL A / ROL RANDOM+1 / BCC
  / EOR #$39` a number, where the pre-release's was one step of an 8-bit one,
  `EOR #$1D`. A zero low byte steps as if it were 1. The port set it to 1 for
  every level; neither X16 version seeds it, so now it is 0 at power-on and
  runs on from one game to the next. Its one caller is still the magnetized
  robot, which reads the low byte, as the probe's `PROBE_RNG` does.
- **A magnetized robot hovers** ($134B), where the pre-release's walked, so it
  can wander out over water.
- **On water it shorts out.** The evilbot and the magnetized robot run
  `WATER_CHECK` ($1E10) before their own AI, through wrappers in the AI chart
  ($1E45, $1341). On water the robot becomes a water droid for 60 runs,
  starting 5 ticks on, its square becomes tile 140 and the shock sounds;
  anywhere else its own AI runs. The wrappers sit just before `EVILBOT` and
  `MAGNETIZED_ROBOT`, because their branches are relative.
- **The sparks are the map's.** `WATER_DROID` ($1B61) steps the map square
  under the droid through tiles 140, 141 and 142, a tile a run, and puts the
  water back at the end, as the droid becomes a wreck. The pre-release
  stepped the droid's own `UNIT_TILE`, which here drew one of three unit-bank
  records over the water. Now the droid's `UNIT_TILE` is 87, 2.1's empty
  sprite, which has no bank image, so nothing is drawn over the square: the
  window shows the Amiga's tiles 140-142 from the tile cache, whole, and the
  live map shows the square in their colour. The three records went to
  2.1's extra frames for the rollerbot and the small explosion (see "More of
  2.1's frames" under "X16 2.1's art and maps").
  `PROBE_VISIBLE` still counts the droid, since it is in `MAP_PRECALC`.
- **The EMP** shorts out a unit on water in the window with the same routine,
  `SHORT_OUT`, but without the shock, as 2.1's does ($4828). So its square
  becomes the sparks too, and a wreck lying on water shorts out again.

Two things go past 2.1, both marked `RP6502` at their sites:

- **Each robot still leaves its own wreck.** 2.1 has one wreck for all; this
  version keeps what the robot was in `UNIT_A` as it dies (see "Robots move
  as they do on the Amiga"). But `UNIT_DEAD` and `WD02` stored the unit's
  type, which is 21 while it is magnetized and 5 while it shorts out, so a
  magnetized rollerbot shot dead left the hoverbot's wreck, and with the
  short-outs so would every robot that met water. `ROBOT_KIND` gives what a
  robot is for its wreck: its type, or while magnetized or shorting out the
  type it had, which both keep in `UNIT_D`, or for a wreck what its
  `UNIT_A` says it was. `SHORT_OUT` keeps that in `UNIT_D`, and `UNIT_DEAD`
  and `WD02` put it in `UNIT_A`.
- **Only a spark tile steps.** 2.1's `WATER_DROID` increments whatever tile
  is under the droid. A bomb or plasma blast centred on a shorting droid that
  leaves it standing rewrites its square, and 2.1 then counts on from the
  blast's tile, through whatever tiles follow it, for the rest of the 60
  runs. Here a tile that is not 140-142 is left alone until the water comes
  back.

And one quirk of 2.1's is not copied. `WATER_CHECK` returns what
`PLAY_DIGI_SOUND` leaves in A, the VERA's PCM control byte with the effects
volume in its low four bits ($5AAE-$5AB9). At an effects volume of 0 that
can be 0, and then the robot shorts out and runs its own AI as well, once.
`PLAY_DIGI_SOUND` returns nothing here, so `WATER_CHECK` returns 1 after a
short-out, whatever the volume.

`tests/emu/water.py` checks them on level-a: the first random number from
zero sending a magnetized robot up onto the water, the short-out a run later,
the sparks stepping a tick at a time and the water coming back, `RANDOM`
against a model of $1399 over twenty runs, the EMP shorting out a hoverbot and
a wreck, a blast's tile left alone, and every wreck the rollerbot's or the
hoverbot's as it should be.

### What the platform layer still stubs

These are real entry points the AI calls; they return cleanly and do nothing
yet. Listed so nobody mistakes a silent one for a working one:

| stub | lands in |
|---|---|
| `plat_play_sound` | M7; now the MS-DOS version's AdLib effects on the OPL2 |
| `plat_print_info` | M5, the three-line message console |
| `plat_display_item`, `plat_display_player_health` | M5, the HUD |
| `plat_elevator_select` | M6, the elevator UI |

## Items, searching, pushing and firing

`src/game/items.s` is `x16Robots.ASM` lines 1468-1986 and 2032-2544: `USE_ITEM`
and the four things it dispatches to, all eight weapons-fire spawns,
`SEARCH_OBJECT`, `MOVE_OBJECT` and `USER_SELECT_OBJECT`. This is the half of the
machine-specific file that is not actually machine-specific -- using an item,
spawning a shot, searching a crate and pushing an object are decisions about
game state.

Two things reached past that and had to change:

- **The search progress dots.** The original pokes a period straight into video
  memory at row 29, column 9 + `SEARCHBAR`. That is now `plat_search_dot` with
  the index in A.
- **`JSR $FFE4`**, KERNAL GETIN. On the RP6502 that address is the RIA's `RW0`
  portal, so the call would pull a byte out of XRAM and advance the portal
  address. `plat_getin` returns what GETIN returned -- the next key code, or
  zero -- and `src/input.c` keeps producing the codes `STANDARD_CONTROLS` names,
  so every comparison in the ported assembly is unchanged.

The `STA $E3C9,X` inside `SEARCH_OBJECT` is deleted. It is a PET-era leftover
with an unconstrained X; on the X16 the target is ROM so the write evaporates,
and here it is RAM.

`SEARCH_OBJECT` returns once it has given what it found. The X16, the PET and
2.1 go on from a pistol, a plasma gun or a medkit into the next item's compare
with whatever A `DISPLAY_WEAPON` or `DISPLAY_ITEM` left; theirs never matches,
and neither does this port's C, but only as it happens to be compiled. The C++
ports' else-if chain and the MS-DOS version return. No test can make the game
show the difference while that holds, so `tests/source/verify_source.py`
checks the three returns are there, and `tests/emu/search_items.txt` that each
find gives its own and nothing of the kinds after it.

One call comes from X16 2.1: the search loop calls `SEARCH_GLASS_CIRCLE`
before each `BACKGROUND_TASKS`, so the magnifier circles the square being
searched; see "X16 2.1's art and maps".

`DISPLAY_ITEM` is C, `plat_display_item`, and it was wrong: an item that had
run out fell back to the first one in stock, where both X16 versions step on
to the next (2.1's $5291), and past the magnet start again from the first. So
with a bomb and a medkit and no EMP, F2 from the bomb came back to the bomb and
the medkit could never be chosen, and using the last EMP went to the bomb
rather than the medkit. It steps on now; `tests/emu/playkeys.py` checks both.

## The tick, and what belongs where

The game runs on a sixty-times-a-second tick: timers count down, the game clock
advances, and `BACKGROUND_TASKS` gets its cue to run one pass of unit AI. That
is a display-rate heartbeat, so it lives on the RIA's VSYNC interrupt, which is
where the X16 has it too.

It has to be an interrupt rather than something the main loop does. The game
waits by spinning: `SEARCH_OBJECT` sits on `BGTIMER2` calling
`BACKGROUND_TASKS` until it reaches zero, and nothing inside that loop would
ever decrement it.

`src/game/irq.s` also carries the video register updates, because the start of
vblank is when a plane's scroll position or a palette entry can change without
tearing. The main loop decides what the registers should say and leaves it in
RAM; the handler pushes it out. That means touching XRAM from an interrupt, and
the two portals are global state with no save area, so the handler saves and
restores portal 1 around its writes -- six bytes at sixty hertz, and the main
loop never has to know.

The VIA is left alone. It is a free-running timer, which suits genuinely
asynchronous work; the game tick is not that.

## The intro screen and the menu

`src/game/screens.s` carried the four screen layouts and the intro artwork from
`x16Robots.ASM` 5327-5457. The layouts are run-length encoded 40x30 character
grids -- a literal byte is one cell, and byte 96 introduces "the next byte,
count+1 times". They stayed compressed: `SCR_TEXT` was eighteen bytes encoded
and twelve hundred expanded, so decoding cost about sixty bytes of code and
saved four thousand. Only `SCR_CUSTOM_KEYS` is left there now: the other
layouts and the artwork gave way to the Amiga's pictures, and the title and the
robot's eyes are 2.1's.

The menu itself is presentation, so it is C rather than ported assembly, but it
keeps the original's shape: four options at character rows 2 to 5, the selected
one marked by its colour, and the intro robot's eyes redrawn from `THREE_FACES`
when the difficulty changes. The rows are where 2.1 puts them on its title, the
options from column 4 and the map's name on row 8. The pre-release flashed the
selected option by cycling its colour through `SPRITECOLCHART`, and its faces
were 16x10 at 2bpp, dropped into the bitmap plane at 234,95; 2.1's
`THREE_FACES` is 16x10 at 4bpp, at 234,75, and that is what is drawn here. See
"X16 2.1's art and maps" below.

One thing worth knowing for the tests: the game reads the RIA's HID keycode bit
array, so the emulator's `type` command does not reach it. `type` goes through
the terminal; `press` and `release` drive the bitmap. Every test drives the game
with `press`.

`frames_total`, which the tests synchronise on, is reset when play starts rather
than counted from boot, so a checkpoint means the same thing however long
someone sat on the menu.

## The end of a game

The live map that was here, the X16's frozen screen, is now the Amiga's; see
"The live map" under "The Amiga look".

The stats screen needs the backdrop out of the way. The X16 turns VERA's layer 0
off; mode 3 has no enable bit, but the plane's position is a signed pixel offset,
so `x_pos_px = -320` moves it a screenful left without disturbing the pixels.

Y in the pause quits straight to the statistics as a loss, as 2.1's `PG6`
does ($46B5: `STZ TEMP_D / JMP GOM4`): no GAME OVER box, no `GOM0` and no
AI, and the clock stays stopped. The pre-release wrote the player's type 0
and let the main loop find him dead, so a quit went the whole way round
through the body and the box. `plat_game_over` is split for it:
`plat_endgame(won)` is `GOM4` to `GOM6`, which the death reaches after the
box and the pause reaches at once. The quit still writes type 0, which 2.1
does not, so the probe reports it at the menu as a death. `GOM0` was also
what ended a big explosion's shake, by letting the blast run out and then
clearing `SCREEN_SHAKE` itself, so `init_game` clears it now; without that a
quit in the middle of a blast left the next level shaking.

For `GOM0` a dead player is a unit again, type 1, as 2.1 makes him ($53EE),
with the ending kept aside, as 2.1 keeps it in `TEMP_D`. The robots treat
the body as they treated him: `CHECK_FOR_UNIT` sees it, so a robot bumps it
and attacks it from beside it, where the pre-release's type 0 was invisible
to it and a robot walked onto the body and attacked it from there. The first
hit makes him type 0 again (`UD01`), with a red flash, and after that they
can step onto it. A pad or a magnet takes the body for the player, in 2.1
too. 2.1 then stops drawing it, since its `DRAW_UNIT_SPRITES` skips a type
0 ($35FF); here it stays drawn, since its frame comes from
`PLAYER_DIRECTION`. Once `GOM0` is over the ending goes back into his type,
where the probe reads it; 2.1's type 1 would read as a game still being
played. 2.1 also ends both flashes there ($5405-$540F), because its `IRQ2`
runs on the AI's tick, which stops at the box. Here the flashes run on the
interrupt and finish by themselves within ten frames, so that is not copied.
`tests/emu/gameover.txt` checks the type through `GOM0` and after it, and
the quit, through to the next level.

### Anything an interrupt writes has to be volatile

`GAME_OVER` waits by spinning on `KEYTIMER`, which the VSYNC handler decrements.
Without `volatile` the compiler is entitled to hoist the load out of the loop,
and it does: the game reached the GAME OVER box and stayed there. Every variable
`src/game/irq.s` touches is declared volatile in `game.h` now.

Worth noting for anyone debugging the emulator scripts: `expect` consumes
stdout up to the point it checks, so two `expect`s in a row after a single `run`
will see the second string as missing even when it was printed. `wait` is the
one to use when checking that a sequence of things happened.

Both endings were verified by hand at first, because dying takes a long walk to
the robots and winning needs every robot dead. `tests/emu/gameover.txt` and
`tests/emu/endgame.txt` cover them now; see *Reaching states no route can*
below.

## The elevator panel

`plat_elevator_select` draws the floor numbers along the bottom row, highlights
the one the player is on, and moves him when left or right picks another. The
window offsets look inconsistent -- `x - 5` but `y - 4` -- and are not: the
original decrements the player's Y after reading it, so he ends up one square
above the elevator and the window four above that, which is the same viewport
row 3 every other move puts him on.

**This one is untested.** It compiles and reads correctly against the original,
but no level puts an elevator somewhere a script can reach cheaply. The nearest
is level-l's, eight tiles from the start, and the route runs around a bunker and
through a corridor where a robot stands in the way. Worth coming back to with a
scripted path, or a test hook that places the player.

## ANIMATE_WATER: rewritten rather than converted

The one routine of David Murray's that could not be converted mechanically.
Everything it does is machine independent -- it permutes bytes of the tileset
and sets `REDRAW_WINDOW` -- but it reaches them through the PET's nine
`TILE_DATA_xx` and nine `TILE_COLOR_xx` arrays, one 256-byte array per cell
position. This port stores the tileset the other way round, eighteen bytes per
tile with glyph and colour interleaved and the colour pre-masked, which is what
makes the blitter six portal writes per row. Structure of arrays into array of
structures is not something symbol arithmetic can bridge, so the routine is
re-expressed in `src/platform.c` against `tile_cells`, with the addressing in
two macros.

Five animations share one twenty-frame timer, as the original runs them: water
(tiles 204 and 221), the trash compactor (148), the HVAC fans (196, 197, 200,
201), the cinema marquee (20, 21, 22, scrolling the 197 bytes of
`CINEMA_MESSAGE`) and the server room light (143). (This describes the X16
character playfield; the Amiga look replaces the rest -- see "The Amiga look"
-- and the timer is now 2.1's, below.) Tile 221 gets five of its
nine cells updated rather than all nine; that is the original's doing and is
reproduced rather than tidied.

`tests/emu/animate.txt` walks to the water in level-a and watches one cell come
back round every third tick, which catches a rotation that runs backwards or
drops a cell as readily as one that does not run.

### On the AI tick, as X16 2.1 runs it

2.1 moved `ANIMATE_WATER` out of the interrupt: its `AI000` calls it first
thing in each AI pass ($1207), before any unit runs, and so does this port's,
through `ANIMATE_WATER` in `src/game/platform_bridge.s` to `view_anim_tick`
in `src/view.c`. So the animated tiles stand still whenever the robots do --
in the pause, the elevator panel, a transport and the waits for a key at the
end of a game -- and a pass that runs over a frame costs them a tick, as it
does everything else. They still move while a search or a push waits, since
those loops call `BACKGROUND_TASKS`.

2.1 also splits them in two on one thirty-tick timer, `WATER_TIMER` at $57A8.
When it reads 0 it is set to 29 and group A steps: the water, the flag and the
server light. Otherwise it counts down, and when the value before the count is
15, group B steps: the trash compactor and the HVAC fans. Each group steps
every thirty ticks, B half way between A's, where the pre-release stepped all
of them together every twenty frames. Neither the timer nor the frames are
reset at a level start, in 2.1 or here. Each tile's frames come in the same
order as before; only the clock changed. `_amiga_tile_anim` marks group B with
bit 6, from `conv_amiga.py`'s copy of 2.1's list at $5707, and `ANIM_STATE` and
`ANIM_STATE_B` count the two groups' steps; `PROBE_ANIM` reports group A's.
2.1 asks for a redraw at every step; here, as before, only while an animated
tile is in view.

One thing goes past 2.1: the cinema marquee, which 2.1 does not have, keeps
its character every twenty ticks, counted in the same place, so it stands
still with the tiles. `tests/emu/animate.txt` now watches the water come round
every thirty ticks, and `tests/emu/effects.py` times group B fifteen ticks
after a step of group A and A again at thirty, then checks that the pause holds
both groups and the marquee still and that they go on after it.

## The tile blitter had to be assembly

`PLOT_TILE` was C, and it cost most of a frame.

It surfaced when `ANIMATE_WATER` landed. The pre-release sets `REDRAW_WINDOW`
from the interrupt every twenty frames so the animations reach the screen, and
two tests that had been passing started failing on timing. Measured by forcing a
full window redraw every frame and counting main loop passes against video
frames:

| | passes per 180 frames |
|---|---|
| C blitter, redraw every pass | 95 (1.9 frames per pass) |
| same with `plot_tile` skipped entirely | 180 (1.0) |
| same with `MAP_PRE_CALCULATE` skipped | 91 (no change) |

So the whole cost was the blitter and none of it was the precalculation: about
15 ms of a 16.7 ms frame for a 77-tile window, roughly 1,560 cycles a tile
against the X16's 219 for the same work. The window redraws on every step the
player takes, so the game was losing most of a frame per step -- and that was
true before the animations existed, which merely made it visible.

cc65 spends it on index arithmetic it cannot keep in registers: a 16-bit
multiply per tile and a pointer increment per byte, reloaded around every store
because `RIA` is volatile. `src/plot.s` writes the same work out by hand at
about 280 cycles a tile, which is what this document predicted for the loop
originally. The redraw now fits inside a frame with room to spare: **180 passes
per 180 frames even with a full redraw on every one of them**, against 95
before. It is also 209 bytes smaller than the C.

The interface is a zero-page pair rather than arguments: the caller sets
`plot_addr` and passes the tile number in A, where fastcall has it anyway, and
the blitter leaves `plot_addr` alone because the window plots terrain and then
the unit overlay at the same address.

Both blitters are verified against the tileset rather than by eye.
`plot_tile` was checked by computing the whole 11x7 window from `level-a` and
`tiles.bin` and comparing all 1,386 bytes of the character plane -- zero
mismatches. `plot_transparent_tile` was checked by forcing a known overlay tile
with four transparent cells over known terrain and confirming each of the nine
cells resolves the right way. The overlay path is covered by `tests/emu/overlay.txt`, which is the only test
that leaves level-a: nothing in level-a puts a mobile unit inside the window
anywhere the player can walk to, since doors and found objects are written into
the map rather than drawn over it. Level-g starts with a robot already in view,
so it reaches the path on the first frame -- and getting there drives the intro
menu's map option, which nothing else did either.

## Game over ran the AI through its own screens

Three faults reported together: "the robot keeps attacking my dead corpse", "the
score screen flashes too fast to read", and "we end up on a map-like screen with
the robot tea bagging my corpse". All three are one line.

The original calls `BACKGROUND_TASKS` in `GOM0` only -- the pause while the body
is on screen and whatever killed him is still moving, which is the point -- and
nowhere after the box goes up. `GOM2`, `GOM3` and `GOM5` are bare waits. This
port called it in all of them, so the AI kept running: a robot went on attacking
the corpse behind the GAME OVER box, and because `BACKGROUND_TASKS` redraws the
map window whenever `REDRAW_WINDOW` is set, the playfield was drawn back over
the endgame statistics -- the map-like screen, with the robot still animating on
it.

Two more differences found while comparing: the original calls `STOP_MUSIC` on
the way in, and `DISPLAY_WIN_LOSE` starts the win or lose *tune* rather than
playing a sound effect, which is what the win and lose patterns in the recovered
PET music are for. This port did neither. `GOM5` also drains whatever is already
waiting before it waits for something new, which is what stops the keypress that
dismissed the box carrying straight through the statistics.

`GOM0` still runs the AI, and since 2.1 the body in it is type 1, a unit the
robots bump and attack as they did him; see "The end of a game".

### The test was lying, which took longer to find than the bug

The first attempt to test this used a recorded route that walks the player into
an evilbot. It passed, and it was worthless: the probe block is refreshed from
the main loop, and `plat_game_over` does not return there until a key has been
pressed at each of its screens. So `tests/emu/playthrough.py` kept reading "alive",
kept walking, and the keypresses it recorded were what dismissed the box and the
statistics. The recording contained the input that defeated the thing being
recorded.

`tests/emu/gameover.txt` writes the player's unit type instead -- which is what
`INFLICT_DAMAGE` does at the end -- and then presses nothing for five seconds at
each screen to prove the wait is a wait. Real damage is covered by
`tests/emu/flash.txt`, which is driven by a hazard hitting the player.

## The gamepad is always live, and the menu has two schemes

A deliberate change, and the reason for it is a design fault in the original:
the pad is one of three schemes chosen from a menu that reads the keyboard, so
**the pad cannot select itself**. You need a keyboard to turn the gamepad on.

Here the pad is always merged with whichever keyboard scheme is chosen, and the
menu offers two: **default** keys, or **custom**, which asks for thirteen of
your own when the game starts. `CONTROL` is 0 or 1 and nothing tests it for 2
any more.

The merge happens in `plat_getin`. That matters more than it looks: the
converted assembly calls GETIN from `MOVE_OBJECT` and `USER_SELECT_OBJECT` and
picks its own pad path on `CONTROL == 2`, which this port no longer sets -- so
without the merge, the selection cursor those routines put up could not be moved
with the pad, and searching with L1 would leave a cursor on screen that nothing
could answer. Doing it at GETIN means every screen that waits on a key answers
to the pad: the intro menu, the elevator panel, the pause prompt, and those two
routines, none of which needed changing.

In play the main loop runs the pad's own pass first, because there a button
means more than a key code can carry -- SELECT is a shift key, the face buttons
fire by position, the sticks are merged in -- and only reads the key queue if
the pad did not act. It uses `plat_getin_keys` for that, the queue without the
pad, since the pad has already had its turn.

One trap, in two parts, both from the same cause: the original keeps a single
`KEY_FAST` because only one scheme is live at a time, and here both are.

The pad's pass ends with `SC35`, which clears `KEY_FAST` when no pad direction
is held -- which is every frame someone is using the keyboard. First that broke
two tests even with no pad attached, so the pass now returns immediately when
none is plugged in, which is also less work per frame. Then the real one: with a
pad actually connected, the keyboard was still being slowed to a crawl, because
`SC35` was resetting its acceleration on every frame and held keys never reached
the fast rate. Measured holding a direction for 120 frames: **8 squares with a
pad connected against 15 without**.

The pad has its own acceleration flag now and never touches the game's
`KEY_FAST`. Same measurement after: 15 either way, and the pad's own repeat
unchanged at 15 squares. Two live schemes need two flags; sharing one was a
detail of the original that stopped being true the moment both ran at once.

## The controls menu, which did nothing

Reported alongside the gamepad: "controls menu also does nothing". Correct, and
it is why the gamepad looked dead too -- there was no way to tell it had been
selected.

`CYCLE_CONTROLS` (x16Robots.ASM 4193) does three things: clears `KEYS_DEFINED`,
steps `CONTROL` through 0, 1, 2, and writes the chosen scheme over the intro
screen's control line -- ten characters at row 5 from column 4, which is where
the menu draws that option's own label, so the label is replaced by the answer.
This port did the middle one only. `CONTROLTEXT` ("keyboard  ", "custom key",
"snes pad  ") had never been converted at all.

`SET_CONTROLS` (4737) was missing its other half as well. It runs at boot and
again when START GAME is chosen; custom keys send it to `SET_CUSTOM_KEYS`, which
puts up `SCR_CUSTOM_KEYS` and asks for thirteen keys, echoing each back as the
decimal code every `CMP` in the ported assembly will be compared against. The
screen data was sitting in the converted screens with nothing reading it. This
port copied `STANDARD_CONTROLS` unconditionally at boot and never called
`SET_CONTROLS` again, so choosing custom keys did nothing.

`tests/emu/controls.txt` cycles all three and checks the line each time, then
chooses custom keys, starts, answers thirteen prompts and checks they landed in
`KEY_MOVE_UP`. It asserts glyphs one at a time rather than whole cells: the
colour byte beside each is animated by the menu's flash, which walks a chart
starting at 0, so reading a cell whole would depend on when the read landed.

## Gamepads

`plat_gamepad_read` was an empty function, so choosing CONTROLLER on the intro
menu gave a game that ignored you -- and the ported assembly was already calling
into it, since `items.s` reads the pad from `MOVE_OBJECT` and
`USER_SELECT_OBJECT`.

The X16 asks the KERNAL for a joystick word and unpacks it into twelve latches:
B, Y, SELECT, START, UP, DOWN, LEFT, RIGHT, A, X, L, R. A press sets one and
whatever acts on it clears it. The RIA keeps the same facts in XRAM, updated
continuously, so the read is four bytes of the player-one block rather than a
call: DPAD holds the directions and a connected flag, STICKS both sticks reduced
to direction bits, BTN0 the face and shoulder buttons, BTN1 select and start.

**Face buttons are mapped by position, not by name.** The original fires in the
direction of the button under your thumb -- SNES Y is the left button and fires
left, A is the right one, X the top, B the bottom. The RIA reports buttons by
label, and a label sits somewhere different depending on the pad: DPAD bits 4-5
say which convention this one uses, and an Eastern BA pad has A and B the other
way round from a Western AB one. Mapping by name would fire left when you press
the top button on half the pads in the world.

**Both sticks are merged in.** The left stick joins the d-pad and the right
stick joins the face buttons where each points, so the pad is twin-stick and
nothing above the read knows: the twelve latches are still the twelve the X16
unpacked, and `SC01`-`SC75` is the original's dispatch unchanged -- directions
gated on `KEYTIMER`, buttons not, SELECT acting as a shift key that turns left
into the map, L into cycle-item and R into cycle-weapon.

One bug worth recording, because it looked like a hardware problem and was a
compiler one. The first version skipped the STICKS byte with `(void)RIA.rw0;`,
relying on the read to advance the portal. A read whose value is discarded is
exactly the kind a compiler may drop, and cc65 dropped it -- so `btn0` received
the stick bits and `btn1` received `btn0`. The d-pad worked, because DPAD is
read first, and no button ever did. All four bytes are used now.

While implementing it: `PAUSE_GAME` had never been ported either. `MSG_PAUSED`
was sitting in the converted messages with nothing reading it, and run/stop did
nothing on the keyboard as well as on the pad. It stops the clock, offers to
quit, and waits in a tight poll with no `BACKGROUND_TASKS` -- so the world
really stops, which it can now that the keyboard is scanned by the interrupt.
`CLEAR_KEY_BUFFER` also sets `KEYTIMER` to 20 in the original and did not here,
which meant a key still held arrived immediately as a fresh press, which is the
one thing the routine exists to prevent.

`tests/emu/gamepad.txt` covers the d-pad, both sticks, L1 into `SEARCH_OBJECT`
and the direction that answers it through `SMV30`, and two face buttons firing
in the directions they sit in.

## Key repeat: the original has one, and I had not used it

Reported as "controls suck ass: press down, press right, release right and you
keep going right". Correct, and the cause was that `src/input.c` was invented
rather than ported.

The X16 source has this logic. `KEY_REPEAT` (x16Robots.ASM 1988) runs at the
top of the main game loop, before `GETIN`, and is meant to take a key still down
when `KEYTIMER` reaches zero as pressed again. It does that through `$C5` and
`$028C`, the C64's LSTX and repeat delay; on the X16 KERNAL those are a byte of
BASIC's floating-point accumulator and an I/O variable, so there it does nothing,
and a held key walks at the PS/2 keyboard's own typematic rate, about 500 ms and
then ten or eleven a second. The PET does it for real, by faking a release, and
the Amiga, which has key-up events, does it directly. The rates are the *game's*,
not the input layer's: `AFTER_MOVE` sets `KEYTIMER` to 15 before the first repeat
of a held direction and 7 after that (this port uses 6; see below), firing and
cycling set 20, `INIT_GAME` sets 30, the game-over wait sets 100.

Two things were wrong here. The first is that this port kept "the key being
repeated" as a single remembered code, set on a fresh press and cleared only
when *nothing* was down -- so releasing the newer of two held keys left the
released one repeating. The original cannot have that fault, because it reads
what is down now rather than remembering. The second is bigger: `KEYTIMER` was
written in twenty-odd places in the original and in **none** in this port, so
the game's own pacing was not connected at all and the input layer had invented
its own timings (20 and 7) in its place.

Now `plat_key_repeat` is `KEY_REPEAT` as the PET and the Amiga run it -- the
newest key still down in the RIA's bit array, pushed onto the queue `plat_getin`
drains -- and the game sets `KEYTIMER` where the original sets it. `tests/emu/keys.txt` holds down, taps right, releases right and checks
he goes down; before the fix x ran on and y did not move.

Worth stating plainly: the menus call `GETIN` alone and only the game loop calls
`KEY_REPEAT` first, which is why menus act on presses and only walking repeats.
That is the original's arrangement, not a choice made here.

A held key repeats as its press was read, with SHIFT as it is now.
`plat_key_repeat` used to repeat the bare key, so once SHIFT+M was 2.1's music
key a held SHIFT+M repeated as M, the push key, and put up the hand.
TAB, SHIFT+TAB, F6 and SHIFT+M do not repeat at all, since each turns
something on and off, and neither does SHIFT+C, which would play the cheat's
sound every seven frames. The volume keys do repeat, one step every 20 frames
held: `fx_volume` sets `KEYTIMER` 20, where 2.1 sets none. 2.1 can leave it
out because its `KEY_REPEAT` does nothing on the X16 and the keyboard's
half-second typematic delay keeps a tap to one step; here, with the timer at
or near 0, a tap would step twice.
`tests/emu/playkeys.py` holds both down.

**Walking speed: ten steps a second, 2.1's.** After the first repeat a held
direction steps every 6 frames, not the X16 code's 7 (`walk` in `src/main.c`).
The 7 never takes effect on an X16 keyboard, where the keyboard's typematic
sets the pace at about ten steps a second, and 2.1's gamepad path,
`AFTER_MOVE_SNES`, uses 6. So 6 is the speed a 2.1 player walks at; the first
repeat still waits 15 frames, as every version's game code asks.

**A key still down after a clear is forgotten, as on the Amiga.**
`plat_clear_key_buffer` empties the queue and also the set of keys held, so a
direction still down after a search, a move, a use or the cycling of a weapon
or item goes back in only when it is let go and pressed again. The PET and the
pre-release only held it off for `KEYTIMER`'s 20 frames, which a slow finger
outlasts; on 2.1 the keyboard's half-second typematic delay hid it. F1 and F2
clear the buffer after cycling, as every version does (MG05, MG06), so held
they act once a press. `tests/emu/search.txt` holds the arrow that chose the
square long after the search, and `tests/emu/keys.txt` holds F2.

## Driving the game further than a fixed list of keys can reach

`tests/emu` scripts are open loop: press keys, check results, with no way to ask
where the player ended up and decide what to press next. That is fine for a few
steps and useless for crossing a level -- a door costs one press to open before
it costs one to walk through, and a robot in the way costs an unknown number, so
a fixed list desynchronises and every move after that is wrong. Two attempts at
hand-written routes into the 2022 level-l (castle robot) and level-g died
exactly there.

`rp6502-emu` takes `--script -`, so `tests/emu/playthrough.py` drives it a line at a
time: read the player's position out of the probe block, plan a route from
*there* with a breadth-first search over the level's walkability, press one key,
look again. Walkability is `TILE_ATTRIB` bit 0, the same bit `REQUEST_WALK` tests
through `MOVE_TYPE`; door squares count as passable because walking into one
opens it, and the extra press that costs is what the loop absorbs.

What it prints is the script that worked. Replayed open loop that is
deterministic -- the RNG starts from zero at power-on and is never reseeded,
as in 2.1, and the emulator runs exactly the frames it is told to -- so a
recorded route is a normal test until the game's timing changes, and when it
does, regenerating is one command rather than an afternoon. `tests/emu/flash.txt` is the first test built this way. The driver
uses `rp6502.Emu` from the SDK's `tools/rp6502.py`, and reads walkability, the
map and the doors out of the game's RAM by name once the level is up.

### Reaching states no route can: poke

`rp6502-emu` grew a `poke` command, which writes memory the program then reads.
That is how the last three gaps closed, and each writes only the state the game
would have arrived at by itself:

* **The endgame.** `TRANSPORTER_PAD` activates only once every unit in slots 1
  to 27 is dead, so winning is a full combat playthrough and no route reaches
  it. `tests/emu/endgame.txt` writes zero over `UNIT_TYPE[1..27]` and the pad's
  own AI clears `UNIT_A` on its next pass, exactly as it would after a real
  fight. The player still walks to the pad and `DEMATERIALIZE` still runs its
  64 ticks.
* **Game over.** The hazards a route can reach stop short of killing him --
  level-e's rollerbot takes twelve health to one and loses interest.
  `tests/emu/gameover.txt` writes the player's unit type to 0 on level-a, as
  the end of `INFLICT_DAMAGE` does, and checks what the game does after: the
  body, the box and the statistics. Taking real damage is `flash.txt`'s.
* **The elevator panel.** Written in M6 and never tested, because all
  thirty-three elevators in the eighteen maps are behind locked doors and the
  shafts are not walkable. `tests/emu/elevator.txt` pokes the player to the
  square `ELEVATOR_PANEL` looks for -- the elevator's column, one row above it
  -- and drives the panel from there.

`poke` was newer than the emulator CI fetched, so for a while those tests were
registered only where it existed, and CI never ran them. With the v0.41 SDK every
test registers through `rp6502_test()` against the emulator release
`CMakeLists.txt` pins, so all of them run everywhere. The first run of
`endgame.txt` under it found a third key press that the slower old emulator had
been absorbing; two screens take two keys.

### Frames are exact now, and the tests sync on the game

Up to v0.40 the emulator did not deliver an exact number of frames: the same
script and ROM gave 143 VSYNCs for `run 600` on some runs and 144 on others, so
`tests/emu/flash.txt` was rewritten to read a value the border ramp holds for
two frames, and positions after a *held* key were the fragile kind. v0.41 runs
exactly the frames it is told to.

Exact frames do not make a fixed offset safe, though. Two tests read a value
whose phase is set by everything that ran before them -- the music's row, which
is eight frames, and the water's tick, then twenty -- and both sat on an
edge. `audio.txt` now peeks a few frames into a row, and `animate.txt` waits
for the first water pattern to arrive and reads each later one half way
through its step. A check should still not depend on exactly when it is read.

### What still cannot be reached, and why

**Locked doors.** `UNIT_C` on a door is 0, or 1, 2, 3 for the spade, heart and
star keys, and `AI_DOOR` will not open a locked one without the key in `KEYS`.
The driver treats locked doors as walls because it starts from a cold boot with
no keys; teaching it to search for keys would make it a game player rather than
a test fixture.

## The border and background flashes

(The X16-style flash this section describes was replaced by the Amiga's
whole-palette flash; see "The Amiga look". The counters and their triggers
are as described.)

`BORDER` and `BGFLASH` are each one array whose index 0 is a countdown and whose
remaining ten bytes are a colour ramp; the interrupt walks the ramp backwards as
the counter falls. The X16 wrote them to the two halves of VERA palette entry 0
-- `BORDER` the byte holding red, `BGFLASH` the byte holding green and blue.
There is no border here, so both land on entry 0 of the bitmap palette, which is
the black the playfield sits on: the same thing the X16 was tinting.

One difference, deliberately. VERA takes four bits of red and ignores the high
nibble of that byte, so the ramp 8, 15, 25, 31 reached the screen as 8, 15, 9,
15 -- a jump backwards in the middle of a fade the author wrote as monotonic and
symmetric. RP6502 palettes are RGB555, so the five-bit value goes through as
written. The green and blue nibbles are doubled to fill five bits.

Verified by forcing both counters at bring-up and reading the palette entry every
frame: red ramps 0, 8, 15, 25, 31, 31, 25, 15, 8, 0 with blue and green
alongside, the opacity bit stays set throughout, and entry 0 returns to opaque
black on the way out.

`tests/emu/flash.txt` then covers it in real play. The triggers are `USE_EMP`,
the trash compactor reaching the player, and the player taking damage, and
nothing in level-a's start area reaches any of them -- but level-e has a hazard
at 75,42 that hurts the player about once a second, which is a repeatable
trigger. Getting there is 25 squares through doors, which is what
`tests/emu/playthrough.py` is for.

## Sound: the MS-DOS version's AdLib effects

The RIA has a PSG and an OPL2, one at a time: mapping one turns the other off.
The OPL2 is the chip of the AdLib card, and the MS-DOS version has AdLib
sound, so the effects are its; `assets/src/dos/` holds its `.ADL` files.
Before the OPL2 the port played the PET's one-voice engine, recovered from the
PET sources, on the PSG; the X16 versions play recorded samples.

**What plays.** The DOS version plays an `.ADL` file with the SSY player in
its `audio.c`: per channel a compressed stream of register changes, waits,
back references and a loop point, decoded 72 times a second, and written to
the chip only where a register changed. `assets/convert/conv_adl.py` runs that
player at build time and keeps only what it writes, as VGM commands -- `5A`
a write, `61` a wait in 44.1 kHz samples, `66` the end -- and `src/sound.s`
plays those on channel 0, the effects' channel in DOS too. Nothing on the
6502 decodes SSY. The effects are 4.4 KB this way, against the `.ADL`'s 1.7,
and stay in RAM.

DOS starts an effect with whatever instrument the last one left, writing only
the registers that differ. Every effect sets all ten of its own before its
first write, which the converter checks, so each stream writes all ten at its
start and owes nothing to what played before; the chip ends up holding what
DOS leaves in it either way. Effect 1, the item cycle, really does set all ten
to $AA.

**The clock.** 72 ticks a second: DOS's `interrupt.c` programs the PC's timer
with a divider of 16571, 72.004 Hz, where `audio.c`'s comment says 72.8. VSYNC
is 60 Hz, so VIA timer 1 is the clock. `src/sound.c` reads PHI2 from
`RIA_ATTR_PHI2_KHZ` -- the RP6502-PICO rounds it up to what it can make -- and
a tick is PHI2 / 72 cycles. At 8 MHz that is 111,111, past what a 16-bit timer
counts, so the timer runs at a whole multiple of 72 Hz and every
`snd_subticks`-th interrupt is a tick: two at 8 MHz, one from 4.7 MHz down. A
tick is 612.5 samples, so the converter writes 612 and 613 in turn from the
start of each stream and the player's count goes up by the same, which lands
every write on the tick DOS made it.

The VIA's interrupt is an `.interruptor` of its own, not part of the C level
handler below: it calls no C, so it needs none of the zero page that handler
saves, and it costs a few hundred cycles a tick. Its pointer is `SND_PTR`, in
the game's half of zero page. It borrows portal 1 and hands it back as the
VSYNC handler does.

**Which effect plays** is the DOS rule, `ssy_sound_play`: each effect has a
priority and a time in ticks, and while that time runs only an effect of the
same priority or higher replaces it. An explosion, 13 for 30 ticks, cannot be
cut off by a pistol shot, 5; a door, 1, follows a beep, 0, at once. This
replaces 2.1's rule, the newest wins, which the port had taken from
`PLAY_DIGI_SOUND`: these are DOS's sounds, and its tables were made for them.
The tables are in `audio.c`, and the 1.22 `robots.exe` carries the same 34
bytes.

The game's effect numbers stay the X16's, because those are what the ported
code names, and map to DOS's by name. DOS has two explosions where the X16 has
one, and uses them: the big explosion, for bombs and canisters, plays
`SFX_EXPLOSION2`, a one-line change in `BIG_EXP_PHASE1`, and the trash
compactor keeps `SFX_EXPLOSION`. The two beeps go by name too: `SFX_BEEP`, the
cursor's, is DOS's `BEEP`, and the menu's `SFX_BEEP2` is `BEEP2`.

**The volume**, 2.1's 0-15 from 10, moves the levels the chip hears: the
carrier's, and the modulator's when the channel adds the two operators rather
than modulating one with the other. 10 is DOS's level and each step is
2.25 dB, near the step of the VERA's PCM volume that 2.1 sets with it. Most
effects already play their carrier at full level, so above 10 those cannot get
louder. At 0 the key-on bit is never set, so nothing sounds, while the effect
still runs and still holds its priority.

**The music** is the DOS version's too, on channels 1-8 as there: METAHEAD on
the title, the four level songs in turn by map as both DOS (`LEVEL & 3`) and
2.1 pick them -- GETPSYCH, METALBOP, ROBOATTK, RUSHING -- and WIN and LOSE at
the end. The same converter runs the player over each and writes a VGM file,
which goes in the ROM as an asset: 1.25 MB of them, against 157 KB of `.ADL`,
because nothing is left to repeat by reference.

A song is too big for RAM, so it is streamed. `src/sound.c` keeps two 512-byte
buffers full with READ_XSTACK, called directly rather than through `read()`,
512 bytes being what the XSTACK holds. The read is the loader's first job
while the main loop waits for VSYNC, ahead of the tiles, and asynchronous as
theirs are: the vblank work goes on if VSYNC comes while it runs
(`src/view.c`). It is not counted as a tile load and has no budget. A buffer
lasts eight frames even in the densest passage and about twenty on average,
so a read comes every twentieth frame or so. The tick plays from one buffer
and on into the other, a command running across the join if it must. If the
other is not ready the song waits, its clock with it, so a late read makes it
pause rather than skip; `mus_underruns` counts the ticks it waited, and the
tests hold it at 0.

A song that loops is read to just before its `$66` and then on from its loop
offset, so every buffer is a full 512 bytes and the join at the loop is a read
like any other. WIN and LOSE play once, as 2.1's jingles do -- the DOS version
loops them every 12 and 15 seconds -- and end where DOS would go round.

A VGM loop replays the same writes each time, where DOS writes only what
changed, so the converter plays each song three times through and loops the
first pass that repeats exactly in what the chip holds, then replays the
result against DOS for all three. GETPSYCH, ROBOATTK and RUSHING loop from the
start. METALBOP's first pass leaves the chip set differently from the passes
after it, so its file holds the intro and two passes and loops the second, 212
seconds in. METAHEAD never repeats: its
voices loop a tick apart, so in DOS they drift a tick further apart every pass.
Here it loops its first pass, back to 22 seconds, without the drift. The start
of a loop writes back whatever the end of the pass changed that the pass needs,
which is nothing the first time round.

A jump back in the stream can put its waits a sample out of step with the
clock's 612 and 613, so a song's tick runs while the stream is less than half
a tick ahead, which reads each tick's writes on its own tick either way.
`music_stop` leaves channels 1-8 as DOS's `ssy_music_stop` does, the carrier
at its lowest level and the instrument cleared, which is what the converter
assumes a song starts from. But DOS clears the instrument with notes still
sounding, and cleared, a note's rates are 0, so it stays at the level it had
reached; the next song's first volume write brings it back on any channel that
song never plays. After level a's song the lose jingle went on ringing with
two of its notes. So first every voice is keyed off at the fastest release,
and the clearing waits two ticks for them to die away.

`tests/emu/sound.py` checks the clock at 8 and 3 MHz, plays every effect and
holds the chip to the converter's writes frame by frame, at several volumes,
and checks the priority rule; then the title, there and round its loop, level
b's song and the lose jingle to its end, each against the converter tick by
tick, with the stream never late. `tests/emu/sfx.py` is the model.

### The interrupt calls C, so it goes through set_irq

Symptom: after walking a while, small runs of coloured pixels appeared over the
playfield and stayed at a fixed screen position while the map scrolled under
them.

They were tile data in the wrong plane. Each run was six bytes, and every second
byte had a zero high nibble -- which is `tile_cells`' `{glyph, colour & 0x0F}`
pairs -- and the runs sat exactly eighty bytes apart, which is `SCR_STRIDE`. So
one `PLOT_TILE` call had written its three character rows into the bitmap plane
instead of the character plane. The bitmap does not scroll, hence "locked to the
screen", and nothing redraws it during play, hence "and stays there".

The cause is that the VSYNC handler reaches C: it ticked the PET's sound
engine then, which called the PSG driver, and today the flash step and the
keyboard scan are C. cc65 compiles every C function against twenty bytes of shared zero-page
scratch -- the C stack pointer, `sreg`, `regsave`, `ptr1-4`, `tmp1-4` -- so an
interrupt that calls C and does not put them back returns to whatever C function
was running with its pointers and temporaries overwritten. `plot_tile` is C, and
its `addr` is one of those temporaries. `zeropage.inc` names the amount for
exactly this case: `zpsavespace`, "the amount of space that needs to be saved by
an interrupt handler that calls C code".

The fix is not to write that save loop. cc65 already has it: `set_irq()` installs
a C level handler and the runtime's `clevel_irq` wrapper saves and restores that
zero page, switches to a separate C stack and preserves `jmpvec` around the call.
So `src/game/irq.s` exports `_petscii_irq` returning `IRQ_HANDLED` /
`IRQ_NOT_HANDLED` and `main()` installs it with `set_irq`, instead of declaring
a bare `.interruptor`. A bare interruptor is only safe if it never reaches C.

Measured: 18 bytes of the bitmap corrupted after ten steps as an `.interruptor`,
zero after 160 steps through `set_irq`. `tests/emu/irq_zp.txt` walks twenty steps
and checks the three addresses it used to land on.

## The Amiga look

The RP6502 version uses the Amiga version's art: its tiles, its HUD pictures,
its game-over picture and its font. The title picture, the playfield's
sprites -- the player, the robots, the shots and explosions -- and two tiles
are X16 2.1's reworks of the Amiga's; the cursor's icons and the intro robot's
eyes are 2.1's own, and so are the maps (see "X16 2.1's art and maps").
The art is in `assets/src/amiga/`, with a note on where it came from, and
`assets/convert/conv_amiga.py` turns it into the RP6502's formats. The game
logic is untouched; what changed is everything that draws.

**The screen is the Amiga's 320x200,** on the RP6502's 320x200 canvas, which
is 16:10, so nothing is letterboxed; the web player and the VS Code launch keep
the window 16:10 from the start. Its layout is the Amiga's: the 11x7 window at
the top left, the weapon, item, keys and health down the right, and the
information panel along the bottom. Every mode is programmed once, in
`video_init`; after that a screen change is an XRAM write. Every position is
from `SCREEN_TOP` in `src/xram.h`, 0 now, 20 when the screen sat in the middle
of a 320x240 canvas.

**The playfield is 77 mode 5 sprites** of 24x24 that never move, over a 13x9
cache of tile images addressed like a wrapping mode 2 map: a scroll changes
which slots the sprites point at. The 253 tiles live in `ROM:images`, kept
open, and a slot is loaded only when the map cell it stands for has a different
tile. `src/view.c` explains the rest.

**Loading happens while the game waits for VSYNC.** `READ_XRAM` moves bytes
without the 6502, so the wait for the next frame polls the load in flight and
starts the next one the cache needs: the window's cells first if any need it,
then the margin, the side the window last moved towards first. When the frame
changes, the vblank work writes the 77 image pointers, the unit sprites and the
player's new frame -- all of it worked out earlier by `DRAW_MAP_WINDOW`, which
only plans now -- and then waits for the load in flight to finish before the
game's tick runs. No load starts after VSYNC.

**A step waits for the cache.** Before the player walks, `view_ready` checks
that the window has been drawn where it now is and that the margin on the side
he is stepping towards has loaded. If not, the key goes back on the front of
the queue, or the pad's press stays latched, and the step happens a frame or
two later; on the RP6502's storage that is all but never. A margin tile can
change without asking for a redraw -- the raft docking there -- so a step that
finds one not loaded starts the margin's walk again itself. It covers
the raft too: the raft carries the player a square in the AI, the window is
only drawn at the start of the next pass, and walking off the raft in the pass
it docked used to move the window two squares between redraws. The raft keeps
its own timer, so a cell it brings into view before the tile has loaded shows
black until it has -- the one way left to see that, and only on storage slower
than a square every eight frames.

**A jump blacks the playfield out.** The elevator and the transporters move
the window further than the margin, and loading the new view would overwrite
slots the old one still shows. So the next vblank moves every playfield sprite,
the units and the player with the tiles, below the screen, where the HUD frame
is transparent over a black canvas. The loads start only after that, and the
window comes back once the whole cache has loaded, margin and all, ready to
walk in any direction. Starting a level loads everything at once instead,
under a black cover; closing the live map goes dark the same way a jump does.

`BACKGROUND_TASKS` now begins with `JSR VIEW_HOOK`. The waits that call it in
a loop -- searching, moving an object, the dying player -- get the vblank work
on each new frame and
keep the loads going in between, but only once the frame's AI has run, so the
game's tick never starts a load. The waits that run no AI -- the pause, the
elevator panel, the game-over screens -- call `view_idle` for the same.
Every other API call first waits out the load in flight: the RIA runs one call
at a time.

**Units are sprites over the tiles,** from a bank of images that stays in
XRAM. `MAP_PRE_CALCULATE` still decides which unit shows in each cell. The
robots, their wrecks, the bomb, the canister about to blow, the magnet, the
shots and the small explosion are X16 2.1's sprites, and the big explosion is
2.1's tile. The Amiga masks the bomb and magnet with colour 0, so there they
have no black outline, where 2.1's sprites draw one here. It also draws the
canister and the electrocuted water droid's sparks through the bomb's mask,
by accident -- only their own masks are missing -- so they show as
bomb-shaped patches there. Here the canister is 2.1's, a whole square, floor
and all, and the sparks are no unit's image but the square's own tiles, the
Amiga's 140-142, as 2.1 has them; see "Water, as X16 2.1 has it".

**Robots move as they do on the Amiga,** in 2.1's art. The game logic now
keeps two facts it did not, both as the Amiga keeps them:

- `REQUEST_WALK_*` stores the way a unit tries to go in `UNIT_DIRECTION` (0 up,
  1 down, 2 left, 3 right) before checking anything, so a blocked step still
  turns it. The evilbot's frame takes the Amiga's offset for that facing, so
  it turns as it hunts; the other robots have one look for every direction
  on the Amiga too.
- `UNIT_DEAD` and `WD02` keep the robot's type in `UNIT_A` as it dies, and the
  wreck is the one that robot leaves: the rollerbot's, the evilbot's, or the
  hoverbot's for anything else. A robot that is magnetized or shorting out
  keeps the type it had, through `ROBOT_KIND`; see "Water, as X16 2.1 has it".

`MAP_PRE_CALCULATE` also notes which unit each window cell's tile belongs to,
in `MAP_PRECALC_UNIT`, so `src/view.c` can read those two. And as the Amiga
draws one unit a cell over the player's: an explosion on his square covers
him, and a bomb or magnet there goes under him and does not show. A shot
leaving him is not let cover him, which on the Amiga it can for a frame.
Transported off the level at the end, he is not drawn on the pad behind the
GAME OVER box; transported within it, he stays out of sight until the window
is drawn where he arrived, then shows the Amiga's frame for tile 97 -- facing
down, no weapon -- until his next step. Firing with no weapon no longer turns
him, as on the Amiga. Still different: the water droid's sparks cycle every
tick where the Amiga's take four, and the animated tiles step on 2.1's clock,
two groups every thirty ticks of the AI, rather than the Amiga's; see "On the
AI tick, as X16 2.1 runs it".

`CHECK_FOR_WINDOW_REDRAW`, which the AI calls after moving a unit, asks for a
redraw when the unit is in the window or the square round it, where the
original asks only for the window. A unit that had just stepped out of view
was outside it, so nothing redrew and its sprite stayed behind. The
pre-release and the Amiga redraw the window every twenty frames regardless,
and 2.1 every fifteen ticks, which hid the same gap for up to a third of a
second; here that redraw comes only for animated tiles in view, so the sprite
could stay indefinitely.

**Differences a player will see,** most of them the Amiga's way rather than
the X16's:

- The player has four walk frames, not three, and is drawn holding whichever
  weapon is selected. `PLAYER_ANIMATE` counts 0 to 3.
- Dematerializing shows the player breaking up, as the Amiga and 2.1 do,
  instead of cycling one palette entry: 2.1's eight frames, eight ticks each,
  to the medkit's sound, while the rest of the game waits, as in 2.1. He
  stands for the first, then breaks up, the last frame showing to the end.
- The intro menu pulses the selected option through 2.1's greys and shows
  2.1's credits under it; see "2.1's title: the pulse and the credits".
- The live map is the Amiga's, played on rather than looked at; see below.
- The elevator's floors are on the information panel's bottom row, and the
  current one is inverted the way the Amiga shows it.
- The information panel's text is the game palette's olive green, 790 (entry
  9), softer than the Amiga's AD0 (entry 10). The weapon and item counts stay
  white, and the health bar and the GAME OVER box keep AD0.
- The statistics are written where the Amiga's game-over picture leaves room
  for them.

**The live map is played on, as on the Amiga.** TAB, or SELECT+LEFT on the
pad, puts the whole 128x64 map where the playfield was, two pixels by two a
square in the Amiga's colours, 20 lines from the top; the game carries on, and the
player can walk, fire, search and use items with it up. TAB again puts the
playfield back. SHIFT+TAB, or SELECT+DOWN, shows the robots on it or stops,
with the map up or not, and the choice stays; it starts off. Those are the
Amiga's main build's keys -- its arcade build steps through all three on TAB.
None of them repeats when held -- each press is one step -- and all work in
the elevator panel too. The cursor for searching and moving is not shown over
the map, as on the Amiga.

- **Dots.** The player blinks white and black, about thirteen frames each.
  Robots of a moving kind are white once asked for, and rafts always, unless
  the player is on one. Every vblank wipes the dots that moved and then draws
  them all, the player last; the Amiga does both in one pass and can lose a
  dot to the wipe of another, which this does not.
- **The map follows MAP.** Every store into MAP in the converted AI -- doors,
  explosions, blown canisters, a moved object, the raft, the trash compactor
  -- is `JSR MAP_STORE` rather than `STA ($04),Y`. `MAP_STORE` makes the
  store and, with the map up, draws the square again. The big explosion's
  centre is a unit rather than a tile, so `LIVEMAP_BLAST` draws its colour
  there, as the Amiga does. The Amiga redraws only some of these squares,
  which leaves an opening door's ends and the trash compactor stale on its
  map; this redraws them all.
- **Drawing.** The map is a mode 3 picture in the tile cache's memory, so the
  playfield's sprites are parked first. `src/livemap.s` draws the whole map
  while the picture is still off the screen -- a load, a lookup and two
  stores a square, a frame and a half for the map, where the C version took
  about eight -- and only then shows it. Shown first, it once put the cache's
  tiles on the screen as a bitmap for those frames.
- **Closing** puts the picture away and lets the playfield come back the way
  a jump does: dark until the tile cache has loaded again, ready to walk.

**The effects are the Amiga's,** where the X16's drew on things the Amiga look
replaced:

- **Fades and flashes.** The Amiga fades its one palette towards a colour, a
  level from 15 down to 0: each channel moves (c - base) * level / 15 of the
  way, rounded down. Here that arithmetic, table and all, runs from the VSYNC
  interrupt in `src/palette.s` whenever the level changes, and writes all six
  palettes in one run, so everything on the screen fades together as it does
  on the Amiga. Each screen fades to black and back over fifteen frames each
  way, the game waiting, and the game starts black and fades the intro in. A
  hit sets `BORDER` and the EMP `BGFLASH`, as before; either now flashes the
  whole screen -- red, or blue -- 60% of the way and back over nine frames, in
  the colour of whichever began first. The entries standing in for the
  Amiga's colour 0 fade with it, and so does the HUD frame's black: palette
  A's entry 0 carries faded black with the opacity bit clear, which sprites
  and text skip and plane 0's background layer draws anyway. The cursor
  flashes too, where the Amiga's hardware sprite does not.
- **Shake.** While `SCREEN_SHAKE` is set and the clock runs, everything sits 3
  pixels right for two frames in every four, as the Amiga's hardware scroll
  puts it: the window's tiles, the units, the player, the HUD frame, the text,
  the picture layer -- the live map included -- and the HUD's pictures, all
  from the vblank work in `src/view.c` and `plat_shake`. The cursor stays
  still, as the Amiga's sprite does. `tests/emu/effects.py` follows each a
  frame at a time. The emulator's frame boundary can fall part way through
  that work, so a sample can show the frame before, and where it falls moves
  with any change to the code's timing: once step B's dematerialize was in,
  it fell just before the player's record each time the shake went off, and
  none of the times it came on. So each sample is checked against its own
  frame or the one before, never two back and never ahead.
- **The cinema marquee** is six characters of `CINEMA_MESSAGE` across the
  middle row of tiles 20 to 22, white on black in the C64 font, a character
  on every twenty ticks of the AI, so it stands still with the animated tiles
  whenever the robots do. The Amiga writes them into the screen after drawing
  the tiles; here they are written into the tiles' cache slots, so the text
  scrolls, hides and blacks out with them. A unit standing on a cinema shows
  over its text, where the Amiga leaves the text out.
- **Choosing a square** for search, push or an item turns the player to face
  it whatever chose it -- arrows, the move keys or the pad -- as on the
  Amiga; the X16 turned him only for the arrows.
- **Keys.** F2 cycles the item, the Amiga's key and 2.1's, where the
  pre-release used F3; F6 turns the music off and on, through the intro and
  the endings too, as the X16 and the Amiga keep it, and in play SHIFT+M does
  the same, 2.1's key; TAB turns the live map on and off and SHIFT+TAB its
  robots, which start off and stay as they were set -- the Amiga's main
  build, where its arcade build steps through all three on TAB. On the pad,
  SELECT+DOWN is the robots, as the CD32 pad's PLAY+DOWN. SHIFT+C is the
  cheat both the X16 and the Amiga have, which this port had dropped: every
  key card and a hundred of each kind of ammunition and item. SHIFT+[ and
  SHIFT+] are 2.1's effects volume, in play only, down and up a step from 10
  to anywhere between 0 and 15: the console shows "new fx volume:  0x" with
  the hex digit, and a beep at the new level, or the error sound at either
  end. 2.1 sets the VERA's PCM volume with it; here it moves the levels the
  OPL2 hears, 2.25 dB a step from the DOS level at 10, and at 0 the key
  never goes on (`src/sound.s`). The music is not touched, as on 2.1. The
  custom keys refuse ESC, as 2.1's do (`SCK01`,
  $59F2) and the pre-release's did not: the game loop tests the thirteen
  before ESC, so ESC bound to one of them left no way to pause.
- **INIT_GAME's pause** before the player can move, `KEYTIMER` 30, starts once
  the level has faded in, so it is the same pause it always was on screen.

**The AI60 and AI300 checkpoints come after the probe is written.** They used
to be printed first, and a frame could end between the line and the probe, so
a test that read the probe at the line read the previous pass. (The game prints
nothing now: the checkpoints are the probe's `PROBE_CHECK` byte; see
`docs/test-abi.md`.) Drawing with
sprites changed how long a pass takes and moved that edge. `emu.ai` reads the
same checksums as before.

## X16 2.1's art and maps

David Murray's version 2.1 of the X16 game is a build with no source, and
where it differs from the pre-release the RP6502 version follows it. The files
the build reads from it are in `assets/src/x16/`. The
Amiga look above stays as it is: the HUD, the live map, the facing rules, the
effects. What comes from 2.1:

| What | From |
|---|---|
| the 18 maps and their names | `LEVEL-A` .. `LEVEL-R`; `ROBOTS.PRG` at $3F8F |
| the difficulty, applied to each map | `SET_DIFF_LEVEL`, which 2.1's INIT_GAME calls |
| the title picture | `title.bin`, cut to 320x200 by `assets/convert/clean_title.py`; its palette at $308E |
| the intro robot's eyes | `faces.bin`, which is `THREE_FACES` at $2E7E |
| the player | `sprites.bin` 0-47, 96 dead, 88-95 dematerializing |
| the robots and their wrecks | `sprites.bin` 48-53, 60-75, 97-99 |
| the bomb, the canister about to blow and the magnet | `sprites.bin` 85, 103 and 86 |
| the shots and the small explosion | `sprites.bin` 76-84 |
| each robot's first frame | `INIT_UNIT_SPRITES`, which 2.1's INIT_GAME calls |
| the sprites' palette, as palette b | `ROBOTS.PRG` at $30CE |
| tiles 155 and 246, the big explosion | `tiles.bin`; its palette at $30AE |
| the cursor's icons | `sprites.bin` 100-102 |
| the magnifier circling during a search | `SEARCH_GLASS_CIRCLE` at $4CE9 |

Everything else that draws is still the Amiga's: the other tiles and the
animated ones, the electrocuted water droid's sparks among them, the HUD
with its pictures and text colours, the game-over picture and the font. The
one colour that is neither is the information panel's text, 790, this
version's own choice (see "Differences a player will see" above).

The rest of 2.1's art -- the title, the playfield's sprites and the two tiles
-- is its reworking of the Amiga's, not new art: its player frames are the
Amiga's but for a few pixels once lined up, its dematerializing frames are the
Amiga's moved a pixel, and its title is the Amiga intro with a new menu frame.
So it keeps the Amiga art's credit -- Vesa Halttunen's port, CC BY 4.0 --
beside 2.1's, and the README gives both; only the eyes, the cursor icons and
the maps are 2.1's own.
`docs/size-budget.md` has what the change cost.

**The maps.** `assets/convert/conv_level.py` turns `LEVEL-A` .. `LEVEL-R` into
`level-a` .. `level-r`, and the pre-release's fourteen in `assets/src/levels/`
are gone. 2.1's files have no 256-byte filler between the units and the map,
and their load address, $7D00 in `LEVEL-A` and $5D00 in the rest, is ignored,
as 2.1 ignores it. Against the pre-release's maps:

- a to j are the same, but for one byte of f: the tile at 41,2 is 10 where it
  was 7, a wall either way.
- k, 11-river death, is new, so bunker, castle robot, rocket center and pilands
  are l to o where they were k to n.
- p, q and r -- 16-grand river, 17-power plant and 18-pi-base -- are new.

`MAP_NAMES` holds 2.1's eighteen names, `MAP_COUNT` in `game.h` is 18, and the
menu's map cycle wraps there. The new maps need nothing new from the game: they
use no unit type the others do not, and 2.1's tile attributes are
`TILESET.GFX`'s byte for byte. The only map tile they alone use is 164, once,
in level-r at 72,9, beside a magnet hidden at 72,8. Tile 164 is blank in both
the Amiga's tiles and 2.1's, so that square draws black, exactly as on 2.1; it
looks like a stray, and it stays, since 2.1 is the one to match.
`tests/emu/levels.py` boots all eighteen and checks the menu's name and the
start square against 2.1's own files, and that the cycle wraps after the last.

**Music numbering.** `level_song` still picks one of the three in-game songs by
`SELECTED_MAP % 3`, so the maps get their songs by 2.1's numbers, and bunker,
castle robot, rocket center and pilands each play a different one than before.
2.1's own table has four songs; the music is a later step.

**The title.** 2.1's `title.bin` is the Amiga intro reworked: 2.1's own menu
frame, whose boxes are empty for the menu's text, and forty more lines of
floor below, making it 320x240, with a COMMANDER X16 logo on them.
`assets/convert/clean_title.py` cuts it to the 320x200 the RP6502 version shows,
which takes the logo's words with the forty lines, and puts back from the
Amiga intro the 715 pixels where the logo's X reaches above line 200, in the
box 88-160 x 174-199. Every other pixel is 2.1's. So it differs from the Amiga
intro in three places, all 2.1's own and not to be "fixed": the menu frame, the
empty box where the eyes go, and 60 pixels of 2.1's floor in lines 194-199,
outside the logo's box. `tests/assets/verify_assets.py` checks the picture
against `title.bin` itself everywhere but that box.

**Its colours.** 2.1's title palette is the Amiga intro's sixteen colours in
another order, but for the white: 2.1's is FFF where the Amiga's is EEE.
`conv_amiga.py` re-indexes the picture and the eyes into the Amiga intro's
order, matching by colour, so `_amiga_pal_intro` is the Amiga's palette with
entry 14 changed from EEE to FFF. The menu's colours, 14 for the selected option
and 15 for the rest, keep their meaning. A title palette with any other
difference fails the build.

**The eyes.** 2.1 draws one of three 16x10 strips, by difficulty, at 234,75:
its tables at $27C9 and $27D3 give lines 75-84 at x 234, and $2771 writes
eight bytes a line from $2E7E plus 80 times `DIFF_LEVEL`.
`plat_change_difficulty_level` does the same into the picture in XRAM. The box
they go in is empty in 2.1's picture, black and 034 only, so the eyes shown are
only ever the strip's, and the mouth below is part of the picture and does not
change. The Amiga's 16x24 faces are no longer drawn: `faces.png` stays in
`assets/src/amiga/` as shipped art, and the program is 336 bytes smaller.

**The text at +8.** The intro's text plane sits eight lines below the grid,
where the Amiga's sat five, so the menu's rows 1-4 and the map name's row 7
land exactly on 2.1's rows 2-5 and 8, inside its picture's empty boxes; at five
the first option and the map's name would sit on the frame. The boxes are
empty, so `plat_display_menu` writes all four options, as it always has.
`tests/emu/title.py` checks the picture with each of the three strips, its
palette, the text plane's place and palette, and the menu's cells.

**2.1's title: the pulse and the credits.** The selected option pulses through
2.1's `SPRITECOLCHART` -- 000, 555, 888, CCC, FFF and back -- a step every seven
frames, counted by the interrupt as 2.1's is. Under the MAP box, text rows
14-17 and columns 1-20 (2.1's 15-18 with the text eight lines down), the
credits fade in eight ticks a step through 555, 888, CCC to white, hold 255
ticks, fade out, and the next page follows twenty ticks later, as 2.1's
`TITLE_CREDITS_TICK` ($280F) does; the first after power-on waits 256 ticks,
and the state carries over between visits to the title. The pages are 2.1's
own first three, word for word ($2966): 6502 assembly, music and pixel art.
Its fourth credits a sound library this version does not use, and is left out.
2.1 writes these colours into the text cells' colour bytes. Here the option's
cells keep ink 14 and the credits' ink 13, and `pal_title_inks` puts the
title's two colours into those entries of `pic_text` in place of the picture's,
faded with everything else, until `pal_picture` or `pal_picture_black` brings
the next screen's; the picture's own white, in `pic`, is untouched. 2.1's clear
colour, its 0, is `PAL_CLEAR`, an entry with no opacity. `tests/emu/title.py`
follows the pulse and a whole credits page frame by frame.

**The sprites.** 2.1's `sprites.bin` is 104 sprites of 32x32 in its unit
palette, at $30CE. The playfield's are 24x24, and 2.1 draws its art from the
top left, so `conv_amiga.py` cuts each to 24x24 there. That drops 13 pixels
in five sprites, all ends of outlines -- two of the evilbot's frames, a pistol
shot, the dead player and the hoverbot's wreck -- and any other loss fails the
build. They are 2.1's reworks of the Amiga's, and look it: the hoverbots have
a tilted bulb, the evilbot's frames facing down, right and up are retouched,
and the bomb and the magnet have a black outline. Some sit a pixel off the
Amiga's, where 2.1 places them: the rollerbot's wreck a pixel higher, and the
player's odd walk frames a pixel to the left, so he shifts a pixel as he
walks, as on 2.1. 2.1's `tiles.bin` is the Amiga's tiles in 2.1's tile
palette, at $30AE, but for two it retouched, 155 and the big explosion, 246,
which come from it, and the units it draws as sprites, which it leaves blank.
The build checks every other tile against the Amiga's, and
`tests/assets/verify_assets.py` checks every converted sprite and tile in
colour against 2.1's own pixels through 2.1's own palettes.

**Their colours.** The robots, their wrecks, the bomb, the canister about to
blow and the magnet draw with palette b, which is 2.1's unit palette with its
entries 2 and 5 swapped: clear, black, white, 789, ABC, 457, then the game
palette's last ten. The Amiga keeps a sprite's black outline in colour 0, with
a separate mask; here 0 is the clear one, so black had moved to an entry the
robots' frames left free, 12. That is B70, which ten of 2.1's sprites use -- a
pixel each in the hoverbots, the rollerbots, an evilbot frame and the
rollerbot's wreck, two in the evilbot's wreck and the bomb -- so b takes 2.1's
own order instead, where black is 1 and 039, the one game colour no unit
sprite has, is left out. With white at 2, entries 0-3 are clear, black, white
and 789, all a 2bpp image in black and white needs, so 2.1's cursor icons can
be drawn with b as it stands.
`_amiga_pal_b_order` gives the game colour of each entry, and `src/palette.s`
builds b from it and fades it with the rest. The player keeps palette a, the
game palette with black at 8: 2.1's player frames never use 560, the colour
there. The shots and the explosions have no black and draw with fg.

**Dematerializing** is 2.1's `DEMATERIALIZE` ($5A1C): the medkit's sound,
then 2.1's eight frames, 88-95, which it puts in `UNIT_TILE` as 2.1's does,
eight ticks each. It spends those 64 ticks inside the AI pass, as 2.1's does,
so nothing else in the game moves meanwhile -- no robot, door or animated
tile -- while the interrupt keeps the clock, the music, the flashes and the
keys going; a key pressed then waits in the queue, which holds seven. The
spin calls `view_idle`, as the game's other waits do, so the frames still load
and show; where 2.1 calls `DRAW_UNIT_SPRITES`, at the start and at each frame,
the port plans the window with `DRAW_MAP_WINDOW` and the player's frame with
`DISPLAY_PLAYER_SPRITE`. The probe and `PROBE_AT_AI60` wait with the rest. The
pre-release ran it as an ordinary unit, every other tick for 48 passes,
cycling a palette entry, with no sound, and the port first showed the eight
frames on that counter, ten to twelve ticks apiece, while the robots went on;
from the pad starting it, a transport now takes 71 ticks where it took about
101. 88 is the player standing, facing down, and 89-95 are the Amiga's seven
frames moved a pixel up and, all but the last, a pixel left. So against the
Amiga's he stands for the first frame, the break-up comes a step later and a
pixel up and left, and its last frame stays to the end, where the Amiga showed
nothing.
`tests/emu/units.py` watches a transporter frame by frame: all eight in turn,
each of the middle six for eight frames, the medkit's sound as they start, and
a hoverbot set going in the pad's room standing still throughout.

**More of 2.1's frames.** Three units draw as 2.1 draws them, where the
pre-release had fewer frames or the Amiga's tile:

- The rollerbot has 2.1's four frames, 48-51, stepping every fourth run
  ($15FA), where it had two; they are unit tiles 164-167. 2.1 steps on from
  any tile but its last; here, as in `EVILBOT`, only the four step, and
  anything else starts again at 164.
- The small explosion has 2.1's five, 80-84, a tick each ($1D6D), where it
  stopped after four, so it lasts a tick longer, and the fifth covers the
  player as the others do. 84 is the Amiga's tile 252, pixel for pixel.
- The canister about to blow is 2.1's sprite 103 ($19B5), drawn with palette
  b, where it was the Amiga's tile 131. It is a whole square, floor and all.
  One thing goes past 2.1: a canister a pistol shot sets off gets 131 there
  ($1C59), not 103, and 131 is past 2.1's 104 sprites, so it does not draw
  as the canister. Here both draw sprite 103.

The three bank records the water droid's sparks no longer need make room for
the two new rollerbot frames and the explosion's fifth, so the bank stays at
38 records and XRAM does not move. `tests/emu/units.py` follows the
rollerbot and the explosion a frame at a time, checking each frame drawn, the
explosion's last one on the player, and the canister's sprite and palette.

**Each robot's first frame.** 2.1's INIT_GAME calls `INIT_UNIT_SPRITES`
($3B9F) once the map is loaded, before `SET_DIFF_LEVEL`: each robot in slots
1-27 gets its kind's first frame. The pre-release set none, so until a robot
first ran, which takes up to 28 ticks, it showed the last game's tile, or
after power-on nothing. `init_game` does the same now, in the same place. 2.1's
hoverbots start on its sprite 56, which has no image here; they start on 99
instead, which `HOVAN` makes 98 on their first step, as 2.1's makes 56 its
52, so from then on the two frames take turns as 2.1's do. And past 2.1:
`UNIT_DIRECTION`, which only this version keeps, was never reset either, so
the same loop faces slots 1-27 down, and an evilbot starts on 2.1's own first
frame, 60, rather than the way it faced in the last game.
`tests/emu/difficulty.py` pokes a stale tile and facing into every slot at the
menu and checks both at the start of the level.

**The Amiga's rules stay** where 2.1 draws a case another way: just
transported within a level the player shows frame 1, facing down with no
weapon, where 2.1 shows 88; transported off it he is hidden, where 2.1 leaves
95; each robot leaves its own wreck, where 2.1 has one for all; and the
evilbot faces the way it last tried to walk, where 2.1 shows only its frames
facing down.

**The cursor** is 2.1's icons, `sprites.bin` 100-102, in place of the Amiga's
frame: `CURSOR_ON` picks the arrows for placing a bomb or a magnet, the
magnifier for searching or the hand for moving, as 2.1's table at $383A does.
They are clear, black and white only, and 25 pixels square at most, so each is
28x28 -- mode 5's sizes go up in fours -- at 2bpp, 196 bytes, drawn with palette
b, whose first four entries are clear, black, white and 789. The three take 588
bytes of XRAM where the Amiga's 1bpp frames took 336; a 4bpp copy would not
have fitted below the probe. Like 2.1's they have no frame, and their top left
is two pixels right of the cell's and one down, where 2.1 puts them. The rest
is as it was: the live map hides the cursor, shake leaves it still, and
choosing a square turns the player, as on the Amiga.

**The circling magnifier.** While a search's eight dots go down, 2.1 moves the
magnifier round its square: the search loop calls `SEARCH_GLASS_CIRCLE`, at
$4CE9, before each `BACKGROUND_TASKS`, and every fifth tick it steps clockwise
from the top, four pixels out, by its tables at $4D4F and $4D57. `items.s`
makes the same call, to `plat_search_glass`, and the search's 144 ticks make
28 or 29 steps, three and a half times round. Neither the step nor the count of
ticks is ever reset, in 2.1 or here, so a search picks the circle up where the
last one left it -- a step can come on its very first frame -- and the cursor
goes when the search ends, to come back at its normal place next time. With
the live map up nothing shows, and the counts go on; 2.1 has no live map to
search under.

One change is deliberate: the ticks are counted from the frame counter. 2.1
counts a tick when it finds `BGTIMER1` set, and `BACKGROUND_TASKS`, called
next, clears it, so a tick that comes between the two reads is lost; by its
cycle counts that is about half of each pass, which makes its own pace nearer a
step in ten ticks, and uneven -- an estimate, not a measurement. Here
`BACKGROUND_TASKS` starts with `VIEW_HOOK`, which would make that gap most of
the loop, and the magnifier would hardly move. So `plat_search_glass` counts
each new `IRQ_FRAME` instead, and steps exactly every `GLASS_TICKS`, 5, the
rate 2.1's code asks for; 10 would be nearer 2.1's. `tests/emu/cursor.py`
pins `GLASS_TICKS` at 5, checks each icon's sprite record and follows the
magnifier a frame at a time through two searches: every step in turn, each
`GLASS_TICKS` frames long but the first, which can show a frame less when it
comes on the search's first pass, no frame missed, and the second going on
from the first. A step that falls on a search's last tick is made in the pass
that ends the search and puts the cursor away, so it never shows; whether the
loop sees that tick at all depends on where in a pass its frame begins, which
any change to the code's timing can move, so the next search can start a step
later than the last one shown, and the test allows that one case. Then, with
the live map up, that nothing shows while the search's dots go down, and that
the next search starts the 28 or 29 steps further round that the hidden one
made.

### A restored omission: SET_DIFF_LEVEL

The menu's DIFFICULTY used to change nothing but the intro robot's face and the
word on the statistics screen. The pre-release's INIT_GAME calls
`SET_DIFF_LEVEL` straight after `MAP_LOAD_ROUTINE` (`x16Robots.ASM` 460-464),
and the port's `init_game`, which replaced INIT_GAME, had left the call out.
`src/game/difficulty.s` is that routine, converted and unchanged, and
`init_game` calls it right after the level is read, before the timers are set.
Easy doubles the quantity of every hidden item but the keys -- level-a's pistol
comes with 200 rounds -- and hard turns every patrolling hoverbot into one that
hunts from the start; normal changes nothing. 2.1 has the same 67 bytes at
$55FB and calls them from the same place, and the PET and C++ versions do the
same, so this puts the original back rather than changing a rule.
`tests/emu/difficulty.py` checks all three on level-a and level-r against a
model of the routine applied to 2.1's files.

### The C++ ports' rules, which 2.1 settled

Before 2.1 was the version to follow, the plan was to adopt the rules of the
Amiga and SDL C++ ports, the latest then known: their tile attribute table,
their robot attack rule, their timers, River Death as map 11, and the search's
fall-through fixed. 2.1's `ROBOTS.PRG` settled each one:

- **Tile tables, attack rule and timers: the X16's.** 2.1's `DESTRUCT_PATH`
  and `TILE_ATTRIB` ($30EE, $31EE) are `TILESET.GFX` byte for byte, where the
  C++ table differs in four entries. Its `ROBOT_ATTACK_RANGE` ($2172) is the
  X16's bump rule: a robot attacks when it tries to step onto the player, not
  when it is beside him. It keeps every X16 timer store, about 1.2 times the
  PET's that the C++ ports use, and the same tick. So the C++ versions of all
  three were dropped.
- **River Death and the map order: 2.1's**, which has it at 11, as the C++
  ports do, and three more maps after the fifteen.
- **The difficulty: restored** from the pre-release's own code, above.
- **The fall-through: fixed**, though 2.1 keeps it; see "Items, searching,
  pushing and firing".
