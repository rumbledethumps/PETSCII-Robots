#ifndef PETSCII_SOUND_H
#define PETSCII_SOUND_H

/* 2.1's effects volume, SFX_VOLUME ($4140): 0-15, from 10. See src/sound.s. */
extern unsigned char sfx_volume;

/* The song playing, SONG_NONE for none, and still the jingle's once it has
 * ended. The songs are 2.1's slots, which the DOS version's fill: METAHEAD,
 * WIN, LOSE, and four for the levels in turn. */
extern unsigned char music_song;
#define SONG_TITLE  0
#define SONG_WIN    1
#define SONG_LOSE   2
#define SONG_LEVEL  3                   /* + SELECTED_MAP % 4 */
#define SONG_NONE   0xFF

/* The OPL2 mapped and set up as the DOS version leaves it, and the VIA's
 * timer started. Once, at boot. */
void sound_init(void);

/* From the start, looping as the DOS version loops it, or once for the win
 * and lose jingles, as 2.1 plays them. */
void __fastcall__ music_play(unsigned char song);
void music_stop(void);

/* For the loader in src/view.c: start the song's next read if a buffer wants
 * it, 1 if one is in flight now; and take its bytes once it is done. */
unsigned char music_read(void);
void music_retire(void);

#endif
