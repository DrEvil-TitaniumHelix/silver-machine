from pathlib import Path
from tempfile import TemporaryDirectory
from .menu import Game
from ._creation_test import create_party
from . import creation, camp, inventory, shop, temple, rules, save


def scenario():
    with TemporaryDirectory(prefix='sm-dkk-services-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        game.player = lambda kind, options, state, **info: 0
        char = game.s.party[0]
        equipped = next(item for item in char.items if item[shop.I['readied']])
        inventory.toggle_ready(game, char, equipped)
        rules.recalc_stats(char)
        assert equipped[shop.I['readied']] == 0
        inventory.toggle_ready(game, char, equipped)
        rules.recalc_stats(char)
        assert equipped[shop.I['readied']] == 1
        shop.pool_money(game.s)
        assert game.s.treasure_money[4] == 3000
        shop.share_money(game.s)
        assert all(shop.coins(c)[4] == 500 for c in game.s.party)
        item = bytearray(equipped)
        item[shop.I['readied']] = 0
        item[shop.I['quantity']] = 0
        shop.put_word(item, shop.I['value'], 100)
        game.s.r1[shop.PRICE_CELL] = 16
        game.s.treasure_items = [item]
        shop.set_creature_steel(char, 30)
        game.s.treasure_money[4] = 80
        choices = iter((0, 1))
        before_count = len(char.items)
        game.player = lambda kind, options, state, **info: next(choices)
        shop.buy_menu(game, char)
        assert shop.coins(char)[4] == 0 and game.s.treasure_money[4] == 10
        assert len(char.items) == before_count + 1
        original_coins = shop.coins(char)
        r = rules.record(char)
        r.set('hp', 1)
        temple.cure(game, char, 4)
        assert r.get('hp') > 1 and shop.coins(char) == original_coins
        game.player = lambda kind, options, state, **info: 0
        creation.save_menu(game)
        snapshot = save.load(tmp, 'A')
        assert len(snapshot.members) == 6 and len(bytes(snapshot.game)) == 2913
        for member, live in zip(snapshot.members.values(), game.s.party):
            assert bytes(member['GAM'][0]) == bytes(live.b[:216])
            assert b''.join(bytes(r) for r in member.get('WIZ', ())) == bytes(live.b[216:])
        game.player = lambda kind, options, state, **info: options.index('Exit')
        inventory.view(game, char)
        assert not camp.run(game)
        return game.s.hash(), tuple(game.trace)


def slots():
    import os
    with TemporaryDirectory(prefix='sm-dkk-slot-') as tmp:
        before = os.environ.get('SM_SAVE_ROOT')
        os.environ['SM_SAVE_ROOT'] = tmp
        try:
            game = Game(None)
            game.roster_directory = creation.save_directory()
            create_party(game)
            game.player = lambda *a, **k: 0
            creation.save_menu(game)
            again = Game(None, slot='a')
            assert again.loaded and len(again.s.party) == 6 and again.vm.resuming
            assert not Game(None, slot='B').loaded
        finally:
            if before is None: del os.environ['SM_SAVE_ROOT']
            else: os.environ['SM_SAVE_ROOT'] = before


def test():
    slots()
    assert scenario() == scenario()
    movement_and_item_effects()
    camp_rules()
    fix_rest_duration()
    camp_linked_characters()
    camp_magic_rules()
    grimoire_keys()
    alter_rules()
    temple_rules()
    shop_rules()
    return_for_money()
    money_notice_frames()
    money_rules()
    service_highlights()
    time_rules()
    walking_roster()
    study_rest_rules()


def walking_roster():
    from . import effects
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        game.s.mode = 4
        first, second = game.s.party[:2]
        before = [camp.roster_values(char) for char in (first, second)]
        for char in (first, second):
            char.effects.clear()
            effects.add_effect(char, 13, 1, 0, True)
        effects.add_effect(first, 13, 2, 0, True)
        camp.advance(game, 1)
        assert game.vm.rows_shown == dict(enumerate(before))
        assert first.b[camp.F['ac']] == before[0][1] - 2
        camp.advance(game, 1)
        assert first.b[camp.F['ac']] == before[0][1] - 4
        assert game.vm.rows_shown[0] == before[0]

        game.s.mode, game.s.r0[0x1F7] = 3, 1
        camp.repaint_walking_row(game, first)
        game.s.mode, game.vm.display['kind'] = 4, 'BIGPIC'
        camp.repaint_walking_row(game, first)
        assert game.vm.rows_shown[0] == before[0]
        game.vm.display['kind'] = None
        camp.repaint_walking_row(game, first)
        repainted = camp.roster_values(first)
        effects.add_effect(first, 13, 1, 0, True)
        camp.advance(game, 1)
        assert game.vm.rows_shown == {0: repainted, 1: before[1]}
        assert first.b[camp.F['ac']] == repainted[1] - 2

        first.b[camp.F['hp']], first.b[camp.F['hp_max']] = 6, 8
        notices = []
        def notice(kind, options, state, **info):
            notices.append((info['creature_text'], game.vm.rows_shown[0], camp.roster_values(first)))
            return 0
        game.player = notice
        ac = first.b[camp.F['ac']]
        for effect, hp_before, hp_after, message in (
                (15, 6, 5, game.assets.text('onePointDamage') + game.assets.text('fromMagic')),
                (62, 5, 6, game.assets.text('partiallyHealedText'))):
            held = game.vm.rows_shown[0]
            first.effects.clear()
            effects.add_effect(first, effect, 1, 0, True)
            effects.add_effect(first, 13, 1, 0, True)
            camp.advance(game, 1)
            notice_hp = hp_before if effect == 15 else hp_after
            assert notices == [(message, held, (notice_hp, ac))]
            assert game.vm.rows_shown == {0: (hp_after, ac), 1: before[1]}
            ac -= 2
            assert camp.roster_values(first) == (hp_after, ac)
            notices.clear()

        first.effects.clear()
        effects.add_effect(first, 101, 0, 0, False)
        effects.add_effect(first, 15, 1, 0, True)
        camp.advance(game, 1)
        assert not notices and camp.roster_values(first) == (6, ac)
        assert game.vm.rows_shown == {1: before[1]}


def time_rules():
    from copy import deepcopy
    from unittest.mock import patch
    from . import effects
    word = lambda raw, offset: int.from_bytes(raw[offset:offset + 2], 'little')
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        s, f = game.s, camp.F
        first = s.party[1]
        s.party[:] = [first]
        extra = deepcopy(first)
        s.monsters[:] = [extra]
        seen = []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        for char in s.chars():
            char.effects.clear()
            shop.put_word(char.b, f['age'], 65535)
        game.age_pass = True
        s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7] = [0, 0, 0, 0, 0, 0, 255]
        camp.advance(game, 2, 6)
        assert all(word(char.b, f['age']) == 1 for char in s.chars())
        assert s.r0[camp.CLOCK_CELL + 6] == 1 and not game.age_pass
        clock = [10, 65535, 0, 0, 0, 0, 0]
        camp.validate_clock(game, clock)
        assert clock == [0] * 7
        rest = [0, 0, 0, 0, 65535, 0, 0]
        camp.validate_rest(game, rest)
        assert rest[4] == 99
        rest = [0, 0, 0, 0, 30, 2184, 0]
        camp.validate_rest(game, rest)
        assert rest[4] == 99
        rest = [0, 0, 0, 0, 376, 2184, 0]
        camp.validate_rest(game, rest)
        assert rest[4:6] == [0, 0]
        rest = [0, 0, 0, 0, 130, 65535, 0]
        camp.validate_rest(game, rest)
        assert rest[4:6] == [100, 0]
        effects.add_effect(first, 55, 65000, 0, False)
        effects.add_effect(extra, 55, 65000, 0, False)
        camp.advance(game, 1, 6)
        assert all(word(char.effects[0], 1) == 5352 for char in s.chars())
        s.mode = camp.CAMPING
        s.g['camp.effects_running'] = [0, 1] + [0] * 70
        s.r1[creation.PARTY_SIZE] = 1
        camp.advance(game, 5)
        assert word(extra.effects[0], 1) == 5352
        s.r1[creation.PARTY_SIZE] = 2
        camp.advance(game, 5)
        assert word(extra.effects[0], 1) == 5347
        s.r1[creation.PARTY_SIZE] = 0
        camp.advance(game, 5)
        assert word(extra.effects[0], 1) == 5347
        s.g['camp.effects_running'][0] = 1
        camp.advance(game, 5)
        assert word(first.effects[0], 1) == 5347
        assert word(extra.effects[0], 1) == 5342
        s.mode = 4
        camp.advance(game, 0)
        assert s.g['camp.effects_running'] == [1] * 72
        first.effects.clear()
        extra.effects.clear()
        effects.add_effect(extra, 12, 1, 0, False)
        with patch.object(effects, 'remove_effect', wraps=effects.remove_effect) as remove:
            camp.advance(game, 1)
            assert remove.call_count == 1 and not extra.effects
        assert s.g['camp.effects_running'][:2] == [0, 0]
        effects.add_effect(first, 62, 1, 0, True)
        s.mode = camp.CAMPING
        s.g['camp.effects_running'] = [1] * 72
        camp.advance(game, 20)
        assert word(first.effects[0], 1) == 60 and not s.g['camp.effects_running'][0]
        camp.advance(game, 5)
        assert word(first.effects[0], 1) == 60
        s.mode = 4
        camp.advance(game, 5)
        assert word(first.effects[0], 1) == 55 and s.g['camp.effects_running'][0]
        first.effects.clear()
        seen.clear()
        for char in s.chars():
            char.b[f['hp']] = 1
            char.b[f['status']], char.b[f['active']] = 0, 1
            char.b[f['memorized']:f['memorized'] + 74] = bytes(74)
            char.b[f['preparation']] = 0
        s.g['camp.heal_ticks'] = 65535
        camp.heal_tick(game)
        assert s.g['camp.heal_ticks'] == 0 and not seen
        def heal_notice(kind, options, state, **info):
            seen.append((kind, options, info))
            assert game.vm.roster_shown == (None if info['redraw_party'] else 0)
            assert game.vm.ready_shown == (None if info['redraw_party'] else (0,))
            game.vm.out.append(info['prompt'])
            return 0
        game.player = heal_notice
        game.vm.roster_shown, game.vm.ready_shown = 0, (0,)
        s.g['camp.heal_ticks'] = 287
        camp.heal_tick(game)
        assert all(char.b[f['hp']] == 2 for char in s.chars())
        assert len(seen) == 1 and seen[-1][2]['redraw_party'] and seen[-1][2]['colour'] == 10 and seen[-1][2]['timed'] == 1
        assert game.vm.text_start == len(game.vm.out)
        for char in s.chars(): char.b[f['status']] = 8
        game.vm.roster_shown, game.vm.ready_shown = 0, (0,)
        s.g['camp.heal_ticks'] = 287
        camp.heal_tick(game)
        assert len(seen) == 2 and not seen[-1][2]['redraw_party']
        assert game.vm.text_start == len(game.vm.out)
        for char in s.chars(): char.b[f['status']] = 0
        seen.clear()
        s.mode = camp.CAMPING
        s.r1[camp.REST_PERIOD_CELL] = 0
        s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7] = [0] * 7
        game.rest_poll = True
        choices = iter(('Rest', 'Stop', 'No', 'Stop', 'Yes'))
        def player(kind, options, state, **info):
            seen.append((kind, options, info))
            return options.index(next(choices))
        game.player = player
        rest = [0, 0, 0, 1, 0, 0, 0]
        assert not camp.camp_rest(game, rest, True)
        assert rest == [0, 5, 5, 0, 0, 0, 0] and s.r0[camp.CLOCK_CELL + 1] == 5
        assert [kind for kind, _, _ in seen] == ['CAMP_REST', 'CAMP_RESTING', 'CAMP_CONFIRM', 'CAMP_RESTING', 'CAMP_CONFIRM']
        assert all(info['start'] == 0 for kind, _, info in seen if kind == 'CAMP_CONFIRM')
        assert s.g['no_border'] == 0 and not s.g['camp.rest_active']
        seen.clear()
        s.g['camp.heal_ticks'] = 285
        choices = iter(('Hours', 'Rest', 'Continue', 'Stop', 'No', 'Continue', 'Continue', 'Continue', 'Continue', 'Continue', 'Stop', 'Yes'))
        rest = [0, 0, 5, 0, 0, 0, 0]
        assert not camp.camp_rest(game, rest, True)
        polls = [(info['minutes'], info['field']) for kind, _, info in seen if kind == 'CAMP_RESTING']
        assert polls == [(50, camp.HOURS), (50, camp.HOURS), (45, 0), (35, 0), (35, 0), (25, 0), (25, 0)]
        assert [info['minutes'] for kind, _, info in seen if kind == 'CAMP_CONFIRM'] == [45, 20]
        assert [info['minutes'] for kind, _, info in seen if kind == 'ACK'] == [35]
        assert rest[camp.TENS] == 2 and not rest[camp.MINUTES]
        seen.clear()
        extra.b[f['memorized'] + 73] = 131
        choices = iter(('Rest', 'Continue', 'Continue', 'Continue', 'Stop', 'Yes'))
        assert not camp.camp_rest(game, [0, 0, 3, 0, 0, 0, 0], True)
        assert [info['minutes'] for kind, _, info in seen if kind == 'CAMP_RESTING'] == [30, 25, 25]
        assert [info['spell'] for kind, _, info in seen if kind == 'ACK'] == [3]
        def cancel_rest(kind, options, state, **info):
            assert kind == 'CAMP_REST' and game.vm.text_start == len(game.vm.out)
            game.vm.out.append(info['rest_label'])
            return options.index('Exit')
        game.vm.out.append('Before rest')
        game.player = cancel_rest
        assert not camp.camp_rest(game, rest, True) and s.g['no_border'] == 0
        assert game.vm.text_start == len(game.vm.out)
        assert s.g['camp.effects_running'] == [1] * 72
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        extra.b[f['memorized'] + 73] = 131
        rest = [0, 5, 0, 0, 0, 0, 0]
        assert not camp.camp_rest(game, rest, False)
        assert extra.b[f['memorized'] + 73] == 3 and seen[-1][2]['spell'] == 3
        extra.b[f['memorized'] + 73] = 131
        s.g['camp.rest_active'] = True
        assert camp.next_pending(game, extra, False) == (0, False) and extra.b[f['memorized'] + 73] == 131
        s.g['camp.rest_active'] = False
        extra.b[f['memorized'] + 73] = 0
        s.r1[camp.REST_PERIOD_CELL], s.r1[camp.REST_CHANCE_CELL] = 1, 100
        s.g['camp.rest_ticks'] = 65535
        with patch.object(camp, 'dice', return_value=1) as roll:
            assert not camp.camp_rest(game, [0, 5, 0, 0, 0, 0, 0], False)
            assert roll.call_count == 0 and s.g['camp.rest_ticks'] == 0
            def interruption(kind, options, state, **info):
                assert game.vm.text_start == len(game.vm.out)
                seen.append((kind, options, info))
                game.vm.out.append(info['prompt'])
                return 0
            game.vm.out.append('Before interruption')
            game.player = interruption
            assert camp.camp_rest(game, [0, 5, 0, 0, 0, 0, 0], False)
            assert roll.call_count == 1 and s.g['no_border'] == 0
            assert game.vm.text_start == len(game.vm.out)
        assert seen[-1][2]['colour'] == 15 and seen[-1][2]['clear_first']
        info = camp.rest_info(game, [0, 255, 1, 9, 100, 0, 0], camp.HOURS)
        assert info['rest_digits'] == ('10', '09', '09') and info['rest_colours'] == (10, 15, 10)


