import struct
from functools import lru_cache

from sm.files import file_path
from sm.titles.ssb.state import Char
from . import save as codec
from .data import Assets
from .faults import BindingRequired
from .records import Character, Item

CLERIC, FIGHTER, RANGER, MAGE, THIEF, KNIGHT = 0, 2, 4, 5, 6, 7
SILVANESTI, QUALINESTI, DWARVES, KENDER, HUMAN, MONSTER = 0, 1, (3, 4), 5, 6, 7
HOOPAK, ARROWS, QUARRELS = 67, 30, 12
BASE_ITEM_SIZE, BASE_ITEMS = 16, 129
PROGRESSION_ROW, PROGRESSION_SPELLS = 99, 44
SLOT, HANDS, ARMOR, SMALL_ROLLS, SMALL_DICE, SMALL_BONUS, USABLE_BY, PROPS = 0, 1, 6, 9, 10, 11, 13, 14
SKILL_BONUS_ON_ENTRY = 7


class _Tables:
    def __init__(self, directory=None):
        assets = Assets(directory)
        self.image = assets.resident
        self.offset = {name: table['offset'] for name, table in assets.layout['tables'].items()}
        for name in assets.layout['tables']:
            assets.table(name)
        rows = file_path(assets.root, 'ITEMS').read_bytes()[2:]
        self.base = rows[:BASE_ITEM_SIZE * BASE_ITEMS].ljust(BASE_ITEM_SIZE * BASE_ITEMS, b'\0')

    def u8(self, name, index):
        return self.image[self.offset[name] + index]

    def s8(self, name, index):
        return _s8(self.u8(name, index))

    def base_item(self, kind):
        if kind >= BASE_ITEMS:
            raise ValueError('item type outside the base item table: %d' % kind)
        return self.base[kind * BASE_ITEM_SIZE:(kind + 1) * BASE_ITEM_SIZE]

    def gained_slots(self, row, level, spell_level):
        return self.u8('classProgression', row * PROGRESSION_ROW + PROGRESSION_SPELLS + (level - 2) * 5 + spell_level - 1)

    def save_needed(self, class_slot, level, kind):
        return self.u8('savingThrowTable', (class_slot * 12 + level - 1) * 5 + kind)


@lru_cache(maxsize=None)
def tables(directory=None):
    return _Tables(directory)


def _s8(value):
    return (value + 128) % 256 - 128


def _s16(value):
    return (value + 32768) % 65536 - 32768


def _view(kind, buffer):
    record = kind.__new__(kind)
    record.data = buffer
    return record


def _signed(record, name):
    raw = record.get(name)
    return struct.unpack('%db' % len(raw), raw)


def _ability(record, index):
    return record.get('abilities')[index * 2 + 1]


def _race(record):
    return _s8(record.get('race'))


def character(record_bytes, items=(), effects=(), rid=None):
    return Char(bytes(Character(record_bytes)), items, effects, rid)


def _bands(value, rows, default=0):
    for low, high, result in rows:
        if low <= value <= high:
            return result(value) if callable(result) else result
    return default


def _strength_rank(record):
    strength, extra = _ability(record, 0), record.get('strength_extra')
    if strength <= 17:
        return strength
    if 19 <= strength <= 25:
        return strength + 5
    if strength != 18 or extra > 100:
        raise ValueError('strength outside the defined scale: %d/%d' % (strength, extra))
    return 18 if extra == 0 else 19 + sum(extra > limit for limit in (50, 75, 90, 99))


def _hit_strength(record):
    if not record.get('use_strength'):
        return 0
    return _bands(_strength_rank(record), ((1, 3, -3), (4, 5, -2), (6, 7, -1), (17, 19, 1), (20, 22, 2),
                                           (23, 25, 3), (26, 27, 4), (28, 30, lambda v: v - 23)))


def _damage_strength(record):
    if not record.get('use_strength'):
        return 0
    return _bands(_strength_rank(record), ((1, 2, -2), (3, 5, -1), (16, 16, 1), (17, 19, lambda v: v - 16),
                                           (20, 29, lambda v: v - 17), (30, 30, 14)))


def _carry_allowance(record):
    return _bands(_strength_rank(record), (
        (1, 3, -350), (4, 5, -250), (6, 7, -150), (12, 13, 100), (14, 15, 200), (16, 16, 350),
        (17, 21, lambda v: (v - 17) * 250 + 500), (22, 26, lambda v: (v - 22) * 1000 + 2000), (27, 27, 7500),
        (28, 30, lambda v: (v - 28) * 3000 + 9000)))


