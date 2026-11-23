from pathlib import Path
from tempfile import TemporaryDirectory
from . import creation as c, rules
from .menu import Game
from .records import Character


def create_party(game, classes=(2, 0, 5, 7, 3, 6)):
    assets = game.assets
    for number, cls in enumerate(classes):
        def player(kind, options, current, **info):
            if kind == c.Kind.RACE.value: return 6
            if kind == c.Kind.CLASS.value: return options.index(assets.names('classNames')[cls])
            if kind == c.Kind.ROLL.value: return 1
            if kind == c.Kind.NAME.value: return 'HERO%d' % number
            if kind == c.Kind.ICON.value: return options.index('Yes' if 'Yes' in options else 'Exit')
            if options is None: raise AssertionError('unexpected typed choice ' + kind)
            return 0
        game.player = player
        stem = c.create(game)
        assert game.s.g['save.file_format'] == 1
        assert stem == 'HERO%d' % number
        path = Path(game.roster_directory) / (stem + '.PC')
        char = c.read_character(path)
        r = rules.record(char)
        assert len(path.read_bytes()) == Character.SIZE
        assert r.get('class') == cls and r.get('experience') == 210003
        assert not c.eligible(char) and r.get('hp_max') == r.get('hp') > 0
        assert r.get('money') == (500).to_bytes(2, 'little') + bytes(4)
        assert len(char.items) > 0 and r.get('item_count') == 3
        assert all(c.levels(char.b)[slot] > 1 for slot in c.CLASS_SLOTS[cls])
        assert c.PENDING not in game.s.g
        c.join(game, char)
    assert len(game.s.party) == len(classes) and game.s.r1[c.PARTY_SIZE] == len(classes)
    return game.s.hash(), tuple(game.trace)


def test():
    runs = []
    for _ in range(2):
        with TemporaryDirectory(prefix='sm-dkk-create-') as tmp:
            game = Game(None)
            game.roster_directory = Path(tmp)
            runs.append(create_party(game))
            assert not c.roster(game.s, tmp)
    assert runs[0] == runs[1]
    reserved_names()
    icon_choices()
    party_actions()
    dotted_roster_drop()
    initialize_input()
    ranger_refusal()
    starred_names()
    add_roster_selection()
    party_menu_input_mode()
    linked_party_menu()
    party_capacity()
    linked_add_admission()
    add_sources()
    roster_disk_prompts()
    save_load_callers()
    load_sources()
    last_member_reset()
    class_recalculation()
    interactive_training()
    creation_intermediate()
    starting_spell_order()
    readiness()
    knight_orders()
    level_hit_points()
    modify_rules()
    modify_editor()
    modify_driver()
    join_restore_movement()
    join_append_contract()
    overwrite_prompt()
    signed_scroll_readiness()
    character_sheet()
    vault_deposit()
    vault_coins()
    inventory_completion()
    inventory_slots()
    item_casting()
    sheet_spell_list()
    trade_carry_context()
    trade_selection()
    linked_sheet_recipients()
    paladin_healing()


def inventory_slots():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from . import inventory
    from .records import Item
    game = Game(None)
    carrier, other = [rules.character(bytes(Character())) for _ in range(2)]
    game.s.party = [carrier, other]
    stack = Item()
    stack.set('type', 30)
    stack.set('quantity', 5)
    original = stack.data
    twin = bytearray(original)
    carrier.items = [original, twin]
    free = bytearray(Item.SIZE)
    pool = game.item_pool = Mock()
    pool.allocate.side_effect = [None, free]
    inventory.halve(game, carrier, original)
    assert carrier.items == [original, twin] and stack.get('quantity') == 5
    inventory.halve(game, carrier, original)
    assert carrier.items[1] is free and free[inventory.I['quantity']] == 2
    inventory.join(game, carrier, original)
    assert carrier.items == [original] and stack.get('quantity') == 10
    released = [call.args[0] for call in pool.release.call_args_list]
    assert len(released) == 2 and released[0] is free and released[1] is twin
    inventory.remove_item(carrier, bytearray(original), game)
    assert carrier.items == [original] and pool.release.call_count == 2
    game.s.mode = inventory.IN_COMBAT
    battle = SimpleNamespace(data={'actors': [dict(outsider=1), dict(outsider=0)]})
    facade = SimpleNamespace(game=game, s=game.s, battle=battle)
    heap_item = inventory.copy_item(facade, carrier, original)
    assert heap_item == original and heap_item is not original
    pool.allocate.side_effect = [free]
    assert inventory.copy_item(facade, other, original) is free
    other.items.append(free)
    c.remove_creature(game, carrier)
    assert not carrier.items and game.s.party == [other] and other.items[0] is free
    assert pool.release.call_count == 3 and pool.release.call_args.args[0] is original


def paladin_healing():
    from . import effects, inventory
    from unittest.mock import patch
    for hp, status, active, level, expected_hp, expected_status, expected_active, healed in (
            (3, 0, 1, 4, 11, 0, 1, True),
            (20, 0, 1, 4, 20, 0, 1, False),
            (0, 6, 0, 4, 0, 6, 0, False),
            (0, 5, 0, 4, 8, 0, 1, True),
            (0, 4, 0, 4, 8, 0, 1, True),
            (3, 1, 1, 4, 11, 1, 1, True),
            (3, 0, 1, 128, 3, 0, 1, True)):
        game = Game(None)
        paladin, target = (rules.character(bytes(Character())) for _ in range(2))
        for char in (paladin, target):
            record = rules.record(char)
            for field, value in dict(race=6, abilities=bytes((14, 14)) * 6, base_move=12,
                                     hp=20, hp_max=20, active=1).items(): record.set(field, value)
        paladin.b[c.F['class']] = c.PALADIN
        paladin.b[c.F['levels'] + c.PALADIN] = level
        r = rules.record(target)
        for field, value in dict(hp=hp, status=status, active=active,
                                 name=b'\x04ROOK' + bytes(11)).items(): r.set(field, value)
        game.s.party = [target, paladin]
        game.s.mode = inventory.CAMPING
        events = iter(('Heal', 0, 'Continue', 'Exit'))
        def player(kind, options, current, **info):
            answer = next(events)
            if kind == inventory.Kind.WHO.value:
                assert info['prompt'] == 'Heal whom? ' and info.get('start', 0) == 0
            if kind == 'ACK':
                assert info['timed'] == 1 and info['message_colour'] == 10
                assert info['prompt'] == 'ROOK' + (' feels better' if healed else ' is unaffected')
                assert not effects.has(paladin, 109)
                assert (r.get('hp'), r.get('status'), r.get('active')) == (expected_hp, expected_status, expected_active)
            if answer == 'Exit': assert 'Heal' not in options
            return options.index(answer) if isinstance(answer, str) else answer
        game.player = player
        with patch.object(effects, 'restore_hp', wraps=effects.restore_hp) as restore:
            assert inventory.view(game, paladin) is False
            restore.assert_called_once_with(target, (2 * level) & 255, True, False)
        assert next(events, None) is None
        node = effects.has_effect(paladin, 109)
        assert node is not None and int.from_bytes(node[1:3], 'little') == 1440
        assert not target.effects
        paladin.effects.clear()
        before = bytes(target.b)
        events = scripted(game, ((inventory.Kind.SHEET.value, 'Heal'), (inventory.Kind.WHO.value, 'Exit'),
                                 (inventory.Kind.SHEET.value, 'Exit')))
        with patch.object(effects, 'restore_hp', wraps=effects.restore_hp) as restore:
            assert inventory.view(game, paladin) is False and not restore.called
        assert bytes(target.b) == before and not paladin.effects and next(events, None) is None
    from sm.engine import Session
    from .ui import screen
    paladin.b[c.F['levels'] + c.PALADIN] = 4
    r.set('hp', 3)
    session = Session(profile='dkk', game=game)
    try:
        controller = screen.Controller(session, presentation=False)
        for key in ('Down', 'Down', 'Down', 'Return', 'Down', 'Return'): controller.key(key)
        assert session.error is None and session.decision['kind'] == inventory.Kind.SHEET.value
        controller.key('h', 'h')
        assert session.decision['kind'] == inventory.Kind.WHO.value and controller.selected == 0
        with patch.object(game, 'ask', wraps=game.ask) as ask:
            controller.key('Return')
            assert session.error is None and session.decision['kind'] == inventory.Kind.SHEET.value
            assert 'Heal' not in session.decision['options'] and r.get('hp') == 11
            assert effects.has(paladin, 109)
            ack = next(call.kwargs for call in ask.call_args_list if call.args[0] == 'ACK')
            assert ack['timed'] == 1 and ack['message_colour'] == 10 and ack['prompt'] == 'ROOK feels better'
    finally: session.close()


def scripted(game, steps):
    pending = iter(steps)
    def player(kind, options, current, **info):
        expected, value = next(pending)
        assert kind == expected, (kind, expected)
        return options.index(value) if isinstance(value, str) else value
    game.player = player
    return pending


def interactive_training():
    game = Game(None)
    t = c.tables(game.assets)
    def member(cls=2, race=6, held=((2, 1),), experience=8001):
        char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
        r = rules.record(char)
        for name, value in dict(name=b'\x04ROOK' + bytes(11), race=race, active=1,
                                abilities=bytes((14, 14)) * 6, hp=7, hp_max=10, hp_rolled=10,
                                base_move=12, experience=experience, robe_order=1).items(): r.set(name, value)
        r.set('class', cls)
        for slot, level in held: char.b[c.F['levels'] + slot] = level
        game.s.party = [char]
        game.s.sel = 0
        game.s.g['dkk.runtime'] = dict(test_training=1, training_done=7)
        game.s.r1[0x2A8] = t.classBits[held[0][0]]
        return char, r
    for reason in ('consciousTrainingMessage', 'classTrainingMessage', 'notEnoughExperienceText'):
        char, r = member()
        if reason == 'consciousTrainingMessage': r.set('status', 1)
        elif reason == 'classTrainingMessage': game.s.r1[0x2A8] = t.classBits[c.MAGE]
        else: r.set('experience', 2000)
        def refuse(kind, options, current, **info):
            assert kind == 'ACK' and info['prompt'] == game.assets.text(reason)
            assert info['timed'] == 1 and info['message_colour'] == 14
            return 0
        game.player = refuse
        before = bytes(char.b)
        assert c.train(game, char) is False
        assert game.s.g['dkk.runtime']['test_training'] == 0
        assert game.s.g['dkk.runtime']['training_done'] == (1 if reason == 'notEnoughExperienceText' else 7)
        assert r.get('experience') == (4000 if reason == 'classTrainingMessage' else int.from_bytes(before[c.F['experience']:c.F['experience'] + 4], 'little'))
        assert c.levels(char.b)[c.FIGHTER] == 1 and r.get('hp_max') == 10
    char, r = member()
    def decline(kind, options, current, **info):
        assert kind == 'CREATE_TRAIN' and info['start'] == 0
        assert info['levels'] == 'a level 2 Fighter'
        assert info['training_lines'] == game.assets.text('aLevelText') + '2 Fighter'
        assert r.get('experience') == 4000
        return 1
    game.player = decline
    seed = game.s.seed
    assert not c.train(game, char) and game.s.seed == seed
    assert r.get('hp_max') == 10 and game.s.g['dkk.runtime']['training_done'] == 7
    char, r = member(experience=0xFFFFFFFF)
    assert c.training_offer(char, t) == (t.classBits[c.FIGHTER], 0, 0)
    char, r = member(race=5, held=((2, 5),))
    assert c.training_offer(char, t) == (t.classBits[c.FIGHTER], 0, 0)
    char, r = member(cls=13, race=2, held=((2, 1), (5, 10)), experience=2000000)
    expected = t.rules.level_xp(c.suborder(char, c.MAGE), 12) - 1
    have, ready, trim = c.training_offer(char, t)
    assert ready == t.classBits[c.FIGHTER] and trim == expected and trim > 4000
    assert have == t.classBits[c.FIGHTER] + t.classBits[c.MAGE]
    outcomes = []
    for mage_level in (0, 255):
        char, r = member(held=((c.FIGHTER, 1), (c.MAGE, mage_level)))
        assert c.training_offer(char, t) == (t.classBits[c.FIGHTER], t.classBits[c.FIGHTER], 4000)
        game.s.seed = 4660
        pending = scripted(game, [('CREATE_TRAIN', 'Yes'), ('ACK', 'Continue')])
        assert c.train(game, char) and next(pending, None) is None
        outcomes.append((r.get('hp_max'), r.get('hp'), r.get('hp_rolled'), game.s.seed))
    assert outcomes[0] == outcomes[1]
    char, r = member(cls=6, held=((6, 17),), experience=t.rules.level_xp(9, 18))
    assert c.training_offer(char, t) == (4, 4, 0)
    r.set('hp_max', 50); r.set('hp', 47); r.set('hp_rolled', 50)
    pending = scripted(game, [('CREATE_TRAIN', 'Yes'), ('ACK', 'Continue')])
    assert c.train(game, char) and next(pending, None) is None
    assert c.levels(char.b)[c.THIEF] == 18 and r.get('experience') == 1760001
    assert r.get('hp_max') - r.get('hp') == 3 and not r.get('level_up_ready')
    for cls, level, learns in ((c.MAGE, 2, True), (c.RANGER, 8, True), (c.RANGER, 7, False)):
        char, r = member(cls=cls, held=((cls, level),), experience=0)
        r.set('experience', t.rules.level_xp(c.suborder(char, cls), level + 1))
        c.starting_spells(char)
        learned = []
        initial_seed = game.s.seed
        def accept(kind, options, current, **info):
            if kind == 'CREATE_TRAIN': return 0
            if kind == 'ACK':
                assert info['timed'] == 1 and info['message_colour'] == 10 and info['prompt'] == game.assets.text('congratulationsText')
                assert c.levels(char.b)[cls] == level and r.get('hp_max') == 10 and game.s.seed == initial_seed
                return 0
            assert kind == 'SPELL' and learns
            assert info['selection'] == 4 and info['title'] == 'to Choose' and 'Exit' not in options
            assert c.levels(char.b)[cls] == level + 1 and r.get('hp_max') == 10 and game.s.seed == initial_seed
            learned.append(info['spells'][0])
            return 0
        game.player = accept
        assert c.train(game, char)
        assert c.levels(char.b)[cls] == level + 1
        assert bool(learned) == learns and r.get('hp_max') - r.get('hp') == 3
        assert r.get('hp_max') > 10 and r.get('level_up_ready') == int(c.can_level_up(char))
        if learns: assert rules.spellbook(char).get('known_spells')[learned[0] - 1] == 1
    char, r = member(cls=10, held=((0, 1), (4, 9)), experience=4000)
    pending = scripted(game, [('CREATE_TRAIN', 'Yes'), ('ACK', 'Continue')])
    assert c.train(game, char) and next(pending, None) is None
    assert c.levels(char.b)[c.CLERIC] == 2 and c.levels(char.b)[c.RANGER] == 9
    char, r = member()
    pending = scripted(game, [(c.Kind.MAIN_MENU.value, game.assets.labels[c.TRAIN]),
                              (c.Kind.WHO.value, 'ROOK'), ('CREATE_TRAIN', 'Yes'), ('ACK', 'Continue'),
                              (c.Kind.MAIN_MENU.value, game.assets.labels[c.BEGIN])])
    c.run(game)
    assert next(pending, None) is None and c.levels(char.b)[c.FIGHTER] == 2
    assert game.s.mode == 4 and game.s.r1[0x2A8] == 0
    char, r = member()
    pending = scripted(game, [(c.Kind.WHO.value, 'Exit')])
    before = bytes(char.b)
    assert not c.train(game) and bytes(char.b) == before and next(pending, None) is None
    assert game.s.g['dkk.runtime'] == dict(test_training=0, training_done=7, mouse_mode=1)
    from sm.engine import Session
    from .ui import screen
    char, r = member()
    session = Session(profile='dkk', game=game)
    try:
        controller = screen.Controller(session, presentation=False)
        for key in ('Down', 'Down', 'Down', 'Return', 'Return'): controller.key(key)
        assert session.error is None and session.decision['kind'] == 'CREATE_TRAIN'
        assert session.decision['info']['training_lines'] == game.assets.text('aLevelText') + '2 Fighter'
        assert r.get('experience') == 4000
        assert len(b''.join(screen.render(controller).rows)) == 64000
        controller.key('n', 'n')
        assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
        assert c.levels(char.b)[c.FIGHTER] == 1 and r.get('experience') == 4000
        controller.key('Return')
        controller.key('Return')
        assert session.decision['kind'] == 'CREATE_TRAIN'
        controller.key('y', 'y')
        assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
        assert c.levels(char.b)[c.FIGHTER] == 2 and not game.menu_note
    finally: session.close()
    for reason in ('status', 'hall', 'experience'):
        char, r = member()
        if reason == 'status': r.set('status', 1)
        elif reason == 'hall': game.s.r1[0x2A8] = t.classBits[c.MAGE]
        else: r.set('experience', 2000)
        session = Session(profile='dkk', game=game)
        try:
            controller = screen.Controller(session, presentation=False)
            for key in ('Down', 'Down', 'Down', 'Return', 'Return'): controller.key(key)
            assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert c.levels(char.b)[c.FIGHTER] == 1 and r.get('hp_max') == 10
        finally: session.close()


