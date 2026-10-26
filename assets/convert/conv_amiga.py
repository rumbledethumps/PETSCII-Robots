#!/usr/bin/env python3
"""Amiga and X16 2.1 art -> RP6502 VGA assets.

The art is the Amiga version of Attack of the PETSCII Robots (David Murray;
Amiga port by Vesa Halttunen, CC BY 4.0), kept as shipped in assets/src/amiga/,
but for what comes from David Murray's X16 version 2.1 in assets/src/x16/:
2.1's rework of the Amiga's title picture, player, robots and their wrecks,
bomb, canister about to blow and magnet, shots, small explosion and tiles 155
and 246, and 2.1's own eyes for the intro robot and icons for the cursor.
assets/convert/clean_title.py cuts 2.1's title to 320x200 first, and this takes
it from there (--title).

Every image comes out 4bpp but the cursors, which are 2bpp, rows top to bottom
with the leftmost pixel in the HIGH bits -- two pixels a byte, the even one in
the high nibble, or four, the first in bits 7-6: the VGA's packing for mode 3
bitmaps, mode 5 sprites and mode 2 tiles alike, so one packer serves them all.
2.1's own pictures are packed the same way.

    images.bin     352 x 288  24x24 records, read by number at run time:
                     0-252    tiles.png, indices as-is, but 155 and 246,
                              which are 2.1's
                     253-309  the player: 2.1's sprites 0-47, 96 (dead),
                              then 88-95 (dematerializing)
                     310-321  items, 48x21 padded to 48x24: 2 records each
                     322-351  health, 48x51 padded to 48x52: 5 records each
    anim.bin        24 x 288  animtiles.png, in file order
    units.bin       38 x 288  the resident robot / shot / explosion bank, BANK
    hud_tiles.bin   72 x 32   gamescreen.png cut into deduplicated 8x8 tiles
    hud_map.bin     40 x 25   ...and the map that rebuilds it; tile 0 is blank
    keys.bin         3 x 128  16x14 keys padded to 16x16
    cursors.bin      3 x 196  2.1's sprites 100-102: the arrows to use an item,
                              the magnifier to search, the hand to move; 28x28
                              2bpp in palette b, 7 bytes a row
    font.bin          2048    C64 font row-major (font[row*256+glyph]) for mode
                              1; 128-255 are 0-127 inverted, as the Amiga draws
    intro.bin        32000    2.1's title (clean_title.py), 320x200
    gameover.bin     32000    gameover.png, 320x200
    amiga_tables.s            palettes, eyes and lookup tables for the ROM

Sprites. 2.1's sprites.bin is 104 sprites of 32x32 in its unit palette
(ROBOTS.PRG $30CE), where 0 is transparent and 1 black. The RP6502's are
24x24, so each is cut at its top left, where 2.1 draws the art; the five that
lose a pixel by it, outline ends, are CROP_LOSS, and any other loss fails
here. Each is then re-indexed, matching by colour, into the palette it is
drawn with (src/palette.c), where 0 is transparent: a for the player, the game
colours with black at 8; b for the robots, wrecks, bomb, canister and magnet,
which is 2.1's unit palette with entries 2 and 5 swapped, black at 1 and white
at 2 (PAL_B_ORDER); fg for the shots and the small explosion, the game colours
with no black. Each lacks one colour -- 560 in a, 039 in b, black in fg -- and
a sprite that uses it fails here instead of quietly losing it. The one tile in
the unit bank, 2.1's 246, keeps index 0: it draws through fg too, so its black
is clear.
The cursor's icons, 100-102, are cut to 28x28 instead, which loses nothing,
and re-indexed into b too, where their black and white are 1 and 2: with
clear, they need only b's first four entries, so they pack at 2bpp, and one
that needs more fails here.

2.1's tiles.bin is the Amiga's tiles in 2.1's tile palette ($30AE), the game
colours in another order, but for two it retouched, 155 and 246, and the units
it draws as sprites, which it leaves blank. Those two are taken from it,
re-indexed by colour, and every other one is checked to be tiles.png's tile or
blank.

Palettes are RGB4, $0RGB, the Amiga's own depth. Every PLTE channel is checked
to be a multiple of 17 so nothing is rounded, and every PNG that shares a
palette is checked to really share it.

The title and the eyes are 2.1's picture in 2.1's title palette, which is the
Amiga intro's sixteen colours in another order but for the white: 2.1's is FFF
where the Amiga's is EEE. Both are re-indexed into the Amiga intro's order,
matched by colour, with FFF in EEE's slot, so the intro palette is the Amiga's
with that one entry changed and the menu's colours, 14 and 15, keep their
meaning. Anything else that differs fails here.
"""
import argparse
import pathlib
import sys

