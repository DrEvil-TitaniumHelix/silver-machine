import hashlib
import json
from pathlib import Path

from sm.files import DataError, file_path
from sm.pascal import HostBinding, VMBinding
from sm.titles.ssb.host import Game as RetainedGame
from sm.titles.ssb.state import State
from sm.titles.ssb.vm import VM, Halt, NoGeo
from sm.ui.art import decode, _pack
from .data import Assets
from .faults import BindingRequired
from . import rules, town




def initialize(state):
    state.dataset, state.block = 1, 0
    state.x, state.y, state.dir = 7, 13, 0
    state.mode, state.prev_mode = 4, 0
    state.walls = [0, 0xFFFF, 0xFFFF]
    state.r0[0x1F4], state.r0[0xE6] = 3, 1
    state.r0[0x1F9:0x1FC] = [2, 2, 2]
    state.g.update(bash=1, pick=1, knock=1)


class MenuAssets(Assets):
    def __init__(self, directory=None):
        super().__init__(directory)
        self.menu_layout = json.loads(Path(__file__).with_name('menu_layout.json').read_text())
        entries = self.part('main_menu')
        self.labels = tuple(entries[i * 42 + 1:i * 42 + 1 + entries[i * 42]]
                            .decode('cp437') for i in range(13))
        self.font = decode(self.records('8X8D1')[201], kind='F1').parts[0].frames
        self.border = decode(self.records('8X8D1')[202]).parts[0].frames

    def part(self, name):
        item = self.menu_layout[name]
        source = file_path(self.root, item['source']).read_bytes() if 'source' in item else self.resident
        raw = source[item['offset']:item['offset'] + item['size']]
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise DataError('Champions menu fingerprint differs: ' + name)
        return raw

    def text(self, name):
        raw = self.part(name)
        return raw[1:1 + raw[0]].decode('cp437')

    def glyph(self, ch):
        number = ord(ch)
        number = number - 32 if 97 <= number <= 122 else number
        return _pack(self.font[number % 64], 8, 8, 1)

    def choices(self, state):
        enabled = set((0, 6, 12))
        if state.party:
            enabled.update((1, 2, 5, 7, 9, 10))
            if state.r1[0x2A8] or state.g.get('free_training'):
                enabled.update((3, 4))
        else:
            enabled.update((8, 11))
        return tuple(sorted(enabled))


class Game(RetainedGame):
    def __init__(self, player, slot=None, engines=True, directory=None):
        self.assets = assets = MenuAssets(directory)
        vm_binding = VMBinding(assets.records, lambda: assets.resident,
                               lambda text: town.wrapped_text(text), rules.character,
                               read_character=town.read_character, write_character=town.write_character,
                               icons=lambda state: {}, service=self.service)
        vm_class = getattr(town, 'VM', VM)
        binding = HostBinding(State, lambda s, ask, geo: vm_class(s, ask, geo, binding=vm_binding),
                              town.Geo, rules.load_slot, rules.restore, assets.root,
                              initialize, finished=town.finished)
        super().__init__(player, slot=None, engines=engines, directory=assets.root, binding=binding)
        if slot is not None:
            if not hasattr(town, 'load_game'): raise BindingRequired('Champions town.load_game is not bound')
            town.load_game(self, slot)

    def service(self, game, unit, name, *arguments):
        from . import creation
        if unit == 'creation': return getattr(creation, name)(game, *arguments)
        return town.service(game, unit, name, *arguments)

    def play(self, limit=100_000):
        if self.slot is None: self.vm.service('creation', 'run')
        if getattr(self.s, 'stop', False): return 'EXIT'
        if not hasattr(town, 'play'): raise BindingRequired('Champions town.play is not bound')
        return town.play(self, limit=limit)


def render(game, selected=0):
    from sm.titles.ssb.ui.screen import Frame
    frame, assets = Frame(), game.assets
    top, side = assets.part('topEdgeTiles'), assets.part('leftEdgeTiles')
    top = bytearray(top)
    for column, cell, bias in ((8, 0x1F9, 10), (19, 0x1FA, 6), (30, 0x1FB, 14)):
        top[column] = game.s.r0[cell] + bias
    placements = [(x, 0, tile) for x, tile in enumerate(top)]
    placements += [(x, y, 4 if 15 <= y <= 17 else tile)
                   for y, tile in enumerate(side) for x in (0, 39)]
    placements += [(x, 23, 0) for x in range(40)]
    for x, y, tile in placements:
        frame.blit(x * 8, y * 8, assets.border[20 + tile])
    ids = assets.choices(game.s)
    for row, ident in enumerate(ids):
        frame.text(9, 12 + row, assets.labels[ident], assets,
                   colour=0 if row == selected else 10, background=15 if row == selected else 0)
    query = assets.text('query')
    frame.text(0, 24, query, assets, colour=13)
    frame.text(len(query), 24, assets.text('select'), assets, colour=10)
    return frame
