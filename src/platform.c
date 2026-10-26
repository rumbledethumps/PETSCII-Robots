/* The presentation side of the ported game logic.
 *
 * src/game/platform_bridge.s forwards the AI's calls here. Each of these stands
 * in for a routine that lived in the X16's machine-specific file and talked to
 * VERA or ZSOUND directly. What they draw is the Amiga version's screen: its
 * game-over picture, its HUD and its text positions, on the 320x200 screen
 * that xram.h places 20 lines down the canvas -- but for the intro, which is
 * X16 2.1's title, with the text where 2.1 puts it. The playfield itself is
 * src/view.c.
 */
#include <fcntl.h>
#include <rp6502.h>
#include <stdbool.h>
#include <stdio.h>
#include <unistd.h>

#include "game/game.h"
#include "input.h"
#include "livemap.h"
#include "palette.h"
#include "platform.h"
#include "sound.h"
#include "view.h"
#include "xram.h"

static void decwrite(unsigned char col, unsigned char row, unsigned char v,
                     unsigned char color);

/* A text cell's colour byte is background then foreground. Entry 8 of every
 * text palette is black, so a written cell is opaque black behind its glyph,
 * which is how the Amiga draws text; background 0 is transparent, which is how
 * a blank cell lets the playfield and the pictures show through. */
#define INK(fg)         MODE1_BG_FG(8, (fg))
#define CLEAR           0x00
#define TEXT_GREEN      INK(10)     /* the Amiga's default text colour */
#define TEXT_WHITE      INK(1)
#define INFO_GREEN      INK(9)      /* the INFORMATION box: 790, softer */

/* ---- the character plane -------------------------------------------- */

static void put_cell(unsigned char col, unsigned char row,
                     unsigned char glyph, unsigned char color)
{
    RIA.addr0 = CELL(col, row);
    RIA.step0 = 1;
    RIA.rw0 = glyph;
    RIA.rw0 = color;
}

/* Glyphs and one colour for all of them. */
static void put_text(unsigned char col, unsigned char row,
                     const unsigned char *g, unsigned char n, unsigned char color)
{
    RIA.addr0 = CELL(col, row);
    RIA.step0 = 1;
    while (n--) {
        RIA.rw0 = *g++;
        RIA.rw0 = color;
    }
}

/* Glyphs only, leaving the colour byte alone -- the X16 does the same by
 * setting the address increment to 2. */
static void put_glyphs(unsigned char col, unsigned char row,
                       const unsigned char *g, unsigned char n)
{
    RIA.addr0 = CELL(col, row);
    RIA.step0 = 2;
    while (n--)
        RIA.rw0 = *g++;
    RIA.step0 = 1;
}

static void fill_cells(unsigned char col, unsigned char row,
                       unsigned char glyph, unsigned char color, unsigned char n)
{
    RIA.addr0 = CELL(col, row);
    RIA.step0 = 1;
    while (n--) {
        RIA.rw0 = glyph;
        RIA.rw0 = color;
    }
}

/* Every cell blank and transparent. */
void plat_clear_text(void)
{
    unsigned i;
    RIA.addr0 = XRAM_CHARS;
    RIA.step0 = 1;
    for (i = 0; i < SCR_COLS * SCR_ROWS; i++) {
        RIA.rw0 = 32;                   /* screen code space */
        RIA.rw0 = CLEAR;
    }
}

/* A 40-wide layout, run-length encoded: a literal byte is one cell, and byte 96
 * introduces "the next byte, count+1 times". Glyphs only. The X16's layouts are
 * 30 rows; the screen here is 25, and nothing below row 24 is decoded. */
static void decompress_screen(const unsigned char *src)
{
    unsigned char x = 0, y = 0, ch, n;

    RIA.addr0 = XRAM_CHARS;
    RIA.step0 = 2;
    while (y < SCR_ROWS) {
        ch = *src++;
        n = 1;
        if (ch == 96) {                 /* the repeat flag */
            ch = *src++;
            n = (unsigned char)(*src++ + 1);
        }
        while (n-- && y < SCR_ROWS) {
            RIA.rw0 = ch;
            if (++x == SCR_COLS) {
                x = 0;
                if (++y < SCR_ROWS)
                    RIA.addr0 = CELL(0, y);
            }
        }
    }
    RIA.step0 = 1;
}

/* ---- whole screens ---------------------------------------------------- */

/* Pictures go on plane 1's bitmap layer, which covers the playfield and the
 * HUD frame on plane 0. It has no enable bit; moving it a screenful left hides
 * it without touching the pixels. */
static int overlay_x = -320;

void plat_overlay_at(int x, int y, unsigned width, unsigned height,
                     unsigned palette)
{
    mode3_config_t cfg;
    overlay_x = x;
    cfg.x_wrap = false;
    cfg.y_wrap = false;
    cfg.x_pos_px = x + shake_dx;
    cfg.y_pos_px = y;
    cfg.width_px = (int)width;
    cfg.height_px = (int)height;
    cfg.xram_data_ptr = XRAM_VIEW;
    cfg.xram_palette_ptr = palette;
    xram0_write(XRAM_CFG_OVERLAY, &cfg, sizeof cfg);
}

static void overlay(int x, unsigned width, unsigned height, unsigned palette)
{
    plat_overlay_at(x, SCREEN_TOP, width, height, palette);
}

void plat_overlay_hide(void)
{
    overlay(-320, 320, SCREEN_H, XRAM_PAL_PIC);
}

/* Screen shake's share, from src/view.c whenever the offset changes: the HUD
 * frame, the text, the picture layer and the HUD's pictures. The cursor stays
 * where it is, as the Amiga's hardware sprite does. */
void __fastcall__ plat_shake(unsigned char dx)
{
    static const unsigned hud_x[HUD_CURSOR] = { 272, 272, 272, 272, 288, 304 };
    unsigned char i;
    unsigned x;

    RIA.step0 = 1;
    RIA.addr0 = XRAM_CFG_HUD + offsetof(mode2_config_t, x_pos_px);
    RIA.rw0 = dx;
    RIA.rw0 = 0;
    RIA.addr0 = XRAM_CFG_CHARS + offsetof(mode1_config_t, x_pos_px);
    RIA.rw0 = dx;
    RIA.rw0 = 0;
    x = (unsigned)(overlay_x + dx);
    RIA.addr0 = XRAM_CFG_OVERLAY + offsetof(mode3_config_t, x_pos_px);
    RIA.rw0 = (unsigned char)x;
    RIA.rw0 = (unsigned char)(x >> 8);
    for (i = 0; i < HUD_CURSOR; i++) {
        x = hud_x[i] + dx;
        RIA.addr0 = HUD_SPRITE(i);
        RIA.rw0 = (unsigned char)x;
        RIA.rw0 = (unsigned char)(x >> 8);
    }
}

