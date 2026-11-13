import hashlib
from importlib import import_module
import re
from sm.files import file_path
from sm.titles.ssb import vm as retained
from sm.titles.ssb.walk import Map, DELTAS
from .records import Character
from .faults import BindingRequired


def buffer(character):
    return character.b if hasattr(character, 'b') else character.data


def monster_record(records, dataset, ident):
    raw = records('MON%dCHA' % dataset).get(ident)
    if raw is None: raise retained.Halt('Unable to load monster')
    return raw


def field(character, name, index=0, *, width=1, signed=False):
    offset, size = Character.FIELDS[name]
    if index < 0 or index + width > size: raise ValueError('character field bounds')
    raw=buffer(character); start=offset+index
    if width==1:
        value=raw[start]
        return value-256 if signed and value>=128 else value
    return int.from_bytes(raw[start:start+width], 'little', signed=signed)


def put(character, name, value, index=0, *, width=1):
    offset, size = Character.FIELDS[name]
    if index < 0 or index + width > size: raise ValueError('character field bounds')
    raw=buffer(character); start=offset+index
    if width==1: raw[start]=value&255
    else: raw[start:start+width] = (value & ((1 << (8*width))-1)).to_bytes(width, 'little')


def earlier_class(c):
    level = next((field(c, 'levels', i, signed=True) for i in range(8) if field(c, 'levels', i)), 0) if field(c, 'race') == 6 else 0
    return level > field(c, 'dual_threshold', signed=True)


def random_treasure(game):
    from .combat import roll
    from .shop import I
    from .records import Item
    die=lambda sides:roll(game,1,sides,'random treasure')
    def pick(sides, groups):
        value=die(sides)
        return next(kind for ceiling,kind in groups if value<=ceiling)
    category=pick(100,((20,0),(65,39),(70,40),(80,37),(85,59),(95,1),(100,2)))
    if category==0:
        branch=die(100)
        if branch<=10: kind=pick(10,((2,6),(6,8),(8,70),(9,15),(10,29)))
        elif branch<=25: kind=pick(20,((3,5),(5,7),(8,24),(10,22),(12,25),(14,23),(16,28),(18,29),(20,30)))
        elif die(4)<4: kind=pick(20,((8,18),(13,17),(14,13),(15,16),(18,19),(20,20)))
        else: kind=pick(8,((1,1),(3,4),(5,8),(6,10),(7,14),(8,71)))
    elif category==1: kind=pick(20,((3,31),(11,35),(16,36),(17,32),(18,33),(20,34)))
    elif category==2: kind=pick(6,((2,50),(4,48),(5,52),(6,53)))
    else: kind=category
    item=bytearray(Item.SIZE); item[I['type']]=kind; item[I['unidentified']]=6
    flag=0
    def byte(name,value): item[I[name]]=value&255
    def word(name,value): item[I[name]:I[name]+2]=(value&65535).to_bytes(2,'little')
    def names(values): item[I['name_ids']:I['name_ids']+3]=bytes(values)
    if kind<=37 or kind in (50,59,70,71):
        bonus=1+int(die(10)==10); byte('bonus',bonus)
        names((0,bonus+110,kind))
        if kind==7 and die(5)==5: flag=49
        if kind==31: names((bonus+110,48,kind)); byte('unidentified',4)
        if 32<=kind<=36: names((bonus+110,47,kind)); byte('unidentified',4)
        if kind==50: bonus=4; byte('bonus',bonus); names((107,90,50))
        if kind==59: names((bonus+110,49,46))
        weights={1:75,17:75,6:50,14:50,15:50,23:50,25:50,37:50,29:50,
                 9:125,8:100,16:100,24:100,70:150,31:150,71:175,4:10,50:10,
                 5:5,10:60,18:60,22:80,7:20,13:40,19:35,20:250,32:250,
                 33:400,34:300,35:350,36:450,28:1,59:1}
        word('weight',weights.get(kind,4)); byte('quantity',20 if kind==5 or kind not in weights else 0)
        word('value',bonus*{37:1250,30:75,32:1500,33:1500,34:1750,35:2000,36:2500,50:1500}.get(kind,1000))
    elif kind in (39,40):
        count=die(3); book=(3 if die(2)==1 else 2) if kind==39 else 0
        names((count+99,40 if book else 39,120 if book==3 else 119 if book==2 else 38))
        byte('bonus',1); word('weight',25); value=0
        known=game.assets.table('knownSpellTable')
        spans=(7,6,6,4) if book==3 else (8,3,6,7) if book==2 else (4,7,4,4)
        for n in range(count):
            level=die(4); entry=die(spans[level-1])-1
            item[I['powers']+n]=known[max(0,book-1)*40+(level-1)*10+entry]
            value+=level*150
        word('value',value); byte('unidentified',4|(16 if book==3 else 32) if book else 0)
    elif kind==48: flag=17 if die(8)<=5 else 1
    else: flag={52:33,53:9}[kind]
    if flag:
        import struct
        row=struct.unpack_from('<8H',game.assets.resident,51178+2*(flag-1))
        names(tuple(v&255 for v in row[:3])); byte('bonus',1); byte('save_bonus',1)
        word('weight',row[3]); word('value',row[4]); byte('quantity',0)
        item[I['powers']:I['powers']+3]=bytes(v&255 for v in row[5:])
    return item


