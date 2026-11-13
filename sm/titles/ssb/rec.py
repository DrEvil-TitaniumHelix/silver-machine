from sm.titles.ssb import data as ssb_data

from sm.rec import Record as _Record

FIELDS = {
    'name': (0x000, 16), 'abilities': (0x010, 12),
    'str_exc_max': (0x01C, 1), 'str_exc': (0x01D, 1),
    'mem_spell': (0x01E, 75), 'rest_need': (0x069, 1),
    'base_thac0': (0x06A, 1), 'race': (0x06B, 1), 'class': (0x06C, 1),
    'cures_left': (0x06D, 1), 'age': (0x06E, 2), 'hp_max': (0x070, 1),
    'known_spell': (0x071, 117), 'fighter_lvl_eff': (0x0E6, 1),
    'size': (0x0E7, 1), 'save': (0x0E8, 5), 'base_move': (0x0ED, 1),
    'level_main': (0x0EE, 1), 'level_main_at_change': (0x0EF, 1),
    'levels_drained': (0x0F0, 1), 'hp_drained': (0x0F1, 1),
    'undead': (0x0F2, 1), 'thief_skill': (0x0F3, 8),
    'effects': (0x0FB, 4), 'npc_morale': (0x0FF, 1),
    'unknown_100': (0x100, 3), 'money': (0x103, 14),
    'level': (0x111, 7), 'old_level': (0x118, 7),
    'gender': (0x11F, 1), 'alignment': (0x120, 1),
    'attacks': (0x121, 1), 'attacks2': (0x122, 1),
    'base_damage': (0x123, 6), 'base_ac': (0x129, 1),
    'str_bonus': (0x12A, 1), 'id': (0x12B, 1), 'xp': (0x12C, 4),
    'class_mask': (0x130, 1), 'hp_rolled': (0x131, 1),
    'spell_slots': (0x132, 28), 'xp_value': (0x14E, 2),
    'xp_per_hp': (0x150, 1), 'head_pic': (0x151, 1),
    'body_pic': (0x152, 1), 'icon_head': (0x153, 1),
    'icon_body': (0x154, 1), 'unknown_155': (0x155, 1),
    'icon_size': (0x156, 1), 'icon_colours': (0x157, 6),
    'unknown_15d': (0x15D, 2), 'monster_flags': (0x15F, 1),
    'item_count': (0x160, 1), 'items': (0x161, 4),
    'readied': (0x165, 52), 'hands_used': (0x199, 1),
    'ac_item_bonus': (0x19A, 1), 'encumbrance': (0x19B, 2),
    'next': (0x19D, 4), 'combatant': (0x1A1, 4),
    'unknown_1a5': (0x1A5, 1), 'status': (0x1A6, 1),
    'active': (0x1A7, 1), 'side': (0x1A8, 1),
    'controlled': (0x1A9, 1), 'thac0': (0x1AA, 1),
    'ac': (0x1AB, 1), 'ac_rear': (0x1AC, 1),
    'attacks_left': (0x1AD, 2), 'damage': (0x1AF, 6),
    'hp': (0x1B5, 1), 'move': (0x1B6, 1),
}
for _i, _ability in enumerate(('str', 'int', 'wis', 'dex', 'con', 'cha')):
    FIELDS[_ability + '_max'] = (0x10 + 2 * _i, 1)
    FIELDS[_ability] = (0x11 + 2 * _i, 1)

ITEM_FIELDS = {
    'name': (0x00, 41), 'unknown_29': (0x29, 1),
    'pointer_2a': (0x2A, 4), 'type': (0x2E, 1),
    'unknown_2f': (0x2F, 3), 'plus': (0x32, 1), 'plus2': (0x33, 1),
    'readied': (0x34, 1), 'hidden': (0x35, 1), 'flags': (0x36, 1),
    'weight': (0x37, 2), 'count': (0x39, 1), 'value': (0x3A, 1),
    'powers': (0x3B, 4), 'next': (0x3F, 4),
}
EFFECT_FIELDS = {
    'type': (0, 1), 'duration': (1, 2), 'p3': (3, 1),
    'call_on_remove': (4, 1), 'next': (5, 4),
}




class Rec(_Record):
    SIZE, FIELDS = 439, FIELDS
    BLOCKS = frozenset(('unknown_15d', 'attacks_left'))

    def __init__(self, data=None):
        super().__init__(data)
        self.items, self.effects = [], []


class Item(_Record):
    SIZE, FIELDS = 67, ITEM_FIELDS
    BLOCKS = frozenset(('powers',))


