; Sound: the MS-DOS version's AdLib effects on the RIA's OPL2, ticked by the
; VIA's timer.
;
; The DOS version plays its sound with the SSY player in its audio.c, from a
; PC timer interrupt 72 times a second: interrupt.c programs the 8253 with a
; divider of 16571, which is 72.004 Hz. assets/convert/conv_adl.py runs that
; player over SOUNDFX.ADL at build time and keeps only what it writes to the
; chip, so what plays here is a flat list of OPL2 register writes and waits for
; each effect, in VGM's command encoding:
;
;     5A rr dd    write dd to register rr
;     61 nn nn    wait nnnn samples of 44.1 kHz
;     66          end
;
; THE CLOCK. A tick is 1/72 s. VSYNC is 60 Hz, so it cannot be the clock; VIA
; timer 1 is. It runs free from PHI2, which the program reads from the RIA
; rather than assuming 8 MHz, and src/sound.c sets it up. At 8 MHz a tick is
; 111,111 cycles, past what a 16-bit timer counts, so the timer runs at a whole
; multiple of 72 Hz and every snd_subticks-th interrupt is a tick: two at
; 8 MHz, one from 4.7 MHz down.
;
; THE WAITS. 612.5 samples a tick: the converter writes 612 and 613 in turn
; from the start of each stream, and FX_CREDIT, samples of the clock ahead of
; the stream, gets the same in the same order. A tick runs commands until a
; wait puts the stream ahead of the clock, so each write lands on the tick the
; DOS player made it.
;
; WHICH EFFECT PLAYS. The DOS version's rule, from ssy_sound_play: every effect
; has a priority and a time, in ticks, during which only an effect of the same
; priority or higher may replace it. After that anything may. 2.1 lets the
; newest effect always win; these are DOS's sounds, and its tables were made
; for them. The tables are in audio.c, and the 1.22 shareware's robots.exe
; carries the same 34 bytes.
;
; THE VOLUME. 2.1's effects volume, 0-15 from 10, set with SHIFT+[ and SHIFT+].
; 10 is the DOS level, and each step is 2.25 dB, near enough the step of the
; VERA's PCM volume that 2.1 sets with it. It is applied to the level of each
; operator that is heard: the carrier, and the modulator too when the channel
; adds the two rather than modulating one with the other. Most effects already
; play their carrier at full level, so above 10 those cannot get louder. At 0
; the key-on bit is never set, so nothing sounds, while the effect still runs
; and still holds its priority.
;
; The effects play on OPL2 channel 0, which is theirs in the DOS version too.
;
; THE MUSIC has channels 1-8, as in DOS. Its songs are VGM files in the ROM,
; tens of kilobytes each, so they are streamed: two 512-byte buffers, which the
; main loop fills with READ_XSTACK while it waits for VSYNC, the first job of
; the wait (src/sound.c, src/view.c), and which the tick plays from in turn. A
; buffer lasts eight frames at the least. A command can run on from the end of
; one into the next; one that is not all there yet waits, and the song's clock
; waits with it, so a late buffer makes the music pause rather than skip.
;
; A song loops with a jump back in the stream, which can put its ticks out of
; step with the 612/613 the clock adds by a sample. So a song's tick runs while
; the stream is less than half a tick ahead, not while it is behind, which
; reads every tick's writes on its own tick either way.

        .include "rp6502.inc"
        .include "game/petscii.inc"

        .export PLAY_SOUND
        .export _snd_subtick, _snd_subticks
        .export _mus_on, _mus_ready, _mus_end_l, _mus_end_h, _mus_buf
        .export _mus_underruns, _mus_go, _mus_read_start, _mus_read_finish
        .export _snd_wait
        .import SFX_START_L, SFX_START_H
        .import _sfx_volume, _mus_fd
        .importzp ptr1, tmp1

        .interruptor SND_IRQ, 2

OPL_PAGE = $FD                  ; >XRAM_OPL; src/sound.c asserts it
MUS_BUF_BYTES = 512             ; src/sound.c's too
HALF_TICK = 306                 ; samples

