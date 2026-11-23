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
COIN_NAMES = ('Silver', 'Copper', 'Bronze', 'Platinum', 'Steel', 'Gems', 'Jewelry')
GEM_NAME, JEWEL_NAME, GEM_TYPE = 122, 123, 47
GEM_VALUES = ((25, 5), (50, 25), (70, 50), (90, 250), (99, 500), (100, 2500))
JEWEL_RANGES = ((10, 450, 50), (20, 500, 100), (40, 750, 150), (50, 1250, 250), (70, 2500, 500), (90, 3000, 1000), (100, 5000, 1000))


class Tables:
    def __init__(self, assets):
        self.parts = assets.names('itemNameParts')


@lru_cache(maxsize=4)
def tables(assets):
    return Tables(assets)


def word_at(data, offset):
    return data[offset] | data[offset + 1] << 8


def put_word(data, offset, value):
    data[offset], data[offset + 1] = value & 255, value >> 8 & 255


def coins(char):
    return [0] * 4 + list(struct.unpack_from('<3H', char.b, F['money']))


def put_coins(char, values):
    struct.pack_into('<3H', char.b, F['money'], *(v & 0xFFFF for v in values[4:]))


def member_name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def note(game, text):
    game.shop_note = text


def horizontal(game, kind, options, **info):
    start = info.get('start', getattr(game, 'menu_highlight', 0))
    count = sum(label not in ('char-up', 'char-down') for label in options)
    info['start'] = start if 0 <= start < count else 0
    if hasattr(game, 'menu_highlight'): del game.menu_highlight
    answer = game.ask(kind, options, **info)
    game.menu_highlight = getattr(game, 'menu_highlight', answer if answer < count else info['start'])
    return answer


def pick(game, kind, prompt, labels, exit_label='Exit', **info):
    answer = game.ask(kind.value, tuple(labels) + (exit_label,), prompt=prompt, message=getattr(game, 'shop_note', ''), **info)
    game.shop_note = ''
    return None if answer == len(labels) else answer


def deal(game, prompt, offer='', start=0, **info):
    return game.ask(Kind.CONFIRM.value, ('Yes', 'No'), prompt=prompt, offer=offer, start=start, **info) == 0


def pause(game, text, **info):
    game.ask(Kind.ACK.value, ('Continue',), prompt=text, **info)


def overload_notice(game, text):
    pause(game, text, timed=1, message_colour=10, blank_bottom_pause=True, flush_keys=True)


def item_name(game, item, inventory=False):
    s, t = game.s, tables(game.assets)
    kind, quantity, ids, unknown = item[I['type']], item[I['quantity']], item[I['name_ids']:I['name_ids'] + 3], item[I['unidentified']]
    text = game.assets.text('equippedText' if item[I['readied']] else 'unequippedText') if inventory else ''
    if any(e[0] == DETECT_MAGIC for c in s.chars() for e in c.effects) and (item[I['bonus']] < 128 and item[I['bonus']] > 0 or 0 < item[I['save_bonus']] < 128 or item[I['cursed']]):
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
    return money[STEEL]


def carrying_capacity(char):
    return (rules._carry_allowance(rules._view(Character, char.b)) + 1500) & 0xFFFF


def weight(char):
    return word_at(char.b, F['weight'])


def add_weight(char, amount):
    put_word(char.b, F['weight'], (weight(char) + amount) & 0xFFFF)


def check_overload(char, amount):
    capacity = carrying_capacity(char)
    if (weight(char) + amount) & 0xFFFF > capacity:
        return True, 0 if weight(char) > capacity else capacity - weight(char)
    return False, 0


def stack_match(first, second):
    spans = (('name_ids', 3), ('type', 1), ('bonus', 1), ('save_bonus', 1), ('cursed', 1), ('weight', 2), ('powers', 3))
    return first[I['powers']] < 2 and all(first[I[key]:I[key] + size] == second[I[key]:I[key] + size] for key, size in spans)


