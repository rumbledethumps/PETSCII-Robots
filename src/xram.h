#ifndef PETSCII_XRAM_H
#define PETSCII_XRAM_H

/* The XRAM working set, as the SDK lays it out: the structure of each device,
 * copied from the manual, and xram_layout_t, whose members the compiler places.
 * Each XRAM_ symbol is the address of one member. The build reads them from
 * robots.sym for rp6502_asset(XRAM(...)), and the emulator tests use the same
 * names, so an address is written down exactly once.
 *
 * The screen is the Amiga version's 320x200, on the 320x200 canvas. The playfield is 77 mode 5 sprites over a 13x9 cache of 24x24 tiles,
 * and the cache shares its 33,696 bytes with the intro and game-over pictures
 * and the live map, which are only ever shown while the playfield is not.
 */

#include <rp6502.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ---- the canvas, vga.rst "Key Registers" ---------------------------- */

#define xreg_vga_canvas(...) xreg(0x1, 0x0, 0x00, __VA_ARGS__)

#define CANVAS_CONSOLE 0
#define CANVAS_320X240 1
#define CANVAS_320X180 2
#define CANVAS_640X480 3
#define CANVAS_640X360 4
#define CANVAS_320X200 5
#define CANVAS_640X400 6

/* ---- mode 1, vga.rst "Mode 1: Character" ---------------------------- */

#define xreg_vga_mode1(...) xreg(0x1, 0x0, 0x01, 1, __VA_ARGS__)

#define MODE1_1BPP 0x00
#define MODE1_4BPPR 0x01
#define MODE1_4BPP 0x02
#define MODE1_8BPP 0x03
#define MODE1_16BPP 0x04

#define MODE1_8X8 0x00
#define MODE1_8X16 0x08

#define MODE1_FG_BG(fg, bg) ((uint8_t)(((fg) << 4) | (bg)))
#define MODE1_BG_FG(bg, fg) ((uint8_t)(((bg) << 4) | (fg)))

typedef struct
{
    bool x_wrap;
    bool y_wrap;
    int16_t x_pos_px;
    int16_t y_pos_px;
    int16_t width_chars;
    int16_t height_chars;
    uint16_t xram_data_ptr;
    uint16_t xram_palette_ptr;
    uint16_t xram_font_ptr;
} mode1_config_t; /* layout */

typedef struct
{
    uint8_t glyph_code;
    uint8_t bg_fg_index;
} mode1_4bpp_data_t; /* layout */

/* ---- mode 2, vga.rst "Mode 2: Tile" -------------------------------- */

#define xreg_vga_mode2(...) xreg(0x1, 0x0, 0x01, 2, __VA_ARGS__)

#define MODE2_1BPP 0x00
#define MODE2_2BPP 0x01
#define MODE2_4BPP 0x02
#define MODE2_8BPP 0x03

#define MODE2_8X8 0x00
#define MODE2_16X16 0x08

#define MODE2_X_TRIM(cols) ((cols) << 4)
#define MODE2_Y_TRIM(rows) ((rows) << 8)

#define MODE2_TILE(bpp, size)                 \
    struct                                    \
    {                                         \
        struct                                \
        {                                     \
            uint8_t cols[(size) * (bpp) / 8]; \
        } rows[size];                         \
    }

typedef struct
{
    bool x_wrap;
    bool y_wrap;
    int16_t x_pos_px;
    int16_t y_pos_px;
    int16_t width_tiles;
    int16_t height_tiles;
    uint16_t xram_data_ptr;
    uint16_t xram_palette_ptr;
    uint16_t xram_tile_ptr;
} mode2_config_t; /* layout */

/* ---- mode 3, vga.rst "Mode 3: Bitmap" ------------------------------- */

#define xreg_vga_mode3(...) xreg(0x1, 0x0, 0x01, 3, __VA_ARGS__)

