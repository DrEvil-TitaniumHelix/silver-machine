"""UI2 menus, input and encounter checks over original data and real decisions."""
from sm.titles.ssb import data as ssb_data
from types import SimpleNamespace

from sm.engine import Session
from sm.titles.ssb import art
from sm.titles.ssb.ui.screen import decision_labels, draw_picture, frame_number
from sm.titles.ssb.ui._fight_test import press
from sm.titles.ssb.ui.screen import Assets, Controller, Frame, LOCAL, menu_items, render


def test(screenshot=False):
    """UI2 / ov18:30DF, ov22:0691, ov28: real treasure, camp, rest, member and spell screens."""
    from sm.titles.ssb.ui._player_screens_test import test as check_player_screens
    check_player_screens(screenshot)
    ui, reference = Session(engines=True), Session(engines=True)
    controller, assets, seen = Controller(ui), Assets(), set()

    def capture(name):
        """UI1 read-only renderer contract; capture review images only under local/."""
        before = ui.game.s.hash(ui.game.vm)
        frame = render(controller, assets)
        assert before == ui.game.s.hash(ui.game.vm)
        assert any(any(row) for row in frame.rows[192:]), 'menu/input line empty'
        if screenshot:
            frame.save(LOCAL / ('ui_%s.png' % name))
        seen.add(ui.decision['kind'])
        return frame

    def answer(value):
        """UI1 Session indices: execute both runs at the same decision boundary."""
        assert ui.decision == reference.decision
        index = ui.decision['options'].index(value) if ui.decision['options'] is not None else value
        press(controller, index)
        reference.step(index)
        assert ui.decision == reference.decision

    try:
        for _ in range(32):
            if ui.decision['kind'] == 'SHOP_MENU':
                break
            answer(ui.decision['options'][0])
        assert ui.decision['kind'] == 'SHOP_MENU'
        answer('take')  # ov07:1158: the restored outer treasure menu precedes Money/Items.
        capture('shop')
        answer('items')
        assert ui.decision['kind'] == 'LIST' and len(ui.decision['options']) > 10
        names = decision_labels(ui.game, ui.decision)
        assert all(not label.isdecimal() for label in names)
        capture('items')
        before = (ui.decision, len(ui.game.trace), ui.game.s.hash(ui.game.vm))
        # ov07:0C80..0CA4 gives Take Items22 rows; Exit is a footer, not an item.
        count=len(ui.decision['options'])-1
        assert not controller.key('Next') and controller.take_start == min(22,max(0,count-22))
        capture('items_next')
        assert not controller.key('p', 'p') and controller.take_start == 0
        assert not controller.key('Down'); selected = controller.selected
        assert not controller.key('End') and controller.selected == selected
        assert not controller.key('Home') and controller.selected == selected  # ov28:167F ignores47/4F; keep the current row.
        assert before == (ui.decision, len(ui.game.trace), ui.game.s.hash(ui.game.vm))
        index = ui.decision['options'].index(None)
        assert controller.key('Escape')
        reference.step(index)
        for _ in range(32):
            if ui.decision['kind'] == 'MOVE':
                break
            answer(('no' if ui.decision['info'].get('purpose') == 'treasure leave' else 'exit') if ui.decision['kind'] == 'SHOP_MENU' else ui.decision['options'][0])  # ov07:1251.
        assert ui.decision['kind'] == 'MOVE'
        answer('camp')
        assert ui.decision['kind'] == 'CAMP_MENU'
        capture('camp')
        answer('rest')
        answer('hours')
        assert ui.decision['info']['field'] == 'hours'  # ov22:0691 selects a clock field.
        capture('rest_time')
        answer('add')
        answer('subtract')
        answer('exit')
        caster = next(i for i, c in enumerate(ui.game.s.party) if c.b[0x111])
        # ov18:30DF uses the shared roster arrows; L is not a camp command.
        assert not controller.key('l', 'l')
        while ui.game.s.sel != caster:
            answer('char-down')
        capture('members')
        answer('magic')
        answer('memorize')
        assert ui.decision['kind'] == 'SPELL'
        names = decision_labels(ui.game, ui.decision)
        assert len(names) > 10 and all(not n.isdecimal() for n in names)
        capture('spells')
        # ov28:1157/1319: initial selection is the last visible spell; Down wraps.
        assert not controller.key('Down') and controller.selected == 0
        assert not controller.key('Next') and controller.cast_start == 11
        capture('spells_next')
        assert not controller.key('End')
        index = ui.decision['options'].index('done')
        assert controller.key('Escape')  # ov23:0225: Exit is a footer command, not a spell row.
        reference.step(index)
        assert ui.game.trace == reference.game.trace and ui.decision == reference.decision
        assert {'SHOP_MENU', 'LIST', 'CAMP_MENU', 'SPELL'} <= seen
        # STRING has the same input widget as NUMBER, with text validation covered
        # by _test.test_input; exercise its rendering without changing a live VM.
        fixture = SimpleNamespace(game=ui.game, decision={
            'kind': 'STRING', 'options': None, 'info': {'prompt': 'Enter text'}}, result=None)
        # ov24:02CC number input remains covered separately from ov22's native clock-field editor.
        number = Controller(SimpleNamespace(game=ui.game, decision={
            'kind': 'NUMBER', 'options': None, 'info': {'prompt': 'How Many', 'max': 99}}, result=None))
        number.entry = '12'
        assert any(any(row) for row in render(number, assets).rows[192:])
        text = Controller(fixture)
        text.entry = 'A' * 40
        frame = render(text, assets)
        assert any(any(row[312:320]) for row in frame.rows[192:]), 'input cursor clipped'
        if screenshot:
            frame.save(LOCAL / 'ui_string.png')
        check_pictures(ui.game)
        print('UI2 camp/shop, item/spell paging, member target, NUMBER/STRING and picture masks: PASS')
    finally:
        ui.close()
        reference.close()


def check_pictures(game):
    """ov30:07E3 / ov28:04DF: native sprite rectangle, EGA mask/remap and A4 timing."""
    before = game.s.hash(game.vm)
    # Choose shipped assets by their directory IDs; no original bytes in this test.
    from sm import dax
    rid = next(iter(dax.load('SPRIT1', d=ssb_data.SECRET)))
    decoded = art.record('SPRIT', rid)
    for distance, part in enumerate(decoded.parts[:3]):
        fixture = SimpleNamespace(s=game.s, vm=SimpleNamespace(display={
            'kind': 'SPRIT', 'dataset': 1, 'id': rid, 'frame': distance, 'pic': 255}))
        frame = Frame()
        frame.rect(0, 0, 320, 200, 7)
        assert draw_picture(frame, fixture)
        x0, y0 = 24 + part.x * 8, 24 + part.y * 8
        for y in range(24, 112):
            for x in range(24, 112):
                raw = part.frames[0][y - y0][x - x0] if (
                    x0 <= x < x0 + part.width and y0 <= y < y0 + part.height) else 0
                assert frame.rows[y][x] == (7 if raw == 0 else 0 if raw == 13 else raw)
        assert all(row[:24] == bytes([7]) * 24 and row[112:] == bytes([7]) * 208 for row in frame.rows)
    delays = [SimpleNamespace(delay=2), SimpleNamespace(delay=3)]
    assert [frame_number(delays, t) for t in (0, .19, .2, .49, .5)] == [0, 0, 1, 1, 0]
    assert game.s.hash(game.vm) == before
