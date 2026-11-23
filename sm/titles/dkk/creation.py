import ntpath
import os
import struct
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath
from functools import lru_cache
from sm.files import file_index, file_path
from sm.titles.cok.creation import (Kind, CREATE, DROP, MODIFY, TRAIN, KNIGHT_MENU, VIEW, ADD, REMOVE,
    LOAD, SAVE, BEGIN, INIT, QUIT, choose, yes_no, read_name, file_stem,
    CLERIC, FIGHTER, PALADIN, RANGER, MAGE, THIEF, KNIGHT,
    KENDER, MOUNTAIN_DWARF, HILL_DWARF, STRENGTH, WISDOM, CONSTITUTION,
    AGE_CLASS, DEITY_GRANTS, RACIAL_EFFECTS, COLOUR_PARTS)
from . import rules
from .records import Character, Item, Effect, Spells
from .faults import required

F = rules.F
EXIT, PENDING, PARTY_SIZE = 'Exit', 'creation.pending', 0x33E
SLOTS = 'ABCDEFGHIJ'
CLASS_SLOTS = {c: (c,) for c in (CLERIC, FIGHTER, PALADIN, RANGER, MAGE, THIEF, KNIGHT)}
CLASS_SLOTS.update({8: (0, 2), 9: (0, 2, 5), 10: (0, 4), 11: (0, 5), 12: (0, 6),
                    13: (2, 5), 14: (2, 6), 15: (2, 5, 6), 16: (5, 6)})
MAGE_START = (10, 11, 12, 15, 16, 18, 19)
MAGE_TRAINED = {1: {3: (29, 33, 34), 5: (46, 47, 51), 7: (81, 82, 85, 87)},
                2: {3: (30, 31, 32, 34), 5: (45, 47, 48, 50), 7: (83, 85, 84, 87)}}


class Tables:
    def __init__(self, assets):
        self.assets = assets
        self.rules = rules.tables(assets.root)
        self.races, self.classes = assets.names('raceNames'), assets.names('classNames')
        self.genders, self.deities = assets.names('genderNames'), assets.names('deityNames')
        self.alignments = assets.names('alignmentNames')
        self.alignment_choices = assets.table('alignmentChoices')
        self.classMin = assets.table('classStatMinimums')
        self.classBits = assets.table('trainingClassBits')
        self.hitDiceLimit = assets.table('firstFixedHpLevel')
        self.hp_dice, self.hp_sides = assets.table('firstLevelHitDice'), assets.table('hitDieSides')
        self.conHpTable = assets.table('constitutionHitPointTable')

    def legal_classes(self, race):
        row = self.assets.part('raceClasses')[race * 15:race * 15 + 15]
        return row[1:row[0] + 1]

    def race_limit(self, race, column):
        return self.rules.u8('raceStatLimits', race * 16 + column)

    def age_limit(self, race, band):
        return struct.unpack_from('<H', self.assets.part('ageThresholds'), (race * 5 + band) * 2)[0]


@lru_cache(maxsize=None)
def tables(assets):
    return Tables(assets)


def dice(s, count, sides):
    return sum(s.random(sides) + 1 for _ in range(count))


def levels(b):
    return tuple(b[F['levels']:F['levels'] + 8])


def word(b, name):
    return int.from_bytes(b[F[name]:F[name] + 2], 'little')


def know(char, *spells):
    book = rules.spellbook(char)
    if book is not None:
        for ident in spells:
            book.data[74 + ident - 1] = 1


def suborder(char, cls):
    r = rules.record(char)
    if cls == CLERIC: return int(r.get('deity') > 4)
    if cls == KNIGHT: return 2 + r.get('knight_order')
    if cls == MAGE: return 7 if r.get('robe_order') == 1 else 8
    return {FIGHTER: 2, RANGER: 6, THIEF: 9, PALADIN: 10}[cls]


def gain_hp(state, char, mask, divisor, t):
    adjust_level_hp(state, char, mask, divisor, True, t)


