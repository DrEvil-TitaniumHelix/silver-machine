import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.engine import Session
from sm.titles import cok
from sm.titles.cok import creation, rules, training
from sm.titles.cok.creation import F, Kind as CK, tables
from sm.titles.cok.menu import Game
from sm.titles.cok.records import Character
from sm.titles.cok.training import Kind

MENU, WHO, TRAIN, KNIGHT, MODIFY, ACK = CK.MAIN_MENU.value, CK.WHO.value, Kind.TRAIN.value, Kind.KNIGHT.value, Kind.MODIFY.value, Kind.ACK.value
HALL_MASK = 0x7F


def starter_game(folder, root):
    seen, notes = [], []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if info.get('message'): notes.append(info['message'])
        if kind == ACK:
            notes.append(info['prompt'])
            return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        return answer(options) if callable(answer) else options.index(answer) if options is not None else answer
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    game.s.r1[creation.TRAIN_MASK] = HALL_MASK
    return game, seen, notes


def begin(game):
    return game.assets.labels[creation.BEGIN]


def hall(game, *rows):
    game.rows = iter(rows + ((MENU, begin(game)),))
    training.run(game)
    game.s.r1[creation.TRAIN_MASK] = HALL_MASK


def member(game, slot):
    return next(i for i, c in enumerate(game.s.party) if c.b[F['levels'] + slot] > 0 and sum(v > 0 for v in creation.levels(c.b)) == 1)


def train_rows(game, index, answer='Yes'):
    name = bytes(game.s.party[index].b[1:1 + game.s.party[index].b[0]]).decode('cp437')
    return (MENU, game.assets.labels[creation.TRAIN]), (WHO, name), (TRAIN, answer)


def one_class(folder, root, slot):
    game, seen, notes = starter_game(folder, root)
    t, rule = tables(game.assets), rules.tables()
    try: index = member(game, slot)
    except StopIteration: return None
    char = game.s.party[index]; b = char.b
    level = b[F['levels'] + slot]
    need = t.level_xp(creation.suborder(b, slot), level + 1)
    b[F['experience']:F['experience'] + 4] = need.to_bytes(4, 'little', signed=True)
    money, hp = bytes(b[F['money']:F['money'] + 14]), b[F['hp_max']]
    hall(game, *train_rows(game, index))
    assert b[F['levels'] + slot] == level + 1
    assert b[F['hp_max']] > hp
    assert bytes(b[F['money']:F['money'] + 14]) == money, 'the original charges no steel'
    assert 'Congratulations...' in notes
    thac0 = max(t.thac0Table[c * 13 + v] for c, v in enumerate(creation.levels(b))) + (b[F['deity']] == 3)
    assert b[F['base_thac0']] == thac0, (b[F['base_thac0']], thac0)
    for kind in range(1, 5):
        needed = min(20, rule.save_needed(slot, level + 1, kind))
        if b[F['levels'] + creation.KNIGHT] > b[F['former_levels'] + creation.KNIGHT]:
            needed = min(needed, rule.save_needed(creation.KNIGHT, b[F['former_levels'] + creation.KNIGHT], kind))
        assert b[F['saves'] + kind] == needed, kind
    return game, char, seen


def fighter_mage(folder, root):
    game, seen, notes = starter_game(folder, root)
    t, rule = tables(game.assets), rules.tables()
    index = next(i for i, c in enumerate(game.s.party) if c.b[F['levels'] + creation.MAGE] and c.b[F['levels'] + creation.FIGHTER])
    char = game.s.party[index]; b = char.b
    mage = b[F['levels'] + creation.MAGE]
    need = t.level_xp(creation.suborder(b, creation.MAGE), mage + 1)
    b[F['experience']:F['experience'] + 4] = need.to_bytes(4, 'little', signed=True)
    known = bytes(b[F['known_spells']:F['known_spells'] + 107])
    row = 7 if b[F['robe_order']] == 1 else 8
    hall(game, *train_rows(game, index), (Kind.SPELL.value, lambda options: 0))
    assert b[F['levels'] + creation.MAGE] == mage + 1
    for spell_level in range(1, 6):
        expected = (spell_level == 1) + sum(rule.gained_slots(row, k, spell_level) for k in range(2, mage + 2))
        assert b[F['spell_slots'] + 15 + spell_level - 1] == expected, spell_level
    assert bytes(b[F['known_spells']:F['known_spells'] + 107]) != known, 'training at a new mage level teaches a spell'
    return seen


