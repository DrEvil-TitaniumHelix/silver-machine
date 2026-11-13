import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch

from sm.titles.ssb import rec
from sm.engine import Session
from sm.titles.ssb.units import combat, shops
from sm.titles.ssb.units._combat_test import fixture, character
from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui._player_screens_test import Fixture, drawing
from sm.titles.ssb.ui._web_test import Browser
from sm.ui.web import Server; from sm.titles.ssb.ui.screen import layout


def arena():
    game, battle = fixture()
    game.s.party = [character(), character(), character()]
    game.s.monsters = [character(1)]
    battle.setup()
    for i, c in enumerate(battle.chars):
        c.b[:5] = (b'\x04HERO', b'\x04ALLY', b'\x04NPC!', b'\x04FOE!')[i]
        game.s.g['combat.positions'][i] = [10 + i, 10, 1]
        battle.record(c)[3] = 1; battle.record(c)[6] = 12
        c.b[0x1AD] = 2
    battle.rebuild()
    return game, battle


def check_move_prompts():
    game, battle = arena(); actor, ally, npc, foe = battle.chars
    npc.b[0xFF] = 0x90; battle.record(npc)[10] = 0
    asked = []
    def answer(kind, options, current, **info):
        asked.append(info)
        ui = screen.Controller(Fixture(current, kind, options, **info))
        assert [label for _, _, label in screen.menu_items(ui.session.decision, current)] == ['Yes', 'No']
        if info.get('action') == 'flee-confirm':
            _, calls = drawing(ui, screen.Assets())
            assert (5,24,'Yes') in calls and (9,24,'No') in calls
            assert [r['rect'] for r in layout(ui)['regions']] == [(40,192,24,8),(72,192,16,8)]
        return 1
    game.player = answer
    before = (ally.b[combat.HP], battle.record(actor)[6], battle.record(actor)[10])
    assert not battle.move_command(actor, 2)
    assert asked[-1]['prompt'] == 'Attack Ally: '
    assert before == (ally.b[combat.HP], battle.record(actor)[6], battle.record(actor)[10])
    assert game.s.r1[0x333] == 0 and npc.b[combat.SIDE] == 0
    game.player = lambda *_args, **_info: 0
    with patch.object(battle, 'attack', return_value=False) as attack:
        assert not battle.move_command(actor, 2)
        assert attack.call_args.args[:2] == (actor, ally)
        assert attack.call_args.kwargs['missile'] is None
    assert game.s.r1[0x333] == game.s.g['8DC6'] == 1
    assert npc.b[combat.SIDE] == 1 and battle.record(npc)[10] == -1
    assert (game.s.g['87CC'], game.s.g['87CD']) == (2, 2)
    game.s.r1[0x333] = 0; actor.b[combat.CTRL] = 1
    with patch.object(game, 'ask', side_effect=AssertionError('controlled attacker prompted')):
        assert battle.confirm_ally(actor, ally)
    assert game.s.r1[0x333] == 0; actor.b[combat.CTRL] = 0
    game, battle = arena(); actor = battle.chars[0]
    with patch.object(battle, 'ranged', return_value=True), patch.object(battle, 'ranged_melee', return_value=False):
        with patch.object(game, 'ask', side_effect=AssertionError('ranged refusal prompted')):
            assert not battle.move_command(actor, 2)
    assert game.vm.out[-1].strip() == 'Not with that weapon'
    assert battle.record(actor)[6] == 12 and actor.b[0x1AD] == 2
    battle.record(actor)[6] = 1
    assert not battle.move_command(actor, 0)
    assert game.vm.out[-1].strip() == "can't go there"
    assert battle.position(actor) == (10, 10) and battle.record(actor)[9] == 0
    battle.record(actor)[6] = 12; battle.set_tile(10, 9, 0)
    game.player = answer
    assert not battle.move_command(actor, 0)
    assert asked[-1]['prompt'] == 'Flee:' and actor.b[combat.ACTIVE]
    game.player = lambda *_args, **_info: 0
    with patch.object(battle, 'flee', return_value=True) as flee:
        assert battle.move_command(actor, 0)
        flee.assert_called_once_with(actor)


