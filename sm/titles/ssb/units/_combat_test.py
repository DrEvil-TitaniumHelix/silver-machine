from pathlib import Path
import sys

if __name__ == '__main__': sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from sm.titles.ssb import host, vm; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char, State
from sm.titles.ssb.units import combat as C


def character(side=0, hp=40):
    c = Char(bytes(439)); b = c.b
    b[0x10:0x1C] = bytes([12]*12)
    b[0x6A], b[0x129] = 40, 50
    b[0xE7], b[0xED], b[0xEE], b[0xE6] = 1, 12, 1, 1
    b[0x70] = b[0x131] = b[C.HP] = hp
    b[0x113], b[0x121], b[0x123], b[0x125], b[0x127] = 1, 2, 1, 6, 0
    b[C.SIDE] = b[C.CTRL] = side; b[C.ACTIVE] = 1
    b[0xE8:0xED] = bytes([12]*5); b[0x130] = 4
    return c


def fixture(n=2):
    from types import SimpleNamespace
    g = host.Game.__new__(host.Game); g.s = State(); g.trace = []; g.hashing = True; g.engines = False
    g.player = lambda kind, options, game, **info: 0
    g.geo = SimpleNamespace(passage=lambda s, x, y, d: 1, wall=lambda s, x, y, d: 0, attr=lambda s, x, y: 0)
    g.s.x = g.s.y = 8; g.s.r0[0xE6] = 1; g.s.r1[0x2C1] = 1
    g.s.party = [character()]; g.s.monsters = [character(1) for _ in range(n-1)]
    g.vm = vm.VM(g.s, g.ask, g.geo); g.vm.host = g
    c = C.Combat(g); c.setup()
    return g, c


def check_party_sweep():
    for status, result, count in ((0, 0, 2), (1, 0, 3), (4, 0x81, 1), (6, 0x81, 1), (7, 0x80, 0)):
        g, combat = fixture(); g.engines = True
        g.s.party = [character(), character()]; g.s.monsters = [character(1)]; combat.setup()
        a, b = g.s.party; a.b[C.STATUS], b.b[C.STATUS] = status, 6 if status == 7 else 3
        a.b[C.ACTIVE], b.b[C.ACTIVE] = int(status in (0, 1)), 0
        if status == 1: g.s.party.append(character())
        g.s.r1[0x33E] = len(g.s.party); g.s.treasure_money[0] = 10
        for c in g.s.party:
            c.effects = [bytearray([t]) + bytearray(8) for t in (3, 11, 21, 23, 27, 35, 40, 31, 51, 52, 53, 0x22, 0x69)]
        assert combat.finish() == result, ('finish', status)
        g.combat = None; g.s.sel = 1; g.vm.after_combat_sweep()
        assert g.s.sel == 0, 'ov07:13D8..13E1 resets even a retained, in-range selected member'
        assert g.s.r1[0x2C7] == result and len(g.s.party) == count, ('sweep', status)
        assert g.s.r1[0x33E] == count and g.s.party_dead == (result == 0x80)
        if count:
            assert b.b[C.STATUS] == 0 and b.b[C.ACTIVE] == 1, 'runner restored'
            assert all([e[0] for e in c.effects] == [0x22, 0x69] for c in g.s.party), 'fight effects not stripped'
            assert g.s.treasure_money[0] == (0 if result == 0x81 else 10), 'treasure discarded after partial flight'

    g, _ = fixture(); g.engines = True; g.combat = None
    g.s.g['combat.result'] = 0x80
    for c in g.s.party: c.b[C.STATUS], c.b[C.ACTIVE] = 6, 0
    g.s.r1[0x370] = 9
    item = bytearray(67); item[0x2E] = 0x37; g.s.treasure_items = [item]
    seen = []
    def loss(kind, options, game, **info):
        assert kind == 'MENU' and info['purpose'] == 'combat defeat'
        assert not game.s.party and game.s.r1[0x33E] == 0 and game.s.r1[0x2C7] == 0x80
        assert game.s.r1[0x370] == 9 and game.s.treasure_items == [item]
        seen.append(info['purpose']); return 0
    g.player = loss; g.vm.after_combat()
    assert seen == ['combat defeat'] and g.s.r1[0x370] == 0

    for active, old, expected in ((0, 0, 1), (1, 0, 0), (1, 1, 1)):
        g, _ = fixture(3); g.s.monsters[0].b[C.ACTIVE] = active; g.s.monsters[1].b[C.ACTIVE] = 0
        g.s.r0[0x1F8] = old; g.s.r1[0x33E] = len(g.s.party); g.vm.after_combat_sweep()
        assert g.s.r0[0x1F8] == expected, 'ov07:1315 first monster flag, not any inactive monster'

