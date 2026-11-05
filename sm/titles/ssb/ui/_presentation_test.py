"""GU-80 sm-x1: ordered display calls, rows 44/47/48/49 and spell display kinds.

Synthetic headless evidence; the original's oracle frames remain a separate gate.
"""
from sm.titles.ssb import data as ssb_data
from collections import deque
from unittest.mock import patch

from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui._player_screens_test import Fixture, drawing
from sm.titles.ssb.units import magic, shops
from sm.titles.ssb.units._combat_test import fixture


def scene():
    """ov12:1564: deterministic two-combatant scene, no native save access."""
    game, battle = fixture()
    for c, name in zip(battle.chars, (b'HERO', b'FOE')):
        c.b[0] = len(name); c.b[1:1+len(name)] = name
    game.s.g['67D6'] = 3
    battle.init_round()
    session = Fixture(game, 'COMBAT_ACTION', ['move', 'done'], actor=0)
    return game, battle, screen.Controller(session, presentation=True)


def check_messages_and_keys():
    """Rows 44b/48: ov26:173F/1827, 0540:0BF7; ov28:03C9 holds every key in order."""
    game, battle, ui = scene()
    # Opaque row-copy optimization must preserve clipping at all four edges.
    for x,y,clip in [(-2,-1,None),(318,199,None),(4,4,(5,5,8,7))]:
        fast,reference=screen.Frame(),screen.Frame();pixels=[bytes(range(8)),[None,1,None,3,4,5,6,7]]*2
        fast.blit(x,y,pixels,clip=clip)
        reference.blit(x,y,pixels,colours=tuple(range(16)),clip=clip)
        assert fast.rows==reference.rows
    shops.message(game, 'First event with a long stale fragment')
    shops.message(game, 'Second event')
    events = list(game.presentation)
    assert [e['text'] for e in events] == ['First event with a long stale fragment', 'Second event']
    assert all(e['delay'] == .3 for e in events)
    frozen = events[0]['scene'].s.chars()[0].b
    game.s.party[0].b[0x1B5] -= 1
    assert events[0]['scene'].s.chars()[0].b == frozen, 'historical HP mutated'
    assert not ui.key('d', 'd') and not ui.key('m', 'm')
    assert list(ui.held_keys) == [('d', 'd'), ('m', 'm')] and not ui.session.answers
    assets = screen.Assets(); before = game.s.hash(game.vm)
    first = screen.render(ui, assets, 0).rows
    assert screen.render(ui, assets, .29).rows == first
    assert ui.presentation_event is events[0]
    second = screen.render(ui, assets, .3).rows
    assert second != first and ui.presentation_event is events[1]
    assert game.s.hash(game.vm) == before and not ui.session.answers
    screen.render(ui, assets, .6)
    assert ui.session.answers == [1]
    ui.key('d', 'd')  # A newly arrived key cannot overtake the older Move.
    screen.render(ui, assets, .7); screen.render(ui, assets, .8)
    assert ui.session.answers == [1, 0, 1] and not ui.held_keys
    assert game.s.hash(game.vm) == before
    # Even a very late poll shows exactly one event; speed zero never drops one.
    game.s.g['67D6'] = 0
    shops.message(game, 'zero one'); shops.message(game, 'zero two')
    screen.render(ui, assets, 10)
    assert ui.presentation_event['text'] == 'zero one'
    screen.render(ui, assets, 1000)
    assert ui.presentation_event['text'] == 'zero two'


