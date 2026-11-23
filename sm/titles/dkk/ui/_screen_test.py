from types import SimpleNamespace
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def frames(stop=None):
    from sm.engine import Session
    from sm.ui.png import encode
    from sm.titles.ssb.ui.screen import PALETTE
    from ..menu import Game
    from .._first_fight import OpeningChoices
    from . import screen
    out = os.environ.get('LOCAL_FRAMES')
    seen, kept, starts, fight, camp = [], {}, {}, None, None
    with TemporaryDirectory(prefix='sm-dkk-screen-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000)
        policy = OpeningChoices()
        try:
            controller = screen.Controller(session)
            controller.presentation_enabled = False
            while session.decision is not None and len(seen) < 2000:
                d = session.decision
                controller.report = []
                frame = screen.render(controller)
                pixels = b''.join(frame.rows)
                assert len(pixels) == 64000 and max(pixels) < 16, d['kind']
                tag = d['kind'] + ':' + str(d['info'].get('prompt'))
                seen.append(tag)
                if camp is None and d['kind'] == 'CAMP_MENU': camp = any(frame.rows[40][128:136]) and any(frame.rows[60][40:100])
                if screen.yes_no_menu(d): starts.setdefault(str(d['info'].get('prompt')), controller.selected)
                if fight is None and screen.fight_rows(d):
                    for key in ('Right', 'Right', 'Down'): controller.key(key)
                    fight = d['options'][controller.selected]
                    for key in ('space', 'Escape'): controller.key(key)
                    assert session.decision is d and d['options'][controller.selected] == fight
                    controller.key('Up'); controller.key('8', '8'); controller.key('h', 'h'); controller.key('p', 'p')
                    assert d['options'][controller.selected] == fight
                    controller.key('Left'); controller.key('6', '6')
                    assert d['options'][controller.selected] == fight
                    controller.selected = 0
                    from ..combat import Battle
                    data = Battle(game).data; r = data['actors'][data['actor']]; keep, (ox, oy) = dict(r), data['view']
                    j = next(n for n, o in enumerate(data['actors']) if n != data['actor'] and o['size'] and 0 <= o['x'] - ox < 7 and 0 <= o['y'] - oy < 7)
                    r.update(x=data['actors'][j]['x'], y=data['actors'][j]['y'], size=0); on = screen.render(controller).rows
                    r.update(x=-60, y=-60); off = screen.render(controller).rows; r.update(keep)
                    assert on == off
                if out and tag not in kept and d['kind'] in ('CAMP_MENU', 'COMBAT_ACTION', 'COMBAT_SPELL', 'TARGET', 'ACK', 'SPELL', 'CREATE_MENU'):
                    kept[tag] = len(seen)
                    rows = [[0xFF000000 | r << 16 | g << 8 | b for r, g, b in (PALETTE[p] for p in row)] for row in frame.rows]
                    Path(out).mkdir(parents=True, exist_ok=True)
                    (Path(out) / ('%04d_%s.png' % (len(seen), tag.replace(':', '_').replace(' ', '_')[:40]))).write_bytes(encode(rows))
                if stop and stop(d): break
                controller.choose(policy(d, game))
            assert session.error is None, session.error
        finally: session.close()
    return seen, starts, fight, camp


def creature_message():
    from . import screen
    import ast
    names = [n.name for n in ast.parse(Path(screen.__file__).read_text(encoding='utf-8')).body if isinstance(n, ast.FunctionDef)]
    assert len(names) == len(set(names)), sorted({n for n in names if names.count(n) > 1})
    assert screen.draw_creature_message.__code__.co_varnames[:3] == ('frame', 'controller', 'info')
    calls = []
    frame = SimpleNamespace(rect=lambda *a: calls.append(('rect',) + a), text=lambda col, row, text, assets, colour, width: calls.append((col, row, text, colour, width)))
    screen.draw_character_message(frame, None, dict(creature_name='TEST', creature_text='one two three four five six', creature_colour=11, creature_column=23, creature_row=10))
    assert calls == [('rect', 184, 80, 128, 96, 0), (23, 10, 'TEST', 11, 16), (23, 11, 'one two three', 10, 16), (23, 12, 'four five six', 10, 16)], calls
    calls.clear()
    screen.draw_character_message(frame, None, dict(creature_name='TEST', creature_text='word', creature_colour=12, creature_column=1, creature_row=19))
    assert calls == [('rect', 8, 144, 304, 40, 0), (1, 19, 'TEST', 12, 38), (1, 20, 'word', 10, 38)], calls


def aim_words():
    from . import screen
    picked = []
    options = ['TEST #4', 'Next', 'Prev', 'Manual', 'Target', 'Center', 'Exit', 'Ground', 'Escape']
    c = SimpleNamespace(session=SimpleNamespace(decision=dict(kind='TARGET', options=options, info=dict(selected=4))), horizontal_choice=3, choose=picked.append)
    c.aim_options = lambda: screen.aim_options(c)
    assert c.aim_options() == ['Next', 'Prev', 'Manual', 'Target', 'Center', 'Exit']
    for key, char in (('Return', ''), ('t', 't'), ('m', 'm'), ('Escape', ''), ('Right', ''), ('6', '6'), ('Return', ''), ('e', 'e'), ('x', 'x')): screen.aim_key(c, key, char)
    assert picked == [4, 4, 3, 8, 5, 6] and c.horizontal_choice == 5, (picked, c.horizontal_choice)
    options.remove('Target'); picked.clear()
    assert c.aim_options() == ['Next', 'Prev', 'Manual', 'Center', 'Exit']
    screen.aim_key(c, 't', 't'); screen.aim_key(c, 'c', 'c')
    assert picked == [4] and c.horizontal_choice == 3


def aim_panel():
    from . import screen
    seen = {(5, 5): True, (6, 5): True, (7, 5): False, (8, 5): True}
    tiles = {(8, 5): 31}
    battle = SimpleNamespace(walk=lambda x, y, tx, ty: (seen[(tx, ty)], (tx, ty), 0), position=lambda i: (4, 5), occupancy=lambda: {(6, 5): 2, (7, 5): 3},
                             tile=lambda x, y: tiles.get((x, y), 23), data=dict(downed=[(8, 5, 23), (8, 5, 24), (9, 9, 23)], downed_who=[4, 5, 6], downed_count=2))
    data = dict(actor=0)
    assert [screen.aim_marked(battle, data, c) for c in ((5, 5), (6, 5), (7, 5), (8, 5))] == [-1, 2, -1, 5]
    assert [screen.panel_of(dict(actor=1, **more)) for more in ({}, dict(panel=3), dict(panel=-1))] == [1, 3, 1] and 'panel_of' in screen._family_battle.__code__.co_names
    move = dict(kind='COMBAT_MOVE', options=['east', 'Done'], info={})
    assert screen.move_stepped(SimpleNamespace(stepped=True), move) and not screen.move_stepped(SimpleNamespace(), move)
    assert not screen.move_stepped(SimpleNamespace(stepped=True), dict(move, kind='COMBAT_ACTION')) and 'move_stepped' in screen._family_battle.__code__.co_names
    noted = SimpleNamespace(session=SimpleNamespace(decision=dict(move, info=dict(prompt='x')), game=SimpleNamespace(s=SimpleNamespace(g={}))), clock=lambda: 0.1, decided_at=0, effect_scale=1)
    assert screen.move_note(noted) and not screen.move_note(SimpleNamespace(session=SimpleNamespace(decision=move)))


def load_flush():
    from . import screen
    runtime, display = {}, dict(kind='PIC', id=9)
    ui = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(g={'dkk.runtime': runtime}), vm=SimpleNamespace(display=display))), typeahead=[('a', 'a')])
    screen.flush_on_load(ui); screen.flush_on_load(ui)
    assert ui.typeahead and screen.loaded_picture(ui) == ('PIC', 9)
    display['id'] = 10; screen.flush_on_load(ui)
    assert not ui.typeahead
    runtime['loads'] = 3; screen.flush_on_load(ui); ui.typeahead = [('a', 'a')]; screen.flush_on_load(ui)
    assert ui.typeahead
    runtime['loads'] = 4; screen.flush_on_load(ui)
    assert not ui.typeahead


def name_flash():
    from . import screen
    saved = screen.combat_view, screen.text_delay
    try:
        screen.combat_view, screen.text_delay = (lambda c: (10, 10)), (lambda c: 1)
        game = SimpleNamespace(s=SimpleNamespace(g={'dkk.battle': dict(actors=[None, None, None, dict(x=12, y=11)])}))
        assets = SimpleNamespace(combat_picture=lambda name, ident: [((6 if ident & 128 else 5, 0),)], view_tables={'icon_palette': None})
        ui, frame = SimpleNamespace(session=SimpleNamespace(game=game), assets=assets, effect_scale=1), screen.Frame()
        holds = screen.name_flash(ui, frame, 3)
        assert len(holds) == 8 and {h['delay'] for h in holds} == {0.07} and frame.rows[32][56] == 0
        assert [tuple(h['frame'].rows[32][56:58]) for h in holds] == [(5, 0), (0, 5), (0, 6), (6, 0)] * 2
        assets.combat_picture = lambda name, ident: [((ident, 0),)]
        holds = screen.name_flash(ui, frame, 3, 1)
        assert [tuple(h['frame'].rows[32][56:58]) for h in holds] == [(11, 0), (0, 11), (0, 139), (139, 0), (0, 0)] and holds[-1]['delay'] == 0.1
    finally: screen.combat_view, screen.text_delay = saved


def aging_page():
    from . import screen
    words = {'pressToContinue': 'press button or enter to continue', 'ageStrainMsg': 'the strain of the last battle has worn heavily on ', 'lastBreathMsg': ' breathes his last', 'continueBattle': 'continue battle?'}
    game = SimpleNamespace(assets=SimpleNamespace(text=words.get), battle=object())
    ack = lambda message, **more: dict(kind='ACK', options=['Continue'], info=dict(message=message, prompt=words['pressToContinue'], **more))
    page = ack(words['ageStrainMsg'] + 'SIR DRYDEN.  ')
    assert screen.aging_page(game, page) and screen.battle_over(game, page)
    assert not screen.aging_page(game, ack('won', experience=5)) and not screen.aging_page(SimpleNamespace(assets=game.assets, battle=None), page)
    drawn = []
    frame = SimpleNamespace(rect=lambda *a: drawn.append(a), text=lambda col, row, text, assets, colour, width=40: drawn.append((col, row, text.upper(), colour)))
    ui = SimpleNamespace(session=SimpleNamespace(game=game), assets=None)
    screen.draw_aging(frame, ui, page['info'])
    assert drawn == [(184, 112, 128, 64, 0), (0, 184, 320, 16, 0), (23, 14, 'THE STRAIN OF', 15), (23, 15, 'THE LAST BATTLE', 15), (23, 16, 'HAS WORN', 15),
                     (23, 17, 'HEAVILY ON SIR', 15), (23, 18, 'DRYDEN.', 15), (0, 24, 'PRESS BUTTON OR ENTER TO CONTINUE', 13)]
    drawn.clear(); screen.draw_aging(frame, ui, ack('nobody saw it')['info'])
    assert drawn[2] == (23, 14, 'NOBODY SAW IT', 14)


