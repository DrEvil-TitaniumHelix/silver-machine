"""Game loop (ov03:3DB9 GameLoop, 3C5C RunAfterNewBlock, 352B CampCheck; evidence titles/ssb/areas/ecl_ops.js) over the VM,
GEO adapter over walk.Map, decision trace with a state hash per decision. Done = cell [4CD9] = 1 (PLAN.md 0)."""
from sm.titles.ssb import vm as V, walk, save; from sm.titles.ssb import rec
from sm.titles.ssb.state import State, Char
from types import SimpleNamespace
from sm.engine import Session, legal_choice

# Closed decision vocabulary emitted by the VM and ported units. GU-69 rejects unknown kinds.
DECISION_KINDS = frozenset(('ACK CAMP CAMP_MENU COMBAT COMBAT_ACTION CREATE CREATE_ABILITY CREATE_ADD '
    'CREATE_ALIGNMENT CREATE_CLASS CREATE_EXIT CREATE_GENDER CREATE_HP CREATE_ICON CREATE_MENU CREATE_MODIFY '
    'CREATE_NAME CREATE_RACE CREATE_REMOVE CREATE_ROLL CREATE_SAVE CREATE_SLOT CREATE_TRAIN LIST MENU MOVE '
    'NUMBER PARLAY SHOP SHOP_MENU SPELL STRING TARGET TEMPLE TREASURE VAULT WHO INPUT').split())  # ov22:0DF3 input poll, recorded for replay.

