from enum import Enum

from . import creation, effects, rules, shop
from .creation import F
from .shop import COIN_NAMES, I

STEEL_COINS = range(1, 7)
ANIMATED, NON_PLAYER, SHOP_TEMPLE, LOOT, IN_COMBAT = 1, 0x80, 1, 6, 5
SCROLL, ARROWS, QUARRELS, MAX_ITEMS = 39, 30, 12, 16
CAMPING, OVERLAND, VIEW_3D, ANTI_MAGIC_CELL, HUMAN, MAGE, CLERIC, THIEF = 2, 3, 4, 0xE5, 6, 5, 0, 6
IN_VAULT = 7


class Kind(str, Enum):
    SHEET = 'CREATE_VIEW'
    ITEMS = 'VIEW_ITEMS'
    ACTION = 'VIEW_ACTION'
    WHO = 'VIEW_WHO'
    COIN = 'VIEW_COIN'
    NUMBER = 'NUMBER'


def signed(value):
    return value - 256 if value > 127 else value


def sheet(game, char):
    rules.recalc_sheet_stats(char, game.s.r1[0x372])
    b = char.b
    move = b[F['move']]
    bonus = signed(b[F['damage_bonus']])
    damage = '%dd%d' % (b[F['damage_rolls']], b[F['damage_dice']]) + ('+%d' % bonus if bonus > 0 else '-%d' % -bonus if bonus < 0 else '')
    worn = rules.worn(char)
    items = '; '.join(shop.item_name(game, worn[slot].data).strip() for slot in (0, 2) if worn[slot] is not None)
    return dict(name=shop.member_name(char), identity=sheet_identity(game, char), hp=b[F['hp']], hp_max=b[F['hp_max']], ac_shown=60 - b[F['ac']], thac0_shown=60 - b[F['thac0']], encumbrance=shop.weight(char), move=move, damage=damage,
                items=items)


def sheet_identity(game, char):
    r, assets = rules.record(char), game.assets
    levels = tuple(signed(n) for n in r.get('levels'))
    label = assets.names('classNames')[r.get('class')]
    if levels[CLERIC] > 0: label = assets.names('deityNames')[r.get('deity')] + ' ' + label
    if levels[MAGE] > 0:
        at = next((i for i in range(len(label) - 2) if label[i] == 'M' and label[i + 2] == 'g'), len(label))
        label = label[:at] + assets.names('robeOrderNames')[r.get('robe_order')] + ' ' + label[at:]
    if levels[creation.KNIGHT] > 0 and 1 <= r.get('knight_order') <= 3:
        label += ' of the ' + ('Crown', 'Sword', 'Rose')[r.get('knight_order') - 1]
    return dict(name=shop.member_name(char), status=r.get('status'), gender=assets.names('genderNames')[r.get('gender')], hp=r.get('hp_max'), hp_now=r.get('hp'),
                age=r.get('age'), alignment=assets.names('alignmentNames')[r.get('alignment')], race=assets.names('raceNames')[r.get('race')],
                description=label, levels='/'.join(str(n) for n in levels if n > 0) or '0', experience=r.get('experience', signed=True),
                steel=shop.coins(char)[4], gems=shop.coins(char)[5], jewelry=shop.coins(char)[6])


def can_hand_over(char):
    return char.b[F['npc']] < NON_PLAYER or not char.b[F['active']] or char.b[F['status']] == ANIMATED


def toggle_item_effect(game, char, item, equipping):
    kind = item[I['powers'] + 2] & 0x7F
    if kind in (0, 2):
        from .effects_handlers import grant_item_effect
        grant_item_effect(game, char, item, removed=not equipping)
    elif kind in (3, 5): effects.recalc_ability(game, char, 0)
    elif kind == 9 and not equipping: effects.remove_effect(game, char, 23)


def bottom_message(game, text):
    shop.pause(game, text[:40], timed=1, message_colour=10)


