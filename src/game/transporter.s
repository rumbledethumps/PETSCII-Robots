; The dematerialize effect, as X16 2.1 has it: DEMATERIALIZE at $5A1C in its
; ROBOTS.PRG, where the pre-release's was x16Robots.ASM lines 4817-4874.
;
; Unit type 23, which a transporter pad becomes when the player stands on it.
; It plays the medkit's sound, shows 2.1's eight frames of the player breaking
; up, UNIT_TILE 88 to 95, eight ticks each, then either ends the level or moves
; the player to the pad's target coordinates. Those 64 ticks are spent here,
; inside the AI pass, as 2.1 spends them: nothing else in the game runs until
; they are over, while the interrupt keeps the clock, the music and the keys
; going. It lives outside background_tasks.s only because David Murray kept it
; in the machine-specific file, and it jumps back into the AI loop the same way
; every other unit routine does.
;
; The pre-release ran it as an ordinary unit instead, 48 passes cycling a
; palette entry, and set its timer through a stale X, slot 40's rather than its
; own; docs/porting-notes.md has that history. 2.1's sets no timer.
;
; Four things are the RP6502's, each marked at its site. 2.1 calls
; DRAW_UNIT_SPRITES, which draws the units as they stand; here DRAW_MAP_WINDOW
; plans them, the player's first frame with them, and DISPLAY_PLAYER_SPRITE
; each frame after it. The spin calls view_idle, as every wait that runs no AI
; does, so the vblank work and the frames' loads go on. _plat_demat_palette,
; the pre-release's palette cycle, now only tells src/view.c to draw the
; player from UNIT_TILE while it runs, and that he has arrived. And DEMA2 has
; him drawn again once he has, as tile 97, the Amiga's frame for a player just
; transported, where 2.1 shows its 88.

        .include "petscii.inc"
        .include "sounds.inc"
        .import _plat_demat_palette, _view_idle
        .segment "CODE"

DEMATERIALIZE:                          ; 2.1 $5A1C
        lda     #SFX_MEDKIT
        jsr     PLAY_DIGI_SOUND
        lda     #88                     ; 2.1's first frame: him standing
        sta     UNIT_TILE
        lda     #1                      ; RP6502: his frame follows UNIT_TILE
        jsr     _plat_demat_palette
        jsr     DRAW_MAP_WINDOW         ; RP6502: 2.1's DRAW_UNIT_SPRITES
        lda     #0                      ; 2.1 $5A29: counted from after the draw
        sta     BGTIMER1
        sta     UNIT_TIMER_B
DEMA:   jsr     _view_idle              ; RP6502: the vblank work and the loads
        lda     BGTIMER1                ; 2.1 spins here, and nothing else runs
        cmp     #1
        bne     DEMA
        lda     #0
        sta     BGTIMER1
        inc     UNIT_TIMER_B            ; eight ticks a frame
        lda     UNIT_TIMER_B
        cmp     #8
        bne     DEMA
        lda     UNIT_TILE
        cmp     #95                     ; the last frame
        beq     DEMA1
        inc     UNIT_TILE
        jsr     DISPLAY_PLAYER_SPRITE   ; RP6502: 2.1's DRAW_UNIT_SPRITES
        lda     #0                      ; 2.1 $5A50: counted from after the draw
        sta     UNIT_TIMER_B
        sta     BGTIMER1
        jmp     DEMA

DEMA1:  ; Transport complete: the player is drawn as usual again, then moved.
        lda     #0                      ; RP6502: see _plat_demat_palette
        jsr     _plat_demat_palette
        ldx     UNIT
        lda     UNIT_B,x
        cmp     #1                      ; 1 = send to coordinates
        beq     DEMA2
        lda     #2                      ; anything else ends the level
        sta     UNIT_TYPE
        lda     #7                      ; back to a normal transporter pad
        sta     UNIT_TYPE,x
        jmp     AILP
DEMA2:  lda     #97                     ; RP6502: 2.1 has 88 again
        sta     UNIT_TILE
        lda     UNIT_C,x                ; target X
        sta     UNIT_LOC_X
        lda     UNIT_D,x                ; target Y
        sta     UNIT_LOC_Y
        lda     #7
        sta     UNIT_TYPE,x
        jsr     DISPLAY_PLAYER_SPRITE   ; RP6502: tile 97, the Amiga's frame 1
        jsr     CACULATE_AND_REDRAW
        jmp     AILP
