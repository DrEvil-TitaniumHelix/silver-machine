from enum import Enum
from functools import lru_cache
import hashlib
import struct

from sm.files import DataError
from .creation import F, dice
from .records import Character, Item
from . import rules


class Kind(str, Enum):
    MENU = 'SHOP_MENU'
    WHO = 'WHO'
    LIST = 'LIST'
    NUMBER = 'NUMBER'
    CONFIRM = 'SHOP_CONFIRM'
    ACK = 'ACK'


I = {name: offset for name, (offset, _) in Item.FIELDS.items()}
STEEL, GEMS, JEWELRY, COIN_TYPES = 4, 5, 6, 7
SHOP_TEMPLE, ANIMATED, NON_PLAYER, POOLING_NPC, DETECT_MAGIC, MAX_ITEMS = 1, 1, 0x80, 0xB3, 5, 16
SCROLLS = (39, 40)
PRICE_CELL = 0x36D
PRICE_SCALE = {1: (1, 16), 2: (1, 8), 4: (1, 4), 8: (1, 2), 16: (1, 1), 32: (2, 1), 64: (4, 1), 128: (8, 1)}
NAME_PARTS = dict(offset=53253, size=2583, sha256='940cee9ee727e8029d82ae9dfe9a2185cfd9f46e3d3bdfebf0a2326fdcac106e')
COIN_NAMES = ('Silver', 'Copper', 'Bronze', 'Platinum', 'Steel', 'Gems', 'Jewelry')
TAKE_NAMES = ('silver ', 'Copper ', 'bronze ', 'platinum ', 'steel ', 'Gems ', 'Jewelry ')
LEFT_MONEY = 'As you Leave the Shopkeeper says, "Excuse me but you have Left Some Money here."  '
GEM_NAME, JEWEL_NAME, GEM_TYPE = 122, 123, 47
GEM_VALUES = ((25, 5), (50, 25), (70, 50), (90, 250), (99, 500), (100, 2500))
JEWEL_RANGES = ((10, 450, 50), (20, 500, 100), (40, 750, 150), (50, 1250, 250), (70, 2500, 500), (90, 3000, 1000), (100, 5000, 1000))


class Tables:
    def __init__(self, assets):
        raw = assets.resident[NAME_PARTS['offset']:NAME_PARTS['offset'] + NAME_PARTS['size']]
        if hashlib.sha256(raw).hexdigest() != NAME_PARTS['sha256']:
            raise DataError('Champions item-name table differs')
        self.parts = tuple(raw[i + 1:i + 1 + raw[i]].decode('cp437') for i in range(0, len(raw), 21))
        self.coin_value = assets.table('coinValue')


@lru_cache(maxsize=4)
def tables(assets):
    return Tables(assets)


def word_at(data, offset):
    return data[offset] | data[offset + 1] << 8


def put_word(data, offset, value):
    data[offset], data[offset + 1] = value & 255, value >> 8 & 255


def coins(char):
    return list(struct.unpack_from('<7H', char.b, F['money']))


def put_coins(char, values):
    struct.pack_into('<7H', char.b, F['money'], *(v & 0xFFFF for v in values))


def member_name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def note(game, text):
    game.shop_note = text


def pick(game, kind, prompt, labels, exit_label='Exit', **info):
    answer = game.ask(kind.value, tuple(labels) + (exit_label,), prompt=prompt, message=getattr(game, 'shop_note', ''), **info)
    game.shop_note = ''
    return None if answer == len(labels) else answer


def deal(game, prompt, offer=''):
    return game.ask(Kind.CONFIRM.value, ('Yes', 'No'), prompt=prompt, offer=offer) == 0


def pause(game, text, **info):
    game.ask(Kind.ACK.value, ('Continue',), prompt=text, **info)


