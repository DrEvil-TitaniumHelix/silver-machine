"""GU-76 sm-q2: headless prompt, appraisal, training and service feedback pixels."""
from types import SimpleNamespace
from unittest.mock import patch

from sm.titles.ssb import rec
from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui.screen import Assets, Controller, Frame, render
from sm.titles.ssb.units import shops, creation
from sm.titles.ssb.units._c3_test import fresh, scripted
from sm.titles.ssb.units._services_test import setup, item


def drawn(game, kind, options, info, entry=''):
    """0540:035D / ov26:16E3: record text positions while also drawing actual glyph pixels."""
    calls = []; original = Frame.text
    session = SimpleNamespace(game=game, decision=dict(kind=kind, options=options, info=info), result=None)
    controller = Controller(session); controller.entry = entry
    def text(frame, col, row, value, *args, **kwargs):
        """0540:035D observer: retain the real rasterizer and capture its coordinates."""
        calls.append((col, row, str(value)))
        return original(frame, col, row, value, *args, **kwargs)
    before = game.s.hash(game.vm)
    with patch.object(Frame, 'text', text): frame = render(controller, Assets())
    assert game.s.hash(game.vm) == before
    return frame, calls, controller


def check_input():
    """ov24:02CC question+digits on row 24; 0540:0748 STRING uses the same readable block cursor."""
    game = fresh(lambda *a, **k: 0); setup(game)
    prompt = 'How Many Gems will you take? '
    frame, calls, controller = drawn(game, 'NUMBER', None, dict(prompt=prompt, max=20, number_prompt=True), '12')
    assert (0, 24, prompt + '12') in calls
    assert not any(prompt.strip() in value and row != 24 for _, row, value in calls)
    col = len(prompt) + 2
    assert all(frame.rows[y][8 * col:8 * (col + 1)] == bytes([15]) * 8 for y in range(192, 200))
    answers = []; controller.session.step = answers.append
    controller.entry = ''
    for ch in '21': assert not controller.key(ch, ch)
    assert controller.entry == '20' and not answers
    assert controller.key('Escape') and answers == [0]
    controller.entry = '1'; assert controller.key('Return') and answers[-1] == 1
    # A 40-character string scrolls the field, never clips away the cursor.
    frame, calls, controller = drawn(game, 'STRING', None, dict(prompt='Enter text: '), 'A' * 40)
    assert (39, 24, '%') in calls
    assert all(frame.rows[y][312:320] == bytes([15]) * 8 for y in range(192, 200))
    answers = []; controller.session.step = answers.append; controller.entry = ''
    for ch in 'Ab c': controller.key(ch, ch)
    controller.key('BackSpace'); controller.key('z', 'z'); controller.key('é', 'é')
    assert controller.key('Escape') and answers == ['Ab z']
    _, calls, _ = drawn(game, 'CREATE_NAME', None, dict(max_length=15), 'TEST')
    assert (0, 24, 'Character name: TEST') in calls
    _, calls, _ = drawn(game, 'STRING', None, {}, 'TEST')
    assert (0, 24, 'TEST') in calls        # ov03:09EB uses an empty prompt


def check_appraisal_training():
    """ov24:1B7A/1D46/20AE collection and named offers; ov19:5064 proposed levels."""
    seen = []
    policy = scripted([('SHOP_MENU', 'gems'), ('SHOP_MENU', 'keep'), ('SHOP_MENU', 'jewelry'), ('SHOP_MENU', 'sell')])
    def answer(kind, options, game, **info):
        """ov24:1C8B/1E2F/2197: inspect the actual suspended appraisal decisions."""
        frame, calls, _ = drawn(game, kind, options, info)
        assert (1, 7, 'You have a fine collection of:') in calls
        assert not any(any(row[8:312]) for row in frame.rows[40:56]), 'purse/roster leaked into appraisal'
        if info['purpose'] == 'appraisal':
            assert (1, 12, 'The %s is Valued at %d gp.' % (info['valuable'], info['value'])) in calls
            seen.append(info['valuable'])
        return policy(kind, options, game, **info)
    game = fresh(answer); setup(game); shops.put_coins(game.s.party[0], [0, 0, 0, 0, 0, 1, 1])
    shops.appraise(game, game.s.party[0]); assert seen == ['Gem', 'Jewel']
    # The source's level-up screen is shown before the answer mutates the record.
    def train_answer(kind, options, game, **info):
        """ov19:504F..51D4: actual confirmation contains class names and proposed levels."""
        assert kind == 'CREATE_TRAIN' and info['levels'] == ['a level 2 Cleric']
        frame, calls, _ = drawn(game, kind, options, info)
        assert (4, 4, 'TEST') in calls and (8, 4, ' will become:') in calls  # ov19:503F..50A6 changes colour after the name.
        assert (6, 5, '    a level 2 Cleric') in calls
        assert any('Do you wish to train?' in value for _, _, value in calls)
        assert game.s.party[0].b[0x111] == 1
        return 1
    game = fresh(train_answer); setup(game); game.s.r1[0x2A8] = 255
    rec.wrw(game.s.party[0].b, 0x12C, creation.xp_for(0, 2))
    assert not creation.train(game, game.s.party[0])


