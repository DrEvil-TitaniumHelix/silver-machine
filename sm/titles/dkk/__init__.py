from . import intake

name = 'dkk'
presentation = 'sm.titles.dkk.ui.screen'
ui_module = 'sm.titles.dkk.ui'
commands = frozenset(('test', 'run', 'serve'))
automatic = frozenset()
strict_choices = typed_inputs = True
require_content = intake.require_folder


def create_game(player, slot=None, engines=True, directory=None):
    from .menu import Game
    return Game(player, slot=slot, engines=engines, directory=directory)


def __getattr__(name):
    if name == 'Fault':
        from .faults import BindingRequired
        return BindingRequired
    raise AttributeError(name)


def test():
    from unittest import SkipTest
    if not intake.configured():
        raise SkipTest('SM_DKK not set: Death Knights checks skipped')
    from .check import check
    return check()


def run_cli(command, arguments, local):
    if command == 'test':
        from .check import main
        return main(arguments)
    from ._first_fight import main
    return main(arguments)