def _dex_armor(record):
    return _bands(_ability(record, 3), ((1, 3, -4), (4, 6, lambda v: v - 7), (15, 18, lambda v: v - 14),
                                        (19, 20, 4), (21, 23, 5), (24, 25, 6)))


def _dex_missile(record):
    return _bands(_ability(record, 3), ((0, 2, -4), (3, 5, lambda v: v - 6), (16, 18, lambda v: v - 15),
                                        (19, 20, 3), (21, 23, 4), (24, 25, 5)))


def worn(char):
    rules, slots = tables(), [None] * 13
    for raw in char.items:
        item = _view(Item, raw)
        if not item.get('readied'):
            continue
        kind = item.get('type')
        slot = rules.base_item(kind)[SLOT]
        if slot <= 8:
            slots[slot] = item
        elif slot == 9:
            if slots[9] is None:
                slots[9] = item
            elif slots[10] is None:
                slots[10] = item
        if kind == ARROWS:
            slots[11] = item
        if kind == QUARRELS:
            slots[12] = item
    return slots


def _earlier_class_active(record):
    level = 0
    if _race(record) == HUMAN:
        levels = _signed(record, 'levels')
        level = levels[next((i for i in range(7) if levels[i]), 7)]
    return level > _s8(record.get('dual_threshold'))


def _weapon_damage(record, slots, rules):
    weapon = slots[0]
    kind = weapon.get('type')
    base = rules.base_item(kind)
    props = base[PROPS]
    thac0 = record.get('base_thac0')
    if props & 2:
        thac0 += _dex_missile(record)
    damage = _s8(base[SMALL_BONUS])
    if props & 4:
        thac0 += _hit_strength(record)
        damage += _damage_strength(record)
    magic = weapon.get('bonus', signed=True)
    if props & 0x80 and slots[12] is not None:
        magic += slots[12].get('bonus', signed=True)
    if props & 1 and slots[11] is not None:
        magic += slots[11].get('bonus', signed=True)
    damage += magic
    if _race(record) in (SILVANESTI, QUALINESTI) and (22 <= kind <= 26 or kind in (18, 19)):
        magic += 1
    if _race(record) == KENDER and kind == HOOPAK:
        magic += 2
    record.set('thac0', (thac0 + magic) & 255)
    return base[SMALL_ROLLS], base[SMALL_DICE], _s8(damage)


def _armor_move(record, item, move, base):
    if base[SLOT] != 2:
        return move
    weight = item.get('weight')
    move = record.get('base_move') if weight <= 150 else 9 if weight <= 399 else 6
    return move + 3 if item.get('bonus', signed=True) and move <= 9 else move


def _carry_move(record, move, load):
    excess = max(_s16(load - _carry_allowance(record)), 0)
    if excess <= 512:
        return move
    return min(move, 9 if excess <= 768 else 6 if excess <= 1024 else 3)


def recalc_stats(char):
    record, rules = _view(Character, char.b), tables()
    slots, items = worn(char), [_view(Item, raw) for raw in char.items]
    load = hands = 0
    for item in items:
        weight = item.get('weight')
        if item.get('quantity'):
            weight = weight * item.get('quantity') & 0xFFFF
        load = load + weight & 0xFFFF
        if item.get('readied'):
            hands = hands + rules.base_item(item.get('type'))[HANDS] & 255
    load = load + sum(struct.unpack('<7H', record.get('money'))[1:]) & 0xFFFF
    record.set('item_count', len(items) & 255)
    record.set('hands_used', hands)
    record.set('weight', load)

    rolls, dice = record.get('unarmed_rolls'), record.get('unarmed_dice')
    bonus = record.get('unarmed_bonus')
    first_rolls, first_dice, first_bonus = rolls[0], dice[0], _s8(bonus[0])
    record.set('thac0', record.get('base_thac0'))
    if slots[0] is None:
        record.set('thac0', (record.get('thac0') + _hit_strength(record)) & 255)
        first_bonus = _s8(first_bonus + _damage_strength(record))
    else:
        first_rolls, first_dice, first_bonus = _weapon_damage(record, slots, rules)
    record.set('damage_rolls', bytes((first_rolls, rolls[1])))
    record.set('damage_dice', bytes((first_dice, dice[1])))
    record.set('damage_bonus', bytes((first_bonus & 255, bonus[1])))

    dexterity, shield, plain, ring, best = _dex_armor(record), 0, 0, 0, 0
    save_bonus, magic_body, move = 0, False, record.get('base_move')
    for item in items:
        if not item.get('readied'):
            continue
        base = rules.base_item(item.get('type'))
        move = _armor_move(record, item, move, base)
        if base[ARMOR] < 0x80:
            continue
        armor, plus, slot = base[ARMOR] & 0x7F, item.get('bonus', signed=True), base[SLOT]
        if slot == 1:
            shield = _s8(armor + plus)
        elif armor == 0:
            if slot == 9:
                ring = max(ring, plus)
            else:
                plain = _s8(plain + plus)
            save_bonus = _s8(save_bonus + item.get('save_bonus', signed=True))
        elif armor + plus > best:
            best = _s8(armor + plus)
            magic_body = magic_body or (plus > 0 and slot == 2)
    if magic_body:
        ring = 0
    record.set('save_bonus', save_bonus, signed=True)
    record.set('move', _carry_move(record, move, load))
    if best < record.get('base_ac'):
        best = _s8(record.get('base_ac'))
    record.set('ac', bytes(((dexterity + shield + plain + ring + best) & 255, (best + plain + ring - 2) & 255)))

    levels, former = _signed(record, 'levels'), _signed(record, 'former_levels')
    fights = (levels[FIGHTER] > 0 or (former[FIGHTER] > 0 and _earlier_class_active(record)) or
              levels[KNIGHT] > 0 or levels[RANGER] > 0)
    record.set('attack_level', max(levels[FIGHTER] & 255, levels[KNIGHT] & 255, levels[RANGER] & 255)
               if fights and _race(record) < MONSTER else 1)
    return slots


