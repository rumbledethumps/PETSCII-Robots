#!/usr/bin/env python3
"""Invariants the converted assets must satisfy before they reach the ROM.

These are the assumptions the platform layer is built on. Each one is cheap to
check and expensive to debug on hardware, because the failure modes are quiet:
a swapped nibble order mirrors every pair of pixels, a black outline left at
index 0 turns transparent, and a unit tile with no image in the bank simply
does not draw.

The images are checked against a fresh decode of the source PNGs, unpacked
here pixel by pixel rather than through the converter's packer, so a packing
bug cannot pass by agreeing with itself. What comes from X16 2.1 is checked
in colour against 2.1's own files through 2.1's own palettes, so a re-indexing
bug cannot either.

    verify_assets.py [gen-dir]      default $PETSCII_AGEN, else assets/gen
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "assets" / "convert"))
import png  # noqa: E402

GEN = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                   else os.environ.get("PETSCII_AGEN", ROOT / "assets" / "gen"))
SRC = ROOT / "assets" / "src"
AMIGA = SRC / "amiga"
X16 = SRC / "x16"
REC = 288                                   # one 24x24 4bpp record

SIZES = {
    "images.bin": 352 * REC, "anim.bin": 24 * REC, "units.bin": 38 * REC,
    "hud_tiles.bin": 72 * 32, "hud_map.bin": 40 * 25, "keys.bin": 3 * 128,
    "cursors.bin": 3 * 196, "font.bin": 2048, "intro.bin": 32000,
    "gameover.bin": 32000, "tiles.bin": 512,
}
# 2.1's sprites for the player's records; then, for each units.bin record,
# its source -- a 2.1 sprite, or "x" and a 2.1 tile -- and the palette it is
# drawn with, 0 fg, 1 a, 2 b.
PLAYER21 = [*range(48), 96, *range(88, 96)]
BANK21 = [52, 53, 48, 49, *range(60, 76), 98, 97, 99, 85, 103, 86, 50, 51,
          78, 79, 76, 77, "x246", 80, 81, 82, 83, 84]
BANK_PAL = [2] * 28 + [0] * 10
# The pixels 2.1's sprites lose cut from 32x32 to 24x24: outline ends.
CROP_LOSS = {71: 3, 75: 3, 77: 1, 96: 4, 98: 2}
# UNIT_TILE values the window draws as robots, shots and explosions: one of
# these with no bank image is a unit that vanishes.
UNIT_SET = set(range(96, 104)) | {111, 115} | set(range(130, 143)) \
    | set(range(160, 168)) | set(range(240, 253))
# UNIT_TILE values that draw nothing on purpose: 87 is X16 2.1's empty sprite,
# a shorting water droid's, whose sparks are the map square's own tiles.
NO_IMAGE = {87}

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


def unpack(blob, w, h, off=0, bpp=4):
    """bpp bits a pixel, rows of whole bytes, the leftmost pixel in a byte's
    high bits: at 4bpp, even x in the high nibble."""
    per, s = 8 // bpp, (w * bpp + 7) // 8
    return [[(blob[off + y * s + x // per] >> ((per - 1 - x % per) * bpp)) & ((1 << bpp) - 1)
             for x in range(w)] for y in range(h)]


def frame(img, h, i, w=None):
    return [r[:w or img.width] for r in img.rows[i * h:(i + 1) * h]]


def x16_pal(addr):
    """Sixteen of 2.1's palette entries at an address in ROBOTS.PRG, as $0RGB.
    The file loads at $0801, after its two-byte load address."""
    prg = (X16 / "ROBOTS.PRG").read_bytes()
    o = addr - 0x0801 + 2
    return [(prg[o + i + 1] & 15) << 8 | prg[o + i] for i in range(0, 32, 2)]


P1 = x16_pal(0x308E)                        # the title's palette
P2 = x16_pal(0x30AE)                        # the tiles'
P3 = x16_pal(0x30CE)                        # the sprites': 0 clear, 1 black
SPRITES21 = (X16 / "sprites.bin").read_bytes()
TILES21 = (X16 / "tiles.bin").read_bytes()


def sprite21(n, w=24, h=24):
    """2.1's sprite n in colour, None where it is clear, cut to w x h."""
    return [[None if v == 0 else P3[v] for v in r[:w]]
            for r in unpack(SPRITES21, 32, 32, n * 512)[:h]]


