import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.ssb.state import Char
from sm.titles.cok import creation, rules
from sm.titles.cok.creation import F, Kind
from sm.titles.cok.faults import BindingRequired
from sm.titles.cok.records import Character, Item, Effect, SavedGame, split_records

LEGAL = {0: (0, 2, 5, 4, 8, 9, 10, 11, 13), 1: (0, 2, 5, 6, 4, 8, 10, 9, 11, 13, 14, 15, 16), 2: (0, 2, 5, 6, 4, 7, 8, 10, 9, 11, 13, 14, 15, 16),
         3: (0, 2, 6, 8, 12, 14), 4: (0, 2, 6, 4, 8, 10, 12, 14), 5: (0, 2, 6, 4, 8, 10, 12, 14), 6: (0, 2, 5, 6, 4, 7)}
HUMAN = 6


def bind_rules_if_pending():
    try:
        rules.character(bytes(Character.SIZE), [], [])
    except BindingRequired:
        originals = rules.character, rules.recalc, rules.write_character
        rules.character = lambda record, items, effects, rid=None: Char(record, items, effects, rid)
        rules.recalc = lambda char: None
        rules.write_character = lambda char: (bytes(char.b), b''.join(bytes(i) for i in char.items), b''.join(bytes(e) for e in char.effects))
        return originals
    except Exception:
        pass
    return None


def player_for(script):
    rows = iter(script); seen = []
    def player(kind, options, game, **info):
        expected, label = next(rows)
        assert kind == expected, (kind, expected)
        seen.append(game.state_hash())
        if options is None: return label
        return options.index(label)
    return player, seen


def script_for(game, cls_name, name, cleric):
    t = creation.tables(game.assets)
    rows = [(Kind.MAIN_MENU.value, game.assets.labels[creation.CREATE]), (Kind.RACE.value, t.races[HUMAN]), (Kind.GENDER.value, t.genders[0]),
            (Kind.CLASS.value, cls_name)]
    if cleric: rows.append((Kind.DEITY.value, t.deities[1]))
    return rows


def run_once(folder, directory):
    from sm.titles.cok.menu import Game
    probe = Game(lambda *a, **k: 0, slot=None, directory=folder)
    t = creation.tables(probe.assets)
    for race, expected in LEGAL.items():
        assert t.legal_classes(race) == expected, race
    assert F['npc'] == 231 and F['money'] <= creation.ROSTER_HIDE_BYTE < F['money'] + 14
    names, script = [], []
    for index, cls in enumerate(LEGAL[HUMAN]):
        name = 'HERO%d' % index; names.append(name)
        script += script_for(probe, t.classes[cls], name, cls == creation.CLERIC)
        allowed = [a for bit, a in enumerate(t.alignment_choices) if t.classAlignMask[cls] >> bit & 1
                   and (cls != creation.CLERIC or 0x15 >> bit & 1)]
        script += [(Kind.ALIGNMENT.value, t.alignments[allowed[0]]), (Kind.ROLL.value, 'No'), (Kind.NAME.value, name.lower()),
                   (Kind.ICON.value, 'Keep'), (Kind.SAVE.value, 'Yes')]
    script += [(Kind.MAIN_MENU.value, probe.assets.labels[creation.ADD]), (Kind.ADD.value, 'HERO0'), (Kind.ADD.value, creation.EXIT),
               (Kind.MAIN_MENU.value, probe.assets.labels[creation.BEGIN])]
    player, seen = player_for(script)
    game = Game(player, slot=None, directory=folder); game.roster_directory = directory
    creation.run(game)
    assert game.s.party and game.s.r1[creation.PARTY_SIZE] == 1 and game.s.mode == 4
    return game, seen, names, t


