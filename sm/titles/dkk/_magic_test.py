from types import SimpleNamespace
from unittest.mock import patch

from . import camp, effects, magic, magic_lists, magic_study, rules, shop
from .data import Assets
from .records import Character, Item, Spells

F, I = camp.F, magic_lists.I


def fixture():
    chars = [rules.character(bytes(Character()), spells=bytes(Spells())) for _ in range(2)]
    for char in chars:
        char.b[F['active']] = 1
        char.b[F['race']] = 6
        char.b[F['levels'] + 5] = 9
        char.b[F['robe_order']] = 1
        char.b[F['abilities'] + 3] = 15
        char.b[F['abilities'] + 5] = 15
    decisions, answers = [], []
    def ask(kind, options, **info):
        decisions.append((kind, options, info))
        return answers.pop(0) if answers else len(options) - 1
    cleared = []
    game = SimpleNamespace(assets=Assets(), s=SimpleNamespace(party=chars, r0=bytearray(1024), mode=0, g={}), ask=ask, vm=SimpleNamespace(clear_text=lambda: cleared.append(len(decisions)), cleared=cleared))
    return game, chars, decisions, answers


def scroll(char, values, mask=32, count=101, kind=39):
    raw = bytearray(Item.SIZE)
    raw[I['type']], raw[I['unidentified']], raw[I['name_ids']] = kind, mask, count
    raw[I['powers']:I['powers'] + 3] = bytes(values)
    char.items.append(raw)
    return char.items[-1]


def check_lists():
    game, (char, other), decisions, answers = fixture()
    base = F['memorized']
    char.b[base:base + 5] = bytes((47, 15, 143, 15, 175))
    char.b[base + 73] = 143
    assert magic.castable(game, char) == [(15, 2), (47, 1)]
    assert magic.castable(game, char, pending=True) == [(15, 2), (47, 1)]
    entries = magic.generate_list(game, char, 5)
    assert all(row.marked for row in entries)
    assert magic_lists.line(game, entries[0]).startswith(' *') and magic_lists.line(game, entries[0]).endswith(' (2)')
    char.b[F['levels']] = 1
    char.b[F['known_spells'] + 100] = 1
    char.b[base] = 101
    assert not magic.spell_known(game, char, 229)
    assert 101 in [row.ident for row in magic.generate_list(game, char, 1)]
    char.b[base + 73] = 229
    assert magic.spell_known(game, char, 101)
    assert 101 not in [row.ident for row in magic.generate_list(game, char, 1)]
    char.b[base:base + 74] = bytes(74)
    char.b[base:base + 3] = bytes((15, 19, 47))
    answers.append(0)
    ident, index, present = magic.spell_menu(game, char, 0, 1)
    assert (ident, index, present) == (15, 1, True)
    assert decisions[-1][2]['start'] == 2 and decisions[-1][2]['levels'] == (1, 1, 3)
    answers.append(1)
    magic.spell_menu(game, char, 0, 1, index)
    assert decisions[-1][2]['start'] == 0
    char.b[base:base + 3] = bytes((143, 147, 175))
    answers.append(0)
    ident, _, present = magic.spell_menu(game, char, 5, 5)
    assert ident == 47 and present
    assert decisions[-1][1] == ('Keep', 'Exit')
    assert decisions[-1][2]['prompt'] == game.assets.text('spellsOkQuery')
    assert len(decisions) == 3
    answers.append(1)
    assert magic.spell_menu(game, char, 5, 5)[0] == 0
    decisions.clear()
    assert magic.spell_menu(game, other, 0, 1) == (0, -1, False)
    assert not decisions
    raw = scroll(char, (47, 143, 15), mask=35)
    assert not magic.scroll_spells(game, char)
    effects.add_effect(char, 16, 10, 0, False)
    rows = magic.scroll_spells(game, char)
    assert [row.ident for row in rows] == [47, 15, 15]
    assert [row.marked for row in rows] == [False, True, False]
    assert all(row.item is raw for row in rows) and raw[I['unidentified']] == 32
    assert [row.ident for row in magic.scroll_spells(game, char, True)] == [15]
    raw[I['unidentified']] = 19
    assert not magic.scroll_spells(game, char)
    assert raw[I['unidentified']] == 19
    assert len(magic.generate_list(game, char, 2, item=raw)) == 3
    assert raw[I['unidentified']] == 16
    answers.append(1)
    magic.spell_menu(game, char, 2, 1, item=raw)
    assert decisions[-1][2]['levels'] == (3, 1, 1)
    assert decisions[-1][2]['start'] == 2
    char.b[F['robe_order']] = 2
    answers.append(0)
    magic.spell_menu(game, char, 3, 3)
    assert game.scroll is raw
    decisions.clear()
    magic.spell_menu(game, char, 6, 0)
    assert len(decisions) == 1 and decisions[0][1] == ('Exit',)
    plain = rules.character(bytes(Character()))
    plain.b[F['levels'] + 5], plain.b[F['abilities'] + 3] = 1, 15
    assert magic.can_cast(game, plain, 15)
    assert not magic.generate_list(game, plain, 0)
    assert not magic.generate_list(game, plain, 6)
    assert len(magic.generate_list(game, plain, 2, item=raw)) == 3
    assert magic.readable(raw) and not magic.readable(None)
    raw2 = scroll(char, (15, 143, 15), mask=0, count=101)
    assert magic.remove_scroll_spell(char, raw2, 15)
    assert list(raw2[I['powers']:I['powers'] + 3]) == [15, 143, 0]
    assert raw2[I['name_ids']] == 100 and any(x is raw2 for x in char.items)
    assert magic.remove_scroll_spell(char, raw2, 15)
    assert raw2[I['powers'] + 1] == 0 and not any(x is raw2 for x in char.items)
    before = bytes(raw)
    assert not magic.remove_scroll_spell(char, raw, 114) and bytes(raw) == before
    raw3 = scroll(char, (15, 0, 0), count=0)
    magic.remove_scroll_spell(char, raw3, 15)
    assert raw3[I['name_ids']] == 255 and any(x is raw3 for x in char.items)
    char.effects.clear()
    raw[I['unidentified']] = 7
    char.b[F['levels']] = 255
    base_items = SimpleNamespace(base_item=lambda kind: bytes((12,)) + bytes(15))
    with patch.object(rules, 'tables', return_value=base_items):
        magic.identify_scroll(game, char, raw)
        assert raw[I['unidentified']] == 7
        char.b[F['levels']] = 1
        magic.identify_scroll(game, char, raw)
        assert raw[I['unidentified']] == 0


def check_learn():
    game, (char, _), decisions, answers = fixture()
    table = bytearray(240)
    table[80:84] = bytes((15, 19, 0, 47))
    table[150] = 114
    table[160:163] = bytes((10, 18, 0))
    table[230] = 114
    slots = F['spell_slots'] + 24
    char.b[slots], char.b[slots + 7] = 1, 1
    char.b[F['known_spells'] + 18] = 1
    original = game.assets.table
    with patch.object(game.assets, 'table', side_effect=lambda name: bytes(table) if name == 'spellsByLevel' else original(name)):
        assert magic.learnable(game, char) == [15, 114]
        char.b[F['abilities'] + 3] = 1
        assert magic.learnable(game, char) == [15, 114]
        answers.append(1)
        assert magic.learn(game, char) == 114
        assert char.b[F['known_spells'] + 113] == 1
        assert 'Exit' not in decisions[-1][1] and decisions[-1][2]['start'] == 1
        for robe in (0, 2, 3):
            char.b[F['robe_order']] = robe
            assert magic.learnable(game, char) == [10, 18]
        char.b[slots:slots + 8] = bytes(8)
        before = len(decisions)
        assert magic.learn(game, char) == 0 and len(decisions) == before


def check_caster_and_target():
    game, (char, other), decisions, answers = fixture()
    effects.add_effect(char, 94, 10, 0, False)
    assert magic.caster_level(game, char, 47) == 8
    effects.add_effect(char, 78, 10, 0, False)
    assert magic.caster_level(game, char, 47) == 15
    assert magic.caster_level(game, char, 15) == 8
    game.using_item = True
    assert magic.caster_level(game, char, 47) == 6
    game.using_item = False
    char.effects.clear()
    char.b[F['levels'] + 5] = 255
    assert magic.caster_level(game, char, 15) == 255
    char.b[F['levels'] + 5] = 1
    char.b[F['levels'] + 4] = 128
    assert magic.caster_level(game, char, 15) == 128
    row = magic.spell(game, 3)
    answers.append(1)
    assert magic._camp_targets(game, char, row) == [other]
    assert decisions[-1][2]['start'] == 0
    answers.append(2)
    assert magic._camp_targets(game, char, row) is None
    assert decisions[-1][2]['start'] == 1
    answers.append(0)
    assert magic._camp_targets(game, char, row) == [char]
    assert decisions[-1][2]['start'] == 0
    game.noncombat_target = other
    magic.reset_target(game)
    assert game.noncombat_target is None


def check_heal_in_camp():
    game, chars, decisions, answers = fixture()
    char = chars[0]
    char.b[F['hp_max']], char.b[F['hp']] = 20, 5
    effects.add_effect(char, 33, 10, 0, False)
    with patch.object(magic, 'dice', lambda s, n, d: 1): magic._heal(game, None, [char], None)
    assert [d[2]['prompt'] for d in decisions] == [' ' + game.assets.text('isCuredText'), ' ' + game.assets.text('healedMessage')]
    assert all(d[2].get('timed') for d in decisions) and char.b[F['hp']] == 19
    info = decisions[-1][2]
    assert (info['creature_name'], info['creature_text'], info['creature_column'], info['creature_row'], info['creature_colour']) == ('', game.assets.text('healedMessage'), 1, 18, 11)
    game.s.g['no_border'], char.b[F['active']] = 1, 0
    magic._timed(game, char, game.assets.text('fullyHealedText'))
    assert (decisions[-1][2]['creature_row'], decisions[-1][2]['creature_colour'], decisions[-1][2]['prompt']) == (19, 12, ' ' + game.assets.text('fullyHealedText'))