def fight_message():
    from . import screen
    from ..records import Character
    def member(text, side):
        b = bytearray(Character.SIZE); b[0] = len(text); b[1:1 + len(text)] = text.encode('cp437')
        for key, value in (('active', 1), ('side', side)): b[Character.FIELDS[key][0]] = value
        return SimpleNamespace(b=b, effects=[], items=[])
    drawn = []
    frame = SimpleNamespace(rect=lambda *a: drawn.append(('rect',) + a), text=lambda col, row, text, assets, colour, width=40: drawn.append((col, row, text, colour)))
    battle = SimpleNamespace(chars=[member('SIR', 0), member('SIR DRYDEN', 0), member('OGRE', 1)])
    assets = SimpleNamespace(text={'lostSpellMessage': 'lost a spell'}.get)
    screen.draw_fight_message(frame, assets, battle, 'SIR DRYDEN is unaffected')
    assert drawn == [('rect', 184, 80, 128, 96, 0), (23, 10, 'SIR DRYDEN', 11), (23, 11, 'is unaffected', 10)], drawn
    drawn.clear(); screen.draw_fight_message(frame, assets, battle, 'OGRE is held')
    assert drawn[1] == (23, 10, 'OGRE', 14), drawn
    drawn.clear(); screen.draw_fight_message(frame, assets, battle, 'OGRE lost a spell')
    assert drawn == [('rect', 184, 96, 128, 80, 0), (23, 12, 'OGRE', 14), (23, 13, 'lost a spell', 10)], drawn
    drawn.clear(); screen.draw_fight_message(frame, assets, battle, 'nobody here')
    assert drawn[1:] == [(23, 11, 'nobody here', 10)], drawn


def paging():
    from types import SimpleNamespace
    from . import screen
    c = SimpleNamespace(text_page=0, lines=['a']*13)
    assert screen.page_prompt(c) == ('press any key to continue', 13)
    c.lines[6] = '  KNIGHT is hit FOR 3 points of Damage.'
    assert screen.page_prompt(c, 0)[1] == 15 and screen.page_prompt(c, 1)[1] == 13


def pictures():
    from . import screen
    assets = screen.Assets()
    assert screen.picture_disk('PIC', 96, 2) == 5 and screen.picture_disk('BIGPIC', 112, 5) == 1 and screen.picture_disk('PIC', 6, 1) == 1
    for family, ident, disk in (('PIC', 60, 1), ('SPRIT', 64, 2), ('PIC', 83, 3), ('BIGPIC', 112, 5)):
        assert assets.picture(family, ident, disk).parts, (family, ident)
    ident = next(iter(assets.records('CPIC1')))
    assert assets.combat_picture('CPIC4', ident) == assets.combat_picture('CPIC1', ident)
    from types import SimpleNamespace as N
    calls, r0 = [], bytearray(0x200)
    r0[0xC3], r0[0xC4] = 10, 5
    game = N(vm=N(display=dict(kind='BIGPIC', id=112, dataset=5, map_cursor=True), is3d=lambda: False), s=N(mode=3, dataset=5, r0=r0))
    screen.draw_picture(N(blit=lambda x, y, px, **k: calls.append((x, y, len(px), k))), game, assets, 0)
    assert calls[-1] == (88, 48, 8, {}), calls[-1]
    flat = [px for part in assets.picture('PIC', 5, 2).parts for px in part.frames]
    for count, at in ((0, 0), (1, 0), (2, 1), (len(flat) + 1, 0)):
        for elapsed in (0, 7.3):
            calls.clear(); game.vm.display = dict(kind='PIC', id=5, dataset=2, frame=count)
            screen.draw_picture(N(blit=lambda x, y, px, **k: calls.append(px)), game, assets, elapsed)
            assert calls == [flat[at]], (count, elapsed)
    now, menu = [0.0], dict(kind='MENU', i=1, options=['a'], info=dict(animate=1))
    ui = N(session=N(decision=menu), clock=lambda: now[0], file_menu=False, text_page=0, lines=[])
    game.s.mode, game.s.g, game.vm.display = 4, {}, dict(kind='PIC', id=5, dataset=2, frame=0)
    def shown(at, drawn=True):
        calls = []
        now[0] = at
        screen.draw_picture(N(blit=lambda x, y, px, **k: calls.append(px)), game, assets, 0, ui, drawn)
        return flat.index(calls[0])
    assert [shown(t) for t in (0, 0.29, 0.3, 0.5, 0.7, 1.0)] == [0, 0, 1, 2, 3, 4]
    assert shown(1.5, False) == 4
    game.vm.display['frame'] = 1; assert shown(2.0, False) == 4
    game.vm.display['frame'] = 2; assert shown(2.1, False) == 5
    ui.session.decision = dict(menu, i=2); assert [shown(t) for t in (3.0, 3.29, 3.3)] == [0, 0, 1]
    game.vm.display = dict(kind='PIC', id=5, dataset=2, frame=0); ui.session.decision = None; assert shown(4.0) == 0
    game.s.mode, game.vm.display, ui.session.decision, game.s.g = 3, dict(kind='PIC', id=5, dataset=2, frame=0), dict(menu, i=3), {}; assert [shown(t) for t in (5.0, 5.3)] == [0, 1]
    for mode in (3, 4):
        game.s.mode, game.vm.display, game.s.g = mode, dict(kind='PIC', id=5, dataset=2, frame=0), {}
        for k, info in enumerate((dict(animate=0), dict(prompt='GIVE HIM THE SLEEPSTONE?'), dict(world_menu=True))):
            ui.session.decision, ui.picture_shown = dict(menu, i=10 + k, info=info), None; assert [shown(6.0 + k + t) for t in (0, 0.3, 0.7)] == [0, 0, 0], (mode, info)
    camp = assets.picture('PIC', 59, game.s.dataset).parts[0].frames[0]
    game.s.mode, game.vm.display, ui.session.decision, ui.picture_shown, calls = 2, dict(kind='PIC', id=93, dataset=1, frame=0), dict(kind='CAMP_MENU', i=30, options=['a'], info={}), None, []
    screen.draw_picture(N(blit=lambda x, y, px, **k: calls.append(px)), game, assets, 0, ui, True); assert calls == [camp]
    assert screen.menu_items(dict(kind='MENU', options=('Press button or enter to continue', 'char-up', 'menu-left', 'menu-right', 'escape', 'extended'), info={})) == [(0, 'Press button or enter to continue')]


