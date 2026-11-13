import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import camp, creation
from sm.titles.cok.camp import Kind, tables
from sm.titles.cok.creation import F
from sm.titles.cok.menu import Game

MENU, WHO, SPELL, REST, CONFIRM, ACK = (k.value for k in (Kind.MENU, Kind.WHO, Kind.SPELL, Kind.REST, Kind.CONFIRM, Kind.ACK))
RESTING = 'CAMP_RESTING'
EXIT = creation.EXIT


def party_game(folder, root, script):
    rows, seen = iter(script), []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if kind == ACK: game.acks.append(info.get('prompt')); return 0
        if kind == RESTING and not game.stop_at: return 0
        if kind == RESTING: game.stop_at -= 1; return 1 if not game.stop_at else 0
        expected, answer = next(rows)
        assert kind == expected, (kind, expected, info)
        return answer(options) if callable(answer) else options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root; game.acks = []; game.stop_at = 0
    creation.load_game(game, 'A'); game.s.mode = 4
    for char in game.s.party:
        char.b[F['memorized']:F['memorized'] + 58] = bytes(58)
    return game, seen


def clock_minutes(s):
    c = s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7]
    return c[1] + 10 * c[2] + 60 * c[3] + 1440 * c[4] + 43200 * c[5]


def caster(game, cls):
    return next(i for i, c in enumerate(game.s.party) if c.b[F['levels'] + cls] > 0)


def to_member(game, frm, index):
    return [(MENU, 'char-down')] * ((index - frm) % len(game.s.party))


def fill_script(game, index, cls, t, at=0):
    char = game.s.party[index]
    count = camp.slot_count(char, 0 if cls == camp.CLERIC else 3, 1) + (camp.slot_display(game, char, t)[0] if cls == camp.MAGE else 0)
    first = next(s for s in camp.memorizable(char, t) if t.level(s) == 1 and t.spell_class(s) == (0 if cls == camp.CLERIC else 3))
    row = camp.memorizable(char, t).index(first)
    rows = [(MENU, 'Magic')] + to_member(game, at, index) + [(MENU, 'Memorize')] + [(SPELL, lambda options: row)] * (count + 1) + [(SPELL, EXIT), (SPELL, EXIT), (CONFIRM, 'Yes'), (MENU, EXIT)]
    return rows, count, first


def memorize_rest(folder, root):
    probe, _ = party_game(folder, root, [])
    t = tables(probe.assets)
    cleric, mage = caster(probe, camp.CLERIC), caster(probe, camp.MAGE)
    a, cleric_count, cleric_spell = fill_script(probe, cleric, camp.CLERIC, t)
    b, mage_count, mage_spell = fill_script(probe, mage, camp.MAGE, t, cleric)
    assert cleric_count and mage_count
    script = a + b + [(MENU, 'Rest'), (REST, 'Rest'), (MENU, EXIT)]
    game, seen = party_game(folder, root, script)
    s = game.s
    before = clock_minutes(s)
    assert camp.run(game) is False
    spent = clock_minutes(s) - before
    levels = max(cleric_count, mage_count)
    expected = 4 * 60 + 15 * levels
    assert spent == (expected + 4) // 5 * 5, (spent, expected)
    for index, count, spell in ((cleric, cleric_count, cleric_spell), (mage, mage_count, mage_spell)):
        memorized = [n for n in camp.memory(s.party[index]) if n]
        assert memorized == [spell] * count, memorized
        said = camp.name(s.party[index]) + ' has memorized ' + t.names[spell - 1]
        assert game.acks.count(said) == count, (said, game.acks)
    assert s.mode == 4
    return seen