class Effect(_Record):
    SIZE, FIELDS = 9, EFFECT_FIELDS


from sm import dax
sx = lambda v: (v & 0xFF ^ 0x80) - 0x80
sx16 = lambda v: (v & 0xFFFF ^ 0x8000) - 0x8000
rdw = lambda b, o: b[o] | b[o + 1] << 8
def wrw(b, o, v): b[o] = v & 0xFF; b[o + 1] = v >> 8 & 0xFF
def _T(it, col): return ssb_data.items_table()[it[0x2E] * 16 + col]
def has_effect(c, t): return any(e[0] == t for e in c.effects)

def dual(c):
    b = c.b
    return int(b[0x6B] == 6 and next((b[0x111 + i] for i in range(7) if b[0x111 + i]), 0) > b[0xEF])

def loaded_character(c, party_bonus=0):
    if c.b[0x114] > 0 or (c.b[0x101] == 3 and dual(c)): c.b[0x6D] = 1
    recalc_character(c, party_bonus); recalc_levels(c)

def readied(c):
    r = [None] * 13
    for it in c.items:
        if not it[0x34]: continue
        sl = _T(it, 0)
        if sl <= 8: r[sl] = it
        elif sl == 9:
            if r[9] is None: r[9] = it
            elif r[10] is None: r[10] = it
        if it[0x2E] == 0x1E: r[11] = it
        if it[0x2E] == 0x0C: r[12] = it
    return r

def recalc_levels(c):
    b, D = c.b, ssb_data.stexe()
    b[0x6A] = 0
    for i in range(7):
        lv = b[0x111 + i]; t = D[0x4C0C + 19 * i + lv]
        if t > b[0x6A]: b[0x6A] = t
        if sx(b[0xEE]) < sx(lv): b[0xEE] = lv
        if i in (2, 3):
            if sx(lv) > 6: b[0x121] = 3
            if sx(lv) > 12: b[0x121] = 4
        elif i == 4:
            if sx(lv) > 7: b[0x121] = 3
            if sx(lv) > 14: b[0x121] = 4
    rebuild_known_spells(c); recalc_saves(c)
    if sx(b[0x117]) > 0: recalc_thief_skills(c)
    b[0x130] = 0
    for i in range(7):
        if sx(b[0x111 + i]) > 0 or (sx(b[0x118 + i]) > 0 and sx(b[0x118 + i]) < sx(b[0xEE])): b[0x130] = (b[0x130] + D[0x4C92 + i]) & 0xFF
    for it in readied(c):
        if it is not None and not (_T(it, 0xD) & b[0x130]) and it[0x36] == 0: it[0x34] = 0
    if dual(c):
        for i in range(7):
            lv = b[0x118 + i]
            if i in (2, 3):
                if sx(lv) >= 13: b[0x121] = 4
                elif sx(lv) >= 7: b[0x121] = 3
            elif i == 4:
                if sx(lv) >= 15: b[0x121] = 4
                elif sx(lv) >= 8: b[0x121] = 3
            elif i == 6 and sx(lv) > 0: recalc_thief_skills(c)
            t = D[0x4C0C + 19 * i + lv]
            if t > b[0x6A]: b[0x6A] = t

def rebuild_known_spells(c):
    b, D = c.b, ssb_data.stexe(); dl = dual(c)
    b[0x132:0x14E] = bytes(0x1C)
    for i in range(7):
        lv = b[0x118 + i] if dl and b[0x118 + i] else b[0x111 + i]
        if sx(lv) <= 0: continue
        if i == 0:
            cleric_slots(c)
            for sid in range(1, 0x76):
                sp = D[0x449D + 16 * sid:0x449D + 16 * sid + 2]
                if sp[0] == 0 and b[0x131 + sp[1]] > 0: b[0x70 + sid] = 1
        elif i == 3 and sx(lv) > 8:
            for L in range(9, lv + 1):
                for k in range(1, 8): b[0x131 + k] = (b[0x131 + k] + D[0x52D2 + 7 * L + k]) & 0xFF
            for sid in range(1, 0x76):
                sp = D[0x449D + 16 * sid:0x449D + 16 * sid + 2]
                if sp[0] == 0 and b[0x131 + sp[1]] > 0: b[0x70 + sid] = 1
        elif i == 4 and sx(lv) > 7:
            for L in range(8, lv + 1):
                for k in range(1, 4): b[0x138 + k] = (b[0x138 + k] + D[0x538D + 7 * L + k]) & 0xFF
                for k in range(4, 6): b[0x146 + k - 3] = (b[0x146 + k - 3] + D[0x538D + 7 * L + k]) & 0xFF
            for sid in range(1, 0x76):
                sp = D[0x449D + 16 * sid:0x449D + 16 * sid + 2]
                if (sp[0] == 1 and b[0x138 + sp[1]] > 0) or (sp[0] == 3 and b[0x146 + sp[1]] > 0): b[0x70 + sid] = 1
        elif i == 5:
            b[0x147] = (b[0x147] + 1) & 0xFF
            for L in range(2, lv + 1):
                for k in range(1, 8): b[0x146 + k] = (b[0x146 + k] + D[0x5448 + 7 * L + k]) & 0xFF
            if b[0x13] < 12: b[0x14C] = 0
            if b[0x13] < 14: b[0x14D] = 0
    for it in c.items:
        if it[0x3E] == 0x81 and it[0x34]: b[0x14B] = (b[0x14B] * 2) & 0xFF

