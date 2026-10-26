/* Keyboard, in the shape the game expects.
 *
 * The X16 build reads keys through KERNAL GETIN, which returns one PETSCII code
 * per call and zero when the buffer is empty. Every comparison in the ported
 * assembly is against those codes -- STANDARD_CONTROLS is literally
 * {73, 75, 74, 76, ...} for I K J L -- so the cheapest way to keep that code
 * unchanged is to keep producing the same codes.
 *
 * The RIA gives a 32-byte bit array of USB HID keycodes instead: bit N is set
 * while the key with HID code N is down. So this file does three things GETIN
 * did for free -- translate, detect the press rather than the hold, and repeat.
 *
 * SCANNING BELONGS IN THE INTERRUPT, which is where the KERNAL does it. That is
 * not a detail: a press is an edge, and an edge is only seen by whoever is
 * looking when it happens. Polling from the main loop instead loses a tap that
 * begins and ends inside one loop pass -- and a pass is not always one frame,
 * since a full window redraw can overrun -- and it also lets the press and the
 * repeat land in the same pass, which queues the key twice. Both were real:
 * brief taps moved two tiles at some phases of the repeat timer and none at
 * others, depending on where the tap fell relative to the loop.
 *
 * So plat_input_poll runs from the VSYNC handler, once per frame, exactly as
 * the KERNAL's own keyboard scan ran from its IRQ, and fills a queue that
 * plat_getin drains. That makes the queue a single producer, single consumer
 * ring: the interrupt only ever advances q_tail and the game only ever advances
 * q_head, each a single byte store, so neither needs to lock the other out.
 * plat_clear_key_buffer, which moves both, and plat_unget_key, which moves
 * q_head back towards q_tail, do.
 *
 * It reads XRAM through portal 1, which is the one src/game/irq.s saves and
 * restores around everything it does, so the main loop's portal 0 work is
 * untouched.
 */
#include <rp6502.h>

#include "game/game.h"
#include "input.h"
#include "platform.h"
#include "xram.h"

/* Bits 0-3 of byte 0 are special: bit 0 means no key is pressed, bits 1-3 are
 * the lock LEDs. Real keys start at HID code 4. */
#define key_down(bits, code) ((bits)[(code) >> 3] & (1 << ((code) & 7)))
#define HID_NONE_DOWN (1 << KEYBOARD_NO_KEY)

#define HID_A     0x04
#define HID_Z     0x1D
#define HID_1     0x1E
#define HID_0     0x27
#define HID_ENTER 0x28
#define HID_ESC   0x29
#define HID_TAB   0x2B
#define HID_SPACE 0x2C
#define HID_LBRACKET 0x2F
#define HID_RBRACKET 0x30
#define HID_F1    0x3A
#define HID_F12   0x45
#define HID_RIGHT 0x4F
#define HID_LEFT  0x50
#define HID_DOWN  0x51
#define HID_UP    0x52

/* KEY_REPEAT's own floor, from x16Robots.ASM 1999. The interesting rates are
 * not here: the game sets KEYTIMER itself after it acts -- 15 frames before the
 * first repeat of a move and 6 after that, 20 after firing or cycling -- and
 * this is only what KEY_REPEAT leaves behind when it re-injects. */
#define REPEAT_FLOOR 7

static unsigned char now[32], before[32];
static unsigned char queue[8], q_head, q_tail, q_last;

/* The keys physically down, as HID codes, oldest first -- so the last entry is
 * the one that arrived most recently and the one that should be repeating.
 *
 * A single "which key is held" byte is not enough, and getting that wrong is
 * felt immediately: hold down, tap right, let right go, and the player carries
 * on right while you are holding down. The key that was released has to stop
 * repeating and whatever is still held has to take over, which means keeping
 * the whole set and the order they arrived in. Eight is more fingers than
 * anyone brings. */
static unsigned char held[8], held_n;

/* HID keycode -> the code the game compares against. These are the PETSCII
 * values KERNAL GETIN produced, so STANDARD_CONTROLS and every CMP in the
 * ported assembly work unchanged. */
