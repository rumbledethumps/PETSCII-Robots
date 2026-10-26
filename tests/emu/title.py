"""X16 2.1's title: its picture, the menu's text over it, the robot's eyes, the
selected option's flash and the credits.

The picture is 2.1's title as assets/convert/clean_title.py and conv_amiga.py
leave it, with the intro robot's eyes for the difficulty drawn into it at
234,75, where 2.1 draws them; everything expected comes from assets/gen. The
text plane sits eight lines below the grid, so the menu's rows 1-4 and the map
name's row 7 fall on 2.1's rows 2-5 and 8, inside the picture's empty boxes.
Cycling the difficulty changes the eyes and nothing else in the picture.

The flash and the credits are checked against 2.1's own ROBOTS.PRG, frame by
frame. The selected option's cells stay ink 14, and the flash is that entry
of pic_text: the interrupt steps SPRITECOLSTATE every seven frames, and the
menu gives the entry SPRITECOLCHART's colour for the step, in 2.1's text
palette, so the entry shows each step a frame after the interrupt takes it.
The credits are 2.1's first three pages, in rows 14-17, faded on entry 13 in
2.1's colours. A model of its TITLE_CREDITS_TICK, a pass of the menu at a
time from power-on, says what the box shows and what entry 13 is after each
pass; both must follow it at every frame, the palette never more than a frame
behind the cells, through the first page, which waits 256 ticks to fade in,
the second and third, and round to the first. Then the title is left in the
middle of a page and come back to after a game: the page is gone, and the
model goes on from where it was, to the next page. Throughout, the picture's
own palette and the rest of the text's do not move.
"""
import struct
import sys

import rp6502

import petscii

T, INTRO = petscii.amiga_tables(), petscii.gen("intro.bin")
FACES = bytes(T["amiga_faces"])
OPTIONS = ("start game", "select map", "difficulty", "controls  ")
NAMES = ("easy", "normal", "hard")
failures = []


def fail(what):
    print("FAIL", what, file=sys.stderr)
    failures.append(what)


def expected(diff):
    """intro.bin with the eye strip for <diff> at 234,75: 160 bytes a row,
    234/2 = 117 bytes in, 8 bytes a row of the strip."""
    pic = bytearray(INTRO)
    for r in range(10):
        o = (75 + r) * 160 + 117
        pic[o:o + 8] = FACES[diff * 80 + r * 8:][:8]
    return bytes(pic)


def screen_codes(text):
    return bytes(32 if c == " " else ord(c) - 96 for c in text)


def cells(emu, row, col, n):
    """The glyphs and the colours of n text cells from row, col."""
    b = petscii.xram(emu, f"XRAM_CHARS+{row}*SCR_STRIDE+{col}*2", 2 * n)
    return b[0::2], b[1::2]


def picture(emu, where, diff):
    got, want = petscii.xram(emu, "XRAM_VIEW", 32000), expected(diff)
    if got != want:
        bad = [i for i in range(32000) if got[i] != want[i]]
        fail(f"{where}: the picture is not intro.bin with the {NAMES[diff]} eyes: "
             f"{len(bad)} bytes differ, the first at line {bad[0] // 160}, "
             f"x {bad[0] % 160 * 2}")


PRG = petscii.x16("ROBOTS.PRG")


def prg(addr, n):
    """n bytes of ROBOTS.PRG at a 2.1 address."""
    return PRG[addr - 0x0801 + 2:][:n]


# 2.1's text colours, the first sixteen of its palette at $306E, as $0RGB.
X16_TEXT = [w & 0xFFF for w in struct.unpack("<16H", prg(0x306E, 32))]
# The flash, SPRITECOLCHART ($41C3), in them. 2.1's colour 0 is clear; its
# 000 stands in, over the option's black box.
FLASH = [X16_TEXT[c] for c in prg(0x41C3, 8)]
# The credits' fade ($28AE), colour 0 clear: None.
FADE = [X16_TEXT[c] if c else None for c in prg(0x28AE, 6)]
# The credits ($2966): screen codes, $FE a new row, $FF the end of a page, 0
# the end of them all. The fourth page, the sound library's, is left out.
CREDITS = prg(0x2966, 256).split(b"\0")[0].split(b"\xff")
PAGES = [page.split(b"\xfe") for page in CREDITS[:3]]
CREDITS_INK = 0x0D              # background 0, nothing, and ink 13

# The picture's own palette and the text's, pic and pic_text, without the
# title's two colours: those are what does not move.
PIC = [petscii.rgb555(c) for c in T["amiga_pal_intro"]]
TEXT = [0] + PIC[1:]
TEXT[8] = PIC[0]


def held(c):
    """A colour as the palette holds it, None clear."""
    return 0 if c is None else petscii.rgb555(c)