def hit_point_cap(char):
    r, t = rules.record(char), rules.tables()
    caps = []
    for cls, raw in enumerate(levels(char.b)):
        level = rules._s8(raw)
        if level <= 0: continue
        con = rules.class_con_adjust(char, cls)
        threshold = t.u8('firstFixedHpLevel', cls)
        if level < threshold:
            extra = cls in (RANGER, KNIGHT) or cls == CLERIC and r.get('deity') <= 4
            cap = (level + extra) * (t.u8('hitDieSides', cls) + con)
        elif cls == 1:
            cap = 112
        else:
            count = (9, 0, 9, 9, 11, 11, 10, 9)[cls]
            fixed = (2, 0, 3, 3, 2, 1, 2, 3)[cls]
            cap = count * (t.u8('hitDieSides', cls) + con) + (level - threshold + 1) * fixed
        caps.append(cap)
    return ((sum(caps) & 0xFFFF) // len(caps)) & 255 if caps else 0


def hp_minimum(char, t):
    held = [(cls, rules._s8(raw)) for cls, raw in enumerate(levels(char.b)) if 0 < rules._s8(raw)]
    total = sum(level + (cls in (RANGER, KNIGHT)) for cls, level in held) & 255
    bonus = rules._s8(sum(con_bonus(char.b, t, cls) for cls, _ in held) & 255)
    if bonus < 0 and total <= -bonus + len(held): return 1
    return ((total + bonus) // len(held)) & 255


def modify_snapshot(char):
    r = rules.record(char)
    return bytes(r.get('abilities')[1::2]), r.get('strength_extra'), r.get('hp_max'), bytes(r.get('name'))


def restore_modified(char, saved, party_adjust=0):
    current, exceptional, maximum, name = saved
    r = rules.record(char)
    abilities = bytearray(r.get('abilities'))
    abilities[1::2] = current
    r.set('abilities', bytes(abilities))
    for field, value in dict(strength_extra=exceptional, hp_max=maximum, hp=maximum, name=name).items(): r.set(field, value)
    rules.recalc_stats(char, party_adjust)


def adjust_modified(char, t, field, delta):
    if delta not in (-1, 1) or field not in (*range(6), 7): raise ValueError('invalid stat adjustment')
    r = rules.record(char)
    if field == 7:
        maximum = r.get('hp_max') + delta & 255
        maximum = min(maximum, hit_point_cap(char)) if delta > 0 else max(maximum, hp_minimum(char, t))
        r.set('hp_max', maximum)
        r.set('hp', maximum)
        return
    race, gender, cls = r.get('race'), r.get('gender'), r.get('class')
    column = gender if field == STRENGTH else 4 + 2 * field
    low = t.race_limit(race, column)
    high = t.race_limit(race, column + (2 if field == STRENGTH else 1))
    if field == 5 and race == MOUNTAIN_DWARF and cls == PALADIN: low = high = 17
    at = F['abilities'] + 2 * field + 1
    value = char.b[at] + delta & 255
    if delta < 0:
        if field == STRENGTH and r.get('strength_extra'):
            r.set('strength_extra', r.get('strength_extra') - 1)
            value = value + 1 & 255
        else:
            value = max(value, low)
        value = max(value, t.classMin[cls * 6 + field])
    elif value > high:
        if field == STRENGTH and value > 18 and any(rules._s8(levels(char.b)[c]) > 0 for c in (FIGHTER, PALADIN, RANGER, KNIGHT)):
            if r.get('strength_extra') < t.race_limit(race, 4 + gender): r.set('strength_extra', r.get('strength_extra') + 1)
        value = high
    char.b[at] = value
    book = rules.spellbook(char)
    if field == WISDOM and book is not None:
        slots = bytearray(book.get('spell_slots'))
        if slots[0]:
            slots[0] = 1
            book.set('spell_slots', bytes(slots))
    if field == CONSTITUTION:
        maximum = max(r.get('hp_max'), hp_minimum(char, t)) if delta > 0 else min(r.get('hp_max'), hit_point_cap(char))
        r.set('hp_max', maximum)
        r.set('hp', maximum)


def keep_modified(char, t):
    r = rules.record(char)
    rules.recalc_cleric_slots(char)
    held = [(cls, rules._s8(raw)) for cls, raw in enumerate(levels(char.b)) if 0 < rules._s8(raw)]
    bonus = sum(rules.class_con_adjust(char, cls) * (level + (cls == RANGER) if level < t.hitDiceLimit[cls] else t.hitDiceLimit[cls] - 1)
                for cls, level in held) & 255
    r.set('hp_rolled', r.get('hp_max') - bonus // len(held) & 255)
    keep_base_abilities(r)


def keep_base_abilities(r):
    abilities = bytearray(r.get('abilities'))
    abilities[::2] = abilities[1::2]
    r.set('abilities', bytes(abilities))
    r.set('strength_extra_base', r.get('strength_extra'))


class ModifyEditor:
    def __init__(self, game, char):
        if rules.record(char).get('experience') not in (210003, 105002, 70001):
            raise ValueError('character cannot be modified')
        self.game, self.char, self.tables = game, char, tables(game.assets)
        self.field, self.cursor, self.result = 0, 1, None
        self.refresh()
        self.saved = modify_snapshot(char)
        self.display_hp = rules.record(char).get('hp')
        self.dirty = (0, 7)

    def refresh(self):
        rules.recalc_sheet_stats(self.char, self.game.s.r1[0x372])

    def edit_name(self, key):
        r = rules.record(self.char)
        raw = bytearray(r.get('name'))
        length, at = raw[0], self.cursor
        if key == 8 and at > 1:
            raw[at - 1:length] = raw[at:length + 1]
            raw[0] -= 1
            self.cursor = min(at, raw[0])
        elif 32 <= key <= 122 and at <= 15:
            raw[at] = key
            self.cursor = min(at + 1, 15)
            if self.cursor > length:
                raw[0] += 1
                raw[self.cursor] = 32
        r.set('name', bytes(raw))

    def delete_name(self):
        r = rules.record(self.char)
        raw = bytearray(r.get('name'))
        length = raw[0]
        if length <= 1: return
        if self.cursor == length:
            self.cursor -= 1
        else:
            raw[self.cursor:length] = raw[self.cursor + 1:length + 1]
        raw[0] -= 1
        r.set('name', bytes(raw))

    def step(self, key, extended=False, mouse_field=None):
        if self.result is not None: raise ValueError('modify editor is closed')
        if not isinstance(key, int) or not 0 <= key <= 255: raise ValueError('invalid modify key')
        old = self.field
        dirty = {old}
        action = None if old == 6 or extended else key
        if old == 6:
            if not extended and (49 <= key <= 57 or key == 92):
                key = 55 if key == 92 else self.game.assets.part('digitKeys')[key - 49]
                extended = True
            if key == 27: key = 0
            if not extended: self.edit_name(key)
        if extended:
            if key in (72, 80): self.field = (old + (1 if key == 80 else -1)) % 8
            elif key == 71 and mouse_field is not None:
                if mouse_field not in range(8): raise ValueError('invalid modify field')
                self.field = mouse_field
            elif key == 83 and old == 6: self.delete_name()
            elif key == 27: action = 3
        if action == 3:
            restore_modified(self.char, self.saved, self.game.s.r1[0x372])
            self.result = False
            return self.result
        if action in (0, 1):
            adjust_modified(self.char, self.tables, old, 1 if action == 0 else -1)
            if old == CONSTITUTION: dirty.add(6)
        rules.recalc_stats(self.char, self.game.s.r1[0x372])
        self.refresh()
        dirty.update((self.field, 7))
        self.dirty = tuple(sorted(dirty))
        self.display_hp = rules.record(self.char).get('hp')
        if action == 2:
            keep_modified(self.char, self.tables)
            self.result = True
        return self.result


def modify(game, char=None):
    if char is None: char = pick_member(game)
    if char is None: return False
    a = game.assets
    if rules.record(char).get('experience') not in (210003, 105002, 70001):
        game.ask('ACK', ('Continue',), prompt=(member_name(char) + a.text('cantBeModifiedText'))[:40],
                 timed=1, message_colour=14)
        return False
    editor, choice = ModifyEditor(game, char), 0
    labels = a.text('modifyMenu').split()
    while editor.result is None:
        token = game.ask('CREATE_MODIFY', None, prompt='', field=editor.field, cursor=editor.cursor,
                         name=member_name(char), query=a.text('modifyQuery'), menu=' '.join(labels), choice=choice,
                         dirty=' '.join(map(str, editor.dirty)), display_hp=editor.display_hp)
        if not isinstance(token, str) or not token: raise ValueError('invalid modify input')
        if token.startswith('#') and len(token) > 1:
            scan, separator, target = token[1:].partition(':')
            key = int(scan)
            mouse_field = int(target) if separator else None
            if editor.field != 6 and key in (75, 77):
                choice = (choice + (1 if key == 77 else -1)) % len(labels)
            else:
                editor.step(key, True, mouse_field)
        elif len(token) != 1:
            raise ValueError('invalid modify input')
        elif editor.field == 6:
            editor.step(ord(token))
        elif token == chr(27):
            editor.step(27, True)
        elif token == chr(13):
            editor.step(choice)
        elif token in '123456789\\':
            if token in '46': choice = (choice + (1 if token == '6' else -1)) % len(labels)
            editor.step(55 if token == '\\' else a.part('digitKeys')[ord(token) - 49], True)
        else:
            hits = [i for i, label in enumerate(labels) if label[0].upper() == token.upper()]
            if hits:
                choice = hits[-1]
                editor.step(hits[0])
    return editor.result


def adjust_level_hp(state, char, mask, divisor, gaining, t):
    r = rules.record(char)
    total = bonus = 0
    for cls, raw in enumerate(levels(char.b)):
        level = rules._s8(raw)
        if level <= 0 or not t.classBits[cls] & mask: continue
        if level >= t.hitDiceLimit[cls]:
            if cls != 1: total = 3 if cls in (FIGHTER, PALADIN, KNIGHT) else 1 if cls == MAGE else 2
        else:
            count = 1 if level > 1 or cls == CLERIC and r.get('deity') > 4 else t.hp_dice[cls]
            total = total + max(dice(state, count, t.hp_sides[cls]), dice(state, count, t.hp_sides[cls])) & 255
            bonus = bonus + count * con_bonus(char.b, t, cls) & 255
    if not divisor:
        for field in ('hp', 'hp_rolled', 'hp_max'): r.set(field, 0)
        return
    gain, con = max(1, total // divisor), bonus // divisor
    wounds = r.get('hp_max') - r.get('hp') & 255
    if gaining:
        r.set('hp_rolled', r.get('hp_rolled') + gain & 255)
        r.set('hp_max', r.get('hp_max') + gain + con & 255)
    else:
        r.set('hp_rolled', max(0, r.get('hp_rolled') - gain))
        loss = (gain + con) & 255
        maximum = r.get('hp_max')
        loss = max(loss, maximum - hit_point_cap(char))
        r.set('hp_max', max(0, maximum - loss))
    r.set('hp', max(0, r.get('hp_max') - wounds))


def eligible(char):
    r, t = rules.record(char), rules.tables()
    experience = int.from_bytes(char.b[F['experience']:F['experience'] + 4], 'little', signed=True)
    return tuple(cls for cls, level in enumerate(levels(char.b))
                 if 0 < level < 18 and level < t.u8('racialLevelCaps', r.get('race') * 8 + cls)
                 and 0 < t.level_xp(suborder(char, cls), level + 1) <= experience)


def can_level_up(char):
    return bool(eligible(char))


def refresh_level_up(char):
    ready = can_level_up(char)
    rules.record(char).set('level_up_ready', int(ready))
    return ready


def train_to_experience(state, char, t):
    r = rules.record(char)
    while ready := eligible(char):
        mask = sum(t.classBits[cls] for cls in ready) & 255
        lv = levels(char.b)
        for cls, level in enumerate(lv):
            if level and t.classBits[cls] & mask:
                char.b[F['levels'] + cls] += 1
        rules.recalc_class_stats(char)
        know(char, *MAGE_TRAINED.get(r.get('robe_order'), {}).get(levels(char.b)[MAGE], ()))
        gain_hp(state, char, mask, sum(level > 0 for level in lv), t)
    r.set('level_up_ready', 0)


def training_offer(char, t):
    r = rules.record(char)
    held = [(cls, level, suborder(char, cls)) for cls, level in enumerate(rules._signed(r, 'levels')) if level > 0]
    experience = r.get('experience', signed=True)
    ready = eligible(char)
    threshold = t.rules.progression_xp
    ceilings = [threshold(row, level + 2) for cls, level, row in held if cls in ready]
    if held and ready:
        cls, level, row = held[-1]
        if threshold(row, level + 1) > 0:
            ceilings.append(threshold(row, level + 2))
    trim = max((ceiling - 1 for ceiling in ceilings if 0 < ceiling <= experience), default=0)
    return (sum(t.classBits[cls] for cls, level, row in held) & 255,
            sum(t.classBits[cls] for cls in ready) & 255, trim)


def train(game, char=None):
    s, a = game.s, game.assets
    runtime = s.g.setdefault('dkk.runtime', {})
    runtime['test_training'] = 0
    if char is None: char = pick_member(game)
    if char is None: return False
    r, t = rules.record(char), tables(a)
    def refuse(text):
        game.ask('ACK', ('Continue',), prompt=a.text(text), timed=1, message_colour=14)
        return False
    if r.get('status'): return refuse('consciousTrainingMessage')
    held, ready, trim = training_offer(char, t)
    hall = s.r1[0x2A8] & 255
    if trim: r.set('experience', trim)
    if not held & hall: return refuse('classTrainingMessage')
    allowed = ready & hall
    if not allowed:
        runtime['training_done'] = 1
        return refuse('notEnoughExperienceText')
    before = rules._signed(r, 'levels')
    gains = [cls for cls, level in enumerate(before) if level > 0 and t.classBits[cls] & allowed]
    offer = '; '.join(a.text('aLevelText').lstrip() + str(before[cls] + 1) + ' ' + t.classes[cls] for cls in gains)
    lines = tuple(a.text('aLevelText' if index == 0 else 'andALevelText') + str(before[cls] + 1) + ' ' + t.classes[cls]
                  for index, cls in enumerate(gains))
    if game.ask('CREATE_TRAIN', ('Yes', 'No'), prompt=a.text('wishToTrainQuery'), start=0,
                character=member_name(char), levels=offer, training_lines='\n'.join(lines), heading=a.text('willBecomeText')):
        return False
    game.ask('ACK', ('Continue',), prompt=a.text('congratulationsText'), timed=1, message_colour=10)
    r.set('class_mask', 0)
    for cls in gains: char.b[F['levels'] + cls] += 1
    rules.recalc_class_stats(char)
    after = rules._signed(r, 'levels')
    if after[MAGE] > before[MAGE] or after[RANGER] > max(8, before[RANGER]):
        from .magic_lists import learn
        learn(game, char)
    gain_hp(s, char, allowed, sum(level > 0 for level in before), t)
    refresh_level_up(char)
    return True


def starting_items(char, assets, party_adjust=0, game=None):
    lv = levels(char.b)
    group = 0 if lv[KNIGHT] else 1 if any(lv[c] for c in (FIGHTER, RANGER, PALADIN)) else 2 if lv[THIEF] else 3 if lv[CLERIC] else 4
    templates = assets.records('ITEM0')[1]
    choices = list(assets.part('startingItems')[group * 4:group * 4 + 4])
    if group == 2 and lv[CLERIC]: choices[0] = assets.part('startingItems')[12]
    for ident in choices:
        slot = rules.allocate_item(game) if game is not None else bytearray(Item.SIZE)
        if slot is None: return False
        slot[:] = bytes(Item.SIZE)
        if not ident: continue
        raw = templates[(ident - 1) * 17:ident * 17]
        if len(raw) != 17 or raw[0] == 255: continue
        item = rules._view(Item, slot)
        item.data[46:] = raw
        item.set('unidentified', item.get('unidentified') & 248)
        if ident != 91: item.set('readied', 1)
        char.items.insert(0, slot)
    rules.recalc_stats(char, party_adjust)
    rules.record(char).set('item_count', 3)
    return True


def starting_spells(char):
    book = rules.spellbook(char)
    if book is None: return
    held = levels(char.b)
    if held[CLERIC]:
        rules.recalc_cleric_slots(char)
        for index in range(10):
            ident = rules.tables().u8('spellsByLevel', index)
            if not ident: break
            know(char, ident)
    if held[MAGE]:
        slots = bytearray(book.get('spell_slots'))
        slots[24] = 1
        book.set('spell_slots', bytes(slots))
        know(char, *MAGE_START)


def create(game):
    state, t = game.s, tables(game.assets)
    char = rules.character(bytes(Character()))
    r = rules.record(char)
    for key, value in dict(base_ac=50, base_thac0=40, active=1, dimensions=1, order=10).items(): r.set(key, value)
    r.set('creature_id', state.random(256))
    r.set('icon_colors', bytes(c + (c + 8) * 16 for c in game.assets.part('iconColorSlots')))
    state.g[PENDING] = [char.b, char.items, char.effects]
    try:
        race = choose(game, Kind.RACE, game.assets.text('pickRaceMenu'), t.races[:7])
        if race is None: return
        r.set('race', race)
        r.set('icon_size', 1 if race in (KENDER, MOUNTAIN_DWARF, HILL_DWARF) else 2)
        for kind in RACIAL_EFFECTS.get(race, ()):
            effect = Effect(); effect.set('type', kind); effect.set('strength', 255)
            char.effects.append(effect.data)
        gender = choose(game, Kind.GENDER, game.assets.text('pickGenderMenu'), t.genders)
        if gender is None: return
        r.set('gender', gender)
        legal = t.legal_classes(race)
        pick = choose(game, Kind.CLASS, game.assets.text('pickClassMenu'), [t.classes[c] for c in legal])
        if pick is None: return
        cls = legal[pick]
        r.set('class', cls)
        held = CLASS_SLOTS[cls]
        if cls not in (FIGHTER, THIEF, 14):
            char.b = char.b + bytearray(Spells.SIZE)
            r = rules.record(char)
            state.g[PENDING][0] = char.b
        for slot in held: char.b[F['levels'] + slot] = 1
        if cls == RANGER: char.b[F['levels'] + RANGER] = 2
        r.set('experience', {1: 210003, 2: 105002, 3: 70001}[len(held)])
        if KNIGHT in held: r.set('knight_order', 1)
        for slot, effect_id in ((RANGER, 105), (PALADIN, 45)):
            if slot in held:
                effect = Effect(); effect.set('type', effect_id); effect.set('strength', 255)
                char.effects.append(effect.data)
        if THIEF in held: rules.recalc_thief_skills(char)
        r.set('base_thac0', max(t.rules.u8('thac0Table', slot * 19 + levels(char.b)[slot]) for slot in held))
        r.set('class_mask', sum(t.rules.u8('classMaskBits', slot) for slot in held) & 255)
        rules.recalc_saves(char)
        alignment_mask = 255
        if CLERIC in held:
            dwarf = race in (MOUNTAIN_DWARF, HILL_DWARF)
            pick = choose(game, Kind.DEITY, game.assets.text('pickDeityMenu'), t.deities[6:7] if dwarf else t.deities[1:8])
            if pick is None: return
            deity = 6 if dwarf else pick + 1
            r.set('deity', deity)
            alignment_mask, grants = DEITY_GRANTS[deity]
            know(char, *grants)
            if deity == 3 or deity == 6 and dwarf: r.set('base_thac0', r.get('base_thac0') + 1 & 255)
        allowed = [a for bit, a in enumerate(t.alignment_choices) if (game.assets.part('classAlignments')[cls] & alignment_mask) >> bit & 1]
        pick = choose(game, Kind.ALIGNMENT, game.assets.text('pickAlignmentMenu'), [t.alignments[a] for a in allowed])
        if pick is None: return
        r.set('alignment', allowed[pick])
        if MAGE in held: r.set('robe_order', 1 if allowed[pick] % 3 == 0 else 2)
        age_cls = cls if cls <= KNIGHT else AGE_CLASS[cls]
        base, count, sides = struct.unpack_from('<HBB', game.assets.part('startingAges'), (race * 8 + age_cls) * 4)
        r.set('age', base + (dice(state, count, sides) if cls <= KNIGHT else count * sides))
        while True:
            for slot in held: char.b[F['levels'] + slot] = 1
            roll_abilities(state, char.b, t)
            r.set('attacks', 2); r.set('unarmed_rolls', bytes((1, 0))); r.set('unarmed_dice', bytes((2, 0)))
            r.set('use_strength', 1); r.set('base_move', 12)
            r.set('money', struct.pack('<3H', 500, 0, 0))
            for key in ('hp_max', 'hp', 'hp_rolled'): r.set(key, 0)
            starting_spells(char)
            gain_hp(state, char, 255, len(held), t)
            hall = state.r1[0x2A8]
            runtime = state.g.setdefault('dkk.runtime', {})
            state.r1[0x2A8] = 255
            runtime.update(auto_training=1, training_done=0, test_training=0)
            try:
                train_to_experience(state, char, t)
                runtime['training_done'] = 1
            finally:
                runtime['auto_training'] = 0
                state.r1[0x2A8] = hall
            rules.recalc_sheet_stats(char, state.r1[0x372])
            if not yes_no(game, Kind.ROLL, game.assets.text('rerollStatsQuery'), start=1, hp=r.get('hp'), levels='/'.join(str(n) for n in levels(char.b) if n)):
                break
        rules.recalc_sheet_stats(char, state.r1[0x372])
        typed = read_name(game, Kind.NAME, game.assets.text('characterNameQuery'), 15)
        r.set('name', (bytes([len(typed)]) + typed).ljust(16, b'\0'))
        default_icon(char.b)
        customize_icon(game, char.b)
        keep_base_abilities(r)
        if yes_no(game, Kind.SAVE, game.assets.text('saveCharacterQuery')):
            if starting_items(char, game.assets, state.r1[0x372], game):
                return store(game, char)
    finally:
        rules.release_inventory(game, char)
        state.g.pop(PENDING, None)


def save_directory(directory=None, *, create=True):
    root = Path(directory) if directory else Path(os.environ.get('SM_SAVE_ROOT') or Path(__file__).resolve().parents[3] / 'local' / 'saves') / 'dkk'
    from .intake import require_folder
    if root.resolve().is_relative_to(require_folder().resolve()):
        raise ValueError('Death Knights originals are read-only; use a separate save directory')
    if create: root.mkdir(parents=True, exist_ok=True)
    return root


RESERVED_CHARS = frozenset(map(chr, range(32))) | frozenset('"*:<>?|/\\')
RESERVED_NAMES = frozenset({'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} |
                           {device + digit for device in ('COM', 'LPT') for digit in '123456789\xb9\xb2\xb3'})


def reserved_part(part):
    if part[-1:] in ('.', ' '): return part not in ('.', '..')
    return not RESERVED_CHARS.isdisjoint(part) or part.partition('.')[0].rstrip(' ').upper() in RESERVED_NAMES


def reserved_name(path):
    return any(map(reserved_part, ntpath.splitroot(path)[2].replace('/', '\\').split('\\')))


def roster_destination(root, stem):
    name = PureWindowsPath(stem + '.PC')
    if name.anchor or '..' in name.parts or any(map(reserved_name, name.parts[:-1])):
        return None
    folder = root.joinpath(*name.parts[:-1])
    if not folder.resolve().is_relative_to(root) or not folder.is_dir():
        return None
    return folder, name.name[:-3]


def store(game, char):
    from . import save
    admitted = save.admit_character(game, char)
    if admitted is None: return
    root = admitted.resolve()
    stem = file_stem(member_name(char))
    initial = True
    while True:
        destination = roster_destination(root, stem)
        if destination is None: return
        folder, leaf = destination
        name = leaf + '.PC'
        if initial:
            if reserved_name(name) or not (folder / name).resolve().is_relative_to(root): return
            index, writable = save.member_destination(game, folder, name)
            if not writable: return
            initial = False
        else:
            index = file_index(folder)
        exists = name in index
        if '*' in name or '?' in name:
            exists = any(fnmatchcase(key, name.replace('[', '[[]')) for key in index)
        if not exists or yes_no(game, Kind.OVERWRITE, game.assets.text('overwritePrefix') + stem + game.assets.text('overwriteSuffix'), start=1): break
        typed = read_name(game, Kind.FILE_NAME, game.assets.text('newFileNamePrompt'), 8)
        stem = typed.decode('ascii')
        char.b[:1 + len(typed)] = bytes([len(typed)]) + typed
    if reserved_name(name): return
    names = [leaf + '.' + suffix for suffix in ('PC', 'WIZ', 'JNK', 'EFF')]
    paths = [index.get(key, folder / key) for key in names]
    if any(not path.resolve().is_relative_to(root) for path in paths): return
    for path, raw in zip(paths, rules.write_character(char)):
        if raw: path.write_bytes(raw)
        else: path.unlink(missing_ok=True)
    return stem


def roster(state, directory=None, imported=False):
    from .save_chars import roster as saved_roster
    folder = Path(directory) if imported else save_directory(directory)
    return saved_roster(folder, state.chars(), imported)


def read_character(path, game=None):
    from . import save_chars
    index = file_index(path.parent)
    name = path.name.upper()
    stem, extension = name.rsplit('.', 1)
    reader = save_chars.read_imported if extension == 'WHO' else save_chars.read_native
    first_dot = name.index('.')
    companions = name[:first_dot] + name[first_dot + 4:]
    if companions != stem:
        index[companions + '.' + extension] = path
    files = reader(index, companions, extension)
    if hasattr(save_chars, 'materialize'):
        return save_chars.materialize(files, getattr(game, 'game', game))
    files = save_chars.detach(files)
    return rules.character(bytes(files['GAM'][0]), [bytes(r) for r in files.get('JNK', ())],
                           [bytes(r) for r in files.get('EFF', ())],
                           spells=bytes(files['WIZ'][0]) if files.get('WIZ') else None)


def remember_icon_disk(game):
    game.s.g['dkk.previous_disk'] = game.s.dataset


def join(game, char):
    from . import effects, save
    slots = rules.recalc_stats(char, game.s.r1[0x372])
    effects.recalc_ability(game, char, STRENGTH)
    rules.recalc_class_stats(char, slots)
    save.append_character(game, char)
    remember_icon_disk(game)
    game.vm.icons.pop(char.b[F['order']], None)


def add(game):
    query = game.assets.text('addFromWhereQuery')
    source = game.ask(Kind.ADD.value, tuple(game.assets.text('sourceGameMenu').split()),
                      prompt=query, query=query, source=True, start=0)
    if source == 2: return
    game.s.g['save.file_format'] = 1 - source
    from . import save
    from .save_chars import roster as saved_roster
    folder = save.load_directory(game)
    if folder is None: return
    entries = saved_roster(folder, game.s.chars(), imported=source == 1)
    names = [(raw := path.read_bytes())[1:1 + raw[0]].decode('cp437') for path in entries]
    starred = set()
    pick = 0
    while entries:
        labels = [('* ' if i in starred else '') + name for i, name in enumerate(names)]
        pick = choose(game, Kind.ADD, game.assets.text('addCharacterQuery'), labels, start=pick)
        if pick is None: return
        if labels[pick].startswith('*'): continue
        starred.add(pick)
        char = read_character(entries[pick], game)
        non_npc, rangers, duplicate = 0, 0, False
        members = game.s.chars()
        for member in members:
            if member_name(member) == member_name(char) and member.b[F['creature_id']] == char.b[F['creature_id']]:
                duplicate = True
                break
            non_npc += member.b[F['npc']] < 128
            rangers += 0 < levels(member.b)[RANGER] < 128
        if not members:
            game.s.r1[PARTY_SIZE] = 0
            join(game, char)
        elif (not duplicate and len(members) < 8
              and (game.s.r1[PARTY_SIZE] < 8 if char.b[F['npc']] >= 128 else non_npc < 6)
              and (not levels(char.b)[RANGER] or rangers < 3)):
            join(game, char)
            non_npc += char.b[F['npc']] < 128
        elif 0 < levels(char.b)[RANGER] < 128 and rangers > 2:
            game.ask('ACK', ('Continue',), prompt=game.assets.text('tooManyRangers'), timed=1, message_colour=10)
        if non_npc >= 6 or game.s.r1[PARTY_SIZE] >= 8 or len(game.s.chars()) >= 8: return


def member_name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def pick_member(game):
    members = game.s.chars()
    runtime = game.s.g.setdefault('dkk.runtime', {})
    previous = runtime.get('mouse_mode', 1)
    runtime['mouse_mode'] = 1
    try:
        pick = choose(game, Kind.WHO, game.assets.text('pickCharacterText'), tuple(member_name(c) for c in members))
    finally:
        runtime['mouse_mode'] = previous
    if pick is None: return
    game.s.sel = pick
    return members[pick]


def remove_creature(game, char, keep_count=False, free_icon=True):
    s = game.s
    members = s.party if char in s.party else s.monsters
    if char not in members: return False
    index = members.index(char)
    previous = max(0, index + (len(s.party) if members is s.monsters else 0) - 1)
    if free_icon:
        icons = getattr(game.vm, 'icons', None)
        if icons is not None: icons.pop(char.b[F['order']], None)
    del members[index]
    rules.release_inventory(game, char)
    s.sel = previous
    if not keep_count: s.r1[PARTY_SIZE] = s.r1[PARTY_SIZE] - 1 & 255
    return True


def drop(game):
    from .inventory import bottom_message
    from .save import forget_character
    char = pick_member(game)
    if char is None: return
    name, a = member_name(char), game.assets
    if (not yes_no(game, Kind.DROP, a.text('dropPrefix') + name + a.text('foreverText'), at=1, start=1)
            or not yes_no(game, Kind.DROP, a.text('areYouSureQuery'), at=1, start=1)):
        bottom_message(game, name + a.text('sighOfReliefText'))
        return
    bottom_message(game, name + a.text('bidsFarewellText' if char.b[F['active']] else 'dumpedOutBackText'))
    filesystem = getattr(game, 'save_filesystem', None)
    directory = (filesystem.host_path(filesystem.save_path[:-1]) if filesystem is not None
                 else getattr(game, 'roster_directory', None))
    folder = save_directory(directory, create=False).resolve()
    try:
        files = file_index(folder)
    except OSError:
        files = {}
    forget_character({key: path for key, path in files.items() if path.resolve().is_relative_to(folder)}, char)
    remove_creature(game, char)


def remove(game):
    char = pick_member(game)
    if char is None: return
    if char.b[F['npc']] >= 128:
        drop(game)
    else:
        store(game, char)
        remove_creature(game, char)


def confirm_quit(game):
    if not yes_no(game, Kind.QUIT, game.assets.text('quitToDosPrompt'), at=1, start=1): return False
    if game.s.chars() and not game.s.g.get('save.recent', 0):
        if not yes_no(game, Kind.QUIT, game.assets.text('quitUnsavedQuery'), at=1, start=1): save_menu(game)
    game.s.stop = 1
    game.exit_game = True
    return True


def advance_order(char):
    r = rules.record(char)
    level, order = rules._s8(levels(char.b)[KNIGHT]), r.get('knight_order')
    row = 4 if order == 1 else 5
    if rules.tables().progression_xp(row, level) > r.get('experience', signed=True):
        loss = 2 if level > 9 else r.get('hp_rolled') // (level + 1)
        adjustment = 0 if level > 9 else rules.class_con_adjust(char, KNIGHT)
        char.b[F['levels'] + KNIGHT] -= 1
        r.set('hp_rolled', r.get('hp_rolled') - loss & 255)
        r.set('hp_max', r.get('hp_max') - loss - adjustment & 255)
        r.set('hp', min(r.get('hp'), r.get('hp_max')))
    r.set('knight_order', order + 1)
    rules.recalc_class_stats(char)
    refresh_level_up(char)


def knight_promotion(game, char):
    r, a = rules.record(char), game.assets
    level, order = rules._s8(levels(char.b)[KNIGHT]), r.get('knight_order')
    if not level or (level > 0 and order == 3): return False
    target = a.text('swordText' if order == 1 else 'roseText')
    minimum, row = (3, 4) if order == 1 else (4, 5)
    name = member_name(char)
    if level < minimum or r.get('experience', signed=True) < rules.tables().level_xp(row, minimum):
        verdict = name + a.text('tooInexperiencedText')
    else:
        required_stats = a.part('knightRequirements')[(order - 1) * 6:order * 6]
        qualified = all(r.get('abilities')[i * 2] >= value for i, value in enumerate(required_stats))
        verdict = name + a.text('mayBecomeText' if qualified else 'doesNotQualifyText')
        if qualified: verdict += '\n' + a.text('knightOfTheText') + target
    selected = game.ask('CREATE_KNIGHT', ('Change', 'Exit'), prompt=verdict, character=name,
                        petition=a.text('petitioningText'), order=a.text('knightOfTheText') + target)
    if selected: return False
    advance_order(char)
    return True


def boot_input_mode(game):
    path = file_path(game.assets.root, 'DKK.CFG')
    lines = path.read_bytes().splitlines() if path.is_file() else []
    mode = lines[2][:1] if len(lines) > 2 else b''
    return mode.decode('ascii') if mode in (b'M', b'J') else 'N'


def init_input(game):
    from . import save_start, shop
    if not hasattr(game, 'input_mode'):
        game.input_mode = boot_input_mode(game)
    text = game.assets.text
    query = text('initInputQuery')
    selected, caption = 0, ''
    while True:
        header = save_start.read_input_config(game)
        labels = (text('mouseOn' if game.input_mode == 'M' else 'mouseOff'),
                  text('joystickOn' if game.input_mode == 'J' else 'joystickOff'), text('disableBoth'))
        selected = shop.pick(game, Kind.INIT, query, labels, window='9 12 38 22', query=query,
                             menu=text('selectMenuText'), start=selected, caption=caption)
        if selected is None: return
        calibration = ()
        if selected == 0:
            game.input_mode = 'N' if game.input_mode == 'M' else 'M'
            if game.input_mode == 'M':
                game.s.g.setdefault('dkk.runtime', {})['mouse_mode'] = 1
        elif selected == 1:
            game.input_mode = 'N' if game.input_mode == 'J' else 'J'
            if game.input_mode == 'J':
                save_start.write_input_config(game, None, game.input_mode)
                shop.pause(game, text('upperPrompt1') + '\n\n' + text('upperPrompt2'), timed=1,
                           window='1 3 38 5', colour=13)
                caption = text('joystickReadError')
                calibration = ((0, 0),) * 3 + ((1, 1),) + ((0, 0),) * 3
        else:
            game.input_mode = 'N'
        save_start.write_input_config(game, header, game.input_mode, calibration)


def run(game):
    s = game.s
    s.g.setdefault('dkk.runtime', {}).update(mouse_mode=0, test_training=0)
    s.prev_mode, s.mode = s.mode, 0
    selected = 0
    while not s.stop:
        game.menu_ids = game.assets.choices(s)
        note, game.menu_note = getattr(game, 'menu_note', ''), ''
        selected = game.ask(Kind.MAIN_MENU.value, tuple(game.assets.labels[i] for i in game.menu_ids),
                            action='main-menu', message=note, start=min(selected, len(game.menu_ids) - 1))
        action = game.menu_ids[selected]
        if action not in (SAVE, QUIT): s.g['save.recent'] = 0
        if action == QUIT:
            confirm_quit(game)
        elif action == BEGIN:
            runtime = s.g['dkk.runtime']
            runtime['mouse_mode'] = 1
            s.mode = s.prev_mode
            if not game.vm.resuming or runtime.get('picture_id') == 9 or s.mode in (0, 4):
                game.vm.party_drawn()
            s.r1[0x2A8] = 0
            return
        elif action == CREATE:
            create(game)
        elif action == ADD:
            add(game)
        elif action == SAVE:
            save_menu(game)
        elif action == LOAD:
            load_menu(game)
        elif action == DROP:
            drop(game)
        elif action == REMOVE:
            remove(game)
        elif action == TRAIN:
            train(game)
        elif action == MODIFY:
            modify(game)
        elif action == INIT:
            init_input(game)
        elif action == KNIGHT_MENU:
            char = pick_member(game)
            if char is not None: knight_promotion(game, char)
        elif action == VIEW:
            char = pick_member(game)
            if char is not None: game.vm.service('inventory', 'view', char)
        else:
            required('party menu action %d' % action)()
        if action in (DROP, REMOVE):
            from .save_start import last_member_removed
            if last_member_removed(game): selected = 0


def save_menu(game):
    choice = choose(game, Kind.SLOT, game.assets.text('saveWhichGamePrompt'), tuple(SLOTS),
                    menu=game.assets.text('saveSlotMenu'), preserve_message=game.s.mode == 2)
    if choice is None: return
    save_game(game, SLOTS[choice])


def slot_folder(game, slot):
    return save_directory(getattr(game, 'roster_directory', None)) / ('SAVGAM' + slot + '.PTY')


def save_game(game, slot):
    from . import save
    return save.save_game(game, slot)


def load_menu(game):
    query = game.assets.text('loadFromWherePrompt')
    source = game.ask(Kind.SLOT.value, tuple(game.assets.text('sourceGameMenu').split()),
                      prompt=query, query=query, source=True, start=0)
    if source == 2: return
    game.s.g['save.file_format'] = 1 - source
    from . import save
    folder = save.load_directory(game)
    if folder is None: return
    index = file_index(folder)
    extension = '.PTY' if source == 0 else '.DAT'
    available = [slot for slot in SLOTS if 'SAVGAM' + slot + extension in index]
    if not available: return
    choice = source if source < len(available) else 0
    while True:
        choice = choose(game, Kind.SLOT, game.assets.text('loadWhichGamePrompt'), available,
                        menu=game.assets.text('saveSlotMenu'), menu_labels=tuple(SLOTS),
                        enabled=tuple(SLOTS.index(slot) for slot in available), start=choice)
        if choice is None: return
        try:
            if file_path(folder, 'SAVGAM' + available[choice] + extension).is_file(): break
        except OSError:
            pass
    if source == 0: save.load_game(game, available[choice], folder)
    else: save.load_imported_game(game, folder, available[choice])


def load_slot(game, slot):
    from . import save
    return save.load_game(game, slot)


def test():
    from .menu import MenuAssets
    from sm.titles.ssb.state import State
    assets, state = MenuAssets(), State()
    assert assets.choices(state) == (CREATE, ADD, LOAD, INIT, QUIT)
    state.party = [object()]
    assert assets.choices(state) == (CREATE, DROP, MODIFY, VIEW, ADD, REMOVE, SAVE, BEGIN, QUIT)
    state.r1[0x2A8] = 1
    assert TRAIN in assets.choices(state) and KNIGHT_MENU in assets.choices(state)


def con_bonus(b, t, cls):
    con = b[F['abilities'] + 2 * CONSTITUTION + 1]
    bonus = t.conHpTable[con - 3]
    if cls in (FIGHTER, PALADIN, KNIGHT, RANGER):
        bonus += {17: 1, 18: 2, 19: 3, 20: 3, 21: 4, 22: 4, 23: 4, 24: 5, 25: 5}.get(con, 0)
    return bonus

def roll_abilities(s, b, t):
    race, gender, cls, age = b[F['race']], b[F['gender']], b[F['class']], word(b, 'age')
    old = [age > t.age_limit(race, band) for band in range(4)]
    adjust = (old[0] - old[1] - 2 * old[2] - old[3], old[1] + old[3], old[1] + old[2] + old[3] - (not old[0]),
              -2 * old[2] - old[3], -(old[1] + old[2] + old[3]), 0)
    columns = ((gender, 2 + gender), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15))
    b[F['strength_extra']] = 0
    for ability in range(6):
        value = max(dice(s, 3, 6) + 1 for _ in range(6)) + adjust[ability]
        low, high = t.race_limit(race, columns[ability][0]), t.race_limit(race, columns[ability][1])
        value = max(min(max(value, low), high), t.classMin[cls * 6 + ability])
        if ability == WISDOM and 8 <= cls <= 12: value = max(value, 13)
        b[F['abilities'] + 2 * ability] = b[F['abilities'] + 2 * ability + 1] = value
        if ability == STRENGTH and value == 18 and any(levels(b)[c] for c in (FIGHTER, PALADIN, RANGER, KNIGHT)):
            b[F['strength_extra']] = min(s.random(100) + 1, t.race_limit(race, 4 + gender))
    b[F['strength_extra_base']] = b[F['strength_extra']]

def default_icon(b):
    large = b[F['icon_size']] == 2
    b[F['icon_head']] = 3 if b[F['race']] == KENDER else (9 if large else 7) if b[F['gender']] else (5 if large else 0)
    lv = levels(b)
    b[F['icon_body']] = 23 if lv[CLERIC] else 1 if lv[RANGER] else 24 if lv[KNIGHT] or lv[PALADIN] or lv[FIGHTER] else 29 if lv[MAGE] else 5

def edit_icon(game, b):
    menus = tuple(tuple(row.split()) for row in game.assets.names('iconMenus'))
    fields = ('icon_head', 'icon_body', 'icon_size')
    colors = F['icon_colors']
    while True:
        remember_icon_disk(game)
        saved = {field: b[F[field]] for field in fields}
        saved_colors = bytes(b[colors:colors + 6])
        old = tuple(saved.values()) + tuple(saved_colors)
        mode, parent, field, shift, slot = 0, 1, 'icon_head', 0, 0
        while True:
            enabled = tuple(i for i in range(len(menus[mode]))
                            if not (mode == 2 and i == (2 if shift else 3))
                            and not (mode == 3 and i == b[F['icon_size']] - 1))
            preview = tuple(b[F[key]] for key in fields) + tuple(b[colors:colors + 6])
            pick = game.ask(Kind.ICON.value, tuple(menus[mode][i] for i in enabled), prompt='',
                            icon_state=mode + 1, icon_old=old, icon_preview=preview, at=0)
            action = enabled[pick]
            if mode == 3 or (mode == 4 and parent == 1):
                remember_icon_disk(game)
            if mode == 0:
                if action == 4: break
                if action == 0: mode = 1
                elif action == 3: mode = 3
                else: shift, mode = (0 if action == 1 else 4), 2
            elif mode == 1:
                if action == 2: mode = 0
                else: field, parent, mode = fields[action], 1, 4
            elif mode == 2:
                if action == 7: mode = 0
                else: slot, parent, mode = (5, 0, 3, 3, 4, 1, 2)[action], 2, 4
            elif mode == 3:
                if action < 2: b[F['icon_size']] = action + 1
                else:
                    if action == 2: saved['icon_size'] = b[F['icon_size']]
                    else: b[F['icon_size']] = saved['icon_size']
                    mode = 0
            elif action < 2:
                delta = 1 if action == 0 else -1
                if parent == 1:
                    b[F[field]] = (b[F[field]] + delta) % (14 if field == 'icon_head' else 32)
                else:
                    at = colors + slot
                    value = ((b[at] >> shift) + delta) & 15
                    b[at] = b[at] & (15 << (4 - shift)) | value << shift
            else:
                if parent == 1:
                    if action == 2: saved[field] = b[F[field]]
                    else: b[F[field]] = saved[field]
                elif action == 2: saved_colors = bytes(b[colors:colors + 6])
                else: b[colors:colors + 6] = saved_colors
                mode = parent
        for key, value in saved.items(): b[F[key]] = value
        b[colors:colors + 6] = saved_colors
        if yes_no(game, Kind.ICON, game.assets.text('iconOkQuery'), icon_state=0, at=0): return


def customize_icon(game, b):
    return edit_icon(game, b)
