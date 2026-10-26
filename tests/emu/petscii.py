"""The moves every Python emulator test makes, on top of rp6502.Emu.

A test imports this beside itself; rp6502_test() puts tools/ on the path for
rp6502. Addresses come from robots.sym through emu.sym, never from literals, so
nothing here moves when the code or the XRAM layout does. docs/test-abi.md
describes the probe block and the lines the game prints.
"""
import functools
import pathlib
import re
import struct

import rp6502

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEVELS = "abcdefghijklmnopqr"
IMG = 288                       # bytes in a 24x24 4bpp image
FACE_BASE = {0: 8, 3: 0, 6: 12, 9: 4}   # PLAYER_DIRECTION -> first frame

# The probe's fields, in the order of the PROBE_ offsets in src/probe.h.
PROBE_FIELDS = ("STATE", "LEVEL", "PLAYER_X", "PLAYER_Y", "HEALTH", "ROBOTS",
                "RNG", "FRAME", "WINDOW_X", "WINDOW_Y", "UNITS_LO", "UNITS_HI",
                "VISIBLE", "WEAPON_ITEM", "LOADS", "UNITS", "ANIM", "PENDING",
                "BLANK", "OVERRUN", "LIVEMAP")


def tap(emu, key, hold=6, after=10):
    """Press a key long enough for the menu to see it, then let go."""
    emu.cmd(f"press {key}")
    emu.cmd(f"run {hold}")
    emu.cmd(f"release {key}")
    emu.cmd(f"run {after}")


def menu(emu, level="a", difficulty=1):
    """From power-on to the intro menu with <level> chosen: CHANGE MAP once
    per level after the first, then, for any difficulty but normal, down to
    DIFFICULTY and round to it -- normal, hard, easy. The last option used
    stays selected."""
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU')
    emu.cmd("run 30")
    tap(emu, "k")
    for _ in range(LEVELS.index(level)):
        tap(emu, "space")
    if difficulty != 1:
        tap(emu, "k")
        for _ in range((difficulty - 1) % 3):
            tap(emu, "space")


def start(emu, level="a"):
    """From the intro menu, back up to START GAME, start, and wait until
    <level> is playing."""
    for _ in range(ram(emu, "MENUY")[0]):
        tap(emu, "i")
    emu.cmd("press space")
    emu.cmd("run 6")
    emu.cmd("release space")
    emu.cmd("wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_PLAY")
    if probe(emu)["LEVEL"] != LEVELS.index(level):
        raise RuntimeError(f"started level {probe(emu)['LEVEL']}, not {level}")


def boot(emu, level="a", difficulty=1):
    """From power-on to playing <level> at <difficulty>, 0 easy, 1 normal,
    2 hard."""
    menu(emu, level, difficulty)
    start(emu, level)


def xram(emu, name, count=1):
    """Bytes of XRAM at a symbol, or an expression of symbols."""
    return bytes.fromhex(emu.cmd(f"dump xram:{name} {count}"))


def ram(emu, name, count=1):
    """Bytes of 6502 RAM at a symbol, or an expression of symbols."""
    return bytes.fromhex(emu.cmd(f"dump {name} {count}"))


def music_on(emu):
    """Whether a song is playing: src/sound.c's music_song, SONG_NONE when
    none is."""
    return ram(emu, "music_song")[0] != 0xFF


def probe(emu):
    """The probe block as a dict of its fields, checked for its magic."""
    size = emu.sym["PROBE_SIZE"]
    block = xram(emu, "XRAM_PROBE", size)
    magic = bytes((emu.sym["PROBE_MAGIC_0"], emu.sym["PROBE_MAGIC_1"]))
    if block[0:2] != magic:
        raise AssertionError(f"probe magic is {block[0:2].hex()}, not {magic.hex()}")
    return {f: block[emu.sym["PROBE_" + f]] for f in PROBE_FIELDS}


@functools.lru_cache(maxsize=None)
def amiga_tables():
    """The labelled .byte/.word tables of assets/gen/amiga_tables.s, by name
    without the leading underscore."""
    out, name = {}, None
    for line in (ROOT / "assets" / "gen" / "amiga_tables.s").read_text().splitlines():
        line = line.split(";", 1)[0].strip()
        m = re.match(r"([A-Za-z_]\w*):(.*)", line)
        if m:
            name, line = m.group(1).lstrip("_"), m.group(2).strip()
            out[name] = []
        m = re.match(r"\.(byte|word)\s+(.*)", line)
        if m and name:
            for v in m.group(2).split(","):
                v = v.strip()
                out[name].append(int(v[1:], 16) if v.startswith("$") else int(v, 0))
    return out