def check_remove_curse():
    game, (char, _), decisions, answers = fixture()
    raw = scroll(char, (0, 8, 128))
    raw[I['cursed']], raw[I['readied']] = 1, 1
    effects.add_effect(char, 36, 10, 0, False)
    effects.add_effect(char, 43, 10, 0, False)
    effects.add_effect(char, 8, 0, 255, False)
    assert magic.remove_curse(game, char)
    assert effects.has_effect(char, 43) is None and effects.has_effect(char, 36) is not None
    assert raw[I['readied']] == 1 and effects.has_effect(char, 8) is not None
    assert [d[2]['prompt'] for d in decisions] == [' ' + game.assets.text('isCuredText'), ' ' + game.assets.text('uncursedText')]
    recalcs = []
    with patch.object(effects, 'recalc_ability', side_effect=lambda g, c, stat: recalcs.append(stat)):
        assert magic.remove_curse(game, char)
    assert recalcs == list(range(6))
    assert not game.handler_override_active and effects.has_effect(char, 8) is None
    assert raw[I['readied']] == 0 and raw[I['cursed']] == 1
    assert decisions[-1][2]['prompt'] == ' ' + game.assets.text('itemUncursedText')
    assert all(magic.handler(game, magic.spell(game, ident)) is magic._remove_curse for ident in (43, 89, 104))
    raw[I['cursed']] = 0
    before = len(decisions)
    assert not magic.remove_curse(game, char) and len(decisions) == before


def check_item_cast():
    game, (char, _), decisions, answers = fixture()
    char.b[F['memorized']] = 8
    effects.add_effect(char, 25, 10, 0, False)
    effects.add_effect(char, 25, 10, 0, False)
    raw = scroll(char, (2, 8, 0), mask=0, kind=0)
    raw[I['quantity']] = 3
    seen = []
    def cast(g, c, targets, row):
        seen.append((g.using_item, g.current_spell, magic.caster_level(g, c, row.id), targets))
        g.area_spell = True
    with patch.dict(magic.HANDLERS, {8: cast}), patch.object(magic, '_camp_targets', return_value=[char]), patch.object(shop, 'item_name', return_value='item') as named:
        assert magic.use_item(game, char, raw)
        assert seen == [(True, 8, 6, [char])]
        named.assert_called_once_with(game, raw)
        assert raw[I['quantity']] == 2 and raw[I['powers']] == 2
        assert char.b[F['memorized']] == 8 and effects.has_effect(char, 25) is None
        assert not game.using_item and game.current_spell == 0 and not game.area_spell
        assert len(decisions) == 1 and 'uses an item' in decisions[0][2]['prompt']
        raw[I['quantity']], raw[I['powers']] = 1, 1
        equal = bytearray(raw)
        char.items.append(equal)
        assert magic.use_item(game, char, raw)
        assert not any(item is raw for item in char.items) and any(item is equal for item in char.items)
        paper = scroll(char, (8, 0, 0), mask=0, count=100)
        answers.append(0)
        assert magic.use_item(game, char, paper)
        assert not any(item is paper for item in char.items) and char.b[F['memorized']] == 8
        decisions.clear()
        raw = scroll(char, (2, 15, 0), mask=0, kind=0)
        answers.extend((0, 1))
        assert not magic.use_item(game, char, raw)
        assert raw[I['powers']] == 2 and len(decisions) == 2
        assert decisions[-1][2]['start'] == 0 and decisions[-1][2]['prompt'] == game.assets.text('useItemPrompt')
        answers.extend((0, 0))
        assert magic.use_item(game, char, raw) and raw[I['powers']] == 1
        game.using_item = False
        char.b[F['memorized']] = 15
        answers.append(0)
        before = len(decisions)
        assert not magic.cast_in_camp(game, char, 15)
        assert char.b[F['memorized']] == 143 and len(decisions) == before + 1 and game.vm.cleared[-1] == before + 1
        assert decisions[-1][2]['start'] == 0
        char.b[F['memorized']] = 8
        assert magic.cast_in_camp(game, char, 8)
        assert char.b[F['memorized']] == 136 and seen[-1][:2] == (False, 8)
        raw[I['powers'] + 1] = 8
        with patch.dict(magic.HANDLERS, {8: lambda *args: (_ for _ in ()).throw(ValueError('failed'))}):
            try: magic.use_item(game, char, raw)
            except ValueError: pass
            else: assert False
        assert not game.using_item and game.current_spell == 0 and raw[I['powers']] == 1
    game, (char, _), decisions, answers = fixture()
    char.b[F['levels'] + 5], char.b[F['levels'] + 6] = 0, 10
    paper = scroll(char, (15, 0, 0), mask=0, count=100)
    answers.extend((0, 0))
    with patch.object(magic, 'dice', return_value=76) as roll:
        assert not magic.use_item(game, char, paper)
        assert roll.call_count == 1 and paper[I['powers']] == 15
    answers.append(0)
    with patch.object(magic, 'dice', return_value=75), patch.object(magic, 'cast_in_camp', return_value=True) as cast:
        assert magic.use_item(game, char, paper)
        assert cast.call_count == 1
    paper = scroll(char, (15, 0, 0), mask=0, count=100)
    calls = []
    game.battle = SimpleNamespace(index=lambda c: 0, end=lambda i: calls.append('end') or True,
                                 message=lambda text: calls.append(text), cast=lambda *a, **kw: calls.append('cast') or False)
    answers.append(0)
    with patch.object(magic, 'dice', return_value=76):
        assert magic.use_item(game, char, paper)
    assert calls == [' oops!', 'end'] and not any(item is paper for item in char.items)
    paper = scroll(char, (15, 0, 0), mask=0, count=100)
    answers.append(0)
    with patch.object(magic, 'dice', return_value=75):
        assert magic.use_item(game, char, paper)
    assert calls[-2:] == ['cast', 'end']
    game.battle = None
    paper = scroll(char, (15, 0, 0), mask=0, count=100)
    char.b[F['levels'] + 6] = 9
    answers.extend((0, 0))
    with patch.object(magic, 'dice', side_effect=AssertionError('unexpected roll')):
        assert magic.use_item(game, char, paper, done=True)
    assert not any(item is paper for item in char.items)


def check_study():
    game, (char, _), decisions, answers = fixture()
    paper = scroll(char, (15, 19, 0), mask=32, count=101)
    char.b[F['spell_slots'] + 24] = 1
    assert magic_study.mark_scribe(game, char, 15) == '' and paper[I['powers']] == 143
    assert magic_study.mark_scribe(game, char, 15) == 'alreadyScribingMessage'
    char.b[F['known_spells'] + 14] = 1
    assert magic_study.mark_scribe(game, char, 15) == 'alreadyKnowsMessage'
    char.b[F['known_spells'] + 14] = 0
    char.b[F['spell_slots'] + 24] = 0
    assert magic_study.mark_scribe(game, char, 19) == 'cannotScribeMessage'
    magic.reset_scribe(char)
    first = scroll(char, (15, 0, 0), kind=0)
    char.items.remove(first)
    char.items.insert(0, first)
    char.b[F['spell_slots'] + 24] = 1
    assert magic_study.mark_scribe(game, char, 15) == ''
    assert first[I['powers']] == 143 and paper[I['powers']] == 15
    magic.reset_scribe(char)
    assert first[I['powers']] == 143
    char.items.remove(first)
    answers.extend((0, 2, 0, 0))
    magic.scribe(game, char)
    assert paper[I['powers']] == 143
    assert [d[1] for d in decisions[-2:]] == [('Exit',), ('Yes', 'No')]
    decisions.clear()
    answers.extend((0, 0))
    magic.scribe(game, char)
    assert len(decisions) == 2 and decisions[-1][2]['start'] == 0
    answers.extend((0, 1, 2))
    magic.scribe(game, char)
    assert paper[I['powers']] == 15
    char.b[F['memorized']] = 143
    paper[I['powers']] = 143
    assert magic.prep_minutes(game, char) == 270 and char.b[F['preparation']] == 4
    char.b[F['active']] = 0
    assert magic.prep_minutes(game, char) == 255
    char.b[F['active']] = 1
    magic.reset_scribe(char)
    char.b[F['memorized']:F['memorized'] + 74] = bytes([242] * 74)
    level = magic.spell(game, 114).level
    assert magic.prep_minutes(game, char) == 360 + ((74 * level) & 255) * 15
    char.b[F['memorized']:F['memorized'] + 74] = bytes(74)
    paper[I['powers']:I['powers'] + 3] = bytes((143, 143, 147))
    char.b[F['active']] = 0
    assert magic.finish_scribe(game, char, False) == (1, True)
    assert char.b[F['known_spells'] + 14] == 1
    assert list(paper[I['powers']:I['powers'] + 3]) == [143, 0, 147]
    assert magic.finish_scribe(game, char, True) == (1, True)
    char.b[F['memorized']:F['memorized'] + 2] = bytes((143, 175))
    assert magic.finish_memorize(game, char, False) == (0, False)
    char.b[F['active']] = 1
    assert magic.finish_memorize(game, char, False) == (3, True)
    assert char.b[F['memorized']] == 15 and char.b[F['memorized'] + 1] == 175
    assert magic.finish_memorize(game, char, False, suppressed=True) == (0, False)
    before = bytes(char.b), bytes(paper)
    assert magic.finish_scribe(game, char, False, suppressed=True) == (0, False)
    assert magic.finish_scribe(game, char, True, suppressed=True) == (0, True)
    assert before == (bytes(char.b), bytes(paper))


def check_camp_resistance():
    game, (caster, target), decisions, answers = fixture()
    caster.b[F['levels']] = 9
    effects.add_effect(target, 59, 10, 0, False)
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert decisions[0][2]['timed'] == 1 and decisions[0][2]['spell'] == 8
    assert effects.has_effect(target, 10) is None
    assert decisions[-1][2]['prompt'] == ' ' + game.assets.text('unaffectedMessage')
    target.effects.clear()
    target.b[F['magic_resistance']] = 50
    rolls = []
    game.s.random = lambda sides: rolls.append(sides) or 0
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert rolls == [100] and effects.has_effect(target, 10) is None
    game.s.random = lambda sides: rolls.append(sides) or 99
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert effects.has_effect(target, 10) is not None and rolls == [100, 100]
    target.b[F['magic_resistance']] = 0
    target.effects.clear()
    effects.add_effect(target, 10, 0, 1, False)
    permanent = target.effects[0]
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert len(target.effects) == 2 and target.effects[0] is permanent
    target.effects.pop(0)
    timed = target.effects[0]
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert len(target.effects) == 1 and target.effects[0] is not timed
    target.effects.clear()
    game.s.r1, rolls[:] = bytearray(1024), []
    game.s.random = lambda sides: rolls.append(sides) or 0
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 80)
    assert rolls == [20] and effects.has_effect(target, 69) is not None
    target.effects.clear()
    effects.add_effect(target, 96, 0, 0, False)
    game.current_spell = 4
    row = magic.spell(game, 4)._replace(save_effect=0, range=0, duration=0, duration_per_level=0)
    magic._resolve(game, caster, [target], row, 1, False, 0, 0, '')
    assert effects.has_effect(target, row.effect) is None
    assert decisions[-1][2]['prompt'] == ' ' + game.assets.text('unaffectedMessage')


