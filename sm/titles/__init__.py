"""Startup selection for installed title profiles; no process-global title switch."""


def select(name=None):
    from importlib import import_module
    from importlib.util import find_spec
    name = name or 'ssb'
    if not name.isidentifier() or name.startswith('_'):
        raise ValueError('invalid title: ' + name)
    module = 'sm.titles.' + name
    if find_spec(module) is None:
        raise ValueError('title is not installed: ' + name)
    return import_module(module)


def startup(arguments):
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--title', default='ssb')
    options, rest = parser.parse_known_args(arguments)
    return select(options.title), rest


def test():
    from importlib.util import find_spec
    from unittest import SkipTest
    if find_spec('sm.titles.dqk') is None:
        raise SkipTest('optional title package sm.titles.dqk is not included in this cut')
    from sm.titles import dqk
    dqk.test()