; The DOS version's numbers, in audio.h. The game's own numbers are the X16's,
; in game/sounds.inc, because those are what the ported code names.
DOS_BEEP        = 0
DOS_CYCLE_ITEM  = 1
DOS_CYCLE_WEAPON = 2
DOS_DOOR        = 3
DOS_FIRE_PISTOL = 4
DOS_BEEP2       = 5
DOS_USE_EMP     = 6
DOS_ERROR       = 7
DOS_ITEM_FOUND  = 8
DOS_USE_MAGNET  = 9
DOS_USE_MAGNET2 = 10
DOS_USE_MEDKIT  = 11
DOS_MOVE_OBJECT = 12
DOS_FIRE_PLASMA = 13
DOS_SHOCK       = 14
DOS_EXPLOSION   = 15
DOS_EXPLOSION2  = 16

        .segment "RODATA"

; Game effect number to DOS effect, by name. DOS has two explosions where the
; X16 has one; SFX_EXPLOSION2 is the big one, see game/sounds.inc.
SFX_DOS:
        .byte DOS_BEEP2         ; SFX_BEEP2, the menu beep
        .byte DOS_BEEP          ; SFX_BEEP, the cursor's
        .byte DOS_CYCLE_ITEM
        .byte DOS_CYCLE_WEAPON
        .byte DOS_DOOR
        .byte DOS_USE_EMP
        .byte DOS_ERROR
        .byte DOS_EXPLOSION     ; SFX_EXPLOSION, the trash compactor
        .byte DOS_ITEM_FOUND
        .byte DOS_USE_MAGNET2
        .byte DOS_USE_MAGNET
        .byte DOS_USE_MEDKIT
        .byte DOS_MOVE_OBJECT
        .byte DOS_FIRE_PISTOL
        .byte DOS_FIRE_PLASMA
        .byte DOS_SHOCK
        .byte DOS_EXPLOSION2    ; SFX_EXPLOSION2, bombs and canisters

; SOUND_PLAY_PRIORITY and SOUND_PLAY_TIMER, audio.c, in DOS numbering.
SFX_PRIORITY:
        .byte 0, 2, 2, 1, 5, 1, 11, 3, 4, 9, 10, 12, 7, 6, 8, 13, 13
SFX_TIMER:
        .byte 5, 10, 10, 30, 5, 5, 20, 20, 20, 50, 50, 15, 5, 10, 20, 30, 40

MUS_BASE_L:
        .lobytes _mus_buf, _mus_buf + MUS_BUF_BYTES
MUS_BASE_H:
        .hibytes _mus_buf, _mus_buf + MUS_BUF_BYTES

; Attenuation for each effects volume, in the OPL2's 0.75 dB steps.
SFX_ATTEN:
        .byte 63, 27, 24, 21, 18, 15, 12, 9, 6, 3
        .byte 0, <-3, <-6, <-9, <-12, <-15

        .segment "BSS"

FX_PTR:         .res 2          ; the effect's next command; high byte 0 = none
FX_CREDIT:      .res 3          ; samples the clock is ahead, signed
FX_PARITY:      .res 1          ; 0 adds 612 samples this tick, 1 adds 613
FX_AGE:         .res 1          ; ticks since the effect started, for the tests
FX_C0:          .res 1          ; channel 0's feedback/connection register
FX_KSL:         .res 1          ; a level register's top two bits
FX_ATT:         .res 1          ; and the attenuation going onto the rest
SND_TIMER:      .res 1          ; ticks the effect is still protected for
SND_PRIORITY:   .res 1          ; and its priority, 0 once that runs out
_snd_subtick:   .res 1          ; timer interrupts left before the next tick
_snd_subticks:  .res 1          ; timer interrupts to a tick
SND_TICKS:      .res 2          ; ticks since power-on, for the tests

; The music. src/sound.c fills the buffers and sets _mus_ready and the end of
; what it put there; the tick clears _mus_ready when it is done with one.
_mus_buf:       .res MUS_BUF_BYTES * 2
_mus_ready:     .res 2
_mus_end_l:     .res 2
_mus_end_h:     .res 2
_mus_on:        .res 1          ; a song is playing; 0 at its end
_mus_underruns: .res 2          ; ticks a song waited for its stream
MUS_PTR:        .res 2          ; the next command
MUS_END:        .res 2          ; the end of the buffer it is in
MUS_CUR:        .res 1          ; and which buffer that is
MUS_CREDIT:     .res 3          ; as FX_CREDIT
MUS_PARITY:     .res 1
MUS_TICKS:      .res 2          ; ticks the song has played, for the tests
MUS_TMP:        .res 2

        .segment "CODE"

