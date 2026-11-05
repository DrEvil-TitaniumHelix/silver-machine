"""Pascal-family P4/A4/F1 EGA decode/encode; no title assets or file access."""
import struct
from typing import NamedTuple

PALETTE = ((0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
           (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
           (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
           (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255))
_NIBBLES = tuple(bytes((b >> 4, b & 15)) for b in range(256))
_BITS = tuple(bytes((b >> s) & 1 for s in range(7, -1, -1)) for b in range(256))


class Part(NamedTuple):
    """One P4 header + frames, or the headerless F1 glyph set; DAX_SWEEP 2."""
    width: int
    height: int
    x: int
    y: int
    cga_map: bytes
    frames: tuple
    delay: int | None = None


class Record(NamedTuple):
    """P4, A4 or F1; A4's PIC/FINAL delta flag is external (ov30:00EC)."""
    kind: str
    parts: tuple
    delta: bool = False


def _part(data, offset, delay=None):
    """DAX_SWEEP.md 2, P4: 17 + n*h*w8*4 bytes, high nibble first."""
    if offset < 0 or offset + 17 > len(data):
        raise ValueError('truncated P4 header')
    h, w8, x, y, n = struct.unpack_from('<4HB', data, offset)
    end = offset + 17 + n * h * w8 * 4
    if not h or not w8 or not n or end > len(data):
        raise ValueError('invalid P4 dimensions/count or truncated pixels')
    stride, cursor, frames = w8 * 4, offset + 17, []
    for _ in range(n):
        rows = tuple(b''.join(_NIBBLES[b] for b in data[p:p + stride])
                     for p in range(cursor, cursor + h * stride, stride))
        frames.append(rows)
        cursor += h * stride
    return Part(w8 * 8, h, x, y, bytes(data[offset + 9:offset + 17]),
                tuple(frames), delay), end


def _xor(part, key):
    """ENGINE_READ_w6.md ov30:0491..0516: each delta XORs the first image."""
    if (part.width, part.height, len(part.frames)) != (key.width, key.height, len(key.frames)):
        raise ValueError('A4 delta dimensions differ from the key frame')
    return part._replace(frames=tuple(tuple(bytes(a ^ b for a, b in zip(row, base))
                         for row, base in zip(frame, first))
                         for frame, first in zip(part.frames, key.frames)))


def decode(data, *, kind=None, delta=False):
    """DAX_SWEEP.md 2 (P4/A4/F1); ov30:00EC (PIC/FINAL XOR, SPRIT independent).

    F1 has no signature: select kind='F1' explicitly. Other inputs must consume
    the entire record. No truncated data, trailing bytes or guessed formats.
    """
    if kind == 'F1':
        if not data or len(data) % 8:
            raise ValueError('F1 must contain whole 8-byte glyphs')
        frames = tuple(tuple(_BITS[b] for b in data[i:i + 8]) for i in range(0, len(data), 8))
        return Record('F1', (Part(8, 8, 0, 0, b'', frames),))
    if kind not in (None, 'P4', 'A4'):
        raise ValueError('unknown picture format')
    if kind != 'A4':
        try:
            part, end = _part(data, 0)
            if end == len(data):
                return Record('P4', (part,))
        except ValueError:
            pass
        if kind == 'P4':
            raise ValueError('P4 size does not match its header')
    if not data or not 1 <= data[0] <= 8:
        raise ValueError('invalid A4 frame count (ov30 limit: 8)')
    parts, cursor = [], 1
    for _ in range(data[0]):
        if cursor + 4 > len(data):
            raise ValueError('truncated A4 delay')
        delay, = struct.unpack_from('<I', data, cursor)
        part, cursor = _part(data, cursor + 4, delay)
        if delta and parts:
            part = _xor(part, parts[0])
        parts.append(part)
    if cursor != len(data):
        raise ValueError('trailing A4 data')
    return Record('A4', tuple(parts), delta)


def _pack(rows, width, height, bits=4):
    """Inverse of DAX_SWEEP.md 2 / daxpic.py font_frames: packed nibbles or bits."""
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError('pixel dimensions do not match header')
    if bits not in (1, 4) or width % (8 // bits):
        raise ValueError('pixel width is not byte aligned')
    if any(not isinstance(c, int) or not 0 <= c < (1 << bits) for row in rows for c in row):
        raise ValueError('pixel index out of range')
    step = 8 // bits
    return bytes(sum(row[x + i] << (8 - bits * (i + 1)) for i in range(step))
                 for row in rows for x in range(0, width, step))


def _encode_part(part):
    """DAX_SWEEP.md 2: preserve all 17 header bytes, then every packed frame."""
    if (not 0 < part.width <= 65535 * 8 or part.width % 8 or not 0 < part.height <= 65535
            or not 0 < len(part.frames) <= 255 or len(part.cga_map) != 8):
        raise ValueError('invalid P4 header')
    return (struct.pack('<4HB', part.height, part.width // 8, part.x, part.y, len(part.frames))
            + part.cga_map + b''.join(_pack(f, part.width, part.height) for f in part.frames))


def encode(decoded):
    """DAX_SWEEP.md 2 and ov30:0491..0516, inverse codec for the V-check."""
    if decoded.kind == 'F1':
        return b''.join(_pack(f, 8, 8, 1) for f in decoded.parts[0].frames)
    if decoded.kind == 'P4' and len(decoded.parts) == 1:
        return _encode_part(decoded.parts[0])
    if decoded.kind != 'A4' or not 1 <= len(decoded.parts) <= 8:
        raise ValueError('invalid picture record')
    out = bytearray((len(decoded.parts),))
    for i, part in enumerate(decoded.parts):
        if decoded.delta and i:
            part = _xor(part, decoded.parts[0])
        out += struct.pack('<I', part.delay) + _encode_part(part)
    return bytes(out)