def sheet_and_items():
    from sm.engine import Session
    from ..menu import Game
    from .._first_fight import OpeningChoices
    from . import screen
    lit = lambda frame, col, row: any(any(frame.rows[row * 8 + y][col * 8:col * 8 + 8]) for y in range(8))
    with TemporaryDirectory(prefix='sm-dkk-sheet-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000)
        policy = OpeningChoices()
        try:
            controller = screen.Controller(session)
            controller.presentation_enabled = False
            while session.decision and not (game.s.party and session.decision['kind'] == 'CAMP_MENU'): controller.choose(policy(session.decision, game))
            controller.choose(session.decision['options'].index('View'))
            assert session.decision['kind'] == 'CREATE_VIEW'
            info = screen.sheet_view(controller)[0]
            assert info['description'] and info['levels'] != '0' and info['race'] and info['experience'] > 0, info
            frame = screen.render(controller)
            assert all(lit(frame, col, row) for col, row in ((1, 1), (20, 1), (1, 3), (1, 5), (1, 7), (1, 9), (20, 9), (1, 17), (1, 21)))
            controller.choose(session.decision['options'].index('Items'))
            assert screen.items_list(session.decision)
            frame = screen.render(controller)
            assert lit(frame, 1, 1) and lit(frame, 1, 3) and lit(frame, 2, 5) and lit(frame, 5, 2)
            words = screen.item_menu(controller)
            assert words[0] == 'Ready' and words[-1] == 'Exit'
            controller.key('Left', ''); assert controller.item_word == len(words) - 1
            controller.key('Right', ''); assert controller.item_word == 0
            controller.key('Right', ''); controller.key('Escape', ''); assert session.decision['kind'] == 'CREATE_VIEW' and controller.item_word == 1
            controller.choose(session.decision['options'].index('Items')); assert controller.item_word == 0
            controller.choose(0)
            assert screen.item_words(session.decision)
            frame = screen.render(controller)
            assert lit(frame, 2, 5) and lit(frame, 5, 2) and lit(frame, 0, 24) and not lit(frame, 20, 10)
            from ..camp import F
            caster = next(n for n, m in enumerate(game.s.party) if len(m.b) > 300)
            game.s.party[caster].b[F['memorized']:F['memorized'] + 2] = bytes((1, 3))
            game.s.sel = caster
            while session.decision['kind'] != 'CAMP_MENU': controller.choose(session.decision['options'].index('Exit'))
            controller.choose(session.decision['options'].index('View'))
            controller.choose(session.decision['options'].index('Spells'))
            assert screen.listed(session.decision)
            nodes = screen.vertical(controller)['nodes']
            assert nodes[0][0] is None and [index for index, _ in nodes[1:]] == [-1, 0], nodes
            frame = screen.render(controller)
            assert lit(frame, 1, 5) and lit(frame, 3, 7) and lit(frame, 0, 24) and lit(frame, 3, 24) and not lit(frame, 4, 24)
        finally: session.close()


def rest_hold_drawn():
    from . import screen
    seen = []
    frame = screen.Frame(); frame.rect(0, 0, 320, 200, 9)
    frame.text = lambda col, row, value, assets, colour=15, *a, **k: seen.append((col, row, value, colour))
    info = dict(prompt='healed', row=19, column=1, colour=10, rest=True, timed=1, days=0, hours=2, minutes=25)
    assert screen.rest_hold(dict(kind='ACK', info=info)) and not screen.rest_hold(dict(kind='ACK', info=dict(info, timed=0)))
    screen.draw_rest_hold(frame, None, info)
    assert (1, 19, 'healed', 10) in seen and (1, 17, 'Rest Time:', 10) in seen and (18, 17, '25', 10) in seen, seen
    assert frame.rows[192] == bytearray(320) and frame.rows[150][8:312] == bytearray(304) and frame.rows[150][0] == 9


def number_backspace():
    from types import SimpleNamespace
    from . import screen
    d = dict(kind='NUMBER', options=None, info=dict(max=12), i=7)
    ui, shown = SimpleNamespace(entry='', file_menu=None), []
    for key in '19bb5':
        keysym, char = ('BackSpace', '') if key == 'b' else (key, key)
        screen.number_cells(ui, d, keysym, char)
        ui.entry = ui.entry[:-1] if keysym == 'BackSpace' else str(min(int((ui.entry + char)[:6]), 12))
        shown.append(screen.entry_text(ui, d))
    assert shown == ['1', '12', '12', '1', '5'] and ui.entry == '5', shown


def timed_pause():
    from types import SimpleNamespace
    from . import screen
    pending = [dict(kind='ACK', options=('Continue',), info=dict(timed=1)), dict(kind='ACK', options=('Continue',), info=dict(timed=2)),
               dict(kind='ACK', options=('Continue',), info={}), None]
    answered = []
    session = SimpleNamespace(decision=pending.pop(0), error=None)
    def step(self, index):
        answered.append(index); session.decision = pending.pop(0); self.report = ['after']
    family, screen._family_choose = screen._family_choose, step
    try:
        ui = SimpleNamespace(session=session, presentation_enabled=False, report=['before'], queue=lambda: ())
        screen.pass_timed(ui)
    finally: screen._family_choose = family
    assert answered == [0, 0] and session.decision['info'] == {} and ui.report == ['before', 'after', 'after'], (answered, ui.report)
    from collections import deque
    from sm.titles.cok.ui.screen import Frame
    pending[:] = [dict(kind='ACK', options=('Continue',), info=dict(timed=1, blank_bottom_pause=True, flush_keys=True)), dict(kind='ACK', options=('Continue',), info={}), None]
    session.decision, drawn, queue = dict(kind='ACK', options=('Continue',), info=dict(timed=1)), [], deque()
    def paint(_):
        frame = Frame(); frame.rect(0, 0, 320, 200, 7 + len(drawn)); drawn.append(frame); return frame
    def chosen(self, index):
        queue.clear(); step(self, index)
    family, render, screen._family_choose, screen.render = screen._family_choose, screen.render, chosen, paint
    family_choose = family
    try:
        ui = SimpleNamespace(session=session, presentation_enabled=True, report=[], queue=lambda: queue, effect_scale=1, typeahead=[('a', 'a')])
        family_pause, screen.pause = screen.pause, lambda _: 0.5
        try: screen.pass_timed(ui)
        finally: screen.pause = family_pause
    finally: screen._family_choose, screen.render = family, render
    shown = [e['frame'] for e in queue]
    assert [e['delay'] for e in queue] == [0.5, 0.5, 0.5] and shown[:2] == drawn and ui.typeahead == [('a', 'a')], queue
    assert [bool(e.get('flush_keys')) for e in queue] == [False, False, True], queue
    family = screen._family_held
    ui = SimpleNamespace(hold_event=queue[1], typeahead=[('b', 'b')], session=SimpleNamespace(decision=None), queue=lambda: ())
    screen._family_held = lambda self: setattr(self, 'hold_event', queue[2]) or queue[2]
    try:
        screen._held(ui); assert ui.typeahead == [('b', 'b')], ui.typeahead
        screen._family_held = lambda self: setattr(self, 'hold_event', None)
        screen._held(ui); assert ui.typeahead == [], ui.typeahead
    finally: screen._family_held = family
    assert shown[2].rows[192] == bytearray(320) and shown[2].rows[191] == drawn[1].rows[191] and drawn[1].rows[192] != bytearray(320)
    pending[:], drawn[:] = [None], []
    queue.clear()
    session.decision = dict(kind='ACK', options=('Continue',), info=dict(timed=1, creature_name='A'))
    ui = SimpleNamespace(session=session, presentation_enabled=True, report=[], queue=lambda: queue, effect_scale=1, typeahead=[], selected=0, answered_index=1)
    screen._family_choose, screen.render, screen.pause = chosen, paint, lambda _: 0.5
    try: screen.pass_timed(ui, dict(kind='CAMP_MENU', options=('Cast', 'Exit'), info={}))
    finally: screen._family_choose, screen.render, screen.pause = family_choose, render, family_pause
    held = queue[0]['frame']
    assert len(drawn) == 2 and held.rows[0][0] == 7 and held.rows[192] == bytearray([8]) * 320 and held.rows[199][319] == 8, len(drawn)
    pending[:], drawn[:] = [dict(kind='ACK', options=('Continue',), info=dict(timed=1, prompt='NO', message_colour=10)), None], []
    queue.clear()
    session.decision = dict(kind='ACK', options=('Continue',), info=dict(timed=1, creature_name='A', clear_bottom=True))
    screen._family_choose, screen.render, screen.pause = chosen, paint, lambda _: 0.5
    try: screen.pass_timed(ui, dict(kind='CAMP_MENU', options=('Cast', 'Exit'), info={}))
    finally: screen._family_choose, screen.render, screen.pause = family_choose, render, family_pause
    first, second = queue[0]['frame'], queue[1]['frame']
    assert first.rows[192] == bytearray(320) and first.rows[0][0] == 7 and second.rows[0][0] == 7 and second.rows[192][0] == 8, len(drawn)


def highlight_kept():
    from types import SimpleNamespace
    from . import screen
    d = dict(kind='MENU', options=('Buy', 'View', 'Pool', 'Appraise', 'Exit', 'char-up', 'char-down'), info=dict(prompt='', start=0))
    ui = SimpleNamespace(session=SimpleNamespace(decision=d, game=SimpleNamespace()), selected=1)
    for index, escaping, kept in ((2, False, 2), (5, False, 1), (4, True, 1), (4, False, 4)):
        ui.escaping = escaping; screen.keep_highlight(ui, index)
        assert ui.session.game.menu_highlight == kept, (index, escaping, ui.session.game.menu_highlight)


def list_top():
    from types import SimpleNamespace as N
    from . import screen
    d = dict(kind='LIST', options=tuple('item%d' % n for n in range(12)) + (None,), info=dict(prompt='q', window='1 17 38 22'))
    ui = N(session=N(decision=d, game=N(s=N(g={}))), selected=3, spell_top=0)
    assert screen.list_entry_top(ui) == 1
    ui.list_top = 5; assert screen.list_entry_top(ui) == 3
    ui.selected = 8; assert screen.list_entry_top(ui) == 5
    ui.session.game.s.g['dkk.item_pool'] = bytes(9); assert screen.list_entry_top(ui) == 1
    ui.list_top = 5
    d['info']['entry'] = 0; assert screen.list_entry_top(ui) == 0
    del d['info']['entry']
    d['options'] = ('a', 'b', None); ui.selected = 1; assert screen.list_entry_top(ui) == 0


def camp_message():
    from types import SimpleNamespace as N
    from . import screen
    vm = N(text_epoch=56)
    ui = N(lines=['Camp', 'x'], line_colours=[10, 10], text_page=0, session=N(game=N(vm=vm)))
    walk = [(dict(kind='CAMP_MENU', info=dict(camp_main=True, preserve_message=True, message='m')), ['', 'm']),
            (dict(kind='ALTER', info=dict(preserve_message=True)), ['', 'm']),
            (dict(kind='CREATE_SLOT', info=dict(preserve_message=True, prompt='save which game: ')), ['', 'm']),
            (dict(kind='CAMP_REST', info=dict(prompt='Rest Time')), ['Rest Time']),
            (dict(kind='CAMP_MENU', info=dict(camp_main=True, preserve_message=True, message='')), [])]
    for d, lines in walk:
        if d['kind'] == 'CAMP_REST': ui.lines = ['Rest Time']
        screen.keep_message(ui, d)
        assert ui.lines == lines and not ui.camp_intro if d['info'].get('preserve_message') else ui.lines == lines, (d, ui.lines)
    screen.keep_message(ui, walk[0][0]); screen.keep_message(ui, walk[1][0])
    vm.text_epoch = 58; screen.keep_message(ui, walk[1][0])
    assert ui.lines == [], ui.lines
    rest = dict(kind='CAMP_REST', options=('Rest', 'Days', 'Hours', 'Mins', 'Add', 'Subtract', 'Exit'), info={})
    assert [screen.next_word(rest, 3, True), screen.next_word(rest, 0, False), screen.next_word(rest, 6, True)] == [4, 6, 0]
    slot = dict(kind='CREATE_SLOT', options=tuple('ABCDEFGHIJ') + ('Exit',), info=dict(prompt='save which game: '))
    assert [label for _, label in screen.menu_items(slot)] == list('ABCDEFGHIJ')
    land, cave = dict(info=dict(overland=True)), dict(info=dict(overland=False))
    assert screen.steps_on(land, '5', '5') and screen.steps_on(land, 'backslash', chr(92)) and screen.steps_on(land, 'F1', '')
    assert not screen.steps_on(land, 'Up', '') and not screen.steps_on(land, '7', '7') and not screen.steps_on(cave, '5', '5')
    level = dict(kind='ALTER_LEVEL', options=('Novice', 'Squire', 'Veteran', 'Adept', 'Champion', 'char-up', 'char-down', 'Exit'), info={})
    assert [label for _, label in screen.menu_items(level)] == ['Novice', 'Squire', 'Veteran', 'Adept', 'Champion']
    refused = dict(kind='ACK', options=('Continue',), info=dict(prompt='x', timed=1, message_colour=14))
    assert screen.own_window(refused) and not screen.own_window(dict(refused, info=dict(prompt='x')))
    assert 'aim: ' in screen._family_battle.__code__.co_consts and 'Aim:' not in screen._family_battle.__code__.co_consts
    assert 'draw_panel' in screen._family_battle.__code__.co_names
    from ..combat import I
    def named(text): return bytes(I['name']) + bytes((len(text),)) + text.encode() + bytes(64)
    shown = dict(hp=1, hp_max=5, ac=50, active=1, side=0, level_up_ready=0, status=0, helpless=False, casting=0, weapon=None)
    texts = dict(helplessText='(helpless)', castingText='(casting)').get
    assert screen.panel_rows(shown, texts) == ([], 7, '')
    assert screen.panel_rows(dict(shown, weapon=named('long sword '), casting=1), texts) == (['long sword '], 9, '(casting)')
    assert screen.panel_rows(dict(shown, weapon=named('two-handed sword '), helpless=True, casting=1), texts) == (['two-handed ', 'sword '], 10, '(helpless)')
    assert screen.panel_rows(dict(shown, weapon=named('long sword +2 x '), active=0, status=6, helpless=True), texts) == (['long sword +2 x '], 10, 'Dead')
    fight = SimpleNamespace(chars=[SimpleNamespace(b=bytearray(400))] * 4, weapon=lambda i: None, disabled=lambda i: False, record=lambda i: dict(casting=0))
    assert screen.panel_print(fight, dict(panel=2, panel_print=shown), 2, False) is shown
    texts = dict(scribeConfirmPrompt='s? ', useItemPrompt='u? ', loseQuery='l? ', itemLabel='that', combatOnlyItemText='only', cantCastHereText='cant')
    def asked(kind, **info): return SimpleNamespace(session=SimpleNamespace(decision=dict(kind=kind, info=info), game=SimpleNamespace(assets=SimpleNamespace(text=texts.get), s=SimpleNamespace(g={}))))
    items, spells, cast = dict(screen.ITEMS_SHOWN), dict(screen.SCRIBE_SHOWN), dict(screen.CAST_SHOWN)
    try:
        screen.ITEMS_SHOWN.clear(); screen.SCRIBE_SHOWN.clear(); screen.CAST_SHOWN.clear()
        assert screen.shown_under(asked('ACK', item='x')) is None and screen.shown_under(asked('CAMP_CONFIRM', prompt='u? ', spell='a')) is None
        screen.ITEMS_SHOWN.update(decision=1); screen.SCRIBE_SHOWN.update(decision=2)
        assert screen.shown_under(asked('ACK', item='x')) == (1, None, True) and screen.shown_under(asked('ACK', prompt='x')) is None
        assert screen.shown_under(asked('CAMP_CONFIRM', prompt='u? ', spell='a')) == (1, ('that', 'only'), True) and screen.shown_under(asked('CAMP_CONFIRM', prompt='u? ')) is None
        assert screen.shown_under(asked('CAMP_CONFIRM', prompt='l? ', spell='a')) is None and screen.shown_under(asked('CAMP_CONFIRM', prompt='s? ')) == (2, (), False)
        screen.CAST_SHOWN.update(decision=3)
        assert screen.shown_under(asked('CAMP_CONFIRM', prompt='l? ', spell='a')) == (3, ('a', 'cant'), False) and screen.shown_under(asked('CAMP_CONFIRM', prompt='u? ', spell='a')) == (3, ('that', 'only'), False)
        screen.CAST_SHOWN.clear()
        fighting = asked('ACK', item='x'); fighting.session.game.s.g['dkk.battle'] = dict(active=True)
        assert screen.shown_under(fighting) is None
    finally: screen.ITEMS_SHOWN.clear(); screen.ITEMS_SHOWN.update(items); screen.SCRIBE_SHOWN.clear(); screen.SCRIBE_SHOWN.update(spells); screen.CAST_SHOWN.clear(); screen.CAST_SHOWN.update(cast)
    assert 'draw_fight_message' in screen._family_battle.__code__.co_names
    assert 'answered_screen' in screen.pass_timed.__code__.co_names and 'compact' in screen.answered_screen.__code__.co_names
    assert [screen.panel_print(fight, data, i, aimed)['hp'] for data, i, aimed in ((dict(panel=2, panel_print=shown), 2, True), (dict(panel=2, panel_print=shown), 3, False), (dict(panel=2), 2, False))] == [0, 0, 0]
    printed = SimpleNamespace(s=SimpleNamespace(chars=lambda: []), vm=SimpleNamespace(out=['A.', chr(10), chr(10), chr(10), 'B?'], text_start=0, text_color=10))
    assert screen.script_text(printed)[0] == ['A.', '', '', 'B?']
    heal = dict(kind='VIEW_WHO', options=('A', 'B', 'Exit'), info=dict(prompt='Heal whom? '))
    assert screen.member_who(heal) and screen.pick_who(heal) and screen.member_who(dict(heal, info=dict(prompt='trade to?', start=1)))
    assert not screen.member_who(dict(heal, options=('A', 'B')))


def modify_keys():
    from .screen import modify_key
    assert [modify_key(k, c) for k, c in (('Up', ''), ('Return', chr(13)), ('a', 'a'), ('F1', ''), ('BackSpace', chr(8)), ('Delete', ''))] == ['#72', chr(13), 'a', None, chr(8), '#83']


def modify_drawing():
    from sm.titles.ssb.ui.screen import Frame
    from . import screen
    assets, colours = screen.Assets(), lambda frame, col, row: {c for y in range(8) for c in frame.rows[row * 8 + y][col * 8:col * 8 + 8]} - {0}
    info = dict(name='AB D', field=6, cursor=3, query='Modify : ', menu='Add Subtract Keep Exit', choice=1, dirty='0 6 7')
    frame = Frame(); screen.draw_modify(frame, assets, info)
    assert colours(frame, 1, 1) == {13} and colours(frame, 3, 1) == {15} and colours(frame, 0, 24) == {13}
    assert colours(frame, 13, 24) == {15} and colours(frame, 10, 24) == {10}
    frame = Frame(); screen.draw_modify(frame, assets, dict(info, field=0, choice=0))
    assert colours(frame, 1, 1) == {10} and colours(frame, 10, 24) == {15}
    frame = Frame(); screen.draw_modify(frame, assets, dict(info, field=0, dirty='0 7'), True)
    assert colours(frame, 1, 1) == {10}


def title_flow():
    from . import start_session, screen, title
    session = start_session(saves=None, title=True)
    try:
        ui, now = screen.Controller(session, presentation=False), [0.0]
        ui.clock = lambda: now[0]
        seen = []
        from itertools import accumulate
        for at in [0] + [t + 0.1 for t in accumulate(title.HOLDS)]:
            now[0] = at; frame = screen.render(ui); seen.append(session.game.title)
        assert seen == [1, 2, 3, 4, 5] and any(frame.rows[8][16:300]), seen
        ui.key('Return', ''); assert session.game.title == title.PLAY and screen.layout(ui)['revision'][0] == 'title'
        ui.key('x', 'x'); assert session.game.title == title.PLAY
        ui.key('p', 'p'); assert session.game.title is None and session.decision['kind'] == 'CREATE_MENU'
        assert len(title.credits(str(ui.assets.root))) == 20
    finally: session.close()
    for keys, wait in (((('d', 'd'),), 0), ((), title.DEMO_WAIT)):
        ui, now = screen.Controller(start_session(saves=None, title=True), presentation=False), [0.0]
        ui.clock = lambda: now[0]
        try:
            ui.key('Return', ''); ui.key('Return', '')
            for key in keys: ui.key(*key)
            now[0] = wait - 0.1; screen.layout(ui); assert title.demo_on(ui.session.game) == (not wait)
            now[0] = wait; screen.layout(ui); game = ui.session.game
            assert title.demo_on(game) and game.title is None and game.s.g['dkk.delay'] == 9 and (ui.session.decision or {}).get('kind') in (None, 'COMBAT_AUTO')
            assert ui.key('Return', '') is False and title.demo_on(ui.session.game)
            if (ui.session.decision or {}).get('kind') == 'COMBAT_AUTO':
                d = ui.session.decision; ui.key('2', '2'); assert ui.session.decision is not d
            while ui.session.decision is not None: assert ui.session.decision['kind'] == 'COMBAT_AUTO'; ui.choose(0)
            assert ui.session.result == 'DEMO'
            now[0] += 1e6; screen.layout(ui); game = ui.session.game
            assert not title.demo_on(game) and game.title == 1 and ui.title_wait == title.AGAIN_WAIT and game.s.g.get('dkk.delay', 4) == 4
            ui.key('Return', ''); ui.key('Return', ''); assert game.title == title.PLAY
            now[0] += title.AGAIN_WAIT + 0.01; screen.layout(ui); assert title.demo_on(ui.session.game)
        finally: ui.session.close()
    ui = screen.Controller(start_session(saves=None, title=True), presentation=False); ui.clock = lambda: 1.0
    try:
        ui.key('Return', ''); ui.key('Return', ''); ui.key('Right', ''); assert ui.title_choice == 1 and ui.session.game.title == title.PLAY
        ui.key('Left', ''); ui.key('6', '6'); ui.key('4', '4'); ui.key('Left', ''); assert ui.title_choice == 1
        ui.key('Right', ''); ui.key('Return', ''); assert ui.session.game.title is None and not title.demo_on(ui.session.game)
    finally: ui.session.close()
    for key in ('Escape', 'Up', 'F1', 'Alt-x'):
        ui = screen.Controller(start_session(saves=None, title=True), presentation=False); ui.clock = lambda: 1.0
        try:
            ui.key('Return', ''); ui.key('Return', ''); ui.key(key, '')
            assert ui.session.game.title is None and not title.demo_on(ui.session.game), key
        finally: ui.session.close()
    session = start_session(saves=None, title=True)
    try:
        ui = screen.Controller(session, presentation=False); ui.clock = lambda: 1.0
        ui.key('Return', ''); assert session.game.title == title.CREDITS
        now = [1.0]; ui.clock = lambda: now[0]
        now[0] += title.CREDIT_HOLD - 0.1; title.tick(ui); assert session.game.title == title.CREDITS
        now[0] += 0.2; title.tick(ui); assert session.game.title == title.PLAY
    finally: session.close()
    session = start_session(saves=None, title=False, demo=True)
    try:
        ui = screen.Controller(session, presentation=False); game = session.game
        names = [c.b[1:1 + c.b[0]] for c in game.s.party]
        ui.capture_text(); game.s.party.clear(); game.s.monsters.clear()
        canvas = screen.Frame(); screen.draw_party(canvas, game, ui.assets)
        kept = [bytes(r) for r in canvas.rows[32:40]]
        del game.demo_shown; canvas = screen.Frame(); screen.draw_party(canvas, game, ui.assets)
        assert names and kept != [bytes(r) for r in canvas.rows[32:40]]
    finally: session.close()


def typeahead():
    from . import start_session, screen
    session = start_session(saves=None, title=False)
    try:
        ui, now = screen.Controller(session, presentation=False), [0.0]
        ui.clock = lambda: now[0]
        ui.hold_event, ui.hold_until = {'kind': 'script-hold', 'delay': 0.6}, 0.6
        ui.key('Return', chr(13)); ui.key('Return', chr(13)); assert session.decision['kind'] == 'CREATE_MENU' and len(ui.typeahead) == 2
        now[0] = 1.0; assert ui.held() is None and ui.typeahead == [] and session.decision['kind'] == 'CREATE_RACE'
        real, pages = ui.session, [dict(kind='MENU', options=['c'], info=dict(purpose='script damage', color=c)) for c in (15, 13)]
        for colour, kept in ((15, 1), (13, 0)):
            fake = __import__('types').SimpleNamespace(game=real.game, decision=dict(pages[0 if colour == 15 else 1]))
            ui.session, ui.typeahead = fake, [('a', 'a'), ('b', 'b')]
            ui.key = lambda keysym, char, fake=fake: setattr(fake, 'decision', None)
            ui.held(); assert len(ui.typeahead) == kept, (colour, ui.typeahead)
        vm = __import__('types').SimpleNamespace(display=dict(kind='PIC', id=3))
        fake = __import__('types').SimpleNamespace(game=__import__('types').SimpleNamespace(vm=vm), decision=None)
        ui.session, ui.typeahead = fake, []; ui.held(); ui.typeahead = [('a', 'a')]
        vm.display['frame'] = 2; ui.held(); assert ui.typeahead == [('a', 'a')]
        vm.display['kind'] = None; ui.held(); assert ui.typeahead == [('a', 'a')]
        vm.display.update(kind='PIC', id=3); ui.held(); assert ui.typeahead == []
        ui.typeahead = [('a', 'a')]; vm.display.update(kind='BIGPIC', id=112); ui.held(); assert ui.typeahead == [('a', 'a')]
        vm.display.update(kind='PIC', id=3); ui.held(); assert ui.typeahead == []
        ui.session = real; del ui.key
    finally: session.close()


def escape_and_source():
    from . import start_session, screen
    lit = lambda frame, col, row: any(any(frame.rows[row * 8 + y][col * 8:col * 8 + 8]) for y in range(8))
    session = start_session(saves=None, title=False)
    try:
        ui = screen.Controller(session, presentation=False)
        ui.key('Return', chr(13)); assert session.decision['kind'] == 'CREATE_RACE'
        ui.key('Escape', chr(27)); assert session.decision['kind'] == 'CREATE_MENU', session.decision['kind']
        ui.key('Down', ''); ui.key('Return', chr(13)); ui.capture_text()
        assert session.decision['info'].get('source')
        frame = screen.render(ui)
        assert not lit(frame, 34, 2) and not lit(frame, 2, 2) and lit(frame, 0, 24)
    finally: session.close()


def overland_view():
    from .screen import shown_display
    r0 = bytearray(0x200); r0[0x1F7] = 1
    view = dict(kind=None, sky=[11, 12])
    game = SimpleNamespace(s=SimpleNamespace(r0=r0, mode=3, dataset=1), vm=SimpleNamespace(display=view, is3d=lambda: False))
    assert shown_display(game)['kind'] == 'BIGPIC' and shown_display(game)['id'] == 112
    r0[0x1F7] = 0; assert shown_display(game) is view
    r0[0x1F7] = 1; game.vm.is3d = lambda: True; assert shown_display(game) is view


def order_window():
    from types import SimpleNamespace
    from ..creation import F
    from .screen import order_message, bottom_query
    b = bytearray(max(F.values()) + 1); b[F['active']] = 1
    c = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(selc=lambda: SimpleNamespace(b=b)))), painted=(['', 'camp'], [10, 10]))
    order_message(c, {'member': 'AB', 'message': ''})
    assert c.lines == ['', 'camp'] and not c.order_placing
    order_message(c, {'member': 'AB', 'message': 'AB has been selected', 'placing': True})
    assert c.lines == ['', 'AB', 'has been selected'] and c.line_colours == [10, 11, 10]
    order_message(c, {'member': 'AB', 'message': ''})
    assert c.lines == [] and not c.order_placing
    c.session.decision = dict(kind='ALTER_ORDER', info={'prompt': 'party order '})
    assert bottom_query(c) == 'party order '
    from .screen import keep_message
    c.painted, c.file_menu = (['', 'the party makes camp'], [10, 10]), False
    keep_message(c, dict(kind='ALTER_SPEED', info={'prompt': 'game speed: ', 'message': 'Game Speed (0=fastest 9=slowest) = 4'}))
    assert c.lines == ['', 'Game Speed (0=fastest 9=slowest) = 4'] and bottom_query(SimpleNamespace(session=SimpleNamespace(decision=dict(kind='ALTER_SPEED', info={'prompt': 'game speed: '})))) == 'game speed: '
    keep_message(c, dict(kind='ALTER', info={'preserve_message': True}))
    assert c.lines == []


