#!/usr/bin/env python3
"""The MS-DOS version's AdLib sound -> OPL2 register streams for the RP6502.

An .ADL file is a set of streams for the SSY player in the DOS version's
audio.c (zeropolis79/PETSCIIRobots-MSDOS): bytes 0-1 are 3 and a count, then a
little-endian offset for each stream. A stream is a compressed list of changes
to a voice -- its ten instrument registers, its volume, its pitch, key off --
with waits between them, back references to repeat earlier parts, and a loop
point. The player decodes every stream once a tick, 72 ticks a second, and
writes the OPL2 registers that changed.

The RP6502 does not decode any of that. This runs the same player here, tick by
tick, and keeps only what it writes to the chip: a flat list of register writes
and waits in VGM's command encoding --

    5A rr dd    write dd to OPL2 register rr
    61 nn nn    wait nnnn samples of 44.1 kHz
    66          end

A tick is 612.5 samples, so the waits alternate 612 and 613 from the start of
the stream, and the player in src/sound.s, counting the same way, lands every
write on the tick the DOS player made it.

    conv_adl.py sfx SOUNDFX.ADL sfx.s

writes the effects as a ca65 source for RAM: one stream each, and a table of
where each starts. Streams play on channel 0, which is the effects' in the DOS
version too.

    conv_adl.py song METAHEAD.ADL metahead.vgm [--once]

writes a song as a VGM file, which the RP6502 streams from the ROM; its
channels are 1-8. A song loops as the DOS player loops it, and with --once it
plays its first pass and ends, as 2.1 plays its win and lose jingles.
"""
import argparse
import pathlib
import sys

TICK_HZ = 72
SAMPLE_HZ = 44100

# SSY_OPL2_OPERATOR_ORDER and SSY_OPL2_INSTRUMENT_REGS, audio.c.
OPORD = (0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12)
INSTR = tuple((0xC0 + c, 0x20 + o, 0x40 + o, 0x60 + o, 0x80 + o, 0xE0 + o,
               0x63 + o, 0x83 + o, 0x23 + o, 0xE3 + o)
              for c, o in enumerate(OPORD))


class Channel:
    """One stream's state: the per-channel arrays of audio.c."""

    def __init__(self):
        self.wait = 0
        self.ptr = 0            # 0 = stopped
        self.ret = 0
        self.loop = 0
        self.refprev = 0
        self.pitch1 = 0
        self.pitch2 = 0
        self.volprev = 0
        self.keyoff = 0
        self.volopl = 0
        self.regs = [0] * 10
        self.prev = [0] * 10
        self.set = set()        # instrument registers the stream has written
        self.fe = []            # the ticks it took its loop start
        self.ff = []            # and its loop


