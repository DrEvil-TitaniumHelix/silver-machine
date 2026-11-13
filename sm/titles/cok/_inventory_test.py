import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import _shop_test, creation, effects, inventory, rules, shop
from sm.titles.cok.creation import F
from sm.titles.cok.inventory import Kind
from sm.titles.cok.menu import Game
from sm.titles.cok.records import Item
from sm.titles.cok.shop import I

SHEET, ITEMS, ACTION, WHO, COIN, NUMBER, CONFIRM = (k.value for k in (Kind.SHEET, Kind.ITEMS, Kind.ACTION, Kind.WHO, Kind.COIN, Kind.NUMBER, Kind.CONFIRM))
ACK = shop.Kind.ACK.value
SHOP_CONFIRM = shop.Kind.CONFIRM.value
EXIT = 'Exit'


def game_for(folder, root):
    seen, notes = [], []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if info.get('message'): notes.append(info['message'])
        if kind == ACK:
            notes.append(info['prompt'])
            return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        game.last_info, game.last_options = info, options
        if kind == NUMBER: game.prompts.append(info['prompt'])
        if kind == ITEMS and info.get('prompt') == 'Items': game.starts.append(info.get('start')); game.last_title = info.get('title')
        return answer if options is None else answer(options) if callable(answer) else options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    game.prompts, game.starts = [], []
    creation.load_game(game, 'A'); game.s.mode = 4
    for char in game.s.party: del char.effects[:]
    return game, seen, notes


def view(game, char, *rows):
    game.rows = iter(rows)
    inventory.view(game, char)


def named(text):
    return lambda options: max(i for i, o in enumerate(options) if text in o)


def act(text, action):
    return (SHEET, 'Items'), (ITEMS, named(text)), (ACTION, action), (ITEMS, EXIT), (SHEET, EXIT)


def clean(char):
    for item in char.items: item[I['readied']] = 0
    rules.recalc_stats(char)


def stocked(game, char, text):
    item = next(i for i in _shop_test.stock_of(game) if text in shop.item_name(game, i))
    item = bytearray(item); char.items.append(item)
    rules.recalc_stats(char)
    return item


def craft(char, kind, **fields):
    item = bytearray(Item.SIZE)
    item[I['type']] = kind; item[I['name_ids'] + 2] = kind
    for name, value in fields.items(): item[I[name]] = value
    char.items.append(item)
    rules.recalc_stats(char)
    return item


def ready_sword_shield(folder, root):
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; b = char.b
    clean(char)
    sword, shield = stocked(game, char, 'Long Sword'), stocked(game, char, 'Shield')
    table = rules.tables()
    sword_row, shield_row = table.base_item(sword[I['type']]), table.base_item(shield[I['type']])
    before = dict(ac=b[F['ac']], thac0=b[F['thac0']], hands=b[F['hands_used']], weight=shop.weight(char))
    view(game, char, *act('Long Sword', 'Ready'))
    assert (b[F['damage_rolls']], b[F['damage_dice']]) == (sword_row[rules.SMALL_ROLLS], sword_row[rules.SMALL_DICE]) and b[F['hands_used']] == sword_row[rules.HANDS]
    assert b[F['thac0']] == before['thac0'], 'an unenchanted sword adds what bare hands do: strength only'
    view(game, char, *act('Shield', 'Ready'))
    assert b[F['ac']] == before['ac'] + (shield_row[rules.ARMOR] & 0x7F) + shield[I['bonus']]
    assert b[F['hands_used']] == sword_row[rules.HANDS] + shield_row[rules.HANDS] and shop.weight(char) == before['weight']
    view(game, char, (SHEET, EXIT))
    assert game.last_info['ac_shown'] == 60 - b[F['ac']] and game.last_info['thac0_shown'] == 60 - b[F['thac0']]
    assert 'Yes  Long Sword' in game.last_info['items'] and game.last_info['encumbrance'] == shop.weight(char), game.last_info['items']
    return seen


