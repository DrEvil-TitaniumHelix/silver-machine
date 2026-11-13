from sm.titles.ssb import data as ssb_data
from sm.titles.ssb import host, vm; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char, State
from sm.titles.ssb.units import magic as M
from pathlib import Path


def character(side=0):
    c=Char(bytes(439)); b=c.b; b[0x10:0x1C]=bytes([16]*12)
    b[0x6B]=6; b[0x6C]=5; b[0x111]=b[0x116]=b[0xEE]=6; b[0x113]=1
    b[0x6A]=b[0x1AA]=40; b[0x129]=b[0x1AB]=b[0x1AC]=50
    b[0x70]=b[0x131]=b[M.HP]=100; b[M.ACTIVE]=1; b[M.SIDE]=side
    b[0xED]=12; b[0xE7]=1; b[0xE8:0xED]=bytes([20]*5)
    b[0x121]=2; b[0x123]=1; b[0x125]=6
    return c


def fixture(combat=False, policy=None):
    g=host.Game.__new__(host.Game); g.s=State(); g.trace=[]; g.engines=True; g.hashing=True
    g.player=policy or (lambda kind,options,game,**info:0); g.geo=host.Geo()
    g.s.party=[character()]; g.s.monsters=[character(1),character(1)]; g.s.r0[0xE6]=1
    g.s.mode=5 if combat else 2; g.vm=vm.VM(g.s,g.ask,g.geo); g.vm.host=g
    g.s.g['test.positions']=((10,10),(12,10),(13,10)); g.s.g['test.tiles']=bytes([23]*1250)
    return g


class Geometry:
    def __init__(self,g):
        self.g=g

    def index(self,c):
        return self.g.s.chars().index(c)

    def position(self,c):
        return self.g.s.g['test.positions'][self.index(c)]

    def terrain(self,x,y):
        return self.g.s.g['test.tiles'][50*y+x]

    def set_terrain(self,x,y,n):
        b=bytearray(self.g.s.g['test.tiles']); b[50*y+x]=n; self.g.s.g['test.tiles']=bytes(b)

    def move(self,c,x,y):
        p=list(self.g.s.g['test.positions']); p[self.index(c)]=(x,y); self.g.s.g['test.positions']=tuple(p)

    def context(self):
        return {'position':self.position,'terrain':self.terrain,'set_terrain':self.set_terrain,'move':self.move}


def dice(g,values):
    it=iter(values); g.s.random=lambda n:next(it)-1


def formulas():
    g=fixture(); a,b,c=g.s.chars(); m=M._Magic(g)
    assert M.spell(15)[8]==0 and M.spell(47)[8]==2 and M.spell(66)[2]==0
    assert M.caster_level(a,15)==6
    a.b[0x116]=0; a.b[0x115]=10
    assert M.caster_level(a,15)==2 and M.caster_level(a,98)==3
    a.b[0x115]=0; a.b[0x114]=12
    assert M.caster_level(a,3)==12
    a.b[0x116]=6
    assert M.spell_range(a,15)==12 and M.spell_range(a,12)==3
    assert m.duration(1,a)==6 and m.duration(26,a)==3780 and m.duration(35,a)==360
    dice(g,[6,1,2,3,4,1,4]); assert m.duration(40,a)==60 and m.duration(57,a)==11 and m.duration(59,a)==80
    del g.s.random
    b.b[0x19A]=2; dice(g,[1,20,18,17])
    assert not m.save(b,4,100) and m.save(b,4,-100) and m.save(b,4) and not m.save(b,4)
    del g.s.random
    e=m.effect(b,1,6,3); assert m.effect(b,1,12,9) is e and rec.rdw(e,1)==12 and e[3]==3
    rec.wrw(e,1,0); m.effect(b,1,999,7); assert rec.rdw(e,1)==0
    assert m.effect(b,2,6,0,False,1,True) is None
    assert m.effect(b,2,6,0,False,2,True) is not None
    g.s.g['87D8']=15; dice(g,[1,2,3]); m.dispatch(a,15,[b]); assert b.b[M.HP]==91
    del g.s.random
    b.effects=[]; b.b[M.HP]=10; dice(g,[4]); m.dispatch(a,90,[b]); assert b.b[M.HP]==96
    del g.s.random
    b.b[M.HP]=90; dice(g,[1,1]); g.s.g['87D8']=66; m.dispatch(a,66,[b]); assert b.b[M.HP]==87
    del g.s.random
    b.b[M.HP]=100; g.s.g['87D8']=4; dice(g,[8,1,20]); m.dispatch(a,4,[b,c]); assert b.b[M.HP]==100 and c.b[M.HP]==100
    del g.s.random
    g.s.g['87D8']=0
    b.b[M.HP]=10; b.b[M.STATUS]=5; b.b[M.ACTIVE]=0
    assert m.heal(b,4) and (b.b[M.HP],b.b[M.STATUS],b.b[M.ACTIVE])==(14,0,1)
    b.b[M.STATUS]=7; assert not m.heal(b,50)
    g.s.mode=5; b.b[M.STATUS]=5; b.b[M.ACTIVE]=0; assert m.heal(b,1) and b.b[M.STATUS]==4 and b.b[M.ACTIVE]==0
    assert M.dispel_chance(10,8)==60 and M.dispel_chance(8,10)==46


