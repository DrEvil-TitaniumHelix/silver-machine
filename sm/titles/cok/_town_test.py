import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.engine import Session
from sm.titles import cok
from sm.titles.cok import rules, save, town
from sm.titles.cok.menu import Game


def combat_name(c):
    from sm.titles.cok.combat import name
    return name(c)


def lost_fight(game, slot, attempt, why, party=None, result=None):
    from collections import Counter
    s=game.s; log=getattr(game,'combat_log',[])
    start=max((k for k,e in enumerate(log) if e['event']=='setup'),default=None)
    if start is None: return 'LOST %s %s %s | %s/%s (%s,%s) | no fight'%(slot,attempt,why,s.dataset,s.block,s.x,s.y)
    roster=log[start]['roster']; party=party or len(s.party); hurt=Counter(); downs=[]
    def who(i): return roster[i][1].strip() if 0<=i<len(roster) else '?%d'%i
    for e in log[start:]:
        if e['event']=='damage' and 0<=e['target']<party:
            hurt[who(e['actor'])]+=e['amount']
            if e['status']>=4: downs.append('%s by %s r%d'%(who(e['target']),who(e['actor']),e['round']))
    monsters=Counter('%s#%s'%(name.strip(),rid) for rid,name,hp in roster[party:])
    return 'LOST %s %s %s | %s/%s (%s,%s) | %s | dmg %s | down %s | %s'%(slot,attempt,why,s.dataset,s.block,s.x,s.y,
        dict(monsters),dict(hurt.most_common(6)),downs[:8],result)


def starter_game(folder=None):
    game = Game(None, slot=None, directory=folder)
    snapshot = rules.load_slot(game.assets.root / 'SAVE', 'A')
    saved, s = snapshot.game, game.s
    save.apply_image(s, saved)
    rules.restore(s, snapshot)
    game.slot = 'A'
    game.vm.resuming = True
    game.geo.resume(s, game.vm)
    return game


def outpost_session(folder=None):
    from sm.titles.cok._cli import at_outpost
    session = Session(profile=cok, game=starter_game(folder))
    try:
        for _ in range(32):
            if at_outpost(session): return session
            if session.error: raise session.error
            assert session.decision is not None
            session.step(0)
        raise AssertionError('Outpost arrival limit')
    except BaseException:
        session.close(); raise


def area_session(folder=None):
    game = starter_game(folder)
    game.s.block, game.s.mode = 32, 4
    game.vm.set0(0x4BF2, 16); game.vm.set0(0x4BE6, 1)
    game.vm.set0(0x4CF7, 0)
    game.vm.setmem(0x7F12, 2)
    game.vm.resuming = False
    def play(limit=100_000):
        game.vm.load_block(32); game.vm.init_vm(); game.vm.run(game.vm.vec[4])
        assert not game.s.restart
        town.refresh(game)
        game.vm.resuming = False
        while len(game.trace) < limit: town.turn(game)
        return 'LIMIT'
    game.play = play
    session = Session(profile=cok, game=game)
    try:
        for _ in range(32):
            if session.error: raise session.error
            if session.decision and session.decision['kind'] == 'MOVE': return session
            assert session.decision
            session.step(0)
        raise AssertionError('3D entry decision limit')
    except BaseException:
        session.close(); raise


def check_fields(game):
    from sm.titles.cok.records import Character
    from sm.titles.ssb.state import Char
    s, vm = game.s, game.vm
    old_party, old_sel = s.party, s.sel
    s.party, s.sel = [Char(bytes(409))], 0
    c = s.party[0]
    try:
        town.put(c, 'knight_order', 3); town.put(c, 'hp', 27); town.put(c, 'race', 255)
        town.put(c, 'abilities', 17, 3); town.put(c, 'levels', 7, 7)
        assert [vm.getmem(a) for a in (0x7C61,0x7D19,0x7C72,0x7C15,0x7CCD)] == [3,27,65535,17,7]
        vm.set1(0x7CCA, 1234); assert vm.getmem(0x7CCA) == 1234
        vm.setmem(0x7CC3, 0x1234)
        assert town.field(c, 'money', 8, width=2) == 0x1234
        vm.setmem(0x7CC5, 999); assert town.field(c, 'money', 10, width=2) == 0
        before = bytes(c.b)
        vm.setmem(0x7C20, 0x1FF); vm.setmem(0x7C59, 37)
        start, size = Character.FIELDS['memorized']
        assert c.b[start] == 255 and c.b[start+57] == 37
        assert c.b[:start] == before[:start] and c.b[start+size:] == before[start+size:]
        vm.setmem(0x7C1F, 77); vm.setmem(0x7C5A, 77)
        assert c.b[start] == 255 and c.b[start+57] == 37
        vm.setmem(0x7D00, 1); assert town.field(c, 'active') == 1 and vm.getmem(0x7D00) == 1
        vm.setmem(0x7D0C, 129); assert town.field(c, 'side') == 1 and vm.getmem(0x7D0C) == 129
        vm.setmem(0x7CB8, 200); assert town.field(c, 'npc') == 150
        vm.setmem(0x7F12, 4); assert s.dataset == 2 and vm.getmem(0x7F12) == 2
        vm.setmem(0x4BE6, 0); assert s.mode == 3
        vm.setmem(0x4BE6, 1); assert s.mode == 4
    finally: s.party, s.sel = old_party, old_sel


def check_maps(assets):
    from sm.titles.ssb.state import State
    s, count = State(), 0
    geo = town.Geo(assets.records)
    for dataset in (1,2,3):
        for ident, raw in assets.records('GEO%d' % dataset).items():
            count += 1; s.dataset, s.block = dataset, ident; geo.load(s, ident)
            for y in range(16):
                for x in range(16):
                    i = y*16+x
                    assert geo.attr(s,x,y) == raw[514+i]
                    for facing in (0,2,4,6):
                        packed = raw[2+(256 if facing >= 4 else 0)+i]
                        wall = packed >> 4 if facing in (0,4) else packed & 15
                        assert geo.wall(s,x,y,facing) == wall
                        assert geo.passage(s,x,y,facing) == (1 if not wall else raw[770+i] >> facing & 3)
            s.block = 80; assert geo.attr(s,-1,0) == geo.wall(s,16,0,0) == geo.passage(s,16,0,0) == 0
            s.block = 32; assert geo.attr(s,-1,16) == raw[514+15]
    assert count == 15


def check_script_rules(folder=None):
    from sm.titles.cok import effects
    from sm.titles.cok._combat_test import audit
    game=starter_game(folder); s,vm=game.s,game.vm
    s.party=s.party[:2]; s.sel=1; vm.set1(0x7F3E,2)
    vm.ask=lambda *args,**kwargs:0
    vm.next=vm.at=0
    def operands(*values): vm.ops=[(2,v&255,v>>8,'') for v in values]
    for c in s.party:
        c.effects=[]
        for key,value in (('hp',20),('ac',62),('thac0',41),('status',0),('active',1)):
            town.put(c,key,value)
        for level in range(8): town.put(c,'levels',0,level); town.put(c,'former_levels',0,level)
        town.put(c,'levels',2,0); town.put(c,'levels',3,5)
    operands(0x4C01); vm.op1D(); assert vm.getmem(0x4C01)==14
    town.put(s.party[0],'move',3); town.put(s.party[1],'move',8)
    operands(0x7C9F,0,0x4C01,0x4C02,0x4C03,0x4C04); vm.op1E()
    assert [vm.getmem(a) for a in range(0x4C01,0x4C05)]==[3,8,5,0]
    effects.add_effect(s.party[1],39,10,1,0)
    operands(0,39,0x4C01,0x4C02,0x4C03,0x4C04); vm.op1E()
    assert vm.getmem(0x4C04)==1
    for flags,save,expected in ((0xE0,0,[(2,6)]),(0x80,0x80,[(2,6),(1,2)]),
                                (2,100,[(2,6),(1,2),(1,2),(1,20),(2,6),(1,2),(1,20),(2,6)])):
        for c in s.party: c.effects=[]; town.put(c,'hp',100)
        s.seed=0; game.combat_log=[]
        operands(flags,2,6,3,save); vm.op2E()
        draws=[e for e in game.combat_log if e['event']=='dice']
        assert [(e['count'],e['sides']) for e in draws]==expected
        amount=3+draws[0]['result']
        if flags==0xE0: assert all(town.field(c,'hp')==100-amount for c in s.party)
        if flags==0x80: assert [town.field(c,'hp') for c in s.party]==[100,100-amount]
        assert s.sel==1 and not s.party_dead
        audit(game)
    from sm import ecl
    from sm.titles.cok import shop
    s.dataset=2; s.treasure_items=[]
    _,vm.ops,vm.next=ecl.decode(game.assets.records('ECL2')[66][2:],0x91E0)
    vm.op27()
    assert len(s.treasure_items)==2 and s.treasure_money==[0,0,0,1000,800,3,1]
    assert all(len(item)==63 and shop.item_name(game,item) for item in s.treasure_items)
    s.block=50; s.x,s.y,s.dir=6,13,0; game.geo.load(s,50)
    vm.display={'kind':None}; s.ahead=-1; operands(0x2E10); vm.op2D()
    assert s.ahead==game.geo.wall(s,6,13,0) and s.attr==game.geo.attr(s,6,13)


def check_vm_read(folder=None):
    import copy
    from sm.titles.cok import effects, inventory
    from sm.titles.cok.shop import I
    def fresh(size=3):
        game=starter_game(folder); s,vm=game.s,game.vm
        s.party=[copy.deepcopy(s.party[0]) for _ in range(size)]; s.monsters=[]; s.sel=0; vm.set1(0x7F3E,size)
        for n,c in enumerate(s.party):
            c.effects,c.items=[],[]
            for key,value in (('hp',50),('status',0),('active',1),('move',12),('order',n)): town.put(c,key,value)
        vm.ask=lambda *args,**kwargs:0; vm.next=vm.at=0; vm.host=game
        return game,s,vm
    def operands(vm,*values): vm.ops=[(2,v&255,v>>8,'') for v in values]
    def monster(s,**values):
        m=copy.deepcopy(s.party[0])
        for key,value in values.items(): town.put(m,key,value)
        s.monsters.append(m); return m
    game,s,vm=fresh(); s.sel=2; s.g['47E2'],s.g['47E7']=1,2
    vm.op3E(); assert (len(s.party),s.sel,s.g['47E7'],vm.m1(0x7F3E))==(2,1,1,2)
    vm.op00(); assert s.sel==1
    for typed,stored in (('abc  ','ABC  '),('',' '),('x'*45,'X'*40)):
        game,s,vm=fresh(); vm.ask=lambda *args,**kwargs:typed; operands(vm,0,0x4C10); vm.op10()
        assert vm.getstr(0x4C10)==stored,(typed,vm.getstr(0x4C10))
    game,s,vm=fresh(); vm.set0(0x4BE6,0); monster(s,move=1)
    operands(vm,1,2,1,0x4C11,0,0,0,0,0,0,0,0,12,0); vm.slots[1:4]=['','','']; vm.ask=lambda *args,**kwargs:2
    vm.op29(); assert vm.getmem(0x4C11)==1
    game,s,vm=fresh(2); m=monster(s,hp=50); operands(vm,0xE0,1,1,9,0); vm.op2E()
    assert town.field(m,'hp')==40 and all(town.field(c,'hp')==40 for c in s.party)
    game,s,vm=fresh(1); town.put(s.party[0],'hp',5); monster(s,hp=50); operands(vm,0xE0,1,1,9,0); vm.op2E()
    assert not town.field(s.party[0],'active') and not s.party_dead
    game,s,vm=fresh(2); monster(s,move=3); operands(vm,0x7C9F,0,0x4C01,0x4C02,0x4C03,0x4C04); vm.op1E()
    assert [vm.getmem(a) for a in (0x4C01,0x4C02,0x4C03)]==[3,12,9]
    game,s,vm=fresh(1); c=s.party[0]; m=monster(s)
    item=bytearray(63); item[I['type']]=77; item[I['readied']]=1; item[I['powers']+1]=39; item[I['powers']+2]=0x80
    c.items=[item]; m.items=[bytearray(item)]; effects.add_effect(c,39,0,255,True)
    operands(vm,77); vm.op40()
    assert not c.items and not m.items and effects.has_effect(c,39) is None
    game,s,vm=fresh(); vm.setmem(0x3DE,10); operands(vm,0xB203); vm.op2D(); vm.setmem(0x3DE,8); vm.op2D()
    assert game.script_sounds==[11,10]
    game,s,vm=fresh(); s.dataset=2; game.geo.load(s,50); s.block=50; s.x,s.y,s.dir=6,13,4
    vm.display={'kind':None,'location':(6,13,4)}; operands(vm,0xC01E); vm.op2D(); operands(vm,0x2E10); vm.op2D()
    assert vm.display['location']==(6,14,4)


def check_destinations(folder=None):
    from sm.titles.cok._cli import at_outpost
    expected = ('CAMP_MENU','CREATE_MENU','MENU','SHOP_MENU','MENU','MENU')
    for choice, kind in enumerate(expected):
        session = outpost_session(folder)
        try:
            session.step(choice)
            if choice in (0,2): session.step(0)
            if session.error: raise session.error
            assert session.decision['kind'] == kind
            options = session.decision['options']
            if choice == 0: session.step(options.index('Exit'))
            elif choice == 1: session.step(session.game.menu_ids.index(10))
            elif choice == 3: session.step(options.index('Exit'))
            elif choice == 4:
                assert options[:3] == ['VAULT','TEMPLE','BAR']
                session.step(options.index('PREV'))
            elif choice == 5:
                assert session.game.s.block == 16
                session.step(options.index('NO'))
                assert session.decision['kind'] == 'MOVE'
                session.step(session.decision['options'].index('northeast')); session.step(0)
                if session.error: raise session.error
                assert session.decision['kind'] == 'COMBAT_ACTION'
                continue
            if session.error: raise session.error
            assert at_outpost(session)
        finally: session.close()


