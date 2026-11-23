from enum import Enum
from . import camp, shop, effects
from .creation import dice
from .town import field, put


class Kind(str, Enum):
    MENU = 'TEMPLE'
    LIST = 'TEMPLE_LIST'
    CONFIRM = 'TEMPLE_CONFIRM'


def confirm_anyway(game, char, message):
    return game.ask(Kind.CONFIRM.value, ('Yes', 'No'), start=1,
                    prompt=game.assets.text('castAnywayPrompt'),
                    offer=shop.member_name(char) + ' ' + game.assets.text(message)) == 0


def spell_service(game, char, index):
    game.vm.service('magic', 'temple_spell', char, game.assets.table('templeMenuSpells')[index])


def cure(game, char, index):
    if index == 0:
        if effects.has(char, 33) or confirm_anyway(game, char, 'notBlindMessage'):
            effects.remove_effect(game, char, 33)
    elif index == 1:
        return
    elif index in (2, 3, 4):
        count, bonus = ((1, 0), (2, 1), (3, 3))[index - 2]
        camp.restore_hit_points(game, char, (dice(game.s, count, 8) + bonus) & 255)
    elif index == 5:
        roll = dice(game.s, 1, 4)
        camp.restore_hit_points(game, char, max(0, field(char, 'hp_max') - field(char, 'hp') - roll))
        effects.remove_effect(game, char, 33)
        for ability in (1, 2): effects.recalc_ability(game, char, ability)
    elif index == 6:
        poisoned = effects.has(char, 55)
        if not poisoned:
            confirm_anyway(game, char, 'notPoisonedMessage')
            return
        if not field(char, 'hp'): put(char, 'hp', 1)
        camp.locked_remove(game, char, 55, 22, 15)
        put(char, 'active', 1); put(char, 'status', 0)
    elif index == 7:
        dead, allowed = field(char, 'status') in (1, 6), field(char, 'race') >= 2
        if (not dead or not allowed) and not confirm_anyway(game, char, 'notDeadMessage' if allowed else 'cannotRaiseMessage'): return
        if dead and allowed: spell_service(game, char, index)
    elif index == 8:
        cursed = effects.has(char, 36) or any(item[shop.I['cursed']] for item in char.items)
        if cursed or confirm_anyway(game, char, 'notCursedMessage'): spell_service(game, char, index)
    elif index == 9:
        stoned = field(char, 'status') == 7
        if stoned or confirm_anyway(game, char, 'notStonedMessage'):
            if stoned:
                put(char, 'status', 0); put(char, 'active', 1); put(char, 'hp', 1)
    elif index == 10:
        drained = any(field(char, 'levels', i, signed=True) < field(char, 'former_levels', i, signed=True) for i in range(8))
        if drained or confirm_anyway(game, char, 'noLostLevelsMessage'): spell_service(game, char, index)


def heal_menu(game, char):
    names = game.assets.names('spellNames')
    ids = game.assets.table('templeMenuSpells')
    selected = 0
    while True:
        title = shop.member_name(char) + game.assets.text('howCanWeHelp')
        hp, maximum = field(char, 'hp'), field(char, 'hp_max')
        pick = shop.pick(game, Kind.LIST, title, [names[i - 1] for i in ids], start=selected,
                         title=title, window='2 3 38 15', menu='Heal', member=shop.member_name(char),
                         hp=hp, hp_max=maximum, hp_row=19, hp_column=18, hp_colour=13 if hp != maximum else 15)
        if pick is None:
            game.vm.clear_text()
            return
        selected = pick
        cure(game, char, pick)


def main_menu(game, options):
    labels = ('Heal', 'View', 'Take', 'Pool', 'Share', 'Appraise', 'Exit')
    choices = options + ('Exit', 'char-up', 'char-down')
    while True:
        pick = shop.horizontal(game, Kind.MENU.value, choices, prompt='', member=shop.member_name(game.s.selc()),
                               escape_choice=len(options), menu_labels=labels,
                               enabled=tuple(labels.index(label) for label in choices[:-2]))
        if choices[pick] in ('char-up', 'char-down'): shop.select_adjacent(game, choices[pick])
        else: return None if pick == len(options) else pick


def run(game):
    s = game.s
    shop.enter_service(game)
    while True:
        options = ('Heal', 'View', 'Take', 'Pool', 'Share', 'Appraise') if shop.has_money(s) else ('Heal', 'View', 'Pool', 'Appraise')
        pick = main_menu(game, options)
        if pick is None:
            if not shop.has_money(s) or game.ask(Kind.CONFIRM.value, ('Yes', 'No'), start=1, prompt='',
                        offer=game.assets.text('leftMoney2'), window='1 17 38 22', colour=10,
                        messages=(game.assets.text('leftMoney1'), game.assets.text('leftMoney2')), clear_first=(True, True)) == 1:
                game.vm.party_drawn()
                return
            game.vm.clear_text()
        else:
            action = options[pick]
            if action == 'Pool': shop.pool_money(s)
            elif action == 'Share': shop.share_money(s)
            elif {'Heal': heal_menu, 'View': shop.view_items, 'Take': shop.take_menu, 'Appraise': shop.appraise}[action](game, s.selc()) or action != 'Appraise':
                game.vm.clear_text()
        game.vm.party_drawn()


def test():
    from ._services_test import scenario
    scenario()
