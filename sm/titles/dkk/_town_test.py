from tempfile import TemporaryDirectory
from pathlib import Path
from .menu import Game
from ._creation_test import create_party
from . import town, save_start


class OpeningReached(Exception): pass


class OpeningGame(Game):
    def service(self, game, unit, name, *arguments):
        if unit == 'combat' and name == 'load_monsters':
            raise OpeningReached(arguments)
        return super().service(game, unit, name, *arguments)


def opening(startup=False):
    with TemporaryDirectory(prefix='sm-dkk-opening-') as tmp:
        game = OpeningGame(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        if startup: game.s.dataset = 5
        before = len(game.trace)
        def player(kind, choices, current, **info):
            if kind == 'ACK': return 0
            if info.get('script_continue'): return 0
            if kind == 'MENU' and choices == ('Yes', 'No'): return 1
            raise AssertionError('unexpected opening choice ' + kind)
        game.player = player
        try: town.boot(game)
        except OpeningReached as reached:
            assert (game.s.dataset, game.s.block) == (1, 16)
            assert game.s.code[game.vm.at - 0x8000] == 0x0B
            assert reached.args == ((1, 4, 1),)
            return (game.state_hash(), tuple(game.trace[before:]), reached.args)
        raise AssertionError('opening did not reach the first fight')


def test():
    first, second = opening(), opening(startup=True)
    assert first == second
    assert len(first[1]) == 12
    commands()
    helpers()
    exploration()
    exploration_highlight()
    encounter_review()
    encounter_counters()
    combat_distance()
    continue_escape()
    menu_string_slots()
    variable_operand_order()
    transition_script_id()
    transition_presentation()
    treasure_pool()
    menu_lifetime()
    resource_loading()
    clear_box()
    boot_archive()
    program_lifetime()
    camp_clears_story_text()
    camp_interrupted_redraw()
    party_menu_return_view()
    program_return_display()
    who_selection()
    wrapped_spaces()
    restart_lifecycle()
    vault_loop()
    script_stops()
    held_frames()
    play_continues()
    demo_loop()


def command(game, opcode, *arguments):
    raw = bytearray((opcode,))
    for kind, value in arguments:
        raw.extend((kind, value & 255))
        if kind in (1, 2, 3, 129): raw.append(value >> 8 & 255)
    vm = game.vm
    vm.s.code[:len(raw)] = raw
    vm.pc = vm.at = 0x8000
    vm.fetch()
    getattr(vm, 'op%02X' % opcode)()


def member(active=True, book=False):
    from .records import Character, Spells
    from .rules import character
    result = character(bytes(Character()), spells=bytes(Spells()) if book else None)
    town.put(result, 'active', int(active))
    town.put(result, 'abilities', 10, 11)
    town.put(result, 'move', 12)
    return result


def combat_distance():
    from itertools import product
    from unittest.mock import patch
    for dungeon, stored, limit in product((0, 1), (0, 1, 2, 255), range(3)):
        game = Game(None)
        vm, s = game.vm, game.s
        s.party, s.monsters = [member()], [member()]
        vm.monsters_loaded = 1
        s.x, s.y, s.dir = 5, 5, 0
        s.r0[0xE6], s.r1[0x2C1] = dungeon, stored
        s.g['world.extended'] = 1
        s.g['dkk.runtime'] = dict(picture_name='PIC', picture_id=9, big_id=112)
        game.geo.map = object()
        expected = min(stored, limit) if dungeon else 2
        seen = []
        def service(unit, name):
            assert (unit, name) == ('combat', 'run')
            assert s.r1[0x2C1] == expected and s.g['world.extended'] == 0
            runtime = s.g['dkk.runtime']
            assert (runtime['picture_name'], runtime['picture_id'], runtime['big_id']) == ('', 255, 255)
            seen.append(s.r1[0x2C1])
        with patch.object(vm, 'service', side_effect=service), patch.object(game.geo, 'wall', side_effect=lambda state, x, y, facing: int(y <= 5 - limit)):
            command(game, 0x24)
        assert seen == [expected] and s.g['world.extended'] == 1
    with TemporaryDirectory(prefix='sm-dkk-distance-') as tmp:
        game = Game(None)
        game.roster_directory = Path(tmp)
        create_party(game)
        game.player = lambda kind, choices, host, **info: 1 if choices == ('Yes', 'No') else 0
        original = game.vm.service
        def service(unit, name, *arguments):
            if (unit, name) == ('combat', 'run'):
                assert game.s.r0[0xE6] == 0 and game.s.r1[0x2C1] == 2
                raise OpeningReached()
            return original(unit, name, *arguments)
        with patch.object(game.vm, 'service', side_effect=service):
            try: town.boot(game)
            except OpeningReached: pass
            else: raise AssertionError('opening did not reach combat placement')


def exploration_highlight():
    from unittest.mock import patch
    from . import world_explore as world
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member(), member()]
    s.mode, s.r0[0x1F7] = 4, 1
    actions = iter((('Cast', 0), ('Encamp', 2), ('char-down', 4), ('Encamp', 3)))
    def choose(kind, options, host, **info):
        action, expected = next(actions)
        assert info['start'] == expected and 'selected' not in info
        assert host.menu_highlight == expected
        if action == 'char-down': host.menu_highlight = 3
        return options.index(action)
    game.player = choose
    with patch.object(vm, 'service') as service:
        assert world.main_menu(game) == 4 and s.g['world.choice'] == 5
        service.assert_called_once_with('magic', 'cast_menu', s.party[0])
        game.menu_highlight = 0
        assert world.main_menu(game) == 4 and s.sel == 1
    for mode, saved, extended, expected in ((3, 7, 0, 0), (3, 2, 0, 1), (4, 0, 0, 0), (4, 7, 1, 0)):
        s.mode = mode
        s.g.update({'world.choice': saved, 'world.extended': extended})
        def choose(kind, options, host, **info):
            assert info['start'] == expected
            raise OpeningReached()
        game.player = choose
        try: world.main_menu(game)
        except OpeningReached: pass
        else: raise AssertionError('menu not reached')


def encounter_counters():
    from unittest.mock import patch
    from . import combat
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member()]
    template = member()
    town.put(template, 'undead', 1)
    with patch.object(combat, 'load_creature', return_value=template):
        command(game, 0x0B, (0, 1), (0, 62), (0, 3))
    assert (vm.loaded_monster_count, vm.monsters_loaded, vm.undead_count, vm.icon_slot) == (62, 1, 1, 9)
    assert vm.linked_shown == 1
    s.monsters.pop()
    with patch.object(combat, 'load_creature', return_value=member()):
        command(game, 0x0B, (0, 1), (0, 5), (0, 4))
    assert vm.loaded_monster_count == 63 and len(s.monsters) == 62 and vm.linked_shown == 1
    vm.rows_shown = {0: (5, 3)}; vm.party_drawn()
    assert vm.linked_shown is None and vm.rows_shown is None
    with patch.object(combat, 'load_creature') as load:
        command(game, 0x0B, (0, 1), (0, 1), (0, 4))
        assert not load.called
    s.sel = len(s.chars()) - 1
    creatures, selected = tuple(s.chars()), s.selc()
    icons = list(s.g['dkk.monster_icons'])
    s.g['treasure_active'] = 1
    s.treasure_money[:] = [7] * len(s.treasure_money)
    s.treasure_items.append(bytearray(63))
    command(game, 0x1C)
    assert vm.pc == 0x8001 and (vm.loaded_monster_count, vm.monsters_loaded, vm.undead_count, vm.icon_slot) == (0, 0, 0, 8)
    assert all(a is b for a, b in zip(creatures, s.chars())) and len(s.chars()) == len(creatures)
    assert s.selc() is selected and s.g['dkk.monster_icons'] == icons
    assert not any(s.treasure_money) and not s.treasure_items and s.g['treasure_active'] == 1
    with patch.object(vm, 'service') as service:
        command(game, 0x24)
        service.assert_called_once_with('combat', 'treasure')
    with patch.object(combat, 'load_creature', return_value=member()):
        command(game, 0x0B, (0, 1), (0, 2), (0, 5))
    assert len(s.monsters) == 64 and (vm.loaded_monster_count, vm.monsters_loaded, vm.undead_count, vm.icon_slot) == (2, 1, 0, 9)
    assert s.selc() is selected
    with patch.object(vm, 'service') as service:
        command(game, 0x24)
        service.assert_called_once_with('combat', 'run')
    command(game, 0x1C)
    assert vm.loaded_monster_count == vm.monsters_loaded == vm.undead_count == 0 and s.selc() is selected


def who_selection():
    from itertools import product
    for extended, selected, prompt in product((0, 1, 255), range(3), ('', 'Choose', 'X' * 45)):
        game = Game(None)
        vm, s = game.vm, game.s
        s.party = [member(), member(active=False)]
        s.monsters = [member()]
        for char, name in zip(s.chars(), ('First', 'Second', 'Loaded')):
            char.b[0] = len(name)
            char.b[1:1 + len(name)] = name.encode('ascii')
        s.sel = selected
        s.g.update({'world.extended': extended, 'A4D1': 1, '8B6D': 1, '47E2': 1, '47E7': 1})
        vm.out.append('Old story')
        vm.display = dict(kind='PIC', id=3)
        vm.bottom_cleared = True
        epoch = vm.text_epoch
        vm.setstr(0x7A20, prompt)
        seen = []
        def choose(kind, options, host, **info):
            assert kind == 'WHO' and tuple(options) == ('First', 'Second', 'Loaded')
            assert s.g['world.extended'] == s.g['A4D1'] == s.g['8B6D'] == 0
            assert s.sel == selected and vm.text_start == len(vm.out)
            assert info['prompt'] == prompt[:40] and info['at'] == 0x8000
            seen.append(info)
            return (selected + 1) % 3
        game.player = choose
        command(game, 0x39, (129, 0x7A20))
        assert vm.pc == 0x8004 and s.sel == (selected + 1) % 3
        assert s.g['world.extended'] == extended and vm.text_epoch == epoch + 1
        assert (s.g['47E2'], s.g['47E7']) == (1, 1)
        assert vm.display == dict(kind='PIC', id=3) and vm.bottom_cleared
        s.sel = selected
        s.g['A4D1'] = s.g['8B6D'] = 1
        command(game, 0x39, (0, 99))
        assert vm.pc == 0x8003 and len(seen) == 2
        assert vm.strs[1] == prompt and s.sel == (selected + 1) % 3
        assert s.g['world.extended'] == extended and vm.text_epoch == epoch + 2