def effects():
    g=fixture(); a,b,c=g.s.chars(); m=M._Magic(g)
    e=m.add(b,11,2,6,True); m.callback(b,e)
    assert b.b[M.SIDE]==0 and b.b[0xFF]==0xB3 and e[3]==102
    M.tick_effects(g,b,2); assert b.b[M.SIDE]==1 and b.b[0x1A9]==0 and not b.effects
    e=m.add(a,0x27,5,6); g.s.g.update({'87D6':3,'87D7':5})
    m.modifiers(a,18); m.modifiers(a,18)
    assert rec.rdw(a.b,0x6E)==1 and e[3]==22 and g.s.g['87D6']==12
    a.effects=[]; e=m.add(a,12,2,101); M.recalc_ability(g,a,0)
    assert (a.b[0x11],a.b[0x1C])==(18,100)
    M.tick_effects(g,a,2); assert a.b[0x11]==16
    e=m.add(a,14,2,7); M.recalc_ability(g,a,5); assert a.b[0x1B]==23
    g.vm.advance_clock(2,1); assert a.b[0x1B]==16 and not a.effects
    m.add(b,0x5D,0,255); g.s.g['87D5']=9; assert m.damage(b,10)==0
    b.effects=[]; m.add(b,0x14,10,6); assert m.damage(b,11,2,True)==2 and b.b[M.HP]==98
    b.effects=[]; m.add(b,0x3F,10,6); g.s.g['87D8']=47; assert m.damage(b,10)==0
    b.effects=[]; m.add(b,0x11,10,6); g.s.g['87D8']=15; assert m.damage(b,12)==0
    b.effects=[]; e=m.add(b,0x1C,20,0x26); g.s.g['87D8']=15; g.s.g['87DD']=0
    dice(g,[1]); assert m.damage(b,5)==5 and e[3]==0x26
    dice(g,[3]); assert m.damage(b,5)==0 and e[3]==0x16
    dice(g,[2]); assert m.damage(b,5)==0 and not b.effects
    del g.s.random
    b.b[0x1A5]=100; g.s.g['87D8']=10; g.s.g['87D4']=0; dice(g,[1])
    assert m.effect(b,11,20,6,True) is None
    del g.s.random; b.b[0x1A5]=0
    g.s.g['87D8']=0; m.add(a,0x2D,20,6); a.b[0x120]=2; dice(g,[18])
    assert m.save(b,4)
    del g.s.random
    a.effects=[]; m.add(b,0x37,0,255); b.b[M.HP]=0; b.b[M.ACTIVE]=0; b.b[M.STATUS]=6
    m.dispatch(a,26,[b]); assert b.b[M.HP]==1 and b.b[M.ACTIVE]==1 and {e[0] for e in b.effects}=={0x37,0x16,15}
    m.dispatch(a,67,[b]); assert not b.effects and b.b[M.STATUS]==0
    b.b[0x6B]=1; b.b[M.STATUS]=6; m.dispatch(a,75,[b]); assert b.b[M.STATUS]==6
    b.b[0x6B]=6; m.dispatch(a,75,[b]); assert b.b[M.STATUS]==0 and b.b[0x18]==15 and b.b[M.HP]==1
    b.effects=[]; c.effects=[]; m.add(b,1,20,1); m.add(c,1,20,1); g.s.g['87D8']=41
    dice(g,[1]); m.dispatch(a,41,[b,c]); del g.s.random
    assert not b.effects and len(c.effects)==1
    b.b[0x6B]=7; dice(g,[1]); m.area_effect(a,23,[b]); del g.s.random
    assert not b.effects
    b.b[0x15E]|=8; b.b[M.HP]=100; dice(g,[1,1,1,1]); m.dispatch(a,110,[b]); del g.s.random
    assert b.b[M.HP]==100


