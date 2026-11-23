from contextlib import contextmanager
from enum import Enum
from functools import lru_cache
import hashlib

from sm.ui.art import decode
from sm.titles.ssb.units.combat import Combat as RetainedCombat, line, in_cone
from sm.titles.cok.combat import direction_to as sector_direction
from . import rules, effects
from .records import Character, Spells, Item, Effect, split_records
from .town import field, put

def earlier_class(char): return False
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
FIGHT_KEYS = ['space','Alt-m','Alt-q','Alt-a','Alt-r']
I = {name: offset for name, (offset, _) in Item.FIELDS.items()}
TABLES = dict(ai='aiDirOffsets', ring_direction='placementDirections', ring_quadrant='combatApproachDirections',
    facing='halfDirections', start_x='approachOffsetX', start_y='approachOffsetY', bands='occupancyRanges',
    classes='combatantTiles', terrain='terrain', footprints='iconDelta', turning='turnUndeadTable')

def missile_art(kind, direction):
    if kind in (5,7,12,30,66):
        if direction&1: return dict(picture=14,facing=int(direction in (3,5)),mirror=direction in (5,7),frames=1,pace=10)
        return dict(picture=13+direction%4,facing=direction//4,mirror=False,frames=1,pace=10)
    picture,frames,pace = (16,4,50) if kind in (2,3,6) else (17,4,50) if kind in (54,55) else (21,2,10) if kind in (28,29,67) else (20,2,20)
    return dict(picture=picture,facing=0,mirror=False,frames=frames,pace=pace)


@lru_cache(maxsize=4)
def tables(assets): return {alias: assets.part(name) for alias, name in TABLES.items()}


def signed(value): return (value+128)%256-128
def longint(value): return (value+0x80000000)%0x100000000-0x80000000
def quotient(value, divisor): return (abs(value)//abs(divisor))*(-1 if (value<0) != (divisor<0) else 1)
def name(c): return bytes(c.b[1:1+c.b[0]]).decode('cp437')
def has(c, ident): return any(e[0] == ident for e in c.effects)
def direction_to(x, y, tx, ty): return 0 if (x,y)==(tx,ty) else sector_direction(x,y,tx,ty)


def roll(game, count, sides, reason, actor=-1, target=-1):
    before = game.s.seed
    faces = tuple(game.s.random(sides)+1 for _ in range(count))
    result = sum(faces)&255
    if not hasattr(game, 'combat_log'): game.combat_log = []
    game.combat_log.append(dict(event='dice', reason=reason, actor=actor, target=target,
                                count=count, sides=sides, faces=faces, result=result,
                                before=before, after=game.s.seed))
    return result


def load_creature(game, ident):
    from .save_chars import detach
    ident &= 255
    files = {'GAM': (Character(game.assets.records('MON1CHA')[ident]),)}
    for archive, suffix, kind in (('WIZ','WIZ',Spells),('SPC','EFF',Effect),('ITM','JNK',Item)):
        files[suffix] = tuple(split_records(game.assets.records('MON1'+archive).get(ident,b''),kind))
    files = detach(files,monster=True)
    return rules.character(bytes(files['GAM'][0]),[bytes(item) for item in files['JNK']],
        [bytes(effect) for effect in files['EFF']],rid=ident,
        spells=bytes(files['WIZ'][0]) if files['WIZ'] else None)


def reset_monster_counters(game):
    game.vm.loaded_monster_count = game.vm.monsters_loaded = game.vm.undead_count = 0
    game.vm.icon_slot = 8


def load_monsters(game, ident, count, picture):
    s = game.s
    loaded = getattr(game.vm,'loaded_monster_count',0)
    count = min(max(1,count&255), max(0,63-loaded))
    if not count: return
    template = load_creature(game,ident)
    if field(template,'side') == 1 and 0 < s.r0[0x1F4] < 6:
        hp, maximum = ((field(template,k)*(s.r0[0x1F4]+1)//4)&255 for k in ('hp','hp_max'))
        if not hp or not maximum: hp = maximum = 1
        put(template,'hp',hp); put(template,'hp_max',maximum)
    if field(template,'undead'):
        game.vm.undead_count = (getattr(game.vm,'undead_count',0)+1)&255
    slot = getattr(game.vm, 'icon_slot', 8)
    icons = s.g.setdefault('dkk.monster_icons', [])
    for copy in range(count):
        c = template if not copy else rules.character(template.b,template.items[::-1],template.effects[::-1],rid=template.rid)
        put(c,'order',slot)
        icons.append((len(s.chars()),s.dataset,picture,slot))
        s.monsters.append(c)
        game.vm.loaded_monster_count = (loaded+copy+1)&255
    game.vm.icon_slot = (slot+1)&255
    game.vm.monsters_loaded = 1


class Battle:
    def __init__(self, game):
        self.game, self.s, self.t = game, game.s, tables(game.assets)
        self.attack_poses = {}
        self.first_target_distance = getattr(game, 'combat_first_target_distance', 255)

    @property
    def data(self): return self.s.g['dkk.battle']
    @property
    def chars(self): return self.s.chars()
    @property
    def magic_enabled(self): return getattr(self.game,'combat_magic',False)
    def record(self, i): return self.data['actors'][i]
    def die(self, count, sides, reason, actor=-1, target=-1): return roll(self.game,count,sides,reason,actor,target)
    def event(self, event, **details): self.game.combat_log.append(dict(event=event,round=self.data['round'],seed=self.s.seed,**details))
    def footprint(self, size):
        raw = self.t['footprints'][(size-1)*8:size*8] if size else b''
        return [(signed(raw[i]),signed(raw[i+1])) for i in range(0,len(raw),2) if signed(raw[i]) >= 0]
    def cells(self, i, x=None, y=None):
        r = self.record(i)
        x, y = (r['x'] if x is None else x), (r['y'] if y is None else y)
        return [(x+dx,y+dy) for dx,dy in self.footprint(r['size'])]
    def tile(self, x, y): return self.data['tiles'][y*50+x] if 0 <= x < 50 and 0 <= y < 25 else 0
    def terrain(self, tile, column=0): return self.t['terrain'][(tile-1)*4+column] if 1 <= tile <= 69 else 255
    def raw_terrain(self, x, y, column, ignore=False):
        offset = y*50+x
        tiles = self.data['tiles']
        if 0 <= offset < len(tiles):
            tile = tiles[offset]
        elif -7 <= offset < 0:
            ox, oy = self.data['view']
            header = (0, 0, ox, oy, self.data.get('cursor_active', False),
                      self.data.get('cursor_size', 1), int(ignore))
            tile = header[offset] & 255
        else:
            return 255
        if 1 <= tile <= 69:
            return self.terrain(tile, column)
        assets = self.game.assets
        base = assets.layout['tables']['terrain']['offset']
        return assets.resident[base+(tile-1)*4+column]

    def put_tile(self, x, y, tile): self.data['tiles'][y*50+x] = tile
    def occupancy(self):
        grid = {(x,y):j for x,y,j in self.data.get('stale',())}
        grid.update({cell:i for i in range(len(self.chars)) for cell in self.cells(i)})
        return grid
    def contents(self, x, y, occupied=None):
        if not (0<=x<50 and 0<=y<25): return -1,0
        return (self.occupancy() if occupied is None else occupied).get((x,y),-1),self.tile(x,y)
    def teams(self): return [sum(field(c,'active') != 0 and field(c,'side') == side for c in self.chars) for side in (0,1)]
    def probe(self, i, direction=8, occupied=None):
        r = self.record(i)
        if occupied is None: occupied=self.occupancy()
        occupant, terrain, highest = -1, 23, 1
        for x,y in self.cells(i,r['x']+DX[direction],r['y']+DY[direction]):
            other,tile = self.contents(x,y,occupied)
            if other not in (-1,i): occupant = other
            if not tile: terrain = 0
            elif terrain and self.terrain(tile) >= highest: terrain,highest = tile,self.terrain(tile)
        return occupant,terrain

    def wilderness(self):
        self.data['tiles'] = bytearray([69]*1250)
        terrain_class = self.t['classes'][15]
        if self.s.r0[0xF3]:
            column = 34-self.die(5,4,'river start')
            column -= (column+2)%7
            chance = 1
            for row in range(25):
                if column > 49: continue
                self.put_tile(column,row,52)
                if column < 49:
                    ford = self.die(1,20,'ford chance') <= chance
                    chance = 1 if ford else chance+1
                    cells = ((1,58,0),(2,58,2),(3,58,2),(4,61,0)) if ford else ((1,52,2),(2,55,0),(3,55,0),(4,55,2))
                    for offset,base,sides in cells:
                        if column+offset < 50:
                            self.put_tile(column+offset,row,base+(self.die(1,sides,'ford tile' if ford else 'river tile') if sides else 0))
                if column+5 < 50: self.put_tile(column+5,row,52)
                column += 1
        density = 5-3*bool(terrain_class&2)-3*bool(terrain_class&4)+2*bool(terrain_class&64)+5*bool(terrain_class&8)
        if density < 0: density = 1
        if not terrain_class&128:
            for x in range(50):
                for y in range(1,25):
                    if all(self.terrain(self.tile(x,j),3) == 37 for j in (y,y-1)) and self.die(1,100,'tree chance') <= density:
                        if self.die(1,100,'bush chance') <= density: self.put_tile(x,y,41+self.die(1,2,'bush type'))
                        else:
                            self.put_tile(x,y-1,31+self.die(1,5,'tree top'))
                            self.put_tile(x,y,36+self.die(1,5,'tree bottom'))
        weight = 50+10*bool(terrain_class&16)+30*bool(terrain_class&32)+20*bool(terrain_class&64)-10*bool(terrain_class&4)-20*bool(terrain_class&2)-50*bool(terrain_class&128)
        bands = next((b for low,high,b in ((-30,9,(0,0,0,30,15)),(10,29,(0,1,5,20,10)),(30,69,(0,2,5,10,5)),(70,89,(10,2,10,10,1)),(90,110,(15,5,15,10,1))) if low <= weight <= high), None)
        if bands is None: return
        for x in range(50):
            for y in range(25):
                if self.terrain(self.tile(x,y),3) != 37: continue
                value = self.die(1,100,'feature chance')
                limits = (bands[0],sum(bands[:2]),sum(bands[:2])+1,sum(bands[:4]),sum(bands))
                for limit,base,sides in zip(limits,(49,44,44,68,61),(2,0,5,0,6)):
                    if value <= limit:
                        self.put_tile(x,y,base+(self.die(1,sides,'feature type') if sides else 0)); break

    def wall(self, x, y, direction):
        return RetainedCombat.wall(self,x,y,direction)

    def dungeon(self):
        self.data['tiles']=bytearray([22]*1250)
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
                t1=(22 if w==0 else 0 if op else 13) if n==0 else ((15 if op else 5) if w==0 else (18 if op else 2))
                t2=22 if n==0 else 17 if n==3 else 5
                t3=(22 if n==0 else 16 if op else 10) if w==0 else (20 if op else 7) if w==3 else (1 if op else 3)
                t4=(22 if n==0 else 23 if n==3 else 10) if w in (0,3) else (13 if n==0 else 21 if n==3 else 6)
                for i,j,t in ((1,0,t1),(2,0,t2),(1,1,t3),(2,1,t4)): put(i,j,t)
                ne,nn=self.wall(x,y-1,2),self.wall(x+1,y,0); op=ne==nn==0
                t1=(4 if ne==1 else 22) if n==0 else 15 if n==3 else 5
                t2=((22 if ne==0 else ((24 if nn else 7) if e==0 else 1) if ne==3 else ((11 if nn else 7) if e==0 else 3))
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

    def place(self, i, masks, counts, distance=None, plane=None):
        side, r = field(self.chars[i],'side') if plane is None else plane, self.record(i)
        occupied={cell:j for j in range(len(self.chars)) if j!=i for cell in self.cells(j)}
        q = (self.s.dir+4*side)%8//2
        distance = self.s.r1[0x2C1] if distance is None else distance
        anchor = (distance*DX[self.s.dir]*side,distance*DY[self.s.dir]*side)
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
                occupant,tile = self.probe(i,8,occupied)
                if occupant < 0 and tile and self.terrain(tile) < 255:
                    masks[side][ring][y*11+x] = 0
                    return True
        raise BindingRequired('Death Knights placement search did not terminate')

    def setup(self):
        self.game.battle = self
        self.s.mode = 5
        self.s.g['dkk.battle'] = dict(active=True,round=0,limit=15,actors=[],order=[],cursor=0,bank=[],messages=[],actor=-1,view=(0,0),
            downed=[(0,0,0)]*8,downed_who=[-1]*8,downed_count=0,yell=-1,treasure_boundary=None,roll=dict(getattr(self.game,'roll_memo',{}),attack=0),morale=getattr(self.game,'morale_memo',0),in_move_menu=False,extended_mode=0,cursor_active=False)
        prior_targets = getattr(self.game, 'combat_target_slots', ())
        if prior_targets:
            self.data['target_list'] = list(prior_targets)
        if not hasattr(self.game,'combat_log'): self.game.combat_log = []
        self.leadership()
        runtime = self.s.g.setdefault('dkk.runtime',{})
        runtime.update(slow_text=0,picture_name='',picture_id=255,big_id=255)
        dungeon = self.game.vm.is3d()
        sheet = getattr(self.game,'combat_tile_frames',None)
        load_tiles = sheet is None or not dungeon or not runtime.get('dungeon_combat_loaded')
        self.game.ask('ACK', ('Continue',), prompt='', timed=1, message_colour=10,
                      after_pause=self.game.assets.text('battleBegins'), flush_keys=load_tiles,
                      discard_pending_reads=3 + len(self.chars))
        self.s.r1[0x333] = 0
        if load_tiles:
            family, count = ('DUNGCOM',25) if dungeon else ('WILDCOM',38)
            frames = decode(self.game.assets.records(family)[1]).parts[0].frames
            if sheet is None: sheet = ((bytes(24),)*24,)*40
            self.game.combat_tile_frames = frames[:count] + sheet[count:]
            runtime.update(dungeon_combat_loaded=int(dungeon),wilderness_combat_loaded=0)
        self.data.update(cursor_active=False,cursor_size=1)
        self.dungeon() if dungeon else self.wilderness()
        face = self.t['facing'][self.s.dir//2]
        for i,c in enumerate(self.chars):
            self.recalc(c)
            r = dict(x=0,y=0,size=0,initiative=0,movement=0,phase=0,sweep=0,guard=0,attacked=0,
                     facing=(face+4*field(c,'side'))%8,target=-1,overkill=0,flanks=0,spread=0,turned=0,
                     turns=0,fleeing=0,stance=0,casting=0,cast_ok=False,item_ok=False,outsider=int(i >= self.s.r1[0x33E]))
            morale = field(c,'npc')&127
            if field(c,'side') == 0 and r['outsider'] and (not morale or morale > 102): put(c,'npc',self.s.r1[0x2C6]+128)
            self.data['actors'].append(r)
        self.place_all()
        self.game.vm.clear_text(); self.game.vm.display = {'kind':None,'misc_info':''}
        self.event('setup',roster=[(c.rid,name(c),field(c,'hp')) for c in self.chars],positions=[(r['x'],r['y']) for r in self.data['actors']],terrain_hash=hashlib.sha256(self.data['tiles']).hexdigest())
        x,y = self.position(0)
        self.data.update(view=(x-3,y-3),panel=-1)
        self.scroll(x,y,255)
        draw_entry = getattr(self.game,'draw_combat_entry',None)
        if draw_entry is not None: draw_entry(self)
        for i in range(len(self.chars)): self.trigger(8,i); self.trigger(22,i)
        self.hp_percent()
        self.data.update(in_move_menu=False,cursor_active=False,extended_mode=0)
        self.s.mode = 5

    def recalc(self, char): return rules.recalc_stats(char,self.s.r1[0x372])

    def placement_masks(self):
        masks = []
        for side in (0,1):
            rings = []
            for ring in range(4):
                q = 4 if ring == 1 else (self.s.dir+4*side)%8//2
                rings.append([int(self.t['bands'][q*12+y*2] <= x <= self.t['bands'][q*12+y*2+1]) for y in range(6) for x in range(11)])
            masks.append(rings)
        return masks

    def place_all(self):
        self.body_state()
        flags = self.s.g.get('combat.direction_flags',0)
        if flags and not flags&15: raise BindingRequired('Death Knights placement has no allowed direction')
        teams = self.data['setup_teams'] = self.teams()
        directions = max(1,(flags&15).bit_count())*2
        counts = [(teams[0]+1)//2,(teams[1]+directions-1)//directions]
        original,previous,rotation,i = self.s.dir,None,0,0
        try:
            while i < len(self.chars):
                c,r = self.chars[i],self.record(i)
                side = field(c,'side')
                if flags and side:
                    rotation = next((rotation+step)%4 for step in range(1,5) if flags&(1<<((rotation+step)%4)))
                    self.s.dir = rotation*2
                else: self.s.dir = original
                plane = 1 if flags and previous not in (None,self.s.dir) else side
                if previous != self.s.dir:
                    masks = self.placement_masks()
                    distance = self.s.r1[0x2C1] or int(self.s.dir != original)
                    if getattr(self.game,'demo_mode',False): distance = 2
                    previous = self.s.dir
                r.update(size=field(c,'dimensions')&7,facing=self.t['facing'][(self.s.dir+4*side)%8//2])
                placed = not (getattr(self.game,'duel_flag',False) and not field(c,'active')) and self.place(i,masks,counts,distance,plane)
                if not placed:
                    r['size'] = 0
                    if r['outsider']:
                        self.event('unplaced',actor=i,monster=c.rid)
                        self.s.party.pop(i) if i < len(self.s.party) else self.s.monsters.pop(i-len(self.s.party)); self.data['actors'].pop(i)
                        self.s.g['dkk.monster_icons'] = [(j-(j>i),*entry) for j,*entry in self.s.g.get('dkk.monster_icons',[]) if j!=i]
                        continue
                elif not field(c,'active'):
                    r['size'] = 0
                    if not r['outsider']:
                        self.record_body(i,self.resolve_terrain(r['x'],r['y']))
                        self.put_tile(r['x'],r['y'],31)
                i += 1
        finally: self.s.dir = original

    def leadership(self):
        for char in self.chars:
            put(char, 'auto_combat', int(field(char, 'side') == 1 or field(char, 'npc') > 127))
        used = False
        for leader in self.chars:
            if field(leader, 'side') or field(leader, 'npc') > 127 or field(leader, 'levels', 7, signed=True) <= 0 or field(leader, 'status'): continue
            for char in self.chars:
                if field(char, 'side') or field(char, 'npc') <= 127 or not field(char, 'auto_combat') or field(char, 'status') or field(char, 'abilities', 3) <= 3: continue
                order = field(leader, 'knight_order')
                if order not in (1, 2, 3): raise BindingRequired('DKK leadership order has an unset base')
                bonus = (5 * max(0, field(leader, 'abilities', 11) - 13)) & 255
                chance = (20, 40, 80)[order - 1] + bonus
                if chance > self.die(1, 100, 'knight leadership', self.index(leader), self.index(char)):
                    put(char, 'auto_combat', 0)
                    if not used:
                        self.message('Using leadership ability')
                        self.message(name(leader)+' leads '+name(char)+'.')
                    used = True
        if used: self.game.ask('ACK', ('Continue',), prompt='Using leadership ability')

    def index(self, char): return next(i for i,c in enumerate(self.chars) if c is char)
    def position(self, i): return self.record(i)['x'], self.record(i)['y']
    def direction(self, a, b): return direction_to(*self.position(a),*self.position(b))
    def drawing(self): return self.data.get('gfx',True)
    def turn_view(self, i):
        self.data['gfx']=field(self.chars[i],'side')==0 or self.visible(i)
        self.centered_view(i,2,True)
    def terrain_view(self, char):
        i = self.index(char)
        if not self.visible(i,True) or not self.drawing(): self.center(i,255)
    def centered_view(self, i, margin=2, cursor=False):
        self.data.update(cursor_active=cursor,cursor_size=self.record(i)['size'])
        try:
            if self.drawing(): self.center(i,margin)
        finally: self.data.update(cursor_active=False,cursor_size=1)
    def face(self, i, direction, frame=0, erase_only=False):
        actor = self.record(i)
        if self.drawing():
            if not self.visible(i,True): self.center(i,3)
            if direction//4 != actor['facing']//4 or frame or erase_only:
                self.erase_footprint(i)
        actor['facing'] = direction
        if not erase_only and self.drawing() and self.visible(i):
            if frame == 1: self.attack_poses[i] = direction
            else: self.attack_poses.pop(i, None)
            present = getattr(self.game, 'present_combat_pose', None)
            if present is not None: present(self, i, frame)

    def finish_attack_pose(self, i):
        if self.visible(i):
            direction = self.record(i)['facing']
            self.face(i, direction, frame=1, erase_only=True)
            self.face(i, direction)

    def center(self, i, margin=2): return self.scroll(*self.position(i),margin)
    def visible_cells(self, cells):
        ox, oy = self.data['view']
        return tuple((x,y) for x,y in cells if ox <= x < ox+7 and oy <= y < oy+7)

    def erase_footprint(self, i):
        self.attack_poses.pop(i, None)
        draw = getattr(self.game, 'draw_combat_cell', None)
        if draw is not None:
            cells = self.visible_cells(self.cells(i))
            if cells: draw(self, cells, False, -1)

    def redraw_cell(self, x, y, *, cursor=False):
        draw = getattr(self.game, 'draw_combat_cell', None)
        if draw is None and not self.attack_poses: return
        occupant, _ = self.contents(x, y)
        self.attack_poses.pop(occupant, None)
        if draw is None: return
        if cursor:
            size = self.data.get('cursor_size', 1)
            cells = [(x+dx, y+dy) for dx, dy in self.footprint(size)]
        else:
            cells = self.cells(occupant) if occupant >= 0 else [(x, y)]
        cells = self.visible_cells(cells)
        if occupant >= 0 and not self.visible(occupant): occupant = -1
        draw(self, cells, cursor and self.data.get('cursor_active', False), occupant)

    def redraw_view(self):
        self.attack_poses.clear()
        draw = getattr(self.game, 'draw_combat_cell', None)
        if draw is None: return
        ox, oy = self.data['view']
        terrain = tuple((x, y) for y in range(oy, oy+7) for x in range(ox, ox+7))
        draw(self, terrain, False, -1)
        for i, char in enumerate(self.chars):
            if field(char, 'active') and self.visible(i):
                draw(self, (), False, i)

    def scroll(self, x, y, margin=2, direction=8):
        source = x,y
        x,y = x+DX[direction],y+DY[direction]
        ox,oy = self.data['view']
        forced = margin==255
        if forced: margin=0
        changed = forced or abs(x-ox-3)>margin or abs(y-oy-3)>margin
        if abs(x-ox-3)>margin: ox = max(0,min(43,x-3))
        if abs(y-oy-3)>margin: oy = max(0,min(18,y-3))
        self.data['view'] = ox,oy
        if changed: self.redraw_view()
        self.redraw_cell(*source)
        if not (ox<=x<ox+7 and oy<=y<oy+7):
            x,y = max(0,min(49,x)),max(0,min(24,y))
        self.redraw_cell(x,y,cursor=True)
        flush = getattr(self.game, 'flush_combat_view', None)
        if flush is not None: flush(self)
        return changed
    def moving_icon(self, sx, sy, ex, ey):
        sx,sy,ex,ey = max(0,min(49,sx)),max(0,min(24,sy)),max(0,min(49,ex)),max(0,min(24,ey))
        sign = lambda v: (v>0)-(v<0)
        cx,cy,tx,ty = sx*3,sy*3,ex*3,ey*3
        adx,ady,stx,sty,err,path = abs(tx-cx),abs(ty-cy),sign(tx-cx),sign(ty-cy),0,[]
        while True:
            dx = dy = 0
            if adx >= ady and cx != tx:
                cx += stx; dx = stx; err += 2*ady
                if err >= adx: err -= 2*adx; cy += sty; dy = sty
            elif adx < ady and cy != ty:
                cy += sty; dy = sty; err += 2*adx
                if err >= ady: err -= 2*ady; cx += stx; dx = stx
            path.append((dx,dy))
            if not dx and not dy: break
        if len(path) < 4: return
        count = len(path)-2
        inside = lambda x,y: 0 <= x-self.data['view'][0] <= 6 and 0 <= y-self.data['view'][1] <= 6
        last,camera = True,(self.data['view'][0]+3,self.data['view'][1]+3)
        if not inside(sx,sy) or not inside(ex,ey):
            if abs(ex-sx) <= 6 and abs(ey-sy) <= 6: camera = sx+int((ex-sx)/2),sy+int((ey-sy)/2)
            else: last = False
        self.scroll(*camera,255)
        at = ax = ay = 0
        for _ in range(64):
            ox,oy = self.data['view']
            px,py = (sx-ox)*3+ax,(sy-oy)*3+ay
            while True:
                dx,dy = path[at]; px += dx; py += dy; at += 1
                out = not (0 <= px <= 18 and 0 <= py <= 18)
                if not out and at < count:
                    ax += dx; ay += dy
                    if abs(ax) == 3: sx += sign(ax); ax = 0
                    if abs(ay) == 3: sy += sign(ay); ay = 0
                if at >= count or out: break
            if at >= count:
                if not inside(ex,ey): self.scroll(ex,ey,3)
                return
            ax = ay = 0; sx,sy = ex,ey
            self.scroll(ex+(ex-49 if ex+3 > 49 else 3-ex if ex < 3 else 0),ey+(ey-24 if ey+3 > 24 else 3-ey if ey < 3 else 0),255)
            ox,oy = self.data['view']
            px,py,at = (ex-ox)*3,(ey-oy)*3,count
            while True:
                if at < 0: raise BindingRequired('Death Knights moving icon walked back past its start')
                dx,dy = -path[at][0],-path[at][1]; px += dx; py += dy
                if px > 18: sx = ox+6
                elif px < 0: sx = ox
                if py > 18: sy = oy+6
                elif py < 0: sy = oy
                if not (0 <= px <= 18 and 0 <= py <= 18): break
                ax += dx; ay += dy
                if abs(ax) == 3: sx += sign(ax); ax = 0
                if abs(ay) == 3: sy += sign(ay); ay = 0
                at -= 1
        raise BindingRequired('Death Knights moving icon never reached its end')
    def visible(self, i, whole=False):
        ox,oy = self.data['view']
        seen = [ox<=x<ox+7 and oy<=y<oy+7 for x,y in self.cells(i)]
        return bool(seen) and (all(seen) if whole else any(seen))
    @contextmanager
    def preserve_target_list(self):
        slots = list(self.data.get('target_list', ()))
        distance = self.first_target_distance
        try:
            yield
        finally:
            self.data['target_list'] = slots
            self.first_target_distance = distance

    def distance(self, a, b):
        with self.preserve_target_list():
            entries = self.spans(self.cells(a), ignore=True)
            if not entries:
                return self.first_target_distance
            return next((distance for j,distance,_ in entries if j == b), entries[-1][1]) // 2
    def disabled(self, i): return any(has(self.chars[i],k) for k in self.game.assets.table('helplessEffects'))
    def weapon(self, i):
        w = rules.worn(self.chars[i])[0]
        return w.data if w is not None else None
    def named(self, i):
        from .shop import item_name
        if self.weapon(i) is not None: item_name(self.game, self.weapon(i))
    def panel(self, i):
        c = self.chars[i]; self.named(i); weapon = self.weapon(i)
        self.data['panel'] = i; self.data['panel_hp'] = field(c,'hp'); self.data['panel_due'] = False
        self.data['panel_print'] = dict(hp=field(c,'hp'),hp_max=field(c,'hp_max'),ac=field(c,'ac'),active=field(c,'active'),side=field(c,'side'),level_up_ready=field(c,'level_up_ready'),status=field(c,'status'),helpless=self.disabled(i),casting=self.record(i)['casting'],weapon=bytes(weapon) if weapon is not None else None)
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

    def clear_message_window(self, *, bottom=False):
        self.data['messages'].clear()
        clear = getattr(self.game, 'clear_combat_text', None)
        if clear is not None: clear(self, bottom=bottom)

    def show(self, kind, **entry):
        panel = self.data.get('panel', -1)
        entry.update(kind=kind, panel=panel, view=tuple(self.data['view']),
                     actors=tuple((r['x'],r['y'],r['size']) for r in self.data['actors']))
        if panel >= 0 and 'panel_print' in self.data:
            entry['panel_print'] = self.data['panel_print'].copy()
        self.game.__dict__.setdefault('combat_report', []).append(entry)

    def name_colour(self, j):
        c=self.chars[j]
        return 12 if not field(c,'active') else 14 if field(c,'side') else 11

    def show_attack(self, i, j, manner, hit, shown, colour):
        t=self.game.assets.text
        lead={2:t('backstabsText'),3:t('slaysHelplessText')}.get(manner,t('attacksText'))
        text=t('fromBehindText') if manner==1 else ''
        if hit: text=t('cruelBlowText') if manner==3 else text+'Hitting for %d'%shown+t('damagePointText' if shown==1 else 'damagePointsText').rstrip()+t('damageSuffix')
        else: text+=t('missesText')
        a,b=self.chars[i],self.chars[j]
        if field(b,'status') == 8: text = ''
        entry=dict(attacker=name(a),attacker_colour=self.name_colour(i),lead=lead,target=name(b),target_colour=colour,result=text)
        if i in self.attack_poses: entry.update(actor=i, facing=self.attack_poses[i])
        self.show('attack',**entry)
        if not field(b,'active'):
            status=field(b,'status')
            self.show('attack',down='' if field(b,'target_flags')&8 else 'Dying' if status==5 else 'killed' if status in (6,7,8) else '',**entry)
    def ask(self, kind, options, **info):
        with self.preserve_target_list():
            return self.game.ask(kind.value, options, actor=self.data['actor'], round=self.data['round'], **info)
    def pause(self, **info):
        messages = self.data['messages']
        return self.ask(Kind.ACK,('Continue',),prompt=messages[-1] if messages else '',timed=1,**info)
    def bottom_line(self, text):
        self.ask(Kind.ACK, ('Continue',), prompt=text, timed=1, message_colour=10, after_pause=' ')
    def name_anim(self, c, hit=False):
        i=self.index(c)
        if not self.visible(i,True): self.scroll(*self.position(i),3)
        return self.pause(anim=i,**({'hit':1} if hit else {}))
    def end(self, i, guard=False):
        r = self.record(i)
        r.update(initiative=0,movement=0,casting=0,guard=int(guard and not r['turned']))
        if r['guard']: self.bottom_line(self.game.assets.text('guardingText'))
        return True
    def hp_percent(self):
        total = sum(field(c,'hp_max') for c in self.chars if field(c,'side') == 1)&65535
        current = sum(field(c,'hp') for c in self.chars if field(c,'side') == 1 and field(c,'active'))&65535
        if total: self.data['hostile_hp'] = ((current*20)&65535)//total*5

    def context(self, attacker=None, **values):
        values.setdefault('spell',self.data.get('current_spell',0))
        values.setdefault('multi_target',self.data.get('multi_target',0))
        values.setdefault('save_passed',self.data.get('save_passed',False))
        values.setdefault('morale',self.data.get('morale',0))
        for key in ('effect','damage','element','dice_count'): values.setdefault(key,self.data.get('roll',{}).get(key,0))
        def bank(c, raw):
            self.data['bank'].append((self.index(c),raw))
            self.event('disarm',actor=self.index(c),item_type=raw[I['type']])
            self.message(name(c)+' loses a weapon')
        return effects.Roll(attacker=attacker,in_combat=True,services={
            'in_aura_range':lambda a,b,r:self.span(self.cells(self.index(a)),self.index(b),r) is not None,
            'distance':lambda a,b:self.distance(self.index(a),self.index(b)),
            'damaging_weapon':lambda c:self.ammo(self.index(c))[1] or self.weapon(self.index(c)),
            'bank_weapon':bank, 'clear_weapon':self.recalc,
            'unready_item':self.unready,
            'neighbours':lambda c:[self.chars[i] for i in self.near(self.index(c))],
            'saving_throw':lambda c,k,b:self.save(self.index(c),k,b),
            'clear_target':lambda c:self.record(self.index(c)).update(target=-1),
            'replace_spell_targets':self.replace_spell_targets,
            'set_turned':lambda c,v:self.record(self.index(c)).update(turned=v),
            'add_with_message':lambda c,k,t,v,m:self.add_effect(c,k,t,v,m),
            'end_actions':lambda c:self.end(self.index(c)),
            'block_casting':lambda c:self.record(self.index(c)).update(cast_ok=False,item_ok=False),
            'terrain_view':self.terrain_view,
            'bottom_line':self.message,
            'pause':self.pause,
            'name_anim':self.name_anim,
            'clear_cloud':lambda c,n:self.clear_cloud(self.index(c),n),
            'caster_level':lambda ident:self.game.vm.service('magic', 'caster_level', attacker, ident),
        },**values)

    def unready(self, char, item):
        from .inventory import toggle_ready
        facade = EffectGame(self,'unready effect',self.index(char))
        facade.weapon = item
        self.held = self.weapon(self.index(char))
        try: toggle_ready(facade,char,item)
        finally: self.held = None

    def weapon_effect(self, c, kind, node, removed, context=None, weapon=None):
        i, x = self.index(c), context or self.context(c)
        target = self.record(i)['target']
        if kind == 7:
            item = getattr(self,'held',None)
            if item is None: item = self.weapon(i)
            close = self.distance(i, target) < 2
            view = rules.record(c)
            x.damage = self.die(1, 6 if close else 4, 'fixed weapon damage', i, target) + (item[I['bonus']] if item is not None else 0) + (rules._damage_strength(view) + 2 if close else 1)
            put(c, 'thac0', field(c, 'base_thac0') + (rules._hit_strength(view) if close else rules._dex_missile(view)))
        elif kind == 26:
            if target >= 0 and field(self.chars[target], 'creature_type') & 128: x.attack += 1
        elif kind == 47:
            if x.attacker is not None and field(x.attacker, 'creature_type') & 4: x.attack -= 4
        elif kind == 105:
            if target >= 0 and field(self.chars[target], 'creature_type') & 8: x.damage += field(c, 'levels', 4)
        elif kind in (93, 103):
            attacker = self.index(x.attacker)
            item = self.ammo(attacker)[1]
            if item is None: item = self.weapon(attacker)
            if kind == 93:
                if item is not None and self.base(item)[7] <= 1: x.damage //= 2
            elif (item is None or not item[I['bonus']]) and (field(x.attacker, 'race') < 7 or field(x.attacker, 'highest_level', signed=True) < 4): x.damage = 0
        elif kind == 106:
            candidates = [j for j in self.targets(i, 1) if not has(self.chars[j], 108)]
            scored = [(field(self.chars[j], 'thac0') + field(self.chars[j], 'attacks_left') *
                       (6 * field(self.chars[j], 'damage_rolls') + field(self.chars[j], 'damage_bonus', signed=True)), j) for j in candidates]
            if scored:
                score = max(value for value, _ in scored)
                if score > 0:
                    j = next(j for value, j in scored if value == score)
                    saved = self.save(j, 3)
                    self.add_with_message(j, 108, 0, 0, True, self.game.assets.text('blindedBySmokeText'), saved, 1)

    def near(self, i):
        return self.targets(i,1,allies=True)[1:]

    def explode(self):
        if self.data.get('explosions'): raise BindingRequired('Death Knights queued explosions are unverified')

    def add_with_message(self, j, kind, minutes, strength, on_remove, text, saved=False, negates=0):
        c=self.chars[j]; actor=self.data['actor']
        x=self.context(self.chars[actor] if actor>=0 else c,effect=kind); self.trigger(9,j,x)
        c=getattr(x,'target',c); j=self.index(c)
        if not x.effect or saved and negates==1: self.message(name(c)+' '+self.game.assets.text('unaffectedMessage')); self.pause(); return
        node=effects.has_effect(c,kind)
        if node is not None and node[1]|node[2]<<8: effects.remove_effect(EffectGame(self,'replace effect',j),c,kind,node)
        effects.add_effect(c,kind,minutes,strength,on_remove)
        if text: self.message(name(c)+' '+text); self.name_anim(c)

    def flee_control(self, j):
        raise BindingRequired('Death Knights combat.flee_control is unverified')

    def frighten(self, i):
        raise BindingRequired('Death Knights combat.frighten is unverified')

    def confusion(self, i):
        raise BindingRequired('Death Knights combat.confusion is unverified')

    def berserk(self, i, kind, node):
        raise BindingRequired('Death Knights combat.berserk is unverified')

    def gate_in(self, i):
        raise BindingRequired('Death Knights combat.gate_in is unverified')

    def monster_breath(self, i, kind, node, context):
        raise BindingRequired('Death Knights combat.monster_breath is unverified')

    def trigger(self, condition, i, context=None):
        c, x = self.chars[i], context or self.context(self.chars[i])
        current = [c]; previous = x.services.get('redirect_target')
        x.services['redirect_target'] = lambda target:current.__setitem__(0,target)
        try:
            if condition in (6,9): effects.check_spell_resistance(EffectGame(self,'magic resistance',i),c,x)
            for kind in effects.CONDITIONS.get(condition,()):
                c=current[0]; target=self.index(c)
                node = effects.has_effect(c,kind)
                if node is None and kind in effects.AURA_IDS: node = effects.aura_node(self.game,c,kind,x)
                if node is None: continue
                effects.call_handler(EffectGame(self,'effect %d'%kind,self.index(x.attacker) if x.attacker is not None else target,target),c,kind,node,False,x)
                x.save &= 255; x.damage &= 255; x.attack = signed(x.attack); x.morale &= 255
        finally:
            if previous is None: x.services.pop('redirect_target',None)
            else: x.services['redirect_target']=previous
        x.target=current[0]
        self.remember_roll(x)
        return x

    def replace_spell_targets(self, before, after):
        targets=getattr(self.game,'spell_targets',None)
        if targets is None: raise BindingRequired('Death Knights spell target list is not bound')
        for at,target in enumerate(targets):
            if target is before: targets[at]=after

    def remember_roll(self, context):
        self.game.roll_memo = self.data['roll'] = {key:getattr(context,key) for key in ('effect','damage','element','dice_count')}
        self.game.morale_memo = self.data['morale'] = context.morale

    def add_effect(self, c, kind, minutes, strength, message):
        effects.add_effect(c,kind,minutes,strength,False); self.message(name(c)+' '+message)
    def valid_location(self, i, x, y, moving=False):
        if not self.s.g.get('dkk.battle',{}).get('active'): return True
        r = self.record(i)
        occupied=self.occupancy()
        r.update(x=signed(x&255),y=signed(y&255),size=field(self.chars[i],'dimensions')&127)
        occupant,tile = self.probe(i,8,occupied)
        if occupant>=0 or not tile or self.terrain(tile)==255:
            r['size']=0
            self.data['stale'] = []
            live = self.occupancy()
            self.data['stale'] = [(cx,cy,j) for (cx,cy),j in occupied.items() if live.get((cx,cy)) != j]
            return False
        if moving and not r['outsider']:
            bodies,owners,count = self.body_state()
            for k,owner in enumerate(owners[:count]):
                if owner!=i: continue
                if bodies[k][2]!=31: tile=bodies[k][2]
                bodies[k],owners[k]=(0,0,0),-1
            if not any(owner>=0 and (body[0],body[1])==(r['x'],r['y']) for body,owner in zip(bodies[:count],owners[:count])):
                self.put_tile(r['x'],r['y'],tile)
        self.data.pop('stale',None)
        return True
    def remove_effect(self, i, kind):
        effects.remove_effect(EffectGame(self,'remove effect %d'%kind,i),self.chars[i],kind)
    def strip(self, i):
        for k in effects._hp_zero_ids(self.game): self.remove_effect(i,k)
        c = self.chars[i]
        if has(c,77) and field(c,'npc') == 179: put(c,'side',0)
    def save(self, i, kind, bonus=0, element=None):
        self.data['save_passed'] = True
        c = self.chars[i]; value = self.die(1,20,'saving throw',i)
        if has(c,57): value = 1
        if value in (1,20):
            self.data['save_passed'] = value == 20
            return self.data['save_passed']
        if field(c,'levels',5,signed=True)>0 and field(c,'robe_order'):
            moon = self.s.r0[field(c,'robe_order')+0x1F8]
            bonus += -1 if moon == 0 else 1 if moon == 2 else 0
        actor = self.data['actor']
        x = self.context(self.chars[actor] if actor>=0 else c,save=(value+field(c,'save_bonus',signed=True)+signed(bonus))&255,save_type=kind,**({} if element is None else {'element':element}))
        self.trigger(12,i,x)
        self.data['save_passed'] = field(c,'saves',kind) <= x.save&255
        return self.data['save_passed']

    def walk(self, x, y, tx, ty, reach=255, ignore=False):
        ceiling = (2*(reach&65535)+1)&65535
        height = self.raw_terrain(x,y,1,ignore)
        for px,py,distance in line(x,y,tx,ty):
            if distance>ceiling or not ignore and self.raw_terrain(px,py,2)>height:
                return False,(px,py),distance
        return True,(tx,ty),distance

    def span(self, origins, j, reach=255, ignore=False, direction=255):
        best = None
        for tx,ty in self.cells(j):
            for x,y in origins:
                if not in_cone(x,y,tx,ty,direction): continue
                reached,point,distance = self.walk(x,y,tx,ty,reach,ignore)
                if reached and (best is None or distance<best[0]):
                    bearing = direction if direction<8 else next(d for d in range(8) if in_cone(x,y,tx,ty,d))
                    best = distance,bearing
        return best

    def spans(self, origins, reach=255, ignore=False, direction=255):
        entries = []
        for j in range(len(self.chars)):
            best = self.span(origins,j,reach,ignore,direction)
            if best is not None: entries.append((j,*best))
        for a in range(len(entries)-1):
            for b in range(a+1,len(entries)):
                if entries[b][1] < entries[a][1] or entries[b][1] == entries[a][1] and entries[b][2] < entries[a][2] and entries[b][2]%2 <= entries[a][2]%2:
                    entries[a],entries[b] = entries[b],entries[a]
        self.remember_targets(entries)
        return entries

    def remember_targets(self, entries):
        slots = self.data.setdefault('target_list', [])
        slots[:len(entries)] = [j for j,_,_ in entries]
        if entries:
            self.first_target_distance = entries[0][1] // 2

    def targets(self, i, reach=255, allies=False, ignore=False):
        entries = self.spans(self.cells(i),reach,ignore)
        result = [j for j,*_ in entries if allies or field(self.chars[j],'side') != field(self.chars[i],'side')]
        if not allies and has(self.chars[i],91) and self.data['yell'] in result:
            p = result.index(self.data['yell']); result[0],result[p] = result[p],result[0]
        return result
    def count_targets(self, i, reach=255, same_side=False, ignore=False):
        side = field(self.chars[i],'side') ^ int(not same_side)
        entries = self.spans(self.cells(i), reach, ignore)
        matches = [entry for entry in entries if field(self.chars[entry[0]], 'side') == side]
        self.remember_targets(matches)
        result = [j for j,_,_ in matches]
        if has(self.chars[i],91) and self.data['yell'] in result:
            p = result.index(self.data['yell']); result[0],result[p] = result[p],result[0]
        return result
    def anchor_reach(self, i, j, reach):
        return self.walk(*self.position(i),*self.position(j),reach)[0]
    def can_target(self, i, j, allow_ally=True):
        if j is None or not 0 <= j < len(self.chars): return False
        if i == j: return True
        x = self.context(self.chars[i]); self.trigger(1,j,x)
        if x.target_veto or not allow_ally and field(self.chars[i],'side') == field(self.chars[j],'side'): return False
        r = self.record(i); previous = r['target']; r['target'] = j
        try: self.trigger(0,i,x)
        finally: r['target'] = previous
        return not x.target_veto
    def attack_targets(self, i):
        if not field(self.chars[i],'active') or not any(field(self.chars[i],'attacks_left',p) for p in (0,1)): return []
        ranged, usable = self.ranged(i),self.ammo(i)[0]
        reach = self.base(self.weapon(i))[12]
        if reach in (0,255): reach = 1
        near = self.targets(i,1)
        return [j for j in self.targets(i,reach) if list(line(*self.position(i),*self.position(j)))[-1][2]//2<=reach and self.can_target(i,j) and
                (not ranged or usable and (not near or self.throwable(i)))]
    def acquire(self, i, relaxed=False, reach=255, force=False, allies=False):
        r = self.record(i); j = r['target']
        if not force and j >= 0 and field(self.chars[j],'active') and field(self.chars[j],'side') != field(self.chars[i],'side') and self.can_target(i,j,allies): return True
        r['target'] = -1
        for ignore in (False,True):
            candidates = self.count_targets(i,reach,same_side=allies,ignore=ignore and not force)
            for attempt in range(20):
                if not any(j >= 0 for j in candidates): break
                k = 0 if not attempt and has(self.chars[i],91) and candidates[0] == self.data['yell'] else self.die(1,len(candidates),'acquire target',i)-1
                j = candidates[k]
                if j >= 0 and (relaxed and ignore and not force or self.can_target(i,j,allies)):
                    r['target'] = j; return True
                candidates[k] = -1
        return False

    def rate(self, i, value): return self.trigger(18,i,self.context(self.chars[i],multiplier=value)).multiplier&255
    def movement(self, i):
        return rules.movement(self.chars[i], self.s.r1[0x372])
    def reset_attacks(self, i):
        c,r = self.chars[i],self.record(i); available,ammo = self.ammo(i)
        ranged = self.ranged(i) and available
        rate = max(2,self.base(self.weapon(i))[5]) if ranged else field(c,'attacks')
        count = ((self.rate(i,rate)+(self.data['round']&1))&255)//2
        if ranged and ammo is not None and ammo[I['quantity']]: count = min(count,max(1,ammo[I['quantity']]))
        put(c,'attacks_left',min(count,field(c,'attacks_left')) if r['attacked'] else count)
    def begin_round(self):
        order = []
        for i,c in enumerate(self.chars):
            r = self.record(i); r.update(attacked=0,phase=1,sweep=0,casting=0,
                                         cast_ok=not any(self.tile(x,y)==29 for x,y in self.cells(i)),item_ok=True)
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
            while p < min(64,len(order)):
                a,b = self.record(i)['initiative'],self.record(order[p])['initiative']
                if a>b or a == b and self.die(1,2,'initiative tie',i,order[p]) == 1: break
                p += 1
            order.insert(p,i)
            del order[72:]
        self.data.update(order=order,cursor=0)
        self.event('initiative',order=tuple(order),values=tuple(r['initiative'] for r in self.data['actors']))

    def body_state(self):
        bodies=self.data.setdefault('downed',[]); owners=self.data.setdefault('downed_who',[])
        count=self.data.setdefault('downed_count',len(bodies))
        bodies.extend([(0,0,0)]*max(0,8-len(bodies)))
        owners.extend([-1]*max(0,8-len(owners)))
        return bodies,owners,count

    def record_body(self, i, ground):
        bodies,owners,count=self.body_state()
        if count>=8: raise BindingRequired('Death Knights downed storage overflow is unverified')
        bodies[count]=(*self.position(i),ground); owners[count]=i
        self.data['downed_count']=count+1

    def restore_body(self, i):
        bodies,owners,count=self.body_state()
        k=next((k for k,owner in enumerate(owners) if owner==i),-1)
        if k<0 or count==0: raise BindingRequired('Death Knights body removal outside the live list is unverified')
        self.put_tile(*bodies[k])
        for slot in range(k,count-1): bodies[slot],owners[slot]=bodies[slot+1],owners[slot+1]
        self.data['downed_count']=count-1

    def resolve_terrain(self, x, y):
        return self._terrain_under(x, y, self.tile(x, y))

    def _terrain_under(self, x, y, tile):
        if tile in (28,29):
            for cloud in self.data.get('clouds',()):
                for cx,cy,under in cloud['cells']:
                    if (cx,cy)==(x,y): tile=under
        elif tile==31:
            bodies = self.data.get('downed', ())
            for bx,by,under in bodies[:self.data.get('downed_count', len(bodies))]:
                if (bx,by)==(x,y): tile=under
        return tile

    def ground_picture(self, x, y):
        tile = self.tile(x, y)
        if 28 <= tile <= 31:
            under = self._terrain_under(x, y, tile)
            tile = self._terrain_under(x, y, under)
        return self.terrain(tile if 1 <= tile <= 69 else 21, 3)

    def down(self, i, *, creature_message=None):
        if not self.s.g.get('dkk.battle',{}).get('active'):
            raise BindingRequired('Death Knights noncombat down sound and pause are unbound')
        bodies,owners,count=self.body_state()
        if i in owners[:8]: return
        r=self.record(i)
        if not self.visible(i,True): self.center(i,3)
        self.erase_footprint(i)
        self.game.vm.queue_sound(5)
        cells = []
        for x, y in self.visible_cells(self.cells(i)):
            tile = self.tile(x, y)
            overlay = self.terrain(tile, 3) if 28 <= tile <= 31 else None
            cells.append((x, y, self.ground_picture(x, y), overlay))
        display = {'creature_message': creature_message} if creature_message is not None else {}
        self.show('fall', actor=i, cells=tuple(cells), picture=23, frames=(0, 1) * 4 + (0,), pace=10, **display)
        if not r['outsider']:
            x,y=self.position(i); under=self.resolve_terrain(x,y)
            self.record_body(i,under)
            if self.tile(x,y) not in (28,29): self.put_tile(x,y,31)
        self.pause(fall=1)
        self.erase_footprint(i)
        r['size'] = 0
        self.data.pop('stale',None)
        ox, oy = self.data['view']
        self.scroll(ox+3, oy+3, 3)
        r.update(initiative=0,movement=0,guard=0)

    def kill(self, i, status, message):
        c=self.chars[i]
        shown = self.creature_message(c, message, report=True)
        if field(c,'status') in (6,7,8): return
        put(c,'status',status); put(c,'active',0); put(c,'hp',0)
        self.strip(i); self.trigger(13,i)
        if not field(c,'active') and field(c,'status') != 10: self.down(i, creature_message=shown)
        self.ask(Kind.ACK, ('Continue',), timed=1, prompt='', **shown)
        self.clear_message_window()
    def damage(self, i, amount, x, nonweapon=False):
        c,r = self.chars[i],self.record(i)
        if not field(c,'active'): return
        x.damage=amount; self.remember_roll(x)
        hp = field(c,'hp'); remaining,overkill = max(0,hp-amount),max(0,amount-hp)
        status = 6 if overkill>9 or not remaining and field(c,'status') == 1 else 5 if overkill else 4 if not remaining else field(c,'status')
        put(c,'status',status); put(c,'hp',remaining if status in (0,1) else 0)
        if status not in (0,1):
            put(c,'active',0); r['initiative'] = 0
            if status == 5: r['overkill'] = overkill
        if amount:
            r['cast_ok'] = False
            if r.get('casting'):
                from .magic import forget
                self.event('spell interrupted',actor=i,spell=r['casting'])
                forget(c,r['casting']); self.message(name(c)+' '+self.game.assets.text('lostSpellMessage')); self.end(i)
        if status not in (0,1):
            if nonweapon:
                text = self.game.assets.text
                message = text('goesDown')
                if not field(c,'target_flags')&8:
                    if status == 5: message += text('dyingSuffix')
                    elif status in (6,7,8): message = text('killedMessage')
                self.message(name(c)+' '+message)
            self.strip(i); self.trigger(13,i,x)
            if not field(c,'active') and field(c,'status') != 10: self.down(i)
        self.event('damage',actor=self.index(x.attacker),target=i,amount=amount,hp=field(c,'hp'),status=field(c,'status'))
    def note_direction(self, i, j):
        r = self.record(j); d = (self.direction(j,i)-r['facing'])%8
        r['flanks'] = (r['flanks']+1)&255; r['spread'] = (r['spread']+min(d,8-d))%8
    def backstab(self, i, j):
        a,t = self.chars[i],self.chars[j]; w = self.weapon(i)
        allowed = w is None or w[I['type']] in (3,4,17,18,19,67)
        return (allowed and (field(a,'levels',6) or earlier_class(a) and field(a,'former_levels',6)) and
                self.record(j)['flanks']>1 and self.distance(i,j)<2 and field(t,'dimensions')&127 <= 1 and
                self.direction(i,j) == self.record(j)['facing'])
    def strike(self, i, j, missile=None):
        c,r = self.chars[i],self.record(i)
        if field(c,'attacks_left')<r['sweep'] and not field(self.chars[j],'highest_level') and self.distance(i,j) == 1:
            targets = self.count_targets(i,1)
            count = sum(not field(self.chars[k],'highest_level') for k in targets)
            if count>field(c,'attacks_left'):
                self.message(name(c)+' '+self.game.assets.text('sweepsText'))
                if targets[0] != j:
                    at = targets.index(j); targets[0],targets[at] = targets[at],targets[0]
                left = min(count,r['sweep'])
                for k in targets:
                    if left and not field(self.chars[k],'highest_level'):
                        self.note_direction(i,k); put(c,'attacks_left',1)
                        self.attack(i,k); left -= 1
                return self.end(i)
        self.note_direction(i,j)
        return self.attack(i,j,missile=missile)

    def confirm_ally(self, i, j):
        if field(self.chars[i],'side')!=field(self.chars[j],'side') or field(self.chars[i],'auto_combat'): return True
        if self.ask(Kind.CONFIRM,['Yes','No'],prompt=self.game.assets.text('attackAllyPrompt'),target=j,start=1)!=0: return False
        self.s.g['dkk.ally_attacked']=1; self.s.r1[0x333]=1
        return True

    def move_attack(self, i, j):
        if self.ranged(i) and not self.throwable(i):
            return False
        if not self.confirm_ally(i,j): return False
        self.record(i)['target']=j
        return self.strike(i,j)

    def attack(self, i, j, behind=False, missile=None):
        a,t,r,tr = self.chars[i],self.chars[j],self.record(i),self.record(j)
        self.data['gfx']=True
        self.data['limit'] = (self.data['round']+15)&255
        direction = tr['facing']
        if tr['flanks'] < 2 and not behind:
            direction = self.direction(j,i); tr['facing']=(direction+4)%8
        elif not behind and self.visible(j):
            tr['facing'] = (direction+4)%8
        if self.visible(j): self.face(j,direction)
        self.panel(i)
        self.face(i,self.direction(i,j),frame=1); r['target']=j
        for shot in (missile,self.weapon(i) if self.weapon(i) is not None and self.weapon(i)[I['type']] in (28,29) else None):
            if shot is not None:
                self.show('missile',actor=i,target=j,item=shot[I['type']],start=self.position(i),aim=self.position(j),**missile_art(shot[I['type']],self.direction(i,j)))
                self.moving_icon(*self.position(i),*self.position(j))
        if not any(field(a,'attacks_left',p) for p in (0,1)):
            self.end(i)
            self.finish_attack_pose(i)
            return True
        r['attacked'] = 1
        self.data.setdefault('roll',{})['damage']=0
        made = [0,0]; x = self.context(a)
        self.data.update(hits_made=0,hits_made_secondary=0,attacks_made=made)
        if self.disabled(j):
            phase = next(p for p in range(r['phase'],-1,-1) if field(a,'attacks_left',p))
            r['phase'] = phase; made[phase] += 1
            colour=self.name_colour(j); self.damage(j,(field(t,'hp')+5)&255,x); self.show_attack(i,j,3,True,0,colour)
            while has(a,25): self.remove_effect(i,25)
            put(a,'attacks_left',0); put(a,'attacks_left',0,1)
        else:
            w = self.weapon(i)
            if w is not None and (field(t,'dimensions')>128 or field(t,'dimensions')&7>1):
                base = self.base(w)
                put(a,'damage_rolls',base[2]); put(a,'damage_dice',base[3])
                put(a,'damage_bonus',field(a,'damage_bonus')-base[11]+base[4])
            self.recalc(t); self.trigger(11,j,x)
            back = self.backstab(i,j)
            rear = behind or tr['flanks']>1 and r['facing'] == tr['facing'] and tr['spread']>4
            ac = field(t,'ac',1)-4 if back else field(t,'ac',int(rear))
            distance = self.distance(i,j); band = (self.base(w)[12]-1)//3 if self.ranged(i) else distance
            ac = (ac+(2 if distance>band else 0)+(3 if distance>2*band else 0))&255
            landed = stopped = False
            for p in range(r['phase'],-1,-1):
                while field(a,'attacks_left',p) and not stopped:
                    put(a,'attacks_left',field(a,'attacks_left',p)-1,p); r['phase'] = p; made[p] += 1
                    while has(a,25): self.remove_effect(i,25)
                    natural = self.die(1,20,'attack',i,j); x = self.context(a,attack=100 if natural == 20 else natural)
                    if natural != 1: self.trigger(10,i,x); self.trigger(16,j,x)
                    modifier = signed(self.s.r1[0x371 if field(a,'side') == 0 else 0x370]&255)
                    hit = natural != 1 and x.attack>=0 and x.attack+field(a,'thac0')+modifier >= ac or self.disabled(j)
                    self.event('attack',actor=i,target=j,phase=p,natural=natural,roll=x.attack,thac0=field(a,'thac0'),modifier=modifier,defense=ac,hit=hit)
                    if hit:
                        landed = True
                        key = 'hits_made_secondary' if p else 'hits_made'
                        self.data[key] = (self.data[key]+1)&255
                        x.dice_count = field(a,'damage_rolls',p)
                        x.damage = (self.die(x.dice_count,field(a,'damage_dice',p),'damage',i,j)+field(a,'damage_bonus',p,signed=True))&255
                        self.trigger(4,i,x); self.trigger(5,j,x)
                        if back: x.damage *= (((field(a,'levels',6)+field(a,'former_levels',6)*earlier_class(a)-1)&65535)//4+2)
                        x.damage &= 255; x.element = 0
                        if field(t,'active'):
                            colour=self.name_colour(j)
                            self.message('%s hits %s for %d'%(name(a),name(t),x.damage),False); self.damage(j,x.damage,x)
                            self.show_attack(i,j,2 if back else 1 if rear else 0,True,x.damage,colour)
                        if field(t,'active') and x.damage: self.trigger(p+2,i,x)
                        if not field(t,'active'): stopped = True
                        if not field(a,'active'): put(a,'attacks_left',0,p)
                    self.explode()
            if not landed:
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
                from .inventory import remove_item
                remove_item(a,getattr(missile,'obj',missile),self.game)
        self.recalc(a)
        done = not field(a,'active') or not any(field(a,'attacks_left',p) for p in (0,1))
        if done: self.end(i)
        self.finish_attack_pose(i)
        return done


    def opportunity(self, i, direction):
        r = self.record(i)
        enemies = self.count_targets(i,1)
        if not enemies:
            return
        candidates = [j for j in enemies if not self.disabled(j) and not self.record(j)['turned'] and not has(self.chars[j],6)]
        r['x'] += DX[direction]; r['y'] += DY[direction]
        after = self.count_targets(i,1)
        r['x'] -= DX[direction]; r['y'] -= DY[direction]
        for j in candidates:
            if j in after or not field(self.chars[i],'active'): continue
            a,ar = self.chars[j],self.record(j); self.data['panel_due'] = True
            if not self.can_target(j,i) or self.ranged(j) and not self.throwable(j): continue
            facing = any(in_cone(*self.position(j),*self.position(i),d%8) for d in range(ar['facing']+6,ar['facing']+11))
            if ar['initiative']>0 or not ar['flanks'] or facing:
                p = next((p for p in (1,0) if field(a,'attacks_left',p)),0 if field(a,'attacks') else 1)
                if not field(a,'attacks_left',p): put(a,'attacks_left',1,p)
                ar['phase'],old = p,ar['target']
                self.attack(j,i,behind=True); ar['target'] = old
                if field(self.chars[i],'active'): self.panel(i)

    def move(self, i, direction, ai=False):
        c,r = self.chars[i],self.record(i); occupant,tile = self.probe(i,direction); had = r['movement']
        cost = (self.terrain(tile)*(3 if direction%2 else 2))&255
        if not tile or occupant >= 0 or self.terrain(tile) == 255 or cost>r['movement']: return False
        self.face(i,direction); self.opportunity(i,direction)
        if not field(c,'active'): self.end(i); return True
        if r['movement']:
            x,y = signed(r['x']+DX[direction]),signed(r['y']+DY[direction])
            debit = (self.raw_terrain(x,y,0)*(3 if direction%2 else 2))&255
            r['movement'] = max(0,r['movement']-debit)
            ox,oy=self.data['view']
            if self.drawing() and field(c,'auto_combat') and not (ox<=x<ox+7 and oy<=y<oy+7): self.center(i,2)
            if self.drawing(): self.erase_footprint(i)
            r.update(x=x,y=y); self.data.pop('stale',None)
            if self.drawing(): self.center(i,3 if field(c,'auto_combat') else 1)
            r.update(flanks=0,spread=0)
            self.event('move',actor=i,x=x,y=y,cost=debit,left=r['movement']); self.show('move',actor=i,left=had>>1 if ai else None)
            for j in self.count_targets(i,1):
                if field(c,'active') and self.record(j)['guard'] and not self.disabled(j):
                    self.center(i,2)
                    self.record(j)['guard'] = 0; self.note_direction(j,i); self.attack(j,i)
            if not field(c,'active') or self.disabled(i): r['movement'] = 0
        if not field(c,'active') or ai and self.disabled(i): self.end(i)
        self.terrain_effects(i,moved=True)
        if not ai and self.disabled(i): self.end(i)
        return True

    def out_of_play(self, i, status, text):
        c = self.chars[i]
        if not field(c,'active'): return
        self.centered_view(i,3)
        self.pause_creature_message(c, text)
        put(c,'active',0); put(c,'status',status)
        if status != 3: put(c,'hp',0)
        self.erase_footprint(i)
        self.record(i)['size'] = 0; self.data.pop('stale',None)
        self.end(i); self.strip(i)

    def flee(self, i):
        enemies = self.count_targets(i); own = speed = 0
        if enemies:
            own = self.movement(i)//2
            speed = max((self.movement(j)//2 for j,c in enumerate(self.chars) if field(c,'active') and field(c,'side') != field(self.chars[i],'side')),default=0)
        success = not enemies or own>speed or own == speed and self.die(1,2,'escape',i) == 1
        if success:
            self.out_of_play(i,3,self.game.assets.text('gotAwayText'))
        else:
            self.bottom_line(self.game.assets.text('escapeBlockedText'))
        self.event('flee',actor=i,own=own,enemy=speed,escaped=success)
        return self.end(i)

    def morale(self, i):
        c,r = self.chars[i],self.record(i); r['fleeing'] = int(bool(r['turned']))
        if r['turned']:
            self.pause_creature_message(c, self.game.assets.text('forcedToFlee')); return False
        if field(c,'npc')<=127: return False
        value = (field(c,'npc')&127)*2
        if value>102: value = 0
        own = self.trigger(17,i,self.context(c,morale=value)).morale
        loss = 100-field(c,'hp')*100//field(c,'hp_max')
        group = None
        holds = bool(own and own>=loss)
        if not holds:
            group = self.trigger(17,i,self.context(c,morale=self.data['hostile_hp'])).morale
            holds = bool(group and group>=100-self.s.r1[0x2C6] and field(c,'side'))
        self.event('morale',actor=i,own=own,loss=loss,group=group,threshold=100-self.s.r1[0x2C6],holds=holds)
        if holds: return False
        speed = max((self.movement(j)//2 for j,other in enumerate(self.chars) if field(other,'active') and field(other,'side') != field(c,'side')),default=0)
        if speed <= self.movement(i)//2:
            r['fleeing'] = 1
        elif field(c,'abilities',3)>5:
            self.out_of_play(i,4,self.game.assets.text('surrenders'))
            self.event('surrender',actor=i); return True
        return False

    def finish_ai(self, i):
        self.clear_message_window()
        return self.end(i,not self.disabled(i) and not self.ranged(i) and self.record(i)['initiative']>0)

    def equip(self, i):
        from .inventory import toggle_ready
        c = self.chars[i]; slots = rules.worn(c)
        raw = lambda slot: slot.data.obj if slot is not None else None
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
                if item[I['type']] == 54 and target>=0 and field(self.chars[target],'undead',signed=True)>0: score = 8
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
            if bs>ms//2 and (ammo is not None or props == 10) and (base[12]>1 and props&20 == 20 or not self.count_targets(i,1)): choice = best
        def toggle(item):
            if item is not None:
                facade = EffectGame(self,'AI equipment effect',i); facade.weapon = self.held = self.weapon(i)
                try: toggle_ready(facade,c,item)
                finally: self.held = None
        changed = old is None or old is not choice and not old[I['cursed']]
        if changed:
            toggle(old); self.recalc(c)
            shield = raw(rules.worn(c)[1])
            if shield is not None and not shield[I['cursed']]: put(c,'hands_used',field(c,'hands_used')-self.base(shield)[1])
            toggle(choice)
        self.recalc(c); self.reset_attacks(i); shield = raw(rules.worn(c)[1])
        if field(c,'hands_used')>2: toggle(shield if shield is not None and not shield[I['cursed']] else choice); changed = True
        elif field(c,'hands_used')<2 and (shield is None or shield is not best_shield and not shield[I['cursed']]):
            toggle(shield); self.recalc(c); toggle(best_shield); changed = True
        self.recalc(c)
        if changed and self.data.get('panel_due'): self.panel(i)
    def ai_can_step(self, i, direction):
        occupant,tile = self.probe(i,direction)
        if not tile: return False,True
        terrain = self.terrain(tile)
        if terrain == 255 or occupant>=0: return False,False
        c,r = self.chars[i],self.record(i)
        cost = (terrain*(3 if direction%2 else 2))&255
        if cost>=r['movement']: return False,False
        ahead = {self.tile(x+DX[direction],y+DY[direction]) for x,y in self.cells(i)}
        if 29 in ahead and not r['turned'] and not any(has(c,k) for k in (32,30,99,63)) and not self.save(i,0):
            cost = (r['movement']+1)&255
        if 28 in ahead and field(c,'highest_level',signed=True)<7 and not has(c,99) and not r['turned']:
            cost = (r['movement']+1)&255
        return cost<=r['movement'],False

    def ai_step(self, i):
        c,r = self.chars[i],self.record(i)
        self.show('move',actor=i,left=r['movement']>>1,still=True)
        if self.ai_key(i): return True
        if r['movement']//2 == 0 or r['initiative']<=0: return self.finish_ai(i)
        npc,side = field(c,'npc'),field(c,'side')
        allowed = npc<128 or npc>127 and self.data['hostile_hp']<=self.die(1,100,'AI advance morale',i)+self.data.get('morale',0) or side == 1
        if not allowed or not (r['fleeing'] or rules.worn(c)[2] is not None or field(c,'class') != 5): return self.finish_ai(i)
        if r['fleeing']:
            r['stance'] = self.die(1,2,'flee pattern',i)
            direction = (self.s.dir-((self.s.dir+2)%4)//2+1+4*(side == 0))%8
        elif r['target']<0: return self.finish_ai(i)
        else: direction = self.direction(i,r['target'])
        chosen = None
        assets = self.game.assets
        offsets = assets.layout['tables']['aiDirOffsets']['offset']+(r['stance']-1)*5
        for attempt in range(1,6):
            d = (direction+assets.resident[offsets+attempt])%8
            allowed,edge = self.ai_can_step(i,d)
            if edge and r['fleeing']: r['fleeing'] = 0; return self.flee(i)
            if allowed:
                chosen = d; break
        if chosen is None or self.data['last_direction'] == (chosen+4)%8:
            self.data['stuck'] = (self.data['stuck']+1)&255; r['stance'] = r['stance']%6+1
            if self.data['stuck']>1:
                r['target'] = -1
                if self.data['stuck']>2:
                    r['movement'] = 0
                    if chosen is not None: self.data['last_direction'] = chosen
                    return False
                if not self.acquire(i,True): return self.finish_ai(i)
        if chosen is not None:
            self.data['gfx']=bool(self.data.get('movement_option',0) or self.visible(i) or side==0)
            self.data['last_direction'] = chosen; self.move(i,chosen,ai=True)
        return False

    def ai_key(self, i, turn_entry=False):
        actor = self.chars[i]
        poll = getattr(self.game, 'ai_check', None)
        if poll is not None:
            key = poll()
        else:
            demo = getattr(self.game, 'demo_mode', 0)
            if not turn_entry or not (demo or field(actor,'npc') < 128 and field(actor,'status') != 1):
                return False
            prompt = '' if demo else 'Space: manual. Magic: toggle spell casting.'
            choice = self.ask(Kind.AUTO, ['Continue','Manual','Magic'], prompt=prompt, magic=int(self.magic_enabled))
            key = (None, ' ', '2')[choice]
        if key == '2': self.toggle_magic()
        if key != ' ': return False
        for member in self.chars:
            if field(member,'npc') < 128 and field(member,'status') != 1:
                put(member,'auto_combat',0)
        if field(actor,'auto_combat'): return False
        self.record(i)['initiative'] = 20
        return True

    def ai(self, i):
        c,r = self.chars[i],self.record(i)
        if r['target'] < 0: self.acquire(i, True)
        stopped = self.ai_key(i, turn_entry=True)
        self.clear_message_window(bottom=True)
        if not field(c,'active'): self.end(i); stopped=True
        if not 1 <= r['stance'] <= 4 or self.die(1,4,'retain AI pattern',i) == 1:
            r['stance'] = self.die(1,2,'AI sweep pattern',i)+4 if self.die(1,8,'AI pattern class',i) == 8 else self.die(1,4,'AI approach pattern',i)
        if not stopped: stopped = self.morale(i)
        if r['fleeing'] and not r['turned']: self.pause_creature_message(c, self.game.assets.text('panicText'))
        if stopped: return
        if self.ai_item(i): return self.end(i)
        if r['casting']:
            if r['target']<0: self.acquire(i,True,force=True)
            self.cast(i,r['casting'],ai=True); return self.end(i)
        if (field(c,'levels',0,signed=True)>0 or field(c,'levels',3,signed=True)>2) and r['turns']<getattr(self.game.vm,'undead_count',0):
            if any(0<field(self.chars[j],'undead')<=13 and not self.record(j)['turned'] for j in self.count_targets(i)):
                return self.turn_undead(i)
        if self.ai_spell(i): return
        self.equip(i)
        if self.ai_key(i): return
        for _ in range(128):
            if not self.acquire(i,True) or r['initiative']<=0 or not field(c,'active'): return self.finish_ai(i)
            self.data.update(last_direction=8,stuck=0,ai_init=0)
            self.trigger(14,i)
            if field(c,'side') == 0 and self.bandage(): r['initiative'] = 0; return
            for iteration in range(21):
                while r['fleeing'] and r['movement']>0 and 0<r['initiative']<20: self.ai_step(i)
                if r['initiative'] in (0,20): return
                last = iteration == 20
                if last: self.finish_ai(i)
                self.data['movement_option']=0
                reach = self.base(self.weapon(i))[12]
                if reach in (0,255): reach = 1
                j = r['target']
                locked = j>=0 and field(self.chars[j],'active') and field(self.chars[j],'side') != 0 and self.can_target(i,j,False) and self.anchor_reach(i,j,reach)
                if not locked:
                    nearby = self.count_targets(i,reach)
                    if not nearby:
                        if self.acquire(i): self.ai_step(i)
                        else: return self.finish_ai(i)
                        if last: return
                        continue
                    j = nearby[self.die(1,len(nearby),'AI attack target',i)-1]
                    if self.ranged(i) and not self.throwable(i) and self.count_targets(i,1): self.equip(i); break
                    if self.distance(i,j) != 1 and not self.can_target(i,j,False): continue
                self.data['movement_option']=1
                self.scroll(*self.position(i),2,self.direction(i,j))
                missile = self.ammo(i)[1] if self.ranged(i) and not (self.throwable(i) and self.distance(i,j) == 1) else None
                if self.strike(i,j,missile=missile) or last: return
                if not field(self.chars[j],'active'): break
            if last: return
        raise BindingRequired('Death Knights AI failed to finish a native turn')

    def cure_target(self, i):
        raise BindingRequired('Death Knights combat.cure_target is unverified')

    def ai_accept_spell(self, i, ident, priority):
        raise BindingRequired('Death Knights combat.ai_accept_spell is unverified')

    def ai_spell(self, i):
        from . import magic
        c,r=self.chars[i],self.record(i)
        if self.s.r0[0xE5] or rules.spellbook(c) is None or not r['cast_ok'] or field(c,'npc')<127 and not self.magic_enabled: return False
        spell = self.ai_pick_spell(i)
        score = (sum(field(c,'levels',k) for k in (2,7,3,4))*4)&255
        if not spell or self.die(1,100,'AI casting inclination',i)<=score: return False
        if magic.spell(self.game,spell).ai_priority<self.die(1,5,'AI spell priority',i): return False
        return self.begin_cast(i,spell,True)

    def ai_pick_spell(self, i):
        from . import magic
        c = self.chars[i]; candidates = []
        for at in range(1,74):
            ident = field(c,'memorized',at)
            if not 0<ident<128: continue
            row = magic.spell(self.game,ident)
            if row.combat_ok: candidates.append((row.ai_priority,at,ident))
        previous = 0
        for priority,at,ident in sorted(candidates,reverse=True):
            if ident == previous: continue
            previous = ident
            if signed(self.rate_spell(i,ident))>0: return ident
        return 0

    def ai_item(self, i):
        self.die(1, 7, 'AI item priority bands', i)
        return False

    def bandage(self, apply=True):
        i=next((i for i,c in enumerate(self.chars) if not self.record(i)['outsider']
                and field(c,'side')==0 and field(c,'status')==5),None)
        if i is None: return False
        if apply:
            put(self.chars[i],'status',4); self.record(i)['overkill']=0
            self.pause_creature_message(self.chars[i], self.game.assets.text('bandageText'))
        return True

    def area_targets(self, x, y, radius):
        return [i for i,*_ in self.spans([(x,y)],radius)]

    def aim_ok(self, i, j, cell, reach, attack, empty):
        if reach < self.walk(*self.position(i),*cell,255,True)[2]//2: return False
        if j < 0: return empty
        return not attack or j != i and self.weapon_reaches(i)

    def weapon_reaches(self, i):
        return not self.ranged(i) or self.ammo(i)[0] and (not self.count_targets(i,1) or self.throwable(i))

    def aim_cycle(self, i, reach=255, attack=False, ground=False, creature_ok=True, empty=False, **info):
        if reach == 255: reach = self.base(self.weapon(i))[12]
        if reach in (0,255): reach = 1
        home = self.position(i)
        self.redraw_cell(*home)
        cycle = [j for j in self.targets(i,255,allies=True) if self.can_target(i,j,False)]
        if not cycle: return None
        lock =self.record(i)['target']; at = cycle.index(lock) if lock in cycle else 0
        j = cycle[at]; cell = self.position(j); flag = True; highlight = 4 if j != i else 0
        with self.preserve_target_list():
            legal = [k for k in cycle if self.aim_ok(i,k,self.position(k),reach,attack,empty)]
        while True:
            words = ['Next','Prev','Manual']+(['Target'] if flag and self.aim_ok(i,j,cell,reach,attack,empty) else [])+['Center','Exit']
            choices = [name(self.chars[k])+' #%d'%k for k in legal]+words+['Ground','Escape']
            if j >= 0: self.centered_view(j,3,True); self.panel(j)
            pick = self.ask(Kind.TARGET,choices,targets=legal,cursor=cell,selected=cycle[at],blank=int(j<0),attack=int(attack),
                            highlight=words[min(highlight,len(words))-1] if highlight else '',range=self.walk(*home,*cell,255,True)[2]//2,**info)
            word = choices[pick]; highlight = 0
            if pick < len(legal):
                k = legal[pick]
                if attack and k != j: self.weapon_reaches(i)
                self.centered_view(k,3,True); self.panel(k)
                return k,self.position(k)
            if word in ('Next','Prev'):
                at = (at+(1 if word == 'Next' else -1))%len(cycle); j = cycle[at]; flag = True
                self.moving_icon(*cell,*self.position(j)); cell = self.position(j)
            elif word in ('Manual','Ground'):
                flag,got = self.aim_cursor(i,cell,reach,attack,ground,creature_ok,**info)
                if got is not None: return got
                j,highlight = -1,3
            elif word == 'Target': return j,cell
            elif word == 'Center':
                self.data.update(cursor_active=True,cursor_size=1)
                try: self.scroll(*cell,0)
                finally: self.data['cursor_active'] = False
            else:
                if word == 'Escape': self.redraw_cell(*cell)
                self.scroll(*(home if word == 'Escape' else cell),0)
                return None

    def aim_cursor(self, i, start, reach, attack, ground, creature_ok, **info):
        home,aim,direction = self.position(i),start,8
        dirs = ['north','northeast','east','southeast','south','southwest','west','northwest']
        self.data.update(cursor_active=True,cursor_size=1)
        while True:
            self.scroll(*aim,2,direction)
            aim = max(0,min(49,aim[0]+DX[direction])),max(0,min(24,aim[1]+DY[direction])); self.data['aim'] = aim
            seen,_,distance = self.walk(*home,*aim); code = self.tile(*aim); target,body = -1,False
            if seen:
                target = self.occupancy().get(aim,-1)
                if target < 0 and code == 31:
                    bodies,owners,count = self.body_state()
                    for k in range(count):
                        if tuple(bodies[k][:2]) == aim: target,body = owners[k],True
            valid = seen and reach >= distance//2 and self.terrain(code) != 255
            if target >= 0:
                self.panel(target)
                if not self.can_target(i,target) or not creature_ok: valid = False
                if attack and (target == i or body or not self.weapon_reaches(i)): valid = False
            else:
                self.data['panel'] = -1
                if not ground: valid = False
            choices = dirs+(['Target'] if valid else [])+['Exit','Center']
            shown = {'range':distance//2} if attack and seen else {}
            pick = self.ask(Kind.AIM,choices,cursor=aim,word='Target' if valid else 'Exit',attack=int(attack),**shown,**info)
            if pick < 8: direction = pick; continue
            direction = 8
            if choices[pick] == 'Center': self.scroll(*aim,0)
            elif choices[pick] == 'Target':
                self.data['cursor_active'] = False
                self.redraw_cell(*aim)
                return True,(target,aim)
            else:
                self.redraw_cell(*aim)
                self.scroll(*start,0)
                self.data['cursor_active'] = False
                self.redraw_cell(*start)
                return bool(valid),None

    def aim_menu(self, i, row, reach, ground):
        return self.aim_cycle(i,reach,False,ground,row.id != 83,row.targeting&15 >= 8,spell=row.id,prompt=row.name)

    def pick_spell_target(self, i, row, reach, ground, ai):
        if not ai:
            picked = self.aim_menu(i,row,reach,ground)
            self.record(i)['target'] = picked[0] if picked is not None else -1
            return picked
        if ground and row.targeting != 8: return self.aim_area(i,row,reach)
        if not self.acquire(i,reach=reach,force=True,allies=not row.hostile): return None
        j = self.record(i)['target']
        team = field(self.chars[i],'side') ^ bool(row.hostile)
        return (j,self.position(j)) if self.rate_spell_target(i,j,row,team)>0 else None

    def rate_spell_target(self, i, j, row, team):
        c = self.chars[j]; ident = row.id
        if field(c,'side') != team: return -10
        blocked = {15:(17,),65:(17,),21:(96,53),23:(97,52),49:(97,52),51:(65,),61:(97,),
                   68:(99,),82:(80,),84:(92,),94:(97,)}
        if ident in blocked:
            good = not any(has(c,effect) for effect in blocked[ident])
            if ident == 21: good = good and field(c,'highest_level',signed=True)<5
            if ident in (23,49): good = good and field(c,'race',signed=True)<7
        elif ident in (1,105): good = not has(c,1) and not self.count_targets(j,1)
        elif ident == 42: good = not has(self.chars[i],49)
        elif ident in (3,53,58,71): good = field(c,'hp')<field(c,'hp_max')
        elif ident == 4: good = field(c,'race',signed=True)<7 or bool(field(c,'creature_type')&16)
        elif ident in (10,106): good = bool(field(c,'creature_type')&2) or field(c,'dimensions') == 1
        elif ident in (37,43,104): good = has(c,33 if ident == 37 else 36)
        elif ident in (47,64,74,108):
            if has(c,76): return -10
            good = True
        elif ident in (56,76): good = not field(c,'target_flags')&8
        elif ident in (81,111): good = bool(field(c,'creature_type')&2)
        elif ident == 91: good = field(c,'highest_level',signed=True)<6
        else: good = not row.effect or not has(c,row.effect)
        protected = row.level<5 and has(c,59) or row.level<4 and has(c,63) or field(c,'magic_resistance')>50
        return int(bool(good) and not protected)

    def rate_spell(self, i, ident):
        from . import magic
        row = magic.spell(self.game,ident); team = field(self.chars[i],'side') ^ bool(row.hostile)
        if not row.targeting: return self.rate_spell_target(i,i,row,team)&255
        reach = magic.spell_range(EffectGame(self,'spell rating',i),self.chars[i],row)
        score = 0
        for j in self.targets(i,reach,allies=True):
            score = self.rate_spell_target(i,j,row,team)
            if score>0: break
        return score&255

    def aim_area(self, i, row, reach):
        radius = (row.targeting-8-int(row.id in (47,108) and not self.game.vm.is3d()))&255
        extent = (reach+radius)&255
        locked = self.record(i)['target']
        center = locked if extent>9 and locked>=0 else i
        extent = min(9,extent)
        limit = (extent-radius)&255
        if limit>9: raise BindingRequired('Area aim exceeds native score storage')
        bx,by = map(signed,self.position(center))
        team = field(self.chars[i],'side') ^ bool(row.hostile)
        contributors = []
        for j,c in enumerate(self.chars):
            x,y = map(signed,self.position(j))
            if field(c,'active') and abs(x-bx)<=extent and abs(y-by)<=extent:
                contributors.append((x,y,self.rate_spell_target(i,j,row,team)))
        assets = self.game.assets
        offset = assets.layout['tables']['areaHalfWidths']['offset']
        widths = {dy:signed(assets.resident[offset+(dy+3)*3+radius]) for dy in range(-radius,radius+1)}
        best,aim = 0,None
        for x in range(bx-limit,bx+limit+1):
            for y in range(by-limit,by+limit+1):
                score = signed(sum(rank for cx,cy,rank in contributors
                    if y-cy in widths and abs(x-cx)<=widths[y-cy]))
                if score<best or score<=0: continue
                if score==best and self.die(1,100,'area aim tie',i)>25: continue
                if 0<=x<50 and 0<=y<24 and self.walk(x,y,*self.position(i),reach)[0]:
                    best,aim = score,(x,y)
        return (-1,aim) if aim is not None else None

    def spell_targets(self, i, row, using_item=False, ai=False):
        from . import magic
        facade = EffectGame(self,'spell targeting',i); facade.using_item = using_item
        reach = magic.spell_range(facade,self.chars[i],row)
        self.data.update(aim=self.position(i),aim_view=self.data['view'],multi_target=0)
        kind = row.targeting & 15
        if kind == 0: return [i]
        if kind == 5:
            threshold = magic.caster_level(facade,self.chars[i],row.id) if row.id == 79 else self.die(2,4,'spell target budget',i)
            chosen,cost = [],0
            while True:
                got = self.pick_spell_target(i,row,reach,False,ai)
                if got is None or got[0] < 0: break
                j = got[0]
                if j in chosen:
                    if ai: threshold = (threshold-1)&255
                    else: self.bottom_line('Already been targeted')
                    over_budget = False
                else:
                    chosen.append(j); self.data['aim'] = self.position(j)
                    t = self.chars[j]
                    if row.id != 79:
                        level = field(t,'highest_level'); cost += 1 if level in (0,1) else 2 if level==2 else 4 if level==3 else 8
                    else: cost += {1:1,2:2,3:2,4:4}.get(field(t,'dimensions'),0)
                    cost &= 255
                    over_budget = len(chosen) > 1 and cost > threshold
                self.redraw_cell(*self.position(j))
                if not threshold or over_budget: break
            return chosen
        if 8 <= kind <= 15:
            got = self.pick_spell_target(i,row,reach,kind<15,ai)
            if got is None: return None
            j,self.data['aim'] = got
            locked = self.record(i)['target']
            if kind == 15 and locked >= 0: return [locked]
            self.data['multi_target'] = 1
            return self.area_targets(*self.data['aim'],(row.targeting>>4) if kind==15 else row.targeting&7)
        total,chosen = (row.targeting&3)+1,[]
        while total:
            got = self.pick_spell_target(i,row,reach,False,ai)
            if got is None or got[0] < 0: break
            j = got[0]
            if j in chosen or row.id in (23,49) and j == i:
                if ai: total -= 1
                else: self.bottom_line('Cannot target yourself' if j == i else 'Already been targeted')
            else:
                chosen.append(j); total -= 1; self.data['aim'] = self.position(j)
            self.redraw_cell(*self.position(j))
        return chosen or None

    def cast(self, i, ident, using_item=False, ai=False):
        from . import magic
        c = self.chars[i]; facade = EffectGame(self,'spell %d'%ident,i); facade.using_item = using_item
        row = magic.spell(facade,ident); body = magic.handler(facade,row)
        if not using_item: self.pause_creature_message(c, self.game.assets.text('castsSpellText'))
        while True:
            targets = self.spell_targets(i,row,using_item,ai)
            if targets is not None: break
            if ai or self.ask(Kind.CONFIRM,['Yes','No'],prompt=self.game.assets.text('abortSpellPrompt'),start=0)==0:
                self.bottom_line(self.game.assets.text('spellAbortedText'))
                if not using_item and rules.spellbook(c) is not None: magic.forget(c,ident)
                self.event('spell aborted',actor=i,spell=ident,item=using_item)
                return False
        magic.show_cast(self,i,ident)
        while has(c,25): self.remove_effect(i,25)
        if not using_item and rules.spellbook(c) is not None: magic.forget(c,ident)
        self.event('cast',actor=i,spell=ident,targets=tuple(targets),aim=tuple(self.data['aim']),item=using_item)
        self.data['flash'] = dict(actor=i,targets=tuple(targets),aim=tuple(self.data['aim']),spell=ident)
        self.data.update(current_spell=ident,using_item=using_item)
        self.game.spell_targets = [self.chars[j] for j in targets]
        try: body(facade,c,self.game.spell_targets,row)
        finally:
            self.data.pop('current_spell',None); self.data.pop('using_item',None)
        self.data['multi_target'] = 0
        self.data.pop('flash',None)
        return True

    def cast_item(self, char, ident):
        raise BindingRequired('Death Knights combat.cast_item is unverified')

    def begin_cast(self, i, ident=0, ai=False):
        from . import magic
        c,r = self.chars[i],self.record(i); facade = EffectGame(self,'cast menu',i)
        if not ident:
            ident = magic.spell_menu(facade,c,0,1,-1,combat=True,ask=lambda options,**info: self.ask(Kind.SPELL,options,**info))[0]
        row = magic.spell(facade,ident) if ident else None
        if ident and not row.combat_ok:
            self.bottom_line('Camp Only Spell')
            ident = 0
        if not ai:
            self.data['panel'] = -1
            self.clear_message_window(bottom=True)
            ox, oy = self.data['view']
            self.scroll(ox+3, oy+3, 255)
            self.data.update(gfx=True, panel_due=True)
            self.centered_view(i, 3, True)
            self.panel(i)
        if not ident: return False
        delay = row.cast_time//3
        if not delay:
            self.cast(i,ident,ai=ai); self.end(i); return True
        self.pause_creature_message(c, 'Begins Casting')
        r.update(casting=ident,initiative=r['initiative']-delay if r['initiative']>delay else 1)
        order,cursor = self.data['order'],self.data['cursor']
        order.pop(cursor); at = cursor
        while at<len(order) and (self.record(order[at])['initiative']>r['initiative'] or
                self.record(order[at])['initiative']==r['initiative'] and self.die(1,2,'casting initiative tie',i,order[at])==1): at += 1
        order.insert(at,i); self.data['cursor'] -= 1
        self.event('begin casting',actor=i,spell=ident,initiative=r['initiative'],position=at)
        return True

    def touch(self, caster, target, row=None):
        i,j = self.index(caster),self.index(target)
        self.recalc(target); x = self.context(caster); self.trigger(11,j,x)
        natural = self.die(1,20,'spell touch',i,j)
        if natural < 2: return False
        x.attack = 100 if natural == 20 else natural
        self.trigger(10,i,x); self.trigger(16,j,x)
        modifier = signed(self.s.r1[0x371 if field(caster,'side')==0 else 0x370]&255)
        return x.attack>=0 and x.attack+field(caster,'thac0')+modifier>=field(target,'ac')

    def spell_damage(self, target, context, reduction, saved):
        j = self.index(target); self.trigger(6,j,context)
        target=getattr(context,'target',target); j=self.index(target)
        if saved and reduction in (1,2): context.damage = 0 if reduction==1 else context.damage//2
        if not saved:
            self.trigger(20,j,context)
            target=getattr(context,'target',target); j=self.index(target)
        self.remember_roll(context)
        if context.damage and field(target,'active'):
            t = self.game.assets.text
            text = t('takesPrefix')+str(context.damage)+t('pointsDamage') if context.damage != 1 else t('onePointDamage')
            text += {1:t('fromFire'),2:t('fromCold'),4:t('fromElectricity'),16:t('fromAcid')}.get(context.element&0xF7,'')
            if context.element&8 == context.element: text += t('fromMagic')
            self.message(name(target)+' '+text); self.name_anim(target,True)
            self.damage(j,context.damage,context,nonweapon=True)
        return target

    def cone(self, i, aim, width, length):
        raise BindingRequired('Death Knights combat.cone is unverified')

    def dragon_breath(self, i, node, context):
        raise BindingRequired('Death Knights combat.dragon_breath is unverified')

    def heal(self, char, amount):
        if field(char,'status') not in (0,1,4,5): return False
        put(char,'hp',min(field(char,'hp_max'),(field(char,'hp')+amount)&255))
        if not field(char,'active') and field(char,'status')==5: put(char,'status',4)
        self.event('heal',actor=self.data['actor'],target=self.index(char),amount=amount,hp=field(char,'hp'))
        return True

    def creature_message(self, c, words, *, report=False):
        who = name(c)
        self.message(who + ' ' + words, report=report)
        colour = 12 if not field(c, 'active') else 14 if field(c, 'side') == 1 else 13 if field(c, 'level_up_ready') else 11
        return dict(creature_column=23, creature_row=10, creature_name=who, creature_colour=colour, creature_text=words)

    def pause_creature_message(self, c, words):
        self.ask(Kind.ACK, ('Continue',), timed=1, prompt='', **self.creature_message(c, words))
        self.clear_message_window()

    def turn_undead(self, i):
        c = self.chars[i]
        self.ask(Kind.ACK, ('Continue',), timed=1, prompt='', clear_bottom=True,
                 **self.creature_message(c, self.game.assets.text('turnsUndeadText')))
        r = self.record(i)
        r['turns'] = (r['turns'] + 1) & 255
        roll = self.die(1,20,'turn undead',i)
        column = max(field(c,'levels',0,signed=True),field(c,'levels',3,signed=True)-2)+2*(field(c,'deity',signed=True)==2)
        if column > 8: column = 9 if column < 14 else 10
        offset = self.s.r0[0x1FF]
        column = 0 if offset > column else column-offset
        cap,minimum,left,turned = 13,6,255,False
        while True:
            candidates = [j for j in self.count_targets(i) if not self.record(j)['turned'] and 0<field(self.chars[j],'undead')<=cap]
            if not candidates or not left: break
            best = max(field(self.chars[j],'undead') for j in candidates)
            j = next(j for j in candidates if field(self.chars[j],'undead') == best); cap = best
            needed = signed(self.t['turning'][(cap-1)*11+column])
            if left == 255: left = self.die(1,6,'turn count',i)+6 if needed<0 else self.die(1,12,'turn count',i)
            if roll < abs(needed): cap -= 1; continue
            turned = True; target = self.chars[j]
            self.centered_view(j,3); self.panel(j)
            if needed > 0:
                self.out_of_play(j,3,self.game.assets.text('turnedText'))
            else:
                message = self.creature_message(target, self.game.assets.text('destroyedText'))
                self.down(j, creature_message=message)
                put(target,'status',8); put(target,'active',0)
            self.event('turn undead',actor=i,target=j,column=column,needed=needed,roll=roll,destroyed=needed<=0)
            if minimum: minimum -= 1
            left -= 1
            if not left and minimum and needed < 0: left = 1
            self.clear_message_window()
        if not turned:
            self.bottom_line(self.game.assets.text('nothingHappensText'))
        self.end(i)
        self.clear_message_window()

    def cloud(self, caster, level):
        raise BindingRequired('Death Knights combat.cloud is unverified')

    def clear_cloud(self, owner, instance):
        raise BindingRequired('Death Knights combat.clear_cloud is unverified')

    def acid_pool(self, i):
        raise BindingRequired('Death Knights combat.acid_pool is unverified')

    def clear_acid(self, owner, instance):
        raise BindingRequired('Death Knights combat.clear_acid is unverified')

    def dispel_clouds(self, caster, succeeds):
        raise BindingRequired('Death Knights combat.dispel_clouds is unverified')

    def terrain_effects(self, i, moved=False):
        from .effects_area import terrain_effects
        terrain_effects(self,i,moved)

    def lightning(self, facade, caster, row, amount, length=7, save=4, element=12, bounce=True, first=None):
        raise BindingRequired('Death Knights combat.lightning is unverified')

    def manual(self, i):
        from . import town
        c,r = self.chars[i],self.record(i)
        if not field(c,'active'): self.end(i); return
        if r['casting']:
            ident = r['casting']; r['casting'] = 0
            self.cast(i,ident); self.end(i); return
        done = False
        while not done:
            options = (['Move'] if r['movement'] else [])+['Aim']+(['Use'] if c.items else [])
            if r['cast_ok'] and not self.s.r0[0xE5] and rules.spellbook(c) is not None and any(field(c,'memorized',k)&127 for k in range(74)): options.append('Cast')
            if r['turns']<getattr(self.game.vm,'undead_count',0) and (field(c,'levels',0,signed=True)>0 or field(c,'levels',3,signed=True)>2): options.append('Turn')
            if not self.ranged(i) or self.throwable(i): options.append('Guard')
            options += ['Quick', 'Delay']
            if self.bandage(False): options.append('Bandage')
            if field(c,'race') == 5 and self.data['yell']<0: options.append('Yell')
            options += ['View', 'Speed', 'End']
            options += FIGHT_KEYS
            action = options[self.ask(Kind.ACTION,options,prompt=name(c),movement=r['movement']//2)]
            if action == 'space':
                for char in self.chars:
                    if field(char,'npc')<128: put(char,'auto_combat',0)
            elif action == 'Alt-m': self.toggle_magic()
            elif action in ('Alt-q','Alt-a'):
                r['initiative'] = 20; self.data['cursor'] -= 1
                for j in range(len(self.chars)): self.auto_on(j)
                return
            elif action == 'Alt-r': pass
            elif action == 'View':
                from .inventory import view
                try: done = bool(view(InventoryGame(self,'inventory effect',i),c))
                finally: self.held = None
                self.reset_attacks(i)
            elif action == 'Use':
                from .inventory import items_menu
                try: done = bool(items_menu(InventoryGame(self,'inventory effect',i),c))
                finally: self.held = None
                self.reset_attacks(i)
            elif action == 'Cast':
                if self.begin_cast(i): return
            elif action == 'Turn': self.turn_undead(i)
            elif action == 'Yell':
                self.data['yell'] = i
                for j,t in enumerate(self.chars):
                    if field(t,'status') == 0 and field(t,'abilities',3)>3 and field(t,'side') != field(c,'side') and not self.disabled(j) and not self.save(j,4):
                        self.add_with_message(j,91,0,255,False,self.game.assets.text('wantsToKill')+name(c))
                self.end(i)
            elif action == 'Aim':
                aimed = self.aim_cycle(i,attack=True)
                if aimed is not None:
                    j,cell = aimed
                    if not self.confirm_ally(i,j): self.scroll(*cell,0)
                    else:
                        ox, oy = self.data['view']
                        self.data['cursor_active'] = False
                        self.scroll(ox + 3, oy + 3, 3)
                        missile = self.ammo(i)[1] if self.ranged(i) and not (self.throwable(i) and self.distance(i,j) == 1) else None
                        self.strike(i,j,missile=missile)
            elif action == 'Move':
                self.data['in_move_menu'] = True
                directions = ['north','northeast','east','southeast','south','southwest','west','northwest']
                start = {k:r[k] for k in ('x','y','size','movement','facing')}
                prompt = ''
                while r['initiative']>0 and field(c,'active'):
                    d = self.ask(Kind.MOVE,directions+['Done','Undo'],movement=r['movement']//2,prompt=prompt)
                    prompt = ''
                    if d == 9:
                        r['movement'] = start['movement']
                        self.erase_footprint(i)
                        valid = self.valid_location(i,start['x'],start['y'])
                        self.center(i,0)
                        r['facing'] = start['facing']
                        if not valid:
                            self.data['in_move_menu'] = False
                            if r['movement']<2: r['movement'] = 0
                            return
                    if d >= 8: break
                    self.face(i,d)
                    occupant,tile = self.probe(i,d)
                    if occupant>=0:
                        refused=self.ranged(i) and not self.throwable(i)
                        self.move_attack(i,occupant)
                        if refused: prompt=self.game.assets.text('notWithWeapon')
                    elif not tile:
                        if self.ask(Kind.CONFIRM,['Yes','No'],prompt=self.game.assets.text('fleePrompt'),start=1) == 0: self.flee(i)
                    elif not self.move(i,d): prompt=self.game.assets.text('cantGoThere')
                if r['movement']<2: r['movement'] = 0
                self.data['in_move_menu'] = False
            elif action in ('Guard', 'End', 'Bandage'):
                if action == 'Bandage': self.bandage()
                self.end(i, action == 'Guard')
            elif action == 'Delay':
                order,cursor = self.data['order'],self.data['cursor']
                order.append(order.pop(cursor)); self.data['cursor'] -= 1; r['initiative'] = 1; return
            elif action == 'Quick':
                self.auto_on(i)
                self.ai(i)
                return
            elif action == 'Speed': self.speed_menu()
            else: raise BindingRequired('Death Knights combat %s is not bound'%action)
            if action not in ('View','Use'): done = r['initiative']<=0 or not field(c,'active')
            if not done: self.centered_view(i,2,True); self.panel(i)

    def auto_on(self, i):
        c,r = self.chars[i],self.record(i)
        put(c,'auto_combat',1)
        if r['target']>=0 and field(self.chars[r['target']],'side') == field(c,'side'): r['target'] = -1

    def toggle_magic(self):
        self.game.combat_magic = not self.magic_enabled
        self.bottom_line(self.game.assets.text('magicOnMsg' if self.magic_enabled else 'magicOffMsg'))

    def speed_menu(self):
        words = self.game.assets.text('speedChoices').split()
        while True:
            speed = self.s.g.get('dkk.delay',4)
            ids = ([0] if speed>0 else [])+([1] if speed<9 else [])+[2]
            selected = ids[self.ask(Kind.DONE,[words[n] for n in ids],query=self.game.assets.text('gameSpeedLabel')+'(%d) '%speed)]
            if selected == 2: return
            self.s.g['dkk.delay'] = speed+(-1 if selected == 0 else 1)
            self.s.r0[0xFC] = self.s.g['dkk.delay']

    def turns(self):
        done,finished = not all(self.data.get('setup_teams',self.teams())),False
        for i in range(len(self.chars)): self.trigger(24,i)
        while not done:
            self.begin_round()
            while not done and self.data['cursor']<len(self.data['order']):
                i = self.data['order'][self.data['cursor']]; c,r = self.chars[i],self.record(i)
                r.update(flanks=0,spread=0,guard=0); self.trigger(7,i)
                if r['initiative']>0:
                    if r['initiative'] == 20: r['initiative'] = 19
                    self.data['actor'] = i; self.s.sel = i
                    self.turn_view(i)
                    self.recalc(c); self.panel(i); self.trigger(15,i)
                    if not r['casting']: self.trigger(21,i)
                    if r['initiative']>0:
                        if field(c,'auto_combat'): self.ai(i)
                        elif r['casting']:
                            ident=r['casting']; r['casting']=0
                            self.cast(i,ident,ai=bool(field(c,'auto_combat'))); self.end(i)
                        else: self.manual(i)
                    self.redraw_cell(*self.position(i))
                self.explode()
                self.data['cursor'] += 1
                if not finished and (not all(self.teams()) or self.data['round']>=self.data['limit']): done = finished = True
            effects.advance(EffectGame(self,'round effects',-1),1,1)
            from .effects_area import count_down_area
            count_down_area(self,False)
            self.data['round'] = (self.data['round']+1)&255; self.hp_percent()
            for i,c in enumerate(self.chars):
                self.trigger(19,i)
                self.terrain_effects(i,moved=False)
                if field(c,'status') == 5:
                    self.record(i)['overkill'] = (self.record(i)['overkill']+1)&255
                    if self.record(i)['overkill']>9: put(c,'status',6)
            if self.bandage(False): self.bottom_line(self.game.assets.text('teammateDying'))
            left,right = self.teams()
            ox,oy = self.data['view']
            self.scroll(ox+3,oy+3,255)
            done = done or not left or not right or self.data['round']>=self.data['limit']
            if left and not right and not getattr(self.game,'demo_mode',0): done = self.ask(Kind.CONFIRM,['Yes','No'],prompt=self.game.assets.text('continueBattle'),start=1) != 0
        if getattr(self.game,'age_pass',False): self.aging_deaths()

    def aging_deaths(self):
        limits = (1600,1600,325,525,525,199,120)
        text = self.game.assets.text
        witnesses = self.data.get('age_witness_count',0)
        witness = None
        for i,c in enumerate(self.chars):
            race,age = field(c,'race'),field(c,'age',width=2)
            if field(c,'status',signed=True)>=6 or self.record(i)['outsider'] == 1 or race>=len(limits): continue
            if age>limits[race]:
                for message in (text('ageStrainMsg')+name(c)+'.  ',text('heMsg' if field(c,'gender') == 0 else 'sheMsg')+text('lastBreathMsg')):
                    self.ask(Kind.ACK,['Continue'],message=message,panel_row=14,panel_colour=15,prompt=text('pressToContinue'))
                self.kill(i,8,text('ageDeathMsg'))
                for other in self.chars:
                    if field(other,'active') == 1 and field(other,'status') == 0 and field(other,'side') != 1:
                        witnesses = (witnesses+1)&255; witness = other
                if witnesses == 1 and witness is None: raise BindingRequired('Death Knights aging witness pointer requires native initial state')
                message = text('noWitnessMsg') if not witnesses else name(witness)+text('oneWitnessMsg') if witnesses == 1 else text('manyWitnessMsg')+name(c)+text('bodySearchMsg')
                self.ask(Kind.ACK,['Continue'],message=message,panel_row=14,panel_colour=14,prompt=text('pressToContinue'))
            elif age>limits[race]-10:
                self.pause_creature_message(c, text('ageWarningMsg'))
        self.game.age_pass = False

    def loot(self):
        from . import magic, shop
        selected = 0
        getattr(self.game.vm,'archive',lambda *memo: None)('PIC',60)
        getattr(self.game.vm,'party_drawn',lambda: None)()
        while self.s.party:
            c = self.s.selc(); money,items = treasure_flags(self.s)
            detect = next((field(c,'memorized',i) for i in range(74) if field(c,'memorized',i) in (5,11,77,103)),0) if items and field(c,'active') else 0
            options = ['View']+(['Take'] if money or items else [])+['Pool']+(['Share'] if money else [])+(['Detect'] if detect else [])+['Exit']
            if selected >= len(options): selected = 0
            index = self.ask(Kind.LOOT,options+['char-up','char-down'],start=selected)
            if index >= len(options):
                self.s.sel = (self.s.sel+(-1 if index == len(options) else 1))%len(self.s.party)
                continue
            selected,choice = index,options[index]
            if choice == 'Exit':
                if not (money or items): return
                text = self.game.assets.text
                if self.ask(Kind.CONFIRM,['Yes','No'],offer=text('treasureLeft1')+text('treasureLeft2'),start=1) == 1: return
            elif choice == 'View': self.game.vm.service('inventory', 'view', self.s.selc())
            elif choice == 'Pool': shop.pool_money(self.s)
            elif choice == 'Share': shop.share_money(self.s)
            elif choice == 'Detect': magic.cast_in_camp(self.game,c,detect,announce=False)
            elif choice == 'Take': loot_take(self.game,money,items)

    def treasure(self):
        self.s.g['dkk.battle'] = dict(active=False,round=0,actor=-1,bank=[],messages=[],
            morale=getattr(self.game,'morale_memo',0),treasure_boundary=None,
            actors=[dict(outsider=0,size=0,x=0,y=0) for c in self.chars])
        if not hasattr(self.game,'combat_log'): self.game.combat_log=[]
        self.postcombat(False)

    def loot_experience(self, participants, excluded):
        from . import shop
        total,added = 0,[]
        for i,char in enumerate(participants):
            if field(char,'side') != 1 or field(char,'status') in (0,3): continue
            self.data['monsters_killed'] = True
            if self.record(i)['outsider'] == 1:
                for coin in range(4,7): shop.change_pool(self.s,coin,shop.coins(char)[coin])
            total = longint(total+field(char,'xp_award',width=2)+field(char,'hp_roll_needed')*field(char,'hp_rolled'))
            if self.s.r1[0x2E3] != 1:
                for raw in char.items:
                    copy = bytearray(raw); copy[I['readied']] = 0
                    shop.item_name(self.game,copy); added.insert(0,copy)
        self.s.treasure_items[:0] = added
        for coin,factor in ((4,2),(5,250),(6,2200)): total = longint(total+self.s.treasure_money[coin]*factor)
        boundary = self.data['treasure_boundary']
        counted = self.s.treasure_items if boundary is None else self.s.treasure_items[:len(added)+boundary]
        for item in counted: total = longint(total+max(0,signed(item[I['bonus']]))*400)
        divisor = self.s.r1[0x33E]-excluded
        if not divisor: raise BindingRequired('DKK native experience divisor is zero')
        return quotient(total,divisor)

    def award_experience(self, participants, share):
        from . import creation
        if self.s.r0[0x1F5]: return
        for i,char in enumerate(participants):
            if not field(char,'active') or field(char,'status') == 1: continue
            cls,award = field(char,'class'),share
            stats = [field(char,'abilities',k*2+1) for k in range(6)]
            prime = {0:stats[2]>14,2:stats[0]>15,3:stats[0]>15 and stats[2]>15,
                     4:all(v>15 for v in stats[:3]),5:stats[1]>15,6:stats[3]>15}
            if prime.get(cls,False): award = longint(share+quotient(share,10))
            elif cls in (8,10,11,12,13,14,16): award = quotient(share,2)
            elif cls in (9,15): award = quotient(share,3)
            put(char,'experience',longint(field(char,'experience',width=4,signed=True)+award),width=4)
            put(char,'level_up_ready',int(bool(creation.eligible(char))))
            self.event('experience',actor=i,amount=award)

    def postcombat(self, fought=True):
        s,participants = self.s,list(self.chars)
        enemy_survivors = self.teams()[1] if fought else 0
        self.data['clouds'] = []
        if fought:
            for i,char in enumerate(participants):
                if has(char,11) and field(char,'status') == 0 and enemy_survivors>1: put(char,'status',3)
                self.strip(i)
            self.game.combat_target_slots = tuple(self.data.get('target_list', ()))
            self.game.combat_first_target_distance = self.first_target_distance
            for key in ('tiles', 'view', 'cursor_active', 'cursor_size'):
                self.data.pop(key, None)
            s.g.setdefault('dkk.runtime',{})['slow_text'] = 1
        self.game.battle = None
        s.r1[0x2C7] = 0
        self.data['monsters_killed'] = False
        demo = bool(getattr(self.game,'demo_mode',0))
        prefix = []
        for i,char in enumerate(participants):
            if self.record(i)['outsider'] == 1: break
            prefix.append(char)
        discarded = set()
        share = getattr(self.game,'exp_share',0)
        fled,won,defeated = False,False,False
        if not demo:
            fled = any(field(c,'status') == 3 for c in prefix)
            alive = any(field(c,'active') or field(c,'status') in (3,4,5) for c in participants)
            defeated = not (s.r1[0x2E6] and alive)
            excluded = 0
            for i,char in enumerate(prefix):
                status = field(char,'status')
                if status in (0,1,3) and field(char,'side') == 0 and field(char,'npc')<128: defeated = False
                if status in (0,1): won,fled = True,False
                if not field(char,'active') or status == 1: excluded = (excluded+1)&255
                for ident in self.game.assets.table('clearEffects'): self.remove_effect(i,ident)
            if won:
                share = self.game.exp_share = self.loot_experience(participants,excluded)
                self.award_experience(participants,share)
            for char in prefix:
                status = field(char,'status')
                if defeated or fled and status != 3:
                    discarded.add(id(char)); s.r1[0x33E] = (s.r1[0x33E]-1)&255
                elif status == 3:
                    put(char,'status',0); put(char,'active',1)
                elif status == 5:
                    put(char,'status',0 if s.r1[0x2E6] else 4)
                    if s.r1[0x2E6]: put(char,'active',1); put(char,'hp',1)
                elif status == 4:
                    if field(char,'hp') or s.r1[0x2E6]:
                        put(char,'status',0); put(char,'active',1)
                        if not field(char,'hp'): put(char,'hp',1)
                if fled and not defeated: s.r1[0x2C7] = 129
            if defeated: s.r1[0x33E] = 0
        s.mode = 6
        self.data['active'] = False
        self.game.morale_memo = self.data.get('morale',0)
        removed = []
        for i,char in enumerate(participants):
            if id(char) in discarded: continue
            if self.record(i)['outsider'] == 1 or field(char,'side') == 1:
                removed.append(char); discarded.add(id(char)); self.data['monsters_killed'] = True
                if self.record(i)['outsider'] != 1: s.r1[0x33E] = (s.r1[0x33E]-1)&255
                if field(char,'status') == 3 and not s.r1[0x2C7]: s.r1[0x2C7] = 1
        s.r1[0x2C8] = sum(field(c,'active') != 1 for c in removed)&255
        if removed and field(removed[0],'active') != 1: s.r0[0x1F8] = 1
        s.party = [c for c in participants if id(c) not in discarded]
        for char in participants:
            if id(char) in discarded: rules.release_inventory(self.game,char)
        s.monsters = []; s.sel = 0; s.mode = 6
        s.g['dkk.monster_icons'] = []
        self.data['actors'] = []
        if demo: return
        for char in s.party: self.recalc(char)
        s.party_dead = defeated
        fought_summary = self.data['monsters_killed']
        lost = bool(fought_summary and not fled and not won and s.r1[0x2E6])
        result = 'defeat' if defeated else 'fled' if fled else 'lost' if lost else 'won' if won else 'ended'
        if defeated or lost: s.r1[0x2C7] = 128
        self.data.update(result=result,experience=share,enemy_survivors=enemy_survivors)
        self.event('result',result=result,experience=share,defeated=s.r1[0x2C8],code=s.r1[0x2C7],enemy_survivors=enemy_survivors)
        text = self.game.assets.text
        if not defeated:
            if fled: s.treasure_items = []
            shown = share
            if fought_summary:
                key = 'msgPartyFled' if fled else 'msgLostFight' if lost else 'msgPartyWon'
                if fled: s.treasure_money[:] = [0]*7
                if fled or lost: shown = 0
            else: key = 'msgPartyTreasure'
            outcome = text(key)
            experience = text('eachReceives')+str(shown)
            treasure = text('msgPartyTreasure' if any(treasure_flags(s)) else 'msgNoTreasure')
            lines = [(3,outcome)]+([] if s.r0[0x1F5] else [(5,experience),(7,text('experiencePoints'))])+[(10,treasure)]
            message = outcome+(' '+experience+' '+text('experiencePoints') if not s.r0[0x1F5] else '')
            self.ask(Kind.ACK,['Continue'],message=message,prompt=text('pressToContinue'),experience=shown,summary_lines=lines)
            if any(treasure_flags(s)): self.loot()
            s.treasure_items = []
        else: self.ask(Kind.ACK,['Continue'],message=text('partyDestroyed'),prompt=text('pressAnyKey'))
        s.g.setdefault('dkk.runtime',{})['slow_text'] = 1
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


class InventoryGame(EffectGame):
    def __init__(self, battle, reason, actor):
        super().__init__(battle,reason,actor); self.weapon = battle.weapon(actor)
    def ask(self, *arguments, **info):
        self.battle.held = self.battle.weapon(self.s.actor)
        return self.game.ask(*arguments,**info)


def treasure_flags(state): return any(state.treasure_money[4:7]),bool(state.treasure_items)


def loot_items(game):
    from . import shop
    s,text = game.s,game.assets.text
    selected = 0
    while s.treasure_items:
        selected = min(selected,len(s.treasure_items)-1)
        labels = [shop.item_name(game,item) for item in s.treasure_items]
        note,game.shop_note = getattr(game,'shop_note',''),''
        selected = game.ask(Kind.LOOT.value,labels+['Exit'],prompt=text('itemsQuery'),query=text('itemsQuery'),
                            menu=text('takeMenu'),window='1 1 38 22',start=selected,message=note)
        if selected == len(labels): return
        if shop.give_item_copy(game,s.selc(),s.treasure_items[selected]): s.treasure_items.pop(selected)


def loot_take(game, coins=None, items=None):
    from . import shop
    s = game.s
    present = treasure_flags(s)
    if coins is None: coins = present[0]
    if items is None: items = present[1]
    if not coins: loot_items(game)
    elif not items: shop.take_menu(game,s.selc())
    else:
        selected = 0
        while True:
            options = ['Money','Items','Exit','char-up','char-down']
            choice = game.ask(Kind.LOOT.value,options,prompt=game.assets.text('takeQuery'),start=selected)
            if choice < 3: selected = choice
            if choice == 0: shop.take_menu(game,s.selc())
            elif choice == 1: loot_items(game)
            elif choice in (3,4): s.sel = (s.sel+(-1 if choice == 3 else 1))%len(s.party)
            coins,items = treasure_flags(s)
            if choice == 2 or not coins or not items: break
    return coins,items


def run(game):
    battle = game.current_battle = Battle(game)
    try:
        battle.setup()
        battle.turns()
        battle.postcombat()
    finally: game.current_battle = game.battle = None


def treasure(game):
    battle = game.current_battle = Battle(game)
    try: battle.treasure()
    finally: game.current_battle = game.battle = None


def test():
    from ._combat_test import test as check
    return check()