/* The text plane's position and palette. The intro's text sits eight lines
 * below the grid, so rows 1-4 and 7 are 2.1's rows 2-5 and 8, inside its
 * picture's empty boxes; text over a picture uses its colours. */
static void text_plane(int y, unsigned palette)
{
    RIA.addr0 = XRAM_CFG_CHARS + offsetof(mode1_config_t, y_pos_px);
    RIA.step0 = 1;
    RIA.rw0 = (unsigned char)(y & 0xFF);
    RIA.rw0 = (unsigned char)(y >> 8);
    RIA.addr0 = XRAM_CFG_CHARS + offsetof(mode1_config_t, xram_palette_ptr);
    RIA.rw0 = (unsigned char)(palette & 0xFF);
    RIA.rw0 = (unsigned char)(palette >> 8);
}

/* A 320x200 picture into the playfield's memory. read_xram hands the whole
 * transfer to the RIA, so the 6502 never touches the pixels. The tile cache
 * was in those bytes, so it is forgotten and stops loading until the game
 * screen comes back; so is a live map left up when the game ended. */
static void load_picture(const char *name)
{
    int fd;
    livemap_stop();
    view_suspend();
    fd = open(name, O_RDONLY);
    if (fd < 0)
        return;
    read_xram(XRAM_VIEW, SCREEN_H * 160u, fd);
    close(fd);
}

static void hud_park(void)
{
    unsigned char i;
    RIA.step0 = 1;
    for (i = 0; i < HUD_COUNT; i++) {
        RIA.addr0 = HUD_SPRITE(i) + offsetof(mode5_csprite_t, y_pos_px);
        RIA.rw0 = SPR_PARKED_Y;
        RIA.rw0 = 0;
    }
}

static unsigned weapon_shown, item_shown, health_shown;

/* Black over everything but the text: the picture layer, shown with a black
 * palette. Whatever is under it -- a half-loaded picture, a tile cache being
 * filled -- stays out of sight until it is ready. */
static void cover(void)
{
    pal_picture_black();
    overlay(0, 320, SCREEN_H, XRAM_PAL_PIC);
}

/* Each screen fades out before it changes and in once it is drawn, fifteen
 * frames each way, as the Amiga's do; src/palette.c. */
void plat_display_intro_screen(void)
{
    pal_fade_out();
    cover();
    hud_park();
    plat_clear_text();
    load_picture("ROM:intro");
    pal_picture(amiga_pal_intro);
    text_plane(SCREEN_TOP + 8, XRAM_PAL_PIC_TEXT);
    plat_menu_flash();                  /* the title's own colours, to fade in */
}

/* The game screen: the Amiga's frame is plane 0's tile map, set up once, so
 * this lays out the text that sits in it, under a cover that
 * plat_reveal_playfield lifts once the level is drawn. */
void plat_display_game_screen(void)
{
    static const unsigned char ticks[6] = {
        INK(15), INK(15), INK(12), INK(12), INK(9), INK(9),
    };
    unsigned char i;

    cover();
    plat_clear_text();
    text_plane(SCREEN_TOP, XRAM_PAL_A);
    weapon_shown = item_shown = health_shown = 0xFFFF;

    /* The message console carries its colour from the outset, because
     * PRINT_INFO writes glyphs only, as the X16 did. */
    for (i = 22; i < 25; i++)
        fill_cells(0, i, 32, INFO_GREEN, 33);

    /* DISPLAY_GAME_SCREEN's six marks under the health bar. */
    for (i = 0; i < 6; i++)
        put_cell((unsigned char)(34 + i), 24, 0x71, ticks[i]);
}

void plat_reveal_playfield(void)
{
    plat_overlay_hide();
}

/* The statistics, on the Amiga's game-over picture. */
void plat_display_endgame_screen(void)
{
    pal_fade_out();
    cover();
    hud_park();
    plat_clear_text();
    load_picture("ROM:gameover");
    pal_picture(amiga_pal_gameover);
    text_plane(SCREEN_TOP, XRAM_PAL_PIC_TEXT);
}

/* ---- the intro menu --------------------------------------------------- */

/* The four options, as the Amiga's INTRO_OPTIONS spells them, in screen
 * codes. 2.1's picture leaves their boxes empty, so plat_display_menu writes
 * all four, 14 for the selected one, which flashes, and green for the rest. */
static const unsigned char MENU_TEXT[4][10] = {
    { 19, 20,  1, 18, 20, 32,  7,  1, 13,  5 },     /* "start game" */
    { 19,  5, 12,  5,  3, 20, 32, 13,  1, 16 },     /* "select map" */
    {  4,  9,  6,  6,  9,  3, 21, 12, 20, 25 },     /* "difficulty" */
    {  3, 15, 14, 20, 18, 15, 12, 19, 32, 32 },     /* "controls  " */
};

/* CCON2: the chosen scheme, written over the controls line. Without it the
 * option looked broken: it cycled CONTROL and changed nothing you could see.
 *
 * DELIBERATE CHANGE. The original offers three schemes -- keyboard, custom key,
 * snes pad -- and the pad is one of them, which means the pad cannot be chosen
 * with the pad. The menu it has to be chosen from reads the keyboard only. Here
 * the pad is always live and merged with whichever keyboard scheme is chosen,
 * so the choice is only which keys: the defaults, or thirteen of your own.
 * CONTROL_TEXT is therefore ours rather than converted, and lives here. */
static const unsigned char CONTROL_TEXT[2][10] = {
    {  4,  5,  6,  1, 21, 12, 20, 32, 32, 32 },     /* "default   " */
    {  3, 21, 19, 20, 15, 13, 32, 32, 32, 32 },     /* "custom    " */
};

/* Whether the controls line has been changed since the menu came up; until
 * then it says "controls", as plat_display_menu wrote it. */
static unsigned char control_shown;

/* REVERSE_MENU_OPTION, in the Amiga's colours: 14 for the selected option,
 * which the title pulses through 2.1's greys (plat_menu_flash), and 15,
 * green, for the others. */
void __fastcall__ plat_menu_option(unsigned char row, unsigned char selected)
{
    const unsigned char *text = row == 3 && control_shown
                              ? CONTROL_TEXT[CONTROL & 1] : MENU_TEXT[row];
    put_text(4, (unsigned char)(1 + row), text, 10, INK(selected ? 14 : 15));
}

void plat_display_menu(void)
{
    unsigned char i;
    control_shown = 0;
    for (i = 0; i < 4; i++)
        plat_menu_option(i, i == MENUY);
}