def check_camp_memo():
    game, (caster, target), decisions, answers = fixture()
    caster.b[F['levels']] = 9
    game.roll_memo = dict(effect=11, damage=3, element=4, dice_count=2)
    target.b[F['magic_resistance']] = 50
    rolls = []
    game.s.random = lambda sides: rolls.append(sides) or 0
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert rolls == [] and effects.has_effect(target, 10) is not None
    assert game.roll_memo == dict(effect=10, damage=3, element=0, dice_count=2)
    target.effects.clear()
    game.roll_memo['damage'] = 0
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 8)
    assert rolls == [100] and effects.has_effect(target, 10) is None
    assert game.roll_memo == dict(effect=0, damage=0, element=0, dice_count=2)
    assert magic._damage_dice(game, 0, 6) == 0 and game.roll_memo['dice_count'] == 0
    effects.add_effect(target, 15, 10, 0, True)
    target.b[F['hp']], target.b[F['hp_max']] = 9, 9
    effects.remove_effect(game, target, 15)
    assert target.b[F['hp']] == 8 and game.roll_memo['damage'] == 1
    game.current_spell, game.area_spell = 15, True
    roll = effects.camp_roll(game, damage=7)
    assert (roll.spell, roll.multi_target, roll.damage, roll.effect) == (15, 1, 7, 0)
    game.current_spell, game.area_spell = 0, False
    target.effects.clear()
    effects.add_effect(target, 20, 10, 0, False)
    target.b[F['save_bonus']], target.b[F['saves'] + 4] = 0, 12
    game.s.random = lambda sides: 9
    game.roll_memo = dict(effect=0, damage=8, element=1, dice_count=0)
    assert magic._save(game, target, 4)
    assert game.roll_memo == dict(effect=0, damage=4, element=1, dice_count=0)
    game.roll_memo = dict(effect=0, damage=8, element=0, dice_count=0)
    assert not magic._save(game, target, 4) and game.roll_memo['damage'] == 8
    target.effects.clear()
    effects.add_effect(target, 50, 10, 0, False)
    game.roll_memo = dict(effect=0, damage=8, element=1, dice_count=0)
    magic._save(game, target, 4)
    assert game.roll_memo['damage'] == 8


def check_revival():
    from . import temple, town
    game, (caster, target), decisions, answers = fixture()
    game.vm.service = lambda unit, name, *args: town.service(game, unit, name, *args)
    r = rules.record(target)
    r.set('status', 6)
    r.set('active', 0)
    r.set('hp', 0)
    r.set('hp_max', 30)
    r.set('hp_rolled', 20)
    target.b[F['abilities'] + 8:F['abilities'] + 10] = bytes((16, 16))
    effects.add_effect(target, 55, 0, 255, True)
    effects.add_effect(target, 55, 0, 255, False)
    effects.add_effect(target, 22, 50, 255, False)
    memory = bytes(target.b[F['memorized']:F['memorized'] + 74])
    locks = []
    original = effects.remove_effect
    def remove(game, char, ident, node=None):
        locks.append((ident, getattr(game, 'effect_busy', False)))
        return original(game, char, ident, node)
    with patch.object(effects, 'remove_effect', remove): temple.cure(game, target, 7)
    assert locks[0] == (55, True) and not game.effect_busy
    assert (r.get('status'), r.get('active'), r.get('hp')) == (0, 1, 1)
    assert target.b[F['abilities'] + 8:F['abilities'] + 10] == bytes((15, 15))
    assert r.get('hp_max') == 29 and [e[0] for e in target.effects] == [55, 22]
    assert decisions[-1][2]['prompt'] == ' ' + game.assets.text('raisedText')
    assert game.current_spell == 75 and game.spell_targets == [target]
    assert bytes(target.b[F['memorized']:F['memorized'] + 74]) == memory
    game.current_spell = 17
    game.using_item = True
    effects.add_effect(target, 43, 0, 1, False)
    answers.append(0)
    temple.cure(game, target, 8)
    assert game.current_spell == 17 and game.using_item and not effects.has(target, 43)
    for ident in (7, 75):
        for race in (0, 1, 2, 6, 127, 128, 255):
            for status in (0, 1, 6, 7):
                r.set('race', race)
                r.set('status', status)
                r.set('active', 0)
                r.set('hp', 0)
                target.b[F['abilities'] + 8:F['abilities'] + 10] = bytes((16, 16))
                decisions.clear()
                magic.handler(game, magic.spell(game, ident))(game, caster, [target], magic.spell(game, ident))
                allowed = (status in (1, 6) and race not in (0, 1)) if ident == 75 else status == 6 and 1 < race < 128
                assert bool(decisions) == allowed, (ident, race, status)
                assert r.get('status') == (0 if allowed else status)
                if allowed: assert r.get('hp') == (1 if ident == 75 else r.get('hp_max'))
    r.set('race', 6)
    r.set('status', 6)
    target.b[F['abilities'] + 8] = 0
    decisions.clear()
    for ident in (7, 75): magic.handler(game, magic.spell(game, ident))(game, caster, [target], magic.spell(game, ident))
    assert not decisions and r.get('status') == 6
    target.b[F['abilities'] + 8] = 16
    game.effect_busy = True
    magic.temple_spell(game, target, 75)
    assert game.effect_busy
    r.set('status', 6)
    game.effect_busy = False
    locks.clear()
    with patch.object(effects, 'remove_effect', remove):
        magic.handler(game, magic.spell(game, 7))(game, caster, [target], magic.spell(game, 7))
    assert locks[0] == (55, False)
    game.using_item = False
    for ident in (7, 75):
        r.set('status', 6)
        r.set('active', 0)
        caster.b[F['memorized']] = ident
        answers.extend((0, 1))
        assert magic.cast_in_camp(game, caster, ident)
        assert r.get('status') == 0 and caster.b[F['memorized']] == ident | 128
        assert game.current_spell == 0 and not game.area_spell


def check_stone_to_flesh():
    from ._combat_test import action_fixture
    for blocked in (False, True):
        game, battle = action_fixture()
        caster, target, other = battle.chars
        target.b[F['status']], target.b[F['active']], target.b[F['hp']] = 7, 0, 0
        battle.record(1)['size'] = 0
        battle.record_body(1, 23)
        battle.record_body(2, 24)
        battle.put_tile(11, 10, 31)
        battle.data['aim'] = (18, 15)
        if blocked: battle.record(0).update(x=11, y=10)
        events = []
        restore, scroll_view = battle.restore_body, battle.scroll
        def restore_body(index):
            assert (target.b[F['status']], target.b[F['active']], target.b[F['hp']]) == (0, 1, 1)
            assert events == [('message', 'TEST ' + game.assets.text('noLongerStatusText'))]
            restore(index)
            events.append(('body',))
        def scroll_viewport(*args):
            events.append(('scroll', args))
            return scroll_view(*args)
        battle.restore_body, battle.scroll = restore_body, scroll_viewport
        battle.message = lambda text: events.append(('message', text))
        row = magic.spell(game, 66)
        with patch.object(magic, '_resolve') as resolve:
            magic.handler(game, row)(game, caster, [target], row)
            resolve.assert_called_once_with(game, caster, [target], row, 0, False, 0, 0, '')
        assert battle.record(1)['size'] == (0 if blocked else 1)
        assert battle.data['downed_count'] == 1 and battle.data['downed_who'][:2] == [2, 2]
        assert battle.tile(11, 10) == 23
        assert events[1:] == [('body',)] + ([] if blocked else [('scroll', (18, 15, 0, 8))])
        events.clear()
        magic.handler(game, row)(game, caster, [target], row)
        assert not events and battle.data['downed_count'] == 1
    game, (caster, target), decisions, answers = fixture()
    target.b[F['status']], target.b[F['active']], target.b[F['hp']] = 7, 0, 0
    caster.b[F['memorized']] = 66
    answers.extend((0, 1))
    assert magic.cast_in_camp(game, caster, 66)
    assert (target.b[F['status']], target.b[F['active']], target.b[F['hp']]) == (0, 1, 1)
    assert decisions[-1][2]['prompt'] == ' ' + game.assets.text('noLongerStatusText')
    assert caster.b[F['memorized']] == 194 and game.current_spell == 0


def check_restoration():
    from . import temple, town
    game, (_, target), decisions, answers = fixture()
    game.vm.service = lambda unit, name, *args: town.service(game, unit, name, *args)
    r = rules.record(target)
    r.set('levels', bytes((2, 0, 2, 0, 0, 0, 0, 0)))
    r.set('former_levels', bytes((3, 0, 3, 0, 0, 0, 0, 0)))
    r.set('hp', 250)
    r.set('hp_max', 40)
    r.set('old_hp_max', 60)
    r.set('hp_rolled', 30)
    r.set('experience', 1000)
    r.set('old_experience', 99999)
    target.b[F['abilities'] + 9] = 16
    with patch.object(rules.Tables, 'level_xp', lambda self, row, level: 1000000 if (row, level) == (5, 14) else 2000):
        temple.cure(game, target, 10)
        assert list(r.get('levels')) == [2, 0, 3, 0, 0, 0, 0, 0]
        assert (r.get('hp'), r.get('hp_max'), r.get('hp_rolled')) == (4, 50, 39)
        assert r.get('experience') == 2000 and r.get('level_up_ready') == 1
        assert game.current_spell == 17 and game.spell_targets == [target] and not decisions
        magic.temple_spell(game, target, 17)
        assert list(r.get('levels')) == [3, 0, 3, 0, 0, 0, 0, 0]
        assert (r.get('hp'), r.get('hp_max'), r.get('hp_rolled')) == (14, 60, 48)
        assert r.get('experience') == 99999
        r.set('experience', 0xFFFFFFFF)
        r.set('level_up_ready', 1)
        before = bytes(target.b)
        magic.temple_spell(game, target, 17)
        assert r.get('level_up_ready') == 0 and r.get('experience') == 0xFFFFFFFF
        assert target.b[:F['level_up_ready']] == before[:F['level_up_ready']]
        r.set('levels', bytes((3, 0, 0, 0, 0, 0, 0, 0)))
        r.set('former_levels', bytes((3, 0, 1, 0, 0, 0, 0, 0)))
        r.set('old_hp_max', 0)
        magic.temple_spell(game, target, 17)
        assert list(r.get('levels')) == [3, 0, 1, 0, 0, 0, 0, 0]
        r.set('levels', bytes((3, 0, 3, 0, 0, 0, 0, 0)))
        r.set('former_levels', bytes((3, 0, 3, 0, 0, 0, 0, 0)))
        r.set('old_hp_max', 60)
        for constitution, expected in ((3, 41), (6, 40)):
            r.set('levels', bytes((2, 0, 2, 0, 0, 0, 0, 0)))
            r.set('hp_max', 40)
            r.set('hp_rolled', 30)
            target.b[F['abilities'] + 9] = constitution
            magic.temple_spell(game, target, 17)
            assert r.get('hp_rolled') == expected
        r.set('former_levels', bytes(r.get('levels')))
        target.b[F['former_levels']] += 1
        r.set('hp_max', 70)
        r.set('hp_rolled', 60)
        r.set('hp', 5)
        r.set('experience', 0xFFFFFFFF)
        r.set('old_experience', 10000)
        magic.temple_spell(game, target, 17)
        assert (r.get('hp'), r.get('hp_max'), r.get('hp_rolled')) == (5, 70, 60)
        assert r.get('experience') == 10000
        limit = rules.tables().u8('firstFixedHpLevel', 2)
        r.set('levels', bytes((0, 0, limit - 1, 0, 0, 0, 0, 0)))
        r.set('former_levels', bytes((0, 0, limit, 0, 0, 0, 0, 0)))
        r.set('hp_max', 40)
        r.set('old_hp_max', 50)
        r.set('hp_rolled', 30)
        r.set('experience', 10000)
        r.set('old_experience', 0xFFFFFFFF)
        target.b[F['abilities'] + 9] = 19
        magic.temple_spell(game, target, 17)
        assert r.get('hp_rolled') == 40 and r.get('experience') == 2000


