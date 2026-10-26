/* PETSCII Robots for the RP6502.
 *
 * The presentation and I/O are new; the game logic under src/game/ is David
 * Murray's assembly converted to ca65, so movement, collision, item use and
 * every robot behave exactly as they do on the X16 rather than approximately.
 */
#include <fcntl.h>
#include <6502.h>
#include <rp6502.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "game/game.h"
#include "input.h"
#include "livemap.h"
#include "palette.h"
#include "platform.h"
#include "probe.h"
#include "sound.h"
#include "view.h"
#include "xram.h"

static unsigned char frame_counter;

/* Frames since the game loop started, as opposed to frame_counter which wraps
 * at 256 for the probe. Only used to announce two checkpoints on the console.
 *
 * Tests need a reference point that does not depend on how long booting took.
 * Loading the assets goes through the host filesystem, and that is not the same
 * number of frames on every machine. Announcing a frame number gives the
 * harness something to synchronise on that the game's own clock defines. */
static unsigned frames_total;

/* Set once the first level is loaded; until then unit 0 is whatever RAM held. */
static unsigned char played;

static void die(const char *what)
{
    view_quiesce();
    printf("\nERROR: %s\n", what);
    exit(1);
}

/* read() moves data through the 512-byte XSTACK, so it loops. */
static void slurp_fd(int fd, void *dst, unsigned len)
{
    unsigned got = 0;
    int n;
    while (got < len) {
        n = read(fd, (unsigned char *)dst + got, len - got);
        if (n <= 0)
            break;
        got += n;
    }
    if (got != len)
        die("short read");
}

static void slurp(const char *name, void *dst, unsigned len)
{
    int fd;
    view_quiesce();                     /* one RIA call at a time */
    fd = open(name, O_RDONLY);
    if (fd < 0)
        die(name);
    slurp_fd(fd, dst, len);
    close(fd);
}

static void load_tileset(void)
{
    int fd = open("ROM:tiles", O_RDONLY);
    if (fd < 0)
        die("ROM:tiles");
    slurp_fd(fd, DESTRUCT_PATH, 256);
    slurp_fd(fd, TILE_ATTRIB, 256);
    close(fd);
}

/* The Amiga's game screen frame: a 40x25 map of 8x8 tiles over the whole
 * screen, black where the playfield goes. It never changes. */
static const mode2_config_t cfg_hud = {
    false, false,
    0, SCREEN_TOP, SCR_COLS, SCR_ROWS,
    XRAM_HUD_MAP, XRAM_PAL_A, XRAM_HUD_TILES,
};

static const mode1_config_t cfg_chars = {
    false, false,
    0, SCREEN_TOP, SCR_COLS, SCR_ROWS,
    XRAM_CHARS, XRAM_PAL_A, XRAM_FONT,
};

/* The picture layer starts a screenful to the left, where it draws nothing. */
static const mode3_config_t cfg_overlay = {
    false, false,
    -320, SCREEN_TOP, 320, SCREEN_H,
    XRAM_VIEW, XRAM_PAL_PIC,
};

/* Every layer is programmed once, here, on the 200 lines of the Amiga screen,
 * and what follows only changes XRAM. From the back:
 *
 *   plane 0  the HUD frame (mode 2), then the playfield's sprites (mode 5):
 *            77 tiles, the units over them, the player on top
 *   plane 1  a picture (mode 3) -- the intro, the statistics, the live map --
 *            that hides the playfield when it is shown; then the HUD's
 *            pictures and the cursor (mode 5)
 *   plane 2  the text (mode 1), over everything
 */
static void video_init(void)
{
    /* Selecting a canvas clears every plane's programming and takes the
     * console away; it stays away until something asks for it back. */
    xreg_vga_canvas(CANVAS_320X200);

    xram0_write(XRAM_CFG_HUD, &cfg_hud, sizeof cfg_hud);
    xram0_write(XRAM_CFG_CHARS, &cfg_chars, sizeof cfg_chars);
    xram0_write(XRAM_CFG_OVERLAY, &cfg_overlay, sizeof cfg_overlay);
    plat_clear_text();
    pal_init();
    view_init();

    xreg_vga_mode2(MODE2_4BPP | MODE2_8X8, XRAM_CFG_HUD, 0,
                   SCREEN_TOP, SCREEN_TOP + SCREEN_H);
    xreg_vga_mode5(MODE5_CUSTOM, XRAM_PF, PF_COUNT, 0,
                   SCREEN_TOP, SCREEN_TOP + MAP_WIN_TILES_H * TILE_PX);
    xreg_vga_mode3(MODE3_4BPP, XRAM_CFG_OVERLAY, 1,
                   SCREEN_TOP, SCREEN_TOP + SCREEN_H);
    xreg_vga_mode5(MODE5_CUSTOM, XRAM_HUD, HUD_COUNT, 1,
                   SCREEN_TOP, SCREEN_TOP + SCREEN_H);
    xreg_vga_mode1(MODE1_4BPP | MODE1_8X8, XRAM_CFG_CHARS, 2,
                   SCREEN_TOP, SCREEN_TOP + SCREEN_H);
}