def commands():
    from .records import Item
    from .faults import BindingRequired
    game = Game(None)
    vm, s = game.vm, game.s
    for answer, expected in ((' Mixed Case  ', ' MIXED CASE  '), ('', ' '), ('x' * 45, 'X' * 40)):
        vm.ask = lambda *args, **kwargs: answer
        command(game, 0x10, (0, 0), (2, 0x7A00))
        assert vm.getstr(0x7A00) == expected
    for opcode, left, right, result in ((0x2F, 0x1234, 0xFFFF, 52), (0x30, 0x1200, 0x3400, 0)):
        vm.setmem(0x7A10, 0xFFFF, 3)
        command(game, opcode, (2, left), (2, right), (3, 0x7A10))
        assert vm.getmem(0x7A10, 3) == result
        assert vm.flags == ([1, 0, 0, 0, 1, 1] if not result else [0, 1, 1, 0, 1, 0])
    vm.setstr(0x7A20, 'SAME')
    vm.setstr(0x7A30, 'SAME')
    vm.setstr(0x7A40, 'DIFFERENT')
    command(game, 0x14, (129, 0x7A20), (129, 0x7A30), (0, 2), (0, 2))
    assert vm.flags == [1, 0, 0, 0, 0, 0]
    command(game, 0x14, (0, 2), (0, 2), (129, 0x7A20), (129, 0x7A40))
    assert vm.flags == [0, 1, 0, 0, 0, 0]
    prompts = []
    def answer(kind, choices, **info):
        prompts.append((kind, choices, info))
        return 1
    vm.ask = answer
    vm.setstr(0x7A50, 'Choose a path')
    vm.setstr(0x7A70, 'Alpha')
    vm.setstr(0x7A80, 'Beta')
    vm.out = ['Existing story.']
    vm.text_start = 0
    command(game, 0x15, (3, 0x7A00), (129, 0x7A50), (0, 2), (129, 0x7A70), (129, 0x7A80))
    assert prompts[-1][1] == ('Alpha', 'Beta') and prompts[-1][2]['prompt'] == 'Choose a path'
    assert vm.strs[1:3] == ['Alpha', 'Beta'] and vm.getmem(0x7A00, 3) == 1
    vm.out.append('Retain this message.')
    start = vm.text_start
    command(game, 0x2B, (3, 0x7A00), (0, 2), (129, 0x7A70), (129, 0x7A80))
    assert vm.text_start == start
    command(game, 0x31, (3, 0x7A00), (0, 2), (129, 0x7A70), (129, 0x7A80))
    assert vm.out[-1] == game.assets.text('whatDoYouDoText') and vm.text_start == start
    command(game, 0x1F, (2, 0x101))
    assert vm.out[-1] == game.assets.text('journalEntryPrefix') + '1.' and vm.text_color == 10
    s.party = [member(), member(False, True)]
    s.monsters = [member(True, True)]
    town.put(s.monsters[0], 'memorized', 42, 73)
    town.put(s.party[1], 'memorized', 42, 0)
    command(game, 0x3B, (0, 42), (3, 0x7A00), (3, 0x7A02))
    assert (vm.getmem(0x7A00, 3), vm.getmem(0x7A02, 3)) == (73, 2)
    command(game, 0x3B, (0, 99), (3, 0x7A00), (3, 0x7A02))
    assert (vm.getmem(0x7A00, 3), vm.getmem(0x7A02, 3)) == (255, 2)
    town.put(s.monsters[0], 'abilities', 25, 11)
    outputs = tuple((3, 0x7A00 + i * 2) for i in range(4))
    command(game, 0x1E, (1, 0x7C19), (0, 0), *outputs)
    assert [vm.getmem(address, kind) for kind, address in outputs] == [10, 25, 15, 0]
    s.monsters[0].effects.append(bytearray((39, 0, 0, 0, 0, 0, 0, 0, 0)))
    command(game, 0x1E, (0, 0), (0, 39), *outputs)
    assert [vm.getmem(address, kind) for kind, address in outputs] == [0, 0, 0, 1]
    command(game, 0x1E, (2, 0x7C72), (0, 0), *outputs)
    assert [vm.getmem(address, kind) for kind, address in outputs] == [0, 0, 0, 1]
    s.sel = 2
    command(game, 0x3F, (0, 39))
    assert vm.flags == [1, 0, 0, 0, 0, 0]
    s.sel = 0
    command(game, 0x3F, (0, 39))
    assert vm.flags == [0, 1, 0, 0, 0, 0]
    item = Item()
    item.set('type', 1)
    item.set('readied', 1)
    s.monsters[0].items = [item.data]
    command(game, 0x32, (0, 1))
    assert vm.flags[0] == 1
    pool = save_start.item_pool(vm.host)
    kept, pool.slots = pool.slots, (item.data,)
    command(game, 0x40, (0, 1))
    assert not s.monsters[0].items and not item.get('readied') and s.sel == 0
    assert not item.get('type')
    pool.slots = kept
    for index, char in enumerate(s.chars()): town.put(char, 'order', index)
    vm.icons = {index: ('CPIC', index, 1) for index in range(3)}
    vm.set1(0x7F3E, 2)
    s.sel, s.g['47E7'], vm.roster_shown = 1, 1, 0
    command(game, 0x3E)
    assert s.sel == s.g['47E7'] == 0 and len(s.party) == 1 and 1 not in vm.icons and vm.roster_shown is None
    command(game, 0x0A, (0, 127))
    assert vm.getmem(0x7D00) == 1 and s.g['A4D1'] == 1 and s.sel == 0
    command(game, 0x0A, (0, 0))
    assert vm.getmem(0x7D00) == 1
    command(game, 0x2C, (0, 0))
    assert not hasattr(game, 'script_sounds')
    command(game, 0x2C, (0, 1))
    assert game.script_sounds == [game.assets.table('soundCueTable')[0]]
    command(game, 0x2C, (0, 130))
    assert game.script_music == [2]
    vm.setmem(0x3DE, 10)
    command(game, 0x2D, (2, 0xB203))
    assert game.script_sounds[-1] == 10
    command(game, 0x2D, (2, 0x1234))
    holds = []
    vm.hold = holds.append
    command(game, 0x3A)
    assert holds == [0.6]
    calls = []
    vm.service = lambda *args: calls.append(args)
    command(game, 0x3C, (0, 0))
    assert calls[-1] == ('shop', 'run') and len(s.treasure_items) == 15
    assert all(not (raw[Item.FIELDS['unidentified'][0]] & 7) for raw in s.treasure_items)
    original_stock = list(s.treasure_items)
    try: command(game, 0x3C, (0, 8))
    except BindingRequired: pass
    else: raise AssertionError('unverified stock overrun was accepted')
    assert s.treasure_items == original_stock
    vm.set0(0x4D00, 2)
    vm.set1(0x7F6C, 1)
    s.monsters = []
    command(game, 0x24)
    assert calls[-1] == ('shop', 'run') and vm.m0(0x4D00) == 2
    painted, was3d, waspaint = [], vm.is3d, vm.paint_location
    vm.paint_location = lambda *a, **k: painted.append(1)
    for dungeon, temple in ((False, 0), (False, 1), (True, 0), (True, 1)):
        vm.is3d = lambda dungeon=dungeon: dungeon
        vm.set1(0x7EE2 if temple else 0x7F6C, 1)
        painted.clear(); command(game, 0x24)
        assert calls[-1] == ('temple' if temple else 'shop', 'run') and len(painted) == dungeon
    vm.is3d, vm.paint_location = was3d, waspaint
    vm.gosub = []
    command(game, 0x13)
    assert vm.pc == 0x8002 and s.stop


def helpers():
    from unittest.mock import patch
    from .records import Item
    from .faults import BindingRequired
    from . import ecl, inventory
    game = Game(None)
    vm, s = game.vm, game.s
    s.party = [member(), member()]
    for index, char in enumerate(s.party):
        vm.s.sel = index
        vm.setstr(0x7C00, 'TEST%d' % index)
    s.sel = 0
    for address in (0x4BE9, 0x4CF7, 0x7C71, 0x7A00, 0x9000):
        vm.setstr(address, 'TEXT')
        assert vm.getstr(address) == 'TEXT'
    assert vm.getstr(0x1234) == ''
    c = s.party[0]
    town.put(c, 'dimensions', 2)
    assert vm.getmem(0x7C00) == ord('T') + ord('E') * 256
    town.put(c, 'dimensions', 0)
    assert vm.getmem(0x7C00) == 0
    town.put(c, 'dimensions', 3)
    try: vm.getmem(0x7C00)
    except BindingRequired: pass
    else: raise AssertionError('word overflow accepted')
    town.put(c, 'levels', 5, 1)
    assert vm.getmem(0x7CEB) == 0
    town.put(c, 'levels', 2, 5)
    assert vm.getmem(0x7CEB) == 1
    town.put(c, 'active', 0)
    assert vm.getmem(0x7D00) == 128
    town.put(c, 'active', 1)
    s.g['A4D1'] = 1
    assert vm.getmem(0x7D00) == 1
    vm.setmem(0x7C00, 7)
    assert s.g['A4B7'] == 1
    vm.setmem(0x7D00, 1)
    assert not s.g.get('A4B6')
    vm.setmem(0x7D0C, 129)
    assert town.field(c, 'side') == town.field(c, 'auto_combat') == 1
    vm.setmem(0x7CC4, 0x1234, 3)
    assert vm.getmem(0x7CC3) == vm.getmem(0x7CC4) == 0x1234
    vm.high_bytes = []
    vm.load_values([(2, 0, 0x7A, None)])
    assert vm.load_values([(0, 12, 0, None)])[0][2] == 0x7A
    skipped = {1: (1, 2, 10, 14, 17, 18, 31, 32, 44, 45, 50, 52, 54, 56, 57, 60, 63, 64),
               2: (3, 8, 9, 15, 16, 65), 3: (4, 5, 6, 7, 11, 12, 33, 40, 42, 47, 48, 53, 55, 59),
               4: (20,), 5: (46,), 6: (30,)}
    assert all(ecl.SKIPCOUNT.get(opcode, 0) == next((n for n, group in skipped.items() if opcode in group), 0)
               for opcode in range(66))
    old = [(2, 1, 2, None)]
    vm.ops = old
    vm.cur, vm.next = 0x16, 0x8000
    vm.flags = [0] * 6
    s.code[0] = 0x15
    vm.op16()
    assert vm.pc == 0x8001 and vm.ops is old
    s.dataset = 5
    vm.load_block(16)
    assert bytes(s.code[:20]) == game.assets.records('ECL1')[16][2:22]
    s.r0[0x100], s.r1[0x379] = 77, 88
    vm.icon_slot, vm.breath_aim = 44, 19
    vm.visual.update(graphics=True, monster_picture=True, protection=True, wall_color=0)
    vm.resuming = True
    vm.init_vm()
    assert vm.pc == 0x8014 and vm.icon_slot == 8 and vm.breath_aim == 0
    assert vm.visual['wall_color'] == 65 and vm.visual['ceiling_color'] == 9 and vm.visual['colors']
    assert not vm.visual['monster_picture'] and not vm.visual['graphics'] and not vm.visual['protection']
    assert (s.r0[0x100], s.r1[0x379]) == (77, 88)
    vm.resuming = False
    vm.init_vm()
    assert s.r0[0x100] == s.r1[0x379] == 0
    s.dataset = 1
    vm.geo.attr = lambda *args: 17
    vm.geo.wall = lambda *args: 3
    geo = town.Geo()
    geo.map = object()
    walls = []
    def wall(state, x, y, facing):
        walls.append((x, y))
        return 0
    geo.wall = wall
    s.x, s.y, s.dir, s.r0[0xE6] = 0, 0, 0, 1
    assert geo.approach(s) == 2 and walls == [(0, 0), (0, -1)]
    s.r0[0xE6] = 0
    assert geo.approach(s) == s.r1[0x2C1] == 2
    vm.setmem(0xC059, 0x1234)
    vm.setmem(0xC05F, 0x1256)
    vm.update_display()
    assert vm.display['wall_color'] == 52 and vm.display['ceiling_color'] == 86
    assert s.attr == 17 and s.ahead == 3
    s.ahead = 99
    vm.update_display()
    assert s.ahead == 99
    command(game, 0x0E, (0, 2))
    assert vm.visual['graphics'] and vm.visual['monster_picture']
    command(game, 0x2D, (2, 0x2DCB))
    assert vm.display['kind'] is None and not vm.visual['graphics'] and s.ahead == 3
    for direction, x, y, expected in ((0, 2, 0, (2, 15)), (2, 15, 3, (0, 3)), (4, 5, 15, (5, 0)),
                                      (6, 0, 7, (15, 7)), (0, 2, -2, (2, 15)), (2, -2, 3, (-1, 3)), (1, 2, 3, (2, 3))):
        s.dir, s.x, s.y = direction, x, y
        vm.step()
        assert (s.x, s.y) == expected and vm.visual['moved']
        vm.update_display()
        assert vm.display['location'] == (*expected, direction)
    s.mode, s.prev_mode, s.r0[0xE6] = 4, 4, 1
    vm.geo.approach = lambda state: 2
    command(game, 0x0C, (0, 1), (0, 2), (0, 2), (0, 0))
    assert vm.display['kind'] == 'SPRIT' and vm.display['head'] == 255 and vm.visual['sprite']
    command(game, 0x0D)
    assert vm.display['frame'] == 1
    command(game, 0x0D)
    assert vm.display['kind'] == 'PIC' and vm.visual['monster_picture']
    command(game, 0x0E, (0, 255))
    assert vm.display['kind'] is None and not vm.visual['monster_picture']
    assert town.script_menu(('ABC123', '1ABC', 'B~ETA')) == ('AbcQRS 1abc BEta', ('A', '1', 'B', 'E'), ('AbcQRS', '1abc', 'B', 'Eta'))
    assert len(town.script_menu(('A' * 60, 'B'))[0]) == 49
    s.r0[0x1F7] = 1
    vm.setstr(0x7A10, 'ALPHA')
    vm.setstr(0x7A20, 'BETA')
    choices = iter((3, 1))
    seen = []
    def menu(kind, options, **info):
        seen.append((options, info))
        return next(choices)
    vm.ask = menu
    command(game, 0x2B, (3, 0x7A00), (0, 2), (129, 0x7A10), (129, 0x7A20))
    assert seen[-1][0] == ('Alpha', 'Beta', 'char-up', 'char-down')
    assert s.sel == 1 and vm.getmem(0x7A00, 3) == 1
    assert seen[-1][1]['shortcuts'] == ('A', 'B') and not seen[-1][1]['enter_ok']
    s.monsters = [member()]
    choices = iter((3, 1))
    command(game, 0x2B, (3, 0x7A00), (0, 2), (129, 0x7A10), (129, 0x7A20))
    assert s.sel == 2
    s.monsters, s.sel = [], 1
    for char in s.party:
        for i, value in enumerate((101, 9, 3)): town.put(char, 'money', value, i * 2, width=2)
    weights = (25, 1, 256, 1)
    c = s.party[0]
    c.items = []
    for weight in weights:
        item = Item()
        item.set('type', 1)
        item.set('weight', weight)
        item.set('readied', 1)
        c.items.append(item.data)
    before = list(c.items)
    s.seed = 4660
    pool = save_start.item_pool(vm.host)
    kept, pool.slots = pool.slots, tuple(before)
    with patch.object(inventory, 'toggle_ready', wraps=inventory.toggle_ready) as ready:
        command(game, 0x28, (0, 1), (0, 50), (0, 255))
    assert all(call.args[1] is s.party[1] for call in ready.call_args_list)
    assert [[town.field(char, 'money', i * 2, width=2) for i in range(3)] for char in s.party] == [[50, 4, 1]] * 2
    assert not c.items and all(not item[inventory.I['readied']] for item in before)
    assert all(not item[inventory.I['type']] for item in before)
    pool.slots = kept
    assert len(game.combat_log) == 4 and s.sel == 1
    untouched = bytes(s.party[0].b)
    try: command(game, 0x28, (0, 1), (0, 27), (0, 0))
    except BindingRequired: pass
    else: raise AssertionError('unverified Real rounding accepted')
    assert bytes(s.party[0].b) == untouched


