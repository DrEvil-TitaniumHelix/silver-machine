"""Original art, decoded in memory; no GUI, dependencies, or writes.

Sources below are relative to GoldBoxUnified: survey/DAX_SWEEP.md section 2
(P4/A4/F1), survey/LAYOUTS.md section 3 (WALLDEF), decode/secret/
ENGINE_READ_w5.md (02BC pictures, 0540 text), ENGINE_READ_w6.md (ov30/34/36),
and GATE.md section 1 (wall loading). survey/tools/daxpic.py was evidence only.

picture(name, id, dataset=1) -> (width, height, frames); frames are immutable
tuples of byte rows containing EGA indices. For A4, frames share a canvas,
placed at their header's x/y * 8 with colour 0 outside their rectangle.
record() preserves native rectangles, delays and CGA maps for animation and
lossless encode(). P4 tile sets retain their native size (origins are metadata).
glyph(str) returns eight byte row masks (bit 7 left) using UpCase(ch) mod 64;
glyph(int) selects a raw glyph, including the extra symbols. F1 picture()
instead returns 0/1 pixels. SECRET's actual font is 8X8D5/201,
not 8X8D1/201: 0540:018F..01B5 (local/w5/res_0540.lst; LAYOUT.md section 3).
symbols(record_id, dataset=1) returns the frames of an 8x8 set. symbol(number,
slots) addresses the five loaded sets as ov36 does (slots may contain None).
walls(id, dataset=1, slot=1) returns WallBlocks, each with five 156-symbol types
and its associated 8x8 record id. wall_piece() slices one of the ten pieces.

Explicit filenames (e.g. PIC2 or PIC2.DAX) select exactly that file. Bare
families follow the engine's data-set rules, including PIC4/5 exceptions,
SPRIT1, CPIC1, and data set 5 -> 8X8D1. HEAD/BODY are supported loaders but
those files are absent from shipped SECRET (DAX_SWEEP.md section 3).
Run the complete, headless V-check with python -m sm.titles.ssb.art.
"""
from sm.titles.ssb import data as ssb_data
from functools import lru_cache
import re
import struct
from typing import NamedTuple

from sm import dax


# Standard IBM EGA default palette; DAX_SWEEP.md section 2. Not asset bytes.
from sm.ui.art import PALETTE, Part, Record, decode, encode, _pack
FONT_SOURCE = '8X8D5'
SYMBOL_BASES = (1, 0x2E, 0x74, 0xBA, 0x100)  # ov36:01C4, DS:1A7C
SYMBOL_LIMIT = 0x14E
class WallBlock(NamedTuple):
    """One 780-byte block after symbol rebasing; GATE.md 1, ov31:101B."""
    slot: int
    symbol_set: int
    types: tuple


class WallPiece(NamedTuple):
    """Descriptor used by ov31:0429 DrawWallPiece; DS:0AD8..0B1C."""
    offset: int
    width: int
    height: int
    x: int
    y: int


def source(name, id, dataset=1):
    """ENGINE_READ_w6.md ov30 e4/e7/e9, ov34 e5, ov36 e2: filename routing."""
    name = name.upper()
    if name.endswith('.DAX'):
        name = name[:-4]
    if not re.fullmatch('[A-Z0-9]+', name):
        raise ValueError('expected a DAX basename, not a path')
    if not isinstance(id, int) or not 0 <= id <= 255:
        raise ValueError('DAX record id must be 0..255')
    if not isinstance(dataset, int) or not 1 <= dataset <= 5:
        raise ValueError('data set must be 1..5')
    if name == 'PIC':
        dataset = 4 if id in (6, 0x3B, 0x3C, 0x42, 0x45, 0x47, 0x59) else (
            5 if id in (1, 0x11, 0x4D, 0x1B) else dataset)
    elif name in ('SPRIT', 'CPIC'):
        dataset = 1
    elif name == '8X8D' and dataset == 5:
        dataset = 1
    if name in ('PIC', 'SPRIT', 'FINAL', 'BIGPIC', 'HEAD', 'BODY', 'CPIC', '8X8D', 'WALLDEF'):
        name += str(dataset)
    return name


@lru_cache(maxsize=256)
def record(name, id, dataset=1):
    """02BC:0118 LoadPicture; ov30:00EC; 0540:0184 (F1 in SECRET's 8X8D5)."""
    name = source(name, id, dataset)
    family = re.sub(r'\d+$', '', name)
    font = id == 201 and name in ('8X8D1', '8X8D5')
    return decode(dax.load(name, d=ssb_data.SECRET)[id], kind='F1' if font else None,
                  delta=family in ('PIC', 'FINAL'))


