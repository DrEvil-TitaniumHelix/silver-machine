from .faults import BindingRequired


DIRECTIONS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, 0))
COMPASS = ('north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest')
SCAN_CODES = (72, 73, 77, 81, 80, 79, 75, 71)


def direction(state):
    if not 0 <= state.dir < len(DIRECTIONS): raise BindingRequired('movement direction outside native table')
    return DIRECTIONS[state.dir]


def refresh(game, map_view=True):
    s = game.s
    if map_view and s.r0[0xFB] and not s.party_dead and (game.vm.is3d() or s.r0[0x1F7] != 1): s.g['world.automap'] = 0
    game.vm.redraw_view()
    game.vm.display.update(automap=bool(game.s.g.get('world.automap', 0)),
                           map_cursor=not game.vm.is3d() and game.s.r0[0x1F7] == 1)


def prepare_forward(game):
    s = game.s
    s.r1[0x2D5] = 0
    if not game.geo.passage(s, s.x, s.y, s.dir): return
    delta = direction(s)
    for axis, step in zip(('x', 'y'), delta):
        target = getattr(s, axis) + step
        if not 0 <= target <= 15:
            setattr(s, axis, max(0, min(15, target)))
            s.r1[0x2D5] = 1


def dungeon_step(game):
    s, vm = game.s, game.vm
    dx, dy = direction(s)
    vm.queue_sound(10)
    vm.hold(0.05)
    s.x, s.y = s.x + dx, s.y + dy
    s.x = 15 if s.x < 0 else 0 if s.x > 15 else s.x
    s.y = 15 if s.y < 0 else 0 if s.y > 15 else s.y
    s.ahead = game.geo.wall(s, s.x, s.y, s.dir)
    s.attr = game.geo.attr(s, s.x, s.y)
    vm.advance_clock(1, 2 if s.r1[0x2CA] & 1 else 1)


def wilderness_step(game):
    from .rules import _s8
    s = game.s
    delta = direction(s)
    s.r0[0xF0:0xF2] = s.r0[0xC3:0xC5]
    for cell, step, bound in zip((0xC3, 0xC4), delta, (37, 14)):
        s.r0[cell] = max(0, min(bound, _s8(s.r0[cell] + step)))
    game.vm.display['map_cursor'] = True
    game.vm.advance_clock(12, 3)


def resolve(game):
    s, vm = game.s, game.vm
    if s.mode == 4:
        if s.r1[0x2C9] == 255: s.r1[0x2C9] = 0
        else:
            vm.display['view_dirty'] = True
            if game.geo.passage(s, s.x, s.y, s.dir) == 1: dungeon_step(game)
            vm.paint_location()
    elif s.mode == 3:
        if s.r1[0x2C9] != 255:
            wilderness_step(game)
            vm.paint_location()
    else: s.r1[0x2C9] = 0
    vm.display['portrait_animation'] = False
    s.g.setdefault('dkk.runtime', {}).update(picture_name='', picture_id=255)