def exploration():
    from unittest.mock import patch
    from . import world_explore as world, camp, rules
    from .faults import BindingRequired
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member(), member()]
    s.monsters = [member()]
    vm.vec = [0x8100, 0x8200, 0x8300, 0x8400, 0x8500]
    game.geo.wall = lambda *args: 9
    game.geo.attr = lambda *args: 37
    game.geo.passage = lambda *args: 1
    s.x, s.y, s.dir = 15, 6, 2
    world.prepare_forward(game)
    assert (s.x, s.y, s.r1[0x2D5]) == (15, 6, 1)
    game.geo.passage = lambda *args: 0
    world.prepare_forward(game)
    assert s.r1[0x2D5] == 0
    for barrier in (0, 1, 2, 3):
        game.geo.passage = lambda *args, value=barrier: value
        s.x, s.y, s.dir, s.mode, s.r1[0x2C9] = 15, 6, 2, 4, 0
        with patch.object(vm, 'advance_clock') as advance, patch.object(vm, 'hold') as hold:
            world.resolve(game)
            assert s.x == (0 if barrier == 1 else 15)
            assert advance.call_count == hold.call_count == int(barrier == 1)
            if barrier == 1:
                advance.assert_called_once_with(1, 1)
                hold.assert_called_once_with(0.05)
                assert (s.ahead, s.attr) == (9, 37)
    game.geo.passage = lambda *args: 1
    s.x, s.y, s.dir, s.r1[0x2CA] = 15, 0, 1, 1
    with patch.object(vm, 'advance_clock') as advance, patch.object(vm, 'hold'):
        world.resolve(game)
        assert (s.x, s.y) == (0, 15)
        advance.assert_called_once_with(1, 2)
    for mode, remaining in ((3, 255), (4, 0), (2, 0)):
        s.mode, s.r1[0x2C9] = mode, 255
        with patch.object(vm, 'advance_clock') as advance:
            world.resolve(game)
            assert s.r1[0x2C9] == remaining and not advance.called
            assert vm.display['portrait_animation'] is False
    s.mode, s.r1[0x2C9], s.dir = 3, 0, 1
    s.r0[0xC3:0xC5] = [37, 0]
    with patch.object(vm, 'advance_clock') as advance:
        world.resolve(game)
        assert s.r0[0xC3:0xC5] == [37, 0] and s.r0[0xF0:0xF2] == [37, 0]
        advance.assert_called_once_with(12, 3)
    s.r0[0xC3:0xC5], s.dir = [255, 128], 2
    with patch.object(vm, 'advance_clock'):
        s.g.setdefault('dkk.runtime', {}).update(picture_name='PIC', picture_id=93)
        world.resolve(game)
        assert s.r0[0xC3:0xC5] == [0, 0] and s.g['dkk.runtime']['picture_id'] == 255
    for facing, (dx, dy) in enumerate(world.DIRECTIONS[:8]):
        s.r0[0xC3:0xC5], s.dir = [8, 8], facing
        with patch.object(vm, 'advance_clock'):
            world.resolve(game)
        assert s.r0[0xC3:0xC5] == [8 + dx, 8 + dy]
    seen = []
    def choices(commands):
        stream = iter(commands)
        def player(kind, options, current, **info):
            chosen = next(stream)
            seen.append((chosen, dict(info), s.sel, s.r1[0x2CA]))
            return options.index(chosen)
        game.player = player
    s.mode, s.dir, s.sel = 4, 0, 0
    s.r1[0x2CA], s.r1[0x2C9], s.r0[0xFB] = 4, 255, 0
    s.g['world.extended'] = 0
    game.script_sounds = []
    choices(('Search', 'char-up', 'Area', 'Move', 'turn-left', 'turn-right', 'turn-around', 'forward'))
    assert world.main_menu(game) == 255
    assert s.r1[0x2C9] == 0 and s.r1[0x2CA] == 5 and s.sel == 2
    assert s.dir == 4 and game.script_sounds == [10, 10]
    assert s.g['world.automap'] == 1 and seen[-1][1]['extended_mode']
    assert not seen[0][1]['extended_mode']
    choices(('escape', 'Encamp'))
    assert world.main_menu(game) == 4 and s.g['world.extended'] == 0
    s.r0[0xFB] = 1
    choices(('Area', 'Continue', 'Encamp'))
    assert world.main_menu(game) == 4
    assert seen[-2][1]['color'] == 14 and s.g['world.automap'] == 1
    s.g['world.extended'] = 1
    choices(('turn-left', 'Exit', 'Encamp'))
    world.main_menu(game)
    assert s.g['world.automap'] == 1 and vm.display['automap']
    s.r0[0xE6] = 1
    world.refresh(game)
    assert s.g['world.automap'] == 0 and not vm.display['automap']
    s.g['world.automap'], s.r0[0xE6], s.r0[0x1F7] = 1, 0, 1
    world.refresh(game)
    assert s.g['world.automap'] == 1
    s.r0[0x1F7], s.dir = 0, 0
    world.refresh(game)
    assert s.g['world.automap'] == 0
    s.sel = 0
    town.put(s.party[0], 'status', 4)
    choices(('Cast', 'View', 'Encamp'))
    with patch.object(vm, 'service') as service:
        assert world.main_menu(game) == 4
        service.assert_called_once_with('inventory', 'view', s.party[0])
    town.put(s.party[0], 'status', 0)
    choices(('Cast', 'Encamp'))
    with patch.object(vm, 'service') as service:
        assert world.main_menu(game) == 4
        service.assert_called_once_with('magic', 'cast_menu', s.party[0])
    s.r1[0x2CA] = 4
    choices(('Look',))
    with patch.object(vm, 'advance_clock') as advance:
        assert world.main_menu(game) == 6
        assert s.r1[0x2CA] == 6 and vm.pc == vm.vec[1]
        advance.assert_called_once_with(1, 2)
    s.mode, s.r0[0x1F7], s.dir, s.sel = 3, 1, 6, 0
    choices(('char-up', 'Move', 'escape'))
    assert world.main_menu(game) == 27 and s.dir == 6 and s.sel == 0
    assert s.g['world.extended'] == 0
    for heading in range(8):
        choices(('Move', world.COMPASS[heading]) if not s.g['world.extended'] else (world.COMPASS[heading],))
        assert world.main_menu(game) == world.SCAN_CODES[heading] and s.dir == heading
    s.r0[0x1F7] = 0
    try: world.main_menu(game)
    except BindingRequired: pass
    else: raise AssertionError('uninitialized native choice accepted')
    s.mode, s.x, s.y, s.dir, s.r1[0x2CA], s.sel = 4, 4, 4, 0, 1, 0
    s.g['world.extended'] = 0
    choices(('Look', 'Move', 'forward'))
    calls = []
    def script(address): calls.append((address, s.x, s.y, s.r1[0x2CA]))
    with patch.object(vm, 'run', side_effect=script), patch.object(vm, 'advance_clock'), patch.object(vm, 'hold'):
        world.turn(game)
    assert calls == [(0x8200, 4, 4, 1), (0x8100, 4, 4, 1), (0x8200, 4, 3, 1)]
    assert s.r0[0xF0:0xF2] == [4, 4]
    game.script_sounds = []
    game.geo.passage = lambda *args: 2
    choices(('forward',))
    calls.clear()
    with patch.object(vm, 'run', side_effect=script), patch.object(vm, 'advance_clock') as advance:
        world.turn(game)
        assert not advance.called
    assert [entry[0] for entry in calls] == [0x8100, 0x8200]
    assert not game.script_sounds
    for interrupted in (False, True):
        calls.clear()
        s.g['save.recent'] = 1
        def camp_script(address):
            assert s.g['save.recent'] == 1
            calls.append(address)
        with patch.object(town, 'service', return_value=interrupted), patch.object(vm, 'run', side_effect=camp_script):
            town.camp(game)
        assert calls == ([0x8300, 0x8400] if interrupted else [0x8300])
        assert s.g['save.recent'] == 0
    with patch.object(camp, 'advance') as advance:
        vm.advance_clock(257, 2)
        advance.assert_called_once_with(game, 1, 2)
    s.r1[0x372] = 7
    with patch.object(rules, 'recalc_stats') as recalc:
        command(game, 0x40, (0, 1))
    assert len(recalc.call_args_list) == len(s.chars())
    assert all(call.args[1] == 7 for call in recalc.call_args_list)