def check_fireball():
    from ._combat_test import action_fixture
    for ident, count in ((47, 8), (64, 7), (108, 8)):
        for dungeon in (False, True):
            game, battle = action_fixture()
            caster, target, other = battle.chars
            caster.b[F['levels'] + 5] = 8
            game.vm.is3d = lambda: dungeon
            battle.data.update(aim=(11, 10), current_spell=ident)
            del battle.trigger
            calls = []
            def random(sides):
                calls.append(sides)
                return 0 if sides == 20 else sides - 1
            game.s.random = random
            handed = [target]
            magic.handler(game, magic.spell(game, ident))(game, caster, handed, magic.spell(game, ident))
            assert len(handed) == (1 if dungeon else 3)
            damage = count * 6 + (count if ident == 108 else 0)
            assert [c.b[F['hp']] for c in battle.chars] == ([250, 250 - damage, 250] if dungeon else [250 - damage] * 3)
            assert calls == ([3] if ident == 64 else []) + [6] * count + [20] * (1 if dungeon else 3)
            assert battle.data['roll']['dice_count'] == count and battle.data['roll']['element'] == 0
            assert battle.data['view'] == (8, 7) and battle.data['multi_target'] == 1
    for level, ident, damage in ((43, 47, 2), (43, 108, 45), (0, 47, 0)):
        game, battle = action_fixture()
        caster, target, _ = battle.chars
        caster.b[F['levels'] + 5] = level or 1
        caster.b[F['robe_order']] = int(not level)
        game.s.r0[0x1F9] = 0
        game.vm.is3d = lambda: True
        game.s.random = lambda sides: 0 if sides == 20 else sides - 1
        battle.data.update(aim=(11, 10), current_spell=ident)
        magic.handler(game, magic.spell(game, ident))(game, caster, [target], magic.spell(game, ident))
        assert target.b[F['hp']] == 250 - damage and battle.data['roll']['dice_count'] == level, (level, ident, target.b[F['hp']], battle.data['roll'])
    game, battle = action_fixture()
    caster = battle.chars[0]
    row = magic.spell(game, 47)
    for targets, damage, expected in (([], 7, 9), ([None], 7, 0), ([], 0, 0)):
        magic._resolve(game, caster, targets, row, 0, False, damage, 9, '')
        assert battle.data['roll']['element'] == expected
    for succeeds in (False, True):
        game, battle = action_fixture()
        caster, target, _ = battle.chars
        caster = game.s.party[0] = rules.character(bytes(caster.b), spells=bytes(Spells()))
        del battle.trigger
        game.vm.is3d = lambda: True
        calls = []
        game.s.random = lambda sides: calls.append(sides) or (0 if sides == 20 else sides - 1)
        caster.b[F['memorized']] = 47
        effects.add_effect(caster, 78, 0, 2, False)
        effects.add_effect(caster, 78, 0, 3, False)
        first, second = caster.effects
        aimed = []
        def select(index, row, using_item=False, ai=False):
            aimed.append((index, row.id, using_item, ai))
            battle.data['aim'] = (11, 10)
            return [1] if succeeds else None
        battle.spell_targets = select
        battle.trigger(14, 0)
        assert aimed == [(0, 47, False, True)]
        assert caster.b[F['memorized']] == 175
        assert target.b[F['hp']] == (160 if succeeds else 250)
        assert len(caster.effects) == (1 if succeeds else 2)
        assert caster.effects[-1] is second
        if not succeeds: assert caster.effects[0] is first
        assert calls[-16:] == [6] * 15 + [20] and calls[:-16].count(1) == 100 and set(calls[:-16]) == {1, 4} if succeeds else calls == []
        if succeeds: assert battle.data['roll']['dice_count'] == 15 and battle.data['roll']['element'] == 0
        assert not battle.data.get('current_spell', 0)
        assert battle.record(0)['initiative'] == 6
        assert any(event['event'] == ('cast' if succeeds else 'spell aborted') for event in game.combat_log)
    game, battle = action_fixture()
    caster, bearer, _ = battle.chars
    effects.add_effect(bearer, 78, 0, 1, False)
    effects.add_effect(bearer, 78, 0, 2, False)
    first, second = bearer.effects
    with patch.object(battle, 'cast', return_value=True) as cast:
        effects.call_handler(game, bearer, 78, second, True)
        cast.assert_called_once_with(0, 47, using_item=False, ai=True)
    assert len(bearer.effects) == 1 and bearer.effects[0] is second


def check_fight_spells():
    from ._combat_test import action_fixture
    def setup(ident, level=8, roll=0):
        game, battle = action_fixture()
        del battle.trigger
        caster, target, other = battle.chars
        caster.b[F['levels'] + 5] = level
        battle.data.update(current_spell=ident, aim=(11, 10))
        rolls, pauses = [], []
        game.s.random = lambda sides: rolls.append(sides) or (roll if sides == 20 else sides - 1)
        game.ask = lambda kind, options, **info: pauses.append((kind, info)) or 0
        return game, battle, caster, target, other, rolls, pauses
    def cast(game, caster, ident, targets):
        row = magic.spell(game, ident)
        magic.handler(game, row)(game, caster, targets, row)
        return row
    for ident in (2, 25, 27, 31, 33, 44, 45, 61, 63, 80, 88, 90, 95, 97, 98, 100, 102):
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        row = cast(game, caster, ident, [target])
        assert bool(effects.has_effect(target, row.effect)) == bool(row.effect) or row.range == 255 or ident == 27, ident
        if ident == 27: assert not target.effects and not rolls
    for level, slept in ((1, True), (0xFF, False)):
        game, battle, caster, target, other, rolls, pauses = setup(21)
        target.b[F['highest_level']] = level
        shared = [target]
        row = cast(game, caster, 21, shared)
        assert bool(effects.has_effect(target, row.effect)) == slept, level
        assert shared == ([target] if slept else [None]) and battle.data['multi_target'] == 1
    game, battle, caster, target, other, rolls, pauses = setup(48, 2)
    effects.add_effect(other, 42, 5, 0, False)
    third = [caster, target, other]
    age = rules.record(caster).get('age')
    cast(game, caster, 48, third)
    assert third == [caster, None, None] and not effects.has(other, 42) and not effects.has(other, 39)
    node = effects.has_effect(caster, 39)
    assert node[1] | node[2] << 8 == 5 and node[3] == 2 + 16 and rules.record(caster).get('age') == age + 1
    assert battle.data['multi_target'] == 1 and not effects.has(target, 39) and game.age_pass
    game, battle, caster, target, other, rolls, pauses = setup(48, 1)
    both = [caster, other]
    cast(game, caster, 48, both)
    assert both == [caster, None] and not effects.has(other, 39)
    game, battle, caster, target, other, rolls, pauses = setup(55)
    effects.add_effect(target, 39, 5, 16, False)
    mixed = [target, caster]
    cast(game, caster, 55, mixed)
    assert mixed == [None, None] and not target.effects and not caster.effects
    cast(game, caster, 55, [target])
    assert effects.has_effect(target, 42)[1] == 11
    game, battle, caster, target, other, rolls, pauses = setup(32)
    cast(game, caster, 32, [caster])
    assert effects.has_effect(caster, 28)[3] == 4 << 4 | 8 and rolls == [4]
    for level, base, strength in ((1, 17, None), (2, 17, 2), (6, 18, 101), (7, 18, 119), (0, 21, 122), (9, 21, None)):
        game, battle, caster, target, other, rolls, pauses = setup(12, level or 1)
        if not level: caster.b[F['robe_order']], caster.b[F['levels'] + 5], game.s.r0[0x1F9] = 1, 1, 0
        target.b[F['abilities']] = target.b[F['abilities'] + 1] = base
        if level == 1: target.b[F['abilities']] = target.b[F['abilities'] + 1] = 18
        cast(game, caster, 12, [target])
        node = effects.has_effect(target, 12)
        assert (node[3] if node else None) == strength, (level, node)
        assert len(pauses) == 1 and pauses[0][1]['timed'] == 1 and not rolls
        suffix = game.assets.text('strongerText' if strength else 'unaffectedMessage')
        assert pauses[0][1]['prompt'] == 'TEST ' + suffix
        if node: assert node[4] == 1 and node[1] | node[2] << 8 == 10 * (level or 0)
    for ident, count, expected in ((94, 1, 253), (94, 2, 255), (94, 3, 0), (49, 1, 253), (23, 1, 254)):
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        seen = []
        real = battle.save
        battle.save = lambda j, kind, bonus=0, element=0: seen.append(bonus) or real(j, kind, bonus, element)
        cast(game, caster, ident, [target, other, caster][:count])
        assert seen == [expected] * count and effects.has(target, 52)
    game, battle, caster, target, other, rolls, pauses = setup(79, roll=0)
    cast(game, caster, 79, [target, other])
    assert effects.has(target, 7) and not effects.has(other, 7) and rolls == [20]
    assert [(e['actor'], e['start'], e['aim'], e['spell'], e['picture'], e['frames'], e['pace'], e['posed']) for e in game.combat_report if isinstance(e, dict)] == [(0, (10, 10), (11, 10), 79, 18, 4, 30, 0)]
    assert battle.data['messages'][-1] == 'TEST ' + game.assets.text('highlightedText')
    game, battle, caster, target, other, rolls, pauses = setup(28)
    cast(game, caster, 28, [caster])
    node = effects.has_effect(caster, 23)
    assert node[4] == 1 and any(item[I['type']] == 6 and item[I['name_ids'] + 2] == 121 for item in caster.items)
    game, battle, caster, target, other, rolls, pauses = setup(37)
    cast(game, caster, 37, [other])
    assert not battle.data['messages']
    effects.add_effect(other, 33, 0, 0, False)
    cast(game, caster, 37, [other])
    assert not other.effects and battle.data['messages'][-1] == 'TEST ' + game.assets.text('canSeeText')
    game, battle, caster, target, other, rolls, pauses = setup(40)
    cast(game, caster, 40, [target])
    assert target.b[F['hp']] == 4 and rolls == [4] and battle.data['roll']['element'] == 8
    for ident, damage, calls in ((65, 10, [4, 4]), (74, 48, [8] * 6 + [20]), (87, 30, [10] * 3)):
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        cast(game, caster, ident, [target])
        assert target.b[F['hp']] == 250 - damage and rolls[:len(calls)] == calls, (ident, target.b[F['hp']], rolls)
        assert battle.data['roll']['dice_count'] == len([c for c in calls if c != 20])
    for ident in (62, 99):
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        caster.b[F['hp']] = 200
        cast(game, caster, ident, [caster])
        assert caster.b[F['hp']] == 210 and rolls == [4, 4]
        assert battle.data['messages'][-1] == 'TEST ' + game.assets.text('healedMessage')
    game, battle, caster, target, other, rolls, pauses = setup(3)
    target.b[F['hp']] = 200
    cast(game, caster, 3, [target])
    assert battle.data['messages'][-1].endswith(game.assets.text('partiallyHealedText')) and len(pauses) == 1, (battle.data['messages'], pauses)
    game, battle, caster, target, other, rolls, pauses = setup(57)
    effects.add_effect(caster, 42, 0, 0, False)
    cast(game, caster, 57, [caster])
    assert not caster.effects
    cast(game, caster, 57, [caster])
    assert effects.has(caster, 39)
    game, battle, caster, target, other, rolls, pauses = setup(73)
    caster.b[F['levels']] = 8
    cast(game, caster, 73, [caster])
    assert effects.has_effect(caster, 4)[1] == 8 and effects.has(caster, 34)
    for age, result, key in ((40, 35, 'youngerText'), (20, 18, 'eighteenYearsOldText'), (3, 65534, 'youngerText')):
        game, battle, caster, target, other, rolls, pauses = setup(96)
        rules.record(caster).set('age', age)
        cast(game, caster, 96, [caster])
        assert rules.record(caster).get('age') == result and rolls == [4]
        assert pauses[0][1]['prompt'] == 'TEST ' + game.assets.text(key) and not caster.effects
    for ident, count, damage in ((15, 4, 20), (20, 1, 16)):
        game, battle, caster, target, other, rolls, pauses = setup(ident, roll=19)
        battle.save = lambda *a, **k: False
        cast(game, caster, ident, [target])
        assert battle.data['roll']['dice_count'] == count and target.b[F['hp']] == 250 - damage, (ident, battle.data['roll'], target.b[F['hp']], rolls)
    for near, left in ((True, [None, None, None]), (False, None)):
        game, battle, caster, target, other, rolls, pauses = setup(1)
        if not near: battle.targets = lambda *a, **k: []
        shared = [caster, target, other]
        row = cast(game, caster, 1, shared)
        assert shared == (left or [caster, None, other]) and battle.data['multi_target'] == 1
        assert effects.has(caster, row.effect) == effects.has(other, row.effect) == (not near) and not effects.has(target, row.effect)
    for ident, deity, calls in ((71, 4, [8]), (71, 0, []), (3, 4, []), (58, 4, [])):
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        caster.b[F['deity']] = deity
        cast(game, caster, ident, [])
        assert rolls == calls, (ident, deity, rolls)
    game, battle, caster, target, other, rolls, pauses = setup(71)
    caster.b[F['deity']], target.b[F['hp']] = 4, 100
    cast(game, caster, 71, [target])
    assert rolls == [8, 8, 8, 8] and target.b[F['hp']] == 100 + 8 + 3 + 24


