; The palettes, faded: the Amiga's Palette::update, run from the VSYNC
; interrupt whenever src/palette.c has asked for a new level.
;
; Every colour is RGB4, and a fade moves each channel towards the base colour's:
; c' = base + (c - base) * level / 15, the change rounded down, so level 15 is
; the colour itself and level 0 is the base. That is the Amiga's arithmetic,
; table and all, and its colours come out exactly.
;
; The six palettes (xram.h, palettes_t) are written in one run through portal 1,
; which the interrupt saves around this: 16 faded game colours make game, fg, a
; and b; 16 faded picture colours make pic and pic_text. The entries that stand
; in for the Amiga's colour 0 -- a[8], b[1], pic_text[8] -- take faded colour
; 0, as the Amiga's colour 0 fades with the rest. a[0] takes it too but stays
; transparent: sprites and text skip it, while the HUD frame, which plane 0's
; background layer draws whatever the opacity, tints with the screen.
; pic_text[13] and [14] take the title's two colours of its own instead of the
; picture's while it has them (pal_title_inks, src/palette.c), faded the same
; way, or clear.

        .include "rp6502.inc"

        .export _pal_write, _pal_vblank
        .import _pal_level, _pal_base, _pal_pic, _pal_pic_black, _pal_dirty
        .import _pal_ink, _pal_inked
        .import _pal_xram, _amiga_pal_game, _amiga_pal_b_order
        .importzp ptr1, tmp1, tmp2, tmp3, tmp4

ALPHA = $20

        .segment "BSS"

glo:    .res 16                         ; the game colours, RGB555
ghi:    .res 16
plo:    .res 16                         ; the picture colours
phi:    .res 16
br:     .res 1                          ; the base colour's channels
bg:     .res 1
bb:     .res 1
fl:     .res 1                          ; the level, times 16

        .segment "RODATA"

; (level * d) / 15, rounded down: the Amiga's fadeTable, a row per level.
fade:
        .repeat 16, F
        .repeat 16, D
        .byte   (F * D) / 15
        .endrepeat
        .endrepeat

; 4 bits to RGB555's 5 -- the 8-bit value is c * 17, and the top five bits of
; that are c * 17 / 8 -- split where the channels fall: red and the opacity bit
; in the low byte, green across both, blue in the high byte.
rlo:
        .repeat 16, C
        .byte   (C * 17 / 8) | ALPHA
        .endrepeat
glo_t:
        .repeat 16, C
        .byte   ((C * 17 / 8) & 3) << 6
        .endrepeat
ghi_t:
        .repeat 16, C
        .byte   (C * 17 / 8) >> 2
        .endrepeat
bhi_t:
        .repeat 16, C
        .byte   (C * 17 / 8) << 3
        .endrepeat

        .segment "CODE"

; void pal_vblank(void): from the interrupt, every frame; writes only when asked.
_pal_vblank:
        lda     _pal_dirty
        bne     _pal_write
        rts

; void pal_write(void): all six palettes at the current level, now.
_pal_write:
        lda     #0
        sta     _pal_dirty
        lda     _pal_level
        asl     a
        asl     a
        asl     a
        asl     a
        sta     fl
        lda     _pal_base+1
        and     #$0F
        sta     br
        lda     _pal_base
        and     #$0F
        sta     bb
        lda     _pal_base
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     bg

        ; The game colours.
        lda     #<_amiga_pal_game
        sta     ptr1
        lda     #>_amiga_pal_game
        sta     ptr1+1
        ldx     #0
@game:  jsr     colour
        sta     glo,x
        lda     tmp3
        sta     ghi,x
        inx
        cpx     #16
        bne     @game

        ; The picture's. With the picture layer black, the text over it keeps
        ; these colours.
        lda     _pal_pic
        sta     ptr1
        lda     _pal_pic+1
        sta     ptr1+1
        ldx     #0
@pic:   jsr     colour
        sta     plo,x
        lda     tmp3
        sta     phi,x
        inx
        cpx     #16
        bne     @pic

        lda     _pal_xram
        sta     RIA_ADDR1
        lda     _pal_xram+1
        sta     RIA_ADDR1+1
        lda     #1
        sta     RIA_STEP1

        ; game: as it is.
        ldx     #0
:       lda     glo,x
        sta     RIA_RW1
        lda     ghi,x
        sta     RIA_RW1
        inx
        cpx     #16
        bne     :-
        ; fg: entry 0 transparent.
        lda     #0
        sta     RIA_RW1
        sta     RIA_RW1
        ldx     #1