def road_battle(session, observe=lambda label:None):
    def choose(label):
        session.step(label if isinstance(label,int) else session.decision['options'].index(label))
        if session.error: raise session.error
    choose('west')
    for _ in range(160):
        d=session.decision; kind,options=d['kind'],d['options']
        if kind=='COMBAT_ACTION':
            assert [c.rid for c in session.game.s.monsters]==[11,9,9,9,9,9]
            observe('road_battle'); return
        if kind=='MOVE': choose('south' if session.game.s.r0[0xC4]==3 else 'north')
        elif kind=='CREATE_MENU':
            from sm.titles.cok import creation
            observe('road_training'); choose(session.game.menu_ids.index(creation.BEGIN))
        elif kind=='SHOP_MENU': observe('road_shop'); choose('Exit')
        elif kind=='TEMPLE': observe('road_temple'); choose('Exit')
        elif 'YES' in options: choose('YES')
        else: choose(0)
    raise AssertionError('road encounter limit')


def check_travel_rules(folder=None):
    session=outpost_session(folder)
    try:
        session.step(5); session.step(session.decision['options'].index('NO'))
        game=session.game; session.close(); s,vm=game.s,game.vm
        vm.set0(0x4BC3,37); vm.set0(0x4BC4,14); s.dir=3
        before=s.r0[0xC6:0xCD]; town.move(game)
        assert s.r0[0xC3:0xC5]==[37,14] and s.r0[0xF0:0xF2]==[37,14]
        assert s.r0[0xC9]==(before[3]+12)%24
        assert s.r0[0xCA]==(before[4]+int(before[3]>=12))%30
        vm.set1(0x7EC9,255); before=game.state_hash(); town.move(game)
        assert game.state_hash()==before
        vm.set1(0x7EC9,0); s.dir=7; s.r0[0xC3:0xC5]=[0,0]; town.move(game)
        assert s.r0[0xC3:0xC5]==[0,0]
        from sm.titles.cok._combat_test import audit
        for ceiling,size in ((0,1),(254,255),(255,255)):
            vm.ops=[(0,ceiling,0,None),(1,0x79,0x7F,None)]
            vm.op08(); event=game.combat_log[-1]
            assert event['sides']==size and vm.m1(0x7F79)==event['result']-1<size
        audit(game)
    finally: session.close()
    return 'clamp, movement lock, twelve-hour step'


def sick(c):
    return any(e[0] in (34,43,44) for e in c.effects)


def restable(c):
    return town.field(c,'status') in (0,1,4,5) and not sick(c)


def recover_camp(session, heal=True, preferred=(34,47,21,3,23,15,1,7), minimum_days=0):
    from sm.titles.cok import camp, magic
    game=session.game
    def choose(label):
        session.step(label if isinstance(label,int) else session.decision['options'].index(label))
        if session.error: raise session.error
    assert session.decision['kind']=='CAMP_MENU'
    party=game.s.party
    wounded=lambda:[i for i,c in enumerate(party) if town.field(c,'status') in (0,1,4,5) and town.field(c,'hp')<town.field(c,'hp_max')]
    diseased=lambda:[i for i,c in enumerate(party) if town.field(c,'status') in (0,1,4,5) and sick(c)]
    def cast(char, ident, patients, key):
        choose('Cast')
        for _ in range(80):
            d=session.decision
            if d['kind']=='CAMP_MENU': return
            if d['kind']=='SPELL':
                offered=[k for k,n in magic.castable(char)]
                choose(offered.index(ident) if ident in offered and patients() else 'Exit')
            elif d['kind']=='WHO': choose(min(patients(),key=key) if patients() else 'Exit')
            else: choose(0)
        raise AssertionError('camp cure limit')
    choose('Magic')
    for _ in range(len(party)):
        char=game.s.selc()
        if town.field(char,'active'):
            if diseased() and 39 in dict(magic.castable(char)): cast(char,39,diseased,lambda i:i)
            if not heal and 3 in dict(magic.castable(char)):
                cast(char,3,wounded,lambda i:town.field(party[i],'hp')-town.field(party[i],'hp_max'))
            want=(39,)+tuple(preferred) if diseased() and not any(39 in (n&127 for n in camp.memory(c)) for c in party) else preferred
            choose('Memorize')
            for _ in range(70):
                d=session.decision
                if d['kind']=='CAMP_MENU': break
                if d['kind']=='SPELL' and d['options']==['Exit']: choose('Exit')
                elif d['kind']=='SPELL':
                    t=camp.tables(game.assets); bonus,_,_=camp.slot_display(game,char,t)
                    ids=camp.memorizable(char,t)
                    allowed=[k for k in (want if 39 not in (n&127 for n in camp.memory(char)) else preferred) if k in ids and (camp.slots_remaining(char,t.level(k),t.spell_class(k),t)[0]>0 or t.spell_class(k)==3 and bonus)]
                    choose(ids.index(allowed[0]) if allowed else 'Exit')
                elif d['kind']=='CAMP_CONFIRM': choose('Yes')
                else: choose(0)
            else: raise AssertionError('memorize decision limit')
        choose('char-down')
    choose('Exit'); choose('Rest')
    days=max((town.field(c,'hp_max')-town.field(c,'hp') for c in game.s.party if restable(c)),default=0) if heal else 0
    days=max(days,minimum_days)
    if days:
        choose('Days')
        for _ in range(days): choose('Add')
    choose('Rest')
    while session.decision and session.decision['kind']=='ACK': choose(0)
    if session.decision['kind']!='CAMP_MENU': return False
    if diseased() and any(town.field(c,'active') and 39 in dict(magic.castable(c)) for c in party):
        return recover_camp(session,heal,preferred,minimum_days)
    if heal: assert all(town.field(c,'hp')==town.field(c,'hp_max') for c in game.s.party if restable(c)),         'party needs a native cure beyond rest: %s'%[(town.field(c,'hp'),town.field(c,'hp_max'),town.field(c,'status')) for c in game.s.party]
    choose('Exit')
    return True


class ThrotlWalk:
    def __init__(self, session, frame=lambda label:None, verbose=False):
        self.session,self.game,self.frame,self.verbose=session,session.game,frame,verbose
        self.steps=[]; self.battles=[]; self.events=[]
        self.focus=False; self.policy=None; self.rest_after_battle=True; self.recovery=None; self.money=False
        self.preferred=(34,47,21,3,23,15,1,7)

    def choose(self, label):
        d=self.session.decision
        if not isinstance(label,int) and d['options'] is not None and label not in d['options']:
            raise ValueError('%r not offered at %d/%d (%d,%d): %s %s %s'%(label,self.game.s.dataset,self.game.s.block,
                             self.game.s.x,self.game.s.y,d['kind'],d['options'],self.game.vm.out[-3:]))
        self.session.step(label if isinstance(label,int) or d['options'] is None else d['options'].index(label))
        if self.session.error: raise self.session.error

    def settle(self):
        from sm.titles.cok._combat_test import finish_battle
        for _ in range(500):
            d=self.session.decision
            if d is None: raise AssertionError('route ended: '+str(self.session.result))
            kind,options=d['kind'],d['options']
            if kind in ('MOVE','CREATE_MENU'): return
            s=self.game.s
            if self.verbose: print('EVENT',s.block,s.x,s.y,kind,options,self.game.vm.out[-2:])
            self.events.append((s.block,s.x,s.y,kind,d['info'].get('at')))
            if kind=='COMBAT_LOOT' and not s.monsters and s.g['cok.battle']['round']==0:
                self.take_find()
            elif kind=='CAMP_MENU':
                recover_camp(self.session,preferred=self.preferred)
            elif kind.startswith('COMBAT_'):
                monsters=tuple(c.rid for c in s.monsters)
                for member in s.party:
                    if town.field(member,'npc')>127: self.frame('npc_%s'%member.rid)
                result=finish_battle(self.session,True,self.focus,self.money); self.battles.append((s.block,monsters,result))
                if self.verbose: print('BATTLE',result)
                assert result[0]=='won','route battle lost by the dice'
            else:
                preferred=('Bash','EAVESDROP','THREATEN HIM','ATTACK','LET THEM GO','YES','PARLAY','NICE')
                chosen=self.policy(d) if self.policy else None
                self.choose(chosen if chosen is not None else 'WAIT' if s.block==34 and (s.attr&63)==28 and 'WAIT' in options else next((v for v in preferred if v in options),0))
        raise AssertionError('event decision limit')

    def take_find(self):
        from sm.titles.cok.shop import I, cannot_carry
        self.frame('catacomb_find')
        s=self.game.s
        while s.treasure_items:
            target={67:3,50:5,52:4,47:0}.get(s.treasure_items[0][I['type']],0)
            if cannot_carry(s.party[target],s.treasure_items[0]):
                target=next((i for i,c in enumerate(s.party) if not cannot_carry(c,s.treasure_items[0])),None)
                if target is None: raise town.BindingRequired('party needs inventory space for discovered treasure')
            while s.sel!=target: self.choose('char-down')
            before=len(s.treasure_items)
            self.choose('Take')
            if 'Items' in self.session.decision['options']: self.choose('Items')
            self.choose(0)
            assert len(s.treasure_items)==before-1
            while 'View' not in self.session.decision['options']: self.choose('Exit')
        self.choose('Exit')

    def ready_wand(self):
        from sm.titles.cok.shop import I
        from sm.titles.cok import rules
        s=self.game.s
        while s.sel!=4: self.choose('char-down')
        char=s.selc(); index=next(i for i,it in enumerate(char.items) if it[I['type']]==52)
        self.choose('view'); self.choose('Items')
        for j,it in enumerate(char.items):
            if it[I['readied']] and rules.tables().base_item(it[I['type']])[rules.SLOT] in (0,1):
                self.choose(j); self.choose('Ready')
        self.choose(index); self.choose('Ready')
        assert char.items[index][I['readied']]
        self.choose('Exit'); self.choose('Exit')

    def go(self, goal, facing=None, arrival=None):
        if self.retrying(): return self.guarded(lambda:self.go(goal,facing,arrival))
        from heapq import heappop,heappush
        s=self.game.s; blocked=set()
        for _ in range(300):
            if (s.x,s.y)==goal: break
            queue=[(0,(s.x,s.y),[])]; seen=set(); route=None
            while queue:
                cost,pos,path=heappop(queue)
                if pos==goal: route=path; break
                if pos in seen: continue
                seen.add(pos)
                for face,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
                    if (pos,face*2) in blocked: continue
                    target=pos[0]+dx,pos[1]+dy
                    if not (0<=target[0]<16 and 0<=target[1]<16): continue
                    if self.game.geo.passage(s,*pos,face*2):
                        weight=1
                        heappush(queue,(cost+weight,target,path+[(target,face*2)]))
            if not route:
                if blocked: blocked.clear(); continue
                raise AssertionError(('no native path',s.block,s.x,s.y,goal))
            target,face=route[0]
            while s.dir!=face: self.choose('turn-right')
            before=s.block,s.x,s.y,s.dir
            raw=self.game.assets.records('GEO%d'%s.dataset)[self.game.geo.map.id]
            cell=s.y*16+s.x; packed=raw[2+(256 if face>=4 else 0)+cell]
            wall=packed>>4 if face in (0,4) else packed&15
            assert not wall or raw[770+cell]>>face&3 or s.g.get('door %d %d %d'%(s.x,s.y,face))
            battles=len(self.battles)
            self.choose('forward'); self.settle()
            self.steps.append((before,(s.block,s.x,s.y,s.dir),s.attr))
            if self.verbose: print('STEP',self.steps[-1])
            if s.block!=before[0]: return
            if target==goal and arrival is not None and (s.x,s.y)==arrival: return
            if getattr(self,'reroute',False) and (s.x,s.y)==(before[1],before[2]): blocked.add(((s.x,s.y),face))
            assert (s.x,s.y) in ((before[1],before[2]),target,(12,6) if s.block==33 and target==(12,7) else target)
            assert s.dir in (0,2,4,6) and s.attr==raw[514+s.y*16+s.x]
            packed=raw[2+(256 if s.dir>=4 else 0)+s.y*16+s.x]
            assert s.ahead==(packed>>4 if s.dir in (0,4) else packed&15)
            if len(self.battles)>battles and self.rest_after_battle:
                if self.recovery:
                    self.rest_after_battle=False
                    self.go(self.recovery); self.rest()
                    self.rest_after_battle=True
                else:
                    try: self.rest(False)
                    except AssertionError as error:
                        if str(error)!='rest interrupted twenty times': raise
        else: raise AssertionError('walking decision limit',goal,self.steps[-12:],self.events[-6:])
        if facing is not None:
            while s.dir!=facing: self.choose('turn-right'); self.settle()

    def save(self, slot):
        from sm.titles.cok import creation
        if not hasattr(self.game,'story_io'): self.game.story_io=[]
        self.game.story_io.append((len(self.game.trace),'save',slot))
        creation.save_game(self.game,slot)

    def reload(self, slot):
        if not hasattr(self.game,'story_io'): self.game.story_io=[]
        self.game.story_io.append((len(self.game.trace),'load',slot))
        self.session.close(); town.load_game(self.game,slot)
        Session.__init__(self.session,profile=cok,game=self.game,limit=getattr(self,'limit',1_000_000))
        if hasattr(self,'step'): self.session.step=self.step
        d=self.session.decision
        if d and d['kind']=='MENU' and d['info'].get('at')==0x8DD5 and self.game.s.block==16: self.choose('NO')
        self.settle()

    def attempt(self, action, slot='A', tries=256, min_active=0, survivors=()):
        self.save(slot); marks=len(self.steps),len(self.battles),len(self.events),len(self.game.s.party)
        party=self.game.s.party
        survivors=tuple(i for i in survivors if not isinstance(i,int) or
                        i<len(party) and town.field(party[i],'status')<6)
        survivors+=tuple(i for i,c in enumerate(party) if town.field(c,'race') in (0,1) and town.field(c,'status')<6 and i not in survivors)
        min_active=min(min_active,sum(bool(town.field(c,'active')) for c in party))
        outer,self.attempting=getattr(self,'attempting',False),True
        try: return self._attempt(action,slot,tries,min_active,survivors,marks)
        finally: self.attempting=outer

    def _attempt(self, action, slot, tries, min_active, survivors, marks):
        for attempt in range(tries):
            try:
                if attempt:
                    self.reload(slot)
                    del self.steps[marks[0]:],self.battles[marks[1]:],self.events[marks[2]:]
                action()
                if (sum(bool(town.field(c,'active')) for c in self.game.s.party)<min_active or
                        any(i>=len(self.game.s.party) or town.field(self.game.s.party[i],'status')>=6 for i in survivors if isinstance(i,int)) or
                        any(combat_name(c) in survivors and town.field(c,'status')>=6 for c in self.game.s.party)):
                    raise AssertionError('campaign party needs recovery')
                return
            except AssertionError as error:
                if (error.args[:1] not in (('route battle lost by the dice',),('campaign party needs recovery',),('walking decision limit',)) and not self.game.s.party_dead
                        and not str(error).startswith('party needs a native cure beyond rest')): raise
                if self.verbose or attempt%10==0: print('RETRY',slot,attempt+1,str(error.args[0] if error.args else error),flush=True)
                if os.environ.get('SM_COK_LOSSES'):
                    try: print(lost_fight(self.game,slot,attempt+1,str(error.args[0] if error.args else error),marks[3],self.battles[-1][2] if len(self.battles)>marks[1] else None),flush=True)
                    except Exception: import traceback; traceback.print_exc()
                self.focus=(True,'auto','melee-auto')[attempt%3]
        raise AssertionError('required battle still lost after %d native loads'%tries)

    def retrying(self):
        return getattr(self,'retry',False) and not getattr(self,'attempting',False)

    def guarded(self, action):
        living=tuple(combat_name(c) for c in self.game.s.party if town.field(c,'status')<6)
        return self.attempt(action,survivors=living)

    def rest(self, heal=True):
        if self.retrying(): return self.guarded(lambda:self.rest(heal))
        for _ in range(20):
            self.choose('camp'); rested=recover_camp(self.session,heal,self.preferred); self.settle()
            if rested and all(town.field(c,'hp')==town.field(c,'hp_max') for c in self.game.s.party if restable(c)): break
        else: raise AssertionError('rest interrupted twenty times')
        self.frame('rest_%d_%d_%d'%(self.game.s.block,self.game.s.x,self.game.s.y))

    def train_at_outpost(self, stairs=True):
        if self.retrying(): return self.guarded(lambda:self.train_at_outpost(stairs))
        from sm.titles.cok import creation
        from sm.titles.cok._cli import at_outpost
        s=self.game.s
        self.go((8,6),6); self.choose('forward'); self.settle(); assert s.block==32
        self.go((7,15),4); self.choose('forward'); assert s.block==16
        self.choose('NO')
        for direction in ('southwest','south'):
            self.choose(direction)
            if self.session.decision['kind']!='MOVE': self.choose('YES')
        for _ in range(100):
            if at_outpost(self.session): break
            self.choose(0)
        else: raise AssertionError('Outpost return limit')
        self.train_party()
        self.choose('LEAVE'); self.choose('NO')
        for direction in ('northeast','north'):
            self.choose(direction)
            if self.session.decision['kind']!='MOVE': self.choose('YES')
        self.settle(); assert s.block==32
        self.go((7,6),2); self.choose('forward'); self.settle(); assert s.block==33
        if stairs: self.go((9,0),0); self.rest()

    def train_party(self, learn=False, preferred=None):
        from sm.titles.cok import creation
        s=self.game.s
        self.choose('HALL')
        for member in range(len(s.party)):
            self.choose(self.game.menu_ids.index(creation.TRAIN)); self.choose(member)
            for _ in range(30):
                d=self.session.decision
                if d['kind']=='CREATE_MENU': break
                wanted=next((v for v in ('Stinking Cloud','Fireball') if learn and v in d['options']),None)
                self.choose(wanted if wanted else 'Yes' if 'Yes' in d['options'] else 0)
            else: raise AssertionError('training choice limit')
        self.frame('earned_training'); self.choose(self.game.menu_ids.index(creation.BEGIN))
        self.choose('INN'); self.choose(0); recover_camp(self.session,preferred=preferred or self.preferred)


