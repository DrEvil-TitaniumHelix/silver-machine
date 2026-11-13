import hashlib, struct

class Char:
    __slots__ = ('b', 'items', 'effects', 'rid')
    def __init__(self, b, items=(), effects=(), rid=None):
        self.b, self.items, self.effects = bytearray(b), [bytearray(i) for i in items], [bytearray(e) for e in effects]
        self.rid = rid

class State:
    def __init__(self):
        self.r0 = [0] * 0x400
        self.r1 = [0] * 0x400
        self.r2 = [0] * 0x200
        self.code = bytearray(0x1E00)
        self.party, self.monsters = [], []
        self.sel = 0
        self.x = self.y = self.dir = self.ahead = self.attr = 0
        self.dataset, self.block = 2, 0x11
        self.mode = self.prev_mode = 4
        self.walls = [0xFFFF] * 3
        self.seed = 0
        self.treasure_money, self.treasure_items = [0] * 7, []
        self.clock = 0
        self.restart = self.stop = self.party_dead = 0
        self.g = {}

    def copy(self):
        n = State.__new__(State); n.__dict__.update(self.__dict__)
        n.r0, n.r1, n.r2, n.code = self.r0[:], self.r1[:], self.r2[:], bytearray(self.code)
        n.party = [Char(c.b, c.items, c.effects) for c in self.party]; n.monsters = [Char(c.b, c.items, c.effects) for c in self.monsters]
        n.walls, n.treasure_money, n.treasure_items, n.g = self.walls[:], self.treasure_money[:], [bytearray(i) for i in self.treasure_items], dict(self.g)
        return n

    def chars(self): return self.party + self.monsters
    def selc(self):
        c = self.chars(); return c[self.sel] if 0 <= self.sel < len(c) else None

    def random(self, n):
        self.seed = (self.seed * 0x08088405 + 1) & 0xFFFFFFFF
        return (self.seed >> 16) % n if n else 0

    def hash(self, vm=None):
        h = hashlib.sha256()
        for r in (self.r0, self.r1, self.r2): h.update(struct.pack('<%dH' % len(r), *(v & 0xFFFF for v in r)))
        h.update(self.code)
        for c in self.chars(): h.update(c.b); [h.update(i) for i in c.items]; [h.update(e) for e in c.effects]
        g = sorted((k, v if isinstance(v, (int, str, bytes)) else repr(v)) for k, v in self.g.items())
        h.update(repr((self.sel, self.x, self.y, self.dir, self.ahead, self.attr, self.dataset, self.block, self.mode, self.prev_mode,
                       self.walls, self.seed, self.treasure_money, [bytes(i) for i in self.treasure_items], self.clock,
                       self.restart, self.stop, self.party_dead, g)).encode())
        if vm is not None: h.update(repr((vm.pc, list(vm.gosub), list(vm.flags), list(vm.vec), vm.resuming, list(vm.slots[1:5]))).encode())
        return h.hexdigest()[:16]

def test():
    s = State(); a = s.hash(); s.r0[0xE6] = 1
    assert s.copy().hash() == s.hash() and s.hash() != a and s.random(100) == State().random(100) and 0 <= s.random(6) < 6