def cleric_slots(c):
    b, D = c.b, ssb_data.stexe(); lv = (b[0x111] + dual(c) * b[0x118]) & 0xFF
    if sx(lv) <= 0: return
    b[0x133:0x139] = bytes(6); b[0x132] = 1
    for L in range(2, lv + 1):
        for k in range(1, 8): b[0x131 + k] = (b[0x131 + k] + D[0x50A1 + 7 * L + k]) & 0xFF
    w = b[0x15]
    for lim, o in ((12, 0x132), (13, 0x132), (14, 0x133), (15, 0x133), (16, 0x134), (17, 0x135)):
        if w > lim and b[o] > 0: b[o] = (b[o] + 1) & 0xFF
    if w < 17: b[0x137] = 0
    if w < 18: b[0x138] = 0

def recalc_saves(c):
    b, D = c.b, ssb_data.stexe()
    sp6 = any(it[0x34] and it[0x3E] > 0x80 and it[0x3E] & 0x7F == 6 for it in c.items)
    for s in range(5):
        v = 20
        for i in range(7):
            lv = b[0x111 + i]
            if sx(lv) > 0: v = min(v, D[0x5592 + 90 * i + 5 * lv + s])
        if sx(b[0x117]) > sx(b[0x11E]): v = min(v, D[0x5592 + 540 + 5 * b[0x11E] + s])
        if s == 0:
            con = b[0x19]
            if sp6: v += 1 if 4 <= con <= 6 else 2 if 7 <= con <= 10 else 3 if 11 <= con <= 13 else 4 if 14 <= con <= 17 else 5 if con == 18 else 0
            v += 1 if con in (19, 20) else 2 if con in (21, 22) else 3 if con in (23, 24) else 4 if con == 25 else 0
        b[0xE8 + s] = v & 0xFF

def recalc_thief_skills(c):
    b, D = c.b, ssb_data.stexe(); lv = (b[0x117] + dual(c) * b[0x11E]) & 0xFF
    for s in range(1, 9):
        r, base = sx(D[0x4D3D + 8 * b[0x6B] + s]), D[0x4CAD + 8 * lv + s]
        if r < 0 and base < -r: b[0xF2 + s] = 0; continue
        v = base + r
        if s <= 5: v += sx(D[0x4D48 + 5 * b[0x17] + s])
        b[0xF2 + s] = v & 0xFF

def dex_ac(c):
    d = c.b[0x17]
    return -4 if 1 <= d <= 3 else d - 7 if 4 <= d <= 6 else d - 14 if 15 <= d <= 18 else 4 if d in (19, 20) else 5 if 21 <= d <= 23 else 6 if d in (24, 25) else 0
def dex_hit(c):
    d = c.b[0x17]
    return -4 if d <= 2 else d - 6 if 3 <= d <= 5 else d - 15 if 16 <= d <= 18 else 3 if d in (19, 20) else 4 if 21 <= d <= 23 else 5 if d in (24, 25) else 0
def str_index(c):
    s, e = c.b[0x11], c.b[0x1C]
    if s <= 0x11: return s
    if s == 0x12: return 0x12 if e == 0 else 0x13 if e <= 0x32 else 0x14 if e <= 0x4B else 0x15 if e <= 0x5A else 0x16 if e <= 0x63 else 0x17 if e == 0x64 else 0
    return s + 5 if 0x13 <= s <= 0x19 else 0
def str_hit(c):
    if not c.b[0x12A]: return 0
    i = str_index(c)
    return -3 if 1 <= i <= 3 else -2 if i in (4, 5) else -1 if i in (6, 7) else 1 if 0x11 <= i <= 0x13 else 2 if 0x14 <= i <= 0x16 else 3 if 0x17 <= i <= 0x19 else 4 if i in (0x1A, 0x1B) else i - 0x17 if 0x1C <= i <= 0x1E else 0