def check_award_xp():
    g, _ = fixture(); s = g.s; s.monsters = []; s.party = [character(), character(), character()]
    s.r1[0x33E] = 3; s.party[1].b[C.ACTIVE] = 0; s.party[2].b[C.STATUS] = 1
    c = s.party[0]; c.b[0x6C] = 2; c.b[0x11] = 16; s.treasure_money[3] = 1000
    assert g.vm.award_xp(2) == 1000
    assert int.from_bytes(c.b[0x12C:0x130], 'little') == 1100
    assert all(not any(ch.b[0x12C:0x130]) for ch in s.party[1:])
    s.treasure_money[3] = 0; s.treasure_items = [bytearray(67) for _ in range(3)]
    for i, item in enumerate(s.treasure_items, 1): item[0x32] = i
    s.g['combat.treasure_boundary'] = 1
    assert g.vm.award_xp(2) == 400 and int.from_bytes(c.b[0x12C:0x130], 'little') == 1540
    s.r0[0x1F5] = 1
    assert g.vm.award_xp(2) == 2400 and int.from_bytes(c.b[0x12C:0x130], 'little') == 1540
    try: g.vm.award_xp(3)
    except ZeroDivisionError: pass
    else: raise AssertionError('native zero-divisor behavior was silently replaced')


def fixed_roll(game, values):
    values = iter(values)
    game.s.random = lambda sides: next(values)-1


def check_ai_picker_passes():
    for keep,bypass,visible,expected in ((True,False,True,True),(True,True,False,True),
                                         (True,False,False,False),(False,False,True,False)):
        g,c=fixture(); a,b=c.chars; passes=[]; dice=[]; seen=[]
        c.record(a)[10]=-1
        def targets(*args,ignore_terrain=False,**kwargs):
            passes.append(ignore_terrain); return [b] if ignore_terrain else []
        c.targets=targets; c.can_see=lambda *args:seen.append(visible) or visible
        g.s.random=lambda n:dice.append(n) or 0
        assert (c.ai_pick_target(a,bypass,keep=keep) is b)==expected
        assert passes==[False,keep] and dice==([1] if keep else [])
        assert seen==([visible] if keep and not bypass else [])
    g,c=fixture(3); a,b,d=c.chars; draws=iter((0,0,1)); bounds=[]; seen=[]
    c.record(a)[10]=-1; c.targets=lambda *args,**kwargs:[b,d]
    c.can_see=lambda actor,target:seen.append(target) is None and target is d
    g.s.random=lambda n:bounds.append(n) or next(draws)
    assert c.ai_pick_target(a,False) is d and bounds==[2,2,2] and seen==[b,d], 'rejected slot retains its index and dice bound'
    from unittest.mock import patch
    g,c=fixture(3); caster,foe,friend=c.chars; friend.b[C.SIDE]=caster.b[C.SIDE]
    c.targets=lambda actor,*args,**kwargs:[foe] if actor is caster else [caster,friend]
    with patch.object(C,'saving_throw',side_effect=[False,True]) as saves:
        assert not c.spell_worth_casting(caster,34,0)
        assert [call.args[1] for call in saves.call_args_list]==[caster,friend]


