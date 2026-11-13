from pathlib import Path
from sm.engine import Session

START_SLOTS = ('A',)
SAVE_SLOTS = tuple('ABCDEFGHIJ')


class ViewSession(Session):
    def __init__(self, *args, loaded=False, **kwargs):
        self.view_pending = loaded
        super().__init__(*args, **kwargs)
        self.refresh_view()

    def refresh_view(self):
        if self.view_pending and self.decision and self.decision['kind'] == 'MOVE':
            from .. import town
            if self.game.vm.is3d(): town.refresh(self.game)
            self.view_pending = False

    def step(self, answer):
        d = self.decision
        decision = super().step(answer)
        if d and d['info'].get('action') == 'main-menu' and d['options'][answer] == 'Begin Adventuring':
            self.view_pending = True
        self.refresh_view()
        return decision


def start_session(slot=None, load=None, root=None, saves=None, *, directory=None, seed=None):
    from ..menu import Game
    from .. import creation, rules, save
    game = Game(None, slot=None, directory=directory)
    game.rest_poll = True
    if saves or root: game.roster_directory = Path(saves or root)
    if seed is not None: game.s.seed = seed
    if load:
        creation.load_game(game, load)
        game.s.prev_mode, game.s.mode = game.s.mode, 0
        game.vm.resuming = True
        game.geo.resume(game.s, game.vm)
    elif slot:
        snapshot = rules.load_slot(game.assets.root / 'SAVE', slot)
        save.apply_image(game.s, snapshot.game); rules.restore(game.s, snapshot)
        game.s.r1[0x33E] = len(game.s.party)
        game.slot, game.vm.resuming = slot, True
        game.geo.resume(game.s, game.vm)
    return ViewSession(profile='cok', game=game, engines=True, loaded=bool(load or slot))


def check(fight=False):
    if fight: raise ValueError('Champions combat is not certified by the town gate')
    from ._screen_test import test
    test()


def test(): check()
