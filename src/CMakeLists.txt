add_executable(robots)
target_sources(robots PRIVATE
    main.c
    platform.c
    view.c                    # the playfield: tile sprites over a tile cache
    view_io.s                 # its RIA register work: async loads, pointers
    livemap.c                 # the live map, played on as on the Amiga
    livemap.s                 # its drawing: the whole map, and a square
    palette.c                 # the palettes, faded as the Amiga fades them
    palette.s                 # the fade itself, from the VSYNC interrupt
    input.c
    sound.c                   # the OPL2 and the VIA's timer, set up
    sound.s                   # the effects, played from the VIA's interrupt
    ${PETSCII_SFX}            # and their streams, made by conv_adl.py
    ${PETSCII_AMIGA_TABLES}   # tables from the art, made by conv_amiga.py
    # David Murray's game logic, converted from ACME to ca65. These are the
    # original instructions, not a transliteration, so they behave exactly as
    # the X16 build does.
    game/background_tasks.s   # the AI dispatcher and all 24 unit types
    game/window.s             # what should be on screen, not how to draw it
    game/transporter.s        # unit type 23, kept apart as the X16 did
    game/difficulty.s         # SET_DIFF_LEVEL, which INIT_GAME runs on the map
    game/messages.s
    game/screens.s            # the custom keys layout and the cinema marquee
    game/items.s              # using, searching, pushing, firing
    game/irq.s                # the VSYNC interrupt: timers and the game clock
    game/globals.s
    game/capi.s               # cc65 name aliasing, the only file that knows C exists
    game/platform_bridge.s    # the AI's calls into the platform layer
)
target_include_directories(robots PRIVATE ${CMAKE_CURRENT_LIST_DIR})

add_dependencies(robots petscii_assets)

# GET_TILE_FROM_MAP builds the map address arithmetically rather than by
# indexing, so MAP has to start on a page boundary. cc65's stock rp6502.cfg has
# no aligned segment, so the project has its own, with LEVELDATA added.
target_link_options(robots PRIVATE -C ${CMAKE_CURRENT_LIST_DIR}/rp6502.cfg)
# ...and relink when it changes, which CMake does not infer from a link option.
set_property(TARGET robots PROPERTY LINK_DEPENDS
             ${CMAKE_CURRENT_LIST_DIR}/rp6502.cfg)

# Static XRAM: loaded straight into place when the ROM loads, costing the 6502
# nothing at run time. Each address is the xram.h symbol, read from robots.sym
# after the link, so moving a member of xram_layout_t moves its asset with it.
rp6502_asset(robots XRAM(XRAM_ANIM)      ${AGEN}/anim.bin)
rp6502_asset(robots XRAM(XRAM_UNITS)     ${AGEN}/units.bin)
rp6502_asset(robots XRAM(XRAM_KEYS)      ${AGEN}/keys.bin)
rp6502_asset(robots XRAM(XRAM_CURSOR)    ${AGEN}/cursors.bin)
rp6502_asset(robots XRAM(XRAM_HUD_TILES) ${AGEN}/hud_tiles.bin)
rp6502_asset(robots XRAM(XRAM_HUD_MAP)   ${AGEN}/hud_map.bin)
rp6502_asset(robots XRAM(XRAM_FONT)      ${AGEN}/font.bin)

# Named files in the ROM's micro filesystem, opened at run time. images comes
# first because the RIA finds a named asset by walking the list, and it is the
# one the game opens and keeps open: the 253 tiles, the player's frames and the
# HUD's pictures, read a record at a time. The two pictures share the tile
# cache's XRAM, and 18 levels are 153 KB, so neither can be resident.
rp6502_asset(robots images   ${AGEN}/images.bin)
rp6502_asset(robots tiles    ${AGEN}/tiles.bin)
rp6502_asset(robots intro    ${AGEN}/intro.bin)
rp6502_asset(robots gameover ${AGEN}/gameover.bin)
foreach(L a b c d e f g h i j k l m n o p q r)
    rp6502_asset(robots level-${L} ${AGEN}/level-${L}.bin)
endforeach()
# The DOS version's songs, read 512 bytes at a time while they play
# (src/sound.c); src/sound.c names them.
foreach(SONG metahead win lose getpsych metalbop roboattk rushing)
    rp6502_asset(robots ${SONG} ${AGEN}/${SONG}.vgm)
endforeach()

# Configs, palettes and sprite arrays must start on even addresses.
rp6502_align(robots "XRAM_.*")
rp6502_executable(robots DATA default RESET default)

# The web player: web/robots.zip in the build folder, which .github/workflows/
# web.yml publishes to GitHub Pages. The game saves nothing, so no db. The
# screen is 16:10 from the start, the shape of the game's 320x200 canvas, so
# the console before it does not show as 4:3 first.
rp6502_web(robots CONFIG [[
    title: 'Attack of the PETSCII Robots',
    aspect: '16:10',
    footer: 'Gamepad or Keyboard. Walk:IJKL Fire:WASD Search:Z Move:M Use:Space Weapon/item:F1/F2 Map:Tab Pause:Esc',
]])
