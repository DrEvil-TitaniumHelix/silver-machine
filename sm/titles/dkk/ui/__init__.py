from pathlib import Path

START_SLOTS = ()
SAVE_SLOTS = tuple('ABCDEFGHIJ')


def start_session(slot=None, load=None, root=None, saves=None, *, directory=None, seed=None, title=True, demo=False):
    from sm.engine import Session
    from ..menu import Game
    from .. import creation
    game = Game(None, slot=None, directory=directory)
    game.first_fight_only = False
    if saves or root: game.roster_directory = Path(saves or root)
    if seed is not None: game.s.seed = seed
    if load:
        creation.load_slot(game, load)
        game.loaded = True
    game.title = 1 if title and not load else None
    if demo: game.s.g.setdefault('dkk.runtime', {})['demo'] = 1; game.s.g['dkk.delay'] = 9; game.presentation = __import__('collections').deque()
    return Session(profile='dkk', game=game, engines=True)


def check(fight=False):
    from ._screen_test import test
    test()


def test(): check()