def toggle_ready(game, char, item, notify=bottom_message):
    special = item[I['powers'] + 2] > 0x7F
    if item[I['readied']]:
        if item[I['cursed']]:
            notify(game, "It's Cursed")
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
    if kind == SCROLL and not (char.b[F['robe_order']] == 1 and item[I['unidentified']] & 0x20 or char.b[F['robe_order']] == 2 and item[I['unidentified']] & 0x10):
        thief = signed(char.b[F['levels'] + THIEF])
        if thief <= 9: error = 6 if thief > 0 else 4
    if kind == 67 and char.b[F['race']] != rules.KENDER: error = 5
    if kind == ARROWS and worn[11] is not None: error, slot = 2, 11
    if kind == QUARRELS and worn[12] is not None: error, slot = 2, 12
    if not base[rules.USABLE_BY] & char.b[F['class_mask']]: error = 1
    if error == 0:
        item[I['readied']] = 1
        if special: toggle_item_effect(game, char, item, True)
    elif error == 1: notify(game, 'Wrong Class')
    elif error == 2: notify(game, ('already using ' + shop.item_name(game, worn[slot].data))[:40])
    elif error == 3:
        if game.s.mode != IN_COMBAT or not char.b[F['auto_combat']]: notify(game, 'Your hands are full!')
    elif error == 4: notify(game, 'Wrong Magical Order')
    elif error == 5: notify(game, 'Usable Only By Kender')
    else: notify(game, 'Thief Level Too Low')


def pick_recipient(game, prompt, initial=None):
    s = game.s
    party = s.chars()
    start = party.index(initial) if initial is not None else 0
    runtime = s.g.setdefault('dkk.runtime', {})
    mouse_mode = runtime.get('mouse_mode', 1)
    extended = s.g.pop('world.extended', None)
    runtime['selection_mode'] = 1
    if s.mode == 0: runtime['mouse_mode'] = 1
    try:
        choice = shop.pick(game, Kind.WHO, prompt, [shop.member_name(c) for c in party], start=start, vertical=True)
        return party[choice] if choice is not None else None
    finally:
        if extended is not None: s.g['world.extended'] = extended
        runtime.update(mouse_mode=mouse_mode, selection_mode=0)


def trade_recipient(game, char, prompt):
    previous = getattr(game, 'trade_character', None)
    target = pick_recipient(game, prompt, previous if previous in game.s.chars() else char)
    if target is not None: game.trade_character = target
    return target


def trade_item(game, char, item):
    receiver = trade_recipient(game, char, 'Trade with Whom?')
    if receiver is None: return
    if shop.cannot_carry(receiver, item, game=game):
        bottom_message(game, 'Overloaded')
        return
    copy = copy_item(game, receiver, item)
    if copy is None: return
    copy[I['next_pointer']:I['next_pointer'] + 4] = bytes(4)
    receiver.items.append(copy)
    remove_item(char, item, game)
    rules.recalc_stats(receiver, game.s.r1[0x372])


def copy_item(game, char, item):
    battle = getattr(game, 'battle', None)
    if game.s.mode == IN_COMBAT and battle is not None:
        actors = battle.data.get('actors', ())
        for member, actor in zip(game.s.chars(), actors):
            if member is char and actor.get('outsider') == 1: return bytearray(item)
    copy = rules.allocate_item(game)
    if copy is not None: copy[:] = item
    return copy


def remove_item(char, item, game):
    for at, held in enumerate(char.items):
        if held is item:
            del char.items[at]
            offset = I['next_pointer']
            item[offset:offset + 4] = bytes(4)
            pool = getattr(getattr(game, 'game', game), 'item_pool', None)
            if pool is not None: pool.release(item)
            return


def halve(game, char, item, notify=bottom_message):
    half = item[I['quantity']] // 2
    if not half:
        notify(game, "Can't halve that")
        return
    for at, held in enumerate(char.items):
        if held is item:
            copy = copy_item(game, char, item)
            if copy is None: return
            copy[I['quantity']], copy[I['readied']] = half, 0
            item[I['quantity']] -= half
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
                remove_item(char, held, game)
            else:
                target[I['quantity']] = 255
                held[I['quantity']] -= 255 - count
                count, target = held[I['quantity']], held
    target[I['quantity']] = count