def check_attack_move_death():
    """Rows 44b/47: ov15:06F7/17F3/181D; ov33:0E9E..0F89; presentation never changes RNG/hash."""
    game, battle, ui = scene()
    ref, other = fixture(); ref.s.g['67D6'] = 3; other.init_round()
    for c, name in zip(other.chars, (b'HERO', b'FOE')):
        c.b[0] = len(name); c.b[1:1+len(name)] = name
    old_direction = battle.record(battle.chars[0])[9]
    battle.attack(*battle.chars); other.attack(*other.chars)
    assert game.s.hash(game.vm) == ref.s.hash(ref.vm), 'display collection changed combat'
    assert getattr(ref, 'presentation', None) is None, 'headless combat collected frames'
    kinds = [e['kind'] for e in game.presentation]
    assert kinds[:4] == ['facing', 'clear', 'status', 'swing'] and 'message' in kinds and kinds[-2:] == ['clear', 'facing']
    assert game.presentation[1]['panel_clear'] and not game.presentation[2].get('merge')  # ov15:17EE completes status before 1803.
    assert all(e['scene'].s.g['combat.records'][0][9] == old_direction for e in list(game.presentation)[:3]), 'ov15:17E5 local direction leaked before swing'
    swing = next(e for e in game.presentation if e['kind'] == 'swing')
    assert swing['delay'] == .1 and swing['poses'][0] == 1
    msg=next(e for e in game.presentation if e['kind']=='message')
    assert msg['text'].startswith('HERO\nAttacks\nFOE\n') and [n[2] for n in msg['names']]==[11,14]
    normal = dict(swing, poses={0: 0})
    assets = screen.Assets()
    assert screen.render_presentation(ui, swing, assets).rows != screen.render_presentation(ui, normal, assets).rows
    game.presentation.clear()
    actor = battle.chars[0]
    battle.record(actor)[6] = 20
    direction = battle.legal_moves(actor)[0]
    battle.move(actor, direction)
    moved = next(e for e in game.presentation if e['kind'] == 'move')
    assert moved['scene'].s.g['combat.positions'][0][:2] == battle.position(actor)
    battle.kill(actor)
    deaths = [e for e in game.presentation if e['kind'] == 'death']
    # ov33:0E9E..0F89 nine 10 ms frames; ov33:106F MessageDelay holds the ninth picture (gtrace 015: no flush
    # between the last Delay(10) and 0540:0BF7); ov33:10BE RedrawMap then shows the corpse with the next frame.
    assert len(deaths) == 10 and all(e['delay'] == .01 for e in deaths[:9]) and deaths[9]['delay'] == .3, 'corpse hold lost'
    assert [e['sprite'] for e in deaths] == [11, 139]*4 + [11, 11]
    assert deaths[0]['scene'].s.g['combat.positions'][0][2] == 1
    assert game.presentation[-1]['kind'] == 'redraw' and game.presentation[-1]['merge']
    assert game.presentation[-1]['scene'].s.g['combat.positions'][0][2] == 0


def check_continue_and_hp():
    """44a ov10:1066..109A demo gate; 49 ov26:0D06..0D17 passes show_max=0 to 0BA6."""
    game, battle, ui = scene()
    c = game.s.party[0]; c.b[0x1B5] = c.b[0x70] = 112
    _, calls = drawing(ui, screen.Assets())
    assert (33, 3, '112') in calls and not any('/' in t for x, y, t in calls if (x, y) == (33, 3))
    prompt=screen.Controller(Fixture(game,'MENU',['continue','end'],action='continue-battle'))
    _,calls=drawing(prompt,screen.Assets())
    assert (0,24,'Continue Battle:') in calls and (23,10,'Continue Battle:') not in calls
    # Contrast the native three-character field with the old clipped 112/11.
    for demo in (0, 1):
        g, fight = fixture(); fight.kill(g.s.monsters[0]); g.s.g['67E9'] = demo
        asked = []
        def answer(kind, options, current, **info):
            """ov10:1066: Yes stays index zero and No stays index one."""
            asked.append((kind, options, info)); return 0
        g.player = answer
        assert fight.end_round() == bool(demo)
        assert bool(asked) == (not demo)
        if asked: assert asked[0][1] == ['continue', 'end'] and asked[0][2]['action'] == 'continue-battle'


