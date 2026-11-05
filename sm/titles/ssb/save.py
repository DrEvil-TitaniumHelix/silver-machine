"""SECRET saves, decode/secret/SAVES.md sections 1-3; ov20:323B..3423.

load(directory, slot) returns a dict: r0/r1/r2 are word lists, pos is five
bytes as ints, walls is three (id, slot) pairs, names is the active filename
list, party contains Rec objects with .items/.effects lists. vault is None or
{header: opaque 28 bytes, items: [Item]}. The unknown vault header is never
inferred from its items. _name_slots preserves all eight Pascal string slots
(including invalid lengths in unused slots); _sidecars preserves empty files.
dump constructs bytes in memory only; it never writes to the source directory.
"""
from pathlib import Path
import struct

from sm.titles.ssb.data import SECRET
from sm.titles.ssb.intake import file_path
from sm.titles.ssb.rec import Rec, Item, Effect

SIZE = 0x155D
# base cell, byte offset, word count: word w is offset + 2 * (w - base).
REGIONS = ((0x4B00, 0x0001, 0x400), (0x7C00, 0x0801, 0x400),
           (0x7A00, 0x1001, 0x200))


def regions(state):
    """Return live word lists indexed by cell minus 4B00/7C00/7A00."""
    return state['r0'], state['r1'], state['r2']


def _slot(slot):
    slot = str(slot).upper()
    if len(slot) != 1 or not 'A' <= slot <= 'Z':
        raise ValueError('save slot must be A..Z')
    return slot


def _stem(name):
    if not name or name in ('.', '..') or any(c in name for c in '/\\:\0'):
        raise ValueError('invalid member filename')
    return name


def _records(raw, cls, filename):
    if raw is None:
        return []
    if len(raw) % cls.SIZE:
        raise ValueError(f'{filename}: partial {cls.__name__} at offset {len(raw) // cls.SIZE * cls.SIZE:#x}')
    return [cls(raw[i:i + cls.SIZE]) for i in range(0, len(raw), cls.SIZE)]


def _load(read, slot):
    """Reader returns bytes or None; also permits in-memory round-trip tests."""
    slot = _slot(slot)
    filename = f'SAVGAM{slot}.DAT'
    raw = read(filename)
    if raw is None:
        raise FileNotFoundError(filename)
    if len(raw) != SIZE:
        raise ValueError(f'{filename}: expected {SIZE} bytes, got {len(raw)}')
    count = raw[0x1414]
    if count > 8:
        raise ValueError(f'{filename}: member count {count} at 0x1414 exceeds 8')
    slots = [raw[i:i + 41] for i in range(0x1415, SIZE, 41)]
    names = []
    for i, entry in enumerate(slots[:count]):
        if entry[0] > 40:
            raise ValueError(f'{filename}: name length at {0x1415 + 41 * i:#x} exceeds 40')
        names.append(_stem(entry[1:1 + entry[0]].decode('latin-1')))
    if len({name.upper() for name in names}) != count:
        raise ValueError(f'{filename}: duplicate member filenames')
    state = dict(slot=slot, dataset=raw[0], pos=list(raw[0x1401:0x1406]),
                 prev_mode=raw[0x1406], mode=raw[0x1407],
                 walls=list(struct.iter_unpack('<HH', raw[0x1408:0x1414])),
                 names=names, party=[], vault=None, _name_slots=slots, _sidecars={})
    for i, (_, off, words) in enumerate(REGIONS):
        state[f'r{i}'] = list(struct.unpack_from(f'<{words}H', raw, off))
    for name in names:
        data = read(name + '.SAV')
        if data is None:
            raise FileNotFoundError(name + '.SAV')
        rec = Rec(data)
        present = []
        for ext, cls, attr in (('STF', Item, 'items'), ('SFX', Effect, 'effects')):
            data = read(name + '.' + ext)
            if data is not None:
                present.append(ext)
            setattr(rec, attr, _records(data, cls, name + '.' + ext))
        state['party'].append(rec)
        state['_sidecars'][name] = present
    vault = read('VAULT.DAT')
    if vault is not None:
        if len(vault) < 28:
            raise ValueError('VAULT.DAT: header shorter than 28 bytes')
        state['vault'] = dict(header=vault[:28], items=_records(vault[28:], Item, 'VAULT.DAT payload'))
    return state


def load(directory=SECRET, slot='A'):
    """Read only. Invoke callers with python -I when using the original files."""
    directory = Path(directory)

    def read(name):
        try: return file_path(directory, name).read_bytes()
        except FileNotFoundError: return None

    return _load(read, slot)