def money_rules():
    from unittest.mock import patch
    from .records import Item
    from .save_start import item_pool
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        s = game.s
        first, second, third = s.party[:3]
        s.party[:] = [first, second, third]
        extra = rules.character(bytes(first.b))
        s.monsters[:] = [extra]
        for char, npc in ((first, 0), (second, 179), (third, 1), (extra, 179)):
            char.b[shop.F['npc']] = npc
            shop.put_coins(char, [0, 0, 0, 0, 10, 1, 1])
            shop.put_word(char.b, shop.F['weight'], 12)
        s.treasure_money[:] = [7, 8, 9, 10, 0, 0, 0]
        shop.pool_money(s)
        assert s.treasure_money == [7, 8, 9, 10, 30, 3, 3]
        assert s.g['treasure_active'] == 1
        assert shop.coins(third)[4:] == [10, 1, 1] and shop.weight(extra) == 0
        for char in s.chars():
            shop.put_coins(char, [0] * 7)
            shop.put_word(char.b, shop.F['weight'], 0)
        s.treasure_money[4:] = [300, 0, 0]
        shop.share_money(s)
        assert [shop.coins(char)[4] for char in s.chars()] == [100, 0, 100, 0]
        assert s.treasure_money == [7, 8, 9, 10, 0, 0, 0] and not shop.has_money(s)
        assert s.g['treasure_active'] == 0
        s.monsters.clear()
        for char in s.party:
            char.b[shop.F['npc']] = 1
            shop.put_word(char.b, shop.F['weight'], 0)
        first.b[shop.F['npc']] = 0
        s.treasure_money[4] = 65535
        with patch.object(shop, 'carrying_capacity', return_value=0): shop.share_money(s)
        assert s.treasure_money[4] == 65533
        first.b[shop.F['npc']] = 1
        s.treasure_money[4:] = [-1, 0, 0]
        shop.share_money(s)
        assert s.treasure_money[4:] == [0, 0, 0]
        s.treasure_money[4] = 1
        try: shop.share_money(s)
        except ZeroDivisionError: pass
        else: raise AssertionError('positive pool without poolers must divide by zero')
        s.treasure_money[4] = 0x7FFFFFFF
        shop.change_pool(s, 4, 1)
        assert s.treasure_money[4] == -0x80000000
        first.b[shop.F['npc']] = 0
        shop.put_coins(first, [0] * 7)
        shop.put_word(first.b, shop.F['weight'], 1062)
        s.treasure_money[4] = 65100
        assert shop.check_overload(first, 64473)[0]
        assert not shop.check_overload(first, 64474)[0]
        shop.take_money(game, first, 65100, 4)
        assert shop.coins(first)[4] == 65100 and shop.weight(first) == 626 and s.treasure_money[4] == 0
        shop.put_coins(first, [0] * 7)
        shop.put_word(first.b, shop.F['weight'], shop.carrying_capacity(first) - 1)
        s.treasure_money[4:] = [1, 0, 0]
        seen = []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        shop.take_money(game, first, 100, 4)
        assert s.treasure_money[4] == 1 and shop.coins(first)[4] == 0
        assert len(seen) == 1 and seen[0][2]['prompt'] == game.assets.text('tradeOverloadMessage')
        assert seen[0][2]['timed'] == 1 and seen[0][2]['message_colour'] == 10
        assert seen[0][2]['blank_bottom_pause'] and seen[0][2]['flush_keys']
        shop.take_money(game, first, 1, 4)
        assert s.treasure_money[4] == 0 and shop.coins(first)[4] == 1 and len(seen) == 1
        s.treasure_money[4:] = [65537, 3, 2]
        choices = iter((1, 2, 3))
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
        shop.put_word(first.b, shop.F['weight'], 0)
        shop.take_menu(game, first)
        assert s.g['treasure_active'] == 1
        assert seen[0][1][:3] == ('Jewelry 2', 'Gems 3', 'Steel 65537')
        assert seen[0][2]['window'] == '2 2 15 8'
        assert seen[1][2]['prompt'] == 'How many Gems  will you take? ' and shop.coins(first)[5] == 2
        assert seen[2][2]['start'] == 1
        s.treasure_money[4:] = [2, 2, 2]
        choices = iter((2, 1, 2, 1, 1, 2, 1))
        seen.clear()
        shop.take_menu(game, first)
        assert [info['start'] for kind, _, info in seen if kind == 'LIST'] == [0, 2, 1, 0]
        assert s.treasure_money[4:] == [0, 0, 2]
        shop.put_word(first.b, shop.F['weight'], shop.carrying_capacity(first))
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        shop.give_steel(game, first, 7)
        assert s.treasure_money[4] == 7
        assert len(seen) == 1 and seen[0][2]['prompt'] == game.assets.text('overloadPoolText')
        assert seen[0][2]['timed'] == 1 and seen[0][2]['message_colour'] == 10
        assert seen[0][2]['blank_bottom_pause'] and seen[0][2]['flush_keys']
        shop.put_word(first.b, shop.F['weight'], 0)
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
        s.treasure_money[4:] = [1, 0, 0]
        choices = iter((0, 1))
        shop.take_menu(game, first)
        assert s.g['treasure_active'] == 0
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or (999 if options is None else 0)
        assert shop.input_number(game, 65537, 'q' * 50) == 1 and len(seen[-1][2]['prompt']) == 40
        first.items.clear()
        shop.put_coins(first, [0] * 7)
        before = bytes(first.b)
        assert shop.appraise(game, first) is False and bytes(first.b) == before
        assert seen[-1][0] == 'ACK' and seen[-1][2]['prompt'] == game.assets.text('noGemsMessage')
        assert seen[-1][2]['timed'] == 1 and seen[-1][2]['message_colour'] == 10
        shop.put_coins(first, [0, 0, 0, 0, 0, 1, 0])
        shop.put_word(first.b, shop.F['weight'], 999)
        s.r1[0x372] = 3
        choices, seen = iter((1,)), []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
        assert shop.appraise(game, first) is True and shop.weight(first) == 1
        assert seen[0][2]['count_lines'] == (game.assets.text('gemsCountLabel') + '1', game.assets.text('jewelryCountLabel') + '0')
        for kind in (shop.GEMS, shop.JEWELRY):
            purse = [0] * 7
            purse[kind] = 1
            shop.put_coins(first, purse)
            choices = iter((0, 1))
            with patch.object(shop, 'detached_item', return_value=None):
                assert shop.appraise(game, first)
            assert shop.coins(first) == purse and not first.items
        for existing in (False, True):
            first.items[:] = [Item().data] if existing else []
            shop.put_coins(first, [0, 0, 0, 0, 0, 1, 0])
            rules.recalc_stats(first, 3)
            choices, seen = iter((0, 1)), []
            game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
            slot = item_pool(game).allocate()
            with patch.object(shop, 'dice', return_value=100): assert shop.appraise(game, first)
            assert slot[shop.I['type']] == shop.GEM_TYPE
            assert len(first.items) == (2 if existing else 0) and shop.coins(first)[5] == 0
            assert seen[1][1] == ('Sell', 'Keep') and seen[1][2]['prompt'] == ''
            assert len(seen) == 2
            if existing:
                kept = first.items[-1]
                assert kept is slot
                assert kept[shop.I['type']] == 47 and shop.word_at(kept, shop.I['value']) == 2500
                assert shop.weight(first) == 1 and first.b[shop.F['item_count']] == 2
        first.items.clear()
        shop.put_coins(first, [0, 0, 0, 0, 0, 1, 0])
        shop.put_word(first.b, shop.F['weight'], shop.carrying_capacity(first))
        s.treasure_money[4:] = [0, 0, 0]
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info, tuple(state.s.treasure_money))) or 0
        with patch.object(shop, 'dice', return_value=25): shop.appraise(game, first)
        assert seen[1][1] == ('Sell',) and seen[2][3][4] == 0
        assert s.treasure_money[4] == 5 and shop.coins(first)[4] == 0
        first.items[:] = [Item().data]
        shop.put_coins(first, [0, 0, 0, 0, 0, 1, 2])
        rules.recalc_stats(first, 3)
        seen.clear()
        def defaults(kind, options, state, **info):
            seen.append((kind, options, info))
            return options.index('Jewelry') if len(seen) == 1 else info.get('start', 0)
        game.player = defaults
        game.menu_highlight = 0
        with patch.object(shop, 'dice', return_value=1): assert shop.appraise(game, first)
        assert [info['start'] for _, _, info in seen] == [0, 1, 1, 1, 1]
        assert seen[-1][1] == ('Gems', 'Exit') and shop.coins(first)[5:] == [1, 0]
        assert len(first.items) == 3 and all(raw[shop.I['name_ids'] + 2] == shop.JEWEL_NAME for raw in first.items[1:])
        first.b[shop.F['item_count']] = 16
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or info.get('start', 0)
        assert shop.appraise_one(game, first, shop.JEWEL_NAME, 1, selected=1) == 0
        assert seen[0][1] == ('Sell',) and seen[0][2]['start'] == 0
        for mode in (1, 2, 6, 7):
            for pool in (65000, 0x7FFFFFFF):
                s.mode, s.g['treasure_active'] = mode, 9
                s.treasure_money[4:] = [pool, 2, 3]
                shop.put_coins(first, [0, 0, 0, 0, 1000, 0, 0])
                shop.put_word(first.b, shop.F['weight'], 1000)
                game.player = lambda kind, options, state, **info: 1000 if options is None else 0
                inventory.drop_coins(game, first)
                total = pool + (1000 if mode in (1, 6, 7) else 0)
                expected = (total + 0x80000000) % 0x100000000 - 0x80000000
                assert s.treasure_money[4:] == [expected, 2, 3] and s.g['treasure_active'] == 9
                assert shop.coins(first)[4] == 0 and shop.weight(first) == 0


