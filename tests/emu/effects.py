"""The Amiga's effects: palette fades and flashes, screen shake, the cinema
marquee, and turning to face a square chosen with the move keys.

The palettes are read back whole -- all six, 96 entries -- and compared with a
model of the Amiga's Palette::update in Python: every colour moves towards a
base colour by level/15, a channel at a time, the change rounded down, and then
splits into the RP6502's palettes, colour 0 standing in where the Amiga's
outlines and text backgrounds used it, and the robots' palette in 2.1's order.
At rest that is the palettes the game always had; a hit takes them to red, the
EMP to blue, nine frames back to normal; a screen change goes to black and
back.

Shake moves everything 3 pixels right, two frames in every four, while
SCREEN_SHAKE is set: the window's tiles, the player, the HUD frame, the text
and the HUD's pictures together. The marquee is CINEMA_MESSAGE in the C64 font
across a cinema's middle row, written into its tiles' cache slots, one
character on every twenty ticks. It counts in the AI tick with the animated
tiles, which step as 2.1's ANIMATE_WATER steps them: water, the flag and the
server light every thirty ticks, the compactor and the fans fifteen after
them. In the pause, which runs no AI, all of it stands still.
"""
import sys

import rp6502

import petscii

T = petscii.amiga_tables()
IMG = petscii.IMG
rgb555 = petscii.rgb555
# The animations' counts, and the steps the tiles' two groups make in the
# thirty ticks after one of group A's: X16 2.1's ANIMATE_WATER.
CLOCK = ("ANIM_STATE", "ANIM_STATE_B", "CINEMA_STATE")
STEPS = [("ANIM_STATE_B", 15), ("ANIM_STATE", 30)]
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


# ---- the palette model ------------------------------------------------------

def fade(c, base, f):
    out = 0
    for sh in (8, 4, 0):
        v, b = (c >> sh) & 15, (base >> sh) & 15
        d = abs(v - b) * f // 15
        out |= (b + d if v >= b else b - d) << sh
    return out


def palettes(f, base, pic, pic_black, inks=None):
    g = [fade(c, base, f) for c in T["amiga_pal_game"]]
    p = [fade(c, base, f) for c in pic]
    G = [rgb555(c) for c in g]
    P = [rgb555(c) for c in p]
    fg = [0] + G[1:]
    a = [rgb555(g[0], False)] + G[1:]
    a[8] = G[0]
    b = [0] + [G[g] for g in T["amiga_pal_b_order"]]
    pt = [0] + P[1:]
    pt[8] = P[0]
    # The title's own two text colours, when it has given them: pic_text's 13
    # and 14 take them faded, or nothing for PAL_CLEAR (src/palette.c).
    for i, ink in zip((13, 14), inks or ()):
        pt[i] = 0 if ink & 0x8000 else rgb555(fade(ink, base, f))
    return G + fg + a + b + ([0x20] * 16 if pic_black else P) + pt


def title_inks(emu):
    """pal_ink, if pal_inked says the title has set it."""
    if not petscii.ram(emu, "pal_inked")[0]:
        return None
    raw = petscii.ram(emu, "pal_ink", 4)
    return (raw[0] | raw[1] << 8, raw[2] | raw[3] << 8)


def read_palettes(emu):
    raw = petscii.xram(emu, "XRAM_PAL_GAME", 192)
    return [raw[i] | raw[i + 1] << 8 for i in range(0, 192, 2)]


def in_game(f, base):
    # In play the picture layer is the cover's black, and the text over a
    # picture keeps the intro's colours.
    return palettes(f, base, T["amiga_pal_intro"], True)


