#!/usr/bin/env python3
"""Drive the game to a map square, and print the emulator script that gets there.

tests/emu scripts are open loop: they press keys and check results, with no way
to ask where the player ended up and decide what to press next. That is fine for
a few steps, but a fixed list of moves cannot cross a level -- a door costs a
press to open before it costs one to walk through, and a robot standing in the
way costs an unknown number -- so the sequence desynchronises and every move
after that is wrong.

This closes the loop. rp6502.Emu drives the emulator a command at a time: read
the player's position out of the probe block, plan a route from *there* with a
breadth first search over the level's walkability, press one key, and look
again. What it prints is the script that worked, which can then be replayed
open loop -- the RNG starts from zero at power-on and is never reseeded, as in
2.1, and the emulator runs exactly the frames it is told to, so a recorded
route stays valid until the game's timing changes.

ONE LIMIT WORTH KNOWING. The probe block is refreshed from the main loop, and
plat_game_over does not return to it until the player has pressed a key at each
of its screens. A route that kills the player therefore keeps reading "alive"
and keeps walking, and its keypresses are what dismiss the game-over box and
the statistics -- so a recording made that way cannot be used to test those
screens. tests/emu/gameover.txt writes the player's unit type instead.

Walkability comes from TILE_ATTRIB, bit 0, which is the same bit REQUEST_WALK
tests through MOVE_TYPE. It, the map and the door units are read out of the
game's RAM once the level is up, so the planner sees exactly what the game
does, whatever the converters made of the files. An unlocked door square counts as passable because the
door AI opens it when the player comes near; the frames that takes are what the
loop absorbs. A locked one does not, because this drives the game from a cold
start with no keys -- UNIT_C on a door unit is 0 for unlocked and 1, 2 or 3 for
the spade, heart and star keys.

The map is not the whole story, though. A door is shut in the map until the
player walks into it, and then it is a six state machine that takes a while to
open, so the first press buys nothing and the square stays impassable for some
frames. CHECK_FOR_UNIT also stops the player entering a square another unit is
standing in, and units move. So when the player stops making progress the loop
first waits, in case something is opening, and only after that gives up on the
square, marks it blocked and plans a route that avoids it.

    tests/emu/playthrough.py e 75 42 > tests/emu/route.txt

It is not a test itself: it makes the routes that tests/emu/flash.txt and
endgame.txt replay. It runs the emulator that the build linked beside the
ROM, or $RP6502_EMU.
"""
import argparse
import os
import pathlib
import re
import sys
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import rp6502  # noqa: E402

KEYS = ((-1, 0, 'j'), (1, 0, 'l'), (0, -1, 'i'), (0, 1, 'k'))
DOOR = 10


def expand(line):
    """`$00 x27` in a --poke is 27 of them, so a long run fits on a line."""
    out = []
    for word in line.split():
        m = re.fullmatch(r'x(\d+)', word)
        out += [out[-1]] * (int(m.group(1)) - 1) if m and out else [word]
    return ' '.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('level')
    ap.add_argument('x', type=int)
    ap.add_argument('y', type=int)
    ap.add_argument('--rom', default='build/cc65/release/src/robots/robots.rp6502')
    ap.add_argument('--emu', default=None,
                    help='default: $RP6502_EMU, else rp6502-emu beside the ROM')
    ap.add_argument('--keys', action='store_true',
                    help='route through locked doors too, for a run that pokes '
                         'KEYS to say the player found them')
    ap.add_argument('--poke', action='append', default=[],
                    help='"[xram:|ram:]<addr> <byte>..." written once the level '
                         'is up, repeatable; "$00 x27" repeats a byte. Some '
                         'states no sequence of keys '
                         'reaches -- the endgame wants every robot dead -- and '
                         'writing them is how a route gets to the part under '
                         'test.')
    ap.add_argument('--max-steps', type=int, default=600)
    a = ap.parse_args()

    rom = str(ROOT / a.rom)
    emu_path = a.emu or os.environ.get('RP6502_EMU') or \
        str(pathlib.Path(rom).parent / 'rp6502-emu')
    os.environ['RP6502_EMU'] = emu_path
    sys.argv = sys.argv[:1]     # Emu adds sys.argv[1:] to the emulator's own
    emu = rp6502.Emu('--mute', rom)
    script = []

    def send(*lines):
        for line in lines:
            emu.cmd(line)
            script.append(line)

    def dump(addr, n):
        return bytes.fromhex(emu.cmd(f'dump {addr} {n}'))

    # The intro menu: down to CHANGE MAP, space once per level, back up, start.
    send('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU', 'run 30')
    send('press k', 'run 6', 'release k', 'run 10')
    for _ in range(ord(a.level) - ord('a')):
        send('press space', 'run 6', 'release space', 'run 10')
    send('press i', 'run 6', 'release i', 'run 10')
    send('press space', 'run 6', 'release space')
    send('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_PLAY', 'run 20')

    att = dump('TILE_ATTRIB', 256)
    MAP = dump('MAP', 128 * 64)
    T, X, Y, C = (dump(name, 64) for name in
                  ('UNIT_TYPE', 'UNIT_LOC_X', 'UNIT_LOC_Y', 'UNIT_C'))
    doors = {(X[i], Y[i]) for i in range(64)
             if T[i] == DOOR and (a.keys or C[i] == 0)}
    target = (a.x, a.y)

    def walkable(x, y):
        if not (0 <= x < 128 and 0 <= y < 64):
            return False
        if (x, y) in doors:
            return True
        return att[MAP[y * 128 + x]] & 1

    blocked = set()

    def route(src):
        seen = {src: None}
        q = deque([src])
        while q:
            c = q.popleft()
            if c == target:
                break
            for dx, dy, k in KEYS:
                n = (c[0] + dx, c[1] + dy)
                if n not in seen and n not in blocked and walkable(*n):
                    seen[n] = (c, k)
                    q.append(n)
        if target not in seen:
            return None
        out, c = [], target
        while seen[c]:
            c, k = seen[c]
            out.append(k)
        return out[::-1]

    for line in a.poke:
        send(f'poke {expand(line)}')
    if a.poke:
        send('run 60')          # let the AI notice the state it was handed

    pos, stuck, status = None, 0, 'ran out of steps'
    for _ in range(a.max_steps):
        try:
            v = dump('xram:XRAM_PROBE', 16)
        except rp6502.ScriptError as e:
            status = f'the emulator failed: {e}'
            break
        here = (v[4], v[5])
        if here == target:
            status = f'reached {target}'
            break
        if v[2] != 2:
            status = f'left play with state {v[2]} at {here}'
            break
        stuck = stuck + 1 if here == pos else 0
        pos = here
        plan = route(here)
        if not plan:
            status = f'no route from {here}'
            break
        if stuck and stuck % 4 == 0:
            # Give a door time to finish opening, or a unit time to wander off.
            send('run 60')
        if stuck > 16:
            # It is not going to open and it is not going to move. Take the
            # square out of the map and go round it.
            dx, dy = {'j': (-1, 0), 'l': (1, 0),
                      'i': (0, -1), 'k': (0, 1)}[plan[0]]
            blocked.add((here[0] + dx, here[1] + dy))
            stuck = 0
            continue
        send(f'press {plan[0]}', 'run 8', f'release {plan[0]}', 'run 8')

    try:
        emu.close()
    except rp6502.ScriptError:
        pass
    print('\n'.join(script))
    print(f'# {status}', file=sys.stderr)
    return 0 if status.startswith('reached') else 1


if __name__ == '__main__':
    sys.exit(main())
