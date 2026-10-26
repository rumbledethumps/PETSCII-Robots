# Commander X16

The maps, tables and pictures of David Murray's Commander X16 version of
*Attack of the PETSCII Robots*, unchanged.

| File | What it is | Read by |
|---|---|---|
| `LEVEL-A` .. `LEVEL-R` | The eighteen maps: a 2-byte load address, then the unit tables and the 128×64 map. | `conv_level.py` |
| `ROBOTS.PRG` | The game, loading at `$0801`, for its palettes and map names. | `conv_amiga.py`, `clean_title.py` |
| `TILESET.GFX` | The tile tables: what each tile becomes when destroyed, and its behaviour bits. | `conv_tiles.py` |
| `sprites.bin` | 104 sprites, 32×32 at 4 bits per pixel: the player, the robots, the cursor icons. | `conv_amiga.py` |
| `tiles.bin` | 256 tiles, 24×24 at 4 bits per pixel, 28 to each 8 KB page; tiles 155 and 246 come from here. | `conv_amiga.py` |
| `faces.bin` | The intro robot's eyes. | `conv_amiga.py` |
| `title.bin` | The title screen, 320×240 at 4 bits per pixel, cut to 320×200. | `clean_title.py` |

The tests read them too.