void update_probe(void)
{
    unsigned char i, robots = 0, visible = 0;
    unsigned sum = 0;
    for (i = 1; i < 28; i++) {
        if (UNIT_TYPE[i])
            robots++;
        /* Weighted so a robot swapping places with another still shows up. */
        sum += (unsigned)UNIT_TYPE[i] * 7u
             + (unsigned)UNIT_LOC_X[i] * 31u
             + (unsigned)UNIT_LOC_Y[i] * 131u;
    }
    for (i = 0; i < 77; i++)
        if (MAP_PRECALC[i])
            visible++;

    RIA.addr0 = XRAM_PROBE;
    RIA.step0 = 1;
    RIA.rw0 = PROBE_MAGIC_0;
    RIA.rw0 = PROBE_MAGIC_1;
    /* The AI signals both endings by changing the player's own type: 0 when he
     * is killed, 2 when DEMATERIALIZE finishes and the level is won. Reporting
     * both as "dead" made a win indistinguishable from a death to a test.
     * Back at the title the last game's ending stays visible. Before the first
     * game there is no unit 0 at all -- LEVELDATA is not cleared, and the
     * emulator fills it at random -- so the title says so. */
    RIA.rw0 = !played            ? PROBE_STATE_TITLE
            : UNIT_TYPE[0] == 1 ? PROBE_STATE_PLAYING
            : UNIT_TYPE[0] == 0 ? PROBE_STATE_DEAD
                                : PROBE_STATE_WON;
    RIA.rw0 = SELECTED_MAP;         /* 0..17, which level is loaded */
    RIA.rw0 = UNIT_LOC_X[0];
    RIA.rw0 = UNIT_LOC_Y[0];
    RIA.rw0 = UNIT_HEALTH[0];
    RIA.rw0 = robots;
    RIA.rw0 = RANDOM;
    RIA.rw0 = frame_counter;
    RIA.rw0 = MAP_WINDOW_X;
    RIA.rw0 = MAP_WINDOW_Y;
    RIA.rw0 = sum & 0xFF;
    RIA.rw0 = sum >> 8;
    RIA.rw0 = visible;
    RIA.rw0 = (unsigned char)(SELECTED_WEAPON | (SELECTED_ITEM << 4));
    RIA.rw0 = view_loads;
    RIA.rw0 = view_units;
    RIA.rw0 = ANIM_STATE;
    RIA.rw0 = view_pending();
    RIA.rw0 = view_blank;
    RIA.rw0 = view_overruns;
    RIA.rw0 = !livemap_on ? 0 : livemap_robots ? 2 : 1;
}

/* Whether there is music at all: F6 turns it off and on, and SHIFT+M in play.
 * It stays as set, through the intro and the endings too, as on the X16 and
 * the Amiga. */
unsigned char music_enabled = 1;

/* One of the four level songs, in turn by map, as both 2.1 and the DOS
 * version pick them. */
static void level_song(void)
{
    if (music_enabled)
        music_play(SONG_LEVEL + SELECTED_MAP % 4);
}

/* CHEATER, from x16Robots.ASM 1392, which the Amiga keeps on SHIFT+C: every
 * key card, a hundred of each kind of ammunition and item, and the pistol and
 * the first item selected. */
static void cheater(void)
{
    plat_play_sound(SFX_CYCLEWEAPON);
    KEYS = 7;
    AMMO_PISTOL = AMMO_PLASMA = 100;
    INV_BOMBS = INV_EMP = INV_MEDKIT = INV_MAGNET = 100;
    SELECTED_WEAPON = SELECTED_ITEM = 1;
    plat_display_keys();
    plat_display_weapon();
    plat_display_item();
}

