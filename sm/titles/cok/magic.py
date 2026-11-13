from collections import namedtuple
from functools import lru_cache

from . import camp, effects, rules
from .creation import F, choose, dice, yes_no
from .faults import BindingRequired
from .effects import I
from .records import Character, Item

CLERIC, FIGHTER, RANGER, MAGE, THIEF, KNIGHT = 0, 2, 4, 5, 6, 7
HUMAN, ANIMATED, OKAY = 6, 1, 0
SPELL_MASK, PENDING, MEMORY_SLOTS = 0x7F, 0x80, 58
ANTI_MAGIC_CELL, ROBE_CELL = 0xE5, 0x1F8
MISCAST, INVISIBLE, BLIND, CURSED, POISON_DAMAGE, SLOW_POISON, POISONED = 74, 25, 33, 36, 15, 22, 55
SLOWED, READ_MAGIC, CLERIC_SCROLL_SLOT, HAMMER_TYPE, HAMMER_NAME = 42, 16, 12, 6, 121
SCROLL_TYPES, SCROLL_FLAGS = (39, 40), {1: 0x20, 2: 0x10}
COMBAT_ONLY, SELF, CHOSEN, PARTY = 0, 1, 2, 4
LIST_PAGE = 18

Spell = namedtuple('Spell', 'id name cast_class level range_base range_per_level duration_base duration_per_level area targeting '
                            'save_effect save_type effect combat_ok cast_time ai_priority offensive ai_radius')


@lru_cache(maxsize=None)
def table():
    t = rules.tables()
    rows = []
    for index in range(107):
        row = [t.u8('spellTbl', index * 16 + column) for column in range(16)]
        row[0], row[1] = rules._s8(row[0]), rules._s8(row[1])
        length = t.u8('spellNames', index * 41)
        text = bytes(t.u8('spellNames', index * 41 + 1 + at) for at in range(length)).decode('cp437')
        rows.append(Spell(index + 1, text, *row))
    return tuple(rows)


def spell(spell_id):
    spell_id &= SPELL_MASK
    if not 1 <= spell_id <= 107:
        raise ValueError('spell id outside the table: %d' % spell_id)
    return table()[spell_id - 1]


def _levels(char):
    record = rules._view(Character, char.b)
    return rules._signed(record, 'levels'), rules._signed(record, 'former_levels'), rules._earlier_class_active(record)


def can_cast(char, spell_id, combat=False):
    kind, (levels, former, earlier) = spell(spell_id).cast_class, _levels(char)
    if kind in (0, 2):
        return camp.ability(char, 2) > 8 and (levels[CLERIC] > 0 or earlier and former[CLERIC] > 0 or
                                              levels[KNIGHT] > 5 or former[KNIGHT] > 5 and earlier)
    if kind == 1:
        return camp.ability(char, 2) > 8 and (levels[RANGER] > 6 or earlier and former[RANGER] > 6)
    if kind == 3:
        return camp.ability(char, 1) > 8 and (rules._s8(char.b[F['race']]) != HUMAN or not combat or rules.worn(char)[2] is None or
                                              levels[RANGER] > 8 or earlier and former[RANGER] > 8 and
                                              (levels[MAGE] > 0 or former[MAGE] > 0))
    return False


def castable(char, combat=False, pending=False):
    rows = []
    for held in camp.memory(char):
        if not (held > PENDING if pending else 0 < held < PENDING) or not can_cast(char, held, combat):
            continue
        held &= SPELL_MASK
        level = spell(held).level
        at = next((i for i, (other, _) in enumerate(rows) if spell(other).level > level or other == held), len(rows))
        if at < len(rows) and rows[at][0] == held:
            rows[at] = (held, rows[at][1] + 1)
        else:
            rows.insert(at, (held, 1))
    return rows


def list_start(levels, kept=-1, scroll=False, page=LIST_PAGE):
    rows, last = [], 0 if scroll else None
    for option, level in enumerate(levels):
        if level != last if scroll else last is None or level > last: rows.append(None)
        rows.append(option)
        last = level
    at = max(kept, 0)
    first = 0 if len(rows) <= page or at < page else at - page + 1
    at = min(at, len(rows) - 1)
    for _ in range(page):
        if rows[at] is not None: break
        at -= 1
        if at < first: at = first + page - 1
        at = min(at, len(rows) - 1)
    return rows[at], rows


