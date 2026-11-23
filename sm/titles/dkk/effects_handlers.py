from . import effects, rules
from .creation import dice
from .faults import BindingRequired
from .records import Item

F = rules.F
I = {key: offset for key, (offset, _) in Item.FIELDS.items()}


def owner(game):
    return getattr(game, 'game', game)


def say(game, char, key, roll, hold=True, anim=False):
    tell(game, char, game.assets.text(key), roll, hold, anim)


def tell(game, char, text, roll, hold=True, anim=False):
    if 'message' in roll.services:
        roll.call('message', char, text)
    else:
        from .magic import _say
        _say(game, char, text)
    if anim and 'name_anim' in roll.services: roll.call('name_anim', char)
    elif hold and 'pause' in roll.services: roll.call('pause')


def armor(char, amount):
    for at in (F['ac'], F['ac'] + 1): char.b[at] = (char.b[at] + amount) & 255


def renewal(game, char, node, minutes):
    if getattr(owner(game), 'effect_busy', False): return False
    effects.add_effect(char, node[0], minutes, node[3], True)
    return True


def actor(game, char):
    battle = game.battle
    return battle.record(battle.index(char))


def target(game, char):
    index = actor(game, char)['target']
    return game.battle.chars[index] if index >= 0 else None


def take_control(char):
    char.b[F['auto_combat']] = 1
    char.b[F['npc']] = 179 if char.b[F['npc']] <= 127 or char.b[F['npc']] == 179 else 178


def release_control(char, keep_quick=False):
    if char.b[F['npc']] == 179:
        char.b[F['npc']] = 0
        if not keep_quick: char.b[F['auto_combat']] = 0


def end_actions(game, char, node, removed, roll):
    if roll.in_combat: roll.call('end_actions', char)


def stun(game, char, node, removed, roll):
    if removed or not roll.in_combat: return
    who = target(game, char)
    if not roll.call('saving_throw', who, 1, 0):
        game.battle.add_with_message(game.battle.index(who), 6, 3, 0, False, game.assets.text('stunnedText'))


def snakes(game, char, node, removed, roll):
    attacks = sum(char.b[F['attacks_left']:F['attacks_left'] + 2]) & 255
    if node[3] > attacks: node[3] -= attacks
    else: effects.remove_effect(game, char, 3)
    say(game, char, 'fightingSnakesText', roll, anim=True)
    end_actions(game, char, node, removed, roll)


def dispelling(game, char, node, removed, roll):
    if not removed and roll.attacker is not None and roll.attacker.b[F['creature_type']] & 1: roll.attack -= 7


def charm(game, char, node, removed, roll):
    if removed:
        char.b[F['side']] = node[3] >> 6 & 1
        release_control(char)
    else:
        if not node[3] & 32:
            node[3] = (node[3] + 32 + 64 * char.b[F['side']]) & 255
            char.b[F['side']], char.b[F['auto_combat']] = node[3] >> 7, 1
            if char.b[F['npc']] <= 127: char.b[F['npc']] = 179
            roll.call('clear_target', char)
            game.battle.teams()
        roll.morale = 100
        battle = getattr(game, 'battle', None)
        if battle is not None: battle.data['morale'] = 100


def armor_change(amount):
    return lambda game, char, node, removed, roll: armor(char, amount)


def resistance(mask, removal_guard=False):
    def apply(game, char, node, removed, roll):
        if roll.element & mask and not (removal_guard and removed):
            roll.damage //= 2
            roll.save += 3
    return apply


def shield(game, char, node, removed, roll):
    char.b[F['ac']] = max(char.b[F['ac']], 57)
    roll.save += 1
    if roll.spell == 15: roll.damage = 0


def silence(game, char, node, removed, roll):
    if not roll.in_combat: return
    state = actor(game, char)
    if state['item_ok']: say(game, char, 'silencedText', roll)
    state.update(item_ok=False, cast_ok=False)
    if state['casting'] > 0:
        from .magic import forget
        say(game, char, 'lostSpellMessage', roll)
        forget(char, state['casting'])
        end_actions(game, char, node, removed, roll)


def invisible(game, char, node, removed, roll):
    if not removed and (roll.attacker is None or not effects.has(roll.attacker, 24)):
        roll.attack -= 4
        roll.target_veto = True


def weakened(game, char, node, removed, roll):
    roll.damage -= roll.damage // 4