def duplicate_view():
    from .screen import viewed
    a, b = (SimpleNamespace(b=bytes((5,)) + b'HERO0') for _ in range(2))
    game = SimpleNamespace(trade_character=b, s=SimpleNamespace(party=[a, b], selc=lambda: a))
    assert viewed(game, 'HERO0') is b and viewed(SimpleNamespace(s=game.s), 'HERO0') is a
    assert viewed(SimpleNamespace(trade_character=a, s=game.s), 'HERO0', 1) is b and viewed(game, 'HERO0', 9) is b


def roster_file_name():
    from . import screen
    from .. import creation
    d = dict(kind='CREATE_FILE_NAME', info=dict(prompt='new file name : '), options=None)
    ui = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(mode=0, g={})), decision=d))
    assert screen.file_name(ui) and screen.menu_screen(ui) and screen.roster_question(ui, d) and not screen.roster_question(ui, dict(d, kind='CREATE_MENU'))
    ui.session.game.s.g[creation.PENDING] = None
    assert not screen.file_name(ui) and not screen.roster_question(ui, d)


def control_keys():
    from .screen import control_key
    runtime = dict(music_on=1, trace=0)
    ui = SimpleNamespace(sound_on=True, session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(g={'dkk.runtime': runtime}))))
    assert control_key(ui, chr(19)) and not ui.sound_on and control_key(ui, chr(19)) and ui.sound_on
    assert control_key(ui, chr(21)) and runtime['music_on'] == 0 and control_key(ui, chr(4)) and runtime['trace'] == 1
    assert control_key(ui, chr(26)) and not control_key(ui, 'a') and not control_key(ui, chr(3))
    ui.sound_on = False; runtime['sound_saved'] = 0; control_key(ui, chr(19))
    assert not ui.sound_on
    from .screen import one_key_pause
    pause = dict(kind='ACK', options=('Continue',), info=dict(prompt='error', message_colour=14))
    ui = SimpleNamespace(file_menu=None, text_page=0, lines=[], session=SimpleNamespace(game=SimpleNamespace(assets=SimpleNamespace(text=str), s=SimpleNamespace(g={})), decision=pause))
    assert one_key_pause(ui)
    ui.session.decision = dict(pause, info=dict(pause['info'], timed=1))
    assert not one_key_pause(ui)


