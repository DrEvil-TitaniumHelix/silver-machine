"""PORT2 V-checks against ENGINE_READ2_g2/g3 and ENGINE_READ_w6.

Synthetic expectations cover formulas, compiled quirks, effect callbacks and a
hashed Game.ask replay. --routes additionally exercises magic at a derived-route
camp and completes both existing resolver routes, with replay equality.
"""
from sm.titles.ssb import data as ssb_data
from sm.titles.ssb import host, vm; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char, State
from sm.titles.ssb.units import magic as M
from pathlib import Path


def character(side=0):
    """ov12:09BF/RECORD.md synthetic active record with six paired abilities."""
    c=Char(bytes(439)); b=c.b; b[0x10:0x1C]=bytes([16]*12)
    b[0x6B]=6; b[0x6C]=5; b[0x111]=b[0x116]=b[0xEE]=6; b[0x113]=1
    b[0x6A]=b[0x1AA]=40; b[0x129]=b[0x1AB]=b[0x1AC]=50
    b[0x70]=b[0x131]=b[M.HP]=100; b[M.ACTIVE]=1; b[M.SIDE]=side
    b[0xED]=12; b[0xE7]=1; b[0xE8:0xED]=bytes([20]*5)
    b[0x121]=2; b[0x123]=1; b[0x125]=6
    return c


def fixture(combat=False, policy=None):
    """ov23:1403 fixture uses real Game.ask and VM position hashing."""
    g=host.Game.__new__(host.Game); g.s=State(); g.trace=[]; g.engines=True; g.hashing=True
    g.player=policy or (lambda kind,options,game,**info:0); g.geo=host.Geo()
    g.s.party=[character()]; g.s.monsters=[character(1),character(1)]; g.s.r0[0xE6]=1
    g.s.mode=5 if combat else 2; g.vm=vm.VM(g.s,g.ask,g.geo); g.vm.host=g
    g.s.g['test.positions']=((10,10),(12,10),(13,10)); g.s.g['test.tiles']=bytes([23]*1250)
    return g


class Geometry:
    """ov33:0483/10FA adapter with all map state immutable in State.g."""
    def __init__(self,g):
        """ov33:0000 map frame."""
        self.g=g

    def index(self,c):
        """ov33:0C28 stable record index."""
        return self.g.s.chars().index(c)

    def position(self,c):
        """ov33:0BB0/0BD8 position accessor."""
        return self.g.s.g['test.positions'][self.index(c)]

    def terrain(self,x,y):
        """ov33:0483 terrain accessor."""
        return self.g.s.g['test.tiles'][50*y+x]

    def set_terrain(self,x,y,n):
        """ov23:2CFB cloud paint."""
        b=bytearray(self.g.s.g['test.tiles']); b[50*y+x]=n; self.g.s.g['test.tiles']=bytes(b)

    def move(self,c,x,y):
        """ov33:10FA movement state."""
        p=list(self.g.s.g['test.positions']); p[self.index(c)]=(x,y); self.g.s.g['test.positions']=tuple(p)

    def context(self):
        """ov25:0423 callback adapter used to test independent of c1 implementation."""
        return {'position':self.position,'terrain':self.terrain,'set_terrain':self.set_terrain,'move':self.move}


def dice(g,values):
    """ov25:11C6 die oracle, one-based expected values; restore after each check."""
    it=iter(values); g.s.random=lambda n:next(it)-1


def formulas():
    """V-check ov23:0F97/23DC/304E/4290; ov25:1137/20C8/21BF; ov26:2E86."""
    g=fixture(); a,b,c=g.s.chars(); m=M._Magic(g)
    assert M.spell(15)[8]==0 and M.spell(47)[8]==2 and M.spell(66)[2]==0
    assert M.caster_level(a,15)==6
    a.b[0x116]=0; a.b[0x115]=10
    assert M.caster_level(a,15)==2 and M.caster_level(a,98)==3
    a.b[0x115]=0; a.b[0x114]=12
    assert M.caster_level(a,3)==12  # bytes 2F21..2F3A: full paladin level
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
    g.s.g['87D8']=15; dice(g,[1,2,3]); m.dispatch(a,15,[b]); assert b.b[M.HP]==91  # 3d4+3 at level 6
    del g.s.random
    b.effects=[]; b.b[M.HP]=10; dice(g,[4]); m.dispatch(a,90,[b]); assert b.b[M.HP]==96  # Barkskin -> Heal, max-1d4
    del g.s.random
    b.b[M.HP]=90; dice(g,[1,1]); g.s.g['87D8']=66; m.dispatch(a,66,[b]); assert b.b[M.HP]==87  # no touch, 2d8+1
    del g.s.random
    b.b[M.HP]=100; g.s.g['87D8']=4; dice(g,[8,1,20]); m.dispatch(a,4,[b,c]); assert b.b[M.HP]==100 and c.b[M.HP]==100
    del g.s.random  # missed touch zeroed the argument for the second target too
    g.s.g['87D8']=0
    b.b[M.HP]=10; b.b[M.STATUS]=5; b.b[M.ACTIVE]=0
    assert m.heal(b,4) and (b.b[M.HP],b.b[M.STATUS],b.b[M.ACTIVE])==(14,0,1)
    b.b[M.STATUS]=7; assert not m.heal(b,50)
    g.s.mode=5; b.b[M.STATUS]=5; b.b[M.ACTIVE]=0; assert m.heal(b,1) and b.b[M.STATUS]==4 and b.b[M.ACTIVE]==0
    assert M.dispel_chance(10,8)==60 and M.dispel_chance(8,10)==46