def check_taken_ready():
    game, battle = arena(); c = battle.chars[0]
    first, last = bytearray(67), bytearray(67)
    first[0x2E] = first[0x30] = 13
    last[0x2E] = last[0x30] = 10
    first[0x34] = last[0x34] = 1
    first[0x2A:0x2E] = last[0x2A:0x2E] = b'link'
    c.items = [first]; shops.recalc(c)
    game.s.treasure_items = [last]
    game.player = lambda *_args, **_info: 0
    shops.take_items(game, c)
    assert not game.s.treasure_items and c.items[0][0x34] == c.items[1][0x34] == 1
    assert c.items[1][0x2A:0x2E] == bytes(4) and last[0x2A:0x2E] == b'link'
    assert rec.readied(c)[0] is c.items[-1]
    controller = screen.Controller(Fixture(game, 'COMBAT_ACTION', ['done'], actor=0))
    _, calls = drawing(controller, screen.Assets())
    assert any(x == 23 and y == 7 and text == screen.item_name(c.items[-1], game.s.party) for x, y, text in calls)


def check_aim_ally():
    for enemy_near in (False, True):
        game, battle = arena(); actor, ally, npc, foe = battle.chars
        if enemy_near:
            game.s.g['combat.positions'][3][:2] = [10, 9]; battle.rebuild()
        legacy = [battle.index(c) for c in battle.attack_targets(actor)] + ['cancel']
        before = game.s.hash(game.vm)
        assert ally in battle.human_targets(actor) and game.s.hash(game.vm) == before
        questions = []
        def answer(kind, options, current, **info):
            if kind == 'COMBAT_ACTION':
                if info.get('action') == 'attack-ally':
                    questions.append(info); return 0
                return options.index('attack' if enemy_near else 'aim')
            assert kind == 'TARGET'
            if enemy_near: assert options[:len(legacy)] == legacy
            session = Fixture(current, kind, options, **info); ui = screen.Controller(session)
            assert screen.cursor(ui) == battle.position(actor)
            for _ in range(len(battle.chars)):
                ui.key('n', 'n')
                if screen.cursor(ui) == battle.position(ally): break
            assert 'Target' in [word for _, word, _ in screen.target_bar(ui)]
            assert ui.key('t', 't') and options[session.answers[-1]] == 1
            return session.answers[-1]
        game.player = answer
        with patch.object(battle, 'attack', return_value=True) as attack:
            battle.player_turn(actor)
            assert attack.call_args.args[:2] == (actor, ally)
        assert len(questions) == 1 and questions[0]['target'] == 1


def check_aim_and_cast():
    game, battle = arena(); assets = screen.Assets()
    cells = [(x, y) for y in range(5, 15) for x in range(5, 16)]
    options = cells + ['cancel']
    session = Fixture(game, 'TARGET', options, caster=0, spell=47)
    before = game.s.hash(game.vm)
    controller = screen.Controller(session)
    assert screen.cursor(controller) == (10, 10) and controller.selected == options.index((10, 10))
    _, calls = drawing(controller, assets)
    assert (23, 1, 'HERO') in calls
    assert not any(x == 23 and (text.startswith('Aim:') or ',' in text) for x, _, text in calls)
    assert not controller.key('n', 'n') and screen.cursor(controller) == (11, 10)
    assert not controller.key('p', 'p') and screen.cursor(controller) == (10, 10)
    assert not controller.key('m', 'm')
    assert not controller.key('Up') and screen.cursor(controller) == (10, 9)
    assert controller.key('t', 't') and session.answers == [options.index((10, 9))]
    assert session.decision['options'] is options and before == game.s.hash(game.vm)
    ui = screen.Controller(Fixture(game, 'TARGET', [3, 1, 0, 2, 'cancel'], caster=0, spell=25))
    assert screen.cursor(ui) == (10, 10) and ui.selected == 2
    ui.key('n', 'n'); assert screen.cursor(ui) == (11, 10) and ui.selected == 1
    with patch.object(combat.Combat, 'can_see', return_value=False):
        hidden = screen.Controller(Fixture(game, 'TARGET', [3, 1, 0, 2, 'cancel'], caster=0, spell=25))
        assert hidden.aim_cycle == [battle.position(battle.chars[0])]
    ui = screen.Controller(Fixture(game, 'SPELL', [3, 15, 'cancel'], actor=0))
    _, calls = drawing(ui, assets)
    assert (1, 1, "HERO's") in calls and (8, 1, 'Spells in Memory') in calls
    assert [word for _, row, word in calls if row == 24 and len(word) > 1][-3:] == ['Choose Spell:', 'Cast', 'Exit']
    drawn = screen.render(ui, assets)
    menu = screen.Frame()
    for col, word, key in screen.cast_bar(ui):
        menu.text(col, 24, word, assets, 0 if key == 'c' else 13 if not key else 10, background=15 if key == 'c' else 0)
        if key: menu.text(col, 24, word[0], assets, 0 if key == 'c' else 15, background=15 if key == 'c' else 0)
    assert drawn.rows[192:] == menu.rows[192:]
    assert [r['key']['char'] for r in layout(ui)['regions'] if r['rect'][1] == 192] == ['c', 'e']
    assert ui.key('c', 'c') and ui.session.answers == [1]