/* F6, the Amiga's music key, and SHIFT+M, 2.1's: the level's song stops, or
 * starts again, and the console says which. */
static void toggle_music(void)
{
    music_enabled ^= 1;
    if (music_enabled) {
        level_song();
        SOURCE = MSG_MUSICON;
    } else {
        music_stop();
        SOURCE = MSG_MUSICOFF;
    }
    plat_print_info();
}

/* SHIFT+[ and SHIFT+], 2.1's effects volume, MG22-MG25 ($43F2-$4423): a step
 * down or up, 0 to 15, then the new volume as a hex digit on the console and a
 * beep at it, or the error sound if it was already at the end. See sound.s for
 * what the volume does to the effects. */
static void fx_volume(unsigned char up)
{
    unsigned char v = sfx_volume;

    /* DELIBERATE CHANGE. 2.1 sets no KEYTIMER here; its KEY_REPEAT does
     * nothing on the X16, so the keyboard's half-second typematic delay is
     * what keeps a tap to one step there. This KEY_REPEAT works, and with the
     * timer at or near 0 a tap would repeat on the next pass. 20, as firing
     * sets, makes a tap one step and a held key one every 20 frames. */
    KEYTIMER = 20;

    if (up) {
        if (v < 15)
            ++v;
    } else if (v)
        --v;
    if (v == sfx_volume) {
        plat_play_sound(SFX_ERROR);     /* MG25 */
        return;
    }
    sfx_volume = v;
    /* SHOW_NEW_VOLUME, $4424: '0'-'9', then the screen codes of 'a'-'f'. */
    MSG_VOLUME[17] = (unsigned char)(v < 10 ? 0x30 + v : v - 9);
    SOURCE = MSG_VOLUME;
    plat_print_info();
    plat_play_sound(SFX_BEEP2);
}

/* Animate the player one step and redraw him, as ANIMATE_PLAYER does. */
static void animate_player(void)
{
    UNIT_TILE[0] = 96;                  /* walking ends a transport's tile 97 */
    if (++PLAYER_ANIMATE == 4)          /* the Amiga's four walk frames */
        PLAYER_ANIMATE = 0;
    plat_display_player_sprite();
}

static void walk(unsigned char facing, void (*request)(void))
{
    /* The window would outrun the tile cache: the key goes back to wait for
     * the next pass. See view_ready. */
    if (!view_ready(facing)) {
        plat_unget_key();
        return;
    }
    PLAYER_DIRECTION = facing;
    UNIT = 0;
    MOVE_TYPE = MOVE_WALK;
    request();
    if (MOVE_RESULT == 1) {
        animate_player();
        CACULATE_AND_REDRAW();
    } else {
        /* Facing changes even when the way is blocked, as it does on the X16. */
        plat_display_player_sprite();
    }

    /* AFTER_MOVE's tail: the first repeat of a held direction waits 15 frames,
     * every one after that waits 6. Setting it here rather than in the input
     * layer is the original's arrangement and the reason it feels right -- the
     * pause is measured from the move actually happening, not from the poll.
     *
     * DELIBERATE CHANGE. The X16 code says 7, but on an X16 keyboard it never
     * takes effect: a held key walks at the keyboard's typematic rate, about
     * ten steps a second, and 2.1's gamepad path, AFTER_MOVE_SNES, uses 6. So
     * 6, ten steps a second, is what a 2.1 player walks at. */
    if (KEY_FAST) {
        KEYTIMER = 6;
    } else {
        KEYTIMER = 15;
        KEY_FAST = 1;
    }
}

static void cycle_weapon(void);
static void cycle_item(void);

/* PAUSE_GAME, from x16Robots.ASM 1412. Run/stop stops the clock, says so, and
 * offers to quit; N or run/stop again carries on. Y goes straight to the
 * statistics as a loss, as 2.1's PG6 does ($46B5: STZ TEMP_D / JMP GOM4),
 * with no GAME OVER box, no GOM0 and no AI, and the clock left stopped. The
 * pre-release killed the player instead and went the whole way round
 * through the death. Returns 1 when the game was quit, for the main loop to
 * go back to the title.
 *
 * The wait is a tight poll with no BACKGROUND_TASKS, so the world really is
 * stopped rather than merely quiet -- which it can be, now that the keyboard is
 * scanned by the interrupt. view_idle keeps the playfield's loads and vblank
 * work going, which runs no AI.
 */
