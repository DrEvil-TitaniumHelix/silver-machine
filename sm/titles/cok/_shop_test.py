import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm import ecl
from sm.titles.cok import creation, rules, shop
from sm.titles.cok.creation import F
from sm.titles.cok.menu import Game
from sm.titles.cok.shop import I, Kind

MENU, WHO, LIST, NUMBER, CONFIRM, ACK = (k.value for k in (Kind.MENU, Kind.WHO, Kind.LIST, Kind.NUMBER, Kind.CONFIRM, Kind.ACK))
EXIT = 'Exit'
SHEET, ITEMS, ACTION = 'CREATE_VIEW', 'VIEW_ITEMS', 'VIEW_ACTION'
TREASURE_OP, OUTPOST = 0x27, (1, 17)


def armoury_record(assets):
    _, instructions = ecl.trace(assets.scripts()[OUTPOST])
    ids = [operands[7][1] for op, operands, _ in instructions.values() if op == TREASURE_OP and operands[7][1] < 0x80]
    assert len(ids) == 1, ids
    return ids[0]


def stock_of(game):
    raw = game.assets.records('ITEM1')[armoury_record(game.assets)]
    assert len(raw) % 63 == 0
    return [bytearray(raw[i:i + 63]) for i in range(len(raw) - 63, -1, -63)]


def contains(text):
    return lambda options: next(i for i, o in enumerate(options) if text in o)


def last_containing(text):
    return lambda options: max(i for i, o in enumerate(options) if text in o)


def shop_game(folder, root):
    seen, notes = [], []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if info.get('message'): notes.append(info['message'])
        if info.get('offer'): notes.append(info['offer'])
        if kind == NUMBER: notes.append(info['prompt'])
        if kind == ACK:
            notes.append(info['prompt'])
            return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        return answer(options) if callable(answer) else options.index(answer) if options is not None else answer
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    game.s.treasure_items = stock_of(game); game.s.sel = 0
    game.s.r1[shop.PRICE_CELL] = 16
    return game, seen, notes


def play(game, *rows):
    game.rows = iter(rows)
    shop.run(game)


def steel(char):
    return shop.coins(char)[shop.STEEL]


def set_steel(char, amount):
    shop.put_coins(char, [0, 0, 0, 0, amount, 0, 0])
    rules.recalc_stats(char)


