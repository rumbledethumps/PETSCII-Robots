#ifndef PETSCII_PROBE_H
#define PETSCII_PROBE_H

/* A fixed block the game refreshes once a frame, so tests can assert on state
 * without knowing where the linker put anything.
 *
 * It lives in XRAM rather than RAM because XRAM addresses are chosen by the
 * program: XRAM_PROBE is a member of xram_layout_t in xram.h, whereas a RAM
 * symbol moves every time the code above it changes size, which would make
 * every `peek` in tests/emu a maintenance burden.
 *
 * Twenty XRAM writes a frame is nothing, so it stays in release builds and a
 * shipped ROM is debuggable in the field.
 */

#define PROBE_MAGIC_0 'P'
#define PROBE_MAGIC_1 'R'

/* Byte offsets from XRAM_PROBE. docs/test-abi.md describes the block. */
#define PROBE_MAGIC     0   /* 2 bytes, 'P' 'R'                     */
#define PROBE_STATE     2   /* PROBE_STATE_* below                  */
#define PROBE_LEVEL     3   /* 0..17                                */
#define PROBE_PLAYER_X  4
#define PROBE_PLAYER_Y  5
#define PROBE_HEALTH    6
#define PROBE_ROBOTS    7   /* live units in slots 1..27            */
#define PROBE_RNG       8   /* RANDOM, the LFSR's low byte          */
#define PROBE_FRAME     9   /* wraps at 256                         */
#define PROBE_WINDOW_X 10
#define PROBE_WINDOW_Y 11
/* A 16-bit checksum over every live unit's type and position. It changes the
 * moment any robot moves, which makes "is the AI running" a peek rather than a
 * screenshot, and with the RNG starting from zero at power-on it is
 * reproducible enough to pin a whole AI pass as a regression. */
#define PROBE_UNITS_LO 12
#define PROBE_UNITS_HI 13
/* Units the last redraw put in the window, i.e. non-zero entries in
 * MAP_PRECALC. */
#define PROBE_VISIBLE  14
/* SELECTED_WEAPON in the low nibble, SELECTED_ITEM in the high one. */
#define PROBE_WEAPON_ITEM 15
/* Images read from ROM:images since boot, wrapping: tiles into the cache, the
 * player's frames and the HUD's pictures. */
#define PROBE_LOADS    16
/* Unit sprites the playfield shows. */
#define PROBE_UNITS    17
/* Steps of the animated tiles' group A -- the water, the flag, the server
 * light -- every thirty AI ticks, wrapping; they show frame ANIM & 3 or & 1. */
#define PROBE_ANIM     18
/* 1 while anything is still on its way to the screen: a load in flight or to
 * come, sprites the next vblank will change, a player frame to show. */
#define PROBE_PENDING  19
/* Window cells showing black because their tile has not loaded yet. */
#define PROBE_BLANK    20
/* Vblanks that came more than a frame after the last, wrapping. */
#define PROBE_OVERRUN  21
/* The live map: 0 off, 1 up, 2 up with the robots. */
#define PROBE_LIVEMAP  22
/* The last checkpoint the game reached, PROBE_AT_* below; tests wait on it
 * with `wait xram:XRAM_PROBE+PROBE_CHECK PROBE_AT_MENU`. */
#define PROBE_CHECK    23
#define PROBE_SIZE     32

#define PROBE_STATE_BOOT    0
#define PROBE_STATE_TITLE   1
#define PROBE_STATE_PLAYING 2
#define PROBE_STATE_DEAD    3
#define PROBE_STATE_WON     4

/* The checkpoints. Each is written once, where it is reached, and stays until
 * the next, so a wait for one is a wait for the game to get there again. */
#define PROBE_AT_NONE   0   /* since power-on, before the first menu       */
#define PROBE_AT_MENU   1   /* the intro menu is up and reading keys       */
#define PROBE_AT_PLAY   2   /* a level has loaded and play begins          */
#define PROBE_AT_AI60   3   /* the main loop has run 60 times since then   */
#define PROBE_AT_AI300  4   /* and 300                                     */

#endif