def shop_rules():
    from unittest.mock import patch
    from . import effects
    from .records import Item
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        char = game.s.party[0]
        item = Item()
        item.set('name_ids', bytes((0, 0, 1))); item.set('type', 30)
        item.set('quantity', 20); item.set('weight', 1); item.set('value', 100)
        for level, expected in ((1, 120), (2, 240), (4, 500), (8, 1000), (16, 2000), (32, 4000), (64, 8000), (128, 16000)):
            game.s.r1[shop.PRICE_CELL] = level
            assert shop.price_of(game.s, item.data) == expected
        item.set('quantity', 2); item.set('value', 32768)
        assert shop.price_of(game.s, item.data) == 1
        item.set('value', 0)
        assert shop.price_of(game.s, item.data) == 16 and item.get('value') == 1
        game.s.r1[shop.PRICE_CELL] = 16
        item.set('quantity', 0); item.set('value', 100)
        char.items[:] = [bytearray(item.data) for _ in range(16)]
        item.set('quantity', 1)
        assert shop.cannot_carry(char, item.data, game=game)
        assert not shop.cannot_carry(char, item.data, may_stack=True, game=game)
        for slot in range(3):
            item.data[shop.I['powers'] + slot] = 1
            assert shop.cannot_carry(char, item.data, may_stack=True, game=game)
            item.data[shop.I['powers'] + slot] = 0
        item.set('weight', 65535)
        assert shop.cannot_carry(char, item.data, may_stack=True, game=game)
        item.set('weight', 1); item.set('quantity', 0)
        char.items[:] = [bytearray(item.data)]
        game.s.r1[0x372] = 3
        assert shop.give_item_copy(game, char, item.data)
        assert len(char.items) == 2 and char.items[-1] is not item.data
        stored_move = rules.record(char).get('move')
        rules.recalc_stats(char, 3)
        assert rules.record(char).get('move') == stored_move
        game.s.treasure_items[:] = [bytearray(item.data), bytearray(item.data)]
        shop.set_creature_steel(char, 30)
        game.s.treasure_money[:] = [17, 18, 19, 20, 70000, 21, 22]
        choices = iter((1, 2))
        game.player = lambda kind, options, state, **info: next(choices)
        with patch.object(shop, 'detached_item', return_value=None):
            shop.buy_menu(game, char)
        assert len(char.items) == 2 and shop.coins(char)[shop.STEEL] == 30
        assert game.s.treasure_money[shop.STEEL] == 70000
        choices, seen = iter((1, 2)), []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
        shop.buy_menu(game, char)
        assert shop.coins(char)[4] == 0 and game.s.treasure_money == [17, 18, 19, 20, 69930, 21, 22]
        assert seen[1][2]['start'] == 1 and seen[0][2]['window'] == '1 1 38 18'
        assert seen[0][2]['money_lines'][1] == game.assets.text('poolLabel') + '70000'.rjust(10)
        assert seen[1][2]['message'] == shop.member_name(char) + game.assets.text('buysAText') + shop.item_name(game, item.data)
        first, second = char.items[-2:]
        first[:] = second
        assert first is not second
        assert any(first is slot for slot in game.item_pool.slots)
        assert any(second is slot for slot in game.item_pool.slots)
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        shop.sell(game, char, second)
        assert char.items[-1] is first and len(seen) == 2
        assert first[shop.I['type']] == 30 and second[shop.I['type']] == 0
        assert all(held is not second for held in char.items)
        assert seen[0][2]['start'] == 0 and seen[0][2]['prompt'] == game.assets.text('dealQuery')
        assert seen[1][2]['prompt'] == game.assets.text('soldText') and seen[1][2]['offer'] == seen[0][2]['offer']
        second = bytearray(first)
        shop.put_word(second, shop.I['value'], 10000)
        second[shop.I['quantity']] = 0
        char.items.append(second)
        seen.clear()
        shop.sell(game, char, second)
        assert [info['prompt'] for kind, _, info in seen if kind == 'ACK'] == [game.assets.text('soldText'), game.assets.text('overloadPoolText')]
        assert all(info['timed'] == 1 and info['message_colour'] == 10 and info['offer'] == seen[0][2]['offer'] for kind, _, info in seen if kind == 'ACK')
        shop.set_creature_steel(char, 0)
        game.s.treasure_money[4] = 0
        seen.clear()
        assert not shop.identify(game, char, first)
        assert seen[-1][2]['prompt'] == game.assets.text('notEnoughMoneyText') and seen[-1][2]['offer'] == seen[0][2]['offer']
        assert seen[-1][2]['timed'] == 1 and seen[-1][2]['message_colour'] == 10
        first[shop.I['unidentified']] = 0xFF
        shop.set_creature_steel(char, 30)
        game.s.treasure_money[:] = [17, 18, 19, 20, 70000, 21, 22]
        seen.clear()
        assert shop.identify(game, char, first)
        assert len(seen) == 3 and first[shop.I['unidentified']] == 0xF8
        assert shop.coins(char)[4] == 0 and game.s.treasure_money == [17, 18, 19, 20, 69930, 21, 22]
        seen.clear()
        assert not shop.identify(game, char, first) and len(seen) == 2
        first[shop.I['type']], first[shop.I['powers']] = 39, 128
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or info.get('start', 0)
        assert not shop.item_available(game, char, first) and seen[-1][2]['start'] == 1
        first[shop.I['bonus']] = 1
        for member in game.s.party: member.effects.clear()
        enemy = rules.character(bytes(char.b))
        effects.add_effect(enemy, 5, 1, 0, False)
        game.s.monsters[:] = [enemy]
        assert shop.item_name(game, first).startswith('* ')
        game.s.monsters.clear()
        game.s.sel = 0
        actions = iter(('char-down', 'View', 'Pool', 'Exit', 'Yes', 'Exit', 'No'))
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or options.index(next(actions))
        mode = game.s.mode
        with patch.object(shop, 'view_items') as viewed:
            shop.run(game)
            viewed.assert_called_once_with(game, game.s.party[1])
        assert game.s.mode == mode and seen[0][2]['start'] == 0
        assert all(kind != 'WHO' for kind, options, info in seen)
        confirmations = [info for kind, options, info in seen if kind == shop.Kind.CONFIRM.value]
        assert len(confirmations) == 2 and all(info['start'] == 0 and info['prompt'] == '' for info in confirmations)
        assert confirmations[0]['offer'] == game.assets.text('leftMoney1') + game.assets.text('leftMoney2')
        main = [info for kind, options, info in seen if kind == shop.Kind.MENU.value]
        assert main[-2]['selected'] == 2 and main[-1]['selected'] == 6
        assert main[-2]['start'] == 2
        assert confirmations[0]['colours'] == (10, 15) and confirmations[0]['clear_first'] == (True, False)
        game.player = lambda kind, options, state, **info: info.get('start', 0)
        assert shop.main_menu(game, ('Buy', 'View', 'Pool', 'Appraise'), 6) == ('Buy', 0)