def menus():
    choices=iter([0,1,0,0])
    g=fixture(policy=lambda k,o,g,**i:next(choices)); a=g.s.party[0]
    a.b[0x73]=1; a.b[0x132]=2
    assert M.memorize(g,a); assert list(a.b[M.MEM:M.MEM+75]).count(0x83)==1 and M.rest_need(a)==255
    M.rest_spells(g,a,250); assert 0x83 in a.b[M.MEM:M.MEM+75]
    M.rest_spells(g,a,5); assert 3 in a.b[M.MEM:M.MEM+75] and 0x83 not in a.b[M.MEM:M.MEM+75]
    assert M.free_slots(a,3)==1
    a.b[0x132]=1; before=bytes(a.b); choices=iter([3,'done']); shown=[]
    def full_book(kind, options, game, **info):
        shown.append(tuple(options)); return options.index(next(choices))
    g.player=full_book
    assert not M.memorize(g,a) and bytes(a.b)==before
    assert shown==[('done',3),('done',3)]
    a.b[0x147]=1; it=bytearray(67); it[0x2E]=0x27; it[0x2F]=100; it[0x3C]=15; a.items=[it]
    choices=iter([0,0,0,0]); g.player=lambda k,o,g,**i:next(choices)
    assert M.scribe(g,a) and it[0x3C]==0x8F and not a.b[0x7F]
    assert 'magic.rest.0' not in g.s.g and M.rest_need(a)==255
    M.rest_spells(g,a,255); assert a.b[0x7F]==1 and not a.items
    a.b[M.MEM+2]=0x83; M.clear_marks(a); assert a.b[M.MEM+2]==0
    a.b[M.MEM:M.MEM+75]=bytes([3,3])+bytes(73); a.b[M.HP]=50
    g.player=lambda k,o,g,**i:len(o)-1
    assert not M.cast(g,a,3) and list(a.b[M.MEM:M.MEM+75]).count(3)==2
    g.player=lambda k,o,g,**i:0
    assert M.cast(g,a,3) and list(a.b[M.MEM:M.MEM+75]).count(3)==1 and a.b[M.HP]>50
    assert {x[1] for x in g.trace}>={'SPELL','LIST','TARGET'}


def ai_target_slots():
    from types import SimpleNamespace
    for order, expected in (((1,1,2),(1,2)), ((1,1,1),(1,)), ((1,2,1),(1,2))):
        g=fixture(True); chars=g.s.chars(); caster=chars[0]; caster.b[0x1A9]=1
        picks=iter(order); observed=[]; records=[[0]*23 for _ in chars]
        def choose(*args, **kwargs):
            i=next(picks); observed.append(i); return chars[i]
        g.combat=SimpleNamespace(targets=lambda *a,**k:chars[:], ai_pick_target=choose,
                                 record=lambda c:records[chars.index(c)])
        m=M._Magic(g,Geometry(g).context())
        assert [m.index(c) for c in m.pick(caster,23,True)]==list(expected)
        assert observed==list(order), 'duplicate must consume a slot without ending the remaining selection'
    g=fixture(True); caster=g.s.party[0]; caster.b[0x1A9]=1
    records=[[0]*23 for _ in g.s.chars()]; records[0][10]=1; searches=[]
    def empty_search(caster,bypass,reach,keep):
        searches.append((bypass,keep)); records[0][10]=-1; return None
    g.combat=SimpleNamespace(targets=lambda *a,**k:[caster],ai_pick_target=empty_search,
                            record=lambda c:records[g.s.chars().index(c)])
    assert M._Magic(g,Geometry(g).context()).pick(caster,61,True)==[]
    assert searches==[(False,False)] and records[0][10]==-1


