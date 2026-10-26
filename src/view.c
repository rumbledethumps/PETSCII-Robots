/* The playfield, drawn with the Amiga version's tiles and X16 2.1's sprites.
 *
 * The 11x7 window is 77 mode 5 sprites of 24x24 that never move. Each points at
 * an image in XRAM, and drawing the window is choosing what they point at. The
 * full tileset is 253 images of 288 bytes, which XRAM cannot hold, so the
 * images live in ROM:images, kept open, and a 13x9 cache holds the ones around
 * the window: the window itself and a margin one tile wide. The cache is
 * addressed like a wrapping mode 2 map -- map cell (mx,my) is always in slot
 * ((my+1) mod 9) * 13 + ((mx+1) mod 13) -- so a scroll changes which slots the
 * sprites point at and leaves the cache alone. A slot remembers which tile it
 * holds and for which cell, and is loaded again only when the cell it stands
 * for has a different tile: the map scrolled, a door opened, a crate moved.
 * Nothing searches the cache for a tile it might already hold elsewhere;
 * reading one from the ROM costs the 6502 nothing.
 *
 * Animated tiles -- water, the flag, the HVAC fans, the compactor, the server
 * light -- are not cached. Their frames stay in XRAM, and an animated cell's
 * sprite points at the current one.
 *
 * Units are a second set of sprites, one per unit the window shows, drawn from
 * a bank of images that stays in XRAM; the player is the last sprite, so he is
 * drawn over them -- except that an explosion on his own cell hides him, as
 * the Amiga's one unit a cell does. MAP_PRE_CALCULATE still decides which unit
 * shows in each cell, exactly as the X16 decided which tile to draw.
 *
 * THE FRAME. Loading is READ_XRAM, which moves the bytes while the 6502 does
 * something else, so the loads happen while the game waits for VSYNC:
 *
 *   spin    while the frame has not changed, poll the load in flight and,
 *           when it is done, start the next one the cache needs
 *   vblank  the moment it changes, write what the sprites should show -- the
 *           77 image pointers, the units, the player's new frame -- then wait
 *           for the load in flight to finish
 *   game    the game runs its tick: DRAW_MAP_WINDOW only works out what each
 *           sprite should show and which slots need loading, and the next
 *           vblank shows it
 *
 * The music's stream is read the same way, and before any tile: a song's next
 * 512 bytes, when one of its two buffers is free, which at the most is every
 * eighth frame (src/sound.c). It is not counted as a load and has no budget.
 *
 * No load starts after VSYNC; the rest wait for the next frame. The margin is
 * there so that a step does not have to wait, and a step that comes before
 * the margin on its side has loaded waits for it: the main loop asks
 * view_ready first. A cell coming into view whose slot has not been loaded
 * shows black until it has, which only the raft, moving on its own timer, can
 * still bring about.
 *
 * A jump -- the elevator, a transporter -- would overwrite slots the old view
 * still shows, so it blacks the playfield out first: the next vblank moves
 * every sprite below the screen, the loads start only after that, and the
 * window comes back once the whole cache, margin and all, has loaded.
 */
#include <fcntl.h>
#include <rp6502.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "game/game.h"
#include "livemap.h"
#include "platform.h"
#include "sound.h"
#include "view.h"
#include "xram.h"

unsigned char ANIM_STATE, ANIM_STATE_B, CINEMA_STATE;
unsigned char view_loads, view_units, view_blank, view_overruns;

/* Test knobs. view_budget caps the loads started a frame, and view_lag holds
 * every load "in flight" until the next VSYNC: the emulator finishes a transfer
 * the moment a script starts it, and these make the backlog a real machine can
 * have happen there too. */
unsigned char view_budget = 255, view_lag;

/* The X16 declares this as a byte that is one and never assigns it again. Kept
 * because it is the switch the original offers for turning the animations off,
 * and tests use it to hold a frame still. */
unsigned char ANIMATE = 1;

/* For src/view_io.s. */
int view_fd = -1;
unsigned char ptr_lo[MAP_WIN_CELLS], ptr_hi[MAP_WIN_CELLS];

void __fastcall__ ldr_start(unsigned xaddr);
unsigned char ldr_busy(void);
void __fastcall__ pf_write_ptrs(unsigned xaddr);
void __fastcall__ xr_copy(unsigned xaddr, const void *src, unsigned char n);

static unsigned char water_timer, cinema_timer, anim_visible;
static unsigned char vbl_frame, loads_frame, suspended;

/* Map coordinates to cache slots, for mx = -1..128 and my = -1..64. */
static unsigned char col13[MAP_W + 2];
static unsigned char row13[MAP_H + 2];

/* What each slot holds, and for which cell. */
static unsigned char slot_tile[CACHE_SLOTS];        /* TILE_UNKNOWN: nothing */
static unsigned char slot_mx[CACHE_SLOTS], slot_my[CACHE_SLOTS];
static unsigned char slot_lo[CACHE_SLOTS], slot_hi[CACHE_SLOTS];
static unsigned char anim_lo[24], anim_hi[24];

#define TILE_UNKNOWN 0xFF

/* The window the cache serves. */
static unsigned char view_wx, view_wy;

/* What the next vblank has to write. Not static: a test waits for both to be
 * clear before it reads the sprites back. */
unsigned char view_ptrs_dirty, view_units_dirty;

