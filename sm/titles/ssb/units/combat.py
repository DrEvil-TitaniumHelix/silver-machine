from sm.titles.ssb import data as ssb_data
from sm import dax; from sm.titles.ssb import rec
from sm.titles.ssb.units.shops import message
from sm.titles.ssb.vm import ACTIVE, HP, HPMAX, STATUS, SIDE, CTRL, Halt

DX = (0, 1, 1, 1, 0, -1, -1, -1, 0)
DY = (-1, -1, 0, 1, 1, 1, 0, -1, 0)
DISABLED = (0x1F, 0x33, 0x34, 0x35)


def roll(s, dice, sides):
    return sum(s.random(sides) + 1 for _ in range(dice)) & 255


def footprint(size):
    if not size: return ()
    d = ssb_data.stexe(); base = 0x1B12 + 8 * size
    return tuple((rec.sx(d[base + 2*k]), rec.sx(d[base + 2*k + 1]))
                 for k in range(4) if rec.sx(d[base + 2*k]) >= 0)


def terrain_cost(tile):
    return ssb_data.stexe()[0x1A9E + 4 * tile]


def line(x0, y0, x1, y1):
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
    if (x, y) == (tx, ty): return 8
    dx, dy = abs(tx-x), abs(ty-y)
    low, high = dx * 106 // 256, dx * 622 // 256
    tests = (ty <= y and high <= dy, ty < y and tx > x and low <= dy <= high,
             tx >= x and low >= dy, ty > y and tx > x and low <= dy <= high,
             ty >= y and high <= dy, ty > y and tx < x and low <= dy <= high,
             tx <= x and low >= dy, ty < y and tx < x and low <= dy <= high)
    return next((i for i, yes in enumerate(tests) if yes), 8)


def attack_roll(game, attacker, target, ac):
    s = game.s
    while rec.has_effect(attacker, 0x19): _remove_effect(game, attacker, 0x19)
    s.g['87DF'] = r = roll(s, 1, 20)
    if r == 1: return False
    if r == 20: s.g['87DF'] = 100
    _mod(game, 10, attacker); _mod(game, 16, target)
    bonus = s.r1[0x371 if attacker.b[SIDE] == 0 else 0x370]
    return s.g['87DF'] >= 0 and s.g['87DF'] + attacker.b[0x1AA] + rec.sx16(bonus) >= ac


def saving_throw(game, character, save_idx, bonus=0):
    if not 0 <= save_idx < 5: raise ValueError('save index outside 0..4')
    g = game.s.g; g['87E8'] = 1; g['87D2'] = r = roll(game.s, 1, 20)
    if r in (1, 20): g['87E8'] = int(r == 20); return r == 20
    g['87D2'] += rec.sx(character.b[0x19A]) + rec.sx(bonus)
    g['87E7'] = save_idx; _mod(game, 12, character)
    g['87E8'] = int(character.b[0xE8 + save_idx] <= g['87D2']); return bool(g['87E8'])


def _magic():
    from sm.titles.ssb.units import magic
    return magic


def _mod(game, kind, character):
    if any(c.effects for c in game.s.chars()): _magic().apply_modifiers(game, character, kind)


def _remove_effect(game, character, kind):
    return _magic().remove_effect(game, character, kind)