def geometry():
    g=fixture(True); a,b,c=g.s.chars(); geo=Geometry(g); ctx=geo.context(); m=M._Magic(g,ctx)
    assert m.line((0,0),(2,1))==[(1,1),(2,1)]
    g.s.g.update({'87D8':34,'8D8B':12,'8D8C':10}); m.make_area(a,0x28,6)
    assert geo.terrain(12,10)==29 and len(g.s.g['magic.areas'])==1
    snapshot=g.s.copy(); M.tick_effects(g,a,6,context=ctx)
    assert geo.terrain(12,10)==23 and not g.s.g['magic.areas'] and snapshot.g['magic.areas']
    b.effects=[]; c.effects=[]; b.b[M.HP]=c.b[M.HP]=100; b.b[M.ACTIVE]=c.b[M.ACTIVE]=1
    g.s.g.update({'87D8':115,'8D8B':12,'8D8C':10}); m.make_area(a,0x64,1)
    g.s.seed=0; M.tick_effects(g,a,1,context=ctx)
    assert not g.s.g['magic.areas'] and b.b[M.HP]<100 and c.b[M.HP]<100 and geo.terrain(12,10)==23
    b.b[M.HP]=c.b[M.HP]=100; g.s.random=lambda n:0; geo.set_terrain(14,10,1)
    assert M.ssb_data.stexe()[0x1A9E+4]==255
    g.s.g.update({'87D8':51,'8D8B':12,'8D8C':10}); m.bolt(a,7,12,12,1)
    assert b.b[M.HP]==88 and c.b[M.HP]==76 and g.s.g['87DD']==0
    g=fixture(True); a,b,c=g.s.chars(); geo=Geometry(g); m=M._Magic(g,geo.context())
    g.s.g['test.positions']=((10,10),(18,10),(20,10)); g.s.g.update({'8D8B':18,'8D8C':10})
    assert m.cone(a,1,9)==[b], 'aiming farther must not extend the total breath range'
    g.s.g['test.positions']=((26,13),(28,12),(27,13)); c.b[M.SIDE]=a.b[M.SIDE]
    geo.set_terrain(31,10,1); g.s.g.update({'8D8B':28,'8D8C':12})
    seed=g.s.seed
    assert m.cone(a,3,9)==[b,c], 'breath cone must include the ally on its lower edge'
    assert g.s.seed==seed


def scribe_refusals():
    g=fixture(); a=g.s.party[0]; a.b[0x147]=a.b[0x80]=1
    first=bytearray(67); first[0x2E]=0x27; first[0x3C:0x3F]=bytes((15,111,16))
    second=bytearray(first); second[0x3C:0x3F]=bytes((15,0,0)); a.items=[first,second]
    answers=iter(((0,111),(0,16),(1,15),(0,15),'done','exit','yes')); purposes=[]
    def answer(kind,options,game,**info):
        purposes.append(info['purpose']); return options.index(next(answers))
    g.player=answer
    assert M.scribe(g,a) and first[0x3C]==143 and second[0x3C]==15
    assert first[0x3D:0x3F]==bytes((111,16)) and not a.b[0x7F]
    assert purposes==['scribe']*5+['scribe summary','scribe confirm']


def timers():
    g=fixture(); a=g.s.party[0]; a.b[M.HP]=50
    e=M.add_effect(g,a,0x3E,60,255,True); M.effect_callback(g,a,e)
    assert a.b[M.HP]==51 and len(a.effects)==2
    M.tick_effects(g,a,125)
    assert a.b[M.HP]==51 and not a.effects
    M.add_effect(g,a,1,0); M.add_effect(g,a,0x4F,5,255,True); g.s.g['87D5']=4
    M.tick_effects(g,a,15)
    assert [e[0] for e in a.effects]==[1] and rec.rdw(a.effects[0],1)==0


def bundles():
    answers=iter([0,0,0,0]); g=fixture(policy=lambda k,o,g,**i:next(answers)); a=g.s.party[0]
    a.b[0x147]=a.b[0x80]=1
    head=bytearray(67); head[0x2E]=0x49; head[0x39]=2
    first=bytearray(67); first[0x2E]=0x27; first[0x2F]=100; first[0x3C]=15
    second=bytearray(first); second[0x3C]=16; a.items=[head,first,second]
    assert M.scribe(g,a) and first[0x3C]==0x8F
    M.rest_spells(g,a,255)
    assert a.b[0x7F]==1 and a.items==[second] and a.b[0x160]==1
    M.add_effect(g,a,0x24,0); a.b[M.ACTIVE]=0; g.s.r0[0xE5]=1
    M.remove_curse(g,a); assert not rec.has_effect(a,0x24)