/* The unit sprites, as whole records, ready to copy. */
static mode5_csprite_t ushadow[PF_UNIT_COUNT];
static unsigned char ushadow_shown;

/* The load in flight. */
static unsigned char inflight, inflight_frame;
static unsigned char job_slot, job_tile, job_mx, job_my;
#define JOB_TILE   1
#define JOB_PLAYER 2
#define JOB_MUSIC  3

/* The walk through the cells the cache serves: the window's in row order when
 * one of them needs a load, then the margin's, the side the window last moved
 * towards first. Off-map and animated cells are passed over. */
static unsigned char walk_phase, walk_i, walk_r, walk_c, walk_g;
/* Right, left, bottom, top: the order before the window first moves. */
static unsigned char walk_order[4] = { 0, 1, 2, 3 };
#define WALK_IDLE     0
#define WALK_VISIBLE  1
#define WALK_MARGIN   2
#define MARGIN_RIGHT  0
#define MARGIN_LEFT   1
#define MARGIN_BOTTOM 2
#define MARGIN_TOP    3

/* A jump's blackout: BLACK_PARK until the vblank has moved every sprite off
 * the screen, BLACK_HELD while the cache loads behind it. */
static unsigned char black;
#define BLACK_PARK 1
#define BLACK_HELD 2

/* The player's two image slots: one shown, the other for the next frame. */
static unsigned char player_front, player_shown = 0xFF, player_want = 0xFF;
static unsigned char player_flip, player_demat;
static unsigned char player_put;        /* the sprite needs its record again */
#define PLAYER_HIDDEN 0xFE

/* x and y of a sprite record, then its image and palette. */
static void put_sprite(unsigned xaddr, int x, int y, unsigned image,
                       unsigned palette)
{
    RIA.addr0 = xaddr;
    RIA.step0 = 1;
    RIA.rw0 = (unsigned char)(x & 0xFF);
    RIA.rw0 = (unsigned char)(x >> 8);
    RIA.rw0 = (unsigned char)(y & 0xFF);
    RIA.rw0 = (unsigned char)(y >> 8);
    RIA.rw0 = (unsigned char)(image & 0xFF);
    RIA.rw0 = (unsigned char)(image >> 8);
    RIA.rw0 = (unsigned char)(palette & 0xFF);
    RIA.rw0 = (unsigned char)(palette >> 8);
}

static void put_size(unsigned xaddr, unsigned char width_height,
                     unsigned char attributes)
{
    RIA.addr0 = xaddr + offsetof(mode5_csprite_t, width_height);
    RIA.step0 = 1;
    RIA.rw0 = width_height;
    RIA.rw0 = attributes;
}

static void park(unsigned xaddr)
{
    RIA.addr0 = xaddr + offsetof(mode5_csprite_t, y_pos_px);
    RIA.step0 = 1;
    RIA.rw0 = SPR_PARKED_Y;
    RIA.rw0 = 0;
}

/* Every playfield sprite -- the window, the units, the player -- below the
 * screen, or the window's back in their rows. Portal 0 takes the low byte of
 * each y and portal 1 the high, a record at a time. */
static void place_all(unsigned char shown)
{
    unsigned char n, c = 0, y = SCREEN_TOP;

    RIA.addr0 = XRAM_PF + offsetof(mode5_csprite_t, y_pos_px);
    RIA.addr1 = XRAM_PF + offsetof(mode5_csprite_t, y_pos_px) + 1;
    RIA.step0 = sizeof(mode5_csprite_t);
    RIA.step1 = sizeof(mode5_csprite_t);
    for (n = 0; n < (shown ? MAP_WIN_CELLS : PF_COUNT); n++) {
        RIA.rw0 = shown ? y : SPR_PARKED_Y;
        RIA.rw1 = 0;
        if (++c == MAP_WIN_TILES_W) {
            c = 0;
            y += TILE_PX;
        }
    }
    RIA.step0 = 1;
    RIA.step1 = 1;
}

/* ---- the cinema marquee ----------------------------------------------- */

/* A cinema is tiles 20, 21 and 22 side by side, and its marquee is six
 * characters of CINEMA_MESSAGE across their middle row, one character on
 * every twenty ticks as CINEMA_STATE counts, as the Amiga draws it: white on
 * black, in the C64 font, written into the tiles' own images. Here the
 * images are the cache slots, so the text scrolls, hides and blacks out with
 * the tiles. A slot remembers which state it shows; a load puts the plain
 * tile back and so forgets it. */
#define CINEMA        20
#define MARQUEE_LEN   197               /* CINEMA_STATE wraps here */
static unsigned char cinema_visible, marquee_dirty;
static unsigned char slot_marquee[CACHE_SLOTS];

/* Character `code` of the font, into slot s at character column col of the
 * tile's middle row: rows 8 to 15, four bytes of two pixels a row, the left
 * one in the high nibble. Portal 1 reads the font, which keeps each glyph row
 * 256 bytes after the last. */
static void glyph(unsigned char s, unsigned char col, unsigned char code)
{
    static const unsigned char pair[4] = { 0x00, 0x01, 0x10, 0x11 };
    unsigned a = (((unsigned)slot_hi[s] << 8) | slot_lo[s]) + 8 * 12 + col * 4;
    unsigned f = XRAM_FONT + code;
    unsigned char r, b;

    RIA.step0 = 1;
    for (r = 0; r < 8; r++, a += 12, f += 256) {
        RIA.addr1 = f;
        b = RIA.rw1;
        RIA.addr0 = a;
        RIA.rw0 = pair[b >> 6];
        RIA.rw0 = pair[(b >> 4) & 3];
        RIA.rw0 = pair[(b >> 2) & 3];
        RIA.rw0 = pair[b & 3];
    }
}