def cannot_carry(char, item, may_stack=False, game=None):
    rules.recalc_stats(char, game.s.r1[0x372] if game is not None else 0)
    duplicate = may_stack and item[I['quantity']] > 0 and any(stack_match(held, item) for held in char.items)
    amount = word_at(item, I['weight'])
    if item[I['quantity']]: amount = amount * item[I['quantity']] & 0xFFFF
    return char.b[F['item_count']] > 15 and not duplicate or weight(char) + amount > carrying_capacity(char)


def detached_item(game, char, item):
    from . import inventory
    copy = inventory.copy_item(game, char, item)
    if copy is not None:
        offset = I['next_pointer']
        copy[offset:offset + 4] = bytes(4)
    return copy


def give_item_copy(game, char, item):
    if cannot_carry(char, item, may_stack=True, game=game):
        note(game, game.assets.text('tradeOverloadMessage'))
        return False
    copy = detached_item(game, char, item)
    if copy is None: return False
    char.items.append(copy)
    if item[I['quantity']]:
        from .inventory import join
        join(game, char, copy)
    rules.recalc_stats(char, game.s.r1[0x372])
    return True


def set_creature_steel(char, steel):
    put_coins(char, [0, 0, 0, 0, steel] + coins(char)[GEMS:])


def set_pool_steel(s, steel):
    s.treasure_money[:5] = [0, 0, 0, 0, steel]


def price_of(s, item):
    value = word_at(item, I['value'])
    if not value:
        value = 1
        put_word(item, I['value'], 1)
    multiply, divide = PRICE_SCALE.get(s.r1[PRICE_CELL], (1, 1))
    price = (value * multiply & 0xFFFF) // divide
    if item[I['quantity']] > 1: price = price * item[I['quantity']] & 65535
    return max(1, price)


def buy_label(game, item):
    price = str(price_of(game.s, item))
    line = list(' ' * (30 - len(price)) + price)
    for at, ch in enumerate(item_name(game, item)[:30]): line[at] = ch
    item[I['name']:I['name'] + 31] = bytes((30,)) + ''.join(line).encode('cp437')
    return ''.join(line)


def buy_menu(game, char):
    s = game.s
    selected = 0
    while True:
        labels = [buy_label(game, item) for item in s.treasure_items]
        money_lines = (game.assets.text('goldLabel') + str(coins(char)[STEEL]).rjust(10),
                       game.assets.text('poolLabel') + str(s.treasure_money[STEEL]).rjust(10))
        index = pick(game, Kind.LIST, game.assets.text('itemsQuery'), labels, purpose='buy', start=selected,
                     window='1 1 38 18', menu=game.assets.text('buyMenu'), money_lines=money_lines,
                     money_column=1, money_rows=(20, 21), member=member_name(char))
        for item in s.treasure_items: item_name(game, item)
        if index is None: return
        selected = index
        item, price = s.treasure_items[index], price_of(s, s.treasure_items[index])
        name = item_name(game, item)
        bought = member_name(char) + game.assets.text('buysText' if item[I['quantity']] else 'buysAText') + name
        own = coin_value(game, coins(char)) & 0xFFFF
        if price <= own:
            if give_item_copy(game, char, item):
                set_creature_steel(char, own - price)
                note(game, bought)
        else:
            pooled = coin_value(game, s.treasure_money)
            if price <= own + pooled:
                if give_item_copy(game, char, item):
                    set_creature_steel(char, 0)
                    s.treasure_money[STEEL] = pooled - (price - own)
                    note(game, bought)
            else: note(game, game.assets.text('notEnoughMoneyText'))


def poolers(s):
    return [c for c in s.chars() if c.b[F['npc']] in (0, POOLING_NPC)]


def change_pool(s, kind, amount):
    s.treasure_money[kind] = (s.treasure_money[kind] + amount + 0x80000000 & 0xFFFFFFFF) - 0x80000000


def pool_money(s):
    s.g['treasure_active'] = 1
    for char in poolers(s):
        money = coins(char)
        for i in range(STEEL, COIN_TYPES):
            change_pool(s, i, money[i])
            add_weight(char, -money[i])
        put_coins(char, [0] * COIN_TYPES)