def dispatch_smoke():
    for sid in range(1,118):
        histories=[]
        for _ in range(2):
            combat=bool(M.spell(sid)[11]); g=fixture(combat); a,b,c=g.s.chars(); ctx=Geometry(g).context()
            g.s.seed=123456; g.s.g['87D8']=sid; g.s.g['8D8B']=12; g.s.g['8D8C']=10
            a.b[M.MEM]=sid; a.b[M.HP]=50; b.b[M.HP]=50
            M._Magic(g,ctx).dispatch(a,sid,[b,c]); histories.append((g.s.hash(g.vm),g.trace))
        assert histories[0]==histories[1], ('dispatch replay',sid)
    for typ in range(1,0x72):
        if typ in (0x53,0x68): continue
        g=fixture(True); a,b,c=g.s.chars(); m=M._Magic(g,Geometry(g).context()); m.put(a,10,b)
        e=m.add(a,typ,10,6,True); m.callback(a,e); m.remove(a,typ,e)


def replay():
    traces=[]
    for _ in range(2):
        g=fixture(); a=g.s.party[0]; a.b[M.MEM:M.MEM+3]=bytes((3,12,14)); a.b[M.HP]=50
        for sid in (3,12,14): assert M.cast(g,a,sid)
        traces.append((g.trace,g.s.hash(g.vm)))
    assert traces[0]==traces[1] and len(traces[0][0])==2


def gaze_sides():
    for caster_side in (0, 1):
        for victim_side in (0, 1):
            g=fixture(True); caster,victim=g.s.chars()[:2]
            caster.b[M.SIDE]=caster_side; victim.b[M.SIDE]=victim_side
            m=M._Magic(g,Geometry(g).context()); m.pick=lambda *args:[victim]
            rolls=[]; g.s.random=lambda bound:rolls.append(bound) or 0
            m.special(caster,0x3A)
            opposing=caster_side!=victim_side
            assert rolls==([20] if opposing else [])
            assert (victim.b[M.STATUS]==7)==opposing
    g=fixture(True); caster,victim=g.s.chars()[:2]
    m=M._Magic(g,Geometry(g).context()); m.pick=lambda *args:[victim]
    rolls=[]; g.s.random=lambda bound:rolls.append(bound) or 0
    m.special(caster,0x51)
    assert rolls==[100,8,8,8,8,20] and victim.b[M.HP]==96