def check_spell_kinds():
    """ov23:15E8/1D22/1910/29C5/3D76; ov25:1F3C/217B; ov26:270F and ov14:3212."""
    for sid in (15, 47, 51, 92, 23, 1, 34, 83):
        game, battle, ui = scene(); a, b = battle.chars
        a.b[0x116] = 9
        with patch.object(magic._Magic, 'save', return_value=False):
            assert magic.cast(game, a, sid, [b], combat=True, consume=False), sid
        kinds = {e['kind'] for e in game.presentation}
        assert game.presentation[0]['text'] == 'HERO\nCasts a Spell' and not game.presentation[0].get('spell')
        assert 'missile' in kinds, (sid, kinds)
        # ov26:1CCD..1D21, ov23:15E8; oracle 051-normal/00463 includes arrival
        # and has already cleared the cast caption during the entire flight.
        missiles = [e for e in game.presentation if e['kind'] == 'missile']
        assert missiles[-1]['point'] == battle.position(b)
        assert all(not e['text'] for e in missiles)
        if sid in (15, 47): assert 'flash' in kinds
        if sid == 51: assert 'bolt' in kinds
        if sid in (47, 34): assert 'area' in kinds
        if sid == 83: assert 'move' in kinds and any('teleports' in e['text'] for e in game.presentation)
        if sid == 92:
            # ConeTargets has no drawing call of its own: the shared cast bolt precedes its target messages.
            assert all(e['kind'] != 'cone' for e in game.presentation)
        before = game.s.hash(game.vm)
        for kind in kinds:
            event = next(e for e in game.presentation if e['kind'] == kind)
            screen.render_presentation(ui, event, screen.Assets())
        assert game.s.hash(game.vm) == before
    game, battle, ui = scene(); a, b = battle.chars
    magic._Magic(game).effect(b, 1, 5, text='is Blessed')
    flashes = [e for e in game.presentation if e['kind'] == 'flash']
    assert len(flashes) == 16 and all(e['delay'] == .07 for e in flashes)
    game.presentation.clear()
    magic._Magic(game).effect(b, 2, 5, save_type=1, saved=True, text='is Cursed')
    assert [e['text'] for e in game.presentation] == ['FOE\nis Unaffected']
    assert all(e['kind'] != 'flash' for e in game.presentation)
    # Missile categories preserve their original frame counts/delays.
    for typ, delay in ((5,.01),(3,.05),(28,.01),(4,.02)):
        game.presentation.clear(); item=bytearray(67); item[0x2E]=typ
        battle.missile(a,b,item)
        # ov26:1C38 calls RedrawMap with no Delay; only the missile steps reach Delay at 1D31.
        events = list(game.presentation)
        assert len(events) > 2 and events[0]['kind'] == 'redraw' and events[0]['delay'] == 0
        assert all(e['kind'] == 'missile' and e['delay'] == delay for e in events[1:-1])
        assert events[-1]['kind'] == 'erase' and events[-1]['delay'] == 0   # ov26:2136 closing flush after the last restore blit
    # Delayed blast uses the most recently allocated four-frame display buffer,
    # including a later effect flash, rather than assuming a fireball sprite.
    game, battle, ui = scene(); a, b = battle.chars
    m=magic._Magic(game); game.s.g['87D8']=115
    game.s.g['8D8B'],game.s.g['8D8C']=battle.position(b)
    m.make_area(a,0x64,1); battle.flash(b,1)
    effect=next(e for e in a.effects if e[0]==0x64)
    game.presentation.clear(); m.clear_area(a,effect,blast=True)
    blast=list(game.presentation)[:4]
    assert [e['delay'] for e in blast]==[.07,.1,.13,.16]
    assert [e['sprite'] for e in blast]==[9,9,137,137]
    assert [bool(e['bottom']) for e in blast]==[False,True,True,True]
    assert all(e['kind']=='area' for e in blast)
    game,battle,ui=scene();a,b=battle.chars
    battle.place(a,12,10); battle.place(b,10,10); battle.record(a)[9]=2
    with patch.object(magic._Magic,'pick',return_value=[b]),patch.object(magic._Magic,'cone',return_value=[b]):
        assert magic.breath_weapon(game,a,bytearray((0x53,0,0,3)))
    # ov23:6324/634F -> ov33:0B55: breath permanently faces its first target, including the raised pose.
    assert battle.record(a)[9]==6
    raised=next(e for e in game.presentation if e['kind']=='swing')
    assert raised['poses'][0]==1 and raised['scene'].s.g['combat.records'][0][9]==6 and raised['text']==''
    missiles=[e for e in game.presentation if e['kind']=='missile']
    assert missiles and all(e['sprite']==5 and e['delay']==.03 for e in missiles)
    game,battle,ui=scene();a,b=battle.chars;b.b[0x1B5]=1
    magic._Magic(game).damage(b,3)
    messages=[e for e in game.presentation if e['kind']=='message']
    # ov25:2054 = DS:7DD5 + 1 after HitAnimation's text leaves 7DD5 on its last row: the spell death text starts directly
    # under the burst text (arena 015/00477, 051-normal/00621: 0 px). The blank row belongs to the melee path ov15:04C0 (st_404).
    assert len(messages)==2 and messages[1]['text'].startswith(messages[0]['text']+'\n') and not messages[1]['text'].startswith(messages[0]['text']+'\n\n'), 'spell death text directly under the burst text'
    assert messages[1]['names'][-1]==(3,1,12) and messages[1]['delay']==0, 'death name belongs on row13 after this three-row damage caption'
    assert messages[1]['text'].endswith('FOE\nGoes Down, and is Dying')  # ov25:1FC8; oracle arena 004/00468.


