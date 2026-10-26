"""Every level loads and plays.

The scripts mostly start on level-a. This boots each of the eighteen from the
menu, as a player would, and checks it against X16 2.1's own files rather than
what the build made of them: the menu shows 2.1's name for the map, the probe
names the level, the player stands on the square 2.1's LEVEL file puts him on,
and the AI is moving units around him. A converter or loader fault in any one
level shows up here by name. Last, the map cycle wraps after the eighteenth.
"""
import sys

import rp6502

import petscii

# 2.1's MAP_NAMES, eighteen sixteen-byte names at $3F8F in ROBOTS.PRG, which
# loads at $0801 after its two-byte load address.
NAMES = petscii.x16("ROBOTS.PRG")[0x3F8F - 0x0801 + 2:][:18 * 16]
NAME_CELLS = "XRAM_CHARS+7*SCR_STRIDE+1*2"     # row 7, column 1, two bytes a cell

failures = []
for i, level in enumerate(petscii.LEVELS):
    data = petscii.x16(f"LEVEL-{level.upper()}")[2:]
    start = (data[64], data[128])           # UNIT_LOC_X[0], UNIT_LOC_Y[0]
    with rp6502.Emu() as emu:
        petscii.menu(emu, level)
        name = petscii.xram(emu, NAME_CELLS, 32)[0::2]
        if name != NAMES[16 * i:16 * i + 16]:
            failures.append(f"level-{level}: the menu names it {name.hex()}, "
                            f"not 2.1's {NAMES[16 * i:16 * i + 16].hex()}")
        petscii.start(emu, level)
        p = petscii.probe(emu)
        got = (p["STATE"], p["LEVEL"], (p["PLAYER_X"], p["PLAYER_Y"]))
        want = (emu.sym["PROBE_STATE_PLAYING"], i, start)
        if got != want:
            failures.append(f"level-{level}: state, level, start {got}, expected {want}")
        # The AI runs from the first frame of play; two seconds is enough for
        # something on every level to have moved.
        emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
        before = petscii.probe(emu)
        emu.cmd("run 120")
        after = petscii.probe(emu)
        if (before["UNITS_LO"], before["UNITS_HI"]) == (after["UNITS_LO"], after["UNITS_HI"]):
            failures.append(f"level-{level}: no unit moved in 120 frames")
        if after["STATE"] != emu.sym["PROBE_STATE_PLAYING"]:
            failures.append(f"level-{level}: left play, state {after['STATE']}")
    print(f"level-{level}: start {start}, {after['ROBOTS']} robots")

# The cycle wraps after the last map: MAP_COUNT presses of CHANGE MAP from the
# first come back to it.
with rp6502.Emu() as emu:
    petscii.menu(emu, "a")
    for _ in range(emu.sym["MAP_COUNT"]):
        petscii.tap(emu, "space")
    name = petscii.xram(emu, NAME_CELLS, 32)[0::2]
    if emu.sym["MAP_COUNT"] != 18 or name != NAMES[:16]:
        failures.append(f"MAP_COUNT {emu.sym['MAP_COUNT']} presses show {name.hex()}, "
                        f"not 2.1's first name")
    print(f"wrap: {emu.sym['MAP_COUNT']} presses, back to the first map")

for line in failures:
    print(line, file=sys.stderr)
sys.exit(1 if failures else 0)