def return_for_money():
    for service in (shop, temple):
        with TemporaryDirectory() as tmp:
            game = Game(None)
            game.roster_directory = Path(tmp)
            create_party(game)
            greeting = game.assets.text('leftMoney1')
            game.vm.out.append(greeting)
            steps = iter(('Pool', 'Exit', 'Yes', 'Exit', 'No'))
            visible = []
            game.s.mode, game.s.prev_mode = 4, 3
            game.vm.roster_shown = (game.s.sel + 1) % len(game.s.party)
            game.vm.ready_shown = (0,) * len(game.s.party)
            def player(kind, options, state, **info):
                if kind == service.Kind.MENU.value:
                    assert game.s.mode == shop.SHOP_TEMPLE
                    assert game.s.g['dkk.runtime']['noncombat_prepared'] == 1
                    assert game.vm.roster_shown is None and game.vm.ready_shown is None
                    game.vm.roster_shown = game.s.sel
                visible.append(game.vm.out[game.vm.text_start:])
                return options.index(next(steps))
            game.player = player
            service.run(game)
            after_pool = [] if service is shop else [greeting]
            assert visible == [[greeting], after_pool, after_pool, [], []]
            assert game.vm.roster_shown is None
            assert (game.s.mode, game.s.prev_mode) == ((4, 4) if service is shop else (1, 3))