def check_quick_rounds():
    """44b ov11:000F: uninterrupted Quick rounds collect frames without changing decisions."""
    from sm.titles.ssb.units.combat import run
    results=[]
    for enabled in (False,True):
        game,battle=fixture(4)
        game.player=lambda kind,options,g,**info: (options.index('quick') if kind=='COMBAT_ACTION' else
                                                  options.index('end') if info.get('action')=='continue-battle' else 0)
        if enabled: game.presentation=deque(); game.presentation_text=''
        run(game)
        if enabled:
            assert len(game.presentation)>100 and {'move','swing','message','death'} <= {e['kind'] for e in game.presentation}
            assert len({e['actor'] for e in game.presentation})==4
            assert len({e['scene'].s.g['8DC7'] for e in game.presentation})>1
        else: assert getattr(game,'presentation',None) is None
        results.append((game.s.hash(game.vm),game.trace))
    assert results[0]==results[1], 'Quick queue changed simulation or answers'


def check_quick_off():
    """Row 90: Space hands Quick back. At a menu (ov10:0B99) all party with morale below 80h; in an AI turn (ov11:121D) also not status 1, and the member's turn returns (+3 = 14h)."""
    from sm.titles.ssb.units.combat import CTRL
    import copy
    game, battle, ui = scene(); party = game.s.party; first = party[0]
    assert battle.legal_actions(first)[-3:] == ['quick-off', 'magic-toggle', 'divine-intervention'], 'new hidden keys must follow the existing Space answer'
    party.extend(copy.deepcopy(first) for _ in range(2))
    records = game.s.g['combat.records']; records[1:1] = [list(records[0]), list(records[0])]
    for p in party: p.b[CTRL] = 1
    party[1].b[0xFF] = 0x80; party[2].b[0x1A6] = 1
    seed = game.s.seed
    battle.quick_off()                                                     # the menu's rule ignores status
    assert [p.b[CTRL] for p in party[:3]] == [0, 1, 0], 'menu rule'
    for p in party: p.b[CTRL] = 1
    game.ai_check = lambda: ' '
    assert battle.check_interrupt(first) and battle.record(first)[3] == 20 and not first.b[CTRL], 'AI rule: turn returns'
    assert [p.b[CTRL] for p in party[1:3]] == [1, 1], 'AI rule skips morale and status 1'
    for p in party: p.b[CTRL] = 1
    monster = game.s.monsters[0]; c3 = battle.record(monster)[3]; monster.b[CTRL] = 1
    assert not battle.check_interrupt(monster) and battle.record(monster)[3] == c3 and not first.b[CTRL], 'monster turn clears Quick and goes on'
    for p in party: p.b[CTRL] = 1
    game.ai_check = lambda: None
    assert not battle.check_interrupt(first) and first.b[CTRL], 'no key'
    for p in party: p.b[CTRL] = 0
    game.ai_check = lambda: None                                          # ov11:1197 still checks 2/- when no party member is Quick.
    assert not battle.check_interrupt(first)
    del game.ai_check
    assert not battle.check_interrupt(first) and game.s.seed == seed, 'headless or dice'