class Ssy:
    """audio.c's ssy_timer_isr and ssy_adlib_update, over one .ADL file."""

    def __init__(self, data: bytes):
        if data[0] != 3:
            raise ValueError("not an SSY stream file: byte 0 is not 3")
        self.data = data
        self.ch = [Channel() for _ in range(9)]
        self.channels = 1       # SSY_CHANNELS: 1 is the effects alone
        self.t = 0              # ticks played

    def start(self, c: int, stream: int):
        self.ch[c].ptr = self.data[2 + stream * 2] | self.data[3 + stream * 2] << 8
        self.ch[c].loop = self.ch[c].ptr

    def music_play(self):
        """ssy_music_play: the song's streams on channels 1 up, every
        register of theirs taken for 0 and the volume for unknown."""
        self.channels = self.data[1] + 1
        for c in range(1, self.channels):
            self.start(c, c - 1)
            self.ch[c].volprev = 0xFF

    def sound_play(self, n: int):
        """ssy_sound_play: effect n on channel 0, from the state it leaves."""
        c = self.ch[0]
        c.wait = 0
        c.volopl = 0
        c.pitch2 = 0
        c.volprev = 255
        c.pitch1 = 65535
        c.keyoff = 255
        self.start(0, n)

    def _step(self, n: int):
        """Decode channel n up to its next wait; False when an effect ends."""
        d, c = self.data, self.ch[n]
        if c.wait:
            c.wait -= 1
            if c.wait:
                return True
        if not c.ptr:
            return True
        while True:
            b = d[c.ptr]
            c.ptr += 1
            if b < 0xC0:
                c.wait = b
                return True
            if b < 0xD0:                # PC speaker and Tandy volume
                continue
            if b in (0xD0, 0xD1, 0xD2):  # PC speaker pitch, PITCH_1
                if b == 0xD2:
                    c.pitch1 = d[c.ptr] | d[c.ptr + 1] << 8
                    c.ptr += 2
                elif b == 0xD0:
                    c.pitch1 = (c.pitch1 & 0xFF00) | d[c.ptr]
                    c.ptr += 1
                else:
                    c.pitch1 = (c.pitch1 & 0x00FF) | d[c.ptr] << 8
                    c.ptr += 1
                return True
            if b == 0xD3:               # short back reference
                off = d[c.ptr]
                c.ptr += 1
                c.ret = c.ptr
                c.ptr -= 2 + off
                c.refprev = c.ptr
                continue
            if b in (0xD4, 0xD5, 0xD6):  # OPL pitch, PITCH_2, and key on
                if b == 0xD6:
                    c.pitch2 = d[c.ptr] | d[c.ptr + 1] << 8
                    c.ptr += 2
                elif b == 0xD4:
                    c.pitch2 = (c.pitch2 & 0xFF00) | d[c.ptr]
                    c.ptr += 1
                else:
                    c.pitch2 = (c.pitch2 & 0x00FF) | d[c.ptr] << 8
                    c.ptr += 1
                c.pitch1 = ~c.pitch2 & 0xFFFF   # force the write
                return True
            if b == 0xD7:               # repeat the last reference
                c.ret = c.ptr
                c.ptr = c.refprev
                continue
            if b == 0xD8:               # Tandy noise mode
                c.ptr += 1
                continue
            if b < 0xE3:                # an instrument register
                c.regs[b - 0xD9] = d[c.ptr]
                c.set.add(b - 0xD9)
                c.ptr += 1
                continue
            if b == 0xE3:               # the carrier's level
                c.volopl = d[c.ptr]
                c.ptr += 1
                continue
            if b == 0xE4:               # key off
                c.keyoff = b
                continue
            if b == 0xFC:               # return; on channel 0 the end
                if n == 0:
                    c.ptr = 0
                    return False
                if c.ret:
                    c.ptr = c.ret
                    c.ret = 0
                continue
            if b == 0xFD:               # long reference, from the file start
                c.ret = c.ptr + 2
                c.ptr = d[c.ptr] | d[c.ptr + 1] << 8
                c.refprev = c.ptr
                continue
            if b == 0xFE:               # loop start
                c.loop = c.ptr
                c.fe.append(self.t)
                continue
            if b == 0xFF:               # take the loop
                c.ptr = c.loop
                c.ff.append(self.t)
                continue

    def _update(self, n: int, out: list):
        """ssy_adlib_update for channel n: the writes, in its order."""
        c = self.ch[n]
        if c.keyoff:
            c.keyoff = 0
            out.append((0xB0 + n, 0))
        if c.volopl != c.volprev:
            c.volprev = c.volopl
            out.append((0x43 + OPORD[n], c.volopl))
        for i in range(10):
            if c.regs[i] != c.prev[i]:
                c.prev[i] = c.regs[i]
                out.append((INSTR[n][i], c.regs[i]))
        if c.pitch2 != c.pitch1:
            c.pitch1 = c.pitch2
            out.append((0xA0 + n, c.pitch2 & 0xFF))
            out.append((0xB0 + n, c.pitch2 >> 8))

    def tick(self, update=range(9)):
        """One tick: decode, then write. Returns (writes, effect playing)."""
        playing = True
        for n in range(self.channels):
            if not self._step(n) and n == 0:
                playing = False
        out = []
        for n in update:
            self._update(n, out)
        self.t += 1
        return out, playing


