"""X16 2.1's cursor icons, and the magnifier circling while a search runs.

CURSOR_ON picks the icon -- 1 the arrows, for placing an item, 2 the
magnifier, for searching, 3 the hand, for moving -- each 28x28 at 2bpp in
palette b, with its top left two pixels right of the cell's and one down,
where 2.1 puts it. While a search's dots go down, the magnifier steps round
its cell, clockwise from the top and four pixels out, every GLASS_TICKS ticks,
5, as 2.1's SEARCH_GLASS_CIRCLE does; the step is never reset, so the next
search picks the circle up where the last one left it. A step that falls on a
search's last tick is made in the pass that ends the search and puts the
cursor away, so it never shows, and the next search starts a step later.
Whether that last tick is counted at all depends on where in the search loop
its frame begins, which moves with every change to the code's timing, so
either can happen. Over the live map the cursor is not shown at all, but the
search's dots still go down and the circle goes on unseen, so the search after
it starts 28 or 29 steps further round.

On level-a, one square left of the start, the square above is tile 137, which
can be searched again and again, and the other three round him are tile 208,
which can be neither searched nor pushed. The cursor's sprite record is read
back from XRAM, during a search every frame. The magnifier counts frames, so
a frame the game missed would make one of its steps a frame too long; the
probe's overrun count shows whether that happened, and the test checks it.
"""
import struct
import sys

import rp6502

import petscii

