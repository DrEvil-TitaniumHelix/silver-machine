from types import SimpleNamespace
from unittest.mock import patch

from . import effects, effects_handlers as handlers, rules
from .data import Assets
from .records import Character, Spells, Item

F, I = rules.F, handlers.I


class Dice:
    def __init__(self, *faces):
        self.faces, self.calls = list(faces), []
        self.g, self.mode = {}, 0

    def random(self, sides):
        self.calls.append(sides)
        value = self.faces.pop(0) if self.faces else 1
        assert 1 <= value <= sides, (value, sides)
        return value - 1


class Fight:
    def __init__(self, chars):
        self.chars, self.events = chars, []
        self.data = {'round': 1, 'hits_made': 2}
        self.records = [dict(target=(i + 1) % len(chars), initiative=5, movement=8,
                             item_ok=True, cast_ok=True, casting=0, turned=0) for i in range(len(chars))]
        self.held, self.scrolls = None, []

    def index(self, char): return next(i for i, value in enumerate(self.chars) if value is char)
    def position(self, index): return (5, 5)
    def scroll(self, x, y, margin=2, direction=8): self.scrolls.append((x, y, margin))
    def event(self, *args, **values): self.events.append(('event', values))
    def record(self, index): return self.records[index]
    def teams(self): return [sum(c.b[F['side']] == side for c in self.chars) for side in (0, 1)]
    def weapon(self, index): return self.held
    def targets(self, index, reach, allies=False): return [index] + [i for i in range(len(self.chars)) if i != index]

    def end(self, char):
        self.record(self.index(char)).update(initiative=0, movement=0, casting=0)

    def add_with_message(self, index, kind, minutes, strength, on_remove, text, saved=False, negates=0):
        self.events.append(('add', index, kind, minutes, strength, on_remove, text, saved, negates))
        if not saved or negates != 1: effects.add_effect(self.chars[index], kind, minutes, strength, on_remove)

    def kill(self, index, status, message):
        self.events.append(('kill', index, status, message))

    def spell_damage(self, char, roll, reduction, saved):
        self.events.append(('damage', self.index(char), roll.damage, roll.element, roll.dice_count, reduction, saved))


def said(messages):
    return [m for m in messages if m != (None, 'pause')][-1][1]


def fixture():
    chars = [rules.character(bytes(Character()), spells=bytes(Spells())) for _ in range(3)]
    for i, char in enumerate(chars):
        for key, value in dict(hp=10, hp_max=20, active=1, race=6, side=int(i > 0), base_ac=50).items():
            char.b[F[key]] = value
        char.b[F['ac']:F['ac'] + 2] = bytes((55, 53))
    game = SimpleNamespace(assets=Assets(), s=Dice(), battle=Fight(chars))
    messages, saves = [], []
    def saving(char, kind, modifier):
        saves.append((game.battle.index(char), kind, modifier))
        return False
    services = dict(message=lambda char, text: messages.append((game.battle.index(char), text)),
                    saving_throw=saving, end_actions=game.battle.end,
                    clear_target=lambda char: handlers.actor(game, char).update(target=-1),
                    set_turned=lambda char, value: handlers.actor(game, char).update(turned=value),
                    distance=lambda a, b: 2, damaging_weapon=lambda char: game.battle.held,
                    neighbours=lambda char: [c for c in chars if c is not char],
                    pause=lambda: messages.append((None, 'pause')))
    game.battle.context = lambda char: effects.Roll(attacker=char, in_combat=True, services=services)
    return game, chars, messages, saves, services


def run(game, char, ident, services, removed=False, strength=0, node=None, **values):
    node = node if node is not None else bytearray((ident, 0, 0, strength, 0, 0, 0, 0, 0))
    if 'attacker' not in values: values['attacker'] = game.battle.chars[1]
    roll = effects.Roll(services=services, **values)
    effects.call_handler(game, char, ident, node, removed, roll)
    return roll, node


