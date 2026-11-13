from enum import Enum
import hashlib

from sm.files import DataError
from . import camp, creation, rules
from .creation import F, FIGHTER, KENDER, KNIGHT, MAGE, RANGER, STRENGTH, WISDOM, CONSTITUTION, TRAIN_MASK, gain_hp, know, levels, suborder, tables, xp


class Kind(str, Enum):
    TRAIN = 'CREATE_TRAIN'
    SPELL = 'CREATE_SPELL'
    KNIGHT = 'CREATE_KNIGHT'
    MODIFY = 'CREATE_MODIFY'
    ACK = 'ACK'


KNIGHT_REQUIRED = {1: (51166, 'b92df9e4fd54f5c77c291b79b89505b801a43794cc3823c31ab98ccc91242a85'),
                   2: (51172, 'c3213c834862b2ef31e76e5d6fc91f76e7abf3d8a3a02b349434ee224f9ebe56')}
START_XP = (1500, 1251, 2000, 2001, 2251, 2500, 5000)
ABILITY_COLUMNS = {0: None, 1: (6, 7), 2: (8, 9), 3: (10, 11), 4: (12, 13), 5: (14, 15)}
FIELD_NAME, FIELD_HP = 6, 7
FIELD_LABELS = creation.ABILITY_LABELS + ('Name', 'HP')


def ack(game, text):
    game.ask(Kind.ACK.value, ('Continue',), prompt=text)


def note(game, text):
    game.menu_note = text


def member_name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def knight_required(game, order):
    offset, sha = KNIGHT_REQUIRED[order]
    raw = game.assets.resident[offset:offset + 6]
    if hashlib.sha256(raw).hexdigest() != sha: raise DataError('Champions knight requirement table differs')
    return raw


def recalc_class_stats(char):
    rules.recalc_class_stats(char, rules.worn(char))


def base_ability(b, index):
    return b[F['abilities'] + 2 * index]


def next_xp(b, t, cls, level):
    return t.level_xp(suborder(b, cls), level)


def kender_capped(b, cls, level):
    return (b[F['race']] == KENDER and cls in (FIGHTER, RANGER) and
            (level == 7 or level == 6 and base_ability(b, STRENGTH) == 17 or level == 5 and base_ability(b, STRENGTH) < 17))


def assess(s, b, t):
    free, can, have, cap = s.g.get('free_training', 0), 0, 0, 0
    stale = None
    for cls, level in enumerate(levels(b)):
        if not level: continue
        have += t.classBits[cls]
        stale = cls, level
        if kender_capped(b, cls, level): continue
        need = next_xp(b, t, cls, level + 1)
        if need > 0 and (free or need <= xp(b)):
            if free and need > xp(b): set_xp(b, need)
            can += t.classBits[cls]
            after = next_xp(b, t, cls, level + 2)
            if 0 < after <= xp(b) and after > cap: cap = after - 1
    if stale:
        cls, level = stale
        need = next_xp(b, t, cls, level + 1)
        if need > 0 and any(t.classBits[c] & can for c in range(8)):
            after = next_xp(b, t, cls, level + 2)
            if 0 < after <= xp(b) and after > cap: cap = after - 1
    return can, have, cap


def set_xp(b, value):
    b[F['experience']:F['experience'] + 4] = value.to_bytes(4, 'little', signed=True)


LEARN_PAGE = 18


def learn_spell(game, char):
    b, t = char.b, tables(game.assets)
    row = 1 if b[F['robe_order']] == 1 else 2
    offered, levels = [], []
    for level in range(4):
        if b[F['spell_slots'] + 15 + level]:
            for spell in t.known_spells[row * 40 + level * 10:row * 40 + level * 10 + 10]:
                if not spell: break
                if not b[F['known_spells'] + spell - 1] and spell not in offered:
                    offered.append(spell)
                    levels.append(level)
    if offered:
        names = camp.tables(game.assets).names
        know(b, offered[game.ask(Kind.SPELL.value, tuple(names[s - 1] for s in offered), prompt='Learn', start=camp.opening_row(levels, LEARN_PAGE))])


