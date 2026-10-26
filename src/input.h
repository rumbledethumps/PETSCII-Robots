#ifndef PETSCII_INPUT_H
#define PETSCII_INPUT_H

/* Codes for keys the X16 never had, chosen clear of every code translate()
 * makes otherwise: F6 where the PETSCII F keys would put it, and SHIFT+TAB. */
#define KEY_F6        139
#define KEY_SHIFT_TAB 0x18
#define KEY_SHIFT_C   195             /* the X16's code for its cheat key */
/* And the X16's for three more shifted keys: 2.1's music key, and its effects
 * volume down and up, SHIFT+[ and SHIFT+]. */
#define KEY_SHIFT_M   205
#define KEY_FX_DOWN   186
#define KEY_FX_UP     192

void input_init(void);
void plat_input_poll(void);             /* the keyboard scan, from VSYNC */
unsigned char plat_getin_keys(void);    /* the queue, without the gamepad */
void plat_unget_key(void);              /* the last of those, back in front */
unsigned char plat_getin(void);         /* what KERNAL GETIN returned */
void plat_clear_key_buffer(void);

#endif