def item_name(game, item, inventory=False):
    s, t = game.s, tables(game.assets)
    kind, quantity, ids, unknown = item[I['type']], item[I['quantity']], item[I['name_ids']:I['name_ids'] + 3], item[I['unidentified']]
    text = (' Yes  ' if item[I['readied']] else ' No   ') if inventory else ''
    if any(e[0] == DETECT_MAGIC for c in s.party for e in c.effects) and (item[I['bonus']] < 128 and item[I['bonus']] > 0 or 0 < item[I['save_bonus']] < 128 or item[I['cursed']]):
        text += '* '
    if quantity: text += '%d ' % quantity
    mask = sum(1 << (n - 1) for n in range(1, 4) if ids[n - 1] and not unknown >> (3 - n) & 1)
    plural = False
    for n in (3, 2, 1):
        if not mask >> (n - 1) & 1: continue
        text += t.parts[ids[n - 1] - 1]
        if quantity < 2 or plural: text += ' '
        elif (1 << (n - 1) == mask or n == 1 and mask > 4 and kind != 55 or n == 2 and not mask & 1 or n == 3 and kind == 55 or
              kind in (30, 5, 12) and ids[2] != 93):
            text += 's '; plural = True
        else: text += ' '
    raw = text[:40].encode('cp437')
    item[I['name']] = len(raw)
    item[I['name'] + 1:I['name'] + 1 + len(raw)] = raw
    return text


def coin_value(game, money):
    value = tables(game.assets).coin_value
    return sum(value[i] * money[i] for i in range(5)) // value[STEEL]


def carrying_capacity(char):
    return (rules._carry_allowance(rules._view(Character, char.b)) + 1500) & 0xFFFF


def weight(char):
    return word_at(char.b, F['weight'])


def add_weight(char, amount):
    put_word(char.b, F['weight'], (weight(char) + amount) & 0xFFFF)


def check_overload(char, amount):
    capacity = carrying_capacity(char)
    if weight(char) + amount > capacity:
        return True, 0 if weight(char) > capacity else capacity - weight(char)
    return False, 0


def cannot_carry(char, item):
    rules.recalc_stats(char)
    amount = word_at(item, I['weight'])
    if item[I['quantity']]: amount = amount * item[I['quantity']] & 0xFFFF
    return char.b[F['item_count']] > 15 or weight(char) + amount > carrying_capacity(char)


def give_item_copy(game, char, item):
    if cannot_carry(char, item):
        note(game, 'OverLoaded')
        return False
    copy = bytearray(item)
    copy[I['next_pointer']:I['next_pointer'] + 4] = bytes(4)
    char.items.append(copy)
    rules.recalc_stats(char)
    return True


def set_creature_steel(char, steel):
    put_coins(char, [0, 0, 0, 0, steel] + coins(char)[GEMS:])


def set_pool_steel(s, steel):
    s.treasure_money[:5] = [0, 0, 0, 0, steel & 0xFFFF]


def price_of(s, item):
    value = word_at(item, I['value'])
    if not value:
        value = 1
        put_word(item, I['value'], 1)
    multiply, divide = PRICE_SCALE.get(s.r1[PRICE_CELL], (1, 1))
    return (value * multiply & 0xFFFF) // divide


def buy_label(game, item):
    price = str(price_of(game.s, item))
    line = list(' ' * (30 - len(price)) + price)
    for at, ch in enumerate(item_name(game, item)[:30]): line[at] = ch
    return ''.join(line)


def buy_menu(game, char):
    s = game.s
    while True:
        labels = [buy_label(game, item) for item in s.treasure_items]
        index = pick(game, Kind.LIST, 'Items: ', labels, purpose='buy', window='1 1 38 22', query='Items: ', menu='Buy')
        if index is None: return
        item, price = s.treasure_items[index], price_of(s, s.treasure_items[index])
        name = item_name(game, item)
        bought = member_name(char) + (' buys ' if item[I['quantity']] else ' buys a ') + name
        own = coin_value(game, coins(char)) & 0xFFFF
        if price <= own:
            if give_item_copy(game, char, item):
                set_creature_steel(char, own - price)
                note(game, bought)
        else:
            pooled = coin_value(game, s.treasure_money)
            if price <= pooled:
                if give_item_copy(game, char, item):
                    set_pool_steel(s, pooled - price)
                    note(game, bought)
            else: note(game, 'Not enough Money.')