import amiga_tables as T
import png

TILE = 24
REC = TILE * TILE // 2              # 288: one 24x24 4bpp record
TILES = 253                         # tiles.png height / 24
PAL_FG, PAL_A, PAL_B = 0, 1, 2      # _amiga_bank_pal values

# The player, as 2.1 numbers its sprites: facing down, right, up and left,
# four walk frames each, sixteen for each weapon; dead; then dematerializing.
PLAYER_FRAMES = [*range(48), 96, *range(88, 96)]

# The cursor's icons, as CURSOR_ON 1, 2 and 3 pick them: the arrows to use an
# item, the magnifier to search, the hand to move. 25 pixels square at most,
# so 28x28, mode 5's next size up, holds them whole.
CURSORS21 = (100, 101, 102)
CURSOR = 28

# The game colour each entry of palette b shows: 2.1's unit palette with its
# entries 2 and 5 swapped, so that black is 1 and white 2 -- entries 0-3 then
# draw a black and white 2bpp image, as 2.1's cursor icons are -- and 039,
# which no unit sprite has, is left out.
PAL_B_ORDER = (None, 0, 1, 3, 4, 2, *range(6, 16))
BLACK_A = 8                         # where black goes in palette a

# The animated tiles 2.1's ANIMATE_WATER steps in its group B ($5707): the
# compactor and the fans, half way between the steps of group A, the water,
# the flag and the server light. _amiga_tile_anim marks them with bit 6.
ANIM_GROUP_B = (148, 196, 197, 200, 201)

# 2.1's sprites that lose pixels when cut from 32x32 to 24x24, and how many:
# the ends of an evilbot's (71, 75), a shot's (77), the dead player's (96)
# and the hoverbot's wreck's (98) outlines.
CROP_LOSS = {71: 3, 75: 3, 77: 1, 96: 4, 98: 2}

# The resident unit bank, as (UNIT_TILE, source, palette). The source is
# ("x16", n) for 2.1's sprite n, or ("x16tile", t) for 2.1's tile t. 100-103
# are the evilbot facing down; src/view.c adds 8, 0, 12 or 4 for up, down,
# left and right, which is where 2.1's frames for those facings sit. 115 is
# the hoverbot's wreck; view.c adds 1 for a rollerbot's and 2 for the
# evilbot's. Those records have no UNIT_TILE of their own, None. The
# rollerbot's frames are 164-167, 2.1's four, and the small explosion's
# 248-252, 2.1's five.
BANK = ([(98, ("x16", 52), PAL_B), (99, ("x16", 53), PAL_B),        # hoverbot
         (164, ("x16", 48), PAL_B), (165, ("x16", 49), PAL_B)]      # rollerbot
        + [(100 + k if k < 4 else None, ("x16", 60 + k), PAL_B) for k in range(16)]
        + [(115, ("x16", 98), PAL_B), (None, ("x16", 97), PAL_B),
           (None, ("x16", 99), PAL_B)]
        + [(130, ("x16", 85), PAL_B), (131, ("x16", 103), PAL_B),   # bomb, canister about to blow
           (134, ("x16", 86), PAL_B)]                               # magnet
        + [(166, ("x16", 50), PAL_B), (167, ("x16", 51), PAL_B)]    # rollerbot, 2.1's frames 3, 4
        + [(240, ("x16", 78), PAL_FG), (241, ("x16", 79), PAL_FG),  # plasma
           (244, ("x16", 76), PAL_FG), (245, ("x16", 77), PAL_FG)]  # pistol
        + [(246, ("x16tile", 246), PAL_FG)]                         # big explosion
        + [(248 + k, ("x16", 80 + k), PAL_FG) for k in range(5)])   # small one, 2.1's five