def check_area_and_death_spells():
    from ._combat_test import action_fixture
    def setup(ident, level=8, d20=0, d100=0):
        game, battle = action_fixture()
        del battle.trigger
        caster, target, other = battle.chars
        caster.b[F['levels'] + 5] = level
        battle.data.update(current_spell=ident, aim=(11, 10), clouds=[])
        rolls, pauses = [], []
        game.s.random = lambda sides: rolls.append(sides) or (d20 if sides == 20 else d100 if sides == 100 else sides - 1)
        game.ask = lambda kind, options, **info: pauses.append((kind, info)) or 0
        return game, battle, caster, target, other, rolls, pauses
    def cast(game, caster, ident, targets):
        row = magic.spell(game, ident)
        magic.handler(game, row)(game, caster, targets, row)
    for ident, cells, terrain in ((34, [(11, 10), (12, 10), (12, 11), (11, 11)], 29),
                                  (91, [(11, 10), (12, 10), (12, 11), (11, 11), (10, 11), (10, 10), (10, 9), (11, 9), (12, 9)], 28)):
        game, battle, caster, target, other, rolls, pauses = setup(ident, d20=19)
        target.b[F['highest_level']] = 9
        battle.put_tile(12, 11, 0)
        old = dict(cells=[], terrain=29, countdown=3, x=30, y=3, level=3)
        battle.data['clouds'].append(old)
        cast(game, caster, ident, [target])
        cloud = battle.data['clouds'][0]
        covered = [cell for cell in cells if cell != (12, 11)]
        assert battle.data['clouds'][1] is old and cloud['cells'] == [(x, y, 23) for x, y in covered]
        assert (cloud['terrain'], cloud['countdown'], cloud['x'], cloud['y'], cloud['level']) == (terrain, 8, 11, 10, 8)
        assert all(battle.tile(x, y) == terrain for x, y in covered) and battle.tile(12, 11) == 0
        assert battle.data['view'] == (8, 7)
        if ident == 34: assert effects.has(target, 30) and not effects.has(caster, 30) and effects.has(other, 30) and rolls == [20, 4, 20, 4]
        else: assert not target.effects and target.b[F['active']] and not rolls
    game, battle, caster, target, other, rolls, pauses = setup(34)
    battle.data['aim'] = (49, 24)
    cast(game, caster, 34, [])
    assert battle.data['clouds'][0]['cells'] == [(49, 24, 23)] and not rolls
    game, battle, caster, target, other, rolls, pauses = setup(41, level=1, d100=59)
    caster.b[F['levels']] = 10
    for strength in (255, 8, 10, 12, 31):
        effects.add_effect(target, 1, 5, strength, False)
    cast(game, caster, 41, [target, other])
    assert [node[3] for node in target.effects] == [255, 10, 12, 31] and rolls == [100] * 7 and not other.effects
    assert battle.data['messages'].count('TEST ' + game.assets.text('isAffectedText')) == 1 and battle.data['multi_target'] == 1
    assert game.spell_cost == 15
    game, battle, caster, target, other, rolls, pauses = setup(34, level=8)
    cast(game, caster, 34, [])
    cast(game, caster, 34, [])
    weak = battle.data['clouds'][1]
    weak['level'] = 20
    battle.data['current_spell'] = 46
    game.spell_cost = 30
    rolls.clear()
    game.s.random = lambda sides: rolls.append(sides) or 29
    cast(game, caster, 46, [])
    assert len(rolls) == 8 and battle.data['clouds'] == [weak] and weak['countdown'] == 8
    assert all(battle.tile(x, y) == 29 for x, y in ((11, 10), (12, 10), (12, 11), (11, 11)))
    game.spell_cost = 0
    cast(game, caster, 46, [])
    assert not battle.data['clouds'] and all(battle.tile(x, y) == 23 for x, y in ((11, 10), (12, 10), (12, 11), (11, 11)))
    game, battle, caster, target, other, rolls, pauses = setup(56, d20=19)
    target.b[F['highest_level']], target.b[F['hp_max']] = 6, 52
    other.b[F['highest_level']] = 9
    third = [target, other, caster]
    caster.b[F['target_flags']] = 8
    cast(game, caster, 56, third)
    assert third == [target, None, None] and target.b[F['status']] == 6 and other.b[F['active']] and caster.b[F['active']]
    assert rolls == [20] * 4 and game.spell_cost == 1 and battle.data['roll']['element'] == 0x40
    for ident, d20, status in ((60, 0, 6), (60, 19, 0), (72, 0, 7), (72, 19, 0), (76, 0, 6), (76, 19, 0)):
        game, battle, caster, target, other, rolls, pauses = setup(ident, d20=d20)
        cast(game, caster, ident, [target])
        assert target.b[F['status']] == status and bool(target.b[F['active']]) == (not status)
        if ident == 76 and d20: assert target.b[F['hp']] == 250 - 17 and rolls == [20, 8, 8] and battle.data['roll']['dice_count'] == 2
        else: assert rolls == [20]
    game, battle, caster, target, other, rolls, pauses = setup(76)
    target.b[F['target_flags']] = 8
    cast(game, caster, 76, [target])
    assert target.b[F['hp']] == 250 - 17 and rolls == [20, 8, 8]
    game, battle, caster, target, other, rolls, pauses = setup(76)
    effects.add_effect(target, 59, 0, 0, False)
    battle.data['current_spell'] = 9
    cast(game, caster, 76, [target])
    assert target.b[F['hp']] == 250 and not rolls and pauses[0][1]['prompt'] == 'TEST ' + game.assets.text('unaffectedMessage')
    for flags, d20, dead, calls in ((0, 0, True, [20, 20]), (8, 0, False, [20, 20]), (0, 19, False, [20, 20])):
        game, battle, caster, target, other, rolls, pauses = setup(68, d20=d20)
        battle.record(0)['target'] = 1
        target.b[F['target_flags']] = flags
        cast(game, caster, 68, [target])
        assert (target.b[F['status']] == 6) == dead and effects.has(target, 55) == dead and rolls == calls


