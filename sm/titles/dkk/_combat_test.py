from pathlib import Path
from tempfile import TemporaryDirectory
from .menu import Game
from ._creation_test import create_party
from . import town, rules, effects
from .combat import Battle, load_monsters, Kind


def player(kind, options, game, **info):
    if kind == 'COMBAT_ACTION': return options.index('Quick')
    if kind == 'COMBAT_AUTO': return 0
    if options and 'No' in options: return options.index('No')
    if options and 'Exit' in options: return options.index('Exit')
    return 0


def fight(classes=(3, 3, 3, 3, 3, 3)):
    with TemporaryDirectory(prefix='sm-dkk-combat-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game, classes)
        game.player = player
        town.boot(game)
        data = game.s.g['dkk.battle']
        assert not data['active']
        events = game.combat_log
        assert any(e['event'] == 'attack' for e in events)
        assert any(e['event'] == 'damage' for e in events)
        assert any(e.get('reason') == 'saving throw' for e in events)
        return game.state_hash(), tuple(game.trace), data['result'], data['enemy_survivors'], tuple(events)


def test():
    check_path_stops()
    check_aim_cycle()
    check_manual_aim_typeahead()
    check_aim_attack_refresh()
    check_round_finish()
    check_timed_texts()
    check_spell_target_contract()
    check_camp_only_spell()
    check_delayed_cast_announcement()
    check_aging()
    check_effect_messages()
    check_timed_effects()
    check_area_integration()
    check_area_aim()
    check_monster_loading()
    check_monster_counters()
    check_postcombat()
    check_berserk_across_fights()
    check_cleanup_to_camp()
    check_pathing()
    check_terrain_at_left_edge()
    check_map()
    check_ground_picture()
    check_scroll_redraw()
    check_cursor_redraw()
    check_cursor_after_refused_placement()
    check_terrain_erase()
    check_fall()
    check_facing_pose()
    check_action_redraw()
    check_setup()
    check_setup_feedback()
    check_actions()
    check_movement_order()
    check_ai()
    check_ai_keys()
    test_turning()
    first = fight()
    assert first == fight()
    assert first[2] in ('won','defeat')
    if first[2] == 'won': assert first[3] == 0
    else: assert first[4][-1]['code'] == 128
    game = Game(None)
    load_monsters(game, 1, 1, 1)
    skeleton = game.s.monsters[0]
    x = effects.Roll(effect=35, damage=12)
    effects.call_handler(game, skeleton, 80, effects.has_effect(skeleton, 80), False, x)
    assert (x.effect, x.damage) == (0, 0)
    x = effects.Roll(attack=8, damage=1)
    effects.call_handler(game, skeleton, 108, bytearray(9), False, x)
    assert (x.attack, x.damage&255) == (6, 255)
    load_monsters(game, 0, 2, 0)
    assert game.s.monsters[1].effects[0] is not game.s.monsters[2].effects[0]
    game.s.monsters[1].effects[0][3] = 7
    assert game.s.monsters[2].effects[0][3] == 255
    load_monsters(game, 64, 1, 64)
    attacker = game.s.monsters[-1]
    battle = Battle(game)
    game.battle = battle
    game.s.g['dkk.battle'] = {'active': True, 'actor': 3, 'round': 0,
                            'actors': [{'target': 0} for _ in game.s.monsters]}
    weapon = rules.worn(attacker)[0].data
    x = effects.Roll(attacker=attacker, damage=10, in_combat=True)
    battle.weapon_effect(skeleton, 103, effects.has_effect(skeleton, 103), False, x)
    assert x.damage == 10
    weapon[50] = 0
    battle.weapon_effect(skeleton, 103, effects.has_effect(skeleton, 103), False, x)
    assert x.damage == 0
    weapon[50], weapon[46] = 1, 18
    x.damage = 11
    battle.weapon_effect(skeleton, 93, effects.has_effect(skeleton, 93), False, x)
    assert x.damage == 5
    weapon[46], x.damage = 8, 11
    battle.weapon_effect(skeleton, 93, effects.has_effect(skeleton, 93), False, x)
    assert x.damage == 11


def turning():
    from . import combat
    original = combat.load_monsters
    def ghouls(game, ident, count, picture): return original(game, 16, count, 16)
    def turner(kind, options, game, **info):
        if kind == 'COMBAT_ACTION': return options.index('Turn' if 'Turn' in options else 'Quick')
        return player(kind, options, game, **info)
    combat.load_monsters = ghouls
    try:
        with TemporaryDirectory(prefix='sm-dkk-turn-') as tmp:
            game = Game(None)
            game.roster_directory = Path(tmp)
            create_party(game, (0, 0, 0, 0, 0, 0))
            game.player = turner
            town.boot(game)
            return [e for e in game.combat_log if e['event'] == 'turn undead']
    finally: combat.load_monsters = original


def check_path_stops():
    from . import combat, inventory
    from .records import Item
    game,b = action_fixture()
    for view,shot,expected in (((23,11),(25,13,16,1),(13,0)),((23,11),(25,13,26,13),(23,11)),((0,0),(10,10,13,13),(8,8)),
                               ((23,11),(25,13,48,23),(43,18)),((23,11),(25,13,47,22),(42,17)),((20,10),(22,12,25,14),(20,10))):
        b.data['view'] = view; before = game.s.seed
        b.moving_icon(*shot)
        assert tuple(b.data['view']) == expected and game.s.seed == before, (view,shot,b.data['view'])
    game,b = action_fixture(); r = b.record(0); r.update(stance=1); b.record(1)['x'] = 13; b.record(2)['x'] = 9
    town.put(b.chars[0],'auto_combat',1)
    b.equip = lambda i: None; b.base = lambda item: bytes(12)+bytes((21,0,0,0)); b.can_target = lambda i,j,allies=False: i == j; b.throwable = lambda i: False
    rolled = []; die = b.die
    b.die = lambda count,sides,reason,*rest: (rolled.append(reason),die(count,sides,reason,*rest))[1]
    b.ai(0)
    assert rolled.count('AI attack target') == 21 and rolled.count('acquire target') == 4 and r['initiative'] == 0, rolled
    seen = []
    class Seen(bytes):
        def __getitem__(self, key):
            seen.append(key); return bytes.__getitem__(self,key)
    assets = game.assets; kept = assets.resident
    base = assets.layout['tables']['aiDirOffsets']['offset']
    for stance in (1,3,6):
        r = b.record(0); r.update(target=1,stance=stance,movement=2,initiative=6); b.record(1).update(x=30,y=10)
        b.data.update(last_direction=8,stuck=0); seen.clear()
        assets.resident = Seen(kept)
        try: b.ai_step(0)
        finally: assets.resident = kept
        assert [k for k in seen if base <= k <= base+30] == [base+(stance-1)*5+n for n in range(1,6)], (stance,seen)
    game,b = action_fixture(); c = b.chars[0]
    kind = next(k for k in range(1,64) if rules.tables().base_item(k)[0] == 0 and rules.tables().base_item(k)[13] and not rules.tables().base_item(k)[14]&24)
    raw = bytearray(Item.SIZE); raw[combat.I['type']] = kind; raw[combat.I['readied']] = 1; raw[combat.I['bonus']] = 2
    c.items.append(raw); town.put(c,'class_mask',255); b.recalc(c)
    toggled = []; kept = inventory.toggle_ready
    inventory.toggle_ready = lambda *args: toggled.append(args[2]) or kept(*args)
    before = game.s.seed
    try: b.equip(0)
    finally: inventory.toggle_ready = kept
    assert not toggled and raw[combat.I['readied']] == 1 and game.s.seed == before
    b.held = raw; raw[combat.I['readied']] = 0; b.record(0)['target'] = 1
    town.put(c,'base_thac0',20)
    b.weapon_effect(c,7,None,True)
    assert game.s.seed != before
    b.held = raw; b.record(0)['target'] = -1; before = game.s.seed
    b.weapon_effect(c,7,None,True)
    assert game.s.seed != before
    b.held = None; c.items.clear(); b.recalc(c); x = b.context(c); before = game.s.seed
    b.weapon_effect(c,7,None,True,x)
    assert game.s.seed != before and 2 <= x.damage <= 5
    for action in ('Use','View'):
        game,b = action_fixture(); c = b.chars[0]
        raw = bytearray(Item.SIZE); raw[combat.I['type']] = kind; raw[combat.I['readied']] = 1; raw[combat.I['bonus']] = 2
        raw[combat.I['powers']+1] = 7; raw[combat.I['powers']+2] = 0x80
        c.items.append(raw); town.put(c,'class_mask',255); effects.add_effect(c,7,0,255,True); b.recalc(c)
        b.record(1)['x'] = 11 if action == 'Use' else 13
        assert b.count_targets(0) == [1]
        b.record(0)['size'] = 0
        route = iter(([action]+(['Items'] if action == 'View' else [])+[0,'Ready','Exit']+(['Exit'] if action == 'View' else [])+['End']))
        def player(kind,options,current,**info):
            step = next(route)
            return step if isinstance(step,int) else options.index(step)
        game.player = player; before = game.s.seed
        b.manual(0)
        assert not raw[combat.I['readied']] and effects.has_effect(c,7) is None and b.held is None, action
        assert game.s.seed == (before*0x08088405+1)&0xFFFFFFFF, action
        assert [event['sides'] for event in game.combat_log if event.get('reason') == 'fixed weapon damage'] == [6 if action == 'Use' else 4]
    from . import magic
    game,b = action_fixture(); c = b.chars[0]
    assert rules.spellbook(c) is None
    cast = []; kept = magic.handler
    magic.handler = lambda facade,row: lambda g,caster,targets,spell: cast.append(len(targets))
    try:
        b.spell_targets = lambda i,row,item,ai: b.data.update(aim=b.position(1)) or [1]
        assert b.cast(0,47,ai=True) is True and cast == [1]
        b.spell_targets = lambda i,row,item,ai: None
        assert b.cast(0,47,ai=True) is False and cast == [1]
    finally: magic.handler = kept
    game,b = action_fixture(); seen = []
    def bookless(kind,options,current,**info):
        seen.append(list(options)); return options.index('End')
    game.player = bookless
    b.manual(0)
    assert seen and 'Cast' not in seen[0] and 'Aim' in seen[0]


def test_turning():
    events = turning()
    assert events and all(e['column'] == 8 and e['needed'] == 4 and not e['destroyed'] for e in events), events


def check_aim_cycle():
    game,b = action_fixture()
    b.record(1).update(x=40,y=20); b.record(2).update(x=12,y=10)
    words = iter(('Next','Prev','Next','Center','Exit'))
    seen = []
    def player(kind, options, current, **info):
        seen.append((tuple(options),info.get('selected'),tuple(info['cursor']),info.get('range'),tuple(b.data['view']),
                     info.get('highlight'),info.get('blank'),info.get('word')))
        return options.index(next(words))
    def run(*picks, **how):
        nonlocal words
        words = iter(picks); seen.clear()
        return b.aim_cycle(0,**how)
    game.player = player; before = game.s.seed; named = []; b.named = named.append
    assert b.aim_cycle(0,attack=True) is None and game.s.seed == before and named == [0,1,0,1,1] and b.data['panel'] == 1
    del b.named
    assert seen[0][0] == ('Next','Prev','Manual','Center','Exit','Ground','Escape') and seen[0][5] == ''
    assert [row[1:5] for row in seen] == [(0,(10,10),0,(7,7)),(1,(40,20),35,(37,17)),(0,(10,10),0,(7,7)),(1,(40,20),35,(37,17)),(1,(40,20),35,(37,17))]
    assert tuple(b.data['view']) == (37,17)
    b.record(0)['size'] = 0; game.exit_game = False; seen.clear(); before = game.s.seed
    assert b.aim_cycle(0) is None and b.aim_cycle(0,attack=True) is None and not seen
    assert not game.exit_game and game.s.seed == before and tuple(b.data['view']) == (37,17)
    b.record(0)['size'] = 1
    off,battle = action_fixture(); battle.record(0)['size'] = 0; asked = []
    off.player = lambda kind,options,current,**info:(asked.append(info['prompt']),options.index('End' if asked[1:] else 'Aim'))[1]
    battle.manual(0)
    assert asked == ['TEST','TEST'] and battle.record(0)['initiative'] == 0 and not getattr(off,'exit_game',False) and off.s.seed == 4660
    b.record(0)['target'] = 1; b.data['view'] = (36,14)
    assert run('Escape',attack=True) is None and seen[0][1:6] == (1,(40,20),35,(36,14),'Center') and tuple(b.data['view']) == (7,7)
    town.put(game.s.party[2],'side',1); b.record(0)['target'] = -1
    assert run('Next','Next','Next','Exit',attack=True) is None and [row[1] for row in seen] == [0,2,1,0]
    town.put(game.s.party[2],'side',0); b.record(1).update(x=11,y=10); b.record(2).update(x=10,y=12); b.record(0)['target'] = 1
    assert run('Target',attack=True) == (1,(11,10)) and seen[0][0][:5] == ('TEST #1','Next','Prev','Manual','Target') and seen[0][5] == 'Target'
    b.record(0)['target'] = -1; b.data['view'] = (0,0); named = []; b.named = named.append
    assert run('TEST #1',attack=True) == (1,(11,10)) and 'Target' not in seen[0][0] and seen[0][5] == ''
    assert named == [0,1] and tuple(b.data['view']) == (7,7)
    del b.named; b.data['view'] = (7,7)
    assert run('Next','Exit') is None and seen[0][0][:2] == ('TEST #0','TEST #1') and 'Target' in seen[0][0]
    b.ranged = lambda i: True; b.ammo = lambda i: (False,None); b.throwable = lambda i: False
    assert run('Next','Exit',attack=True) is None and not any('Target' in row[0] or 'TEST #1' in row[0] for row in seen)
    b.ammo = lambda i: (True,None)
    assert run('Next','Exit',attack=True) is None and not any('Target' in row[0] for row in seen)
    b.throwable = lambda i: True
    assert run('Next','Exit',attack=True) is None and 'Target' in seen[1][0]
    full_list = b.targets(0,allies=True)
    assert run('Exit',attack=True) is None and b.data['target_list'] == full_list
    assert run('Next','Exit',attack=True) is None and b.data['target_list'][0] == 1
    assert run('TEST #1',attack=True) == (1,(11,10)) and b.data['target_list'][0] == 1
    del b.ranged, b.ammo, b.throwable
    assert run('Manual','east','Target',attack=True) == (1,(11,10)) and [row[7] for row in seen] == [None,'Exit','Target']
    assert seen[1][3] == 0 and seen[2][3] == 1 and b.data['aim'] == (11,10) and game.s.seed == before
    assert run('Ground','east','east','Center','Exit','Exit',attack=True) is None
    assert [row[7] for row in seen[1:5]] == ['Exit','Target','Exit','Exit'] and seen[4][4] == (9,7)
    assert seen[5][1:8] == (0,(10,10),0,(7,7),'Manual',1,None) and 'Target' not in seen[5][0]
    assert run('Manual','south','south','Exit','Exit',attack=True) is None and seen[3][7] == 'Exit' and seen[3][2] == (10,12)
    assert run('Manual','Exit','Target',reach=5,ground=True,empty=True) == (-1,(10,10)) and seen[1][0][8:] == ('Target','Exit','Center') and seen[2][6] == 1
    assert run('Manual','Exit','Exit',reach=5,ground=True) is None and 'Target' not in seen[2][0]
    assert run('Manual','Exit','Exit',reach=5,creature_ok=False) is None and seen[1][7] == 'Exit'
    assert run('Manual','north','north','south','Target',reach=1,ground=True) == (-1,(10,9)) and [row[7] for row in seen[1:]] == ['Target','Target','Exit','Target']
    assert b.data['panel'] == -1
    assert run('Manual','east','Target',attack=True) == (1,(11,10)) and b.data['panel'] == 1
    assert run('Manual','north','Exit','Exit',reach=1) is None and seen[2][7] == 'Exit'
    b.record(1)['size'] = 0; b.data['tiles'][9*50+10] = 31; b.data.update(downed=[(10,9,23),(10,9,23)],downed_who=[2,1],downed_count=2)
    assert run('Manual','north','Target',reach=5) == (1,(10,9))
    assert run('Manual','north','Exit','Exit',attack=True) is None and seen[2][7] == 'Exit'
    b.record(1)['size'] = 1; b.data['tiles'][9*50+10] = 23; b.data.update(downed=[],downed_who=[],downed_count=0)
    b.record(0).update(x=0,y=0)
    assert run('Manual','northwest','Exit','Exit') is None and seen[2][2] == (0,0) and tuple(b.data['view']) == (0,0)
    b.record(0).update(x=10,y=10); b.record(2).update(x=11,y=11); b.data['view'] = (7,7); asked = []
    def refuse(kind, options, current, **info):
        asked.append(kind)
        if kind == 'COMBAT_ACTION': return options.index('Aim' if asked.count(kind) == 1 else 'End')
        if kind == 'TARGET': return options.index('Manual')
        if kind == 'COMBAT_SPELL_AIM': return options.index('southeast' if asked.count(kind) == 1 else 'Target')
        return options.index('No')
    game.player = refuse; struck = []; b.strike = lambda *a,**k: struck.append(a)
    b.data['panel'] = 2
    b.manual(0)
    assert asked == ['COMBAT_ACTION','TARGET','COMBAT_SPELL_AIM','COMBAT_SPELL_AIM','COMBAT_CONFIRM','COMBAT_ACTION'] and not struck
    assert tuple(b.data['view']) == (8,8) and b.data['panel'] == 0


def check_manual_aim_typeahead():
    from sm.engine import Session
    from .ui.screen import Controller

    game, battle = action_fixture()
    game.play = lambda limit: battle.aim_cycle(0, attack=True)
    session = Session(profile='dkk', game=game)
    try:
        ui = Controller(session, presentation=False)
        now = 0
        ui.clock = lambda: now
        for first, cell in ((('m', 'm'), (10, 10)), (('Right', ''), (11, 10)), (('5', '5'), (11, 10))):
            keys = [first, ('d', chr(4)), ('Right', '')]
            ui.hold_event = dict(kind='script-hold', delay=1)
            ui.hold_until = now + 1
            for symbol, char in keys:
                ui.key(symbol, char)
            assert ui.typeahead == keys
            now += 2
            assert ui.held() is None
            assert session.decision['kind'] == 'COMBAT_SPELL_AIM'
            assert ui.aim_cell == cell and ui.typeahead == []
            assert game.s.g['dkk.runtime']['trace'] == 0
        ui.key('t', 't')
        assert session.error is None and session.result == (1, (11, 10))
        assert game.s.seed == 4660
    finally:
        session.close()


def check_aim_attack_refresh():
    for target, keys in ((1, ('Aim', 'Next', 'Target')), (2, ('Aim', 'Manual', 'south', 'Target', 'Yes'))):
        game, battle = action_fixture()
        battle.record(2).update(x=10, y=11)
        events = []
        choices = iter(keys)

        def choose(kind, options, current, **info):
            word = next(choices)
            events.append(word)
            return options.index(word)

        def strike(actor, defender, missile=None):
            events.append(('strike', actor, defender))
            battle.end(actor)

        game.player = choose
        game.draw_combat_cell = lambda current, cells, highlight, occupant: events.append((cells, highlight, occupant))
        game.flush_combat_view = lambda current: events.append(('flush', current.data['view']))
        battle.strike = strike
        battle.manual(0)
        center = (((10, 10),), False, 0)
        assert events[events.index(keys[-1]) + 1:] == [center, center, ('flush', (7, 7)), ('strike', 0, target)]
        assert game.s.seed == 4660


def action_fixture():
    from .records import Character
    game = Game(None)
    game.s.party = [rules.character(bytes(Character.SIZE)) for _ in range(3)]
    for i,c in enumerate(game.s.party):
        c.b[:5] = bytes((4,))+b'TEST'
        for key,value in (('active',1),('hp',250),('hp_max',255),('dimensions',1),('side',i == 1),
                          ('thac0',20),('base_thac0',20),('attacks_left',2),('damage_rolls',1),('damage_dice',6)):
            town.put(c,key,value)
        town.put(c,'ac',20)
        town.put(c,'ac',20,1)
    game.combat_log = []
    game.player = lambda *a,**k: 0
    game.s.seed = 4660
    game.s.g['dkk.battle'] = dict(active=True,round=1,actor=0,view=(7,7),messages=[],bank=[],
        yell=-1,treasure_boundary=None,tiles=bytearray([23]*1250),order=[0,1,2],cursor=0,
        actors=[dict(x=10+i,y=10,size=1,initiative=6,movement=12,phase=0,sweep=0,guard=0,attacked=0,
            facing=2,target=-1,overkill=0,flanks=0,spread=0,turned=0,turns=0,fleeing=0,stance=0,
            casting=0,cast_ok=True,item_ok=True,outsider=0) for i in range(3)])
    battle = Battle(game); game.battle = battle
    battle.trigger = lambda condition,i,context=None: context or battle.context(battle.chars[i])
    return game,battle


def settlement_fixture():
    game,b = action_fixture()
    a,enemy,c = game.s.party
    game.s.party,game.s.monsters = [a,c],[enemy]
    records = b.data['actors']
    b.data['actors'] = [records[0],records[2],records[1]]
    b.record(2)['outsider'] = 1
    town.put(enemy,'status',4); town.put(enemy,'active',0)
    game.s.r1[0x33E] = 2
    decisions = []
    def choose(kind,options,state,**info):
        decisions.append((kind,options,info))
        return options.index('No') if 'No' in options else options.index('Exit') if 'Exit' in options else 0
    game.player = choose
    b.recalc = lambda c: None
    return game,b,decisions


def check_berserk_across_fights():
    from .combat import treasure
    game, first, _ = settlement_fixture()
    first.record(2)['size'] = 0
    assert first.area_targets(8, 10, 5) == [0, 1]
    first.postcombat()
    game.s.treasure_money[4] = 1
    treasure(game)

    former_first, seeker = game.s.party
    game.s.party.reverse()
    load_monsters(game, 1, 1, 1)
    second = Battle(game)
    second.setup()
    size = second.record(0)['size']
    second.record(0)['size'] = 0
    assert second.distance(0, 1) == 2
    second.record(0)['size'] = size
    for index, x in enumerate((10, 14, 12)):
        second.record(index).update(x=x, y=10)
    for x in range(10, 15):
        second.put_tile(x, 10, 23)
    second.put_tile(11, 10, 1)
    effects.add_effect(seeker, 77, 10, 0, False)
    second.begin_round()
    second.trigger(15, 0)
    assert second.chars[second.record(0)['target']] is former_first
    assert second.record(0)['target'] == 1 and town.field(seeker, 'side') == 1

    second.put_tile(11, 10, 23)
    second.trigger(15, 0)
    assert second.record(0)['target'] == 2 and town.field(seeker, 'side') == 0


def check_postcombat():
    from . import combat, shop, magic
    from .records import Item
    from .faults import BindingRequired
    game,b,seen = settlement_fixture(); enemy = game.s.monsters[0]
    town.put(enemy,'xp_award',101,width=2); town.put(enemy,'hp_rolled',2); town.put(enemy,'hp_roll_needed',3); town.put(enemy,'old_hp_max',17)
    shop.put_coins(enemy,[0,0,0,0,5,0,0]); seed = game.s.seed
    b.data['morale'] = 45
    b.postcombat()
    assert b.data['experience'] == 58 and game.exp_share == 58
    assert [town.field(c,'experience',width=4) for c in game.s.party] == [58,58]
    assert game.s.treasure_money[4] == 5 and game.s.r1[0x33E] == 2
    assert game.s.seed == seed and not b.data['actors'] and game.battle is None
    assert seen[0][2]['summary_lines'] == [(3,game.assets.text('msgPartyWon')),(5,game.assets.text('eachReceives')+'58'),
                                          (7,game.assets.text('experiencePoints')),(10,game.assets.text('msgPartyTreasure'))]
    game.s.treasure_money[4] = 1
    combat.treasure(game)
    assert game.morale_memo == 45 and seen[-1][0] == combat.Kind.CONFIRM.value
    Battle(game).setup()
    assert game.battle.context().morale == 45
    for fought in (True,False):
        game,b,seen = settlement_fixture()
        runtime = game.s.g.setdefault('dkk.runtime',{})
        runtime['slow_text'] = 0
        game.s.treasure_money[4] = 1
        observed = []
        choose = game.player
        def read_prompt(kind,options,state,**info):
            observed.append((kind,runtime['slow_text']))
            return choose(kind,options,state,**info)
        game.player = read_prompt
        b.postcombat(fought)
        assert observed == [(kind.value,int(fought)) for kind in (combat.Kind.ACK,combat.Kind.LOOT,combat.Kind.CONFIRM)]
        assert seen[-1][2]['offer'] == game.assets.text('treasureLeft1')+game.assets.text('treasureLeft2')
        assert runtime['slow_text'] == 1
    for old_hp in (0,17,255):
        game,b,seen = settlement_fixture(); enemy = game.s.monsters[0]
        town.put(enemy,'hp_roll_needed',255); town.put(enemy,'hp_rolled',255); town.put(enemy,'old_hp_max',old_hp)
        assert b.loot_experience(b.chars,0) == 32512
    for status,hp,revive,expected in ((5,7,1,(0,1,1)),(4,7,1,(0,1,7)),(4,0,1,(0,1,1)),(5,7,0,(4,0,7))):
        game,b,seen = settlement_fixture(); c = game.s.party[1]
        town.put(c,'status',status); town.put(c,'hp',hp); town.put(c,'active',0); game.s.r1[0x2E6] = revive
        b.postcombat()
        assert tuple(town.field(c,k) for k in ('status','active','hp')) == expected
    game,b,seen = settlement_fixture(); game.s.r1[0x2E6] = 1
    for c in game.s.party: town.put(c,'status',5); town.put(c,'active',0)
    b.postcombat()
    assert game.s.r1[0x2C7] == 128 and b.data['result'] == 'lost' and not game.s.party_dead
    assert seen[0][2]['summary_lines'][0][1] == game.assets.text('msgLostFight') and seen[0][2]['experience'] == 0
    assert all(town.field(c,'hp') == 1 for c in game.s.party)
    game,b,seen = settlement_fixture()
    for c in game.s.party: town.put(c,'status',6); town.put(c,'active',0)
    game.s.treasure_money[4] = 123; game.s.treasure_items = [bytearray(Item.SIZE)]
    b.postcombat()
    assert game.s.party_dead and not game.s.party and game.s.r1[0x2C7] == 128
    assert seen[0][2]['message'] == game.assets.text('partyDestroyed') and game.s.treasure_items
    game,b,seen = settlement_fixture(); runner,fallen = game.s.party
    town.put(runner,'status',3); town.put(fallen,'status',6); town.put(fallen,'active',0)
    town.put(game.s.monsters[0],'status',3); game.s.treasure_money[4] = 9
    held = []
    for owner in (runner,fallen,game.s.monsters[0]):
        slot = rules.allocate_item(game); slot[Item.FIELDS['type'][0]] = 41; owner.items.append(slot); held.append(slot)
    assert all(slot is game.item_pool.slots[k] for k,slot in enumerate(held))
    b.postcombat()
    assert [slot[Item.FIELDS['type'][0]] for slot in held] == [41,0,0]
    assert runner.items == [held[0]] and not fallen.items
    assert game.s.party == [runner] and game.s.r1[0x2C7] == 129 and game.s.r1[0x33E] == 1
    assert not any(game.s.treasure_money)
    game,b,seen = settlement_fixture(); game.demo_mode = 1; game.s.r1[0x370] = 9; game.s.r0[0x1F5] = 1
    b.postcombat()
    assert not seen and game.s.r1[0x370] == 9 and game.s.r0[0x1F5] == 1 and not hasattr(game,'exp_share')
    game,b,seen = settlement_fixture(); game.s.r0[0x1F5] = 1; game.s.treasure_money[4] = 12
    b.postcombat()
    assert len(seen[0][2]['summary_lines']) == 2 and town.field(game.s.party[0],'experience',width=4) == 0
    assert game.s.r0[0x1F5] == 0 and game.s.g['dkk.runtime']['slow_text'] == 1
    game,b,seen = settlement_fixture(); game.exp_share = 77
    for c in game.s.party: town.put(c,'status',4); town.put(c,'active',0)
    game.s.monsters = []; game.s.r1[0x2E6] = 1
    b.postcombat(False)
    assert b.data['experience'] == 77 and game.exp_share == 77 and seen[0][2]['experience'] == 77
    assert seen[0][2]['summary_lines'][0][1] == game.assets.text('msgPartyTreasure')
    game,b,seen = settlement_fixture(); game.s.r1[0x33E] = 3; town.put(game.s.monsters[0],'xp_award',10,width=2)
    assert b.loot_experience(b.chars,0) == 3
    game.s.r1[0x33E] = 0
    try: b.loot_experience(b.chars,0)
    except BindingRequired: pass
    else: assert False
    game,b,seen = settlement_fixture(); game.s.treasure_money[4] = 0x7FFFFFFF
    shop.put_coins(game.s.monsters[0],[0,0,0,0,1,0,0])
    assert b.loot_experience(b.chars,0) == 0 and game.s.treasure_money[4] == -0x80000000
    for suppress,expected in ((0,600),(1,0)):
        game,b,seen = settlement_fixture(); enemy = game.s.monsters[0]
        old = bytearray(Item.SIZE); old[combat.I['bonus']] = 9
        game.s.treasure_items = [old]; b.data['treasure_boundary'] = 0
        for bonus in (1,2):
            raw = bytearray(Item.SIZE); raw[combat.I['bonus']] = bonus; raw[combat.I['readied']] = 1
            enemy.items.append(raw)
        game.s.r1[0x2E3] = suppress
        assert b.loot_experience(b.chars,0) == expected
        assert [raw[combat.I['bonus']] for raw in game.s.treasure_items] == ([9] if suppress else [2,1,9])
        assert all(raw[combat.I['readied']] == 1 for raw in enemy.items)
        assert all(not raw[combat.I['readied']] for raw in game.s.treasure_items)
    for cls,expected in ((0,-12),(8,-5),(9,-3)):
        game,b,seen = settlement_fixture(); c = game.s.party[0]
        town.put(c,'class',cls); town.put(c,'abilities',15,5)
        b.award_experience([c],-11)
        assert town.field(c,'experience',width=4,signed=True) == expected
    game,b,seen = settlement_fixture(); b.record(0)['outsider'] = 2
    game.s.monsters = []; b.postcombat(False)
    assert len(game.s.party) == 2 and game.s.r1[0x33E] == 2
    game,b,seen = settlement_fixture(); b.record(0)['outsider'] = 1
    b.postcombat(False)
    assert game.s.party_dead and len(game.s.party) == 1 and town.field(game.s.party[0],'experience',width=4) == 0
    check_loot()


def check_cleanup_to_camp():
    from unittest.mock import patch
    from . import magic
    from .records import Spells
    game, battle, decisions = settlement_fixture()
    caster, target = game.s.party
    caster = game.s.party[0] = rules.character(bytes(caster.b), spells=bytes(Spells()))
    town.put(caster, 'memorized', 3)
    town.put(target, 'hp', 5)
    town.put(target, 'hp_max', 6)
    battle.data.update(cursor_active=True, cursor_size=1)
    award = battle.award_experience
    def settled_experience(participants, share):
        assert game.battle is None and battle.data['active']
        assert all(key not in battle.data for key in ('tiles', 'view', 'cursor_active', 'cursor_size'))
        return award(participants, share)
    release = rules.release_inventory
    def release_in_loot(game, char):
        assert game.s.mode == 6 and not battle.data['active']
        return release(game, char)
    enemy = game.s.monsters[0]
    with patch.object(battle, 'award_experience', side_effect=settled_experience) as awarded, \
         patch.object(rules, 'release_inventory', side_effect=release_in_loot) as released:
        battle.postcombat()
    awarded.assert_called_once()
    released.assert_called_once_with(game, enemy)

    decisions.clear()
    def pick_member(kind, options, state, **info):
        decisions.append((kind, options, info))
        return 1 if info.get('who') else 0
    game.player = pick_member
    assert magic.cast_in_camp(game, caster, 3)
    assert decisions[1][2]['prompt'] == game.assets.text('spellTargetPrompt')
    assert decisions[1][2]['who'] and decisions[1][2]['start'] == 0
    assert game.noncombat_target is target and town.field(target, 'hp') == 6
    assert town.field(caster, 'hp') == 250 and town.field(caster, 'memorized') == 131


def check_loot():
    from unittest.mock import patch
    from . import combat, shop, magic
    from .records import Item, Spells
    def item(tag):
        raw = bytearray(Item.SIZE); raw[combat.I['bonus']] = tag
        raw[combat.I['type']] = 1
        return raw
    game,b,seen = settlement_fixture(); game.s.treasure_money[4] = 1
    with patch.object(shop,'take_menu') as take:
        combat.loot_take(game); take.assert_called_once_with(game,game.s.party[0])
    assert not seen
    game,b,seen = settlement_fixture(); game.s.treasure_items = [item(1),item(2),item(3)]
    answers = iter((1,1,1))
    def choose(kind,options,state,**info): seen.append((kind,options,info)); return next(answers)
    game.player = choose
    combat.loot_take(game)
    assert [d[2]['start'] for d in seen] == [0,1,0]
    assert [r[combat.I['bonus']] for r in game.s.party[0].items] == [2,3]
    assert len(game.s.treasure_items) == 1 and seen[0][2]['prompt'] == game.assets.text('itemsQuery')
    game,b,seen = settlement_fixture(); game.s.treasure_items = [item(1),item(2)]
    game.s.party[0].items = [item(0) for _ in range(16)]
    answers = iter((1,2)); game.player = choose
    combat.loot_take(game)
    assert len(game.s.treasure_items) == 2 and seen[-1][2]['start'] == 1
    assert seen[-1][2]['message'] == game.assets.text('tradeOverloadMessage') and game.shop_note == ''
    game,b,seen = settlement_fixture(); game.s.treasure_items = [item(1)]; game.s.treasure_money[4] = 1
    answers = iter((4,1,1,0,2)); game.player = choose
    with patch.object(shop,'take_menu') as take:
        combat.loot_take(game); take.assert_called_once_with(game,game.s.party[1])
    assert [d[2]['prompt'] for d in seen] == [game.assets.text('takeQuery'),game.assets.text('takeQuery'),
                                           game.assets.text('itemsQuery'),game.assets.text('takeQuery'),game.assets.text('takeQuery')]
    assert game.s.sel == 1
    game,b,seen = settlement_fixture(); game.s.treasure_money[0] = 1
    assert combat.treasure_flags(game.s) == (False,False)
    game.s.treasure_money[4] = -1
    assert combat.treasure_flags(game.s) == (True,False)
    game,b,seen = settlement_fixture(); game.s.treasure_items = [item(1)]
    answers = iter((1,1,3,1)); game.player = choose; drawn = []; game.vm.party_drawn = lambda: drawn.append(len(seen))
    game.vm.archive = lambda *memo: drawn.append(memo)
    b.loot()
    assert [d[2].get('start') for d in seen] == [0,0,1,1] and drawn == [('PIC',60),0]
    assert tuple(seen[-1][1]) == ('Yes','No') and seen[-1][2]['offer'] == game.assets.text('treasureLeft1')+game.assets.text('treasureLeft2')
    game,b,seen = settlement_fixture(); game.s.treasure_items = [item(1)]
    caster = rules.character(bytes(game.s.party[0].b),spells=bytes(Spells()))
    game.s.party[0] = caster
    town.put(caster,'memorized',133,0); town.put(caster,'memorized',11,1); town.put(caster,'memorized',5,73)
    answers = iter((3,4,1)); game.player = choose
    with patch.object(magic,'cast_in_camp') as cast:
        b.loot(); cast.assert_called_once_with(game,caster,11,announce=False)
    assert tuple(seen[0][1]) == ('View','Take','Pool','Detect','Exit','char-up','char-down')
    town.put(caster,'active',0); seen.clear(); answers = iter((3,1))
    b.loot(); assert 'Detect' not in seen[0][1]
    town.put(caster,'active',1); town.put(caster,'levels',9,5)
    town.put(caster,'memorized',0,73); game.s.monsters = []; game.s.treasure_items = []
    game.player = player
    b.postcombat(False)
    assert game.battle is None
    game.s.treasure_items = [item(1)]; seed = game.s.seed; seen.clear()
    def detect_player(kind,options,state,**info):
        seen.append((kind,options,info))
        if 'Detect' in options: return options.index('Detect')
        return options.index('Exit') if 'Exit' in options else options.index('No') if 'No' in options else 0
    game.player = detect_player; b.loot()
    assert town.field(caster,'memorized',1) == 139 and game.s.seed == seed
    assert shop.item_name(game,game.s.treasure_items[0]).startswith('* ')
    assert not any(game.assets.text('castsText') in d[2].get('message','') for d in seen)
    game.battle = b
    with patch.object(Battle,'setup',side_effect=ValueError('stop')):
        try: combat.run(game)
        except ValueError: pass
        else: assert False
    assert game.battle is None and game.current_battle is None


def check_terrain_at_left_edge():
    from . import magic
    for y in (0, 1):
        game, battle = action_fixture()
        actor = battle.record(0)
        actor.update(x=1, y=y)
        battle.record(1).update(x=0, y=y)

        def choose(kind, options, game, **info):
            if kind == Kind.TARGET:
                return options.index('Target' if info['selected'] == 1 else 'Next')
            return 0

        game.player = choose
        assert battle.cast(0, 83)
        assert battle.position(0) == (0, y) and actor['size'] == 0 and actor['target'] == 1
        assert battle.move(0, 6)
        assert battle.position(0) == (-1, y) and actor['movement'] == 10
        assert battle.anchor_reach(0, 1, 1) == (y == 1)
        if y == 1:
            battle.put_tile(49, 0, 1)
            assert not battle.anchor_reach(0, 1, 1)
        assert battle.walk(-1, y, 0, y, 1, ignore=True) == (True, (0, y), 2)
        facing = actor['facing']
        assert battle.cast(0, 19)
        assert actor['facing'] == facing
        assert effects.has(battle.chars[0], magic.spell(game, 19).effect)


def check_pathing():
    from .combat import line, in_cone
    assert list(line(10,10,12,11)) == [(10,10,0),(11,11,3),(12,11,5)]
    assert list(line(10,10,11,12)) == [(10,10,0),(11,11,3),(11,12,5)]
    assert list(line(10,10,10,10)) == [(10,10,0)]
    assert list(line(10,10,8,9)) == [(10,10,0),(9,9,3),(8,9,5)]
    assert list(line(0,0,49,24))[-1] == (49,24,122)
    assert list(line(0,0,128,0))[-1] == (128,0,0)
    assert not in_cone(-1,10,10,10) and not in_cone(10,10,50,10,8)
    assert in_cone(10,10,0,24,255) and in_cone(10,10,0,24,8)
    for d,(x,y) in enumerate(((10,9),(11,9),(11,10),(11,11),(10,11),(9,11),(9,10),(9,9))):
        assert in_cone(10,10,10,10,d) and in_cone(10,10,x,y,d)
        assert not in_cone(10,10,20-x,20-y,d)
    assert in_cone(10,10,11,8,0) and not in_cone(10,10,11,9,0)
    game,b = action_fixture()
    assert b.walk(10,10,12,11,2) == (True,(12,11),5)
    assert b.walk(10,10,12,11,1) == (False,(12,11),5)
    assert b.walk(10,10,10,10,0) == (True,(10,10),0)
    assert b.walk(10,10,12,10,32768) == (False,(11,10),2)
    assert b.walk(10,10,12,10,65535) == (True,(12,10),4)
    for point in ((10,10),(11,10),(12,10)):
        b.put_tile(*point,1)
        assert b.walk(10,10,12,10)[:2] == (False,point)
        assert b.walk(10,10,12,10,ignore=True) == (True,(12,10),4)
        b.put_tile(*point,23)
    b.record(1).update(x=14,y=10,size=0)
    b.record(2).update(x=10,y=14)
    assert b.distance(0,1) == 4 and b.distance(0,-1) == 4
    b.record(0)['size'] = 0
    assert b.spans(b.cells(0)) == [] and b.distance(0,1) == 255
    assert b.area_targets(8,13,3) == [2]
    assert b.distance(0,1) == 2
    assert b.distance(2,2) == 0
    game.player = lambda *args, **kwargs: b.count_targets(2, same_side=True).index(2)
    b.ask(Kind.ACK, ('Continue',))
    assert b.distance(0,1) == 2
    assert b.count_targets(2) == [] and b.distance(0,1) == 0
    game,b = action_fixture()
    b.record(0).update(x=10,y=10,size=4)
    b.record(1).update(x=12,y=12)
    b.record(2).update(x=20,y=20)
    assert b.span(b.cells(0),1,1) == (3,3)
    assert b.near(0) == [1] and b.context().call('neighbours',b.chars[0]) == [b.chars[1]]
    b.record(0)['size'] = 0
    assert not b.near(0)
    game,b = action_fixture()
    b.record(1).update(x=12,y=10)
    b.record(2).update(x=10,y=12)
    assert b.spans([(10,10)],direction=2) == [(0,0,2),(1,4,2)]
    assert b.spans([(10,10)],direction=4) == [(0,0,4),(2,4,4)]
    assert b.spans([(-1,10)],ignore=True) == []
    b.record(1).update(x=50,y=10)
    assert b.span([(10,10)],1,ignore=True) is None
    b.record(1).update(x=12,y=10)
    town.put(b.chars[1],'active',0)
    assert b.targets(0,allies=True) == [0,1,2]
    assert b.area_targets(10,10,255) == [0,1,2]
    b.record(1).update(x=10,y=8)
    b.record(2).update(x=12,y=12)
    assert b.spans([(10,10)]) == [(0,0,0),(1,4,0),(2,6,3)]
    b.record(1).update(x=9,y=9)
    b.record(2).update(x=11,y=11)
    assert b.spans([(10,10)]) == [(0,0,0),(2,3,3),(1,3,7)]
    b.record(1).update(x=10,y=8)
    b.record(2).update(x=11,y=9)
    b.walk = lambda *a,**kw:(True,(a[2],a[3]),0 if a[:2]==a[2:4] else 4)
    assert b.spans([(10,10)]) == [(0,0,0),(1,4,0),(2,4,1)]
    b.record(1).update(x=12,y=10)
    assert b.spans([(10,10)]) == [(0,0,0),(1,4,2),(2,4,1)]
    game,b = action_fixture(); visits=[]
    b.record(1).update(x=14,y=10,size=4)
    def probe(x,y,tx,ty,*args):
        visits.append((x,y,tx,ty))
        return True,(tx,ty),4
    b.walk = probe
    origins=[(10,10),(10,11)]
    b.span(origins,1)
    assert visits == [(x,y,tx,ty) for tx,ty in b.cells(1) for x,y in origins]
    game,b = action_fixture(); del b.trigger
    for c in b.chars: c.effects.clear()
    b.record(1).update(x=13,y=10)
    b.record(2).update(x=20,y=20)
    town.put(b.chars[1],'side',0)
    effects.add_effect(b.chars[0],49,0,0,False)
    before=game.s.seed
    assert b.trigger(10,1,b.context(b.chars[1],attack=10)).attack == 11
    b.put_tile(11,10,1)
    assert b.trigger(10,1,b.context(b.chars[1],attack=10)).attack == 10
    b.put_tile(11,10,23); b.record(0)['size']=0
    assert b.trigger(10,1,b.context(b.chars[1],attack=10)).attack == 10
    b.record(0)['size']=1; b.record(1)['size']=0
    assert b.trigger(10,1,b.context(b.chars[1],attack=10)).attack == 10
    assert game.s.seed == before


def check_ground_picture():
    game, battle = action_fixture()
    x, y = 10, 10
    for tile, picture in ((0, 20), (70, 20), (1, 0), (26, 38), (69, 37), (30, 20)):
        battle.put_tile(x, y, tile)
        assert battle.ground_picture(x, y) == picture
    assert battle.ground_picture(-1, y) == 20

    battle.data['clouds'] = [dict(cells=[(x, y, 22)]), dict(cells=[(x, y, 31)])]
    bodies = [(x, y, 23), (x, y, 26), (x + 1, y, 27), (x, y, 21)]
    battle.data.update(downed=bodies, downed_count=3)
    battle.put_tile(x, y, 28)
    assert battle.resolve_terrain(x, y) == 31
    assert battle.ground_picture(x, y) == 38
    for under in (0, 70):
        bodies[1] = (x, y, under)
        assert battle.ground_picture(x, y) == 20

    bodies[1] = (x, y, 29)
    battle.put_tile(x, y, 31)
    assert battle.resolve_terrain(x, y) == 29
    assert battle.ground_picture(x, y) == 21
    assert battle.tile(x, y) == 31 and game.s.seed == 4660
    assert len(bodies) == 4 and 'downed_who' not in battle.data


def check_scroll_redraw():
    game, battle = action_fixture()
    paints = []
    def draw(current, cells, highlight, occupant):
        paints.append((current.data['view'], cells, highlight, occupant))
    game.draw_combat_cell = draw
    def flush(current):
        assert current is battle
        paints.append('flush')
    game.flush_combat_view = flush
    battle.data.update(view=(0,0), cursor_active=True, gfx=False)
    battle.record(0).update(x=6, y=7, size=4)
    town.put(battle.chars[1], 'active', 0)
    battle.record(1).update(x=10, y=10)
    battle.record(2).update(x=7, y=8)
    view = (7,7)
    terrain = tuple((x,y) for y in range(7,14) for x in range(7,14))
    source = (view, ((10,10),), False, 1)
    cursor = (view, ((10,10),), True, 1)
    assert battle.scroll(10,10,2)
    assert paints == [(view,terrain,False,-1), (view,(),False,0), (view,(),False,2), source, cursor, 'flush']
    paints.clear()
    assert not battle.scroll(10,10,2)
    assert paints == [source, cursor, 'flush']
    battle.record(0)['size'] = 0
    battle.record(2)['x'] = 14
    paints.clear()
    assert battle.scroll(10,10,255)
    assert paints == [(view,terrain,False,-1), source, cursor, 'flush']
    battle.data['view'] = (0,0)
    paints.clear()
    battle.scroll(0,0,2,7)
    assert paints[-3:] == [((0,0),((0,0),),False,-1), ((0,0),((0,0),),True,-1), 'flush']
    assert game.s.seed == 4660


def check_cursor_redraw():
    game, battle = action_fixture()
    paints = []
    def draw(current, cells, cursor, occupant):
        assert current is battle
        paints.append((cells, cursor, occupant))
    game.draw_combat_cell = draw
    battle.record(2).update(x=12, y=12, size=4)
    town.put(battle.chars[2], 'active', 0)
    square = ((12,12),(13,12),(12,13),(13,13))
    battle.centered_view(2, 3, True)
    assert paints == [(square,False,2),(square,True,2)]
    assert not battle.data['cursor_active'] and battle.data['cursor_size'] == 1
    battle.record(2).update(x=6, y=6)
    paints.clear()
    assert not battle.scroll(7,7,3)
    assert paints == [(((7,7),),False,2),(((7,7),),False,2)]
    battle.data.update(cursor_size=4, cursor_active=True)
    battle.redraw_cell(13,13,cursor=True)
    assert paints[-1] == (((13,13),),True,-1)
    battle.data['cursor_size'] = 0
    battle.redraw_cell(7,7,cursor=True)
    assert paints[-1] == ((),True,2)
    battle.record(2)['size'] = 0
    battle.data['stale'] = [(7,7,2)]
    battle.redraw_cell(7,7)
    assert paints[-1] == ((),False,-1)
    battle.data.update(view=(0,0), cursor_size=1)
    battle.scroll(0,0,2,7)
    assert paints[-1] == (((0,0),),True,-1)
    for final in ('Target','Exit'):
        paints.clear()
        keys = iter(('east',final))
        def choose(kind, options, current, **info):
            assert battle.data['cursor_active'] and battle.data['cursor_size'] == 1
            assert paints[-1] == ((info['cursor'],),True,battle.occupancy()[info['cursor']])
            return options.index(next(keys))
        game.player = choose
        result = battle.aim_cursor(0,(10,10),3,False,True,True)
        if final == 'Target':
            assert result == (True,(1,(11,10))) and paints[-1] == (((11,10),),False,1)
        else:
            assert result == (True,None)
            assert paints[-2:] == [(((10,10),),True,0),(((10,10),),False,0)]
        assert not battle.data['cursor_active'] and game.s.seed == 4660


def check_cursor_after_refused_placement():
    game, battle = action_fixture()
    target = battle.position(1)
    assert not battle.valid_location(0, *target)
    assert battle.position(0) == target and battle.record(0)['size'] == 0
    paints = []
    game.draw_combat_cell = lambda current, cells, cursor, occupant: paints.append((cells, cursor, occupant))
    battle.turn_view(0)
    assert paints == [((target,), False, 1), ((), True, 1)]
    assert not battle.data['cursor_active'] and battle.data['cursor_size'] == 1


def check_terrain_erase():
    game, battle = action_fixture()
    actor = battle.record(0)
    erases = []
    def draw(current, cells, highlight, occupant):
        if occupant == -1 and not highlight:
            erases.append((cells, actor['facing'], actor['movement'], current.tile(*cells[0])))
    game.draw_combat_cell = draw
    actor.update(x=6,y=6,size=4)
    battle.record(1).update(x=7,y=7)
    battle.erase_footprint(0)
    assert erases == [(((7,7),),2,12,23)]
    actor['size'] = 0
    battle.erase_footprint(0)
    assert len(erases) == 1
    actor.update(x=10,y=10,size=4)
    square = ((10,10),(11,10),(10,11),(11,11))
    erases.clear()
    battle.face(0,3)
    battle.face(0,4)
    battle.face(0,6,frame=1)
    battle.face(0,7,erase_only=True)
    battle.data['gfx'] = False
    battle.face(0,2,frame=1)
    assert actor['facing'] == 2 and erases == [(square,d,12,23) for d in (3,4,6)]

    battle.record(2).update(x=20,y=10)
    battle.data['gfx'] = True
    town.put(battle.chars[0],'dimensions',4)
    keys = iter(('Move','east','Undo','End'))
    game.player = lambda kind,options,state,**info: options.index(next(keys))
    erases.clear()
    battle.manual(0)
    moved = tuple((x+1,y) for x,y in square)
    assert erases == [(square,2,10,23),(moved,2,12,23)]
    assert battle.position(0) == (10,10)

    battle.data['gfx'] = False
    game.player = lambda kind,options,state,**info: options.index('Continue')
    erases.clear()
    actor['movement'] = 12
    battle.data['stale'] = [(10,10,0)]
    battle.down(0)
    battle.down(0)
    center = ((10,10),)
    assert [(cells,left,tile) for cells,_,left,tile in erases] == [
        (square,12,23), (square,12,31), (center,12,31), (center,12,31)]
    assert actor['movement'] == 0
    erases.clear()
    battle.out_of_play(1,3,'')
    assert [entry[0] for entry in erases] == [((7,7),)]

    game, battle = action_fixture()
    game.draw_combat_cell = draw
    actor = battle.record(0)
    battle.record(1)['flanks'] = 2
    town.put(battle.chars[0],'attacks_left',0)
    erases.clear()
    battle.attack(0,1)
    assert [entry[0] for entry in erases] == [((11,10),),((10,10),),((10,10),)]
    assert game.s.seed == 4660


def check_fall():
    for outsider, size in ((0,4), (1,4), (0,0)):
        game, battle = action_fixture()
        actor = battle.record(0)
        actor.update(x=49,y=12,size=size,outsider=outsider,guard=1)
        battle.data['gfx'] = False
        battle.put_tile(49,13,29)
        battle.data['clouds'] = [dict(cells=[(49,13,24)])]
        holds = []
        def hold(kind, options, current, **info):
            assert (kind, options, info['timed'], info['prompt']) == ('ACK', ('Continue',), 1, '')
            assert game.script_sounds == [5]
            assert (actor['size'], actor['guard'], actor['movement']) == (size,1,12)
            assert battle.tile(49,12) == (23 if outsider else 31)
            assert battle.data['downed_count'] == 1-outsider
            assert info['fall'] == 1
            holds.append(game.combat_report[-1])
            return 0
        game.player = hold
        battle.panel(1)
        battle.data['panel'] = -1
        battle.down(0)
        if not outsider: battle.down(0)
        cells = ((49,12,battle.terrain(23,3),None),
                 (49,13,battle.terrain(24,3),battle.terrain(29,3))) if size else ()
        assert holds == game.combat_report == [dict(kind='fall',actor=0,panel=-1,view=(43,7),cells=cells,picture=23,
                              actors=((49,12,size),(11,10,1),(12,10,1)),
                              frames=(0,1,0,1,0,1,0,1,0),pace=10)]
        assert (actor['size'], actor['guard'], actor['movement']) == (0,0,0)
        assert game.s.seed == 4660 and game.script_sounds == [5]


def check_facing_pose():
    game, battle = action_fixture()
    actor = battle.record(0)
    actor.update(x=13, y=10, size=4)
    paints = []
    def draw(current, cells, highlight, occupant):
        paints.append(('cell', cells, occupant, actor['facing']))
    def present(current, who, frame):
        paints.append(('pose', who, frame, current.record(who)['facing']))
    game.draw_combat_cell = draw
    game.present_combat_pose = present
    battle.face(0,6,frame=1)
    clipped = ((13,10),(13,11))
    assert paints[-2:] == [('cell',clipped,-1,2), ('pose',0,1,6)]
    paints.clear()
    battle.face(0,6)
    assert paints[-1] == ('pose',0,0,6)
    assert sum(p[0] == 'pose' for p in paints) == 1
    paints.clear()
    battle.face(0,7,frame=1,erase_only=True)
    assert paints[-1] == ('cell',clipped,-1,6) and all(p[0] == 'cell' for p in paints)
    paints.clear()
    battle.data['gfx'] = False
    battle.face(0,3,frame=1)
    assert actor['facing'] == 3 and not paints
    battle.data['gfx'] = True
    actor.update(x=40, y=20, size=1)
    battle.face(0,0)
    assert battle.visible(0) and paints[-1] == ('pose',0,0,0)
    paints.clear()
    actor['size'] = 0
    battle.face(0,4,frame=1)
    assert actor['facing'] == 4 and all(p[0] == 'cell' for p in paints)
    assert game.s.seed == 4660


def check_action_redraw():
    from unittest.mock import patch
    from . import magic
    game, battle = action_fixture()
    events = []
    def paint(current, cells, highlight, occupant):
        events.append((cells, highlight, occupant))
    game.draw_combat_cell = paint
    actor = (((10,10),), False, 0)
    enemy = (((11,10),), False, 1)
    ally = (((12,10),), False, 2)
    battle.record(0)['target'] = 1
    game.player = lambda kind, options, current, **info: options.index('Target')
    assert battle.aim_cycle(0, attack=True) == (1,(11,10))
    assert events == [actor, enemy, (enemy[0], True, 1)]

    row = magic.spell(game,23)
    def select(kind, picks, ai=False):
        choices = iter(picks)
        def pick(*args):
            j = next(choices)
            return None if j is None else (j,battle.position(j))
        battle.pick_spell_target = pick
        events.clear()
        return battle.spell_targets(0,row._replace(targeting=kind),ai=ai)
    battle.message('Previous message')
    def warning(kind, options, state, **info):
        assert kind == 'ACK' and tuple(options) == ('Continue',)
        assert info['timed'] == 1 and info['message_colour'] == 10 and info['after_pause'] == ' '
        events.append(info['prompt'])
        return 0
    game.player = warning
    assert select(1, (0,1,1,2)) == [1,2]
    assert events == ['Cannot target yourself', actor, enemy, 'Already been targeted', enemy, ally]
    battle.die = lambda *args: 2
    assert select(5, (1,1,None)) == [1]
    assert events == [enemy, 'Already been targeted', enemy]
    assert select(5, (1,2,1,1), ai=True) == [1,2]
    assert events == [enemy, ally, enemy, enemy]
    assert select(1, (None,)) is None and not events
    assert battle.data['messages'] == game.combat_report == ['Previous message']

    game, battle = action_fixture()
    game.draw_combat_cell = paint
    battle.data['limit'] = 2
    def condition(group, i, context=None):
        if (group,i) in ((7,1),(21,2)):
            battle.end(i)
        return context or battle.context(battle.chars[i])
    def act(i):
        assert i == 0
        battle.record(i)['y'] = 11
        battle.end(i)
    battle.trigger, battle.manual = condition, act
    battle.begin_round = lambda: None
    battle.explode = lambda: events.append('after turn')
    with patch.object(effects,'advance'):
        battle.turns()
    assert events[:8] == [actor, (actor[0],True,0), (((10,11),),False,0), 'after turn',
                          'after turn', ally, (ally[0],True,2), ally]
    assert events[8] == 'after turn'


def check_map():
    from .combat import direction_to
    from .faults import BindingRequired
    bodies=lambda:b.data['downed'][:b.data['downed_count']]
    owners=lambda:b.data['downed_who'][:b.data['downed_count']]
    assert direction_to(10,20,17,4) == 0
    assert direction_to(10,20,17,5) == 1
    assert direction_to(10,10,10,10) == 0
    game,b = action_fixture(); r=b.record(0)
    b.data['view']=(0,0); r.update(x=6,y=6,size=4)
    assert b.visible(0) and not b.visible(0,True)
    r['size']=0
    assert not b.visible(0) and not b.visible(0,True)
    r.update(x=30,y=20,size=1)
    b.center(0,255)
    assert b.data['view'] == (27,17)
    b.data['view']=(7,7)
    assert not b.scroll(10,10,3)
    assert b.scroll(10,10,255) and b.data['view'] == (7,7)
    b.scroll(10,10,0,2)
    assert b.data['view'] == (8,7)
    game,b = action_fixture()
    b.record(1).update(x=30,y=20)
    b.turn_view(1)
    assert not b.drawing() and b.data['view']==(7,7)
    assert not b.data['cursor_active'] and b.data['cursor_size']==1
    b.face(1,4)
    assert b.record(1)['facing']==4 and b.data['view']==(7,7)
    assert b.move(1,2) and b.data['view']==(7,7)
    b.data['gfx']=True; b.face(1,6)
    assert b.record(1)['facing']==6 and b.data['view']==(28,17)
    game,b = action_fixture(); b.data['gfx']=False
    b.record(1).update(x=30,y=20)
    b.out_of_play(1,3,'')
    assert b.data['view']==(7,7) and not b.data.get('downed_count',0)
    game,b = action_fixture(); r=b.record(0)
    r.update(x=20,y=15,casting=45,guard=1); b.data['gfx']=False
    b.down(0)
    assert bodies() == [(20,15,23)] and owners() == [0]
    assert b.tile(20,15)==31 and b.data['view']==(17,12)
    assert (r['size'],r['initiative'],r['movement'],r['guard'],r['casting']) == (0,0,0,0,45)
    r.update(initiative=7,movement=8,guard=1); b.data['view']=(0,0)
    b.down(0)
    assert b.data['downed_count']==1 and b.data['view']==(0,0)
    assert (r['initiative'],r['movement'],r['guard']) == (7,8,1)
    assert b.valid_location(0,20,15,True)
    assert b.tile(20,15)==23 and bodies()==[(0,0,0)] and owners()==[-1]
    b.down(0)
    assert bodies()==[(0,0,0),(20,15,23)] and owners()==[-1,0]
    game,b = action_fixture(); r=b.record(0)
    r.update(x=20,y=15,size=0)
    b.down(0)
    assert b.tile(20,15)==31 and owners()==[0]
    b.record(2).update(x=20,y=15); b.down(2)
    assert bodies()==[(20,15,23),(20,15,23)]
    assert b.valid_location(0,20,15,True) and b.tile(20,15)==31
    assert owners()==[-1,2]
    game,b = action_fixture(); r=b.record(0); b.down(0)
    before=(town.field(b.chars[0],'hp'),list(b.data['downed']))
    b.record(1).update(x=10,y=10)
    assert not b.valid_location(0,10,10,True) and r['size']==0
    assert (town.field(b.chars[0],'hp'),b.data['downed'])==before
    assert b.valid_location(0,20,15,False)
    assert owners()==[0] and b.tile(10,10)==31
    assert b.valid_location(0,20,15,True)
    assert owners()==[-1] and b.tile(10,10)==31 and b.tile(20,15)==23
    game,b = action_fixture(); r=b.record(0); r['outsider']=1
    b.down(0)
    assert b.tile(10,10)==23 and not b.data.get('downed_count',0) and r['size']==0
    game,b = action_fixture()
    b.record(0).update(x=11,y=10)
    assert b.probe(1)[0]==-1
    b.record(2).update(x=11,y=10)
    assert b.probe(1)[0]==2
    game,b = action_fixture()
    assert not b.valid_location(2,10,10,True)
    assert b.record(2)['size']==0 and b.record(0)['size']==1
    game,b = action_fixture(); choices=iter(('Move','east','Undo'))
    def move_then_block(kind,options,current,**info):
        choice=next(choices)
        if choice=='Undo': b.record(0).update(x=12,y=10)
        return options.index(choice)
    game.player=move_then_block; b.opportunity=lambda *args:None
    b.manual(2)
    assert b.position(2)==(12,10) and b.record(2)['size']==0
    assert b.record(2)['movement']==12 and b.record(2)['initiative']==6
    game,b = action_fixture()
    b.record(0).update(x=-1,y=10); b.record(1).update(x=-1,y=10)
    assert b.probe(0)==(-1,0)
    game,b = action_fixture(); r=b.record(0)
    b.data['downed']=[(10,10,23),(0,0,0),(10,10,24)]
    b.data['downed_who']=[0,-1,2]; b.put_tile(10,10,31)
    assert b.resolve_terrain(10,10)==24
    b.put_tile(0,0,31)
    assert b.resolve_terrain(0,0)==0
    game,b = action_fixture(); b.put_tile(10,10,28)
    b.down(0)
    assert b.tile(10,10)==28 and bodies()==[(10,10,28)]
    assert b.valid_location(0,10,10,True) and b.tile(10,10)==28
    game,b = action_fixture(); r=b.record(0)
    b.data['downed']=[(0,0,0)]*8; b.data['downed_who']=[-1]*8
    try: b.down(0)
    except BindingRequired: pass
    else: raise AssertionError('downed storage overflow accepted')
    assert r['size']==1 and len(b.data['downed'])==8
    b.data['active']=False; before=dict(r)
    assert b.valid_location(0,30,20,True) and r==before
    game,b = action_fixture(); r=b.record(0); b.down(0)
    b.restore_body(0)
    assert b.data['downed_count']==0 and b.data['downed_who'][0]==0
    assert len(b.data['downed'])==len(b.data['downed_who'])==8 and b.tile(10,10)==23
    assert b.valid_location(0,10,10,True)
    r.update(initiative=7,movement=8,guard=1,casting=45)
    before=dict(r); b.down(0)
    assert r==before and b.data['downed_count']==0
    b.put_tile(10,10,31)
    assert b.resolve_terrain(10,10)==31
    game,b = action_fixture()
    assert not b.valid_location(0,11,10) and b.record(0)['size']==0 and b.data['stale']==[(10,10,0)]
    assert b.occupancy()[(10,10)]==0 and b.contents(10,10)[0]==0
    b.record(1).update(x=11,y=11)
    assert b.probe(1,7)[0]==0 and not b.move(1,7)
    assert b.move(2,2) and 'stale' not in b.data and (10,10) not in b.occupancy()
    assert b.probe(1,7)[0]==-1
    for clear in (lambda: b.down(2), lambda: b.out_of_play(2,3,'flees'), lambda: b.valid_location(2,30,20)):
        game,b = action_fixture()
        assert not b.valid_location(0,11,10) and b.data['stale']
        clear()
        assert 'stale' not in b.data
    game,b = action_fixture(); b.down(0); b.down(2)
    b.restore_body(0)
    assert b.data['downed_count']==1 and b.data['downed_who'][:2]==[2,2]
    assert b.data['downed'][:2]==[(12,10,23),(12,10,23)]


def check_setup():
    from unittest.mock import patch
    from .faults import BindingRequired
    game,b = action_fixture()
    b.t = dict(b.t,classes=bytes(15)+bytes((128,)))
    original = b.die
    def open_ground(count,sides,reason):
        original(count,sides,reason)
        return 100
    b.die = open_ground
    b.wilderness()
    assert len(game.combat_log) == 1250
    assert all(e['reason'] == 'feature chance' for e in game.combat_log)
    assert set(b.data['tiles']) == {69}
    seed = 4660
    for _ in range(1250): seed = (seed*0x08088405+1)&0xFFFFFFFF
    assert game.s.seed == seed
    for percentile,tile,extra in ((1,47,1250),(2,68,0),(30,68,0),(31,64,1250),(45,64,1250),(46,69,0)):
        calls = []
        def feature(count,sides,reason):
            calls.append((reason,sides))
            return percentile if reason == 'feature chance' else 3
        b.die = feature; b.wilderness()
        assert set(b.data['tiles']) == {tile} and len(calls) == 1250+extra
    game.s.r0[0xF3] = 1; calls = []; fords = iter((20,2))
    def river(count,sides,reason):
        calls.append((count,sides,reason))
        return 20 if reason == 'river start' else next(fords,20) if reason == 'ford chance' else 100 if reason == 'feature chance' else 1
    b.die = river; b.wilderness()
    assert list(b.data['tiles'][12:18]) == [52,53,55,55,56,52]
    assert list(b.data['tiles'][63:69]) == [52,58,59,59,61,52]
    assert calls[0] == (5,4,'river start') and sum(reason == 'ford chance' for _,_,reason in calls) == 25
    game.s.r0[0xF3] = 0; b.t['classes'] = bytes(16); first = True
    def tree(count,sides,reason):
        nonlocal first
        if reason == 'tree chance' and first: first = False; return 1
        return 5 if reason in ('tree top','tree bottom') else 100
    b.die = tree; b.wilderness()
    assert (b.tile(0,0),b.tile(0,1)) == (36,41)
    game,b = action_fixture(); game.s.x = game.s.y = 8
    b.wall = lambda x,y,d: 3 if (x,y,d) == (8,8,6) else 0
    game.geo.attr = lambda *args: 0
    b.dungeon(); assert b.tile(22,10) == 1
    b.wall = lambda x,y,d: 3 if (x,y,d) == (8,7,2) else 0
    b.dungeon(); assert b.tile(27,10) == 8
    initial = []
    put_tile = b.put_tile
    def capture(x,y,tile):
        if not initial: initial.append(set(b.data['tiles']))
        put_tile(x,y,tile)
    b.put_tile = capture; b.dungeon()
    assert initial == [{22}]
    game,b = action_fixture(); game.s.dir = 0
    game.s.g['combat.direction_flags'] = 15; game.s.r1[0x2C1] = 0
    game.s.monsters = [game.s.party.pop(1)]
    game.s.monsters *= 4
    b.data['actors'] = [dict(b.record(0),outsider=int(i>=2)) for i in range(6)]
    observed = []; masks_seen = []
    def place(i,masks,counts,distance,plane):
        observed.append((game.s.dir,counts[:],distance,b.record(i)['facing'],plane))
        masks_seen.append(masks)
        return True
    b.place = place; b.place_all()
    assert [row[0] for row in observed] == [0,0,2,4,6,0]
    assert all(row[1] == [1,1] for row in observed)
    assert [row[2] for row in observed] == [0,0,1,1,1,0]
    assert [row[3] for row in observed] == [b.t['facing'][i] for i in (0,0,3,0,1,2)]
    assert masks_seen[0] is masks_seen[1] and all(masks_seen[i] is not masks_seen[i+1] for i in range(1,5))
    assert game.s.dir == 0 and [row[4] for row in observed] == [0,0,1,1,1,1]
    game,b = action_fixture(); game.s.dir = 0
    game.s.g['combat.direction_flags'] = 15; game.s.r1[0x2C1] = 0
    game.s.monsters = [game.s.party.pop(1),game.s.party[0],game.s.party[0]]
    b.data['actors'] = [dict(b.record(0),outsider=int(i>=2)) for i in range(5)]
    planes = []
    b.place = lambda i,masks,counts,distance,plane:planes.append((game.s.dir,plane)) or True
    b.place_all()
    assert planes == [(0,0),(0,0),(2,1),(0,1),(0,0)]
    game.s.g['combat.direction_flags'] = 0; planes.clear(); b.place_all()
    assert planes == [(0,0),(0,0),(0,1),(0,0),(0,0)]
    game,b = action_fixture(); b.data['downed'] = []; town.put(b.chars[0],'active',0)
    b.place = lambda *args: True
    b.place_all()
    assert b.record(0)['size'] == 0 and b.tile(10,10) == 31
    assert b.data['downed_count']==1 and b.data['downed'][0]==(10,10,23) and b.data['downed_who']==[0]+[-1]*7
    game,b = action_fixture(); game.duel_flag = True; town.put(b.chars[0],'active',0)
    visited = []; b.place = lambda i,*args: visited.append(i) or True
    b.place_all(); assert visited == [1,2] and b.record(0)['size'] == 0 and b.tile(10,10) == 23
    game,b = action_fixture(); game.s.monsters = [game.s.party.pop()]
    b.record(2)['outsider'] = 1; b.place = lambda *args: False
    b.place_all()
    assert len(b.chars) == len(b.data['actors']) == 2 and not game.s.monsters
    assert all(r['size'] == 0 for r in b.data['actors']) and b.data['setup_teams'] == [2,1]
    game,b = action_fixture(); town.put(b.chars[1],'status',9)
    b.place = lambda *args: True; b.place_all()
    assert town.field(b.chars[1],'active') and b.record(1)['size'] == 1
    game,b = action_fixture(); game.s.dir = 2; asked = []
    b.wall = lambda *args: asked.append(args) or 1
    b.probe = lambda *args: (-1,0)
    assert not b.place(0,b.placement_masks(),[2,1]) and asked
    for tile in (66,67,68,69):
        b.put_tile(10,10,tile); b.record(0).update(x=10,y=10)
        b.terrain_effects(0,True)
    b.put_tile(10,10,29); b.terrain_effects(0,False)
    town.put(b.chars[0],'undead',1); b.terrain_effects(0,True)
    game,b = action_fixture(); game.s.r1[0x372] = 7
    with patch.object(rules,'recalc_stats') as recalc:
        b.recalc(b.chars[0]); b.context().services['clear_weapon'](b.chars[1])
        assert [call.args for call in recalc.call_args_list] == [(b.chars[0],7),(b.chars[1],7)]

    game,b = action_fixture()
    game.s.r1[0x33E] = len(b.chars)
    del b.trigger
    effects.add_effect(b.chars[0],89,60,0xAD,False)
    cloak = effects.has_effect(b.chars[0],89)
    def arena():
        return (b.data['view'], b.data['panel'], b.data['cursor_active'], bytes(b.data['tiles']),
                [(b.position(i), b.record(i)['size'], b.record(i)['facing']) for i in range(len(b.chars))])
    entry = []
    def edge_placement(i,*args):
        b.record(i).update(x=i,y=1)
        return True
    def draw_entry(battle):
        assert battle is b and battle.data['view'] == (-3,-2)
        assert battle.data['panel'] == -1 and not battle.data['cursor_active']
        assert battle.position(1) == (1,1) and battle.record(1)['size'] == 1
        assert cloak[3] == 0xAD
        entry.append((arena(),game.s.seed))
    b.place, game.draw_combat_entry = edge_placement, draw_entry
    with patch.object(b,'trigger',wraps=b.trigger) as trigger, patch.object(game,'ask',wraps=game.ask) as ask:
        b.setup()
    assert [call.args for call in trigger.call_args_list] == [(8,0),(22,0),(8,1),(22,1),(8,2),(22,2)]
    assert cloak[3] == 0x0D and entry == [(arena(),game.s.seed)]
    assert ask.call_count == 1 and ask.call_args.kwargs['after_pause'] == game.assets.text('battleBegins')
    assert not b.data['messages'] and not getattr(game,'combat_report',[])


def check_setup_feedback():
    from unittest.mock import patch
    from .faults import BindingRequired
    from .records import Spells
    game,b = action_fixture()
    game.s.party *= 24
    b.data['actors'] = [dict(b.record(0)) for _ in range(72)]
    for c in b.chars: town.put(c,'active',0)
    calls = []
    b.die = lambda n,s,why,*args: calls.append(why) or 2
    b.begin_round()
    assert b.data['order'] == list(range(64))+list(range(71,63,-1))
    assert len(calls) == sum(min(i,64) for i in range(72)) and set(calls) == {'initiative tie'}
    game,b = action_fixture(); b.toggle_magic()
    assert b.magic_enabled and game.combat_magic
    def build_wilderness():
        assert b.data['cursor_active'] is False and b.data['cursor_size'] == 1
        b.data.update(tiles=bytearray([69]*1250))
    b.wilderness = build_wilderness
    b.place = lambda *args:True
    game.s.r0[0xE6] = 0
    game.s.r1[0x33E] = 2; game.s.r1[0x2C6] = 40; town.put(game.s.party[2],'npc',110)
    b.setup()
    assert [r['outsider'] for r in b.data['actors']] == [0,0,1] and [town.field(c,'npc') for c in game.s.party] == [0,0,168]
    game.s.g['dkk.runtime'] = dict(picture_name='PIC',picture_id=9,big_id=112,slow_text=1,loads=4)
    leader, enemy, follower = b.chars
    town.put(leader,'knight_order',3)
    town.put(leader,'abilities',20,11)
    town.put(follower,'abilities',4,3)
    seen = []
    def observe_entry(kind, options, current, **info):
        assert kind == 'ACK' and options == ('Continue',) and current.s.mode == 5
        assert not b.data['actors'] and 'tiles' not in b.data
        seen.append((current.s.g['dkk.runtime']['slow_text'], info))
        return 0
    game.player = observe_entry
    blank = (0, dict(prompt='', timed=1, message_colour=10, after_pause=game.assets.text('battleBegins'),
                     flush_keys=True, discard_pending_reads=6))
    game.s.r1[0x33E] = 8
    for level in (0,1):
        town.put(leader,'levels',level,7)
        game.s.g['dkk.runtime']['slow_text'] = 1
        seen.clear()
        b.setup()
        assert seen == ([(1, dict(prompt='Using leadership ability'))] if level else []) + [blank]
    assert not any(r['outsider'] for r in b.data['actors'])
    outsider = rules.character(bytes(follower.b))
    game.s.monsters.append(outsider)
    game.s.r1[0x33E] = 3
    seen.clear()
    with patch.object(b, 'place', side_effect=lambda i,*args: b.chars[i] is not outsider):
        b.setup()
    assert seen[-1] == (0, dict(blank[1], discard_pending_reads=7))
    assert len(b.chars) == 3 and not game.s.monsters
    assert game.s.g['dkk.runtime'] == dict(picture_name='',picture_id=255,big_id=255,slow_text=0,loads=4,
                                            dungeon_combat_loaded=0,wilderness_combat_loaded=0)
    wilderness_sheet = game.combat_tile_frames
    assert len(wilderness_sheet) == 40 and any(any(row) for row in wilderness_sheet[37])
    assert wilderness_sheet[38:] == ((bytes(24),)*24,)*2
    with patch.object(game.assets, 'records', wraps=game.assets.records) as reads:
        for dungeon, reload_tiles in ((True,True),(True,False),(False,True),(False,True),(True,True)):
            game.s.r0[0xE6] = int(dungeon)
            previous = game.combat_tile_frames
            b.setup()
            assert seen[-1][1]['flush_keys'] == reload_tiles
            assert (game.combat_tile_frames is not previous) == reload_tiles
            assert game.s.g['dkk.runtime']['dungeon_combat_loaded'] == dungeon
            assert game.combat_tile_frames[25:] == wilderness_sheet[25:]
            assert (game.combat_tile_frames[:25] != wilderness_sheet[:25]) == dungeon
        assert [call.args[0] for call in reads.call_args_list] == ['DUNGCOM','WILDCOM','WILDCOM','DUNGCOM']
    game.roll_memo = dict(effect=11,damage=3,element=8,dice_count=2); b.setup()
    assert b.data['roll'] == dict(effect=11,damage=3,element=8,dice_count=2,attack=0) and b.context(b.chars[0]).effect == 11
    b.remember_roll(b.context(b.chars[0],effect=0)); b.setup()
    assert game.roll_memo['effect'] == 0 and b.context(b.chars[0]).effect == 0 and b.context(b.chars[0]).damage == 3
    game.morale_memo = 40; b.setup()
    assert b.data['morale'] == 40 and b.context(b.chars[0]).morale == 40
    b.remember_roll(b.context(b.chars[0],morale=45)); b.setup()
    assert game.morale_memo == 45 and b.data['morale'] == 45
    was = town.field(b.chars[0],'hp'); b.panel(0); town.put(b.chars[0],'hp',was-1)
    assert b.data['panel'] == 0 and b.data['panel_hp'] == was and b.data['panel_print']['hp'] == was and not b.data['panel_due']
    assert set(b.data['panel_print']) == {'hp','hp_max','ac','active','side','level_up_ready','status','helpless','casting','weapon'}
    town.put(b.chars[0],'hp',was)
    assert b.magic_enabled and Battle(game).magic_enabled and not Battle(Game(None)).magic_enabled
    game.player = lambda *a,**k: 0; b.toggle_magic(); assert not b.magic_enabled
    game,b = action_fixture(); c = b.chars[0]
    c.b.extend(bytes(Spells.SIZE))
    town.put(c,'memorized',1,1)
    town.put(c,'npc',126); assert not b.ai_spell(0)
    town.put(c,'npc',127)
    with patch.object(b,'ai_pick_spell',return_value=0) as pick:
        assert not b.ai_spell(0)
        pick.assert_called_once_with(0)
    for difficulty,hp,maximum in ((4,205,100),(4,100,205),(5,171,171)):
        game,b = action_fixture(); template = b.chars[1]
        town.put(template,'hp',hp); town.put(template,'hp_max',maximum)
        game.s.r0[0x1F4] = difficulty
        with patch.object(game.assets,'records',side_effect=lambda stem:{7:bytes(template.b)} if stem.endswith('CHA') else {}):
            load_monsters(game,7,1,7)
        assert (town.field(game.s.monsters[0],'hp'),town.field(game.s.monsters[0],'hp_max')) == (1,1)


def check_monster_loading():
    from unittest.mock import patch
    from .records import Character, Item, Effect, Spells
    from .combat import load_creature
    game,b = action_fixture()
    raw = Character(bytes(b.chars[1].b))
    pointers = ('items_pointer','effects_pointer','next_pointer','combat_pointer','spells_pointer')
    for key in pointers: raw.set(key,0x12345678)
    raw.set('equipped_pointers',bytes(range(52)))
    raw.set('hp',40); raw.set('hp_max',80)
    items, nodes = [Item(),Item()],[Effect(),Effect()]
    for index,(item,node) in enumerate(zip(items,nodes),1):
        item.set('next_pointer',0x12345678); item.set('type',index)
        node.set('next_pointer',0x12345678); node.set('type',index)
    book = Spells(); book.set('memorized',bytes([3])+bytes(73))
    source = {'MON1CHA':{7:bytes(raw)},'MON1WIZ':{7:bytes(book)},
              'MON1ITM':{7:b''.join(bytes(item) for item in items)},
              'MON1SPC':{7:b''.join(bytes(node) for node in nodes)}}
    for dataset in (1,2,3,5):
        game = Game(None); game.s.dataset = dataset; game.s.r0[0x1F4] = 1
        seed = game.s.seed
        with patch.object(game.assets,'records',side_effect=source.__getitem__) as reads:
            load_monsters(game,7,3,9)
        assert [call.args[0] for call in reads.call_args_list] == ['MON1CHA','MON1WIZ','MON1SPC','MON1ITM']
        first,second,third = game.s.monsters
        for char in game.s.monsters:
            assert all(town.field(char,key) == 0 for key in pointers)
            assert rules.record(char).get('equipped_pointers') == bytes(range(52))
            assert (town.field(char,'hp'),town.field(char,'hp_max')) == (20,40)
            assert town.field(char,'memorized',0) == 3
            assert all(Item(item).get('next_pointer') == 0 for item in char.items)
            assert all(Effect(node).get('next_pointer') == 0 for node in char.effects)
        assert [Item(item).get('type') for item in first.items] == [1,2]
        assert [Item(item).get('type') for item in second.items] == [2,1]
        assert [Effect(node).get('type') for node in third.effects] == [2,1]
        first.items[0][0] = 99; first.effects[0][0] = 99; town.put(first,'memorized',8,0)
        assert second.items[-1][0] != 99 and third.effects[-1][0] != 99
        assert town.field(second,'memorized',0) == 3 and game.s.seed == seed
        assert game.vm.icon_slot == 9
    game = Game(None)
    with patch.object(game.assets,'records',side_effect=lambda archive:source[archive] if archive == 'MON1CHA' else {}):
        creature = load_creature(game,263)
    assert creature.rid == 7 and len(creature.b) == Character.SIZE
    assert not creature.items and not creature.effects and not game.s.monsters
    assert town.field(creature,'hp') == 40


def check_monster_counters():
    from unittest.mock import patch
    from . import combat
    game,b = action_fixture()
    raw = bytes(b.chars[1].b)
    def creature(current,ident):
        char = rules.character(raw)
        town.put(char,'undead',int(ident == 1))
        return char
    game.s.sel = 2
    with patch.object(combat,'load_creature',side_effect=creature) as reads:
        load_monsters(game,1,3,9)
        assert (game.vm.loaded_monster_count,game.vm.undead_count,game.vm.monsters_loaded,game.vm.icon_slot) == (3,1,1,9)
        game.s.monsters.pop()
        load_monsters(game,1,0,10)
        assert (len(game.s.monsters),game.vm.loaded_monster_count,game.vm.undead_count,game.vm.icon_slot) == (3,4,2,10)
        load_monsters(game,0,255,11)
        assert (len(game.s.monsters),game.vm.loaded_monster_count,game.vm.undead_count,game.vm.icon_slot) == (62,63,2,11)
        game.s.monsters.clear()
        before = reads.call_count,len(game.s.g['dkk.monster_icons']),game.s.seed
        load_monsters(game,1,2,12)
        assert (reads.call_count,len(game.s.g['dkk.monster_icons']),game.s.seed) == before
        assert not game.s.monsters and game.vm.monsters_loaded == 1 and game.vm.undead_count == 2
        party = tuple(game.s.party)
        combat.reset_monster_counters(game)
        assert (game.vm.loaded_monster_count,game.vm.undead_count,game.vm.monsters_loaded,game.vm.icon_slot) == (0,0,0,8)
        assert tuple(game.s.party) == party and game.s.sel == 2
        load_monsters(game,1,2,13)
        roster = tuple(game.s.chars()); icons = game.s.g['dkk.monster_icons'][:]
        combat.reset_monster_counters(game)
        assert tuple(game.s.chars()) == roster and game.s.g['dkk.monster_icons'] == icons and game.s.sel == 2
        load_monsters(game,0,1,14)
        assert (len(game.s.monsters),game.vm.loaded_monster_count,game.vm.undead_count,game.vm.monsters_loaded) == (3,1,0,1)
        assert town.field(game.s.monsters[-1],'order') == 8 and game.s.seed == 4660
    game,b = action_fixture()
    with patch.object(combat,'load_creature',side_effect=KeyError(7)):
        try: load_monsters(game,7,1,9)
        except KeyError: pass
        else: raise AssertionError('missing monster must not be admitted')
    assert not game.s.monsters and getattr(game.vm,'loaded_monster_count',0) == getattr(game.vm,'undead_count',0) == getattr(game.vm,'monsters_loaded',0) == 0
    for count,attempts,present,expected in ((0,0,True,False),(1,1,True,False),(2,1,True,True),(2,1,False,False)):
        game,b = action_fixture(); called=[]; game.vm.undead_count = count
        b.record(0).update(target=1,stance=1,turns=attempts)
        town.put(b.chars[0],'levels',1,0); town.put(b.chars[1],'undead',int(present))
        game.player=lambda *args,**kw:0; b.morale=lambda i:False; b.ai_item=lambda i:False
        b.ai_spell=lambda i:called.append('spell') or True
        b.turn_undead=lambda i:called.append('turn')
        b.ai(0)
        assert called == ['turn' if expected else 'spell']
        seen=[]
        game.player=lambda kind,options,current,**info:(seen.append(options),options.index('End'))[1]
        b.manual(0)
        assert ('Turn' in seen[0]) == (attempts < count)


def check_ai():
    from types import SimpleNamespace
    from unittest.mock import patch
    from . import magic
    from .records import Spells
    game,b = action_fixture(); c = b.chars[0]; c.b.extend(bytes(Spells.SIZE))
    values = (10,11,12,11,13,14,129,0)
    for at,ident in enumerate(values): town.put(c,'memorized',ident,at)
    seen = []
    b.rate_spell = lambda i,ident: seen.append(ident) or {11:128,12:255,13:1}.get(ident,0)
    rows = {ident:SimpleNamespace(combat_ok=ident!=14,ai_priority=5 if ident in (11,12) else 4) for ident in range(10,15)}
    with patch.object(magic,'spell',side_effect=lambda game,ident:rows[ident]):
        assert b.ai_pick_spell(0) == 13 and seen == [11,12,11,13]
        town.put(c,'memorized',11,2); seen.clear()
        assert b.ai_pick_spell(0) == 13 and seen == [11,13]
        b.rate_spell = lambda *args:255
        assert b.ai_pick_spell(0) == 0
    game,b = action_fixture(); c=b.chars[0]; c.b.extend(bytes(Spells.SIZE)); town.put(c,'npc',127)
    b.ai_pick_spell = lambda i:15; cast = []
    b.begin_cast = lambda *args:cast.append(args) or True
    town.put(c,'levels',64,2)
    row = magic.spell(game,15)._replace(ai_priority=3)
    with patch.object(magic,'spell',return_value=row):
        values=iter((1,3)); calls=[]
        b.die=lambda count,sides,reason,*args:calls.append(sides) or next(values)
        assert b.ai_spell(0) and cast == [(0,15,True)] and calls == [100,5]
        town.put(c,'levels',1,2); values=iter((4,)); calls.clear()
        assert not b.ai_spell(0) and calls == [100]
        values=iter((5,4)); calls.clear()
        assert not b.ai_spell(0) and calls == [100,5]
        game.s.r0[0xE5]=1; calls.clear()
        assert not b.ai_spell(0) and not calls
    game,b = action_fixture(); b.ai_pick_spell=lambda i:0
    c=b.chars[0]; c.b.extend(bytes(Spells.SIZE)); town.put(c,'npc',127)
    before=game.s.seed; assert not b.ai_spell(0) and game.s.seed == before
    assert not b.ai_item(0) and game.s.seed == (before*0x08088405+1)&0xFFFFFFFF
    game,b = action_fixture(); c=b.chars[0]; c.b.extend(bytes(Spells.SIZE)); town.put(c,'npc',127)
    b.ai_pick_spell=lambda i:15; b.begin_cast=lambda *args:True; before=game.s.seed
    row=magic.spell(game,15)._replace(ai_priority=5)
    with patch.object(magic,'spell',return_value=row): assert b.ai_spell(0)
    expected=before
    for _ in range(2): expected=(expected*0x08088405+1)&0xFFFFFFFF
    assert game.s.seed == expected and [e['sides'] for e in game.combat_log if e['event']=='dice'] == [100,5]
    game,b=action_fixture(); del b.trigger; effects.add_effect(b.chars[0],1,0,0,False)
    assert b.trigger(17,0,b.context(b.chars[0],morale=255)).morale == 4
    game,b = action_fixture(); c=b.chars[0]; town.put(c,'npc',128); town.put(c,'hp',1); town.put(c,'hp_max',100)
    town.put(c,'abilities',6,3); b.data['hostile_hp']=0; b.movement=lambda i:4 if i==0 else 20
    notices = []
    game.player = lambda kind, options, state, **info: notices.append(info['creature_text']) or 0
    b.morale(0)
    assert town.field(c,'status') == 4 and town.field(c,'hp') == 0 and not town.field(c,'active')
    assert b.record(0)['size'] == 0 and b.tile(10,10) == 23 and not b.record(0)['initiative']
    assert notices == [game.assets.text('surrenders')] and not b.data['messages']
    game,b = action_fixture(); c=b.chars[0]; town.put(c,'npc',128); b.data['hostile_hp']=0
    town.put(c,'hp',1); b.movement=lambda i:20 if i==0 else 4
    effects.add_effect(c,74,0,0,False); effects.add_effect(c,75,0,0,False)
    assert not b.morale(0) and b.record(0)['fleeing'] and {74,75}.issubset({e[0] for e in c.effects})
    held = []; game.player = lambda kind,options,state,**info: held.append((info.get('creature_text'),info.get('timed'),info.get('creature_row'))) or 0
    b.message('earlier'); b.record(0)['turned']=1; assert not b.morale(0)
    assert held == [(game.assets.text('forcedToFlee'),1,10)] and not b.data['messages'] and b.record(0)['fleeing'] == 1
    game,b=action_fixture(); r=b.record(0); r.update(casting=15,stance=1)
    town.put(b.chars[0],'auto_combat',1)
    game.player=lambda kind,options,current,**info:options.index('Manual')
    b.ai(0)
    assert (r['initiative'],r['movement'],r['casting']) == (20,12,15)
    assert not town.field(b.chars[0],'auto_combat')
    for actor in (0,1):
        outcomes = []
        for demo in (False,True):
            game,b = action_fixture()
            game.demo_mode = demo
            b.data['actor'] = actor
            town.put(b.chars[1],'npc',128)
            b.record(actor)['target'] = 1-actor
            decisions = []
            def choose(kind,options,current,**info):
                decisions.append((kind,list(options),info['actor'],current.s.seed))
                if demo: assert info['prompt'] == ''
                return options.index('Continue')
            game.player = choose
            with patch.object(b,'morale',return_value=True):
                b.ai(actor)
            options = ['Continue','Manual','Magic']
            expected = [('COMBAT_AUTO',options,actor,4660)] if demo or actor == 0 else []
            assert decisions == expected
            outcomes.append((b.record(actor)['stance'],game.s.seed))
        assert outcomes[0] == outcomes[1]
    game,b = action_fixture()
    game.demo_mode = 1
    hero,enemy,animated = b.chars
    game.s.party,game.s.monsters = [hero],[enemy,animated]
    town.put(enemy,'npc',128)
    town.put(animated,'status',1)
    for member in b.chars: town.put(member,'auto_combat',1)
    b.data['actor'] = 1
    b.record(1)['target'] = 0
    shown = []
    def toggle(kind,options,current,**info):
        if 'Magic' in options: return options.index('Magic')
        shown.append((info['prompt'],info['timed'],info['message_colour'])); return 0
    game.player = toggle
    with patch.object(b,'morale',return_value=True) as morale:
        for label in ('magicOnMsg','magicOffMsg'):
            b.ai(1)
            assert b.magic_enabled == (label == 'magicOnMsg')
            assert not b.data['messages'] and shown[-1] == (game.assets.text(label),1,10)
            assert game.assets.text(label) not in game.__dict__.get('combat_report',())
        game.player = lambda kind,options,current,**info: options.index('Manual')
        b.ai(1)
        assert [town.field(c,'auto_combat') for c in b.chars] == [0,1,1]
        assert b.record(1)['initiative'] == 6 and morale.call_count == 3
        town.put(enemy,'npc',127)
        b.ai(1)
        assert [town.field(c,'auto_combat') for c in b.chars] == [0,0,1]
        assert b.record(1)['initiative'] == 20 and morale.call_count == 3
    check_bandage()
    game,b=action_fixture(); r=b.record(0); b.record(1)['y']=15; b.put_tile(11,10,29)
    saves=[]; b.save=lambda *args:saves.append(args) or False
    assert b.ai_can_step(0,2) == (False,False) and saves == [(0,0)]
    for ident in (32,30,99,63):
        effects.add_effect(b.chars[0],ident,0,0,False); saves.clear()
        assert b.ai_can_step(0,2) == (True,False) and not saves
        b.chars[0].effects.clear()
    r['turned']=1; assert b.ai_can_step(0,2) == (True,False)
    r['turned']=0; r['movement']=255
    assert b.ai_can_step(0,2) == (True,False)
    r['movement']=12; b.put_tile(11,10,28)
    town.put(b.chars[0],'highest_level',6); saves.clear()
    assert b.ai_can_step(0,2) == (False,False) and not saves
    town.put(b.chars[0],'highest_level',7); assert b.ai_can_step(0,2) == (True,False)
    for level in (128,255):
        town.put(b.chars[0],'highest_level',level)
        assert b.ai_can_step(0,2) == (False,False)
    b.put_tile(11,10,23); r['movement']=2
    assert b.ai_can_step(0,2) == (False,False)
    r['movement']=3; assert b.ai_can_step(0,2) == (True,False)
    b.terrain=lambda tile,column=0:130; r['movement']=5
    assert b.ai_can_step(0,2) == (True,False)
    r['x']=49; assert b.ai_can_step(0,2) == (False,True)
    game,b=action_fixture(); b.record(1).update(x=12,size=2)
    assert not b.anchor_reach(0,1,1) and b.anchor_reach(0,1,2)
    b.put_tile(11,10,1); assert not b.anchor_reach(0,1,2)
    for slot,level,expected in ((0,255,'spell'),(0,128,'spell'),(3,255,'spell'),(3,2,'spell'),(0,1,'turn'),(3,3,'turn')):
        game,b=action_fixture(); called=[]; b.record(0).update(target=1,stance=1)
        town.put(b.chars[0],'levels',level,slot); town.put(b.chars[1],'undead',1)
        game.vm.undead_count = 1
        game.player=lambda *args,**kw:0; b.morale=lambda i:False; b.ai_item=lambda i:False
        b.ai_spell=lambda i:called.append('spell') or True
        b.turn_undead=lambda i:called.append('turn')
        b.ai(0)
        assert called==[expected],(slot,level,called)


def check_ai_keys():
    game,b = action_fixture()
    hero,enemy,animated = b.chars
    game.s.party,game.s.monsters = [hero],[enemy,animated]
    for member in b.chars: town.put(member,'auto_combat',1)
    town.put(enemy,'npc',128)
    town.put(animated,'status',1)
    r = b.record(1)
    b.data['actor'] = 1
    def poll_enemy():
        assert r['target'] >= 0 and r['stance'] == 0
        return ' '
    game.ai_check = poll_enemy
    b.morale = lambda i: True
    b.ai(1)
    assert [town.field(c,'auto_combat') for c in b.chars] == [0,1,1]
    assert r['initiative'] == 6 and r['stance'] > 0

    for interrupt_at_step in (False,True):
        game,b = action_fixture()
        r = b.record(0)
        town.put(b.chars[0],'auto_combat',1)
        b.record(1)['x'] = 18
        keys = iter(('2',None,' ') if interrupt_at_step else ('2',' '))
        events = []
        poll_seeds = []
        def poll():
            events.append('key')
            poll_seeds.append(game.s.seed)
            if len(events) == 1: assert r['target'] == 1
            if interrupt_at_step and len(events) == 4:
                report = game.combat_report[-1]
                assert report['kind'] == 'move' and report['still'] and report['left'] == 6
            return next(keys)
        game.ai_check = poll
        b.equip = lambda i: events.append('equip')
        shown = []; game.player = lambda kind,options,current,**info: shown.append((info.get('prompt'),info.get('timed'),info.get('message_colour'))) or 0
        b.ai(0)
        assert events == ['key','equip','key'] + (['key'] if interrupt_at_step else [])
        assert b.magic_enabled and shown[0] == (game.assets.text('magicOnMsg'),1,10)
        assert not b.data['messages']
        assert not town.field(b.chars[0],'auto_combat') and r['initiative'] == 20
        assert r['movement'] == 12 and b.position(0) == (10,10)
        assert game.s.seed == poll_seeds[-1]

    game,b = action_fixture()
    clears = []
    game.clear_combat_text = lambda battle, bottom: clears.append(
        (bottom, battle.record(0)['initiative'], list(battle.data['messages']), list(game.combat_report)))
    previous = game.assets.text('panicText')
    b.message(previous)
    town.put(b.chars[0],'auto_combat',1)
    game.ai_check = lambda: ' '
    b.ai(0)
    assert clears == [(True,20,[],[previous])]
    held = []
    game.player = lambda kind,options,current,**info:held.append((info['prompt'],info['timed'],info['message_colour'],info['after_pause'],
                                                                  b.record(0)['initiative'],b.record(0)['guard'],len(clears))) or 0
    for initiative in (0,6):
        b.record(0)['initiative'] = initiative
        b.message(previous)
        earlier = list(game.combat_report); held.clear()
        assert b.finish_ai(0)
        assert clears[-1] == (False,initiative,[],earlier)
        assert held == ([(game.assets.text('guardingText'),1,10,' ',0,1,len(clears))] if initiative else [])
        assert not b.data['messages'] and game.combat_report == earlier


def attack_rolls(battle, values):
    original, values = battle.die, iter(values)
    def die(count, sides, reason, *actors):
        result = original(count,sides,reason,*actors)
        return next(values) if reason == 'attack' else result
    battle.die = die


def check_movement_order():
    from unittest.mock import patch
    for automatic in (False,True):
        for fallen in (False,True):
            game,b = action_fixture(); r = b.record(0); c = b.chars[0]
            r.update(casting=15,guard=1); b.record(1).update(x=12,guard=1)
            b.record(2).update(x=15)
            seen = []
            def guard(i,j):
                assert (i,j) == (1,0) and b.position(j) == (11,10)
                if fallen: town.put(c,'active',0)
                else: effects.add_effect(c,31,0,0,False)
            b.attack = guard
            b.terrain_effects = lambda i,moved:seen.append((moved,r['movement'],r['initiative'],r['casting'],r['guard']))
            assert b.move(0,2,ai=automatic)
            assert seen == [(True,0,0 if automatic or fallen else 6,0 if automatic or fallen else 15,0 if automatic or fallen else 1)]
            assert (r['initiative'],r['movement'],r['casting'],r['guard']) == (0,0,0,0)
            assert not b.record(1)['guard'] and game.s.seed == 4660
        game,b = action_fixture(); r = b.record(0); c = b.chars[0]
        r.update(casting=15,guard=1); b.record(1).update(x=14); b.record(2).update(x=15)
        def terrain(i,moved):
            assert moved and r['initiative'] == 6 and r['casting'] == 15
            effects.add_effect(c,31,0,0,False)
        b.terrain_effects = terrain; had = r['movement']
        assert b.move(0,2,ai=automatic)
        assert game.combat_report[-1]['kind'] == 'move' and game.combat_report[-1]['left'] == (had>>1 if automatic else None)
        assert (r['initiative'],r['casting'],r['guard']) == ((6,15,1) if automatic else (0,0,0))
        assert game.s.seed == 4660
        game,b = action_fixture(); r = b.record(0); b.record(1).update(x=14); b.record(2).update(x=15)
        visited = []
        def opportunity(i,direction):
            town.put(b.chars[i],'active',0)
        b.opportunity = opportunity
        b.terrain_effects = lambda *args,**kwargs:visited.append(True)
        assert b.move(0,2,ai=automatic)
        assert b.position(0) == (10,10) and r['initiative'] == 0 and not visited
        for saved in (False,True):
            game,b = action_fixture(); del b.trigger
            b.record(1).update(x=14); b.record(2).update(x=15); b.put_tile(11,10,29)
            c = b.chars[0]; town.put(c,'saves',0 if saved else 255)
            with patch.object(rules,'recalc_stats'):
                assert b.move(0,2,ai=automatic)
            assert effects.has(c,30 if saved else 31)
            assert b.record(0)['initiative'] == (6 if saved else 0)
            seed = 4660
            for _ in range(2): seed = (seed*0x08088405+1)&0xFFFFFFFF
            assert game.s.seed == seed
    game,b = action_fixture(); b.record(0).update(target=1,stance=1); b.record(1).update(x=14)
    b.data.update(last_direction=8,stuck=0); calls = []; move = b.move
    def moved(i,direction,ai=False):
        calls.append(ai)
        return move(i,direction,ai=ai)
    b.move = moved; b.ai_step(0)
    assert calls == [True]
    steps = [entry for entry in game.combat_report if isinstance(entry,dict) and entry['kind'] == 'move']
    assert [(entry.get('still',False),entry['left']) for entry in steps] == [(True,6),(False,6)]

    game,b = action_fixture()
    town.put(b.chars[0],'class',5)
    b.record(0).update(movement=9,target=1)
    held = []; game.player = lambda kind,options,current,**info:held.append(info['prompt']) or 0
    assert b.ai_step(0)
    prompt, = game.combat_report
    assert (prompt['kind'],prompt['actor'],prompt['left'],prompt['still']) == ('move',0,4,True)
    assert held == [game.assets.text('guardingText')] and b.position(0) == (10,10) and game.s.seed == 4660


def check_actions():
    from unittest.mock import patch
    from . import combat
    with patch.object(rules,'recalc_stats',lambda c,party_adjust=0:None):
        for rolls,hits,shown in (([1,1],[False,False],1),([20,1],[True,False],1),([20,20],[True,True],2)):
            game,b = action_fixture(); attack_rolls(b,rolls); b.attack(0,1)
            assert [e['hit'] for e in game.combat_log if e['event'] == 'attack'] == hits
            assert b.data['hits_made'] == sum(hits) and b.data['hits_made_secondary'] == 0 and b.data['attacks_made'] == [2,0]
            frames = [e for e in game.combat_report if isinstance(e,dict) and e['kind'] == 'attack']
            assert len(frames) == shown and all((e['actor'], e['facing']) == (0, 2) for e in frames)
            assert sum(' misses ' in message for message in b.data['messages']) == int(not any(hits))
            seed = 4660
            for _ in range(2+sum(hits)): seed = (seed*0x08088405+1)&0xFFFFFFFF
            assert game.s.seed == seed
        game,b = action_fixture(); attack_rolls(b,[20,1]); trigger = b.trigger
        def paralyze(condition,i,context=None):
            if condition == 2: effects.add_effect(b.chars[1],31,0,0,False)
            return trigger(condition,i,context)
        b.trigger = paralyze; b.attack(0,1)
        assert [e['hit'] for e in game.combat_log if e['event'] == 'attack'] == [True,True]
        assert len([e for e in game.combat_log if e.get('reason') == 'attack']) == 2
        game,b = action_fixture(); attack_rolls(b,[20,20]); a = b.chars[0]
        town.put(a,'attacks_left',2,1); town.put(a,'attacks_left',1); b.record(0)['phase'] = 1
        town.put(a,'damage_rolls',1,1); town.put(a,'damage_dice',6,1)
        trigger = b.trigger
        def retaliation(condition,i,context=None):
            if condition == 3: town.put(a,'active',0)
            return trigger(condition,i,context)
        b.trigger = retaliation; b.attack(0,1)
        assert [e['phase'] for e in game.combat_log if e['event'] == 'attack'] == [1,0]
        game,b = action_fixture(); town.put(b.chars[0],'attacks_left',0); b.attack(0,1)
        assert b.record(0)['attacked'] == 0 and game.s.seed == 4660
        game,b = action_fixture(); effects.add_effect(b.chars[1],31,0,0,False)
        town.put(b.chars[1],'hp',253); b.attack(0,1)
        assert town.field(b.chars[1],'hp') == 251 and game.s.seed == 4660
        assert not any(town.field(b.chars[0],'attacks_left',p) for p in (0,1))
        game,b = action_fixture(); attack_rolls(b,[1,1]); item = bytearray(combat.Item.SIZE); item[combat.I['type']] = 66
        b.weapon = lambda i:item if i == 0 else None
        b.attack(0,1)
        assert len([e for e in game.combat_log if e['event'] == 'attack']) == 2
        game,b = action_fixture(); attack_rolls(b,[20,20]); trigger = b.trigger
        def remove_target(condition,i,context=None):
            if condition == 5: town.put(b.chars[1],'active',0)
            return trigger(condition,i,context)
        b.trigger = remove_target; b.attack(0,1)
        assert not getattr(game,'combat_report',[]) and town.field(b.chars[1],'hp') == 250
        assert len([e for e in game.combat_log if e['event'] == 'attack']) == 1
        game,b = action_fixture(); town.put(b.chars[0],'attacks_left',1); town.put(b.chars[0],'damage_bonus',254)
        b.die = lambda count,sides,reason,*a:20 if reason == 'attack' else 1
        seen = []; trigger = b.trigger
        def inspect_damage(condition,i,context=None):
            if condition in (4,5): seen.append(context.damage)
            return trigger(condition,i,context)
        b.trigger = inspect_damage; b.attack(0,1)
        assert seen == [255,255]
    check_targeting()
    check_departure()
    check_turn_results()
    check_spell_locks()
    check_spell_ratings()
    check_leadership()
    check_effect_integration()
    check_combat_loop()
    check_combat_menu()
    check_reviewed_actions()
    game,b = action_fixture(); b.data['multi_target'] = 1; b.data['save_passed'] = True
    b.remember_roll(effects.Roll(dice_count=3))
    x = b.context(b.chars[0]); assert (x.multi_target,x.save_passed,x.dice_count) == (1,True,3)
    for face,passed in ((1,False),(20,True),(10,True)):
        b.die = lambda *a:face; assert b.save(0,0) == passed and b.context().save_passed == passed
    game,b = action_fixture(); b.kill(1,8,'gone')
    assert b.record(1)['size'] == 0 and b.tile(11,10) == 31
    with patch.object(Battle,'treasure') as run_treasure:
        combat.treasure(game)
        run_treasure.assert_called_once_with()
        assert game.current_battle is None
    game,b = action_fixture(); b.record(1).update(flanks=255,spread=7); b.note_direction(0,1)
    assert b.record(1)['flanks'] == 0 and 0 <= b.record(1)['spread'] < 8
    game,b = action_fixture()
    for c in b.chars: town.put(c,'side',1)
    game.s.party *= 5; b.hp_percent()
    assert b.data['hostile_hp'] == ((3750*20)&65535)//3825*5
    for c in b.chars: town.put(c,'side',0)
    b.data['hostile_hp'] = 35; b.hp_percent(); assert b.data['hostile_hp'] == 35


def check_targeting():
    game,b = action_fixture(); calls = []; b.record(0)['target'] = 2
    def veto(condition,i,context=None):
        calls.append((condition,i,b.record(0)['target']))
        if condition == 1: context.target_veto = True
        return context
    b.trigger = veto
    assert b.can_target(0,0,False) and not b.can_target(0,-1) and not b.can_target(0,None)
    assert not calls and not b.can_target(0,1) and calls == [(1,1,2)]
    calls.clear()
    def accepted(condition,i,context=None):
        calls.append((condition,i,b.record(0)['target']))
        return context
    b.trigger = accepted
    assert not b.can_target(0,2,False) and calls == [(1,2,2)]
    calls.clear(); assert b.can_target(0,1) and calls == [(1,1,2),(0,0,1)] and b.record(0)['target'] == 2
    b.record(1)['x'] = 13; b.record(2)['x'] = 11
    town.put(b.chars[2],'side',1)
    base = bytearray(16); base[12] = 3
    b.base = lambda item:base; b.ranged = lambda i:True; b.throwable = lambda i:True; b.ammo = lambda i:(True,None)
    assert 1 in b.attack_targets(0)
    b.throwable = lambda i:False; assert not b.attack_targets(0)
    game,b = action_fixture(); calls = []
    game.player = lambda kind,options,current,**info:(calls.append(info),1)[1]
    assert not b.confirm_ally(0,2) and calls[-1]['start'] == 1 and not game.s.r1[0x333]
    game.player = lambda *a,**kw:0; town.put(b.chars[2],'npc',128)
    assert b.confirm_ally(0,2) and game.s.r1[0x333] == 1 and town.field(b.chars[2],'side') == 0
    game,b = action_fixture(); b.record(0)['target'] = 1; before = game.s.seed
    assert b.acquire(0) and game.s.seed == before
    assert b.acquire(0,force=True,allies=True) and game.s.seed != before
    assert town.field(b.chars[b.record(0)['target']],'side') == 0
    town.put(b.chars[2],'active',0)
    assert b.count_targets(0,same_side=True) == [0,2] and b.count_targets(0) == [1]
    assert b.chars[2] in b.context().call('neighbours',b.chars[1])
    assert 2 in b.area_targets(11,10,1)
    b.record(2)['size'] = 0
    assert b.chars[2] not in b.context().call('neighbours',b.chars[1])
    assert 2 not in b.area_targets(11,10,1)
    b.record(2)['size'] = 1
    effects.add_effect(b.chars[0],91,0,0,False); b.data['yell'] = 2
    assert b.count_targets(0,same_side=True) == [2,0]
    assert b.data['target_list'] == [0,2,2]
    b.record(1)['size'] = b.record(2)['size'] = 0
    assert b.count_targets(0) == [] and b.data['target_list'] == [0,2,2]
    from . import effects_handlers
    effects_handlers.berserk(game,b.chars[0],bytes((77,0,0,0)),False,b.context(b.chars[0]))
    assert b.record(0)['target'] == 2


def check_spell_target_contract():
    from unittest.mock import patch
    from . import effects_handlers, magic
    from .faults import BindingRequired
    for saved,reduction,damage in ((False,0,12),(True,2,6),(True,1,0)):
        game,b = action_fixture(); del b.trigger
        caster,target,other=b.chars
        game.spell_targets=[target,other,target,None]
        held=game.spell_targets
        effects.add_effect(target,71,0,0,False)
        effects.add_effect(target,98,0,0,False)
        effects.add_effect(caster,75,0,0,False)
        effects.add_effect(caster,71,0,0,False)
        seen=[]
        def redirect(facade,char,node,removed,roll):
            seen.append(char)
            b.trigger(255,2,roll)
            roll.call('replace_spell_targets',char,caster)
            roll.call('redirect_target',caster)
        context=b.context(caster,damage=6,element=2)
        with patch.dict(effects_handlers.HANDLERS,{71:redirect}):
            assert b.spell_damage(target,context,reduction,saved) is caster
        assert seen==[target] and context.target is caster
        assert game.spell_targets is held and held==[caster,other,caster,None]
        assert town.field(caster,'hp')==250-damage and town.field(target,'hp')==250
        assert 'redirect_target' not in context.services and game.s.seed==4660
    for saved,negates,blocked in ((False,0,False),(True,1,False),(False,0,True)):
        game,b=action_fixture(); del b.trigger
        caster,target,other=b.chars
        game.spell_targets=[target]
        effects.add_effect(target,71,0,0,False)
        effects.add_effect(caster if blocked else target,99,0,0,False)
        def redirect(facade,char,node,removed,roll): roll.call('redirect_target',caster)
        with patch.dict(effects_handlers.HANDLERS,{71:redirect}):
            b.add_with_message(1,55,7,3,False,'',saved,negates)
        assert effects.has(caster,55)==(not saved and not blocked)
        assert not effects.has(target,55) and game.s.seed==4660
    game,b=action_fixture(); del b.trigger
    caster,target,other=b.chars
    context=b.context(caster)
    callback=lambda char:None
    context.services['redirect_target']=callback
    effects.add_effect(target,71,0,0,False)
    def fail(*args): raise BindingRequired('Unbound spell animation')
    with patch.dict(effects_handlers.HANDLERS,{71:fail}):
        try: b.trigger(9,1,context)
        except BindingRequired: pass
        else: raise AssertionError('missing spell animation accepted')
    assert context.services['redirect_target'] is callback
    game,b=action_fixture()
    caster,target,other=b.chars
    game.player=lambda *args,**kwargs:0
    b.spell_targets=lambda *args:[1,2,1]
    b.data['aim']=b.position(1)
    observed=[]
    def body(facade,char,targets,row):
        assert targets is game.spell_targets and facade.spell_targets is targets
        b.context(caster).call('replace_spell_targets',target,caster)
        observed.extend(targets)
    with patch.object(magic,'handler',return_value=body): assert b.cast(0,15,using_item=True)
    assert observed==[caster,other,caster] and game.s.seed==4660
    twin=rules.character(bytes(target.b))
    game.spell_targets=[target,twin,target]
    b.replace_spell_targets(target,caster)
    assert game.spell_targets[0] is caster and game.spell_targets[1] is twin and game.spell_targets[2] is caster


def check_effect_messages():
    from .combat import name
    from .records import Spells
    for amount,status,key in ((5,4,'goesDown'),(6,5,'dyingSuffix'),(15,6,'killedMessage')):
        for concealed in (False,True):
            game,b = action_fixture(); del b.trigger
            c = b.chars[1]; town.put(c,'hp',5); town.put(c,'target_flags',8 if concealed else 0)
            text = game.assets.text
            expected = text('goesDown') if concealed or status == 4 else text('goesDown')+text(key) if status == 5 else text(key)
            removed = []
            strip = b.strip
            def observe(i):
                removed.append((town.field(c,'hp'),town.field(c,'status'),game.combat_report[-1]))
                strip(i)
            b.strip = observe
            b.spell_damage(c,b.context(b.chars[0],damage=amount,element=8),0,False)
            assert removed == [(0,status,name(c)+' '+expected)]
            assert b.record(1)['size'] == 0 and b.tile(11,10) == 31
            assert len(game.combat_report) == 3 and game.combat_report[-1]['kind'] == 'fall'
            assert game.s.seed == 4660
    game,b = action_fixture(); del b.trigger
    game.s.party[1] = rules.character(bytes(b.chars[1].b),spells=bytes(Spells()))
    c = b.chars[1]; town.put(c,'hp',5); town.put(c,'memorized',15)
    b.record(1)['casting'] = 15
    observed = []
    message = b.message
    def capture(text,report=True):
        observed.append((text,town.field(c,'hp'),town.field(c,'active')))
        message(text,report)
    b.message = capture
    b.spell_damage(c,b.context(b.chars[0],damage=6,element=8),0,False)
    assert observed[1] == (name(c)+' '+game.assets.text('lostSpellMessage'),0,0)
    assert town.field(c,'memorized') == 143 and b.record(1)['casting'] == 0
    for status in (0,6,7,8):
        game,b = action_fixture(); del b.trigger
        c = b.chars[1]; town.put(c,'status',status)
        removed = []; original = b.strip
        def observe(i):
            removed.append((game.combat_report[:],town.field(c,'hp'),town.field(c,'status')))
            original(i)
        b.strip = observe
        b.kill(1,8,game.assets.text('killedMessage'))
        expected = [name(c)+' '+game.assets.text('killedMessage')]
        if status == 0:
            assert game.combat_report[:-1] == expected and game.combat_report[-1]['kind'] == 'fall'
        else:
            assert game.combat_report == expected
        assert removed == ([(expected,0,8)] if status == 0 else [])
        assert town.field(c,'hp') == (0 if status == 0 else 250)
        assert b.record(1)['size'] == (0 if status == 0 else 1)
    game,b = action_fixture(); del b.trigger
    b.save = lambda *args:False
    b.weapon_effect(b.chars[0],106,None,False,b.context(b.chars[0]))
    assert effects.has(b.chars[1],108)
    assert game.combat_report[-1] == name(b.chars[1])+' '+game.assets.text('blindedBySmokeText')
    b.add_with_message(1,108,0,0,True,'',True,1)
    assert game.combat_report[-1] == name(b.chars[1])+' '+game.assets.text('unaffectedMessage')


def check_timed_effects():
    from .combat import name
    for kind,count in ((67,1),(68,2)):
        game,b = action_fixture(); del b.trigger
        c = b.chars[1]; r = rules.record(c)
        c.b[rules.F['abilities']:rules.F['abilities']+12] = bytes([10]*12)
        for key,value in (('hp',20),('hp_max',25),('hp_rolled',25),('experience',9000)):
            r.set(key,value)
        town.put(c,'levels',4,2)
        b.record(0)['target'] = 1
        effects.add_effect(b.chars[0],kind,0,0,False)
        before = bytes(c.b),game.s.seed
        observed = []
        def answer(action,options,current,**info):
            observed.append((action,options,info,bytes(c.b),current.s.seed,current.combat_report[:]))
            return 0
        game.player = answer
        b.trigger(2,0,b.context(b.chars[0]))
        message = name(c)+' '+game.assets.text('drainedText')
        assert observed == [('ACK',('Continue',),dict(actor=0,round=1,prompt=message,timed=1),*before,[message])]
        assert town.field(c,'levels',2) == 4-count and town.field(c,'former_levels',2) == 4
        assert town.field(c,'hp') < 20 and town.field(c,'hp_max') < 25
        seed = before[1]
        for _ in range(2*count): seed = (seed*0x08088405+1)&0xFFFFFFFF
        assert game.s.seed == seed
        b.record(0)['target'] = -1
        b.trigger(2,0,b.context(b.chars[0]))
        assert len(observed) == 1 and game.s.seed == seed
    for level,saved in ((0,False),(4,False),(5,False),(5,True),(6,False),(6,True),(7,False)):
        game,b = action_fixture(); del b.trigger
        c = b.chars[0]; town.put(c,'highest_level',level); town.put(c,'saves',0 if saved else 255)
        b.put_tile(10,10,28)
        before = bytes(c.b)
        observed = []
        def answer(action,options,current,**info):
            observed.append((action,options,info,bytes(c.b),bool(effects.has(c,55)),b.record(0)['size'],current.s.seed))
            return 0
        game.player = answer
        b.terrain_effects(0,False)
        seed = (4660*0x08088405+1)&0xFFFFFFFF if level in (5,6) else 4660
        assert game.s.seed == seed
        if level > 6 or saved:
            assert not observed and bytes(c.b) == before and not effects.has(c,55)
        else:
            message = name(c)+' '+game.assets.text('poisonedMessage')
            assert observed[:1] == [('ACK',('Continue',),dict(actor=0,round=1,prompt=message,timed=1),before,False,1,seed)]
            assert len(observed) == 3 and observed[1][2]['fall'] == 1
            assert observed[2][2]['timed'] == 1 and observed[2][2]['creature_text'] == game.assets.text('killedMessage')
            assert town.field(c,'hp') == 0 and town.field(c,'status') == 6 and not town.field(c,'active')
            assert effects.has(c,55) and b.record(0)['size'] == 0 and b.tile(10,10) == 28
            assert game.combat_report[:-1] == [message,name(c)+' '+game.assets.text('killedMessage')]
            assert (game.combat_report[-1]['kind'],game.combat_report[-1]['actor']) == ('fall',0)


def check_area_integration():
    from unittest.mock import patch
    from . import effects_area
    game,b = action_fixture()
    b.data['clouds'] = [dict(cells=[(10,10,24)],terrain=29,countdown=2),
                        dict(cells=[(10,10,31)],terrain=28,countdown=1)]
    b.data.update(downed=[(10,10,25)],downed_who=[2],downed_count=1)
    effects_area.refresh_area(b)
    assert b.resolve_terrain(10,10) == 31
    b.down(0)
    assert b.body_state()[0][1] == (10,10,31) and b.tile(10,10) == 28
    effects_area.count_down_area(b)
    assert len(b.data['clouds']) == 1 and b.tile(10,10) == 29
    effects_area.count_down_area(b)
    assert not b.data['clouds'] and b.tile(10,10) == 31
    assert game.combat_report[0]['kind'] == 'fall'
    assert game.combat_report[1:] == [game.assets.text('explosionMessage')]*2
    for saved in (False,True):
        game,b = action_fixture(); del b.trigger
        c = b.chars[0]; b.put_tile(10,10,29); b.data.update(view=(0,0),actor=2,gfx=False)
        game.s.sel = 1; town.put(c,'saves',0 if saved else 255)
        seed = game.s.seed
        b.terrain_effects(0,False)
        assert game.s.seed == seed and not c.effects and b.data['view'] == (0,0)
        with patch.object(rules,'recalc_stats'):
            b.terrain_effects(0,True)
        node = effects.has_effect(c,30 if saved else 31)
        assert node is not None and 2 <= node[1] <= 5
        for _ in range(2): seed = (seed*0x08088405+1)&0xFFFFFFFF
        assert game.s.seed == seed and b.data['view'] == (7,7)
        assert (b.data['actor'],game.s.sel) == (2,1)
        if saved: assert not b.record(0)['cast_ok'] and not b.record(0)['item_ok']
        assert b.record(0)['initiative'] == (6 if saved else 0)
    game,b = action_fixture(); b.data['limit'] = 1
    b.data['clouds'] = [dict(cells=[(10,10,23)],terrain=28,countdown=1)]
    effects_area.refresh_area(b)
    b.begin_round = lambda:b.data.update(order=[],cursor=0)
    seen = []
    def trigger(condition,i,context=None):
        if condition == 19: seen.append((b.data['round'],b.tile(10,10),len(b.data['clouds'])))
        return context or b.context(b.chars[i])
    b.trigger = trigger
    def advance(*args):
        assert b.data['round'] == 1 and b.tile(10,10) == 28 and b.data['clouds']
    with patch.object(effects,'advance',advance): b.turns()
    assert seen == [(2,23,0)]*3 and town.field(b.chars[0],'active')


def check_effect_integration():
    from unittest.mock import patch
    from . import combat
    game,b = action_fixture(); del b.trigger
    c = b.chars[0]; town.put(c,'saves',9); town.put(c,'save_bonus',127)
    b.die = lambda *a:10
    assert not b.save(0,0,127)
    town.put(c,'save_bonus',129); b.die = lambda *a:2
    assert b.save(0,0)
    game,b = action_fixture(); del b.trigger
    effects.add_effect(b.chars[0],57,0,0,False)
    before = game.s.seed
    assert not b.save(0,0) and game.s.seed == (before*0x08088405+1)&0xFFFFFFFF
    game,b = action_fixture(); del b.trigger
    effects.add_effect(b.chars[1],41,0,0,False)
    b.record(1)['x'] = 14
    item = bytearray(combat.Item.SIZE)
    b.weapon = lambda i:item if i == 0 else None
    b.ammo = lambda i:(True,item if i == 0 else None)
    town.put(b.chars[0],'attacks_left',1); attack_rolls(b,[20])
    with patch.object(rules,'recalc_stats',lambda c,party_adjust=0:None): b.attack(0,1)
    assert town.field(b.chars[1],'hp') == 250 and b.data['hits_made'] == 0
    seed = 4660
    for _ in range(3): seed = (seed*0x08088405+1)&0xFFFFFFFF
    assert game.s.seed == seed
    game,b = action_fixture(); held = []
    game.player = lambda kind,options,current,**info:held.append((info['prompt'],info['timed'],info['message_colour'],info['after_pause'])) or 0
    assert b.end(0,True)
    assert b.record(0)['guard'] == 1 and not b.data['messages'] and held == [(game.assets.text('guardingText'),1,10,' ')]
    held.clear(); b.record(0)['turned'] = 1; b.end(0,True)
    assert b.record(0)['guard'] == 0 and not b.data['messages'] and not held


def check_combat_loop():
    from unittest.mock import patch
    game,b = action_fixture(); b.data.update(limit=15,actor=2)
    turns,conditions,terrain = [],[],[]
    def begin():
        b.data.update(order=[0,1,2],cursor=0)
        for r in b.data['actors']: r['initiative'] = 6
    def act(i):
        turns.append((b.data['round'],i))
        town.put(b.chars[1],'active',0)
        b.end(i)
    def trigger(condition,i,context=None):
        conditions.append((condition,i,b.data['actor']))
        return context or b.context(b.chars[i])
    prompts = []
    def choose(kind,options,current,**info):
        prompts.append(info)
        return int(len(prompts)>1)
    b.begin_round,b.manual,b.trigger = begin,act,trigger
    b.terrain_effects = lambda i,moved=False:terrain.append((i,moved))
    game.player = choose
    with patch.object(effects,'advance'),patch.object(rules,'recalc_stats'):
        b.turns()
    assert turns == [(1,0),(2,0),(2,1),(2,2)]
    assert conditions[3] == (7,0,2)
    assert len(terrain) == 6 and all(not moved for _,moved in terrain)
    assert all(p['start'] == 1 and p['prompt'] == game.assets.text('continueBattle') for p in prompts)
    game,b = action_fixture(); town.put(b.chars[1],'active',0)
    seen = []
    def entry(condition,i,context=None):
        seen.append(condition)
        town.put(b.chars[1],'active',1)
    b.trigger = entry; b.begin_round = lambda:(_ for _ in ()).throw(AssertionError('empty side snapshot lost'))
    b.turns(); assert seen == [24,24,24]
    for counter,expected,status in ((9,10,6),(255,0,5)):
        game,b = action_fixture(); b.data.update(limit=255,round=255)
        town.put(b.chars[2],'status',5); town.put(b.chars[2],'active',0); b.record(2)['overkill'] = counter
        b.begin_round = lambda:b.data.update(order=[],cursor=0)
        warned = []
        def answer(kind,options,current,**info):
            if tuple(options) != ('Continue',): return 1
            warned.append((info['prompt'],info['timed'],info['message_colour'],info['after_pause'],
                           town.field(b.chars[2],'status'),b.record(2)['overkill'],b.data['round']))
            return 0
        game.player = answer
        b.teams = lambda:(1,0)
        def start(condition,i,context=None):
            if condition == 24: b.teams = lambda:(1,1)
            if condition == 19: b.teams = lambda:(1,0)
            return context or b.context(b.chars[i])
        b.trigger = start
        b.teams = lambda:(1,1)
        with patch.object(effects,'advance'): b.turns()
        assert b.data['round'] == 0 and b.record(2)['overkill'] == expected and town.field(b.chars[2],'status') == status
        assert warned == ([(game.assets.text('teammateDying'),1,10,' ',5,0,0)] if status == 5 else [])
        assert game.assets.text('teammateDying') not in b.data['messages'] and game.s.seed == 4660


def check_bandage():
    for manual in (True,False):
        game,b = action_fixture(); r = b.record(0); r.update(target=1,stance=1); b.equip = lambda i:None
        town.put(b.chars[2],'status',5); town.put(b.chars[2],'active',0); b.record(2)['overkill'] = 4
        seen = []
        def answer(kind,options,current,**info):
            if 'Bandage' in options: return options.index('Bandage')
            if 'creature_text' in info:
                seen.append((info['creature_text'],info['timed'],info['prompt'],info['creature_name'],info['creature_colour'],
                             town.field(b.chars[2],'status'),b.record(2)['overkill'],r['initiative']))
            return 0
        game.player = answer
        game.clear_combat_text = lambda battle,bottom:seen.append(('clear',bottom,tuple(battle.data['messages'])))
        b.manual(0) if manual else b.ai(0)
        held = (game.assets.text('bandageText'),1,'','TEST',12,4,0,6)
        assert seen[seen.index(held):] == [held,('clear',False,())]
        assert town.field(b.chars[2],'status') == 4 and town.field(b.chars[2],'active') == 0
        assert (r['initiative'],r['movement'],game.s.seed) == ((0,0,4660) if manual else (0,12,1231448858))
        assert not any(game.assets.text('bandageText') in str(e) for e in getattr(game,'combat_report',()))


def check_timed_texts():
    from unittest.mock import patch
    from . import magic
    for turned,expected in ((0,1),(1,0)):
        game,b = action_fixture(); held = []
        game.player = lambda kind,options,current,**info: (held.append((info['creature_text'],info['timed'],info['creature_column'],info['creature_row'],tuple(b.data['messages']))) if 'creature_text' in info else None) or 0
        game.clear_combat_text = lambda battle,bottom: held.append(('clear',bottom))
        b.morale = lambda i: b.record(i).update(fleeing=1,turned=turned) or True
        b.ai(0)
        panic = (game.assets.text('panicText'),1,23,10,('TEST'+' '+game.assets.text('panicText'),))
        assert held == [('clear',True)] + ([panic,('clear',False)] if expected else []) and not b.data['messages']
    game,b = action_fixture(); seen = []
    game.player = lambda kind,options,current,**info: seen.append((kind,info.get('creature_text'),info.get('prompt'),info.get('timed'))) or 0
    game.clear_combat_text = lambda battle,bottom: seen.append(('clear',bottom,tuple(battle.data['messages'])))
    b.message('earlier'); b.spell_targets = lambda *args: seen.append('aim')
    with patch.object(magic,'handler',return_value=lambda *args:None): assert not b.cast(0,1,ai=True)
    assert seen == [('ACK',game.assets.text('castsSpellText'),'',1),('clear',False,()),'aim',('ACK',None,game.assets.text('spellAbortedText'),1)]
    game,b = action_fixture(); seen = []
    b.ranged = lambda i: True; b.throwable = lambda i: False; b.ammo = lambda i: (True,None)
    words = iter(('Move','east','Done','End'))
    def player(kind,options,current,**info):
        seen.append((kind,info.get('prompt')))
        return options.index(next(words))
    game.player = player; b.manual(0)
    moves = [prompt for kind,prompt in seen if kind == 'COMBAT_MOVE']
    assert moves == ['',game.assets.text('notWithWeapon')] and not b.data['messages']
    assert b.position(0) == (10,10) and town.field(b.chars[1],'hp') == 250 and game.s.seed == 4660


def check_round_finish():
    from unittest.mock import patch
    for demo in (None,0,1,2):
        for survivor in (0,1,None):
            game,b = action_fixture(); b.data.update(limit=2,view=(43,18),gfx=False)
            if demo is not None: game.demo_mode = demo
            b.begin_round = lambda:b.data.update(order=[],cursor=0)
            stages = []
            def terrain(i,moved=False):
                stages.append(('terrain',i))
                if survivor is not None and town.field(b.chars[i],'side') != survivor:
                    town.put(b.chars[i],'active',0)
                if survivor == 0 and i == 2:
                    town.put(b.chars[i],'active',0); town.put(b.chars[i],'status',5)
            b.terrain_effects = terrain
            teams,scroll = b.teams,b.scroll
            def count():
                found = teams()
                stages.append(('teams',found))
                return found
            def refresh(x,y,margin=2,direction=8):
                assert stages[-1] == ('teams',teams())
                assert all(('terrain',i) in stages for i in range(3))
                assert (x,y,margin,direction) == (46,21,255,8)
                assert b.data['round'] == 2
                assert stages.count(('dying',)) == (stages[-2] == ('dying',)) == (survivor == 0)
                assert game.assets.text('teammateDying') not in b.data['messages']
                changed = scroll(x,y,margin,direction)
                stages.append(('refresh',changed))
                return changed
            def choose(kind,options,current,**info):
                if info.get('prompt') == game.assets.text('teammateDying'):
                    assert tuple(options) == ('Continue',) and (info['timed'],info['message_colour'],info['after_pause']) == (1,10,' ')
                    assert stages[-1] == ('terrain',2) and b.data['round'] == 2
                    stages.append(('dying',))
                    return 0
                assert survivor == 0 and not demo and stages[-1] == ('refresh',True)
                assert info['prompt'] == game.assets.text('continueBattle') and info['start'] == 1
                stages.append(('confirm',tuple(options)))
                return 1
            b.teams,b.scroll,game.player = count,refresh,choose
            seed = game.s.seed
            with patch.object(effects,'advance'): b.turns()
            assert stages.count(('refresh',True)) == 1
            assert sum(s[0] == 'confirm' for s in stages) == int(survivor == 0 and not demo)
            assert b.data['view'] == (43,18) and game.s.seed == seed
    game,b = action_fixture(); b.data.update(limit=1); b.begin_round = lambda:b.data.update(order=[],cursor=0)
    game.s.monsters = [game.s.party.pop()]; b.terrain_effects = lambda i,moved=False:None
    for c in b.chars: effects.add_effect(c,31,2,255,False)
    aged = []; real = effects.age_effects
    with patch.object(effects,'age_effects',lambda g,c,m:(aged.append(b.chars.index(c)),real(g,c,m))[1]): b.turns()
    assert sorted(aged) == [0,1,2] and all(int.from_bytes(c.effects[0][1:3],'little') == 1 for c in b.chars)


def check_combat_menu():
    from unittest.mock import patch
    from . import inventory, magic
    from .records import Spells
    from .faults import BindingRequired
    game,b = action_fixture(); seen = []; game.s.g['dkk.delay'] = 1
    choices = iter(('Faster','Slower','Exit'))
    def speed(kind,options,current,**info):
        seen.append((tuple(options),info['query']))
        return options.index(next(choices))
    game.player = speed; b.speed_menu()
    assert seen[0][0] == ('Faster','Slower','Exit') and seen[1][0] == ('Slower','Exit')
    assert game.s.g['dkk.delay'] == game.s.r0[0xFC] == 1
    game.s.g['dkk.delay'] = 9; game.player = lambda kind,options,current,**info:(seen.append((tuple(options),info)),options.index('Exit'))[1]
    b.speed_menu(); assert seen[-1][0] == ('Faster','Exit')
    game,b = action_fixture(); seen = []; b.chars[0].b.extend(bytes(Spells.SIZE)); town.put(b.chars[0],'memorized',128)
    for c in b.chars: town.put(c,'auto_combat',1)
    town.put(b.chars[1],'npc',128)
    choices = iter(('space','Alt-m','Alt-m','Alt-r','End'))
    held = []
    def manual(kind,options,current,**info):
        if kind == 'ACK': held.append((info['prompt'],info['timed'],info['message_colour'])); return 0
        seen.append(options); return options.index(next(choices))
    game.player = manual; b.manual(0)
    assert not any('Cast' in options for options in seen)
    assert [town.field(c,'auto_combat') for c in b.chars] == [0,1,0]
    assert held == [(game.assets.text('magicOnMsg'),1,10),(game.assets.text('magicOffMsg'),1,10)] and not b.data['messages']
    game,b = action_fixture(); b.record(0)['target'] = 2; b.record(1)['target'] = 0
    game.player = lambda kind,options,current,**info:options.index('Alt-q')
    b.manual(0)
    assert b.data['cursor'] == -1 and b.record(0)['initiative'] == 20
    assert b.record(0)['target'] == -1 and b.record(1)['target'] == 0
    assert all(town.field(c,'auto_combat') for c in b.chars)
    for action,helper in (('View','view'),('Use','items_menu')):
        for initiative in (0,7):
            for done in (False,True):
                game,b = action_fixture(); b.chars[0].items.append(bytearray(65)); calls=[]; recalculated=[]; centered=[]
                choices=iter((action,'End'))
                def menu(kind,options,current,**info):
                    calls.append(kind); return options.index(next(choices))
                def finish(*args):
                    b.record(0)['initiative']=initiative
                    return done
                game.player=menu; b.reset_attacks=lambda i:recalculated.append(i); b.center=lambda *args:centered.append(args)
                with patch.object(inventory,helper,finish): b.manual(0)
                assert len(calls)==(1 if done else 2) and recalculated==[0]
                assert centered==([] if done else [(0,2)])
                assert b.record(0)['initiative']==(initiative if done else 0)
    for cleric,paladin,offered in ((255,0,False),(0,128,False),(1,0,True),(0,2,False),(0,3,True)):
        game,b = action_fixture(); town.put(b.chars[0],'levels',cleric,0); town.put(b.chars[0],'levels',paladin,3)
        town.put(b.chars[1],'undead',1); seen=[]
        game.vm.undead_count = 1
        game.player=lambda kind,options,current,**info:(seen.append(options),options.index('End'))[1]
        b.manual(0); assert ('Turn' in seen[0])==offered
    game,b = action_fixture(); prompts=[]
    game.player=lambda kind,options,current,**info:(prompts.append(info),1)[1]
    assert not b.confirm_ally(0,2)
    assert prompts[-1]['prompt']==game.assets.text('attackAllyPrompt') and prompts[-1]['start']==1
    game.player=lambda kind,options,current,**info:(prompts.append(info),0)[1]
    b.spell_targets=lambda *args:None
    with patch.object(magic,'handler',return_value=lambda *args:None): assert not b.cast(0,1,using_item=True)
    assert prompts[-2]['prompt']==game.assets.text('abortSpellPrompt') and prompts[-2]['start']==0
    assert (prompts[-1]['prompt'],prompts[-1]['timed'],prompts[-1]['message_colour'])==(game.assets.text('spellAbortedText'),1,10)


def check_aging():
    from .combat import name
    from .faults import BindingRequired
    game,b = action_fixture()
    game.age_pass = True
    warning = game.assets.text('ageWarningMsg')
    seen = []
    for c, age in zip(b.chars, (1590, 1591, 1600)):
        town.put(c, 'age', age, width=2)
    b.chars[1].b[1:5] = b'FOES'
    b.chars[2].b[1:5] = b'ALLY'
    town.put(b.chars[2], 'level_up_ready', 1)
    def warn(kind, options, current, **info):
        assert kind == 'ACK' and info['timed'] == 1 and info['prompt'] == ''
        assert (info['creature_column'], info['creature_row']) == (23, 10)
        assert info['creature_text'] == warning
        assert b.data['messages'] == [info['creature_name'] + ' ' + warning]
        seen.append((info['creature_name'], info['creature_colour']))
        return 0
    def clear_warning(battle, bottom=False):
        assert game.age_pass and not bottom and not battle.data['messages']
        seen.append('clear')
    game.player = warn
    game.clear_combat_text = clear_warning
    b.aging_deaths()
    assert seen == [(name(b.chars[1]), 14), 'clear', (name(b.chars[2]), 13), 'clear']
    assert not getattr(game, 'combat_report', []) and not game.age_pass and game.s.seed == 4660
    assert all(town.field(c, 'hp') == 250 and town.field(c, 'status') == 0 for c in b.chars)

    def collect_message(kind, options, current, **info):
        if not info.get('timed'): messages.append(info['message'])
        return 0
    for gender in (0,1):
        game,b = action_fixture(); del b.trigger
        c = b.chars[0]; text = game.assets.text; seen = []; game.age_pass = True
        town.put(c,'age',1601,width=2); town.put(c,'gender',gender)
        town.put(c,'level_up_ready',1)
        death = dict(creature_name=name(c), creature_text=text('ageDeathMsg'), creature_colour=13,
                     creature_row=10, creature_column=23)
        def choose(kind,options,current,**info):
            assert kind == 'ACK'
            state = (town.field(c,'hp'),town.field(c,'status'),b.record(0)['size'])
            if info.get('fall'):
                assert game.combat_report[-1]['creature_message'] == death
                seen.append(('fall',state))
            elif info.get('timed'):
                assert info['timed'] == 1 and info['prompt'] == ''
                assert {key:info[key] for key in death} == death
                seen.append(('hold',state))
            else:
                assert info['panel_row'] == 14 and info['prompt'] == text('pressToContinue')
                seen.append((info['message'],info['panel_colour'],state))
            return 0
        def cleared(battle, bottom=False):
            assert not bottom and not battle.data['messages']
            seen.append(('clear',b.record(0)['size']))
        game.player = choose
        game.clear_combat_text = cleared
        b.aging_deaths()
        assert seen == [
            (text('ageStrainMsg')+name(c)+'.  ',15,(250,0,1)),
            (text('heMsg' if gender == 0 else 'sheMsg')+text('lastBreathMsg'),15,(250,0,1)),
            ('fall',(0,8,1)), ('hold',(0,8,0)), ('clear',0),
            (name(b.chars[2])+text('oneWitnessMsg'),14,(0,8,0))]
        assert game.combat_report[:-1] == [name(c)+' '+text('ageDeathMsg')]
        assert game.combat_report[-1]['kind'] == 'fall'
        assert (town.field(c,'hp'),town.field(c,'status'),town.field(c,'active')) == (0,8,0)
        assert (b.record(0)['size'],b.record(0)['initiative'],b.record(0)['movement']) == (0,0,0)
        assert b.body_state() == ([(10,10,23)]+[(0,0,0)]*7,[0]+[-1]*7,1)
        assert not game.age_pass and game.s.seed == 4660
    for count,key in ((0,'oneWitnessMsg'),(1,'manyWitnessMsg'),(255,'noWitnessMsg')):
        game,b = action_fixture(); del b.trigger
        c = b.chars[0]; text = game.assets.text; messages = []; game.age_pass = True
        town.put(c,'age',1601,width=2); b.data['age_witness_count'] = count
        game.player = collect_message
        b.aging_deaths()
        expected = name(b.chars[2])+text(key) if count == 0 else text(key)+name(c)+text('bodySearchMsg') if count == 1 else text(key)
        assert len(messages) == 3 and messages[-1] == expected
        assert not game.age_pass and town.field(c,'status') == 8 and game.s.seed == 4660
    game,b = action_fixture(); del b.trigger
    game.age_pass = True; b.data['age_witness_count'] = 1; messages = []
    town.put(b.chars[0],'age',1601,width=2); town.put(b.chars[2],'active',0)
    game.player = collect_message
    try: b.aging_deaths()
    except BindingRequired as error: assert 'witness pointer' in str(error)
    else: raise AssertionError('unset witness pointer accepted')
    assert len(messages) == 2 and town.field(b.chars[0],'status') == 8 and game.age_pass
    game,b = action_fixture(); del b.trigger
    text = game.assets.text; messages = []; game.age_pass = True; b.data['age_witness_count'] = 0
    for i in (0,2): town.put(b.chars[i],'age',1601,width=2)
    game.player = collect_message
    b.aging_deaths()
    assert len(messages) == 6 and messages[2] == messages[5] == name(b.chars[2])+text('oneWitnessMsg')
    assert b.body_state()[2] == 2 and not game.age_pass and game.s.seed == 4660


def check_reviewed_actions():
    from unittest.mock import patch
    from . import combat,magic
    with patch.object(rules,'recalc_stats',lambda c,party_adjust=0:None):
        for rolls,hits,spent in (([1,1],0,2),([1,20],1,2),([20],1,1)):
            game,b = action_fixture(); town.put(b.chars[1],'active',0); town.put(b.chars[1],'status',10)
            item = bytearray(combat.Item.SIZE); item[combat.I['quantity']] = 4
            attack_rolls(b,rolls); b.attack(0,1,missile=item)
            assert len([e for e in game.combat_log if e.get('reason') == 'attack']) == spent
            assert b.data['hits_made'] == hits and town.field(b.chars[1],'hp') == 250
            assert item[combat.I['quantity']] == 4-spent and b.data['limit'] == 16
            assert b.record(0)['initiative'] == (6 if spent == 1 else 0)
        game,b = action_fixture(); town.put(b.chars[1],'active',0); town.put(b.chars[1],'status',10)
        item = bytearray(combat.Item.SIZE); item[combat.I['quantity']] = 2; b.chars[0].items.append(item)
        released = []; game.item_pool = type('Pool',(),{'release':lambda self,raw:released.append(raw)})()
        b.record(1)['x'] = 21
        attack_rolls(b,[1,1]); b.attack(0,1,missile=memoryview(item))
        assert not item[combat.I['quantity']] and not any(raw is item for raw in b.chars[0].items) and len(released) == 1 and released[0] is item
        flight = [e for e in game.combat_report if isinstance(e,dict) and e['kind'] == 'missile']
        assert len(flight) == 1 and flight[0]['start'] == b.position(0) and flight[0]['aim'] == b.position(1) and (flight[0]['item'],flight[0]['picture'],flight[0]['frames'],flight[0]['pace']) == (0,20,2,20)
        assert flight[0]['view'] == (7,7)
        impact = next(e for e in game.combat_report if isinstance(e,dict) and e['kind'] == 'attack')
        assert impact['view'] != flight[0]['view'] and 'actor' not in impact
        town.put(b.chars[0], 'hp', 12)
        b.show('move', actor=1, left=6)
        move = game.combat_report[-1]
        b.panel(1)
        assert b.data['panel'] == 1 and b.data['panel_print']['active'] == 0
        for step in (flight[0], impact, move):
            assert step['panel'] == 0 and step['panel_print']['hp'] == 250 and step['panel_print']['active'] == 1
        art = lambda kind,direction:tuple(combat.missile_art(kind,direction)[key] for key in ('picture','facing','mirror','frames','pace'))
        assert art(5,5) == (14,1,True,1,10) and art(7,1) == (14,0,False,1,10) and art(66,7) == (14,0,True,1,10) and art(12,6) == (15,1,False,1,10) and art(30,0) == (13,0,False,1,10)
        assert art(3,2) == (16,0,False,4,50) and art(55,2) == (17,0,False,4,50) and art(67,3) == (21,0,False,2,10) and art(9,3) == (20,0,False,2,20)
        game,b = action_fixture(); b.record(0).update(x=12,y=10); b.record(1).update(x=10,y=10,size=2)
        b.footprint = lambda size:[(0,0),(1,0)] if size == 2 else [(0,0)] if size else []
        assert 1 in b.targets(0,1) and 1 not in b.attack_targets(0)
        game,b = action_fixture(); b.die = lambda *a:6; b.reset_attacks = lambda i:None; b.movement = lambda i:12
        b.put_tile(10,10,29); b.put_tile(11,10,30); b.begin_round()
        assert not b.record(0)['cast_ok'] and b.record(1)['cast_ok']
        for tile in (28,29,30):
            game,b = action_fixture(); b.put_tile(10,10,tile); b.down(0)
            assert b.tile(10,10) == (tile if tile in (28,29) else 31)
        game,b = action_fixture(); choices = iter(('Move','Undo'))
        game.player = lambda kind,options,current,**info:options.index(next(choices))
        b.probe = lambda *a,**kw:(1,23)
        b.manual(0)
        assert b.record(0)['size'] == 0 and b.record(0)['movement'] == 12 and b.record(0)['initiative'] == 6
        assert not b.data['in_move_menu']
        game,b = action_fixture(); row = magic.spell(game,79); picked = []
        b.pick_spell_target = lambda *a:(picked.append(a),(1,b.position(1)))[1]
        with patch.object(magic,'caster_level',return_value=0): targets = b.spell_targets(0,row)
        assert targets == [1] and len(picked) == 1


def check_departure():
    game,b = action_fixture(); attacks = []
    b.attack = lambda *a,**kw:attacks.append((a,kw))
    effects.add_effect(b.chars[1],6,0,0,False)
    b.opportunity(0,6); assert not attacks and b.position(0) == (10,10)
    b.chars[1].effects.clear(); b.opportunity(0,6)
    assert len(attacks) == 1 and attacks[0][1] == {'behind':True} and b.record(1)['target'] == -1
    game,b = action_fixture(); b.can_target = lambda *a,**kw:False; b.data['panel'] = 1
    b.opportunity(0,6); assert b.data['panel_due'] and b.data['panel'] == 1
    b.equip(0); assert b.data['panel'] == 0 and not b.data['panel_due']
    b.data['panel'] = 1; b.equip(0); assert b.data['panel'] == 1
    game,b = action_fixture(); b.recalc = lambda c:None; town.put(b.chars[0],'hands_used',2)
    b.data.update(panel=1,panel_due=True); b.equip(0); assert b.data['panel'] == 0 and not b.data['panel_due']
    game,b = action_fixture(); listed = b.targets(0,allies=True); assert b.data['target_list'] == listed and len(listed) == 3
    b.record(listed[1])['size'] = b.record(listed[2])['size'] = 0
    assert b.targets(0,allies=True) == [0] and b.data['target_list'] == listed
    game.ask = lambda *a,**kw:b.record(listed[1]).update(size=1) or b.targets(listed[1],allies=True) and 0
    b.ask(Kind.ACK,('Continue',)); assert b.data['target_list'] == listed
    b.record(listed[1])['size'] = 0; kept = list(b.data['target_list']); b.distance(listed[2],0); assert b.data['target_list'] == kept == listed
    b.panel(1); town.put(b.chars[1],'side',1-town.field(b.chars[1],'side')); town.put(b.chars[1],'level_up_ready',1)
    assert b.data['panel_print']['side'] == 1-town.field(b.chars[1],'side') and b.data['panel_print']['level_up_ready'] == 0
    effects.add_effect(b.chars[0],1,10,0,False); del b.trigger; b.data['morale'] = 40
    assert b.trigger(10,0).morale == 45 and b.data['morale'] == 45 and b.trigger(10,0).morale == 50 and b.context(b.chars[0],morale=7).morale == 7
    seen = []; b.die = lambda *a,**kw:10; b.data['roll'] = dict(effect=0,damage=0,element=4,dice_count=0)
    b.trigger = lambda condition,i,context=None:seen.append(context.element) or context
    b.save(0,0); b.save(0,0,0,1); assert seen == [4,1]
    game,b = action_fixture(); town.put(b.chars[1],'active',0); town.put(b.chars[1],'status',6)
    b.show_attack(0,1,0,True,5,12); assert game.combat_report[-1]['down'] == 'killed'
    town.put(b.chars[1],'target_flags',8); b.show_attack(0,1,0,True,5,12); assert game.combat_report[-1]['down'] == ''
    game,b = action_fixture(); b.record(1)['size'] = 0
    b.movement = lambda i:(_ for _ in ()).throw(AssertionError('unnecessary movement lookup'))
    order = []
    b.strip = lambda i:order.append((b.record(i)['initiative'],b.record(i)['size']))
    notices = []
    game.player = lambda kind, options, state, **info: notices.append(info['creature_text']) or 0
    b.flee(0)
    assert order == [(0,0)] and town.field(b.chars[0],'hp') == 250 and game.s.seed == 4660
    assert b.tile(10,10) == 23 and not b.data['messages'] and notices == [game.assets.text('gotAwayText')]
    for own,enemy,expected_rolls in ((4,6,0),(6,6,1),(8,6,0)):
        game,b = action_fixture(); b.movement = lambda i:own if i == 0 else enemy; b.flee(0)
        assert len([e for e in game.combat_log if e.get('reason') == 'escape']) == expected_rolls
        assert b.record(0)['initiative'] == 0

    game, battle = action_fixture()
    actor = battle.record(0)
    actor['x'] = 0
    battle.movement = lambda i: 4 if i == 0 else 6
    battle.message('Previous message')
    blocked = game.assets.text('escapeBlockedText')
    choices = iter(('Move', 'west', 'Yes'))
    holds = []
    def attempt_escape(kind, options, state, **info):
        if kind != 'ACK':
            return options.index(next(choices))
        assert tuple(options) == ('Continue',) and info['timed'] == 1
        assert info['message_colour'] == 10 and info['after_pause'] == ' '
        holds.append((info['prompt'], actor['initiative'], actor['movement']))
        return 0
    game.player = attempt_escape
    battle.manual(0)
    assert holds == [(blocked, 6, 12)]
    assert actor['initiative'] == actor['movement'] == 0 and battle.position(0) == (0, 10)
    assert town.field(battle.chars[0], 'active') and game.s.seed == 4660
    assert battle.data['messages'] == ['Previous message'] and blocked not in game.combat_report


def check_turn_results():
    for needed,status in ((4,3),(-1,8)):
        game,b = action_fixture(); town.put(b.chars[0],'levels',8,0)
        town.put(b.chars[2], 'side', 1)
        for target in b.chars[1:]:
            town.put(target, 'undead', 1)
        b.t = dict(b.t,turning=bytes([needed&255]*143)); b.die = lambda count, sides, *args: sides
        stripped = []; b.strip = lambda i:stripped.append((i,b.record(i)['initiative'],b.record(i)['size']))
        holds = []
        falls = []
        b.chars[2].b[:5] = bytes((4,)) + b'FOE2'
        destroyed = game.assets.text('destroyedText')
        turned = game.assets.text('turnedText')
        def observe_turn(kind, options, state, **info):
            holds.append(info['prompt'])
            if info.get('creature_text') == turned:
                j = b.data['panel']
                assert kind == 'ACK' and tuple(options) == ('Continue',) and info['timed'] == 1
                assert (info['creature_column'], info['creature_row'], info['creature_colour']) == (23, 10, 14)
                assert info['creature_name'] == ('TEST' if j == 1 else 'FOE2')
                assert town.field(b.chars[j], 'active') and town.field(b.chars[j], 'status') == 0
                assert b.record(j)['size'] == 1 and b.record(j)['initiative'] == 6
                line = info['creature_name'] + ' ' + turned
                assert b.data['messages'][-1] == line and line not in getattr(game, 'combat_report', ())
                order.append(('hold', j))
            if info.get('fall'):
                fall = game.combat_report[-1]
                j = fall['actor']
                message = fall['creature_message']
                assert fall['kind'] == 'fall' and fall['panel'] == j
                assert town.field(b.chars[j], 'active') and town.field(b.chars[j], 'status') == 0
                assert (message['creature_column'], message['creature_row'], message['creature_colour']) == (23, 10, 14)
                assert message['creature_text'] == destroyed
                assert info['prompt'] == message['creature_name'] + ' ' + destroyed
                assert info['prompt'] not in game.combat_report
                falls.append((j, message['creature_name']))
            return 0
        game.player = observe_turn
        order = []
        count_targets = b.count_targets
        def search(actor):
            order.append('search')
            return count_targets(actor)
        b.count_targets = search
        def clear_result(battle, *, bottom):
            assert not bottom and not battle.data['messages']
            statuses = tuple(town.field(target, 'status') for target in battle.chars[1:])
            order.append((statuses, battle.record(0)['initiative']))
        game.clear_combat_text = clear_result
        b.turn_undead(0)
        expected = ['search']
        if needed > 0:
            expected.extend([('hold', 1), ((0, 0), 6)])
        expected.extend([((status, 0), 6), 'search'])
        if needed > 0:
            expected.extend([('hold', 2), ((status, 0), 6)])
        assert order == expected + [((status, status), 6), 'search', ((status, status), 0)]
        assert town.field(b.chars[1],'status') == status and town.field(b.chars[1],'hp') == 250
        assert not town.field(b.chars[1],'active') and b.record(1)['turned'] == 0 and b.record(1)['size'] == 0
        assert stripped == ([(1,0,0), (2,0,0)] if needed > 0 else [])
        assert falls == ([] if needed > 0 else [(1, 'TEST'), (2, 'FOE2')])
        assert holds == (['', '', ''] if needed > 0 else ['', 'TEST ' + destroyed, 'FOE2 ' + destroyed])
        assert b.tile(11,10) == (23 if needed > 0 else 31)
        assert game.assets.text('nothingHappensText') not in holds and not b.data['messages']
    game,b = action_fixture()
    b.record(0)['turns'] = 255
    town.put(b.chars[0], 'level_up_ready', 1)
    words = game.assets.text('turnsUndeadText')
    nothing = game.assets.text('nothingHappensText')
    order = []
    def turn_message(kind, options, state, **info):
        assert kind == 'ACK' and tuple(options) == ('Continue',)
        if info['prompt'] == nothing:
            assert info['timed'] == 1 and info['message_colour'] == 10 and info['after_pause'] == ' '
            assert b.record(0)['initiative'] == 6 and b.record(0)['movement'] == 12
            assert b.data['messages'] == ['TEST ' + words]
            order.append('nothing')
            return 0
        assert info['timed'] == 1 and info['prompt'] == '' and info['clear_bottom']
        assert (info['creature_column'], info['creature_row'], info['creature_colour']) == (23, 10, 13)
        assert (info['creature_name'], info['creature_text']) == ('TEST', words)
        assert b.record(0)['turns'] == 255 and game.s.seed == 4660
        assert b.data['messages'][-1] == 'TEST ' + words
        assert 'TEST ' + words not in getattr(game, 'combat_report', ())
        order.append('announcement')
        return 0
    game.player = turn_message
    def cleared(battle, *, bottom):
        assert not bottom and battle.data['messages'] == []
        assert battle.record(0)['initiative'] == 0 and battle.record(0)['movement'] == 0
        order.append('clear')
    game.clear_combat_text = cleared
    die = b.die
    def roll(*args):
        order.append((args, b.record(0)['turns']))
        return die(*args)
    b.die = roll
    b.turn_undead(0)
    assert order == ['announcement', ((1, 20, 'turn undead', 0), 0), 'nothing', 'clear']
    assert [e['reason'] for e in game.combat_log if e['event'] == 'dice'] == ['turn undead']
    assert nothing not in getattr(game, 'combat_report', ())

    game, battle = action_fixture()
    town.put(battle.chars[0], 'levels', 1, 0)
    town.put(battle.chars[2], 'side', 1)
    for enemy in battle.chars[1:]:
        town.put(enemy, 'undead', 1)
    battle.record(2)['x'] = 13
    game.vm.undead_count = 1
    game.s.seed = 14
    game.player = lambda kind, options, state, **info: options.index('Turn') if kind == 'COMBAT_ACTION' else 0
    battle.manual(0)
    assert town.field(battle.chars[1], 'status') == 3 and town.field(battle.chars[2], 'active')
    assert battle.data['target_list'][0] == 2 and battle.first_target_distance == 3
    assert game.s.seed == 2777724260


def check_area_aim():
    from . import magic
    from .faults import BindingRequired
    def arranged(radius=1):
        game,b = action_fixture()
        town.put(b.chars[0],'active',0); town.put(b.chars[2],'active',0)
        b.record(1).update(x=20,y=10)
        b.record(0)['target'] = 1
        game.s.r0[0xE6] = 1
        row = magic.spell(game,34)._replace(targeting=8+radius,range=20,range_per_level=0)
        return game,b,row
    for radius,cells,first in ((1,9,(19,9)),(2,21,(18,9)),(3,37,(17,9))):
        game,b,row = arranged(radius)
        rolls = []; b.die = lambda *args:rolls.append(args) or 100
        assert b.pick_spell_target(0,row,20,True,True) == (-1,first)
        assert len(rolls) == cells-1 and all(args[:3] == (1,100,'area aim tie') for args in rolls)
        assert b.record(0)['target'] == 1
        b.record(1)['size'] = 4
        rolls.clear()
        assert b.aim_area(0,row,20) == (-1,first) and len(rolls) == cells-1
    for ident,reduced in ((47,True),(108,True),(64,False),(82,False)):
        for dungeon in (0,1):
            game,b,row = arranged(3); game.s.r0[0xE6] = dungeon
            rolls = []; b.die = lambda *args:rolls.append(args) or 100
            b.aim_area(0,row._replace(id=ident),20)
            assert len(rolls) == (20 if reduced and not dungeon else 36)
    game,b,row = arranged()
    town.put(b.chars[2],'active',1); b.record(2).update(x=21,y=10)
    rolls = []; b.die = lambda *args:rolls.append(args) or 100
    assert b.aim_area(0,row,20) == (-1,(19,9)) and len(rolls) == 2
    town.put(b.chars[1],'active',0); rolls.clear()
    assert b.aim_area(0,row,20) is None and not rolls
    assert b.aim_area(0,row._replace(hostile=0),20) == (-1,(20,9))
    game,b,row = arranged(); b.record(0)['target'] = -1
    assert b.aim_area(0,row,20) is None and game.s.seed == 4660
    b.record(1).update(x=16,y=10); b.record(0)['target'] = 2
    b.record(2).update(x=40,y=10)
    b.die = lambda *args:100
    assert b.aim_area(0,row,8) == (-1,(15,9))
    assert b.aim_area(0,row,9) is None
    for face,expected,walks in ((25,(1,23),[(0,23),(1,23)]),(26,(0,23),[(0,23)])):
        game,b,row = arranged(); b.record(0).update(x=0,y=22,target=-1); b.record(1).update(x=0,y=24)
        rolls,paths = [],[]
        b.die = lambda *args:rolls.append(args) or face
        b.walk = lambda x,y,tx,ty,reach:paths.append((x,y,tx,ty,reach)) or (True,(tx,ty),0)
        assert b.aim_area(0,row,6) == (-1,expected) and len(rolls) == 5
        assert paths == [(x,y,0,22,6) for x,y in walks]
    game,b,row = arranged(); paths = []
    b.walk = lambda x,y,tx,ty,reach:paths.append((x,y)) or (False,(x,y),0)
    assert b.aim_area(0,row,20) is None and game.s.seed == 4660 and len(paths) == 9
    game,b,row = arranged(); town.put(b.chars[1],'active',0); town.put(b.chars[2],'active',1)
    b.record(2).update(x=20,y=10)
    for _ in range(12):
        game.s.party.append(rules.character(b.chars[2].b))
        b.data['actors'].append(dict(b.record(2)))
    b.die = lambda *args:100
    assert b.aim_area(0,row,20) == (-1,(19,9))
    game,b,row = arranged()
    expected = (19,9)
    for x in range(19,22):
        for y in range(9,12):
            if (x,y) != (19,9) and game.s.random(100)<25: expected = x,y
    seed = game.s.seed; game.s.seed = 4660
    assert b.aim_area(0,row,20) == (-1,expected) and game.s.seed == seed
    assert len(game.combat_log) == 8
    game,b,row = arranged(); town.put(b.chars[0],'active',1)
    b.die = lambda *args:100
    assert b.spell_targets(0,row,ai=True) == [1]
    assert b.data['aim'] == (19,9) and b.data['multi_target'] == 1 and b.record(0)['target'] == 1
    b.aim_area = lambda *args:(_ for _ in ()).throw(AssertionError('point spell used area scoring'))
    del b.die
    assert b.pick_spell_target(0,row._replace(targeting=8),20,True,True) == (1,(20,10))
    game,b,row = arranged()
    try: b.aim_area(0,row._replace(targeting=11),254)
    except BindingRequired: pass
    else: raise AssertionError('wrapped area grid accepted')
    from .records import Spells
    game,b = action_fixture(); del b.trigger
    game.s.r0[0xE6] = 1
    b.record(1).update(x=20,y=10); b.record(2).update(x=45,y=10); b.record(0)['target'] = 1
    b.chars[0].b.extend(bytes(Spells.SIZE))
    town.put(b.chars[0],'memorized',47,0); town.put(b.chars[0],'levels',6,5)
    for _ in range(36): game.s.random(100)
    for _ in range(100): game.s.random(1); game.s.random(4)
    damage = sum(game.s.random(6)+1 for _ in range(6)); game.s.random(20)
    seed = game.s.seed; game.s.seed = 4660
    assert b.cast(0,47,ai=True) and game.s.seed == seed
    assert town.field(b.chars[1],'hp') == 250-damage//2
    assert town.field(b.chars[0],'hp') == town.field(b.chars[2],'hp') == 250
    assert town.field(b.chars[0],'memorized',0) == 175 and b.data['multi_target'] == 0
    assert next(e for e in game.combat_log if e['event'] == 'cast')['targets'] == (1,)


def check_camp_only_spell():
    from .records import Spells
    game, battle = action_fixture()
    caster = battle.chars[0]
    caster.b.extend(bytes(Spells.SIZE))
    town.put(caster, 'levels', 1, 5)
    town.put(caster, 'abilities', 12, 3)
    town.put(caster, 'memorized', 18)
    battle.panel(1)
    battle.data['messages'].append('previous message')
    battle.data['view'] = (0, 0)
    events = []
    actions = iter(('Cast', 'Cast', 'End'))
    selections = iter(('Read Magic', 'Exit'))

    def choose(kind, options, state, **info):
        if kind == 'COMBAT_SPELL':
            choice = next(selections)
            events.append(choice)
            return [option.strip() for option in options].index(choice)
        if kind == 'ACK':
            events.append(info['prompt'])
            assert (info['timed'], info['message_colour'], info['after_pause']) == (1, 10, ' ')
            assert battle.data['panel'] == 1 and battle.data['messages'] == ['previous message']
            return 0
        assert kind == 'COMBAT_ACTION'
        assert town.field(caster, 'memorized') == 18 and game.s.seed == 4660
        actor = battle.record(0)
        assert (actor['casting'], actor['movement'], actor['initiative']) == (0, 12, 6)
        if events:
            assert battle.data['panel'] == 0 and not battle.data['panel_due']
            assert not battle.data['messages'] and battle.data['view'] == (7, 7)
        choice = next(actions)
        events.append(choice)
        return options.index(choice)

    game.player = choose
    def flushed(current):
        events.append((current.data['view'], current.data.get('cursor_active', False), current.data['panel']))

    game.flush_combat_view = flushed
    battle.manual(0)
    centered, restored = ((7, 7), True, -1), ((7, 7), True, 0)
    assert events == ['Cast', 'Read Magic', 'Camp Only Spell', ((0, 0), False, -1), centered, restored,
                      'Cast', 'Exit', ((7, 7), False, -1), centered, restored, 'End']


def check_delayed_cast_announcement():
    from .records import Spells
    for ai in (False, True):
        game, battle = action_fixture()
        caster = battle.chars[0]
        caster.b.extend(bytes(Spells.SIZE))
        town.put(caster, 'levels', 5, 5)
        town.put(caster, 'abilities', 18, 3)
        town.put(caster, 'memorized', 47)
        town.put(caster, 'side', int(ai))
        actor = battle.record(0)
        initial = 1 if ai else 6
        delayed = max(1, initial - 1)
        actor['initiative'] = initial
        battle.record(2)['initiative'] = delayed
        expected_order = [1, 2, 0] if game.s.random(2) == 0 else [1, 0, 2]
        end_seed = game.s.seed
        game.s.seed = 4660
        events = []

        def check_before_delay():
            assert (actor['casting'], actor['initiative'], game.s.seed) == (0, initial, 4660)
            assert battle.data['order'] == [0, 1, 2] and battle.data['cursor'] == 0

        def choose(kind, options, state, **info):
            if kind == 'COMBAT_ACTION': return options.index('Cast')
            if kind == 'COMBAT_SPELL': return [option.strip() for option in options].index('Fireball')
            assert kind == 'ACK' and (info['timed'], info['prompt']) == (1, '')
            check_before_delay()
            assert (info['creature_column'], info['creature_row']) == (23, 10)
            assert (info['creature_name'], info['creature_colour']) == ('TEST', 14 if ai else 11)
            assert info['creature_text'] == 'Begins Casting'
            assert battle.data['messages'] == ['TEST Begins Casting']
            events.append('hold')
            return 0

        def cleared(current, bottom):
            if bottom: return
            check_before_delay()
            assert not current.data['messages']
            events.append('clear')

        game.player = choose
        game.clear_combat_text = cleared
        if ai: assert battle.begin_cast(0, 47, ai=True)
        else: battle.manual(0)
        assert events == ['hold', 'clear']
        assert (actor['casting'], actor['initiative'], game.s.seed) == (47, delayed, end_seed)
        assert battle.data['order'] == expected_order and battle.data['cursor'] == -1
        assert 'TEST Begins Casting' not in getattr(game, 'combat_report', ())


def check_spell_locks():
    from . import magic
    game,b = action_fixture(); row = magic.spell(game,79)
    b.record(0)['target'] = 1
    choices = iter(('Target', 'Target', 'Already been targeted', 'Exit'))
    def repeat_target(kind, options, state, **info):
        choice = next(choices)
        assert b.record(0)['target'] == 1
        if kind == 'ACK':
            assert info['prompt'] == choice
            return 0
        return options.index(choice)
    game.player = repeat_target
    assert b.spell_targets(0,row) == [1]
    assert next(choices, None) is None and b.record(0)['target'] == -1 and game.s.seed == 4660
    choices = iter(((1,b.position(1)),(2,b.position(2)),None))
    b.aim_menu = lambda *a:next(choices)
    assert b.pick_spell_target(0,row,10,False,False)[0] == 1 and b.record(0)['target'] == 1
    assert b.pick_spell_target(0,row,10,False,False)[0] == 2 and b.record(0)['target'] == 2
    assert b.pick_spell_target(0,row,10,False,False) is None and b.record(0)['target'] == -1
    row = row._replace(targeting=15)
    b.record(0)['target'] = 1; b.pick_spell_target = lambda *a:(-1,(11,10))
    assert b.spell_targets(0,row,ai=True) == [1] and b.record(0)['target'] == 1
    b.record(0)['target'] = -1; seen = []
    b.area_targets = lambda x,y,radius:(seen.append(radius),[2])[1]
    assert b.spell_targets(0,row._replace(targeting=47),ai=True) == [2] and seen == [2]
    game,b = action_fixture(); row = magic.spell(game,79)._replace(id=18,targeting=5)
    town.put(b.chars[1],'highest_level',255); town.put(b.chars[2],'highest_level',1)
    b.die = lambda *a:8
    picks = iter(((1,b.position(1)),(2,b.position(2))))
    b.aim_menu = lambda *a:next(picks)
    assert b.spell_targets(0,row) == [1,2]


def check_spell_ratings():
    from . import magic
    game,b = action_fixture(); target = b.chars[1]
    def rated(ident, **changes):
        row = magic.spell(game,ident)._replace(**changes)
        return b.rate_spell_target(0,1,row,1)
    for ident,effect in ((15,17),(65,17),(21,96),(21,53),(23,97),(49,52),(51,65),(61,97),
                         (68,99),(82,80),(84,92),(94,97)):
        assert rated(ident) == 1, ident
        effects.add_effect(target,effect,0,0,False)
        assert rated(ident) == 0, ident
        target.effects.clear()
    town.put(target,'highest_level',5); assert rated(21) == 0 and rated(91) == 1
    town.put(target,'highest_level',6); assert rated(91) == 0
    town.put(target,'highest_level',255); assert rated(21) == rated(91) == 1
    town.put(target,'race',255); assert rated(23) == rated(49) == rated(4) == 1
    town.put(target,'race',7); assert rated(23) == rated(49) == 0
    assert rated(4) == 0
    town.put(target,'creature_type',16); assert rated(4) == 1
    assert rated(10) == rated(106) == 1
    town.put(target,'dimensions',2); assert rated(10) == rated(106) == 0
    town.put(target,'creature_type',2); assert rated(10) == rated(106) == rated(81) == rated(111) == 1
    town.put(target,'creature_type',0); assert rated(81) == rated(111) == 0
    for ident in (3,53,58,71): assert rated(ident) == 1
    town.put(target,'hp',255)
    for ident in (3,53,58,71): assert rated(ident) == 0
    for ident,effect in ((37,33),(43,36),(104,36)):
        assert rated(ident) == 0
        effects.add_effect(target,effect,0,0,False); assert rated(ident) == 1
        target.effects.clear()
    for ident in (47,64,74,108):
        assert rated(ident) == 1
        effects.add_effect(target,76,0,0,False); assert rated(ident) == -10
        target.effects.clear()
    for ident in (56,76): assert rated(ident) == 1
    town.put(target,'target_flags',8)
    for ident in (56,76): assert rated(ident) == 0
    assert rated(1) == rated(105) == 0
    b.record(1)['x'] = 20
    assert rated(1) == rated(105) == 1
    effects.add_effect(target,1,0,0,False); assert rated(1) == rated(105) == 0
    target.effects.clear()
    effects.add_effect(target,49,0,0,False); assert rated(42) == 1
    effects.add_effect(b.chars[0],49,0,0,False); assert rated(42) == 0
    target.effects.clear(); b.chars[0].effects.clear()
    assert rated(19,effect=17) == rated(19,effect=0) == 1
    effects.add_effect(target,17,0,0,False); assert rated(19,effect=17) == 0
    target.effects.clear()
    for effect,cutoff in ((59,5),(63,4)):
        effects.add_effect(target,effect,0,0,False)
        assert rated(19,effect=0,level=cutoff-1) == 0 and rated(19,effect=0,level=cutoff) == 1
        target.effects.clear()
    town.put(target,'magic_resistance',50); assert rated(19,effect=0) == 1
    town.put(target,'magic_resistance',51); assert rated(19,effect=0) == 0
    assert b.rate_spell_target(0,1,magic.spell(game,19),0) == -10 and game.s.seed == 4660
    game,b = action_fixture(); b.targets = lambda *a,**kw:[1]
    assert b.rate_spell(0,1) == 246 and game.s.seed == 4660
    row = magic.spell(game,15); selected = b.pick_spell_target(0,row,10,False,True)
    assert selected == (1,b.position(1)) and b.record(0)['target'] == 1
    effects.add_effect(b.chars[1],17,0,0,False)
    assert b.pick_spell_target(0,row,10,False,True) is None and b.record(0)['target'] == 1
    b.targets = lambda *a,**kw:[2]
    row = magic.spell(game,3)
    assert b.pick_spell_target(0,row,10,False,True) == (2,b.position(2))


def check_leadership():
    for charisma,roll,automatic in ((20,55,1),(20,54,0),(64,100,0),(65,24,1),(65,23,0)):
        game,b = action_fixture(); c = b.chars[0]; follower = b.chars[2]
        town.put(c,'levels',1,7); town.put(c,'knight_order',1); town.put(c,'abilities',charisma,11)
        town.put(follower,'npc',128); town.put(follower,'abilities',4,3)
        b.die = lambda *a:roll; game.player = lambda *a,**kw:0
        b.leadership()
        assert town.field(follower,'auto_combat') == automatic and town.field(b.chars[1],'auto_combat') == 1
        assert sum(' leads ' in message for message in b.data['messages']) == 1-automatic
    for level,intelligence in ((255,4),(0,4),(1,3)):
        game,b = action_fixture()
        leader,enemy,follower = b.chars
        town.put(leader,'levels',level,7)
        town.put(follower,'npc',128)
        town.put(follower,'abilities',intelligence,3)
        b.leadership()
        assert game.s.seed == 4660 and not b.data['messages']
        assert town.field(follower,'auto_combat') == town.field(enemy,'auto_combat') == 1