def check_play_log():
    screen.SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.combat-pass-', dir=screen.SAVE_ROOT) as root:
        path = Path(root) / 'web_play.log'
        with Server(Session(engines=True), 0, save_root=root, presentation=False, log_path=path) as server:
            browser = Browser(server.server_port)
            worker = Thread(target=server.serve, daemon=True); worker.start()
            try:
                initial = browser.decision()
                browser.key('F2')
                browser.request('/key', dict(keys=[dict(keysym='Return', char=''), dict(keysym='Return', char='')]))
                before = browser.decision()
                browser.request('/key', dict(keysym='x', char='x', revision=['stale']))
                browser.request('/key', dict(keysym='bad', char='xx'), status=400)
                assert browser.decision() == before
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                keys = [r for r in rows if r['event'] == 'key']
                assert [(r['keysym'], r['char']) for r in keys] == [('F2', ''), ('Return', ''), ('Return', ''), ('x', 'x'), ('bad', 'xx')]
                assert keys[-2]['stale'] and all(r['time'] and r['instance'] for r in rows)
                decisions = [r for r in rows if r['event'] == 'decision']
                assert decisions[0]['hash'] == initial['hash'] and decisions[0]['i'] == initial['i']
                assert [(r['i'], r['kind'], r['hash']) for r in decisions] == [
                    (t[0], t[1], t[5]) for t in server.controller.session.game.trace] + [(before['i'], before['kind'], before['hash'])]
            finally:
                browser.close(); server.stopping = True; worker.join(3)
                assert not worker.is_alive()
        with Server(Session(engines=True), 0, save_root=root, presentation=False) as server:
            assert server.log_path is None


def check_viewport_and_corners():
    game, battle = arena()
    ui = screen.Controller(Fixture(game, 'TARGET', [3, 'cancel'], actor=0, action='aim'), presentation=True)
    game.presentation_view = (7, 7)
    before = game.s.hash(game.vm)
    ui.key('n', 'n'); ui.key('n', 'n'); ui.key('n', 'n')
    assert screen.cursor(ui) == (13, 10)
    assert screen.player_viewport(ui) == (7, 7), 'automatic Aim scrolled at its inclusive three-cell margin'
    ui.key('c', 'c')
    assert screen.player_viewport(ui) == (10, 7) and screen.cursor(ui) == (13, 10)
    game.presentation_view = (7, 7)
    ui.key('m', 'm')
    assert screen.player_viewport(ui) == (10, 7), 'Manual needs a two-cell margin'
    ui.target_cursor = (49, 24)
    assert screen.player_viewport(ui) == (43, 18)
    ui.target_cursor = (0, 0)
    assert screen.player_viewport(ui) == (0, 0)
    assert before == game.s.hash(game.vm) and not ui.session.answers
    for north, north_east, want in ((0, 0, 9), (0, 1, 13), (3, 0, 24), (3, 1, 11)):
        game, battle = fixture(); x, y = game.s.x, game.s.y
        walls = {(x, y, 0): north, (x, y-1, 2): 1, (x+1, y, 0): north_east}
        seed = game.s.seed
        with patch.object(battle, 'wall', side_effect=lambda xx, yy, d: walls.get((xx, yy, d), 0)):
            battle.build_map()
        assert battle.tile(27, 11) == want, (north, north_east, battle.tile(27, 11))
        assert game.s.seed == seed


def check_inventory_use():
    game, battle = arena(); actor = battle.chars[0]
    old = battle.legal_actions(actor)
    item = bytearray(67); item[0x2E] = item[0x30] = 10; item[0x39] = 1
    actor.items = [item]
    actions = battle.legal_actions(actor)
    assert not battle.usable_items(actor) and [a for a in actions if a != 'use'] == old
    assert actions.index('use') == old.index('quick-off')
    decisions = []
    def answer(kind, options, current, **info):
        decisions.append((kind, info.get('purpose')))
        if len(decisions) == 1: return options.index('use')
        if kind == 'LIST':
            assert info.get('purpose') == 'items' and options == [0, None]
            return options.index(None)
        return options.index('guard')
    game.player = answer
    with patch.object(battle, 'guard') as guard:
        battle.player_turn(actor)
        guard.assert_called_once_with(actor)
    assert decisions == [('COMBAT_ACTION', None), ('LIST', 'items'), ('COMBAT_ACTION', None)]