READ_FIELDS = {
    0x7C15: ('abilities', 3, False), 0x7C18: ('abilities', 9, False),
    0x7C19: ('abilities', 11, False), 0x7C61: ('knight_order', 0, False),
    0x7C72: ('race', 0, True), 0x7C73: ('class', 0, True),
    0x7C76: ('hp_max', 0, False), 0x7C9B: ('saves', 1, False),
    0x7CA0: ('highest_level', 0, True), 0x7CB8: ('npc', 0, False),
    0x7CCC: ('levels', 2, True), 0x7CCD: ('levels', 7, True),
    0x7CD0: ('levels', 4, True), 0x7CD6: ('gender', 0, True),
    0x7CD8: ('alignment', 0, True), 0x7CF9: ('xp_per_hp', 0, False),
    0x7D19: ('hp', 0, False), 0x7D1B: ('move', 0, False),
}


def read_character(vm, address):
    s, c = vm.s, vm.s.selc()
    if address == 0x7F12: return s.dataset
    if address == 0x7F3E: return vm.m1(address)
    if address in (0x7EB1, 0x7EB4): return s.sel
    if c is None: return None
    if address in READ_FIELDS:
        name, index, signed = READ_FIELDS[address]
        return field(c, name, index, signed=signed)
    if 0x7CA5 <= address <= 0x7CAC: return field(c, 'thief_skills', address-0x7CA5)
    if address in range(0x7CBB, 0x7CC4, 2): return field(c, 'money', address-0x7CBB, width=2)
    if address == 0x7CF7: return field(c, 'xp_award', width=2)
    if address == 0x7CC9: return field(c, 'levels', 5, signed=True) + earlier_class(c)*field(c, 'former_levels', 5, signed=True)
    if address == 0x7D00: return 0 if s.g.get('A4D1') else {0: 1, 3: 6, 4: 5, 5: 4, 6: 3, 7: 7, 8: 2}.get(field(c, 'status'), 0)
    if address == 0x7D0C: return 0x81 if field(c, 'side') == 1 else 0x80 if field(c, 'side') == 0 and field(c, 'auto_combat') else 0
    if address == 0x7ECF:
        charisma = field(c, 'abilities', 11)
        return next((score for low, high, score in ((3, 7, (charisma-3)*5), (8, 12, 25),
                     (13, 15, 30+(charisma-13)*5), (16, 17, 50+(charisma-16)*5), (18, 25, 60))
                     if low <= charisma <= high), None)
    return None