def character_sheet():
    from . import effects, inventory
    game = Game(None)
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()), rid=17)
    r, book = rules.record(char), rules.spellbook(char)
    for name, value in dict(name=b'\x04ROOK' + bytes(11), race=6, gender=1, age=321, alignment=0,
                            status=0, active=1, base_move=12, hp=7, hp_max=20, deity=1,
                            robe_order=1, abilities=bytes((14, 14)) * 6, experience=0xFFFFFFFF).items(): r.set(name, value)
    r.set('class', 9)
    r.set('levels', bytes((3, 0, 4, 0, 0, 5, 0, 0)))
    book.data[73] = 138
    game.s.party = [char]
    copy = rules.character(char.b, char.items, char.effects, char.rid)
    assert bytes(copy.b) == bytes(char.b) and copy.rid == 17
    rules.spellbook(copy).data[73] = 12
    assert book.data[73] == 138
    for raw, extra in ((bytes(215), None), (bytes(217), None), (bytes(435), None), (bytes(437), None), (char.b, bytes(c.Spells()))):
        try: rules.character(raw, spells=extra)
        except ValueError: pass
        else: raise AssertionError('ambiguous or partial character accepted')
    sheet = inventory.sheet(game, char)
    assert sheet['hp'] == 7 and sheet['hp_max'] == 20 and 'status' not in sheet
    info = sheet['identity']
    assert info['name'] == 'ROOK' and info['age'] == 321 and info['experience'] == -1
    assert info['hp_now'] == 7 and info['hp'] == 20 and info['levels'] == '3/4/5'
    assert info['description'] == game.assets.names('deityNames')[1] + ' ' + game.assets.names('classNames')[9].replace('Mage', game.assets.names('robeOrderNames')[1] + ' Mage')
    assert info['gender'] == game.assets.names('genderNames')[1] and info['race'] == game.assets.names('raceNames')[6]
    r.set('levels', bytes((255, 128, 0, 0, 0, 255, 0, 0)))
    info = inventory.sheet_identity(game, char)
    assert info['levels'] == '0' and info['description'] == game.assets.names('classNames')[9]
    r.set('class', c.KNIGHT)
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 0, 5)))
    for order, label in enumerate(('Crown', 'Sword', 'Rose'), 1):
        r.set('knight_order', order)
        assert inventory.sheet_identity(game, char)['description'] == game.assets.names('classNames')[c.KNIGHT] + ' of the ' + label
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 0, 255)))
    assert inventory.sheet_identity(game, char)['description'] == game.assets.names('classNames')[c.KNIGHT]
    game.s.r1[0x372] = 3
    r.set('side', 0)
    for ident in (39, 42, 9): effects.add_effect(char, ident, 30, 0, False)
    assert inventory.sheet(game, char)['move'] == r.get('move') == 24


def vault_deposit():
    from . import inventory, shop
    from .records import Item
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('abilities', bytes((14, 14)) * 6)
    r.set('base_move', 12)
    game.s.party = [char]
    game.s.mode = inventory.IN_VAULT
    item = Item()
    for name, value in dict(type=3, name_ids=bytes((1, 0, 0)), quantity=2, next_pointer=0x12345678).items(): item.set(name, value)
    char.items = [item.data]
    prior = bytearray(Item.SIZE)
    game.s.treasure_items = [prior]
    def player(kind, options, current, **info):
        assert kind == shop.Kind.ACK.value and info['prompt'].startswith('Your ')
        assert info['prompt'].endswith('will be left in the vault')
        assert info['timed'] == 1 and info['window'] == '1 21 38 22' and info['colour'] == 14
        assert char.items == [item.data] and game.s.treasure_items == [prior]
        return 0
    game.player = player
    assert 'Deposit' in inventory.item_actions(game, char, False) and 'Drop' not in inventory.item_actions(game, char, False)
    inventory.drop_item(game, char, item.data)
    assert not char.items and len(game.s.treasure_items) == 2 and game.s.treasure_items[0] is prior
    stored = rules._view(Item, game.s.treasure_items[1])
    assert stored.get('quantity') == 2 and stored.get('next_pointer') == 0 and item.get('next_pointer') == 0
    item.set('quantity', 1)
    assert stored.get('quantity') == 2
    item.set('readied', 1)
    char.items = [item.data]
    inventory.drop_item(game, char, item.data)
    assert char.items and len(game.s.treasure_items) == 2
    item.set('readied', 0)
    game.s.mode = inventory.CAMPING
    def refuse(kind, options, current, **info):
        assert kind == shop.Kind.CONFIRM.value and info['start'] == 1
        assert info['window'] == '1 21 38 22' and info['colour'] == 14
        return 1
    game.player = refuse
    inventory.drop_item(game, char, item.data)
    assert char.items and len(game.s.treasure_items) == 2


def inventory_completion():
    from types import SimpleNamespace
    from unittest.mock import patch
    from . import inventory
    from .records import Item
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    for field, value in dict(active=1, abilities=bytes((14, 14)) * 6, base_move=12, class_mask=255).items(): r.set(field, value)
    item = Item()
    for field, value in dict(type=3, readied=1, powers=bytes((0, 1, 0))).items(): item.set(field, value)
    char.items = [item.data]
    game.s.party = [char]
    game.s.mode = inventory.IN_COMBAT
    battle = {'item_ok': True, 'initiative': 0}
    game.battle = SimpleNamespace(data={'active': True}, index=lambda char: 0, record=lambda index: battle)
    for initiative in (0, 7):
        battle['initiative'] = initiative
        pending = scripted(game, ((inventory.Kind.SHEET.value, 'Items'), (inventory.Kind.ITEMS.value, 0), (inventory.Kind.ACTION.value, 'Use')))
        with patch.object(inventory, 'use_item', return_value=True) as used:
            assert inventory.view(game, char) is True
            used.assert_called_once_with(game, char, item.data)
        assert next(pending, None) is None
    game.s.r1[0x372] = 3
    r.set('move', 1)
    pending = scripted(game, ((inventory.Kind.ITEMS.value, 'Exit'),))
    assert inventory.items_menu(game, char) is False and r.get('move') == 15
    assert next(pending, None) is None
    game.s.mode = inventory.CAMPING
    pending = scripted(game, ((inventory.Kind.SHEET.value, 'Items'), (inventory.Kind.ITEMS.value, 0), (inventory.Kind.ACTION.value, 'Use'),
                              (inventory.Kind.ITEMS.value, 'Exit'), (inventory.Kind.SHEET.value, 'Exit')))
    with patch.object(inventory, 'use_item', return_value=True): assert inventory.view(game, char) is False
    assert next(pending, None) is None
    item.set('readied', 0)
    pending = scripted(game, ((inventory.Kind.ITEMS.value, 0), (inventory.Kind.ACTION.value, 'Use'),
                              (inventory.Kind.ITEMS.value, 'Exit')))
    with patch.object(inventory, 'use_item') as used:
        assert inventory.items_menu(game, char) is False
        used.assert_not_called()
    assert next(pending, None) is None
    from sm.engine import Session
    from .ui import screen
    game.play = lambda limit: inventory.view(game, char)
    for key, expected in (('u', game.assets.text('mustBeReadied')), ('h', "Can't halve that"), ('r', "It's Cursed")):
        item.set('cursed', int(key == 'r'))
        item.set('readied', int(key == 'r'))
        session = Session(profile='dkk', game=game)
        try:
            controller = screen.Controller(session, presentation=True)
            controller.key('i', 'i')
            rows = screen.render(controller).rows[:192]
            controller.key(key, key)
            assert session.decision['kind'] == inventory.Kind.ITEMS.value
            assert session.decision['info']['message'] == expected
            assert controller.held()['frame'].rows[:192] == rows
            assert controller.selected == 0 and item.get('readied') == int(key == 'r')
        finally:
            session.close()


def vault_coins():
    from types import SimpleNamespace
    from . import inventory, shop
    from .ui import screen
    def layout(kind, options, info):
        decision = dict(kind=kind, options=options, info=info)
        controller = SimpleNamespace(session=SimpleNamespace(decision=decision), selected=0)
        return screen.vertical(controller)
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('abilities', bytes((14, 14)) * 6)
    r.set('base_move', 12)
    game.s.party = [char]
    game.s.mode = inventory.IN_VAULT
    game.s.g['treasure_active'] = 7
    shop.put_coins(char, [0, 0, 0, 0, 2500, 0, 0])
    game.s.treasure_money[4] = 65530
    steps = iter(('Deposit', 0, 2500, 'Exit'))
    def player(kind, options, current, **info):
        answer = next(steps)
        if kind == inventory.Kind.SHEET.value:
            assert info['encumbrance'] == 2500 and info['move'] == r.get('move') == 3
            if answer == 'Deposit':
                assert 'Deposit' in options and 'Drop' not in options and info['identity']['steel'] == 2500
            else:
                assert 'Deposit' not in options and info['identity']['steel'] == shop.weight(char) == 0
        elif kind == inventory.Kind.COIN.value:
            assert screen.coin_list(dict(kind=kind, options=options, info=info)) and info['start'] == 0
            assert layout(kind, options, info)['window'] == (20, 9, 38, 15)
        elif kind == inventory.Kind.NUMBER.value:
            assert info['prompt'] == game.assets.text('howMuch') + game.assets.names('moneyNames')[4] + ' ' + game.assets.text('giveAmountText')
            assert info['max'] == 2500
        return options.index(answer) if isinstance(answer, str) else answer
    game.player = player
    assert inventory.view(game, char) is False
    assert next(steps, None) is None and not shop.coins(char)[4] and game.s.treasure_money[4] == 68030
    assert shop.weight(char) == 0 and game.s.g['treasure_active'] == 7
    assert inventory.sheet(game, char)['move'] == r.get('move') == 12
    for mode in (inventory.SHOP_TEMPLE, inventory.LOOT, inventory.CAMPING):
        game.s.mode = mode
        shop.put_coins(char, [0, 0, 0, 0, 3, 0, 0])
        r.set('weight', 3)
        game.s.treasure_money[4] = 65535
        steps = iter((0, 3))
        def drop(kind, options, current, **info):
            if kind == inventory.Kind.NUMBER.value:
                assert info['prompt'].endswith(game.assets.text('dropAmountText'))
            return next(steps)
        game.player = drop
        inventory.drop_coins(game, char)
        assert next(steps, None) is None and shop.weight(char) == 0
        assert game.s.treasure_money[4] == (65535 if mode == inventory.CAMPING else 65538)
    game.s.mode = inventory.IN_VAULT
    shop.put_coins(char, [0, 0, 0, 0, 1, 0, 0])
    r.set('weight', 1)
    game.s.treasure_money[4] = 0x7FFFFFFF
    steps = iter((0, 1))
    def lower_window(kind, options, current, **info):
        if kind == inventory.Kind.COIN.value:
            assert info['window'] == '1 17 38 22' and info['start'] == 0
            assert not screen.coin_list(dict(kind=kind, options=options, info=info))
            shown = layout(kind, options, info)
            assert shown['window'] == (1, 17, 38, 22) and shown['query'] == game.assets.text('selectCoinQuery')
        else:
            assert kind == inventory.Kind.NUMBER.value and info['prompt'].endswith(game.assets.text('giveAmountText'))
        return next(steps)
    game.player = lower_window
    inventory.drop_coins(game, char, on_sheet=False)
    assert next(steps, None) is None and game.s.treasure_money[4] == -0x80000000
    receiver = rules.character(bytes(char.b))
    rules.record(receiver).set('weight', shop.carrying_capacity(receiver))
    shop.put_coins(char, [0, 0, 0, 0, 3, 0, 0])
    before = bytes(char.b), bytes(receiver.b)
    def overloaded(kind, options, current, **info):
        assert kind == shop.Kind.ACK.value and info['prompt'] == game.assets.text('tradeOverloadMessage')
        assert info['timed'] == 1 and info['message_colour'] == 10 and info['flush_keys'] is True
        assert info['blank_bottom_pause'] is True
        return 0
    game.player = overloaded
    inventory.trade_money(game, char, receiver, 3, 4)
    assert before == (bytes(char.b), bytes(receiver.b))
    rules.record(receiver).set('weight', 65535)
    r.set('weight', 3)
    inventory.trade_money(game, char, receiver, 3, 4)
    assert shop.coins(char)[4] == 0 and shop.coins(receiver)[4] == 3
    assert shop.weight(char) == 0 and shop.weight(receiver) == 2


