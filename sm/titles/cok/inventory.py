from enum import Enum

from . import creation, effects, rules, shop
from .creation import F
from .shop import COIN_NAMES, I

STEEL_COINS = range(1, 7)
ANIMATED, NON_PLAYER, SHOP_TEMPLE, LOOT, IN_COMBAT = 1, 0x80, 1, 6, 5
SCROLL, ARROWS, QUARRELS, MAX_ITEMS = 39, 30, 12, 16
CAMPING, OVERLAND, VIEW_3D, ANTI_MAGIC_CELL, HUMAN, MAGE, CLERIC, THIEF = 2, 3, 4, 0xE5, 6, 5, 0, 6


class Kind(str, Enum):
    SHEET = 'CREATE_VIEW'
    ITEMS = 'VIEW_ITEMS'
    ACTION = 'VIEW_ACTION'
    WHO = 'VIEW_WHO'
    COIN = 'VIEW_COIN'
    NUMBER = 'NUMBER'
    CONFIRM = 'VIEW_CONFIRM'


def signed(value):
    return value - 256 if value > 127 else value


def sheet(game, char):
    rules.recalc_stats(char)
    b = char.b
    move = b[F['move']]
    if effects.has_effect(char, effects.HASTED) is not None: move = move * 2 & 255
    if effects.has_effect(char, 42) is not None: move //= 2
    bonus = signed(b[F['damage_bonus']])
    damage = '%dd%d' % (b[F['damage_rolls']], b[F['damage_dice']]) + ('+%d' % bonus if bonus > 0 else '-%d' % -bonus if bonus < 0 else '')
    return dict(creation.sheet(game, char), ac_shown=60 - b[F['ac']], thac0_shown=60 - b[F['thac0']], encumbrance=shop.weight(char), move=move, damage=damage,
                items='; '.join(shop.item_name(game, item, True).strip() for item in char.items))


def can_hand_over(char):
    return char.b[F['npc']] < NON_PLAYER or not char.b[F['active']] or char.b[F['status']] == ANIMATED


def toggle_item_effect(game, char, item, equipping):
    kind = item[I['powers'] + 2] & 0x7F
    if kind in (0, 2):
        if equipping: effects.add_effect(char, item[I['powers'] + 1], 0, 255, True)
        else: effects.remove_effect(game, char, item[I['powers'] + 1])
    elif kind in (3, 5): effects.recalc_ability(game, char, 0)
    elif kind == 9 and not equipping: effects.remove_effect(game, char, 23)


def toggle_ready(game, char, item):
    special = item[I['powers'] + 2] > 0x7F
    if item[I['readied']]:
        if item[I['cursed']]:
            shop.note(game, "It's Cursed")
            return
        item[I['readied']] = 0
        if special: toggle_item_effect(game, char, item, False)
        return
    kind = item[I['type']]
    base = rules.tables().base_item(kind)
    worn = rules.worn(char)
    slot, error = base[rules.SLOT], 0
    if char.b[F['hands_used']] + base[rules.HANDS] > 2: error = 3
    if slot <= 8 and worn[slot] is not None: error = 2
    if slot == 9 and worn[10] is not None: error = 2
    if kind == SCROLL and not (char.b[F['robe_order']] == 1 and item[I['unidentified']] & 0x20 or char.b[F['robe_order']] == 2 and item[I['unidentified']] & 0x10): error = 4
    if kind == rules.HOOPAK and char.b[F['race']] != rules.KENDER: error = 5
    if kind == ARROWS and worn[11] is not None: error, slot = 2, 11
    if kind == QUARRELS and worn[12] is not None: error, slot = 2, 12
    if not base[rules.USABLE_BY] & char.b[F['class_mask']]: error = 1
    if error == 0:
        item[I['readied']] = 1
        if special: toggle_item_effect(game, char, item, True)
    elif error == 1: shop.note(game, 'Wrong Class')
    elif error == 2: shop.note(game, 'already using ' + shop.item_name(game, worn[slot].data))
    elif error == 3: shop.note(game, 'Your hands are full!')
    elif error == 4: shop.note(game, 'Wrong Magical Order')
    else: shop.note(game, 'Usable Only By Kender')