@lru_cache(maxsize=128)
def picture(name, id, dataset=1):
    """02BC:0118; ov30:07E3 places A4 SPRIT rectangles at (x*8, y*8).

    Common canvas for animations; native rectangles remain in record().
    The unused area is colour 0 (ov30:0518..053D transparency argument).
    """
    decoded = record(name, id, dataset)
    if decoded.kind != 'A4':
        part = decoded.parts[0]
        return part.width, part.height, part.frames
    w = max(p.x * 8 + p.width for p in decoded.parts)
    h = max(p.y * 8 + p.height for p in decoded.parts)
    frames = []
    for part in decoded.parts:
        for frame in part.frames:
            if (part.x, part.y, part.width, part.height) == (0, 0, w, h):
                frames.append(frame)
                continue
            rows = [bytes(w)] * h
            for y, row in enumerate(frame, part.y * 8):
                rows[y] = bytes(part.x * 8) + row + bytes(w - part.x * 8 - part.width)
            frames.append(tuple(rows))
    return w, h, tuple(frames)


@lru_cache(maxsize=256)
def glyph(ch):
    """0540:0184 LoadTextFont; 01E7 DrawGlyph, UpCase(ch) mod 40h; bit 7 left."""
    if isinstance(ch, str):
        if len(ch) != 1 or ord(ch) > 255:
            raise ValueError('glyph expects one byte character')
        n = ord(ch)
        ch = (n - 32 if 97 <= n <= 122 else n) % 64
    frames = record(FONT_SOURCE, 201).parts[0].frames
    if not isinstance(ch, int) or not 0 <= ch < len(frames):
        raise ValueError('glyph index out of range')
    return _pack(frames[ch], 8, 8, 1)


def symbols(set, dataset=1):
    """ENGINE_READ_w6.md ov36:004D Load8x8Set: data set 5 reads 8X8D1."""
    w, h, frames = picture('8X8D', set, dataset)
    if (w, h) != (8, 8):
        raise ValueError('symbol set must contain 8x8 tiles')
    return frames


def symbol(number, slots):
    """ENGINE_READ_w6.md ov36:01C4: ranges 1..2D/73/B9/FF/14D, nil -> skip."""
    if not isinstance(number, int) or not 1 <= number < SYMBOL_LIMIT or len(slots) != 5:
        raise ValueError('symbol requires number 1..14Dh and five slots')
    slot = next(i for i in range(4, -1, -1) if number >= SYMBOL_BASES[i])
    frames = slots[slot]
    if frames is None:
        return None
    index = number - SYMBOL_BASES[slot]
    if index >= len(frames):
        raise ValueError('symbol outside loaded set')
    return frames[index]


@lru_cache(maxsize=1)
def wall_layout():
    """ov31:0429 DrawWallPiece; DS:0AD8/0AE2/0AEC bytes, 0AF6/0B0A words.

    GATE.md 2 + asm-cited evidence titles/ssb/areas/view_ov30.js, checked
    against local/rt/ov31.lst 0436/044A/0463. Tables read from ST.EXE at runtime.
    """
    ds = ssb_data.stexe()
    xs, ys = struct.unpack_from('<10H', ds, 0xAF6), struct.unpack_from('<10H', ds, 0xB0A)
    return tuple(WallPiece(ds[0xAD8 + i], ds[0xAE2 + i], ds[0xAEC + i], xs[i], ys[i])
                 for i in range(10))


def decode_walls(data, id, slot=1):
    """LAYOUTS.md 3; GATE.md 1 ov31:101B, rebase >=45 by the START slot.

    Multi-block records already address successive sets. All blocks receive
    the same starting-slot delta, with byte wrap, not a delta per block.
    """
    n = len(data) // 780
    if not n or len(data) % 780 or slot not in (1, 2, 3) or slot + n > 4:
        raise ValueError('WALLDEF must fit whole 780-byte blocks in slots 1..3')
    if not isinstance(id, int) or not 0 <= id <= 255:
        raise ValueError('wall id must be 0..255')
    delta = SYMBOL_BASES[slot] - SYMBOL_BASES[1]
    blocks = []
    for k in range(n):
        raw = data[k * 780:(k + 1) * 780]
        values = bytes((b + delta) & 255 if b >= 45 else b for b in raw)
        types = tuple(tuple(values[t:t + 156]) for t in range(0, 780, 156))
        blocks.append(WallBlock(slot + k, (id * 10 + k + 1) & 255 if n > 1 else id, types))
    return tuple(blocks)


@lru_cache(maxsize=64)
def walls(id, dataset=1, slot=1):
    """GATE.md 1, ov31:101B: WALLDEF<dataset>/id -> wall blocks and tile ids."""
    return decode_walls(dax.load(source('WALLDEF', id, dataset), d=ssb_data.SECRET)[id], id, slot)


def wall_piece(block, wall_type, piece):
    """ov31:0429: type 1..5, piece 0..9 -> row-major symbol grid (0 = skip)."""
    if wall_type not in range(1, 6) or piece not in range(10):
        raise ValueError('wall type must be 1..5 and piece 0..9')
    p = wall_layout()[piece]
    data = block.types[wall_type - 1]
    return tuple(data[i:i + p.width] for i in range(p.offset, p.offset + p.width * p.height, p.width))


def test():
    """UI1 V-check; DAX_SWEEP 2/3 counts, GATE 1 walls, ov36 symbol bounds."""
    from sm.titles.ssb.ui._art_test import check
    return check()


if __name__ == '__main__':
    test()