/* Every cinema cell in the window whose slot is loaded and shows an older
 * state: tile 20's last two columns take characters 0 and 1, 21's three take
 * 2 to 4, 22's first takes 5. */
static void marquee(void)
{
    static const unsigned char first[3] = { 0, 2, 5 };
    static const unsigned char col0[3] = { 1, 0, 0 };
    static const unsigned char count[3] = { 2, 3, 1 };
    unsigned char r, c, t, s, k, i, state;
    const unsigned char *m;

    /* The flag first: a tick that lands between the two asks again. */
    marquee_dirty = 0;
    state = CINEMA_STATE;
    for (r = 0; r < MAP_WIN_TILES_H; r++) {
        m = MAP + ((unsigned)(view_wy + r) << 7) + view_wx;
        for (c = 0; c < MAP_WIN_TILES_W; c++) {
            t = (unsigned char)(m[c] - CINEMA);
            if (t > 2)
                continue;
            s = (unsigned char)(row13[view_wy + r + 1]
                                + col13[view_wx + c + 1]);
            if (slot_tile[s] != t + CINEMA || slot_marquee[s] == state)
                continue;
            slot_marquee[s] = state;
            for (k = 0; k < count[t]; k++) {
                i = (unsigned char)(state + first[t] + k);
                if (i >= MARQUEE_LEN)
                    i -= MARQUEE_LEN;
                glyph(s, (unsigned char)(col0[t] + k), CINEMA_MESSAGE[i]);
            }
        }
    }
}

/* ---- loading ---------------------------------------------------------- */

static void retire(void)
{
    unsigned char n, c, r;

    if (inflight == JOB_MUSIC) {
        music_retire();
        inflight = 0;
        return;
    }
    ++view_loads;
    if (inflight == JOB_PLAYER) {
        player_shown = player_want == PLAYER_HIDDEN ? PLAYER_HIDDEN : job_tile;
        player_flip = 1;
    } else {
        slot_tile[job_slot] = job_tile;
        slot_mx[job_slot] = job_mx;
        slot_my[job_slot] = job_my;
        slot_marquee[job_slot] = 0xFF;
        if ((unsigned char)(job_tile - CINEMA) <= 2)
            marquee_dirty = 1;
        /* In view: the cell shows its image from the next vblank. */
        c = (unsigned char)(job_mx - view_wx);
        r = (unsigned char)(job_my - view_wy);
        if (c < MAP_WIN_TILES_W && r < MAP_WIN_TILES_H) {
            n = (unsigned char)(r * MAP_WIN_TILES_W + c);
            if (ptr_lo[n] == (unsigned char)(XRAM_BLANK & 0xFF)
                && ptr_hi[n] == (unsigned char)(XRAM_BLANK >> 8))
                --view_blank;
            ptr_lo[n] = slot_lo[job_slot];
            ptr_hi[n] = slot_hi[job_slot];
            view_ptrs_dirty = 1;
        }
    }
    inflight = 0;
}

/* Wait out the load in flight, if any. Every API call goes through here
 * first: the RIA runs one call at a time, and a second started while READ_XRAM
 * runs is lost. */
void view_quiesce(void)
{
    if (!inflight)
        return;
    while (ldr_busy())
        ;
    retire();
}

/* One record of ROM:images into XRAM, now. For the HUD's pictures, which
 * change rarely and are not worth a queue. */
void __fastcall__ view_load(unsigned xaddr, unsigned record, unsigned count)
{
    view_quiesce();
    lseek(view_fd, (long)record * IMG24_BYTES, SEEK_SET);
    read_xram(xaddr, count, view_fd);
    ++view_loads;
}

/* The next cell of the walk, or 0 when the window's cells or the margin's
 * have all been walked. *mx and *my are left on the map; a cell off it is
 * skipped here. */
static unsigned char walk_next(unsigned char *mx, unsigned char *my)
{
    signed char dc, dr;

    for (;;) {
        if (walk_phase == WALK_VISIBLE) {
            if (walk_i == MAP_WIN_CELLS) {
                walk_phase = WALK_MARGIN;
                walk_g = walk_i = 0;
                return 0;
            }
            *mx = (unsigned char)(view_wx + walk_c);
            *my = (unsigned char)(view_wy + walk_r);
            ++walk_i;
            if (++walk_c == MAP_WIN_TILES_W) {
                walk_c = 0;
                ++walk_r;
            }
            return 1;
        }
        if (walk_phase != WALK_MARGIN)
            return 0;
        if (walk_g == 4) {
            walk_phase = WALK_IDLE;
            return 0;
        }
        /* The columns run the margin's full height, the rows only the
         * window's width, so the corners are walked once. */
        switch (walk_order[walk_g]) {
        case MARGIN_RIGHT:
            dc = MAP_WIN_TILES_W;
            dr = (signed char)(walk_i - 1);
            break;
        case MARGIN_LEFT:
            dc = -1;
            dr = (signed char)(walk_i - 1);
            break;
        case MARGIN_BOTTOM:
            dc = (signed char)walk_i;
            dr = MAP_WIN_TILES_H;
            break;
        default:
            dc = (signed char)walk_i;
            dr = -1;
            break;
        }
        if (++walk_i == (walk_order[walk_g] <= MARGIN_LEFT
                         ? MAP_WIN_TILES_H + 2 : MAP_WIN_TILES_W)) {
            walk_i = 0;
            ++walk_g;
        }
        *mx = (unsigned char)(view_wx + dc);
        *my = (unsigned char)(view_wy + dr);
        if (*mx < MAP_W && *my < MAP_H)
            return 1;
    }
}