def check_combat_controls():
    """ov10:0A87/0D63 vs ov11:11C6/1274: player 2/- are filtered; AI raw keys retain turn and RNG."""
    game, battle, ui = scene(); actor = battle.chars[0]; monster = battle.chars[1]
    seed = game.s.seed; initiative = battle.record(actor)[3]
    game.ai_check = lambda: '2'
    actor.b[0x1A9] = 0
    assert not battle.check_interrupt(monster) and game.s.g['8E14'] == 1, 'monster turn must check without any Quick member'
    assert [e['command'] for e in game.presentation] == ['Magic On', '']
    game.presentation.clear()
    assert not battle.check_interrupt(monster) and game.s.g['8E14'] == 0
    assert [e['command'] for e in game.presentation] == ['Magic Off', '']
    game.presentation.clear(); before = bytes(monster.b)
    game.ai_check = lambda: '-'
    assert not battle.check_interrupt(monster) and not game.presentation, 'AI ignores a false intervention result'
    assert bytes(monster.b) == before
    actor.b[0x1F:0x69] = bytes(0x4A); actor.b[0x1F:0x21] = bytes((3,75)); game.s.g['8E14'] = 1
    bounds=[]
    def sample(bound):
        """ov11:0586..0653: noncombat75 still participates in the AI's random spell pool."""
        bounds.append(bound); return 0
    with patch.object(game.s,'random',side_effect=sample), patch.object(battle,'spell_worth_casting',return_value=False):
        assert not battle.ai_magic(actor)
    assert bounds == [7,2,2,2], 'AI must sample both memorized slots before testing spell priority'
    flags = battle.record(actor); saved = flags[1], flags[22]
    for first, second in ((0, 1), (1, 0)):
        flags[1], flags[22] = first, second
        with patch.object(game.s, 'random', side_effect=AssertionError('ineligible caster rolled')):
            assert not battle.ai_magic(actor)  # ov11:0552/0561 -> 057F: either missing flag returns before Random.
    flags[1], flags[22] = saved
    ui.session = Fixture(game, 'COMBAT_ACTION', battle.legal_actions(actor), actor=0); ui.capture_text()
    assert not ui.key('2', '2') and not ui.key('-', '-') and not ui.session.answers  # sm-r2-8: ordinary menu keys leave8E14 and the screen unchanged; ov10:0A87 distinguishes scan codes.
    game.dos_args = ('unused', 'wrong')
    assert not battle.divine_intervention(actor) and bytes(monster.b) == before
    from sm import dax
    data = ssb_data.stexe(); game.dos_args = ('unused', data[0x1910:0x1910+data[0x190F]].decode('cp437'))
    assert battle.divine_intervention(actor)
    assert monster.b[0x1A6] == 6 and monster.b[0x1A7] == 0 and monster.b[0x1B5] == before[0x1B5]
    assert not battle.s.g['combat.positions'][1][2] and not battle.s.g['combat.bodies']
    assert game.s.seed == seed and battle.record(actor)[3] == initiative


def check_ai_edge_recenter():
    """ov15:0807..0849: an off-view AI destination first follows the old position with margin2."""
    game, battle, ui = scene(); actor, enemy = battle.chars
    battle.place(actor,13,10); battle.place(enemy,10,14); actor.b[0x1A9]=1
    battle.record(actor)[6]=20; game.presentation_view=(7,7); seed=game.s.seed
    battle.move(actor,2)
    assert battle.position(actor)==(14,10) and game.s.seed==seed
    assert game.presentation_view==(10,7), 'centering on the destination would incorrectly yield (11,7)'
    assert game.presentation[0]['scene'].s.g['combat.positions'][0][:2]==(13,10)
    assert game.presentation[0]['merge'] and game.presentation[1]['scene'].s.g['combat.positions'][0][:2]==(14,10)
    # ov11:1034 calls RedrawMap even for an actor whose turn began off-screen (DS:8E29=0).
    game.presentation_redraw=False
    battle.show('view',enemy,margin=2)
    assert game.presentation_view==(10,7)
    battle.show('view',enemy,margin=2,focus=(21,15))
    assert game.presentation_view==(18,12) and not game.presentation_redraw


def check_queued_cast_panel():
    """Oracle 027/00177..00205: a delayed cast keeps (Casting) on its panel while it fires; the record clears first, and the flag is gone after."""
    from sm.titles.ssb.units import magic
    game, battle, ui = scene(); hero = battle.chars[0]; battle.record(hero)[0] = 5; cast = magic.cast
    magic.cast = lambda g, c, sp, combat=False: g.present('message', actor=0, delay=.1, text='x')
    try: battle.queued_cast(hero)
    finally: magic.cast = cast
    assert game.presentation[-1]['scene'].s.g['casting'] == 0 and game.presentation_casting is None and not battle.record(hero)[0]
    check_gu94_cast_calls()


def check_gu94_cast_calls():
    """GU-94: retained target panel, Begin clear, preflight redraw and hammer NameMessage; virtual events only."""
    game,battle,ui=scene();hero,foe=battle.chars
    battle.record(hero)[0]=28
    game.present('status',actor=1,status=True); game.present('swing',actor=0,spell=28)
    assert not game.presentation[-1]['panel_casting'], 'target inherited caster status'
    game.present('status',actor=0,status=True); battle.record(hero)[0]=0; game.present('clear',actor=0)
    assert game.presentation[-1]['panel_casting'], 'clear lost the previously drawn casting status'
    game.presentation.clear(); assert battle.cast(hero,28)
    assert [e['kind'] for e in game.presentation]==['message','clear']
    game.presentation.clear()
    game.presentation_footer=(bytes(320),)*16
    with patch.object(magic._Magic,'dispatch'):
        assert magic.cast(game,hero,1,[foe],combat=True,consume=False)
    flight=list(game.presentation);raised=next(i for i,e in enumerate(flight) if e['kind']=='swing')
    assert flight[raised+1]['kind']=='redraw' and not flight[raised+1].get('merge')
    assert flight[-2]['kind']=='facing' and flight[-2]['merge']
    assert flight[-1]['kind']=='footer' and flight[-1]['spell_row_cleared']
    game.presentation.clear(); magic._Magic(game).callback(hero,bytearray((0x17,0,0,0,0,0,0,0,0)))
    assert [e['kind'] for e in game.presentation]==['message','clear']
    assert game.presentation[0]['text']=='HERO\ngains an item'