; A = effect, in the game's numbering. Called from the main loop, never from
; an interrupt; it keeps the caller's interrupt flag.
PLAY_SOUND:
        tax
        ldy     SFX_DOS,x
        php
        sei
        lda     SND_TIMER
        beq     @play
        lda     SFX_PRIORITY,y
        cmp     SND_PRIORITY
        bcc     @keep                   ; below one still protected
@play:  lda     SFX_TIMER,y
        sta     SND_TIMER
        lda     SFX_PRIORITY,y
        sta     SND_PRIORITY
        stx     SOUND_EFFECT
        lda     SFX_START_L,y
        sta     FX_PTR
        lda     SFX_START_H,y
        sta     FX_PTR+1
        stz     FX_CREDIT
        stz     FX_CREDIT+1
        stz     FX_CREDIT+2
        stz     FX_PARITY
        stz     FX_AGE
@keep:  plp
        rts

; The VIA's interrupt: an interruptor rather than part of the C level handler
; in game/irq.s, because it calls no C and so needs none of the zero page that
; handler saves. It touches only its own: SND_PTR, which the game's half of
; zero page keeps for it. Carry set says it was ours.
SND_IRQ:
        bit     VIA_IFR                 ; bit 7: an enabled VIA interrupt, and
        bpl     @not                    ; timer 1 is the only one enabled
        lda     VIA_T1CL                ; reading this acknowledges it
        dec     _snd_subtick
        bne     @ours
        lda     _snd_subticks
        sta     _snd_subtick
        jsr     SND_TICK
@ours:  sec
        rts
@not:   clc
        rts

; One tick. The registers are XRAM, written through portal 1, which the main
; loop may be part way through using: it is handed back exactly as it was found,
; as the VSYNC handler does.
SND_TICK:
        lda     RIA_ADDR1
        pha
        lda     RIA_ADDR1+1
        pha
        lda     RIA_STEP1
        pha
        stz     RIA_STEP1
        lda     #OPL_PAGE
        sta     RIA_ADDR1+1

        jsr     FX_TICK
        jsr     MUS_TICK

        ; ssy_timer_isr counts the protection down after the channels.
        lda     SND_TIMER
        beq     @count
        dec     SND_TIMER
        bne     @count
        stz     SND_PRIORITY
@count: inc     SND_TICKS
        bne     @out
        inc     SND_TICKS+1

@out:   pla
        sta     RIA_STEP1
        pla
        sta     RIA_ADDR1+1
        pla
        sta     RIA_ADDR1
        rts

; The effect's commands for this tick. A tick is at most a few dozen bytes,
; which the converter checks, so Y indexes all of it.
FX_TICK:
        lda     FX_PTR+1
        beq     @idle
        sta     SND_PTR+1
        lda     FX_PTR
        sta     SND_PTR
        ldy     #0
@next:  bit     FX_CREDIT+2             ; the stream is ahead of the clock:
        bmi     @tick                   ; this tick is done
        lda     (SND_PTR),y
        iny
        cmp     #$5A
        bne     @wait
        lda     (SND_PTR),y             ; register
        tax
        iny
        lda     (SND_PTR),y             ; value
        iny
        jsr     FX_WRITE
        bra     @next
@wait:  cmp     #$61
        bne     @end
        sec
        lda     FX_CREDIT
        sbc     (SND_PTR),y
        sta     FX_CREDIT
        iny
        lda     FX_CREDIT+1
        sbc     (SND_PTR),y
        sta     FX_CREDIT+1
        iny
        lda     FX_CREDIT+2
        sbc     #0
        sta     FX_CREDIT+2
        bra     @next
@end:   stz     FX_PTR+1                ; $66, the end
        lda     #$FF
        sta     SOUND_EFFECT
@idle:  rts

