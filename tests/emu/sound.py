"""The sound effects: the MS-DOS version's, on the OPL2, ticked by the VIA.

THE CLOCK. VIA timer 1, set from the PHI2 the RIA reports, makes 72 ticks a
second whatever the clock: at 8 MHz two interrupts a tick, at 3 MHz one. 600
frames are ten seconds, so 720 ticks.

THE STREAMS. assets/convert/conv_adl.py runs the DOS version's player over
SOUNDFX.ADL and writes what it sends the chip. Every effect is started here
the way PLAY_SOUND starts one and checked against those writes frame by frame:
FX_AGE is the ticks it has played, so the registers must be the first FX_AGE
ticks' writes -- and perhaps some of the next tick's, if the frame ended inside
the interrupt. At volumes other than 10 the levels that are heard move by
2.25 dB a step, and at 0 the key never goes on.

WHICH EFFECT PLAYS. The DOS rule: while an effect is protected, only one of
its priority or higher replaces it. The menu's beep has priority 1.

THE MUSIC. The DOS version's songs, streamed from the ROM 512 bytes at a time.
Channels 1-8 must hold what the converter wrote by MUS_TICKS ticks: the title
at the menu, there and past its loop at 97 seconds; level b's song, the second
of the four; and the lose jingle, which plays once and ends. The stream must
never have kept a song waiting.
"""
import sys

import rp6502

import petscii
import sfx

failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def r(emu, name, n=1):
    b = petscii.ram(emu, name, n)
    return int.from_bytes(b, "little")


def poke(emu, name, value, n=1):
    for i in range(n):
        emu.cmd(f"poke {name}+{i} {(value >> 8 * i) & 0xFF}")


def clock(phi2):
    """Ticks in 600 frames, and the timer as set up, at <phi2> kHz."""
    args = ("--phi2", str(phi2)) if phi2 != 8000 else ()
    with rp6502.Emu(*args) as emu:
        emu.cmd("wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU 1200")
        cycles = phi2 * 125 // 9
        sub = cycles // 65537 + 1
        latch = cycles // sub - 2
        if r(emu, "_snd_subticks") != sub:
            fail(f"{phi2} kHz: {r(emu, '_snd_subticks')} interrupts a tick, not {sub}")
        got = r(emu, "$FFD6", 2)
        if got != latch:
            fail(f"{phi2} kHz: timer 1 latches {got}, not {latch}")
        if r(emu, "$FFDB") & 0xC0 != 0x40 or r(emu, "$FFDE") != 0xC0:
            fail(f"{phi2} kHz: ACR {r(emu, '$FFDB'):02X} IER {r(emu, '$FFDE'):02X}, "
                 "not free-running with timer 1 alone on")
        t0 = r(emu, "SND_TICKS", 2)
        emu.cmd("run 600")
        ticks = (r(emu, "SND_TICKS", 2) - t0) & 0xFFFF
        if abs(ticks - 720) > 1:
            fail(f"{phi2} kHz: {ticks} ticks in 600 frames, not 720")


def effect(emu, n, volume):
    """Effect n, DOS numbering, started as PLAY_SOUND starts it, checked
    against the converter's writes every frame until it ends."""
    poke(emu, "_sfx_volume", volume)
    start = r(emu, f"SFX_START_L+{n}") | r(emu, f"SFX_START_H+{n}") << 8
    poke(emu, "FX_CREDIT", 0, 3)
    poke(emu, "FX_PARITY", 0)
    poke(emu, "FX_AGE", 0)
    poke(emu, "FX_PTR", start, 2)
    for frame in range(200):
        emu.cmd("run 1")
        bad = sfx.check(emu, n, volume)
        if bad:
            fail(f"effect {n} at volume {volume}, tick {r(emu, 'FX_AGE')}: "
                 f"{sfx.show(bad)}")
            return
        if not r(emu, "FX_PTR+1"):
            if r(emu, "FX_AGE") != len(sfx.ticks(n)) - 1:
                fail(f"effect {n} played {r(emu, 'FX_AGE') + 1} ticks, "
                     f"not {len(sfx.ticks(n))}")
            return
    fail(f"effect {n} never ended")


