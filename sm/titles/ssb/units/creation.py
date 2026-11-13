from sm.titles.ssb import data as ssb_data
import struct
from pathlib import Path
from sm import dax; from sm.titles.ssb import rec; from sm.titles.ssb import save
from sm.titles.ssb.state import Char
from sm.titles.ssb.units.shops import choose, pick_member, name, view, message

MULTI = {8: (0, 2), 9: (0, 2, 5), 10: (0, 4), 11: (0, 5), 12: (0, 6),
         13: (2, 5), 14: (2, 6), 15: (2, 5, 6), 16: (5, 6)}
AUTO_SPELLS = {6: (12, 15, 30, 3, 34, 47, 51, 54), 7: (14, 16, 29, 35, 45, 48, 81),
               8: (10, 9, 32, 55, 85), 9: (50, 52, 82, 88, 94)}


def image(c):
    return bytes(c.b), tuple(bytes(i) for i in c.items), tuple(bytes(e) for e in c.effects)


def from_image(data):
    return Char(*data)


def table_list(base, stride, key):
    d = ssb_data.stexe(); o = base + stride * key
    return list(d[o + 1:o + 1 + d[o]])


def xp_for(cls, level):
    if not 0 <= cls < 7 or not 1 <= level <= 40: return -1
    return struct.unpack_from('<i', ssb_data.stexe(), 0x5064 + cls * 0xBB + level * 4)[0]


def con_bonus(c, cls, high=True):
    v = c.b[0x19]
    if not high:
        return -2 if v == 3 else -1 if 4 <= v <= 6 else 1 if v == 15 else 2 if v == 16 else v - 14 if 17 <= v <= 19 and cls in (2, 3, 4) else 2 if 17 <= v <= 19 else 0
    bonus = rec.sx(ssb_data.stexe()[0x5052 + v])
    if cls in (2, 3, 4): bonus += 1 if v == 17 else 2 if v == 18 else 3 if v in (19, 20) else 4 if 21 <= v <= 23 else 5 if v in (24, 25) else 0
    return bonus


def min_hp(c):
    levels = c.b[0x111:0x118]; n = sum(v > 0 for v in levels)
    if not n: return 1
    total = (sum(levels) + bool(levels[4])) & 255
    bonus = rec.sx(sum(con_bonus(c, i) for i, lv in enumerate(levels) if lv))
    return 1 if bonus < 0 and total <= n + abs(bonus) else int((total + bonus) / n) & 255


def max_hp(c):
    d = ssb_data.stexe(); total = n = 0
    for i, lv in enumerate(c.b[0x111:0x118]):
        if not lv: continue
        n += 1; cap = d[0x4CA9 + i]; b = con_bonus(c, i, False)
        if lv < cap: total = (total + (lv + (i == 4)) * (b + (8, 8, 10, 10, 8, 4, 6)[i])) & 255
        else:
            k = lv - cap + 1; total = (72 + 2 * k, 112, 88 + 2 * k, 88 + 2 * k, 88 + 2 * k, 44 + k, 60 + 2 * k)[i] & 255
    return total // n if n else 1


def roll(s, dice, sides):
    return sum(s.random(sides) + 1 for _ in range(dice)) & 255


