# Convert the game data into the shapes the RP6502 wants.
#
# Nothing here edits a binary by hand: every asset in assets/gen/ is produced
# from what assets/src/ holds -- the Amiga version's art, X16 2.1's files and
# the MS-DOS version's sound -- by a script in assets/convert/, so touching a
# source file regenerates it on the next build.

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(ASRC ${CMAKE_SOURCE_DIR}/assets/src)
set(AGEN ${CMAKE_SOURCE_DIR}/assets/gen)
set(CONV ${CMAKE_SOURCE_DIR}/assets/convert)
set(X16  ${ASRC}/x16)
set(DOS  ${ASRC}/dos)

file(MAKE_DIRECTORY ${AGEN})

# petscii_convert(<output> <script> <inputs...>)
function(petscii_convert out script)
    add_custom_command(
        OUTPUT ${AGEN}/${out}
        DEPENDS ${CONV}/${script} ${ARGN}
        COMMAND ${Python3_EXECUTABLE} ${CONV}/${script} ${ARGN} ${AGEN}/${out}
        COMMENT "asset ${out}"
        VERBATIM)
    set(PETSCII_ASSETS ${PETSCII_ASSETS} ${AGEN}/${out} PARENT_SCOPE)
endfunction()

petscii_convert(tiles.bin    conv_tiles.py    ${X16}/TILESET.GFX)

# The maps are X16 2.1's, LEVEL-A .. LEVEL-R, as level-a .. level-r.
foreach(L a b c d e f g h i j k l m n o p q r)
    string(TOUPPER ${L} U)
    petscii_convert(level-${L}.bin conv_level.py ${X16}/LEVEL-${U})
endforeach()

# 2.1's title picture at 320x200, its Commander X16 logo taken out.
# petscii_convert cannot add png.py to DEPENDS, so the rule is written out.
add_custom_command(
    OUTPUT ${AGEN}/title21.png
    DEPENDS ${CONV}/clean_title.py ${CONV}/png.py
            ${X16}/title.bin ${X16}/ROBOTS.PRG ${ASRC}/amiga/introscreen.png
    COMMAND ${Python3_EXECUTABLE} ${CONV}/clean_title.py
            ${X16}/title.bin ${X16}/ROBOTS.PRG ${ASRC}/amiga/introscreen.png
            ${AGEN}/title21.png
    COMMENT "asset title21.png"
    VERBATIM)
list(APPEND PETSCII_ASSETS ${AGEN}/title21.png)

# The art, the Amiga's and 2.1's: one script, every image and table, so one
# rule.
set(AMIGA_INPUTS
    tiles.png animtiles.png items.png health.png keys.png
    gamescreen.png introscreen.png gameover.png C64Font.raw)
list(TRANSFORM AMIGA_INPUTS PREPEND ${ASRC}/amiga/)
set(X16_INPUTS ROBOTS.PRG sprites.bin tiles.bin faces.bin)
list(TRANSFORM X16_INPUTS PREPEND ${X16}/)
set(AMIGA_OUTPUTS
    images.bin anim.bin units.bin hud_tiles.bin hud_map.bin keys.bin
    cursors.bin font.bin intro.bin gameover.bin amiga_tables.s)
list(TRANSFORM AMIGA_OUTPUTS PREPEND ${AGEN}/)
add_custom_command(
    OUTPUT ${AMIGA_OUTPUTS}
    DEPENDS ${CONV}/conv_amiga.py ${CONV}/png.py ${CONV}/amiga_tables.py
            ${AMIGA_INPUTS} ${X16_INPUTS} ${AGEN}/title21.png
    COMMAND ${Python3_EXECUTABLE} ${CONV}/conv_amiga.py
            --src ${ASRC}/amiga --x16 ${X16} --title ${AGEN}/title21.png
            --out ${AGEN}
    COMMENT "asset art"
    VERBATIM)
list(APPEND PETSCII_ASSETS ${AMIGA_OUTPUTS})

# Generated ca65 source of palettes and lookup tables, for the ROM to assemble.
set(PETSCII_AMIGA_TABLES ${AGEN}/amiga_tables.s)

# The MS-DOS version's AdLib effects, as the OPL2 register writes its player
# makes: a ca65 source too, since they live in RAM. Written out because the
# script takes a word before its input.
add_custom_command(
    OUTPUT ${AGEN}/sfx.s
    DEPENDS ${CONV}/conv_adl.py ${DOS}/SOUNDFX.ADL
    COMMAND ${Python3_EXECUTABLE} ${CONV}/conv_adl.py sfx
            ${DOS}/SOUNDFX.ADL ${AGEN}/sfx.s
    COMMENT "asset sfx.s"
    VERBATIM)
list(APPEND PETSCII_ASSETS ${AGEN}/sfx.s)
set(PETSCII_SFX ${AGEN}/sfx.s)

# Its songs, as VGM files the ROM streams from. The two jingles play once, as
# 2.1 plays its own; the rest loop as the DOS version loops them.
foreach(SONG METAHEAD GETPSYCH METALBOP ROBOATTK RUSHING WIN LOSE)
    string(TOLOWER ${SONG} LOWER)
    if(SONG STREQUAL "WIN" OR SONG STREQUAL "LOSE")
        set(ONCE --once)
    else()
        set(ONCE)
    endif()
    add_custom_command(
        OUTPUT ${AGEN}/${LOWER}.vgm
        DEPENDS ${CONV}/conv_adl.py ${DOS}/${SONG}.ADL
        COMMAND ${Python3_EXECUTABLE} ${CONV}/conv_adl.py song
                ${DOS}/${SONG}.ADL ${AGEN}/${LOWER}.vgm ${ONCE}
        COMMENT "asset ${LOWER}.vgm"
        VERBATIM)
    list(APPEND PETSCII_ASSETS ${AGEN}/${LOWER}.vgm)
endforeach()

add_custom_target(petscii_assets DEPENDS ${PETSCII_ASSETS})