def test():
    game, chars, messages, saves, services = fixture()
    char, foe, other = chars
    for damage, expected in ((0, 254), (1, 255), (2, 0), (255, 253)):
        roll, _ = run(game, char, 108, services, damage=damage, attack=8)
        assert (roll.damage, roll.attack) == (expected, 6)
    for attack, expected in ((-128, 126), (-127, 127), (-126, -128), (127, 125)):
        assert run(game, char, 108, services, damage=2, attack=attack)[0].attack == expected
    for con, kind, expected in ((3, 0, 5), (4, 0, 6), (13, 2, 8), (20, 4, 10), (21, 4, 5), (12, 1, 5)):
        char.b[F['abilities'] + 9] = con
        assert run(game, char, 94, services, save_type=kind, save=5)[0].save == expected
    for ident, element, damage, saved, expected in (
        (10, 2, 11, False, (5, 3)), (10, 1, 11, False, (11, 0)),
        (20, 1, 11, False, (5, 3)), (20, 2, 11, False, (11, 0)),
        (50, 2, 9, False, (9, 2)), (50, 1, 130, False, (4, 0)),
        (50, 1, 130, True, (130, 0)), (54, 1, 9, False, (9, 2)),
        (54, 2, 130, True, (4, 0)), (65, 4, 15, False, (0, 0)),
        (75, 2, 130, False, (4, 0)), (83, 6, 11, False, (5, 0)),
        (29, 0, 11, False, (9, 0))):
        roll, _ = run(game, char, ident, services, element=element, damage=damage, save_passed=saved)
        assert (roll.damage, roll.save) == expected, (ident, roll)
    game.s.g['save.recent'] = 1
    assert run(game, char, 54, services, element=2, damage=130)[0].damage == 130
    assert run(game, char, 20, services, removed=True, element=1, damage=11)[0].damage == 11
    for ident, expected in ((13, (53, 51)), (33, (51, 49)), (57, (51, 49)), (60, (59, 57))):
        char.b[F['ac']:F['ac'] + 2] = bytes((55, 53))
        run(game, char, ident, services)
        assert tuple(char.b[F['ac']:F['ac'] + 2]) == expected
    char.b[F['ac']:F['ac'] + 2] = bytes((55, 53))
    roll, _ = run(game, char, 17, services, spell=15, damage=20)
    assert char.b[F['ac']] == 57 and char.b[F['ac'] + 1] == 53 and (roll.damage, roll.save) == (0, 1)
    for ident, limit in ((59, 5), (63, 4)):
        for level, expected in ((limit - 1, 0), (limit, 10)):
            with patch('sm.titles.dkk.magic.spell', return_value=SimpleNamespace(level=level)):
                roll, _ = run(game, char, ident, services, spell=1, damage=10, effect=11)
                assert roll.damage == expected and roll.effect == (0 if not expected else 11)
        assert run(game, char, ident, services, spell=0, damage=10)[0].damage == 10
    for effect_id in (11, 35, 52, 61, 111, 53):
        roll, _ = run(game, char, 58, services, effect=effect_id, damage=9)
        assert roll.damage == (9 if effect_id == 53 else 0)
    with patch('sm.titles.dkk.magic.spell', return_value=SimpleNamespace(save_type=4)):
        assert run(game, char, 48, services, spell=1)[0].save == 0
        assert run(game, char, 48, services, spell=0)[0].save == 1
    roll, _ = run(game, char, 65, services, element=4, effect=11, damage=9)
    assert (roll.damage, roll.effect) == (0, 11)
    roll, _ = run(game, char, 73, services, element=32, effect=11, damage=9)
    assert (roll.damage, roll.effect) == (0, 0)
    assert messages[-2][1] == game.assets.text('unaffectedMessage') and messages[-1] == (None, 'pause')
    for ident, strength in ((39, 0), (39, 16), (42, 0)):
        before = rules.record(char).get('age')
        roll, node = run(game, char, ident, services, strength=strength, multiplier=3)
        assert roll.multiplier == (6 if ident == 39 else 1)
        assert rules.record(char).get('age') == before + int(ident == 39 and strength == 0)
        after = rules.record(char).get('age')
        assert run(game, char, ident, services, node=node, removed=True, multiplier=3)[0].multiplier == 3
        assert rules.record(char).get('age') == after
    assert game.age_pass
    roll, _ = run(game, char, 25, services)
    assert roll.target_veto and roll.attack == -4
    effects.add_effect(foe, 24, 0, 0, False)
    assert not run(game, char, 25, services)[0].target_veto
    foe.effects.clear()
    for race, level, plus, expected in ((6, 9, 2, 0), (6, 9, 3, 12), (7, 3, 2, 0), (7, 4, 0, 12)):
        item = bytearray(Item.SIZE); item[I['bonus']] = plus
        game.battle.held = item
        foe.b[F['race']], foe.b[F['highest_level']] = race, level
        assert run(game, char, 66, services, damage=12)[0].damage == expected
    game.battle.held = bytearray(Item.SIZE)
    assert run(game, char, 41, services, in_combat=True, damage=10)[0].damage == 0
    assert game.s.calls[-1] == 100 and game.battle.data['hits_made'] == 1
    calls = len(game.s.calls)
    game.battle.held[I['bonus']] = 1
    assert run(game, char, 41, services, in_combat=True, damage=10)[0].damage == 10
    assert len(game.s.calls) == calls
    for ident, element, damage, count, expected_hp, expected_calls in (
        (76, 9, 8, 2, 18, []), (76, 1, 8, 2, 10, []), (87, 9, 8, 2, 18, []),
        (87, 4, 8, 2, 10, []), (101, 12, 8, 2, 12, []), (101, 9, 8, 2, 10, [6, 6])):
        char.b[F['hp']] = 10; char.effects.clear(); game.s = Dice(3, 4)
        roll, _ = run(game, char, ident, services, element=element, damage=damage, effect=11, dice_count=count)
        assert (char.b[F['hp']], roll.damage, roll.effect) == (expected_hp, 0, 0)
        assert game.s.calls == expected_calls
        if ident == 87 and element == 4 or ident == 101 and element == 9:
            node = effects.has_effect(char, 42)
            assert int.from_bytes(node[1:3], 'little') == (3 if ident == 87 else 7)
    char.b[F['hp']], char.b[F['hp_max']] = 254, 255
    run(game, char, 84, services)
    assert char.b[F['hp']] == 1
    char.b[F['hp']], char.b[F['hp_max']] = 10, 20
    game.battle.data['round'] = 0
    roll, node = run(game, char, 89, services, in_combat=True, strength=255)
    assert node[3] == 15
    game.battle.data['round'] = 1
    roll, node = run(game, char, 89, services, in_combat=True, node=node, attack=12)
    assert roll.attack == -1 and node[3] == 31
    assert run(game, char, 89, services, in_combat=True, node=node, attack=12)[0].attack == 12
    char.b[F['side']] = 0
    roll, node = run(game, char, 11, services, in_combat=True, strength=128)
    assert char.b[F['side']] == 1 and char.b[F['npc']] == 179 and node[3] == 160 and roll.morale == 100
    run(game, char, 11, services, in_combat=True, node=node, removed=True)
    assert (char.b[F['side']], char.b[F['npc']], char.b[F['auto_combat']]) == (0, 0, 0)
    from .camp import F as memory_fields
    char.b[memory_fields['memorized']] = 15
    actor = game.battle.records[0]
    actor.update(item_ok=True, casting=15, initiative=5)
    run(game, char, 21, services, in_combat=True)
    assert not actor['item_ok'] and not actor['cast_ok'] and actor['initiative'] == actor['casting'] == 0
    assert char.b[memory_fields['memorized']] == 143
    assert [m[1] for m in messages[-4:]] == [game.assets.text('silencedText'), 'pause', game.assets.text('lostSpellMessage'), 'pause']
    count = len(messages)
    run(game, char, 21, services, in_combat=True)
    assert len(messages) == count
    actor.update(target=1, initiative=5)
    foe.effects.clear(); saves.clear()
    run(game, char, 2, services, in_combat=True)
    assert saves == [(1, 1, 0)] and effects.has_effect(foe, 6)[1] == 3
    effects.add_effect(foe, 116, 0, 7, False)
    run(game, char, 64, services, in_combat=True)
    assert saves[-1] == (1, 0, 7) and effects.has(foe, 55)
    assert messages[-2:] == [(1, game.assets.text('poisonedMessage')), (None, 'pause')]
    run(game, char, 86, services, in_combat=True)
    assert saves[-1] == (1, 0, 0)
    foe.b[F['target_flags']] = 8
    before = len(game.battle.events)
    run(game, char, 64, services, in_combat=True)
    assert saves[-1] == (1, 0, 7) and len(game.battle.events) == before
    foe.b[F['target_flags']] = 0
    for race in (0, 1, 2, 200):
        foe.effects.clear(); foe.b[F['race']] = race; saves.clear()
        run(game, char, 88, services, in_combat=True)
        assert bool(saves) == (1 < race < 128)
        if 1 < race < 128: assert bytes(effects.has_effect(foe, 52)[1:5]) == bytes((100, 0, 12, 0))
    char.effects.clear(); effects.add_effect(char, 62, 1, 255, True)
    char.b[F['hp']] = 19
    services['message'] = lambda c, text: messages.append((0, text))
    node = char.effects[0]
    run(game, char, 62, services, node=node, removed=True)
    assert char.b[F['hp']] == 20 and char.effects[-1][1] == 60
    assert said(messages) == game.assets.text('fullyHealedText')
    game.effect_busy = True
    before = len(char.effects)
    run(game, char, 62, services, node=node, removed=True)
    assert len(char.effects) == before
    game.effect_busy = False
    char.effects.clear(); effects.add_effect(char, 15, 1, 12, True)
    char.b[F['hp']] = 1
    run(game, char, 15, services, node=char.effects[0], removed=True)
    assert char.b[F['hp']] == 1 and len(char.effects) == 2 and char.effects[-1][1] == 10
    asked = []
    camp_game = SimpleNamespace(assets=game.assets, s=game.s, battle=None, ask=lambda kind, options, **info: asked.append(info))
    char.effects.clear(); effects.add_effect(char, 15, 1, 12, True)
    char.b[F['hp']] = 5
    run(camp_game, char, 15, dict(services), node=char.effects[0], removed=True, attacker=foe)
    t = game.assets.text
    assert char.b[F['hp']] == 4 and asked[-1]['timed'] == 1 and asked[-1]['prompt'].endswith(t('onePointDamage') + t('fromMagic'))
    foe.effects.clear(); foe.b[F['creature_type']] = 0; handlers.actor(game, char).update(target=1); messages.clear()
    run(game, char, 34, services, in_combat=True)
    assert messages == [(0, t('resistsDispelEvilText')), (None, 'pause'), (None, 'pause')]
    char.effects.clear(); effects.add_effect(char, 15, 1, 12, True); effects.add_effect(char, 55, 0, 255, False)
    run(game, char, 22, services, in_combat=True)
    assert effects.has(char, 55) and not effects.has(char, 15) and not game.effect_busy
    assert game.battle.events[-1][0:3] == ('kill', 0, 4)
    game.s = Dice(1, 6); game.battle.events.clear(); game.battle.s = SimpleNamespace(seed=0, random=lambda sides: 0)
    run(game, char, 70, services, in_combat=True, element=4)
    assert game.battle.events[0][1]['points'] == 16 and game.battle.data['aim'] == (5, 5)
    assert game.battle.scrolls == [(5, 5, 255), (5, 5, 255)]
    assert [row[2:5] for row in game.battle.events[1:]] == [(1, 1, 1), (6, 1, 1)]
    services['distance'] = lambda a, b: 1
    roll, _ = run(game, char, 112, services, in_combat=True, damage=130, element=2)
    assert (roll.damage, roll.element) == (130, 2)
    assert game.battle.events[-1][2:4] == (4, 8)
    char.effects.clear(); foe.effects.clear(); other.effects.clear(); saves.clear()
    char.b[F['side']], foe.b[F['side']], other.b[F['side']] = 0, 1, 1
    run(game, char, 79, services, in_combat=True)
    assert len(char.effects) == 2 and all(n[0] == 118 for n in char.effects)
    assert not foe.effects and not other.effects and len(saves) == 2
    item = bytearray(Item.SIZE); item[I['powers'] + 1] = 5
    handlers.grant_item_effect(game, char, item)
    assert bytes(effects.has_effect(char, 5)[:5]) == bytes((5, 0, 0, 255, 1))
    handlers.grant_item_effect(game, char, item, True)
    assert not effects.has(char, 5) and not game.handler_override_active
    char.effects.clear()
    for _ in range(2): effects.add_effect(char, 5, 0, 255, False)
    first, second = char.effects
    effects.remove_effect(game, char, 5, second)
    assert len(char.effects) == 1 and char.effects[0] is first
    char.effects.clear()
    with patch.object(rules, 'recalc_stats') as recalc:
        char.items.clear(); char.b[F['item_count']] = 0
        run(game, char, 23, services)
        assert len(char.items) == 1 and char.items[0][I['readied']] == 0
        assert char.items[0][I['bonus']] == 1 and char.items[0][I['powers'] + 1] == 23
        slot = game.item_pool.slots[0]
        assert char.items[0] is slot and slot[I['type']] == 6
        run(game, char, 23, services)
        assert len(char.items) == 1
        run(game, char, 23, services, removed=True)
        assert not char.items and recalc.call_count == 3 and slot[I['type']] == 0
        char.b[F['item_count']] = 16
        run(game, char, 23, services)
        assert not char.items
    actor.update(target=1)
    foe.b[F['target_flags']] = 1
    char.b[F['hp']] = 17
    assert run(game, char, 114, services, in_combat=True, damage=5)[0].damage == 17
    foe.b[F['creature_type']] = 32
    assert run(game, char, 115, services, in_combat=True, damage=254)[0].damage == 1
    foe.b[F['creature_type']], foe.b[F['undead']] = 2, 4
    before = len(game.battle.events)
    assert run(game, char, 117, services, in_combat=True, damage=130)[0].damage == 4
    assert len(game.battle.events) == before
    foe.b[F['creature_type']] = 0
    run(game, char, 117, services, in_combat=True, damage=12)
    assert game.battle.events[-1][0:3] == ('kill', 1, 8)
    for ident in (77, 107):
        char.b[F['side']], char.b[F['npc']], char.b[F['auto_combat']] = 1, 0, 0
        foe.b[F['side']] = 0
        actor.update(cast_ok=True)
        roll, node = run(game, char, ident, services, in_combat=True, strength=1)
        assert (char.b[F['side']], char.b[F['npc']], char.b[F['auto_combat']]) == (1, 179, 1)
        assert actor['cast_ok'] == (ident == 107)
        run(game, char, ident, services, in_combat=True, node=node, removed=True)
        assert (char.b[F['side']], char.b[F['npc']], char.b[F['auto_combat']]) == ((0, 0, 0) if ident == 77 else (1, 0, 1))
        seen = game.battle.targets
        game.battle.targets = lambda *args, **options: [0]
        char.b[F['side']] = 0
        run(game, char, ident, services, in_combat=True, strength=1)
        assert (char.b[F['side']], actor['target']) == (0, -1)
        game.battle.data['target_list'] = [0, 1]
        run(game, char, ident, services, in_combat=True, strength=1)
        assert (char.b[F['side']], actor['target']) == (1, 1)
        del game.battle.data['target_list']
        game.battle.targets = seen
        actor.update(target=1)
    for face, expected in ((1, 'runsAwayText'), (11, 'confusedText'), (60, 'confusedText'),
                           (61, 'berserkText'), (80, 'berserkText'), (81, 'enragedText'), (100, 'enragedText')):
        char.effects.clear(); effects.add_effect(char, 35, 10, 0, False)
        game.s = Dice(face); messages.clear(); game.battle.events.clear(); saves.clear()
        actor.update(initiative=5)
        run(game, char, 35, services, in_combat=True)
        assert game.s.calls == [100] and saves[-1] == (0, 4, 254)
        if face == 1: assert effects.has(char, 111) and not effects.has(char, 35) and actor['turned']
        elif face <= 60: assert actor['initiative'] == 0 and said(messages) == game.assets.text(expected)
        elif face <= 80: assert effects.has(char, 77) and said(messages) == game.assets.text(expected)
        else: assert actor['initiative'] == 5 and said(messages) == game.assets.text(expected)
    game.s = Dice(2, 2)
    node = bytearray((28, 0, 0, 48, 0, 0, 0, 0, 0)); char.effects[:] = [node]
    roll, _ = run(game, char, 28, services, node=node, damage=12, effect=11)
    assert (node[3], roll.damage, roll.effect) == (47, 0, 0)
    roll, _ = run(game, char, 28, services, node=node, damage=12, spell=47, multi_target=1)
    assert (node[3], roll.damage) == (47, 12) and game.s.calls == [4, 3]
    actor.update(item_ok=True, casting=15, initiative=5)
    with patch.object(rules, 'recalc_stats'):
        char.b[F['ac']:F['ac'] + 2] = bytes((51, 50))
        run(game, char, 30, services, in_combat=True)
        assert tuple(char.b[F['ac']:F['ac'] + 2]) == (49, 48)
    assert actor['casting'] == 15 and actor['initiative'] == 5 and not actor['cast_ok']
    char.effects.clear(); foe.effects.clear()
    char.b[F['creature_type']] = 64
    effects.add_effect(foe, 24, 0, 255, False)
    assert run(game, char, 32, services)[0].target_veto
    effects.add_effect(char, 24, 0, 255, False)
    assert not run(game, char, 32, services)[0].target_veto
    game.s = Dice(2, 6); saves.clear(); actor.update(target=1)
    run(game, char, 74, services, in_combat=True, element=1)
    assert game.battle.events[-1][2:] == (8, 0, 2, 2, False) and saves == [(1, 4, 0)]
    test_engine()
    test_aging()
    test_drain()
    test_abilities()
    test_stat_movement()
    test_area()


