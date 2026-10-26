# Size budget

RAM available to the program: `$0200–$FEFF` = **64,768 bytes**
(llvm-mos `link.ld`: `ram : ORIGIN = 0x0200, LENGTH = 0xfd00`, `__stack = 0xFF00`).
Zero page available to the compiler: `$20–$FF` = 224 bytes
(`zp : ORIGIN = __rc31 + 1, LENGTH = 0x100 - (__rc31 + 1)`).

## Reference: the X16 assembly build

| | bytes |
|---|---|
| Machine code (6,133 instructions, 2.37 avg) | 14,564 |
| Embedded tables + `!SCR` strings | 3,184 |
| **X16ROBOTS.PRG** | **17,748** |

## Spike 0a — the portable C++ port on llvm-mos

`zeropolis79/PETSCIIRobots-SDL` `petrobots.cpp` (5,892 lines) + `Platform.cpp`, against a
stub `PlatformRP6502` whose every method is a no-op. Character-based tile rendering
(`PLATFORM_SPRITE_SUPPORT` off — it swaps character tiles for image tiles, and mode 1 draws
characters). `PLATFORM_IMAGE_SUPPORT`, `PLATFORM_LIVE_MAP_SUPPORT`, `PLATFORM_COLOR_SUPPORT`,
`PLATFORM_CURSOR_SUPPORT` on; `PLATFORM_MODULE_BASED_AUDIO`, `OPTIMIZED_MAP_RENDERING` off.
Built `-Os -fno-lto -fno-exceptions -fno-rtti`.

| section | bytes |
|---|---|
| `.text` | 34,930 |
| `.rodata` | 282 |
| `.data` | 2,413 |
| `.bss` | 17,442 |
| `.noinit` | 14 |
| `.zp.data` + `.zp` | 48 |
| **RAM used, `$0200–$D94F`** | **55,375** |
| **free** | **9,393** |

Largest `.bss`: `MAP_DATA` 8,960, tileset 6,656, `SCREEN_MEMORY` 1,200 — all real, all
required by the design.

Largest `.text`: `MAIN_GAME_LOOP` 2,310, `main` 1,297, `PLOT_TRANSPARENT_TILE` 1,196,
`MOVE_OBJECT` 1,193, `ELEVATOR_SELECT` 1,141, `GAME_OVER` 1,067, `PLOT_TILE` 968.

### Verdict

**It fits, with 9.4 KB spare — but that spare is the entire budget for work not yet written.**
The stub platform is empty; the real one has to supply video, input, storage, the PSG driver
(~800 B) and the music/SFX data (~1,456 B). A 4–8 KB platform layer leaves 2–5 KB of margin
on a 64 KB machine. Viable, not comfortable.

### LTO is not available

`-flto` fails to link: `relocation R_MOS_ADDR8 out of range: 256 is not in [-128, 255];
references section '.zp.noinit'`. Whole-program LTO allocates more static stack frames into
zero page than the 224 available bytes hold. Swept `-mlto-zp` at 8/16/32/64 (8 came closest,
2 errors rather than 6) and devirtualised the platform class with `final`; neither fixes it.
So the usual llvm-mos size lever is off the table for this codebase, which matches the
warning that llvm-mos has no size-priority option that works.

`PLOT_TILE` at 968 bytes and `PLOT_TRANSPARENT_TILE` at 1,196 are both the hot path and
prime candidates for hand-written `.s` — that would buy size and speed together.

### cc65 is not an option for this path

`cc65-toolchain.cmake` fatals with "cc65 has no C++ compiler". The C path is llvm-mos only.

## Spike 0b — ACME → ca65 conversion

`tools/convert/acme2ca65.py`, **164 lines**, run over all 8,505 lines of ACME source
(`x16Robots.ASM`, `BACKGROUND_TASKS.ASM`, `sounds.asm`, `sounds.inc`, `zsound.inc`, and the
five payload loaders).

- **0 lines the converter could not handle.**
- **0 ca65 errors.**
- **All six programs assemble and link byte-identical to the shipped X16 builds:**

| program | bytes | |
|---|---|---|
| `X16ROBOTS.PRG` | 17,748 | identical |
| `PAYLOAD1.PRG` | 4,141 | identical |
| `PAYLOAD2.PRG` | 6,189 | identical |
| `PAYLOAD3.PRG` | 8,237 | identical |
| `PAYLOAD4.PRG` | 13,681 | identical |
| `PAYLOAD5.PRG` | 3,757 | identical |

PAYLOAD3 and PAYLOAD5 rebuilding bit-for-bit also **proves the carve offsets** for the two
assets that survive only inside them: `CURSORS4BIT.BIN = PAYLOAD3.PRG[47:1583]` (1,536 B) and
`gamepic.rle = PAYLOAD5.PRG[146:3759]` (3,613 B).

### The three things that were not mechanical

Worth recording, because they are the whole difference between "assembles" and "identical":