def check_morale_round_boundary():
    g, c = fixture(); enemy = g.s.monsters[0]
    assert g.s.g['8E13'] == 100
    enemy.b[C.HP] = 4; c.recount()
    assert g.s.g['8E13'] == 100, 'damage must not change morale HP within a round'
    c.end_round()
    assert g.s.g['8E13'] == 10, 'round end refreshes morale HP'
    c.move_allowance = lambda who: 24 if who is g.s.party[0] else 12
    enemy.b[0xFF] = 128; enemy.b[0x13] = 5; c.record(enemy)[19] = 10
    assert not c.morale(enemy) and enemy.b[C.ACTIVE], 'combatant +13h is not the intelligence gate'
    enemy.b[0x13] = 6; c.record(enemy)[19] = 0
    assert c.morale(enemy) and not enemy.b[C.ACTIVE] and enemy.b[C.STATUS] == 4


def check_defender_facing():
    g, c = fixture(3); first, target, second = c.chars
    g.s.g['combat.tiles'] = [23]*1250
    c.place(first, 11, 9); c.place(target, 10, 10); c.place(second, 9, 9)
    c.record(target)[9] = 7
    for actor in (first, second): actor.b[0x1AD] = actor.b[0x1AE] = 0
    c.face_toward(first, target); c.attack(first, target)
    assert c.record(target)[9] == 1 and c.record(target)[15] == 1
    c.face_toward(second, target); c.attack(second, target)
    assert c.record(target)[9] == 1 and c.record(target)[15] == 2
    assert c.record(target)[18] == 4
    assert all(c.record(actor)[15] == 0 for actor in (first, second))


