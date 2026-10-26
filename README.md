# Attack of the PETSCII Robots — Picocomputer 6502

David Murray's *Attack of the PETSCII Robots* for the
[Picocomputer 6502](https://picocomputer.github.io/): the RP6502 version, put
together from several others. The game logic is his own 6502 assembly from the Commander X16
version, converted to ca65, and the eighteen maps are those of its version 2.1.
The graphics are the Amiga version's, with the title and the sprites as 2.1
reworked them, and so is the live map you can play on. The sound effects and
the music are the MS-DOS version's for the AdLib, played on the RP6502's OPL2,
the AdLib's own chip. The input is new.

Play it in a browser:

<!-- rp6502
preset: cc65/Release
publish: robots.zip
frames: 150
-->
[![Attack of the PETSCII Robots](https://rumbledethumps.github.io/PETSCII-Robots/robots/screenshot.png)](https://rumbledethumps.github.io/PETSCII-Robots/robots/)


[Run it in your browser](https://rumbledethumps.github.io/PETSCII-Robots/robots/).

## Controls

A gamepad is always live, whichever keyboard scheme is selected — plug one in
and it works. The intro menu's control option chooses only which *keys* are
used: **default**, or **custom**, which asks you for thirteen of your own when
you start the game. The menu itself can be driven with either.

### Gamepad

| Input | Action |
| --- | --- |
| D-pad, or left stick | Walk |
| Face buttons, or right stick | Fire in that direction |
| L1 | Search |
| R1 | Push / move object |
| Start | Use item |
| Select + L1 | Cycle item |
| Select + R1 | Cycle weapon |
| Select + Left | Live map on / off |
| Select + Down | Robots on the live map on / off |
| D-pad / Start / bottom button | Navigate and choose, in menus |

Face buttons fire in the direction of the button under your thumb — top fires
up, bottom fires down, left fires left, right fires right — regardless of
whether the pad labels them in the Nintendo, Xbox or PlayStation arrangement.

### Keyboard (default)

| Key | Action |
| --- | --- |
| I K J L | Walk up, down, left, right |
| W S A D | Fire up, down, left, right |
| F1 / F2 | Cycle weapon / item |
| F6 or Shift + M | Music on / off |
| Shift + [ / Shift + ] | Effects volume down / up |
| Space | Use item |
| Z | Search |
| M | Push / move object |
| Tab | Live map on / off |
| Shift + Tab | Robots on the live map on / off |
| Esc | Pause; Y quits to the statistics |
| Shift + C | The original's cheat: every key, weapon and item |

Cursor keys also walk, and choose in menus.

## Building

The build needs CMake 3.28, Ninja, Python 3, and the Picocomputer fork of cc65
(see the [SDK documentation](https://picocomputer.github.io/sdk.html)). The
first configure downloads the emulator that the tests run.

```sh
cmake --workflow --preset check
```

That configures, builds `build/cc65/release/src/robots/robots.rp6502` and the
web player in `build/cc65/release/web/`, and runs every test: the checks on
the source, the asset invariants, and the emulator scripts in `tests/emu`. `docs/test-abi.md`
describes what the scripts can rely on, and `docs/porting-notes.md` records
how the RP6502 version is put together and where it departs from its sources.
