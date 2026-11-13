from unittest.mock import patch
from sm.titles import ssb

from sm.titles.ssb import rec
from sm.titles.ssb.host import Game
from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui.screen import layout
from sm.titles.ssb.units import camp, magic, shops
from sm.titles.ssb.units._combat_test import fixture as battle_fixture


class Fixture:
    profile = ssb
    def __init__(self, game, kind, options, **info):
        self.game, self.answers, self.result = game, [], None
        self.decision = dict(kind=kind, options=options, info=info, i=0, hash=game.s.hash(game.vm))

    def step(self, answer):
        self.answers.append(answer)


def drawing(controller, assets):
    calls, original = [], screen.Frame.text

    def text(frame, col, row, value, *args, **kwargs):
        calls.append((col, row, str(value)))
        return original(frame, col, row, value, *args, **kwargs)

    before = controller.session.game.s.hash(controller.session.game.vm)
    with patch.object(screen.Frame, 'text', text):
        frame = screen.render(controller, assets)
    assert before == controller.session.game.s.hash(controller.session.game.vm), 'render changed simulation'
    return frame, calls


def camp_screens(game, assets, screenshot):
    options = ['save', 'view', 'magic', 'rest', 'alter', 'fix', 'select', 'exit', 'char-up', 'char-down']
    controller = screen.Controller(Fixture(game, 'CAMP_MENU', options))
    frame, calls = drawing(controller, assets)
    assert [s for _, y, s in calls if y == 24 and len(s) > 1] == ['Save', 'View', 'Magic', 'Rest', 'Alter', 'Fix', 'Exit']
    assert not any(s.startswith('platinum') for _, _, s in calls)
    c = game.s.party[0]
    controller = screen.Controller(Fixture(game, 'CAMP_MENU', ['items', 'exit', 'spells'],
                                          purpose='view', record=bytes(c.b).hex()))
    frame, calls = drawing(controller, assets)
    for expected in ((1, 1, shops.name(c)), (20, 1, 'Status:'), (20, 3, 'Hit Points'),
                     (24, 6, 'Experience:'), (1, 9, 'STR'), (1, 14, 'CHA'), (1, 17, 'Armor Class'),
                     (1, 18, 'THAC0'), (20, 17, 'Encumbrance'), (1, 19, 'Damage')):
        assert expected in calls, expected
    assert all(r['rect'][1] == 192 for r in layout(controller)['regions'])
    if screenshot: frame.save(screen.LOCAL / 'q3_character.png')
    c.effects = [bytearray([1]) + bytearray(8)] * 20
    controller = screen.Controller(Fixture(game, 'CAMP_MENU', ['exit'], purpose='effects'))
    _, calls = drawing(controller, assets)
    assert (1, 5, shops.name(c)) in calls
    assert not controller.key('n', 'n') and controller.effects_start == 19
    assert not controller.session.answers
    _, calls = drawing(controller, assets)
    assert any('<No Magical Effects>' in text for _, _, text in calls)
    assert not controller.key('p','p') and controller.effects_start==0
    assert not controller.key('Down') and controller.effects_selected==2
    assert controller.key('e', 'e') and controller.session.answers == [0]
    c.effects.clear()
    c.b[0x132], c.b[0x1E], c.b[0x1F] = 3, 3, 0x83
    controller = screen.Controller(Fixture(game, 'SPELL', list(range(1, 25)) + ['done'], purpose='memorize', caster=0))
    frame, calls = drawing(controller, assets)
    assert (1, 1, shops.name(c) + "'s") in calls and (20, 18, '1') in calls
    assert any(text == 'Spells in Grimoire' for _, _, text in calls)
    assert not controller.key('Next') and controller.cast_start == 11
    regions = [r for r in layout(controller)['regions'] if 'select' in r]
    assert regions and all(40 <= r['rect'][1] <= 120 for r in regions)
    assert all(r['keys'][-1] == dict(keysym='m', char='m') for r in regions)
    if screenshot: frame.save(screen.LOCAL / 'q3_memorize.png')
    for options in (['yes', 'no'], ['keep', 'replace'], ['hot', 'cold']):
        controller = screen.Controller(Fixture(game, 'SPELL', options, prompt='memorize these spells?'))
        _, calls = drawing(controller, assets)
        assert screen.compact_menu(screen.menu_items(controller.session.decision, game), controller.session.decision)
        assert not any('Next Prev' in s for _, _, s in calls)
    controller = screen.Controller(Fixture(game, 'SPELL', [(0, 0x3C, 15), None], purpose='use scroll'))
    _, calls = drawing(controller, assets)
    assert (3, 6, magic.spell_name(15)) in calls
    controller = screen.Controller(Fixture(game, 'CAMP_MENU', ['faster', 'slower', 'exit'], purpose='speed', speed=5))
    _, calls = drawing(controller, assets)
    assert (1, 18, 'Game Speed = 5 (0=fastest 9=slowest)') in calls
    controller = screen.Controller(Fixture(game, 'SHOP_MENU', ['cancel', 'use'], purpose='use refusal', prompt='Use it? ', text='is a combat-only item...'))
    controller.inventory_background = screen.capture_background(controller)
    _, calls = drawing(controller, assets)
    assert (1, 19, 'That Item') in calls and (1, 20, 'is a combat-only item...') in calls and (0, 24, 'Use it? ') in calls
    assert screen.menu_items(controller.session.decision, game) == [(1, 'y', 'Yes'), (0, 'n', 'No')] and controller.selected == 0