def stock_check(folder, root):
    game, _, _ = shop_game(folder, root)
    stock, s = game.s.treasure_items, game.s
    raw = game.assets.records('ITEM1')[armoury_record(game.assets)]
    assert len(stock) == len(raw) // 63 and stock[-1] == bytearray(raw[:63])
    for item in stock:
        value = shop.word_at(item, I['value'])
        assert shop.price_of(s, item) == (value or 1)
        assert shop.buy_label(game, item).endswith(str(value or 1))
    names = [shop.item_name(game, item) for item in stock]
    assert any('Long Sword' in n for n in names), names
    item = next(i for i in stock if shop.word_at(i, I['value']) >= 16)
    value = shop.word_at(item, I['value'])
    for level, price in ((1, value // 16), (8, value // 2), (32, value * 2 & 0xFFFF), (128, value * 8 & 0xFFFF), (3, value)):
        s.r1[shop.PRICE_CELL] = level
        assert shop.price_of(s, item) == price, (level, price)


def buy_sell(folder, root):
    first = lambda options: 0
    game, seen, notes = shop_game(folder, root)
    char = game.s.party[0]
    set_steel(char, 1000)
    items, before_weight = len(char.items), shop.weight(char)
    sword = next(i for i in game.s.treasure_items if 'Long Sword' in shop.item_name(game, i))
    price, weight = shop.word_at(sword, I['value']), shop.word_at(sword, I['weight'])
    play(game, (MENU, 'Buy'), (LIST, contains('Long Sword')), (LIST, EXIT), (MENU, EXIT))
    assert steel(char) == 1000 - price and len(char.items) == items + 1
    assert char.items[-1][I['type']] == sword[I['type']] and shop.weight(char) == before_weight + weight, (shop.weight(char), before_weight, weight)
    assert any(' buys a ' in n and 'Long Sword' in n for n in notes), notes
    held = steel(char)
    play(game, (MENU, 'View'), (SHEET, 'Items'), (ITEMS, last_containing('Long Sword')), (ACTION, 'Sell'), (CONFIRM, 'Yes'), (ITEMS, EXIT), (SHEET, EXIT), (MENU, EXIT))
    assert steel(char) == held + price // 2 and len(char.items) == items
    assert 'Sold!' in notes
    char.items.append(bytearray(sword)); set_steel(char, 60000); rules.recalc_stats(char); notes.clear()
    play(game, (MENU, 'View'), (SHEET, 'Items'), (ITEMS, last_containing('Long Sword')), (ACTION, 'Sell'), (CONFIRM, 'Yes'), (ITEMS, EXIT), (SHEET, EXIT), (MENU, EXIT), (CONFIRM, 'No'))
    said = [n for n in notes if n in ('Sold!', 'Overloaded.  Money will be put in pool.')]
    assert said == ['Sold!', 'Overloaded.  Money will be put in pool.'] and game.s.treasure_money[shop.STEEL] == price // 2, (notes, game.s.treasure_money)
    return seen


def pool_share(folder, root):
    game, seen, _ = shop_game(folder, root)
    s = game.s
    assert all(c.b[F['npc']] == 0 for c in s.party)
    amounts = [103, 1, 0, 0, 7, 0]
    for char, amount in zip(s.party, amounts):
        shop.put_coins(char, [0, 3, 0, 0, amount, 0, 0])
        rules.recalc_stats(char)
    play(game, (MENU, 'Pool'), (MENU, 'Share'), (MENU, EXIT))
    total, count = sum(amounts), len(s.party)
    got = [steel(c) for c in s.party]
    share, left = total // count, total % count
    assert got == [share + (i < left) for i in range(count)], got
    assert sum(got) == total and not shop.has_money(s)
    assert [shop.coins(c)[1] for c in s.party] == [3] * count
    return seen


def refusals(folder, root):
    first = lambda options: 0
    game, seen, notes = shop_game(folder, root)
    char = game.s.party[0]
    items = len(char.items)
    attempt = ((MENU, 'Buy'), (LIST, contains('Long Sword')), (LIST, EXIT), (MENU, EXIT))
    set_steel(char, 0)
    play(game, *attempt)
    assert 'Not enough Money.' in notes and len(char.items) == items and steel(char) == 0
    play(game, (MENU, 'View'), (SHEET, 'Items'), (ITEMS, contains('Long Sword')), (ACTION, 'Sell'), (ITEMS, EXIT), (SHEET, EXIT), (MENU, EXIT))
    assert 'Must be unreadied' in notes and len(char.items) == items
    notes.clear()
    set_steel(char, 5000)
    play(game, *attempt)
    assert 'OverLoaded' in notes and len(char.items) == items and steel(char) == 5000, notes
    return seen


def money_words(folder, root):
    first = lambda options: 0
    game, seen, notes = shop_game(folder, root)
    s = game.s
    shop.set_pool_steel(s, 70000)
    assert s.treasure_money[shop.STEEL] == 70000 & 0xFFFF
    s.treasure_money[:] = [0] * shop.COIN_TYPES
    shop.put_coins(s.party[0], [0, 0, 0, 0, 30, 2, 0]); rules.recalc_stats(s.party[0])
    play(game, (MENU, 'Pool'), (MENU, 'Take'), (LIST, contains('Steel')), (NUMBER, 0), (LIST, contains('Gems')), (NUMBER, 0), (LIST, EXIT),
         (MENU, EXIT), (CONFIRM, 'Yes'), (MENU, 'Share'), (MENU, EXIT))
    assert 'As you Leave the Shopkeeper says, "Excuse me but you have Left Some Money here."  ' in notes, notes
    return seen


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-shop-') as first, tempfile.TemporaryDirectory(prefix='cok-shop-') as second:
        stock_check(folder, first)
        run = lambda root: (buy_sell(folder, root), pool_share(folder, root), refusals(folder, root), money_words(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS stock, buy, sell, pool, share, refusals; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
