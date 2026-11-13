from sm.titles.ssb import data as ssb_data
from sm import ecl, dax; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char
from sm.pascal import VMBinding
BASE = ecl.BASE
INT, CON, CHA, MEMSPELL, RACE, CLS, HPMAX, SAVE, LVMAIN, UNDEAD, THIEF = 0x13, 0x19, 0x1B, 0x1E, 0x6B, 0x6C, 0x70, 0xE8, 0xEE, 0xF2, 0xF3
MORALE, MONEY, LEVEL, OLDLV, GENDER, ALIGN, XP, XPVAL, XPHP = 0xFF, 0x103, 0x111, 0x118, 0x11F, 0x120, 0x12C, 0x14E, 0x150
STATUS, ACTIVE, SIDE, CTRL, HP, MOVE = 0x1A6, 0x1A7, 0x1A8, 0x1A9, 0x1B5, 0x1B6
ITYPE, IREADY = 0x2E, 0x34
lo = lambda v: v & 0xFF
w16 = lambda v: v & 0xFFFF
sx8 = lambda v: (v & 0xFF ^ 0x80) - 0x80
rdw = lambda b, o: b[o] | b[o + 1] << 8
def wrw(b, o, v): b[o] = v & 0xFF; b[o + 1] = v >> 8 & 0xFF

DECODED, CODEBYTES = {}, {}

def code_bytes(s, cache=None):
    cache = CODEBYTES if cache is None else cache
    k = (s.dataset, s.block)
    if k not in cache: cache[k] = {a for pc, (_, _, n) in ecl.trace(bytes(s.code))[1].items() for a in range(pc, n)}
    return cache[k]

SHOP_OPTIONS = ['done'] + ['buy item type %d' % t for t in range(1, 256)]

class Halt(Exception): pass

def dual(c):
    b = c.b
    return int(b[RACE] == 6 and next((b[LEVEL + i] for i in range(6) if b[LEVEL + i]), 0) > b[0xEF])

def recalc_cha(c):
    b = c.b; v = b[0x1A]
    for it in c.items:
        if it[0x34] and it[0x3E] > 0x80:
            p = it[0x3E] & 0x7F; v += -1 if p == 6 else 1 if p == 8 and it[0x3D] == 5 else 0
    b[0x1B] = lo(v + sum(e[3] for e in c.effects if e[0] == 0x0E))

class NoGeo:
    def load(self, s, m): pass
    def attr(self, s, x, y): return 0
    def wall(self, s, x, y, d): return 0
    def approach(self, s): return 0