def test_stat_movement():
    for ident in (23, 30):
        for bonus, side, expected in ((0, 0, 12), (5, 0, 17), (120, 0, 4), (250, 0, 6), (5, 1, 12)):
            game, chars, messages, saves, services = fixture()
            char = chars[0]
            game.s.r1 = bytearray(1024)
            game.s.r1[0x372] = bonus
            char.b[F['base_move']], char.b[F['side']] = 12, side
            char.b[F['abilities']:F['abilities'] + 12] = bytes([10] * 12)
            run(game, char, ident, services, in_combat=True)
            assert char.b[F['move']] == expected, (ident, bonus, side, char.b[F['move']])
            if ident == 23:
                run(game, char, ident, services, in_combat=True, removed=True)
                assert char.b[F['move']] == expected and not char.items


def area_fixture():
    from .combat import Battle
    game, chars, messages, saves, services = fixture()
    battle = game.battle
    battle.game = game
    battle.body_state = lambda: Battle.body_state(battle)
    battle.data.update(actor=1, clouds=[], downed=[], downed_who=[])
    game.s.sel = 2
    tiles, writes = {}, []
    battle.tile = lambda x, y: tiles.get((x, y), 23)
    battle.put_tile = lambda x, y, tile: (tiles.__setitem__((x, y), tile), writes.append((x, y, tile)))
    battle.cells = lambda index: [(4, 5), (5, 5)]
    services['terrain_view'] = lambda char: battle.events.append(('view', battle.index(char)))
    services['pause'] = lambda: battle.events.append(('pause',))
    services['bottom_line'] = lambda text: battle.events.append(('bottom', text))
    battle.context = lambda char=None: effects.Roll(attacker=char, in_combat=True, services=services)
    return game, chars[0], tiles, writes, messages, saves, services