def train(game, char):
    s, b, t = game.s, char.b, tables(game.assets)
    free = s.g.get('free_training', 0)
    if b[F['status']] and not free:
        ack(game, 'we only train conscious people')
        return False
    can, have, cap = assess(s, b, t)
    if cap: set_xp(b, cap)
    hall = s.r1[TRAIN_MASK] & 255
    if not free:
        if not have & hall:
            ack(game, "We don't train that class here")
            return False
        if not can & hall:
            ack(game, 'Not Enough Experience')
            return False
    allowed = can if free else can & hall
    offer = '; '.join('a level %d %s' % (level + 1, t.classes[cls]) for cls, level in enumerate(levels(b)) if level and t.classBits[cls] & allowed)
    if game.ask(Kind.TRAIN.value, ('Yes', 'No'), prompt='Do you wish to train? ', character=member_name(char), levels=offer):
        return False
    note(game, 'Congratulations...')
    mage_before, count = b[F['levels'] + MAGE], 0
    b[F['class_mask']] = 0
    for cls in range(8):
        if b[F['levels'] + cls]:
            count += 1
            if t.classBits[cls] & allowed:
                b[F['levels'] + cls] += 1
                if b[F['drained_levels']]:
                    b[F['drained_hp']] -= b[F['drained_hp']] // b[F['drained_levels']]
                    b[F['drained_levels']] -= 1
    recalc_class_stats(char)
    if b[F['levels'] + MAGE] > mage_before or b[F['levels'] + RANGER] > 8: learn_spell(game, char)
    if b[F['highest_level']] > b[F['dual_threshold']]: gain_hp(s, b, t, allowed, count)
    return True


def con_hp_bonus(b, cls):
    con = b[F['abilities'] + 2 * CONSTITUTION + 1]
    if con == 3: return -2
    if 4 <= con <= 6: return -1
    if con == 15: return 1
    if con == 16: return 2
    if 17 <= con <= 19: return con - 14 if cls in (FIGHTER, RANGER, KNIGHT) else 2
    return 0


def advance_order(char, t):
    b = char.b
    level = b[F['levels'] + KNIGHT]
    row = 4 if b[F['knight_order']] == 1 else 5
    if t.level_xp(row, level) > xp(b):
        b[F['levels'] + KNIGHT] -= 1
        loss = b[F['hp_rolled']] // (level + 1)
        b[F['hp_rolled']] -= loss
        b[F['hp_max']] = (b[F['hp_max']] - loss - con_hp_bonus(b, KNIGHT)) & 255
        if b[F['hp']] >= b[F['hp_max']]: b[F['hp']] = b[F['hp_max']]
    b[F['knight_order']] += 1
    recalc_class_stats(char)


def knight_promotion(game, char):
    b, t = char.b, tables(game.assets)
    order = b[F['knight_order']]
    if not b[F['levels'] + KNIGHT] or order == 3: return False
    target = 'Sword' if order == 1 else 'Rose'
    minimum = 3 if order == 1 else 4
    row = 4 if order == 1 else 5
    if b[F['levels'] + KNIGHT] < minimum or xp(b) < t.level_xp(row, minimum):
        verdict = member_name(char) + (' is too inexperienced.' if order == 1 else ' is too inexperienced')
    elif any(base_ability(b, a) < knight_required(game, order)[a] for a in range(6)): verdict = member_name(char) + ' does not qualify.'
    else:
        verdict = member_name(char) + ' may become a Knight Of The ' + target
        if game.ask(Kind.KNIGHT.value, ('Change', 'Exit'), prompt=verdict) == 0:
            advance_order(char, t)
            return True
        return False
    game.ask(Kind.KNIGHT.value, ('Exit',), prompt=verdict)
    return False


def hp_minimum(b, t):
    total, classes, con = 0, 0, 0
    for cls, level in enumerate(levels(b)):
        if not level: continue
        total = (total + level + (cls in (RANGER, KNIGHT))) & 255
        classes += 1
        con = (con + creation.con_bonus(b, t, cls)) & 255
    signed = con - 256 if con > 127 else con
    if signed < 0: return (total + signed) // classes if total > -signed + classes else 1
    return (total + signed) // classes


def hp_maximum(b, t):
    total, classes = 0, 0
    die = {0: 8, 1: 8, FIGHTER: 10, 3: 10, KNIGHT: 10, RANGER: 8, MAGE: 4, 6: 6}
    for cls, level in enumerate(levels(b)):
        if not level: continue
        classes += 1
        if level < t.hitDiceLimit[cls]:
            extra = cls == KNIGHT or cls == RANGER or cls == 0 and b[F['deity']] <= 4
            total = (total + (con_hp_bonus(b, cls) + die[cls]) * (level + extra)) & 255
        else:
            over = level - t.hitDiceLimit[cls] + 1
            total = {0: over * 2 + 72, 1: 112, FIGHTER: over * 3 + 90, 3: over * 3 + 90, KNIGHT: over * 3 + 90, RANGER: over * 2 + 88, MAGE: over + 44, 6: over * 2 + 60}[cls] & 255
    return total // classes


