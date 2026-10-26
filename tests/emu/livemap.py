"""The live map, played on as on the Amiga.

TAB puts the whole 128x64 map where the playfield was, two pixels by two a
square, and the game carries on: this walks with it up. Every square is read
back from XRAM and compared with MAP through amiga_livemap, so the colour
table, the row doubling and the addressing are all checked square by square,
and checked again while a door opens and closes beside the player, which is
the game writing tiles into MAP: MAP_STORE has to draw each one as it happens.
The dots: the player blinks white and black, the robots show white once SHIFT+TAB
asks for them. And the map never shows before it is drawn, which it once did,
and the playfield comes back whole when it goes.

Run on level-a, whose door 32 at 32,32 is unlocked and opens for a player
below it.
"""
import struct
import sys

import rp6502

import petscii

T = petscii.amiga_tables()
COLOUR = T["amiga_livemap"]
ROBOTS = (1, 2, 3, 4, 5, 9, 17, 18)
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def overlay(emu):
    """The picture layer's x, y, width, height, data and palette."""
    return struct.unpack("<hhhhHH", petscii.xram(emu, "XRAM_CFG_OVERLAY+2", 12))


def units(emu):
    t = petscii.ram(emu, "UNIT_TYPE", 48)
    x = petscii.ram(emu, "UNIT_LOC_X", 48)
    y = petscii.ram(emu, "UNIT_LOC_Y", 48)
    return t, x, y


def mismatches(emu):
    """Squares whose two bytes are not their tile's colour, leaving out the
    squares that carry dots: the player's, the rafts', and the robots' once
    they are asked for. A door is a unit too, but its square is a tile."""
    mp = petscii.ram(emu, "MAP", 128 * 64)
    pic = petscii.xram(emu, "XRAM_VIEW", 128 * 256)
    t, x, y = units(emu)
    robots = petscii.probe(emu)["LIVEMAP"] == 2
    skip = {(x[i], y[i]) for i in range(48)
            if i == 0 or t[i] == 22 or (robots and i < 28 and t[i] in ROBOTS)}
    bad = []
    for my in range(64):
        for mx in range(128):
            want = COLOUR[mp[my * 128 + mx]]
            a = my * 256 + mx
            if (pic[a], pic[a + 128]) != (want, want) and (mx, my) not in skip:
                bad.append((mx, my))
    return bad


def behind(emu):
    """The squares still not their tile's colour a frame later. A dot follows
    its unit at the next vblank, so a square a robot has just left can show
    its dot for one frame, as the Amiga's does; a square the map failed to
    redraw stays wrong."""
    first = set(mismatches(emu))
    emu.cmd("run 1")
    return sorted(first & set(mismatches(emu)))


def square(emu, x, y):
    a = petscii.xram(emu, f"XRAM_VIEW+{y * 256 + x}", 1)[0]
    b = petscii.xram(emu, f"XRAM_VIEW+{y * 256 + 128 + x}", 1)[0]
    return a if a == b else None


def parked(emu):
    pf = petscii.xram(emu, "XRAM_PF", 110 * 10)
    return all(struct.unpack_from("<h", pf, i * 10 + 2)[0] == 240
               for i in range(110))


def tap(emu, key):
    petscii.tap(emu, key, hold=4, after=4)