def level_hp(s, c, mask, count):
    b, d = c.b, ssb_data.stexe(); total = bonus = 0
    for i, lv in enumerate(b[0x111:0x118]):
        if not lv or not d[0x4C99 + i] & mask: continue
        if lv < d[0x4CA9 + i]:
            dice = 1 if lv > 1 else d[0x09B0 + i]; sides = d[0x09B7 + i]
            total = (total + max(roll(s, dice, sides), roll(s, dice, sides))) & 255
            bonus = (bonus + dice * con_bonus(c, i)) & 255
        elif i in (2, 3): total = 3
        elif i in (0, 4, 6): total = 2
        elif i == 5: total = 1
    gain = max(1, total // count); wounds = (b[0x70] - b[0x1B5]) & 255
    b[0x131] = (b[0x131] + gain) & 255
    b[0x70] = (b[0x70] + gain + bonus // count) & 255; b[0x1B5] = (b[0x70] - wounds) & 255


def capped(c, cls):
    b = c.b; race, lv, st, iq = b[0x6B], b[0x111 + cls], b[0x11], b[0x13]
    if race == 3: return (cls == 2 and (lv == 9 or lv == 8 and st == 17 or lv == 7 and st < 17)) or cls == 0 and lv >= 8
    if race == 1: return (cls == 2 and (lv == 7 or lv == 6 and st == 17 or lv == 5 and st < 17)) or (cls == 5 and (lv == 11 or lv == 10 and iq == 17 or lv == 9 and iq < 17)) or cls == 0 and lv >= 7
    if race == 4: return (cls == 2 and (lv == 6 or lv == 5 and st < 18)) or cls == 0 and lv >= 7
    if race == 2: return cls == 0 and lv == 5 or cls in (2, 4) and (lv == 8 or lv == 7 and st == 17 or lv == 6 and st < 17) or cls == 5 and (lv == 8 or lv == 7 and iq == 17 or lv == 6 and iq < 17)
    if race == 5: return cls == 2 and (lv == 6 or lv == 5 and st == 17 or lv == 4 and st < 17)
    return False


def train(game, c=None, auto=False, free=False):
    from sm.titles.ssb.units import magic
    s = game.s; c = c if c is not None else pick_member(game)
    if c is None: return False
    if c.b[0x1A6] and not free:
        message(game, 'we only train conscious people', bottom=True); return False
    b, d = c.b, ssb_data.stexe(); xp = struct.unpack_from('<i', b, 0x12C)[0]
    have = can = cap = last_level = 0
    for i, lv in enumerate(b[0x111:0x118]):
        if rec.sx(lv) <= 0: continue
        last_level = lv; have |= d[0x4C99 + i]
        if capped(c, i): continue
        need = xp_for(i, lv + 1)
        if need <= 0 or xp < need and not free: continue
        if free: xp = max(xp, need)
        can |= d[0x4C99 + i]; nxt = xp_for(i, lv + 2)
        if 0 < nxt <= xp and nxt > cap: cap = nxt - 1
    if not auto:
        best = max((i for i in range(7) if can & d[0x4C99 + i]), key=lambda i: xp_for(i, last_level + 1), default=None)
        if best is not None:
            nxt = xp_for(best, last_level + 2)
            if 0 < nxt <= xp and nxt > cap: cap = nxt - 1
        if cap: xp = cap
    struct.pack_into('<i', b, 0x12C, xp)
    hall = 255 if auto or free else s.r1[0x2A8]; mask = can & hall
    if not have & hall and not auto and not free:
        message(game, "We don't train that class here", bottom=True); return False
    if not mask:
        s.g['8DBB'] = 1
        if not auto: message(game, 'Not Enough Experience', bottom=True)
        return False
    if not auto:
        classes = [i for i in range(7) if b[0x111 + i] and mask & d[0x4C99 + i]]
        levels = []
        for i in classes:
            offset = 0x0B8B + 27 * i
            label = d[offset + 1:offset + 1 + d[offset]].decode('latin1')
            levels.append('a level %d %s' % (b[0x111 + i] + 1, label))
        if choose(game, 'CREATE_TRAIN', ['train', 'cancel'], classes=classes, cost=0,
                  character=name(c), levels=levels, level_text='\n'.join(levels), prompt='Do you wish to train? ') != 'train': return False
        message(game, 'Congratulations...', bottom=True)
    count = sum(lv > 0 for lv in b[0x111:0x118]); old_mu = b[0x116]; b[0x130] = 0
    for i in range(7):
        if b[0x111 + i] and mask & d[0x4C99 + i]:
            b[0x111 + i] += 1
            if b[0xF0]: b[0xF1] -= b[0xF1] // b[0xF0]; b[0xF0] -= 1
    rec.recalc_levels(c)
    if auto:
        for sid in AUTO_SPELLS.get(b[0x116], ()): b[0x70 + sid] = 1
    else:
        if b[0x116] > old_mu or b[0x115] > 8:
            spells = []
            for level in range(1, 8):
                if not b[0x146 + level]: continue
                for sid in d[0x5852 + 11*level:0x585D + 11*level]:
                    if not sid: break
                    if not b[0x70 + sid]: spells.append(sid)
            if spells: b[0x70 + choose(game, 'SPELL', spells, purpose='learn at training')] = 1
        if rec.dual(c):
            for o, t in ((0x11C, 0x69), (0x11B, 8)):
                if b[o] and not rec.has_effect(c, t): magic.add_effect(game, c, t, 0, 255, False)
    if rec.sx(b[0xEE]) > rec.sx(b[0xEF]): level_hp(s, c, mask, count)
    return True


def ability_limits(c, ability):
    b, d = c.b, ssb_data.stexe(); o = 0x4D9D + 16 * b[0x6B]
    lo, hi = (d[o + b[0x11F]], d[o + 2 + b[0x11F]]) if ability == 0 else (d[o + 4 + 2 * ability], d[o + 5 + 2 * ability])
    return max(lo, d[0x4F45 + b[0x6C] * 6 + ability]), hi


def roll_abilities(s, c):
    b, d = c.b, ssb_data.stexe(); age = rec.rdw(b, 0x6E)
    old = [age > rec.rdw(d, 0x4EFF + b[0x6B] * 10 + 2 * k) for k in range(4)]
    b[0x1C] = b[0x1D] = 0
    adjustments = (old[0] - old[1] - 2 * old[2] - old[3], old[1] + old[3],
                   -(not old[0]) + old[1] + old[2] + old[3], -2 * old[2] - old[3], -sum(old[1:]), 0)
    for a in range(6):
        value = (max(roll(s, 3, 6) + 1 for _ in range(6)) + adjustments[a]) & 255
        lo, hi = ability_limits(c, a); value = max(lo, min(hi, value))
        if a == 2 and 8 <= b[0x6C] <= 12: value = max(13, value)
        b[0x10 + 2 * a] = b[0x11 + 2 * a] = value
        if a == 0 and value == 18 and any(b[o] for o in (0x113, 0x114, 0x115)):
            b[0x1C] = b[0x1D] = min(s.random(100) + 1, d[0x4DA1 + b[0x6B] * 16 + b[0x11F]])


def default_icon(c):
    b = c.b; big = b[0x156] == 2
    b[0x153] = (9 if big else 7) if b[0x11F] else (5 if big else 0)
    b[0x154] = 23 if b[0x111] else 1 if b[0x115] else 24 if b[0x114] or b[0x113] else 29 if b[0x116] else 5


def icon(game, c):
    before = bytes(c.b[0x153:0x15D])
    while True:
        game.s.g['creation.pending'] = image(c)
        field = choose(game, 'CREATE_ICON', ['keep', 'head', 'weapon', 'size', 'color', 'cancel'])
        if field in ('keep', 'cancel'):
            if field == 'cancel': c.b[0x153:0x15D] = before
            return
        if field in ('head', 'weapon', 'size'):
            o, opts = {'head': (0x153, list(range(14))), 'weapon': (0x154, list(range(32))), 'size': (0x156, [1, 2])}[field]
            value = choose(game, 'CREATE_ICON', opts + [None], field=field)
            if value is not None: c.b[o] = value
        else:
            part = choose(game, 'CREATE_ICON', list(range(6)) + [None], field='part')
            if part is None: continue
            nibble = choose(game, 'CREATE_ICON', [0, 1], field='color channel')
            value = choose(game, 'CREATE_ICON', list(range(16)) + [None], field='color')
            if value is None: continue
            o = 0x157 + part; c.b[o] = c.b[o] & (0xF0 if not nibble else 0x0F) | value << (4 * nibble)


def create(game):
    from sm.titles.ssb.units import magic
    s, d = game.s, ssb_data.stexe(); c = Char(bytes(439)); b = c.b
    for k in range(1, 7): b[0x156 + k] = ((d[0x4CAF + k] + 8) * 16 + d[0x4CAF + k]) & 255
    b[0x129], b[0x6A], b[0x1A7], b[0xE7], b[0x155] = 50, 40, 1, 1, 10; b[0x12B] = s.random(256)
    s.g['creation.pending'] = image(c)
    try:
        race = choose(game, 'CREATE_RACE', list(range(1, 7)) + [None])
        if race is None: return
        b[0x6B] = race; b[0x156] = 1 if race in (3, 4, 5) else 2
        for t in {1: (0x5F,), 2: (0x12,), 3: (0x2F, 0x1A, 0x61), 4: (0x30, 7, 0x61), 5: (0x61,)}.get(race, ()):
            magic.add_effect(game, c, t, 0, 255, False)
        s.g['creation.pending'] = image(c)
        gender = choose(game, 'CREATE_GENDER', [0, 1, None])
        if gender is None: return
        b[0x11F] = gender; s.g['creation.pending'] = image(c)
        cls = choose(game, 'CREATE_CLASS', table_list(0x4DFF, 14, race) + [None])
        if cls is None: return
        b[0x6C] = cls; b[0xEE] = 1; classes = MULTI[cls] if cls in MULTI else (cls,)
        for i in classes: b[0x111 + i] = 1
        struct.pack_into('<i', b, 0x12C, 66667 if cls in (9, 15, 16) else 100000 if cls in MULTI else 200000)
        if 3 in classes: b[0x6D] = 1; magic.add_effect(game, c, 8, 0, 255, False)
        if 4 in classes: magic.add_effect(game, c, 0x69, 0, 255, False)
        if 6 in classes: rec.recalc_thief_skills(c)
        b[0x6A] = max(d[0x4C0C + 19 * i + b[0x111 + i]] for i in classes)
        b[0x130] = sum(d[0x4C92 + i] for i in classes) & 255; rec.recalc_saves(c)
        s.g['creation.pending'] = image(c)
        alignment = choose(game, 'CREATE_ALIGNMENT', table_list(0x4FAB, 10, cls) + [None])
        if alignment is None: return
        b[0x120] = alignment
        age_cls = cls if cls < 7 else 0 if cls in (8, 9, 10, 11) else 5 if cls in (13, 15, 16) else 2
        o = 0x4E45 + race * 28 + age_cls * 4
        if cls != 12: rec.wrw(b, 0x6E, rec.rdw(d, o) + (roll(s, d[o + 2], d[o + 3]) if cls < 7 else d[o + 2] * d[o + 3]))
        while True:
            for i in classes: b[0x111 + i] = 1
            b[0xEE] = 1; roll_abilities(s, c)
            b[0x121], b[0x123], b[0x125], b[0x12A], b[0xED] = 2, 1, 2, 1, 12
            b[0x132:0x14E] = bytes(28)
            if 0 in classes:
                rec.cleric_slots(c)
                for sid in d[0x580D:0x5817]:
                    if sid == 0: break
                    b[0x70 + sid] = 1
            if 5 in classes:
                b[0x147] = 1
                for sid in (11, 18, 19, 21): b[0x70 + sid] = 1
            rec.wrw(b, 0x109, roll(s, 2, 6) if 6 in classes else 0)
            b[0x70] = b[0x131] = b[0x1B5] = 0; level_hp(s, c, 255, len(classes))
            while train(game, c, auto=True): pass
            rec.recalc_character(c); s.g['creation.pending'] = image(c)
            if choose(game, 'CREATE_ROLL', ['keep', 'reroll']) == 'keep': break
        while True:
            text = game.ask('CREATE_NAME', None, min_length=1, max_length=15)
            if isinstance(text, str) and text and len(text.encode('latin1')) <= 15: break
        raw = text.upper().encode('latin1')[:15]; b[:16] = bytes([len(raw)]) + raw + bytes(15 - len(raw))
        default_icon(c); icon(game, c); s.g['creation.pending'] = image(c)
        if choose(game, 'CREATE_SAVE', ['save', 'cancel'], character=name(c)) == 'save':
            save_character(game, c); game.stored_character = name(c)
        return c
    finally: s.g.pop('creation.pending', None)


def store_character(s, c):
    s.g['character.' + name(c).upper()] = image(c)


def save_character(game, c):
    s = game.s; roster(s, getattr(game, 'directory', None))
    while s.g.get('character.' + name(c).upper()) is not None:
        if choose(game, 'CREATE_EXIT', ['continue', 'exit'], overwrite=1, prompt='Overwrite ' + name(c) + '? ') == 'exit': break
        text = ''
        while not text:
            text = game.ask('STRING', None, prompt='New file name: ', min_length=1, max_length=8, purpose='file name', at=0)
            text = text.strip(' ').upper()[:8] if isinstance(text, str) else ''
        raw = text.encode('latin1'); c.b[:16] = bytes([len(raw)]) + raw + bytes(15 - len(raw))
    store_character(s, c)


def roster(s, directory=None):
    if not s.g.get('creation.roster_loaded'):
        for path in sorted(Path(directory or ssb_data.SECRET).glob('*.WHO')):
            raw = path.read_bytes()
            if len(raw) != 439: continue
            it = path.with_suffix('.STF'); ef = path.with_suffix('.SFX')
            items = it.read_bytes() if it.exists() else b''; effects = ef.read_bytes() if ef.exists() else b''
            if len(items) % 67 or len(effects) % 9: raise ValueError('partial standalone sidecar')
            c = Char(raw, [items[i:i + 67] for i in range(0, len(items), 67)], [effects[i:i + 9] for i in range(0, len(effects), 9)])
            s.g.setdefault('character.' + name(c).upper(), image(c))
        s.g['creation.roster_loaded'] = 1
    return [k for k in sorted(s.g) if k.startswith('character.') and s.g[k] is not None]


def can_add(s, c):
    if any(name(c) == name(p) and c.b[0x12B] == p.b[0x12B] for p in s.party): return False
    if len(s.party) >= 8 or c.b[0xFF] < 128 and sum(p.b[0xFF] < 128 for p in s.party) >= 6: return False
    evil = lambda p: (p.b[0x120] + 1) % 3 == 0
    return not (c.b[0x114] and any(evil(p) for p in s.party) or evil(c) and any(p.b[0x114] for p in s.party) or
                c.b[0x115] and sum(p.b[0x115] > 0 for p in s.party) >= 3)


def add(game):
    s = game.s; all_keys=roster(s,getattr(game,'directory',None))
    members={name(p) for p in s.party}; all_keys=[k for k in all_keys if name(from_image(s.g[k])) not in members]
    legal=[k for k in all_keys if can_add(s,from_image(s.g[k]))]
    choices=legal+[None]+[k for k in all_keys if k not in legal]
    added=[]; key=''
    while True:
        key=choose(game,'CREATE_ADD',choices,added='|'.join(added),last=key)
        if key is None: return bool(added)
        if key not in added:
            c=from_image(s.g[key])
            if can_add(s,c):
                rec.loaded_character(c,s.r1[0x372]); c.b[0x155]=next(i for i in range(8) if all(p.b[0x155]!=i for p in s.party))
                s.party.append(c); s.sel=len(s.party)-1; s.r1[0x33E]=len(s.party); added.append(key)
            elif c.b[0x114] and any((p.b[0x120]+1)%3==0 for p in s.party): message(game,'paladins do not join with evil scum',bottom=True)
            elif c.b[0x115] and sum(p.b[0x115]>0 for p in s.party)>=3: message(game,'too many rangers in party',bottom=True)
            elif (c.b[0x120]+1)%3==0 and any(p.b[0x114] for p in s.party):
                message(game,name(next(p for p in s.party if p.b[0x114]))+' will tolerate no evil!',bottom=True)
        if len(s.party)>=8 or sum(p.b[0xFF]<128 for p in s.party)>=6: return bool(added)
        if getattr(game,'vm',None): game.vm.clear_text()


def change_class(game):
    from sm.titles.ssb.units import magic
    c = pick_member(game)
    if c is None: return False
    refuse = lambda: message(game, name(c) + " doesn't qualify.", bottom=True)
    if c.b[0x6B] != 6 or any(c.b[0x118:0x11F]): refuse(); return False
    b, d = c.b, ssb_data.stexe(); current = next((i for i in range(7) if b[0x111 + i]), None)
    if current is None: return False
    eligible = []
    for cls in table_list(0x4DFF, 14, b[0x6B]):
        if cls == current or cls > 6: continue
        if any(d[0x4F45 + current * 6 + a] >= 9 and b[0x10 + 2 * a] <= 14 for a in range(6)): continue
        if any(d[0x4F45 + cls * 6 + a] >= 9 and b[0x10 + 2 * a] <= 16 for a in range(6)): continue
        if b[0x120] in table_list(0x4FAB, 10, cls): eligible.append(cls)
    if not eligible: refuse(); return False
    cls = choose(game, 'CREATE_CLASS', eligible + [None], purpose='dual class')
    if cls is None: return False
    b[0x12C:0x130] = bytes(4); b[0x121] = 2; b[0x118 + current] = b[0x111 + current]
    b[0xEF], b[0xEE] = b[0xEE], 1; b[0x111 + current] = 0; b[0x111 + cls] = 1; b[0x6C] = cls
    b[0x132:0x14E] = bytes(28); b[0x1E:0x69] = bytes(75)
    if cls == 0: b[0x132] = 1
    if cls == 5:
        b[0x147] = 1
        for sid in (11, 18, 12, 21): b[0x70 + sid] = 1
    rec.recalc_levels(c); rec.cleric_slots(c); rec.recalc_character(c)
    for t in (8, 0x69): magic.remove_effect(game, c, t)
    if cls in (3, 4): magic.add_effect(game, c, 8 if cls == 3 else 0x69, 0, 255, False)
    o = 0x0B8B + 27 * cls
    message(game, name(c) + ' is now a 1st level ' + d[o + 1:o + 1 + d[o]].decode('latin1') + '.', bottom=True)
    return True


def remove(game, forever=False):
    s = game.s; c = pick_member(game)
    if c is None: return
    forever = forever or c.b[0xFF] >= 128
    for confirmation in range(2 if forever else 0):
        if choose(game, 'CREATE_REMOVE', ['cancel', 'remove'], forever=forever, character=name(c),
                  confirmation=confirmation) != 'remove':
            message(game, name(c) + ' breathes a sigh of relief.', bottom=True); return
    if forever:
        message(game, name(c) + ' bids you farewell.' if c.b[0x1A7] else 'You dump ' + name(c) + ' out back.', bottom=True)
        s.g['character.' + name(c).upper()] = None
    else: save_character(game, c)
    s.party.remove(c); s.sel = min(s.sel, max(0, len(s.party) - 1)); s.r1[0x33E] = len(s.party)
    if not s.party: s.party_dead = 1


def modify(game):
    c = pick_member(game)
    if c is None: return
    if struct.unpack_from('<i', c.b, 0x12C)[0] not in (0, 66667, 100000, 200000) or c.b[0xEF]:
        message(game, name(c) + " can't be modified.", bottom=True); return
    before = image(c); b = c.b
    while True:
        action = choose(game, 'CREATE_MODIFY', ['keep', 'ability', 'hp', 'name', 'cancel'])
        if action == 'cancel':
            c.b[:], c.items, c.effects = from_image(before).b, from_image(before).items, from_image(before).effects
            c.b[0x1B5] = c.b[0x70]; return
        if action == 'keep':
            levels = b[0x111:0x118]; n = sum(v > 0 for v in levels); bonus = 0
            for i, lv in enumerate(levels):
                if lv:
                    cap = ssb_data.stexe()[0x4CA9 + i]
                    bonus += con_bonus(c, i, False) * (lv + 1 if i == 4 and lv < cap else min(lv, cap - 1))
            b[0x100] = 1; b[0x131] = (b[0x70] - (bonus & 255) // max(1, n)) & 255
            for a in range(6): b[0x10 + 2 * a] = b[0x11 + 2 * a]
            b[0x1D] = b[0x1C]; rec.cleric_slots(c); return
        if action == 'ability':
            a = choose(game, 'CREATE_ABILITY', list(range(6))); lo, hi = ability_limits(c, a)
            b[0x11 + 2 * a] = choose(game, 'CREATE_ABILITY', list(range(lo, hi + 1)), ability=a)
            if a == 0 and b[0x11] == 18 and any(b[o] for o in (0x113, 0x114, 0x115)):
                cap = ssb_data.stexe()[0x4DA1 + b[0x6B] * 16 + b[0x11F]]
                b[0x1C] = choose(game, 'CREATE_ABILITY', list(range(cap + 1)), ability='exceptional strength')
            if a == 2 and b[0x132]: b[0x132] = 1
            if a == 4: b[0x70] = max(min_hp(c), min(b[0x70], max_hp(c))); b[0x1B5] = b[0x70]
        elif action == 'hp': b[0x70] = choose(game, 'CREATE_HP', list(range(min_hp(c), max_hp(c) + 1))); b[0x1B5] = b[0x70]
        elif action == 'name':
            text = game.ask('CREATE_NAME', None, min_length=1, max_length=15)
            if not isinstance(text, str) or not 1 <= len(text.encode('latin1')) <= 15: raise ValueError('name must be 1..15 bytes')
            raw = text.encode('latin1'); b[:16] = bytes([len(raw)]) + raw + bytes(15 - len(raw))
        rec.recalc_character(c)


def snapshot(game, slot='A'):
    s = game.s; save.sync_globals(s)
    names = ['CHRDAT' + slot + str(i + 1) for i in range(len(s.party))]; party = []
    for c in s.party:
        r = rec.Rec(bytes(c.b)); r.items = [rec.Item(bytes(i)) for i in c.items]; r.effects = [rec.Effect(bytes(e)) for e in c.effects]; party.append(r)
    d = dict(slot=slot, dataset=s.dataset, r0=s.r0, r1=s.r1, r2=s.r2, pos=[s.x, s.y, s.dir, s.ahead, s.attr],
             prev_mode=s.prev_mode, mode=s.mode, walls=[(v & 65535, i + 1) for i, v in enumerate(s.walls)], names=names, party=party)
    if 'vault.image' in s.g:
        v = s.g['vault.image']; d['vault'] = dict(header=v[:28], items=[rec.Item(v[i:i + 67]) for i in range(28, len(v), 67)])
    files = tuple(sorted(save.dump(d).items())); s.g['save.' + slot] = files; s.g['save.seed.' + slot] = s.seed; s.g['game.saved'] = 1
    return files


def load_game(game, slot):
    s = game.s; files = dict(s.g['save.' + slot]) if 'save.' + slot in s.g else None
    directory=Path(game.directory)
    if not (directory/('SAVGAM'+slot+'.DAT')).is_file():
        directory=directory/slot if (directory/slot/('SAVGAM'+slot+'.DAT')).is_file() else Path(ssb_data.SECRET)
    from sm.titles.ssb.intake import file_path
    def disk(filename):
        try: return file_path(directory, filename).read_bytes()
        except FileNotFoundError: return None
    source = files.get if files is not None else disk
    missing = set()
    def read(filename):
        data = source(filename)
        if data is None and filename.upper().endswith('.SAV'): missing.add(filename[:-4]); return bytes(rec.Rec.SIZE)
        return data
    try:
        try: d = save._load(files.get, slot) if files is not None else save.load(directory, slot)
        except FileNotFoundError: d = save._load(read, slot)
    except (OSError, ValueError, KeyError):
        message(game, "Can't load.  Saved game is damaged.", bottom=True); return
    if missing:
        keep = [i for i, n in enumerate(d['names']) if n not in missing]
        d['party'] = [d['party'][i] for i in keep]; d['names'] = [d['names'][i] for i in keep]
    save.restore(s, d); game.geo.resume(s, game.vm)
    game.vm.icons = {c.b[0x155]: ('CPIC', c.b[0x12B], s.dataset) for c in s.party if c.b[0xFF] >= 0x80}
    if d['vault'] is not None: s.g['vault.image'] = d['vault']['header'] + b''.join(bytes(i) for i in d['vault']['items'])
    if not s.r0[0xF2]: s.dataset = 2
    s.block = s.r0[0xF2] or 17; game.vm.resuming = True
    game.vm.load_block(s.block); game.vm.init_vm(); s.restart = 1


def save_menu(game):
    slot = choose(game, 'CREATE_SLOT', list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + [None])
    if slot is not None: snapshot(game, slot)


def run(game):
    s = game.s; mode = s.mode; s.mode = 0; s.g['8DBC'] = 0
    try:
        while True:
            opts = ['create', 'add']
            if s.party:
                opts += ['drop', 'modify', 'view', 'remove', 'save', 'begin']
                if s.r1[0x2A8]: opts += ['train', 'change class']
            else: opts += ['load']
            opts.append('exit')
            if not s.party: opts.append('initialize')
            action = choose(game, 'CREATE_MENU', opts)
            if action not in ('exit', 'save'): s.g.pop('game.saved', None)
            if action == 'create': create(game)
            elif action == 'add': add(game)
            elif action == 'drop': remove(game, True)
            elif action == 'remove': remove(game)
            elif action == 'modify': modify(game)
            elif action == 'train': train(game)
            elif action == 'change class': change_class(game)
            elif action == 'view': view(game)
            elif action == 'save': save_menu(game)
            elif action == 'initialize':
                from sm.titles.ssb.vm import Halt
                raise Halt('ov19:5508 input-device calibration is unimplemented')
            elif action == 'load':
                directory = Path(game.directory)
                slots = sorted({p.stem[-1] for p in Path(ssb_data.SECRET).glob('SAVGAM?.DAT')} |
                               {p.stem[-1] for p in directory.glob('SAVGAM?.DAT')} |
                               {p.stem[-1] for p in directory.glob('?/SAVGAM?.DAT') if p.parent.name == p.stem[-1]} |
                               {k[5:] for k in s.g if k.startswith('save.') and len(k) == 6})
                slot = choose(game, 'CREATE_SLOT', slots + [None], purpose='load game')
                if slot is not None: load_game(game, slot)
            elif action == 'begin': s.r1[0x2A8] = 0; return
            elif action == 'exit' and choose(game, 'CREATE_EXIT', ['continue', 'exit'], prompt='Quit to DOS ') == 'exit':
                if s.party and not s.g.get('game.saved') and choose(game, 'CREATE_EXIT', ['continue', 'exit'], unsaved=1,
                                                                    prompt='Game NOT saved.  Quit anyway? ') != 'exit':
                    save_menu(game); continue
                s.stop = 1; return
    finally: s.mode = mode


def test_review():
    from types import SimpleNamespace
    from unittest.mock import patch
    from sm.titles.ssb.host import Game
    from sm.titles.ssb.ui.screen import Controller
    game = Game(lambda *a, **k: 0, slot=None); s = game.s; sent = []
    assert (s.g['67D6'], s.g['67EB'], s.g['67ED']) == (4, 1, 1), 'a new game starts at speed 4 with pictures and animation on'
    def at(kind, options, **info):
        session = SimpleNamespace(game=game, decision=dict(kind=kind, options=options, info=info, i=0, hash=''), result=None)
        session.step = sent.append
        return Controller(session)
    for kind, options, info in (('CREATE_EXIT', ['continue', 'exit'], dict(prompt='Quit to DOS ')), ('CREATE_SAVE', ['save', 'cancel'], dict(character='X')),
                                ('CREATE_REMOVE', ['cancel', 'remove'], dict(character='X', forever=True, confirmation=0))):
        assert at(kind, options, **info).key('Escape') is False and not sent, kind + ': Escape must not answer a Yes/No question'
    c = at('CREATE_RACE', [1, 2, 3, 4, 5, 6, None])
    c.key('Up'); assert c.selected == 5, 'Up on the first row wraps to the last'
    c.key('Down'); c.key('End'); assert c.selected == 0, 'Down wraps; End is not a list key'
    c.key('2', '2'); assert c.selected == 1 and not sent, 'keypad 2 moves down and chooses nothing'
    c.key('5', '5'); c.key('8', '8'); assert c.selected == 0 and not sent, 'keypad 8 moves up; other digits do nothing'
    c.key('2', '2'); c.key('s', 's'); assert sent == [1], 'S chooses the highlighted row'
    at('CREATE_MENU', ['create', 'add', 'load', 'exit', 'initialize']).key('space', ' '); assert sent == [1, 0], 'Space chooses the highlighted row'
    c = at('STRING', None)
    for ch in ' ab' + ' ' * 300 + 'c': c.key('space' if ch == ' ' else ch, ch)
    assert c.entry == 'ab' + ' ' * 253, 'no leading space; spaces stop at 255; no letter once the line is at the limit of 40'
    c.key('Return'); assert sent[-1] == 'ab', 'trailing spaces are cut from the answer'
    d = save.load(); member = Char(bytes(d['party'][0])); key = 'character.' + name(member).upper()
    s.g['creation.roster_loaded'] = 1; s.g[key] = image(member); s.party = [member]; seen = []
    answers = iter((0, 0, 0, 'NEWNAME9'))
    def player(kind, options, g, **info): seen.append((kind, options and list(options), info.get('prompt'))); return next(answers)
    game.player = player; add(game); remove(game)
    assert seen[0][:2] == ('CREATE_ADD', [None]), 'a party member is not on the Add list'
    assert [x[2] for x in seen[2:]] == ['Overwrite ' + name(Char(bytes(d['party'][0]))) + '? ', 'New file name: '], seen
    assert not s.party and name(from_image(s.g['character.NEWNAME9'])) == 'NEWNAME9', 'No renames the character to the new file name'
    files = save.dump(save.load()); gone = sorted(f for f in files if f.endswith('.SAV'))[1]; del files[gone]
    with patch.object(game.vm, 'load_block'), patch.object(game.vm, 'init_vm'):
        s.g['save.A'] = tuple(files.items()); load_game(game, 'A'); assert len(s.party) == 5 == s.r1[0x33E], 'the other members load'
        s.g['save.A'] = (('SAVGAMA.DAT', b'x'),); load_game(game, 'A'); assert len(s.party) == 5, 'a damaged save leaves the party menu as it was'


def test():
    from sm.titles.ssb.state import State
    from types import SimpleNamespace
    test_review()
    test_remove_npc()
    test_change_class()
    test_modify_hp_rules()
    test_exit_unsaved()
    test_initial_class_stats()
    test_modify_eligibility()
    test_modify_hp_basis()
    test_add_loop()
    test_load_source()
    for cls, weapon in ((5, 29), (6, 5)):
        icon_char = Char(bytes(439)); icon_char.b[0x111 + cls] = 1; default_icon(icon_char)
        assert icon_char.b[0x154] == weapon
    c = Char(bytes(439)); b = c.b; b[0x6B] = 6; b[0x6C] = 2; b[0x113] = 1; b[0xEE] = 1
    b[0x19] = 18; b[0x11] = 18
    assert con_bonus(c, 2) == 4 and con_bonus(c, 5) == 2
    assert min_hp(c) == 5 and max_hp(c) == 14
    assert [xp_for(2, lv) for lv in (2, 3, 4, 5)] == [2001, 4001, 8001, 18001]
    s = State(); s.party = [c]; s.r1[0x2A8] = 8; b[0x70] = 12; b[0x1B5] = 7
    game = SimpleNamespace(s=s, ask=lambda kind, opts, **info: 0)
    struct.pack_into('<i', b, 0x12C, 2000); assert not train(game, c)
    struct.pack_into('<i', b, 0x12C, 2001); assert train(game, c)
    assert b[0x113] == 2 and b[0x70] - b[0x1B5] == 5 and struct.unpack_from('<i', b, 0x12C)[0] == 2001
    b[0x6B], b[0x113], b[0x11] = 3, 8, 17; assert capped(c, 2)
    b[0x11] = 18; assert not capped(c, 2)
    b[0x113] = 10; b[0x70], b[0x1B5] = 30, 25; level_hp(s, c, 8, 1)
    assert (b[0x70], b[0x1B5]) == (33, 28)
    oracle = State(); oracle.seed = s.seed = 123456
    b[0x113], b[0x19], b[0x131], b[0x70], b[0x1B5] = 2, 18, 10, 14, 9
    best = max(oracle.random(10) + 1, oracle.random(10) + 1)
    level_hp(s, c, 8, 1)
    assert (b[0x131], b[0x70], b[0x1B5], s.seed) == (10 + best, 18 + best, 13 + best, oracle.seed)
    files = dict(snapshot(game)); d = save._load(files.get, 'A'); assert bytes(d['party'][0]) == bytes(c.b)
    assert image(from_image(image(c))) == image(c) and s.copy().hash() == s.hash()

def test_load_source():
    from tempfile import TemporaryDirectory
    from sm.titles.ssb.host import Game
    data=save.load(slot='B'); data['party'][0].data[:16]=bytes([7])+b'W1LOCAL'+bytes(8)
    with TemporaryDirectory(dir='local') as temp:
        directory=Path(temp)
        for filename,raw in save.dump(data).items(): (directory/filename).write_bytes(raw)
        game=Game(lambda *args,**info:0,slot='B',directory=directory)
        game.s.party=[]; game.s.seed=0x12345678; load_game(game,'B')
        assert name(game.s.party[0])=='W1LOCAL' and game.s.seed==0x12345678
        snapshot(game,'B'); game.s.seed=0x87654321; load_game(game,'B')
        assert game.s.seed==0x87654321, 'native Load rewound RandSeed to the saved-session value'
        (directory/'W1LOCAL.WHO').write_bytes(bytes(game.s.party[0].b))
        assert roster(game.s,directory)==['character.W1LOCAL']


def test_add_loop():
    from sm.titles.ssb.host import Game
    game=Game(lambda *args,**info:0); s=game.s; removed=s.party[-2:]; s.party=s.party[:-2]; s.g['creation.roster_loaded']=1
    for c in removed: store_character(s,c)
    keys=['character.'+name(c).upper() for c in removed]; answers=iter((keys[0],keys[0],keys[1])); seen=[]
    def answer(kind,options,current,**info):
        seen.append(info['added']); return options.index(next(answers))
    game.player=answer
    assert add(game) and len(s.party)==6 and s.r1[0x33E]==6
    assert seen==['',keys[0],keys[0]] and len({name(c) for c in s.party})==6


def test_remove_npc():
    from sm.titles.ssb.host import Game
    for morale in (127, 128, 255):
        calls = []
        def answer(kind, options, game, **info):
            if kind == 'CREATE_REMOVE': calls.append(info['forever']); return options.index('remove')
            return 0
        g = Game(answer); c = g.s.party[0]; c.b[0xFF] = morale
        g.s.party = [c]; key = 'character.' + name(c).upper()
        remove(g)
        assert not g.s.party and g.s.r1[0x33E] == 0 and g.s.party_dead
        if morale >= 128:
            assert calls == [True, True] and g.s.g.get(key) is None, 'NPC Remove must drop without a WHO image'
            assert ' bids you farewell.' in ''.join(g.vm.out)
        else:
            assert calls == [] and g.s.g[key] == image(c), 'ov19:0528..054B saves/removes a PC without confirmation'

def test_modify_eligibility():
    from sm.titles.ssb.host import Game
    for xp, old_level, eligible in ((0, 0, True), (66667, 0, True), (100000, 0, True),
                                    (200000, 0, True), (200001, 0, False), (0, 1, False)):
        seen = []
        def answer(kind, options, game, **info):
            if kind == 'CREATE_MODIFY': seen.append(kind); return options.index('cancel')
            return 0
        game = Game(answer); c = game.s.party[0]
        struct.pack_into('<i', c.b, 0x12C, xp); c.b[0xEF] = old_level; before = image(c)
        modify(game)
        assert bool(seen) == eligible and image(c) == before


def test_modify_hp_basis():
    from sm.titles.ssb.host import Game
    for cls, level, con, hp, rolled in ((4, 5, 18, 60, 36), (2, 5, 18, 60, 40), (4, 5, 3, 60, 72)):
        game = Game(lambda kind, options, current, **info: options.index('keep') if kind == 'CREATE_MODIFY' else 0)
        c = game.s.party[0]; c.b[0x111:0x118] = bytes(7); c.b[0x111 + cls] = level
        c.b[0x19], c.b[0x70], c.b[0xEF] = con, hp, 0; struct.pack_into('<i', c.b, 0x12C, 0)
        modify(game)
        assert c.b[0x131] == rolled, (cls, level, con, c.b[0x131])


def test_initial_class_stats():
    from sm.titles.ssb.host import Game
    for cls, mask in ((2, 8), (6, 4)):
        seen = []
        def answer(kind, options, game, **info):
            if kind == 'CREATE_ALIGNMENT':
                c = from_image(game.s.g['creation.pending']); b = c.b
                assert (b[0x6A], b[0x130]) == (40, mask), 'initial THAC0/class mask'
                assert all(b[0xE8:0xED]), 'initial saving throws'
                if cls == 6: assert any(b[0xF3:0xFB]), 'initial thief skills'
                seen.append(True); return options.index(None)
            return options.index({'CREATE_RACE': 6, 'CREATE_GENDER': 0, 'CREATE_CLASS': cls}[kind])
        create(Game(answer)); assert seen


def _script(answers):
    queues = {k: list(v) for k, v in answers.items()}
    def answer(kind, options, game, **info):
        return options.index(queues[kind].pop(0)) if queues.get(kind) else 0
    return answer


def test_change_class():
    from sm.titles.ssb.host import Game
    game = Game(_script({'CREATE_CLASS': [2]})); c = game.s.party[0]; b = c.b
    b[0x6B] = 6; b[0x6C] = 6; b[0x111:0x118] = bytes([0, 0, 0, 0, 0, 0, 3]); b[0x118:0x11F] = bytes(7); b[0xEE], b[0xEF] = 3, 0
    for a in range(6): b[0x10 + 2 * a] = b[0x11 + 2 * a] = 18
    b[0x120] = table_list(0x4FAB, 10, 2)[0]
    assert change_class(game) and (b[0x113], b[0x117], b[0x11E], b[0xEF], b[0x6C]) == (1, 0, 3, 3, 2)
    assert ' is now a 1st level ' in ''.join(game.vm.out)
    before = image(c); assert not change_class(game) and image(c) == before, 'a former Thief changed class twice'
    assert "doesn't qualify." in ''.join(game.vm.out)
    b[0x118:0x11F] = bytes(7); b[0x11] = b[0x10] = 14; mark = len(game.vm.out)
    def no_list(kind, options, g, **info):
        assert kind != 'CREATE_CLASS', 'empty class list shown'
        return 0
    game.player = no_list
    assert not change_class(game) and "doesn't qualify." in ''.join(game.vm.out[mark:])


def test_modify_hp_rules():
    from sm.titles.ssb.host import Game
    def fighter(game):
        c = game.s.party[0]; b = c.b; b[0x6B] = 6; b[0x6C] = 2; b[0x111:0x118] = bytes([0, 0, 8, 0, 0, 0, 0]); b[0x118:0x11F] = bytes(7)
        b[0xEF] = 0; b[0x18] = b[0x19] = 14; struct.pack_into('<i', b, 0x12C, 200000); return c
    game = Game(_script({'CREATE_MODIFY': ['ability', 'keep'], 'CREATE_ABILITY': [4, 18]})); c = fighter(game)
    c.b[0x70] = c.b[0x1B5] = low = min_hp(c); modify(game)
    assert c.b[0x19] == 18 and c.b[0x70] == c.b[0x1B5] == min_hp(c) > low
    game = Game(_script({'CREATE_MODIFY': ['cancel']})); c = fighter(game); c.b[0x70], c.b[0x1B5] = 40, 7; modify(game)
    assert (c.b[0x70], c.b[0x1B5]) == (40, 40)


def test_exit_unsaved():
    from sm.titles.ssb.host import Game
    seen = []
    def recording(script):
        def answer(kind, options, game, **info):
            if kind == 'CREATE_EXIT': seen.append(info.get('prompt'))
            return script(kind, options, game, **info)
        return answer
    game = Game(recording(_script({'CREATE_MENU': ['exit', 'exit'], 'CREATE_EXIT': ['exit', 'continue', 'exit', 'exit'], 'CREATE_SLOT': [None]})))
    game.s.g.pop('game.saved', None); run(game)
    assert game.s.stop and seen == ['Quit to DOS ', 'Game NOT saved.  Quit anyway? '] * 2
    seen.clear(); game = Game(recording(_script({'CREATE_MENU': ['exit'], 'CREATE_EXIT': ['exit']}))); game.s.g['game.saved'] = 1
    run(game); assert game.s.stop and seen == ['Quit to DOS ']
