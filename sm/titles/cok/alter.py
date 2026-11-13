from enum import Enum

from . import creation
from .creation import DELAY, ANIMATIONS, PICTURES, F, choose, customize_icon, game_setting, member_title, pick_member, remove_creature, yes_no

DIFFICULTY_CELL = 0x1F4


class Kind(str, Enum):
    MENU = 'ALTER'
    ORDER = 'ALTER_ORDER'
    LEVEL = 'ALTER_LEVEL'
    SPEED = 'ALTER_SPEED'
    PICS = 'ALTER_PICS'
    CONFIRM = 'ALTER_CONFIRM'
    ACK = 'ACK'


LEVELS = ('Novice', 'Squire', 'Veteran', 'Adept', 'Champion')


def ack(game, text):
    game.ask(Kind.ACK.value, ('Continue',), prompt=text)


def move(s, step):
    index = s.sel
    if len(s.party) < 2: return
    if step < 0 and index == 0 or step > 0 and index == len(s.party) - 1:
        char = s.party.pop(index)
        if step < 0: s.party.append(char)
        else: s.party.insert(0, char)
        s.sel = len(s.party) - 1 if step < 0 else 0
    else:
        s.party[index], s.party[index + step] = s.party[index + step], s.party[index]
        s.sel = index + step


def order(game):
    s = game.s
    while True:
        names = ', '.join(member_title(c) for c in s.party)
        pick = choose(game, Kind.ORDER, 'Party Order: ', ('Previous', 'Next', 'Up', 'Down'), party=names, member=member_title(s.party[s.sel]))
        if pick is None: return
        if pick == 0: s.sel = (s.sel - 1) % len(s.party)
        elif pick == 1: s.sel = (s.sel + 1) % len(s.party)
        elif pick == 2: move(s, -1)
        else: move(s, 1)


def drop(game):
    s = game.s
    char = pick_member(game)
    if char is None: return False
    name = member_title(char)
    if len(s.party) == 1:
        if yes_no(game, Kind.CONFIRM, 'quit TO DOS: '):
            remove_creature(game, char)
            s.stop = 1
            game.exit_game = True
            return True
        return False
    if yes_no(game, Kind.CONFIRM, 'Drop from party? ', offer=name + ' will be gone'):
        ack(game, name + (' bids you farewell' if char.b[F['active']] else ' is dumped in a ditch'))
        remove_creature(game, char)
    else: ack(game, name + ' Breathes A sigh of relief')
    return False


def level(game):
    s = game.s
    pick = choose(game, Kind.LEVEL, 'Level', LEVELS, level=s.r0[DIFFICULTY_CELL] & 255,
                  start=min(4, max(0, (s.r0[DIFFICULTY_CELL] & 255) - 1)))
    if pick is not None: s.r0[DIFFICULTY_CELL] = pick + 1


def speed(game):
    s = game.s
    while True:
        delay = game_setting(s, DELAY)
        options = (('Faster',) if delay > 0 else ()) + (('Slower',) if delay < 9 else ())
        pick = choose(game, Kind.SPEED, 'Game Speed:', options, speed=delay)
        if pick is None: return
        s.g[DELAY] = delay - 1 if options[pick] == 'Faster' else delay + 1


def pics(game):
    s = game.s
    while True:
        on, animated = game_setting(s, PICTURES), game_setting(s, ANIMATIONS)
        options = ('Pics on', 'Animation on' if animated else 'Animation off') if on else ('Pics off',)
        pick = choose(game, Kind.PICS, '', options)
        if pick is None: return
        if pick == 0: s.g[PICTURES] = int(not on)
        else: s.g[ANIMATIONS] = int(not animated)


def run(game):
    while True:
        pick = choose(game, Kind.MENU, '', ('Order', 'Drop', 'Speed', 'Icon', 'Pics', 'Level'))
        if pick is None: return False
        if pick == 0: order(game)
        elif pick == 1:
            if drop(game): return True
        elif pick == 2: speed(game)
        elif pick == 3:
            char = pick_member(game)
            if char is not None: customize_icon(game, char.b)
        elif pick == 4: pics(game)
        else: level(game)
