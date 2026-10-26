; Screen layouts, from the pre-release's x16Robots.ASM 5327-5457.
;
; SCR_CUSTOM_KEYS is a run-length encoded 40x30 character grid: a literal byte
; is one cell, and byte 96 introduces a run of "next byte, count+1 times".
; src/platform.c expands it on the way to the screen. The intro, game and
; endgame layouts, the intro robot's faces and the live map's colours were the
; X16's; the Amiga's pictures and tables in assets/src/amiga replace them, but
; for the title picture and the robot's eyes, which are X16 2.1's, from
; assets/src/x16.
;
; CINEMA_MESSAGE is the marquee ANIMATE_WATER scrolls across the cinema tiles.

        .include "petscii.inc"
        .segment "RODATA"

SCR_CUSTOM_KEYS:
	.byte $55, $60, $40, $03, $73, $01, $14, $14, $01, $03, $0B, $20, $0F, $06, $20
	.byte $14, $08, $05, $20, $10, $05, $14, $13, $03, $09, $09, $20, $12, $0F, $02
	.byte $0F, $14, $13, $6B, $60, $40, $03, $49, $5D, $60, $20, $25, $5D, $5D, $60
	.byte $20, $25, $5D, $5D, $60, $20, $03, $10, $12, $05, $13, $13, $20, $14, $08
	.byte $05, $20, $0B, $05, $19, $13, $20, $19, $0F, $15, $20, $17, $09, $13, $08
	.byte $20, $14, $0F, $20, $15, $13, $05, $60, $20, $03, $5D, $5D, $60, $20, $04
	.byte $06, $0F, $12, $20, $14, $08, $05, $20, $06, $0F, $0C, $0C, $0F, $17, $09
	.byte $0E, $07, $20, $06, $15, $0E, $03, $14, $09, $0F, $0E, $13, $60, $20, $05
	.byte $5D, $5D, $60, $20, $25, $5D, $5D, $60, $20, $25, $5D, $5D, $60, $20, $25
	.byte $5D, $5D, $60, $20, $06, $0D, $0F, $16, $05, $20, $15, $10, $3A, $60, $20
	.byte $16, $5D, $5D, $60, $20, $04, $0D, $0F, $16, $05, $20, $04, $0F, $17, $0E
	.byte $3A, $60, $20, $16, $5D, $5D, $60, $20, $04, $0D, $0F, $16, $05, $20, $0C
	.byte $05, $06, $14, $3A, $60, $20, $16, $5D, $5D, $60, $20, $03, $0D, $0F, $16
	.byte $05, $20, $12, $09, $07, $08, $14, $3A, $60, $20, $16, $5D, $5D, $60, $20
	.byte $06, $06, $09, $12, $05, $20, $15, $10, $3A, $60, $20, $16, $5D, $5D, $60
	.byte $20, $04, $06, $09, $12, $05, $20, $04, $0F, $17, $0E, $3A, $60, $20, $16
	.byte $5D, $5D, $60, $20, $04, $06, $09, $12, $05, $20, $0C, $05, $06, $14, $3A
	.byte $60, $20, $16, $5D, $5D, $60, $20, $03, $06, $09, $12, $05, $20, $12, $09
	.byte $07, $08, $14, $3A, $60, $20, $16, $5D, $5D, $20, $03, $19, $03, $0C, $05
	.byte $20, $17, $05, $01, $10, $0F, $0E, $13, $3A, $60, $20, $16, $5D, $5D, $60
	.byte $20, $02, $03, $19, $03, $0C, $05, $20, $09, $14, $05, $0D, $13, $3A, $60
	.byte $20, $16, $5D, $5D, $60, $20, $05, $15, $13, $05, $20, $09, $14, $05, $0D
	.byte $3A, $60, $20, $16, $5D, $5D, $20, $13, $05, $01, $12, $03, $08, $20, $0F
	.byte $02, $0A, $05, $03, $14, $3A, $60, $20, $16, $5D, $5D, $60, $20, $02, $0D
	.byte $0F, $16, $05, $20, $0F, $02, $0A, $05, $03, $14, $3A, $60, $20, $16, $5D
	.byte $5D, $60, $20, $25, $5D, $5D, $60, $20, $25, $5D, $5D, $60, $20, $25, $5D
	.byte $5D, $60, $20, $25, $5D;ROW 24
	.byte $5D, $60, $20, $25, $5D;ROW 25
	.byte $5D, $60, $20, $25, $5D;ROW 26
	.byte $5D, $60, $20, $25, $5D;ROW 27
	.byte $5D, $60, $20, $25, $5D;ROW 28
	.byte $4A, $60, $40, $25, $4B;ROW 29

CINEMA_MESSAGE:
	.byte 3,15,13,9,14,7,32,19,15,15,14,58,32,19,16,1,3,5,32,2,1,12,12,19,32,50,32,45,32,20,8,5,32,19,5,1,18,3,8,32,6,15,18,32,13,15,18,5,32,13,15,14,5,25,44,32
	.byte 1,20,20,1,3,11,32,15,6,32,20,8,5,32,16,1,16,5,18,3,12,9,16,19,58,32,3,12,9,16,16,25,39,19,32,18,5,22,5,14,7,5,44,32
	.byte 9,20,32,3,1,13,5,32,6,18,15,13,32,16,12,1,14,5,20,32,5,1,18,20,8,44,32
	.byte 18,15,3,11,25,32,53,48,48,48,44,32,1,12,12,32,13,25,32,3,9,18,3,21,9,20,19,32,20,8,5,32,13,15,22,9,5,44,32
	.byte 3,15,14,1,14,32,20,8,5,32,12,9,2,18,1,18,9,1,14,44,32,1,14,4,32,13,15,18,5,33,32

;; Symbols from legacy sound engine pending deletion
;NOTE_FREQ_L:
;NOTE_FREQ_H:
;SND_EXPLOSION:
;SND_MEDKIT:
;SND_EMP:
;SND_MAGNET:
;SND_SHOCK:
;SND_MOVE_OBJ:
;SND_PLASMA:
;SND_PISTOL:
;SND_ITEM_FOUND:
;SND_ERROR:
;SND_CYCLE_WEAPON:
;SND_CYCLE_ITEM:
;SND_DOOR:
;SND_MENU_BEEP:
;SND_SHORT_BEEP:
;INTRO_MUSIC:
;WIN_MUSIC:
;LOSE_MUSIC:
;IN_GAME_MUSIC1:
;IN_GAME_MUSIC2:
;IN_GAME_MUSIC3:

; The game over box and the two endings, from the pre-release's x16Robots.ASM
; 3926-3928 and 3977-3978. The box is PETSCII line drawing -- corners and
; horizontal rules around the words -- eleven characters to a row.
GAMEOVER1:	.byte $70,$40,$40,$40,$40,$40,$40,$40,$40,$40,$6e
GAMEOVER2:	.byte $5d,$07,$01,$0d,$05,$20,$0f,$16,$05,$12,$5d
GAMEOVER3:	.byte $6d,$40,$40,$40,$40,$40,$40,$40,$40,$40,$7d
WIN_MSG:	.byte 25,15,21,32,23,9,14,33
LOS_MSG:	.byte 25,15,21,32,12,15,19,5,33