/* Start the next load the cache needs, if there is one among the next few
 * cells of the walk. The player comes first, since he is always on screen.
 * The spin looks at a few cells a call, so it keeps polling. */
static unsigned char start_next(unsigned char cells)
{
    unsigned char n, mx, my, t, s;
    unsigned a;

    if (player_want < PLAYER_HIDDEN && player_want != player_shown
        && !player_flip) {
        a = XRAM_PLAYER + (unsigned)(player_front ^ 1) * IMG24_BYTES;
        lseek(view_fd, (long)(IMG_PLAYER + player_want) * IMG24_BYTES,
              SEEK_SET);
        ldr_start(a);
        job_tile = player_want;
        inflight = JOB_PLAYER;
        return 1;
    }
    for (n = 0; n < cells; n++) {
        if (!walk_next(&mx, &my))
            return 0;
        t = MAP[((unsigned)my << 7) | mx];
        if (amiga_tile_anim[t] != 0xFF)
            continue;
        s = (unsigned char)(row13[my + 1] + col13[mx + 1]);
        if (slot_tile[s] == t)
            continue;
        lseek(view_fd, (long)t * IMG24_BYTES, SEEK_SET);
        ldr_start(((unsigned)slot_hi[s] << 8) | slot_lo[s]);
        job_slot = s;
        job_tile = t;
        job_mx = mx;
        job_my = my;
        inflight = JOB_TILE;
        return 1;
    }
    return 0;
}

/* While waiting for VSYNC: poll, and keep a load going, the music's first.
 * Nothing loads after a jump until the old view is off the screen; the music
 * still does, and on every other screen too. */
static void pump(void)
{
    if (inflight) {
        if (ldr_busy() || (view_lag && inflight_frame == IRQ_FRAME))
            return;
        retire();
    }
    if (music_read()) {
        inflight = JOB_MUSIC;
        inflight_frame = IRQ_FRAME;
        return;
    }
    if (suspended || black == BLACK_PARK || vbl_frame != IRQ_FRAME
        || loads_frame >= view_budget)
        return;
    if (start_next(12)) {
        inflight_frame = IRQ_FRAME;
        ++loads_frame;
    }
}

/* Whether the cache or the player still has a load to come. */
static unsigned char loading(void)
{
    return (unsigned char)(walk_phase || inflight
                           || (player_want < PLAYER_HIDDEN
                               && player_want != player_shown));
}

/* ---- what the sprites show -------------------------------------------- */

static void show(void)
{
    unsigned char n, lift = 0;

    if (black == BLACK_PARK) {
        place_all(0);
        black = BLACK_HELD;
        return;
    }
    if (black) {
        /* A new player frame swaps slots as usual, unseen, so the next one
         * can load. */
        if (player_flip) {
            player_front ^= 1;
            player_flip = 0;
        }
        if (loading())
            return;
        black = 0;
        lift = player_put = 1;
        view_ptrs_dirty = view_units_dirty = 1;
    }
    if (view_ptrs_dirty) {
        pf_write_ptrs(XRAM_PF + offsetof(mode5_csprite_t, xram_sprite_ptr));
        view_ptrs_dirty = 0;
    }
    /* The window comes back only once it points at the new view, so a vblank
     * that runs late can only show part of it still dark. */
    if (lift)
        place_all(1);
    if (marquee_dirty)
        marquee();
    if (view_units_dirty) {
        n = view_units > ushadow_shown ? view_units : ushadow_shown;
        if (n > 16) {
            xr_copy(PF_SPRITE(PF_UNITS), ushadow,
                    16 * sizeof(mode5_csprite_t));
            xr_copy(PF_SPRITE(PF_UNITS + 16), ushadow + 16,
                    (unsigned char)((n - 16) * sizeof(mode5_csprite_t)));
        } else if (n) {
            xr_copy(PF_SPRITE(PF_UNITS), ushadow,
                    (unsigned char)(n * sizeof(mode5_csprite_t)));
        }
        ushadow_shown = view_units;
        view_units_dirty = 0;
    }
    if (player_flip) {
        player_front ^= 1;
        player_flip = 0;
        player_put = 1;
    }
    /* Hidden, he is parked -- and a frame that finished loading after he
     * was, the last of the dematerialize, stays out of sight. */
    if (player_put) {
        if (player_want != PLAYER_HIDDEN)
            put_sprite(PF_SPRITE(PF_PLAYER), PLAYER_SPR_X + shake_dx,
                       PLAYER_SPR_Y,
                       XRAM_PLAYER + (unsigned)player_front * IMG24_BYTES,
                       XRAM_PAL_A);
        else
            park(PF_SPRITE(PF_PLAYER));
        player_put = 0;
    }
}

