from enum import Enum

from . import camp, effects, shop
from .creation import F, dice
from .effects import has_effect, remove_effect
from .shop import I

BLIND, ANIMATED, CURSED, POISONED, SLOW_POISON, POISON_DAMAGE, FEEBLEMINDED = 33, 32, 36, 55, 22, 15, 68
DEAD, ANIMATED_STATUS, STONED, CON = 6, 1, 7, 4
ELF_RACES_BELOW, FIGHTER = 2, 2
LEFT_MONEY = 'As you leave a priest says, "Excuse me but you have left some money here" '


class Kind(str, Enum):
    MENU = 'TEMPLE'
    LIST = 'TEMPLE_LIST'
    CONFIRM = 'TEMPLE_CONFIRM'


def names(game):
    raw = bytes(game.assets.table('templeMenuItems'))
    return [raw[i + 1:i + 1 + raw[i]].decode('cp437') for i in range(0, len(raw), 41)][:10]


def disease_ids(game):
    return game.assets.table('diseaseEffects')


def confirm(game, prompt, offer=''):
    return game.ask(Kind.CONFIRM.value, ('Yes', 'No'), prompt=prompt, offer=offer) == 0


def cure_anyway(game, char, text):
    return confirm(game, 'cast cure anyway: ', shop.member_name(char) + ' ' + text)


def pay(game, char, label, cost):
    s = game.s
    if not confirm(game, 'pay for cure ', '%s will only cost %d steel pieces.' % (label, cost)): return False
    own = shop.coin_value(game, shop.coins(char)) & 0xFFFF
    if cost <= own: shop.set_creature_steel(char, own - cost)
    else:
        pooled = shop.coin_value(game, s.treasure_money)
        if cost > pooled:
            shop.note(game, 'Not enough money.')
            return False
        shop.set_pool_steel(s, pooled - cost)
    shop.pause(game, shop.member_name(char) + ' is cured.')
    return True


def locked_remove(game, char, *kinds):
    game.effect_busy = True
    try:
        for kind in kinds: remove_effect(game, char, kind)
    finally: game.effect_busy = False


def cure_blindness(game, char):
    if (has_effect(char, BLIND) is not None or cure_anyway(game, char, 'is not blind.')) and pay(game, char, 'Cure Blindness', 500):
        remove_effect(game, char, BLIND)


def cure_disease(game, char):
    ids = disease_ids(game)
    if any(has_effect(char, k) is not None for k in ids) or cure_anyway(game, char, 'is not Diseased.'):
        if pay(game, char, 'Cure Disease', 500):
            locked_remove(game, char, *ids)
            effects.recalc_ability(game, char, 0)


def cure_wounds(game, char, label, cost, count, bonus):
    if pay(game, char, label, cost):
        camp.restore_hit_points(game, char, (dice(game.s, count, 8) + bonus) & 255)


def heal(game, char):
    if not pay(game, char, 'Heal', 2500): return
    roll = dice(game.s, 1, 4)
    hp, top = char.b[F['hp']], char.b[F['hp_max']]
    camp.restore_hit_points(game, char, 0 if hp + roll > top else (top - hp - roll) & 255)
    remove_effect(game, char, BLIND)
    for kind in disease_ids(game): remove_effect(game, char, kind)
    remove_effect(game, char, FEEBLEMINDED)
    effects.recalc_ability(game, char, 1)
    effects.recalc_ability(game, char, 2)


def raise_dead(game, char):
    b = char.b
    was_dead, cannot = b[F['status']] in (DEAD, ANIMATED_STATUS), b[F['race']] < ELF_RACES_BELOW
    if (not was_dead or cannot) and not cure_anyway(game, char, 'cannot be raised' if cannot else 'is not dead.'): return
    if not pay(game, char, 'Raise Dead', 2750) or not was_dead or cannot: return
    locked_remove(game, char, ANIMATED, POISONED)
    b[F['hp']], b[F['status']], b[F['active']] = 1, 0, 1
    at = F['abilities'] + 2 * CON + 1
    if b[at]: b[at] -= 1
    loss = b[F['hp_max']] - b[F['hp_rolled']] if b[F['hp_max']] > b[F['hp_rolled']] else 0
    con = b[at]
    if con >= 14:
        bonus = 0
        for cls in range(8):
            level = b[F['levels'] + cls]
            if level > 0:
                if cls == FIGHTER: bonus = (bonus + (con - 14) * level) & 255
                elif con > 15: bonus = (bonus + level * 2) & 255
                else: bonus = (bonus + level) & 255
        if bonus: loss //= bonus
        if con < 17 or b[F['levels'] + FIGHTER] > 0 or b[F['levels'] + FIGHTER] > b[F['dual_threshold']]:
            b[F['hp_max']] = (b[F['hp_max']] - loss) & 255