def tile21(t, clear0=False):
    """2.1's tile t in colour, 28 to an 8 KB bank; with clear0 its colour 0
    is None, as a unit drawn from it shows it."""
    return [[None if v == 0 and clear0 else P2[v] for v in r]
            for r in unpack(TILES21, 24, 24, t // 28 * 8192 + t % 28 * REC)]


def rgb4(pal):
    """A PNG's first 16 palette entries as $0RGB."""
    return [(r // 17) << 8 | (g // 17) << 4 | b // 17 for r, g, b in pal[:16]]


def parse_asm(text):
    """label -> list of .byte/.word values; plus the set of .export names."""
    tables, exports, cur = {}, set(), None
    for line in text.splitlines():
        line = line.split(";")[0].rstrip()
        m = re.match(r"^(\w+):", line)
        if m:
            cur = tables.setdefault(m.group(1), [])
            continue
        m = re.match(r"\s+\.export\s+(.*)", line)
        if m:
            exports |= {e.strip() for e in m.group(1).split(",")}
            continue
        m = re.match(r"\s+\.(?:byte|word)\s+(.*)", line)
        if m and cur is not None:
            cur += [int(v.strip().lstrip("$"), 16) for v in m.group(1).split(",")]
    return tables, exports


def unit_tile_stores():
    """Every UNIT_TILE value src/game can give a unit in slots 1-31.

    Levels do not carry UNIT_TILE (conv_level.py: eight 64-byte unit arrays,
    TYPE to HEALTH, then the map); it is working state the AI sets, so the code
    is the only source. Three shapes occur:

      LDA #n ... STA UNIT_TILE,X    possibly through a JMP to a shared STA
      CMP #v / Bxx / INC UNIT_TILE,X           the evilbot's v -> v+1
      INC UNIT_TILE,X / LDA UNIT_TILE,X / CMP #n   counts up from the nearest
                                               stored value below n, n excluded

    A plain STA UNIT_TILE is slot 0, the player, which has its own frames.
    """
    keep_a = {"STA", "STX", "STY", "LDX", "LDY", "INX", "INY", "DEX", "DEY",
              "CLC", "SEC", "NOP", "TAX", "TAY", "PHA"}
    found, player, ups, tops = {}, [], [], []

    def imm(op):
        op = op.strip()
        if not op.startswith("#"):
            return None
        v = op[1:]
        try:
            return int(v[1:], 16) if v.startswith("$") else \
                int(v[1:], 2) if v.startswith("%") else int(v)
        except ValueError:
            return None

    for path in sorted((ROOT / "src" / "game").glob("*.s")):
        code, labels = [], {}
        for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            line = line.split(";")[0]
            m = re.match(r"^\s*(?:([A-Za-z_@.]\w*):)?\s*([A-Za-z]{3})?\b\s*(.*)$", line)
            if not m:
                continue
            if m.group(1):
                labels[m.group(1).upper()] = len(code)
            if m.group(2):
                code.append((n, m.group(2).upper(), m.group(3).replace(" ", "").upper()))
        where = lambda i: f"{path.name}:{code[i][0]}"
        for i, (_, op, arg) in enumerate(code):
            if op == "LDA" and imm(arg) is not None:
                j, steps = i + 1, 0
                while j < len(code) and steps < 12:
                    _, op2, arg2 = code[j]
                    steps += 1
                    if op2 == "STA" and arg2 == "UNIT_TILE,X":
                        found.setdefault(imm(arg), []).append(where(i))
                        break
                    if op2 == "STA" and arg2 == "UNIT_TILE":
                        player.append((imm(arg), where(i)))
                        break
                    if op2 == "JMP" and arg2 in labels:
                        j = labels[arg2]
                        continue
                    if op2 not in keep_a:
                        break
                    j += 1
            elif op == "INC" and arg == "UNIT_TILE,X":
                for k in range(i - 1, max(i - 4, -1), -1):
                    v = imm(code[k][2]) if code[k][1] == "CMP" else None
                    if v is not None:
                        ups.append((v + 1, where(i)))
                        break
                if (i + 2 < len(code) and code[i + 1][1:] == ("LDA", "UNIT_TILE,X")
                        and code[i + 2][1] == "CMP" and imm(code[i + 2][2]) is not None):
                    tops.append((imm(code[i + 2][2]), where(i)))
    for v, w in ups:
        found.setdefault(v, []).append(w)
    for top, w in tops:
        below = [v for v in found if v < top]
        if below:
            for v in range(max(below) + 1, top):
                found.setdefault(v, []).append(w)
    return found, player


def main() -> int:
    print(f"assets in {GEN}")
    b = {}
    for name, size in SIZES.items():
        p = GEN / name
        b[name] = p.read_bytes() if p.is_file() else b""
        check(f"{name} is {size} bytes", len(b[name]) == size, len(b[name]))
    good = lambda *names: all(len(b[n]) == SIZES[n] for n in names)

    img = {n: png.read(AMIGA / f"{n}.png") for n in
           ("tiles", "animtiles", "items", "health", "keys", "gamescreen",
            "introscreen", "gameover")}

    # The palettes the sprites are drawn with, as src/palette.s builds them,
    # written out here rather than taken from the converter; None is clear.
    # b is 2.1's unit palette with its entries 2 and 5 swapped.
    game = rgb4(img["tiles"].palette)
    pal_fg = [None] + game[1:]
    pal_a = pal_fg[:8] + [game[0]] + pal_fg[9:]
    pal_b = [None, game[0], game[1], game[3], game[4], game[2]] + game[6:]
    colour = lambda blob, i, pal: [[pal[v] for v in r] for r in unpack(blob, 24, 24, i * REC)]
    used21 = set(PLAYER21) | {n for n in BANK21 if isinstance(n, int)}
    lost = {n: sum(1 for y, r in enumerate(unpack(SPRITES21, 32, 32, n * 512))
                   for x, v in enumerate(r) if v and (x >= 24 or y >= 24)) for n in used21}
    check("2.1's sprites cut to 24x24 lose only the ends of five outlines",
          {n: k for n, k in lost.items() if k} == CROP_LOSS,
          {n: k for n, k in lost.items() if k})

    # ---- images.bin -------------------------------------------------------
    if good("images.bin"):
        im = b["images.bin"]
        tiles = img["tiles"]
        check("images.bin 0-252 are tiles.png, but 155 and 246",
              all(unpack(im, 24, 24, t * REC) == frame(tiles, 24, t, 24)
                  for t in range(253) if t not in (155, 246)))
        check("images.bin 155 and 246 are 2.1's tiles.bin's, in colour",
              all(colour(im, t, game) == tile21(t) for t in (155, 246)))
        # One asymmetric pixel pair proves the nibble order on its own.
        t, y, x = next((t, y, x) for t in range(253) for y in range(24) for x in range(0, 24, 2)
                       if t not in (155, 246)
                       and tiles.rows[t * 24 + y][x] != tiles.rows[t * 24 + y][x + 1])
        byte = im[t * REC + y * 12 + x // 2]
        left = tiles.rows[t * 24 + y][x]
        check(f"high nibble is the left pixel (tile {t} row {y} x {x}: ${byte:02X}, left {left})",
              byte >> 4 == left)

        check("images.bin 253-309 are 2.1's player, sprites 0-47, 96 and 88-95, "
              "in colour through palette a",
              all(colour(im, 253 + i, pal_a) == sprite21(f) for i, f in enumerate(PLAYER21)))
        it, he = img["items"], img["health"]
        check("images.bin 310-321 are the 6 items, padded to 48x24",
              all(unpack(im, 48, 24, (310 + 2 * k) * REC) == frame(it, 21, k) + [[0] * 48] * 3
                  for k in range(6)))
        check("images.bin 322-351 are the 6 health frames, padded to 48x52 in 5 records",
              all(unpack(im, 48, 52, (322 + 5 * k) * REC) == frame(he, 51, k) + [[0] * 48]
                  and not any(im[(322 + 5 * k) * REC + 1248:(327 + 5 * k) * REC])
                  for k in range(6)))

    if good("anim.bin"):
        check("anim.bin is animtiles.png in file order",
              all(unpack(b["anim.bin"], 24, 24, f * REC) == frame(img["animtiles"], 24, f)
                  for f in range(24)))

    # ---- units.bin --------------------------------------------------------
    if good("units.bin"):
        un = b["units.bin"]
        want = [sprite21(n) if isinstance(n, int) else tile21(int(n[1:]), clear0=True)
                for n in BANK21]
        bad = [i for i, w in enumerate(want)
               if colour(un, i, (pal_fg, pal_a, pal_b)[BANK_PAL[i]]) != w]
        check("units.bin is 2.1's robots, wrecks, bomb, canister, magnet, shots and "
              "explosions, in colour through each one's palette",
              not bad, f"records {bad}")

    # ---- HUD --------------------------------------------------------------
    if good("hud_tiles.bin", "hud_map.bin"):
        ht, hm = b["hud_tiles.bin"], b["hud_map.bin"]
        scr = img["gamescreen"].rows
        check("hud tile 0 is blank", not any(ht[:32]))
        check("hud_map ids are all < 72", max(hm) < 72, max(hm))
        tiles = [unpack(ht, 8, 8, i * 32) for i in range(72)]
        check(f"hud_tiles + hud_map rebuild gamescreen.png exactly ({len(set(hm) | {0})} tiles)",
              all(tiles[hm[by * 40 + bx]][y][x] == scr[by * 8 + y][bx * 8 + x]
                  for by in range(25) for bx in range(40) for y in range(8) for x in range(8)))

    if good("keys.bin"):
        check("keys.bin is keys.png, 16x14 padded to 16x16",
              all(unpack(b["keys.bin"], 16, 16, k * 128) == frame(img["keys"], 14, k) + [[0] * 16] * 2
                  for k in range(3)))

    # 2.1's cursor icons, 100-102: 2bpp, so drawn with palette b's first four
    # entries, clear, black, white and 789; and whole at 28x28.
    if good("cursors.bin"):
        cur = b["cursors.bin"]
        check("cursors.bin is 2.1's sprites 100-102, 28x28 2bpp, in colour through palette b",
              all([[pal_b[v] for v in r] for r in unpack(cur, 28, 28, k * 196, 2)]
                  == sprite21(100 + k, 28, 28) for k in range(3)))
        check("2.1's sprites 100-102 have nothing beyond 28x28",
              not any(v for k in range(3)
                      for y, r in enumerate(unpack(SPRITES21, 32, 32, (100 + k) * 512))
                      for x, v in enumerate(r) if x >= 28 or y >= 28))

    # ---- font -------------------------------------------------------------
    if good("font.bin"):
        font = b["font.bin"]
        raw = (AMIGA / "C64Font.raw").read_bytes()
        glyph = lambda g: bytes(font[r * 256 + g] for r in range(8))
        check("font is row-major C64Font.raw (font[row*256+glyph])",
              all(glyph(g) == raw[g * 8:g * 8 + 8] for g in range(128)))
        check("glyph 32 is blank (screen-code space)", not any(glyph(32)))
        check("glyph 1 is 'A' (not blank)", any(glyph(1)))
        check("glyphs 128-255 are 0-127 inverted",
              all(glyph(128 + g) == bytes(~v & 0xFF for v in glyph(g)) for g in range(128)))

    if good("gameover.bin"):
        check("gameover.bin is gameover.png",
              unpack(b["gameover.bin"], 320, 200) == img["gameover"].rows)

    # ---- tiles.bin --------------------------------------------------------
    if good("tiles.bin"):
        gfx = (X16 / "TILESET.GFX").read_bytes()
        check("tiles.bin is TILESET.GFX's DESTRUCT_PATH + TILE_ATTRIB",
              b["tiles.bin"] == gfx[2:514])

    # ---- amiga_tables.s ---------------------------------------------------
    asm_path = GEN / "amiga_tables.s"
    check("amiga_tables.s exists", asm_path.is_file())
    if asm_path.is_file():
        text = asm_path.read_text()
        tab, exports = parse_asm(text)
        lens = {"_amiga_pal_game": 16, "_amiga_pal_intro": 16, "_amiga_pal_gameover": 16,
                "_amiga_pal_b_order": 15, "_amiga_faces": 240, "_amiga_livemap": 256, "_amiga_unit_bank": 256,
                "_amiga_bank_pal": 38, "_amiga_tile_anim": 256}
        check("amiga_tables.s is RODATA and exports every table",
              '.segment "RODATA"' in text and set(lens) <= exports, sorted(set(lens) - exports))
        short = {k: len(tab.get(k, [])) for k, n in lens.items() if len(tab.get(k, [])) != n}
        check("amiga_tables.s table sizes", not short, short)
        if not short:
            check("_amiga_pal_game is tiles.png's palette in RGB4",
                  tab["_amiga_pal_game"] == rgb4(img["tiles"].palette)
                  and all(c % 17 == 0 for p in img["tiles"].palette[:16] for c in p))
            check("_amiga_pal_gameover is gameover.png's palette",
                  tab["_amiga_pal_gameover"] == rgb4(img["gameover"].palette))

            # 2.1's title and eyes, in colour: what the intro palette makes of
            # the converter's indices against what 2.1's makes of its own.
            pal_intro, amiga = tab["_amiga_pal_intro"], rgb4(img["introscreen"].palette)
            check("_amiga_pal_intro is the Amiga intro's palette with EEE as 2.1's FFF",
                  pal_intro == [0xFFF if c == 0xEEE else c for c in amiga]
                  and sorted(pal_intro) == sorted(P1))
            if good("intro.bin"):
                got = [[pal_intro[v] for v in r] for r in unpack(b["intro.bin"], 320, 200)]
                title = (X16 / "title.bin").read_bytes()
                want = [[P1[v] for v in r] for r in unpack(title, 320, 200)]
                # The part of 2.1's Commander X16 logo above line 200 is gone,
                # the Amiga intro's floor in its place (clean_title.py).
                for y in range(174, 200):
                    for x in range(88, 161):
                        c = amiga[img["introscreen"].rows[y][x]]
                        want[y][x] = 0xFFF if c == 0xEEE else c
                check("intro.bin is 2.1's title.bin, lines 0-199, the logo's box the Amiga's",
                      got == want)
                box = {got[y][x] for y in range(75, 85) for x in range(234, 250)}
                check("the title's face box, 234-249 x 75-84, is only 000 and 034",
                      box <= {0x000, 0x034}, sorted(f"{c:03X}" for c in box))
            three = (X16 / "faces.bin").read_bytes()
            check("_amiga_faces is 2.1's faces.bin, three 16x10 eye strips",
                  [[pal_intro[v] for v in r] for r in unpack(bytes(tab["_amiga_faces"]), 16, 30)]
                  == [[P1[v] for v in r] for r in unpack(three, 16, 30)])
            check("_amiga_livemap entries are a palette index in both nibbles",
                  all(v >> 4 == v & 15 for v in tab["_amiga_livemap"]))
            check("_amiga_bank_pal is b for the robots, wrecks, bomb, canister and magnet, "
                  "else fg",
                  tab["_amiga_bank_pal"] == BANK_PAL)
            order = tab["_amiga_pal_b_order"]
            p3 = P3[:2] + [P3[5], P3[3], P3[4], P3[2]] + P3[6:]
            check("_amiga_pal_b_order is 0,1,3,4,2,6-15: 2.1's unit palette, 2 and 5 swapped",
                  order == [0, 1, 3, 4, 2, *range(6, 16)]
                  and [game[g] for g in order] == p3[1:] == pal_b[1:])
            ta = [(t, v) for t, v in enumerate(tab["_amiga_tile_anim"]) if v != 0xFF]
            check("_amiga_tile_anim frames stay inside anim.bin",
                  all((v & 0x1F) + (4 if v & 0x80 else 2) <= 24 for _, v in ta), ta)
            check("_amiga_tile_anim marks 2.1's group B, the compactor and the fans ($5707)",
                  [t for t, v in ta if v & 0x40] == [148, 196, 197, 200, 201]
                  and not any(v & 0x20 for _, v in ta), ta)

            bank = tab["_amiga_unit_bank"]
            check("_amiga_unit_bank points inside units.bin",
                  all(v < 38 for v in bank if v != 0xFF))
            found, player = unit_tile_stores()
            check("found UNIT_TILE stores in src/game", bool(found))
            print(f"  note  UNIT_TILE values src/game can set: {sorted(found)}")
            for v, w in player:
                print(f"  note  slot 0 (player) set to {v} at {w}: drawn from the player frames")
            missing = sorted(v for v in found if bank[v] == 0xFF)
            hard = [v for v in missing if v in UNIT_SET]
            for v in missing:
                if v not in UNIT_SET | NO_IMAGE:
                    print(f"  warn  UNIT_TILE {v} has no bank image ({', '.join(found[v])})")
            check("the UNIT_TILE values that draw nothing have no bank image, and are set",
                  all(bank[v] == 0xFF and v in found for v in NO_IMAGE),
                  [(v, bank[v], found.get(v)) for v in sorted(NO_IMAGE)])
            check("every robot / shot / explosion UNIT_TILE has a bank image", not hard,
                  "; ".join(f"{v} ({', '.join(found[v])})" for v in hard))

    # ---- levels -----------------------------------------------------------
    levels = sorted(GEN.glob("level-*.bin"))
    check("18 levels converted", len(levels) == 18, len(levels))
    used = set()
    for p in levels:
        lv = p.read_bytes()
        if len(lv) != 8704:
            check(f"{p.name} is 8704 bytes", False, len(lv))
            continue
        # X16 2.1's LEVEL-A .. LEVEL-R, without the load address.
        x16 = X16 / f"LEVEL-{p.stem[-1].upper()}"
        if lv != x16.read_bytes()[2:]:
            check(f"{p.name} is {x16.name} without its first two bytes", False, "")
        types, x, y = lv[0:64], lv[64:128], lv[128:192]
        if types[0] != 1:
            check(f"{p.name} unit 0 is the player", False, types[0])
        # robots must sit inside the REQUEST_WALK_* bounds; hidden objects never
        # move, so they are exempt (level-l has a key at y=2).
        bad = [i for i in range(1, 28) if types[i] and not (5 <= x[i] <= 122 and 3 <= y[i] <= 60)]
        if bad:
            check(f"{p.name} robots within walk bounds", False, f"slots {bad}")
        if any(types[i] for i in range(28, 32)):
            check(f"{p.name} weapons band empty at load", False, "")
        used |= set(lv[512:])
    check("all levels parse and their robots are in bounds", True)
    check("every map tile the levels use has an image (< 253)",
          not used or max(used) < 253, sorted(t for t in used if t >= 253))

    print("assets:", "OK" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