def refusals(folder, root):
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; b = char.b
    clean(char)
    sword = stocked(game, char, 'Long Sword')
    view(game, char, *act('Long Sword', 'Ready'))
    table = rules.tables()
    usable = lambda kind: table.base_item(kind)[rules.USABLE_BY] & b[F['class_mask']]
    other = next(k for k in range(1, 100) if table.base_item(k)[rules.SLOT] == 0 and usable(k) and k != sword[I['type']])
    second = craft(char, other, cursed=0)
    notes.clear()
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: len(char.items) - 1), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert any(n.startswith('already using') for n in notes) and not second[I['readied']], notes
    wrong = next(k for k in range(1, 100) if table.base_item(k)[rules.SLOT] == 0 and not usable(k))
    forbidden = craft(char, wrong)
    notes.clear()
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: len(char.items) - 1), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert 'Wrong Class' in notes and not forbidden[I['readied']], notes
    clean(char)
    two = next(k for k in range(1, 100) if table.base_item(k)[rules.HANDS] == 2 and usable(k))
    shield = stocked(game, char, 'Shield')
    shield[I['readied']] = 1; rules.recalc_stats(char)
    big = craft(char, two)
    notes.clear()
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: len(char.items) - 1), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert 'Your hands are full!' in notes and not big[I['readied']], notes
    clean(char)
    sword[I['cursed']], sword[I['readied']] = 1, 1; rules.recalc_stats(char)
    notes.clear()
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: char.items.index(sword)), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert "It's Cursed" in notes and sword[I['readied']] == 1, notes
    return seen


def special(folder, root):
    game, seen, _ = game_for(folder, root)
    char = game.s.party[0]
    clean(char)
    table = rules.tables()
    kind = next(k for k in range(1, 100) if table.base_item(k)[rules.SLOT] == 0 and table.base_item(k)[rules.USABLE_BY] & char.b[F['class_mask']])
    item = craft(char, kind); item[I['powers']:I['powers'] + 3] = bytes((0, 77, 0x82))
    rules.recalc_stats(char)
    index = lambda o: char.items.index(item)
    view(game, char, (SHEET, 'Items'), (ITEMS, index), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert effects.has_effect(char, 77) is not None and item[I['readied']] == 1
    view(game, char, (SHEET, 'Items'), (ITEMS, index), (ACTION, 'Ready'), (ITEMS, EXIT), (SHEET, EXIT))
    assert effects.has_effect(char, 77) is None and item[I['readied']] == 0
    return seen


def trade_drop(folder, root):
    game, seen, notes = game_for(folder, root)
    giver, receiver = game.s.party[:2]
    clean(giver)
    item = stocked(game, giver, 'Long Sword'); weight = shop.word_at(item, I['weight'])
    a, b = shop.weight(giver), shop.weight(receiver)
    count = len(giver.items)
    view(game, giver, (SHEET, 'Items'), (ITEMS, named('Long Sword')), (ACTION, 'Trade'), (WHO, shop.member_name(receiver)), (ITEMS, EXIT), (SHEET, EXIT))
    assert len(giver.items) == count - 1 and shop.weight(giver) == a - weight and shop.weight(receiver) == b + weight
    assert any('Long Sword' in shop.item_name(game, i) for i in receiver.items)
    second = stocked(game, giver, 'Long Sword')
    shop.put_coins(receiver, [0, 0, 0, 0, 60000, 0, 0]); rules.recalc_stats(receiver)
    notes.clear()
    view(game, giver, (SHEET, 'Items'), (ITEMS, named('Long Sword')), (ACTION, 'Trade'), (WHO, shop.member_name(receiver)), (ITEMS, EXIT), (SHEET, EXIT))
    assert 'Overloaded' in notes and any(i is second for i in giver.items)
    view(game, giver, (SHEET, 'Items'), (ITEMS, named('Long Sword')), (ACTION, 'Drop'), (SHOP_CONFIRM, 'Yes'), (ITEMS, EXIT), (SHEET, EXIT))
    assert not any(i is second for i in giver.items) and len(giver.items) == count - 1
    return seen


def stacks(folder, root):
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; clean(char)
    arrows = craft(char, 30, quantity=21, weight=1)
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: char.items.index(arrows)), (ACTION, 'Halve'), (ITEMS, EXIT), (SHEET, EXIT))
    at = next(i for i, held in enumerate(char.items) if held is arrows)
    assert arrows[I['quantity']] == 11 and char.items[at + 1][I['quantity']] == 10
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: char.items.index(arrows)), (ACTION, 'Join'), (ITEMS, EXIT), (SHEET, EXIT))
    assert arrows[I['quantity']] == 21 and sum(i[I['type']] == 30 for i in char.items) == 1
    arrows[I['quantity']] = 250
    craft(char, 30, quantity=20, weight=1)
    inventory.join(game, char, arrows)
    amounts = sorted(i[I['quantity']] for i in char.items if i[I['type']] == 30)
    assert amounts == [15, 255], amounts
    single = craft(char, 31)
    notes.clear()
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: char.items.index(single)), (ACTION, 'Halve'), (ITEMS, EXIT), (SHEET, EXIT))
    assert "Can't halve that" in notes
    return seen


