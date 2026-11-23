from sm.titles.cok.effects import Roll
from . import rules
from .faults import BindingRequired

F = rules.F
HASTED = 39
AURA_IDS = frozenset((21, 45, 46, 49))
CONDITIONS = {
    1: (25, 32, 37), 2: (2, 64, 67, 68, 69, 74, 86, 88), 3: (64, 67, 68, 69, 74, 86),
    4: (7, 29, 34, 105, 108, 114, 115, 117), 5: (28, 41, 66, 103, 93, 112),
    6: (10, 17, 20, 28, 59, 63, 65, 71, 73, 75, 76, 83, 87, 98, 101),
    7: (3, 6, 27, 31, 57, 52, 53), 8: (89,),
    9: (18, 57, 59, 63, 71, 80, 87, 92, 95, 96, 97, 98, 99, 101, 116),
    10: (1, 7, 26, 33, 36, 49, 108, 118), 11: (4, 8, 13, 17, 30, 33, 45, 48, 57, 60),
    12: (8, 10, 17, 20, 33, 36, 45, 48, 49, 50, 54, 57, 94, 99),
    14: (81, 85, 78, 90, 100, 104, 106), 15: (11, 21, 30, 61, 70, 72, 79, 77, 84),
    16: (25, 32, 37, 47, 89), 17: (1, 11), 18: (9, 39, 42), 19: (11, 23), 20: (50, 54), 21: (35,)}
EMPTY = frozenset((5, 9, 12, 14, 16, 19, 24, 38, 40, 43, 44, 46, 51, 55, 56, 61, 82, 91, 102, 109, 113, 116, 119, 120))


def has(char, ident):
    return any(raw[0] == ident for raw in char.effects)


def has_effect(char, ident):
    return next((raw for raw in char.effects if raw[0] == ident), None)


def add_effect(char, ident, duration, strength, on_remove):
    char.effects.append(bytearray((ident, duration & 255, duration >> 8 & 255, strength & 255, int(on_remove), 0, 0, 0, 0)))


def remove_effect(game, char, ident, node=None):
    from .faults import BindingRequired
    node = node if node is not None else has_effect(char, ident)
    if node is None: return
    if node[4]: call_handler(game, char, ident, node, True)
    for at, held in enumerate(char.effects):
        if held is node:
            del char.effects[at]
            break
    if ident in (12, 38): recalc_ability(game, char, 0)
    elif ident == 14: recalc_ability(game, char, 5)


def _hp_zero_ids(game): return game.assets.table('hitPointEffectIds')


def nullify(roll, ident=0):
    if not ident or roll.effect == ident: roll.damage = roll.effect = 0


def aura_node(game, char, kind, roll):
    for carrier in game.s.chars() if roll.in_combat else game.s.party:
        node = has_effect(carrier, kind)
        if node is not None and (not roll.in_combat or roll.call('in_aura_range', carrier, char, 6 if kind == 49 else 1)):
            return node


def check_spell_resistance(game, char, roll):
    resistance = char.b[F['magic_resistance']]
    if resistance and (roll.effect or roll.element & 8) and (not roll.damage or roll.element & 8):
        level = roll.call('caster_level', roll.spell)
        if game.s.random(100) + 1 <= (resistance + (11 - level) * 5) & 255:
            roll.damage = 0
            if roll.effect not in (91, 82): roll.effect = 0


MEMO = ('effect', 'damage', 'element', 'dice_count')


def camp_roll(game, **values):
    from .effects_handlers import owner
    host = owner(game)
    memo = getattr(host, 'roll_memo', {})
    standing = dict(spell=getattr(game, 'current_spell', getattr(host, 'current_spell', 0)), multi_target=int(bool(getattr(game, 'area_spell', getattr(host, 'area_spell', False)))))
    return Roll(**{**{key: memo.get(key, 0) for key in MEMO}, **standing, **values})


def remember(game, roll=None, **values):
    from .effects_handlers import owner
    host = owner(game)
    memo = getattr(host, 'roll_memo', {})
    host.roll_memo = {**{key: memo.get(key, 0) if roll is None else getattr(roll, key) for key in MEMO}, **values}


def call_handler(game, char, ident, node, removed, roll=None):
    if roll is not None or getattr(game, 'battle', None) or getattr(game, 'handler_override_active', False):
        return _handle(game, char, ident, node, removed, roll)
    roll = camp_roll(game)
    result = _handle(game, char, ident, node, removed, roll)
    remember(game, roll)
    return result