class StoryWalk(ThrotlWalk):
    def __init__(self, session, frame=lambda label:None, verbose=False, limit=1_000_000):
        super().__init__(session,frame,verbose)
        self.limit=limit; self.focus='melee-auto'; self.money=True; self.rest_after_battle=False
        self.reroute=True
        self.preferred=(102,25,34,47,15,21,3,6)
        self.policy=self.story_choice
        self.spread=set(); self.spread_stamp=None; self.spread_battle=None
        session.step=self.step

    def step(self, answer):
        from sm.titles.cok import combat
        d=self.session.decision
        if len(self.game.trace)>=self.limit: raise town.BindingRequired('campaign decision limit')
        if (d['kind']=='COMBAT_LOOT' and 'View' in d['options'] and not getattr(self,'claiming',False)
                and any(item[combat.I['type']]==69 for item in self.game.s.treasure_items)):
            self.claiming=True
            try: self.take_find()
            finally: self.claiming=False
            return self.session.decision
        battle=combat.Battle(self.game) if d['kind'] in ('COMBAT_ACTION','COMBAT_MOVE') else None
        if battle is not None and battle.data is not self.spread_battle:
            self.spread_battle=battle.data; self.spread.clear(); self.spread_stamp=None
        dragons=[] if battle is None else [j for j in battle.targets(battle.data['actor'])
                   if any(combat.has(battle.chars[j],kind) for kind in (6,83,84,90,104))]
        if dragons and d['kind']=='COMBAT_ACTION' and d['info']['actor'] in (2,3,5) and d['info']['round']==0 and 'Move' in d['options'] and d['info']['actor'] not in self.spread:
            self.spread.add(d['info']['actor'])
            answer=d['options'].index('Move')
        elif dragons and d['kind']=='COMBAT_MOVE' and battle.data['actor'] in (2,3,5) and battle.data['round']==0:
            actor=battle.data['actor']; r=battle.record(actor); stamp=(actor,r['x'],r['y'],r['movement'])
            choices=[]
            if stamp!=self.spread_stamp:
                for direction in range(8):
                    occupant,tile=battle.probe(actor,direction)
                    if occupant<0 and tile and battle.terrain(tile)<255 and battle.terrain(tile)*(3 if direction%2 else 2)<=r['movement']:
                        x,y=r['x']+combat.DX[direction],r['y']+combat.DY[direction]
                        distance=min(max(abs(x-battle.position(j)[0]),abs(y-battle.position(j)[1])) for j in dragons)
                        allies=[j for j in range(len(self.game.s.party)) if j!=actor and town.field(battle.chars[j],'active')]
                        separation=min((max(abs(x-battle.position(j)[0]),abs(y-battle.position(j)[1])) for j in allies),default=0)
                        choices.append((distance*3+separation, y if actor==5 else -y,direction))
            self.spread_stamp=stamp
            answer=max(choices)[2] if choices else d['options'].index('Done')
        elif d['kind']=='COMBAT_ACTION' and not dragons and 'Yell' in d['options']:
            answer=d['options'].index('Yell')
        elif d['kind']=='COMBAT_SPELL':
            from sm.titles.cok import magic
            battle=combat.Battle(self.game); actor=d['info']['actor']
            offered=[ident for ident,_ in magic.castable(battle.chars[actor],True)]
            if 15 in offered and any(any(combat.has(battle.chars[j],kind) for kind in (6,83,84,90,104))
                                    for j in battle.targets(actor)):
                answer=offered.index(15)
        elif d['kind']=='TARGET' and not d['info'].get('spell'):
            battle=combat.Battle(self.game)
            side=town.field(battle.chars[battle.data['actor']],'side')
            targets=[(i,int(label.rsplit('#',1)[1])) for i,label in enumerate(d['options']) if '#' in label]
            targets=[pair for pair in targets if town.field(battle.chars[pair[1]],'side')!=side]
            if targets:
                answer=max(targets,key=lambda pair:(
                    any(town.field(battle.chars[pair[1]],'memorized',k) for k in range(58)),
                    -town.field(battle.chars[pair[1]],'hp')))[0]
        return Session.step(self.session,answer)

    def story_choice(self, decision):
        options=decision['options'] or []
        if decision['kind']=='STRING': return 'RUMOR'
        if self.game.s.block==97:
            if 'MOVE AWAY' in options: return 'ATTACK' if getattr(self,'assault',False) else 'MOVE AWAY'
            chosen=next((v for v in ('ENCOURAGE THE PLOT','TALK','GREET','THANK THEM') if v in options),None)
            if chosen is not None: return chosen
        if self.game.s.block==99:
            preferred=('TELL ABOUT ASSASSINS','GREET','WALK PAST','TALK','YES')
            chosen=next((v for v in preferred if v in options),None)
            if chosen is not None: return chosen
        if self.game.s.block==68 and 'LISTEN' in options: return 'LISTEN'
        if self.game.s.block==82 and 'RESCUE' in options: return 'RESCUE'
        if self.game.s.block==67:
            if not getattr(self,'leaving',False) and 'NO' in options and 'REACHED THE EXIT' in ''.join(self.game.vm.out[-3:]): return 'NO'
            if 'RIGHT' in options: return 'RIGHT'
            if 'MONEY' in options and 'LIFE' in options: return 'MONEY'
            if 'NO' in options and ('TAKE ANY?' in ''.join(self.game.vm.out[-4:]) or 'TAKE ANY?' in ''.join(self.game.vm.out[-6:])): return 'NO'
        if self.game.s.block==16 and 'DO YOU ENTER?' in ''.join(self.game.vm.out[-3:]) and 'NO' in options: return 'NO'
        if decision['kind'].startswith('SHOP_') and 'Exit' in options: return 'Exit'
        preferred=('ALLOW HER TO JOIN','RUN AWAY','FIGHT','YES','Yes','ATTACK')
        return next((choice for choice in preferred if choice in options),None)

    def checkpoint(self, slot, label):
        self.save(slot)
        self.game.frontier=slot,label,self.game.s.dataset,self.game.s.block,self.game.s.x,self.game.s.y
        print('SAVE %s: %s; block %d/%d (%d,%d); %d decisions'%
              (slot,label,self.game.s.dataset,self.game.s.block,self.game.s.x,self.game.s.y,len(self.game.trace)),flush=True)

    def outpost(self):
        from sm.titles.cok._cli import at_outpost
        for _ in range(100):
            if at_outpost(self.session): return
            self.choose(0)
        raise AssertionError('Outpost menu limit')

    def road(self, goal, enter=True):
        s=self.game.s
        for _ in range(150):
            if s.block!=16: return
            d=self.session.decision
            if d['kind']=='MENU' and 'DO YOU ENTER?' in ''.join(self.game.vm.out[-3:]):
                if tuple(s.r0[0xC3:0xC5])==goal and enter:
                    self.choose('YES')
                    if s.block==17: self.outpost()
                    else: self.settle()
                    return
                self.choose('NO')
            elif d['kind']!='MOVE': self.settle()
            elif tuple(s.r0[0xC3:0xC5])==goal: return
            else:
                x,y=s.r0[0xC3:0xC5]; dx=(goal[0]>x)-(goal[0]<x); dy=(goal[1]>y)-(goal[1]<y)
                self.choose({(0,-1):'north',(1,-1):'northeast',(1,0):'east',(1,1):'southeast',
                             (0,1):'south',(-1,1):'southwest',(-1,0):'west',(-1,-1):'northwest'}[dx,dy])
        raise AssertionError('overland travel limit')

    def rest(self, heal=True, camp=None):
        if camp is not None:
            back=self.game.s.x,self.game.s.y
            self.attempt(lambda:self.go(camp),min_active=sum(bool(town.field(c,'active')) for c in self.game.s.party))
            self.rest(heal)
            return self.attempt(lambda:self.go(back),min_active=sum(bool(town.field(c,'active')) for c in self.game.s.party))
        active=sum(bool(town.field(c,'active')) for c in self.game.s.party)
        rested=False
        def cycle():
            nonlocal rested
            self.choose('camp')
            rested=recover_camp(self.session,False,(3,)+self.preferred,minimum_days=1)
            self.settle()
        for _ in range(80):
            self.attempt(cycle,slot='E',min_active=active)
            if rested and (not heal or all(town.field(c,'hp')==town.field(c,'hp_max')
                    for c in self.game.s.party if restable(c))): return
        raise AssertionError('campaign healing limit')

    def recover(self):
        self.cure()
        try: self.rest()
        except AssertionError as error:
            if str(error) not in ('rest interrupted twenty times','campaign healing limit'): raise

    def cure(self):
        from sm.titles.cok import magic
        s=self.game.s
        self.choose('camp'); self.choose('Magic')
        for _ in range(len(s.party)):
            char=s.selc()
            if town.field(char,'active') and 3 in dict(magic.castable(char)):
                self.choose('Cast')
                for _ in range(80):
                    d=self.session.decision
                    if d['kind']=='CAMP_MENU': break
                    wounded=[i for i,c in enumerate(s.party) if town.field(c,'status') in (0,1,4,5) and town.field(c,'hp')<town.field(c,'hp_max')]
                    if d['kind']=='SPELL':
                        ids=[ident for ident,_ in magic.castable(char)]
                        self.choose(ids.index(3) if 3 in ids and wounded else 'Exit')
                    elif d['kind']=='WHO':
                        self.choose(min(wounded,key=lambda i:(town.field(s.party[i],'status') not in (4,5),
                            town.field(s.party[i],'hp')/town.field(s.party[i],'hp_max'))) if wounded else 'Exit')
                    else: self.choose(0)
                else: raise AssertionError('campaign cure limit')
            self.choose('char-down')
        self.choose('Exit'); self.choose('Exit'); self.settle()

    def equip_dargaard(self):
        from sm.titles.cok.shop import I
        s=self.game.s; char=s.party[0]
        choices=[i for i,it in enumerate(char.items) if it[I['type']] in (42,68) and not it[I['readied']]]
        if not choices: return
        while s.sel: self.choose('char-down')
        self.choose('view'); self.choose('Items')
        for kind in (42,68):
            candidates=[i for i,it in enumerate(char.items) if it[I['type']]==kind]
            if not candidates or any(char.items[i][I['readied']] for i in candidates): continue
            selected=candidates[0]; slot=rules.tables().base_item(kind)[rules.SLOT]
            for i,it in enumerate(char.items):
                if it[I['readied']] and rules.tables().base_item(it[I['type']])[rules.SLOT]==slot:
                    self.choose(i); self.choose('Ready')
            self.choose(selected); self.choose('Ready')
        self.choose('Exit'); self.choose('Exit')

    def equip_dragonlance(self):
        from .shop import I
        for member,char in enumerate(self.game.s.party):
            lance=next((i for i,it in enumerate(char.items) if it[I['type']]==69),None)
            if lance is None or char.items[lance][I['readied']]: continue
            while self.game.s.sel!=member: self.choose('char-down')
            self.choose('view'); self.choose('Items')
            for i,it in enumerate(char.items):
                if it[I['readied']] and rules.tables().base_item(it[I['type']])[rules.SLOT] in (0,1):
                    self.choose(i); self.choose('Ready')
            self.choose(lance); self.choose('Ready')
            assert char.items[lance][I['readied']]
            self.choose('Exit'); self.choose('Exit')

    def prepare_fire(self):
        from . import magic
        s=self.game.s
        while s.sel!=5: self.choose('char-down')
        self.choose('cast')
        while self.session.decision['kind']=='SPELL' and 25 in dict(magic.castable(s.selc())):
            self.choose([k for k,_ in magic.castable(s.selc())].index(25))
            self.choose(0); self.choose('Yes')
        if self.session.decision['kind']=='SPELL': self.choose('Exit')
        self.preferred=(24,102,34,47,15,21,3,6)
        self.rest()

    def equip_recovered_gifts(self):
        from . import shop
        I=shop.I; s=self.game.s
        def inventory(member):
            while s.sel!=member: self.choose('char-down')
            self.choose('view'); self.choose('Items')
        def leave(): self.choose('Exit'); self.choose('Exit')
        for member,kind,bonus in ((1,58,2),(1,59,2),(5,36,1)):
            char=s.party[member]
            item=next((it for it in char.items if it[I['type']]==kind and it[I['bonus']]==bonus),None)
            if item is None or item[I['readied']]: continue
            inventory(member)
            slot=rules.tables().base_item(kind)[rules.SLOT]
            for index,old in enumerate(char.items):
                if old[I['readied']] and rules.tables().base_item(old[I['type']])[rules.SLOT]==slot:
                    self.choose(index); self.choose('Ready')
            self.choose(next(i for i,it in enumerate(char.items) if it is item)); self.choose('Ready'); leave()
        steel=shop.coins(s.party[2])[4]
        if steel>500:
            while s.sel!=2: self.choose('char-down')
            self.choose('view'); self.choose('Drop')
            self.choose(next(i for i,label in enumerate(self.session.decision['options']) if label.startswith('Steel ')))
            self.choose(steel-500); leave()
        for kind,bonus in ((37,2),(59,1)):
            item=next((it for it in s.party[1].items if it[I['type']]==kind and it[I['bonus']]==bonus),None)
            if item is not None:
                inventory(1); self.choose(next(i for i,it in enumerate(s.party[1].items) if it is item))
                self.choose('Trade'); self.choose(2); leave()
            char=s.party[2]
            item=next((it for it in char.items if it[I['type']]==kind and it[I['bonus']]==bonus),None)
            if item is None or item[I['readied']]: continue
            inventory(2); slot=rules.tables().base_item(kind)[rules.SLOT]
            for index,old in enumerate(char.items):
                if old[I['readied']] and rules.tables().base_item(old[I['type']])[rules.SLOT]==slot:
                    self.choose(index); self.choose('Ready')
            self.choose(next(i for i,it in enumerate(char.items) if it is item)); self.choose('Ready'); leave()

    def resist_fire(self):
        from . import magic
        s=self.game.s
        while s.sel!=5: self.choose('char-down')
        self.choose('cast')
        for target,char in enumerate(s.party):
            if town.field(char,'status')>=6: continue
            offered=[k for k,_ in magic.castable(s.selc())]
            if 24 not in offered: break
            self.choose(offered.index(24))
            while self.session.decision['kind']=='ACK': self.choose(0)
            self.choose(target)
            while self.session.decision['kind']=='ACK': self.choose(0)
        if self.session.decision['kind']=='SPELL': self.choose('Exit')

    def revive(self):
        from sm.titles.cok import combat, shop
        s=self.game.s
        patients=[i for i,c in enumerate(s.party) if town.field(c,'status')==6 and (combat.has(c,55) or town.field(c,'race')>=2)]
        if not patients: return
        self.choose('NEXT'); self.choose('TEMPLE')
        for i,c in enumerate(s.party):
            if not any(shop.coins(c)[5:]): continue
            while s.sel!=i: self.choose('char-down')
            self.choose('Appraise')
            for _ in range(200):
                if self.session.decision['kind']=='TEMPLE': break
                self.choose('Sell' if 'Sell' in self.session.decision['options'] else 0)
            else: raise AssertionError('campaign appraisal limit')
        self.choose('Pool')
        for i in patients:
            poison=combat.has(s.party[i],55); cost=500 if poison else 2750
            if shop.coin_value(self.game,s.treasure_money)<cost:
                raise town.BindingRequired('campaign temple recovery needs %d steel'%cost)
            while s.sel!=i: self.choose('char-down')
            self.choose('Heal'); self.choose(6 if poison else 7)
            self.choose('Yes'); self.choose(0); self.choose('Exit')
            assert town.field(s.party[i],'status')==0
        if 'Share' in self.session.decision['options']: self.choose('Share')
        self.choose('Exit')
        if self.session.decision['kind']=='SHOP_CONFIRM': self.choose('No')


