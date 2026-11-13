from enum import Enum
from functools import lru_cache
import os
from pathlib import Path
import shutil
import struct
import tempfile

from .faults import BindingRequired
from .records import Character, Item, Effect, split_records
from . import rules
from . import save as codec


class Kind(str, Enum):
    MAIN_MENU = 'CREATE_MENU'
    RACE = 'CREATE_RACE'
    GENDER = 'CREATE_GENDER'
    CLASS = 'CREATE_CLASS'
    DEITY = 'CREATE_DEITY'
    ALIGNMENT = 'CREATE_ALIGNMENT'
    ROLL = 'CREATE_ROLL'
    NAME = 'CREATE_NAME'
    ICON = 'CREATE_ICON'
    SAVE = 'CREATE_SAVE'
    OVERWRITE = 'CREATE_OVERWRITE'
    FILE_NAME = 'CREATE_FILE_NAME'
    ADD = 'CREATE_ADD'
    SLOT = 'CREATE_SLOT'
    WHO = 'CREATE_WHO'
    VIEW = 'CREATE_VIEW'
    DROP = 'CREATE_DROP'
    INIT = 'CREATE_INIT'
    QUIT = 'CREATE_QUIT'


CREATE, DROP, MODIFY, TRAIN, KNIGHT_MENU, VIEW, ADD, REMOVE, LOAD, SAVE, BEGIN, INIT, QUIT = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
DELAY, PICTURES, ANIMATIONS = 'game.delay', 'game.pictures', 'game.animations'
SETTING_START = {DELAY: 4, PICTURES: 1, ANIMATIONS: 1}
DELAY_CELL, PICTURES_CELL = 0xFC, 0xFF
CLERIC, FIGHTER, PALADIN, RANGER, MAGE, THIEF, KNIGHT = 0, 2, 3, 4, 5, 6, 7
HILL_DWARF, MOUNTAIN_DWARF, KENDER = 4, 3, 5
STRENGTH, INTELLIGENCE, WISDOM, DEXTERITY, CONSTITUTION, CHARISMA = range(6)
ABILITY_LABELS = ('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHA')
EXIT = 'Exit'
PENDING, TRAIN_MASK, PARTY_SIZE = 'creation.pending', 0x2A8, 0x33E
NPC_FLAG, ROSTER_HIDE_BYTE = 128, 247
INVALID_FILE_CHARS = ' .*,?/\\:;|'
F = {name: offset for name, (offset, _) in Character.FIELDS.items()}
STEEL = 4

START = {CLERIC: ({CLERIC: 1}, 0), FIGHTER: ({FIGHTER: 2}, 2001), RANGER: ({RANGER: 2}, 2251), MAGE: ({MAGE: 2}, 5000),
         THIEF: ({THIEF: 2}, 1251), KNIGHT: ({KNIGHT: 1}, 2500), 8: ({CLERIC: 1, FIGHTER: 1}, 2001),
         9: ({CLERIC: 1, FIGHTER: 1, MAGE: 1}, 5000), 10: ({CLERIC: 1, RANGER: 1}, 2251), 11: ({CLERIC: 1, MAGE: 1}, 5000),
         12: ({CLERIC: 1, THIEF: 1}, 0), 13: ({FIGHTER: 1, MAGE: 1}, 5000), 14: ({FIGHTER: 1, THIEF: 1}, 2001),
         15: ({FIGHTER: 1, MAGE: 1, THIEF: 1}, 5000), 16: ({MAGE: 1, THIEF: 1}, 5000)}
RACIAL_EFFECTS = {KENDER: (92, 94), MOUNTAIN_DWARF: (94, 26, 47), HILL_DWARF: (94, 26, 47), 0: (95,), 1: (95,), 2: (18,)}
RANGER_EFFECT = 105
AGE_CLASS = {8: CLERIC, 9: CLERIC, 10: CLERIC, 11: CLERIC, 12: MAGE, 13: MAGE, 15: MAGE, 16: MAGE, 14: FIGHTER}
DEITY_GRANTS = {1: (0x15, (101,)), 2: (0x15, (102,)), 3: (0x15, (103,)), 4: (0x15, (104, 105, 106)),
                5: (0x2E, (107,)), 6: (0x2E, ()), 7: (0x2E, (106,))}
