"""PORT2 magic: ov23, ov14 and ov25 effects (ENGINE_READ2_g2/g3, ENGINE_READ_w6).

Original spell/name tables are read from ST.EXE, never copied into the repository.
All mutable state lives in Char or State.g; context contains combat callbacks only.
Offsets in comments cite the decoded unit, not a reimplementation in another title.
"""
from sm.titles.ssb import data as ssb_data
from sm import dax; from sm.titles.ssb import rec
from sm.titles.ssb.units.shops import message, name_message

MEM, HP, STATUS, ACTIVE, SIDE = 0x1E, 0x1B5, 0x1A6, 0x1A7, 0x1A8
MODIFIERS = {                         # ov25:0466..0B15, dispatch order matters
    1: '19 25 45', 2: '41 56 58', 3: '40 41 56 58', 4: '1D 42 4B 69 20',
    5: '1C 29 3C 5A 67 70', 6: '06 0A 11 14 1C 3D 3F 39 49 4F 5D 62',
    7: '03 1B 1F 33 34 35', 8: '38 52 59 6C', 9: '12 1C 3F 4C 4F 5C 5F 60 63',
    10: '01 02 07 1A 21 24 31 4B', 11: '04 08 09 0D 11 1E 21 2D 2E 2F 30 47 4A',
    12: '08 09 0A 0D 11 14 21 24 2D 2E 31 32 36 3D 4E 5E',
    14: '3A 43 46 50 51 53 68 6B', 15: '03 05 0B 15 1B 1E 4D 6A 19 25 2F 30 45 59',
    17: '01 02 0B', 18: '27 2A', 19: '0B 17 38 64', 20: '32 36', 21: '23', 22: '27 2A 4A'}
MODIFIERS = {k: tuple(int(t, 16) for t in v.split()) for k, v in MODIFIERS.items()}
DEATH_EFFECTS = (3, 11, 21, 23, 27, 30, 31, 51, 52, 53, 91, 106, 107, 111)  # ov25:13E9
DIRECTIONS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, 0))


def spell(spell_id):
    """ov23:1046, DS:449D + 16*id; valid table IDs 1..117."""
    if not 1 <= spell_id <= 117: raise ValueError('spell ID must be 1..117')
    return ssb_data.stexe()[0x449D + 16 * spell_id:0x44AD + 16 * spell_id]


def spell_name(spell_id):
    """ov23:6628, DS:348B + 35*id Pascal string."""
    spell(spell_id)
    d, p = ssb_data.stexe(), 0x348B + 35 * spell_id
    return d[p + 1:p + 1 + min(34, d[p])].decode('cp437')


def caster_level(caster, spell_id, item=False):
    """ov26:2E86..302A: old levels count only while DualClassActive; item casts use 6."""
    if caster is None: return 6
    b, k = caster.b, spell(spell_id)[0]
    if item and k != 4: return 6
    if not b[0x111] and not b[0x116] and rec.sx(b[0x115]) < 8: return 6
    lv = [b[0x111 + i] + b[0x118 + i] * rec.dual(caster) for i in range(7)]
    if k == 0: return max(lv[0], lv[3])  # 2F21: paladin level is NOT reduced (w3 prose corrected by bytes)
    if k == 1: return max(0, lv[4] - 7)
    if k == 3: return max(lv[5], max(0, lv[4] - 8))
    return 12 if k == 4 else 0


def legal_spells(caster, combat=False):
    """ov23:0B3E/1403; ov15:2558 camp-only check, ov18:089C condition check."""
    if caster is None or not caster.b[ACTIVE] or caster.b[STATUS] == 1 or rec.has_effect(caster, 0x44): return []
    if combat and rec.has_effect(caster, 0x15): return []
    return sorted({i for i in caster.b[MEM:MEM + 75] if 0 < i <= 117 and spell(i)[11 if combat else 7]})


def forget(caster, spell_id):
    """ov26:149F ForgetSpell: remove one memorized instance, preserving pending marks."""
    for i in range(MEM, MEM + 75):
        if caster.b[i] == spell_id: caster.b[i] = 0; return True
    return False


