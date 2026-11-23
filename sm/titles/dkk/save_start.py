from .records import Item


class ItemPool:
    def __init__(self):
        self.slots = tuple(bytearray(Item.SIZE) for _ in range(128))

    def allocate(self):
        item_type = Item.FIELDS['type'][0]
        return next((slot for slot in self.slots if slot[item_type] == 0), None)

    def release(self, item):
        for slot in self.slots:
            if slot is item:
                slot[Item.FIELDS['type'][0]] = 0
                return None
        return item

    def clear(self):
        for slot in self.slots:
            slot[:] = bytes(Item.SIZE)


def item_pool(game):
    if getattr(game, 'item_pool', None) is None:
        game.item_pool = ItemPool()
    return game.item_pool


RUNTIME_DEFAULTS = {
    'mouse_mode': 1, 'trace': 0, 'slow_text': 1, 'vertical_top': 1, 'duel': 0,
    'no_border': 0, 'saved_search': 0, 'print_return': 0, 'sound_init': 1,
    'suppress_disk': 0, 'picture_name': '', 'saved_picture_name': '',
    'picture_id': 255, 'saved_picture_id': 255, 'show_turn': 1, 'big_id': 255,
    'marker_init': 0, 'auto_training': 0, 'selected_choice': 1, 'script_init': 0,
    'move_menu': 0, 'cursor_active': 0, 'extended_key': 0, 'mouse_click': 0,
    'selection_mode': 0, 'modify_active': 0, 'big_picture_shown': 0, 'last_mode': 1,
    'trade_character': None, 'highlighted_character': None, 'mouse_character': None,
    'bottom_line': '',
}


def reset_state(state, startup=False):
    old_wall = state.walls[0]
    previous = state.g.get('save.wall_pairs', ())
    first_pair = previous[0] if previous and previous[0][0] == old_wall else (old_wall, 65535 if old_wall == 65535 else 1 if old_wall == 0 else 0)
    for region in (state.r0, state.r1, state.r2): region[:] = [0] * len(region)
    state.code[:] = bytes(len(state.code))
    state.r0[0xE6], state.r0[0x1F4] = 1, 3
    state.r0[0x1F9:0x1FC] = [2, 2, 2]
    state.x, state.y, state.dir = 7, 13, 0 if startup else 2
    state.ahead = state.attr = state.block = state.party_dead = 0
    state.dataset = 5 if startup else 1
    state.mode, state.prev_mode, state.sel = 4, 0, 0
    state.party.clear()
    state.monsters.clear()
    empty = (65535, 65535)
    pairs = ((0, 1), empty, empty, empty) if startup else (first_pair, (0, 1), empty, empty)
    state.walls[:] = [pair[0] for pair in pairs]
    state.g.update({'save.wall_pairs': pairs, 'dkk.delay': 4, 'dkk.previous_disk': 1,
                    'camp.rest_ticks': 0, 'save.recent': 0, 'vault.pending': 0, 'vault.letter': 'Q',
                    'world.choice': 1, 'world.extended': 0, 'world.automap': 0, 'no_border': 0,
                    'dkk.encounter_menu': 0, 'dkk.item_pool': bytes(128 * 63),
                    'dkk.spans': (bytes(168), bytes(336), bytes([255]) * 336, bytes(336))})
    runtime = state.g.setdefault('dkk.runtime', {})
    runtime.update(RUNTIME_DEFAULTS)
    runtime['game_up'] = int(not startup)
    if startup:
        state.treasure_items.clear()
        state.g.update({'dkk.pictures': 1, 'dkk.animations': 1, 'camp.rest_active': False})
        runtime.update(demo=0, music_on=1, sound_saved=0, sound_active=0, music_driver_loaded=0,
                       camp_rest_active=False, current_music=255, dungeon_combat_loaded=0,
                       wilderness_combat_loaded=0, music_data=None, music_size=0, restart_loop=0)


def initialize(state):
    reset_state(state, startup=True)


def reset_game(game, startup=False):
    reset_state(game.s, startup=startup)
    if getattr(game, 'item_pool', None) is not None:
        game.item_pool.clear()
    game.menu_highlight = 0
    game.trade_character = None
    game.age_pass = False
    game.handler_override_active = False
    game.menu_note = ''
    vm = game.vm
    vm.pc, vm.resuming, vm.box_cleared = 0x8000, False, False
    vm.party_drawn()
    vm.cache.clear()
    vm.visual.update(graphics=False, sprite=False, wall_color=219, ceiling_color=232)
    vm.display.update(kind=None, id=255, automap=False, wall_color=219, ceiling_color=232)
    if startup:
        vm.icons.clear()
        game.combat_magic = False


def last_member_removed(game):
    if game.s.chars(): return False
    reset_game(game)
    game.s.prev_mode, game.s.mode = 4, 0
    game.s.g['dkk.runtime'].update(mouse_mode=0, test_training=0, restart_loop=1)
    return True


def input_config_path(game):
    from .intake import config_path
    path = config_path().with_name('dkk-input.cfg')
    root = game.assets.root.resolve()
    if path.resolve().is_relative_to(root) or path.parent.resolve().is_relative_to(root):
        raise ValueError('Death Knights originals are read-only; use a separate configuration directory')
    return path


