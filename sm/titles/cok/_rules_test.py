import argparse
import os
from pathlib import Path
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import rules
from sm.titles.cok.records import Character, Item
from sm.titles.cok.save import load
from sm.titles.ssb.state import State

POINTERS = {'effects_pointer', 'items_pointer', 'equipped_pointers', 'next_pointer', 'combat_pointer'}
EXPECTED = {('CHRDATA5', 'known_spells'), ('CHRDATA6', 'known_spells')}


def field_diff(before, after, kind=Character):
    return [(name, before[o:o + w], after[o:o + w]) for name, (o, w) in kind.FIELDS.items()
            if before[o:o + w] != after[o:o + w]]


def pointer_mismatches(disk, char, slots):
    record, addresses, address = Character(disk), {}, Character(disk).get('items_pointer')
    for raw in char.items:
        addresses[id(raw)] = address
        address = Item(raw).get('next_pointer')
    stored = struct.unpack('<13I', record.get('equipped_pointers'))
    derived = [0 if item is None else addresses[id(item.data)] for item in slots]
    return [(slot, hex(s), hex(d)) for slot, (s, d) in enumerate(zip(stored, derived)) if s != d]


def compare(directory):
    report = {}
    for stem, files in load(Path(directory) / 'SAVE').members.items():
        disk, items = bytes(files['SAV'][0]), [bytes(r) for r in files.get('STF', ())]
        char = rules.character(disk, items, [bytes(r) for r in files.get('SFX', ())])
        slots = rules.recalc_stats(char)
        pointers = pointer_mismatches(disk, char, slots)
        rules.recalc_class_stats(char, slots)
        sav, stf, sfx = rules.write_character(char)
        assert sfx == b''.join(bytes(r) for r in files.get('SFX', ()))
        report[stem] = dict(fields=[row for row in field_diff(disk, sav) if row[0] not in POINTERS],
                            items=[(i, row) for i, raw in enumerate(items)
                                   for row in field_diff(raw, stf[i * 63:(i + 1) * 63], Item)],
                            pointers=pointers)
    return report


def show(report):
    unexpected = 0
    for stem, row in report.items():
        for name, disk, ours in row['fields']:
            changed = [(i + 1, a, b) for i, (a, b) in enumerate(zip(disk, ours)) if a != b]
            print(stem, name, '(entry, disk, ours):', changed)
            unexpected += (stem, name) not in EXPECTED
        for index, (name, disk, ours) in row['items']:
            print(stem, 'item', index, name, 'disk', list(disk), 'ours', list(ours))
            unexpected += 1
        for slot, disk, ours in row['pointers']:
            print(stem, 'equipped slot', slot, 'disk', disk, 'ours', ours)
            unexpected += 1
    print('unexpected differences:', unexpected)
    return unexpected


def restored_party(directory):
    state, snapshot = State(), rules.load_slot(Path(directory) / 'SAVE', 'A')
    party = rules.restore(state, snapshot)
    assert state.party is party and len(party) == len(snapshot.members) == 6
    assert [Character(bytes(c.b)).get('order') for c in party] == list(range(6))
    return party


def test():
    from unittest import SkipTest
    folder = os.environ.get('SM_COK')
    if not folder:
        raise SkipTest('SM_COK is not set')
    assert not show(compare(folder))
    restored_party(folder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    arguments = parser.parse_args()
    os.environ['SM_COK'] = arguments.folder
    failed = show(compare(arguments.folder))
    restored_party(arguments.folder)
    print('slot A party restored: 6 members, order numbers 0..5')
    raise SystemExit(1 if failed else 0)