def caster_level(game, caster, spell_id):
    kind = lambda: spell(spell_id).cast_class if spell_id & SPELL_MASK else rules._s8(rules.tables().u8('spellTbl', -16))
    if getattr(game, 'using_item', False) and kind() != 4: return 6
    levels, former, earlier = _levels(caster)
    if not levels[CLERIC] and not levels[MAGE] and levels[KNIGHT] < 9 and levels[RANGER] < 8:
        return 6
    total = lambda cls, less=0: levels[cls] + former[cls] * earlier - less
    kind = kind()
    if kind in (0, 2):
        return max(total(CLERIC), total(KNIGHT, 8)) & 255
    if kind == 1:
        return max(total(RANGER, 7), 0)
    if kind == 3:
        primary = total(MAGE)
        robe = caster.b[F['robe_order']]
        if levels[MAGE] > 0 and robe > 0:
            moon = game.s.r0[ROBE_CELL + robe]
            primary += -1 if moon == 0 else 1 if moon == 2 and levels[MAGE] > 5 else 0
        return max(primary, total(RANGER, 8)) & 255
    return 12


def duration(game, caster, row):
    s, fixed = game.s, {26: 3780, 67: 1440}
    if row.id in fixed: return fixed[row.id]
    if row.id == 40: return dice(s, 1, 6) * 10
    if row.id in (57, 61): return dice(s, 5, 4)
    if row.id == 59: return dice(s, 1, 4) * 10 + 40
    if row.id == 63: return (dice(s, 2, 10) if s.mode == 5 else dice(s, 1, 10) + 10) * 10
    return row.duration_base + row.duration_per_level * caster_level(game, caster, row.id) & 0xFFFF


def forget(char, spell_id):
    base = F['memorized']
    for at in range(base, base + MEMORY_SLOTS):
        if char.b[at] == spell_id:
            char.b[at] = 0
            return


def _find(char, effect_id):
    return next((at for at, effect in enumerate(char.effects) if effect[0] == effect_id), None)


def _remove(game, char, effect_id):
    if effects.has_effect(char, effect_id) is None: return False
    effects.remove_effect(game, char, effect_id)
    return True


def _say(game, char, text):
    if getattr(game, 'battle', None) is not None:
        game.battle.message(camp.name(char) + ' ' + text)
        return
    camp.ack(game, camp.name(char) + ' ' + text)


def _roll(game, caster, row, effect_id=None):
    battle = getattr(game, 'battle', None)
    if battle is not None:
        values={} if effect_id is None else dict(effect=effect_id)
        roll = battle.context(caster, spell=row.id, multi_target=battle.data.get('multi_target', 0), **values)
        roll.services['caster_level'] = lambda spell_id: caster_level(game, caster, spell_id)
        return roll
    return effects.Roll(effect=effect_id or 0, spell=row.id, services={'caster_level': lambda spell_id: caster_level(game, caster, spell_id),
                                                                       'message': lambda who, text: effects.window_message(game, who, text)})


def _damage_dice(game, count, sides):
    battle = getattr(game, 'battle', None)
    if battle is not None: battle.data.setdefault('roll', {})['dice_count'] = count
    return dice(game.s, count, sides)


def _saving_throw(game, caster, target, row, kind, bonus=0, element=0):
    if getattr(game, 'battle', None) is not None: return game.battle.save(game.battle.index(target), kind, bonus, element)
    natural = dice(game.s, 1, 20)
    if natural in (1, 20): return natural == 20
    robe = target.b[F['robe_order']]
    if rules._s8(target.b[F['levels'] + MAGE]) > 0 and robe > 0:
        moon = game.s.r0[ROBE_CELL + robe]
        bonus += -1 if moon == 0 else 1 if moon == 2 else 0
    roll = _roll(game, caster, row)
    roll.save, roll.save_type = natural + rules._s8(target.b[F['save_bonus']]) + bonus & 255, kind
    effects.trigger_condition(game, 12, target, roll)
    return target.b[F['saves'] + kind] <= roll.save


def _add_with_message(game, caster, target, row, effect_id, minutes, strength, on_remove, text, saved=False, negates=0):
    roll = _roll(game, caster, row, effect_id)
    effects.trigger_condition(game, 9, target, roll)
    if getattr(game, 'battle', None) is not None: game.battle.remember_roll(roll)
    if not roll.effect or saved and negates == 1:
        _say(game, target, 'is Unaffected')
        return
    node = effects.has_effect(target, effect_id)
    if node is not None and node[1] | node[2] << 8:
        effects.remove_effect(game, target, effect_id, node)
    effects.add_effect(target, effect_id, minutes, strength, on_remove)
    if text: _say(game, target, text)


