"""A minimal PNG reader for indexed images, standard library only.

CI and the Picocomputer's web runner have no Pillow, and the Amiga art is all
palette PNGs, so this reads exactly that: non-interlaced colour type 3 at bit
depth 1, 2, 4 or 8, with any of the five scanline filters. Anything else is
rejected rather than guessed at. Chunk CRCs are checked, so a truncated or
corrupted download fails here instead of turning into wrong pixels.

    width, height, palette, rows = png.read(path)

palette is a list of (r, g, b) tuples in PLTE order; rows is a list of height
lists, each of width palette indices.
"""
import pathlib
import struct
import zlib
from typing import List, NamedTuple, Tuple

SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Image(NamedTuple):
    width: int
    height: int
    palette: List[Tuple[int, int, int]]
    rows: List[List[int]]


class PNGError(ValueError):
    pass


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(data: bytes, height: int, stride: int, bpp: int) -> List[bytearray]:
    """Undo the per-scanline filters. bpp is bytes per complete pixel, min 1."""
    if len(data) < height * (stride + 1):
        raise PNGError(f"image data short: {len(data)} < {height * (stride + 1)}")
    out = []
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = data[pos]
        line = bytearray(data[pos + 1:pos + 1 + stride])
        pos += stride + 1
        if ftype == 0:
            pass
        elif ftype == 1:                                   # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:                                   # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:                                   # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:                                   # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
        else:
            raise PNGError(f"row {y}: unknown filter type {ftype}")
        out.append(line)
        prev = line
    return out


def _unpack(line: bytes, width: int, depth: int) -> List[int]:
    if depth == 8:
        return list(line[:width])
    per = 8 // depth
    mask = (1 << depth) - 1
    px = []
    for b in line:
        for k in range(per):                               # MSB is leftmost
            px.append((b >> (8 - depth * (k + 1))) & mask)
    return px[:width]


def read(path) -> Image:
    raw = pathlib.Path(path).read_bytes()
    if raw[:8] != SIGNATURE:
        raise PNGError(f"{path}: not a PNG")
    pos = 8
    ihdr = None
    palette = None
    idat = bytearray()
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise PNGError(f"{path}: truncated chunk header")
        length, ctype = struct.unpack(">I4s", raw[pos:pos + 8])
        body = raw[pos + 8:pos + 8 + length]
        crc_at = pos + 8 + length
        if crc_at + 4 > len(raw):
            raise PNGError(f"{path}: truncated {ctype!r} chunk")
        (crc,) = struct.unpack(">I", raw[crc_at:crc_at + 4])
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != crc:
            raise PNGError(f"{path}: bad CRC in {ctype!r} chunk")
        pos = crc_at + 4
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif ctype == b"PLTE":
            if length % 3:
                raise PNGError(f"{path}: PLTE length {length} not a multiple of 3")
            palette = [tuple(body[i:i + 3]) for i in range(0, length, 3)]
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
    if ihdr is None:
        raise PNGError(f"{path}: no IHDR")
    width, height, depth, colour, comp, filt, interlace = ihdr
    if colour != 3:
        raise PNGError(f"{path}: colour type {colour}, only 3 (indexed) is supported")
    if depth not in (1, 2, 4, 8):
        raise PNGError(f"{path}: bit depth {depth} invalid for indexed colour")
    if comp != 0 or filt != 0:
        raise PNGError(f"{path}: unknown compression/filter method {comp}/{filt}")
    if interlace != 0:
        raise PNGError(f"{path}: interlaced PNGs are not supported")
    if palette is None:
        raise PNGError(f"{path}: indexed image without PLTE")

    stride = (width * depth + 7) // 8
    lines = _unfilter(zlib.decompress(bytes(idat)), height, stride, max(1, depth // 8))
    rows = [_unpack(line, width, depth) for line in lines]
    top = max(max(r) for r in rows) if rows else 0
    if top >= len(palette):
        raise PNGError(f"{path}: pixel index {top} beyond the {len(palette)}-entry palette")
    return Image(width, height, palette, rows)
