import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.files import file_index
from sm.titles.cok.data import Assets
from sm.titles.cok.records import Character, Item, Effect, SavedGame, split_records
from sm.titles.cok import save


def record_check(record):
    before = bytes(record)
    for name, (offset, width) in record.FIELDS.items():
        value = record.get(name)
        record.set(name, value)
        assert bytes(record) == before, name
        changed = type(record)(before)
        replacement = bytes(width) if isinstance(value, bytes) else 0
        changed.set(name, replacement)
        assert bytes(changed)[:offset] == before[:offset], name
        assert bytes(changed)[offset + width:] == before[offset + width:], name
        assert len(bytes(changed)) == record.SIZE


def check(directory):
    assets = Assets(directory)
    for name in assets.layout['tables']:
        assets.table(name)
    census = assets.script_census()
    assert (census['records'], census['instructions'], census['opcodes'], census['undecoded']) == (22, 13547, 58, 0)
    assert all(row['vectors'][4] == 0x8014 for row in census['blocks'])
    monsters = maps = 0
    for dataset in (1, 2, 3):
        for raw in assets.records('MON%dCHA' % dataset).values():
            record_check(Character(raw))
            monsters += 1
        for raw in assets.records('GEO%d' % dataset).values():
            assert len(raw) == 1026
            maps += 1
    assert (monsters, maps) == (88, 15)
    fixture = assets.root / 'SAVE'
    snapshot = save.load(fixture)
    record_check(snapshot.game)
    items = effects = 0
    for files in snapshot.members.values():
        for records in files.values():
            for record in records:
                record_check(record)
                items += isinstance(record, Item)
                effects += isinstance(record, Effect)
    assert (len(snapshot.members), items, effects) == (6, 26, 8)
    index = file_index(fixture)
    disk = snapshot.dump()
    for name, raw in disk.items():
        assert raw == index[name.upper()].read_bytes(), 'save round trip: ' + name
    for record_type in (Character, Item, Effect, SavedGame):
        try:
            split_records(bytes(record_type.SIZE - 1), record_type)
        except ValueError:
            pass
        else:
            raise AssertionError('partial record accepted')
    bad = SavedGame(bytes(snapshot.game))
    bad.set('party_count', 9)
    try:
        save.member_stems(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('oversize party accepted')
    from unittest.mock import patch
    from sm.titles.cok.intake import inspect_folder
    entry = json.loads(Path(__file__).with_name('supported_versions.json').read_text(encoding='utf-8'))
    entry['versions'][0]['files']['ECL1.DAX']['sha256'] = '0' * 64
    with patch('sm.titles.cok.intake.catalog', return_value=entry):
        assert not inspect_folder(assets.root)['ok']
    return dict(gate='intake-codecs', result='PASS', route_percent=0,
                gameplay_started=False, tables=len(assets.layout['tables']),
                monsters=monsters, maps=maps, party=6, items=items, effects=effects,
                save_files=len(disk), save_hashes={name: hashlib.sha256(raw).hexdigest()
                                                  for name, raw in disk.items()}, scripts=census)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(arguments)
    report = check(args.folder)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS intake-codecs: 16 tables; 22 scripts / 13547 instructions; '
          '88 creatures; 18 save files identical; gameplay not started')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