HUD_COLS, HUD_ROWS, HUD_TILES = 40, 25, 72
INPUTS = ("tiles.png", "animtiles.png", "items.png", "health.png", "keys.png",
          "gamescreen.png", "introscreen.png", "gameover.png", "C64Font.raw")

# X16 2.1's files, and where ROBOTS.PRG keeps what is read from it. It loads
# at $0801, after its two-byte load address.
X16_INPUTS = ("ROBOTS.PRG", "sprites.bin", "tiles.bin", "faces.bin")
X16_LOAD = 0x0801
TITLE_PAL = 0x308E                  # P1, the title's palette
TILE_PAL = 0x30AE                   # P2, the tiles'
UNIT_PAL = 0x30CE                   # P3, the sprites'
THREE_FACES = 0x2E7E                # the eyes, which faces.bin holds too
FACE_W, FACE_H, FACES = 16, 10, 3   # easy, normal, hard
SPRITE21, SPRITES21 = 32, 104       # sprites.bin: 104 of 32x32, 512 bytes each
X16_TILES = (155, 246)              # tiles.bin's own tiles
# tiles.bin's blank tiles: units 2.1 draws from its sprites. The canister
# about to blow, sprite 103, is not one: tile 131 is also the canister on the
# map, so tiles.bin keeps it.
X16_BLANK = {130, 134, 240, 241, 244, 245, *range(248, 253)}


def fail(msg):
    sys.exit(f"conv_amiga: {msg}")


def need(cond, msg):
    if not cond:
        fail(msg)


def pack(rows, bpp=4) -> bytes:
    """Rows of pixel indices, bpp bits each, the leftmost in a byte's high
    bits."""
    per = 8 // bpp
    out = bytearray()
    for r in rows:
        need(len(r) % per == 0, f"row width {len(r)} is not whole bytes at {bpp}bpp")
        for x in range(0, len(r), per):
            v = 0
            for p in r[x:x + per]:
                need(p < 1 << bpp, f"pixel index {p} does not fit {bpp} bits")
                v = v << bpp | p
            out.append(v)
    return bytes(out)