@tick:  tya
        clc
        adc     SND_PTR
        sta     FX_PTR
        lda     SND_PTR+1
        adc     #0
        sta     FX_PTR+1
        inc     FX_AGE
        lda     FX_PARITY               ; the clock moves on: 612 samples,
        lsr                             ; and 613 every other tick
        lda     FX_CREDIT
        adc     #<612
        sta     FX_CREDIT
        lda     FX_CREDIT+1
        adc     #>612
        sta     FX_CREDIT+1
        lda     FX_CREDIT+2
        adc     #0
        sta     FX_CREDIT+2
        lda     FX_PARITY
        eor     #1
        sta     FX_PARITY
        rts

; X = register, A = value, both channel 0's. The levels that are heard go
; through the effects volume; the key-on bit goes nowhere at volume 0. Keeps Y.
FX_WRITE:
        cpx     #$B0
        beq     @key
        cpx     #$43                    ; the carrier's level
        beq     @level
        cpx     #$C0
        bne     @mod
        sta     FX_C0
        bra     @out
@mod:   cpx     #$40                    ; the modulator's, heard only when
        bne     @out                    ; the connection bit says add
        pha
        lda     FX_C0
        lsr
        pla
        bcc     @out
@level: pha
        and     #$C0
        sta     FX_KSL
        phx
        ldx     _sfx_volume
        lda     SFX_ATTEN,x
        sta     FX_ATT
        plx
        pla
        and     #$3F
        clc
        adc     FX_ATT                  ; -15 to +63 onto 0-63
        bpl     @floor
        lda     #0                      ; louder than full is full
@floor: cmp     #$40
        bcc     @ksl
        lda     #$3F                    ; quieter than silent is silent
@ksl:   ora     FX_KSL
        bra     @out
@key:   pha
        lda     _sfx_volume
        bne     @on
        pla
        and     #<~$20
        bra     @out
@on:    pla
@out:   stx     RIA_ADDR1
        sta     RIA_RW1
        rts

; ---- the music --------------------------------------------------------------

; The song's commands for this tick, from the buffers. Writes go straight to
; the chip: the effects volume is the effects'.
MUS_TICK:
        lda     _mus_on
        beq     @off
        lda     MUS_PTR
        sta     SND_PTR
        lda     MUS_PTR+1
        sta     SND_PTR+1
@next:  clc                             ; half a tick ahead: this tick is done
        lda     MUS_CREDIT
        adc     #<HALF_TICK
        lda     MUS_CREDIT+1
        adc     #>HALF_TICK
        lda     MUS_CREDIT+2
        adc     #0
        bmi     @tick
        jsr     MUS_HAVE
        bcc     @starved
        jsr     MUS_BYTE
        cmp     #$5A
        bne     @wait
        jsr     MUS_BYTE                ; register
        tax
        jsr     MUS_BYTE                ; value
        stx     RIA_ADDR1
        sta     RIA_RW1
        bra     @next
@wait:  cmp     #$61
        bne     @end
        jsr     MUS_BYTE
        sta     MUS_TMP
        jsr     MUS_BYTE
        sta     MUS_TMP+1
        sec
        lda     MUS_CREDIT
        sbc     MUS_TMP
        sta     MUS_CREDIT
        lda     MUS_CREDIT+1
        sbc     MUS_TMP+1
        sta     MUS_CREDIT+1
        lda     MUS_CREDIT+2
        sbc     #0
        sta     MUS_CREDIT+2
        bra     @next
@end:   stz     _mus_on                 ; $66: a song that plays once is over
@off:   rts

@starved:
        inc     _mus_underruns          ; the clock holds until it comes
        bne     @save
        inc     _mus_underruns+1
        bra     @save

@tick:  inc     MUS_TICKS
        bne     @clock
        inc     MUS_TICKS+1
@clock: lda     MUS_PARITY
        lsr
        lda     MUS_CREDIT
        adc     #<612
        sta     MUS_CREDIT
        lda     MUS_CREDIT+1
        adc     #>612
        sta     MUS_CREDIT+1
        lda     MUS_CREDIT+2
        adc     #0
        sta     MUS_CREDIT+2
        lda     MUS_PARITY
        eor     #1
        sta     MUS_PARITY
@save:  lda     SND_PTR
        sta     MUS_PTR
        lda     SND_PTR+1
        sta     MUS_PTR+1
        rts

