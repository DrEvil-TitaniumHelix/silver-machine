import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import camp, creation, effects, magic
from sm.titles.cok.camp import Kind
from sm.titles.cok.creation import F
from sm.titles.cok.faults import BindingRequired
from sm.titles.cok.menu import Game
from sm.titles.cok.records import Item

CURE, CAUSE, BLESS, HASTE, UNBOUND = 3, 4, 1, 48, 107
ENLARGE, REDUCE, FRIENDS, HAMMER, STRENGTH, DISPEL = 12, 13, 14, 28, 35, 46
KNIGHT, MULTI_FIGHTER_MAGE, KENDER, CLERIC_MAGE, CLERIC_FIGHTER_MAGE = 0, 2, 3, 4, 5
CASTABLE_CLASSES = ([3], [3], [3], [3], [0, 2, 3], [0, 2, 3])


class Table:
    def __init__(self, answers=()):
        self.answers, self.prompts, self.hashes, self.asked = list(answers), [], [], []

    def __call__(self, kind, options, game, **info):
        self.hashes.append(game.state_hash())
        self.prompts.append(info.get('prompt', ''))
        self.asked.append((kind, tuple(options), info))
        if kind == Kind.ACK.value: return 0
        answer = self.answers.pop(0)
        return options.index(answer(game) if callable(answer) else answer)


def fixture(folder, root, answers=()):
    table = Table(answers)
    game = Game(table, slot=None, directory=folder)
    game.roster_directory = root
    creation.load_game(game, 'A')
    game.s.mode = 4
    for char in game.s.party:
        char.b[F['memorized']:F['memorized'] + 58] = bytes(58)
    game.s.seed = 0x1234
    return game, table


def memorize(char, *spells):
    char.b[F['memorized']:F['memorized'] + len(spells)] = bytes(spells)


def copies(char, spell):
    return sum(1 for value in char.b[F['memorized']:F['memorized'] + 58] if value == spell)


def rolls(seed, *sides):
    result = []
    for count in sides:
        seed = (seed * 0x08088405 + 1) & 0xFFFFFFFF
        result.append((seed >> 16) % count + 1)
    return result


def check_table(game):
    layout = json.loads(Path(magic.__file__).with_name('tables.json').read_text(encoding='utf-8'))['tables']
    rows = magic.table()
    assert len(rows) == 107 and [row.id for row in rows] == list(range(1, 108))
    raw = b''.join(bytes((row.cast_class & 255, row.level & 255, *row[4:])) for row in rows)
    assert hashlib.sha256(raw).hexdigest() == layout['spellTbl']['sha256']
    assert all(rows[i].name for i in (0, 2, 41, 70))
    image = bytes(magic.rules.tables().image)
    at = image.index(bytes((9,)) + b'1st Level')
    assert image.count(bytes((9,)) + b'1st Level') == 1 and all(image[at + 41 * k] == 9 for k in range(9))
    assert image[at - 41:at - 41 + 8] == bytes((7,)) + b'Special' and not any(image[at - 33:at])


def check_castable(game):
    for char, expected in zip(game.s.party, CASTABLE_CLASSES):
        kinds = sorted({row.cast_class for row in magic.table() if magic.can_cast(char, row.id)})
        assert kinds == expected, (kinds, expected)
    cleric = game.s.party[CLERIC_MAGE]
    memorize(cleric, 8, CURE, 3 + 128, CURE, HASTE)
    order = magic.castable(cleric)
    assert order == [(8, 1), (CURE, 2), (HASTE, 1)], order
    memorize(cleric, CURE + 128, HASTE + 128, 8 + 128, CURE + 128, 101 + 128, 128)
    assert magic.castable(cleric, pending=True) == [(101, 1), (CURE, 2), (8, 1), (HASTE, 1)]
    memorize(cleric, 0, 0, 0, 0, 0, 0)


