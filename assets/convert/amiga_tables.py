"""Tables transcribed from the Amiga port's source, not derived from the art.

Source: zeropolis79/PETSCIIRobots-Amiga, PlatformAmiga.cpp (Vesa Halttunen,
CC BY 4.0). Line numbers are that file's. Values are copied exactly; anything
the RP6502 version decides for itself lives in conv_amiga.py instead.
"""

# ---- animated tiles ------------------------------------------------------
# animTileMap, 370-387: tile -> first frame in animtiles.png; every other entry
# is -1. The frame count is the gap to the next base (24 frames in all), and
# the Amiga adds a 0-3 or 0-1 variant to the base.
ANIM_TILE_MAP = {
    66: 0, 148: 4, 196: 8, 197: 10, 200: 12, 201: 14, 143: 16, 204: 20,
}
ANIM_FRAMES = 24

# ---- live map ------------------------------------------------------------
# tileLiveMap, 465-482: tile -> game palette index for the one-pixel-per-tile
# overview map.
TILE_LIVE_MAP = [
     0, 13,  1,  1,  1,  1,  1,  1,  1,  5,  1,  1,  1,  1, 13,  1,
     1,  1,  1,  1,  1,  1,  1,  2,  8,  1,  1,  1,  1,  6, 14, 14,
    15, 13, 14, 15, 15, 13,  5, 15,  6, 13, 13, 12,  6, 13, 13, 12,
     1,  1,  1, 12,  1,  9,  9,  6,  1,  9, 15,  6, 10, 10,  1,  1,
     1,  1,  7, 13,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,
     4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,
     2,  2, 13, 13, 13, 13, 13, 13,  1,  1,  1, 13,  4,  4,  4,  0,
     1,  1,  4, 13,  4,  4,  4,  1,  1,  1,  2,  2,  2,  2,  2,  2,
     1,  1, 13, 10,  1,  1, 13,  9,  1,  1,  4,  5, 13, 13, 13,  4,
     1,  1,  1,  1, 15,  5, 15, 15,  1,  1,  6,  6, 15, 15,  6,  5,
     2,  2,  2,  5, 13, 13,  1,  7,  5,  3,  1,  7,  4,  4,  4, 13,
     1,  1,  1,  1,  1,  4,  4,  2,  3,  3,  3,  1,  3,  2,  3,  3,
     3,  3,  3,  1,  4,  4,  9,  9,  4,  4,  2,  2,  5, 11, 12, 12,
     8,  8,  8,  9,  3,  3,  2, 10,  1,  1,  1,  9,  1,  1,  1, 10,
     1,  1,  1, 13,  8,  8, 13, 13,  8,  8, 13, 13,  3,  3, 13, 13,
    13, 13,  5, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13,
]

# ---- HUD art geometry ----------------------------------------------------
# renderItem / renderKey / renderHealth / renderFace, 1879-1912: each strip is
# frames stacked vertically at these sizes. renderFace's faces are not here:
# the intro robot's eyes are X16 2.1's (conv_amiga.py).
ITEM_W, ITEM_H, ITEMS = 48, 21, 6        # pistol, plasma, medkit, EMP, magnet, timebomb
HEALTH_W, HEALTH_H, HEALTHS = 48, 51, 6
KEY_W, KEY_H, KEYS = 16, 14, 3           # spade, heart, star

assert len(TILE_LIVE_MAP) == 256
