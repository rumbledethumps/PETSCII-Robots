"""The keys and sounds X16 2.1 changed in play: the item cycle skips forward,
an effect replaces one of its own priority, SHIFT+M turns the music off and
on, and SHIFT+[ and SHIFT+] set the effects volume.

2.1's DISPLAY_ITEM ($5291) steps on from an item that has run out to the next
one in stock, past the magnet back to the first. So with a time bomb and a
medkit and no EMP, F2 from the bomb skips the EMP to the medkit, and using the
last EMP goes on to the medkit too. The port used to fall back to the first
item in stock, the bomb, so the medkit could never be chosen.

The effects are the MS-DOS version's, with its rule for which one plays: a
new effect replaces one still protected only if its priority is the same or
higher. F2's and F1's sounds are both priority 2, so F1's replaces F2's. The
port once had the PET's rule, the lower number wins, which in the X16's
numbering kept F1's sound from replacing F2's. tests/emu/sound.py has the
rest of the rule.

SHIFT+M is 2.1's music key, beside the Amiga's F6; it used to arrive as M, the
push key. SHIFT+[ and SHIFT+] step the effects volume, 0 to 15 from 10, print
2.1's "new fx volume:  0x" with the hex digit, and beep, or give the error
sound at either end. The volume moves the levels the OPL2 hears, 2.25 dB a
step from the DOS level at 10, and at 0 the key never goes on: tests/emu/sfx.py
holds the chip to that. A held SHIFT+M must not repeat as M, and a held volume
key repeats as itself, not as the bracket.
"""
import sys

import rp6502

import petscii
import sfx

MUSIC_OFF = bytes((13, 21, 19, 9, 3, 32, 15, 6, 6, 46))
# 2.1's MSG_VOLUME, $412D, up to the digit: "new fx volume:  0".
NEW_FX = bytes((14, 5, 23, 32, 6, 24, 32, 22, 15, 12, 21, 13, 5, 58, 32, 32, 48))
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def r(emu, name):
    return petscii.ram(emu, name)[0]


def shift_tap(emu, key, hold=6, after=10):
    """<key> with SHIFT, down for <hold> frames, about as long as a tap. A
    volume key sets KEYTIMER 20, so a tap is one step whenever it lands."""
    emu.cmd("press lshift")
    emu.cmd(f"press {key}")
    emu.cmd(f"run {hold}")
    emu.cmd(f"release {key}")
    emu.cmd("release lshift")
    emu.cmd(f"run {after}")


def quiet(emu, where):
    """Run until no effect is playing."""
    for _ in range(120):
        if r(emu, "SOUND_EFFECT") == 0xFF:
            return
        emu.cmd("run 1")
    fail(f"{where}: the effect never ended")


def console(emu, n):
    """The first <n> glyphs of the console's bottom row."""
    return petscii.xram(emu, "XRAM_CHARS+24*SCR_STRIDE", 2 * n)[::2]


def playing_at(emu, volume, what):
    """The effect playing is on the chip as DOS wrote it, at <volume>."""
    effect = r(emu, "SOUND_EFFECT")
    if effect == 0xFF:
        fail(f"{what}: no effect is playing")
        return
    bad = sfx.check(emu, sfx.dos(emu, effect), volume)
    if bad:
        fail(f"{what}: the chip holds {sfx.show(bad)}")