# Where 2.1's tables at $4D4F and $4D57 put the magnifier, less 4: in order,
# from the top, clockwise.
OFFSETS = ((0, -4), (3, -3), (4, 0), (3, 3), (0, 4), (-3, 3), (-4, 0), (-3, -3))
SEARCH_TICKS = 8 * 18           # eight dots, eighteen ticks each (SOBJ1)
GLASS_TICKS = 5                 # a step every fifth tick, as decided
SAMPLES = 170                   # frames sampled from the arrow that starts it
ICON = 28 * 28 * 2 // 8         # bytes in one 28x28 2bpp icon
SIZE_28 = (28 // 4 - 1) << 4 | (28 // 4 - 1)    # MODE5_SIZE(28, 28)
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def rec(emu):
    """The cursor's sprite record: x, y, image, palette, size, attributes."""
    return struct.unpack("<hhHHBB", petscii.xram(emu, "XRAM_HUD+HUD_CURSOR*10", 10))


def place(emu, col, row):
    """Where the cursor sits over window cell col, row."""
    s = emu.sym
    return col * s["TILE_PX"] + 2, s["SCREEN_TOP"] + row * s["TILE_PX"] + 1


def want(emu, where, x, y, icon):
    s = emu.sym
    expected = (x, y, s["XRAM_CURSOR"] + ICON * icon, s["XRAM_PAL_B"],
                SIZE_28, s["MODE5_2BPP"])
    if rec(emu) != expected:
        fail(f"{where}: the cursor's record is {rec(emu)}, not {expected}")


def dots(emu, row=24):
    """How many of the search's dots are on console row <row>, from column 9:
    on 24, the bottom, while they go down. The eighth goes down in the frame
    the result is printed, which scrolls the line up to 23."""
    cells = petscii.xram(emu, f"XRAM_CHARS+{row}*SCR_STRIDE+9*2", 2 * 8)
    return cells[::2].count(46)


def circle(emu):
    """The steps one search makes, fewest and most: its ticks over
    GLASS_TICKS, with up to GLASS_TICKS - 1 carried over from the last."""
    ticks = emu.sym["GLASS_TICKS"]
    return SEARCH_TICKS // ticks, (SEARCH_TICKS + ticks) // ticks


def after(last, hidden=(0,)):
    """The steps a search can start from: the one after <last>, the last that
    the search before showed, and <hidden> more made unseen. Any, if that
    search went wrong."""
    if last is None:
        return set(range(8))
    return {(last + 1 + h) & 7 for h in hidden}


def search_up(emu, where, firsts):
    """With the magnifier up, choose the square above and sample the cursor
    every frame until the search is over: the normal place, which a search
    that finds the count at its last tick leaves before a frame can show it;
    then the circle, from one of the steps <firsts>, a step every GLASS_TICKS
    frames, the last cut short by the end; then parked to the end. Returns the
    last step shown and how many more the search can have made unseen, (0,)
    or (0, 1); or None and (0,) if the circle went wrong.

    The unseen one is a step on the search's last tick, made in the pass that
    ends the search and parks the cursor. It comes GLASS_TICKS ticks after the
    last step shown, so that step must have shown for all of them, and it
    counts towards the steps a search can make.

    The first step can show for a frame less. The samples come at the same
    point in every frame, and a step is made on the first pass of the search
    loop after a frame begins, before the sample -- but for a first step made
    on the search's very first pass, as it is when the count carried over is
    at its last tick. That pass can come after the sample in its frame, so the
    step is seen a frame late."""
    s = emu.sym
    ticks, parked = s["GLASS_TICKS"], s["SPR_PARKED_Y"]
    home = place(emu, 5, 2)
    late = petscii.probe(emu)["OVERRUN"]
    emu.cmd("press i")
    runs = []
    for f in range(SAMPLES):
        emu.cmd("run 1")
        if f == 5:
            emu.cmd("release i")
        x, y = rec(emu)[:2]
        at = "parked" if y == parked else (x, y)
        if runs and runs[-1][0] == at:
            runs[-1][1] += 1
        else:
            runs.append([at, 1])
    late = (petscii.probe(emu)["OVERRUN"] - late) & 0xFF
    if late:
        fail(f"{where}: {late} late vblanks during the search")
    print(f"{where}: {[(at, n) for at, n in runs]}")

    if runs[-1][0] != "parked":
        fail(f"{where}: the cursor is not parked once the search is over")
        return None, (0,)
    if runs[0][0] == home:
        runs = runs[1:]
    steps = runs[:-1]
    if not steps:
        fail(f"{where}: the magnifier never moved")
        return None, (0,)
    at = steps[0][0]
    offset = None if at == "parked" else (at[0] - home[0], at[1] - home[1])
    first = OFFSETS.index(offset) if offset in OFFSETS else None
    if first not in firsts:
        fail(f"{where}: the circle starts at {at}, not at step "
             f"{' or '.join(str(k) for k in sorted(firsts))}")
        return None, (0,)
    for k, (at, n) in enumerate(steps):
        step = (first + k) & 7
        dx, dy = OFFSETS[step]
        if at != (home[0] + dx, home[1] + dy):
            fail(f"{where}: move {k} shows the cursor at {at}, not step {step}, "
                 f"{home[0] + dx},{home[1] + dy}")
            return None, (0,)
        short = (k == 0 and n == ticks - 1) or (k == len(steps) - 1 and n < ticks)
        if n != ticks and not short:
            fail(f"{where}: step {step} lasts {n} frames, not {ticks}")
    lo, hi = circle(emu)
    if not lo <= len(steps) <= hi:
        fail(f"{where}: the magnifier moved {len(steps)} times, not {lo} or {hi}")
    unseen = (0, 1) if steps[-1][1] == ticks and len(steps) < hi else (0,)
    return (first + len(steps) - 1) & 7, unseen


with rp6502.Emu() as emu:
    s = emu.sym
    if s["GLASS_TICKS"] != GLASS_TICKS:
        fail(f"GLASS_TICKS is {s['GLASS_TICKS']}, not {GLASS_TICKS}")
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    if petscii.xram(emu, "XRAM_CURSOR", 3 * ICON) != petscii.gen("cursors.bin"):
        fail("XRAM_CURSOR is not assets/gen/cursors.bin")

    # One square left, as tests/emu/search.txt goes.
    petscii.tap(emu, "j", after=20)
    p = petscii.probe(emu)
    if (p["PLAYER_X"], p["PLAYER_Y"]) != (21, 38):
        fail(f"the player is at {p['PLAYER_X']},{p['PLAYER_Y']}, not 21,38")
    on_him = place(emu, 5, 3)

    # Z puts the magnifier on him; the arrow up searches the square above,
    # which finds the pistol. The glass's step starts at 0, as BSS does.
    petscii.tap(emu, "z")
    want(emu, "the magnifier", *on_him, 1)
    last, unseen = search_up(emu, "the first search", {0})
    if petscii.probe(emu)["WEAPON_ITEM"] != 0x01:
        fail("the first search did not find the pistol")
    emu.cmd("run 20")

    # Again: nothing this time, but the same eight dots, and the circle goes
    # on from the step after the last one made, shown or not.
    petscii.tap(emu, "z")
    want(emu, "the magnifier again", *on_him, 1)
    last, unseen = search_up(emu, "the second search", after(last, unseen))
    emu.cmd("run 20")

    # With the live map up, the cursor never shows, circling or not; but the
    # search runs, its dots go down one by one, and the circle goes on.
    petscii.tap(emu, "tab")
    for _ in range(60):
        if petscii.probe(emu)["LIVEMAP"] == 1:
            break
        emu.cmd("run 1")
    else:
        fail("the live map did not open")
    petscii.tap(emu, "z")
    late = petscii.probe(emu)["OVERRUN"]
    emu.cmd("press i")
    shown, down = set(), set()
    for f in range(SAMPLES):
        emu.cmd("run 1")
        if f == 5:
            emu.cmd("release i")
        y = rec(emu)[1]
        if y != s["SPR_PARKED_Y"]:
            shown.add(y)
        down.add(dots(emu))
    late = (petscii.probe(emu)["OVERRUN"] - late) & 0xFF
    if shown:
        fail(f"the cursor showed over the live map, at y {sorted(shown)}")
    if not set(range(1, 8)) <= down or dots(emu, 23) != 8:
        fail(f"under the live map the dots went {sorted(down)}, and "
             f"{dots(emu, 23)} scrolled up: not 1 to 7, then 8")
    if late:
        fail(f"under the live map: {late} late vblanks during the search")
    emu.cmd("run 20")
    petscii.tap(emu, "tab", after=30)
    if petscii.probe(emu)["LIVEMAP"] != 0:
        fail("the live map did not close")

    # Searching again, the circle starts as many steps on from the second
    # search's last as the one under the map made unseen, 28 or 29, and the
    # second's own unseen one if it made one.
    lo, hi = circle(emu)
    petscii.tap(emu, "z")
    want(emu, "the magnifier after the map", *on_him, 1)
    search_up(emu, "the search after the map",
              after(last, {u + h for u in unseen for h in range(lo, hi + 1)}))
    emu.cmd("run 20")

    # M puts the hand on him; open ground to the left cannot be moved, so the
    # cursor goes.
    petscii.tap(emu, "m")
    want(emu, "the hand", *on_him, 2)
    petscii.tap(emu, "j")
    if rec(emu)[1] != s["SPR_PARKED_Y"]:
        fail(f"the cursor is not parked after a move that cannot be made: {rec(emu)}")
    emu.cmd("run 20")

    # A magnet, used: the arrows, to place it.
    emu.cmd("poke INV_MAGNET 1")
    emu.cmd("poke SELECTED_ITEM 4")
    petscii.tap(emu, "space")
    want(emu, "the arrows", *on_him, 0)
    emu.cmd('shot "cursor.png"')

print(f"cursor: three icons, three searches circling, one under the live map, "
      f"{len(failures)} failures")
sys.exit(1 if failures else 0)