def restore(s, data):
    """Runtime LoadGame ov20:2813 (2B6A..2DDA); leave the byte-preserving codec image untouched."""
    from sm.titles.ssb import rec
    from sm.titles.ssb.state import Char
    s.r0, s.r1, s.r2 = (data[k][:] for k in ('r0', 'r1', 'r2'))
    s.x, s.y, s.dir, s.ahead, s.attr = data['pos']
    s.walls = [w[0] for w in data['walls']]
    s.g['67D6'] = s.r0[0xFC] & 255
    s.g['67EB'], s.g['67ED'] = s.r0[0xFF] // 2, s.r0[0xFF] & 1
    s.r1[0x33E] = 0; s.party = []; s.monsters = []; s.sel = 0; s.party_dead = 0
    for r in data['party']:
        c = Char(bytes(r), [bytes(i) for i in r.items], [bytes(e) for e in r.effects])
        rec.loaded_character(c, s.r1[0x372])
        c.b[0x155] = len(s.party)                                   # ov20:2C7D -> 2676..2778: allocate a fresh icon slot in load order.
        s.party.append(c); s.r1[0x33E] += 1                            # LinkIntoParty ov20:2676
    s.dataset = s.r1[0x312] & 255
    s.prev_mode, s.mode = data['mode'], 0


def sync_globals(s):
    """SaveGame ov20:2FAB, 31F3..3223: mirror engine globals before writing regions (bypass SetDataSet)."""
    s.r0[0xFC] = s.g.get('67D6', 0) & 255
    s.r0[0xFF] = (2 * s.g.get('67EB', 0) + s.g.get('67ED', 0)) & 65535
    s.r1[0x312] = s.dataset & 255

def _packed(records, cls):
    if any(not isinstance(rec, cls) for rec in records):
        raise TypeError(f'expected {cls.__name__} records')
    return b''.join(bytes(rec) for rec in records)


def dump(state):
    """Encode the current fields, retaining stale bytes and optional-file presence."""
    slot = _slot(state['slot'])
    names, party = state['names'], state['party']
    if len(names) != len(party) or len(names) > 8:
        raise ValueError('names and party must have the same length, at most 8')
    if len({name.upper() for name in names}) != len(names):
        raise ValueError('duplicate member filenames')
    raw = bytearray(SIZE)
    raw[0] = state['dataset']
    for values, (_, off, count) in zip(regions(state), REGIONS):
        if len(values) != count:
            raise ValueError(f'region at {off:#x}: expected {count} words')
        struct.pack_into(f'<{count}H', raw, off, *values)
    if len(state['pos']) != 5 or len(state['walls']) != 3:
        raise ValueError('expected five position bytes and three wall pairs')
    raw[0x1401:0x1406] = bytes(state['pos'])
    raw[0x1406], raw[0x1407] = state['prev_mode'], state['mode']
    for i, wall in enumerate(state['walls']):
        struct.pack_into('<HH', raw, 0x1408 + 4 * i, *wall)
    raw[0x1414] = len(party)
    slots = state.get('_name_slots', [bytes(41) for _ in range(8)])
    if len(slots) != 8 or any(len(entry) != 41 for entry in slots):
        raise ValueError('expected eight raw 41-byte name slots')
    raw[0x1415:] = b''.join(slots)
    files = {}
    for i, (name, rec) in enumerate(zip(names, party)):
        encoded = _stem(name).encode('latin-1')
        if len(encoded) > 40:
            raise ValueError('member filename exceeds 40 bytes')
        off = 0x1415 + 41 * i
        raw[off:off + 1 + len(encoded)] = bytes([len(encoded)]) + encoded
        files[name + '.SAV'] = _packed([rec], Rec)
        present = state.get('_sidecars', {}).get(name, ())
        for ext, cls, records in (('STF', Item, rec.items), ('SFX', Effect, rec.effects)):
            if records or ext in present:
                files[name + '.' + ext] = _packed(records, cls)
    files[f'SAVGAM{slot}.DAT'] = bytes(raw)
    if state.get('vault') is not None:
        vault = state['vault']
        if len(vault['header']) != 28:
            raise ValueError('VAULT.DAT: expected 28-byte opaque header')
        files['VAULT.DAT'] = bytes(vault['header']) + _packed(vault['items'], Item)
    return files


def _equal(actual, expected):
    assert actual.keys() == expected.keys(), ('file set', sorted(actual.keys() ^ expected.keys()))
    for name, raw in expected.items():
        other = actual[name]
        if raw != other:
            off = next((i for i, (a, b) in enumerate(zip(raw, other)) if a != b), min(len(raw), len(other)))
            raise AssertionError(f'{name}: first mismatch at {off:#x}, lengths {len(other)}/{len(raw)}')