def sheet_spell_list():
    from . import camp, inventory, shop
    game = Game(None)
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r = rules.record(char)
    r.set('abilities', bytes((15, 15)) * 6)
    r.set('base_move', 12)
    r.set('class', c.MAGE)
    r.set('levels', bytes((0, 0, 0, 0, 0, 9, 0, 0)))
    book = rules.spellbook(char)
    book.data[:4] = bytes((47, 15, 143, 15))
    game.s.party = [char]
    steps = iter(('Spells', 'Exit', 'Exit'))
    def player(kind, options, current, **info):
        if kind == camp.Kind.SPELL.value:
            assert options == ('Exit',) and info['selection'] == 0 and info['title'] == 'in Memory'
            assert info['spells'] == (15, 47) and info['lines'][0].endswith('(2)')
        return options.index(next(steps))
    game.player = player
    assert inventory.view(game, char) is False and next(steps, None) is None
    assert book.data[:4] == bytes((47, 15, 143, 15))
    book.data[:4] = bytes((143, 0, 0, 0))
    pending = scripted(game, ((inventory.Kind.SHEET.value, 'Spells'), (inventory.Kind.SHEET.value, 'Exit')))
    assert inventory.view(game, char) is False and next(pending, None) is None
    book.data[:4] = bytes(4)
    shop.put_coins(char, [1, 2, 3, 4, 0, 0, 0])
    def no_money(kind, options, current, **info):
        assert options == ('Exit',)
        return 0
    game.player = no_money
    assert inventory.view(game, char) is False


def trade_carry_context():
    from . import inventory
    from .records import Item
    game = Game(None)
    giver, receiver = [rules.character(bytes(Character())) for _ in range(2)]
    for char in (giver, receiver):
        r = rules.record(char)
        r.set('abilities', bytes((14, 14)) * 6)
        r.set('base_move', 12)
    game.s.party = [giver, receiver]
    game.s.r1[0x372] = 3
    item = Item()
    item.set('type', 3)
    item.set('quantity', 1)
    giver.items = [item.data]
    receiver.items = [bytearray(item.data) for _ in range(16)]
    pending = scripted(game, ((inventory.Kind.WHO.value, 1), ('ACK', 0)))
    inventory.trade_item(game, giver, item.data)
    assert next(pending, None) is None and len(receiver.items) == 16 and giver.items
    assert rules.record(receiver).get('move') == 15
    receiver.items = receiver.items[:1]
    pending = scripted(game, ((inventory.Kind.WHO.value, 1),))
    inventory.trade_item(game, giver, item.data)
    assert next(pending, None) is None and not giver.items and len(receiver.items) == 2
    assert receiver.items[0][inventory.I['quantity']] == receiver.items[1][inventory.I['quantity']] == 1


def trade_selection():
    from sm.engine import Session
    from . import inventory, shop
    from .ui import screen
    game = Game(None)
    with TemporaryDirectory() as tmp:
        game.roster_directory = Path(tmp)
        create_party(game, (2, 3))
        receiver, giver = game.s.party
        rules.record(giver).set('name', rules.record(receiver).get('name'))
        session = Session(profile='dkk', game=game)
        try:
            controller = screen.Controller(session, presentation=False)
            for _ in range(game.menu_ids.index(c.VIEW)): controller.key('Down')
            controller.key('Return')
            controller.key('Return')
            assert game.trade_character is giver
            assert session.decision['info']['view_index'] == 1
            controller.key('t', 't')
            assert controller.selected == 1
            controller.key('Up')
            controller.key('Return')
            assert session.decision['kind'] == inventory.Kind.COIN.value and game.trade_character is receiver
            controller.key('Return')
            controller.key('1', '1')
            controller.key('Return')
            assert shop.coins(giver)[4] == 499 and shop.coins(receiver)[4] == 501
            controller.key('Escape')
            assert session.decision['kind'] == inventory.Kind.WHO.value and controller.selected == 0
            controller.key('Down')
            controller.key('Escape')
            assert session.decision['kind'] == inventory.Kind.SHEET.value and game.trade_character is receiver
            assert session.decision['info']['view_index'] == 1 and game.s.party[1] is giver
            assert session.decision['options'][controller.selected] == 'Trade'
            controller.key('t', 't')
            assert controller.selected == 0
            controller.key('Return')
            controller.key('Escape')
            assert session.decision['kind'] == inventory.Kind.SHEET.value and game.trade_character is receiver
            assert shop.coins(giver)[4] == 499 and shop.coins(receiver)[4] == 501
            controller.key('i', 'i')
            last = len(giver.items) - 1
            for _ in range(last): controller.key('Down')
            item = giver.items[last]
            if item[inventory.I['readied']]: controller.key('r', 'r')
            controller.key('t', 't')
            assert session.decision['kind'] == inventory.Kind.WHO.value and controller.selected == 0
            controller.key('Escape')
            assert session.decision['kind'] == inventory.Kind.ITEMS.value and controller.selected == last
            assert giver.items[last] is item
            controller.key('t', 't')
            controller.key('Return')
            assert session.decision['kind'] == inventory.Kind.ITEMS.value and controller.selected == last - 1
            assert item not in giver.items and receiver.items[-1] == item
            controller.key('Escape')
            controller.key('i', 'i')
            assert controller.selected == 0
            controller.key('Escape')
            controller.key('Escape')
            controller.key('Return')
            controller.key('Return')
            assert session.decision['kind'] == inventory.Kind.SHEET.value and controller.selected == 0
            controller.key('Return')
            assert session.decision['kind'] == inventory.Kind.ITEMS.value
        finally: session.close()


def linked_sheet_recipients():
    from sm.engine import Session
    from . import camp, shop
    from .ui import screen
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, (2, 3))
        head, paladin = game.s.party
        game.s.monsters.append(game.s.party.pop())
        game.s.sel = 0
        paladin.b[c.F['hp']] -= 1
        paladin.b[c.F['cure_ability']] = 1
        game.play = lambda limit: camp.run(game)
        session = Session(profile='dkk', game=game)
        try:
            ui = screen.Controller(session, presentation=False)
            def keys(*sequence):
                for key in sequence:
                    ui.key(key, key if len(key) == 1 else '')
                    assert session.error is None, session.error
            keys('Up', 'v', 't')
            assert ui.selected == 1 and session.decision['options'] == ('HERO0', 'HERO1', 'Exit')
            keys('Down', 'Return', 'Return', '1', 'Return', 'Escape', 'Escape')
            assert shop.coins(paladin)[4] == 499 and shop.coins(head)[4] == 501
            keys('c', 'Up', 'Return')
            assert paladin.b[c.F['cure_ability']] == 1
            keys('h', 'Up', 'Return')
            assert paladin.b[c.F['hp']] == paladin.b[c.F['hp_max']]
            assert 'Heal' not in session.decision['options']
        finally:
            session.close()


def icon_choices():
    game = Game(None)
    char = rules.character(bytes(c.Character()))
    r = rules.record(char)
    r.set('icon_size', 2)
    r.set('icon_colors', bytes((0x23,) * 6))
    answers = ('Parts', 'Head', 'Prev', 'Exit', 'Head', 'Prev', 'Keep', 'Exit',
               '1st-color', 'Weapon', 'Prev', 'Exit', 'Weapon', 'Next', 'Keep', 'Exit',
               '2nd-color', 'Face', 'Prev', 'Keep', 'Exit', 'Size', 'Small', 'Exit',
               'Size', 'Small', 'Keep', 'Exit', 'No', 'Exit', 'Yes')
    seen = []
    steps = iter(answers)
    game.s.dataset = 5
    disks = []
    def player(kind, options, current, **info):
        assert kind == c.Kind.ICON.value
        disks.append(game.s.g['dkk.previous_disk'])
        game.s.g['dkk.previous_disk'] = 2
        seen.append((tuple(options), dict(info)))
        return options.index(next(steps))
    game.player = player
    c.customize_icon(game, char.b)
    assert next(steps, None) is None
    assert disks[0] == game.s.dataset == 5
    assert [answer for answer, disk in zip(answers, disks[1:]) if disk == 5] == [
        'Prev', 'Exit', 'Prev', 'Keep', 'Small', 'Exit', 'Small', 'Keep', 'No']
    assert set(disks) == {2, 5}
    assert r.get('icon_head') == 13 and r.get('icon_size') == 1
    assert r.get('icon_colors') == bytes((0x23, 0x23, 0x23, 0x13, 0x23, 0x24))
    color_menus = [options for options, info in seen if info['icon_state'] == 3]
    assert any('Hair' in options and 'Face' not in options for options in color_menus)
    assert any('Face' in options and 'Hair' not in options for options in color_menus)
    size_menus = [options for options, info in seen if info['icon_state'] == 4]
    assert size_menus[0] == ('Small', 'Keep', 'Exit')
    assert size_menus[1] == ('Large', 'Keep', 'Exit')
    assert seen[0][1]['icon_old'][:3] == (0, 0, 2)
    assert seen[-2][1]['icon_old'][:3] == (13, 0, 1)


