import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import camp, creation, effects, rules
from sm.titles.cok.camp import Kind
from sm.titles.cok.creation import F
from sm.titles.cok.effects import Roll, add_effect, has_effect, remove_effect
from sm.titles.cok.faults import BindingRequired
from sm.titles.cok.menu import Game
from sm.titles.cok.records import Character

MENU, REST, ACK = Kind.MENU.value, Kind.REST.value, Kind.ACK.value
AT = {name: F[name] for name in ('abilities', 'hp', 'hp_max', 'npc', 'side', 'auto_combat', 'strength_extra')}
POINTERS = {'effects_pointer', 'items_pointer', 'equipped_pointers', 'next_pointer', 'combat_pointer'}


def party_game(folder, root):
    seen = []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if kind == ACK: return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        return options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    for char in game.s.party: del char.effects[:]
    return game, seen


def rest_hours(game, hours):
    game.rows = iter(((MENU, 'Rest'), (REST, 'Hours'), *((REST, 'Add') for _ in range(hours)), (REST, 'Rest'), (MENU, creation.EXIT)))
    camp.run(game)


def fields(char):
    return {name: bytes(char.b[o:o + w]) for name, (o, w) in Character.FIELDS.items() if name not in POINTERS}


def same_as(char, before):
    now = fields(char)
    return [name for name in before if before[name] != now[name]]


def minutes_until_gone(game, char, kind):
    flags, spent = [True] * len(game.s.party), 0
    while has_effect(char, kind) is not None:
        camp.advance_time(game, flags); spent += 5
        assert spent < 10000
    return spent


def ability_class(folder, root):
    game, seen = party_game(folder, root)
    char = game.s.party[0]
    before = fields(char)
    add_effect(char, 12, 20, 119, True)
    effects.recalc_ability(game, char, 0)
    assert char.b[F['abilities'] + 1] == 19 and char.b[F['strength_extra']] == 0
    rest_hours(game, 1)
    assert has_effect(char, 12) is None
    assert same_as(char, before) == [], same_as(char, before)
    return seen