def effects():
    """V-check ov14 charm/haste/immunity/poison timers, ov25 expiry, recalc and auras."""
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
    g.vm.advance_clock(2,1); assert a.b[0x1B]==16 and not a.effects  # Foreman engines hook
    m.add(b,0x5D,0,255); g.s.g['87D5']=9; assert m.damage(b,10)==0
    b.effects=[]; m.add(b,0x14,10,6); assert m.damage(b,11,2,True)==2 and b.b[M.HP]==98
    b.effects=[]; m.add(b,0x3F,10,6); g.s.g['87D8']=47; assert m.damage(b,10)==0
    b.effects=[]; m.add(b,0x11,10,6); g.s.g['87D8']=15; assert m.damage(b,12)==0
    b.effects=[]; e=m.add(b,0x1C,20,0x26); g.s.g['87D8']=15; g.s.g['87DD']=0
    assert m.damage(b,5)==0 and e[3]==0x16
    assert m.damage(b,5)==0 and not b.effects
    b.b[0x1A5]=100; g.s.g['87D8']=10; g.s.g['87D4']=0; dice(g,[1])
    assert m.effect(b,11,20,6,True) is None
    del g.s.random; b.b[0x1A5]=0
    g.s.g['87D8']=0; m.add(a,0x2D,20,6); a.b[0x120]=2; dice(g,[18])
    assert m.save(b,4)  # out-of-combat protection aura adds 2
    del g.s.random
    a.effects=[]; m.add(b,0x37,0,255); b.b[M.HP]=0; b.b[M.ACTIVE]=0; b.b[M.STATUS]=6
    m.dispatch(a,26,[b]); assert b.b[M.HP]==1 and b.b[M.ACTIVE]==1 and {e[0] for e in b.effects}=={0x37,0x16,15}
    m.dispatch(a,67,[b]); assert not b.effects and b.b[M.STATUS]==0
    b.b[0x6B]=1; b.b[M.STATUS]=6; m.dispatch(a,75,[b]); assert b.b[M.STATUS]==6  # elves cannot be raised
    b.b[0x6B]=6; m.dispatch(a,75,[b]); assert b.b[M.STATUS]==0 and b.b[0x18]==15 and b.b[M.HP]==1
    # Dispel's outer loop repeats the FIRST target, leaving the second untouched (g2:336B).
    b.effects=[]; c.effects=[]; m.add(b,1,20,1); m.add(c,1,20,1); g.s.g['87D8']=41
    dice(g,[1]); m.dispatch(a,41,[b,c]); del g.s.random
    assert not b.effects and len(c.effects)==1
    # Hold Person refuses race 0/7; death magic respects +15E bit 3.
    b.b[0x6B]=7; dice(g,[1]); m.area_effect(a,23,[b]); del g.s.random
    assert not b.effects
    b.b[0x15E]|=8; b.b[M.HP]=100; dice(g,[1,1,1,1]); m.dispatch(a,110,[b]); del g.s.random
    assert b.b[M.HP]==100