class Combat:

    def __init__(self, game):
        self.game, self.s = game, game.s
        game.combat = self

    def show(self, kind, character=None, delay=0, **details):
        if getattr(self.game, 'presentation', None) is not None:
            self.game.present(kind, self.index(character) if character is not None else None, delay, **details)

    def projectile(self, character, end, sprite=5, frames=4, speed=30, kind='missile', separate_redraw=False, **details):
        if getattr(self.game, 'presentation', None) is None: return
        start = details.pop('start', self.position(character))
        if tuple(start) == tuple(end): return
        self.game.presentation_poses = {}
        view = getattr(self.game, 'presentation_view', None)
        if (view is not None and any(not (view[0] <= x <= view[0]+6 and view[1] <= y <= view[1]+6) for x,y in (start,end))
                and all(abs(end[i]-start[i]) <= 6 for i in (0,1))):
            self.game.presentation_view = tuple(max(0, min(bound, start[i]+int((end[i]-start[i])/2)-3))
                                                for i,bound in enumerate((43,18)))
        if details.get('cue'): self.show('sound', character, merge=True, cue=details.pop('cue'))
        self.show('redraw', character, merge=not separate_redraw,
                  recenter=getattr(self.game, 'presentation_view', None) != view)
        mirror = details.pop('mirror', False)
        sprites = tuple((sprite + (128 if (p >= 2 if frames == 4 else p == 1) else 0),
                         p in (1, 2) if frames == 4 else mirror) for p in range(frames))
        self.game.presentation_sprites = sprites
        points = list(line(start[0]*3, start[1]*3, end[0]*3, end[1]*3))
        directions = [(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:])]
        phase = 0

        def draw(x, y):
            nonlocal phase
            current = self.game.presentation_view
            self.show(kind, character, speed / 1000, sprite=sprite + (128 if (phase >= 2 if frames == 4 else phase == 1) else 0),
                      mirror=phase in (1, 2) if frames == 4 else mirror, point=(x/3,y/3),
                      focus=tuple(v+3 for v in current), margin=255, **details)
            phase = (phase+1) % frames

        current = self.game.presentation_view; n = 0; x,y = points[0][:2]
        while n < len(directions)-1:
            dx,dy = directions[n]; x+=dx; y+=dy; draw(x,y); n+=1
            if not all(0 <= p-3*v <= 18 for p,v in zip((x,y),current)): break
        if n < len(directions)-1:
            current = tuple(max(0,min(bound,end[i]-3)) for i,bound in enumerate((43,18)))
            self.game.presentation_view = current
            self.show('redraw',character)
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
        if not all(current[i] <= end[i] <= current[i]+6 for i in (0,1)):
            self.show('redraw',character,focus=end,margin=3)
        draw(end[0]*3,end[1]*3)
        self.show('erase', character, **{k: v for k, v in details.items() if k in ('spell', 'facing')})

    def flash(self, character, kind=0):
        if getattr(self.game, 'presentation', None) is None: return
        self.game.presentation_sprites = tuple(((9 if kind else 10) + 128*(p>=2), p in (1,2)) for p in range(4))
        for _ in range(self.s.g.get('67D6', 0) + 1 if kind else 1):
            for phase in range(4):
                self.show('flash', character, .07, sprite=(9 if kind else 10) + (128 if phase >= 2 else 0),
                          mirror=phase in (1, 2), point=self.position(character))
        self.show('restore', character, 0 if kind else self.s.g.get('67D6', 0) / 10)

    def missile(self, attacker, target, item):
        if getattr(self.game, 'presentation', None) is None: return
        typ = item[0x2E]; d = direction_to(*self.position(attacker), *self.position(target))
        if typ in (0x42, 5, 7, 12, 30):
            sprite = (1 + (128 if d in (3, 5) else 0) if d % 2 else d % 4 + (128 if d >= 4 else 0))
            self.projectile(attacker, self.position(target), sprite, 1, 10, mirror=d in (5, 7))
        else:
            sprite, frames, speed = ((3, 4, 50) if typ in (2, 3, 6) else
                                      (8, 2, 10) if typ in (28, 29) else (7, 2, 20))
            self.projectile(attacker, self.position(target), sprite, frames, speed)

    @property
    def chars(self):
        return self.s.chars()

    @property
    def tiles(self):
        return self.s.g['combat.tiles']

    def index(self, character):
        return self.chars.index(character)

    def record(self, character):
        return self.s.g['combat.records'][self.index(character)]

    def position(self, character):
        return tuple(self.s.g['combat.positions'][self.index(character)][:2])

    def tile(self, x, y):
        return self.tiles[y * 50 + x] if 0 <= x < 50 and 0 <= y < 25 else 0

    def set_tile(self, x, y, value):
        if 0 <= x < 50 and 0 <= y < 25: self.tiles[y * 50 + x] = value

    def cells(self, character, x=None, y=None):
        p = self.s.g['combat.positions'][self.index(character)]
        if x is None: x, y = p[:2]
        return [(x+dx, y+dy) for dx, dy in footprint(p[2])]

    def rebuild(self):
        occ = [0] * 1250
        for i, c in enumerate(self.chars):
            for x, y in self.cells(c):
                if 0 <= x < 50 and 0 <= y < 25: occ[y*50+x] = i+1
        self.s.g['combat.occupancy'] = occ

    def ahead(self, character, direction=8):
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
        if not in_cone(x, y, tx, ty): return False, 255
        ds = ssb_data.stexe(); height = ds[0x1A9F + 4*self.tile(x, y)]
        for cx, cy, steps in line(x, y, tx, ty):
            if steps > 2*range+1 or (not ignore_terrain and ds[0x1AA0 + 4*self.tile(cx, cy)] > height): return False, steps
        return True, steps

    def target_entries(self, character, range=255, direction=255, ignore_terrain=False, own=None):
        out = []; own = self.cells(character) if own is None else own
        for i, other in enumerate(self.chars):
            best = None
            for tx, ty in self.cells(other):
                for x, y in own:
                    if not in_cone(x, y, tx, ty, direction): continue
                    ok, distance = self.walk_line(x, y, tx, ty, range, ignore_terrain)
                    if ok and (best is None or distance < best[0]):
                        d = direction if direction < 8 else next((d for d, _ in enumerate(DX[:8]) if in_cone(x, y, tx, ty, d)), 8)
                        best = distance, d
            if best is not None: out.append((i, *best))
        i = 0
        while i < len(out)-1:
            j = i+1
            while j < len(out):
                if out[j][1] < out[i][1] or out[j][1] == out[i][1] and out[j][2] < out[i][2] and out[j][2] % 2 <= out[i][2] % 2:
                    out[i], out[j] = out[j], out[i]
                j += 1
            i += 1
        return out

    def targets(self, character, range=255, side=None, direction=255, ignore_terrain=False, own=None):
        chars = self.chars
        return [chars[i] for i, _, _ in self.target_entries(character, range, direction, ignore_terrain, own)
                if chars[i].b[ACTIVE] and (side is None or chars[i].b[SIDE] == side)]

    def distance(self, a, b):
        own, other = self.cells(a), self.cells(b)
        return min((list(line(x, y, tx, ty))[-1][2] // 2 for x, y in own for tx, ty in other), default=255)

    def recount(self):
        g = self.s.g; chars = self.chars
        g['87CC'], g['87CD'] = (sum(bool(c.b[ACTIVE]) for c in chars if c.b[SIDE] == side) for side in (0, 1))
        return g['87CC'], g['87CD']

    def monster_hp_percent(self):
        g = self.s.g; chars = self.chars
        total = sum(c.b[HPMAX] for c in chars if c.b[SIDE] == 1)
        if total: g['8E13'] = sum(c.b[HP] for c in chars if c.b[SIDE] == 1 and c.b[ACTIVE]) * 20 // total * 5

    def reset(self, character):
        c = self.record(character)
        for offset in (0, 3, 7, 6): c[offset] = 0
        return True

    def remove(self, character, downed=True):
        i = self.index(character); p = self.s.g['combat.positions'][i]
        animated = p[2] and downed and character.b[STATUS] != 3
        if animated:
            for phase in range(9):
                self.show('death', character, .01, sprite=11 + 128*(phase % 2), point=tuple(p[:2]), cells=footprint(p[2]))
            self.show('death', character, self.s.g.get('67D6',0)/10, sprite=11, point=tuple(p[:2]), cells=footprint(p[2]))
        if p[2] and downed and not self.record(character)[0x13] and character.b[STATUS] != 3:
            x, y = p[:2]; self.s.g['combat.bodies'].append([i, x, y, self.tile(x, y)])
            if self.tile(x, y) != 0x1D: self.set_tile(x, y, 0x1C if character.b[STATUS] == 7 else 0x1E)
        p[2] = 0; self.reset(character); self.rebuild(); self.recount()
        if animated: self.show('redraw', character, merge=True)
        else: self.show('view', character, self.s.g.get('67D6',0)/10)

    def strip(self, character):
        for kind in ssb_data.stexe()[0xA9A:0xAA8]:
            if rec.has_effect(character, kind): _remove_effect(self.game, character, kind)
        if rec.has_effect(character, 0x4D) and character.b[0xFF] == 0xB3: character.b[SIDE] = 0

    def kill(self, character, status=6, downed=True):
        if character.b[STATUS] in (6, 7, 8): return
        character.b[STATUS], character.b[ACTIVE] = status, 0
        if status != 3: character.b[HP] = 0
        self.strip(character)
        if not character.b[ACTIVE]: self.remove(character, downed)

    def apply_damage(self, character, amount):
        if amount <= 0 or not character.b[ACTIVE]: return
        b, c = character.b, self.record(character); over = max(0, amount-b[HP])
        hp = max(0, b[HP]-amount)
        if over > 9 or (not hp and b[STATUS] == 1): b[STATUS] = 6
        elif over: b[STATUS] = 5; c[14] = over
        elif not hp: b[STATUS] = 4
        b[HP] = hp; c[1] = 0
        if c[0]:
            slots = b[0x1E:0x69]
            message(self.game, '%s lost a spell' % bytes(b[1:1 + b[0]]).decode('latin1'))
            if c[0] in slots: b[0x1E + slots.index(c[0])] = 0
            self.reset(character)
        if b[STATUS] in (4, 5, 6, 7, 8):
            name=bytes(b[1:1 + b[0]]).decode('latin1'); who=self.index(character)
            result = 'goes down\n%s\nis killed' % name if b[STATUS] in (6, 7, 8) else 'goes down, and is Dying' if b[STATUS] == 5 else 'goes down'
            message(self.game, '%s %s' % (name,result.replace('\n',' ')),display_text=name+'\n'+result.replace(', and','\nand'),
                    names=((0,who,12),(2,who,12)) if b[STATUS] in (6, 7, 8) else ((0,who,12),),continuation=True,delay=0)
            b[ACTIVE], b[HP] = 0, 0; self.strip(character); _mod(self.game, 13, character)
            if not b[ACTIVE] and b[STATUS] != 10: self.remove(character)
        self.recount()

    def damage(self, character, amount, save_result=0, use_save=False):
        g = self.s.g; g['87D4'] = amount & 255; _mod(self.game, 6, character)
        if use_save:
            if save_result == 1: g['87D4'] = 0
            elif save_result == 2: g['87D4'] //= 2
        else: _mod(self.game, 20, character)
        self.apply_damage(character, max(0, g['87D4']))

    def wall(self, x, y, direction):
        def face(x, y, d):
            if not (0 <= x < 16 and 0 <= y < 16): return 0 if y == self.s.y and d in (2, 6) else 1
            if not self.game.geo.passage(self.s, x, y, d): return 1
            return 3 if self.game.geo.wall(self.s, x, y, d) else 0
        return face(x, y, direction) | face(x+DX[direction], y+DY[direction], (direction+4) % 8)

    def build_map(self):
        self.s.g['combat.tiles'] = [0] * 1250
        if not self.s.r0[0xE6]:
            raise Halt('2D combat: unreachable, [4BE6] = 1 in every shipped state (ENGINE_READ2_f1.md: ov12:0939 empty by design, no 2D map data)')
        for dy in range(-2, 3):
            for dx in range(-6, 7):
                x, y = self.s.x+dx, self.s.y+dy
                w, n, e, south = (self.wall(x, y, d) for d in (6, 0, 2, 4))
                def put(i, j, t):
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
            escaped = not 0 <= cx <= 10 and not 0 <= cy <= 5
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
            if outside: continue
            if not masks[side][k][cy*11+cx]: continue
            tx, ty = 22+6*sx+5*sy+cx, 10+5*sy+cy
            p = self.s.g['combat.positions'][self.index(character)]; p[:2] = [tx, ty]
            who, tile, _, _ = self.ahead(character)
            if who < 0 and tile > 0 and terrain_cost(tile) != 255:
                masks[side][k][cy*11+cx] = 0; self.rebuild(); return True

    def setup(self):
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
            self.s.monsters[:] = [c for i, c in enumerate(self.s.monsters, len(self.s.party)) if i not in dropped]
            for key in ('combat.records', 'combat.positions'): g[key] = [v for i, v in enumerate(g[key]) if i not in dropped]
            self.rebuild()
        if g['combat.positions']:
            self.game.presentation_view = tuple(v-3 for v in g['combat.positions'][0][:2])
        for char in self.chars: _mod(self.game, 8, char)
        self.recount(); self.monster_hp_percent()

    def move_allowance(self, character):
        return rec.compute_move(character, self.s.r1[0x372])

    def ranged(self, character):
        w = rec.readied(character)[0]
        return w is not None and rec._T(w, 12) > 1

    def ranged_melee(self, character):
        w = rec.readied(character)[0]
        return self.ranged(character) and (rec._T(w, 14) & 0x14 == 0x14 or w[0x2E] == 0x43)

    def ammo(self, character):
        slots = rec.readied(character); w = slots[0]
        if w is None: return False, None
        f = rec._T(w, 14); ammo = w if f & 16 else None
        if f & 8:
            if f & 1: ammo = slots[11]
            if f & 128: ammo = slots[12]
        return ammo is not None or f == 10, ammo

    def reset_attacks(self, character):
        b, c, g = character.b, self.record(character), self.s.g
        old = b[0x1AD]; w = rec.readied(character)[0]
        ranged = self.ranged(character) and self.ammo(character)[0]
        g['87D6'] = max(2, rec._T(w, 5)) if ranged else b[0x121]
        _mod(self.game, 18, character); count = (g['87D6'] + (g['8DC7'] & 1)) // 2
        if ranged:
            _, ammo = self.ammo(character)
            if ammo is not None and ammo[0x39]: count = min(count, max(1, ammo[0x39]))
        b[0x1AD] = min(count, old) if c[8] else count

    def init_round(self):
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
        return any(rec.has_effect(character, t) for t in DISABLED)

    def can_see(self, attacker, target):
        old = self.s.sel; self.s.sel = self.index(attacker); self.s.g['87DB'] = 0
        _mod(self.game, 1, target); self.s.sel = old
        return self.s.g['87DB'] == 0

    def attack_targets(self, character, allies=False):
        if not character.b[ACTIVE] or not any(character.b[0x1AD:0x1AF]): return []
        ranged = self.ranged(character); melee = self.ranged_melee(character)
        w = rec.readied(character)[0]; reach = (rec._T(w, 12)-1) & 255 if ranged else 1
        if reach in (0, 255): reach = 1
        nearby = self.targets(character, 1, 1-character.b[SIDE])
        available, _ = self.ammo(character)
        return [t for t in self.targets(character, reach, None if allies else 1-character.b[SIDE])
                if t is not character and self.can_see(character, t)
                and (not ranged or (available and (melee or not nearby)))]

    def human_targets(self, character):
        from copy import copy
        game = copy(self.game); game.s = self.s.copy(); game.presentation = None
        game.vm = copy(self.game.vm); game.vm.s = game.s; game.vm.host = game
        game.vm.out = list(self.game.vm.out); game.combat = Combat(game)
        battle = game.combat
        return [self.chars[battle.index(t)] for t in battle.attack_targets(battle.chars[self.index(character)], allies=True)]

    def backstab(self, attacker, target):
        b = attacker.b; w = rec.readied(attacker)[0]
        if not (b[0x117] or b[0x11E] and rec.dual(attacker)): return False
        return ((w is None or w[0x2E] in (3, 4, 0x11, 0x12, 0x13)) and self.record(target)[15] > 1
                and self.distance(attacker, target) < 2 and target.b[0xE7] & 127 <= 1
                and direction_to(*self.position(attacker), *self.position(target)) == self.record(target)[9])

    def face_toward(self, attacker, target):
        c = self.record(target); d = direction_to(*self.position(target), *self.position(attacker))
        r = (d-c[9]+8) % 8; c[15] += 1; c[18] = (c[18]+min(r, 8-r)) % 8

    def attack(self, attacker, target, opportunity=False, missile=None):
        b, t, c, tc, g = attacker.b, target.b, self.record(attacker), self.record(target), self.s.g
        if not b[ACTIVE] or not t[ACTIVE]: return True
        g['8DC8'] = g['8DC7'] + 15
        if tc[15] < 2 and not opportunity: tc[9] = direction_to(*self.position(target), *self.position(attacker))
        direction = direction_to(*self.position(attacker), *self.position(target))
        aname, tname = (bytes(r[1:1+r[0]]).decode('latin1') for r in (b,t))
        self.show('facing', target)
        self.show('clear', attacker, panel_clear=True)
        self.show('status', attacker, status=True)
        c[9] = direction
        self.show('swing', attacker, .1, pose=1)
        c[10] = self.index(target)
        if missile is not None: self.missile(attacker, target, missile)
        weapon = rec.readied(attacker)[0]
        if weapon is not None and weapon[0x2E] in (28, 29): self.missile(attacker, target, weapon)
        if not any(b[0x1AD:0x1AF]):
            self.show('facing', attacker, pose=0)
            return self.reset(attacker)
        old_sel = self.s.sel; self.s.sel = self.index(attacker)
        g['87E0'] = g['87E1'] = g['8E11'] = g['8E12'] = g['87D4'] = 0; c[8] = 1
        if self.disabled(target):
            message(self.game, '%s slays helpless %s with one cruel blow' % (
                aname, tname), display_text=aname+'\nslays helpless\n'+tname+'\nwith one cruel blow',names=((0,self.index(attacker)),(2,self.index(target))))
            slot = c[4]
            while slot > 1 and not b[0x1AC+slot]: slot -= 1
            c[4] = slot; g['8E1'+str(slot)] += 1
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
            distance = self.distance(attacker, target)
            reach = (rec._T(w, 12)-1)//3 if self.ranged(attacker) else distance
            penalty = (2 if distance > reach else 0) + (3 if distance > 2*reach else 0)
            ac += penalty
            stop = any_hit = False
            for slot in range(c[4], 0, -1):
                while b[0x1AC+slot] and not stop:
                    b[0x1AC+slot] -= 1; c[4] = slot
                    g['combat.attacks'] = g.get('combat.attacks', 0)+1
                    g['8E1'+str(slot)] = g.get('8E1'+str(slot), 0)+1
                    hit = attack_roll(self.game, attacker, target, ac) or self.disabled(target)
                    if hit:
                        any_hit = True
                        g['87E'+str(slot-1)] += 1
                        g['87D9'] = b[0x1AE+slot]
                        g['87D4'] = max(0, roll(self.s, b[0x1AE+slot], b[0x1B0+slot]) + rec.sx(b[0x1B2+slot]))
                        _mod(self.game, 4, attacker); _mod(self.game, 5, target)
                        if back: g['87D4'] *= (b[0x117]+b[0x11E]*rec.dual(attacker)-1)//4+2
                        g['87D5'] = 0; damage = g['87D4']
                        verb = '-Backstabs-' if back else 'Attacks'
                        self.show('clear', attacker)
                        message(self.game, '%s %s %s%s Hitting for %d point%s of damage' % (
                            bytes(b[1:1 + b[0]]).decode('latin1'), verb, bytes(t[1:1 + t[0]]).decode('latin1'),
                            ' (from behind)' if behind and not back else '', damage, '' if damage == 1 else 's'),
                            display_text='%s\n%s\n%s\n%sHitting for %d point%s of damage' %
                            (aname,verb,tname,'(from behind) ' if behind and not back else '',damage,'' if damage==1 else 's'),
                            names=((0,self.index(attacker)),(2,self.index(target))))
                        if t[ACTIVE]: self.apply_damage(target, damage)
                        if t[ACTIVE] and damage > 0: _mod(self.game, slot+1, attacker)
                        if not t[ACTIVE] and w is not None and w[0x2E] == 0x42: b[0x1AC+slot] = 0
                    stop = not b[ACTIVE] or not t[ACTIVE]
            if not any_hit:
                self.show('clear', attacker)
                message(self.game, '%s Attacks %s and Misses' % (
                    aname,tname), display_text=aname+'\nAttacks\n'+tname+'\nand Misses',names=((0,self.index(attacker)),(2,self.index(target))))
            c[5] = 0
        if missile is not None:
            if missile[0x39]: missile[0x39] = max(0, missile[0x39]-g['8E11'])
            if not missile[0x39]:
                if self.ranged_melee(attacker) and missile[0x3D] != 0x17:
                    copy = bytearray(missile); copy[0x34] = 0
                    index = g.get('combat.treasure_boundary', len(self.s.treasure_items)-1)+1
                    self.s.treasure_items.insert(index, copy); g['combat.treasure_boundary'] = index
                attacker.items.remove(missile)
        rec.recalc_character(attacker, self.s.r1[0x372]); self.s.sel = old_sel
        done = not b[ACTIVE] or not any(b[0x1AD:0x1AF])
        if done: self.reset(attacker)
        self.show('clear', attacker)
        self.show('facing', attacker, pose=0)
        self.recount(); return done

    def sweep(self, attacker, target):
        c = self.record(attacker)
        if attacker.b[0x1AD] >= c[5] or target.b[0xEE] or self.distance(attacker, target) != 1: return False
        near = self.targets(attacker, 1, 1-attacker.b[SIDE])
        if target in near: i = near.index(target); near[0], near[i] = near[i], near[0]
        else: near.insert(0, target)
        foes = [t for t in near if t.b[0xEE] == 0]
        if len(foes) <= attacker.b[0x1AD]: return False
        count = min(len(foes), c[5])
        name = bytes(attacker.b[1:1 + attacker.b[0]]).decode('latin1')
        message(self.game, name + ' sweeps', display_text=name + '\nsweeps', actor=self.index(attacker), names=((0, self.index(attacker)),))
        self.show('clear', attacker)
        for t in foes[:count]:
            if not attacker.b[ACTIVE]: break
            self.face_toward(attacker, t); attacker.b[0x1AD] = 1; c[4] = 1; self.attack(attacker, t)
        self.reset(attacker); return True

    def confirm_ally(self, attacker, target, moving=False, cursor=True):
        if target.b[SIDE] != attacker.b[SIDE] or attacker.b[CTRL]: return True
        if self.game.ask('COMBAT_ACTION', ['yes', 'no'], actor=self.index(attacker),
                         target=self.index(target), action='attack-ally', moving=moving, cursor=cursor, prompt='Attack Ally: '): return False
        self.s.g['8DC6'] = 1; self.s.r1[0x333] = 1
        for npc in self.s.party:
            if npc.b[STATUS] == 0 and npc.b[0xFF] > 127 and npc.b[0xFF] != 0xB3:
                npc.b[SIDE] = 1; self.record(npc)[10] = -1
        self.recount()
        return True

    def attack_command(self, attacker, target, moving=False, cursor=True):
        if moving and self.ranged(attacker) and not self.ranged_melee(attacker):
            self.refusal(attacker, 'Not with that weapon'); return False
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
        legal = self.attack_targets(character); out = []
        for d in range(8):
            who = self.ahead(character, d)[0]
            if who >= 0 and self.chars[who] in legal: out.append((d, self.chars[who]))
        return out

    def move_command(self, character, direction, cursor=True):
        self.record(character)[9] = direction
        self.show('facing', character)
        who, tile, _, _ = self.ahead(character, direction)
        if who >= 0: return self.attack_command(character, self.chars[who], moving=True, cursor=cursor)
        if tile == 0:
            if self.game.ask('COMBAT_ACTION', ['yes', 'no'], actor=self.index(character), action='flee-confirm', cursor=cursor, prompt='Flee:'):
                return False
            return self.flee(character)
        cost = 255 if terrain_cost(tile) == 255 else terrain_cost(tile) * (3 if direction % 2 else 2)
        if cost > self.record(character)[6]:
            self.refusal(character, "can't go there"); return False
        return self.move(character, direction)

    def refusal(self, character, text):
        message(self.game, text, display=False)
        self.show('command', character, self.s.g.get('67D6', 0)/10, command=text)
        self.show('command', character, command='')

    def move(self, character, direction):
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
                self.show('view', character, margin=2, merge=True)
            p[0] += DX[direction]; p[1] += DY[direction]
            c[6] = max(0, c[6]-terrain_cost(self.tile(*p[:2]))*(3 if direction % 2 else 2))
            c[15] = c[18] = 0; self.rebuild()
            self.show('move', character, margin=3 if character.b[CTRL] else 1)
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
        if not character.b[ACTIVE]: return
        _, _, cloud, poison = self.ahead(character)
        b = character.b
        if cloud and moving and not b[0xF2] and not any(rec.has_effect(character, t) for t in (0x1F, 0x63)) and not b[0x15E] & 8:
            saved = saving_throw(self.game, character, 0)
            t, duration = (0x1E, 1) if saved else (0x1F, roll(self.s, 1, 4)+1)
            _magic().apply_effect(self.game, character, t, duration, 255, False, text='starts to cough' if saved else 'chokes and gags from nausea')
            effect = next((e for e in character.effects if e[0] == t), None)
            if effect is not None: _magic().effect_callback(self.game, character, effect)
        if poison and b[ACTIVE] and b[0xEE] < 7:
            if b[0xEE] < 5 or not saving_throw(self.game, character, 0, -4 if b[0xEE] == 5 else 0):
                name = bytes(b[1:1 + b[0]]).decode('latin1'); who = ((0, self.index(character)),)
                message(self.game, name + ' is Poisoned', display_text=name + '\nis Poisoned', names=who)
                _magic().add_effect(self.game, character, 0x37, 0, 255)
                message(self.game, name + ' is killed', display_text=name + '\nis killed', names=who, delay=0)
                self.kill(character)

    def guard(self, character):
        self.reset(character)
        if not self.record(character)[16]:
            self.record(character)[7] = 1
            self.show('guard',character,.06,bottom='Guarding')
        return True

    def bandage(self):
        for c in self.chars:
            if not self.record(c)[19] and c.b[SIDE] == 0 and c.b[STATUS] == 5:
                c.b[STATUS] = 4; self.record(c)[14] = 0
                name = bytes(c.b[1:1 + c.b[0]]).decode('latin1')
                message(self.game, name + ' is bandaged', display_text=name + '\nis bandaged', names=((0, self.index(c)),))
                self.show('clear', c)
                return True
        return False

    def flee(self, character):
        enemies = self.targets(character, 255, 1-character.b[SIDE])
        mine = self.move_allowance(character)//2
        theirs = max((self.move_allowance(t)//2 for t in self.chars if t.b[ACTIVE] and t.b[SIDE] != character.b[SIDE]), default=0)
        ok = not enemies or theirs < mine or theirs == mine and roll(self.s, 1, 2) == 1
        if ok:
            name = bytes(character.b[1:1 + character.b[0]]).decode('latin1')
            message(self.game, name + ' Got Away', display_text=name + '\nGot Away', names=((0, self.index(character)),))
            self.show('clear', character); self.kill(character, 3)
        else: self.refusal(character, 'Escape is blocked')
        self.reset(character); return ok

    def spells(self, character, all_memorized=False):
        if self.s.r0[0xE5] or not self.record(character)[1] or not any(0 < s <= 117 for s in character.b[0x1E:0x69]): return []
        if all_memorized:
            if not character.b[ACTIVE] or character.b[STATUS] == 1 or any(rec.has_effect(character, e) for e in (0x44, 0x15)): return []
            return sorted({s for s in character.b[0x1E:0x69] if 0 < s <= 117
                           and (character.b[CTRL] or _magic().can_cast(character, s, False, True))})
        return _magic().legal_spells(character, combat=True)

    def cast(self, character, spell_id):
        if not _magic().spell(spell_id)[11]:
            self.refusal(character, 'Camp Only Spell'); return False
        c = self.record(character); delay = _magic().spell(spell_id)[12]//3
        if not delay:
            _magic().cast(self.game, character, spell_id, combat=True)
            self.reset(character); return True
        name = bytes(character.b[1:1 + character.b[0]]).decode('latin1')
        message(self.game, name + ' Begins Casting', display_text=name + chr(10) + 'Begins Casting', actor=self.index(character), names=((0, self.index(character)),), status=False)
        self.show('clear', character)
        c[0] = spell_id; c[3] = max(1, c[3]-delay)
        order = self.s.g['combat.order']; cursor = self.s.g['combat.cursor']; slot = cursor+1
        while slot < len(order) and self.s.g['combat.records'][order[slot]][3] >= c[3]:
            if self.s.g['combat.records'][order[slot]][3] == c[3] and roll(self.s, 1, 2) != 1: break
            slot += 1
        moved = order.pop(cursor); order.insert(slot-1, moved); self.s.g['combat.cursor'] -= 1
        return True

    def queued_cast(self, character):
        c = self.record(character); sp = c[0]; c[0] = 0; self.game.presentation_casting = self.index(character)
        try: _magic().cast(self.game, character, sp, combat=True)
        finally: self.game.presentation_casting = None
        self.reset(character)

    def done_menu(self, character):
        c = self.record(character); options = ['delay', 'quit']
        if any(t.b[STATUS] == 5 and t.b[SIDE] == 0 and not self.record(t)[19] for t in self.chars): options.append('bandage')
        options += ['exit', 'speed']
        if not self.ranged(character) or self.ranged_melee(character): options.append('guard')
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
        if self.s.r0[0xE5]: return []
        from sm.titles.ssb.units.shops import groups
        return [i for i, group in groups(character.items) if self.item_spells(character, i)
                and (group[0][0x2E] in (0x27, 0x28, 0x49) or group[0][0x34])]

    def item_spells(self, character, index):
        it = character.items[index]; out = []
        if it[0x2E] in (0x27, 0x28, 0x49):
            indices = range(index+1, min(len(character.items), index+1+it[0x39])) if it[0x2E] == 0x49 else (index,)
            for child, offset, sid in _magic().scroll_spells(character, indices, combat=True):
                if _magic().spell(sid)[11]: out.append((sid, child, offset))
        elif it[0x3E] < 128 and 0 < it[0x3D] <= 117 and _magic().spell(it[0x3D])[11]: out.append((it[0x3D], index, 0))
        return out

    def use_item(self, character, index):
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
        out = []
        if self.legal_moves(character): out.append('move')
        if self.attack_targets(character): out.append('attack')
        if self.spells(character, all_memorized=True): out.append('cast')
        if self.usable_items(character): out.append('use')
        if not self.ranged(character) or self.ranged_melee(character): out.append('guard')
        if any(self.ahead(character, d)[1] == 0 for d in range(8)): out.append('flee')
        out += ['quick', 'done', 'view'] + ([] if 'attack' in out else ['aim'])
        if 'move' not in out and self.record(character)[6] > 0: out.append('move')
        if character.items and 'use' not in out: out.append('use')
        out.append('quick-off')
        out += ['magic-toggle', 'divine-intervention']
        return out

    def player_turn(self, character):
        i = self.index(character); action = None
        while character.b[ACTIVE] and self.record(character)[3] > 0:
            if action != 'move':
                actions = self.legal_actions(character)
                action = actions[self.game.ask('COMBAT_ACTION', actions, actor=i, round=self.s.g['8DC7'], at=getattr(self.game.vm, 'at', 0))]
                if action == 'move':
                    move_origin = (*self.position(character), self.record(character)[6], self.record(character)[9])
                    move_first = True
            if action == 'move':
                dirs = self.legal_moves(character); x, y = self.position(character)
                attacks = self.move_attacks(character)
                ordered = dirs + [d for d, _ in attacks]
                ordered += [None] + [d for d in range(8) if d not in ordered]
                cells = ['cancel' if d is None else (x+DX[d], y+DY[d]) for d in ordered]
                cells.append('done')
                pick = self.game.ask('TARGET', cells, actor=i, action=action, cursor=move_first)
                if cells[pick] in ('cancel', 'done'):
                    if cells[pick] == 'cancel':
                        x0, y0, allowance, facing = move_origin
                        self.record(character)[6] = allowance
                        if not self.place(character, x0, y0): return
                        self.show('view', character, margin=0)
                        self.record(character)[9] = facing
                    if self.record(character)[6] < 2: self.record(character)[6] = 0
                    action = None
                else:
                    before = self.position(character)
                    if self.record(character)[9]//4 != ordered[pick]//4: move_first = False
                    if self.move_command(character, ordered[pick], cursor=move_first): return
                    if self.position(character) != before: move_first = False
            elif action == 'attack':
                targets = self.attack_targets(character); ids = [self.index(t) for t in targets]
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
                options = spells + ['cancel'] + [s for s in self.spells(character, all_memorized=True) if s not in spells]
                pick = options[self.game.ask('SPELL', options, actor=i)]
                if pick != 'cancel' and self.cast(character, pick): return
            elif action == 'use':
                items = self.usable_items(character)
                if not items:
                    from sm.titles.ssb.units import shops
                    shops.item_menu(self.game, character, 'combat'); self.reset_attacks(character)
                    continue
                pick = self.game.ask('LIST', items + [None], actor=i, action='use')
                if pick < len(items) and self.use_item(character, items[pick]): return
            elif action == 'guard': self.guard(character); return
            elif action == 'flee': self.flee(character); return
            elif action == 'quick-off':
                self.quick_off(); action = None; continue
            elif action == 'magic-toggle':
                self.toggle_magic(character); action = None; continue
            elif action == 'divine-intervention':
                if self.divine_intervention(character):
                    self.show('view', character, margin=3, cursor=False); return
                self.refusal(character, "That doesn't work")
                action = None; continue
            elif action == 'quick':
                self.show('command', character, .2, command='', cursor=True)
                character.b[CTRL] = 1; target = self.record(character)[10]
                if target >= 0 and self.chars[target].b[SIDE] == character.b[SIDE]: self.record(character)[10] = -1
                self.computer_turn(character); return
            elif action == 'view':
                from sm.titles.ssb.units import shops
                shops.view(self.game, 'combat', character=character)
                self.reset_attacks(character)
            elif self.done_menu(character): return

    def weapon_score(self, character, item):
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
            if slots[1] is not None and not slots[1][0x36]: b[0x199] = (b[0x199]-rec._T(slots[1], 1)) & 255
            if choice is not None: shops.ready(self.game, character, choice, recalculate=False)
        rec.recalc_character(character, self.s.r1[0x372]); self.reset_attacks(character)
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
        b, c, g = character.b, self.record(character), self.s.g; c[20] = 0
        name = bytes(b[1:1 + b[0]]).decode('latin1'); who = ((0, self.index(character)),)
        if c[16]:
            c[20] = 1; message(self.game, name + ' is forced to flee', display_text=name + '\nis forced to flee', names=who)
            self.show('clear', character); return False
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
        if b[0x13] > 5:
            message(self.game, name + ' Surrenders', display_text=name + '\nSurrenders', names=who)
            self.show('clear', character); self.kill(character, 4, downed=False); return self.reset(character)
        return False

    def spell_worth_casting(self, character, sp, minimum):
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
            for friend in self.targets(foe, row[15], character.b[SIDE], own=[self.position(foe)]):
                if row[8] != 1 and not saving_throw(self.game, friend, row[9], -2 if character.b[SIDE] == 0 else 8): unsafe = True
            if unsafe: return False
        return True

    def ai_magic(self, character, items=False):
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
        if not c[22] or not c[1] or rec.has_effect(character, 0x44): return False
        spells = [sp for sp in character.b[0x1F:0x69] if sp]
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
        c = self.record(character); target = c[10]
        if keep and 0 <= target < len(self.chars):
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
                candidates[slot] = None
        return None

    def ai_move(self, character, target):
        c, b, g = self.record(character), character.b, self.s.g
        self.show('command', character, command='Move/Attack, Move Left = %d' % (c[6]//2))
        if self.check_interrupt(character): return False
        if c[6]//2 <= 0 or c[3] <= 0: return False
        if b[0xFF] >= 128 and g['8E13'] > g.get('87E2', 0)+roll(self.s, 1, 100) and b[SIDE] != 1: return False
        if not c[20] and rec.readied(character)[2] is None and b[0x6C] == 5 and not rec.dual(character): return False
        if c[20]:
            c[21] = roll(self.s, 1, 2); f = self.s.dir
            d = (f-((f+2) % 4)//2+4*int(b[SIDE] == 0)) % 8
        elif target is not None: d = direction_to(*self.position(character), *self.position(target))
        else: return False
        ds = ssb_data.stexe(); chosen = None
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
                if g['59C7'] > 2: c[6] = 0; return None
                if self.ai_pick_target(character) is None: return False
        if chosen is None: return None
        g['59C6'] = chosen; c[9] = chosen
        self.show('facing', character)
        self.move(character, chosen); return bool(b[ACTIVE] and c[3])

    def quick_off(self, skip_status=None):
        for p in self.s.party:
            if p.b[0xFF] < 0x80 and p.b[0x1A6] != skip_status: p.b[CTRL] = 0

    def toggle_magic(self, character):
        self.s.g['8E14'] = int(not self.s.g['8E14'])
        self.refusal(character, 'Magic On' if self.s.g['8E14'] else 'Magic Off')

    def divine_intervention(self, character):
        args = getattr(self.game, 'dos_args', ())
        data = ssb_data.stexe(); password = data[0x1910:0x1910 + data[0x190F]].decode('cp437')
        if len(args) < 2 or args[1] != password: return False
        self.refusal(character, 'The Gods intervene!')
        for other in self.chars:
            if other.b[SIDE] == 1:
                other.b[ACTIVE], other.b[STATUS] = 0, 6
                self.s.g['combat.positions'][self.index(other)][2] = 0
            self.move_allowance(other)
        self.rebuild()
        view = getattr(self.game, 'presentation_view', None)
        self.show('redraw', character, focus=tuple(v+3 for v in view) if view is not None else self.position(character), margin=255)
        return True

    def check_interrupt(self, character):
        hook = getattr(self.game, 'ai_check', None)
        if hook is None: return False
        key = hook()
        if key == '2': self.toggle_magic(character); return False
        if key == '-': self.divine_intervention(character); return False
        if key != ' ': return False
        self.quick_off(skip_status=1)
        if character.b[CTRL]: return False
        self.record(character)[3] = 20
        return True

    def computer_turn(self, character):
        c, g = self.record(character), self.s.g
        stop = self.check_interrupt(character)
        self.show('clear', character, command='', cursor=True)
        if not character.b[ACTIVE]: self.reset(character); return
        if not 1 <= c[21] <= 4 or roll(self.s, 1, 4) == 1:
            c[21] = roll(self.s, 1, 2)+4 if roll(self.s, 1, 8) == 8 else roll(self.s, 1, 4)
        done = stop or self.morale(character)
        if c[20] and not c[16]:
            name = bytes(character.b[1:1 + character.b[0]]).decode('latin1')
            message(self.game, name + ' flees in panic', display_text=name + '\nflees in panic', names=((0, self.index(character)),))
            self.show('clear', character)
        if done: return
        if self.ai_magic(character, items=True): self.reset(character); return
        if c[0]:
            self.queued_cast(character); return
        if self.ai_magic(character): return
        self.choose_weapons(character)
        if self.check_interrupt(character): return
        def end():
            if self.disabled(character) or self.ranged(character) or not c[3]: self.reset(character)
            else: self.guard(character)
        for _ in range(40):
            if self.ai_pick_target(character, True) is None or c[3] <= 0 or not character.b[ACTIVE]: end(); return
            if self.ai_attack_loop(character, end): return
        end()

    def ai_attack_loop(self, character, end):
        c, g = self.record(character), self.s.g; side = 1-character.b[SIDE]; steps = 0
        def stored():
            return self.chars[c[10]] if 0 <= c[10] < len(self.chars) else None
        g['59C6'], g['59C7'], g['59C8'] = 8, 0, 0; _mod(self.game, 14, character)
        if character.b[SIDE] == 0 and self.bandage(): c[3] = 0
        while character.b[ACTIVE]:
            while c[20] and c[6] > 0 and 0 < c[3] < 20:
                if self.ai_move(character, stored()) is False and c[3] not in (0, 20): end()
            if not character.b[ACTIVE] or c[3] in (0, 20): return True
            steps += 1
            if steps > 20: end(); return True
            w = rec.readied(character)[0]; reach = (rec._T(w, 12)-1) & 255 if w is not None else 1
            if reach in (0, 255): reach = 1
            t = stored(); hit = False
            if t is not None and (not t.b[ACTIVE] or t.b[SIDE] == 0): t = None
            if t is not None and self.can_see(character, t):
                hit = self.walk_line(*self.position(character), *self.position(t), reach)[0]
            if not hit:
                near = self.targets(character, reach, side)
                if not near:
                    if self.ai_pick_target(character, False) is None: end(); return False
                    if self.ai_move(character, stored()) is False:
                        if c[3] != 20: end()
                        return True
                    continue
                t = near[roll(self.s, 1, len(near))-1]
                if self.ranged(character) and not self.ranged_melee(character) and self.targets(character, 1, side):
                    self.choose_weapons(character); return False
                hit = self.distance(character, t) == 1 or self.can_see(character, t)
            if not hit: continue
            x, y = self.position(character); d = direction_to(x, y, *self.position(t)); ds = ssb_data.stexe()
            self.show('view', character, margin=2, cursor=False, focus=(x+rec.sx(ds[0x1A90+d]), y+rec.sx(ds[0x1A99+d])))
            if self.sweep(character, t): self.reset(character); return False
            self.face_toward(character, t); missile = None
            if self.ranged(character):
                missile = self.ammo(character)[1]
                if self.ranged_melee(character) and self.distance(character, t) == 1: missile = None
            if self.attack(character, t, missile=missile): return True
            if not t.b[ACTIVE]: return False
        return True

    def do_turn(self, character):
        c = self.record(character); c[15] = c[18] = c[7] = 0; _mod(self.game, 7, character)
        if c[3] <= 0: return
        if c[3] == 20: c[3] = 19
        self.s.sel = self.index(character); rec.recalc_character(character, self.s.r1[0x372])
        self.show('view', character, margin=2, turn_start=True, cursor=True)
        self.show('clear', character, panel_clear=True)
        self.show('status', character, status=True, merge=True)
        _mod(self.game, 15, character)
        if not c[0]: _mod(self.game, 21, character)
        if c[3] <= 0: return
        if character.b[CTRL]: self.computer_turn(character)
        elif c[0]:
            self.queued_cast(character)
        else: self.player_turn(character)

    def end_round(self):
        ages = [rec.rdw(c.b, 0x6E) for c in self.s.party]
        self.game.vm.advance_clock(1, 1); g = self.s.g; g['8DC7'] += 1
        if ages != [rec.rdw(c.b, 0x6E) for c in self.s.party]: g['7D44'] = 1
        for character in self.s.monsters:
            if character.effects: _magic().tick_effects(self.game, character, 1)
        self.monster_hp_percent()
        self.recount()
        for character in self.chars:
            _mod(self.game, 19, character); self.hazards(character)
            c = self.record(character)
            if character.b[STATUS] == 5:
                c[14] += 1
                if c[14] > 9: character.b[STATUS] = 6
        if any(t.b[STATUS] == 5 and t.b[SIDE] == 0 and not self.record(t)[19] for t in self.chars):
            self.refusal(None, 'Your Teammate is Dying')
        party, enemies = self.recount()
        if party and not enemies and not g.get('67E9', 0):
            options = ['continue', 'end']
            return bool(self.game.ask('MENU', options, action='continue-battle', round=g['8DC7']))
        return not party or not enemies or g['8DC7'] >= g['8DC8']

    def finish(self):
        g = self.s.g
        if g.get('7D44'):
            for character in self.s.party:
                b = character.b; cap = {1: 1600, 2: 325, 3: 525, 4: 750, 5: 199, 6: 120}.get(b[0x6B])
                if cap is None or b[STATUS] >= 6: continue
                age = rec.rdw(b, 0x6E); name = bytes(b[1:1 + b[0]]).decode('latin1'); who = ((0, self.index(character)),)
                if age > cap:
                    message(self.game, 'The strain of this last battle has worn heavily on %s.  ' % name)
                    message(self.game, ('She' if b[0x11F] else 'He') + ' breathes deeply one last time and crumples to the ground.')
                    message(self.game, name + ' dies from age', display_text=name + '\ndies from age', names=who)
                    self.kill(character, 8)
                    left = [c for c in self.s.party if c is not character and c.b[ACTIVE] == 1 and c.b[STATUS] == 0 and c.b[SIDE] != 1]
                    message(self.game, 'Sadly, no party member witnesses the passing of the champion.' if not left else
                            bytes(left[-1].b[1:1 + left[-1].b[0]]).decode('latin1') + ' weeps at the loss of such a venerable companion.' if len(left) == 1 else
                            " The remaining party members are overcome with grief as they search %s's body for valuables." % name)
                elif age > cap - 10:
                    message(self.game, name + ' is looking very old', display_text=name + '\nis looking very old', names=who)
            g['7D44'] = 0
        self.recount()
        for character in self.chars:
            if rec.has_effect(character, 0x0B) and character.b[STATUS] == 0: character.b[STATUS] = 3 if g['87CD'] > 1 else 0
            self.strip(character)
        party_fled = any(c.b[STATUS] == 3 for c in self.s.party) and not any(c.b[STATUS] in (0, 1) for c in self.s.party)
        monsters_fled = any(c.b[STATUS] == 3 for c in self.s.monsters)
        alive = any(c.b[STATUS] in (0, 1, 3) and c.b[SIDE] == 0 and c.b[0xFF] < 128 for c in self.s.party)
        if self.s.r1[0x2E6]: alive |= any(c.b[ACTIVE] or c.b[STATUS] in (3, 4, 5) for c in self.chars)
        self.s.party_dead = int(not alive)
        g['combat.result'] = 0x80 if not alive else 0x81 if party_fled else 1 if monsters_fled else 0
        g['combat.active'] = 0; g['67F8'] = 1
        return g['combat.result']


def run(game):
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
    from sm.titles.ssb.units._combat_test import check
    check()
