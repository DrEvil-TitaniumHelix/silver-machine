from sm.titles.ssb import vm as V, walk, save; from sm.titles.ssb import rec
from sm.titles.ssb.state import State, Char
from types import SimpleNamespace
from sm.engine import Session, legal_choice
from sm.pascal import HostBinding

DECISION_KINDS = frozenset(('ACK CAMP CAMP_MENU COMBAT COMBAT_ACTION CREATE CREATE_ABILITY CREATE_ADD '
    'CREATE_ALIGNMENT CREATE_CLASS CREATE_EXIT CREATE_GENDER CREATE_HP CREATE_ICON CREATE_MENU CREATE_MODIFY '
    'CREATE_NAME CREATE_RACE CREATE_REMOVE CREATE_ROLL CREATE_SAVE CREATE_SLOT CREATE_TRAIN LIST MENU MOVE '
    'NUMBER PARLAY SHOP SHOP_MENU SPELL STRING TARGET TEMPLE TREASURE VAULT WHO INPUT').split())

class Geo:
    def __init__(self): self.map = None
    def load(self, s, m):
        try: self.map = walk.Map(s.dataset, m)
        except KeyError: raise V.Halt('GEO%d record %d missing' % (s.dataset, m))
        for k in [k for k in s.g if k.startswith('door ')]: del s.g[k]
    def resume(self, s, vm):
        if vm.is3d() and 0 < s.walls[0] < 0x8000: self.load(s, vm.m0(0x4BC5))
    def passage(self, s, x, y, f):
        if not self.map: return 0
        if self.map.walls(x, y, f) == 0: return 1
        return s.g.get('door %d %d %d' % (x, y, f), self.map.passages(x, y, f))
    def attr(self, s, x, y): return self.map.attr(x & 15, y & 15) if self.map else 0
    def wall(self, s, x, y, d): return self.map.walls(x & 15, y & 15, d) if self.map else 0
    def approach(self, s):
        if s.r0[0xE6] == 0: s.r1[0x2C1] = 2; return 2
        if not self.map: return 0
        x, y, n = s.x, s.y, 0
        while n < 2 and 0 <= x < 16 and 0 <= y < 16 and self.map.walls(x, y, s.dir) == 0:
            dx, dy = walk.DELTAS[s.dir // 2]; x, y, n = x + dx, y + dy, n + 1
        return n

class Done(Exception): pass

class Game:
    def __init__(self, player, slot='A', engines=False, directory=None, *, binding=None):
        from pathlib import Path
        self.binding = binding or HostBinding(State, V.VM, Geo, save.load, save.restore, save.SECRET)
        self.s = s = self.binding.state(); self.trace = []; self.player = player; self.hashing = True
        self.presentation = None
        self.presentation_text = ''
        self.presentation_poses = {}
        self.engines = engines
        self.slot = slot; path = Path(directory or self.binding.root).resolve()
        if slot is not None and not (path / ('SAVGAM%s.DAT' % slot)).is_file() and (path / slot / ('SAVGAM%s.DAT' % slot)).is_file(): path /= slot
        self.directory = str(path)
        if slot is None and self.binding.initialize is not None:
            self.binding.initialize(s)
        elif slot is None:
            s.r0[0x1F4], s.r0[0xE6] = 2, 1
            s.x, s.y, s.dir, s.dataset, s.block, s.prev_mode = 7, 13, 0, 1, 0, 0
            s.walls = [0, 0xFFFF, 0xFFFF]
            s.g.update(bash=1, pick=1, knock=1)
            s.g.update({'67D6': 4, '67EB': 1, '67ED': 1})
        else:
            d = self.binding.load(path, slot=slot)
            self.binding.restore(s, d)
        self.geo = self.binding.geo(); self.vm = self.binding.vm(s, self.ask, self.geo); self.vm.host = self; self.vm.resuming = slot is not None
        if slot is not None: self.geo.resume(s, self.vm)

    def state_hash(self):
        return self.s.hash(self.vm)

    def present(self, kind, actor=None, delay=0, **details):
        if self.presentation is None or not self.s.g.get('combat.active'): return
        s = self.s
        actor = s.sel if actor is None else actor
        if kind == 'message':
            self.presentation_text = details['text']
            self.presentation_names = tuple((n[0],n[1],n[2] if len(n)>2 else
                12 if not s.chars()[n[1]].b[0x1A7] else 14 if s.chars()[n[1]].b[0x1A8] else 11) for n in details.get('names',()))
        elif kind == 'clear': self.presentation_text, self.presentation_names = '', ()
        poses = getattr(self, 'presentation_poses', {})
        if 'command' in details: self.presentation_command = details['command']
        if 'pose' in details: poses[actor] = details['pose']
        self.presentation_poses = poses
        chars = tuple(SimpleNamespace(b=bytes(c.b), items=tuple(bytes(i) for i in c.items),
                                      effects=tuple(bytes(e) for e in c.effects)) for c in s.chars())
        if details.get('status') or kind == 'swing' and not details.get('spell') or getattr(self, 'presentation_panel', None) is None:
            self.presentation_panel = chars[actor]
            self.presentation_panel_party = chars[:len(s.party)]
            self.presentation_panel_casting = bool(s.g['combat.records'][actor][0] or getattr(self, 'presentation_casting', None)==actor)
        fields = {k: tuple(tuple(p) for p in s.g[k]) for k in ('combat.positions', 'combat.records')}
        fields.update({'combat.tiles': bytes(s.g['combat.tiles']), 'combat.active': 1,
                       '8DC7': s.g.get('8DC7', 0), '87D8': s.g.get('87D8', 0), 'casting': getattr(self, 'presentation_casting', None)})
        cursor = getattr(self, 'presentation_cursor', None)
        if 'cursor' in details:
            cursor = (actor, fields['combat.positions'][actor], fields['combat.records'][actor][9]) if details['cursor'] else None
        elif kind in ('view', 'redraw') or (cursor and cursor[0] == actor and
                (kind in ('move', 'swing', 'flash', 'death') or kind == 'facing' and
                 cursor[2]//4 != fields['combat.records'][actor][9]//4)):
            cursor = None
        self.presentation_cursor = cursor
        focus = details.get('focus', fields['combat.positions'][actor][:2])
        view = getattr(self, 'presentation_view', None)
        margin = details.get('margin', 3)
        if view is None:
            origin = fields['combat.positions'][0]
            view = (max(0, min(43, origin[0]-3)), max(0, min(18, origin[1]-3)))
        pos = fields['combat.positions'][actor]
        if kind == 'view' and (details.get('turn_start') or details.get('status')):
            self.presentation_redraw = chars[actor].b[V.SIDE] == 0 or bool(pos[2]) and all(view[i] <= pos[i] <= view[i] + 6 for i in (0, 1))
        if kind == 'swing' and details.get('spell'): self.presentation_redraw = True
        if (('focus' in details or getattr(self, 'presentation_redraw', True)) and
                ('focus' in details or 'margin' in details or kind in ('view', 'move', 'swing', 'facing', 'flash', 'death', 'missile', 'bolt', 'area'))):
            view = tuple(max(0, min(bound, focus[i]-3)) if abs(focus[i]-view[i]-3) > margin else view[i]
                         for i, bound in enumerate((43, 18)))
        self.presentation_view = view
        scene = SimpleNamespace(s=SimpleNamespace(g=fields, sel=actor, chars=lambda: chars,
                                                  party=chars[:len(s.party)]),
                                vm=SimpleNamespace(icons=dict(getattr(self.vm, 'icons', {}))))
        self.presentation.append(dict(kind=kind, actor=actor, delay=delay, scene=scene,
                                      text=self.presentation_text, poses=dict(poses), view=view,
                                      footer=getattr(self, 'presentation_footer', ()),
                                      panel=self.presentation_panel,
                                      panel_casting=getattr(self, 'presentation_panel_casting', False),
                                      cursor_cell=cursor[1] if cursor else None,
                                      command=getattr(self,'presentation_command',None),
                                      names=getattr(self, 'presentation_names', ()),
                                      redraw=getattr(self, 'presentation_redraw', True),
                                      panel_party=getattr(self, 'presentation_panel_party', None),
                                      **{k: v for k, v in details.items() if k not in ('text','names','command')}))

    def ask(self, kind, options, **info):
        s = self.s
        finished = getattr(getattr(self, 'binding', None), 'finished', None)
        if (finished(self) if finished is not None else self.vm.m0(0x4CD9) == 1): raise Done()
        h = s.hash(self.vm) if self.hashing else ''; c = self.player(kind, options, self, **info)
        if not legal_choice(options, c):
            raise V.Halt('player returned %r for %s %r' % (c, kind, options))
        self.trace.append((len(self.trace), kind, s.dataset, s.block, info.get('at', 0), h, c))
        return c

    def camp(self):
        vm = self.vm; vm.run(vm.vec[2])
        if self.engines:
            if vm.service('camp', 'run'): vm.run(vm.vec[3])
        else: self.ask('CAMP', ['rest'], at=0); vm.run(vm.vec[3])

    def after_new_block(self):
        s, vm = self.s, self.vm
        while True:
            s.restart = 0; s.attr = self.geo.attr(s, s.x, s.y); s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
            vm.display['view_dirty'] = True
            vm.set1(0x7ED5, 0); s.g['47E7'] = s.sel
            vm.run(vm.vec[4])
            if not s.restart:
                if s.prev_mode==s.mode==4: vm.display.pop('blank',None)
                vm.set0(0x4BF2, s.block); vm.run(vm.vec[0])
                if not s.restart:
                    vm.run(vm.vec[1])
                    if not s.restart: s.sel = s.g['47E7']
            if not s.restart: break
        s.prev_mode = s.mode

    def boot(self):
        s, vm = self.s, self.vm
        s.mode, s.restart = 4, 0
        if vm.m0(0x4BF2) == 0: s.dataset, s.block = 2, 0x11
        else: s.block = vm.m0(0x4BF2) & 0xFF
        if vm.m0(0x4BE6) == 0: s.mode = 3
        vm.load_block(s.block); vm.init_vm(); self.entry = (s.dataset, s.block, vm.vec[4])
        vm.run(vm.vec[4])
        if not s.restart: vm.set0(0x4BF2, s.block)
        else: self.after_new_block()
        vm.resuming = False

    def moves(self):
        opts = ['turn-left', 'turn-right', 'forward', 'look', 'search', 'camp'] if self.geo.map else ['look', 'search', 'camp']
        return opts + (['cast', 'view', 'turn-around', 'char-up', 'char-down'] if self.engines else [])

    def turn(self):
        s, vm = self.s, self.vm
        if not any(c.b[V.ACTIVE] for c in s.party): raise V.Halt('AllDead (ov03:3D56): no active member')
        if 'location' not in vm.display: self.paint_location()
        opts = self.moves(); c = opts[self.ask('MOVE', opts, x=s.x, y=s.y, dir=s.dir)]
        if c in ('char-up', 'char-down'):
            s.sel = (s.sel + (-1 if c == 'char-up' else 1)) % len(s.party); return
        if c in ('cast', 'view'):
            from sm.titles.ssb.units import camp, shops
            if c == 'view': shops.view(self, character=s.selc())
            elif s.selc() and s.selc().b[V.STATUS] == 0: camp.cast_command(self, s.selc())
            return
        vm.set1(0x7EC9, 0)
        if c in ('forward', 'look', 'camp'): vm.clear_text()
        if c in ('turn-left', 'turn-right', 'turn-around'):
            s.dir = (s.dir + {'turn-left': 6, 'turn-right': 2, 'turn-around': 4}[c]) % 8; s.ahead = self.geo.wall(s, s.x, s.y, s.dir); vm.display = {'kind': None}; return
        if c == 'search': vm.set1(0x7ECA, vm.m1(0x7ECA) ^ 1); return
        s.g['47E7'] = s.sel
        if not s.restart: vm.set0(0x4BF2, s.block)
        if c == 'camp': self.camp(); return
        if c == 'look':
            vm.set1(0x7ECA, vm.m1(0x7ECA) | 2); vm.advance_clock(1, 2)
            keep = vm.m1(0x7ECA) & 1; vm.set1(0x7ECA, 1); self.refresh_attr(); vm.run(vm.vec[1])
            if s.restart: self.after_new_block()
            vm.set1(0x7ECA, keep); return
        vm.set1(0x7ED5, 0)
        dx, dy = walk.DELTAS[s.dir // 2]
        if self.geo.passage(s, s.x & 15, s.y & 15, s.dir) and not (0 <= s.x + dx < 16 and 0 <= s.y + dy < 16): vm.set1(0x7ED5, 1)
        vm.run(vm.vec[0])
        if s.restart: self.after_new_block(); return
        vm.set0(0x4BF0, s.x); vm.set0(0x4BF1, s.y)
        self.move_party(); self.refresh_attr()
        vm.run(vm.vec[1])
        if s.restart: self.after_new_block()

    def refresh_attr(self):
        s = self.s
        if s.r0[0xE6] or s.r0[0x138]:
            s.attr = self.geo.attr(s, s.x, s.y)
            self.vm.display['sky'] = s.r0[0xFD:0xFF]

    def move_party(self):
        s, vm = self.s, self.vm
        if s.mode != 4: return
        if vm.m1(0x7EC9) >= 0xFF: vm.set1(0x7EC9, 0); return
        p = self.geo.passage(s, s.x & 15, s.y & 15, s.dir)
        if p == 1: self.step()
        elif p in (2, 3) and self.door(p): self.step()
        self.paint_location()

    def paint_location(self):
        self.vm.paint_location()

    def door(self, p):
        s, f = self.s, self.s.g
        R = lambda n: s.random(n) + 1
        thief = any(c.b[V.LEVEL + 6] or c.b[V.OLDLV + 6] and V.dual(c) for c in s.party)
        knock = [c for c in s.party if 0x1F in c.b[V.MEMSPELL:V.MEMSPELL + 75]]
        opts = (['Bash'] if f.get('bash', 1) else []) + (['Pick'] if f.get('pick', 1) and thief else []) + (['Knock'] if f.get('knock', 1) and knock else []) + ['Exit']
        if opts == ['Exit']: return False
        c = opts[self.ask('MENU', opts, door=p, at=0)]
        ok = False
        if c == 'Bash':
            for m in s.party:
                st, ex = m.b[0x11], m.b[0x1C]
                if p == 3: t = ((6, 1) if st == 18 and 91 <= ex <= 99 else (6, 2) if st == 18 and ex == 0x64 else (6, 3) if st in (19, 20) else (6, 4) if st in (21, 22)
                                else (6, 5) if st == 23 else (8, 7) if st == 24 else (1, 1) if st >= 25 else None)
                else: t = ((6, 1) if 3 <= st <= 7 else (6, 2) if st <= 15 else (6, 3) if st <= 17 else ((6, 3) if ex <= 50 else (6, 4) if ex <= 99 else (6, 5)) if st == 18
                           else (8, 7) if st <= 20 else (10, 9) if st == 21 else (12, 11) if st <= 23 else (20, 19) if st == 24 else (1, 1))
                if t is None: f['bash'] = 0
                elif R(t[0]) <= t[1]: ok = True; break
        elif c == 'Pick':
            if p == 2: ok = any(R(100) <= m.b[0xF4] and m.b[V.STATUS] == 0 for m in s.party)
            f['pick'] = 0
        elif c == 'Knock': m = knock[0]; m.b[V.MEMSPELL + list(m.b[V.MEMSPELL:V.MEMSPELL + 75]).index(0x1F)] = 0; ok = True
        if ok:
            f['door %d %d %d' % (s.x, s.y, s.dir)] = 1
            dx, dy = walk.DELTAS[s.dir // 2]; nx, ny = s.x + dx, s.y + dy
            if 0 <= nx < 16 and 0 <= ny < 16: f['door %d %d %d' % (nx, ny, (s.dir + 4) % 8)] = 1
        return ok

    def step(self):
        s = self.s; dx, dy = walk.DELTAS[s.dir // 2]; self.vm.display = {'kind': None}
        s.x, s.y = (s.x + dx) & 15, (s.y + dy) & 15
        s.ahead = self.geo.wall(s, s.x, s.y, s.dir); s.attr = self.geo.attr(s, s.x, s.y)
        s.g['bash'] = s.g['pick'] = s.g['knock'] = 1; self.vm.advance_clock(1, 2 if self.vm.m1(0x7ECA) & 1 else 1)

    def play(self, limit=100_000):
        try:
            if self.slot is None:
                self.vm.service('creation', 'run')
                if self.s.stop: return 'EXIT'
            self.boot()
            while len(self.trace) < limit: self.turn()
        except Done: return 'DONE'
        return 'LIMIT'



def test():
    g = Game(lambda k, o, game, **i: 0 if o else 1)
    try: g.play(limit=3)
    except V.Halt as e: raise AssertionError('V3 halt: %s' % e)
    assert g.entry == (2, 0x11, 0x8014), g.entry
    assert ''.join(g.vm.out).strip(), 'no opening text'
    test_look()
    test_loaded_character()
    test_load_recalc()
    test_load_globals()
    test_session()
    test_door()

def test_door():
    g = Game(lambda k, o, game, **i: o.index('Bash') if 'Bash' in o else 0); s = g.s; seen = []
    for c in s.party: c.b[0x11], c.b[0x1C] = 10, 0; c.b[V.LEVEL + 6] = c.b[V.OLDLV + 6] = 0; c.b[V.MEMSPELL:V.MEMSPELL + 75] = bytes(75)
    s.party[1].b[0x11] = 19; s.random = lambda n: n - 1
    s.g.update(bash=1, pick=1, knock=1)
    assert not g.door(3) and s.g['bash'] == 0, 'Bash stays on offer after a weak member tried'
    assert not g.door(3) and not any(k.startswith('door ') for k in s.g), 'a door with nothing left to offer must stay a door'
    s.g['bash'] = 1; s.party[0].b[0x11] = s.party[1].b[0x11]
    for c in s.party[2:]: c.b[0x11] = 19
    assert not g.door(3) and s.g['bash'] == 1, 'nobody too weak: Bash stays'
    g.player = lambda k, o, game, **i: (seen.append(list(o)), len(o) - 1)[1]
    c = s.party[0]; c.b[V.OLDLV + 6], c.b[V.RACE], c.b[0xEF] = 3, 6, 9; c.b[V.LEVEL:V.LEVEL + 7] = bytes((0, 0, 2, 0, 0, 0, 0))
    g.door(2); c.b[V.LEVEL + 2] = 10; g.door(2)
    assert seen == [['Bash', 'Exit'], ['Bash', 'Pick', 'Exit']], seen

def test_look():
    from unittest.mock import patch
    for search in (0, 1):
        g = Game(lambda k, o, game, **i: o.index('look'))
        s, vm = g.s, g.vm; vm.vec[1] = 0x8123; vm.set1(0x7ECA, search)
        vm.set0(0x4BC8, 5); vm.set0(0x4BC9, 23); vm.set0(0x4BCA, 7)
        s.party[0].effects = [bytearray([1, 10, 0, 0, 0, 0, 0, 0, 0]), bytearray([2, 11, 0, 0, 0, 0, 0, 0, 0])]
        before = (s.x, s.y, s.dir); seen = []
        with patch.object(vm, 'run', side_effect=lambda pc: seen.append((pc, s.r0[0xC8:0xCB], [list(e[:3]) for e in s.party[0].effects]))):
            g.turn()
        assert seen == [(0x8123, [0, 0, 8], [[2, 1, 0]])], seen
        assert (s.x, s.y, s.dir) == before and vm.m1(0x7ECA) == search

def test_loaded_character():
    from unittest.mock import patch
    from sm.titles.ssb.units import creation
    for paladin, former, race, level, want in ((1, 0, 6, 1, 1), (0, 3, 6, 7, 1),
                                              (0, 3, 6, 6, 0), (0, 3, 2, 7, 0), (0, 2, 6, 7, 0)):
        d = save.load(); r = d['party'][0]; b = r.data
        b[0x111:0x118] = bytes(7); b[0x118:0x11F] = bytes(7)
        b[0x114], b[0x101], b[0x6B], b[0x116], b[0xEF], b[0x6D] = paladin, former, race, level, 6, 0
        with patch.object(save, 'load', return_value=d):
            g = Game(lambda k, o, game, **i: 0)
            assert g.s.party[0].b[0x6D] == want, ('boot cure', paladin, former, race, level)
            with patch.object(g.vm, 'load_block'), patch.object(g.vm, 'init_vm'):
                creation.load_game(g, 'A')
            assert g.s.party[0].b[0x6D] == want, 'menu load cure'
        assert r.data[0x6D] == 0, 'runtime load mutated the raw codec record'
        g.s.party = []; g.s.g['creation.roster_loaded'] = 1
        g.s.g['character.TEST'] = creation.image(Char(bytes(r)))
        g.player=lambda k,o,current,**info: o.index(None) if current.s.party else 0
        creation.add(g)
        assert g.s.party[0].b[0x6D] == want, 'standalone cure'

def test_load_recalc():
    from unittest.mock import patch
    from sm.titles.ssb.units import creation
    d = save.load(); r = d['party'][0]; b = r.data
    b[0x111:0x11F] = bytes(14); b[0x113] = 7; b[0x6B] = 6; b[0x6A] = b[0x130] = 255
    with patch.object(save, 'load', return_value=d):
        g = Game(lambda *a, **k: 0)
        assert (g.s.party[0].b[0x6A], g.s.party[0].b[0x130]) == (46, 8), 'boot RecalcLevels'
        expected = Char(bytes(r), [bytes(i) for i in r.items], [bytes(e) for e in r.effects])
        rec.recalc_character(expected, d['r1'][0x372]); rec.recalc_levels(expected)
        assert (g.s.party[0].b, g.s.party[0].items) == (expected.b, expected.items), 'ReadCharacter recalculation order'
        with patch.object(g.vm, 'load_block'), patch.object(g.vm, 'init_vm'):
            creation.load_game(g, 'A')
        assert (g.s.party[0].b, g.s.party[0].items) == (expected.b, expected.items), 'menu RecalcLevels'
    assert b[0x6A] == b[0x130] == 255, 'codec bytes changed'

def test_load_globals():
    from unittest.mock import patch
    from sm.titles.ssb.units import creation
    d = save.load(); d['r0'][0xFC] = 0x107; d['r0'][0xFF] = 3; d['r1'][0x312] = 0x102
    d['r1'][0x33E] = 99; d['dataset'] = 1; d['prev_mode'], d['mode'] = 3, 2
    d['walls'] = [(11, 1), (12, 2), (13, 3)]; d['r0'][0xC5] = 49
    for r in d['party']: r.data[0x155] = 7
    d['party'][-1].data[0xFF] = 0xB2; d['party'][-1].data[0x12B] = 0x4D
    def check(s):
        assert s.dataset == 2 and s.r1[0x33E] == len(d['party']), 'dataset/count'
        assert [c.b[0x155] for c in s.party] == list(range(len(s.party))), 'load icon slots'
        assert all(r.data[0x155] == 7 for r in d['party']), 'load mutated codec icon slots'
        assert (s.g.get('67D6'), s.g.get('67EB'), s.g.get('67ED')) == (7, 1, 1), 'speed/pictures/animation'
        assert (s.prev_mode, s.mode, s.sel, s.walls) == (2, 0, 0, [11, 12, 13]), 'mode/selection/walls'
    with patch.object(save, 'load', return_value=d):
        g = Game(lambda *a, **k: 0); check(g.s); assert g.geo.map, 'ov20:2D5E Load3DMap'
        assert g.vm.icons == {5: ('CPIC', 0x4D, 2)}, 'loaded NPC icon missing'
        g.vm.icons = {0: ('CPIC', 14, 3), 8: ('CPIC', 32, 3)}
        g.s.sel = 5; g.geo.map = None
        with patch.object(g.vm, 'load_block'), patch.object(g.vm, 'init_vm'):
            creation.load_game(g, 'A')
        check(g.s); assert g.geo.map, 'party-menu load: Load3DMap'
        assert g.vm.icons == {5: ('CPIC', 0x4D, 2)}, 'menu Load retained old combat icons'
        d['walls'][0] = (0xFFFF, 1)
        assert not Game(lambda *a, **k: 0).geo.map, 'ov20:2D61 JLE: signed word 89DC'

def test_session():
    from sm.titles.ssb.resolve import resolve
    RES = ('COMBAT', 'TREASURE', 'CAMP', 'TEMPLE', 'VAULT', 'CREATE', 'ACK')
    def p(k, o, game, **i):
        if k in RES: resolve(k, game); return 0
        return 0 if o else 1
    ref = Game(p); ref.play(limit=30); want = [(t[1], t[5]) for t in ref.trace if t[1] not in RES][:20]
    ses = Session(); seen = []
    while ses.decision and len(seen) < 20:
        seen.append((ses.decision['kind'], ses.decision['hash'])); ses.step(0 if ses.decision['options'] else 1)
    ses.close()
    assert seen == want and len(seen) == 20, 'Session diverges from Game'