def money_notice_frames():
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        char = game.s.selc()
        game.s.mode = shop.SHOP_TEMPLE
        shop.put_coins(char, [0] * 7)
        shop.put_word(char.b, shop.F['weight'], shop.carrying_capacity(char))
        def play(limit):
            game.ask('TEMPLE', ('Appraise', 'Exit'))
            shop.appraise(game, char)
            game.ask('TEMPLE', ('Take', 'Exit'))
            shop.take_money(game, char, 1, shop.STEEL)
            game.ask('TEMPLE', ('Take', 'Exit'))
        game.play = play
        session = Session(profile='dkk', game=game)
        try:
            ui = screen.Controller(session)
            for label in ('noGemsMessage', 'tradeOverloadMessage'):
                ui.choose(0)
                assert session.decision['kind'] == 'TEMPLE'
                expected = screen.Frame()
                expected.text(0, 24, game.assets.text(label), ui.assets, 10, 40)
                assert ui.held()['frame'].rows[192:200] == expected.rows[192:200]
        finally: session.close()


def service_highlights():
    from types import SimpleNamespace
    from unittest.mock import patch
    from .ui import screen
    from . import services_alter
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        steps, seen = iter(()), []
        def player(kind, options, state, **info):
            expected, action, cursor, escaping = next(steps)
            assert info.get('start') == expected, (kind, options, info, expected)
            seen.append((kind, options, info))
            answer = options.index(action)
            decision = dict(kind=kind, options=options, info=info)
            ui = SimpleNamespace(session=SimpleNamespace(decision=decision, game=game), selected=cursor, escaping=escaping)
            screen.keep_highlight(ui, answer)
            return answer
        game.player = player
        options = ('Buy', 'View', 'Pool', 'Appraise')
        steps = iter(((0, 'char-down', 2, False), (2, 'Exit', 2, True)))
        before = game.s.sel
        assert shop.main_menu(game, options, 0) == ('Exit', 2)
        assert game.s.sel == (before + 1) % len(game.s.party)
        assert seen[-1][2]['escape_choice'] == 4
        steps = iter(((2, 'Pool', 0, False),))
        assert shop.main_menu(game, options, 2) == ('Pool', 2)
        steps = iter(((2, 'Take', 2, False),))
        assert shop.main_menu(game, ('Buy', 'View', 'Take', 'Pool', 'Share', 'Appraise'), 2) == ('Take', 2)
        steps = iter(((2, 'Exit', 1, True),))
        assert temple.main_menu(game, ('Heal', 'View', 'Pool', 'Appraise')) is None
        assert game.menu_highlight == 1

        steps = iter(((0, 'char-down', 2, False), (2, 'Exit', 2, True)))
        before = game.s.sel
        assert camp.member_menu(game, '', ('Cast', 'Memorize', 'Scribe', 'Display', 'Rest')) is None
        assert game.s.sel == (before + 1) % len(game.s.party) and game.menu_highlight == 2
        assert seen[-1][2]['escape_choice'] == 5
        steps = iter(((0, 'char-down', 1, False), (1, 'Exit', 1, True)))
        services_alter.order(game)
        assert game.menu_highlight == 1
        steps = iter(((0, 'Select', 0, False), (0, 'char-up', 1, False), (1, 'Exit', 1, True)))
        before = game.s.party[:]
        selected = game.s.sel
        services_alter.order(game)
        assert game.s.sel == (selected - 1) % len(before)
        assert game.s.party[game.s.sel] is before[selected]
        game.s.g['dkk.delay'] = 4
        steps = iter(((0, 'char-down', 1, False), (1, 'Exit', 1, True)))
        services_alter.speed(game)
        assert game.s.g['dkk.delay'] == 3 and game.menu_highlight == 1
        game.s.g['dkk.delay'] = 8
        steps = iter(((0, 'Slower', 1, False), (1, 'Exit', 1, False)))
        services_alter.speed(game)
        assert game.s.g['dkk.delay'] == 9
        game.s.g['dkk.delay'] = 8
        steps = iter(((0, 'char-up', 2, False), (0, 'Exit', 0, True)))
        services_alter.speed(game)
        assert game.s.g['dkk.delay'] == 9 and game.menu_highlight == 0
        steps = iter(((0, 'char-down', 4, False), (0, 'Exit', 0, True)))
        services_alter.run(game)
        assert game.menu_highlight == 0
        steps = iter(((0, 'char-down', 2, False), (2, 'Scribe', 2, False), (2, 'Exit', 2, True)))
        def child(*args): game.menu_highlight = 0
        with patch.object(game.vm, 'service', side_effect=child): assert not camp.magic_menu(game, [0] * 7)
        steps = iter(((0, 'char-down', 4, False), (4, 'Alter', 4, False), (4, 'Exit', 4, True)))
        with patch.object(services_alter, 'run', side_effect=child): assert not camp.run(game)
        steps = iter(((0, 'Rest', 3, False), (None, 'Exit', 6, False), (3, 'Exit', 6, False)))
        assert not camp.run(game)
        assert seen[-1][2]['camp_main'] and seen[-1][2]['query'] == '' and seen[-1][2]['message'] == ''
        game.menu_highlight = 1
        steps = iter(((1, 'View', 1, False),))
        assert temple.main_menu(game, ('Heal', 'View', 'Pool', 'Appraise')) == 1
        char = game.s.selc()
        char.items[:] = [bytearray(shop.Item.SIZE)]
        shop.put_coins(char, [0, 0, 0, 0, 0, 1, 1])
        rules.recalc_stats(char)
        steps = iter(((1, 'Jewelry', 1, False), (1, 'Sell', 1, True), (1, 'Exit', 1, False)))
        with patch.object(shop, 'dice', return_value=1): assert shop.appraise(game, char)
        assert shop.coins(char)[5:] == [1, 0] and len(char.items) == 1
        assert game.menu_highlight == 1


def temple_rules():
    from unittest.mock import patch
    from . import effects
    from .records import Item
    from .town import field, put
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        char = game.s.party[0]
        seen = []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or info.get('start', 1)
        char.effects.clear()
        for index, message in ((0, 'notBlindMessage'), (6, 'notPoisonedMessage'), (7, 'notDeadMessage'), (8, 'notCursedMessage'), (9, 'notStonedMessage'), (10, 'noLostLevelsMessage')):
            char.items.clear()
            put(char, 'race', 3); put(char, 'status', 0)
            for i in range(8): put(char, 'former_levels', field(char, 'levels', i), i)
            before = bytes(char.b), game.s.seed
            temple.cure(game, char, index)
            assert (bytes(char.b), game.s.seed) == before
            assert seen[-1][0] == 'TEMPLE_CONFIRM' and seen[-1][2]['start'] == 1
            assert seen[-1][2]['prompt'] == game.assets.text('castAnywayPrompt')
            assert seen[-1][2]['offer'] == shop.member_name(char) + ' ' + game.assets.text(message)
        before = bytes(char.b), game.s.seed, len(seen)
        temple.cure(game, char, 1)
        assert (bytes(char.b), game.s.seed, len(seen)) == before
        money = tuple(shop.coins(char)), tuple(game.s.treasure_money)
        for index, count, bonus in ((2, 1, 0), (3, 2, 1), (4, 3, 3)):
            put(char, 'hp', 1); put(char, 'hp_max', 100)
            with patch.object(temple, 'dice', return_value=count * 8) as rolled:
                temple.cure(game, char, index)
                rolled.assert_called_once_with(game.s, count, 8)
            assert field(char, 'hp') == 1 + count * 8 + bonus
        put(char, 'hp', 98)
        effects.add_effect(char, 33, 0, 0, False)
        effects.add_effect(char, 61, 0, 0, False)
        with patch.object(temple, 'dice', return_value=4), patch.object(effects, 'recalc_ability') as recalc:
            temple.cure(game, char, 5)
            assert [call.args[2] for call in recalc.call_args_list] == [1, 2]
        assert field(char, 'hp') == 98 and not effects.has(char, 33) and effects.has(char, 61)
        for hp in (0, 7):
            char.effects.clear()
            put(char, 'hp', hp); put(char, 'status', 4); put(char, 'active', 0)
            for ident in (55, 22, 15): effects.add_effect(char, ident, 10, 0, True)
            temple.cure(game, char, 6)
            assert not char.effects and field(char, 'hp') == max(1, hp)
            assert field(char, 'status') == 0 and field(char, 'active') == 1 and not game.effect_busy
        game.effect_busy = True
        with patch.object(effects, 'remove_effect', side_effect=ValueError('stop')):
            try: camp.locked_remove(game, char, 55)
            except ValueError: pass
            else: raise AssertionError('effect failure swallowed')
        assert game.effect_busy
        game.effect_busy = False
        game.player = lambda *args, **info: 0
        with patch.object(game.vm, 'service') as service:
            for race, status, calls in ((0, 6, 0), (1, 1, 0), (2, 6, 1), (3, 1, 1), (3, 0, 0)):
                service.reset_mock()
                put(char, 'race', race); put(char, 'status', status)
                temple.cure(game, char, 7)
                assert service.call_count == calls
                if calls: service.assert_called_once_with('magic', 'temple_spell', char, 75)
            service.reset_mock()
            item = Item(); item.set('cursed', 1); char.items.append(item.data)
            temple.cure(game, char, 8)
            service.assert_called_once_with('magic', 'temple_spell', char, 43)
            service.reset_mock()
            put(char, 'levels', -1, 7); put(char, 'former_levels', 0, 7)
            game.player = lambda *args, **info: (_ for _ in ()).throw(AssertionError('unexpected confirmation'))
            temple.cure(game, char, 10)
            service.assert_called_once_with('magic', 'temple_spell', char, 17)
        put(char, 'status', 7); put(char, 'hp', 30); put(char, 'active', 0)
        temple.cure(game, char, 9)
        assert (field(char, 'status'), field(char, 'hp'), field(char, 'active')) == (0, 1, 1)
        assert (tuple(shop.coins(char)), tuple(game.s.treasure_money)) == money
        choices = iter((1, 11))
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or next(choices)
        temple.heal_menu(game, char)
        assert len(seen[0][1]) == 12 and seen[1][2]['start'] == 1
        assert seen[0][2]['title'] == shop.member_name(char) + game.assets.text('howCanWeHelp')
        assert seen[0][2]['window'] == '2 3 38 15' and seen[0][2]['hp_colour'] == 13
        game.s.sel = 0
        game.s.treasure_money[4] = 123
        actions = iter(('char-down', 'Heal', 'Pool', 'Exit', 'Share', 'Exit'))
        seen.clear()
        def player(kind, options, state, **info):
            seen.append((kind, options, info))
            if kind == 'TEMPLE_CONFIRM': return 0
            return options.index(next(actions))
        game.player = player
        with patch.object(temple, 'heal_menu') as healing:
            temple.run(game)
            healing.assert_called_once_with(game, game.s.party[1])
        assert 'Take' not in seen[0][1] and 'Share' not in seen[0][1]
        confirmation = next(info for kind, options, info in seen if kind == 'TEMPLE_CONFIRM')
        assert confirmation['start'] == 1 and confirmation['prompt'] == ''
        assert confirmation['offer'] == game.assets.text('leftMoney2') and confirmation['clear_first'] == (True, True)
        assert confirmation['messages'] == (game.assets.text('leftMoney1'), game.assets.text('leftMoney2'))
        assert game.s.mode == 1 and not shop.has_money(game.s)
        assert game.s.g['treasure_active'] == 0


