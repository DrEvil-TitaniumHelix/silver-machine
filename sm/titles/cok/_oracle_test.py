import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import camp, creation, inventory, magic, rules, shop, temple, training
from sm.titles.cok import _shop_test as shop_check
from sm.titles.cok.camp import Kind
from sm.titles.cok.creation import F
from sm.titles.cok.menu import Game
from sm.titles.cok.records import Character
from sm.titles.cok.shop import I

POINTERS = {'effects_pointer', 'items_pointer', 'equipped_pointers', 'next_pointer', 'combat_pointer'}
LIVE_RECORDS = ('e66b0f5aec44a0cbaba8ab0818a651a5e3bb2102ab4eeeae5dd8c1b1af19a2f4', 'bf6fcf0860f49b638aca592009f421560ea70f1c10ba3cbda1a09a9b21a95bd5',
                'c1507e74003f1042e9f37069812c5c033eb7e742e217b4570f54e598cca74f47', '4615b9c23f835c3662c4551f772c0367c901bad950cd7443bcc1994a202bfc78',
                'c969ddb398c6d372d432c534a6676510b1d2bcbed29536d42dd75bbada9fb580', '48d49e43204e4eb9591e4d66dbf2b575746d4d7deca2150d12a54ebf0f100d7a')
REST = dict(seed=0x1234, wound=3, gained=1, clock_after=(0, 0, 0, 0, 1, 0, 0), only_changed='hp', seed_after=0x1234)
CURES = ((4, 0, 0x1234, 5, 16, 1231448858), (4, 0, 0xBEEF, 5, 16, 1715175773), (5, 0, 0x1234, 5, 9, 990063365), (5, 0, 0xBEEF, 5, 12, 3522098860), (4, 1, 0x77, 29, 30, 3272484773))
CURE_COPIES = (2, 1)
SHOP = dict(start=dict(steel=100, weight=562), bought=dict(steel=93, weight=705), sold=dict(steel=96, weight=656), items=(3, 4, 3), item_weight=45, item_value=7,
            item_sha256='ef150ecef00f51e79e66fedbb42b5a38adcbce89ab47018f0f08c594794e8f99')
