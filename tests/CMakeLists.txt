# Everything CTest runs; CI just runs ctest.

# What the source has to keep that no game test can see: the game's zero page,
# and SEARCH_OBJECT's returns. It reads the source, nothing built.
add_test(NAME source.checks
         COMMAND ${Python3_EXECUTABLE}
                 ${CMAKE_CURRENT_LIST_DIR}/source/verify_source.py
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(source.checks PROPERTIES LABELS source TIMEOUT 60)

# The invariants the platform layer assumes of the converted assets. These read
# assets/gen, which the ROM build produces, so it waits for the build fixture
# that rp6502_test() sets up.
add_test(NAME assets.invariants
         COMMAND ${Python3_EXECUTABLE}
                 ${CMAKE_CURRENT_LIST_DIR}/assets/verify_assets.py
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(assets.invariants PROPERTIES LABELS assets TIMEOUT 120
                     FIXTURES_REQUIRED rp6502.build)

add_subdirectory(emu)