def cure(folder, root, deity):
    game, table = fixture(folder, root)
    caster, target = game.s.party[CLERIC_MAGE], game.s.party[KNIGHT]
    caster.b[F['deity']] = deity
    memorize(caster, CURE, CURE)
    target.b[F['hp']] = 3
    assert magic.cast(game, caster, CURE, target)
    sides = (8, 8) if deity == 4 else (8,)
    amount = sum(rolls(0x1234, *sides))
    assert target.b[F['hp']] == min(3 + amount, target.b[F['hp_max']]), (target.b[F['hp']], amount)
    assert copies(caster, CURE) == 1
    assert any('casts' in text for text in table.prompts) and any('healed' in text for text in table.prompts)
    return table.hashes


def refusals(folder, root):
    game, table = fixture(folder, root, ['No', 'Yes'])
    party = game.s.party
    wizard, knight, kender = party[CLERIC_MAGE], party[KNIGHT], party[KENDER]
    memorize(wizard, CAUSE)
    assert not magic.cast(game, wizard, CAUSE) and copies(wizard, CAUSE) == 1
    assert table.prompts[0].endswith("can't be cast here...") and table.prompts[1] == 'Lose it? '
    assert not magic.cast(game, wizard, CAUSE) and copies(wizard, CAUSE) == 0
    del table.prompts[:]
    assert not magic.cast(game, kender, CURE)
    assert table.prompts == [camp.name(kender) + ' has no spells memorized']
    del table.prompts[:]
    memorize(knight, CURE)
    assert not magic.can_cast(knight, CURE) and not magic.cast(game, knight, CURE) and copies(knight, CURE) == 1
    assert table.prompts == [camp.name(knight) + ' has no spells memorized']
    del table.prompts[:]
    memorize(wizard, BLESS)
    assert not magic.cast(game, wizard, CURE) and table.prompts == [] and copies(wizard, BLESS) == 1
    game.s.r0[magic.ANTI_MAGIC_CELL] = 1
    assert not magic.cast(game, wizard, BLESS) and table.prompts == [camp.name(wizard) + ' cannot cast spells in this area']
    assert copies(wizard, BLESS) == 1
    game.s.r0[magic.ANTI_MAGIC_CELL] = 0
    del table.prompts[:]
    wizard.b[F['status']] = 1
    assert not magic.cast(game, wizard, BLESS) and table.prompts == [camp.name(wizard) + ' is in no condition to cast any spells']
    return table.hashes


def bless(folder, root):
    game, table = fixture(folder, root)
    party = game.s.party
    caster = party[CLERIC_MAGE]
    memorize(caster, BLESS, BLESS)
    level = magic.caster_level(game, caster, BLESS)
    before = [len(char.effects) for char in party]
    party[KNIGHT].b[F['magic_resistance']] = 100
    assert magic.cast(game, caster, BLESS) and copies(caster, BLESS) == 1
    assert len(party[KNIGHT].effects) == before[KNIGHT], 'magic resistance stops the record'
    assert any(text.endswith('is Unaffected') for text in table.prompts)
    for index, char in enumerate(party):
        if index != KNIGHT:
            effect = char.effects[-1]
            assert (effect[0], effect[1] | effect[2] << 8, effect[3], effect[4]) == (BLESS, 6, level, 0), (index, list(effect))
            assert len(char.effects) == before[index] + 1
    party[KNIGHT].b[F['magic_resistance']] = 0
    assert magic.cast(game, caster, BLESS) and all(sum(e[0] == BLESS for e in c.effects) == 1 for c in party)
    return table.hashes


def target_and_faults(folder, root):
    game, table = fixture(folder, root)
    caster, target = game.s.party[CLERIC_MAGE], game.s.party[1]
    table.answers = [camp.name(target), creation.EXIT]
    memorize(caster, CURE, UNBOUND)
    target.b[F['hp']] = 1
    assert magic.cast(game, caster, CURE) and target.b[F['hp']] > 1 and copies(caster, CURE) == 0
    memorize(caster, CURE, UNBOUND)
    assert not magic.cast(game, caster, CURE) and copies(caster, CURE) == 1
    bound = magic.HANDLERS.pop(UNBOUND)
    try:
        magic.cast(game, caster, UNBOUND)
    except BindingRequired:
        pass
    else:
        raise AssertionError('unbound spell did not fault')
    finally: magic.HANDLERS[UNBOUND] = bound
    assert copies(caster, UNBOUND) == 1
    return table.hashes