/* The level name, sixteen characters at row 7 column 1. MAP_NAMES is one
 * sixteen-byte name per level, so the offset is the level number times
 * sixteen -- which is what CALC_MAP_NAME computes the long way. */
void plat_display_map_name(void)
{
    put_text(1, 7, MAP_NAMES + (unsigned)SELECTED_MAP * 16, 16, INK(15));
}

void plat_display_control(void)
{
    control_shown = 1;
    plat_menu_option(3, MENUY == 3);
}

/* The intro robot's eyes: one of 2.1's three 16x10 strips (THREE_FACES), by
 * difficulty, into the picture at 234,75 where 2.1 draws them -- 160 bytes a
 * row, 234/2 = 117 bytes in. The mouth below is part of 2.1's picture. */
void plat_change_difficulty_level(void)
{
    const unsigned char *p = amiga_faces + (unsigned)DIFF_LEVEL * (10 * 8);
    unsigned char row, i;
    RIA.step0 = 1;
    for (row = 0; row < 10; row++) {
        RIA.addr0 = XRAM_VIEW + (unsigned)(75 + row) * 160u + 117u;
        for (i = 0; i < 8; i++)
            RIA.rw0 = *p++;
    }
}

/* ---- X16 2.1's title: the flash and the credits ----------------------- */

/* 2.1's credits ($2966), its first three pages as it has them: screen codes,
 * CR_ROW for the next row, CR_PAGE for the end of a page and 0 for the end of
 * them all, after which the first comes round again. The names are spaced to
 * end at the box's right edge. 2.1's fourth page credits the sound library,
 * which this version does not use, and is left out: the third ends as 2.1's
 * fourth does. */
#define CR_ROW  0xFE
#define CR_PAGE 0xFF
static const unsigned char CREDITS[] = {
    /* "6502 assembly:" */
    54, 53, 48, 50, 32, 1, 19, 19, 5, 13, 2, 12, 25, 58, CR_ROW,
    /* "        david murray" */
    32, 32, 32, 32, 32, 32, 32, 32, 4, 1, 22, 9, 4, 32, 13, 21, 18, 18, 1, 25,
    CR_PAGE,
    /* "music:" */
    13, 21, 19, 9, 3, 58, CR_ROW,
    /* " anders enger jensen" */
    32, 1, 14, 4, 5, 18, 19, 32, 5, 14, 7, 5, 18, 32, 10, 5, 14, 19, 5, 14,
    CR_ROW,
    /* "           noel aman" */
    32, 32, 32, 32, 32, 32, 32, 32, 32, 32, 32, 14, 15, 5, 12, 32, 1, 13, 1,
    14, CR_ROW,
    /* "         ian herrera" */
    32, 32, 32, 32, 32, 32, 32, 32, 32, 9, 1, 14, 32, 8, 5, 18, 18, 5, 18, 1,
    CR_PAGE,
    /* "pixel art:" */
    16, 9, 24, 5, 12, 32, 1, 18, 20, 58, CR_ROW,
    /* "       piotr radecki" */
    32, 32, 32, 32, 32, 32, 32, 16, 9, 15, 20, 18, 32, 18, 1, 4, 5, 3, 11, 9,
    0,
};

/* 2.1's credits fade ($28AE), its colours 0 11 12 15 1 1, which its text
 * palette makes clear, 555, 888, CCC and white twice: in from the first to the
 * fifth, out from the sixth back to the first. */
static const unsigned CREDITS_FADE[6] = {
    PAL_CLEAR, 0x555, 0x888, 0xCCC, 0xFFF, 0xFFF,
};

/* The box: text rows 14 to 17, columns 1 to 20, which is 2.1's rows 15 to 18
 * with the text plane eight lines down, over the city on the left. The letters
 * are ink 13 on nothing, as 2.1's are on its clear colour 0, so only they
 * show, in the colour the fade has reached. */
#define CREDITS_ROW 14
#define CREDITS_INK MODE1_BG_FG(0, 13)

/* TITLE_CREDITS_TICK's state, 2.1's CREDITS_STATE, _TIMER, _FADE_IDX, _PTR
 * and _COLOUR, all starting at 0, colour 0 being clear, and never reset: the
 * title picks up where it was, with the page it was showing gone, since
 * coming back clears the screen, as 2.1's does. */
static unsigned char credits_state, credits_timer, credits_fade, credits_ptr;
static unsigned credits_ink = PAL_CLEAR;

/* UPDATE_MENU_FLASH ($2741), every pass of the menu, as 2.1's ISLOOP calls
 * it: the selected option in SPRITECOLCHART's colour at the step the interrupt
 * has reached, and the credits in theirs. 2.1 writes the colour into the
 * option's cells; here they are INK(14) already, and it goes into the
 * palette's entry instead, src/palette.c. */
void plat_menu_flash(void)
{
    pal_title_inks(credits_ink, SPRITECOLCHART[SPRITECOLSTATE]);
}

/* CREDITS_CLEAR_BOX ($28B4). */
static void credits_clear(void)
{
    unsigned char row;
    for (row = CREDITS_ROW; row < CREDITS_ROW + 4; row++)
        fill_cells(1, row, 32, CLEAR, 20);
}

/* CREDITS_PRINT_PAGE ($291E): the next page, in the colour the fade is at,
 * which is clear. */
static void credits_page(void)
{
    unsigned char row = CREDITS_ROW, c;

    RIA.addr0 = CELL(1, row);
    RIA.step0 = 1;
    for (;;) {
        c = CREDITS[credits_ptr];
        if (!c) {
            credits_ptr = 0;
            return;
        }
        ++credits_ptr;
        if (c == CR_PAGE)
            return;
        if (c == CR_ROW) {
            RIA.addr0 = CELL(1, ++row);
            continue;
        }
        RIA.rw0 = c;
        RIA.rw0 = CREDITS_INK;
    }
}

/* CREDITS_SET_COLOUR ($28E9): 2.1 writes the colour into the box's cells,
 * and here it goes into the palette's entry 13 instead. */
static void credits_colour(void)
{
    credits_ink = CREDITS_FADE[credits_fade];
    plat_menu_flash();
}

/* TITLE_CREDITS_TICK ($280F), once a tick of the menu, as 2.1's acts once a
 * BGTIMER1: a page printed while it is clear, faded in eight ticks a step,
 * held 255, faded out, and twenty ticks later the next, 349 ticks a page. The
 * first after power-on waits 256 ticks rather than twenty to fade in, since
 * 2.1's timer starts at 0. */