def check_neutralize():
    game, (caster, target), decisions, answers = fixture()
    row = magic.spell(game, 67)
    magic.handler(game, row)(game, caster, [target], row)
    assert decisions[-1][2]['timed'] == 1 and decisions[-1][2]['prompt'].endswith(game.assets.text('unaffectedMessage'))
    for ident in (55, 15, 22, 55): effects.add_effect(target, ident, 0, 255, ident != 55)
    target.b[F['hp']], target.b[F['active']], target.b[F['status']] = 0, 0, 6
    magic.handler(game, row)(game, caster, [target], row)
    assert [node[0] for node in target.effects] == [55] and not getattr(game, 'effect_busy', False)
    assert (target.b[F['hp']], target.b[F['active']], target.b[F['status']]) == (1, 1, 0)
    assert decisions[-1][2]['prompt'].endswith(game.assets.text('unpoisonedText'))
    target.b[F['status']] = camp.ANIMATED
    group = [target]
    magic.handler(game, row)(game, caster, group, row)
    assert group == [None] and [node[0] for node in target.effects] == [55]


def check_charm():
    from ._combat_test import action_fixture
    def setup(ident, side=0, saved=False):
        game, battle = action_fixture()
        del battle.trigger
        caster, target, other = battle.chars
        caster.b[F['side']], target.b[F['side']] = side, 1 - side
        caster.b[F['levels'] + (4 if ident == 4 else 0 if ident == 106 else 5)] = 15 if ident == 4 else 8
        target.b[F['race']] = 6
        battle.data.update(current_spell=ident, aim=(11, 10))
        battle.record(1)['target'] = 0
        rolls, pauses = [], []
        game.s.random = lambda sides: rolls.append(sides) or (19 if saved else 0)
        game.ask = lambda kind, options, **info: pauses.append((kind, info, bytes(target.b))) or 0
        return game, battle, caster, target, other, rolls, pauses
    for ident in (4, 10, 106):
        for side in (0, 1):
            game, battle, caster, target, other, rolls, pauses = setup(ident, side)
            row = magic.spell(game, ident)
            magic.handler(game, row)(game, caster, [target], row)
            node = effects.has_effect(target, 11)
            assert node is not None and node[1] | node[2] << 8 == (60 if ident == 4 else 540 if ident == 10 else 0)
            assert node[3] == 8 + side * 128 + 32 + (1 - side) * 64 and node[4] == 1
            assert target.b[F['side']] == side and target.b[F['auto_combat']] == 1 and target.b[F['npc']] == 179
            assert battle.record(1)['target'] == -1 and rolls == [20] and [(k, i['timed'], i['anim']) for k, i, _ in pauses] == [('ACK', 1, 1)]
            suffix = game.assets.text('isText') + game.assets.names('effectNames')[10] if ident == 4 else game.assets.text('charmedText')
            assert battle.data['messages'][-1] == 'TEST ' + suffix and battle.data['morale'] == 100
            effects.remove_effect(game, target, 11, node)
            assert target.b[F['side']] == 1 - side and target.b[F['auto_combat']] == 0 and target.b[F['npc']] == 0
            assert battle.record(1)['target'] == -1
        cases = ((255, 0, 2, True), (7, 0, 1, False), (7, 16, 2, True), (8, 2, 1, False)) if ident == 4 else (
            (255, 0, 1, True), (7, 0, 1, False), (7, 2, 1, True), (7, 16, 1, False),
            (8, 0, 1, True), (6, 0, 0, True), (6, 2, 2, False))
        for race, kind, size, allowed in cases:
            game, battle, caster, target, other, rolls, pauses = setup(ident)
            for key, value in (('race', race), ('creature_type', kind), ('dimensions', size)): target.b[F[key]] = value
            before = bytes(target.b)
            row = magic.spell(game, ident)
            magic.handler(game, row)(game, caster, [target], row)
            assert bool(effects.has_effect(target, 11)) == allowed, (ident, race, kind, size)
            assert rolls == ([20] if allowed else [])
            if not allowed:
                suffix = game.assets.text('isText') + game.assets.text('notText') + game.assets.names('effectNames')[10] if ident == 4 else game.assets.text('unaffectedMessage')
                assert len(pauses) == 1 and pauses[0][0] == 'ACK' and pauses[0][1]['timed'] == 1
                assert pauses[0][1]['prompt'] == 'TEST ' + suffix and pauses[0][2] == before
                assert bytes(target.b) == before and battle.record(1)['target'] == 0
        for targets in ([], [None], [None, True]):
            game, battle, caster, target, other, rolls, pauses = setup(ident)
            row = magic.spell(game, ident)
            magic.handler(game, row)(game, caster, targets, row)
            assert not rolls and not pauses and not battle.data['messages'] and not target.effects
        for blocked in ('save', 'resistance', 'immunity'):
            for existing in (False, True):
                game, battle, caster, target, other, rolls, pauses = setup(ident, saved=blocked == 'save')
                if blocked == 'resistance': target.b[F['magic_resistance']] = 100
                if blocked == 'immunity': effects.add_effect(target, 96, 0, 0, False)
                if existing:
                    effects.add_effect(target, 11, 0, 8, True)
                    effects.add_effect(target, 11, 0, 136, True)
                    first, second = target.effects[-2:]
                row = magic.spell(game, ident)
                magic.handler(game, row)(game, caster, [target], row)
                assert rolls == ([20, 100] if blocked == 'resistance' else [20])
                assert target.b[F['side']] == (0 if existing else 1)
                if existing:
                    assert effects.has_effect(target, 11) is first and first[3] == 104 and second[3] == 136
                    assert battle.record(1)['target'] == -1
                else: assert effects.has_effect(target, 11) is None and battle.record(1)['target'] == 0
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        effects.add_effect(target, 11, 0, 8, True)
        old = target.effects[0]
        row = magic.spell(game, ident)
        magic.handler(game, row)(game, caster, [target, None, other], row)
        assert target.effects[0] is old and len(target.effects) == 2 and old[3] == 104
        assert target.effects[1][3] == 8 and effects.has_effect(other, 11)[3] == 8
        assert other.b[F['auto_combat']] == 0 and rolls == [20, 20]
        battle.record(1)['target'] = 2
        game.s.random = lambda sides: 19
        magic.handler(game, row)(game, caster, [target], row)
        assert target.effects[0] is old and old[3] == 104 and battle.record(1)['target'] == 2
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        effects.add_effect(target, 11, 10, 104, True)
        old = target.effects[0]
        target.b[F['side']], target.b[F['npc']], target.b[F['auto_combat']] = 0, 179, 1
        magic.handler(game, row)(game, caster, [target], row)
        assert len(target.effects) == 1 and target.effects[0] is not old and target.effects[0][3] == 104
        effects.remove_effect(game, target, 11)
        assert target.b[F['side']] == 1 and target.b[F['npc']] == 0 and target.b[F['auto_combat']] == 0
        game, battle, caster, target, other, rolls, pauses = setup(ident)
        caster = game.s.party[0] = rules.character(bytes(caster.b), spells=bytes(Spells()))
        caster.b[F['memorized']] = ident
        battle.spell_targets = lambda *args, **kwargs: [1]
        assert battle.cast(0, ident)
        assert caster.b[F['memorized']] == ident | 128 and target.b[F['side']] == 0
        assert not battle.data.get('current_spell') and rolls == [20]