def coins(folder, root):
    game, seen, _ = game_for(folder, root)
    giver, receiver = game.s.party[:2]
    shop.put_coins(giver, [0, 0, 0, 0, 100, 0, 0]); shop.put_coins(receiver, [0, 0, 0, 0, 0, 0, 0])
    rules.recalc_stats(giver); rules.recalc_stats(receiver)
    view(game, giver, (SHEET, 'Trade'), (WHO, shop.member_name(receiver)), (COIN, named('Steel')), (NUMBER, 40), (COIN, EXIT), (WHO, EXIT), (SHEET, EXIT))
    assert shop.coins(giver)[4] == 60 and shop.coins(receiver)[4] == 40
    view(game, giver, (SHEET, 'Drop'), (COIN, named('Steel')), (NUMBER, 10), (COIN, EXIT), (SHEET, EXIT))
    assert shop.coins(giver)[4] == 50
    shop.put_coins(giver, [0, 7, 0, 3, 50, 2, 1]); rules.recalc_stats(giver)
    rows = []
    grab = lambda options: rows.append(list(options)) or len(options) - 1
    view(game, giver, (SHEET, 'Trade'), (WHO, shop.member_name(receiver)), (COIN, grab), (WHO, EXIT), (SHEET, EXIT))
    assert rows[-1] == ['Copper        7', 'Platinum      3', 'Steel         50', 'Gems          2', 'Jewelry       1', EXIT], rows[-1]
    view(game, giver, (SHEET, 'Drop'), (COIN, grab), (SHEET, EXIT))
    assert rows[-1] == ['Copper           7', 'Platinum         3', 'Steel           50', 'Gems             2', 'Jewelry          1', EXIT], rows[-1]
    view(game, giver, (SHEET, 'Trade'), (WHO, shop.member_name(receiver)), (COIN, named('Steel')), (NUMBER, 0), (COIN, named('Platinum')), (NUMBER, 0), (COIN, EXIT), (WHO, EXIT),
         (SHEET, 'Drop'), (COIN, named('Gems')), (NUMBER, 0), (COIN, EXIT), (SHEET, EXIT))
    assert game.prompts[-3:] == ['How much steel will you trade? ', 'How much platinum will you trade? ', 'How much Gems will you drop? '], game.prompts
    return seen


def item_list_place(folder, root):
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; clean(char)
    while len(char.items) < 4: craft(char, 1)
    last = len(char.items) - 1
    view(game, char, (SHEET, 'Items'), (ITEMS, lambda o: 2), (ACTION, 'Join'), (ITEMS, lambda o: last), (ACTION, 'Drop'), (SHOP_CONFIRM, 'Yes'), (ITEMS, EXIT), (SHEET, EXIT))
    assert game.starts == [0, 2, last - 1], game.starts
    assert game.last_title == shop.member_name(char) + "'s Items", game.last_title
    return seen


def combat_failed_use(folder, root):
    from sm.titles.cok import combat
    from sm.titles.cok._combat_test import spell_fixture, audit
    witnesses = []
    for readable in (True, False):
        game, b = spell_fixture(folder); c = b.chars[4]
        item = craft(c, 39 if readable else 41, readied=1)
        item[I['powers']:I['powers'] + 3] = bytes((15, 0, 0) if readable else (2, 65, 0)); item[I['name_ids']] = 100
        rules.recalc_stats(c)
        b.cast_item = lambda char, ident: False
        game.player = lambda kind, options, game, **info: 0
        b.record(4).update(initiative=5, item_ok=True)
        inventory.use_item(combat.EffectGame(b, 'inventory spell', 4), c, item)
        assert not b.record(4)['initiative'], 'the turn is over'
        assert not any(held is item for held in c.items) if readable else item[I['powers']] == 1, 'spent'
        witnesses.append(audit(game))
    return witnesses