def test_save_globals():
    """SaveGame ov20:31F3..3223 writes globals into the live cells before serialization in both save paths."""
    from sm.titles.ssb.host import Game
    from sm.titles.ssb.units import creation
    from sm.titles.ssb.ui import slots
    for snapshot in (creation.snapshot, slots.snapshot):
        g = Game(lambda *a, **k: 0); s = g.s
        s.g['67D6'], s.g['67EB'], s.g['67ED'], s.dataset = 7, 1, 0, 3
        s.r0[0xFC] = s.r0[0xFF] = s.r1[0x312] = 99
        files = dict(snapshot(g, 'T')); d = _load(files.get, 'T')
        assert (s.r0[0xFC], s.r0[0xFF], s.r1[0x312]) == (7, 2, 3), 'live SaveGame cells'
        assert (d['r0'][0xFC], d['r0'][0xFF], d['r1'][0x312], d['dataset']) == (7, 2, 3, 3), 'saved cells'

def test():
    """V1: every A/B file, then 200 seeded mutations per slot, all in memory."""
    test_save_globals()
    import random
    rng, counts = random.Random(0x155D), {}
    directory = Path(SECRET)
    for slot in 'AB':
        expected = {p.name: p.read_bytes() for p in directory.iterdir()
                    if p.name in (f'SAVGAM{slot}.DAT', 'VAULT.DAT') or
                    (p.name.startswith('CHRDAT' + slot) and p.suffix in ('.SAV', '.STF', '.SFX'))}
        state = load(directory, slot)
        _equal(dump(state), expected)
        counts[slot] = len(expected)
        # Check the published cell formula independently of encoder/decoder agreement.
        raw = expected[f'SAVGAM{slot}.DAT']
        for i, (base, off, words) in enumerate(REGIONS):
            values = regions(state)[i]
            assert isinstance(values, list) and len(values) == words
            for cell in range(base, base + words):
                start = off + 2 * (cell - base)
                assert values[cell - base] == int.from_bytes(raw[start:start + 2], 'little'), (slot, cell)
        for case in range(200):
            state = _load(expected.get, slot)
            kind = case % 10
            if kind < 3:
                _, off, words = REGIONS[kind]
                index = rng.choice((0, words - 1, rng.randrange(words)))
                value = rng.randrange(65536)
                regions(state)[kind][index] = value
                changed = dump(state)[f'SAVGAM{slot}.DAT']
                start = off + 2 * index
                assert changed == raw[:start] + value.to_bytes(2, 'little') + raw[start + 2:]
            elif kind == 3:
                for key in ('dataset', 'prev_mode', 'mode'):
                    state[key] = rng.randrange(256)
                state['pos'] = list(rng.randbytes(5))
                state['walls'] = [(rng.randrange(65536), rng.randrange(65536)) for _ in range(3)]
            elif kind == 4:
                rec = rng.choice(state['party'])
                field = rng.choice(list(Rec.FIELDS))
                value = rng.randbytes(Rec.FIELDS[field][1])
                rec.set(field, value if isinstance(rec.get(field), bytes) else int.from_bytes(value, 'little'))
            elif kind == 5:
                rec = rng.choice(state['party'])
                rec.items = [Item(rng.randbytes(Item.SIZE)) for _ in range(rng.randrange(4))]
                rec.effects = [Effect(rng.randbytes(Effect.SIZE)) for _ in range(rng.randrange(4))]
            elif kind == 6:
                state['vault'] = dict(header=rng.randbytes(28), items=[Item(rng.randbytes(67))])
            elif kind == 7:
                state['names'][0] = 'TEST' + str(case)
            elif kind == 8:
                count = rng.randrange(7)
                state['names'], state['party'] = state['names'][:count], state['party'][:count]
                state['vault'] = None
            else:
                state['names'] += ['TEST7', 'TEST8']
                state['party'] += [Rec(rng.randbytes(439)), Rec(rng.randbytes(439))]
            encoded = dump(state)
            _equal(dump(_load(encoded.get, slot)), encoded)
        # An empty sidecar is distinct from an absent sidecar.
        empty = dict(expected)
        name = state['names'][0] if state['names'][0].startswith('CHRDAT') else f'CHRDAT{slot}1'
        empty[name + '.STF'] = empty[name + '.SFX'] = b''
        _equal(dump(_load(empty.get, slot)), empty)
        for filename, data in ((f'SAVGAM{slot}.DAT', raw[:-1]),
                               (f'CHRDAT{slot}1.SAV', bytes(438)),
                               (f'CHRDAT{slot}1.STF', bytes(66)),
                               (f'CHRDAT{slot}1.SFX', bytes(8)), ('VAULT.DAT', bytes(27)),
                               ('VAULT.DAT', bytes(29))):
            malformed = dict(expected, **{filename: data})
            try: _load(malformed.get, slot)
            except ValueError: pass
            else: raise AssertionError((filename, 'accepted malformed size'))
    print(f"V1: A {counts['A']} files, B {counts['B']} files byte-identical")
    return counts