def effect_fixes():
    from sm.titles.ssb.units import combat as C
    g=fixture(); a,b,c=g.s.chars(); m=M._Magic(g); said=lambda text:any(text in line for line in g.vm.out)
    b.b[0x1A5]=100; rolls=[]; g.s.random=lambda n:rolls.append(n) or 0
    g.s.g.update({'87D3':11,'87D5':9}); assert m.damage(b,10)==0 and rolls==[100]
    del rolls[:]; g.s.g.update({'87D3':11,'87D5':1}); assert m.damage(b,10)==10 and not rolls
    del rolls[:]; g.s.g.update({'87D3':0,'87D5':9}); assert m.damage(b,10)==10 and not rolls
    del rolls[:]; g.s.g.update({'87D3':11,'87D5':9}); assert m.damage(b,10)==0 and rolls==[100]
    del rolls[:]; g.s.g.update({'87D4':0,'87D5':0}); assert m.effect(b,0x34,10,6,False,1) is None and rolls==[100]
    del rolls[:]; g.s.g.update({'87D4':4,'87D5':0}); assert m.effect(b,0x34,10,6,False,1) is not None and not rolls
    b.effects=[]; g.s.g['87D4']=0
    del g.s.random; b.b[0x1A5]=0; g.s.g['87D3']=0
    g.s.g['87D5']=0; m.damage(b,1); assert said('takes 1 point of damage from Magic')
    dice(g,[20]); assert m.save(b,4) and g.s.g['87E8']==1
    dice(g,[1]); assert not C.saving_throw(g,b,4) and g.s.g['87E8']==0
    dice(g,[20]); assert C.saving_throw(g,b,4) and g.s.g['87E8']==1
    dice(g,[1]); saved=m.save(b,4); del g.s.random
    m.add(b,0x32,10,0); g.s.g['87D5']=1; assert not saved and m.damage(b,5,2,saved)==10
    b.effects=[]; g.s.g['87D5']=0
    b.b[0x15D]=1; m.add(a,4,10,0); e=m.add(a,0x20,10,0); m.put(a,10,b)
    dice(g,[20]); m.callback(a,e); assert len(a.effects)==2 and b.b[M.STATUS]==0 and said('resists dispel evil')
    dice(g,[1]); m.callback(a,e); del g.s.random
    assert not a.effects and b.b[M.STATUS]==8 and said('is dispelled')
    g=fixture(); a,b,c=g.s.chars(); m=M._Magic(g); g.s.sel=0; table=ssb_data.items_table()
    bow=next(t for t in range(1,64) if table[16*t]==0 and table[16*t+14]&0x99==9)
    launcher=bytearray(67); launcher[0x2E]=bow; launcher[0x34]=1; launcher[0x32]=1
    arrows=bytearray(67); arrows[0x2E]=0x1E; arrows[0x34]=1
    a.items=[launcher,arrows]; assert m.weapon(a) is arrows
    e=m.add(b,0x67,0,255); g.s.g['87D4']=5; m.callback(b,e); assert g.s.g['87D4']==0
    launcher[0x32],arrows[0x32]=0,1; g.s.g['87D4']=5; m.callback(b,e); assert g.s.g['87D4']==5
    a.items=[]; m.callback(a,m.add(a,0x17,10,0)); assert len(a.items)==1 and a.items[0][0x34]==0
    d=character(); d.b[0x111:0x11F]=bytes(14); d.b[0x11A]=5; d.b[0xEF]=5; d.b[0x116]=3; d.b[0x18]=16; d.b[0x131]=30
    M.recalc_ability(g,d,4); assert d.b[0x70]==40, d.b[0x70]
    d=character(); d.b[0x1C]=d.b[0x1D]=0; m.add(d,0x0C,10,51); m.add(d,0x26,10,108)
    M.recalc_ability(g,d,0); assert (d.b[0x11],d.b[0x1C])==(18,60), (d.b[0x11],d.b[0x1C])
    g=fixture(True); a,b,c=g.s.chars(); geo=Geometry(g); tiles={}; g.s.g['combat.bodies']=[]
    class Arena:
        def tile(self,x,y):
            return tiles.get((x,y),0x17)
        def set_tile(self,x,y,v):
            tiles[(x,y)]=v
        def remove(self,ch):
            x,y=geo.position(ch); g.s.g['combat.bodies'].append([geo.index(ch),x,y,self.tile(x,y)]); self.set_tile(x,y,0x1E)
    m=M._Magic(g,{'position':geo.position,'get':lambda ch,field:a if field==10 else 0,'set':lambda *args:None}); m.fight=Arena()
    g.s.g['87DF']=80; dice(g,[1]); m.callback(c,m.add(c,0x42,0,255)); del g.s.random
    said=lambda text:any(text in line for line in g.vm.out)
    assert g.s.g['combat.bodies']==[[0,13,10,0x17]] and tiles=={(10,10):0x17,(13,10):0x1E} and a.b[M.STATUS]==6
    assert said('is swallowed whole') and said('is killed') and said('belches in satisfaction')


