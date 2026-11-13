

class Record:
    BLOCKS = frozenset()

    def __init__(self, data=None):
        if data is None:
            data = bytes(self.SIZE)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError('record data must be bytes-like')
        if len(data) != self.SIZE:
            raise ValueError(f'{type(self).__name__}: expected {self.SIZE} bytes, got {len(data)}')
        self.data = bytearray(data)

    def get(self, name, *, signed=False):
        off, size = self.FIELDS[name]
        raw = self.data[off:off + size]
        if name in self.BLOCKS or size not in (1, 2, 4):
            return bytes(raw)
        return int.from_bytes(raw, 'little', signed=signed)

    def set(self, name, value, *, signed=False):
        off, size = self.FIELDS[name]
        if name in self.BLOCKS or size not in (1, 2, 4):
            if not isinstance(value, (bytes, bytearray, memoryview)):
                raise TypeError(f'{name}: expected {size} bytes')
            raw = bytes(value)
        else:
            raw = value.to_bytes(size, 'little', signed=signed)
        if len(raw) != size:
            raise ValueError(f'{name}: expected {size} bytes, got {len(raw)}')
        self.data[off:off + size] = raw

    def __bytes__(self):
        if len(self.data) != self.SIZE:
            raise ValueError(f'{type(self).__name__}: backing array was resized')
        return bytes(self.data)