def encounter_review():
    from unittest.mock import patch
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member()]
    s.monsters = [member()]
    vm.encounter_picture = (255, 2)
    s.r1[0x2C1] = 0
    vm.display = dict(kind='PIC', id=2, frame=3)
    before = dict(vm.display)
    with patch.object(vm, 'show_monster') as display:
        command(game, 0x0D)
        assert not display.called and vm.display == before
        s.r1[0x2C1] = 1
        command(game, 0x0D)
        display.assert_called_once_with()
    s.monsters = []
    s.g['world.extended'] = 1
    vm.visual.update(graphics=True, monster_picture=True, monster_sprite=True, sprite=True)
    def service(*args): assert s.g['world.extended'] == 0
    with patch.object(vm, 'service', side_effect=service) as provider:
        command(game, 0x24)
        provider.assert_called_once_with('combat', 'treasure')
    assert all(not vm.visual[k] for k in ('graphics', 'monster_picture', 'monster_sprite'))
    assert vm.visual['sprite'] and s.g['world.extended'] == 1
    vm.show_monster()
    assert vm.display['id'] == 2 and vm.visual['monster_picture']
    s.monsters = [member()]
    s.r0[0x1F7], s.sel = 1, 0
    picks = iter((1, 2, 0))
    seen = []
    def choose(kind, options, **info):
        seen.append((kind, options, info))
        return next(picks)
    vm.ask = choose
    vm.out.append('Keep this story')
    start = vm.text_start
    command(game, 0x1D)
    assert s.sel == 0 and vm.text_start == start
    assert len(seen) == 3 and seen[0][0] == 'MENU'
    assert seen[0][1][1:] == ('char-up', 'char-down', 'escape')
    assert seen[0][2]['shortcuts'] == ('P',) and seen[0][2]['enter_ok'] and seen[0][2]['animate']
    assert vm.display['bottom_line_cleared']
    s.mode = 3
    picks = iter((1,))
    command(game, 0x1F, (2, 257))
    assert seen[-1][1][-1] == 'escape' and len(seen[-1][1]) == 2
    assert vm.out[-1].endswith('1.') and vm.text_color == 10


def continue_escape():
    from itertools import product
    for opcode, mode, wild in product((0x1D, 0x1F), (3, 4), (0, 1)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party, s.monsters = [member(), member()], [member()]
        s.mode, s.r0[0x1F7], s.sel = mode, wild, 0
        roster = mode != 3 and wild == 1
        actions = iter(('escape', 'char-up', 'char-down', 'escape', 0) if roster else ('escape',))
        selected = []
        def choose(kind, options, **info):
            selected.append(s.sel)
            assert not vm.display['bottom_line_cleared']
            action = next(actions)
            return action if isinstance(action, int) else options.index(action)
        vm.ask = choose
        vm.out.append('Preserved text')
        start = vm.text_start
        command(game, opcode, *((0, 7),) if opcode == 0x1F else ())
        assert selected == ([0, 0, 2, 0, 0] if roster else [0])
        assert s.sel == 0 and vm.display['bottom_line_cleared']
        if opcode == 0x1D: assert vm.text_start == start and vm.out[-1] == 'Preserved text'
        else: assert vm.text_start == start + 1 and vm.out[-1].endswith('7.')


def menu_string_slots():
    from itertools import product
    from .faults import BindingRequired
    for opcode, kind, position in product((0x15, 0x2B, 0x31), (0, 1, 2, 3), range(3)):
        game = Game(None)
        vm, s = game.vm, game.s
        s.mode, s.r0[0x1F7] = 3, 0
        for address, text in ((0x7A20, 'Alpha'), (0x7A30, 'Beta'), (0x7A40, 'Gamma'),
                              (0x7A50, 'Prompt'), (0x7A60, 'Delta'), (0x7A70, 'Echo'),
                              (0x7A80, 'Wrong')):
            vm.setstr(address, text)
        seen = []
        def choose(menu_kind, options, **info):
            seen.append((options, info))
            return 2
        vm.ask = choose
        prefix = ((3, 0x7A00),) + (((129, 0x7A50),) if opcode == 0x15 else ()) + ((0, 3),)
        command(game, opcode, *prefix, (129, 0x7A20), (129, 0x7A30), (129, 0x7A40))
        assert vm.strs[1:4] == ['Alpha', 'Beta', 'Gamma']
        tail = [(129, 0x7A60), (129, 0x7A70)]
        tail.insert(position, (kind, 0x7A80 if kind else 128))
        vm.out.append('Keep the story')
        start = vm.text_start
        command(game, opcode, *prefix, *tail)
        assert seen[-1][0] == ('Delta', 'Echo', 'Gamma')
        assert vm.strs[1:4] == ['Delta', 'Echo', 'Gamma']
        assert vm.getmem(0x7A00, 3) == 2
        if opcode == 0x15:
            assert seen[-1][1]['prompt'] == 'Prompt' and vm.text_start == len(vm.out)
        else:
            assert vm.text_start == start and seen[-1][1]['shortcuts'] == ('D', 'E', 'G')
        command(game, opcode, *prefix, (0, 1), (0, 2), (0, 3))
        assert seen[-1][0] == (('Prompt', 'Echo', 'Gamma') if opcode == 0x15 else ('Delta', 'Echo', 'Gamma'))
    game = Game(None)
    vm = game.vm
    seen = []
    vm.ask = lambda kind, options, **info: seen.append(options) or 9
    entries = []
    for index in range(10):
        address = 0x7A20 + index * 16
        vm.setstr(address, 'Choice' + chr(65 + index))
        entries.append((129, address))
    command(game, 0x15, (3, 0x7A00), (0, 0), (0, 10), *entries)
    command(game, 0x15, (3, 0x7A00), (0, 0), (0, 10), *[(0, index) for index in range(10)])
    assert seen[0] == seen[1] == tuple('Choice' + chr(65 + index) for index in range(10))
    assert vm.getmem(0x7A00, 3) == 9
    for count in (10, 11):
        game = Game(None)
        game.vm.ask = lambda *args, **info: (_ for _ in ()).throw(AssertionError('unverified string slots displayed'))
        try: command(game, 0x15, (3, 0x7A00), (0, 0), (0, count), *[(0, index) for index in range(count)])
        except BindingRequired: pass
        else: raise AssertionError('unverified string slots accepted')


def variable_operand_order():
    from unittest.mock import patch
    for opcode in (0x15, 0x25, 0x26, 0x27, 0x2B, 0x31):
        game = Game(None)
        s, vm = game.s, game.vm
        s.mode = 3
        vm.setmem(0x7A00, 2)
        vm.setstr(0x7A20, 'Alpha')
        vm.setstr(0x7A30, 'Beta')
        vm.load_values([(2, 0, 0x7A, None)] * 4)
        seen = []
        vm.ask = lambda kind, options, **info: seen.append((options, info)) or 1
        if opcode in (0x15, 0x2B, 0x31):
            header = ((3, 0x7A10),) + (((0, 0),) if opcode == 0x15 else ()) + ((128, 0),)
            command(game, opcode, *header, (129, 0x7A20), (129, 0x7A30))
            assert seen[0][0] == ('Alpha', 'Beta')
            assert vm.getmem(0x7A10, 3) == 1
            assert vm.pc == vm.next == 0x8000 + (14 if opcode == 0x15 else 12)
        elif opcode in (0x25, 0x26):
            command(game, opcode, (0, 1), (128, 0), (2, 0x8123), (2, 0x8456))
            assert vm.pc == 0x8456 and vm.next == 0x800B
            assert vm.gosub == ([0x800B] if opcode == 0x26 else [])
        else:
            command(game, opcode, (0, 11), (0, 12), (0, 13), (128, 0), (0, 1), (0, 2))
            assert s.treasure_money[4:] == [11, 12, 13]
            assert len(s.treasure_items) == 2 and vm.pc == vm.next == 0x800D
    game = Game(None)
    s, vm = game.s, game.vm
    vm.setstr(0x7A20, 'Tail')
    original = vm.getstr
    observed = []
    def read(address):
        observed.append(tuple(s.treasure_money[4:]))
        return original(address)
    with patch.object(vm, 'getstr', side_effect=read):
        command(game, 0x27, (0, 11), (0, 12), (0, 13), (0, 1), (129, 0x7A20))
    assert observed == [(11, 12, 13)]
    for opcode in (0x25, 0x26):
        for choice in (0, 1, 2, 257):
            game = Game(None)
            vm = game.vm
            command(game, opcode, (2, choice), (2, 258), (2, 0x8123), (0, 0x56))
            expected = (0x8123, 0x0156, 0x800C)[min(choice & 255, 2)]
            assert vm.pc == expected and vm.next == 0x800C
            assert vm.gosub == ([0x800C] if opcode == 0x26 and choice & 255 < 2 else [])


def transition_script_id():
    from unittest.mock import patch
    for restart_at in (None, 4, 0, 1):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member(), member(), member()]
        s.block, s.r0[0xF2], s.sel = 16, 77, 0
        s.mode, s.prev_mode = 4, 3
        vm.vec = [0x8100, 0x8200, 0x8300, 0x8400, 0x8500]
        vm.files_loaded = True
        entries, retried = [], False
        def run(address):
            nonlocal retried
            vector = vm.vec.index(address)
            if vector == 4:
                assert vm.display['portrait_animation'] is False
                assert s.g['dkk.runtime']['saved_picture_id'] == 255
            vm.display['portrait_animation'] = True
            s.g['dkk.runtime']['saved_picture_id'] = 21
            entries.append((vector, s.block, s.r0[0xF2], s.sel))
            s.r0[0xF2] = 91 + vector
            s.sel = (s.sel + 1) % 3
            if vector == restart_at and not retried:
                s.block, s.restart, retried = 20, 1, True
        with patch.object(vm, 'run', side_effect=run):
            town.after_block(game)
        prefix = [] if restart_at is None else [(4, 16, 77, 0)]
        if restart_at in (0, 1): prefix.append((0, 16, 16, 1))
        if restart_at == 1: prefix.append((1, 16, 91, 2))
        initial = len(prefix) % 3
        block = 16 if restart_at is None else 20
        saved = 77 if restart_at is None else 91 + restart_at
        assert entries == prefix + [(4, block, saved, initial), (0, block, block, (initial + 1) % 3),
                                    (1, block, 91, (initial + 2) % 3)]
        assert s.r0[0xF2] == 92 and s.sel == initial and s.prev_mode == 4
        assert vm.portrait_clear_epoch == 1 + (restart_at is not None)
        assert vm.map_view_epoch == 1 + (restart_at in (0, 1))
        assert vm.display['portrait_animation'] and s.g['dkk.runtime']['saved_picture_id'] == 21


def transition_presentation():
    from itertools import product
    from unittest.mock import patch
    from . import world_explore
    for previous, current, loaded, defeated in product((3, 4, 7), (3, 4, 7), (False, True), (0, 1)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member()]
        s.block, s.mode, s.prev_mode, s.party_dead = 16, previous, previous, defeated
        s.ahead, s.r1[0x2D5] = 55, 1
        vm.vec = [0, 1, 2, 3, 4]
        vm.display.update(kind='PIC', id=21, portrait_animation=True)
        vm.out.append('Keep the story text')
        vm.files_loaded = not loaded
        runtime = s.g.setdefault('dkk.runtime', {})
        runtime.update(picture_name='PIC', picture_id=21, saved_picture_name='PIC', saved_picture_id=22,
                       big_id=112, unrelated=8)
        events = []
        def run(vector):
            events.append(vector)
            if vector == 4:
                assert vm.portrait_clear_epoch == 1 and vm.display['portrait_animation'] is False
                assert vm.display['kind'] == 'PIC' and vm.display['id'] == 21
                assert s.attr == 27 and s.ahead == 55 and s.r1[0x2D5] == 0
                assert (runtime['picture_name'], runtime['picture_id']) == ('', 255)
                assert (runtime['saved_picture_name'], runtime['saved_picture_id']) == ('', 255)
                assert runtime['big_id'] == 112 and runtime['unrelated'] == 8
                s.mode, vm.files_loaded = current, loaded
        refresh = world_explore.refresh
        def draw(host):
            assert host is game and s.r0[0xF2] == 16
            events.append('map')
            refresh(host)
        with patch.object(vm, 'run', side_effect=run), patch.object(game.geo, 'attr', return_value=27), \
             patch.object(game.geo, 'wall', side_effect=AssertionError('unexpected wall refresh')), \
             patch.object(world_explore, 'refresh', side_effect=draw):
            town.after_block(game)
        request = current == 4 if previous == 4 else loaded
        assert events == [4] + (['map'] if request and not defeated else []) + [0, 1]
        assert vm.map_view_epoch == int(request) and vm.portrait_clear_epoch == 1
        assert s.prev_mode == current and vm.out == ['Keep the story text']
        assert vm.text_start == vm.text_epoch == 0
        vm.redraw_view()
        assert vm.map_view_epoch == int(request) and vm.portrait_clear_epoch == 1