def strength_now(char):
    return char.b[F['abilities'] + 1], char.b[F['strength_extra']]


def expected_enlarge(game, caster):
    level = caster.b[F['levels'] + 5] - (game.s.r0[0x1F8 + caster.b[F['robe_order']]] == 0)
    return level, {1: (18, 0), 2: (18, 1)}[level]


def camp_cast_and_rest(folder, root):
    game, table = fixture(folder, root)
    party = game.s.party
    mage, fighter = party[CLERIC_MAGE], party[KENDER]
    memorize(mage, ENLARGE, BLESS)
    start, base_effects = strength_now(fighter), [len(char.effects) for char in party]
    level, (value, extra) = expected_enlarge(game, mage)

    def before_rest(game):
        assert strength_now(fighter) == (value, extra), strength_now(fighter)
        node = fighter.effects[-2]
        assert (node[0], node[1] | node[2] << 8, node[3], node[4]) == (ENLARGE, 10 * level, extra + 1, 1), list(node)
        assert fighter.effects[-1][0] == BLESS and (fighter.effects[-1][1] | fighter.effects[-1][2] << 8) == 6
        assert copies(mage, ENLARGE) == copies(mage, BLESS) == 0
        return 'Rest'

    def after_rest(game):
        assert strength_now(fighter) == start, strength_now(fighter)
        assert [len(char.effects) for char in party] == base_effects, 'Enlarge and Bless have run out'
        return creation.EXIT

    enlarge, bless = magic.spell(ENLARGE).name, magic.spell(BLESS).name
    table.answers = ['Magic', *['char-down'] * CLERIC_MAGE, 'Cast', enlarge, camp.name(fighter), bless, before_rest, 'Hours', 'Add', 'Rest', after_rest, creation.EXIT]
    camp.run(game)
    assert any(text.endswith('is stronger') for text in table.prompts) and any(text.endswith('is Blessed') for text in table.prompts)
    return table.hashes


def more_spells(folder, root):
    game, table = fixture(folder, root)
    party, s = game.s.party, game.s
    caster, target = party[CLERIC_MAGE], party[KENDER]
    memorize(caster, STRENGTH, HASTE, DISPEL, REDUCE, FRIENDS, HAMMER)
    level = magic.caster_level(game, caster, STRENGTH)

    s.seed = 0x1234
    assert magic.cast(game, caster, STRENGTH, target)
    node = target.effects[-1]
    assert (node[0], node[3], node[1] | node[2] << 8) == (38, rolls(0x1234, 6, 8)[1] + 100, 60 * level), list(node)
    target.effects.pop()
    effects.recalc_ability(game, target, effects.STR)

    held = [len(char.effects) for char in party]
    assert magic.cast(game, caster, HASTE)
    hasted = [i for i, char in enumerate(party) if effects.has_effect(char, 39) is not None]
    assert hasted == list(range(magic.caster_level(game, caster, HASTE))), hasted
    for index in hasted: del party[index].effects[held[index]:]

    s.seed = 0x4321
    effects.add_effect(target, 5, 30, 0, False)
    assert magic.cast(game, caster, DISPEL, target)
    assert (effects.has_effect(target, 5) is None) == (rolls(0x4321, 100)[0] <= 50 + 5 * magic.caster_level(game, caster, DISPEL))
    target.effects[:] = [e for e in target.effects if e[0] != 5]

    s.seed = 0x5555
    target.b[F['saves'] + 4] = 21
    effects.add_effect(target, ENLARGE, 30, 1, True)
    assert magic.cast(game, caster, REDUCE, target)
    assert (effects.has_effect(target, ENLARGE) is None) == (rolls(0x5555, 20)[0] != 20)
    target.effects[:] = [e for e in target.effects if e[0] != ENLARGE]

    charisma = caster.b[F['abilities'] + 11]
    assert magic.cast(game, caster, FRIENDS)
    node = effects.has_effect(caster, FRIENDS)
    assert node is not None and caster.b[F['abilities'] + 11] == charisma + node[3], list(node)

    before = len(caster.items)
    assert magic.cast(game, caster, HAMMER) and len(caster.items) == before + 1
    hammer = caster.items[-1]
    assert hammer[effects.I['type']] == 6 and hammer[effects.I['name_ids'] + 2] == 121 and not hammer[effects.I['readied']]
    return table.hashes