SECOND = json.loads(r'''{"temple": {"light": {"steel": 50, "hp": 5, "hp_max": 27, "status": 0, "active": 1, "constitution": 18, "effects": [], "seed": 990063365, "sha256": "b2d864359a3fd2d0479e1a3660b0c4088c38b9a67703e70dbd0baf973fa99bbf"}, "light2": {"steel": 50, "hp": 8, "hp_max": 27, "status": 0, "active": 1, "constitution": 18, "effects": [], "seed": 3522098860, "sha256": "fd320be2fd1e20d8a4cc089d63822f25284f4cedeeb5d5ee5cd2bbb793cdb9f0"}, "poison": {"steel": 500, "hp": 1, "hp_max": 21, "status": 0, "active": 1, "constitution": 18, "effects": [], "seed": 4660, "sha256": "7d1d2012ed574a22bf574455331f6678bee7bb010b6160676f77584e350a4e7d"}, "raised": {"steel": 250, "hp": 1, "hp_max": 27, "status": 0, "active": 1, "constitution": 17, "effects": [], "seed": 4660, "sha256": "06ae2256dc7bdb7161793d52e93529b22970a3595a95fe12ce1a0daa011e5b33"}, "broke": {"steel": 10, "hp": 1, "hp_max": 27, "status": 0, "active": 1, "constitution": 18, "effects": [], "seed": 4660, "sha256": "96c178bd173e3fdd56be6760414a006d8d6d61edd25388b7fd3fa4c4224b5a73"}}, "train": {"knight": {"levels": [0, 0, 0, 0, 0, 0, 0, 2], "hp_max": 39, "hp": 39, "hp_rolled": 31, "base_thac0": 40, "saves": [11, 10, 10, 14, 11], "slots": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "xp": 5000, "steel": 2, "known": "a2fc9fa6e6b6d3a4b88353d579157843faa359c96cba77b815bbeeaf6a966a96", "seed": 1231448858}, "ranger": {"levels": [0, 0, 0, 0, 3, 0, 0, 0], "hp_max": 41, "hp": 41, "hp_rolled": 25, "base_thac0": 42, "saves": [13, 14, 15, 16, 16], "slots": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "xp": 4501, "steel": 2, "known": "a2fc9fa6e6b6d3a4b88353d579157843faa359c96cba77b815bbeeaf6a966a96", "seed": 1231448858}, "ranger2": {"levels": [0, 0, 0, 0, 3, 0, 0, 0], "hp_max": 41, "hp": 41, "hp_rolled": 25, "base_thac0": 42, "saves": [13, 14, 15, 16, 16], "slots": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "xp": 4501, "steel": 2, "known": "a2fc9fa6e6b6d3a4b88353d579157843faa359c96cba77b815bbeeaf6a966a96", "seed": 1715175773}, "garin": {"levels": [0, 0, 4, 0, 0, 3, 0, 0], "hp_max": 30, "hp": 30, "hp_rolled": 22, "base_thac0": 43, "saves": [13, 13, 11, 15, 12], "slots": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 1, 0, 0, 0], "xp": 10000, "steel": 1, "known": "078f74d0b58d911f0d7ec3a82213e03d4255edd0278501e282fb6ca7bf59018f", "seed": 4245096848}, "short": {"levels": [0, 0, 0, 0, 0, 0, 0, 1], "hp_max": 27, "hp": 27, "hp_rolled": 23, "base_thac0": 40, "saves": [11, 10, 10, 14, 11], "slots": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "xp": 4999, "steel": 2, "known": "a2fc9fa6e6b6d3a4b88353d579157843faa359c96cba77b815bbeeaf6a966a96", "seed": 4660}}, "ready": {"start": {"ac": 61, "thac0": 43, "rolls": 1, "dice": 8, "bonus": 6, "weight": 562, "hands": 2, "move": 6, "readied": [1, 1, 1]}, "bare": {"ac": 60, "thac0": 43, "rolls": 1, "dice": 2, "bonus": 6, "weight": 562, "hands": 0, "move": 6, "readied": [1, 0, 0]}, "sword": {"ac": 60, "thac0": 43, "rolls": 1, "dice": 8, "bonus": 6, "weight": 562, "hands": 1, "move": 6, "readied": [1, 0, 1]}, "both": {"ac": 61, "thac0": 43, "rolls": 1, "dice": 8, "bonus": 6, "weight": 562, "hands": 2, "move": 6, "readied": [1, 1, 1]}}, "buffs": {"enlarge_max": [{"strength": 18, "extra": 100, "effects": [], "thac0": 43, "seed": 4660}, {"strength": 18, "extra": 100, "effects": [], "thac0": 43, "seed": 4660}, {"strength": 18, "extra": 100, "effects": [], "thac0": 43, "seed": 4660}], "enlarge": [{"strength": 18, "extra": 1, "effects": [[92, 0, 0, 255, 0], [94, 0, 0, 255, 0], [7, 0, 0, 255, 1], [12, 20, 0, 2, 1]], "thac0": 42, "seed": 4660}, {"strength": 16, "extra": 0, "effects": [[92, 0, 0, 255, 0], [94, 0, 0, 255, 0], [7, 0, 0, 255, 1]], "thac0": 42, "seed": 4660}, {"strength": 16, "extra": 0, "effects": [[92, 0, 0, 255, 0], [94, 0, 0, 255, 0], [7, 0, 0, 255, 1]], "thac0": 42, "seed": 4660}], "bless": [{"strength": 18, "extra": 100, "effects": [[1, 6, 0, 2, 0]], "thac0": 43, "seed": 4245096848}, {"strength": 18, "extra": 100, "effects": [], "thac0": 43, "seed": 4245096848}, {"strength": 18, "extra": 100, "effects": [], "thac0": 43, "seed": 4245096848}]}, "sell": {"ring": {"start": {"steel": 500, "weight": 562}, "sold": {"steel": 496, "weight": 1056}, "items": [3, 4, 3]}, "darts": {"start": {"steel": 500, "weight": 562}, "sold": {"steel": 499, "weight": 1059}, "items": [3, 4, 3]}, "bow": {"start": {"steel": 500, "weight": 562}, "sold": {"steel": 495, "weight": 1055}, "items": [3, 4, 3]}}, "pool": {"pooled": [{"steel": 0, "weight": 560}, {"steel": 0, "weight": 645}, {"steel": 0, "weight": 645}, {"steel": 0, "weight": 405}, {"steel": 0, "weight": 430}, {"steel": 0, "weight": 645}], "shared": [{"steel": 19, "weight": 579}, {"steel": 19, "weight": 664}, {"steel": 19, "weight": 664}, {"steel": 18, "weight": 423}, {"steel": 18, "weight": 448}, {"steel": 18, "weight": 663}]}}''')
KNOWN_DIFFERENCES = {}
KNOWN_SECOND = {}


