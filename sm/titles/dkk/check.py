import argparse
from . import intake

MODULES = ('faults', 'data', 'records', 'save', 'menu', 'creation', 'rules', '_creation_test', 'ecl', 'town', '_town_test',
           'effects', 'effects_handlers', 'effects_ability', '_effects_test', 'camp', 'shop', 'inventory', 'alter', 'temple', '_services_test', 'magic', 'combat', '_first_fight', 'ui.title', 'ui', 'ui.plus', 'ui._plus_test')


def check(directory=None):
    from importlib import import_module
    root = intake.require_folder(directory)
    assert intake.inspect_folder(root)['ok']
    bad = {'versions': [{'id': 'bad', 'label': 'test', 'files': {
        'START.EXE': {'size': -1, 'sha256': '0' * 64}}}], 'missing': 'test'}
    assert not intake.inspect_folder(root, bad)['ok']
    for module in MODULES:
        import_module('sm.titles.dkk.' + module).test()
    return len(MODULES) + 1


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder')
    args = parser.parse_args(arguments)
    count = check(args.folder)
    print('PASS dkk: %d checks' % count)
    return 0