class VM:
    def __init__(self, s, ask, geo=None, *, binding=None):
        self.binding = binding or VMBinding(lambda name: dax.load(name, d=ssb_data.SECRET),
                                           ssb_data.stexe, ssb_data.wrapped_text, Char)
        self.decoded = DECODED if binding is None else binding.decoded
        self.codebytes = CODEBYTES if binding is None else binding.codebytes
        self.s, self.ask, self.geo = s, ask, geo or NoGeo()
        self.out, self.flags, self.gosub, self.pc, self.cache = [], [0] * 6, [], BASE, {}
        self.vec, self.resuming, self.steps = [0] * 5, False, 0
        self.display = {'kind': None}
        self.text_start, self.text_epoch = 0, 0
        self.icons = (self.binding.icons(s) if self.binding.icons else
                      {c.b[0x155]: ('CPIC', c.b[0x12B], s.dataset) for c in s.party if c.b[MORALE] >= 0x80})
        self.ops, self.cur = [], 0
        self.slots = [''] * 5; self.strs = self.slots

    @staticmethod
    def region(a):
        return 0 if 0x4B00 <= a <= 0x4EFF else 1 if 0x7C00 <= a <= 0x7FFF else 2 if 0x7A00 <= a <= 0x7BFF else 3 if 0x8000 <= a <= 0x9DFF else 4
    def m0(self, a): return self.s.r0[a - 0x4B00]
    def m1(self, a): return self.s.r1[a - 0x7C00]
    def set0(self, a, v): self.s.r0[a - 0x4B00] = w16(v)
    def set1(self, a, v): self.s.r1[a - 0x7C00] = w16(v)

    def getmem(self, a):
        a, s = w16(a), self.s; r = self.region(a)
        if r == 0: return s.dir if a == 0x4BEA else self.m0(a)
        if r == 1: v = self.charfield(a); return self.m1(a) if v is None else w16(v)
        if r == 2: return s.r2[a - 0x7A00]
        if r == 3: return s.code[a - BASE]
        if a == 0x033D: return s.dir
        return {0xC04B: w16(sx8(s.x)), 0xC04C: w16(sx8(s.y)), 0xC04D: s.dir >> 1 if self.is3d() else s.dir, 0xC04E: s.ahead, 0xC04F: s.attr}.get(a, 0)

    def setmem(self, a, v):
        a, v, s = w16(a), w16(v), self.s; r = self.region(a)
        if r == 0:
            if a == 0x4BE6 and self.m0(a) != v: s.prev_mode, s.mode = s.mode, 4
            self.set0(a, v)
        elif r == 1: self.set1(a, v); self.setcharfield(a, v)
        elif r == 2: s.r2[a - 0x7A00] = v
        elif r == 3:
            s.code[a - BASE] = lo(v); self.cache.clear()
            if not s.g.get('codemod') and a in self.code_addresses(): s.g['codemod'] = 1
        elif a == 0xC04B: s.x = lo(v); self.display['view_dirty'] = True
        elif a == 0xC04C: s.y = lo(v); self.display['view_dirty'] = True
        elif a == 0xC04D: s.dir = (v % 4) * 2; self.display['view_dirty'] = True

    def getstr(self, a):
        a, r = w16(a), self.region(w16(a))
        if a == 0x7C00: c = self.s.selc(); return bytes(c.b[1:1 + c.b[0]]).decode('latin1') if c else ''
        if r == 4: return ''
        out = []
        while len(out) < 255:
            ch = self.getmem(a + len(out)) if r != 1 else self.m1(a + len(out))
            if ch == 0: break
            out.append(chr(lo(ch)))
        return ''.join(out)

    def setstr(self, a, t):
        a, r = w16(a), self.region(w16(a))
        if a == 0x7C00:
            c = self.s.selc()
            if c: t = t[:15].encode('latin1'); c.b[0] = len(t); c.b[1:1 + len(t)] = t
            return
        if r == 4: return
        for i, ch in enumerate(t[:255] + '\0'):
            v = ord(ch) & 0xFF
            if r == 0: self.set0(a + i, v)
            elif r == 1: self.set1(a + i, v)
            elif r == 2: self.s.r2[a + i - 0x7A00] = v
            else:
                self.s.code[a + i - BASE] = v; self.cache.clear()
                if a + i in self.code_addresses(): self.s.g['codemod'] = 1

    def charfield(self, a):
        if self.binding.read_character is not None: return self.binding.read_character(self, a)
        c = self.s.selc(); o = a - 0x7C00
        if o == 0x312: return self.s.dataset
        if o == 0x33E: return self.m1(0x7F3E)
        if c is None: return None
        b = c.b; L = dual(c)
        if 0xA5 <= o <= 0xAC: return b[THIEF + o - 0xA5]
        cls = {0xC9: 5, 0xCA: 0, 0xCB: 6, 0xCC: 2, 0xCF: 3, 0xD0: 4}
        if o in cls: return lo(b[LEVEL + cls[o]] + b[OLDLV + cls[o]] * L)
        if o == 0x100:
            if self.s.g.get('A4D1'): return 0
            return {0: 1, 3: 6, 4: 5, 5: 4, 6: 3, 7: 7, 8: 2}.get(b[STATUS], 0)
        if o == 0x10C: return 0x80 if b[SIDE] == 0 and b[CTRL] else 0x81 if b[SIDE] == 1 else 0
        if o == 0x2CF:
            ch = b[CHA]
            return 0 if ch == 3 else 5 if ch == 4 else 10 if ch == 5 else 15 if ch == 6 else 20 if ch == 7 else 25 if 8 <= ch <= 12 else \
                30 if ch == 13 else 35 if ch == 14 else 40 if ch == 15 else 50 if ch == 16 else 55 if ch == 17 else 60 if 18 <= ch <= 25 else 0
        if o in (0x2B1, 0x2B4): return self.s.sel
        if o in (0xBB, 0xBD, 0xBF, 0xC1, 0xC3, 0xC5): return rdw(b, MONEY + o - 0xBB)
        f = {0x15: lambda: b[INT], 0x18: lambda: b[CON], 0x19: lambda: b[CHA], 0x72: lambda: w16(sx8(b[RACE])),
             0x73: lambda: w16(sx8(b[CLS])), 0x76: lambda: b[HPMAX], 0x9B: lambda: b[SAVE + 1], 0xA0: lambda: w16(sx8(b[LVMAIN])),
             0xB8: lambda: b[MORALE], 0xD6: lambda: w16(sx8(b[GENDER])), 0xD8: lambda: w16(sx8(b[ALIGN])), 0xF7: lambda: rdw(b, XPVAL),
             0xF9: lambda: b[XPHP], 0x10D: lambda: 0, 0x119: lambda: b[HP], 0x11B: lambda: b[MOVE]}.get(o)
        return f() if f else None

    def setcharfield(self, a, v):
        if self.binding.write_character is not None: return self.binding.write_character(self, a, v)
        o, s = a - 0x7C00, self.s
        if o == 0: (v == 0) and s.g.__setitem__('A4B7', 1); return
        if o == 0x312: s.dataset = (lo(v) + 1) // 2; return
        if o in (0x322, 0x324, 0x326):
            if v > 0x80: self.load_wall(v & 0x7F, 1 + ((o - 0x322) >> 1))
            return
        c = s.selc()
        if c is None: return
        b = c.b
        if 0x1B <= o <= 0x65: b[MEMSPELL + o - 0x1B] = lo(v)
        elif o == 0xB8: b[MORALE] = lo(v - 0x32 if v > 0xB2 else v)
        elif o in (0xBB, 0xBD, 0xBF, 0xC1, 0xC3, 0xC5): wrw(b, MONEY + o - 0xBB, v)
        elif o == 0xF7: wrw(b, XPVAL, v)
        elif o == 0xF9: b[XPHP] = lo(v)
        elif o == 0x100 and v == 1: b[STATUS], b[ACTIVE] = 0, 1
        elif o == 0x10C and v in (0, 0x80, 0x81): b[SIDE], b[CTRL] = {0: (0, 0), 0x80: (0, 1), 0x81: (1, 1)}[v]
        elif o == 0x119: b[HP] = lo(v)

    def code_addresses(self): return code_bytes(self.s, self.codebytes)

    def fetch(self):
        c = self.cache if self.s.g.get('codemod') else self.decoded.setdefault((self.s.dataset, self.s.block), {})
        d = c.get(self.pc)
        if d is None: d = c[self.pc] = ecl.decode(self.s.code, self.pc)
        op, ops, npc = d
        if ops is None: raise Halt('opcode %02X at %04X has no handler (VM hangs)' % (op, self.pc))
        self.cur, self.ops, self.next = op, ops, npc
        self.read_strings(ops)

    def read_strings(self, ops):
        k = 0
        for o in ops:
            if o[0] in (0x80, 0x81):
                k += 1
                if k >= len(self.slots): self.slots.append('')
                self.slots[k] = o[3] if o[0] == 0x80 else self.getstr(ecl.word(o))
        self.strs = self.slots
    def a(self, i): return ecl.word(self.ops[i - 1])
    def v(self, i):
        t, l, h, _ = self.ops[i - 1]
        return l if t == 0 else self.getmem(h * 256 + l) if t in (1, 3, 0x80) else h * 256 + l
    def t(self, i): return self.ops[i - 1][0]

    def cmp(self, x, y):
        self.flags = [int(x == y), int(x != y), int(x < y), int(x > y), int(x <= y), int(x >= y)]

    def run(self, addr):
        s = self.s; self.pc = addr; s.stop = 0; self.steps = 0
        while not s.stop and not s.party_dead:
            self.steps += 1
            if self.steps > 200_000: raise Halt('step limit at %04X' % self.pc)
            self.fetch(); self.at = self.pc
            getattr(self, 'op%02X' % self.cur)()
        s.stop = 0

    def load_block(self, n):
        rec = self.binding.records('ECL%d' % self.s.dataset).get(lo(n))
        if rec is None: raise Halt('ECL%d record %d missing' % (self.s.dataset, n))
        self.s.code[:] = bytes(0x1E00); self.s.code[:len(rec) - 2] = rec[2:]; self.cache.clear(); self.s.g.pop('codemod', None)
        self.display = {'kind': None, **{k:v for k,v in self.display.items() if k in ('blank','location','clock')}}

    def init_vm(self):
        s = self.s; self.pc = BASE; self.gosub = []; self.flags = [0] * 6
        s.g['enc_shown'] = 0; self.set1(0x7EE1, 0xFF); self.set1(0x7ED2, 0); self.set1(0x7ED3, 0); self.set0(0x4BE5, 0)
        self.vec = ecl.vectors(s.code)
        if not self.resuming:
            for j in range(0x20): self.set0(0x4C00 + j, 0)
            for j in range(10): self.set1(0x7F79 + j, 0)

    def award_xp(self, excluded):
        from sm.titles.ssb.units import shops
        s = self.s; mask = 0xFFFFFFFF; total = 0
        signed = lambda x: (x & mask) if (x & mask) < 0x80000000 else (x & mask)-0x100000000
        quot = lambda x, n: (1 if signed(x) >= 0 else -1) * (abs(signed(x)) // n)
        boundary = s.g.pop('combat.treasure_boundary', None)
        for index, c in enumerate(s.chars()):
            b = c.b
            if b[SIDE] != 1 or b[STATUS] in (0, 3): continue
            s.g['59C0'] = 1
            if index >= len(s.party):
                for k in range(1, 7): s.treasure_money[k] = (s.treasure_money[k] + rdw(b, MONEY+2*k)) & mask
            total = (total + rdw(b, XPVAL) + rec.sx16(b[0x131]*b[XPHP])) & mask
            if self.m1(0x7EE3) != 1:
                for _, group in shops.groups(c.items):
                    copied = [bytearray(item) for item in group]; copied[0][IREADY] = 0
                    s.treasure_items[:0] = copied
                    if boundary is not None: boundary += len(copied)
        for k, divisor in enumerate((200, 20, 2)): total = (total + quot(s.treasure_money[k], divisor)) & mask
        for k, factor in enumerate((1, 5, 250, 2200), 3): total = (total + s.treasure_money[k]*factor) & mask
        for index, group in shops.groups(s.treasure_items):
            if boundary is not None and index >= boundary: break
            bonus = rec.sx(group[0][0x32])
            if bonus > 0: total = (total + rec.sx16(bonus*400)) & mask
        each = quot(total, self.m1(0x7F3E)-excluded) & mask; s.g['A4BC'] = each
        if self.m0(0x4CF5): return each
        stats = {0: ((0x15, 14),), 2: ((0x11, 15),), 3: ((0x11, 15), (0x15, 15)),
                 4: ((0x11, 15), (0x13, 15), (0x15, 15)), 5: ((0x13, 15),), 6: ((0x17, 15),)}
        for c in s.chars():
            b = c.b; kind = b[CLS]; value = each
            if not b[ACTIVE] or b[STATUS] == 1: continue
            if kind in stats and all(b[o] > limit for o, limit in stats[kind]): value += quot(each, 10)
            elif kind in (8, 10, 11, 12, 13, 14, 16): value = quot(each, 2)
            elif kind in (9, 15): value = quot(each, 3)
            value = (rdw(b, XP) + (rdw(b, XP+2) << 16) + value) & mask
            wrw(b, XP, value); wrw(b, XP+2, value >> 16)
        return each

    def after_combat_sweep(self):
        s = self.s; res = s.g.get('combat.result', 0) & 0xFF
        from sm.titles.ssb.units import magic
        standing = any(c.b[STATUS] in (0, 1) for c in s.party)
        fled = (res == 0x81 or any(c.b[STATUS] == 3 for c in s.party)) and not standing
        if res == 0x81 and not fled: res = int(any(c.b[STATUS] == 3 for c in s.monsters))
        excluded = sum(not c.b[ACTIVE] or c.b[STATUS] == 1 for c in s.party)
        for c in s.party:
            for kind in (0x03, 0x0B, 0x15, 0x17, 0x1B, 0x23, 0x28, 0x1F, 0x33, 0x34, 0x35):
                magic.remove_effect(self.host, c, kind)
        if standing: self.award_xp(excluded)
        turned = [c for c in s.party if c.b[SIDE] == 1]
        keep = []
        for c in s.party:
            if res == 0x80 or any(c is t for t in turned): continue
            b = c.b
            if fled:
                if b[STATUS] == 3: b[STATUS], b[ACTIVE] = 0, 1; keep.append(c)
                continue
            if b[STATUS] == 3: b[STATUS], b[ACTIVE] = 0, 1
            elif b[STATUS] == 5:
                if self.m1(0x7EE6): b[STATUS], b[ACTIVE], b[HP] = 0, 1, 1
                else: b[STATUS] = 4
            elif b[STATUS] == 4:
                if b[HP] > 0 or self.m1(0x7EE6): b[STATUS], b[ACTIVE] = 0, 1; b[HP] = b[HP] or 1
            keep.append(c)
        s.party = keep
        self.set1(0x7F3E, len(keep))
        s.sel = 0
        removed = turned + s.monsters
        self.set1(0x7EC8, sum(1 for m in removed if not m.b[ACTIVE]))
        if removed and not removed[0].b[ACTIVE]: self.set0(0x4CF8, 1)
        if removed: s.g['59C0'] = 1
        s.monsters = []; s.g['monsters'] = 0
        if fled: s.treasure_items, s.treasure_money = [], [0] * 7
        self.set1(0x7EC7, 0x81 if fled else res)
        s.party_dead = int(res == 0x80)

    def unit(self, mod, fn):
        g = getattr(self, 'host', None)
        if not getattr(g, 'engines', False): return False
        self.service(mod, fn); return True

    def service(self, mod, fn, *arguments):
        g = self.host
        if self.binding.service is not None: return self.binding.service(g, mod, fn, *arguments)
        import importlib
        try: m = importlib.import_module('sm.titles.ssb.units.' + mod)
        except ImportError: raise Halt('engines=True but sm.titles.ssb.units.%s is not ported yet' % mod)
        return getattr(m, fn)(g, *arguments)

    def is3d(self): return self.m0(0x4BE6) != 0

    def op00(self):
        s = self.s
        if s.g.get('47E2'): s.sel = s.g.get('47E7', 0); s.g['47E2'] = 0
        s.stop = 1; self.pc = self.next; self.gosub = []
    def op01(self): self.pc = self.a(1)
    def op02(self): self.gosub.append(self.next); self.pc = self.a(1)
    def op03(self):
        self.pc = self.next
        if self.t(1) >= 0x80 or self.t(2) >= 0x80: self.cmp(self.strs[1], self.strs[2])
        else: self.cmp(self.v(1), self.v(2))
    def op04(self):
        self.pc = self.next; x1, x2, op = self.v(1), self.v(2), self.cur
        if op == 6:
            if x2 == 0: raise Halt('runtime error 200: DIVIDE by 0 at %04X' % self.at)
            r = x1 // x2; self.set1(0x7F3F, x1 % x2)
        else: r = x1 + x2 if op == 4 else x2 - x1 if op == 5 else x1 * x2
        self.setmem(self.a(3), r)
    op05 = op06 = op07 = op04
    def op08(self):
        self.pc = self.next; n = lo(self.v(1)); n += n < 0xFF
        self.setmem(self.a(2), lo(self.s.random(n)))
    def op09(self):
        self.pc = self.next
        if self.t(1) >= 0x80: self.setstr(self.a(2), self.strs[1])
        else: self.setmem(self.a(2), self.v(1))
    def op0A(self):
        s = self.s; self.pc = self.next
        if not s.g.get('47E2'): self.roster_highlights = {s.sel}
        s.g['47E2'] = 1; x = lo(self.v(1)); i = x & 0x7F
        if i < len(s.chars()): s.sel = i; s.g['8B6D'] = 0
        else: s.g['8B6D'] = 1
        if x & 0x80 and s.g.get('A4B6') and s.g.get('A4B7') and s.sel < len(s.party):
            s.party.pop(s.sel); s.sel = 0; s.g['A4B6'] = s.g['A4B7'] = 0
            self.roster_highlights = {s.sel}
    def op0B(self):
        s = self.s; self.pc = self.next
        if len(s.monsters) >= 0x3F: return
        rid, cnt = lo(self.v(1)), lo(self.v(2)) or 1
        b = bytearray(self.binding.records('MON1CHA')[rid]); dif = self.m0(0x4CF4)
        if b[SIDE] == 1 and dif < 5:
            b[HP], b[HPMAX] = lo(b[HP] * (dif + 2) // 4), lo(b[HPMAX] * (dif + 2) // 4)
            if not b[HP] or not b[HPMAX]: b[HP] = b[HPMAX] = 1
        it = self.binding.records('MON1ITM').get(rid, b''); ef = self.binding.records('MON1SPC').get(rid, b'')
        items = [it[k:k + 63] + bytes(4) for k in range(0, len(it), 63)]; effs = [ef[k:k + 9] for k in range(0, len(ef), 9)]
        slot = s.g.get('7603', 8); b[0x155] = slot
        self.icons[slot] = ('CPIC', lo(self.v(3)), s.dataset)
        for copy in range(cnt):
            if len(s.monsters) >= 0x3F: break
            s.monsters.append(self.binding.character(b, items if copy == 0 else items[::-1], effs if copy == 0 else effs[::-1], rid))
        s.g['monsters'] = 1; s.g['7603'] = lo(slot + 1)
    def op0C(self):
        self.pc = self.next; self.set1(0x7EC0, self.v(2))
        self.set1(0x7EC1, min(self.m1(0x7EC0), self.geo.approach(self.s)))
        self.display = {'kind': 'SPRIT', 'dataset': self.s.dataset, 'id': lo(self.v(1)), 'pic': lo(self.v(3)), 'frame': self.m1(0x7EC1), 'head': None}
    def op0D(self):
        self.pc = self.next
        if self.m1(0x7EC1) > 0: self.set1(0x7EC1, self.m1(0x7EC1) - 1)
        if self.display.get('kind') == 'SPRIT': self.display = dict(self.display, frame=self.m1(0x7EC1))
    def op0E(self):
        self.pc = self.next; p = lo(self.v(1)); s = self.s
        if p == 0xFF: self.display = {'kind': None}
        elif self.m1(0x7EE1) != 0xFF: self.display = {'kind': 'HEAD_BODY', 'dataset': s.dataset, 'id': p, 'frame': 0, 'head': self.m1(0x7EE1)}
        else: self.display = {'kind': 'BIGPIC' if p >= 0x70 else 'PIC', 'dataset': s.dataset, 'id': p, 'frame': 0, 'head': None}
    def op0F(self): self.pc = self.next; self.setmem(self.a(2), self.ask('NUMBER', None, at=self.at))
    def op10(self):
        self.pc = self.next
        text = (self.ask('STRING', None, at=self.at) or '').strip(' ').upper()
        self.setstr(self.a(2), text or ' ')
    def clear_text(self):
        self.text_start = len(self.out); self.text_epoch += 1; self.text_color = 15

    def op11(self):
        self.pc = self.next
        t = str(self.v(1)) if self.t(1) < 0x80 else self.strs[1]
        if self.cur == 0x12: self.clear_text()
        self.text_color = 10
        self.out.append(t)
    op12 = op11
    def op13(self):
        self.pc = self.next
        if self.gosub: self.pc = self.gosub.pop()
        else: self.op00()
    def op14(self):
        self.pc = self.next; e = self.v(1) == self.v(2) and self.v(3) == self.v(4); self.flags = [int(e), int(not e), 0, 0, 0, 0]
    def op15(self):
        self.pc = self.next; n = lo(self.v(3)); items = self.strs[2:2 + n] if len(self.strs) > n + 1 else self.strs[1:]
        self.setmem(self.a(1), self.ask('MENU', items, at=self.at, prompt=self.strs[1], vertical=1))
    def op16(self):
        self.pc = self.next
        if not self.flags[self.cur - 0x16]:
            self.cur = self.s.code[self.pc - BASE]
            n = ecl.SKIPCOUNT.get(self.cur, ecl.OPS.get(self.cur, ('', 0))[1])
            if n:
                self.ops, self.pc = ecl.operands(self.s.code, self.pc, n); self.read_strings(self.ops)
            else: self.pc += 1
    op17 = op18 = op19 = op1A = op1B = op16
    def op1C(self):
        s = self.s; self.pc = self.next; s.monsters = []; s.g['monsters'] = 0; s.g['A4D5'] = 0; s.g['7603'] = 8
        s.treasure_money, s.treasure_items = [0] * 7, []
        if s.sel >= len(s.party): s.sel = 0
    def op1D(self): raise Halt('PARTY STRENGTH unused in the shipped scripts')
    def op1E(self):
        self.pc = self.next; s = self.s
        key = self.a(1) if self.t(1) == 1 else self.v(1); idn = lo(self.v(2)); k = w16(key - 0x7C00)
        mn, mx, avg, found, tot, n = 0xFF, 0, 0, 0, 0, 0
        ch = s.chars()
        def scan(get):
            nonlocal mn, mx, avg, tot, n
            for c in ch: n += 1; x = get(c); mx = max(mx, x); mn = min(mn, x); tot = w16(tot + x)
            avg = lo(tot // n) if n else 0
        if k == 0x8400: found = int(any(e[0] == idn for c in ch for e in c.effects)); mn = mx = avg = 0
        elif k == 0x19: scan(lambda c: c.b[CHA])
        elif k == 0x72: found = int(any(c.b[RACE] == idn for c in ch))
        elif 0xA5 <= k <= 0xAC: scan(lambda c: c.b[THIEF + k - 0xA5])
        elif k == 0x9F: scan(lambda c: c.b[MOVE])
        elif k in (0xC9, 0xCA, 0xCB, 0xCC, 0xCF, 0xD0):
            cl = {0xC9: 5, 0xCA: 0, 0xCB: 6, 0xCC: 2, 0xCF: 3, 0xD0: 4}[k]
            for c in ch:
                n += 1; lv = sx8(c.b[LEVEL + cl])
                if sx8(c.b[OLDLV + cl]) > lv and dual(c): lv = sx8(c.b[OLDLV + cl])
                if lv >= sx8(idn): mn = lo(lv) if lv < sx8(mn) else mn; mx = lo(lv) if lv > sx8(mx) else mx
                tot = w16(tot + lv)
            avg = lo(int((tot - 0x10000 if tot & 0x8000 else tot) / n)) if n else 0
        else: return
        for i, val in zip((3, 4, 5, 6), (mn, mx, avg, found)): self.setmem(self.a(i), val)
    def op20(self):
        s = self.s; n = lo(self.v(1)); self.set0(0x4BF2, s.block); s.block = n
        self.load_block(n); self.init_vm(); s.stop = s.restart = 1
    def load_wall(self, rid, slot):
        if rid != 0xFFFF:
            blocks = len(self.binding.records('WALLDEF%d' % self.s.dataset)[rid]) // 0x30C
            for i in range(slot - 1, min(3, slot - 1 + blocks)): self.s.walls[i] = 0xFFFF
        self.s.walls[slot - 1] = rid

    def op21(self):
        self.pc = self.next; s = self.s; b = [0, lo(self.v(1)), lo(self.v(2)), lo(self.v(3))]
        ok = lambda x: x not in (0xFF, 0x7F)
        if self.cur == 0x21:
            if ok(b[1]) and self.is3d(): self.set0(0x4BC5, b[1]); self.geo.load(s, b[1]); self.set1(0x7EC9, 0)
        elif b[1] == 0x7F: self.load_wall(0, 1)
        elif self.m0(0x4BE7) and self.m0(0x4BE8):
            self.load_wall(b[1] if b[1] != 0xFF else 0xFFFF, 1)
            if self.m0(0x4BE9):
                for i in (2, 3):
                    if ok(b[i]): self.load_wall(b[i], i)
            else: self.load_wall(b[3] if ok(b[3]) else 0xFFFF, 3)
        else:
            for i in (1, 2, 3): self.load_wall(b[i] if ok(b[i]) else 0xFFFF, i)
    op37 = op21
    def op22(self): raise Halt('PARTY SURPRISE unused in the shipped scripts')
    def op23(self): raise Halt('SURPRISE unused in the shipped scripts')
    def op24(self):
        s = self.s; self.pc = self.next
        if s.monsters:
            self.set1(0x7EC1, min(self.m1(0x7EC1), self.geo.approach(s)))
            if getattr(getattr(self, 'host', None), 'engines', False): self.unit('combat', 'run')
            else: self.set1(0x7ECB, 0); self.ask('COMBAT', ['win'], at=self.at, monsters=len(s.monsters))
            self.after_combat()
        elif self.m0(0x4CFC) == 1: self.set0(0x4CFC, 0); self.unit('shops', 'vault') or self.ask('VAULT', ['done'], at=self.at)
        elif self.m1(0x7F6C) == 1:
            self.set1(0x7F6C, 0)
            while not self.unit('shops', 'shop') and (c := self.ask('SHOP', SHOP_OPTIONS, at=self.at)):
                it = bytearray(67); it[ITYPE] = c; (s.selc() or s.party[0]).items.append(it)
        elif self.m1(0x7EE2) == 1: self.set1(0x7EE2, 0); self.unit('shops', 'temple') or self.ask('TEMPLE', ['done'], at=self.at)
        else: self.after_combat()
        s.mode = 4 if self.is3d() else 3; self.set1(0x7ECA, self.m1(0x7ECA) & 1)
        if s.mode == 4:
            for key in ('clock','location','blank','sky'): self.display.pop(key,None)
            self.display['portrait_hidden']=True
    def after_combat(self):
        s = self.s; engines = getattr(getattr(self, 'host', None), 'engines', False)
        if engines:
            s.g['59C0'] = 0; self.after_combat_sweep(); s.mode = 6
        else: self.set1(0x7EC7, 0); self.set1(0x7EC8, 0)
        for c in s.party: rec.recalc_character(c, self.m1(0x7F72))
        self.set1(0x7F3E, len(s.party))
        if not engines:
            for c in (0x7F70, 0x7F71, 0x7F72, 0x7EE3, 0x7EE6): self.set1(c, 0)
            self.set0(0x4CF5, 0)
        if not engines or not s.party_dead:
            s.treasure_items = [i for i in s.treasure_items if i[ITYPE] not in (0x37, 0x38, 0x39)]
        npc = [c for c in s.party if c.b[MORALE] > 0x7F and c.b[STATUS] == 0]
        shares = sum(c.b[0x100] & 7 for c in npc); total = shares + len(s.party) - len(npc); took = False
        if shares and total:
            for k in range(1, 7):
                if s.treasure_money[k]: s.treasure_money[k] -= s.treasure_money[k] // total * shares; took = True
        if engines and took and not s.party_dead:
            self.clear_text(); ds = self.binding.resident()
            self.ask('MENU', [ds[0xB55:0xB55+ds[0xB54]].decode('cp437')], purpose='npc share',
                     lines=['%s takes and hides %s share.' % (bytes(c.b[1:1 + c.b[0]]).decode('latin1'), 'her' if c.b[0x11F] else 'his') for c in npc if c.b[0x100]])
        if engines and s.party_dead:
            self.clear_text()
            self.ask('MENU', ['Press any key to continue'], purpose='combat defeat')
        elif engines:
            self.clear_text(); ds = self.binding.resident(); prompt = ds[0xB55:0xB55+ds[0xB54]].decode('cp437')
            self.ask('MENU', [prompt], purpose='combat result', experience=0 if self.m1(0x7EC7)==0x81 else s.g.get('A4BC', 0),
                     no_xp=bool(self.m0(0x4CF5)), outcome=('fled' if self.m1(0x7EC7)==0x81 else 'won') if s.g.get('59C0') else '',
                     treasure=bool(s.treasure_items or any(s.treasure_money)))
            if s.treasure_items or any(s.treasure_money): self.unit('shops', 'treasure')
            s.treasure_items = []
        elif not engines and (s.treasure_items or any(s.treasure_money)): self.ask('TREASURE', ['take'], at=self.at)
        if engines:
            for c in (0x7F70, 0x7F71, 0x7F72, 0x7EE3, 0x7EE6): self.set1(c, 0)
            self.set0(0x4CF5, 0)
    def op25(self):
        x, n = lo(self.v(1)), lo(self.v(2)); self.pc = self.next
        if x < n:
            if self.cur == 0x26: self.gosub.append(self.next)
            self.pc = ecl.word(self.ops[2 + x])
    op26 = op25
    def op27(self):
        self.pc = self.next; s = self.s; s.treasure_money = [w16(self.v(i)) for i in range(1, 8)]; t = lo(self.v(8))
        if t < 0x80:
            r = self.binding.records('ITEM%d' % s.dataset).get(t)
            if r is None: raise Halt('TREASURE: ITEM%d record %d missing' % (s.dataset, t))
            s.treasure_items = [bytearray(r[k:k + 63] + bytes(4)) for k in range(0, len(r), 63)][::-1] + s.treasure_items
        elif t != 0xFF:
            from sm.titles.ssb.units.shops import make_treasure_item
            for _ in range(t - 0x80): s.treasure_items.insert(0, make_treasure_item(s, self.rand_item()))
    def rand_item(self):
        R = lambda n: self.s.random(n) + 1; typ = self.s.g.get('ttyp', 0); r1 = R(100)
        if r1 <= 0x1F:
            r2 = R(100)
            if r2 <= 0x14: r = R(10); typ = 6 if r <= 2 else 8 if r <= 6 else 0x46 if r <= 8 else 0x0F if r == 9 else 0x1D
            elif r2 <= 0x2C: typ = (5, 0x0C, 0x1E)[R(3) - 1]
            elif r2 <= 0x3C: r = R(20); typ = 7 if r <= 3 else 0x18 if r <= 6 else 0x16 if r <= 9 else 0x19 if r <= 12 else 0x17 if r <= 14 else 0x1C if r <= 17 else 0x0F
            elif R(4) < 4: r = R(20); typ = 0x12 if r <= 8 else 0x11 if r <= 13 else 0x0D if r == 14 else 0x10 if r == 15 else 0x13 if r <= 18 else 0x14
            else: typ = [typ, 1, 4, 4, 9, 9, 0x0A, 0x0E, 0x47][R(8)]
        elif r1 <= 0x3E: typ = 0x27
        elif r1 <= 0x46: typ = 0x28
        elif r1 <= 0x50: typ = 0x25
        elif r1 <= 0x55: typ = 0x3B
        elif r1 <= 0x5F: r = R(20); typ = 0x1F if r <= 3 else 0x23 if r <= 11 else 0x24 if r <= 16 else 0x20 if r == 17 else 0x21 if r == 18 else 0x22
        else: r = R(6); typ = 0x32 if r <= 2 else 0x2F if r <= 4 else 0x34 if r == 5 else 0x35
        self.s.g['ttyp'] = typ; return typ
    def op28(self):
        self.pc = self.next; s = self.s; f, pct0 = 100 - lo(self.v(2)), lo(self.v(3))
        for c in (s.chars() if lo(self.v(1)) else [s.selc()]):
            if not c: continue
            for k in range(7): wrw(c.b, MONEY + 2 * k, rdw(c.b, MONEY + 2 * k) * f // 100)
            keep, pct = [], pct0
            for it in c.items:
                w = it[0x37] | it[0x38] << 8
                if w > 0xFF: pct = max(pct - 90, 0)
                elif w > 0x18: pct = max(pct - 50, 0)
                if s.random(100) + 1 > pct: keep.append(it)
            if len(keep) != len(c.items):
                c.items = keep; rec.recalc_character(c, self.m1(0x7F72))
    def op29(self):
        self.pc = self.next; dest = self.a(4); react = [lo(self.v(i)) for i in range(5, 10)]; flee = lo(self.v(13))
        sprite, picture, texts = lo(self.v(1)), lo(self.v(3)), list(self.strs[1:4])
        mn = self.s.party[0].b[MOVE] if self.s.party else 0
        for c in self.s.party: mn = min(mn, rec.compute_move(c, self.m1(0x7F72)) // 2)
        self.set1(0x7EC0, self.v(2)); self.set1(0x7EC1, min(self.m1(0x7EC0), self.geo.approach(self.s)))
        def show():
            self.display = {'kind': 'SPRIT', 'dataset': self.s.dataset, 'id': sprite, 'pic': picture, 'frame': self.m1(0x7EC1), 'head': None}
        def say(text, wait=False):
            self.clear_text(); self.text_color = 10; self.out.append(text)
            if wait: self.hold(len(text) * 3 * self.s.g.get('67D6', 0) / 1000)
        def appr(): self.set1(0x7EC1, self.m1(0x7EC1) - 1); show()
        show()
        while True:
            d0 = self.m1(0x7EC1) == 0; pmenu = d0 or not self.is3d()
            order = {0: (0, 1, 2), 1: (1, 2, 0), 2: (2, 0, 1)}.get(self.m1(0x7EC1), ())
            text = next((texts[k] for k in order if texts[k]), '')
            if text: say(text)
            ch = self.ask('MENU', ['COMBAT', 'WAIT', 'FLEE', 'PARLAY' if pmenu else 'ADVANCE'], at=self.at, encounter=1)
            if pmenu and ch == 3: ch = 4
            r = react[ch] if ch < 5 else 0xFF; again = False
            if r == 0: self.setmem(dest, 2 if ch == 2 and mn >= flee else 1)
            elif r in (1, 3):
                if ch == 0: self.setmem(dest, 1)
                elif ch == 2: self.setmem(dest, 2)
                elif ch == 4 and d0: self.setmem(dest, 3)
                elif ch == 1 and r == 1: say('Both sides wait.', True); again = True
                else: (appr() if not d0 else say('Both sides wait.', True)); again = True
            elif r == 2:
                self.setmem(dest, 0 if ch else 1)
                if ch: say('The monsters flee.')
            elif r == 4:
                if ch == 0: self.setmem(dest, 1)
                elif ch == 2: self.setmem(dest, 2)
                elif d0: self.setmem(dest, 3)
                else: appr(); again = True
            if not again: return
    def op2A(self): self.pc = self.next; self.setmem(self.a(3), self.getmem(self.a(1) + lo(self.v(2))))
    def op2B(self):
        self.pc = self.next; n = lo(self.v(2)); opts = self.strs[1:1 + n]; destination = self.a(1)
        choices = opts + (['char-up', 'char-down', 'char-first'] if len(self.s.party) > 1 and getattr(getattr(self, 'host', None), 'engines', False) else [])
        while True:
            answer = self.ask('MENU', choices, at=self.at)
            if answer < n: break
            previous = self.s.sel
            self.s.sel = 0 if answer == n+2 else (self.s.sel + (-1 if answer == n else 1)) % len(self.s.party)
            if self.s.g.get('47E2') and hasattr(self, 'roster_highlights'):
                self.roster_highlights.discard(previous); self.roster_highlights.add(self.s.sel)
        self.setmem(destination, self.hotkey(opts, answer))
    @staticmethod
    def hotkey(opts, i):
        keys = [o[:1].upper() for o in opts]
        return keys.index(keys[i]) if keys[i] else i
    def op2C(self):
        self.pc = self.next; resp = [self.v(i) for i in range(1, 6)]
        self.setmem(self.a(6), resp[self.ask('PARLAY', ['HAUGHTY', 'SLY', 'NICE', 'MEEK', 'ABUSIVE'], at=self.at)])
    def op2D(self):
        self.pc = self.next; s = self.s; i = self.a(1)
        if i == 0x2DCB:
            s.attr = self.geo.attr(s, s.x, s.y); s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
            if self.display.get('kind') or self.display.get('view_dirty'):
                self.display = {'kind': None, 'sky': s.r0[0xFD:0xFF]}
                self.paint_location()
        elif i == 0xC01E: self.step()
        elif i not in (0xB203,): raise Halt('CALL id %04X: no case' % i)
    def step(self):
        s = self.s; dx, dy = {0: (0, -1), 2: (1, 0), 4: (0, 1), 6: (-1, 0)}[s.dir]
        s.x, s.y = (s.x + dx) & 15, (s.y + dy) & 15; s.attr = self.geo.attr(s, s.x, s.y); s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
    def damage_wait(self, page=False):
        ds=self.binding.resident(); prompt='Press any key to continue' if page else ds[0xB55:0xB55+ds[0xB54]].decode('cp437')
        self.ask('MENU' if getattr(self.host,'engines',False) else 'ACK', [prompt],
                 at=self.at, purpose='script damage', page=page, defeated=bool(self.s.party_dead))

    def script_damage(self, character, amount):
        b=character.b
        if b[STATUS] in (6,7): return
        name=bytes(b[1:1+b[0]]).decode('latin1')
        text=name+(' dies. ' if b[HP]+10<amount else ' is hit FOR %d points of Damage.'%amount)
        lines=self.binding.wrapped_text(''.join(self.out[self.text_start:])) or ['']
        if self.display.get('damage_prefix',(None,))[0]!=self.text_epoch:
            self.display['damage_prefix']=(self.text_epoch,len(lines),getattr(self,'text_color',15))
        for line in self.binding.wrapped_text(text):
            if len(lines)>=6:
                self.damage_wait(page=True); self.clear_text(); lines=[]
            self.out.append(('\n' if lines else '')+line); lines.append(line); self.text_color=15
        damage=lo(amount); hp=max(0,b[HP]-damage); over=max(0,damage-b[HP])
        if over>9 or hp==0 and b[STATUS]==1: b[STATUS]=6
        elif over:
            b[STATUS]=5
            if self.s.mode==5:
                from sm.titles.ssb.units.magic import _Magic
                _Magic(self.host).put(character,14,over)
        elif hp==0: b[STATUS]=4
        if b[STATUS] not in (0,1):
            b[ACTIVE]=0; b[HP]=0
            if self.s.mode==5:
                from sm.titles.ssb.units.magic import _Magic
                self.s.g['87CC' if b[SIDE]==0 else '87CD']=lo(self.s.g.get('87CC' if b[SIDE]==0 else '87CD',0)-1)
                _Magic(self.host).put(character,3,0)
        else: b[HP]=hp
        self.display['location_hidden']=True

    def op2E(self):
        from sm.titles.ssb.units.magic import _Magic
        self.pc=self.next; s=self.s; selected=s.sel; m=_Magic(self.host)
        flags,dice,sides,extra,save=(lo(self.v(i)) for i in range(1,6))
        chars=s.chars(); all_targets=bool(flags&0x40)
        random_target=m.roll(1,lo(self.m1(0x7F3E))) if not all_targets else 0
        if flags&0x80:
            bonus=flags&0x1F; save_index=save&7
            targets=chars if all_targets else [s.selc()] if save&0x80 else [chars[max(0,random_target-1)]]
            for target in targets:
                amount=m.roll(dice,sides)+extra
                no_save=bool(flags&0x20) if all_targets else bool(save&0x80 and save_index==0)
                saved=False if no_save else m.save(target,save_index-1 if save&0x80 and not all_targets else save_index,bonus)
                if not saved or flags&0x10: self.script_damage(target,amount)
        else:
            for _ in range(flags):
                amount=m.roll(dice,sides)+extra
                target=chars[max(0,m.roll(1,lo(self.m1(0x7F3E)))-1)]
                s.g['87DF']=m.roll(1,20)
                if s.g['87DF']==1: continue
                if s.g['87DF']==20: s.g['87DF']=100
                m.modifiers(target,16)
                if sx8(s.g['87DF'])>=0 and sx8(s.g['87DF'])+save>target.b[0x1AB]: self.script_damage(target,amount)
        s.party_dead=int(not any(c.b[ACTIVE] for c in chars)); s.sel=selected
        if s.party_dead:
            self.clear_text(); self.text_color=10; self.out.append('The entire party is killed!')
            queue=getattr(self.host,'presentation',None)
            if queue is not None: queue.append(dict(kind='script-death',delay=3,text=self.out[-1]))
        self.damage_wait()
    def op2F(self):
        self.pc = self.next; r = lo(self.v(1) & self.v(2)) if self.cur == 0x2F else lo(self.v(1) | self.v(2))
        self.cmp(0, r); self.setmem(self.a(3), r)
    op30 = op2F
    def op31(self): raise Halt('SPRITE OFF unused in the shipped scripts')
    def op32(self):
        self.pc = self.next; idn = lo(self.v(1)); f = any(i[ITYPE] == idn for c in self.s.chars() for i in c.items)
        self.flags = [int(f), int(not f), 0, 0, 0, 0]
    def op33(self): self.pc = self.next; self.out.append('\n')
    def op34(self):
        self.display.setdefault('clock', self.s.r0[0xC6:0xCD])
        self.pc = self.next; self.advance_clock(self.v(1), self.v(2))
    def advance_clock(self, amount, unit):
        s = self.s; lim = (10, 10, 6, 24, 30, 12, 100); t = s.r0[0xC6:0xCD]
        for _ in range(amount):
            t[unit] += 1
            for i in range(7):
                if t[i] >= lim[i]:
                    if i < 6: t[i + 1] += 1; t[i] -= lim[i]
                    else:
                        t[6] -= 100
                        for c in s.party: wrw(c.b, 0x6E, rdw(c.b, 0x6E) + 1)
        s.r0[0xC6:0xCD] = t
        mins = amount
        for u in range(unit, 1, -1): mins *= lim[u - 1]
        if getattr(getattr(self, 'host', None), 'engines', False):
            from sm.titles.ssb.units import magic
            for c in s.party: magic.tick_effects(self.host, c, mins)
            return
        for c in s.party:
            keep = []
            gone = set()
            for e in c.effects:
                d = e[1] | e[2] << 8
                if d == 0: keep.append(e)
                elif d > mins: e[1:3] = (d - mins).to_bytes(2, 'little'); keep.append(e)
                else: gone.add(e[0])
            c.effects = keep
            if 0x0E in gone: recalc_cha(c)
            if gone & {0x0C, 0x26, 0x71}: c.b[0x11], c.b[0x1C] = c.b[0x10], 0
    def op35(self): self.pc = self.next; self.setmem(self.a(2) + self.v(3), self.v(1))
    def op36(self):
        self.pc = self.next; s = self.s
        if self.m1(0x7F3E) > 7: return
        rid = lo(self.v(1)); b = bytearray(self.binding.records('MON1CHA')[rid]); b[0x12B] = rid
        it = self.binding.records('MON1ITM').get(rid, b''); ef = self.binding.records('MON1SPC').get(rid, b'')
        b[MORALE] = lo(self.v(2) >> 1 | 0x80)
        c = self.binding.character(b, [it[k:k + 63] + bytes(4) for k in range(0, len(it), 63)], [ef[k:k + 9] for k in range(0, len(ef), 9)])
        if self.binding.records('MON1CHA')[rid][MORALE] > 0x7F: rec.recalc_levels(c)
        c.b[0x155] = next(i for i in range(8) if all(p.b[0x155] != i for p in s.party))
        self.icons[c.b[0x155]] = ('CPIC', {0x32: 0x4D, 0x33: 0x4C, 0x34: 0x42}.get(rid, rid) if s.g.get('67E9') else rid, s.dataset)
        s.party.append(c); s.sel = len(s.party) - 1; self.set1(0x7F3E, self.m1(0x7F3E) + 1)
        rec.recalc_character(c, self.m1(0x7F72))
    def op38(self):
        self.pc = self.next; s = self.s; p = lo(self.v(1))
        if s.g.get('47E2'): s.sel = s.g.get('47E7', 0); s.g['47E2'] = 0
        if p == 0: self.unit('creation', 'run') or self.ask('CREATE', ['continue'], at=self.at)
        elif p == 9:
            pc = self.pc; self.host.camp(); self.pc = pc
            if self.m0(0x4C38) == 0: self.op00()
    def op39(self):
        self.pc = self.next; s = self.s; s.g['A4D1'] = 0
        self.clear_text()
        names = [bytes(c.b[1:1 + c.b[0]]).decode('latin1') for c in s.party]
        s.sel = self.ask('WHO', names, at=self.at, prompt=self.strs[1] if len(self.strs) > 1 else '')
    def hold(self, seconds):
        queue = getattr(getattr(self, 'host', None), 'presentation', None)
        if queue is None: return
        import copy; from types import SimpleNamespace
        s = self.s; shot = copy.copy(s); shot.r0, shot.party = type(s.r0)(s.r0), list(s.party)
        queue.append(dict(kind='script-hold', delay=seconds, text=''.join(self.out[self.text_start:]), colour=getattr(self, 'text_color', 15),
                          scene=SimpleNamespace(s=shot, vm=SimpleNamespace(display=dict(self.display)),
                                                geo=SimpleNamespace(map=getattr(self.geo, 'map', None)))))
    def op3A(self):
        self.pc = self.next; self.hold(self.s.g.get('67D6', 0) / 10)
    def op3B(self):
        self.pc = self.next; idn = lo(self.v(1)); k, n = 0xFF, 0
        for j, c in enumerate(self.s.chars()):
            hit = [q for q in range(75) if c.b[MEMSPELL + q] == idn]
            if hit: k, n = hit[0], j; break
        else: n = max(len(self.s.chars()) - 1, 0)
        self.setmem(self.a(2), k); self.setmem(self.a(3), n)
    def op3C(self): self.pc += 1
    def op3D(self):
        self.pc = self.next; self.clear_text()
        self.display.pop('portrait_hidden',None)
        self.display.update(blank=True,clock=self.s.r0[0xC6:0xCD]); self.paint_location()
        if self.display.get('kind')=='BIGPIC': self.display['kind']=None
    def paint_location(self):
        s = self.s; fixed = s.r0[0x1FD] != 255
        self.display['location'] = (s.r0[0x1FD] if fixed else s.x, s.r0[0x1FE] if fixed else s.y,
            (s.dir + s.r0[0x1FF] * (2 if s.r0[0xE6] else 1)) % 8)
    def op3E(self):
        self.pc = self.next; s = self.s
        if s.sel < len(s.party):
            s.party.pop(s.sel); s.sel = s.sel if s.sel < len(s.party) else 0; self.set1(0x7F3E, self.m1(0x7F3E) - 1)
            s.g['47E7'] = s.sel
    def op3F(self): raise Halt('FIND SPECIAL unused in the shipped scripts')
    def op40(self):
        self.pc = self.next; idn = lo(self.v(1))
        for c in self.s.chars(): c.items = [i for i in c.items if i[ITYPE] != idn]; rec.recalc_character(c, self.m1(0x7F72))
    def op41(self):
        self.pc = self.next; s = self.s; amt, mode = self.v(2), self.v(1); c = s.selc()
        if mode or c is not None:
            who = 'the party' if mode else bytes(c.b[1:1 + c.b[0]]).decode('latin1')
            self.clear_text(); self.text_color = 10; self.out.append('Congratulations %s gains experience!' % who)
            self.hold(s.g.get('67D6', 0) / 10)
        for c in (s.party if mode else [c]):
            if c is None: continue
            n = sum(1 for k in range(7) if c.b[LEVEL + k]) or 1
            if c.b[ACTIVE]: x = int.from_bytes(c.b[XP:XP + 4], 'little') + amt // n; c.b[XP:XP + 4] = (x & 0xFFFFFFFF).to_bytes(4, 'little')

def test_slots():
    from sm.titles.ssb.state import State
    vm = VM(State(), lambda *a, **k: 0)
    vm.ops = [(0x80, 3, 0, 'ABC'), (0x80, 3, 0, 'XYZ')]; vm.slots[1:3] = ['ABC', 'XYZ']
    code = bytearray(0x1E00); code[0:3] = bytes([3, 1, 0]) ; code[3] = 0x7C
    code[4:7] = bytes([0x80, 0, 0]); vm.s.code[:] = code; vm.pc = BASE; vm.fetch()
    assert vm.slots[1] == '' and vm.slots[2] == 'XYZ', vm.slots[:3]
    vm.op03(); assert vm.flags[1] == 1

def test_mode_change():
    from sm.titles.ssb.state import State
    vm = VM(State(), lambda *a, **k: 0); s = vm.s
    for old, value in ((0, 1), (1, 0)):
        s.mode, s.prev_mode = 2, 7; vm.set0(0x4BE6, old); vm.setmem(0x4BE6, value)
        assert (s.prev_mode, s.mode, vm.m0(0x4BE6)) == (2, 4, value)
        s.mode = 3; vm.setmem(0x4BE6, value)
        assert (s.prev_mode, s.mode) == (2, 3)

def test_skip_slots():
    from sm.titles.ssb.state import State
    for code, end, slots in (([0x11, 0x80, 3, 4, 0x20, 0xC0], 6, ['ABC', 'old2']),
                              ([0x03, 0x81, 0, 0x7A, 0x80, 0], 6, ['CELL', '']),
                              ([0x09, 0, 7, 2, 1, 0], 6, ['old1', 'old2']),
                              ([0x34, 0x80, 3, 4, 0x20, 0xC0, 0, 1], 6, ['ABC', 'old2']),
                              ([0x2B, 0x80, 3, 4, 0x20, 0xC0], 1, ['old1', 'old2'])):
        vm = VM(State(), lambda *a, **k: 0); vm.s.g['codemod'] = 1
        vm.setstr(0x7A00, 'CELL'); vm.s.code[:len(code)] = bytes(code)
        vm.slots[1:3] = ['old1', 'old2']; vm.cur = 0x16; vm.next = BASE
        vm.op16()
        assert vm.pc == BASE + end and vm.slots[1:3] == slots, (code[0], vm.pc, vm.slots)
        assert vm.cur == code[0], 'skipped opcode replaces CurOp'
        vm.s.code[end:end + 7] = bytes([3, 1, 0, 0x7C, 0x80, 0, 0]); vm.run(BASE + end)
        assert vm.flags[0] == int(slots[1] == '')

def test_input_string():
    from sm.titles.ssb.state import State
    for answer, expected in (('Mixed Case   ', 'MIXED CASE'), (' leading ', 'LEADING'), ('', ' '), ('   ', ' ')):
        vm = VM(State(), lambda *a, **k: answer); vm.s.g['codemod'] = 1
        vm.s.code[:6] = bytes([0x10, 0, 0, 2, 0, 0x7A]); vm.run(BASE)
        assert vm.getstr(0x7A00) == expected, (answer, vm.getstr(0x7A00))

def test_wall_descriptors():
    from sm.titles.ssb.state import State
    vm = VM(State(), lambda *a, **k: 0); vm.s.dataset = 3; vm.s.walls = [1, 0xFFFF, 9]
    assert len(dax.load('WALLDEF3', d=ssb_data.SECRET)[3]) == 3 * 0x30C
    vm.load_wall(3, 1)
    assert vm.s.walls == [3, 0xFFFF, 0xFFFF]
    vm.s.walls = [1, 0xFFFF, 9]; vm.setcharfield(0x7F22, 0x83)
    assert vm.s.walls == [3, 0xFFFF, 0xFFFF]

def test_script_damage():
    from types import SimpleNamespace
    from unittest.mock import patch
    from sm.titles.ssb.state import State
    from sm.titles.ssb.units.magic import _Magic
    def make():
        s=State();s.party=[Char(bytes(439)) for _ in range(3)];s.sel=1
        for c in s.party: c.b[ACTIVE]=1;c.b[HP]=30
        vm=VM(s,lambda *a,**k:0);vm.host=SimpleNamespace(s=s,vm=vm,engines=True);vm.at=0;vm.next=1
        vm.set1(0x7F3E,3);return vm
    for flags,save,expected in (
        (0x80,0x80,[('roll',1,3),('roll',2,6),('hit',1,12),('wait',)]),
        (0x80,0x81,[('roll',1,3),('roll',2,6),('save',1,0,0),('wait',)]),
        (0x90,0,[('roll',1,3),('roll',2,6),('save',1,0,16),('hit',1,12),('wait',)]),
        (0xE0,0,sum(([('roll',2,6),('hit',i,12)] for i in range(3)),[])+[('wait',)])):
        vm=make();events=[];vm.v=lambda i:(flags,2,6,10,save)[i-1]
        def roll(m,dice,sides): events.append(('roll',dice,sides));return 2
        def saved(m,c,idx,bonus): events.append(('save',vm.s.party.index(c),idx,bonus));return True
        vm.script_damage=lambda c,amt:events.append(('hit',vm.s.party.index(c),amt));vm.damage_wait=lambda:events.append(('wait',))
        with patch.object(_Magic,'roll',roll),patch.object(_Magic,'save',saved):vm.op2E()
        assert events==expected,(flags,save,events)
        assert vm.s.sel==1 and vm.pc==1
    for hp,status,amount,expected in ((10,0,10,(0,4,0)),(10,1,10,(0,6,0)),(10,0,19,(0,5,0)),
        (10,0,20,(0,6,0)),(30,2,1,(0,2,0)),(30,3,0,(0,3,0)),(30,0,266,(20,0,1)),(30,6,2,(30,6,1))):
        vm=make();c=vm.s.party[0];c.b[HP]=hp;c.b[STATUS]=status;vm.script_damage(c,amount)
        assert (c.b[HP],c.b[STATUS],c.b[ACTIVE])==expected,(hp,status,amount)


def test_monster_copy_order():
    from sm.titles.ssb.state import State
    from unittest.mock import patch
    s = State(); v = VM(s, lambda *a, **k: 0); v.next = 0
    v.v = lambda n: {1: 7, 2: 3, 3: 1}[n]
    items = b''.join(bytes([tag]) + bytes(62) for tag in (1, 2, 3))
    effects = b''.join(bytes([tag]) + bytes(8) for tag in (4, 5))
    data = {'MON1CHA': {7: bytes(439)}, 'MON1ITM': {7: items}, 'MON1SPC': {7: effects}}
    with patch.object(dax, 'load', side_effect=lambda name, d: data[name]): v.op0B()
    assert [[i[0] for i in c.items] for c in s.monsters] == [[1, 2, 3], [3, 2, 1], [3, 2, 1]]
    assert [[e[0] for e in c.effects] for c in s.monsters] == [[4, 5], [5, 4], [5, 4]]
    s.monsters[1].items[0][0] = 9
    assert s.monsters[2].items[0][0] == 3 and s.monsters[0].items[-1][0] == 3


def test_random_treasure():
    from sm.titles.ssb.state import State
    from sm.titles.ssb.units.shops import make_treasure_item
    s = State(); s.seed = 0x7F8723A0; vm = VM(s, lambda *a, **k: 0); vm.next = 0
    vm.v = lambda n: 0x82 if n == 8 else 0
    vm.op27()
    assert s.seed == 0xBF148B2D
    assert [(i[ITYPE],i[0x32],rdw(i,0x37),rdw(i,0x3A)) for i in s.treasure_items] == [(0x25,2,50,2500),(0x22,1,300,1750)]
    calls = []; rolls = iter((2,0,0,1,0,2,0))
    def random(bound): calls.append(bound); return next(rolls)
    s.random = random; scroll = make_treasure_item(s,0x27)
    assert calls == [3,7,10,7,7,7,11] and scroll[0x3C:0x3F] == bytes((9,29,45))
    assert rdw(scroll,0x3A) == 900 and scroll[0x35] == 4
    s.random = lambda bound: 0
    ring = make_treasure_item(s,0x2F)
    assert ring[0x2F:0x32] == bytes(ssb_data.stexe()[0xA28+2*n] for n in (1,2,3))


def test_menu_roster():
    from sm.titles.ssb.state import State
    from types import SimpleNamespace
    s = State(); s.party = [Char(bytes(439)) for _ in range(2)]; answers = iter((2,1))
    def ask(kind, options, **info):
        assert options == ['YES','NO','char-up','char-down','char-first']
        vm.a = lambda _: 0x4C06
        return next(answers)
    vm = VM(s,ask); vm.host = SimpleNamespace(engines=True); vm.next = vm.at = 0
    vm.strs[1:3] = ['YES','NO']; vm.v = lambda _: 2; vm.a = lambda _: 0x4C05
    vm.op2B()
    assert s.sel == 1 and vm.m0(0x4C05) == 1 and vm.m0(0x4C06) == 0


def test_encounter_menu():
    from sm.titles.ssb.state import State
    from types import SimpleNamespace
    s = State(); s.party = [Char(bytes(439))]; s.r0[0xE6] = 1; seen = []; answers = iter((3, 1, 0))
    def ask(kind, options, **info):
        seen.append((options[3], vm.display['frame'], vm.display['id'], vm.display['pic'], ''.join(vm.out[vm.text_start:]))); return next(answers)
    vm = VM(s, ask); vm.geo = SimpleNamespace(approach=lambda s: 2); vm.host = SimpleNamespace(presentation=None); vm.next = vm.at = 0
    vm.v = lambda i: (33, 1, 7, 0, 0, 3, 1, 3, 0, 0, 0, 0, 12, 9)[i - 1]; vm.a = lambda i: 0x7F79
    vm.strs[1:4] = ['NEAR TEXT', 'FAR TEXT', '']
    vm.op29()
    assert seen == [('ADVANCE', 1, 33, 7, 'FAR TEXT'), ('PARLAY', 0, 33, 7, 'NEAR TEXT'), ('PARLAY', 0, 33, 7, 'NEAR TEXT')], seen
    assert vm.m1(0x7F79) == 1 and vm.m1(0x7EC1) == 0
    vm.set1(0x7EC0, 0); seen.clear(); answers = iter((0,)); vm.v = lambda i: (33, 2, 7, 0, 0, 3, 1, 3, 0, 0, 0, 0, 12, 9)[i - 1]
    vm.strs[1:4] = ['', 'MIDDLE', '']; vm.op29()
    assert seen == [('ADVANCE', 2, 33, 7, 'MIDDLE')], 'distance 2 falls back to the next text that exists'

def test_script_hold():
    from sm.titles.ssb.state import State
    from types import SimpleNamespace
    from collections import deque
    for queue in (None, deque()):
        s = State(); s.party = [Char(bytes([4]) + b'HERO' + bytes(434)) for _ in range(2)]; s.g['67D6'] = 5
        for c in s.party: c.b[ACTIVE] = 1; c.b[LEVEL + 2] = 1
        vm = VM(s, lambda *a, **k: 0); vm.host = SimpleNamespace(presentation=queue); vm.next = vm.at = vm.pc = 0
        before = s.hash(vm); vm.out.append('OLD'); vm.clear_text(); vm.out.append('SEEN ONLY DURING THE PAUSE'); vm.op3A()
        assert s.hash(vm) == before, 'DELAY changed the state'
        vm.clear_text(); vm.v = lambda i: (1, 1000)[i - 1]; vm.op41()
        assert ''.join(vm.out[vm.text_start:]) == 'Congratulations the party gains experience!'
        assert [int.from_bytes(c.b[XP:XP + 4], 'little') for c in s.party] == [1000, 1000]
        s.sel = 1; vm.v = lambda i: (0, 500)[i - 1]; vm.op41()
        assert ''.join(vm.out[vm.text_start:]) == 'Congratulations HERO gains experience!'
        if queue is not None:
            assert [(e['kind'], e['delay'], e['text']) for e in queue] == [('script-hold', .5, 'SEEN ONLY DURING THE PAUSE'),
                ('script-hold', .5, 'Congratulations the party gains experience!'), ('script-hold', .5, 'Congratulations HERO gains experience!')]
            s.x = 9; assert queue[0]['scene'].s.x != 9, 'the held frame keeps the position of its moment'

def test_rob():
    from sm.titles.ssb.state import State
    from unittest.mock import patch
    s = State(); c = Char(bytes(439)); s.party = [c]
    def item(tag, weight): it = bytearray(67); it[0] = tag; wrw(it, 0x37, weight); return it
    c.items = [item(1, 5), item(2, 30), item(3, 5)]; wrw(c.b, MONEY + 6, 10); wrw(c.b, MONEY + 8, 19)
    vm = VM(s, lambda *a, **k: 0); vm.next = 0; vm.v = lambda i: (1, 5, 50)[i - 1]; s.random = lambda n: 0
    with patch.object(rec, 'recalc_character') as recalc: vm.op28()
    assert (rdw(c.b, MONEY + 6), rdw(c.b, MONEY + 8)) == (9, 18), 'Trunc(10 * .95), Trunc(19 * .95)'
    assert [i[0] for i in c.items] == [2, 3] and recalc.call_count == 1, 'light item taken; the heavy one and everything after it are safe'

def test_dump():
    from sm.titles.ssb.state import State
    s = State(); s.party = [Char(bytes(439)) for _ in range(3)]; s.g.update({'47E2': 1, '47E7': 2}); s.sel = 2
    vm = VM(s, lambda *a, **k: 0); vm.next = 0; vm.set1(0x7F3E, 3); vm.op3E(); vm.op00()
    assert len(s.party) == 2 and s.sel == 0 and s.selc() is s.party[0] and vm.m1(0x7F3E) == 2

def test():
    from sm.titles.ssb.state import State
    res = {}
    for f in (1, 2, 3):
        for r in sorted(dax.load('ECL%d' % f, d=ssb_data.SECRET)):
            s = State(); s.dataset, s.block = f, r
            s.party = [Char(bytes([4]) + b'TEST' + bytes(434)) for _ in range(6)]; s.r1[0x33E] = 6
            vm = VM(s, lambda k, o, **i: 0 if o else 1)
            vm.load_wall = lambda rid, slot: s.walls.__setitem__(slot - 1, rid)
            vm.host = type('H', (), {'camp': staticmethod(lambda: None), 's':s, 'vm':vm})
            vm.load_block(r); vm.init_vm()
            try: vm.run(vm.vec[4]); res[(f, r)] = 'ok'
            except Halt as e:
                raise AssertionError('ECL%d/%d: %s' % (f, r, e))
    assert len(res) == 22, res
    test_slots()
    test_mode_change()
    test_skip_slots()
    test_input_string()
    test_wall_descriptors()
    test_script_damage()
    test_monster_copy_order()
    test_random_treasure()
    test_menu_roster()
    test_encounter_menu()
    test_script_hold()
    test_rob()
    test_dump()