def rest_screens(game, assets):
    for c in game.s.party: camp.clear_marks(c)
    game.s.r1[0x2D2] = 0
    actions = iter(['hours', 'add', 'minutes', 'add', 'rest', 'stop'])
    clocks = []

    def answer(kind, options, current, **info):
        if kind == 'INPUT': return int(info['remaining'] == 5)
        controller = screen.Controller(Fixture(current, kind, options, **info))
        _, calls = drawing(controller, assets)
        assert any(x == 1 and y == 17 and s.startswith('Rest Time: ') for x, y, s in calls)
        clocks.append(info.get('minutes', info.get('remaining')))
        if info['purpose'] == 'resting':
            assert screen.decision_labels(current, controller.session.decision) == ['No', 'Yes']
            assert (0, 24, 'Stop Resting? ') in calls and controller.selected == options.index('stop')
        return options.index(next(actions))

    game.player = answer
    assert not camp.rest_menu(game)
    assert clocks == [0, 0, 60, 60, 65, 5], clocks
    assert game.s.g['camp.remaining'] == 5 and not game.s.g['8DB4']
    c = game.s.party[0]; c.b[0x1E] = 0x83
    assert camp.rest_need(c) == 255
    camp.rest(game, 255)
    assert c.b[0x1E] == 3 and 'has memorized ' + magic.spell_name(3) in ''.join(game.vm.out)
    game.s.r1[0x2D2], game.s.r1[0x2D3] = 1, 100
    assert camp.rest(game, 5) and 'Your repose is suddenly interrupted!' in ''.join(game.vm.out)
    choices = iter(['slower', 'faster', 'exit'])
    game.s.g['67D6'] = 0
    game.player = lambda kind, options, current, **info: options.index(next(choices))
    camp.speed(game)
    assert game.s.g['67D6'] == 0


