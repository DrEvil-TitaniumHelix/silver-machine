from enum import Enum
from sm.titles.cok.alter import move
from .creation import choose, yes_no, customize_icon, PARTY_SIZE
from .camp import name


class Kind(str, Enum):
    MENU = 'ALTER'
    ORDER = 'ALTER_ORDER'
    LEVEL = 'ALTER_LEVEL'
    SPEED = 'ALTER_SPEED'
    WHO = 'WHO'
    CONFIRM = 'ALTER_CONFIRM'


def run(game):
    s = game.s
    while s.party:
        pick = choose(game, Kind.MENU, 'Alter', ('Order', 'Drop', 'Speed', 'Icon', 'Level'))
        if pick is None: return
        if pick == 0:
            while True:
                action = choose(game, Kind.ORDER, 'Party Order', ('Previous', 'Next', 'Up', 'Down'), member=name(s.selc()))
                if action is None: break
                if action < 2: s.sel = (s.sel + (-1 if action == 0 else 1)) % len(s.party)
                else: move(s, -1 if action == 2 else 1)
        elif pick == 1:
            who = choose(game, Kind.WHO, 'Drop whom?', tuple(name(c) for c in s.party))
            if who is not None and yes_no(game, Kind.CONFIRM, 'Quit to DOS?' if len(s.party) == 1 else 'Drop from party?'):
                s.party.pop(who)
                s.sel = min(s.sel, max(0, len(s.party) - 1))
                s.r1[PARTY_SIZE] = len(s.party)
                if not s.party: s.stop = 1; return
        elif pick == 2:
            while True:
                delay = s.g.get('dkk.delay', 4)
                options = tuple(label for label, enabled in (('Faster', delay > 0), ('Slower', delay < 9)) if enabled)
                choice = choose(game, Kind.SPEED, 'Game Speed', options, speed=delay)
                if choice is None: break
                s.g['dkk.delay'] = delay + (-1 if options[choice] == 'Faster' else 1)
        elif pick == 3: customize_icon(game, s.selc().b)
        else:
            level = choose(game, Kind.LEVEL, 'Level', ('Novice', 'Squire', 'Veteran', 'Adept', 'Champion'))
            if level is not None: s.r0[0x1F4] = level + 1


def test():
    from sm.titles.ssb.state import State
    s = State()
    s.party, s.sel = [1, 2, 3], 0
    move(s, -1)
    assert s.party == [2, 3, 1] and s.sel == 2