def poolers(s):
    return [c for c in s.party if c.b[F['npc']] in (0, POOLING_NPC)]


def pool_money(s):
    for char in poolers(s):
        money = coins(char)
        for i in range(COIN_TYPES):
            s.treasure_money[i] += money[i]
            add_weight(char, -money[i])
        put_coins(char, [0] * COIN_TYPES)


def share_money(s):
    count, party = len(poolers(s)), s.party
    share = [(v // count) & 0xFFFF for v in s.treasure_money]
    rest = [(v % count) & 0xFFFF for v in s.treasure_money]
    for char in party:
        if char.b[F['npc']] < NON_PLAYER:
            money = coins(char)
            for i in range(6, -1, -1):
                over, takable = check_overload(char, share[i])
                if over:
                    money[i] += takable; rest[i] += share[i] - takable; add_weight(char, takable)
                else:
                    money[i] += share[i]; add_weight(char, share[i])
                    if rest[i] and not check_overload(char, 1)[0]:
                        money[i] += 1; add_weight(char, 1); rest[i] -= 1
            put_coins(char, money)
    for i in range(6, -1, -1):
        for char in party:
            if not rest[i]: break
            takable = (carrying_capacity(char) - weight(char)) & 0xFFFF
            if takable:
                amount = min(rest[i], takable)
                money = coins(char); money[i] += amount; put_coins(char, money)
                add_weight(char, amount); rest[i] -= amount
    s.treasure_money[:] = rest


def take_menu(game, char):
    s = game.s
    while any(v > 0 for v in s.treasure_money):
        kinds = [i for i in range(COIN_TYPES - 1, -1, -1) if s.treasure_money[i] > 0]
        index = pick(game, Kind.LIST, 'Select type of coin ', ['%s %d' % (COIN_NAMES[i], s.treasure_money[i]) for i in kinds], purpose='take')
        if index is None: return
        kind, limit = kinds[index], s.treasure_money[kinds[index]] & 0xFFFF
        amount = game.ask(Kind.NUMBER.value, None, prompt=('How Many ' if kind == GEMS else 'How much ') + TAKE_NAMES[kind] + ' will you take? ', max=limit)
        amount = min(amount, limit)
        if check_overload(char, amount)[0]: pause(game, 'Overloaded')
        else:
            s.treasure_money[kind] -= amount
            money = coins(char); money[kind] += amount; put_coins(char, money)
            add_weight(char, amount)


def give_steel(game, char, amount):
    over, takable = check_overload(char, amount)
    if over:
        pause(game, 'Overloaded.  Money will be put in Pool.')
        amount, game.s.treasure_money[STEEL] = takable, amount + game.s.treasure_money[STEEL] - takable
    money = coins(char); money[STEEL] += amount; put_coins(char, money)
    add_weight(char, amount)


def appraise_one(game, char, name_id, value):
    must_sell = check_overload(char, 1)[0] or char.b[F['item_count']] >= MAX_ITEMS
    label = 'The Gem' if name_id == GEM_NAME else 'The Jewel'
    index = game.ask(Kind.LIST.value, ('Sell',) if must_sell else ('Sell', 'Keep'), prompt=label + ' is Valued at %d steel.' % value,
                     message=getattr(game, 'shop_note', '')); game.shop_note = ''
    if index == 1:
        gem = bytearray(Item.SIZE)
        gem[I['name_ids'] + 2], gem[I['type']], gem[I['weight']] = name_id, GEM_TYPE, 1
        put_word(gem, I['value'], value)
        if char.items: char.items.append(gem)
    else: give_steel(game, char, value)


def appraise(game, char):
    s = game.s
    if not coins(char)[GEMS] and not coins(char)[JEWELRY]:
        note(game, 'No Gems or Jewelry')
        return
    while coins(char)[GEMS] or coins(char)[JEWELRY]:
        money = coins(char)
        options = [label for label, count in (('Gems', money[GEMS]), ('Jewelry', money[JEWELRY])) if count]
        index = pick(game, Kind.LIST, 'Appraise : ', options, gems=money[GEMS], jewelry=money[JEWELRY])
        if index is None: return
        if options[index] == 'Gems':
            money[GEMS] -= 1; put_coins(char, money)
            roll = dice(s, 1, 100)
            appraise_one(game, char, GEM_NAME, next(v for top, v in GEM_VALUES if roll <= top))
        else:
            money[JEWELRY] -= 1; put_coins(char, money)
            roll = dice(s, 1, 100)
            span, base = next((span, base) for top, span, base in JEWEL_RANGES if roll <= top)
            appraise_one(game, char, JEWEL_NAME, s.random(span) + base)
        rules.recalc_stats(char)


def item_available(game, char, item):
    if item[I['readied']]:
        note(game, 'Must be unreadied')
        return False
    if item[I['type']] in SCROLLS and any(v > 0x7F for v in item[I['powers']:I['powers'] + 3]):
        return deal(game, 'is it Okay to lose it? ', member_name(char) + ' was going to scribe from that scroll')
    return True


def sell(game, char, item):
    value = word_at(item, I['value'])
    price = value // 2 if value else 0
    if item[I['quantity']] > 1: price = (price * item[I['quantity']] & 0xFFFF) // 20
    offer = "I'll give you %d steel pieces for your %s" % (price, item_name(game, item))
    if not deal(game, 'Is It a Deal? ', offer): return
    note(game, 'Sold!')
    char.items.remove(item)
    over, takable = check_overload(char, price)
    money = coins(char)
    if over:
        pause(game, 'Sold!')
        note(game, 'Overloaded.  Money will be put in pool.')
        money[STEEL] += takable
        game.s.treasure_money[STEEL] += price - takable
    else: money[STEEL] += price
    put_coins(char, money)


def identify(game, char, item):
    if not deal(game, 'Is It a Deal? ', "For 100 steel pieces I'll identify your " + item_name(game, item)): return
    s, own = game.s, coin_value(game, coins(char))
    if own >= 100: set_creature_steel(char, own - 100)
    else:
        pooled = coin_value(game, s.treasure_money)
        if pooled < 100:
            note(game, 'Not Enough Money')
            return
        set_pool_steel(s, pooled - 100)
    if item[I['unidentified']] & 7:
        item[I['unidentified']] &= 0xF8
        pause(game, 'It looks like some sort of ' + item_name(game, item))
    else: pause(game, "I can't tell anything new about your " + item_name(game, item))


def view_items(game, char):
    from . import inventory
    inventory.view(game, char)


def has_money(s):
    return any(s.treasure_money)


MEMBER_KEYS = ('char-up', 'char-down')


def main_menu(game, options, kind=Kind.MENU):
    s = game.s
    while True:
        answer = game.ask(kind.value, tuple(options) + ('Exit',) + MEMBER_KEYS, prompt='', member=member_name(s.party[s.sel]),
                          message=getattr(game, 'shop_note', ''))
        game.shop_note = ''
        if answer < len(options): return answer
        if answer == len(options): return None
        s.sel = (s.sel + (-1 if answer == len(options) + 1 else 1)) % len(s.party)


def run(game, shop_id=None):
    s = game.s
    mode, s.mode = s.mode, SHOP_TEMPLE
    s.treasure_money[:] = [0] * COIN_TYPES
    for item in s.treasure_items: item_name(game, item)
    try:
        while True:
            options = ('Buy', 'View', 'Take', 'Pool', 'Share', 'Appraise') if has_money(s) else ('Buy', 'View', 'Pool', 'Appraise')
            index = main_menu(game, options)
            if index is None:
                if not has_money(s) or not deal(game, 'Do you want to go back and get your Money?', LEFT_MONEY): return
                continue
            action = options[index]
            if action == 'Pool': pool_money(s)
            elif action == 'Share': share_money(s)
            else:
                char = s.party[s.sel]
                if action == 'Buy': buy_menu(game, char)
                elif action == 'View': view_items(game, char)
                elif action == 'Take': take_menu(game, char)
                else: appraise(game, char)
    finally:
        s.mode = mode