def check_record(path, cls, t):
    r = Character(path.read_bytes()); b = r.data; start, xp = creation.START[cls]
    assert r.get('class') == cls and r.get('race') == HUMAN
    assert r.get('experience', signed=True) >= xp
    for slot in start: assert b[F['levels'] + slot] >= 1
    assert all(3 <= b[F['abilities'] + 2 * a + 1] <= 19 for a in range(6))
    for a in range(6):
        assert b[F['abilities'] + 2 * a] == b[F['abilities'] + 2 * a + 1] >= t.classMin[cls * 6 + a]
    assert b[F['hp_max']] >= 1 and b[F['hp']] == b[F['hp_max']]
    assert b[F['base_move']] == 12 and b[F['attacks']] == 2
    assert b[F['order']] == 10 and b[F['base_ac']] == 50
    return r


def image(char):
    return bytes(char.b), [bytes(i) for i in char.items], [bytes(e) for e in char.effects]


def saveload_run(folder, root):
    from sm.titles.cok import _rules_test
    from sm.titles.cok.menu import Game
    labels = Game(lambda *a, **k: 0, slot=None, directory=folder).assets.labels
    menu, slot = Kind.MAIN_MENU.value, Kind.SLOT.value
    def play(*rows):
        player, seen = player_for(rows)
        game = Game(player, slot=None, directory=folder); game.roster_directory = root
        creation.run(game)
        return game, seen
    game, seen = play((menu, labels[creation.LOAD]), (slot, 'A'), (menu, labels[creation.BEGIN]))
    s = game.s
    assert [image(c) for c in s.party] == [image(c) for c in _rules_test.restored_party(folder)]
    assert len(s.party) == s.r1[creation.PARTY_SIZE] == 6 and (s.dataset, s.x, s.y) == (1, 7, 13) and s.mode == 4
    stem = creation.dos_stem(bytes(s.party[0].b[1:1 + s.party[0].b[0]]).decode('cp437'))
    Path(root, stem + '.WHO').write_bytes(bytes(Character.SIZE))
    copy = bytearray(s.party[1].b); assert copy[0] < 15
    copy[1 + copy[0]] ^= 0x55; Path(root, 'JUNK.WHO').write_bytes(bytes(copy))
    assert 'JUNK' not in [e['file'] for e in creation.roster(s, root)]
    copy[1] ^= 1; Path(root, 'JUNK.WHO').write_bytes(bytes(copy))
    assert 'JUNK' in [e['file'] for e in creation.roster(s, root)]
    Path(root, 'JUNK.WHO').unlink()
    for stem in ('A_', 'AA'): Path(root, stem + '.WHO').write_bytes(bytes(copy))
    native = [n[:-4] for n in os.listdir(root) if n[:-4] in ('A_', 'AA')]
    assert [e['file'] for e in creation.roster(s, root) if e['file'] in ('A_', 'AA')] == native, native
    for stem in ('A_', 'AA'): Path(root, stem + '.WHO').unlink()
    assert game.walls_filed == tuple(k for k, ident in enumerate(s.walls, 1) if ident == 0)
    s.x, s.y, s.dir = 9, 4, 2
    s.block = s.r0[0xF2] = 36
    s.r0[0x100], s.r0[0x11F], s.r1[0x379], s.r1[0x382] = 7, 8, 9, 10
    before = game.state_hash()
    creation.save_game(game, 'B')
    assert game.state_hash() == before and not Path(root, stem + '.WHO').exists()
    written = sorted(p.name for p in Path(root, 'B').iterdir())
    assert 'SAVGAMB.DAT' in written and all('CHRDATB%d.SAV' % n in written for n in range(1, 7)), written
    s.x, s.party = 0, s.party[:1]
    creation.load_game(game, 'B')
    assert game.state_hash() == before, 'save then load changed the state'
    dat = Path(root, 'B', 'SAVGAMB.DAT'); raw = dat.read_bytes()
    dat.write_bytes(raw[:1 + 2 * creation.PICTURES_CELL] + b'' + raw[3 + 2 * creation.PICTURES_CELL:]); creation.load_game(game, 'B')
    assert (s.g[creation.PICTURES], s.g[creation.ANIMATIONS]) == (0, 1)
    dat.write_bytes(raw)
    creation.load_game(game, 'A')
    creation.save_game(game, 'C')
    shipped, ours = SavedGame((Path(folder) / 'SAVE' / 'SAVGAMA.DAT').read_bytes()), SavedGame(Path(root, 'C', 'SAVGAMC.DAT').read_bytes())
    for name in SavedGame.FIELDS:
        assert name == 'party_names' or shipped.get(name) == ours.get(name), name
    other, more = play((menu, labels[creation.LOAD]), (slot, 'B'), (menu, labels[creation.BEGIN]))
    assert creation.available_slots(other) == ['A', 'B', 'C'] and (other.s.x, other.s.y, other.s.dir, other.s.block) == (9, 4, 2, 36)
    other.vm.load_block(36); other.vm.init_vm()
    assert other.vm.resuming and (other.s.r0[0x100], other.s.r0[0x11F], other.s.r1[0x379], other.s.r1[0x382]) == (7, 8, 9, 10)
    creation.load_game(game, 'B')
    assert [image(c) for c in other.s.party] == [image(c) for c in game.s.party]
    stf = next(p for p in sorted(Path(root, 'C').glob('*.STF')))
    index = int(stf.stem[-1]) - 1; count = len(game.s.party[index].items)
    stf.write_bytes(stf.read_bytes() + b''); sav = Path(root, 'C', 'CHRDATC6.SAV'); sav.write_bytes(sav.read_bytes()[:-1])
    creation.load_game(game, 'C')
    assert len(game.s.party) == 6 and len(game.s.party[index].items) == count
    return seen + more


