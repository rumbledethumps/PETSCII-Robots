# Attack of the PETSCII Robots — RP6502 version.
#
# The SDK's template shape: tools/rp6502.cmake picks the toolchain from the
# preset, so it is included before project(). `cmake --list-presets` shows the
# builds.

cmake_minimum_required(VERSION 3.28)

include(${CMAKE_CURRENT_LIST_DIR}/tools/rp6502.cmake)

project(petscii-robots-rp6502 VERSION 0.1.0 LANGUAGES C ASM)

# Every emulator the build links, for the ROM and for each test, and the web
# player, are this release: the first with the 320x200 canvas. The tests are
# tuned to its frame timing, so it moves on purpose.
set(RP6502_EMU_VERSION 0.42)
set(RP6502_WEB_VERSION 0.42)

include(${CMAKE_CURRENT_LIST_DIR}/assets/assets.cmake)
add_subdirectory(src)
add_subdirectory(tests)