def drop_item(game, char, item):
    if not shop.item_available(game, char, item): return
    name = shop.item_name(game, item)[:40]
    if game.s.mode == IN_VAULT:
        shop.pause(game, 'Your ' + name + 'will be left in the vault', timed=1, window='1 21 38 22', colour=14)
        stored = rules.Item(item)
        stored.set('next_pointer', 0)
        game.s.treasure_items.append(stored.data)
        remove_item(char, item, game)
    elif shop.deal(game, game.assets.text('loseQuery'), game.assets.text('dropYour') + name + game.assets.text('goneForever'),
                   start=1, window='1 21 38 22', colour=14):
        remove_item(char, item, game)


def can_use(game, char):
    s = game.s
    battle = getattr(game, 'battle', None)
    combat_ok = s.mode == IN_COMBAT and battle is not None and battle.record(battle.index(char))['item_ok']
    return char.b[F['active']] and not s.r0[ANTI_MAGIC_CELL] and (s.mode in (CAMPING, OVERLAND, VIEW_3D) or combat_ok)


def actions_left(game, char):
    battle = getattr(game, 'battle', None)
    return battle is None or not battle.data['active'] or battle.record(battle.index(char))['initiative'] > 0


def use_item(game, char, item):
    from . import magic
    return magic.use_item(game, char, item)


def item_actions(game, char, in_shop):
    options = ['Ready']
    if can_use(game, char): options.append('Use')
    handed = can_hand_over(char)
    if handed and game.s.mode != IN_COMBAT: options.append('Trade')
    options.append('Deposit' if game.s.mode == IN_VAULT else 'Drop')
    if char.b[F['item_count']] < MAX_ITEMS: options.append('Halve')
    options.append('Join')
    if in_shop and handed: options.append('Sell')
    if in_shop: options.append('Id')
    return options


def items_menu(game, char):
    in_shop = game.s.mode == SHOP_TEMPLE
    index = 0
    while char.items:
        done = False
        labels = [shop.item_name(game, item, True) for item in char.items]
        index = shop.pick(game, Kind.ITEMS, 'Items', labels, start=min(index, len(labels) - 1))
        if index is None:
            rules.recalc_stats(char, game.s.r1[0x372])
            return False
        item = char.items[index]
        options = item_actions(game, char, in_shop)
        pick = shop.pick(game, Kind.ACTION, 'Item', options)
        if pick is None: continue
        action = options[pick]
        if action == 'Ready': toggle_ready(game, char, item, notify=shop.note)
        elif action == 'Use':
            if not item[I['readied']]: shop.note(game, game.assets.text('mustBeReadied'))
            elif item[I['type']] in shop.SCROLLS or item[I['powers'] + 1] > 0 and item[I['powers'] + 2] < 0x80:
                done = bool(use_item(game, char, item)) and game.s.mode == IN_COMBAT
        elif action == 'Trade':
            if shop.item_available(game, char, item): trade_item(game, char, item)
        elif action in ('Drop', 'Deposit'): drop_item(game, char, item)
        elif action == 'Halve': halve(game, char, item, notify=shop.note)
        elif action == 'Join': join(game, char, item)
        elif action == 'Sell':
            if shop.item_available(game, char, item): shop.sell(game, char, item)
        else: shop.identify(game, char, item)
        rules.recalc_stats(char, game.s.r1[0x372])
        if done: return True
    return False


def coin_kinds(char):
    money = shop.coins(char)
    return [m for m in range(4, 7) if money[m]]