void plat_credits_tick(void)
{
    switch (credits_state) {
    case 0:
        credits_clear();
        credits_page();
        credits_state = 1;
        break;
    case 1:                             /* CREDITS_FADE_IN */
        if (--credits_timer)
            break;
        credits_timer = 8;
        credits_colour();
        if (++credits_fade == 5) {
            credits_state = 2;
            credits_timer = 0;
        }
        break;
    case 2:                             /* CREDITS_HOLD */
        if (--credits_timer == 1)
            credits_state = 3;
        break;
    default:                            /* CREDITS_FADE_OUT */
        if (--credits_timer)
            break;
        credits_timer = 8;
        credits_colour();
        if (--credits_fade == 0xFF) {
            credits_state = 0;
            credits_timer = 20;
            credits_fade = 0;
        }
    }
}

/* A gamepad press as the key code a menu would have got from the keyboard, so
 * every screen that waits on GETIN answers to the pad without knowing about it:
 * the intro menu, the elevator panel, the pause prompt. Directions come back as
 * the cursor codes the game already accepts alongside the configurable ones,
 * and either the bottom face button or START reads as a press of space.
 *
 * Returns one code per call and consumes the latch, the same contract GETIN
 * has. Not used in play -- gamepad_pass does that, because there the buttons
 * mean more than a menu can express. */
unsigned char plat_pad_key(void)
{
    plat_gamepad_read();

    if (NEW_BUTTONS[PAD_UP])    { NEW_BUTTONS[PAD_UP] = 0;    return 0x91; }
    if (NEW_BUTTONS[PAD_DOWN])  { NEW_BUTTONS[PAD_DOWN] = 0;  return 0x11; }
    if (NEW_BUTTONS[PAD_LEFT])  { NEW_BUTTONS[PAD_LEFT] = 0;  return 0x9D; }
    if (NEW_BUTTONS[PAD_RIGHT]) { NEW_BUTTONS[PAD_RIGHT] = 0; return 0x1D; }
    if (NEW_BUTTONS[PAD_START]) { NEW_BUTTONS[PAD_START] = 0; return 32; }
    if (NEW_BUTTONS[PAD_B])     { NEW_BUTTONS[PAD_B] = 0;     return 32; }
    return 0;
}

/* SET_CUSTOM_KEYS, from x16Robots.ASM 4767. Thirteen keys in the order
 * KEY_MOVE_UP lists them, each echoed back as the decimal code it will be
 * compared against, then KEYS_DEFINED so it is not asked again.
 *
 * The prompts are the screen SCR_CUSTOM_KEYS draws, in the Amiga's colour 15
 * over a black screen; the answers go down column 16 from row 8, which is
 * where the original puts them.
 */
void plat_set_custom_keys(void)
{
    unsigned char i, key;

    if (KEYS_DEFINED)
        return;

    pal_fade_out();
    pal_picture_black();
    plat_clear_text();
    for (i = 0; i < SCR_ROWS; i++)
        fill_cells(0, i, 32, INK(15), SCR_COLS);
    text_plane(SCREEN_TOP, XRAM_PAL_PIC_TEXT);
    decompress_screen(SCR_CUSTOM_KEYS);
    pal_fade_in();

    /* ESC is refused, as 2.1's SCK01 does ($59F2); the pre-release took it.
     * The game loop tests the thirteen before ESC, so an ESC bound to one of
     * them would leave no way to pause. */
    for (i = 0; i < 13; i++) {
        do {
            view_idle();
            key = plat_getin();
        } while (!key || key == 3);
        KEY_MOVE_UP[i] = key;
        decwrite(16, (unsigned char)(8 + i), key, INK(15));
    }

    KEYS_DEFINED = 1;
}

/* ---- the end of a game ------------------------------------------------ */

/* The box, eleven characters wide at column 11, rows 9 to 11, in the Amiga's
 * text green. */
static void game_over_box(void)
{
    put_text(11, 9, GAMEOVER1, 11, TEXT_GREEN);
    put_text(11, 10, GAMEOVER2, 11, TEXT_GREEN);
    put_text(11, 11, GAMEOVER3, 11, TEXT_GREEN);
}

/* The stats screen: which level, how long it took, and what was left, where
 * the Amiga's DISPLAY_ENDGAME_SCREEN writes them over its picture. */
static void endgame_stats(void)
{
    static const unsigned char words[3][6] = {      /* easy / normal / hard */
        {  5,  1, 19, 25, 32, 32 },
        { 14, 15, 18, 13,  1, 12 },
        {  8,  1, 18,  4, 32, 32 },
    };
    unsigned char i, robots = 0, secrets = 0;

    put_text(22, 7, MAP_NAMES + (unsigned)SELECTED_MAP * 16, 16, INK(4));

    decwrite(21, 9, HOURS, INK(4));
    decwrite(24, 9, MINUTES, INK(4));
    decwrite(27, 9, SECONDS, INK(4));
    /* Blank the leading digit of the hours and put colons between the fields,
     * exactly where the original pokes them. */
    put_glyphs(21, 9, (const unsigned char *)"\x20", 1);
    put_glyphs(24, 9, (const unsigned char *)"\x3A", 1);
    put_glyphs(27, 9, (const unsigned char *)"\x3A", 1);

    for (i = 1; i < 28; i++)
        if (UNIT_TYPE[i])
            robots++;
    for (i = 48; i < 64; i++)
        if (UNIT_TYPE[i])
            secrets++;
    decwrite(22, 11, robots, INK(4));
    decwrite(22, 13, secrets, INK(4));

    put_text(22, 15, words[DIFF_LEVEL < 3 ? DIFF_LEVEL : 1], 6, INK(4));
}

/* The player is dead, or has reached the transporter. Show the box, wait, then
 * the stats screen, then back to the title.
 *
 * GAME_OVER keeps the ending in TEMP_D, and a dead player becomes a unit again
 * for GOM0, type 1, as 2.1 makes him ($53EE). The pre-release left him type 0,
 * which CHECK_FOR_UNIT does not see, so a robot walked onto the body and
 * attacked it from there; now it bumps it, as it would him alive, and the
 * first hit makes him type 0 again (UD01). The body stays drawn either way,
 * since its frame comes from PLAYER_DIRECTION and not from the type. */