def test_area():
    from . import effects_area as area, magic
    game, char, tiles, writes, messages, saves, services = area_fixture()
    battle = game.battle
    first = dict(cells=[(4, 5, 23), (5, 5, 24)], terrain=29, countdown=2)
    second = dict(cells=[(4, 5, 25)], terrain=28, countdown=-1)
    last = dict(cells=[(6, 5, 26)], terrain=29, countdown=0)
    clouds = battle.data['clouds']
    clouds[:] = [first, second, last]
    area.refresh_area(battle)
    assert writes == [(4, 5, 29), (5, 5, 29), (4, 5, 28), (6, 5, 29)]
    writes.clear()
    battle.data.update(downed=[(4, 5, 23), (5, 5, 24)], downed_who=[0, -1], downed_count=2)
    area.count_down_area(battle, True)
    assert clouds == [first, last] and first['countdown'] == 2 and last['countdown'] == 0
    assert writes == [(4, 5, 31), (4, 5, 29), (5, 5, 29), (6, 5, 29)]
    assert battle.events == [('bottom', game.assets.text('explosionMessage'))]
    writes.clear(); battle.events.clear()
    area.count_down_area(battle)
    assert clouds == [first] and first['countdown'] == 1
    assert writes == [(6, 5, 26), (4, 5, 29), (5, 5, 29)]
    writes.clear(); battle.events.clear()
    area.count_down_area(battle, True)
    assert not writes and not battle.events and first['countdown'] == 1
    area.count_down_area(battle)
    assert not clouds and writes == [(4, 5, 31), (5, 5, 24)]
    game, char, tiles, writes, messages, saves, services = area_fixture()
    battle = game.battle
    battle.data.update(downed=[(4, 5, 23), (5, 5, 24)], downed_who=[0, 1], downed_count=1)
    battle.data['clouds'] = [dict(cells=[(4, 5, 23), (5, 5, 24)], terrain=29, countdown=1)]
    area.count_down_area(battle)
    assert writes == [(4, 5, 31), (5, 5, 24)]
    for immediate in (False, True):
        game, char, tiles, writes, messages, saves, services = area_fixture()
        battle = game.battle
        nodes = [dict(cells=[(i, 1, 23)], terrain=29, countdown=n) for i, n in enumerate((-2, -1, 0, 1, 2, 127, 255))]
        battle.data['clouds'][:] = nodes
        area.count_down_area(battle, immediate)
        survivors = [nodes[i] for i in ((0, 2, 3, 4, 5) if immediate else (4, 5))]
        assert battle.data['clouds'] == survivors
        assert [n['countdown'] for n in survivors] == ([-2, 0, 1, 2, 127] if immediate else [1, 126])
        assert len(battle.events) == 1
    battle.data['clouds'][:] = [dict(cells=[], terrain=29, countdown=-1)]
    writes.clear(); battle.events.clear()
    area.count_down_area(battle, True)
    assert not writes and len(battle.events) == 1 and not battle.data['clouds']
    for saved, casting in ((False, 15), (True, 0), (True, 15)):
        game, char, tiles, writes, messages, saves, services = area_fixture()
        battle = game.battle
        tiles[4, 5] = 29
        game.s.faces = [4]
        services['saving_throw'] = lambda char, kind, modifier: saved
        state = battle.record(0)
        state['casting'] = casting
        char.b[magic.F['memorized']] = 15
        area.terrain_effects(battle, 0)
        node = effects.has_effect(char, 30 if saved else 31)
        assert node is not None and bytes(node[1:5]) == bytes((5, 0, 255, 0))
        assert game.s.calls == [4] and battle.events[0] == ('view', 0)
        assert state['initiative'] == (5 if saved and not casting else 0)
        assert char.b[magic.F['memorized']] == (143 if saved and casting else 15)
        assert (battle.data['actor'], game.s.sel) == (1, 2)
        if saved:
            assert not state['cast_ok'] and not state['item_ok']
            if casting: assert messages[-1][1] == game.assets.text('lostSpellMessage')
    for active, undead, ident, moved, view in ((0, 0, 0, True, False), (1, 1, 0, True, True),
                                             (1, 0, 31, True, True), (1, 0, 99, True, True),
                                             (1, 0, 0, False, False)):
        game, char, tiles, writes, messages, saves, services = area_fixture()
        char.b[F['active']], char.b[F['undead']] = active, undead
        if ident: effects.add_effect(char, ident, 0, 0, False)
        tiles[4, 5] = 29
        area.terrain_effects(game.battle, 0, moved)
        assert not game.s.calls and not saves
        assert game.battle.events == ([('view', 0)] if view else [])
    for level in (0, 4, 5, 6, 7, 127, 128, 255):
        for saved in (False, True):
            game, char, tiles, writes, messages, saves, services = area_fixture()
            char.b[F['highest_level']] = level
            char.b[F['undead']] = 1
            effects.add_effect(char, 99, 0, 0, False)
            tiles[5, 5] = 28
            def saving(char, kind, modifier):
                saves.append((kind, modifier))
                return saved
            services['saving_throw'] = saving
            area.terrain_effects(game.battle, 0, False)
            assert saves == ([(0, 252 if level == 5 else 0)] if level in (5, 6) else [])
            killed = level <= 4 or level in (5, 6) and not saved
            assert effects.has(char, 55) == killed
            assert not game.s.calls
            if killed:
                assert game.battle.events == [('pause',), ('kill', 0, 6, game.assets.text('killedMessage'))]
                assert messages[-1][1] == game.assets.text('poisonedMessage')
            else: assert not game.battle.events and not messages
    game, char, tiles, writes, messages, saves, services = area_fixture()
    battle = game.battle
    tiles[4, 5], tiles[5, 5] = 29, 28
    char.b[F['highest_level']] = 5
    def end_and_disable(char):
        battle.end(char)
        char.b[F['active']] = 0
        battle.data['actor'], game.s.sel = 0, 0
    services['end_actions'] = end_and_disable
    area.terrain_effects(battle, 0)
    assert saves == [(0, 0, 0)] and not effects.has(char, 55)
    assert (battle.data['actor'], game.s.sel) == (1, 2)
    for held in (False, True):
        game, char, tiles, writes, messages, saves, services = area_fixture()
        battle = game.battle
        tiles[4, 5] = 29
        services['saving_throw'] = lambda *args: True
        if held: effects.add_effect(char, 30, 1, 0, False)
        battle.add_with_message = lambda *args: battle.data.update(actor=0)
        area.terrain_effects(battle, 0)
        assert battle.record(0)['cast_ok'] == (not held)
        assert (battle.data['actor'], game.s.sel) == (1, 2)