def check_quit_during_playback():
    game, battle = arena()
    session = Fixture(game, 'COMBAT_ACTION', ['done'], actor=0)
    def close():
        session.decision = None
    session.close = close
    ui = screen.Controller(session, presentation=True)
    game.present('message', actor=0, delay=.1, text='Finishing attack')
    ui.key('F10'); ui.key('q', 'q')
    screen.render(ui, elapsed=0)
    screen.render(ui, elapsed=1)
    screen.render(ui, elapsed=2)
    assert ui.quit_requested and session.decision is None and not ui.held_keys


def check_ai_facing_before_move():
    game, battle = arena(); actor, target = battle.chars[0], battle.chars[-1]
    screen.Controller(Fixture(game, 'COMBAT_ACTION', ['quick'], actor=0), presentation=True)
    game.s.g.update({'59C6': 8, '59C7': 0})
    old = battle.position(actor)
    battle.ai_move(actor, target)
    events = list(game.presentation)
    moved = next(i for i, event in enumerate(events) if event['kind'] == 'move')
    facing = events[moved-1]
    assert facing['kind'] == 'facing', 'AI skipped the pre-move facing draw'
    assert tuple(facing['scene'].s.g['combat.positions'][0][:2]) == old
    assert tuple(events[moved]['scene'].s.g['combat.positions'][0][:2]) != old
    assert facing['scene'].s.g['combat.records'][0][9] == battle.record(actor)[9]


def check_view_items_presentation():
    game, battle = arena(); actor = battle.chars[0]
    session = Fixture(game, 'SHOP_MENU', ['items', 'exit'], purpose='view', record=bytes(actor.b).hex())
    ui = screen.Controller(session, presentation=True)
    before = game.s.hash(game.vm)
    assert ui.key('i', 'i') and session.answers == [0]
    panel = game.presentation_panel
    assert panel.b == bytes(actor.b) and panel.items == tuple(bytes(it) for it in actor.items)
    assert panel.effects == tuple(bytes(e) for e in actor.effects)
    assert game.s.hash(game.vm) == before


def check_move_repeats():
    game, battle = arena(); actor = battle.chars[0]
    battle.set_tile(10, 9, 16)
    choices = [('COMBAT_ACTION', 'move'), ('TARGET', (11, 10)),
               ('COMBAT_ACTION', 'no'), ('TARGET', (10, 9)),
               ('TARGET', (9, 10)), ('TARGET', 'done'), ('COMBAT_ACTION', 'done'), ('MENU', 'guard')]
    seen = []
    def answer(kind, options, current, **info):
        expected, value = choices[len(seen)]
        assert kind == expected, 'Move/Attack exited after a direction or refusal'
        if value == 'done': assert battle.record(actor)[6] == 10
        seen.append((kind, info.get('action')))
        return options.index(value)
    game.player = answer
    battle.player_turn(actor)
    assert len(seen) == len(choices) and battle.position(actor) == (9, 10)
    assert game.s.r1[0x333] == 0
    ui = screen.Controller(Fixture(game, 'MENU', ['delay', 'quit', 'exit', 'speed', 'guard'], actor=0, action='done'))
    assert ui.selected == 4 and screen.player_menu(ui.session.decision)[0][2] == 'Guard'


def check_move_escape_undo():
    for ending in ('cancel', 'done'):
        game, battle = arena(); actor = battle.chars[0]; facing = battle.record(actor)[9]
        choices = ['move', (9, 10), ending, 'guard']; seen = []
        def answer(kind, options, current, **info):
            value = choices[len(seen)]
            if value == 'guard':
                assert battle.position(actor) == ((10, 10) if ending == 'cancel' else (9, 10))
                assert battle.record(actor)[6] == (12 if ending == 'cancel' else 10)
                assert battle.record(actor)[9] == (facing if ending == 'cancel' else 6)
            if kind == 'TARGET': assert info['cursor'] == (len(seen) == 1)
            seen.append(value); return options.index(value)
        game.player = answer; battle.player_turn(actor)
        assert seen == choices
    for key, answer in (('Escape', 1), ('Return', 2), ('d', 2)):
        session = Fixture(game, 'TARGET', [(9, 10), 'cancel', 'done'], actor=0, action='move')
        ui = screen.Controller(session)
        assert ui.key(key, key if len(key) == 1 else '') and session.answers == [answer]