def scroll(char, spells, count=100, flag=0x20):
    item = Item()
    item.set('type', 39)
    item.set('unidentified', flag)
    item.set('name_ids', bytes((count, 0, 0)))
    item.set('powers', bytes(spells) + bytes(3 - len(spells)))
    char.items.append(item.data)
    return item.data


def known(char, spell_id):
    return char.b[F['known_spells'] + spell_id - 1]


def unknown_mage_spell(char):
    return next(row.id for row in magic.table() if row.cast_class == 3 and row.level == 1 and row.name and not known(char, row.id))


def scribing(folder, root):
    game, table = fixture(folder, root)
    mage = game.s.party[CLERIC_MAGE]
    spell_id = unknown_mage_spell(mage)
    raw = scroll(mage, [spell_id])
    label = '  ' + magic.spell(spell_id).name
    at = effects.I['powers']

    def before_rest(game):
        assert raw[at] == spell_id | 0x80 and not known(mage, spell_id), list(raw[at:at + 3])
        assert magic.scribed_levels(mage) == (magic.spell(spell_id).level, magic.spell(spell_id).level)
        return 'Rest'

    def after_rest(game):
        assert known(mage, spell_id) == 1 and not any(item is raw for item in mage.items), 'the spell is learned and the scroll used up'
        return creation.EXIT

    cell = lambda offset: game.s.r0[camp.CLOCK_CELL + offset]
    clock = lambda: cell(1) + 10 * cell(2) + 60 * cell(3) + 1440 * cell(4)
    started = clock()
    table.answers = ['Magic', *['char-down'] * CLERIC_MAGE, 'Scribe', label, creation.EXIT, creation.EXIT, 'Yes', before_rest, 'Rest', after_rest, creation.EXIT]
    camp.run(game)
    assert clock() - started == 255, (clock(), started)
    assert any(text.endswith('has scribed ' + magic.spell(spell_id).name) for text in table.prompts)
    hashes = list(table.hashes)

    game, table = fixture(folder, root)
    party = game.s.party
    mage = party[CLERIC_MAGE]
    magic.scribe(game, mage)
    assert table.prompts == [camp.name(mage) + ' has no copyable scrolls'], table.prompts
    del table.prompts[:]

    known_id = next(row.id for row in magic.table() if row.cast_class == 3 and known(mage, row.id))
    table.answers = ['  ' + magic.spell(known_id).name, creation.EXIT]
    first = scroll(mage, [known_id])
    magic.scribe(game, mage)
    assert 'You already know that spell' in table.prompts and first[at] == known_id
    mage.items.pop()
    del table.prompts[:]

    too_high = next(row.id for row in magic.table() if row.cast_class == 0 and row.level == 3 and not known(mage, row.id))
    assert camp.slot_count(mage, 0, 3) == 0
    table.answers = ['  ' + magic.spell(too_high).name, creation.EXIT]
    first = scroll(mage, [too_high])
    magic.scribe(game, mage)
    assert 'You can not scribe that spell.' in table.prompts and first[at] == too_high
    mage.items.pop()
    del table.prompts[:]

    spell_id = unknown_mage_spell(mage)
    name = magic.spell(spell_id).name
    table.answers = ['  ' + name, ' *' + name, creation.EXIT, creation.EXIT, 'No']
    first = scroll(mage, [spell_id])
    magic.scribe(game, mage)
    assert 'You are already scibing that spell' in table.prompts and first[at] == spell_id, 'No clears the mark'
    mage.items.pop()

    game, table = fixture(folder, root)
    party, mage = game.s.party, game.s.party[CLERIC_MAGE]
    left = scroll(mage, [spell_id])
    table.answers = ['Magic', *['char-down'] * CLERIC_MAGE, 'Scribe', '  ' + name, creation.EXIT, creation.EXIT, 'Yes', creation.EXIT, creation.EXIT]
    camp.run(game)
    assert left[at] == spell_id, 'leaving camp clears the mark'
    mage.items.pop()

    other = next(row.id for row in magic.table() if row.cast_class == 3 and row.level == 1 and row.name and row.id != spell_id and not known(mage, row.id))
    two = scroll(mage, [spell_id | 0x80, other], count=101)
    assert magic.finish_scribe(game, mage, False)[1] and any(item is two for item in mage.items), 'a scroll with a spell left stays'
    assert two[at] == 0 and two[at + 1] == other and two[effects.I['name_ids']] == 100

    table.prompts[:] = []
    kender = party[KENDER]
    scroll(kender, [spell_id])
    magic.scribe(game, kender)
    assert table.prompts == [camp.name(kender) + ' has no copyable scrolls'], 'a character with no robe order reads no scrolls'
    return hashes + table.hashes