void plat_game_over(void)
{
    unsigned char won;

    CLOCK_ACTIVE = 0;
    music_stop();

    won = UNIT_TYPE[0];                 /* TEMP_D: 0 dead, 2 won */
    if (!won) {
        PLAYER_DIRECTION = FACE_DEAD;
        PLAYER_ANIMATE = 0;
        UNIT_TYPE[0] = 1;               /* 2.1 $53EE: the body is a unit again */
        view_player();
        KEYTIMER = 100;
    } else {
        view_player();                  /* won: transported away, not drawn */
    }

    /* GOM0. The only wait the world keeps running through: the body is on
     * screen and whatever killed him is still moving, which is the point. */
    do {
        BACKGROUND_TASKS();
    } while (KEYTIMER);

    /* RP6502: the ending goes back into his type, which is what the probe
     * reports at the menu. 2.1 only reads TEMP_D, and leaves a dead player
     * type 1, which here would read as a game still being played.
     *
     * 2.1 also ends both flashes here ($5405-$540F), because its IRQ2 runs on
     * the AI's tick, which stops at the box. Here they run on the interrupt
     * and finish by themselves within ten frames, so that is not copied. */
    UNIT_TYPE[0] = won;
    SCREEN_SHAKE = 0;
    game_over_box();

    /* GOM2, and everything after it, runs BACKGROUND_TASKS nowhere. The AI
     * stops the moment the box goes up. Calling it in these waits is what left
     * a robot attacking the corpse behind the GAME OVER box, and then -- since
     * BACKGROUND_TASKS redraws the map window whenever REDRAW_WINDOW is set --
     * drawing the playfield back over the endgame statistics. */
    KEYTIMER = 100;
    while (KEYTIMER)
        view_idle();
    plat_clear_key_buffer();
    while (!plat_getin())               /* GOM3 */
        view_idle();

    plat_endgame(won);
}

/* GOM4 to GOM6: the statistics, then back to the title. The pause's Y comes
 * straight here, as 2.1's PG6 does ($46B5), with won 0: no box, no GOM0. */
void __fastcall__ plat_endgame(unsigned char won)
{
    const unsigned char *msg;
    unsigned char n;

    /* GOM4: the statistics, over the playfield. */
    plat_clear_key_buffer();
    music_stop();
    plat_display_endgame_screen();
    endgame_stats();

    /* DISPLAY_WIN_LOSE, from TEMP_D. The original starts a tune here rather
     * than playing an effect, which is what the win and lose patterns in the
     * recovered PET music are for. */
    msg = won ? WIN_MSG : LOS_MSG;
    n = (unsigned char)(won ? 8 : 9);
    put_text(16, 3, msg, n, INK(4));
    if (music_enabled)
        music_play(won ? SONG_WIN : SONG_LOSE);
    pal_fade_in();

    /* GOM5 drains whatever is already waiting before it waits for a fresh
     * press. Without that the key that dismissed the box is still there and
     * carries straight through, which is the statistics screen appearing and
     * vanishing too fast to read. */
    while (plat_getin())
        ;
    while (!plat_getin())
        view_idle();
    plat_clear_key_buffer();
}

/* ---- the message console --------------------------------------------- */

/* Rows 22, 23 and 24, columns 0 to 32: the Amiga's information panel. */
#define CON_TOP    22
#define CON_BOTTOM 24
#define CON_WIDTH  33

static unsigned char print_x;

/* Copy row 23 to 22 and row 24 to 23, then blank row 24. Glyphs only: the
 * console colour is set once and never scrolls.
 *
 * The X16 reads the characters back out of video memory to do this. The RIA
 * portals read as well as write -- a read of RIA.rw0 returns the byte and then
 * advances addr0 by step0 -- so the routine ports directly instead of needing a
 * shadow copy in RAM. Portal 0 reads, portal 1 writes. */
void plat_scroll_info(void)
{
    unsigned char i;

    RIA.step0 = 2;
    RIA.step1 = 2;
    RIA.addr0 = CELL(0, CON_TOP + 1);
    RIA.addr1 = CELL(0, CON_TOP);
    for (i = 0; i < CON_WIDTH; i++)
        RIA.rw1 = RIA.rw0;

    RIA.addr0 = CELL(0, CON_BOTTOM);
    RIA.addr1 = CELL(0, CON_TOP + 1);
    for (i = 0; i < CON_WIDTH; i++)
        RIA.rw1 = RIA.rw0;

    RIA.addr0 = CELL(0, CON_BOTTOM);
    for (i = 0; i < CON_WIDTH; i++)
        RIA.rw0 = 32;                   /* screen code space */

    RIA.step0 = 1;
    RIA.step1 = 1;
}

/* SOURCE points at a screen-code string: 0 ends it, 255 forces a new line.
 * Text always arrives on the bottom row, so printing always scrolls first. */
void plat_print_info(void)
{
    const unsigned char *p = SOURCE;
    unsigned char ch;

    plat_scroll_info();
    print_x = 0;
    RIA.addr0 = CELL(0, CON_BOTTOM);
    RIA.step0 = 2;

    for (;;) {
        ch = *p++;
        if (ch == 0)
            break;
        if (ch == 255) {
            RIA.step0 = 1;
            plat_scroll_info();
            print_x = 0;
            RIA.addr0 = CELL(0, CON_BOTTOM);
            RIA.step0 = 2;
            continue;
        }
        RIA.rw0 = ch;
        if (++print_x == 34) {
            RIA.step0 = 1;
            plat_scroll_info();
            print_x = 0;
            RIA.addr0 = CELL(0, CON_BOTTOM);
            RIA.step0 = 2;
        }
    }
    RIA.step0 = 1;
}

/* The eight dots SEARCH_OBJECT lays down while it works, on the console's
 * bottom row from column 9. A is the dot index. */
void __fastcall__ plat_search_dot(unsigned char n)
{
    put_cell((unsigned char)(9 + n), CON_BOTTOM, 46, INFO_GREEN);
}

/* ---- the status panel ------------------------------------------------- */

/* Three digits, as DECWRITE puts them. */
static void decwrite(unsigned char col, unsigned char row, unsigned char v,
                     unsigned char color)
{
    unsigned char d[3];
    d[0] = (unsigned char)(48 + v / 100);
    d[1] = (unsigned char)(48 + (v / 10) % 10);
    d[2] = (unsigned char)(48 + v % 10);
    put_text(col, row, d, 3, color);
}

/* A HUD picture: hidden, loaded, then shown, so it never shows half loaded.
 * The record is the first of the picture's in ROM:images. */
static void hud_picture(unsigned char sprite, unsigned *shown, unsigned record,
                        unsigned xaddr, unsigned bytes, int x, int y)
{
    if (*shown != record) {
        RIA.addr0 = HUD_SPRITE(sprite) + offsetof(mode5_csprite_t, y_pos_px);
        RIA.step0 = 1;
        RIA.rw0 = SPR_PARKED_Y;
        RIA.rw0 = 0;
        view_load(xaddr, record, bytes);
        *shown = record;
    }
    x += shake_dx;
    RIA.addr0 = HUD_SPRITE(sprite);
    RIA.step0 = 1;
    RIA.rw0 = (unsigned char)x;
    RIA.rw0 = (unsigned char)(x >> 8);
    RIA.rw0 = (unsigned char)y;
    RIA.rw0 = (unsigned char)(y >> 8);
    RIA.rw0 = (unsigned char)(xaddr & 0xFF);
    RIA.rw0 = (unsigned char)(xaddr >> 8);
    RIA.rw0 = (unsigned char)(XRAM_PAL_FG & 0xFF);
    RIA.rw0 = (unsigned char)(XRAM_PAL_FG >> 8);
}