def check_spell_menu_refusal_and_aim_exit():
    game, battle = arena(); actor = battle.chars[0]
    actor.b[0x1E:0x69] = bytes(75); actor.b[0x1E:0x20] = bytes((1, 75))
    actor.b[0x111] = actor.b[0x111] or 1; actor.b[0x15] = 16
    battle.record(actor)[1] = 1
    assert battle.spells(actor) == [1] and battle.spells(actor, all_memorized=True) == [1, 75]
    seed, memory = game.s.seed, bytes(actor.b[0x1E:0x69]); choices = ['cast', 75, 'guard']; seen=[]
    def answer(kind, options, current, **info):
        if kind == 'SPELL': assert options == [1, 'cancel', 75]
        value=choices[len(seen)];seen.append(value);return options.index(value)
    game.player=answer; battle.player_turn(actor)
    assert seen == choices and game.s.seed == seed and bytes(actor.b[0x1E:0x69]) == memory
    actor.b[0x1E]=75
    assert 'cast' in battle.legal_actions(actor), 'camp-only memory wrongly hid Cast'
    ui = screen.Controller(Fixture(game, 'TARGET', [3, 'cancel'], actor=0, action='aim'), presentation=True)
    game.presentation_view=(0,0)
    assert ui.key('Escape') and ui.session.answers == [1] and game.presentation_view == (7,7)
    ui = screen.Controller(Fixture(game, 'COMBAT_ACTION', ['move', 'done'], actor=0))
    assert not ui.key('Escape') and not ui.session.answers


def check_native_d2_branches():
    for seed in (1, 0x5C388495):
        game, battle = arena(); actor = battle.chars[0]; game.s.seed=seed
        reference=game.s.copy(); coin=reference.random(2)+1
        for c, initiative in zip(battle.chars,(10,9,8,7)): battle.record(c)[3]=initiative
        game.s.g['combat.order']=[0,1,2,3];game.s.g['combat.cursor']=0
        assert battle.cast(actor,42)
        assert game.s.seed==reference.seed and battle.record(actor)[0]==42
        assert game.s.g['combat.order']==([1,2,0,3] if coin==1 else [1,0,2,3])
        game, battle = arena(); actor=battle.chars[0];game.s.seed=seed
        with patch.object(battle,'move_allowance',return_value=12):
            assert battle.flee(actor)==(coin==1)
        assert game.s.seed==reference.seed and bool(actor.b[combat.ACTIVE])==(coin!=1)


def check_spell_abort():
    from sm.titles.ssb.units import magic
    game, battle = arena(); caster = battle.chars[0]
    caster.b[magic.MEM:magic.MEM+2] = bytes((23,23)); calls = []; seed = game.s.seed
    def answer(kind, options, current, **info):
        calls.append((kind, info.get('action')))
        assert list(caster.b[magic.MEM:magic.MEM+75]).count(23) == 2
        if kind == 'TARGET':
            ui = screen.Controller(Fixture(current,kind,options,**info))
            screen.init_aim(ui)
            assert 'Target' in [word for _,word,_ in screen.target_bar(ui)]
            assert options[-2:] == ['cancel',0], 'old cancel index must precede appended self'
            return options.index(0) if len(calls)==1 else options.index('cancel')
        assert info['action']=='abort-spell' and not info['cursor']
        ui = screen.Controller(Fixture(current,kind,options,**info))
        assert ui.selected==1 and {r['key']['char'] for r in layout(ui)['regions']}=={'y','n'}
        return 1 if len(calls)==3 else 0
    game.player=answer; caster.b[0x111]=caster.b[0x111] or 1; caster.b[0x15]=16
    assert magic.cast(game,caster,23,combat=True)
    assert calls==[('TARGET',None),('TARGET',None),('MENU','abort-spell'),('TARGET',None),('MENU','abort-spell')]
    assert game.s.seed==seed and list(caster.b[magic.MEM:magic.MEM+75]).count(23)==1
    assert all(not rec.has_effect(c,0x33) for c in battle.chars)


def test():
    check_move_prompts(); check_taken_ready(); check_aim_ally(); check_aim_and_cast(); check_play_log()
    check_viewport_and_corners(); check_inventory_use(); check_quit_during_playback()
    check_ai_facing_before_move(); check_move_repeats(); check_move_escape_undo(); check_view_items_presentation()
    check_spell_menu_refusal_and_aim_exit(); check_native_d2_branches(); check_spell_abort()
    print('rows 45/46/50/51 and ally/refusal/flee prompts: PASS')


if __name__ == '__main__': test()