class Geo:
    """Current 3D map = GEO<dataset> record [4BC5] (LOAD FILES ov03:0CFA)."""
    def __init__(self): self.map = None
    def load(self, s, m):
        try: self.map = walk.Map(s.dataset, m)
        except KeyError: raise V.Halt('GEO%d record %d missing' % (s.dataset, m))
        for k in [k for k in s.g if k.startswith('door ')]: del s.g[k]     # opened doors last for the visit only (GATE.md 2b)
    def resume(self, s, vm):
        """LoadGame ov20:2D52..2D71: in a 3D area, JLE on signed word DS:89DC skips, else Load3DMap([4BC5]); the area script is not re-run."""
        if vm.is3d() and 0 < s.walls[0] < 0x8000: self.load(s, vm.m0(0x4BC5))
    def passage(self, s, x, y, f):
        """GetPassage ov31:0568 with this visit's opened doors (ov16:010E writes state 1 into the map buffer)."""
        if not self.map: return 0
        if self.map.walls(x, y, f) == 0: return 1
        return s.g.get('door %d %d %d' % (x, y, f), self.map.passages(x, y, f))
    def attr(self, s, x, y): return self.map.attr(x & 15, y & 15) if self.map else 0
    def wall(self, s, x, y, d): return self.map.walls(x & 15, y & 15, d) if self.map else 0
    def approach(self, s):
        """ApproachDistance ov09:0478: 2D -> [7EC1] := 2, 2; 3D: steps ahead while the wall nibble is 0 (no wrap), max 2."""
        if s.r0[0xE6] == 0: s.r1[0x2C1] = 2; return 2
        if not self.map: return 0
        x, y, n = s.x, s.y, 0
        while n < 2 and 0 <= x < 16 and 0 <= y < 16 and self.map.walls(x, y, s.dir) == 0:
            dx, dy = walk.DELTAS[s.dir // 2]; x, y, n = x + dx, y + dy, n + 1
        return n

class Done(Exception): pass

class Game:
    def __init__(self, player, slot='A', engines=False, directory=None):
        """ov03:3DB9 game host; ov26:173F display calls are opt-in, outside State."""
        from pathlib import Path
        self.s = s = State(); self.trace = []; self.player = player; self.hashing = True
        self.presentation = None                 # Headless Game/Session/route never collect frames or wait.
        self.presentation_text = ''
        self.presentation_poses = {}
        self.engines = engines                                           # PORT2: True = the ported units (Bruce plays), False = GU-59 resolvers
        self.slot = slot; path = Path(directory or save.SECRET).resolve()
        if slot is not None and not (path / ('SAVGAM%s.DAT' % slot)).is_file() and (path / slot / ('SAVGAM%s.DAT' % slot)).is_file(): path /= slot
        self.directory = str(path)
        if slot is None:
            # StartupInit ov13:03DA..0440/049C..0641; MainProgram 0000:027E sets dataset 1 before the menu.
            s.r0[0x1F4], s.r0[0xE6] = 2, 1
            s.x, s.y, s.dir, s.dataset, s.block, s.prev_mode = 7, 13, 0, 1, 0, 0
            s.walls = [0, 0xFFFF, 0xFFFF]
            s.g.update(bash=1, pick=1, knock=1)
        else:
            d = save.load(path, slot=slot)                               # accepts the save root or the slot directory
            save.restore(s, d)
        self.geo = Geo(); self.vm = V.VM(s, self.ask, self.geo); self.vm.host = self; self.vm.resuming = slot is not None
        if slot is not None: self.geo.resume(s, self.vm)

    def state_hash(self):
        return self.s.hash(self.vm)

    def present(self, kind, actor=None, delay=0, **details):
        """ov33:0959/0AB9, ov26:173F/270F: snapshot a display call, never the simulation.

        Delay is in seconds (0540:0BF7 = DS:67D6 * 100 ms). Only an attached UI
        enables this queue. Records, terrain and icon bindings must survive combat
        cleanup before the first queued frame is played.
        """
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
        # ov23:15E8 / arena 015/00423: a spell pose retains the aimed target;
        # ov15:1638 melee poses refresh the attacker before their message.
        if details.get('status') or kind == 'swing' and not details.get('spell') or getattr(self, 'presentation_panel', None) is None:
            self.presentation_panel = chars[actor]  # ov26:0C8F; subsequent messages/death do not refresh the status panel.
            self.presentation_panel_party = chars[:len(s.party)]  # the panel's item names (Detect Magic '*', ov26:0D2E) are as drawn then, not as the effects change later (arena 005/00224).
            self.presentation_panel_casting = bool(s.g['combat.records'][actor][0] or getattr(self, 'presentation_casting', None)==actor)
        fields = {k: tuple(tuple(p) for p in s.g[k]) for k in ('combat.positions', 'combat.records')}
        fields.update({'combat.tiles': bytes(s.g['combat.tiles']), 'combat.active': 1,
                       '8DC7': s.g.get('8DC7', 0), '87D8': s.g.get('87D8', 0), 'casting': getattr(self, 'presentation_casting', None)})  # 87D8 = the spell being cast: its Spell: row stays until ov23:17AA
        # ov33:1307/01D3 paints a cursor into the map. Text/menu writes retain it;
        # ov33:0B04..0B47 erases its cell only when DrawIcon changes mirror or pose.
        cursor = getattr(self, 'presentation_cursor', None)
        if 'cursor' in details:
            cursor = (actor, fields['combat.positions'][actor], fields['combat.records'][actor][9]) if details['cursor'] else None
        elif kind in ('view', 'redraw') or (cursor and cursor[0] == actor and
                (kind in ('move', 'swing', 'flash', 'death') or kind == 'facing' and
                 cursor[2]//4 != fields['combat.records'][actor][9]//4)):
            cursor = None
        self.presentation_cursor = cursor
        # ov33:0797: retain the view while the point is inside center +/- margin;
        # outside, center on that axis and clamp to the 50x25 map.
        focus = details.get('focus', fields['combat.positions'][actor][:2])
        view = getattr(self, 'presentation_view', None)
        margin = details.get('margin', 3)
        if view is None:
            origin = fields['combat.positions'][0]  # ov12:1564 setup centers the party; ov33:0797 then follows within a margin.
            view = (max(0, min(43, origin[0]-3)), max(0, min(18, origin[1]-3)))
        # ov33:0797 ViewFollow runs only inside ov33:0959 RedrawMap. Its callers: ov33:1307 turn start
        # (margin 2), ov33:0AB9 face/pose and ov26:270F HitAnimation / ov33:0DEB death (margin 3 when the
        # icon is not visible), ov26:1C38 projectile (FF = center), moves and aiming. NameMessage ov26:173F,
        # ClearMenuLine and the Guard action ov26:2E3B never redraw the map, so a message, clear, command,
        # guard or restore event keeps the view (arena 015: Guard by the off-map Dominic must not scroll to 0,0).
        # DS:8E29 (ov10:08F6..0915): at a turn start := side = 0 or IconVisible(rec, 0); ov33:1307 redraws only
        # when it is set, so an off-screen enemy's turn never scrolls (arena 015/00513: Guy, side 1 at (32,11),
        # view stays (24,9)). ov23:1632 sets it to 1 for a cast. Presentation state only; never State.g.
        pos = fields['combat.positions'][actor]
        if kind == 'view' and (details.get('turn_start') or details.get('status')):  # ov10:0935..0944: visibility is set before cursor drawing, independently of the later panel write.
            self.presentation_redraw = chars[actor].b[V.SIDE] == 0 or bool(pos[2]) and all(view[i] <= pos[i] <= view[i] + 6 for i in (0, 1))
        if kind == 'swing' and details.get('spell'): self.presentation_redraw = True
        # Explicit RedrawMap callers ignore DS:8E29: AI focus ov11:1007..1034,
        # projectile ov26:1C28..1C38 and area redraws. The flag gates DrawIcon/turn start only.
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
        if self.vm.m0(0x4CD9) == 1: raise Done()
        h = s.hash(self.vm) if self.hashing else ''; c = self.player(kind, options, self, **info)   # state + VM position (V6)
        if not legal_choice(options, c):
            raise V.Halt('player returned %r for %s %r' % (c, kind, options))
        self.trace.append((len(self.trace), kind, s.dataset, s.block, info.get('at', 0), h, c))
        return c

    def camp(self):
        vm = self.vm; vm.run(vm.vec[2])
        if self.engines:
            from sm.titles.ssb.units import camp
            if camp.run(self): vm.run(vm.vec[3])                          # ov03:352B: vecD only when the party rested
        else: self.ask('CAMP', ['rest'], at=0); vm.run(vm.vec[3])

    def after_new_block(self):
        s, vm = self.s, self.vm
        while True:
            s.restart = 0; s.attr = self.geo.attr(s, s.x, s.y); s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
            vm.display['view_dirty'] = True  # ov03:3C9C sets A4CC before vecE, even with no retained portrait.
            vm.set1(0x7ED5, 0); s.g['47E7'] = s.sel
            vm.run(vm.vec[4])
            if not s.restart:
                if s.prev_mode==s.mode==4: vm.display.pop('blank',None)  # ov03:3CDD..3D00 redraws the 3D view after the init script, without ov26:316A's location line.
                vm.set0(0x4BF2, s.block); vm.run(vm.vec[0])
                if not s.restart:
                    vm.run(vm.vec[1])
                    if not s.restart: s.sel = s.g['47E7']
            if not s.restart: break
        s.prev_mode = s.mode

    def boot(self):
        s, vm = self.s, self.vm
        s.mode, s.restart = 4, 0
        if vm.m0(0x4BF2) == 0: s.dataset, s.block = 2, 0x11                 # ov03:3E00 new game -> data set 2, block 11h
        else: s.block = vm.m0(0x4BF2) & 0xFF
        if vm.m0(0x4BE6) == 0: s.mode = 3
        vm.load_block(s.block); vm.init_vm(); self.entry = (s.dataset, s.block, vm.vec[4])
        vm.run(vm.vec[4])
        if not s.restart: vm.set0(0x4BF2, s.block)
        else: self.after_new_block()
        vm.resuming = False

    def moves(self):
        """ov16:08C3..0C1A: preserve movement indices; expose Cast/View and roster keys for the player."""
        opts = ['turn-left', 'turn-right', 'forward', 'look', 'search', 'camp'] if self.geo.map else ['look', 'search', 'camp']
        return opts + (['cast', 'view', 'turn-around', 'char-up', 'char-down'] if self.engines else [])

    def turn(self):
        """One explore command (ExploreCommand ov16:08C3 + game loop ov03:3F25..40A6; GATE.md item 2)."""
        s, vm = self.s, self.vm
        if not any(c.b[V.ACTIVE] for c in s.party): raise V.Halt('AllDead (ov03:3D56): no active member')   # GU-60 stop, never patched
        # ov16:0C46..0C59/0F04: the no-step flag skips PrintLocation. Retain the last painted line before vecA changes coordinates.
        if 'location' not in vm.display: self.paint_location()
        opts = self.moves(); c = opts[self.ask('MOVE', opts, x=s.x, y=s.y, dir=s.dir)]
        if c in ('char-up', 'char-down'):
            s.sel = (s.sel + (-1 if c == 'char-up' else 1)) % len(s.party); return  # ov28:03C9 roster selection
        if c in ('cast', 'view'):
            from sm.titles.ssb.units import camp, shops
            if c == 'view': shops.view(self, character=s.selc())       # ov16:09E9..09F8 -> ov21:0D0F, SelectedChar directly
            elif s.selc() and s.selc().b[V.STATUS] == 0: camp.cast_command(self, s.selc())  # ov16:09D1..09DE -> ov18:09D1
            return
        vm.set1(0x7EC9, 0)                                                   # ov16:08CA
        if c in ('forward', 'look', 'camp'): vm.clear_text()              # ov16:0C03/0C08: clear on leaving ExploreCommand; turns stay in its loop
        if c in ('turn-left', 'turn-right', 'turn-around'):                # inside ExploreCommand; 89DA recomputed (ov16:0B26..0BC5)
            s.dir = (s.dir + {'turn-left': 6, 'turn-right': 2, 'turn-around': 4}[c]) % 8; s.ahead = self.geo.wall(s, s.x, s.y, s.dir); vm.display = {'kind': None}; return
        if c == 'search': vm.set1(0x7ECA, vm.m1(0x7ECA) ^ 1); return        # ov16:0A0E: toggle, no script
        s.g['47E7'] = s.sel
        if not s.restart: vm.set0(0x4BF2, s.block)
        if c == 'camp': self.camp(); return
        if c == 'look':                                                      # ov03:3F99..3FD9
            vm.set1(0x7ECA, vm.m1(0x7ECA) | 2); vm.advance_clock(1, 2)        # ExploreCommand ov16:08C3, 0A47..0A4D
            keep = vm.m1(0x7ECA) & 1; vm.set1(0x7ECA, 1); self.refresh_attr(); vm.run(vm.vec[1])
            if s.restart: self.after_new_block()
            vm.set1(0x7ECA, keep); return
        vm.set1(0x7ED5, 0)                                                   # ov16:071B map edge
        dx, dy = walk.DELTAS[s.dir // 2]
        if self.geo.passage(s, s.x & 15, s.y & 15, s.dir) and not (0 <= s.x + dx < 16 and 0 <= s.y + dy < 16): vm.set1(0x7ED5, 1)
        vm.run(vm.vec[0])
        if s.restart: self.after_new_block(); return
        vm.set0(0x4BF0, s.x); vm.set0(0x4BF1, s.y)
        self.move_party(); self.refresh_attr()                              # UpdateView ov29:0034 at ov03:4043
        vm.run(vm.vec[1])
        if s.restart: self.after_new_block()

    def refresh_attr(self):
        """UpdateView ov29:0034: in a 3D area ([4BE6] or [4C38] <> 0) DS:89DB := GetCellAttr(X, Y)."""
        s = self.s
        if s.r0[0xE6] or s.r0[0x138]:
            s.attr = self.geo.attr(s, s.x, s.y)
            self.vm.display['sky'] = s.r0[0xFD:0xFF]  # ov03:4043 -> ov29:007B..00A1 paints before vecB can change 4BFD/4BFE.

    def move_party(self):
        """MoveParty ov16:0C3B (GATE.md 2a): 3D only; [7EC9] >= FFh = no step; passage 1 steps; 2/3 = the door menu."""
        s, vm = self.s, self.vm
        if s.mode != 4: return
        if vm.m1(0x7EC9) >= 0xFF: vm.set1(0x7EC9, 0); return
        p = self.geo.passage(s, s.x & 15, s.y & 15, s.dir)
        if p == 1: self.step()
        elif p in (2, 3) and self.door(p): self.step()
        self.paint_location()  # ov16:0F04, also when an ordinary wall/door prevented a step.

    def paint_location(self):
        self.vm.paint_location()

    def door(self, p):
        """ov16:0C88..0EF7: Bash / Pick / Knock / Exit; rolls from the explicit RNG. -> opened."""
        s, f = self.s, self.s.g
        R = lambda n: s.random(n) + 1
        thief = any(c.b[V.LEVEL + 6] or c.b[V.OLDLV + 6] for c in s.party)
        knock = [c for c in s.party if 0x1F in c.b[V.MEMSPELL:V.MEMSPELL + 75]]
        opts = (['Bash'] if f.get('bash', 1) else []) + (['Pick'] if f.get('pick', 1) and thief else []) + (['Knock'] if f.get('knock', 1) and knock else []) + ['Exit']
        if opts == ['Exit']: f['door %d %d %d' % (s.x, s.y, s.dir)] = 0; return False      # ov16:0000: the door becomes a wall
        c = opts[self.ask('MENU', opts, door=p, at=0)]
        ok = False
        if c == 'Bash':
            able = False
            for m in s.party:
                st, ex = m.b[0x11], m.b[0x1C]
                if p == 3: t = ((6, 1) if st == 18 and 91 <= ex <= 99 else (6, 2) if st == 18 and ex == 0x64 else (6, 3) if st in (19, 20) else (6, 4) if st in (21, 22)
                                else (6, 5) if st == 23 else (8, 7) if st == 24 else (1, 1) if st >= 25 else None)
                else: t = ((6, 1) if 3 <= st <= 7 else (6, 2) if st <= 15 else (6, 3) if st <= 17 else ((6, 3) if ex <= 50 else (6, 4) if ex <= 99 else (6, 5)) if st == 18
                           else (8, 7) if st <= 20 else (10, 9) if st == 21 else (12, 11) if st <= 23 else (20, 19) if st == 24 else (1, 1))
                able |= t is not None
                if t and R(t[0]) <= t[1]: ok = True; break
            if not able: f['bash'] = 0                                       # nobody strong enough: Bash withdrawn (DS:8DC2)
        elif c == 'Pick':
            if p == 2: ok = any(R(100) <= m.b[0xF4] and m.b[V.STATUS] == 0 for m in s.party)
            f['pick'] = 0
        elif c == 'Knock': m = knock[0]; m.b[V.MEMSPELL + list(m.b[V.MEMSPELL:V.MEMSPELL + 75]).index(0x1F)] = 0; ok = True
        if ok:                                                               # ov16:010E: this side and the opposite side ahead := 1
            f['door %d %d %d' % (s.x, s.y, s.dir)] = 1
            dx, dy = walk.DELTAS[s.dir // 2]; nx, ny = s.x + dx, s.y + dy
            if 0 <= nx < 16 and 0 <= ny < 16: f['door %d %d %d' % (nx, ny, (s.dir + 4) % 8)] = 1
        return ok

    def step(self):
        """ov16:07C9: X/Y += delta (wrap), wall ahead, door options reset, cell attribute, clock."""
        s = self.s; dx, dy = walk.DELTAS[s.dir // 2]; self.vm.display = {'kind': None}   # a step frees the encounter picture (ov16:0F16..0F39)
        s.x, s.y = (s.x + dx) & 15, (s.y + dy) & 15
        s.ahead = self.geo.wall(s, s.x, s.y, s.dir); s.attr = self.geo.attr(s, s.x, s.y)
        s.g['bash'] = s.g['pick'] = s.g['knock'] = 1; self.vm.advance_clock(1, 2 if self.vm.m1(0x7ECA) & 1 else 1)

    def play(self, limit=100_000):
        try:
            if self.slot is None:
                from sm.titles.ssb.units import creation
                creation.run(self)                                      # MainProgram 0000:02A9 -> ov19:01A1, before 0000:0375 GameLoop.
                if self.s.stop: return 'EXIT'
            self.boot()
            while len(self.trace) < limit: self.turn()
        except Done: return 'DONE'
        return 'LIMIT'



def test():
    """V3: boot from the shipped starter save A reaches data set 2 / block 17 / entry 8014 and prints the opening text."""
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

def test_look():
    """ov16:08C3 (0A47..0A4D): Look advances time before vecB, with either search setting."""
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
    """ReadCharacter ov20:1CEB resets paladin cures in all three runtime load paths; the codec retains bytes."""
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
        g.player=lambda k,o,current,**info: o.index(None) if current.s.party else 0  # ov19:3875..3893 keeps Add open below capacity.
        creation.add(g)
        assert g.s.party[0].b[0x6D] == want, 'standalone cure'

def test_load_recalc():
    """ov20:22A2/22AD -> ov26:21A4 then ov27:0366: stale saved THAC0 and class mask are recomputed."""
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
    """LoadGame ov20:2813 / 2C7D -> 2676: globals and newly allocated icon slots replace stale saved values."""
    from unittest.mock import patch
    from sm.titles.ssb.units import creation
    d = save.load(); d['r0'][0xFC] = 0x107; d['r0'][0xFF] = 3; d['r1'][0x312] = 0x102
    d['r1'][0x33E] = 99; d['dataset'] = 1; d['prev_mode'], d['mode'] = 3, 2
    d['walls'] = [(11, 1), (12, 2), (13, 3)]; d['r0'][0xC5] = 49              # GEO2 record 49: a real 3D map
    for r in d['party']: r.data[0x155] = 7
    d['party'][-1].data[0xFF] = 0xB2; d['party'][-1].data[0x12B] = 0x4D  # ov20:2CE7..2D20: a saved NPC uses its CPIC record, not zero head/body colours.
    def check(s):
        """ov20:267F..2778: each load relinks every member, including duplicate saved icon slots."""
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
    """API: a Session driven by step() makes the same decisions with the same hashes as the callback Game."""
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