def drain_fixture():
    game, chars, messages, saves, services = fixture()
    game.s.r0 = bytearray(1024)
    events = game.battle.events
    services['message'] = lambda who, text: events.append(('message', game.battle.index(who), text))
    services['pause'] = lambda: events.append(('pause',))
    who = chars[1]
    who.b[F['abilities']:F['abilities'] + 12] = bytes([10] * 12)
    who.b[F['robe_order']] = 1
    r = rules.record(who)
    for name, value in (('hp', 20), ('hp_max', 25), ('hp_rolled', 25), ('experience', 9000)):
        r.set(name, value)
    return game, chars[0], who, r, events, services


def test_drain():
    from . import creation, magic
    from .faults import BindingRequired
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 2] = 4
    r.set('old_experience', 0xFFFFFFFF)
    r.set('old_hp_max', 30)
    game.s.faces[:] = [3, 7]
    run(game, attacker, 67, services, in_combat=True, removed=True)
    assert events == [('message', 1, game.assets.text('drainedText')), ('pause',)]
    assert who.b[F['levels'] + 2] == 3 and who.b[F['former_levels'] + 2] == 4
    assert (r.get('experience'), r.get('old_experience'), r.get('old_hp_max')) == (6001, 9000, 30)
    assert (r.get('hp'), r.get('hp_max'), r.get('hp_rolled')) == (13, 18, 18)
    assert game.s.calls == [10, 10] and r.get('highest_level') == 3
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 2], who.b[F['levels'] + 5] = 4, 4
    who.b[F['former_levels']] = 2
    r.set('experience', 0xFFFFFFFF)
    r.set('old_experience', 20000)
    changes = []
    original = creation.adjust_level_hp
    def adjust(state, char, mask, divisor, gaining, tables):
        changes.append((tuple(r.get('levels')), mask, divisor, gaining, r.get('experience')))
        return original(state, char, mask, divisor, gaining, tables)
    game.s.faces[:] = [2, 4, 3, 7]
    with patch.object(creation, 'adjust_level_hp', adjust):
        run(game, attacker, 68, services, in_combat=True)
    assert [(levels[2], levels[5], mask, divisor, gaining, xp) for levels, mask, divisor, gaining, xp in changes] == [
        (4, 3, 1, 3, False, 15000), (3, 3, 8, 3, False, 6001)]
    assert r.get('old_experience') == 20000 and who.b[F['former_levels'] + 2] == who.b[F['former_levels'] + 5] == 4
    assert game.s.calls == [4, 4, 10, 10] and events.count(('pause',)) == 1
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 2] = 20
    game.s.faces[:] = [3, 7]
    table = rules.tables()
    start = table.offset['classProgression'] + creation.suborder(who, 2) * 204
    lower, upper = (int.from_bytes(table.image[start + at:start + at + 4], 'little', signed=True) for at in (68, 72))
    with patch.object(creation, 'adjust_level_hp', lambda *a: None):
        run(game, attacker, 67, services, in_combat=True)
    assert who.b[F['levels'] + 2] == 19 and r.get('experience') == (lower + int((upper - lower) / 2)) & 0xFFFFFFFF
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 2] = 4
    effects.call_handler(game, attacker, 68, None, False, effects.Roll(services=services))
    assert who.b[F['levels'] + 2] == 2 and events.count(('pause',)) == 1
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 2] = who.b[F['levels'] + 5] = 4
    with patch.object(creation, 'adjust_level_hp'), patch.object(rules, 'recalc_class_stats'), patch.object(rules.tables(), 'level_xp', return_value=8001):
        run(game, attacker, 67, services)
    assert who.b[F['levels'] + 2] == 3 and who.b[F['levels'] + 5] == 4
    for cleric, fighter, selected in ((-1, 1, 2), (2, -1, 0), (7, 7, 0)):
        game, attacker, who, r, events, services = drain_fixture()
        who.b[F['levels']] = who.b[F['levels'] + 2] = 1
        tables = rules.tables()
        image = bytearray(tables.image)
        for cls, value in ((0, cleric), (2, fighter)):
            at = tables.offset['classProgression'] + creation.suborder(who, cls) * 204 - 4
            image[at:at + 4] = value.to_bytes(4, 'little', signed=True)
        with patch.object(tables, 'image', image): run(game, attacker, 67, services)
        assert who.b[F['levels'] + selected] == 0
        assert who.b[F['levels'] + (2 if selected == 0 else 0)] == 1
        assert r.get('experience') == 0 and not game.s.calls
        assert events == [('message', 1, game.assets.text('drainedText')), ('pause',)]
    for level, hp, maximum, expected in ((1, 20, 25, 8), (3, 0, 25, 4), (3, 0, 0, 8)):
        game, attacker, who, r, events, services = drain_fixture()
        who.b[F['levels'] + 2] = level
        r.set('hp', hp); r.set('hp_max', maximum)
        run(game, attacker, 67, services)
        assert events[-1] == ('kill', 1, expected, game.assets.text('drainDeathText' if expected == 8 else 'drainCollapseText'))
        if level == 1: assert r.get('experience') == 0 and not game.s.calls
    game, attacker, who, r, events, services = drain_fixture()
    who.b[F['levels'] + 7], who.b[F['former_levels'] + 7] = 1, 7
    run(game, attacker, 68, services, in_combat=True)
    assert who.b[F['levels'] + 7] == 255 and who.b[F['former_levels'] + 7] == 7 and not game.s.calls
    assert events == [('message', 1, game.assets.text('drainedText')), ('pause',), ('kill', 1, 8, game.assets.text('drainDeathText'))]
    game, attacker, who, r, events, services = drain_fixture()
    game.battle.record(0)['target'] = -1
    run(game, attacker, 68, services)
    assert not events and not game.s.calls
    game.battle.record(0)['target'] = 1
    who.b[F['levels'] + 2] = 255
    try: run(game, attacker, 67, services)
    except BindingRequired: pass
    else: assert False
    base = magic.F['memorized']
    for phase in (0, 1, 2, 3):
        game, attacker, who, r, events, services = drain_fixture()
        who.b[F['levels'] + 5] = 3
        game.s.r0[0x1F9] = phase
        book = rules.spellbook(who)
        capacity = bytearray(32)
        capacity[24], capacity[25] = 1, 1
        book.set('spell_slots', capacity)
        who.b[base:base + 9] = bytes((143, 15, 15, 15, 33, 33, 175, 47, 161))
        handlers.trim_drained_spells(game, who)
        assert list(who.b[base:base + 9]) == [0, 15, 15 if phase in (1, 2) else 0, 15 if phase == 2 else 0, 33, 0, 0, 0, 0]
    game, attacker, who, r, events, services = drain_fixture()
    book = rules.spellbook(who)
    capacity = bytearray(32); capacity[24] = 1
    book.set('spell_slots', capacity)
    who.b[base:base + 5] = bytes((15, 15, 15, 33, 143))
    handlers.trim_drained_spells(game, who)
    assert list(who.b[base:base + 5]) == [15, 15, 15, 0, 0]


