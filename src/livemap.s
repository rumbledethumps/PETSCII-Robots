; The live map's drawing, where it has to be quick: the whole map when it opens,
; and one square whenever the game writes a tile into MAP while it is up.
; Everything else about it is src/livemap.c.
;
; The map is a mode 3 picture at XRAM_VIEW, 4 bits a pixel, and a square is two
; pixels by two: one byte on each of two lines. Square (x,y) is the byte at
; y*256 + x and the one 128 after it. amiga_livemap holds each tile's colour in
; both nibbles, ready to store.

        .include "rp6502.inc"

        .export _livemap_draw, MAP_STORE, LIVEMAP_BLAST
        .import _livemap_on, _livemap_redot, _amiga_livemap, MAP
        .importzp MAP_X, MAP_Y, ptr1, tmp1, tmp2

LIVEMAP_HI = 0                          ; >XRAM_VIEW; src/livemap.c asserts it
EXPLOSION  = 246                        ; the big explosion's tile

        .segment "CODE"

; void livemap_draw(void)
;
; All of MAP, a row at a time: portal 0 writes the even line and portal 1 the
; odd one, both stepping a byte, so a square is a load, a lookup and two stores.
; About 24 cycles a square, a frame and a half for the map.
_livemap_draw:
        lda     #<MAP
        sta     ptr1
        lda     #>MAP
        sta     ptr1+1
        lda     #1
        sta     RIA_STEP0
        sta     RIA_STEP1
        lda     #LIVEMAP_HI
        sta     tmp1                    ; the row's high byte
@row:   lda     #0
        sta     RIA_ADDR0
        lda     #128
        sta     RIA_ADDR1
        lda     tmp1
        sta     RIA_ADDR0+1
        sta     RIA_ADDR1+1
        ldy     #0
@square:
        lda     (ptr1),y
        tax
        lda     _amiga_livemap,x
        sta     RIA_RW0
        sta     RIA_RW1
        iny
        bpl     @square                 ; 128 squares
        lda     ptr1                    ; MAP is page aligned: rows start at
        eor     #$80                    ; $00 and $80
        sta     ptr1
        bmi     @next
        inc     ptr1+1
@next:  inc     tmp1
        lda     tmp1
        cmp     #LIVEMAP_HI + 64
        bne     @row
        rts

; MAP_STORE: STA ($04),Y, for every tile the game writes into MAP, and while
; the live map is up, that square drawn again. A, X, Y and the flags are as the
; STA left them, so it stands in for the instruction anywhere.
;
; ($04) points into MAP and Y is an offset from it, so the square is
; ($04 + Y - MAP): x is the low seven bits and y the rest.
MAP_STORE:
        sta     ($04),y
        php
        bit     _livemap_on
        bmi     @draw
        plp
        rts
@draw:  pha
        phx
        phy
        tax                             ; the tile just written
        lda     _amiga_livemap,x
        sta     tmp2
        tya
        clc
        adc     $04
        tax
        lda     $05
        adc     #0
        sec
        sbc     #>MAP
        cmp     #32                     ; past MAP's 32 pages: leave it
        bcs     @out
        sta     tmp1
        txa
        asl     a
        rol     tmp1                    ; y
        txa
        and     #$7F                    ; x
        jsr     plot
@out:   ply
        plx
        pla
        plp
        rts

; LIVEMAP_BLAST: the middle of a big explosion on the live map, in the
; explosion's colour, at MAP_X,MAP_Y. The explosion there is a unit, not a
; tile, so MAP keeps what is under it; the Amiga paints it anyway. A, X and Y
; are kept.
LIVEMAP_BLAST:
        bit     _livemap_on
        bpl     @rts
        pha
        phx
        lda     _amiga_livemap+EXPLOSION
        sta     tmp2
        lda     MAP_Y
        sta     tmp1
        lda     MAP_X
        jsr     plot
        plx
        pla
@rts:   rts

; Square A,tmp1 in colour tmp2, both lines through portal 0, whatever its step.
; A dot drawn on it is gone now, so the next frame puts the dots back.
plot:   tax
        lda     tmp1
        clc
        adc     #LIVEMAP_HI
        sta     tmp1
        stx     RIA_ADDR0
        sta     RIA_ADDR0+1
        lda     tmp2
        sta     RIA_RW0
        txa
        ora     #$80
        sta     RIA_ADDR0
        lda     tmp1
        sta     RIA_ADDR0+1
        lda     tmp2
        sta     RIA_RW0
        lda     #1
        sta     _livemap_redot
        rts