def combat_screens(assets, screenshot):
    game, battle = battle_fixture()
    game.combat = battle
    a, b = game.s.chars()
    a.b[:5], b.b[:5] = b'\x04HERO', b'\x04FOE!'
    game.vm.out.append('HERO Attacks FOE! Hitting for 4 points of damage')
    session = Fixture(game, 'COMBAT_ACTION', battle.legal_actions(a), actor=0)
    controller = screen.Controller(session)
    frame, calls = drawing(controller, assets)
    assert (23, 1, 'HERO') in calls and (23, 3, 'Hitpoints') in calls
    assert any(x == 23 and 10 <= y <= 21 and 'Hitting' in s for x, y, s in calls)
    assert not any(y == 24 and s in ('Guard', 'Flee') for _, y, s in calls)
    if screenshot: frame.save(screen.LOCAL / 'q3_combat.png')
    session = Fixture(game, 'TARGET', [1, 'cancel'], actor=0, action='attack')
    controller = screen.Controller(session)
    _, calls = drawing(controller, assets)
    assert (23, 1, 'HERO') in calls
    assert not controller.key('n', 'n')
    _, calls = drawing(controller, assets)
    assert (23, 1, 'FOE!') in calls and (14, 24, 'Manual') in calls
    selected = controller.selected
    assert not controller.key('c', 'c') and controller.selected == selected
    assert not controller.key('m', 'm')
    assert not controller.key('Left') and screen.cursor_choice(controller) is None
    assert not controller.key('t', 't') and not session.answers
    _, calls = drawing(controller, assets)
    assert not any(y == 24 and s == 'Target' for _, y, s in calls)
    assert not controller.key('Escape') and not screen.manual(controller) and not session.answers
    assert controller.key('Escape') and session.answers == [1]
    x, y = battle.position(a)
    session = Fixture(game, 'TARGET', [(x + 1, y), (x, y - 1), 'cancel'], actor=0, action='move')
    controller = screen.Controller(session)
    _, calls = drawing(controller, assets)
    assert any(y == 24 and s.startswith('Move/Attack, Move Left = ') for _, y, s in calls)
    assert (23, 1, 'HERO') in calls
    region = next(r for r in layout(controller)['regions'] if r.get('select') == 0)
    assert len(region['keys']) == 1
    assert controller.key('Up') and session.answers == [1]
    controller = screen.Controller(Fixture(game, 'MENU', ['yes', 'no'], prompt='Attack Ally:'))
    _, calls = drawing(controller, assets)
    assert (23, 10, 'Attack Ally:') in calls
    cells = [(x, y) for y in range(25) for x in range(50)]
    session = Fixture(game, 'TARGET', cells + ['cancel'], caster=0, spell=47)
    controller = screen.Controller(session); controller.selected = 510; controller.page = 51
    assert not controller.key('m', 'm')
    assert not controller.key('Right') and controller.selected == 511
    assert not controller.key('Down') and controller.selected == 561
    _, calls = drawing(controller, assets)
    assert (0, 24, '(Use Cursor keys)') in calls
    before = game.s.hash(game.vm)
    region = next(r for r in layout(controller)['regions'] if r.get('select') == 612)
    assert len(region['keys']) < 20
    for key in region['keys']: controller.key(**key)
    assert session.answers == [612] and game.s.hash(game.vm) == before
    session.decision = dict(session.decision)
    assert not screen.manual(controller), 'manual mode leaked into a later picker'
    controller = screen.Controller(Fixture(game, 'SPELL', [3, 15, 'cancel'], actor=0))
    _, calls = drawing(controller, assets)
    assert (1, 1, "HERO's") in calls and (8, 1, 'Spells in Memory') in calls
    assert next(r for r in layout(controller)['regions'] if 'select' in r)['rect'] == (8, 48, 304, 8)
    controller = screen.Controller(Fixture(game, 'MENU', ['continue', 'end'], action='continue-battle'))
    _, calls = drawing(controller, assets)
    assert (0, 24, 'Continue Battle:') in calls
    assert screen.decision_labels(game, controller.session.decision) == ['Yes', 'No']
    controller = screen.Controller(Fixture(game, 'NUMBER', None, prompt='Blast Delay in segments (1-50)?', min=0, max=50))
    controller.entry = '10'
    _, calls = drawing(controller, assets)
    assert any(y == 24 and 'segments (1-50)? 10' in s for _, y, s in calls)
    battle.record(a)[0] = 3; a.b[0x1E] = 3
    battle.apply_damage(a, 1)
    assert 'HERO lost a spell' in ''.join(game.vm.out) and a.b[0x1E] == 0
    magic._Magic(game).effect(a, 1, 10, save_type=1, saved=True)
    assert 'HERO is Unaffected' in ''.join(game.vm.out)
    def delay(kind, options, current, **info):
        assert kind == 'NUMBER' and options is None and info['max'] == 50
        return 10
    game.player = delay
    engine = magic._Magic(game)
    with patch.object(engine, 'make_area') as area:
        engine.dispatch(a, 115, [b])
        assert area.call_args.args == (a, 0x64, 1)


def view_actions(assets):
    game = Game(lambda *_args, **_info: 0, engines=True); game.s.mode = 2
    caster, patient = game.s.party[:2]
    caster.b[0x6C], caster.b[0x6D] = 3, 1
    patient.b[0x1B5] = patient.b[0x70] - 10
    patient.effects = [bytearray([0x22]) + bytearray(8)]
    shops.put_coins(caster, [0, 0, 0, 5, 0, 0, 0]); shops.put_coins(patient, [0] * 7)
    steps = iter([('CAMP_MENU', 'heal'), ('TARGET', 1),
                  ('CAMP_MENU', 'cure'), ('TARGET', 1),
                  ('CAMP_MENU', 'trade'), ('TARGET', 1), ('LIST', 3), ('NUMBER', 2),
                  ('LIST', None), ('CAMP_MENU', 'exit')])
    seen = set()

    def answer(kind, options, current, **info):
        expected, value = next(steps); assert kind == expected, (kind, expected)
        controller = screen.Controller(Fixture(current, kind, options, **info))
        _, calls = drawing(controller, assets)
        if kind == 'TARGET': assert screen.is_roster(controller.session.decision)
        if info.get('purpose') == 'view':
            if getattr(current.vm, 'service_bottom', None): seen.add(current.vm.service_bottom[2])
            labels = [label for _, _, label in screen.menu_items(controller.session.decision, current)]
            assert 'Trade' in labels and 'Drop' in labels
            assert 'char-up' not in options
            if value == 'cure': assert 'heal' not in options
            if value == 'exit': assert 'cure' not in options
        return value if options is None else options.index(value)

    game.player = answer
    shops.view(game, character=caster)
    assert patient.b[0x1B5] == patient.b[0x70] and not rec.has_effect(patient, 0x22)
    assert shops.coins(caster)[3] == 3 and shops.coins(patient)[3] == 2
    assert {shops.name(patient) + ' feels better', shops.name(patient) + ' is cured'} == seen
    assert rec.has_effect(caster, 0x6D) and rec.has_effect(caster, 0x6E) and caster.b[0x6D] == 0
    def cancel(kind, options, current, **info):
        assert kind == 'TARGET' and options[-1] is None and info['purpose'] == 'party member'
        return len(options) - 1
    game.player = cancel
    assert magic._Magic(game).pick(caster, 3, False) == []
    pool = tuple(game.s.treasure_money); moves = iter([3, 2, None])
    game.player = lambda kind, options, current, **info: (next(moves) if options is None else options.index(next(moves)))
    shops.coin_menu(game, caster, True)
    assert shops.coins(caster)[3] == 1 and tuple(game.s.treasure_money) == pool


