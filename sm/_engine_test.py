"""Cross-profile transport, validation and continuation regressions."""
from importlib.util import find_spec
from sm.engine import Decision, Session, legal_choice, play
from sm.titles import select, startup


def refused(call):
    try: call()
    except ValueError: return
    raise AssertionError('invalid decision accepted')


def test():
    third_profile()
    assert legal_choice(('one',), False)  # Existing SSB and raw VM contract.
    assert not legal_choice(('one',), False, strict=True)
    for value in (-1, 1, '0', 0.0):
        refused(lambda: Decision('MENU', ('one',)).validate(value))
    for value in (-1, 65536, '1'):
        refused(lambda: Decision('NUMBER').validate(value))
    for value in (None, 1, 'x' * 41):
        refused(lambda: Decision('STRING').validate(value))
    Decision('NUMBER').validate(65535)
    Decision('STRING').validate('x' * 40)
    ssb, rest = startup(['--title', 'ssb', '--seed', '7'])
    assert ssb is select() and rest == ['--seed', '7']
    refused(lambda: select('../ssb'))
    refused(lambda: select('not_installed'))
    if find_spec('sm.titles.dqk') is None: return  # Public cut has only SSB.
    from sm.titles.dqk._loop_test import fixture
    from sm.titles.dqk._vm_test import instruction, operand
    from sm.titles.dqk.vm import Fault
    dqk = select('dqk')
    code = instruction(0x15, (3, 0x100), (0x80, 'TEST'), (0, 2))
    code += operand(0x80, 'ALPHA') + operand(0x80, 'BETA') + b'\0'
    def prepared():
        game = fixture(code)
        game.boot = game.drive  # Start the synthetic VM at its prepared entry.
        return game
    direct = prepared()
    direct.boot()
    before = direct.state_hash()
    direct.answer(1)
    game = prepared()
    session = Session(profile=dqk, game=game, limit=1)
    try:
        assert session.decision['kind'] == 'LIST' and session.decision['hash'] == before
        for bad in (True, -1, 2):
            refused(lambda: session.step(bad))
            assert game.state_hash() == before and not game.trace
        assert session.step(1) is None and session.result == 'LIMIT'
        assert game.trace == direct.trace and game.state_hash() == direct.state_hash()
    finally: session.close()
    assert not session._worker.is_alive()
    # Bad typed input leaves the same pending continuation usable.
    number = fixture(instruction(0x0F, (0, 0), (3, 0x100)) + b'\0')
    number.boot = number.drive
    session = Session(profile=dqk, game=number, limit=1)
    try:
        before_number = number.state_hash()
        assert session.decision['kind'] == 'NUMBER'
        for bad in ('7', True, -1, 65536):
            refused(lambda: session.step(bad))
            assert number.state_hash() == before_number and not number.trace
        session.step(7)
        assert number.vm.get(0x100) == 7
    finally: session.close()
    # A policy failure propagates and releases the worker without an answer/write.
    game = prepared()
    def fail(*args, **info): raise Fault('synthetic policy failure')
    try: play(game, fail, profile=dqk)
    except Fault as error: assert str(error) == 'synthetic policy failure'
    else: raise AssertionError('policy failure was swallowed')
    assert not game.trace and game.state_hash() == before


def third_profile():
    """An installed third profile uses startup, commands and transport unchanged."""
    import sys
    from contextlib import redirect_stdout
    from importlib.machinery import ModuleSpec
    from io import StringIO
    from types import ModuleType
    from unittest.mock import patch
    from sm.__main__ import main
    from sm import titles
    profile = ModuleType('sm.titles.synthetic')
    profile.__spec__ = ModuleSpec(profile.__name__, loader=None)
    profile.name, profile.Fault = 'synthetic', ValueError
    profile.commands = frozenset(('run', 'serve'))
    profile.strict_choices = profile.typed_inputs = True
    profile.automatic = frozenset()
    created = []
    class Game:
        def __init__(self, player, **options):
            self.player, self.trace, self.value = player, [], 0
            created.append(self)
        def state_hash(self): return str(self.value)
        def play(self, limit):
            for _ in range(min(limit, 3)):
                answer = self.player('MENU', ('stay', 'advance'), self)
                self.trace.append((self.state_hash(), answer))
                self.value += answer
            return 'DONE'
    profile.create_game = Game
    def command(name, arguments, local):
        assert (name, arguments, local) == ('run', ['--example'], 'synthetic-local')
        game = Game(None)
        assert play(game, lambda *args, **info: 1, profile=profile) == 'DONE'
        assert game.trace == [('0', 1), ('1', 1), ('2', 1)] and game.value == 3
        return 7
    profile.run_cli = command
    with patch.dict(sys.modules, {profile.__name__: profile}):
        with patch.object(titles, 'select', wraps=titles.select) as selection:
            assert main(['run', '--title', 'synthetic', '--example'], local='synthetic-local') == 7
            selection.assert_called_once_with('synthetic')
        refused(lambda: main(['route', '--title', 'synthetic']))
        output = StringIO()
        with patch.object(sys, 'stdin', StringIO('1\n1\n1\n')), redirect_stdout(output):
            assert main(['serve', '--title', 'synthetic']) is None
        assert created[-1].value == 3 and '"result": "DONE"' in output.getvalue()