def _learn_list(known, rules, list_row, slots, column):
    for spell_level in range(4):
        if slots[column * 5 + spell_level]:
            for entry in range(10):
                spell = rules.u8('knownSpellTable', list_row * 40 + spell_level * 10 + entry)
                if not spell:
                    break
                known[spell - 1] = 1


def _spell_slots(record, char, rules):
    slots, known = bytearray(20), bytearray(record.get('known_spells'))
    levels = _signed(record, 'levels')
    wisdom, deity = _ability(record, 2), _s8(record.get('deity'))

    def add(column, row, first, last):
        for level in range(first, last + 1):
            for spell_level in range(5):
                slots[column * 5 + spell_level] += rules.gained_slots(row, level, spell_level + 1)

    if levels[CLERIC] > 0:
        row = 0 if deity <= 4 else 1
        slots[0] = 1 if row == 0 else 2
        add(0, row, 2, levels[CLERIC])
        for threshold, spell_level in ((12, 0), (13, 0), (14, 1), (15, 1), (16, 2), (17, 3)):
            if wisdom > threshold and slots[spell_level]:
                slots[spell_level] += 1
        _learn_list(known, rules, 0, slots, 0)
    if levels[KNIGHT] > 5 and record.get('knight_order') != 1:
        add(0, 4 if record.get('knight_order') == 2 else 5, 6, levels[KNIGHT])
        _learn_list(known, rules, 0, slots, 0)
    if levels[RANGER] > 7:
        for level in range(8, levels[RANGER] + 1):
            for spell_level in range(3):
                slots[5 + spell_level] += rules.gained_slots(6, level, spell_level + 1)
            for spell_level in range(2):
                slots[15 + spell_level] += rules.gained_slots(6, level, spell_level + 4)
        for spell in range(100):
            if rules.u8('spellTbl', spell * 16) == 1:
                known[spell] = 1
    if levels[MAGE] > 0:
        slots[15] = slots[15] + 1 & 255
        add(3, 7 if record.get('robe_order') == 1 else 8, 2, levels[MAGE])
    for raw in char.items:
        item = _view(Item, raw)
        if item.get('powers')[2] == 0x81 and item.get('readied'):
            for spell_level in range(3):
                slots[15 + spell_level] = slots[15 + spell_level] * 2 & 255
    record.set('spell_slots', bytes(slots))
    record.set('known_spells', bytes(known))


def _readied_special(char):
    codes = []
    for raw in char.items:
        item = _view(Item, raw)
        if item.get('powers')[2] > 0x80 and item.get('readied'):
            codes.append(item.get('powers')[2] & 0x7F)
    return codes


def _saves(record, char, rules):
    levels, former = _signed(record, 'levels'), _signed(record, 'former_levels')
    constitution, result = _ability(record, 4), bytearray(5)
    for kind in range(5):
        best = min([20] + [rules.save_needed(c, levels[c], kind) for c in range(8) if levels[c] > 0])
        if levels[KNIGHT] > former[KNIGHT]:
            best = min(best, rules.save_needed(KNIGHT, former[KNIGHT], kind))
        result[kind] = best
    if _race(record) in DWARVES + (KENDER,) or 6 in _readied_special(char):
        result[0] += _bands(constitution, ((4, 6, 1), (7, 10, 2), (11, 13, 3), (14, 17, 4), (18, 18, 5)))
    result[0] += _bands(constitution, ((19, 20, 1), (21, 22, 2), (23, 24, 3), (25, 25, 4)))
    record.set('saves', bytes(result))


