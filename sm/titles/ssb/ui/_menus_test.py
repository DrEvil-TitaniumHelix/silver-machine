from types import SimpleNamespace
from unittest.mock import patch

from sm.titles.ssb.host import Game
from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui.screen import layout


class Fixture:
    def __init__(self, game, kind, options, **info):
        self.game, self.answers, self.result = game, [], None
        self.decision = dict(kind=kind, options=options, info=info, i=0, hash=game.s.hash(game.vm))

    def step(self, answer):
        self.answers.append(answer)


def drawing(controller):
    calls, original = [], screen.Frame.text

    def text(frame, col, row, value, *args, **kwargs):
        calls.append((col, row, str(value)))
        return original(frame, col, row, value, *args, **kwargs)

    with patch.object(screen.Frame, 'text', text):
        frame = screen.render(controller)
    return frame, calls


def menus(game):
    options = ['Alpha action', 'Beta action', 'Gamma action', 'Delta action', 'Exit']
    session = Fixture(game, 'MENU', options)
    controller = screen.Controller(session)
    items = screen.menu_items(session.decision, game)
    assert screen.compact_menu(items, session.decision) and len(screen.menu_pages(items)) == 2
    before = game.s.hash(game.vm)
    frame, calls = drawing(controller)
    assert (17, 2, 'Name') in calls
    assert all(row == 24 for _, row, text in calls if text in options)
    assert not any('Next Prev' in text for _, _, text in calls)
    assert not controller.key('Next') and controller.page == 1
    assert controller.key('Return') and session.answers == [3]
    assert before == game.s.hash(game.vm)
    hidden = Fixture(game, 'SHOP_MENU', ['alpha', 'char-up', 'beta', 'char-down', 'exit'])
    assert [i for i, _, _ in screen.menu_items(hidden.decision, game)] == [0, 2, 4]
    numeric = screen.Controller(hidden)
    assert numeric.key('2', '2') and hidden.answers == [3]
    assert numeric.key('8', '8') and hidden.answers == [3, 1]
    numeric.selected = 0
    assert not numeric.key('6', '6') and numeric.selected == 2
    assert not numeric.key('4', '4') and numeric.selected == 0
    levels = Fixture(game, 'MENU', ['SURFACE','7','char-up','char-down','char-first'])
    elevator = screen.Controller(levels)
    assert elevator.key('7','7') and levels.answers == [4] and elevator.selected == 1
    assert elevator.key('Return') and levels.answers == [4,1]
    fixture = Fixture(game, 'LIST', ['Alpha', 'Beta'])
    _, calls = drawing(screen.Controller(fixture))
    assert any('Next Prev' in text for _, _, text in calls)
    race = Fixture(game, 'CREATE_RACE', [1, 2, None]); picker = screen.Controller(race)
    _, calls = drawing(picker)
    assert (1, 2, 'Pick Race') in calls and (3, 3, screen.string(0xD71 + 9, 8)) in calls
    assert (0, 24, 'Select') in calls and (7, 24, 'Exit') in calls
    assert [i for i, _, _ in screen.menu_items(race.decision, game)] == [0, 1]
    picker.key('Down'); assert picker.key('Return') and race.answers == [1]
    assert picker.key('Escape') and race.answers[-1] == 2
    vertical = Fixture(game, 'MENU', ['Alpha', 'Beta'], vertical=1, prompt='Choose:')
    _, calls = drawing(screen.Controller(vertical))
    assert (17, 2, 'Name') in calls and (1, 17, 'Choose:') in calls and (1, 18, 'Alpha') in calls
    assert (0, 24, 'Select') in calls and not any('Next Prev' in text for _, _, text in calls)
    top = Fixture(game, 'CREATE_MENU', ['create', 'add', 'drop', 'modify', 'view', 'remove',
                                      'save', 'begin', 'train', 'change class', 'exit'])
    controller = screen.Controller(top)
    _, calls = drawing(controller)
    items = screen.menu_items(top.decision, game)
    assert (1, 2, 'Name') in calls and (9, 22, items[-1][2]) in calls
    assert [i for i, _, _ in items] == [0, 2, 3, 8, 9, 4, 1, 5, 6, 7, 10], 'native order changed engine indices'
    assert not controller.key('Next') and controller.page == 0
    assert len([r for r in layout(controller)['regions'] if 'select' in r]) == 11
    controller.key('End'); controller.key('Up'); assert controller.key('Return') and top.answers == [10]


