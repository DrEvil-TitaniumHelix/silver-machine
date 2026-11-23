from collections import namedtuple
from functools import lru_cache

from sm.titles.ssb.units.combat import line
from . import camp, rules
from .creation import choose, yes_no, dice
from .faults import BindingRequired
from .records import Item
from .magic_lists import (spell_known, generate_list, spell_menu, learnable, learn, readable,
                          identify_scroll, scroll_spells, remove_scroll_spell)
from .magic_study import scribe, reset_scribe, prep_minutes, finish_scribe, finish_memorize

CLERIC, FIGHTER, PALADIN, RANGER, MAGE, THIEF, KNIGHT = 0, 2, 3, 4, 5, 6, 7
HUMAN, MONSTER = 6, 7
F, PENDING, MASK = camp.F, camp.PENDING, camp.SPELL_MASK
SCROLLS = 39, 40
STORED_FIREBALL = 78

Spell = namedtuple('Spell', 'id name cast_class level range range_per_level duration duration_per_level targeting '
                            'camp_target save_effect save_type effect combat_ok cast_time ai_priority hostile hostile_tail')


@lru_cache(maxsize=4)
def _table(assets):
    raw, names = assets.table('spellTable'), assets.names('spellNames')
    s8 = lambda v: v - 256 if v > 127 else v
    return tuple(Spell(i + 1, names[i], s8(raw[i * 16]), s8(raw[i * 16 + 1]), *raw[i * 16 + 2:i * 16 + 16]) for i in range(114))


def spell(game, ident):
    ident &= MASK
    if not 1 <= ident <= 114: raise ValueError('spell id outside the table: %d' % ident)
    return _table(game.assets)[ident - 1]


def lv(char, cls): return rules._s8(char.b[F['levels'] + cls])


def can_cast(game, char, ident, combat=False):
    kind = spell(game, ident).cast_class
    if kind in (0, 2): return camp.ability(char, 2) > 8 and (lv(char, CLERIC) > 0 or lv(char, KNIGHT) > 5 or lv(char, PALADIN) > 8)
    if kind == 1: return camp.ability(char, 2) > 8 and lv(char, RANGER) > 7
    if kind == 3:
        shielded = rules._s8(char.b[F['race']]) == HUMAN and rules.worn(char)[2] is not None and lv(char, RANGER) <= 8 and combat
        return camp.ability(char, 1) > 8 and not shielded and (lv(char, RANGER) > 8 or lv(char, MAGE) > 0)
    return False


def castable(game, char, combat=False, pending=False):
    return [(entry.ident, entry.copies) for entry in generate_list(game, char, 5 if pending else 0, combat=combat)]


def caster_level(game, caster, ident):
    row = spell(game, ident) if ident & MASK else None
    if getattr(game, 'using_item', False) and (row is None or row.cast_class != 4): return 6
    if not lv(caster, CLERIC) and not lv(caster, MAGE) and lv(caster, KNIGHT) < 9 and lv(caster, RANGER) < 8: level = 6
    else:
        kind = row.cast_class if row else 0
        if kind in (0, 2): level = max(lv(caster, CLERIC), lv(caster, KNIGHT))
        elif kind == 1: level = lv(caster, RANGER) - 7 if lv(caster, RANGER) > 7 else 0
        elif kind == 3:
            level = caster.b[F['levels'] + MAGE]
            robe = caster.b[F['robe_order']]
            if lv(caster, MAGE) > 0 and robe > 0:
                moon = game.s.r0[robe + 0x1F8]
                level = level + (-1 if moon == 0 else 1 if moon == 2 and lv(caster, MAGE) > 5 else 0) & 255
            level = max(level, caster.b[F['levels'] + RANGER])
        else: level = 12
    if (ident & MASK) == 47 and any(e[0] == STORED_FIREBALL for e in caster.effects):
        level = 15
    return level & 255


def spell_range(game, caster, row):
    if getattr(game, 'using_item', False): reach = row.range_per_level * 6 + row.range & 255
    else: reach = row.range + row.range_per_level * caster_level(game, caster, row.id) & 255
    return 1 if reach == 255 or not reach and row.targeting else reach


def duration(game, caster, row):
    if row.id == 26: return 3780
    if row.id in (57, 61): return dice(game.s, 5, 4)
    if row.id == 59: return dice(game.s, 1, 4) * 10 + 40
    return row.duration_per_level * caster_level(game, caster, row.id) + row.duration & 0xFFFF


def forget(char, ident):
    if rules.spellbook(char) is None: return
    for at in range(F['memorized'], F['memorized'] + camp.MEMORY_SLOTS):
        if char.b[at] == ident:
            char.b[at] = ident | PENDING
            return


def _say(game, char, text, anim=False):
    battle = getattr(game, 'battle', None)
    if battle is not None:
        battle.message(camp.name(char) + ' ' + text)
        if anim: battle.name_anim(char)
    else: _notice(game, char, text)


def _notice(game, char, text):
    from .effects_handlers import owner
    who, plain = camp.name(char), getattr(owner(game).s, 'g', {}).get('no_border')
    game.ask(camp.Kind.ACK.value, ('Continue',), prompt=who + ' ' + text, timed=1, creature_name=who, creature_text=text, creature_column=1,
             creature_row=19 if plain else 18, creature_colour=12 if not char.b[F['active']] else 13 if char.b[F['level_up_ready']] else 11)


def _text(game, key): return game.assets.text(key)


def _resolve(game, caster, targets, row, strength, on_remove, damage, element, text):
    battle = getattr(game, 'battle', None)
    live = [t for t in targets if t is not None]
    if battle is None and (row.save_effect or damage):
        raise BindingRequired('DKK spell save/attack outside combat: %d %s' % (row.id, row.name))
    if battle is not None: battle.data.setdefault('roll', {})['element'] = element if damage else 0
    else:
        from . import effects
        effects.remember(game, element=0)
    if not live:
        if battle is not None and targets: battle.data['roll']['element'] = 0
        return
    value = strength or caster_level(game, caster, row.id)
    mask = element if damage else 0
    for at in range(len(targets)):
        if targets[at] is None: continue
        saved = bool(row.save_effect) and battle.save(battle.index(targets[at]), row.save_type, 0, mask)
        if row.range == 255 and not (battle.touch(caster, targets[at]) if battle is not None else _camp_touch(game, caster, targets[at])): damage, saved = 0, True
        if damage: battle.spell_damage(targets[at], battle.context(caster, damage=damage & 255, element=element), row.save_effect, saved)
        if row.effect:
            if battle is not None:
                battle.add_with_message(battle.index(targets[at]), row.effect, duration(game, caster, row), value, on_remove, text, saved, row.save_effect)
            else: _add(game, caster, targets[at], row.effect, duration(game, caster, row), value, on_remove, text, row.id)
    if battle is not None: battle.data['roll']['element'] = 0


def _camp_touch(game, caster, target):
    from . import effects
    rules.recalc_stats(target, game.s.r1[0x372])
    roll = effects.camp_roll(game, attacker=caster, spell=getattr(game, 'current_spell', 0))
    effects.trigger_condition(game, 11, target, roll)
    natural = dice(game.s, 1, 20)
    if natural >= 2:
        roll.attack = 100 if natural == 20 else natural
        effects.trigger_condition(game, 10, caster, roll)
        effects.trigger_condition(game, 16, target, roll)
    effects.remember(game, roll)
    if natural < 2: return False
    modifier = rules._s8(game.s.r1[0x371 if caster.b[F['side']] == 0 else 0x370])
    return roll.attack >= 0 and roll.attack + caster.b[F['thac0']] + modifier >= target.b[F['ac']]