static unsigned char pause_game(void)
{
    unsigned char key;

    plat_play_sound(SFX_BEEP2);
    CLOCK_ACTIVE = 0;
    plat_scroll_info();
    SOURCE = MSG_PAUSED;
    plat_print_info();
    plat_clear_key_buffer();

    for (;;) {
        view_idle();
        key = plat_getin();
        if (key == 3 || key == 'N')
            break;
        if (key == 'Y') {
            /* PG6. RP6502: type 0 as well, so the probe reports the quit
             * at the menu as a death; 2.1 leaves him type 1. */
            UNIT_TYPE[0] = 0;
            plat_endgame(0);
            return 1;
        }
    }

    plat_play_sound(SFX_BEEP2);
    plat_scroll_info();
    plat_scroll_info();
    plat_scroll_info();
    plat_clear_key_buffer();
    CLOCK_ACTIVE = 1;
    return 0;
}

/* The pad's own repeat acceleration. The original keeps one KEY_FAST because
 * only one control scheme is live at a time; here both are, and sharing it made
 * the keyboard slow whenever a pad was plugged in -- SC35 clears the flag when
 * no pad direction is held, which is every frame someone is using the keyboard,
 * so held keys never reached the fast rate. Measured at 8 squares in 120 frames
 * with a pad connected against 15 without. They are separate now. */
static unsigned char pad_fast;

/* A pad direction whose step is waiting for the tile cache. Its latch is kept
 * through SC02 rather than forgotten, so a tap shorter than the wait still
 * steps, as a key put back on the queue does. */
static unsigned char pad_wait;

/* AFTER_MOVE_SNES. Not the same as the keyboard's AFTER_MOVE: the repeats are
 * 6 frames rather than 7, and it clears the direction latches so a held d-pad
 * has to be seen again by the next read. */
static void walk_pad(unsigned char facing, void (*request)(void))
{
    /* As walk: not yet, and the direction stays latched to try again. */
    if (!view_ready(facing)) {
        pad_wait = 1;
        return;
    }
    PLAYER_DIRECTION = facing;
    UNIT = 0;
    MOVE_TYPE = MOVE_WALK;
    request();
    if (MOVE_RESULT == 1) {
        animate_player();
        CACULATE_AND_REDRAW();
    } else {
        plat_display_player_sprite();
    }

    if (pad_fast) {
        KEYTIMER = 6;
        NEW_BUTTONS[PAD_UP] = NEW_BUTTONS[PAD_DOWN] = 0;
        NEW_BUTTONS[PAD_LEFT] = NEW_BUTTONS[PAD_RIGHT] = 0;
    } else {
        KEYTIMER = 15;
        pad_fast = 1;
    }
}

/* SC01-SC75: one pass of the gamepad, when CONTROL says the pad is in use.
 *
 * Directions are gated on KEYTIMER and the buttons are not, which is why the
 * original jumps straight to SC40 while the timer is running -- you can keep
 * firing while a walk is still on its cooldown. SELECT is a shift key rather
 * than an action: held with left it opens the map, with L it cycles the item
 * and with R the weapon.
 */