static void hud_hide(unsigned char sprite)
{
    RIA.addr0 = HUD_SPRITE(sprite) + offsetof(mode5_csprite_t, y_pos_px);
    RIA.step0 = 1;
    RIA.rw0 = SPR_PARKED_Y;
    RIA.rw0 = 0;
}

/* The bar on row 23, columns 34 to 39: a full block per two health, a half
 * block for the odd one, spaces after. Above it, the Amiga's picture of the
 * player, which looks worse the less health there is. */
void plat_display_player_health(void)
{
    unsigned char i, half = (unsigned char)(UNIT_HEALTH[0] >> 1), h;
    unsigned char cells[6];
    for (i = 0; i < 6; i++)
        cells[i] = (unsigned char)(i < half ? 0x66
                   : (i == half && (UNIT_HEALTH[0] & 1)) ? 0x5C : 32);
    put_text(34, 23, cells, 6, TEXT_GREEN);

    h = (unsigned char)(5 - (half < 5 ? half : 5));
    hud_picture(HUD_HEALTH, &health_shown, IMG_HEALTH + h * 5u, XRAM_HEALTH,
                sizeof(img48x52_t), 272, SCREEN_TOP + 131 + (h >> 1));
}

/* The three key cards, spade, heart and star, side by side under KEYS. */
void plat_display_keys(void)
{
    unsigned char k;
    for (k = 0; k < 3; k++) {
        if (!(KEYS & (1 << k))) {
            hud_hide((unsigned char)(HUD_KEY0 + k));
            continue;
        }
        RIA.addr0 = HUD_SPRITE(HUD_KEY0 + k);
        RIA.step0 = 1;
        RIA.rw0 = (unsigned char)(272 + k * 16 + shake_dx);
        RIA.rw0 = 1;                                /* x is 272 and up */
        RIA.rw0 = SCREEN_TOP + 106;
        RIA.rw0 = 0;
        RIA.rw0 = (unsigned char)((XRAM_KEYS + k * sizeof(img16_t)) & 0xFF);
        RIA.rw0 = (unsigned char)((XRAM_KEYS + k * sizeof(img16_t)) >> 8);
        RIA.rw0 = (unsigned char)(XRAM_PAL_FG & 0xFF);
        RIA.rw0 = (unsigned char)(XRAM_PAL_FG >> 8);
    }
}

/* ---- sprites ---------------------------------------------------------- */

void plat_display_player_sprite(void)
{
    view_player();
}

/* The selection cursor over a window cell: 2.1's icons, picked by CURSOR_ON --
 * 1 the arrows, for placing an item, 2 the magnifier, for searching, 3 the
 * hand, for moving -- 28x28 at 2bpp in palette b, with no frame, their top
 * left two pixels right of the cell's and one down, where 2.1 puts them. dx
 * and dy move it from there while the magnifier circles. Shake leaves it
 * still. */
static void cursor_at(signed char dx, signed char dy)
{
    int x;
    unsigned char y;
    unsigned image;
    /* Over the live map the cursor would mark a window nobody can see: the
     * Amiga does not show it there, and neither does this. */
    if (!CURSOR_ON || livemap_on) {
        hud_hide(HUD_CURSOR);
        return;
    }
    x = CURSOR_X * TILE_PX + 2 + dx;
    y = (unsigned char)(SCREEN_TOP + CURSOR_Y * TILE_PX + 1 + dy);
    image = XRAM_CURSOR + (unsigned)(CURSOR_ON - 1) * sizeof(img28x28_t);
    RIA.addr0 = HUD_SPRITE(HUD_CURSOR);
    RIA.step0 = 1;
    RIA.rw0 = (unsigned char)(x & 0xFF);
    RIA.rw0 = (unsigned char)(x >> 8);
    RIA.rw0 = y;
    RIA.rw0 = 0;
    RIA.rw0 = (unsigned char)(image & 0xFF);
    RIA.rw0 = (unsigned char)(image >> 8);
    RIA.rw0 = (unsigned char)(XRAM_PAL_B & 0xFF);
    RIA.rw0 = (unsigned char)(XRAM_PAL_B >> 8);
}

void plat_reverse_tile(void)
{
    cursor_at(0, 0);
}

/* Ticks between the circling magnifier's steps, as 2.1's code asks. 2.1 loses
 * some of its ticks (below), which by its cycle counts makes its own pace
 * nearer one step in ten. */
#define GLASS_TICKS 5

/* SEARCH_GLASS_CIRCLE, 2.1's $4CE9, which SEARCH_OBJECT calls before each
 * BACKGROUND_TASKS while its dots go down: the magnifier circles its cell
 * clockwise from the top, four pixels out, a step every GLASS_TICKS ticks.
 * The offsets are 2.1's tables at $4D4F and $4D57 less 4. The step and the
 * count are never reset, as 2.1's $4D4D and $4D4E are not, so a search picks
 * the circle up where the last one left it.
 *
 * DELIBERATE CHANGE. 2.1 counts a tick when it finds BGTIMER1 set, and
 * BACKGROUND_TASKS, called next, clears it, so a tick that comes between the
 * two reads goes uncounted. Here BACKGROUND_TASKS starts with VIEW_HOOK, which
 * makes that gap most of the loop, and the magnifier would hardly move; so
 * this counts the new frames it sees instead, which is every tick the game
 * does not overrun. */
void plat_search_glass(void)
{
    static const signed char dx[8] = { 0, 3, 4, 3, 0, -3, -4, -3 };
    static const signed char dy[8] = { -4, -3, 0, 3, 4, 3, 0, -3 };
    static unsigned char frame, ticks, step;
    unsigned char f = IRQ_FRAME;

    if (f == frame)
        return;
    frame = f;
    if (++ticks != GLASS_TICKS)
        return;
    ticks = 0;
    cursor_at(dx[step], dy[step]);
    step = (unsigned char)((step + 1) & 7);
}

/* Weapon and item panels. The selection rules are 2.1's PRESELECT_* and
 * DISPLAY_*: if nothing is selected, take the first thing in inventory. A
 * weapon that has run out falls back the same way; an item steps on to the
 * next one in stock, and past the magnet starts again from the first. With
 * nothing to show, the Amiga clears the panel, digits and all. */
