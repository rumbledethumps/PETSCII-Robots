#ifndef PETSCII_LIVEMAP_H
#define PETSCII_LIVEMAP_H

/* The live map: see src/livemap.c. */

/* 0 while the playfield shows; src/livemap.s tests bit 7. */
extern unsigned char livemap_on;
#define LIVEMAP_ON     0x80

/* Whether the robots show on it; it starts off and stays as it was set. */
extern unsigned char livemap_robots;

void livemap_toggle(void);
void livemap_robot_dots(void);
void livemap_stop(void);
void livemap_frame(void);

#endif
