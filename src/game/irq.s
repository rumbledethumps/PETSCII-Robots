; The game tick.
;
; Sixty times a second, tied to the display: timers count down, the menu's
; flash steps, the game clock advances, and BACKGROUND_TASKS gets its cue to
; run one pass of unit AI. The X16 does this from VERA's VBLANK interrupt; the
; RIA raises the same signal, so the structure ports directly.
;
; It has to be an interrupt rather than something the main loop does, because
; the game waits by spinning: SEARCH_OBJECT sits on BGTIMER2 calling
; BACKGROUND_TASKS until it reaches zero, and nothing inside that loop would
; ever decrement it.
;
; $FFF0 is an enable mask on write and a triggered-signal register on read, and
; reading clears what it reports -- so testing and acknowledging are the same
; instruction.
;
; Video register updates happen here too, and only here. This is the start of
; vblank, so a plane's scroll position or a palette entry changed now lands
; between frames instead of part way down one. The main loop decides what the
; registers should say and leaves it in RAM; this pushes it out.
;
; That means touching XRAM from an interrupt, and the two portals -- their
; addresses and step values -- are global state with no save area, so an
; interrupt that repointed one in the middle of a redraw would scribble the
; wrong bytes. The handler saves and restores portal 1 around its writes. Six
; bytes at sixty hertz is nothing, and it keeps the main loop free to use both
; portals without knowing this exists.
;
; This handler reaches C -- the flash step and the keyboard scan are C -- and
; cc65 compiles every C function against twenty bytes of shared zero-page
; scratch: the C stack pointer, sreg, regsave, ptr1-4 and tmp1-4. An interrupt
; that calls C without putting those back hands the interrupted function its
; own pointers rewritten. When the tile blitter was C, a tile would
; occasionally draw its three rows into the bitmap plane instead of the
; character plane and sit there; the renderer that replaced it is C as well.
;
; cc65 already solves this. set_irq() installs a C level handler and the
; runtime's clevel_irq wrapper saves and restores that zero page, switches to a
; separate C stack and preserves jmpvec around the call. So this is registered
; through set_irq rather than as a bare .interruptor, and returns A = 1 for
; IRQ_HANDLED and 0 for IRQ_NOT_HANDLED, which is what a cc65 irq_handler is.

        .include "petscii.inc"
        .include "rp6502.inc"

        .export _petscii_irq
        .import _plat_flash_step, _plat_input_poll
        .import _pal_vblank

        .segment "CODE"

_petscii_irq:
        lda     RIA_IRQ                 ; reading returns the triggered bits
        bmi     @vsync                  ; ...and clears them. bit 7 is VSYNC.
        lda     #0                      ; IRQ_NOT_HANDLED
        rts

@vsync:
        inc     IRQ_FRAME               ; the main loop's tick reference

        lda     #1
        sta     BGTIMER1                ; BACKGROUND_TASKS runs once per tick

        lda     BGTIMER2                ; counts down to zero and stays there
        beq     @keytimer
        dec     BGTIMER2
@keytimer:
        lda     KEYTIMER
        beq     @flash
        dec     KEYTIMER

        ; The intro menu's flash: a step through SPRITECOLCHART every seven
        ; frames, always, as both X16 versions' interrupts step it (2.1's IRQ30,
        ; $419E). The menu shows the colour; src/platform.c, plat_menu_flash.
@flash:
        dec     SPRITECOLTIMER
        bne     @clock
        lda     #7
        sta     SPRITECOLTIMER
        inc     SPRITECOLSTATE
        lda     SPRITECOLSTATE
        cmp     #8
        bne     @clock
        lda     #0
        sta     SPRITECOLSTATE

@clock:
        jsr     UPDATE_GAME_CLOCK
        jsr     VBLANK_VIDEO
        lda     #1                      ; IRQ_HANDLED
        rts

; Push the staged video register values out, inside vblank.
;
; Portal 1 is borrowed and handed back exactly as it was found, so nothing in
; the main loop has to know an interrupt happened.
VBLANK_VIDEO:
        lda     RIA_ADDR1
        pha
        lda     RIA_ADDR1+1
        pha
        lda     RIA_STEP1
        pha

        ; The damage and EMP flashes count down here, where the X16 ran them,
        ; and set the palettes' fade; then the palettes are written if the fade
        ; or the colours changed, this frame or in the main loop's last one --
        ; a screen fading in or out. src/palette.c and src/palette.s. Screen
        ; shake moves sprites the vblank work rewrites, so it is there:
        ; src/view.c.
        jsr     _plat_flash_step
        jsr     _pal_vblank

        ; The keyboard scan, where the KERNAL's own scan ran: in the interrupt.
        ; A press is an edge and only whoever is looking when it happens sees
        ; it, so scanning from the main loop drops taps that start and finish
        ; inside one pass. Reads XRAM through this portal, hence inside the save.
        jsr     _plat_input_poll

        pla
        sta     RIA_STEP1
        pla
        sta     RIA_ADDR1+1
        pla
        sta     RIA_ADDR1
        rts

; The game clock, from the pre-release's x16Robots.ASM. Sixty ticks to the second.
UPDATE_GAME_CLOCK:
        lda     CLOCK_ACTIVE
        beq     @out
        inc     CYCLES
        lda     CYCLES
        cmp     #60
        bne     @out
        lda     #0
        sta     CYCLES
        inc     SECONDS
        lda     SECONDS
        cmp     #60
        bne     @out
        lda     #0
        sta     SECONDS
        inc     MINUTES
        lda     MINUTES
        cmp     #60
        bne     @out
        lda     #0
        sta     MINUTES
        inc     HOURS
@out:   rts