def share_money(s):
    count, party = len(poolers(s)) & 255, s.chars()
    share, rest = [0] * COIN_TYPES, [0] * COIN_TYPES
    for i in range(STEEL, COIN_TYPES):
        value = s.treasure_money[i]
        if value > 0: share[i], rest[i] = value // count & 0xFFFF, value % count & 0xFFFF
    for char in party:
        if char.b[F['npc']] < NON_PLAYER:
            money = coins(char)
            for i in range(JEWELRY, STEEL - 1, -1):
                over, takable = check_overload(char, share[i])
                if over:
                    money[i] += takable; rest[i] = rest[i] + share[i] - takable & 0xFFFF; add_weight(char, takable)
                else:
                    money[i] += share[i]; add_weight(char, share[i])
                    if rest[i] and not check_overload(char, 1)[0]:
                        money[i] += 1; add_weight(char, 1); rest[i] -= 1
            put_coins(char, money)
    for i in range(JEWELRY, STEEL - 1, -1):
        for char in party:
            if not rest[i]: break
            takable = (carrying_capacity(char) - weight(char)) & 0xFFFF
            if takable:
                amount = min(rest[i], takable)
                money = coins(char); money[i] += amount; put_coins(char, money)
                add_weight(char, amount); rest[i] -= amount
    s.treasure_money[STEEL:] = rest[STEEL:]
    s.g['treasure_active'] = int(any(rest[STEEL:]))


def input_number(game, maximum, query):
    maximum &= 0xFFFF
    value = game.ask(Kind.NUMBER.value, None, prompt=query[:40], max=maximum, colour=10,
                     purpose='money', number_colour=15, number_column=len(query[:40]))
    return min(max(0, value), maximum)


def take_money(game, char, amount, kind):
    amount &= 0xFFFF
    if check_overload(char, amount)[0]:
        overload_notice(game, game.assets.text('tradeOverloadMessage'))
        return
    amount = min(amount, game.s.treasure_money[kind]) & 0xFFFF
    change_pool(game.s, kind, -amount)
    money = coins(char); money[kind] += amount; put_coins(char, money)
    add_weight(char, amount)


def take_menu(game, char):
    s = game.s
    names = game.assets.names('moneyNames')
    selected = 0
    while True:
        kinds = [i for i in range(JEWELRY, STEEL - 1, -1) if s.treasure_money[i] > 0]
        selected = min(selected, max(0, len(kinds) - 1))
        index = pick(game, Kind.LIST, game.assets.text('selectCoinQuery'),
                     [names[i] + ' ' + str(s.treasure_money[i]) for i in kinds], purpose='take',
                     window='2 2 15 8', menu=game.assets.text('selectMenuText'), start=selected)
        if index is None: return
        selected = index
        kind = kinds[index]
        query = game.assets.text('howMany' if kind == GEMS else 'howMuch') + names[kind] + ' ' + game.assets.text('takePromptTail')
        take_money(game, char, input_number(game, s.treasure_money[kind], query), kind)
        s.g['treasure_active'] = int(any(v > 0 for v in s.treasure_money[STEEL:]))
        if not s.g['treasure_active']: return


def give_steel(game, char, amount):
    amount &= 0xFFFF
    over, takable = check_overload(char, amount)
    if over:
        overload_notice(game, game.assets.text('overloadPoolText'))
        change_pool(game.s, STEEL, amount - takable)
        amount = takable
    money = coins(char); money[STEEL] += amount; put_coins(char, money)
    add_weight(char, amount)


def appraise_one(game, char, name_id, value, selected=0):
    must_sell = check_overload(char, 1)[0] or char.b[F['item_count']] >= MAX_ITEMS
    line = game.assets.text('gemValuePrefix' if name_id == GEM_NAME else 'jewelValuePrefix') + str(value) + game.assets.text('goldValueSuffix')
    index = horizontal(game, Kind.MENU.value, ('Sell',) if must_sell else ('Sell', 'Keep'), prompt='', purpose='appraise-value',
                     value_line=line, value_column=1, value_row=12, menu=game.assets.text('sellMenu'),
                     menu_labels=('Sell', 'Keep'), enabled=(0,) if must_sell else (0, 1), horizontal=True,
                     escape_choice=0, start=selected if not must_sell and selected < 2 else 0,
                     message=getattr(game, 'shop_note', ''))
    game.shop_note = ''
    if index == 1 and not must_sell:
        gem = bytearray(Item.SIZE)
        gem[I['name_ids'] + 2], gem[I['type']], gem[I['weight']] = name_id, GEM_TYPE, 1
        put_word(gem, I['value'], value)
        kept = detached_item(game, char, gem)
        if kept is None: return None
        if char.items: char.items.append(kept)
    else: give_steel(game, char, value)
    return game.menu_highlight