def check_bolt_cone_breath():
    from ._combat_test import action_fixture
    def setup(dungeon=0, level=5, roll=0):
        game, battle = action_fixture()
        del battle.trigger
        battle.chars[0].b[F['levels'] + 5] = level
        game.s.r0[0xE6] = dungeon
        rolls, pauses = [], []
        game.s.random = lambda sides: rolls.append(sides) or (roll if sides == 20 else sides - 1)
        game.ask = lambda kind, options, **info: pauses.append(info.get('prompt')) or 0
        return game, battle, rolls, pauses
    def cast(game, battle, ident, aim=(11, 10)):
        battle.data.update(aim=aim, current_spell=ident)
        game.spell_targets = []
        row = magic.spell(game, ident)
        magic.handler(game, row)(game, battle.chars[0], game.spell_targets, row)
        return game.spell_targets
    hp = lambda battle: [c.b[F['hp']] for c in battle.chars]
    table = Assets().table
    matrix = table('directionMatrix')
    assert all(matrix[(table('directionY')[d] + 1) * 3 + table('directionX')[d] + 1] == d for d in range(8))
    for dungeon, wall, expected, saves, aim in ((0, 13, [250, 220, 220], 2, (11, 10)), (1, 13, [220, 190, 190], 5, (13, 10)),
                                              (2, 13, [250, 220, 220], 2, (11, 10)), (1, 14, [250, 220, 220], 2, (14, 10))):
        game, battle, rolls, _ = setup(dungeon)
        battle.put_tile(wall, 10, 1)
        cast(game, battle, 51)
        assert hp(battle) == expected and rolls == [6] * 5 + [20] * saves, (dungeon, wall, hp(battle), rolls)
        assert battle.data['aim'] == aim and battle.data['multi_target'] == 0
        assert battle.data['roll']['element'] == 12 and battle.data['roll']['dice_count'] == 5
        stretches = [e for e in game.combat_report if isinstance(e, dict) and e['kind'] == 'flight']
        assert stretches and all((e['picture'], e['frames'], e['pace']) == (19, 4, 50) for e in stretches)
        if (dungeon, wall) == (1, 13):
            assert [(e['start'], e['aim']) for e in stretches] == [((11, 10), (12, 10)), ((12, 10), (13, 10)), ((13, 10), (12, 10)),
                                                                   ((12, 10), (11, 10)), ((11, 10), (10, 10))]
    game, battle, rolls, _ = setup(1, roll=19)
    cast(game, battle, 51)
    assert hp(battle) == [250, 235, 235] and rolls == [6] * 5 + [20, 20]
    game, battle, rolls, _ = setup(1)
    cast(game, battle, 51, (10, 10))
    assert hp(battle) == [220, 250, 250] and rolls == [6] * 5 + [20] and not battle.data.get('multi_target')
    game, battle, rolls, _ = setup(0)
    battle.record(1).update(x=10, y=9)
    battle.record(2).update(x=10, y=1)
    cast(game, battle, 51, (10, 9))
    assert hp(battle) == [250, 220, 250] and rolls == [6] * 5 + [20]
    for ident, spot, expected, count in ((92, (12, 11), [250, 225, 225], 2), (92, (12, 9), [250, 225, 250], 1)):
        game, battle, rolls, _ = setup()
        battle.record(2).update(x=spot[0], y=spot[1])
        found = cast(game, battle, ident)
        assert hp(battle) == expected and rolls == [4] * 5 + [20] * count and len(found) == count, (spot, hp(battle), rolls)
        assert battle.data['roll']['dice_count'] == 5 and battle.data['roll']['element'] == 0
    game, battle, rolls, _ = setup()
    battle.record(1).update(x=1, y=1)
    battle.record(2).update(x=12, y=11)
    assert cast(game, battle, 92) == [] and hp(battle) == [250, 250, 250]
    game, battle, rolls, _ = setup(level=1)
    battle.record(2).update(x=12, y=10)
    assert cast(game, battle, 92) == [battle.chars[1]] and hp(battle) == [250, 245, 250]
    game, battle, rolls, _ = setup()
    battle.put_tile(12, 10, 1)
    battle.record(2).update(x=13, y=10)
    assert cast(game, battle, 92) == [battle.chars[1]]
    game, battle, rolls, _ = setup()
    effects.add_effect(battle.chars[1], 10, 0, 0, False)
    battle.chars[1].b[F['saves'] + 4] = 8
    game.s.random = lambda sides: rolls.append(sides) or (4 if sides == 20 else sides - 1)
    cast(game, battle, 92)
    assert hp(battle) == [250, 244, 238], hp(battle)
    game, battle, rolls, _ = setup()
    battle.record(2).update(size=2)
    battle.record(1).update(x=14, y=10)
    assert cast(game, battle, 92) == [battle.chars[2]]
    assert cast(game, battle, 92, (10, 10)) == []
    for spot, afraid in (((13, 9), True), ((13, 11), True), ((14, 12), False), ((17, 10), False)):
        game, battle, rolls, pauses = setup()
        battle.record(2).update(x=spot[0], y=spot[1])
        battle.record(1)['target'] = battle.record(2)['target'] = 0
        cast(game, battle, 84)
        assert [effects.has(c, 111) for c in battle.chars] == [False, True, afraid] and rolls == [20] * (1 + afraid)
        assert [(r['target'], r['turned']) for r in battle.data['actors'][1:]] == [(-1, 1), (-1, 1) if afraid else (0, 0)]
        assert [c.b[F['npc']] for c in battle.chars] == [0, 179, 179 if afraid else 0] and battle.chars[1].b[F['auto_combat']] == 1
        assert effects.has_effect(battle.chars[1], 111)[1:5] == bytes((5, 0, 0, 1)) and len(pauses) == 1 + afraid
    game, battle, rolls, pauses = setup(roll=19)
    cast(game, battle, 84)
    assert not any(effects.has(c, 111) for c in battle.chars) and len(pauses) == 2 and rolls == [20, 20]
    assert pauses[0].endswith(game.assets.text('unaffectedMessage')) and battle.record(1)['turned'] == 0
    game, battle, rolls, pauses = setup()
    battle.data['view'] = (0, 0)
    battle.record(1).update(x=30, y=20)
    battle.message('X')
    battle.name_anim(battle.chars[1])
    assert battle.data['view'] == (27, 17) and pauses == ['X']
    battle.record(1).update(x=29, y=19)
    battle.name_anim(battle.chars[1])
    assert battle.data['view'] == (27, 17)
    def breathe(kind, rnd, strength, dungeon=1, roll=0, spots=None, sides=(0, 1, 0)):
        game, battle, rolls, pauses = setup(dungeon, roll=roll)
        for at, spot in enumerate(spots or ()): battle.record(at).update(x=spot[0], y=spot[1])
        for c, side in zip(battle.chars, sides): c.b[F['side']] = side
        bearer = battle.chars[1]
        bearer.b[F['hp_max']] = 40
        effects.add_effect(bearer, kind, 0, strength, False)
        battle.data.update(actor=1, round=rnd)
        battle.record(1)['target'] = 0
        battle.trigger(14, 1)
        return game, battle, rolls, pauses, effects.has_effect(bearer, kind)
    for kind, mask, word in ((85, 36, ''), (90, 48, 'acidText'), (100, 96, 'deathText'), (104, 33, 'fireText')):
        for rnd, strength, left in ((0, 0, 2), (1, 2, 1), (0, 9, 2)):
            game, battle, rolls, pauses, node = breathe(kind, rnd, strength)
            assert hp(battle) == [210, 250, 250] and node[3] == left and rolls[-1] == 20, (kind, rnd, hp(battle), rolls)
            assert battle.record(1)['initiative'] == 0 and battle.record(1)['facing'] == 6
            assert pauses[0].endswith(game.assets.text('breathesText') + (game.assets.text(word) if word else ''))
            assert battle.data['roll']['element'] == mask and battle.data['roll']['damage'] == 40
            flights = [(e['start'], e['aim'], e['picture'], e['frames'], e['pace']) for e in game.combat_report if isinstance(e, dict) and e['kind'] == 'flight']
            assert flights[0] == ((11, 10), (10, 10)) + ((19, 4, 50) if kind == 85 else (18, 1, 30)), flights
        game, battle, rolls, pauses, node = breathe(kind, 1, 0)
        assert hp(battle) == [250, 250, 250] and not rolls and not pauses and battle.record(1)['initiative'] == 6
        game, battle, rolls, pauses, node = breathe(kind, 1, 2, roll=19)
        assert hp(battle) == [230, 250, 250] and node[3] == 1
    game, battle, rolls, pauses, node = breathe(90, 1, 2, spots=((10, 10), (11, 10), (9, 10)), sides=(0, 1, 1))
    assert hp(battle) == [250, 250, 250] and node[3] == 2 and not pauses and battle.record(1)['initiative'] == 6
    assert battle.data['roll']['element'] == 48
    game, battle, rolls, pauses, node = breathe(90, 1, 2, spots=((10, 10), (11, 10), (9, 10)))
    assert hp(battle) == [210, 250, 210] and node[3] == 1
    game, battle, rolls, pauses, node = breathe(104, 1, 2, spots=((10, 10), (11, 10), (6, 11)))
    assert hp(battle) == [210, 250, 210]
    game, battle, rolls, pauses, node = breathe(90, 1, 2, spots=((10, 10), (11, 10), (6, 11)))
    assert hp(battle) == [210, 250, 250]
    for rnd in (0, 1):
        game, battle, rolls, pauses, node = breathe(81, rnd, 0)
        assert effects.has(battle.chars[0], 11) and node[3] == 0 and battle.record(1)['initiative'] == 6
        assert battle.data['current_spell'] == 10 and pauses[0].endswith(game.assets.text('gazesText'))
        assert game.spell_targets == [battle.chars[0]] and battle.record(1)['facing'] == 6 and hp(battle) == [250, 250, 250]
        assert [(e['start'], e['aim'], e['picture'], e['frames'], e['pace']) for e in game.combat_report if isinstance(e, dict) and e['kind'] == 'flight'] == [((11, 10), (10, 10), 18, 4, 50)]
    game, battle, rolls, pauses, node = breathe(81, 1, 0, roll=19)
    assert not effects.has(battle.chars[0], 11) and battle.data['current_spell'] == 10


def check_empty_cast():
    game, (char, other), decisions, answers = fixture()
    game.noncombat_target = other
    before = bytes(char.b)
    magic.cast_menu(game, char)
    assert len(decisions) == 1 and decisions[0][0] == 'ACK'
    assert decisions[0][2]['prompt'] == ' ' + game.assets.text('noSpellsMessage')
    assert decisions[0][2].get('timed') == 1 and decisions[0][2]['creature_text'] == game.assets.text('noSpellsMessage')
    assert game.noncombat_target is None and bytes(char.b) == before
    from sm.engine import Session
    from .menu import Game
    from .ui import screen
    game = Game(None)
    game.s.party = [char]
    game.s.mode, game.s.sel, game.s.r0[0xE5] = 6, 0, 0
    seed = game.s.seed
    def play(limit):
        game.ask('MENU', ('Cast',), prompt='')
        magic.cast_menu(game, char)
        game.ask('MENU', ('Exit',), prompt='')
    game.play = play
    session = Session(profile='dkk', game=game)
    try:
        controller = screen.Controller(session, presentation=False)
        assert session.decision['options'] == ('Cast',)
        controller.key('c', 'c')
        assert session.error is None and session.decision['options'] == ('Exit',)
        assert session.decision['kind'] == 'MENU'
        assert game.s.seed == seed and bytes(char.b) == before
    finally: session.close()


def check_camp_refusals():
    game, (char, other), decisions, answers = fixture()
    text = game.assets.text
    drawn = []
    with patch.object(camp, 'redraw_camp', drawn.append):
        game.s.r0[0xE5] = 1
        magic.cast_menu(game, char)
        assert decisions[-1][2]['creature_text'] == text('antiMagicMessage') and len(text('antiMagicMessage')) == 30
        game.s.r0[0xE5], char.b[F['active']] = 0, 0
        magic.cast_menu(game, char)
        assert decisions[-1][2]['creature_text'] == text('incapacitatedPrefix') + text('castingSuffix')
        char.b[F['active']], game.s.mode = 1, camp.CAMPING
        magic.cast_menu(game, char)
        assert not drawn
        char.b[F['memorized']] = 19
        answers.extend((0, 0))
        magic.cast_menu(game, char)
        assert drawn == [game] and decisions[-1][2]['creature_text'] == text('noSpellsMessage')
        game.s.mode = 0
        char.b[F['memorized']] = 19
        answers.extend((0, 0))
        magic.cast_menu(game, char)
        assert drawn == [game]
        game.s.mode = camp.CAMPING
        magic.scribe(game, char)
        assert drawn == [game] and decisions[-1][2]['creature_text'] == text('noCopyableMessage')
        paper = scroll(char, (15, 0, 0))
        char.b[F['spell_slots'] + 24] = 1
        answers.append(1)
        magic.scribe(game, char)
        assert drawn == [game, game]
        paper[I['powers']] = 143
        answers.extend((0, 0))
        magic.scribe(game, char)
        assert drawn == [game] * 3 and paper[I['powers']] == 143
        game.s.g['camp.rest'] = [0, 5, 2, 3, 1, 0, 0]
        assert magic.finish_scribe(game, char, False) == (0, True)
        shown = decisions[-1][2]
        assert shown['rest_digits'] == ('01', '03', '25') and shown['field'] == 0 and shown['spell'] == 15 and shown['timed'] == 1