def str_dmg(c):
    if not c.b[0x12A]: return 0
    i = str_index(c)
    return -2 if i in (1, 2) else -1 if 3 <= i <= 5 else 1 if i == 0x10 else i - 0x10 if 0x11 <= i <= 0x13 else i - 0x11 if 0x14 <= i <= 0x1D else 0xE if i == 0x1E else 0
def carry(c):
    i = str_index(c)
    return (-350 if 1 <= i <= 3 else -250 if i in (4, 5) else -150 if i in (6, 7) else 100 if i in (0xC, 0xD) else 200 if i in (0xE, 0xF) else 350 if i == 0x10
            else (i - 0x11) * 250 + 500 if 0x11 <= i <= 0x15 else (i - 0x16) * 1000 + 2000 if 0x16 <= i <= 0x1A else 7500 if i == 0x1B
            else (i - 0x1C) * 3000 + 9000 if 0x1C <= i <= 0x1E else 0)

def compute_move(c, party_bonus=0):
    b = c.b; b[0x1B6] = b[0xED]
    for it in c.items:
        if it[0x34] and _T(it, 0) == 2:
            w = rdw(it, 0x37); b[0x1B6] = b[0xED] if w <= 0x96 else 9 if w <= 0x18F else 6
            if it[0x32] and b[0x1B6] <= 9: b[0x1B6] = (b[0x1B6] + 3) & 0xFF
    over = max(sx16(rdw(b, 0x19B) - carry(c)), 0)
    m = b[0x1B6] if over <= 0x200 else 9 if over <= 0x300 else 6 if over <= 0x400 else 3
    if m < b[0x1B6]: b[0x1B6] = m
    if has_effect(c, 0x27): b[0x1B6] = (b[0x1B6] * 2) & 0xFF
    if has_effect(c, 0x2A): b[0x1B6] //= 2
    if has_effect(c, 0x4A): b[0x1B6] = (b[0x1B6] * 2) & 0xFF
    r = b[0x1B6]
    if b[0x1A8] == 0: r = (r + party_bonus) & 0xFF
    return (r * 2) & 0xFF

def _weapon(c, sl):
    b, w = c.b, sl[0]
    if w is None: return
    f = _T(w, 0xE); b[0x1AA] = b[0x6A]
    if f & 2: b[0x1AA] = (b[0x1AA] + dex_hit(c)) & 0xFF
    b[0x1B3] = _T(w, 0xB)
    if f & 4: b[0x1AA] = (b[0x1AA] + str_hit(c)) & 0xFF; b[0x1B3] = (sx(b[0x1B3]) + str_dmg(c)) & 0xFF
    plus = w[0x32]
    if f > 0x7F and sl[12] is not None: plus = (sx(plus) + sx(sl[12][0x32])) & 0xFF
    if f & 1 and sl[11] is not None: plus = (sx(plus) + sx(sl[11][0x32])) & 0xFF
    b[0x1B3] = (sx(b[0x1B3]) + sx(plus)) & 0xFF
    if 0x16 <= w[0x2E] <= 0x1A or w[0x2E] in (0x12, 0x13): plus = (plus + 1) & 0xFF
    b[0x1AA] = (b[0x1AA] + sx(plus)) & 0xFF
    b[0x1AF] = _T(w, 9); b[0x1B1] = _T(w, 0xA)

def _item_bonus(c, it, loc):
    b = c.b; bc = _T(it, 6); flag = 0
    if bc <= 0x7F: return 0
    bc &= 0x7F; cls = _T(it, 0); plus = sx(it[0x32])
    if cls == 1: loc[1] = (plus + bc) & 0xFF
    elif bc == 0:
        if cls == 9:
            if plus > sx(loc[3]): loc[3] = it[0x32]
        else: loc[2] = (plus + sx(loc[2])) & 0xFF
        b[0x19A] = (sx(b[0x19A]) + sx(it[0x33])) & 0xFF
    elif plus + bc > sx(loc[4]):
        loc[4] = (plus + bc) & 0xFF
        if plus > 0 and cls == 2: flag = 1
    return flag

