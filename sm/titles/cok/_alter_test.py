import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sm.titles.cok import alter, creation
from sm.titles.cok.alter import Kind
from sm.titles.cok.creation import F, Kind as CK
from sm.titles.cok.menu import Game
from sm.titles.cok.records import SavedGame

MENU, ORDER, LEVEL, SPEED, PICS, CONFIRM, ACK = (k.value for k in (Kind.MENU, Kind.ORDER, Kind.LEVEL, Kind.SPEED, Kind.PICS, Kind.CONFIRM, Kind.ACK))
ICON, WHO, MAIN, QUIT, INIT, SLOT = CK.ICON.value, CK.WHO.value, CK.MAIN_MENU.value, CK.QUIT.value, CK.INIT.value, CK.SLOT.value
EXIT = creation.EXIT


def game_for(folder, root, load=True):
    seen, notes = [], []
    def player(kind, options, game, **info):
        seen.append(game.state_hash())
        if info.get('message'): notes.append(info['message'])
        if kind == ACK:
            notes.append(info['prompt'])
            return 0
        expected, answer = next(game.rows)
        assert kind == expected, (kind, expected, info)
        game.last_info = info
        return answer if options is None else options.index(answer)
    game = Game(player, slot=None, directory=folder); game.roster_directory = root
    if load: creation.load_game(game, 'A')
    return game, seen, notes


def alter_run(game, *rows):
    game.rows = iter(rows + ((MENU, EXIT),))
    return alter.run(game)


def names(s):
    return [creation.member_title(c) for c in s.party]


def settings(folder, root):
    game, seen, _ = game_for(folder, root)
    s = game.s
    alter_run(game, (MENU, 'Level'), (LEVEL, 'Champion'))
    assert s.r0[alter.DIFFICULTY_CELL] == 5
    alter_run(game, (MENU, 'Level'), (LEVEL, EXIT))
    assert s.r0[alter.DIFFICULTY_CELL] == 5
    before = creation.game_setting(s, creation.DELAY)
    alter_run(game, (MENU, 'Speed'), (SPEED, 'Slower'), (SPEED, 'Faster'), (SPEED, 'Faster'), (SPEED, EXIT))
    assert s.g[creation.DELAY] == before - 1
    alter_run(game, (MENU, 'Pics'), (PICS, 'Pics on'), (PICS, 'Pics off'), (PICS, EXIT)) if creation.game_setting(s, creation.PICTURES) else None
    s.g[creation.PICTURES], s.g[creation.ANIMATIONS] = 1, 1
    alter_run(game, (MENU, 'Pics'), (PICS, 'Animation on'), (PICS, EXIT))
    assert s.g[creation.ANIMATIONS] == 0
    creation.save_game(game, 'B')
    saved = SavedGame(Path(root, 'B', 'SAVGAMB.DAT').read_bytes()).get('zone0')
    assert saved[creation.DELAY_CELL * 2] == before - 1 and saved[creation.PICTURES_CELL * 2] == 2
    return seen


def fresh_defaults(folder, root):
    game, _, _ = game_for(folder, root, load=False)
    assert (creation.game_setting(game.s, creation.DELAY), creation.game_setting(game.s, creation.PICTURES)) == (4, 1)


def party_order(folder, root):
    game, seen, _ = game_for(folder, root)
    s = game.s
    start = names(s)
    s.sel = 1
    alter_run(game, (MENU, 'Order'), (ORDER, 'Up'), (ORDER, EXIT))
    assert names(s) == [start[1], start[0]] + start[2:] and s.sel == 0
    alter_run(game, (MENU, 'Order'), (ORDER, 'Up'), (ORDER, EXIT))
    assert names(s) == [start[0]] + start[2:] + [start[1]] and s.sel == 5
    alter_run(game, (MENU, 'Order'), (ORDER, 'Down'), (ORDER, 'Previous'), (ORDER, EXIT))
    assert names(s)[0] == start[1] and s.sel == len(s.party) - 1
    order_now = names(s)
    creation.save_game(game, 'C')
    other, _, _ = game_for(folder, root, load=False)
    creation.load_game(other, 'C')
    assert names(other.s) == order_now, 'the save reflects the order'
    return seen


def drop_cases(folder, root):
    game, seen, notes = game_for(folder, root)
    s = game.s
    first = names(s)[0]
    alter_run(game, (MENU, 'Drop'), (WHO, first), (CONFIRM, 'No'))
    assert first in names(s) and any('sigh of relief' in n for n in notes)
    alter_run(game, (MENU, 'Drop'), (WHO, first), (CONFIRM, 'Yes'))
    assert first not in names(s) and s.r1[creation.PARTY_SIZE] == 5
    while len(s.party) > 1: creation.remove_creature(game, s.party[0])
    last = names(s)[0]
    game.rows = iter(((MENU, 'Drop'), (WHO, last), (CONFIRM, 'Yes')))
    assert alter.run(game) is True and s.stop == 1 and not s.party
    return seen


def icon(folder, root):
    game, seen, _ = game_for(folder, root)
    char = game.s.party[0]
    name = creation.member_title(char)
    head = char.b[F['icon_head']]
    wanted = str((head + 1) % 14)
    alter_run(game, (MENU, 'Icon'), (WHO, name), (ICON, 'Head'), (ICON, wanted), (ICON, 'Keep'))
    assert char.b[F['icon_head']] == int(wanted)
    creation.save_game(game, 'D')
    other, _, _ = game_for(folder, root, load=False)
    creation.load_game(other, 'D')
    assert other.s.party[0].b[F['icon_head']] == int(wanted)
    return seen


def main_menu(folder, root):
    game, seen, notes = game_for(folder, root, load=False)
    labels = game.assets.labels
    def menu(*rows):
        game.rows = iter(rows)
        creation.run(game)
    menu((MAIN, labels[creation.INIT]), (INIT, 'mouse OFF'), (INIT, 'mouse ON'), (INIT, EXIT), (MAIN, labels[creation.QUIT]), (QUIT, 'No'), (MAIN, labels[creation.QUIT]), (QUIT, 'Yes'))
    assert game.s.stop == 1 and game.s.g['input.mouse'] == 0, 'no party: a single question'
    other, more, _ = game_for(folder, root)
    labels = other.assets.labels
    other.rows = iter(((MAIN, labels[creation.QUIT]), (QUIT, 'Yes'), (QUIT, 'No'), (SLOT, 'E'), (MAIN, labels[creation.QUIT]), (QUIT, 'Yes')))
    creation.run(other)
    assert other.s.stop == 1 and Path(root, 'E', 'SAVGAME.DAT').is_file(), 'declining saves, and a just-saved party quits on one question'
    return seen + more


def test(folder=None):
    from unittest import SkipTest
    folder = folder or os.environ.get('SM_COK')
    if not folder or not Path(folder).is_dir(): raise SkipTest('SM_COK is not set')
    os.environ.setdefault('SM_COK', str(folder))
    with tempfile.TemporaryDirectory(prefix='cok-alter-') as first, tempfile.TemporaryDirectory(prefix='cok-alter-') as second:
        fresh_defaults(folder, first)
        run = lambda root: (settings(folder, root), party_order(folder, root), drop_cases(folder, root), icon(folder, root), main_menu(folder, root))
        one, two = run(first), run(second)
        assert one == two, 'replay diverged'
    return 'PASS level, speed, pics, order, drop, icon, init, exit; %d decisions' % sum(len(r) for r in one)


if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
