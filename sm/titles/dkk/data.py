import hashlib
import json
import struct
from collections.abc import Mapping
from pathlib import Path
from sm import dax
from sm.files import DataError, file_path
from sm.titles.cok.data import Assets as FamilyAssets
from .intake import require_folder
from .faults import BindingRequired


def decode_block(raw, start, size):
    if size == 0 or not 0 <= start < len(raw):
        raise BindingRequired('Archive block requires unspecified buffer or file state')
    result = bytearray()
    cursor = start
    while len(result) < size:
        if cursor >= len(raw): raise BindingRequired('Archive block ends before its decoded length')
        control = raw[cursor]
        cursor += 1
        if control in (127, 128): continue
        count = control + 1 if control < 127 else 256 - control
        consumed = count if control < 127 else 1
        if cursor + consumed > len(raw): raise BindingRequired('Incomplete archive run has unspecified bytes')
        if len(result) + count > size: raise BindingRequired('Archive run exceeds its allocated buffer')
        result.extend(raw[cursor:cursor + consumed] if control < 127 else raw[cursor:cursor + 1] * count)
        cursor += consumed
    return bytes(result)


class ArchiveRecords(Mapping):
    def __init__(self, raw):
        self.raw = bytes(raw)
        if len(self.raw) < 2: raise BindingRequired('Incomplete archive directory length')
        length = int.from_bytes(self.raw[:2], 'little')
        self.base = length + 2 & 65535

    def _entries(self):
        for cursor in range(2, max(3, self.base), 9):
            if cursor + 7 > len(self.raw):
                raise BindingRequired('Incomplete archive directory has unspecified fields')
            yield struct.unpack_from('<BiH', self.raw, cursor)

    def __getitem__(self, ident):
        for entry, offset, size in self._entries():
            if entry == ident:
                return decode_block(self.raw, self.base + offset, size)
        raise KeyError(ident)

    def __iter__(self):
        seen = set()
        for ident, offset, size in self._entries():
            if ident not in seen:
                seen.add(ident)
                yield ident

    def __len__(self):
        return sum(1 for ident in self)

    def __contains__(self, ident):
        return any(entry == ident for entry, offset, size in self._entries())


def archive_records(raw):
    return ArchiveRecords(raw)


class Assets(FamilyAssets):
    def __init__(self, directory=None):
        self.root = require_folder(directory)
        self.layout = json.loads(Path(__file__).with_name('tables.json').read_text(encoding='utf-8'))
        self.resident = dax.unpack_exepack(file_path(self.root, 'START.EXE').read_bytes())
        if len(self.resident) != self.layout['resident_bytes'] or hashlib.sha256(self.resident).hexdigest() != self.layout['resident_sha256']:
            raise DataError('Death Knights resident image differs from the verified layout')

    def records(self, name):
        return archive_records(file_path(self.root, name + '.DAX').read_bytes())

    def part(self, name):
        row = self.layout['tables'][name]
        raw = self.resident[row['offset']:row['offset'] + row['size']]
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise DataError('Death Knights table differs: ' + name)
        return raw

    def text(self, name):
        raw = self.part(name)
        return raw[1:1 + raw[0]].decode('cp437')

    def names(self, name):
        row = self.layout['tables'][name]
        width = row['shape'][-1]
        raw = self.part(name)
        return tuple(raw[i + 1:i + 1 + raw[i]].decode('cp437') for i in range(0, len(raw), width))

    def item_templates(self):
        from .faults import BindingRequired
        raw = self.records('ITEM0').get(1, b'')[:127 * 17]
        if not raw: raise BindingRequired('Missing item templates require the native error pause and exit')
        if len(raw) % 17: raise BindingRequired('Partial item template has unspecified bytes beyond its archive record')
        loaded = tuple(raw[i:i + 17] for i in range(0, len(raw), 17))
        return loaded + (bytes([255]) * 17,) * (254 - len(loaded))