def short_of_xp(folder, root):
    game, seen, notes = starter_game(folder, root)
    t = tables(game.assets)
    index = next(i for i, c in enumerate(game.s.party) if sum(v > 0 for v in creation.levels(c.b)) == 1)
    char = game.s.party[index]; b = char.b
    slot = next(c for c, v in enumerate(creation.levels(b)) if v)
    level = b[F['levels'] + slot]
    short = t.level_xp(creation.suborder(b, slot), level + 1) - 1
    b[F['experience']:F['experience'] + 4] = short.to_bytes(4, 'little', signed=True)
    rows = train_rows(game, index)[:2]
    hall(game, *rows)
    assert 'Not Enough Experience' in notes and b[F['levels'] + slot] == level
    return seen


def knight(folder, root):
    game, seen, notes = starter_game(folder, root)
    t = tables(game.assets)
    index = next((i for i, c in enumerate(game.s.party) if c.b[F['levels'] + creation.KNIGHT] > 0), None)
    assert index is not None, 'no knight among the starters'
    char = game.s.party[index]; b = char.b
    name = bytes(b[1:1 + b[0]]).decode('cp437')
    required = training.knight_required(game, 1)
    for a in range(6): b[F['abilities'] + 2 * a] = b[F['abilities'] + 2 * a + 1] = max(b[F['abilities'] + 2 * a], required[a])
    b[F['knight_order']], b[F['levels'] + creation.KNIGHT] = 1, 3
    need = t.level_xp(4, 3)
    b[F['experience']:F['experience'] + 4] = need.to_bytes(4, 'little', signed=True)
    hall(game, (MENU, game.assets.labels[creation.KNIGHT_MENU]), (WHO, name), (KNIGHT, 'Change'))
    assert b[F['knight_order']] == 2
    assert b[F['levels'] + creation.KNIGHT] == 3
    b[F['knight_order']], b[F['levels'] + creation.KNIGHT] = 1, 3
    b[F['hp_rolled']], b[F['hp_max']], b[F['hp']] = 20, 30, 30
    b[F['experience']:F['experience'] + 4] = (t.level_xp(4, 3) - 1).to_bytes(4, 'little', signed=True)
    training.advance_order(char, t)
    assert b[F['levels'] + creation.KNIGHT] == 2 and b[F['knight_order']] == 2
    assert b[F['hp_rolled']] == 20 - 20 // 4 and b[F['hp_max']] == 30 - 20 // 4 - training.con_hp_bonus(b, creation.KNIGHT)
    return seen


def knight_words(folder, root):
    game, _, _ = starter_game(folder, root)
    char = next(c for c in game.s.party if c.b[F['levels'] + creation.KNIGHT] > 0); b = char.b
    name, said = bytes(b[1:1 + b[0]]).decode('cp437'), []
    game.player = lambda kind, options, game, **info: said.append(info['prompt']) or options.index('Exit')
    b[F['knight_order']], b[F['levels'] + creation.KNIGHT] = 2, 3
    training.knight_promotion(game, char)
    required = training.knight_required(game, 1)
    for a in range(6): b[F['abilities'] + 2 * a] = max(b[F['abilities'] + 2 * a], required[a])
    b[F['knight_order']] = 1
    b[F['experience']:F['experience'] + 4] = tables(game.assets).level_xp(4, 3).to_bytes(4, 'little', signed=True)
    training.knight_promotion(game, char)
    assert said == [name + ' is too inexperienced', name + ' may become a Knight Of The Sword'], said