def trade_item(game, char, item):
    target = shop.pick(game, Kind.WHO, 'Trade with Whom?', [shop.member_name(c) for c in game.s.party])
    if target is None: return
    receiver = game.s.party[target]
    if shop.cannot_carry(receiver, item):
        shop.note(game, 'Overloaded')
        return
    copy = bytearray(item)
    copy[I['next_pointer']:I['next_pointer'] + 4] = bytes(4)
    receiver.items.append(copy)
    remove_item(char, item)
    rules.recalc_stats(receiver)


def remove_item(char, item):
    for at, held in enumerate(char.items):
        if held is item:
            del char.items[at]
            return


def halve(game, char, item):
    half = item[I['quantity']] // 2
    if not half:
        shop.note(game, "Can't halve that")
        return
    copy = bytearray(item)
    copy[I['quantity']], copy[I['readied']] = half, 0
    item[I['quantity']] -= half
    for at, held in enumerate(char.items):
        if held is item:
            char.items.insert(at + 1, copy)
            return


def join(game, char, item):
    target, count = item, item[I['quantity']]
    for held in list(char.items):
        if held is target or not held[I['quantity']]: continue
        if (held[I['name_ids']:I['name_ids'] + 3] == target[I['name_ids']:I['name_ids'] + 3] and held[I['type']] == target[I['type']] and held[I['bonus']] == target[I['bonus']] and
                held[I['save_bonus']] == target[I['save_bonus']] and held[I['cursed']] == target[I['cursed']] and held[I['weight']:I['weight'] + 2] == target[I['weight']:I['weight'] + 2] and
                held[I['powers']] < 2):
            if count + held[I['quantity']] <= 255:
                count += held[I['quantity']]
                remove_item(char, held)
            else:
                target[I['quantity']] = 255
                held[I['quantity']] -= 255 - count
                count, target = held[I['quantity']], held
    target[I['quantity']] = count


def drop_item(game, char, item):
    if shop.item_available(game, char, item) and shop.deal(game, 'Drop It? ', 'Your ' + shop.item_name(game, item) + 'will be gone forever'):
        remove_item(char, item)


def can_use(game, char):
    s = game.s
    battle = getattr(game, 'battle', None)
    combat_ok = s.mode == IN_COMBAT and battle is not None and battle.record(battle.index(char))['item_ok']
    return char.b[F['active']] and not s.r0[ANTI_MAGIC_CELL] and (s.mode in (CAMPING, OVERLAND, VIEW_3D) or combat_ok)


def actions_left(game, char):
    battle = getattr(game, 'battle', None)
    return battle is None or not battle.data['active'] or battle.record(battle.index(char))['initiative'] > 0


def first_class(levels, char):
    if char.b[F['race']] != HUMAN: return 17
    return next((c for c in range(7) if levels[c] > 0), 17)


def magic_row(spell_id):
    from . import magic
    return magic.spell(spell_id)


def scroll_spells(char, item):
    from . import magic
    magic._identify(char, item)
    if item[I['unidentified']] & 7: return []
    return [v for v in item[I['powers']:I['powers'] + 3] if v]


def cast_from_item(game, char, spell_id):
    if getattr(game, 'battle', None) is not None: return game.battle.cast_item(char, spell_id)
    from . import magic
    s, row, done = game.s, magic.spell(spell_id), False
    going = row.targeting != magic.COMBAT_ONLY
    if not going and shop.deal(game, 'Use it? ', 'That Item is a combat-only item...'): done = True
    if magic._find(char, magic.MISCAST) is not None and creation.dice(s, 1, 2) == 1:
        shop.pause(game, shop.member_name(char) + ' miscasts ' + row.name)
        return done
    if not going: return done
    if row.id not in magic.HANDLERS: raise creation.BindingRequired('Champions spell not bound outside combat: %d %s' % (row.id, row.name))
    targets = magic._targets(game, char, row, None)
    if targets is None: return False
    while magic._remove(game, char, magic.INVISIBLE): pass
    magic.HANDLERS[row.id](game, char, targets, row)
    return True


