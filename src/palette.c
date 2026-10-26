/* The palettes, made from the Amiga's, and faded as the Amiga fades them.
 *
 * The Amiga has one 16-colour palette per screen, 4 bits a channel. The RP6502
 * gives every sprite and plane its own palette, RGB555 with an opacity bit, so
 * each Amiga palette becomes several here, differing only in which entries are
 * transparent and which stand in for black (xram.h, palettes_t):
 *
 *   game      the game palette, all opaque: the tiles and the live map
 *   fg        game, entry 0 transparent: units drawn from tiles, shots,
 *             explosions, HUD pictures
 *   a         game, 0 transparent, 8 black: the player, the text, the HUD
 *             frame
 *   b         2.1's unit palette: 0 transparent, 1 black, 2 white, the game
 *             colours but 039: the robots, their wrecks, the bomb, the magnet,
 *             and the cursor, 2bpp, from its first four
 *   pic       the intro or game-over palette, opaque
 *   pic_text  pic, 0 transparent, 8 black: the text over a picture; on the
 *             title 13 and 14 are the title's own, see pal_title_inks
 *
 * The Amiga draws a sprite's black outline with colour 0 and keeps a separate
 * mask; here colour 0 is the transparent one, so conv_amiga.py moves each
 * frame's black to an entry that frame does not otherwise use -- 8 for the
 * player -- and these palettes put colour 0 there. The robots keep 2.1's own
 * order, black at 1, in the order _amiga_pal_b_order gives.
 *
 * All of them fade together, as the Amiga's one palette does: a level from 0
 * to 15 and a colour to fade towards. The screens fade to black and back over
 * fifteen frames each; a hit flashes red and an EMP blue, nine frames back to
 * normal. The interrupt writes them (src/palette.s) whenever the level or the
 * colours change, so a fade is only ever a value left in RAM.
 */
#include <rp6502.h>

#include "game/game.h"
#include "palette.h"
#include "view.h"
#include "xram.h"

_Static_assert(XRAM_PAL_FG == XRAM_PAL_GAME + 32
               && XRAM_PAL_A == XRAM_PAL_GAME + 64
               && XRAM_PAL_B == XRAM_PAL_GAME + 96
               && XRAM_PAL_PIC == XRAM_PAL_GAME + 128
               && XRAM_PAL_PIC_TEXT == XRAM_PAL_GAME + 160,
               "src/palette.s writes the six palettes in one run");

/* For src/palette.s. */
const unsigned pal_xram = XRAM_PAL_GAME;
unsigned char pal_level, pal_pic_black = 1, pal_dirty;
unsigned pal_base;
const unsigned *pal_pic = amiga_pal_intro;
unsigned pal_ink[2];            /* the title's, for pic_text's 13 and 14 */
unsigned char pal_inked;        /* while this is set: pal_title_inks */

void pal_write(void);

/* While a screen fades the flashes leave the level alone. */
static unsigned char fading;

/* The flash in progress, and the colour it locked when it began. */
static unsigned char flashing;

#define RED  0x0F00
#define BLUE 0x000F

static void level(unsigned char l)
{
    pal_level = l;
    pal_dirty = 1;
}

/* Black, before anything is on the screen: the Amiga starts there too, and the
 * intro fades in. The interrupt is not running yet, so this writes them. */
void pal_init(void)
{
    pal_level = 0;
    pal_base = 0;
    pal_write();
}

/* A new picture brings its own colours: any the title gave the text are gone
 * with the one before. */
void __fastcall__ pal_picture(const unsigned *rgb4)
{
    pal_pic = rgb4;
    pal_pic_black = 0;
    pal_inked = 0;
    pal_dirty = 1;
}

/* A black picture, for a screen that is only text: the text keeps the colours
 * of the picture before, but for the title's own. */
void pal_picture_black(void)
{
    pal_pic_black = 1;
    pal_inked = 0;
    pal_dirty = 1;
}

/* X16 2.1's title pulses its selected option through greys and fades its
 * credits in and out, in colours its picture does not have. The text there
 * draws them with pic_text's entries 14 and 13, which take these in place of
 * the picture's until the next picture, so pic, the picture's own, keeps its
 * white. They fade with the rest; PAL_CLEAR is no colour at all, as 2.1's
 * colour 0 is. The menu sets them on every pass, and only a change has the
 * palettes written. */
void __fastcall__ pal_title_inks(unsigned ink13, unsigned ink14)
{
    if (pal_inked && pal_ink[0] == ink13 && pal_ink[1] == ink14)
        return;
    pal_ink[0] = ink13;
    pal_ink[1] = ink14;
    pal_inked = 1;
    pal_dirty = 1;
}

/* The Amiga's fadeScreen(level, false): a level a frame, the game waiting. The
 * frame's vblank work and loads go on, and keys pressed meanwhile stay
 * queued. */
static void to(unsigned char target)
{
    unsigned char f;
    fading = 1;
    flashing = 0;           /* a flash still running ends with the fade */
    while (pal_level != target) {
        level((unsigned char)(pal_level < target ? pal_level + 1
                                                 : pal_level - 1));
        f = IRQ_FRAME;
        while (f == IRQ_FRAME)
            view_idle();
    }
    fading = 0;
}

/* To black, fifteen frames. A flash leaves its colour as the one to fade
 * towards, so black is put back first, as GOM4 does. */
void pal_fade_out(void)
{
    pal_base = 0;
    to(0);
}

void pal_fade_in(void)
{
    pal_base = 0;
    to(15);
}

/* From the interrupt, every frame: the damage and EMP flashes. The game sets
 * BORDER[0] (a hit, red) or BGFLASH[0] (the EMP, blue) to 10; each counts down
 * a frame at a time and the screen sits at 15 minus the count, so it jumps 60%
 * of the way to the colour and comes back in nine frames. The colour is the
 * one the flash began with, though another starts over it, as on the Amiga,
 * which keeps one counter for both. */
void plat_flash_step(void)
{
    unsigned char n;

    if (BORDER[0])
        BORDER[0]--;
    if (BGFLASH[0])
        BGFLASH[0]--;
    n = BORDER[0] > BGFLASH[0] ? BORDER[0] : BGFLASH[0];
    if (fading)
        return;
    if (n) {
        if (!flashing) {
            flashing = 1;
            pal_base = BGFLASH[0] > BORDER[0] ? BLUE : RED;
        }
        level((unsigned char)(15 - n));
    } else if (flashing) {
        flashing = 0;
        level(15);
    }
}