def party_actions():
    with TemporaryDirectory(prefix='sm-dkk-party-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, (2, 0, 6))
        first, middle, last = game.s.party
        c.remove_creature(game, middle)
        assert game.s.party == [first, last] and game.s.sel == 0 and game.s.r1[c.PARTY_SIZE] == 2
        assert not c.remove_creature(game, middle)
        c.remove_creature(game, last, keep_count=True)
        assert game.s.r1[c.PARTY_SIZE] == 2 and game.s.sel == 0
        game.s.r1[c.PARTY_SIZE] = 1
        def drop_with(answers, message):
            choices = iter(answers)
            notices = []
            def player(kind, options, state, **info):
                if kind == c.Kind.WHO.value: return 0
                if kind == c.Kind.DROP.value:
                    assert info['start'] == 1
                    return options.index(next(choices))
                assert kind == 'ACK' and info['timed'] == 1 and info['message_colour'] == 10
                assert game.s.party == [first] and (Path(tmp) / 'HERO0.PC').is_file()
                notices.append(info['prompt'])
                return 0
            game.player = player
            c.drop(game)
            assert next(choices, None) is None and notices == ['HERO0' + game.assets.text(message)]
            assert not getattr(game, 'menu_note', '')
        for answers in (('No',), ('Yes', 'No')):
            drop_with(answers, 'sighOfReliefText')
            assert game.s.party == [first] and (Path(tmp) / 'HERO0.PC').exists()
        first.b[c.F['active']] = 0
        drop_with(('Yes', 'Yes'), 'dumpedOutBackText')
        assert not game.s.party
        assert not any((Path(tmp) / ('HERO0.' + suffix)).exists() for suffix in ('PC', 'WIZ', 'JNK', 'EFF'))
        assert (Path(tmp) / 'HERO1.PC').exists()
        c.join(game, middle)
        pending = scripted(game, ((c.Kind.QUIT.value, 'Yes'), (c.Kind.QUIT.value, 'No'), (c.Kind.SLOT.value, 'A')))
        assert c.confirm_quit(game)
        assert next(pending, None) is None and game.s.stop == 1 and game.exit_game
        assert (Path(tmp) / 'SAVGAMA.PTY').exists()
        game.s.stop = 0
        pending = scripted(game, ((c.Kind.QUIT.value, 'Yes'),))
        assert c.confirm_quit(game) and next(pending, None) is None
        game.s.stop = 0
        pending = scripted(game, ((c.Kind.WHO.value, 0),))
        c.remove(game)
        assert next(pending, None) is None and not game.s.party
        assert (Path(tmp) / 'HERO1.PC').exists()
        c.join(game, last)
        last.b[c.F['npc']] = 128
        pending = scripted(game, ((c.Kind.WHO.value, 0), (c.Kind.WHO.value, 'Exit')))
        c.remove(game)
        assert next(pending, None) is None and game.s.party == [last]
        game.s.g['save.recent'] = 1
        pending = scripted(game, ((c.Kind.MAIN_MENU.value, game.assets.labels[c.VIEW]),
                                  (c.Kind.WHO.value, 'Exit'),
                                  (c.Kind.MAIN_MENU.value, game.assets.labels[c.QUIT]),
                                  (c.Kind.QUIT.value, 'Yes'), (c.Kind.QUIT.value, 'Yes')))
        c.run(game)
        assert next(pending, None) is None and game.s.g['save.recent'] == 0


def dotted_roster_drop():
    from types import SimpleNamespace
    with TemporaryDirectory() as temp:
        game = Game(None)
        folder = game.roster_directory = Path(temp)
        create_party(game, (2,))
        char = game.s.party[0]
        rules.record(char).set('name', b'\x04A..B' + bytes(11))
        assert c.store(game, char) == 'AB'
        suffixes = ('PC', 'WIZ', 'JNK', 'EFF')
        for suffix in suffixes:
            (folder / ('A.B.' + suffix)).write_bytes(b'drop')
            if not (folder / ('AB.' + suffix)).exists(): (folder / ('AB.' + suffix)).write_bytes(b'keep')
        kept = [(folder / ('AB.' + suffix)).read_bytes() for suffix in suffixes]
        pending = scripted(game, ((c.Kind.WHO.value, 0), (c.Kind.DROP.value, 'Yes'), (c.Kind.DROP.value, 'Yes'), ('ACK', 0)))
        c.drop(game)
        assert next(pending, None) is None and not game.s.party
        assert all(not (folder / ('A.B.' + suffix)).exists() for suffix in suffixes)
        assert [(folder / ('AB.' + suffix)).read_bytes() for suffix in suffixes] == kept
        disk = folder / 'native'
        disk.mkdir()
        for location in (disk, folder):
            for suffix in suffixes: (location / ('A.B.' + suffix)).write_bytes(b'roster')
        game.save_filesystem = SimpleNamespace(save_path='A:/SAVE/', host_path={'A:/SAVE': disk}.__getitem__)
        def confirm_drop():
            c.join(game, char)
            pending = scripted(game, ((c.Kind.WHO.value, 0), (c.Kind.DROP.value, 'Yes'),
                                      (c.Kind.DROP.value, 'Yes'), ('ACK', 0)))
            c.drop(game)
            assert next(pending, None) is None and not game.s.party and not game.s.r1[c.PARTY_SIZE]
        confirm_drop()
        assert not list(disk.iterdir())
        assert all((folder / ('A.B.' + suffix)).read_bytes() == b'roster' for suffix in suffixes)
        disk.rmdir()
        confirm_drop()
        assert not disk.exists()
        del game.save_filesystem
        game.roster_directory = folder / 'unavailable'
        game.roster_directory.touch()
        confirm_drop()
        assert game.roster_directory.is_file()


def initialize_input():
    from types import SimpleNamespace
    from unittest.mock import patch
    with TemporaryDirectory() as temp:
        root = Path(temp)
        assets = SimpleNamespace(root=root)
        for mode in ('M', 'J', 'N'):
            (root / 'dkk.cfg').write_bytes(b'E\r\nA\r\n' + mode.encode() + b'\r\n')
            assert c.boot_input_mode(SimpleNamespace(assets=assets)) == mode
        game = Game(None)
        with patch('sm.titles.dkk.intake.config_path', return_value=root / 'settings.json'):
            initialize_keys(game, root / 'dkk-input.cfg')


def initialize_keys(game, target):
    from unittest.mock import patch
    from sm.engine import Session
    from . import shop
    from .ui import screen
    session = Session(profile='dkk', game=game)
    try:
        controller = screen.Controller(session, presentation=False)
        for _ in range(game.menu_ids.index(c.INIT)): controller.key('Down')
        controller.key('Return')
        text = game.assets.text
        def check(mode, row):
            assert session.error is None and session.decision['kind'] == c.Kind.INIT.value
            assert session.decision['options'] == (text('mouseOn' if mode == 'M' else 'mouseOff'),
                                                   text('joystickOn' if mode == 'J' else 'joystickOff'), text('disableBoth'), 'Exit')
            assert session.decision['info']['window'] == '9 12 38 22' and controller.selected == row
        check(c.boot_input_mode(game), 0)
        assert not target.exists()
        controller.key('Escape')
        assert not target.exists()
        controller.key('Return')
        controller.key('Down')
        controller.key('Down')
        controller.key('Return')
        check('N', 2)
        assert target.read_bytes() == b''
        header = [b'E', b'A', b'N', b'first directory', b'second directory']
        target.write_bytes(b'\r\n'.join(header) + b'\r\n')
        controller.key('Escape')
        assert target.read_bytes() == b'\r\n'.join(header) + b'\r\n'
        controller.key('Return')
        controller.key('Return')
        check('M', 0)
        def stored(mode, words):
            assert target.read_bytes() == b'\r\n'.join(header[:2] + [mode] + header[3:] + words) + b'\r\n'
        stored(b'M', [b'0'] * 14)
        controller.key('Return')
        check('N', 0)
        stored(b'N', [b'0'] * 14)
        controller.key('Down')
        pause = shop.pause
        def calibration_prompt(*args, **kwargs):
            assert target.read_bytes() == b''
            return pause(*args, **kwargs)
        with patch.object(shop, 'pause', side_effect=calibration_prompt) as calibration:
            controller.key('Return')
        calibration.assert_called_once()
        check('J', 1)
        stored(b'J', [b'0'] * 6 + [b'1'] * 2 + [b'0'] * 6)
        assert session.decision['info']['caption'] == text('joystickReadError')
        controller.key('Escape')
        assert session.decision['kind'] == c.Kind.MAIN_MENU.value and game.menu_ids[controller.selected] == c.INIT
        controller.key('Return')
        check('J', 0)
        assert not session.decision['info']['caption']
        controller.key('Down')
        controller.key('Return')
        check('N', 1)
    finally: session.close()


def ranger_refusal():
    with TemporaryDirectory(prefix='sm-dkk-rangers-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, (4, 4, 4, 4))
        fourth = game.s.party[-1]
        c.remove_creature(game, fourth)
        game.s.monsters.append(game.s.party.pop())
        seen = []
        warnings = []
        def player(kind, options, current, **info):
            if kind == 'ACK':
                assert info['timed'] == 1 and info['message_colour'] == 10 and info['prompt'] == game.assets.text('tooManyRangers')
                assert len(game.s.chars()) == 3
                warnings.append(info['prompt'])
                return 0
            assert kind == c.Kind.ADD.value
            if info.get('source'): return options.index('Death')
            seen.append((options, info.get('message', '')))
            return options.index('Exit') if len(seen) == 3 else 0
        game.player = player
        c.add(game)
        assert len(game.s.chars()) == 3 and game.s.r1[c.PARTY_SIZE] == 3
        assert seen[1:] == [(('* HERO3', 'Exit'), '')] * 2
        assert warnings == [game.assets.text('tooManyRangers')]
        game.s.monsters[0].b[c.F['levels'] + c.RANGER] = 255
        pending = scripted(game, ((c.Kind.ADD.value, 'Death'), (c.Kind.ADD.value, 'HERO3'),
                                  (c.Kind.ADD.value, 'Exit')))
        c.add(game)
        assert next(pending, None) is None and len(game.s.chars()) == game.s.r1[c.PARTY_SIZE] == 4


def reserved_names():
    import ntpath, random
    reference = getattr(ntpath, 'isreserved', None)
    if reference: del ntpath.isreserved
    try:
        typed, draw = [chr(code) for code in range(32, 97)], random.Random(4660)
        names = typed + [a + b for a in typed for b in typed]
        names += [''.join(draw.choices(typed, k=draw.randint(3, 8))) for _ in range(20000)]
        names += [device + tail for device in sorted(c.RESERVED_NAMES)
                  for tail in ('', '.PC', ' .PC', '  .PC', '.', ' ', ':', '1', '$', '\\X', 'X\\', '/X')]
        names += [name + '.PC' for name in names]
        answers = [c.reserved_name(name) for name in names]
        if reference: assert answers == [reference(name) for name in names]
        assert all(map(c.reserved_name, ('CON.PC', 'CON .PC', 'COM1.PC', 'LPT9', 'NUL', 'A.', 'A ', 'AB:C', '*ROOK.PC',
                                         'A"B', 'X\\AUX', 'CONIN$')))
        assert not any(map(c.reserved_name, ('ROOK.PC', 'COM0.PC', 'CONX.PC', '.', '..', 'A:B', 'X\\Y', '')))
        with TemporaryDirectory(prefix='sm-dkk-reserved-') as tmp:
            game = Game(None)
            root = game.roster_directory = Path(tmp)
            (root / 'SUB').mkdir()
            assert c.roster_destination(root, 'NUL\\X') is None and c.roster_destination(root, 'SUB\\X')[1] == 'X'
            create_party(game, (2,))
            char = game.s.party[0]
            rules.record(char).set('name', b'\x03CON' + bytes(12))
            assert c.store(game, char) is None and not any(root.glob('CON.*'))
    finally:
        if reference: ntpath.isreserved = reference


def starred_names():
    with TemporaryDirectory(prefix='sm-dkk-starred-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, (2,))
        candidate = rules.character(game.s.party[0].b)
        rules.record(candidate).set('name', b'\x05*ROOK' + bytes(10))
        stem = c.store(game, candidate)
        path = game.roster_directory / (stem + '.PC')
        saved = path.read_bytes()
        seen = []
        def player(kind, options, current, **info):
            assert kind == c.Kind.ADD.value
            if info.get('source'): return options.index('Death')
            seen.append(options)
            return options.index('Exit') if len(seen) == 3 else options.index('*ROOK')
        game.player = player
        game.s.g['save.file_format'] = 1
        before = game.s.hash()
        c.add(game)
        assert seen == [('*ROOK', 'Exit')] * 3
        assert game.s.hash() == before and path.read_bytes() == saved
        rules.record(candidate).set('name', b'\x06R*ALLY' + bytes(9))
        c.store(game, candidate)
        pending = scripted(game, ((c.Kind.ADD.value, 'Death'), (c.Kind.ADD.value, 'R*ALLY'),
                                  (c.Kind.ADD.value, 'Exit')))
        c.add(game)
        assert next(pending, None) is None and len(game.s.party) == 2
        assert c.member_name(game.s.party[-1]) == 'R*ALLY'


def add_roster_selection():
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory() as temp:
        game = Game(None)
        game.roster_directory = Path(temp)
        create_party(game, (2, 2, 2))
        for char in tuple(game.s.party): c.remove_creature(game, char)
        session = Session(profile='dkk', game=game)
        try:
            controller = screen.Controller(session, presentation=False)
            def open_list():
                for _ in range((game.menu_ids.index(c.ADD) - controller.selected) % len(game.menu_ids)):
                    controller.key('Down')
                controller.key('Return')
                controller.key('Return')
                assert session.decision['kind'] == c.Kind.ADD.value and controller.selected == 0
            open_list()
            controller.key('Down')
            game.s.dataset = 5
            game.s.g['dkk.previous_disk'] = 2
            game.vm.icons[0] = ('CPIC', 48, 1)
            controller.key('Return')
            assert session.decision['options'][1] == '* HERO1' and controller.selected == 1
            assert game.s.g['dkk.previous_disk'] == game.s.dataset == 5 and 0 not in game.vm.icons
            game.s.g['dkk.previous_disk'] = 2
            controller.key('Return')
            assert game.s.g['dkk.previous_disk'] == 2
            assert [c.member_name(char) for char in game.s.party] == ['HERO1']
            controller.key('Down')
            controller.key('Return')
            assert game.s.g['dkk.previous_disk'] == 5 and len(game.s.party) == 2
            controller.key('Escape')
            open_list()
            assert session.decision['options'] == ('HERO0', 'Exit')
        finally:
            session.close()


def party_menu_input_mode():
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory() as temp:
        game = Game(None)
        game.roster_directory = Path(temp)
        create_party(game, (2, 3))
        game.s.r1[0x2A8] = 255
        runtime = game.s.g.setdefault('dkk.runtime', {})
        runtime.update(mouse_mode=1, test_training=1)
        session = Session(profile='dkk', game=game)
        try:
            controller = screen.Controller(session, presentation=False)
            def menu(action):
                for _ in range((game.menu_ids.index(action) - controller.selected) % len(game.menu_ids)):
                    controller.key('Down')
                controller.key('Return')
            assert (runtime['mouse_mode'], runtime['test_training']) == (0, 0)
            menu(c.VIEW)
            assert runtime['mouse_mode'] == 1
            controller.key('Up')
            controller.key('Escape')
            assert runtime['mouse_mode'] == 0 and game.s.sel == 0
            menu(c.VIEW)
            controller.key('Return')
            assert runtime['mouse_mode'] == 0 and session.decision['kind'] == 'CREATE_VIEW'
            game.s.g['world.extended'] = 1
            for answer in ('Escape', 'Return'):
                controller.key('t', 't')
                assert session.decision['kind'] == 'VIEW_WHO'
                assert runtime['selection_mode'] == runtime['mouse_mode'] == 1
                assert not game.s.g.get('world.extended', 0)
                controller.key('Down')
                controller.key(answer)
                assert runtime['selection_mode'] == runtime['mouse_mode'] == 0
                assert game.s.g['world.extended'] == 1
                if answer == 'Return':
                    assert session.decision['kind'] == 'VIEW_COIN'
                    controller.key('Escape')
                assert session.decision['kind'] == 'CREATE_VIEW'
            controller.key('Escape')
            menu(c.BEGIN)
            assert runtime['mouse_mode'] == 1 and game.s.r1[0x2A8] == 0
        finally:
            session.close()
        for mode, resuming, picture, redraw in (
                (3, False, 255, True), (3, True, 255, False), (3, True, 9, True),
                (0, True, 255, True), (4, True, 255, True)):
            game.s.mode, game.vm.resuming, runtime['picture_id'] = mode, resuming, picture
            previous = game.vm.ready_shown = (0, 1)
            scripted(game, [(c.Kind.MAIN_MENU.value, game.assets.labels[c.BEGIN])])
            c.run(game)
            assert game.s.mode == mode
            assert game.vm.ready_shown is (None if redraw else previous)


def linked_party_menu():
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory() as temp:
        game = Game(None)
        game.roster_directory = Path(temp)
        create_party(game, (2, 0, 3))
        head, middle, last = game.s.party
        game.s.monsters.extend(game.s.party[1:])
        del game.s.party[1:]
        game.s.sel = 0
        session = Session(profile='dkk', game=game)
        try:
            ui = screen.Controller(session, presentation=False)
            def key(name):
                ui.key(name, name if len(name) == 1 else '')
                assert session.error is None, session.error
            def menu(action):
                for _ in range((game.menu_ids.index(action) - ui.selected) % len(game.menu_ids)):
                    key('Down')
                key('Return')
            menu(c.VIEW)
            key('Up')
            key('Escape')
            assert game.s.selc() is last
            menu(c.VIEW)
            key('Return')
            assert screen.sheet_view(ui)[1] is last
            key('Escape')
            menu(c.DROP)
            key('Return')
            key('y')
            key('y')
            assert game.s.chars() == [head, middle] and game.s.selc() is middle
            assert game.s.r1[c.PARTY_SIZE] == 2 and not (Path(temp) / 'HERO2.PC').exists()
            menu(c.REMOVE)
            key('Return')
            if session.decision['kind'] == c.Kind.OVERWRITE.value: key('y')
            assert game.s.chars() == [head] and game.s.selc() is head
            assert game.s.r1[c.PARTY_SIZE] == 1 and (Path(temp) / 'HERO1.PC').is_file()
        finally:
            session.close()


def party_capacity():
    with TemporaryDirectory(prefix='sm-dkk-capacity-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, (2,) * 6)
        candidate = game.s.party[-1]
        c.remove_creature(game, candidate)
        for index in range(3):
            npc = rules.character(game.s.party[0].b)
            r = rules.record(npc)
            name = ('ALLY%d' % index).encode('ascii')
            r.set('name', bytes((len(name),)) + name + bytes(15 - len(name)))
            r.set('npc', 128)
            c.join(game, npc)
        game.s.monsters.append(game.s.party.pop())
        before = tuple(bytes(char.b) for char in game.s.chars())
        game.menu_note = ''
        pending = scripted(game, ((c.Kind.ADD.value, 'Death'), (c.Kind.ADD.value, 'HERO5')))
        c.add(game)
        assert next(pending, None) is None and len(game.s.chars()) == game.s.r1[c.PARTY_SIZE] == 8
        assert tuple(bytes(char.b) for char in game.s.chars()) == before and game.menu_note == ''
        assert len({char.b[c.F['order']] for char in game.s.chars()}) == 8
        assert (Path(tmp) / 'HERO5.PC').exists()
        c.remove_creature(game, game.s.monsters[-1])
        pending = scripted(game, ((c.Kind.ADD.value, 'Death'), (c.Kind.ADD.value, 'HERO5')))
        c.add(game)
        assert next(pending, None) is None and len(game.s.party) == game.s.r1[c.PARTY_SIZE] == 8
        assert c.member_name(game.s.party[-1]) == 'HERO5'


def linked_add_admission():
    with TemporaryDirectory() as temp:
        game = Game(None)
        folder = game.roster_directory = Path(temp)
        create_party(game, (2,) * 7)
        candidate = game.s.party[-1]
        c.remove_creature(game, candidate)
        game.s.monsters.extend(game.s.party)
        game.s.party.clear()
        held = tuple(game.s.chars())
        candidate_file = folder / 'HERO6.PC'
        assert c.roster(game.s, folder) == (candidate_file,)
        pending = scripted(game, ((c.Kind.ADD.value, 'Death'), (c.Kind.ADD.value, 'HERO6')))
        c.add(game)
        assert next(pending, None) is None and tuple(game.s.chars()) == held
        assert game.s.r1[c.PARTY_SIZE] == 6
        c.remove_creature(game, held[0])
        def swapped(kind, options, current, **info):
            if info.get('source'): return options.index('Death')
            if '* HERO6' in options: return options.index('Exit')
            candidate_file.write_bytes(bytes(held[-1].b[:Character.SIZE]))
            return options.index('HERO6')
        game.player = swapped
        c.add(game)
        assert tuple(game.s.chars()) == held[1:] and game.s.r1[c.PARTY_SIZE] == 5
        game.s.g['save.recent'] = 0
        pending = scripted(game, ((c.Kind.QUIT.value, 'Yes'), (c.Kind.QUIT.value, 'Yes')))
        assert c.confirm_quit(game) and next(pending, None) is None


def add_sources():
    from sm.titles.cok.records import Character as ImportedCharacter
    from .records import Item
    with TemporaryDirectory(prefix='sm-dkk-add-') as tmp:
        root, game = Path(tmp), Game(None)
        game.roster_directory = root / 'native'
        game.champions_directory = root / 'import'
        game.champions_directory.mkdir()
        pending = scripted(game, ((c.Kind.ADD.value, 'Exit'),))
        c.add(game)
        assert next(pending, None) is None and not game.s.party
        assert 'save.file_format' not in game.s.g and not game.roster_directory.exists()
        old = ImportedCharacter()
        old.set('name', b'\x05GUEST' + bytes(10))
        old.set('abilities', bytes((18, 18)) * 6)
        old.set('levels', bytes((0, 0, 3, 0, 0, 0, 0, 0)))
        old.set('class', 2)
        old.set('race', 6)
        old.set('age', 80)
        old.set('money', bytes(8) + (321).to_bytes(2, 'little') + bytes(4))
        path = game.champions_directory / 'GUEST.WHO'
        path.write_bytes(bytes(old))
        gear = Item()
        gear.set('type', 3)
        gear.set('next_pointer', 1234)
        skipped = Item()
        skipped.set('type', 47)
        path.with_suffix('.STF').write_bytes(bytes(skipped) + bytes(gear))
        isolated = c.read_character(path)
        pending = scripted(game, ((c.Kind.ADD.value, 'Champions'), (c.Kind.ADD.value, 'GUEST'), (c.Kind.ADD.value, 'Exit')))
        c.add(game)
        assert next(pending, None) is None and game.s.g['save.file_format'] == 0
        record = rules.record(game.s.party[0])
        held = game.s.party[0].items
        assert len(held) == 1 and isolated.items == held and isolated.items[0] is not held[0]
        assert rules._view(Item, held[0]).get('next_pointer') == 0
        pool = getattr(game, 'item_pool', None)
        if pool is not None: assert any(held[0] is slot for slot in pool.slots)
        assert record.get('age') == 50 and record.get('money') == (321).to_bytes(2, 'little') + bytes(4)
        assert path.read_bytes() == bytes(old) and not c.roster(game.s, game.champions_directory, imported=True)
        imported_item = held[0]
        c.remove_creature(game, game.s.party[0])
        if pool is not None: assert pool.allocate() is imported_item
        create_party(game, (2,) * 6)
        candidate = rules.character(game.s.party[0].b)
        rules.record(candidate).set('name', b'\x04ALLY' + bytes(11))
        c.store(game, candidate)
        def player(kind, options, current, **info):
            assert kind == c.Kind.ADD.value
            if info.get('source'):
                assert options == ('Death', 'Champions', 'Exit') and info['start'] == 0
                assert info['prompt'] == game.assets.text('addFromWhereQuery')
                return 0
            rules.record(candidate).set('npc', 128)
            (game.roster_directory / 'ALLY.PC').write_bytes(bytes(candidate.b[:Character.SIZE]))
            return options.index('ALLY')
        game.player = player
        c.add(game)
        assert len(game.s.party) == game.s.r1[c.PARTY_SIZE] == 7 and game.s.g['save.file_format'] == 1
        assert rules.record(game.s.party[-1]).get('npc') == 128
        game.s.party.pop()
        game.s.r1[c.PARTY_SIZE] = 6
        assert not c.roster(game.s, game.roster_directory)
        rules.record(candidate).set('npc', 0)
        rules.record(candidate).set('name', b'\x05HERO0' + bytes(10))
        rules.record(candidate).set('creature_id', game.s.party[0].b[c.F['creature_id']] ^ 255)
        (game.roster_directory / 'ALLY.PC').write_bytes(bytes(candidate.b[:Character.SIZE]))
        assert not c.roster(game.s, game.roster_directory)


def roster_disk_prompts():
    from unittest.mock import patch
    from . import save
    for action in (c.create, c.remove):
        for failure in ('directory', 'open', 'ok', 'retry', 'escape'):
            with TemporaryDirectory() as temp:
                game = Game(None)
                folder = game.roster_directory = Path(temp)
                output = folder / 'ROOK.PC'
                if failure == 'directory':
                    game.roster_directory = folder / 'blocked'
                    game.roster_directory.touch()
                elif failure == 'open':
                    output.mkdir()
                else:
                    output.write_bytes(b'occupied')
                if action == c.remove:
                    member = rules.character(bytes(Character()))
                    rules.record(member).set('name', b'\x04ROOK' + bytes(11))
                    game.s.party = [member]
                    game.s.r1[c.PARTY_SIZE] = 1
                prompts = []
                game.s.g['save.file_format'] = 0
                def player(kind, options, current, **info):
                    if kind == c.Kind.RACE.value: return 6
                    if kind == c.Kind.CLASS.value: return options.index(game.assets.names('classNames')[c.FIGHTER])
                    if kind == c.Kind.ROLL.value: return 1
                    if kind == c.Kind.NAME.value: return 'ROOK'
                    if kind == c.Kind.ICON.value: return options.index('Yes' if 'Yes' in options else 'Exit')
                    if kind in ('ACK', 'MENU', c.Kind.OVERWRITE.value):
                        assert game.s.g['save.file_format'] == 1
                        prompts.append(info['prompt'])
                        if kind == 'ACK': assert info['message_colour'] == 14
                        if kind == 'MENU': return {'ok': 0, 'retry': 1, 'escape': 2}[failure]
                    return 0
                game.player = player
                refusing = failure in ('directory', 'open')
                with patch.object(save, 'free_space', side_effect=(65535,) if refusing else (0, 65535)) as space:
                    action(game)
                if refusing:
                    assert prompts == [game.assets.text('noSaveDirectoryMessage')] and not output.is_file()
                else:
                    assert prompts == [game.assets.text('diskFullMessage'), game.assets.text('loseCharacterPrompt'),
                                       game.assets.text('overwritePrefix') + 'ROOK' + game.assets.text('overwriteSuffix')]
                    assert space.call_count == (1 if failure == 'ok' else 2)
                    assert c.member_name(c.read_character(output)) == 'ROOK'
                assert not game.s.party and game.s.r1[c.PARTY_SIZE] == 0 and c.PENDING not in game.s.g
    with TemporaryDirectory() as temp:
        game = Game(None)
        blocked = Path(temp) / 'blocked'
        blocked.touch()
        game.roster_directory = game.champions_directory = blocked
        for action, kind in ((c.add, c.Kind.ADD), (c.load_menu, c.Kind.SLOT)):
            for source, message in enumerate(('noSaveDirectoryMessage', 'noChampionsDirectoryMessage')):
                seen = []
                def player(key, options, current, **info):
                    seen.append(key)
                    if key == kind.value: return source
                    assert key == 'ACK' and info['prompt'] == game.assets.text(message) and info['message_colour'] == 14
                    return 0
                game.player = player
                action(game)
                assert seen == [kind.value, 'ACK'] and game.s.g['save.file_format'] == 1 - source


def save_load_callers():
    from unittest.mock import call, patch
    from . import save
    from .save_vault import write_vault
    from sm.engine import Session
    from .ui import screen
    with TemporaryDirectory(prefix='sm-dkk-save-callers-') as tmp:
        root, game = Path(tmp), Game(None)
        game.roster_directory = root
        create_party(game, (2,))
        game.age_pass = True
        game.s.g.update({'dkk.pictures': 0, 'dkk.animations': 1, 'dkk.delay': 7})
        game.s.treasure_money[4:7] = [70000, -1, 3]
        write_vault(game.s, root)
        pending = scripted(game, ((c.Kind.SLOT.value, 'B'),))
        c.save_menu(game)
        assert next(pending, None) is None and game.age_pass and game.s.g['save.recent'] == 1
        assert not (root / 'HERO0.PC').exists() and not (root / 'TMPVAULT.DAT').exists()
        assert (root / 'VAULTB.DAT').is_file()
        snapshot = save.load(root, 'B')
        assert snapshot.game.get('zone0')[0xFF] == 1 and snapshot.game.get('zone0')[0xFC] == 7
        loaded = Game(None)
        loaded.roster_directory = root
        loaded.age_pass = True
        loaded.s.g['save.recent'] = 0
        (root / 'HERO0.PC').write_bytes(bytes(game.s.party[0].b[:Character.SIZE]))
        pending = scripted(loaded, ((c.Kind.SLOT.value, 'Death'), (c.Kind.SLOT.value, 'B')))
        with patch.object(save, 'load_directory', wraps=save.load_directory) as directory:
            c.load_menu(loaded)
        assert directory.call_args_list == [call(loaded), call(loaded, root)]
        assert next(pending, None) is None and len(loaded.s.party) == loaded.s.r1[c.PARTY_SIZE] == 1
        assert loaded.vm.resuming and loaded.s.mode == 0 and loaded.s.g['vault.letter'] == 'B'
        assert loaded.age_pass and loaded.s.g['save.recent'] == 0
        assert not (root / 'HERO0.PC').exists()
        assert c.member_name(loaded.s.party[0]) == 'HERO0' and loaded.s.sel == 0
        session = Session(profile='dkk', game=loaded)
        try:
            controller = screen.Controller(session, presentation=False)
            for _ in range(loaded.menu_ids.index(c.SAVE)): controller.key('Down')
            controller.key('Return')
            assert session.error is None and session.decision['kind'] == c.Kind.SLOT.value
            assert [label for _, label in screen.menu_items(session.decision)][:10] == list(c.SLOTS)
            assert session.decision['info']['prompt'] == loaded.assets.text('saveWhichGamePrompt')
            files = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
            controller.key('Escape', chr(27))
            assert session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()} == files
            controller.key('Return'); controller.key('j', 'j')
            assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert (root / 'SAVGAMJ.PTY').is_file() and not (root / 'SAVGAMA.PTY').exists()
        finally: session.close()


def load_sources():
    from sm.titles.cok.records import SavedGame as ImportedGame, Character as ImportedCharacter
    with TemporaryDirectory(prefix='sm-dkk-load-sources-') as tmp:
        root, game = Path(tmp), Game(None)
        game.roster_directory = root / 'native'
        game.champions_directory = root / 'import'
        pending = scripted(game, ((c.Kind.SLOT.value, 'Exit'),))
        c.load_menu(game)
        assert next(pending, None) is None and 'save.file_format' not in game.s.g
        assert not game.roster_directory.exists() and not game.champions_directory.exists()
        pending = scripted(game, ((c.Kind.SLOT.value, 'Death'),))
        c.load_menu(game)
        assert next(pending, None) is None and game.s.g['save.file_format'] == 1 and not game.s.party
        create_party(game, (2,))
        c.save_game(game, 'A')
        rules.record(game.s.party[0]).set('experience', 243974)
        c.save_game(game, 'J')
        game.s.party.clear()
        game.s.r1[c.PARTY_SIZE] = 0
        (game.roster_directory / 'SAVGAMJ.PTY').rename(game.roster_directory / 'savgamj.pty')
        seen = []
        def player(kind, options, current, **info):
            seen.append(info)
            assert kind == c.Kind.SLOT.value and info['start'] == 0
            if info.get('source'):
                assert options == ('Death', 'Champions', 'Exit')
                assert info['prompt'] == game.assets.text('loadFromWherePrompt')
                return 0
            assert options == ('A', 'J', 'Exit') and info['enabled'] == (0, 9)
            assert info['menu_labels'] == tuple(c.SLOTS) and info['menu'] == game.assets.text('saveSlotMenu')
            assert info['prompt'] == game.assets.text('loadWhichGamePrompt')
            return options.index('J')
        game.player = player
        c.load_menu(game)
        assert len(seen) == 2 and rules.record(game.s.party[0]).get('experience') == 243974
        assert game.s.g['vault.letter'] == 'J' and game.vm.resuming
        from sm.engine import Session
        from .ui import screen
        keyed = Game(None)
        keyed.roster_directory = game.roster_directory
        session = Session(profile='dkk', game=keyed)
        try:
            controller = screen.Controller(session, save_root=keyed.roster_directory, presentation=False)
            controller.key('Down')
            controller.key('Down')
            controller.key('Return')
            assert session.decision['info']['source']
            controller.key('d', 'd')
            assert session.decision['options'] == ('A', 'J', 'Exit')
            slot_file = keyed.roster_directory / 'savgamj.pty'
            removed = slot_file.rename(root / 'removed.pty')
            controller.key('j', 'j')
            assert session.error is None and session.decision['options'] == ('A', 'J', 'Exit')
            assert not keyed.s.party and not keyed.vm.resuming and controller.selected == 1
            removed.rename(slot_file)
            controller.key('Return')
            assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert keyed.s.g['vault.letter'] == 'J' and rules.record(keyed.s.party[0]).get('experience') == 243974
        finally: session.close()
        game.s.party.clear()
        game.s.r1[c.PARTY_SIZE] = 0
        pending = scripted(game, ((c.Kind.SLOT.value, 'Death'), (c.Kind.SLOT.value, 'Exit')))
        c.load_menu(game)
        assert next(pending, None) is None and not game.s.party
        game.champions_directory.mkdir()
        old_game = ImportedGame()
        old_game.set('party_count', 1)
        old_game.set('party_names', (b'\x08CHRDATC1' + bytes(32)).ljust(328, b'\0'))
        old_game.data[615:617] = (1234).to_bytes(2, 'little')
        old_char = ImportedCharacter()
        old_char.set('name', b'\x05GUEST' + bytes(10))
        old_char.set('class', 2)
        old_char.set('race', 6)
        old_char.set('abilities', bytes((18, 18)) * 6)
        old_char.set('levels', bytes((0, 0, 3, 0, 0, 0, 0, 0)))
        old_char.set('age', 80)
        files = {'SAVGAMC.DAT': bytes(old_game), 'CHRDATC1.SAV': bytes(old_char)}
        for name, raw in files.items(): (game.champions_directory / name).write_bytes(raw)
        position = game.s.x, game.s.y, game.s.dataset
        slot_file = game.champions_directory / 'SAVGAMC.DAT'
        def remove_imported_slot(kind, options, current, **info):
            if info.get('source'): return options.index('Champions')
            assert options == ('C', 'Exit') and info['start'] == 0
            if slot_file.is_file():
                slot_file.unlink()
                return options.index('C')
            return options.index('Exit')
        game.player = remove_imported_slot
        c.load_menu(game)
        assert not game.s.party and (game.s.x, game.s.y, game.s.dataset) == position
        slot_file.write_bytes(bytes(old_game))
        pending = scripted(game, ((c.Kind.SLOT.value, 'Champions'), (c.Kind.SLOT.value, 'C')))
        c.load_menu(game)
        assert next(pending, None) is None and len(game.s.party) == game.s.r1[c.PARTY_SIZE] == 1
        assert game.s.g['save.file_format'] == 0 and not game.vm.resuming and game.s.mode == 0
        assert c.member_name(game.s.party[0]) == 'GUEST' and rules.record(game.s.party[0]).get('age') == 50
        assert game.s.r0[0x133:0x135] == [210, 4] and (game.s.x, game.s.y, game.s.dataset) == position
        assert all((game.champions_directory / name).read_bytes() == raw for name, raw in files.items())
        old_game.data[615:617] = bytes(2)
        (game.champions_directory / 'SAVGAMA.DAT').write_bytes(bytes(old_game))
        keyed = Game(None)
        keyed.roster_directory, keyed.champions_directory = game.roster_directory, game.champions_directory
        session = Session(profile='dkk', game=keyed)
        try:
            controller = screen.Controller(session, presentation=False)
            for key in ('Down', 'Down', 'Return'): controller.key(key)
            controller.key('c', 'c')
            assert session.decision['options'] == ('A', 'C', 'Exit') and controller.selected == 1
            controller.key('Return')
            assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert keyed.s.r0[0x133:0x135] == [210, 4]
        finally: session.close()


def item_casting():
    from types import SimpleNamespace
    from . import camp, inventory
    from .records import Item
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    for field, value in dict(active=1, abilities=bytes((14, 14)) * 6, base_move=12, class_mask=255).items(): r.set(field, value)
    item = Item()
    for field, value in dict(type=3, readied=1, quantity=1, powers=bytes((1, 15, 0))).items(): item.set(field, value)
    char.items = [item.data]
    game.s.party = [char]
    game.s.mode = inventory.IN_COMBAT
    calls = []
    def cast(index, spell, **options):
        calls.append((index, spell, options, game.using_item))
        return False
    def end(index):
        calls.append(('end', index))
        return True
    game.battle = SimpleNamespace(data={'active': True}, index=lambda member: 0,
                                 record=lambda index: {'item_ok': True, 'initiative': 7}, cast=cast, end=end)
    pending = scripted(game, ((inventory.Kind.ITEMS.value, 0), (inventory.Kind.ACTION.value, 'Use'), (camp.Kind.ACK.value, 'Continue')))
    assert inventory.items_menu(game, char) is True
    assert next(pending, None) is None and not char.items and not game.using_item
    assert calls == [(0, 15, {'using_item': True, 'ai': False}, True), ('end', 0)]


def last_member_reset():
    for action in (c.DROP, c.REMOVE):
        with TemporaryDirectory(prefix='sm-dkk-reset-') as tmp:
            game = Game(None)
            game.roster_directory = Path(tmp)
            create_party(game, (2,))
            game.s.r0[0x100], game.s.r1[0x2A8] = 91, 255
            game.s.x, game.s.y = 1, 2
            game.s.treasure_money[4] = 70000
            seed = game.s.seed
            steps = [(c.Kind.MAIN_MENU.value, game.assets.labels[action]), (c.Kind.WHO.value, 'Exit'),
                     (c.Kind.MAIN_MENU.value, game.assets.labels[action]), (c.Kind.WHO.value, 0)]
            steps += [(c.Kind.DROP.value, 'Yes'), (c.Kind.DROP.value, 'Yes'), ('ACK', 0)] if action == c.DROP else [(c.Kind.OVERWRITE.value, 'Yes')]
            steps += [(c.Kind.MAIN_MENU.value, game.assets.labels[c.QUIT]), (c.Kind.QUIT.value, 'Yes')]
            pending = scripted(game, steps)
            answer = game.player
            starts = iter((c.CREATE, action, c.CREATE))
            def player(kind, options, state, **info):
                if kind == c.Kind.MAIN_MENU.value:
                    assert options[info['start']] == game.assets.labels[next(starts)]
                return answer(kind, options, state, **info)
            game.player = player
            c.run(game)
            assert next(starts, None) is None
            assert next(pending, None) is None and not game.s.party and game.s.r1[c.PARTY_SIZE] == 0
            assert (game.s.x, game.s.y, game.s.dir, game.s.mode, game.s.prev_mode) == (7, 13, 2, 0, 4)
            assert game.s.r0[0x100] == game.s.r1[0x2A8] == 0 and game.s.seed == seed
            assert game.s.treasure_money[4] == 70000 and game.s.g['dkk.runtime']['mouse_mode'] == 0
            assert (Path(tmp) / 'HERO0.PC').exists() == (action == c.REMOVE)
    game = Game(None)
    char = rules.character(bytes(Character()))
    game.s.party.append(char)
    game.s.r1[c.PARTY_SIZE], game.s.r0[0x100] = 1, 91
    c.remove_creature(game, char)
    assert game.s.r0[0x100] == 91


def class_recalculation():
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r, book = rules.record(char), rules.spellbook(char)
    r.set('race', 6)
    r.set('deity', 1)
    r.set('levels', bytes((1, 0, 0, 0, 0, 0, 0, 0)))
    r.set('abilities', bytes((14, 14)) * 6)
    book.set('spell_slots', bytes((123,)) * 32)
    book.set('known_spells', bytes((7,)) * 114)
    before = bytes(char.b)
    rules.recalc_cleric_slots(char)
    at = Character.SIZE + c.Spells.FIELDS['spell_slots'][0]
    assert char.b[:at] == before[:at] and char.b[at + 7:] == before[at + 7:]
    assert book.get('spell_slots')[:7] == bytes((3, 0, 0, 0, 0, 0, 0))
    r.set('deity', 6)
    rules.recalc_cleric_slots(char)
    assert book.get('spell_slots')[0] == 4
    r.set('levels', bytes(8))
    before = bytes(char.b)
    rules.recalc_cleric_slots(char)
    assert bytes(char.b) == before
    r.set('levels', bytes((0, 0, 1, 0, 0, 0, 0, 0)))
    r.set('abilities', bytes((18, 18)) * 6)
    rules.recalc_saves(char)
    human = r.get('saves')
    r.set('race', 3)
    rules.recalc_saves(char)
    assert r.get('saves')[0] == human[0] + 5 and r.get('saves')[1:] == human[1:]
    r.set('race', 6)
    charm = c.Item()
    charm.set('powers', bytes((0, 0, 134)))
    charm.set('readied', 1)
    char.items.append(charm.data)
    rules.recalc_saves(char)
    assert r.get('saves')[0] == human[0] + 5
    charm.set('readied', 0)
    rules.recalc_saves(char)
    assert r.get('saves') == human
    r.set('levels', bytes((0, 0, 13, 0, 0, 0, 0, 0)))
    r.set('attacks', 2)
    rules.recalc_class_stats(char)
    assert r.get('attacks') == 4 and r.get('highest_level') == 13
    r.set('levels', bytes((0, 0, 12, 0, 0, 0, 0, 0)))
    rules.recalc_class_stats(char)
    assert r.get('attacks') == 3 and r.get('highest_level') == 12
    r.set('levels', bytes((0, 0, 6, 0, 0, 0, 0, 0)))
    r.set('attacks', 4)
    rules.recalc_class_stats(char)
    assert r.get('attacks') == 4
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 5, 0)))
    r.set('abilities', bytes((14, 14)) * 6)
    rules.recalc_thief_skills(char)
    earlier = r.get('thief_skills')
    char.b[c.F['abilities'] + 7] = 18
    rules.recalc_thief_skills(char)
    assert r.get('thief_skills')[:5] != earlier[:5] and r.get('thief_skills')[5:] == earlier[5:]


