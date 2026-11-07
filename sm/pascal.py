"""Per-game dependencies for the retained Pascal-family host and interpreter.

Bindings contain code/data providers, never simulation state. Native state hashes
remain owned by the selected title. No title module is imported during selection.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HostBinding:
    state: object
    vm: object
    geo: object
    load: object
    restore: object
    root: object
    initialize: object = None
    finished: object = None


@dataclass(frozen=True)
class VMBinding:
    records: object
    resident: object
    wrapped_text: object
    character: object
    read_character: object = None
    write_character: object = None
    icons: object = None
    service: object = None
    decoded: dict = field(default_factory=dict, compare=False, repr=False)
    codebytes: dict = field(default_factory=dict, compare=False, repr=False)


def test():
    from types import SimpleNamespace
    from sm.titles.ssb.host import Game
    events = []
    state = lambda: SimpleNamespace()
    geo = lambda: SimpleNamespace(resume=lambda s, v: events.append('resume'))
    vm = lambda s, ask, geo: SimpleNamespace(s=s, ask=ask, geo=geo)
    binding = HostBinding(state, vm, geo,
                          lambda path, slot: (events.append(('load', slot)), 7)[1],
                          lambda s, value: setattr(s, 'native', value), '.',
                          lambda s: setattr(s, 'native', 11))
    game = Game(None, slot=None, binding=binding)
    assert game.s.native == 11 and game.vm.s is game.s and not game.vm.resuming
    assert game.vm.geo is game.geo and game.vm.host is game and not events
    loaded = Game(None, slot='A', binding=binding)
    assert loaded.s.native == 7 and loaded.vm.resuming
    assert events == [('load', 'A'), 'resume']
    from sm.titles.ssb.vm import VM
    from sm.titles.ssb.state import State
    def native(tag):
        return VMBinding(lambda name: {17: tag}, lambda: tag,
                         lambda value: [value], lambda *args: None,
                         read_character=lambda vm, address: vm.s.g.get('field', tag[0]),
                         write_character=lambda vm, address, value: vm.s.g.__setitem__('field', value),
                         icons=lambda s: {}, service=lambda game, unit, name, *args: (tag, unit, name, args))
    left, right = VM(State(), None, binding=native(b'a')), VM(State(), None, binding=native(b'b'))
    left.host = right.host = None
    assert left.getmem(0x7C72) != right.getmem(0x7C72)
    left.setmem(0x7C72, 9)
    assert left.getmem(0x7C72) == 9 and right.getmem(0x7C72) == ord('b')
    assert left.binding.records('ECL1') != right.binding.records('ECL1')
    assert left.service('creation', 'run') == (b'a', 'creation', 'run', ())
    # Identical native block ids in two content providers must not share code.
    # Synthetic SAVE operands, with only the immediate value differing.
    for vm, value in ((left, 7), (right, 9)):
        vm.s.code[:20] = bytes((1, 2, 0x14, 0x80)) * 5
        vm.s.code[20:28] = bytes((0x09, 0, value, 1, 0, 0x4B, 0, 0))
        vm.pc = 0x8014
        vm.fetch()
        assert vm.v(1) == value
    assert left.decoded is not right.decoded
    assert left.codebytes is not right.codebytes
    assert left.code_addresses() == right.code_addresses()
    assert left.codebytes and right.codebytes
    # A self-modifying instruction uses the VM's private decode after a write.
    left.setmem(0x8016, 11)
    left.fetch(); right.fetch()
    assert left.v(1) == 11 and right.v(1) == 9