def check_unbound_spells():
    from ._combat_test import action_fixture
    def setup(roll=0, low=False):
        game, battle = action_fixture()
        del battle.trigger
        caster, target, other = battle.chars
        caster.b[F['levels'] + 5] = 8
        for char in battle.chars: char.b[F['levels'] + 2] = 3
        battle.data.update(aim=(11, 10))
        pauses = []
        game.s.random = lambda sides: roll if sides == 20 else 0 if low else sides - 1
        game.ask = lambda kind, options, **info: pauses.append((kind, info)) or 0
        return game, battle, caster, target, other, pauses
    def cast(game, caster, ident, targets):
        row = magic.spell(game, ident)
        battle = game.battle
        battle.data['current_spell'] = ident
        magic.handler(game, row)(game, caster, targets, row)
        return battle.data['messages']
    for roll, kept in ((0, False), (19, True)):
        game, battle, caster, target, other, pauses = setup(roll)
        effects.add_effect(target, 12, 5, 0, True)
        cast(game, caster, 13, [target])
        assert effects.has(target, 12) == kept
    game, battle, caster, target, other, pauses = setup()
    cast(game, caster, 14, [caster])
    assert effects.has_effect(caster, 14)[3] == 8
    game, battle, caster, target, other, pauses = setup()
    target.b[F['status']] = camp.ANIMATED
    chosen = [target]
    cast(game, caster, 26, chosen)
    assert chosen == [None] and not target.effects
    game, battle, caster, target, other, pauses = setup()
    effects.add_effect(target, 55, 0, 0, False)
    target.b[F['hp']], target.b[F['status']], target.b[F['active']] = 0, 5, 0
    cast(game, caster, 26, [target])
    assert (target.b[F['hp']], target.b[F['status']], target.b[F['active']]) == (1, 0, 1)
    assert effects.has_effect(target, 15)[3] == 255 and effects.has_effect(target, 22)[3] == 255
    game, battle, caster, target, other, pauses = setup()
    target.b[F['abilities']] = target.b[F['abilities'] + 1] = 17
    cast(game, caster, 35, [target])
    assert effects.has_effect(target, 38)[3] == 108
    game, battle, caster, target, other, pauses = setup()
    for char in (target,): char.b[F['levels'] + 2] = 0
    try: cast(game, caster, 35, [target]); raise AssertionError('Strength without a class')
    except magic.BindingRequired: pass
    game, battle, caster, target, other, pauses = setup()
    target.b[F['hp']], target.b[F['hp_max']] = 10, 50
    effects.add_effect(target, 33, 5, 0, False)
    messages = cast(game, caster, 53, [target])
    assert target.b[F['hp']] == 46 and not effects.has(target, 33) and messages[-1].endswith('is healed')
    game, battle, caster, target, other, pauses = setup()
    target.b[F['hp']], target.b[F['hp_max']] = 49, 50
    cast(game, caster, 53, [target])
    assert target.b[F['hp']] == 49
    game, battle, caster, target, other, pauses = setup()
    target.b[F['abilities']] = 17
    cast(game, caster, 59, [target])
    node = effects.has_effect(target, 113)
    assert node[1] == 80 and pauses
    game, battle, caster, target, other, pauses = setup()
    target.b[F['highest_level']] = 6
    messages = cast(game, caster, 70, [target])
    assert not target.effects and messages[-1].endswith('smashes them flat')
    game, battle, caster, target, other, pauses = setup(0, True)
    chosen = [target, other, caster]
    cast(game, caster, 82, chosen)
    assert chosen == [target, other] and effects.has(target, 35) and not effects.has(caster, 35)
    for roll, kind in ((0, 27), (19, 42)):
        game, battle, caster, target, other, pauses = setup(roll)
        cast(game, caster, 86, [target])
        assert effects.has(target, kind)
    game, battle, caster, target, other, pauses = setup()
    target.b[F['hp']] = 20
    cast(game, caster, 110, [target])
    assert effects.has_effect(target, 6)[1] == 16
    game, battle, caster, target, other, pauses = setup()
    level = F['levels'] + 5
    caster.b[level] = 4
    for char in (target, other, caster): char.b[F['creature_type']], char.b[F['highest_level']] = 2, 4
    cast(game, caster, 111, [target, other, caster])
    assert effects.has(target, 11) and effects.has(other, 11) and not effects.has(caster, 11)
    game, battle, caster, target, other, pauses = setup()
    target.b[F['hp_max']], other.b[F['hp_max']], caster.b[F['hp_max']] = 60, 50, 40
    cast(game, caster, 114, [target, other, caster])
    assert effects.has(target, 33) and not effects.has(other, 33) and effects.has(caster, 33)
    game, battle, caster, target, other, pauses = setup()
    saves = target.b[F['saves'] + 4]
    cast(game, caster, 93, [target])
    assert target.b[F['saves'] + 4] == saves
    game, battle, caster, target, other, pauses = setup()
    caster.b[F['auto_combat']] = 1
    cast(game, caster, 85, [caster])
    assert effects.has(caster, 54) and effects.has(caster, 112) and not effects.has(caster, 50)
    game, battle, caster, target, other, pauses = setup()
    caster.b[F['auto_combat']] = 0
    cast(game, caster, 85, [caster])
    assert effects.has(caster, 50) and pauses[0][1]['prompt'] == 'Flame type: '
    game, battle, caster, target, other, pauses = setup()
    i = battle.index(caster)
    cast(game, caster, 83, [caster])
    assert battle.position(i) == (11, 10) and battle.record(i)['size'] == 0
    game, battle, caster, target, other, pauses = setup()
    i = battle.index(caster)
    battle.data['aim'] = (10, 12)
    messages = cast(game, caster, 83, [caster])
    assert battle.position(i) == (10, 12) and battle.record(i)['size'] and messages[-1].endswith('teleports')
    assert all(magic.HANDLERS.get(ident) for ident in range(1, 115))


def check_reflection():
    from ._combat_test import action_fixture
    for first, reflected in ((0, True), (1, False)):
        game, battle = action_fixture()
        caster, target, other = battle.chars
        del battle.trigger
        effects.add_effect(target, 71, 0, 0, False)
        game.s.random = lambda sides: first if sides == 10 else 0
        moved = []
        battle.moving_icon = lambda *cells: moved.append(cells)
        row = magic.spell(game, 33)
        battle.data.update(aim=(11, 10), current_spell=33)
        game.spell_targets = [target]
        magic.handler(game, row)(game, caster, game.spell_targets, row)
        assert bool(effects.has(caster, 29)) == reflected and bool(effects.has(target, 29)) != reflected
        assert game.spell_targets == [caster if reflected else target]
        assert moved == ([(11, 10, 10, 10)] if reflected else []) and battle.data['aim'] == ((10, 10) if reflected else (11, 10))
        flights = [(e['start'], e['aim'], e['picture'], e['frames'], e['pace']) for e in getattr(game, 'combat_report', ()) if isinstance(e, dict) and e['kind'] == 'flight']
        assert flights == ([((11, 10), (10, 10), 18, 1, 30)] if reflected else [])
        assert any(game.assets.text('reflectsSpellText') in m for m in battle.data['messages']) == reflected
    for first, reflected in ((0, True), (1, False)):
        game, battle = action_fixture()
        del battle.trigger
        caster, target, other = battle.chars
        battle.data['actor'] = 0
        effects.add_effect(target, 71, 0, 0, False)
        game.s.random = lambda sides: first if sides == 10 else 0
        moved = []
        battle.moving_icon = lambda *cells: moved.append(cells)
        battle.add_with_message(1, 29, 1, 1, False, '')
        assert bool(effects.has(caster, 29)) == reflected and bool(effects.has(target, 29)) != reflected and not moved


def check_cast_show():
    assert magic.toward(29, 13, 19, 1, 0) and not magic.toward(5, 5, 9, 5, 0) and magic.toward(5, 5, 9, 5, 2)
    assert magic.toward(5, 5, 5, 5, 3) and not magic.toward(5, 5, 60, 5, 2)
    def battle(ident, aim, dungeon=False):
        seen, state = [], SimpleNamespace(seed=1, calls=0)
        def random(sides):
            state.calls += 1; state.seed = (state.seed * 0x08088405 + 1) & 0xFFFFFFFF
            return (state.seed >> 16) % sides
        state.random = random
        b = SimpleNamespace(s=state, data={'aim': aim}, rows=[{'facing': 7}], position=lambda i: (29, 13),
                            record=lambda i: b.rows[i], moving_icon=lambda *a: seen.append(a), scroll=lambda *a: None,
                            game=SimpleNamespace(vm=SimpleNamespace(is3d=lambda: dungeon)), event=lambda *a, **k: seen.append(k),
                            show=lambda kind, **k: battle.shown.append(kind) or battle.entries.append((k, len(seen))))
        magic.show_cast(b, 0, ident)
        return b.rows[0]['facing'], state.calls, seen
    battle.shown, battle.entries = [], []
    facing, calls, seen = battle(47, (20, 10))
    assert battle.shown == ['bolt', 'scatter']
    entry, before = battle.entries[0]
    assert before == 0 and (entry['start'], entry['aim'], entry['picture'], entry['frames'], entry['pace'], entry['posed']) == ((29, 13), (20, 10), 18, 4, 30, 1)
    assert (battle.entries[1][0]['actor'], battle.entries[1][0]['posed']) == (0, 1)
    assert facing == 6 and calls == 98 and seen[0] == (29, 13, 20, 10) and seen[1]['points'] == 49
    facing, calls, seen = battle(47, (19, 1))
    assert facing == 0 and calls == 49 + seen[1]['points'] < 98
    assert battle(25, (19, 1))[1:] == (0, [(29, 13, 19, 1)])
    assert battle(34, (20, 10))[1] == 2 * 16 and battle(64, (20, 10), True)[1] == 98
    facing, calls, seen = battle(108, (20, 10), True)
    assert calls == 100 + seen[1]['points']
    from . import effects_handlers
    seen, state = [], SimpleNamespace(seed=1, calls=[])
    def random(sides):
        state.calls.append(sides); state.seed = (state.seed * 0x08088405 + 1) & 0xFFFFFFFF
        return (state.seed >> 16) % sides
    state.random = random
    b = SimpleNamespace(s=state, data={'aim': (0, 0)}, index=lambda c: 0, position=lambda i: (20, 10), scroll=lambda *a: None, event=lambda *a, **k: seen.append(k),
                        spell_damage=lambda who, roll, *a: seen.append((who, roll.damage, roll.element)))
    roll = SimpleNamespace(call=lambda name, char: ['near'])
    effects_handlers.immolate(SimpleNamespace(battle=b, s=state), 'bearer', None, False, roll)
    assert b.data['aim'] == (20, 10) and seen[0]['points'] == 16 and state.calls == [1, 4] * 16 + [6]
    assert seen[1][0] == 'near' and seen[1][2] == 1 and 1 <= seen[1][1] <= 6


def test():
    check_lists()
    check_learn()
    check_caster_and_target()
    check_remove_curse()
    check_item_cast()
    check_study()
    check_camp_resistance()
    check_camp_memo()
    check_revival()
    check_stone_to_flesh()
    check_restoration()
    check_fireball()
    check_charm()
    check_fight_spells()
    check_area_and_death_spells()
    check_neutralize()
    check_bolt_cone_breath()
    check_empty_cast()
    check_camp_refusals()
    check_unbound_spells()
    check_reflection()
    check_cast_show()
    check_heal_in_camp()