/* Screen shake, the Amiga's hardware shake: while SCREEN_SHAKE is set and the
 * clock runs, the whole screen sits 3 pixels right for two frames in every
 * four. The Amiga moves the display; here every plane and sprite moves -- the
 * window's tiles here, the units and the player through their records, and
 * the frame, the text, the picture layer and the HUD's pictures through
 * plat_shake. The cursor stays still, a hardware sprite on the Amiga too. */
unsigned char shake_dx;
static unsigned char shake_step;

static void shake(void)
{
    unsigned char n, c = 0, x, dx = 0;
    mode5_csprite_t *u = ushadow;

    if (SCREEN_SHAKE && CLOCK_ACTIVE) {
        shake_step = (unsigned char)((shake_step + 1) & 3);
        if (shake_step < 2)
            dx = 3;
    } else {
        shake_step = 3;
    }
    if (dx == shake_dx)
        return;

    for (n = 0; n < PF_UNIT_COUNT; n++, u++)
        u->x_pos_px += (int)dx - (int)shake_dx;
    shake_dx = dx;
    view_units_dirty = player_put = 1;

    RIA.addr0 = XRAM_PF + offsetof(mode5_csprite_t, x_pos_px);
    RIA.step0 = sizeof(mode5_csprite_t);
    for (n = 0, x = dx; n < MAP_WIN_CELLS; n++) {
        RIA.rw0 = x;
        x += TILE_PX;
        if (++c == MAP_WIN_TILES_W) {
            c = 0;
            x = dx;
        }
    }
    RIA.step0 = 1;
    plat_shake(dx);
}

/* The moment VSYNC changes the frame: show what the game decided, or the live
 * map's dots while it has the playfield's place, then let the load in flight
 * finish before the game runs again. */
void view_vblank(void)
{
    if ((unsigned char)(IRQ_FRAME - vbl_frame) > 1)
        ++view_overruns;
    vbl_frame = IRQ_FRAME;
    loads_frame = 0;
    shake();
    if (!suspended)
        show();
    else if (livemap_on)
        livemap_frame();
    view_quiesce();
}

/* The main loop's tick: spin until VSYNC, loading, then the vblank work. */
void view_wait(void)
{
    while (vbl_frame == IRQ_FRAME)
        pump();
    view_vblank();
}

/* The first thing BACKGROUND_TASKS does. The waits that call it in a loop --
 * searching, moving an object, the dying player -- get the vblank work on
 * each new frame and keep the loads going in between. Once the
 * AI has run for the frame, BGTIMER1 is 0; before that the game is in its
 * tick and nothing starts. */
void view_hook(void)
{
    if (vbl_frame != IRQ_FRAME)
        view_vblank();
    else if (!BGTIMER1)
        pump();
}

/* The same, for a wait that runs no AI: the pause, the elevator panel, the
 * game-over screens. */
void view_idle(void)
{
    if (vbl_frame != IRQ_FRAME)
        view_vblank();
    else
        pump();
}

/* Every load the cache and the player need, now, and then show them. For when
 * nothing is on screen to tear: starting a level, under a cover. A jump needs
 * no blackout there, but one already under way ends here. */
void view_flush(void)
{
    view_quiesce();
    while (loading()) {
        /* A frame loaded while the view was suspended holds up the next one
         * until show() swaps it in. Under the cover the swap can happen now,
         * and show() puts the sprite right. */
        if (player_flip) {
            player_front ^= 1;
            player_flip = 0;
            player_put = 1;
        }
        if (music_read()) {
            while (ldr_busy())
                ;
            music_retire();
        }
        if (start_next(MAP_WIN_CELLS)) {
            while (ldr_busy())
                ;
            retire();
        }
    }
    if (black == BLACK_PARK)
        black = 0;
    show();
}

/* ---- deciding what to show -------------------------------------------- */

void view_invalidate(void)
{
    unsigned char s;
    view_quiesce();
    for (s = 0; s < CACHE_SLOTS; s++) {
        slot_tile[s] = TILE_UNKNOWN;
        slot_mx[s] = 0xFF;
        slot_marquee[s] = 0xFF;
    }
}

/* The cache's memory is about to hold a picture: no loads into it, and what
 * it held is gone. view_resume gives it back. */
void view_suspend(void)
{
    view_invalidate();
    suspended = 1;
}

void view_resume(void)
{
    suspended = 0;
}

/* The live map's turn: the cache stops loading, and every playfield sprite goes
 * below the screen now, before the map is drawn over the tiles they show.
 * view_show gives the playfield back, dark until the cache has loaded, as
 * after a jump. */
void view_hide(void)
{
    view_suspend();
    place_all(0);
    black = BLACK_HELD;
}

void view_show(void)
{
    view_resume();
    view_request();
}

/* What the Amiga adds to a frame for the way it faces -- up, down, left,
 * right, its UNIT_DIRECTION order -- for the player and the evilbot. */
static const unsigned char face_base[4] = { 8, 0, 12, 4 };

/* Whether an explosion has the player's cell: the Amiga draws one unit a
 * cell, so it covers him. */
static unsigned char player_covered;

/* Between the end of a dematerialize and the window being drawn where he
 * has arrived: he stays out of sight, rather than showing for a frame on the
 * pad he left before the jump blacks the playfield out. */
static unsigned char player_arriving;

/* Every unit the window shows, in window order, as records ready for the
 * vblank. A unit tile with no image in the bank is left out, as the Amiga
 * leaves out what tileSpriteMap does not map. */

