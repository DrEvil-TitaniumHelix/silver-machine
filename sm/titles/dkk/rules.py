import struct
from functools import lru_cache
from pathlib import Path
from sm.files import file_path
from sm.titles.ssb.state import Char
from sm.titles.cok.rules import (_s8, _s16, _signed, _ability, _race, _bands,
    _strength_rank, _hit_strength, _damage_strength, _carry_allowance,
    _dex_armor, _dex_missile, _weapon_damage, _armor_move, _carry_move, _readied_special)
from .records import Character, Item, Spells
from .data import Assets
from . import save as codec

CLERIC, FIGHTER, PALADIN, RANGER, MAGE, THIEF, KNIGHT = 0, 2, 3, 4, 5, 6, 7
DWARVES, KENDER = (3, 4), 5
SLOT, HANDS, ARMOR, USABLE_BY = 0, 1, 6, 13
F = {name: offset for name, (offset, _) in Character.FIELDS.items()}


def _view(kind, raw):
    result = kind.__new__(kind)
    result.data = memoryview(raw)[:kind.SIZE]
    return result


def record(char):
    return _view(Character, char.b)


def allocate_item(game):
    from . import save_start
    host = getattr(game, 'game', game)
    pool = getattr(host, 'item_pool', None)
    if pool is None and hasattr(save_start, 'item_pool'):
        pool = save_start.item_pool(host)
    return pool.allocate() if pool is not None else bytearray(Item.SIZE)


def release_inventory(game, char):
    items = getattr(char, 'items', None)
    if items is None: return
    pool = getattr(getattr(game, 'game', game), 'item_pool', None)
    if pool is not None:
        for item in items:
            pool.release(item)
    items.clear()


def spellbook(char):
    return _view(Spells, memoryview(char.b)[Character.SIZE:]) if len(char.b) > Character.SIZE else None


def character(record_bytes, items=(), effects=(), rid=None, spells=None):
    if len(record_bytes) == Character.SIZE + Spells.SIZE:
        if spells is not None: raise ValueError('spellbook supplied twice')
        record_bytes, spells = record_bytes[:Character.SIZE], record_bytes[Character.SIZE:]
    raw = bytes(Character(record_bytes))
    if spells is not None:
        raw += bytes(Spells(spells))
    return Char(raw, items, effects, rid)


class Tables:
    def __init__(self, directory=None):
        self.assets = Assets(directory)
        self.image = self.assets.resident
        self.offset = {name: entry['offset'] for name, entry in self.assets.layout['tables'].items()}
        self.base = file_path(self.assets.root, 'ITEMS').read_bytes()[2:].ljust(129 * 16, b'\0')

    def u8(self, name, index):
        return self.image[self.offset[name] + index]

    def s8(self, name, index):
        return _s8(self.u8(name, index))

    def base_item(self, kind):
        if not 0 <= kind < 129:
            raise ValueError('item type outside the base table')
        return self.base[kind * 16:kind * 16 + 16]

    def gained_slots(self, row, level, spell_level):
        return self.u8('classProgression', row * 204 + 68 + (level - 2) * 8 + spell_level - 1)

    def level_xp(self, row, level):
        if not 2 <= level <= 18:
            return -1
        return self.progression_xp(row, level)

    def progression_xp(self, row, level):
        return struct.unpack_from('<i', self.image, self.offset['classProgression'] + row * 204 + (level - 2) * 4)[0]

    def save_needed(self, cls, level, kind):
        return self.u8('savingThrows', (cls * 18 + level - 1) * 5 + kind)


@lru_cache(maxsize=None)
def tables(directory=None):
    return Tables(directory)


def worn(char):
    slots, t = [None] * 13, tables()
    for raw in char.items:
        item = _view(Item, raw)
        if not item.get('readied'):
            continue
        kind = item.get('type')
        slot = t.base_item(kind)[SLOT]
        if slot <= 8:
            slots[slot] = item
        elif slot == 9:
            target = 9 if slots[9] is None else 10
            if slots[target] is None:
                slots[target] = item
        if kind in (30, 12):
            slots[11 if kind == 30 else 12] = item
    return slots