# The clock, at the 8 MHz every machine starts at and at 3 MHz.
clock(8000)
clock(3000)

with rp6502.Emu() as emu:
    petscii.menu(emu)
    emu.cmd("run 60")

    # Every effect at the DOS level. Effects 1 and 6 start with all their
    # waveform and operator registers $AA and $00; what matters is that the
    # chip gets what DOS sent it.
    for n in range(sfx.ADL[1]):
        effect(emu, n, 10)
    # BEEP2, 5, adds its operators, so both levels move with the volume.
    for volume in (0, 1, 15):
        effect(emu, 5, volume)
        effect(emu, 0, volume)
    poke(emu, "_sfx_volume", 10)

    # The menu's beep is priority 1. While an explosion's priority 13 is still
    # protected it is not heard; once the time is out it is.
    emu.cmd("poke SOUND_EFFECT $FF")
    emu.cmd("poke SND_PRIORITY 13")
    emu.cmd("poke SND_TIMER 200")
    menu = r(emu, "MENUY")
    petscii.tap(emu, "k")
    if r(emu, "MENUY") == menu:
        fail("the menu did not move")
    if r(emu, "SOUND_EFFECT") != 0xFF:
        fail(f"a beep replaced a protected explosion: {r(emu, 'SOUND_EFFECT')}")
    emu.cmd("poke SND_TIMER 0")
    emu.cmd("press i")
    emu.cmd("run 2")
    if r(emu, "SOUND_EFFECT") != 0:
        fail(f"after the protection the menu plays {r(emu, 'SOUND_EFFECT')}, not the beep, 0")
    if r(emu, "SND_PRIORITY") != 1:
        fail(f"the beep holds priority {r(emu, 'SND_PRIORITY')}, not 1")
    emu.cmd("release i")
    # Five ticks of protection, then none.
    emu.cmd("run 6")
    if r(emu, "SND_TIMER") or r(emu, "SND_PRIORITY"):
        fail(f"the beep is still protected: timer {r(emu, 'SND_TIMER')}, "
             f"priority {r(emu, 'SND_PRIORITY')}")


def song(emu, n, frames, what):
    """Song n plays, held to the converter every frame for <frames>."""
    if r(emu, "_music_song") != n:
        fail(f"{what}: song {r(emu, '_music_song')} plays, not {n}")
        return
    for _ in range(frames):
        emu.cmd("run 1")
        bad = sfx.song_check(emu, n)
        if bad:
            fail(f"{what}, tick {r(emu, 'MUS_TICKS', 2)}: {sfx.show(bad)}")
            return
    if r(emu, "_mus_underruns", 2):
        fail(f"{what}: the song waited {r(emu, '_mus_underruns', 2)} ticks for its stream")


with rp6502.Emu() as emu:
    emu.cmd("wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU")
    song(emu, 0, 120, "the title")
    # The title loops back to 22 seconds at tick 6,989, its end.
    while r(emu, "MUS_TICKS", 2) < 6989 - 100:
        emu.cmd("run 600")
    song(emu, 0, 240, "the title round its loop")

with rp6502.Emu() as emu:
    petscii.boot(emu, "b")
    song(emu, 4, 300, "level b, METALBOP")
    # Dead, then the box, a key, and the statistics with the lose jingle,
    # which plays once and ends.
    emu.cmd("poke UNIT_TYPE $00")
    emu.cmd("run 200")
    for _ in range(10):                 # until the box takes a key
        petscii.tap(emu, "space", hold=8, after=30)
        if r(emu, "_music_song") == 2:
            break
    song(emu, 2, 60, "the lose jingle")
    for _ in range(40):
        if not r(emu, "_mus_on"):
            break
        emu.cmd("run 30")
    if r(emu, "_mus_on"):
        fail("the lose jingle never ended")
    elif r(emu, "MUS_TICKS", 2) != len(sfx.song_ticks(2)[0]):
        fail(f"the lose jingle ended after {r(emu, 'MUS_TICKS', 2)} ticks, "
             f"not {len(sfx.song_ticks(2)[0])}")
    elif sfx.song_check(emu, 2):
        fail(f"the lose jingle ended with {sfx.show(sfx.song_check(emu, 2))}")

sys.exit(1 if failures else 0)