def main_menu(game):
    from .town import field
    s, vm = game.s, game.vm
    s.r1[0x2C9] = 0
    if s.mode not in (3, 4) or s.mode == 3 and not s.r0[0x1F7]:
        raise BindingRequired('movement menu has an uninitialized native return in this interface')
    while True:
        extended = bool(s.g.get('world.extended', 0))
        overland = s.mode == 3
        if extended:
            options = ('Exit',) + (COMPASS if overland else ('forward', 'turn-left', 'turn-right', 'turn-around')) + ('escape',) + (('step',) if overland else ())
            labels = ('Exit',)
        else:
            labels = ('Move', 'Encamp') if overland else ('Move', 'Area', 'Cast', 'View', 'Encamp', 'Search', 'Look')
            options = labels + ('char-up', 'char-down')
        selected = 0 if extended else s.g.get('world.choice', 1) - 1
        if not 0 <= selected < len(labels): selected = 0
        game.menu_highlight = selected
        pick = game.ask('MENU', options, world_menu=True, extended_mode=extended, overland=overland,
                        start=selected, menu_labels=labels,
                        shortcuts=tuple(label[0].upper() for label in labels), enter_ok=True)
        command = options[pick]
        if not extended:
            s.g['world.choice'] = (pick if pick < len(labels) else game.menu_highlight) + 1
            if command in ('char-up', 'char-down'):
                if not overland and s.chars():
                    from .camp import repaint_walking_row
                    repaint_walking_row(game, s.selc())
                    s.sel = (s.sel + (-1 if command == 'char-up' else 1)) % len(s.chars())
                    repaint_walking_row(game, s.selc())
                    vm.paint_location()
                continue
            if command == 'Move': s.g['world.extended'] = 1
            elif command == 'Encamp': result = 4; break
            elif command == 'Area':
                if s.r0[0xFB] and not getattr(game, 'debug_automap', False):
                    game.ask('ACK', ('Continue',), prompt=game.assets.text('notHere'), color=14)
                else:
                    s.g['world.automap'] = int(not s.g.get('world.automap', 0))
                    refresh(game, False)
            elif command == 'Cast':
                if s.selc() is not None and field(s.selc(), 'status') == 0: vm.interface('magic', 'cast_menu', s.selc())
            elif command == 'View': vm.interface('inventory', 'view', s.selc())
            elif command == 'Search':
                s.r1[0x2CA] ^= 1
                vm.paint_location()
            elif command == 'Look':
                s.r1[0x2CA] |= 2
                vm.paint_location()
                vm.advance_clock(1, 2)
                vm.pc = vm.vec[1]
                result = 6
                break
        elif command == 'Exit': s.g['world.extended'] = 0
        elif overland:
            if command == 'escape': s.g['world.extended'] = 0; result = 27
            elif command == 'step': result = 32
            else:
                s.dir = COMPASS.index(command)
                result = SCAN_CODES[s.dir]
            vm.paint_location()
            break
        elif command == 'escape': s.g['world.extended'] = 0
        elif command == 'forward':
            prepare_forward(game)
            vm.paint_location()
            result = 255
            break
        else:
            s.dir = (s.dir + {'turn-left': 6, 'turn-right': 2, 'turn-around': 4}[command]) % 8
            if command != 'turn-around': vm.queue_sound(10)
            s.ahead = game.geo.wall(s, s.x, s.y, s.dir)
            refresh(game, False)
            vm.paint_location()
    if not vm.bottom_cleared: vm.clear_text(); vm.bottom_cleared = True
    return result


def turn(game):
    from . import town
    s, vm = game.s, game.vm
    selection = main_menu(game)
    s.g['47E7'] = s.sel
    if not s.restart: s.r0[0xF2] = s.block
    while s.r1[0x2CA] > 1 or selection == 4:
        if s.party_dead or s.stop or town.restart_requested(s): return
        if selection == 4: town.camp(game)
        else:
            saved = s.r1[0x2CA] & 1
            s.r1[0x2CA] = 1
            refresh(game)
            vm.run(vm.vec[1])
            if s.restart: town.after_block(game)
            s.r1[0x2CA] = saved
        if s.party_dead or s.stop or town.restart_requested(s): return
        selection = main_menu(game)
        s.g['47E7'] = s.sel
    if s.party_dead or s.stop or town.restart_requested(s): return
    vm.run(vm.vec[0])
    if s.restart: town.after_block(game); return
    if s.party_dead or s.stop or town.restart_requested(s): return
    s.r0[0xF0:0xF2] = [s.x & 255, s.y & 255]
    resolve(game)
    refresh(game)
    if (s.x, s.y) != tuple(s.r0[0xF0:0xF2]): vm.queue_sound(10)
    vm.visual['graphics'] = False
    vm.run(vm.vec[1])
    if s.restart: town.after_block(game)


def test():
    from ._town_test import exploration
    exploration()