def creation_intermediate():
    for cls in (c.CLERIC, c.RANGER, c.THIEF):
        game = Game(None)
        seen = {}
        def player(kind, options, current, **info):
            if kind == c.Kind.RACE.value: return 6
            if kind == c.Kind.CLASS.value: return options.index(game.assets.names('classNames')[cls])
            if kind in (c.Kind.DEITY.value, c.Kind.ALIGNMENT.value):
                raw = game.s.g[c.PENDING][0]
                r = c.Character(bytes(raw[:c.Character.SIZE]))
                assert r.get('class_mask') > 0 and r.get('base_thac0') > 0
                assert all(r.get('saves'))
                if cls == c.RANGER: assert r.get('levels')[c.RANGER] == 2
                if cls == c.THIEF: assert any(r.get('thief_skills'))
                if kind == c.Kind.DEITY.value:
                    seen['attack'] = r.get('base_thac0')
                    return 2
                if cls == c.CLERIC: assert r.get('base_thac0') == seen['attack'] + 1
                seen['finished'] = True
                return options.index('Exit')
            return 0
        game.player = player
        assert c.create(game) is None and seen['finished'] and c.PENDING not in game.s.g


def starting_spell_order():
    from unittest.mock import patch
    for cls in (c.CLERIC, c.RANGER, c.MAGE):
        game, seen = Game(None), {}
        game.s.r1[0x2A8] = 7
        game.s.r1[0x372] = 3
        original = c.gain_hp
        def gain(state, char, mask, divisor, t):
            if mask == 255:
                r, book = rules.record(char), rules.spellbook(char)
                assert (r.get('base_thac0'), r.get('saves'), r.get('highest_level')) == seen['initial']
                assert r.get('levels')[cls] == 1
                if cls == c.CLERIC:
                    assert book.get('spell_slots')[0] >= 1
                    assert book.get('known_spells')[0] == 1
                elif cls == c.MAGE:
                    assert book.get('spell_slots') == bytes(24) + bytes((1,)) + bytes(7)
                    assert all(book.get('known_spells')[ident - 1] for ident in c.MAGE_START)
                else:
                    assert book.get('spell_slots') == bytes(32)
                    assert book.get('known_spells') == bytes(114)
                seen['gain'] = True
            else:
                assert state.r1[0x2A8] == 255
                assert state.g['dkk.runtime']['auto_training'] == 1
            return original(state, char, mask, divisor, t)
        def player(kind, options, current, **info):
            if kind == c.Kind.RACE.value: return 6
            if kind == c.Kind.CLASS.value: return options.index(game.assets.names('classNames')[cls])
            if kind == c.Kind.ALIGNMENT.value:
                r = c.Character(bytes(game.s.g[c.PENDING][0][:c.Character.SIZE]))
                seen['initial'] = r.get('base_thac0'), r.get('saves'), r.get('highest_level')
            if kind == c.Kind.ROLL.value:
                assert info['start'] == 1 and seen['gain']
                assert game.s.r1[0x2A8] == 7
                runtime = game.s.g['dkk.runtime']
                assert runtime['auto_training'] == 0 and runtime['training_done'] == 1
                raw = game.s.g[c.PENDING][0]
                r = c.Character(raw[:Character.SIZE])
                assert r.get('weight') == 500 and r.get('damage_dice')[0] == 2
                seen['move'] = r.get('move')
                raw[c.F['move']] = 0
                return 1
            if kind == c.Kind.NAME.value:
                assert game.s.g[c.PENDING][0][c.F['move']] == seen['move'] > 0
                return 'ROOK'
            if kind == c.Kind.ICON.value:
                raw = game.s.g[c.PENDING][0]
                raw[c.F['abilities']] = raw[c.F['strength_extra_base']] = 0
                return options.index('Yes' if 'Yes' in options else 'Exit')
            if kind == c.Kind.SAVE.value:
                r = c.Character(game.s.g[c.PENDING][0][:Character.SIZE])
                assert r.get('abilities')[::2] == r.get('abilities')[1::2]
                assert r.get('strength_extra_base') == r.get('strength_extra')
                return 1
            return 0
        game.player = player
        with patch.object(c, 'gain_hp', gain):
            assert c.create(game) is None
        assert seen['gain']
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r, book = rules.record(char), rules.spellbook(char)
    r.set('levels', bytes((1, 0, 0, 0, 0, 1, 0, 0)))
    r.set('deity', 1)
    r.set('abilities', bytes((14, 14)) * 6)
    book.set('spell_slots', bytes((123,)) * 32)
    book.set('known_spells', bytes((7,)) * 114)
    before = bytes(char.b[:Character.SIZE])
    c.starting_spells(char)
    assert bytes(char.b[:Character.SIZE]) == before
    slots = book.get('spell_slots')
    assert slots[:7] == bytes((3, 0, 0, 0, 0, 0, 0))
    assert slots[7:24] == bytes((123,)) * 17 and slots[24] == 1 and slots[25:] == bytes((123,)) * 7
    assert book.get('known_spells')[-1] == 7