with rp6502.Emu() as emu:
    # A screen change fades to black and back: watch the white in the game
    # palette from START to the level.
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU')
    # The title's pulse changes pal_ink every 7 frames, and the palettes follow
    # at the next VSYNC: compare when nothing is waiting to be written.
    for _ in range(3):
        if not petscii.ram(emu, "pal_dirty")[0]:
            break
        emu.cmd("run 1")
    if read_palettes(emu) != palettes(15, 0, T["amiga_pal_intro"], False,
                                      title_inks(emu)):
        fail("the intro's palettes are not amiga_pal_intro at full brightness")
    emu.cmd("run 30")
    emu.cmd("press space")
    white = []
    for _ in range(80):
        emu.cmd("run 1")
        white.append(read_palettes(emu)[1])
        if len(white) == 4:
            emu.cmd("release space")
    seen = sorted(set(white))
    if white[-1] != rgb555(0xFFF) or 0x20 not in white or len(seen) < 12:
        fail(f"no fade out and in at the game's start: {[hex(v) for v in seen]}")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_PLAY')
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    if read_palettes(emu) != in_game(15, 0):
        fail("the game's palettes at rest are not the Amiga's")

    # A hit flashes red and the EMP blue: from 60% of the way back to the
    # colours, a level a frame.
    for counter, base, what in (("BORDER", 0xF00, "hit"), ("BGFLASH", 0x00F, "EMP")):
        emu.cmd(f"poke {counter} 10")
        levels = []
        for _ in range(12):
            emu.cmd("run 1")
            n = petscii.ram(emu, counter)[0]
            f = 15 - n
            levels.append(f)
            if read_palettes(emu) != in_game(f, base if n else 0):
                fail(f"{what} flash at level {f}: palettes are not the model's")
                break
        if levels[:9] != list(range(6, 15)) or levels[-1] != 15:
            fail(f"{what} flash levels {levels}")

    # Shake: everything 3 pixels right, two frames in four.
    def offsets():
        tile = petscii.xram(emu, "XRAM_PF", 2)[0]
        player = petscii.xram(emu, "XRAM_PF+109*10", 2)
        hud = petscii.xram(emu, "XRAM_CFG_HUD+2", 2)[0]
        text = petscii.xram(emu, "XRAM_CFG_CHARS+2", 2)[0]
        health = petscii.xram(emu, "XRAM_HUD+2*10", 2)
        return (tile, (player[0] | player[1] << 8) - 120, hud, text,
                (health[0] | health[1] << 8) - 272)
    # Each is checked on its own: the emulator's frame boundary can fall part
    # way through the vblank work, after the tiles are moved and before the
    # player's record is, so one can show a frame after another here.
    emu.cmd("poke SCREEN_SHAKE 1")
    seqs = [[] for _ in range(5)]
    for _ in range(12):
        emu.cmd("run 1")
        for k, v in enumerate(offsets()):
            seqs[k].append(v)
    emu.cmd("poke SCREEN_SHAKE 0")
    emu.cmd("run 2")
    names = ("tiles", "player", "HUD frame", "text", "health picture")
    # Two on and two off from the vblank after the poke. A sample taken part
    # way through the vblank work shows what it has not written yet a frame
    # late, and where the boundary falls is the code's timing: it can fall
    # just before the player's record at every change one way and at none the
    # other, so that he shows three frames on and one off. So each sample is
    # checked against the frame it was taken in, or failing that the one
    # before: never two frames late, never early.
    want = [3, 3, 0, 0] * 3
    for name, seq in zip(names, seqs):
        if (set(seq) != {0, 3}
                or any(v not in (want[i], want[i - 1] if i else 0)
                       for i, v in enumerate(seq))):
            fail(f"{name} shake offsets {seq}, not two frames on and two off")
    if offsets() != (0, 0, 0, 0, 0):
        fail(f"shake did not stop: {offsets()}")

    # Search with the move keys: the player turns to the square chosen.
    petscii.tap(emu, "z", hold=4, after=6)
    petscii.tap(emu, "l", hold=4, after=30)
    if petscii.ram(emu, "PLAYER_DIRECTION")[0] != 9:
        fail("choosing a square with L did not turn the player right")

    # F6 stops the music and starts it again; F2 cycles the item. Level a's
    # song is the first of the four, SONG_LEVEL.
    if petscii.ram(emu, "music_song")[0] != 3:
        fail(f"song {petscii.ram(emu, 'music_song')[0]} in play, not level a's, 3")
    petscii.tap(emu, "f6", hold=4, after=30)
    if petscii.music_on(emu):
        fail("F6 did not stop the music")
    petscii.tap(emu, "f6", hold=4, after=30)
    if petscii.ram(emu, "music_song")[0] != 3:
        fail("F6 did not start level a's song again")
    emu.cmd("poke INV_MEDKIT 1")
    petscii.tap(emu, "f2", hold=4, after=30)
    if not petscii.probe(emu)["WEAPON_ITEM"] >> 4:
        fail("F2 did not cycle to the medkit")

    # SHIFT+C, the cheat: every key, a hundred of everything, the pistol and
    # the time bomb selected. Then a bomb, placed to the right, and the shake
    # when it goes off.
    emu.cmd("press lshift")
    petscii.tap(emu, "c", hold=4, after=4)
    emu.cmd("release lshift")
    emu.cmd("run 10")
    got = [petscii.ram(emu, n)[0] for n in ("KEYS", "AMMO_PLASMA", "INV_BOMBS")]
    if got != [7, 100, 100] or petscii.probe(emu)["WEAPON_ITEM"] != 0x11:
        fail(f"SHIFT+C gave keys, plasma, bombs {got}")
    petscii.tap(emu, "space", hold=4, after=6)
    petscii.tap(emu, "l", hold=4, after=10)
    if petscii.ram(emu, "INV_BOMBS")[0] != 99:
        fail("the time bomb was not placed")
    shaken = set()
    for _ in range(250):
        emu.cmd("run 1")
        if petscii.ram(emu, "SCREEN_SHAKE")[0]:
            shaken.add(petscii.xram(emu, "XRAM_PF", 1)[0])
    if shaken != {0, 3}:
        fail(f"the bomb's explosion shook the tiles by {sorted(shaken)}")
    if petscii.xram(emu, "XRAM_PF", 1)[0] != 0:
        fail("the shake did not stop with the explosion")