def saveload_test(folder):
    gog = sorted(p.name for p in (Path(folder) / 'SAVE').iterdir())
    with tempfile.TemporaryDirectory(prefix='cok-load-') as first, tempfile.TemporaryDirectory(prefix='cok-load-') as second:
        assert saveload_run(folder, first) == saveload_run(folder, second), 'replay diverged'
        assert not list(Path(first).glob('*-new-*')) and not list(Path(first).glob('*-old'))
    assert sorted(p.name for p in (Path(folder) / 'SAVE').iterdir()) == gog


def test(folder=None):
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir():
        return 'skipped (no Champions copy)'
    os.environ.setdefault('SM_COK', str(folder))
    pending = bind_rules_if_pending()
    try:
        with tempfile.TemporaryDirectory(prefix='cok-creation-') as first, tempfile.TemporaryDirectory(prefix='cok-creation-') as second:
            game, seen, names, t = run_once(folder, first)
            for index, cls in enumerate(LEGAL[HUMAN]):
                path = Path(first) / (names[index] + '.WHO')
                r = check_record(path, cls, t)
                assert r.get('name')[1:1 + r.data[0]] == names[index].encode('ascii'), 'ReadString uppercases'
            knight = Path(first) / (names[LEGAL[HUMAN].index(creation.KNIGHT)] + '.STF')
            kit = split_records(knight.read_bytes(), Item)
            assert [item.get('type') for item in kit] == [36, 37, 18]
            ranger = Path(first) / (names[LEGAL[HUMAN].index(creation.RANGER)] + '.SFX')
            assert [e.get('type') for e in split_records(ranger.read_bytes(), Effect)] == [creation.RANGER_EFFECT]
            assert not (Path(first) / (names[0] + '.SFX')).exists()
            listed = [e['file'] for e in creation.roster(game.s, first)]
            assert listed == sorted(names[1:]), listed
            assert game.s.party[0].b[F['order']] == 0
            assert creation.file_stem('a b..c*d') == 'ABCD' and creation.sanitize('a..b', '.') == 'a.b'
            replay, seen2, _, _ = run_once(folder, second)
            assert seen == seen2 and replay.state_hash() == game.state_hash(), 'replay diverged'
            for name in sorted(p.name for p in Path(first).iterdir()):
                assert (Path(first) / name).read_bytes() == (Path(second) / name).read_bytes(), name
        saveload_test(folder)
        return 'PASS %d classes, %d decisions, HP/THAC0 %s' % (len(LEGAL[HUMAN]), len(seen), 'pending rules' if pending else 'recalculated')
    finally:
        if pending: rules.character, rules.recalc, rules.write_character = pending


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