#define MODE3_1BPP 0x00
#define MODE3_2BPP 0x01
#define MODE3_4BPP 0x02
#define MODE3_8BPP 0x03
#define MODE3_16BPP 0x04

#define MODE3_REVERSE_BITS 0x08

typedef struct
{
    bool x_wrap;
    bool y_wrap;
    int16_t x_pos_px;
    int16_t y_pos_px;
    int16_t width_px;
    int16_t height_px;
    uint16_t xram_data_ptr;
    uint16_t xram_palette_ptr;
} mode3_config_t; /* layout */

/* ---- mode 5, vga.rst "Mode 5: Sprite" ------------------------------- */

#define xreg_vga_mode5(...) xreg(0x1, 0x0, 0x01, 5, __VA_ARGS__)

#define MODE5_1BPP 0x00
#define MODE5_2BPP 0x01
#define MODE5_4BPP 0x02
#define MODE5_8BPP 0x03

#define MODE5_8X8 0x00
#define MODE5_16X16 0x08
#define MODE5_32X32 0x10
#define MODE5_64X64 0x18
#define MODE5_128X128 0x20
#define MODE5_256X256 0x28
#define MODE5_512X512 0x30
#define MODE5_CUSTOM 0x38

#define MODE5_HFLIP 0x10
#define MODE5_VFLIP 0x20
#define MODE5_HDOUBLE 0x40
#define MODE5_VDOUBLE 0x80

#define MODE5_IMAGE(bpp, size)                \
    struct                                    \
    {                                         \
        struct                                \
        {                                     \
            uint8_t cols[(size) * (bpp) / 8]; \
        } rows[size];                         \
    }

#define MODE5_SIZE(width, height) \
    ((((height) / 4 - 1) << 4) | ((width) / 4 - 1))

#define MODE5_CUSTOM_IMAGE(bpp, width, height)       \
    struct                                           \
    {                                                \
        struct                                       \
        {                                            \
            uint8_t cols[((width) * (bpp) + 7) / 8]; \
        } rows[height];                              \
    }