def mirror(game, char, node, removed, roll):
    missed = dice(game.s, 1, node[3] // 16 + 1) > 1
    if missed and (not roll.spell or not roll.multi_target):
        effects.nullify(roll)
        say(game, char, 'lostImageText', roll)
        node[3] = node[3] - 1 & 255
        if node[3] == 0: effects.remove_effect(game, char, 28)


def coughing(game, char, node, removed, roll):
    if not roll.in_combat: return
    state = actor(game, char)
    if state['item_ok']: say(game, char, 'coughingText', roll)
    state.update(item_ok=False, cast_ok=False)
    effects.recalc_stats(game, char)
    armor(char, -2)
    battle = game.battle
    if battle.data.get('panel_due') and battle.data.get('actor') == battle.index(char): battle.panel(battle.index(char))


def invisible_flag(game, char, node, removed, roll):
    if not removed and char.b[F['creature_type']] & 64 and not effects.has(char, 24):
        roll.attack -= 4
        roll.target_veto = True


def blind(game, char, node, removed, roll):
    armor(char, -4)
    roll.attack -= 4
    roll.save -= 4


def dispel_touch(game, char, node, removed, roll):
    if removed or not roll.in_combat: return
    who = target(game, char)
    if who.b[F['creature_type']] & 1 and not roll.call('saving_throw', who, 4, 0):
        game.battle.kill(game.battle.index(who), 8, game.assets.text('dispelledText'))
        for ident in (4, 34): effects.remove_effect(game, char, ident)
    else:
        say(game, who, 'resistsDispelEvilText', roll)
        roll.call('pause')


def cursed(game, char, node, removed, roll):
    roll.attack -= 4
    roll.save -= 4


def blinking(game, char, node, removed, roll):
    if roll.in_combat and actor(game, char)['initiative'] == 0:
        roll.attack, roll.target_veto = -1, True


def haste(game, char, node, removed, roll):
    if removed: return
    if not node[3] & 16:
        node[3] = node[3] + 16 & 255
        say(game, char, 'agesText', roll)
        record = rules.record(char)
        record.set('age', record.get('age') + 1 & 65535)
        owner(game).age_pass = True
    roll.multiplier = roll.multiplier * 2 & 255


def slow(game, char, node, removed, roll):
    if not removed: roll.multiplier //= 2


def dwarf_defense(game, char, node, removed, roll):
    if roll.attacker is not None and roll.attacker.b[F['creature_type']] & 4: roll.attack -= 4


def barkskin(game, char, node, removed, roll):
    from .magic import spell
    armor(char, 1)
    if not roll.spell or spell(game, roll.spell).save_type != 4: roll.save += 1


def fire_shield(game, char, node, removed, roll):
    hot = node[0] == 50
    if roll.element & (2 if hot else 1): roll.save += 2
    elif roll.element & (1 if hot else 2):
        protected = roll.save_passed if hot else game.s.g.get('save.recent', 0)
        if not protected: roll.damage *= 2


def mind_blank(game, char, node, removed, roll):
    if roll.effect in (11, 35, 52, 61, 111): effects.nullify(roll)


def globe(game, char, node, removed, roll):
    from .magic import spell
    if roll.spell and spell(game, roll.spell).level < (5 if node[0] == 59 else 4): effects.nullify(roll)


def electricity(game, char, node, removed, roll):
    if roll.element & 4: roll.damage = 0


def weapon_gate(game, char, node, removed, roll):
    item = roll.call('damaging_weapon', roll.attacker)
    monster = rules._s8(roll.attacker.b[F['race']]) >= 7 and rules._s8(roll.attacker.b[F['highest_level']]) >= 4
    insufficient = item is None or (rules._s8(item[I['bonus']]) < 3 if node[0] == 66 else item[I['bonus']] == 0)
    if not monster and insufficient: roll.damage = 0


def missile_protection(game, char, node, removed, roll):
    item = roll.call('damaging_weapon', roll.attacker)
    if item is None or item[I['bonus']] or not roll.in_combat: return
    battle = game.battle
    if battle.weapon(battle.index(roll.attacker)) is None or roll.call('distance', roll.attacker, char) <= 1: return
    dice(game.s, 1, 100)
    say(game, char, 'avoidsItText', roll)
    roll.damage, roll.attack = 0, -1
    hits = battle.data.get('hits_made', 0)
    if isinstance(hits, list): hits[0] = (hits[0] - 1) & 255
    else: battle.data['hits_made'] = (hits - 1) & 255


def immune_breath(game, char, node, removed, roll):
    if roll.element & 32:
        effects.nullify(roll)
        say(game, char, 'unaffectedMessage', roll)


def cold_vulnerable(game, char, node, removed, roll):
    if roll.element & 2: roll.damage *= 2


def fire_touch(game, char, node, removed, roll):
    if not roll.in_combat: return
    who = target(game, char)
    if who is None: return
    roll.element, roll.dice_count = 0, 2
    roll.damage = dice(game.s, 2, 6)
    saved = roll.call('saving_throw', who, 4, 0)
    game.battle.spell_damage(who, roll, 2, saved)


def heal_raw(game, char, amount, roll):
    say(game, char, 'healedMessage', roll)
    char.b[F['hp']] = min((char.b[F['hp']] + amount) & 255, char.b[F['hp_max']])


def healed_by_fire(game, char, node, removed, roll):
    if roll.element & 1:
        if roll.element & 8: heal_raw(game, char, roll.damage, roll)
        effects.nullify(roll)


def dual_resistance(game, char, node, removed, roll):
    if roll.element & 6: roll.damage //= 2


def regenerate_three(game, char, node, removed, roll):
    if char.b[F['hp']] < char.b[F['hp_max']]:
        char.b[F['hp']] = min((char.b[F['hp']] + 3) & 255, char.b[F['hp_max']])


def golem(game, char, node, removed, roll):
    iron = node[0] == 87
    if roll.element & (1 if iron else 4) and roll.element & 8:
        heal_raw(game, char, roll.damage if iron else roll.dice_count, roll)
    elif roll.element & 4 if iron else roll.element & 3 and roll.element & 8:
        effects.add_effect(char, 42, 3 if iron else dice(game.s, 2, 6), 255, False)
        tell(game, char, game.assets.text('isText') + game.assets.names('effectNames')[41], roll)
    effects.nullify(roll)


def displacement(game, char, node, removed, roll):
    round_number = game.battle.data['round'] if roll.in_combat else 0
    if round_number == 0 and roll.attack == 0: node[3] &= 15
    elif not node[3] & 16:
        roll.attack = -1
        node[3] |= 16


def half_weapon(game, char, node, removed, roll):
    item = roll.call('damaging_weapon', roll.attacker)
    if item is not None and rules.tables().base_item(item[I['type']])[7] <= 1: roll.damage //= 2


def fear(game, char, node, removed, roll):
    if removed:
        release_control(char)
        if roll.in_combat: roll.call('set_turned', char, 0)


def weapon_bonus(game, char, node, removed, roll):
    if not roll.in_combat or node[0] == 117 and removed: return
    who = target(game, char)
    if node[0] == 114:
        if who.b[F['target_flags']] & 1: roll.damage = char.b[F['hp']]
    elif node[0] == 115:
        if who.b[F['creature_type']] & 32: roll.damage += 3
    elif who.b[F['creature_type']] & 2: roll.damage *= 2
    elif who.b[F['undead']]: game.battle.kill(game.battle.index(who), 8, game.assets.text('disruptedText'))


def stench_penalty(game, char, node, removed, roll):
    roll.attack -= 2


def grant_item_effect(game, char, item, removed=False):
    owner(game).handler_override_active = False
    if 'handler_override_active' in game.__dict__: game.handler_override_active = False
    ident = item[I['powers'] + 1]
    if removed: effects.remove_effect(game, char, ident)
    else: effects.add_effect(char, ident, 0, 255, True)


def regeneration(game, char, node, removed, roll):
    if not renewal(game, char, node, 60): return
    if not effects.restore_hp(char, 1, True, roll.in_combat): return
    key = 'fullyHealedText' if char.b[F['hp']] == char.b[F['hp_max']] else 'partiallyHealedText'
    say(game, char, key, roll)
    if not roll.in_combat:
        from .camp import repaint_walking_row
        repaint_walking_row(game, char)


def poison_tick(game, char, node, removed, roll):
    if not renewal(game, char, node, 10) or char.b[F['hp']] <= 1: return
    roll.element, roll.damage = 0, 1
    if roll.in_combat: game.battle.spell_damage(char, roll, 0, False)
    else:
        effects.trigger_condition(game, 6, char, roll)
        effects.trigger_condition(game, 20, char, roll)
        damage = roll.damage & 255
        if damage and char.b[F['active']]:
            t = game.assets.text
            text = t('takesPrefix') + str(damage) + t('pointsDamage') if damage != 1 else t('onePointDamage')
            text += {1: t('fromFire'), 2: t('fromCold'), 4: t('fromElectricity'), 16: t('fromAcid')}.get(roll.element & 0xF7, '')
            if roll.element & 8 == roll.element: text += t('fromMagic')
            from .magic import _timed
            _timed(game, char, text)
            char.b[F['hp']] = max(0, char.b[F['hp']] - damage)
        from .camp import repaint_walking_row
        repaint_walking_row(game, char)


def poison_end(game, char, node, removed, roll):
    if effects.has(char, 55):
        if roll.in_combat: game.battle.kill(game.battle.index(char), 4, game.assets.text('poisonCollapseText'))
        else:
            say(game, char, 'poisonCollapseText', roll)
            if char.b[F['status']] not in (6, 7, 8):
                char.b[F['status']], char.b[F['hp']], char.b[F['active']] = 4, 0, 0
                for ident in effects._hp_zero_ids(game): effects.remove_effect(game, char, ident)
    owner(game).effect_busy = True
    try: effects.remove_effect(game, char, 15)
    finally: owner(game).effect_busy = False


def poison_attack(game, char, node, removed, roll):
    if not roll.in_combat: return
    who = target(game, char)
    modifier = -2 if node[0] == 86 else 0
    resistance = effects.has_effect(who, 116)
    if resistance is not None: modifier = 0 if modifier < 0 else rules._s8(modifier + resistance[3] & 255)
    saved = roll.call('saving_throw', who, 0, modifier & 255)
    if saved or who.b[F['target_flags']] & 8: return
    say(game, who, 'poisonedMessage', roll, False)
    roll.call('pause')
    effects.add_effect(who, 55, 0, 255, False)
    game.battle.kill(game.battle.index(who), 6, game.assets.text('killedMessage'))


def hammer(game, char, node, removed, roll):
    held = next((item for item in char.items if item[I['type']] == 6 and item[I['name_ids'] + 2] == 121), None)
    if removed and held is not None:
        from .inventory import remove_item
        remove_item(char, held, game)
    elif not removed and held is None and char.b[F['item_count']] < 16:
        from .inventory import copy_item
        made = bytearray(Item.SIZE)
        for offset, value in ((I['type'], 6), (I['name_ids'] + 1, 6), (I['name_ids'] + 2, 121),
                              (I['bonus'], 1), (I['powers'] + 1, 23), (I['powers'] + 2, 128)):
            made[offset] = value
        item = copy_item(owner(game), char, made)
        if item is not None: char.items.append(item)
        say(game, char, 'gainsItemText', roll)
    effects.recalc_stats(game, char)


def paralyze(game, char, node, removed, roll):
    if not roll.in_combat: return
    who = target(game, char)
    if node[0] == 88 and rules._s8(who.b[F['race']]) <= 1: return
    if not roll.call('saving_throw', who, 0, 0):
        say(game, who, 'paralyzedText', roll, anim=True)
        effects.add_effect(who, 52, 100, 12, False)


def flee(game, char):
    char.b[F['auto_combat']] = 1
    if char.b[F['npc']] <= 127: char.b[F['npc']] = 179
    actor(game, char).update(target=-1, turned=1)


def berserk(game, char, node, removed, roll):
    confused = node[0] == 107
    if removed or confused and not roll.in_combat:
        release_control(char, keep_quick=confused)
        char.b[F['side']] = node[3] if confused else 0
        return
    take_control(char)
    if not roll.in_combat: return
    state, battle = actor(game, char), game.battle
    state['target'] = -1
    targets = battle.targets(battle.index(char), 255, allies=True)
    targets = (targets if len(targets) > 1 else battle.data.get('target_list', ()))[1:2]
    if targets and targets[0] < len(battle.chars):
        state['target'] = targets[0]
        char.b[F['side']] = battle.chars[targets[0]].b[F['side']] ^ 1
    if not confused:
        state['cast_ok'] = False
        say(game, char, 'berserkText', roll)


def confusion(game, char, node, removed, roll):
    if not roll.in_combat: return
    value = dice(game.s, 1, 100)
    battle, index = game.battle, game.battle.index(char)
    if value <= 10:
        effects.remove_effect(game, char, 35)
        flee(game, char)
        battle.add_with_message(index, 111, 10, 0, True, game.assets.text('runsAwayText'), False, 1)
    elif value <= 60:
        say(game, char, 'confusedText', roll, anim=True)
        end_actions(game, char, node, removed, roll)
    elif value <= 80:
        battle.add_with_message(index, 77, 1, char.b[F['side']], True, game.assets.text('berserkText'), False, 1)
        berserk(game, char, bytearray((77, 0, 0, 0)), False, roll)
    else: say(game, char, 'enragedText', roll, anim=True)
    if roll.call('saving_throw', char, 4, 254): effects.remove_effect(game, char, 35)


def dragon_fear(game, char, node, removed, roll):
    for who in roll.call('neighbours', char):
        if who.b[F['side']] == char.b[F['side']] or effects.has(who, 92): continue
        if not roll.call('saving_throw', who, 4, 0):
            game.battle.add_with_message(game.battle.index(who), 111, 0, 0, True, game.assets.text('terrifiedText'), False, 1)
            if effects.has(who, 111): flee(game, who)


def stench(game, char, node, removed, roll):
    say(game, char, 'evilStenchText', roll, False)
    for who in roll.call('neighbours', char):
        if who.b[F['side']] != char.b[F['side']] and not roll.call('saving_throw', who, 4, 0) and not effects.has(who, 118):
            say(game, who, 'affectedText', roll, anim=True)
            effects.add_effect(char, 118, 0, 255, False)


def trim_drained_spells(game, char):
    from .magic import F as spell_fields, spell
    book = rules.spellbook(char)
    if book is None: return
    bonus = 255
    if rules._s8(char.b[F['levels'] + 5]) > 0:
        phase = game.s.r0[0x1F8 + char.b[F['robe_order']]]
        bonus = phase if phase in (1, 2) else 0
    capacity, used = book.get('spell_slots'), [0] * 32
    for pending in (False, True):
        for at in range(spell_fields['memorized'], spell_fields['memorized'] + 74):
            value = char.b[at]
            if not value or (value > 127) != pending: continue
            row = spell(game, value)
            slot = row.cast_class * 8 + row.level - 1
            if not 0 <= slot < 32: raise BindingRequired('Drained spell slot outside declared storage')
            if used[slot] < capacity[slot]:
                used[slot] += 1
                continue
            if not pending and row.cast_class == 3 and capacity[slot] and bonus:
                bonus -= 1
                continue
            char.b[at] = 0


def level_threshold(who, cls, level):
    from . import creation
    tables = rules.tables()
    if 2 <= level <= 18: return tables.level_xp(creation.suborder(who, cls), level)
    at = tables.offset['classProgression'] + creation.suborder(who, cls) * 204 + (level - 2) * 4
    return int.from_bytes(tables.image[at:at + 4], 'little', signed=True)


def drain_levels(game, char, count, roll):
    from . import creation
    who = target(game, char)
    if who is None: return
    say(game, who, 'drainedText', roll, False)
    roll.call('pause')
    r, tables, hp_tables = rules.record(who), rules.tables(), creation.tables(game.assets)
    def experience(field):
        start = F[field]
        return int.from_bytes(who.b[start:start + 4], 'little', signed=True)
    def threshold(cls, level): return level_threshold(who, cls, level)
    selected = None
    for _ in range(count):
        current = [rules._s8(value) for value in r.get('levels')]
        former = [rules._s8(value) for value in r.get('former_levels')]
        count = sum(level > 0 or peak > 0 for level, peak in zip(current, former))
        highest = max(0, *current)
        if highest:
            candidates = [cls for cls, level in enumerate(current) if level == highest]
            selected = max(candidates, key=lambda cls: threshold(cls, highest)) if len(candidates) > 1 else candidates[0]
        elif selected is None: raise BindingRequired('Drain class selection is unset without positive levels')
        if former[selected] <= highest: who.b[F['former_levels'] + selected] = highest
        if experience('old_experience') <= experience('experience'): r.set('old_experience', r.get('experience'))
        if r.get('old_hp_max') <= r.get('hp_max'): r.set('old_hp_max', r.get('hp_max'))
        lower = 0 if highest in (1, 2) else threshold(selected, highest - 1)
        upper = 0 if highest == 1 else threshold(selected, highest)
        difference = (upper - lower + 0x80000000) % 0x100000000 - 0x80000000
        midpoint = lower + abs(difference) // 2 * (-1 if difference < 0 else 1)
        r.set('experience', midpoint & 0xFFFFFFFF)
        who.b[F['levels'] + selected] = highest - 1 & 255
        creation.adjust_level_hp(game.s, who, hp_tables.classBits[selected], count, False, hp_tables)
        rules.recalc_class_stats(who)
        trim_drained_spells(game, who)
    if not any(rules._s8(value) > 0 for value in r.get('levels')) or not r.get('hp_max'):
        game.battle.kill(game.battle.index(who), 8, game.assets.text('drainDeathText'))
    elif not r.get('hp'):
        game.battle.kill(game.battle.index(who), 4, game.assets.text('drainCollapseText'))


def drain_one(game, char, node, removed, roll):
    drain_levels(game, char, 1, roll)


def drain_two(game, char, node, removed, roll):
    drain_levels(game, char, 2, roll)


def immolate(game, char, node, removed, roll):
    from .magic import scatter
    battle = game.battle; i = battle.index(char)
    battle.data['aim'] = battle.position(i)
    scatter(battle, i, 0, *battle.data['aim'], 1, 24)
    for who in roll.call('neighbours', char):
        roll.element, roll.dice_count = 1, 1
        roll.damage = dice(game.s, 1, 6)
        game.battle.spell_damage(who, roll, 0, False)


def zap(game, char, node, removed, roll):
    if roll.call('distance', roll.attacker, char) >= 2: return
    damage, element = roll.damage, roll.element
    roll.damage, roll.element = damage * 2 & 255, 8
    say(game, roll.attacker, 'zappedText', roll)
    try: game.battle.spell_damage(roll.attacker, roll, 0, False)
    finally: roll.damage, roll.element = damage, element


def reflect(game, char, node, removed, roll):
    value = dice(game.s, 1, 10)
    if not 0 <= roll.spell <= 114: raise BindingRequired('Spell reflection outside a spell reads an undeclared spell row')
    from .magic import spell
    targeting = spell(owner(game), roll.spell).targeting if roll.spell else 0
    if not (value == 1 and targeting < 8 or targeting > 14): return
    battle = getattr(game, 'battle', None)
    if battle is None or not roll.in_combat: raise BindingRequired('Spell reflection outside a fight is unverified')
    say(game, char, 'reflectsSpellText', roll, False)
    caster = battle.chars[battle.data['actor']]
    battle.data['aim'] = battle.position(battle.index(caster))
    targets = getattr(battle.game, 'spell_targets', None)
    if targets is not None: roll.call('replace_spell_targets', char, caster)
    if targets and any(targets[0] is c for c in battle.chars):
        from .magic import flight
        flight(battle, *battle.position(battle.index(char)), *battle.position(battle.index(targets[0])), 18, 1, 30)
    roll.call('redirect_target', caster)


HANDLERS = {
    2: stun, 3: snakes, 4: dispelling, 6: end_actions, 10: resistance(2), 11: charm,
    13: armor_change(-2), 15: poison_tick, 17: shield, 20: resistance(1, True), 21: silence, 22: poison_end, 23: hammer, 25: invisible,
    27: end_actions, 28: mirror, 29: weakened, 30: coughing, 31: end_actions, 32: invisible_flag, 33: blind, 34: dispel_touch,
    35: confusion, 36: cursed, 37: blinking, 39: haste, 41: missile_protection, 42: slow, 47: dwarf_defense,
    48: barkskin, 50: fire_shield, 52: end_actions, 53: end_actions, 54: fire_shield,
    57: armor_change(-4), 58: mind_blank, 59: globe, 60: armor_change(4), 62: regeneration, 63: globe, 64: poison_attack,
    65: electricity, 66: weapon_gate, 67: drain_one, 68: drain_two, 69: paralyze, 70: immolate, 71: reflect, 72: dragon_fear, 73: immune_breath, 74: fire_touch, 75: cold_vulnerable,
    76: healed_by_fire, 77: berserk, 79: stench, 83: dual_resistance, 84: regenerate_three, 86: poison_attack, 87: golem, 88: paralyze,
    89: displacement, 93: half_weapon, 101: golem, 103: weapon_gate, 107: berserk, 111: fear, 112: zap,
    114: weapon_bonus, 115: weapon_bonus, 117: weapon_bonus, 118: stench_penalty,
}


def test():
    from ._effects_test import test as check_handlers
    check_handlers()