static unsigned char translate(unsigned char hid)
{
    if (hid >= HID_A && hid <= HID_Z)
        return (unsigned char)('A' + (hid - HID_A));    /* letters, uppercase */
    if (hid >= HID_1 && hid <= HID_0)
        return (unsigned char)(hid == HID_0 ? '0' : '1' + (hid - HID_1));
    switch (hid) {
    case HID_SPACE: return 32;
    case HID_ENTER: return 13;
    case HID_TAB:   return 9;
    case HID_ESC:   return 3;      /* the X16's run/stop */
    case HID_LBRACKET: return '[';
    case HID_RBRACKET: return ']';
    case HID_RIGHT: return 0x1D;   /* PETSCII cursor right */
    case HID_LEFT:  return 0x9D;
    case HID_DOWN:  return 0x11;
    case HID_UP:    return 0x91;
    case HID_F1:    return 133;
    case HID_F1 + 1: return 137;   /* F2, as the X16 numbered them */
    case HID_F1 + 2: return 134;   /* F3 */
    case HID_F1 + 3: return 138;   /* F4 */
    case HID_F1 + 5: return KEY_F6;
    default:        return 0;
    }
}

#define HID_LSHIFT 0xE1
#define HID_RSHIFT 0xE5

/* The keys the game reads with SHIFT: TAB, the Amiga's key for the robots on
 * the live map, and C, the cheat the X16 and the Amiga both have; M, 2.1's
 * music key, and [ and ], its effects volume down and up. Anything else is the
 * same key with SHIFT or without. */
static unsigned char shifted(unsigned char code)
{
    if (!key_down(now, HID_LSHIFT) && !key_down(now, HID_RSHIFT))
        return code;
    switch (code) {
    case 9:   return KEY_SHIFT_TAB;
    case 'C': return KEY_SHIFT_C;
    case 'M': return KEY_SHIFT_M;
    case '[': return KEY_FX_DOWN;
    case ']': return KEY_FX_UP;
    default:  return code;
    }
}

static void push(unsigned char code)
{
    unsigned char next = (unsigned char)((q_tail + 1) & 7);
    if (code && next != q_head) {       /* a full queue drops, as a real one does */
        queue[q_tail] = code;
        q_tail = next;
    }
}

void input_init(void)
{
    unsigned char i;
    for (i = 0; i < 32; i++)
        before[i] = 0;
    q_head = q_tail = held_n = 0;
    xreg_ria_keyboard(XRAM_KEYBOARD);
}

/* One keyboard scan, from the VSYNC interrupt. Queues a code for every key that
 * went down since the last frame and keeps the held set up to date. Repeats are
 * not this routine's business; see plat_key_repeat. */
void plat_input_poll(void)
{
    unsigned char i, j, b, hid, code;

    RIA.addr1 = XRAM_KEYBOARD;
    RIA.step1 = 1;
    for (i = 0; i < 32; i++)
        now[i] = RIA.rw1;

    for (i = 0; i < 32; i++) {
        b = (unsigned char)(now[i] & ~before[i]);        /* newly pressed */
        if (!b)
            continue;
        for (hid = 0; hid < 8; hid++) {
            if (!(b & (1 << hid)))
                continue;
            /* Byte 0 bits 0-3 are the no-key flag and the lock LEDs. */
            if (i == 0 && hid < 4)
                continue;
            code = shifted(translate((unsigned char)((i << 3) | hid)));
            if (code) {
                push(code);
                if (held_n == 8) {      /* forget the oldest to make room */
                    for (j = 0; j < 7; j++)
                        held[j] = held[j + 1];
                    held_n = 7;
                }
                held[held_n++] = (unsigned char)((i << 3) | hid);
            }
        }
        before[i] = now[i];
    }
    for (i = 0; i < 32; i++)
        before[i] = now[i];

    /* Drop the ones that have been let go, keeping the rest in order. */
    for (i = 0, j = 0; i < held_n; i++)
        if (key_down(now, held[i]))
            held[j++] = held[i];
    held_n = j;
}

/* The key queue alone, with no gamepad. The in-game loop wants this: the pad
 * has already had its turn there, in gamepad_pass, where a button means more
 * than a key code can carry. */
unsigned char plat_getin_keys(void)
{
    unsigned char code;
    if (q_head == q_tail)
        return 0;
    code = queue[q_head];
    q_head = (unsigned char)((q_head + 1) & 7);
    return q_last = code;
}

/* The code plat_getin_keys last returned, back at the front of the queue, for
 * a step that has to wait for the tile cache: the next read gets it again,
 * ahead of anything typed since. A full queue drops it, as it drops a key. */