def write_character(vm, address, value):
    s, c = vm.s, vm.s.selc()
    if address == 0x7C00:
        if not value: s.g['A4B7'] = 1
        return True
    if address == 0x7F12: s.dataset = ((value & 255)+1)//2; return True
    if address in (0x7F22, 0x7F24, 0x7F26):
        if value > 128: vm.load_wall(value & 127, (address-0x7F22)//2+1)
        return True
    if c is None: return False
    if 0x7C20 <= address <= 0x7C59: put(c, 'memorized', value, address-0x7C20)
    elif address in range(0x7CBB, 0x7CC4, 2): put(c, 'money', value, address-0x7CBB, width=2)
    elif address == 0x7CB8: put(c, 'npc', value-50 if value > 178 else value)
    elif address == 0x7CF7: put(c, 'xp_award', value, width=2)
    elif address == 0x7CF9: put(c, 'xp_per_hp', value)
    elif address == 0x7D19: put(c, 'hp', value)
    elif address == 0x7D00:
        if value == 1: put(c, 'status', 0); put(c, 'active', 1)
    elif address == 0x7D0C:
        if value in (0, 128, 129): put(c, 'side', int(value == 129)); put(c, 'auto_combat', int(bool(value)))
    else: return False
    return True


def wrapped_text(text, width=38):
    if width < 1: raise ValueError('text width must be positive')
    lines = []
    for paragraph in text.rstrip().splitlines():
        row = ''
        for match in re.finditer(r'[!,\-.:;?]*[^!,\-.:;? ]*(?:[!,\-.:;?]+| |$)', paragraph):
            token = match.group()
            if not token: continue
            if len(row)+len(token) > width:
                lines.append(row.rstrip()); row = ''; token = token.lstrip(' ')
            row += token
        lines.append(row.rstrip())
    return lines


class Geo:
    def __init__(self, records=None): self.records, self.map = records, None

    def load(self, s, ident):
        if self.records is None: raise BindingRequired('Champions Geo requires its records provider')
        self.map = Map(s.dataset, ident, record=self.records('GEO%d' % s.dataset)[ident])
        for key in tuple(s.g):
            if key.startswith('door '): del s.g[key]

    def resume(self, s, vm):
        if vm.is3d() and 0 < s.walls[0] < 0x8000: self.load(s, vm.m0(0x4BC5))

    def cell(self, s, x, y):
        if self.map is None or (s.block in (0, 80) and not (0 <= x < 16 and 0 <= y < 16)): return None
        return (0 if x > 15 else 15 if x < 0 else x, 0 if y > 15 else 15 if y < 0 else y)

    def attr(self, s, x, y):
        cell = self.cell(s, x, y)
        return self.map.attr(*cell) if cell else 0

    def wall(self, s, x, y, facing):
        cell = self.cell(s, x, y)
        return self.map.walls(*cell, facing) if cell else 0

    def passage(self, s, x, y, facing):
        cell = self.cell(s, x, y)
        if cell is None: return 0
        if not self.map.walls(*cell, facing): return 1
        return s.g.get('door %d %d %d' % (*cell, facing), self.map.passages(*cell, facing))

    def approach(self, s):
        if not s.r0[0xE6]:
            s.r1[0x2C1] = 2
            return 2
        x, y, distance = s.x, s.y, 0
        dx, dy = DELTAS[s.dir//2]
        while self.map and distance < 2 and 0 <= x < 16 and 0 <= y < 16 and not self.wall(s, x, y, s.dir):
            x, y, distance = x+dx, y+dy, distance+1
        return distance


class VM(retained.VM):
    def __init__(self, s, ask, geo=None, *, binding):
        super().__init__(s, ask, geo or Geo(), binding=binding)
        self.geo.records = binding.records

    def fetch(self):
        super().fetch()
        if self.cur in (0x22, 0x23):
            raise BindingRequired('Champions opcode %02X at %04X needs native rules' % (self.cur, self.pc))

    def op1D(self):
        self.pc = self.next
        def strength(c):
            levels = [field(c,'levels',i)+earlier_class(c)*field(c,'former_levels',i) for i in (0,5)]
            return (4*levels[0]+8*levels[1]+field(c,'hp')+5*max(0,field(c,'ac')-60)+5*max(0,field(c,'thac0')-39))//10
        self.setmem(self.a(1),sum(map(strength,self.s.party))&255)

    def op1E(self):
        self.pc = self.next
        attr = self.a(1) if self.t(1)==1 else self.v(1)
        found, members = 0, self.s.chars()
        if attr == 0:
            from .effects import has_effect
            values = [0]; found = int(any(has_effect(c,self.v(2)&255) is not None for c in members))
        elif attr == 0x7C19: values = [field(c,'abilities',11) for c in members]
        elif 0x7CA5 <= attr <= 0x7CAC: values = [field(c,'thief_skills',attr-0x7CA5) for c in members]
        elif attr == 0x7C9F: values = [field(c,'move') for c in members]
        else: return
        if not values: raise BindingRequired('Champions CHECK_PARTY has an empty native party')
        for i,value in enumerate((min(values),max(values),sum(values)//len(values),found),3): self.setmem(self.a(i),value)

    def op36(self):
        from . import rules
        from .records import Item, Effect, split_records
        self.pc = self.next
        if self.m1(0x7F3E) <= 7:
            ident = self.v(1)&255; stem = 'MON%d'%self.s.dataset
            c = rules.character(monster_record(self.binding.records,self.s.dataset,ident),
                [bytes(r) for r in split_records(self.binding.records(stem+'ITM').get(ident,b''),Item)],
                [bytes(r) for r in split_records(self.binding.records(stem+'SPC').get(ident,b''),Effect)],rid=ident)
            put(c,'creature_id',ident)
            slot = next(n for n in range(8) if all(field(p,'order')!=n for p in self.s.party))
            put(c,'order',slot); self.s.party.append(c); self.s.sel = len(self.s.party)-1
            self.set1(0x7F3E,self.m1(0x7F3E)+1)
            if field(c,'npc')>127: rules.recalc_class_stats(c,())
            self.icons[slot] = ('CPIC',ident,self.s.dataset)
        c = self.s.selc()
        put(c,'npc',(self.v(2)&255)//2|128); rules.recalc_stats(c)

    def op3F(self):
        from .effects import has_effect
        self.pc = self.next
        found = has_effect(self.s.selc(),self.v(1)&255) is not None
        self.flags = [int(found),int(not found),0,0,0,0]

    def op29(self):
        from .combat import has
        self.pc = self.next
        members = self.s.chars()
        speeds = [field(members[0],'move')]+[(field(c,'move')*(2 if has(c,39) else 1)//(2 if not has(c,39) and has(c,42) else 1))&255 for c in members]
        high,low = max(speeds),min(speeds)
        dest = self.a(4); responses = [self.v(i)&255 for i in range(5,10)]
        messages = self.strs[1:4]
        self.set1(0x7EC0,self.v(2)); self.set1(0x7EC1,min(self.v(2),self.geo.approach(self.s)))
        self.display = dict(kind='SPRIT',dataset=self.s.dataset,id=self.v(1)&255,pic=self.v(3)&255,head=None,menu=1)
        while True:
            distance = self.m1(0x7EC1); self.display['frame'] = distance
            text = next((messages[(distance+n)%3] for n in range(3) if messages[(distance+n)%3]),'')
            if text:
                if self.is3d(): self.clear_text()
                self.text_color = 10; self.out.append(text)
            parlay = not distance or not self.is3d()
            choice = self.ask('MENU',['COMBAT','WAIT','FLEE','PARLAY' if parlay else 'ADVANCE'],at=self.at,encounter=1)
            if choice==3 and parlay: choice=4
            response = responses[choice]
            if response==0: result = 2 if choice==2 and low >= (self.v(13)&255) else 1
            elif response==2:
                result = int(choice==0 and (self.v(14)&255)<=high)
                if not result: self.clear_text(); self.text_color = 10; self.out.append('The monsters flee.')
            elif choice==0: result=1
            elif choice==2: result=2
            elif not distance and (choice==4 or response==4): result=3
            else:
                if distance and (response!=1 or choice!=1): self.set1(0x7EC1,distance-1)
                else:
                    self.clear_text(); self.text_color = 10; self.out.append('Both sides wait.'); self.hold(16*3*self.delay()/1000)
                continue
            self.setmem(dest,result); return

    def script_damage(self, c, amount):
        from .combat import name
        if field(c,'status')==6: return
        self.out.append('\n'+name(c)+(' dies. ' if field(c,'hp')+10<amount else ' is hit FOR %d points of Damage.'%amount))
        remaining = field(c,'hp')-(amount&255)
        if remaining < -9 or remaining<=0 and field(c,'status')==1: put(c,'status',6)
        elif remaining<0: put(c,'status',5)
        elif remaining==0: put(c,'status',4)
        put(c,'hp',max(0,remaining) if field(c,'status') in (0,1) else 0)
        if field(c,'status') not in (0,1): put(c,'active',0)

    def op2E(self):
        from . import effects, magic
        from .combat import roll, signed
        self.pc = self.next
        flags,dice,sides,extra,save = (self.v(i)&255 for i in range(1,6))
        draw = lambda n,d,why: roll(self.host,n,d,'script DAMAGE '+why)
        amount = draw(dice,sides,'amount')+extra
        party = self.s.chars()
        target = 0 if flags&64 else draw(1,self.m1(0x7F3E),'initial target')-1
        if flags&128:
            targets = party if flags&64 else [self.s.selc() if save&128 else party[target]]
            for c in targets:
                no_save = bool(flags&32) if flags&64 else bool(save&128 and not save&7)
                kind = (save&7)-int(not flags&64 and bool(save&128))
                saved = not no_save and script_save(self.host,c,kind,flags&31)
                if not saved or flags&16: self.script_damage(c,amount)
        else:
            for _ in range(flags):
                c = party[draw(1,self.m1(0x7F3E),'attack target')-1]
                natural = draw(1,20,'attack')
                x = effects.Roll(attack=100 if natural==20 else natural)
                if natural>1:
                    effects.trigger_condition(self.host,16,c,x)
                    if signed(x.attack)>=0 and signed(x.attack)+save>field(c,'ac'): self.script_damage(c,amount)
                amount = draw(dice,sides,'amount')+extra
        self.s.party_dead = int(not any(field(c,'active') for c in party))
        if self.s.party_dead: self.clear_text(); self.out.append('The entire party is killed!')
        self.ask('MENU',['press <enter>/<return> to continue'],at=self.at,purpose='script damage',defeated=bool(self.s.party_dead))

    def op08(self):
        from .combat import roll
        self.pc = self.next
        ceiling = self.v(1) & 255
        value = roll(self.host,1,min(255,ceiling+1),'ECL%d/%d RANDOM %04X'%(self.s.dataset,self.s.block,self.at))-1
        self.setmem(self.a(2),value)

    def op11(self):
        if not hasattr(self.host,'script_log'): self.host.script_log=[]
        self.host.script_log.append((self.s.dataset,self.s.block,self.at,self.cur))
        super().op11()
    op12 = op11

    def op0B(self):
        from .combat import load_monsters
        values = [self.v(i)&255 for i in (1,2,3)]
        self.pc = self.next
        load_monsters(self.host, *values)

    def op1C(self):
        super().op1C()
        self.icon_slot = 8
        if 'cok.monster_icons' in self.s.g: self.s.g['cok.monster_icons'] = []
        self.s.g.pop('cok.undead_count',None)

    def setmem(self, address, value):
        if address == 0x4BE6 and self.m0(address) != (value & 65535):
            self.s.prev_mode, self.s.mode = self.s.mode, 4 if value else 3
            self.set0(address, value)
        else: super().setmem(address, value)
        if address == 0x3DE: self.sound_effect = value & 65535
        if address in (0x4BFD, 0x4BFE, 0xC059, 0xC05F): self.display['view_dirty'] = True

    def op0A(self):
        super().op0A()
        self.s.g['A4D1'] = self.s.g.get('8B6D', 0)

    def load_wall(self, rid, slot):
        super().load_wall(rid, slot)
        host = getattr(self, 'host', None)
        if getattr(host, 'walls_filed', ()):
            host.walls_filed = tuple(k for k in host.walls_filed if k != slot and self.s.walls[k-1] == 0)

    def op21(self):
        if self.cur == 0x21: return super().op21()
        self.pc = self.next
        ids = [self.v(i) & 255 for i in (1, 2, 3)]
        if ids[0] == 127: self.load_wall(0, 1)
        else:
            slots = (1, 3) if self.m0(0x4BE7) and self.m0(0x4BE8) else (1, 2, 3)
            for slot in slots:
                rid = ids[slot-1]
                self.load_wall(0xFFFF if rid == 255 or slot == 3 and rid == 127 else rid, slot)
    op37 = op21

    def op2D(self):
        self.pc = self.next
        address, s = self.a(1), self.s
        if address == 0x2E10:
            s.attr = self.geo.attr(s, s.x, s.y)
            s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
            if self.display.get('kind') or self.display.get('view_dirty'):
                self.display = {'kind': None, 'sky': s.r0[0xFD:0xFF]}
                self.paint_location()
        elif address == 0xC01E: self.step(); self.display['view_dirty'] = True
        elif address == 0xB203:
            if not hasattr(self.host, 'script_sounds'): self.host.script_sounds = []
            self.host.script_sounds.append(11 if getattr(self, 'sound_effect', 0) == 10 else 10)
        elif address == 0xC018:
            if not self.is3d(): s.ahead = self.geo.wall(s, s.x, s.y, s.dir)
        elif address == 0x6803:
            self.hold(self.delay()/10); self.display['frame'] = self.display.get('frame', 0)+1
        else: raise BindingRequired('Champions CALL %04X is unverified' % address)

    def op3E(self):
        self.pc = self.next; s = self.s
        if s.sel < len(s.party):
            gone = s.party.pop(s.sel); self.icons.pop(field(gone, 'order'), None)
            s.sel = max(0, s.sel-1); self.set1(0x7F3E, self.m1(0x7F3E)-1)
        s.g['47E7'] = s.sel

    def op10(self):
        self.pc = self.next
        text = ''.join(ch.upper() if 'a' <= ch <= 'z' else ch for ch in (self.ask('STRING', None, at=self.at) or '')[:40])
        self.setstr(self.a(2), text or ' ')

    def op24(self):
        self.pc = self.next
        if self.s.monsters:
            distance = self.geo.approach(self.s)
            self.set1(0x7EC1, min(distance, self.m1(0x7EC1)))
            self.service('combat', 'run')
            self.s.mode = 4 if self.is3d() else 3
            self.s.r1[0x2CA] &= 1
            if not self.is3d(): self.display = {'kind':'BIGPIC','id':121,'dataset':self.s.dataset}
            self.icon_slot = 8
            if self.s.party_dead: self.s.stop = 1
            return
        for address, name in ((0x7F6C, 'shop'), (0x7EE2, 'temple')):
            if self.getmem(address) == 1:
                self.setmem(address, 0)
                if name == 'shop': return self.service('shop', 'run', getattr(self, 'stock_id', None))
                return self.service('temple', 'run')
        from .combat import Battle
        Battle(self.host).treasure()
        self.s.mode = 4 if self.is3d() else 3
        self.s.r1[0x2CA] &= 1

    def op32(self):
        self.pc = self.next
        found = any(item[46] == (self.v(1) & 255) for c in self.s.chars() for item in c.items)
        self.flags = [int(found), int(not found), 0, 0, 0, 0]

    def op27(self):
        ident = self.v(8) & 255
        self.pc = self.next
        self.s.treasure_money = [self.v(i) & 65535 for i in range(1, 8)]
        if ident < 128:
            self.stock_id = ident
            raw = self.binding.records('ITEM%d' % self.s.dataset)[ident]
            if len(raw)%63: raise ValueError('partial Champions treasure item')
            self.s.treasure_items = [bytearray(raw[i:i+63]) for i in reversed(range(0, len(raw), 63))]+self.s.treasure_items
        elif ident < 255:
            from .shop import item_name
            for _ in range(ident-128):
                self.s.treasure_items.insert(0,random_treasure(self.host))
            for item in self.s.treasure_items: item_name(self.host,item)

    def op28(self):
        from . import inventory, shop
        from .combat import roll
        whole,percent,chance = (self.v(i)&255 for i in (1,2,3))
        self.pc = self.next
        for c in (self.s.chars() if whole else [self.s.selc()]):
            if c is None: continue
            shop.put_coins(c,[int(value*(100-percent)/100)&65535 for value in shop.coins(c)])
            remaining = chance
            for item in list(c.items):
                weight = int.from_bytes(item[shop.I['weight']:shop.I['weight']+2],'little')
                remaining = max(0,remaining-(90 if weight>255 else 50 if weight>24 else 0))
                if roll(self.host,1,100,'script ROB',self.s.chars().index(c)) <= remaining:
                    if item[shop.I['readied']]: inventory.toggle_ready(self.host,c,item)
                    c.items.remove(item)

    def op40(self):
        from . import rules, inventory
        self.pc = self.next
        target = self.v(1)&255
        for c in self.s.chars():
            for item in [item for item in c.items if item[46] == target]:
                if item[inventory.I['readied']]: inventory.toggle_ready(self.host, c, item)
                c.items.remove(item)
            put(c, 'item_count', len(c.items))
            rules.recalc_stats(c)

    def op41(self):
        party, amount = self.v(1)&255, self.v(2)&65535
        self.pc = self.next
        members = self.s.chars() if party else [self.s.selc()]
        for c in members:
            if c is None: continue
            count = sum(field(c,'levels',i,signed=True)>0 for i in range(8))
            if not count: raise BindingRequired('Champions experience award has a zero native class count')
            if field(c,'active'): put(c,'experience',field(c,'experience',width=4)+amount//count,width=4)
        self.clear_text(); self.text_color = 10
        self.out.append('Congratulations the party gains experience!' if party else 'Congratulations '+bytes(buffer(members[0])[1:1+buffer(members[0])[0]]).decode('cp437')+' gains experience!')
        self.hold(self.delay()/10)

    def delay(self):
        from .creation import game_setting, DELAY
        return game_setting(self.s, DELAY)

    def op3A(self):
        self.pc = self.next; self.hold(self.delay()/10)

    def hold(self, seconds):
        queue = getattr(getattr(self, 'host', None), 'presentation', None)
        if queue is None: return
        import copy
        s = self.s; shot = copy.copy(s)
        shot.r0, shot.r1, shot.party, shot.monsters, shot.walls, shot.g = type(s.r0)(s.r0), type(s.r1)(s.r1), list(s.party), list(s.monsters), list(s.walls), dict(s.g)
        queue.append(dict(kind='script-hold', delay=seconds, text=''.join(self.out[self.text_start:]), colour=getattr(self, 'text_color', 10),
                          state=shot, display=dict(self.display, head=self.display.get('head') if self.display.get('head') is not None else self.m1(0x7EE1)),
                          map=self.geo.map, walls_filed=tuple(getattr(self.host, 'walls_filed', ()))))

    def op38(self):
        self.pc = self.next
        if self.s.g.get('47E2'):
            self.s.sel = self.s.g.get('47E7', 0); self.s.g['47E2'] = 0
        if self.v(1) == 0:
            from . import creation
            creation.run(AuditedService(self.host,'creation'))
        elif self.v(1) == 9:
            pc = self.pc; camp(self.host); self.pc = pc
            if not self.m0(0x4C38): self.op00()

    def op3B(self):
        self.pc = self.next
        slot, member = 255, max(0, len(self.s.chars())-1)
        for i, c in enumerate(self.s.chars()):
            matches = [j for j in range(58) if field(c, 'memorized', j) == (self.v(1) & 255)]
            if matches: slot, member = matches[0], i; break
        self.setmem(self.a(2), slot); self.setmem(self.a(3), member)

    def paint_location(self):
        self.display['location'] = (self.s.x, self.s.y, self.s.dir)

    def advance_clock(self, amount, unit):
        from .effects import advance
        advance(self.host, amount & 255, unit)


def script_save(game, char, kind, bonus=0):
    from . import effects
    from .combat import roll, signed
    value = roll(game,1,20,'script saving throw')
    if value in (1,20): return value==20
    if field(char,'levels',5,signed=True)>0 and field(char,'robe_order'):
        moon = game.s.r0[(field(char,'robe_order')+0x1F8)&255]
        bonus += -1 if moon==0 else 1 if moon==2 else 0
    x = effects.Roll(save=(value+field(char,'save_bonus',signed=True)+signed(bonus))&255,save_type=kind)
    effects.trigger_condition(game,12,char,x)
    return field(char,'saves',kind)<=x.save


def finished(game):
    return False


def refresh(game):
    s, vm = game.s, game.vm
    if vm.is3d():
        s.attr, s.ahead = game.geo.attr(s, s.x, s.y), game.geo.wall(s, s.x, s.y, s.dir)
        vm.display.update(kind=None, sky=s.r0[0xFD:0xFF])
    vm.display.pop('blank', None)
    vm.paint_location()


def after_block(game):
    s, vm = game.s, game.vm
    for _ in range(256):
        s.restart = 0; s.attr = game.geo.attr(s, s.x, s.y)
        vm.set1(0x7ED5, 0); s.g['47E7'] = s.sel
        vm.run(vm.vec[4])
        if s.restart: continue
        vm.set0(0x4BF2, s.block)
        if s.mode == 4: refresh(game)
        vm.run(vm.vec[0])
        if s.restart: continue
        vm.run(vm.vec[1])
        if s.restart: continue
        s.sel = s.g['47E7']; s.prev_mode = s.mode
        return
    raise retained.Halt('Champions new-block transition limit')


def load_game(game, slot):
    from . import creation
    creation.load_game(game, slot)
    game.slot, game.vm.resuming = slot, True
    game.geo.resume(game.s, game.vm)


def boot(game):
    s, vm = game.s, game.vm
    if not isinstance(vm, VM): raise BindingRequired('Champions host must construct town.VM')
    s.mode, s.restart = (4 if vm.is3d() else 3), 0
    s.block = (vm.m0(0x4BF2) or 36) & 255
    vm.load_block(s.block); vm.init_vm(); game.entry = (s.dataset, s.block, vm.vec[4])
    vm.run(vm.vec[4])
    if s.restart: after_block(game)
    else: vm.set0(0x4BF2, s.block)
    vm.resuming = False


def camp(game):
    vm = game.vm
    vm.run(vm.vec[2])
    if service(game, 'camp', 'run'): vm.run(vm.vec[3])
    refresh(game)
    game.recently_saved = False


def turn(game):
    s, vm = game.s, game.vm
    if not any(field(c, 'active') for c in s.party): raise retained.Halt('Champions: no active party member')
    choices = ['forward', 'turn-left', 'turn-right', 'turn-around', 'look', 'search', 'camp', 'view', 'cast', 'char-up', 'char-down']
    if not vm.is3d(): choices = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest', 'camp']
    vm.paint_location()
    command = choices[game.ask('MOVE', choices, x=s.x, y=s.y, dir=s.dir)]
    vm.set1(0x7EC9, 0)
    if command in ('char-up', 'char-down'):
        s.sel = (s.sel+(-1 if command == 'char-up' else 1)) % len(s.party); return
    if command.startswith('turn-'):
        s.dir = (s.dir+{'turn-left': 6, 'turn-right': 2, 'turn-around': 4}[command])%8
        refresh(game); return
    if command == 'search': vm.set1(0x7ECA, vm.m1(0x7ECA)^1); return
    if command in ('view', 'cast'): return service(game, 'explore', command)
    vm.clear_text(); s.g['47E7'] = s.sel; vm.set0(0x4BF2, s.block)
    if command == 'camp': return camp(game)
    if command == 'look':
        vm.advance_clock(1, 2); keep = vm.m1(0x7ECA)&1; vm.set1(0x7ECA, 1)
        refresh(game); vm.run(vm.vec[1])
        if s.restart: after_block(game)
        vm.set1(0x7ECA, keep); return
    if vm.is3d():
        dx, dy = DELTAS[s.dir//2]
        vm.set1(0x7ED5, int(bool(game.geo.passage(s, s.x, s.y, s.dir)) and not (0 <= s.x+dx < 16 and 0 <= s.y+dy < 16)))
    else: s.dir = choices.index(command)
    vm.run(vm.vec[0])
    if s.restart: after_block(game); return
    vm.set0(0x4BF0, s.x); vm.set0(0x4BF1, s.y)
    move(game); refresh(game); vm.run(vm.vec[1])
    if s.restart: after_block(game)


def move(game):
    s, vm = game.s, game.vm
    if s.mode == 3:
        if vm.m1(0x7EC9) >= 255: return
        dx, dy = ((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1))[s.dir]
        for address, delta, bound in ((0x4BC3, dx, 37), (0x4BC4, dy, 14)):
            vm.set0(address+0x2D, vm.m0(address)); vm.set0(address, max(0, min(bound, vm.m0(address)+delta)))
        vm.advance_clock(12, 3); return
    if vm.m1(0x7EC9) >= 255: vm.set1(0x7EC9, 0); return
    passage = game.geo.passage(s, s.x, s.y, s.dir)
    if passage == 1 or passage in (2, 3) and door(game, passage):
        vm.step(); vm.advance_clock(1, 2 if vm.m1(0x7ECA)&1 else 1)
        s.g.update(bash=1, pick=1, knock=1)


def door(game, passage):
    from .combat import roll
    s = game.s
    thieves = any(field(c, 'levels', 6) or earlier_class(c) and field(c, 'former_levels', 6) for c in s.party)
    knock = [(c, j) for c in s.party for j in range(58) if field(c, 'memorized', j) == 31]
    options = ([key.title() for key, available in (('bash', True), ('pick', thieves), ('knock', bool(knock)))
                if available and s.g.get(key, 1)] + ['Exit'])
    if len(options) == 1:
        return False
    choice = options[game.ask('MENU', options, door=passage)]
    success = False
    if choice == 'Knock': put(knock[0][0], 'memorized', 0, knock[0][1]); success = True
    if choice == 'Pick':
        s.g['pick'] = 0
        if passage == 2: success = any(roll(game,1,100,'pick door') <= field(c, 'thief_skills', 1) and field(c, 'status') == 0 for c in s.party)
    if choice == 'Bash':
        for c in s.party:
            strength, extra = field(c, 'abilities', 1), field(c, 'strength_extra')
            odds = None
            if strength == 25: success = True; break
            if passage == 3:
                if strength == 18 and extra >= 91: odds = (6, 2 if extra == 100 else 1)
                elif 19 <= strength <= 23: odds = (6, (strength-19)//2+3)
                elif strength == 24: odds = (8, 7)
                else: s.g['bash'] = 0
            else:
                if 3 <= strength <= 17: odds = (6, 1 if strength <= 7 else 2 if strength <= 15 else 3)
                elif strength == 18: odds = (6, 3 if extra <= 50 else 4 if extra <= 99 else 5)
                elif 19 <= strength <= 24:
                    die = 8 if strength <= 20 else 10 if strength == 21 else 12 if strength <= 23 else 20
                    odds = (die, die-1)
            if odds and roll(game,1,odds[0],'bash door') <= odds[1]: success = True; break
    if success:
        dx, dy = DELTAS[s.dir//2]
        for x, y, f in ((s.x, s.y, s.dir), (s.x+dx, s.y+dy, (s.dir+4)%8)):
            if 0 <= x < 16 and 0 <= y < 16: s.g['door %d %d %d' % (x, y, f)] = 1
    return success


def play(game, limit=100_000):
    boot(game)
    while len(game.trace) < limit and not game.s.party_dead: turn(game)
    return 'DEFEAT' if game.s.party_dead else 'LIMIT'


class AuditedState:
    def __init__(self, game, reason): object.__setattr__(self,'game',game); object.__setattr__(self,'reason',reason)
    def __getattr__(self, key): return getattr(self.game.s,key)
    def __setattr__(self, key, value): setattr(self.game.s,key,value)
    def random(self, sides):
        from .combat import roll
        roll(self.game,1,sides,self.reason)
        return self.game.combat_log[-1]['faces'][0]-1


class AuditedService:
    def __init__(self, game, reason): object.__setattr__(self,'game',game); object.__setattr__(self,'s',AuditedState(game,reason))
    def __getattr__(self, key): return getattr(self.game,key)
    def __setattr__(self, key, value): setattr(self.game,key,value)


def service(game, unit, name, *arguments):
    if (unit, name) == ('explore', 'view'): return view_character(game)
    if (unit, name) == ('explore', 'cast'):
        if field(game.s.selc(),'status')==0:
            from .magic import cast_menu
            return cast_menu(AuditedService(game,'exploration cast'),game.s.selc())
        return
    if unit in ('camp', 'shop', 'training', 'temple', 'combat') and name == 'run':
        try: module = import_module('.'+unit, __package__)
        except ModuleNotFoundError as error:
            if error.name != __package__+'.'+unit: raise
            module = None
        if run := getattr(module, 'run', None):
            return run(AuditedService(game,unit) if unit in ('camp','shop','temple') else game, *arguments)
        if unit == 'shop': unit, name = 'shops', 'shop'
    if (unit, name) == ('camp', 'run'):
        raise BindingRequired('Champions service is not bound: camp.run')
    if unit == 'shops' and name in ('shop', 'temple'):
        mode, game.s.mode = game.s.mode, 1
        game.s.treasure_money = [0]*7
        try: return service_menu(game, name, 'SHOP_MENU' if name == 'shop' else 'TEMPLE')
        finally: game.s.mode = mode
    raise BindingRequired('Champions service is not bound: ' + unit + '.' + name)


SERVICE_TEXT = {
    'shop': ('GAME.OVR', 34457, 28, '144ab94a57bb2e9d3f98c47d3e540c500888b028555fbfc53f3648dd2224106e'),
    'temple': ('GAME.OVR', 24380, 29, 'e2ff451d5a226323cb9f783a011b871a4bffc4724edff78332ce898e516e9d4c'),
}


def service_text(game, name):
    source, offset, size, digest = SERVICE_TEXT[name]
    data = file_path(game.assets.root, source).read_bytes() if source else game.assets.resident
    raw = data[offset:offset+size]
    if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Champions service text differs: '+name)
    return raw[1:1+raw[0]].decode('cp437')


def service_menu(game, name, kind):
    options = service_text(game, name).split()+['char-up', 'char-down']
    while True:
        choice = options[game.ask(kind, options, service=name)]
        if choice == 'Exit': return
        if choice in ('char-up', 'char-down'):
            game.s.sel = (game.s.sel+(-1 if choice == 'char-up' else 1))%len(game.s.party)
        elif choice == 'View': view_character(game)
        else: raise BindingRequired('Champions %s: %s rules are not bound' % (name, choice))


def view_character(game):
    c = game.s.selc()
    try: module = import_module('.inventory', __package__)
    except ModuleNotFoundError as error:
        if error.name != __package__+'.inventory': raise
        module = None
    if view := getattr(module, 'view', None): return view(game, c)
    money = any(field(c, 'money', i*2, width=2) for i in range(1, 7))
    options = (['Items'] if c.items else []) + (['Spells'] if any(field(c, 'memorized', i) for i in range(58)) else [])
    if money and (field(c, 'npc') < 128 or not field(c, 'active') or field(c, 'status') == 1): options.append('Trade')
    if money: options.append('Drop')
    options.append('Exit')
    choice = options[game.ask('MENU', options, service='view')]
    if choice != 'Exit': raise BindingRequired('Champions character %s rules are not bound' % choice)


def test():
    from ._town_test import test as check
    return check(quick=True)