with rp6502.Emu() as emu:
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')

    # Open: a frame at a time, the picture is either off the screen or showing
    # the finished map, over a playfield parked out of the way.
    emu.cmd("press tab")
    for f in range(20):
        emu.cmd("run 1")
        if overlay(emu)[0] == 0:
            break
    else:
        fail("TAB did not bring up the map")
    emu.cmd("release tab")
    if overlay(emu) != (0, emu.sym["SCREEN_TOP"] + 20, 256, 128, emu.sym["XRAM_VIEW"],
                        emu.sym["XRAM_PAL_GAME"]):
        fail(f"the map's picture is {overlay(emu)}")
    if not parked(emu):
        fail("the playfield shows under the map")
    bad = mismatches(emu)
    if bad:
        fail(f"{len(bad)} squares not drawn when the map came up, first {bad[:4]}")
    emu.cmd("run 4")
    if petscii.probe(emu)["LIVEMAP"] != 1:
        fail("the probe does not say the map is up")
    emu.cmd('shot "livemap.png"')

    # The player blinks white and black, nothing else.
    p = petscii.probe(emu)
    seen = set()
    for _ in range(40):
        emu.cmd("run 1")
        seen.add(square(emu, p["PLAYER_X"], p["PLAYER_Y"]))
    if seen != {0x11, 0x00}:
        fail(f"the player's square showed {sorted(map(str, seen))}")

    # Walking with the map up: the dot goes with him, and the map comes back
    # where he was.
    x0, y0 = p["PLAYER_X"], p["PLAYER_Y"]
    tap(emu, "l")
    emu.cmd("run 4")
    p = petscii.probe(emu)
    if (p["PLAYER_X"], p["PLAYER_Y"]) != (x0 + 1, y0):
        fail(f"no step with the map up: at {p['PLAYER_X']},{p['PLAYER_Y']}")
    mp = petscii.ram(emu, "MAP", 128 * 64)
    if square(emu, x0, y0) != COLOUR[mp[y0 * 128 + x0]]:
        fail("the square the player left still shows his dot")
    if square(emu, x0 + 1, y0) not in (0x11, 0x00):
        fail("the square the player went to shows no dot")

    # SHIFT+TAB: the robots too, white.
    emu.cmd("press lshift")
    tap(emu, "tab")
    emu.cmd("release lshift")
    if petscii.probe(emu)["LIVEMAP"] != 2:
        fail("SHIFT+TAB did not show the robots")
    for _ in range(10):
        emu.cmd("run 1")
        t, x, y = units(emu)
        missing = [i for i in range(1, 28) if t[i] in ROBOTS
                   and square(emu, x[i], y[i]) != 0x11]
        if not missing:
            break
    else:
        fail(f"robots without a white dot: {missing}")

    # A door opening by the player, and closing behind him: the game writes
    # its tiles into MAP a frame at a time, and each one is on the map at once.
    door = [32 * 128 + 31, 32 * 128 + 32, 32 * 128 + 33]
    closed = [petscii.ram(emu, f"MAP+{a}")[0] for a in door]
    emu.cmd("poke UNIT_LOC_X 32")
    emu.cmd("poke UNIT_LOC_Y 33")
    late = set()
    for f in range(30):
        emu.cmd("run 1")
        late.update(behind(emu))
    if [petscii.ram(emu, f"MAP+{a}")[0] for a in door] == closed:
        fail("the door did not open, so the map had nothing to follow")
    emu.cmd(f"poke UNIT_LOC_X {x0 + 1}")
    emu.cmd(f"poke UNIT_LOC_Y {y0}")
    for f in range(60):
        emu.cmd("run 1")
        late.update(behind(emu))
        if [petscii.ram(emu, f"MAP+{a}")[0] for a in door] == closed:
            break
    else:
        fail("the door did not close again")
    if late:
        fail(f"squares left behind MAP while the door moved: {sorted(late)}")

    # TAB again: the picture goes, and the playfield comes back once the
    # tile cache has loaded again: every tile, unit and the player's frame,
    # which changed while he walked with the map up.
    tap(emu, "tab")
    if petscii.probe(emu)["LIVEMAP"] != 0:
        fail("the second TAB did not put the playfield back")
    if overlay(emu)[0] != -320:
        fail("the map's picture is still on the screen")
    petscii.check_playfield(emu, "after the map", fail)
    if parked(emu):
        fail("the playfield did not come back")

    # The pad's SELECT+LEFT does what TAB does and SELECT+DOWN what SHIFT+TAB
    # does, once a press: held for half a second, the map opens and stays
    # open, with the robots, since that choice outlasts the map; short taps
    # still count, and neither walks the player.
    emu.cmd("pad 0 connect")
    emu.cmd("run 30")
    emu.cmd("pad 0 press select")
    emu.cmd("pad 0 press left")
    emu.cmd("run 30")
    emu.cmd("pad 0 release left")
    emu.cmd("pad 0 release select")
    emu.cmd("run 4")
    if petscii.probe(emu)["LIVEMAP"] != 2:
        fail(f"SELECT+LEFT held: map state {petscii.probe(emu)['LIVEMAP']}, not 2")
    for button, want in (("down", 1), ("down", 2), ("left", 0)):
        emu.cmd("pad 0 press select")
        emu.cmd(f"pad 0 press {button}")
        emu.cmd("run 2")
        emu.cmd(f"pad 0 release {button}")
        emu.cmd("pad 0 release select")
        emu.cmd("run 4")
        if petscii.probe(emu)["LIVEMAP"] != want:
            fail(f"SELECT+{button.upper()} tapped: map state "
                 f"{petscii.probe(emu)['LIVEMAP']}, not {want}")
    p = petscii.probe(emu)
    if (p["PLAYER_X"], p["PLAYER_Y"]) != (x0 + 1, y0):
        fail("SELECT+LEFT walked the player")
    emu.cmd("pad 0 disconnect")
    petscii.check_playfield(emu, "after the pad's map", fail)

sys.exit(1 if failures else 0)