def rgb555(c, alpha=True):
    """An RGB4 colour, $0RGB as amiga_tables.s holds them, as src/palette.s
    writes it to a palette: RGB555 with blue in the high bits and the opacity
    bit, $20, set unless alpha is False."""
    to5 = lambda v: v * 17 >> 3
    return (to5(c & 15) << 11 | to5((c >> 4) & 15) << 6
            | (0x20 if alpha else 0) | to5((c >> 8) & 15))


def gen(name):
    """A file the build wrote to assets/gen."""
    return (ROOT / "assets" / "gen" / name).read_bytes()


def x16(name):
    """One of X16 2.1's own files in assets/src/x16, the oracle for what
    came from it: the maps, their names and their start squares."""
    return (ROOT / "assets" / "src" / "x16" / name).read_bytes()


@functools.lru_cache(maxsize=None)
def images():
    """ROM:images as the build wrote it: 288-byte records."""
    return gen("images.bin")


def tile_matches(got, t):
    """Whether a cache slot's 288 bytes are tile t's image. A cinema's tiles,
    20 to 22, carry the marquee across their middle character row, rows 8 to
    15, which src/view.c writes over the image; those rows are not compared."""
    want = images()[t * IMG:(t + 1) * IMG]
    if 20 <= t <= 22:
        return got[:96] == want[:96] and got[192:] == want[192:]
    return got == want


def pending(emu):
    """view_pending() in src/view.c, read from RAM. The probe's PENDING is the
    same, but written at the start of a tick, before the tick's own redraw,
    which can leave something on its way that the probe has not seen: a unit
    gone from the player's square, say, and his frame still to load."""
    r = lambda name: ram(emu, name)[0]
    want, hidden = r("player_want"), 0xFE       # PLAYER_HIDDEN
    return bool(r("walk_phase") or r("inflight") or r("black")
                or r("player_flip") or r("player_put")
                or r("view_ptrs_dirty") or r("view_units_dirty")
                or (want < hidden and want != r("player_shown")))


def settle(emu, fail):
    """Run until no redraw is asked for and nothing is on its way to the
    screen, so the screen matches RAM."""
    for _ in range(60):
        if ram(emu, "REDRAW_WINDOW")[0] == 0 and not pending(emu):
            return
        emu.cmd("run 1")
    fail("the playfield never settled")


def check_units_bank(emu, fail):
    """XRAM's resident unit bank against assets/gen/units.bin. The ROM loads
    it once and nothing writes it after, so once a boot is enough;
    check_playfield checks which record each unit shows."""
    if xram(emu, "XRAM_UNITS", 38 * IMG) != gen("units.bin"):
        fail("XRAM_UNITS is not assets/gen/units.bin")


