; Map window bookkeeping, from the pre-release's x16Robots.ASM.
;
; These three are pure logic in the middle of an otherwise machine-specific
; file, so they come across with the presentation left behind: they decide what
; should be on screen, and the platform layer draws it.
;
;   CACULATE_AND_REDRAW      2545   centre the window on the player  (sic)
;   MAP_PRE_CALCULATE        2562   collect the units inside the window
;   CHECK_FOR_WINDOW_REDRAW  2925   does this unit's move need a redraw?

        .include "petscii.inc"
        .segment "CODE"

CACULATE_AND_REDRAW:
	LDA	UNIT_LOC_X	;no index needed since it's player unit
	SEC
	SBC	#5
	STA	MAP_WINDOW_X
	LDA	UNIT_LOC_Y	;no index needed since it's player unit
	SEC
	SBC	#3
	STA	MAP_WINDOW_Y
	LDA	#1
	STA	REDRAW_WINDOW
	RTS

MAP_PRE_CALCULATE:
	;CLEAR OLD BUFFER
	LDA	#0
	LDY	#0
PREC0:	STA	MAP_PRECALC,Y
	INY
	CPY	#77
	BNE	PREC0
	LDX	#1
	;JMP	PREC2	;skip the check for unit zero, always draw it.
PREC1:	;CHECK THAT UNIT EXISTS
	LDA	UNIT_TYPE,X
	CMP	#0
	BEQ	PREC5
	;CHECK HORIZONTAL POSITION
	LDA	UNIT_LOC_X,X
	CMP	MAP_WINDOW_X
	BCC	PREC5
	LDA	MAP_WINDOW_X
	CLC
	ADC	#10
	CMP	UNIT_LOC_X,X
	BCC	PREC5
	;NOW CHECK VERTICAL
	LDA	UNIT_LOC_Y,X
	CMP	MAP_WINDOW_Y
	BCC	PREC5
	LDA	MAP_WINDOW_Y
	CLC
	ADC	#6
	CMP	UNIT_LOC_Y,X
	BCC	PREC5
	;Unit found in map window, now add that unit's
	;tile to the precalc map.
PREC2:	LDA	UNIT_LOC_Y,X
	SEC
	SBC	MAP_WINDOW_Y
	TAY
	LDA	UNIT_LOC_X,X
	SEC
	SBC	MAP_WINDOW_X
	CLC
	ADC	PRECALC_ROWS,Y
	TAY
	LDA	UNIT_TILE,X
	CMP	#130	;is it a bomb
	BEQ	PREC6
	CMP	#134	;is it a magnet?
	BEQ	PREC6
PREC4:	STA	MAP_PRECALC,Y
	TXA			;RP6502: and which unit it is, for src/view.c
	STA	MAP_PRECALC_UNIT,Y
PREC5:	;continue search
	INX
	CPX	#32
	BNE	PREC1
	RTS
PREC6:	;What to do in case of bomb or magnet that should
	;go underneath the unit or robot.
	LDA	MAP_PRECALC,Y
	CMP	#0
	BNE	PREC5
	LDA	UNIT_TILE,X
	JMP	PREC4

PRECALC_ROWS:	.byte 0,11,22,33,44,55,66

;This routine is where the MAP is displayed on the screen
;This is a temporary routine, taken from the map editor.
CHECK_FOR_WINDOW_REDRAW:
	LDX	UNIT
	;RP6502: the window and the square round it, where the X16 checks the
	;window alone. Called after a unit moves, the window alone misses one
	;that has just stepped out of view, and its sprite would stay where it
	;was; the X16 and the Amiga redraw every fifteen or twenty frames
	;regardless, which hides that, and the RP6502 redraws only for animated
	;tiles.
	;FIRST CHECK HORIZONTAL
	LDA	UNIT_LOC_X,X
	CLC
	ADC	#1		;x + 1 >= window: x >= window - 1
	CMP	MAP_WINDOW_X
	BCC	CFR1
	LDA	MAP_WINDOW_X
	CLC
	ADC	#11
	CMP	UNIT_LOC_X,X
	BCC	CFR1
	;NOW CHECK VERTICAL
	LDA	UNIT_LOC_Y,X
	CLC
	ADC	#1
	CMP	MAP_WINDOW_Y
	BCC	CFR1
	LDA	MAP_WINDOW_Y
	CLC
	ADC	#7
	CMP	UNIT_LOC_Y,X
	BCC	CFR1
	LDA	#1
	STA	REDRAW_WINDOW
CFR1:	RTS
