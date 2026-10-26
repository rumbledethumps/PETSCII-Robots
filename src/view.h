#ifndef PETSCII_VIEW_H
#define PETSCII_VIEW_H

/* The playfield: 77 sprites over the tile cache, the units over them, and the
 * player on top. See src/view.c. */

/* The art's tables, from assets/convert/conv_amiga.py (amiga_tables.s). The
 * faces are X16 2.1's eyes, THREE_FACES, in the intro palette, and the unit
 * bank picks the records of XRAM_UNITS, all of them 2.1's art. */
extern const unsigned char amiga_faces[3 * 10 * 8];
extern const unsigned char amiga_livemap[256];
extern const unsigned char amiga_unit_bank[256];
extern const unsigned char amiga_bank_pal[38];
extern const unsigned char amiga_tile_anim[256];

/* Records of ROM:images, 288 bytes each. */
#define IMG_TILES       0       /* 253 tiles, by tile number                */
#define IMG_PLAYER      253     /* 57: 2.1 sprites 0-47, 96 (dead), 88-95   */
#define IMG_ITEMS       310     /* 6 x 2 records: pistol, plasma, medkit,   */
                                /*   EMP, magnet, time bomb                  */
#define IMG_HEALTH      322     /* 6 x 5 records                            */
#define IMG_COUNT       352

/* How many times each group of animated tiles has stepped -- A the water, the
 * flag and the server light, B the compactor and the fans, X16 2.1's two -- and
 * the cinema marquee's position. */
extern unsigned char ANIM_STATE, ANIM_STATE_B, CINEMA_STATE;

/* For the probe: loads since boot (wrapping), unit sprites shown, window cells
 * showing black while their tile loads, and vblanks that came late. */
extern unsigned char view_loads, view_units, view_blank, view_overruns;

/* Screen shake's offset, 0 or 3 pixels right: whatever places a sprite or a
 * plane adds it. */
extern unsigned char shake_dx;

void view_init(void);
void view_invalidate(void);
void view_suspend(void);
void view_resume(void);
void view_hide(void);
void view_show(void);
void view_request(void);
void view_anim_tick(void);
void view_player(void);
void __fastcall__ view_load(unsigned xaddr, unsigned record, unsigned count);

/* The frame: see src/view.c. */
void view_wait(void);
void view_hook(void);
void view_idle(void);
void view_vblank(void);
void view_quiesce(void);
void view_flush(void);
unsigned char __fastcall__ view_ready(unsigned char facing);
unsigned char view_pending(void);

#endif
