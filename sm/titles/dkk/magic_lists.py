from collections import namedtuple

from sm.titles.cok.magic import list_start
from . import camp, effects, rules
from .records import Item

Entry = namedtuple('Entry', 'ident copies marked item')
I = {key: offset for key, (offset, _) in Item.FIELDS.items()}
TITLES = ('in Memory', 'in Grimoire', 'on Scroll', 'on Scrolls', 'to Choose', 'to Memorize', 'to Scribe')


def readable(item):
    return item is not None and item[I['type']] in (39, 40)


def spell_known(game, char, ident):
    from .magic import spell
    ident &= 127
    return rules.spellbook(char) is not None and spell(game, ident).cast_class == 2 and any(
        held & 127 == ident for held in camp.memory(char)[1:])


def _group(game, values):
    from .magic import spell
    rows = []
    for value in values:
        ident, level = value & 127, spell(game, value).level
        at = next((i for i, row in enumerate(rows) if row.ident == ident or spell(game, row.ident).level > level), len(rows))
        copies = 1
        if at < len(rows) and rows[at].ident == ident:
            copies = rows.pop(at).copies + 1 & 255
        rows.insert(at, Entry(ident, copies, value > 127, None))
    return rows


def identify_scroll(game, char, item):
    if effects.has_effect(char, 16) is not None or (
            rules._s8(char.b[rules.F['levels']]) > 0 and rules.tables(game.assets.root).base_item(item[I['type']])[rules.SLOT] == 12):
        item[I['unidentified']] &= 248


def scroll_spells(game, char, pending=False, item=None):
    rows = []
    single = item is not None
    flag = {1: 32, 2: 16}.get(char.b[rules.F['robe_order']], 0)
    for raw in (item,) if single else char.items:
        if not single and (not readable(raw) or not raw[I['unidentified']] & flag): continue
        identify_scroll(game, char, raw)
        if raw[I['unidentified']] & 7: continue
        for value in raw[I['powers']:I['powers'] + 3]:
            if value > (128 if pending else 0):
                rows.append(Entry(value & 127, 1, value > 127, raw))
    return rows


def learnable(game, char):
    book = rules.spellbook(char)
    if book is None: return []
    slots, known = book.get('spell_slots'), book.get('known_spells')
    group = 1 if char.b[rules.F['robe_order']] == 1 else 2
    table, offered = game.assets.table('spellsByLevel'), []
    for level in range(8):
        if not slots[24 + level]: continue
        start = (group * 8 + level) * 10
        for ident in table[start:start + 10]:
            if not ident: break
            if not known[ident - 1]: offered.append(ident)
    return [row.ident for row in _group(game, offered)]


def generate_list(game, char, mode, item=None, combat=False):
    from .magic import can_cast
    if mode not in range(7): return []
    book = rules.spellbook(char)
    if book is None and mode not in (2, 3): return []
    if mode in (2, 3, 6):
        if mode == 2 and item is None: return []
        return scroll_spells(game, char, mode == 6, item if mode == 2 else None)
    if mode == 4: return _group(game, learnable(game, char))
    if mode == 1:
        values = [i + 1 for i, known in enumerate(book.get('known_spells'))
                  if known and can_cast(game, char, i + 1, combat) and not spell_known(game, char, i + 1)]
    else:
        values = [v for v in camp.memory(char) if (v >= 128 if mode == 5 else 0 < v < 128)
                  and can_cast(game, char, v, combat)]
    return _group(game, values)


def line(game, entry):
    from .magic import spell
    return (' *' if entry.marked else '  ') + spell(game, entry.ident).name + (' (%d)' % entry.copies if entry.copies > 1 else '')


def spell_menu(game, char, mode, selection, index=-1, item=None, combat=False, message='', ask=None):
    from .magic import spell
    ask = ask or (lambda options, **info: game.ask(camp.Kind.SPELL.value, options, **info))
    entries = generate_list(game, char, mode, item, combat)
    if not entries: return 0, index, False
    levels = tuple(spell(game, row.ident).level for row in entries)
    start, drawn = list_start(levels, index, mode in (2, 3, 6), 11 if selection == 2 else 18)
    labels = tuple(line(game, row) for row in entries)
    menu = {1: 'castMenu', 2: 'memorizeMenu', 3: 'scribeMenu', 4: 'learnMenu', 5: 'keepMenu'}.get(selection)
    query = game.assets.text('spellsOkQuery' if selection == 5 else 'chooseSpellQuery') if menu else ''
    info = dict(title=TITLES[mode], levels=levels, spells=tuple(row.ident for row in entries),
                lines=labels, menu=game.assets.text(menu) if menu else '',
                window='1 5 38 %d' % (15 if selection == 2 else 22), start=start, selection=selection, entry=max(index, 0))
    if message: info['message'] = message
    if selection == 5:
        info['start'] = 0
        pick = ask(('Keep', 'Exit'), prompt=query, **info)
        return entries[start].ident if pick == 0 else 0, drawn.index(start), True
    if menu is None:
        info['start'] = 0
        ask(('Exit',), prompt='', **info)
        return 0, drawn.index(start), True
    options = labels if selection == 4 else labels + ('Exit',)
    pick = ask(options, prompt=query, **info)
    if pick is None or not 0 <= pick < len(entries): return 0, drawn.index(start), True
    if selection == 3: game.scroll = entries[pick].item
    return entries[pick].ident, drawn.index(pick), True


def learn(game, char):
    index = -1
    while True:
        ident, index, present = spell_menu(game, char, 4, 4, index)
        if ident:
            char.b[camp.F['known_spells'] + ident - 1] = 1
            return ident
        if not present: return 0


def remove_scroll_spell(char, item, ident, game=None):
    matches = [at for at in range(I['powers'], I['powers'] + 3) if item[at] & 127 == ident]
    if not matches: return False
    item[matches[-1]] = 0
    item[I['name_ids']] = item[I['name_ids']] - 1 & 255
    if item[I['name_ids']] < 100:
        from .inventory import remove_item
        remove_item(char, item, game)
    return True


def test():
    from ._magic_test import check_lists
    check_lists()
