/* The OPL2 and the VIA's timer, set up; and the music's stream, read.
 *
 * The player is src/sound.s. This is what runs once -- mapping the chip,
 * putting its registers where the DOS version's ssy_adlib_shut puts them, and
 * starting the clock the player ticks from -- and the main loop's half of the
 * music: opening a song and keeping its two buffers full.
 *
 * A song is a VGM file in the ROM, assets/convert/conv_adl.py's. The reads are
 * READ_XSTACK, called directly, 512 bytes at most, which is the XSTACK. One
 * starts while the main loop waits for VSYNC, before any tile load, and the
 * vblank work goes on while it runs (src/view.c). A song that loops is read to
 * just before its end and on from its loop, so every buffer is a full 512
 * bytes; the one that reaches the end of a song that plays once is the only
 * short one.
 */
#include <fcntl.h>
#include <rp6502.h>
#include <stdio.h>
#include <unistd.h>

#include "game/game.h"
#include "sound.h"
#include "view.h"
#include "xram.h"

_Static_assert(XRAM_OPL == 0xFD00u, "src/sound.s writes the OPL2 at page $FD");

unsigned char sfx_volume = 10;
unsigned char music_song = SONG_NONE;

#define MUS_BUF_BYTES 512               /* src/sound.s's too: the XSTACK */

/* src/sound.s */
extern unsigned char snd_subtick, snd_subticks;
extern unsigned char mus_on, mus_ready[2], mus_end_l[2], mus_end_h[2];
extern unsigned char mus_buf[2 * MUS_BUF_BYTES];
void mus_go(void);
void __fastcall__ mus_read_start(unsigned count);
int __fastcall__ mus_read_finish(unsigned char *dst);
void __fastcall__ snd_wait(unsigned char ticks);
unsigned char ldr_busy(void);           /* src/view_io.s */

/* The song's file, and where the reading is in it. */
int mus_fd = -1;
static long mus_pos, mus_end, mus_loop;
static unsigned mus_fill;               /* bytes in the buffer being filled */
static unsigned char mus_next;          /* which buffer that is */

/* The DOS version's file names, in SONG_ order. */
static const char *const song_name[] = {
    "ROM:metahead", "ROM:win", "ROM:lose",
    "ROM:getpsych", "ROM:metalbop", "ROM:roboattk", "ROM:rushing",
};

static const unsigned char opord[9] = {
    0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12
};

/* Portal 1, which the interrupts hand back as they found it. */
static void opl_write(unsigned char reg, unsigned char val)
{
    RIA.addr1 = XRAM_OPL + reg;
    RIA.rw1 = val;
}

/* Timer 1 free-running, interrupting every latch + 2 cycles. The writes are
 * the VIA's own order: the high byte of the counter loads it and starts it. */
#pragma optimize(push, off)
static void via_start(unsigned latch)
{
    VIA.ier = 0x7F;                     /* every VIA interrupt off */
    VIA.acr = (VIA.acr & 0x3F) | 0x40;  /* timer 1 continuous, PB7 untouched */
    VIA.t1_lo = (unsigned char)latch;
    VIA.t1_hi = (unsigned char)(latch >> 8);
    VIA.ier = 0xC0;                     /* timer 1 on */
}
#pragma optimize(pop)

void sound_init(void)
{
    unsigned long cycles;
    unsigned char i, op;

    SOUND_EFFECT = 0xFF;

    /* Mapping it resets the chip, clears the page and turns the PSG off. Then
     * ssy_adlib_shut, which ssy_adlib_init is: waveform select on, every
     * operator silent, and the envelopes the DOS player expects to find. The
     * effects write all of their channel's registers anyway; this is the
     * state the music starts from. */
    xreg_ria_opl(XRAM_OPL);
    opl_write(0x01, 0x20);
    for (i = 0x20; i < 0xA0; i++)
        opl_write(i, 0xFF);
    for (i = 0; i < 9; i++) {
        op = opord[i];
        opl_write(0x60 + op, 0xE0);
        opl_write(0x63 + op, 0xE0);
        opl_write(0x80 + op, 0x0E);
        opl_write(0x83 + op, 0x0E);
    }

    /* A tick is PHI2 / 72 cycles: kHz * 1000 / 72. Past 65,537 the timer
     * cannot count it in one go, so it counts a whole fraction of it. The
     * RP6502-PICO rounds PHI2 up to what it can make, so this asks the RIA
     * what it is rather than assuming 8 MHz. */
    cycles = (unsigned long)ria_attr_get(RIA_ATTR_PHI2_KHZ) * 125u / 9u;
    snd_subticks = (unsigned char)(cycles / 65537u + 1);
    snd_subtick = snd_subticks;
    via_start((unsigned)(cycles / snd_subticks) - 2);
}

/* The next read the song needs, started; 1 if one is in flight now. For the
 * loader in src/view.c, which retires it with music_retire. */