def treasure_pool():
    game = Game(None)
    s = game.s
    s.treasure_money[:] = [11, 12, 13, 14, 0, 0, 0]
    s.g['treasure_active'] = 0
    args = ((2, 40000), (2, 35000), (2, 65535), (0, 0))
    command(game, 0x27, *args)
    command(game, 0x27, *args)
    assert s.treasure_money == [11, 12, 13, 14, 80000, 70000, 131070]
    assert s.g['treasure_active'] == 0
    s.treasure_money[4:] = [2147483647, -1, -2147483648]
    s.g['treasure_active'] = 1
    command(game, 0x27, (0, 1), (0, 1), (2, 65535), (0, 0))
    assert s.treasure_money[4:] == [-2147483648, 0, -2147418113]
    assert s.g['treasure_active'] == 1


def menu_lifetime():
    from unittest.mock import patch
    from . import world_explore
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member()]
    s.mode = 4
    vm.bottom_cleared = True
    vm.out.append('Retained message')
    start = vm.text_start
    command(game, 0)
    assert vm.bottom_cleared and not vm.box_cleared
    with patch.object(game, 'ask', return_value=4), patch.object(vm, 'paint_location'):
        assert world_explore.main_menu(game) == 4
    assert vm.text_start == start
    for opcode in (0x11, 0x12):
        command(game, opcode, (0, 7))
        assert not vm.bottom_cleared and vm.out[-1] == '7'
        command(game, 0)
        assert not vm.bottom_cleared
        with patch.object(game, 'ask', return_value=4), patch.object(vm, 'paint_location'):
            world_explore.main_menu(game)
        assert vm.bottom_cleared and vm.text_start == len(vm.out)
    with patch.object(vm, 'ask', return_value=0):
        command(game, 0x15, (2, 0x7A00), (0, 0), (0, 1), (129, 0x7A10))
    assert not vm.bottom_cleared
    s.g.update({'world.extended': 1, 'world.choice': 4})
    with patch.object(vm, 'load_block'), patch.object(vm, 'init_vm'), patch.object(vm, 'run'):
        town.boot(game)
    assert s.g['world.extended'] == 0 and s.g['world.choice'] == 1


def resource_loading():
    from unittest.mock import patch
    from itertools import product
    for previous, current, redraw, order in product((3, 4), (3, 4), (False, True), ((0x21, 0x37), (0x37, 0x21))):
        game = Game(None)
        s, vm = game.s, game.vm
        s.prev_mode, s.mode = previous, current
        vm.noncombat_redraw = redraw
        command(game, order[0], (0, 255), (0, 255), (0, 255))
        assert vm.files_loaded and vm.interface_redraw_epoch == 0 and vm.noncombat_redraw == redraw
        command(game, order[1], (0, 255), (0, 255), (0, 255))
        assert vm.map_loaded and vm.pieces_loaded and vm.files_loaded
        assert vm.interface_redraw_epoch == int(previous == 3 and current != 3 and redraw)
        assert vm.noncombat_redraw == (redraw and previous != 3)
        epoch = vm.interface_redraw_epoch
        command(game, 0x21, (0, 255), (0, 0), (0, 0))
        assert vm.interface_redraw_epoch == epoch
    game = Game(None)
    s, vm = game.s, game.vm
    s.walls = [0, 2, 3, 4]
    s.g['save.wall_pairs'] = ((0, 1), (2, 1), (3, 2), (4, 3))
    s.r0[0xE7:0xE9] = [1, 1]
    command(game, 0x37, (0, 0), (0, 9), (0, 127))
    assert s.walls == [0, 2, 3, 65535]
    assert s.g['save.wall_pairs'] == ((0, 0), (2, 1), (3, 2), (65535, 65535))
    command(game, 0x37, (0, 255), (0, 9), (0, 3))
    assert s.g['save.wall_pairs'][0] == (65535, 65535) and s.g['save.wall_pairs'][3] == (3, 3)
    s.r0[0xE7] = 0
    command(game, 0x37, (0, 1), (0, 255), (0, 127))
    assert s.g['save.wall_pairs'][1:] == ((1, 1), (65535, 65535), (127, 3))
    command(game, 0x37, (0, 127), (0, 1), (0, 1))
    assert s.g['save.wall_pairs'][1:] == ((0, 1), (65535, 65535), (127, 3))
    for dungeon, ident in product((0, 1), (127, 255, 2)):
        s.r0[0xE6], s.r0[0xC5], s.r1[0x2C9] = dungeon, 19, 255
        def load(state, block):
            assert state.r0[0xC5] == block == 2 and state.r1[0x2C9] == 255
        with patch.object(game.geo, 'load', side_effect=load) as loaded:
            command(game, 0x21, (0, ident), (0, 0), (0, 0))
        expected = bool(dungeon and ident == 2)
        assert loaded.call_count == int(expected)
        assert s.r1[0x2C9] == (0 if expected else 255) and s.r0[0xC5] == (2 if expected else 19)
    vm.noncombat_redraw = True
    command(game, 0x3D)
    assert not vm.noncombat_redraw
    for script, redraw in ((0, False), (16, True)):
        s.r0[0xF2] = script
        vm.files_loaded = vm.map_loaded = vm.pieces_loaded = True
        with patch.object(vm, 'load_block'), patch.object(vm, 'init_vm'), patch.object(vm, 'run'):
            town.boot(game)
        assert not (vm.files_loaded or vm.map_loaded or vm.pieces_loaded)
        assert vm.noncombat_redraw == redraw


def clear_box():
    from itertools import product
    from copy import deepcopy
    from unittest.mock import patch
    for demo, mode, bottom, kind in product((0, 1, 255), (3, 4, 7), (False, True), ('PIC', 'SPRIT', 'BIGPIC', None)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member(), member(False)]
        s.sel, s.mode = 1, mode
        s.g['dkk.runtime'] = dict(demo=demo, big_picture_shown=1, picture_name='SPRIT', picture_id=7,
                                  saved_picture_name='PIC', saved_picture_id=3)
        s.g['world.extended'] = 1
        s.g['47E2'], s.g['47E7'] = 1, 0
        vm.out[:] = ['Old text', 'Visible text']
        vm.text_start, vm.text_epoch, vm.text_color = 1, 6, 10
        vm.text_cursor = (13, 21)
        vm.bottom_cleared, vm.box_cleared, vm.noncombat_redraw = bottom, False, True
        vm.display = dict(kind=kind, id=7, dataset=1, frame=3, portrait_hidden=True,
                          clock=[9], location=(99, 99, 0))
        vm.visual.update(graphics=True, sprite=True, monster_sprite=True, monster_picture=True)
        visual, runtime = dict(vm.visual), dict(s.g['dkk.runtime'])
        roster = deepcopy([char.b for char in s.chars()])
        with patch.object(vm, 'clear_text', side_effect=AssertionError('text state reset')):
            command(game, 0x3D)
        assert vm.pc == 0x8001 and vm.text_start == 2 and vm.text_epoch == 7
        assert vm.out == ['Old text', 'Visible text'] and vm.text_color == 10 and vm.text_cursor == (13, 21)
        assert vm.bottom_cleared == bottom and vm.box_cleared and not vm.noncombat_redraw
        assert vm.clear_box_epoch == 1 and vm.clear_box_portrait == (demo == 0)
        assert vm.interface_redraw_epoch == vm.map_view_epoch == vm.portrait_clear_epoch == 0
        assert vm.visual == visual and s.g['dkk.runtime'] == dict(runtime, big_picture_shown=0)
        assert [char.b for char in s.chars()] == roster and s.sel == 1
        assert s.g['world.extended'] == s.g['47E2'] == 1 and s.g['47E7'] == 0
        assert vm.display['blank'] and vm.display['frame'] == 3
        assert vm.display.get('portrait_hidden', False) == bool(demo)
        assert vm.display['kind'] == (None if kind == 'BIGPIC' or demo else kind)
        if mode == 3:
            assert 'clock' not in vm.display and 'location' not in vm.display
        else:
            assert vm.display['clock'] == s.r0[0xC6:0xCD]
            assert vm.display['location'] == (s.x, s.y, s.dir)
        vm.display = dict(kind='PIC', id=3)
        command(game, 0x3D)
        assert vm.clear_box_epoch == 2 and vm.text_epoch == 8
        command(game, 0)
        assert not vm.box_cleared and vm.bottom_cleared == bottom


def boot_archive():
    from unittest.mock import patch
    from itertools import product
    for disk, saved, resuming in product((1, 2, 3, 4, 5), (0, 16, 36), (False, True)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.dataset, s.r0[0xF2], vm.resuming = disk, saved, resuming
        expected = (disk, saved) if saved else (1, 16)
        events = []
        def observe(stage):
            assert (s.dataset, s.block) == expected
            assert s.r0[0xF2] == saved and vm.resuming == resuming
            events.append(stage)
        with patch.object(vm, 'load_block', side_effect=lambda block: observe(('load', block))), \
             patch.object(vm, 'init_vm', side_effect=lambda: observe('init')), \
             patch.object(vm, 'run', side_effect=lambda address: observe(('main', address))):
            town.boot(game)
        assert events == [('load', expected[1]), 'init', ('main', vm.vec[4])]
        assert s.r0[0xF2] == expected[1] and not vm.resuming


def program_lifetime():
    from itertools import product
    from unittest.mock import patch
    for program, extended, restore, wild in product((0, 9, 1, 256, 265), (0, 1), (False, True), (0, 1, 2)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member(), member()]
        s.sel = 1
        s.r0[0x1F7] = wild
        s.g.update({'world.extended': extended, '47E2': int(restore), '47E7': 0})
        vm.gosub = [0x8300]
        calls = []
        def service(*args):
            assert s.g['world.extended'] == 0 and not s.g['47E2']
            assert s.sel == (0 if restore else 1)
            s.g['world.extended'] = 7
            calls.append(args)
        def camping(host):
            service('camp', host)
            vm.pc, vm.next = 0x8100, 0x8101
        with patch.object(vm, 'service', side_effect=service), patch.object(town, 'camp', side_effect=camping):
            command(game, 0x38, (2, program))
        selected = program & 255
        assert calls == ([('creation', 'run')] if selected == 0 else [('camp', game)] if selected == 9 else [])
        stopped = selected == 9 and wild == 1
        assert s.g['world.extended'] == extended and not s.g['47E2']
        assert s.sel == (0 if restore else 1) and s.stop == int(stopped)
        assert vm.pc == 0x8004 + int(stopped)
        assert vm.gosub == ([] if stopped else [0x8300])


def camp_clears_story_text():
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member()]
    vm.vec = [0x8000, 0x8000, 0x8000, 0x8000, 0x8000]
    order = []
    vm.run = lambda pc: order.append(('vector', vm.out[vm.text_start:]))
    vm.out, vm.text_start, epoch = ['SLEEP AND YOU WILL HAVE A DREAM.'], 0, vm.text_epoch
    vm.service = lambda unit, name, *arguments: order.append((unit, vm.out[vm.text_start:]))
    town.camp(game)
    assert order[:2] == [('vector', ['SLEEP AND YOU WILL HAVE A DREAM.']), ('camp', [])]
    assert vm.text_epoch == epoch + 1 and vm.out == ['SLEEP AND YOU WILL HAVE A DREAM.']