with rp6502.Emu() as emu:
    # level-d's cinema, tiles 20 to 22 at 118..120,4, with the window on it.
    petscii.boot(emu, "d")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')
    emu.cmd("poke MAP_WINDOW_X 117 2")
    emu.cmd("poke REDRAW_WINDOW 1")
    emu.cmd("run 30")
    message = petscii.ram(emu, "CINEMA_MESSAGE", 197)
    font = petscii.xram(emu, "XRAM_FONT", 2048)
    pair = (0x00, 0x01, 0x10, 0x11)

    def marquee_ok(state):
        k = 0
        for mx, cols in ((118, (1, 2)), (119, (0, 1, 2)), (120, (0,))):
            slot = (5 % 9) * 13 + (mx + 1) % 13
            got = petscii.xram(emu, f"XRAM_VIEW+{slot * IMG}", IMG)
            tile = 20 + mx - 118
            if not petscii.tile_matches(got, tile):
                return False
            for col in cols:
                code = message[(state + k) % 197]
                k += 1
                for r in range(8):
                    b = font[r * 256 + code]
                    want = bytes((pair[b >> 6], pair[(b >> 4) & 3],
                                  pair[(b >> 2) & 3], pair[b & 3]))
                    at = (8 + r) * 12 + col * 4
                    if got[at:at + 4] != want:
                        return False
        return True

    # The state moves in the AI tick and the slots in the next vblank's work,
    # so look half way between steps.
    s0 = petscii.ram(emu, "CINEMA_STATE")[0]
    for _ in range(25):
        emu.cmd("run 1")
        if petscii.ram(emu, "CINEMA_STATE")[0] != s0:
            break
    emu.cmd("run 10")
    shown = []
    for _ in range(3):
        s = petscii.ram(emu, "CINEMA_STATE")[0]
        if not marquee_ok(s):
            fail(f"the marquee does not show the message from {s}")
        shown.append(s)
        emu.cmd("run 20")
    if len(set(shown)) != 3:
        fail(f"the marquee did not move: states {shown}")

    # The tiles' clock, 2.1's ANIMATE_WATER ($5650), from the AI tick: from a
    # step of group A, group B steps 15 ticks on and A again at 30. A tick is
    # a frame while no pass runs over, which the probe counts.
    def clock():
        return [petscii.ram(emu, n)[0] for n in CLOCK]

    a0 = petscii.ram(emu, "ANIM_STATE")[0]
    for _ in range(35):
        emu.cmd("run 1")
        if petscii.ram(emu, "ANIM_STATE")[0] != a0:
            break
    else:
        fail("ANIM_STATE did not step")
    overruns = petscii.probe(emu)["OVERRUN"]
    steps, last = [], clock()
    for f in range(1, 31):
        emu.cmd("run 1")
        now = clock()
        steps += [(n, f) for n, was, new in zip(CLOCK, last, now)
                  if n != "CINEMA_STATE" and was != new]
        last = now
    if steps != STEPS:
        fail(f"the tile animations stepped at {steps}, not {STEPS}")
    if petscii.probe(emu)["OVERRUN"] != overruns:
        fail("a pass ran over while the animations were timed")

    # The pause runs no AI, so the tiles and the marquee stand still in it,
    # as everything does in 2.1's; N lets them go on.
    petscii.tap(emu, "escape", hold=6, after=10)
    before = clock()
    emu.cmd("run 70")
    if clock() != before:
        fail(f"in the pause the animations went {before} to {clock()}")
    petscii.tap(emu, "n", hold=6, after=10)
    before = clock()
    emu.cmd("run 45")
    if any(a == b for a, b in zip(before, clock())):
        fail(f"after the pause the animations went {before} to {clock()}")

sys.exit(1 if failures else 0)