def box(page):
    """Rows 14-17 as the text plane holds them, with <page> in the box at
    columns 1-20, or nothing. The rest is blank and clear."""
    cells = bytearray(bytes((32, 0)) * 4 * 40)
    if page is not None:
        for r, row in enumerate(PAGES[page]):
            for c, g in enumerate(row):
                i = (r * 40 + 1 + c) * 2
                cells[i:i + 2] = bytes((g, CREDITS_INK))
    return bytes(cells)


def credits(passes):
    """2.1's TITLE_CREDITS_TICK ($280F) from power-on: after each pass of the
    menu, the page in the box, None before the first, and the credits'
    colour, None while clear. Entry 0 is before the first pass."""
    state = timer = step = 0
    page, upcoming, colour = None, 0, None
    out = [(page, colour)]
    for _ in range(passes):
        if state == 0:                  # clear the box and print a page
            page, upcoming, state = upcoming, (upcoming + 1) % len(PAGES), 1
        elif state == 2:                # hold
            timer = (timer - 1) & 255
            if timer == 1:
                state = 3
        else:                           # fade in, fade out
            timer = (timer - 1) & 255
            if timer == 0:
                timer, colour = 8, FADE[step]
                if state == 1:
                    step += 1
                    if step == 5:
                        state, timer = 2, 0
                else:
                    step -= 1
                    if step < 0:
                        state, timer, step = 0, 20, 0
        out.append((page, colour))
    return out


MODEL = credits(2000)


def sample(emu, frames):
    """A frame at a time: the box's rows, pic and pic_text, and the
    interrupt's SPRITECOLSTATE."""
    out = []
    for _ in range(frames):
        emu.cmd("run 1")
        raw = petscii.xram(emu, "XRAM_PAL_PIC", 64)
        out.append((petscii.xram(emu, "XRAM_CHARS+14*SCR_STRIDE", 4 * 80),
                    [raw[i] | raw[i + 1] << 8 for i in range(0, 64, 2)],
                    petscii.ram(emu, "SPRITECOLSTATE")[0]))
    return out


def check_flash(where, frames):
    """The picture's palette and the text's but for 13 and 14 never move; the
    interrupt steps SPRITECOLSTATE round the chart every seven frames; entry
    14 is the chart's colour for each step, a frame later."""
    for k, (_, pals, _) in enumerate(frames):
        if pals[:16] != PIC or [v for e, v in enumerate(pals[16:]) if e not in (13, 14)] \
                != [v for e, v in enumerate(TEXT) if e not in (13, 14)]:
            fail(f"{where}, frame {k}: the picture's palette or the text's moved")
            return
    states = [st for _, _, st in frames]
    runs = []
    for st in states:
        if runs and runs[-1][0] == st:
            runs[-1][1] += 1
        else:
            runs.append([st, 1])
    if any(n != 7 for _, n in runs[1:-1]) or \
            any(b != (a + 1) % 8 for (a, _), (b, _) in zip(runs, runs[1:])):
        fail(f"{where}: SPRITECOLSTATE does not step every seven frames: {runs}")
    for k in range(1, len(frames)):
        if frames[k][1][16 + 14] != held(FLASH[states[k - 1]]):
            fail(f"{where}, frame {k}: pic_text 14 is ${frames[k][1][30]:04X}, not "
                 f"SPRITECOLCHART's {FLASH[states[k - 1]]:03X} for step {states[k - 1]}")
            return


def fits(frames, start, left=None):
    """The model's entries the frames follow, from model entry <start>, as
    (cells, colour): each True if every frame's box, or every frame's entry
    13, is the model's. After a return to the title, <left> is the page it
    left, which is gone, so the box is blank until the next."""
    cells = colour = True
    for k, (got, pals, _) in enumerate(frames):
        page, c = MODEL[start + k]
        if left is not None and page == left:
            page = None
        cells = cells and got == box(page)
        colour = colour and pals[16 + 13] == held(c)
    return cells, colour


def follow(where, frames, starts, left=None):
    """Where in the model the frames are: the one start the box fits and the
    one entry 13 fits, the palette no later than a frame behind the cells.
    Returns the cells' start, or None."""
    fit = {s: fits(frames, s, left) for s in starts}
    cells = [s for s in starts if fit[s][0]]
    colour = [s for s in starts if fit[s][1]]
    if len(cells) != 1 or len(colour) != 1 or cells[0] - colour[0] not in (0, 1):
        fail(f"{where}: the credits do not follow 2.1's TITLE_CREDITS_TICK: the box "
             f"fits from passes {cells} and entry 13 from {colour}, of {starts[0]}-{starts[-1]}")
        return None
    return cells[0]


if len(CREDITS) != 4 or not CREDITS[3].startswith(bytes((19, 15, 21, 14, 4))):
    fail(f"ROBOTS.PRG's credits at $2966 are not four pages, the last 'sound...': {CREDITS}")