def camp_interrupted_redraw():
    for mode, interrupted in ((4, 1), (4, 0), (3, 1)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party, s.mode, s.x, s.y, s.dir = [member()], mode, 10, 11, 2
        vm.vec = [0x8000, 0x8000, 0x8100, 0x8200, 0x8000]
        seen = []
        vm.run = lambda pc: seen.append((pc, vm.view_at, vm.roster_shown, vm.display.get('misc_info')))
        vm.service = lambda unit, name, *arguments: interrupted
        vm.view_at, vm.roster_shown, vm.info_line, vm.display = None, 2, '', dict(kind=None, misc_info='')
        town.camp(game)
        if mode == 4 and interrupted: assert seen[1][0] == 0x8200 and seen[1][1] == (10, 11, 2) and seen[1][2] is None and seen[1][3] not in ('', None)
        elif interrupted: assert seen[1][0] == 0x8200, seen
        else: assert [pc for pc, *_ in seen] == [0x8100]


def party_menu_return_view():
    from unittest.mock import patch
    for mode in (3, 4):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member()]
        s.mode = mode
        vm.display = dict(kind=None, location=(10, 11, 2), misc_info='10,11 E 00:32', clock=[0] * 7)
        vm.info_line, vm.roster_shown = '10,11 E 00:32', 0
        with patch.object(vm, 'service', return_value=None): command(game, 0x38, (2, 0))
        if mode == 4:
            assert vm.display.get('blank') and vm.display.get('kind') is None and vm.info_line == '' and vm.roster_shown is None
            assert vm.display['misc_info'] == '' and not any(key in vm.display for key in ('clock', 'location'))
            vm.redraw_view()
            assert vm.display['misc_info'] == ''
        else: assert not vm.display.get('blank') and vm.display['misc_info'] == vm.info_line


def program_return_display():
    from itertools import product
    from unittest.mock import patch
    for picture, dungeon, wild, restart in product((9, 21, 255), (0, 1, 2), (0, 1, 2), (0, 1)):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member()]
        runtime = s.g.setdefault('dkk.runtime', {})
        s.g['world.extended'] = 1
        runtime.update(picture_id=9, restart_loop=1)
        s.r0[0xE6], s.r0[0x1F7] = 1, 0
        s.mode = 3
        vm.interface_redraw_epoch = 4
        vm.display = dict(kind='BIGPIC', id=112, map_cursor=False)
        vm.out = ['story text']
        text_epoch = vm.text_epoch
        def leave_menu(*args):
            assert args == ('creation', 'run') and s.g['world.extended'] == 0
            assert vm.interface_redraw_epoch == 4 and not vm.display['map_cursor']
            runtime.update(picture_id=picture, restart_loop=restart)
            s.r0[0xE6], s.r0[0x1F7] = dungeon, wild
            s.restart = 1
        with patch.object(vm, 'service', side_effect=leave_menu):
            command(game, 0x38, (2, 256))
        redraw = picture != 9 and dungeon == 0 and wild == 1 and restart == 0
        assert vm.interface_redraw_epoch == 4 + redraw
        assert vm.display == dict(kind='BIGPIC', id=112, map_cursor=redraw)
        assert s.g['world.extended'] == 1 and s.restart == 1
        assert vm.out == ['story text'] and vm.text_epoch == text_epoch
    from . import creation
    for dungeon in (0, 1):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member()]
        s.mode = 4 if dungeon else 3
        s.r0[0xE6], s.r0[0x1F7] = dungeon, 1
        def begin(kind, choices, current, **info):
            assert info['action'] == 'main-menu' and s.mode == 0
            assert vm.interface_redraw_epoch == 0
            return game.menu_ids.index(creation.BEGIN)
        game.player = begin
        command(game, 0x38, (0, 0))
        assert s.mode == (4 if dungeon else 3)
        assert vm.interface_redraw_epoch == 1 - dungeon
        assert bool(vm.display.get('map_cursor')) == (dungeon == 0)
        assert bool(vm.display.get('blank')) == (dungeon == 1)


def wrapped_spaces():
    for wrap in (town.wrapped_text, Game(None).vm.binding.wrapped_text):
        for mark in '!,.-:;?':
            for spaces in (1, 2, 3, 12):
                assert wrap('A' * 37 + mark + ' ' * spaces + 'Next') == ['A' * 37 + mark, 'Next']
        assert wrap('A' * 37 + '   Next') == ['A' * 37, 'Next']
        assert wrap('A' * 37 + '.   ' + 'B' * 37 + '.   End') == ['A' * 37 + '.', 'B' * 37 + '.', 'End']
        assert wrap('  First.  Second\n  Third') == ['  First.  Second', '  Third']
        assert wrap('A.   B.', 2) == ['A.', 'B.']
        assert wrap('') == []
    game = Game(None)
    vm = game.vm
    for text, gap in (('A' * 37 + '.', 2), ('A' * 37 + ' ', 2), ('A' * 36 + '.', 1), ('A' * 10, 1)):
        vm.out, vm.text_start = [text], 0
        command(game, 0x33)
        command(game, 0x33)
        vm.out.append('Next')
        assert ''.join(vm.out).count('\n') == gap + 1


def restart_lifecycle():
    from unittest.mock import patch
    from . import world_explore
    game = Game(None)
    s, vm = game.s, game.vm
    flags = s.g.setdefault('dkk.runtime', {})
    s.code[:10] = bytes((0x38, 0, 0, 9, 0, 99, 1, 0x10, 0x4B, 0))
    def restart(*args):
        flags['restart_loop'] = 1
    with patch.object(vm, 'service', side_effect=restart) as service:
        vm.run(0x8000)
    assert service.call_count == 1 and vm.pc == 0x8003 and vm.steps == 1
    assert s.r0[0x10] == 0 and s.stop == 0 and s.restart == 0
    vm.run(0x8003)
    assert vm.steps == 0 and s.r0[0x10] == 0 and flags['restart_loop'] == 1
    flags['restart_loop'], s.restart = 0, 1
    vm.run(0x8003)
    assert vm.steps == 2 and s.r0[0x10] == 99 and s.restart == 1
    assert not s.party and not s.stop
    flags['restart_loop'] = 1
    def observe(*args):
        assert flags['restart_loop'] == 0
    with patch.object(vm, 'load_block', side_effect=observe), patch.object(vm, 'init_vm', side_effect=observe), \
         patch.object(vm, 'run', side_effect=observe):
        town.boot(game)
    assert flags['restart_loop'] == 0
    for stage in ('menu', 'camp', 'search', 'before', 'after'):
        game = Game(None)
        s, vm = game.s, game.vm
        s.party = [member()]
        s.g.setdefault('dkk.runtime', {})['restart_loop'] = 0
        s.r1[0x2CA] = 2 if stage == 'search' else 0
        vm.vec = [0x8100, 0x8200, 0, 0, 0]
        events = []
        def signal():
            s.g['dkk.runtime']['restart_loop'] = 1
        def menu(host):
            events.append('menu')
            if stage == 'menu': signal()
            return 4 if stage == 'camp' else 0
        def camping(host):
            events.append('camp')
            signal()
        def vector(address):
            label = 'before' if address == vm.vec[0] else 'after'
            events.append(label)
            if stage == label or stage == 'search': signal()
        with patch.object(world_explore, 'main_menu', side_effect=menu), \
             patch.object(town, 'camp', side_effect=camping), patch.object(vm, 'run', side_effect=vector), \
             patch.object(world_explore, 'refresh'), \
             patch.object(world_explore, 'resolve', side_effect=lambda host: events.append('move')):
            world_explore.turn(game)
        expected = {'menu': ['menu'], 'camp': ['menu', 'camp'], 'search': ['menu', 'after'],
                    'before': ['menu', 'before'], 'after': ['menu', 'before', 'move', 'after']}
        assert events == expected[stage] and town.restart_requested(s) and not s.restart
        if stage == 'search': assert s.r1[0x2CA] == 0
    game = Game(None)
    events = []
    def boot(host):
        events.append('boot')
        host.s.g.setdefault('dkk.runtime', {})['restart_loop'] = 0
    def turn(host):
        assert not town.restart_requested(host.s)
        events.append('turn')
        host.s.g['dkk.runtime']['restart_loop'] = 1
        if events.count('turn') == 2: host.s.party_dead = 1
    from types import SimpleNamespace
    game.s.party = [SimpleNamespace(b=bytearray(512)), SimpleNamespace(b=bytearray(512))]
    game.s.r1[0x33E] = 2
    with patch.object(town, 'boot', side_effect=boot), patch.object(town, 'turn', side_effect=turn):
        assert town.play(game) == 'DEFEAT'
    assert events == ['boot', 'turn', 'boot', 'turn'] and game.s.party == [] and not game.s.party_dead and game.s.r1[0x33E] == 0