with rp6502.Emu() as emu:
    petscii.boot(emu, "a")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_AI60')

    # The item cycle. A bomb and a medkit, no EMP: F2 from the bomb goes to
    # the medkit, and F2 again past the magnet, which there is none of, back
    # to the bomb.
    emu.cmd("poke INV_BOMBS 1")
    emu.cmd("poke INV_EMP 0")
    emu.cmd("poke INV_MEDKIT 1")
    emu.cmd("poke INV_MAGNET 0")
    emu.cmd("poke SELECTED_ITEM 1")
    petscii.tap(emu, "f2", hold=4, after=30)
    if r(emu, "SELECTED_ITEM") != 3:
        fail(f"F2 from the bomb chose item {r(emu, 'SELECTED_ITEM')}, not the medkit, 3")
    petscii.tap(emu, "f2", hold=4, after=30)
    if r(emu, "SELECTED_ITEM") != 1:
        fail(f"F2 from the medkit chose item {r(emu, 'SELECTED_ITEM')}, not the bomb, 1")
    # The last EMP used goes on to the medkit, not back to the bomb.
    emu.cmd("poke INV_EMP 1")
    emu.cmd("poke SELECTED_ITEM 2")
    petscii.tap(emu, "space", hold=4, after=30)
    if r(emu, "INV_EMP") != 0:
        fail("space did not use the EMP")
    if r(emu, "SELECTED_ITEM") != 3:
        fail(f"after the last EMP the item is {r(emu, 'SELECTED_ITEM')}, not the medkit, 3")

    # Of one priority, the newer plays: F2's SFX_CYCLEITEM, 2, then F1's
    # SFX_CYCLEWEAPON, 3, while the first is still protected.
    quiet(emu, "the EMP")
    emu.cmd("press f2")
    emu.cmd("run 2")
    emu.cmd("release f2")
    if r(emu, "SOUND_EFFECT") != 2:
        fail(f"F2 plays effect {r(emu, 'SOUND_EFFECT')}, not 2")
    emu.cmd("press f1")
    emu.cmd("run 2")
    emu.cmd("release f1")
    emu.cmd("run 1")
    if r(emu, "SOUND_EFFECT") != 3:
        fail(f"F1 after F2 plays effect {r(emu, 'SOUND_EFFECT')}, not 3")

    # SHIFT+M turns the music off, as F6 does. It used to arrive as M, the
    # push key, which put up the hand and waited for a direction.
    quiet(emu, "F1")
    if not petscii.music_on(emu):
        fail("no music in play")
    shift_tap(emu, "m", hold=4, after=30)
    if r(emu, "CURSOR_ON") != 0:
        fail(f"SHIFT+M put up cursor {r(emu, 'CURSOR_ON')}: it was read as M")
        petscii.tap(emu, "l", hold=4, after=30)
    if petscii.music_on(emu):
        fail("SHIFT+M did not stop the music")
    if console(emu, 10) != MUSIC_OFF:
        fail(f"SHIFT+M printed {list(console(emu, 10))}, not music off.")

    # Held, it starts the music once. It does not repeat at all, as F6 does
    # not, and above all not as M.
    emu.cmd("press lshift")
    emu.cmd("press m")
    toggles, music = 0, 0
    for _ in range(60):
        emu.cmd("run 1")
        toggles += petscii.music_on(emu) != music
        music = petscii.music_on(emu)
        if r(emu, "CURSOR_ON"):
            break
    emu.cmd("release m")
    emu.cmd("release lshift")
    emu.cmd("run 10")
    if r(emu, "CURSOR_ON"):
        fail("a held SHIFT+M repeated as M")
        petscii.tap(emu, "l", hold=4, after=30)
    if toggles != 1 or music != 1:
        fail(f"a held SHIFT+M turned the music on and off {toggles} times")

    # SHIFT+] from 10 to 11: "new fx volume:  0b" on the console, and the beep
    # at the new level, a step louder.
    quiet(emu, "SHIFT+M")
    shift_tap(emu, "rightbracket", hold=2, after=1)     # the beep still sounding
    if r(emu, "sfx_volume") != 11:
        fail(f"SHIFT+] set the volume to {r(emu, 'sfx_volume')}, not 11")
    if console(emu, 18) != NEW_FX + bytes((2,)):
        fail(f"SHIFT+] printed {list(console(emu, 18))}, not new fx volume:  0b")
    if r(emu, "SOUND_EFFECT") != 0:
        fail(f"SHIFT+] played effect {r(emu, 'SOUND_EFFECT')}, not the beep, 0")
    playing_at(emu, 11, "the beep at volume 11")

    # SHIFT+[ twice, to 9.
    for _ in range(2):
        quiet(emu, "a volume key")
        shift_tap(emu, "leftbracket", after=3)
    if r(emu, "sfx_volume") != 9:
        fail(f"SHIFT+[ twice set the volume to {r(emu, 'sfx_volume')}, not 9")
    if console(emu, 18) != NEW_FX + b"9":
        fail(f"SHIFT+[ printed {list(console(emu, 18))}, not new fx volume:  09")
    playing_at(emu, 9, "the beep at volume 9")

    # Down to 0, where SHIFT+[ gives the error sound and leaves the digit, and
    # an effect plays without the key ever going on.
    for _ in range(9):
        shift_tap(emu, "leftbracket", after=10)
    if r(emu, "sfx_volume") != 0 or console(emu, 18) != NEW_FX + b"0":
        fail(f"nine more SHIFT+[ left volume {r(emu, 'sfx_volume')}, "
             f"printed {list(console(emu, 18))}")
    quiet(emu, "volume 0")
    shift_tap(emu, "leftbracket", after=3)
    if r(emu, "SOUND_EFFECT") != 6 or console(emu, 18) != NEW_FX + b"0":
        fail(f"SHIFT+[ at 0 played effect {r(emu, 'SOUND_EFFECT')}, not the error, "
             f"and printed {list(console(emu, 18))}")
    quiet(emu, "the error")
    emu.cmd("press f2")
    keys = []
    for _ in range(12):
        emu.cmd("run 1")
        keys.append(petscii.xram(emu, "XRAM_OPL+$B0")[0])
        if len(keys) == 3 and r(emu, "SOUND_EFFECT") != 2:
            fail(f"F2 at volume 0 plays effect {r(emu, 'SOUND_EFFECT')}, not 2")
    emu.cmd("release f2")
    if any(k & 0x20 for k in keys):
        fail(f"at volume 0 an effect keyed on: {[f'{k:02X}' for k in keys]}")

    # Held, SHIFT+] repeats as itself, as KEY_REPEAT repeats any key, and not
    # as ]: every 20 frames a step, up to 15, and then the error sound.
    quiet(emu, "F2")
    emu.cmd("press lshift")
    emu.cmd("press rightbracket")
    emu.cmd("run 330")
    emu.cmd("release rightbracket")
    emu.cmd("release lshift")
    emu.cmd("run 3")
    if r(emu, "sfx_volume") != 15 or console(emu, 18) != NEW_FX + bytes((6,)):
        fail(f"a held SHIFT+] reached volume {r(emu, 'sfx_volume')}, "
             f"printed {list(console(emu, 18))}, not 15 and 0f")
    playing_at(emu, 15, "an effect at volume 15")
    quiet(emu, "volume 15")
    shift_tap(emu, "rightbracket", after=3)
    if r(emu, "SOUND_EFFECT") != 6 or console(emu, 18) != NEW_FX + bytes((6,)):
        fail(f"SHIFT+] at 15 played effect {r(emu, 'SOUND_EFFECT')}, not the "
             f"error, and printed {list(console(emu, 18))}")

sys.exit(1 if failures else 0)
