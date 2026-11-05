"""VGA TILE operations and palette slices (PICTURES sections 2-4).

Pixels are indices, not RGB. Each operation computes (destination & keep) XOR
pixels, preserving partial masks and opaque zeroes in sprite runs. Only the
VGA data set is supported; bounds also limit corrupt dimensions/composites.
"""
from dataclasses import dataclass
import struct
from .hlib import DecodeError, Reader

MAX_PIXELS = 1 << 20
COMPOSITE_PIXELS = 8 << 20


def _rle(r, count):
    result = bytearray()
    while len(result) < count:
        control = r.byte()
        if control == 128:
            continue
        length = control + 1 if control < 128 else 257 - control
        if length > count - len(result):
            raise DecodeError('RLE run crosses output boundary')
        result.extend(r.take(length) if control < 128 else bytes([r.byte()]) * length)
    return bytes(result)


def decode_rle(data, count):
    """Decode exactly count bytes; return output and consumed source length."""
    if not 0 <= count <= MAX_PIXELS:
        raise DecodeError('RLE output exceeds limit')
    reader = Reader(data)
    return _rle(reader, count), reader.pos


def _interleave(planes):
    result = bytearray(len(planes))
    size = len(planes) // 4
    for plane in range(4):
        result[plane::4] = planes[plane * size:(plane + 1) * size]
    return bytes(result)


@dataclass(frozen=True)
class Picture:
    w: int
    h: int
    pixels: bytes
    keep: bytes
    dx: int = 0
    dy: int = 0
    flags: int = 0
    used: int = 0
    tail: bytes = b''

    def render(self, background=0):
        if isinstance(background, int):
            background = bytes([background]) * (self.w * self.h)
        if len(background) != len(self.pixels):
            raise ValueError('background dimensions differ')
        return bytes((old & mask) ^ value for old, mask, value in zip(background, self.keep, self.pixels))

    def draw(self, canvas, width, height, x=0, y=0):
        if width < 0 or height < 0 or len(canvas) != width * height:
            raise ValueError('canvas dimensions differ')
        left, top = x - self.dx, y - self.dy
        for row in range(max(0, -top), min(self.h, height - top)):
            for col in range(max(0, -left), min(self.w, width - left)):
                source, dest = row * self.w + col, (row + top) * width + col + left
                canvas[dest] = (canvas[dest] & self.keep[source]) ^ self.pixels[source]
        return canvas


@dataclass(frozen=True)
class Palette:
    flags: int
    first: int
    rgb: tuple
    ranges: tuple
    trailer: bytes
    padding: bytes
    header: bytes

    def to_bytes(self):
        return (self.header + bytes(c for colour in self.rgb for c in colour) +
                bytes(c for cycle in self.ranges for c in cycle) + self.trailer + self.padding)

    def apply(self, colours, *, dac=False):
        """Return an updated 256-colour table; DAC values use six-bit channels."""
        if len(colours) != 256:
            raise ValueError('palette table must have 256 entries')
        updated = list(colours)
        updated[self.first:self.first + len(self.rgb)] = [tuple(c >> 2 if dac else c for c in rgb) for rgb in self.rgb]
        return updated


def palette(data):
    r = Reader(data)
    header = r.take(8)
    flags, first, count, extra, kind = struct.unpack('<HHHBB', header)
    if kind & 15 != 8:
        raise DecodeError('expected palette leaf')
    if not flags & 1:
        first, count = 0, 256
    if not flags & 2:
        extra = 0
    if first + count > 256:
        raise DecodeError('palette slice exceeds 256 colours')
    rgb = tuple(r.unpack('3B') for _ in range(count))
    ranges = tuple(r.unpack('4B') for _ in range(extra))
    trailer = r.take((count + 1) // 2)
    if r.left > 1:
        raise DecodeError('palette has excess data')
    return Palette(flags, first, rgb, ranges, trailer, r.take(r.left), header)


def decode(data, resolve=None):
    """Decode a VGA picture; resolve(entry) returns bytes from the same group.

    Cycles fail before recursion, repeated siblings are cached, and each call
    has an aggregate pixel budget. Stream loops always consume an input byte.
    """
    return _decode(data, resolve, (), {}, [COMPOSITE_PIXELS])


def _decode(data, resolve, active, cache, budget):
    r = Reader(data)
    h, dy, dx, quarter, flags = r.unpack('<HhhBB')
    width, kind = quarter * 4, flags & 15
    size = width * h
    if not size or size > MAX_PIXELS or len(active) > 32 or size > budget[0]:
        raise DecodeError('invalid TILE dimensions or composite budget exceeded')
    budget[0] -= size
    if kind in (0, 1, 5):
        keep = _interleave(r.take(size)) if kind == 1 else bytes(size)
        pixels = _interleave(r.take(size))
        if kind == 5:
            keep = bytes(255 if value == 255 else 0 for value in pixels)
            pixels = pixels.replace(b'\xff', b'\0')
    elif kind == 2:
        # Each encoded row holds all four planes, unlike raw plane-major data.
        pixels = b''.join(_interleave(_rle(r, width)) for _ in range(h))
        keep = bytes(size)
    elif kind == 7:
        raw, mask = bytearray(size), bytearray(b'\xff') * size
        for plane in range(4):
            for row in range(h):
                column = 0
                while True:
                    command = r.byte()
                    if command == 0:
                        break
                    run = command if command < 128 else 256 - command
                    if column + run > quarter:
                        raise DecodeError('sprite run crosses row')
                    if command < 128:
                        start = (plane * h + row) * quarter + column
                        raw[start:start + run] = r.take(run)
                        mask[start:start + run] = bytes(run)
                    column += run
        pixels, keep = _interleave(raw), _interleave(mask)
    elif kind == 9:
        if resolve is None:
            raise DecodeError('composite needs sibling resolver')
        operations = []
        first = r.unpack('<BBhh')
        count = first[1]
        if not count:
            raise DecodeError('empty composite')
        operations.append(first)
        operations.extend(r.unpack('<BBhh') for _ in range(count - 1))
        pixels, keep = bytearray(size), bytearray(b'\xff') * size
        for entry, repeated_count, row, col in operations:
            if repeated_count != count or entry in active:
                raise DecodeError('inconsistent or cyclic composite')
            if entry not in cache:
                try:
                    child_data = resolve(entry)
                except (KeyError, IndexError) as exc:
                    raise DecodeError('missing composite sibling') from exc
                cache[entry] = _decode(child_data, resolve, active + (entry,), cache, budget)
            child = cache[entry]
            child.draw(pixels, width, h, col, row)
            left, top = col - child.dx, row - child.dy
            for y in range(max(0, -top), min(child.h, h - top)):
                for x in range(max(0, -left), min(child.w, width - left)):
                    keep[(top + y) * width + left + x] &= child.keep[y * child.w + x]
    else:
        raise DecodeError(f'unsupported VGA TILE kind {kind}')
    used = r.pos
    if r.left > 1:
        raise DecodeError('TILE has excess data')
    return Picture(width, h, bytes(pixels), bytes(keep), dx, dy, flags, used, r.take(r.left))


def decode_path(library, path):
    parts = tuple(int(p) for p in path.split('/')) if isinstance(path, str) else tuple(path)
    leaf = library.at(parts)
    if leaf.tag != 'TILE':
        raise DecodeError('expected TILE leaf')
    group = library.at(parts[:-1])
    return decode(leaf.data, lambda entry: group.entries[entry].data)


