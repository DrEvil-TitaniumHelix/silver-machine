"""PORT2 headless CombatMain (ov10), AI (ov11), setup (ov12), attacks (ov15), ov25/32/33.

Evidence: ENGINE_READ2_g1.md, ENGINE_READ2_g3.md (ov15), ENGINE_READ_w6.md,
ENGINE_READ_w3.md and GATE.md, in GoldBoxUnified/decode/secret. Original tables are
read through dax, never embedded. Indices are zero based into State.chars(). The
facade holds no mutable simulation state: combat.* globals are part of State.hash.
AfterCombat is the VM's responsibility; run leaves the records for its sweep.
"""
from sm.titles.ssb import data as ssb_data
from sm import dax; from sm.titles.ssb import rec
from sm.titles.ssb.units.shops import message
from sm.titles.ssb.vm import ACTIVE, HP, HPMAX, STATUS, SIDE, CTRL, Halt

DX = (0, 1, 1, 1, 0, -1, -1, -1, 0)
DY = (-1, -1, 0, 1, 1, 1, 0, -1, 0)
DISABLED = (0x1F, 0x33, 0x34, 0x35)


def roll(s, dice, sides):
    """ov25:11C6 Roll; zero dice consumes no RNG, zero sides still consumes it."""
    return sum(s.random(sides) + 1 for _ in range(dice)) & 255


def footprint(size):
    """ov33:0000 GetIconCell: DS:1B12 + 8*size + 2*cell; negative x ends a cell."""
    if not size: return ()
    d = ssb_data.stexe(); base = 0x1B12 + 8 * size
    return tuple((rec.sx(d[base + 2*k]), rec.sx(d[base + 2*k + 1]))
                 for k in range(4) if rec.sx(d[base + 2*k]) >= 0)


def terrain_cost(tile):
    """ov10:13A3 / ov12:0BCD: DS:1A9E + four bytes per stored tile."""
    return ssb_data.stexe()[0x1A9E + 4 * tile]


def line(x0, y0, x1, y1):
    """ov32:0196/023F InitLine/StepLine; yield x,y,half-steps including origin."""
    dx, dy = abs(x1-x0), abs(y1-y0)
    sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    x, y, err, steps = x0, y0, 0, 0
    yield x, y, steps
    while (x, y) != (x1, y1):
        if dx >= dy:
            x += sx; err += 2 * dy; steps += 2
            if err >= dx: err -= 2 * dx; y += sy; steps += 1
        else:
            y += sy; err += 2 * dx; steps += 2
            if err >= dy: err -= 2 * dy; x += sx; steps += 1
        yield x, y, steps & 255


def in_cone(x, y, tx, ty, direction=255):
    """ov32:0543 InCone, eight rotated half-plane tests, FF/8 unrestricted."""
    if not (0 <= x < 50 and 0 <= y < 25 and 0 <= tx < 50 and 0 <= ty < 25): return False
    if direction in (8, 255) or (x, y) == (tx, ty): return True
    fx, fy = x + DX[direction], y + DY[direction]
    if (tx, ty) == (fx, fy): return True
    a, b = tx-fx, ty-fy
    return (b <= -abs(a), (a >= 0 and b <= -a) or (b <= 0 and a >= -b),
            a >= abs(b), (b >= 0 and a >= b) or (a >= 0 and b >= a),
            b >= abs(a), (a <= 0 and b >= -a) or (b >= 0 and a <= -b),
            a <= -abs(b), (b <= 0 and a <= b) or (a <= 0 and b <= a))[direction]


def direction_to(x, y, tx, ty):
    """ov26:38C8 DirectionTo: fixed-point 106/256 and 622/256 cone slopes."""
    if (x, y) == (tx, ty): return 8
    dx, dy = abs(tx-x), abs(ty-y)
    low, high = dx * 106 // 256, dx * 622 // 256
    tests = (ty <= y and high <= dy, ty < y and tx > x and low <= dy <= high,
             tx >= x and low >= dy, ty > y and tx > x and low <= dy <= high,
             ty >= y and high <= dy, ty > y and tx < x and low <= dy <= high,
             tx <= x and low >= dy, ty < y and tx < x and low <= dy <= high)
    return next((i for i, yes in enumerate(tests) if yes), 8)


def attack_roll(game, attacker, target, ac):
    """ov25:103A AttackRoll: natural 1 misses; 20 -> 100; 60-based to-hit >= AC."""
    s = game.s
    while rec.has_effect(attacker, 0x19): _remove_effect(game, attacker, 0x19)
    s.g['87DF'] = r = roll(s, 1, 20)
    if r == 1: return False
    if r == 20: s.g['87DF'] = 100
    _mod(game, 10, attacker); _mod(game, 16, target)
    bonus = s.r1[0x371 if attacker.b[SIDE] == 0 else 0x370]
    return s.g['87DF'] >= 0 and s.g['87DF'] + attacker.b[0x1AA] + rec.sx16(bonus) >= ac


def saving_throw(game, character, save_idx, bonus=0):
    """ov25:1137 SavingThrow: natural 1/20 bypass bonuses and effect dispatch."""
    if not 0 <= save_idx < 5: raise ValueError('save index outside 0..4')
    g = game.s.g; g['87E8'] = 1; g['87D2'] = r = roll(game.s, 1, 20)
    if r in (1, 20): return r == 20
    g['87D2'] += rec.sx(character.b[0x19A]) + rec.sx(bonus)
    g['87E7'] = save_idx; _mod(game, 12, character)
    return character.b[0xE8 + save_idx] <= g['87D2']


def _magic():
    """ov25:0423 effect callback dispatch to the separately ported ov14/ov23 unit."""
    from sm.titles.ssb.units import magic
    return magic


def _mod(game, kind, character):
    """ov25:0466 ApplyModifiers shared with magic (all effect writes stay hashed)."""
    if any(c.effects for c in game.s.chars()): _magic().apply_modifiers(game, character, kind)


def _remove_effect(game, character, kind):
    """ov25:00A6 RemoveEffect; magic owns callbacks and derived-stat restoration."""
    return _magic().remove_effect(game, character, kind)