def roster(game):
    game.s.sel = 2
    for kind, options, info in (
            ('WHO', [screen.pstring(c.b) for c in game.s.party], {'prompt': 'Who will go?'}),
            ('TARGET', list(range(len(game.s.party))) + [None], {'purpose': 'party member'})):
        session = Fixture(game, kind, options, **info)
        controller = screen.Controller(session)
        before = game.s.hash(game.vm)
        assert controller.selected == 2 and controller.roster_selected() == 2
        assert not controller.key('Down') and controller.roster_selected() == 3
        frame, calls = drawing(controller)
        assert (17, 2, 'Name') in calls
        assert any(row == 24 and text.startswith('Select') for _, row, text in calls)
        assert not any('Next Prev' in text for _, _, text in calls)
        assert any(15 in frame.rows[y][136:256] for y in range(56, 64))
        assert before == game.s.hash(game.vm) and not session.answers
        assert controller.key('Return') and session.answers == [3]
        controller.key('Home'); controller.key('Up')
        assert controller.roster_selected() == len(game.s.party) - 1
        if kind == 'TARGET':
            assert controller.key('Escape') and session.answers[-1] == len(game.s.party)


def text_window(game):
    vm = game.vm
    session = Fixture(game, 'MENU', ['Yes', 'No'])
    controller = screen.Controller(session)
    vm.out.append('old event'); controller.capture_text()
    assert controller.text.endswith('old event')
    vm.ops, vm.strs, vm.cur, vm.next = [(0x80, 0, 0, None)], ['', 'new event'], 0x12, vm.pc
    before = game.s.hash(vm)
    vm.op11(); controller.capture_text()
    assert controller.text == 'new event' and game.s.hash(vm) == before, 'PRINTCLEAR inserted a blank first row'
    vm.cur, vm.strs = 0x11, ['', ' continues']; vm.op11(); controller.capture_text()
    assert controller.text.strip() == 'new event continues'
    vm.cur, vm.strs = 0x12, ['', '']; vm.op11(); controller.capture_text()
    assert not controller.text.strip(), 'empty PRINTCLEAR is a clear event'
    vm.out.append('another event'); controller.capture_text(); vm.op3D(); controller.capture_text()
    assert not controller.text.strip() and 'old event' in vm.out
    for action in ('turn-left', 'turn-right', 'turn-around', 'forward', 'look'):
        game.player = lambda kind, opts, game, **info: opts.index(action)
        vm.out.append('stale building sign'); controller.capture_text()
        with patch.object(vm, 'run'), patch.object(game, 'move_party'):
            game.turn()
        controller.capture_text()
        if action in ('forward', 'look'): assert not controller.text.strip(), action
        else: assert controller.text.strip().endswith('stale building sign'), action


def question(game):
    game.s.dataset = 1
    game.vm.load_block(16)
    seen = []

    def answer(kind, options, current, **info):
        fixture = Fixture(current, kind, options, **info)
        controller = screen.Controller(fixture)
        _, calls = drawing(controller)
        seen.append((kind, options, controller.text, calls))
        return 1

    game.player = answer
    game.vm.run(0x99D4)
    assert len(seen) == 1 and seen[0][0:2] == ('MENU', ['YES', 'NO', 'char-up', 'char-down', 'char-first'])
    assert seen[0][2].rstrip().endswith('?')
    assert any(row == 24 and text == 'YES' for _, row, text in seen[0][3])
    fixture = Fixture(game, 'MOVE', game.moves())
    assert not screen.Controller(fixture).text.strip(), 'answered question leaked onto movement'


def commands(game):
    session = Fixture(game, 'MOVE', game.moves())
    controller = screen.Controller(session)
    assert [label for _, _, label in screen.menu_items(session.decision, game)] == [
        'Move', 'Area', 'Cast', 'View', 'Encamp', 'Search', 'Look']
    assert not controller.key('Return') and controller.move_mode and not session.answers
    assert controller.key('Left') and session.answers[-1] == 0
    assert not controller.key('Escape') and controller.move_mode
    assert not controller.key('Return') and not controller.move_mode
    assert controller.key('Down') and session.answers[-1] == session.decision['options'].index('char-down')
    wait = Fixture(game, 'MENU', ['Press Return to continue.'])
    controller = screen.Controller(wait)
    assert not controller.key('Up') and not wait.answers and not controller.error
    assert not controller.key('F2') and not wait.answers and 'Return' in controller.error
    _, calls = drawing(controller)
    assert (1, 22, 'Press Return to continue.') in calls
    assert controller.key('Return') and wait.answers == [0]
    for action in ('cast', 'view'):
        game.player = lambda kind, options, current, **info: options.index(action)
        with patch('sm.titles.ssb.units.camp.cast_command') as cast, patch('sm.titles.ssb.units.shops.view') as view:
            game.turn()
            assert (cast if action == 'cast' else view).call_count == 1