def spell_rules():
    g=fixture(True); a,b,c=g.s.chars()
    armor=bytearray(67); armor[0x34]=1
    armor[0x2E]=next(t for t in range(1,128) if t not in (0x1E,0x0C,0x27,0x28,0x49) and rec._T(bytearray(0x2E)+bytes([t])+bytes(20),0)==2)
    assert M.can_cast(a,15,False,True), 'unarmored human mage casts in combat'
    a.items=[armor]; assert rec.readied(a)[2] is armor
    assert not M.can_cast(a,15,False,True) and M.can_cast(a,15,False,False), 'armored human mage: camp only'
    a.b[0x6B]=1; assert M.can_cast(a,15,False,True), 'the armor rule is for humans only'
    a.b[0x6B]=6; assert M.can_cast(a,3,False,True)
    a.b[M.MEM]=19; a.b[M.MEM+1]=3; assert M.legal_spells(a,True)==[3] and M.legal_spells(a,False)==[3,19]
    a.b[0x1A9]=1; assert M.legal_spells(a,True)==[3,19], 'computer-controlled casters are not gated'
    a.b[0x1A9]=0; a.b[0x15]=8; assert not M.can_cast(a,3) and M.legal_spells(a,False)==[19], 'cleric list needs WIS above 8'
    a.b[0x15]=16; a.b[0x13]=8; assert not M.can_cast(a,15), 'mage list needs INT above 8'
    a.b[0x13]=16; a.b[0x111]=a.b[0x116]=0; a.b[0x117]=11
    assert M.can_cast(a,15,True) and not M.can_cast(a,15,False) and not M.can_cast(a,3,True), 'thief above 10: mage scrolls only'
    assert not M.can_cast(a,62), 'item powers are never cast from memory'
    g=fixture(); a=g.s.party[0]; a.b[0x111]=0
    scroll=bytearray(67); scroll[0x2E]=0x27; scroll[0x35]=1; scroll[0x3C:0x3F]=bytes((15,3,16)); other=bytearray(scroll); a.items=[scroll,other]
    assert M.scroll_spells(a)==[] and scroll[0x35]==1, 'unidentified scroll lists nothing'
    M.add_effect(g,a,16,10)
    assert M.scroll_spells(a,(0,))==[(0,0x3C,15)] and scroll[0x35]==0 and other[0x35]==1
    assert M.scribe_scrolls(a)==[(0,0x3C,15),(1,0x3C,15)]
    g=fixture(True); a,b,c=g.s.chars(); geo=Geometry(g); m=M._Magic(g,geo.context())
    g.s.g.update({'87D8':34,'8D8B':20,'8D8C':20}); m.make_area(a,0x28,6)
    assert all(geo.terrain(x,y)==29 for x,y in ((20,20),(21,20),(21,21),(20,21))), 'cloud needs no occupant'
    geo.set_terrain(31,5,1); g.s.g.update({'87D8':115,'8D8B':31,'8D8C':5}); m.make_area(a,0x64,1)
    assert geo.terrain(31,5)==1, 'no blast marker on a wall'
    g=fixture(); a=g.s.party[0]; a.b[M.MEM]=5; M.add_effect(g,a,0x19,0,12); M.add_effect(g,a,0x19,0,12)
    assert M.cast(g,a,5) and not rec.has_effect(a,0x19) and ' casts ' in ''.join(g.vm.out)
    g=fixture(); a=g.s.party[0]; a.b[M.MEM]=5; a.b[M.HP]=50; M.add_effect(g,a,0x44,0)
    assert not M.cast(g,a,5) and a.b[M.MEM]==5
    assert M.cast(g,a,62,consume=False) and a.b[M.HP]>50 and ' casts ' not in ''.join(g.vm.out)
    seen=[]
    def cancel(kind,options,game,**info):
        seen.append(' casts ' in ''.join(game.vm.out)); return len(options)-1
    g=fixture(policy=cancel); a=g.s.party[0]; a.b[M.MEM]=3
    assert not M.cast(g,a,3) and seen==[True] and a.b[M.MEM]==3
    g=fixture(); a=g.s.party[0]; rolls=[4,6,8]; g.s.random=lambda n:rolls.pop(0)-1
    M._Magic(g).dispatch(a,35,[a]); e=next(e for e in a.effects if e[0]==0x26)
    assert not rolls and e[3]==108
    g=fixture(); a=g.s.party[0]; a.b[0x111]=a.b[0x113]=0; rolls=[3]; g.s.random=lambda n:rolls.pop(0)-1
    M._Magic(g).dispatch(a,35,[a]); assert not rolls and next(e for e in a.effects if e[0]==0x26)[3]==103
    g=fixture(); a=g.s.party[0]; dice(g,[1]); M._Magic(g).dispatch(a,59,[a])
    assert 'gains Giant Strength' in ''.join(g.vm.out)
    for answer,shown in ((0,True),(1,False)):
        g=fixture(policy=lambda k,o,game,answer=answer,**i:answer); a=g.s.party[0]; M._Magic(g).dispatch(a,85,[a])
        assert ('is protected' in ''.join(g.vm.out))==shown and rec.has_effect(a,0x32 if shown else 0x36)
    asked=[]
    g=fixture(policy=lambda k,o,game,**i:asked.append((o,i.get('prompt'))) or 0); a=g.s.party[0]
    M._Magic(g).dispatch(a,113,[a])
    assert asked==[(['yes','no'],'cast cure anyway: ')] and 'is not stoned.' in ''.join(g.vm.out)
    g=fixture(True,policy=lambda k,o,game,**i:asked.append(0) or 0); a=g.s.party[0]; M._Magic(g,Geometry(g).context()).dispatch(a,113,[a])
    assert len(asked)==1, 'the question is asked in camp only'
    import inspect
    assert "'cold'" in inspect.getsource(M.breath_weapon) and "'memorize these spells?'" in inspect.getsource(M.memorize)