static unsigned char gamepad_pass(void)
{
    unsigned char acted;

    plat_gamepad_read();
    if (!plat_pad_present()) {
        pad_wait = 0;
        return 0;
    }

    /* SELECT+LEFT turns the live map on or off and SELECT+DOWN its robots, as
     * the CD32 pad's PLAY+LEFT and PLAY+DOWN do: on the press itself, as TAB
     * and SHIFT+TAB do, not gated on KEYTIMER, so a tap is never missed, and
     * not repeated while held. Only a press in this read counts: a latch can
     * be left from a step, or kept for one that is waiting. */
    if (pad_held(PAD_SELECT) && !pad_wait
        && (pad_pressed(PAD_LEFT) || pad_pressed(PAD_DOWN))) {
        if (pad_pressed(PAD_LEFT))
            livemap_toggle();
        else
            livemap_robot_dots();
        plat_clear_key_buffer();
        return 1;
    }

    if (!KEYTIMER) {
        /* SC02: forget the directions on both sides and look again, so a
         * d-pad that is still held reads as a new press -- unless a step is
         * waiting, whose press is still latched. */
        if (!pad_wait) {
            NEW_BUTTONS[PAD_UP] = NEW_BUTTONS[PAD_DOWN] = 0;
            NEW_BUTTONS[PAD_LEFT] = NEW_BUTTONS[PAD_RIGHT] = 0;
            plat_gamepad_forget_dirs();
            plat_gamepad_read();
        }
        pad_wait = 0;

        if (NEW_BUTTONS[PAD_LEFT]) {
            /* LEFT still held with SELECT, read again by SC02: the map has
             * had its press, and SELECT keeps him from walking. */
            if (pad_held(PAD_SELECT)) {
                NEW_BUTTONS[PAD_LEFT] = 0;
                return 1;
            }
            walk_pad(FACE_LEFT, REQUEST_WALK_LEFT);
            return 1;
        }
        if (NEW_BUTTONS[PAD_RIGHT]) {
            walk_pad(FACE_RIGHT, REQUEST_WALK_RIGHT);
            return 1;
        }
        if (NEW_BUTTONS[PAD_UP]) {
            walk_pad(FACE_UP, REQUEST_WALK_UP);
            return 1;
        }
        if (NEW_BUTTONS[PAD_DOWN]) {
            if (pad_held(PAD_SELECT)) {     /* as LEFT: the map's robots */
                NEW_BUTTONS[PAD_DOWN] = 0;
                return 1;
            }
            walk_pad(FACE_DOWN, REQUEST_WALK_DOWN);
            return 1;
        }
        pad_fast = 0;                   /* SC35: nothing held, slow repeat again */
    }

    /* SC40: the buttons, which do not wait for the timer. The four face
     * buttons fire in the direction they sit in. */
    acted = 0;
    if (NEW_BUTTONS[PAD_Y]) { FIRE_LEFT();  NEW_BUTTONS[PAD_Y] = 0; acted = 1; }
    if (NEW_BUTTONS[PAD_A]) { FIRE_RIGHT(); NEW_BUTTONS[PAD_A] = 0; acted = 1; }
    if (NEW_BUTTONS[PAD_X]) { FIRE_UP();    NEW_BUTTONS[PAD_X] = 0; acted = 1; }
    if (NEW_BUTTONS[PAD_B]) { FIRE_DOWN();  NEW_BUTTONS[PAD_B] = 0; acted = 1; }

    if (NEW_BUTTONS[PAD_L]) {
        if (pad_held(PAD_SELECT))
            cycle_item();
        else
            SEARCH_OBJECT();
        NEW_BUTTONS[PAD_L] = 0;
        KEYTIMER = 15;
        acted = 1;
    }
    if (NEW_BUTTONS[PAD_R]) {
        if (pad_held(PAD_SELECT))
            cycle_weapon();
        else
            MOVE_OBJECT();
        NEW_BUTTONS[PAD_R] = 0;
        KEYTIMER = 15;
        acted = 1;
    }
    if (NEW_BUTTONS[PAD_START]) {
        USE_ITEM();
        NEW_BUTTONS[PAD_START] = 0;
        KEYTIMER = 15;
        acted = 1;
    }
    return acted;
}

/* CYCLE_WEAPON and CYCLE_ITEM: step to the next one and let the display
 * routine's rules sort out an empty slot. CYCLE_ITEM is 2.1's $5272 as it
 * reads: past the magnet is nothing, which preselects. */
static void cycle_weapon(void)
{
    plat_play_sound(SFX_CYCLEWEAPON);
    KEYTIMER = 20;
    SELECTED_WEAPON = (unsigned char)(SELECTED_WEAPON == 1 ? 2 : 1);
    plat_display_weapon();
}

static void cycle_item(void)
{
    plat_play_sound(SFX_CYCLEITEM);
    KEYTIMER = 20;
    if (++SELECTED_ITEM == 5)
        SELECTED_ITEM = 0;
    plat_display_item();
}

/* The interrupt's own C stack. It only has to hold the flash step's and the
 * keyboard scan's frames; a quarter of a page is generous and costs nothing
 * that matters. */
static unsigned char irq_stack[128];

/* Wait for the next game tick, which the VSYNC interrupt raises. The wait is
 * when the tile cache loads, and the tick starts with the vblank work that
 * shows what the last one drew; see src/view.c. */
static void wait_tick(void)
{
    view_wait();
    frame_counter++;
    ++frames_total;
}

/* A checkpoint for the tests: PROBE_AT_* into PROBE_CHECK. See probe.h. */
static void probe_check(unsigned char at)
{
    RIA.addr0 = XRAM_PROBE + PROBE_CHECK;
    RIA.rw0 = at;
}

