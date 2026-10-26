; The renderer's RIA register work, where cc65 cannot be trusted with it.
;
; cc65 ignores volatile, so a C loop polling RIA_BUSY may read it once and
; never again, and the hot loops here are a few cycles an iteration in assembly
; against tens in C. Everything else about the renderer is src/view.c.

        .include "rp6502.inc"

        .export _ldr_start, _ldr_busy, _pf_write_ptrs, _xr_copy
        .import _view_fd, _ptr_lo, _ptr_hi
        .importzp ptr1, tmp1

IMG24_BYTES = 288
PF_POINTERS = 77
CSPRITE     = 10                ; sizeof(mode5_csprite_t)

        .segment "CODE"

; void __fastcall__ ldr_start(unsigned xaddr)
;
; Start reading one 288-byte record from the images file into XRAM at xaddr,
; and return without waiting: READ_XRAM moves the bytes while the 6502 does
; something else. The file is already at the record; lseek on a ROM asset is
; only arithmetic in the RIA, so view.c does that first, blocking.
;
; The arguments go on the XSTACK as the C library's read_xram pushes them:
; xaddr, then count, high byte first.
_ldr_start:
        stx     RIA_XSTACK              ; xaddr high
        sta     RIA_XSTACK              ; xaddr low
        lda     #>IMG24_BYTES
        sta     RIA_XSTACK
        lda     #<IMG24_BYTES
        sta     RIA_XSTACK
        lda     _view_fd
        sta     RIA_A
        lda     #RIA_OP_READ_XRAM
        sta     RIA_OP
        rts

; unsigned char ldr_busy(void)
;
; Non-zero while an API call is running. Bit 7 of RIA_BUSY, read every time.
_ldr_busy:
        lda     RIA_BUSY
        and     #$80
        ldx     #0
        rts

; void __fastcall__ pf_write_ptrs(unsigned xaddr)
;
; The playfield's 77 image pointers, from ptr_lo and ptr_hi, into the sprite
; records starting at xaddr -- the xram_sprite_ptr of the first. Portal 0 takes
; the low bytes and portal 1 the high, both stepping a record at a time, so a
; sprite is two loads and two stores. The interrupt saves portal 1 around its
; own use. Both steps go back to 1, which the rest of the program assumes.
_pf_write_ptrs:
        sta     RIA_ADDR0
        stx     RIA_ADDR0+1
        clc
        adc     #1
        sta     RIA_ADDR1
        txa
        adc     #0
        sta     RIA_ADDR1+1
        lda     #CSPRITE
        sta     RIA_STEP0
        sta     RIA_STEP1
        ldy     #0
@loop:  lda     _ptr_lo,y
        sta     RIA_RW0
        lda     _ptr_hi,y
        sta     RIA_RW1
        iny
        cpy     #PF_POINTERS
        bne     @loop
        lda     #1
        sta     RIA_STEP0
        sta     RIA_STEP1
        rts

; void __fastcall__ xr_copy(unsigned xaddr, const void *src, unsigned char n)
;
; n bytes (1-255) of RAM to XRAM, through portal 0.
_xr_copy:
        sta     tmp1                    ; n
        jsr     popax                   ; src
        sta     ptr1
        stx     ptr1+1
        jsr     popax                   ; xaddr
        sta     RIA_ADDR0
        stx     RIA_ADDR0+1
        lda     #1
        sta     RIA_STEP0
        ldy     #0
@loop:  lda     (ptr1),y
        sta     RIA_RW0
        iny
        cpy     tmp1
        bne     @loop
        rts

        .import popax