def camp_rules():
    from unittest.mock import patch
    from .records import Item
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        char, t = game.s.party[1], camp.tables(game.assets)
        base = camp.F['memorized']
        char.b[base:base + 74] = bytes(74)
        high = next(i for i in range(1, 115) if t.level(i) == 4)
        char.b[base:base + 64] = bytes([high | 128]) * 64
        assert camp.prep_minutes(char, t) == 360 and char.b[camp.F['preparation']] == 6
        char.b[camp.F['active']] = 0
        assert camp.prep_minutes(char, t) == 0 and char.b[camp.F['preparation']] == 0
        scroll = Item()
        scroll.set('type', 39)
        scroll.set('powers', bytes((high | 128, 0, 0)))
        char.items.append(scroll.data)
        assert camp.prep_minutes(char, t) == 420
        scroll.set('type', 1)
        assert camp.prep_minutes(char, t) == 0
        char.b[camp.F['active']] = 1
        char.b[base:base + 74] = bytes(74)
        char.b[base] = 131
        bonus, available, rows = camp.slot_display(game, char, t)
        assert available and game.assets.text('specialSpellsLabel') in rows and ' / ' not in rows
        assert rows.splitlines()[0][13:].startswith(str(camp.slots_remaining(char, 1, 0, t)[0]))
        drained = rules.character(bytes(char.b))
        drained.b[camp.F['robe_order']] = 1
        game.s.r0[0x1F9] = 2
        for raw_level in (128, 255):
            drained.b[camp.F['levels']:camp.F['levels'] + 8] = bytes([raw_level]) * 8
            bonus, _, rows = camp.slot_display(game, drained, t)
            assert bonus == 0 and game.assets.text('specialSpellsLabel') not in rows
            assert not camp.memorizable(drained, t)
        seen = []
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or options.index('Exit')
        before = game.s.mode
        assert not camp.run(game) and game.s.mode == before and char.b[base] == 131
        assert seen[0][2]['message'] == game.assets.text('partyMakesCamp')
        seen.clear()
        camp.display(game)
        assert seen[0][0] == 'ACK' and seen[0][1] == ('Exit',)
        assert seen[0][2]['lines'][0] == ' ' and seen[0][2]['window'] == '1 4 38 22'
        game.player = lambda kind, options, state, **info: options.index('Fix')
        with patch.object(camp, 'fix', return_value=True) as fixed:
            assert camp.run(game) and game.s.mode == before and fixed.call_count == 1
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append(info) or 0
        no_book = game.s.party[0]
        no_book.b[camp.F['active']] = 0
        camp.memorize(game, no_book)
        assert seen[-1]['prompt'].endswith(game.assets.text('cannotMemorizeMessage'))
        assert seen[-1]['timed'] == 1
        assert seen[-1]['creature_name'] == camp.name(no_book) and seen[-1]['creature_colour'] == 12
        assert seen[-1]['creature_text'] == game.assets.text('cannotMemorizeMessage')
        assert (seen[-1]['creature_column'], seen[-1]['creature_row']) == (1, 18)
        game.s.g['no_border'] = 1
        camp.memorize(game, no_book)
        assert seen[-1]['creature_row'] == 19
        game.s.g['no_border'] = 0
        saved_mode = game.s.mode
        speaker = rules.character(bytes(no_book.b))
        speaker.b[camp.F['active']] = speaker.b[camp.F['level_up_ready']] = 1
        for mode, side, expected in ((inventory.IN_COMBAT, 1, (23, 10, 14)), (inventory.LOOT, 1, (1, 18, 13)),
                                     (inventory.IN_COMBAT, 0, (23, 10, 13))):
            game.s.mode, speaker.b[camp.F['side']] = mode, side
            camp.ack(game, game.assets.text('cannotMemorizeMessage'), speaker)
            assert tuple(seen[-1][key] for key in ('creature_column', 'creature_row', 'creature_colour')) == expected
        game.s.mode = saved_mode
        char.b[camp.F['hp_max']], char.b[camp.F['hp']] = 0, 1
        for other in game.s.party:
            if other is not char: other.b[camp.F['hp']] = other.b[camp.F['hp_max']]
        assert camp.missing(game.s) == 65535
        for negative in (128, 255):
            char.b[camp.F['levels']:camp.F['levels'] + 8] = bytes((1, 0, 0, 0, 0, 0, 0, negative))
            char.b[camp.F['abilities'] + 9] = 18
            char.b[camp.F['hp_max']], char.b[camp.F['hp_rolled']] = 100, 60
            camp.raise_dead(char)
            assert char.b[camp.F['hp_max']] == 100
            char.b[camp.F['levels']:camp.F['levels'] + 8] = bytes((0, 0, negative, 1, 0, 0, 0, 0))
            char.b[camp.F['abilities'] + 9] = 17
            char.b[camp.F['hp_max']], char.b[camp.F['hp_rolled']] = 100, 60
            camp.raise_dead(char)
            assert char.b[camp.F['hp_max']] == 80


def fix_rest_duration():
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        game.player = lambda *args, **kwargs: 0
        s, f = game.s, camp.F
        cleric = s.party[1]
        s.party[:], s.sel, s.mode = [cleric], 0, camp.CAMPING
        cleric.b[f['spell_slots']:f['spell_slots'] + 32] = bytes(32)
        cleric.b[f['spell_slots']] = 1
        cleric.b[f['hp_max']], cleric.b[f['hp']] = 10, 5
        s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7] = bytes(7)
        s.r1[camp.REST_PERIOD_CELL] = 0
        game.vm.roster_shown, game.vm.ready_shown = 0, (0,)
        assert not camp.fix(game, [0] * 7)
        assert list(s.r0[camp.CLOCK_CELL + 1:camp.CLOCK_CELL + 4]) == [5, 3, 0]
        assert game.vm.roster_shown is None and game.vm.ready_shown is None
        assert game.vm.info_line.endswith('00:35 camping')