def use_item(game, char, item):
    b = char.b
    readable = item[I['type']] in shop.SCROLLS
    spell = 0
    if readable:
        from . import magic
        offered = scroll_spells(char, item)
        if not offered: return
        levels = tuple(magic.spell(v).level for v in offered)
        pick = shop.pick(game, Kind.ITEMS, 'Spells on Scroll', [magic.scroll_line(v) for v in offered], levels=levels,
                         start=magic.list_start(levels, scroll=True)[0])
        spell = 0 if pick is None else offered[pick] & 0x7F
    elif item[I['powers'] + 1] > 0 and item[I['powers'] + 2] < 0x80:
        spell = item[I['powers'] + 1] & 0x7F
    if not spell: return
    done = False
    if not readable:
        shop.pause(game, shop.member_name(char) + ' uses an item', item=shop.item_name(game, item))
        done = cast_from_item(game, char, spell)
    else:
        levels, former = creation.levels(b), b[F['former_levels']:F['former_levels'] + 8]
        if (first_class(former, char) in (MAGE, CLERIC) or first_class(levels, char) in (MAGE, CLERIC) or levels[MAGE] > 0 or levels[CLERIC] > 0 or
                levels[THIEF] > 9 and creation.dice(game.s, 1, 100) <= 75):
            done = cast_from_item(game, char, spell)
        else: shop.pause(game, shop.member_name(char) + ' oops!')
    battle = getattr(game, 'battle', None)
    if battle is not None and battle.data['active'] and magic_row(spell).combat_ok:
        done = battle.end(battle.index(char))
    if not done: return
    if readable: spend_scroll(char, item, spell)
    elif item[I['powers']] > 0:
        if item[I['quantity']] > 1: item[I['quantity']] -= 1
        else:
            item[I['powers']] -= 1
            if not item[I['powers']]: remove_item(char, item)


def spend_scroll(char, item, spell):
    match = [i for i in range(3) if item[I['powers'] + i] & 0x7F == spell]
    if not match: return
    item[I['powers'] + match[-1]] = 0
    item[I['name_ids']] -= 1
    if item[I['name_ids']] < 100: remove_item(char, item)


def item_actions(game, char, in_shop):
    options = ['Ready']
    if can_use(game, char): options.append('Use')
    handed = can_hand_over(char)
    if handed and game.s.mode != IN_COMBAT: options.append('Trade')
    options.append('Drop')
    if char.b[F['item_count']] < MAX_ITEMS: options.append('Halve')
    options.append('Join')
    if in_shop and handed: options.append('Sell')
    if in_shop: options.append('Id')
    return options


def items_menu(game, char):
    in_shop, index = game.s.mode == SHOP_TEMPLE, 0
    while char.items and actions_left(game, char):
        labels = [shop.item_name(game, item, True) for item in char.items]
        index = shop.pick(game, Kind.ITEMS, 'Items', labels, window='1 5 38 22', title=shop.member_name(char) + "'s Items", caption='Ready Item',
                          start=min(index, len(labels) - 1))
        if index is None: return
        item = char.items[index]
        options = item_actions(game, char, in_shop)
        pick = shop.pick(game, Kind.ACTION, 'Item', options)
        if pick is None: continue
        action = options[pick]
        if action == 'Ready': toggle_ready(game, char, item)
        elif action == 'Use':
            if not item[I['readied']]: shop.note(game, 'Must be Readied')
            elif item[I['type']] in shop.SCROLLS or item[I['powers'] + 1] > 0 and item[I['powers'] + 2] < 0x80: use_item(game, char, item)
        elif action == 'Trade':
            if shop.item_available(game, char, item): trade_item(game, char, item)
        elif action == 'Drop': drop_item(game, char, item)
        elif action == 'Halve': halve(game, char, item)
        elif action == 'Join': join(game, char, item)
        elif action == 'Sell':
            if shop.item_available(game, char, item): shop.sell(game, char, item)
        else: shop.identify(game, char, item)
        rules.recalc_stats(char)