MAGE_FIRST_SPELLS = (11, 18, 12, 15, 21)
MAGE_TRAINED_SPELLS = {2: (15,), 3: (34, 10), 4: (31,), 5: (47,)}
MONEY_DICE = {CLERIC: (3, 6), FIGHTER: (5, 4), RANGER: (5, 4), MAGE: (2, 4), THIEF: (2, 6)}
KNIGHT_KIT = ((36, 47, 450), (37, 0, 60), (18, 0, 50))
FIXED_HP_PAST_LIMIT = {FIGHTER: 3, KNIGHT: 3, RANGER: 2, CLERIC: 2, THIEF: 2, MAGE: 1}
COLOUR_PARTS = (('Weapon', 6), ('Body', 1), ('Hair/Face', 4), ('Shield', 5), ('Arm', 2), ('Leg', 3))


class Tables:
    def __init__(self, assets):
        def names(part, width):
            raw = assets.part(part)
            return tuple(raw[i + 1:i + 1 + raw[i]].decode('cp437') for i in range(0, len(raw), width))
        self.assets = assets
        self.races, self.classes = names('raceNames', 16), names('classNames', 27)
        self.alignments, self.deities, self.genders = names('alignmentNames', 17), names('deityNames', 12), names('genderNames', 7)
        self.alignment_choices, self.hp_dice, self.hp_sides = assets.part('alignmentChoices'), assets.part('hpDice'), assets.part('hpSides')
        self.icon_colours, self.limits = assets.part('defIconColors'), assets.part('raceLimits')
        self.start_age = tuple(struct.iter_unpack('<HBB', assets.part('startAge')))
        self.age_limits = assets.part('ageLimit')
        self.progression, self.known_spells = assets.part('classProgression'), assets.part('knownSpellTable')
        for name in ('raceClass', 'classMin', 'classAlignMask', 'conHpTable', 'classBits', 'classMaskTable', 'hitDiceLimit', 'thac0Table'):
            setattr(self, name, assets.table(name))

    def legal_classes(self, race):
        row = self.raceClass[race * 15:(race + 1) * 15]
        return tuple(row[1:1 + row[0]])

    def race_limit(self, race, column):
        return self.limits[race * 16 + column]

    def age_limit(self, race, band):
        return struct.unpack_from('<H', self.age_limits, race * 10 + band * 2)[0]

    def level_xp(self, suborder, level):
        return struct.unpack_from('<i', self.progression, suborder * 99 + (level - 2) * 4)[0]


@lru_cache(maxsize=4)
def tables(assets):
    return Tables(assets)


def dice(s, count, sides):
    return sum(s.random(sides) + 1 for _ in range(count)) & 255


def levels(b):
    return b[F['levels']:F['levels'] + 8]


def word(b, field):
    return int.from_bytes(b[F[field]:F[field] + 2], 'little')


def set_word(b, field, value):
    b[F[field]:F[field] + 2] = (value & 0xFFFF).to_bytes(2, 'little')


def xp(b):
    return int.from_bytes(b[F['experience']:F['experience'] + 4], 'little', signed=True)


def know(b, *spells):
    for spell in spells:
        b[F['known_spells'] + spell - 1] = 1


def choose(game, kind, prompt, labels, **info):
    if kind in (Kind.RACE, Kind.GENDER, Kind.CLASS, Kind.DEITY, Kind.ALIGNMENT):
        info = dict(info, window='1 2 38 22', header=prompt, indent=2)
    elif kind == Kind.ADD:
        info = dict(info, window='1 2 38 22', query=prompt, menu='Add')
    pick = game.ask(kind.value, tuple(labels) + (EXIT,), prompt=prompt, **info)
    return None if pick == len(labels) else pick


def yes_no(game, kind, prompt, **info):
    return game.ask(kind.value, ('Yes', 'No'), prompt=prompt, **info) == 0


def suborder(b, cls):
    if cls == CLERIC: return 0 if b[F['deity']] <= 4 else 1
    if cls == KNIGHT: return 2 + b[F['knight_order']]
    if cls == MAGE: return 7 if b[F['robe_order']] == 1 else 8
    return {FIGHTER: 2, RANGER: 6, THIEF: 9}[cls]