def test_aging():
    game, chars, messages, saves, services = fixture()
    char = chars[0]
    assert effects.age_effects(game, char, 1) is False
    for durations, step, expected, running in (
        ((0, 0), 10, [0, 0], False), ((11, 1, 20), 1, [9, 19], True),
        ((11, 20, 1, 30), 1, [10, 19, 29], True), ((2, 1, 0), 1, [0], True),
        ((1, 1), 1, [], False), ((65535, 10), 10, [65525], True)):
        char.effects.clear()
        for duration in durations: effects.add_effect(char, 5, duration, 0, False)
        assert effects.age_effects(game, char, step) == running
        assert [int.from_bytes(n[1:3], 'little') for n in char.effects] == expected
    for prefix, expected, running in (((), [60], False), ((0,), [0, 60], True), ((20, 0), [10, 0, 60], True)):
        char.effects.clear()
        for duration in prefix: effects.add_effect(char, 5, duration, 0, False)
        effects.add_effect(char, 62, 1, 0, True)
        old = char.effects[-1]
        char.b[F['hp']] = 10
        assert effects.age_effects(game, char, 10) == running
        assert char.b[F['hp']] == 11
        assert [int.from_bytes(n[1:3], 'little') for n in char.effects] == expected
        assert all(n is not old for n in char.effects)
    char.effects.clear()
    for ident, minutes, callback in ((5, 30, False), (62, 1, True), (5, 20, False)):
        effects.add_effect(char, ident, minutes, 0, callback)
    assert effects.age_effects(game, char, 10)
    assert [int.from_bytes(n[1:3], 'little') for n in char.effects] == [10, 10, 60]
    for lead, later, expected in (((), (), [55]), ((5,), (), [5, 55]), ((5, 5), (3, 5), [5, 5, 55, 5])):
        char.effects.clear()
        for ident in lead: effects.add_effect(char, ident, 0, 0, False)
        for ident, minutes, callback in ((55, 0, False), (22, 10, True)) + tuple((k, 40, False) for k in later) + ((15, 10, True),):
            effects.add_effect(char, ident, minutes, 255, callback)
        game.battle.kill = lambda i, status, text, who=char: [effects.remove_effect(game, who, k) for k in effects._hp_zero_ids(game)]
        assert effects.age_effects(game, char, 10) == bool(lead or later)
        assert [n[0] for n in char.effects] == expected and not game.effect_busy
        assert [int.from_bytes(n[1:3], 'little') for n in char.effects if n[0] == 5 and n[1]] == ([40] if len(lead) > 1 else [])
    del game.battle.kill
    char.effects.clear()
    effects.add_effect(char, 62, 1, 0, True)
    game.effect_busy = True
    before = char.b[F['hp']]
    assert not effects.age_effects(game, char, 10)
    assert not char.effects and char.b[F['hp']] == before and game.effect_busy


