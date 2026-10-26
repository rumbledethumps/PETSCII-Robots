        .ifndef PETSCII_INC
PETSCII_INC = 1

; Shared declarations for the ported game logic.
;
; The routines below are David Murray's, converted from ACME to ca65 and then
; adapted for the RP6502. Every deliberate difference from the X16
; pre-release's sources is commented at the site.

; ---- zero page ----------------------------------------------------------
; The X16 build assigns fixed zero page addresses. Under cc65 the linker owns
; zero page, so these are allocated in the ZEROPAGE segment instead. The one
; that matters is MAP_PTR: the original hardcodes $04/$05 as its map pointer,
; which belongs to the C runtime here.
        .globalzp TILE, MAP_X, MAP_Y, UNIT, MOVE_TYPE, MOVE_RESULT
        .globalzp UNIT_FIND, MAP_PTR, SOURCE, SND_PTR
        .globalzp TEMP_X, TEMP_Y, DECNUM, ATTRIB
        .global NEW_BUTTONS, MSG_PAUSED
        .global KEYS_DEFINED
        .global RANDOM, SSCOUNT
        .global SOUND_EFFECT, PLAY_SOUND

; ---- level data ---------------------------------------------------------
        .global UNIT_TYPE, UNIT_LOC_X, UNIT_LOC_Y
        .global UNIT_A, UNIT_B, UNIT_C, UNIT_D, UNIT_HEALTH
        .global MAP

; ---- tileset ------------------------------------------------------------
        .global DESTRUCT_PATH, TILE_ATTRIB

; ---- more game state ----------------------------------------------------
        .globalzp TEMP_A, TEMP_B, TEMP_C, TEMP_D
        .globalzp MAP_WINDOW_X, MAP_WINDOW_Y, REDRAW_WINDOW, SCREEN_SHAKE
        .globalzp PRECALC_COUNT
        .global UNIT_TIMER_A, UNIT_TIMER_B, UNIT_TILE, EXP_BUFFER, MAP_PRECALC
        .global UNIT_DIRECTION, MAP_PRECALC_UNIT
        .global BGTIMER1, BGTIMER2, BIG_EXP_ACT, MAGNET_ACT, PLASMA_ACT
        .global IRQ_FRAME, KEY_FAST, KEYTIMER, CLOCK_ACTIVE, CYCLES, SECONDS, MINUTES, HOURS
        .global KEYS, INV_MAGNET, BORDER

; ---- messages -----------------------------------------------------------
        .global INTRO_MESSAGE
        .global SCR_CUSTOM_KEYS, CINEMA_MESSAGE
        .global GAMEOVER1, GAMEOVER2, GAMEOVER3, WIN_MSG, LOS_MSG
        .global MSG_TERMINATED, MSG_TRANS1, MSG_ELEVATOR, MSG_LEVELS
        .global MSG_BLOCKED, MSG_CANTMOVE, MSG_EMPUSED, MSG_MUCHBET
        .global MSG_NOTFOUND, MSG_SEARCHING, MSG_MUSICON, MSG_MUSICOFF
        .global MSG_VOLUME
        .global MSG_FOUNDKEY, MSG_FOUNDGUN, MSG_FOUNDEMP, MSG_FOUNDBOMB
        .global MSG_FOUNDPLAS, MSG_FOUNDMED, MSG_FOUNDMAG

; ---- inventory and control state ----------------------------------------
        .globalzp CURSOR_X, CURSOR_Y, CURSOR_ON
        .global AMMO_PISTOL, AMMO_PLASMA, INV_BOMBS, INV_EMP, INV_MEDKIT
        .global SELECTED_WEAPON, SELECTED_ITEM
        .global PLAYER_DIRECTION, PLAYER_ANIMATE, CONTROL
        .global KEY_MOVE_UP, KEY_MOVE_DOWN, KEY_MOVE_LEFT, KEY_MOVE_RIGHT
        .global KEY_FIRE_UP, KEY_FIRE_DOWN, KEY_FIRE_LEFT, KEY_FIRE_RIGHT
        .global KEY_CYCLE_WEAPONS, KEY_CYCLE_ITEMS, KEY_USE, KEY_SEARCH, KEY_MOVE
        .global NEW_B, NEW_Y, NEW_SELECT, NEW_START, NEW_UP, NEW_DOWN
        .global NEW_LEFT, NEW_RIGHT, NEW_A, NEW_X, NEW_BACK_L, NEW_BACK_R
        .global BGFLASH, STANDARD_CONTROLS, SPRITECOLCHART
        .global MENUY, MENUCOL, SELECTED_MAP, DIFF_LEVEL
        .global SPRITECOLSTATE, SPRITECOLTIMER, MAP_NAMES

; ---- routines -----------------------------------------------------------
        .global GET_TILE_FROM_MAP, PLOT_TILE_TO_MAP, CHECK_FOR_UNIT
        .global REQUEST_WALK_UP, REQUEST_WALK_DOWN
        .global REQUEST_WALK_LEFT, REQUEST_WALK_RIGHT
        .global GENERATE_RANDOM_NUMBER
        .global ROBOT_KIND, SHORT_OUT, WATER_CHECK     ; X16 2.1's water
        .global BACKGROUND_TASKS, BG_TASKS_IMPL, UNIT_AI, AILP
        .global CACULATE_AND_REDRAW, MAP_PRE_CALCULATE, CHECK_FOR_WINDOW_REDRAW
        .global CHECK_FOR_HIDDEN_UNIT
        .global USE_ITEM, SEARCH_OBJECT, MOVE_OBJECT
        .global FIRE_UP, FIRE_DOWN, FIRE_LEFT, FIRE_RIGHT
        .global REVERSE_TILE, DISPLAY_KEYS, DISPLAY_WEAPON, SEARCH_GLASS_CIRCLE
        .global DISPLAY_PLAYER_SPRITE, SNES_CONTROLER_READ
        .global DEMATERIALIZE, SET_DIFF_LEVEL
        .global DRAW_MAP_WINDOW, VIEW_HOOK, PLAY_DIGI_SOUND, PRINT_INFO
        .global ANIMATE_WATER
        .global DISPLAY_ITEM, DISPLAY_PLAYER_HEALTH, ELEVATOR_SELECT
        .global MAP_STORE, LIVEMAP_BLAST        ; src/livemap.s

; MOVE_TYPE bits, tested as (TILE_ATTRIB & MOVE_TYPE) == MOVE_TYPE
MOVE_WALK       = %00000001
MOVE_HOVER      = %00000010

; TILE_ATTRIB bits
ATTR_WALKABLE     = %00000001
ATTR_HOVERABLE    = %00000010
ATTR_PUSHABLE     = %00000100
ATTR_DESTRUCTIBLE = %00001000
ATTR_SEETHROUGH   = %00010000
ATTR_DESTINATION  = %00100000
ATTR_SEARCHABLE   = %01000000

        .endif