def fixture(folder, root, answers=()):
    rows = list(answers)
    def player(kind, options, game, **info):
        if kind == Kind.ACK.value: return 0
        reply = rows.pop(0)
        return reply(options) if callable(reply) else options.index(reply)
    game = Game(player, slot=None, directory=folder)
    game.roster_directory = root
    creation.load_game(game, 'A')
    game.s.mode = 4
    return game


def live_hash(char):
    return hashlib.sha256(b''.join(bytes(char.b[o:o + w]) for name, (o, w) in Character.FIELDS.items() if name not in POINTERS)).hexdigest()


def records(folder, root):
    game = fixture(folder, root)
    assert tuple(live_hash(char) for char in game.s.party) == LIVE_RECORDS, 'live record differs from the original'


def rest(folder, root):
    game = fixture(folder, root, ['Rest', 'Days', 'Add', 'Rest', creation.EXIT])
    s = game.s
    for char in s.party:
        char.b[F['hp']] = char.b[F['hp_max']] - REST['wound']
    before = [bytes(char.b) for char in s.party]
    s.seed = REST['seed']
    camp.run(game)
    found = dict(clock=tuple(s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7]), seed=s.seed, gained=[c.b[F['hp']] - b[F['hp']] for c, b in zip(s.party, before)],
                 changed=sorted({name for c, b in zip(s.party, before) for name, (o, w) in Character.FIELDS.items() if bytes(c.b[o:o + w]) != b[o:o + w]}))
    assert found['clock'] == REST['clock_after'], found
    assert found['seed'] == REST['seed_after'] and found['gained'] == [REST['gained']] * 6 and found['changed'] == [REST['only_changed']], found
    return found


def cure(folder, root):
    results = []
    for caster_index, target_index, seed, hp, expected, seed_after in CURES:
        game = fixture(folder, root)
        s = game.s
        caster, target = s.party[caster_index], s.party[target_index]
        target.b[F['hp']] = hp
        count = lambda: sum(1 for value in caster.b[F['memorized']:F['memorized'] + 58] if value == magic.spell(3).id)
        assert count() == CURE_COPIES[0]
        s.seed = seed
        assert magic.cast(game, caster, 3, target)
        assert target.b[F['hp']] == expected, (seed, target.b[F['hp']], expected)
        assert count() == CURE_COPIES[1] and s.seed == seed_after, (s.seed, seed_after)
        results.append(target.b[F['hp']])
    return results


def stack_hash(raw):
    o, length = I['next_pointer'], raw[I['name']]
    return hashlib.sha256(bytes(raw[:1 + length]) + bytes(raw[41:o]) + bytes(raw[o + 4:])).hexdigest()


def armoury(folder, root):
    game, _, _ = shop_check.shop_game(folder, root)
    char = game.s.party[0]
    char.b[F['money'] + 8:F['money'] + 10] = struct.pack('<H', SHOP['start']['steel'])
    state = lambda: dict(steel=shop_check.steel(char), weight=shop.weight(char))
    assert state() == SHOP['start'], state()
    assert len(char.items) == SHOP['items'][0]
    first = lambda options: 0
    M, W, L, C = shop_check.MENU, shop_check.WHO, shop_check.LIST, shop_check.CONFIRM
    shop_check.play(game, (M, 'Buy'), (L, shop_check.contains('Long Sword')), (L, 'Exit'), (M, 'Exit'))
    bought, item = state(), bytes(char.items[-1])
    assert len(char.items) == SHOP['items'][1]
    assert struct.unpack_from('<H', item, I['weight'])[0] == SHOP['item_weight'] and struct.unpack_from('<H', item, I['value'])[0] == SHOP['item_value']
    assert stack_hash(item) == SHOP['item_sha256']
    shop_check.play(game, (M, 'View'), (shop_check.SHEET, 'Items'), (shop_check.ITEMS, shop_check.last_containing('Long Sword')), (shop_check.ACTION, 'Sell'),
                    (C, 'Yes'), (shop_check.ITEMS, 'Exit'), (shop_check.SHEET, 'Exit'), (M, 'Exit'))
    sold = state()
    assert len(char.items) == SHOP['items'][2]
    return dict(bought=bought, sold=sold)


START = object()


def live_name(char):
    return creation.member_title(char)


def steel_only(char, amount):
    shop.put_coins(char, [0, 0, 0, 0, amount, 0, 0])