def adjust_ability(b, t, field, delta):
    race, gender, cls = b[F['race']], b[F['gender']], b[F['class']]
    at = F['abilities'] + 2 * field + 1
    low_col, high_col = (gender, 2 + gender) if field == STRENGTH else ABILITY_COLUMNS[field]
    low, high = t.race_limit(race, low_col), t.race_limit(race, high_col)
    value = b[at] + delta
    if delta > 0:
        if value > high:
            if field == STRENGTH and value > 18 and any(b[F['levels'] + c] for c in (FIGHTER, KNIGHT, RANGER)) and t.race_limit(race, 4 + gender) > b[F['strength_extra']]:
                b[F['strength_extra']] += 1
            value = high
    elif field == STRENGTH and b[F['strength_extra']]:
        b[F['strength_extra']] -= 1
        value += 1
    else:
        value = max(value, low, t.classMin[cls * 6 + field])
    b[at] = value
    if field == WISDOM and b[F['spell_slots']]: b[F['spell_slots']] = 1
    if field == CONSTITUTION:
        if delta > 0: b[F['hp_max']] = max(b[F['hp_max']], hp_minimum(b, t))
        else: b[F['hp_max']] = min(b[F['hp_max']], hp_maximum(b, t))
        b[F['hp']] = b[F['hp_max']]


def adjust(char, t, field, delta):
    b = char.b
    if field < FIELD_NAME: adjust_ability(b, t, field, delta)
    elif field == FIELD_HP:
        hp = (b[F['hp_max']] + delta) & 255
        b[F['hp_max']] = b[F['hp']] = min(hp, hp_maximum(b, t)) if delta > 0 else max(hp, hp_minimum(b, t))
    rules.recalc_stats(char)


def keep_modified(char, t):
    b = char.b
    recalc_class_stats(char)
    b[F['modified']] = 1
    total, classes = 0, 0
    for cls, level in enumerate(levels(b)):
        if not level: continue
        classes += 1
        if level < t.hitDiceLimit[cls]: total = (total + con_hp_bonus(b, cls) * (level + (cls == RANGER))) & 255
        else: total = (total + con_hp_bonus(b, cls) * (t.hitDiceLimit[cls] - 1)) & 255
    b[F['hp_rolled']] = (b[F['hp_max']] - total // classes) & 255
    for a in range(6): b[F['abilities'] + 2 * a] = b[F['abilities'] + 2 * a + 1]
    b[F['strength_extra_base']] = b[F['strength_extra']]


def modify(game, char):
    b, t = char.b, tables(game.assets)
    if xp(b) not in START_XP or b[F['dual_threshold']]:
        ack(game, member_name(char) + " can't be modified.")
        return False
    saved = bytes(b[F['abilities']:F['abilities'] + 12]), b[F['strength_extra']], b[F['hp_max']], bytes(b[:16])
    field = 0
    while True:
        options = ('Rename', 'Keep', 'Exit', 'Next', 'Previous') if field == FIELD_NAME else ('Add', 'Subtract', 'Keep', 'Exit', 'Next', 'Previous')
        info = creation.summary(b, t)
        action = options[game.ask(Kind.MODIFY.value, options, prompt='Modify: ', field=FIELD_LABELS[field], name=member_name(char), **info)]
        if action == 'Keep':
            keep_modified(char, t)
            return True
        if action == 'Exit':
            for a in range(6): b[F['abilities'] + 2 * a + 1] = saved[0][2 * a + 1]
            b[F['strength_extra']], b[F['hp_max']], b[F['hp']], b[:16] = saved[1], saved[2], saved[2], saved[3]
            rules.recalc_stats(char)
            return False
        if action == 'Next': field = (field + 1) % 8
        elif action == 'Previous': field = (field - 1) % 8
        elif action == 'Rename':
            raw = creation.read_name(game, creation.Kind.NAME, 'Character name: ', 15)
            b[F['name']:F['name'] + 16] = bytes([len(raw)]) + raw + bytes(15 - len(raw))
        else: adjust(char, t, field, 1 if action == 'Add' else -1)


def run(game):
    return creation.run(game)