def file_save_places():
    from .screen import Controller
    assert Controller.plus_file == 'dkk-plus.json'
    def tried(decision):
        ui = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(), decision=decision), file_mode='game', file_message='', file_menu=True)
        Controller.file_key(ui, 's', 's')
        return ui.file_mode, ui.file_message
    assert tried(dict(kind='MENU', options=('Move', 'Encamp'), info=dict(world_menu=True))) == ('save', '')
    assert tried(dict(kind='CAMP_MENU', options=('Save',), info={})) == ('save', '')
    assert tried(dict(kind='MENU', options=('Yes', 'No'), info={})) == ('game', 'Save from exploration, camp or the Outpost menu.')


def study_speaker():
    from .screen import speaker
    a, b, c = (SimpleNamespace(b=bytes((len(n),)) + n) for n in (b'TANAR', b'TANAR II', b'TANAR'))
    assert speaker([a, b], 'TANAR II has memorized') is b and speaker([a, b], 'TANAR has memorized') is a
    assert speaker([a, b, c], 'TANAR has memorized', 2) is c and speaker([a], 'X has') is None


def view_entry():
    from .screen import view_start
    view = dict(kind='CREATE_VIEW', options=['Items', 'Trade', 'Drop', 'Exit'], info={})
    ui = SimpleNamespace(session=SimpleNamespace(decision=view), view_word=2)
    view_start(ui, dict(kind='SHOP_MENU', options=['Buy', 'View', 'Exit'], info={}), 1)
    assert (ui.horizontal_choice, ui.selected) == (0, 0)
    view_start(ui, view, 2)
    view_start(ui, dict(kind='VIEW_ITEMS', options=['Mace', 'Exit'], info={}), 0)
    assert (ui.horizontal_choice, ui.selected) == (2, 2)


def leave_colours():
    from .screen import leave_question, yes_no_menu
    ask = lambda **info: dict(kind='CONFIRM', options=('Yes', 'No'), info=info)
    treasure = ask(offer='there is still treasure left. do you want to go back and claim your treasure?', start=1)
    assert leave_question(treasure) == ('there is still treasure left. ', 'do you want to go back and claim your treasure?', True)
    assert not yes_no_menu(treasure)
    assert leave_question(ask(prompt='', offer='x. do you want to go back and get your money?', clear_first=(True, False)))[2]
    assert leave_question(ask(offer='do you want to go back and get your money?', clear_first=(True, True))) == ('', 'do you want to go back and get your money?', False)
    assert leave_question(ask(offer='abort spell? ')) is None
    from .screen import heal_confirm, HEAL_SHOWN
    HEAL_SHOWN.update(decision={}, index=0)
    try:
        assert not heal_confirm(dict(kind='TEMPLE_CONFIRM', options=('Yes', 'No'), info=dict(offer='do you want to go back and get your money?', clear_first=(True, True))))
        assert heal_confirm(dict(kind='TEMPLE_CONFIRM', options=('Yes', 'No'), info=dict(offer='AB is not blind.')))
    finally: HEAL_SHOWN.clear()


def ready_shown():
    from ..creation import F
    from . import screen
    b = bytearray(400); b[0], b[1], b[F['active']], b[F['level_up_ready']] = 1, 65, 1, 1
    seen = []
    frame = SimpleNamespace(text=lambda col, row, text, assets, colour=15, *rest: seen.append((row, text, colour)))
    game = SimpleNamespace(vm=SimpleNamespace(roster_shown=None, ready_shown=(0,)), s=SimpleNamespace(party=[SimpleNamespace(b=b)], sel=1, mode=0))
    screen.draw_party(frame, game, None)
    assert (4, 'A', 11) in seen
    game.vm.ready_shown, seen[:] = None, []
    screen.draw_party(frame, game, None)
    assert (4, 'A', 13) in seen
    game.vm.ready_shown, seen[:] = (0,), []
    screen.roster_moved(game, (0, 1))
    screen.draw_party(frame, game, None)
    assert (4, 'A', 13) in seen, seen
    game.vm.ready_shown, seen[:] = tuple([0]), []
    screen.draw_party(frame, game, None)
    assert (4, 'A', 11) in seen, seen
    screen.roster_moved(SimpleNamespace(vm=SimpleNamespace(ready_shown=None)), ())
    assert not screen.READY_LIVE
    game.s.monsters, game.s.sel, seen[:] = [SimpleNamespace(b=bytearray(b))], 1, []
    screen.draw_party(frame, game, None)
    assert (5, 'A', 15) in seen, seen
    game.vm.linked_shown, seen[:] = 1, []
    screen.draw_party(frame, game, None)
    assert seen and not [row for row in seen if row[0] == 5], seen
    game.vm.linked_shown, seen[:] = None, []
    screen.draw_party(frame, game, None)
    assert (5, 'A', 15) in seen, seen
    game.vm.linked_shown, game.s.mode, seen[:] = 1, 6, []
    screen.draw_party(frame, game, None)
    assert (5, 'A', 15) in seen, seen
    game.s.mode = 0
    b[F['hp']], b[F['hp_max']], b[F['ac']], seen[:] = 9, 9, 55, []
    game.vm.rows_shown = {0: (7, 50)}
    screen.draw_party(frame, game, None)
    assert (4, '10', 10) in seen and (4, '7', 14) in seen, seen
    game.vm.rows_shown = {0: (7, 50), 3: (1, 1)}
    screen.roster_moved(game, (0, 1))
    assert game.vm.rows_shown == {3: (1, 1)}
    game.vm.rows_shown, seen[:] = None, []
    screen.draw_party(frame, game, None)
    assert (4, '5', 10) in seen and (4, '9', 10) in seen, seen
    del game.s.monsters, game.vm.linked_shown
    game.vm.ready_shown, game.vm.roster_shown, game.s.mode, seen[:] = (0,), 0, 6, []
    screen.draw_party(frame, game, None)
    assert (4, 'A', 13) in seen, seen



def appraise_drawn():
    from ..creation import F
    from . import screen
    b = bytearray(400); b[F['active']] = 1
    seen = []
    frame = SimpleNamespace(rect=lambda *a: None, text=lambda col, row, text, assets, colour=15, *rest: seen.append((col, row, text, colour)))
    game = SimpleNamespace(assets=SimpleNamespace(text=lambda key: {'gemsCountLabel': 'gems : ', 'jewelryCountLabel': 'jewelry : '}[key]), s=SimpleNamespace(selc=lambda: SimpleNamespace(b=b)))
    listed = dict(kind='LIST', info=dict(purpose='appraise', member='A', collection='C', gems=2, jewelry=0))
    screen.APPRAISE_SHOWN.update(info=listed['info'])
    screen.draw_appraisal(frame, game, None, dict(kind='SHOP_MENU', info=dict(purpose='appraise-value', value_line='V', value_column=1, value_row=12)))
    screen.APPRAISE_SHOWN.clear()
    assert seen == [(1, 1, 'A', 11), (1, 7, 'C', 15), (1, 9, 'gems : 2', 15), (1, 10, 'jewelry : 0', 15), (1, 12, 'V', 15)], seen

def icon_old():
    from . import screen
    from ..creation import F, PENDING
    from ..rules import Character
    b = bytearray(Character.SIZE); b[F['icon_head']] = 3
    game = SimpleNamespace(s=SimpleNamespace(g={PENDING: [b, [], []]}))
    ui = SimpleNamespace(session=SimpleNamespace(game=game))
    menu = dict(kind='CREATE_ICON', options=('Parts', 'Exit'), info=dict(icon_state=1))
    screen.icon_seen(ui, menu); b[F['icon_head']] = 4; screen.icon_seen(ui, menu)
    assert ui.icon_old[0] == 3 and screen.icon_record(game)[0] == 4
    screen.icon_seen(ui, dict(kind='CREATE_ICON', options=('Yes', 'No'), info=dict(icon_state=0))); assert ui.icon_old[0] == 3
    screen.icon_seen(ui, menu); assert ui.icon_old[0] == 4
    screen.icon_seen(ui, dict(kind='CREATE_SAVE', options=('Yes', 'No'), info={})); assert ui.icon_old is None
    ui.session.decision, ui.file_menu, ui.held, ui.error = menu, None, lambda: None, None
    assert screen._key(ui, 'Escape') is False
    cast = SimpleNamespace(session=SimpleNamespace(decision=dict(kind='ACK', info=dict(spell=3)), game=SimpleNamespace(s=SimpleNamespace(g={}))))
    assert screen.spell_message(cast) and not screen.spell_message(SimpleNamespace(session=SimpleNamespace(decision=dict(kind='ACK', info={}), game=cast.session.game)))


