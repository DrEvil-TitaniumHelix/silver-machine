import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Thread

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))

from sm import ecl
from sm.titles.cok import combat, effects, magic, rules, town
from sm.titles.cok._town_test import outpost_session


def ambush(folder=None):
    session = outpost_session(folder)
    try:
        session.step(5)
        session.step(session.decision['options'].index('NO'))
        session.step(session.decision['options'].index('northeast'))
        session.step(0)
        if session.error: raise session.error
        assert session.decision['kind'] == 'COMBAT_ACTION'
        return session
    except BaseException:
        session.close(); raise


def check_roster(game):
    code = game.assets.records('ECL1')[16][2:]
    op,operands,next_pc = ecl.decode(code,0x860B)
    ident,count,picture = [ecl.word(o) for o in operands]
    assert op == 11 and (ident,count,picture) == (1,4,1) and next_pc == 0x8612
    assert code[next_pc-0x8000] == 0x24
    monsters = game.s.monsters
    assert len(monsters) == count and all(c.rid == ident for c in monsters)
    original = rules.character(game.assets.records('MON1CHA')[ident])
    for c in monsters:
        for key in ('name','base_thac0','base_ac','attacks','dimensions','hp_max','hp_rolled','xp_award'):
            offset,size = rules.Character.FIELDS[key]
            assert c.b[offset:offset+size] == original.b[offset:offset+size],key
        assert all(c.b is not other.b and c.effects is not other.effects for other in monsters if c is not other)
    b = combat.Battle(game)
    assert game.s.r1[0x2C1]==2
    assert [b.position(i) for i in range(6,10)]==[(29,2),(28,2),(28,1),(27,1)]
    cells = [cell for i in range(len(b.chars)) for cell in b.cells(i)]
    assert len(cells) == len(set(cells))
    assert hashlib.sha256(b.data['tiles']).hexdigest() == 'c91b9a16f88b58ff1b7acf5186d8a462b6408e3823a9686bc0f9a3984fd2a7da'