def coin_kinds(char):
    money = shop.coins(char)
    return [m for m in range(1, 7) if money[m]]


def trade_money(game, giver, receiver, amount, kind):
    if shop.weight(receiver) + amount > shop.carrying_capacity(receiver):
        shop.pause(game, 'Overloaded')
        return
    money = shop.coins(giver); money[kind] -= amount; shop.put_coins(giver, money); shop.add_weight(giver, -amount)
    money = shop.coins(receiver); money[kind] = (money[kind] + amount) & 0xFFFF; shop.put_coins(receiver, money); shop.add_weight(receiver, amount)


def ask_amount(game, char, kind, verb):
    limit = shop.coins(char)[kind]
    return min(game.ask(Kind.NUMBER.value, None, prompt='How much %swill you %s? ' % (shop.TAKE_NAMES[kind], verb), max=limit), limit)


def coin_label(char, kind, drop=False):
    name, amount = COIN_NAMES[kind], str(shop.coins(char)[kind])
    return name + ' ' * (18 - len(name) - len(amount)) + amount if drop else name.ljust(14) + amount


def trade_coins(game, char):
    while True:
        target = shop.pick(game, Kind.WHO, 'Trade to?', [shop.member_name(c) for c in game.s.party])
        if target is None: return
        receiver = game.s.party[target]
        while coin_kinds(char):
            kinds = coin_kinds(char)
            pick = shop.pick(game, Kind.COIN, 'Select type of coin ', [coin_label(char, k) for k in kinds])
            if pick is None: break
            trade_money(game, char, receiver, ask_amount(game, char, kinds[pick], 'trade'), kinds[pick])
        else: return


def drop_coins(game, char):
    while coin_kinds(char):
        kinds = coin_kinds(char)
        pick = shop.pick(game, Kind.COIN, 'Select type of coin ', [coin_label(char, k, True) for k in kinds])
        if pick is None: return
        kind, amount = kinds[pick], ask_amount(game, char, kinds[pick], 'drop')
        money = shop.coins(char); money[kind] -= amount; shop.put_coins(char, money); shop.add_weight(char, -amount)
        if game.s.mode in (SHOP_TEMPLE, LOOT): game.s.treasure_money[kind] += amount


def memorized_names(game, char):
    from . import camp
    names = camp.tables(game.assets).names
    return ', '.join(names[(n & 0x7F) - 1] for n in camp.memory(char) if 0 < n < 0x80)


def view(game, char):
    from . import camp
    s = game.s
    while actions_left(game, char):
        spells = memorized_names(game, char)
        options = (['Items'] if char.items else []) + (['Spells'] if any(camp.memory(char)) else [])
        money = any(shop.coins(char)[1:])
        if money and can_hand_over(char) and s.mode != IN_COMBAT: options.append('Trade')
        if money: options.append('Drop')
        options.append('Exit')
        info = sheet(game, char)
        action = options[game.ask(Kind.SHEET.value, tuple(options), message=getattr(game, 'shop_note', ''), **info)]
        game.shop_note = ''
        if action == 'Exit': return
        if action == 'Items': items_menu(game, char)
        elif action == 'Spells':
            if spells: shop.pick(game, Kind.ITEMS, 'Spells in Memory', [], spells=spells)
        elif action == 'Trade': trade_coins(game, char)
        else: drop_coins(game, char)