def _resolve(game, caster, targets, row, strength, on_remove, text, damage=0, element=0):
    battle = getattr(game, 'battle', None)
    if battle is None and (row.save_effect or row.range_base == 255 or damage):
        raise BindingRequired('Champions spell save or attack path not bound outside combat: spell %d' % row.id)
    strength = strength or caster_level(game, caster, row.id)
    if battle is not None: battle.data.setdefault('roll',{})['element']=element if damage else 0
    for target in targets:
        if target is None: continue
        saved = bool(row.save_effect) and _saving_throw(game, caster, target, row, row.save_type, element=element if damage else 0)
        if row.range_base == 255 and not battle.touch(caster, target, row): damage, saved = 0, True
        if damage:
            roll = _roll(game, caster, row)
            roll.damage, roll.element = damage & 255, element
            battle.spell_damage(target, roll, row.save_effect, saved)
        if row.effect:
            _add_with_message(game, caster, target, row, row.effect, duration(game, caster, row), strength, on_remove, text, saved, row.save_effect)
    if battle is not None and targets: battle.data['roll']['element']=0


def _plain(text):
    return lambda game, caster, targets, row: _resolve(game, caster, targets, row, 0, False, text)


def _bless(game, caster, targets, row):
    side = caster.b[F['side']] ^ (row.id == 2)
    battle = getattr(game, 'battle', None)
    kept = [t for t in targets if t is not None and t.b[F['side']] == side and
            (battle is None or row.id == 2 or not battle.targets(battle.index(t), 1))]
    _resolve(game, caster, kept, row, 0, False, 'is Cursed' if row.id == 2 else 'is Blessed')


def _prayer(game, caster, targets, row):
    strength = caster_level(game, caster, row.id) + rules._s8(caster.b[F['side']]) * 16 & 255
    _resolve(game, caster, targets, row, strength, False, 'is praying')


def _mirror(game, caster, targets, row):
    strength = dice(game.s, 1, 4) << 4 & 255 | caster_level(game, caster, row.id)
    _resolve(game, caster, targets, row, strength, False, 'is duplicated')


def _cure(count, sides, bonus):
    def apply(game, caster, targets, row):
        if not targets: return
        extra = dice(game.s, 1, 8) if caster.b[F['deity']] == 4 else 0
        amount = dice(game.s, count, sides) + bonus + extra & 255
        target = targets[0]
        battle = getattr(game, 'battle', None)
        healed = battle.heal(target, amount) if battle is not None else camp.restore_hit_points(game, target, amount)
        if healed:
            _say(game, target, 'is fully healed' if target.b[F['hp']] == target.b[F['hp_max']] else 'is partially healed')
    return apply


def _cured_of(game, target, effect_id):
    node = effects.has_effect(target, effect_id)
    if node is None: return False
    _say(game, target, 'is Cured')
    effects.remove_effect(game, target, effect_id, node)
    return True


def _cure_blindness(game, caster, targets, row):
    if _cured_of(game, targets[0], BLIND): _say(game, targets[0], 'can see')


def _cure_disease(game, caster, targets, row):
    target = targets[0]
    game.effect_busy = True
    _cured_of(game, target, 34)
    if _cured_of(game, target, 43):
        _remove(game, target, 44)
        _remove(game, target, 31)
        effects.recalc_ability(game, target, effects.STR)
    game.effect_busy = False


def _awaken(target):
    if target.b[F['hp']] == 0: target.b[F['hp']] = 1
    target.b[F['active']] = 1
    target.b[F['status']] = OKAY


def _slow_poison(game, caster, targets, row):
    target = targets[0]
    if target.b[F['status']] != ANIMATED and effects.has_effect(target, POISONED) is not None:
        _awaken(target)
        _resolve(game, caster, targets, row, 255, True, 'is affected')
        effects.add_effect(target, POISON_DAMAGE, 10, 255, True)


def _neutralize(game, caster, targets, row):
    target = targets[0]
    if target.b[F['status']] == ANIMATED: return
    if effects.has_effect(target, POISONED) is None:
        _say(game, target, 'is unaffected')
        return
    if target.b[F['hp']] == 0: target.b[F['hp']] = 1
    game.effect_busy = True
    for effect_id in (POISONED, SLOW_POISON, POISON_DAMAGE): _remove(game, target, effect_id)
    game.effect_busy = False
    _say(game, target, 'is unpoisoned')
    target.b[F['active']] = 1
    target.b[F['status']] = OKAY


def _remove_curse(game, caster, targets, row):
    target = targets[0]
    if _cured_of(game, target, CURSED):
        _say(game, target, 'is un-cursed')
        return
    for raw in target.items:
        if raw[I['cursed']]:
            raw[I['readied']] = 0
            if raw[I['powers'] + 2] > SPELL_MASK:
                effects.remove_effect(game, target, raw[I['powers'] + 1])
                for ability in range(6): effects.recalc_ability(game, target, ability)
            _say(game, target, 'has an item un-cursed')
            return