def recalc_ability(game, char, kind):
    """ov25:16C0..1CC7 RecalcAbility, w6; item powers and best STR effect survive removal."""
    b = char.b; value = b[0x10 + 2 * kind]; fixed = None; exc = b[0x1D] if kind == 0 else 0
    for it in char.items:
        if not it[0x34] or it[0x3E] <= 0x80: continue
        power, sub = it[0x3E] & 127, it[0x3D]
        if kind == 0:
            strength, exceptional = value, exc
            if power == 3: strength, exceptional = 18, 100
            elif power == 5: strength, exceptional = (18, 100) if sub == 0 else (18 + sub, 0)
            elif power == 8 and sub == 0 and b[0x10] < 18: strength += 1
            elif power == 13: fixed = 3
            if strength > value or strength == 18 and exceptional > exc: value, exc = strength, exceptional
        else:
            if power == 8 and sub == kind and b[0x10 + 2 * kind] < 18: value += 1
            if kind == 1 and power in (12, 13): fixed = 7 if power == 12 else 3
            if kind == 3 and power == 2: value += 4 if b[0x16] < 7 else 2 if b[0x16] < 14 else 1
            if kind == 3 and power == 10: value -= 2
            if kind == 4 and power == 6: value += 1
            if kind == 5 and power == 6: value -= 1
    for e in char.effects:
        if kind == 0:
            strength, exceptional = value, exc
            p = e[3] & 127
            if e[0] == 0x0C: strength, exceptional = (18, p - 1) if p <= 101 else (p - 100, 0)
            elif e[0] == 0x71: strength, exceptional = 21, 0
            elif e[0] == 0x26 and value <= 18 and exc < 100:
                strength += 18 if p <= 101 else p - 100  # ov25:192C..195A adds decoded STR, not exceptional byte
                if strength > 18:
                    exceptional = min(100, 10 * (strength - 18) + b[0x1C]) if any(b[j] for j in (0x113, 0x114, 0x115, 0x11A, 0x11B, 0x11C)) else exc
                    strength = 18
            if strength > value or strength == 18 and exceptional > exc: value, exc = strength, exceptional
        elif kind in (1, 2) and e[0] == 0x44: fixed = 3
        elif kind == 5 and e[0] == 0x0E: value += e[3]
    value = fixed if fixed is not None else value
    b[0x11 + 2 * kind] = value & 255
    if kind == 0: b[0x1C] = (exc if fixed is None and value == 18 else 0) & 255
    if kind == 4:
        old, bonus, count = b[0x70], 0, 0
        for i in range(7):
            cap = ssb_data.stexe()[0x4CA9 + i]
            for former in (True, False):
                lv = b[(0x118 if former else 0x111) + i]
                if not lv: continue
                if not former:
                    count += 1; lv = min(lv, cap)
                    if lv > b[0xEF]: lv -= b[0xEF]
                lv = min(lv, cap - 1)
                if i == 4 and (b[0xEF] == 0 or b[0x11C] == b[0xEF]): lv += 1
                per = max(0, value - 14) if value <= 19 else 5 if value == 20 else 6 if value <= 23 else 7
                if i not in (2, 3, 4): per = min(per, 2)
                bonus += per * lv
        b[0x70] = (b[0x131] + bonus // max(1, count)) & 255
        b[HP] = max(0, min(255, b[HP] + b[0x70] - old))
        if value >= 20: add_effect(game, char, 0x3E, 60, 255, True)
        else: remove_effect(game, char, 0x3E)


class _Magic:
    """ov23/ov25 execution frame; no persistent or un-hashed state is kept here."""
    def __init__(self, game, context=None):
        """ov25:0423 callback frame; context is the combat unit's geometry adapter."""
        self.game, self.s, self.g, self.ctx = game, game.s, game.s.g, context or {}
        self.fight = getattr(game, 'combat', None)

    def index(self, char):
        """ov33:0C28 combatant lookup; stable State.chars index replaces a far pointer."""
        return next((i for i, c in enumerate(self.s.chars()) if c is char), -1)

    def tell(self, char, text, flash=None, delay=None):
        """ov26:173F/270F: name message and optional four-frame hit/effect animation."""
        name=bytes(char.b[1:1 + char.b[0]]).decode('latin1')
        message(self.game, name + ' ' + text, display_text=name+'\n'+text,
                actor=self.index(char), delay=0 if flash is not None and self.fight else delay,names=((0,self.index(char)),),
                status=False)  # ov26:27B1 completes NameMessage before the first hit blit/flush at 284E/2853, regardless of caption length.
        if flash is not None and self.fight is not None:
            self.fight.flash(char, flash)
            if flash: self.fight.show('clear', char)  # ov25:2194; damage clears after its death/disruption tail at 20B1.

    def effect_text(self, sid):
        """ov23:1F14..619A: the strings passed to ApplyToTargets/AreaEffectNoDamage.

        Literal labels are in the original DS effect-name table; no message is
        invented for handlers passing the empty string (28, 97, 100, etc.).
        """
        offsets = {1:0x224D, 8:0x23A3, 14:0x243B, 19:0x24AD, 24:0x251F, 25:0x2545,
                   32:0x264F, 33:0x2675, 38:0x270D, 40:0x2733, 42:0x296D, 45:0x27A5,
                   48:0x27F1, 55:0x2863, 79:0x2CB1, 80:0x25DD, 116:0x25DD, 117:0x31E3}
        if sid in offsets:
            ds=ssb_data.stexe(); off=offsets[sid]
            return 'is ' + ds[off+1:off+1+ds[off]].decode('cp437')
        if sid in (5,11,18,22,26,29,73,77): return 'is Affected'
        if sid in (6,7,16,17,52,53,54,69,88,95,112): return 'is Protected'
        if sid in (10,27,81,96): return 'is Charmed'
        if sid in (23,49,94): return 'is Held'
        if sid in (30,50): return 'is invisible'
        return {2:'is Cursed', 21:'falls Asleep', 44:'has been cursed!', 57:'is Hastened',
                61:'is paralyzed', 82:'is Confused', 86:'is clumsy'}.get(sid, '')

    def roll(self, dice, sides, record=False):
        """ov25:11C6 / 1211; one System.Random(sides) per die, byte result."""
        if record: self.g['87D9'] = dice & 255
        return sum(self.s.random(sides) + 1 for _ in range(max(0, dice))) & 255

    def get(self, c, field):
        """ov14:0014 et al: combatant fields via c1, fallback state keys are hashed."""
        if 'get' in self.ctx: return self.ctx['get'](c, field)
        if self.fight is not None:
            v = self.fight.record(c)[field]
            return (self.s.chars()[v] if 0 <= v < len(self.s.chars()) else None) if field == 10 else v
        v = self.g.get('magic.c.%d.%d' % (self.index(c), field), -1 if field == 10 else 0)
        return (self.s.chars()[v] if 0 <= v < len(self.s.chars()) else None) if field == 10 else v

    def put(self, c, field, value):
        """ov14:0274 combatant writes; pointer fields stored as stable indices."""
        if 'set' in self.ctx: self.ctx['set'](c, field, value); return
        if self.fight is not None:
            self.fight.record(c)[field] = self.index(value) if field == 10 else value
            return
        self.g['magic.c.%d.%d' % (self.index(c), field)] = self.index(value) if field == 10 else value

    def reset(self, c):
        """ov26:2DEC CombatantReset (ov14:0274)."""
        for field in (0, 3, 6, 7): self.put(c, field, 0)

    def position(self, c):
        """ov33:0B96/0BDF combatant coordinates; map-dependent calls require c1."""
        if 'position' in self.ctx: return self.ctx['position'](c)
        if self.fight is not None: return self.fight.position(c)
        raise ValueError('magic requires combat position context')

    def distance(self, a, b):
        """ov26:2D10 Reach: orthogonal costs 2 and diagonal 3, in half-square units."""
        if a is None or b is None: return 255
        if a is b: return 0
        if self.fight is not None: return self.fight.distance(a, b)
        if 'position' not in self.ctx: return 255
        x, y = self.position(a); u, v = self.position(b); dx, dy = abs(x-u), abs(y-v)
        return max(dx, dy) + min(dx, dy) // 2

    def find(self, c, typ):
        """ov26:28C8 HasEffect: first matching live node."""
        return next((e for e in c.effects if e[0] == typ), None) if c is not None else None

    def add(self, c, typ, duration, param=0, cb=False):
        """ov25:1235 AddEffect always appends; duplicates are legal."""
        e = bytearray((typ & 255, duration & 255, duration >> 8 & 255, param & 255, int(bool(cb)), 0, 0, 0, 0))
        c.effects.append(e); return e

    def remove(self, c, typ, e=None):
        """ov25:00A6 RemoveEffect calls expiry before unlink, then recalculates STR/CHA."""
        if e is None: e = self.find(c, typ)
        if e is None or not any(e is x for x in c.effects): return False
        if e[4]: self.callback(c, e, 1)
        c.effects[:] = [x for x in c.effects if x is not e]
        if typ in (0x0C, 0x26, 0x71, 0x0E): recalc_ability(self.game, c, 5 if typ == 14 else 0)
        return True

    def cancel(self, typ=0):
        """ov14:007F CancelSpell clears pending effect and damage."""
        if not typ or self.g.get('87D3', 0) == typ: self.g['87D3'] = self.g['87D4'] = 0

    def resistance(self, c):
        """ov25:01E1 MagicResistance; 87D8 is spell ID (g2 correction to w6)."""
        g = self.g
        if c.b[0x1A5] and g.get('87D3', 0) and (not g.get('87D4', 0) or not g.get('87D5', 0) & 8):
            sid = g.get('87D8', 0)
            level = caster_level(self.s.selc(), sid, g.get('8D99', 0)) if sid else 6
            if self.roll(1, 100) <= c.b[0x1A5] + 5 * (11-level):
                g['87D4'] = 0
                if g['87D3'] not in (0x5B, 0x52): g['87D3'] = 0

    def modifiers(self, c, kind):
        """ov25:0466 dispatch + 0287 aura lookup; only first effect per type is invoked."""
        if kind in (6, 9): self.resistance(c)
        for typ in MODIFIERS.get(kind, ()):
            e = self.find(c, typ)
            if e is None and typ in (0x15, 0x2D, 0x2E, 0x31):
                for owner in self.s.chars():
                    candidate = self.find(owner, typ)
                    if candidate is not None and (self.s.mode != 5 or self.distance(owner, c) <= (6 if typ == 0x31 else 1)):
                        e = candidate; break
            if e is not None: self.callback(c, e)

    def save(self, c, idx, bonus=0):
        """ov25:1137 SavingThrow: natural 1/20 bypass modifiers, item AC bonus applies."""
        g = self.g; g['87E8'] = 1; g['87D2'] = self.roll(1, 20)
        if g['87D2'] in (1, 20): return g['87D2'] == 20
        g['87D2'] += c.b[0x19A] + rec.sx(bonus); g['87E7'] = idx
        self.modifiers(c, 12)
        return c.b[0xE8 + idx] <= g['87D2']

    def effect(self, c, typ, duration, param=0, cb=False, save_type=0, saved=False, text=''):
        """ov25:20C8 ApplyEffect: resistance, then save, then extend first duration."""
        self.g['87D3'] = typ; self.modifiers(c, 9)
        if not self.g['87D3'] or saved and save_type == 1:
            self.tell(c, 'is Unaffected')  # ov25:20F3..2126, NameMessage without HitAnimation.
            return None
        e = self.find(c, typ)
        if e is None: e = self.add(c, typ, duration, param, cb)
        elif rec.rdw(e, 1) and duration > rec.rdw(e, 1): rec.wrw(e, 1, duration)
        if text: self.tell(c, text, 1)  # ov25:217B..2194.
        return e

    def strip(self, c):
        """ov25:13E9 StripOnDeath; remove one instance of each decoded type."""
        for typ in DEATH_EFFECTS: self.remove(c, typ)
        if self.find(c, 0x4D) is not None and c.b[0xFF] == 0xB3: c.b[SIDE] = 0

    def kill(self, c, status=6):
        """ov25:0000 KillCharacter; preserve an existing dead/stone/gone status."""
        if c.b[STATUS] in (6, 7, 8): return
        c.b[STATUS], c.b[ACTIVE], c.b[HP] = status, 0, 0
        self.strip(c); self.reset(c)
        if 'kill' in self.ctx: self.ctx['kill'](c, status)
        elif self.fight is not None: self.fight.remove(c)

    def damage(self, c, amount, save_type=0, saved=False):
        """ov25:1D84 damage modifiers/saves; ov26:2953 HP, overkill, interrupted casting."""
        g, b = self.g, c.b; g['87D4'] = amount & 255; self.modifiers(c, 6)
        if saved:
            if save_type == 1: g['87D4'] = 0
            elif save_type == 2: g['87D4'] //= 2
        else: self.modifiers(c, 20)
        n = g['87D4']
        if n <= 0 or not b[ACTIVE]: return 0
        source = {1: 'Fire', 2: 'Cold', 4: 'Electricity', 0x10: 'Acid'}.get(g.get('87D5', 0) & 0xF7,
                  'Magic' if g.get('87D5') == 8 else '')
        name = bytes(b[1:1 + b[0]]).decode('latin1')
        self.tell(c, 'takes %d point%s of damage%s' % (
            n, '' if n == 1 else 's', ' from ' + source if source else ''), 0)  # ov25:1DE9..1F5A
        hp, over = max(0, b[HP] - n), max(0, n - b[HP])
        if over > 9 or hp == 0 and b[STATUS] == 1: b[STATUS] = 6
        elif over: b[STATUS] = 5; self.put(c, 14, over)
        elif hp == 0: b[STATUS] = 4
        b[HP] = hp
        if b[STATUS] in (4, 5, 6, 7, 8): b[ACTIVE] = 0; b[HP] = 0
        if self.s.mode == 5:
            self.put(c, 1, 0)
            pending = self.get(c, 0)
            if pending:
                message(self.game, name + ' lost a spell')  # ov25:1F5F..1FC4
                forget(c, pending); self.reset(c)
            if not b[ACTIVE]:
                result='is killed' if b[STATUS] in (6,7,8) else 'Goes Down, and is Dying' if b[STATUS]==5 else 'Goes Down'
                message(self.game,name+' '+result,display_text=name+'\n'+result,  # ov25:1FC8..205E; arena 004/00468: GOES DOWN, AND / IS DYING.
                        names=((0,self.index(c),12),),continuation=True,delay=0,blank=False)  # ov25:1FC8..205E; no blank row (015/00477 0 px). Not merged with the first skull: the text write and ov33:0DEB's first flush are a few ms apart; 015/00477 shows them in one frame, 051-normal/00621, -diagonal/00661, -shallow/00591 in two.
                self.strip(c); self.modifiers(c, 13); self.reset(c)
                if 'kill' in self.ctx and b[STATUS] != 10: self.ctx['kill'](c, b[STATUS])
                elif self.fight is not None and b[STATUS] != 10: self.fight.remove(c)
        if self.fight is not None: self.fight.show('clear',c)  # ov25:20B1 -> ov26:1827.
        return n

    def heal(self, c, amount, only_if_hurt=False):
        """ov25:21BF HealHP; unconscious/dying recovery differs inside combat."""
        b = c.b
        if b[STATUS] not in (0, 1, 4, 5) or only_if_hurt and b[HP] >= b[0x70]: return False
        b[HP] = min(b[0x70], b[HP] + max(0, amount))
        if not b[ACTIVE]:
            if b[STATUS] == 5: b[STATUS] = 4
            if b[STATUS] == 4 and self.s.mode != 5: b[STATUS], b[ACTIVE] = 0, 1
        return True

    def touch(self, caster, target):
        """ov23:111E recalculation, ov25:103A SpellTouchAttack (60-based AC)."""
        rec.recalc_character(target, self.s.r1[0x372]); self.modifiers(target, 11)
        if 'touch' in self.ctx: return self.ctx['touch'](caster, target, target.b[0x1AB])
        while self.remove(caster, 0x19): pass
        g = self.g; g['87DF'] = self.roll(1, 20)
        if g['87DF'] == 1: return False
        if g['87DF'] == 20: g['87DF'] = 100
        self.modifiers(caster, 10); self.modifiers(target, 16)
        return g['87DF'] >= 0 and g['87DF'] + caster.b[0x1AA] + self.s.r1[0x371 if caster.b[SIDE] == 0 else 0x370] >= target.b[0x1AB]

    def duration(self, sid, caster):
        """ov23:0F97 EffectDuration special cases and the DS duration coefficients."""
        if sid == 26: return 3780
        if sid == 40: return 10 * self.roll(1, 6)
        if sid in (57, 61): return self.roll(5, 4)
        if sid == 59: return 40 + 10 * self.roll(1, 4)
        sp = spell(sid)
        return (caster_level(caster, sid, self.g.get('8D99', 0)) * sp[5] + sp[4]) & 65535

    def apply(self, caster, sid, targets, param=0, cb=False, damage=0, dtype=0):
        """ov23:1046 common handler tail; a missed touch zeros damage for later targets too."""
        sp = spell(sid); self.g['87D5'] = dtype if damage else 0
        level = param or caster_level(caster, sid, self.g.get('8D99', 0))
        for target in targets:
            if target is None: continue
            saved = self.save(target, sp[9]) if sp[8] else False
            if spell(self.g.get('87D8') or sid)[2] == 255 and not self.touch(caster, target): damage, saved = 0, True
            if damage: self.damage(target, damage, sp[8], saved)
            if sp[10]: self.effect(target, sp[10], self.duration(sid, caster), level, cb, sp[8], saved, self.effect_text(sid))
        self.g['87D5'] = 0

    def fear(self, c):
        """ov23:4AE9 / ov14:2A36: controlled flight clears current opponent."""
        self.put(c, 16, 1); self.put(c, 10, None); c.b[0x1A9] = 1
        if c.b[0xFF] <= 127: c.b[0xFF] = 0xB3

    def poison(self, c, bonus=0):
        """ov14:1A67 PoisonBite: carrier 40h contributes its save bonus."""
        victim = self.get(c, 10)
        if victim is None: return
        e = self.find(victim, 0x40)
        if e is not None: bonus = 0 if bonus < 0 else bonus + e[3]
        self.effect(victim, 0x37, 0, 255, False, 1, self.save(victim, 0, bonus))
        if self.find(victim, 0x37) is not None: self.kill(victim)

    def callback(self, c, e, mode=0, typ=None):
        """ov25:0423 -> ov14 handlers; each branch cites its decoded entry offset."""
        typ = e[0] if typ is None else typ
        b, g, actor = c.b, self.g, self.s.selc() or c
        ab, dtype, sid = actor.b, g.get('87D5', 0), g.get('87D8', 0)
        opponent = self.get(c, 10)
        # Removal-specific and mode-independent handlers precede the apply-only guard.
        if typ == 0x78 or g.get('8DB8', 0):                            # ov14:3908 item override
            g['8DB8'] = 0
            if mode: self.remove(c, e[0x3D])
            else: self.add(c, e[0x3D], 0, 255, True)
            return
        if typ in (0x1B, 0x1F, 0x33, 0x34, 0x35, 0x6A): self.reset(c); return  # ov14:0274/3619
        if typ == 3:                                                # ov14:02FF snakes
            n = b[0x1AD] + b[0x1AE]
            if e[3] > n: e[3] -= n
            elif not mode: self.remove(c, 3)
            self.reset(c); return
        if typ == 0x0B:                                             # ov14:04B8 charm
            if mode:
                b[SIDE] = (e[3] & 64) // 64
                if b[0xFF] == 0xB3: b[0xFF] = b[0x1A9] = 0
            elif not e[3] & 32:
                e[3] = (e[3] + 32 + (b[SIDE] << 6)) & 255
                b[SIDE], b[0x1A9] = e[3] // 128, 1
                if b[0xFF] <= 127: b[0xFF] = 0xB3
                self.put(c, 10, None)
            g['87E2'] = 100
            g['87CC'], g['87CD'] = (sum(x.b[ACTIVE] != 0 and x.b[SIDE] == side for x in self.s.chars()) for side in (0, 1))
            return
        if typ == 0x17:                                             # ov14:080A spiritual hammer
            it = next((i for i in c.items if i[0x2E] == 6 and i[0x31] == 0x79), None)
            if mode and it is not None: c.items[:] = [i for i in c.items if i is not it]
            elif not mode and it is None and len(c.items) < 16:
                it = bytearray(67); it[0x2E] = it[0x30] = 6; it[0x31] = 0x79; it[0x32] = 1
                it[0x3D], it[0x3E] = 0x17, 0x80
                if rec.readied(c)[0] is None: it[0x34] = 1
                c.items.append(it)
                if self.fight is not None:
                    self.tell(c, 'gains an item'); self.fight.show('clear', c)  # ov14:09BF..09E9, DS:204D + CS:0802, clear=1.
                else: name_message(self.game, c, 'gains an item')
            b[0x160] = len(c.items); rec.recalc_character(c, self.s.r1[0x372]); return
        if typ in (0x28, 0x5B): self.clear_area(c, e); return           # ov14:1096/2C4E
        if typ == 0x64:                                             # ov14:30B1 delayed blast expiry
            if mode and self.s.mode == 5: self.clear_area(c, e, blast=True)
            return
        if typ in (0x4D, 0x6B) and mode:                             # ov14:250D/3637 berserk removal
            if b[0xFF] == 0xB3:
                b[0xFF] = 0
                if typ == 0x4D: b[0x1A9] = 0
            b[SIDE] = 0 if typ == 0x4D else e[3]; return
        if typ == 0x38:                                             # ov14:16BC invisibility refresh
            if mode:
                if self.s.mode == 5: self.remove(c, 0x19)
            else: self.add(c, 0x19, 1, 12)
            return
        if typ == 0x6E:                                             # ov14:3784 paladin timer
            if mode: b[0x6D] = ((b[0x114] + b[0x11B] * rec.dual(c) - 1) // 5 + 1) & 255
            return
        if typ == 0x6F:                                             # ov14:37D5 fear removal
            if mode:
                if b[0xFF] == 0xB3: b[0xFF] = b[0x1A9] = 0
                self.put(c, 16, 0)
            return
        if typ == 0x4F:                                             # ov14:2689 golem (both modes)
            if dtype & 1 and dtype & 8: b[HP] = min(b[0x70], b[HP] + g.get('87D4', 0))
            elif dtype & 4: self.add(c, 0x2A, 3, 255)
            self.cancel(); return
        if mode: return
        if typ == 1: g['87E2'] = (g.get('87E2', 0) + 5) & 255; g['87DF'] = g.get('87DF', 0) + 1  # ov14:02A9
        elif typ == 2: g['87E2'] = max(0, g.get('87E2', 0)-5); g['87DF'] = g.get('87DF', 0)-1  # ov14:02C1
        elif typ in (4, 0x2F, 0x30):                                # ov14:0394/159E/15C3
            if ab[0x15D] & {4: 1, 0x2F: 4, 0x30: 32}[typ]: g['87DF'] = g.get('87DF', 0) - (7 if typ == 4 else 4)
        elif typ in (6, 0x49, 0x5D, 0x62):                          # ov14:03B7/2444/2ECE/3045
            if dtype & {6: 4, 0x49: 32, 0x5D: 1, 0x62: 2}[typ]: self.cancel()
        elif typ in (7, 0x1A):                                      # ov14:03D6/0A38
            if opponent is not None and opponent.b[0x15E if typ == 7 else 0x15D] & (4 if typ == 7 else 128): g['87DF'] = g.get('87DF', 0) + 1
        elif typ in (8, 9, 0x2D, 0x2E):                             # ov14:0413/0450 protection
            if ab[0x120] in ((2, 5, 8) if typ in (8, 0x2D) else (0, 3, 6)):
                g['87D2'] = g.get('87D2', 0) + 2; g['87DF'] = g.get('87DF', 0)-2
        elif typ in (0x0A, 0x14):                                   # ov14:048D/06CA elemental resistance
            if dtype & (2 if typ == 10 else 1): g['87D4'] = g.get('87D4', 0)//2; g['87D2'] = g.get('87D2', 0)+3
        elif typ == 0x0D:                                          # ov14:05AC
            if not dtype & 8: g['87D2'] = g.get('87D2', 0)+1
            g['87DF'] = g.get('87DF', 0)-1
        elif typ in (0x0F, 0x2B, 0x2C, 0x3E):                       # ov14:05D5/145F/14F4/19D7
            if not g.get('87DC', 0):
                self.add(c, 0x1A if typ == 15 else typ, 60 if typ in (0x2B, 0x3E) else 10, e[3], True)
                if typ == 0x3E: self.heal(c, 1, True)
                elif typ == 0x2B:
                    if b[0x11] > 3: b[0x11] -= 1
                    else: self.add(c, 0x1F, 0, 255)
                elif b[HP] > 1: g['87D5'] = 0; self.damage(c, 1)
                elif typ == 0x2C: self.add(c, 0x1F, 0, 255)
        elif typ == 0x11:                                          # ov14:0665 shield
            b[0x1AB] = max(b[0x1AB], 57); g['87D2'] = g.get('87D2', 0)+1
            if sid == 15: g['87D4'] = 0
        elif typ in (0x12, 0x5F, 0x60):                             # ov14:069E/2F77/2FA5 charm/sleep immunity
            if typ == 0x60 or self.roll(1, 100) <= (30 if typ == 0x12 else 90): self.cancel(11); self.cancel(0x35)
        elif typ in (0x15, 0x1E):                                   # ov14:06F5/0B8F silence/cough
            if typ == 0x1E and self.get(c, 2): self.tell(c, 'is coughing')  # ov14:0B9E..0BCF, oracle 034
            self.put(c, 1, 0); self.put(c, 2, 0)
            if typ == 0x1E:
                rec.recalc_character(c, self.s.r1[0x372]); b[0x1AC] = b[0x1AC]-2 if b[0x1AC] > 52 else 50; b[0x1AB] = b[0x1AC]
        elif typ == 0x16:                                          # ov14:077A slow poison
            if self.find(c, 0x37) is not None: self.kill(c); self.remove(c, 0x37)
            g['87DC'] = 1; self.remove(c, 15); g['87DC'] = 0
        elif typ == 0x19:                                          # ov14:0A03 invisibility
            if self.find(actor, 0x18) is None: g['87DB'] = 1; g['87DF'] = g.get('87DF', 0)-4
        elif typ == 0x1C:                                          # ov14:0A83 mirror image: Roll(images+1,1)
            if self.roll(e[3]//16+1, 1) <= 1: return
            if sid and (g.get('87DD', 0) or not spell(sid)[14]): return
            self.cancel(); n = (e[3] >> 4)-1
            if n: e[3] = n << 4 | e[3] & 15
            else: self.remove(c, typ)
        elif typ == 0x1D: g['87D4'] = g.get('87D4', 0)-g.get('87D4', 0)//4  # ov14:0B5D
        elif typ == 0x20:                                          # ov14:0C8B dispel evil
            if opponent is not None and opponent.b[0x15D] & 1:
                if not self.save(opponent, 4): self.kill(opponent, 8)
                self.remove(c, 4); self.remove(c, 0x20)
        elif typ in (0x21, 0x24):                                   # ov14:0D51/0FB9 blind/curse
            g['87DF'] = g.get('87DF', 0)-4; g['87D2'] = g.get('87D2', 0)-4
            if typ == 0x21: b[0x1AB] = (b[0x1AB]-4)&255; b[0x1AC] = (b[0x1AC]-4)&255
        elif typ == 0x22: self.callback(c, e, typ=0x2B); self.callback(c, e, typ=0x2C)  # ov14:0D82
        elif typ == 0x23:                                          # ov14:0DED confusion
            r = self.roll(1, 100)
            if r <= 10: self.remove(c, typ); self.fear(c); self.effect(c, 0x6F, 10, 0, True, 1)
            elif r <= 60: self.reset(c)
            elif r <= 80:
                berserk = self.effect(c, 0x4D, 1, b[SIDE], True, 1)
                if berserk is not None: self.callback(c, berserk)
            if self.save(c, 4, -2): self.remove(c, 0x23)
        elif typ == 0x25:                                          # ov14:0FD2 blink
            if not self.get(c, 3): g['87DB'], g['87DF'] = 1, -1
        elif typ in (0x27, 0x2A):                                   # ov14:1002/1429 haste/slow
            if typ == 0x27 and not e[3] & 16:
                e[3] = (e[3]+16)&255; rec.wrw(b, 0x6E, rec.rdw(b, 0x6E)+1); g['7D44'] = 1
            for k in ('87D6', '87D7'): g[k] = (g.get(k, 0)*2)&255 if typ == 0x27 else g.get(k, 0)//2
        elif typ in (0x29, 0x3C, 0x5A, 0x67):                        # ov14:13E5/1930/2BE7/3553 weapon immunity
            w = rec.readied(actor)[0]
            if typ == 0x29 and w is not None and w[0x32] == 0 and self.distance(actor, c) > 1:
                if self.roll(1, 100) <= 100: g['87D4'] = 0; g['87DF'] = -1; g['87E0'] = g.get('87E0', 0)-1
            elif typ == 0x3C and (w is None or w[0x32] < 3): g['87D4'] = 0
            elif typ == 0x5A and w is not None and rec._T(w, 7)&128: g['87D4'] = 0
            elif typ == 0x67 and (w is None or not w[0x32]) and (1 <= ab[0x6B] <= 6 or ab[0x6B] in (0, 7) and ab[0xEE] < 4): g['87D4'] = 0
        elif typ == 0x31:                                          # ov14:15E8 prayer
            sign = 1 if b[SIDE] == (e[3]&16)//16 else -1
            g['87D2'] = g.get('87D2', 0)+sign; g['87DF'] = g.get('87DF', 0)+sign
        elif typ in (0x32, 0x36):                                   # ov14:163D/1678 hot/cold fire shield
            protect, hurt = (2, 1) if typ == 0x32 else (1, 2)
            if dtype & protect: g['87D2'] = g.get('87D2', 0)+2
            elif dtype & hurt and not g.get('87E8' if typ == 0x32 else '7523', 0): g['87D4'] = (g.get('87D4', 0)*2)&255
        elif typ in (0x39, 0x3F):                                   # ov14:1708/1A2C globe
            if sid and spell(sid)[1] <= (4 if typ == 0x39 else 3): self.cancel()
        elif typ == 0x3D:                                          # ov14:1974 fire resistance
            if dtype & 1:
                n = g.get('87D9', 0); g['87D4'] = max(n, g.get('87D4', 0)-2*n)
                g['87D2'] = g.get('87D2', 0)+4
                if not dtype & 8: self.cancel()
        elif typ in (0x40, 0x56): self.poison(c, -2 if typ == 0x56 else 0)  # ov14:1B49/2B56
        elif typ in (0x41, 0x58):                                   # ov14:1B79/2B73
            if opponent is not None:
                saved = self.save(opponent, 1 if typ == 0x41 else 0)
                if typ == 0x41:
                    if not saved: self.kill(opponent, 7)
                else: self.effect(opponent, 0x34, 10, 12, False, 1, saved)
        elif typ == 0x42 and g.get('87DF', 0) >= 75 and opponent is not None:  # ov14:1C26 swallow
            self.kill(opponent); self.roll(1, 100)
            if self.fight is not None:
                x, y = self.position(c); self.fight.place(opponent, x, y); self.fight.remove(opponent)
        elif typ == 0x44:                                          # ov14:21BC feeblemind
            b[0x13] = b[0x15] = 3
            if self.s.mode == 5:
                self.put(c, 1, 0); pending = self.get(c, 0)
                if pending: forget(c, pending); self.put(c, 0, 0)
        elif typ == 0x45:                                          # ov14:2284 invisibility to animals
            if b[0x15D]&0x45 and self.find(c, 0x18) is None: g['87DB'] = 1; g['87DF'] = g.get('87DF', 0)-4
        elif typ in (0x47, 0x4A):                                   # ov14:240F/2465 AC modifiers
            n = -2 if typ == 0x47 else 2
            b[0x1AB], b[0x1AC] = (b[0x1AB]+n)&255, (b[0x1AC]+n)&255
        elif typ == 0x4B:                                          # ov14:2497 giant-slayer
            if opponent is not None and opponent.b[0x15E]&1: g['87D4'] = (rec.str_dmg(c)+self.roll(6, 6, True))&255; g['87DF'] = g.get('87DF', 0)+1
        elif typ in (0x4D, 0x6B):                                   # ov14:250D/3637 berserk
            b[0x1A9] = 1; b[0xFF] = 0xB3 if b[0xFF] <= 127 or b[0xFF] == 0xB3 else 0xB2
            if self.s.mode == 5 or typ == 0x6B:
                others = sorted((x for x in self.s.chars() if x is not c and x.b[ACTIVE]), key=lambda x: self.distance(c, x))
                self.put(c, 10, others[0] if others else None)
                if others: b[SIDE] = others[0].b[SIDE]^1
                if typ == 0x4D: self.put(c, 1, 0)
        elif typ == 0x4E: g['87D2'] = g.get('87D2', 0)+1              # ov14:2674
        elif typ == 0x52:                                          # ov14:2A36 fear aura
            for m in self.s.chars():
                if m.b[SIDE] != b[SIDE] and m.b[0xEE] < 5 and self.find(m, 0x5C) is None and self.find(m, 0x6F) is None:
                    if self.effect(m, 0x6F, 0, 255, True, 1) is not None: self.fear(m)
        elif typ == 0x59:                                          # ov14:2B94 displacement
            if not g.get('8DC7', 0) and not g.get('87DF', 0): e[3] &= 15
            elif not e[3]&16: g['87DF'] = -1; e[3] |= 16
        elif typ == 0x5C: self.cancel(0x6F)                         # ov14:2EB6
        elif typ in (0x5E, 0x61):                                   # ov14:2EEF/2FC4 racial CON saves
            if g.get('87E7', 0) in ((0, 2, 4) if typ == 0x5E else (2, 4)):
                con = b[0x19]; bonus = 1 if 4 <= con <= 6 else 2 if 7 <= con <= 10 else 3 if 11 <= con <= 13 else 4 if 14 <= con <= 17 else 5 if 18 <= con <= 20 else 0
                g['87D2'] = g.get('87D2', 0)+bonus
        elif typ == 0x63:                                          # ov14:3066 poison immunity
            self.cancel(0x37); self.cancel(0x34)
            if not g.get('87E7', 0): g['87D2'] = 100
        elif typ == 0x69:                                          # ov14:35B2 ranger melee bonus
            if opponent is not None and self.distance(c, opponent) <= 1 and opponent.b[0x15D]&8: g['87D4'] = (g.get('87D4', 0)+b[0x115])&255
        elif typ == 0x6C: self.add(c, 0x19, 255, 255)                # ov14:3757
        elif typ == 0x70:                                          # ov14:3826 fire shield retaliation
            if self.distance(actor, c) < 2 and g.get('87D4', 0):
                damage = g['87D4']; g['87D5'] = 8; self.damage(actor, 2*damage); g['87D4'], g['87D5'] = damage, dtype
        elif typ in (0x3A, 0x43, 0x46, 0x50, 0x51): self.special(c, typ)  # ov14:1762/2094/22E4/278C/28BC
        elif typ in (0x53, 0x68): breath_weapon(self.game, c, e)  # ov23:6DBF/6DCC store e121 at DS:87E6 + 4*type (kind 0Eh); the original breathes, this never ran
        # The remaining table entries are decoded empty/marker/display handlers.

    def special(self, caster, typ):
        """ov14:1762/2094/22E4/278C/28BC gaze, adjacent/ranged breath and acid spit."""
        victim = self.get(caster, 10)
        if typ != 0x43:
            targets = self.pick(caster, 61 if typ in (0x3A, 0x51) else 68, True)
            victim = targets[0] if targets else None
        if victim is None: return
        distance = self.distance(caster, victim)
        if typ == 0x3A:
            if victim.b[SIDE] != (caster.b[SIDE] == 0): return  # ov14:178A..179A: keep the gaze only when victim equals OppositeSide(caster).
            if self.find(caster, 0x3B) is not None and self.find(victim, 0x48) is not None: victim = caster
            if not self.save(victim, 1): self.kill(victim, 7)
        elif typ == 0x46:
            if distance < 2 and not self.save(victim, 4): self.effect(victim, 0x23, self.roll(1, 10)+2, caster.b[SIDE], True, 1)
        elif typ == 0x43:
            if self.g.get('8DC7', 0) and caster.b[0x121] >= self.g['8DC7'] and distance < 2:
                self.g['87D5'] = 0x21; self.damage(victim, 8, 2, self.save(victim, 3))
        elif typ == 0x50: self.g['87D5'] = 0x21; self.damage(victim, 7, 2, self.save(victim, 3))
        else:
            self.g['87D5'] = 16; pct = (10 if not self.g.get('8DC7', 0) else (11-distance)*10) if distance <= 11 else 0
            if pct and self.roll(1, 100) <= pct: self.damage(victim, self.roll(4, 8, True), 2, self.save(victim, 3))  # ov14:29D5..29DB pushes four dice, eight sides.

    def tile(self, x, y, value=None):
        """ov33:0483 CellContents / ov23:2CFB cloud terrain writes."""
        if not (0 <= x < 50 and 0 <= y < 25): return 0
        if value is None:
            if 'terrain' in self.ctx: return self.ctx['terrain'](x, y)
            if self.fight is not None: return self.fight.tiles[y*50+x]
        else:
            if 'set_terrain' in self.ctx: self.ctx['set_terrain'](x, y, value); return value
            if self.fight is not None: self.fight.set_tile(x, y, value); return value
            return value                    # ov07:069C AfterCombat strips cloud effects after the fight: the original writes its stale combat map (DS), rebuilt at the next fight
        raise ValueError('magic requires combat terrain context')

    def at(self, x, y):
        """ov33:0483 occupant lookup; first live footprint owns the cell."""
        if 'at' in self.ctx: return self.ctx['at'](x, y)
        if self.fight is not None and 0<=x<50 and 0<=y<25:
            idx=self.g['combat.occupancy'][50*y+x]-1
            return self.s.chars()[idx] if idx>=0 else None
        for c in self.s.chars():
            if c.b[ACTIVE] and self.position(c) == (x, y): return c
        return None

    def line(self, start, end):
        """ov32:0196/023F exact zero-error Bresenham steps, excluding the start."""
        x, y = start; tx, ty = end; dx, dy = abs(tx-x), abs(ty-y)
        sx, sy, err, out = (tx > x)-(tx < x), (ty > y)-(ty < y), 0, []
        while (x, y) != (tx, ty):
            if dx >= dy:
                x += sx; err += 2*dy
                if err >= dx: err -= 2*dx; y += sy
            else:
                y += sy; err += 2*dx
                if err >= dy: err -= 2*dy; x += sx
            out.append((x, y))
        return out

    def area(self, x, y, radius):
        """ov32:08D1 BuildTargetList, sorted by half-step distance and direction."""
        if 'area' in self.ctx: return self.ctx['area'](x, y, radius)
        if self.fight is not None and hasattr(self.fight, 'targets_from'):
            return self.fight.targets_from(x, y, radius)
        found = []
        for c in self.s.chars():
            if not c.b[ACTIVE]: continue
            if self.fight is not None:
                best=None
                for px,py in self.fight.cells(c):
                    ok,dist=self.fight.walk_line(x,y,px,py,radius)
                    if ok:
                        from sm.titles.ssb.units.combat import in_cone
                        direction=next((d for d in range(8) if in_cone(x,y,px,py,d)),8)
                        candidate=(dist,direction//2,self.index(c),c)
                        if best is None or candidate[:2]<best[:2]: best=candidate
                if best is not None: found.append(best)
                continue
            px, py = self.position(c); dx, dy = abs(px-x), abs(py-y); dist = 2*max(dx, dy)+min(dx, dy)
            if dist > 2*radius+1: continue
            cells = self.line((x, y), (px, py))
            if any(ssb_data.stexe()[0x1A9E+4*self.tile(a,b)] == 255 for a,b in cells): continue
            direction = DIRECTIONS.index(((px>x)-(px<x), (py>y)-(py<y)))
            found.append((dist, direction//2, self.index(c), c))
        return [entry[3] for entry in sorted(found)]

    def adjacent(self, c):
        """ov26:2B70 EnemiesAdjacent used by Bless/Mass Invisibility."""
        if 'adjacent' in self.ctx: return self.ctx['adjacent'](c)
        return [t for t in self.s.chars() if t.b[ACTIVE] and t.b[SIDE] != c.b[SIDE] and self.distance(c,t) <= 1]

    def aim(self, c, targets):
        """ov15:1FA1 target cell DS:8D8B/8D8C; explicit caller aim is preserved."""
        if targets and (self.fight is not None or 'position' in self.ctx):
            self.g['8D8B'], self.g['8D8C'] = self.position(targets[0])
        elif '8D8B' not in self.g:
            self.g['8D8B'], self.g['8D8C'] = self.position(c)

    def pick(self, caster, sid, combat):
        """ov23:1253 party picker; ov15:1FA1/23D5..24E7 combat picker, ov23:0EE1 range."""
        sp = spell(sid); mode=sp[6]&15
        if not combat:
            if sp[7] == 0: return []
            if sp[7] == 1: return [caster]
            if sp[7] == 3: return self.s.chars()
            candidates = self.s.party[:]
        else:
            self.g['8D8B'],self.g['8D8C']=self.position(caster)
            self.g['87DD']=0
            if mode==0: return [caster]
            reach = spell_range(caster, sid, bool(self.g.get('8D99', 0)))
            if self.fight is not None: candidates = self.fight.targets(caster, range=reach)
            else: candidates = [c for c in self.s.chars() if self.distance(caster, c) <= reach]
            # The manual target menu permits an ally, self and recoverable corpses.
            if sid in (75, 113): candidates += [c for c in self.s.chars() if c not in candidates and self.distance(caster,c) <= reach]
            if 8<=mode<=14 or mode==15:
                x, y = self.position(caster)
                cells = [(a,b) for b in range(25) for a in range(50) if max(abs(a-x),abs(b-y))+min(abs(a-x),abs(b-y))//2 <= reach and self.tile(a,b) and ssb_data.stexe()[0x1A9E+4*self.tile(a,b)] != 255]
                if self.fight is not None: cells=[p for p in cells if self.fight.walk_line(x,y,*p,reach)[0]]
                if not cells: return []
                if caster.b[0x1A9]:
                    # ov15:1D7C..1E85: the AI aims through AiPickTarget mode 1 over the spell's reach, never the stored target.
                    target=self.fight.ai_pick_target(caster,False,reach,False) if self.fight is not None else None
                    target=target if target is not None else caster
                    p=self.position(target)
                    if p not in cells: return []
                    selected=cells.index(p)
                else: selected = self.game.ask('TARGET', cells + ['cancel'], spell=sid, caster=self.index(caster), at=0x1FA1)
                if selected == len(cells): return []
                self.g['8D8B'], self.g['8D8C'] = cells[selected]
                victim=self.at(*cells[selected])
                if mode==15 and victim is not None: return [victim]
                self.g['87DD']=1
                return self.area(*cells[selected],mode&7 if mode!=15 else 0) or [None]
            if mode==5 or sid in (23,49,94): candidates=[t for t in candidates if t is not caster]
        if not candidates: return []
        count=(sp[6]&3)+1 if combat else 1
        budget=caster_level(caster,sid) if sid==79 else self.roll(2,4) if combat and mode==5 else 0
        picked=[]; used=0; attempts=0
        ai_slots=combat and caster.b[0x1A9] and mode!=5
        while candidates and (attempts<count if ai_slots else len(picked)<count or combat and mode==5):
            if combat and caster.b[0x1A9]:
                wanted=[c for c in candidates if c.b[SIDE]!=(caster.b[SIDE]) if sp[14]] if sp[14] else [c for c in candidates if c.b[SIDE]==caster.b[SIDE]]
                # ov15:1E78..1E85 ->3C1F..3C6C: even an empty enemy search clears the stored target in mode1.
                if sp[14] and self.fight is not None:                      # ov15:1DED/1E85 as above; sp[14] = 0 aims at the caster (1DF4)
                    target=self.fight.ai_pick_target(caster,False,reach,False)
                    if target is None: break
                else:
                    if not wanted: break
                    target=caster if caster in wanted else wanted[0]
                if ai_slots:
                    attempts+=1  # ov15:245D/24C1: accepted and duplicate AI picks both spend one slot.
                    if target in picked or target not in wanted: continue
                elif target not in wanted: break
            else:
                ids=[self.index(c) for c in candidates]
                # ov15:2415..24A4 (20A2/21A4 for mode 5): self is selectable, then refused.
                # Append it after the old cancel slot so recorded legal answers stay stable.
                rejected = [self.index(caster)] if combat and caster not in candidates and (mode==5 or sid in (23,49,94)) else []
                selected=self.game.ask('TARGET',ids+([None] if not combat else ['done' if picked else 'cancel'])+rejected,spell=sid,caster=self.index(caster),
                                       purpose='party member' if not combat else 'aim', at=0x1253 if not combat else 0x1FA1)
                if selected==len(candidates): break
                if selected>len(candidates):
                    if self.fight is not None: self.fight.refusal(caster, 'Cannot target yourself')
                    continue
                target=candidates[selected]
            picked.append(target)
            if not ai_slots: candidates.remove(target)
            self.g['8D87']=self.index(target)
            if combat: self.aim(caster,[target]); self.put(caster,10,target)
            if combat and mode==5:
                n=target.b[0xE7 if sid==79 else 0xEE]
                used+=(1 if n==1 else 2 if n in (2,3) else 4 if n==4 else 0) if sid==79 else (1 if n<=1 else 2 if n==2 else 4 if n==3 else 8)
                if len(picked)>1 and used>budget or not budget: break  # ov15:215E..216C; 21E1 repeats only while the budget byte is non-zero (oracle 079)
        return picked

    def cone(self, caster, width, length):
        """ov23:1910 ConeTargets: extend sampled axis, clip, collect axis/side lines."""
        start = self.position(caster); end = self.g['8D8B'], self.g['8D8C']
        points = self.line(start, end)
        if not points: return []
        dirs, prev = [], start
        for p in points: dirs.append((p[0]-prev[0],p[1]-prev[1])); prev = p
        # ov23:1979 copies InitLine's accumulated half-step count before extending.
        x,y = end; used, n = sum(3 if dx and dy else 2 for dx,dy in dirs) & 255, 0
        while used < 2*length and 0 < x < 49 and 0 < y < 24:
            dx,dy = dirs[n % len(dirs)]; cost = 3 if dx and dy else 2
            x,y,n,used = x+dx,y+dy,n+1,(used+cost)&255
        x,y = min(49,max(0,x)),min(24,max(0,y))  # ov23:1997..1A39 permits the border step, then clips.
        axis = []; targets = []; duplicate = False; occupied_direction = None; prev = start
        for p in self.line(start,(x,y)):
            axis.append(p)  # ov23:1A5B WalkLine ends ON the first blocking cell (oracle: arena 084, 092 and the breath on turn 4)
            occupant = self.at(*p)
            if occupant is not None:
                if not targets: duplicate = False
                elif occupant in targets: duplicate = True
                if not duplicate: targets.append(occupant)  # ov23:1AC4..1B16 does not clear the duplicate flag after its first hit.
                occupied_direction = DIRECTIONS.index((p[0]-prev[0],p[1]-prev[1]))  # ov23:1ABE..1B1C updates side-line direction only at occupied cells.
            prev = p
            if ssb_data.stexe()[0x1A9E+4*self.tile(*p)] == 255: break
        end = axis[-1] if axis else start  # x1,y1 are by-value parameters: DS:8D8B stays on the aimed cell (live oracle)
        if width == 255: return [c for c in self.area(*end,3) if c is not caster]
        if width in (2,3) and axis:
            prev = axis[-2] if len(axis)>1 else start
            d = occupied_direction if occupied_direction is not None else DIRECTIONS.index((end[0]-prev[0],end[1]-prev[1])); ds=ssb_data.stexe()
            for ox,oy in ((0x0A1A,0x0A22),(0x0A0A,0x0A12))[:width-1]:  # ov23:1BB4 width 2 walks the 0A1A line, 1BD4 width 3 adds 0A0A
                side = min(49,max(0,end[0]+rec.sx(ds[ox+d]))),min(24,max(0,end[1]+rec.sx(ds[oy+d])))
                for p in self.line(start,side):
                    c=self.at(*p)
                    if c is not None and c not in targets: targets.append(c)  # ov23:1899..18FD resets the flag per side-line cell.
        return [c for c in targets if c is not caster]  # ov23:1C74..1C7E excludes the caster only after collecting the list.

    def bolt(self, caster, length, damage, dtype, bounce_bonus, line_damage=None):
        """ov23:3B36/3BE8: aimed occupant first; walls reflect, bonus consumes RANGE."""
        g=self.g; g['87D5']=dtype; start=(g['8D8B'],g['8D8C']); victim=self.at(*start)
        if victim is not None: self.damage(victim,damage,2,self.save(victim,4))
        origin=self.position(caster)
        if origin==start: return
        g['87DD']=1; bounced=False; budget=2*length; direction=1; last=victim; previous_used=0
        display_start=start
        while budget>0:
            end=tuple(start[i]+(start[i]-origin[i])*direction*budget for i in (0,1))
            used=0; previous=start
            for x,y in self.line(start,end):
                used+=3 if x!=previous[0] and y!=previous[1] else 2; previous=(x,y)
                terrain=self.tile(x,y); cost=ssb_data.stexe()[0x1A9E+4*terrain]; target=self.at(x,y)
                if cost==1: bounced=False
                if target is last and terrain and cost<=1 and used<budget: continue
                if target is None and terrain and cost<=1 and used<budget: continue
                if self.fight is not None:
                    self.fight.projectile(caster,(x,y),6,4,50,kind='bolt',start=display_start)  # ov23:3D76..3D8C.
                    display_start=(x,y)
                if not terrain: budget=0
                bounced=bool(terrain and cost==255 and self.s.r0[0xE6]==1 and not bounced)
                if target is not None and target is not last: self.damage(target,damage if line_damage is None else line_damage,2,self.save(target,4))
                last=target
                if bounced:
                    start=(x,y); g['8D8B'],g['8D8C']=start; direction=-direction; last=None
                    dx,dy=abs(x-origin[0]),abs(y-origin[1])
                    if bounce_bonus and 2*max(dx,dy)+min(dx,dy)<=8: used+=8
                    bounce_bonus=0
                # 3E2F: the previous line counter survives a reflection (byte subtraction).
                budget=max(0,budget-((used-previous_used)&255)); previous_used=used
                if bounced or not budget: break
            else: break
        g['87DD']=0

    def make_area(self,caster,typ,duration):
        """ov23:29C5/4F39/5D90: immutable area nodes in State.g, effect param = id*16+level."""
        g=self.g; g['87DD']=1; owner=self.index(caster); nodes=list(g.get('magic.areas',()))
        idx=sum(n[0]==owner and n[1]==typ for n in nodes); x,y=g['8D8B'],g['8D8C']
        ds=ssb_data.stexe(); dirs=ds[0x34A0:0x34A4] if typ==0x28 else ds[0x34A4:0x34AD] if typ==0x5B else (8,)
        tile={0x28:0x1D,0x5B:0x1B,0x64:0x1A}[typ]; cells=[]; hits=[]
        for d in dirs:
            dx,dy=DIRECTIONS[d]; px,py=x+dx,y+dy
            if not (0<=px<50 and 0<=py<25): continue
            old=self.tile(px,py); hit=self.at(px,py)
            # Both cloud constructors require an occupant, as the compiled code does.
            used=hit is not None and ssb_data.stexe()[0x1A9E+4*old]!=255
            for node in nodes:
                prior=next((z[2] for z in node[5] if z[:2]==(px,py) and z[3]),None)
                if prior is not None: old=prior; break
            if old in (0x1C,0x1E):
                body=next((b for b in g.get('combat.bodies',()) if tuple(b[1:3])==(px,py)),None)
                if body is not None: old=body[3]
            cells.append((px,py,old,int(used)))
            if used: self.tile(px,py,tile)
            if hit is not None and (typ==0x5B or hit not in hits): hits.append(hit)
        level=caster_level(caster,g['87D8'],g.get('8D99',0))
        self.add(caster,typ,duration,(idx<<4)+level,True)
        nodes.append((owner,typ,idx,x,y,tuple(cells),0)); g['magic.areas']=tuple(nodes)
        self.tell(caster, {0x28:'Creates a noxious cloud',0x5B:'Creates a poisonous cloud',
                           0x64:'Sets a delayed blast fireball.'}[typ], delay=0 if self.fight is not None else None)  # ov23:2D7F NameMessage, then 2D92 RedrawMap and 2D97 MessageDelay: the hold sits on the area redraw below (gt3000/034).
        if self.fight is not None:
            self.fight.show('area',caster,self.g.get('67D6',0)/10,focus=(x,y),margin=0)
            self.fight.show('clear',caster)
        if typ!=0x64:
            for hit in hits: self.hazard(hit,typ)

    def hazard(self,c,typ):
        """ov25:0C52 terrain hazards, g1: nausea and Cloud Kill level thresholds."""
        b=c.b
        if not b[ACTIVE]: return
        if typ==0x28:
            if b[0xF2] or b[0x15E]&8 or self.find(c,0x1F) is not None or self.find(c,0x63) is not None: return
            saved=self.save(c,0); effect=0x1E if saved else 0x1F
            e=self.effect(c,effect,1 if saved else self.roll(1,4)+1,255,text='starts to cough' if saved else 'chokes and gags from nausea')  # ov25:0CED..0E57, oracle 034
            if e is not None: self.callback(c,e)
        elif b[0xEE]<5 or b[0xEE] in (5,6) and not self.save(c,0,-4 if b[0xEE]==5 else 0):
            self.add(c,0x37,0,255); self.kill(c)

    def clear_area(self,c,e,blast=False):
        """ov14:1096/2C4E/30B1 removal restores terrain and repaints overlapping areas."""
        nodes=list(self.g.get('magic.areas',())); key=(self.index(c),e[0],e[3]//16)
        node=next((n for n in nodes if n[:3]==key),None)
        if node is None: return
        if blast and self.fight is not None:
            # ov14:3212..330C consumes the last DS:8E1A buffer (possibly changed since casting).
            sprites=getattr(self.game,'presentation_sprites',())
            for phase in range(4):
                picture=dict(sprite=sprites[phase % len(sprites)][0],mirror=sprites[phase % len(sprites)][1]) if sprites else {}
                self.fight.show('area',c,(70+30*phase)/1000,**picture,point=node[3:5],focus=node[3:5],margin=0,
                                bottom='Delayed Blast Fireball goes off' if phase else '')
        targets=self.area(node[3],node[4],3) if blast else []
        for x,y,old,used in node[5]:
            corpse=any(tuple(b[1:3])==(x,y) for b in self.g.get('combat.bodies',()))
            if used: self.tile(x,y,(0x1C if c.b[STATUS]==7 else 0x1E) if corpse else old)
        nodes.remove(node); self.g['magic.areas']=tuple(nodes)
        for n in sorted(nodes,key=lambda z:{0x5B:0,0x28:1,0x64:2}[z[1]]):
            for x,y,old,used in n[5]:
                if used: self.tile(x,y,{0x5B:0x1B,0x28:0x1D,0x64:0x1A}[n[1]])
        if self.fight is not None: self.fight.show('area',c,focus=node[3:5],margin=0)
        if blast:
            g=self.g; g['87DD']=1; g['8D8B'],g['8D8C']=node[3:5]; g['87D5']=9
            lv=c.b[0x116]+c.b[0x11D]*rec.dual(c); dmg=lv+self.roll(lv,6,True)
            g['8C66']=len(targets); g['magic.targets']=tuple(self.index(t) for t in targets)
            for t in targets: self.damage(t,dmg,2,self.save(t,4))
            g['87D5']=0

    def cure(self,c):
        """ov23:2FBD CureHelper; suppress recursive disease effects while removing."""
        self.g['87DC']=1; removed=False
        for typ in (0x1F,0x22,0x2B,0x2C): removed=self.remove(c,typ) or removed
        if removed: recalc_ability(self.game,c,0)
        self.g['87DC']=0; return removed

    def side_limited(self,caster,sid,targets,opposite,side):
        """ov23:39DE Haste/Slow: level-limited side filter and cancellation."""
        self.g['87DD']=1; left=caster_level(caster,sid); kept=[]
        for t in targets:
            if t is not None and t.b[SIDE]==side and left:
                left-=1
                if not self.remove(t,opposite): kept.append(t)
        self.apply(caster,sid,kept)
        for t in kept: self.modifiers(t,18)

    def area_effect(self,caster,sid,targets,bonus=0):
        """ov23:1CC8 reverse target order; last Charm Monsters/Faerie Fire entry exempt."""
        sp=spell(sid)
        for i in range(len(targets)-1,-1,-1):
            t=targets[i]
            if t is None: continue
            if self.fight is not None and i != len(targets)-1:
                self.fight.projectile(caster,self.position(t),cue='cast')  # ov23:1D2F PlayOrStopSound(19CA), 1D37 LoadSprite(12h), 1D7A Projectile per extra target.
            saved=True if sid in (79,81) and i==len(targets)-1 else self.save(t,sp[9],bonus)
            if sid in (23,49) and t.b[0x6B] in (0,7): saved=True
            if not saved: self.effect(t,sp[10],self.duration(sid,caster),caster_level(caster,sid),sid==81,sp[8],saved,self.effect_text(sid))

    def dispatch(self,caster,sid,targets):
        """ov23:1F0D..619A complete spell table; branches cite shared handler entry offsets."""
        t=next((c for c in targets if c is not None),None); g=self.g; lv=caster_level(caster,sid,g.get('8D99',0)); sp=spell(sid)
        if sid in range(101,110) or sid in (31,78): return             # ov23:1F0D/28E9/47FB empty handlers
        if sid in (1,2,116):                                        # ov23:1F14/1F47/6038
            g['87DD']=1; side=caster.b[SIDE] if sid!=2 else int(caster.b[SIDE]==0)
            kept=[c for c in targets if c is not None and c.b[SIDE]==side and not (sid in (1,116) and self.s.mode==5 and self.adjacent(c))]
            self.apply(caster,sid,kept); return
        if sid == 63:                                               # ov23:41C8 RestoreYouth: table DS:8A8E + 4*63 holds its stub 1B0 (init bytes + oracle 063; the decode says no slot)
            age = rec.rdw(caster.b, 0x6E)-self.roll(1,4)-1
            rec.wrw(caster.b, 0x6E, max(age, 18)); self.tell(caster, 'is now 18 years old' if age < 18 else 'becomes younger')
            return
        if sid in (3,58,62,71,98,99):                             # ov23:1F7E/3FEF/414A/4536/5815/5852
            dice,sides,extra={3:(1,8,0),58:(2,8,1),62:(2,4,2),63:(2,4,2),71:(3,8,3),98:(1,8,0),99:(2,4,2)}[sid]
            if t is not None and self.heal(t,self.roll(dice,sides)+extra):
                result = ('is Healed' if sid in (62, 63, 99) else
                          'is fully healed' if t.b[HP] == t.b[0x70] else 'is partially healed')
                self.tell(t,result,1 if sid in (62,63,99) else None)  # ov26:2A75 / ov23:414A.
        elif sid in (4,9,15,20,65,66,72,74,87):                       # ov23:1FBC/209E/23DC/2475/4254/4290/4579/462C/4EB0
            dice,sides,extra,dtype={4:(1,8,0,8),9:(0,1,lv,9),15:((lv+1)//2,4,(lv+1)//2,8),20:(1,8,lv,12),65:(2,4,2,8),66:(2,8,1,8),72:(3,8,3,8),74:(6,8,0,9),87:(3,10,0,10)}[sid]
            dmg=self.roll(dice,sides,True)+extra if dice else extra
            self.apply(caster,sid,targets,damage=dmg,dtype=dtype)
        elif sid in (10,96):                                        # ov23:20D1/56FF charm
            if t is not None and (t.b[0x6B]<7 or t.b[0x15E if sid==10 else 0x15D]&2):
                self.apply(caster,sid,targets,lv+(caster.b[SIDE]<<7),True)
                e=self.find(t,11)
                if e is not None: self.callback(t,e)
            elif t is not None: self.tell(t,'is not Charmed' if sid==96 else 'is Unaffected')
        elif sid in (12,35,59):                                     # ov23:21AF/2E2C/402F strength spells
            if t is None: return
            if sid==12:
                strength,exc=(18,(0,1,51,76,91,100)[lv-1]) if 1<=lv<=6 else (lv+12,0) if 7<=lv<=9 else (22,0) if lv in (10,11) else (23,0)
                p=encode_strength(t,strength,exc)
                if p is not None: self.effect(t,12,self.duration(sid,caster),p,text='is Enlarged'); recalc_ability(self.game,t,0)
                else: self.tell(t,'is Unaffected')
            elif sid==59:
                p=encode_strength(t,21,0)
                self.add(t,0x71,self.duration(sid,caster),p if p is not None else 0,True); recalc_ability(self.game,t,0)
            else:
                b=t.b; die=4
                if b[0x111] or b[0x118]>b[0xEF] or b[0x117] or b[0x11E]>b[0xEF]: die=6
                if b[0x113] or b[0x11A]>b[0xEF]: die=8
                bonus=self.roll(1,die); strength=b[0x11]+bonus; exc=b[0x1C]
                if strength>18:
                    if b[0x113] or b[0x11A]>b[0xEF] or b[0x115] or b[0x11C]>b[0xEF]: exc=min(100,10*(strength-18)+exc)
                    strength=18
                if encode_strength(t,strength,exc) is not None: self.add(t,0x26,self.duration(sid,caster),bonus+100,True); recalc_ability(self.game,t,0)
        elif sid==13:                                              # ov23:22F6 reduce
            if t is not None and not self.save(t,4) and self.remove(t,12):
                recalc_ability(self.game,t,0); self.tell(t,'has been reduced',1)
        elif sid==14: self.apply(caster,sid,targets,self.roll(2,4),True); recalc_ability(self.game,caster,5)  # ov23:2389
        elif sid==21:                                              # ov23:24C8 sleep budget
            g['87DD']=1; budget=self.roll(4,4); kept=[]
            for c in targets:
                if c is None: continue
                hd=c.b[0xEE]; cost=1 if hd<=1 else 2 if hd==2 else 4 if hd==3 else 6 if hd==4 else 10 if hd==5 and c.b[0x6B]==0 else 20
                if c.b[STATUS]!=1 and self.find(c,0x35) is None and budget>=cost: budget-=cost; kept.append(c)
            self.apply(caster,sid,kept)
        elif sid in (23,49,94):                                    # ov23:260A hold, save penalty by target count
            n=len(targets); self.area_effect(caster,sid,targets,(-2 if sid==23 else -3) if n==1 else -1 if n==2 else 0)
        elif sid==26:                                              # ov23:26D9 slow poison
            if t is not None and self.find(t,0x37) is not None:
                if not t.b[HP]: t.b[HP],t.b[STATUS],t.b[ACTIVE]=1,0,1
                self.apply(caster,sid,targets,255,True); self.add(t,15,10,255,True)
        elif sid==27:                                              # ov23:2773 snake charm
            budget=caster.b[HP]; kept=[]
            for c in self.s.chars():
                if c.b[0x15D]&16 and c.b[ACTIVE] and self.find(c,0x33) is None and budget>=c.b[HP]: budget-=c.b[HP]; kept.append(c)
            self.apply(caster,sid,kept)
        elif sid==28:                                              # ov23:2857 spiritual hammer immediate callback
            self.apply(caster,sid,targets,cb=True)
            if t is not None: self.callback(t,bytearray((0x17,0,0,0,0,0,0,0,0)))
        elif sid==32: self.apply(caster,sid,targets,lv | self.roll(1,4)<<4)  # ov23:2916 mirror image
        elif sid in (34,91): self.make_area(caster,0x28 if sid==34 else 0x5B,lv)  # ov23:29C5/4F39
        elif sid in (36,90):                                       # ov23:304E heal; Barkskin shares this entry
            if t is not None:
                if self.cure(t): self.tell(t,'is cured',1)
                if self.remove(t,0x21): self.tell(t,'is no longer blind',1)
                if self.remove(t,0x44):
                    self.tell(t,'regains intellect',1); recalc_ability(self.game,t,1); recalc_ability(self.game,t,2)
                if self.heal(t,max(0,t.b[0x70]-t.b[HP]-self.roll(1,4))): self.tell(t,'is Healed',1)
        elif sid==37:
            if t is not None and self.remove(t,0x21): self.tell(t,'can see',1)  # ov23:31C5.
        elif sid==39:
            if t is not None: self.cure(t)                          # ov23:323B
        elif sid in (41,46):                                       # ov23:3337 dispel repeats targets[1]
            g['87DD']=1
            removed=False
            if t is not None:
                for _ in targets:
                    for e in t.effects[:]:
                        if e[3]!=255 and self.roll(1,100)<=dispel_chance(lv,e[3]&15):
                            self.remove(t,e[0],e); removed=True
                if removed: self.tell(t,'is Affected',1)  # ov23:3443..346C.
            if self.fight is not None or 'position' in self.ctx:
                x,y=g['8D8B'],g['8D8C']
                for node in tuple(g.get('magic.areas',())):
                    if node[6] or not any(abs(a-x)<=1 and abs(b-y)<=1 for a,b,_,_ in node[5]): continue
                    owner=self.s.chars()[node[0]]; other=owner.b[0x116]+owner.b[0x11D]*rec.dual(caster)
                    if self.roll(1,100)<=dispel_chance(lv,other):
                        e=next((e for e in owner.effects if e[0]==node[1] and e[3]//16==node[2]),None)
                        if e is not None: self.remove(owner,e[0],e)
                    else: g['magic.areas']=tuple(n[:6]+(1,) if n==node else n for n in g.get('magic.areas',()))
                if self.fight is not None and g.get('magic.areas'): self.fight.show('area',caster,focus=(x,y))  # ov23:356B..3573 -> 36D5..36E3: RedrawMap only when an area list exists (per cell; gt3000/041: none without areas).
        elif sid==42: self.apply(caster,sid,targets,lv+(caster.b[SIDE]<<4))  # ov23:36F6 prayer
        elif sid in (43,89):                                       # ov23:376B remove curse
            if t is not None:
                if self.remove(t,0x24): self.tell(t,'is un-cursed',1)
                else:
                    it=next((i for i in t.items if i[0x36]),None)
                    if it is not None:
                        it[0x34]=0
                        if it[0x3E]>127:
                            g['8DB8']=1; self.callback(t,it,1)
                            for k in range(6): recalc_ability(self.game,t,k)
                        self.tell(t,'has an item un-cursed',1)
        elif sid in (47,64):                                       # ov23:38E8 fireball
            g['87DD']=1; dice=lv if sid==47 else 2*self.roll(1,3)+1
            if not self.s.r0[0xE6]: targets=self.area(g['8D8B'],g['8D8C'],2)
            if self.fight is not None: self.fight.show('area',caster,focus=(g['8D8B'],g['8D8C']),margin=0)  # ov23:39AD.
            self.apply(caster,sid,targets,damage=self.roll(dice,6,True),dtype=9)
        elif sid in (48,55): self.side_limited(caster,sid,targets,0x2A if sid==48 else 0x27,caster.b[SIDE] if sid==48 else int(caster.b[SIDE]==0))  # ov23:3B00/3EC7
        elif sid in (51,60): self.bolt(caster,7 if sid==51 else 3,self.roll(lv,6) if sid==51 else self.roll(1,6)+20,12 if sid==51 else 4,int(sid==51),None if sid==51 else 20)  # ov23:3E77/40C0
        elif sid==56:                                              # ov23:3F02 harm has no touch/save
            if t is not None: g['87D5']=8; self.effect(t,0x22,0); self.tell(t,'is Diseased'); self.damage(t,t.b[HP]-self.roll(1,4))
        elif sid==57:
            if t is not None and not self.remove(t,0x2A): self.apply(caster,sid,targets)  # ov23:3FA2
        elif sid==67:                                              # ov23:42DF neutralize poison
            if t is not None and t.b[STATUS]!=1 and self.find(t,0x37) is not None:
                if not t.b[HP]: t.b[HP]=1
                for typ in (0x37,0x16,15): self.remove(t,typ)
                t.b[STATUS],t.b[ACTIVE]=0,1
                self.tell(t,'is unpoisoned')
            elif t is not None and t.b[STATUS]!=1: self.tell(t,'is unaffected')
        elif sid==68:                                              # ov23:43E1 poison hook
            self.apply(caster,sid,targets); victim=self.get(caster,10)
            if victim is not None:
                g['87D3']=0x40; self.modifiers(victim,9)
                if g['87D3']==0x40: self.poison(caster)
        elif sid==70:                                              # ov23:447E sticks to snakes
            if t is not None and t.b[0xEE]<6:
                self.tell(caster,'turns sticks into snakes')
                self.apply(caster,sid,targets,lv); e=self.find(t,3)
                if e is not None: self.callback(t,e)
            elif t is not None: self.tell(t,'smashes them flat')
        elif sid==73:                                              # ov23:45B5 dispel evil
            g['87DD'],g['87D5']=0,64; self.effect(caster,4,self.duration(sid,caster)); self.apply(caster,sid,targets)
        elif sid==75:                                              # ov23:4669 raise dead
            if t is not None and t.b[STATUS] in (1,6) and t.b[0x18]>0 and t.b[0x6B]!=1:
                self.remove(t,0x37); t.b[STATUS],t.b[ACTIVE]=0,1; t.b[0x18]-=1; recalc_ability(self.game,t,4); t.b[HP]=1
                self.tell(t,'is raised',1)
        elif sid in (76,111,114):                                   # ov23:4722/5A11/5CD8 slay/disintegrate/stone
            if t is None: return
            g['87D5'],g['87D4']=64,255; self.modifiers(t,9)
            if sid==76 and t.b[0x15E]&8: g['87D4']=0
            if g['87D4']:
                if not self.save(t,4):
                    self.tell(t,{76:'is slain',111:'disintegrates',114:'is turned to stone'}[sid])
                    self.kill(t,7 if sid==114 else 6)
                elif sid==76: g['87D5']=8; self.damage(t,self.roll(2,8,True)+1)
            elif sid==76: self.tell(t,'is Unaffected')
        elif sid in (79,81):                                       # ov23:4805/486A
            self.area_effect(caster,sid,targets)
            if sid==81:
                for c in targets:
                    e=self.find(c,11)
                    if e is not None: self.callback(c,e)
        elif sid==82:                                              # ov23:48F9 confusion cap
            for c in targets[:self.roll(2,8)]:
                if c is not None: self.effect(c,0x23,self.duration(sid,caster),0,False,1,self.save(c,4),self.effect_text(sid))
        elif sid==83:                                              # ov23:49CA dimension door
            if 'move' in self.ctx: self.ctx['move'](caster,g['8D8B'],g['8D8C'])
            elif self.fight is not None: self.fight.place(caster,g['8D8B'],g['8D8C'])
            else: raise ValueError('Dimension Door requires combat move context')
            if self.fight is not None: self.fight.show('move',caster)
            self.tell(caster,'teleports')
        elif sid==84:                                              # ov23:4A63 fear cone
            for c in self.cone(caster,3,6):
                saved=self.save(c,4)
                if not saved: self.effect(c,0x6F,self.duration(sid,caster),0,True,1,saved,'flees in terror'); self.fear(c)
                else: self.tell(c,'is Unaffected')
        elif sid==85:                                              # ov23:4BC9 fire shield
            hot=self.roll(1,10)>5 if caster.b[0x1A9] else self.game.ask('SPELL',['hot','cold'],spell=sid,at=0x4BC9)==0
            self.effect(caster,0x32 if hot else 0x36,self.duration(sid,caster),text='is protected'); self.effect(caster,0x70,self.duration(sid,caster))
        elif sid==86:                                              # ov23:4D7C fumble has two saving throws
            if t is not None:
                g['87D5']=64; saved=self.save(t,4); e=self.effect(t,0x2A if saved else 0x1B,self.duration(sid,caster),text='is Slowed' if saved else 'is Befuddled')
                if not saved and e is not None: self.callback(t,e)
                self.apply(caster,sid,targets,cb=True)
        elif sid==92: self.apply(caster,sid,self.cone(caster,2,max(1,(lv+1)//2)),damage=self.roll(lv,4,True)+lv,dtype=10)  # ov23:5499
        elif sid==93:                                              # ov23:5549 feeblemind class/save rules
            if t is None: return
            b=t.b; cls=b[0x6C]; old=b[0xEC]; adjustment=None
            if cls==4: adjustment=1 if b[0xEE]==8 else 2 if b[0xEE]>=9 else 0
            elif cls==3: adjustment=4 if b[0xEE]>=9 else 0
            elif cls in (5,13,15,16): adjustment=4 if b[0x6B]==6 else 2
            elif cls in (9,10,11): adjustment=2
            if adjustment is not None:
                b[0xEC]=(old+adjustment)&255
                try:
                    self.apply(caster,sid,targets); e=self.find(t,0x44)
                    if e is not None: self.callback(t,e)
                    else: self.tell(t,'is unaffected')
                finally: b[0xEC]=old
            else: self.tell(t,'is unaffected')  # ov23:5687..56AD: flag 0 skips the spell and still answers (oracle 093)
        elif sid==110:                                             # ov23:58E5 death-spell HD budget
            g['87DD'],g['87D5']=1,64; budget=2*self.roll(4,20)
            for c in targets:
                if c is None: continue
                hd=c.b[0xEE]; cost=1 if hd==0 else 2 if hd==1 else 8 if hd<=3 else 16 if hd<=5 or hd==6 and c.b[0x70]<=51 else 20 if hd<=8 else 162
                if not c.b[0x15E]&8 and budget>=cost:
                    budget-=cost; self.tell(c,'drops dead'); self.kill(c)
        elif sid==113:                                             # ov23:5AD5 stone to flesh
            if t is not None and t.b[STATUS]==7:
                t.b[STATUS],t.b[ACTIVE],t.b[HP]=0,1,1
                self.tell(t,'is no longer a statue')  # ov23:5AE8..5B37.
                if self.fight is not None:
                    self.fight.place(t,*self.position(t),restore=True); self.fight.show('move',t)  # ov23:5C03..5C3B.
        elif sid==115:                                             # ov23:5D90 delayed fireball segments
            g['87DD']=1; delay=self.game.ask('NUMBER',None,spell=sid,prompt='Blast Delay in segments (1-50)?',
                                           min=0,max=50,number_prompt=True,at=0x5D90)
            rounds=(delay+5)//10
            if rounds: self.make_area(caster,0x64,rounds)
            else: self.apply(caster,sid,targets,damage=self.roll(lv,6,True)+lv,dtype=9)
        elif sid==117:                                             # ov23:60ED Power Word Stun: zero duration is retained
            if t is not None:
                hp=t.b[HP]; duration=self.roll(4 if hp<=30 else 2 if hp<=60 else 1,4) if 1<=hp<=90 else 0
                self.effect(t,sp[10],duration,lv,False,sp[8],text=self.effect_text(sid))
        else: self.apply(caster,sid,targets,cb=sid==40)              # ov23 shared tails, all remaining table handlers


def spell_range(caster, spell_id, item=False):
    """ov23:0EE1..0F97: base + level*increment/4; item branch divides before multiplying."""
    sp=spell(spell_id)
    n=(sp[2]+(6*(sp[3]//4) if item else caster_level(caster,spell_id)*sp[3]//4))&255
    return 1 if n==255 or n==0 and sp[6] else n


def encode_strength(char, strength, exceptional=0):
    """ov25:1514/149A: only encode an improvement over max STR/exceptional STR."""
    if strength>char.b[0x10] or strength==18 and exceptional>char.b[0x1D]:
        return exceptional+1 if strength==18 else strength+100
    return None


def dispel_chance(level, other):
    """ov23:3285/3337 asymmetrical dispel probability, deliberately not clamped."""
    return 50+5*(level-other) if level>other else 50-2*(other-level)


def cast(game, caster=None, spell_id=0, targets=None, *, combat=False, consume=True, context=None):
    """ov23:1403 CastSpell: choose, target, consume one slot, dispatch, clear spell globals."""
    caster=caster or game.s.selc()
    if caster is None or rec.has_effect(caster,0x44) or not caster.b[ACTIVE] or caster.b[STATUS]==1 or game.s.r0[0xE5]: return False
    legal=legal_spells(caster,combat)
    if not spell_id:
        if not legal: return False
        pick=game.ask('SPELL',legal+['cancel'],caster=_Magic(game).index(caster),at=0x1403)
        if pick==len(legal): return False
        spell_id=legal[pick]
    sp=spell(spell_id)
    if consume and spell_id not in legal: return False
    if not sp[11 if combat else 7]: return False
    m=_Magic(game,context); oldsel=game.s.sel; olditem=m.g.get('8D99',0)
    game.s.sel=m.index(caster); m.g['8D99']=int(not consume)
    try:
        name=bytes(caster.b[1:1 + caster.b[0]]).decode('latin1')
        if combat and getattr(game,'presentation',None) is not None:
            # ov23:6628..66B2, 15CA: original arena 015/00158 has this caption
            # BEFORE Aim (00186); Spell: appears only after the caption clears.
            game.present('message',actor=m.index(caster),delay=game.s.g.get('67D6',0)/10,
                         text=name+'\nCasts a Spell',names=((0,m.index(caster)),),status=True)
            game.present('clear',actor=m.index(caster),spell=spell_id)
        if targets is None:
            while True:  # ov23:15B4..15D7/1725..178A: cancelled combat Aim asks before abandoning the spell.
                targets=m.pick(caster,spell_id,combat)
                if targets or not combat: break
                if caster.b[0x1A9] or game.ask('MENU',['yes','no'],actor=m.index(caster),spell=spell_id,
                        action='abort-spell',prompt='Abort Spell?',cursor=False)==0:  # ov15:3B7F/3B95 erased the Aim cursor.
                    if consume: forget(caster,spell_id)  # ov23:1770..1781: confirmed abort consumes the slot.
                    if m.fight is not None: m.fight.refusal(caster,'Spell Aborted')
                    return True
        else:
            targets=list(targets)
            if combat and targets and targets[0] is not None: m.aim(caster,targets)
        if not targets: return False
        if consume and not forget(caster,spell_id): return False
        message(game, '%s casts %s' % (name, spell_name(spell_id)),actor=m.index(caster),
                display=not combat,names=((0,m.index(caster)),))  # ov23:6628..66B2: combat caption already preceded the picker; retain the successful-cast log.
        if combat and m.fight is not None:
            end=(m.g['8D8B'],m.g['8D8C'])
            from sm.titles.ssb.units.combat import in_cone
            facing=next((d for d in range(9) if in_cone(*m.position(caster),*end,d)),8)  # ov23:160C..1630.
            m.fight.record(caster)[9]=facing  # ov23:1647 -> ov33:0B4A..0B55: e14 stores the cast direction in c.+9 (a self-cast turns the caster north: 005/00176 left-facing pose).
            m.fight.show('clear',caster,merge=True)  # ov26:173F -> ov23:15E8; arena 051-normal/00433: cast caption is gone before the raised pose; 015/00410 shows cursor erase and pose in one frame (LoadSprite ov23:15EB sits between, no flush).
            m.fight.show('swing',caster,pose=1,facing=facing,spell=spell_id,cursor=False)  # ov33:0B47: the pose erases the box, self-cast too (011/00189, 005/00179).
            m.fight.projectile(caster,end,spell=spell_id,facing=facing,separate_redraw=True)  # ov26:1C38 flushes normal icons before flight (001/00409).
            m.fight.show('facing',caster,pose=0,spell=spell_id,merge=tuple(m.position(caster))!=tuple(end))  # ov23:16A7..16DE: flight already restored normal icons; self-cast still needs the separate erase (005/00179).
        m.g['87D8']=spell_id; m.g['8E29']=1
        m.g['8C66']=len(targets); m.g['magic.targets']=tuple(m.index(c) for c in targets)
        m.dispatch(caster,spell_id,targets)
        if combat and getattr(game,'presentation',None) is not None and getattr(game,'presentation_footer',None):
            # ov23:17AA ClearRectangle at the end of CastSpell blanks the Spell: row (y 184..191); gtrace 015 shows it
            # right after the handler's ClearMessage (ov26:1842), in the same frame (arena 015/00511).
            game.presentation_footer=(bytes(320),)*8+tuple(game.presentation_footer[8:])
            if game.presentation and game.presentation[-1]['kind']=='clear' and not game.presentation[-1]['delay']:
                game.presentation[-1]['footer']=game.presentation_footer; game.presentation[-1]['spell_row_cleared']=True
            else:
                game.present('footer',actor=m.index(caster),spell_row_cleared=True)  # ov23:17AA still runs when the last bolt segment hits nobody (051-diagonal/00877).
        return True
    finally:
        m.g['87D8']=m.g['87DD']=0; m.g['8D99']=olditem; game.s.sel=oldsel


def add_effect(game, char, effect_type, duration, param=0, call_on_remove=False):
    """ov25:1235 AddEffect: raw list append, without resistance or deduplication."""
    return _Magic(game).add(char,effect_type,duration,param,call_on_remove)


def remove_effect(game, char, effect_type, effect=None, *, context=None):
    """ov25:00A6 RemoveEffect; callback and derived abilities included."""
    return _Magic(game,context).remove(char,effect_type,effect)


def apply_effect(game, char, effect_type, duration, param=0, call_on_remove=False, save_type=0, saved=False, *, context=None, text=''):
    """ov25:20C8 ApplyEffect; saved with type 2 still applies the effect."""
    return _Magic(game,context).effect(char,effect_type,duration,param,call_on_remove,save_type,saved,text)


def apply_modifiers(game, char, kind, *, context=None):
    """ov25:0466 ApplyModifiers; shared accumulators are the DS-named State.g keys."""
    _Magic(game,context).modifiers(char,kind)


def effect_callback(game, char, effect, mode=0, *, context=None):
    """ov25:0423 EffectCallback; effect record supplied by the caller."""
    _Magic(game,context).callback(char,effect,mode)


def tick_effects(game, char, elapsed=1, *, context=None):
    """ov22:0000 expiry in <=10-minute chunks; callbacks may append the next timer."""
    if elapsed<0: raise ValueError('negative effect time')
    m=_Magic(game,context)
    while elapsed>0:
        step=min(elapsed,10); elapsed-=step
        for e in char.effects[:]:  # ov22:00F2..0156 stops at the original list tail
            if not any(e is live for live in char.effects): continue
            duration=rec.rdw(e,1)
            if not duration: continue
            if duration<=step: m.remove(char,e[0],e)
            else: rec.wrw(e,1,duration-step)


def remove_curse(game, char, *, context=None):
    """ov06:01B2 -> ov23:376B temple treatment bypasses caster/area restrictions."""
    _Magic(game,context).dispatch(char,43,[char])


def saving_throw(game, char, save_idx, bonus=0, *, context=None):
    """ov25:1137 SavingThrow."""
    if not 0<=save_idx<5: raise ValueError('save index must be 0..4')
    return _Magic(game,context).save(char,save_idx,bonus)


def deal_damage(game, char, amount, save_type=0, saved=False, *, context=None):
    """ov25:1D84 DealDamage; returns damage after resistance/save modifiers."""
    return _Magic(game,context).damage(char,amount,save_type,saved)


def heal(game, char, amount, only_if_hurt=False):
    """ov25:21BF HealHP."""
    return _Magic(game).heal(char,amount,only_if_hurt)


def breath_weapon(game, caster, breath, *, context=None):
    """ov23:61AE BreathWeapon: S/h cold/fire cones, max-HP damage, three uses."""
    m=_Magic(game,context)
    if not m.g.get('8DC7',0) or breath[3]>3: breath[3]=3
    if not breath[3]: return False
    if breath[0] not in (0x53,0x68): return False
    old=game.s.sel; game.s.sel=m.index(caster)
    try:
        targets=m.pick(caster,61,True)
        if not targets: return False
        targets=m.cone(caster,3,7 if breath[0]==0x53 else 9)
        if not targets or any(t.b[SIDE]==caster.b[SIDE] for t in targets): return False
        m.tell(caster,'breathes ' + ('Cold' if breath[0]==0x53 else 'Fire'))
        if m.fight is not None:
            from sm.titles.ssb.units.combat import direction_to
            end=m.position(targets[0])
            m.fight.show('clear',caster,status=True)  # ov23:6336 -> ov26:0C8F; complete caption-clear frame precedes pose (sm_n2_seq_monster_turns/29).
            m.fight.record(caster)[9]=direction_to(*m.position(caster),*end)  # ov23:6324/634F -> ov33:0B55 persists facing AFTER the status clear.
            m.fight.show('swing',caster,pose=1)  # ov23:6349..634F; projectile's redraw restores the normal pose.
            m.fight.projectile(caster,end,5,1,30,separate_redraw=True)  # ov23:6354..63A2 -> ov26:1C38; normal pose is complete before flight.
        m.g['87D5']=0x22 if breath[0]==0x53 else 0x21
        for t in targets: m.damage(t,caster.b[0x70],2,m.save(t,3))
        breath[3]-=1; m.reset(caster); return True
    finally: game.s.sel=old


def free_slots(char, spell_id):
    """ov18:0744 FreeSlots counts ready AND pending spells by class and level."""
    sp=spell(spell_id); cls,level=sp[:2]
    if cls>3 or not 1<=level<=7: return 0
    count=sum(1 for n in char.b[MEM:MEM+75] if n and n&127<=117 and spell(n&127)[:2]==sp[:2])
    return max(0,char.b[0x131+7*cls+level]-count)


def clear_marks(char, *, memory=True, scroll=True):
    """ov18:05C9/060C: delete pending memory slots; clear only bit 7 on scroll spells."""
    if memory:
        for i in range(MEM,MEM+75):
            if char.b[i]>127: char.b[i]=0
        char.b[0x69]=0
    if scroll:
        for it in char.items:
            if it[0x2E] in (0x27,0x28):
                for j in range(0x3C,0x3F): it[j]&=127


def memorize(game, caster=None):
    """ov18:0E3D..102F: show pending marks, choose from the grimoire, then review and confirm."""
    caster=caster or game.s.selc()
    if caster is None: return False
    if not caster.b[ACTIVE] or caster.b[STATUS]==1:
        name_message(game,caster,'is in no condition to memorize spells'); return False  # ov18:09AB, mode 2.
    def review(options, at):
        """ov18:0E60..0E70 / 0FC8..0FD8 calls mode5 SpellList before AskYesNo."""
        index = game.s.party.index(caster)
        game.ask('SPELL', ['exit'], purpose='memorize summary', caster=index, at=at)
        return game.ask('SPELL', options, purpose='memorize confirm', caster=index,
                        prompt='Memorize these spells?', at=at)
    changed=False
    if any(n>127 for n in caster.b[MEM:MEM+75]):
        if review(['keep','replace'],0x0E3D)==0: return True
        clear_marks(caster,scroll=False); changed=True
    if not any(caster.b[0x132:0x14E]): name_message(game,caster,'cannot memorize any spells')  # ov18:0F20.
    while any(caster.b[0x132:0x14E]):
        known=[i for i in range(1,118) if caster.b[0x70+i]]
        if not known: break
        game.vm.clear_text()  # ov21:3C63 / ov18:1027 -> ov26:3031 clears the replaced camp panel.
        # Keep the former legal-spell and Done indices; append unavailable rows.
        options=[i for i in known if free_slots(caster,i)]+['done']+[i for i in known if not free_slots(caster,i)]
        choice=options[game.ask('SPELL',options,purpose='memorize',at=0x0F28)]
        if choice=='done': break
        if not free_slots(caster,choice): continue  # ov18:0F79..0FBA loops without marking.
        slot=next(i for i in range(MEM,MEM+75) if not caster.b[i]); caster.b[slot]=choice|128
        caster.b[MEM:MEM+75]=bytes(sorted(caster.b[MEM:MEM+75],key=lambda n:n&127)); changed=True
        game.s.g['8DBE']=0
        game.s.g.pop('magic.rest.%d'%_Magic(game).index(caster),None)
    if any(n>127 for n in caster.b[MEM:MEM+75]):
        if review(['yes','no'],0x0FBD): clear_marks(caster,scroll=False)
    return changed


def scribe_scrolls(caster):
    """ov23:08DD..09EF/0000..0198: identified scroll powers, filtered by class, not knowledge or level."""
    b=caster.b; old=rec.dual(caster); levels=[max(b[0x111+i],old*b[0x118+i]) for i in range(7)]
    powers=[]
    for n,it in enumerate(caster.items):
        if it[0x2E] not in (0x27,0x28): continue
        if rec.has_effect(caster,16) or ((b[0x111] or rec.sx(b[0x118])>rec.sx(b[0xEF])) and rec._T(it,0)==12): it[0x35]&=0xF8
        if it[0x35]&7: continue
        for slot in range(0x3C,0x3F):
            sid=it[slot]&127
            if not 1<=sid<=117: continue
            cls=spell(sid)[0]
            capable=(b[0x15]>8 and (levels[0]>0 or levels[3]>8) if cls==0 else
                     b[0x15]>8 and levels[4]>6 if cls==1 else
                     b[0x13]>8 and (levels[5]>0 or levels[4]>8 or levels[6]>10) if cls==3 else False)
            if not capable: break  # ov23:09B2 stops this scroll at the first incompatible power.
            powers.append((n,slot,sid))
    return powers


def scribe(game, caster=None):
    """ov18:10A7..14EF: browse all readable scrolls; mark legal spells, then review before confirmation."""
    caster=caster or game.s.selc()
    if caster is None: return False
    if not caster.b[ACTIVE] or caster.b[STATUS]==1:
        name_message(game,caster,'is in no condition to scribe any scrolls'); return False  # ov18:09AB, mode 3.
    changed=False
    def review(options, at):
        """ov18:10C5..1112/1487..14D2: mode6 SpellList precedes the Yes-default question."""
        index=game.s.party.index(caster)
        marks=[(n,sid) for n,slot,sid in scribe_scrolls(caster) if caster.items[n][slot]>127]
        game.ask('SPELL',['exit']+marks,purpose='scribe summary',caster=index,at=at)
        return game.ask('SPELL',options,purpose='scribe confirm',caster=index,prompt='Scribe these spells?',at=at)
    if any(it[j]>127 for it in caster.items if it[0x2E] in (0x27,0x28) for j in range(0x3C,0x3F)):
        if review(['keep','replace'],0x10A7)==0: return True
        clear_marks(caster,memory=False); changed=True
    while True:
        marked={it[j]&127 for it in caster.items if it[0x2E] in (0x27,0x28) for j in range(0x3C,0x3F) if it[j]>127}
        powers=scribe_scrolls(caster)
        if not powers: name_message(game,caster,'has no copyable scrolls'); break  # ov18:1181.
        available=lambda sid: not caster.b[0x70+sid] and sid not in marked and caster.b[0x131+7*spell(sid)[0]+spell(sid)[1]]
        eligible=[(n,sid) for n,_,sid in powers if available(sid)]
        options=eligible+['done']+[(n,sid) for n,_,sid in powers if not available(sid)]  # append refused rows; old legal/Done indices stay.
        game.vm.clear_text()
        value=options[game.ask('LIST',options,purpose='scribe',caster=game.s.party.index(caster),at=0x113C)]
        if value=='done': break
        n,sid=value
        if not available(sid):
            message(game,'You already know that spell' if caster.b[0x70+sid] else
                    'You are already scribing that spell' if sid in marked else 'You can not scribe that spell.',bottom=True)
            continue  # ov18:1193..11B9/1235..12F7/1300..1337: refusal leaves the book open.
        n,slot,sid=next(p for p in powers if p[2]==sid)  # ov18:133A..1463 marks the first matching power, even from a later duplicate row.
        caster.items[n][slot]=sid|128; changed=True
        game.s.g.pop('magic.rest.%d'%_Magic(game).index(caster),None)
    if any(caster.items[n][slot]>127 for n,slot,_ in scribe_scrolls(caster)):
        if review(['yes','no'],0x147C): clear_marks(caster,memory=False)
    game.vm.clear_text()  # ov18:14E0..14E6 -> ov26:3031 redraws the caller after the list.
    return changed


def rest_need(char):
    """ov18:0023: 4/6 hours sleep + 15 minutes per pending memorized/scribed spell level."""
    memory=[max(1,spell(n&127)[1]) for n in char.b[MEM:MEM+75] if n>127 and n&127<=117]
    scroll=[spell(it[j]&127)[1] for it in char.items if it[0x2E] in (0x27,0x28) for j in range(0x3C,0x3F) if it[j]>128 and it[j]&127<=117]
    levels=memory+scroll; char.b[0x69]=6 if levels and max(levels)>2 else 4 if levels else 0
    return char.b[0x69]*60+sum(levels)*15


def rest_spells(game,char,minutes):
    """ov22:089C/095E/0B8E/0C3F standalone rest progress; camp may own its countdown instead."""
    if minutes<0: raise ValueError('negative rest time')
    key='magic.rest.%d'%_Magic(game).index(char); g=game.s.g
    if key not in g: rest_need(char)
    remaining,subminute=g.get(key,(char.b[0x69]*60,0)); budget=minutes+subminute; changed=False
    while budget>0:
        if remaining:
            spent=min(remaining,budget); remaining-=spent; budget-=spent
            char.b[0x69]=(remaining+59)//60
            if remaining: break
        pending=next(((it,j,it[j]&127) for it in char.items if it[0x2E] in (0x27,0x28) for j in range(0x3C,0x3F) if it[j]>128 and it[j]&127<=117),None)
        slot=next((i for i in range(MEM,MEM+75) if char.b[i]>127),None)
        if pending is None and slot is None: budget=0; break
        sid=pending[2] if pending else char.b[slot]&127; cost=15*spell(sid)[1]
        if budget<cost: break
        budget-=cost; changed=True
        if pending:
            from sm.titles.ssb.units.camp import consume_scroll
            it,j,sid=pending; char.b[0x70+sid]=1
            consume_scroll(char,next(i for i,v in enumerate(char.items) if v is it),j)
        else: char.b[slot]&=127
    g[key]=(remaining,budget)
    return changed


def test():
    """PORT2 V-check: ov23:1403/ov14:0000 dispatch, formulas and hashed decision replay."""
    from sm.titles.ssb.units import _magic_test as magic_test
    magic_test.check()