def check_scribe_pending_list(folder, root):
    game, table = fixture(folder, root)
    mage = game.s.party[CLERIC_MAGE]
    spell_id = unknown_mage_spell(mage)
    name = magic.spell(spell_id).name
    scroll(mage, [spell_id | 0x80])
    table.answers = [creation.EXIT, 'Yes']
    magic.scribe(game, mage)
    (kind, options, info), (kind2, options2, info2) = table.asked
    assert (kind, options, info['prompt'], info['title'], info['lines']) == (Kind.SPELL.value, (creation.EXIT,), '', 'to Scribe', (' *' + name,)), table.asked[0]
    assert (kind2, options2, info2['prompt']) == (Kind.CONFIRM.value, ('Yes', 'No'), 'Scribe These Spells? '), table.asked[1]
    del table.asked[:]
    table.answers = [creation.EXIT, 'No', creation.EXIT, creation.EXIT, 'Yes']
    scroll(mage, [next(row.id for row in magic.table() if row.cast_class == 3 and row.level == 1 and row.name and row.id != spell_id and not known(mage, row.id)) | 0x80])
    magic.scribe(game, mage)
    assert [(k, o) for k, o, _ in table.asked][:2] == [(Kind.SPELL.value, (creation.EXIT,)), (Kind.CONFIRM.value, ('Yes', 'No'))]
    assert len(table.asked) == 3 and table.asked[2][2]['prompt'] == 'Scribe', 'nothing pending after No: no closing list, no closing question'
    del table.asked[:]
    table.answers = ['  ' + name, creation.EXIT, creation.EXIT, 'Yes']
    magic.scribe(game, mage)
    assert [(k, o, i['prompt']) for k, o, i in table.asked][-2:] == [(Kind.SPELL.value, (creation.EXIT,), ''), (Kind.CONFIRM.value, ('Yes', 'No'), 'Scribe these spells? ')], table.asked
    return 'row 1'