def use(folder, root):
    game, seen, notes = game_for(folder, root)
    s = game.s; s.mode = 2
    kal = next(c for c in s.party if c.b[F['levels']] > 0)
    patient = next(c for c in s.party if c is not kal); patient.b[F['hp']] = 1
    name = shop.member_name(patient)
    from sm.titles.cok import camp
    scroll = craft(kal, 40, readied=1); scroll[I['powers']:I['powers'] + 3] = bytes((3, 0, 0)); scroll[I['name_ids']] = 100
    index = lambda it, ch: (lambda o: ch.items.index(it))
    view(game, kal, (SHEET, 'Items'), (ITEMS, index(scroll, kal)), (ACTION, 'Use'), (ITEMS, named('Cure Light')), (camp.Kind.WHO.value, name), (ITEMS, EXIT), (SHEET, EXIT))
    assert patient.b[F['hp']] > 1 and not any(i is scroll for i in kal.items), 'healed and the scroll is gone'
    hp = patient.b[F['hp']] = 1
    wand = craft(kal, 41, readied=1); wand[I['powers']:I['powers'] + 3] = bytes((2, 3, 0))
    view(game, kal, (SHEET, 'Items'), (ITEMS, index(wand, kal)), (ACTION, 'Use'), (camp.Kind.WHO.value, name), (ITEMS, EXIT), (SHEET, EXIT))
    assert patient.b[F['hp']] > hp and wand[I['powers']] == 1 and any(i is wand for i in kal.items)
    knight = s.party[0]
    paper = craft(knight, 39, readied=1); paper[I['powers']:I['powers'] + 3] = bytes((15, 0, 0)); paper[I['name_ids']] = 100
    notes.clear()
    view(game, knight, (SHEET, 'Items'), (ITEMS, index(paper, knight)), (ACTION, 'Use'), (ITEMS, named('Magic Missile')), (ITEMS, EXIT), (SHEET, EXIT))
    assert any(n.endswith('oops!') for n in notes) and any(i is paper for i in knight.items) and paper[I['powers']] == 15, notes
    return seen


def scroll_list(folder, root):
    game, seen, notes = game_for(folder, root)
    game.s.mode = 2
    kal = next(c for c in game.s.party if c.b[F['levels']] > 0)
    scroll = craft(kal, 40, readied=1); scroll[I['powers']:I['powers'] + 3] = bytes((3, 1, 0)); scroll[I['name_ids']] = 101
    game.rows = iter([(ITEMS, EXIT)])
    inventory.use_item(game, kal, scroll)
    assert game.last_info['prompt'] == 'Spells on Scroll' and game.last_info['start'] == 1, game.last_info
    return seen


def scroll_nothing_and_marks(folder, root):
    game, seen, notes = game_for(folder, root)
    game.s.mode = 2
    knight = game.s.party[0]
    hidden = craft(knight, 39, readied=1, unidentified=7); hidden[I['powers']:I['powers'] + 3] = bytes((15, 0, 0)); hidden[I['name_ids']] = 100
    empty = craft(knight, 39, readied=1); empty[I['name_ids']] = 100
    game.rows = iter([])
    inventory.use_item(game, knight, hidden); inventory.use_item(game, knight, empty)
    kal = next(c for c in game.s.party if c.b[F['levels']] > 0)
    marked = craft(kal, 40, readied=1); marked[I['powers']:I['powers'] + 3] = bytes((3 | 0x80, 1, 0)); marked[I['name_ids']] = 101
    labels = []
    game.rows = iter([(ITEMS, lambda options: labels.extend(options) or len(options) - 1)])
    inventory.use_item(game, kal, marked)
    from sm.titles.cok import rules as r
    assert not any(r.tables().base_item(k)[r.SLOT] == 12 for k in range(r.BASE_ITEMS))
    from sm.titles.cok import magic
    assert labels == [' *' + magic.spell(3).name, '  ' + magic.spell(1).name, EXIT], labels
    return seen