def movement(char, party_adjust=0):
    r, t = record(char), tables()
    move = r.get('base_move')
    for raw in char.items:
        item = _view(Item, raw)
        if item.get('readied'):
            move = _armor_move(r, item, move, t.base_item(item.get('type')))
    move = _carry_move(r, move, r.get('weight'))
    from .effects import has
    if has(char, 39): move = move * 2 & 255
    if has(char, 42): move //= 2
    if has(char, 9): move = move * 2 & 255
    r.set('move', move)
    if r.get('side') == 0: move = move + party_adjust & 255
    return move * 2 & 255


def recalc_sheet_stats(char, party_adjust):
    recalc_stats(char, party_adjust)
    movement(char, party_adjust)


def class_con_adjust(char, cls):
    con = _ability(record(char), 4)
    if not 3 <= con <= 19: return 70
    if con < 7: return -2 if con == 3 else -1
    if con < 15: return 0
    if con < 17: return con - 14
    return con - 14 if cls in (FIGHTER, PALADIN, RANGER, KNIGHT) else 2


def _cleric_slots(r, t):
    row = int(r.get('deity') > 4)
    result = bytearray((row + 1, 0, 0, 0, 0, 0, 0))
    for level in range(2, _signed(r, 'levels')[CLERIC] + 1):
        for k in range(7): result[k] = result[k] + t.gained_slots(row, level, k + 1) & 255
    for threshold, k in ((12, 0), (13, 0), (14, 1), (15, 1), (16, 2), (17, 3)):
        if _ability(r, 2) > threshold and result[k]: result[k] = result[k] + 1 & 255
    return result


def recalc_cleric_slots(char):
    book, r = spellbook(char), record(char)
    if book is None or _signed(r, 'levels')[CLERIC] <= 0: return
    slots = bytearray(book.get('spell_slots'))
    slots[:7] = _cleric_slots(r, tables())
    book.set('spell_slots', bytes(slots))


def _spell_slots(char, t):
    book = spellbook(char)
    if book is None:
        return
    r = record(char)
    levels, slots, known = _signed(r, 'levels'), bytearray(32), bytearray(book.get('known_spells'))
    def add(column, row, start, stop, columns=8, source=0):
        for level in range(start, stop + 1):
            for k in range(columns):
                at = column * 8 + k
                slots[at] = slots[at] + t.gained_slots(row, level, k + source + 1) & 255
    if levels[CLERIC] > 0:
        slots[:7] = _cleric_slots(r, t)
    if levels[PALADIN] > 8:
        add(0, 10, 9, levels[PALADIN], 4)
    if levels[KNIGHT] > 5 and r.get('knight_order') != 1:
        add(0, 4 if r.get('knight_order') == 2 else 5, 6, levels[KNIGHT], 7)
    for k in range(7):
        if slots[k]:
            for j in range(10):
                ident = t.u8('spellsByLevel', k * 10 + j)
                if not ident: break
                known[ident - 1] = 1
    if levels[RANGER] > 7:
        add(1, 6, 8, levels[RANGER], 4)
        add(3, 6, 8, levels[RANGER], 4, 4)
        for ident in range(114):
            if t.u8('spellTable', ident * 16) == 1 and slots[8 + t.u8('spellTable', ident * 16 + 1) - 1]:
                known[ident] = 1
    if levels[MAGE] > 0:
        slots[24] += 1
        add(3, 7 if r.get('robe_order') == 1 else 8, 2, levels[MAGE])
    book.set('spell_slots', bytes(slots))
    book.set('known_spells', bytes(known))