1. **`!SCR` lowercase.** ACME maps `a`–`z` to screen codes 1–26, i.e. `-0x60`, not the `-0x20`
   of the textbook PETSCII→screencode table. Verified against the binary: `"searching"`
   assembles to `13 05 01 12 03 08 09 0e 07`.
2. **`!ifndef SYM !eof`** means *stop assembling when SYM is undefined*, so everything below it
   is conditional on SYM being **defined** — `.ifdef`, not `.ifndef`. Getting this backwards
   added 3 bytes at the end of `sounds.asm`.
3. **ACME sizes an operand by how the literal is written.** `STA $00C6` is four hex digits, so
   ACME assembles it absolute; ca65 always shortens to zero page. Four sites (`$00C6` ×3,
   `$009E` ×1) need ca65's `a:` prefix. This was the missing 4 bytes.

## Decision: the assembly path

| | assembly (cc65/ca65) | C (llvm-mos) |
|---|---|---|
| Program | **17,748 B** | 37,625 B code+data |
| Resident data | ~14,500 B | 17,442 B |
| **RAM free** | **~47 KB** | **9.4 KB** |
| Behavioural risk | none — provably identical machine code | transliteration, shipped elsewhere |
| LTO | n/a | unusable (zero page overflows) |
| Conversion cost | paid: 164-line script, byte-exact | none |

Assembly wins on every axis that matters here. The 9.4 KB the C path leaves has to absorb the
entire platform layer, the PSG driver and the music data, none of which is written yet; the
assembly path starts with 47 KB free.

**The presentation layer still has to be rewritten** — roughly 2,900 lines of VERA/KERNAL/ZSOUND
code. That new code can be written in **cc65 C and linked against the ca65 objects**, which is
the arrangement cc65 is built for: proven game logic stays as assembly, new platform code is
readable C, and the size budget stays comfortable either way.

## M2 — video bring-up, measured on target

The first ROM: three planes up, the game screen in the bitmap plane, and
`level-a`'s map window drawn into the character plane. Built with cc65.

| segment | bytes |
|---|---|
| `CODE` | 4,741 |
| `RODATA` + `DATA` | 405 |
| `BSS` | 13,872 (tileset 5,120 + level 8,704 + state) |
| **RAM used, `$0200–$4C82`** | **19,586** of 64,768 |

ROM file 226,565 bytes: the code plus 122 KB of levels, two 38,400-byte screens,
the tileset, the font, the palettes and 14 KB of sprites — the whole game in one
self-contained `.rp6502`.

The same source also builds and passes under llvm-mos (232,669 bytes), which is
worth keeping as a second opinion on the C.

### What the on-target test proves

`tests/emu/bringup.txt` checks eleven distinct tiles' character cells against
`conv_tiles.py`'s output with `peek xram:`, so the tileset reorganisation, the
cell address arithmetic and the portal writes are all verified on the machine
rather than by eye. It also peeks `XRAM_FONT + 1` for `$7E`, which confirms the
font really is stored row-major as mode 1 reads it — the failure that would
otherwise show up as the VGA quietly substituting its built-in code page.

## M3 — movement and collision

`src/game/` in ca65 plus the C platform layer, built with cc65.

| segment | bytes |
|---|---|
| `CODE` | 5,746 |
| `RODATA` + `DATA` | 411 |
| `BSS` | 5,202 |
| `LEVELDATA` | 8,704 |
| **RAM used, `$0200–$50FF`** | **20,735** of 64,768 — **44 KB free** |

The 6502 routines themselves are small: `map.s`, `move.s` and `rng.s` together
are about 300 bytes. Most of `CODE` is still the C platform layer.

## M4 — the whole unit AI

`BACKGROUND_TASKS.ASM` in full: the dispatcher and all 24 unit types, plus the
window bookkeeping and the transporter.

| segment | bytes | change |
|---|---|---|
| `CODE` | 11,028 | +5,282 |
| `RODATA` + `DATA` | 1,270 | +859 |
| `BSS` | 5,460 | |
| `LEVELDATA` | 8,704 | |
| **RAM used, `$0200–$69FF`** | **27,135** of 64,768 — **36.7 KB free** |

The AI is 2,022 instructions of the original 6,133, and it cost 5.3 KB against
the roughly 4.8 KB those instructions occupy in the X16 build — so the ported
assembly is carrying its own weight, and the overhead is the C platform layer
around it.

## M5 — items, searching, the console and the HUD

| segment | bytes | change |
|---|---|---|
| `CODE` | 15,871 | +4,843 |
| `RODATA` + `DATA` | 1,297 | |
| `BSS` | 5,549 | |
| `LEVELDATA` | 8,704 | |
| **RAM used, `$0200–$7DFF`** | **31,743** of 64,768 — **32.2 KB free** |

## M6 (part) — the intro screen and menu

| segment | bytes |
|---|---|
| `CODE` | 17,595 |
| `RODATA` + `DATA` | 2,437 |
| `BSS` | 5,558 |
| `LEVELDATA` | 8,704 |
| **RAM used** | **≈34,300** of 64,768 — **≈30 KB free** |