def recalc_character(c, party_bonus=0):
    b = c.b; b[0x160] = 0; b[0x199] = 0; enc = 0
    for it in c.items:
        b[0x160] = (b[0x160] + 1) & 0xFF
        w = rdw(it, 0x37)
        if it[0x39]: w = (it[0x39] * w) & 0xFFFF
        enc = (enc + w) & 0xFFFF
        if it[0x34]: b[0x199] = (b[0x199] + _T(it, 1)) & 0xFF
    for k in range(7): enc = (enc + rdw(b, 0x103 + 2 * k)) & 0xFFFF
    wrw(b, 0x19B, enc)
    b[0x1AF:0x1B5] = b[0x123:0x129]
    loc = [0] * 5; flag = 0
    b[0x19A] = 0; b[0x1AB] = b[0x129]; b[0x1AA] = b[0x6A]
    loc[0] = dex_ac(c) & 0xFF
    sl = readied(c)
    if sl[0] is None: b[0x1AA] = (b[0x1AA] + str_hit(c)) & 0xFF; b[0x1B3] = (sx(b[0x1B3]) + str_dmg(c)) & 0xFF
    _weapon(c, sl)
    for it in c.items:
        if it[0x34]: flag |= _item_bonus(c, it, loc)
    if flag: loc[3] = 0
    b[0x1B6] = compute_move(c, party_bonus) // 2
    if sx(loc[4]) < b[0x1AB]: loc[4] = b[0x1AB]
    b[0x1AB] = sum(sx(v) for v in loc) & 0xFF
    b[0x1AC] = (sx(loc[4]) + sx(loc[2]) + sx(loc[3]) - 2) & 0xFF
    multi = sx(b[0x113]) > 0 or sx(b[0x114]) > 0 or sx(b[0x115]) > 0 or (sx(b[0x11A]) > 0 and dual(c))
    if multi and b[0x6B] not in (0, 7): b[0xE6] = max(b[0x113], b[0x115], b[0x114])
    else: b[0xE6] = 1

def oracle(slot, party_bonus=None):
    from sm.titles.ssb import save
    from sm.titles.ssb.state import Char
    st = save.load(slot=slot); bonus = st['r1'][0x372] if party_bonus is None else party_bonus
    out = []
    for r in st['party']:
        c = Char(bytes(r), [bytes(i) for i in r.items], [bytes(e) for e in r.effects]); before, items = bytes(c.b), [bytes(i) for i in c.items]
        for o, n in ((0xE6, 1), (0xE8, 5), (0xEE, 1), (0x130, 1), (0x132, 28), (0x160, 1), (0x199, 4), (0x1AA, 3), (0x1AF, 6), (0x1B6, 1)) +                     (((0xF3, 8),) if c.b[0x117] else ()):
            c.b[o:o + n] = bytes(n)
        recalc_character(c, bonus); recalc_levels(c)
        out.append((before[1:1 + before[0]].decode('latin1'), [o for o in range(439) if c.b[o] != before[o]], [bytes(i) for i in c.items] != items))
    return out