def audit(game):
    previous = None
    for event in game.combat_log:
        if event['event'] != 'dice': continue
        if previous is not None: assert event['before'] == previous,('unlogged RNG',event)
        seed,faces = event['before'],[]
        for _ in range(event['count']):
            seed = (seed*0x08088405+1)&0xFFFFFFFF
            faces.append((seed>>16)%event['sides']+1 if event['sides'] else 1)
        assert tuple(faces) == event['faces'] and sum(faces)&255 == event['result'] and seed == event['after']
        previous = seed
    assert previous == game.s.seed
    return hashlib.sha256(json.dumps(game.combat_log,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def fight(attack=True, folder=None, spells=False, session=None):
    owns_session=session is None
    session = session or ambush(folder); game = session.game
    try:
        check_roster(game)
        experience = [town.field(c,'experience',width=4) for c in game.s.party]
        unavailable = False
        plan={4:[21,15],2:[15,21],5:[1,3]} if spells else {}
        pending=0
        for _ in range(1600):
            if session.error: raise session.error
            if not session.decision: break
            d = session.decision; kind,options = d['kind'],d['options']
            if kind == combat.Kind.ACTION.value:
                actor=d['info']['actor']; offered=magic.castable(game.s.chars()[actor],True)
                wanted=plan.get(actor,[])
                if wanted and 'Cast' in options and wanted[0] in [k for k,_ in offered]:
                    pending=wanted.pop(0); choice=options.index('Cast')
                else: choice = options.index('Aim' if attack and not unavailable else 'Done')
                unavailable = False
            elif kind == combat.Kind.SPELL.value:
                offered=magic.castable(game.s.chars()[d['info']['actor']],True)
                choice=next(i for i,(ident,_) in enumerate(offered) if ident==pending)
            elif kind == combat.Kind.TARGET.value:
                choice = 0
                if not d['info'].get('spell'):
                    b=combat.Battle(game); actor=b.data['actor']
                    choice=next((n for n,label in enumerate(options) if '#' in label and town.field(b.chars[int(label.rsplit('#',1)[1])],'side')!=town.field(b.chars[actor],'side')),len(options)-1)
                if spells and d['info'].get('spell'):
                    b=combat.Battle(game); ident=d['info']['spell']; actor=b.data['actor']
                    candidates=[(index,int(label.rsplit('#',1)[1])) for index,label in enumerate(options) if '#' in label]
                    candidates=[(index,j) for index,j in candidates if (town.field(b.chars[j],'side')!=town.field(b.chars[actor],'side'))==bool(magic.spell(ident).offensive)]
                    if ident==3: candidates.sort(key=lambda v:town.field(b.chars[v[1]],'hp')-town.field(b.chars[v[1]],'hp_max'))
                    choice=candidates[0][0] if candidates else options.index('Exit')
                if options == ['Exit'] or not d['info'].get('spell') and choice == len(options)-1: unavailable = True
            elif kind == combat.Kind.DONE.value: choice = options.index('Guard' if attack and 'Guard' in options else 'Quit')
            elif kind == combat.Kind.CONFIRM.value: choice = 0 if d['info'].get('prompt')=='Abort Spell? ' else 1
            elif kind == combat.Kind.LOOT.value: choice = options.index('Exit')
            elif kind == combat.Kind.ACK.value: choice = 0
            elif kind == 'MENU' and attack:
                from sm.titles.cok._cli import at_outpost
                if at_outpost(session): break
                choice = 0
            else: break
            session.step(choice)
        else: raise AssertionError('fight choice limit')
        b = combat.Battle(game)
        assert b.data['result'] == ('won' if attack else 'defeat')
        assert not game.s.monsters and not b.data['active']
        if attack:
            if not spells: assert game.s.r1[0x2C7] == 0 and game.s.r1[0x2C8] == 4 and b.data['experience'] == 108
            from sm.titles.cok._cli import at_outpost
            assert at_outpost(session) and not game.s.party_dead
            op,operands,_ = ecl.decode(game.assets.records('ECL1')[16][2:],0x8798)
            assert op == 65 and [ecl.word(o) for o in operands] == [1,1000]
            awards = {e['actor']:e['amount'] for e in game.combat_log if e['event'] == 'experience'}
            for i,c in enumerate(game.s.party):
                classes = sum(town.field(c,'levels',k,signed=True)>0 for k in range(8))
                assert town.field(c,'experience',width=4) == experience[i]+awards.get(i,0)+(1000//classes if town.field(c,'active') else 0)
        else:
            assert session.result == 'DEFEAT' and game.s.party_dead and not game.s.party and game.s.r1[0x2C7] == 128
        log_hash = audit(game)
        assert any(e['event'] == 'morale' for e in game.combat_log)
        attacks = [e for e in game.combat_log if e['event'] == 'attack']
        assert attacks and any(e['hit'] for e in attacks) and any(not e['hit'] for e in attacks)
        if spells: assert {e['spell'] for e in game.combat_log if e['event']=='cast'} >= {1,3,15,21}
        return dict(result=b.data['result'],rounds=b.data['round'],state=game.state_hash(),dice=log_hash,
                    log=game.combat_log,trace=game.trace)
    finally:
        if owns_session: session.close()


def breather(c):
    return any(combat.has(c,k) for k in (6,83,84,85,90,104))


def ground_cell(b, actor, row):
    side=town.field(b.chars[actor],'side')
    radius=2 if row.id==47 and not b.game.vm.is3d() else row.area&7
    cells={(b.position(j)[0]+dx,b.position(j)[1]+dy) for j in b.targets(actor) for dx in range(-radius,radius+1) for dy in range(-radius,radius+1)}
    reach=(row.range_base+row.range_per_level*(6 if row.id==87 else magic.caster_level(combat.EffectGame(b,'route range',actor),b.chars[actor],row.id)))&255
    def value(cell):
        result=0
        victims=sorted({j for (x,y),j in b.occupancy().items() if cell[0]<=x<=cell[0]+1 and cell[1]<=y<=cell[1]+1}) if row.id==34 else b.area_targets(*cell,radius)
        for j in victims:
            c=b.chars[j]
            if row.id==21 and combat.has(c,53): continue
            level=town.field(c,'highest_level')
            result+=(-10 if town.field(c,'side')==side else 0 if row.id==21 and (town.field(c,'undead') or level>5 or level==5 and town.field(c,'race')!=7) else 5 if any(town.field(c,'memorized',k) for k in range(58)) else 1)
        return result
    cells=[cell for cell in sorted(cells) if b.tile(*cell) and b.terrain(b.tile(*cell))<255 and list(combat.line(*b.position(actor),*cell))[-1][2]<=2*reach+1 and all(b.terrain(b.tile(x,y),2)<=b.terrain(b.tile(*b.position(actor)),1) for x,y,_ in combat.line(*b.position(actor),*cell))]
    if not cells: return None,0
    best=max(cells,key=value)
    return best,value(best)


def finish_battle(session, spells=False, focus=False, money=False):
    blocked=False; pending=0; ground=None; last_move=None; move_blocked=None; selected=set(); gave_up=False
    blessed=set()
    using=None; shared=False
    for _ in range(3200):
        if session.error: raise session.error
        d=session.decision
        if d is None: break
        kind,options=d['kind'],d['options']
        if kind=='COMBAT_ACTION':
            actor=d['info']['actor']; b=combat.Battle(session.game); c=b.chars[actor]
            offered=dict(magic.castable(c,True)); wanted=[]
            enemies=[j for j in b.targets(actor) if not b.disabled(j)]
            if spells and 'Cast' in options:
                if 47 in offered and ground_cell(b,actor,magic.spell(47))[1]>=3: wanted.append(47)
                if 3 in offered and any(town.field(b.chars[j],'hp')*2<town.field(b.chars[j],'hp_max') for j in b.targets(actor,1,allies=True) if town.field(b.chars[j],'side')==town.field(c,'side')): wanted.append(3)
                if focus and any(any(town.field(b.chars[j],'memorized',k) for k in range(58)) and not combat.has(b.chars[j],21) for j in enemies): wanted.append(25)
                if focus and len([j for j in enemies if not town.field(b.chars[j],'undead') and not combat.has(b.chars[j],99)])>=2: wanted.append(34)
                if any(town.field(b.chars[j],'race')==6 for j in enemies): wanted.append(23)
                if any(not town.field(b.chars[j],'undead') and town.field(b.chars[j],'highest_level')<5 for j in enemies): wanted.append(21)
                if enemies: wanted.insert(0,15) if any(breather(b.chars[j]) for j in enemies) else wanted.append(15)
                if actor not in blessed: wanted.append(1)
            wanted=[k for k in wanted if k in offered]
            wand=next((item for item in c.items if item[combat.I['readied']] and item[combat.I['powers']+1]==87 and item[combat.I['powers']]>0),None)
            if b.bandage(False): choice='Done'
            elif wand is not None and 'Use' in options and b.record(actor)['item_ok'] and len(b.targets(actor,6))>=3:
                using=wand; selected=set(); choice='Use'
            elif 'Turn' in options and any(town.field(b.chars[j],'undead') for j in b.targets(actor)): choice='Turn'
            elif wanted: pending=wanted[0]; selected=set(); blessed.add(actor) if pending==1 else None; choice='Cast'
            else: choice=('Move' if focus and focus not in ('auto','melee-auto') and b.record(actor)['movement']>0 and move_blocked!=(actor,d['info']['round']) else 'Done') if blocked else 'Aim'
            blocked=False
        elif kind=='COMBAT_AUTO': choice=('Magic' if not d['info']['magic'] else 'Continue') if focus=='auto' else 'Manual' if d['info']['round']==0 else 'Continue'
        elif kind=='COMBAT_MOVE':
            from heapq import heappop,heappush
            b=combat.Battle(session.game); actor=b.data['actor']; occupied=b.occupancy(); side=town.field(b.chars[actor],'side')
            goals={cell for cell,j in occupied.items() if town.field(b.chars[j],'side')!=side and b.can_target(actor,j)}
            queue=[(0,b.position(actor),None)]; seen=set(); step=None
            while queue:
                cost,cell,first=heappop(queue)
                if cell in goals: step=first; break
                if cell in seen: continue
                seen.add(cell)
                for direction in range(8):
                    dest=cell[0]+combat.DX[direction],cell[1]+combat.DY[direction]
                    tile=b.tile(*dest); other=occupied.get(dest)
                    if not tile or b.terrain(tile)==255 or other not in (None,actor) and dest not in goals: continue
                    heappush(queue,(cost+(30 if tile in (29,30) else max(1,b.terrain(tile)))*(3 if direction%2 else 2),dest,direction if first is None else first))
            choice=options[step] if step is not None else 'Done'
            stamp=(actor,d['info']['round'],b.position(actor),b.record(actor)['movement'])
            if step is None or stamp==last_move:
                choice='Done'; blocked=True; move_blocked=(actor,d['info']['round'])
            last_move=stamp
        elif kind=='COMBAT_SPELL':
            offered=magic.castable(session.game.s.chars()[d['info']['actor']],True)
            choice=options[next(i for i,(k,_) in enumerate(offered) if k==pending)]
        elif kind=='VIEW_ITEMS' and using is not None:
            c=session.game.s.chars()[combat.Battle(session.game).data['actor']]
            choice=options[next(i for i,it in enumerate(c.items) if it is using)]
        elif kind=='VIEW_ACTION' and using is not None: choice='Use'
        elif kind=='TARGET' and d['info'].get('spell'):
            b=combat.Battle(session.game); row=magic.spell(d['info']['spell']); actor=b.data['actor']
            side=town.field(b.chars[actor],'side')
            candidates=[(label,int(label.rsplit('#',1)[1])) for label in options if '#' in label]
            candidates=[(label,i) for label,i in candidates if (town.field(b.chars[i],'side')!=side)==bool(row.offensive)
                        and town.field(b.chars[i],'active')]
            if row.id==21:
                def score(pair):
                    return sum((4 if focus and any(town.field(b.chars[j],'memorized',k) for k in range(58)) else 1) if town.field(b.chars[j],'side')!=side else -2 for j in b.area_targets(*b.position(pair[1]),1) if not combat.has(b.chars[j],53))
                candidates.sort(key=score,reverse=True)
            if row.id==3: candidates.sort(key=lambda pair:town.field(b.chars[pair[1]],'hp')-town.field(b.chars[pair[1]],'hp_max'))
            if focus and row.id in (15,25):
                if row.id==25: candidates=[pair for pair in candidates if not combat.has(b.chars[pair[1]],21)]
                candidates.sort(key=lambda pair:any(town.field(b.chars[pair[1]],'memorized',k) for k in range(58)),reverse=True)
            if row.id==15: candidates.sort(key=lambda pair:breather(b.chars[pair[1]]),reverse=True)
            if row.id==23:
                candidates=[pair for pair in candidates if not b.disabled(pair[1]) and town.field(b.chars[pair[1]],'race')==6]
                candidates.sort(key=lambda pair:bool(town.field(b.chars[pair[1]],'levels',0) or town.field(b.chars[pair[1]],'levels',5)),reverse=True)
            candidates=[pair for pair in candidates if pair[1] not in selected]
            choice=candidates[0][0] if candidates else 'Exit'
            if candidates: selected.add(candidates[0][1])
            if (focus or row.id==47) and row.id in (21,34,47,87) and 'Ground' in options:
                cell,_=ground_cell(b,actor,row)
                if cell is not None: ground=cell; choice='Ground'
            if gave_up: choice='Exit'; gave_up=False
        elif kind=='COMBAT_SPELL_AIM':
            b=combat.Battle(session.game); x,y=b.data['aim']; dx,dy=ground[0]-x,ground[1]-y
            if not dx and not dy: choice='Target' if 'Target' in options else 'Exit'; gave_up=choice=='Exit'
            else:
                direction=combat.direction_to(x,y,*ground)
                choice=('north','northeast','east','southeast','south','southwest','west','northwest')[direction]
        elif kind=='TARGET':
            b=combat.Battle(session.game); side=town.field(b.chars[b.data['actor']],'side')
            choice=next((o for o in options if '#' in o and town.field(b.chars[int(o.rsplit('#',1)[1])],'side')!=side),'Exit'); blocked=choice=='Exit'
        elif kind=='COMBAT_DONE': choice='Bandage' if 'Bandage' in options else 'Auto' if focus in ('auto','melee-auto') else 'Guard' if 'Guard' in options else 'Quit'
        elif kind=='COMBAT_CONFIRM': choice=options[0] if d['info'].get('prompt')=='Abort Spell? ' else options[1]
        elif kind=='COMBAT_LOOT':
            choice='Share' if money and not shared and 'Share' in options else 'Exit'; shared=True
        elif kind=='ACK': choice=options[0]
        else: break
        session.step(options.index(choice))
    else: raise AssertionError('combat route decision limit')
    b=combat.Battle(session.game)
    assert not b.data['active']
    audit(session.game)
    return b.data['result'],b.data['round']


def check_disarm(folder=None):
    session = ambush(folder)
    try:
        game,b = session.game,combat.Battle(session.game)
        i = next(i for i,c in enumerate(b.chars) if effects.has_effect(c,7) is not None)
        c,target = b.chars[i],b.chars[6]; item = b.weapon(i)
        assert item is not None and item[combat.I['type']] == 67
        b.record(i).update(x=20,y=12,target=6); b.record(6).update(x=21,y=12)
        town.put(c,'abilities',3,7)
        seen = _seen(b); kept = item[combat.I['type']],item[combat.I['name_ids']+2]; before = len(c.items)
        item[combat.I['type']],item[combat.I['name_ids']+2] = 6,121
        b.trigger(13,6,b.context(c))
        assert seen == [combat.name(c)+' loses his weapon'] and len(c.items) == before and not b.data['bank'], seen
        item[combat.I['type']],item[combat.I['name_ids']+2] = kept; del seen[:]
        before = len(c.items); seed = game.s.seed
        b.trigger(13,6,b.context(c))
        assert seen == [combat.name(c)+' loses his weapon'], seen
        assert len(c.items) == before-1 and effects.has_effect(c,7) is None
        assert b.data['bank'][-1][0] == i and not b.data['bank'][-1][1][combat.I['readied']]
        dice = [e for e in game.combat_log if e['event'] == 'dice'][-2:]
        assert [e['sides'] for e in dice] == [20,6] and dice[0]['before'] == seed
        session.close()
        for monster in game.s.monsters:
            town.put(monster,'status',6); town.put(monster,'active',0); town.put(monster,'hp',0)
        game.player = lambda kind,options,*args,**info: options.index('Exit') if 'Exit' in options else options.index('No') if 'No' in options else 0
        b.postcombat()
        assert not b.data['bank'] and len(c.items) == before and not c.items[-1][combat.I['readied']]
        assert any(e['event'] == 'bank return' and e['actor'] == i and e['returned'] for e in game.combat_log)
        assert effects.has_effect(c,7) is None
    finally: session.close()


def check_browser(folder=None):
    from sm.titles import cok
    from sm.titles.cok.ui import screen
    from sm.titles.cok.ui._screen_test import request
    from sm.ui.web import Server
    session = ambush(folder); server = Server(session,port=0,profile=cok,presentation=True)
    worker = Thread(target=server.serve_forever,kwargs={'poll_interval':0.01}); worker.start()
    try:
        game,c = session.game,server.controller
        before = game.state_hash(); frame = b''.join(screen.render(c).rows)
        body,headers = request(server,'/frame?t=0')
        assert frame == body and len(body) == 64000 and game.state_hash() == before
        assert headers['X-Frame-Hash'] == hashlib.sha256(frame).hexdigest()
        request(server,'/key',dict(keysym='a',char='a'))
        assert session.decision['kind'] == 'TARGET' and not session.error
        request(server,'/key',dict(keysym='Escape',char=''))
        request(server,'/key',dict(keysym='m',char='m'))
        assert session.decision['kind'] == 'COMBAT_MOVE'
        b = combat.Battle(game); i = b.data['actor']; old = b.position(i); r=b.record(i)
        budget,facing,seed=r['movement'],r['facing'],game.s.seed
        before=game.state_hash(); decision=session.decision['i']
        for char in 'nsew': request(server,'/key',dict(keysym=char,char=char))
        assert game.state_hash()==before and session.decision['i']==decision
        move_frame=screen.render(c); expected=screen.Frame()
        label='Move/Attack, Move Left = 9'
        expected.text(0,24,label,c.assets,13); expected.text(len(label)+1,24,'Done',c.assets,0,background=15)
        assert move_frame.rows[192:]==expected.rows[192:]
        expected.text(23,3,'Hitpoints',c.assets,10); expected.text(33,3,'21',c.assets,10)
        assert all(row[184:312]==want[184:312] for row,want in zip(move_frame.rows[24:32],expected.rows[24:32]))
        for x,left in ((30,16),(31,14),(32,12),(33,10),(34,8),(35,4),(36,2),(37,0)):
            request(server,'/key',dict(keysym='Right',char=''))
            assert session.decision['kind']=='COMBAT_MOVE' and (b.position(i),r['movement'],r['facing'])==((x,14),left,2)
        request(server,'/key',dict(keysym='Right',char=''))
        assert b.position(i)==(37,14) and session.decision['info']['prompt']=="can't go there"
        request(server,'/key',dict(keysym='Escape',char=''))
        assert session.decision['kind']=='COMBAT_ACTION' and (b.position(i),r['movement'],r['facing'])==(old,budget,facing)
        assert game.s.seed==seed
        for done in ('Return','d'):
            c.key('m','m'); c.key('Right'); position=b.position(i); remaining=r['movement']
            c.key(done,done if len(done)==1 else '')
            assert session.decision['kind']=='COMBAT_ACTION' and (b.position(i),r['movement'],r['facing'])==(position,remaining,2)
        assert not session.error and request(server,'/frame?t=0')[0] != frame
        return hashlib.sha256(frame).hexdigest()
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close(); session.close()


def check_spell_browser(folder=None):
    from sm.titles import cok
    from sm.titles.cok.ui import screen
    from sm.titles.cok.ui._screen_test import request
    from sm.ui.web import Server
    witnesses=[]
    for ident in (15,21):
        session=ambush(folder)
        for _ in range(200):
            d=session.decision; options=d['options']; b=combat.Battle(session.game)
            if d['kind']=='COMBAT_ACTION':
                actor=d['info']['actor']; row=magic.spell(ident)
                reach=(row.range_base+row.range_per_level*magic.caster_level(combat.EffectGame(b,'range',actor),b.chars[actor],ident))&255
                if 'Cast' in options and ident in dict(magic.castable(b.chars[actor],True)) and b.targets(actor,reach): break
                choice='Done'
            elif d['kind']=='COMBAT_DONE': choice='Guard'
            else: choice=options[0]
            session.step(options.index(choice))
            if session.error: raise session.error
        else: raise AssertionError('no live spell target reached')
        server=Server(session,port=0,profile=cok,presentation=True)
        worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.01}); worker.start()
        try:
            game,c=session.game,server.controller
            key=lambda symbol,char='':request(server,'/key',dict(keysym=symbol,char=char))
            key('c','c'); assert session.decision['kind']=='COMBAT_SPELL'
            session.step(next(k for k,o in enumerate(session.decision['options']) if str(o).startswith(magic.spell(ident).name)))
            for _ in range(100):
                if session.decision['kind']=='TARGET': break
                d=session.decision; options=d['options']
                choice='Done' if d['kind']=='COMBAT_ACTION' else 'Guard' if d['kind']=='COMBAT_DONE' else options[0]
                session.step(options.index(choice))
                if session.error: raise session.error
            c.capture_text()
            assert session.decision['kind']=='TARGET'
            before=game.state_hash()
            if ident==15:
                b=combat.Battle(game)
                target=next(int(label.rsplit('#',1)[1]) for label in session.decision['options'] if '#' in label and town.field(b.chars[int(label.rsplit('#',1)[1])],'side')==1)
                tx,ty=b.position(target); key('m','m'); assert c.aim_manual
                while c.aim_cell[0]!=tx: key('Right' if c.aim_cell[0]<tx else 'Left')
                while c.aim_cell[1]!=ty: key('Down' if c.aim_cell[1]<ty else 'Up')
            frame=request(server,'/frame?t=0')[0]
            assert game.state_hash()==before and frame==b''.join(screen.render(c).rows)
            if ident==15:
                now=[0.0]; c.clock=lambda:now[0]
                key('Return'); assert session.decision['kind']=='ACK' and not session.error
                before=game.state_hash(); seed=game.s.seed
                bolt=next(k for k,e in enumerate(c.report) if isinstance(e,dict) and e['kind']=='bolt')
                start=sum(screen.report_hold(e) for e in c.report[:bolt]); flight=screen.report_hold(c.report[bolt])
                def shot(at): now[0]=at; return request(server,'/frame?t=0')[0]
                frames=[shot(start+flight*f) for f in (0.0,0.5,0.95)]+[shot(start+flight+0.01)]
                assert len(set(frames[:3]))==3, 'bolt does not move during its flight'
                assert screen.report_step(c)[0]!=bolt, 'bolt still flying after its flight time'
                tx,ty=c.report[bolt]['aim']; snapshot=c.report[bolt]['actors']
                assert any((x,y)==(tx,ty) and size for x,y,size in snapshot), 'target not standing during the flight'
                assert game.state_hash()==before and game.s.seed==seed
                witnesses.append(hashlib.sha256(frames[1]).hexdigest())
            else:
                key('m','m'); assert session.decision['kind']=='COMBAT_SPELL_AIM'
                b=combat.Battle(game); old=b.data['aim']
                keys=('Up','Prior','Right','Next','Down','End','Left','Home')
                for direction,symbol in enumerate(keys):
                    cell=old[0]+combat.DX[direction],old[1]+combat.DY[direction]
                    if b.terrain(b.tile(*cell),2)<=b.terrain(b.tile(*old),1):
                        key(symbol); assert b.data['aim']==cell; break
                else: raise AssertionError('fixture has no visible neighbouring cell')
                key('Escape'); assert session.decision['kind']=='TARGET'
                key('Escape'); assert session.decision['kind']=='COMBAT_CONFIRM'
                key('y','y'); assert not session.error
        finally:
            server.shutdown(); worker.join(timeout=5); server.server_close(); session.close()
    return witnesses[0]


def check_auto_browser(folder=None):
    from sm.titles.cok.ui import screen
    frames=[]
    for key in ('Alt-m','space'):
        session=ambush(folder)
        try:
            game=session.game; c=screen.Controller(session); b=combat.Battle(game)
            actor=b.data['actor']
            c.key('d','d'); assert session.decision['kind']=='COMBAT_DONE'
            c.key('a','a'); assert session.decision['kind']=='COMBAT_AUTO'
            before=game.state_hash(); pixels=b''.join(screen.render(c).rows)
            assert len(pixels)==64000 and game.state_hash()==before
            frames.append(hashlib.sha256(pixels).hexdigest())
            c.key(key,key if len(key)==1 else '')
            if session.error: raise session.error
            if key=='Alt-m': assert b.data['magic_enabled']
            else:
                assert b.record(actor)['initiative']==20
                assert all(not town.field(p,'auto_combat') for p in game.s.party if town.field(p,'npc')<128)
            assert game.trace[-1][1]=='COMBAT_AUTO'
            audit(game)
        finally: session.close()
    assert frames[0]==frames[1]
    return frames[0]


def check_attack_ally(folder=None):
    from sm.titles.cok.ui import screen
    frames=[]
    for answer in ('No','Yes'):
        session=ambush(folder)
        try:
            game=session.game; b=combat.Battle(game); c=screen.Controller(session); actor=b.data['actor']
            direction,target=next((d,b.probe(actor,d)[0]) for d in range(8) if 0<=b.probe(actor,d)[0]<len(game.s.party))
            position=b.position(actor); seed=game.s.seed
            c.key('m','m'); c.key(('Up','Prior','Right','Next','Down','End','Left','Home')[direction])
            assert session.decision['kind']=='COMBAT_CONFIRM'
            assert session.decision['info']['prompt']=='Attack Ally: ' and session.decision['options']==['Yes','No']
            before=game.state_hash(); frame=b''.join(screen.render(c).rows)
            assert len(frame)==64000 and game.state_hash()==before
            frames.append(hashlib.sha256(frame).hexdigest()); count=len(game.combat_log)
            c.key(answer[0].lower(),answer[0].lower())
            if session.error: raise session.error
            assert b.position(actor)==position and b.record(actor)['facing']==direction
            if answer=='No':
                assert session.decision['kind']=='COMBAT_MOVE' and game.state_hash()==before and game.s.seed==seed
                assert len(game.combat_log)==count and not game.s.r1[0x333]
            else:
                assert game.s.r1[0x333]==game.s.g['cok.ally_attacked']==1
                assert any(e['event']=='attack' and e['actor']==actor and e['target']==target for e in game.combat_log[count:])
                assert not b.record(actor)['initiative']
            audit(game)
        finally: session.close()
    assert frames[0]==frames[1]
    game,b=spell_fixture(folder)
    for i,npc,status in ((1,128,0),(2,0xB3,0),(3,129,4)):
        town.put(b.chars[i],'npc',npc); town.put(b.chars[i],'status',status); b.record(i)['target']=6
    assert b.confirm_ally(4,0)
    assert town.field(b.chars[1],'side')==1 and b.record(1)['target']==-1
    assert all(town.field(b.chars[i],'side')==0 and b.record(i)['target']==6 for i in (2,3))
    return frames[0]


def check_missile(folder=None):
    session = ambush(folder)
    try:
        game,b = session.game,combat.Battle(session.game)
        from sm.titles.cok.records import Item, split_records
        stock = [bytearray(bytes(r)) for r in split_records(game.assets.records('ITEM1')[16],Item)]
        bow = next(item for item in stock if b.base(item)[0] == 0 and b.base(item)[14]&1 and b.base(item)[12]>1)
        ammo = next(item for item in stock if item[combat.I['type']] == 30)
        c = b.chars[4]
        c.items = [bow,ammo]; bow[combat.I['readied']] = ammo[combat.I['readied']] = 1; ammo[combat.I['quantity']] = 3
        rules.recalc_stats(c)
        b.data['tiles'][:] = bytes([23])*1250
        b.record(4).update(x=20,y=10,phase=0,initiative=1)
        b.record(6).update(x=24,y=10)
        town.put(c,'attacks_left',1); town.put(c,'attacks_left',0,1)
        assert b.ranged(4) and b.ammo(4)[1] is ammo and 6 in b.attack_targets(4)
        b.strike(4,6,missile=ammo)
        assert ammo[combat.I['quantity']] == 2 and ammo in c.items and not b.record(4)['initiative']
        events = [e for e in game.combat_log if e['event'] == 'attack']
        assert len(events) == 1 and events[0]['actor'] == 4 and events[0]['target'] == 6
    finally: session.close()


def spell_fixture(folder=None):
    session=ambush(folder); game=session.game; session.close(); b=combat.Battle(game)
    b.data['tiles'][:]=bytes([23])*1250
    for i in range(len(b.chars)): b.record(i).update(x=5+i,y=5)
    for i,cell in enumerate(((20,10),(21,10),(20,11),(21,11)),6): b.record(i).update(x=cell[0],y=cell[1])
    b.record(4).update(x=18,y=10); b.data['actor']=4
    game.player=lambda kind,options,*args,**info: next((k for k,v in enumerate(options) if '#6' in str(v)),0) if kind=='TARGET' else 0
    return game,b


def check_spells(folder=None):
    game,b=spell_fixture(folder); c=b.chars[4]; initial=game.s.seed
    held=sum(v==15 for v in c.b[magic.F['memorized']:magic.F['memorized']+58])
    assert b.cast(4,15)
    assert town.field(b.chars[6],'hp')==4
    assert sum(v==15 for v in c.b[magic.F['memorized']:magic.F['memorized']+58])==held-1
    spell_dice=[e for e in game.combat_log if e['event']=='dice' and e['before']==initial]
    assert spell_dice[0]['faces']==(4,) and spell_dice[0]['sides']==4
    missile_hash=audit(game)
    before=len(game.combat_log); b.cast(4,21)
    dice=[e for e in game.combat_log[before:] if e['event']=='dice']
    assert [e['sides'] for e in dice]==[4]*4
    assert b.data['roll']['effect']==53 and b.data['roll']['damage']==5
    before=len(game.combat_log); b.cast(4,65,using_item=True)
    dice=[e for e in game.combat_log[before:] if e['event']=='dice']
    assert [e['sides'] for e in dice[:3]]==[4,4,100]
    audit(game)

    game,b=spell_fixture(folder); before=len(game.combat_log)
    b.cast(4,21)
    dice=[e for e in game.combat_log[before:] if e['event']=='dice']
    assert [e['sides'] for e in dice]==[4]*4+[100]*4
    assert [e['result'] for e in dice]==[4,4,2,3,94,70,31,93]
    budget=sum(e['result'] for e in dice[:4])
    asleep=[i for i in range(6,10) if combat.has(b.chars[i],53)]
    order=b.area_targets(20,10,1)
    assert asleep==[6,7,9] and budget==13,(budget,asleep,order)
    for i in asleep:
        node=effects.has_effect(b.chars[i],53)
        assert node[1]|node[2]<<8 == magic.duration(combat.EffectGame(b,'test',4),b.chars[4],magic.spell(21))
        b.record(i)['initiative']=5; b.trigger(7,i); assert b.record(i)['initiative']==0
    sleep_hash=audit(game)

    game,b=spell_fixture(folder)
    for target in b.chars[6:]: town.put(target,'magic_resistance',0); town.put(target,'highest_level',3)
    b.cast(4,21)
    assert [i for i in range(6,10) if combat.has(b.chars[i],53)]==[6,7,8]
    audit(game)

    game,b=spell_fixture(folder); c=b.chars[4]; town.put(c,'hp',1)
    game.player=lambda kind,options,*args,**info: next((k for k,v in enumerate(options) if '#4' in str(v)),0) if kind=='TARGET' else 0
    b.cast(4,3)
    healed=[e for e in game.combat_log if e['event']=='heal'][-1]
    assert healed['target']==4 and healed['amount']==8 and town.field(c,'hp')==min(town.field(c,'hp_max'),9)
    b.cast(4,1); assert combat.has(c,1)
    node=effects.has_effect(c,1); assert node[1:3]==bytearray((6,0))
    effects.age_effects(combat.EffectGame(b,'test expiry',4),c,6); assert not combat.has(c,1)
    cure_hash=audit(game)

    game,b=spell_fixture(folder); c=b.chars[4]; cursor=b.data['cursor']
    assert b.begin_cast(4,1) and b.record(4)['casting']==1 and b.record(4)['initiative']==5
    assert b.data['cursor']==cursor-1 and b.data['order'].index(4)>cursor
    count=sum(v==1 for v in c.b[magic.F['memorized']:magic.F['memorized']+58])
    b.damage(4,1,b.context(b.chars[6]))
    assert not b.record(4)['initiative'] and not b.record(4)['casting'] and not b.record(4)['cast_ok']
    assert sum(v==1 for v in c.b[magic.F['memorized']:magic.F['memorized']+58])==count-1
    assert game.combat_log[-2]['event']=='spell interrupted'
    audit(game)

    game,b=spell_fixture(folder)
    b.cast(4,34)
    assert len(b.data['clouds'])==1 and all(b.tile(x,y)==30 for x,y in ((20,10),(21,10),(20,11),(21,11)))
    assert [i for i in range(6,10) if combat.has(b.chars[i],31)]==[7]
    assert [i for i in range(6,10) if combat.has(b.chars[i],30)]==[8]
    assert not b.record(7)['initiative'] and not b.record(8)['cast_ok'] and not b.record(8)['item_ok']
    level=magic.caster_level(game,b.chars[4],34)
    effects.age_effects(combat.EffectGame(b,'cloud expiry',4),b.chars[4],level)
    assert not b.data['clouds'] and b.tile(20,10)==23
    audit(game)

    game,b=spell_fixture(folder); picks=iter((6,7,8))
    def hold_player(kind, options, *args, **info):
        if kind=='TARGET':
            target=next(picks); return next(k for k,v in enumerate(options) if '#%d'%target in str(v))
        return 0
    game.player=hold_player; before=len(game.combat_log); b.cast(4,23)
    assert not any(combat.has(c,52) for c in b.chars[6:])
    assert len([e for e in game.combat_log[before:] if e['event']=='dice' and e['sides']==20])==3
    audit(game)
    return dict(missile=missile_hash,sleep=sleep_hash,cure=cure_hash,budget=budget,asleep=asleep)


def check_turning(folder=None):
    results=[]
    for level,deity in ((1,0),(1,2),(6,2)):
        game,b=spell_fixture(folder); c=b.chars[4]
        town.put(c,'levels',level,0); town.put(c,'former_levels',0,0); town.put(c,'deity',deity)
        for target in b.chars[6:]: town.put(target,'undead',1)
        b.turn_undead(4)
        events=[e for e in game.combat_log if e['event']=='turn undead']
        dice=[e for e in game.combat_log if e['event']=='dice'][-2:]
        assert [e['sides'] for e in dice]==[12,20]
        column=level+2*(deity==2); needed=combat.signed(b.t['turning'][column-1])
        expected=min(4,max(dice[0]['result'],6 if needed<0 else 0)) if dice[1]['result']>=abs(needed) else 0
        assert len(events)==expected and all(e['column']==column and e['destroyed']==(needed<=0) for e in events)
        assert not b.record(4)['initiative'] and b.record(4)['turns']==1
        results.append(dict(level=level,deity=deity,count=len(events),needed=needed,dice=audit(game)))
    game,b=spell_fixture(folder)
    for _ in range(2):
        original=b.chars[6]
        game.s.monsters.append(rules.character(bytes(original.b),[bytes(v) for v in original.items],[bytes(v) for v in original.effects]))
        b.data['actors'].append(dict(b.record(6),x=22,y=10+_))
    town.put(b.chars[4],'levels',6,0); town.put(b.chars[4],'deity',2)
    for c in b.chars[6:]: town.put(c,'undead',1)
    game.s.seed=0; game.combat_log=[]
    b.turn_undead(4)
    assert game.combat_log[0]['result']==1
    assert len([e for e in game.combat_log if e['event']=='turn undead' and e['destroyed']])==6
    audit(game)
    return results


def check_bandage(folder=None):
    game,b=spell_fixture(folder); before=game.s.seed
    for i in (0,1,2,5):
        town.put(b.chars[i],'status',5); town.put(b.chars[i],'hp',0)
        b.record(i)['overkill']=3
    town.put(b.chars[0],'side',1); b.record(1)['outsider']=1
    game.player=lambda kind,options,*args,**info: options.index('Done' if kind=='COMBAT_ACTION' else 'Bandage')
    b.manual(4)
    assert [town.field(b.chars[i],'status') for i in (0,1,2,5)]==[5,5,4,5]
    assert [b.record(i)['overkill'] for i in (0,1,2,5)]==[3,3,0,3]
    assert not b.record(4)['initiative'] and game.s.seed==before
    assert b.bandage(False) and town.field(b.chars[5],'status')==5
    assert b.bandage() and town.field(b.chars[5],'status')==4 and b.record(5)['overkill']==0
    assert not b.bandage(False) and not b.bandage()


def check_lightning(folder=None):
    for dungeon in (False,True):
        game,b=spell_fixture(folder); game.s.r0[0xE6]=int(dungeon)
        wall=next(k for k in range(1,66) if b.terrain(k)==255)
        b.put_tile(22,10,wall); b.data['aim']=(20,10)
        hits=[]; damage=b.spell_damage
        def record(target,context,reduction,saved):
            hits.append(b.index(target)); damage(target,context,reduction,saved)
        b.spell_damage=record
        b.lightning(combat.EffectGame(b,'lightning fixture',4),b.chars[4],magic.spell(51),1)
        assert hits==([6,7,7] if dungeon else [6,7]),hits
        segments=[(e['cell'],e['distance'],e['bounce']) for e in game.combat_log if e['event']=='lightning segment']
        if dungeon:
            assert segments==[((21,10),2,False),((22,10),4,True),((21,10),2,False)]
            assert b.data['aim']==(22,10)
        else: assert not any(e[2] for e in segments)
        assert not b.data['multi_target']; audit(game)


def check_acid_breath(folder=None):
    game,b=spell_fixture(folder); game.s.dataset=2
    game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
    combat.load_monsters(game,2,1,2); b.setup(); b.data['tiles'][:]=bytes([23])*1250
    b.data['actor']=6; b.record(6).update(x=10,y=10,initiative=5)
    for i,c in enumerate(game.s.party):
        b.record(i).update(x=14+i%3,y=9+i//3); town.put(c,'hp',200); c.effects=[]
    b.trigger(14,6); node=effects.has_effect(b.chars[6],90)
    event=next(e for e in game.combat_log if e['event']=='breath')
    assert event['kind']==90 and node[3]==2 and not b.record(6)['initiative']
    amount=town.field(b.chars[6],'hp_max')
    assert all(town.field(b.chars[j],'hp') in (200-amount,200-amount//2) for j in event['targets'])
    assert b.data['roll']['element']==0x30
    b.data['round']=1; node[3]=0; before=game.s.seed
    b.trigger(14,6); assert game.s.seed==before
    node[3]=2; b.record(6)['initiative']=5
    original=b.cone; b.cone=lambda *args:[6]
    b.trigger(14,6); b.cone=original
    assert node[3]==2 and b.record(6)['initiative']==5
    audit(game)

    game,b=spell_fixture(folder); b.record(4)['target']=6
    for flags,amount,expected in ((0,7,7),(32,7,10),(32,254,1)):
        town.put(b.chars[6],'creature_type',flags); x=b.context(b.chars[4],damage=amount)
        b.weapon_effect(b.chars[4],115,bytearray(9),False,x)
        assert x.damage==expected


def check_kapak(folder=None):
    game,b=spell_fixture(folder)
    game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
    combat.load_monsters(game,14,1,14); b.setup()
    b.data['actor']=6; b.record(6)['target']=4
    game.s.seed=0; game.combat_log=[]
    b.trigger(2,6,b.context(b.chars[6]))
    node=effects.has_effect(b.chars[4],52)
    assert node is not None and node[1:4]==bytearray((100,0,12))
    assert game.combat_log[0]['sides']==20 and game.combat_log[0]['result']==1
    b.record(4)['initiative']=5; b.trigger(7,4); assert not b.record(4)['initiative']
    effects.age_effects(combat.EffectGame(b,'paralysis expiry',4),b.chars[4],100)
    assert not combat.has(b.chars[4],52)
    cell=b.position(6); ground=b.tile(*cell)
    b.damage(6,town.field(b.chars[6],'hp')+10,b.context(b.chars[4]))
    assert b.tile(*cell)==29 and len(b.data['acid'])==1
    node=effects.has_effect(b.chars[6],80); length=node[1]|node[2]<<8
    assert 1<=length<=6 and node[4]==1
    b.record(4).update(x=cell[0],y=cell[1]); b.data['actor']=4
    for undead in (0,1):
        town.put(b.chars[4],'undead',undead); town.put(b.chars[4],'hp',50)
        b.terrain_effects(4)
        dice=[e for e in game.combat_log if e['event']=='dice'][-1]
        assert dice['reason']=='acid damage' and town.field(b.chars[4],'hp')==50-dice['result']
    effects.age_effects(combat.EffectGame(b,'acid expiry',6),b.chars[6],length)
    assert not b.data['acid'] and b.tile(*cell)==ground and not combat.has(b.chars[6],80)
    acid=audit(game)
    b.record(4).update(size=0); town.put(b.chars[4],'status',6); b.put_tile(*cell,31)
    b.acid_pool(6)
    assert b.data['acid'][0]['ground'] is None and b.tile(*cell)==29
    b.clear_acid(6,0)
    assert b.tile(*cell)==31 and not b.data['acid']
    b.acid_pool(6); b.record(4)['x']+=1
    try: b.clear_acid(6,0)
    except town.BindingRequired as error: assert 'unset native neighbour index' in str(error)
    else: raise AssertionError('unknown ground was invented after moving the body')
    results=[]
    for seed in (0,2):
        game,b=spell_fixture(folder); actor=4; b.data['actor']=actor
        speed=town.field(b.chars[6],'move'); town.put(b.chars[actor],'move',speed)
        b.record(actor).update(x=49,y=12,initiative=5,movement=24)
        game.s.seed=seed; game.combat_log=[]; decisions=[]
        def player(kind,options,*args,**info):
            decisions.append(kind)
            return options.index('Move') if kind=='COMBAT_ACTION' else 2 if kind=='COMBAT_MOVE' else 0
        game.player=player; b.manual(actor)
        event=next(e for e in game.combat_log if e['event']=='flee')
        assert decisions==['COMBAT_ACTION','COMBAT_MOVE','COMBAT_CONFIRM']
        assert event['escaped']==(seed==0) and not b.record(actor)['initiative']
        assert (town.field(b.chars[actor],'status')==3)==event['escaped']
        results.append(audit(game))
    return acid,tuple(results)


def check_throtl_rules(folder=None):
    from sm.titles.cok import inventory
    game,b=spell_fixture(folder)
    raw=game.assets.records('ITEM1')[37]
    wand=next(bytearray(raw[k:k+63]) for k in range(0,len(raw),63) if raw[k+combat.I['type']]==52)
    assert wand[combat.I['powers']]==8 and wand[combat.I['powers']+1]==87
    c=b.chars[4]; c.items.append(wand); wand[combat.I['readied']]=1
    for target in b.chars[6:]:
        target.effects=[]; town.put(target,'magic_resistance',0); town.put(target,'hp',100)
    before=tuple(town.field(c,'memorized',j) for j in range(58)); start=len(game.combat_log)
    inventory.use_item(combat.EffectGame(b,'Ice Storm wand',4),c,wand)
    dice=[e for e in game.combat_log[start:] if e['event']=='dice']
    assert len(dice)==3 and all(e['sides']==10 for e in dice)
    amount=sum(e['result'] for e in dice)
    assert all(town.field(target,'hp')==100-amount for target in b.chars[6:])
    assert wand[combat.I['powers']]==7 and not b.record(4)['initiative']
    assert before==tuple(town.field(c,'memorized',j) for j in range(58))
    storm=audit(game)

    game,b=spell_fixture(folder); game.s.r0[0xE6]=1
    b.record(9).update(x=23,y=10); b.put_tile(22,10,1)
    assert 9 not in b.area_targets(20,10,3)
    b.put_tile(22,10,23)
    assert 9 in b.area_targets(20,10,3) and 9 not in b.area_targets(20,10,2)
    for target in b.chars[6:]:
        target.effects=[]; town.put(target,'magic_resistance',0); town.put(target,'hp',100)
    assert b.cast(4,47,using_item=True)
    assert town.field(b.chars[9],'hp')<100; audit(game)

    game,b=spell_fixture(folder); actor=6; target=4
    b.data['actor']=actor; b.record(actor)['target']=target
    game.s.seed=0; game.combat_log=[]
    b.weapon_effect(b.chars[actor],65,bytearray(9),False,b.context(b.chars[actor]))
    assert town.field(b.chars[target],'status')==6 and combat.has(b.chars[target],55)
    assert game.combat_log[0]['sides']==20 and game.combat_log[0]['result']==1
    poison=audit(game)
    game,b=spell_fixture(folder); b.data['actor']=6; b.record(6)['target']=4
    before=game.s.seed; assert town.field(b.chars[4],'race')<=1
    b.weapon_effect(b.chars[6],88,bytearray(9),False,b.context(b.chars[6]))
    assert game.s.seed==before and not combat.has(b.chars[4],52)
    b.record(6)['target']=0; game.s.seed=0; game.combat_log=[]
    b.weapon_effect(b.chars[6],88,bytearray(9),False,b.context(b.chars[6]))
    assert combat.has(b.chars[0],52); audit(game)

    game,b=spell_fixture(folder); game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
    combat.load_monsters(game,30,1,30); b.setup(); b.data['tiles'][:]=bytes([23])*1250
    b.data['actor']=6; b.record(6).update(x=10,y=10,initiative=5)
    for i,c in enumerate(game.s.party):
        b.record(i).update(x=14+i%3,y=9+i//3); town.put(c,'hp',100); c.effects=[]
    assert b.cone(6,(14,10),3,7) and 6 not in b.cone(6,(14,10),3,7)
    b.trigger(14,6); node=effects.has_effect(b.chars[6],83)
    assert node[3]==2 and not b.record(6)['initiative']
    breath=next(e for e in game.combat_log if e['event']=='breath')
    assert all(town.field(b.chars[j],'hp')<100 for j in breath['targets'])
    b.data['round']=1; node[3]=0; before=game.s.seed
    b.trigger(14,6); assert game.s.seed==before
    breath_hash=audit(game)

    game,b=spell_fixture(folder); game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
    combat.load_monsters(game,30,2,30); b.setup(); b.data['tiles'][:]=bytes([23])*1250
    positions=((27,8,1),(28,13,1),(26,13,1),(28,14,1),(29,14,1),(27,12,1),(25,7,0),(25,9,3))
    for i,(x,y,size) in enumerate(positions): b.record(i).update(x=x,y=y,size=size)
    assert b.cone(7,(28,14),3,7)==[5,1,3,4]
    return dict(storm=storm,poison=poison,breath=breath_hash)


def check_acid_resistance(folder=None):
    results=[]
    for actor in (0,4):
        game,b=spell_fixture(folder); target=b.chars[6]
        town.put(target,'magic_resistance',30); b.data['actor']=actor
        b.data['roll']=dict(effect=53,damage=0,element=8)
        b.put_tile(*b.position(6),29); before=len(game.combat_log)
        b.terrain_effects(6)
        dice=[e for e in game.combat_log[before:] if e['event']=='dice']
        assert [e['sides'] for e in dice][:2]==[6,100],dice
        results.append((actor,audit(game)))
    return results


BREADTH = (
    (2, 4, 0, 'explodes.'),
    (2, 6, 0, 'emits an evil stench'),
    (2, 10, 0, 'breathes poison'),
    (2, 44, 0, 'cast 55'),
    (3, 0, 0, 'cast 82'),
    (3, 3, 0, 'Breathes!'),
    (3, 22, 0, 'is terrified|is afraid'),
    (3, 43, 0, 'cast 70'),
    (3, 47, 0, 'cast 82'),
    (3, 18, 0, 'cast 82|Fires An Energy Bolt!'),
    (3, 24, 0, 'throws a fireball|reflects the spell'),
    (2, 28, 0, 'misses'),
)


def breadth_fight(folder, dataset, ident, seed):
    session=ambush(folder); game=session.game; session.close()
    seen=[]
    def player(kind, options, *args, **info):
        if kind=='COMBAT_CONFIRM': return options.index('No') if 'No' in options else 0
        if kind=='COMBAT_ACTION': return options.index('Auto' if 'Auto' in options else 'Done')
        if kind=='COMBAT_DONE': return options.index('Auto')
        return 0
    game.player=player; game.s.dataset=dataset; game.s.seed=seed*7919+1
    game.s.monsters=[]; game.s.g['cok.monster_icons']=[]; game.combat_log=[]
    combat.load_monsters(game,ident,3,1)
    for c in game.s.party: town.put(c,'auto_combat',1); town.put(c,'hp',150); town.put(c,'hp_max',150)
    b=combat.Battle(game); message=b.message
    b.message=lambda text,report=True:(seen.append(text),message(text,report))
    b.setup(); b.data.update(magic_enabled=True,limit=30)
    b.turns()
    seen+=['cast %d'%e['spell'] for e in game.combat_log if e['event']=='cast']
    return dict(rounds=b.data['round'],teams=b.teams(),state=game.state_hash(),dice=audit(game)),seen


def check_breadth(folder=None):
    results={}
    for dataset,ident,seed,proof in BREADTH:
        first,seen=breadth_fight(folder,dataset,ident,seed)
        again,_=breadth_fight(folder,dataset,ident,seed)
        assert first==again,(dataset,ident,'replay differs')
        assert any(any(p in text for p in proof.split('|')) for text in seen),(dataset,ident,proof)
        assert not all(first['teams']) or first['rounds']>=30,(dataset,ident,first)
        results['%d/%d'%(dataset,ident)]=first['rounds'],first['state']
    return results


def check_unplaced(folder=None):
    game,b=spell_fixture(folder)
    party=tuple(game.s.party); outsiders=len(game.s.monsters)
    b.wilderness=lambda:b.data.update(tiles=bytearray(1250))
    b.setup()
    assert tuple(game.s.party)==party and not game.s.monsters
    assert len(b.data['actors'])==len(party) and not any(r['size'] for r in b.data['actors'])
    assert len([e for e in game.combat_log if e['event']=='unplaced'])==outsiders
    assert all(j<len(party) for j,*_ in game.s.g.get('cok.monster_icons',[]))


def check_aurak_death(folder=None):
    from . import effects
    game,b=spell_fixture(folder); game.s.dataset=3
    game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
    combat.load_monsters(game,0,1,0); b.setup()
    b.data['tiles'][:]=bytes([23])*1250
    b.record(6).update(x=10,y=10); b.record(0).update(x=11,y=10)
    for i in range(1,6): b.record(i).update(x=20+i,y=15)
    c=b.chars[6]; b.data['actor']=0
    b.damage(6,town.field(c,'hp')+20,b.context(b.chars[0]))
    assert (town.field(c,'hp'),town.field(c,'status'),town.field(c,'active'))==(20,0,1)
    assert not combat.has(c,13) and all(combat.has(c,k) for k in (32,48,57,58))
    assert not any(town.field(c,'memorized',i) for i in range(58))
    assert list(effects.has_effect(c,58)[1:5])==[6,0,255,1]
    b.remove_effect(6,58)
    assert combat.has(c,59) and combat.has(c,60) and not any(combat.has(c,k) for k in (32,48,57))
    before=town.field(b.chars[0],'hp'); seen=_seen(b); b.remove_effect(6,60)
    assert town.field(c,'status')==8 and not town.field(c,'active')
    assert b.record(6)['size']==0 and b.tile(10,10)==23 and b.record(6)['initiative']==0
    assert seen[0]==combat.name(c)+' explodes!', seen
    assert town.field(b.chars[0],'hp')<before
    assert any(e['event']=='dice' and e['reason']=='Aurak explosion' and e['count']==3 for e in game.combat_log)
    audit(game)


def _fall(b, i, status=4):
    c=b.chars[i]; town.put(c,'status',status); town.put(c,'active',0); town.put(c,'hp',0); b.down(i)


def check_stand_up_ground(folder=None):
    game,b=spell_fixture(folder); b.put_tile(5,5,27)
    _fall(b,0)
    assert b.tile(5,5)==31 and b.record(0)['size']==0
    b.data['view']=(30,15)
    assert b.revive(0,5,'stands')
    assert b.tile(5,5)==27 and b.record(0)['size']==1 and town.field(b.chars[0],'active')==1
    assert b.data['downed']==[(0,0,0)] and b.data['downed_who']==[-1]
    assert b.data['view']==(2,2)
    _fall(b,0); b.record(1).update(x=5,y=5); _fall(b,1)
    assert b.data['downed'][1:]==[(5,5,27),(5,5,31)]
    assert b.revive(0,5,'stands') and b.tile(5,5)==31
    b.record(0).update(x=6,y=5)
    assert b.revive(1,5,'stands') and b.tile(5,5)==31
    assert all(j<0 for j in b.data['downed_who'])


def check_killed_while_down(folder=None):
    game,b=spell_fixture(folder); b.put_tile(5,5,27)
    _fall(b,0)
    b.kill(0,6,'is killed')
    assert b.data['downed']==[(5,5,27),(5,5,31)] and b.data['downed_who']==[0,0] and b.tile(5,5)==31
    _fall(b,6,6); assert len(b.data['downed'])==2 and b.tile(20,10)==23


def check_down_pulls_view(folder=None):
    game,b=spell_fixture(folder); b.data['view']=(0,0)
    _fall(b,6,6); assert b.data['view']==(17,7), b.data['view']
    b.data.update(view=(0,0),gfx=False); _fall(b,7,3); assert b.data['view']==(0,0)
    b.data['view']=(14,9); _fall(b,8,6); assert b.data['view']==(14,9)
    b.record(9).update(x=20,y=11,size=3); b.data['view']=(14,9)
    assert b.visible(9) and not b.visible(9,True)
    _fall(b,9,6); assert b.data['view']==(14,9)
    b.record(9).update(x=24,y=11,size=3); b.data['view']=(18,9)
    assert b.visible(9) and not b.visible(9,True)
    _fall(b,9,6); assert b.data['view']==(18,9)
    b.record(9).update(x=17,y=11,size=3); b.data['view']=(18,9)
    assert b.visible(9) and not b.visible(9,True)
    _fall(b,9,6); assert b.data['view']==(14,9)


def check_view_rule(folder=None):
    game,b=spell_fixture(folder)
    b.data['view']=(0,0); b.turn_view(6); assert (b.data['view'],b.data['gfx'])==((0,0),False)
    b.data['view']=(10,0); b.turn_view(0); assert (b.data['view'],b.data['gfx'])==((2,0),True)
    b.data.update(view=(0,0),gfx=False); b.record(6)['movement']=24
    assert b.move(6,6) and b.position(6)==(19,10) and b.data['view']==(0,0)
    b.face(6,2); _fall(b,7,3); assert b.data['view']==(0,0)
    town.put(b.chars[6],'auto_combat',1); b.data.update(view=(13,7),gfx=True); b.record(6)['movement']=24
    assert b.move(6,2) and b.position(6)==(20,10) and b.data['view']==(16,7), b.data['view']
    b.data['view']=(0,0); b.face(6,6); assert b.data['view']==(17,7) and b.record(6)['facing']==6
    b.data['view']=(0,0); _fall(b,8,3); assert b.data['view']==(17,8)
    b.data.update(view=(30,0),gfx=False); b.record(6)['flanks']=0
    b.attack(4,6)
    assert b.data['gfx'] is True and b.data['view']==(15,7), b.data['view']
    assert b.record(6)['facing']==(b.direction(6,4)+4)%8
    b.data['view']=(0,0); b.scroll(21,10,2); assert b.data['view']==(18,7)


def check_resistance_wrap(folder=None):
    from types import SimpleNamespace
    game,b=spell_fixture(folder); c=b.chars[6]; town.put(c,'magic_resistance',10)
    roll=SimpleNamespace(effect=47,damage=0,element=0,spell=47,call=lambda name,*a:14)
    effects.check_spell_resistance(game,c,roll)
    assert roll.effect==0


def check_regeneration_down(folder=None):
    game,b=spell_fixture(folder); c=b.chars[6]
    town.put(c,'status',4); town.put(c,'active',0); town.put(c,'hp',0)
    assert effects.restore_hp(game,c,1,True)
    assert (town.field(c,'status'),town.field(c,'active'),town.field(c,'hp'))==(4,0,1)
    assert effects.restore_hp(game,c,1)
    assert (town.field(c,'status'),town.field(c,'active'))==(0,1)


def large_fixture(folder, size):
    game,b=spell_fixture(folder); b.data['tiles'][:]=bytes([23])*1250
    for j in (7,8,9): town.put(b.chars[j],'active',0); town.put(b.chars[j],'status',6); b.record(j)['size']=0
    m=b.chars[6]; town.put(m,'hp',200); town.put(m,'hp_max',200); m.effects=[]
    b.record(6).update(x=20,y=10,size=size)
    for i in range(6): b.record(i).update(x=40+i,y=20)
    return game,b


def no_overlap(b):
    seen={}
    for i in range(len(b.chars)):
        for cell in b.cells(i):
            assert cell not in seen, ('two figures on one square',cell,seen.get(cell),i)
            seen[cell]=i


def check_large_footprints(folder=None):
    for size in (2,3,4):
        game,b=large_fixture(folder,size); body=set(b.cells(6))
        assert len(body)==(2 if size<4 else 4)
        for cx,cy in sorted(body):
            for d in range(8):
                spot=(cx-combat.DX[d],cy-combat.DY[d])
                if spot in body: continue
                town.put(b.chars[6],'hp',200); game.s.seed=1; b.record(0).update(x=spot[0],y=spot[1],initiative=5,movement=24,attacked=0); b.reset_attacks(0)
                assert 6 in b.attack_targets(0), (size,spot)
                occupant,_=b.probe(0,d); assert occupant==6, (size,spot,d)
                before=len(game.combat_log); b.move_attack(0,6)
                assert any(e['event']=='attack' and e['actor']==0 and e['target']==6 for e in game.combat_log[before:]), (size,spot)
                assert b.position(0)==spot and not b.move(0,d); no_overlap(b)
            b.record(0).update(x=40,y=20)
            for spot in ((cx-4,cy),(cx,cy+4) if size!=2 else (cx+4,cy)):
                if spot in body: continue
                town.put(b.chars[6],'hp',200); game.s.seed=1; b.record(5).update(x=spot[0],y=spot[1],initiative=5,attacked=0); b.reset_attacks(5)
                assert b.ranged(5) and 6 in b.attack_targets(5), (size,spot)
                before=len(game.combat_log); b.strike(5,6,missile=b.ammo(5)[1])
                assert any(e['event']=='attack' and e['actor']==5 and e['target']==6 for e in game.combat_log[before:]), (size,spot)
                b.record(5).update(x=45,y=20)
        for x in range(16,25):
            for y in range(6,15):
                for radius in (0,1,2,3):
                    hit=b.area_targets(x,y,radius)
                    assert hit.count(6)<=1
                    if any(max(abs(x-a),abs(y-c))<=radius//2 for a,c in body): assert 6 in hit, (size,x,y,radius)
        b.record(0).update(x=14,y=10)
        for aim in sorted(body):
            for width in (1,3):
                assert b.cone(0,aim,width,8).count(6)==1, (size,aim,width)
        b.data['aim']=(min(body)[0]-1,min(body)[1]); b.record(4).update(x=12,y=10)
        before=len(game.combat_log); b.cloud(b.chars[4],5)
        assert sum(e['event']=='dice' and e['reason']=='saving throw' and e['actor']==6 for e in game.combat_log[before:])==1, size
        no_overlap(b)


def check_no_overlap_fights(folder=None):
    original=combat.Battle.event; checked=[0]
    def event(self, *args, **details):
        original(self,*args,**details); no_overlap(self); checked[0]+=1
    combat.Battle.event=event
    try:
        for dataset,ident in ((1,16),(2,2),(2,56),(3,3)):
            breadth_fight(folder,dataset,ident,1)
    finally: combat.Battle.event=original
    assert checked[0]>100, checked
    game,b=large_fixture(folder,4)
    b.record(6).update(initiative=5); b.flee(6)
    if town.field(b.chars[6],'status')==3: assert b.cells(6)==[]
    no_overlap(b)
    game,b=large_fixture(folder,4)
    for j in (7,8,9): town.put(b.chars[j],'status',9); town.put(b.chars[j],'dimensions',132)
    for i in range(6): b.record(i).update(x=19+i%3,y=8+i//3*4)
    town.put(b.chars[6],'hp',10); b.gate_in(6); no_overlap(b)
    assert all(b.cells(j) for j in range(len(b.chars)) if town.field(b.chars[j],'active')), 'a figure in play with no squares'
    game,b=large_fixture(folder,4)
    for j in (7,8,9): town.put(b.chars[j],'status',9); town.put(b.chars[j],'dimensions',132)
    b.record(0).update(x=30,y=10)
    town.put(b.chars[6],'hp',10); b.gate_in(6); no_overlap(b)
    assert sum(town.field(b.chars[j],'active') for j in (7,8,9))>=2
    assert all(b.cells(j) for j in range(len(b.chars)) if town.field(b.chars[j],'active'))


def check_ai_balks(folder=None):
    for tile in (30,29):
        game,b=spell_fixture(folder); game.s.seed=3
        for j in (7,8,9): town.put(b.chars[j],'active',0); town.put(b.chars[j],'status',6); b.record(j)['size']=0
        for i in range(6): b.record(i).update(x=40+i,y=20)
        b.record(0).update(x=24,y=10); b.record(6).update(x=20,y=10,target=0,movement=24,initiative=5,stance=1,turned=0)
        b.chars[6].effects=[]; town.put(b.chars[6],'saves',21,0); town.put(b.chars[6],'highest_level',2)
        bad={(21,9),(21,10),(21,11)}
        for cell in bad: b.put_tile(*cell,tile)
        b.data.update(last_direction=8,stuck=0)
        b.ai_step(6)
        assert b.position(6) not in bad, (tile,b.position(6))


def check_ai_touch_range(folder=None):
    game,b=spell_fixture(folder)
    for j in (7,8,9): town.put(b.chars[j],'active',0); b.record(j)['size']=0
    for i in range(6): b.record(i).update(x=40+i,y=20)
    b.record(6).update(x=20,y=10); b.record(0).update(x=21,y=10)
    assert b.ai_accept_spell(6,68,0)
    b.record(0).update(x=25,y=10)
    assert not b.ai_accept_spell(6,68,0)


def check_ai_locked_anchor(folder=None):
    game,b=large_fixture(folder,4)
    c=b.chars[0]; town.put(c,'auto_combat',1)
    b.record(0).update(x=22,y=12,target=6,initiative=5,movement=0,attacked=0,turned=0); b.reset_attacks(0)
    before=len(game.combat_log); b.ai(0)
    dice=[e['reason'] for e in game.combat_log[before:] if e['event']=='dice']
    assert 'AI attack target' in dice, dice
    assert any(e['event']=='attack' and e['actor']==0 and e['target']==6 for e in game.combat_log[before:])


def check_undead_count(folder=None):
    session=ambush(folder); game=session.game; session.close()
    game.s.dataset=2; game.s.monsters=[]; game.s.g['cok.monster_icons']=[]; game.s.g['cok.undead_count']=0
    combat.load_monsters(game,31,5,1)
    assert sum(town.field(c,'undead')>0 for c in game.s.monsters)==5
    b=combat.Battle(game); b.setup()
    cleric=next(i for i,c in enumerate(game.s.party) if town.field(c,'levels',0))
    b.record(cleric).update(turns=1,initiative=5); town.put(game.s.party[cleric],'auto_combat',1)
    game.player=lambda kind,options,*a,**k: 0
    before=len(game.combat_log); b.ai(cleric)
    assert not any(e['event']=='turn undead' for e in game.combat_log[before:])
    combat.load_monsters(game,31,1,1); assert game.s.g['cok.undead_count']==2


def check_ai_repeat_pick(folder=None):
    from sm.titles.cok import magic
    game,b=spell_fixture(folder)
    for j in (7,8,9): town.put(b.chars[j],'active',0); b.record(j)['size']=0
    for i in range(1,6): town.put(b.chars[i],'active',0); b.record(i)['size']=0
    b.record(6).update(x=20,y=10); b.record(0).update(x=22,y=10)
    seen=[]; message=b.message; b.message=lambda text,report=True:(seen.append(text),message(text,report))
    before=len(game.combat_log)
    picked=b.spell_targets(6,magic.spell(23),ai=True)
    rolls=[e for e in game.combat_log[before:] if e['event']=='dice' and e['reason']=='acquire target']
    assert picked==[0] and len(rolls)==3 and not seen, (picked,len(rolls),seen)


def check_sweep_message(folder=None):
    game,b=spell_fixture(folder)
    for i in range(1,6): b.record(i).update(x=40+i,y=20)
    for k,j in enumerate((6,7,8,9)):
        town.put(b.chars[j],'highest_level',0); town.put(b.chars[j],'hp',100); b.record(j).update(x=19+k,y=9)
    b.record(0).update(x=20,y=10,sweep=4,attacked=0,initiative=5); b.reset_attacks(0); town.put(b.chars[0],'attacks_left',1)
    seen=[]; message=b.message; b.message=lambda text,report=True:(seen.append(text),message(text,report))
    before=len(game.combat_log); b.strike(0,6)
    assert any(text.endswith(' sweeps') for text in seen), seen
    assert len({e['target'] for e in game.combat_log[before:] if e['event']=='attack' and e['actor']==0})>=3


def check_flee_messages(folder=None):
    game,b=spell_fixture(folder); game.player=lambda kind,options,*a,**k: 0
    seen=[]; message=b.message; b.message=lambda text,report=True:(seen.append(text),message(text,report))
    b.record(6).update(turned=1,initiative=5,movement=24); b.ai(6)
    assert any(text.endswith('is forced to flee') for text in seen), seen
    game,b=spell_fixture(folder); game.player=lambda kind,options,*a,**k: 0
    seen=[]; message=b.message; b.message=lambda text,report=True:(seen.append(text),message(text,report))
    m=b.chars[7]; town.put(m,'npc',0x80|1); town.put(m,'hp',1); town.put(m,'move',96)
    b.data['hostile_hp']=0; b.record(7).update(initiative=5,movement=200,turned=0); b.ai(7)
    assert any(text.endswith('flees in panic') for text in seen), seen


def check_displacement(folder=None):
    from . import effects
    game,b=spell_fixture(folder); c=b.chars[0]
    effects.add_effect(c,89,0,255,False)
    node=effects.has_effect(c,89); b.data['round']=0
    b.trigger(8,0,b.context(c,attack=0)); assert node[3]==15
    first=b.trigger(16,0,b.context(b.chars[6],attack=100))
    second=b.trigger(16,0,b.context(b.chars[6],attack=100))
    assert first.attack==-1 and second.attack==100 and node[3]==31
    b.data['round']=1; b.trigger(8,0,b.context(c,attack=0))
    assert node[3]==31


def _after_fight(folder, setup, fought=True):
    game,b=spell_fixture(folder); texts=[]; s=game.s
    def player(kind,options,*args,**info):
        if info.get('message'): texts.append(info['message'])
        return options.index('Exit') if 'Exit' in options else options.index('No') if 'No' in options else 0
    game.player=player; setup(game,b)
    if fought: b.postcombat()
    else: s.monsters=[]; combat.Battle(game).treasure()
    return game,texts


def check_after_fight(folder=None):
    def down(chars):
        for c in chars: town.put(c,'status',4); town.put(c,'active',0); town.put(c,'hp',0)
    def killed(game,b): down(game.s.monsters)
    def lost(game,b): game.s.r1[0x2E6]=1; down(game.s.party)
    game,texts=_after_fight(folder,lost)
    assert game.s.r1[0x2C7]==0x80 and texts==['You have lost the fight. Each character receives 0 experience points.'], (game.s.r1[0x2C7],texts)
    assert game.s.party and all(town.field(c,'status')==0 and town.field(c,'hp')==1 for c in game.s.party) and not game.s.party_dead
    assert [e for e in game.combat_log if e['event']=='result'][-1]['code']==0x80
    game,texts=_after_fight(folder,killed)
    share=[e for e in game.combat_log if e['event']=='result'][-1]['experience']
    assert share and texts==['The party has won. Each character receives %d experience points.'%share], texts
    def fled(game,b):
        for c in game.s.party: town.put(c,'status',3); town.put(c,'active',0)
    game,texts=_after_fight(folder,fled)
    assert game.s.r1[0x2C7]==0x81 and texts==['The party has fled. Each character receives 0 experience points.'], texts
    game,texts=_after_fight(folder,lambda game,b:None,fought=False)
    assert len(texts)==1 and texts[0].startswith('The party has found Treasure! Each character receives ') and texts[0].endswith(' experience points.'), texts
    def npcs(money):
        def setup(game,b):
            killed(game,b); a,c=game.s.party[0],game.s.party[1]
            for who,gender in ((a,0),(c,1)): town.put(who,'npc',128); town.put(who,'modified',2); town.put(who,'gender',gender)
            for m in game.s.monsters:
                for k in range(7): town.put(m,'money',0,k*2,width=2)
            game.s.treasure_money=[0,0,0,money,0,0,0]
        return setup
    game,texts=_after_fight(folder,npcs(80))
    names=[combat.name(c) for c in game.s.party[:2]]
    assert texts[0]==names[0]+' takes and hides his share.'+chr(10)+names[1]+' takes and hides her share.' and len(texts)==2, texts
    assert game.s.treasure_money[3]==80-4*(80//(len(game.s.party)+2)), game.s.treasure_money
    game,texts=_after_fight(folder,npcs(0))
    assert len(texts)==1 and texts[0].startswith('The party has won.'), texts


def _loot(folder, setup, script=()):
    game,b=spell_fixture(folder); s=game.s; asked=[]; script=list(script)
    def player(kind,options,*args,**info):
        asked.append((kind,tuple(options),info))
        if script:
            answer=script.pop(0); return options.index(answer) if isinstance(answer,str) else answer
        return options.index('Exit') if 'Exit' in options else options.index('No') if 'No' in options else 0
    s.sel=0; s.mode=6; s.treasure_money=[0]*7; s.treasure_items=[]; setup(game,b); game.player=player; b.loot()
    return game,asked


def _hoard(game, count, **fields):
    raw=next(c for c in game.s.party if c.items).items[0]; made=[]
    for n in range(count):
        item=bytearray(raw); item[combat.I['readied']]=0; item[combat.I['weight']:combat.I['weight']+2]=bytes(2)
        for key,value in fields.items(): item[combat.I[key]]=value
        made.append(item)
    game.s.treasure_items=made
    return made


def check_loot_detect(folder=None):
    from sm.titles.cok import camp, magic, shop
    def mage(spell_id):
        def setup(game,b):
            _hoard(game,1,bonus=1); c=game.s.party[0]; base=camp.F['memorized']
            c.b[base:base+camp.MEMORY_SLOTS]=bytes(camp.MEMORY_SLOTS); c.b[base+3]=spell_id
        return setup
    game,asked=_loot(folder,mage(11),['Detect'])
    main=[options for kind,options,info in asked if kind=='COMBAT_LOOT' and 'View' in options]
    assert main[0][:5]==('View','Take','Pool','Detect','Exit'), main[0]
    assert 'Detect' not in main[1] and not any(camp.memory(game.s.party[0])), main
    assert shop.item_name(game,game.s.treasure_items[0]).startswith('* ')
    said=[info.get('prompt','') for kind,options,info in asked if kind=='ACK']
    assert not any(' casts ' in text for text in said), said
    game,asked=_loot(folder,mage(11|0x80)); assert 'Detect' not in asked[0][1], asked[0]
    def out(game,b): mage(5)(game,b); town.put(game.s.party[0],'active',0)
    game,asked=_loot(folder,out); assert 'Detect' not in asked[0][1], asked[0]
    def coins(game,b): mage(103)(game,b); game.s.treasure_items=[]; game.s.treasure_money[4]=9
    game,asked=_loot(folder,coins); assert asked[0][1][:5]==('View','Take','Pool','Share','Exit'), asked[0]
    def cursed(game,b): mage(77)(game,b); effects.add_effect(game.s.party[0],74,0,0,False)
    roll=magic.dice; magic.dice=lambda s,count,sides: 1
    try: game,asked=_loot(folder,cursed,['Detect'])
    finally: magic.dice=roll
    said=[info.get('prompt','') for kind,options,info in asked if kind=='ACK']
    assert said==[combat.name(game.s.party[0])+' miscasts Detect Magic'] and 77 in camp.memory(game.s.party[0]), said
    assert not shop.item_name(game,game.s.treasure_items[0]).startswith('* ')
    return 'Detect'


def check_loot_take(folder=None):
    from sm.titles.cok import shop
    prompts=lambda asked: [(kind,info.get('prompt','')) for kind,options,info in asked]
    def coins(game,b): game.s.treasure_money[4]=9
    game,asked=_loot(folder,coins,['Take'])
    assert prompts(asked)[1]==('LIST','Select type of coin '), prompts(asked)
    game,asked=_loot(folder,lambda game,b:_hoard(game,2),['Take'])
    assert asked[1][0]=='COMBAT_LOOT' and asked[1][1][-1]=='Exit' and len(asked[1][1])==3, asked[1]
    def both(count):
        def setup(game,b): _hoard(game,count); game.s.treasure_money[4]=9
        return setup
    game,asked=_loot(folder,both(2),['Take','Items',0,'Exit','Exit'])
    assert [options[:3] for kind,options,info in asked if info.get('prompt')=='Take: ']==[('Money','Items','Exit')]*2, prompts(asked)
    assert 'View' in asked[5][1] and len(game.s.treasure_items)==1 and len(asked)==7, prompts(asked)
    game,asked=_loot(folder,both(1),['Take','Items',0])
    assert 'View' in asked[3][1] and 'Share' in asked[3][1] and not game.s.treasure_items, prompts(asked)
    held=[]
    def counted(game,b): both(2)(game,b); held[:]=[len(c.items) for c in game.s.party]
    game,asked=_loot(folder,counted,['Take','char-down','Items',0])
    assert asked[1][1][3:]==('char-up','char-down') and [len(c.items) for c in game.s.party[:2]]==[held[0],held[1]+1], asked[1]
    def three(game,b):
        for n,item in enumerate(_hoard(game,3)): item[combat.I['quantity']]=n+2
    game,asked=_loot(folder,three,['Take',1,1])
    lists=[(options,info) for kind,options,info in asked if info.get('prompt')=='Items: ']
    assert [info['start'] for options,info in lists]==[0,1,0] and [len(options) for options,info in lists]==[4,3,2], lists
    assert lists[1][0][1]==lists[0][0][2] and lists[2][0][0]==lists[0][0][0], lists
    assert all(info['query']=='Items: ' and info['menu']=='Take' and info['window']=='1 1 38 22' for options,info in lists), lists
    def heavy(game,b):
        three(game,b); item=game.s.treasure_items[1]; item[combat.I['weight']:combat.I['weight']+2]=bytes([255,255]); item[combat.I['quantity']]=0
    game,asked=_loot(folder,heavy,['Take',1])
    lists=[(options,info) for kind,options,info in asked if info.get('prompt')=='Items: ']
    assert len(game.s.treasure_items)==3 and lists[1][1]['message']=='OverLoaded' and lists[1][1]['start']==1 and not lists[0][1]['message'], lists
    assert lists[1][0]==lists[0][0] and not getattr(game,'shop_note',''), lists
    def banked(game,b): heavy(game,b); b.data['bank']=[(0,game.s.treasure_items[1])]
    game,texts=_after_fight(folder,banked)
    assert [e['returned'] for e in game.combat_log if e['event']=='bank return']==[False] and not getattr(game,'shop_note','x'), texts
    game,asked=_loot(folder,coins,['Exit','Yes','Exit','No'])
    asks=[(options,info) for kind,options,info in asked if kind=='COMBAT_CONFIRM']
    assert len(asks)==2 and len(asked)==4 and asks[0][0][:2]==('Yes','No') and not asks[0][1].get('prompt'), asked
    assert asks[0][1]['offer']=='There is still treasure left.  Do you want to go back and claim your treasure?', asks[0]
    game,asked=_loot(folder,coins,['Exit','char-up','No'])
    assert game.s.sel==len(game.s.party)-1 and len(asked)==3, (game.s.sel,asked)
    game,asked=_loot(folder,coins,['char-down','char-down','char-first'])
    assert asked[0][1][-3:]==('char-up','char-down','char-first') and game.s.sel==0, asked[0]
    return 'Take'


def _seen(b):
    seen=[]; message=b.message; b.message=lambda text,report=True:(seen.append(text),message(text,report)); return seen


def _attack_fixture(folder, phase0=2, phase1=0):
    game,b=spell_fixture(folder)
    b.record(0).update(x=19,y=10,phase=1 if phase1 else 0); t=b.chars[6]
    town.put(t,'hp_max',255); town.put(t,'hp',250)
    town.put(b.chars[0],'attacks_left',phase0,0); town.put(b.chars[0],'attacks_left',phase1,1)
    return game,b


def _attack_dice(b, values):
    seq=iter(values); die=b.die
    b.die=lambda count,sides,reason,*a: next(seq) if reason=='attack' else die(count,sides,reason,*a)


def check_helpless_mid_sequence(folder=None):
    game,b=_attack_fixture(folder); calls=[0]
    def disabled(j): calls[0]+=1; return calls[0]>1
    b.disabled=disabled; _attack_dice(b,[2,2]); before=len(game.combat_log)
    b.attack(0,6)
    hits=[e['hit'] for e in game.combat_log[before:] if e['event']=='attack']
    assert hits==[True,True], hits


def check_miss_once(folder=None):
    game,b=_attack_fixture(folder); seen=_seen(b); _attack_dice(b,[1,1]); b.attack(0,6)
    assert sum(' misses ' in t for t in seen)==1, seen
    game,b=_attack_fixture(folder); seen=_seen(b); _attack_dice(b,[20,1]); b.attack(0,6)
    assert not any(' misses ' in t for t in seen), seen


def check_target_self(folder=None):
    game,b=spell_fixture(folder)
    def veto(kind,j,x=None):
        if x is not None: x.target_veto=True
        return x
    b.trigger=veto
    assert b.can_target(4,4) and not b.can_target(4,6)


def _turn_fixture(folder, level, deity, roll):
    game,b=spell_fixture(folder); c=b.chars[4]
    town.put(c,'levels',level,0); town.put(c,'former_levels',0,0); town.put(c,'deity',deity)
    for j in (7,8,9): town.put(b.chars[j],'active',0); b.record(j)['size']=0
    town.put(b.chars[6],'undead',1); die=b.die
    b.die=lambda count,sides,reason,*a: roll if reason=='turn undead' else 1 if reason=='turn count' else die(count,sides,reason,*a)
    return game,b,_seen(b)


def check_turn_destroyed_gone(folder=None):
    game,b,seen=_turn_fixture(folder,6,2,20); b.turn_undead(4)
    assert town.field(b.chars[6],'status')==8 and any(t.endswith(' Is destroyed') for t in seen), seen


def check_turn_nothing(folder=None):
    game,b,seen=_turn_fixture(folder,1,0,1); b.turn_undead(4)
    assert town.field(b.chars[6],'active') and 'Nothing Happens...' in seen, seen


def check_turned_strips(folder=None):
    from . import effects
    game,b,seen=_turn_fixture(folder,1,0,20); k=effects._hp_zero_ids(game)[0]
    effects.add_effect(b.chars[6],k,10,0,False); assert combat.has(b.chars[6],k)
    b.turn_undead(4)
    assert town.field(b.chars[6],'status')==3 and not combat.has(b.chars[6],k)


def check_ai_self_spell_keeps_target(folder=None):
    game,b=spell_fixture(folder); b.record(6)['target']=0
    assert b.spell_targets(6,magic.spell(6),ai=True)==[6] and b.record(6)['target']==0


def check_area15_locked(folder=None):
    game,b=spell_fixture(folder); b.record(6)['target']=0
    row=magic.spell(25)._replace(offensive=0)
    assert b.spell_targets(6,row,ai=True)==[0]


def check_already_been_targeted(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b); picks=iter((1,1,99))
    def player(kind,options,*a,**k):
        p=next(picks,99); return min(p,len(options)-1) if kind=='TARGET' else 0
    game.player=player; b.spell_targets(4,magic.spell(23))
    assert 'Already been targeted' in seen, seen


def check_fight_keys(folder=None):
    from sm.titles.cok import creation
    field=town.field
    game,b=spell_fixture(folder); seen=_seen(b); r=b.record(4); r['initiative']=5; asked=[]
    for c in b.chars: town.put(c,'auto_combat',1)
    picks=iter(('space','Alt-m','Alt-m','Done','Speed','Slower','Faster','Faster','Exit','Quit'))
    def player(kind,options,*a,**k):
        asked.append((kind,tuple(options),k.get('query'))); return options.index(next(picks))
    game.player=player; b.data['magic_enabled']=False; game.s.g[creation.DELAY]=4
    b.manual(4)
    assert [field(c,'auto_combat') for c in b.chars]==[int(field(c,'npc')>=128) for c in b.chars] and not field(b.chars[4],'auto_combat')
    assert [t for t in seen if t.startswith('Magic')]==['Magic On','Magic Off'] and not b.data['magic_enabled'], seen
    assert asked[0][1][-4:]==('space','Alt-m','Alt-q','Alt-a') and asked[0][1][-5]=='Done'
    assert asked[4][1][-3:]==('Auto','Speed','Exit') and asked[9][1]==asked[4][1]
    assert [(o,q) for _,o,q in asked[5:9]]==[(('Slower','Faster','Exit'),'GameSpeed (%d) :'%n) for n in (4,5,4,3)], asked[5:9]
    assert game.s.g[creation.DELAY]==3 and r['initiative']==0
    for delay,words in ((0,('Slower','Exit')),(9,('Faster','Exit'))):
        game.s.g[creation.DELAY]=delay; shown=[]
        game.player=lambda kind,options,*a,**k: (shown.append(tuple(options)),len(options)-1)[1]
        b.speed_menu(); assert shown==[words], shown
    for key in ('Alt-q','Alt-a'):
        game,b=spell_fixture(folder); r=b.record(4); r.update(initiative=5,target=0,movement=6); b.record(6)['target']=7
        for c in b.chars: town.put(c,'auto_combat',0)
        b.data['order']=[4,6]; b.data['cursor']=0
        game.player=lambda kind,options,*a,**k: options.index(key)
        b.manual(4)
        assert (r['initiative'],r['movement'],r['target'],b.data['cursor'])==(20,6,-1,-1), r
        assert b.record(6)['target']==-1 and all(field(c,'auto_combat') for c in b.chars)
    game,b=spell_fixture(folder); seen=_seen(b); r=b.record(4); r.update(initiative=5,movement=6)
    for c in b.chars[:6]: town.put(c,'auto_combat',1)
    game.player=lambda kind,options,*a,**k: options.index('Manual') if kind=='COMBAT_AUTO' else 0
    b.ai(4)
    assert (r['initiative'],r['movement'])==(20,6) and not any(field(c,'auto_combat') for c in b.chars[:6]), r
    game,b=spell_fixture(folder); seen=_seen(b); b.data['magic_enabled']=False; b.record(4)['initiative']=5
    answers=iter(('Magic',)); b.morale=lambda i: True
    game.player=lambda kind,options,*a,**k: options.index(next(answers,'Continue')) if kind=='COMBAT_AUTO' else 0
    b.ai(4)
    assert b.data['magic_enabled'] and 'Magic On' in seen, seen
    game,b=spell_fixture(folder); sent=[]
    game.player=lambda kind,options,*a,**k: (sent.append(k),len(options)-1)[1]
    b.begin_cast(4)
    offered=magic.castable(b.chars[4],True); levels=tuple(magic.spell(k).level for k,_ in offered)
    assert len(offered)>1 and sent[0]['start']==magic.list_start(levels)[0]==len(offered)-1 and tuple(sent[0]['levels'])==levels, sent


def check_begins_casting(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b); b.record(4)['initiative']=20
    b.data['order']=[4]; b.data['cursor']=0
    b.begin_cast(4,1)
    said=[t for t in seen if 'Casting' in t or 'casting' in t]
    assert said and said[0].endswith(' Begins Casting') and 'Bless' not in said[0], seen


def check_attacker_down_phase(folder=None):
    game,b=_attack_fixture(folder,1,2); _attack_dice(b,[20,20,20]); damage=b.damage
    def downed(j,amount,x): damage(j,amount,x); town.put(b.chars[0],'active',0)
    b.damage=downed; before=len(game.combat_log); b.attack(0,6)
    phases=[e['phase'] for e in game.combat_log[before:] if e['event']=='attack']
    assert phases==[1,0], phases


def check_faerie_fire_sizes(folder=None):
    game,b=spell_fixture(folder)
    for j in range(1,10):
        if j!=6: town.put(b.chars[j],'active',0); b.record(j)['size']=0
    town.put(b.chars[0],'dimensions',5); b.record(0).update(x=19,y=10); b.record(6).update(x=20,y=10)
    assert b.spell_targets(6,magic.spell(79),ai=True)==[0]


def check_helpless_byte(folder=None):
    game,b=_attack_fixture(folder); t=b.chars[6]; town.put(t,'hp',252)
    b.disabled=lambda j: j==6; b.attack(0,6)
    assert town.field(t,'hp')==251 and town.field(t,'active'), town.field(t,'hp')


def check_aim_flags(folder=None):
    game,b=spell_fixture(folder); offered={}; seen=[]
    def player(kind,options,*a,**k):
        offered.setdefault(k.get('spell'),[]).append(list(map(str,options)))
        if kind=='TARGET' and k.get('spell')==83: return options.index('Ground') if len(seen)<2 else len(options)-1
        if kind=='COMBAT_SPELL_AIM':
            seen.append((k['cursor'],list(options)))
            return options.index('Exit') if len(seen)>1 else 2
        return len(options)-1
    game.player=player; b.record(4).update(x=19,y=10)
    b.spell_targets(4,magic.spell(83)); b.spell_targets(4,magic.spell(25))
    assert any('#' in o for o in offered[83][0]) and 'Ground' in offered[83][0], offered[83]
    assert seen[1][0]==(20,10) and 'Target' not in seen[1][1], seen
    assert 'Ground' not in offered[25][0] and any('#' in o for o in offered[25][0]), offered[25]


def check_no_type66_rule(folder=None):
    game,b=_attack_fixture(folder); weapon=b.weapon
    def typed(i):
        w=weapon(i)
        if w is None: return w
        w=bytearray(w); w[combat.I['type']]=66; return bytes(w)
    b.weapon=typed; _attack_dice(b,[1,1]); before=len(game.combat_log); b.attack(0,6)
    assert sum(e['event']=='attack' for e in game.combat_log[before:])==2


def check_flee_texts(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b)
    for j in range(6,10): town.put(b.chars[j],'active',0)
    b.flee(0); assert seen[-1].endswith(' Got Away'), seen
    game,b=spell_fixture(folder); seen=_seen(b); b.movement=lambda i: 0 if i==0 else 24
    b.flee(0); assert seen[-1]=='Escape is blocked', seen


def check_made_attack(folder=None):
    game,b=_attack_fixture(folder,0,0); b.record(0)['attacked']=0; b.attack(0,6)
    assert b.record(0)['attacked']==0


def check_cloud_end_of_round(folder=None):
    game,b=spell_fixture(folder); b.data['clouds']=[dict(owner=4,instance=0,cells=((20,10,23),),spent=False)]
    b.put_tile(20,10,30); before=len(game.combat_log)
    b.terrain_effects(6,cloud=False)
    assert not [e for e in game.combat_log[before:] if e['event']=='dice'], 'cloud save rolled at end of round'
    b.terrain_effects(6)
    assert [e for e in game.combat_log[before:] if e['event']=='dice']


def check_teammate_dying(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b)
    town.put(b.chars[1],'status',5); town.put(b.chars[1],'hp',0); town.put(b.chars[1],'active',0)
    pick=lambda options,*names: next(options.index(n) for n in names if n in options)
    game.player=lambda kind,options,*a,**k: pick(options,'Done','Quit','No','Exit',options[0])
    for i in range(6): town.put(b.chars[i],'auto_combat',0)
    b.data['limit']=b.data['round']+1; b.turns()
    assert 'Your Teammate is Dying' in seen, seen


def check_yell_message(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b); c=b.chars[4]; town.put(c,'race',5); b.data['yell']=-1
    b.save=lambda j,kind,bonus=0,element=0: False
    picks=iter(('Yell',))
    game.player=lambda kind,options,*a,**k: options.index(next(picks)) if kind=='COMBAT_ACTION' else 0
    b.record(4)['initiative']=5; b.manual(4)
    assert any(t.endswith(' wants to kill '+combat.name(c)) for t in seen), seen


def check_nausea_text(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b)
    b.data['clouds']=[dict(owner=4,instance=0,cells=((20,10,23),),spent=False)]; b.put_tile(20,10,30)
    b.save=lambda j,kind,bonus=0,element=0: False
    import sm.titles.cok.magic as m; said=[]; add=m._add_with_message
    m._add_with_message=lambda *a: (said.append(a[-1]),add(*a))[1]
    try: b.terrain_effects(6)
    finally: m._add_with_message=add
    assert said==['chokes and gags from nausea'], said


def check_flee_prompt(folder=None):
    game,b=spell_fixture(folder); asked=[]
    b.record(4).update(x=0,y=10,initiative=5,movement=12)
    def player(kind,options,*a,**k):
        if kind=='COMBAT_CONFIRM': asked.append(k.get('prompt')); return 1
        if kind=='COMBAT_ACTION': return options.index('Move') if not asked else options.index('Done')
        if kind=='COMBAT_MOVE': return 6 if not asked else options.index('Done')
        if kind=='COMBAT_DONE': return options.index('Quit')
        return 0
    game.player=player; b.manual(4)
    assert asked==['Flee:'], asked


def check_auto_drops_ally_target(folder=None):
    game,b=spell_fixture(folder); b.record(4).update(target=0,initiative=5)
    seen=[]; ai=b.ai; b.ai=lambda i: seen.append(b.record(i)['target'])
    game.player=lambda kind,options,*a,**k: options.index('Done') if kind=='COMBAT_ACTION' else options.index('Auto') if kind=='COMBAT_DONE' else 0
    b.manual(4)
    assert seen==[-1], seen


def check_undo_invalid_ends(folder=None):
    game,b=spell_fixture(folder); b.record(4).update(x=18,y=10,initiative=5,movement=12)
    moves=iter((2,9))
    def player(kind,options,*a,**k):
        if kind=='COMBAT_MOVE':
            d=next(moves)
            if d==9: b.record(5).update(x=18,y=10)
            return d
        return options.index('Move') if kind=='COMBAT_ACTION' else 0
    game.player=player; b.manual(4)
    assert b.record(4)['initiative']==0 and b.record(4)['size'], b.record(4)


def check_aim_allies(folder=None):
    game,b=spell_fixture(folder); b.record(4).update(x=19,y=10); b.record(3).update(x=18,y=11)
    assert 3 in b.attack_targets(4) and 6 in b.attack_targets(4) and 4 not in b.attack_targets(4)
    asked=[]
    def player(kind,options,*a,**k):
        if kind=='COMBAT_CONFIRM': asked.append(k.get('prompt')); return 0
        if kind=='TARGET': return next(n for n,o in enumerate(options) if o.endswith('#3'))
        return options.index('Aim') if kind=='COMBAT_ACTION' and not asked else options.index('Done') if kind=='COMBAT_ACTION' else options.index('Quit') if kind=='COMBAT_DONE' else 0
    game.player=player; b.record(4)['initiative']=5; before=len(game.combat_log); b.manual(4)
    assert asked==['Attack Ally: '] and any(e['event']=='attack' and e['target']==3 for e in game.combat_log[before:]), asked


def check_throw_with_enemy_near(folder=None):
    game,b=spell_fixture(folder); b.record(4).update(x=19,y=10)
    b.ranged=lambda i: True; b.throwable=lambda i: True; b.ammo=lambda i: (True,None)
    b.record(8).update(x=26,y=10)
    assert 8 in b.attack_targets(4) and 6 in b.attack_targets(4)


def check_prot_missiles(folder=None):
    game,b=_attack_fixture(folder); seen=_seen(b); w=b.weapon(0); t=b.chars[6]
    assert w is not None
    w[combat.I['bonus']]=0; effects.add_effect(t,41,10,0,False)
    b.record(0).update(x=17,y=10); _attack_dice(b,[20,20]); before=len(game.combat_log); b.attack(0,6)
    d100=[e for e in game.combat_log[before:] if e['event']=='dice' and e['sides']==100]
    assert town.field(t,'hp')==250 and sum(x.endswith(' Avoids it') for x in seen)==2 and len(d100)==2, (seen,town.field(t,'hp'))
    b.record(0).update(x=19,y=10); town.put(b.chars[0],'attacks_left',1,0); _attack_dice(b,[20]); del seen[:]; b.attack(0,6)
    near=town.field(t,'hp'); assert near<250 and not any('Avoids' in x for x in seen), seen
    w[combat.I['bonus']]=1; b.record(0).update(x=17,y=10); town.put(b.chars[0],'attacks_left',1,0); _attack_dice(b,[20]); b.attack(0,6)
    assert town.field(t,'hp')<near and not any('Avoids' in x for x in seen), seen


def check_effect_messages(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b); n=lambda i,text: seen.count(combat.name(b.chars[i])+' '+text)
    handle=lambda i,kind,node: effects.call_handler(combat.EffectGame(b,'effect %d'%kind,i),b.chars[i],kind,node,False,b.context(b.chars[i]))
    effects.add_effect(b.chars[4],21,10,0,False); effects.add_effect(b.chars[5],30,10,0,False)
    for i in (4,5,4,5): b.trigger(15,i)
    assert n(4,'is silenced')==1 and n(5,'is coughing')==1 and not b.record(4)['item_ok'] and not b.record(5)['cast_ok'], seen
    c=b.chars[3]; effects.add_effect(c,28,10,0x32,False); die=b.die
    b.die=lambda count,sides,reason,*a: 2 if reason=='effect 28' else die(count,sides,reason,*a)
    x=b.trigger(5,3,b.context(b.chars[6],damage=7)); b.die=die
    assert x.damage==0 and n(3,'lost an image')==1 and effects.has_effect(c,28)[3]==0x31, seen
    effects.add_effect(b.chars[2],39,10,0,False); age=town.field(b.chars[2],'age')
    assert b.rate(2,4)==8 and b.rate(2,4)==8 and n(2,'ages')==1 and town.field(b.chars[2],'age')==age+1, seen
    c=b.chars[1]; strength=town.field(c,'abilities',1); assert strength>3
    effects.add_effect(c,43,60,0,False); handle(1,43,effects.has_effect(c,43))
    assert n(1,'is weakened')==1 and town.field(c,'abilities',1)==strength-1, seen
    c=b.chars[3]; effects.add_effect(c,73,0,0,False); assert not town.field(c,'magic_resistance')
    x=b.trigger(6,3,b.context(b.chars[6],damage=10,element=0x20))
    assert x.damage==0 and n(3,'is unaffected')==1, seen
    c=b.chars[0]; town.put(c,'hp',town.field(c,'hp_max')-2); effects.add_effect(c,62,60,0,False)
    handle(0,62,effects.has_effect(c,62)); handle(0,62,effects.has_effect(c,62))
    assert n(0,'is partially healed')==1 and n(0,'is fully healed')==1 and town.field(c,'hp')==town.field(c,'hp_max'), seen
    ring=effects._handlers()[61]
    for damage,count,result in ((1,1,255),(0,1,254),(10,3,4),(5,3,3)):
        x=effects.Roll(damage=damage,element=9,dice_count=count); ring(None,None,None,False,x)
        assert x.damage==result, (damage,count,x.damage)


def check_immolate_mask(folder=None):
    for kind,reason in ((48,'immolate'),(66,'zap')):
        game,b=_attack_fixture(folder); c=b.chars[0]; effects.add_effect(b.chars[6],kind,0,255,False); effects.add_effect(c,20,10,0,False)
        assert not town.field(c,'magic_resistance')
        town.put(c,'hp_max',50); town.put(c,'hp',50); die=b.die
        b.die=lambda count,sides,why,*a,reason=reason,die=die: 6 if why==reason else die(count,sides,why,*a)
        b.data['roll']=dict(effect=0,damage=0,element=1); b.trigger(15,6)
        assert town.field(c,'hp')==47, (kind,town.field(c,'hp'))


def check_dice_count_left(folder=None):
    stale=lambda b,element=0: b.data.__setitem__('roll',dict(effect=0,damage=0,element=element,dice_count=7))
    game,b=_attack_fixture(folder); c=b.chars[0]; c.effects=[]; effects.add_effect(b.chars[6],48,0,255,False); effects.add_effect(c,61,0,0,False)
    assert not town.field(c,'magic_resistance')
    town.put(c,'hp_max',50); town.put(c,'hp',50); die=b.die
    b.die=lambda count,sides,why,*a: 6 if why=='immolate' else die(count,sides,why,*a)
    stale(b,9); b.trigger(15,6)
    assert b.data['roll']['dice_count']==1 and town.field(c,'hp')==46, (b.data['roll'],town.field(c,'hp'))
    game,b=_attack_fixture(folder); stale(b)
    b.weapon_effect(b.chars[6],60,bytearray([60,0,0,0,1,0,0,0,0]),True)
    assert b.data['roll']['dice_count']==3 and any(e['event']=='dice' and e['reason']=='Aurak explosion' for e in game.combat_log), b.data['roll']
    game,b=_attack_fixture(folder)
    i=next(i for i,c in enumerate(b.chars) if effects.has_effect(c,7) is not None); b.record(i)['target']=6
    stale(b); x=b.context(b.chars[i],dice_count=3); b.weapon_effect(b.chars[i],7,effects.has_effect(b.chars[i],7),False,x)
    assert x.dice_count==1 and b.data['roll']['dice_count']==1, (x.dice_count,b.data['roll'])
    item=b.weapon(0); kept=item[combat.I['type']]; item[combat.I['type']]=54
    stale(b); x=b.context(b.chars[0],dice_count=3); b.weapon_effect(b.chars[6],101,bytearray(9),False,x)
    item[combat.I['type']]=kept
    assert x.dice_count==1 and b.data['roll']['dice_count']==1 and 2<=x.damage<=7, (x.dice_count,x.damage,b.data['roll'])


def check_spell_damage_texts(folder=None):
    game,b=_attack_fixture(folder); c=b.chars[0]; n=combat.name(c); seen=_seen(b)
    town.put(c,'hp_max',200); town.put(c,'hp',200); assert not town.field(c,'magic_resistance')
    for damage,element,text in ((5,1,'5 points of damage from Fire'),(1,2,'1 point of damage from Cold'),(3,4,'3 points of damage from Electricity'),
                                (3,16,'3 points of damage from Acid'),(3,0,'3 points of damage from Magic'),(3,8,'3 points of damage from Magic'),
                                (3,9,'3 points of damage from Fire'),(3,32,'3 points of damage ')):
        del seen[:]; b.spell_damage(c,b.context(b.chars[6],damage=damage,element=element),0,False)
        assert seen==[n+' takes '+text], (seen,text)
    for hp,damage,text in ((5,5,' Goes Down'),(5,8,' Goes Down, and is Dying'),(5,15,' is killed')):
        town.put(c,'hp',hp); town.put(c,'status',0); town.put(c,'active',1); b.record(0)['size']=1; del seen[:]
        b.spell_damage(c,b.context(b.chars[6],damage=damage,element=32),0,False)
        assert seen[1]==n+text, seen
    del seen[:]; b.kill(0,6,'is killed')
    assert seen==[n+' is killed'] and town.field(c,'status')==6
    game,b=_attack_fixture(folder); seen=_seen(b)
    b.end(0,True); assert seen==['Guarding'] and b.record(0)['guard']==1
    b.record(0)['turned']=1; del seen[:]; b.end(0,True); assert not seen and not b.record(0)['guard']


def check_casts_before_target(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b); order=[]
    player=game.player
    def watch(kind,options,*a,**k): order.append(('ask',kind)); return player(kind,options,*a,**k)
    game.player=watch; message=b.message
    b.message=lambda text,report=True:(order.append(('say',text)),message(text,report))
    b.cast(4,15)
    said=next(n for n,(w,v) in enumerate(order) if w=='say' and v.endswith(' Casts a Spell'))
    asked=next(n for n,(w,v) in enumerate(order) if w=='ask' and v=='TARGET')
    assert said<asked, order[:6]
    game,b=spell_fixture(folder); seen=_seen(b); b.cast(4,15,using_item=True)
    assert not any(' uses ' in t or ' Casts ' in t for t in seen), seen
    game,b=spell_fixture(folder); seen=_seen(b); effects.add_effect(b.chars[4],74,0,0,False); b.die=lambda *a:1
    assert not b.cast(4,15) and seen==[combat.name(b.chars[4])+' Casts a Spell'], seen


def check_spell_aborted(folder=None):
    game,b=spell_fixture(folder); seen=_seen(b)
    game.player=lambda kind,options,*a,**k: len(options)-1 if kind=='TARGET' else 0
    assert not b.cast(4,15) and 'Spell Aborted' in seen, seen


def check_cloud_message_first(folder=None):
    game,b=spell_fixture(folder); order=[]; message=b.message
    b.message=lambda text,report=True:(order.append(text),message(text,report))
    die=b.die; b.die=lambda count,sides,reason,*a:(order.append('dice:'+reason),die(count,sides,reason,*a))[1]
    b.data['aim']=(20,10); b.cloud(b.chars[4],3)
    said=next(n for n,v in enumerate(order) if v.endswith('Creates a noxious cloud'))
    assert all(not v.startswith('dice:') for v in order[:said]) and any(v.startswith('dice:') for v in order[said:]), order


def check_cloud_over_corpse(folder=None):
    game,b=spell_fixture(folder); b.record(1).update(x=30,y=15); ground=b.tile(30,15)
    town.put(b.chars[1],'status',6); town.put(b.chars[1],'active',0); b.down(1)
    assert b.tile(30,15)==31
    b.data['aim']=(30,15); b.cloud(b.chars[4],3)
    cell=next(t for x,y,t in b.data['clouds'][-1]['cells'] if (x,y)==(30,15))
    assert cell==ground, (cell,ground)


def check_wall_asked_outdoors(folder=None):
    game,b=spell_fixture(folder); assert not game.vm.is3d()
    game.s.dir=2; spots=[]
    for kind in (1,0):
        b.wall=lambda x,y,d,kind=kind: kind
        b.setup(); spots.append([b.position(i) for i in range(len(game.s.party))])
    assert spots[0]!=spots[1], spots


def check_removed_at_setup(folder=None):
    game,b=spell_fixture(folder); town.put(b.chars[6],'status',9); town.put(b.chars[6],'active',1)
    b.setup(); r=b.record(6)
    assert (town.field(b.chars[6],'active'),r['size'])==(0,0) and (r['x'],r['y'])!=(0,0) and b.tile(r['x'],r['y'])!=31


def check_list17(folder=None):
    assert [combat.direction_to(*v) for v in ((0,16,7,0),(7,16,0,0),(7,0,0,16),(0,0,7,16),(0,0,5,0))]==[0,0,4,3,2]
    def dragon():
        game,b=spell_fixture(folder); game.s.monsters=[]; game.s.g['cok.monster_icons']=[]
        combat.load_monsters(game,30,1,30); b.setup(); b.data['tiles'][:]=bytes([23])*1250
        b.data['actor']=6; b.record(6).update(x=10,y=10,initiative=5)
        for i,c in enumerate(game.s.party):
            b.record(i).update(x=40+i,y=20); town.put(c,'hp',200); c.effects=[]; town.put(c,'magic_resistance',0)
        return game,b
    game,b=dragon(); b.record(1).update(x=13,y=10); b.record(0).update(x=17,y=10)
    assert b.cone(6,(14,10),3,7)==[1,0]
    b.put_tile(16,10,next(k for k in range(1,66) if b.terrain(k,2)>b.terrain(23,1)))
    assert b.cone(6,(14,10),3,7)==[1]
    game,b=dragon(); b.record(1).update(x=14,y=10); b.record(0).update(x=11,y=9); b.record(2).update(x=11,y=11)
    b.put_tile(12,10,next(k for k in range(1,66) if b.terrain(k,2)>b.terrain(23,1)))
    assert b.cone(6,(14,10),1,7)==[] and sorted(b.cone(6,(14,10),3,7))==[0,2], b.cone(6,(14,10),3,7)
    game,b=dragon(); b.record(0).update(x=13,y=10); c=b.chars[0]
    effects.add_effect(c,10,10,0,False); town.put(c,'saves',10,3); town.put(c,'save_bonus',0); town.put(c,'robe_order',0)
    die=b.die; b.die=lambda count,sides,reason,*a: 8 if reason=='saving throw' else die(count,sides,reason,*a)
    saves=[]; damage=b.spell_damage
    b.spell_damage=lambda target,context,reduction,saved:(saves.append(saved),damage(target,context,reduction,saved))
    b.trigger(14,6); assert saves==[True], saves
    for standing,stopped in ((0,False),(51,True)):
        game,b=spell_fixture(folder); t=b.chars[6]; t.effects=[]; effects.add_effect(t,63,10,0,False)
        town.put(t,'magic_resistance',0); town.put(t,'hp',100); town.put(t,'hp_max',100)
        b.record(7).update(x=40,y=20); b.data['aim']=(20,10)
        if standing: b.data['current_spell']=standing
        b.lightning(combat.EffectGame(b,'lightning fixture',4),b.chars[4],magic.spell(51),10,length=10,save=3,element=0x24,bounce=False)
        assert (town.field(t,'hp')==100)==stopped, (standing,town.field(t,'hp'))
    game,b=spell_fixture(folder); facade=combat.EffectGame(b,'dice count',4)
    b.damage_dice(15,6,'thrown fireball',6); assert magic._roll(facade,b.chars[4],magic.spell(47)).dice_count==15
    magic._damage_dice(facade,3,10); assert b.context(b.chars[4]).dice_count==3
    town.put(b.chars[7],'active',0); town.put(b.chars[7],'status',10)
    assert 7 in b.area_targets(20,10,1)
    b.record(7)['size']=0; assert 7 not in b.area_targets(20,10,1)
    game,b=spell_fixture(folder); game.s.r0[0xE6]=2
    b.put_tile(22,10,next(k for k in range(1,66) if b.terrain(k)==255)); b.data['aim']=(20,10)
    b.lightning(combat.EffectGame(b,'lightning fixture',4),b.chars[4],magic.spell(51),1)
    assert not any(e['bounce'] for e in game.combat_log if e['event']=='lightning segment')
    game,b=spell_fixture(folder); b.data['actor']=6; b.data['round']=1; targets=b.spell_targets
    b.spell_targets=lambda *a,**k: None
    b.monster_breath(6,85,bytearray([85,0,0,3,0,0,0,0,0]),b.context(b.chars[6])); assert b.data['roll']['element']==0x24
    b.spell_targets=lambda *a,**k: [0]
    b.monster_breath(6,78,bytearray([78,0,0,0,0,0,0,0,0]),b.context(b.chars[6]))
    assert b.data['current_spell']==47 and b.context(b.chars[6]).dice_count==15
    b.data.pop('current_spell'); b.data['roll']=dict(effect=0,damage=0,element=2,dice_count=0); seen=_seen(b)
    c=b.chars[1]; c.effects=[]; town.put(c,'magic_resistance',0); town.put(c,'hp',200); town.put(c,'hp_max',200)
    b.spell_targets=lambda *a,**k: [1]
    die=b.die; b.die=lambda count,sides,reason,*a: 10 if reason=='energy bolt chance' else die(count,sides,reason,*a)
    b.monster_breath(6,4,bytearray([4,0,0,0,0,0,0,0,0]),b.context(b.chars[6]))
    assert sum(text.endswith('from Cold') for text in seen)==2, seen
    game,b=dragon(); b.record(0).update(x=13,y=10); asked=[]; ask=b.ask
    b.ask=lambda kind,*a,**k: (asked.append(kind),ask(kind,*a,**k))[1]
    game.combat_report=[]; b.trigger(14,6); texts=[t for t in game.combat_report if isinstance(t,str)]
    assert not asked and 'breathes' in texts[0] and len(texts)>1 and 'flash' not in b.data, (asked,texts)
    game,b=spell_fixture(folder); b.record(6).update(x=23,y=9); assert b.cast(4,15)
    assert b.data['aim']==(23,9) and b.record(4)['facing']==1, (b.data['aim'],b.record(4)['facing'])


def check_corpse_at_setup(folder=None):
    game,b=spell_fixture(folder)
    for j in (1,7): town.put(b.chars[j],'status',4); town.put(b.chars[j],'active',0)
    b.setup(); x,y=b.position(1)
    assert b.tile(x,y)==31 and b.record(1)['size']==0 and b.data['downed']==[(x,y,23)], (b.tile(x,y),b.data.get('downed'))
    assert b.tile(*b.position(7))!=31
    assert b.data['downed_who']==[1], b.data.get('downed_who')
    assert b.revive(1,5,'stands') and b.tile(x,y)==23 and b.data['downed']==[(0,0,0)] and b.data['downed_who']==[-1]


def check_surrender_no_body(folder=None):
    game,b=spell_fixture(folder); c=b.chars[1]; b.put_tile(6,5,27)
    town.put(c,'npc',0x81); town.put(c,'hp',1); town.put(c,'abilities',10,3)
    b.movement=lambda j: 2 if j==1 else 24
    b.record(1).update(initiative=5); b.data.update(view=(30,15),gfx=False)
    assert b.morale(1) is True
    assert (town.field(c,'status'),town.field(c,'active'),town.field(c,'hp'))==(4,0,0)
    assert (b.record(1)['size'],b.record(1)['initiative'])==(0,0)
    assert b.tile(6,5)==27 and not b.data.get('downed'), (b.tile(6,5),b.data.get('downed'))
    assert b.data['view']==(30,15) and b.data['messages'][-1]==combat.name(c)+' Surrenders', (b.data['view'],b.data['messages'])
    game,b=spell_fixture(folder); c=b.chars[1]
    town.put(c,'npc',0x81); town.put(c,'hp',1); town.put(c,'abilities',10,3)
    b.movement=lambda j: 2 if j==1 else 24; b.data.update(view=(30,15),gfx=True)
    assert b.morale(1) is True and b.data['view']==(3,2), b.data['view']


def open_fixture(folder=None):
    game,b=large_fixture(folder,1); wall=next(t for t in range(1,66) if b.terrain(t,2)>b.terrain(23,1))
    for j,(x,y) in zip((6,7,8,9),((22,10),(20,8),(21,11),(18,10))):
        town.put(b.chars[j],'active',1); town.put(b.chars[j],'status',0); b.record(j).update(x=x,y=y,size=1)
    b.record(0).update(x=20,y=10)
    return game,b,wall


def check_target_list(folder=None):
    game,b,wall=open_fixture(folder); here=b.cells(0)
    assert b.spans(here)[:5]==[(0,0,0),(8,3,3),(7,4,0),(6,4,2),(9,4,6)], b.spans(here)[:5]
    assert [j for j,*_ in b.spans(here,1)]==[0,8] and b.area_targets(20,10,1)==[0,8] and b.targets(0,1)==[8]
    assert b.targets(0,2)==[8,7,6,9] and b.targets(0,2,allies=True)==[0,8,7,6,9]
    for spot in ((21,10),(22,10)):
        b.put_tile(*spot,wall)
        assert 6 not in [j for j,*_ in b.spans(here)] and (6,4,2) in b.spans(here,255,True), spot
        b.put_tile(*spot,23)
    b.put_tile(20,10,wall); assert b.spans(here)==[] and len(b.spans(here,255,True))==10
    game,b=large_fixture(folder,4); b.record(0).update(x=23,y=11)
    assert (6,4,6) in b.spans(b.cells(0)) and (0,4,2) in b.spans(b.cells(6))


def check_near_whole_figure(folder=None):
    game,b=large_fixture(folder,4); b.record(0).update(x=22,y=12)
    assert b.near(6)==[0] and 0 not in b.area_targets(*b.position(6),1), (b.near(6),b.area_targets(*b.position(6),1))
    b.record(0).update(x=19,y=9); b.record(6)['size']=0
    assert b.near(6)==[], b.near(6)


def check_aura_sight(folder=None):
    game,b,wall=open_fixture(folder); carrier,far,close=b.chars[0],b.chars[6],b.chars[8]
    covered=lambda other,reach: b.context(carrier).call('in_aura_range',carrier,other,reach)
    assert covered(close,1) and not covered(far,1) and covered(far,6)
    b.put_tile(21,10,wall); assert not covered(far,6) and covered(close,6)
    b.put_tile(21,10,23); assert covered(far,6)


def check_berserk_sight(folder=None):
    game,b,wall=open_fixture(folder)
    for j in (7,9): b.record(j).update(x=20+j,y=20)
    b.put_tile(21,11,wall)
    b.berserk(0,77,None)
    assert b.record(0)['target']==6 and town.field(b.chars[0],'side')==town.field(b.chars[6],'side')^1, b.record(0)['target']


def check_distance_no_square(folder=None):
    game,b,wall=open_fixture(folder)
    b.put_tile(21,10,wall); assert (b.distance(0,6),b.distance(0,8),b.distance(0,5))==(2,1,30)
    b.record(6)['size']=0; assert b.distance(0,6)==30, b.distance(0,6)
    b.record(0)['size']=0; assert b.distance(0,8)==255


def check_ally_attack_turns_all(folder=None):
    game,b=spell_fixture(folder); asked=[]
    town.put(b.chars[7],'side',0); town.put(b.chars[7],'npc',178); b.record(7)['target']=6
    b.record(8)['target']=0; town.put(b.chars[9],'npc',0xB3); town.put(b.chars[9],'side',0)
    game.player=lambda kind,options,*a,**k: asked.append(k.get('start')) or 0
    assert b.confirm_ally(4,3) and asked==[1], asked
    assert town.field(b.chars[7],'side')==1 and b.record(7)['target']==-1 and b.record(8)['target']==-1
    assert town.field(b.chars[9],'side')==0 and all(town.field(c,'side')==0 for c in game.s.party)


def check_side_count_stale(folder=None):
    game,b=spell_fixture(folder); b.count_teams(); live=b.teams()[1]
    b.kill(6,6,'is killed'); assert b.teams()[1]==live-1 and b.team(1)==live, (b.teams(),b.team(1))
    b.damage(7,200,b.context(b.chars[4])); assert b.teams()[1]==live-2 and b.team(1)==live-1
    b.count_teams(); assert b.team(1)==live-2 and 'ghosts' not in b.data


def check_slay_helpless_shown(folder=None):
    game,b=spell_fixture(folder); b.record(4).update(x=19,y=10); effects.add_effect(b.chars[6],52,10,0,False)
    town.put(b.chars[4],'attacks_left',1); game.combat_report=[]
    b.attack(4,6)
    shown=[e for e in game.combat_report if isinstance(e,dict) and e.get('kind')=='attack']
    assert shown and shown[0]['lead']=='slays helpless' and shown[0]['result']=='with one cruel blow', shown
    assert not town.field(b.chars[6],'active')


def check_flee_step_in_range_flag(folder=None):
    for flag in (False,True):
        game,b=spell_fixture(folder); b.data['view']=(0,0)
        b.record(6).update(x=30,y=15,fleeing=1,movement=24,initiative=5,stance=1)
        if flag: b.data['in_range']=True
        b.data.update(last_direction=8,stuck=0,actor=6); b.ai_step(6)
        assert b.position(6)!=(30,15) and b.data['gfx'] is flag, (flag,b.data['gfx'],b.position(6))


def check_aim_spell_at_body(folder=None):
    game,b=spell_fixture(folder); b.record(3).update(x=18,y=11)
    town.put(b.chars[3],'status',5); town.put(b.chars[3],'active',0); town.put(b.chars[3],'hp',0); b.down(3)
    assert b.tile(18,11)==31 and b.record(3)['size']==0
    seen=[]
    def player(kind,options,*a,**k):
        seen.append((list(options),list(k.get('targets',())))); return next(n for n,o in enumerate(options) if o.endswith('#3'))
    game.player=player
    assert b.spell_targets(4,magic.spell(3))==[3] and 3 not in seen[0][1], seen
    b.record(5).update(x=18,y=11); seen.clear()
    game.player=lambda kind,options,*a,**k: seen.append(list(options)) or len(options)-1
    b.spell_targets(4,magic.spell(3)); assert not any(o.endswith('#3') for o in seen[0]), seen


def test(folder=None, quick=False):
    folder = folder or os.environ.get('SM_COK')
    if not folder: return 'skipped (no Champions copy)'
    if quick: check_bandage(folder); return 'first eligible patient'
    first = fight(True,folder)
    loss = fight(False,folder); check_disarm(folder); check_missile(folder); frame = check_browser(folder)
    spells=check_spells(folder)
    turning=check_turning(folder)
    kapak=check_kapak(folder)
    casting=fight(True,folder,spells=True)
    assert (first['rounds'],first['state'],first['dice'])==(11,'124f9ba8efe433ad','f552c258ea04b6fa5638eaa62a5fc1a1070ef51ffed3770656eb5954196f0f04')
    assert (loss['rounds'],loss['state'])==(27,'ea68844d64fae08d')
    assert (casting['rounds'],casting['state'])==(4,'e7f6b5105be09f69')
    throtl=check_throtl_rules(folder)
    spell_frame=check_spell_browser(folder)
    auto_frame=check_auto_browser(folder)
    ally_frame=check_attack_ally(folder)
    check_bandage(folder)
    check_lightning(folder)
    check_acid_breath(folder)
    check_acid_resistance(folder)
    check_unplaced(folder)
    check_aurak_death(folder)
    check_displacement(folder)
    check_resistance_wrap(folder)
    check_regeneration_down(folder)
    check_large_footprints(folder)
    check_no_overlap_fights(folder)
    check_ai_balks(folder)
    check_ai_touch_range(folder)
    check_ai_locked_anchor(folder)
    check_undead_count(folder)
    check_ai_repeat_pick(folder)
    check_sweep_message(folder)
    check_flee_messages(folder)
    check_helpless_mid_sequence(folder)
    check_miss_once(folder)
    check_target_self(folder)
    check_turn_destroyed_gone(folder)
    check_turn_nothing(folder)
    check_turned_strips(folder)
    check_ai_self_spell_keeps_target(folder)
    check_area15_locked(folder)
    check_already_been_targeted(folder)
    check_begins_casting(folder)
    check_fight_keys(folder)
    check_attacker_down_phase(folder)
    check_faerie_fire_sizes(folder)
    check_helpless_byte(folder)
    check_aim_flags(folder)
    check_no_type66_rule(folder)
    check_flee_texts(folder)
    check_made_attack(folder)
    check_cloud_end_of_round(folder)
    check_teammate_dying(folder)
    check_yell_message(folder)
    check_nausea_text(folder)
    check_flee_prompt(folder)
    check_auto_drops_ally_target(folder)
    check_undo_invalid_ends(folder)
    check_aim_allies(folder)
    check_ally_attack_turns_all(folder); check_side_count_stale(folder); check_slay_helpless_shown(folder)
    check_flee_step_in_range_flag(folder); check_aim_spell_at_body(folder)
    check_throw_with_enemy_near(folder)
    check_prot_missiles(folder)
    check_loot_detect(folder)
    check_loot_take(folder)
    check_effect_messages(folder)
    check_immolate_mask(folder)
    check_dice_count_left(folder)
    check_spell_damage_texts(folder)
    check_after_fight(folder)
    check_casts_before_target(folder)
    check_spell_aborted(folder)
    check_cloud_message_first(folder)
    check_cloud_over_corpse(folder)
    check_wall_asked_outdoors(folder)
    check_removed_at_setup(folder)
    check_corpse_at_setup(folder)
    check_list17(folder)
    check_stand_up_ground(folder)
    check_killed_while_down(folder)
    check_down_pulls_view(folder)
    check_view_rule(folder)
    check_surrender_no_body(folder)
    check_target_list(folder)
    check_near_whole_figure(folder)
    check_aura_sight(folder)
    check_berserk_sight(folder)
    check_distance_no_square(folder)
    breadth,seen=breadth_fight(folder,2,6,0)
    assert any('emits an evil stench' in text for text in seen)
    return dict(breadth=breadth,win={k:v for k,v in first.items() if k not in ('log','trace')},
                loss={k:v for k,v in loss.items() if k not in ('log','trace')},
                casting={k:v for k,v in casting.items() if k not in ('log','trace')},frame=frame,spell_frame=spell_frame,auto_frame=auto_frame,ally_frame=ally_frame,spells=spells,turning=turning,kapak=kapak,throtl=throtl)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--folder')
    print(test(parser.parse_args().folder))