def test_engine():
    game, chars, messages, saves, services = fixture()
    char, foe, other = chars
    char.b[F['magic_resistance']] = 10
    services['caster_level'] = lambda spell: 14
    game.s = Dice(100)
    roll = effects.Roll(services=services, effect=0, element=8, damage=12)
    effects.check_spell_resistance(game, char, roll)
    assert roll.damage == 0 and game.s.calls == [100]
    for ident, expected in ((11, 0), (91, 91), (82, 82)):
        game.s = Dice(1)
        roll = effects.Roll(services=services, effect=ident, damage=0)
        effects.check_spell_resistance(game, char, roll)
        assert roll.effect == expected
    game.s = Dice(1)
    roll = effects.Roll(services=services, effect=11, damage=4, element=1)
    effects.check_spell_resistance(game, char, roll)
    assert roll.damage == 4 and roll.effect == 11 and not game.s.calls
    item = bytearray(Item.SIZE); item[I['powers'] + 1] = 5
    game.handler_override_active = True
    effects.call_handler(game, char, 1, item, False)
    assert effects.has(char, 5) and not game.handler_override_active
    game.handler_override_active = True
    effects.call_handler(game, char, 1, item, True)
    assert not effects.has(char, 5) and not game.handler_override_active
    game.battle.held = bytearray(Item.SIZE)
    game.battle.held[I['bonus']] = 255
    assert run(game, char, 66, services, damage=12)[0].damage == 0
    assert run(game, char, 103, services, damage=12)[0].damage == 12
    game.battle.held[I['bonus']] = 0
    game.battle.data['hits_made'] = [0, 7]
    run(game, char, 41, services, in_combat=True, damage=10)
    assert game.battle.data['hits_made'] == [255, 7]
    game.s = Dice(*([6] * 50))
    roll = effects.Roll()
    assert effects.damage_dice(game.s, 50, 6, roll) == 44 and roll.dice_count == 50
    assert effects.roll_dice(game.s, 0, 6) == 0 and len(game.s.calls) == 50
    char.b[F['hp']], char.b[F['hp_max']] = 20, 20
    assert not effects.restore_hp(char, 1)
    assert effects.restore_hp(char, 255, False) and char.b[F['hp']] == 19
    char.b[F['status']], char.b[F['active']], char.b[F['hp']] = 5, 0, 0
    assert effects.restore_hp(char, 2, in_combat=True)
    assert (char.b[F['status']], char.b[F['active']]) == (4, 0)
    assert effects.restore_hp(char, 2)
    assert (char.b[F['status']], char.b[F['active']]) == (0, 1)
    effects.add_effect(char, 5, 0, 0, False)
    assert effects.remove_with_message(game, char, 5, effects.Roll(services=services))
    assert said(messages) == game.assets.text('isCuredText')
    assert not effects.remove_with_message(game, char, 5)