def recalc_saves(char):
    r, t = record(char), tables()
    levels = _signed(r, 'levels')
    saves = bytearray(min([20] + [t.save_needed(cls, level, k) for cls, level in enumerate(levels) if level > 0]) for k in range(5))
    con = _ability(r, 4)
    if _race(r) in DWARVES + (KENDER,) or 6 in _readied_special(char):
        saves[0] += _bands(con, ((4, 6, 1), (7, 10, 2), (11, 13, 3), (14, 17, 4), (18, 18, 5)))
    saves[0] += _bands(con, ((19, 20, 1), (21, 22, 2), (23, 24, 3), (25, 25, 4)))
    r.set('saves', bytes(saves))


def recalc_thief_skills(char):
    r, t = record(char), tables()
    level = _signed(r, 'levels')[THIEF]
    skills = bytearray(8)
    for k in range(8):
        value = t.u8('thiefSkillBase', (level - 1) * 8 + k) + t.s8('thiefSkillRaceAdjust', _race(r) * 8 + k)
        if k < 5: value += t.s8('thiefSkillDexterityAdjust', (_ability(r, 3) - 9) * 5 + k)
        skills[k] = value & 255
    r.set('thief_skills', bytes(skills))


def recalc_class_stats(char, slots=None):
    r, t = record(char), tables()
    levels = _signed(r, 'levels')
    attack = r.get('attacks')
    for cls in (FIGHTER, PALADIN, RANGER, KNIGHT):
        level = levels[cls]
        if level > (7 if cls == RANGER else 6):
            attack = 4 if level > 12 and cls != RANGER else 3
    best = max(t.u8('thac0Table', cls * 19 + level) for cls, level in enumerate(levels))
    if r.get('deity') == 3 or r.get('deity') == 6 and _race(r) in DWARVES: best += 1
    r.set('base_thac0', best & 255)
    r.set('attacks', attack)
    r.set('highest_level', max(0, *levels))
    r.set('class_mask', sum(t.u8('classMaskBits', cls) for cls, level in enumerate(levels) if level > 0) & 255)
    _spell_slots(char, t)
    recalc_saves(char)
    if levels[THIEF] > 0: recalc_thief_skills(char)
    for item in worn(char) if slots is None else slots:
        if item is not None and not t.base_item(item.get('type'))[USABLE_BY] & r.get('class_mask') and not item.get('cursed'):
            item.set('readied', 0)


def recalc(char, party_adjust=0):
    recalc_class_stats(char, recalc_stats(char, party_adjust))
    return char


def load_slot(path, slot='A'):
    root = Path(path)
    if not (root / ('SAVGAM%s.PTY' % slot)).is_file() and (root / 'SAVE').is_dir():
        root /= 'SAVE'
    return codec.load(root, slot)


def restore(state, snapshot):
    state.party = []
    for files in snapshot.members.values():
        char = character(bytes(files['GAM'][0]), [bytes(r) for r in files.get('JNK', ())],
                         [bytes(r) for r in files.get('EFF', ())],
                         spells=bytes(files['WIZ'][0]) if files.get('WIZ') else None)
        recalc(char, state.r1[0x372])
        record(char).set('order', len(state.party))
        state.party.append(char)
    return state.party


def write_character(char):
    return (bytes(char.b[:216]), bytes(char.b[216:]),
            b''.join(bytes(i) for i in char.items), b''.join(bytes(e) for e in char.effects))


def test():
    from sm.titles.ssb.state import State
    snapshot = load_slot(tables().assets.root)
    state = State()
    restore(state, snapshot)
    assert len(state.party) == 6
    for char, files in zip(state.party, snapshot.members.values()):
        r, original = record(char), files['GAM'][0]
        for field in ('base_thac0', 'saves', 'class_mask', 'highest_level', 'thief_skills'):
            assert r.get(field) == original.get(field), (field, r.get(field), original.get(field))
        before = state.hash()
        book = spellbook(char)
        if book is not None:
            book.data[0] ^= 1
            assert state.hash() != before
            book.data[0] ^= 1


def recalc_stats(char, party_adjust=0):
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
    load = load + sum(struct.unpack('<3H', record.get('money'))) & 0xFFFF
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

    record.set('move', movement(char, party_adjust) // 2)
    return slots