def modify_rules():
    t = c.tables(Game(None).assets)
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r, book = rules.record(char), rules.spellbook(char)
    r.set('race', 6)
    r.set('class', c.PALADIN)
    r.set('levels', bytes((0, 0, 0, 1, 0, 0, 0, 0)))
    r.set('abilities', bytes((18, 18)) * 6)
    r.set('strength_extra', 99)
    c.adjust_modified(char, t, c.STRENGTH, 1)
    assert r.get('abilities')[1] == 18 and r.get('strength_extra') == 100
    c.adjust_modified(char, t, c.STRENGTH, 1)
    assert r.get('strength_extra') == 100
    c.adjust_modified(char, t, c.STRENGTH, -1)
    assert r.get('abilities')[1] == 18 and r.get('strength_extra') == 99
    r.set('race', c.MOUNTAIN_DWARF)
    char.b[c.F['abilities'] + 11] = 17
    for delta in (-1, 1):
        c.adjust_modified(char, t, 5, delta)
        assert r.get('abilities')[11] == 17
    r.set('race', 6)
    r.set('class', 8)
    r.set('levels', bytes((1, 0, 1, 0, 0, 0, 0, 0)))
    r.set('deity', 1)
    r.set('abilities', bytes((14, 14)) * 6)
    r.set('hp_max', 10)
    r.set('hp', 2)
    r.set('base_move', 12)
    r.set('name', b'\x04ROOK' + bytes(11))
    book.set('spell_slots', bytes((123,)) * 32)
    book.set('known_spells', bytes((7,)) * 114)
    saved = c.modify_snapshot(char)
    c.adjust_modified(char, t, c.WISDOM, -1)
    r.set('hp_max', 8)
    r.set('name', b'\x04TEST' + bytes(11))
    c.restore_modified(char, saved, 3)
    assert r.get('abilities') == bytes((14, 14)) * 6
    assert r.get('hp') == r.get('hp_max') == 10 and r.get('move') == 15
    assert r.get('name') == saved[3]
    assert book.get('spell_slots') == bytes((1,)) + bytes((123,)) * 31
    r.set('saves', bytes((9,)) * 5)
    r.set('attacks', 4)
    r.set('base_thac0', 55)
    char.b[c.F['abilities'] + 9] = 3
    c.keep_modified(char, t)
    assert r.get('hp_rolled') == 140
    assert r.get('abilities')[8:10] == bytes((3, 3))
    assert r.get('saves') == bytes((9,)) * 5 and r.get('attacks') == 4 and r.get('base_thac0') == 55
    assert book.get('spell_slots')[:7] == bytes((3, 0, 0, 0, 0, 0, 0))
    assert book.get('spell_slots')[7:] == bytes((123,)) * 25
    assert book.get('known_spells') == bytes((7,)) * 114
    r.set('class', c.FIGHTER)
    r.set('levels', bytes((0, 0, 1, 0, 0, 0, 0, 0)))
    assert c.hp_minimum(char, t) == 1
    char.b[c.F['abilities'] + 9] = 7
    r.set('hp_max', 40)
    c.adjust_modified(char, t, c.CONSTITUTION, -1)
    assert r.get('abilities')[9] == 7 and r.get('hp_max') == r.get('hp') == 10
    char.b[c.F['abilities'] + 9] = 17
    r.set('hp_max', 1)
    c.adjust_modified(char, t, c.CONSTITUTION, 1)
    assert r.get('hp_max') == r.get('hp') == 5
    r.set('hp_max', 255)
    c.adjust_modified(char, t, 7, 1)
    assert r.get('hp_max') == r.get('hp') == 0
    c.adjust_modified(char, t, 7, -1)
    assert r.get('hp_max') == r.get('hp') == 255
    r.set('levels', bytes((0, 0, 0, 0, 1, 0, 0, 0)))
    assert c.hp_minimum(char, t) == 6
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 0, 1)))
    assert c.hp_minimum(char, t) == 6
    r.set('levels', bytes((255, 0, 1, 0, 0, 0, 0, 0)))
    assert c.hp_minimum(char, t) == 5