def check_result_capture():
    """ov19:01CF/0329/5004; 0540:0B9D..0BEE: refusal clears before settled top menu."""
    game = fresh(lambda *a, **k: 0); setup(game); game.s.r1[0x2A8] = 255
    assert not creation.train(game, game.s.party[0])
    game.vm.display = dict(kind='BIGPIC', id=255)  # the hall must discard the previous scene layout too.
    frame, calls, _ = drawn(game, 'CREATE_MENU', ['create', 'add', 'drop', 'modify', 'view', 'remove', 'save', 'begin', 'train', 'change class'], {})
    assert 'Not Enough Experience' in ''.join(game.vm.out)
    assert (1, 2, 'Name') in calls  # ov26:07E7..07FB: full-width top-menu roster.
    assert not any('Not Enough Experience' in value for _, _, value in calls)
    assert not any(17 <= row <= 22 and col == 1 for col, row, _ in calls)
    assert not any(any(row[8:72]) for row in frame.rows[128:184]), 'stale divider/text beside party menu'
    # DrawScreenFrame clears an existing picture too, and the list ends above row 23.
    cleared = Frame(); cleared.rect(0, 0, 320, 200, 7)
    screen.draw_frame(cleared, Assets(), 'party')
    assert not any(any(row[8:312]) for row in cleared.rows[8:184])
    assert frame.rows[184:192] == cleared.rows[184:192]
    assert (0, 24, 'Choose a FUNCTION ') in calls and (18, 24, 'Select ') in calls
    game.vm.display = {}
    shops.cure(game, game.s.party[0], 0)
    _, calls, _ = drawn(game, 'LIST', list(range(10)) + [None], dict(purpose='temple service'))
    assert 'TEST is not blind' in ''.join(game.vm.out)
    assert not any('TEST is not blind' in value for _, _, value in calls)  # ov06:008A -> ov26:1812..1827 clears the transient result before the service list.
    # ov24:0DA4: the Take Money picker shows the pile's gems; the outer Take footer retains the scene.
    game.s.treasure_money[5] = 20
    # ov07:0E10..0E47; native sm-s1-gu95-r1-area-2-064/020 keeps the party pane and Take: footer.
    _, calls, _ = drawn(game, 'SHOP_MENU', ['money', 'items', 'exit'], dict(purpose='take'))
    assert (0, 24, 'Take: ') in calls
    assert not any('gems' in value.lower() for _, _, value in calls)
    _, calls, _ = drawn(game, 'SHOP_MENU', [5, None], dict(purpose='take money', money_picker='take'))
    assert any(value.lower() == 'gems 20' for _, _, value in calls)


def test():
    """GU-76 screen kinds: NUMBER, STRING/CREATE_NAME, appraisal, training and service results."""
    check_input(); check_appraisal_training(); check_result_capture(); check_service_menus(); check_direct_view(); check_view_items(); check_item_bar(); check_slot_labels()


def check_service_menus():
    """Row 33: ov08:0889..08E9 / ov06:0CC7..0D31 menu words with/without pooled coins."""
    game = fresh(lambda *a, **k: 0); setup(game)
    for place, first in (('shop', 'buy'), ('temple', 'heal')):
        for pooled in (False, True):
            options = [first, 'view', 'pool', 'appraise', 'select', 'exit']
            if pooled: options[2:2] = ['take', 'share']
            options += list(shops.ROSTER)
            _, calls, controller = drawn(game, 'SHOP_MENU', options, dict(place=place))
            words = [first, 'view'] + (['take', 'pool', 'share'] if pooled else ['pool']) + ['appraise', 'exit']
            items = screen.menu_items(controller.session.decision, game)
            assert [(options[i], label.lower()) for i, _, label in items] == [(word, word) for word in words]
            assert len(screen.menu_pages(items)) == 1
            assert [value.lower() for _, row, value in calls if row == 24 and len(value) > 1] == words
            answers = []; controller.session.step = answers.append
            assert controller.key('e', 'e') and answers == [options.index('exit')]