def day_rest(folder, root):
    script = [(MENU, 'Rest'), (REST, 'Days'), (REST, 'Add'), (REST, 'Rest'), (MENU, EXIT)]
    game, seen = party_game(folder, root, script)
    s = game.s
    for char in s.party: char.b[F['hp']] = char.b[F['hp_max']] - 3
    s.r0[camp.CLOCK_CELL + 3] = 23
    junction, before = s.r0[0x1FC], clock_minutes(s)
    camp.run(game)
    assert clock_minutes(s) - before == 1440 and s.r0[0x1FC] != junction
    assert all(c.b[F['hp']] == c.b[F['hp_max']] - 2 for c in s.party), 'one hit point per rested day'
    return seen


def stop_resting(folder, root):
    script = [(MENU, 'Rest'), (REST, 'Days'), (REST, 'Add'), (REST, 'Rest'), (CONFIRM, 'No'), (CONFIRM, 'Yes'), (MENU, EXIT)]
    game, seen = party_game(folder, root, script)
    s, prompts = game.s, []
    player = game.player
    game.player = lambda kind, options, g, **info: (prompts.append(info.get('prompt')) if kind == CONFIRM else None, player(kind, options, g, **info))[1]
    game.rest_poll = True
    before = clock_minutes(s); game.stop_at = 3
    def keys(kind, options, g, **info):
        if kind == RESTING and g.stop_at == 0: g.stop_at = 1
        return player2(kind, options, g, **info)
    player2, game.player = game.player, keys
    camp.run(game)
    assert prompts == ['Stop Resting? ', 'Stop Resting? '], prompts
    assert 0 < clock_minutes(s) - before < 1440, clock_minutes(s) - before
    return seen


