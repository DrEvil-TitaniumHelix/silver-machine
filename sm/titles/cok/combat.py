from enum import Enum
from functools import lru_cache
import hashlib

from sm.titles.ssb.units.combat import Combat as RetainedCombat, line, in_cone
from . import rules, effects
from .records import Item, Effect, split_records
from .town import field, put, earlier_class, monster_record
from .faults import BindingRequired


class Kind(str, Enum):
    ACTION = 'COMBAT_ACTION'
    AUTO = 'COMBAT_AUTO'
    MOVE = 'COMBAT_MOVE'
    TARGET = 'TARGET'
    SPELL = 'COMBAT_SPELL'
    AIM = 'COMBAT_SPELL_AIM'
    DONE = 'COMBAT_DONE'
    CONFIRM = 'COMBAT_CONFIRM'
    LOOT = 'COMBAT_LOOT'
    ACK = 'ACK'


DX, DY = (0,1,1,1,0,-1,-1,-1,0), (-1,-1,0,1,1,1,0,-1,0)
FIGHT_KEYS = ['space','Alt-m','Alt-q','Alt-a']
I = {name: offset for name, (offset, _) in Item.FIELDS.items()}
TABLES = {
    'ai': (49148,30,'406abfec8f5d35d8258e69ed3fac9bdc2a889a40f9cf2a44a1ea972909f1de35'),
    'ring_direction': (49178,16,'6eb3511d57e7705f2de07752237987e7f1950a336634e19997ffdc919678827d'),
    'ring_quadrant': (49194,16,'7b5d1b03210c50346f68b248f36367eb1162fbc54b91e1fabc831e931869973b'),
    'facing': (49210,4,'7dde7343fca717d7417634c1786c932416c6248af5f33a5498095a64a4f7b3a4'),
    'start_x': (49214,8,'a6b24dca1f0fc9b8f07c11f93d4f001a6dd0374db8ae1ea79f5e2b714d7bfbef'),
    'start_y': (49222,8,'f3deb66fff4455ad854c22dad0fd504f5fda85fddfadaf2f644701d23cdb3752'),
    'bands': (49230,60,'505c860b2f99dd4a28c048c0b26fa3fd368c829b332721591ae123c61b690949'),
    'classes': (49298,32,'9f1507fe44321e135e069681e6a93708e1a094ff8004849c745bf4d94058e346'),
    'terrain': (56136,260,'0de588c54e15d02717ff5cfda2d1c0000361fb1154be9becc086d45698b15ee7'),
    'footprints': (56396,32,'680f39869307fa7b6e9cac182985e2299becda8e34bf41af48dbb449b18da0f5'),
    'turning': (49330,156,'e1347618e3a176208626d4a21c0c4bf3b22134c5ecab06846a76b629db9d27ed'),
    'cone_sides': (51700,32,'2583a86388a4080cdb74345abe0fed43adc3f161d940866d421636353cb8c295'),
}


@lru_cache(maxsize=4)
def tables(assets):
    result = {}
    for name, (offset, size, digest) in TABLES.items():
        raw = assets.resident[offset:offset+size]
        if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Champions combat table differs: '+name)
        result[name] = raw
    return result


def signed(value): return (value+128)%256-128
def direction_to(x, y, tx, ty):
    if (x,y) == (tx,ty): return 8
    dx,dy = abs(tx-x),abs(ty-y)
    steep,diagonal = dx*618//256 <= dy, dx*106//256 <= dy <= dx*618//256
    shallow = dx*106//256 >= dy
    tests = (ty<=y and steep, ty<y and tx>x and diagonal, tx>=x and shallow, ty>y and tx>x and diagonal,
             ty>=y and steep, ty>y and tx<x and diagonal, tx<=x and shallow, ty<y and tx<x and diagonal)
    return next((d for d,yes in enumerate(tests) if yes),8)
def name(c): return bytes(c.b[1:1+c.b[0]]).decode('cp437')
def has(c, ident): return any(e[0] == ident for e in c.effects)


def roll(game, count, sides, reason, actor=-1, target=-1):
    before = game.s.seed
    faces = tuple(game.s.random(sides)+1 for _ in range(count))
    result = sum(faces)&255
    if not hasattr(game, 'combat_log'): game.combat_log = []
    game.combat_log.append(dict(event='dice', reason=reason, actor=actor, target=target,
                                count=count, sides=sides, faces=faces, result=result,
                                before=before, after=game.s.seed))
    return result