/* A tick's state, then its checkpoint. The probe goes first so that a test
 * which sees PROBE_AT_AI60 reads the probe of that same pass. Counted from the
 * start of play, not from boot, so the checkpoints mean the same thing however
 * long someone sat on the menu. */
static void tick_report(void)
{
    update_probe();
    if (frames_total == 60)
        probe_check(PROBE_AT_AI60);
    else if (frames_total == 300)
        probe_check(PROBE_AT_AI300);
}

/* SET_CONTROLS, from x16Robots.ASM 4737. Custom keys ask the player for
 * thirteen of them; anything else takes the defaults. Called at boot and again
 * when START GAME is chosen, which is where the original calls it -- so
 * choosing custom keys and then starting is what brings the entry screen up. */
static void set_controls(void)
{
    unsigned char i;

    if (CONTROL == CONTROL_CUSTOM) {
        plat_set_custom_keys();
        return;
    }
    for (i = 0; i < 13; i++)
        KEY_MOVE_UP[i] = STANDARD_CONTROLS[i];
}

/* The intro screen: pick a level, a difficulty and a control scheme, then
 * start. Four options, on rows 1 to 4 of a text plane eight lines down, which
 * puts them in 2.1's rows 2 to 5; the selected one is INK 14, which pulses
 * through 2.1's greys as its colour did on the X16, and 2.1's credits fade in
 * and out below them. */
static void intro_screen(void)
{
    unsigned char key;

    MENUY = 0;
    plat_display_intro_screen();
    plat_display_menu();
    plat_display_map_name();
    if (music_enabled)
        music_play(SONG_TITLE);
    plat_change_difficulty_level();
    pal_fade_in();
    update_probe();                     /* so a test at the menu reads it */
    probe_check(PROBE_AT_MENU);

    for (;;) {
        wait_tick();
        tick_report();
        plat_menu_flash();              /* ISLOOP's first two, every pass */
        plat_credits_tick();

        key = plat_getin();             /* which answers the pad as well */
        if (!key)
            continue;

        if (key == 0x91 || key == KEY_MOVE_UP[0]) {             /* up */
            if (MENUY) {
                plat_menu_option(MENUY, 0);
                MENUY--;
                plat_menu_option(MENUY, 1);
                plat_play_sound(SFX_BEEP2);
            }
        } else if (key == 0x11 || key == KEY_MOVE_UP[1]) {      /* down */
            if (MENUY < 3) {
                plat_menu_option(MENUY, 0);
                MENUY++;
                plat_menu_option(MENUY, 1);
                plat_play_sound(SFX_BEEP2);
            }
        } else if (key == KEY_F6) {             /* the music, here too */
            music_enabled ^= 1;
            if (music_enabled)
                music_play(SONG_TITLE);
            else
                music_stop();
        } else if (key == 32 || key == 13) {                    /* space, return */
            plat_play_sound(SFX_BEEP);
            switch (MENUY) {
            case 0:
                set_controls();         /* EXEC_COMMAND: before anything else */
                return;                                         /* start */
            case 1:
                if (++SELECTED_MAP == MAP_COUNT)
                    SELECTED_MAP = 0;
                plat_display_map_name();
                break;
            case 2:
                if (++DIFF_LEVEL == 3)
                    DIFF_LEVEL = 0;
                plat_change_difficulty_level();
                break;
            case 3:                     /* CYCLE_CONTROLS, two schemes now */
                KEYS_DEFINED = 0;       /* a new scheme is a new set of keys */
                CONTROL ^= 1;
                plat_display_control();
                break;
            }
        }
    }
}