def con_bonus(b, t, cls):
    con = b[F['abilities'] + 2 * CONSTITUTION + 1]
    bonus = t.conHpTable[con - 3]
    if cls in (FIGHTER, KNIGHT, RANGER):
        bonus += {17: 1, 18: 2, 19: 3, 20: 3, 21: 4, 22: 4, 23: 4, 24: 5, 25: 5}.get(con, 0)
    return bonus


def gain_hp(s, b, t, mask, divisor):
    total = bonus = 0
    for cls, level in enumerate(levels(b)):
        if not level or not t.classBits[cls] & mask: continue
        if level >= t.hitDiceLimit[cls]:
            total = FIXED_HP_PAST_LIMIT[cls]
            continue
        count = 1 if level > 1 or cls == CLERIC and b[F['deity']] > 4 else t.hp_dice[cls]
        total = (total + max(dice(s, count, t.hp_sides[cls]), dice(s, count, t.hp_sides[cls]))) & 255
        bonus = (bonus + count * con_bonus(b, t, cls)) & 255
    gain = max(total // divisor, 1)
    b[F['hp_rolled']] = (b[F['hp_rolled']] + gain) & 255
    wounds = (b[F['hp_max']] - b[F['hp']]) & 255
    b[F['hp_max']] = (b[F['hp_max']] + gain + bonus // divisor) & 255
    b[F['hp']] = (b[F['hp_max']] - wounds) & 255


def train_to_experience(s, b, t):
    strength = b[F['abilities'] + 2 * STRENGTH]
    while True:
        mask = 0
        for cls, level in enumerate(levels(b)):
            if not level: continue
            if (b[F['race']] == KENDER and cls in (FIGHTER, RANGER) and
                    (level == 7 or level == 6 and strength == 17 or level == 5 and strength < 17)): continue
            need = t.level_xp(suborder(b, cls), level + 1)
            if 0 < need <= xp(b): mask += t.classBits[cls]
        if not mask: return
        count = 0
        for cls in range(8):
            if b[F['levels'] + cls]:
                count += 1
                if t.classBits[cls] & mask: b[F['levels'] + cls] += 1
        b[F['highest_level']] = max(b[F['highest_level']], *levels(b))
        know(b, *MAGE_TRAINED_SPELLS.get(b[F['levels'] + MAGE], ()))
        if b[F['highest_level']] > b[F['dual_threshold']]: gain_hp(s, b, t, mask, count)


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
        if ability == STRENGTH and value == 18 and any(levels(b)[c] for c in (FIGHTER, RANGER, KNIGHT)):
            b[F['strength_extra']] = min(s.random(100) + 1, t.race_limit(race, 4 + gender))
    b[F['strength_extra_base']] = b[F['strength_extra']]


def roll_money_and_hit_points(s, b, t):
    b[F['attacks']], b[F['unarmed_rolls']], b[F['unarmed_dice']] = 2, 1, 2
    b[F['use_strength']], b[F['base_move']] = 1, 12
    b[F['spell_slots']:F['spell_slots'] + 20] = bytes(20)
    steel = classes = 0
    for cls, level in enumerate(levels(b)):
        if not level: continue
        classes += 1
        if cls == KNIGHT: steel = dice(s, 1, 4)
        else: steel = (steel + dice(s, *MONEY_DICE[cls])) & 255
        if cls == CLERIC: know(b, *[spell for spell in t.known_spells[:10] if spell])
        elif cls == MAGE: know(b, *MAGE_FIRST_SPELLS)
    steel = (steel + steel * 20 // 100) & 255
    money = F['money'] + STEEL * 2
    b[money:money + 2] = steel.to_bytes(2, 'little')
    b[F['hp_max']] = b[F['hp_rolled']] = b[F['hp']] = 0
    gain_hp(s, b, t, 255, classes)
    train_to_experience(s, b, t)


def summary(b, t):
    parts = []
    for ability, label in enumerate(ABILITY_LABELS):
        value = b[F['abilities'] + 2 * ability + 1]
        if ability == STRENGTH and b[F['strength_extra']]: parts.append('%s %d/%02d' % (label, value, b[F['strength_extra']] % 100))
        else: parts.append('%s %d' % (label, value))
    return dict(abilities=' '.join(parts), hp=b[F['hp_max']], age=word(b, 'age'),
                levels='/'.join(str(v) for v in levels(b) if v), steel=int.from_bytes(b[F['money'] + STEEL * 2:F['money'] + STEEL * 2 + 2], 'little'))


def pending(s, r, items, effects):
    s.g[PENDING] = bytes(r), tuple(bytes(i) for i in items), tuple(bytes(e) for e in effects)


def add_effect(effects, kind):
    effect = Effect(); effect.set('type', kind); effect.set('strength', 255); effects.append(effect)


def default_icon(b):
    large = b[F['icon_size']] == 2
    b[F['icon_head']] = 3 if b[F['race']] == KENDER else (9 if large else 7) if b[F['gender']] else (5 if large else 0)
    lv = levels(b)
    b[F['icon_body']] = 23 if lv[CLERIC] else 1 if lv[RANGER] else 24 if lv[KNIGHT] or lv[FIGHTER] else 29 if lv[MAGE] else 5


def customize_icon(game, b):
    while True:
        pick = choose(game, Kind.ICON, game.assets.text('iconOk'), ('Keep', 'Head', 'Weapon', 'Size', '1st-color', '2nd-color'))
        if pick in (None, 0): return
        if pick in (1, 2):
            field, options = ('icon_head', 14) if pick == 1 else ('icon_body', 32)
            value = choose(game, Kind.ICON, field, [str(i) for i in range(options)], field=field)
            if value is not None: b[F[field]] = value
        elif pick == 3:
            value = choose(game, Kind.ICON, 'size', ('Small', 'Large'), field='icon_size')
            if value is not None: b[F['icon_size']] = value + 1
        else:
            part = choose(game, Kind.ICON, 'part', [name for name, _ in COLOUR_PARTS], field='part')
            if part is None: continue
            value = choose(game, Kind.ICON, 'color', [str(i) for i in range(16)], field='colour')
            if value is None: continue
            at = F['icon_colors'] + COLOUR_PARTS[part][1] - 1
            b[at] = b[at] & 0xF0 | value if pick == 4 else b[at] & 0x0F | value << 4


def read_name(game, kind, prompt, limit):
    while True:
        text = game.ask(kind.value, None, prompt=prompt, min_length=1, max_length=limit)
        if isinstance(text, str) and 1 <= len(text) <= limit and all(' ' <= ch <= 'z' for ch in text):
            return text.encode('ascii').upper()


def sanitize(text, remove):
    index, limit = 0, len(text) - len(remove) + 1
    while index < limit:
        if text[index:index + len(remove)] == remove: text = text[:index] + text[index + len(remove):]
        index += 1
    return text


def dos_stem(name):
    for ch in INVALID_FILE_CHARS: name = sanitize(name, ch)
    return name[:8].upper()


def file_stem(name):
    return dos_stem(sanitize(name, '.'))


def save_directory(directory=None):
    root = Path(directory) if directory else Path(os.environ.get('SM_SAVE_ROOT') or Path(__file__).resolve().parents[3] / 'local' / 'saves') / 'cok'
    root.mkdir(parents=True, exist_ok=True)
    return root


def store(game, r, items, effects):
    directory = save_directory(getattr(game, 'roster_directory', None))
    stem = file_stem(r.get('name')[1:1 + r.data[0]].decode('ascii'))
    while (directory / (stem + '.WHO')).exists():
        if yes_no(game, Kind.OVERWRITE, 'Overwrite ' + stem + '? '): break
        typed = read_name(game, Kind.FILE_NAME, 'New file name: ', 8)
        stem = typed.decode('ascii')
        r.set('name', bytes([len(typed)]) + typed + bytes(15 - len(typed)))
    live = rules.character(bytes(r), [bytes(i) for i in items], [bytes(e) for e in effects])
    rules.recalc(live)
    who, stf, sfx = rules.write_character(live)
    (directory / (stem + '.WHO')).write_bytes(who)
    for suffix, raw in (('.STF', stf), ('.SFX', sfx)):
        path = directory / (stem + suffix)
        if raw: path.write_bytes(raw)
        elif path.exists(): path.unlink()
    return stem


def knight_kit():
    items = []
    for kind, middle, weight in KNIGHT_KIT:
        item = Item(); item.set('type', kind); item.data[Item.FIELDS['name_ids'][0] + 1] = middle
        item.data[Item.FIELDS['name_ids'][0] + 2] = kind; item.set('weight', weight); items.append(item)
    return items


def create(game):
    s, t = game.s, tables(game.assets)
    r = Character(); b = r.data; items, effects = [], []
    for slot, colour in enumerate(t.icon_colours):
        b[F['icon_colors'] + slot] = (colour + (colour + 8) * 16) & 255
    b[F['base_ac']], b[F['base_thac0']], b[F['status']], b[F['active']], b[F['dimensions']] = 50, 40, 0, 1, 1
    b[F['creature_id']] = s.random(256); b[F['order']] = 10
    try:
        pending(s, r, items, effects)
        race = choose(game, Kind.RACE, game.assets.text('pickRace'), t.races[:7])
        if race is None: return None
        b[F['race']] = race; b[F['icon_size']] = 1 if race in (KENDER, MOUNTAIN_DWARF, HILL_DWARF) else 2
        for kind in RACIAL_EFFECTS.get(race, ()): add_effect(effects, kind)
        gender = choose(game, Kind.GENDER, game.assets.text('pickGender'), t.genders)
        if gender is None: return None
        b[F['gender']] = gender

        legal = t.legal_classes(race)
        pick = choose(game, Kind.CLASS, game.assets.text('pickClass'), [t.classes[c] for c in legal])
        if pick is None: return None
        cls = legal[pick]; start_levels, experience = START[cls]
        b[F['class']] = cls
        for slot, level in start_levels.items(): b[F['levels'] + slot] = level
        b[F['experience']:F['experience'] + 4] = experience.to_bytes(4, 'little', signed=True)
        if KNIGHT in start_levels: b[F['knight_order']] = 1
        if RANGER in start_levels: add_effect(effects, RANGER_EFFECT)
        b[F['base_thac0']] = max(t.thac0Table[slot * 13 + level] for slot, level in start_levels.items())
        b[F['class_mask']] = sum(t.classMaskTable[slot] for slot in start_levels)
        pending(s, r, items, effects)

        alignment_mask = 0xFF
        if CLERIC in start_levels:
            dwarf = race in (MOUNTAIN_DWARF, HILL_DWARF)
            pick = choose(game, Kind.DEITY, game.assets.text('pickGod'), t.deities[6:7] if dwarf else t.deities[1:8])
            if pick is None: return None
            deity = 6 if dwarf else pick + 1
            b[F['deity']] = deity; alignment_mask, spells = DEITY_GRANTS[deity]
            know(b, *spells)
            if deity == 3 or deity == 6 and dwarf: b[F['base_thac0']] += 1

        allowed = [a for bit, a in enumerate(t.alignment_choices) if (t.classAlignMask[cls] & alignment_mask) >> bit & 1]
        pick = choose(game, Kind.ALIGNMENT, game.assets.text('pickAlignment'), [t.alignments[a] for a in allowed])
        if pick is None: return None
        alignment = b[F['alignment']] = allowed[pick]
        grant = {0: (2000, 1), 3: (2000, 1), 6: (2000, 1), 1: (1500, 2), 4: (1500, 2), 7: (1500, 2)}[alignment]
        if xp(b) == 0 and CLERIC in start_levels: b[F['experience']:F['experience'] + 4] = grant[0].to_bytes(4, 'little', signed=True)
        if MAGE in start_levels: b[F['robe_order']] = grant[1]
        if cls <= KNIGHT:
            base, count, sides = t.start_age[race * 8 + cls]; set_word(b, 'age', base + dice(s, count, sides))
        else:
            base, count, sides = t.start_age[race * 8 + AGE_CLASS[cls]]; set_word(b, 'age', base + sides * count)

        while True:
            for slot in start_levels: b[F['levels'] + slot] = 1
            roll_abilities(s, b, t)
            roll_money_and_hit_points(s, b, t)
            pending(s, r, items, effects)
            if not yes_no(game, Kind.ROLL, game.assets.text('rerollStats'), **summary(b, t)): break

        raw = read_name(game, Kind.NAME, game.assets.text('characterName'), 15)
        b[F['name']:F['name'] + 16] = bytes([len(raw)]) + raw + bytes(15 - len(raw))
        default_icon(b); customize_icon(game, b); pending(s, r, items, effects)
        for ability in range(6): b[F['abilities'] + 2 * ability] = b[F['abilities'] + 2 * ability + 1]
        b[F['strength_extra_base']] = b[F['strength_extra']]

        if not yes_no(game, Kind.SAVE, game.assets.text('saveQuery') + raw.decode('ascii') + '? '): return None
        if KNIGHT in start_levels:
            items = knight_kit(); b[F['item_count']] = len(items)
        return store(game, r, items, effects)
    finally:
        s.g.pop(PENDING, None)


def roster(state, directory=None):
    folder = save_directory(directory); out = []
    text = lambda raw: bytes(raw[1:1 + raw[0]]).ljust(15)
    held = {text(c.b) for c in state.party}
    for path in folder.glob('*.WHO'):
        raw = path.read_bytes()
        if len(raw) != Character.SIZE or raw[ROSTER_HIDE_BYTE] >= NPC_FLAG or text(raw) in held: continue
        out.append(dict(file=path.stem, name=raw[1:1 + raw[0]].decode('cp437'), path=str(path)))
    return out


def read_character(entry):
    path = Path(entry['path']); raw = path.read_bytes()
    items = path.with_suffix('.STF').read_bytes() if path.with_suffix('.STF').exists() else b''
    effects = path.with_suffix('.SFX').read_bytes() if path.with_suffix('.SFX').exists() else b''
    return raw, [bytes(x) for x in codec.whole(items, Item)], [bytes(x) for x in codec.whole(effects, Effect)]


def evil(alignment):
    return (alignment + 1) % 3 == 0


def refusal(game, c, party):
    if any(p[:16] == c[:16] and p[F['creature_id']] == c[F['creature_id']] for p in party): return ''
    a = game.assets; pc = sum(p[F['npc']] < NPC_FLAG for p in party)
    rangers = sum(p[F['levels'] + RANGER] > 0 for p in party)
    paladins = [p for p in party if p[F['levels'] + PALADIN] > 0]
    if c[F['levels'] + PALADIN] and any(evil(p[F['alignment']]) for p in party): return a.text('noPaladin')
    if c[F['levels'] + RANGER] and rangers >= 3: return a.text('tooManyRangers')
    if evil(c[F['alignment']]) and paladins:
        return paladins[-1][1:1 + paladins[-1][0]].decode('cp437') + a.text('noEvil')
    if c[F['npc']] < NPC_FLAG and pc >= 6 or c[F['npc']] >= NPC_FLAG and len(party) >= 8: return ''
    return None


def join(game, raw, items, effects):
    s = game.s
    live = rules.character(raw, items, effects); rules.recalc(live)
    used = {c.b[F['order']] for c in s.party}
    live.b[F['order']] = next(i for i in range(8) if i not in used)
    s.party.append(live); s.sel = len(s.party) - 1; s.r1[PARTY_SIZE] = len(s.party)


def add(game):
    s = game.s
    entries = roster(s, getattr(game, 'roster_directory', None))
    if not entries: return
    starred, message = set(), ''
    while True:
        labels = [('* ' if e['file'] in starred else '') + e['name'] for e in entries]
        pick = choose(game, Kind.ADD, game.assets.text('addCharacter'), labels, message=message)
        if pick is None: return
        message = ''; entry = entries[pick]
        if entry['file'] in starred: continue
        raw, items, effects = read_character(entry)
        why = refusal(game, raw, [c.b for c in s.party])
        if why is None:
            join(game, raw, items, effects); starred.add(entry['file'])
        else: message = why
        if sum(c.b[F['npc']] < NPC_FLAG for c in s.party) > 5 or len(s.party) > 7: return


SLOTS = 'ABCDEFGHIJ'


def slot_folder(game, slot):
    return save_directory(getattr(game, 'roster_directory', None)) / slot


def slot_source(game, slot):
    own = slot_folder(game, slot)
    return own if (own / ('SAVGAM%s.DAT' % slot)).is_file() else Path(game.directory) / 'SAVE'


def available_slots(game):
    return [slot for slot in SLOTS if (slot_source(game, slot) / ('SAVGAM%s.DAT' % slot)).is_file()]


def forget_roster_copies(game):
    roster_folder = save_directory(getattr(game, 'roster_directory', None))
    for char in game.s.party:
        stem = dos_stem(bytes(char.b[1:1 + char.b[0]]).decode('cp437'))
        for suffix in ('.WHO', '.STF', '.SFX'):
            (roster_folder / (stem + suffix)).unlink(missing_ok=True)


def write_slot(game, slot, files):
    target = slot_folder(game, slot)
    old, stage = target.with_name(slot + '-old'), Path(tempfile.mkdtemp(prefix=slot + '-new-', dir=target.parent))
    try:
        for name, raw in files.items(): (stage / name).write_bytes(raw)
        shutil.rmtree(old, ignore_errors=True)
        if target.exists(): target.rename(old)
        try: stage.rename(target)
        except OSError:
            if old.exists(): old.rename(target)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)


def save_game(game, slot):
    s = game.s
    if slot not in SLOTS or len(slot) != 1: raise ValueError('Champions save slot must be A through J')
    if not s.party: raise ValueError('There is no party to save')
    s.r1[codec.DISK_CELL] = s.dataset & 255
    s.r0[DELAY_CELL] = game_setting(s, DELAY)
    s.r0[PICTURES_CELL] = game_setting(s, PICTURES) * 2 + game_setting(s, ANIMATIONS)
    game.recently_saved = True
    snapshot = codec.Snapshot(slot, codec.game_image(s, slot), {})
    for stem, char in zip(codec.member_names(slot, len(s.party)), s.party):
        who, stf, sfx = rules.write_character(char)
        snapshot.members[stem] = {'SAV': (Character(who),)}
        if stf: snapshot.members[stem]['STF'] = split_records(stf, Item)
        if sfx: snapshot.members[stem]['SFX'] = split_records(sfx, Effect)
    write_slot(game, slot, snapshot.dump())
    forget_roster_copies(game)


def load_game(game, slot):
    s = game.s
    snapshot = rules.load_slot(slot_source(game, slot), slot)
    codec.apply_image(s, snapshot.game)
    s.g[DELAY], s.g[PICTURES], s.g[ANIMATIONS] = s.r0[DELAY_CELL] & 255, s.r0[PICTURES_CELL] >> 1 & 255, s.r0[PICTURES_CELL] & 1
    s.monsters, s.sel, s.party_dead = [], 0, 0
    rules.restore(s, snapshot)
    s.r1[PARTY_SIZE] = len(s.party)
    icons = getattr(getattr(game, 'vm', None), 'icons', None)
    if icons is not None:
        for c in s.party:
            if c.b[F['npc']] > 127: icons[c.b[F['order']]] = ('CPIC', c.b[F['creature_id']], s.dataset)
    game.walls_filed = tuple(slot for slot, ident in enumerate(s.walls, 1) if ident == 0)
    forget_roster_copies(game)


def load_menu(game):
    slots = available_slots(game)
    if not slots: return
    pick = choose(game, Kind.SLOT, game.assets.text('loadQuery'), slots)
    if pick is None: return
    load_game(game, slots[pick])
    game.s.prev_mode, game.s.mode = game.s.mode, 0
    game.vm.resuming = True
    game.geo.resume(game.s, game.vm)


def save_menu(game):
    pick = choose(game, Kind.SLOT, game.assets.text('saveGameQuery'), SLOTS)
    if pick is not None: save_game(game, SLOTS[pick])


def game_setting(s, name):
    return s.g.get(name, SETTING_START[name])


def member_title(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def pick_member(game):
    s = game.s
    who = choose(game, Kind.WHO, 'Pick Character ', [bytes(c.b[1:1 + c.b[0]]).decode('cp437') for c in s.party])
    if who is None: return None
    s.sel = who
    return s.party[who]


def sheet(game, char):
    b, t = char.b, tables(game.assets)
    label = t.classes[b[F['class']]]
    if b[F['levels'] + CLERIC]: label = t.deities[b[F['deity']]] + ' ' + label
    if b[F['levels'] + MAGE]: label = label.replace('Mage', ('', 'White ', 'Red ', 'Black ')[b[F['robe_order']]] + 'Mage', 1)
    if b[F['levels'] + KNIGHT]: label += ' of the ' + ('', 'Crown', 'Sword', 'Rose')[b[F['knight_order']]]
    money = dict(zip(('copper', 'bronze', 'platinum', 'steel', 'gems', 'jewelry'), struct.unpack_from('<6H', b, F['money'] + 2)))
    return dict(summary(b, t), name=bytes(b[1:1 + b[0]]).decode('cp437'), status=b[F['status']], gender=t.genders[b[F['gender']]],
                alignment=t.alignments[b[F['alignment']]], race=t.races[b[F['race']]], description=label, experience=xp(b),
                hp_now=b[F['hp']], thac0=b[F['thac0']], ac=b[F['ac']], move=b[F['move']], **money)


def view(game):
    char = pick_member(game)
    if char is not None:
        from . import inventory
        inventory.view(game, char)


def remove_creature(game, char):
    s = game.s
    index = s.party.index(char)
    del s.party[index]
    s.sel = max(index - 1, 0)
    s.r1[PARTY_SIZE] = len(s.party)


def drop(game):
    char = pick_member(game)
    if char is None: return
    name = bytes(char.b[1:1 + char.b[0]]).decode('cp437')
    if yes_no(game, Kind.DROP, 'Drop ' + name + ' forever? ') and yes_no(game, Kind.DROP, 'Are you sure? '):
        game.menu_note = ('You dump ' + name + ' out back.') if not char.b[F['active']] else name + ' bids you farewell.'
        roster_folder = save_directory(getattr(game, 'roster_directory', None))
        stem = dos_stem(name)
        for suffix in ('.WHO', '.STF', '.SFX'): (roster_folder / (stem + suffix)).unlink(missing_ok=True)
        remove_creature(game, char)
    else: game.menu_note = name + ' breathes a sigh of relief.'


def remove(game):
    char = pick_member(game)
    if char is None: return
    if char.b[F['npc']] >= NPC_FLAG:
        drop(game)
        return
    store(game, Character(bytes(char.b)), [bytes(i) for i in char.items], [bytes(e) for e in char.effects])
    remove_creature(game, char)


def init_input(game):
    s = game.s
    while True:
        mouse = s.g.get('input.mouse', 0)
        pick = choose(game, Kind.INIT, 'Init Mouse/Joystick: ', ('mouse ON' if mouse else 'mouse OFF', 'joystick OFF', 'disable both'))
        if pick is None: return
        if pick == 0: s.g['input.mouse'] = int(not mouse)
        elif pick == 2: s.g['input.mouse'] = 0


def confirm_quit(game):
    if not yes_no(game, Kind.QUIT, 'Quit to DOS '): return False
    if game.s.party and not getattr(game, 'recently_saved', False):
        if not yes_no(game, Kind.QUIT, 'Game NOT saved.  Quit anyway? '):
            save_menu(game)
            return False
    game.s.stop = 1
    game.exit_game = True
    return True


def run(game):
    s = game.s; mode, s.mode = s.mode, 0
    while True:
        ids = game.menu_ids = game.assets.choices(s)
        note, game.menu_note = getattr(game, 'menu_note', ''), ''
        selected = ids[game.ask(Kind.MAIN_MENU.value, tuple(game.assets.labels[i] for i in ids), action='main-menu', at=0, message=note)]
        if selected not in (QUIT, SAVE): game.recently_saved = False
        if selected == CREATE: create(game)
        elif selected == ADD: add(game)
        elif selected == LOAD: load_menu(game)
        elif selected == SAVE: save_menu(game)
        elif selected == INIT: init_input(game)
        elif selected == QUIT:
            if confirm_quit(game): return
        elif selected == VIEW: view(game)
        elif selected == REMOVE: remove(game)
        elif selected == DROP: drop(game)
        elif selected in (TRAIN, KNIGHT_MENU, MODIFY):
            from . import training
            char = pick_member(game)
            if char is not None: {TRAIN: training.train, KNIGHT_MENU: training.knight_promotion, MODIFY: training.modify}[selected](game, char)
        elif selected == BEGIN and s.party:
            s.mode = mode; s.r1[TRAIN_MASK] = 0
            return
        else: raise BindingRequired('Champions main-menu action %d is not bound' % selected)