def menus():
    """V-check ov18:0744/0E3D/10A7 and ov22:089C/095E rest completion/consumption."""
    choices=iter([0,1,0,0])  # ov18:0FC8..0FD8 reviews pending spells before the Yes/No answer.
    g=fixture(policy=lambda k,o,g,**i:next(choices)); a=g.s.party[0]
    a.b[0x73]=1; a.b[0x132]=2
    assert M.memorize(g,a); assert list(a.b[M.MEM:M.MEM+75]).count(0x83)==1 and M.rest_need(a)==255
    M.rest_spells(g,a,250); assert 0x83 in a.b[M.MEM:M.MEM+75]
    M.rest_spells(g,a,5); assert 3 in a.b[M.MEM:M.MEM+75] and 0x83 not in a.b[M.MEM:M.MEM+75]
    assert M.free_slots(a,3)==1
    # ov18:0ED7/0F79: even a full book opens; selecting a full level changes nothing.
    a.b[0x132]=1; before=bytes(a.b); choices=iter([3,'done']); shown=[]
    def full_book(kind, options, game, **info):
        shown.append(tuple(options)); return options.index(next(choices))
    g.player=full_book
    assert not M.memorize(g,a) and bytes(a.b)==before
    assert shown==[('done',3),('done',3)]
    # Scroll copying consumes the power only after the full sleep+study interval.
    a.b[0x147]=1; it=bytearray(67); it[0x2E]=0x27; it[0x2F]=100; it[0x3C]=15; a.items=[it]
    choices=iter([0,0,0,0]); g.player=lambda k,o,g,**i:next(choices)  # ov18:1479/1487: Exit, review, Yes after marking.
    assert M.scribe(g,a) and it[0x3C]==0x8F and not a.b[0x7F]
    assert 'magic.rest.0' not in g.s.g and M.rest_need(a)==255
    M.rest_spells(g,a,255); assert a.b[0x7F]==1 and not a.items
    a.b[M.MEM+2]=0x83; M.clear_marks(a); assert a.b[M.MEM+2]==0
    # Target cancel does not consume a prepared spell, success consumes exactly one.
    a.b[M.MEM:M.MEM+75]=bytes([3,3])+bytes(73); a.b[M.HP]=50
    g.player=lambda k,o,g,**i:len(o)-1
    assert not M.cast(g,a,3) and list(a.b[M.MEM:M.MEM+75]).count(3)==2
    g.player=lambda k,o,g,**i:0
    assert M.cast(g,a,3) and list(a.b[M.MEM:M.MEM+75]).count(3)==1 and a.b[M.HP]>50
    assert {x[1] for x in g.trace}>={'SPELL','LIST','TARGET'}


def ai_target_slots():
    """ov15:23D5..24E7: a duplicate spends one AI slot, then later targets are still attempted."""
    from types import SimpleNamespace
    for order, expected in (((1,1,2),(1,2)), ((1,1,1),(1,)), ((1,2,1),(1,2))):
        g=fixture(True); chars=g.s.chars(); caster=chars[0]; caster.b[0x1A9]=1
        picks=iter(order); observed=[]; records=[[0]*23 for _ in chars]
        def choose(*args, **kwargs):
            """ov15:1E85 ->3BF1: provide a known legal sequence without changing the picker under test."""
            i=next(picks); observed.append(i); return chars[i]
        g.combat=SimpleNamespace(targets=lambda *a,**k:chars[:], ai_pick_target=choose,
                                 record=lambda c:records[chars.index(c)])
        m=M._Magic(g,Geometry(g).context())
        assert [m.index(c) for c in m.pick(caster,23,True)]==list(expected)
        assert observed==list(order), 'duplicate must consume a slot without ending the remaining selection'
    g=fixture(True); caster=g.s.party[0]; caster.b[0x1A9]=1
    records=[[0]*23 for _ in g.s.chars()]; records[0][10]=1; searches=[]
    def empty_search(caster,bypass,reach,keep):
        """ov15:3C1F..3C6C mode1 clears the old opponent even when none is in spell range."""
        searches.append((bypass,keep)); records[0][10]=-1; return None
    g.combat=SimpleNamespace(targets=lambda *a,**k:[caster],ai_pick_target=empty_search,
                            record=lambda c:records[g.s.chars().index(c)])
    assert M._Magic(g,Geometry(g).context()).pick(caster,61,True)==[]
    assert searches==[(False,False)] and records[0][10]==-1


def geometry():
    """V-check ov23:29C5/4F39/5D90 and ov14:30B1 area expiry and overlapping terrain."""
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
    # ov23:3E10..3E16 bounce bonus adds eight HALF-STEPS, never damage.
    b.b[M.HP]=c.b[M.HP]=100; g.s.random=lambda n:0; geo.set_terrain(14,10,1)
    assert M.ssb_data.stexe()[0x1A9E+4]==255
    g.s.g.update({'87D8':51,'8D8B':12,'8D8C':10}); m.bolt(a,7,12,12,1)
    assert b.b[M.HP]==88 and c.b[M.HP]==76 and g.s.g['87DD']==0
    # ov23:1979..1989: the aimed distance is part of the cone's total range.
    g=fixture(True); a,b,c=g.s.chars(); geo=Geometry(g); m=M._Magic(g,geo.context())
    g.s.g['test.positions']=((10,10),(18,10),(20,10)); g.s.g.update({'8D8B':18,'8D8C':10})
    assert m.cone(a,1,9)==[b], 'aiming farther must not extend the total breath range'
    # ov23:1ABE..1B1C: an empty diagonal wall cell cannot rotate the side rays.
    # This ally veto is the first-AI branch in original sm-r2-5 key23, before draw6.
    g.s.g['test.positions']=((26,13),(28,12),(27,13)); c.b[M.SIDE]=a.b[M.SIDE]
    geo.set_terrain(31,10,1); g.s.g.update({'8D8B':28,'8D8C':12})
    seed=g.s.seed
    assert m.cone(a,3,9)==[b,c], 'breath cone must include the ally on its lower edge'
    assert g.s.seed==seed