def _new_strength_applies(target, value, extra):
    return value > target.b[F['abilities']] or value == 18 and extra > target.b[F['strength_extra_base']]


ENLARGED = {2: (18, 1), 3: (18, 51), 4: (18, 76), 5: (18, 91), 6: (18, 100), 7: (19, 0), 8: (20, 0), 9: (21, 0), 10: (22, 0), 11: (22, 0)}


def _enlarge(game, caster, targets, row):
    target = targets[0]
    value, extra = ENLARGED.get(caster_level(game, caster, row.id), (18, 0))
    if not _new_strength_applies(target, value, extra):
        _say(game, target, 'is unaffected')
        return
    _say(game, target, 'is stronger')
    effects.add_effect(target, 12, duration(game, caster, row), extra + 1 if value == 18 else value + 100, True)
    effects.recalc_ability(game, target, effects.STR)


def _reduce(game, caster, targets, row):
    target = targets[0]
    if not _saving_throw(game, caster, target, row, 4) and effects.has_effect(target, 12) is not None:
        effects.remove_effect(game, target, 12)
        effects.recalc_ability(game, target, effects.STR)
        _say(game, target, 'has been reduced')


def _friends(game, caster, targets, row):
    _resolve(game, caster, targets, row, dice(game.s, 2, 4), True, 'is friendly')
    effects.recalc_ability(game, caster, effects.CHA)


def _strength(game, caster, targets, row):
    target, s = targets[0], game.s
    levels, former, _ = _levels(target)
    threshold = rules._s8(target.b[F['dual_threshold']])
    has = lambda cls: levels[cls] > 0 or former[cls] > threshold
    gain = None
    if has(MAGE): gain = dice(s, 1, 4)
    if has(CLERIC) or has(THIEF): gain = dice(s, 1, 6)
    if has(FIGHTER): gain = dice(s, 1, 8)
    if gain is None:
        raise BindingRequired('Strength on a target with no mage, cleric, thief or fighter levels: the original reads an unset local')
    value, extra = target.b[F['abilities'] + 1] + gain & 255, 0
    if value > 18:
        if has(FIGHTER) or has(KNIGHT) or has(RANGER):
            extra = min(target.b[F['strength_extra']] + (value - 18) * 10 & 255, 100)
        value = 18
    if _new_strength_applies(target, value, extra):
        effects.add_effect(target, 38, duration(game, caster, row), gain + 100, True)
        effects.recalc_ability(game, target, effects.STR)


def _hammer(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, True, '')
    if targets: ensure_hammer(game, targets[0])


def ensure_hammer(game, target):
    held = any(raw[I['type']] == HAMMER_TYPE and raw[I['name_ids'] + 2] == HAMMER_NAME for raw in target.items)
    if not held and target.b[F['item_count']] < 16:
        item = bytearray(Item.SIZE)
        item[I['type']], item[I['name_ids'] + 1], item[I['name_ids'] + 2] = HAMMER_TYPE, HAMMER_TYPE, HAMMER_NAME
        item[I['bonus']], item[I['powers'] + 1], item[I['powers'] + 2] = 1, 23, 0x80
        target.items.append(item)
        _say(game, target, 'Gains an item')
    rules.recalc_stats(target)


def _haste(game, caster, targets, row):
    side, reach, kept = caster.b[F['side']], caster_level(game, caster, row.id), []
    for target in targets:
        if target.b[F['side']] == side and reach > 0:
            reach -= 1
            kept.append(None if _cured_of(game, target, SLOWED) else target)
        else:
            kept.append(None)
    _resolve(game, caster, kept, row, 0, False, 'is Hasted')
    for target in kept:
        if target is not None: effects.trigger_condition(game, 18, target, _roll(game, caster, row))


def _dispel(game, caster, targets, row):
    level = caster_level(game, caster, row.id)
    def succeeds(other):
        chance = (level-other)*5+50 if level>other else 50-(other-level)*2
        return dice(game.s,1,100)<=chance&255
    for _ in targets:
        target, removed = targets[0], False
        for node in list(target.effects):
            if not any(node is effect for effect in target.effects) or node[3]>=255: continue
            if succeeds(node[3]&15):
                effects.remove_effect(game,target,node[0],node); removed=True
        if removed: _say(game,target,'is affected')
    battle = getattr(game,'battle',None)
    if battle is not None:
        battle.data['multi_target']=1
        battle.dispel_clouds(caster,succeeds)