def test_abilities():
    from . import effects_ability as ability
    game, chars, messages, saves, services = fixture()
    char = chars[0]
    char.b[F['abilities']:F['abilities'] + 12] = bytes((16, 9, 14, 3, 15, 4, 6, 1, 18, 1, 10, 1))
    char.b[F['levels'] + 3] = 2
    assert ability.encode_strength(18, 100) == 101 and ability.encode_strength(21, 0) == 121
    assert ability.decode_strength(128) == (18, 255)
    assert ability.decode_strength(249) == (21, 0)
    assert ability.improved_strength(char, 15, 0, 77) == (False, 77)
    assert ability.improved_strength(char, 21, 0, 77) == (True, 121)
    effects.add_effect(char, 38, 1, 104, False)
    effects.recalc_ability(game, char, 0)
    assert (char.b[F['abilities'] + 1], char.b[F['strength_extra']]) == (18, 20)
    char.effects.clear()
    item = bytearray(Item.SIZE)
    item[I['readied']], item[I['powers'] + 2], item[I['powers'] + 1] = 1, 133, 6
    char.items[:] = [item]
    effects.recalc_ability(game, char, 0)
    assert char.b[F['abilities'] + 1] == 24
    item[I['powers'] + 2] = 141
    effects.recalc_ability(game, char, 0)
    assert (char.b[F['abilities'] + 1], char.b[F['strength_extra']]) == (3, 0)
    for stat, expected in ((1, 3), (2, 4)):
        effects.recalc_ability(game, char, stat)
        assert char.b[F['abilities'] + stat * 2 + 1] == expected
    item[I['powers'] + 2] = 130
    effects.recalc_ability(game, char, 3)
    assert char.b[F['abilities'] + 7] == 10
    item[I['powers'] + 2] = 138
    char.b[F['abilities'] + 6] = 1
    effects.recalc_ability(game, char, 3)
    assert char.b[F['abilities'] + 7] == 255
    item[I['powers'] + 2] = 134
    effects.add_effect(char, 14, 1, 250, False)
    effects.recalc_ability(game, char, 5)
    assert char.b[F['abilities'] + 11] == 3
    char.items.clear(); char.effects.clear()
    char.b[F['former_levels']:F['former_levels'] + 8] = bytes([20] * 8)
    for cls, expected_max, expected_hp in ((0, 14, 9), (3, 18, 13), (4, 22, 17)):
        char.b[F['levels']:F['levels'] + 8] = bytes(8)
        char.b[F['levels'] + cls] = 2
        char.b[F['hp_rolled']], char.b[F['hp_max']], char.b[F['hp']] = 10, 10, 5
        effects.recalc_ability(game, char, 4)
        assert (char.b[F['hp_max']], char.b[F['hp']]) == (expected_max, expected_hp)
        assert char.b[F['abilities'] + 9] == 18
    char.b[F['abilities'] + 8] = 20
    effects.recalc_ability(game, char, 4)
    node = effects.has_effect(char, 62)
    assert bytes(node[1:5]) == bytes((60, 0, 255, 1))
    game.effect_busy = True
    char.b[F['abilities'] + 8] = 10
    effects.recalc_ability(game, char, 4)
    assert not effects.has(char, 62) and char.b[F['hp_max']] == 10
    game.effect_busy = False
    char.b[F['levels']:F['levels'] + 8] = bytes(8)
    try: effects.recalc_ability(game, char, 4)
    except effects.BindingRequired: pass
    else: raise AssertionError('zero-class Constitution must not guess a divisor')