def read_input_config(game):
    from sm.files import file_path
    from .faults import BindingRequired
    path = input_config_path(game)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        try:
            raw = file_path(game.assets.root, 'KRYNN.CFG').read_bytes()
        except FileNotFoundError:
            return None
    if not raw: return None
    header = raw.splitlines()[:5]
    if len(header) != 5:
        raise BindingRequired('Incomplete input configuration header')
    return tuple(line[:255] for line in header)


def write_input_config(game, header, mode, calibration=()):
    from pathlib import Path
    from tempfile import NamedTemporaryFile
    if mode not in ('M', 'N', 'J'): raise ValueError('Unknown input mode')
    raw = b''
    if header is not None:
        if len(header) != 5 or any(not isinstance(line, bytes) or len(line) > 255 or
                                    b'\r' in line or b'\n' in line for line in header):
            raise ValueError('Expected five configuration header lines')
        lines = list(header)
        lines[2] = mode.encode('ascii')
        if mode == 'J':
            pairs = tuple(calibration)
            if len(pairs) != 7 or any(len(pair) != 2 for pair in pairs):
                raise ValueError('Expected seven joystick coordinate pairs')
            values = [value for pair in pairs for value in pair]
            if any(type(value) is not int or not 0 <= value <= 65535 for value in values):
                raise ValueError('Joystick calibration values must fit a word')
            lines.extend(str(value).encode('ascii') for value in values)
        else:
            lines.extend([b'0'] * 14)
        raw = b'\r\n'.join(lines) + b'\r\n'
    path = input_config_path(game)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        temporary.replace(path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def test():
    from .menu import Game
    from sm.titles.ssb.state import State
    state = State()
    state.seed = 4660
    state.g.update({'camp.rest_active': True, 'no_border': 1})
    state.g['dkk.runtime'] = {'restart_loop': 1}
    initialize(state)
    assert (state.dataset, state.x, state.y, state.dir) == (5, 7, 13, 0)
    assert state.walls == [0, 65535, 65535, 65535]
    assert state.g['save.wall_pairs'][0] == (0, 1) and state.seed == 4660
    assert state.g['dkk.pictures'] == state.g['dkk.animations'] == 1
    assert not state.g['camp.rest_active'] and state.g['no_border'] == 0
    assert state.g['dkk.runtime']['restart_loop'] == 0
    game = Game(None)
    pool = item_pool(game)
    first = pool.allocate()
    assert first is pool.allocate()
    item_type = Item.FIELDS['type'][0]
    for index, slot in enumerate(pool.slots):
        assert pool.allocate() is slot
        slot[0], slot[item_type] = index + 1, 1
    assert pool.allocate() is None
    middle = pool.slots[64]
    external = bytearray(middle)
    assert pool.release(external) is external and pool.allocate() is None
    assert pool.release(middle) is None and pool.allocate() is middle
    assert middle[0] == 65 and middle[item_type] == 0 and external[item_type] == 1
    state = game.s
    state.seed = 9876
    state.r0[:] = [7] * 1024
    state.r1[:] = [8] * 1024
    state.r2[:] = [9] * 512
    state.code[:] = b'x' * len(state.code)
    state.walls[:] = [27, 18, 19, 20]
    state.g['save.wall_pairs'] = ((27, 3), (18, 0), (19, 2), (20, 1))
    state.g.update({'dkk.pictures': 0, 'dkk.animations': 0, 'save.recent': 1,
                    'world.choice': 5, 'world.extended': 1, 'world.automap': 1,
                    'camp.rest_active': True, 'no_border': 1, 'camp.effects_running': [0, 1] * 36,
                    'vault.pending': 1, 'vault.letter': 'A', 'unrelated': 55})
    state.g['dkk.runtime'] = dict(demo=1, music_on=0, sound_active=1, current_music=7, camp_rest_active=True, restart_loop=1)
    state.treasure_money[4:7] = [500, 2, 3]
    state.treasure_items = [bytearray(bytes(Item()))]
    game.age_pass = game.handler_override_active = game.combat_magic = True
    marker = object()
    game.menu_highlight = 2
    game.trade_character = marker
    game.geo.map = marker
    game.vm.icons[0] = marker
    game.vm.roster_shown, game.vm.ready_shown = 3, (1, 1, 0, 0)
    game.vm.gosub[:] = [0x8123]
    game.vm.flags[:] = [1] * 6
    game.vm.display.update(kind='PIC', id=21, automap=True)
    reset_game(game)
    assert item_pool(game) is pool and pool.allocate() is first
    assert all(slot == bytes(Item.SIZE) for slot in pool.slots)
    assert (state.x, state.y, state.dir, state.dataset, state.mode, state.prev_mode) == (7, 13, 2, 1, 4, 0)
    assert state.walls == [27, 0, 65535, 65535]
    assert state.g['save.wall_pairs'] == ((27, 3), (0, 1), (65535, 65535), (65535, 65535))
    assert not any(state.r1 + state.r2) and not any(state.code)
    assert {i: value for i, value in enumerate(state.r0) if value} == {0xE6: 1, 0x1F4: 3, 0x1F9: 2, 0x1FA: 2, 0x1FB: 2}
    assert state.seed == 9876 and state.g['unrelated'] == 55
    assert state.treasure_money[4:7] == [500, 2, 3] and len(state.treasure_items) == 1
    assert state.g['dkk.pictures'] == state.g['dkk.animations'] == 0
    assert state.g['dkk.runtime']['demo'] == state.g['dkk.runtime']['sound_active'] == 1
    assert state.g['dkk.runtime']['current_music'] == 7 and state.g['dkk.runtime']['camp_rest_active']
    assert state.g['dkk.runtime']['restart_loop'] == 1
    assert state.g['camp.rest_active'] and state.g['no_border'] == 0
    assert state.g['camp.effects_running'] == [0, 1] * 36
    assert state.g['save.recent'] == state.g['vault.pending'] == 0 and state.g['vault.letter'] == 'Q'
    assert (state.g['world.choice'], state.g['world.extended'], state.g['world.automap']) == (1, 0, 0)
    assert not game.age_pass and not game.handler_override_active and game.combat_magic
    assert game.menu_highlight == 0 and game.trade_character is None
    assert game.vm.roster_shown is None and game.vm.ready_shown is None
    assert game.geo.map is marker and game.vm.icons[0] is marker
    assert game.vm.gosub == [0x8123] and game.vm.flags == [1] * 6
    assert game.vm.pc == 0x8000 and not game.vm.resuming
    assert game.vm.visual['wall_color'] == 219 and game.vm.visual['ceiling_color'] == 232
    assert game.vm.display['kind'] is None and not game.vm.display['automap']
    for transition in (0, 1):
        state.restart = transition
        state.g['dkk.runtime']['restart_loop'] = 0
        assert last_member_removed(game)
        assert (state.mode, state.prev_mode, state.restart) == (0, 4, transition)
        assert state.g['dkk.runtime']['restart_loop'] == 1
    assert state.g['dkk.runtime']['mouse_mode'] == state.g['dkk.runtime']['test_training'] == 0
    state.party.append(marker)
    game.menu_highlight = 2
    game.trade_character = marker
    state.g['dkk.runtime']['restart_loop'] = 0
    assert not last_member_removed(game) and state.party == [marker]
    assert game.menu_highlight == 2 and game.trade_character is marker
    assert state.g['dkk.runtime']['restart_loop'] == 0 and state.restart == 1
    from .save import game_image
    state.party.clear()
    state.walls[0] = 65535
    reset_state(state)
    assert game_image(state, 'A').get('walls')[:4] == b'\xff' * 4
    state.walls[0] = 0
    state.g['save.wall_pairs'] = ((0, 0),)
    reset_state(state)
    assert game_image(state, 'A').get('walls')[:4] == bytes(4)
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace
    from unittest.mock import patch
    with TemporaryDirectory(prefix='sm-dkk-input-') as directory:
        root = Path(directory) / 'original'
        root.mkdir()
        (root / 'DKK.CFG').write_bytes(b'boot')
        game = SimpleNamespace(assets=SimpleNamespace(root=root))
        target = root.parent / 'private' / 'dkk-input.cfg'
        with patch('sm.titles.dkk.intake.config_path', return_value=target.with_suffix('.json')):
            assert read_input_config(game) is None and not target.parent.exists()
            write_input_config(game, None, 'N')
            assert target.read_bytes() == b'' and read_input_config(game) is None
            target.unlink()
            header = (b'\x82', b'', b'M', b'save path ', b'other')
            original = b'\r\n'.join(header + (b'old calibration',)) + b'\r\n'
            (root / 'krynn.cfg').write_bytes(original)
            assert read_input_config(game) == header and not target.exists()
            pairs = tuple((i, 65535-i) for i in range(7))
            for mode in ('J', 'M', 'N'):
                write_input_config(game, read_input_config(game), mode, pairs)
                expected = list(header)
                expected[2] = mode.encode('ascii')
                assert read_input_config(game) == tuple(expected)
                coords = [v for pair in pairs for v in pair] if mode == 'J' else [0] * 14
                expected.extend(str(v).encode('ascii') for v in coords)
                assert target.read_bytes() == b'\r\n'.join(expected) + b'\r\n'
            data = target.read_bytes()
            for invalid in (pairs[:-1], pairs[:6] + ((0, 65536),)):
                try: write_input_config(game, header, 'J', invalid)
                except ValueError: pass
                else: raise AssertionError('Invalid calibration accepted')
                assert target.read_bytes() == data
            assert (root / 'krynn.cfg').read_bytes() == original
            assert (root / 'DKK.CFG').read_bytes() == b'boot'
        with patch('sm.titles.dkk.intake.config_path', return_value=root / 'settings.json'):
            try: write_input_config(game, header, 'N')
            except ValueError: pass
            else: raise AssertionError('Original configuration directory accepted')
            assert not (root / 'dkk-input.cfg').exists()