def inside_jelek(session, frame=lambda label:None, verbose=False):
    walk=StoryWalk(session,frame,verbose); game=session.game; s=game.s
    walk.settle()
    if not game.vm.m0(0x4C73):
        while s.sel!=5: walk.choose('char-down')
        from sm.titles.cok import magic
        walk.choose('cast')
        while session.decision['kind']=='SPELL' and 23 in dict(magic.castable(s.selc())):
            walk.choose([k for k,_ in magic.castable(s.selc())].index(23))
            walk.choose(0); walk.choose('Yes')
        if session.decision['kind']=='SPELL': walk.choose('Exit')
        walk.go((2,15),4); walk.choose('forward'); walk.choose('YES')
        walk.settle(); walk.road((13,5))
        walk.choose('INN'); walk.choose(0); recover_camp(session,preferred=walk.preferred)
        walk.choose('LEAVE'); walk.choose('NO')
        walk.road((12,7))
        walk.go((10,13)); walk.checkpoint('F','Jelek before the betrayal')
        walk.attempt(lambda:walk.go((10,14)),min_active=5)
        walk.checkpoint('E','Jelek betrayal won')
        walk.recover()
    if not game.vm.m0(0x4C7B):
        if (s.x,s.y)!=(15,3): walk.attempt(lambda:walk.go((13,0),arrival=(15,3)),min_active=5)
        walk.rest(); walk.checkpoint('D','Jelek refuge, recovered')
        walk.attempt(lambda:walk.go((2,2)),min_active=5)
        assert game.vm.m0(0x4C7B)==255
        walk.checkpoint('C','Jelek silver rose')
    walk.attempt(lambda:walk.go((2,15),4))
    walk.choose('forward'); walk.choose('YES')
    walk.settle(); walk.road((13,5))
    walk.train_party(True,preferred=walk.preferred)
    walk.choose('COMMANDANT'); walk.outpost()
    while not game.vm.m0(0x4C32):
        walk.choose('LEAVE'); walk.choose('YES'); walk.outpost()
    walk.choose('COMMANDANT')
    for _ in range(100):
        if s.block==64 and session.decision['kind']=='MOVE': break
        walk.choose('YES' if session.decision['kind']=='MENU' and 'YES' in session.decision['options'] else 0)
    else: raise AssertionError('Maya departure limit')
    walk.checkpoint('B','Neraka with Maya')
    return dict(block=(s.dataset,s.block),position=(s.x,s.y),decisions=len(game.trace))


def inside_neraka(session, frame=lambda label:None, verbose=False):
    walk=StoryWalk(session,frame,verbose); game=session.game; s=game.s
    walk.settle()
    if s.block==64:
        walk.attempt(lambda:walk.go((8,14)),min_active=5)
        walk.rest(camp=(15,5))
        walk.checkpoint('G','Neraka Sir Karl')
        walk.go((8,14),4); walk.choose('forward'); walk.settle()
        assert s.block==66
        walk.checkpoint('H','Neraka slave prison')
    if not game.vm.m0(0x4C39):
        walk.attempt(lambda:walk.go((11,6)),min_active=5)
        walk.rest()
        walk.checkpoint('I','Neraka Tanis orders')
    for flag,mask,cell in ((0x4C94,1,(10,10)),(0x4C94,2,(11,10)),(0x4C94,4,(13,10)),
                           (0x4C94,8,(10,13)),(0x4C94,16,(11,13)),(0x4C94,32,(14,13))):
        if not game.vm.m0(flag)&mask:
            walk.attempt(lambda:walk.go(cell),min_active=5)
            walk.rest()
            walk.checkpoint('I','Neraka slave cells: %d/6'%game.vm.m0(0x4C98))
    walk.attempt(lambda:walk.go((9,12)),min_active=6)
    walk.attempt(lambda:walk.go((6,12)),min_active=5)
    walk.rest()
    walk.checkpoint('I','Neraka prison lord defeated')
    elves=tuple(i for i,c in enumerate(s.party) if town.field(c,'race') in (0,1) and town.field(c,'status')<6)
    walk.attempt(lambda:walk.go((3,14)),min_active=4,survivors=elves)
    walk.cure()
    active=sum(bool(town.field(c,'active')) for c in s.party)
    walk.attempt(lambda:walk.go((0,9),6),min_active=active,survivors=elves)
    walk.choose('forward'); walk.settle()
    assert s.block==16 and game.vm.m0(0x4C97)==1
    walk.checkpoint('J','Neraka slaves rescued')
    walk.road((13,5)); walk.revive(); walk.train_party(True,preferred=walk.preferred)
    walk.choose('COMMANDANT'); walk.outpost()
    walk.checkpoint('B','Outpost after Neraka')


def continue_story(session):
    game=session.game
    if (game.s.dataset,game.s.block)==(2,50): inside_jelek(session)
    if game.s.dataset==2 and game.s.block in (64,66): inside_neraka(session)
    if not game.vm.m0(0x4C9B) and (game.s.block==17 or (game.s.dataset,game.s.block)==(2,67)): inside_tomb(session)
    if not game.vm.m0(0x4CDD) and (game.s.block==17 or (game.s.dataset,game.s.block)==(3,99)): inside_ogre(session)
    if not game.vm.m0(0x4CA5) and (game.s.block==17 or (game.s.dataset,game.s.block)==(2,68)): inside_southern(session)
    if game.s.block==17 or (game.s.dataset,game.s.block)==(3,80): inside_sanction(session)
    if (game.s.dataset,game.s.block)==(3,81): inside_huerzyd(session)
    if (game.s.dataset,game.s.block)==(3,82): inside_dungeons(session)
    if (game.s.dataset,game.s.block)==(3,96): inside_citadel(session)
    if (game.s.dataset,game.s.block)==(3,97): inside_kernen(session)
    if (game.s.dataset,game.s.block)==(3,98): inside_stronghold(session)
    if game.vm.m0(0x4C3A)!=1:
        raise town.BindingRequired('campaign route stopped before the native ending')
    furthest=next(((disk,block) for disk,block,_,_ in reversed(game.script_log) if block>=32 and block!=36),(game.s.dataset,game.s.block))
    return dict(furthest=furthest,position=(game.s.x,game.s.y),decisions=len(game.trace))


