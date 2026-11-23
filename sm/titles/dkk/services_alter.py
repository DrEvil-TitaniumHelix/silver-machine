from . import camp, creation
from .shop import horizontal, select_adjacent


def move(state, step):
    characters = state.chars()
    destination = (state.sel + step) % len(characters)
    member = characters.pop(state.sel)
    characters.insert(destination, member)
    state.sel = destination
    split = len(state.party)
    state.party[:], state.monsters[:] = characters[:split], characters[split:]


def order(game):
    s, placing, start, message = game.s, False, 0, ''
    try:
        while True:
            options = ('Place' if placing else 'Select', 'Exit', *camp.MEMBER_KEYS)
            s.g['camp.order_mode'] = int(placing)
            pick = horizontal(game, 'ALTER_ORDER', options, prompt=game.assets.text('orderQuery'), member=camp.name(s.selc()),
                              start=start, message=message, placing=placing, escape_choice=1)
            start = game.menu_highlight
            key = options[pick]
            if key == 'Exit': return
            if key in camp.MEMBER_KEYS:
                if placing:
                    move(s, -1 if key == 'char-up' else 1)
                    game.vm.party_drawn()
                else: select_adjacent(game, key)
            else:
                placing = not placing
                message = camp.name(s.selc()) + ' ' + game.assets.text('hasBeenSelected') if placing else ''
    finally:
        s.g['camp.order_mode'] = 0


def drop(game):
    s, a = game.s, game.assets
    char = s.selc()
    if len(s.chars()) == 1:
        if creation.yes_no(game, camp.Kind.CONFIRM, a.text('quitToDosPrompt'), start=1):
            game.vm.remove_selected()
            s.stop = 1
            game.exit_game = True
        return
    if creation.yes_no(game, camp.Kind.CONFIRM, 'Drop from party? ', start=1,
                       offer=camp.name(char) + ' ' + a.text('goneForever')):
        camp.ack(game, 'bids you farewell' if char.b[camp.F['active']] else 'is dumped in a ditch', char)
        game.vm.remove_selected()
        game.vm.party_drawn()
    else: camp.ack(game, 'Breathes A sigh of relief', char)


def level(game):
    s = game.s
    options = ('Novice', 'Squire', 'Veteran', 'Adept', 'Champion', *camp.MEMBER_KEYS, 'Exit')
    pick = game.ask('ALTER_LEVEL', options, prompt='', level=s.r0[0x1F4], start=max(0, min(4, s.r0[0x1F4] - 1)),
                    menu_labels=options[:5], escape_choice=len(options) - 1)
    if options[pick] in camp.MEMBER_KEYS: select_adjacent(game, options[pick])
    elif pick < 5: s.r0[0x1F4] = pick + 1


def speed(game):
    s, a, start = game.s, game.assets, 0
    while True:
        delay = s.g.get('dkk.delay', 4)
        options = tuple(label for label, enabled in (('Faster', delay > 0), ('Slower', delay < 9)) if enabled)
        options += ('Exit', 'char-down', 'char-up')
        pick = horizontal(game, 'ALTER_SPEED', options, prompt=a.text('gameSpeedLabel'), speed=delay,
                          message=a.text('gameSpeedPrompt') + str(delay), start=start, escape_choice=len(options) - 3)
        start = game.menu_highlight
        key = options[pick]
        if key == 'Exit': return
        s.g['dkk.delay'] = max(0, min(9, delay + (-1 if key in ('Faster', 'char-down') else 1)))


def run(game):
    s = game.s
    options = ('Order', 'Drop', 'Speed', 'Icon', 'Level', 'Exit', *camp.MEMBER_KEYS)
    actions = (order, drop, speed, lambda g: creation.customize_icon(g, g.s.selc().b), level)
    while s.chars() and not s.stop:
        pick = horizontal(game, 'ALTER', options, prompt='', start=0, member=camp.name(s.selc()),
                          escape_choice=5, preserve_message=True)
        if options[pick] == 'Exit': return
        if options[pick] in camp.MEMBER_KEYS: select_adjacent(game, options[pick])
        else: actions[pick](game)


def test():
    from ._services_test import alter_rules
    alter_rules()
