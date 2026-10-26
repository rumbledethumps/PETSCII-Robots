"""The menu's difficulty changes the level, as SET_DIFF_LEVEL does.

INIT_GAME runs SET_DIFF_LEVEL on the map it has just loaded: easy doubles the
quantity of every hidden item in slots 48-63 but the keys, hard turns every
hoverbot in slots 0-27 that patrols (type 2 or 3) into one that hunts (4), and
normal changes nothing. This picks each difficulty on the menu, starts level-a
and level-r, and compares the unit tables in RAM with a model of the routine
applied to X16 2.1's own LEVEL files. Before it, 2.1's INIT_UNIT_SPRITES gives
each robot in slots 1-27 its first tile, and this version faces every unit
there down: of the tiles and facings a last game could have left, poked at the
menu, only the tiles of what is not a robot stay.

The tables are read the moment play begins, PROBE_AT_PLAY, which is before any
unit could have changed them: init_game gives slot i the timer i, so the first
AI pass runs no unit and only counts timers down, and the hidden items in
slots 48-63 never run, since their types are past the AI's chart.
"""
import sys

import rp6502

import petscii

NAMES = ("easy", "normal", "hard")
# INIT_UNIT_SPRITES ($3B9F): type -> the robot's first UNIT_TILE. 2.1's
# hoverbots start on its sprite 56, drawn here as 99.
START = {2: 99, 3: 99, 4: 99, 5: 99, 9: 100, 17: 164, 18: 164}
FACING = 1                              # UNIT_DIRECTION in slots 1-27, down
STALE_TILE, STALE_FACING = 246, 3       # what a last game could have left
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def model(diff, raw):
    """UNIT_TYPE and UNIT_A after SET_DIFF_LEVEL, x16Robots.ASM 4369-4407."""
    t, a = bytearray(raw[0:64]), bytearray(raw[192:256])
    if diff == 0:                                   # SET_DIFF_EASY
        for s in range(48, 64):
            if t[s] not in (0, 128):                # nothing there, or a key
                a[s] = a[s] * 2 & 255               # ASL UNIT_A,X
    elif diff == 2:                                 # SET_DIFF_HARD
        for s in range(28):
            if t[s] in (2, 3):
                t[s] = 4
    return bytes(t), bytes(a)


# The model has something to find. On level-a easy doubles thirteen items --
# the pistol's 100 rounds among them, in slot 51 -- and leaves the three keys
# in 48-50 alone, and hard sets thirteen hoverbots hunting. On level-r a
# plasma gun with no shots, slot 52, stays at none.
A_RAW = petscii.x16("LEVEL-A")[2:]
R_RAW = petscii.x16("LEVEL-R")[2:]
easy_t, easy_a = model(0, A_RAW)
hard_t, hard_a = model(2, A_RAW)
if [s for s in range(64) if easy_a[s] != A_RAW[192 + s]] != [*range(51, 64)]:
    fail("level-a: the model's easy does not double slots 51-63")
if (easy_a[51], easy_a[52], easy_a[60]) != (200, 24, 100) or easy_a[48:51] != A_RAW[240:243]:
    fail("level-a: the model's easy quantities are not 200, 24 and 100, keys kept")
if [s for s in range(64) if hard_t[s] != A_RAW[s]] != [*range(1, 11), 12, 14, 15]:
    fail("level-a: the model's hard does not turn slots 1-10, 12, 14 and 15")
if (R_RAW[52], R_RAW[192 + 52], model(0, R_RAW)[1][52]) != (132, 0, 0):
    fail("level-r: slot 52 is not an empty plasma gun that stays empty")

for level, raw in (("a", A_RAW), ("r", R_RAW)):
    for diff in (0, 1, 2):
        where = f"level-{level} {NAMES[diff]}"
        want_t, want_a = model(diff, raw)
        with rp6502.Emu() as emu:
            petscii.menu(emu, level, diff)
            # What a last game could have left: a tile no robot starts with,
            # and the facing right.
            emu.cmd("poke UNIT_TILE+1 " + " ".join([str(STALE_TILE)] * 27))
            emu.cmd("poke UNIT_DIRECTION+1 " + " ".join([str(STALE_FACING)] * 27))
            petscii.start(emu, level)
            if petscii.ram(emu, "DIFF_LEVEL")[0] != diff:
                fail(f"{where}: DIFF_LEVEL is {petscii.ram(emu, 'DIFF_LEVEL')[0]}")
            got_t = petscii.ram(emu, "UNIT_TYPE", 64)
            got_a = petscii.ram(emu, "UNIT_A+48", 16)
            got_tile = petscii.ram(emu, "UNIT_TILE", 28)
            got_dir = petscii.ram(emu, "UNIT_DIRECTION", 28)
        for s in range(64):
            if got_t[s] != want_t[s]:
                fail(f"{where}: UNIT_TYPE+{s} is {got_t[s]}, expected {want_t[s]} "
                     f"(the file has {raw[s]})")
        for s in range(48, 64):
            if got_a[s - 48] != want_a[s]:
                fail(f"{where}: UNIT_A+{s} is {got_a[s - 48]}, expected {want_a[s]} "
                     f"(the file has {raw[192 + s]})")
        for s in range(1, 28):
            want = START.get(want_t[s], STALE_TILE)
            if got_tile[s] != want:
                fail(f"{where}: UNIT_TILE+{s} is {got_tile[s]}, expected {want} "
                     f"(type {want_t[s]})")
        if set(got_dir[1:]) != {FACING}:
            fail(f"{where}: UNIT_DIRECTION+1..27 are {list(got_dir[1:])}, not all {FACING}")
        hunters = sum(1 for s in range(28) if got_t[s] == 4)
        print(f"{where}: {hunters} hoverbots hunting, "
              f"items {list(got_a)}")

sys.exit(1 if failures else 0)