def combat_use(folder, root):
    from sm.titles.cok import combat, magic, town
    from sm.titles.cok._combat_test import spell_fixture, audit
    witnesses=[]
    for readable in (True,False):
        game,b=spell_fixture(folder); c=b.chars[4]
        item=craft(c,39 if readable else 41,readied=1)
        item[I['powers']:I['powers']+3]=bytes((15,0,0) if readable else (2,65,0))
        item[I['name_ids']]=100
        rules.recalc_stats(c)
        copies=bytes(c.b[F['memorized']:F['memorized']+58]); prompts=[]
        def player(kind, options, game, **info):
            prompts.append(kind)
            if kind==SHEET: return options.index('Items')
            if kind==ITEMS: return 0 if info.get('prompt')=='Spells on Scroll' else next(i for i,held in enumerate(c.items) if held is item)
            if kind==ACTION: return options.index('Use')
            if kind=='TARGET': return next(i for i,v in enumerate(options) if '#6' in v)
            return 0
        game.player=player; facade=combat.EffectGame(b,'inventory spell',4)
        inventory.view(facade,c)
        assert prompts.count(SHEET)==1 and prompts.count(ACTION)==1 and not b.record(4)['initiative']
        assert bytes(c.b[F['memorized']:F['memorized']+58])==copies
        assert not any(held is item for held in c.items) if readable else item[I['powers']]==1
        assert any(e['event']=='cast' and e['item'] for e in game.combat_log)
        assert town.field(b.chars[6],'hp')<9
        b.record(4).update(initiative=5,item_ok=True)
        assert inventory.can_use(facade,c)
        effects.add_effect(c,21,2,1,False); b.trigger(15,4)
        assert not inventory.can_use(facade,c) and 'Use' not in inventory.item_actions(facade,c,False)
        witnesses.append(audit(game))
    return witnesses


def spells_pending(folder, root):
    from sm.titles.cok import camp
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; base = camp.F['memorized']
    char.b[base:base + camp.MEMORY_SLOTS] = bytes(camp.MEMORY_SLOTS)
    view(game, char, (SHEET, lambda options: (options.index(EXIT), 'Spells' in options)[0]))
    assert 'Spells' not in game.last_options, game.last_options
    char.b[base + 2] = 11 | camp.PENDING
    view(game, char, (SHEET, 'Spells'), (SHEET, EXIT))
    assert next(game.rows, None) is None
    char.b[base + 5] = 11
    view(game, char, (SHEET, 'Spells'), (ITEMS, EXIT), (SHEET, EXIT))
    assert game.last_info.get('prompt') != 'Spells in Memory' and next(game.rows, None) is None
    return tuple(seen)


def sheet_checks(folder, root):
    from sm.titles.cok import camp
    game, seen, notes = game_for(folder, root)
    char = game.s.party[0]; b = char.b
    move = lambda: inventory.sheet(game, char)['move']
    base = move(); assert base
    effects.add_effect(char, effects.HASTED, 10, 0, False); assert move() == base * 2 & 255
    effects.add_effect(char, 42, 10, 0, False); assert move() == (base * 2 & 255) // 2
    del char.effects[0]; assert move() == base // 2
    del char.effects[:]
    def offered():
        view(game, char, (SHEET, EXIT)); return list(game.last_options)
    if not char.items: craft(char, 1)
    b[camp.F['memorized']] = 11; shop.put_coins(char, [0, 0, 0, 0, 0, 3, 0])
    assert offered() == ['Items', 'Spells', 'Trade', 'Drop', EXIT]
    b[F['npc']] = 0x80; assert offered() == ['Items', 'Spells', 'Drop', EXIT]
    b[F['active']] = 0; assert 'Trade' in offered()
    b[F['active']], b[F['status']] = 1, 1; assert 'Trade' in offered()
    b[F['npc']] = b[F['status']] = 0; game.s.mode = 5; assert offered() == ['Items', 'Spells', 'Drop', EXIT]
    game.s.mode = 4; shop.put_coins(char, [9, 0, 0, 0, 0, 0, 0]); assert offered() == ['Items', 'Spells', EXIT]
    return tuple(seen)


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-inv-') as first, tempfile.TemporaryDirectory(prefix='cok-inv-') as second:
        run = lambda root: tuple(check(folder, root) for check in (ready_sword_shield, refusals, special, trade_drop, stacks, coins, use, scroll_list, scroll_nothing_and_marks, combat_use, spells_pending, sheet_checks,
                                                              item_list_place, combat_failed_use))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS ready, refusals, specials, trade, drop, halve, join, coins; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