class Combat:
    """ov12:1564 state facade. Lists in s.g are the emulated map and combatant records."""

    def __init__(self, game):
        """ov12:1564 CombatSetup; construction alone also reattaches a saved facade."""
        self.game, self.s = game, game.s
        game.combat = self

    def show(self, kind, character=None, delay=0, **details):
        """ov33:0959/0AB9 and ov26:173F: display-only calls, disabled in headless games."""
        if getattr(self.game, 'presentation', None) is not None:
            # ov11:08CE..0920 writes Move Left on entering AiMove, not on a move/swing redraw.
            self.game.present(kind, self.index(character) if character is not None else None, delay, **details)

    def projectile(self, character, end, sprite=5, frames=4, speed=30, kind='missile', separate_redraw=False, **details):
        """ov26:1A5E..1D66: 8-pixel line steps, COMSPR frames, explicit millisecond delay.

        ov13:0682 maps sprite slots 0Dh..18h to COMSPR records 0..11.
        ov26:1A11's four frames are normal, mirrored normal, mirrored alternate,
        alternate. The display line never participates in target selection.
        """
        if getattr(self.game, 'presentation', None) is None: return
        start = details.pop('start', self.position(character))
        if tuple(start) == tuple(end): return  # ov26:1B1A..1B28: fewer than two line points -> jmp 213B, no RedrawMap, no step, no closing flush (gt3000/005: self-target spells)
        self.game.presentation_poses = {}  # ov26:1C32..1C38 forces ov33:0959 redraw (normal icons) before the first missile cell.
        view = getattr(self.game, 'presentation_view', None)
        # ov26:1B3F..1BDA: if an endpoint is outside the view and the entire
        # flight fits, center on its midpoint BEFORE drawing the first step.
        # Arena 051-shallow/00752 moves (27,9)->(31,8) for (32,12)->(37,10).
        if (view is not None and any(not (view[0] <= x <= view[0]+6 and view[1] <= y <= view[1]+6) for x,y in (start,end))
                and all(abs(end[i]-start[i]) <= 6 for i in (0,1))):
            self.game.presentation_view = tuple(max(0, min(bound, start[i]+int((end[i]-start[i])/2)-3))
                                                for i,bound in enumerate((43,18)))
        if details.get('cue'): self.show('sound', character, merge=True, cue=details.pop('cue'))  # ov23:1D2F PlayOrStopSound(19CA) before each extra projectile (gt3000/023)
        self.show('redraw', character, merge=not separate_redraw,  # ov26:1C38: breath has a complete normal-pose frame (sm_n2_seq_monster_turns/47); cast keeps its measured merge.
                  recenter=getattr(self.game, 'presentation_view', None) != view)  # ov26:1B2B..1BDA midpoint recenter took the other RedrawMap path (GU-84 gap key)
        mirror = details.pop('mirror', False)
        sprites = tuple((sprite + (128 if (p >= 2 if frames == 4 else p == 1) else 0),
                         p in (1, 2) if frames == 4 else mirror) for p in range(frames))
        self.game.presentation_sprites = sprites
        # ov26:1CCD..1D21 draws the arrival step too (arena 051-normal/00463,
        # 00572); excluding it loses the final missile/bolt phase at each cell.
        points = list(line(start[0]*3, start[1]*3, end[0]*3, end[1]*3))
        directions = [(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:])]
        phase = 0

        def draw(x, y):
            # ov26:1D21..1D66: phase advances per blit, including a clipped edge step.
            # Projectile owns its viewport; DrawIcon's DS:8E29 never follows the moving sprite.
            nonlocal phase
            current = self.game.presentation_view
            self.show(kind, character, speed / 1000, sprite=sprite + (128 if (phase >= 2 if frames == 4 else phase == 1) else 0),
                      mirror=phase in (1, 2) if frames == 4 else mirror, point=(x/3,y/3),
                      focus=tuple(v+3 for v in current), margin=255, **details)
            phase = (phase+1) % frames

        # ov26:1D6F..1E2E: draw through the first point outside the viewport, then
        # jump to the endpoint view. Do not scroll along every intermediate cell.
        current = self.game.presentation_view; n = 0; x,y = points[0][:2]
        while n < len(directions)-1:
            dx,dy = directions[n]; x+=dx; y+=dy; draw(x,y); n+=1
            if not all(0 <= p-3*v <= 18 for p,v in zip((x,y),current)): break
        if n < len(directions)-1:
            current = tuple(max(0,min(bound,end[i]-3)) for i,bound in enumerate((43,18)))
            self.game.presentation_view = current
            self.show('redraw',character)  # ov26:1EC4..1ED4: completed endpoint map before the arrival segment.
            # ov26:1ED9..2056 walks the direction array backward from the endpoint
            # to its visible edge. Whole-cell anchors and the signed remainders
            # are retained separately, just as the native three-subcell loop does.
            anchor=list(end); remainder=[0,0]; relative=[3*(end[i]-current[i]) for i in (0,1)]
            n=len(directions)-1
            while True:
                delta=tuple(-v for v in directions[n]); relative=[relative[i]+delta[i] for i in (0,1)]
                for i in (0,1):
                    if relative[i]>18: anchor[i]=current[i]+6
                    elif relative[i]<0: anchor[i]=current[i]
                if any(v<0 or v>18 for v in relative): break
                for i in (0,1):
                    remainder[i]+=delta[i]
                    if abs(remainder[i])==3: anchor[i]+=remainder[i]//3; remainder[i]=0
                n-=1
            x,y=(3*anchor[i]+remainder[i] for i in (0,1))
            while n < len(directions)-1:
                dx,dy=directions[n]; x+=dx; y+=dy; draw(x,y); n+=1
        # ov26:2059..2104 draws the final endpoint with the next sprite phase.
        if not all(current[i] <= end[i] <= current[i]+6 for i in (0,1)):
            self.show('redraw',character,focus=end,margin=3)
        draw(end[0]*3,end[1]*3)
        # ov26:2127..2136: the last restore blit gets its own FlushViewDirtyLines before Projectile returns, so the
        # erased sprite is a frame of its own (arena 015/00430, 051-normal/00575 and 00682 before the next segment).
        self.show('erase', character, **{k: v for k, v in details.items() if k in ('spell', 'facing')})

    def flash(self, character, kind=0):
        """ov26:270F..28C8: kind 0 plays four 70-ms frames once; kind 1 repeats speed+1 times."""
        if getattr(self.game, 'presentation', None) is None: return
        self.game.presentation_sprites = tuple(((9 if kind else 10) + 128*(p>=2), p in (1,2)) for p in range(4))
        for _ in range(self.s.g.get('67D6', 0) + 1 if kind else 1):
            for phase in range(4):
                self.show('flash', character, .07, sprite=(9 if kind else 10) + (128 if phase >= 2 else 0),
                          mirror=phase in (1, 2), point=self.position(character))
        self.show('restore', character, 0 if kind else self.s.g.get('67D6', 0) / 10)

    def missile(self, attacker, target, item):
        """ov15:2872..2A58: directional arrows, spinning weapons, two-frame/default missiles."""
        if getattr(self.game, 'presentation', None) is None: return
        typ = item[0x2E]; d = direction_to(*self.position(attacker), *self.position(target))
        if typ in (0x42, 5, 7, 12, 30):
            # ov15:28CA..2947 -> ov26 e23: copy a directional sprite with optional horizontal mirror.
            sprite = (1 + (128 if d in (3, 5) else 0) if d % 2 else d % 4 + (128 if d >= 4 else 0))
            self.projectile(attacker, self.position(target), sprite, 1, 10, mirror=d in (5, 7))
        else:
            sprite, frames, speed = ((3, 4, 50) if typ in (2, 3, 6) else
                                      (8, 2, 10) if typ in (28, 29) else (7, 2, 20))
            self.projectile(attacker, self.position(target), sprite, frames, speed)

    @property
    def chars(self):
        """ov26:2B1C: the linked list includes both party and monsters during combat."""
        return self.s.chars()

    @property
    def tiles(self):
        """ov12:094B map allocation: 50 columns, 25 rows, stored tile IDs."""
        return self.s.g['combat.tiles']

    def index(self, character):
        """ov33:0C28 index lookup; identity rather than record-byte equality."""
        return self.chars.index(character)

    def record(self, character):
        """ov12:09BF allocated 17h-byte combatant; +A uses -1 for a nil target."""
        return self.s.g['combat.records'][self.index(character)]

    def position(self, character):
        """ov33:0BB0/0BD8 CombatantX/Y, DS:7EDF/7EE0."""
        return tuple(self.s.g['combat.positions'][self.index(character)][:2])

    def tile(self, x, y):
        """ov33:0483 ReadCell: outside the 50x25 combat field returns terrain 0."""
        return self.tiles[y * 50 + x] if 0 <= x < 50 and 0 <= y < 25 else 0

    def set_tile(self, x, y, value):
        """ov12:0000 PutTile / ov33:0DEB body terrain writes (already stored IDs)."""
        if 0 <= x < 50 and 0 <= y < 25: self.tiles[y * 50 + x] = value

    def cells(self, character, x=None, y=None):
        """ov33:0000/0368 enumerate the character footprint at its anchor."""
        p = self.s.g['combat.positions'][self.index(character)]
        if x is None: x, y = p[:2]
        return [(x+dx, y+dy) for dx, dy in footprint(p[2])]

    def rebuild(self):
        """ov33:0368 RebuildOccupancy; 0 empty, character index + 1 occupied."""
        occ = [0] * 1250
        for i, c in enumerate(self.chars):
            for x, y in self.cells(c):
                if 0 <= x < 50 and 0 <= y < 25: occ[y*50+x] = i+1
        self.s.g['combat.occupancy'] = occ

    def ahead(self, character, direction=8):
        """ov33:0C80 CellAhead: worst footprint terrain, occupant, cloud, poison."""
        who, tile, best, cloud, poison = -1, 0x17, 1, False, False
        own = self.index(character); occ = self.s.g['combat.occupancy']
        for x, y in self.cells(character):
            x += DX[direction]; y += DY[direction]; t = self.tile(x, y)
            o = occ[y*50+x]-1 if 0 <= x < 50 and 0 <= y < 25 else -1
            if o >= 0 and o != own: who = o
            if t == 0 or tile == 0: tile = 0
            if t == 0x1D: cloud = True
            elif t == 0x1B: poison = True
            elif tile and terrain_cost(t) >= best: best, tile = terrain_cost(t), t
        return who, tile, cloud, poison

    def place(self, character, x, y, restore=False):
        """ov33:10FA PlaceAt; a failed placement removes the footprint."""
        i = self.index(character); p = self.s.g['combat.positions'][i]
        p[:] = [x, y, character.b[0xE7] & 0x7F]
        who, tile, _, _ = self.ahead(character)
        if who >= 0 or not tile or terrain_cost(tile) == 255:
            p[2] = 0; self.rebuild(); return False
        if restore:
            bodies = self.s.g['combat.bodies']
            for body in bodies[:]:
                if body[0] == i:
                    _, bx, by, under = body; bodies.remove(body)
                    if not any(b[1:3] == [bx, by] for b in bodies) and under not in (0x1C, 0x1E): self.set_tile(bx, by, under)
        self.rebuild(); return True

    def walk_line(self, x, y, tx, ty, range=255, ignore_terrain=False):
        """ov32:03E3 WalkLine. L2 interpolates equal origin heights (0447/0488).

        The decode's h0' ambiguity is resolved by L2.cy at bp-21h: it is the
        origin height, not the horizontal distance. Return (reached, halfsteps).
        """
        if not in_cone(x, y, tx, ty): return False, 255
        ds = ssb_data.stexe(); height = ds[0x1A9F + 4*self.tile(x, y)]
        for cx, cy, steps in line(x, y, tx, ty):
            if steps > 2*range+1 or (not ignore_terrain and ds[0x1AA0 + 4*self.tile(cx, cy)] > height): return False, steps
        return True, steps

    def target_entries(self, character, range=255, direction=255, ignore_terrain=False):
        """ov32:08D1 BuildTargetList / 002E SortTargets: min footprint distance."""
        out = []; own = self.cells(character)
        for i, other in enumerate(self.chars):
            best = None
            for x, y in own:
                for tx, ty in self.cells(other):
                    if not in_cone(x, y, tx, ty, direction): continue
                    ok, distance = self.walk_line(x, y, tx, ty, range, ignore_terrain)
                    if ok and (best is None or distance < best[0]):
                        d = direction if direction < 8 else next((d for d, _ in enumerate(DX[:8]) if in_cone(x, y, tx, ty, d)), 8)
                        best = distance, d
            if best is not None: out.append((i, *best))
        i = 0                                                              # ov32:002E..0192 exact exchange sort (unstable; the tie rule is not a key). `range` is a parameter here.
        while i < len(out)-1:
            j = i+1
            while j < len(out):
                if out[j][1] < out[i][1] or out[j][1] == out[i][1] and out[j][2] < out[i][2] and out[j][2] % 2 <= out[i][2] % 2:
                    out[i], out[j] = out[j], out[i]
                j += 1
            i += 1
        return out

    def targets(self, character, range=255, side=None, direction=255, ignore_terrain=False):
        """ov26:2B70 EnemiesInRange; side=None returns either side for spell targeting."""
        chars = self.chars
        return [chars[i] for i, _, _ in self.target_entries(character, range, direction, ignore_terrain)
                if chars[i].b[ACTIVE] and (side is None or chars[i].b[SIDE] == side)]

    def distance(self, a, b):
        """ov26:2D10 DistanceTo: terrain ignored, footprint min halfsteps divided by 2."""
        own, other = self.cells(a), self.cells(b)
        return min((list(line(x, y, tx, ty))[-1][2] // 2 for x, y in own for tx, ty in other), default=255)

    def recount(self):
        """ov26:2B1C CountSides; this does not refresh the round's morale HP."""
        g = self.s.g; chars = self.chars
        g['87CC'], g['87CD'] = (sum(bool(c.b[ACTIVE]) for c in chars if c.b[SIDE] == side) for side in (0, 1))
        return g['87CC'], g['87CD']

    def monster_hp_percent(self):
        """ov15:2A58, called at ov12:16C7 setup and ov10:0F76 round end."""
        g = self.s.g; chars = self.chars
        total = sum(c.b[HPMAX] for c in chars if c.b[SIDE] == 1)
        if total: g['8E13'] = sum(c.b[HP] for c in chars if c.b[SIDE] == 1 and c.b[ACTIVE]) * 20 // total * 5

    def reset(self, character):
        """ov26:2DEC CombatantReset clears queued spell, initiative, guard and moves."""
        c = self.record(character)
        for offset in (0, 3, 7, 6): c[offset] = 0
        return True

    def remove(self, character):
        """ov33:0DEB DeathAnimation: nine frames (0..8, modulo 2 at 0F50), then the body tile."""
        i = self.index(character); p = self.s.g['combat.positions'][i]
        animated = p[2] and character.b[STATUS] != 3
        if animated:
            for phase in range(9):
                self.show('death', character, .01, sprite=11 + 128*(phase % 2), point=tuple(p[:2]), cells=footprint(p[2]))
            # ov33:106F MessageDelay follows the ninth frame with no flush in between (gtrace 015: Delay 10 at
            # 0F83, then 0540:0BF7 by ov33:1074): the last picture (i = 8 -> 7ED2[0]) stays on screen for the hold.
            self.show('death', character, self.s.g.get('67D6',0)/10, sprite=11, point=tuple(p[:2]), cells=footprint(p[2]))
        if p[2] and not self.record(character)[0x13] and character.b[STATUS] != 3:
            x, y = p[:2]; self.s.g['combat.bodies'].append([i, x, y, self.tile(x, y)])
            if self.tile(x, y) != 0x1D: self.set_tile(x, y, 0x1C if character.b[STATUS] == 7 else 0x1E)
        p[2] = 0; self.reset(character); self.rebuild(); self.recount()
        if animated: self.show('redraw', character, merge=True)  # ov33:107F..10BE: DrawCellIcon, rebuild, RedrawMap after the delay; the corpse shows with the next frame (arena 015/00511).
        else: self.show('view', character, self.s.g.get('67D6',0)/10)  # ov33:0DF1..0E06: MessageDelay only.

    def strip(self, character):
        """ov25:13E9 StripOnDeath, also used by ov10:0000 on battle exit."""
        for kind in ssb_data.stexe()[0xA9A:0xAA8]:
            if rec.has_effect(character, kind): _remove_effect(self.game, character, kind)
        if rec.has_effect(character, 0x4D) and character.b[0xFF] == 0xB3: character.b[SIDE] = 0

    def kill(self, character, status=6):
        """ov25:0000 KillCharacter / 12E5 SetFled (flee retains current HP)."""
        if character.b[STATUS] in (6, 7, 8): return
        character.b[STATUS], character.b[ACTIVE] = status, 0
        if status != 3: character.b[HP] = 0
        self.strip(character)
        if not character.b[ACTIVE]: self.remove(character)

    def apply_damage(self, character, amount):
        """ov26:2953 ApplyDamage + ov15:02D5 spell disruption and death handling."""
        if amount <= 0 or not character.b[ACTIVE]: return
        b, c = character.b, self.record(character); over = max(0, amount-b[HP])
        hp = max(0, b[HP]-amount)
        if over > 9 or (not hp and b[STATUS] == 1): b[STATUS] = 6
        elif over: b[STATUS] = 5; c[14] = over
        elif not hp: b[STATUS] = 4
        b[HP] = hp; c[1] = 0
        if c[0]:
            slots = b[0x1E:0x69]
            message(self.game, '%s lost a spell' % bytes(b[1:1 + b[0]]).decode('latin1'))  # ov15:04C9..0531
            if c[0] in slots: b[0x1E + slots.index(c[0])] = 0
            self.reset(character)
        if b[STATUS] in (4, 5, 6, 7, 8):
            result = 'is killed' if b[STATUS] in (6, 7, 8) else 'goes down, and is Dying' if b[STATUS] == 5 else 'goes down'
            name=bytes(b[1:1 + b[0]]).decode('latin1')
            message(self.game, '%s %s' % (name,result),display_text=name+'\n'+result.replace(', and','\nand'),
                    names=((0,self.index(character),12),),continuation=True,delay=0)  # ov15:056C/059C completes death text before 05F7 calls the skull animation; sm-r2-14/251 captures the normal icon.
            b[ACTIVE], b[HP] = 0, 0; self.strip(character); _mod(self.game, 13, character)
            if not b[ACTIVE] and b[STATUS] != 10: self.remove(character)
        self.recount()

    def damage(self, character, amount, save_result=0, use_save=False):
        """ov25:1D84 Damage: resistance, optional negate/half save, special defense."""
        g = self.s.g; g['87D4'] = amount & 255; _mod(self.game, 6, character)
        if use_save:
            if save_result == 1: g['87D4'] = 0
            elif save_result == 2: g['87D4'] //= 2
        else: _mod(self.game, 20, character)
        self.apply_damage(character, max(0, g['87D4']))

    def wall(self, x, y, direction):
        """ov12:02AE WallAt and 0330 WallBoth (both faces, GEO boundary special)."""
        def face(x, y, d):
            # ov12:02AE: an out-of-map horizontal opening only along party Y.
            if not (0 <= x < 16 and 0 <= y < 16): return 0 if y == self.s.y and d in (2, 6) else 1
            if not self.game.geo.passage(self.s, x, y, d): return 1
            return 3 if self.game.geo.wall(self.s, x, y, d) else 0
        return face(x, y, direction) | face(x+DX[direction], y+DY[direction], (direction+4) % 8)

    def build_map(self):
        """ov12:0875 Build3DMap; 0000/03A4/0449/04C6/069E tiles, 0084 hazards."""
        self.s.g['combat.tiles'] = [0] * 1250
        if not self.s.r0[0xE6]:
            raise Halt('2D combat: unreachable, [4BE6] = 1 in every shipped state (ENGINE_READ2_f1.md: ov12:0939 empty by design, no 2D map data)')
        for dy in range(-2, 3):
            for dx in range(-6, 7):
                x, y = self.s.x+dx, self.s.y+dy
                w, n, e, south = (self.wall(x, y, d) for d in (6, 0, 2, 4))
                def put(i, j, t):
                    # ov12:0000 PutTile stores t+1 in the skewed dungeon projection.
                    self.set_tile(21+6*dx+5*dy+i, 10+5*dy+j, t+1)
                for j in range(2, 5):
                    for i in range(6): put(i, j, 0x16)
                    if w == 1: put(j-1, j, 4); put(j, j, 3); put(j+1, j, 13)
                if w == 3: put(1, 2, 8); put(5, 4, 0)
                for i in (3, 4): put(i, 0, 5 if n == 1 else 0x16); put(i, 1, 10 if n == 1 else 0x16)
                op = self.wall(x, y-1, 6) == self.wall(x-1, y, 0) == 0
                t1 = (0x16 if w == 0 else 13 if w == 3 else 0 if op else 13) if n == 0 else ((15 if op else 5) if w == 0 else (18 if op else 2))
                t2 = 0x16 if n == 0 else 17 if n == 3 else 5
                t3 = (0x16 if n == 0 else 16 if op else 10) if w == 0 else (20 if op else 7) if w == 3 else (1 if op else 3)
                t4 = (0x16 if n == 0 else 23 if n == 3 else 10) if w in (0, 3) else (13 if n == 0 else 21 if n == 3 else 6)
                for i, j, t in ((1, 0, t1), (2, 0, t2), (1, 1, t3), (2, 1, t4)): put(i, j, t)
                ne, nn = self.wall(x, y-1, 2), self.wall(x+1, y, 0); op = ne == nn == 0
                t1 = (4 if ne == 1 else 0x16) if n == 0 else 15 if n == 3 else 5
                t2 = ((0x16 if ne == 0 else (24 if e == 0 and nn else 1) if ne == 3 else ((11 if nn else 7) if e == 0 else 3))
                      if n == 0 else 9 if e else 5 if nn else 17 if op else 19)
                t3 = 0x16 if n == 0 else 16 if n == 3 else 10
                # ov12:07FF..080B / 081E..082A: the nn == 0 branches select 8 / 23, respectively.
                t4 = (0x16 if ne == 0 else 4 if e else 12 if nn else 8) if n == 0 else 14 if e else 10 if nn else 23
                for i, j, t in ((5, 0, t1), (6, 0, t2), (5, 1, t3), (6, 1, t4)): put(i, j, t)
                open_floor = 3 not in (n, e, south, w) and (1 not in (n, e, south, w) or n == south == 1 or e == w == 1)
                for i in (2, 3):
                    for j in range(2, 5):
                        tx, ty = 21+6*dx+5*dy+i+j, 10+5*dy+j
                        if self.tile(tx, ty) != 0x17 or not open_floor or not self.game.geo.attr(self.s, x, y) & 64: continue
                        if roll(self.s, 1, 10) > 5: continue
                        self.set_tile(tx, ty, 0x1A)
                        for d in (0, 2, 4, 6):
                            nx, ny = tx+DX[d], ty+DY[d]
                            if self.tile(nx, ny) == 0x17 and roll(self.s, 1, 10) <= 9: self.set_tile(nx, ny, 0x1B)

    def find_cell(self, character, anchors, quadrants, masks, counts):
        """ov12:0C60 FindCell state machine and 0B1C ClaimCell, four window passes.

        Details omitted by g1's summary (zigzag/line counters) follow 0CBD..10C0.
        All geometry constants still come from DS:0350..03BF.
        """
        ds = ssb_data.stexe(); side = character.b[SIDE]; q = quadrants[side]
        sx, sy = anchors[side]; k = depth = 0; phase = 1; first = True
        base_x = base_y = cx = cy = width = number = 0
        while True:
            axis = ds[0x360+4*q+k] // 2
            if phase == 1:
                d = ds[0x370+(axis+2) % 4]
                base_x = rec.sx(ds[0x374+4*int(k > 0)+axis]) + depth*DX[d]
                base_y = rec.sx(ds[0x37C+4*int(k > 0)+axis]) + depth*DY[d]
                cx, cy = base_x, base_y; width = number = 1; phase = 2
            elif phase == 2:
                d = ds[0x370+(axis+1) % 4]; cx, cy = base_x+width*DX[d], base_y+width*DY[d]; phase = 3; number += 1
            else:
                d = ds[0x370+(axis+3) % 4]; cx, cy = base_x+width*DX[d], base_y+width*DY[d]; phase = 2; width += 1; number += 1
            outside = not (0 <= cx <= 10 and 0 <= cy <= 5)
            escaped = not 0 <= cx <= 10 and not 0 <= cy <= 5  # ov12:0AEB..0B13: BOTH axes must leave the window before trying another room.
            if (outside and not escaped) or (first and number >= counts[side]) or (not first and number > 11):
                depth += 1
                if side == 0 and q % 2 and k == 0 and depth == 1:
                    if any(self.wall(self.s.x+anchors[side][0], self.s.y+anchors[side][1], ds[0x350+4*q+j]) != 1 for j in (1, 2, 3)): depth += 1
                phase = 1; first = False
            if escaped:
                phase = 0
                while k < 3 and phase != 1:
                    k += 1; d = ds[0x350+4*q+k]
                    if self.wall(self.s.x+anchors[side][0], self.s.y+anchors[side][1], d) != 1:
                        sx, sy = anchors[side][0]+DX[d], anchors[side][1]+DY[d]; depth = 0; phase = 1
                if phase != 1: return False
                continue
            if outside: continue  # ov12:0FA4..0FBD/108F: one-axis overflow advances depth but never claims an out-of-window cell.
            if not masks[side][k][cy*11+cx]: continue
            tx, ty = 22+6*sx+5*sy+cx, 10+5*sy+cy
            p = self.s.g['combat.positions'][self.index(character)]; p[:2] = [tx, ty]
            who, tile, _, _ = self.ahead(character)
            if who < 0 and tile > 0 and terrain_cost(tile) != 255:
                masks[side][k][cy*11+cx] = 0; self.rebuild(); return True

    def setup(self):
        """ov12:1564/09BF/10DC CombatSetup, InitCombatants, PlaceCombatants."""
        s, g = self.s, self.s.g
        for key in [k for k in g if k.startswith('combat.')]: del g[key]
        for key in ('8E14', '8DC7', '87DF', '86CD', '8E22', '8E21', 'A4D4'): g[key] = 0
        g['8DC8'] = 15; g['combat.active'] = 1; g['combat.bodies'] = []; g['combat.order'] = []
        s.mode = 5; s.r1[0x333] = 0
        self.build_map()
        g['combat.records'], g['combat.positions'] = [], []
        face = ssb_data.stexe()[0x370+s.dir//2]
        for i, char in enumerate(self.chars):
            rec.recalc_character(char, s.r1[0x372]); c = [0]*23; c[10] = -1; c[19] = int(i >= len(s.party)); c[22] = 1
            c[9] = (face + 4*char.b[SIDE]) % 8
            m = char.b[0xFF] & 127
            if char.b[SIDE] == 0 and c[19] and (m == 0 or m > 0x66): char.b[0xFF] = (s.r1[0x2C6]+128) & 255
            g['combat.records'].append(c); g['combat.positions'].append([0, 0, 0])
        self.recount(); self.rebuild()
        anchors = ((0, 0), (s.r1[0x2C1]*DX[s.dir], s.r1[0x2C1]*DY[s.dir]))
        quadrants = (s.dir//2, ((s.dir+4) % 8)//2); ds = ssb_data.stexe(); masks = []
        counts = ((g['87CC']+1)//2, (g['87CD']+1)//2)
        for side in (0, 1):
            group = []
            for k in range(4):
                q = 4 if k == 1 else quadrants[side]
                group.append([int(ds[0x384+12*q+2*y] <= x <= ds[0x385+12*q+2*y]) for y in range(6) for x in range(11)])
            masks.append(group)
        for i, char in enumerate(self.chars):
            g['combat.positions'][i][2] = char.b[0xE7] & 7
            if not self.find_cell(char, anchors, quadrants, masks, counts):
                g['combat.positions'][i][2] = 0
                if i >= len(s.party): g.setdefault('combat.unplaced', []).append(i); char.b[ACTIVE] = 0
            elif not char.b[ACTIVE]: self.remove(char)
            self.rebuild()
        dropped = g.pop('combat.unplaced', [])
        if dropped:
            # ov12:14BE: a monster with no placement is unlinked, not a casualty/loot source.
            self.s.monsters[:] = [c for i, c in enumerate(self.s.monsters, len(self.s.party)) if i not in dropped]
            for key in ('combat.records', 'combat.positions'): g[key] = [v for i, v in enumerate(g[key]) if i not in dropped]
            self.rebuild()
        # ov12:1650..167E writes a fresh map origin from PartyHead every battle.
        # Retaining the previous battle's presentation view shifts later fights.
        if g['combat.positions']:
            self.game.presentation_view = tuple(v-3 for v in g['combat.positions'][0][:2])
        for char in self.chars: _mod(self.game, 8, char)
        self.recount(); self.monster_hp_percent()

    def move_allowance(self, character):
        """ov26:25EA ComputeMove; a half-square count, including party cell 7F72."""
        return rec.compute_move(character, self.s.r1[0x372])

    def ranged(self, character):
        """ov26:3466 RangedWeaponReadied and 34A9 RangedCanMelee."""
        w = rec.readied(character)[0]
        return w is not None and rec._T(w, 12) > 1

    def ranged_melee(self, character):
        """ov26:34A9 RangedCanMelee: flags 14h or weapon type 43h."""
        w = rec.readied(character)[0]
        return self.ranged(character) and (rec._T(w, 14) & 0x14 == 0x14 or w[0x2E] == 0x43)

    def ammo(self, character):
        """ov26:34FD AmmoFor: (available, item), self ammunition or readied 11/12."""
        slots = rec.readied(character); w = slots[0]
        if w is None: return False, None
        f = rec._T(w, 14); ammo = w if f & 16 else None
        if f & 8:
            if f & 1: ammo = slots[11]
            if f & 128: ammo = slots[12]
        return ammo is not None or f == 10, ammo

    def reset_attacks(self, character):
        """ov15:0DF9 ResetAttacks / 0F12 HalfRoundUp (round parity)."""
        b, c, g = character.b, self.record(character), self.s.g
        old = b[0x1AD]; w = rec.readied(character)[0]
        ranged = self.ranged(character) and self.ammo(character)[0]  # ov15:0E24/0E38: e42 and e44 usable ammo (bytes + oracle: 5 Darts throw 3), not RangedCanMelee
        g['87D6'] = max(2, rec._T(w, 5)) if ranged else b[0x121]
        _mod(self.game, 18, character); count = (g['87D6'] + (g['8DC7'] & 1)) // 2
        if ranged:
            _, ammo = self.ammo(character)
            if ammo is not None and ammo[0x39]: count = min(count, max(1, ammo[0x39]))
        b[0x1AD] = min(count, old) if c[8] else count

    def init_round(self):
        """ov15:0000 round initialization, ov10:0741 insertion-sort initiative."""
        g = self.s.g; order = []
        for i, character in enumerate(self.chars):
            c, b = self.record(character), character.b
            c[0] = c[8] = 0; c[1] = int(not self.ahead(character)[2]); c[2] = 1; c[4] = 2
            self.reset_attacks(character); g['87D6'] = b[0x122]; _mod(self.game, 18, character)
            b[0x1AE] = (g['87D6'] + (g['8DC7'] & 1)) // 2; c[5] = b[0xE6]
            c[3] = max(1, rec.dex_hit(character) + roll(self.s, 1, 6)) if b[ACTIVE] else 0
            if b[ACTIVE] and self.s.r1[0x2CB] & (b[SIDE]+1): c[3] -= 6
            if not 0 <= c[3] <= 20: c[3] = 0
            c[6] = self.move_allowance(character)
        self.s.r1[0x2CB] = 0
        for i, character in enumerate(self.chars):
            key = self.record(character)[3]; p = 0
            while p < len(order):
                other = g['combat.records'][order[p]][3]
                if key > other or key == other and roll(self.s, 1, 2) == 1: break
                p += 1
            order.insert(p, i)
        g['combat.order'] = order; g['combat.cursor'] = 0

    def disabled(self, character):
        """ov26:0E75 HasDisablingEffect (nausea, hold, sleep, paralysis)."""
        return any(rec.has_effect(character, t) for t in DISABLED)

    def can_see(self, attacker, target):
        """ov15:1144 CanAttack; kind 1 visibility effects use the selected attacker."""
        old = self.s.sel; self.s.sel = self.index(attacker); self.s.g['87DB'] = 0
        _mod(self.game, 1, target); self.s.sel = old
        return self.s.g['87DB'] == 0

    def attack_targets(self, character, allies=False):
        """ov15:37DB/2C85: human Aim includes allies; AI keeps its enemy-only list."""
        if not character.b[ACTIVE] or not any(character.b[0x1AD:0x1AF]): return []
        ranged = self.ranged(character); melee = self.ranged_melee(character)
        w = rec.readied(character)[0]; reach = (rec._T(w, 12)-1) & 255 if ranged else 1
        if reach in (0, 255): reach = 1
        nearby = self.targets(character, 1, 1-character.b[SIDE])
        available, _ = self.ammo(character)
        return [t for t in self.targets(character, reach, None if allies else 1-character.b[SIDE])
                if t is not character and self.can_see(character, t)
                and (not ranged or (self.distance(character, t) <= 1 and melee)
                     or (available and not nearby))]

    def human_targets(self, character):
        """ov15:2C85/37DB: offer allied targets without input queries mutating visibility state."""
        from copy import copy
        game = copy(self.game); game.s = self.s.copy(); game.presentation = None
        game.vm = copy(self.game.vm); game.vm.s = game.s; game.vm.host = game
        game.vm.out = list(self.game.vm.out); game.combat = Combat(game)
        battle = game.combat
        return [self.chars[battle.index(t)] for t in battle.attack_targets(battle.chars[self.index(character)], allies=True)]

    def backstab(self, attacker, target):
        """ov15:2783 IsBackstab: thief, weapon whitelist, behind an acted small target."""
        b = attacker.b; w = rec.readied(attacker)[0]
        if not (b[0x117] or b[0x11E] and rec.dual(attacker)) or w is None: return False
        return (w[0x2E] in (3, 4, 0x11, 0x12, 0x13) and self.record(target)[15] > 1
                and self.distance(attacker, target) < 2 and target.b[0xE7] & 127 <= 1
                and direction_to(*self.position(attacker), *self.position(target)) == self.record(target)[9])

    def face_toward(self, attacker, target):
        """ov15:1638 records the defender's attack count and cumulative turning cost."""
        # Callers push attacker then target (ov11:1069..1075); bp+6 is
        # the target, whose +0F/+12 control turning and attacks from behind.
        c = self.record(target); d = direction_to(*self.position(target), *self.position(attacker))
        r = (d-c[9]+8) % 8; c[15] += 1; c[18] = (c[18]+min(r, 8-r)) % 8

    def attack(self, attacker, target, opportunity=False, missile=None):
        """ov15:16C7 Attack + 11DD ResolveAttack + 014C MeleeDamage; on-hit effects."""
        b, t, c, tc, g = attacker.b, target.b, self.record(attacker), self.record(target), self.s.g
        if not b[ACTIVE] or not t[ACTIVE]: return True
        g['8DC8'] = g['8DC7'] + 15
        if tc[15] < 2 and not opportunity: tc[9] = direction_to(*self.position(target), *self.position(attacker))
        # ov15:1736..1780 keeps the old direction in local -0D; DrawIcon
        # (ov33:0B4A..0B55) restores it after the temporary +4. An acted
        # target therefore keeps its facing, including when off screen.
        direction = direction_to(*self.position(attacker), *self.position(target))  # ov15:17E0..17E5: local until DrawIcon at 1803.
        aname, tname = (bytes(r[1:1+r[0]]).decode('latin1') for r in (b,t))
        self.show('facing', target)
        self.show('clear', attacker, panel_clear=True)  # ov15:16D2/17EE -> ov26:0CA4..0CB0: every attack refreshes the status rectangle before raising the weapon.
        self.show('status', attacker, status=True)  # ov15:17EE -> ov26:0CB5..0E6F completes the normal-pose panel before 1803.
        c[9] = direction
        self.show('swing', attacker, .1, pose=1)  # ov15:17F3..1821 -> ov33:0AB9, Delay(100).
        c[10] = self.index(target)  # ov15:1808..1819: target pointer follows DrawIcon.
        if missile is not None: self.missile(attacker, target, missile)
        weapon = rec.readied(attacker)[0]
        if weapon is not None and weapon[0x2E] in (28, 29): self.missile(attacker, target, weapon)
        if not any(b[0x1AD:0x1AF]):
            self.show('facing', attacker, pose=0)  # ov15:1A2E..1A77 also restores an exhausted attacker.
            return self.reset(attacker)
        old_sel = self.s.sel; self.s.sel = self.index(attacker)
        g['87E0'] = g['87E1'] = g['8E11'] = g['8E12'] = g['87D4'] = 0; c[8] = 1
        if self.disabled(target):
            message(self.game, '%s slays helpless %s with one cruel blow' % (
                aname, tname), display_text=aname+'\nslays helpless\n'+tname+'\nwith one cruel blow',names=((0,self.index(attacker)),(2,self.index(target))))  # ov15:02D5..0397.
            self.apply_damage(target, t[HP]+5)
            while rec.has_effect(attacker, 0x19): _remove_effect(self.game, attacker, 0x19)
            b[0x1AD] = b[0x1AE] = 0
        else:
            w = rec.readied(attacker)[0]
            if w is not None and (t[0xE7] > 128 or t[0xE7] & 7 > 1):
                b[0x1AF], b[0x1B1] = rec._T(w, 2), rec._T(w, 3)
                b[0x1B3] = (b[0x1B3]-rec._T(w, 11)+rec._T(w, 4)) & 255
            rec.recalc_character(target, self.s.r1[0x372]); _mod(self.game, 11, target)
            back = self.backstab(attacker, target)
            behind = opportunity or (tc[15] > 1 and c[9] == tc[9] and tc[18] > 4)
            ac = t[0x1AC]-4 if back else t[0x1AB+int(behind)]
            # ov15:1A82 range penalty is applied to the caller's byte (AC).
            distance = self.distance(attacker, target)
            reach = (rec._T(w, 12)-1)//3 if self.ranged(attacker) else distance
            penalty = (2 if distance > reach else 0) + (3 if distance > 2*reach else 0)
            ac += penalty
            stop = False
            for slot in range(c[4], 0, -1):
                while b[0x1AC+slot] and not stop:
                    b[0x1AC+slot] -= 1; c[4] = slot
                    g['combat.attacks'] = g.get('combat.attacks', 0)+1
                    g['8E1'+str(slot)] = g.get('8E1'+str(slot), 0)+1
                    hit = attack_roll(self.game, attacker, target, ac)
                    if hit:
                        g['87E'+str(slot-1)] += 1
                        g['87D9'] = b[0x1AE+slot]
                        g['87D4'] = max(0, roll(self.s, b[0x1AE+slot], b[0x1B0+slot]) + rec.sx(b[0x1B2+slot]))
                        _mod(self.game, 4, attacker); _mod(self.game, 5, target)
                        if back: g['87D4'] *= (b[0x117]+b[0x11E]*rec.dual(attacker)-1)//4+2
                        g['87D5'] = 0; damage = g['87D4']
                        verb = '-Backstabs-' if back else 'Attacks'
                        self.show('clear', attacker)  # ov15:0335 -> ov26:173F: clear before EACH damage caption, even identical successive hits.
                        message(self.game, '%s %s %s%s Hitting for %d point%s of damage' % (
                            bytes(b[1:1 + b[0]]).decode('latin1'), verb, bytes(t[1:1 + t[0]]).decode('latin1'),
                            ' (from behind)' if behind and not back else '', damage, '' if damage == 1 else 's'),
                            display_text='%s\n%s\n%s\n%sHitting for %d point%s of damage' %
                            (aname,verb,tname,'(from behind) ' if behind and not back else '',damage,'' if damage==1 else 's'),
                            names=((0,self.index(attacker)),(2,self.index(target))))  # ov15:0324..04B8.
                        if t[ACTIVE]: self.apply_damage(target, damage)
                        if t[ACTIVE] and damage > 0: _mod(self.game, slot+1, attacker)
                    else:
                        self.show('clear', attacker)  # ov15:0335/050A -> ov26:173F: the next caption replaces the old message rectangle.
                        message(self.game, '%s Attacks %s and Misses' % (
                            aname,tname), display_text=aname+'\nAttacks\n'+tname+'\nand Misses',names=((0,self.index(attacker)),(2,self.index(target))))  # ov15:0324..04B8; oracle seq_attack/00690.
                    if w is not None and w[0x2E] == 0x42: b[0x1AC+slot] = 0
                    stop = not b[ACTIVE] or not t[ACTIVE]
            c[5] = 0
        if missile is not None and missile[0x39]:
            missile[0x39] = max(0, missile[0x39]-g['8E11'])
            if not missile[0x39]:
                if self.ranged_melee(attacker) and missile[0x3D] != 0x17:
                    copy = bytearray(missile); copy[0x34] = 0
                    index = g.get('combat.treasure_boundary', len(self.s.treasure_items)-1)+1
                    self.s.treasure_items.insert(index, copy); g['combat.treasure_boundary'] = index  # ov15:1943..19E6; ov07:02B9 excludes the tail from item XP.
                attacker.items.remove(missile)
        rec.recalc_character(attacker, self.s.r1[0x372]); self.s.sel = old_sel
        done = not b[ACTIVE] or not any(b[0x1AD:0x1AF])
        if done: self.reset(attacker)
        self.show('clear', attacker)  # ov15:0603 -> ov26:1827.
        self.show('facing', attacker, pose=0)  # ov15:1A2E..1A77 restores the normal icon.
        self.recount(); return done

    def sweep(self, attacker, target):
        """ov15:0F46 fighter sweep against adjacent level-zero enemies, capped at +E6."""
        c = self.record(attacker)
        if attacker.b[0x1AD] >= c[5] or target.b[0xEE] or self.distance(attacker, target) != 1: return False
        foes = [t for t in self.targets(target, 1, target.b[SIDE]) if t.b[0xEE] == 0 and self.distance(attacker, t) == 1]
        if len(foes) <= attacker.b[0x1AD]: return False
        foes = [target] + [t for t in foes if t is not target]
        count = min(len(foes), c[5])
        for t in foes[:count]:
            if not attacker.b[ACTIVE]: break
            self.face_toward(attacker, t); attacker.b[0x1AD] = 1; c[4] = 1; self.attack(attacker, t)
        self.reset(attacker); return True

    def confirm_ally(self, attacker, target, moving=False, cursor=True):
        """ov15:2B73..2C4E: confirm a same-side uncontrolled target; turn hostile NPCs."""
        if target.b[SIDE] != attacker.b[SIDE] or target.b[CTRL]: return True
        if self.game.ask('COMBAT_ACTION', ['yes', 'no'], actor=self.index(attacker),
                         target=self.index(target), action='attack-ally', moving=moving, cursor=cursor, prompt='Attack Ally: '): return False
        self.s.g['8DC6'] = 1; self.s.r1[0x333] = 1
        for npc in self.s.party:
            if npc.b[STATUS] == 0 and npc.b[0xFF] > 127 and npc.b[0xFF] != 0xB3:
                npc.b[SIDE] = 1; self.record(npc)[10] = -1
        self.recount()
        return True

    def attack_command(self, attacker, target, moving=False, cursor=True):
        """ov10:1515 / ov15:2B73/2E7C: refusal, ally confirmation, sweep, face, attack."""
        if moving and self.ranged(attacker) and not self.ranged_melee(attacker):
            self.refusal(attacker, 'Not with that weapon'); return False  # ov10:151B..154D.
        if not moving and target not in self.attack_targets(attacker, allies=target.b[SIDE] == attacker.b[SIDE]):
            raise Halt('combat attack target is not legal')
        if not self.confirm_ally(attacker, target, moving=moving, cursor=cursor): return False
        self.record(attacker)[10] = self.index(target)
        if self.sweep(attacker, target): return True
        self.face_toward(attacker, target)
        missile = self.ammo(attacker)[1] if self.ranged(attacker) and not moving else None
        if self.ranged_melee(attacker) and self.distance(attacker, target) == 1: missile = None
        return self.attack(attacker, target, missile=missile)

    def legal_moves(self, character, ai=False):
        """ov10:1194 MoveCommand / ov11:06BB TryStep, including strict AI move cost."""
        c = self.record(character); out = []
        for d in range(8):
            who, tile, cloud, poison = self.ahead(character, d)
            cost = terrain_cost(tile)*(3 if d % 2 else 2)
            if who >= 0 or tile == 0 or terrain_cost(tile) == 255 or cost > c[6] or ai and cost == c[6]: continue
            if ai and cloud and not any(rec.has_effect(character, t) for t in (0x1E, 0x3F, 0x39, 0x63)) and not c[16]:
                if not saving_throw(self.game, character, 0): continue
            if ai and poison and character.b[0xEE] < 7 and not rec.has_effect(character, 0x63) and not c[16]: continue
            out.append(d)
        return out

    def move_attacks(self, character):
        """ov10:1321..1355: legacy enemy-answer prefix; move_command handles the other directions."""
        legal = self.attack_targets(character); out = []
        for d in range(8):
            who = self.ahead(character, d)[0]
            if who >= 0 and self.chars[who] in legal: out.append((d, self.chars[who]))
        return out

    def move_command(self, character, direction, cursor=True):
        """ov10:12F5..14AB: face first; occupant, Flee, cost refusal, then step."""
        self.record(character)[9] = direction
        self.show('facing', character)  # ov10:12F5 -> ov33:0AB9.
        who, tile, _, _ = self.ahead(character, direction)
        if who >= 0: return self.attack_command(character, self.chars[who], moving=True, cursor=cursor)
        if tile == 0:
            if self.game.ask('COMBAT_ACTION', ['yes', 'no'], actor=self.index(character), action='flee-confirm', cursor=cursor, prompt='Flee:'):
                return False
            return self.flee(character)  # ov10:1358..13A0 -> ov15:0D3B.
        cost = 255 if terrain_cost(tile) == 255 else terrain_cost(tile) * (3 if direction % 2 else 2)
        if cost > self.record(character)[6]:
            self.refusal(character, "can't go there"); return False  # ov10:13F4..1416.
        return self.move(character, direction)

    def refusal(self, character, text):
        """ov26:16E3..1734: transient green bottom line, MessageDelay, then clear; no status-panel message."""
        message(self.game, text, display=False)
        self.show('command', character, self.s.g.get('67D6', 0)/10, command=text)
        self.show('command', character, command='')

    def move(self, character, direction):
        """ov15:0902 opportunity attacks, 06F7 movement, 060E guard attacks; ov25:0C52."""
        if direction not in self.legal_moves(character): raise Halt('combat move is not legal')
        c = self.record(character); p = self.s.g['combat.positions'][self.index(character)]
        before = self.targets(character, 1, 1-character.b[SIDE]); old = p[:2]
        p[0] += DX[direction]; p[1] += DY[direction]
        after = self.targets(character, 1, 1-character.b[SIDE]); p[:2] = old
        c[9] = direction
        for enemy in before:
            ec = self.record(enemy)
            if enemy in after or self.disabled(enemy) or ec[16] or not self.can_see(enemy, character): continue
            if self.ranged(enemy) and not self.ranged_melee(enemy): continue
            if ec[3] or not ec[15] or any(in_cone(*self.position(enemy), *old, (ec[9]+d) % 8) for d in range(-2, 3)):
                slot = 1 if enemy.b[0x121] else 2
                for k in (1, 2):
                    if enemy.b[0x1AC+k]: slot = k
                if not enemy.b[0x1AC+slot]: enemy.b[0x1AC+slot] = 1
                ec[4] = slot; saved = ec[10]; self.attack(enemy, character, opportunity=True); ec[10] = saved
                if not character.b[ACTIVE]: return self.reset(character)
        if c[6] > 0:
            view = getattr(self.game, 'presentation_view', None)
            if (character.b[CTRL] and view is not None and getattr(self.game, 'presentation_redraw', True)
                    and any(not view[i] <= p[i] + (DX[direction], DY[direction])[i] <= view[i]+6 for i in (0, 1))):
                self.show('view', character, margin=2, merge=True)  # ov15:0807..0849 -> ov33:06AC/0959: recenter on the OLD position; st_404 candidate477 is a partial redraw,478 the completed step.
            p[0] += DX[direction]; p[1] += DY[direction]
            c[6] = max(0, c[6]-terrain_cost(self.tile(*p[:2]))*(3 if direction % 2 else 2))
            c[15] = c[18] = 0; self.rebuild()
            self.show('move', character, margin=3 if character.b[CTRL] else 1)  # ov15:07F4/084E..08A3.
            for enemy in self.targets(character, 1, 1-character.b[SIDE]):
                ec = self.record(enemy)
                if ec[7] and not self.disabled(enemy):
                    ec[7] = 0; self.face_toward(enemy, character); self.attack(enemy, character)
                    if not character.b[ACTIVE]: break
        if not character.b[ACTIVE] or self.disabled(character): c[6] = 0
        self.hazards(character, True)
        if not character.b[ACTIVE] or self.disabled(character): return self.reset(character)
        if c[6] < 2: c[6] = 0
        return False

    def hazards(self, character, moving=False):
        """ov25:0C52 TerrainHazards: stinking cloud saves and level-based poison."""
        if not character.b[ACTIVE]: return
        _, _, cloud, poison = self.ahead(character)
        b = character.b
        if cloud and moving and not b[0xF2] and not any(rec.has_effect(character, t) for t in (0x1F, 0x63)) and not b[0x15E] & 8:
            saved = saving_throw(self.game, character, 0)
            t, duration = (0x1E, 1) if saved else (0x1F, roll(self.s, 1, 4)+1)
            _magic().apply_effect(self.game, character, t, duration, 255, False, text='starts to cough' if saved else 'chokes and gags from nausea')  # ov25:0CED..0E57
            effect = next((e for e in character.effects if e[0] == t), None)
            if effect is not None: _magic().effect_callback(self.game, character, effect)
        if poison and b[ACTIVE] and b[0xEE] < 7:
            if b[0xEE] < 5 or not saving_throw(self.game, character, 0, -4 if b[0xEE] == 5 else 0):
                _magic().add_effect(self.game, character, 0x37, 0, 255); self.kill(character)

    def guard(self, character):
        """ov26:2E3B Guard and ov11:1125 GuardOrEnd."""
        self.reset(character)
        if not self.record(character)[16]:
            self.record(character)[7] = 1
            self.show('guard',character,.06,bottom='Guarding')  # oracle S12/seq_monster_turns: menu-row message about66 ms.
        return True

    def bandage(self):
        """ov26:35CB DyingCheck: stabilize the first dying party-side party member."""
        for c in self.chars:
            if not self.record(c)[19] and c.b[SIDE] == 0 and c.b[STATUS] == 5:
                c.b[STATUS] = 4; self.record(c)[14] = 0; return True
        return False

    def flee(self, character):
        """ov15:0D3B/0D96..0DA3: faster than enemies, or one d2 equals one at equal speed."""
        enemies = self.targets(character, 255, 1-character.b[SIDE])
        mine = self.move_allowance(character)//2
        theirs = max((self.move_allowance(t)//2 for t in self.chars if t.b[ACTIVE] and t.b[SIDE] != character.b[SIDE]), default=0)
        ok = not enemies or theirs < mine or theirs == mine and roll(self.s, 1, 2) == 1
        if ok: self.kill(character, 3)
        self.reset(character); return ok

    def spells(self, character, all_memorized=False):
        """ov10:0D63 cast gate; ov15:2596/25A4 lists camp spells, then refuses their selection."""
        if self.s.r0[0xE5] or not self.record(character)[1] or not any(0 < s <= 117 for s in character.b[0x1E:0x69]): return []
        if all_memorized:
            if not character.b[ACTIVE] or character.b[STATUS] == 1 or any(rec.has_effect(character, e) for e in (0x44, 0x15)): return []
            return sorted({s for s in character.b[0x1E:0x69] if 0 < s <= 117})
        return _magic().legal_spells(character, combat=True)

    def cast(self, character, spell_id):
        """ov15:2558/25A4 CastInCombat: refuse camp-only, otherwise delay and reinsert by casting time."""
        if not _magic().spell(spell_id)[11]:
            self.refusal(character, 'Camp Only Spell'); return False  # ov15:25A4..25CA, before queuing or consuming.
        c = self.record(character); delay = _magic().spell(spell_id)[12]//3
        if not delay:
            if _magic().cast(self.game, character, spell_id, combat=True): self.reset(character); return True
            return False
        name = bytes(character.b[1:1 + character.b[0]]).decode('latin1')
        # ov15:2651..2673 -> 0151:0084 NameMessage: name row, text row, one Delay, no panel redraw, so no (Casting) yet. Oracle 027/00150.
        message(self.game, name + ' Begins Casting', display_text=name + chr(10) + 'Begins Casting', actor=self.index(character), names=((0, self.index(character)),), status=False)
        self.show('clear', character)  # ov15:2673 -> ov26:1818/181E: clear the notice before the next turn's panel rebuild.
        c[0] = spell_id; c[3] = max(1, c[3]-delay)
        order = self.s.g['combat.order']; cursor = self.s.g['combat.cursor']; slot = cursor+1
        while slot < len(order) and self.s.g['combat.records'][order[slot]][3] >= c[3]:
            if self.s.g['combat.records'][order[slot]][3] == c[3] and roll(self.s, 1, 2) != 1: break  # ov15:2716..2723, one die/two sides (ov25:11D0/11EB).
            slot += 1
        moved = order.pop(cursor); order.insert(slot-1, moved); self.s.g['combat.cursor'] -= 1
        return True

    def queued_cast(self, character):
        """The delayed cast fires. Oracle 027/00177..00205: the panel keeps (Casting) through the cast; presentation only, the record clears first as before."""
        c = self.record(character); sp = c[0]; c[0] = 0; self.game.presentation_casting = self.index(character)
        try: _magic().cast(self.game, character, sp, combat=True)
        finally: self.game.presentation_casting = None
        self.reset(character)

    def done_menu(self, character):
        """ov10:1614 DoneMenu: delay to end of round, quit, bandage, or return to actions."""
        c = self.record(character); options = ['delay', 'quit']
        if any(t.b[STATUS] == 5 and t.b[SIDE] == 0 and not self.record(t)[19] for t in self.chars): options.append('bandage')
        options += ['exit', 'speed']  # ov10:16BF Speed; append to preserve prior answer indices.
        if not self.ranged(character) or self.ranged_melee(character): options.append('guard')  # ov10:1626..1644.
        while True:
            choice = options[self.game.ask('MENU', options, actor=self.index(character), action='done')]
            if choice != 'speed': break
            from sm.titles.ssb.units.camp import speed
            speed(self.game, combat=True)
        if choice == 'exit': return False
        if choice == 'guard': return self.guard(character)
        if choice == 'delay':
            c[3] = 1; g = self.s.g; order = g['combat.order']; order.append(order.pop(g['combat.cursor'])); g['combat.cursor'] -= 1
        else:
            if choice == 'bandage': self.bandage()
            self.reset(character)
        return True

    def usable_items(self, character):
        """ov21:27B6 UseItem / ov11:03E9 usable scrolls and readied charged powers."""
        if self.s.r0[0xE5]: return []
        from sm.titles.ssb.units.shops import groups
        return [i for i, group in groups(character.items) if self.item_spells(character, i)
                and (group[0][0x2E] in (0x27, 0x28, 0x49) or group[0][0x34])]

    def item_spells(self, character, index):
        """ov21:3B5A / ov23:6440 scroll slots +3C..3E, bundle children, item +3D."""
        it = character.items[index]; out = []
        if it[0x2E] in (0x27, 0x28, 0x49):
            indices = range(index+1, min(len(character.items), index+1+it[0x39])) if it[0x2E] == 0x49 else (index,)
            for child in indices:
                for offset in range(0x3C, 0x3F):
                    sid = character.items[child][offset]
                    if 0 < sid <= 117 and _magic().spell(sid)[11]: out.append((sid, child, offset))
        elif it[0x3E] < 128 and 0 < it[0x3D] <= 117 and _magic().spell(it[0x3D])[11]: out.append((it[0x3D], index, 0))
        return out

    def use_item(self, character, index):
        """ov21:27B6 item casts consume counts/charges, scroll spell slot consumed once."""
        it = character.items[index]; scroll = it[0x2E] in (0x27, 0x28, 0x49)
        entries = self.item_spells(character, index)
        if not entries: return False
        selected = self.game.ask('SPELL', [e[0] for e in entries], actor=self.index(character), item=index) if len(entries) > 1 and not character.b[CTRL] else 0
        sp, child, offset = entries[selected]; can_read = True
        if scroll:
            current = next((i for i in range(6) if character.b[0x111+i]), 17)
            former = next((i for i in range(6) if character.b[0x118+i]), 17)
            can_read = current in (0, 5) or former in (0, 5) or character.b[0x111] or character.b[0x116]
            if not can_read: can_read = character.b[0x117] >= 10 and roll(self.s, 1, 100) <= 75
        if can_read: _magic().cast(self.game, character, sp, combat=True, consume=False)
        # ov21:2A23 overwrites the cast outcome with CombatantReset for a combat spell,
        # including a failed scroll reading; 2A48 then consumes its charge.
        if scroll:
            from sm.titles.ssb.units.camp import consume_scroll
            consume_scroll(character, child, offset)
        elif it[0x3C]:
            if it[0x39] > 1: it[0x39] -= 1
            else:
                it[0x3C] -= 1
                if not it[0x3C]: character.items.remove(it)
        rec.recalc_character(character, self.s.r1[0x372]); self.reset(character); return True

    def legal_actions(self, character):
        """ov10:0D63 ActionMenu + 1614 DoneMenu as a closed, legal decision list."""
        out = []
        if self.legal_moves(character): out.append('move')
        if self.attack_targets(character): out.append('attack')
        if self.spells(character, all_memorized=True): out.append('cast')
        if self.usable_items(character): out.append('use')
        if not self.ranged(character) or self.ranged_melee(character): out.append('guard')
        if any(self.ahead(character, d)[1] == 0 for d in range(8)): out.append('flee')
        out += ['quick', 'done', 'view'] + ([] if 'attack' in out else ['aim'])  # ov10:0D63: View/Aim always available.
        if 'move' not in out and self.record(character)[6] > 0: out.append('move')  # ov10:0D6F: last preserves existing answer indices.
        if character.items and 'use' not in out: out.append('use')  # ov10:0DD0: inventory count, not usable powers; append for replay indices.
        out.append('quick-off')                                            # ov10:0B99 Space, no menu row; last, so existing answer indices stay
        out += ['magic-toggle', 'divine-intervention']                      # ov10:0BDD/0C82: hidden keys 2/- follow all existing answer indices.
        return out

    def player_turn(self, character):
        """ov10:0A05 PlayerTurn; 1194/14AE..14D6 keeps Move active until Done/cancel."""
        i = self.index(character); action = None
        while character.b[ACTIVE] and self.record(character)[3] > 0:
            if action != 'move':
                actions = self.legal_actions(character)
                action = actions[self.game.ask('COMBAT_ACTION', actions, actor=i, round=self.s.g['8DC7'], at=getattr(self.game.vm, 'at', 0))]
                if action == 'move':
                    move_origin = (*self.position(character), self.record(character)[6], self.record(character)[9])  # ov10:119B..11D7.
                    move_first = True
            if action == 'move':
                dirs = self.legal_moves(character); x, y = self.position(character)
                attacks = self.move_attacks(character)
                ordered = dirs + [d for d, _ in attacks]
                # ov10:12EC: every direction is input, including walls/allies/edges.
                # Keep the old movement, attack and cancel indices; append newly reachable inputs.
                ordered += [None] + [d for d in range(8) if d not in ordered]
                cells = ['cancel' if d is None else (x+DX[d], y+DY[d]) for d in ordered]
                cells.append('done')  # ov10:11F4..1203: Return/Done keeps movement; append after all legacy indices.
                pick = self.game.ask('TARGET', cells, actor=i, action=action, cursor=move_first)
                if cells[pick] in ('cancel', 'done'):
                    if cells[pick] == 'cancel':
                        # ov10:10A0..1159: Escape restores only the entry move allowance, position and facing.
                        x0, y0, allowance, facing = move_origin
                        self.record(character)[6] = allowance
                        if not self.place(character, x0, y0): return
                        self.show('view', character, margin=0)
                        self.record(character)[9] = facing
                    if self.record(character)[6] < 2: self.record(character)[6] = 0  # ov10:14D9..14F0.
                    action = None
                else:
                    before = self.position(character)
                    if self.record(character)[9]//4 != ordered[pick]//4: move_first = False  # ov33:0B04..0B47: a mirrored facing redraw erases the cursor tile even without a step.
                    if self.move_command(character, ordered[pick], cursor=move_first): return
                    if self.position(character) != before: move_first = False  # ov15:06F7 removes the old cursor cell only when stepping.
            elif action == 'attack':
                targets = self.attack_targets(character); ids = [self.index(t) for t in targets]
                # ov15:2B73/37DB: append allies after the old cancel index.
                options = ids + ['cancel'] + [self.index(t) for t in self.human_targets(character) if t not in targets]
                pick = options[self.game.ask('TARGET', options, actor=i, action=action)]
                if pick != 'cancel' and self.attack_command(character, self.chars[pick]): return
            elif action == 'aim':
                ids = [self.index(t) for t in self.chars if t is not character and t.b[ACTIVE]]
                legal = [self.index(t) for t in self.human_targets(character)]
                pick = self.game.ask('TARGET', ids + ['cancel'], actor=i, action='aim', attackable=','.join(map(str, legal)))
                if pick < len(ids) and ids[pick] in legal and self.attack_command(character, self.chars[ids[pick]]): return
            elif action == 'cast':
                spells = self.spells(character)
                options = spells + ['cancel'] + [s for s in self.spells(character, all_memorized=True) if s not in spells]  # ov21:3B5A, preserve cancel index.
                pick = options[self.game.ask('SPELL', options, actor=i)]
                if pick != 'cancel' and self.cast(character, pick): return
            elif action == 'use':
                items = self.usable_items(character)
                if not items:
                    # ov10:0B2F..0B48 -> ov21:136A: the newly offered Use opens inventory even without a usable power.
                    from sm.titles.ssb.units import shops
                    shops.item_menu(self.game, character, 'combat'); self.reset_attacks(character)
                    continue
                pick = self.game.ask('LIST', items + [None], actor=i, action='use')
                if pick < len(items) and self.use_item(character, items[pick]): return
            elif action == 'guard': self.guard(character); return
            elif action == 'flee': self.flee(character); return
            elif action == 'quick-off':
                self.quick_off(); action = None; continue                  # ov10:0B99..0BD7: stays in this member's menu
            elif action == 'magic-toggle':
                self.toggle_magic(character); action = None; continue      # ov10:0BDD..0C22: no turn cost or RNG.
            elif action == 'divine-intervention':
                if self.divine_intervention(character):
                    self.show('view', character, margin=3, cursor=False); return  # ov10:0C8F..0CA4.
                self.refusal(character, "That doesn't work")               # ov10:0CA6..0CB5; AI caller ignores a false result.
                action = None; continue
            elif action == 'quick':
                self.show('command', character, .2, command='', cursor=True)  # ov10:0AA2..0AB5: ClearMenuLine, Delay(200).
                character.b[CTRL] = 1; target = self.record(character)[10]
                if target >= 0 and self.chars[target].b[SIDE] == character.b[SIDE]: self.record(character)[10] = -1
                self.computer_turn(character); return
            elif action == 'view':
                from sm.titles.ssb.units import shops
                shops.view(self.game, 'combat', character=character)  # ov10:0AE0: active combatant's View.
                self.reset_attacks(character)
            elif self.done_menu(character): return

    def weapon_score(self, character, item):
        """ov11:1439 WeaponScore: expected dice, plus, hands, alignment and curse."""
        s = rec._T(item, 9)*rec._T(item, 10)
        if rec.sx(item[0x32]) > 0: s += item[0x32]*8
        if rec.sx(rec._T(item, 11)) > 0: s += rec._T(item, 11)*2
        if rec._T(item, 14) & 8: s += (rec._T(item, 5)-1)*2
        if rec._T(item, 1) <= 1: s += 3
        if character.b[0x199]+rec._T(item, 1) >= 3: s = 0
        if item[0x3E] == 0x84 and item[0x3D] & 15 != character.b[0x120]: s = 0
        if item[0x3D] == 0x53 or item[0x36]: s = 0
        return s & 255

    def choose_weapons(self, character):
        """ov11:1544 ChooseWeapons: best melee/ranged choice, ammo, then shield."""
        from sm.titles.ssb.units import shops
        b = character.b; slots = rec.readied(character); old = slots[0]
        if old is not None: b[0x199] = (b[0x199]-rec._T(old, 1)) & 255
        best = melee = shield = None; bs, ms, ss = 1, b[0x123]*b[0x125]+max(0, rec.sx(b[0x127]))*2, 0
        for it in character.items:
            if not rec._T(it, 13) & b[0x130]: continue
            if rec._T(it, 0) == 0:
                score = self.weapon_score(character, it); flags = rec._T(it, 14)
                if flags & 24 and score > bs: best, bs = it, score
                if not flags & 8 and score > ms: melee, ms = it, score
            elif rec._T(it, 0) == 1:
                score = it[0x32]+1 if rec.sx(it[0x32]) >= 0 else 0
                if score > ss: shield, ss = it, score
        choice = melee
        if best is not None:
            f = rec._T(best, 14); ammo = best if f & 16 else None
            if f & 8:
                if f & 1: ammo = slots[11]
                if f & 128: ammo = slots[12]
            rm = rec._T(best, 12) > 1 and f & 0x14 == 0x14
            if bs > ms//2 and (ammo is not None or f == 10) and (rm or not self.targets(character, 1, 1-b[SIDE])): choice = best
        if choice is not old and (old is None or not old[0x36]):
            if old is not None: shops.ready(self.game, character, old, recalculate=False)
            rec.recalc_character(character, self.s.r1[0x372])
            slots = rec.readied(character)
            # ov11:18C8..1929: release the shield's hands without unreadying it before raw ReadyItem.
            if slots[1] is not None and not slots[1][0x36]: b[0x199] = (b[0x199]-rec._T(slots[1], 1)) & 255
            if choice is not None: shops.ready(self.game, character, choice, recalculate=False)
        rec.recalc_character(character, self.s.r1[0x372]); self.reset_attacks(character)  # ov11:1938..1943, before shield adjustment.
        slots = rec.readied(character)
        if b[0x199] > 2:
            lose = slots[1] if slots[1] is not None and not slots[1][0x36] else choice
            if lose is not None: shops.ready(self.game, character, lose, recalculate=False)
        elif b[0x199] < 2 and (slots[1] is None or slots[1] is not shield and not slots[1][0x36]):
            if slots[1] is not None: shops.ready(self.game, character, slots[1], recalculate=False)
            rec.recalc_character(character, self.s.r1[0x372])
            if shield is not None: shops.ready(self.game, character, shield, recalculate=False)
        rec.recalc_character(character, self.s.r1[0x372])

    def morale(self, character):
        """ov11:12AC MoraleCheck: forced fleeing, HP thresholds, script morale, surrender."""
        b, c, g = character.b, self.record(character), self.s.g; c[20] = 0
        if c[16]: c[20] = 1; return False
        if b[0xFF] <= 127: return False
        g['87E2'] = (b[0xFF] & 127)*2
        if g['87E2'] > 102: g['87E2'] = 0
        _mod(self.game, 17, character)
        pct = 100-b[HP]*100//max(1, b[HPMAX])
        if g['87E2'] and g['87E2'] >= pct: return False
        g['87E2'] = g['8E13']; _mod(self.game, 17, character)
        if g['87E2'] and g['87E2'] >= 100-self.s.r1[0x2C6] and b[SIDE]: return False
        theirs = max((self.move_allowance(t)//2 for t in self.chars if t.b[ACTIVE] and t.b[SIDE] != b[SIDE]), default=0)
        if theirs <= self.move_allowance(character)//2: c[20] = 1; return False
        if b[0x13] > 5: self.kill(character, 4); return self.reset(character)  # ov11:13FB..1403 reads character intelligence, not combatant +13h.
        return False

    def spell_worth_casting(self, character, sp, minimum):
        """ov11:02F0 SpellWorthCasting / 01F0 FriendInBlast, DS:44A4 row +6/7/8.

        The actual spell row starts 449D, so these are columns 13/14/15.
        """
        row = _magic().spell(sp)
        if row[13] < minimum: return False
        if sp == 3:
            return any(t.b[HP] < t.b[HPMAX] for t in self.targets(character, 1, character.b[SIDE]))
        if row[14] == 0: return True
        reach = _magic().spell_range(character, sp)
        foes = self.targets(character, reach, 1-character.b[SIDE])
        if not foes: return False
        if not row[15]: return True
        for foe in foes:
            unsafe = False
            for friend in self.targets(foe, row[15], character.b[SIDE]):
                if row[8] != 1 and not saving_throw(self.game, friend, row[9], -2 if character.b[SIDE] == 0 else 8): unsafe = True
            if unsafe: return False  # ov11:02D8..02E4 finishes every friendly save before03CE rejects this blast center.
        return True

    def ai_magic(self, character, items=False):
        """ov11:03E9 TryUseItem / 0544 TryCastSpell: seven declining priority passes."""
        c = self.record(character); g = self.s.g
        if items:
            tries = roll(self.s, 1, 7)
            if not c[2] or not g['87CD' if character.b[SIDE] == 0 else '87CC'] or self.s.r0[0xE5]: return False
            for minimum in range(7, 7-tries, -1):
                for i in self.usable_items(character):
                    it = character.items[i]
                    if it[0x2E] in (0x27, 0x28, 0x49): continue
                    sp = it[0x3D] if it[0x3D] <= 0x38 else it[0x3D]-0x17
                    if self.spell_worth_casting(character, sp, minimum): return self.use_item(character, i)
            return False
        if not c[22] or not c[1] or rec.has_effect(character, 0x44): return False  # ov11:054A..057F: both flags are required before building the pool or rolling.
        spells = [sp for sp in character.b[0x1F:0x69] if sp]  # ov11:0586..05C3 copies EVERY nonzero memorized slot; filtering camp-only75 changed Dominic's draw bound37 to36 (sm-r2-9).
        if not spells: c[22] = 0; return False
        tries = roll(self.s, 1, 7)
        if character.b[0xFF] <= 127 and not g['8E14']: return False
        if not g['87CD' if character.b[SIDE] == 0 else '87CC']: return False
        for minimum in range(7, 7-tries, -1):
            for _ in range(3):
                sp = spells[roll(self.s, 1, len(spells))-1]
                if self.spell_worth_casting(character, sp, minimum): return self.cast(character, sp)
        return False

    def ai_pick_target(self, character, ignore_terrain=True, reach=255, keep=True):
        """ov15:3BF1/3C98..3E05: two searches; mode0's second ignores terrain, independently of visibility bypass."""
        c = self.record(character); target = c[10]
        if keep and 0 <= target < len(self.chars):                         # ov15:3C1F: mode 0 keeps a valid stored target; spell aiming (ov15:1E78, mode 1) always re-rolls
            t = self.chars[target]
            if t.b[ACTIVE] and t.b[SIDE] != character.b[SIDE] and self.can_see(character, t): return t
        c[10] = -1
        for ignore in (False, bool(keep)):
            candidates = self.targets(character, reach, 1-character.b[SIDE], ignore_terrain=ignore)
            for _ in range(20):
                if not any(t is not None for t in candidates): break
                slot = roll(self.s, 1, len(candidates))-1; target = candidates[slot]
                if target is None: continue
                if ignore and ignore_terrain or self.can_see(character, target): c[10] = self.index(target); return target
                candidates[slot] = None  # ov15:3DA6..3DED: clear rejected entries without changing the dice bound.
        return None

    def ai_move(self, character, target):
        """ov11:08CE AiMove with DS:032C mode offsets and reversal/oscillation limit."""
        c, b, g = self.record(character), character.b, self.s.g
        self.show('command', character, command='Move/Attack, Move Left = %d' % (c[6]//2))  # ov11:08F7..0920, before spending movement.
        if self.check_interrupt(character): return False                   # ov11:092C..0933
        if c[6]//2 <= 0 or c[3] <= 0: return False
        if b[0xFF] >= 128 and g['8E13'] > g.get('87E2', 0)+roll(self.s, 1, 100) and b[SIDE] != 1: return False
        if not c[20] and rec.readied(character)[2] is None and b[0x6C] == 5 and not rec.dual(character): return False
        if c[20]:
            c[21] = roll(self.s, 1, 2); f = self.s.dir
            d = (f-((f+2) % 4)//2+4*int(b[SIDE] == 0)) % 8
        elif target is not None: d = direction_to(*self.position(character), *self.position(target))
        else: return False
        ds = ssb_data.stexe(); chosen = None
        # TryStep's saving throws occur in direction-priority order, not for all eight cells.
        for k in range(1, 6):
            step = (d+ds[0x32C+5*c[21]+k]) % 8
            who, tile, cloud, poison = self.ahead(character, step)
            if tile == 0:
                if c[20]: self.flee(character); return False
                continue
            cost = terrain_cost(tile)*(3 if step % 2 else 2)
            if who >= 0 or terrain_cost(tile) == 255 or cost >= c[6]: continue
            if cloud and not c[16] and not any(rec.has_effect(character, t) for t in (0x1E, 0x3F, 0x39, 0x63)):
                if not saving_throw(self.game, character, 0): continue
            if poison and b[0xEE] < 7 and not rec.has_effect(character, 0x63) and not c[16]: continue
            chosen = step; break
        if chosen is None or g['59C6'] == (chosen+4) % 8:
            g['59C7'] += 1; c[21] = c[21] % 6+1
            if g['59C7'] > 1:
                c[10] = -1
                if g['59C7'] > 2: c[6] = 0; return None  # ov11:0B7A: done, no GuardOrEnd; AiAttackLoop comes round, re-picks (one roll), then 0936 guards
                if self.ai_pick_target(character) is None: return False
        if chosen is None: return None                                 # ov11:0BD4: k = 6, done, no GuardOrEnd
        g['59C6'] = chosen; c[9] = chosen
        self.show('facing', character)  # ov11:0C1C..0C2C -> ov33:0AB9, before opportunity attacks and the step.
        self.move(character, chosen); return bool(b[ACTIVE] and c[3])

    def quick_off(self, skip_status=None):
        """Space: every party member with morale +FF below 80h gets control back (ov10:0BA9..0BD5; ov11:121D..1254 also skips status +1A6 = skip_status)."""
        for p in self.s.party:
            if p.b[0xFF] < 0x80 and p.b[0x1A6] != skip_status: p.b[CTRL] = 0

    def toggle_magic(self, character):
        """ov10:0BE1..0C1D / ov11:11CA..1206: toggle DS:8E14, then BottomMessage."""
        self.s.g['8E14'] = int(not self.s.g['8E14'])
        self.refusal(character, 'Magic On' if self.s.g['8E14'] else 'Magic Off')

    def divine_intervention(self, character):
        """ov15:3E2D..3F02 (00C9:0098): exact second DOS argument gates the debug action."""
        args = getattr(self.game, 'dos_args', ())
        data = ssb_data.stexe(); password = data[0x1910:0x1910 + data[0x190F]].decode('cp437')  # resident0B77:0003..0011 copies DS:190F to A5E6.
        if len(args) < 2 or args[1] != password: return False  # 3E3E..3E53: ParamStr(2), case-sensitive Pascal comparison.
        self.refusal(character, 'The Gods intervene!')  # ov15:3E5A..3E69 -> ov26:16E3.
        for other in self.chars:
            if other.b[SIDE] == 1:
                other.b[ACTIVE], other.b[STATUS] = 0, 6
                self.s.g['combat.positions'][self.index(other)][2] = 0  # 3E82..3EB2: no damage roll, death callback, HP write or body.
            self.move_allowance(other)  # 3EB7..3EC2 -> ov26:25EA refreshes +1B6 even for party members.
        self.rebuild()
        view = getattr(self.game, 'presentation_view', None)
        self.show('redraw', character, focus=tuple(v+3 for v in view) if view is not None else self.position(character), margin=255)  # 3ED7..3EF7 retains viewport.
        return True

    def check_interrupt(self, character):
        """ov11:1197 CheckInterrupt, from 001C, 018E, 092C. The UI hook waits until the screen has caught up, then gives the first held key; the rest are flushed (06EF:044F at 1281). No hook (headless) = no key. No dice."""
        hook = getattr(self.game, 'ai_check', None)
        if hook is None: return False                                      # ov11:1197: keys 2/- are checked on monster turns too, without any Quick party member.
        key = hook()
        if key == '2': self.toggle_magic(character); return False           # ov11:11C6..120B continues this AI turn.
        if key == '-': self.divine_intervention(character); return False    # ov11:1274..127F ignores the return value.
        if key != ' ': return False
        self.quick_off(skip_status=1)
        if character.b[CTRL]: return False                                 # ov11:1256..125F: only the member now back under control stops; a monster's turn goes on
        self.record(character)[3] = 20                                     # ov11:1269; DoTurn takes 20 as 19 and gives the menu (ov10)
        return True

    def computer_turn(self, character):
        """ov11:000F ComputerTurn and 0CD6 AiAttackLoop, NPCs/monsters/Quick members."""
        c, g = self.record(character), self.s.g
        stop = self.check_interrupt(character)                             # ov11:001C
        self.show('clear', character, command='', cursor=True)  # ov11:0022/0027: clear menu and combat message before AI work.
        if not character.b[ACTIVE]: self.reset(character); return
        if not 1 <= c[21] <= 4 or roll(self.s, 1, 4) == 1:   # ov11:0054..006D: mode 0 or above 4 always re-rolls (bytes + oracle; ENGINE_READ2_g1 line 189 reads this wrongly)
            c[21] = roll(self.s, 1, 2)+4 if roll(self.s, 1, 8) == 8 else roll(self.s, 1, 4)
        if stop or self.morale(character): return                          # ov11:00B5, 0106
        if self.ai_magic(character, items=True): self.reset(character); return
        if c[0]:
            self.queued_cast(character); return
        if self.ai_magic(character): return
        self.choose_weapons(character)
        if self.check_interrupt(character): return                         # ov11:018E, 0194
        def end():                                                         # ov11:1125 GuardOrEnd
            if self.disabled(character) or self.ranged(character) or not c[3]: self.reset(character)
            else: self.guard(character)
        for _ in range(40):                                                # ov11:0194..01E8 repeat: pick, attack loop, until it reports the turn spent (bytes + oracle: a kill with attacks left picks again)
            if self.ai_pick_target(character, True) is None or c[3] <= 0 or not character.b[ACTIVE]: end(); return  # ov11:01A3 pushes dropFlag=1; AiMove's later search passes0.
            if self.ai_attack_loop(character, end): return
        end()

    def ai_attack_loop(self, character, end):
        """ov11:0CD6 AiAttackLoop; True = keep cleared (the turn is spent), False = ComputerTurn repeats."""
        c, g = self.record(character), self.s.g; side = 1-character.b[SIDE]; steps = 0
        def stored():
            return self.chars[c[10]] if 0 <= c[10] < len(self.chars) else None
        g['59C6'], g['59C7'], g['59C8'] = 8, 0, 0; _mod(self.game, 14, character)  # 0CDC..0CFF
        if character.b[SIDE] == 0 and self.bandage(): c[3] = 0             # 0D07..0D23
        while character.b[ACTIVE]:                                         # 0D3B
            while c[20] and c[6] > 0 and 0 < c[3] < 20:                    # 0D55..0D93 fleeing
                if not self.ai_move(character, stored()): break
            if not character.b[ACTIVE] or c[3] in (0, 20): return True     # 0D9D..0DB3
            steps += 1
            if steps > 20: end(); return True                              # 0DCF..0DF0
            w = rec.readied(character)[0]; reach = (rec._T(w, 12)-1) & 255 if w is not None else 1
            if reach in (0, 255): reach = 1                                # 0DF3..0E35
            t = stored(); hit = False                                      # 0E41..0E6B: a stored target counts only when it is a monster
            if t is not None and (not t.b[ACTIVE] or t.b[SIDE] == 0): t = None
            if t is not None and self.can_see(character, t):               # 0E76..0F08
                hit = self.walk_line(*self.position(character), *self.position(t), reach)[0]
            if not hit:
                near = self.targets(character, reach, side)                # 0F17..0F26
                if not near:                                               # 0F29..0F60
                    if self.ai_pick_target(character, False) is None: end(); return False
                    if self.ai_move(character, stored()) is False: end(); return True  # False = its own GuardOrEnd paths (0936, 0963, 09A8)
                    continue
                t = near[roll(self.s, 1, len(near))-1]                     # 0F63..0F8E
                if self.ranged(character) and not self.ranged_melee(character) and self.targets(character, 1, side):
                    self.choose_weapons(character); return False           # 0F91..0FCF
                hit = self.distance(character, t) == 1 or self.can_see(character, t)
            if not hit: continue
            x, y = self.position(character); d = direction_to(x, y, *self.position(t)); ds = ssb_data.stexe()
            self.show('view', character, margin=2, cursor=False, focus=(x+rec.sx(ds[0x1A90+d]), y+rec.sx(ds[0x1A99+d])))  # ov11:1007..1034 -> ov33:095F..099A: redraw around the direction-offset point, removing the cursor without turning the icon.
            if self.sweep(character, t): self.reset(character); return False   # 1043..1066
            self.face_toward(character, t); missile = None                 # 1069..107F
            if self.ranged(character):                                     # 1082..10CD
                missile = self.ammo(character)[1]
                if self.ranged_melee(character) and self.distance(character, t) == 1: missile = None
            if self.attack(character, t, missile=missile): return True     # 10EF..10F5
            if not t.b[ACTIVE]: return False                               # 10FB..1106
        return True

    def do_turn(self, character):
        """ov10:089E DoTurn: turn-start modifiers, selection, recalc, control dispatch."""
        c = self.record(character); c[15] = c[18] = c[7] = 0; _mod(self.game, 7, character)
        if c[3] <= 0: return
        if c[3] == 20: c[3] = 19
        self.s.sel = self.index(character); rec.recalc_character(character, self.s.r1[0x372])
        self.show('view', character, margin=2, turn_start=True, cursor=True)  # ov10:0935..0944 -> ov33:1307: cursor/map completes with the previous status panel.
        self.show('clear', character, panel_clear=True)  # ov10:095F -> ov26:0CA4..0CB0: clear columns23..38, rows1..21 before rebuilding the panel.
        self.show('status', character, status=True, merge=True)  # ov26:0CB5..0E6F: new status precedes the following menu/AI clear; no extra hold.
        _mod(self.game, 15, character)
        if not c[0]: _mod(self.game, 21, character)
        if c[3] <= 0: return
        if character.b[CTRL]: self.computer_turn(character)
        elif c[0]:
            self.queued_cast(character)
        else: self.player_turn(character)

    def end_round(self):
        """ov10:0F61/1066..109A: continue only with active allies, no enemies, demo off."""
        ages = [rec.rdw(c.b, 0x6E) for c in self.s.party]
        self.game.vm.advance_clock(1, 1); g = self.s.g; g['8DC7'] += 1
        if ages != [rec.rdw(c.b, 0x6E) for c in self.s.party]: g['7D44'] = 1
        # VM.advance_clock iterates s.party; the original linked list also contains monsters.
        for character in self.s.monsters:
            if character.effects: _magic().tick_effects(self.game, character, 1)
        self.monster_hp_percent()  # ov10:0F76: retain this value throughout the next round, including after attacks.
        self.recount()
        for character in self.chars:
            _mod(self.game, 19, character); self.hazards(character)
            c = self.record(character)
            if character.b[STATUS] == 5:
                c[14] += 1
                if c[14] > 9: character.b[STATUS] = 6
        party, enemies = self.recount()
        if party and not enemies and not g.get('67E9', 0):
            options = ['continue', 'end']
            return bool(self.game.ask('MENU', options, action='continue-battle', round=g['8DC7']))
        return not party or not enemies or g['8DC7'] >= g['8DC8']

    def finish(self):
        """ov10:0387 AgeDeaths / 0000 cleanup; result contract for ov07:17B8 sweep."""
        g = self.s.g
        if g.get('7D44'):
            for character in self.s.party:
                b = character.b; cap = {1: 1600, 2: 325, 3: 525, 4: 750, 5: 199, 6: 120}.get(b[0x6B])
                if cap is not None and b[STATUS] < 6 and rec.rdw(b, 0x6E) >= cap: self.kill(character, 8)
            g['7D44'] = 0
        self.recount()
        for character in self.chars:
            if rec.has_effect(character, 0x0B) and character.b[STATUS] == 0: character.b[STATUS] = 3 if g['87CD'] > 1 else 0
            self.strip(character)
        party_fled = any(c.b[STATUS] == 3 for c in self.s.party) and not any(c.b[STATUS] in (0, 1) for c in self.s.party)  # PartySweep ov07:066B..0686
        monsters_fled = any(c.b[STATUS] == 3 for c in self.s.monsters)
        alive = any(c.b[STATUS] in (0, 1, 3) and c.b[SIDE] == 0 and c.b[0xFF] < 128 for c in self.s.party)
        if self.s.r1[0x2E6]: alive |= any(c.b[STATUS] in (3, 4, 5) for c in self.s.party)
        self.s.party_dead = int(not alive)
        g['combat.result'] = 0x80 if not alive else 0x81 if party_fled else 1 if monsters_fled else 0
        g['combat.active'] = 0; g['67F8'] = 1
        # Body/map data is kept until the VM sweep for inspection/replay; no process-local state.
        return g['combat.result']


def run(game):
    """ov10:011D CombatMain; VM.op24 calls once and invokes its own AfterCombat."""
    combat = Combat(game); combat.setup()
    done = not all(combat.recount())
    while not done:
        combat.init_round(); g = game.s.g
        while g['combat.cursor'] < len(g['combat.order']):
            character = combat.chars[g['combat.order'][g['combat.cursor']]]
            combat.do_turn(character); g['combat.cursor'] += 1
        done = combat.end_round()
    result = combat.finish(); game.combat = None
    return result


def test():
    """V-checks for the ov10/11/12/15/25/32/33 rows; see _combat_test source citations."""
    from sm.titles.ssb.units._combat_test import check
    check()