def _fire_shield(game, caster, targets, row):
    if caster.b[F['auto_combat']]: hot = dice(game.s, 1, 10) > 5
    else: hot = game.ask(camp.Kind.CONFIRM.value, ('Hot', 'Cold'), prompt='flame type: ') == 0
    _add_with_message(game, caster, caster, row, 50 if hot else 54, duration(game, caster, row), 0, False, 'is protected' if hot else '')
    _add_with_message(game, caster, caster, row, 112, duration(game, caster, row), 0, False, '')


def _nothing(game, caster, targets, row):
    pass


def _missile(game, caster, targets, row):
    count = 2 if row.id == 65 else (caster_level(game, caster, row.id) + 1 & 255) // 2
    _resolve(game, caster, targets, row, 0, False, '', count + _damage_dice(game, count, 4), 8)


def _burning(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, '', caster_level(game, caster, row.id), 9)


def _shock(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, '', _damage_dice(game, 1, 8) + caster_level(game, caster, row.id), 12)


def _sleep(game, caster, targets, row):
    game.battle.data['multi_target'] = 1
    budget, kept = dice(game.s, 4, 4), []
    for target in targets:
        level = target.b[F['highest_level']]
        cost = (1, 1, 2, 4, 6)[level] if level < 5 else 10 if level == 5 and target.b[F['race']] == 7 else 20
        if target.b[F['status']] != ANIMATED and effects.has_effect(target, 53) is None and budget >= cost:
            budget -= cost
            kept.append(target)
    _resolve(game, caster, kept, row, 0, False, 'falls asleep')


def _hold(game, caster, targets, row):
    bonus = (-2 if row.id == 23 else -3) if len(targets) == 1 else -1 if len(targets) == 2 else 0
    for target in reversed(targets):
        saved = _saving_throw(game, caster, target, row, row.save_type, bonus)
        if row.id in (23, 49) and target.b[F['race']] == 7: saved = True
        _add_with_message(game, caster, target, row, row.effect, duration(game, caster, row),
                          caster_level(game, caster, row.id), False, 'is held', saved, row.save_effect)


def _charm(game, caster, targets, row):
    if not targets: return
    target = targets[0]
    if target.b[F['creature_type']] > 1 or target.b[F['dimensions']] > 1:
        _say(game, target, 'is unaffected')
        return
    _resolve(game, caster, targets, row, caster.b[F['side']] * 128 + caster_level(game, caster, row.id), True, 'is charmed')
    node = effects.has_effect(target, 11)
    if node is not None: effects.call_handler(game, target, 11, node, False, _roll(game, caster, row))


def _fireball(game, caster, targets, row):
    battle = game.battle
    level = dice(game.s, 1, 3) * 2 + 1 if row.id == 64 else caster_level(game, caster, row.id)
    battle.data['multi_target'] = 1
    if not game.vm.is3d(): targets = [battle.chars[i] for i in battle.area_targets(*battle.data['aim'], 2)]
    _resolve(game, caster, targets, row, 0, False, '', _damage_dice(game, level, 6), 9)


def _lightning(game, caster, targets, row):
    game.battle.lightning(game, caster, row, dice(game.s, caster_level(game, caster, row.id), 6))


def _ice_storm(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, '', _damage_dice(game, 3, 10), 10)


def _cloud(game, caster, targets, row):
    game.battle.cloud(caster, caster_level(game, caster, row.id))


def _cause_wounds(game, caster, targets, row):
    count, bonus = (1, 0) if row.id == 4 else (2, 3 if caster.b[F['deity']] == 4 else 1)
    _resolve(game, caster, targets, row, 0, False, '', _damage_dice(game, count, 8) + bonus, 8)


HANDLERS = {1: _bless, 105: _bless, 42: _prayer, 32: _mirror, 12: _enlarge, 13: _reduce, 14: _friends, 35: _strength, 28: _hammer,
            48: _haste, 41: _dispel, 46: _dispel, 85: _fire_shield, 3: _cure(1, 8, 0), 58: _cure(2, 8, 1),
            37: _cure_blindness, 39: _cure_disease, 26: _slow_poison, 67: _neutralize,
            43: _remove_curse, 89: _remove_curse, 104: _remove_curse,
            8: _plain('is cold-resistant'), 24: _plain('is fire resistant'), 19: _plain('is shielded'),
            30: _plain('is invisible'), 50: _plain('is invisible'), 88: _plain('is protected')}