:       lda     glo,x
        sta     RIA_RW1
        lda     ghi,x
        sta     RIA_RW1
        inx
        cpx     #16
        bne     :-
        ; a: entry 0 colour 0 but transparent, 8 colour 0.
        lda     glo
        and     #<~ALPHA
        sta     RIA_RW1
        lda     ghi
        sta     RIA_RW1
        ldx     #1
@a:     cpx     #8
        bne     @a1
        lda     glo
        sta     RIA_RW1
        lda     ghi
        sta     RIA_RW1
        jmp     @a2
@a1:    lda     glo,x
        sta     RIA_RW1
        lda     ghi,x
        sta     RIA_RW1
@a2:    inx
        cpx     #16
        bne     @a
        ; b: entry 0 transparent, then the game colours in 2.1's unit order
        ; (_amiga_pal_b_order, conv_amiga.py): black at 1 and white at 2,
        ; and no 039.
        lda     #0
        sta     RIA_RW1
        sta     RIA_RW1
        ldy     #0
@b:     ldx     _amiga_pal_b_order,y
        lda     glo,x
        sta     RIA_RW1
        lda     ghi,x
        sta     RIA_RW1
        iny
        cpy     #15
        bne     @b
        ; pic: as it is, or black.
        ldx     #0
        lda     _pal_pic_black
        bne     @pblack
:       lda     plo,x
        sta     RIA_RW1
        lda     phi,x
        sta     RIA_RW1
        inx
        cpx     #16
        bne     :-
        beq     @ptext
@pblack:
        lda     #ALPHA
        sta     RIA_RW1
        lda     #0
        sta     RIA_RW1
        inx
        cpx     #16
        bne     @pblack
@ptext:
        ; The title's two colours, if it has them: pic_text's 13 and 14 take
        ; them faded, or nothing at all for PAL_CLEAR, the high bit, in place
        ; of the picture's. pic is written, so plo and phi are free to change.
        lda     _pal_inked
        beq     @pt
        lda     #<_pal_ink
        sta     ptr1
        lda     #>_pal_ink
        sta     ptr1+1
        ldx     #0
@ink:   jsr     colour
        sta     plo+13,x
        lda     tmp3
        sta     phi+13,x
        txa
        asl     a
        tay
        iny
        lda     (ptr1),y
        bpl     @ink1
        lda     #0                      ; clear: the opacity bit off
        sta     plo+13,x
        sta     phi+13,x
@ink1:  inx
        cpx     #2
        bne     @ink
@pt:
        ; pic_text: entry 0 transparent, 8 colour 0.
        lda     #0
        sta     RIA_RW1
        sta     RIA_RW1
        ldx     #1
@t:     cpx     #8
        bne     @t1
        lda     plo
        sta     RIA_RW1
        lda     phi
        sta     RIA_RW1
        jmp     @t2
@t1:    lda     plo,x
        sta     RIA_RW1
        lda     phi,x
        sta     RIA_RW1
@t2:    inx
        cpx     #16
        bne     @t
        rts

; Colour X of the RGB4 words at ptr1, faded. Returns the RGB555 low byte in A
; and the high one in tmp3; X is kept.
colour:
        txa
        asl     a
        tay
        lda     (ptr1),y                ; green and blue
        sta     tmp1
        iny
        lda     (ptr1),y                ; red
        and     #$0F
        ldy     br
        jsr     channel
        tay
        lda     rlo,y
        sta     tmp2                    ; low byte, red and alpha
        lda     tmp1
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        ldy     bg
        jsr     channel
        tay
        lda     ghi_t,y
        sta     tmp3
        lda     glo_t,y
        ora     tmp2
        sta     tmp2
        lda     tmp1
        and     #$0F
        ldy     bb
        jsr     channel
        tay
        lda     bhi_t,y
        ora     tmp3
        sta     tmp3
        lda     tmp2
        rts

; Channel A towards base Y at the level: base + (A - base) * level / 15.
channel:
        sty     tmp4
        sec
        sbc     tmp4
        bcc     @down
        ora     fl
        tay
        lda     fade,y
        clc
        adc     tmp4
        rts
@down:  eor     #$FF                    ; carry is clear: this negates
        adc     #1
        ora     fl
        tay
        lda     tmp4
        sec
        sbc     fade,y
        rts
