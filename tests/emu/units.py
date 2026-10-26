"""Units drawn as the Amiga draws them.

The evilbot faces the way it last tried to walk: REQUEST_WALK_* store it in
UNIT_DIRECTION, and its frame takes the Amiga's offset for it. A robot that
dies keeps what it was in UNIT_A, and its wreck is the one that robot leaves:
the rollerbot's, the evilbot's, or the hoverbot's. An explosion on the player's
square covers him, a bomb there goes under him and does not show, and firing
with no weapon does not turn him. The frames are X16 2.1's: the small
explosion's five, the last of which covers him too, the rollerbot's four, and
the canister about to blow, drawn with palette b. Each case is set up on
level-a by poking units round the player, on open ground, and checked through
check_playfield, which works the right frame out from RAM and assets/gen; the
bank those frames come from is checked against units.bin once a boot. Units
that run every tick are held still for it. Then on level-c a
transporter sends him across the level: he breaks up through 2.1's eight
frames, eight ticks each, to the medkit's sound, while nothing else moves, and
arrives as the Amiga's tile 97 until his next step.
"""
import struct
import sys

import rp6502

import petscii

T = petscii.amiga_tables()
IMG = petscii.IMG
IMAGES = petscii.images()
SMALL = [248, 249, 250, 251, 252]       # the small explosion's tiles, 2.1's five
ROLLER = [164, 165, 166, 167, 164]      # the rollerbot's, 2.1's four, from 164
CANISTER_PAL = "XRAM_PAL_B"             # the canister's palette, as 2.1's sprite's
DEMAT_FRAMES = (7, 9)                   # 2.1's eight ticks a frame, give or take its load
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def unit(emu, u, kind, x, y, tile, health=10, timer=0):
    emu.cmd(f"poke UNIT_TYPE+{u} {kind}")
    emu.cmd(f"poke UNIT_LOC_X+{u} {x}")
    emu.cmd(f"poke UNIT_LOC_Y+{u} {y}")
    emu.cmd(f"poke UNIT_TILE+{u} {tile}")
    emu.cmd(f"poke UNIT_HEALTH+{u} {health}")
    emu.cmd(f"poke UNIT_TIMER_A+{u} {timer}")
    emu.cmd(f"poke UNIT_TIMER_B+{u} 0")
    emu.cmd(f"poke UNIT_A+{u} 0")
    if u < 32:
        emu.cmd(f"poke UNIT_DIRECTION+{u} 3")
    emu.cmd("poke REDRAW_WINDOW 1")


def sprite_at(emu, x, y, palette=False):
    """The bank image of the unit sprite at screen x, y, or None; with
    palette, the image and the palette it is drawn with."""
    pf = petscii.xram(emu, "XRAM_PF+77*10", 32 * 10)
    for k in range(32):
        sx, sy, ptr, pal = struct.unpack_from("<hhHH", pf, k * 10)
        if (sx, sy) == (x, y):
            b = (ptr - emu.sym["XRAM_UNITS"]) // petscii.IMG
            return (b, pal) if palette else b
    return (None, None) if palette else None


def held(emu, u, where):
    """check_playfield with unit <u> held still, and then let go: a unit
    that runs every tick asks for a redraw every time, and would never let
    the playfield settle."""
    timer = petscii.ram(emu, f"UNIT_TIMER_A+{u}")[0]
    emu.cmd(f"poke UNIT_TIMER_A+{u} 250")
    petscii.check_playfield(emu, where, fail)
    emu.cmd(f"poke UNIT_TIMER_A+{u} {timer}")