def modify(folder, root):
    game, seen, notes = starter_game(folder, root)
    t = tables(game.assets)
    index = next(i for i, c in enumerate(game.s.party) if c.b[F['npc']] == 0)
    char = game.s.party[index]; b = char.b
    name = bytes(b[1:1 + b[0]]).decode('cp437')
    label = game.assets.labels[creation.MODIFY]
    b[F['experience']:F['experience'] + 4] = (2001).to_bytes(4, 'little', signed=True)
    b[F['dual_threshold']] = 0
    before = bytes(b)
    hall(game, (MENU, label), (WHO, name), (MODIFY, 'Next'), (MODIFY, 'Add'), (MODIFY, 'Exit'))
    assert bytes(b) == before, 'Exit undoes every change'
    at = F['abilities'] + 2 * 1 + 1
    was = b[at]
    high = t.race_limit(b[F['race']], 7)
    hall(game, (MENU, label), (WHO, name), (MODIFY, 'Next'), (MODIFY, 'Add'), (MODIFY, 'Keep'))
    assert b[at] == min(was + 1, high) and b[at - 1] == b[at] and b[F['modified']] == 1
    b[F['experience']:F['experience'] + 4] = (2002).to_bytes(4, 'little', signed=True)
    notes.clear()
    hall(game, (MENU, label), (WHO, name))
    assert any("can't be modified" in n for n in notes), notes
    return seen


def session_walk(folder, root):
    os.environ['SM_SAVE_ROOT'] = root
    from sm.titles.cok import intake
    s = Session(profile=cok, slot=None, directory=folder, auto_resolve=False)
    log = []
    def answer(kind, text):
        d = s.decision
        assert d and d['kind'] == kind, d
        log.append(d)
        s.step(next(i for i, o in enumerate(d['options']) if o.startswith(text)))
    try:
        answer(MENU, 'Load'); answer(CK.SLOT.value, 'A')
        first = s.game.s.party[0]
        name = bytes(first.b[1:1 + first.b[0]]).decode('cp437')
        answer(MENU, 'View'); answer(WHO, name); assert s.decision['kind'] == CK.VIEW.value
        info = s.decision['info']
        assert info['name'] == name and info['hp'] == first.b[F['hp_max']] and 'STR' in info['abilities'], info
        answer(CK.VIEW.value, 'Exit')
        answer(MENU, 'Remove'); answer(WHO, name)
        assert len(s.game.s.party) == 5 and (Path(root) / 'cok' / (creation.file_stem(name) + '.WHO')).is_file()
        second = bytes(s.game.s.party[0].b[1:1 + s.game.s.party[0].b[0]]).decode('cp437')
        answer(MENU, 'Drop'); answer(WHO, second); answer(CK.DROP.value, 'Yes'); answer(CK.DROP.value, 'No')
        assert len(s.game.s.party) == 5
        answer(MENU, 'Drop'); answer(WHO, second); answer(CK.DROP.value, 'Yes'); answer(CK.DROP.value, 'Yes')
        assert len(s.game.s.party) == 4 and second not in [bytes(c.b[1:1 + c.b[0]]).decode('cp437') for c in s.game.s.party]
    finally:
        s.close()
    return [d['hash'] for d in log]


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    saved = os.environ.get('SM_SAVE_ROOT')
    try:
        with tempfile.TemporaryDirectory(prefix='cok-train-') as first, tempfile.TemporaryDirectory(prefix='cok-train-') as second:
            run = lambda root: (one_class(folder, root, creation.KNIGHT)[2], one_class(folder, root, creation.RANGER)[2], fighter_mage(folder, root),
                                short_of_xp(folder, root), knight(folder, root), modify(folder, root), session_walk(folder, root))
            knight_words(folder, first)
            one, two = run(first), run(second)
            assert one == two, 'replay diverged'
    finally:
        if saved is None: os.environ.pop('SM_SAVE_ROOT', None)
        else: os.environ['SM_SAVE_ROOT'] = saved
    return 'PASS train, knight, modify, view, remove, drop; %d decisions' % sum(len(r) for r in one if r)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