void plat_unget_key(void)
{
    unsigned char prev;

    __asm__("sei");
    prev = (unsigned char)((q_head - 1) & 7);
    if (prev != q_tail) {
        queue[prev] = q_last;
        q_head = prev;
    }
    __asm__("cli");
}

void plat_clear_key_buffer(void)
{
    unsigned char i;

    /* Both ends at once, so the interrupt must not be part way through a scan.
     * The keys that are down are forgotten as well, as the Amiga's clear
     * forgets its held key: one still down after a search, a move or a use
     * goes back in the held set only when it is let go and pressed again, so
     * it never walks the player on its own. The PET and the pre-release only
     * held it off for the 20 frames below, which a slow finger outlasts. */
    __asm__("sei");
    q_head = q_tail = held_n = 0;
    __asm__("cli");

    /* The gamepad's latches are part of the buffer now that plat_getin falls
     * back to them: a press left sitting in one is a keystroke waiting to be
     * read, and a routine that clears the buffer and then waits for input would
     * be answered by it immediately. That is a game-over screen appearing and
     * vanishing in the same frame. */
    for (i = 0; i < 12; i++)
        NEW_BUTTONS[i] = 0;
    /* CLEAR_KEY_BUFFER's tail, kept as the Amiga keeps it. With the held keys
     * forgotten it now only holds off a gamepad direction still down. */
    KEYTIMER = 20;
}

/* KEY_REPEAT, from x16Robots.ASM 1988. The main game loop calls this before
 * GETIN; the menus do not, which is why a menu acts on presses only and walking
 * repeats.
 *
 * What it means to do: when KEYTIMER runs out with a key still down, take that
 * key as pressed again. The X16 source tries it through $C5 and $028C, the
 * C64's LSTX and repeat delay, which on the X16 KERNAL are other variables, so
 * there it does nothing and a held key walks at the keyboard's own typematic
 * rate. The PET does it for real, and the Amiga, with key-up events, does it
 * directly. So does this: the newest key still down in the RIA's bit array is
 * pushed onto the queue GETIN reads.
 *
 * Reading what is down *now* is the whole point, and is why the original does
 * not have the fault this port did: hold down, tap right, let right go, and the
 * key that is still down is down, so the player goes down. A remembered "the
 * key being repeated" keeps repeating the one you let go of.
 */
void plat_key_repeat(void)
{
    unsigned char code, hid;

    if (q_head != q_tail)
        return;                         /* a real press is already waiting */
    if (KEYTIMER)
        return;
    /* The interrupt keeps the held set, so read its count and newest entry
     * together: a key let go in between would leave held_n - 1 past it. */
    __asm__("sei");
    code = held_n;
    hid = code ? held[code - 1] : 0;
    __asm__("cli");
    if (!code) {
        KEY_FAST = 0;                   /* KEYR1: back to the slow first repeat */
        KEYTIMER = REPEAT_FLOOR;
        return;
    }
    /* A held key repeats as its press was read, with SHIFT as it is now, so a
     * held SHIFT+M is not taken for M, the push key, nor a held SHIFT+] for
     * ]. TAB, SHIFT+TAB, F6 and SHIFT+M turn something on and off, and held
     * they would flip it back and forth, so none of them repeats; the Amiga's
     * do not either. Nor does SHIFT+C, which would play the cheat's sound
     * every seven frames. The volume keys do repeat. */
    code = shifted(translate(hid));
    if (code != 9 && code != KEY_SHIFT_TAB && code != KEY_F6
        && code != KEY_SHIFT_M && code != KEY_SHIFT_C)
        push(code);
    KEYTIMER = REPEAT_FLOOR;
}

/* What KERNAL GETIN returned: the next key code, or zero if none is waiting --
 * and a gamepad press if no key is.
 *
 * The merge belongs here rather than in each caller. The converted assembly
 * calls GETIN from MOVE_OBJECT and USER_SELECT_OBJECT and chooses its own pad
 * path on CONTROL == 2, which this port no longer sets, so without this the
 * cursor those routines put up could not be moved with the pad. Menus, the
 * elevator panel and the pause prompt get it for the same reason and for free.
 */
unsigned char plat_getin(void)
{
    unsigned char code = plat_getin_keys();
    return code ? code : plat_pad_key();
}