def check_direct_view():
    """Row 34: ov16:09E9, ov08:091E, ov06:0D5C, ov04:0370 View SelectedChar; ov08:0719 clears."""
    from sm.titles.ssb.state import Char
    for place in ('street', 'shop', 'temple', 'vault'):
        seen = []
        def answer(kind, options, game, **info):
            """ov21:0D3B: the first decision after View belongs to the selected sheet."""
            assert kind != 'TARGET', (place, kind, info)
            _, calls, _ = drawn(game, kind, options, info)
            if info.get('purpose') == 'view':
                assert info['character'] == 'OTHER' and (1, 1, 'OTHER') in calls
                seen.append('view'); return options.index('exit')
            if seen:
                # ov08:0804/08F7 / ov06:0C89 retain the service portrait.
                assert (1,2,place) not in calls  # ov04:0071 -> ov26:3056: Vault also keeps the portrait, with no invented title.
                assert not any('Choose a member' in text for _, _, text in calls)
                return options.index('exit')
            return options.index('view')
        game = fresh(answer); setup(game)
        other = Char(bytes(game.s.party[0].b)); other.b[:16] = bytes([5]) + b'OTHER' + bytes(10)
        game.s.party.append(other); game.s.sel = 1; game.s.g['vault.image'] = bytes(28)
        if place == 'street': game.turn()
        else: getattr(shops, place)(game)
        assert seen == ['view'] and game.s.sel == 1
    steps = iter(['buy', 0, 0, None, 'exit']); results = []
    def buy_answer(kind, options, game, **info):
        """ov08:0469/0719: a second failed buy replaces the message; Exit clears it."""
        _, calls, controller = drawn(game, kind, options, info)
        results.append(controller.text.count('Not enough Money.'))
        return options.index(next(steps))
    game = fresh(buy_answer); setup(game); game.s.treasure_items = [item()]
    shops.shop(game)
    assert results == [0, 0, 1, 1, 0], results


def check_view_items():
    """Row 35: ov21:0D3B/0FA7/1014 opens a sheet, enters Items only on I, then restores the sheet."""
    steps = iter(['items', None, 'exit']); screens = []
    def answer(kind, options, game, **info):
        """ov21:0041/0D0F: inspect the actual shop View decisions, not a hand-built sheet."""
        _, calls, controller = drawn(game, kind, options, info)
        screens.append(info.get('purpose'))
        if info.get('purpose') == 'view':
            assert (1, 1, 'TEST') in calls and (20, 3, 'Hit Points') in calls
            assert [label for _, _, label in screen.menu_items(controller.session.decision, game)] == ['Items', 'Exit']
        return options.index(next(steps))
    game = fresh(answer); setup(game); game.s.party[0].items = [item()]
    shops.view(game, 'shop', character=game.s.selc())
    assert screens == ['view', 'items', 'view'], screens


def check_item_bar():
    """Row 36: ov21:13F3..15D0 keeps the conditional native menu, including Id/Join, on one row."""
    for place, mode, words in (
            ('shop', 1, 'Ready Trade Drop Halve Join Sell Id Exit'),
            ('temple', 1, 'Ready Trade Drop Halve Join Sell Id Exit'),
            ('vault', 8, 'Ready Trade Deposit Halve Join Exit'),
            ('camp', 2, 'Ready Use Trade Drop Halve Join Exit')):
        steps = iter([0, 'exit', None])
        def answer(kind, options, game, **info):
            """ov21:16E0: menu hotkeys address stable action indices, with no second page."""
            if info.get('purpose') == 'item':
                _, calls, controller = drawn(game, kind, options, info)
                items = screen.menu_items(controller.session.decision, game)
                assert ' '.join(label for _, _, label in items) == words
                assert len(screen.menu_pages(items)) == 1
                assert not any('PgUp/PgDn' in text for _, _, text in calls)
                assert options[:6] == ['ready', 'use', 'trade', 'halve', 'deposit' if place == 'vault' else 'drop', 'exit']
                assert not any(v in shops.ROSTER for v in options)
                replies = []; controller.session.step = replies.append
                for _, key, _ in items: assert controller.key(key, key)
                assert replies == [index for index, _, _ in items]
            return options.index(next(steps))
        game = fresh(answer); setup(game); game.s.mode = mode; game.s.party[0].items = [item()]
        shops.item_menu(game, game.s.party[0], place)
    # The added native Join command must conserve counts across byte overflow and scroll grouping.
    game = fresh(lambda *a, **k: 0); setup(game); c = game.s.party[0]
    c.items = [item() for _ in range(3)]
    for it, count in zip(c.items, (240, 20, 30)): it[0x39] = count
    shops.join_items(game, c, 0)
    assert [it[0x39] for it in c.items] == [255, 35]
    c.items = [item(value=i) for i in range(1, 12)]
    for it in c.items: it[0x2E] = 0x27; it[0x3D] = 3
    shops.join_items(game, c, 0)
    grouped = list(shops.groups(c.items))
    assert len(grouped) == 2 and len(grouped[0][1]) == 11 and grouped[1][1][0][0x2E] == 0x27
    assert rec.rdw(c.items[0], 0x3A) == 55 and sum(rec.rdw(it, 0x3A) for it in c.items[1:]) == 66
    before = [bytes(it) for it in c.items]; shops.join_items(game, c, 0)
    assert [bytes(it) for it in c.items] == before


