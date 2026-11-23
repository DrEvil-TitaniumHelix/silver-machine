from . import camp, rules
from .creation import yes_no
from .magic_lists import I, readable, spell_menu, remove_scroll_spell


def scroll_cells(char):
    for item in list(char.items):
        if readable(item):
            for at in range(I['powers'], I['powers'] + 3):
                yield item, at


def reset_scribe(char):
    for item, at in scroll_cells(char): item[at] &= 127


def mark_scribe(game, char, ident):
    from .magic import spell
    if char.b[camp.F['known_spells'] + ident - 1]: return 'alreadyKnowsMessage'
    if any(item[at] > 127 and item[at] & 127 == ident for item, at in scroll_cells(char)):
        return 'alreadyScribingMessage'
    row = spell(game, ident)
    if not camp.slot_count(char, row.cast_class, row.level): return 'cannotScribeMessage'
    for item in char.items:
        for at in range(I['powers'], I['powers'] + 3):
            if item[at] == ident:
                item[at] |= 128
                return ''
    return ''


def keep_scribe(game, char):
    if not spell_menu(game, char, 6, 0)[2]: return None
    kept = yes_no(game, camp.Kind.CONFIRM, game.assets.text('scribeConfirmPrompt'), start=0)
    if not kept: reset_scribe(char)
    return kept


def scribe(game, char):
    if char.b[camp.F['status']] == camp.ANIMATED or not char.b[camp.F['active']]:
        camp.ack(game, game.assets.text('incapacitatedPrefix') + game.assets.text('scribingSuffix'), char)
        return
    kept = keep_scribe(game, char)
    redraw = kept is not None
    index, message = -1, ''
    while not kept:
        ident, index, present = spell_menu(game, char, 3, 3, index, message=message)
        if present: redraw = True
        if not ident:
            if not present: camp.ack(game, game.assets.text('noCopyableMessage'), char)
            break
        key = mark_scribe(game, char, ident)
        message = game.assets.text(key) if key else ''
    if index != -1: keep_scribe(game, char)
    if redraw and game.s.mode == camp.CAMPING: camp.redraw_camp(game)


def prep_minutes(game, char):
    from .magic import spell
    counts, maxima = [0, 0], [0, 0]
    if rules.spellbook(char) is not None and char.b[camp.F['active']]:
        for value in camp.memory(char):
            if value > 127:
                level = spell(game, value).level & 255
                level = level or 1
                counts[0] = counts[0] + level & 255
                maxima[0] = max(maxima[0], level)
    for item, at in scroll_cells(char):
        if item[at] > 127:
            level = spell(game, item[at]).level & 255
            counts[1] = counts[1] + level & 255
            maxima[1] = max(maxima[1], level)
    hours = 6 if max(maxima) > 2 else 4 if any(counts) else 0
    char.b[camp.F['preparation']] = hours
    return hours * 60 + sum(counts) * 15


def _announce(game, char, ident, key):
    from .magic import spell
    rest = game.s.g.get('camp.rest')
    info = camp.rest_info(game, rest) if rest is not None else dict(rest=True)
    game.ask(camp.Kind.ACK.value, ('Continue',), prompt=camp.name(char) + ' ' + game.assets.text(key) + ' ' + spell(game, ident).name,
             spell=ident, timed=1, member=next((i for i, who in enumerate(game.s.party) if who is char), None), **info)


def finish_scribe(game, char, done, suppressed=False):
    from .magic import spell
    if suppressed or rules.spellbook(char) is None: return 0, done
    for item, at in scroll_cells(char):
        if item[at] <= 128: continue
        ident = item[at] & 127
        if done:
            level = spell(game, ident).level & 255
            if level: return level, done
        else:
            char.b[camp.F['known_spells'] + ident - 1] = 1
            remove_scroll_spell(char, item, ident, game)
            _announce(game, char, ident, 'scribedText')
            done = True
    return 0, done


def finish_memorize(game, char, done, suppressed=False):
    from .magic import spell
    if suppressed or rules.spellbook(char) is None or not char.b[camp.F['active']]: return 0, done
    for at in range(camp.F['memorized'], camp.F['memorized'] + camp.MEMORY_SLOTS):
        if char.b[at] <= 127: continue
        ident = char.b[at] & 127
        if done:
            level = spell(game, ident).level & 255
            if level: return level, done
        else:
            char.b[at] = ident
            _announce(game, char, ident, 'memorizedText')
            done = True
    return 0, done


def test():
    from ._magic_test import check_study
    check_study()