def inside_tomb(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    walk.focus=True
    def enter():
        walk.choose('LEAVE'); walk.choose('NO'); walk.road((11,3))
        assert s.block==67
    def leave():
        walk.go((7,7)); walk.leaving=True; walk.choose('look'); walk.settle(); walk.leaving=False
        assert s.block==16
    if s.block==17: enter(); walk.checkpoint('H','Sir Dargaard tomb')
    if not game.vm.m0(0x4C9D)&128:
        for cell in ((10,10),(14,10),(14,5)): walk.go(cell)
        walk.checkpoint('G','Dargaard fear test')
    if not game.vm.m0(0x4C9E)&32:
        for cell in ((12,4),(14,3),(9,2)): walk.go(cell)
        walk.checkpoint('G','Dargaard honor test')
    if not game.vm.m0(0x4C9F)&32: walk.attempt(lambda:walk.go((4,10)),min_active=5)
    walk.cure()
    if not game.vm.m0(0x4C9F)&64: walk.attempt(lambda:walk.go((3,15)),min_active=5)
    walk.checkpoint('G','Dargaard second battle')
    if not game.vm.m0(0x4C9F)&128:
        leave(); walk.road((13,5)); walk.train_party(True,preferred=walk.preferred); enter()
        walk.attempt(lambda:walk.go((1,12)),min_active=5)
    assert game.vm.m0(0x4C9A)==3
    for cell in ((12,13),(9,13),(13,15)):
        walk.attempt(lambda:walk.go(cell),min_active=5)
    assert game.vm.m0(0x4C9B)==1
    walk.checkpoint('G','Dargaard laid to rest')
    walk.equip_dargaard()
    walk.rest(); walk.attempt(leave,min_active=5)
    walk.road((13,5)); walk.revive(); walk.train_party(True,preferred=walk.preferred)
    walk.checkpoint('B','Outpost after Dargaard')


def inside_ogre(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    if s.block==17:
        walk.choose('LEAVE'); walk.choose('NO'); walk.road((16,3))
        walk.checkpoint('F','Ogre base entrance')
    if not game.vm.m0(0x4CD6): walk.go((15,7))
    if not game.vm.m0(0x4CDE):
        walk.attempt(lambda:walk.go((12,11)),min_active=5); walk.rest()
        walk.checkpoint('F','Ogre assassination evidence')
    walk.attempt(lambda:walk.go((8,8)),min_active=5)
    assert s.block==16 and game.vm.m0(0x4CD2)==1 and game.vm.m0(0x4CDD)==1
    walk.checkpoint('F','Gravnak alliance')
    walk.road((13,5)); walk.revive(); walk.train_party(True,preferred=walk.preferred)
    walk.checkpoint('B','Outpost after Gravnak')


def inside_southern(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    if s.block==17:
        walk.choose('LEAVE'); walk.choose('NO'); walk.road((15,11))
        walk.checkpoint('D','Southern Outpost entrance')
    if not game.vm.m0(0x4CA4)&8:
        walk.go((8,4)); walk.rest()
        walk.attempt(lambda:walk.go((9,2)),min_active=5)
        walk.checkpoint('J','Southern Outpost children rescued')
    if not game.vm.m0(0x4CA4)&16:
        walk.attempt(lambda:walk.go((8,4)),min_active=5); walk.rest()
        walk.attempt(lambda:walk.go((4,10)),min_active=5)
        walk.checkpoint('J','Southern Outpost real guards freed')
    if not game.vm.m0(0x4CA4)&32:
        walk.attempt(lambda:walk.go((5,13)),min_active=5)
        walk.choose('search'); walk.settle()
    if not game.vm.m0(0x4C05)&128:
        walk.go((8,4)); walk.rest()
        walk.attempt(lambda:walk.go((3,8)),min_active=5)
        walk.checkpoint('J','Southern Outpost false commandant defeated')
    if not game.vm.m0(0x4CA5):
        walk.go((8,4)); walk.rest()
        walk.attempt(lambda:walk.go((3,6)),min_active=3,survivors=(2,5))
        assert game.vm.m0(0x4CA5)==1
        walk.rest(); walk.checkpoint('J','Southern Outpost Jadefang defeated')
    walk.go((15,8),2); walk.choose('forward'); walk.settle()
    walk.road((13,5)); walk.revive(); walk.train_party(True,preferred=walk.preferred)
    walk.checkpoint('D','Outpost after Southern Outpost')


def inside_sanction(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    if s.block==17:
        walk.choose('LEAVE'); walk.choose('NO'); walk.road((10,13))
    assert (s.dataset,s.block)==(3,80)
    if game.vm.m0(0x4CB3)!=255:
        walk.attempt(lambda:(walk.go((13,14)),walk.go((15,14))),min_active=5,survivors=(0,1,2,5)); walk.rest()
        walk.attempt(lambda:walk.go((14,11)),min_active=5,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CB3)==255
        walk.checkpoint('H','Sanction dark elf defeated')
    if not game.vm.m0(0x4CAE)&32:
        walk.attempt(lambda:walk.go((15,14)),min_active=5,survivors=(0,1,2,5)); walk.rest()
        for goal in ((5,5),(9,5),(9,6)):
            walk.attempt(lambda:walk.go(goal),min_active=5,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CAE)&56==56
    if game.vm.m0(0x4CB4)!=255:
        walk.attempt(lambda:walk.go((1,12)),min_active=5,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CB4)==255
        walk.checkpoint('H','Sanction shadow amulet')
    walk.attempt(lambda:walk.go((15,14)),min_active=5,survivors=(0,1,2,5)); walk.rest()
    walk.checkpoint('H','Sanction recovered with shadow amulet')
    walk.attempt(lambda:walk.go((8,9)),min_active=5,survivors=(0,1,2,5))
    assert (s.dataset,s.block)==(3,81)
    walk.checkpoint('B','Huerzyd entrance')


def inside_huerzyd(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    if not game.vm.m0(0x4CB5)&8:
        walk.attempt(lambda:walk.go((13,2)),min_active=5,survivors=(0,1,2,5))
    if not game.vm.m0(0x4CB6)&4:
        walk.go((13,0),6); walk.choose('forward'); walk.settle()
        assert (s.x,s.y)==(15,15)
        walk.attempt(lambda:walk.go((13,14)),min_active=4,survivors=(0,1,2,5))
        walk.checkpoint('C','Huerzyd shadowpeople conclave')
        for entrance in ((0,15),(0,14)):
            walk.attempt(lambda:walk.go(entrance,6),min_active=4,survivors=(0,1,2,5))
            walk.choose('forward'); walk.settle()
        walk.attempt(lambda:walk.go((7,11)),min_active=4,survivors=(0,1,2,5))
        walk.rest(); walk.checkpoint('D','Huerzyd common area recovered')
    if not game.vm.m0(0x4CB5)&16:
        walk.go((0,13),6); walk.choose('forward'); walk.settle()
        walk.attempt(lambda:walk.go((3,10)),min_active=4,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CB5)&16
        walk.checkpoint('F','Huerzyd Ancient Revered One')
    walk.go((0,10),6); walk.choose('forward'); walk.settle()
    assert (s.dataset,s.block)==(3,82)
    walk.checkpoint('G','Duerghast dungeons entrance')


def inside_dungeons(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    def recover():
        def common():
            walk.go((15,0),2); walk.choose('forward'); walk.settle()
            walk.go((8,10),2); walk.choose('forward'); walk.settle(); walk.go((7,11))
        walk.attempt(common,min_active=3,survivors=(0,1,2,5)); walk.rest()
        walk.go((0,13),6); walk.choose('forward'); walk.settle()
        walk.go((0,10),6); walk.choose('forward'); walk.settle()
        assert (s.dataset,s.block)==(3,82)
    if not game.vm.m0(0x4CC1)&8:
        walk.attempt(lambda:walk.go((13,3)),min_active=3,survivors=(0,1,2,5))
        walk.attempt(lambda:walk.go((15,7)),min_active=3,survivors=(0,1,2,5))
        walk.checkpoint('I','Duerghast torture victim rescued'); recover()
    if not game.vm.m0(0x4CC1)&32:
        walk.attempt(lambda:walk.go((13,9)),min_active=3,survivors=(0,1,2,5))
        walk.checkpoint('I','Duerghast corridor guards defeated'); recover()
    if not game.vm.m0(0x4CC1)&128:
        walk.attempt(lambda:walk.go((12,13)),min_active=3,survivors=(0,1,2,5))
        walk.attempt(lambda:walk.go((11,13)),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC1)&128
        from .shop import I
        assert any(it[I['type']]==69 for c in s.party for it in c.items)
        walk.checkpoint('J','Duerghast dragonlance obtained')
        walk.rest()
    walk.equip_dragonlance()
    if not game.vm.m0(0x4CC2)&2:
        def upstairs():
            walk.go((5,15),4); walk.choose('forward'); walk.settle()
        walk.attempt(upstairs,min_active=3,survivors=(0,1,2,5))
        walk.checkpoint('G','Duerghast temple entrance')
    if not game.vm.m0(0x4CC2)&16:
        walk.cure()
        walk.attempt(lambda:walk.go((10,3)),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC2)&16
        walk.checkpoint('I','Duerghast Skyla defeated')
    walk.attempt(lambda:walk.go((11,4)),min_active=3,survivors=(0,1,2,5)); walk.rest()
    if not game.vm.m0(0x4CC3)&1:
        walk.attempt(lambda:walk.go((10,8)),min_active=3,survivors=(0,1,2,5))
        walk.attempt(lambda:walk.go((12,8)),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC3)&1
        walk.attempt(lambda:walk.go((11,4)),min_active=3,survivors=(0,1,2,5)); walk.rest()
        walk.checkpoint('I','Duerghast manuscript recovered')
    if not game.vm.m0(0x4CC3)&2:
        walk.attempt(lambda:walk.go((2,10)),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC3)&2
        walk.checkpoint('H','Duerghast blue dragons defeated and eggs secured')
        walk.attempt(lambda:walk.go((11,4)),min_active=3,survivors=(0,1,2,5)); walk.rest()
    if not game.vm.m0(0x4CC3)&8:
        walk.attempt(lambda:walk.go((1,2)),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC3)&8
        walk.checkpoint('H','Duerghast arena undead defeated')
        walk.attempt(lambda:walk.go((11,4)),min_active=3,survivors=(0,1,2,5)); walk.rest()
    if not game.vm.m0(0x4CC5):
        walk.prepare_fire()
        def approach():
            walk.go((3,5),2)
            if any(town.field(c,'status') not in (0,6) or
                   town.field(c,'status')==0 and town.field(c,'hp')*2<town.field(c,'hp_max') for c in s.party):
                raise AssertionError('campaign party needs recovery')
        walk.attempt(approach,min_active=sum(town.field(c,'status')<6 for c in s.party),survivors=(0,1,2,5))
        walk.cure(); walk.resist_fire(); walk.checkpoint('G','Duerghast protected before Sir Lebaum')
        def lebaum():
            walk.choose('forward'); walk.settle()
        walk.attempt(lebaum,min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4CC5)==255
        walk.checkpoint('H','Duerghast Sir Lebaum defeated')
        walk.go((0,15),6); walk.choose('forward'); walk.settle()
    try: walk.rest()
    except AssertionError as error:
        if str(error)!='campaign healing limit': raise
    walk.attempt(lambda:walk.go((0,8)),min_active=3,survivors=(0,1,2,5))
    assert (s.dataset,s.block)==(3,96)
    walk.checkpoint('F','Flying citadel arrival after Duerghast pursuit')


def inside_citadel(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    walk.preferred=(24,102,34,47,15,21,3,6)
    def climb(goal,face):
        walk.go(goal,face); walk.choose('forward'); walk.settle()
    if not game.vm.m0(0x4C04):
        walk.attempt(lambda:walk.go((6,12)),min_active=3,survivors=(0,1,2,5))
        walk.checkpoint('G','Flying citadel main tower entered')
        walk.attempt(lambda:climb((8,9),2),min_active=3,survivors=(0,1,2,5))
        walk.cure()
        for goal,face in (((10,9),4),((10,11),2),((10,9),4),((10,11),2),((10,9),4)):
            walk.attempt(lambda:climb(goal,face),min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4C05)==7
        walk.checkpoint('I','Flying citadel seventh floor'); walk.cure()
        walk.attempt(lambda:climb((10,11),2),min_active=3,survivors=(0,1,2,5))
        walk.resist_fire()
        walk.checkpoint('J','Windcaptain guards defeated, rested and fire protected')
        def collision():
            if not game.vm.m0(0x4C04): walk.choose('forward'); walk.settle()
        walk.attempt(collision,min_active=3,survivors=(0,1,2,5))
        assert game.vm.m0(0x4C04)==1
        walk.checkpoint('B','Flying citadel collision survived')
        walk.recover()
    walk.attempt(lambda:climb((11,4),6),min_active=3,survivors=(0,1,2,5))
    walk.attempt(lambda:walk.go((3,7)),min_active=3,survivors=(0,1,2,5))
    assert game.vm.m0(0x4CD1)==1
    walk.checkpoint('D','Flying citadel uniforms captured')
    walk.attempt(lambda:walk.go((0,10)),min_active=3,survivors=(0,1,2,5))
    assert (s.dataset,s.block)==(3,97)
    walk.checkpoint('F','Kernen after flying citadel escape')


def inside_kernen(session):
    walk=StoryWalk(session); game=session.game; s=game.s
    walk.preferred=(24,102,34,47,15,21,3,6)
    walk.rest()
    for goal in ((14,7),(3,11),(0,4),(14,12),(14,2),(10,14),(5,11)):
        walk.attempt(lambda:walk.go(goal),min_active=3,survivors=(0,1,2,5))
    assert game.vm.m0(0x4CEB)==5 and game.vm.m0(0x4CE8)==1
    walk.checkpoint('I','Kernen allies and diversions secured')
    walk.attempt(lambda:walk.go((6,14)),min_active=3,survivors=(0,1,2,5))
    assert session.decision['kind']=='CREATE_MENU'
    from . import creation
    for member,char in enumerate(s.party):
        if town.field(char,'status'): continue
        walk.choose(game.menu_ids.index(creation.TRAIN)); walk.choose(member)
        for _ in range(30):
            d=session.decision
            if d['kind']=='CREATE_MENU': break
            walk.choose(next((v for v in ('Fireball','Stinking Cloud','Lightning Bolt','Yes') if v in (d['options'] or [])),0))
        else: raise AssertionError('Kernen training choice limit')
    walk.choose(game.menu_ids.index(creation.BEGIN)); walk.settle(); walk.rest()
    walk.checkpoint('J','Kernen trained and rested before gate')
    walk.resist_fire(); walk.assault=True
    walk.attempt(lambda:walk.go((6,8)),min_active=3,survivors=(0,1,2,5))
    assert game.vm.m0(0x4CE7)==1
    walk.checkpoint('B','Kernen gate secured and rested under ogre guard')
    walk.equip_recovered_gifts(); walk.money=False
    walk.resist_fire()
    def enter():
        walk.go((6,8),0); walk.choose('forward'); walk.settle()
    walk.attempt(enter,min_active=4,survivors=(0,1,2,5))
    assert (s.dataset,s.block)==(3,98) and game.vm.m0(0x4C0B)&1
    walk.checkpoint('F','Myrtani stronghold entrance guards defeated')


def inside_stronghold(session):
    walk=StoryWalk(session); game=session.game
    walk.money=False; walk.preferred=(24,102,34,47,15,21,3,6)
    def choice(d):
        options=d['options'] or []
        if 'USE KEY' in options: return 'USE KEY'
        if 'NO' in options and 'YOU FIND A PASSAGE' in ''.join(game.vm.out[-6:]): return 'NO'
        return walk.story_choice(d)
    walk.policy=choice; walk.cure()
    walk.attempt(lambda:walk.go((7,4)),min_active=4,survivors=(0,1,2,5))
    walk.checkpoint('H','Myrtani inner guards defeated')
    walk.recover()
    walk.attempt(lambda:walk.go((10,5)),min_active=3,survivors=(0,1,2,5))
    walk.choose('look'); walk.settle(); assert game.vm.m0(0x4C07)==1
    walk.checkpoint('J','Myrtani bedroom key recovered')
    for goal in ((9,2),(11,2)):
        walk.attempt(lambda:walk.go(goal),min_active=3,survivors=(0,1,2,5))
    assert game.vm.m0(0x4C0A)==1
    walk.rest(); walk.checkpoint('D','Myrtani salve and native camp recovery')
    walk.attempt(lambda:walk.go((4,3)),min_active=3,survivors=(0,1,2,5))
    walk.rest(); walk.resist_fire()
    walk.checkpoint('F','Protected before Dragon Master')
    walk.attempt(lambda:walk.go((4,6)),min_active=3,survivors=(0,1,2,5))
    assert game.vm.m0(0x4C04)==1
    walk.checkpoint('G','Dragon Master and five red pupils defeated')
    walk.rest(); walk.resist_fire()
    walk.checkpoint('H','Recovered and protected before Myrtani')
    walk.policy=walk.story_choice
    def ending():
        walk.choose('look'); walk.settle()
    walk.attempt(ending,min_active=1)
    assert game.vm.m0(0x4C3A)==1
    walk.checkpoint('F','Champions of Krynn ending reached')


def inside_throtl(session, frame=lambda label:None, verbose=False):
    walk=ThrotlWalk(session,frame,verbose); game=session.game
    walk.focus=True; walk.retry=getattr(game,'roster_directory',None) is not None
    walk.rest()
    for goal in ((0,3),(2,6),(0,3),(6,11),(1,11),(1,14),(1,11)):
        walk.go(goal)
        if goal==(6,11):
            assert game.vm.m0(0x4C49)==1; frame('caramon_rescued')
        if goal==(1,14):
            assert game.vm.m0(0x4C46)==1; frame('temple_key')
        if goal in ((0,3),(1,11)): walk.rest()
    walk.go((7,6),2); walk.choose('forward'); walk.settle()
    assert game.s.block==33 and (game.s.x,game.s.y)==(8,6); frame('temple_entry')
    walk.train_at_outpost(False)
    walk.go((12,6)); walk.rest(False); walk.focus=True; walk.go((12,7))
    assert game.vm.m0(0x4C61)==255; frame('temple_wards_down')
    walk.rest(); walk.focus=True; walk.train_at_outpost(); walk.choose('forward'); walk.settle()
    assert game.s.block==34 and (game.s.x,game.s.y)==(0,0); frame('catacombs_entry')
    walk.focus=True
    for goal in ((1,0),(8,1)):
        walk.go(goal); walk.go((0,0),6); walk.choose('forward'); walk.settle()
        assert game.s.block==33
        if goal==(8,1): walk.train_at_outpost()
        walk.rest(); walk.go((9,0),0); walk.choose('forward'); walk.settle()
    walk.go((15,0),2); walk.choose('forward'); walk.settle()
    assert (game.s.x,game.s.y)==(0,1)
    walk.focus=True
    walk.go((5,2)); walk.rest(False); walk.go((4,2)); walk.rest(False)
    walk.go((4,3)); frame('gargath_map'); walk.go((5,4)); walk.rest()
    walk.ready_wand()
    walk.focus=True
    for goal,face in (((15,1),2),((0,8),6),((1,9),None)):
        walk.go(goal,face)
        if face is not None:
            walk.choose('forward'); walk.settle()
            assert (game.s.x,game.s.y,game.s.dir)=={(15,1):(0,3,2),(0,8):(15,4,6)}[goal]
    assert game.vm.m0(0x4C57)==game.vm.m0(0x4C5C)==255
    assert any(30 in roster and result[0]=='won' for _,roster,result in walk.battles)
    frame('white_dragons_defeated')
    walk.go((0,9),6); walk.choose('forward')
    assert game.s.block==16 and tuple(game.s.r0[0xC3:0xC5])==(2,1)
    frame('throtl_exit'); walk.choose('NO')
    def to_gargath():
        for _ in range(40):
            x,y=game.s.r0[0xC3:0xC5]
            if (x,y)==(14,3): return
            walk.choose('southeast' if y<3 else 'east')
            if session.decision['kind']=='MENU' and session.decision['info'].get('at')==0x8DD5:
                if tuple(game.s.r0[0xC3:0xC5])!=(14,3): walk.choose('NO')
            else: walk.settle()
        raise AssertionError('Gargath travel limit')
    walk.guarded(to_gargath) if walk.retrying() else to_gargath()
    assert game.s.block==16 and 'GARGATH' in game.vm.out[-4:]
    frame('gargath_arrival')
    from sm import ecl
    texts=[entry for entry in game.script_log if entry[1] in (32,33,34)]
    for dataset,block,address,opcode in texts:
        assert ecl.decode(game.assets.records('ECL%d'%dataset)[block][2:],address)[0]==opcode and opcode in (0x11,0x12)
    flags={hex(a):game.vm.m0(a) for a in (0x4C49,0x4C46,0x4C61,0x4C57,0x4C5C)}
    assert list(flags.values())==[1,1,255,255,255]
    casts=[e for e in game.combat_log if e['event']=='cast']
    assert any(e['spell']==87 and e['item'] for e in casts), 'found wand was not used'
    breath=[e for e in game.combat_log if e['event']=='breath']
    assert breath and all(e['kind']==83 for e in breath)
    def digest(value): return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    battles=[entry for entry in walk.battles if entry[1]]
    assert battles and all(result[0]=='won' for _,_,result in battles)
    return dict(steps=len(walk.steps),movement=digest(walk.steps),battles=battles,
                events=len(walk.events),event_hash=digest(walk.events),texts=len(texts),text_hash=digest(texts),flags=flags,breaths=len(breath))


KEEP_OUT=(((5,11),4,(2,11)),((1,11),4,(14,5)),((15,5),4,(10,5)),((13,2),6,(6,3)),((0,4),6,(8,11)))


def inside_gargath(session, frame=lambda label:None, verbose=False):
    earlier=inside_throtl(session,frame)
    walk=ThrotlWalk(session,frame,verbose); walk.focus=True; s=session.game.s
    walk.retry=getattr(session.game,'roster_directory',None) is not None
    walk.money=True
    from sm.titles.cok._cli import at_outpost
    def temple_recovery():
        from sm.titles.cok import combat, shop
        patients=[i for i,c in enumerate(s.party) if town.field(c,'status')==6 and (combat.has(c,55) or town.field(c,'race')>=2)]
        sickbed=[i for i,c in enumerate(s.party) if town.field(c,'status')<6 and sick(c)]
        if not patients and not sickbed: return
        walk.choose('NEXT'); walk.choose('TEMPLE')
        for i,c in enumerate(s.party):
            if not any(shop.coins(c)[5:]): continue
            while s.sel!=i: walk.choose('char-down')
            walk.choose('Appraise')
            for _ in range(100):
                if session.decision['kind']=='TEMPLE': break
                walk.choose('Sell' if 'Sell' in session.decision['options'] else 0)
            else: raise AssertionError('appraisal limit')
        needed=sum(500 if combat.has(s.party[i],55) else 2750 for i in patients)+500*len(sickbed)
        def funds(): return sum(shop.coin_value(session.game,shop.coins(c)) for c in s.party)+shop.coin_value(session.game,s.treasure_money)
        goods=sorted((int.from_bytes(item[shop.I['value']:shop.I['value']+2],'little'),i,j)
                     for i,c in enumerate(s.party) for j,item in enumerate(c.items)
                     if not item[shop.I['readied']] and int.from_bytes(item[shop.I['value']:shop.I['value']+2],'little')>=400)
        for value,i,_ in goods:
            if funds()>=needed: break
            char=s.party[i]
            index=next(j for j,item in enumerate(char.items) if not item[shop.I['readied']] and int.from_bytes(item[shop.I['value']:shop.I['value']+2],'little')==value)
            while s.sel!=i: walk.choose('char-down')
            walk.choose('View'); walk.choose('Items'); walk.choose(index)
            walk.choose('Sell'); walk.choose('Yes'); walk.choose('Exit'); walk.choose('Exit')
            assert session.decision['kind']=='TEMPLE'
        walk.choose('Pool')
        patients.sort(key=lambda i:not combat.has(s.party[i],55))
        for i in patients:
            poison=combat.has(s.party[i],55); cost=500 if poison else 2750
            if shop.coin_value(session.game,s.treasure_money)<cost: continue
            while s.sel!=i: walk.choose('char-down')
            walk.choose('Heal'); walk.choose(6 if poison else 7); walk.choose('Yes'); walk.choose(0)
            assert town.field(s.party[i],'status')==0
            walk.choose('Exit')
        for i in sickbed:
            if shop.coin_value(session.game,s.treasure_money)<500: continue
            while s.sel!=i: walk.choose('char-down')
            walk.choose('Heal'); walk.choose(1); walk.choose('Yes'); walk.choose(0)
            assert not sick(s.party[i]), s.party[i].effects
            walk.choose('Exit')
        if 'Share' in session.decision['options']: walk.choose('Share')
        walk.choose('Exit')
        if session.decision['kind']=='SHOP_CONFIRM': walk.choose('No')
        assert at_outpost(session)
        frame('temple_recovery')
    def visit_outpost(report=False):
        walk.choose('NO')
        walk.guarded(lambda:outpost_trip(report)) if walk.retrying() else outpost_trip(report)
    def outpost_trip(report):
        while tuple(s.r0[0xC3:0xC5])!=(1,3):
            walk.choose('west')
            if session.decision['kind']=='MENU' and session.decision['info'].get('at')==0x8DD5:
                walk.choose('YES' if tuple(s.r0[0xC3:0xC5])==(1,3) else 'NO')
            else: walk.settle()
        while not at_outpost(session): walk.choose(0)
        temple_recovery()
        if report:
            walk.choose('COMMANDANT')
            for _ in range(100):
                if at_outpost(session): break
                walk.choose(0)
            else: raise AssertionError('Commandant report limit')
            frame('throtl_reported')
        else:
            walk.choose('INN'); walk.choose(0); recover_camp(session,preferred=walk.preferred)
        walk.train_party(True)
        walk.choose('LEAVE'); walk.choose('NO')
        while tuple(s.r0[0xC3:0xC5])!=(14,3):
            walk.choose('east')
            if session.decision['kind']=='MENU' and session.decision['info'].get('at')==0x8DD5:
                if tuple(s.r0[0xC3:0xC5])!=(14,3): walk.choose('NO')
            else: walk.settle()
    visit_outpost(True)
    walk.policy=lambda d: '101' if d['options'] is None else next((v for v in ("SAY YOU'RE TRADESMEN",'BLUFF','MAKE UP A UNIT','SIT','FIGHT','LEAVE') if v in d['options']),None)
    walk.rest_after_battle=True
    walk.recovery=(7,10)
    def gate():
        if s.block==16 and session.decision['kind']=='MOVE':
            walk.choose('west'); walk.settle()
            for _ in range(20):
                d=session.decision
                if d['kind']=='MENU' and d['info'].get('at')==0x8DD5 and tuple(s.r0[0xC3:0xC5])==(14,3): break
                if d['kind']=='MOVE': walk.choose('east')
                elif d['kind']=='MENU' and d['info'].get('at')==0x8DD5: walk.choose('NO')
                else: walk.settle()
            else: raise AssertionError('Gargath entry prompt not reached after reload')
        for choice in ('YES',0,"SAY YOU'RE TRADESMEN",0,'BLUFF',0,0):
            if session.decision['kind'].startswith('COMBAT_') or session.decision['kind']=='MOVE': break
            walk.choose(choice)
        walk.settle()
    walk.guarded(gate) if walk.retrying() else gate()
    assert (s.dataset,s.block,s.x,s.y)==(2,48,8,15), (s.dataset,s.block,s.x,s.y,session.decision['kind'],session.decision['options'])
    frame('gargath_gate')
    walk.go((8,14),arrival=(11,12)); frame('gargath_hoods')
    walk.go((8,10)); walk.go((6,10)); walk.go((7,10)); walk.rest()
    walk.go((13,6),arrival=(13,5)); frame('gargath_officers')
    walk.go((8,7)); walk.go((7,10)); walk.rest(); walk.go((3,0),0)
    walk.go((8,15),4); walk.choose('forward'); assert s.block==16
    visit_outpost()
    walk.choose('YES'); walk.settle(); assert s.block==48
    walk.go((7,10)); walk.rest(); walk.go((3,0),0)
    walk.policy=None; walk.focus=True; walk.choose('forward'); walk.settle()
    assert s.block==49; frame('gargath_keep')
    walk.rest_after_battle=False
    walk.go((8,11),6); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(0,4)
    walk.go((5,5)); frame('keep_castellan')
    walk.go((1,1)); frame('keep_prisoner')
    walk.go((6,3),2); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(13,2)
    walk.go((10,5),4); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(15,5)
    walk.go((14,5),4); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(1,11)
    walk.go((2,11),4); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(5,11)
    walk.go((4,10),0); walk.choose('forward'); walk.settle()
    assert (s.x,s.y)==(4,9); frame('keep_treasure')
    def cure_trip():
        if not any(town.field(c,'status')<6 and sick(c) for c in s.party): return
        policy,walk.policy=walk.policy,None
        for goal,face,arrival in KEEP_OUT:
            walk.go(goal,face); walk.choose('forward'); walk.settle(); assert (s.x,s.y)==arrival
        walk.go((11,15),4); walk.choose('forward'); walk.settle(); assert s.block==48
        walk.go((8,15),4); walk.choose('forward'); assert s.block==16
        visit_outpost()
        walk.choose('YES'); walk.settle(); assert s.block==48
        walk.go((3,0),0); walk.choose('forward'); walk.settle(); assert s.block==49
        for goal,face,arrival in ((8,11),6,(0,4)),((6,3),2,(13,2)),((10,5),4,(15,5)),((14,5),4,(1,11)),((2,11),4,(5,11)),((4,10),0,(4,9)):
            walk.go(goal,face); walk.choose('forward'); walk.settle(); assert (s.x,s.y)==arrival
        walk.policy=policy
    walk.rest(); cure_trip()
    walk.focus='auto'
    walk.go((5,9)); frame('keep_eggs')
    walk.go((4,9)); walk.rest(); cure_trip()
    walk.policy=lambda d: next((v for v in ('STAY','NO') if v in d['options']),None)
    walk.go((6,10)); frame('myrtani_stairs')
    walk.go((4,9)); walk.rest(); cure_trip()
    walk.policy=None; walk.go((6,10),arrival=(0,14)); frame('tower_ascent')
    walk.policy=lambda d: next((v for v in ('DOWN','NO') if v in d['options']),None)
    walk.choose('look'); walk.settle(); assert (s.x,s.y)==(6,10)
    walk.go((4,9)); walk.rest(); cure_trip()
    walk.policy=lambda d: 'NO' if (s.x,s.y)==(0,15) and 'NO' in d['options'] else None
    walk.go((6,10),arrival=(0,15)); frame('black_dragons_defeated')
    assert session.game.vm.m0(0x4C7D)==255
    walk.policy=lambda d: next((v for v in ('DOWN','YES') if v in d['options']),None) if (s.x,s.y)!=(6,10) else ('NO' if 'NO' in d['options'] else None)
    walk.choose('look'); walk.settle(); assert (s.x,s.y)==(6,10)
    walk.go((4,9)); walk.rest(); cure_trip(); walk.policy=None
    for goal,face,arrival in KEEP_OUT:
        walk.go(goal,face); walk.choose('forward'); walk.settle(); assert (s.x,s.y)==arrival
    walk.go((11,15),4); walk.choose('forward'); walk.settle(); assert s.block==48
    walk.focus=True; walk.recovery=(7,10); walk.rest_after_battle=True
    walk.go((7,10)); walk.rest()
    walk.go((8,15),4); walk.choose('forward'); assert s.block==16
    frame('gargath_exit'); walk.choose('NO')
    def to_outpost():
        for direction in ('southwest','south'):
            walk.choose(direction)
            if session.decision['kind']=='MENU' and session.decision['info'].get('at')==0x8DD5: walk.choose('YES')
            elif session.decision['kind']!='MOVE': walk.settle()
        for _ in range(100):
            if at_outpost(session): return
            walk.choose(0)
        raise AssertionError('southern Outpost arrival limit')
    walk.guarded(to_outpost) if walk.retrying() else to_outpost()
    assert tuple(s.r0[0xC3:0xC5])==(13,5)
    walk.choose('COMMANDANT')
    for _ in range(100):
        if at_outpost(session): break
        walk.choose(0)
    else: raise AssertionError('Gargath report limit')
    frame('gargath_reported'); temple_recovery()
    walk.train_party(True)
    walk.choose('LEAVE'); walk.choose('NO')
    for direction in ('southwest','south'):
        walk.choose(direction)
        if session.decision['kind']=='MENU' and session.decision['info'].get('at')==0x8DD5: walk.choose('YES')
        elif session.decision['kind']!='MOVE': walk.settle()
    walk.settle(); assert (s.dataset,s.block)==(2,50)
    frame('jelek_arrival')
    assert (s.x,s.y)==(2,15) and tuple(s.r0[0xC3:0xC5])==(12,7)
    from sm import ecl
    texts=[entry for entry in session.game.script_log if entry[0]==2 and entry[1] in (48,49,50)]
    for disk,block,address,opcode in texts:
        assert ecl.decode(session.game.assets.records('ECL%d'%disk)[block][2:],address)[0]==opcode and opcode in (0x11,0x12)
    flags={hex(a):session.game.vm.m0(a) for a in (0x4C70,0x4C7D)}
    assert list(flags.values())==[255,255]
    battles=[entry for entry in walk.battles if entry[1]]
    assert all(result[0]=='won' for _,_,result in battles)
    assert any(block==49 and roster==(2,2,2) for block,roster,_ in battles)
    breath=[e for e in session.game.combat_log if e['event']=='breath' and e['kind']==90]
    assert breath
    def digest(value): return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    return dict(throtl=earlier,steps=len(walk.steps),movement=digest(walk.steps),battles=battles,
                events=len(walk.events),event_hash=digest(walk.events),texts=len(texts),text_hash=digest(texts),flags=flags,acid_breaths=len(breath))


def throtl_route(folder=None, detour=False, browser=False, onward=None, limit=30_000, record=None, session=None):
    from sm.titles.cok import combat, creation
    from sm.titles.cok._combat_test import ambush, fight, finish_battle, audit
    from sm.titles.cok.ui import screen
    if session is None: session=ambush(folder)
    elif session.decision['kind']!='COMBAT_ACTION':
        from sm.titles.cok._cli import at_outpost
        for _ in range(32):
            if at_outpost(session): break
            session.step(0)
            if session.error: raise session.error
        else: raise AssertionError('caravan departure: Outpost menu not reached')
        for label in ('LEAVE','NO','northeast',0):
            session.step(label if isinstance(label,int) else session.decision['options'].index(label))
            if session.error: raise session.error
    game=session.game; frames={}; checkpoints=[]; server=worker=None
    step=session.step
    def limited_step(choice):
        if len(game.trace)>=limit:
            raise town.BindingRequired('route limit: block %d/%d, %d decisions, hash %s'%(game.s.dataset,game.s.block,len(game.trace),game.state_hash()))
        return step(choice)
    session.step=limited_step
    try:
        caravan=fight(session=session)
        controller=screen.Controller(session)
        if browser:
            from threading import Thread
            from sm.ui.web import Server
            from sm.titles.cok.ui._screen_test import request
            server=Server(session,port=0,profile=cok,presentation=True); controller=server.controller
            worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.01}); worker.start()
        def choose(label):
            options=session.decision['options']
            session.step(label if isinstance(label,int) else options.index(label))
            if session.error: raise session.error
            controller.capture_text()
        def frame(label,marker=False):
            controller.capture_text()
            controller.drop_holds()
            before=game.state_hash(); f=screen.render(controller)
            frames[label]=hashlib.sha256(b''.join(f.rows)).hexdigest()
            checkpoints.append(dict(label=label,i=len(game.trace),state=before,frame=frames[label],
                                    block=(game.s.dataset,game.s.block),position=(game.s.x,game.s.y,game.s.dir)))
            if server:
                body,headers=request(server,'/frame?t=0')
                assert body==b''.join(f.rows) and headers['X-Frame-Hash']==frames[label]
            assert game.state_hash()==before
            if marker:
                assert game.vm.display.get('kind')=='BIGPIC' and game.vm.display['id']==121
                icon=controller.assets.combat_picture('CURSOR',1)[0]
                x,y=((v+1)*8 for v in game.s.r0[0xC3:0xC5])
                assert all(f.rows[y+j][x+i]==v for j,row in enumerate(icon) for i,v in enumerate(row) if v!=13)
            if label.startswith('npc_'):
                battle=combat.Battle(game)
                for i,member in enumerate(game.s.party):
                    if town.field(member,'npc')<128: continue
                    pixels=controller.assets.combat_picture('CPIC%d'%game.s.dataset,member.rid)[0]
                    if battle.record(i)['facing']>3: pixels=tuple(row[::-1] for row in pixels)
                    assert controller.assets.combat_icon(game,i)[0]==pixels
            return f
        choose('INN'); choose(0); assert session.decision['kind']=='CAMP_MENU'; frame('inn')
        recover_camp(session); controller.capture_text()
        choose('HALL'); frame('hall'); choose(game.menu_ids.index(creation.TRAIN)); choose(0)
        assert session.decision['info']['prompt']=='Not Enough Experience'; frame('training'); choose(0)
        choose(game.menu_ids.index(creation.BEGIN))
        choose('ARMOURY'); assert session.decision['kind']=='SHOP_MENU'; frame('armoury'); choose('Exit')
        choose('NEXT'); choose('TEMPLE'); assert session.decision['kind']=='TEMPLE'; frame('temple'); choose('Exit')
        choose('LEAVE'); choose('NO'); frame('overland_start',True)
        road=None
        if detour:
            road_battle(session,frame); road=finish_battle(session); controller.capture_text()
            assert road[0]=='won' and any(label.startswith('road_') for label in frames)
        while tuple(game.s.r0[0xC3:0xC5])!=(2,1):
            x,y=game.s.r0[0xC3:0xC5]
            symbol='Right' if x<2 else 'Up'
            old=x,y; before=game.s.r0[0xC6:0xCD]
            if server: request(server,'/key',dict(keysym=symbol,char=''))
            else: controller.key(symbol)
            if session.error: raise session.error
            assert tuple(game.s.r0[0xC3:0xC5])!=old
            assert game.s.r0[0xC6:0xCD]!=before
            if session.decision['kind']=='MENU' and 'THROTL' not in game.vm.out[-3:]: choose('NO')
            moved=frame('overland_moved',True)
            ground=screen.Frame(); part=controller.assets.picture('BIGPIC',121,game.s.dataset).parts[0]
            ground.blit(8+part.x*8,8+part.y*8,part.frames[0])
            px,py=((v+1)*8 for v in old)
            assert all(moved.rows[py+j][px:px+8]==ground.rows[py+j][px:px+8] for j in range(8)), 'old marker was not restored'
        assert session.decision['options'][:2]==['YES','NO'] and 'THROTL' in game.vm.out[-3:]
        choose('YES'); assert game.s.block==32 and (game.s.x,game.s.y)==(7,15)
        assert session.decision['options'][:2]==['ATTACK','LEAVE']; frame('guards')
        choose('LEAVE'); assert game.s.block==16 and tuple(game.s.r0[0xC3:0xC5])==(2,1)
        choose('YES'); choose('ATTACK'); frame('throtl_battle')
        b=combat.Battle(game)
        assert [(ident,sum(c.rid==ident for c in game.s.monsters)) for ident in (12,13,35)]==[(12,7),(13,4),(35,4)]
        terrain=hashlib.sha256(b.data['tiles']).hexdigest()
        cells=[cell for i in range(len(b.chars)) for cell in b.cells(i)]
        assert len(cells)==len(set(cells)) and all(b.terrain(b.tile(*cell))<255 for cell in cells)
        guards=finish_battle(session,spells=True); controller.capture_text()
        assert guards[0]=='won' and game.s.block==32 and session.decision['kind']=='MOVE'
        frame('inside_throtl'); before=game.s.x,game.s.y
        choose('forward'); assert (game.s.x,game.s.y)!=before; frame('throtl_step')
        assert session.decision['kind']=='MOVE'
        extended = onward(session,frame) if onward else None
        rolls=[(e['reason'],e['sides'],e['result']-1) for e in game.combat_log if e['event']=='dice' and 'RANDOM' in e['reason']]
        result=dict(caravan=caravan['rounds'],road=road,guards=guards,extended=extended,block=game.s.block,position=(game.s.x,game.s.y),
                    overland=tuple(game.s.r0[0xC3:0xC5]),furthest=next((disk,block) for disk,block,_,_ in reversed(game.script_log) if block>=32 and block!=36),
                    decisions=len(game.trace),state=game.state_hash(),dice=audit(game),encounters=rolls,terrain=terrain,frames=frames,
                    trace=hashlib.sha256(json.dumps(game.trace,separators=(',',':')).encode()).hexdigest())
        if record is not None:
            record.update(version=1,title='cok',start='native-slot-A',decisions=list(game.trace),checkpoints=checkpoints,
                          io=list(getattr(game,'story_io',())),final={key:result[key] for key in ('decisions','state','dice','trace')})
        return result
    finally:
        if server: server.shutdown(); worker.join(timeout=5); server.server_close()
        session.close()


def replay_route(record, folder=None):
    from sm.titles.cok._combat_test import audit
    from sm.titles.cok.ui import screen
    assert (record['version'],record['title'],record['start'])==(1,'cok','native-slot-A')
    session=Session(profile=cok,game=starter_game(folder)); game=session.game
    saves=TemporaryDirectory(prefix='cok-replay-'); game.roster_directory=Path(saves.name)
    controller=screen.Controller(session); checkpoints={}
    operations={}
    for index,action,slot in record.get('io',()): operations.setdefault(index,[]).append((action,slot))
    for point in record['checkpoints']: checkpoints.setdefault(point['i'],[]).append(point)
    try:
        def check():
            for point in checkpoints.get(len(game.trace),[]):
                assert game.state_hash()==point['state'],point['label']
                assert (game.s.dataset,game.s.block)==tuple(point['block']),point['label']
                assert (game.s.x,game.s.y,game.s.dir)==tuple(point['position']),point['label']
                controller.capture_text(); controller.drop_holds()
                assert hashlib.sha256(b''.join(screen.render(controller).rows)).hexdigest()==point['frame'],point['label']
        def storage():
            from . import creation
            for action,slot in operations.pop(len(game.trace),()):
                if action=='save': creation.save_game(game,slot)
                elif action=='load':
                    session.close(); town.load_game(game,slot)
                    Session.__init__(session,profile=cok,game=game)
                else: raise ValueError('unknown campaign storage action: '+action)
        check(); storage()
        for entry in record['decisions']:
            d=session.decision
            assert d is not None,session.result
            actual=(d['i'],d['kind'],game.s.dataset,game.s.block,d['info'].get('at',0),d['hash'])
            assert actual==tuple(entry[:6]),('route decision differs',actual,entry)
            session.step(entry[6])
            if session.error: raise session.error
            assert game.trace[-1]==tuple(entry)
            check(); storage()
        final=dict(decisions=len(game.trace),state=game.state_hash(),dice=audit(game),
                   trace=hashlib.sha256(json.dumps(game.trace,separators=(',',':')).encode()).hexdigest())
        assert final==record['final'],'recorded route finish differs'
        return final
    finally: session.close(); saves.cleanup()


def check_service_random():
    from types import SimpleNamespace
    from sm.titles.ssb.state import State
    from sm.titles.cok._combat_test import audit
    game=SimpleNamespace(s=State()); native=State(); proxy=town.AuditedState(game,'appraisal')
    for sides in (100,450,5000,100,1250):
        assert proxy.random(sides)==native.random(sides)
        assert game.s.seed==native.seed
    audit(game)


def check_field_cast(folder=None):
    from ._magic_test import fixture, memorize, copies
    from ._combat_test import audit
    from . import magic, camp
    with TemporaryDirectory(prefix='cok-field-cast-') as directory:
        game,table=fixture(folder,directory)
        caster,target=game.s.party[5],game.s.party[0]
        game.s.sel=5; town.put(target,'hp',3); memorize(caster,3)
        table.answers[:]=[magic.spell(3).name,camp.name(target)]
        town.service(game,'explore','cast')
        assert town.field(target,'hp')>3 and copies(caster,3)==0
        assert not table.answers
        audit(game)


def short_route(folder=None):
    from sm.titles.cok import creation
    from sm.titles.cok._cli import at_outpost
    from sm.titles.cok._combat_test import check_roster, audit
    from sm.titles.cok.ui import screen
    with TemporaryDirectory(prefix='cok-menu-') as directory:
        game=Game(None,slot=None,directory=folder); game.roster_directory=directory
        session=Session(profile=cok,game=game)
        try:
            def choose(value):
                session.step(value if isinstance(value,int) else session.decision['options'].index(value))
                if session.error: raise session.error
            choose(game.menu_ids.index(creation.LOAD)); choose('A'); choose(game.menu_ids.index(creation.BEGIN))
            for _ in range(20):
                if at_outpost(session): break
                choose(0)
            else: raise AssertionError('short witness missed the Outpost')
            assert len(game.trace)==10 and len(game.s.party)==6
            outpost=screen.render(screen.Controller(session))
            choose('LEAVE'); choose('NO'); choose('northeast'); choose(0)
            assert session.decision['kind']=='COMBAT_ACTION' and len(game.trace)==14
            check_roster(game); audit(game)
            battle=screen.render(screen.Controller(session))
            assert all(len(b''.join(frame.rows))==64000 for frame in (outpost,battle))
            assert game.state_hash()=='91a87f1204420066', game.state_hash()
            return dict(decisions=14,state=game.state_hash())
        finally: session.close()


def test(folder=None, quick=False):
    if folder: os.environ['SM_COK'] = str(folder)
    if not (folder or os.environ.get('SM_COK')): return 'skipped (no Champions copy)'
    check_fields(starter_game(folder)); check_maps(Game(None, slot=None, directory=folder).assets)
    check_script_rules(folder)
    check_vm_read(folder)
    check_service_random()
    check_field_cast(folder)
    assert town.wrapped_text('one two three', 7) == ['one', 'two', 'three']
    assert town.wrapped_text('a,b.c! d?', 5) == ['a,b.', 'c! d?']
    add_npc_order(folder)
    wall_slots_loaded_again(folder)
    check_script_holds(folder)
    return dict(maps=15,route=None if quick else short_route(folder))


def check_script_holds(folder=None):
    from collections import deque
    results = []
    for queue in (None, deque()):
        game = starter_game(folder); s, vm = game.s, game.vm
        vm.host, vm.next, vm.at, game.presentation = game, vm.pc, 0, queue
        vm.clear_text(); vm.out.append('HELD TEXT'); before = game.state_hash(); vm.op3A()
        assert game.state_hash() == before, 'DELAY changed the state'
        vm.ops = [(2, 1, 0, ''), (2, 100, 0, '')]; vm.op41()
        results.append((game.state_hash(), [town.field(c, 'experience', width=4) for c in s.party]))
        if queue is None: assert game.presentation is None
        else:
            assert [(e['kind'], e['delay'], e['text']) for e in queue] == [('script-hold', .4, 'HELD TEXT'),
                ('script-hold', .4, 'Congratulations the party gains experience!')], list(queue)
            s.x = (s.x+1) & 15; assert queue[0]['state'].x != s.x, 'the held screen keeps the square of its moment'
            s.g['game.delay'] = 9; vm.op3A(); assert queue[-1]['delay'] == .9
    assert results[0] == results[1], 'a hold queue changed the award'


def wall_slots_loaded_again(folder):
    game = starter_game(folder); s, vm = game.s, game.vm
    ident = min(game.assets.records('WALLDEF%d' % s.dataset))
    s.walls[:] = [0, 0, 0]; game.walls_filed = (1, 2, 3)
    vm.load_wall(ident, 3)
    assert game.walls_filed == (1, 2) and s.walls == [0, 0, ident], (game.walls_filed, s.walls)
    vm.load_wall(0xFFFF, 2)
    assert game.walls_filed == (1,) and s.walls == [0, 0xFFFF, ident]
    town.write_character(vm, 0x7F22, 0x80 | ident)
    assert game.walls_filed == () and s.walls[0] == ident


def add_npc_order(folder):
    from sm.titles.cok import creation, combat
    from sm.titles.cok.records import Item
    from sm.titles.ssb import vm as retained
    with TemporaryDirectory(prefix='cok-npc-') as roster:
        game = Game(lambda *a, **k: 0, slot=None, directory=folder); game.roster_directory = roster
        creation.load_game(game, 'A'); vm = game.vm
        vm.v, vm.next = (lambda i: (9, 40)[i-1]), 0; vm.op36()
        npc = game.s.party[-1]; at = Item.FIELDS['readied'][0]
        filed = game.assets.records('MON1ITM')[9]
        assert len(game.s.party) == 7 and game.s.sel == 6 and town.field(npc,'npc') == 148 and town.field(npc,'order') == 6
        for load in (lambda: combat.load_monsters(game, 255, 1, 0), vm.op36):
            vm.v = lambda i: (255, 40)[i-1]
            try: load()
            except retained.Halt as fault: assert str(fault) == 'Unable to load monster' and len(game.s.party) == 7
            else: raise AssertionError('missing monster loaded')
        assert [i[at] for i in npc.items] == [filed[k+at] for k in range(0, len(filed), Item.SIZE)] and any(i[at] for i in npc.items)


ROUTE_PINS = dict(
    route=((2, 50), (12, 7), (2, 15), 22306, '4e740472a784f1f3'),
    dice='ee982d66fd023899994be8480b5ec1089c1a6fe379b7589e31febcac15298c1c',
    trace='4203b5291340c876deb6ee31be938abd87dcc98281d4bfda96f312ab219ae43d',
    arrival=(14034, '1119c5d352ce4d34'),
    throtl=(390, 159, 762, 16, 38, '30f1e2c51b714bf7351551ad6d6f6c95091f2acb0d55c6d2e52f0f11cfca077f', '7a6f5e0138cba8f7ae460a149558a1e819d13c384cafb9851d73d9c5dab0f92d', 'fc62c8b1e79877000d4834289ed60d48ae74a7129137ba2fc0c62985fc63bd45'),
    gargath=(637, 150, 720, 5, 27, '951331e446d185d4fda1e89152810f11b39b50df162efc9ed1038b2f52a978e3', '32ef6f318f91120364ffb8dbe5d462227544d9146dfcc7dfa4668f4bbd8b0d04', '985525c480949d151608bb79cee260d217944119766bb32f2832986dfe268455'))


def route_test(folder=None):
    if folder: os.environ['SM_COK']=str(folder)
    from sm.titles.cok._cli import arrive
    reports, traces = [], []
    for _ in range(2):
        with TemporaryDirectory(prefix='cok-town-') as directory:
            game = Game(None, slot=None, directory=folder); game.roster_directory = directory
            session = Session(profile=cok, game=game)
            try:
                reports.append(arrive(session)); traces.append(tuple(game.trace))
                assert len(game.s.party) == 1 and game.entry == (1,36,0x8014)
            finally: session.close()
    assert reports[0] == reports[1] and traces[0] == traces[1], 'creation and town replay diverged'
    assert reports[0]['block'] == [1,17] and reports[0]['decisions'] == 21
    check_destinations(folder)
    travel=check_travel_rules(folder)
    routes=[]
    detour=throtl_route(folder,True)
    assert detour==throtl_route(folder,True), 'road replay diverged'
    with TemporaryDirectory(prefix='cok-route-') as roster:
        def onward(session, frame):
            session.game.roster_directory=Path(roster); return inside_gargath(session,frame)
        record={}; route=throtl_route(folder,browser=True,onward=onward,record=record)
        replay_route(json.loads(json.dumps(record)),folder)
    point=next(p for p in record['checkpoints'] if p['label']=='gargath_arrival')
    throtl,gargath=route['extended']['throtl'],route['extended']
    got=dict(route=(route['furthest'],route['overland'],route['position'],route['decisions'],route['state']),
             dice=route['dice'],trace=route['trace'],arrival=(point['i'],point['state']),
             throtl=(throtl['steps'],throtl['events'],throtl['texts'],throtl['breaths'],len(throtl['battles']),
                     throtl['movement'],throtl['event_hash'],throtl['text_hash']),
             gargath=(gargath['steps'],gargath['events'],gargath['texts'],gargath['acid_breaths'],len(gargath['battles']),
                      gargath['movement'],gargath['event_hash'],gargath['text_hash']))
    assert got==ROUTE_PINS, got
    missing={'gargath_gate','gargath_hoods','gargath_officers','gargath_keep','keep_castellan','keep_prisoner',
             'keep_treasure','keep_eggs','myrtani_stairs','tower_ascent','black_dragons_defeated','gargath_exit',
             'gargath_reported','jelek_arrival'}-route['frames'].keys()
    assert not missing, sorted(missing)
    routes.extend((detour,route))
    return dict(block=reports[0]['block'], decisions=21, hash=reports[0]['hash'], maps=15, destinations=6,travel=travel,throtl=routes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder')
    parser.add_argument('--route',action='store_true')
    args=parser.parse_args()
    print(route_test(args.folder) if args.route else test(args.folder))