def missile_flight():
    from types import SimpleNamespace
    from . import screen
    assert 'missile_shot' in screen._family_battle.__code__.co_names and 'shot' in screen._family_battle.__code__.co_varnames
    assert 'step_data' in screen._family_battle.__code__.co_names
    hit = dict(kind='attack', lead='attacks GOBLIN', result='Hitting for 3 points of damage', target='GOBLIN')
    def cursor_after(*report): return screen.fight_cursor(SimpleNamespace(combat_report=list(report), s=SimpleNamespace(chars=lambda: []), assets=SimpleNamespace(text=dict(lostSpellMessage='lost a spell').get)))
    assert cursor_after('GOBLIN lost a spell', hit) == screen.message_window('lost a spell', 23, 13, 38, 21, 23, 13)[1:] != cursor_after(hit)
    assert cursor_after('ORC lost a spell', hit) == cursor_after(hit)
    assert 'posed_icon' in screen._family_battle.__code__.co_names and 'view' in screen._family_battle.__code__.co_consts
    posing = SimpleNamespace(combat_icon=lambda game, i, frame: (((frame, 0, 1),), None))
    held = SimpleNamespace(s=SimpleNamespace(g={'dkk.battle': dict(actors=[dict(facing=1), dict(facing=6)])}))
    assert [screen.posed_icon(posing, held, step, i)[0] for step, i in ((dict(kind='attack', actor=0, facing=5), 0), (dict(kind='attack', actor=0, facing=2), 0), (dict(kind='attack', actor=1, facing=4), 1), (dict(kind='attack', actor=1), 0), ('text', 1))] == [((1, 0, 1)[::-1],), ((1, 0, 1),), ((1, 0, 1),), ((0, 0, 1),), ((0, 0, 1),)]
    data = dict(actor=0, panel=2, panel_print=dict(hp=9))
    assert screen.step_data(data, 'text') is data and screen.step_data(data, dict(kind='move')) is data
    assert screen.step_data(data, dict(kind='attack', panel=4)) == dict(actor=0, panel=4) and screen.step_data(data, dict(kind='attack', panel=4, panel_print=dict(hp=3)))['panel_print'] == dict(hp=3)
    assert screen.flight((0, 0), (1, 1), (1, 1)) == ()
    assert screen.flight((0, 0), (1, 1), (2, 1)) == ((0, 0, 4, 3), (0, 0, 5, 3), (0, 0, 6, 3))
    assert screen.flight((0, 0), (1, 1), (6, 3))[4:7] == ((0, 0, 8, 5), (0, 0, 9, 5), (0, 0, 10, 6))
    near = screen.flight((10, 10), (8, 12), (13, 12))
    assert len(near) == 15 and {shot[:2] for shot in near} == {(7, 9)} and near[-1] == (7, 9, 18, 9)
    far = screen.flight((24, 10), (28, 14), (12, 1))
    assert far[0] == (24, 10, 11, 11) and far[-1] == (9, 0, 9, 3) and len(far) == 23
    shot = dict(kind='missile', view=(0, 0), start=(1, 1), aim=(6, 3), pace=50, frames=4, picture=16, facing=0, mirror=False, item=2)
    assert screen.report_hold(shot, 0.4) == 0.75 and screen.report_hold(dict(shot, pace=10), 0.4) == 0.15
    assert screen.report_hold(dict(kind='move', actor=0, left=3, still=1), 0.4) == 0 and screen.report_hold(dict(kind='move', actor=0, left=3), 0.4) == screen.MOVE_HOLD
    assert screen.step_sounds(shot) == [12, 9] and screen.step_sounds(dict(shot, item=5)) == [12, 12] and screen.step_sounds(dict(shot, item=28)) == [12, 6]
    assert screen.step_sounds(dict(kind='move', still=1)) == [] and screen.step_sounds(dict(kind='move')) == [10]
    pictures = {}
    assets = SimpleNamespace(combat_picture=lambda family, ident: [pictures.setdefault(ident, ((ident, 0),))])
    frames = screen.missile_frames(assets, shot)
    assert frames == [((3, 0),), ((0, 3),), ((0, 131),), ((131, 0),)]
    assert screen.missile_frames(assets, dict(shot, frames=2, picture=21)) == [((8, 0),), ((136, 0),)]
    assert screen.missile_frames(assets, dict(shot, frames=1, picture=14, facing=1, mirror=True)) == [((0, 129),)]
    controller = SimpleNamespace(assets=assets)
    assert screen.missile_shot(controller, shot, (0, 0.26), (5, 5)) == (0, 0, 9, 5, ((0, 3),))
    assert screen.missile_shot(controller, shot, (0, 9.0), (5, 5))[:4] == (0, 0, 18, 9)
    assert screen.missile_shot(controller, dict(kind='move'), (0, 0.0), (5, 5)) is None and screen.missile_shot(controller, 'text', (0, 0.0), (5, 5)) is None
    cloud = dict(kind='scatter', cell=26, aim=(47, 1), rings=(((9, 9, 0),), ((10, 8, 1), (8, 9, 2)), ((12, 4, 3),)))
    assert screen.report_hold(cloud, 0.4) == 3 * screen.SCATTER_RING and screen.step_sounds(cloud) == [11] and screen.scatter_shot(controller, shot, (0, 0.0)) is None
    assert screen.scatter_shot(controller, cloud, (0, 0.0)) == (43, 0, [(9, 9, ((13, 0),))])
    assert screen.scatter_shot(controller, cloud, (0, 0.06))[2][1:] == [(10, 8, ((0, 13),)), (8, 9, ((141, 0),))]
    assert screen.scatter_shot(controller, cloud, (0, 9.0))[2][3] == (12, 4, ((0, 141),)) and screen.scatter_shot(controller, dict(cloud, aim=(10, 12)), (0, 0.0))[:2] == (7, 9)
    assert 'scatter_shot' in screen._family_battle.__code__.co_names and 'fall_view' in screen._family_battle.__code__.co_names
    fall = dict(kind='fall', actor=3, view=(4, 2), actors=(), cells=((5, 3, 7, None), (20, 3, 7, 4)), picture=23, frames=(0, 1) * 4 + (0,), pace=10)
    hit, down = dict(kind='attack', result='Hitting for 5'), dict(kind='attack', result='Hitting for 5', down='')
    report = ['a', fall, hit, down]; screen.place_falls(report, [(2, 'x')])
    assert report == ['a', hit, dict(down, fall=fall)] and screen.falling(report[2]) is fall and screen.falling(hit) is None and screen.falling('a') is None
    report = ['a', fall, 'b']; screen.place_falls(report, [(2, 'TROLL takes 9')])
    assert report == ['a', dict(fall, text='TROLL takes 9'), 'b'] and screen.step_sounds(report[1]) == [5]
    report = ['a', hit]; screen.place_falls(report, [(2, 'x')]); assert report == ['a', hit]
    assert abs(screen.report_hold(fall, 0.4) - (0.09 + screen._family_report_hold(fall, 0.4))) < 1e-9 and abs(screen.report_hold(dict(down, fall=fall), 0.4) - (0.09 + screen.report_hold(down, 0.4))) < 1e-9
    assert screen.fall_view(fall) == (4, 2, ()) and screen.fall_view(hit) is None
    drawn = []
    canvas = SimpleNamespace(blit=lambda x, y, pixels, **k: drawn.append((x, y, pixels)))
    looks = SimpleNamespace(assets=SimpleNamespace(combat_picture=assets.combat_picture, view_tables={'icon_palette': None}), session=SimpleNamespace(game=SimpleNamespace(combat_tile_frames=['g%d' % n for n in range(9)])))
    screen.draw_fall(canvas, looks, None, dict(down, fall=fall), (0, 0.015))
    assert drawn == [(32, 32, 'g7'), (32, 32, ((138, 0),))]
    drawn.clear(); screen.draw_fall(canvas, looks, None, dict(down, fall=fall), (0, 0.5)); assert drawn[-1] == (32, 32, ((10, 0),))
    family, said = screen.draw_character_message, []
    screen.draw_character_message = lambda frame, assets, info: said.append(info)
    try: screen.draw_fall(canvas, looks, None, dict(fall, text='X destroyed', creature_message={'creature_name': 'X'}), (0, 0.5))
    finally: screen.draw_character_message = family
    assert said == [{'creature_name': 'X'}], said
    report = [dict(kind='move', actor=1, left=4), dict(kind='move', actor=1, left=3, still=1), dict(kind='attack'), dict(kind='begin'), 'text', dict(kind='move', actor=0, left=None)]
    assert [screen.left_line(report, at) for at in range(6)] == [4, 3, 3, None, None, None]
    report = [dict(kind='move', actor=1, left=4), dict(kind='clear', bottom=False), dict(kind='clear', bottom=True), dict(kind='attack')]
    assert [screen.left_line(report, at) for at in range(4)] == [4, 4, None, None]
    assert screen.report_hold(report[2], 0.4) == 0 and screen.step_sounds(report[2]) == []


def bolt_steps():
    from types import SimpleNamespace
    from . import screen
    pictures = {}
    controller = SimpleNamespace(assets=SimpleNamespace(combat_picture=lambda family, ident: [pictures.setdefault(ident, ((ident, 0),))]))
    actors = ((1, 1, 1), (6, 3, 1))
    cast = dict(kind='bolt', actor=0, start=(1, 1), aim=(6, 3), spell=51, picture=18, frames=4, pace=30, view=(0, 0), actors=actors)
    stretch = dict(kind='flight', start=(6, 3), aim=(9, 3), picture=19, frames=4, pace=50, view=(0, 0), actors=actors)
    assert screen.missile_shot(controller, cast, (0, 0.0), (5, 5)) == (0, 0, 4, 3, ((5, 0),))
    assert screen.missile_shot(controller, cast, (0, 0.16), (5, 5)) == (0, 0, 9, 5, ((0, 5),))
    assert screen.missile_shot(controller, stretch, (0, 0.0), (5, 5)) == (4, 0, 7, 9, ((6, 0),))
    assert screen.missile_shot(controller, stretch, (0, 0.11), (5, 5)) == (4, 0, 9, 9, ((0, 134),))
    assert screen.missile_shot(controller, stretch, (0, 9.0), (5, 5)) == (4, 0, 15, 9, ((6, 0),))
    assert screen.missile_shot(controller, dict(stretch, picture=18, frames=1, pace=30), (0, 0.1), (5, 5))[4] == ((5, 0),)
    assert abs(screen.report_hold(cast, 0.4) - 15 * 0.03) < 1e-9 and abs(screen.report_hold(stretch, 0.4) - 9 * 0.05) < 1e-9
    assert screen.report_hold(dict(cast, aim=(1, 1)), 0.4) == 0 and screen.report_hold(dict(stretch, aim=(6, 3)), 0.4) == 0
    old = dict(kind='bolt', actor=0, aim=(6, 3), spell=51, view=(0, 0), actors=actors)
    assert screen.flown(old) is None and screen.missile_shot(controller, old, (0, 0.0), (5, 5)) is None and screen.report_hold(old, 0.4) == screen._family_report_hold(old, 0.4)
    assert [screen.step_sounds(dict(cast, spell=n)) for n in (51, 47, 20)] == [[8], [11], [2]] and screen.step_sounds(stretch) == []
    posing = SimpleNamespace(combat_icon=lambda game, i, frame: (((frame, 0, 1),), None))
    held = SimpleNamespace(s=SimpleNamespace(g={'dkk.battle': dict(actors=[dict(facing=1), dict(facing=6)])}))
    assert screen.posed_icon(posing, held, dict(cast, posed=1), 0)[0] == ((1, 0, 1),) and screen.posed_icon(posing, held, dict(cast, posed=1), 1)[0] == ((0, 0, 1),)
    assert screen.posed_icon(posing, held, cast, 0)[0] == ((0, 0, 1),) and screen.posed_icon(posing, held, stretch, 0)[0] == ((0, 0, 1),)