#define MODE5_PALETTE_CHECK(type) \
    _Static_assert(sizeof(type) / sizeof(uint16_t) <= 512, #type " holds more than 512 colors.")

typedef struct
{
    int16_t x_pos_px;
    int16_t y_pos_px;
    uint16_t xram_sprite_ptr;
    uint16_t palette_ptr;
} mode5_sprite_t; /* layout */

typedef struct
{
    int16_t x_pos_px;
    int16_t y_pos_px;
    uint16_t xram_sprite_ptr;
    uint16_t palette_ptr;
    uint8_t width_height;
    uint8_t attributes;
} mode5_csprite_t; /* layout */

/* ---- keyboard, ria.rst "Keyboard" ----------------------------------- */

#define KEYBOARD_NO_KEY 0
#define KEYBOARD_NUM_LOCK 1
#define KEYBOARD_CAPS_LOCK 2
#define KEYBOARD_SCROLL_LOCK 3

#define KEYBOARD_PRESSED(keys, code) ((keys)[(code) >> 3] & (1 << ((code) & 7)))

#define xreg_ria_keyboard(...) xreg(0x0, 0x0, 0x00, __VA_ARGS__)

typedef struct
{
    uint8_t keys[32];
} keyboard_t; /* layout */

/* ---- gamepads, ria.rst "Gamepad" ------------------------------------ */

#define GAMEPAD_PLAYERS 4

#define GAMEPAD_DPAD_UP 0x01
#define GAMEPAD_DPAD_DOWN 0x02
#define GAMEPAD_DPAD_LEFT 0x04
#define GAMEPAD_DPAD_RIGHT 0x08

#define GAMEPAD_FEAT_TYPE_MASK 0x30
#define GAMEPAD_TYPE_UNKNOWN 0x00
#define GAMEPAD_TYPE_WESTERN 0x10
#define GAMEPAD_TYPE_EASTERN 0x20
#define GAMEPAD_TYPE_PLAYSTATION 0x30
#define GAMEPAD_FEAT_STICKS 0x40
#define GAMEPAD_FEAT_CONNECTED 0x80

#define GAMEPAD_LSTICK_UP 0x01
#define GAMEPAD_LSTICK_DOWN 0x02
#define GAMEPAD_LSTICK_LEFT 0x04
#define GAMEPAD_LSTICK_RIGHT 0x08
#define GAMEPAD_RSTICK_UP 0x10
#define GAMEPAD_RSTICK_DOWN 0x20
#define GAMEPAD_RSTICK_LEFT 0x40
#define GAMEPAD_RSTICK_RIGHT 0x80

#define GAMEPAD_BTN0_A 0x01
#define GAMEPAD_BTN0_B 0x02
#define GAMEPAD_BTN0_C 0x04
#define GAMEPAD_BTN0_X 0x08
#define GAMEPAD_BTN0_Y 0x10
#define GAMEPAD_BTN0_Z 0x20
#define GAMEPAD_BTN0_L1 0x40
#define GAMEPAD_BTN0_R1 0x80

#define GAMEPAD_BTN1_L2 0x01
#define GAMEPAD_BTN1_R2 0x02
#define GAMEPAD_BTN1_SELECT 0x04
#define GAMEPAD_BTN1_START 0x08
#define GAMEPAD_BTN1_HOME 0x10
#define GAMEPAD_BTN1_L3 0x20
#define GAMEPAD_BTN1_R3 0x40

#define xreg_ria_gamepad(...) xreg(0x0, 0x0, 0x02, __VA_ARGS__)

typedef struct
{
    uint8_t dpad;
    uint8_t sticks;
    uint8_t btn0;
    uint8_t btn1;
    int8_t lx;
    int8_t ly;
    int8_t rx;
    int8_t ry;
    uint8_t l2;
    uint8_t r2;
} gamepad_player_t;

typedef struct
{
    gamepad_player_t player[GAMEPAD_PLAYERS];
} gamepad_t; /* layout */

/* ---- OPL2, ria.rst "Yamaha OPL2 FM Sound Generator" ------------------ */

#define xreg_ria_opl(...) xreg(0x0, 0x1, 0x01, __VA_ARGS__)

typedef struct
{
    uint8_t reg[256];
} opl_t; /* layout */

/* After the XRAM_ names: OPL_PAGE_CHECK(XRAM_OPL); */
#define OPL_PAGE_CHECK(addr) \
    _Static_assert((addr) % 256 == 0, #addr " does not start a page.")

/* ---- this game ------------------------------------------------------- */

/* The Amiga screen is 320x200, and so is the canvas, 16:10, so nothing is
 * letterboxed. Every position is from SCREEN_TOP, which was 20 when the screen
 * sat in the middle of a 320x240 canvas, and is kept so that one number places
 * the screen if it ever has to sit on another. */
#define SCREEN_TOP      0
#define SCREEN_H        200

/* The text plane: 40x25 cells of 8x8, over everything. */
#define SCR_COLS        40
#define SCR_ROWS        25
#define SCR_STRIDE      (SCR_COLS * 2)          /* 2 bytes per cell, 4-bit colour */

/* The playfield: 11x7 tiles of 24x24 at the top left of the screen, so 264x168.
 * The player is always at window cell (5,3). */
#define MAP_WIN_TILES_W 11
#define MAP_WIN_TILES_H 7
#define MAP_WIN_CELLS   77
#define TILE_PX         24

#define MAP_W           128
#define MAP_H           64

/* The tile cache: 13x9 slots, the window plus a one-tile margin all round, so a
 * step in any direction finds the tiles it brings into view already loaded. A
 * map cell (mx,my) lives in slot ((my+1) mod 9) * 13 + ((mx+1) mod 13), the way
 * mode 2 wraps a map: scrolling moves which slots the sprites point at, and
 * nothing in the cache. */
#define CACHE_W         13
#define CACHE_H         9
#define CACHE_SLOTS     117

/* The plane 0 sprite array: the 77 playfield tiles in row-major order, then a
 * sprite for each unit the window shows, then the player on top. */
#define PF_UNITS        77
#define PF_UNIT_COUNT   32
#define PF_PLAYER       109
#define PF_COUNT        110

/* The plane 1 sprite array: the HUD's pictures and the cursor, drawn last. */
#define HUD_WEAPON      0
#define HUD_ITEM        1
#define HUD_HEALTH      2
#define HUD_KEY0        3
#define HUD_CURSOR      6
#define HUD_COUNT       7

/* Off-screen parks a sprite: mode 5 has no enable bit, and nothing is drawn
 * below the last line a mode is programmed on. */
#define SPR_PARKED_Y    240

/* The player never moves on screen: the window follows him. */
#define PLAYER_SPR_X    (5 * TILE_PX)
#define PLAYER_SPR_Y    (SCREEN_TOP + 3 * TILE_PX)

/* PLAYER_DIRECTION values, as the X16 uses them. */
#define FACE_UP     0
#define FACE_DOWN   3
#define FACE_LEFT   6
#define FACE_RIGHT  9
#define FACE_DEAD  12

typedef MODE5_CUSTOM_IMAGE(4, 24, 24) img24_t;      /* 288 bytes */
typedef MODE5_CUSTOM_IMAGE(4, 48, 24) img48x24_t;   /* 576: weapon, item */
typedef MODE5_CUSTOM_IMAGE(4, 48, 52) img48x52_t;   /* 1248: health */
typedef MODE5_CUSTOM_IMAGE(4, 16, 16) img16_t;      /* 128: keys */
typedef MODE5_CUSTOM_IMAGE(2, 28, 28) img28x28_t;   /* 196: the cursor */
typedef MODE2_TILE(4, 8) hud_tile_t;                /* 32 */

#define IMG24_BYTES     288

/* What the playfield's memory holds depends on the screen. */
typedef union
{
    img24_t cache[CACHE_SLOTS];
    uint8_t picture[SCREEN_H][160];                 /* intro, game over */
    uint8_t livemap[MAP_H * 2][MAP_W];              /* src/livemap.s */
} view_t;

/* Every palette is derived at run time from the Amiga's 4-bit RGB bases; see
 * src/palette.c. */
typedef struct
{
    uint16_t game[16];      /* all opaque: tiles, the live map           */
    uint16_t fg[16];        /* 0 transparent: shots, explosions, HUD      */
    uint16_t a[16];         /* 0 transparent, 8 black: player, text, HUD  */
    uint16_t b[16];         /* 0 transparent, 1 black, 2 white: robots    */
    uint16_t pic[16];       /* the intro or game-over picture, opaque     */
    uint16_t pic_text[16];  /* that, with 0 transparent and 8 black       */
} palettes_t; /* layout */
MODE5_PALETTE_CHECK(palettes_t);

/* The probe block that tests read; see probe.h. */
typedef struct
{
    uint8_t bytes[32];
} probe_t; /* layout */

typedef struct
{
    view_t view;
    img24_t anim[24];                               /* animated tiles      */
    img24_t units[38];                              /* robots, shots, ...  */
    img24_t player[2];                              /* shown, and loading  */
    img24_t blank;                                  /* zeros: a black tile */
    img48x24_t weapon;
    img48x24_t item;
    img48x52_t health;
    img16_t keys[3];
    img28x28_t cursor[3];                           /* use, search, move   */
    hud_tile_t hud_tiles[72];
    uint8_t hud_map[SCR_ROWS][SCR_COLS];            /* mode 2, the frame   */
    mode1_4bpp_data_t chars[SCR_ROWS][SCR_COLS];    /* mode 1, the text    */
    uint8_t font[8][256];                           /* row-major           */
    mode5_csprite_t pf[PF_COUNT];
    mode5_csprite_t hud[HUD_COUNT];
    palettes_t pal;
    mode2_config_t cfg_hud;
    mode1_config_t cfg_chars;
    mode3_config_t cfg_overlay;
    keyboard_t keyboard;
    gamepad_t gamepad;
    uint8_t free0[0xFD00u - 0xFC6Cu];
    opl_t opl;              /* a whole page; at $FF00 this struct would be
                               64 KB, which cc65's size_t cannot hold */
    probe_t probe;
} xram_layout_t;            /* $FE20-$FFFF is free too */

#define XRAM_VIEW       offsetof(xram_layout_t, view)
#define XRAM_ANIM       offsetof(xram_layout_t, anim)
#define XRAM_UNITS      offsetof(xram_layout_t, units)
#define XRAM_PLAYER     offsetof(xram_layout_t, player)
#define XRAM_BLANK      offsetof(xram_layout_t, blank)
#define XRAM_WEAPON     offsetof(xram_layout_t, weapon)
#define XRAM_ITEM       offsetof(xram_layout_t, item)
#define XRAM_HEALTH     offsetof(xram_layout_t, health)
#define XRAM_KEYS       offsetof(xram_layout_t, keys)
#define XRAM_CURSOR     offsetof(xram_layout_t, cursor)
#define XRAM_HUD_TILES  offsetof(xram_layout_t, hud_tiles)
#define XRAM_HUD_MAP    offsetof(xram_layout_t, hud_map)
#define XRAM_CHARS      offsetof(xram_layout_t, chars)
#define XRAM_FONT       offsetof(xram_layout_t, font)
#define XRAM_PF         offsetof(xram_layout_t, pf)
#define XRAM_HUD        offsetof(xram_layout_t, hud)
#define XRAM_PALETTES   offsetof(xram_layout_t, pal)
#define XRAM_PAL_GAME   (XRAM_PALETTES + offsetof(palettes_t, game))
#define XRAM_PAL_FG     (XRAM_PALETTES + offsetof(palettes_t, fg))
#define XRAM_PAL_A      (XRAM_PALETTES + offsetof(palettes_t, a))
#define XRAM_PAL_B      (XRAM_PALETTES + offsetof(palettes_t, b))
#define XRAM_PAL_PIC    (XRAM_PALETTES + offsetof(palettes_t, pic))
#define XRAM_PAL_PIC_TEXT (XRAM_PALETTES + offsetof(palettes_t, pic_text))
#define XRAM_CFG_HUD    offsetof(xram_layout_t, cfg_hud)
#define XRAM_CFG_CHARS  offsetof(xram_layout_t, cfg_chars)
#define XRAM_CFG_OVERLAY offsetof(xram_layout_t, cfg_overlay)
#define XRAM_KEYBOARD   offsetof(xram_layout_t, keyboard)
#define XRAM_GAMEPAD    offsetof(xram_layout_t, gamepad)
#define XRAM_PROBE      offsetof(xram_layout_t, probe)
#define XRAM_OPL        offsetof(xram_layout_t, opl)

OPL_PAGE_CHECK(XRAM_OPL);

/* The tests and the probe stay where they were; everything else packs below. */
_Static_assert(XRAM_PROBE == 0xFE00u, "probe moved");
_Static_assert(XRAM_OPL == 0xFD00u, "OPL2 moved");
_Static_assert(offsetof(xram_layout_t, free0) == 0xFC6Cu, "free0 is sized by hand");
_Static_assert(sizeof(img24_t) == IMG24_BYTES, "a 24x24 4bpp image");
_Static_assert(sizeof(img28x28_t) == 196, "a 28x28 2bpp image");

#define CELL(col, row)  (XRAM_CHARS + (row) * SCR_STRIDE + (col) * 2)
#define PF_SPRITE(i)    (XRAM_PF + (i) * sizeof(mode5_csprite_t))
#define HUD_SPRITE(i)   (XRAM_HUD + (i) * sizeof(mode5_csprite_t))

#endif