unsigned char music_read(void)
{
    unsigned n;
    long left;

    if (mus_fd < 0 || mus_ready[mus_next])
        return 0;
    left = mus_end - mus_pos;
    if (left <= 0)
        return 0;                       /* a song that plays once, all read */
    n = MUS_BUF_BYTES - mus_fill;
    if (left < (long)n)
        n = (unsigned)left;
    mus_read_start(n);
    return 1;
}

/* The read is done: its bytes into the buffer, and the buffer handed to the
 * player once it is full, or holds the end of the song. At the end of a song
 * that loops the reading goes back to the loop, and the same buffer fills on
 * from there with the next read. */
void music_retire(void)
{
    int n = mus_read_finish(mus_buf + mus_next * MUS_BUF_BYTES + mus_fill);
    unsigned end;

    if (n <= 0) {
        mus_end = mus_pos;              /* an error: play what there is, */
        mus_loop = 0;                   /* once */
        n = 0;
    }
    mus_fill += n;
    mus_pos += n;
    if (mus_pos >= mus_end && mus_loop) {
        lseek(mus_fd, mus_loop, SEEK_SET);
        mus_pos = mus_loop;
    }
    if (mus_fill == MUS_BUF_BYTES || (mus_pos >= mus_end && mus_fill)) {
        end = (unsigned)(mus_buf + mus_next * MUS_BUF_BYTES + mus_fill);
        mus_end_l[mus_next] = (unsigned char)end;
        mus_end_h[mus_next] = (unsigned char)(end >> 8);
        mus_ready[mus_next] = 1;        /* last: the player may take it now */
        mus_next ^= 1;
        mus_fill = 0;
    }
}

static unsigned long le32(const unsigned char *p)
{
    return p[0] | (unsigned)p[1] << 8 | (unsigned long)p[2] << 16
         | (unsigned long)p[3] << 24;
}

/* A song from its start: the VGM header says where its commands are and where
 * it loops; both buffers are filled before it plays. The chip's channels 1-8
 * are as ssy_music_stop leaves them, which is what the converter expects. */
void __fastcall__ music_play(unsigned char song)
{
    unsigned char head[0x40];
    unsigned long loop;

    music_stop();
    mus_fd = open(song_name[song], O_RDONLY);
    if (mus_fd < 0)
        return;
    if (read_xstack(head, sizeof(head), mus_fd) != sizeof(head)) {
        music_stop();
        return;
    }
    music_song = song;
    mus_pos = 0x34 + le32(head + 0x34);
    mus_end = 0x04 + le32(head + 0x04);
    loop = le32(head + 0x1C);
    mus_loop = loop ? 0x1C + loop : 0;
    if (mus_loop)
        --mus_end;                      /* the $66 at the end: go round */
    lseek(mus_fd, mus_pos, SEEK_SET);
    mus_fill = 0;
    mus_next = 0;
    mus_ready[0] = mus_ready[1] = 0;
    while (music_read()) {              /* both buffers, or all of a short one */
        while (ldr_busy())
            ;
        music_retire();
    }
    if (mus_ready[0])
        mus_go();
}

/* ssy_music_stop: the song stops where it is, and channels 1-8 go silent, the
 * carrier at its lowest level and the instrument cleared, as DOS leaves them
 * for the next song.
 *
 * DELIBERATE CHANGE. DOS clears the instrument with its notes still sounding.
 * Cleared, a note's rates are 0, so it stays at whatever level it had reached,
 * and the next song's first volume write brings it back up on any channel
 * that song never plays: after level a's song the lose jingle went on ringing
 * with two of its notes. So every voice is let go first, at the fastest
 * release, and the clearing waits until they have died away. */
void music_stop(void)
{
    unsigned char c, op, key;

    mus_on = 0;
    view_quiesce();                     /* a read of the old song in flight */
    if (music_song != SONG_NONE) {
        for (c = 1; c < 9; c++) {
            op = opord[c];
            opl_write(0x80 + op, 0x0F);
            opl_write(0x83 + op, 0x0F);
            RIA.addr1 = XRAM_OPL + 0xB0 + c;
            key = RIA.rw1;
            opl_write(0xB0 + c, key & ~0x20);
        }
        snd_wait(2);
    }
    for (c = 1; c < 9; c++) {
        op = opord[c];
        opl_write(0x43 + op, 0xFF);
        opl_write(0xC0 + c, 0);
        opl_write(0x20 + op, 0);
        opl_write(0x40 + op, 0);
        opl_write(0x60 + op, 0);
        opl_write(0x80 + op, 0);
        opl_write(0xE0 + op, 0);
        opl_write(0x63 + op, 0);
        opl_write(0x83 + op, 0);
        opl_write(0x23 + op, 0);
        opl_write(0xE3 + op, 0);
    }
    if (mus_fd >= 0)
        close(mus_fd);
    mus_fd = -1;
    music_song = SONG_NONE;
}