def check_list_highlight(folder, root):
    start = lambda levels, kept=-1, **k: magic.list_start(levels, kept, **k)[0]
    assert start([1, 1, 1]) == 2 and start([1, 1, 2, 2, 3]) == 4 and start([1] * 20) == 16
    assert start([1] * 16 + [2] * 3) == 15
    assert magic.list_start([1, 1, 2], scroll=False)[1] == [None, 0, 1, None, 2]
    assert magic.list_start([2, 1, 1, 2], scroll=True)[1] == [None, 0, None, 1, 2, None, 3]
    assert magic.list_start([0, 1], scroll=True)[1] == [0, None, 1]
    assert start([1, 1], 2) == 1 and start([1, 1], 3) == 1
    assert start([1, 2], 2) == 0
    assert start([2, 2], 1) == 0 and start([1, 1, 1], 1) == 0
    game, table = fixture(folder, root)
    cleric = game.s.party[CLERIC_MAGE]
    three = [row.id for row in magic.table() if row.cast_class == 0 and row.level == 1 and row.id != CURE][:2] + [CURE]
    memorize(cleric, *sorted(three))
    offered = [held for held, _ in magic.castable(cleric)]
    target = camp.name(game.s.party[KNIGHT])
    table.answers = [magic.spell(CURE).name, target, creation.EXIT]
    game.s.party[KNIGHT].b[F['hp']] = 1
    magic.cast_menu(game, cleric)
    lists = [info for kind, _, info in table.asked if kind == Kind.SPELL.value]
    assert len(offered) == 3 and lists[0]['start'] == 2, lists[0]
    at = offered.index(CURE)
    assert lists[1]['start'] == min(at, 1), (lists[1], at)
    mage = game.s.party[CLERIC_MAGE]
    ids = [row.id for row in magic.table() if row.cast_class == 3 and row.level == 1 and row.name and not known(mage, row.id)][:2]
    scroll(mage, ids)
    del table.asked[:]
    table.answers = ['  ' + magic.spell(ids[0]).name, creation.EXIT, creation.EXIT, 'No']
    magic.scribe(game, mage)
    lists = [info for kind, _, info in table.asked if info.get('prompt') == 'Scribe']
    assert [info['start'] for info in lists] == [1, 0], lists
    return 'row 2'