def _add(game, caster, target, kind, minutes, strength, on_remove, text, ident=0, saved=False, negates=0):
    from . import effects
    battle = getattr(game, 'battle', None)
    if battle is not None: return battle.add_with_message(battle.index(target), kind, minutes, strength, on_remove, text, saved, negates)
    roll = effects.camp_roll(game, attacker=caster, effect=kind, spell=getattr(game, 'current_spell', ident),
                             services={'caster_level': lambda spell_id: caster_level(game, caster, spell_id)})
    effects.trigger_condition(game, 9, target, roll)
    effects.remember(game, roll)
    if not roll.effect or saved and negates == 1: return _say(game, target, _text(game, 'unaffectedMessage'))
    node = effects.has_effect(target, kind)
    if node is not None and node[1] | node[2] << 8: effects.remove_effect(game, target, kind, node)
    effects.add_effect(target, kind, minutes, strength, on_remove)
    if text: _say(game, target, text)


def _plain(key):
    return lambda game, caster, targets, row: _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, key) if key else '')


def _timed(game, char, text):
    message = camp.name(char) + ' ' + text
    battle = getattr(game, 'battle', None)
    if battle is not None:
        battle.message(message)
        battle.pause()
    else: _notice(game, char, text)


def _damage_dice(game, count, sides):
    from . import effects
    battle = getattr(game, 'battle', None)
    if battle is not None: battle.data.setdefault('roll', {})['dice_count'] = count
    else: effects.remember(game, dice_count=count)
    return effects.roll_dice(game.s, count, sides)


def _dice_damage(count, sides, plus, element):
    return lambda game, caster, targets, row: _resolve(game, caster, targets, row, 0, False, _damage_dice(game, count, sides) + plus & 255, element, '')


def _cost(game, value=None):
    from .effects_handlers import owner
    top = owner(game)
    if value is not None: top.spell_cost = value
    return getattr(top, 'spell_cost', 0)


def _barkskin(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, 'isText') + game.assets.names('effectNames')[47])


def _enlarge(game, caster, targets, row):
    from . import effects
    from .effects_ability import improved_strength
    target = targets[0]
    level = caster_level(game, caster, row.id)
    base, exceptional = {1: (18, 0), 2: (18, 1), 3: (18, 51), 4: (18, 76), 5: (18, 91), 6: (18, 100), 7: (19, 0), 8: (20, 0), 9: (21, 0)}.get(level, (22, 0))
    _cost(game, exceptional if base == 18 else 0)
    better, value = improved_strength(target, base, exceptional, 0)
    if not better: return _timed(game, target, _text(game, 'unaffectedMessage'))
    _timed(game, target, _text(game, 'strongerText'))
    effects.add_effect(target, 12, duration(game, caster, row), value, True)
    effects.recalc_ability(game, target, 0)


def _hammer(game, caster, targets, row):
    from . import effects
    _resolve(game, caster, targets, row, 0, True, 0, 0, '')
    effects.call_handler(game, targets[0], 23, None, False)


def _mirror(game, caster, targets, row):
    value = dice(game.s, 1, 4) << 4 & 255 | caster_level(game, caster, row.id)
    _resolve(game, caster, targets, row, value, False, 0, 0, _text(game, 'duplicatedText'))


def _cure_blindness(game, caster, targets, row):
    from . import effects
    if effects.remove_with_message(game, targets[0], 33): _say(game, targets[0], _text(game, 'canSeeText'), True)


def _harm(game, caster, targets, row):
    battle, target = game.battle, targets[0]
    damage = target.b[F['hp']] - dice(game.s, 1, 4) & 255
    battle.spell_damage(target, battle.context(caster, damage=damage, element=8), 0, False)


def _rate(counter, enemy, key):
    def apply(game, caster, targets, row):
        from . import effects
        battle = getattr(game, 'battle', None)
        if battle is not None: battle.data['multi_target'] = 1
        side = caster.b[F['side']]
        if enemy: side = int(not side)
        left = caster_level(game, caster, row.id)
        for at, target in enumerate(targets):
            if target is not None and target.b[F['side']] == side and left > 0:
                left -= 1
                if effects.remove_with_message(game, target, counter): targets[at] = None
            else: targets[at] = None
        _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, key))
        for target in targets:
            if target is None: continue
            if battle is not None: battle.trigger(18, battle.index(target))
            else:
                roll = effects.camp_roll(game)
                effects.trigger_condition(game, 18, target, roll)
                effects.remember(game, roll)
    return apply


def _speed_potion(game, caster, targets, row):
    from . import effects
    if not effects.remove_with_message(game, targets[0], 42): _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, 'hastedText'))


def _heal_potion(game, caster, targets, row):
    from . import effects
    battle, target, amount = getattr(game, 'battle', None), targets[0], dice(game.s, 2, 4) + 2
    if battle.heal(target, amount) if battle is not None else effects.restore_hp(target, amount, False):
        _say(game, target, _text(game, 'healedMessage'), True)


def _dispel_evil(game, caster, targets, row):
    battle = game.battle
    battle.add_with_message(battle.index(caster), 4, duration(game, caster, spell(game, 73)), 0, False, '')
    _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, 'isAffectedText'))


def _cloud(game, caster, targets, row):
    from .effects_area import terrain_effects
    battle = game.battle
    x, y = battle.data['aim']
    level = caster_level(game, caster, row.id)
    count, terrain = (4, 29) if row.id == 34 else (9, 28)
    patch, dx, dy = (game.assets.table(key) for key in ('patchDir', 'directionX', 'directionY'))
    occupied, cells, found = battle.occupancy(), [], []
    for at in range(count):
        cx, cy = x + dx[patch[at]], y + dy[patch[at]]
        if not (0 <= cx <= 49 and 0 <= cy <= 24): continue
        occupant = battle.contents(cx, cy, occupied)[0]
        if occupant >= 0 and occupant not in found: found.append(occupant)
        under = battle.resolve_terrain(cx, cy)
        if under > 0 and battle.terrain(under) < 255:
            cells.append((cx, cy, under))
            battle.put_tile(cx, cy, terrain)
    battle.data.setdefault('clouds', []).insert(0, dict(cells=cells, terrain=terrain, countdown=level, x=x, y=y, level=level))
    battle.scroll(x, y, 255, 8)
    for occupant in found: terrain_effects(battle, occupant, True)


def _dispel(game, caster, targets, row):
    from . import effects
    battle = getattr(game, 'battle', None)
    if battle is not None: battle.data['multi_target'] = 1
    level = caster_level(game, caster, row.id)
    def dispelled(value, cost):
        chance = (level - value) * 5 + 50 if level > value else 50 - (cost - level) * 2 if level < value else 50
        return dice(game.s, 1, 100) <= chance & 255
    for _ in targets:
        target, removed = targets[0], False
        if target is None: continue
        for node in list(target.effects):
            if node[3] == 255 or not any(node is live for live in target.effects): continue
            cost = _cost(game, node[3] & 15)
            if dispelled(cost, cost):
                effects.remove_effect(game, target, node[0], node)
                removed = True
        if removed: _say(game, target, _text(game, 'isAffectedText'), True)
    if battle is None: return
    from .effects_area import count_down_area
    patch, dx, dy = (game.assets.table(key) for key in ('patchDir', 'directionX', 'directionY'))
    ax, ay = battle.data['aim']
    for direction in range(9):
        x, y = ax + dx[direction], ay + dy[direction]
        tile = battle.contents(x, y, {})[1]
        if tile not in (28, 29): continue
        for cloud in battle.data.get('clouds', ()):
            for at in range(4 if tile == 29 else 9):
                if (x, y) == (cloud['x'] + dx[patch[at]], cloud['y'] + dy[patch[at]]) and dispelled(cloud['level'], _cost(game)):
                    cloud['countdown'] = -1
        battle.scroll(ax, ay, 3, 8)
    count_down_area(battle, True)


