from .vm import Halt as Fault
from .resolve import resolve as resolve_decision
from sm.titles.ssb.intake import require_folder as require_content

name = 'ssb'
presentation = 'sm.titles.ssb.ui.screen'
ui_module = 'sm.titles.ssb.ui'
strict_choices = False
typed_inputs = False
automatic = frozenset(('COMBAT', 'TREASURE', 'CAMP', 'TEMPLE', 'VAULT', 'CREATE', 'ACK'))
commands = frozenset(('test', 'route', 'run', 'maxrun', 'replay', 'dump', 'cells', 'serve'))


def create_game(player, *, slot='A', engines=False, directory=None):
    from .host import Game
    return Game(player, slot, engines, directory)


def run_cli(command, arguments, local):
    from . import _cli
    return getattr(_cli, command)(arguments, local)