def bolt_playback():
    from types import SimpleNamespace
    from . import screen
    text = 'SOLAMNIC KNIGHT takes 29 points of damagefrom electricity'
    flash = dict(kind='flash', creature=14, hit=True, at=(27, 18), text=text, frames=4, view=(25, 14), panel=6)
    assert screen.flashed(['a', text], flash) == ['a', dict(flash, said=True)] and screen.flashed(['a'], flash) == ['a', dict(flash, said=False)]
    assert abs(screen.report_hold(flash, 0.4) - (0.28 + screen._family_report_hold(flash, 0.4))) < 1e-9 and abs(screen.report_hold(dict(flash, hit=False, frames=20), 0.4) - 1.4) < 1e-9
    assert screen.step_sounds(dict(flash, said=True)) == screen._family_step_sounds(text) and screen.step_sounds(dict(flash, said=False)) == []
    drawn, said = [], []
    canvas = SimpleNamespace(blit=lambda x, y, px, **k: drawn.append((x, y, px)))
    looks = SimpleNamespace(assets=SimpleNamespace(combat_picture=lambda family, ident: [((ident, 0),)], view_tables={'icon_palette': None}))
    family = screen.draw_fight_message
    screen.draw_fight_message = lambda frame, assets, battle, t: said.append(t)
    try:
        screen.draw_flash(canvas, looks, None, flash, (0, 0.15)); screen.draw_flash(canvas, looks, None, flash, (0, 0.3))
    finally: screen.draw_fight_message = family
    assert drawn == [(56, 104, ((0, 139),))] and said == [text, text]
    cast = dict(kind='bolt', actor=5, spell=51, start=(1, 1), aim=(6, 3), picture=18, frames=4, pace=30, view=(0, 0))
    report = ['x', cast, 'y', dict(kind='attack', actor=5, view=(5, 6)), 'z']
    assert screen.ended_view(report, 0) is None and screen.ended_view(report, 2) == screen.flight((0, 0), (1, 1), (6, 3))[-1][:2] and screen.ended_view(report, 4) == (5, 6)
    assert screen.ended_view(['x', dict(kind='begin'), 'y'], 2) is None
    shows = [cast, dict(kind='flight'), flash, 'hit text', dict(kind='scatter'), dict(kind='attack', actor=7)]
    assert [screen.casting_spell(shows, k) for k in range(6)] == [51, 51, 51, 51, 51, None]
    rows = [bytearray(1)] * 16
    ui = SimpleNamespace(report=shows[:3] + [dict(kind='move', actor=5), 'Guarding', dict(kind='attack', actor=7)])
    ui.aim_kept = (ui.report, 5, rows)
    held = screen.holding
    screen.holding = lambda controller: True
    try:
        kept = [screen.aim_rows(ui, (k, 0)) is rows for k in range(6)]
        ui.report = list(ui.report); lost = screen.aim_rows(ui, (0, 0))
    finally: screen.holding = held
    assert kept == [True, True, True, True, False, False] and lost is None


def timed_carry():
    from types import SimpleNamespace
    from . import screen
    menu = dict(kind='COMBAT_ACTION', i=1, options=['Move', 'Aim', 'Use', 'Cast', 'Guard', 'Quick'], info={})
    note = dict(kind='ACK', i=2, options=['Continue'], info=dict(timed=1, prompt='casts a spell'))
    aim = dict(kind='TARGET', i=3, options=['Next', 'Prev', 'Manual', 'Target', 'Center', 'Exit', 'GOBLIN#7'], info=dict(selected=7, highlight=''))
    def run(*steps, index=3):
        queue = iter(steps)
        ui = SimpleNamespace(session=SimpleNamespace(decision=menu), horizontal_choice=0)
        ui.aim_options = lambda: screen.aim_options(ui)
        def fake(self, chosen): self.session.decision = next(queue); self.horizontal_choice = 0; return True
        plain = screen._plain_choose
        screen._plain_choose = fake
        try:
            screen._family_choose(ui, index)
            while ui.session.decision is not steps[-1]: screen._family_choose(ui, 0)
        finally: screen._plain_choose = plain
        return ui.horizontal_choice
    assert run(note, aim) == 3 and run(note, dict(note, i=4), aim) == 3
    assert run(note, dict(aim, info=dict(selected=7, highlight='Next'))) == 0 and run(note, menu) == 0 and run(aim) == 0


def fight_view():
    from . import screen
    view = dict(kind='CREATE_VIEW', options=('Items', 'Spells', 'Drop', 'Exit'), info={'name': 'NEACAIL'})
    coin = dict(kind='VIEW_COIN', options=('Steel          500', 'Exit'), info={'prompt': 'select type of coin '})
    amount = dict(kind='NUMBER', options=None, info={'prompt': 'How much Steel will you drop? '})
    kept = dict(screen.COIN_SHOWN); screen.COIN_SHOWN.clear()
    try:
        assert screen.own_window(view) and screen.own_window(coin) and not screen.own_window(amount)
        assert not screen.own_window(dict(kind='COMBAT_ACTION', options=('Move', 'View'), info={}))
        screen.COIN_SHOWN.update(decision=coin); assert screen.own_window(amount)
    finally: screen.COIN_SHOWN.clear(); screen.COIN_SHOWN.update(kept)


def slow_text():
    from . import screen
    words = dict(whatDoYouDoText='What do you do?', partyKilledText='The party is killed.', partyGainsText='The party gains.',
                 congratulationsText='Congratulations ', journalEntryPrefix='Journal entry ', partyDestroyed='gone')
    hero = SimpleNamespace(b=bytearray(bytes((4,)) + b'DRAK' + bytes(400)))
    runtime = dict(slow_text=1)
    vm = SimpleNamespace(out=[], text_start=0)
    game = SimpleNamespace(assets=SimpleNamespace(text=words.get), s=SimpleNamespace(chars=lambda: [hero], g={'dkk.runtime': runtime}), vm=vm)
    printed = lambda *parts: screen.printed(game, list(parts))
    assert not printed('What do you do?', '\n', 'Journal entry 12.', 'Congratulations DRAK gains')
    assert not printed('DRAK is hit FOR 4 points', '\nof Damage.', '\n  DRAK dies.') and printed('A door opens.') and printed('DRAK dies.', 'A door.')
    ui = SimpleNamespace(session=SimpleNamespace(game=game, decision=None), slow=(1, 0, 0.0), file_menu=False)
    def capture(*parts, d=None, flag=None):
        if flag is not None: runtime['slow_text'] = flag
        vm.out.extend(parts); ui.session.decision = d; ui.slow = (1, 0, 0.0); screen.slow_window(ui, d); return ui.slow is not None
    assert capture('What do you do?') and screen.slow_on(ui)
    assert capture('A sign reads.') and not screen.slow_on(ui) and not capture('What do you do?') and capture('Another sign.')
    assert not capture(flag=0) and not capture('Journal entry 3.')
    gone = dict(kind='ACK', options=['Continue'], info=dict(message='gone', prompt='x'))
    capture(d=gone); assert screen.slow_on(ui) and ui.typed == (2, 5, 37, 22)
    assert capture('What do you do?', flag=1) and capture('Text.', flag=0) and not capture('What do you do?')
    question = dict(kind='MENU', options=['North', 'South'], info=dict(vertical=1, prompt='Which way?'))
    capture(d=question, flag=1); assert ui.typed == (1, 17, 38, 17)
    capture('A sign.', d=question); capture(d=question); assert ui.typed is None
    frame = SimpleNamespace(rows=[bytearray(320) for _ in range(200)])
    for col in (1, 2, 4): frame.rows[17 * 8 + 3][col * 8 + 2] = 10
    frame.rows[18 * 8][1 * 8] = 10
    rect = (1, 17, 38, 22)
    assert screen.row_lengths(frame, rect) == [4, 1, 0, 0, 0, 0]
    cut = SimpleNamespace(rows=[bytearray(row) for row in frame.rows])
    assert not screen.type_cells(cut, rect, 2) and screen.row_lengths(cut, rect) == [2, 0, 0, 0, 0, 0]
    cut = SimpleNamespace(rows=[bytearray(row) for row in frame.rows])
    assert screen.type_cells(cut, rect, 5) and cut.rows == frame.rows
    now = [10.0]
    ui = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(g={'dkk.delay': 4}))), effect_scale=1, file_menu=False, typed=rect, decided_at=10.0, clock=lambda: now[0])
    assert screen.typing(ui) == 0; now[0] += 0.037; assert screen.typing(ui) == 3
    ui.effect_scale = 0; assert screen.typing(ui) is None
    def inked(controller, event):
        shown = SimpleNamespace(rows=[bytearray(320) for _ in range(200)])
        for col in range(len(event['text'])): shown.rows[17 * 8][(1 + col) * 8] = 10
        return shown
    kept, screen.render_hold = screen.render_hold, inked
    try:
        ui.effect_scale = 1
        held = screen.typed_script_holds(ui, [dict(kind='script-hold', text=t, delay=1.0) for t in ('AB', 'ABCD', 'ABCD', 'X')])
        step = screen.typed_step(ui)
        assert [(e.get('typed_from'), round(e['delay'] - 1.0, 6)) for e in held] == [(0, round(2 * step, 6)), (2, round(2 * step, 6)), (None, 0), (0, round(step, 6))]
    finally: screen.render_hold = kept


def heal_held():
    from . import screen
    from ..records import Character
    from ..creation import F
    def member(text, hp):
        b = bytearray(Character.SIZE); b[0] = len(text); b[1:1 + len(text)] = text.encode('cp437')
        for key, value in (('active', 1), ('hp', hp), ('hp_max', 9), ('ac', 60)): b[F[key]] = value
        return SimpleNamespace(b=b)
    party = [member('A', 3), member('B', 7)]
    texts = {'fullyHealedText': 'is fully healed', 'partiallyHealedText': 'is partially healed'}
    game = SimpleNamespace(s=SimpleNamespace(party=party, monsters=[], g={}, mode=0, sel=0), vm=SimpleNamespace(), assets=SimpleNamespace(text=texts.get))
    ui = SimpleNamespace(session=SimpleNamespace(game=game), hp_seen=[3, 2])
    party[1].b[F['hp']] = 9
    assert screen.healed(ui, dict(creature_name='B', creature_text='is unaffected')) == {}
    held = screen.healed(ui, dict(creature_name='B', creature_text='is fully healed'))
    assert held == dict(game=game, member=1, hp=2) and ui.hp_seen == [3, 9], held
    drawn = []
    frame = SimpleNamespace(text=lambda col, row, text, assets, colour=10, width=40: drawn.append((col, row, text, colour)))
    screen.HP_HELD.update(held); screen.draw_party(frame, game, None); screen.HP_HELD.clear()
    assert (38, 5, '2', 14) in drawn and (38, 4, '3', 14) in drawn, drawn
    assert screen.healed(ui, dict(creature_name='B', creature_text='is fully healed')) == {}
    game.s.g['dkk.battle'] = dict(active=1); party[1].b[F['hp']] = 5
    assert screen.healed(ui, dict(creature_name='B', creature_text='is partially healed')) == {}


def after_fight_text():
    from . import screen
    assert screen.attack_result_lines(dict(result='Hitting for 14 points of damage')) == ['Hitting for 14', 'points  of', 'damage']
    lines, col, row = screen.message_window("SKOMP'S BOAR LIES DEAD BEFORE YOU. DO YOU PICK IT UP?", 1, 17, 38, 22, 32, 17, False)
    assert (min(lines), col, row) == (18, 16, 19) and lines[18].endswith(' DO'), lines
    assert screen.message_window('goes down', 23, 17, 38, 21, 29, 15)[1:] == (32, 17)
    left = dict(kind='CONFIRM', options=['Yes', 'No'], info=dict(offer='there is still treasure left. do you want to go back and claim your treasure?'))
    assert screen.left_cursor(left) == (10, 19)
    assert screen.notice_end(dict(info=dict(offer='Your LONG SWORD will be left in the vault')), (1, 21, 38, 22)) == (6, 22)
    assert screen.notice_end(dict(info=dict(creature_name='SIR', creature_text='is fully healed')), (1, 19, 38, 22)) == (16, 19)