/* INIT_GAME. Nothing starts in inventory; everything is found by searching. */
static void init_game(void)
{
    char name[16];
    unsigned char i;

    played = 1;
    KEYS = AMMO_PISTOL = AMMO_PLASMA = 0;
    INV_BOMBS = INV_EMP = INV_MEDKIT = INV_MAGNET = 0;
    SELECTED_WEAPON = SELECTED_ITEM = 0;
    MAGNET_ACT = PLASMA_ACT = BIG_EXP_ACT = 0;
    /* RP6502: a quit from the pause skips GOM0, whose ticks let a big
     * explosion end and clear the shake; without this the next level would
     * shake until some later one ends. */
    SCREEN_SHAKE = 0;
    CYCLES = SECONDS = MINUTES = HOURS = 0;
    KEY_FAST = 0;

    pal_fade_out();
    plat_display_game_screen();

    /* "ROM:level-a" .. "ROM:level-r". The X16 patches the same last byte of
     * its filename; here the name is short enough to just build. */
    for (i = 0; i < 10; i++)
        name[i] = "ROM:level-"[i];
    name[10] = (char)('a' + SELECTED_MAP);
    name[11] = 0;
    slurp(name, UNIT_TYPE, LEVEL_BYTES);

    /* 2.1's INIT_UNIT_SPRITES ($3B9F), where its INIT_GAME calls it: each
     * robot's first frame. The X16's kept the last game's tile, or none after
     * power-on, until the robot first ran. 2.1's hoverbots start on its
     * sprite 56, which this version has no image of; they start on 99, which
     * HOVAN makes 98 on their first step, as 2.1's makes 56 its 52. 2.1 gives
     * type 1 tile 0 too, but no level has one in these slots. */
    for (i = 1; i < 28; i++) {
        switch (UNIT_TYPE[i]) {
        case 2: case 3: case 4: case 5: UNIT_TILE[i] = 99;  break;
        case 9:                         UNIT_TILE[i] = 100; break;
        case 17: case 18:               UNIT_TILE[i] = 164; break;
        }
        /* RP6502: and facing down, since nothing reset that either; an
         * evilbot then starts on 2.1's first frame, 60. */
        UNIT_DIRECTION[i] = 1;
    }
    SET_DIFF_LEVEL();       /* INIT_GAME: next, as 2.1's calls it ($3D49) */

    /* RANDOM is not seeded, as neither X16 version seeds it: it starts from
     * zero at power-on and runs on from game to game. */
    PLAYER_DIRECTION = FACE_DOWN;
    PLAYER_ANIMATE = 0;
    UNIT_TYPE[0] = 1;
    UNIT_TILE[0] = 96;

    /* SET_INITIAL_TIMERS: stagger them so the AI does not run every robot on
     * the same tick. */
    CLOCK_ACTIVE = 1;
    for (i = 1; i < 48; i++) {
        UNIT_TIMER_A[i] = i;
        UNIT_TIMER_B[i] = 0;
    }

    /* The whole window and its margin, loaded under the cover before it
     * lifts, since nothing is on screen yet to tear. */
    view_resume();
    CACULATE_AND_REDRAW();
    view_request();
    plat_display_player_sprite();
    view_flush();
    plat_display_player_health();
    plat_display_keys();
    plat_display_weapon();
    plat_display_item();
    plat_reveal_playfield();
    pal_fade_in();
    KEYTIMER = 30;          /* INIT_GAME: a beat before he can move, once seen */

    level_song();

    /* PRINT_INTRO_MESSAGE. */
    SOURCE = INTRO_MESSAGE;
    plat_print_info();
}

/* Load the chosen level and say so: tests synchronise on PROBE_AT_PLAY, and
 * the level and start square in the probe are what they check first. */
static void start_game(void)
{
    init_game();
    frames_total = 0;
    update_probe();
    probe_check(PROBE_AT_PLAY);
}

