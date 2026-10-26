"""Water, as X16 2.1 has it: the RNG, magnets, shorting out and the sparks.

2.1's GENERATE_RANDOM_NUMBER ($1399) is a 16-bit LFSR, RANDOM low byte first,
which starts from zero at power-on and is never reseeded; from zero its first
output is $00, which sends a magnetized robot up. A magnetized robot hovers
($134B), so it can cross water, and an evilbot or a magnetized robot that
finds itself on water shorts out (WATER_CHECK, $1E10): it becomes a water
droid, with the shock sound, and the sparks are the map square's, tiles 140 to
142, stepped once a run while the droid draws nothing (WATER_DROID, $1B61).
After sixty runs the water comes back and the droid is a wreck. The EMP shorts
out whatever is on water in the window the same way, without the shock: a
hoverbot, and a wreck already lying there.

This version keeps what each robot was for its wreck: a magnetized or shorting
robot is the type it had (ROBOT_KIND), so a magnetized rollerbot shot dead, a
rollerbot that shorts out and a wreck shorted again all leave the rollerbot's.
And only a spark tile steps: anything else on the square, say what a blast
left there, is left alone until the water comes back.

On level-a, with its robots taken away, beside the water nearest the start.
A droid runs every tick and asks for a redraw every time, so the playfield is
checked with it held still and then let go.
"""
import struct
import sys

import rp6502

import petscii

WATER = 204
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def r(emu, name):
    return petscii.ram(emu, name)[0]


def unit(emu, u, kind, x, y, tile, timer=0, timer_b=0, d=0, a=0, health=10):
    for name, v in (("TYPE", kind), ("LOC_X", x), ("LOC_Y", y), ("TILE", tile),
                    ("TIMER_A", timer), ("TIMER_B", timer_b), ("D", d), ("A", a),
                    ("HEALTH", health)):
        emu.cmd(f"poke UNIT_{name}+{u} {v}")
    emu.cmd("poke REDRAW_WINDOW 1")


def square(emu, x, y):
    return petscii.ram(emu, f"MAP+{y * 128 + x}")[0]


def sprite_at(emu, x, y):
    """The bank image of the unit sprite at window cell x, y, or None."""
    pf = petscii.xram(emu, "XRAM_PF+77*10", 32 * 10)
    for k in range(32):
        sx, sy, ptr = struct.unpack_from("<hhH", pf, k * 10)
        if (sx, sy) == (x * 24, emu.sym["SCREEN_TOP"] + y * 24):
            return (ptr - emu.sym["XRAM_UNITS"]) // petscii.IMG
    return None


def rng(lo, hi):
    """2.1's GENERATE_RANDOM_NUMBER, $1399: a zero low byte steps as 1, then
    eight times ASL A / ROL RANDOM+1 / BCC / EOR #$39."""
    a = lo or 1
    for _ in range(8):
        a <<= 1
        hi = hi << 1 | a >> 8
        a &= 0xFF
        if hi > 0xFF:
            a ^= 0x39
        hi &= 0xFF
    return a, hi


def shorted(emu, u):
    return [r(emu, f"UNIT_{n}+{u}") for n in ("TYPE", "A", "TIMER_A", "TILE", "D")]


def held(emu, u, where):
    """check_playfield with unit <u> held still, and then let go."""
    timer = r(emu, f"UNIT_TIMER_A+{u}")
    emu.cmd(f"poke UNIT_TIMER_A+{u} 250")
    petscii.check_playfield(emu, where, fail)
    emu.cmd(f"poke UNIT_TIMER_A+{u} {timer}")