def temple_result(game, char):
    b = char.b
    return dict(steel=shop.coins(char)[4], hp=b[F['hp']], hp_max=b[F['hp_max']], status=b[F['status']], active=b[F['active']], constitution=b[F['abilities'] + 2 * 4 + 1],
                effects=[e[0] for e in char.effects], seed=game.s.seed, sha256=live_hash(char))


def temple_case(folder, root, service, index, seed, setup):
    game = fixture(folder, root)
    char = game.s.party[index]
    setup(char)
    game.s.seed = seed
    game.s.sel = index
    rows = ['Heal', service, 'Yes', 'Exit', 'Exit']
    fixture_player(game, rows)
    temple.run(game)
    return temple_result(game, char)


def fixture_player(game, rows):
    def player(kind, options, current, **info):
        if kind == Kind.ACK.value: return 0
        reply = rows.pop(0)
        if reply is START: return info['start']
        return reply(options) if callable(reply) else options.index(reply)
    game.player = player
    return rows


def downed(char):
    char.b[F['hp']], char.b[F['status']], char.b[F['active']] = 0, 6, 0


def temple_cases(folder, root):
    def light(c): steel_only(c, 100); c.b[F['hp']] = 1
    def poison(c): steel_only(c, 1000); downed(c); c.effects[0][0] = 55
    def raised(c): steel_only(c, 3000); downed(c)
    def broke(c): steel_only(c, 10); c.b[F['hp']] = 1
    run = lambda service, index, seed, setup: temple_case(folder, root, service, index, seed, setup)
    return dict(light=run('Cure Light Wounds', 0, 0x1234, light), light2=run('Cure Light Wounds', 0, 0xBEEF, light), poison=run('Neutralize Poison', 4, 0x1234, poison),
                raised=run('Raise Dead', 0, 0x1234, raised), broke=run('Cure Light Wounds', 0, 0x1234, broke))


def trained(game, char):
    b = char.b
    return dict(levels=list(b[F['levels']:F['levels'] + 8]), hp_max=b[F['hp_max']], hp=b[F['hp']], hp_rolled=b[F['hp_rolled']], base_thac0=b[F['base_thac0']], saves=list(b[F['saves']:F['saves'] + 5]),
                slots=list(b[F['spell_slots']:F['spell_slots'] + 20]), xp=struct.unpack_from('<i', b, F['experience'])[0], steel=shop.coins(char)[4],
                known=hashlib.sha256(bytes(b[F['known_spells']:F['known_spells'] + 107])).hexdigest(), seed=game.s.seed)


def train_case(folder, root, index, xp, seed, learned=False, trains=True):
    game = fixture(folder, root)
    s, char = game.s, game.s.party[index]
    s.r1[creation.TRAIN_MASK] = 0x7F
    char.b[F['experience']:F['experience'] + 4] = xp.to_bytes(4, 'little', signed=True)
    s.seed = seed
    labels = game.assets.labels
    rows = [labels[creation.TRAIN], live_name(char)] + (['Yes'] if trains else []) + ([START] if learned else []) + [labels[creation.BEGIN]]
    fixture_player(game, rows)
    creation.run(game)
    return trained(game, char)


def train_cases(folder, root):
    run = lambda *args, **kwargs: train_case(folder, root, *args, **kwargs)
    return dict(knight=run(0, 5000, 0x1234), ranger=run(1, 4501, 0x1234), ranger2=run(1, 4501, 0xBEEF), garin=run(2, 10000, 0x1234, learned=True), short=run(0, 4999, 0x1234, trains=False))


def combat_numbers(char):
    b = char.b
    return dict(ac=b[F['ac']], thac0=b[F['thac0']], rolls=b[F['damage_rolls']], dice=b[F['damage_dice']], bonus=b[F['damage_bonus']], weight=shop.weight(char), hands=b[F['hands_used']], move=b[F['move']],
                readied=[item[I['readied']] for item in char.items])


def ready_case(folder, root):
    game = fixture(folder, root)
    game.s.mode = camp.CAMPING
    char = game.s.party[0]
    row = lambda index: (lambda options: index)
    def view(*rows):
        fixture_player(game, ['Items', *rows, 'Exit', 'Exit'])
        inventory.view(game, char)
    start = combat_numbers(char)
    view(row(1), 'Ready', row(2), 'Ready')
    bare = combat_numbers(char)
    view(row(2), 'Ready')
    sword = combat_numbers(char)
    view(row(1), 'Ready')
    return dict(start=start, bare=bare, sword=sword, both=combat_numbers(char))


def buff_state(game, char):
    b = char.b
    return dict(strength=b[F['abilities'] + 1], extra=b[F['strength_extra']], effects=[list(e[:5]) for e in char.effects], thac0=b[F['thac0']], seed=game.s.seed)


