"""The sound effects and the songs as src/sound.s plays them, for the tests
to hold the OPL2 to.

assets/convert/conv_adl.py runs the MS-DOS version's player over its .ADL
files; what it writes, tick by tick, is what the chip must get. src/sound.s
puts the effects volume onto the levels that are heard and keeps the key off
at volume 0, so the same is done here. A song is played from the state
music_stop leaves channels 1-8 in, and loops where the converter loops it.
"""
import functools
import sys

import petscii

sys.path.insert(0, str(petscii.ROOT / "assets" / "convert"))
import conv_adl                                     # noqa: E402

DOS = petscii.ROOT / "assets" / "src" / "dos"
ADL = (DOS / "SOUNDFX.ADL").read_bytes()
ATTEN = (63, 27, 24, 21, 18, 15, 12, 9, 6, 3, 0, -3, -6, -9, -12, -15)
# Channel 0's registers: connection, both operators' five, frequency, key.
CH0 = (0xC0, 0x20, 0x23, 0x40, 0x43, 0x60, 0x63, 0x80, 0x83, 0xE0, 0xE3,
       0xA0, 0xB0)


@functools.lru_cache(maxsize=None)
def ticks(n):
    """DOS effect n's writes, a list a tick."""
    return conv_adl.effect_ticks(ADL, n)


def heard(writes, volume):
    """Channel 0's registers after <writes>, as src/sound.s writes them."""
    regs, c0 = {}, 0
    for reg, val in writes:
        if reg == 0xC0:
            c0 = val
        if reg == 0x43 or (reg == 0x40 and c0 & 1):
            tl = max(0, min(63, (val & 0x3F) + ATTEN[volume]))
            val = (val & 0xC0) | tl
        elif reg == 0xB0 and volume == 0:
            val &= ~0x20
        regs[reg] = val
    return {k: v for k, v in regs.items() if k in CH0}


def chip(emu):
    """Channel 0's registers as the OPL2's page holds them."""
    page = petscii.xram(emu, "XRAM_OPL", 256)
    return {reg: page[reg] for reg in CH0}


def dos(emu, effect):
    """The DOS number of the game's effect <effect>."""
    return petscii.ram(emu, f"SFX_DOS+{effect}")[0]


def check(emu, n, volume):
    """None if the chip holds what DOS effect n has written by FX_AGE ticks at
    <volume>, or all of it once the effect is over; else what it holds. A
    frame can end inside the interrupt, so any part of the next tick's writes
    may be there too."""
    t = ticks(n)
    got = chip(emu)
    if not petscii.ram(emu, "FX_PTR+1")[0]:
        return None if got == heard(sum(t, []), volume) else got
    age = petscii.ram(emu, "FX_AGE")[0]
    done = sum(t[:age], [])
    nxt = t[age] if age < len(t) else []
    if any(got == heard(done + nxt[:j], volume) for j in range(len(nxt) + 1)):
        return None
    return got


def show(regs):
    return " ".join(f"{k:02X}={v:02X}" for k, v in regs.items())


# The songs in SONG_ order, src/sound.h, and whether each plays once.
SONGS = (("METAHEAD", False), ("WIN", True), ("LOSE", True), ("GETPSYCH", False),
         ("METALBOP", False), ("ROBOATTK", False), ("RUSHING", False))


@functools.lru_cache(maxsize=None)
def song_ticks(n):
    """Song n's writes, a list a tick, and the tick it loops back to."""
    name, once = SONGS[n]
    adl = (DOS / f"{name}.ADL").read_bytes()
    return conv_adl.song_ticks(adl, once)


def song_tick(n, t):
    ticks, loop = song_ticks(n)
    if t < len(ticks):
        return ticks[t]
    if loop is None:
        return []
    return ticks[loop + (t - loop) % (len(ticks) - loop)]


def song_check(emu, n):
    """None if channels 1-8 hold what song n has written by MUS_TICKS ticks,
    or some of the next tick's writes besides; else what they hold. Only the
    registers it has written or music_stop set are compared."""
    played = int.from_bytes(petscii.ram(emu, "MUS_TICKS", 2), "little")
    state = conv_adl.stopped()
    for t in range(played):
        for reg, val in song_tick(n, t):
            state[reg] = val
    page = petscii.xram(emu, "XRAM_OPL", 256)
    got = {reg: page[reg] for reg in state}
    nxt = song_tick(n, played)
    for j in range(len(nxt) + 1):
        want = dict(state)
        for reg, val in nxt[:j]:
            want[reg] = val
        if {reg: page[reg] for reg in want} == want:
            return None
    return {reg: v for reg, v in got.items() if v != state[reg]}