void plat_display_weapon(void)
{
    if (SELECTED_WEAPON == 1 && !AMMO_PISTOL)
        SELECTED_WEAPON = 0;
    if (SELECTED_WEAPON == 2 && !AMMO_PLASMA)
        SELECTED_WEAPON = 0;
    if (!SELECTED_WEAPON)
        SELECTED_WEAPON = AMMO_PISTOL ? 1 : AMMO_PLASMA ? 2 : 0;

    if (!SELECTED_WEAPON) {
        hud_hide(HUD_WEAPON);
        fill_cells(37, 4, 32, CLEAR, 3);
        return;
    }
    hud_picture(HUD_WEAPON, &weapon_shown,
                IMG_ITEMS + (SELECTED_WEAPON - 1) * 2u, XRAM_WEAPON,
                sizeof(img48x24_t), 272, SCREEN_TOP + 13);
    decwrite(37, 4, SELECTED_WEAPON == 1 ? AMMO_PISTOL : AMMO_PLASMA, TEXT_WHITE);
}

void plat_display_item(void)
{
    /* The Amiga's pictures run pistol, plasma, medkit, EMP, magnet, time bomb;
     * SELECTED_ITEM runs bomb, EMP, medkit, magnet. */
    static const unsigned char picture_for[5] = { 0, 5, 3, 2, 4 };
    unsigned char qty;

    /* 1 bomb, 2 EMP, 3 medkit, 4 magnet -- the order CYCLE_ITEM walks.
     *
     * 2.1's DISPLAY_ITEM, $5291, and the pre-release's too. The port used to
     * fall back to the first item in stock instead, which neither does: with
     * a bomb and a medkit and no EMP, F2 from the bomb went back to the bomb,
     * so the medkit could never be chosen, and the last EMP used went back to
     * the bomb as well. */
    for (;;) {
        if (!SELECTED_ITEM)             /* PRESELECT_ITEM, $5349 */
            SELECTED_ITEM = INV_BOMBS ? 1 : INV_EMP ? 2 : INV_MEDKIT ? 3
                          : INV_MAGNET ? 4 : 0;
        switch (SELECTED_ITEM) {
        case 1: qty = INV_BOMBS;  break;
        case 2: qty = INV_EMP;    break;
        case 3: qty = INV_MEDKIT; break;
        case 4: qty = INV_MAGNET; break;
        default: qty = 0;         break;
        }
        if (!SELECTED_ITEM || qty)
            break;
        /* None of this one: the next, and past the magnet, DSIT09, nothing
         * selected, which preselects again. */
        if (++SELECTED_ITEM > 4)
            SELECTED_ITEM = 0;
    }

    if (!SELECTED_ITEM) {
        hud_hide(HUD_ITEM);
        fill_cells(37, 10, 32, CLEAR, 3);
        return;
    }
    hud_picture(HUD_ITEM, &item_shown,
                IMG_ITEMS + picture_for[SELECTED_ITEM] * 2u, XRAM_ITEM,
                sizeof(img48x24_t), 272, SCREEN_TOP + 54);
    decwrite(37, 10, qty, TEXT_WHITE);
}

void __fastcall__ plat_play_sound(unsigned char effect)
{
    PLAY_SOUND(effect);
}

/* The elevator panel. The AI has already printed the two message lines; this
 * draws the floor numbers along the console's bottom row, inverts the one the
 * player is on, and lets left and right pick another.
 *
 * Choosing a floor moves the player immediately -- there is no travel -- by
 * finding the elevator unit whose UNIT_C matches, which is what
 * ELEVATOR_FIND_XY does. The window offsets look inconsistent at a glance:
 * x - 5 but y - 4. They are not. The original decrements the player's Y after
 * reading it, so the player ends up one square above the elevator and the
 * window four above that, which is the same viewport row 3 every other move
 * puts him on.
 */
#define ELEV_ROW      CON_BOTTOM
#define ELEV_COL      6

static unsigned char elevator_max, elevator_floor;

/* ELEVATOR_INVERT: the floor's glyph with its top bit flipped, which the font
 * draws inverted. */
static void elevator_invert(void)
{
    unsigned char g;
    RIA.addr0 = CELL(ELEV_COL + elevator_floor - 1, ELEV_ROW);
    RIA.step0 = 0;
    g = RIA.rw0;
    RIA.rw0 = (unsigned char)(g ^ 0x80);
    RIA.step0 = 1;
}

/* Put the player on the chosen floor. */
static void elevator_find_xy(void)
{
    unsigned char i;
    for (i = 32; i < 48; i++) {
        if (UNIT_TYPE[i] != 19 || UNIT_C[i] != elevator_floor)
            continue;
        UNIT_LOC_X[0] = UNIT_LOC_X[i];
        MAP_WINDOW_X = (unsigned char)(UNIT_LOC_X[i] - 5);
        UNIT_LOC_Y[0] = (unsigned char)(UNIT_LOC_Y[i] - 1);
        MAP_WINDOW_Y = (unsigned char)(UNIT_LOC_Y[i] - 4);
        view_request();
        plat_play_sound(SFX_BEEP2);
        return;
    }
}

void plat_elevator_select(void)
{
    unsigned char i, key;

    view_request();
    elevator_max = UNIT_D[UNIT];
    elevator_floor = UNIT_C[UNIT];

    /* The floors, as digits from 1. */
    RIA.addr0 = CELL(ELEV_COL, ELEV_ROW);
    RIA.step0 = 2;
    for (i = 0; i < elevator_max; i++)
        RIA.rw0 = (unsigned char)(0x31 + i);    /* screen code for '1' */
    RIA.step0 = 1;
    elevator_invert();

    /* ELS5 is a tight poll -- no BACKGROUND_TASKS -- so the world holds still
     * while a floor is being chosen. This used to run the AI round this loop,
     * which let robots move and shoot while the panel was up. The keyboard is
     * scanned by the interrupt now, so waiting here costs nothing. */
    for (;;) {
        view_idle();
        key = plat_getin();             /* SELS5: which answers the pad too */
        if (!key)
            continue;

        if (key == 0x9D && pad_held(PAD_SELECT)) {       /* the pad's map */
            livemap_toggle();
            plat_clear_key_buffer();
        } else if (key == 0x11 && pad_held(PAD_SELECT)) { /* and its robots */
            livemap_robot_dots();
            plat_clear_key_buffer();
        } else if (key == 0x9D || key == KEY_MOVE_UP[2]) {      /* left */
            if (elevator_floor > 1) {
                elevator_invert();
                elevator_floor--;
                elevator_invert();
                elevator_find_xy();
            }
        } else if (key == 0x1D || key == KEY_MOVE_UP[3]) {      /* right */
            if (elevator_floor < elevator_max) {
                elevator_invert();
                elevator_floor++;
                elevator_invert();
                elevator_find_xy();
            }
        } else if (key == 0x11 || key == KEY_MOVE_UP[1]) {      /* down: leave */
            elevator_invert();
            plat_scroll_info();
            plat_scroll_info();
            plat_scroll_info();
            plat_clear_key_buffer();
            return;
        } else if (key == 9) {          /* TAB, after the keys, as in play */
            livemap_toggle();
            plat_clear_key_buffer();
        } else if (key == KEY_SHIFT_TAB) {
            livemap_robot_dots();
            plat_clear_key_buffer();
        }
    }
}