def fixes(folder, root):
    game, seen = party_game(folder, root, [])
    def player(kind, options, current, **info):
        seen.append(current.state_hash())
        if kind == ACK: return 0
        if not camp.missing(current.s): return options.index(EXIT)
        return options.index('Fix')
    game.player = player
    s = game.s
    for char in s.party: char.b[F['hp']] = max(1, char.b[F['hp_max']] // 2)
    assert camp.missing(s)
    before = clock_minutes(s)
    camp.run(game)
    assert not camp.missing(s) and clock_minutes(s) > before, (camp.missing(s), clock_minutes(s) - before)
    return seen


def effects(folder, root):
    game, _ = party_game(folder, root, [])
    char = game.s.party[0]
    timed = lambda kind, minutes: bytearray([kind, minutes & 255, minutes >> 8, 0, 0, 0, 0, 0, 0])
    char.effects[:] = [timed(50, 20), timed(51, 5), timed(52, 0)]
    assert camp.age_effects(game, char, 5)
    assert [e[0] for e in char.effects] == [50, 52] and char.effects[0][1] == 10
    char.effects[:] = [timed(50, 15), timed(52, 0)]
    assert camp.age_effects(game, char, 5) and char.effects[0][1] == 10
    char.effects[:] = [timed(14, 5)]
    assert not camp.age_effects(game, char, 5) and not char.effects
    char.effects[:] = [bytearray([48, 5, 0, 255, 1, 0, 0, 0, 0])]
    try: camp.age_effects(game, char, 5)
    except camp.BindingRequired: pass
    else: raise AssertionError('a combat-only handler on expiry must be an explicit fault')
    rest = [0, 3, 0, 0, 0, 0, 0]
    camp.decrement_rest(game, rest, 5, 1)
    assert not any(rest), rest
    rest = [0, 0, 1, 2, 0, 0, 0]
    camp.decrement_rest(game, rest, 5, 1)
    assert rest[1:4] == [5, 0, 2], rest


def menus(folder, root):
    from sm.titles.cok import alter
    from sm.titles.cok.creation import Kind as CK
    seen, kinds = [], []
    down = [('char-down', MENU)] * 4
    script = iter([('Save', CK.SLOT.value), (EXIT, CONFIRM), ('No', MENU),
                   ('View', CK.VIEW.value), (EXIT, MENU),
                   ('Magic', MENU), *down, ('Cast', SPELL), (EXIT, MENU), ('Memorize', SPELL), (EXIT, MENU), ('Scribe', MENU),
                   ('Display', MENU), ('Rest', REST), ('Exit', MENU), (EXIT, MENU),
                   ('Rest', REST), ('Exit', MENU), ('Alter', alter.Kind.MENU.value), (EXIT, MENU), ('Fix', MENU), (EXIT, None)])
    expected = [MENU]
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        kinds.append((kind, tuple(options), info.get('lines')))
        if kind == ACK: return 0
        assert kind == expected[0], (kind, expected[0], options, info)
        answer, expected[0] = next(script)
        return options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root; game.acks = []
    creation.load_game(game, 'A'); game.s.mode = 4
    game.vm.service = lambda unit, entry: game.ask(CK.VIEW.value, (EXIT,), prompt='sheet')
    assert camp.run(game) is False
    menus_seen = [options for kind, options, _ in kinds if kind == MENU]
    assert menus_seen[0] == ('Save', 'View', 'Magic', 'Rest', 'Alter', 'Fix', EXIT) + camp.MEMBER_KEYS, menus_seen[0]
    assert ('Cast', 'Memorize', 'Scribe', 'Display', 'Rest', EXIT) + camp.MEMBER_KEYS in menus_seen, menus_seen
    assert game.s.sel == 4 and not any(kind == WHO for kind, _, _ in kinds)
    lines = next(row[2] for row in kinds if row[2])
    assert lines[:4] == (' ', camp.name(game.s.party[0]), ' <No Spell Effects>', ' ') and len(lines) == 19, lines
    t = tables(game.assets)
    effects_list = game.s.party[0].effects
    effects_list.append(bytearray([1, 6, 0, 2, 0, 0, 0, 0, 0]))
    effects_list.append(bytearray([44, 6, 0, 2, 0, 0, 0, 0, 0]))
    effects_list.append(bytearray([18, 0, 0, 0, 0, 0, 0, 0, 0]))
    assert camp.display_lines(game.s, t)[:5] == (' ', camp.name(game.s.party[0]), ' ' + t.names[0], ' Cause Disease', ' ')
    return seen


def member_keys(folder, root):
    names = []
    keys = iter(('char-up', 'char-down', 'char-down', EXIT))
    def player(kind, options, game, **info):
        assert kind == MENU
        names.append(info['member'])
        return options.index(next(keys))
    game, _ = party_game(folder, root, [])
    game.player = player
    assert camp.run(game) is False
    party = [camp.name(c) for c in game.s.party]
    assert names == [party[0], party[-1], party[0], party[1]] and game.s.sel == 1, names


def learn_row():
    assert camp.opening_row([1, 1, 1, 2, 2, 2, 2, 2, 2], 18) == 8
    assert camp.opening_row([1] * 12, 11) == 9
    assert camp.opening_row([1] * 9 + [2] * 3, 11) == 8


def memorize_list(folder, root):
    game, _ = party_game(folder, root, [])
    t = tables(game.assets)
    ids = camp.memorizable(game.s.party[4], t)
    levels = [t.level(s) for s in ids]
    assert len(ids) == 13 and levels[:4] == [0, 0, 0, 1] and levels == sorted(levels), levels
    assert camp.opening_row(levels, camp.MEMORIZE_PAGE) == 8


def pending_list_first(folder, root):
    asked = []
    def player(kind, options, game, **info):
        asked.append((kind, tuple(options), info.get('prompt'), info.get('title')))
        return {SPELL: 0 if len(asked) == 3 else len(options) - 1, CONFIRM: 1 if len(asked) == 2 else 0}.get(kind, 0)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    t = tables(game.assets)
    mage = game.s.party[caster(game, camp.MAGE)]
    mage.b[F['memorized']:F['memorized'] + 58] = bytes(58)
    spell = next(s for s in camp.memorizable(mage, t) if t.level(s) == 1 and t.spell_class(s) == 3)
    mage.b[F['memorized']] = spell | camp.PENDING
    camp.memorize(game, mage)
    shape = [row for row in asked if row[0] != ACK]
    assert shape[0] == (SPELL, (EXIT,), '', 'to Memorize') and shape[1] == (CONFIRM, ('Yes', 'No'), 'Memorize These Spells? ', None), shape[:2]
    assert shape[-2] == (SPELL, (EXIT,), '', 'to Memorize') and shape[-1] == (CONFIRM, ('Yes', 'No'), 'Memorize these spells? ', None), shape[-2:]
    assert len(shape) == 6 and [row[2] for row in shape[2:4]] == ['memorize', 'memorize'], shape


def pending_lines(folder, root):
    asked = []
    def player(kind, options, game, **info):
        asked.append(info)
        return 0
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    t = tables(game.assets)
    kal = game.s.party[4]
    one, two, special = 1, 22, 101
    assert [(t.spell_class(s), t.level(s)) for s in (one, two, special)] == [(0, 1), (0, 2), (2, 0)]
    kal.b[F['memorized']:F['memorized'] + 58] = bytes(v | camp.PENDING for v in (one, one, two, special)) + bytes(54)
    camp.memorize(game, kal)
    assert asked[0]['lines'] == (' *' + t.names[special - 1], ' *%s (2)' % t.names[one - 1], ' *' + t.names[two - 1]) and asked[0]['levels'] == (0, 1, 2), asked[0]


def signed_levels(folder, root):
    game, _ = party_game(folder, root, [])
    t = tables(game.assets)
    char = game.s.party[0]
    char.b[F['race']] = camp.HUMAN
    char.b[F['levels']:F['levels'] + 8] = bytes((0, 0, 2, 0, 0, 0, 0, 0))
    char.b[F['former_levels']:F['former_levels'] + 8] = bytes((3, 0, 0, 0, 0, 0, 0, 0))
    char.b[F['abilities'] + 2 * 2 + 1] = 12
    char.b[F['dual_threshold']] = 0xFF
    assert camp.can_cast(char, 1, t), 'the earlier cleric levels count: 2 > -1'
    char.b[F['dual_threshold']] = 2
    assert not camp.can_cast(char, 1, t), 'not above the threshold'


def slot_lines(folder, root):
    game, _ = party_game(folder, root, [])
    t = tables(game.assets)
    cleric = game.s.party[caster(game, camp.CLERIC)]
    cleric.b[F['deity']] = 1
    rows = camp.slot_display(game, cleric, t)[2].splitlines()
    assert rows[0].startswith('    Cleric Spells: ') and rows[0][19].isdigit() and '   Special Spells: 1' in rows, rows
    level1 = camp.slot_count(cleric, 0, 1)
    cleric.b[F['memorized']:F['memorized'] + level1] = bytes([next(s for s in range(1, 108) if t.level(s) == 1 and t.spell_class(s) == 0)]) * level1
    assert camp.slot_display(game, cleric, t)[2].splitlines()[0][19:20] == '0'


def prep_wrap(folder, root):
    game, _ = party_game(folder, root, [])
    t = tables(game.assets)
    five = next(s for s in range(1, 108) if t.level(s) == 5)
    char = game.s.party[0]
    char.b[F['memorized']:F['memorized'] + 58] = bytes([five | camp.PENDING]) * 58
    assert camp.prep_minutes(char, t) == 6 * 60 + (290 & 255) * 15


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-camp-') as first, tempfile.TemporaryDirectory(prefix='cok-camp-') as second:
        effects(folder, first)
        learn_row()
        member_keys(folder, first)
        memorize_list(folder, first)
        pending_list_first(folder, first)
        pending_lines(folder, first)
        signed_levels(folder, first)
        slot_lines(folder, first)
        prep_wrap(folder, first)
        stop_resting(folder, first)
        run = lambda root: (memorize_rest(folder, root), day_rest(folder, root), fixes(folder, root), menus(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS memorize, rest, fix, effects; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