def _handle(game, char, ident, node, removed, roll):
    from .effects_handlers import HANDLERS, grant_item_effect
    from .magic import EFFECT_HANDLERS
    if getattr(game, 'handler_override_active', False):
        return grant_item_effect(game, char, node, removed)
    roll = roll or (game.battle.context(char) if getattr(game, 'battle', None) else camp_roll(game))
    if ident in EMPTY: return
    if ident in EFFECT_HANDLERS: return EFFECT_HANDLERS[ident](game, char, node, removed, roll)
    if ident in HANDLERS:
        result = HANDLERS[ident](game, char, node, removed, roll)
        roll.damage &= 255
        return result
    if ident == 1: roll.morale += 5; roll.attack += 1
    elif ident in (8, 45):
        if roll.attacker is not None and roll.attacker.b[F['alignment']] in (2, 5, 8):
            roll.save += 2; roll.attack -= 2
    elif ident == 18:
        if game.s.random(100) + 1 <= 30:
            nullify(roll, 53); nullify(roll, 11)
    elif ident == 95:
        if game.s.random(100) + 1 <= 90:
            nullify(roll, 53); nullify(roll, 11)
    elif ident == 80: nullify(roll, 35)
    elif ident == 92: nullify(roll, 111)
    elif ident == 96: nullify(roll, 11); nullify(roll, 53)
    elif ident == 97: nullify(roll, 52)
    elif ident == 98:
        if roll.element & 2: nullify(roll)
    elif ident == 99:
        nullify(roll, 55); nullify(roll, 52)
        if roll.save_type == 0: roll.save = 100
    elif ident == 94:
        if roll.save_type in (0, 2, 4):
            con = char.b[F['abilities'] + 9]
            roll.save += next((bonus for low, high, bonus in ((4, 6, 1), (7, 10, 2), (11, 13, 3), (14, 17, 4), (18, 20, 5)) if low <= con <= high), 0)
    elif ident == 108:
        roll.damage = (roll.damage - 2) & 255
        roll.attack = ((roll.attack - 2) + 128) % 256 - 128
    elif ident == 49:
        step = 1 if char.b[F['side']] == (node[3] & 0x10) >> 4 else -1
        roll.save += step; roll.attack += step
    elif ident == 110:
        if removed: char.b[F['cure_ability']] = char.b[F['levels'] + 3] // 5 + 1
    elif ident in (7, 26, 103, 105, 106):
        if not roll.in_combat: return
        game.battle.weapon_effect(char, ident, node, removed, roll)
        roll.damage &= 255
    else: raise BindingRequired('Death Knights effect handler unverified: %d' % ident)


def trigger_condition(game, condition, char, roll):
    if condition in (6, 9): check_spell_resistance(game, char, roll)
    for ident in CONDITIONS.get(condition, ()):
        node = has_effect(char, ident)
        if node is None and ident in AURA_IDS: node = aura_node(game, char, ident, roll)
        if node is not None: call_handler(game, char, ident, node, False, roll)


def recalc_ability(game, char, stat):
    from .effects_ability import recalculate
    return recalculate(game, char, stat)


def recalc_stats(game, char):
    slots = rules.recalc_stats(char)
    zone = getattr(game.s, 'r1', None)
    if zone is not None: char.b[F['move']] = rules.movement(char, zone[0x372]) // 2
    return slots


def roll_dice(state, count, sides):
    return sum(state.random(sides) + 1 for _ in range(count)) & 255


def damage_dice(state, count, sides, roll):
    roll.dice_count = count
    return roll_dice(state, count, sides)


def restore_hp(char, amount, show_message=True, in_combat=False):
    if char.b[F['status']] not in (0, 1, 4, 5): return False
    if show_message and char.b[F['hp']] >= char.b[F['hp_max']]: return False
    char.b[F['hp']] = min((char.b[F['hp']] + amount) & 255, char.b[F['hp_max']])
    if not char.b[F['active']]:
        if char.b[F['status']] == 5: char.b[F['status']] = 4
        if not in_combat and char.b[F['status']] == 4:
            char.b[F['status']], char.b[F['active']] = 0, 1
    return True


def remove_with_message(game, char, ident, roll=None):
    from .effects_handlers import say
    node = has_effect(char, ident)
    if node is None: return False
    battle = getattr(game, 'battle', None)
    say(game, char, 'isCuredText', roll or (battle.context(char) if battle is not None else camp_roll(game)))
    remove_effect(game, char, ident, node)
    return True


def age_effects(game, char, minutes):
    nodes = char.effects
    if not nodes: return False
    boundary, predecessor, node = nodes[-1], nodes[0], nodes[0]
    running = False
    while node is not None:
        at = next((i for i, held in enumerate(nodes) if held is node), None)
        if at is None: return True
        last = node is boundary
        successor = nodes[at + 1] if at + 1 < len(nodes) else None
        duration = int.from_bytes(node[1:3], 'little')
        if duration and duration <= minutes:
            remove_effect(game, char, node[0], node)
            node = nodes[0] if nodes and predecessor is nodes[0] else successor
        else:
            if duration:
                node[1:3] = (duration - minutes).to_bytes(2, 'little')
                running = True
            node = successor
        at = next((i for i, held in enumerate(nodes) if held is node), len(nodes))
        if last:
            return running or any(held[1] or held[2] for held in nodes[at:])
        predecessor = nodes[max(0, at - 1)] if nodes else None
    return running


def advance(game, amount, unit=1, flags=None):
    from .camp import advance as clock_advance
    clock_advance(game, amount, unit)


def test():
    from .rules import character
    from .records import Character
    char = character(bytes(Character()))
    add_effect(char, 39, 0, 0, False)
    assert has(char, 39)
    remove_effect(None, char, 39)
    assert not char.effects
    from ._effects_test import test as check_handlers
    check_handlers()