def check_slot_labels():
    """Row 38: ov18:0BBA..0CCF keeps all class labels/counts within the text-window borders."""
    game = fresh(lambda *a, **k: 0); setup(game); c = game.s.party[0]
    for cls in (0, 1, 3): c.b[0x132 + 7 * cls] = 2
    frame, calls, _ = drawn(game, 'SPELL', [3, 'done'], dict(purpose='memorize', caster=0))
    labels = [(x, y, text) for x, y, text in calls if 'Spells:' in text]
    assert len(labels) == 3 and (1, 20, 'Magic-User Spells:') in labels
    assert (1, 18, '    Cleric Spells:') in labels and (1, 19, '     Druid Spells:') in labels
    assert all(x >= 1 and x + len(text) <= 19 for x, _, text in labels)
    assert all((20, row, '2') in calls for row in range(18, 21))
    border = Frame(); screen.draw_frame(border, Assets(), 'full')
    assert all(frame.rows[y][:8] == border.rows[y][:8] and frame.rows[y][312:] == border.rows[y][312:]
               for y in range(136, 184))
    check_name_notices()


def check_name_notices():
    """GU-94: all screen kinds retain pixels outside the name window; only temple LIST loses its highlight."""
    from sm.titles.ssb.host import DECISION_KINDS
    game = fresh(lambda *a, **k: 0); setup(game); c = game.s.party[0]; game.s.g['67D6'] = 3
    assets = Assets()
    for kind in DECISION_KINDS:
        ui = SimpleNamespace(session=SimpleNamespace(game=game,decision=dict(kind=kind,info={})),selected=0,effect_scale=1)
        frame = Frame(); frame.rows = [bytearray([15])*320 for _ in range(200)]
        game.vm.service_names = []; shops.name_message(game,c,'has been selected',clear=False)
        screen.name_notice(ui,frame,assets,10); screen.name_notice(ui,frame,assets,100)
        assert all(row==bytearray([15])*320 for row in frame.rows[:136]+frame.rows[184:])
        assert any(v!=15 for row in frame.rows[136:184] for v in row)
    ui.session.decision = dict(ui.session.decision, info={'purpose': 'alter'})
    screen.name_notice(ui,frame,assets,101)
    assert game.vm.service_names, 'ov18:1BE1/212C changes menus without clearing the selected-member notice'
    ui.session.decision=dict(kind='LIST',info=dict(purpose='temple service')); frame.rows[32][16:18]=bytes((15,0))
    game.vm.service_names=[]; shops.name_message(game,c,'is healed'); shops.name_message(game,c,'regains sight')
    screen.name_notice(ui,frame,assets,200)
    assert frame.rows[32][16:18]==bytes((0,10)) and ui.name_notice_seen[2]=='is healed'
    screen.name_notice(ui,frame,assets,200.31); assert ui.name_notice_seen[2]=='regains sight'
    screen.name_notice(ui,frame,assets,200.62); assert not game.vm.service_names
    # A persistent warning survives a settled render, but the native clear after an answer removes it.
    shops.name_message(game,c,'will be gone',clear=False); screen.name_notice(ui,frame,assets,1e6)
    game.vm.clear_text(); before=[row[:] for row in frame.rows]; screen.name_notice(ui,frame,assets,1e6)
    assert frame.rows==before


if __name__ == '__main__':
    test()
    print('GU-76 prompt/service pixels: input, appraisal, training, visible results PASS')
