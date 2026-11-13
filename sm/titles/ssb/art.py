from sm.titles.ssb import data as ssb_data
from functools import lru_cache
import re
import struct
from typing import NamedTuple

from sm import dax


from sm.ui.art import PALETTE, Part, Record, decode, encode, _pack
FONT_SOURCE = '8X8D5'
SYMBOL_BASES = (1, 0x2E, 0x74, 0xBA, 0x100)
SYMBOL_LIMIT = 0x14E
class WallBlock(NamedTuple):
    slot: int
    symbol_set: int
    types: tuple


class WallPiece(NamedTuple):
    offset: int
    width: int
    height: int
    x: int
    y: int


def source(name, id, dataset=1):
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
    name = source(name, id, dataset)
    family = re.sub(r'\d+$', '', name)
    font = id == 201 and name in ('8X8D1', '8X8D5')
    return decode(dax.load(name, d=ssb_data.SECRET)[id], kind='F1' if font else None,
                  delta=family in ('PIC', 'FINAL'))


@lru_cache(maxsize=128)
def picture(name, id, dataset=1):
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
    w, h, frames = picture('8X8D', set, dataset)
    if (w, h) != (8, 8):
        raise ValueError('symbol set must contain 8x8 tiles')
    return frames


def symbol(number, slots):
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
    ds = ssb_data.stexe()
    xs, ys = struct.unpack_from('<10H', ds, 0xAF6), struct.unpack_from('<10H', ds, 0xB0A)
    return tuple(WallPiece(ds[0xAD8 + i], ds[0xAE2 + i], ds[0xAEC + i], xs[i], ys[i])
                 for i in range(10))


def decode_walls(data, id, slot=1):
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
    return decode_walls(dax.load(source('WALLDEF', id, dataset), d=ssb_data.SECRET)[id], id, slot)


def wall_piece(block, wall_type, piece):
    if wall_type not in range(1, 6) or piece not in range(10):
        raise ValueError('wall type must be 1..5 and piece 0..9')
    p = wall_layout()[piece]
    data = block.types[wall_type - 1]
    return tuple(data[i:i + p.width] for i in range(p.offset, p.offset + p.width * p.height, p.width))


def test():
    from sm.titles.ssb.ui._art_test import check
    return check()


if __name__ == '__main__':
    test()
