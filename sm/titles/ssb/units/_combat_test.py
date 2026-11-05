"""Combat V-checks: synthetic records, decode-derived expectations, no original content.

Run: python -I sm/units/_combat_test.py [--routes]
The optional real-game check runs a derived-route fight and the two resolver routes.
"""
from pathlib import Path
import sys

if __name__ == '__main__': sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from sm.titles.ssb import host, vm; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char, State
from sm.titles.ssb.units import combat as C


def character(side=0, hp=40):
    """ov12:09BF fixture: medium, active fighter, ordinary unarmed damage and movement."""
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
    """ov12:1564 fixture with synthetic open GEO, actual Game.ask/VM hashing."""
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
    """PartySweep ov07:0518: a standing member cancels party flight, eleven effect types expire, dead parties unlink."""
    for status, result, count in ((0, 0, 2), (1, 0, 3), (4, 0x81, 1), (6, 0x81, 1), (7, 0x80, 0)):
        g, combat = fixture(); g.engines = True
        g.s.party = [character(), character()]; g.s.monsters = [character(1)]; combat.setup()
        a, b = g.s.party; a.b[C.STATUS], b.b[C.STATUS] = status, 6 if status == 7 else 3
        a.b[C.ACTIVE], b.b[C.ACTIVE] = int(status in (0, 1)), 0
        if status == 1: g.s.party.append(character())                 # ov07:068B..06A1 excludes status1 and the inactive fleer; retain one XP recipient.
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

    # ov07:18EB..194B: the empty party still waits on its defeat message before clearing combat cells.
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
    """ov07:068B/02B9/0357: native-byte-verified exclusion, item boundary, suppression and zero divisor."""
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
    except ZeroDivisionError: pass  # Unchanged System:0294 also faults on the all-excluded synthetic party.
    else: raise AssertionError('native zero-divisor behavior was silently replaced')


def fixed_roll(game, values):
    """ov25:11C6 deterministic die oracle; supplied values are one-based dice."""
    values = iter(values)
    game.s.random = lambda sides: next(values)-1


def check_ai_picker_passes():
    """ov15:3C98..3E05: native-byte audit separates the second terrain pass from visibility bypass."""
    for keep,bypass,visible,expected in ((True,False,True,True),(True,True,False,True),
                                         (True,False,False,False),(False,False,True,False)):
        g,c=fixture(); a,b=c.chars; passes=[]; dice=[]; seen=[]
        c.record(a)[10]=-1
        def targets(*args,ignore_terrain=False,**kwargs):
            """ov26:2B70 fixture: the only enemy is behind terrain."""
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
    # ov11:02D8..02E4 records danger but still rolls every friendly save in this blast.
    from unittest.mock import patch
    g,c=fixture(3); caster,foe,friend=c.chars; friend.b[C.SIDE]=caster.b[C.SIDE]
    c.targets=lambda actor,*args,**kwargs:[foe] if actor is caster else [caster,friend]
    with patch.object(C,'saving_throw',side_effect=[False,True]) as saves:
        assert not c.spell_worth_casting(caster,34,0)
        assert [call.args[1] for call in saves.call_args_list]==[caster,friend]


def check_morale_round_boundary():
    """ov12:16C7 / ov10:0F76 cache HP percent; ov11:13FB tests character intelligence."""
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
    """ov15:1638/16C7: successive attacks count on the defender and retain its first facing."""
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