def test():
    assets = Assets()
    for name in assets.layout['tables']:
        assets.part(name)
    assert len(assets.scripts()) == 25
    assert {len(raw) for raw in assets.records('MON1CHA').values()} == {216}
    assert {len(raw) for raw in assets.records('MON1WIZ').values()} == {220}
    assert all(len(raw) == 1026 for disk in (1, 2, 3) for raw in assets.records('GEO%d' % disk).values())
    assert len(assets.item_templates()) == 254
    from types import SimpleNamespace
    from .faults import BindingRequired
    fake = SimpleNamespace(records=lambda name: {1: bytes(17 * 129)})
    templates = Assets.item_templates(fake)
    assert templates[126] == bytes(17) and templates[127] == templates[-1] == bytes([255]) * 17
    for raw in (b'', bytes(16)):
        fake.records = lambda name: {1: raw}
        try: Assets.item_templates(fake)
        except BindingRequired: pass
        else: raise AssertionError('invalid item templates accepted')
    raw = struct.pack('<H', 27) + b''.join(struct.pack('<BiHH', *entry) for entry in
          ((7, 0, 3, 1), (7, 9999, 3, 1), (8, 7, 1, 65535))) + b'\x7f\x80\x00A\xfeB\x7f\x00C'
    assert archive_records(raw) == {7: b'ABB', 8: b'C'}
    for invalid in ((9, 9999, 1, 1), (9, 2, 3, 1), (9, 0, 0, 1)):
        for entries in ((invalid, (7, 0, 1, 2)), ((7, 0, 1, 2), invalid)):
            raw = struct.pack('<H', 18) + b''.join(struct.pack('<BiHH', *entry) for entry in entries) + b'\x00A\x02B'
            records = archive_records(raw)
            assert len(records) == 2 and tuple(records) == tuple(entry[0] for entry in entries)
            assert 9 in records and 8 not in records and records.get(8, b'absent') == b'absent'
            assert records[7] == b'A'
            try: records[9]
            except BindingRequired: pass
            else: raise AssertionError('undefined requested archive block accepted')
            assert records[7] == b'A'
    for length in (0, 1, 8, 9, 65534, 65535):
        base = length + 2 & 65535
        raw = struct.pack('<HBiHH', length, 7, 11 - base, 1, 2) + b'\x00A'
        records = archive_records(raw)
        assert records[7] == b'A' and 7 in records and tuple(records) == (7,)
        assert len(records) == 1 and 8 not in records and records.get(8) is None
    raw = struct.pack('<HBiHH', 10, 7, 8, 1, 2) + struct.pack('<BiHH', 8, 10, 1, 2) + b'\x00A\x00B'
    assert archive_records(raw) == {7: b'A', 8: b'B'}
    raw = struct.pack('<HBiHH', 10, 7, 0, 1, 2) + b'\xff\x00A'
    records = archive_records(raw)
    assert records[7] == b'A' and 7 in records and next(iter(records)) == 7
    for action in (lambda: records[8], lambda: 8 in records, lambda: len(records), lambda: tuple(records)):
        try: action()
        except BindingRequired: pass
        else: raise AssertionError('undefined directory fields accepted')
    raw = struct.pack('<HBiHH', 18, 7, -9, 1, 2) + b'\x00A'
    assert archive_records(raw)[7] == b'A'
    for tail in (b'', b'\xff'):
        records = archive_records(struct.pack('<HBiH', 0, 7, -2, 1) + tail)
        assert records[7] == b'\x00' and records.get(8) is None and tuple(records) == (7,)
    assert decode_block(b'\x00A\x00B', 0, 1) == b'A'
    for raw, size in ((b'\x7f\x80', 1), (b'\x02A', 3), (b'\xfeA', 1), (b'\x00A', 0)):
        try: decode_block(raw, 0, size)
        except BindingRequired: pass
        else: raise AssertionError('undefined archive bytes accepted')
