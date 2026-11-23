from sm.pascal import HostBinding, VMBinding
from sm.titles.ssb.host import Game as RetainedGame
from sm.titles.ssb.state import State
from sm.titles.ssb.vm import VM, NoGeo
from sm.titles.cok.menu import MenuAssets as FamilyMenuAssets
from sm.ui.art import decode
import re
from .data import Assets
from . import town, rules


def initialize(state):
    from . import save_start
    save_start.initialize(state)
    state.dataset = 1
    state.g.update(bash=1, pick=1, knock=1)


class MenuAssets(Assets):
    glyph = FamilyMenuAssets.glyph

    def __init__(self, directory=None):
        super().__init__(directory)
        self.labels = self.names('partyMenuItems')
        self.font = decode(self.records('8X8D1')[201], kind='F1').parts[0].frames
        self.border = decode(self.records('8X8D1')[202]).parts[0].frames

    def choices(self, state):
        enabled = {0, 6, 12}
        if state.party or state.selc() is not None:
            enabled.update((1, 2, 5, 7, 9, 10))
            if state.r1[0x2A8] or state.g.get('free_training'): enabled.update((3, 4))
        else: enabled.update((8, 11))
        return tuple(sorted(enabled))

    def text(self, name):
        return '' if name == 'query' else super().text('selectMenuText' if name == 'select' else name)


TOKEN = re.compile(r'[!,\-.:;?]*[^!,\-.:;? ]*(?:[!,\-.:;?]+| |$)')


def wrapped_text(text, width=38):
    if width < 1: raise ValueError('text width must be positive')
    lines = []
    for paragraph in text.rstrip().splitlines():
        row, skipping = '', False
        for token in TOKEN.findall(paragraph):
            if skipping: token = token.lstrip(' ')
            if not token: continue
            skipping = False
            if len(row)+len(token) > width:
                lines.append(row.rstrip()); row = ''; token = token.lstrip(' ')
                if not token: skipping = True; continue
            row += token
        lines.append(row.rstrip())
    return lines


DIRECTIONS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')


def misc_info(game):
    s = game.s
    if s.mode == 3: return None
    text = ('' if s.r0[0xFB] else '%d,%d ' % (s.x, s.y)) + DIRECTIONS[s.dir % 8]
    text += ' %02d:%02d' % (s.r0[0xC9], s.r0[0xC8] * 10 + s.r0[0xC7]) + '*' * bool(s.g.get('dkk.runtime', {}).get('trace'))
    return text + (' camping' if s.mode == 2 else ' search' if s.r1[0x2CA] & 1 else '')


class Game(RetainedGame):
    def __init__(self, player, slot=None, engines=True, directory=None):
        self.assets = assets = MenuAssets(directory)
        vm_binding = VMBinding(assets.records, lambda: assets.resident,
                              wrapped_text, rules.character,
                              read_character=town.read_character, write_character=town.write_character,
                              icons=lambda state: {}, service=self.service)
        binding = HostBinding(State, lambda s, ask, geo: town.VM(s, ask, geo, binding=vm_binding),
                              town.Geo, rules.load_slot, rules.restore, assets.root,
                              initialize, finished=lambda game: False)
        super().__init__(player, slot=None, engines=engines, directory=assets.root, binding=binding)
        self.loaded = False
        if slot is not None:
            from . import creation
            if (creation.save_directory() / ('SAVGAM%s.PTY' % str(slot).upper())).is_file():
                creation.load_slot(self, slot)
                self.loaded = True

    def service(self, game, unit, name, *arguments):
        from . import creation
        if unit == 'creation':
            return getattr(creation, name)(game, *arguments)
        return town.service(game, unit, name, *arguments)

    def play(self, limit=100_000):
        from . import creation, save_start
        while True:
            if not self.loaded and not getattr(self.s, 'g', {}).get('dkk.runtime', {}).get('demo', 0): creation.run(self)
            if self.s.stop:
                return 'EXIT'
            result = town.play(self, limit=limit)
            if result != 'DEFEAT' or getattr(self, 'first_fight_only', True): return result
            save_start.reset_game(self)
            self.loaded = False


