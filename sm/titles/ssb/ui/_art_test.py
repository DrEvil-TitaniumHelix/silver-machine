"""Headless UI1 decoder V-check; generated fixtures plus Bruce's read-only DAX.

Sources: survey/DAX_SWEEP.md sections 2/3, survey/LAYOUTS.md section 3,
decode/secret/ENGINE_READ_w5.md 0540, ENGINE_READ_w6.md ov30/34/36,
GATE.md section 1. All original pixel data remains in memory.
"""
from sm.titles.ssb import data as ssb_data
from collections import Counter
from pathlib import Path
import struct
import time

from sm import dax
from sm.titles.ssb import art


def _reject(function, *args, **kwargs):
    """DAX_SWEEP 2: dimensions/counts must consume an exact record."""
    try:
        function(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError('invalid input accepted by ' + function.__name__)


def _p4(pixels, *, width=8, height=1, count=1, x=0, y=0):
    """DAX_SWEEP 2: a constructed P4 header, never an original fixture."""
    return struct.pack('<4HB', height, width // 8, x, y, count) + bytes(range(8)) + pixels


def _synthetic():
    """DAX_SWEEP 2; ov30 delta frames, ov36 slot boundaries, ov31 rebase >=45."""
    raw = _p4(bytes(range(16)), height=2, count=2, x=3, y=4)
    decoded = art.decode(raw)
    part = decoded.parts[0]
    assert (part.width, part.height, part.x, part.y, len(part.frames)) == (8, 2, 3, 4, 2)
    assert part.frames[0][0] == bytes((0, 0, 0, 1, 0, 2, 0, 3))
    assert part.frames[1][1] == bytes((0, 12, 0, 13, 0, 14, 0, 15))
    assert art.encode(decoded) == raw
    # Three frames distinguish key-frame XOR from a running/previous-frame XOR.
    animation = b'\3' + b''.join(struct.pack('<I', i + 10) + _p4(bytes([v]) * 4)
                                  for i, v in enumerate((0x12, 0x34, 0x56)))
    direct, delta = art.decode(animation), art.decode(animation, delta=True)
    assert [p.delay for p in delta.parts] == [10, 11, 12]
    assert [p.frames[0][0][:2] for p in direct.parts] == [b'\1\2', b'\3\4', b'\5\6']
    assert [p.frames[0][0][:2] for p in delta.parts] == [b'\1\2', b'\2\6', b'\4\4']
    assert art.encode(delta) == animation == art.encode(direct)
    font = bytes((128 >> i) for i in range(8))
    f1 = art.decode(font, kind='F1')
    assert all(row == bytes(int(x == y) for x in range(8))
               for y, row in enumerate(f1.parts[0].frames[0]))
    assert art.encode(f1) == font
    for bad in (b'', raw[:16], raw[:-1], raw + b'\0', _p4(b'', count=0),
                _p4(b'', width=0), animation[:-1], animation + b'\0', b'\11' + animation[1:]):
        _reject(art.decode, bad)
    _reject(art.decode, font[:-1], kind='F1')
    _reject(art.decode, raw, kind='other')
    _reject(art.decode, b'\2' + bytes(4) + _p4(bytes(4)) + bytes(4) + _p4(bytes(8), height=2), delta=True)
    _reject(art._pack, ((16,) * 8,), 8, 1)
    _reject(art._pack, ((0,) * 7,), 8, 1)
    # Sentinel frames make slot selection independent of any original pixels.
    slots = tuple(tuple((s, i) for i in range(n)) for s, n in enumerate((45, 70, 70, 70, 78)))
    for s, first in enumerate(art.SYMBOL_BASES):
        last = (art.SYMBOL_BASES + (art.SYMBOL_LIMIT,))[s + 1] - 1
        assert art.symbol(first, slots) == (s, 0)
        assert art.symbol(last, slots) == (s, last - first)
    assert art.symbol(46, (None,) * 5) is None
    for number in (0, -1, 334):
        _reject(art.symbol, number, slots)
    _reject(art.symbol, 1, ())
    _reject(art.symbol, 1, ((), None, None, None, None))
    wall = bytes((0, 44, 45, 46, 185, 255)) * 130
    block, = art.decode_walls(wall, 6, 3)
    assert block.slot == 3 and block.symbol_set == 6
    assert block.types[0][:6] == (0, 44, 185, 186, 69, 139)
    blocks = art.decode_walls(wall * 2, 7, 2)
    assert [b.symbol_set for b in blocks] == [71, 72]
    assert blocks[0].types == blocks[1].types  # starting slot, not target slot
    for bad in (b'', wall[:-1], wall * 4):
        _reject(art.decode_walls, bad, 6)
    _reject(art.decode_walls, wall * 2, 7, 3)
    _reject(art.decode_walls, wall, 6, 0)
    _reject(art.wall_piece, block, 0, 0)
    _reject(art.wall_piece, block, 1, 10)


def _plane_bytes(rows, width, height):
    """DAX_SWEEP 2 / 02BC:02AC: independent 4 bitplane reconstruction of P4.

    Extract four 1bpp planes, then pack pairs of pixels from those planes.
    This deliberately does not call the decoder's nibble lookup or encoder.
    """
    planes = []
    for bit in range(4):
        plane = bytearray()
        for row in rows:
            for x in range(0, width, 8):
                mask = 0
                for pixel in row[x:x + 8]:
                    mask = (mask << 1) | ((pixel >> bit) & 1)
                plane.append(mask)
        planes.append(plane)
    out = bytearray()
    pair = tuple(tuple(((p >> 1) << (bit + 4)) | ((p & 1) << bit) for p in range(4)) for bit in range(4))
    for i in range(height * (width // 8)):
        for shift in (6, 4, 2, 0):
            out.append(pair[0][(planes[0][i] >> shift) & 3] | pair[1][(planes[1][i] >> shift) & 3] |
                       pair[2][(planes[2][i] >> shift) & 3] | pair[3][(planes[3][i] >> shift) & 3])
    return bytes(out)


def _planes_record(decoded):
    """DAX_SWEEP 2 / ov30:0491..0516: reconstruct record through bitplanes."""
    if decoded.kind == 'F1':
        return bytes(sum(pixel << (7 - x) for x, pixel in enumerate(row))
                     for frame in decoded.parts[0].frames for row in frame)
    out, key = bytearray(), None
    if decoded.kind == 'A4':
        out.append(len(decoded.parts))
    for part in decoded.parts:
        if decoded.kind == 'A4':
            out += struct.pack('<I', part.delay)
        out += struct.pack('<4HB', part.height, part.width // 8, part.x, part.y, len(part.frames))
        out += part.cga_map
        pixels = b''.join(_plane_bytes(frame, part.width, part.height) for frame in part.frames)
        if key is None:
            key = pixels
        elif decoded.delta:
            assert len(pixels) == len(key)
            pixels = bytes(a ^ b for a, b in zip(pixels, key))
        out += pixels
    return bytes(out)


def _routing():
    """ENGINE_READ_w6 ov30 e4/e7/e9, ov34 e5, ov36 e2; exact file names win."""
    for id in (6, 0x3B, 0x3C, 0x42, 0x45, 0x47, 0x59):
        assert art.source('PIC', id, 2) == 'PIC4'
    for id in (1, 0x11, 0x4D, 0x1B):
        assert art.source('PIC', id, 3) == 'PIC5'
    assert art.source('PIC', 80, 2) == 'PIC2'
    assert art.source('pic2.dax', 6) == 'PIC2'
    assert art.source('SPRIT', 1, 3) == 'SPRIT1'
    assert art.source('CPIC', 1, 3) == 'CPIC1'
    assert art.source('8X8D', 202, 5) == '8X8D1'
    for family in ('BIGPIC', 'HEAD', 'BODY', 'WALLDEF'):
        assert art.source(family, 1, 3) == family + '3'
    assert art.source('SKY', 250, 3) == 'SKY'
    for name in ('../PIC1', 'C:/PIC1', 'PIC1.BIN', ''):
        _reject(art.source, name, 1)
    _reject(art.source, 'PIC', 256)
    _reject(art.source, 'PIC', 1, 0)


def check():
    """UI1 V-check: every shipped picture, byte-exact packed/planar round trips."""
    start = time.perf_counter()
    _synthetic()
    _routing()
    counts, frames, files = Counter(), Counter(), 0
    families = ('8X8D', 'BIGPIC', 'PIC', 'SPRIT', 'CPIC', 'CHEAD', 'CBODY', 'COMSPR', 'DUNGCOM', 'SKY', 'TITLE')
    for path in sorted(Path(ssb_data.SECRET).glob('*.DAX')):
        if not path.stem.startswith(families):
            continue
        files += 1
        for id, raw in dax.load(path.stem, d=ssb_data.SECRET).items():
            label = '%s/%d' % (path.stem, id)
            decoded = art.record(path.stem, id)
            counts[decoded.kind] += 1
            frames[decoded.kind] += sum(len(p.frames) for p in decoded.parts)
            expected = 1 if decoded.kind == 'A4' else 0
            for part in decoded.parts:
                assert all(len(f) == part.height and all(len(r) == part.width for r in f)
                           for f in part.frames), label
                if decoded.kind == 'F1':
                    expected += len(part.frames) * 8
                else:
                    expected += 17 + len(part.frames) * part.height * (part.width // 8) * 4
                    if decoded.kind == 'A4':
                        expected += 4
            assert expected == len(raw), label + ' declared size'
            assert art.encode(decoded) == raw, label + ' packed round trip'
            assert _planes_record(decoded) == raw, label + ' plane round trip'
            w, h, canvases = art.picture(path.stem, id)
            assert len(canvases) == sum(len(p.frames) for p in decoded.parts), label
            assert all(len(f) == h and all(len(r) == w for r in f) for f in canvases), label
            if decoded.kind == 'A4':
                index = 0
                for p in decoded.parts:
                    for frame in p.frames:
                        canvas = canvases[index]
                        assert all(canvas[y + p.y * 8][p.x * 8:p.x * 8 + p.width] == row
                                   for y, row in enumerate(frame)), label + ' placement'
                        index += 1
    assert counts == {'P4': 353, 'A4': 72, 'F1': 1}, counts  # DAX_SWEEP 3: SECRET
    assert art.PALETTE[6] == (170, 85, 0) and len(art.PALETTE) == 16
    font = dax.load(art.FONT_SOURCE, d=ssb_data.SECRET)[201]
    for index in range(len(font) // 8):
        assert art.glyph(index) == font[index * 8:index * 8 + 8]
    for code in range(256):
        upper = code - 32 if 97 <= code <= 122 else code
        assert art.glyph(chr(code)) == art.glyph(upper % 64)
    assert art.glyph(' ') == bytes(8) and any(art.glyph('A'))
    for invalid in ('', 'ab', '\u2603', -1, len(font) // 8):
        _reject(art.glyph, invalid)
    # Startup slots: 202 -> 4, 203 -> 0 (ENGINE_READ_w5 ov13:0646..067D).
    slots = [art.symbols(203), None, None, None, art.symbols(202)]
    assert (len(slots[0]), len(slots[4])) == (45, 101)
    assert art.symbols(202, 5) == slots[4]
    for number in (*range(1, 46), *range(256, 334)):
        tile = art.symbol(number, slots)
        assert len(tile) == 8 and all(len(row) == 8 for row in tile)
    layout = art.wall_layout()
    assert len(layout) == 10 and sum(p.width * p.height for p in layout) == 156
    assert [p.offset for p in layout] == [sum(q.width * q.height for q in layout[:i]) for i in range(10)]
    wall_records, wall_blocks, pieces = 0, 0, 0
    for dataset in (1, 2, 3):
        for id, raw in dax.load('WALLDEF%d' % dataset, d=ssb_data.SECRET).items():
            wall_records += 1
            blocks = art.walls(id, dataset)
            wall_blocks += len(blocks)
            reconstructed = bytearray()
            for block in blocks:
                tiles = art.symbols(block.symbol_set, dataset)
                assert len(tiles) == 70
                for wall_type in range(1, 6):
                    for piece in range(10):
                        grid = art.wall_piece(block, wall_type, piece)
                        assert len(grid) == layout[piece].height
                        assert all(len(row) == layout[piece].width for row in grid)
                        reconstructed.extend(v for row in grid for v in row)
                        pieces += 1
            assert bytes(reconstructed) == raw, 'wall pieces must cover every byte'
            # Every legal placement, including single-block records in slots 2/3.
            for slot in range(1, 5 - len(blocks)):
                moved = art.walls(id, dataset, slot)
                assert [b.slot for b in moved] == list(range(slot, slot + len(blocks)))
                delta = (slot - 1) * 70
                assert tuple(v for b in moved for t in b.types for v in t) == tuple(
                    ((v + delta) & 255) if v >= 45 else v for v in raw)
    assert (wall_records, wall_blocks, pieces) == (10, 19, 950)
    result = dict(files=files, records=sum(counts.values()), formats=dict(counts),
                  picture_frames=frames['P4'] + frames['A4'], glyphs=frames['F1'],
                  wall_records=wall_records, wall_blocks=wall_blocks, wall_pieces=pieces)
    print('art V-check:', result, '| packed/plane round trips exact | %.2fs' % (time.perf_counter() - start))
    return result