def check():
    formulas(); effects(); menus(); ai_target_slots(); geometry(); timers(); bundles(); scribe_refusals(); dispatch_smoke(); gaze_sides(); effect_fixes(); spell_rules(); replay()


def derived_camp(recorded=None):
    from sm.titles.ssb import route, resolve
    replay_rows=iter(recorded) if recorded is not None else None
    phases={'root':0,'magic':0,'cast':False}

    def policy(kind,options,g,**info):
        if kind=='TREASURE': resolve.resolve(kind,g)
        if replay_rows is not None:
            row=next(replay_rows); assert row[1]==kind; return row[6]
        if kind=='CREATE_MENU': return options.index('begin')
        if kind=='CAMP_MENU':
            purpose=info.get('purpose')
            if purpose=='resting': return options.index('continue')
            if purpose=='rest duration': return options.index('rest')
            key='magic' if purpose=='magic' else 'root'
            actions=('memorize','rest','cast','exit') if key=='magic' else ('select','magic','exit')
            action=actions[phases[key]]; phases[key]+=1
            if key=='root' and action=='exit':
                assert all(rec.has_effect(c,1) for c in g.s.party)
                assert 1 not in g.s.party[4].b[M.MEM:M.MEM+75]; phases['cast']=True
            return options.index(action)
        if kind=='TARGET' and info.get('purpose')=='party member': return options.index(4)
        if kind=='SPELL':
            if info.get('purpose')=='memorize':
                return options.index('done' if 0x81 in g.s.selc().b[M.MEM:M.MEM+75] else 1)
            return 0
        if kind=='COMBAT_ACTION': return options.index('quick') if 'quick' in options else options.index('done')
        if kind=='MENU' and info.get('action')=='continue-battle': return options.index('end')
        if kind=='MENU' and info.get('action')=='done': return options.index('quit')
        return 0

    g=host.Game(policy,engines=True); g.boot()
    steps,_=route.load_steps(str(Path(route.ROOT)/'herdr/route/derived.json'))
    assert (g.s.dataset,g.s.block)==tuple(steps[0]['block'])
    g.camp()
    assert recorded is not None or phases['cast']
    assert any(t[1]=='SPELL' for t in g.trace) and g.s.g['camp.rested']==1
    return g


def route_checks():
    import json,time
    from sm.titles.ssb import route, player
    root=Path(route.ROOT); started=time.perf_counter()
    a=derived_camp(); b=derived_camp(a.trace)
    assert a.trace==b.trace and a.s.hash(a.vm)==b.s.hash(b.vm)
    print('derived engines=True camp: memorize/rest/cast, decisions=%d replay=equal'%len(a.trace))
    for name,steps,answers in (
        ('derived',json.loads((root/'herdr/route/derived.json').read_text()),json.loads((root/'local/answers_derived.json').read_text())),
        ('walkthrough',*route.load_steps())):
        result,g=route.play(steps,answers); assert result=='DONE',(name,result)
        result2,h=player.run([t[6] for t in g.trace])
        assert result2=='DONE' and g.trace==h.trace and g.s.hash(g.vm)==h.s.hash(h.vm),(name,result2,'replay differs')
        print('%s engines=False: DONE decisions=%d replay=equal'%(name,len(g.trace)))
    print('magic route checks: %.2fs'%(time.perf_counter()-started))


if __name__=='__main__':
    check(); print('magic formula/effect/dispatch/replay checks: PASS')
    if '--routes' in __import__('sys').argv: route_checks()