def wait_samples(tick: int) -> int:
    """The samples between tick and tick + 1, counted from the stream's start:
    612 and 613 in turn, which is 612.5 on average and exact every two."""
    return ((tick + 1) * SAMPLE_HZ // TICK_HZ) - (tick * SAMPLE_HZ // TICK_HZ)


def encode(ticks) -> bytes:
    """Ticks of writes -> the VGM commands: a wait after each tick but the
    last, the waits of ticks without writes run together, and the end on the
    last tick, where the DOS player stops, even when it writes nothing."""
    out = bytearray()
    pending = 0
    for t, writes in enumerate(ticks):
        last = t + 1 == len(ticks)
        while pending and (writes or last):
            n = min(pending, 0xFFFF)
            out += bytes((0x61, n & 0xFF, n >> 8))
            pending -= n
        for reg, val in writes:
            out += bytes((0x5A, reg, val))
        if not last:
            pending += wait_samples(t)
    out.append(0x66)
    return bytes(out)


def effect_ticks(adl: bytes, n: int):
    """Effect n as the DOS player sounds it on channel 0: the writes of each
    tick, from ssy_sound_play to the end of its stream.

    ssy_sound_play leaves the instrument registers as the last effect left
    them, so the DOS player writes only the ones this effect changes. Every
    effect sets all ten before its first update, which this checks, so the
    stream writes all ten at its start and needs no history: what the chip
    holds afterwards is what DOS leaves there, whatever played before."""
    ssy = Ssy(adl)
    c = ssy.ch[0]
    c.prev = [None] * 10        # whatever was there; write them all
    ssy.sound_play(n)
    ticks = []
    while True:
        writes, playing = ssy.tick(update=(0,))
        if not ticks and len(c.set) != 10:
            raise ValueError(f"effect {n} leaves instrument registers "
                             f"{sorted(set(range(10)) - c.set)} to the last effect")
        ticks.append(writes)
        if not playing:
            return ticks
        if len(ticks) > 10 * TICK_HZ:
            raise ValueError(f"effect {n} never ends")


# What ssy_music_stop leaves on channels 1-8, which the RP6502 writes before a
# song starts: the carrier silent and the ten instrument registers 0. It does
# not touch the frequencies, so those are not known.
def stopped():
    chip = {}
    for c in range(1, 9):
        chip[0x43 + OPORD[c]] = 0xFF
        for r in INSTR[c]:
            chip[r] = 0
    return chip


def song_ticks(adl: bytes, once: bool):
    """The song as the DOS player writes it, a list of writes a tick, and the
    tick its loop goes back to, None with once.

    A VGM loop replays the same writes every time, where the DOS player writes
    only what changed, so a pass can sound different from the one before: the
    intro leaves an instrument the loop never sets, say. So this plays the song
    three times through, and loops the first pass that is the same as the next
    one, tick for tick, in what the chip holds. Its start then writes back
    whatever the end of the pass changed, which is nothing the first time
    round. METAHEAD never repeats -- its voices loop a tick apart, so they
    drift a tick further apart every pass -- and loops its first pass, without
    the drift."""
    ssy = Ssy(adl)
    ssy.music_play()
    chans = range(1, ssy.channels)
    need = 1 if once else 3
    chip, ticks, states = stopped(), [], []
    while any(len(ssy.ch[c].ff) < need for c in chans):
        writes, _ = ssy.tick(update=range(1, 9))
        for reg, val in writes:
            chip[reg] = val
        ticks.append(writes)
        states.append(dict(chip))
        if len(ticks) > 30 * 60 * TICK_HZ:
            raise ValueError("the song never loops")
    starts = {ssy.ch[c].fe[0] if ssy.ch[c].fe else 0 for c in chans}
    ends = [{ssy.ch[c].ff[k] for c in chans} for k in range(need)]
    if len(starts) != 1 or len(ends[0]) != 1:
        raise ValueError("the voices do not start their loops together")
    first, end1 = min(starts), min(ends[0])
    if once:
        return ticks[:end1], None

    def same(a, b, n):
        return all(states[a + k] == states[b + k] for k in range(n))

    period = end1 - first
    end2 = min(ends[1])
    if same(first, end1, period):
        start, end = first, end1
    elif (len(ends[1]) == 1 and len(ends[2]) == 1
          and end2 - end1 == period and min(ends[2]) - end2 == period
          and same(end1, end2, period)):
        start, end = end1, end2
    else:
        start, end = first, end1
    before = states[start - 1] if start else stopped()
    fix = [(r, v) for r, v in sorted(before.items()) if states[end - 1].get(r) != v]
    out = ticks[:end]
    out[start] = fix + out[start]

    # Played back from stopped, looping, the chip must hold what DOS has it
    # hold, tick for tick, wherever DOS repeats: all three passes, or for
    # METAHEAD the first.
    check = len(states) if (start, end) != (first, end1) or same(first, end1, period) else end
    chip = stopped()
    for t in range(check):
        for reg, val in out[t if t < end else start + (t - start) % (end - start)]:
            chip[reg] = val
        if any(chip.get(r) != v for r, v in states[t].items() if r in chip):
            raise ValueError(f"the loop plays back wrong at tick {t}")
    return out, start


def vgm(ticks, loop) -> bytes:
    """A VGM 1.51 file for the OPL2: the ticks as commands, the waits of ticks
    that write nothing run together, the last tick's wait too, so a loop back
    keeps time; the end; and the loop, if any, from the first command of tick
    <loop>."""
    data = bytearray()
    loop_at = loop_samples = None
    samples = pending = 0

    def flush():
        nonlocal pending
        while pending:
            n = min(pending, 0xFFFF)
            data.extend((0x61, n & 0xFF, n >> 8))
            pending -= n

    for t, writes in enumerate(ticks):
        if t == loop:
            flush()
            loop_at, loop_samples = len(data), samples
        if writes:
            flush()
            for reg, val in writes:
                data.extend((0x5A, reg, val))
        n = wait_samples(t)
        pending += n
        samples += n
    flush()
    data.append(0x66)
    head = bytearray(0x80)
    head[0:4] = b"Vgm "
    head[0x08:0x0C] = (0x151).to_bytes(4, "little")
    head[0x18:0x1C] = samples.to_bytes(4, "little")
    if loop is not None:
        head[0x1C:0x20] = (0x80 + loop_at - 0x1C).to_bytes(4, "little")
        head[0x20:0x24] = (samples - loop_samples).to_bytes(4, "little")
    head[0x34:0x38] = (0x80 - 0x34).to_bytes(4, "little")
    head[0x50:0x54] = (3579545).to_bytes(4, "little")      # YM3812
    out = head + data
    out[0x04:0x08] = (len(out) - 4).to_bytes(4, "little")
    return bytes(out)


def sfx_source(adl: bytes, name: str) -> str:
    count = adl[1]
    streams = [encode(effect_ticks(adl, n)) for n in range(count)]
    lines = [f"; Generated by assets/convert/conv_adl.py from {name}.",
             ";",
             "; The DOS version's sound effects as OPL2 register streams for",
             "; channel 0, in its numbering. See src/sound.s.",
             "",
             "        .export SFX_COUNT, SFX_START_L, SFX_START_H",
             "",
             f"SFX_COUNT = {count}",
             "",
             '        .segment "RODATA"',
             ""]
    for n, s in enumerate(streams):
        lines.append(f"SFX_{n}:")
        for i in range(0, len(s), 16):
            lines.append("        .byte " + ",".join(f"${b:02X}" for b in s[i:i + 16]))
    lines.append("")
    lines.append("SFX_START_L:")
    lines.append("        .lobytes " + ", ".join(f"SFX_{n}" for n in range(count)))
    lines.append("SFX_START_H:")
    lines.append("        .hibytes " + ", ".join(f"SFX_{n}" for n in range(count)))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=("sfx", "song"))
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument("--once", action="store_true",
                    help="a song's first pass, without its loop")
    args = ap.parse_args()
    adl = args.src.read_bytes()
    try:
        if args.kind == "sfx":
            args.dst.write_text(sfx_source(adl, args.src.name))
        else:
            args.dst.write_bytes(vgm(*song_ticks(adl, args.once)))
    except ValueError as e:
        sys.exit(f"{args.src}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
