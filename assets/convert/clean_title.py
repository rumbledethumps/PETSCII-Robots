#!/usr/bin/env python3
"""The X16 version 2.1 title screen at 320x200, without the Commander X16 logo.

2.1's TITLE.BIN is the Amiga intro picture, with 2.1's own menu frame, made
320x240 by forty more lines of floor below it. On that floor sits a COMMANDER
X16 logo: the words, and a large X that reaches up into the Amiga's lines. The
RP6502 version shows 320x200, so the forty lines go, and with them the words.
Where the X still covers the floor, lines 174-199, the Amiga intro has the
floor as it was, so those pixels are put back from it. Every other pixel is
2.1's.

    clean_title.py TITLE.BIN ROBOTS.PRG introscreen.png out.png

The output is a 320x200 indexed PNG in 2.1's title palette. Standard library
only; png.py in this directory reads the Amiga picture.
"""
import argparse
import pathlib
import struct
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import png  # noqa: E402

W, H = 320, 200
PALETTE = 0x308E            # 2.1's title palette, in ROBOTS.PRG
LOGO = (88, 174, 160, 199)  # the part of the X above line 200: x0, y0, x1, y1


def load_title(path):
    d = pathlib.Path(path).read_bytes()
    if len(d) != W * 240 // 2:
        sys.exit(f"{path}: {len(d)} bytes, not a 320x240 4bpp picture")
    return [[(d[y * 160 + x // 2] >> 4) if x % 2 == 0 else d[y * 160 + x // 2] & 15
             for x in range(W)] for y in range(H)]


def load_palette(prg_path):
    prg = pathlib.Path(prg_path).read_bytes()
    o = PALETTE - 0x0801 + 2
    return [((prg[o + j + 1] & 15) * 17, (prg[o + j] >> 4) * 17, (prg[o + j] & 15) * 17)
            for j in range(0, 32, 2)]


def write_png(path, rows, palette):
    raw = b"".join(b"\x00" + bytes((r[x] << 4) | r[x + 1] for x in range(0, W, 2))
                   for r in rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    out = png.SIGNATURE
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 4, 3, 0, 0, 0))
    out += chunk(b"PLTE", b"".join(bytes(c) for c in palette))
    out += chunk(b"IDAT", zlib.compress(raw, 9))
    out += chunk(b"IEND", b"")
    pathlib.Path(path).write_bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("title")
    ap.add_argument("prg")
    ap.add_argument("amiga")
    ap.add_argument("out")
    a = ap.parse_args()

    img = load_title(a.title)
    pal = load_palette(a.prg)
    am = png.read(a.amiga)
    if (am.width, am.height) != (W, H):
        sys.exit(f"{a.amiga}: {am.width}x{am.height}, not the 320x200 Amiga intro")
    # The Amiga intro's colours, as 2.1's title palette numbers them. 2.1's
    # white is FFF where the Amiga's is EEE.
    rgb21 = [(r >> 4, g >> 4, b >> 4) for r, g, b in pal]
    to21 = {}
    for i, (r, g, b) in enumerate(am.palette[:16]):
        c = (r >> 4, g >> 4, b >> 4)
        to21[i] = rgb21.index((15, 15, 15) if c == (14, 14, 14) else c)

    x0, y0, x1, y1 = LOGO
    changed = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            v = to21[am.rows[y][x]]
            if img[y][x] != v:
                img[y][x] = v
                changed += 1
    write_png(a.out, img, pal)
    print(f"{a.out}: {changed} pixels of the logo put back from the Amiga intro")


if __name__ == "__main__":
    main()