with rp6502.Emu() as emu:
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    petscii.check_units_bank(emu, fail)
    emu.cmd("poke ANIMATE 0")
    for u in range(1, 28):
        emu.cmd(f"poke UNIT_TYPE+{u} 0")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 4")
    px, py = petscii.ram(emu, "UNIT_LOC_X")[0], petscii.ram(emu, "UNIT_LOC_Y")[0]
    wx, wy = petscii.ram(emu, "MAP_WINDOW_X", 2)

    # No weapon: firing does not turn him. He starts facing down.
    petscii.tap(emu, "w", hold=4, after=30)
    if petscii.ram(emu, "PLAYER_DIRECTION")[0] != 3:
        fail("firing with no weapon turned the player")

    # The cheat for a pistol, which does turn him.
    emu.cmd("press lshift")
    petscii.tap(emu, "c", hold=4, after=4)
    emu.cmd("release lshift")
    petscii.tap(emu, "w", hold=4, after=30)
    if petscii.ram(emu, "PLAYER_DIRECTION")[0] != 0:
        fail("firing with the pistol did not turn the player up")
    emu.cmd("poke UNIT_HEALTH 12")

    # An evilbot three up and four right comes for him, facing each way it
    # tries to go: down and left, never right, which unit() leaves it facing
    # so that a direction not stored would show. check_playfield checks the
    # frame for its facing each time.
    unit(emu, 1, 9, px + 4, py - 3, 100, health=50)
    faced = set()
    for _ in range(14):
        emu.cmd("run 6")
        petscii.check_playfield(emu, "an evilbot coming", fail)
        faced.add(petscii.ram(emu, "UNIT_DIRECTION+1")[0])
    if not {1, 2} <= faced or 3 in faced or 0 in faced:
        fail(f"the evilbot faced {sorted(faced)}, not down and left")
    emu.cmd("poke UNIT_TYPE+1 0")
    emu.cmd("poke UNIT_HEALTH 12")

    # Wrecks: each robot two to the right, held still, shot dead.
    for kind, tile, offset, name in ((17, 164, 1, "rollerbot"), (9, 100, 2, "evilbot"),
                                     (3, 98, 0, "hoverbot")):
        unit(emu, 2, kind, px + 2, py, tile, health=1, timer=250)
        emu.cmd("run 4")
        petscii.tap(emu, "d", hold=4, after=40)
        if petscii.ram(emu, "UNIT_TYPE+2")[0] != 8:
            fail(f"the {name} was not killed")
            continue
        if petscii.ram(emu, "UNIT_A+2")[0] != kind:
            fail(f"the dead {name} did not keep its type")
        petscii.check_playfield(emu, f"a dead {name}", fail)
        bank = sprite_at(emu, (px + 2 - wx) * 24, emu.sym["SCREEN_TOP"] + (py - wy) * 24)
        if bank != 20 + offset:
            fail(f"the dead {name} shows bank {bank}, not its wreck {20 + offset}")
        emu.cmd("poke UNIT_TYPE+2 0")
        emu.cmd("poke REDRAW_WINDOW 1")
        emu.cmd("run 4")

    # A bomb on his own square goes under him: no unit sprite there.
    unit(emu, 28, 6, px, py, 130, timer=250)
    emu.cmd("run 4")
    petscii.check_playfield(emu, "a bomb under the player", fail)
    if sprite_at(emu, (px - wx) * 24, emu.sym["SCREEN_TOP"] + (py - wy) * 24) is not None:
        fail("the bomb under the player shows")
    emu.cmd("poke UNIT_TYPE+28 0")

    # An explosion on his square covers him, and he is back when it is over.
    unit(emu, 29, 11, px, py, 248, timer=250)
    emu.cmd("run 4")
    petscii.check_playfield(emu, "an explosion on the player", fail)
    if petscii.xram(emu, "XRAM_PF+109*10+2", 1)[0] != 240:
        fail("the player shows through the explosion on him")
    emu.cmd("poke UNIT_TYPE+29 0")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 10")
    petscii.check_playfield(emu, "the explosion over", fail)
    if petscii.xram(emu, "XRAM_PF+109*10+2", 1)[0] == 240:
        fail("the player did not come back after the explosion")

    # The small explosion is 2.1's five frames, a run each: its timer is 0,
    # so it runs every tick, and a sample a frame sees each in turn, then it
    # is gone ($1D6D).
    unit(emu, 29, 11, px + 1, py, 248)
    seen = [248]
    for _ in range(20):
        emu.cmd("run 1")
        if petscii.ram(emu, "UNIT_TYPE+29")[0] != 11:
            break
        t = petscii.ram(emu, "UNIT_TILE+29")[0]
        if t != seen[-1]:
            seen.append(t)
    else:
        fail("the small explosion did not end")
    if seen != SMALL:
        fail(f"the small explosion showed {seen}, not {SMALL}")

    # Its last frame covers him too: one on his square, held there.
    unit(emu, 29, 11, px, py, 248)
    for _ in range(20):
        emu.cmd("run 1")
        if petscii.ram(emu, "UNIT_TILE+29")[0] == SMALL[-1]:
            break
    else:
        fail(f"the small explosion on the player did not reach {SMALL[-1]}")
    emu.cmd("poke UNIT_TIMER_A+29 250")
    petscii.check_playfield(emu, "the small explosion's last frame on the player", fail)
    if sprite_at(emu, (px - wx) * 24, emu.sym["SCREEN_TOP"] + (py - wy) * 24) is None:
        fail("the small explosion's last frame is not drawn")
    if petscii.xram(emu, "XRAM_PF+109*10+2", 1)[0] != 240:
        fail("the player shows through the small explosion's last frame")
    emu.cmd("poke UNIT_TIMER_A+29 0")
    emu.cmd("run 4")
    if petscii.ram(emu, "UNIT_TYPE+29")[0] != 0:
        fail("the small explosion on the player did not end after its last frame")

    # The rollerbot steps through 2.1's frames every fourth run ($15FA). Two
    # bombs whose UNIT_A is 2, which do nothing (TB02) and with no tile draw
    # nothing, box it in above and below, so it stays out of his row and
    # column and never fires. Each frame is checked held still.
    for u, dy in ((3, -3), (4, -1)):
        unit(emu, u, 6, px + 3, py + dy, 0, timer=250)
        emu.cmd(f"poke UNIT_A+{u} 2")
    unit(emu, 2, 17, px + 3, py - 2, 164)
    seen = [164]
    for _ in range(200):
        emu.cmd("run 1")
        t = petscii.ram(emu, "UNIT_TILE+2")[0]
        if t != seen[-1]:
            seen.append(t)
            held(emu, 2, f"the rollerbot at tile {t}")
            if sprite_at(emu, (px + 3 - wx) * 24, emu.sym["SCREEN_TOP"] + (py - 2 - wy) * 24) is None:
                fail(f"the rollerbot at tile {t} is not drawn")
            if len(seen) == len(ROLLER):
                break
    if seen != ROLLER:
        fail(f"the rollerbot showed {seen}, not {ROLLER}")
    if (petscii.ram(emu, "UNIT_LOC_X+2")[0], petscii.ram(emu, "UNIT_LOC_Y+2")[0]) \
            != (px + 3, py - 2):
        fail("the boxed-in rollerbot moved")
    for u in (2, 3, 4):
        emu.cmd(f"poke UNIT_TYPE+{u} 0")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 4")

    # The canister about to blow, beside him: a bomb whose UNIT_A is 2 stays.
    unit(emu, 28, 6, px - 2, py, 131, timer=250)
    emu.cmd("poke UNIT_A+28 2")
    emu.cmd("run 4")
    petscii.check_playfield(emu, "a canister about to blow", fail)
    got = sprite_at(emu, (px - 2 - wx) * 24, emu.sym["SCREEN_TOP"] + (py - wy) * 24, palette=True)
    if got != (24, emu.sym[CANISTER_PAL]):
        fail(f"the canister shows {got}, not record 24 with {CANISTER_PAL}")
    emu.cmd("poke UNIT_TYPE+28 0")

