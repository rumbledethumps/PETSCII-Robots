"""The playfield shows what the map says, from the right images.

Every visible cell's sprite must point either at the current frame of an
animated tile, or at the cache slot its map square owns -- ((y+1) mod 9) * 13 +
((x+1) mod 13) -- and that slot must hold the tile's image, byte for byte, as
conv_amiga.py wrote it into images.bin. The units must be the ones
MAP_PRE_CALCULATE put in the window, in window order, each with its bank image
and palette, and the player must be the frame his direction, walk and weapon
choose. This checks all of that after boot, after steps in every direction,
with the window at the map's four corners, through every animation frame, and
on a level with robots in view. It also checks that a step the cache is not
ready for waits rather than showing black, and that a jump of the window
blacks the playfield out until everything the cache serves has loaded.

The expectations come from the build's own assets and the game's own RAM, so
nothing here changes when the art does.
"""
import struct
import sys

import rp6502

import petscii

IMG = petscii.IMG
T = petscii.amiga_tables()
IMAGES = petscii.images()
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def settle(emu):
    petscii.settle(emu, fail)


def loading(emu, where):
    """While loads are still to come, every window cell must show either the
    current frame of an animated tile, the black tile, or a slot that already
    holds its tile: never a slot that holds another cell's. Returns how many
    cells are black."""
    s = emu.sym
    wx, wy = petscii.ram(emu, "MAP_WINDOW_X")[0], petscii.ram(emu, "MAP_WINDOW_Y")[0]
    mp = petscii.ram(emu, "MAP", 128 * 64)
    pf = petscii.xram(emu, "XRAM_PF", 77 * 10)
    black = 0
    for n in range(77):
        c, r = n % 11, n // 11
        ptr = struct.unpack_from("<H", pf, n * 10 + 4)[0]
        t = mp[(wy + r) * 128 + wx + c]
        if ptr == s["XRAM_BLANK"]:
            black += 1
        elif T["amiga_tile_anim"][t] == 0xFF:
            slot = (ptr - s["XRAM_VIEW"]) // IMG
            if petscii.xram(emu, f"{ptr}", IMG) != IMAGES[t * IMG:(t + 1) * IMG]:
                fail(f"{where}: cell ({c},{r}) shows slot {slot} without tile {t}")
    print(f"{where}: {black} cells black while loading")
    return black


def parked(emu):
    """Whether every playfield sprite -- window, units, player -- is below the
    screen, as a jump leaves them while the cache loads."""
    pf = petscii.xram(emu, "XRAM_PF", 110 * 10)
    return all(struct.unpack_from("<h", pf, i * 10 + 2)[0] == 240
               for i in range(110))