def check_whole_read_fixes():
    from sm.titles.ssb import data as ssb_data
    def arena(n):
        g, c = fixture(n); g.s.g['combat.tiles'] = [23]*1250
        return g, c
    def said(g, text): return sum(text in line for line in g.vm.out)
    for rolls, misses in (([1, 1], 1), ([20, 3, 1], 0)):
        g, c = arena(2); a, b = c.chars; c.place(a, 10, 10); c.place(b, 11, 10)
        a.b[0x1AD] = 2; c.record(a)[4] = 2; fixed_roll(g, rolls); c.face_toward(a, b); c.attack(a, b)
        assert said(g, 'and Misses') == misses and g.s.g['combat.attacks'] == 2, ('D2', rolls)
    g, c = arena(2); a, b = c.chars; c.place(a, 10, 10); c.place(b, 11, 10)
    c.disabled = lambda who: who is b and b.b[C.HP] < 40
    a.b[0x1AD] = 2; c.record(a)[4] = 2; fixed_roll(g, [20, 3, 1, 4]); c.face_toward(a, b); c.attack(a, b)
    assert b.b[C.HP] == 33, 'D8'
    g, c = arena(2); a, b = c.chars; c.place(a, 10, 10); c.place(b, 11, 10)
    a.b[0x117] = 5; c.record(b)[15] = 2; c.record(b)[9] = 2
    assert c.backstab(a, b), 'D12'
    arrows = bytearray(67); arrows[0x39] = 5; a.items.append(arrows); c.disabled = lambda who: who is b
    a.b[0x1AD] = 1; c.record(a)[4] = 2; c.attack(a, b, missile=arrows)
    assert arrows[0x39] == 4 and not b.b[C.ACTIVE], 'D13'
    g, c = arena(2); a, b = c.chars; c.apply_damage(b, 60)
    assert b.b[C.STATUS] == 6 and said(g, 'goes down') == 1 and said(g, 'is killed') == 1, 'D16'
    table = ssb_data.items_table()
    kind = next(t for t in range(len(table)//16) if table[16*t] == 0 and table[16*t+12] > 2 and table[16*t+14] & 0x14 == 0x14)
    g, c = arena(3); a, near, far = c.chars; c.place(a, 10, 10); c.place(near, 10, 11); c.place(far, 12, 10)
    axe = bytearray(67); axe[0x2E] = kind; axe[0x34] = 1; a.items.append(axe); a.b[0x1AD] = 1; c.record(a)[4] = 2
    assert c.ranged_melee(a) and far in c.attack_targets(a), 'D4'
    fixed_roll(g, [1]); c.face_toward(a, far); c.attack(a, far, missile=axe)
    assert not a.items and g.s.treasure_items[-1][0x2E] == kind and not g.s.treasure_items[-1][0x34], 'D3'
    g, c = arena(4); a = c.chars[0]; foes = c.chars[1:]; c.place(a, 10, 10)
    for foe, (x, y) in zip(foes, ((11, 10), (9, 10), (10, 11))): c.place(foe, x, y); foe.b[0xEE] = 0
    a.b[0x1AD] = 1; c.record(a)[4] = 2; c.record(a)[5] = 3; c.record(a)[3] = 4; fixed_roll(g, [1, 1, 1])
    assert c.sweep(a, foes[1]) and g.s.g['combat.attacks'] == 3 and said(g, 'sweeps') == 1, 'D9'
    assert [c.record(f)[15] for f in foes] == [1, 1, 1], 'D9 victims'
    g, c = arena(2); a, b = c.chars; c.place(a, 10, 10); c.place(b, 20, 10)
    fixed_roll(g, [2]); assert not c.flee(a) and said(g, 'Escape is blocked') == 1
    fixed_roll(g, [1]); assert c.flee(a) and said(g, 'Got Away') == 1 and a.b[C.STATUS] == 3
    g, c = arena(2); a, b = c.chars; a.b[C.STATUS], a.b[C.ACTIVE], a.b[C.HP] = 5, 0, 0
    c.end_round(); assert said(g, 'Your Teammate is Dying') == 1
    assert c.bandage() and said(g, 'is bandaged') == 1
    c.end_round(); assert said(g, 'Your Teammate is Dying') == 1
    for age, status, old, dead in ((110, 0, 0, 0), (120, 0, 1, 0), (121, 8, 0, 1)):
        g, c = arena(2); a = c.chars[0]; a.b[0x6B] = 6; rec.wrw(a.b, 0x6E, age); g.s.g['7D44'] = 1; c.finish()
        assert (a.b[C.STATUS], said(g, 'is looking very old'), said(g, 'dies from age')) == (status, old, dead), ('D11', age)
        assert said(g, 'Sadly, no party member witnesses') == dead


def check_ai_post_fixes():
    out = lambda g: ''.join(g.vm.out)
    g, c = fixture(); npc = g.s.party[0]; x, y = c.position(npc); under = c.tile(x, y)
    c.move_allowance = lambda who: 12 if who is npc else 24
    npc.b[0xFF] = 128; npc.b[0x13] = 6
    assert c.morale(npc) and npc.b[C.STATUS] == 4 and not npc.b[C.ACTIVE] and 'Surrenders' in out(g)
    assert not g.s.g['combat.bodies'] and c.tile(x, y) == under, 'a surrender leaves no body'
    g, c = fixture(); foe = g.s.monsters[0]; c.record(foe)[16] = 1
    assert not c.morale(foe) and c.record(foe)[20] == 1 and 'is forced to flee' in out(g)
    g, c = fixture(); foe = g.s.monsters[0]; c.record(foe)[3] = 5
    c.morale = lambda who: bool(c.record(who).__setitem__(20, 1)) or True
    c.computer_turn(foe); assert 'flees in panic' in out(g)
    g, c = fixture(3); caster, foe, _ = c.chars; calls = []
    c.targets = lambda actor, *a, **k: calls.append((actor, k.get('own'))) or ([foe] if actor is caster else [])
    assert c.spell_worth_casting(caster, 34, 0) and calls[-1] == (foe, [c.position(foe)])
    g, c = fixture(); a, foe = c.chars; ended = []; c.record(a)[3] = 5
    c.targets = lambda *x, **k: []; c.ai_pick_target = lambda *x, **k: foe
    c.ai_move = lambda *x: bool(c.record(a).__setitem__(3, 20))
    assert c.ai_attack_loop(a, lambda: ended.append(1)) is True and not ended and c.record(a)[7] == 0, 'Space in the move step does not guard'
    g, c = fixture(); a = c.chars[0]; ended = []; steps = iter((None, False))
    c.record(a)[3], c.record(a)[6], c.record(a)[20] = 5, 4, 1; c.ai_move = lambda *x: next(steps)
    assert c.ai_attack_loop(a, lambda: ended.append(1) or c.reset(a)) is True and ended == [1], 'a blocked flight step is retried; a refused one ends the round'
    for flag, result in ((0, 0x80), (1, 0)):
        g, c = fixture(); g.s.party[0].b[C.STATUS], g.s.party[0].b[C.ACTIVE] = 6, 0; g.s.r1[0x2E6] = flag
        assert c.finish() == result, ('no-defeat flag', flag)
    g, c = fixture(); foe = g.s.monsters[0]; c.ahead = lambda who, d=8: (-1, 0x17, False, True)
    c.hazards(foe); text = out(g)
    assert foe.b[C.STATUS] == 6 and text.index('is Poisoned') < text.index('is killed')


def check_post_fight_fixes():
    from unittest.mock import patch
    from sm.titles.ssb.units import magic
    g, _ = fixture(); g.combat = None; m = g.s.monsters[0]; m.b[C.STATUS], m.b[C.ACTIVE] = 3, 0
    g.s.g['59C0'] = 0; g.s.r1[0x33E] = 1; g.vm.after_combat_sweep(); assert g.s.g['59C0'] == 1
    g, _ = fixture(); g.combat = None; t = character(); g.s.party.append(t); m = g.s.monsters[0]
    t.b[C.SIDE] = 1; t.b[C.STATUS], t.b[C.ACTIVE] = 6, 0; m.b[C.STATUS], m.b[C.ACTIVE] = 6, 0
    g.s.r1[0x33E] = 2; g.vm.after_combat_sweep()
    assert g.s.party == [g.s.party[0]] and t not in g.s.party and g.s.r1[0x33E] == 1 and g.s.r1[0x2C8] == 2 and g.s.r0[0x1F8] == 1
    g, _ = fixture(); g.engines = True; g.combat = None; g.s.monsters = []; n = character(); g.s.party.append(n)
    n.b[0xFF], n.b[0x100], n.b[0] = 0x80, 1, 3; n.b[1:4] = b'Bob'; g.s.treasure_money[3] = 10; g.s.r1[0x33E] = 2; seen = []
    def player(kind, options, game, **info):
        seen.append((info.get('purpose'), info.get('lines')))
        return options.index('exit') if 'exit' in options else options.index('no') if 'no' in options else 0
    g.player = player; g.vm.after_combat()
    assert seen[0] == ('npc share', ['Bob takes and hides his share.']) and seen[1][0] == 'combat result', seen[:2]
    g, c = fixture(); a = c.chars[0]; c.record(a)[3] = 5
    sid = next(i for i in range(1, 118) if magic.spell(i)[11] and not magic.spell(i)[12]//3)
    with patch.object(magic, 'cast', return_value=False):
        assert c.cast(a, sid) is True and c.record(a)[3] == 0, 'an instant spell that is not cast still ends the turn'
    g, c = fixture(); a = c.chars[0]; c.record(a)[1] = 1
    a.b[0x1E] = next(i for i in range(1, 118) if magic.spell(i)[0] == 3); a.b[C.CTRL] = 0
    assert c.spells(a, all_memorized=True) == [], 'a fighter is not offered a memorised mage spell'
    a.b[0x116], a.b[0x13] = 1, 12
    assert c.spells(a, all_memorized=True) == [a.b[0x1E]]


def check():
    from copy import deepcopy
    check_award_xp()
    check_whole_read_fixes()
    check_party_sweep()
    check_ai_picker_passes()
    check_morale_round_boundary()
    check_ai_post_fixes()
    check_post_fight_fixes()
    check_defender_facing()

    assert list(C.line(3, 3, 6, 3)) == [(3, 3, 0), (4, 3, 2), (5, 3, 4), (6, 3, 6)]
    assert list(C.line(3, 3, 5, 5)) == [(3, 3, 0), (4, 4, 3), (5, 5, 6)]
    assert list(C.line(2, 2, 4, 3)) == [(2, 2, 0), (3, 3, 3), (4, 3, 5)]
    assert C.in_cone(10, 10, 10, 7, 0) and not C.in_cone(10, 10, 13, 10, 0)
    for d in range(8): assert C.direction_to(10, 10, 10+3*C.DX[d], 10+3*C.DY[d]) == d
    assert C.direction_to(1, 1, 1, 1) == 8
    assert C.footprint(1) == ((0, 0),) and len(C.footprint(4)) == 4
    assert all(C.terrain_cost(t) == 1 for t in (5, 9, 11, 13, 15, 17, 23, 24, 26, 27, 28, 29, 30))
    assert all(C.terrain_cost(t) == 255 for t in (1, 2, 3, 4, 6, 7, 8, 10, 12, 14))

    g, c = fixture(); a, b = c.chars
    assert all(c.s.g['combat.positions'][i][2] for i in (0, 1))
    assert set(c.cells(a)).isdisjoint(c.cells(b))
    g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 12, 10)
    assert c.walk_line(10, 10, 12, 10, 2) == (True, 4)
    assert c.walk_line(10, 10, 13, 10, 2) == (False, 6)
    c.set_tile(11, 10, 2)
    assert not c.walk_line(10, 10, 12, 10, 2)[0]
    assert c.walk_line(10, 10, 12, 10, 2, True) == (True, 4)
    c.set_tile(11, 10, 23)
    assert c.distance(a, b) == 2
    c.place(b, 11, 11); assert c.distance(a, b) == 1

    fixed_roll(g, [1, 20, 10, 9])
    assert not C.attack_roll(g, a, b, 0)
    assert C.attack_roll(g, a, b, 100)
    assert C.attack_roll(g, a, b, 50) and not C.attack_roll(g, a, b, 50)
    g.s.r1[0x371] = 3; fixed_roll(g, [7]); assert C.attack_roll(g, a, b, 50)
    g.s.r1[0x371] = 0
    fixed_roll(g, [1, 20, 10, 9]); a.b[0x19A] = 2
    assert not C.saving_throw(g, a, 0, 100) and C.saving_throw(g, a, 0, -100)
    assert C.saving_throw(g, a, 0) and not C.saving_throw(g, a, 0)
    del g.s.random

    a.b[C.HP] = 10; c.record(a)[0] = 15; a.b[0x1E] = 15
    c.apply_damage(a, 1)
    assert a.b[C.HP] == 9 and c.record(a)[1] == c.record(a)[0] == a.b[0x1E] == 0
    c.apply_damage(a, 9)
    assert (a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE]) == (0, 4, 0)
    a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE] = 10, 0, 1; c.place(a, 10, 10, True)
    c.apply_damage(a, 15)
    assert a.b[C.STATUS] == 5 and c.record(a)[14] == 5
    assert c.bandage() and a.b[C.STATUS] == 4
    a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE] = 10, 0, 1; c.place(a, 10, 10, True)
    c.apply_damage(a, 20); assert a.b[C.STATUS] == 6

    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 20, 10)
    a.b[0x121] = 3; g.s.g['8DC7'] = 0; c.reset_attacks(a); assert a.b[0x1AD] == 1
    g.s.g['8DC7'] = 1; c.reset_attacks(a); assert a.b[0x1AD] == 2
    c.record(a)[8] = 1; a.b[0x1AD] = 1; c.reset_attacks(a); assert a.b[0x1AD] == 1
    c.record(a)[6] = 3; c.record(a)[3] = 4
    assert 2 in c.legal_moves(a) and 3 in c.legal_moves(a)
    assert 3 not in c.legal_moves(a, ai=True)
    c.move(a, 2); assert c.position(a) == (11, 10) and c.record(a)[6] == 0
    c.record(a)[6] = 20; c.record(a)[3] = 4; c.guard(a)
    assert c.record(a)[7] == 1 and c.record(a)[3] == c.record(a)[6] == 0
    hp = a.b[C.HP]; fixed_roll(g, [2]); assert not c.flee(a)
    assert a.b[C.STATUS] == 0 and a.b[C.HP] == hp
    del g.s.random
    b.b[0xED] = 3; c.flee(a); assert a.b[C.STATUS] == 3 and a.b[C.HP] == hp

    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 11, 10); c.record(a)[6] = 24; c.record(a)[3] = 4
    b.b[0x1AD] = b.b[0x1AE] = 0
    fixed_roll(g, [20, 3]); c.move(a, 6)
    assert a.b[C.HP] == 37 and c.position(a) == (9, 10)
    del g.s.random

    g, c = fixture(); a = c.chars[0]
    c.damage(a, 9, 1, True); assert a.b[C.HP] == 40
    c.damage(a, 9, 2, True); assert a.b[C.HP] == 36
    c.damage(a, 9); assert a.b[C.HP] == 27
    snapshot = deepcopy(g.s); old_hash = g.s.hash(g.vm); c.record(a)[6] += 1
    assert g.s.hash(g.vm) != old_hash and snapshot.g['combat.records'][0][6] != c.record(a)[6]

    a.b[C.STATUS], a.b[C.ACTIVE], a.b[C.HP] = 5, 0, 0; c.record(a)[14] = 9
    c.end_round(); assert a.b[C.STATUS] == 6 and g.s.r0[0xC7] == 1

    from sm.titles.ssb.units import magic
    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 12, 10); a.b[0x116] = 6; a.b[0x1E] = 47
    g.s.g['combat.order'] = [0, 1]; g.s.g['combat.cursor'] = 0
    c.record(a)[3] = 5; c.record(b)[3] = 4; c.record(a)[1] = 1
    assert c.cast(a, 47) and c.record(a)[0] == 47
    assert c.record(a)[3] == max(1, 5-magic.spell(47)[12]//3)
    assert g.s.g['combat.order'] == [1, 0] and g.s.g['combat.cursor'] == -1
    c.apply_damage(a, 1); assert c.record(a)[0] == a.b[0x1E] == 0
    magic.add_effect(g, a, 1, 10); fixed_roll(g, [9])
    assert C.attack_roll(g, a, b, 50); del g.s.random
    magic.remove_effect(g, a, 1)
    a.b[0x1E] = 15; before = b.b[C.HP]
    g.player = lambda kind, options, game, **info: options.index(1) if kind == 'TARGET' else 0
    assert magic.cast(g, a, 15, combat=True) and b.b[C.HP] < before and a.b[0x1E] == 0
    magic.add_effect(g, b, 1, 1); c.end_round(); assert not rec.has_effect(b, 1)

    item = bytearray(67); item[0x2E] = 0x1F; item[0x34] = item[0x39] = 1; item[0x3C] = 2; item[0x3D] = 15
    a.items.append(item); assert c.use_item(a, 0)
    assert item[0x39] == 1 and item[0x3C] == 1 and len(a.items) == 1
    assert c.use_item(a, 0) and not a.items
    scroll = bytearray(67); scroll[0x2E] = 0x27; scroll[0x2F] = 100; scroll[0x3C] = 15
    a.items.append(scroll); assert c.item_spells(a, 0) == [(15, 0, 0x3C)]
    assert c.use_item(a, 0) and not a.items

    def policy(kind, options, game, **info):
        return options.index('quick') if kind == 'COMBAT_ACTION' else options.index('end') if info.get('action') == 'continue-battle' else 0
    first, _ = fixture(); first.engines = True; first.player = policy
    C.run(first)
    second, _ = fixture(); second.engines = True; choices = iter(t[6] for t in first.trace)
    second.player = lambda kind, options, game, **info: next(choices)
    C.run(second)
    assert first.trace and first.s.g.get('combat.attacks', 0) > 0
    assert first.trace == second.trace and first.s.hash(first.vm) == second.s.hash(second.vm)


def derived_fight(choices=None):
    import json
    from sm.titles.ssb import route, resolve
    root = Path(__file__).resolve().parents[4]
    steps = json.loads((root/'herdr/route/derived.json').read_text())
    answers = json.loads((root/'local/answers_derived.json').read_text())
    walker = route.Walk(steps, answers); replay = iter(choices) if choices is not None else None
    recorded = []

    def approach(game, actor):
        from collections import deque
        fight = game.combat; char = fight.chars[actor]; start = fight.position(char)
        foes = [t for t in fight.chars if t.b[C.ACTIVE] and t.b[C.SIDE] != char.b[C.SIDE]]
        goals = set()
        for foe in foes:
            for x, y in fight.cells(foe):
                for dx, dy in zip(C.DX[:8], C.DY[:8]): goals.add((x+dx, y+dy))
        q = deque([(start, None)]); seen = {start}; occupancy = game.s.g['combat.occupancy']
        while q:
            (x, y), first = q.popleft()
            if first is not None and (x, y) in goals: return first
            for d in range(8):
                nx, ny = x+C.DX[d], y+C.DY[d]
                if (nx, ny) in seen: continue
                cells = fight.cells(char, nx, ny)
                if not cells or any(not (0 <= a < 50 and 0 <= b < 25) or not fight.tile(a, b)
                                    or C.terrain_cost(fight.tile(a, b)) == 255 or occupancy[b*50+a] not in (0, actor+1) for a, b in cells): continue
                seen.add((nx, ny)); q.append(((nx, ny), (nx, ny) if first is None else first))
        return None

    class Finished(Exception):
        pass

    def player(kind, options, game, **info):
        if not game.engines: return walker(kind, options, game, **info)
        if kind == 'TREASURE': resolve.resolve(kind, game); return 0
        if replay is not None: answer = next(replay)
        elif kind == 'COMBAT_ACTION':
            step = approach(game, info['actor']) if 'move' in options and 'attack' not in options else None
            action = 'attack' if 'attack' in options else 'move' if step is not None else 'guard' if 'guard' in options else 'done'
            answer = options.index(action)
        elif kind == 'TARGET' and info.get('action') == 'move':
            step = approach(game, info['actor']); answer = options.index(step) if step in options else 0
        elif kind in ('TARGET', 'SPELL', 'LIST'): answer = 0
        elif kind == 'MENU' and info.get('action') == 'continue-battle': answer = options.index('end')
        elif kind == 'MENU' and info.get('action') == 'done': answer = options.index('quit')
        else: raise AssertionError(('unexpected combat decision', kind))
        recorded.append(answer); return answer

    game = host.Game(player)
    op24, after = game.vm.op24, game.vm.after_combat

    def enter():
        if game.s.monsters: game.engines = True
        return op24()

    def finish():
        after()
        if game.engines: raise Finished()

    game.vm.op24, game.vm.after_combat = enter, finish
    try: game.play(limit=100_000)
    except Finished: pass
    else: raise AssertionError('derived prefix did not reach a combat')
    assert game.s.g.get('combat.attacks', 0) > 0
    assert not game.s.monsters and any(t[1] == 'COMBAT_ACTION' for t in game.trace)
    assert not game.s.party_dead, 'scripted derived fight lost'
    assert game.s.g['87CD'] == 0, 'scripted fight reached round limit with enemies alive'
    return game, recorded


def route_checks():
    import json, time
    from sm.titles.ssb import route, player
    root = Path(__file__).resolve().parents[4]; start = time.perf_counter()
    a, choices = derived_fight(); b, replayed = derived_fight(choices)
    assert choices == replayed and a.trace == b.trace and a.s.hash(a.vm) == b.s.hash(b.vm)
    print('derived engines=True fight: decisions=%d attacks=%d rounds=%d result=%d replay=equal' %
          (len(choices), a.s.g['combat.attacks'], a.s.g['8DC7'], a.s.g['combat.result']))
    for name, steps, answers in (
        ('derived', json.loads((root/'herdr/route/derived.json').read_text()), json.loads((root/'local/answers_derived.json').read_text())),
        ('walkthrough', *route.load_steps()),
    ):
        walker = route.Walk(steps, answers); fights = [0, 0]
        def observe(kind, options, game, **info):
            if kind == 'COMBAT': fights[int(bool(game.s.r0[0xE6]))] += 1
            return walker(kind, options, game, **info)
        g = host.Game(observe); result = g.play(limit=500_000)
        assert result == 'DONE', (name, result)
        result2, replay = player.run([t[6] for t in g.trace])
        assert result2 == 'DONE' and g.trace == replay.trace, (name, result2, 'replay differs')
        assert fights[0] == 0, (name, '2D fight requires the unresolved ov12:0939 map loader')
        print('%s engines=False: DONE decisions=%d fights3D=%d fights2D=%d replay=equal' % (name, len(g.trace), fights[1], fights[0]))
    print('route controls: %.2fs' % (time.perf_counter()-start))


if __name__ == '__main__':
    check(); print('combat formula/state checks: PASS')
    if '--routes' in sys.argv: route_checks()