/* SNES_CONTROLER_READ, from x16Robots.ASM 778.
 *
 * The X16 asks the KERNAL for a joystick word and unpacks it into twelve bytes
 * -- B, Y, SELECT, START, UP, DOWN, LEFT, RIGHT, A, X, L, R -- keeping the
 * previous read alongside so it can tell a press from a hold. A press sets the
 * matching NEW_ latch and leaves it set; whichever piece of code acts on it
 * clears it. That is the contract the ported assembly expects: items.s calls
 * this from MOVE_OBJECT and USER_SELECT_OBJECT and then reads NEW_ directly.
 *
 * The RIA keeps the same twelve facts in XRAM, continuously updated, so this
 * reads four bytes of the player-one block instead of calling anything:
 * DPAD holds the directions in bits 0-3 and a connected flag in bit 7, BTN0 the
 * face and shoulder buttons, BTN1 select and start.
 *
 * FACE BUTTONS ARE MAPPED BY POSITION, NOT BY NAME. The original fires in the
 * direction of the button under your thumb -- SNES Y is the left button and
 * fires left, A is the right one and fires right, X is the top, B is the
 * bottom. The RIA reports buttons by label, and a label sits in a different
 * place depending on the pad: DPAD bits 4-5 say which convention this one uses,
 * and an "Eastern BA" pad has A and B the other way round from a "Western AB"
 * one. Mapping by name would fire left when you press the top button on half
 * the pads in the world, so the layout byte picks the positions.
 *
 * BOTH STICKS ARE MERGED IN. The RIA reduces each to four direction bits in
 * STICKS, so the left one joins the d-pad and the right one joins the face
 * buttons where each points. The pad becomes twin-stick and nothing above this
 * function knows: the twelve latches are still the twelve the X16 unpacked. */

static unsigned char pad_now[12], pad_last[12], pad_present;

void plat_gamepad_read(void)
{
    unsigned char i, dpad, sticks, btn0, btn1, bottom, right, left, top;

    for (i = 0; i < 12; i++)
        pad_last[i] = pad_now[i];

    RIA.addr0 = XRAM_GAMEPAD;           /* player one */
    RIA.step0 = 1;
    dpad = RIA.rw0;
    sticks = RIA.rw0;
    btn0 = RIA.rw0;
    btn1 = RIA.rw0;

    pad_present = (dpad & GAMEPAD_FEAT_CONNECTED) != 0;
    if (!pad_present) {
        for (i = 0; i < 12; i++)
            pad_now[i] = 0;
        return;                         /* no pad: nothing held, nothing new */
    }

    if ((dpad & GAMEPAD_FEAT_TYPE_MASK) == GAMEPAD_TYPE_EASTERN) {
        bottom = 0x02; right = 0x01;    /* B, A */
        left   = 0x10; top   = 0x08;    /* Y, X */
    } else {
        bottom = 0x01; right = 0x02;    /* A/Cross, B/Circle */
        left   = 0x08; top   = 0x10;    /* X/Square, Y/Triangle */
    }

    /* The left stick walks, alongside the d-pad: STICKS bits 0-3 are the same
     * four directions already reduced to bits, so this is an OR rather than a
     * threshold to pick. */
    pad_now[PAD_UP]     = (dpad & 0x01) || (sticks & 0x01);
    pad_now[PAD_DOWN]   = (dpad & 0x02) || (sticks & 0x02);
    pad_now[PAD_LEFT]   = (dpad & 0x04) || (sticks & 0x04);
    pad_now[PAD_RIGHT]  = (dpad & 0x08) || (sticks & 0x08);

    /* The right stick fires, alongside the face buttons -- bits 4-7, the same
     * four directions again. The face buttons already fire in the direction
     * they sit in, so the stick joins each one where it points and the pad ends
     * up twin-stick without the game knowing anything changed. */
    pad_now[PAD_X]      = (btn0 & top)    || (sticks & 0x10);   /* fire up    */
    pad_now[PAD_B]      = (btn0 & bottom) || (sticks & 0x20);   /* fire down  */
    pad_now[PAD_Y]      = (btn0 & left)   || (sticks & 0x40);   /* fire left  */
    pad_now[PAD_A]      = (btn0 & right)  || (sticks & 0x80);   /* fire right */

    pad_now[PAD_L]      = (btn0 & 0x40) != 0;   /* L1 */
    pad_now[PAD_R]      = (btn0 & 0x80) != 0;   /* R1 */
    pad_now[PAD_SELECT] = (btn1 & 0x04) != 0;
    pad_now[PAD_START]  = (btn1 & 0x08) != 0;

    for (i = 0; i < 12; i++)
        if (!NEW_BUTTONS[i] && pad_now[i] && !pad_last[i])
            NEW_BUTTONS[i] = 1;
}

/* SNES_SELECT and friends: whether a button is down now, as opposed to whether
 * it has just been pressed. SELECT is used as a shift key rather than an
 * action, so the code that reads it wants the hold, not the edge. */
/* Whether a pad is plugged into player one, as of the last read. The main loop
 * asks before running the pad's pass at all: that pass ends by clearing
 * KEY_FAST when no direction is held, which is the pad's own business and would
 * otherwise reset the keyboard's repeat acceleration on every frame. */
unsigned char plat_pad_present(void)
{
    return pad_present;
}

unsigned char __fastcall__ pad_held(unsigned char button)
{
    return pad_now[button];
}

/* Whether a button went down in the last read, as opposed to a NEW_BUTTONS
 * latch, which can be left over from a step taken a moment ago. */
unsigned char __fastcall__ pad_pressed(unsigned char button)
{
    return pad_now[button] && !pad_last[button];
}

/* SC02 zeroes SNES_UP..SNES_RIGHT before reading again, which makes a direction
 * that is still held look like a fresh press and is how a held d-pad repeats.
 * Those four live here rather than in the game's variables, so the main loop
 * asks for them to be forgotten instead of writing them. */
void plat_gamepad_forget_dirs(void)
{
    pad_now[PAD_UP] = pad_now[PAD_DOWN] = 0;
    pad_now[PAD_LEFT] = pad_now[PAD_RIGHT] = 0;
}