static void plan_units(void)
{
    static const unsigned pal_for[3] = { XRAM_PAL_FG, XRAM_PAL_A, XRAM_PAL_B };
    mode5_csprite_t *u = ushadow;
    unsigned char n, r, c, t, b, a, pc, covered = 0, k = 0;

    pc = (unsigned char)((UNIT_LOC_Y[0] - view_wy) * MAP_WIN_TILES_W
                         + (UNIT_LOC_X[0] - view_wx));
    for (r = 0, n = 0; r < MAP_WIN_TILES_H; r++)
        for (c = 0; c < MAP_WIN_TILES_W; c++, n++) {
            t = MAP_PRECALC[n];
            if (!t || k == PF_UNIT_COUNT)
                continue;
            /* On the player's own cell a bomb or magnet goes under him and
             * does not show, and an explosion goes over him and he does not.
             * A shot leaving him is not let cover him, which on the Amiga it
             * can for a frame. */
            if (n == pc) {
                if (t == 130 || t == 134)
                    continue;
                if (t == 246 || (unsigned char)(t - 248) <= 4)
                    covered = 1;    /* the small one's five frames, 2.1's */
            }
            b = amiga_unit_bank[t];
            if (b == 0xFF)
                continue;
            /* The evilbot faces the way it last tried to walk, and a wreck
             * is the one its robot leaves: a rollerbot's, the evilbot's, or
             * the hoverbots' for anything else. */
            if ((unsigned char)(t - 100) <= 3) {
                b += face_base[UNIT_DIRECTION[MAP_PRECALC_UNIT[n]] & 3];
            } else if (t == 115) {
                a = UNIT_A[MAP_PRECALC_UNIT[n]];
                b += a == 9 ? 2 : (a == 17 || a == 18);
            }
            u->x_pos_px = c * TILE_PX + shake_dx;
            u->y_pos_px = SCREEN_TOP + r * TILE_PX;
            u->xram_sprite_ptr = XRAM_UNITS + (unsigned)b * IMG24_BYTES;
            u->palette_ptr = pal_for[amiga_bank_pal[b]];
            ++u;
            ++k;
        }
    for (n = k; n < ushadow_shown; n++, u++)
        u->y_pos_px = SPR_PARKED_Y;
    view_units = k;
    view_units_dirty = 1;
    if (covered != player_covered) {
        player_covered = covered;
        view_player();
    }
}

/* DRAW_MAP_WINDOW. Works out what each window sprite should show -- the
 * current frame of an animated tile, the cell's cache slot when it holds the
 * cell's tile, or the cell's old image while the new one loads -- and black
 * for a cell whose slot holds another cell's tile, until the walk has loaded
 * it. Nothing reaches the screen before the next vblank. */
void view_request(void)
{
    unsigned char r, c, n, t, a, s, wx, wy, mx, my, rb, need = 0;
    const unsigned char *m;

    REDRAW_WINDOW = 0;
    if (suspended)
        return;
    view_quiesce();
    MAP_PRE_CALCULATE();

    /* REQUEST_WALK_* keeps the player at least 5 squares from the side and 3
     * from the top, so the window is always on the map. */
    wx = MAP_WINDOW_X;
    wy = MAP_WINDOW_Y;
    if (wx > MAP_W - MAP_WIN_TILES_W)
        wx = MAP_W - MAP_WIN_TILES_W;
    if (wy > MAP_H - MAP_WIN_TILES_H)
        wy = MAP_H - MAP_WIN_TILES_H;

    /* More than a step is a jump: the elevator or a transporter. view_ready
     * keeps the player from stepping again until the window has been drawn
     * where the raft or his last step left it. */
    if (!black && ((unsigned char)(wx - view_wx + 1) > 2
                   || (unsigned char)(wy - view_wy + 1) > 2))
        black = BLACK_PARK;

    /* The side of the margin the window moved towards is the one it will
     * need next. */
    if (wx != view_wx) {
        walk_order[0] = wx > view_wx ? MARGIN_RIGHT : MARGIN_LEFT;
        walk_order[1] = wx > view_wx ? MARGIN_LEFT : MARGIN_RIGHT;
        walk_order[2] = MARGIN_BOTTOM;
        walk_order[3] = MARGIN_TOP;
    } else if (wy != view_wy) {
        walk_order[0] = wy > view_wy ? MARGIN_BOTTOM : MARGIN_TOP;
        walk_order[1] = wy > view_wy ? MARGIN_TOP : MARGIN_BOTTOM;
        walk_order[2] = MARGIN_RIGHT;
        walk_order[3] = MARGIN_LEFT;
    }
    view_wx = wx;
    view_wy = wy;

    anim_visible = cinema_visible = 0;
    view_blank = 0;
    for (r = 0, n = 0; r < MAP_WIN_TILES_H; r++) {
        my = (unsigned char)(wy + r);
        m = MAP + ((unsigned)my << 7) + wx;
        rb = row13[my + 1];
        for (c = 0; c < MAP_WIN_TILES_W; c++, n++) {
            t = m[c];
            if ((unsigned char)(t - CINEMA) <= 2)
                cinema_visible = marquee_dirty = 1;
            a = amiga_tile_anim[t];
            if (a != 0xFF) {
                /* Bit 6 is 2.1's group B, the compactor and the fans. */
                a = (unsigned char)((a & 0x1F)
                                    + ((a & 0x40 ? ANIM_STATE_B : ANIM_STATE)
                                       & (a & 0x80 ? 3 : 1)));
                ptr_lo[n] = anim_lo[a];
                ptr_hi[n] = anim_hi[a];
                anim_visible = 1;
                continue;
            }
            mx = (unsigned char)(wx + c);
            s = (unsigned char)(rb + col13[mx + 1]);
            if (slot_tile[s] == t
                || (slot_mx[s] == mx && slot_my[s] == my)) {
                if (slot_tile[s] != t)
                    need = 1;
                ptr_lo[n] = slot_lo[s];
                ptr_hi[n] = slot_hi[s];
            } else {
                need = 1;
                ++view_blank;
                ptr_lo[n] = (unsigned char)(XRAM_BLANK & 0xFF);
                ptr_hi[n] = (unsigned char)(XRAM_BLANK >> 8);
            }
        }
    }
    view_ptrs_dirty = 1;

    walk_phase = need ? WALK_VISIBLE : WALK_MARGIN;
    walk_i = walk_r = walk_c = walk_g = 0;

    plan_units();
    if (player_arriving) {
        player_arriving = 0;
        view_player();
    }
}