def appraise(game, char):
    s = game.s
    if not coins(char)[GEMS] and not coins(char)[JEWELRY]:
        pause(game, game.assets.text('noGemsMessage'), timed=1, message_colour=10, preserve_message=True)
        return False
    selected = getattr(game, 'menu_highlight', 0)
    while True:
        money = coins(char)
        if not money[GEMS] and not money[JEWELRY]: return True
        options = [label for label, count in (('Gems', money[GEMS]), ('Jewelry', money[JEWELRY])) if count]
        index = horizontal(game, Kind.LIST.value, tuple(options) + ('Exit',), prompt=game.assets.text('appraiseQuery'),
                     message=getattr(game, 'shop_note', ''), escape_choice=len(options), gems=money[GEMS], jewelry=money[JEWELRY],
                     purpose='appraise', start=selected if selected <= len(options) else 0,
                     member=member_name(char), name_column=1, name_row=1,
                     collection=game.assets.text('collectionMessage'), collection_column=1, collection_row=7,
                     count_lines=(game.assets.text('gemsCountLabel') + str(money[GEMS]), game.assets.text('jewelryCountLabel') + str(money[JEWELRY])),
                     count_column=1, count_rows=(9, 10), menu=game.assets.text('appraiseOptions'), horizontal=True,
                     menu_labels=('Gems', 'Jewelry', 'Exit'), enabled=tuple(i for i, held in enumerate((money[GEMS], money[JEWELRY], 1)) if held))
        game.shop_note = ''
        selected = game.menu_highlight
        if index == len(options):
            rules.recalc_stats(char, s.r1[0x372])
            return True
        kind = GEMS if options[index] == 'Gems' else JEWELRY
        money[kind] -= 1
        put_coins(char, money)
        roll = dice(s, 1, 100)
        if kind == GEMS:
            name_id, value = GEM_NAME, next(v for top, v in GEM_VALUES if roll <= top)
        else:
            span, base = next((span, base) for top, span, base in JEWEL_RANGES if roll <= top)
            name_id, value = JEWEL_NAME, s.random(span) + base
        selected = appraise_one(game, char, name_id, value, selected)
        if selected is None:
            money[kind] += 1
            put_coins(char, money)
        rules.recalc_stats(char, s.r1[0x372])
        if selected is None: return True


def item_available(game, char, item):
    if item[I['readied']]:
        note(game, 'Must be unreadied')
        return False
    if item[I['type']] in SCROLLS and any(v > 0x7F for v in item[I['powers']:I['powers'] + 3]):
        return deal(game, game.assets.text('loseQuery'), member_name(char) + ' ' + game.assets.text('scribeMessage'),
                    start=1, window='1 21 38 22')
    return True


def sell(game, char, item):
    value = word_at(item, I['value'])
    price = value // 2 if value else 0
    if item[I['quantity']]: price = price * item[I['quantity']] & 0xFFFF
    offer = game.assets.text('sellOfferPrefix') + str(price) + game.assets.text('steelPiecesFor') + item_name(game, item)
    if not deal(game, game.assets.text('dealQuery'), offer, window='1 21 38 22', colour=14): return
    pause(game, game.assets.text('soldText'), timed=1, message_colour=10,
          offer=offer, window='1 21 38 22', colour=14)
    from . import inventory
    inventory.remove_item(char, item, game)
    over, takable = check_overload(char, price)
    money = coins(char)
    if over:
        pause(game, game.assets.text('overloadPoolText'), timed=1, message_colour=10,
              offer=offer, window='1 21 38 22', colour=14)
        money[STEEL] += takable
        change_pool(game.s, STEEL, price - takable)
    else: money[STEEL] += price
    put_coins(char, money)


