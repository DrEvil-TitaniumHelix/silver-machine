"""UI milestone 2: real derived-route fight through Session and screen keys only."""
from collections import deque
import json
import sys
import time

from sm.engine import Session
from sm.titles.ssb.route import Walk, RESOLVED
from sm.titles.ssb.ui.screen import Assets, Controller, LOCAL, compact_menu, is_roster, list_geometry, menu_items, menu_pages, render
from sm.titles.ssb.ui import screen
from sm.titles.ssb.units import combat as C


def press(controller, answer):
    """UI1 Session contract / ov28:03C9,13EE: submit via visible keys and paging."""
    decision = controller.session.decision
    if decision['options'] is None:
        for ch in str(answer):
            assert not controller.key(ch, ch)
        assert controller.key('Return')
        return
    ui = getattr(controller, 'controller', controller)
    # ov10:0D63: legacy combat API shortcuts stay addressable, outside the native command bar.
    value = decision['options'][answer]
    if value in ('char-up', 'char-down', 'char-first'):
        assert controller.key({'char-up': 'Up', 'char-down': 'Down', 'char-first': 'Home'}[value]); return
    if (decision['kind'], value) in (('COMBAT_ACTION', 'guard'), ('COMBAT_ACTION', 'flee')):
        key = {'guard': 'g', 'flee': 'f'}[value]
        assert controller.key(key, key); return
    if decision['kind'] == 'MOVE':
        value = decision['options'][answer]
        moves = {'turn-left': 'Left', 'turn-right': 'Right', 'forward': 'Up', 'turn-around': 'Down'}
        if value in moves:
            if not ui.move_mode: assert not controller.key('m', 'm')
            assert controller.key(moves[value]); return
        if ui.move_mode: assert not controller.key('e', 'e')  # ov16:0ADA..0AE6: Escape is ignored inside Move.
    if is_roster(decision):
        if decision['options'][answer] is None:
            assert controller.key('Escape'); return
        while ui.selected != answer:
            assert not controller.key('Down' if ui.selected < answer else 'Up')
        assert controller.key('Return'); return
    if screen.cast_list(decision):  # ov23:0316 / ov28:13EE: level headers count as rows, not answers.
        if not isinstance(value, (int, tuple, list)):
            assert controller.key('Escape'); return
        row = next(r for r, (i, _) in enumerate(screen.cast_rows(ui)) if i == answer)
        while not getattr(ui, 'cast_start', 0) <= row < getattr(ui, 'cast_start', 0) + 18:
            key = 'p' if row < getattr(ui, 'cast_start', 0) else 'n'
            assert not controller.key(key, key)
        while ui.selected != answer: assert not controller.key('Down')
        assert controller.key('c', 'c'); return
    items = menu_items(decision, controller.session.game)
    if not compact_menu(items, decision):
        for _ in range(answer // list_geometry(decision)[3]):
            assert not controller.key('Next')
    else:
        page = next(p for p, row in enumerate(menu_pages(items)) if any(i == answer for i, _, _ in row))
        while ui.page < page: assert not controller.key('Next')
    key = next(key for i, key, _ in items if i == answer)
    assert controller.key(key, key), (decision['kind'], answer, key)


def approach(game, actor):
    """ENGINE_READ2_g1 ov10:1194 test policy: approach melee over legal map cells."""
    fight = game.combat
    char = fight.chars[actor]
    start = fight.position(char)
    goals = {(x + dx, y + dy) for foe in fight.chars
             if foe.b[C.ACTIVE] and foe.b[C.SIDE] != char.b[C.SIDE]
             for x, y in fight.cells(foe) for dx, dy in zip(C.DX[:8], C.DY[:8])}
    queue, seen = deque([(start, None)]), {start}
    occupancy = game.s.g['combat.occupancy']
    legal = {(C.DX[d], C.DY[d]) for d in fight.legal_moves(char)}  # ov10:13F4: Move remains offered when the next step costs too much.
    while queue:
        (x, y), first = queue.popleft()
        if first is not None and (x, y) in goals:
            return first
        for dx, dy in zip(C.DX[:8], C.DY[:8]):
            if first is None and (dx, dy) not in legal: continue
            point = (x + dx, y + dy)
            if point in seen:
                continue
            cells = fight.cells(char, *point)
            if not cells or any(not (0 <= a < 50 and 0 <= b < 25) or not fight.tile(a, b)
                                or C.terrain_cost(fight.tile(a, b)) == 255
                                or occupancy[b * 50 + a] not in (0, actor + 1) for a, b in cells):
                continue
            seen.add(point)
            queue.append((point, point if first is None else first))
    return None


def fight_answer(game, decision):
    """ENGINE_READ2_g1 ov10/ov15: deterministic player choices, no state writes."""
    kind, options, info = decision['kind'], decision['options'], decision['info']
    if kind == 'COMBAT_ACTION':
        step = approach(game, info['actor']) if 'move' in options and 'attack' not in options else None
        action = ('attack' if 'attack' in options else 'move' if step is not None
                  else 'guard' if 'guard' in options else 'done')
        return options.index(action)
    if kind == 'TARGET':
        step = approach(game, info['actor']) if info.get('action') == 'move' else None
        return options.index(step) if step in options else 0
    if kind == 'MENU' and info.get('action') in ('continue-battle', 'done'):
        return options.index('end' if info['action'] == 'continue-battle' else 'quit')
    raise AssertionError(('unexpected fight decision', decision))


ARROWS = {(-1, 0): 'Left', (1, 0): 'Right', (0, -1): 'Up', (0, 1): 'Down',
          (-1, -1): 'Home', (1, -1): 'Prior', (-1, 1): 'End', (1, 1): 'Next'}


def check_active_icon(controller, frame):
    """Row 42, ov33:01D3..0292: the actor's icon stays on top of the COMSPR/19h cursor."""
    game, decision = controller.session.game, controller.session.decision
    actor = screen.actor_index(game, decision); x0, y0 = screen.player_viewport(controller)
    x, y = game.s.g['combat.positions'][actor][:2]
    pixels, palette = screen.icon(game, game.s.chars()[actor], game.s.g['combat.records'][actor][9])
    drawn = [(c, r, v) for r, row in enumerate(pixels) for c, v in enumerate(row) if v]
    assert drawn, 'actor icon has no pixels'
    for c, r, v in drawn:
        assert frame.rows[8 + (y - y0) * 24 + r][8 + (x - x0) * 24 + c] == palette[v], 'cursor covers the active icon'


def check_move_attack(controller, reference, step):
    """Row 43, ov10:1321..1355: M, then the arrow toward an adjacent enemy, attacks it through real keys."""
    ui = controller.session; state = ui.game.s; before = state.g.get('combat.attacks', 0)
    reference.step(ui.decision['options'].index('move'))
    controller.key('m', 'm')
    assert ui.decision['kind'] == 'TARGET' and ui.decision['info'].get('action') == 'move'
    x, y = ui.game.combat.position(step[1])
    cell = (x + C.DX[step[0]], y + C.DY[step[0]])
    reference.step(ui.decision['options'].index(cell))
    assert controller.key(ARROWS[C.DX[step[0]], C.DY[step[0]]]) is not False, 'arrow into an enemy did nothing'
    assert state.g.get('combat.attacks', 0) > before, 'moving into an enemy did not attack'


def test(screenshot=False):
    """UI2 requested check: engines=True from boot; every screen choice replays equal."""
    started = time.perf_counter()
    ui, reference = Session(engines=True), Session(engines=True)
    controller, assets = Controller(ui), Assets()
    walker = Walk(json.loads((LOCAL.parent / 'herdr/route/derived.json').read_text()), {})
    fighting, seen, move_attacked = False, set(), False
    try:
        for _ in range(1000):
            decision = ui.decision
            assert decision is not None, ui.result
            assert decision == reference.decision, 'fight decision diverged'
            active = bool(ui.game.s.g.get('combat.active'))
            if fighting and not active:
                break
            fighting |= active
            before = ui.game.s.hash(ui.game.vm)
            frame = render(controller, assets)
            assert before == ui.game.s.hash(ui.game.vm), 'render mutated simulation'
            name = ('combat' if decision['kind'] == 'COMBAT_ACTION' else
                    'target' if active and decision['kind'] == 'TARGET' else
                    ui.game.vm.display.get('kind'))
            if screenshot and name and name not in seen:
                frame.save(LOCAL / ('ui_%s.png' % name.lower()))
            seen.add(name)
            if decision['kind'] == 'COMBAT_ACTION':
                check_active_icon(controller, frame)
                cb = ui.game.combat; actor = cb.chars[decision['info']['actor']]
                steps = cb.move_attacks(actor)
                if steps and not move_attacked:
                    check_move_attack(controller, reference, (steps[0][0], actor)); move_attacked = True
                    continue
            if active:
                answer = fight_answer(ui.game, decision)
            elif decision['kind'] in ('SHOP_MENU', 'CAMP_MENU'):
                answer = decision['options'].index('no' if decision['info'].get('purpose') == 'treasure leave' else 'exit')  # ov07:1251.
            else:
                assert decision['kind'] not in RESOLVED, 'resolver reached engines=True UI'
                answer = walker(decision['kind'], decision['options'], ui.game, **decision['info'])
            press(controller, answer)
            reference.step(answer)
        else:
            raise AssertionError('derived first fight exceeded 1000 screen decisions')
        state = ui.game.s
        assert fighting and {'combat', 'target'} <= seen and move_attacked
        assert state.g.get('combat.attacks', 0) > 0
        assert not state.monsters and not state.party_dead and state.g['87CD'] == 0
        assert ui.game.combat is None and ui.decision == reference.decision
        assert ui.game.trace == reference.game.trace, 'fight decision trace differs'
        assert state.hash(ui.game.vm) == reference.game.s.hash(reference.game.vm)
        assert 'tkinter' not in sys.modules
        print('UI2 first derived fight: %d screen decisions, %d attacks, %d rounds; replay identical (%.2fs)' %
              (len(ui.game.trace), state.g['combat.attacks'], state.g['8DC7'], time.perf_counter() - started))
    finally:
        ui.close()
        reference.close()