/* Whether the player can step towards facing without the window outrunning
 * the cache: the playfield is not dark, the window has been drawn where it
 * now is, and the cells the step would bring into view have their own tiles.
 * The raft moves him in the AI, and the window is drawn at the start of the
 * next pass, so a step in between waits for that. A step that will not move
 * the window -- into a wall -- waits the same way, since only trying it tells
 * them apart; off the map's edge there is nothing to wait for. */
unsigned char __fastcall__ view_ready(unsigned char facing)
{
    unsigned char wx = MAP_WINDOW_X, wy = MAP_WINDOW_Y, mx, my, n, t, s;
    unsigned char across = 0;

    if (suspended)
        return 1;
    if (wx > MAP_W - MAP_WIN_TILES_W)
        wx = MAP_W - MAP_WIN_TILES_W;
    if (wy > MAP_H - MAP_WIN_TILES_H)
        wy = MAP_H - MAP_WIN_TILES_H;
    if (black || wx != view_wx || wy != view_wy)
        return 0;

    switch (facing) {
    case FACE_UP:
        mx = wx;
        my = (unsigned char)(wy - 1);
        across = 1;
        break;
    case FACE_DOWN:
        mx = wx;
        my = (unsigned char)(wy + MAP_WIN_TILES_H);
        across = 1;
        break;
    case FACE_LEFT:
        mx = (unsigned char)(wx - 1);
        my = wy;
        break;
    default:
        mx = (unsigned char)(wx + MAP_WIN_TILES_W);
        my = wy;
        break;
    }
    if (mx >= MAP_W || my >= MAP_H)
        return 1;
    for (n = across ? MAP_WIN_TILES_W : MAP_WIN_TILES_H; n; n--) {
        t = MAP[((unsigned)my << 7) | mx];
        if (amiga_tile_anim[t] == 0xFF) {
            s = (unsigned char)(row13[my + 1] + col13[mx + 1]);
            if (slot_tile[s] != t && (slot_mx[s] != mx || slot_my[s] != my)) {
                /* A tile that changed in the margin, outside the window --
                 * the raft docking there -- asks for no redraw, so nothing
                 * would load it: walk the margin again. */
                if (walk_phase == WALK_IDLE) {
                    walk_phase = WALK_MARGIN;
                    walk_i = walk_g = 0;
                }
                return 0;
            }
        }
        if (across)
            ++mx;
        else
            ++my;
    }
    return 1;
}

/* ANIMATE_WATER, as X16 2.1 runs it ($5650): first thing in each AI pass
 * (AI000, $1207), so the tiles stand still whenever the robots do -- the
 * pause, the elevator panel, a transport, the waits for a key at the end of a
 * game. Group A -- water, the flag, the server light -- steps when
 * water_timer reads 0, and group B -- the compactor, the fans -- when it
 * reads 15, each every thirty ticks, B half way between; 2.1 compares the
 * value before the decrement, and so does this. Nothing is reset at a level
 * start, as in 2.1. It only counts and asks for a redraw, and only while an
 * animated tile is in view, where 2.1 always asks. RP6502: the marquee, which
 * 2.1 does not have, keeps its twenty ticks here, so it stands still with the
 * tiles. */
void view_anim_tick(void)
{
    if (ANIMATE != 1)
        return;
    if (!water_timer) {
        water_timer = 29;
        ++ANIM_STATE;
        if (anim_visible)
            REDRAW_WINDOW = 1;
    } else if (water_timer-- == 15) {
        ++ANIM_STATE_B;
        if (anim_visible)
            REDRAW_WINDOW = 1;
    }
    if (++cinema_timer == 20) {
        cinema_timer = 0;
        if (++CINEMA_STATE == MARQUEE_LEN)
            CINEMA_STATE = 0;
        if (cinema_visible)
            marquee_dirty = 1;
    }
}

/* ---- the player ------------------------------------------------------- */

/* The player's frame, as the Amiga picks it: a base for the direction he
 * faces (up, down, left, right), then the walk frame, then sixteen more for
 * each weapon. The X16's PLAYER_DIRECTION counts in threes, which indexes the
 * bases directly. */