HANDLERS.update((spell_id, _plain('is affected')) for spell_id in (5, 11, 18, 22, 29, 77, 103))
HANDLERS.update((spell_id, _plain('is protected')) for spell_id in (6, 7, 16, 17, 52, 53, 54, 69, 101))
HANDLERS.update((spell_id, _nothing) for spell_id in (36, 56, 71, 75, 80, 90))
HANDLERS.update({2: _bless, 4: _cause_wounds, 9: _burning, 10: _charm, 106: _charm,
                 15: _missile, 20: _shock, 21: _sleep, 23: _hold, 49: _hold,
                 25: _plain('is silenced'), 102: _plain('is silenced'), 33: _plain('is weakened'),
                 34: _cloud, 38: _plain('is blind'), 40: lambda game, caster, targets, row: _resolve(game, caster, targets, row, 0, True, 'is diseased'),
                 44: _plain('has been cursed!'), 45: _plain('is blinking'), 47: _fireball, 51: _lightning,
                 64: _fireball, 65: _missile, 66: _cause_wounds, 87: _ice_storm})


def _haste_slow(cure_id, enemy, text):
    def apply(game, caster, targets, row):
        side, reach, kept = caster.b[F['side']] ^ enemy, caster_level(game, caster, row.id), []
        for target in targets:
            if target.b[F['side']] == side and reach > 0:
                reach -= 1
                kept.append(None if _cured_of(game, target, cure_id) else target)
            else:
                kept.append(None)
        if getattr(game, 'battle', None) is not None: game.battle.data['multi_target'] = 1
        _resolve(game, caster, kept, row, 0, False, text)
        for target in kept:
            if target is not None: effects.trigger_condition(game, 18, target, _roll(game, caster, row))
    return apply


def _apply_effect(text, bonus=0):
    def apply(game, caster, targets, row):
        for at in range(len(targets) - 1, -1, -1):
            target = targets[at]
            if target is None: continue
            if row.id in (79, 81) and at == len(targets) - 1: saved, negates = True, 1
            else: saved, negates = _saving_throw(game, caster, target, row, row.save_type, bonus), row.save_effect
            if row.id in (23, 49) and target.b[F['race']] == 7: saved = True
            _add_with_message(game, caster, target, row, row.effect, duration(game, caster, row),
                              caster_level(game, caster, row.id), False, text, saved, negates)
    return apply


def _charm_monsters(game, caster, targets, row):
    _apply_effect('is charmed')(game, caster, targets, row)
    for target in targets:
        node = effects.has_effect(target, 11)
        if node is not None: effects.call_handler(game, target, 11, node, False, _roll(game, caster, row))


def _confusion(game, caster, targets, row):
    limit = dice(game.s, 2, 8)
    for target in targets[:limit]:
        if target is None: continue
        saved = _saving_throw(game, caster, target, row, 4)
        _add_with_message(game, caster, target, row, 35, duration(game, caster, spell(82)), 0, False, 'is confused', saved, 1)


def _sticks(game, caster, targets, row):
    target = targets[0]
    if rules._s8(target.b[F['highest_level']]) < 6:
        _resolve(game, caster, targets, row, caster_level(game, caster, row.id), False, '', 0, 8)
        node = effects.has_effect(target, 3)
        if node is not None: effects.call_handler(game, target, 3, node, False, _roll(game, caster, row))
    else: _say(game, target, 'smashes them flat')


def _poison(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, '', 0, 8)
    battle = game.battle
    j = battle.record(battle.index(caster))['target']
    if j < 0: return
    roll = _roll(game, caster, row, 64)
    battle.trigger(9, j, roll)
    if roll.effect == 64: battle.weapon_effect(caster, 64, None, False, roll)


def _snake_charm(game, caster, targets, row):
    budget, kept = caster.b[F['hp']], []
    for target in game.s.chars():
        if target.b[F['creature_type']] & 0x10 and target.b[F['active']] and effects.has_effect(target, 51) is None and budget >= target.b[F['hp']]:
            budget -= target.b[F['hp']]
            kept.append(target)
    _resolve(game, caster, kept, row, 0, False, 'is charmed')


def _fear(game, caster, targets, row):
    battle = game.battle
    i = battle.index(caster)
    for j in battle.cone(i, battle.data['aim'], 3, 6):
        if not battle.save(j, 4):
            battle.add_with_message(j, 111, duration(game, caster, spell(84)), 0, True, 'runs in terror')
            battle.flee_control(j)
        else: _say(game, battle.chars[j], 'is unaffected')


def _fumble(game, caster, targets, row):
    target = targets[0]
    battle = game.battle
    j = battle.index(target)
    kind, text = (27, 'is clumsy') if not battle.save(j, 4, element=0x40) else (SLOWED, 'is slowed')
    battle.add_with_message(j, kind, duration(game, caster, spell(86)), 0, False, text)
    if kind == 27 and effects.has_effect(target, 27) is not None: battle.end(j)
    _resolve(game, caster, targets, row, 0, True, 'is clumsy')