def camp_linked_characters():
    from copy import deepcopy
    from . import effects
    from .magic_lists import I
    from .records import Item
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        s, f = game.s, camp.F
        member = s.party[1]
        extra = deepcopy(member)
        s.party[:], s.monsters[:], s.sel = [member], [extra], 0
        scroll, other = Item(), Item()
        scroll.set('type', 40)
        other.set('type', 5)
        for item in (scroll, other): item.set('powers', bytes((131, 143, 255)))
        extra.items[:] = [scroll.data, other.data]
        extra.b[f['active']], extra.b[f['memorized']], extra.b[f['preparation']] = 0, 131, 4
        powers = slice(I['powers'], I['powers'] + 3)
        def leave(kind, options, state, **info):
            assert scroll.data[powers] == bytes((3, 15, 127))
            scroll.data[powers] = bytes((143, 255, 131))
            return options.index('Exit')
        game.player = leave
        assert not camp.run(game)
        assert scroll.data[powers] == bytes((15, 127, 3)) and other.data[powers] == bytes((131, 143, 255))
        assert extra.b[f['memorized']] == 131 and extra.b[f['preparation']] == 4
        member.effects.clear()
        extra.effects.clear()
        effects.add_effect(extra, 55, 10, 0, False)
        shown = []
        game.player = lambda kind, options, state, **info: shown.append(info) or 0
        camp.display(game)
        assert shown[-1]['lines'] == (' ', camp.name(member), ' <No Spell Effects>', ' ', camp.name(extra), ' Poisoned', ' ')
        for char in s.chars():
            char.b[f['memorized']:f['memorized'] + 74] = bytes(74)
            char.b[f['spell_slots']:f['spell_slots'] + 32] = bytes(32)
            char.b[f['hp']] = char.b[f['hp_max']]
        extra.b[f['active']], extra.b[f['preparation']], extra.b[f['status']] = 1, 0, 0
        extra.b[f['hp']] -= 2
        extra.b[f['memorized']:f['memorized'] + 2] = bytes((3, 67))
        assert camp.missing(s) == 2 and not camp.fix(game, [0] * 7)
        assert not camp.missing(s) and not extra.effects
        assert shown[-1]['creature_text'] == 'is detoxified'
        extra.b[:6] = b'\x05EXTRA'
        s.sel = 1
        for service in (camp, shop, temple):
            visited = []
            keys = iter(('char-down', 'char-up', 'Exit'))
            def navigate(kind, options, state, **info):
                visited.append(info['member'])
                return options.index(next(keys))
            game.player = navigate
            service.run(game)
            assert visited == ['EXTRA', camp.name(member), 'EXTRA']
        s.mode = 4
        s.r1[creation.PARTY_SIZE] = 2
        game.vm.roster_shown = 0
        game.vm.ready_shown = (0,)
        game.vm.out.append('before camp')
        keys = iter(('Alter', 'Order', 'Select', 'char-down', 'Place', 'Exit', 'Drop', 'Yes', 'Continue', 'Exit', 'Exit'))
        def arrange(kind, options, state, **info):
            if kind == 'CAMP_MENU':
                assert game.vm.roster_shown is None and game.vm.ready_shown is None
                assert game.vm.text_start == len(game.vm.out)
            if kind == 'ALTER_ORDER' and info['placing'] and s.sel == 0:
                assert s.party[0] is extra and s.monsters[0] is member
            if kind == 'CAMP_CONFIRM': assert info['prompt'] == 'Drop from party? '
            return options.index(next(keys))
        game.player = arrange
        assert not camp.run(game)
        assert s.chars() == [member] and s.selc() is member and not s.stop
        assert s.r1[creation.PARTY_SIZE] == 1 and game.vm.text_start == len(game.vm.out)


def study_rest_rules():
    from copy import deepcopy
    from unittest.mock import patch
    from . import effects
    from .records import Item
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        s, f = game.s, camp.F
        char = s.party[1]
        s.party[:] = [char]
        extra = deepcopy(char)
        s.monsters[:] = [extra]
        s.sel, s.mode, s.r1[camp.REST_PERIOD_CELL] = 0, camp.CAMPING, 0
        seen = []
        game.player = lambda kind, options, state, **info: seen.append((kind, info)) or 0
        for held in s.chars():
            held.items.clear()
            held.effects.clear()
            held.b[f['memorized']:f['memorized'] + 74] = bytes(74)
            held.b[f['known_spells']:f['known_spells'] + 114] = bytes(114)
            held.b[f['preparation']] = 0
        for minutes, active, completed in ((60, 1, ()), (75, 1, (15,)), (90, 1, (15, 3)), (90, 0, (15,))):
            seen.clear()
            extra.b[f['active']] = active
            extra.b[f['memorized']] = 131
            extra.b[f['known_spells'] + 14] = 0
            extra.b[f['preparation']] = 1
            scroll = Item()
            scroll.set('type', 39)
            scroll.set('powers', bytes((143, 0, 0)))
            extra.items[:] = [scroll.data]
            rest = [0] * 7
            camp.set_rest(rest, minutes)
            assert not camp.camp_rest(game, rest, False)
            assert tuple(info['spell'] for kind, info in seen if 'spell' in info) == completed
            assert extra.b[f['known_spells'] + 14] == int(minutes >= 75)
            assert extra.b[f['memorized']] == (3 if active and minutes >= 90 else 131)
            assert s.g['camp.prep_timers'][1] == (3 if minutes in (60, 75) else 0)
        extra.b[f['active']] = 1
        extra.b[f['memorized']] = 131
        extra.items.clear()
        rest = [0, 0, 0, 0, 2, 0, 0]
        def capture(game, value, interactive):
            assert value == [0, 5, 1, 4, 2, 0, 0] and interactive
            return False
        with patch.object(camp, 'camp_rest', side_effect=capture):
            assert not camp.rest_for_prep(game, rest)
        assert rest == [0] * 7 and extra.b[f['preparation']] == 4
        char.b[f['preparation']] = 0
        assert not camp.camp_rest(game, [0, 5, 0, 0, 0, 0, 0], False, fixing=True)
        assert not s.g['camp.rest_active'] and s.g['no_border'] == 0
        game.current_spell = 17
        effects.add_effect(char, 43, 0, 0, False)
        temple.cure(game, char, 8)
        assert not effects.has(char, 43) and game.spell_targets == [char] and game.current_spell == 17
        char.b[f['status']], char.b[f['active']], char.b[f['hp']], char.b[f['race']] = 6, 0, 0, 2
        char.b[f['abilities'] + 8:f['abilities'] + 10] = bytes((16, 16))
        temple.cure(game, char, 7)
        assert char.b[f['status']] == 0 and char.b[f['hp']] == 1 and game.current_spell == 75
        char.b[f['former_levels']:f['former_levels'] + 8] = char.b[f['levels']:f['levels'] + 8]
        temple.cure(game, char, 10)
        assert game.current_spell == 17 and game.spell_targets == [char]


def grimoire_keys():
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        game.s.sel = 1
        char = game.s.selc()
        known, memory = camp.F['known_spells'], camp.F['memorized']
        char.b[known:known + 114] = bytes(114)
        char.b[memory:memory + 74] = bytes(74)
        for ident in (1, 3, 23, 101, 102): char.b[known + ident - 1] = 1
        char.b[camp.F['deity']] = 4
        game.play = lambda limit: camp.run(game)
        session = Session(profile='dkk', game=game)
        try:
            ui = screen.Controller(session, presentation=False)
            ui.key('m', 'm')
            ui.key('m', 'm')
            info = session.decision['info']
            assert info['prompt'] == game.assets.text('chooseSpellQuery')
            assert info['selection'] == 2 and info['window'] == '1 5 38 15'
            assert game.assets.text('specialSpellsLabel') in info['slots']
            for _ in range(3): ui.key('Up', '')
            names = camp.tables(game.assets).names
            assert session.decision['options'][ui.selected] == '  ' + names[101]
            ui.key('Return', '\r')
            assert session.decision['options'][ui.selected] == '  ' + names[100]
            ui.key('Return', '\r')
            ui.key('Escape', '')
            ui.key('Return', '\r')
            assert session.decision['kind'] == 'CAMP_MENU'
            assert [n for n in camp.memory(char) if n] == [101 | camp.PENDING, 102 | camp.PENDING]
        finally: session.close()