int main(void)
{
    unsigned char key;

    /* XRAM powers up holding anything, and the emulator fills it at random, so
     * the probe would read as whatever was there until the first update. A
     * test that waits for PROBE_STATE could match that by chance. */
    RIA.addr0 = XRAM_PROBE;
    RIA.step0 = 1;
    RIA.rw0 = PROBE_MAGIC_0;
    RIA.rw0 = PROBE_MAGIC_1;
    for (key = 2; key < PROBE_SIZE; key++)
        RIA.rw0 = 0;                    /* PROBE_STATE_BOOT */

    load_tileset();

    video_init();
    input_init();
    xreg_ria_gamepad(XRAM_GAMEPAD);     /* four pads of ten bytes; we read one */
    /* The OPL2, and the VIA's timer the effects tick from, which interrupts
     * through its own handler in src/sound.s. */
    sound_init();

    /* Writing the register sets the enable mask and clears anything already
     * triggered; src/game/irq.s reads it to acknowledge, since reading returns
     * the triggered bits and clears them.
     *
     * set_irq rather than a bare .interruptor: the handler reaches C, and
     * cc65's clevel_irq wrapper is what saves the C runtime's zero page,
     * switches to the stack below, and puts both back afterwards. Doing that by
     * hand is the same work with none of the maintenance. */
    set_irq(petscii_irq, irq_stack, sizeof(irq_stack));
    RIA.irq = 0x80;

    CONTROL = 0;
    KEYS_DEFINED = 0;
    set_controls();                     /* copy initial key controls */
    DIFF_LEVEL = 1;
    SELECTED_MAP = 0;

    intro_screen();
    start_game();

    for (;;) {
        wait_tick();
        tick_report();

        BACKGROUND_TASKS();

        /* Unit 0 stops being type 1 when the player dies or reaches the
         * transporter, which is how the AI signals both endings. */
        if (UNIT_TYPE[0] != 1) {
            plat_game_over();
            intro_screen();
            start_game();
            continue;
        }

        /* MG00 in the original picks the pad OR the keyboard, which leaves the
         * pad unable to select itself: the menu that chooses it reads keys.
         * Both run here, every pass, and the pad having acted is all that stops
         * a key being read in the same one. */
        if (gamepad_pass())
            continue;

        /* KY01: KEY_REPEAT then GETIN. The menus call GETIN alone, which is
         * why they act on presses and only walking repeats. */
        plat_key_repeat();
        key = plat_getin_keys();
        if (!key)
            continue;

        if (key == 0x1D || key == KEY_MOVE_UP[3])
            walk(FACE_RIGHT, REQUEST_WALK_RIGHT);
        else if (key == 0x9D || key == KEY_MOVE_UP[2])
            walk(FACE_LEFT, REQUEST_WALK_LEFT);
        else if (key == 0x11 || key == KEY_MOVE_UP[1])
            walk(FACE_DOWN, REQUEST_WALK_DOWN);
        else if (key == 0x91 || key == KEY_MOVE_UP[0])
            walk(FACE_UP, REQUEST_WALK_UP);
        else if (key == KEY_MOVE_UP[4]) {
            FIRE_UP();
            KEYTIMER = 20;              /* MG14 */
        }
        else if (key == KEY_MOVE_UP[5]) {
            FIRE_DOWN();
            KEYTIMER = 20;              /* MG15 */
        }
        else if (key == KEY_MOVE_UP[6]) {
            FIRE_LEFT();
            KEYTIMER = 20;              /* MG16 */
        }
        else if (key == KEY_MOVE_UP[7]) {
            FIRE_RIGHT();
            KEYTIMER = 20;              /* MG17 */
        }
        /* MG05 and MG06 clear the buffer after cycling, as every version does,
         * so a held F1 or F2 acts once a press. The pad's cycling does not, as
         * none of the originals' does. */
        else if (key == KEY_MOVE_UP[8]) {
            cycle_weapon();
            plat_clear_key_buffer();
        }
        else if (key == KEY_MOVE_UP[9]) {
            cycle_item();
            plat_clear_key_buffer();
        }
        /* MG07-MG09 clear the buffer after these, as CLEAR_KEY_BUFFER: the
         * direction key that chose the square may still be down when they
         * return, and would otherwise repeat as a step. The clear forgets
         * it, as the Amiga's does (src/input.c). */
        else if (key == KEY_MOVE_UP[10]) {
            USE_ITEM();
            plat_clear_key_buffer();
        }
        else if (key == KEY_MOVE_UP[11]) {
            SEARCH_OBJECT();
            plat_clear_key_buffer();
        }
        else if (key == KEY_MOVE_UP[12]) {
            MOVE_OBJECT();
            plat_clear_key_buffer();
        }
        else if (key == 3) {            /* MG18: run/stop */
            if (pause_game()) {
                intro_screen();
                start_game();
            }
        }
        else if (key == 9) {            /* TAB: the live map */
            livemap_toggle();
            plat_clear_key_buffer();
        }
        else if (key == KEY_SHIFT_TAB) {        /* its robots */
            livemap_robot_dots();
            plat_clear_key_buffer();
        }
        else if (key == KEY_SHIFT_C)            /* MG19: the cheat */
            cheater();
        else if (key == KEY_F6) {               /* the music */
            toggle_music();
            plat_clear_key_buffer();
        }
        else if (key == KEY_SHIFT_M) {          /* MG20: 2.1's music key */
            toggle_music();
            plat_clear_key_buffer();
        }
        else if (key == KEY_FX_DOWN)            /* MG22 */
            fx_volume(0);
        else if (key == KEY_FX_UP)              /* MG23 */
            fx_volume(1);
    }
}