def rest_hour(game):
    fixture_player(game, ['Rest', 'Hours', 'Add', 'Rest', creation.EXIT])
    camp.run(game)


def buff_case(folder, root, spell, target_index, watch):
    game = fixture(folder, root)
    s = game.s
    kal = s.party[4]
    at = F['memorized'] + bytes(kal.b[F['memorized']:F['memorized'] + 58]).index(21)
    kal.b[at] = 12
    s.seed = 0x1234
    target = None if target_index is None else s.party[target_index]
    fixture_player(game, [])
    assert magic.cast(game, kal, spell, target)
    rows = [buff_state(game, s.party[watch])]
    for _ in range(2):
        rest_hour(game)
        rows.append(buff_state(game, s.party[watch]))
    return rows


def sell_case(folder, root, name):
    game, _, _ = shop_check.shop_game(folder, root)
    char = game.s.party[0]
    steel_only(char, 500)
    state = lambda: dict(steel=shop_check.steel(char), weight=shop.weight(char))
    first = lambda options: 0
    M, W, L, C = shop_check.MENU, shop_check.WHO, shop_check.LIST, shop_check.CONFIRM
    start, before = state(), len(char.items)
    shop_check.play(game, (M, 'Buy'), (L, shop_check.contains(name)), (L, 'Exit'), (M, 'Exit'))
    bought = len(char.items)
    shop_check.play(game, (M, 'View'), (shop_check.SHEET, 'Items'), (shop_check.ITEMS, shop_check.last_containing(name)), (shop_check.ACTION, 'Sell'), (C, 'Yes'),
                    (shop_check.ITEMS, 'Exit'), (shop_check.SHEET, 'Exit'), (M, 'Exit'))
    return dict(start=start, sold=state(), items=[before, bought, len(char.items)])


def pool_case(folder, root, amounts):
    game, _, _ = shop_check.shop_game(folder, root)
    party = game.s.party
    for char, amount in zip(party, amounts):
        steel_only(char, amount)
        rules.recalc_stats(char)
    state = lambda: [dict(steel=shop_check.steel(c), weight=shop.weight(c)) for c in party]
    pooled = []
    fixture_rows = ['Pool']
    def player(kind, options, current, **info):
        if kind == Kind.ACK.value: return 0
        if fixture_rows:
            label = fixture_rows.pop(0)
            return options.index(label)
        pooled.append(state())
        fixture_rows.append('Share')
        game.player = second
        return options.index(fixture_rows.pop(0))
    def second(kind, options, current, **info):
        if kind == Kind.ACK.value: return 0
        return options.index('Exit')
    game.player = player
    shop.run(game)
    return dict(pooled=pooled[0], shared=state())


def second_round(folder, root):
    found = dict(temple=temple_cases(folder, root), train=train_cases(folder, root), ready=ready_case(folder, root),
                 buffs=dict(enlarge_max=buff_case(folder, root, 12, 0, 0), enlarge=buff_case(folder, root, 12, 3, 3), bless=buff_case(folder, root, 1, None, 0)),
                 sell=dict(ring=sell_case(folder, root, 'Ring Mail'), darts=sell_case(folder, root, '4 Darts'), bow=sell_case(folder, root, 'Short Bow')),
                 pool=pool_case(folder, root, [103, 1, 0, 0, 7, 0]))
    differences = {}
    def walk(path, a, b):
        if isinstance(a, dict):
            for key in a: walk(path + '.' + key, a[key], b.get(key) if isinstance(b, dict) else None)
        elif isinstance(a, list) and a and isinstance(a[0], (dict, list)):
            for index, item in enumerate(a): walk('%s[%d]' % (path, index), item, b[index] if isinstance(b, list) and index < len(b) else None)
        elif a != b: differences[path.lstrip('.')] = (a, b)
    walk('', SECOND, found)
    return differences


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-oracle-') as root:
        records(folder, root)
        results = dict(rest=rest(folder, root), cure=cure(folder, root), shop=armoury(folder, root))
        second = second_round(folder, root)
    differences = {key: results['shop'][key] for key in ('bought', 'sold') if results['shop'][key] != SHOP[key]}
    assert differences == KNOWN_DIFFERENCES, differences
    assert second == KNOWN_SECOND, second
    return 'PASS live records, rest, cure, shop, temple, training, Ready, camp buffs, Sell, Pool and Share against the original; number differences: %d' % (len(differences) + len(second))


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