def combat_rows(folder=None):
    from sm.titles.cok import combat, town
    from sm.titles.cok._combat_test import spell_fixture, audit
    witnesses=[]
    for ident in (9,20,47,51):
        game,b=spell_fixture(folder); caster=b.chars[4]
        b.record(4).update(x=19 if ident in (9,20) else 14,y=10)
        town.put(caster,'thac0',100)
        for c in b.chars[6:]: town.put(c,'hp',100); town.put(c,'hp_max',100)
        if ident==47: b.record(9).update(x=23,y=10)
        if ident==51: b.record(9).update(x=25,y=10)
        before=len(game.combat_log); level=magic.caster_level(game,caster,ident)
        assert b.cast(4,ident)
        events=game.combat_log[before:]
        damage=[e for e in events if e['event']=='damage']
        rolls=[e for e in events if e['event']=='dice']
        if ident==9:
            assert not rolls and len(damage)==1 and damage[0]['amount']==level
        elif ident==20:
            assert [e['sides'] for e in rolls]==[8,20]
            assert damage[0]['amount']==rolls[0]['result']+level
        else:
            assert [e['sides'] for e in rolls]==[6]*level+[20]*3
            total=sum(e['result'] for e in rolls[:level])
            assert {e['target'] for e in damage}==({6,7,8} if ident==47 else {6,7,9})
            for entry,save in zip(damage,rolls[level:]):
                target=b.chars[entry['target']]; natural=save['result']
                passed=natural==20 or natural!=1 and natural+town.field(target,'save_bonus',signed=True)>=town.field(target,'saves',4)
                assert entry['amount']==(total//2 if passed else total)
        witnesses.append(audit(game))
    game,b=spell_fixture(folder); caster=b.chars[4]
    game.player=lambda kind,options,*args,**info: next((k for k,v in enumerate(options) if '#4' in str(v)),0) if kind=='TARGET' else 0
    assert b.cast(4,28)
    hammer=caster.items[-1]
    assert hammer[effects.I['type']]==6 and hammer[effects.I['name_ids']+2]==121
    count=len(caster.items); b.trigger(19,4); assert len(caster.items)==count
    caster.items.remove(hammer); b.trigger(19,4); assert len(caster.items)==count
    node=effects.has_effect(caster,23)
    effects.age_effects(combat.EffectGame(b,'hammer expiry',4),caster,node[1]|node[2]<<8)
    assert not combat.has(caster,23) and len(caster.items)==count-1
    witnesses.append(audit(game))
    for seed,clears in ((0,True),(1,False)):
        game,b=spell_fixture(folder); caster=b.chars[4]; b.data['aim']=(30,15)
        b.cloud(caster,2); game.s.seed=seed; game.combat_log=[]
        facade=combat.EffectGame(b,'dispel cloud test',4)
        magic._dispel(facade,caster,[],magic.spell(46))
        rolls=[e for e in game.combat_log if e['event']=='dice']
        assert len(rolls)==1 and (rolls[0]['result']<=50)==clears
        assert (not b.data['clouds'])==clears and b.tile(30,15)==(23 if clears else 30)
        if not clears:
            assert b.data['clouds'][0]['spent']
            magic._dispel(facade,caster,[],magic.spell(46))
            assert len([e for e in game.combat_log if e['event']=='dice'])==1
        witnesses.append(audit(game))
    return tuple(witnesses)


def _texts(folder, ident, target=6):
    from sm.titles.cok._combat_test import spell_fixture
    game, b = spell_fixture(folder); seen = []; add = magic._add_with_message
    b.save = lambda *a, **k: False
    def spy(*a, **k): seen.append((a[8], a[7])); return add(*a, **k)
    magic._add_with_message = spy
    try: magic.HANDLERS[ident](combat_facade(b, 4), b.chars[4], [b.chars[target]], magic.spell(ident))
    finally: magic._add_with_message = add
    return seen


def combat_facade(b, i):
    from sm.titles.cok.combat import EffectGame
    return EffectGame(b, 'list 03 check', i)


def check_disease_on_remove(folder=None):
    assert ('is diseased', True) in _texts(folder, 40), _texts(folder, 40)


def check_blind_text(folder=None):
    assert [t for t, _ in _texts(folder, 38)] == ['is blind'], _texts(folder, 38)


def check_bestow_curse_text(folder=None):
    assert [t for t, _ in _texts(folder, 44)] == ['has been cursed!'], _texts(folder, 44)


def check_knock_bound(folder=None):
    assert 31 in magic.HANDLERS


def check_remove_curse_powered(folder=None):
    from sm.titles.cok._combat_test import spell_fixture
    game, b = spell_fixture(folder); c = b.chars[4]; I = magic.I
    raw = next(r for r in c.items); raw[I['cursed']] = 1; raw[I['readied']] = 1
    raw[I['powers'] + 1] = 23; raw[I['powers'] + 2] = 0x80
    effects.add_effect(c, 23, 0, 255, True); c.effects[-1][4] = 0
    for r in c.items:
        if r is not raw: r[I['cursed']] = 0
    magic.HANDLERS[43](combat_facade(b, 4), c, [c], magic.spell(43))
    assert effects.has_effect(c, 23) is None and not raw[I['readied']]


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-magic-') as first, tempfile.TemporaryDirectory(prefix='cok-magic-') as second:
        game, _ = fixture(folder, first)
        check_table(game)
        check_castable(game)
        run = lambda root: (cure(folder, root, 0), cure(folder, root, 4), refusals(folder, root), bless(folder, root), target_and_faults(folder, root),
                           camp_cast_and_rest(folder, root), more_spells(folder, root), scribing(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
        assert combat_rows(folder)==combat_rows(folder)
        check_scribe_pending_list(folder, first)
        check_list_highlight(folder, first)
    check_disease_on_remove(folder)
    check_blind_text(folder)
    check_bestow_curse_text(folder)
    check_knock_bound(folder)
    check_remove_curse_powered(folder)
    return 'PASS spell table, castable rule, cure, refusals, buffs, camp Cast through rest, scribe; %d decisions, replay equal' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