def _thief_skills(record, char, rules, repeat=False):
    codes = [code for code in _readied_special(char) if code in (2, 11)][:1]
    boost, fixed = codes == [11], codes == [2]
    if repeat and not boost:
        raise BindingRequired('thief skills of a dual-class former thief: the original reads an unset local here')
    base = _signed(record, 'levels')[THIEF]
    if _earlier_class_active(record):
        base += _signed(record, 'former_levels')[THIEF]
    if base < 4 and fixed:
        base, fixed = 4, False
    race, dexterity, bonus, skills = _race(record), _ability(record, 3), SKILL_BONUS_ON_ENTRY, bytearray(8)
    for skill in range(8):
        level = base
        if boost and skill < 2:
            floor = (5, 7)[skill]
            bonus = 5 if level >= floor else 0
            level = max(level, floor)
        table = rules.u8('thiefSkillTable', (level - 1) * 8 + skill)
        adjust = rules.s8('raceSkillAdjust', race * 8 + skill)
        if adjust >= 0 or table >= -adjust + bonus:
            value = table + adjust + bonus
            if skill < 5:
                value += rules.s8('dexteritySkillAdjust', (dexterity - 9) * 5 + skill)
            skills[skill] = value & 255
        if fixed:
            skills[skill] = skills[skill] + 10 & 255
    record.set('thief_skills', bytes(skills))


def recalc_class_stats(char, slots):
    record, rules = _view(Character, char.b), tables()
    levels = _signed(record, 'levels')
    best = 0
    highest = _s8(record.get('highest_level'))
    attacks = record.get('attacks')
    for class_slot, level in enumerate(levels):
        best = max(best, rules.u8('thac0Table', class_slot * 13 + level))
        highest = max(highest, level)
    if levels[FIGHTER] > 6 or levels[RANGER] > 7 or levels[KNIGHT] > 6:
        attacks = 3
    deity = _s8(record.get('deity'))
    if deity == 3 or (deity == 6 and _race(record) in DWARVES):
        best += 1
    record.set('base_thac0', best & 255)
    record.set('highest_level', highest, signed=True)
    record.set('attacks', attacks)
    _spell_slots(record, char, rules)
    _saves(record, char, rules)
    if levels[THIEF] > 0:
        _thief_skills(record, char, rules)
    former = _signed(record, 'former_levels')
    mask = 0
    for class_slot in range(8):
        if levels[class_slot] > 0 or 0 < former[class_slot] < highest:
            mask = mask + rules.u8('classMaskTable', class_slot) & 255
    record.set('class_mask', mask)
    for item in slots:
        if item is not None and not rules.base_item(item.get('type'))[USABLE_BY] & mask and not item.get('cursed'):
            item.set('readied', 0)
    if _earlier_class_active(record):
        for class_slot, level in enumerate(former):
            best = max(best, rules.u8('thac0Table', class_slot * 13 + level))
        record.set('base_thac0', best & 255)
        if former[FIGHTER] > 6 or former[RANGER] > 7 or former[KNIGHT] > 6:
            record.set('attacks', 3)
        if former[THIEF] > 0:
            _thief_skills(record, char, rules, repeat=True)


def recalc(char):
    recalc_class_stats(char, recalc_stats(char))
    return char


def load_slot(path, slot):
    from pathlib import Path as _P
    root = _P(path)
    if not (root / ('SAVGAM%s.DAT' % str(slot).upper())).is_file() and (root / 'SAVE' / ('SAVGAM%s.DAT' % str(slot).upper())).is_file(): root = root / 'SAVE'
    return codec.load(root, slot)


def restore(state, snapshot):
    party = []
    for number, files in enumerate(snapshot.members.values()):
        char = recalc(character(bytes(files['SAV'][0]), [bytes(r) for r in files.get('STF', ())],
                                [bytes(r) for r in files.get('SFX', ())]))
        record = _view(Character, char.b)
        record.set('order', number)
        if record.get('npc') > 127:
            recalc_class_stats(char, worn(char))
        party.append(char)
    state.party = party
    return party


def write_character(char):
    return bytes(char.b), b''.join(bytes(i) for i in char.items), b''.join(bytes(e) for e in char.effects)