def modify_editor():
    from unittest.mock import patch
    game = Game(None)
    game.s.r1[0x372] = 3
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r, book = rules.record(char), rules.spellbook(char)
    for field, value in dict(race=6, gender=0, experience=210003, abilities=bytes((14, 14)) * 6,
                             base_move=12, hp_max=10, hp=2, name=b'\x04ROOK' + bytes(11),
                             deity=1, **{'class': 8}).items(): r.set(field, value)
    r.set('levels', bytes((1, 0, 1, 0, 0, 0, 0, 0)))
    for value in (210003, 105002, 70001):
        r.set('experience', value)
        editor = c.ModifyEditor(game, char)
        assert editor.field == 0 and editor.cursor == 1 and editor.result is None
        assert r.get('hp') == 2 and r.get('move') == 12
    for value in (0, 210002, 210004, 0xFFFFFFFF):
        r.set('experience', value)
        before = bytes(char.b)
        try: c.ModifyEditor(game, char)
        except ValueError: pass
        else: raise AssertionError('ineligible character entered Modify')
        assert bytes(char.b) == before
    r.set('experience', 210003)
    book.set('spell_slots', bytes((4,)) * 32)
    saved = c.modify_snapshot(char)
    editor = c.ModifyEditor(game, char)
    for _ in range(8): assert editor.step(80, True) is None
    assert editor.field == 0
    editor.step(72, True)
    assert editor.field == 7
    editor.step(72, True)
    assert editor.field == 6
    editor.step(ord('K'))
    assert c.member_name(char) == 'KOOK' and editor.cursor == 2 and editor.result is None
    for key in (27, 13, 92, ord('1')):
        editor.step(key)
        assert c.member_name(char) == 'KOOK' and editor.field == 6 and editor.cursor == 2
    editor.step(27, True)
    assert editor.result is None
    editor.step(55, True, mouse_field=2)
    assert editor.field == 6 and editor.cursor == 2
    editor.step(8)
    assert c.member_name(char) == 'OOK' and editor.cursor == 2
    editor.step(83, True)
    assert c.member_name(char) == 'OK' and editor.cursor == 2
    editor.step(83, True)
    assert c.member_name(char) == 'O' and editor.cursor == 1
    for key, extended in ((8, False), (83, True)):
        editor.step(key, extended)
        assert c.member_name(char) == 'O' and editor.cursor == 1
    editor.step(ord('Q'))
    assert c.member_name(char) == 'Q ' and editor.cursor == 2
    for _ in range(20): editor.step(ord('Z'))
    assert c.member_name(char) == 'Q' + 'Z' * 14 and editor.cursor == 15
    editor.step(ord('8'))
    assert editor.field == 5
    editor.step(71, True, mouse_field=c.WISDOM)
    editor.step(1)
    assert r.get('abilities')[5] == 13 and book.get('spell_slots')[0] == 1
    assert editor.step(27, True) is False
    assert c.modify_snapshot(char) == saved and r.get('hp') == 10 and r.get('move') == 15
    assert book.get('spell_slots') == bytes((1,)) + bytes((4,)) * 31
    try: editor.step(0)
    except ValueError: pass
    else: raise AssertionError('closed editor accepted a key')
    r.set('class', c.FIGHTER)
    r.set('levels', bytes((0, 0, 1, 0, 0, 0, 0, 0)))
    r.set('hp_max', 40)
    r.set('hp', 40)
    char.b[c.F['abilities'] + 9] = 8
    editor = c.ModifyEditor(game, char)
    editor.step(71, True, mouse_field=c.CONSTITUTION)
    with patch.object(rules, 'recalc_stats', wraps=rules.recalc_stats) as recalc:
        editor.step(1)
        assert recalc.call_count == 2
    assert r.get('hp_max') == r.get('hp') == 10 and r.get('move') == 12
    assert editor.display_hp == 10 and editor.dirty == (4, 6, 7)
    editor.step(71, True, mouse_field=7)
    assert editor.display_hp == 10
    assert editor.step(3) is False and r.get('hp') == r.get('hp_max') == 40
    assert r.get('abilities')[9] == 8
    r.set('hp_max', 10)
    r.set('hp', 10)
    r.set('class', 8)
    r.set('levels', bytes((1, 0, 1, 0, 0, 0, 0, 0)))
    r.set('saves', bytes((9,)) * 5)
    r.set('attacks', 4)
    r.set('base_thac0', 55)
    editor = c.ModifyEditor(game, char)
    editor.step(71, True, mouse_field=c.WISDOM)
    editor.step(0)
    assert editor.step(2) is True
    assert r.get('abilities')[4:6] == bytes((15, 15))
    assert r.get('attacks') == 4 and r.get('base_thac0') == 55 and r.get('saves') == bytes((9,)) * 5
    assert book.get('spell_slots')[0] > 1 and book.get('spell_slots')[7:] == bytes((4,)) * 25


def modify_driver():
    from sm.engine import Session
    from .ui import screen
    from unittest.mock import patch
    game = Game(None)
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r = rules.record(char)
    for field, value in dict(race=6, gender=0, experience=210003, abilities=bytes((14, 14)) * 6,
                             base_move=12, hp_max=10, hp=2, name=b'\x04ROOK' + bytes(11),
                             active=1, levels=bytes((0, 0, 1, 0, 0, 0, 0, 0)),
                             **{'class': c.FIGHTER}).items(): r.set(field, value)
    game.s.party = [char]
    pending = scripted(game, [(c.Kind.WHO.value, 'Exit')])
    saved = bytes(char.b)
    assert not c.modify(game) and bytes(char.b) == saved and next(pending, None) is None
    events = iter(('#71:4', 's', '#71', '#71:6', 'K', chr(27), '#83', '8', 'e'))
    def keys(kind, options, current, **info):
        assert kind == 'CREATE_MODIFY' and options is None
        assert info['menu'] == 'Add Subtract Keep Exit' and info['query'] == game.assets.text('modifyQuery')
        assert isinstance(info['dirty'], str) and info['display_hp'] == r.get('hp')
        if info['name'] == 'KOOK': assert info['field'] == 6
        return next(events)
    game.player = keys
    saved = c.modify_snapshot(char)
    assert not c.modify(game, char) and c.modify_snapshot(char) == saved and r.get('hp') == 10
    assert next(events, None) is None
    session = Session(profile='dkk', game=game)
    try:
        controller = screen.Controller(session, presentation=False)
        for key in ('Down', 'Down', 'Return', 'Return'): controller.key(key)
        assert session.error is None and session.decision['kind'] == 'CREATE_MODIFY'
        assert session.decision['info']['field'] == 0 and session.decision['info']['choice'] == 0
        for key in ('Up', 'Up'): controller.key(key)
        controller.key('K', 'K')
        controller.key('Escape', chr(27))
        assert c.member_name(char) == 'KOOK' and session.decision['info']['field'] == 6
        controller.key('BackSpace', chr(8))
        assert c.member_name(char) == 'OOK'
        controller.key('8', '8')
        controller.key('Escape', chr(27))
        assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
        assert c.modify_snapshot(char) == saved
        controller.key('Return'); controller.key('Return')
        with patch.object(rules, 'recalc_stats', wraps=rules.recalc_stats) as recalc:
            controller.key('Right')
            assert recalc.call_count == 0 and session.decision['info']['choice'] == 1
        controller.key('Return')
        assert r.get('abilities')[1] == 13
        controller.key('Right'); controller.key('Return')
        assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
        assert r.get('abilities')[:2] == bytes((13, 13))
        controller.key('Return'); controller.key('Return')
        controller.key('6', '6')
        assert session.decision['info']['choice'] == 1 and r.get('abilities')[1] == 13
        controller.key('Return')
        assert r.get('abilities')[1] == 12
        controller.key('e', 'e')
        assert r.get('abilities')[1] == 13 and session.decision['kind'] == c.Kind.MAIN_MENU.value
        r.set('experience', 210004)
        before = bytes(char.b)
        with patch.object(game, 'ask', wraps=game.ask) as ask:
            controller.key('Return'); controller.key('Return')
            assert session.error is None and session.decision['kind'] == c.Kind.MAIN_MENU.value
            assert bytes(char.b) == before
            ack = next(call.kwargs for call in ask.call_args_list if call.args[0] == 'ACK')
            assert ack['prompt'] == 'ROOK' + game.assets.text('cantBeModifiedText')
            assert ack['timed'] == 1 and ack['message_colour'] == 14
    finally: session.close()


def join_restore_movement():
    from types import SimpleNamespace
    from . import effects
    game = Game(None)
    game.s.r1[0x372] = 3
    members = {}
    for side in (0, 1):
        raw = Character()
        raw.set('abilities', bytes((18, 18)) * 6)
        raw.set('levels', bytes((0, 0, 1, 0, 0, 0, 0, 0)))
        raw.set('base_move', 12)
        raw.set('side', side)
        members[str(side)] = {'GAM': [raw]}
        char = rules.character(bytes(raw))
        c.join(game, char)
        assert rules.record(char).get('move') == (15 if side == 0 else 12)
    rules.restore(game.s, SimpleNamespace(members=members))
    assert [rules.record(char).get('move') for char in game.s.party] == [15, 12]
    rules.record(game.s.party[0]).set('base_move', 200)
    rules.recalc(game.s.party[0], 3)
    assert rules.record(game.s.party[0]).get('move') == 75
    game.s.party.clear()
    raw.set('abilities', bytes((14, 7)) + bytes((18, 18)) * 5)
    char = rules.character(bytes(raw))
    effects.add_effect(char, 12, 10, 119, False)
    c.join(game, char)
    assert char.b[c.F['abilities']:c.F['abilities'] + 2] == bytes((14, 19))
    assert char.b[c.F['strength_extra']] == 0 and rules.record(char).get('order') == 0


