#!/usr/bin/env python3
"""TILESET.GFX -> the tile behaviour tables, 512 bytes.

The file is a CBM PRG: a 2-byte load address ($4900, though the loader forces
$8000 with SETLFS SA=0) then 5119 bytes laid out as twenty 256-byte arrays --
except the last one is 255 bytes, one short:

    $000  DESTRUCT_PATH   tile -> the tile it becomes when destroyed
    $100  TILE_ATTRIB     b0 walkable   b1 hoverable  b2 pushable  b3 destructible
                          b4 see-through b5 valid destination b6 searchable
    $200  TILE_DATA_TL..BR   9 x 256 character codes, a 3x3 block per tile
    $B00  TILE_COLOR_TL..BR  9 x 256 colour nibbles

Only the first two tables survive. The tiles are drawn from the Amiga art now
(conv_amiga.py), so the PETSCII character cells and their colours are dropped
and the output is DESTRUCT_PATH followed by TILE_ATTRIB, which is what the game
logic reads. The whole file is still checked, so a different TILESET.GFX cannot
slip through just because most of it is discarded.
"""
import argparse
import pathlib
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    raw = args.src.read_bytes()
    if len(raw) != 5121:
        sys.exit(f"{args.src}: expected 5121 bytes, got {len(raw)}")
    load = raw[0] | (raw[1] << 8)
    body = raw[2:] + b"\x00"          # pad the one missing TILE_COLOR_BR byte
    assert len(body) == 5120

    destruct, attrib = body[0:256], body[256:512]
    blob = destruct + attrib
    assert len(blob) == 512

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_bytes(blob)
    print(f"{args.dst}: {len(blob)} bytes "
          f"(destruct 256 + attrib 256), PRG load was ${load:04X}")

    if args.report:
        print(f"  distinct TILE_ATTRIB values: {len(set(attrib))}")
        print(f"  destructible tiles (b3): {sum(1 for a in attrib if a & 0x08)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