def creation_icon_preview(game):
    from sm.titles.ssb.units import creation
    candidate = creation.from_image(creation.image(game.s.party[0])); candidate.b[0x153] = 13
    game.s.g['creation.pending'] = creation.image(candidate)
    try:
        fixture = Fixture(game, 'CREATE_ICON', list(range(14)) + [None], field='head')
        picker = screen.Controller(fixture); before = game.s.hash(game.vm)
        assert not picker.key('n', 'n') and picker.icon_value == 0 and not fixture.answers
        assert not picker.key('p', 'p') and picker.icon_value == 13 and game.s.hash(game.vm) == before
        assert picker.key('k', 'k') and fixture.answers == [13]
        assert picker.key('Escape') and fixture.answers[-1] == 14
        assert game.s.hash(game.vm) == before
        assert [r['key']['char'] for r in layout(picker)['regions']] == ['n', 'p', 'k', 'e']
    finally: game.s.g.pop('creation.pending', None)


def script_engine(game):
    from collections import deque
    session = Fixture(game, 'MENU', ['YES', 'NO']); controller = screen.Controller(session, presentation=True)
    vm = game.vm; shown = vm.display; vm.display = {'kind': None}
    try:
        assert isinstance(game.presentation, deque) and not game.presentation
        vm.clear_text(); vm.out.append('HELD TEXT'); vm.op3A(); vm.clear_text(); vm.out.append('LATER TEXT')
        assert [e['kind'] for e in game.presentation] == ['script-hold']
        _, calls = drawing(controller); words = [text for _, _, text in calls]
        assert 'HELD TEXT' in words and 'LATER TEXT' not in words and 'YES' not in words and 'Name' in words, words
        controller.presentation_deadline = 0; _, calls = drawing(controller); words = [text for _, _, text in calls]
        assert 'LATER TEXT' in words and 'YES' in words and 'HELD TEXT' not in words, words
    finally:
        vm.display = shown; game.presentation = None; vm.clear_text()
    leave = Fixture(game, 'CREATE_EXIT', ['continue', 'exit'], prompt='Quit to DOS ')
    controller = screen.Controller(leave); controller.creation_background = screen.capture_background(controller)
    assert screen.menu_items(leave.decision, game) == [(1, 'y', 'Yes'), (0, 'n', 'No')] and controller.selected == 0
    _, calls = drawing(controller)
    assert (0, 24, 'Quit to DOS ') in calls and (12, 24, 'Yes') in calls and (16, 24, 'No') in calls, calls
    assert controller.key('y', 'y') and leave.answers == [1]
    assert controller.key('n', 'n') and leave.answers == [1, 0]
    typed = screen.Controller(Fixture(game, 'STRING', None))
    for char in ' A B': typed.key('space' if char == ' ' else char, char)
    assert typed.entry == 'A B', typed.entry
    fight = Fixture(game, 'COMBAT_ACTION', ['move', 'guard', 'flee', 'done'], actor=0); controller = screen.Controller(fight)
    with patch.object(screen, 'player_menu', return_value=[(0, 'm', 'Move'), (3, 'd', 'Done')]):
        controller.key('g', 'g'); controller.key('f', 'f')
        assert fight.answers == [], fight.answers
        controller.key('d', 'd')
    assert fight.answers == [3], fight.answers


def test():
    game = Game(lambda *_args, **_info: 0, engines=True)
    game.s.mode = 4
    game.geo.map = SimpleNamespace(walls=lambda *_: 0, attr=lambda *_: 0, passages=lambda *_: 1)
    menus(game); roster(game); text_window(game); question(game); commands(game); creation_icon_preview(game); script_engine(game)
    print('menus/roster/text: horizontal vs e5, WHO, empty PRINTCLEAR, movement, teleporter, Return: PASS')