def maximize_party(s, equipment=None):
    from types import SimpleNamespace
    from sm.titles.ssb.units import creation, shops, combat
    game = SimpleNamespace(s=s); ds = ssb_data.stexe()
    catalog = {(area, rid, j // 63): bytearray(raw[j:j + 63] + bytes(4)) for area in (1, 2, 3)
               for rid, raw in dax.load('ITEM%d' % area, d=ssb_data.SECRET).items() for j in range(0, len(raw), 63)}
    stock = [it for it in catalog.values() if len(it) == 67 and not it[0x36] and sx(it[0x32]) >= 0]
    for c in s.party:
        if bytes(c.b[1:1 + c.b[0]]) == b'EPONA': c.b[0x6C] = 5; c.b[0x111:0x118] = bytes([0, 0, 0, 0, 0, 1, 0]); c.b[0x118:0x11F] = bytes(7); c.b[0x121] = 2
    for member, c in enumerate(s.party):
        b = c.b; classes = [i for i, lv in enumerate(b[0x111:0x118]) if lv]
        for a in range(6): b[0x10 + 2*a] = b[0x11 + 2*a] = min(18, creation.ability_limits(c, a)[1])
        b[0x1C] = b[0x1D] = min(100, ds[0x4DA1 + b[0x6B]*16 + b[0x11F]]) if any(i in (2, 3, 4) for i in classes) and b[0x11] == 18 else 0
        caps = [0] * 7
        for i in classes:
            b[0x111 + i] = 1
            while not creation.capped(c, i) and creation.xp_for(i, b[0x111 + i] + 1) > 0:
                b[0x111 + i] += 1
            caps[i] = b[0x111 + i]
        b[0x12C:0x130] = max(creation.xp_for(i, caps[i]) for i in classes).to_bytes(4, 'little')
        b[0x70] = b[0x131] = b[0x1B5] = 0
        b[0xF0] = b[0xF1] = 0
        for level in range(1, max(caps) + 1):
            b[0x111:0x118] = bytes(min(level, cap) for cap in caps)
            mask = sum(ds[0x4C99 + i] for i in classes if caps[i] >= level)
            creation.level_hp(SimpleNamespace(random=lambda n: n - 1), c, mask, len(classes))
        c.items = []; b[0xEE] = b[0x199] = 0
        recalc_levels(c); recalc_character(c, s.r1[0x372])
        eligible = [it for it in stock if _T(it, 13) & b[0x130] and
                    (it[0x3E] != 0x84 or it[0x3D] & 15 == b[0x120])]
        shields = [it for it in eligible if _T(it, 0) == 1]
        weapons = [it for it in eligible if _T(it, 0) == 0 and not _T(it, 14) & 8
                   and _T(it, 1) <= (1 if shields else 2)]
        armour = [it for it in eligible if _T(it, 0) == 2]
        gear = []
        if weapons: gear.append(max(weapons, key=lambda it: (combat.Combat.weapon_score(None, c, it), -rdw(it, 0x37))))
        if armour: gear.append(max(armour, key=lambda it: ((_T(it, 6) & 127) + sx(it[0x32]), -rdw(it, 0x37))))
        if shields: gear.append(max(shields, key=lambda it: (sx(it[0x32]), -rdw(it, 0x37))))
        if equipment is not None: gear = [catalog[key] for key in equipment[member]]
        for source in gear:
            it = bytearray(source); it[0x2A:0x2E] = bytes(4); it[0x3F:0x43] = bytes(4); it[0x34] = 0
            c.items.append(it)
            if not shops.ready(game, c, it): raise ValueError('max party equipment cannot be readied')
        loaded_character(c, s.r1[0x372]); recalc_character(c, s.r1[0x372])
        for slot_class, n in (() if equipment is not None else ((3, 1), (5, 1), (7, 1), (8, 1), (9, 2), (10, 1), (2, 1))):
            for _ in range(n):
                tried = set()
                for it0 in sorted((it for it in eligible if _T(it, 0) == slot_class), key=lambda it: -sx(it[0x32])):
                    if bytes(it0) in tried: continue
                    tried.add(bytes(it0)); before = b[0x1AB]
                    it = bytearray(it0); it[0x2A:0x2E] = bytes(4); it[0x3F:0x43] = bytes(4); it[0x34] = 0; c.items.append(it)
                    if shops.ready(game, c, it):
                        loaded_character(c, s.r1[0x372]); recalc_character(c, s.r1[0x372])
                        if b[0x1AB] > before: break
                        shops.ready(game, c, it) if it[0x34] else None
                    c.items.remove(it); loaded_character(c, s.r1[0x372]); recalc_character(c, s.r1[0x372])
        expert_spells(c)
    return s


def max_party(write=True, root=None):
    from sm.titles.ssb import save
    from sm.titles.ssb.state import State
    from sm.titles.ssb.ui import screen
    data = save.load(slot='A'); s = State(); save.restore(s, data)
    maximize_party(s)
    data['slot'] = 'M'; data['names'] = ['CHRDATM%d' % (i + 1) for i in range(len(s.party))]
    data['party'] = []
    for c in s.party:
        r = Rec(bytes(c.b)); r.items = [Item(bytes(it)) for it in c.items]; r.effects = [Effect(bytes(e)) for e in c.effects]
        data['party'].append(r)
    if write: screen.write_slot_files(save.dump(data), 'M', root or screen.SAVE_ROOT)
    return data


MAX_PARTY_RECIPE = (
    ('Guy de Valois ', 6, 3, 0, 0, (5, 24, 2), ((3, 98, 1), (2, 55, 1), (3, 81, 1), (1, 20, 0))),
    ('PAINE',         6, 4, 0, 0, (5, 1, 2),  ((3, 98, 1), (2, 55, 1), (3, 81, 1), (1, 20, 0))),
    ('EPONA',         6, 5, 1, 1, (9, 24, 2), ((2, 68, 1), (1, 20, 0), (2, 52, 0), (2, 67, 0))),
    ('MALACHITE',     3, 14, 3, 0, (0, 24, 1), ((3, 98, 1), (2, 55, 1), (3, 81, 1), (1, 20, 0))),
    ('DOMINIC',       6, 0, 0, 0, (5, 23, 2), ((1, 99, 34), (2, 55, 1), (3, 81, 1), (1, 20, 0))),
    ('MORGAINE',      6, 5, 4, 1, (9, 29, 2), ((2, 68, 1), (1, 20, 0), (2, 52, 0), (2, 67, 0))),
)


def seed_max_party(root=None):
    from sm.titles.ssb.host import Game
    from sm.titles.ssb.units import creation
    from sm.titles.ssb.ui import screen
    root = root if root is not None else screen.SAVE_ROOT
    target = screen.slot_directory('A', root)
    if target.exists() and (not target.is_dir() or any(target.iterdir())): return False
    choices = {}
    def choose(kind, options, game, **info):
        value = choices[kind]
        return options.index(value) if options is not None else value
    game = Game(choose, slot=None, engines=True, directory=root)
    for name, race, cls, alignment, gender, icon, gear in MAX_PARTY_RECIPE:
        choices.update(CREATE_RACE=race, CREATE_CLASS=cls, CREATE_ALIGNMENT=alignment, CREATE_GENDER=gender,
                       CREATE_NAME=name, CREATE_ROLL='keep', CREATE_ICON='keep', CREATE_SAVE='cancel')
        c = creation.create(game)
        identity = name.encode('latin1'); c.b[:16] = bytes([len(identity)]) + identity + bytes(15 - len(identity))
        c.b[0x153], c.b[0x154], c.b[0x156] = icon
        c.b[0x155] = len(game.s.party)
        game.s.party.append(c)
    game.s.r1[0x33E] = len(game.s.party)
    maximize_party(game.s, [row[-1] for row in MAX_PARTY_RECIPE])
    game.s.dataset = 2
    files = screen.snapshot(game, 'A')
    if target.exists() and any(target.iterdir()): return False
    screen.write_slot_files(files, 'A', root)
    return True


LOADOUT = {0: {1: (3, 1), 2: (25, 23), 3: (42, 41), 4: (58,), 5: (74, 71, 73, 75), 6: (36,), 7: ()},
           3: {1: (15, 13), 2: (34,), 3: (48, 47, 51, 46, 49), 4: (88, 87, 85), 5: (91, 92, 94), 6: (112, 113, 110), 7: (115, 117)}}

def expert_spells(c):
    b, D = c.b, ssb_data.stexe(); mem = []
    for cls, base in ((0, 0x131), (3, 0x146)):
        for sid in range(1, 0x76):
            if D[0x449D + 16 * sid] == cls and b[base + D[0x449E + 16 * sid]] > 0: b[0x70 + sid] = 1
        for L in range(1, 8):
            n = b[base + L]
            if not n: continue
            pool = [x for x in LOADOUT[cls][L] if b[0x70 + x]] or [x for x in range(1, 0x76) if D[0x449D + 16 * x] == cls and D[0x449E + 16 * x] == L and b[0x70 + x]]
            mem += [pool[k % len(pool)] for k in range(n)] if pool else []
    mem = mem[:75]; b[0x1E:0x69] = bytes(mem + [0] * (75 - len(mem)))

def test_max_party():
    from unittest.mock import patch
    from sm.titles.ssb import host, save
    before = save.load(); data = max_party(write=False); files = save.dump(data)
    data = save._load(files.get, 'M')
    assert [list(r.data[0x111:0x118]) for r in data['party']] == [
        [0, 0, 0, 15, 0, 0, 0], [0, 0, 0, 0, 15, 0, 0], [0, 0, 0, 0, 0, 15, 0],
        [0, 0, 9, 0, 0, 0, 18], [15, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 15, 0]]
    assert [r.data[0x70] for r in data['party']] == [144, 142, 70, 111, 112, 70]
    for a, b in zip(before['party'], data['party']):
        assert all(a.get(k) == b.get(k) for k in ('name', 'race', 'alignment'))
        assert a.get('class') == b.get('class') or b.get('name') == a.get('name') and b.get('class') == 5
    with patch.object(save, 'load', return_value=data):
        session = host.Session(slot='M', engines=True)
        try:
            for r, c in zip(data['party'], session.game.s.party):
                assert bytes(r) == bytes(c.b), ('max party load changed record', r.get('name'))
                assert [bytes(it) for it in r.items] == [bytes(it) for it in c.items]
                before = bytes(c.b); loaded_character(c, session.game.s.r1[0x372])
                assert before == bytes(c.b), 'max party recalculation is not stable'
                assert c.b[0x199] <= 2 and all(_T(it, 13) & c.b[0x130] for it in c.items)
        finally: session.close()


def test():
    _test_layout()
    test_dual_thief()
    test_cleric_wisdom()
    test_max_party()
    bad = [(s, n, ['%03X' % o for o in d], i) for s in 'AB' for n, d, i in oracle(s) if d or i]
    assert not bad, 'recalc oracle: %s' % bad

def test_dual_thief():
    from sm.titles.ssb.state import Char
    c = Char(bytes(439)); b = c.b; b[0x6B], b[0x11A], b[0xEF], b[0x117], b[0x121] = 6, 5, 5, 5, 2
    assert not dual(c)
    b[0x117] = 6; assert dual(c)
    recalc_levels(c); D = ssb_data.stexe()
    assert b[0x6A] == max(D[0x4C0C + 19 * 6 + 6], D[0x4C0C + 19 * 2 + 5]), 'former Fighter THAC0 counts'
    b[0x11A] = 7; recalc_levels(c); assert b[0x121] == 3, 'former Fighter 7 gives 3/2 attacks'
    b[0x6B] = 3; assert not dual(c)

def test_cleric_wisdom():
    from sm.titles.ssb.state import Char
    c = Char(bytes(439)); c.b[0x111] = 18; c.b[0x15] = 12; cleric_slots(c)
    base = list(c.b[0x132:0x137])
    for wisdom, bonus in ((12, (0, 0, 0, 0, 0)), (13, (1, 0, 0, 0, 0)), (14, (2, 0, 0, 0, 0)),
                          (15, (2, 1, 0, 0, 0)), (16, (2, 2, 0, 0, 0)), (17, (2, 2, 1, 0, 0)), (18, (2, 2, 1, 1, 0))):
        c.b[0x15] = wisdom; cleric_slots(c)
        assert list(c.b[0x132:0x137]) == [a + b for a, b in zip(base, bonus)]
        assert bool(c.b[0x137]) == (wisdom >= 17) and bool(c.b[0x138]) == (wisdom >= 18)
    expected = bytes(c.b[0x132:0x139])
    c.b[0x111], c.b[0x118], c.b[0x113], c.b[0xEF], c.b[0x6B] = 0, 18, 19, 18, 6
    cleric_slots(c); assert bytes(c.b[0x132:0x139]) == expected, 'active former cleric contributes its level'
    c.b[0x113] = 18; c.b[0x132:0x139] = bytes([99] * 7)
    cleric_slots(c); assert list(c.b[0x132:0x139]) == [99] * 7, 'inactive former cleric has no effective level'
    c.b[0x111], c.b[0x118], c.b[0x113] = 1, 0, 0; cleric_slots(c)
    assert list(c.b[0x132:0x139]) == [3, 0, 0, 0, 0, 0, 0], 'WIS must not grant an unavailable spell level'


def _test_layout():
    import random
    rng = random.Random(0x4396709)
    for cls in (Rec, Item, Effect):
        fields = list(cls.FIELDS)
        covered = set()
        for off, size in cls.FIELDS.values():
            assert 0 <= off < off + size <= cls.SIZE
            covered.update(range(off, off + size))
        assert covered == set(range(cls.SIZE)), cls.__name__
        rec = cls(rng.randbytes(cls.SIZE))
        for name in fields + rng.choices(fields, k=200):
            off, size = cls.FIELDS[name]
            before = bytes(rec)
            raw = rng.randbytes(size)
            value = raw if isinstance(rec.get(name), bytes) else int.from_bytes(raw, 'little')
            rec.set(name, value)
            assert rec.get(name) == cls(bytes(rec)).get(name) == value, (cls.__name__, name, off)
            assert bytes(rec) == before[:off] + raw + before[off + size:], (name, off)
        for size in (0, cls.SIZE - 1, cls.SIZE + 1):
            try: cls(bytes(size))
            except ValueError: pass
            else: raise AssertionError((cls.__name__, 'accepted size', size))
        scalar = next(n for n, (_, size) in cls.FIELDS.items() if size == 1)
        before = bytes(rec)
        for value in (-1, 256):
            try: rec.set(scalar, value)
            except OverflowError: pass
            else: raise AssertionError((scalar, 'accepted out-of-range value'))
        assert bytes(rec) == before
        try: rec.get('creature_type')
        except KeyError: pass
        else: raise AssertionError('unknown field accepted')
    rec = Rec()
    rec.set('xp', -1234, signed=True)
    assert rec.get('xp', signed=True) == -1234
    before = bytes(rec)
    try: rec.set('name', b'bad size')
    except ValueError: pass
    else: raise AssertionError('short name accepted')
    assert bytes(rec) == before