## M6 and M7 — live map, endings, elevator, sound

| segment | bytes |
|---|---|
| `CODE` | 20,469 |
| `RODATA` + `DATA` | 3,910 |
| `BSS` | 5,563 |
| `LEVELDATA` | 8,704 |
| **RAM used** | **≈39,000** of 64,768 — **≈25 KB free** |

The sound engine is about 400 bytes of code and 1,314 of data, against the
1.44 MB of ZSM and ZCM the X16 build carries.

## The Amiga look (step 3a)

The playfield became 77 mode 5 sprites over a 13x9 cache of the Amiga's 24x24
tiles, and the screens, the HUD and the font became the Amiga's. Dropping the
PETSCII tile cells and the blitter paid for the renderer with RAM to spare:

| segment | bytes | before |
|---|---|---|
| `CODE` | 23,736 | 20,983 |
| `RODATA` + `DATA` | 4,950 | 4,239 |
| `BSS` | 1,915 | 5,763 |
| `LEVELDATA` | 8,704 | 8,704 |

XRAM is the tight one: the layout in `src/xram.h` ends at `$FB70`, 656 bytes
below the probe. The tile cache's 33,696 bytes also hold the intro and
game-over pictures and the live map, which are never shown at the same time
as the playfield. The ROM is 342 KB, up from 247 KB, most of it the 101 KB
`images` asset of tiles, player frames and HUD pictures read at run time.

## Step A: 2.1's art and maps

X16 2.1's eighteen maps, its title, sprites, cursor icons and two tiles, and
the difficulty routine. The program got slightly smaller:

| segment | bytes | before |
|---|---|---|
| `CODE` | 29,214 | 28,999 |
| `RODATA` | 4,878 | 5,119 |
| `DATA` | 177 | 177 |
| `BSS` | 3,096 | 3,093 |
| `LEVELDATA` | 8,704 | 8,704 |

The code grew by `SET_DIFF_LEVEL`, 67 bytes, and by 142 bytes of C and 6 of
assembly for the circling magnifier and the cursor's new placing, less 16 for
palette b's shorter loop, and by 16 more in small changes elsewhere. 2.1's three eye strips, 240 bytes, replace the
Amiga's 576-byte faces, which more than pays for the four more map names, 64
bytes, the 15-byte palette order and the magnifier's 16 bytes of tables. Net,
23 bytes less RAM; `BSS` still ends at `$9455`, below `LEVELDATA` at `$9500`.

In XRAM only the cursor changed size: three 28x28 icons at 2bpp, 588 bytes
where the Amiga's 1bpp frames took 336. Everything after it moved up 252, so
the layout now ends at `$FC6C`, 404 bytes below the probe, and 820 are free in
all, counting the 224 between the probe and the PSG and the 192 past it. A
4bpp cursor would have run past the probe.

The ROM is 383,164 bytes, up from 347,687, almost all of it the four new
maps' 34,816; `images` grew 288 for the eighth dematerialize frame, and the
cursor 252.

Step B, X16 2.1's gameplay, the title's pulse and credits, and the keys, left
XRAM as it was: the water droid's sparks moved onto the map, and their three
unit-bank records went to the rollerbot's two extra frames and the small
explosion's fifth. The ROM is 384,511 bytes.

## The OPL2 and the DOS version's sound effects

The PET's sound engine and its 1,314 bytes of patterns and notes went, and the
MS-DOS version's seventeen effects came in as OPL2 register streams, 4,367
bytes in RAM, with a player in the VIA's interrupt:

| segment | bytes | before |
|---|---|---|
| `CODE` | 30,488 | 30,300 |
| `RODATA` | 8,077 | 4,995 |
| `DATA` | 210 | 209 |
| `BSS` | 3,108 | 3,106 |
| `LEVELDATA` | 8,704 | 8,704 |

`LEVELDATA` now starts at `$A600` and ends at `$C7FF`, which leaves 12,032
bytes of RAM free below the 2 KB C stack at `$F700`.

In XRAM the OPL2 takes a whole page, `$FD00`, inside what was free below the
probe; the PSG's 64 bytes at `$FF00` are gone. 628 bytes are free: 148 below
the OPL2's page, and the 480 from `$FE20` to the top. The ROM is 387,831 bytes.

The music added two 512-byte buffers and the streaming, and 1.25 MB of songs
to the ROM:

| segment | bytes | before |
|---|---|---|
| `CODE` | 32,463 | 30,488 |
| `RODATA` | 8,227 | 8,077 |
| `DATA` | 212 | 210 |
| `BSS` | 4,169 | 3,108 |
| `LEVELDATA` | 8,704 | 8,704 |

`LEVELDATA` is at `$B300-$D4FF`, which leaves 8,704 bytes of RAM free below
the C stack. XRAM did not change. The ROM is 1,645,266 bytes.
