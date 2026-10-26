/* The live map, as the Amiga plays it.
 *
 * TAB puts the whole 128x64 map where the playfield was, and the game carries
 * on underneath it: walk, fire, search, use. Every unit's dot follows it, and
 * every tile the game writes into MAP is drawn again as it changes. TAB again
 * puts the playfield back. SHIFT+TAB shows the robots on it or stops, whether
 * the map is up or not, and the choice stays until it is changed again; it
 * starts off. Those are the Amiga's keys, and the Amiga's defaults.
 *
 * The map is a mode 3 picture on plane 1, 256x128 at the Amiga's place, 20
 * lines down the playfield, two pixels by two a square. It is drawn into the
 * tile cache's memory, so the playfield's sprites go below the screen while it
 * is up (view_hide). When it goes, the playfield stays dark until the cache has
 * loaded again (view_show), as after a jump. The drawing that has to be quick
 * -- the whole map, and a square whenever MAP changes -- is src/livemap.s.
 */
#include <rp6502.h>

#include "game/game.h"
#include "livemap.h"
#include "platform.h"
#include "view.h"
#include "xram.h"

_Static_assert(XRAM_VIEW == 0, "src/livemap.s draws the map at XRAM 0");

unsigned char livemap_on, livemap_robots;

/* Set by src/livemap.s whenever it draws a square, which may be under a dot. */
unsigned char livemap_redot;

void livemap_draw(void);

/* The units that can have a dot: the player, the robots in 1-27, and the
 * rafts among 32-47. What each one shows, and where, as last drawn. */
#define DOTS     48
#define DOT_NONE 0xFF
#define WHITE    0x11
#define BLACK    0x00
static unsigned char dot_c[DOTS], dot_x[DOTS], dot_y[DOTS];
static unsigned char want_c[DOTS], want_x[DOTS], want_y[DOTS];
static unsigned char blink;

static void plot(unsigned char x, unsigned char y, unsigned char c)
{
    unsigned a = XRAM_VIEW + ((unsigned)y << 8) + x;
    RIA.step0 = 1;
    RIA.addr0 = a;
    RIA.rw0 = c;
    RIA.addr0 = a + 128;
    RIA.rw0 = c;
}

/* What unit i's dot should be this frame. The player blinks white and black,
 * about thirteen frames each; robots of a moving kind are white once SHIFT+TAB
 * has asked for them, and rafts always, unless the player stands on one. */
static unsigned char dot_for(unsigned char i)
{
    unsigned char t = UNIT_TYPE[i];

    if (UNIT_LOC_X[i] >= MAP_W || UNIT_LOC_Y[i] >= MAP_H)
        return DOT_NONE;
    if (!i)
        return blink < 128 ? WHITE : BLACK;
    if (t == 22)
        return UNIT_LOC_X[i] == UNIT_LOC_X[0] && UNIT_LOC_Y[i] == UNIT_LOC_Y[0]
               ? DOT_NONE : WHITE;
    if (i < 28 && livemap_robots
        && (t <= 5 || t == 9 || t == 17 || t == 18) && t)
        return WHITE;
    return DOT_NONE;
}

/* Every vblank while the map is up. A dot that has moved or gone is wiped
 * first, all of them, and then the dots are drawn, the player last: wiping a
 * square after a dot went on it would lose the dot. The Amiga does it in one
 * pass and can lose them that way. Both passes work from one reading of where
 * the units are, so what is drawn is always what is remembered. */
void livemap_frame(void)
{
    unsigned char i, c, again = livemap_redot;

    blink += 10;
    livemap_redot = 0;
    for (i = 0; i < DOTS; i++) {
        c = want_c[i] = dot_for(i);
        want_x[i] = UNIT_LOC_X[i];
        want_y[i] = UNIT_LOC_Y[i];
        if (dot_c[i] != DOT_NONE
            && (c == DOT_NONE
                || dot_x[i] != want_x[i] || dot_y[i] != want_y[i])) {
            plot(dot_x[i], dot_y[i],
                 amiga_livemap[MAP[((unsigned)dot_y[i] << 7) | dot_x[i]]]);
            dot_c[i] = DOT_NONE;
            again = 1;
        }
    }
    i = DOTS;
    do {
        --i;
        c = want_c[i];
        if (c != DOT_NONE && (again || c != dot_c[i])) {
            plot(want_x[i], want_y[i], c);
            dot_c[i] = c;
            dot_x[i] = want_x[i];
            dot_y[i] = want_y[i];
        }
    } while (i);
}

/* The playfield off the screen, the map drawn while nothing shows it, and then
 * the picture on. The dots follow at the next vblank. */
static void open(void)
{
    unsigned char i;

    view_hide();
    livemap_draw();
    for (i = 0; i < DOTS; i++)
        dot_c[i] = DOT_NONE;
    livemap_on = LIVEMAP_ON;
    plat_overlay_at(0, SCREEN_TOP + 20, MAP_W * 2, MAP_H * 2, XRAM_PAL_GAME);
}

/* TAB, and SELECT+LEFT on the pad: the map, or the playfield again. */
void livemap_toggle(void)
{
    plat_play_sound(SFX_BEEP2);
    if (!livemap_on) {
        open();
    } else {
        livemap_on = 0;
        plat_overlay_hide();
        view_show();
    }
}

/* SHIFT+TAB, and SELECT+DOWN on the pad: the robots on the map, or not. The
 * next vblank draws or wipes their dots. */
void livemap_robot_dots(void)
{
    if (livemap_on)
        plat_play_sound(SFX_BEEP2);
    livemap_robots ^= 1;
}

/* The map's memory is about to hold something else -- a picture -- so nothing
 * may draw on it from now on. The playfield comes back with the next level. */
void livemap_stop(void)
{
    livemap_on = 0;
}
