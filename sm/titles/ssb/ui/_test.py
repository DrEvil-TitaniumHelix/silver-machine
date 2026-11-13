import sys
from types import SimpleNamespace

from sm.engine import Session
from sm.titles.ssb.units import shops
from sm.titles.ssb.ui.screen import Assets, Controller, Frame, LOCAL, menu_items, render


def townhall(controller, reference=None):
    session = controller.session
    for _ in range(32):
        decision = session.decision
        assert decision is not None, session.result
        if reference is not None:
            assert decision == reference.decision, 'boot decision diverged'
        if decision['kind'] == 'MOVE':
            s = session.game.s
            assert (s.dataset, s.block, s.x, s.y, s.dir) == (1, 16, 3, 3, 4)
            return
        if decision['kind'] == 'SHOP_MENU' and decision['info'].get('purpose') in ('take', 'treasure', 'treasure leave'):
            answer = decision['options'].index('no' if decision['info']['purpose']=='treasure leave' else 'exit')
            key = next(key for i, key, _ in menu_items(decision) if i == answer)
            assert controller.key(key, key)
        else:
            assert decision['kind'] == 'MENU' and len(menu_items(decision)) == 1, decision['kind']
            answer = 0
            assert controller.key('Return')
        if reference is not None:
            reference.step(answer)
    raise AssertionError('save A did not reach the town hall')


def test_input():
    class Stub:
        def __init__(self):
            self.decision = {'kind': 'NUMBER', 'options': None, 'info': {'min': 1, 'max': 20}}
            self.game = SimpleNamespace(vm=SimpleNamespace(out=[]))
            self.answers = []

        def step(self, answer):
            self.answers.append(answer)

    stub = Stub()
    controller = Controller(stub)
    assert not controller.key('2', '2')
    assert not controller.key('1', '1')
    assert not controller.key('Return') and not stub.answers
    assert controller.error
    controller.key('BackSpace')
    assert controller.key('Return') and stub.answers == [2]
    stub.decision = {'kind': 'STRING', 'options': None, 'info': {}}
    for ch in 'Ab c':
        assert not controller.key(ch, ch)
    assert controller.key('Return') and stub.answers[-1] == 'Ab c'
    stub.decision = {'kind': 'MENU', 'options': ['Sell', 'Save', 'Search', None], 'info': {}}
    items = menu_items(stub.decision)
    assert len({key for _, key, _ in items}) == 4
    for index, key, _ in items:
        assert controller.key(key, key) and stub.answers[-1] == index
    assert controller.key('Return') and stub.answers[-1] == 0
    before = len(stub.answers)
    assert not controller.key('Left') and len(stub.answers) == before
    stub.decision = {'kind': 'LIST', 'options': ['Same'] * 45, 'info': {}}
    items = menu_items(stub.decision)
    for page in range(5):
        for index, key, _ in items[page * 10:(page + 1) * 10]:
            controller.page = page; controller.selected = index
            assert not controller.key('5', '5')
            assert controller.key('Return') and stub.answers[-1] == index
    controller.page = 4
    assert not controller.key('Next') and controller.page == 4


def test_render(controller, assets):
    session = controller.session
    before = session.game.s.hash(session.game.vm)
    frame = render(controller, assets)
    assert session.game.s.hash(session.game.vm) == before
    assert len(frame.rows) == 200 and all(len(row) == 320 for row in frame.rows)
    assert all(0 <= pixel < 16 for row in frame.rows for pixel in row)
    for i, member in enumerate(session.game.s.party):
        row = 4 + i
        assert any(frame.rows[y][136:256].count(15 if i == session.game.s.sel else 11)
                   for y in range(row * 8, row * 8 + 8))
        assert any(any(frame.rows[y][256:312]) for y in range(row * 8, row * 8 + 8))
    assert not controller.text.strip(), 'empty PRINTCLEAR left the town-hall text on screen'
    assert any(any(row) for row in frame.rows[192:]), 'menu bar empty'
    clipped = Frame()
    clipped.rect(-2, -2, 4, 4, 7)
    clipped.blit(319, 199, ((1, 2), (3, 4)))
    assert clipped.rows[0][:3] == bytes((7, 7, 0)) and clipped.rows[199][-1] == 1
    assert all(len(row) == 320 for row in clipped.rows)
    return frame


def test(screenshot=False):
    test_input()
    from sm.titles.ssb.ui._menus_test import test as check_menus
    check_menus()
    ui, reference = Session(engines=True), Session(engines=True)
    assets = Assets()
    try:
        controller = Controller(ui)
        townhall(controller, reference)
        frame = test_render(controller, assets)
        if screenshot:
            frame.save(LOCAL / 'ui_townhall.png')
        start = (ui.game.s.x, ui.game.s.y)
        assert not controller.key('m', 'm')
        for key, value in (('Left', 'turn-left'), ('Right', 'turn-right'), ('Up', 'forward'),
                           ('Left', 'turn-left'), ('Right', 'turn-right')):
            assert ui.decision == reference.decision
            assert ui.decision['kind'] == 'MOVE'
            answer = 0 if value is None else reference.decision['options'].index(value)
            assert controller.key(key)
            reference.step(answer)
            assert ui.decision == reference.decision, 'keyboard replay diverged'
            render(controller, assets)
        assert (ui.game.s.x, ui.game.s.y) != start, 'forward did not walk'
        assert ui.game.trace == reference.game.trace, 'decision trace differs'
        assert ui.game.s.hash(ui.game.vm) == reference.game.s.hash(reference.game.vm)
        take = Session(engines=True)
        try:
            while take.decision['kind'] != 'SHOP_MENU': take.step(0)
            assert take.decision['info']['purpose'] == 'treasure'
            take.step(take.decision['options'].index('take'))
            tc = Controller(take); assert tc.key('Down') and take.game.s.sel == 1, 'Down did not move SelectedChar'
            assert 'char-down' not in [label for _, _, label in menu_items(take.decision, take.game)], 'roster keys shown as menu words'
            assert take.game.s.treasure_money[5] == 20; render(tc, assets)
            tc.key('m', 'm'); tc.key('Return'); assert take.decision['kind'] == 'NUMBER', 'no amount prompt'
            for ch in '20': tc.key(ch, ch)
            tc.key('Return'); assert shops.coins(take.game.s.party[1])[5] == 20, 'gems not given to the selected member'
        finally: take.close()
        assert 'tkinter' not in sys.modules, 'headless check imported tkinter'
        print('UI1 town hall 1/16 (3,3,S), roster/text/menu drawn; %d decisions, replay identical%s' %
              (len(ui.game.trace), '; local/ui_townhall.png' if screenshot else ''))
    finally:
        ui.close()
        reference.close()