def unpack4(blob, w, h, off=0):
    """2.1's 4bpp, which is the VGA's: the left pixel in the high nibble."""
    s = w // 2
    return [[(blob[off + y * s + x // 2] >> (0 if x & 1 else 4)) & 15 for x in range(w)]
            for y in range(h)]


def prg_bytes(prg, addr, n):
    """n bytes of ROBOTS.PRG at a 2.1 address."""
    o = addr - X16_LOAD + 2
    return prg[o:o + n]


def x16_palette(prg, addr):
    """Sixteen VERA palette entries, two bytes each, GB then 0R, as $0RGB."""
    d = prg_bytes(prg, addr, 32)
    return [(d[i + 1] & 15) << 8 | d[i] for i in range(0, 32, 2)]


def strip(img, h, i, w=None):
    """Frame i of a vertical strip of h-row frames, cropped to w columns."""
    w = img.width if w is None else w
    return [row[:w] for row in img.rows[i * h:(i + 1) * h]]


def blank(w, n):
    return [[0] * w for _ in range(n)]


def rgb4(name, pal):
    need(len(pal) >= 16, f"{name}: palette has only {len(pal)} entries")
    for i, c in enumerate(pal[:16]):
        need(all(v % 17 == 0 for v in c),
             f"{name}: palette entry {i} #{bytes(c).hex()} is not 4-bit (channels must be multiples of 17)")
    return [(r // 17) << 8 | (g // 17) << 4 | (b // 17) for r, g, b in pal[:16]]


def asm_table(label, values, word=False, per=16):
    lines = [f"{label}:"]
    fmt, op = ("${:04X}", ".word") if word else ("${:02X}", ".byte")
    for i in range(0, len(values), per):
        lines.append(f"        {op}   " + ",".join(fmt.format(v) for v in values[i:i + per]))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=pathlib.Path, required=True, help="assets/src/amiga")
    ap.add_argument("--x16", type=pathlib.Path, required=True, help="assets/src/x16")
    ap.add_argument("--title", type=pathlib.Path, required=True,
                    help="2.1's title as clean_title.py leaves it")
    ap.add_argument("--out", type=pathlib.Path, required=True, help="the gen directory")
    args = ap.parse_args()

    for n in INPUTS:
        need((args.src / n).is_file(), f"missing input {args.src / n}")
    for n in X16_INPUTS:
        need((args.x16 / n).is_file(), f"missing input {args.x16 / n}")
    try:
        img = {n[:-4]: png.read(args.src / n) for n in INPUTS if n.endswith(".png")}
        img["title21"] = png.read(args.title)
    except png.PNGError as e:
        fail(str(e))
    prg = (args.x16 / "ROBOTS.PRG").read_bytes()
    need(prg[0] | prg[1] << 8 == X16_LOAD, "ROBOTS.PRG does not load at $0801")
    sprites21 = (args.x16 / "sprites.bin").read_bytes()
    need(len(sprites21) == SPRITES21 * SPRITE21 * SPRITE21 // 2,
         f"sprites.bin is {len(sprites21)} bytes, expected {SPRITES21 * SPRITE21 * SPRITE21 // 2}")
    tiles21 = (args.x16 / "tiles.bin").read_bytes()
    # 256 tiles, 28 to an 8 KB bank, the last bank holding the four left over.
    need(len(tiles21) == 256 // 28 * 8192 + 256 % 28 * REC,
         f"tiles.bin is {len(tiles21)} bytes, expected {256 // 28 * 8192 + 256 % 28 * REC}")

    def size(name, w, h):
        i = img[name]
        need((i.width, i.height) == (w, h),
             f"{name}.png is {i.width}x{i.height}, expected {w}x{h}")

    size("tiles", 32, TILES * TILE)
    size("animtiles", TILE, T.ANIM_FRAMES * TILE)
    size("items", T.ITEM_W, T.ITEMS * T.ITEM_H)
    size("health", T.HEALTH_W, T.HEALTHS * T.HEALTH_H)
    size("keys", T.KEY_W, T.KEYS * T.KEY_H)
    for n in ("gamescreen", "introscreen", "gameover", "title21"):
        size(n, 320, 200)

    # ---- palettes ---------------------------------------------------------
    pal_game = rgb4("tiles.png", img["tiles"].palette)
    for n in ("animtiles", "items", "health", "keys", "gamescreen"):
        need(rgb4(f"{n}.png", img[n].palette) == pal_game,
             f"{n}.png palette[0..15] differs from tiles.png's (the game palette)")
    pal_over = rgb4("gameover.png", img["gameover"].palette)

    # 2.1's tile and unit palettes, as game colours, matched by colour and
    # never by index. The tiles' is the game palette in another order; the
    # units' 0 is transparent, 1 black, and the rest are game colours.
    p2 = x16_palette(prg, TILE_PAL)
    p2g = [pal_game.index(c) if c in pal_game else None for c in p2]
    need(None not in p2g and sorted(p2g) == list(range(16)),
         f"2.1's tile palette ($30AE) is not the game palette reordered: {[f'{c:03X}' for c in p2]}")
    p3 = x16_palette(prg, UNIT_PAL)
    p3g = [None] + [pal_game.index(c) if c in pal_game else None for c in p3[1:]]
    need(None not in p3g[1:] and p3g[1] == 0,
         f"2.1's unit palette ($30CE) is not black then game colours: {[f'{c:03X}' for c in p3]}")
    # Game colour -> the entry that shows it, in each palette a sprite is
    # drawn with.
    to_pal = {
        PAL_FG: {g: g for g in range(1, 16)},
        PAL_A: {**{g: g for g in range(1, 16) if g != BLACK_A}, 0: BLACK_A},
        PAL_B: {g: k for k, g in enumerate(PAL_B_ORDER) if g is not None},
    }

    def sprite21(n, pal, size=TILE):
        """2.1's sprite n, cut to size x size and re-indexed into palette pal."""
        rows = unpack4(sprites21, SPRITE21, SPRITE21, n * SPRITE21 * SPRITE21 // 2)
        lost = sum(1 for y, r in enumerate(rows) for x, v in enumerate(r)
                   if v and (x >= size or y >= size))
        want = CROP_LOSS.get(n, 0) if size == TILE else 0
        need(lost == want,
             f"2.1's sprite {n} loses {lost} pixels cut to {size}x{size}, expected {want}")
        out = [[0 if v == 0 else to_pal[pal].get(p3g[v]) for v in r[:size]] for r in rows[:size]]
        need(all(None not in r for r in out),
             f"2.1's sprite {n} has a colour that palette {('fg', 'a', 'b')[pal]} lacks")
        return out

    def tile21(t):
        """2.1's tile t in game palette indices."""
        return [[p2g[v] for v in r]
                for r in unpack4(tiles21, TILE, TILE, t // 28 * 8192 + t % 28 * REC)]

    # ---- images.bin -------------------------------------------------------
    tiles = img["tiles"]
    need(all(v == 0 for r in tiles.rows for v in r[TILE:]),
         "tiles.png columns 24-31 are not all 0")
    for t in range(TILES):
        if t in X16_BLANK:
            need(not any(v for r in tile21(t) for v in r), f"2.1's tile {t} is not blank")
        elif t not in X16_TILES:
            need(tile21(t) == strip(tiles, TILE, t, TILE), f"2.1's tile {t} is not tiles.png's")
    images = bytearray()
    for t in range(TILES):
        images += pack(tile21(t) if t in X16_TILES else strip(tiles, TILE, t, TILE))
    for f in PLAYER_FRAMES:
        images += pack(sprite21(f, PAL_A))
    for k in range(T.ITEMS):
        images += pack(strip(img["items"], T.ITEM_H, k) + blank(T.ITEM_W, 3))
    for k in range(T.HEALTHS):
        rec = pack(strip(img["health"], T.HEALTH_H, k) + blank(T.HEALTH_W, 1))
        images += rec + bytes(5 * REC - len(rec))
    need(len(images) == 352 * REC, f"images.bin is {len(images)}, expected {352 * REC}")

    # ---- anim.bin ---------------------------------------------------------
    anim = b"".join(pack(strip(img["animtiles"], TILE, f)) for f in range(T.ANIM_FRAMES))

    # ---- units.bin --------------------------------------------------------
    units = bytearray()
    for _, (kind, n), pal in BANK:
        units += pack(sprite21(n, pal) if kind == "x16" else tile21(n))
    need(len(units) == 38 * REC, f"units.bin is {len(units)}, expected {38 * REC}")

    unit_bank = [0xFF] * 256
    for b, (tile, _, _) in enumerate(BANK):
        if tile is not None:
            unit_bank[tile] = b
    # What src/view.c adds to a record: the evilbot's facing and the wreck's
    # robot. They have to land on 2.1's frames for those.
    need([src for _, src, _ in BANK[4:20]] == [("x16", 60 + v) for v in range(16)],
         "the evilbot's frames, 2.1's 60-75, must be records 4-19, in order")
    need([src for _, src, _ in BANK[20:23]] == [("x16", n) for n in (98, 97, 99)],
         "the wrecks, 2.1's 98, 97 and 99, must be records 20-22, in order")
    bank_pal = [pal for _, _, pal in BANK]

    # ---- HUD --------------------------------------------------------------
    screen = img["gamescreen"].rows
    ids = {bytes(32): 0}
    hud_map = bytearray()
    for by in range(HUD_ROWS):
        for bx in range(HUD_COLS):
            blk = pack([r[bx * 8:bx * 8 + 8] for r in screen[by * 8:by * 8 + 8]])
            hud_map.append(ids.setdefault(blk, len(ids)))
    need(len(ids) <= HUD_TILES,
         f"gamescreen.png has {len(ids)} unique 8x8 blocks, more than the {HUD_TILES} reserved")
    hud_tiles = b"".join(ids) + bytes((HUD_TILES - len(ids)) * 32)

    # ---- keys, cursors, font, full screens ---------------------------------
    keys = b"".join(pack(strip(img["keys"], T.KEY_H, k) + blank(T.KEY_W, 16 - T.KEY_H))
                    for k in range(T.KEYS))

    # 2.1's icons in palette b: 0 clear, 1 black, 2 white.
    cursors = bytearray()
    for n in CURSORS21:
        rows = sprite21(n, PAL_B, CURSOR)
        need(all(v < 4 for r in rows for v in r),
             f"2.1's cursor {n} has a colour beyond palette b's first four")
        cursors += pack(rows, 2)

    raw = (args.src / "C64Font.raw").read_bytes()
    need(len(raw) == 1024, f"C64Font.raw is {len(raw)} bytes, expected 1024")
    glyphs = [raw[g * 8:g * 8 + 8] for g in range(128)]
    glyphs += [bytes(~b & 0xFF for b in g) for g in glyphs]
    font = bytes(glyphs[g][r] for r in range(8) for g in range(256))
    need(not any(glyphs[32]), "glyph 32 must be blank (screen-code space)")
    need(any(glyphs[1]), "glyph 1 ('A') is blank")

    gameover = pack(img["gameover"].rows)

    # ---- 2.1's title and eyes, in the Amiga intro's order ------------------
    p1 = x16_palette(prg, TITLE_PAL)
    need(rgb4("title21.png", img["title21"].palette) == p1,
         "title21.png's palette is not 2.1's title palette (ROBOTS.PRG $308E)")
    pal_amiga = rgb4("introscreen.png", img["introscreen"].palette)
    # Title index -> the Amiga intro's index of the same colour.
    order = [pal_amiga.index(c) if c in pal_amiga else None for c in p1]
    odd = [i for i, k in enumerate(order) if k is None]
    need(len(odd) == 1 and p1[odd[0]] == 0xFFF and 0xEEE in pal_amiga
         and 0xFFF not in pal_amiga,
         "2.1's title palette must be the Amiga intro's but for its white, FFF for EEE; "
         f"{[f'{p1[i]:03X}' for i in odd]} are not in the Amiga's")
    order[odd[0]] = pal_amiga.index(0xEEE)
    need(sorted(order) == list(range(16)),
         "2.1's title colours do not map one to one onto the Amiga intro's")
    pal_intro = [0] * 16
    for i, k in enumerate(order):
        pal_intro[k] = p1[i]
    intro = pack([[order[v] for v in r] for r in img["title21"].rows])

    eyes = (args.x16 / "faces.bin").read_bytes()
    need(len(eyes) == FACES * FACE_H * FACE_W // 2,
         f"faces.bin is {len(eyes)} bytes, expected {FACES * FACE_H * FACE_W // 2}")
    need(eyes == prg_bytes(prg, THREE_FACES, len(eyes)),
         "faces.bin is not ROBOTS.PRG's THREE_FACES ($2E7E)")
    faces = pack([[order[v] for v in r] for r in unpack4(eyes, FACE_W, FACES * FACE_H)])

    # ---- amiga_tables.s ---------------------------------------------------
    tile_anim = [0xFF] * 256
    need(set(ANIM_GROUP_B) <= T.ANIM_TILE_MAP.keys(),
         f"group B tiles {ANIM_GROUP_B} are not all animated")
    bases = sorted(T.ANIM_TILE_MAP.values()) + [T.ANIM_FRAMES]
    for tile, base in T.ANIM_TILE_MAP.items():
        frames = bases[bases.index(base) + 1] - base
        need(frames in (2, 4), f"anim tile {tile}: {frames} frames")
        need(base < 0x20, f"anim tile {tile}: frame {base} reaches the group bit")
        tile_anim[tile] = (base | (0x80 if frames == 4 else 0)
                           | (0x40 if tile in ANIM_GROUP_B else 0))

    exports = ["_amiga_pal_game", "_amiga_pal_intro", "_amiga_pal_gameover",
               "_amiga_pal_b_order", "_amiga_faces", "_amiga_livemap",
               "_amiga_unit_bank", "_amiga_bank_pal", "_amiga_tile_anim"]
    asm = "\n".join([
        "; Generated by assets/convert/conv_amiga.py from assets/src/amiga/ and",
        "; assets/src/x16/ -- do not edit.",
        "",
        "        .export " + ", ".join(exports[:4]),
        "        .export " + ", ".join(exports[4:]),
        "",
        "        .segment \"RODATA\"",
        "",
        "; 16 colours each, RGB4 as $0RGB. The intro's is 2.1's title palette in",
        "; the Amiga intro's order.",
        asm_table("_amiga_pal_game", pal_game, word=True, per=8),
        asm_table("_amiga_pal_intro", pal_intro, word=True, per=8),
        asm_table("_amiga_pal_gameover", pal_over, word=True, per=8),
        "",
        "; Palette b's entries 1-15 as game palette indices: 2.1's unit palette,",
        "; black at 1 and white at 2, and no 039.",
        asm_table("_amiga_pal_b_order", PAL_B_ORDER[1:]),
        "",
        "; 3 faces, 16x10 4bpp (8 bytes a row), intro palette, 2.1's THREE_FACES.",
        asm_table("_amiga_faces", faces),
        "",
        "; Tile -> game palette index in both nibbles: a byte of two pixels,",
        "; one square's row on the live map.",
        asm_table("_amiga_livemap", [c * 0x11 for c in T.TILE_LIVE_MAP]),
        "",
        "; UNIT_TILE -> units.bin record, $FF if the unit has no bank image.",
        asm_table("_amiga_unit_bank", unit_bank),
        "",
        "; units.bin record -> palette: 0 foreground, 1 palette A, 2 palette B.",
        asm_table("_amiga_bank_pal", bank_pal),
        "",
        "; Tile -> anim.bin first frame, | $80 if it has 4 frames (else 2),",
        "; | $40 if it steps with 2.1's group B; $FF if the tile is not animated.",
        asm_table("_amiga_tile_anim", tile_anim),
        "",
    ])

    # ---- write ------------------------------------------------------------
    outputs = [
        ("images.bin", images, "352 x 24x24 4bpp: tiles 0-252, player 253-309, "
                               "items 310-321, health 322-351"),
        ("anim.bin", anim, f"{T.ANIM_FRAMES} x 24x24 4bpp animated tile frames"),
        ("units.bin", units, f"{len(BANK)} x 24x24 4bpp unit bank"),
        ("hud_tiles.bin", hud_tiles, f"{HUD_TILES} x 8x8 4bpp, {len(ids)} used"),
        ("hud_map.bin", hud_map, f"{HUD_COLS}x{HUD_ROWS} tile ids"),
        ("keys.bin", keys, f"{T.KEYS} x 16x16 4bpp"),
        ("cursors.bin", cursors, "3 x 28x28 2bpp, palette b: USE, SEARCH, MOVE"),
        ("font.bin", font, "256 glyphs x 8 rows, row-major, 128-255 inverse"),
        ("intro.bin", intro, "320x200 4bpp, 2.1's title"),
        ("gameover.bin", gameover, "320x200 4bpp"),
        ("amiga_tables.s", asm.encode(), "ca65 RODATA: " + ", ".join(exports)),
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    for name, blob, what in outputs:
        (args.out / name).write_bytes(blob)
        print(f"{args.out / name}: {len(blob)} bytes, {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
