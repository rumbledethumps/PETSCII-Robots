; The difficulty setting, from the pre-release's x16Robots.ASM lines 4365-4407.
;
; Converted from ACME to ca65, with nothing changed. INIT_GAME runs
; SET_DIFF_LEVEL once a level, right after MAP_LOAD_ROUTINE and before the
; timers are set (x16Robots.ASM 460-464): easy doubles the quantity of every
; hidden item but the keys, hard turns every patrolling hoverbot into one that
; hunts, and normal changes nothing. The port's init_game, which replaced
; INIT_GAME, had left the call out, so the menu's DIFFICULTY changed only the
; intro robot's face; src/main.c makes it in the same place now.
;
; X16 2.1 has the same 67 bytes at $55FB, with UNIT_TYPE at $7D00, UNIT_A at
; $7DC0 and DIFF_LEVEL at $27E0, and its INIT_GAME calls it at $3D49, after the
; map load. The original's DIFF_LEVEL !BYTE 1 (line 4363) stays behind:
; DIFF_LEVEL lives in globals.s, and main() starts it at 1, normal.

        .include "petscii.inc"
        .segment "CODE"

;This routine is run after the map is loaded, but before the
;game starts.  If the diffulcty is set to normal, nothing
;actually happens.  But if it is set to easy or hard, then
;some changes occur accordingly.
SET_DIFF_LEVEL:
	LDA	DIFF_LEVEL
	CMP	#0	;easy
	BNE	SDLE1
	JMP	SET_DIFF_EASY
SDLE1:	CMP	#2	;hard
	BNE	SDLE2
	JMP	SET_DIFF_HARD
SDLE2:	RTS

SET_DIFF_EASY:
	;Find all hidden items and double the quantity.
	LDX	#48
SDE1:	LDA	UNIT_TYPE,X
	CMP	#0
	BEQ	SDE2
	CMP	#128	;KEY
	BEQ	SDE2
	ASL	UNIT_A,X	;item qty
SDE2:	INX
	CPX	#64
	BNE	SDE1
	RTS

SET_DIFF_HARD:
	;Find all hoverbots and change AI
	LDX	#0
SDH1:	LDA	UNIT_TYPE,X
	CMP	#2	;hoverbot left/right
	BEQ	SDH4
	CMP	#3	;hoverbot up/down
	BEQ	SDH4
SDH2:	INX
	CPX	#28
	BNE	SDH1
	RTS
SDH4:	LDA	#4	;hoverbot attack mode
	STA	UNIT_TYPE,X
	JMP	SDH2