def scribe_refusals():
    """ov18:1193/1261/1300/133A: refused rows stay visible; a duplicate row marks the first matching scroll."""
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
    """ov14:19D7/2689 and ov22:0000: mode-specific handlers and the old list tail."""
    g=fixture(); a=g.s.party[0]; a.b[M.HP]=50
    e=M.add_effect(g,a,0x3E,60,255,True); M.effect_callback(g,a,e)
    assert a.b[M.HP]==51 and len(a.effects)==2
    M.tick_effects(g,a,125)
    assert a.b[M.HP]==51 and not a.effects  # regeneration is apply-only, no heal on removal
    M.add_effect(g,a,1,0); M.add_effect(g,a,0x4F,5,255,True); g.s.g['87D5']=4
    M.tick_effects(g,a,15)  # golem callback creates a 3-minute slow during the first chunk
    assert [e[0] for e in a.effects]==[1] and rec.rdw(a.effects[0],1)==0


def bundles():
    """ov18:10A7 and ov23:647F: copy a bundled scroll, then collapse its header."""
    answers=iter([0,0,0,0]); g=fixture(policy=lambda k,o,g,**i:next(answers)); a=g.s.party[0]  # ov18:1479/1487 review.
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
    """ov23:67A1 table coverage: execute all 117 IDs twice, comparing state and decisions."""
    for sid in range(1,118):
        histories=[]
        for _ in range(2):
            combat=bool(M.spell(sid)[11]); g=fixture(combat); a,b,c=g.s.chars(); ctx=Geometry(g).context()
            g.s.seed=123456; g.s.g['87D8']=sid; g.s.g['8D8B']=12; g.s.g['8D8C']=10
            a.b[M.MEM]=sid; a.b[M.HP]=50; b.b[M.HP]=50
            # Direct dispatch also covers otherwise inaccessible unused IDs.
            M._Magic(g,ctx).dispatch(a,sid,[b,c]); histories.append((g.s.hash(g.vm),g.trace))
        assert histories[0]==histories[1], ('dispatch replay',sid)
    # Every mapped ov14 effect handler is executable with an opponent and geometry.
    for typ in range(1,0x72):
        if typ in (0x53,0x68): continue  # no handler table slot
        g=fixture(True); a,b,c=g.s.chars(); m=M._Magic(g,Geometry(g).context()); m.put(a,10,b)
        e=m.add(a,typ,10,6,True); m.callback(a,e); m.remove(a,typ,e)


def replay():
    """ov23:1403 + Game.ask: identical choices reproduce every decision and final hash."""
    traces=[]
    for _ in range(2):
        g=fixture(); a=g.s.party[0]; a.b[M.MEM:M.MEM+3]=bytes((3,12,14)); a.b[M.HP]=50
        for sid in (3,12,14): assert M.cast(g,a,sid)
        traces.append((g.trace,g.s.hash(g.vm)))
    assert traces[0]==traces[1] and len(traces[0][0])==2


def gaze_sides():
    """ov14:178A..179A/18EB: only the opposite side receives the petrification save."""
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
    assert rolls==[100,8,8,8,8,20] and victim.b[M.HP]==96  # ov14:29D5..29F8:4d8 then save.


def check():
    """PORT2 check 1 plus hashed magic decision replay (ov23:1403)."""
    formulas(); effects(); menus(); ai_target_slots(); geometry(); timers(); bundles(); scribe_refusals(); dispatch_smoke(); gaze_sides(); replay()


def derived_camp(recorded=None):
    """PORT2: original starter save at the derived route's ECL1/16 camp, host hook."""
    from sm.titles.ssb import route, resolve
    replay_rows=iter(recorded) if recorded is not None else None
    phases={'root':0,'magic':0,'cast':False}

    def policy(kind,options,g,**info):
        """ov18:30DF -> 0E3D -> ov22:0D25 -> ov23:1403: prepare and cast Bless."""
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
    """PORT2 gates 2/3, ov18:30DF: real camp replay and both resolver routes DONE."""
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