; Carry set if the next command is all there: in this buffer, or running on
; into the other, which is ready. A buffer used up is handed back here.
MUS_HAVE:
        sec
        lda     MUS_END
        sbc     SND_PTR
        sta     MUS_TMP
        lda     MUS_END+1
        sbc     SND_PTR+1
        bne     @yes                    ; 256 or more left
        lda     MUS_TMP
        beq     @used
        cmp     #3
        bcs     @yes                    ; a whole write or wait
        lda     (SND_PTR)
        cmp     #$66
        beq     @yes                    ; the end is a byte
@other: lda     MUS_CUR
        eor     #1
        tay
        lda     _mus_ready,y
        beq     @no
@yes:   sec
        rts
@used:  lda     MUS_CUR
        eor     #1
        tay
        lda     _mus_ready,y
        beq     @no
        jsr     MUS_SWITCH              ; a buffer only ever holds whole
        sec                             ; commands from its start on
        rts
@no:    clc
        rts

; A = the next byte, going on into the other buffer when this one is done.
; Keeps X.
MUS_BYTE:
        lda     SND_PTR
        cmp     MUS_END
        bne     @get
        lda     SND_PTR+1
        cmp     MUS_END+1
        bne     @get
        jsr     MUS_SWITCH
@get:   lda     (SND_PTR)
        inc     SND_PTR
        bne     @out
        inc     SND_PTR+1
@out:   rts

; Done with this buffer: hand it back to be filled, and go on in the other.
; Keeps X.
MUS_SWITCH:
        ldy     MUS_CUR
        lda     #0
        sta     _mus_ready,y
        tya
        eor     #1
        sta     MUS_CUR
        tay
        lda     MUS_BASE_L,y
        sta     SND_PTR
        lda     MUS_BASE_H,y
        sta     SND_PTR+1
        lda     _mus_end_l,y
        sta     MUS_END
        lda     _mus_end_h,y
        sta     MUS_END+1
        rts

; void mus_go(void)
;
; Play from the first buffer, which src/sound.c has filled.
_mus_go:
        php
        sei
        stz     MUS_CUR
        lda     #<_mus_buf
        sta     MUS_PTR
        lda     #>_mus_buf
        sta     MUS_PTR+1
        lda     _mus_end_l
        sta     MUS_END
        lda     _mus_end_h
        sta     MUS_END+1
        stz     MUS_CREDIT
        stz     MUS_CREDIT+1
        stz     MUS_CREDIT+2
        stz     MUS_PARITY
        stz     MUS_TICKS
        stz     MUS_TICKS+1
        lda     #1
        sta     _mus_on
        plp
        rts

; void __fastcall__ mus_read_start(unsigned count)
;
; Start reading count bytes, 512 at most, of the song onto the XSTACK, and
; return without waiting, as src/view_io.s starts its loads. The count goes on
; the XSTACK high byte first.
_mus_read_start:
        stx     RIA_XSTACK
        sta     RIA_XSTACK
        lda     _mus_fd
        sta     RIA_A
        lda     #RIA_OP_READ_XSTACK
        sta     RIA_OP
        rts

; int __fastcall__ mus_read_finish(unsigned char *dst)
;
; Once the read is done: the bytes it read, pulled off the XSTACK into dst, as
; the C library's read_xstack pulls them; -1 for an error.
_mus_read_finish:
        sta     ptr1
        stx     ptr1+1
        lda     RIA_A
        ldx     RIA_X
        bmi     @done
        sta     tmp1
        pha
        phx
        ldy     #0
        txa
        beq     @rest
@page:  lda     RIA_XSTACK
        sta     (ptr1),y
        iny
        bne     @page
        inc     ptr1+1
        dex
        bne     @page
@rest:  cpy     tmp1
        beq     @end
        lda     RIA_XSTACK
        sta     (ptr1),y
        iny
        bra     @rest
@end:   plx
        pla
@done:  rts

; void __fastcall__ snd_wait(unsigned char ticks)
;
; Wait out that many ticks of the sound's clock, a few at most. From the main
; loop, with interrupts on.
_snd_wait:
        clc
        adc     SND_TICKS
        sta     tmp1
@wait:  lda     SND_TICKS
        cmp     tmp1
        bne     @wait
        rts
