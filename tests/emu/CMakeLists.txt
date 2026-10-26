# The emulator script tests. rp6502_test() runs each one in its own folder under
# build/<preset>/test/, with the emulator that configure linked there and an
# empty save folder. Names in the scripts, such as UNIT_TYPE or XRAM_PROBE, are
# looked up in robots.sym, which sits beside the ROM. docs/test-abi.md says what
# a test can rely on.
#
# An explicit list, not a glob: this file is a .txt too.

set(ROM $<TARGET_PROPERTY:robots,RP6502_ROM>)

# These also read what is on screen -- sprite records, text cells, palettes,
# plane configs, the live map -- so they change with the graphics. The rest
# check only game state: the probe, RAM, the OPL2.
set(SCREEN bringup animate overlay irq_zp gamezp controls elevator gameover
    search endgame)

foreach(t menu bringup walk ai search search_items irq_zp
          gamezp animate overlay flash keys gamepad controls elevator
          endgame gameover)
    rp6502_test(NAME emu.${t} COMMAND ${t}.txt --mute ${ROM})
    if(t IN_LIST SCREEN)
        set_tests_properties(emu.${t} PROPERTIES LABELS "emu;screen")
    else()
        set_tests_properties(emu.${t} PROPERTIES LABELS emu)
    endif()
    set_tests_properties(emu.${t} PROPERTIES TIMEOUT 120)
endforeach()
set_tests_properties(emu.endgame emu.gameover PROPERTIES TIMEOUT 180)

# Python tests drive the emulator through rp6502.Emu, with petscii.py beside
# them for the moves every test makes.
foreach(t levels render livemap effects units difficulty title cursor sound
          playkeys water)
    rp6502_test(NAME emu.${t} COMMAND ${t}.py --mute ${ROM})
    set_tests_properties(emu.${t} PROPERTIES LABELS emu TIMEOUT 300)
endforeach()
set_tests_properties(emu.levels emu.render emu.livemap emu.effects emu.units
                     emu.title emu.cursor emu.playkeys emu.water
                     PROPERTIES LABELS "emu;screen")