def _dimension_door(game, caster, targets, row):
    battle = game.battle
    i = battle.index(caster)
    r = battle.record(i)
    r['x'], r['y'] = battle.data['aim']
    occupant, tile = battle.probe(i)
    if occupant >= 0 or not tile or battle.terrain(tile) >= 255: r['size'] = 0
    _say(game, caster, 'teleports')


def _speed(game, caster, targets, row):
    if not _cured_of(game, targets[0], SLOWED): _resolve(game, caster, targets, row, 0, False, 'is Speedy')


def _giant_strength(game, caster, targets, row):
    target = targets[0]
    if _new_strength_applies(target, 21, 0): _say(game, target, 'is stronger')
    effects.add_effect(target, 113, dice(game.s, 1, 4) * 10 + 40, 121, True)
    effects.recalc_ability(game, target, effects.STR)


def _javelin(game, caster, targets, row):
    first = dice(game.s, 1, 6) + 20
    game.battle.lightning(game, caster, row, 20, length=3, save=4, element=4, bounce=False, first=first)


def _heal_self(game, caster, targets, row):
    amount = dice(game.s, 2, 4) + 2
    battle = getattr(game, 'battle', None)
    healed = battle.heal(targets[0], amount) if battle is not None else camp.restore_hit_points(game, targets[0], amount)
    if healed: _say(game, targets[0], 'is Healed')


HANDLERS.update({55: _haste_slow(39, 1, 'is Slowed'), 81: _charm_monsters, 82: _confusion, 70: _sticks, 68: _poison, 27: _snake_charm,
                 84: _fear, 86: _fumble, 83: _dimension_door, 94: _hold, 100: _plain('has been cursed!'), 107: _burning,
                 57: _speed, 59: _giant_strength, 60: _javelin, 61: _plain('is paralyzed'), 62: _heal_self, 63: _plain('is invisible'),
                 95: _plain(''), 96: _plain(''), 97: _plain(''), 99: _heal_self, 31: _plain('Knock-Knock')})
HANDLERS.update((spell_id, _nothing) for spell_id in (72, 73, 74, 76, 78, 79, 91, 92, 93, 98))


def _targets(game, caster, row, target):
    party = game.s.party
    if row.targeting == SELF: return [caster]
    if row.targeting == PARTY: return list(party)
    if row.targeting != CHOSEN: return None
    if target is not None: return [target]
    pick = choose(game, camp.Kind.WHO, 'Cast Spell on whom', [camp.name(char) for char in party], spell=row.name)
    return None if pick is None else [party[pick]]


def _cast_blocked(game, caster):
    if game.s.r0[ANTI_MAGIC_CELL] > 0:
        _say(game, caster, 'cannot cast spells in this area')
        return True
    if caster.b[F['status']] == ANIMATED or not caster.b[F['active']]:
        _say(game, caster, 'is in no condition to cast any spells')
        return True
    return False


def cast_spell(game, caster, spell_id, announce=True, target=None):
    s, row = game.s, spell(spell_id)
    going = row.targeting != COMBAT_ONLY
    if going and row.id not in HANDLERS:
        raise BindingRequired('Champions spell not bound outside combat: %d %s' % (row.id, row.name))
    if not going:
        camp.ack(game, row.name + " can't be cast here...")
        if yes_no(game, camp.Kind.CONFIRM, 'Lose it? ', spell=row.name):
            forget(caster, row.id)
    if effects.has_effect(caster, MISCAST) is not None and dice(s, 1, 2) == 1:
        _say(game, caster, 'miscasts ' + row.name)
        return False
    if not going:
        return False
    if announce: _say(game, caster, 'casts ' + row.name)
    targets = _targets(game, caster, row, target)
    if targets is None:
        return False
    while _remove(game, caster, INVISIBLE):
        pass
    forget(caster, row.id)
    HANDLERS[row.id](game, caster, targets, row)
    return True


def cast(game, caster, spell_id, target=None):
    if _cast_blocked(game, caster):
        return False
    offered = castable(caster)
    if not offered:
        _say(game, caster, 'has no spells memorized')
        return False
    if spell(spell_id).id not in [held for held, _ in offered]:
        return False
    return cast_spell(game, caster, spell_id, target=target)


def cast_menu(game, caster):
    if _cast_blocked(game, caster): return
    kept = -1
    while True:
        offered = castable(caster)
        if not offered:
            _say(game, caster, 'has no spells memorized')
            return
        labels = [spell(held).name + (' (%d)' % count if count > 1 else '') for held, count in offered]
        levels = tuple(spell(held).level for held, _ in offered)
        start, rows = list_start(levels, kept)
        pick = choose(game, camp.Kind.SPELL, 'Cast', labels, start=start, levels=levels)
        if pick is None: return
        kept = rows.index(pick)
        cast(game, caster, offered[pick][0])


