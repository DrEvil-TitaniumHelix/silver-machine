import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import creation, rules, shop, temple
from sm.titles.cok.creation import F, dice
from sm.titles.cok.effects import add_effect, has_effect
from sm.titles.cok.menu import Game
from sm.titles.cok.shop import I
from sm.titles.cok.temple import Kind

MENU, LIST, CONFIRM, WHO, ACK = Kind.MENU.value, Kind.LIST.value, Kind.CONFIRM.value, shop.Kind.WHO.value, shop.Kind.ACK.value
EXIT = 'Exit'


def temple_game(folder, root):
    seen, notes = [], []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if info.get('message'): notes.append(info['message'])
        if info.get('offer'): notes.append(info['offer'])
        if kind == ACK:
            notes.append(info['prompt'])
            return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        return options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    creation.load_game(game, 'A'); game.s.mode = 4
    for char in game.s.party: del char.effects[:]
    return game, seen, notes


def visit(game, char, *rows):
    name = shop.member_name(char)
    game.s.sel = game.s.party.index(char)
    game.rows = iter(((MENU, 'Heal'),) + rows + ((LIST, EXIT), (MENU, EXIT)))
    temple.run(game)


def steel(char):
    return shop.coins(char)[shop.STEEL]


def purse(char, amount):
    shop.put_coins(char, [0, 0, 0, 0, amount, 0, 0])
    rules.recalc_stats(char)


def paid(*rows):
    return tuple(rows) + ((CONFIRM, 'Yes'),)


def wounds(folder, root):
    game, seen, _ = temple_game(folder, root)
    char = game.s.party[0]; purse(char, 1000)
    char.b[F['hp']] = 1
    roll = dice(game.s.copy(), 1, 8)
    visit(game, char, (LIST, 'Cure Light Wounds'), (CONFIRM, 'Yes'))
    assert steel(char) == 950 and char.b[F['hp']] == min(1 + roll, char.b[F['hp_max']])
    return seen


def poison(folder, root):
    game, seen, _ = temple_game(folder, root)
    char = game.s.party[0]; purse(char, 1000)
    char.b[F['hp']], char.b[F['status']], char.b[F['active']] = 0, 6, 0
    add_effect(char, 55, 0, 255, False); add_effect(char, 22, 60, 255, True); add_effect(char, 15, 10, 255, True)
    visit(game, char, (LIST, 'Neutralize Poison'), (CONFIRM, 'Yes'))
    assert steel(char) == 500 and (char.b[F['hp']], char.b[F['status']], char.b[F['active']]) == (1, 0, 1)
    assert not char.effects, 'the lock stops poison renewing itself'
    return seen


def curse(folder, root):
    game, seen, notes = temple_game(folder, root)
    char = game.s.party[0]; purse(char, 4000)
    add_effect(char, 36, 0, 255, False)
    visit(game, char, (LIST, 'Remove Curse'), (CONFIRM, 'Yes'))
    assert steel(char) == 2250 and has_effect(char, 36) is None and any('un-cursed' in n for n in notes)
    item = char.items[0]; item[I['cursed']], item[I['readied']] = 1, 1
    item[I['powers']:I['powers'] + 3] = bytes((0, 77, 0x81))
    add_effect(char, 77, 0, 0, False)
    visit(game, char, (LIST, 'Remove Curse'), (CONFIRM, 'Yes'))
    assert steel(char) == 500 and item[I['readied']] == 0 and item[I['cursed']] == 1 and has_effect(char, 77) is None
    return seen