def trade_money(game, giver, receiver, amount, kind):
    amount &= 0xFFFF
    if (shop.weight(receiver) + amount & 0xFFFF) > shop.carrying_capacity(receiver):
        shop.overload_notice(game, game.assets.text('tradeOverloadMessage'))
        return
    money = shop.coins(giver); money[kind] -= amount; shop.put_coins(giver, money); shop.add_weight(giver, -amount)
    money = shop.coins(receiver); money[kind] = (money[kind] + amount) & 0xFFFF; shop.put_coins(receiver, money); shop.add_weight(receiver, amount)


def ask_amount(game, char, kind, verb):
    limit = shop.coins(char)[kind]
    query = game.assets.text('howMuch') + game.assets.names('moneyNames')[kind] + ' ' + game.assets.text(verb + 'AmountText')
    return shop.input_number(game, limit, query)


def coin_label(char, kind, drop=False):
    name, amount = COIN_NAMES[kind], str(shop.coins(char)[kind])
    return name + ' ' * (18 - len(name) - len(amount)) + amount if drop else name.ljust(14) + amount


def trade_coins(game, char):
    selected_coin = False
    while True:
        receiver = trade_recipient(game, char, game.assets.text('tradeToText'))
        if receiver is None: return
        sheet(game, char)
        while coin_kinds(char):
            kinds = coin_kinds(char)
            pick = shop.pick(game, Kind.COIN, game.assets.text('selectCoinQuery'), [coin_label(char, k) for k in kinds])
            if pick is None:
                if not selected_coin: return
                break
            selected_coin = True
            trade_money(game, char, receiver, ask_amount(game, char, kinds[pick], 'trade'), kinds[pick])
        else: return


def drop_coins(game, char, on_sheet=True):
    query = game.assets.text('selectCoinQuery')
    layout = {} if on_sheet else dict(window='1 17 38 22', query=query, menu=game.assets.text('selectMenuText'))
    while coin_kinds(char):
        kinds = coin_kinds(char)
        pick = shop.pick(game, Kind.COIN, query, [coin_label(char, k, True) for k in kinds],
                         start=0, **layout)
        if pick is None: return
        kind, amount = kinds[pick], ask_amount(game, char, kinds[pick], 'give' if game.s.mode == IN_VAULT else 'drop')
        money = shop.coins(char); money[kind] -= amount; shop.put_coins(char, money); shop.add_weight(char, -amount)
        if game.s.mode in (SHOP_TEMPLE, LOOT, IN_VAULT): shop.change_pool(game.s, kind, amount)


def memorized_names(game, char):
    from . import camp
    names = camp.tables(game.assets).names
    return ', '.join(names[(n & 0x7F) - 1] for n in camp.memory(char) if 0 < n < 0x80)


def view(game, char):
    from . import magic
    s = game.s
    game.trade_character = char
    info = sheet(game, char)
    choice = 0
    while True:
        book = rules.spellbook(char)
        has_spells = book is not None and any(n & 0x7F for n in book.get('memorized'))
        options = (['Items'] if char.items else []) + (['Spells'] if has_spells else [])
        money = bool(coin_kinds(char))
        if money and can_hand_over(char) and s.mode != IN_COMBAT: options.append('Trade')
        if money: options.append('Deposit' if s.mode == IN_VAULT else 'Drop')
        paladin = char.b[F['class']] == 3 and char.b[F['status']] == 0 and s.mode != IN_COMBAT
        if paladin and not effects.has(char, 109): options.append('Heal')
        if paladin and char.b[F['cure_ability']]: options.append('Cure')
        options.append('Exit')
        view_index = next((index for index, member in enumerate(s.chars()) if member is char), None)
        choice = game.ask(Kind.SHEET.value, tuple(options), view_index=view_index,
                          start=choice if choice < len(options) else 0,
                          message=getattr(game, 'shop_note', ''), **info)
        action = options[choice]
        game.shop_note = ''
        if action == 'Exit': return False
        if action == 'Items':
            if items_menu(game, char): return True
        elif action == 'Spells':
            magic.spell_menu(game, char, 0, 0, combat=s.mode == IN_COMBAT)
        elif action == 'Trade': trade_coins(game, char)
        elif action in ('Heal', 'Cure'):
            target = pick_recipient(game, action + ' whom? ')
            if action == 'Cure' and target is None:
                sheet(game, char)
            if target is not None and action == 'Heal':
                healed = effects.restore_hp(target, (2 * char.b[F['levels'] + 3]) & 255, True, s.mode == IN_COMBAT)
                shop.pause(game, shop.member_name(target) + (' feels better' if healed else ' is unaffected'), timed=1, message_colour=10)
                effects.add_effect(char, 109, 1440, 0, False)
        else:
            drop_coins(game, char)
            info = dict(info, identity=sheet_identity(game, char))
            continue
        info = sheet(game, char)