def expiry_time(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    add_effect(char, 33, 12, 255, False)
    assert minutes_until_gone(game, char, 33) == 15
    add_effect(char, 33, 10, 255, False)
    assert minutes_until_gone(game, char, 33) == 10
    add_effect(char, 33, 0, 255, False)
    camp.advance_time(game, [True] * len(game.s.party))
    assert has_effect(char, 33) is not None, 'a zero-duration effect never runs out'


def status_class(folder, root):
    game, seen = party_game(folder, root)
    char = game.s.party[0]
    before = fields(char)
    char.b[F['npc']], char.b[F['auto_combat']], char.b[F['side']] = 0xB3, 1, 1
    add_effect(char, 11, 15, 0x20, True)
    rest_hours(game, 1)
    assert has_effect(char, 11) is None and same_as(char, before) == [], same_as(char, before)
    return seen


def ac_class(folder, root):
    game, seen = party_game(folder, root)
    char = game.s.party[0]
    before = fields(char)
    add_effect(char, 17, 20, 255, False)
    rest_hours(game, 1)
    assert has_effect(char, 17) is None and same_as(char, before) == [], same_as(char, before)
    roll = Roll()
    char.b[F['ac']] = 50
    effects.call_handler(game, char, 17, bytearray(9), False, roll)
    assert char.b[F['ac']] == 57 and roll.save == 1
    return seen


def renewal_class(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    hp = char.b[F['hp']]
    add_effect(char, 15, 10, 255, True)
    flags = [True] * len(game.s.party)
    for _ in range(2): camp.advance_time(game, flags)
    assert char.b[F['hp']] == hp - 1 and has_effect(char, 15) is not None
    char.b[F['hp']] = 1
    for _ in range(2): camp.advance_time(game, flags)
    assert char.b[F['hp']] == 1, 'never below one from the tick'


def slow_poison_end(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    add_effect(char, effects.POISONED, 0, 255, False)
    add_effect(char, effects.POISON_DAMAGE, 600, 255, True)
    add_effect(char, effects.SLOW_POISON, 5, 255, True)
    camp.advance_time(game, [True] * len(game.s.party))
    assert char.b[F['status']] == effects.DEAD and char.b[F['hp']] == 0 and not char.b[F['active']]
    assert has_effect(char, effects.POISON_DAMAGE) is None and has_effect(char, effects.POISONED) is None


def table(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    assert all(effects.effect_kind(k) for k in effects.HANDLER_NAMES)
    assert all(effects.effect_kind(k) is None for k in (4, 6, 78, 83, 84, 85, 90, 104))
    before = bytes(char.b)
    for kind in sorted(effects.EMPTY_IDS):
        effects.call_handler(game, char, kind, bytearray(9), True)
    assert bytes(char.b) == before
    try: effects.call_handler(game, char, 48, bytearray(9), True)
    except BindingRequired as fault: assert 'Immolate' in str(fault)
    else: raise AssertionError('Immolate needs combat state')


def combat_handlers(folder, root):
    game, _ = party_game(folder, root)
    dragon, near, immune = game.s.party[:3]
    dragon.b[F['side']], near.b[F['side']], immune.b[F['side']] = 1, 0, 0
    add_effect(immune, 92, 0, 255, False)
    log = []
    roll = Roll(services=dict(neighbours=lambda c: [near, immune], saving_throw=lambda c, k, m: False, clear_target=lambda c: log.append('clear'),
                              set_turned=lambda c, v: log.append(('turned', v)), add_with_message=lambda c, k, m, s, t: add_effect(c, k, m, s, True)))
    effects.call_handler(game, dragon, 72, bytearray(9), False, roll)
    assert has_effect(near, 111) is not None and has_effect(immune, 111) is None and ('turned', 1) in log
    assert near.b[F['npc']] == 0xB3 and near.b[F['auto_combat']] == 1
    attacker, defender = game.s.party[3:5]
    attacker.b[F['abilities'] + 2 * 3 + 1] = 3
    weapon = attacker.items[0]; weapon[effects.I['cursed']], weapon[effects.I['type']] = 0, 1
    items, bank = len(attacker.items), []
    from sm.titles.cok.inventory import toggle_ready
    weapon[effects.I['readied']] = 1
    weapon[effects.I['powers']+1], weapon[effects.I['powers']+2] = 7, 130
    if has_effect(attacker, 7) is None: add_effect(attacker, 7, 0, 255, True)
    stages = []
    def combat_effect(c, kind, node, removed, roll):
        assert c is attacker and kind == 7 and removed
        assert weapon in c.items and weapon[effects.I['readied']] == 0 and not bank
        stages.append('unready')
    game.combat_effect = combat_effect
    def bank_weapon(c, raw):
        assert has_effect(c, 7) is None and stages == ['unready']
        bank.append(raw)
    roll = Roll(attacker=attacker, services=dict(damaging_weapon=lambda c: weapon, distance=lambda a, b: 1, bank_weapon=bank_weapon,
                unready_item=lambda c, item: toggle_ready(game, c, item), clear_weapon=lambda c: None))
    effects.call_handler(game, defender, 67, bytearray(9), False, roll)
    assert len(attacker.items) == items - 1 and len(bank) == 1 and bank[0][effects.I['readied']] == 0
    down = game.s.party[5]
    down.b[F['status']] = effects.DEAD
    add_effect(down, 32, 0, 255, False); add_effect(down, 58, 0, 255, False)
    roll = Roll(services=dict(revive=lambda c, hp, text: True))
    effects.call_handler(game, down, 32, has_effect(down, 32), False, roll)
    assert down.b[F['status']] == 0 and has_effect(down, 59) is not None and has_effect(down, 60) is not None and has_effect(down, 66) is not None
    assert has_effect(down, 32) is None and has_effect(down, 58) is None


def recalc_cases(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]; b = char.b
    add_effect(char, 113, 0, 110 | 0, True)
    start = b[F['abilities'] + 1]
    effects.recalc_ability(game, char, 0)
    assert b[F['abilities'] + 1] == max(start, 10)
    del char.effects[:]
    base = b[F['abilities'] + 2 * 4]; hp_max = b[F['hp_max']]
    effects.recalc_ability(game, char, 4)
    assert b[F['abilities'] + 2 * 4 + 1] == base and b[F['hp_max']] == hp_max, (b[F['hp_max']], hp_max)


def arena_expiry_after_combat(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    add_effect(char, 40, 10, 0x10, True); add_effect(char, 80, 10, 0, True)
    before = bytes(char.b)
    for _ in range(2): camp.advance_time(game, [True] * len(game.s.party))
    assert has_effect(char, 40) is None and has_effect(char, 80) is None and bytes(char.b) == before


def target_effects_outside_combat(folder, root):
    game, _ = party_game(folder, root)
    char = game.s.party[0]
    for kind in (89, 105, 114, 115, 117): add_effect(char, kind, 0, 255, True)
    before = bytes(char.b)
    for kind in (89, 105, 114, 115, 117): effects.remove_effect(game, char, kind)
    assert not char.effects and bytes(char.b) == before
    add_effect(char, 7, 0, 255, True); seed = game.s.seed
    effects.remove_effect(game, char, 7)
    assert not char.effects and bytes(char.b) == before and game.s.seed == (seed * 0x08088405 + 1) & 0xFFFFFFFF


def cold_after_save(folder, root):
    from sm.titles.cok import town
    game, _ = party_game(folder, root)
    for saved, expected in ((True, 10), (False, 20)):
        game.recently_saved = saved; roll = Roll(element=2, damage=10)
        effects.call_handler(game, game.s.party[0], 54, bytearray(9), False, roll)
        assert roll.damage == expected, (saved, roll.damage)
    game.recently_saved, kept = True, (town.service, town.refresh)
    game.vm.run = lambda at: None
    town.service = lambda *a: [seen.append(game.recently_saved), True][1]; town.refresh = lambda g: None; seen = []
    try: town.camp(game)
    finally: town.service, town.refresh = kept
    assert seen == [True] and game.recently_saved is False


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-fx-') as first, tempfile.TemporaryDirectory(prefix='cok-fx-') as second:
        for check in (expiry_time, arena_expiry_after_combat, renewal_class, slow_poison_end, table, combat_handlers, recalc_cases, target_effects_outside_combat, cold_after_save): check(folder, first)
        run = lambda root: (ability_class(folder, root), status_class(folder, root), ac_class(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS ability, AC, status, timed renewal, poison end, table, named combat handlers; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