def _death(game, caster, targets, row):
    battle = game.battle
    battle.data['multi_target'] = 1
    battle.data.setdefault('roll', {})['element'] = 0x40
    budget = dice(game.s, 4, 20) * 2 & 255
    for at, target in enumerate(targets):
        if target is None: continue
        level = target.b[F['highest_level']]
        cost = _cost(game, {0: 1, 1: 2, 2: 8, 3: 8, 4: 16, 5: 16, 6: 16 if target.b[F['hp_max']] <= 51 else 20, 7: 20, 8: 20}.get(level, 162))
        if not target.b[F['target_flags']] & 8 and budget >= cost:
            budget -= cost
            battle.kill(battle.index(target), 6, _text(game, 'dropsDeadText'))
        else: targets[at] = None


def _ruin(game, caster, targets, damage):
    battle = game.battle
    x = battle.context(caster, damage=damage, element=0x40)
    battle.trigger(9, battle.index(targets[0]), x)
    return x.damage, getattr(x, 'target', targets[0])


def _destroy(status, key):
    def apply(game, caster, targets, row):
        battle = game.battle
        damage, target = _ruin(game, caster, targets, 255)
        if damage and not _save(game, target, 4): battle.kill(battle.index(target), status, _text(game, key))
    return apply


def _slay(game, caster, targets, row):
    battle = game.battle
    damage, target = _ruin(game, caster, targets, 67)
    if not damage: return _timed(game, target, _text(game, 'unaffectedMessage'))
    if not _save(game, target, 4) and not target.b[F['target_flags']] & 8:
        return battle.kill(battle.index(target), 6, _text(game, 'slainText'))
    battle.spell_damage(target, battle.context(caster, damage=_damage_dice(game, 2, 8) + 1 & 255, element=8), 0, False)


def _poison(game, caster, targets, row):
    from . import effects
    battle = game.battle
    _resolve(game, caster, targets, row, 0, False, 0, 8, '')
    j = battle.record(battle.index(caster))['target']
    if j < 0: raise BindingRequired('DKK Poison without a combat target is unset')
    x = battle.context(caster, effect=64)
    battle.trigger(9, j, x)
    if x.effect == 64: effects.call_handler(game, caster, 64, bytearray((64, 0, 0, 0, 0, 0, 0, 0, 0)), False)


def _neutralize(game, caster, targets, row):
    from . import effects
    from .effects_handlers import owner
    target = targets[0]
    if target.b[F['status']] == camp.ANIMATED:
        targets[0] = None
        return
    if not effects.has(target, 55): return _timed(game, target, _text(game, 'unaffectedMessage'))
    if not target.b[F['hp']]: target.b[F['hp']] = 1
    root = owner(game)
    locked = getattr(root, 'effect_busy', False)
    root.effect_busy = True
    try:
        for ident in (55, 22, 15): effects.remove_effect(game, target, ident)
    finally: root.effect_busy = locked
    _timed(game, target, _text(game, 'unpoisonedText'))
    target.b[F['active']], target.b[F['status']] = 1, 0


def _youth(game, caster, targets, row):
    record = rules.record(caster)
    age = record.get('age') - (dice(game.s, 1, 4) + 1) & 65535
    record.set('age', max(age, 18))
    _timed(game, caster, _text(game, 'eighteenYearsOldText' if age < 18 else 'youngerText'))


def _bless(game, caster, targets, row):
    battle = getattr(game, 'battle', None)
    if battle is not None: battle.data['multi_target'] = 1
    side = caster.b[F['side']]
    for at, t in enumerate(targets):
        if t is not None and (t.b[F['side']] != side or battle is not None and battle.targets(battle.index(t), 1)): targets[at] = None
    _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, 'isText') + game.assets.names('effectNames')[0])


def _restore(game, caster, target, amount):
    battle = getattr(game, 'battle', None)
    if battle is not None: done = battle.heal(target, amount)
    else:
        done = target.b[F['status']] in (0, 1, 4, 5)
        if done:
            target.b[F['hp']] = min(target.b[F['hp_max']], target.b[F['hp']] + amount & 255)
            if not target.b[F['active']]:
                if target.b[F['status']] == 5: target.b[F['status']] = 4
                if target.b[F['status']] == 4: target.b[F['status']], target.b[F['active']] = 0, 1
    if done: _timed(game, target, _text(game, 'fullyHealedText' if target.b[F['hp']] == target.b[F['hp_max']] else 'partiallyHealedText'))


def _cure(count, sides, plus, deity_extra):
    def apply(game, caster, targets, row):
        empty = not targets or targets[0] is None
        if empty and not deity_extra: return
        bonus = (dice(game.s, 1, 8) if caster.b[F['deity']] == 4 else 0) + deity_extra
        if not empty: _restore(game, caster, targets[0], bonus + dice(game.s, count, sides) + plus)
    return apply


def _burning(game, caster, targets, row): _resolve(game, caster, targets, row, 0, False, caster_level(game, caster, row.id), 0x09, '')


def _charm(game, caster, targets, row):
    from . import effects
    if not targets or targets[0] is None: return
    target = targets[0]
    race, kind, size = (target.b[F[key]] for key in ('race', 'creature_type', 'dimensions'))
    if row.id == 4:
        allowed = rules._s8(race) < MONSTER or bool(kind & 16)
        text = _text(game, 'isText') + game.assets.names('effectNames')[10]
        rejected = _text(game, 'isText') + _text(game, 'notText') + game.assets.names('effectNames')[10]
    else:
        allowed = not (race == MONSTER and not kind & 2 or size > 1)
        text, rejected = _text(game, 'charmedText'), _text(game, 'unaffectedMessage')
    if not allowed: return _timed(game, target, rejected)
    _resolve(game, caster, targets, row, caster_level(game, caster, row.id) + caster.b[F['side']] * 128, True, 0, 0, text)
    node = effects.has_effect(target, 11)
    if node is not None: effects.call_handler(game, target, 11, node, False)