def camp_magic_rules():
    from unittest.mock import patch
    from . import effects
    from .records import Item
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        char, f = game.s.party[1], camp.F
        char.b[f['memorized']:f['memorized'] + 74] = bytes(74)
        char.b[f['known_spells']:f['known_spells'] + 114] = bytes(114)
        char.b[f['known_spells'] + 2] = 1
        char.b[f['spell_slots']] = 2
        char.b[f['memorized']] = 131
        char.b[f['preparation']] = 4
        seen, answers = [], iter(('Keep',))
        def player(kind, options, state, **info):
            seen.append((kind, options, info))
            return options.index(next(answers))
        game.player = player
        game.vm.roster_shown = 0
        game.vm.out.append('before pending list')
        camp.memorize(game, char)
        assert len(seen) == 1 and seen[0][1] == ('Keep', 'Exit')
        assert seen[0][2]['prompt'] == game.assets.text('spellsOkQuery')
        assert seen[0][2]['title'] == 'to Memorize'
        assert char.b[f['memorized']] == 131 and char.b[f['preparation']] == 4
        assert game.vm.roster_shown is None and game.vm.text_start == len(game.vm.out)
        seen.clear()
        answers = iter(('Exit', 'Exit'))
        camp.memorize(game, char)
        assert len(seen) == 2 and not any(camp.memory(char)) and char.b[f['preparation']] == 0
        for confirmation in ('Keep', 'Exit'):
            char.b[f['memorized']:f['memorized'] + 74] = bytes(74)
            seen.clear()
            answers = iter(('  ' + camp.tables(game.assets).names[2], 'Exit', confirmation))
            camp.memorize(game, char)
            assert len(seen) == 3 and seen[-1][1] == ('Keep', 'Exit')
            assert seen[-1][2]['prompt'] == game.assets.text('spellsOkQuery')
            assert (131 in camp.memory(char)) == (confirmation == 'Keep')
        char.b[f['spell_slots']:f['spell_slots'] + 32] = bytes(32)
        char.b[f['deity']] = 6
        game.vm.roster_shown = 0
        answers = iter(('Continue',))
        camp.memorize(game, char)
        assert seen[-1][2]['creature_text'] == game.assets.text('cannotMemorizeMessage')
        assert game.vm.roster_shown == 0
        runtime = game.s.g.setdefault('dkk.runtime', {})
        for archive, ident, interrupted in (('PIC', 93, False), ('PIC', 9, True), ('PIC', 59, False),
                                            ('PIC', 255, False), ('SPRIT', 7, False), ('', 255, False)):
            game.noncombat_target = char
            before = game.s.mode
            runtime.update(picture_name=archive, picture_id=ident)
            def camp_choice(kind, options, state, **info):
                assert (runtime['saved_picture_name'], runtime['saved_picture_id']) == (archive, ident)
                assert (runtime['picture_name'], runtime['picture_id']) == ('PIC', 59)
                return options.index('Fix' if interrupted else 'Exit')
            game.player = camp_choice
            with patch.object(camp, 'fix', return_value=True), patch.object(game.vm, 'archive', wraps=game.vm.archive) as load:
                assert camp.run(game) == interrupted
            calls = [('PIC', 59)]
            if archive.startswith('PIC'): calls.append((archive, ident))
            assert [entry.args for entry in load.call_args_list] == calls
            assert game.noncombat_target is None and game.s.mode == before
            expected = (archive, ident) if archive == 'PIC' and ident != 255 else ('PIC', 59)
            assert (runtime['picture_name'], runtime['picture_id']) == expected
        game.noncombat_target = char
        game.player = lambda kind, options, state, **info: options.index('Fix')
        with patch.object(camp, 'fix', side_effect=RuntimeError('stop')):
            try: camp.run(game)
            except RuntimeError: pass
            else: raise AssertionError('missing failure')
        assert game.noncombat_target is None and game.s.mode == before
        game.player = lambda kind, options, state, **info: seen.append((kind, options, info)) or 0
        char.effects.clear()
        raw = Item().data
        raw[shop.I['cursed']], raw[shop.I['readied']] = 1, 1
        raw[shop.I['powers'] + 1] = 8
        raw[shop.I['powers'] + 2] = 128
        char.items[:] = [raw]
        effects.add_effect(char, 36, 10, 0, False)
        effects.add_effect(char, 43, 10, 0, False)
        effects.add_effect(char, 8, 0, 255, False)
        assert camp.remove_curse(game, char)
        assert not effects.has(char, 43) and effects.has(char, 36) and raw[shop.I['readied']] == 1
        with patch.object(effects, 'recalc_ability', wraps=effects.recalc_ability) as recalc:
            assert camp.remove_curse(game, char) and recalc.call_count == 6
        assert not effects.has(char, 8) and raw[shop.I['readied']] == 0 and raw[shop.I['cursed']] == 1
        assert seen[-1][2]['prompt'].endswith(game.assets.text('itemUncursedText'))


def alter_rules():
    from . import services_alter
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        original = game.s.party[:]
        game.s.sel = 0
        actions = iter(('Select', 'char-up', 'Place', 'char-down', 'Exit'))
        game.player = lambda kind, options, state, **info: options.index(next(actions))
        services_alter.order(game)
        assert game.s.party == original[1:] + original[:1] and game.s.sel == 0
        assert game.s.g['camp.order_mode'] == 0
        selected, seen = game.s.selc(), []
        game.player = lambda kind, options, state, **info: seen.append((kind, info)) or (options.index('No') if 'No' in options else 0)
        services_alter.drop(game)
        assert game.s.selc() is selected and len(game.s.party) == 6
        assert seen[0][1]['start'] == 1 and 'gone forever' in seen[0][1]['offer']
        assert seen[-1][1]['prompt'].endswith('Breathes A sigh of relief')
        selected.b[camp.F['active']] = 0
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append((kind, info)) or 0
        services_alter.drop(game)
        assert all(c is not selected for c in game.s.party) and len(game.s.party) == 5
        assert seen[-1][1]['prompt'].endswith('is dumped in a ditch')
        actions = iter(('char-down', 'char-up', 'Faster', 'Exit'))
        game.s.g['dkk.delay'] = 0
        game.player = lambda kind, options, state, **info: options.index(next(actions))
        services_alter.speed(game)
        assert game.s.g['dkk.delay'] == 0
        level, index = game.s.r0[0x1F4], game.s.sel
        game.player = lambda kind, options, state, **info: options.index('char-down')
        services_alter.level(game)
        assert game.s.r0[0x1F4] == level and game.s.sel == (index + 1) % 5
        seen.clear()
        game.player = lambda kind, options, state, **info: seen.append(info) or info['escape_choice']
        services_alter.level(game)
        assert seen[0]['menu_labels'] == ('Novice', 'Squire', 'Veteran', 'Adept', 'Champion')
        assert game.s.r0[0x1F4] == level
        from unittest.mock import patch
        actions = iter(('Save', 'Yes'))
        game.player = lambda kind, options, state, **info: options.index(next(actions))
        with patch.object(game.vm, 'service') as service: assert not camp.run(game)
        assert service.call_args.args == ('creation', 'save_menu') and game.s.stop and game.exit_game
        game.s.stop, game.exit_game = 0, False
        game.s.party[:] = game.s.party[:1]
        game.s.sel, game.s.r1[creation.PARTY_SIZE] = 0, 1
        actions = iter(('Alter', 'Drop', 'Yes'))
        game.player = lambda kind, options, state, **info: options.index(next(actions))
        assert not camp.run(game) and not game.s.party and game.s.stop and game.exit_game


def movement_and_item_effects():
    from . import effects
    from .records import Character, Item
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('base_move', 12)
    r.set('abilities', bytes((18, 18)) * 6)
    r.set('move', 99)
    assert rules.movement(char, 3) == 30 and r.get('move') == 12
    rules.recalc_stats(char, 3)
    assert r.get('move') == 15
    for ident in (39, 42, 9): effects.add_effect(char, ident, 30, 0, False)
    assert rules.movement(char, 3) == 54 and r.get('move') == 24
    game.s.r1[0x372] = 3
    assert inventory.sheet(game, char)['move'] == r.get('move')
    r.set('side', 1)
    assert inventory.sheet(game, char)['move'] == 24
    r.set('side', 0)
    r.set('base_move', 200)
    assert rules.movement(char, 3) == 38 and r.get('move') == 144
    rules.recalc_stats(char, 3)
    assert r.get('move') == 19
    item = Item()
    item.set('powers', bytes((0, 5, 128)))
    game.handler_override_active = True
    inventory.toggle_item_effect(game, char, item.data, True)
    assert not game.handler_override_active and effects.has(char, 5)
    game.handler_override_active = True
    inventory.toggle_item_effect(game, char, item.data, False)
    assert not game.handler_override_active and not effects.has(char, 5)
