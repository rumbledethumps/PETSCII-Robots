#ifndef PETSCII_PALETTE_H
#define PETSCII_PALETTE_H

/* The Amiga version's 4-bit RGB palettes, from assets/convert/conv_amiga.py;
 * the intro's is X16 2.1's title palette, which is the Amiga's with FFF for
 * its EEE. */
extern const unsigned amiga_pal_game[16];
extern const unsigned amiga_pal_intro[16];
extern const unsigned amiga_pal_gameover[16];

/* The fade, 0 black to 15 the colours themselves: see src/palette.c. */
extern unsigned char pal_level;

void pal_init(void);
void __fastcall__ pal_picture(const unsigned *rgb4);
void pal_picture_black(void);

/* The title's own colours for pic_text's 13 and 14, RGB4 or clear. */
#define PAL_CLEAR 0x8000u
void __fastcall__ pal_title_inks(unsigned ink13, unsigned ink14);
void pal_fade_out(void);
void pal_fade_in(void);
void pal_vblank(void);

#endif
