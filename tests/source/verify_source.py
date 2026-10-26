#!/usr/bin/env python3
"""Checks on the source that no emulator test can make: things the game would
only show if the code changed in a way it has not yet.

Run directly, or via ctest as `source.checks`.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def check_zeropage_is_partitioned() -> int:
    """The linker must keep reserving the game's zero page.

    The ported assembly names the addresses David Murray gave it -- $02-$05 for
    its two pointers, $23-$3B for the rest -- so those addresses have to belong
    to the game and not to cc65's runtime. src/rp6502.cfg does that with
    a separate memory area, and src/game/globals.s asserts at assembly time that
    each variable landed where the original put it.

    Both halves matter, and either can be deleted without anything obviously
    breaking until a routine starts reading the wrong byte, so check both are
    still there. The addresses themselves are checked by the build.
    """
    bad = []
    cfg = (ROOT / "src" / "rp6502.cfg").read_text()
    if "GAMEZP:" not in cfg or "GAMEZEROPAGE:" not in cfg:
        bad.append("  rp6502.cfg no longer reserves a zero page area "
                   "for the game")
    if not re.search(r'start\s*=\s*\$0002', cfg):
        bad.append("  the game's zero page area does not start at $02")

    globals_s = (ROOT / "src" / "game" / "globals.s").read_text()
    if '.segment "GAMEZEROPAGE"' not in globals_s:
        bad.append("  globals.s does not put the game's variables in GAMEZEROPAGE")
    asserts = len(re.findall(r'^\s*\.assert\s+\w+\s*=\s*\$[0-9A-Fa-f]{2},', 
                             globals_s, re.M))
    if asserts < 8:
        bad.append(f"  globals.s pins only {asserts} zero page addresses; "
                   "the layout is load-bearing")

    if bad:
        print("zero page is no longer partitioned:")
        print("\n".join(bad))
        return 1
    print(f"  zero page          partitioned, {asserts} addresses pinned")
    return 0


def check_search_object_returns() -> int:
    """SEARCH_OBJECT must return after each thing it gives.

    The original falls from a pistol, a plasma gun and a medkit into the next
    item's CMP with whatever A the display routine left; src/game/items.s
    returns instead. Nothing a test can make the game do shows the difference
    while that A never matches, so the instruction before SOBJ21, SOBJ22 and
    SOBJ23 is checked here: it must be RTS or JMP.
    """
    lines = (ROOT / "src" / "game" / "items.s").read_text().splitlines()
    bad = []
    for label in ("SOBJ21", "SOBJ22", "SOBJ23"):
        at = next(i for i, l in enumerate(lines) if l.startswith(label + ":"))
        last = next(l.split(";")[0].split() for l in reversed(lines[:at])
                    if l.split(";")[0].strip())
        if last[0].upper() not in ("RTS", "JMP"):
            bad.append(f"  {label} is reached by falling through: {' '.join(last)}")
    if bad:
        print("SEARCH_OBJECT falls through:")
        print("\n".join(bad))
        return 1
    print("  SEARCH_OBJECT      returns after each find")
    return 0


def main() -> int:
    failures = check_zeropage_is_partitioned()
    failures += check_search_object_returns()
    print("source checks:", "OK" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