def join_append_contract():
    from unittest.mock import patch
    from . import effects
    for npc, count in ((0, 7), (127, 255), (128, 7), (255, 255)):
        game = Game(None)
        for order in (0, 2):
            member = rules.character(bytes(Character()))
            rules.record(member).set('order', order)
            game.s.party.append(member)
        game.s.r1[c.PARTY_SIZE] = count
        raw = Character()
        raw.set('abilities', bytes((14, 7)) + bytes((18, 18)) * 5)
        raw.set('levels', bytes((0, 0, 1, 0, 0, 0, 0, 0)))
        raw.set('npc', npc)
        raw.set('order', 6)
        char = rules.character(bytes(raw))
        effects.add_effect(char, 12, 10, 119, False)
        observations, recalc = [], rules.recalc_class_stats
        def observe(member, slots=None):
            observations.append((member in game.s.party, game.s.sel, game.s.r1[c.PARTY_SIZE],
                                 rules.record(member).get('order'), member.b[c.F['abilities'] + 1]))
            return recalc(member, slots)
        with patch.object(rules, 'recalc_class_stats', side_effect=observe):
            c.join(game, char)
        assert game.s.party[-1] is char and game.s.sel == 2
        assert game.s.r1[c.PARTY_SIZE] == (count + 1) & 255
        assert rules.record(char).get('order') == 1
        expected = [(False, 0, count, 6, 19)]
        if npc > 127: expected.append((True, 2, (count + 1) & 255, 1, 19))
        assert observations == expected


def overwrite_prompt():
    with TemporaryDirectory(prefix='sm-dkk-roster-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        game.s.g['save.file_format'] = 0
        char = rules.character(bytes(Character()))
        r = rules.record(char)
        r.set('name', b'\x04ROOK' + bytes(11))
        original = bytes(char.b)
        for stem in ('ROOK', 'A..B'): (Path(tmp) / (stem + '.PC')).write_bytes(original)
        pending = iter(((c.Kind.OVERWRITE.value, 'ROOK', 1), (c.Kind.FILE_NAME.value, '', ''),
                        (c.Kind.FILE_NAME.value, '', 'A..B'), (c.Kind.OVERWRITE.value, 'A..B', 1),
                        (c.Kind.FILE_NAME.value, '', 'X.Y')))
        def player(kind, options, current, **info):
            expected, stem, answer = next(pending)
            assert kind == expected
            assert game.s.g['save.file_format'] == 1
            if kind == c.Kind.OVERWRITE.value:
                assert info['start'] == 1
                assert info['prompt'] == game.assets.text('overwritePrefix') + stem + game.assets.text('overwriteSuffix')
            else:
                assert info['prompt'] == game.assets.text('newFileNamePrompt') and info['min_length'] == 1 and info['max_length'] == 8
            return answer
        game.player = player
        assert c.store(game, char) == 'X.Y' and next(pending, None) is None
        assert r.get('name') == b'\x03X.YB' + bytes(11)
        for stem in ('ROOK', 'A..B'): assert (Path(tmp) / (stem + '.PC')).read_bytes() == original
        assert (Path(tmp) / 'X.Y.PC').read_bytes() == bytes(char.b)
        r.set('name', b'\x04ROOK' + bytes(11))
        pending = iter(((c.Kind.OVERWRITE.value, 'ROOK', 0),))
        r.set('hp', 7)
        assert c.store(game, char) == 'ROOK' and next(pending, None) is None
        assert (Path(tmp) / 'ROOK.PC').read_bytes() == bytes(char.b)
        folder = Path(tmp)
        (folder / 'X.Y.JNK').write_bytes(bytes(c.Item()))
        assert not c.read_character(folder / 'X.Y.PC').items
        (folder / 'XC.JNK').write_bytes(bytes(c.Item()))
        assert len(c.read_character(folder / 'X.Y.PC').items) == 1
        r.set('name', b'\x01.' + bytes(14))
        assert c.store(game, char) == ''
        assert c.member_name(c.read_character(folder / '.PC')) == '.'
        game.roster_directory = folder / 'private'
        r.set('name', b'\x04ROOK' + bytes(11))
        assert c.store(game, char) == 'ROOK'
        pending = iter(((c.Kind.OVERWRITE.value, 'ROOK', 1), (c.Kind.FILE_NAME.value, '', '../ROOK')))
        r.set('hp', 9)
        assert c.store(game, char) is None and next(pending, None) is None
        assert c.member_name(char) == '../ROOK' and c.read_character(folder / 'ROOK.PC').b[c.F['hp']] == 7


def signed_scroll_readiness():
    from unittest.mock import patch
    from . import inventory
    game = Game(None)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('class_mask', 255)
    item = c.Item()
    item.set('type', 39)
    char.items.append(item.data)
    for level, message in ((128, 'Wrong Magical Order'), (255, 'Wrong Magical Order'), (0, 'Wrong Magical Order'),
                           (1, 'Thief Level Too Low'), (9, 'Thief Level Too Low'), (10, None)):
        char.b[c.F['levels'] + c.THIEF] = level
        item.set('readied', 0)
        with patch.object(inventory.shop, 'pause') as pause:
            inventory.toggle_ready(game, char, item.data)
        assert item.get('readied') == int(message is None)
        if message is None: pause.assert_not_called()
        else: pause.assert_called_once_with(game, message, timed=1, message_colour=10)
    item.set('readied', 0)
    item.set('unidentified', 0x20)
    r.set('robe_order', 1)
    char.b[c.F['levels'] + c.THIEF] = 255
    with patch.object(inventory.shop, 'pause') as pause:
        inventory.toggle_ready(game, char, item.data)
    assert item.get('readied') == 1
    pause.assert_not_called()


def readiness():
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('race', 6)
    r.set('deity', 1)
    r.set('levels', bytes((1, 0, 0, 0, 0, 0, 0, 0)))
    threshold = rules.tables().level_xp(0, 2)
    r.set('experience', threshold - 1)
    r.set('level_up_ready', 1)
    assert not c.refresh_level_up(char) and r.get('level_up_ready') == 0
    r.set('experience', threshold)
    r.set('status', 6)
    assert c.can_level_up(char) and c.refresh_level_up(char) and r.get('level_up_ready') == 1
    for experience in (0x80000000, 0xFFFFFFFF):
        r.set('experience', experience)
        r.set('level_up_ready', 1)
        assert not c.eligible(char) and not c.refresh_level_up(char) and r.get('level_up_ready') == 0
    r.set('experience', 0x7FFFFFFF)
    assert c.eligible(char) == (c.CLERIC,)
    r.set('race', 5)
    cap = rules.tables().u8('racialLevelCaps', 5 * 8 + c.FIGHTER)
    r.set('levels', bytes((0, 0, cap, 0, 0, 0, 0, 0)))
    r.set('experience', 2000000000)
    assert not c.refresh_level_up(char)
    r.set('levels', bytes((18, 0, 0, 0, 0, 0, 0, 0)))
    assert not c.can_level_up(char)
    r.set('abilities', bytes((18, 18)) * 6)
    assert rules.class_con_adjust(char, c.PALADIN) == 4
    assert rules.class_con_adjust(char, c.CLERIC) == 2
    for con, expected in ((3, -2), (6, -1), (7, 0), (14, 0), (15, 1), (16, 2), (19, 5)):
        char.b[c.F['abilities'] + 9] = con
        assert rules.class_con_adjust(char, c.KNIGHT) == expected
    char.b[c.F['abilities'] + 9] = 20
    assert rules.class_con_adjust(char, c.CLERIC) == 70
    assert rules.class_con_adjust(char, c.RANGER) == 70


def knight_orders():
    game = Game(None)
    char = rules.character(bytes(Character()), spells=bytes(c.Spells()))
    r = rules.record(char)
    r.set('race', 6)
    r.set('class', c.KNIGHT)
    r.set('knight_order', 1)
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 0, 10)))
    r.set('abilities', bytes((18, 18)) * 6)
    r.set('hp_rolled', 40)
    r.set('hp_max', 60)
    r.set('hp', 60)
    seen = []
    def player(kind, options, current, **info):
        assert kind == 'CREATE_KNIGHT' and options == ('Change', 'Exit')
        seen.append(info)
        return 0
    game.player = player
    assert c.knight_promotion(game, char)
    assert game.assets.text('tooInexperiencedText') in seen[0]['prompt']
    assert r.get('knight_order') == 2 and c.levels(char.b)[c.KNIGHT] == 9
    assert (r.get('hp_rolled'), r.get('hp_max'), r.get('hp')) == (38, 58, 58)
    r.set('levels', bytes((0, 0, 0, 0, 0, 0, 0, 4)))
    r.set('hp_rolled', 25)
    r.set('hp_max', 40)
    r.set('hp', 20)
    assert c.knight_promotion(game, char)
    assert r.get('knight_order') == 3 and c.levels(char.b)[c.KNIGHT] == 3
    assert (r.get('hp_rolled'), r.get('hp_max'), r.get('hp')) == (20, 31, 20)
    before = bytes(char.b)
    assert not c.knight_promotion(game, char) and bytes(char.b) == before and len(seen) == 2
    r.set('knight_order', 1)
    r.set('experience', 2000000000)
    r.set('abilities', bytes((3, 18)) * 6)
    game.player = lambda kind, options, current, **info: 1
    before = bytes(char.b)
    assert not c.knight_promotion(game, char) and bytes(char.b) == before

    game.player = player
    assert c.knight_promotion(game, char)
    assert game.assets.text('doesNotQualifyText') in seen[-1]['prompt']
    assert r.get('knight_order') == 2 and c.levels(char.b)[c.KNIGHT] == 3
    r.set('knight_order', 1)
    r.set('abilities', bytes((18, 18)) * 6)
    assert c.knight_promotion(game, char)
    assert seen[-1]['prompt'].endswith(game.assets.text('knightOfTheText') + game.assets.text('swordText'))
    assert game.assets.text('mayBecomeText') in seen[-1]['prompt']
    for level in (1, 4):
        r.set('knight_order', 1)
        r.set('levels', bytes(7) + bytes((level,)))
        r.set('experience', -1, signed=True)
        assert c.knight_promotion(game, char)
        assert game.assets.text('tooInexperiencedText') in seen[-1]['prompt']
        assert r.get('knight_order') == 2 and c.levels(char.b)[c.KNIGHT] == level - 1
    r.set('levels', bytes(8))
    before = bytes(char.b)
    assert not c.knight_promotion(game, char) and bytes(char.b) == before


def level_hit_points():
    t = c.tables(Game(None).assets)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    r.set('abilities', bytes((18, 18)) * 6)
    r.set('deity', 1)
    def at(cls, level):
        lv = bytearray(8)
        lv[cls] = level
        r.set('levels', lv)
    for cls, level, cap in ((0, 9, 100), (0, 10, 92), (1, 14, 140), (1, 15, 112),
                             (2, 9, 126), (2, 10, 129), (3, 1, 14), (4, 10, 132),
                             (4, 11, 134), (5, 11, 66), (5, 12, 67), (6, 10, 80),
                             (6, 11, 82), (7, 9, 140), (7, 10, 129)):
        at(cls, level)
        assert c.hit_point_cap(char) == cap, (cls, level, c.hit_point_cap(char), cap)
    at(0, 9)
    r.set('deity', 5)
    assert c.hit_point_cap(char) == 90
    r.set('levels', bytes((9, 0, 9, 0, 0, 0, 0, 0)))
    assert c.hit_point_cap(char) == 108
    r.set('levels', bytes((255, 128, 0, 0, 0, 0, 0, 0)))
    assert c.hit_point_cap(char) == 0
    at(2, 127)
    char.b[c.F['abilities'] + 9] = 19
    assert c.hit_point_cap(char) == 233
    class Rolls:
        def __init__(self, values):
            self.values = iter(values)
            self.count = 0
        def random(self, sides):
            value = next(self.values)
            assert 0 <= value < sides
            self.count += 1
            return value
    at(2, 1)
    char.b[c.F['abilities'] + 9] = 18
    for field in ('hp', 'hp_rolled', 'hp_max'): r.set(field, 20)
    dice = Rolls((0, 9))
    c.gain_hp(dice, char, 255, 0, t)
    assert dice.count == 2 and all(r.get(field) == 0 for field in ('hp', 'hp_rolled', 'hp_max'))
    r.set('levels', bytes((1, 0, 1, 0, 0, 0, 0, 0)))
    r.set('deity', 1)
    char.b[c.F['abilities'] + 9] = 3
    r.set('hp_rolled', 0)
    r.set('hp_max', 10)
    r.set('hp', 5)
    dice = Rolls((0,) * 6)
    c.gain_hp(dice, char, 255, 2, t)
    assert dice.count == 6 and (r.get('hp_rolled'), r.get('hp_max'), r.get('hp')) == (1, 136, 131)
    at(2, 9)
    char.b[c.F['abilities'] + 9] = 18
    r.set('hp_rolled', 150)
    r.set('hp_max', 200)
    r.set('hp', 190)
    c.adjust_level_hp(Rolls((0, 0)), char, 255, 1, False, t)
    assert (r.get('hp_rolled'), r.get('hp_max'), r.get('hp')) == (149, 126, 116)
    r.set('hp_rolled', 1)
    r.set('hp_max', 2)
    r.set('hp', 1)
    c.adjust_level_hp(Rolls((9, 9)), char, 255, 1, False, t)
    assert all(r.get(field) == 0 for field in ('hp', 'hp_rolled', 'hp_max'))
    r.set('levels', bytes((2, 0, 10, 0, 0, 0, 0, 0)))
    char.b[c.F['abilities'] + 9] = 14
    c.gain_hp(Rolls((7, 7)), char, 255, 2, t)
    assert r.get('hp_rolled') == 1 and r.get('hp_max') == 1
    r.set('levels', bytes((2, 15, 0, 0, 0, 0, 0, 0)))
    c.gain_hp(Rolls((7, 7)), char, 255, 2, t)
    assert r.get('hp_rolled') == 5 and r.get('hp_max') == 5
    at(2, 255)
    r.set('hp_rolled', 255)
    r.set('hp_max', 255)
    r.set('hp', 250)
    dice = Rolls(())
    c.gain_hp(dice, char, 255, 1, t)
    assert dice.count == 0 and all(r.get(field) == 0 for field in ('hp', 'hp_rolled', 'hp_max'))
    r.set('levels', bytes((7, 0, 0, 0, 6, 0, 0, 0)))
    r.set('deity', 2)
    char.b[c.F['abilities'] + 9] = 20
    r.set('hp_rolled', 59)
    r.set('hp_max', 78)
    r.set('hp', 46)
    state = Game(None).s
    state.seed = 3216934686
    c.adjust_level_hp(state, char, t.classBits[c.RANGER], 2, False, t)
    assert (r.get('hp_rolled'), r.get('hp_max'), r.get('hp')) == (56, 73, 41)
    assert state.seed == 2912314868