def _readable(raw):
    return raw[I['type']] in SCROLL_TYPES


def _spell_bytes(raw):
    return range(I['powers'], I['powers'] + 3)


def reset_scribe(char):
    for raw in char.items:
        if _readable(raw):
            for at in _spell_bytes(raw): raw[at] &= SPELL_MASK


def _identify(char, raw):
    levels, former, _ = _levels(char)
    cleric = levels[CLERIC] > 0 or former[CLERIC] > rules._s8(char.b[F['dual_threshold']])
    if effects.has_effect(char, READ_MAGIC) is not None or cleric and rules.tables().base_item(raw[I['type']])[rules.SLOT] == CLERIC_SCROLL_SLOT:
        raw[I['unidentified']] &= 0xF8


def scroll_spells(char, pending):
    rows, flag = [], SCROLL_FLAGS.get(char.b[F['robe_order']], 0)
    for raw in char.items:
        if _readable(raw) and raw[I['unidentified']] & flag:
            _identify(char, raw)
            if not raw[I['unidentified']] & 7:
                rows += [raw[at] for at in _spell_bytes(raw) if (raw[at] > PENDING if pending else raw[at] > 0)]
    return rows


def _pending_bytes(char):
    return [raw[at] for raw in char.items if _readable(raw) for at in _spell_bytes(raw) if raw[at] > PENDING]


def _names(rows):
    return ', '.join(spell(value).name for value in rows)


def scroll_line(value):
    return (' *' if value > SPELL_MASK else '  ') + spell(value).name


def show_list(game, title, values):
    choose(game, camp.Kind.SPELL, '', [], title=title, lines=tuple(map(scroll_line, values)), levels=tuple(spell(v).level for v in values))


def _mark_for_scribing(char, spell_id):
    for raw in char.items:
        for at in _spell_bytes(raw):
            if raw[at] == spell_id:
                raw[at] |= PENDING
                return


def scribe(game, caster):
    if caster.b[F['status']] == ANIMATED or not caster.b[F['active']]:
        _say(game, caster, 'is in no condition to scribe any scrolls')
        return
    pending = scroll_spells(caster, True)
    if pending:
        show_list(game, 'to Scribe', pending)
        if yes_no(game, camp.Kind.CONFIRM, 'Scribe These Spells? ', spells=_names(pending)): return
        reset_scribe(caster)
    shown, kept = False, -1
    while True:
        rows = scroll_spells(caster, False)
        if not rows:
            _say(game, caster, 'has no copyable scrolls')
            break
        shown = True
        levels = tuple(spell(value).level for value in rows)
        start, drawn = list_start(levels, kept, scroll=True)
        pick = choose(game, camp.Kind.SPELL, 'Scribe', [scroll_line(value) for value in rows], start=start, levels=levels)
        if pick is None: break
        kept = drawn.index(pick)
        row = spell(rows[pick])
        if caster.b[F['known_spells'] + row.id - 1]:
            camp.ack(game, 'You already know that spell')
        elif row.id in [value & SPELL_MASK for value in _pending_bytes(caster)]:
            camp.ack(game, 'You are already scibing that spell')
        elif camp.slot_count(caster, row.cast_class, row.level) > 0:
            _mark_for_scribing(caster, row.id)
        else:
            camp.ack(game, 'You can not scribe that spell.')
    if shown:
        pending = scroll_spells(caster, True)
        if pending:
            show_list(game, 'to Scribe', pending)
            if not yes_no(game, camp.Kind.CONFIRM, 'Scribe these spells? ', spells=_names(pending)): reset_scribe(caster)


def scribed_levels(char):
    levels = [spell(value).level for value in _pending_bytes(char)]
    return max(levels, default=0), sum(levels)


def _used_up(char, raw, spell_id):
    slots = [at for at in _spell_bytes(raw) if raw[at] & SPELL_MASK == spell_id]
    if not slots: return
    raw[slots[-1]] = 0
    raw[I['name_ids']] = raw[I['name_ids']] - 1 & 255
    if raw[I['name_ids']] < 100:
        for at, item in enumerate(char.items):
            if item is raw:
                del char.items[at]
                return


def finish_scribe(game, char, done):
    level = 0
    for raw in list(char.items):
        if level or not _readable(raw): continue
        for at in _spell_bytes(raw):
            if not level and raw[at] > PENDING:
                row = spell(raw[at])
                if done:
                    level = row.level
                else:
                    char.b[F['known_spells'] + row.id - 1] = 1
                    _used_up(char, raw, row.id)
                    _say(game, char, 'has scribed ' + row.name)
                    done = True
    return level, done
