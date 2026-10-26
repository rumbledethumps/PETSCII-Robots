# MS-DOS

The sound effects and the music of David Murray's MS-DOS version of *Attack of
the PETSCII Robots*, for the AdLib card, whose OPL2 chip the RP6502 has,
unchanged. The DOS source,
[zeropolis79/PETSCIIRobots-MSDOS](https://github.com/zeropolis79/PETSCIIRobots-MSDOS),
plays them with the SSY player in its `audio.c`, about 72 times a second.

| File | What it is | Read by |
|---|---|---|
| `SOUNDFX.ADL` | The seventeen sound effects. | `conv_adl.py` |
| `METAHEAD.ADL` | The title music. | `conv_adl.py` |
| `GETPSYCH.ADL`, `METALBOP.ADL`, `ROBOATTK.ADL`, `RUSHING.ADL` | The level music, in turn by map. | `conv_adl.py` |
| `WIN.ADL`, `LOSE.ADL` | The endings' music. | `conv_adl.py` |

The tests read them too.