def load_monsters(game, ident, count, picture):
    s, assets = game.s, game.assets
    count = min(max(1,count&255), max(0,63-len(s.chars())))
    if not count: return
    stem = 'MON%d' % s.dataset
    raw = monster_record(assets.records, s.dataset, ident)
    if field(rules.character(raw,[],[],rid=ident),'undead'): s.g['cok.undead_count'] = (s.g.get('cok.undead_count',0)+1)&255
    items = [bytes(r) for r in split_records(assets.records(stem+'ITM').get(ident,b''), Item)]
    effects = [bytes(r) for r in split_records(assets.records(stem+'SPC').get(ident,b''), Effect)]
    slot = getattr(game.vm, 'icon_slot', 8)
    icons = s.g.setdefault('cok.monster_icons', [])
    for copy in range(count):
        c = rules.character(raw, items if not copy else items[::-1], effects if not copy else effects[::-1], rid=ident)
        if field(c,'side') == 1 and 0 < s.r0[0x1F4] < 6:
            hp, maximum = (field(c,k)*(s.r0[0x1F4]+1)//4 for k in ('hp','hp_max'))
            if not hp or not maximum: hp = maximum = 1
            put(c,'hp',hp); put(c,'hp_max',maximum)
        put(c,'order',slot)
        icons.append((len(s.chars()),s.dataset,picture,slot))
        s.monsters.append(c)
    game.vm.icon_slot = slot+1


class Battle:
    def __init__(self, game):
        self.game, self.s, self.t = game, game.s, tables(game.assets)

    @property
    def data(self): return self.s.g['cok.battle']
    @property
    def chars(self): return self.s.chars()
    def record(self, i): return self.data['actors'][i]
    def die(self, count, sides, reason, actor=-1, target=-1): return roll(self.game,count,sides,reason,actor,target)
    def damage_dice(self, count, sides, reason, actor=-1, target=-1):
        self.data.setdefault('roll',{})['dice_count'] = count
        return self.die(count,sides,reason,actor,target)
    def event(self, event, **details): self.game.combat_log.append(dict(event=event,round=self.data['round'],**details))
    def footprint(self, size):
        raw = self.t['footprints'][(size-1)*8:size*8] if size else b''
        return [(signed(raw[i]),signed(raw[i+1])) for i in range(0,len(raw),2) if signed(raw[i]) >= 0]
    def cells(self, i, x=None, y=None):
        r = self.record(i)
        x, y = (r['x'] if x is None else x), (r['y'] if y is None else y)
        return [(x+dx,y+dy) for dx,dy in self.footprint(r['size'])]
    def tile(self, x, y): return self.data['tiles'][y*50+x] if 0 <= x < 50 and 0 <= y < 25 else 0
    def terrain(self, tile, column=0): return self.t['terrain'][(tile-1)*4+column] if 1 <= tile <= 65 else 255
    def put_tile(self, x, y, tile): self.data['tiles'][y*50+x] = tile
    def occupancy(self): return {cell:i for i in range(len(self.chars)) for cell in self.cells(i)}
    def teams(self): return [sum(field(c,'active') != 0 and field(c,'side') == side for c in self.chars) for side in (0,1)]
    def count_teams(self):
        self.data.pop('ghosts',None)
    def ghost(self, i):
        g = self.data.setdefault('ghosts',[0,0]); g[field(self.chars[i],'side')&1] += 1
    def team(self, side): return self.teams()[side]+self.data.get('ghosts',(0,0))[side]
    def probe(self, i, direction=8):
        r, occupied = self.record(i), {cell:j for j in range(len(self.chars)) if j != i for cell in self.cells(j)}
        occupant, terrain, highest = -1, 23, 1
        for x,y in self.cells(i,r['x']+DX[direction],r['y']+DY[direction]):
            if (other := occupied.get((x,y), -1)) not in (-1,i): occupant = other
            tile = self.tile(x,y)
            if not tile: terrain = 0
            elif tile not in (29,30) and terrain and self.terrain(tile) >= highest: terrain,highest = tile,self.terrain(tile)
        return occupant,terrain

    def wilderness(self):
        self.data['tiles'] = bytearray([23]*1250)
        terrain_class = self.t['classes'][15]
        threshold = 75 if terrain_class&16 else 35 if terrain_class&32 else 0
        if self.die(1,100,'river chance') <= threshold:
            column = 34-self.die(5,4,'river start')
            column -= (column+2)%7
            for row in range(25):
                if column > 49: continue
                self.put_tile(column,row,59+self.die(1,2,'river left'))
                if column < 49: self.put_tile(column+1,row,61+self.die(1,2,'river right'))
                if self.die(1,20,'ford chance') == 1 and column < 49:
                    self.put_tile(column+1,row,64)
                    if row < 24: self.put_tile(column+1,row+1,65)
                column += 1
        density = 10-5*bool(terrain_class&2)-2*bool(terrain_class&4)+5*bool(terrain_class&64)+10*bool(terrain_class&8)
        if density < 0: density = 1
        if not terrain_class&128:
            for x in range(50):
                for y in range(1,25):
                    if all(self.terrain(self.tile(x,j),3) == 22 for j in (y,y-1)) and self.die(1,100,'tree chance') <= density:
                        if self.die(1,100,'bush chance') <= density: self.put_tile(x,y,41+self.die(1,2,'bush type'))
                        else:
                            self.put_tile(x,y-1,31+self.die(1,6,'tree top'))
                            self.put_tile(x,y,37+self.die(1,4,'tree bottom'))
        weight = 50+10*bool(terrain_class&16)+30*bool(terrain_class&32)+20*bool(terrain_class&64)-10*bool(terrain_class&4)-20*bool(terrain_class&2)-50*bool(terrain_class&128)
        bands = next((b for low,high,b in ((-30,9,(0,0,0,30,15)),(10,29,(0,1,5,20,10)),(30,69,(0,2,5,10,5)),(70,89,(10,2,10,10,1)),(90,110,(15,5,15,10,1))) if low <= weight <= high), None)
        if bands is None: return
        for x in range(50):
            for y in range(25):
                if self.terrain(self.tile(x,y),3) != 22: continue
                value = self.die(1,100,'feature chance')
                for odds,base,sides in zip(bands,(57,47,43,54,49),(2,2,4,3,4)):
                    value -= odds
                    if value <= 0:
                        self.put_tile(x,y,base+self.die(1,sides,'feature type')); break

    def wall(self, x, y, direction):
        if self.game.geo.map is None:
            def face(x,y,d): return 0 if 0<=x<16 and 0<=y<16 or y==self.s.y and d in (2,6) else 1
            return face(x,y,direction)|face(x+DX[direction],y+DY[direction],(direction+4)%8)
        return RetainedCombat.wall(self,x,y,direction)

    def dungeon(self):
        self.data['tiles']=bytearray(1250)
        for dy in range(-2,3):
            for dx in range(-6,7):
                x,y=self.s.x+dx,self.s.y+dy
                w,n,e,south=(self.wall(x,y,d) for d in (6,0,2,4))
                def put(i,j,t):
                    tx,ty=21+6*dx+5*dy+i,10+5*dy+j
                    if 0<=tx<50 and 0<=ty<25: self.put_tile(tx,ty,t+1)
                for j in range(2,5):
                    for i in range(6): put(i,j,22)
                    if w==1: put(j-1,j,4); put(j,j,3); put(j+1,j,13)
                if w==3: put(1,2,8); put(5,4,0)
                for i in (3,4): put(i,0,5 if n==1 else 22); put(i,1,10 if n==1 else 22)
                op=self.wall(x,y-1,6)==self.wall(x-1,y,0)==0
                t1=(22 if w==0 else 13 if w==3 else 0 if op else 13) if n==0 else ((15 if op else 5) if w==0 else (18 if op else 2))
                t2=22 if n==0 else 17 if n==3 else 5
                t3=(22 if n==0 else 16 if op else 10) if w==0 else (20 if op else 7) if w==3 else (1 if op else 3)
                t4=(22 if n==0 else 23 if n==3 else 10) if w in (0,3) else (13 if n==0 else 21 if n==3 else 6)
                for i,j,t in ((1,0,t1),(2,0,t2),(1,1,t3),(2,1,t4)): put(i,j,t)
                ne,nn=self.wall(x,y-1,2),self.wall(x+1,y,0); op=ne==nn==0
                t1=(4 if ne==1 else 22) if n==0 else 15 if n==3 else 5
                t2=((22 if ne==0 else (24 if e==0 and nn else 1) if ne==3 else ((11 if nn else 7) if e==0 else 3))
                    if n==0 else 9 if e else 5 if nn else 17 if op else 19)
                t3=22 if n==0 else 16 if n==3 else 10
                t4=(22 if ne==0 else 4 if e else 12 if nn else 8) if n==0 else 14 if e else 10 if nn else 23
                for i,j,t in ((5,0,t1),(6,0,t2),(5,1,t3),(6,1,t4)): put(i,j,t)
                enclosed=3 not in (n,e,south,w) and 1 in (n,e,south,w) and not (n==south==1 and (e!=1 or w!=1) or e==w==1 and (n!=1 or south!=1))
                if not enclosed or not self.game.geo.attr(self.s,x,y)&64: continue
                for i in (2,3):
                    for j in range(2,5):
                        tx,ty=21+6*dx+5*dy+i+j,10+5*dy+j
                        if self.terrain(self.tile(tx,ty),3)!=22 or self.die(1,10,'dungeon decoration')>5: continue
                        self.put_tile(tx,ty,26)
                        for d in (0,2,4,6):
                            nx,ny=tx+DX[d],ty+DY[d]
                            if self.terrain(self.tile(nx,ny),3)==22 and self.die(1,10,'dungeon decoration neighbour')<=9: self.put_tile(nx,ny,27)

    def place(self, i, masks, counts):
        side, r = field(self.chars[i],'side'), self.record(i)
        q = (self.s.dir+4*side)%8//2
        anchor = (self.s.r1[0x2C1]*DX[self.s.dir]*side,self.s.r1[0x2C1]*DY[self.s.dir]*side)
        def open_ring(number):
            d=self.t['ring_direction'][q*4+number]
            return self.wall(self.s.x+anchor[0],self.s.y+anchor[1],d)!=1
        bx,by = anchor
        depth, ring, phase, first = 0,0,0,True
        for _ in range(10000):
            axis = self.t['ring_quadrant'][q*4+ring]//2
            if phase == 0:
                d = self.t['facing'][(axis+2)%4]
                ox = self.t['start_x'][4*bool(ring)+axis]+depth*DX[d]
                oy = self.t['start_y'][4*bool(ring)+axis]+depth*DY[d]
                x,y,span,tries,phase = ox,oy,1,1,1
            else:
                d = self.t['facing'][(axis+(1 if phase == 1 else 3))%4]
                x,y = ox+span*DX[d],oy+span*DY[d]
                if phase == 2: span += 1
                phase = 3-phase; tries += 1
            outside = not (0 <= x <= 10 and 0 <= y <= 5)
            escaped = not 0 <= x <= 10 and not 0 <= y <= 5
            if outside and not escaped or first and tries >= counts[side] or not first and tries > 11:
                depth += 1
                if side == 0 and q%2 and ring == 0 and depth == 1 and any(open_ring(k) for k in (1,2,3)): depth += 1
                phase,first = 0,False
            if escaped:
                ring += 1
                while ring<4 and not open_ring(ring): ring+=1
                if ring == 4: return False
                d = self.t['ring_direction'][q*4+ring]
                bx,by = anchor[0]+DX[d],anchor[1]+DY[d]
                depth,phase = 0,0
            if not outside and masks[side][ring][y*11+x]:
                r['x'],r['y'] = x+bx*6+by*5+22,y+by*5+10
                occupant,tile = self.probe(i)
                if occupant < 0 and tile and self.terrain(tile) < 255:
                    masks[side][ring][y*11+x] = 0
                    return True
        raise BindingRequired('Champions placement search did not terminate')

    def setup(self):
        self.s.g['cok.battle'] = dict(active=True,round=0,limit=15,actors=[],order=[],cursor=0,bank=[],messages=[],actor=-1)
        if not hasattr(self.game,'combat_log'): self.game.combat_log = []
        self.dungeon() if self.game.vm.is3d() else self.wilderness()
        face = self.t['facing'][self.s.dir//2]
        for i,c in enumerate(self.chars):
            rules.recalc_stats(c)
            r = dict(x=0,y=0,size=0,initiative=0,movement=0,phase=1,sweep=0,guard=0,attacked=0,
                     facing=(face+4*field(c,'side'))%8,target=-1,overkill=0,flanks=0,spread=0,turned=0,
                     turns=0,fleeing=0,stance=0,casting=0,cast_ok=True,item_ok=True,outsider=int(i >= len(self.s.party)))
            morale = field(c,'npc')&127
            if field(c,'side') == 0 and r['outsider'] and (not morale or morale > 102): put(c,'npc',self.s.r1[0x2C6]+128)
            self.data['actors'].append(r)
        counts = [(n+1)//2 for n in self.teams()]
        masks = []
        for side in (0,1):
            rings = []
            for ring in range(4):
                q = 4 if ring == 1 else (self.s.dir+4*side)%8//2
                rings.append([int(self.t['bands'][q*12+y*2] <= x <= self.t['bands'][q*12+y*2+1]) for y in range(6) for x in range(11)])
            masks.append(rings)
        i=0
        while i<len(self.chars):
            c=self.chars[i]
            self.record(i)['size'] = field(c,'dimensions')&7
            if not self.place(i,masks,counts):
                self.record(i)['size']=0
                if i>=len(self.s.party):
                    self.event('unplaced',actor=i,monster=c.rid)
                    self.s.monsters.pop(i-len(self.s.party))
                    self.data['actors'].pop(i)
                    self.s.g['cok.monster_icons']=[(j-(j>i),*entry) for j,*entry in self.s.g.get('cok.monster_icons',[]) if j!=i]
                    continue
            elif not field(c,'active'):
                if not self.record(i)['outsider']: self.body(i)
            elif field(c,'status') == 9: put(c,'active',0)
            if not field(c,'active'): self.record(i)['size'] = 0
            i+=1
        self.s.mode = 5; self.s.r1[0x333] = 0
        self.game.vm.clear_text(); self.game.vm.display = {'kind':None}
        self.event('setup',roster=[(c.rid,name(c),field(c,'hp')) for c in self.chars],positions=[(r['x'],r['y']) for r in self.data['actors']],terrain_hash=hashlib.sha256(self.data['tiles']).hexdigest())
        self.data.update(treasure_boundary=None,yell=-1,view=(self.record(0)['x']-3,self.record(0)['y']-3))
        for i in range(len(self.chars)): self.trigger(8,i); self.trigger(22,i)
        self.hp_percent()

    def index(self, char): return next(i for i,c in enumerate(self.chars) if c is char)
    def position(self, i): return self.record(i)['x'], self.record(i)['y']
    def direction(self, a, b): return direction_to(*self.position(a),*self.position(b))
    def scroll(self, x, y, margin):
        ox,oy = self.data['view']
        if abs(x-ox-3)>margin: ox = max(0,min(43,x-3))
        if abs(y-oy-3)>margin: oy = max(0,min(18,y-3))
        self.data['view'] = ox,oy
    def center(self, i, margin=2): self.scroll(*self.position(i),margin)
    def drawing(self): return self.data.get('gfx',True)
    def shown(self, i): return field(self.chars[i],'side') == 0 or self.visible(i)
    def turn_view(self, i):
        self.data['gfx'] = self.shown(i)
        if self.data['gfx']: self.center(i)
    def face(self, i, direction):
        if self.drawing() and not self.visible(i,True): self.center(i,3)
        self.record(i)['facing'] = direction
    def visible(self, i, whole=False):
        seen = [self.in_view(x,y) for x,y in self.cells(i)]
        return bool(seen) and (all if whole else any)(seen)
    def in_view(self, x, y):
        ox,oy = self.data['view']; return ox<=x<ox+7 and oy<=y<oy+7
    def distance(self, a, b):
        origins = self.cells(a)
        best = self.span(origins,b,255,True) or max((s for j in range(len(self.chars)) if (s := self.span(origins,j,255,True))),default=(510,))
        return best[0]//2
    def disabled(self, i): return any(has(self.chars[i],k) for k in (51,52,53,31))
    def weapon(self, i):
        w = rules.worn(self.chars[i])[0]
        return w.data if w is not None else None
    def base(self, item): return rules.tables().base_item(item[I['type']]) if item is not None else bytes(16)
    def ranged(self, i): return self.base(self.weapon(i))[12] > 1
    def throwable(self, i):
        w = self.weapon(i)
        return self.ranged(i) and (self.base(w)[14]&20 == 20 or w[I['type']] == 67)
    def ammo(self, i):
        w, slots = self.weapon(i), rules.worn(self.chars[i])
        if w is None: return False,None
        props = self.base(w)[14]
        raw = w if props&16 else None
        if props&8:
            for flag,slot in ((1,11),(128,12)):
                if props&flag: raw = slots[slot].data if slots[slot] is not None else None
        return raw is not None or props == 10,raw
    def message(self, text, report=True):
        self.data['messages'].append(text)
        if report: self.game.__dict__.setdefault('combat_report', []).append(text)
        self.data['messages'] = self.data['messages'][-6:]

    def show(self, kind, **entry):
        entry.update(kind=kind,actors=tuple((r['x'],r['y'],r['size']) for r in self.data['actors']))
        self.game.__dict__.setdefault('combat_report', []).append(entry)

    def name_colour(self, j):
        c=self.chars[j]
        return 12 if not field(c,'active') else 14 if field(c,'side') else 11

    def show_attack(self, i, j, manner, hit, shown, colour):
        lead={2:'-Backstabs-',3:'slays helpless'}.get(manner,'Attacks')
        text='(from behind) ' if manner==1 else ''
        if hit: text='with one cruel blow' if manner==3 else text+'Hitting for %d point%s of damage'%(shown,'' if shown==1 else 's')
        else: text+='and Misses'
        a,t=self.chars[i],self.chars[j]
        entry=dict(actor=i,attacker=name(a),attacker_colour=self.name_colour(i),lead=lead,target=name(t),target_colour=colour,result=text)
        self.show('attack',**entry)
        if not field(t,'active'):
            status=field(t,'status')
            self.show('attack',down='Dying' if status==5 else 'killed' if status in (6,7,8) else '',**entry)
    def ask(self, kind, options, **info):
        return self.game.ask(kind.value, options, actor=self.data['actor'], round=self.data['round'], **info)
    def end(self, i, guard=False):
        r = self.record(i)
        r.update(initiative=0,movement=0,casting=0,guard=int(guard and not r['turned']))
        if r['guard']: self.message('Guarding')
        return True
    def hp_percent(self):
        total = sum(field(c,'hp_max') for c in self.chars if field(c,'side') == 1)
        if total: self.data['hostile_hp'] = sum(field(c,'hp') for c in self.chars if field(c,'side') == 1 and field(c,'active'))*20//total*5

    def context(self, attacker=None, **values):
        from . import magic
        values.setdefault('spell',self.data.get('current_spell',0))
        for key in ('effect','damage','element','dice_count'): values.setdefault(key,self.data.get('roll',{}).get(key,0))
        def bank(c, raw):
            self.data['bank'].append((self.index(c),raw))
            self.event('disarm',actor=self.index(c),item_type=raw[I['type']])
        def block(c, text):
            r = self.record(self.index(c))
            if r['item_ok']: self.message(name(c)+' '+text)
            r.update(cast_ok=False,item_ok=False)
        return effects.Roll(attacker=attacker,in_combat=True,services={
            'in_aura_range':lambda a,b,r:self.span(self.cells(self.index(a)),self.index(b),r) is not None,
            'distance':lambda a,b:self.distance(self.index(a),self.index(b)),
            'damaging_weapon':lambda c:self.ammo(self.index(c))[1] or self.weapon(self.index(c)),
            'bank_weapon':bank, 'clear_weapon':rules.recalc_stats,
            'unready_item':self.unready,
            'neighbours':lambda c:[self.chars[i] for i in self.targets(self.index(c),1,allies=True) if self.chars[i] is not c],
            'saving_throw':lambda c,k,b:self.save(self.index(c),k,b),
            'clear_target':lambda c:self.record(self.index(c)).update(target=-1),
            'set_turned':lambda c,v:self.record(self.index(c)).update(turned=v),
            'revive':lambda c,h,m:self.revive(self.index(c),h,m),
            'add_with_message':lambda c,k,t,v,m:self.add_with_message(self.index(c),k,t,v,True,m),
            'end_actions':lambda c:self.end(self.index(c)),
            'block_casting':block,
            'message':lambda c,text:self.message(name(c)+' '+text),
            'clear_cloud':lambda c,n:self.clear_cloud(self.index(c),n),
            'caster_level':lambda ident:magic.caster_level(EffectGame(self,'spell level',self.index(attacker)),attacker,ident),
        },**values)

    def unready(self, char, item):
        from .inventory import toggle_ready
        facade = EffectGame(self,'unready effect',self.index(char))
        facade.weapon = item
        toggle_ready(facade,char,item)

    def weapon_effect(self, c, kind, node, removed, context=None, weapon=None):
        i = self.index(c); x = context or self.context(c)
        target = self.record(i)['target']
        if kind == 7:
            w = self.weapon(i) if weapon is None else weapon
            if w is None: raise BindingRequired('Champions Hoopak effect has an undefined native weapon')
            if target<0: target=self.targets(i,allies=True,ignore=True)[-1]
            view,close = rules._view(rules.Character,c.b),self.distance(i,target)<2
            x.damage = (self.damage_dice(1,6 if close else 4,'Hoopak damage',i,target)+(rules._damage_strength(view)+2 if close else 1)+w[I['bonus']])&255; x.dice_count = 1
            put(c,'thac0',field(c,'base_thac0')+(rules._hit_strength(view) if close else rules._dex_missile(view)))
        elif kind == 105:
            if target>=0 and field(self.chars[target],'creature_type')&8: x.damage = (x.damage+field(c,'levels',4))&255
        elif kind == 115:
            if target>=0 and field(self.chars[target],'creature_type')&32: x.damage=(x.damage+3)&255
        elif kind == 26:
            if target>=0 and field(self.chars[target],'creature_type')&128: x.attack+=1
        elif kind in (69,81,88):
            if kind==81: x.damage=0
            if target>=0 and (kind!=88 or field(self.chars[target],'race')>1) and not self.save(target,0): self.add_effect(self.chars[target],52,100,12,'is Paralyzed')
        elif kind in (64,65,86,87):
            if target>=0:
                modifier={64:0,65:4,86:-2,87:1}[kind]
                resistance=effects.has_effect(self.chars[target],116)
                if resistance is not None: modifier=0 if modifier<0 else modifier+resistance[3]
                if not self.save(target,0,modifier):
                    self.add_effect(self.chars[target],55,0,255,'is Poisoned')
                    self.kill(target,6,'is killed')
        elif kind == 70:
            if not field(c,'hp') or not field(c,'active'): self.acid_pool(i)
        elif kind == 80: self.clear_acid(i,node[3])
        elif kind == 100:
            attacker=self.index(x.attacker)
            item=self.ammo(attacker)[1] or self.weapon(attacker)
            if item is not None:
                flags=self.base(item)[7]
                if not flags or flags&1: x.damage >>= 1
        elif kind == 101:
            item=self.weapon(self.index(x.attacker))
            if item is not None and item[I['type']]==54: x.damage=self.damage_dice(1,6,'holy water',self.index(x.attacker),i)+1; x.dice_count=1
        elif kind == 68:
            if not field(c,'active'):
                put(c,'status',10); queue=self.data.setdefault('explosions',[])
                if len(queue)<20: queue.append(i)
                self.remove_effect(i,68)
        elif kind == 60:
            if removed:
                nearby=self.near(i)
                self.kill(i,8,'explodes!')
                for j in nearby:
                    if not field(self.chars[j],'active'): continue
                    self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(3,6,'Aurak explosion',i,j)),0,False)
                    if not self.save(j,4): self.add_effect(self.chars[j],106,0,255,'is stunned')
                self.explode()
        elif kind == 79:
            self.message(name(c)+' emits an evil stench')
            for j in self.near(i):
                t=self.chars[j]
                if field(t,'side')!=field(c,'side') and not self.save(j,4) and not has(t,118):
                    self.message(name(t)+' is affected'); effects.add_effect(c,118,0,255,False)
        elif kind == 103:
            k=self.index(x.attacker) if x.attacker is not None else self.data['actor']
            item=self.ammo(k)[1] or self.weapon(k)
            a=self.chars[k]
            if (item is None or not item[I['bonus']]) and (field(a,'race')<7 or field(a,'highest_level',signed=True)<4): x.damage=0
        elif kind == 93:
            k=self.index(x.attacker) if x.attacker is not None else self.data['actor']
            item=self.ammo(k)[1] or self.weapon(k)
            if item is not None and self.base(item)[7]&0x81: x.damage>>=1
        elif kind == 71:
            from . import magic
            roll=self.die(1,10,'reflect spell',i)
            area=magic.spell(x.spell).area if x.spell else None
            if area is not None and (roll==1 and area<8 or area>14):
                self.message(name(c)+' reflects the spell'); x.reflect=self.data['actor']
        elif kind == 82: self.frighten(i)
        elif kind == 89:
            if self.data['round']==0 and x.attack==0: node[3]&=15
            elif not node[3]&16: x.attack=-1; node[3]|=16
        elif kind == 74:
            if self.die(1,20,'random dispel',i)==1:
                from . import magic
                magic.HANDLERS[41](EffectGame(self,'random dispel',i),c,[c],magic.spell(41))
        elif kind == 76: self.gate_in(i)
        elif kind in (48,66):
            near=self.near(i)
            if kind==48:
                self.message(name(c)+' immolates')
                for j in near:
                    if field(self.chars[j],'active'): self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(1,6,'immolate',i,j)),0,False)
            else:
                j=next((j for j in near if field(self.chars[j],'side')!=field(c,'side')),None)
                if j is not None:
                    self.message(name(self.chars[j])+' gets zapped!')
                    self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(2,6,'zap',i,j)),0,False)
                    self.end(i)
        elif kind == 112:
            k=self.index(x.attacker) if x.attacker is not None else self.data['actor']
            if self.distance(k,i)<2:
                kept=x.damage,x.element
                self.message(name(self.chars[k])+' gets zapped')
                self.spell_damage(self.chars[k],self.context(c,damage=(x.damage*2)&255,element=8),0,False)
                x.damage,x.element=kept
        elif kind in (75,114,117):
            if target>=0:
                t=self.chars[target]
                if kind==75 and field(t,'target_flags')&1:
                    x.damage=(self.die(1,12,'dragon slayer',i,target)*3+4+rules._damage_strength(rules._view(rules.Character,c.b)))&255; x.attack+=2
                elif kind==114 and field(t,'target_flags')&1: x.damage=field(c,'hp')
                elif kind==117 and field(t,'creature_type')&2:
                    if field(t,'undead'): self.kill(target,8,'is disrupted')
                    else: x.damage=(x.damage*2)&255
        elif kind == 3:
            penalty=field(c,'attacks_left',0)+field(c,'attacks_left',1)
            if node[3]>penalty: node[3]-=penalty
            else: self.remove_effect(i,3)
            self.message(name(c)+' is fighting with snakes'); self.end(i)
        elif kind == 35: self.confusion(i)
        else: raise BindingRequired('Champions effect handler not bound: %d %s'%(kind,effects.HANDLER_NAMES.get(kind,'unknown')))
        return x

    def near(self, i):
        return [j for j,*_ in self.spans(self.cells(i),1) if j!=i]

    def explode(self):
        queue=self.data.get('explosions')
        if not queue: return
        self.data['explosions']=[]
        for i in queue:
            c=self.chars[i]; self.message(name(c)+' explodes.')
            self.event('explosion',actor=i)
            for j in self.near(i):
                if field(self.chars[j],'status')!=10:
                    self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(1,6,'explosion',i,j),element=0),0,False)
            put(c,'active',0); put(c,'status',6); self.down(i)

    def add_with_message(self, j, kind, minutes, strength, on_remove, text, saved=False, negates=0):
        c=self.chars[j]; actor=self.data['actor']
        x=self.context(self.chars[actor] if actor>=0 else c,effect=kind); self.trigger(9,j,x)
        if not x.effect or saved and negates==1: self.message(name(c)+' is Unaffected'); return
        node=effects.has_effect(c,kind)
        if node is not None and node[1]|node[2]<<8: effects.remove_effect(EffectGame(self,'replace effect',j),c,kind,node)
        effects.add_effect(c,kind,minutes,strength,on_remove)
        if text: self.message(name(c)+' '+text)

    def flee_control(self, j):
        t=self.chars[j]; put(t,'auto_combat',1)
        if field(t,'npc')<=127: put(t,'npc',0xB3)
        self.record(j).update(target=-1,turned=1)

    def frighten(self, i):
        c=self.chars[i]
        for j,t in enumerate(self.chars):
            if field(t,'side')==field(c,'side') or any(has(t,k) for k in (92,111,119)): continue
            if 0<=field(t,'highest_level',signed=True)<=3:
                self.add_with_message(j,111,0,255,True,'is terrified')
                if has(t,111): self.flee_control(j)
            elif not self.save(j,4): self.add_with_message(j,119,0,255,True,'is afraid')

    def confusion(self, i):
        c=self.chars[i]; roll=self.die(1,100,'confusion',i)
        if roll<=10:
            self.remove_effect(i,35); self.flee_control(i)
            self.add_with_message(i,111,10,0,True,'runs away')
        elif roll<=60:
            self.message(name(c)+' is confused'); self.end(i)
        elif roll<=80:
            self.add_with_message(i,77,1,field(c,'side'),True,'goes berserk')
            node=effects.has_effect(c,77)
            self.berserk(i,77,node)
        else: self.message(name(c)+' is enraged')
        if self.save(i,4,254): self.remove_effect(i,35)

    def berserk(self, i, kind, node):
        c=self.chars[i]; put(c,'auto_combat',1)
        put(c,'npc',0xB3 if field(c,'npc')<=127 or field(c,'npc')==0xB3 else 0xB2)
        r=self.record(i); r['target']=-1
        near=[j for j in self.targets(i,255,allies=True) if j!=i]
        if not near: raise BindingRequired('Champions berserk with no other creature in sight reads an unset target list entry')
        r['target']=near[0]
        if kind==77: r['cast_ok']=False
        put(c,'side',field(self.chars[near[0]],'side')^1)
        if kind==77: self.message(name(c)+' goes berserk')

    def gate_in(self, i):
        c=self.chars[i]
        if field(c,'hp')>=field(c,'hp_max')//2: return
        chars,side=self.chars,field(c,'side')
        t=next((k for k,o in enumerate(chars) if field(o,'side')!=side),None)
        w=next((k for k,o in enumerate(chars) if field(o,'status')==9),None)
        done,d=False,0
        while True:
            if d>7:
                if t is None: t,done=i,True
                else:
                    t=t+1 if t+1<len(chars) else None
                    if t is None or field(chars[t],'side')==side: t,done=i,True
                d=0
            if w is None: done=True
            else:
                x,y=self.position(t); revived=False
                while True:
                    nx,ny=x+DX[d],y+DY[d]
                    if not (0<=nx<=49 and 0<=ny<=24): raise BindingRequired('Champions gate-in direction stalls at the arena edge (the original loops)')
                    if self.occupancy().get((nx,ny)) is None and self.tile(nx,ny)==23:
                        o=chars[w]; self.record(w).update(size=field(o,'dimensions')&7,x=nx,y=ny)
                        revived=self.revive(w,field(o,'hp_max'),'gates in')
                        w=w+1 if w+1<len(chars) else None
                        if w is None or field(chars[w],'status')!=9: done=True
                    d+=1
                    if revived or d>7 or w is None: break
            if done or t==i: break
        self.remove_effect(i,76)

    def monster_breath(self, i, kind, node, context):
        from . import magic
        c=self.chars[i]; facade=EffectGame(self,'breath %d'%kind,i)
        if kind==78:
            self.data['multi_target']=1
            targets=self.spell_targets(i,magic.spell(47),ai=True)
            if targets is None: return
            self.data['current_spell']=47
            self.message(name(c)+' throws a fireball'); self.event('breath',actor=i,kind=kind,targets=tuple(targets),charges=0)
            amount=self.damage_dice(15,6,'thrown fireball',i)
            magic._resolve(facade,c,[self.chars[j] for j in targets],magic.spell(47),0,False,'',amount,9)
            self.remove_effect(i,78); return
        if not self.data['round']: node[3]=3
        if kind==4:
            mask=self.data.get('roll',{}).get('element',0)
            if self.die(1,100,'energy bolt chance',i)>75: return
            if node[3] and self.die(1,100,'blinding breath chance',i)<=25:
                victim=None
                for j in self.area_targets(*self.position(i),1):
                    if j!=i and field(self.chars[j],'side')!=field(c,'side'): victim=j
                if victim is not None:
                    self.message(name(c)+' Breathes!'); self.event('breath',actor=i,kind=kind,targets=(victim,),charges=node[3])
                    t=self.chars[victim]
                    if self.save(victim,3,element=mask): self.spell_damage(t,self.context(c,damage=10),0,True)
                    else:
                        self.spell_damage(t,self.context(c,damage=20),0,False)
                        self.add_with_message(victim,33,0,0,False,'is blinded'); self.end(i)
                    node[3]-=1; return
            fired,n=False,0
            while n<2:
                targets=self.spell_targets(i,magic.spell(61),ai=True)
                if not targets: break
                n+=1; j=targets[0]; fired=True
                self.message(name(c)+' Fires An Energy Bolt!'); self.event('energy bolt',actor=i,target=j)
                self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(1,8,'energy bolt',i,j)+2),0,False)
                if field(self.chars[j],'active') and n==1:
                    self.spell_damage(self.chars[j],self.context(c,damage=self.damage_dice(1,8,'energy bolt',i,j)+2),0,False); n+=1
            if fired: self.end(i)
            return
        if not node[3]: return
        if kind==84:
            if self.spell_targets(i,magic.spell(36),ai=True) is None: return
            targets=self.cone(i,self.data['aim'],255,3)
            if not targets: return
            context.element=0x20; self.remember_roll(context)
            self.message(name(c)+' breathes poison')
            self.record(i)['facing']=self.direction(i,targets[0])
            self.event('breath',actor=i,kind=kind,targets=tuple(targets),charges=node[3])
            for j in targets:
                saved=self.save(j,3,element=0x20)
                self.spell_damage(self.chars[j],self.context(c,damage=field(c,'hp_max'),element=0x20),2,saved)
        else:
            context.element=0x24; self.remember_roll(context)
            if self.spell_targets(i,magic.spell(51),ai=True) is None: return
            self.message(name(c)+' Breathes!')
            self.event('breath',actor=i,kind=kind,targets=(),charges=node[3])
            if self.data['aim']!=self.position(i): self.record(i)['facing']=direction_to(*self.position(i),*self.data['aim'])
            self.lightning(facade,c,magic.spell(51),field(c,'hp_max'),length=10,save=3,element=0x24,bounce=False)
        node[3]-=1; self.end(i)

    def trigger(self, condition, i, context=None):
        c, x = self.chars[i], context or self.context(self.chars[i])
        if condition in (6,9): effects.check_spell_resistance(EffectGame(self,'magic resistance',i),c,x)
        for kind in effects.CONDITIONS.get(condition,()):
            node = effects.has_effect(c,kind)
            if node is None and kind in effects.AURA_IDS: node = effects.aura_node(self.game,c,kind,x)
            if node is None: continue
            if kind in (6,83,90,104): self.dragon_breath(i,node,x)
            elif kind in (4,78,84,85): self.monster_breath(i,kind,node,x)
            elif kind in (7,105): self.weapon_effect(c,kind,node,False,x)
            else:
                side = field(c,'side')
                effects.call_handler(EffectGame(self,'effect %d'%kind,self.index(x.attacker) if x.attacker is not None else i,i),c,kind,node,False,x)
                if kind == 11 and field(c,'side') != side: self.count_teams()
        self.remember_roll(x)
        return x

    def remember_roll(self, context):
        self.data['roll'] = {key:getattr(context,key) for key in ('effect','damage','element')}|{'dice_count':self.data.get('roll',{}).get('dice_count',0)}

    def add_effect(self, c, kind, minutes, strength, message):
        effects.add_effect(c,kind,minutes,strength,False); self.message(name(c)+' '+message)
    def revive(self, i, hp, message):
        c,r = self.chars[i],self.record(i)
        r['size']=field(c,'dimensions')&127
        occupant,tile=self.probe(i)
        if occupant>=0 or not tile or self.terrain(tile)==255:
            r['size']=0
            return False
        if not r['outsider']:
            downed,who = self.data.setdefault('downed',[]),self.data.setdefault('downed_who',[])
            for k,j in enumerate(who):
                if j == i:
                    if downed[k][2] != 31: tile = downed[k][2]
                    downed[k],who[k] = (0,0,0),-1
            if not any(j >= 0 and (downed[k][0],downed[k][1]) == (r['x'],r['y']) for k,j in enumerate(who)): self.put_tile(r['x'],r['y'],tile)
        put(c,'hp',hp); put(c,'status',0); put(c,'active',1); self.center(i,3)
        self.count_teams()
        self.message(name(c)+' '+message); return True
    def remove_effect(self, i, kind):
        effects.remove_effect(EffectGame(self,'remove effect %d'%kind,i),self.chars[i],kind)
    def strip(self, i):
        for k in effects._hp_zero_ids(self.game): self.remove_effect(i,k)
        c = self.chars[i]
        if has(c,77) and field(c,'npc') == 179: put(c,'side',0)
    def save(self, i, kind, bonus=0, element=0):
        c = self.chars[i]; value = self.die(1,20,'saving throw',i)
        if value in (1,20): return value == 20
        if field(c,'levels',5,signed=True)>0 and field(c,'robe_order'):
            moon = self.s.r0[(field(c,'robe_order')+0x1F8)&255]
            bonus += -1 if moon == 0 else 1 if moon == 2 else 0
        actor = self.data['actor']
        x = self.context(self.chars[actor] if actor>=0 else c,save=(value+field(c,'save_bonus',signed=True)+signed(bonus))&255,save_type=kind,element=element)
        self.trigger(12,i,x)
        return field(c,'saves',kind) <= x.save

    def span(self, origins, j, reach=255, ignore=False):
        best = None
        for tx,ty in self.cells(j):
            for x,y in origins:
                points = list(line(x,y,tx,ty)); distance = points[-1][2]
                if distance > 2*reach+1: continue
                height = self.terrain(self.tile(x,y),1)
                if not ignore and any(self.terrain(self.tile(px,py),2)>height for px,py,_ in points): continue
                if best is None or distance < best[0]: best = distance,next((d for d in range(8) if in_cone(x,y,tx,ty,d)),8)
        return best
    def spans(self, origins, reach=255, ignore=False):
        entries = [(j,*best) for j in range(len(self.chars)) if (best := self.span(origins,j,reach,ignore))]
        for a in range(len(entries)-1):
            for b in range(a+1,len(entries)):
                if entries[b][1] < entries[a][1] or entries[b][1] == entries[a][1] and entries[b][2] < entries[a][2] and entries[b][2]%2 <= entries[a][2]%2:
                    entries[a],entries[b] = entries[b],entries[a]
        return entries
    def targets(self, i, reach=255, allies=False, ignore=False):
        entries = self.spans(self.cells(i),reach,ignore)
        result = [j for j,*_ in entries if field(self.chars[j],'active') and (allies or field(self.chars[j],'side') != field(self.chars[i],'side'))]
        if not allies and has(self.chars[i],91) and self.data['yell'] in result:
            p = result.index(self.data['yell']); result[0],result[p] = result[p],result[0]
        return result
    def anchor_reach(self, i, j, reach):
        x,y = self.position(i); points = list(line(x,y,*self.position(j)))
        height = self.terrain(self.tile(x,y),1)
        return points[-1][2] <= 2*reach+1 and all(self.terrain(self.tile(px,py),2) <= height for px,py,_ in points)
    def can_target(self, i, j):
        if i == j: return True
        x = self.context(self.chars[i]); self.trigger(1,j,x); self.trigger(0,i,x)
        return not x.target_veto
    def attack_targets(self, i):
        if not field(self.chars[i],'active') or not any(field(self.chars[i],'attacks_left',p) for p in (0,1)): return []
        ranged, usable = self.ranged(i),self.ammo(i)[0]
        reach = max(1,(self.base(self.weapon(i))[12]-1)&255) if ranged else 1
        near = self.targets(i,1)
        return [j for j in self.targets(i,reach,allies=True) if j != i and self.can_target(i,j) and
                (not ranged or usable and (not near or self.throwable(i)))]
    def acquire(self, i, relaxed=False, reach=255, force=False):
        r = self.record(i); j = r['target']
        if not force and j >= 0 and field(self.chars[j],'active') and field(self.chars[j],'side') != field(self.chars[i],'side') and self.can_target(i,j): return True
        r['target'] = -1
        for ignore in (False,True):
            candidates = self.targets(i,reach,ignore=ignore and not force)
            for attempt in range(20):
                if not any(j >= 0 for j in candidates): break
                k = 0 if not attempt and has(self.chars[i],91) and candidates[0] == self.data['yell'] else self.die(1,len(candidates),'acquire target',i)-1
                j = candidates[k]
                if j >= 0 and (relaxed and ignore and not force or self.can_target(i,j)):
                    r['target'] = j; return True
                candidates[k] = -1
        return False

    def rate(self, i, value): return self.trigger(18,i,self.context(self.chars[i],multiplier=value)).multiplier&255
    def movement(self, i):
        c = self.chars[i]; value = (field(c,'move')+(self.s.r1[0x372] if field(c,'side') == 0 else 0))&255
        return self.rate(i,2*(value if 1 <= value <= 96 else 1))
    def reset_attacks(self, i):
        c,r = self.chars[i],self.record(i); available,ammo = self.ammo(i)
        ranged = self.ranged(i) and available
        rate = max(2,self.base(self.weapon(i))[5]) if ranged else field(c,'attacks')
        count = ((self.rate(i,rate)+(self.data['round']&1))&255)//2
        if ranged and ammo is not None and ammo[I['quantity']]: count = min(count,max(1,ammo[I['quantity']]))
        put(c,'attacks_left',min(count,field(c,'attacks_left')) if r['attacked'] else count)
    def begin_round(self):
        order = []
        self.count_teams()
        for i,c in enumerate(self.chars):
            r = self.record(i); r.update(attacked=0,phase=1,sweep=field(c,'attack_level'),casting=0,
                                         cast_ok=not any(self.tile(x,y)==30 for x,y in self.cells(i)),item_ok=True)
            self.reset_attacks(i)
            put(c,'attacks_left',((self.rate(i,field(c,'second_attacks'))+(self.data['round']&1))&255)//2,1)
            initiative = 0
            if field(c,'active'):
                initiative = max(1,self.die(1,6,'initiative',i)+rules._dex_missile(rules._view(rules.Character,c.b)))
                if self.s.r1[0x2CB]&(field(c,'side')+1): initiative -= 6
                if not 0 <= initiative <= 20: initiative = 0
            r.update(initiative=initiative,movement=self.movement(i))
        self.s.r1[0x2CB] = 0
        for i in range(len(self.chars)):
            p = 0
            while p < len(order):
                a,b = self.record(i)['initiative'],self.record(order[p])['initiative']
                if a>b or a == b and self.die(1,2,'initiative tie',i,order[p]) == 1: break
                p += 1
            order.insert(p,i)
        self.data.update(order=order,cursor=0)
        self.event('initiative',order=tuple(order),values=tuple(r['initiative'] for r in self.data['actors']))

    def body(self, i):
        r = self.record(i); x,y = r['x'],r['y']
        self.data.setdefault('downed',[]).append((x,y,self.tile(x,y)))
        self.data.setdefault('downed_who',[]).append(i)
        if self.tile(x,y) != 30: self.put_tile(x,y,31)
    def down(self, i):
        c,r = self.chars[i],self.record(i)
        if field(c,'status') == 3:
            if self.drawing(): self.center(i,3)
        else:
            if not self.visible(i,True): self.center(i,3)
            if not r['outsider']: self.body(i)
        r['size'] = 0; self.end(i)

    def kill(self, i, status, message):
        c=self.chars[i]; self.message(name(c)+' '+message)
        if field(c,'status') in (6,7,8): return
        if field(c,'active'): self.ghost(i)
        put(c,'status',status); put(c,'active',0); put(c,'hp',0)
        self.strip(i); self.trigger(13,i)
        if not field(c,'active') and field(c,'status') != 10: self.down(i)
    def damage(self, i, amount, x, spell=False):
        c,r = self.chars[i],self.record(i)
        if not field(c,'active'): return
        x.damage=amount; self.remember_roll(x)
        if amount:
            r['cast_ok'] = False
            if r.get('casting'):
                from .magic import forget
                self.event('spell interrupted',actor=i,spell=r['casting'])
                forget(c,r['casting']); self.message(name(c)+' lost a spell'); self.end(i)
        hp = field(c,'hp'); remaining,overkill = max(0,hp-amount),max(0,amount-hp)
        status = 6 if overkill>9 or not remaining and field(c,'status') == 1 else 5 if overkill else 4 if not remaining else field(c,'status')
        put(c,'status',status); put(c,'hp',remaining if status in (0,1) else 0)
        if status not in (0,1):
            put(c,'active',0); r['initiative'] = 0
            if status == 5: r['overkill'] = overkill
            if spell: self.message(name(c)+(' is killed' if status in (6,7,8) else ' Goes Down, and is Dying' if status == 5 else ' Goes Down'))
            self.strip(i); self.trigger(13,i,x)
            if not field(c,'active') and field(c,'status') != 10: self.down(i)
        self.event('damage',actor=self.index(x.attacker),target=i,amount=amount,hp=field(c,'hp'),status=field(c,'status'))
    def note_direction(self, i, j):
        r = self.record(j); d = (self.direction(j,i)-r['facing'])%8
        r['flanks'] += 1; r['spread'] = (r['spread']+min(d,8-d))%8
    def backstab(self, i, j):
        a,t = self.chars[i],self.chars[j]; w = self.weapon(i)
        allowed = w is None or w[I['type']] in (3,4,17,18,19,67)
        return (allowed and (field(a,'levels',6) or earlier_class(a) and field(a,'former_levels',6)) and
                self.record(j)['flanks']>1 and self.distance(i,j)<2 and field(t,'dimensions')&127 <= 1 and
                self.direction(i,j) == self.record(j)['facing'])
    def strike(self, i, j, missile=None):
        if self.sweep(i,j): return self.end(i)
        self.note_direction(i,j)
        return self.attack(i,j,missile=missile)
    def sweep(self, i, j):
        c,r = self.chars[i],self.record(i)
        if field(c,'attacks_left')<r['sweep'] and not field(self.chars[j],'highest_level') and self.distance(i,j) == 1:
            targets = self.targets(i,1)
            count = sum(not field(self.chars[k],'highest_level') for k in targets)
            if count>field(c,'attacks_left'):
                self.message(name(c)+' sweeps')
                if targets[0] != j:
                    at = targets.index(j); targets[0],targets[at] = targets[at],targets[0]
                left = min(count,r['sweep'])
                for k in targets:
                    if left and not field(self.chars[k],'highest_level'):
                        self.note_direction(i,k); put(c,'attacks_left',1)
                        self.attack(i,k); left -= 1
                return True
        return False

    def confirm_ally(self, i, j):
        if field(self.chars[i],'side')!=field(self.chars[j],'side') or field(self.chars[i],'auto_combat'): return True
        if self.ask(Kind.CONFIRM,['Yes','No'],prompt='Attack Ally: ',target=j,start=1)!=0: return False
        self.s.g['cok.ally_attacked']=1; self.s.r1[0x333]=1
        for k,c in enumerate(self.chars):
            if field(c,'status')==0 and field(c,'npc')>127 and field(c,'npc')!=0xB3:
                put(c,'side',1); self.record(k)['target']=-1
        self.count_teams()
        return True

    def move_attack(self, i, j):
        if self.ranged(i) and not self.throwable(i):
            self.message('Not with that weapon'); return False
        if not self.confirm_ally(i,j): return False
        self.record(i)['target']=j
        return self.strike(i,j)

    def attack(self, i, j, behind=False, missile=None):
        a,t,r,tr = self.chars[i],self.chars[j],self.record(i),self.record(j)
        if not field(a,'active') or not field(t,'active'): return self.end(i)
        self.data['limit'] = self.data['round']+15
        self.data['gfx'] = True
        seen = self.visible(j)
        if tr['flanks'] < 2 and not behind: tr['facing'] = (self.direction(j,i)+(0 if seen else 4))%8
        if seen: self.face(j,tr['facing'])
        self.face(i,self.direction(i,j)); r['target'] = j
        if not any(field(a,'attacks_left',p) for p in (0,1)): return self.end(i)
        r['attacked'] = 1
        self.data.setdefault('roll',{})['damage']=0
        made = [0,0]; x = self.context(a)
        if self.disabled(j):
            phase = next(p for p in range(r['phase'],-1,-1) if field(a,'attacks_left',p))
            r['phase'] = phase; made[phase] += 1
            colour=self.name_colour(j); self.damage(j,(field(t,'hp')+5)&255,x)
            self.show_attack(i,j,3,True,0,colour)
            while has(a,25): self.remove_effect(i,25)
            put(a,'attacks_left',0); put(a,'attacks_left',0,1)
        else:
            w = self.weapon(i)
            if w is not None and (field(t,'dimensions')>128 or field(t,'dimensions')&7>1):
                base = self.base(w)
                put(a,'damage_rolls',base[2]); put(a,'damage_dice',base[3])
                put(a,'damage_bonus',field(a,'damage_bonus')-base[11]+base[4])
            rules.recalc_stats(t); self.trigger(11,j,x)
            back = self.backstab(i,j)
            rear = behind or tr['flanks']>1 and r['facing'] == tr['facing'] and tr['spread']>4
            ac = field(t,'ac',1)-4 if back else field(t,'ac',int(rear))
            distance = self.distance(i,j); band = (self.base(w)[12]-1)//3 if self.ranged(i) else distance
            ac = (ac+(2 if distance>band else 0)+(3 if distance>2*band else 0))&255
            any_hit = False
            for p in range(r['phase'],-1,-1):
                while field(a,'attacks_left',p) and field(t,'active'):
                    put(a,'attacks_left',field(a,'attacks_left',p)-1,p); r['phase'] = p; made[p] += 1
                    while has(a,25): self.remove_effect(i,25)
                    natural = self.die(1,20,'attack',i,j); x = self.context(a,attack=100 if natural == 20 else natural)
                    if natural != 1: self.trigger(10,i,x); self.trigger(16,j,x)
                    modifier = signed(self.s.r1[0x371 if field(a,'side') == 0 else 0x370]&255)
                    hit = natural != 1 and x.attack>=0 and x.attack+field(a,'thac0')+modifier >= ac or self.disabled(j)
                    self.event('attack',actor=i,target=j,phase=p,natural=natural,roll=x.attack,thac0=field(a,'thac0'),modifier=modifier,defense=ac,hit=hit)
                    if hit:
                        x.dice_count = field(a,'damage_rolls',p)
                        x.damage = (self.damage_dice(x.dice_count,field(a,'damage_dice',p),'damage',i,j)+field(a,'damage_bonus',p,signed=True))&255
                        self.trigger(4,i,x); self.trigger(5,j,x)
                        if back: x.damage *= (((field(a,'levels',6)+field(a,'former_levels',6)*earlier_class(a)-1)&65535)//4+2)
                        x.damage &= 255; x.element = 0
                        self.remember_roll(x)
                        colour=self.name_colour(j)
                        self.message('%s hits %s for %d'%(name(a),name(t),x.damage),False); self.damage(j,x.damage,x)
                        self.show_attack(i,j,2 if back else 1 if rear else 0,True,x.damage,colour)
                        if field(t,'active') and x.damage: self.trigger(p+2,i,x)
                        any_hit = True
                        if not field(a,'active'): put(a,'attacks_left',0,p)
                    self.explode()
            if not any_hit:
                self.message(name(a)+' misses '+name(t),False)
                self.show_attack(i,j,2 if back else 1 if rear else 0,False,0,self.name_colour(j))
            r['sweep'] = 0
        if missile is not None and (self.weapon(i) is None or self.weapon(i)[I['type']] != 67):
            if missile[I['quantity']]: missile[I['quantity']] = (missile[I['quantity']]-made[0])&255
            if not missile[I['quantity']]:
                if self.throwable(i) and missile[I['powers']+1] != 23:
                    raw = bytearray(missile); raw[I['readied']] = 0
                    boundary = self.data['treasure_boundary']
                    at = len(self.s.treasure_items) if boundary is None else boundary+1
                    self.s.treasure_items.insert(at,raw); self.data['treasure_boundary'] = at
                a.items = [raw for raw in a.items if raw is not missile]
        rules.recalc_stats(a)
        done = not field(a,'active') or not any(field(a,'attacks_left',p) for p in (0,1))
        if self.visible(i): self.face(i,r['facing'])
        return self.end(i) if done else False


    def opportunity(self, i, direction):
        r = self.record(i)
        candidates = [j for j in self.targets(i,1) if not self.disabled(j) and not self.record(j)['turned']]
        r['x'] += DX[direction]; r['y'] += DY[direction]
        after = self.targets(i,1)
        r['x'] -= DX[direction]; r['y'] -= DY[direction]
        for j in candidates:
            if j in after or not field(self.chars[i],'active'): continue
            a,ar = self.chars[j],self.record(j)
            if not self.can_target(j,i) or self.ranged(j) and not self.throwable(j): continue
            facing = any(in_cone(*self.position(j),*self.position(i),d%8) for d in range(ar['facing']+6,ar['facing']+11))
            if ar['initiative']>0 or not ar['flanks'] or facing:
                p = next((p for p in (1,0) if field(a,'attacks_left',p)),0 if field(a,'attacks') else 1)
                if not field(a,'attacks_left',p): put(a,'attacks_left',1,p)
                ar['phase'],old = p,ar['target']
                self.attack(j,i,behind=True); ar['target'] = old

    def move(self, i, direction):
        c,r = self.chars[i],self.record(i); occupant,tile = self.probe(i,direction)
        cost = self.terrain(tile)*(3 if direction%2 else 2)
        if not tile or occupant >= 0 or self.terrain(tile) == 255 or cost>r['movement']: return False
        r['facing'] = direction; self.opportunity(i,direction)
        if not field(c,'active'): return False
        if r['movement']:
            x,y = r['x']+DX[direction],r['y']+DY[direction]
            debit = self.terrain(self.tile(x,y))*(3 if direction%2 else 2)
            r.update(x=x,y=y,movement=max(0,r['movement']-debit),flanks=0,spread=0)
            if self.drawing():
                if field(c,'auto_combat') and not self.in_view(x,y): self.scroll(x-DX[direction],y-DY[direction],2)
                self.center(i,3 if field(c,'auto_combat') else 1)
            self.event('move',actor=i,x=x,y=y,cost=debit,left=r['movement']); self.show('move',actor=i,left=(r['movement']+debit)//2 if field(c,'auto_combat') else None)
            for j in self.targets(i,1):
                if field(c,'active') and self.record(j)['guard'] and not self.disabled(j):
                    self.center(i,2)
                    self.record(j)['guard'] = 0; self.note_direction(j,i); self.attack(j,i)
            self.terrain_effects(i)
        if not field(c,'active') or self.disabled(i): self.end(i)
        return True

    def flee(self, i):
        enemies = self.targets(i); own = self.movement(i)//2
        speed = max((self.movement(j)//2 for j,c in enumerate(self.chars) if field(c,'active') and field(c,'side') != field(self.chars[i],'side')),default=0)
        success = not enemies or own>speed or own == speed and self.die(1,2,'escape',i) == 1
        if success:
            self.ghost(i); put(self.chars[i],'status',3); put(self.chars[i],'active',0); self.strip(i); self.down(i)
        self.message(name(self.chars[i])+' Got Away' if success else 'Escape is blocked')
        self.event('flee',actor=i,own=own,enemy=speed,escaped=success)
        return self.end(i)

    def morale(self, i):
        c,r = self.chars[i],self.record(i); r['fleeing'] = int(bool(r['turned']))
        if r['turned']: self.message(name(c)+' is forced to flee'); return False
        if field(c,'npc')<=127: return False
        value = (field(c,'npc')&127)*2
        if value>102: value = 0
        own = self.trigger(17,i,self.context(c,morale=value)).morale
        loss = 100-field(c,'hp')*100//field(c,'hp_max')
        group = None
        holds = bool(own and own>=loss)
        self.data['morale'] = own
        if not holds:
            group = self.trigger(17,i,self.context(c,morale=self.data['hostile_hp'])).morale
            self.data['morale'] = group
            holds = bool(group and group>=100-self.s.r1[0x2C6] and field(c,'side'))
        self.event('morale',actor=i,own=own,loss=loss,group=group,threshold=100-self.s.r1[0x2C6],holds=holds)
        if holds: return False
        speed = max((self.movement(j)//2 for j,other in enumerate(self.chars) if field(other,'active') and field(other,'side') != field(c,'side')),default=0)
        if speed <= self.movement(i)//2:
            r['fleeing'] = 1
            for k in (74,75): self.remove_effect(i,k)
        elif field(c,'abilities',3)>5:
            if self.drawing(): self.center(i,3)
            self.message(name(c)+' Surrenders')
            self.ghost(i); put(c,'active',0); put(c,'status',4); put(c,'hp',0); r['size'] = 0; self.end(i); self.strip(i)
            self.event('surrender',actor=i); return True
        return False

    def finish_ai(self, i): return self.end(i,not self.disabled(i) and not self.ranged(i) and self.record(i)['initiative']>0)

    def equip(self, i):
        from .inventory import toggle_ready
        c = self.chars[i]; slots = rules.worn(c)
        raw = lambda slot: slot.data if slot is not None else None
        old,shield = raw(slots[0]),raw(slots[1])
        put(c,'hands_used',field(c,'hands_used')-sum(self.base(it)[1] for it in (old,shield) if it is not None))
        best,melee,best_shield = None,None,None
        bs,ms,ss = 1,(field(c,'unarmed_dice')*field(c,'unarmed_rolls')+max(0,field(c,'unarmed_bonus',signed=True))*2)&255,0
        for item in c.items:
            base = self.base(item)
            if not base[13]&field(c,'class_mask'): continue
            if base[0] == 0:
                score = base[9]*base[10]+max(0,signed(item[I['bonus']]))*8+max(0,signed(base[11]))*2
                target = self.record(i)['target']
                if item[I['type']] == 54 and target>=0 and field(self.chars[target],'undead')>0: score = 8
                if base[14]&8: score += (base[5]-1)*2
                if base[1]<=1: score += 3
                if base[1]+field(c,'hands_used')>3 or item[I['cursed']] or item[I['powers']+1] == 83 or item[I['powers']+2] == 132 and item[I['powers']+1]&15 != field(c,'alignment'): score = 0
                score &= 255
                if base[14]&24 and score>bs: best,bs = item,score
                if not base[14]&8 and score>ms: melee,ms = item,score
            elif base[0] == 1:
                score = signed(item[I['bonus']])+1 if signed(item[I['bonus']])>=0 else 0
                if score>ss: best_shield,ss = item,score
        choice = melee
        if best is not None:
            base = self.base(best); props = base[14]; ammo = best if props&16 else None
            if props&8:
                if props&1: ammo = slots[11]
                if props&128: ammo = slots[12]
            if bs>ms//2 and (ammo is not None or props == 10) and (base[12]>1 and props&20 == 20 or not self.targets(i,1)): choice = best
        def toggle(item):
            if item is not None:
                facade = EffectGame(self,'AI equipment effect',i); facade.weapon = self.weapon(i)
                toggle_ready(facade,c,item)
        if old is not choice and (old is None or not old[I['cursed']]):
            toggle(old); rules.recalc_stats(c)
            shield = raw(rules.worn(c)[1])
            if shield is not None and not shield[I['cursed']]: put(c,'hands_used',field(c,'hands_used')-self.base(shield)[1])
            toggle(choice)
        rules.recalc_stats(c); self.reset_attacks(i); shield = raw(rules.worn(c)[1])
        if field(c,'hands_used')>2: toggle(shield if shield is not None and not shield[I['cursed']] else choice)
        elif field(c,'hands_used')<2 and (shield is None or shield is not best_shield and not shield[I['cursed']]):
            toggle(shield); rules.recalc_stats(c); toggle(best_shield)
        rules.recalc_stats(c)
    def ai_step(self, i):
        c,r = self.chars[i],self.record(i)
        if r['movement']//2 == 0 or r['initiative']<=0: return self.finish_ai(i)
        npc,side = field(c,'npc'),field(c,'side')
        allowed = npc<128 or npc>127 and self.data['hostile_hp']<=self.die(1,100,'AI advance morale',i)+self.data.get('morale',0) or side == 1
        if not allowed or not (r['fleeing'] or rules.worn(c)[2] is not None or field(c,'class') != 5): return self.finish_ai(i)
        if r['fleeing']:
            r['stance'] = self.die(1,2,'flee pattern',i)
            direction = (self.s.dir-((self.s.dir+2)%4)//2+4*(side == 0))%8
        elif r['target']<0: return self.finish_ai(i)
        else: direction = self.direction(i,r['target'])
        chosen = None
        for attempt in range(5):
            d = (direction+self.t['ai'][(r['stance']-1)*5+attempt])%8
            occupant,tile = self.probe(i,d)
            if not tile and r['fleeing']: r['fleeing'] = 0; return self.flee(i)
            if tile and occupant<0 and self.terrain(tile)<255 and self.terrain(tile)*(3 if d%2 else 2)<r['movement']:
                ahead = [self.tile(x+DX[d],y+DY[d]) for x,y in self.cells(i)]
                if 30 in ahead and not any(has(c,k) for k in (32,30,99,63)) and not r['turned'] and not self.save(i,0): continue
                if 29 in ahead and field(c,'highest_level')<7 and not has(c,99) and not r['turned']: continue
                chosen = d; break
        if chosen is None or self.data['last_direction'] == (chosen+4)%8:
            self.data['stuck'] += 1; r['stance'] = r['stance']%6+1
            if self.data['stuck']>1:
                r['target'] = -1
                if self.data['stuck']>2: r['movement'] = 0; return False
                if not self.acquire(i,True): return self.finish_ai(i)
        if chosen is not None:
            self.data['last_direction'] = chosen
            self.data['gfx'] = bool(self.data.get('in_range')) or self.shown(i); self.face(i,chosen)
            self.move(i,chosen)
        return False

    def ai(self, i):
        c,r = self.chars[i],self.record(i)
        stopped=False
        if field(c,'npc')<128 and field(c,'status')!=1:
            key=self.ask(Kind.AUTO,['Continue','Manual','Magic'],prompt='Space: manual. Magic: toggle spell casting.',magic=int(self.data.get('magic_enabled',False)))
            if key==2: self.toggle_magic()
            if key==1:
                for member in self.s.party:
                    if field(member,'npc')<128 and field(member,'status')!=1: put(member,'auto_combat',0)
                r['initiative']=20; stopped=True
        if not field(c,'active'): self.end(i); stopped=True
        if not 1 <= r['stance'] <= 4 or self.die(1,4,'retain AI pattern',i) == 1:
            r['stance'] = self.die(1,2,'AI sweep pattern',i)+4 if self.die(1,8,'AI pattern class',i) == 8 else self.die(1,4,'AI approach pattern',i)
        if not stopped: stopped = self.morale(i)
        if r['fleeing'] and not r['turned']: self.message(name(c)+' flees in panic')
        if stopped: return
        if self.ai_item(i): return self.end(i)
        if r['casting']:
            self.cast(i,r['casting'],ai=True); return self.end(i)
        undead = [j for j in self.targets(i) if 0<field(self.chars[j],'undead')<=13 and not self.record(j)['turned']]
        if (field(c,'levels',0) or field(c,'former_levels',0)>field(c,'dual_threshold')) and r['turns']<self.s.g.get('cok.undead_count',0) and undead:
            return self.turn_undead(i)
        if self.ai_spell(i): return
        self.equip(i)
        for _ in range(128):
            if not self.acquire(i,True) or r['initiative']<=0 or not field(c,'active'): return self.finish_ai(i)
            self.data.update(last_direction=8,stuck=0)
            self.trigger(14,i)
            if field(c,'side') == 0 and self.bandage(): return self.end(i)
            for iteration in range(21):
                while r['fleeing'] and r['movement']>0 and 0<r['initiative']<20: self.ai_step(i)
                if r['initiative'] in (0,20): return
                last = iteration == 20
                if last: self.finish_ai(i)
                self.data.pop('in_range',None)
                reach = (self.base(self.weapon(i))[12]-1)&255
                if reach in (0,255): reach = 1
                j = r['target']
                locked = j>=0 and field(self.chars[j],'active') and field(self.chars[j],'side') != 0 and self.can_target(i,j) and self.anchor_reach(i,j,reach)
                if not locked:
                    nearby = self.targets(i,reach)
                    if not nearby:
                        if self.acquire(i): self.ai_step(i)
                        else: return self.finish_ai(i)
                        if last: return
                        continue
                    j = nearby[self.die(1,len(nearby),'AI attack target',i)-1]
                    if self.ranged(i) and not self.throwable(i) and self.targets(i,1):
                        self.equip(i)
                        if last: return
                        break
                    if self.distance(i,j) != 1 and not self.can_target(i,j):
                        if last: return
                        continue
                missile = self.ammo(i)[1] if self.ranged(i) and not (self.throwable(i) and self.distance(i,j) == 1) else None
                self.data['in_range'] = True
                d = self.direction(i,j); self.scroll(r['x']+DX[d],r['y']+DY[d],2)
                if self.sweep(i,j): self.end(i); return
                if self.ranged(i) and not self.ammo(i)[0]: self.data.pop('in_range',None)
                self.note_direction(i,j)
                if self.attack(i,j,missile=missile) or last: return
                if not field(self.chars[j],'active'): break
        raise BindingRequired('Champions AI failed to finish a native turn')

    def cure_target(self, i):
        best,down,hp = None,None,255
        occupied = self.occupancy(); x,y=self.position(i)
        for direction in range(9):
            cell=x+DX[direction],y+DY[direction]; j=occupied.get(cell)
            if j is not None:
                c=self.chars[j]; current=field(c,'hp')
                if field(c,'side')==field(self.chars[i],'side') and current<field(c,'hp_max') and (current<hp or j==i and current<field(c,'hp_max')//2): best,hp=j,current
            elif self.tile(*cell)==31:
                for j,c in enumerate(self.s.party):
                    if self.position(j)==cell and field(c,'status') not in (6,7,8): down=j
        return best if hp<8 or down is None else down

    def ai_accept_spell(self, i, ident, priority):
        from . import magic
        row=magic.spell(ident)
        if row.ai_priority<priority: return False
        if not row.offensive and ident!=3 or ident==3 and self.cure_target(i) is not None: return True
        reach=(row.range_base+row.range_per_level*magic.caster_level(EffectGame(self,'AI range',i),self.chars[i],ident))&255
        if reach==255 or not reach and row.area: reach=1
        candidates=self.targets(i,reach)
        if not candidates: return False
        for j in candidates if row.ai_radius else ():
            unsafe=False
            for k in self.area_targets(*self.position(j),row.ai_radius):
                if field(self.chars[k],'side')==field(self.chars[i],'side') and row.save_effect!=1 and not self.save(k,row.save_type,-2 if field(self.chars[i],'side')==0 else 8): unsafe=True
            if unsafe: return False
        return True

    def ai_spell(self, i):
        c,r=self.chars[i],self.record(i)
        candidates=[field(c,'memorized',k) for k in range(1,58) if field(c,'memorized',k)] if r['cast_ok'] else []
        bands=self.die(1,7,'AI spell priority bands',i)
        if not candidates or field(c,'npc')<=127 and not self.data.get('magic_enabled',False) or not self.team(1-field(c,'side')): return False
        for priority in range(7,7-bands,-1):
            for _ in range(3):
                ident=candidates[self.die(1,len(candidates),'AI spell candidate',i)-1]
                if self.ai_accept_spell(i,ident,priority): return self.begin_cast(i,ident,True)
        return False

    def ai_item(self, i):
        from . import inventory
        c,r=self.chars[i],self.record(i); bands=self.die(1,7,'AI item priority bands',i)
        if not r['item_ok'] or not self.team(1-field(c,'side')) or self.s.r0[0xE5]: return False
        for priority in range(7,7-bands,-1):
            for item in c.items:
                ident=item[I['powers']+1]
                if not item[I['readied']] or item[I['powers']+2]>=128 or not ident or item[I['type']] in (39,40): continue
                ident=ident-23 if ident>56 else ident
                if self.ai_accept_spell(i,ident,priority):
                    inventory.use_item(EffectGame(self,'AI item',i),c,item); return True
        return False

    def bandage(self, apply=True):
        i=next((i for i,c in enumerate(self.chars) if not self.record(i)['outsider']
                and field(c,'side')==0 and field(c,'status')==5),None)
        if i is None: return False
        if apply:
            put(self.chars[i],'status',4); self.record(i)['overkill']=0
            self.message(name(self.chars[i])+' is bandaged')
        return True

    def area_targets(self, x, y, radius):
        return [j for j,*_ in self.spans([(x,y)],radius)]

    def spell_targets(self, i, row, using_item=False, ai=False):
        from . import magic
        facade = EffectGame(self,'spell targeting',i); facade.using_item = using_item
        reach = (row.range_base+row.range_per_level*(6 if using_item else magic.caster_level(facade,self.chars[i],row.id)))&255
        if reach == 255 or not reach and row.area: reach = 1
        area = row.area&15
        self.data.update(aim=self.position(i),aim_view=self.data['view'],multi_target=0)
        if area == 0: return [i]
        available = [j for j in self.targets(i,reach,allies=True) if self.can_target(i,j)]
        bodies = {}
        if not ai and row.id != 83:
            occupied = self.occupancy(); origin = self.position(i); height = self.terrain(self.tile(*origin),1)
            for (x,y,_),j in zip(self.data.get('downed',[]),self.data.get('downed_who',[])):
                if j < 0 or self.tile(x,y) != 31 or (x,y) in occupied: continue
                ray = list(line(*origin,x,y))
                if ray[-1][2] <= 2*reach+1 and all(self.terrain(self.tile(a,b),2) <= height for a,b,_ in ray): bodies[(x,y)] = j
        listed = available+[j for j in bodies.values() if j not in available and self.can_target(i,j)]
        selected = []
        count = 1 if area>=8 else (area&3)+1
        budget = (magic.caster_level(facade,self.chars[i],row.id) if row.id==79 else self.die(2,4,'spell target budget',i)) if area==5 else None
        total = 0
        while count or budget is not None:
            if ai:
                j=i
                if row.id == 3:
                    j=self.cure_target(i)
                    if j is None: break
                elif row.offensive:
                    if not self.acquire(i,reach=reach,force=True): break
                    j=self.record(i)['target']
                    if self.disabled(j) and row.effect in (51,52,53,31): break
                aim = self.position(j)
            else:
                creature_ok,ground_ok = row.id!=83,8<=area<=14
                choices = [name(self.chars[j])+' #%d'%j for j in listed]+(['Ground'] if ground_ok else [])+['Exit']
                pick = self.ask(Kind.TARGET,choices,spell=row.id,prompt=row.name,targets=available,selected=selected)
                if pick == len(choices)-1: break
                j = listed[pick] if pick<len(listed) else -1
                aim = self.position(j) if j>=0 else self.position(i)
                if j<0:
                    dirs = ['north','northeast','east','southeast','south','southwest','west','northwest']
                    while True:
                        self.data['aim'] = aim
                        ray = list(line(*self.position(i),*aim))
                        height = self.terrain(self.tile(*self.position(i)),1)
                        valid = self.tile(*aim) and self.terrain(self.tile(*aim))<255 and ray[-1][2]<=2*reach+1 and all(self.terrain(self.tile(x,y),2)<=height for x,y,_ in ray)
                        occupant=self.occupancy().get(aim,-1)
                        if occupant>=0 and (not creature_ok or not self.can_target(i,occupant)): valid=False
                        choices=dirs+(['Target'] if valid else [])+['Exit']
                        pick=self.ask(Kind.AIM,choices,prompt=row.name,spell=row.id,cursor=aim,range=reach)
                        if choices[pick]=='Exit': aim=None; break
                        if choices[pick]=='Target': break
                        aim=max(0,min(49,aim[0]+DX[pick])),max(0,min(24,aim[1]+DY[pick]))
                        ox,oy=self.data['aim_view']
                        if abs(aim[0]-ox-3)>2: ox=max(0,min(43,aim[0]-3))
                        if abs(aim[1]-oy-3)>2: oy=max(0,min(18,aim[1]-3))
                        self.data['aim_view']=ox,oy
                    if aim is None: continue
            self.data['aim'] = aim
            if not ai or row.offensive: self.record(i)['target'] = j
            if area>=8:
                locked = self.record(i)['target']
                if area==15 and locked is not None and locked>=0: return [locked]
                self.data['multi_target'] = 1
                return self.area_targets(*aim,0 if area==15 else area&7)
            if j in selected or row.id in (23,49) and j==i:
                if not ai:
                    self.message('Cannot target yourself' if j==i and area!=5 else 'Already been targeted'); continue
                if budget is not None:
                    budget -= 1
                    if budget <= 0: break
                else: count -= 1
                continue
            selected.append(j); count-=1
            if budget is not None:
                level = field(self.chars[j],'highest_level')
                total += (1 if level<2 else 2 if level==2 else 4 if level==3 else 8) if row.id!=79 else {1:1,2:2,3:2,4:4}.get(field(self.chars[j],'dimensions'),0)
                if len(selected)>1 and total>budget: break
        return selected if selected or area==5 else None

    def cast(self, i, ident, using_item=False, ai=False):
        from . import magic
        row,c = magic.spell(ident),self.chars[i]
        if ident not in magic.HANDLERS: raise BindingRequired('Champions combat spell not bound: %d %s'%(ident,row.name))
        facade = EffectGame(self,'spell %d %s'%(ident,row.name),i); facade.using_item = using_item
        if has(c,74) and self.die(1,2,'miscast',i)==1:
            self.message(name(c)+' Casts a Spell'); self.event('miscast',actor=i,spell=ident); return False
        if not using_item: self.message(name(c)+' Casts a Spell')
        while True:
            targets = self.spell_targets(i,row,using_item,ai)
            if targets is not None: break
            if ai or self.ask(Kind.CONFIRM,['Yes','No'],prompt='Abort Spell? ')==0:
                self.message('Spell Aborted')
                if not using_item: magic.forget(c,ident)
                self.event('spell aborted',actor=i,spell=ident,item=using_item)
                return False
        while has(c,25): self.remove_effect(i,25)
        if not using_item: magic.forget(c,ident)
        self.record(i)['facing'] = next(d for d in range(8) if in_cone(*self.position(i),*self.data['aim'],d))
        self.event('cast',actor=i,spell=ident,targets=tuple(targets),aim=self.data['aim'],item=using_item)
        self.data['flash'] = dict(actor=i,targets=tuple(targets),aim=self.data['aim'],spell=ident)
        self.show('bolt',actor=i,aim=tuple(self.data['aim']),spell=ident)
        self.data.update(current_spell=ident,using_item=using_item)
        try: magic.HANDLERS[ident](facade,c,[self.chars[j] for j in targets],row)
        finally:
            self.data.pop('current_spell',None); self.data.pop('using_item',None)
        self.data['multi_target'] = 0
        if not ai: self.ask(Kind.ACK,['Continue'],prompt=row.name,spell=ident)
        self.data.pop('flash',None)
        return True

    def cast_item(self, char, ident):
        i = self.index(char)
        if not self.record(i)['item_ok']:
            self.message(name(char)+' cannot use an item'); return False
        done = self.cast(i,ident,True,bool(field(char,'auto_combat')))
        if done: self.end(i)
        return done

    def begin_cast(self, i, ident=0, ai=False):
        from . import magic
        c,r = self.chars[i],self.record(i)
        if not ident:
            offered = magic.castable(c,True)
            levels = tuple(magic.spell(k).level for k,_ in offered)
            pick = self.ask(Kind.SPELL,[magic.spell(k).name+(' (%d)'%n if n>1 else '') for k,n in offered]+['Exit'],prompt='Cast',spells=[k for k,_ in offered],
                            start=magic.list_start(levels)[0] if offered else 0,levels=levels)
            if pick==len(offered): return False
            ident = offered[pick][0]
        row = magic.spell(ident)
        if not row.combat_ok: self.message('Camp Only Spell'); return False
        delay = row.cast_time//3
        if not delay:
            self.cast(i,ident,ai=ai); self.end(i); return True
        r.update(casting=ident,initiative=max(1,r['initiative']-delay))
        order,cursor = self.data['order'],self.data['cursor']
        order.pop(cursor); at=cursor
        while at<len(order) and (self.record(order[at])['initiative']>r['initiative'] or
                self.record(order[at])['initiative']==r['initiative'] and self.die(1,2,'casting initiative tie',i,order[at])==1): at+=1
        order.insert(at,i); self.data['cursor']-=1
        self.message(name(c)+' Begins Casting')
        self.event('begin casting',actor=i,spell=ident,initiative=r['initiative'],position=at)
        return True

    def touch(self, caster, target, row):
        from .magic import _roll
        i,j = self.index(caster),self.index(target)
        x = _roll(EffectGame(self,'touch spell',i),caster,row)
        rules.recalc_stats(target); self.trigger(11,j,x)
        natural = self.die(1,20,'spell touch',i,j); x.attack = 100 if natural==20 else natural
        if natural!=1: self.trigger(10,i,x); self.trigger(16,j,x)
        modifier = signed(self.s.r1[0x371 if field(caster,'side')==0 else 0x370]&255)
        return natural!=1 and x.attack>=0 and x.attack+field(caster,'thac0')+modifier>=field(target,'ac')

    def spell_damage(self, target, context, reduction, saved):
        j = self.index(target); self.trigger(6,j,context)
        if getattr(context,'reflect',None) is not None: j=context.reflect; target=self.chars[j]
        if saved and reduction in (1,2): context.damage = 0 if reduction==1 else context.damage//2
        if not saved: self.trigger(20,j,context)
        self.remember_roll(context)
        if context.damage and field(target,'active'):
            e = context.element&255
            source = {1:'from Fire',2:'from Cold',4:'from Electricity',16:'from Acid'}.get(e&0xF7,'')+('from Magic' if e&8 == e else '')
            self.message('%s takes %s of damage %s'%(name(target),'1 point' if context.damage == 1 else '%d points'%context.damage,source))
            self.damage(j,context.damage,context,True)
        return target

    def cone(self, i, aim, width, length):
        start=self.position(i); points=list(line(*start,*aim))[1:]
        if not points: return []
        directions=[]; previous=start
        for x,y,_ in points:
            directions.append((x-previous[0],y-previous[1])); previous=x,y
        x,y=aim; used=points[-1][2]; n=0
        while used<2*length and 0<x<49 and 0<y<24:
            dx,dy=directions[n%len(directions)]; n+=1
            x+=dx; y+=dy; used=(used+(3 if dx and dy else 2))&255
        end=tip=max(0,min(49,x)),max(0,min(24,y))
        height=self.terrain(self.tile(*start),1)
        end=tip=next(((x,y) for x,y,_ in line(*start,*tip) if self.terrain(self.tile(x,y),2)>height),tip)
        occupied=self.occupancy(); targets=[]; duplicate=False; center=last=None; previous=start
        for x,y,_ in list(line(*start,*end))[1:]:
            occupant=occupied.get((x,y)); end=x,y
            if occupant is not None:
                if not targets: duplicate=False
                elif occupant in targets: duplicate=True
                if not duplicate: targets.append(occupant)
                center=direction_to(*previous,x,y)
            last=direction_to(*previous,x,y); previous=x,y
        if width==255:
            area=self.area_targets(*tip,3); targets=area+targets[len(area):]
        elif width>1:
            if center is None: center=last
            if center is None: raise BindingRequired('Champions cone center direction is undefined without an occupied ray')
            raw=self.t['cone_sides']
            for offset in (16,0)[:width-1]:
                side=tuple(max(0,min(bound,end[k]+signed(raw[offset+8*k+center]))) for k,bound in enumerate((49,24)))
                for x,y,_ in list(line(*start,*side))[1:]:
                    occupant=occupied.get((x,y))
                    if occupant is not None and occupant not in targets: targets.append(occupant)
        return [j for j in targets if j!=i]

    def dragon_breath(self, i, node, context):
        from . import magic
        kind=node[0]; c=self.chars[i]
        if not self.data['round'] or kind!=90 and node[3]>3: node[3]=1 if kind==6 else 3
        if not node[3]: return
        element=0x30 if kind==90 else 0x21 if kind==104 else 0x22
        context.element=element; self.remember_roll(context)
        if self.spell_targets(i,magic.spell(61),ai=True) is None: return
        targets=self.cone(i,self.data['aim'],1 if kind==90 else 3,{6:8,83:7,90:6,104:9}[kind])
        if not targets or any(field(self.chars[j],'side')==field(c,'side') for j in targets): return
        self.message(name(c)+' breathes '+('acid' if kind==90 else 'Fire' if kind==104 else 'cold'))
        self.record(i)['facing']=self.direction(i,targets[0])
        self.event('breath',actor=i,kind=kind,targets=tuple(targets),charges=node[3])
        self.show('bolt',actor=i,aim=tuple(self.position(targets[0])),spell=61)
        for j in targets:
            saved=self.save(j,3,element=element)
            self.spell_damage(self.chars[j],self.context(c,damage=field(c,'hp_max'),element=element),2,saved)
        for key,value in self.data['roll'].items(): setattr(context,key,value)
        node[3]-=1; self.end(i)

    def heal(self, char, amount):
        if field(char,'status') not in (0,1,4,5): return False
        put(char,'hp',min(field(char,'hp_max'),(field(char,'hp')+amount)&255))
        if not field(char,'active') and field(char,'status')==5: put(char,'status',4)
        self.event('heal',actor=self.data['actor'],target=self.index(char),amount=amount,hp=field(char,'hp'))
        return True

    def turn_undead(self, i):
        c,r = self.chars[i],self.record(i); r['turns']+=1
        left,roll = self.die(1,12,'turn count',i),self.die(1,20,'turn undead',i)
        column = field(c,'levels',0)+field(c,'former_levels',0)*earlier_class(c)+2*(field(c,'deity')==2)
        if not 1<=column<=13: raise BindingRequired('Champions turning column outside native table: %d'%column)
        minimum,cap,turned_any = 6,13,False
        while left:
            candidates = [j for j in self.targets(i) if not self.record(j)['turned'] and 0<field(self.chars[j],'undead')<=cap]
            if not candidates: break
            j = max(candidates,key=lambda j:field(self.chars[j],'undead')); cap=field(self.chars[j],'undead')
            needed = signed(self.t['turning'][(cap-1)*13+column-1])
            if roll<abs(needed): cap-=1; continue
            target = self.chars[j]; destroyed=needed<=0; turned_any=True
            if self.drawing(): self.center(j,3)
            if destroyed:
                self.message(name(target)+' Is destroyed'); put(target,'status',8); put(target,'active',0); self.down(j)
            else:
                self.message(name(target)+' is turned'); put(target,'status',3); put(target,'active',0); self.strip(j); self.down(j)
            self.event('turn undead',actor=i,target=j,column=column,needed=needed,roll=roll,destroyed=destroyed)
            minimum=max(0,minimum-1); left-=1
            if not left and minimum and needed<0: left=1
        if not turned_any: self.message('Nothing Happens...')
        self.count_teams()
        self.end(i)

    def cloud(self, caster, level):
        i = self.index(caster); clouds=self.data.setdefault('clouds',[])
        instance = sum(n['owner']==i for n in clouds[:-1])
        effects.add_effect(caster,40,level,level+instance*16,True)
        x,y=self.data['aim']; cells=[]; victims=[]; occupied=self.occupancy()
        for dx,dy in ((0,0),(1,0),(1,1),(0,1)):
            cell=(x+dx,y+dy); tile=self.tile(*cell)
            if tile and self.terrain(tile)<255:
                original=tile
                if tile==30:
                    original=next((t for n in clouds for a,b,t in n['cells'] if (a,b)==cell and t!=30),tile)
                elif tile==31:
                    original=next((t for a,b,t in reversed(self.data.get('downed',[])) if (a,b)==cell),tile)
                cells.append((*cell,original)); self.put_tile(*cell,30)
                target=occupied.get(cell,-1)
                if target>=0 and target not in victims: victims.append(target)
        clouds.append(dict(owner=i,instance=instance,cells=cells,spent=False))
        self.event('cloud',actor=i,cells=tuple((a,b) for a,b,_ in cells),minutes=level)
        self.message(name(caster)+' Creates a noxious cloud')
        for j in victims: self.terrain_effects(j)

    def clear_cloud(self, owner, instance):
        clouds=self.data.get('clouds',[])
        node=next((n for n in clouds if n['owner']==owner and n['instance']==instance),None)
        if node is None: return
        for x,y,tile in node['cells']:
            corpse=any(not r['size'] and not r['outsider'] and (r['x'],r['y'])==(x,y) and field(c,'status')!=3
                       for c,r in zip(self.chars,self.data['actors']))
            self.put_tile(x,y,31 if corpse else tile)
        clouds.remove(node)
        for other in clouds:
            for x,y,_ in other['cells']: self.put_tile(x,y,30)
        for pool in self.data.get('acid',[]): self.put_tile(*pool['cell'],29)
        self.message('The air clears a little...')

    def acid_pool(self, i):
        pools=self.data.setdefault('acid',[]); cell=self.position(i); tile=self.tile(*cell)
        if tile==31: tile=None
        instance=sum(n['owner']==i for n in pools[:-1])
        length=self.die(1,6,'acid pool duration',i)
        effects.add_effect(self.chars[i],80,length,instance,True)
        if tile==30:
            for cloud in self.data.get('clouds',[]):
                for x,y,ground in cloud['cells']:
                    if (x,y)==cell and ground!=30: tile=ground
        pools.append(dict(owner=i,instance=instance,cell=cell,ground=tile))
        self.put_tile(*cell,29); self.message(name(self.chars[i])+' dissolves into acid!')
        self.event('acid pool',actor=i,cell=cell,minutes=length)

    def clear_acid(self, owner, instance):
        pools=self.data.get('acid',[])
        node=next((n for n in pools if n['owner']==owner and n['instance']==instance),None)
        if node is None: return
        corpse=any(not r['size'] and not r['outsider'] and (r['x'],r['y'])==node['cell'] and field(c,'status')!=3
                   for c,r in zip(self.chars,self.data['actors']))
        if not corpse and node['ground'] is None:
            raise BindingRequired('Champions acid exposed after moving a corpse uses an unset native neighbour index')
        self.put_tile(*node['cell'],31 if corpse else node['ground']); pools.remove(node)
        for cloud in self.data.get('clouds',[]):
            for x,y,_ in cloud['cells']: self.put_tile(x,y,30)
        for pool in pools: self.put_tile(*pool['cell'],29)
        self.message('The acid drains away..')

    def dispel_clouds(self, caster, succeeds):
        x,y=self.data['aim']
        for dx,dy in ((0,0),*zip(DX[:8],DY[:8])):
            cell=x+dx,y+dy
            if self.tile(*cell)!=30: continue
            for node in list(self.data.get('clouds',[])):
                if node.get('spent') or not any((a,b)==cell for a,b,_ in node['cells']): continue
                owner=self.chars[node['owner']]
                level=(field(owner,'levels',5)+field(owner,'former_levels',5)*earlier_class(caster))&255
                if succeeds(level):
                    effect=next((e for e in owner.effects if e[0]==40 and e[3]//16==node['instance']),None)
                    if effect is not None: effects.remove_effect(EffectGame(self,'dispel cloud',self.index(caster)),owner,40,effect)
                else: node['spent']=True

    def terrain_effects(self, i, cloud=True):
        from . import magic
        c=self.chars[i]
        if not field(c,'active'): return
        cells=self.cells(i)
        if cloud and not field(c,'undead') and not has(c,31) and not has(c,99) and any(self.tile(x,y)==30 for x,y in cells):
            cloud=next((n for n in self.data.get('clouds',[]) if any((x,y) in cells for x,y,_ in n['cells'])),None)
            if cloud is None: raise BindingRequired('Champions cloud owner is not bound')
            saved=self.save(i,0); ident=30 if saved else 31
            length=self.die(1,4,'cloud duration',cloud['owner'],i)+1
            owner=self.chars[cloud['owner']]; facade=EffectGame(self,'cloud effect',cloud['owner'],i)
            magic._add_with_message(facade,owner,c,magic.spell(34),ident,length,255,False,'starts to cough' if saved else 'chokes and gags from nausea')
            node=effects.has_effect(c,ident)
            if node is not None: effects.call_handler(facade,c,ident,node,False,self.context(owner))
        if any(self.tile(x,y)==29 for x,y in cells):
            actor=self.data['actor']; x=self.context(self.chars[actor] if actor>=0 else c)
            x.damage=self.damage_dice(1,6,'acid damage',actor,i); x.dice_count=1; self.spell_damage(c,x,0,False)

    def lightning(self, facade, caster, row, amount, length=7, save=4, element=12, bounce=True, first=None):
        from .magic import _roll
        origin=self.position(self.index(caster)); start=self.data['aim']
        def hit(j, amount=amount):
            if j>=0:
                x=_roll(facade,caster,row); x.damage,x.element=amount,element
                x.spell=self.data.get('current_spell',0)
                self.spell_damage(self.chars[j],x,2,self.save(j,save,element=element))
        hit(self.occupancy().get(start,-1),amount if first is None else first)
        if start==origin: return
        previous=self.occupancy().get(start,-1)
        budget,sign,used,bonus,blocked=2*length,1,0,bounce,False
        self.data['multi_target']=1
        while budget>0:
            end=tuple(start[k]+(start[k]-origin[k])*sign*budget for k in (0,1))
            for x,y,distance in list(line(*start,*end))[1:]:
                tile=self.tile(x,y); cost=self.terrain(tile)
                j=self.occupancy().get((x,y),-1)
                if cost==1: blocked=False
                if tile and cost<=1 and j in (-1,previous) and distance<budget: continue
                if not tile: budget=0
                blocked=bool(tile and cost==255 and self.game.vm.m0(0x4BE6)==1 and not blocked)
                if j!=previous: hit(j)
                previous=j
                self.event('lightning segment',cell=(x,y),distance=distance,bounce=blocked)
                if blocked:
                    self.data['aim']=start=(x,y); sign=-sign; previous=-1
                    if bonus and list(line(x,y,*origin))[-1][2]<=8: distance+=8
                    bonus=False
                budget=max(0,budget-((distance-used)&255)); used=distance
                if blocked or not budget: break
            else: break
        self.data['multi_target']=0

    def toggle_magic(self):
        self.data['magic_enabled'] = not self.data.get('magic_enabled',False)
        self.message('Magic On' if self.data['magic_enabled'] else 'Magic Off')

    def auto_on(self, i):
        c,r = self.chars[i],self.record(i)
        put(c,'auto_combat',1)
        if r['target']>=0 and field(self.chars[r['target']],'side')==field(c,'side'): r['target']=-1

    def speed_menu(self):
        from .creation import DELAY, game_setting
        while True:
            delay = game_setting(self.s,DELAY)
            options = (['Slower'] if delay<9 else [])+(['Faster'] if delay>0 else [])+['Exit']
            choice = options[self.ask(Kind.DONE,options,query='GameSpeed (%d) :'%delay)]
            if choice == 'Exit': return
            self.s.g[DELAY] = delay+(1 if choice == 'Slower' else -1)

    def manual(self, i):
        from . import town
        c,r = self.chars[i],self.record(i)
        while r['initiative']>0 and field(c,'active'):
            options = (['Move'] if r['movement'] else [])+['View','Aim']+(['Use'] if c.items else [])
            if r['cast_ok'] and not self.s.r0[0xE5] and any(field(c,'memorized',k) for k in range(58)): options.append('Cast')
            if r['turns']<self.s.g.get('cok.undead_count',0) and (field(c,'levels',0) or earlier_class(c) and field(c,'former_levels',0)): options.append('Turn')
            if field(c,'race') == 5 and self.data['yell']<0: options.append('Yell')
            options.append('Done')
            action = (options+FIGHT_KEYS)[self.ask(Kind.ACTION,options+FIGHT_KEYS,prompt=name(c),movement=r['movement']//2)]
            if action == 'space':
                for member in self.chars:
                    if field(member,'npc')<128: put(member,'auto_combat',0)
            elif action == 'Alt-m': self.toggle_magic()
            elif action in ('Alt-q','Alt-a'):
                self.data['cursor'] -= 1; r['initiative'] = 20
                for j in range(len(self.chars)): self.auto_on(j)
                return
            elif action == 'View':
                from .inventory import view
                facade = EffectGame(self,'inventory effect',i); facade.weapon = self.weapon(i)
                view(facade,c); self.reset_attacks(i)
            elif action == 'Use':
                from .inventory import items_menu
                facade = EffectGame(self,'inventory effect',i); facade.weapon = self.weapon(i)
                items_menu(facade,c); self.reset_attacks(i)
            elif action == 'Cast':
                if self.begin_cast(i): return
            elif action == 'Turn': self.turn_undead(i)
            elif action == 'Yell':
                self.data['yell'] = i
                for j,t in enumerate(self.chars):
                    if field(t,'status') == 0 and field(t,'abilities',3)>3 and field(t,'side') != field(c,'side') and not self.disabled(j) and not self.save(j,4):
                        effects.add_effect(t,91,0,255,False); self.message(name(t)+' wants to kill '+name(c))
                self.end(i)
            elif action == 'Aim':
                targets = self.attack_targets(i)
                choice = self.ask(Kind.TARGET,[name(self.chars[j])+' #%d'%j for j in targets]+['Exit'],targets=targets)
                if choice<len(targets) and self.confirm_ally(i,targets[choice]):
                    j = targets[choice]
                    missile = self.ammo(i)[1] if self.ranged(i) and not (self.throwable(i) and self.distance(i,j) == 1) else None
                    self.strike(i,j,missile=missile)
            elif action == 'Move':
                directions = ['north','northeast','east','southeast','south','southwest','west','northwest']
                start = {k:r[k] for k in ('x','y','size','movement','facing')}
                prompt = ''
                while r['initiative']>0 and field(c,'active'):
                    d = self.ask(Kind.MOVE,directions+['Done','Undo'],movement=r['movement']//2,prompt=prompt)
                    prompt = ''
                    if d == 9:
                        r.update(start)
                        occupant,tile = self.probe(i)
                        self.center(i,0)
                        if occupant>=0 or not tile or self.terrain(tile)==255: self.end(i)
                    if d >= 8: break
                    self.face(i,d)
                    occupant,tile = self.probe(i,d)
                    if occupant>=0:
                        refused=self.ranged(i) and not self.throwable(i)
                        self.move_attack(i,occupant)
                        if refused: prompt='Not with that weapon'
                    elif not tile:
                        if self.ask(Kind.CONFIRM,['Yes','No'],prompt='Flee:',start=1) == 0: self.flee(i)
                    elif not self.move(i,d): prompt="can't go there"
                if r['movement']<2: r['movement'] = 0
            elif action == 'Done':
                while True:
                    options = (['Guard'] if not self.ranged(i) or self.throwable(i) else [])+['Delay','Quit']
                    if self.bandage(False): options.append('Bandage')
                    options += ['Auto','Speed','Exit']
                    choice = options[self.ask(Kind.DONE,options)]
                    if choice != 'Speed': break
                    self.speed_menu()
                if choice in ('Guard','Quit','Bandage'):
                    if choice == 'Bandage': self.bandage()
                    self.end(i,choice == 'Guard')
                elif choice == 'Delay':
                    order,cursor = self.data['order'],self.data['cursor']
                    order.append(order.pop(cursor)); self.data['cursor'] -= 1; r['initiative'] = 1; return
                elif choice == 'Auto':
                    self.auto_on(i); self.ai(i); return
            else: raise BindingRequired('Champions combat %s is not bound'%action)

    def turns(self):
        for i in range(len(self.chars)): self.trigger(24,i)
        if not all(self.teams()): return
        while True:
            self.begin_round()
            while self.data['cursor']<len(self.data['order']):
                i = self.data['order'][self.data['cursor']]; c,r = self.chars[i],self.record(i)
                self.data['actor'] = i; self.s.sel = i
                r.update(flanks=0,spread=0,guard=0); self.trigger(7,i)
                if r['initiative']>0:
                    if r['initiative'] == 20: r['initiative'] = 19
                    self.turn_view(i)
                    rules.recalc_stats(c); self.trigger(15,i)
                    if not r['casting']: self.trigger(21,i)
                    if r['initiative']>0:
                        if field(c,'auto_combat'): self.ai(i)
                        elif r['casting']:
                            ident=r['casting']; r['casting']=0
                            self.cast(i,ident,ai=bool(field(c,'auto_combat'))); self.end(i)
                        else: self.manual(i)
                self.explode()
                self.data['cursor'] += 1
            effects.advance(EffectGame(self,'round effects',-1),1,1)
            for i in range(len(self.s.party),len(self.chars)): effects.age_effects(EffectGame(self,'monster round effects',i),self.chars[i],1)
            self.data['round'] += 1; self.hp_percent()
            for i,c in enumerate(self.chars):
                self.trigger(19,i)
                self.terrain_effects(i,cloud=False)
                if field(c,'status') == 5:
                    self.record(i)['overkill'] += 1
                    if self.record(i)['overkill']>9: put(c,'status',6)
            if self.bandage(False): self.message('Your Teammate is Dying')
            left,right = self.teams()
            done = not left or not right or self.data['round']>=self.data['limit']
            if left and not right: done = self.ask(Kind.CONFIRM,['Yes','No'],prompt='Continue Battle:',start=1) != 0
            if done: return

    def loot(self):
        from . import camp, magic, shop, town
        s,game = self.s,self.game
        def member(choice):
            s.sel = 0 if choice == 'char-first' else (s.sel+(-1 if choice == 'char-up' else 1))%len(s.party)
        def take_items():
            at = 0
            while s.treasure_items:
                at = min(at,len(s.treasure_items)-1)
                labels = [shop.item_name(game,item) for item in s.treasure_items]
                note,game.shop_note = getattr(game,'shop_note',''),''
                at = self.ask(Kind.LOOT,labels+['Exit'],prompt='Items: ',query='Items: ',menu='Take',window='1 1 38 22',start=at,message=note)
                if at == len(labels): return
                if shop.give_item_copy(game,s.selc(),s.treasure_items[at]): s.treasure_items.pop(at)
        def take(money, items):
            if not items: return shop.take_menu(game,s.selc())
            if not money: return take_items()
            while any(s.treasure_money) and s.treasure_items:
                options = ['Money','Items','Exit','char-up','char-down']
                what = options[self.ask(Kind.LOOT,options,prompt='Take: ')]
                if what == 'Exit': return
                if what == 'Money': shop.take_menu(game,s.selc())
                elif what == 'Items': take_items()
                else: member(what)
        while s.party:
            c = s.selc(); money,items = any(s.treasure_money),bool(s.treasure_items)
            detect = next((held for held in camp.memory(c) if held in (5,11,77,103)),0) if items and field(c,'active') else 0
            options = ['View']+(['Take'] if money or items else [])+['Pool']+(['Share'] if money else [])+(['Detect'] if detect else [])+['Exit','char-up','char-down','char-first']
            choice = options[self.ask(Kind.LOOT,options)]
            if choice == 'Exit':
                if not (money or items): return
                while True:
                    options = ['Yes','No','char-up','char-down','char-first']
                    answer = options[self.ask(Kind.CONFIRM,options,offer='There is still treasure left.  Do you want to go back and claim your treasure?')]
                    if answer in ('Yes','No'): break
                    member(answer)
                if answer == 'No': return
            elif choice == 'View': town.view_character(game)
            elif choice == 'Pool': shop.pool_money(s)
            elif choice == 'Share': shop.share_money(s)
            elif choice == 'Detect': magic.cast_spell(game,c,detect,announce=False)
            elif choice.startswith('char-'): member(choice)
            elif choice == 'Take': take(money,items)

    def treasure(self):
        self.s.g['cok.battle'] = dict(active=False,round=0,actor=-1,bank=[],messages=[],
            treasure_boundary=None,actors=[dict(outsider=0,size=0,x=0,y=0) for c in self.chars])
        if not hasattr(self.game,'combat_log'): self.game.combat_log=[]
        self.postcombat(False)

    def postcombat(self, fought=True):
        from . import shop
        s = self.s
        for i,c in enumerate(self.chars if fought else ()):
            if has(c,11) and field(c,'status') == 0 and self.teams()[1]>1: put(c,'status',3)
            self.strip(i)
        for key in ('clouds','acid'):
            if self.data.get(key): self.data[key]=[]
        for key in ('in_range','ghosts'): self.data.pop(key,None)
        for owner,raw in self.data['bank']:
            returned = shop.give_item_copy(self.game,self.chars[owner],raw)
            if not returned: self.message('OverLoaded')
            self.event('bank return',actor=owner,item_type=raw[I['type']],returned=returned)
            self.game.shop_note = ''
        self.data['bank'] = []
        s.r1[0x2C7] = 0
        fled = any(field(c,'status') == 3 for c in s.party)
        alive = any(field(c,'active') or field(c,'status') in (3,4,5) for c in self.chars)
        defeated = not (s.r1[0x2E6] and alive or any(field(c,'status') in (0,1,3) and field(c,'side') == 0 and field(c,'npc')<128 for c in s.party))
        won = any(field(c,'status') in (0,1) for c in s.party)
        if won: fled = False
        eligible = sum(bool(field(c,'active')) and field(c,'status') != 1 for c in s.party)
        for i in range(len(s.party)):
            for k in (3,11,21,23,27,35,40,51,52,53,31): self.remove_effect(i,k)
        share,total = 0,0
        if won:
            boundary = self.data['treasure_boundary']
            for i,c in enumerate(self.chars):
                if field(c,'side') != 1 or field(c,'status') in (0,3): continue
                if self.record(i)['outsider']:
                    s.treasure_money = [a+field(c,'money',k*2,width=2) for k,a in enumerate(s.treasure_money)]
                total += field(c,'xp_award',width=2)+field(c,'xp_per_hp')*field(c,'hp_rolled')
                if s.r1[0x2E3] != 1:
                    for raw in c.items:
                        copy = bytearray(raw); copy[I['readied']] = 0
                        shop.item_name(self.game,copy); s.treasure_items.insert(0,copy)
                        if boundary is not None: boundary += 1
            money = s.treasure_money
            total += money[0]//100+money[1]//20+money[2]//10+money[3]+money[4]*2+money[5]*250+money[6]*2200
            total += sum(max(0,signed(item[I['bonus']]))*400 for item in s.treasure_items[:boundary])
            if not eligible: raise BindingRequired('Champions native XP divisor is zero')
            share = total//eligible
            if not s.r0[0x1F5]:
                for i,c in enumerate(self.chars):
                    if not field(c,'active') or field(c,'status') == 1: continue
                    cls = field(c,'class'); award = share
                    stats = [field(c,'abilities',k*2+1) for k in range(6)]
                    prime = {0:stats[2]>14,2:stats[0]>15,3:stats[0]>15 and stats[2]>15,
                             4:all(v>15 for v in stats[:3]),5:stats[1]>15,6:stats[3]>15}
                    if prime.get(cls,False): award += share//10
                    elif cls in (8,10,11,12,13,14,16): award //= 2
                    elif cls in (9,15): award //= 3
                    put(c,'experience',field(c,'experience',width=4)+award,width=4)
                    self.event('experience',actor=i,amount=award)
        self.data.update(active=False,result='defeat' if defeated else 'fled' if fled else 'won' if won else 'ended',experience=share)
        removed = []
        for i,c in enumerate(self.chars):
            if self.record(i)['outsider'] or field(c,'side') == 1: removed.append(c)
        s.r1[0x2C8] = sum(field(c,'active') != 1 for c in removed)
        if removed and field(removed[0],'active') != 1: s.r0[0x1F8] = 1
        if any(field(c,'status') == 3 for c in removed): s.r1[0x2C7] = 1
        if defeated: s.party = []; s.party_dead = True; s.r1[0x2C7] = 128
        else:
            if fled: s.party = [c for c in s.party if field(c,'status') == 3]; s.r1[0x2C7] = 129
            for c in s.party:
                status = field(c,'status')
                if status == 3: put(c,'status',0); put(c,'active',1)
                elif status in (4,5):
                    if s.r1[0x2E6] or status == 4 and field(c,'hp')>0:
                        put(c,'status',0); put(c,'active',1)
                        if not field(c,'hp'): put(c,'hp',1)
                    elif status == 5: put(c,'status',4)
            s.party = [c for c in s.party if field(c,'side') == 0]
        s.monsters = []; s.r1[0x33E] = len(s.party); s.sel = 0; s.mode = 6
        s.g['cok.monster_icons'] = []
        for c in s.party: rules.recalc_stats(c)
        if fled: s.treasure_items = []
        lost = bool(removed) and not defeated and not fled and not won and bool(s.r1[0x2E6])
        if lost: s.r1[0x2C7] = 128; self.data['result'] = 'lost'
        self.event('result',result=self.data['result'],experience=share,defeated=s.r1[0x2C8],code=s.r1[0x2C7])
        if not defeated:
            weights = [field(c,'modified')&7 if field(c,'npc')>127 and field(c,'status') == 0 else 1 for c in s.party]
            npc = sum(weight for c,weight in zip(s.party,weights) if field(c,'npc')>127 and field(c,'status') == 0)
            if npc and any(v>0 for v in s.treasure_money):
                s.treasure_money = [v-npc*((v//sum(weights))&255) for v in s.treasure_money]
                takers = [c for c in s.party if field(c,'npc')>127 and field(c,'status') == 0 and field(c,'modified')]
                self.ask(Kind.ACK,['Continue'],message='\n'.join('%s takes and hides %s share.'%(name(c),'her' if field(c,'gender') else 'his') for c in takers))
            if removed and fled: s.treasure_money = [0]*7
            outcome = ('The party has fled.' if fled else 'You have lost the fight.' if lost else 'The party has won.') if removed else 'The party has found Treasure!'
            self.ask(Kind.ACK,['Continue'],message=outcome+' Each character receives %d experience points.'%(0 if removed and (fled or lost) else share))
            self.loot(); s.treasure_items = []
        else: self.ask(Kind.ACK,['Continue'],message='The monsters rejoice for the party has been destroyed')
        for offset in (0x370,0x371,0x372,0x2E3,0x2E6): s.r1[offset] = 0
        s.r0[0x1F5] = 0


class EffectState:
    def __init__(self, battle, reason, actor, target): self.battle,self.reason,self.actor,self.target = battle,reason,actor,target
    def __getattr__(self, key): return getattr(self.battle.s,key)
    def random(self, sides): return self.battle.die(1,sides,self.reason,self.actor,self.target)-1


class EffectGame:
    def __init__(self, battle, reason, actor, target=-1):
        self.game,self.s,self.battle,self.weapon = battle.game,EffectState(battle,reason,actor,target),battle,None
        self.using_item = battle.data.get('using_item',False)
    def __getattr__(self, key): return getattr(self.game,key)
    def combat_effect(self, char, kind, node, removed, roll):
        return self.battle.weapon_effect(char,kind,node,removed,roll if roll.attacker is not None else None,self.weapon)


def run(game):
    battle = Battle(game)
    battle.setup()
    battle.turns()
    battle.postcombat()


def test():
    from ._combat_test import test as check
    return check(quick=True)
