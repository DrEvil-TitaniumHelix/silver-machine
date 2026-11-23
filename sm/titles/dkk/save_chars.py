from sm.files import file_index
from sm.titles.cok.records import Character as ImportedCharacter
from .records import Character, Spells, Item, Effect, split_records
from .faults import BindingRequired


def whole(raw, kind):
    return split_records(raw[:len(raw) // kind.SIZE * kind.SIZE], kind)


def padded(raw, kind):
    return kind(raw[:kind.SIZE].ljust(kind.SIZE, b'\0'))


def party_stems(game):
    return tuple(iter_party_stems(game))


def iter_party_stems(game):
    from sm.titles.cok.creation import file_stem
    count, names = game.get('party_count'), game.get('party_names')
    if count > 8:
        raise BindingRequired('Party count exceeds the stored filename array')
    for index in range(count):
        entry = names[index * 41:(index + 1) * 41]
        if entry[0] > 40:
            raise BindingRequired('Member filename extends beyond its stored slot')
        yield file_stem(entry[1:1 + entry[0]].decode('latin1'))


def read_native(index, stem, extension='GAM'):
    path = index.get((stem + '.' + extension).upper())
    if path is None: return None
    result = {'GAM': (padded(path.read_bytes(), Character),)}
    for suffix, kind in (('WIZ', Spells), ('JNK', Item), ('EFF', Effect)):
        path = index.get((stem + '.' + suffix).upper())
        if path is None: continue
        raw = path.read_bytes()
        if kind is Spells:
            if len(raw) < Spells.SIZE:
                raise BindingRequired('Short spell block requires the original error pause and unread heap bytes')
            result[suffix] = (Spells(raw[:Spells.SIZE]),)
        else:
            result[suffix] = whole(raw, kind)
    return result


def detach(files, monster=False):
    result = {suffix: tuple(type(record)(bytes(record)) for record in records) for suffix, records in files.items()}
    record = result['GAM'][0]
    for name in ('items_pointer', 'effects_pointer', 'combat_pointer', 'next_pointer'):
        record.set(name, 0)
    if monster: record.set('spells_pointer', 0)
    for suffix in ('JNK', 'EFF'):
        for entry in result.get(suffix, ()): entry.set('next_pointer', 0)
    return result


def materialize(files, game=None):
    from . import rules
    from .save_start import item_pool
    files = detach(files)
    char = rules.character(bytes(files['GAM'][0]),
                           effects=[bytes(record) for record in files.get('EFF', ())],
                           spells=bytes(files['WIZ'][0]) if files.get('WIZ') else None)
    items = files.get('JNK', ())
    if game is None:
        char.items = [bytearray(bytes(record)) for record in items]
        return char
    pool = item_pool(game)
    for record in items:
        slot = pool.allocate()
        if slot is None:
            for allocated in char.items:
                pool.release(allocated)
            raise BindingRequired('Loaded character exceeds the available party item slots')
        slot[:] = bytes(record)
        char.items.append(slot)
    return char


def import_character(raw, items=b'', effects=b''):
    old, new = padded(raw, ImportedCharacter), Character()
    excluded = {'money', 'npc', 'items_pointer', 'effects_pointer', 'combat_pointer', 'next_pointer'}
    for name, (offset, size) in Character.FIELDS.items():
        previous = ImportedCharacter.FIELDS.get(name)
        if previous is not None and name not in excluded and previous[1] == size:
            start = previous[0]
            new.data[offset:offset + size] = old.data[start:start + size]
    new.set('cure_ability', old.get('knight_bracket'))
    new.set('hp_roll_needed', old.get('xp_per_hp'))
    new.set('money', old.get('money')[8:14])
    age, race = new.get('age'), new.get('race')
    limits = {0: 1200, 1: 1200, 2: 200, 3: 300, 4: 300, 6: 50}
    if race in limits: new.set('age', min(age, limits[race]))
    elif race == 5 and age > 199: new.set('age', 70)
    result = {'GAM': (new,),
              'JNK': tuple(item for item in whole(items, Item) if item.get('type') not in (42, 47, 58, 60, 63, 69, 72)),
              'EFF': whole(effects, Effect)}
    if new.get('class') not in (2, 6, 14):
        book = Spells()
        book.set('memorized', old.get('memorized').ljust(74, b'\0'))
        book.set('known_spells', old.get('known_spells').ljust(114, b'\0'))
        slots = old.get('spell_slots')
        book.set('spell_slots', b''.join(slots[row * 5:row * 5 + 5] + b'\0' * 3 for row in range(4)))
        result['WIZ'] = (book,)
    return detach(result)


def read_imported(index, stem, extension='SAV'):
    path = index.get((stem + '.' + extension).upper())
    if path is None: return None
    side = lambda suffix: index[(stem + '.' + suffix).upper()].read_bytes() if (stem + '.' + suffix).upper() in index else b''
    return import_character(path.read_bytes(), side('STF'), side('SFX'))


def padded_name(raw):
    return bytes(raw[1:1 + min(raw[0], 15)]).ljust(15, b' ')


def roster(directory, party=(), imported=False):
    kind, suffix = (ImportedCharacter, '.WHO') if imported else (Character, '.PC')
    held = {padded_name(char.b if hasattr(char, 'b') else bytes(char)) for char in party}
    result = []
    for name, path in sorted(file_index(directory).items(), key=lambda entry: entry[1].name):
        if not name.endswith(suffix): continue
        raw = path.read_bytes()
        if len(raw) == kind.SIZE and raw[kind.FIELDS['npc'][0]] < 128 and padded_name(raw) not in held:
            result.append(path)
    return tuple(result)


def file_size(files, include_spells=True):
    return sum(len(records) * kind.SIZE for suffix, kind in
               (('GAM', Character), ('WIZ', Spells), ('JNK', Item), ('EFF', Effect))
               if include_spells or suffix != 'WIZ' for records in (files.get(suffix, ()),)) & 65535


def test():
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace
    from unittest.mock import patch
    with TemporaryDirectory(prefix='sm-dkk-files-') as folder:
        root = Path(folder)
        (root / 'HERO.GAM').write_bytes(b'\x03ABC')
        (root / 'HERO.JNK').write_bytes(bytes(Item()) + b'x')
        (root / 'HERO.EFF').write_bytes(bytes(Effect()) + b'x')
        (root / 'HERO.WIZ').write_bytes(bytes(Spells()) + b'extra')
        files = read_native(file_index(root), 'hero')
        assert files['GAM'][0].get('name') == b'\x03ABC' + bytes(12)
        assert len(files['JNK']) == len(files['EFF']) == len(files['WIZ']) == 1
        assert file_size(files) == 508 and file_size(files, False) == 288
        (root / 'HERO.WIZ').write_bytes(bytes(219))
        try: read_native(file_index(root), 'hero')
        except BindingRequired: pass
        else: raise AssertionError('short spell block invented unread bytes')
        assert read_native(file_index(root), 'missing') is None
        old = ImportedCharacter()
        old.set('name', b'\x03ABC' + b'x' * 12)
        old.set('class', 5)
        old.set('race', 5)
        old.set('age', 200)
        old.set('money', bytes(range(14)))
        old.set('memorized', bytes(range(58)))
        old.set('known_spells', bytes(range(107)))
        old.set('spell_slots', bytes(range(20)))
        old.set('equipped_pointers', bytes(range(52)))
        old.set('items_pointer', 123)
        old.set('npc', 255)
        entries = []
        for ident in (41, 42, 47, 58, 60, 63, 69, 72, 73):
            item = Item(); item.set('type', ident); item.set('next_pointer', 123); entries.append(bytes(item))
        imported = import_character(bytes(old), b''.join(entries) + b'x', bytes(Effect()) + b'x')
        new, book = imported['GAM'][0], imported['WIZ'][0]
        assert new.get('age') == 70 and new.get('money') == bytes(range(8, 14))
        assert new.get('items_pointer') == new.get('spells_pointer') == 0
        assert new.get('npc') == 0
        assert new.get('equipped_pointers') == bytes(range(52))
        assert [r.get('type') for r in imported['JNK']] == [41, 73]
        assert all(r.get('next_pointer') == 0 for r in imported['JNK'])
        game = SimpleNamespace()
        char = materialize(imported, game)
        pool = game.item_pool
        assert char.items[0] is pool.slots[0] and char.items[1] is pool.slots[1]
        assert char.items == materialize(imported).items
        for slot in pool.slots[2:-1]:
            slot[:] = char.items[0]
        try:
            materialize(imported, game)
        except BindingRequired: pass
        else: raise AssertionError('Loaded items exceeded available slots')
        assert pool.allocate() is pool.slots[-1]
        assert [bytes(item) for item in char.items] == [bytes(item) for item in imported['JNK']]
        assert book.get('memorized') == bytes(range(58)) + bytes(16)
        assert book.get('known_spells') == bytes(range(107)) + bytes(7)
        assert book.get('spell_slots') == b''.join(bytes(range(i, i + 5)) + bytes(3) for i in range(0, 20, 5))
        for race, threshold, result in ((0, 1200, 1200), (1, 1200, 1200), (2, 200, 200), (3, 300, 300),
                                         (4, 300, 300), (5, 199, 70), (6, 50, 50)):
            old.set('race', race)
            old.set('age', threshold)
            assert import_character(bytes(old))['GAM'][0].get('age') == threshold
            old.set('age', threshold + 1)
            assert import_character(bytes(old))['GAM'][0].get('age') == result
        for cls in (2, 6, 14):
            old.set('class', cls)
            assert 'WIZ' not in import_character(bytes(old))
        old.set('npc', 0)
        (root / 'HERO.WHO').write_bytes(bytes(old))
        assert len(roster(root, imported=True)) == 1
        new.set('name', b'\x04ABC ' + bytes(11))
        assert not roster(root, (new,), imported=True)
        (root / 'HERO.PC').write_bytes(bytes(new))
        assert not roster(root, (new,)) and len(roster(root)) == 1
        new.set('npc', 128)
        (root / 'HERO.PC').write_bytes(bytes(new))
        assert not roster(root)
        for imported, kind, suffix in ((False, Character, '.PC'), (True, ImportedCharacter, '.WHO')):
            directory = root / suffix[1:]
            directory.mkdir()
            for stem in ('z', 'a0', 'A_', 'AA'):
                (directory / (stem + suffix)).write_bytes(bytes(kind()))
            index = file_index(directory)
            expected = tuple(stem + suffix for stem in ('AA', 'A_', 'a0', 'z'))
            for entries in (tuple(index.items()), tuple(reversed(tuple(index.items())))):
                read, seen = Path.read_bytes, []
                def record_read(path):
                    seen.append(path.name)
                    return read(path)
                with patch(__name__ + '.file_index', return_value=dict(entries)):
                    with patch.object(Path, 'read_bytes', record_read):
                        assert tuple(path.name for path in roster(directory, imported=imported)) == expected
                assert tuple(seen) == expected
