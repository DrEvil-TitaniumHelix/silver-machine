from dataclasses import dataclass
import struct


class DecodeError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = memoryview(data).cast('B')
        self.pos = 0

    @property
    def left(self):
        return len(self.data) - self.pos

    def take(self, size):
        if size < 0 or size > self.left:
            raise DecodeError(f'truncated field at {self.pos}: needs {size}, has {self.left}')
        start = self.pos
        self.pos += size
        return bytes(self.data[start:self.pos])

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def byte(self):
        if not self.left:
            raise DecodeError(f'truncated control at {self.pos}')
        value = self.data[self.pos]
        self.pos += 1
        return value


@dataclass(frozen=True)
class Leaf:
    tag: str
    offset: int
    data: bytes


class Library:
    def __init__(self, data, *, _offset=0, _depth=0):
        if _depth > 32:
            raise DecodeError('HLIB nesting exceeds 32')
        r = Reader(data)
        magic, size, count, reserved, indexed, tag = r.unpack('<4sIHBB4s')
        if magic != b'HLIB' or size != len(data) or reserved != 0 or indexed not in (0, 1):
            raise DecodeError('invalid HLIB header or extent')
        if tag not in (b'HLIB', b'TILE', b'DATA', b'DIG4'):
            raise DecodeError('unsupported HLIB leaf tag')
        self.tag, self.offset, self.size = tag.decode('ascii'), _offset, size
        offsets = r.unpack(f'<{count + 1}I')
        if offsets[0] != r.pos or offsets[-1] != size:
            raise DecodeError('HLIB directory extent mismatch')
        if any(a > b for a, b in zip(offsets, offsets[1:])):
            raise DecodeError('HLIB offsets are not ordered')
        self.ids, self.entries, self.index = {}, {}, []
        if indexed:
            if not count:
                raise DecodeError('missing HLIB index entry')
            index = Reader(data[offsets[0]:offsets[1]])
            pairs, = index.unpack('<H')
            for _ in range(pairs):
                ident, entry = index.unpack('<HH')
                if not 1 <= entry < count:
                    raise DecodeError('invalid HLIB index target')
                self.index.append((ident, entry))
                self.ids.setdefault(ident, entry)
            if index.left:
                raise DecodeError('HLIB index has trailing bytes')
        self.directory_size = offsets[indexed]
        for entry in range(indexed, count):
            start, end = offsets[entry:entry + 2]
            payload = bytes(data[start:end])
            absolute = _offset + start
            self.entries[entry] = (Library(payload, _offset=absolute, _depth=_depth + 1)
                                   if self.tag == 'HLIB' else Leaf(self.tag, absolute, payload))

    def by_id(self, ident, occurrence=0):
        matches = [entry for key, entry in self.index if key == ident]
        if not 0 <= occurrence < len(matches):
            raise KeyError(ident)
        return self.entries[matches[occurrence]]

    def at(self, path):
        node = self
        parts = tuple(int(p) for p in path.split('/')) if isinstance(path, str) else tuple(path)
        for part in parts:
            if not isinstance(node, Library):
                raise KeyError(path)
            node = node.entries[part]
        return node

    def leaves(self, prefix=()):
        for entry, node in self.entries.items():
            path = prefix + (entry,)
            if isinstance(node, Library):
                yield from node.leaves(path)
            else:
                yield path, node