with rp6502.Emu() as emu:
    # A transporter within the level: level-c's pad at 71,11 sends him to
    # 119,7. On the way he breaks up through 2.1's eight frames, player
    # records 49-56, eight ticks each ($5A1C), so a sample every frame sees
    # them all, and 50-55 each for eight frames; before the first, the frame
    # he had may show while it loads. The medkit's sound starts with them.
    # Those 64 ticks hold the game up, as 2.1's do: a hoverbot set going in
    # the pad's room stays on its square throughout. Halfway, check_playfield
    # works the frame out from UNIT_TILE. Then he shows the Amiga's frame for
    # tile 97 -- facing down, no weapon -- until his next step.
    petscii.boot(emu, "c")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    petscii.check_units_bank(emu, fail)
    player = [IMAGES[(emu.sym["IMG_PLAYER"] + k) * IMG:(emu.sym["IMG_PLAYER"] + k + 1) * IMG]
              for k in range(57)]
    unit(emu, 20, 2, 78, 11, 99)
    emu.cmd("poke UNIT_LOC_X 71")
    emu.cmd("poke UNIT_LOC_Y 11")
    emu.cmd("poke UNIT_HEALTH 12")
    shown, at, squares, sound = [], [], [], None
    for _ in range(300):
        emu.cmd("run 1")
        p = petscii.probe(emu)
        if (p["PLAYER_X"], p["PLAYER_Y"]) == (119, 7):
            break
        if not petscii.ram(emu, "player_demat")[0]:
            continue
        if sound is None:
            sound = petscii.ram(emu, "SOUND_EFFECT")[0]
        squares.append((petscii.ram(emu, "UNIT_LOC_X+20")[0],
                        petscii.ram(emu, "UNIT_LOC_Y+20")[0]))
        y, ptr = struct.unpack("<hH", petscii.xram(emu, "XRAM_PF+109*10+2", 4))
        if y != 240:
            got = petscii.xram(emu, f"{ptr}", IMG)
            k = next((k for k in range(57) if player[k] == got), None)
            if not shown or shown[-1] != k:
                shown.append(k)
                at.append(petscii.ram(emu, "IRQ_FRAME")[0])
                if k == 52:
                    petscii.check_playfield(emu, "dematerializing", fail)
    else:
        fail(f"the pad did not send him to 119,7: at {p['PLAYER_X']},{p['PLAYER_Y']}")
    print(f"dematerializing: player records {shown}")
    lasted = {k: (at[i + 1] - at[i]) & 0xFF for i, k in enumerate(shown[:-1])}
    print(f"dematerializing: frames each record showed {lasted}")
    if any(not DEMAT_FRAMES[0] <= lasted.get(k, 0) <= DEMAT_FRAMES[1]
           for k in range(50, 56)):
        fail(f"dematerializing: records 50-55 did not show {DEMAT_FRAMES} frames each")
    if sound != 11:
        fail(f"dematerializing: effect {sound} at its first frame, not the medkit's, 11")
    if len(set(squares)) != 1:
        fail(f"dematerializing: the hoverbot moved, {squares[0]} to {squares[-1]}")
    first = shown.index(49) if 49 in shown else len(shown)
    if (shown[first:] != list(range(49, 57))
            or not all(k is not None and k < 49 for k in shown[:first])):
        fail(f"dematerializing showed player records {shown}, not 49-56 in turn")
    emu.cmd("run 30")
    if petscii.ram(emu, "UNIT_TILE")[0] != 97:
        fail("after the transport his tile is not 97")
    petscii.check_playfield(emu, "transported within the level", fail)
    petscii.tap(emu, "j", hold=4, after=20)
    if petscii.ram(emu, "UNIT_TILE")[0] != 96:
        fail("a step did not end the transport's tile 97")
    petscii.check_playfield(emu, "a step after the transport", fail)

sys.exit(1 if failures else 0)