def vault_loop():
    from unittest.mock import patch
    from types import SimpleNamespace
    from . import combat, inventory, save_vault, shop, world_vault
    from .records import Item
    from .faults import BindingRequired
    game = Game(None)
    s, vm = game.s, game.vm
    s.party = [member()]
    s.monsters = [member()]
    s.treasure_money[4:7] = [11, 12, 13]
    stale = bytearray(bytes(Item()))
    s.treasure_items = [stale]
    epoch = vm.interface_redraw_epoch
    def unavailable(host, unit, name):
        assert host is game and (unit, name) == ('save', 'check_directory')
        assert s.mode == 7 and s.g['dkk.runtime']['noncombat_prepared'] == 1
        assert vm.interface_redraw_epoch == epoch + 1
        return None
    game.save_filesystem = SimpleNamespace(save_path='c:', disk_free=lambda drive: 65536)
    with patch.object(game, 'service', side_effect=unavailable): world_vault.run(game)
    assert s.treasure_items == [stale] and s.treasure_money[4:7] == [11, 12, 13]
    with TemporaryDirectory(prefix='sm-dkk-vault-') as tmp:
        folder = Path(tmp)
        stored = Item(); stored.data[-1] = 7
        (folder / 'VAULTQ.DAT').write_bytes(save_vault.Vault((5, 0, 0), (stored,)).dump())
        s.g['treasure_active'] = 1
        events = []
        actions = iter(('Take', 'View', 'Items', 'char-down', 'extended', 'escape'))
        def player(kind, options, host, **info):
            assert kind == 'MENU' and info['vault_menu'] and not info['animation']
            assert s.g['treasure_active'] == 0
            assert options[info['escape_choice']] == 'escape'
            assert host.menu_highlight == info['start']
            action = next(actions)
            events.append((action, info['start'], s.sel, tuple(options[:len(info['enabled'])])))
            if action == 'char-down': host.menu_highlight = 3
            return options.index(action)
        game.player = player
        s.party[0].items = [bytearray(bytes(Item()))]
        def take(host, coins, items):
            assert host is game and coins and items
            assert s.treasure_money[4:7] == [5, 0, 0]
            assert s.treasure_items == [bytearray(bytes(stored))]
            s.treasure_money[4:7] = [0, 0, 0]
            s.treasure_items.clear()
        def view(host, char):
            assert char is s.party[0]
            return True
        def deposit(host, char):
            s.treasure_items.append(char.items.pop())
            host.menu_highlight = 99
            return True
        with patch.object(combat, 'loot_take', side_effect=take) as taker, \
             patch.object(inventory, 'view', side_effect=view), \
             patch.object(inventory, 'items_menu', side_effect=deposit):
            epoch = vm.interface_redraw_epoch
            world_vault.interact(game, folder)
        taker.assert_called_once_with(game, True, True)
        assert events == [
            ('Take', 0, 0, ('View', 'Take', 'Pool', 'Items', 'Exit')),
            ('View', 1, 0, ('View', 'Pool', 'Items', 'Exit')),
            ('Items', 0, 0, ('View', 'Pool', 'Items', 'Exit')),
            ('char-down', 2, 0, ('View', 'Take', 'Pool', 'Exit')),
            ('extended', 3, 1, ('View', 'Take', 'Pool', 'Exit')),
            ('escape', 3, 1, ('View', 'Take', 'Pool', 'Exit'))]
        assert vm.interface_redraw_epoch == epoch + 1 and s.mode == 7
        assert s.g['vault.pending'] == 1 and len(s.treasure_items) == 1
        saved = save_vault.decode((folder / 'TMPVAULT.DAT').read_bytes())
        assert saved.money == (0, 0, 0) and len(saved.items) == 1
        s.sel = 0
        s.party[0].items.clear()
        s.treasure_items.clear()
        save_vault.write_vault(s, folder)
        shop.put_coins(s.party[0], [0, 0, 0, 0, 40000, 0, 0])
        shop.put_coins(s.monsters[0], [0, 0, 0, 0, 40000, 0, 0])
        for char in s.chars(): shop.add_weight(char, 40000 - shop.weight(char))
        actions = iter(('Pool', 'Exit'))
        game.player = lambda kind, options, host, **info: options.index(next(actions))
        world_vault.interact(game, folder)
        assert s.treasure_money[4] == 80000 and s.g['treasure_active'] == 1
        assert shop.coins(s.party[0])[4] == shop.coins(s.monsters[0])[4] == 0
        assert save_vault.decode((folder / 'TMPVAULT.DAT').read_bytes()).money == (80000, 0, 0)
        s.treasure_money[4:7] = [0, 0, 0]
        save_vault.write_vault(s, folder)
        shop.put_coins(s.party[0], [0, 0, 0, 0, 7, 0, 0])
        shop.add_weight(s.party[0], 7)
        actions = iter(('Money', 'steel', 7, 'char-down', 'Exit'))
        starts, coin_layouts = [], []
        def money_player(kind, options, host, **info):
            action = next(actions)
            if options is None: return action
            if info.get('vault_menu'):
                starts.append(info['start'])
                assert host.menu_highlight == info['start']
                assert options[info['escape_choice']] == 'escape'
                if isinstance(action, tuple): action, host.menu_highlight = action
            if action == 'steel':
                coin_layouts.append(info)
                return 0
            return options.index(action)
        game.player = money_player
        epoch = vm.text_epoch
        world_vault.interact(game, folder)
        assert starts == [0, 2, 2] and vm.text_epoch == epoch + 1
        assert coin_layouts[0]['window'] == '1 17 38 22'
        assert coin_layouts[0]['query'] == game.assets.text('selectCoinQuery')
        assert coin_layouts[0]['menu'] == game.assets.text('selectMenuText')
        assert s.treasure_money[4] == 7 and shop.coins(s.party[0])[4] == 0
        assert save_vault.decode((folder / 'TMPVAULT.DAT').read_bytes()).money == (7, 0, 0)
        s.sel = 0
        actions = iter(('Take', 'steel', 7, 'Exit'))
        game.player = money_player
        epoch = vm.interface_redraw_epoch
        with patch.object(game, 'service', return_value=folder) as directory:
            town.service(game, 'vault', 'run')
        directory.assert_called_once_with(game, 'save', 'check_directory')
        assert vm.interface_redraw_epoch == epoch + 1
        assert s.treasure_money[4] == 0 and shop.coins(s.party[0])[4] == 7
        assert s.g['treasure_active'] == 0 and not s.treasure_items
        assert save_vault.decode((folder / 'TMPVAULT.DAT').read_bytes()).money == (0, 0, 0)
        s.treasure_money[4] = 1
        save_vault.write_vault(s, folder)
        s.party[0].items = [bytearray(bytes(Item()))]
        actions = iter((('extended', 1), ('extended', 2), ('extended', 3), ('extended', 4),
                        'char-down', ('extended', 3), 'char-up', 'escape'))
        starts = []
        with patch.object(save_vault, 'write_vault', wraps=save_vault.write_vault) as writer:
            world_vault.interact(game, folder)
        writer.assert_called_once_with(s, folder, game=game)
        assert starts == [0, 1, 2, 3, 4, 0, 3, 3]
        assert s.sel == 0 and s.treasure_money[4] == 1

    with TemporaryDirectory(prefix='sm-dkk-vault-') as tmp:
        game.save_filesystem, game.roster_directory = None, Path(tmp)
        vm.out.append('BANK')
        seen = []
        def leave(kind, choices, current, **info):
            seen.append(''.join(vm.out[vm.text_start:]))
            return choices.index('Exit')
        game.player = leave
        town.service(game, 'vault', 'run')
        assert seen == [''] and (Path(tmp) / 'TMPVAULT.DAT').is_file()


def held_frames():
    from collections import deque
    game = Game(None)
    s, vm = game.s, game.vm
    game.presentation = deque()
    game.player = lambda kind, choices, current, **info: 0
    def shown(): return game.presentation[-1]['scene'].s
    def place(state): return state.x, state.y, state.dir
    s.r0[0xE6], s.mode, s.x, s.y, s.dir = 1, 4, 0, 8, 2
    vm.redraw_view()
    command(game, 0x3A)
    assert place(shown()) == (0, 8, 2) and game.presentation[-1]['loading_notice'] is False
    assert game.presentation[-1]['linked_shown'] is vm.linked_shown
    s.r0[0xE7], s.r0[0xE8] = 1, 1
    command(game, 0x37, (0, 1), (0, 127), (0, 127))
    vm.step()
    command(game, 0x3A)
    assert place(s) == (1, 8, 2) and place(shown()) == (0, 8, 2) and game.presentation[-1]['loading_notice'] is True
    vm.update_display()
    s.dir = 4
    command(game, 0x3A)
    assert place(shown()) == (1, 8, 2) and game.presentation[-1]['scene'].vm.display['misc_info'].startswith('1,8 E')
    vm.ask('MENU', ('Yes', 'No'))
    s.x = 5
    command(game, 0x3A)
    assert place(shown()) == (1, 8, 4) and game.presentation[-1]['loading_notice'] is False
    vm.redraw_view()
    command(game, 0x3A)
    assert place(shown()) == (5, 8, 4)
    vm.loading_notice = False
    vm.load_wall(65535, 3)
    assert vm.loading_notice is False
    vm.load_wall(1, 0)
    assert vm.loading_notice is True
    assert s.g['dkk.runtime']['big_id'] == 255
    vm.loading_notice = False
    command(game, 0x0E, (0, 120))
    assert vm.loading_notice is True and s.g['dkk.runtime']['big_id'] == 120
    vm.loading_notice = False
    command(game, 0x0E, (0, 120))
    assert vm.loading_notice is False
    s.party = [member(), member(), member()]
    s.sel, s.g['47E7'] = 0, 0
    command(game, 0x0A, (0, 2))
    assert s.sel == 2 and vm.roster_shown == 0
    command(game, 0x0A, (0, 1))
    command(game, 0x3A)
    assert s.sel == 1 and vm.roster_shown == 0 and shown().sel == 0
    command(game, 0x00)
    assert s.sel == 0 and vm.roster_shown is None
    command(game, 0x0A, (0, 1))
    command(game, 0x3D)
    assert s.sel == 1 and vm.roster_shown is None
    command(game, 0x00)
    assert s.sel == 0 and vm.roster_shown == 1
    command(game, 0x0A, (0, 2))
    vm.service = lambda unit, name, *arguments: None
    vm.interface('camp', 'run')
    assert vm.roster_shown is None
    game.presentation = None
    command(game, 0x3A)
    vm.out.append('STORY TEXT')
    vm.paint_location()
    seen = []
    vm.service = lambda unit, name, *arguments: seen.append((unit, name, vm.display.get('misc_info'), vm.out[vm.text_start:]))
    vm.monsters_loaded, epoch = 0, vm.text_epoch
    s.r0[0x200], s.r1[0x36C], s.r1[0x2E2] = 0, 0, 0
    command(game, 0x24)
    assert seen == [('combat', 'treasure', '', [])] and vm.text_epoch == epoch + 1
    assert vm.display['misc_info'] == vm.info_line != ''


def play_continues():
    from unittest.mock import patch
    game, turns = Game(None), []
    game.s.g['dkk.battle'] = dict(active=False, result='won', enemy_survivors=0)
    def turn(played):
        turns.append(played.s.g['world.choice'])
        played.s.stop = 1
    with patch.object(town, 'boot'), patch.object(town, 'turn', turn):
        assert town.play(game) == 'FIRST_FIGHT_WON' and not turns
        game.first_fight_only = False
        assert town.play(game) == 'LIMIT' and turns == [1]