def test():
    assert signed(255) == -1 and signed(127) == 127
    from .menu import Game
    from .records import Character, Item, Spells
    game = Game(None)
    char = rules.character(bytes(Character()), spells=bytes(Spells()))
    r, book = rules.record(char), rules.spellbook(char)
    r.set('abilities', bytes((14, 14)) * 6)
    r.set('base_move', 12)
    game.s.party = [char]
    game.s.mode = CAMPING
    book.data[73] = 138
    answers = iter(('Spells', 'Exit'))
    def player(kind, options, current, **info):
        assert kind == Kind.SHEET.value and 'Spells' in options
        return options.index(next(answers))
    game.player = player
    view(game, char)
    assert next(answers, None) is None and book.data[73] == 138
    shop.put_coins(char, [0, 0, 0, 0, 30, 2, 1])
    assert coin_kinds(char) == [4, 5, 6]
    assert coin_label(char, 4) == COIN_NAMES[4].ljust(14) + '30'
    assert len(coin_label(char, 4, True)) == 18
    item = Item()
    t = rules.tables()
    kind = next(k for k in range(39) if t.base_item(k)[rules.HANDS] and t.base_item(k)[rules.SLOT] < 9)
    item.set('type', kind)
    char.items.append(item.data)
    r.set('hands_used', 2)
    r.set('class_mask', 255)
    r.set('auto_combat', 1)
    game.s.mode = IN_COMBAT
    notices = []
    game.player = lambda kind, options, current, **info: notices.append(info) or 0
    toggle_ready(game, char, item.data)
    assert not notices and not item.get('readied')
    r.set('auto_combat', 0)
    toggle_ready(game, char, item.data)
    assert notices == [dict(prompt='Your hands are full!', timed=1, message_colour=10)] and not item.get('readied')
    game.s.mode = CAMPING
    game.s.r1[0x372] = 3
    choices = iter((0, 'Join', 'Exit'))
    def menu_player(kind, options, current, **info):
        answer = next(choices)
        return options.index(answer) if isinstance(answer, str) else answer
    game.player = menu_player
    items_menu(game, char)
    assert next(choices, None) is None and r.get('move') == 15
    decisions = []
    def refuse(kind, options, current, **info):
        assert kind == shop.Kind.CONFIRM.value and options == ('Yes', 'No')
        decisions.append(info)
        return 1
    game.player = refuse
    drop_item(game, char, item.data)
    assert char.items == [item.data] and decisions[0]['start'] == 1
    assert decisions[0]['prompt'] == game.assets.text('loseQuery')
    game.player = lambda *args, **kwargs: 0
    drop_item(game, char, item.data)
    assert not char.items
    r.set('class', 3)
    r.set('cure_ability', 1)
    sheet(game, char)
    before = bytes(char.b)
    answers = iter(('Cure', 0, 'Exit'))
    def cure_player(kind, options, current, **info):
        answer = next(answers)
        if kind == Kind.WHO.value: assert info['prompt'] == 'Cure whom? '
        return options.index(answer) if isinstance(answer, str) else answer
    game.player = cure_player
    view(game, char)
    assert next(answers, None) is None and bytes(char.b) == before and not char.effects