def frame(game):
    from sm.titles.ssb.ui.screen import Frame
    result, assets = Frame(), game.assets
    top = bytearray(assets.part('borderTopRow'))
    for column, phase, bias in ((8, 0x1F9, 21), (19, 0x1FA, 13), (30, 0x1FB, 17)):
        top[column] = game.s.r0[phase] + bias
    for row, tiles in ((0, top), (23, assets.part('borderBottomRow'))):
        for x, tile in enumerate(tiles):
            result.blit(x * 8, row * 8, assets.border[tile])
    for row in range(1, 23):
        for column in (0, 39):
            result.blit(column * 8, row * 8, assets.border[7])
    return result


def render(game, selected=0):
    result = frame(game)
    for row, ident in enumerate(game.assets.choices(game.s)):
        result.text(9, 12 + row, game.assets.labels[ident], game.assets,
                    colour=0 if row == selected else 10, background=15 if row == selected else 0)
    result.text(0, 24, game.assets.text('selectMenuText'), game.assets, colour=10)
    return result


def test():
    from sm.engine import Session
    assert wrapped_text('a'*37+'.  Next') == ['a'*37+'.', 'Next']
    assert wrapped_text('a'*36+'   b') == ['a'*36, 'b']
    assert wrapped_text('one two') == ['one two']
    from sm.titles.ssb.state import State
    linked = State(); linked.monsters, linked.sel = [object()], 0
    assert MenuAssets.choices(None, State()) == (0, 6, 8, 11, 12) and MenuAssets.choices(None, linked) == (0, 1, 2, 5, 6, 7, 9, 10, 12)
    from types import SimpleNamespace
    s = SimpleNamespace(mode=4, x=7, y=13, dir=0, r0=bytearray(512), r1=bytearray(1024), g={})
    assert misc_info(SimpleNamespace(s=s)) == '7,13 N 00:00'
    s.r0[0xFB], s.r0[0xC9], s.r0[0xC8], s.r0[0xC7], s.r1[0x2CA], s.dir = 1, 9, 3, 5, 1, 6
    assert misc_info(SimpleNamespace(s=s)) == 'W 09:35 search'
    s.mode = 2; assert misc_info(SimpleNamespace(s=s)).endswith(' camping')
    s.g['dkk.runtime'] = dict(trace=1); assert misc_info(SimpleNamespace(s=s)) == 'W 09:35* camping'
    s.mode = 3; assert misc_info(SimpleNamespace(s=s)) is None
    checkpoints = []
    for _ in range(2):
        session = Session(profile='dkk', slot=None)
        try:
            assert session.error is None, session.error
            assert session.decision['kind'] == 'CREATE_MENU'
            assert session.game.menu_ids == (0, 6, 8, 11, 12)
            pixels = b''.join(render(session.game).rows)
            assert len(pixels) == 64000 and max(pixels) < 16
            checkpoints.append((session.decision['hash'], pixels))
            session.step(4)
            session.step(0)
            assert session.result == 'EXIT' and session.error is None
        finally:
            session.close()
    assert checkpoints[0] == checkpoints[1]
    from unittest.mock import patch
    from . import creation, save_start
    for only, runs, result in ((False, 2, 'EXIT'), (True, 1, 'DEFEAT')):
        game, seen = SimpleNamespace(loaded=True, first_fight_only=only, s=SimpleNamespace(stop=0)), []
        def run(host): seen.append('menu'); host.s.stop = len(seen) > 1
        with patch.object(creation, 'run', run), patch.object(town, 'play', lambda host, limit: 'DEFEAT'), patch.object(save_start, 'reset_game', lambda host: seen.append('reset')):
            assert Game.play(game) == result and seen.count('menu') == runs - 1 and seen.count('reset') == runs - 1, (only, seen)