static unsigned char player_frame(void)
{
    unsigned char k;
    /* Gone: transported off the level -- type 2 is how the AI says he won --
     * or under an explosion, dead or alive. */
    if (UNIT_TYPE[0] == 2 || player_covered || player_arriving)
        return PLAYER_HIDDEN;
    if (PLAYER_DIRECTION == FACE_DEAD)
        return 48;
    /* Dematerializing: 2.1's eight frames, 88-95, which DEMATERIALIZE puts
     * in UNIT_TILE as 2.1's does, eight ticks each. They are frames 76-83
     * here, where the Amiga's seven were. */
    if (player_demat) {
        k = (unsigned char)(UNIT_TILE[0] - 88);
        return k < 8 ? (unsigned char)(76 + k) : PLAYER_HIDDEN;
    }
    /* Just transported within the level: the Amiga's tile 97, frame 1 --
     * facing down, no weapon -- until his next step. */
    if (UNIT_TILE[0] == 97)
        return 1;
    return (unsigned char)(face_base[PLAYER_DIRECTION / 3]
                           + (PLAYER_ANIMATE & 3) + (SELECTED_WEAPON << 4));
}

/* DISPLAY_PLAYER_SPRITE. The new frame loads into the slot not on screen, and
 * the vblank after it has loaded switches the sprite to it, so it never shows
 * half loaded. */
void view_player(void)
{
    unsigned char f = player_frame();

    if (f == PLAYER_HIDDEN) {
        player_want = player_shown = PLAYER_HIDDEN;
        player_put = 1;                 /* the next vblank parks him */
        return;
    }
    player_want = f <= 48 ? f : (unsigned char)(f - 27);
}

/* DEMATERIALIZE's palette cycle on the X16. Here it is 2.1's eight frames
 * of the player breaking up, from UNIT_TILE as 2.1 draws them: 1 when they
 * start, 0 when he has gone. */
void __fastcall__ plat_demat_palette(unsigned char value)
{
    if (player_demat && !value)
        player_arriving = 1;
    player_demat = value != 0;
    view_player();
}

/* ---- setting up ------------------------------------------------------- */

void view_init(void)
{
    unsigned char i, r, c;
    unsigned a;

    view_fd = open("ROM:images", O_RDONLY);
    if (view_fd < 0) {
        printf("\nERROR: ROM:images\n");
        exit(1);
    }

    for (i = 0; i < MAP_W + 2; i++)
        col13[i] = (unsigned char)(i % CACHE_W);
    for (i = 0; i < MAP_H + 2; i++)
        row13[i] = (unsigned char)((i % CACHE_H) * CACHE_W);
    for (i = 0, a = XRAM_VIEW; i < CACHE_SLOTS; i++, a += IMG24_BYTES) {
        slot_lo[i] = (unsigned char)(a & 0xFF);
        slot_hi[i] = (unsigned char)(a >> 8);
    }
    for (i = 0, a = XRAM_ANIM; i < 24; i++, a += IMG24_BYTES) {
        anim_lo[i] = (unsigned char)(a & 0xFF);
        anim_hi[i] = (unsigned char)(a >> 8);
    }
    for (i = 0; i < PF_UNIT_COUNT; i++) {
        ushadow[i].width_height = MODE5_SIZE(24, 24);
        ushadow[i].attributes = MODE5_4BPP;
    }
    view_invalidate();
    vbl_frame = IRQ_FRAME;

    /* The black tile, for cells off the map and cells still loading. */
    RIA.addr0 = XRAM_BLANK;
    RIA.step0 = 1;
    for (a = 0; a < IMG24_BYTES; a++)
        RIA.rw0 = 0;

    /* The window's sprites have fixed places; only their images change. */
    for (r = 0, i = 0; r < MAP_WIN_TILES_H; r++)
        for (c = 0; c < MAP_WIN_TILES_W; c++, i++) {
            put_sprite(PF_SPRITE(i), c * TILE_PX, SCREEN_TOP + r * TILE_PX,
                       XRAM_BLANK, XRAM_PAL_GAME);
            put_size(PF_SPRITE(i), MODE5_SIZE(24, 24), MODE5_4BPP);
        }
    for (; i < PF_COUNT; i++) {
        put_sprite(PF_SPRITE(i), 0, SPR_PARKED_Y, XRAM_BLANK, XRAM_PAL_A);
        put_size(PF_SPRITE(i), MODE5_SIZE(24, 24), MODE5_4BPP);
    }

    /* The HUD's pictures and the cursor, all parked until there is something
     * to show. */
    for (i = 0; i < HUD_COUNT; i++)
        put_sprite(HUD_SPRITE(i), 0, SPR_PARKED_Y, XRAM_BLANK, XRAM_PAL_FG);
    put_size(HUD_SPRITE(HUD_WEAPON), MODE5_SIZE(48, 24), MODE5_4BPP);
    put_size(HUD_SPRITE(HUD_ITEM), MODE5_SIZE(48, 24), MODE5_4BPP);
    put_size(HUD_SPRITE(HUD_HEALTH), MODE5_SIZE(48, 52), MODE5_4BPP);
    for (i = 0; i < 3; i++)
        put_size(HUD_SPRITE(HUD_KEY0 + i), MODE5_SIZE(16, 16), MODE5_4BPP);
    put_size(HUD_SPRITE(HUD_CURSOR), MODE5_SIZE(28, 28), MODE5_2BPP);
}

/* Whether anything is still on its way to the screen; the probe reports it. */
unsigned char view_pending(void)
{
    return (unsigned char)(loading() || black || player_flip || player_put
                           || view_ptrs_dirty || view_units_dirty);
}