with rp6502.Emu() as emu:
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    for u in range(1, 28):
        emu.cmd(f"poke UNIT_TYPE+{u} 0")
    emu.cmd("poke RANDOM 0 0")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 4")
    px, py = r(emu, "UNIT_LOC_X"), r(emu, "UNIT_LOC_Y")

    # A magnetized rollerbot shot dead leaves the rollerbot's wreck: it is
    # type 21, and what it was is in UNIT_D. The cheat gives him a pistol.
    emu.cmd("press lshift")
    petscii.tap(emu, "c", hold=4, after=4)
    emu.cmd("release lshift")
    unit(emu, 1, 21, px + 2, py, 164, timer=250, timer_b=70, d=18, health=1)
    emu.cmd("run 4")
    petscii.tap(emu, "d", hold=4, after=40)
    if r(emu, "UNIT_TYPE+1") != 8:
        fail("the magnetized rollerbot was not killed")
    elif r(emu, "UNIT_A+1") != 18:
        fail(f"the dead magnetized rollerbot keeps {r(emu, 'UNIT_A+1')}, not 18")
    petscii.check_playfield(emu, "a dead magnetized rollerbot", fail)
    emu.cmd("poke UNIT_TYPE+1 0")
    emu.cmd("poke UNIT_HEALTH 12")

    # W, the water nearest the start with a square S below it that a robot
    # can hover on and no unit at either; the player three to the right of W,
    # and the window round him.
    mp = petscii.ram(emu, "MAP", 128 * 64)
    attrib = petscii.ram(emu, "TILE_ATTRIB", 256)
    wx, wy = min(((x, y) for y in range(4, 62) for x in range(1, 121)
                  if mp[y * 128 + x] == WATER and mp[y * 128 + 128 + x] != WATER
                  and attrib[mp[y * 128 + 128 + x]] & 2
                  and attrib[mp[y * 128 + x + 3]] & 1),
                 key=lambda s: abs(s[0] - px) + abs(s[1] - py))
    print(f"water at {wx},{wy}, dry below it")
    emu.cmd(f"poke UNIT_LOC_X {wx + 3}")
    emu.cmd(f"poke UNIT_LOC_Y {wy}")
    emu.cmd(f"poke MAP_WINDOW_X {wx - 2} {wy - 3}")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 10")
    p = petscii.probe(emu)
    if (p["WINDOW_X"], p["WINDOW_Y"]) != (wx - 2, wy - 3):
        fail(f"the window is at {p['WINDOW_X']},{p['WINDOW_Y']}, not {wx - 2},{wy - 3}")
    cx, cy = 2, 3                       # W's window cell

    # A magnetized rollerbot on S. RANDOM is still zero, as at power-on, so
    # its first number is $00, up, and it hovers onto the water.
    emu.cmd("poke RANDOM 0 0")
    unit(emu, 1, 21, wx, wy + 1, 164, timer_b=70, d=17)
    for _ in range(10):
        emu.cmd("run 1")
        if r(emu, "UNIT_TIMER_A+1") == 12:
            break
    else:
        fail("the magnetized robot never ran")
    at = (r(emu, "UNIT_LOC_X+1"), r(emu, "UNIT_LOC_Y+1"))
    if at != (wx, wy):
        fail(f"the magnetized robot's first run took it to {at}, not onto the water")
    if tuple(petscii.ram(emu, "RANDOM", 2)) != (0x00, 0x01):
        fail(f"the first random number from zero leaves RANDOM "
             f"{petscii.ram(emu, 'RANDOM', 2).hex()}, not 00 01")
    calls = 1

    # Its next run, thirteen ticks on, finds the water: a water droid for 60
    # runs, starting in 5 ticks, drawing nothing, still a rollerbot in UNIT_D,
    # the square its sparks, and the shock. The timer is 5 only in the frame
    # of the short-out, so every frame is read.
    for frames in range(1, 30):
        emu.cmd("run 1")
        if r(emu, "UNIT_TYPE+1") != 21:
            break
    if frames != 13:
        fail(f"the magnetized robot's second run came {frames} frames after its first, not 13")
    if shorted(emu, 1) != [5, 60, 5, 87, 17]:
        fail(f"on the water it is type, A, timer, tile, D {shorted(emu, 1)}, "
             "not 5, 60, 5, 87, 17")
    if square(emu, wx, wy) != 140:
        fail(f"the square it shorts out on is {square(emu, wx, wy)}, not the sparks, 140")
    if r(emu, "SOUND_EFFECT") != 15:
        fail(f"shorting out plays {r(emu, 'SOUND_EFFECT')}, not the shock, 15")

    # The sparks step on the map, a tile a run from six ticks on: 141, 142,
    # 140 and round. A few steps in, the playfield with the droid held still:
    # the square's own tile from the cache, and no sprite over it. The 60th
    # run brings the water back and leaves the rollerbot's wreck.
    seen, steps, frames = [square(emu, wx, wy)], [], 0
    while frames < 120 and r(emu, "UNIT_TYPE+1") == 5:
        emu.cmd("run 1")
        frames += 1
        if square(emu, wx, wy) != seen[-1]:
            seen.append(square(emu, wx, wy))
            steps.append(frames)
        if len(seen) == 5 and len(steps) == 4:
            held(emu, 1, "a water droid shorting out")
            if sprite_at(emu, cx, cy) is not None:
                fail(f"the shorting droid shows bank image {sprite_at(emu, cx, cy)}")
            if petscii.ram(emu, f"MAP_PRECALC+{cy * 11 + cx}")[0] != 87:
                fail("the shorting droid is not in its window cell as tile 87")
            steps.append(None)
    want = [140] + [140 + k % 3 for k in range(1, 60)] + [WATER]
    if seen != want:
        fail(f"the square went {seen}, not 140, 141, 142 and round, then water")
    if [s for s in steps if s is not None] != list(range(6, 66)):
        fail(f"the square stepped at frames {steps}, not each frame from 6 to 65")
    if [r(emu, f"UNIT_{n}+1") for n in ("TYPE", "TILE", "A")] != [8, 115, 17]:
        fail(f"after the sparks it is type, tile, A "
             f"{[r(emu, f'UNIT_{n}+1') for n in ('TYPE', 'TILE', 'A')]}, not 8, 115, 17")
    petscii.check_playfield(emu, "the shorted rollerbot's wreck", fail)
    if sprite_at(emu, cx, cy) != 21:
        fail(f"the shorted rollerbot shows bank image {sprite_at(emu, cx, cy)}, not its wreck, 21")

    # A second one, twenty squares from any water, for twenty runs: RANDOM
    # against a model, counting every run since it was zero. Each run counts
    # its UNIT_TIMER_B down.
    far = next((x, y) for y in range(64) for x in range(128)
               if attrib[mp[y * 128 + x]] & 2
               and all(WATER not in mp[yy * 128 + max(x - 20, 0):yy * 128 + min(x + 21, 128)]
                       for yy in range(max(y - 20, 0), min(y + 21, 64))))
    print(f"no water within twenty squares of {far[0]},{far[1]}")
    unit(emu, 2, 21, far[0], far[1], 164, timer_b=70, d=17)
    emu.cmd("run 270")
    runs = 70 - r(emu, "UNIT_TIMER_B+2")
    lo, hi = 0, 0
    for _ in range(calls + runs):
        lo, hi = rng(lo, hi)
    got = tuple(petscii.ram(emu, "RANDOM", 2))
    if runs < 20 or got != (lo, hi):
        fail(f"after {calls} + {runs} runs RANDOM is {got}, the model ${lo:02X} ${hi:02X}")
    if r(emu, "UNIT_TYPE+2") != 21:
        fail(f"the robot far from water is type {r(emu, 'UNIT_TYPE+2')}, not 21")
    emu.cmd("poke UNIT_TYPE+2 0")

    # The EMP. A wreck lying on W, a rollerbot's, and a hoverbot on the water
    # beside it, held still until the EMP reaches it. Both short out, with
    # the EMP's sound and not the shock, the wreck still a rollerbot's.
    hx, hy = next((x, y) for x, y in ((wx + 1, wy), (wx - 1, wy), (wx, wy - 1))
                  if mp[y * 128 + x] == WATER)
    emu.cmd(f"poke MAP+{wy * 128 + wx} {WATER}")
    unit(emu, 1, 8, wx, wy, 115, timer=255, a=17)
    unit(emu, 3, 3, hx, hy, 98, timer=250, d=0)
    emu.cmd("run 4")
    emu.cmd("poke INV_EMP 1")
    emu.cmd("poke SELECTED_ITEM 2")
    emu.cmd("press space")
    for _ in range(20):
        emu.cmd("run 1")
        if r(emu, "UNIT_TYPE+3") == 5:
            break
    emu.cmd("release space")
    for u, kind in ((1, 17), (3, 3)):
        if shorted(emu, u) != [5, 60, 5, 87, kind]:
            fail(f"after the EMP unit {u} is type, A, timer, tile, D {shorted(emu, u)}, "
                 f"not 5, 60, 5, 87, {kind}")
    if r(emu, "SOUND_EFFECT") != 5:
        fail(f"the EMP's short-out plays {r(emu, 'SOUND_EFFECT')}, not the EMP's 5")
    if (square(emu, wx, wy), square(emu, hx, hy)) != (140, 140):
        fail(f"after the EMP the squares are {square(emu, wx, wy)}, "
             f"{square(emu, hx, hy)}, not the sparks, 140")

    # A blast left the hoverbot's square another tile: it is not stepped, and
    # the water comes back when the droid is done.
    emu.cmd(f"poke MAP+{hy * 128 + hx} 170")
    for _ in range(90):
        emu.cmd("run 1")
        if (r(emu, "UNIT_TYPE+1"), r(emu, "UNIT_TYPE+3")) == (8, 8):
            break
        if square(emu, hx, hy) != 170:
            fail(f"the square under the shorting hoverbot became {square(emu, hx, hy)}")
            break
    else:
        fail("the EMP's droids never ended")
    if (square(emu, wx, wy), square(emu, hx, hy)) != (WATER, WATER):
        fail(f"after the EMP's droids the squares are {square(emu, wx, wy)}, "
             f"{square(emu, hx, hy)}, not water")
    for u, kind in ((1, 17), (3, 3)):
        if r(emu, f"UNIT_A+{u}") != kind:
            fail(f"unit {u}'s wreck keeps {r(emu, f'UNIT_A+{u}')}, not {kind}")
    petscii.check_playfield(emu, "the EMP's wrecks", fail)
    got = (sprite_at(emu, cx, cy), sprite_at(emu, cx + hx - wx, cy + hy - wy))
    if got != (21, 20):
        fail(f"the EMP's wrecks show bank images {got}, not the rollerbot's and the hoverbot's, 21, 20")

sys.exit(1 if failures else 0)