def neutralize_poison(game, char):
    b = char.b
    poisoned = has_effect(char, POISONED) is not None
    if (poisoned or cure_anyway(game, char, 'is not poisoned.')) and pay(game, char, 'Neutralize Poison', 500) and poisoned:
        if b[F['hp']] == 0: b[F['hp']] = 1
        locked_remove(game, char, POISONED, SLOW_POISON, POISON_DAMAGE)
        b[F['active']], b[F['status']] = 1, 0


def remove_curse(game, char):
    cursed = any(item[I['cursed']] for item in char.items) or has_effect(char, CURSED) is not None
    if not (cursed or cure_anyway(game, char, 'is not cursed.')) or not pay(game, char, 'Remove Curse', 1750): return
    if has_effect(char, CURSED) is not None:
        shop.pause(game, shop.member_name(char) + ' is Cured')
        remove_effect(game, char, CURSED)
        shop.pause(game, shop.member_name(char) + ' is un-cursed')
        return
    item = next((item for item in char.items if item[I['cursed']]), None)
    if item is None: return
    item[I['readied']] = 0
    if item[I['powers'] + 2] > 0x7F:
        remove_effect(game, char, item[I['powers'] + 1])
        for ability in range(6): effects.recalc_ability(game, char, ability)
    shop.pause(game, shop.member_name(char) + ' has an item un-cursed')


def stone_to_flesh(game, char):
    b = char.b
    stoned = b[F['status']] == STONED
    if (stoned or cure_anyway(game, char, 'is not stoned.')) and pay(game, char, 'Stone to Flesh', 1000) and stoned:
        b[F['status']], b[F['active']], b[F['hp']] = 0, 1, 1


def heal_menu(game, char):
    labels = names(game)
    services = (lambda: cure_blindness(game, char), lambda: cure_disease(game, char), lambda: cure_wounds(game, char, labels[2], 50, 1, 0),
                lambda: cure_wounds(game, char, labels[3], 175, 2, 1), lambda: cure_wounds(game, char, labels[4], 300, 3, 3), lambda: heal(game, char),
                lambda: neutralize_poison(game, char), lambda: raise_dead(game, char), lambda: remove_curse(game, char), lambda: stone_to_flesh(game, char))
    while True:
        pick = shop.pick(game, Kind.LIST, shop.member_name(char) + ', how can we help you?', labels, window='2 4 38 15', menu='Heal',
                         title=shop.member_name(char) + ', how can we help you?')
        if pick is None: return
        services[pick]()


def run(game):
    s = game.s
    mode, s.mode = s.mode, shop.SHOP_TEMPLE
    s.treasure_money[:] = [0] * shop.COIN_TYPES
    try:
        while True:
            options = ('Heal', 'View', 'Take', 'Pool', 'Share', 'Appraise') if shop.has_money(s) else ('Heal', 'View', 'Pool', 'Appraise')
            index = shop.main_menu(game, options, Kind.MENU)
            if index is None:
                if not shop.has_money(s) or not shop.deal(game, 'Do you want to go back and retrieve your money?', LEFT_MONEY): return
                continue
            action = options[index]
            if action == 'Pool': shop.pool_money(s)
            elif action == 'Share': shop.share_money(s)
            else:
                char = s.party[s.sel]
                {'Heal': heal_menu, 'View': shop.view_items, 'Take': shop.take_menu, 'Appraise': shop.appraise}[action](game, char)
    finally:
        s.mode = mode