def raise_cases(folder, root):
    game, seen, notes = temple_game(folder, root)
    human = game.s.party[0]; b = human.b; purse(human, 6000)
    b[F['hp']], b[F['status']], b[F['active']] = 0, 6, 0
    con, hp_max, rolled = b[F['abilities'] + 2 * 4 + 1], b[F['hp_max']], b[F['hp_rolled']]
    visit(game, human, (LIST, 'Raise Dead'), (CONFIRM, 'Yes'))
    assert (b[F['hp']], b[F['status']], b[F['active']]) == (1, 0, 1) and b[F['abilities'] + 2 * 4 + 1] == con - 1 and steel(human) == 3250
    now = con - 1
    expected = hp_max
    if now >= 14:
        bonus = sum(((now - 14) * level if cls == 2 else level * 2 if now > 15 else level) for cls, level in enumerate(creation.levels(b)) if level > 0)
        loss = max(hp_max - rolled, 0)
        if bonus: loss //= bonus
        if now < 17 or b[F['levels'] + 2] > 0: expected = hp_max - loss
    assert b[F['hp_max']] == expected, (b[F['hp_max']], expected)
    elf = next(c for c in game.s.party if c.b[F['race']] < 2); e = elf.b; purse(elf, 3000)
    e[F['hp']], e[F['status']], e[F['active']] = 0, 6, 0
    visit(game, elf, (LIST, 'Raise Dead'), (CONFIRM, 'No'))
    assert steel(elf) == 3000 and e[F['status']] == 6
    visit(game, elf, (LIST, 'Raise Dead'), (CONFIRM, 'Yes'), (CONFIRM, 'Yes'))
    assert steel(elf) == 250 and e[F['status']] == 6 and e[F['hp']] == 0, 'an elf pays and is not raised'
    return seen


def refusals(folder, root):
    game, seen, notes = temple_game(folder, root)
    char = game.s.party[0]; purse(char, 10)
    char.b[F['hp']] = 1
    visit(game, char, (LIST, 'Cure Light Wounds'), (CONFIRM, 'Yes'))
    assert 'Not enough money.' in notes and steel(char) == 10 and char.b[F['hp']] == 1
    notes.clear()
    visit(game, char, (LIST, 'Cure Blindness'), (CONFIRM, 'No'))
    assert steel(char) == 10
    purse(char, 1000)
    add_effect(char, 33, 0, 255, False)
    visit(game, char, (LIST, 'Cure Blindness'), (CONFIRM, 'Yes'))
    assert steel(char) == 500 and has_effect(char, 33) is None
    return seen


def pool_pays(folder, root):
    game, seen, _ = temple_game(folder, root)
    s = game.s
    char, other = s.party[0], s.party[1]
    purse(char, 10); purse(other, 400)
    for c in s.party[2:]: purse(c, 0)
    char.b[F['hp']] = 1
    name = shop.member_name(char)
    s.sel = 0
    game.rows = iter(((MENU, 'Pool'), (MENU, 'Heal'), (LIST, 'Cure Light Wounds'), (CONFIRM, 'Yes'), (LIST, EXIT), (MENU, 'Share'), (MENU, EXIT)))
    temple.run(game)
    assert sum(steel(c) for c in s.party) == 360 and char.b[F['hp']] > 1
    return seen


def left_money(folder, root):
    game, seen, notes = temple_game(folder, root)
    game.rows = iter(((MENU, 'Pool'), (MENU, EXIT), (shop.Kind.CONFIRM.value, 'Yes'), (MENU, 'Share'), (MENU, EXIT)))
    temple.run(game)
    assert 'As you leave a priest says, "Excuse me but you have left some money here" ' in notes, notes
    return seen


def menu_table(folder, root):
    game, _, _ = temple_game(folder, root)
    assert temple.names(game)[0] == 'Cure Blindness' and temple.names(game)[9] == 'Stone to Flesh' and tuple(game.assets.table('diseaseEffects')) == (31, 34, 43, 44, 50, 57)


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-temple-') as first, tempfile.TemporaryDirectory(prefix='cok-temple-') as second:
        menu_table(folder, first)
        run = lambda root: (wounds(folder, root), poison(folder, root), curse(folder, root), raise_cases(folder, root), refusals(folder, root), pool_pays(folder, root), left_money(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS wounds, poison, curse, raise, refusals, pool pays; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