def identify(game, char, item):
    offer = game.assets.text('identifyOfferText') + item_name(game, item)
    if not deal(game, game.assets.text('dealQuery'), offer, window='1 21 38 22', colour=14): return False
    s, own = game.s, coin_value(game, coins(char))
    if own >= 100: set_creature_steel(char, own - 100)
    else:
        pooled = coin_value(game, s.treasure_money)
        if pooled + own < 100:
            pause(game, game.assets.text('notEnoughMoneyText'), timed=1, message_colour=10,
                  offer=offer, window='1 21 38 22', colour=14)
            return False
        set_creature_steel(char, 0)
        s.treasure_money[STEEL] = pooled - (100 - own)
    changed = bool(item[I['unidentified']] & 7)
    if changed:
        item[I['unidentified']] &= 0xF8
    message = game.assets.text('identifyKindText' if changed else 'identifyNoNewsText') + item_name(game, item)
    if changed: pause(game, message, window='1 21 38 22', colour=14, timed=1)
    pause(game, message, window='1 21 38 22', colour=14, timed=1)
    return changed


def view_items(game, char):
    from . import inventory
    inventory.view(game, char)


def has_money(s):
    return any(s.treasure_money[STEEL:])


def choose_member(game):
    who = pick(game, Kind.WHO, 'Who', [member_name(c) for c in game.s.party])
    if who is not None: game.s.sel = who
    return None if who is None else game.s.party[who]


def enter_service(game):
    s, vm = game.s, game.vm
    s.mode = SHOP_TEMPLE
    runtime = s.g.setdefault('dkk.runtime', {})
    runtime['noncombat_prepared'] = 0
    vm.interface_redraw_epoch += 1
    vm.party_drawn()
    runtime['noncombat_prepared'] = 1
    s.treasure_money[:] = [0] * COIN_TYPES
    s.g['treasure_active'] = 0


def select_adjacent(game, key):
    s = game.s
    s.sel = (s.sel + (-1 if key == 'char-up' else 1)) % len(s.chars())
    game.vm.party_drawn()


def main_menu(game, options, selected):
    labels = ('Buy', 'View', 'Take', 'Pool', 'Share', 'Appraise', 'Exit')
    choices = options + ('Exit', 'char-up', 'char-down')
    enabled = tuple(labels.index(label) for label in choices[:-2])
    while True:
        start = selected if 0 <= selected < len(enabled) else 0
        answer = horizontal(game, Kind.MENU.value, choices, prompt='', start=start, selected=selected,
                          escape_choice=len(options),
                          menu_labels=labels, enabled=enabled, member=member_name(game.s.selc()),
                          message=getattr(game, 'shop_note', ''))
        game.shop_note = ''
        selected = game.menu_highlight
        action = choices[answer]
        if action in ('char-up', 'char-down'): select_adjacent(game, action)
        else: return action, selected


def run(game, shop_id=None):
    s = game.s
    s.prev_mode = s.mode
    enter_service(game)
    for item in s.treasure_items: item_name(game, item)
    selected, redraw_after_pool = 0, True
    try:
        while True:
            options = ('Buy', 'View', 'Take', 'Pool', 'Share', 'Appraise') if has_money(s) else ('Buy', 'View', 'Pool', 'Appraise')
            action, selected = main_menu(game, options, selected)
            if action == 'Exit':
                if not has_money(s) or not deal(game, '', game.assets.text('leftMoney1') + game.assets.text('leftMoney2'),
                                                window='1 17 38 22',
                                                messages=(game.assets.text('leftMoney1'), game.assets.text('leftMoney2')),
                                                clear_first=(True, False), colours=(10, 15)): return
                game.vm.clear_text()
            elif action == 'Pool':
                pool_money(s)
                if redraw_after_pool: game.vm.clear_text()
            elif action == 'Share': share_money(s)
            else:
                char = s.selc()
                if action == 'Buy': buy_menu(game, char)
                elif action == 'View': view_items(game, char)
                elif action == 'Take': take_menu(game, char)
                else: redraw_after_pool = appraise(game, char)
                game.vm.clear_text()
            game.vm.party_drawn()
    finally:
        game.vm.party_drawn()
        s.mode = s.prev_mode


def test():
    from .data import Assets
    assert len(tables(Assets()).parts) > 100
