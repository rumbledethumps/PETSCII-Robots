#!/usr/bin/env python3
"""X16 2.1's LEVEL-A .. LEVEL-R -> RP6502 level blobs, level-a .. level-r.

Each file in assets/src/x16/ is a CBM PRG, 8706 bytes:

    +0     2 bytes   load address: $7D00 in LEVEL-A, $5D00 in B to R
    +2     8 x 64    UNIT_TYPE, LOC_X, LOC_Y, A, B, C, D, HEALTH
    +514   8192      MAP, 128 wide x 64 tall, one byte per tile

2.1 ignores the load address, loading with SETLFS 2,8,0 to an address of its
own, so it is not checked; the two values are only told apart by --report.
Unlike the 2022 pre-release's files there is no 256-byte filler between the
unit arrays and the map. The result is the file without its first two bytes:
8704 bytes, 512 of unit arrays followed by the map, which is exactly the
layout the port declares, so loading a level is one read() into one struct.

Unit slots: 0 player, 1-27 robots, 28-31 weapons fire, 32-47 doors and other
unsprited units, 48-63 hidden findable objects.
"""
import argparse
import pathlib
import sys

UNITS, MAP = 512, 8192


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    raw = args.src.read_bytes()
    if len(raw) != 2 + UNITS + MAP:
        sys.exit(f"{args.src}: expected {2 + UNITS + MAP} bytes, got {len(raw)}")
    out = raw[2:]                       # 2.1 ignores the load address
    units, mapdata = out[:UNITS], out[UNITS:]

    types = units[0:64]
    if types[0] != 1:
        sys.exit(f"{args.src}: unit 0 is type {types[0]}, expected 1 (the player)")

    assert len(out) == UNITS + MAP == 8704
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_bytes(out)

    if args.report:
        load = raw[0] | (raw[1] << 8)
        x, y = units[64:128], units[128:192]
        robots = sum(1 for i in range(1, 28) if types[i])
        doors = sum(1 for i in range(32, 48) if types[i])
        hidden = sum(1 for i in range(48, 64) if types[i])
        fire = sum(1 for i in range(28, 32) if types[i])
        print(f"{args.dst.name}: header ${load:04X}  player ({x[0]},{y[0]})  "
              f"robots {robots:2}  doors {doors:2}  hidden {hidden:2}  "
              f"fire {fire}  tiles {len(set(mapdata)):3}")
    else:
        print(f"{args.dst}: {len(out)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