if any(len(p) > 4 or any(len(r) > 20 for r in p) for p in PAGES):
    fail("a page of 2.1's credits does not fit the box")

# The three strips differ, so a picture with the wrong one cannot pass.
if len({expected(d) for d in range(3)}) != 3:
    fail("the three eye strips in amiga_tables.s are not all different")

with rp6502.Emu() as emu:
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU')
    emu.cmd("run 40")

    # The picture, at normal, in the intro palette.
    picture(emu, "menu", 1)
    pal = petscii.xram(emu, "XRAM_PAL_PIC", 32)
    got = [pal[i] | pal[i + 1] << 8 for i in range(0, 32, 2)]
    want = [petscii.rgb555(c) for c in T["amiga_pal_intro"]]
    if got != want:
        fail(f"the picture's palette is {[hex(v) for v in got]}, "
             f"not _amiga_pal_intro's {[hex(v) for v in want]}")

    # The text plane: eight lines below the grid, in the picture's colours.
    cfg = petscii.xram(emu, "XRAM_CFG_CHARS", 14)
    y, palette = cfg[4] | cfg[5] << 8, cfg[12] | cfg[13] << 8
    if y != emu.sym["SCREEN_TOP"] + 8:
        fail(f"the intro's text plane is at line {y}, not SCREEN_TOP+8")
    if palette != emu.sym["XRAM_PAL_PIC_TEXT"]:
        fail(f"the intro's text plane uses palette ${palette:04X}, not XRAM_PAL_PIC_TEXT")

    # The four options at rows 1-4, column 4, START GAME selected in 14 and
    # the rest in 15; the first map's name at row 7, column 1, in 15.
    for row, text in enumerate(OPTIONS, 1):
        glyphs, colours = cells(emu, row, 4, 10)
        ink = 0x8E if row == 1 else 0x8F
        if glyphs != screen_codes(text) or set(colours) != {ink}:
            fail(f"row {row}: {glyphs.hex()} in {colours.hex()}, "
                 f"not {text!r} in ${ink:02X}")
    glyphs, colours = cells(emu, 7, 1, 16)
    if glyphs != petscii.ram(emu, "MAP_NAMES", 16) or set(colours) != {0x8F}:
        fail(f"row 7: {glyphs.hex()} in {colours.hex()}, not the first map's name in $8F")

    # Down twice to DIFFICULTY, then round it: hard, easy, normal. Each time
    # the eyes change and nothing else in the picture does.
    petscii.tap(emu, "k")
    petscii.tap(emu, "k")
    for diff in (2, 0, 1):
        petscii.tap(emu, "space")
        if petscii.ram(emu, "DIFF_LEVEL")[0] != diff:
            fail(f"DIFF_LEVEL is {petscii.ram(emu, 'DIFF_LEVEL')[0]}, not {diff}")
        picture(emu, NAMES[diff], diff)
    emu.cmd('shot "title.png"')

with rp6502.Emu() as emu:
    # From the menu checkpoint: the first page at once, its fade 256 ticks
    # later, the next two pages, and the first again, 349 ticks each; then into
    # its hold.
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU')
    first = sample(emu, 1400)
    check_flash("the first visit", first)
    at = follow("the first visit", first, range(0, 9))
    if at is not None and MODEL[at + len(first) - 1][1] != FADE[4]:
        fail("the first visit did not end in a page's hold")

    # Start, quit from the pause and come back: in play the text's 13 and 14
    # are the picture's again, and back at the title the page is gone and the
    # credits go on from where they were, with the passes that saw the keys.
    petscii.tap(emu, "space")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_PLAY')
    raw = petscii.xram(emu, "XRAM_PAL_PIC_TEXT+13*2", 4)
    if (raw[0] | raw[1] << 8, raw[2] | raw[3] << 8) != (TEXT[13], TEXT[14]):
        fail(f"in play pic_text 13 and 14 are {raw.hex()}, not the picture's own")
    emu.cmd("run 30")
    petscii.tap(emu, "escape")
    petscii.tap(emu, "y")
    emu.cmd("run 120")
    petscii.tap(emu, "space")
    emu.cmd('wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU 400')
    again = sample(emu, 300)
    check_flash("the return", again)
    if at is not None:
        last = at + len(first) - 1
        left = MODEL[last][0]
        back = follow("the return", again, range(last + 1, last + 12), left)
        if back is not None and MODEL[back + len(again) - 1][0] != (left + 1) % 3:
            fail("the return did not reach the next page")
    emu.cmd('shot "credits.png"')

print(f"title: picture, palette, text plane, menu, three eye strips, the flash and "
      f"the credits checked, {len(failures)} failures")
sys.exit(1 if failures else 0)