def discard_on_setup():
    from types import SimpleNamespace
    from . import screen
    c = SimpleNamespace(session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(g={}))), sound_on=True)
    c.typeahead = [('d', chr(4)), ('a', 'a'), ('b', 'b'), ('c', 'c')]
    screen.discard_reads(c, 3)
    assert c.typeahead == [('c', 'c')] and c.session.game.s.g['dkk.runtime']['trace'] == 1
    c.typeahead = [('Up', ''), ('a', 'a'), ('Alt-q', 'q'), ('b', 'b')]
    screen.discard_reads(c, 3)
    assert c.typeahead == [('Alt-q', 'q'), ('b', 'b')]
    screen.discard_reads(c, 1)
    assert c.typeahead == [(chr(16), chr(16)), ('b', 'b')] and c.sound_on
    c.typeahead = [('Alt-r', 'r'), ('a', 'a')]
    screen.discard_reads(c, 2)
    assert c.typeahead == [('a', 'a')] and not c.sound_on
    c.typeahead = [('a', 'a'), ('Up', '')]
    screen.discard_reads(c, 2)
    assert c.typeahead == [('H', 'H')]
    c.typeahead = [('Alt-y', 'y')]
    screen.discard_reads(c, 1)
    assert c.typeahead == [(chr(21), chr(21))] and 'music_on' not in c.session.game.s.g['dkk.runtime']


def quick_space():
    from sm.engine import Session
    from ..menu import Game
    from .._first_fight import OpeningChoices
    from . import screen
    with TemporaryDirectory(prefix='sm-dkk-screen-') as tmp:
        game = Game(None); game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000); policy = OpeningChoices()
        ui, now = screen.Controller(session), [0.0]
        ui.clock = lambda: now[0]
        try:
            while not (session.decision['kind'] == 'COMBAT_ACTION' and 'Alt-q' in session.decision['options']):
                ui.choose(policy(session.decision, game))
            ui.choose(session.decision['options'].index('Alt-q'))
            while not (screen.holding(ui) and session.decision['kind'] == 'COMBAT_AUTO'):
                now[0] += 0.05; screen.render(ui)
            shown = len(ui.report); ui.key('space', ' ')
            assert len(ui.report) == shown and (getattr(ui, 'fight_keys', None) or getattr(ui, 'typeahead', None)) == [('space', ' ')]
            for _ in range(400):
                now[0] += 0.05; screen.render(ui)
                if session.decision['kind'] != 'COMBAT_AUTO': break
            assert session.decision['kind'] == 'COMBAT_ACTION' and not getattr(ui, 'fight_keys', None) and not getattr(ui, 'typeahead', None), session.decision['kind']
        finally: session.close()


def manual_typeahead():
    from sm.engine import Session
    from ..menu import Game
    from .._first_fight import OpeningChoices
    from . import screen
    with TemporaryDirectory(prefix='sm-dkk-screen-') as tmp:
        game = Game(None); game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000); policy = OpeningChoices()
        ui, now = screen.Controller(session), [0.0]
        ui.clock = lambda: now[0]
        try:
            while not (session.decision['kind'] == 'COMBAT_ACTION' and 'Alt-q' in session.decision['options']):
                ui.choose(policy(session.decision, game))
            ui.choose(session.decision['options'].index('Guard'))
            assert screen.holding(ui) and session.decision['kind'] == 'COMBAT_ACTION' and screen.poll_times(ui)
            asked = session.decision; ui.key('g', 'g')
            assert session.decision is asked and (getattr(ui, 'fight_keys', None) or getattr(ui, 'typeahead', None)) == [('g', 'g')]
            for _ in range(400):
                now[0] += 0.05; screen.render(ui)
                if not screen.holding(ui): break
            screen.render(ui)
            assert session.decision is asked and not ui.fight_keys and not getattr(ui, 'typeahead', None)
            ui.choose(session.decision['options'].index('Guard'))
            asked = session.decision
            while ui.queue():
                now[0] += 0.05; screen.render(ui)
            now[0] = ui.report_at + screen.poll_times(ui)[-1] * ui.effect_scale + 0.01; screen.render(ui)
            assert screen.holding(ui); ui.key('g', 'g')
            for _ in range(400):
                now[0] += 0.05; screen.render(ui)
                if session.decision is not asked: break
            assert session.decision is not asked and not ui.fight_keys and not ui.typeahead
        finally: session.close()


def polled_effects():
    from sm.engine import Session
    from ..menu import Game
    from ..town import field, put
    from .._first_fight import OpeningChoices
    from . import screen
    with TemporaryDirectory(prefix='sm-dkk-screen-') as tmp:
        game = Game(None); game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000); policy = OpeningChoices()
        ui, now = screen.Controller(session), [0.0]
        ui.clock = lambda: now[0]
        try:
            while not (session.decision['kind'] == 'COMBAT_ACTION' and 'Alt-q' in session.decision['options']):
                ui.choose(policy(session.decision, game))
            ui.choose(session.decision['options'].index('Guard'))
            while ui.queue():
                now[0] += 0.05; screen.render(ui)
            polls, actor = sorted(set(screen.poll_times(ui))), game.s.g['dkk.battle']['actor']
            assert len(polls) > 1 and screen.holding(ui)
            quick = next(c for c in game.s.party if c is not game.battle.chars[actor])
            put(quick, 'auto_combat', 1); magic = bool(getattr(game, 'combat_magic', False))
            for key, at in ((('2', '2'), polls[0]), (('space', ' '), polls[1])):
                now[0] = ui.report_at + (at - 0.001) * ui.effect_scale; screen.render(ui); ui.key(*key)
            for _ in range(800):
                now[0] += 0.05; screen.render(ui)
                if not screen.holding(ui) and not ui.queue() and session.decision['kind'] == 'COMBAT_ACTION' and not ui.fight_keys: break
            assert bool(getattr(game, 'combat_magic', False)) is not magic and field(quick, 'auto_combat') == 0
            assert session.decision['kind'] == 'COMBAT_ACTION' and not ui.fight_keys and not getattr(ui, 'typeahead', None)
            assert screen.poll_read(('Alt-d', '')) == 'manual' and screen.poll_read(('Alt-m', '')) == 'magic' and screen.poll_read(('g', 'g')) is None
        finally: session.close()


def string_steps():
    from sm.engine import Session
    from ..menu import Game
    from .. import combat
    from .._first_fight import OpeningChoices
    from . import screen
    ui = lambda report, live=(): SimpleNamespace(report=report, session=SimpleNamespace(game=SimpleNamespace(s=SimpleNamespace(g={'dkk.battle': {'actors': [dict(x=x, y=y, size=z) for x, y, z in live]}}))))
    walk = [dict(kind='move', actors=((1, 1, 1), (2, 2, 1), (3, 3, 1))), 'fled', dict(kind='move', actors=((1, 2, 1), (2, 2, 0), (3, 3, 1))),
            dict(kind='attack', actors=((1, 2, 1), (2, 2, 0), (3, 3, 0))), dict(kind='attack', fall=dict(actor=2), actors=((1, 2, 1), (2, 2, 0), (3, 3, 0))),
            'struck', dict(kind='fall', actor=0, actors=((1, 2, 1), (2, 2, 0), (3, 3, 0))), 'fallen']
    assert screen.string_places(ui(walk), (1, 0.0)) == [(1, 1, 1), (2, 2, 0), (3, 3, 1)]
    assert screen.string_places(ui(walk), (5, 0.0)) == [(1, 2, 1), (2, 2, 0), (3, 3, 0)]
    assert screen.string_places(ui(walk, ((1, 2, 0), (2, 2, 0), (3, 3, 0))), (7, 0.0)) == [(1, 2, 0), (2, 2, 0), (3, 3, 0)]
    later = [dict(kind='move', actors=((1, 1, 1), (2, 2, 1))), 'kept', dict(kind='attack', actors=((1, 1, 1), (2, 2, 0))), dict(kind='attack', fall=dict(actor=1), actors=((1, 1, 1), (2, 2, 0)))]
    assert screen.string_places(ui(later), (1, 0.0)) == [(1, 1, 1), (2, 2, 1)]
    assert screen.string_places(ui(['first'] + later), (0, 0.0)) is None and screen.string_places(ui(later), (0, 0.0)) is None and screen.string_places(ui(later), None) is None
    truth, plain = [], combat.Battle.message
    def message(self, text, report=True):
        if report: truth.append((text, tuple((r['x'], r['y'], r['size']) for r in self.data['actors'])))
        return plain(self, text, report)
    drawn = lambda places: {(i, x, y) for i, (x, y, size) in enumerate(places) if size}
    combat.Battle.message = message
    with TemporaryDirectory(prefix='sm-dkk-screen-') as tmp:
        game = Game(None); game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=5000); policy = OpeningChoices()
        control = screen.Controller(session)
        checked = moved = 0
        try:
            while not (session.decision['kind'] == 'COMBAT_ACTION' and 'Alt-q' in session.decision['options']): control.choose(policy(session.decision, game))
            for _ in range(400):
                if not game.s.g.get('dkk.battle', {}).get('active'): break
                del truth[:]; control.choose(policy(session.decision, game))
                live, p = [(r['x'], r['y'], r['size']) for r in game.s.g['dkk.battle']['actors']], 0
                for k, step in enumerate(control.report):
                    if not isinstance(step, str): continue
                    while truth[p][0] != step: p += 1
                    real = truth[p][1]; p += 1
                    assert drawn(screen.string_places(control, (k, 0.0)) or live) == drawn(real), (k, step)
                    checked += 1; moved += drawn(live) != drawn(real)
        finally:
            combat.Battle.message = plain; session.close()
        assert checked >= 5 and moved, (checked, moved)


def test():
    string_steps()
    polled_effects()
    manual_typeahead()
    discard_on_setup()
    after_fight_text()
    heal_held()
    slow_text()
    icon_old()
    ready_shown()
    appraise_drawn()
    leave_colours()
    view_entry()
    duplicate_view()
    roster_file_name()
    control_keys()
    file_save_places()
    study_speaker()
    order_window()
    overland_view()
    timed_pause()
    rest_hold_drawn()
    number_backspace()
    highlight_kept()
    list_top()
    camp_message()
    from .title import test as title_test
    title_test()
    modify_keys()
    from .screen import symbol_frames
    sets = symbol_frames(bytes((8, 0, 1, 0, 0, 0, 0, 0, 255)) + bytes(8) + bytes(range(256)) * 32)
    assert len(sets) == 256 and sets[1][0] == bytes((2, 0, 2, 1, 2, 2, 2, 3)), sets[1][0]
    paging()
    fight_message()
    missile_flight()
    bolt_steps()
    bolt_playback()
    timed_carry()
    fight_view()
    name_flash()
    aging_page()
    aim_panel()
    load_flush()
    aim_words()
    creature_message()
    from .. import intake
    if not intake.configured(): return 'skipped (no Death Knights copy)'
    pictures()
    modify_drawing()
    title_flow()
    typeahead()
    quick_space()
    escape_and_source()
    sheet_and_items()
    seen, starts, fight, camp = frames()
    assert camp, 'camp shows the view frame and its picture'
    kinds = {tag.split(':')[0] for tag in seen}
    assert {'CREATE_MENU', 'CAMP_MENU', 'COMBAT_ACTION'} <= kinds and kinds & {'COMBAT_SPELL', 'TARGET', 'COMBAT_AUTO'}, kinds
    assert starts.get('reroll stats? ') == 1 and starts.get('save character? ') == 0, starts
    assert fight in ('View', 'Speed', 'Bandage'), fight