def inventory_input():
    import tempfile
    from pathlib import Path
    from sm.titles.ssb import save
    from sm.engine import Session
    with tempfile.TemporaryDirectory(dir=screen.LOCAL, prefix='inventory-check-') as tmp:
        for name, data in save.dump(rec.max_party(write=False)).items():
            (Path(tmp) / name).write_bytes(data)
        ui = Session(slot='M', directory=tmp, engines=True)
        ref = Session(slot='M', directory=tmp, engines=True)
        try:
            controller = screen.Controller(ui, save_root=Path(tmp) / 'saves')
            from sm.titles.ssb.ui._test import townhall
            townhall(controller, ref)
            for key, value in (('v', 'view'), ('i', 'items')):
                controller.key(key, key); ref.step(ref.decision['options'].index(value))
            assert ui.decision == ref.decision and ui.decision['info']['purpose'] == 'items'
            before, count = ui.game.s.hash(ui.game.vm), len(ui.game.trace)
            region = next(r for r in layout(controller)['regions'] if r.get('select') == 1)
            assert region['rect'] == (16, 48, 288, 8)
            for key in region['keys']: controller.key(**key)
            assert controller.selected == 1 and len(ui.game.trace) == count and ui.game.s.hash(ui.game.vm) == before
            ready = next(r for r in layout(controller)['regions'] if r.get('key', {}).get('char') == 'r')
            controller.key(**ready['key']); ref.step(1); ref.step(ref.decision['options'].index('ready'))
            assert ui.decision == ref.decision and ui.game.trace == ref.game.trace
            assert ui.game.s.hash(ui.game.vm) == ref.game.s.hash(ref.game.vm)
            controller.key('Escape'); ref.step(len(ref.decision['options']) - 1)
            assert ui.decision == ref.decision and ui.decision['info']['purpose'] == 'view'
        finally:
            ui.close(); ref.close()


def empty_view():
    session=screen.Session(slot='B',engines=True)
    try:
        session.game.s.party[0].items=[]; controller=screen.Controller(session)
        controller.key('v','v'); decision=session.decision
        assert 'items' in decision['options'] and 'available' not in decision['info']
        assert 'Items' not in [label for _,_,label in screen.menu_items(decision,session.game)]
        assert 'Exit' in [label for _,_,label in screen.menu_items(decision,session.game)]
    finally:session.close()


def load_prompt(game,assets):
    session=Fixture(game,'CREATE_SLOT',['A','B','Z',None],purpose='load game')
    controller=screen.Controller(session)
    _,calls=drawing(controller,assets)
    assert (0,24,'Load Which Game: ') in calls and (17,24,'A') in calls and (19,24,'B') in calls
    assert not any(text=='Z' for _,_,text in calls)
    controller.key('Right'); assert controller.selected==1 and session.answers==[]
    controller.key('Right'); assert controller.selected==0 and session.answers==[]
    regions=layout(controller)['regions']
    assert any(r['rect']==(152,192,8,8) and r['key']['char']=='b' for r in regions)
    controller.key('Escape'); assert session.answers==[3]


def test(screenshot=False):
    game = Game(lambda *_args, **_info: 0, engines=True); game.s.mode = 2
    assets = screen.Assets()
    camp_screens(game, assets, screenshot)
    rest_screens(game, assets)
    combat_screens(assets, screenshot)
    view_actions(assets)
    inventory_input()
    empty_view()
    load_prompt(game,assets)
    print('camp/combat: sheet, effects, rest, spells, native bars, messages and target clicks: PASS')