def check_effect_scale():
    """The one speed knob: same frames, same order, same state; only the deadline moves (.3 s hold x .5 = .15 s)."""
    runs = {}
    for scale, t in ((1.0, (0, .29, .31)), (.5, (0, .14, .16)), (0, (0, .001, .002))):
        game, battle, ui = scene(); shops.message(game, 'First'); shops.message(game, 'Second'); ui.set_effect_scale(scale)
        assets = screen.Assets(); before = game.s.hash(game.vm); seed = game.s.seed
        runs[scale] = [screen.render(ui, assets, x).rows for x in t]
        assert game.s.hash(game.vm) == before and game.s.seed == seed, 'the knob changed the game'
    assert runs[1.0][1] == runs[1.0][0] != runs[1.0][2], 'hold at x1'
    assert runs[.5] == runs[1.0] or (runs[.5][0] == runs[1.0][0] and runs[.5][2] == runs[1.0][2] and runs[.5][1] == runs[.5][0]), 'x.5 frames differ'
    assert runs[0][0] == runs[1.0][0] and runs[0][1] == runs[1.0][2], 'x0 must still show every frame, in order'
    game, battle, ui = scene()
    for bad in (-1, 11, 'x', True, None, float('nan')):
        try: ui.set_effect_scale(bad)
        except ValueError: continue
        raise AssertionError('accepted scale %r' % (bad,))


def check_http_playback():
    """44b/48 ov28:03C9: real /key queues input while /frame plays the same saved scene."""
    import json
    from threading import Thread
    from sm.ui.web import Server
    from sm.titles.ssb.ui._web_test import Browser
    game,battle,ui=scene(); ui.session.close=lambda: None
    with Server(ui.session,0) as server:
        server.controller.autosave_enabled=False
        shops.message(game,'HTTP first'); shops.message(game,'HTTP second')
        first=game.presentation[0]
        worker=Thread(target=server.serve,daemon=True); worker.start()
        browser=Browser(server.server_port)
        try:
            assert json.loads(browser.request('/speed')[0])=={'scale':1.0}
            answers=list(ui.session.answers)
            assert json.loads(browser.request('/speed',{'scale':.5})[0])=={'scale':.5} and server.controller.effect_scale==.5 and ui.session.answers==answers
            for bad in ({'scale':-1},{'scale':'x'},{'scale':True},{},[]): browser.request('/speed',bad,status=400)
            browser.request('/speed',{'scale':.5},headers={'X-SM-Build':'old-build'},status=409)
            browser.request('/speed',{'scale':1})
            browser.request('/key',dict(keysym='d',char='d'))
            browser.request('/key',dict(keysym='m',char='m'))
            assert not ui.session.answers
            data,_=browser.request('/frame?t=0')
            assert data==b''.join(screen.render_presentation(server.controller,first,server.assets).rows)
            data,_=browser.request('/layout')
            assert json.loads(data)['animating'] and not json.loads(data)['regions']
            for t in (300,600,700): browser.request('/frame?t='+str(t))
            assert ui.session.answers==[1,0]
        finally:
            browser.close(); server.stopping=True; worker.join(2)
            assert not worker.is_alive()


def test():
    """GU-80 rows 44/47/48/49 plus one headless check for each native display kind."""
    check_messages_and_keys(); check_attack_move_death(); check_continue_and_hp(); check_spell_kinds()
    check_quick_rounds(); check_queued_cast_panel(); check_effect_scale(); check_quick_off(); check_combat_controls(); check_ai_edge_recenter(); check_http_playback()
    print('GU-80 presentation: ordered frames, speed, retained keys, HP, demo, attack/spell kinds and hash parity: PASS')


if __name__ == '__main__': test()