def stale(emu, wx, wy):
    """The window cells at wx,wy whose sprite points at a cache slot that does
    not hold the cell's tile."""
    s = emu.sym
    mp = petscii.ram(emu, "MAP", 128 * 64)
    pf = petscii.xram(emu, "XRAM_PF", 77 * 10)
    cache = petscii.xram(emu, "XRAM_VIEW", 117 * IMG)
    bad = []
    for n in range(77):
        ptr = struct.unpack_from("<H", pf, n * 10 + 4)[0] - s["XRAM_VIEW"]
        if 0 <= ptr < 117 * IMG:
            t = mp[(wy + n // 11) * 128 + wx + n % 11]
            if cache[ptr:ptr + IMG] != IMAGES[t * IMG:(t + 1) * IMG]:
                bad.append((n % 11, n // 11))
    return bad


def margin_loaded(emu, where):
    """Every cell the cache serves -- the window and the margin round it, on
    the map and not animated -- has its tile in its slot."""
    wx, wy = petscii.ram(emu, "MAP_WINDOW_X")[0], petscii.ram(emu, "MAP_WINDOW_Y")[0]
    mp = petscii.ram(emu, "MAP", 128 * 64)
    cache = petscii.xram(emu, "XRAM_VIEW", 117 * IMG)
    missing = 0
    for my in range(wy - 1, wy + 8):
        for mx in range(wx - 1, wx + 12):
            if not (0 <= mx < 128 and 0 <= my < 64):
                continue
            t = mp[my * 128 + mx]
            if T["amiga_tile_anim"][t] != 0xFF:
                continue
            slot = ((my + 1) % 9) * 13 + (mx + 1) % 13
            if cache[slot * IMG:(slot + 1) * IMG] != IMAGES[t * IMG:(t + 1) * IMG]:
                missing += 1
    if missing:
        fail(f"{where}: {missing} cells of the window and margin not loaded")


def jump(emu, wx, wy, where):
    """Move the window to wx,wy at once, as the elevator and the transporters
    do, and follow it a frame at a time: no load starts until the playfield
    has gone dark, and it comes back with the whole cache loaded.

    A load can only overwrite a slot the old view still shows if it starts
    before the vblank that parks the sprites, and the emulator's frame
    boundary falls after that vblank, so the screen alone cannot show it.
    view_lag can: it holds a load in flight until the next vblank retires it,
    so one started before the blackout is already counted when the
    playfield is first seen dark, and one started after it is not."""
    old = petscii.ram(emu, "MAP_WINDOW_X")[0], petscii.ram(emu, "MAP_WINDOW_Y")[0]
    loads = petscii.ram(emu, "view_loads")[0]
    emu.cmd("poke view_lag 1")
    emu.cmd(f"poke MAP_WINDOW_X {wx} {wy}")
    emu.cmd("poke REDRAW_WINDOW 1")
    dark = 0
    for _ in range(60):
        emu.cmd("run 1")
        if parked(emu):
            if not dark:
                early = (petscii.ram(emu, "view_loads")[0] - loads) & 0xFF
                if early:
                    fail(f"{where}: {early} loads started before the blackout")
                emu.cmd("poke view_lag 0")
            dark += 1
        elif dark:
            margin_loaded(emu, where)
            break
        else:
            bad = stale(emu, *old)
            if bad:
                fail(f"{where}: before the blackout the old view showed new "
                     f"tiles at {bad}")
                break
    else:
        fail(f"{where}: the playfield did not come back")
    emu.cmd("poke view_lag 0")
    if not dark:
        fail(f"{where}: no blackout")
    print(f"{where}: dark for {dark} frames")
    check(emu, where)


def check(emu, where):
    petscii.check_playfield(emu, where, fail)


def step(emu, key):
    petscii.tap(emu, key, hold=8, after=8)


with rp6502.Emu() as emu:
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    petscii.check_units_bank(emu, fail)
    check(emu, "level-a start")

    # The HUD's health picture: full health is the first of six.
    hud = petscii.xram(emu, "XRAM_HUD+2*10", 10)
    x, y, ptr, pal, wh, attr = struct.unpack("<hhHHBB", hud)
    if (x, y, ptr, wh) != (272, emu.sym["SCREEN_TOP"] + 131, emu.sym["XRAM_HEALTH"], 0xCB):
        fail(f"health picture record {(x, y, ptr, wh)}")
    health = emu.sym["IMG_HEALTH"] * IMG
    if petscii.xram(emu, "XRAM_HEALTH", 1248) != IMAGES[health:health + 1248]:
        fail("health picture is not the full-health one")

    for key, n in (("l", 3), ("k", 2), ("j", 4), ("i", 2)):
        for _ in range(n):
            step(emu, key)
        emu.cmd("run 10")
        check(emu, f"after {n} x {key}")

    # Animation: held, then each frame in turn on a window with water in it.
    emu.cmd("poke ANIMATE 0")
    mp = petscii.ram(emu, "MAP", 128 * 64)
    spot = next((x, y) for y in range(0, 57) for x in range(0, 117)
                if mp[y * 128 + x] == 204)
    wx, wy = min(max(spot[0] - 5, 0), 117), min(max(spot[1] - 3, 0), 57)
    for k in range(4):
        emu.cmd(f"poke ANIM_STATE {k}")
        emu.cmd(f"poke MAP_WINDOW_X {wx} {wy}")
        emu.cmd("poke REDRAW_WINDOW 1")
        emu.cmd("run 2")
        check(emu, f"water at {spot}, frame {k}")

    # The corners of the map: the margin runs off every edge.
    for wx, wy in ((0, 0), (117, 0), (0, 57), (117, 57)):
        emu.cmd(f"poke MAP_WINDOW_X {wx} {wy}")
        emu.cmd("poke REDRAW_WINDOW 1")
        emu.cmd("run 2")
        check(emu, f"corner {wx},{wy}")

with rp6502.Emu() as emu:
    # No loads at all: the margin loaded at the start covers one step right,
    # and the next waits for the cache instead of showing black. Then the
    # loads resume and the step it was holding happens.
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    emu.cmd("poke ANIMATE 0")
    emu.cmd("poke view_budget 0")
    x = petscii.probe(emu)["PLAYER_X"]
    step(emu, "l")
    emu.cmd("run 4")
    if loading(emu, "no loads, one step"):
        fail("the margin did not cover the first step")
    if petscii.probe(emu)["PLAYER_X"] != x + 1:
        fail("the first step did not happen")
    step(emu, "l")
    emu.cmd("run 4")
    if loading(emu, "no loads, a second step"):
        fail("a step past the margin showed black cells")
    if petscii.probe(emu)["PLAYER_X"] != x + 1:
        fail("a step past the margin did not wait for the cache")
    emu.cmd("poke view_budget 255")
    emu.cmd("run 4")
    if petscii.probe(emu)["PLAYER_X"] != x + 2:
        fail("the step that waited did not happen once the loads resumed")
    check(emu, "loads resumed")
    if petscii.probe(emu)["BLANK"]:
        fail("black cells left after the loads")

    # A tile that changes in the margin, outside the window, asks for no
    # redraw: the raft docking there, say. If the cell was water when the walk
    # passed it -- animated, so never loaded -- its slot still holds another
    # cell's tile, and a step towards it waits for the cache to load it, not
    # for some other redraw that may never come. Taps are short so that the
    # key's fast repeat adds no second step.
    wx, wy = petscii.ram(emu, "MAP_WINDOW_X")[0], petscii.ram(emu, "MAP_WINDOW_Y")[0]
    at = (wy + 3) * 128 + wx + 12           # beyond the margin, for now
    was = petscii.ram(emu, f"MAP+{at}")[0]
    gone = petscii.ram(emu, f"MAP+{at - 13}")[0]   # its slot's tile today
    emu.cmd(f"poke MAP+{at} 204")           # water
    x = petscii.probe(emu)["PLAYER_X"]
    petscii.tap(emu, "l", hold=4, after=8)
    settle(emu)
    other = next(t for t in range(253)
                 if T["amiga_tile_anim"][t] == 0xFF and t not in (was, gone)
                 and IMAGES[t * IMG:(t + 1) * IMG] != IMAGES[gone * IMG:(gone + 1) * IMG])
    emu.cmd(f"poke MAP+{at} {other}")       # the raft arrives
    petscii.tap(emu, "l", hold=4, after=8)
    if petscii.probe(emu)["PLAYER_X"] != x + 2:
        fail("a step waited on a margin tile that nothing reloaded")
    check(emu, "a margin tile that changed unseen")
    emu.cmd(f"poke MAP+{at} {was}")
    emu.cmd("poke REDRAW_WINDOW 1")
    check(emu, "the margin tile put back")

    # The pad: a press let go before the wait is over still steps once the
    # cache is ready, as a key put back on the queue does. The pad only looks
    # at its directions when KEYTIMER runs out, every seven frames, so a press
    # is held for eight.
    emu.cmd("pad 0 connect")
    emu.cmd("run 30")
    emu.cmd("poke view_budget 0")
    x = petscii.probe(emu)["PLAYER_X"]
    for _ in range(2):
        emu.cmd("pad 0 press right")
        emu.cmd("run 8")
        emu.cmd("pad 0 release right")
        emu.cmd("run 30")
    if petscii.probe(emu)["PLAYER_X"] != x + 1:
        fail("a pad step past the margin did not wait for the cache")
    emu.cmd("poke view_budget 255")
    emu.cmd("run 4")
    if petscii.probe(emu)["PLAYER_X"] != x + 2:
        fail("a pad press that had to wait was lost")
    emu.cmd("pad 0 disconnect")
    check(emu, "pad steps")
    home = petscii.ram(emu, "MAP_WINDOW_X")[0], petscii.ram(emu, "MAP_WINDOW_Y")[0]

    # A jump -- the elevator, a transporter -- blacks the playfield out until
    # the cache has loaded, margin and all; with the spin's loads stopped it
    # stays dark.
    emu.cmd("poke view_budget 0")
    emu.cmd("poke MAP_WINDOW_X 60 20")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 10")
    if not parked(emu):
        fail("a jump with no loads did not stay dark")
    if not petscii.probe(emu)["PENDING"]:
        fail("the probe says nothing is pending in the dark")
    emu.cmd("poke view_budget 255")
    for _ in range(30):
        emu.cmd("run 1")
        if not parked(emu):
            break
    else:
        fail("still dark once the loads resumed")
    margin_loaded(emu, "a jump with the loads resumed")
    check(emu, "a jump with the loads resumed")

    # And with them running, a frame at a time, there and back.
    jump(emu, 90, 40, "a jump")
    jump(emu, *home, "back from the jump")

    # Every load still in flight when VSYNC comes, so the vblank work always
    # runs with one outstanding, as a slow card or USB drive makes it. Loading
    # a level or a picture blocks for frames on purpose; walking should not.
    late = petscii.probe(emu)["OVERRUN"]
    emu.cmd("poke view_lag 1")
    for key in ("k", "k", "j", "j", "j", "i"):
        step(emu, key)
        if loading(emu, f"loads across VSYNC, after {key}"):
            fail(f"black cells while walking, after {key}")
    check(emu, "loads across VSYNC")
    late = (petscii.probe(emu)["OVERRUN"] - late) & 0xFF
    if late:
        fail(f"{late} late vblanks while walking")

with rp6502.Emu() as emu:
    # A robot stepping out of the window takes its sprite with it. The game
    # asks for a redraw only when the unit it moved is near the window, and
    # nothing else redraws a window without animated tiles in it, so the
    # window is put on a droid at one edge, and checked the moment the droid
    # is out by that edge: a left-right droid, 7, for the sides, and an
    # up-down one, 1, for the top and bottom. Each patrols, so the window
    # waits for it to come back to the edge if it leaves by the other.
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    emu.cmd("poke ANIMATE 0")
    for u, side in ((7, "left"), (7, "right"), (1, "top"), (1, "bottom")):
        done = False
        for _ in range(4):
            x0 = petscii.ram(emu, f"UNIT_LOC_X+{u}")[0]
            y0 = petscii.ram(emu, f"UNIT_LOC_Y+{u}")[0]
            wx = {"left": x0, "right": x0 - 10}.get(side, x0 - 5)
            wy = {"top": y0, "bottom": y0 - 6}.get(side, y0 - 3)
            emu.cmd(f"poke MAP_WINDOW_X {wx} {wy}")
            emu.cmd("poke REDRAW_WINDOW 1")
            emu.cmd("run 20")
            for _ in range(200):
                emu.cmd("run 1")
                x = petscii.ram(emu, f"UNIT_LOC_X+{u}")[0]
                y = petscii.ram(emu, f"UNIT_LOC_Y+{u}")[0]
                if not (wx <= x <= wx + 10 and wy <= y <= wy + 6):
                    break
            out = {"left": x == wx - 1, "right": x == wx + 11,
                   "top": y == wy - 1, "bottom": y == wy + 7}[side]
            if out:
                emu.cmd("run 3")
                check(emu, f"droid {u} out of the {side}")
                done = True
                break
        if not done:
            fail(f"droid {u} never left the window by the {side}")

with rp6502.Emu() as emu:
    # level-g starts with robots in view.
    petscii.boot(emu, "g")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    check(emu, "level-g start")
    emu.cmd("run 120")
    check(emu, "level-g later")

sys.exit(1 if failures else 0)