def script_stops():
    from unittest.mock import patch
    from . import world_explore as world
    from .faults import BindingRequired
    game = Game(None)
    s, vm = game.s, game.vm
    text = game.assets.text
    asked = []
    prompts = []
    game.player = lambda kind, choices, current, **info: prompts.append(choices) or asked.append((kind, info)) or 0
    def party(*points):
        s.party, s.monsters, s.sel, s.party_dead = [member() for _ in points], [], 0, 0
        for index, (char, hp) in enumerate(zip(s.party, points)):
            char.b[0:2] = bytes((1, 65 + index))
            town.put(char, 'hp', hp)
            town.put(char, 'ac', 50)
            town.put(char, 'levels', 1, 0)
            for kind in range(5): town.put(char, 'saves', 10, kind)
        s.r1[0x33E] = len(points)
        vm.out.clear(); vm.text_start = 0; asked.clear(); prompts.clear()
    def damage(rolls, *operands):
        rolls, calls = iter(rolls), []
        def dice(count, sides):
            calls.append((count, sides))
            return next(rolls)
        with patch.object(vm, 'dice', side_effect=dice):
            command(game, 0x2E, *((0, value) for value in operands))
        assert next(rolls, None) is None
        return calls
    def state(char): return town.field(char, 'hp'), town.field(char, 'status'), town.field(char, 'active')
    party(20, 8, 3, 9)
    town.put(s.party[3], 'status', 6)
    assert damage((5,), 0xE0, 2, 4, 3, 0) == [(2, 4)]
    assert [state(char) for char in s.party] == [(12, 0, 1), (0, 4, 0), (0, 5, 0), (9, 6, 1)]
    shown = [line for line in ''.join(vm.out[vm.text_start:]).splitlines() if line]
    assert shown == ['%s is hit FOR 8 points of Damage.' % name for name in 'ABC']
    assert asked[-1][1]['purpose'] == 'script damage' and not asked[-1][1]['page'] and not s.party_dead
    party(20, 20, 20)
    s.sel = 1
    assert damage((4, 2, 15), 0x92, 1, 6, 0, 0x83) == [(1, 6), (1, 3), (1, 20)]
    assert [town.field(char, 'hp') for char in s.party] == [20, 18, 20]
    assert damage((4, 1, 7), 0x92, 1, 6, 0, 0x83) == [(1, 6), (1, 3), (1, 20)]
    assert town.field(s.party[1], 'hp') == 14
    assert damage((4, 3), 0x80, 1, 6, 0, 0x80) == [(1, 6), (1, 3)]
    assert [town.field(char, 'hp') for char in s.party] == [20, 10, 20]
    assert damage((4, 3, 1), 0x80, 1, 6, 0, 1) == [(1, 6), (1, 3), (1, 20)]
    assert [town.field(char, 'hp') for char in s.party] == [20, 10, 16]
    assert damage((4, 3, 20), 0x80, 1, 6, 0, 1)[-1] == (1, 20)
    assert town.field(s.party[2], 'hp') == 16
    party(20, 20, 20)
    calls = damage((6, 1, 2, 20, 3, 3, 1, 9), 2, 1, 8, 0, 5)
    assert calls == [(1, 8), (1, 3), (1, 3), (1, 20), (1, 8), (1, 3), (1, 20), (1, 8)]
    assert [town.field(char, 'hp') for char in s.party] == [20, 14, 20]
    assert damage((6, 1, 2, 19, 6), 1, 1, 8, 0, 31) == [(1, 8), (1, 3), (1, 3), (1, 20), (1, 8)]
    assert town.field(s.party[1], 'hp') == 14
    assert damage((6, 1, 2, 19, 6), 1, 1, 8, 0, 32)[-1] == (1, 8) and town.field(s.party[1], 'hp') == 8
    party(100)
    assert damage((255,), 0xE0, 1, 255, 45, 0) == [(1, 255)]
    assert state(s.party[0]) == (56, 0, 1) and vm.out[-1].strip() == 'A dies.'
    party(250)
    damage((255,), 0xE0, 1, 255, 5, 0)
    assert vm.out[-1].strip() == 'A is hit FOR 260 points of Damage.' and state(s.party[0]) == (246, 0, 1)
    party(5)
    damage((30,), 0xE0, 1, 30, 0, 0)
    assert state(s.party[0]) == (0, 6, 0) and s.party_dead == 1
    assert vm.out[-1] == text('partyKilledText') and vm.display.get('party_killed')
    assert asked[-1][1]['defeated']
    party(*(50,) * 8)
    damage((1,), 0xE0, 1, 1, 0, 0)
    assert [info['page'] for kind, info in asked] == [True, False]
    assert [(options[0], info['color']) for (kind, info), options in zip(asked, prompts)] == [(text('pressAnyKey'), 13), (text('pressToContinue'), 15)]
    party(*(50,) * 5)
    for index, char in enumerate(s.party): char.b[0:8] = bytes((7,)) + bytes((65 + index,)) * 7
    damage((5,), 0xE0, 1, 5, 0, 0)
    row = '%s is hit FOR 5 points of Damage.'
    assert len(row % 'AAAAAAA') == 38 and [info['page'] for kind, info in asked] == ['row', False]
    assert [options[0] for options in prompts] == ['PRESS <ENTER>/<RETURN> TO CONTINUE', text('pressToContinue')]
    assert ''.join(vm.out[vm.text_start:]).splitlines() == ['  DDDDDDD is hit FOR 5 points of', 'Damage.', row % 'EEEEEEE']
    party(*(50,) * 4)
    for index, char in enumerate(s.party): char.b[0:8] = bytes((7,)) + bytes((65 + index,)) * 7
    s.party[3].b[0:8] = bytes((2,)) + b'DD' + bytes(5)
    damage((5,), 0xE0, 1, 5, 0, 0)
    assert ''.join(vm.out[vm.text_start:]).splitlines() == ['  DD is hit FOR 5 points of Damage.']
    party(*(50,) * 3)
    for index, char in enumerate(s.party): char.b[0:8] = bytes((7,)) + bytes((65 + index,)) * 7
    damage((5,), 0xE0, 1, 5, 0, 0)
    assert ''.join(vm.out[vm.text_start:]).splitlines() == ['', row % 'AAAAAAA', '', row % 'BBBBBBB', '', row % 'CCCCCCC']
    assert vm.display['misc_info'] == '' and vm.info_line == ''
    party(20, 20)
    s.r1[0x33E] = 3
    try: damage((1, 3), 0x80, 1, 1, 0, 0)
    except (BindingRequired, AssertionError): pass
    else: raise AssertionError('script damage walked beyond the creature list')
    from . import effects
    seen = []
    def trigger(host, condition, char, roll):
        seen.append((condition, roll.element, roll.save_passed, roll.attack))
        roll.damage = 9
    for operands, rolls, expected in (((0x80, 1, 6, 0, 1), (4, 1, 7), (12, 5, True, 0)), ((1, 1, 8, 0, 5), (6, 1, 1, 7, 6), (16, 5, False, 7))):
        party(20)
        game.roll_memo = {'element': 5}
        with patch.object(effects, 'trigger_condition', side_effect=trigger): damage(rolls, *operands)
        assert seen.pop() == expected and game.roll_memo['damage'] == 9 and game.roll_memo['element'] == 5
    party(20, 20)
    town.put(s.party[1], 'levels', 2, 3)
    s.sel, vm.roster_shown = 1, None
    town.put(s.party[0], 'level_up_ready', 1)
    with patch.object(vm, 'hold') as hold: command(game, 0x41, (0, 0), (2, 10001))
    assert vm.ready_shown == (1, 0)
    hold.assert_called_once_with(s.g.get('dkk.delay', 4) / 10)
    vm.display['frame'], s.g['dkk.delay'] = 2, 7
    with patch.object(vm, 'hold') as hold: command(game, 0x2D, (2, 0x6803))
    assert vm.display['frame'] == 3
    hold.assert_called_once_with(0.7)
    assert [town.field(char, 'experience', width=4) for char in s.party] == [0, 5000]
    assert vm.out[-1] == text('congratulationsText') + 'B' + text('gainsSuffix')
    town.put(s.party[0], 'active', 0)
    with patch.object(vm, 'hold'): command(game, 0x41, (0, 1), (2, 30000))
    assert [town.field(char, 'experience', width=4) for char in s.party] == [0, 20000]
    assert vm.out[-1] == text('partyGainsText') and vm.ready_shown == (1, 0)
    command(game, 0x00)
    assert vm.ready_shown == (1, 0) and vm.roster_shown is None
    s.sel, before = 0, len(vm.out)
    with patch.object(vm, 'hold') as hold: command(game, 0x41, (0, 0), (2, 500))
    assert not hold.called and len(vm.out) == before and town.field(s.party[0], 'experience', width=4) == 0
    party(20)
    vm.roster_shown = 0
    vm.ready_shown = (0,)
    command(game, 0x36, (0, 48), (0, 100))
    joined = s.party[1]
    assert vm.roster_shown is None and vm.ready_shown is None
    assert len(s.party) == 2 and s.sel == 1 and s.r1[0x33E] == 2
    assert town.field(joined, 'creature_id') == 48 and town.field(joined, 'npc') == 0xB2
    assert town.field(joined, 'order') == 1 and vm.icons[1] == ('CPIC', 48, s.dataset)
    slots = save_start.item_pool(vm.host).slots
    assert joined.items and all(any(item is slot for slot in slots) for item in joined.items)
    assert len({id(item) for item in joined.items}) == len(joined.items)
    s.r1[0x33E], s.sel, vm.roster_shown = 8, 0, 1
    command(game, 0x36, (0, 49), (0, 7))
    assert vm.roster_shown is None and len(s.party) == 2 and s.r1[0x33E] == 8 and town.field(s.party[0], 'npc') == 0x83
    party(20)
    vm.vec = [0x8100, 0x8200, 0x8300, 0x8400, 0x8500]
    s.mode, s.r0[0x1F7], s.dir = 3, 1, 5
    s.g['world.extended'] = 1
    seen = []
    def step(kind, choices, current, **info):
        seen.append(choices)
        return choices.index('step')
    game.player = step
    assert world.main_menu(game) == 32 and s.dir == 5 and s.g['world.extended'] == 1
    s.mode, s.r0[0x1F7] = 4, 0
    game.player = lambda kind, choices, current, **info: seen.append(choices) or choices.index('forward')
    game.geo.passage = lambda *args: 0
    world.main_menu(game)
    assert 'step' not in seen[-1] and 'step' in seen[0]
    s.mode, s.x, s.y, s.dir = 4, 7, 13, 0
    s.r0[0xC7:0xCA] = [0, 0, 0]
    vm.paint_location()
    assert vm.info_line == '7,13 N 00:00'
    s.mode = 3
    command(game, 0x0E, (0, 96))
    assert vm.display['kind'] == 'PIC' and vm.display['misc_info'] == '7,13 N 00:00'
    assert (s.g['dkk.runtime']['picture_name'], s.g['dkk.runtime']['picture_id']) == ('PIC', 96)
    command(game, 0x0E, (0, 113))
    assert 'misc_info' not in vm.display and vm.info_line is None
    assert (s.g['dkk.runtime']['picture_name'], s.g['dkk.runtime']['picture_id']) == ('', 255)
    loads = s.g['dkk.runtime']['loads']
    command(game, 0x0E, (0, 96))
    assert 'misc_info' not in vm.display and s.g['dkk.runtime']['loads'] == loads + 1
    vm.archive('PIC', 96); vm.archive('PIC', 255)
    assert s.g['dkk.runtime']['loads'] == loads + 1
    vm.loading_notice = True
    vm.archive('PIC', 96)
    assert vm.loading_notice is True
    s.g['dkk.animations'] = 0
    vm.archive('PIC', 97)
    assert vm.loading_notice is True
    s.g['dkk.animations'] = 1
    vm.archive('SPRIT', 64)
    assert vm.loading_notice is False
    s.mode = 4
    vm.paint_location()
    assert vm.display['misc_info'] == '7,13 N 00:00'
    from types import SimpleNamespace
    s.r1[0x2CA], s.g['world.extended'] = 0, 0
    game.player = lambda kind, choices, current, **info: choices.index('Look')
    with patch.object(vm, 'run'): world.main_menu(game)
    assert s.r0[0xC8] == 1 and s.r1[0x2CA] == 2 and vm.display['misc_info'] == '7,13 N 00:00'
    s.r1[0x2CA] = 1
    world.refresh(game)
    command(game, 0x0E, (0, 96))
    assert vm.display['kind'] == 'PIC' and vm.display['misc_info'] == '7,13 N 00:00'
    game.player = lambda kind, choices, current, **info: choices.index('Encamp')
    world.main_menu(game)
    assert vm.display['misc_info'] == '7,13 N 00:00'
    picks = iter(('Search', 'Encamp'))
    game.player = lambda kind, choices, current, **info: choices.index(next(picks))
    world.main_menu(game)
    assert s.r1[0x2CA] == 0 and vm.display['misc_info'] == '7,13 N 00:10'
    s.r0[0xC8] = 2
    seen = []
    with patch.object(vm, 'service', side_effect=lambda *call: seen.append(vm.display.get('misc_info'))):
        vm.service('combat', 'load_monsters')
        assert vm.display['misc_info'] == '7,13 N 00:10'
        s.mode = 2
        vm.interface('camp', 'run')
        assert 'misc_info' not in vm.display
        s.mode = 4
        vm.interface('camp', 'run')
    assert seen == ['7,13 N 00:10', None, None] and vm.display['misc_info'] == '7,13 N 00:20'


def demo_loop():
    game = Game(None)
    game.s.g.setdefault('dkk.runtime', {})['demo'] = 1
    loads, load = [], game.vm.load_block
    game.vm.load_block = lambda ident: (loads.append((game.s.dataset, ident)), load(ident))[1]
    game.player = lambda kind, choices, current, **info: 0
    run = game.vm.run
    game.vm.run = lambda at: (run(at), game.s.monsters.append(member()))[0]
    assert town.play(game) == 'DEMO'
    assert loads == [(5, 2)] and game.demo_mode == 1
    assert not game.s.party and not game.s.monsters and game.s.r1[0x33E] == 3
    assert game.s.code[game.vm.at - 0x8000] == 0x00
