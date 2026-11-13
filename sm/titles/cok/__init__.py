from . import intake

name = 'cok'
commands = frozenset(('test', 'run', 'serve'))
automatic = frozenset()
strict_choices = typed_inputs = True
presentation = 'sm.titles.cok.ui.screen'
ui_module = 'sm.titles.cok.ui'
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
    from importlib import import_module
    from unittest import SkipTest
    if not intake.configured(): raise SkipTest('SM_COK not set: Champions checks skipped')
    for module in ('rules', 'creation', 'camp', 'shop', 'training', 'effects', 'magic', 'temple', 'inventory', 'alter', 'combat', 'town', 'ui.screen', '_rules_test', '_creation_test', '_camp_test', '_shop_test', '_training_test', '_effects_test', '_magic_test', '_temple_test', '_inventory_test', '_alter_test', '_oracle_test', '_fightcheck_test', '_combat_test', '_town_test', 'ui._screen_test'):
        try: m = import_module('sm.titles.cok.' + module)
        except ImportError: continue
        if callable(getattr(m, 'test', None)): m.test()


def run_cli(command, arguments, local):
    if command == 'test':
        from .check import main
        return main(arguments)
    from . import _cli
    return getattr(_cli, command)(arguments, local)