def check():
    """ov25/32 formula checks + ov12 placement, ov15 actions, ov10 deterministic replay."""
    from copy import deepcopy
    check_award_xp()
    check_party_sweep()
    check_ai_picker_passes()
    check_morale_round_boundary()
    check_defender_facing()

    assert list(C.line(3, 3, 6, 3)) == [(3, 3, 0), (4, 3, 2), (5, 3, 4), (6, 3, 6)]  # ov32:023F
    assert list(C.line(3, 3, 5, 5)) == [(3, 3, 0), (4, 4, 3), (5, 5, 6)]
    assert list(C.line(2, 2, 4, 3)) == [(2, 2, 0), (3, 3, 3), (4, 3, 5)]
    assert C.in_cone(10, 10, 10, 7, 0) and not C.in_cone(10, 10, 13, 10, 0)  # ov32:0543
    for d in range(8): assert C.direction_to(10, 10, 10+3*C.DX[d], 10+3*C.DY[d]) == d
    assert C.direction_to(1, 1, 1, 1) == 8
    assert C.footprint(1) == ((0, 0),) and len(C.footprint(4)) == 4  # ov33:0000 DS:1B12
    assert all(C.terrain_cost(t) == 1 for t in (5, 9, 11, 13, 15, 17, 23, 24, 26, 27, 28, 29, 30))
    assert all(C.terrain_cost(t) == 255 for t in (1, 2, 3, 4, 6, 7, 8, 10, 12, 14))  # ov12 terrain table

    g, c = fixture(); a, b = c.chars
    assert all(c.s.g['combat.positions'][i][2] for i in (0, 1))
    assert set(c.cells(a)).isdisjoint(c.cells(b))  # ov12:0B1C placement must not overlap
    g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 12, 10)
    assert c.walk_line(10, 10, 12, 10, 2) == (True, 4)
    assert c.walk_line(10, 10, 13, 10, 2) == (False, 6)
    c.set_tile(11, 10, 2)
    assert not c.walk_line(10, 10, 12, 10, 2)[0]
    assert c.walk_line(10, 10, 12, 10, 2, True) == (True, 4)
    c.set_tile(11, 10, 23)
    assert c.distance(a, b) == 2
    c.place(b, 11, 11); assert c.distance(a, b) == 1  # diagonals are three halfsteps

    fixed_roll(g, [1, 20, 10, 9])
    assert not C.attack_roll(g, a, b, 0)
    assert C.attack_roll(g, a, b, 100)
    assert C.attack_roll(g, a, b, 50) and not C.attack_roll(g, a, b, 50)  # ov25:103A >=
    g.s.r1[0x371] = 3; fixed_roll(g, [7]); assert C.attack_roll(g, a, b, 50)
    g.s.r1[0x371] = 0
    fixed_roll(g, [1, 20, 10, 9]); a.b[0x19A] = 2
    assert not C.saving_throw(g, a, 0, 100) and C.saving_throw(g, a, 0, -100)
    assert C.saving_throw(g, a, 0) and not C.saving_throw(g, a, 0)  # ov25:1137 threshold
    del g.s.random

    a.b[C.HP] = 10; c.record(a)[0] = 15; a.b[0x1E] = 15
    c.apply_damage(a, 1)
    assert a.b[C.HP] == 9 and c.record(a)[1] == c.record(a)[0] == a.b[0x1E] == 0  # ov15:02D5 interruption
    c.apply_damage(a, 9)
    assert (a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE]) == (0, 4, 0)  # ov26:2953 exact zero unconscious
    a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE] = 10, 0, 1; c.place(a, 10, 10, True)
    c.apply_damage(a, 15)
    assert a.b[C.STATUS] == 5 and c.record(a)[14] == 5  # overkill 1..9 dying, not dead
    assert c.bandage() and a.b[C.STATUS] == 4
    a.b[C.HP], a.b[C.STATUS], a.b[C.ACTIVE] = 10, 0, 1; c.place(a, 10, 10, True)
    c.apply_damage(a, 20); assert a.b[C.STATUS] == 6  # ten overkill dead

    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 20, 10)
    a.b[0x121] = 3; g.s.g['8DC7'] = 0; c.reset_attacks(a); assert a.b[0x1AD] == 1
    g.s.g['8DC7'] = 1; c.reset_attacks(a); assert a.b[0x1AD] == 2  # ov15:0F12 alternating attacks
    c.record(a)[8] = 1; a.b[0x1AD] = 1; c.reset_attacks(a); assert a.b[0x1AD] == 1
    c.record(a)[6] = 3; c.record(a)[3] = 4
    assert 2 in c.legal_moves(a) and 3 in c.legal_moves(a)
    assert 3 not in c.legal_moves(a, ai=True)  # ov11:06BB strict cost < moves
    c.move(a, 2); assert c.position(a) == (11, 10) and c.record(a)[6] == 0  # odd halfstep remainder zeroed
    c.record(a)[6] = 20; c.record(a)[3] = 4; c.guard(a)
    assert c.record(a)[7] == 1 and c.record(a)[3] == c.record(a)[6] == 0
    hp = a.b[C.HP]; fixed_roll(g, [2]); assert not c.flee(a)
    assert a.b[C.STATUS] == 0 and a.b[C.HP] == hp  # ov15:0D96..0DA3: one d2, only one escapes (ov25:11D0/11EB).
    del g.s.random
    b.b[0xED] = 3; c.flee(a); assert a.b[C.STATUS] == 3 and a.b[C.HP] == hp

    # ov15:0902 moving out of melee grants an exhausted enemy one opportunity attack.
    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 11, 10); c.record(a)[6] = 24; c.record(a)[3] = 4
    b.b[0x1AD] = b.b[0x1AE] = 0
    fixed_roll(g, [20, 3]); c.move(a, 6)
    assert a.b[C.HP] == 37 and c.position(a) == (9, 10)
    del g.s.random

    # ov25:1D84 damage save modes, including special-defense dispatch without save.
    g, c = fixture(); a = c.chars[0]
    c.damage(a, 9, 1, True); assert a.b[C.HP] == 40
    c.damage(a, 9, 2, True); assert a.b[C.HP] == 36
    c.damage(a, 9); assert a.b[C.HP] == 27
    snapshot = deepcopy(g.s); old_hash = g.s.hash(g.vm); c.record(a)[6] += 1
    assert g.s.hash(g.vm) != old_hash and snapshot.g['combat.records'][0][6] != c.record(a)[6]

    # ov10:0F61 bleeding advances once per combat round and stops at ten.
    a.b[C.STATUS], a.b[C.ACTIVE], a.b[C.HP] = 5, 0, 0; c.record(a)[14] = 9
    c.end_round(); assert a.b[C.STATUS] == 6 and g.s.r0[0xC7] == 1

    # ov15:2558 delayed casts are reordered; ov15:02D5 damage consumes the queued spell.
    from sm.titles.ssb.units import magic
    g, c = fixture(); a, b = c.chars; g.s.g['combat.tiles'] = [23]*1250
    c.place(a, 10, 10); c.place(b, 12, 10); a.b[0x116] = 6; a.b[0x1E] = 47
    g.s.g['combat.order'] = [0, 1]; g.s.g['combat.cursor'] = 0
    c.record(a)[3] = 5; c.record(b)[3] = 4; c.record(a)[1] = 1
    assert c.cast(a, 47) and c.record(a)[0] == 47
    assert c.record(a)[3] == max(1, 5-magic.spell(47)[12]//3)
    assert g.s.g['combat.order'] == [1, 0] and g.s.g['combat.cursor'] == -1
    c.apply_damage(a, 1); assert c.record(a)[0] == a.b[0x1E] == 0
    # ov25:0466 / ov14:02A9: the magic lane's Bless adds one to a weapon to-hit roll.
    magic.add_effect(g, a, 1, 10); fixed_roll(g, [9])
    assert C.attack_roll(g, a, b, 50); del g.s.random
    magic.remove_effect(g, a, 1)
    # ov23:1E7C magic missile through the real combat facade targets and damages a foe.
    a.b[0x1E] = 15; before = b.b[C.HP]
    g.player = lambda kind, options, game, **info: options.index(1) if kind == 'TARGET' else 0
    assert magic.cast(g, a, 15, combat=True) and b.b[C.HP] < before and a.b[0x1E] == 0
    # ov22:0000 monsters belong to the combat linked list, so their effects expire too.
    magic.add_effect(g, b, 1, 1); c.end_round(); assert not rec.has_effect(b, 1)

    # ov21:2A79 charged items keep a count of one while spending the charge byte.
    item = bytearray(67); item[0x2E] = 0x1F; item[0x34] = item[0x39] = 1; item[0x3C] = 2; item[0x3D] = 15
    a.items.append(item); assert c.use_item(a, 0)
    assert item[0x39] == 1 and item[0x3C] == 1 and len(a.items) == 1
    assert c.use_item(a, 0) and not a.items
    # ov23:647F scroll offsets +3C..3E and the c3 flattened-bundle convention.
    scroll = bytearray(67); scroll[0x2E] = 0x27; scroll[0x2F] = 100; scroll[0x3C] = 15
    a.items.append(scroll); assert c.item_spells(a, 0) == [(15, 0, 0x3C)]
    assert c.use_item(a, 0) and not a.items

    # ov10:011D / host.Game.ask: complete synthetic encounter and exact hash replay.
    def policy(kind, options, game, **info):
        """ov10:0A05/0F61 synthetic test policy: let the real AI fight, then end."""
        return options.index('quick') if kind == 'COMBAT_ACTION' else options.index('end') if info.get('action') == 'continue-battle' else 0
    first, _ = fixture(); first.engines = True; first.player = policy
    C.run(first)
    second, _ = fixture(); second.engines = True; choices = iter(t[6] for t in first.trace)
    second.player = lambda kind, options, game, **info: next(choices)
    C.run(second)
    assert first.trace and first.s.g.get('combat.attacks', 0) > 0
    assert first.trace == second.trace and first.s.hash(first.vm) == second.s.hash(second.vm)


def derived_fight(choices=None):
    """PORT2 scripted run: ov03:1A60 -> ov10:011D on the derived route's first fight.

    The proven prefix keeps its resolvers. At the real combat hook engines=True
    activates the combat port; the real AfterCombat sweep runs before stopping.
    A second run replays the recorded fight choices, with every decision hashed.
    """
    import json
    from sm.titles.ssb import route, resolve
    root = Path(__file__).resolve().parents[4]
    steps = json.loads((root/'herdr/route/derived.json').read_text())
    answers = json.loads((root/'local/answers_derived.json').read_text())
    walker = route.Walk(steps, answers); replay = iter(choices) if choices is not None else None
    recorded = []

    def approach(game, actor):
        """ov10:1194 test policy: BFS over the engine's legal footprint cells to melee."""
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
        """ov07:17B8 stop only after the real VM AfterCombat sweep."""

    def player(kind, options, game, **info):
        """ov10:0A05 deterministic attack/Quick policy; only legal decision options."""
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
        """ov03:1C8C activate engines at the original first combat call site."""
        if game.s.monsters: game.engines = True
        return op24()

    def finish():
        """ov03:1C99 run the VM AfterCombat unchanged, then end this fixture."""
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
    """PORT2 controls: real derived fight replay and both engines=False DONE routes."""
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
            """ov03:1A60 count actual fight map modes without changing route decisions."""
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
