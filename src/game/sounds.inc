        .ifndef SOUNDS_INC
SOUNDS_INC = 1

; Sound effect indices, from the pre-release's sounds.inc.
;
; The X16 played these as digitised samples through ZSOUND; the RP6502 plays the
; MS-DOS version's AdLib effects on the OPL2 instead, src/sound.s. The indices
; are unchanged, so every JSR PLAY_DIGI_SOUND site in the AI still names the
; right effect. The DOS version has two explosions where the X16 has one: the
; big one, for bombs and canisters, is SFX_EXPLOSION2, and SFX_EXPLOSION is the
; trash compactor's.
SFX_BEEP2 = 0
SFX_BEEP = 1
SFX_CYCLEITEM = 2
SFX_CYCLEWEAPON = 3
SFX_DOOR = 4
SFX_EMP = 5
SFX_ERROR = 6
SFX_EXPLOSION = 7
SFX_FOUNDITEM = 8
SFX_MAGNET2 = 9
SFX_MAGNET = 10
SFX_MEDKIT = 11
SFX_MOVE = 12
SFX_PISTOL = 13
SFX_PLASMA = 14
SFX_SHOCK = 15
SFX_EXPLOSION2 = 16

        .endif