def check_playfield(emu, where, fail):
    """Settle, then check every playfield sprite against the map: each window
    cell's record and image (an animation frame, or its cache slot holding its
    tile), the unit sprites MAP_PRE_CALCULATE asks for, and the player's frame.
    Reports through fail(what)."""
    T, IMAGES = amiga_tables(), images()
    s = emu.sym
    settle(emu, fail)
    wx, wy = ram(emu, "MAP_WINDOW_X")[0], ram(emu, "MAP_WINDOW_Y")[0]
    mp = ram(emu, "MAP", 128 * 64)
    precalc = ram(emu, "MAP_PRECALC", 77)
    # Each group of animated tiles has its own count, as 2.1's ANIMATE_WATER
    # steps them: bit 6 of a tile's entry is group B, the compactor and fans.
    anim, anim_b = ram(emu, "ANIM_STATE")[0], ram(emu, "ANIM_STATE_B")[0]
    pf = xram(emu, "XRAM_PF", 110 * 10)
    rec = [struct.unpack_from("<hhHHBB", pf, i * 10) for i in range(110)]
    bad = 0

    for r in range(7):
        for c in range(11):
            n = r * 11 + c
            x, y, ptr, pal, wh, attr = rec[n]
            if (x, y, pal, wh, attr) != (24 * c, s["SCREEN_TOP"] + 24 * r, s["XRAM_PAL_GAME"], 0x55, 2):
                fail(f"{where}: tile sprite {n} record {rec[n]}")
            t = mp[(wy + r) * 128 + wx + c]
            a = T["amiga_tile_anim"][t]
            if a != 0xFF:
                frame = (a & 0x1F) + ((anim_b if a & 0x40 else anim)
                                      & (3 if a & 0x80 else 1))
                if ptr != s["XRAM_ANIM"] + IMG * frame:
                    fail(f"{where}: cell ({c},{r}) tile {t} shows ${ptr:04X}, "
                         f"not animation frame {frame}")
                continue
            slot = ((wy + r + 1) % 9) * 13 + (wx + c + 1) % 13
            if ptr != s["XRAM_VIEW"] + IMG * slot:
                fail(f"{where}: cell ({c},{r}) shows ${ptr:04X}, not slot {slot}")
                continue
            got = xram(emu, f"XRAM_VIEW+{IMG * slot}", IMG)
            if not tile_matches(got, t):
                bad += 1
                fail(f"{where}: slot {slot} for cell ({c},{r}) does not hold tile {t}")

    # Which unit each cell's tile is, and what it carries: the evilbot's
    # facing is added to its frame, and a wreck is the one its robot leaves.
    # On the player's own cell a bomb or magnet does not show and an
    # explosion covers him.
    unit = ram(emu, "MAP_PRECALC_UNIT", 77)
    facing = ram(emu, "UNIT_DIRECTION", 32)
    kind = ram(emu, "UNIT_A", 64)
    px, py = ram(emu, "UNIT_LOC_X")[0], ram(emu, "UNIT_LOC_Y")[0]
    pc = (py - wy) * 11 + (px - wx)
    covered = False
    want = []
    for n, t in enumerate(precalc):
        b = T["amiga_unit_bank"][t] if t else 0xFF
        if n == pc and t in (130, 134):
            continue
        if n == pc and (t == 246 or 248 <= t <= 252):
            covered = True
        if 100 <= t <= 103:
            b += (8, 0, 12, 4)[facing[unit[n]] & 3]
        elif t == 115:
            a = kind[unit[n]]
            b += 2 if a == 9 else 1 if a in (17, 18) else 0
        if b != 0xFF and len(want) < 32:
            pal = (s["XRAM_PAL_FG"], s["XRAM_PAL_A"], s["XRAM_PAL_B"])[T["amiga_bank_pal"][b]]
            want.append((24 * (n % 11), s["SCREEN_TOP"] + 24 * (n // 11),
                         s["XRAM_UNITS"] + IMG * b, pal))
    got = [r[:4] for r in rec[77:109]]
    for k in range(32):
        if k < len(want):
            if got[k] != want[k]:
                fail(f"{where}: unit sprite {k} is {got[k]}, expected {want[k]}")
        elif got[k][1] != 240:
            fail(f"{where}: unit sprite {k} is not parked: {got[k]}")
    # And no sprite outlives its unit: every unit sprite shown stands where a
    # unit is now. A robot that steps out of the window must take its sprite
    # with it.
    t_, x_, y_ = ram(emu, "UNIT_TYPE", 32), ram(emu, "UNIT_LOC_X", 32), ram(emu, "UNIT_LOC_Y", 32)
    here = {(x_[i] - wx, y_[i] - wy) for i in range(1, 32) if t_[i]}
    for k in range(32):
        x, y = got[k][0], got[k][1]
        if y != 240 and ((x // 24, (y - s["SCREEN_TOP"]) // 24) not in here):
            fail(f"{where}: unit sprite {k} at {x},{y} has no unit there")
    # The count the probe reports, read where it comes from: the probe is
    # written at the start of a tick, before that tick's redraw.
    if ram(emu, "view_units")[0] != len(want):
        fail(f"{where}: view_units counts {ram(emu, 'view_units')[0]} units, "
             f"expected {len(want)}")

    d = ram(emu, "PLAYER_DIRECTION")[0]
    if d != 12:
        walk = ram(emu, "PLAYER_ANIMATE")[0] & 3
        weapon = ram(emu, "SELECTED_WEAPON")[0]
        frame = FACE_BASE[d] + walk + (weapon << 4)
    else:
        frame = 48
    if ram(emu, "UNIT_TILE")[0] == 97 and d != 12:
        frame = 1                       # just transported: the Amiga's tile 97
    # Dematerializing, alive: 2.1's eight frames, 88-95 in UNIT_TILE as 2.1
    # keeps them, which src/view.c numbers 76-83. view.c checks it after death
    # and before tile 97, which is still his if he goes again before taking a
    # step, so here it comes after the tile-97 rule and overrides it.
    if d != 12 and ram(emu, "player_demat")[0]:
        frame = 76 + ram(emu, "UNIT_TILE")[0] - 88
    record = s["IMG_PLAYER"] + (frame if frame <= 48 else frame - 27)
    x, y, ptr, pal, wh, attr = rec[109]
    if covered or ram(emu, "UNIT_TYPE")[0] == 2:
        if y != 240:
            fail(f"{where}: the player shows, covered or transported away")
    elif (x, y, pal, wh, attr) != (120, s["SCREEN_TOP"] + 72, s["XRAM_PAL_A"], 0x55, 2):
        fail(f"{where}: player record {rec[109]}")
    elif ptr not in (s["XRAM_PLAYER"], s["XRAM_PLAYER"] + IMG):
        fail(f"{where}: player shows ${ptr:04X}")
    elif xram(emu, f"{ptr}", IMG) != IMAGES[record * IMG:(record + 1) * IMG]:
        fail(f"{where}: player image is not frame {frame}")
    print(f"{where}: window {wx},{wy}, {len(want)} units, anim {anim} {anim_b}"
          + (f", {bad} bad slots" if bad else ""))