def _missile(game, caster, targets, row):
    value = caster_level(game, caster, row.id) + 1 & 255
    _resolve(game, caster, targets, row, 0, False, _damage_dice(game, value // 2, 4) + value // 2 & 255, 0x08, '')


def _shock(game, caster, targets, row):
    _resolve(game, caster, targets, row, 0, False, _damage_dice(game, 1, 8) + caster_level(game, caster, row.id) & 255, 0x0C, '')


def _sleep(game, caster, targets, row):
    battle = getattr(game, 'battle', None)
    if battle is not None: battle.data['multi_target'] = 1
    budget = dice(game.s, 4, 4)
    for at, t in enumerate(targets):
        level = rules._s8(t.b[F['highest_level']])
        cost = 1 if 0 <= level <= 1 else 2 if level == 2 else 4 if level == 3 else 6 if level == 4 else (10 if level == 5 and rules._s8(t.b[F['race']]) == MONSTER else 20)
        _cost(game, cost)
        if t.b[F['status']] != 1 and not any(e[0] == row.effect for e in t.effects) and budget >= cost: budget -= cost
        else: targets[at] = None
    _resolve(game, caster, targets, row, 0, False, 0, 0, _text(game, 'fallsAsleepText'))


def _apply_each(game, caster, targets, row, modifier, text):
    battle, last = game.battle, len(targets) - 1
    for at in range(last, -1, -1):
        target = targets[at]
        if target is None: continue
        j = battle.index(target)
        if at < last: _cast_flight(battle, battle.index(caster), *battle.position(j), row.id)
        if row.id in (79, 81) and at == last: saved, negates = True, 1
        else: saved, negates = _save(game, target, row.save_type, modifier), row.save_effect
        if target.b[F['race']] == MONSTER and row.id in (23, 49): saved = True
        value = caster_level(game, caster, row.id) + (caster.b[F['side']] * 128 if row.id == 81 else 0) & 255
        battle.add_with_message(j, row.effect, duration(game, caster, row), value, False, text, saved, negates)


def _hold(game, caster, targets, row):
    modifier = {1: 254 if row.id == 23 else 253, 2: 255}.get(len(targets), 0)
    _apply_each(game, caster, targets, row, modifier, _text(game, 'heldText'))


def _faerie(game, caster, targets, row): _apply_each(game, caster, targets, row, 0, _text(game, 'highlightedText'))


def _save(game, target, kind, bonus=0, element=None):
    from . import effects
    battle = getattr(game, 'battle', None)
    if battle is not None: return battle.save(battle.index(target), kind, bonus, _standing(battle) if element is None else element)
    value = effects.roll_dice(game.s, 1, 20)
    if effects.has(target, 57): value = 1
    if value in (1, 20): return value == 20
    order = target.b[F['robe_order']]
    if lv(target, MAGE) > 0 and order:
        moon = game.s.r0[order + 0x1F8]
        bonus += -1 if moon == 0 else 1 if moon == 2 else 0
    roll = effects.camp_roll(game, save=value + rules._s8(target.b[F['save_bonus']]) + rules._s8(bonus & 255) & 255, save_type=kind, save_passed=True, **({} if element is None else {'element': element}))
    effects.trigger_condition(game, 12, target, roll)
    effects.remember(game, roll)
    return target.b[F['saves'] + kind] <= roll.save & 255


def _reduce(game, caster, targets, row):
    from . import effects
    target = targets[0] if targets else None
    if target is None or _save(game, target, 4) or not effects.has(target, 12): return
    effects.remove_effect(game, target, 12)
    effects.recalc_ability(game, target, 0)
    _timed(game, target, _text(game, 'reducedText'))


def _friends(game, caster, targets, row):
    from . import effects
    _resolve(game, caster, targets, row, dice(game.s, 2, 4), True, 0, 0, _text(game, 'friendlyText'))
    effects.recalc_ability(game, caster, 5)


def _slow_poison(game, caster, targets, row):
    from . import effects
    target = targets[0]
    if target.b[F['status']] == camp.ANIMATED:
        targets[0] = None
        return
    if not effects.has(target, 55): return
    if not target.b[F['hp']]: target.b[F['hp']] = 1
    target.b[F['status']], target.b[F['active']] = 0, 1
    _resolve(game, caster, targets, row, 255, True, 0, 0, _text(game, 'isAffectedText'))
    effects.add_effect(target, 15, 10, 255, True)


def _strength(game, caster, targets, row):
    from . import effects
    from .effects_ability import improved_strength
    target, bonus = targets[0], None
    warrior = any(lv(target, c) > 0 for c in (FIGHTER, RANGER, KNIGHT, PALADIN))
    if lv(target, MAGE) > 0: bonus = dice(game.s, 1, 4)
    if lv(target, CLERIC) > 0 or lv(target, THIEF) > 0: bonus = dice(game.s, 1, 6)
    if warrior: bonus = dice(game.s, 1, 8)
    if bonus is None: raise BindingRequired('Strength on a creature with no class level leaves the bonus unset')
    value, percentage = target.b[F['abilities'] + 1] + bonus & 255, 0
    if value > 18:
        if warrior: percentage = min(100, target.b[F['strength_extra']] + (value - 18) * 10 & 255)
        value = 18
    if improved_strength(target, value, percentage, 0)[0]:
        effects.add_effect(target, 38, duration(game, caster, row), bonus + 100 & 255, True)
        effects.recalc_ability(game, target, 0)


def _heal(game, caster, targets, row):
    from . import effects
    target, battle = targets[0], getattr(game, 'battle', None)
    said = []
    tell = (lambda key: _say(game, target, _text(game, key))) if battle is not None else said.append
    if effects.remove_with_message(game, target, 33): tell('canSeeText')
    if effects.remove_with_message(game, target, 61):
        tell('regainsIntellectText')
        effects.recalc_ability(game, target, 1)
        effects.recalc_ability(game, target, 2)
    value = dice(game.s, 1, 4)
    hp, top = target.b[F['hp']], target.b[F['hp_max']]
    value = 0 if hp + value > top else top - hp - value & 255
    if battle.heal(target, value) if battle is not None else effects.restore_hp(target, value, False):
        tell('healedMessage')
    if said: _say(game, target, _text(game, said[-1]))


def _giant_strength(game, caster, targets, row):
    from . import effects
    from .effects_ability import improved_strength
    target = targets[0]
    better, value = improved_strength(target, 21, 0, None)
    if better: _timed(game, target, _text(game, 'strongerText'))
    else: raise BindingRequired('Giant Strength on a creature at least as strong adds an unset strength')
    effects.add_effect(target, 113, dice(game.s, 1, 4) * 10 + 40, value, True)
    effects.recalc_ability(game, target, 0)


def _snakes(game, caster, targets, row):
    from . import effects
    target = targets[0]
    if rules._s8(target.b[F['highest_level']]) >= 6: return _timed(game, target, _text(game, 'smashesFlatText'))
    _resolve(game, caster, targets, row, caster_level(game, caster, row.id), False, 0, 0x08, '')
    node = effects.has_effect(target, 3)
    if node is not None: effects.call_handler(game, target, 3, node, False)


def _each_saved(game, caster, targets, ident, kind, text):
    battle = game.battle
    for target in targets:
        if target is None: continue
        saved = _save(game, target, 4, 0, _standing(battle))
        battle.add_with_message(battle.index(target), kind, duration(game, caster, spell(game, ident)), 0, False, _text(game, text), saved, 1)


def _entangle(game, caster, targets, row):
    if not game.vm.is3d(): _each_saved(game, caster, targets, 78, 6, 'entangledText')


def _confusion(game, caster, targets, row):
    del targets[dice(game.s, 2, 8):]
    _each_saved(game, caster, targets, 82, 35, 'confusedText')


def _fumble(game, caster, targets, row):
    from . import effects
    battle, target = game.battle, targets[0]
    battle.data.setdefault('roll', {})['element'] = 0x40
    kind, text = (42, 'slowedText') if _save(game, target, 4, 0, 0x40) else (27, 'clumsyText')
    battle.add_with_message(battle.index(target), kind, duration(game, caster, spell(game, 86)), 0, False, _text(game, text), False, 0)
    if effects.has(target, kind): effects.call_handler(game, target, kind, None, False)
    _resolve(game, caster, targets, row, 0, True, 0, 0, _text(game, 'clumsyText'))


def _charm_monsters(game, caster, targets, row):
    from . import effects
    _apply_each(game, caster, targets, row, 0, _text(game, 'charmedText'))
    for target in targets:
        node = effects.has_effect(target, 11) if target is not None else None
        if node is not None: effects.call_handler(game, target, 11, node, False)


def _dimension_door(game, caster, targets, row):
    battle = game.battle
    i = battle.index(caster)
    battle.valid_location(i, *battle.data['aim'])
    battle.scroll(*battle.position(i), 0, 8)
    _timed(game, caster, _text(game, 'teleportsText'))


def _fire_shield(game, caster, targets, row):
    from .shop import horizontal
    from .combat import Kind
    battle = getattr(game, 'battle', None)
    def ask(name, options, **info):
        if battle is not None: return battle.ask(Kind.CONFIRM, list(options), **info)
        return horizontal(game, camp.Kind[name].value, options, **info)
    minutes, text = duration(game, caster, spell(game, 85)), _text(game, 'isText') + _text(game, 'protectedText')
    while True:
        if caster.b[F['auto_combat']]: choice = dice(game.s, 1, 2) - 1
        else: choice = ask('MENU', tuple(_text(game, 'flameTypeMenu').split()), prompt=_text(game, 'flameTypePrompt'), start=0)
        if choice in (0, 1):
            _add(game, caster, caster, (50, 54)[choice], minutes, 0, False, text, 85)
            _add(game, caster, caster, 112, minutes, 0, False, '', 85)
            return
        if ask('CONFIRM', ('Yes', 'No'), prompt=_text(game, 'abortSpellPrompt'), start=0) == 0: return


def _feeblemind(game, caster, targets, row):
    from . import effects
    target = targets[0]
    at = F['saves'] + 4
    kept = target.b[at]
    target.b[at] = kept + {CLERIC: -1, MAGE: 4}.get(target.b[F['class']], 2) & 255
    try:
        _resolve(game, caster, targets, row, 0, False, 0, 0, '')
        if effects.has(target, 68): effects.call_handler(game, target, 68, None, False)
    finally: target.b[at] = kept


def _mass_charm(game, caster, targets, row):
    from . import effects
    battle, total, done = game.battle, 0, False
    level = caster_level(game, caster, row.id)
    limit = level * 2 & 255
    for target in targets:
        if done: break
        if target is None: continue
        if not target.b[F['creature_type']] & 2 or target.b[F['dimensions']] > 1:
            _timed(game, target, _text(game, 'unaffectedMessage'))
            continue
        state = target.b[F['highest_level']]
        if state + total > limit: continue
        total = total + state & 255
        done = total == limit
        saved = _save(game, target, 4)
        battle.add_with_message(battle.index(target), 11, duration(game, caster, row), level + caster.b[F['side']] * 128 & 255, True, _text(game, 'charmedText'), saved, 1)
        node = effects.has_effect(target, 11)
        if node is not None: effects.call_handler(game, target, 11, node, False)


def _dance(game, caster, targets, row):
    battle, target = game.battle, targets[0]
    if not battle.touch(caster, target): return
    minutes, level = duration(game, caster, spell(game, 113)), caster_level(game, caster, 113)
    battle.add_with_message(battle.index(target), 6, minutes, level, False, '')
    battle.add_with_message(battle.index(target), 57, minutes, level, False, _text(game, 'dancingText'))


def _blind_word(game, caster, targets, row):
    battle = game.battle
    def chosen():
        total = 0
        for target in targets:
            if total > 100: break
            if target is None: continue
            top = target.b[F['hp_max']]
            if top <= 100 and top + total <= 100:
                total += top
                yield target
    list(chosen())
    dice(game.s, 1, 4)
    for target in list(chosen()):
        battle.add_with_message(battle.index(target), 33, duration(game, caster, row), 0, False, _text(game, 'blindText'))


def _stun(game, caster, targets, row):
    battle, target = game.battle, targets[0]
    hp = target.b[F['hp']]
    value = dice(game.s, 4, 4) if 1 <= hp <= 30 else dice(game.s, 2, 4) if 31 <= hp <= 60 else dice(game.s, 1, 4) if 61 <= hp <= 90 else 0
    battle.add_with_message(battle.index(target), row.effect, value, caster_level(game, caster, row.id), False, _text(game, 'stunnedText'), False, row.save_effect)


def _prayer(game, caster, targets, row):
    _resolve(game, caster, targets, row, caster_level(game, caster, row.id) + caster.b[F['side']] * 16 & 255, False, 0, 0, _text(game, 'prayingText'))


def _fireball(game, caster, targets, row):
    from . import effects
    battle = game.battle
    battle.data['multi_target'] = 1
    count = dice(game.s, 1, 3) * 2 + 1 if row.id == 64 else caster_level(game, caster, row.id)
    if not game.vm.is3d(): targets[:] = [battle.chars[j] for j in battle.area_targets(*battle.data['aim'], 2)]
    battle.scroll(*battle.data['aim'], 0, 8)
    battle.data.setdefault('roll', {})['dice_count'] = count
    damage = effects.roll_dice(game.s, count, 6)
    if row.id == 108: damage = damage + count & 255
    _resolve(game, caster, targets, row, 0, False, damage, 0x09, '')


def toward(x, y, tx, ty, facing):
    if not (0 <= x <= 49 and 0 <= y <= 24 and 0 <= tx <= 49 and 0 <= ty <= 24): return False
    nx, ny = x + (0, 1, 1, 1, 0, -1, -1, -1, 0)[facing], y + (-1, -1, 0, 1, 1, 1, 0, -1, 0)[facing]
    if (tx, ty) in ((x, y), (nx, ny)) or facing == 8: return True
    u, v = tx - nx, ty - ny
    side = (u >= 0 and v <= -u, u <= 0 and v <= u, v <= 0 and u >= -v, v >= 0 and u >= v,
            u >= 0 and v >= u, u <= 0 and v >= -u, v >= 0 and u <= -v, v <= 0 and u <= v)
    first, second = ((0, 1), (0, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 1))[facing]
    return side[first] or side[second]


SCATTER = {34: (1, 26), 91: (1, 27), 87: (2, 25)}


def show_cast(battle, i, ident):
    x, y = battle.position(i)
    tx, ty = battle.data['aim']
    for facing in range(9):
        if toward(x, y, tx, ty, facing):
            battle.record(i)['facing'] = facing
            break
    _cast_flight(battle, i, tx, ty, ident, 1)
    radius, cell = SCATTER.get(ident, (2 if ident == 64 or not battle.game.vm.is3d() else 3, 24) if ident in (47, 64, 108) else (0, 0))
    if radius: scatter(battle, i, ident, tx, ty, radius, cell, 1)


def _cast_flight(battle, i, tx, ty, ident, posed=0):
    x, y = battle.position(i)
    if hasattr(battle, 'show'): battle.show('bolt', actor=i, start=(x, y), aim=(tx, ty), spell=ident, picture=18, frames=4, pace=30, posed=posed)
    battle.moving_icon(x, y, tx, ty)


def flight(battle, sx, sy, ex, ey, picture=19, frames=4, pace=50):
    if hasattr(battle, 'show'): battle.show('flight', start=(sx, sy), aim=(ex, ey), picture=picture, frames=frames, pace=pace)
    battle.moving_icon(sx, sy, ex, ey)


def scatter(battle, i, ident, tx, ty, radius, cell, posed=0):
    import math
    battle.scroll(tx, ty, 255)
    ox = (tx - 3) * 3 if tx < 3 else (tx - 46) * 3 if tx > 46 else 0
    oy = (ty - 3) * 3 if ty < 3 else (ty - 21) * 3 if ty > 21 else 0
    rings = []
    for ring in range(1, radius * 3 + 2):
        points = []
        rings.append(points)
        for _ in range(2 * ring - 1):
            battle.s.random(1)
            angle = battle.s.seed / 4294967296 * 2 * math.pi
            px, py = int(math.cos(angle) * ring) + ox, int(math.sin(angle) * ring) + oy
            if -9 <= px <= 9 and -9 <= py <= 9: points.append((px + 9, py + 9, battle.s.random(4)))
    clipped_rings = tuple(map(tuple, rings))
    battle.event('scatter', actor=i, spell=ident, cell=cell, aim=(tx, ty), points=sum(map(len, rings)), rings=clipped_rings)
    if hasattr(battle, 'show'):
        battle.show('scatter', cell=cell, aim=(tx, ty), rings=clipped_rings, actor=i, posed=posed)
    battle.scroll(tx, ty, 255)


def _stored_fireball(game, char, node, removed, roll):
    from . import effects
    battle = game.battle
    if battle.cast(battle.data['actor'], 47, using_item=bool(getattr(game, 'using_item', False)), ai=True):
        effects.remove_effect(game, char, STORED_FIREBALL)
    _handed_back(battle, roll)


def _standing(battle): return battle.data.setdefault('roll', {}).get('element', 0)


def _steps(game, sx, sy, ex, ey):
    dx, dy = game.assets.table('directionX'), game.assets.table('directionY')
    walk = line(sx, sy, ex, ey)
    x, y, _ = next(walk)
    for nx, ny, distance in walk:
        yield nx, ny, distance, next(d for d in range(8) if (dx[d], dy[d]) == (nx - x, ny - y))
        x, y = nx, ny


def _bolt_cell(game, caster, x, y, damage, save, skip, bounced):
    battle = game.battle
    occupant, tile = battle.contents(x, y)
    bounced = int(tile > 0 and battle.terrain(tile) == 255 and game.vm.m0(0x4BE6) == 1 and not bounced)
    if occupant >= 0 and occupant != skip:
        saved = battle.save(occupant, save, 0, _standing(battle))
        battle.spell_damage(battle.chars[occupant], battle.context(caster, damage=damage), 2, saved)
    return bounced


def _bolt_path(game, caster, reach, damage, save, rebound):
    battle = game.battle
    ox, oy = battle.position(battle.index(caster))
    prior = battle.contents(*battle.data['aim'])[0]
    if (ox, oy) == tuple(battle.data['aim']): return
    used, sign, accepted, remaining = 0, 1, 0, reach * 2 & 255
    battle.data['multi_target'] = 1
    while remaining > 0:
        tx, ty = battle.data['aim']
        walk = line(tx, ty, (tx - ox) * sign * remaining + tx, (ty - oy) * sign * remaining + ty)
        cx, cy, distance = next(walk)
        while True:
            sx, sy = cx, cy
            while True:
                step = next(walk, None)
                if step is not None: cx, cy, distance = step
                neighbor, cell = battle.contents(cx, cy)
                if not cell or battle.terrain(cell) == 1: accepted = 0
                if step is None or neighbor >= 0 and neighbor != prior or not cell or battle.terrain(cell) > 1 or distance >= remaining: break
            if not cell: remaining = 0
            flight(battle, sx, sy, cx, cy)
            accepted = _bolt_cell(game, caster, cx, cy, damage, save, prior, accepted)
            prior = neighbor
            if accepted:
                battle.data['aim'] = cx, cy
                back = 0
                for *_, back in line(cx, cy, ox, oy): pass
                if rebound and back <= 8: distance = distance * 2 & 255
                sign, rebound, prior = -sign, 0, -1
            used = max(2, distance - used)
            remaining = remaining - used if remaining > used else 0
            used = distance
            if accepted or not remaining: break
    battle.data['multi_target'] = 0


def _lightning(game, caster, targets, row):
    battle = game.battle
    damage = _damage_dice(game, caster_level(game, caster, row.id), 6)
    battle.data['roll']['element'] = 0x0C
    _bolt_cell(game, caster, *battle.data['aim'], damage, 4, -1, 0)
    _bolt_path(game, caster, 7, damage, 4, 1)


def _cone(game, caster, fx, fy, tx, ty, width, reach):
    battle, tables = game.battle, game.assets.table
    dx, dy = tables('directionX'), tables('directionY')
    turns, distance = [], 0
    for *_, distance, turn in _steps(game, fx, fy, tx, ty): turns.append(turn)
    if not turns: return []
    reach, at = reach * 2 & 255, 0
    while distance < reach and 0 < tx < 49 and 0 < ty < 24:
        turn = turns[at]
        distance = distance + 2 + (turn & 1) & 255
        tx, ty, at = tx + dx[turn], ty + dy[turn], (at + 1) % len(turns)
    tx, ty = battle.walk(fx, fy, max(0, min(49, tx)), max(0, min(24, ty)), reach)[1]
    if width not in (1, 2, 3): raise BindingRequired('Death Knights cone width is unverified: %d' % width)
    occupied, found, repeated, final = battle.occupancy(), [], False, None
    for x, y, _, turn in _steps(game, fx, fy, tx, ty):
        occupant = battle.contents(x, y, occupied)[0]
        if occupant < 0: continue
        if not found: repeated = False
        elif occupant in found: repeated = True
        if not repeated: found.append(occupant)
        final = turn
    if width > 1 and final is not None:
        for side in ('Far', 'Near')[:width - 1]:
            ex = max(0, min(49, tx + tables('direction%sX' % side)[final]))
            ey = max(0, min(24, ty + tables('direction%sY' % side)[final]))
            for x, y, *_ in _steps(game, fx, fy, ex, ey):
                occupant = battle.contents(x, y, occupied)[0]
                if occupant >= 0 and occupant not in found: found.append(occupant)
    return [battle.chars[k] for k in found if battle.chars[k] is not caster]


def _cone_of_cold(game, caster, targets, row):
    battle = game.battle
    level = caster_level(game, caster, row.id)
    targets[:] = _cone(game, caster, *battle.position(battle.index(caster)), *battle.data['aim'], 2, max(1, (level + 1) // 2))
    _resolve(game, caster, targets, row, 0, False, _damage_dice(game, level, 4) + level & 255, 0x0A, '')


def _fear(game, caster, targets, row):
    from . import effects
    from .effects_handlers import flee
    battle = game.battle
    targets[:] = _cone(game, caster, *battle.position(battle.index(caster)), *battle.data['aim'], 3, 6)
    for at in range(len(targets)):
        target = targets[at]
        j = battle.index(target)
        if battle.save(j, 4, 0, _standing(battle)): _timed(game, target, _text(game, 'unaffectedMessage'))
        else:
            battle.add_with_message(j, 111, duration(game, caster, spell(game, 84)), 0, True, _text(game, 'runsAwayText'), False, 1)
            if effects.has_effect(target, 111) is not None: flee(game, target)


def _handed_back(battle, roll):
    for key, value in battle.data.get('roll', {}).items():
        if key in ('effect', 'damage', 'element', 'dice_count'): setattr(roll, key, value)


def _select(battle, ident):
    actor = battle.data['actor']
    picked = battle.spell_targets(actor, spell(battle.game, ident), False, True)
    if picked is not None: battle.game.spell_targets = [battle.chars[j] for j in picked]
    return battle.chars[actor], picked


def _breath_bolt(game, char, node, removed, roll):
    battle = game.battle
    if battle.data['round'] == 0: node[3] = 3
    if node[3]:
        battle.data.setdefault('roll', {})['element'] = 0x24
        i = battle.index(char)
        fx, fy = battle.position(i)
        actor, picked = _select(battle, 51)
        if picked is not None:
            _timed(game, char, _text(game, 'breathesText'))
            if battle.data.get('panel_due'): battle.panel(i)
            if picked: battle.face(i, battle.direction(i, picked[0]))
            flight(battle, fx, fy, *battle.data['aim'])
            _bolt_cell(game, actor, *battle.data['aim'], char.b[F['hp_max']], 3, -1, 0)
            _bolt_path(game, actor, 10, char.b[F['hp_max']], 3, 0)
            node[3] = node[3] - 1 & 255
            battle.end(i)
    _handed_back(battle, roll)


BREATHS = {90: (0x30, 1, 6, 'acidText'), 100: (0x60, 1, 8, 'deathText'), 104: (0x21, 3, 9, 'fireText')}


def _breath(game, char, node, removed, roll):
    battle = game.battle
    if battle.data['round'] == 0: node[3] = 3
    if node[3]:
        mask, width, reach, key = BREATHS[node[0]]
        battle.data.setdefault('roll', {})['element'] = mask
        i = battle.index(char)
        fx, fy = battle.position(i)
        actor, picked = _select(battle, 36)
        if picked is not None:
            found = battle.game.spell_targets = _cone(game, actor, fx, fy, *battle.data['aim'], width, reach)
            if found and all(t.b[F['side']] == (char.b[F['side']] == 0) for t in found):
                _timed(game, char, _text(game, 'breathesText') + _text(game, key))
                if battle.data.get('panel_due'): battle.panel(i)
                first = battle.index(found[0])
                battle.face(i, battle.direction(i, first))
                flight(battle, *battle.position(i), *battle.position(first), 18, 1, 30)
                for at in range(len(found)):
                    if found[at] is None: continue
                    saved = battle.save(battle.index(found[at]), 3, 0, _standing(battle))
                    battle.spell_damage(found[at], battle.context(actor, damage=char.b[F['hp_max']]), 2, saved)
                node[3] = node[3] - 1 & 255
                battle.end(i)
    _handed_back(battle, roll)


def _gaze(game, char, node, removed, roll):
    battle = game.battle
    actor, picked = _select(battle, 10)
    if picked:
        i = battle.index(char)
        _timed(game, char, _text(game, 'gazesText'))
        battle.face(i, battle.direction(i, picked[0]))
        flight(battle, *battle.position(i), *battle.data['aim'], 18, 4, 50)
        battle.data['current_spell'] = 10
        _charm(game, actor, battle.game.spell_targets, spell(game, 10))
    _handed_back(battle, roll)


EFFECT_HANDLERS = {78: _stored_fireball, 81: _gaze, 85: _breath_bolt, 90: _breath, 100: _breath, 104: _breath}


def _nothing(game, caster, targets, row): pass


def remove_curse(game, char):
    from . import effects
    if effects.remove_with_message(game, char, 43):
        _say(game, char, _text(game, 'uncursedText'), True)
        return True
    fields = {key: offset for key, (offset, _) in Item.FIELDS.items()}
    for item in char.items:
        if not item[fields['cursed']]: continue
        item[fields['readied']] = 0
        special = item[fields['powers'] + 2]
        if special > 127:
            game.handler_override_active = True
            effects.call_handler(game, char, special, item, True)
            for stat in range(6): effects.recalc_ability(game, char, stat)
        _say(game, char, _text(game, 'itemUncursedText'), True)
        return True
    return False


def _remove_curse(game, caster, targets, row):
    remove_curse(game, targets[0])


def _revive(game, caster, targets, row):
    from . import effects
    from .effects_handlers import owner
    target = targets[0]
    r = rules.record(target)
    raising = row.id == 75
    race = rules._s8(r.get('race'))
    constitution = F['abilities'] + 8
    if r.get('status') not in ((1, 6) if raising else (6,)): return
    if not target.b[constitution] or (race in (0, 1) if raising else race <= 1): return
    root = owner(game)
    locked = getattr(root, 'effect_busy', False)
    if raising: root.effect_busy = True
    try:
        effects.remove_effect(game, target, 55)
    finally:
        if raising: root.effect_busy = locked
    r.set('status', 0)
    r.set('active', 1)
    if raising:
        target.b[constitution] -= 1
        effects.recalc_ability(game, target, 4)
    r.set('hp', 1 if raising else r.get('hp_max'))
    _timed(game, target, _text(game, 'raisedText' if raising else 'resurrectedText'))


def _stone_to_flesh(game, caster, targets, row):
    target = targets[0]
    if target.b[F['status']] == 7:
        target.b[F['status']], target.b[F['active']], target.b[F['hp']] = 0, 1, 1
        _say(game, target, _text(game, 'noLongerStatusText'))
        battle = getattr(game, 'battle', None)
        if battle is not None:
            index = battle.index(target)
            battle.restore_body(index)
            x, y = battle.position(index)
            if battle.valid_location(index, x, y, True): battle.scroll(*battle.data['aim'], 0, 8)
    _resolve(game, caster, targets, row, 0, False, 0, 0, '')


def _restoration(game, caster, targets, row):
    from .creation import can_level_up
    from .effects_handlers import level_threshold
    target = targets[0]
    r, tables = rules.record(target), rules.tables()
    current = [rules._s8(v) for v in r.get('levels')]
    former = [rules._s8(v) for v in r.get('former_levels')]
    active = sum(v > 0 for v in former)
    missing, selected, threshold = 0, None, tables.level_xp(5, 14)
    for cls, (level, peak) in enumerate(zip(current, former)):
        if level >= peak: continue
        missing = missing + ((peak & 255) - (level & 255) & 255) & 255
        needed = level_threshold(target, cls, level + 1)
        if needed <= threshold: selected, threshold = cls, needed
    if selected is not None:
        if r.get('hp_max') < r.get('old_hp_max'):
            if not missing: raise BindingRequired('Restoration hit point share divides by zero')
            share = (r.get('old_hp_max') - r.get('hp_max')) // missing
            reduction = 0
            if (current[selected] & 255) + 1 < tables.u8('firstFixedHpLevel', selected):
                if not active: raise BindingRequired('Restoration constitution share divides by zero')
                adjustment = rules.class_con_adjust(target, selected)
                reduction = (abs(adjustment) // active * (-1 if adjustment < 0 else 1)) & 255
            r.set('hp', r.get('hp') + share & 255)
            r.set('hp_rolled', r.get('hp_rolled') + share - reduction & 255)
            r.set('hp_max', r.get('hp_max') + share & 255)
        target.b[F['levels'] + selected] = current[selected] + 1 & 255
        rules.recalc_class_stats(target)
        experience = int.from_bytes(target.b[F['experience']:F['experience'] + 4], 'little', signed=True)
        previous = int.from_bytes(target.b[F['old_experience']:F['old_experience'] + 4], 'little', signed=True)
        r.set('experience', (previous if missing == 1 and experience < previous else threshold) & 0xFFFFFFFF)
    experience = int.from_bytes(target.b[F['experience']:F['experience'] + 4], 'little', signed=True)
    r.set('level_up_ready', int(experience >= 0 and can_level_up(target)))


def temple_spell(game, char, ident):
    if ident not in (17, 43, 75): raise ValueError('unsupported temple spell')
    game.spell_targets = [char]
    if ident != 43: game.current_spell = ident
    row = spell(game, ident)
    handler(game, row)(game, char, game.spell_targets, row)


HANDLERS = {1: _bless, 105: _bless, 3: _cure(1, 8, 0, 0), 58: _cure(2, 8, 1, 0), 71: _cure(3, 8, 0, 3),
            5: _plain('isAffectedText'), 11: _plain('isAffectedText'), 18: _plain('isAffectedText'), 22: _plain('isAffectedText'),
            29: _plain('isAffectedText'), 77: _plain('isAffectedText'), 103: _plain('isAffectedText'),
            6: _plain('isProtectedText'), 16: _plain('isProtectedText'), 52: _plain('isProtectedText'), 54: _plain('isProtectedText'),
            69: _plain('isProtectedText'), 101: _plain('isProtectedText'), 112: _plain('isProtectedText'),
            8: _plain('coldResistantText'), 24: _plain('fireResistantText'), 19: _plain('shieldedText'),
            30: _plain('invisibleText'), 50: _plain('invisibleText'), 109: _plain('invisibleText'), 38: _plain('blindText'),
            9: _burning, 107: _burning, 15: _missile, 20: _shock, 21: _sleep, 23: _hold, 49: _hold, 94: _hold,
            42: _prayer, 47: _fireball, 64: _fireball, 108: _fireball, 36: _nothing, 43: _remove_curse, 89: _remove_curse, 104: _remove_curse,
            7: _revive, 75: _revive, 17: _restoration, 66: _stone_to_flesh, 4: _charm, 10: _charm, 106: _charm,
            2: _barkskin, 12: _enlarge, 25: _plain('silencedText'), 102: _plain('silencedText'), 27: _nothing, 28: _hammer,
            31: _plain(''), 95: _plain(''), 97: _plain(''), 32: _mirror, 33: _plain('weakenedText'), 37: _cure_blindness,
            40: _harm, 44: _plain('cursedText'), 100: _plain('cursedText'), 45: _plain('blinkingText'),
            48: _rate(42, False, 'hastedText'), 55: _rate(39, True, 'slowedText'), 57: _speed_potion,
            61: _plain('paralyzedText'), 62: _heal_potion, 99: _heal_potion, 63: _plain('isProtectedText'),
            88: _plain('isProtectedText'), 90: _plain('isProtectedText'), 65: _dice_damage(2, 4, 2, 8), 73: _dispel_evil,
            74: _dice_damage(6, 8, 0, 9), 87: _dice_damage(3, 10, 0, 8), 79: _faerie, 80: _plain('invisibleText'),
            96: _youth, 98: _plain('coveredInFlameText'), 34: _cloud, 91: _cloud, 41: _dispel, 46: _dispel, 56: _death,
            60: _destroy(6, 'disintegratesText'), 72: _destroy(7, 'turnedToStoneText'), 76: _slay, 68: _poison, 67: _neutralize,
            51: _lightning, 92: _cone_of_cold, 84: _fear, 13: _reduce, 14: _friends, 26: _slow_poison, 35: _strength,
            39: _nothing, 53: _heal, 59: _giant_strength, 70: _snakes, 78: _entangle, 82: _confusion, 86: _fumble, 110: _stun,
            81: _charm_monsters, 83: _dimension_door, 85: _fire_shield, 93: _feeblemind, 111: _mass_charm, 113: _dance, 114: _blind_word}


def handler(game, row):
    h = HANDLERS.get(row.id)
    if h is None: raise BindingRequired('Death Knights spell not bound: %d %s' % (row.id, row.name))
    return h


def fit(game, char, verb):
    if char.b[F['status']] != camp.ANIMATED and char.b[F['active']]: return True
    camp.ack(game, _text(game, 'incapacitatedPrefix') + _text(game, verb), char)
    return False


def _camp_targets(game, caster, row):
    if getattr(game, 'noncombat_target', None) is None: game.noncombat_target = caster
    if row.camp_target == 1: return [caster]
    if row.camp_target == 3: return list(game.s.party)
    if row.camp_target != 2: return None
    party = game.s.party
    start = next((i for i, char in enumerate(party) if char is game.noncombat_target), 0)
    pick = choose(game, camp.Kind.SPELL, _text(game, 'spellTargetPrompt'), [camp.name(c) for c in party], spell=row.name, who=True, start=start)
    game.noncombat_target = None if pick is None else party[pick]
    return None if pick is None else [game.noncombat_target]


def cast_in_camp(game, caster, ident, done=False, announce=True):
    done = _cast_camp(game, caster, ident, done, announce)
    game.vm.clear_text()
    return done


def _cast_camp(game, caster, ident, done, announce):
    row = spell(game, ident)
    using_item = bool(getattr(game, 'using_item', False))
    if not row.camp_target:
        key = 'useItemPrompt' if using_item else 'loseQuery'
        lines = (_text(game, 'itemLabel'), _text(game, 'combatOnlyItemText')) if using_item else (row.name, _text(game, 'cantCastHereText'))
        if yes_no(game, camp.Kind.CONFIRM, _text(game, key), spell=row.name, lines=lines, start=0):
            if using_item: return True
            forget(caster, row.id)
        return done
    if announce and not using_item:
        game.ask(camp.Kind.ACK.value, ('Continue',), prompt=camp.name(caster) + ' ' + _text(game, 'castsText') + ' ' + row.name, spell=row.id, timed=1)
    targets = _camp_targets(game, caster, row)
    if targets is None: return False
    h = handler(game, row)
    from . import effects
    while effects.has_effect(caster, 25) is not None: effects.remove_effect(game, caster, 25)
    if not using_item: forget(caster, row.id)
    game.current_spell = row.id
    try: h(game, caster, targets, row)
    finally:
        game.current_spell = 0
        game.area_spell = False
    return True


def cast_menu(game, char):
    reset_target(game)
    if game.s.r0[0xE5]: return camp.ack(game, _text(game, 'antiMagicMessage'), char)
    if not fit(game, char, 'castingSuffix'): return
    index, redraw = -1, False
    while True:
        ident, index, present = spell_menu(game, char, 0, 1, index)
        if not present: camp.ack(game, _text(game, 'noSpellsMessage'), char)
        else: redraw = True
        if not ident: break
        cast_in_camp(game, char, ident)
    if redraw and game.s.mode == camp.CAMPING: camp.redraw_camp(game)


def reset_target(game):
    game.noncombat_target = None


def use_item(game, char, item, done=False):
    from . import inventory, shop
    fields = {key: offset for key, (offset, _) in Item.FIELDS.items()}
    battle = getattr(game, 'battle', None)
    is_scroll = readable(item)
    game.using_item = False
    if is_scroll:
        game.scroll = item
        ident = spell_menu(game, char, 2, 1, item=item, combat=battle is not None)[0]
    else:
        ident = item[fields['powers'] + 1] & MASK if item[fields['powers'] + 2] < 128 else 0
    if not ident: return False
    try:
        if not is_scroll:
            game.using_item = True
            game.ask(camp.Kind.ACK.value, ('Continue',), prompt=camp.name(char) + ' uses an item', item=shop.item_name(game, item), timed=1)
        game.using_item = True
        permitted = not is_scroll or lv(char, MAGE) > 0 or lv(char, CLERIC) > 0
        if not permitted and lv(char, THIEF) > 9: permitted = dice(game.s, 1, 100) <= 75
        if permitted:
            if battle is None: done = cast_in_camp(game, char, ident, done, False)
            else: done = battle.cast(battle.index(char), ident, using_item=True, ai=bool(char.b[F['auto_combat']]))
        else: _say(game, char, 'oops!')
    finally: game.using_item = False
    if battle is not None and spell(game, ident).combat_ok: done = battle.end(battle.index(char))
    if done:
        if is_scroll: remove_scroll_spell(char, item, ident, game)
        elif item[fields['powers']]:
            if item[fields['quantity']] > 1: item[fields['quantity']] -= 1
            else:
                item[fields['powers']] -= 1
                if not item[fields['powers']]: inventory.remove_item(char, item, game)
    return done


def test():
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from .menu import Game
    from ._creation_test import create_party
    with TemporaryDirectory() as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        assert spell(game, 15).name == 'Magic Missile' and spell(game, 3).camp_target == 2 and spell(game, 1).targeting == 10
        shown = []
        game.player = lambda kind, options, state, **info: shown.append(info.get('prompt')) or len(options) - 1
        cast_menu(game, game.s.party[0])
        who = camp.name(game.s.party[0])
        assert shown[-1].startswith(who + ' ') and 'spell' in shown[-1], shown
        char = game.s.party[0]
        if rules.spellbook(char) is not None:
            at = F['memorized']; char.b[at] = 15; forget(char, 15); assert char.b[at] == 15 | PENDING
    from ._magic_test import test as check
    check()
