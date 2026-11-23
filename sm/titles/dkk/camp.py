from enum import Enum
from functools import lru_cache
from . import creation, rules, effects
from .creation import yes_no, dice, EXIT
from .records import Spells, Item

F = dict(rules.F, **{k: 216 + v[0] for k, v in Spells.FIELDS.items()})
CLERIC, PALADIN, RANGER, MAGE, KNIGHT = 0, 3, 4, 5, 7
ANIMATED, UNCONSCIOUS, DYING, CAMPING = 1, 4, 5, 2
PENDING, SPELL_MASK, MEMORY_SLOTS = 128, 127, 74
CLOCK_CELL, REST_PERIOD_CELL, REST_CHANCE_CELL = 0xC6, 0x2D2, 0x2D3
FIX_INITIAL_SCORE = 14
REST_MENU = ('Rest', 'Days', 'Hours', 'Mins', 'Add', 'Subtract', 'Exit')
DAYS, HOURS, TENS, MINUTES = 4, 3, 2, 1
MEMBER_KEYS = ('char-up', 'char-down')

class Kind(str, Enum):
    MENU = 'CAMP_MENU'
    SPELL = 'SPELL'
    REST = 'CAMP_REST'
    RESTING = 'CAMP_RESTING'
    CONFIRM = 'CAMP_CONFIRM'
    ACK = 'ACK'

class Tables:
    def __init__(self, assets):
        self.names = assets.names('spellNames')
        self.spells, self.scale = assets.table('spellTable'), assets.table('clockUnitScale')
    def spell_class(self, spell): return self.spells[(spell - 1) * 16]
    def level(self, spell): return self.spells[(spell - 1) * 16 + 1]

@lru_cache(maxsize=4)
def tables(assets): return Tables(assets)

def memory(char): return char.b[F['memorized']:F['memorized'] + MEMORY_SLOTS]

def slot_count(char, cls, level):
    return char.b[F['spell_slots'] + cls * 8 + level - 1] if rules.spellbook(char) is not None else 0

def can_cast(char, spell, t):
    if rules.spellbook(char) is None: return False
    kind = t.spell_class(spell)
    if kind in (0, 2): return ability(char, 2) > 8 and (level_of(char, CLERIC) > 0 or level_of(char, KNIGHT) > 5 or level_of(char, PALADIN) > 8)
    if kind == 1: return ability(char, 2) > 8 and level_of(char, RANGER) > 7
    return kind == 3 and ability(char, 1) > 8 and (level_of(char, MAGE) > 0 or level_of(char, RANGER) > 8)

def reset_memorize(char):
    for i, value in enumerate(memory(char)):
        if value > 127: char.b[F['memorized'] + i] = 0
    char.b[F['preparation']] = 0

def memorizable(char, t):
    if rules.spellbook(char) is None: return []
    held = {n & 127 for n in memory(char)[1:]}
    return sorted((s for s in range(1, 115) if char.b[F['known_spells'] + s - 1] and can_cast(char, s, t) and not (t.spell_class(s) == 2 and s in held)), key=t.level)

def prep_minutes(char, t):
    levels = [max(1, t.level(n & SPELL_MASK)) for n in memory(char) if n > SPELL_MASK] if char.b[F['active']] else []
    offset = Item.FIELDS['powers'][0]
    scrolls = [t.level(n & SPELL_MASK) for raw in char.items if raw[Item.FIELDS['type'][0]] in (39, 40)
               for n in raw[offset:offset + 3] if n > SPELL_MASK]
    total, scroll_total = sum(levels) & 255, sum(scrolls) & 255
    hours = 6 if max((*levels, *scrolls), default=0) > 2 else 4 if total or scroll_total else 0
    char.b[F['preparation']] = hours
    return hours * 60 + (total + scroll_total) * 15

def name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def ack(game, text, char=None):
    info = {}
    if char is not None:
        from .inventory import IN_COMBAT
        combat = game.s.mode == IN_COMBAT
        row = 10 if combat else 19 if game.s.g.get('no_border') else 18
        colour = 12 if not char.b[F['active']] else 14 if combat and char.b[F['side']] == 1 else 13 if char.b[F['level_up_ready']] else 11
        info = dict(creature_name=name(char), creature_text=text, creature_colour=colour,
                    creature_column=23 if combat else 1, creature_row=row)
        text = name(char) + ' ' + text
    game.ask(Kind.ACK.value, ('Continue',), prompt=text, timed=1, **info)


def ability(char, index):
    return char.b[F['abilities'] + index * 2 + 1]


def level_of(char, cls):
    return rules._s8(char.b[F['levels'] + cls])


def slots_remaining(char, level, cls, t):
    if cls == 2:
        allowance = {4: 3, 6: 0}.get(char.b[F['deity']], 1) if level_of(char, CLERIC) > 0 else 0
        return (allowance - sum(100 < n & SPELL_MASK < 108 for n in memory(char))) & 255, 0
    used = sum(1 for n in memory(char) if n and t.level(n & SPELL_MASK) == level and t.spell_class(n & SPELL_MASK) == cls)
    count = slot_count(char, cls, level)
    return count - min(count, used), used


def slot_display(game, char, t):
    if rules.spellbook(char) is None: return 0, False, ''
    any_slots, lines = level_of(char, CLERIC) > 0 and char.b[F['deity']] != 6, []
    for cls, label in enumerate(('clericSpellsLabel', 'druidSpellsLabel', 'specialSpellsLabel', 'magicUserSpellsLabel')):
        if cls == 2:
            if level_of(char, CLERIC) > 0 and char.b[F['deity']] != 6:
                lines.append(game.assets.text(label).ljust(13) + str(slots_remaining(char, 0, cls, t)[0]))
            continue
        row = [slots_remaining(char, level, cls, t)[0] if slot_count(char, cls, level) else None for level in range(1, 9)]
        if any(v is not None for v in row):
            any_slots = True
            lines.append((game.assets.text(label).ljust(13) + ''.join(('' if v is None else str(v)).ljust(3) for v in row)).rstrip())
    bonus = 0
    if level_of(char, MAGE) > 0 and char.b[F['robe_order']] > 0:
        value = game.s.r0[0x1F8 + char.b[F['robe_order']]]
        bonus = value if value in (1, 2) else 0
        for level in range(1, 9):
            if bonus:
                over = slots_remaining(char, level, 3, t)[1] - slot_count(char, 3, level)
                if over > 0: bonus = 0 if over > bonus else bonus - over
        any_slots = any_slots or bonus > 0
    if bonus: lines.append(game.assets.text('bonusSpellsLabel').ljust(13) + str(bonus))
    return bonus, any_slots, '\n'.join(lines)


def sort_memory(char):
    if rules.spellbook(char) is None: return
    b, base = char.b, F['memorized']
    for left in range(MEMORY_SLOTS - 1):
        for right in range(left, MEMORY_SLOTS):
            if b[base + left] & SPELL_MASK > b[base + right] & SPELL_MASK: b[base + left], b[base + right] = b[base + right], b[base + left]


def pending_names(char, t):
    return ', '.join(t.names[(n & SPELL_MASK) - 1] for n in memory(char) if n > SPELL_MASK and can_cast(char, n & SPELL_MASK, t))


def redraw_camp(game):
    game.vm.archive('PIC', 59)
    game.vm.party_drawn()
    game.vm.clear_text()


def memorize(game, char):
    from . import magic
    t = tables(game.assets)
    if rules.spellbook(char) is None:
        ack(game, game.assets.text('cannotMemorizeMessage'), char)
        return
    if char.b[F['status']] == ANIMATED or not char.b[F['active']]:
        ack(game, game.assets.text('incapacitatedPrefix') + game.assets.text('memorizingSuffix'), char)
        return
    kept, _, redraw = magic.spell_menu(game, char, 5, 5)
    if redraw and not kept: reset_memorize(char)
    def pick_spell(options, **info):
        return game.ask(Kind.SPELL.value, options, slots=left, bonus=bonus, **info)

    index = -1
    while not kept:
        bonus, any_slots, left = slot_display(game, char, t)
        if not any_slots:
            ack(game, game.assets.text('cannotMemorizeMessage'), char)
            break
        spell, index, _ = magic.spell_menu(game, char, 1, 2, index, ask=pick_spell)
        redraw = True
        if not spell: break
        if slots_remaining(char, t.level(spell), t.spell_class(spell), t)[0] > 0 or t.spell_class(spell) == 3 and bonus > 0:
            game.s.g['camp.special_selection'] = int(t.spell_class(spell) == 2)
            at = next((i for i, n in enumerate(memory(char)) if n == 0), None)
            if at is not None:
                char.b[F['memorized'] + at] = spell | PENDING
                sort_memory(char)
    if index != -1:
        spell, _, present = magic.spell_menu(game, char, 5, 5)
        if present and not spell: reset_memorize(char)
    if redraw: redraw_camp(game)


def advance_junctions(s):
    for cell, limit in ((0x1FC, 8), (0x1FD, 1), (0x1FE, 6)):
        if s.r0[cell] >= limit:
            s.r0[cell - 3] = 0 if s.r0[cell - 3] >= 3 else s.r0[cell - 3] + 1
            s.r0[cell] = 0
        else: s.r0[cell] += 1


def validate_clock(game, clock):
    s, scale = game.s, tables(game.assets).scale
    for i in range(7):
        if clock[i] >= scale[i]:
            if i == 6:
                for char in s.chars():
                    age = F['age']
                    char.b[age:age + 2] = ((int.from_bytes(char.b[age:age + 2], 'little') + 1) & 0xFFFF).to_bytes(2, 'little')
                from .effects_handlers import owner
                owner(game).age_pass = False
            else:
                clock[i + 1] = (clock[i + 1] + 1) & 65535
                clock[i] -= scale[i]
                if i == 3: advance_junctions(s)


def validate_rest(game, rest):
    validate_clock(game, rest)
    if rest[5]:
        rest[4] = min((rest[4] + tables(game.assets).scale[4] * rest[5]) & 65535, 99)
        rest[5] = 0


def decrement_rest(game, rest, count, unit):
    scale = tables(game.assets).scale
    if not any(rest[1:5]): return
    while count > rest[unit]:
        source = unit + 1
        while rest[source] == 0 and source < 5: source += 1
        if source == 5:
            rest[:] = [0] * 7
            count = 0
        else:
            for k in range(source, unit, -1):
                rest[k] = (rest[k] - 1) & 65535
                rest[k - 1] = (rest[k - 1] + scale[k - 1]) & 65535
    rest[unit] -= count
    validate_rest(game, rest)


def restore_hit_points(game, char, amount):
    if char.b[F['status']] not in (0, ANIMATED, UNCONSCIOUS, DYING): return False
    char.b[F['hp']] = min((char.b[F['hp']] + amount) & 255, char.b[F['hp_max']])
    if not char.b[F['active']]:
        if char.b[F['status']] == DYING: char.b[F['status']] = UNCONSCIOUS
        if char.b[F['status']] == UNCONSCIOUS:
            char.b[F['status']], char.b[F['active']] = 0, 1
    return True


def rest_info(game, rest, field=0):
    values = (rest[DAYS], rest[HOURS], 10 * rest[TENS] + rest[MINUTES])
    return dict(days=values[0], hours=values[1], minutes=values[2] & 255, field=field,
                rest=True, rest_label=game.assets.text('restLabel'), rest_row=17,
                rest_columns=(12, 15, 18), rest_digits=tuple(('%02d' % (v & 255))[:2] for v in values),
                rest_colours=tuple(15 if field == i else 10 for i in (DAYS, HOURS, TENS)))


def heal_tick(game, rest=None, interactive=False):
    g = game.s.g
    g['camp.heal_ticks'] = (g.get('camp.heal_ticks', 0) + 1) & 65535
    if g['camp.heal_ticks'] >= 288:
        healed = [restore_hit_points(game, char, 1) for char in game.s.chars()]
        redraw = any(healed)
        if redraw: game.vm.party_drawn()
        info = rest_info(game, rest) if interactive and rest is not None else {}
        game.ask(Kind.ACK.value, ('Continue',), prompt=game.assets.text('partyHealedText'),
                 row=19, column=1, colour=10, redraw_party=redraw, clear_after=True, timed=1, **info)
        game.vm.clear_text()
        g['camp.heal_ticks'] = 0
        return True
    return False


def next_pending(game, char, done):
    from . import magic
    suppressed = game.s.g.get('camp.rest_active', False)
    level, done = magic.finish_scribe(game, char, done, suppressed)
    return (level, done) if level else magic.finish_memorize(game, char, done, suppressed)


def rest_menu(game, rest):
    selected = TENS
    while True:
        pick = REST_MENU[game.ask(Kind.REST.value, REST_MENU, prompt='Rest Time',
                                  extended_keys={'Up': 'Add', 'Down': 'Subtract', 'Left': None, 'Right': None},
                                  extended_exit=True, **rest_info(game, rest, selected))]
        if pick == 'Rest': return selected
        if pick == 'Exit': return None
        if pick in ('Days', 'Hours', 'Mins'): selected = {'Days': DAYS, 'Hours': HOURS, 'Mins': TENS}[pick]
        elif pick == 'Add':
            if selected == TENS: rest[MINUTES] = (rest[MINUTES] + 5) & 65535
            else: rest[selected] = (rest[selected] + 1) & 65535
            validate_rest(game, rest)
        else:
            if selected == TENS: decrement_rest(game, rest, 5, MINUTES)
            else: decrement_rest(game, rest, 1, selected)
            validate_rest(game, rest)


def set_rest(rest, minutes):
    rest[HOURS], rest[TENS], rest[MINUTES] = minutes // 60, (minutes % 60) // 10, minutes % 10


def rest_for_prep(game, rest):
    set_rest(rest, max((prep_minutes(char, tables(game.assets)) for char in game.s.chars()), default=0))
    interrupted = camp_rest(game, rest, True)
    rest[:] = [0] * 7
    return interrupted


def member_menu(game, prompt, entries, start=0, **info):
    from .shop import horizontal, select_adjacent
    s, options = game.s, entries + (EXIT,) + MEMBER_KEYS
    while True:
        pick = horizontal(game, Kind.MENU.value, options, prompt=prompt, member=name(s.selc()), start=start,
                          escape_choice=len(entries), **info)
        start = game.menu_highlight
        if options[pick] not in MEMBER_KEYS: return None if pick == len(entries) else pick
        select_adjacent(game, options[pick])


def roster_values(char):
    return char.b[F['hp']], char.b[F['ac']]


def repaint_walking_row(game, char):
    rows = getattr(getattr(game, 'vm', None), 'rows_shown', None)
    if not rows or game.s.mode not in (3, 4): return
    if game.s.mode == 3 and game.s.r0[0x1F7] == 1: return
    if game.vm.display.get('kind') == 'BIGPIC' or game.s.g.get('dkk.runtime', {}).get('big_picture_shown'): return
    for index, member in enumerate(game.s.chars()):
        if member is char:
            if index in rows: rows[index] = roster_values(char)
            break


def age_walking_effects(game, index, char, step):
    if getattr(game.vm, 'rows_shown', None) is None: game.vm.rows_shown = {}
    rows = game.vm.rows_shown
    rows.setdefault(index, roster_values(char))
    try:
        return effects.age_effects(game, char, step)
    finally:
        if rows.get(index) == roster_values(char): rows.pop(index)


def advance(game, amount, unit=1):
    amount &= 255
    clock = list(game.s.r0[CLOCK_CELL:CLOCK_CELL + 7])
    for _ in range(amount):
        clock[unit] = (clock[unit] + 1) & 65535
        validate_clock(game, clock)
    game.s.r0[CLOCK_CELL:CLOCK_CELL + 7] = [v & 255 for v in clock]
    flags = game.s.g.setdefault('camp.effects_running', [1] * 72)
    if game.s.mode != CAMPING: flags[:] = [1] * 72
    elif not any(flags[:max(1, game.s.r1[creation.PARTY_SIZE])]): return
    total = amount
    for i in range(unit - 1, 0, -1): total = (total * tables(game.assets).scale[i]) & 65535
    while total:
        step = min(total, 10)
        for index, char in enumerate(game.s.chars()):
            if not flags[index]: continue
            flags[index] = 0
            if game.s.mode in (3, 4) and char.effects:
                running = age_walking_effects(game, index, char, step)
            else:
                running = effects.age_effects(game, char, step)
            flags[index] = int(running)
        total -= step


def camp_rest(game, rest, interactive, fixing=False):
    s = game.s
    timers = s.g['camp.prep_timers'] = [0] * len(s.chars())
    s.g['camp.effects_running'] = [1] * 72
    s.g['camp.hour_tick'] = 0
    s.g['no_border'] = 1
    active = s.g.get('camp.rest_active', False)
    s.g['camp.rest_active'] = active or fixing
    try:
        displayed = None
        if interactive:
            game.vm.clear_text()
            field = rest_menu(game, rest)
            if field is None: return False
            displayed = rest_info(game, rest, field)
        steps = 0
        while any(rest[1:5]):
            if interactive and getattr(game, 'rest_poll', True):
                if game.ask(Kind.RESTING.value, ('Continue', 'Stop'), **displayed):
                    displayed = rest_info(game, rest)
                    if game.ask(Kind.CONFIRM.value, ('Yes', 'No'), prompt=game.assets.text('stopRestPrompt'),
                                start=0, clear_bottom_after=True, **displayed) == 0: break
            decrement_rest(game, rest, 5, 1)
            steps += 1
            if interactive and steps % 5 == 0:
                displayed = rest_info(game, rest)
            advance(game, 5)
            announced = heal_tick(game, rest, interactive)
            for i, char in enumerate(s.chars()):
                if timers[i]: timers[i] -= 1
                if not timers[i] and not char.b[F['preparation']]:
                    level, completed = next_pending(game, char, False)
                    timers[i] = level * 3 & 255
                    announced |= completed
            if interactive and announced:
                displayed = rest_info(game, rest)
            s.g['camp.hour_tick'] += 1
            if s.g['camp.hour_tick'] >= 12:
                s.g['camp.hour_tick'] = 0
                for i, char in enumerate(s.chars()):
                    if char.b[F['preparation']]:
                        char.b[F['preparation']] -= 1
                        if not char.b[F['preparation']]: timers[i] = (next_pending(game, char, True)[0] * 3) & 255
            if s.r1[REST_PERIOD_CELL]:
                s.g['camp.rest_ticks'] = (s.g.get('camp.rest_ticks', 0) + 1) & 65535
                if s.g['camp.rest_ticks'] >= s.r1[REST_PERIOD_CELL]:
                    s.g['camp.rest_ticks'] = 0
                    if dice(s, 1, 100) <= s.r1[REST_CHANCE_CELL]:
                        game.vm.clear_text()
                        game.ask(Kind.ACK.value, ('Continue',), prompt=game.assets.text('interruptedText'),
                                 row=19, column=1, colour=15, clear_first=True, timed=1, **rest_info(game, rest))
                        return True
        return False
    finally:
        game.vm.clear_text()
        s.g['camp.rest_active'] = active
        s.g['no_border'] = 0


def reset_scribing(game):
    from .magic_study import reset_scribe
    for char in game.s.chars():
        reset_scribe(char)


def missing(s):
    return sum(char.b[F['hp_max']] - char.b[F['hp']] for char in s.chars()) & 65535


def locked_remove(game, char, *idents):
    from .effects_handlers import owner
    holder = owner(game)
    previous = getattr(holder, 'effect_busy', False)
    holder.effect_busy = True
    try:
        for ident in idents: effects.remove_effect(game, char, ident)
    finally: holder.effect_busy = previous


def remove_curse(game, char):
    from .magic import remove_curse as cure
    return cure(game, char)


def raise_dead(char):
    con = F['abilities'] + 2 * 4 + 1
    char.b[F['hp']], char.b[F['status']], char.b[F['active']] = 1, 0, 1
    if char.b[con]: char.b[con] -= 1
    bonus = max(char.b[F['hp_max']] - char.b[F['hp_rolled']], 0)
    if char.b[con] < 14: return
    divisor, lv = 0, char.b[F['levels']:F['levels'] + 7]
    for cls, level in enumerate(lv):
        if 0 < level < 128:
            step = char.b[con] - 14 if cls in (2, PALADIN, RANGER) else 2 if char.b[con] > 15 else 1
            divisor = divisor + step * level & 255
    if divisor: bonus //= divisor
    if char.b[con] < 17 or any(0 < char.b[F['levels'] + cls] < 128 for cls in (2, PALADIN, KNIGHT)):
        char.b[F['hp_max']] = char.b[F['hp_max']] - bonus & 255


def fix(game, rest):
    s = game.s
    if s.r0[0xE5] or not missing(s): return False
    casters = lambda: [c for c in s.chars() if c.b[F['status']] == 0 and rules.spellbook(c) is not None]
    n = dict(heal=0, poison=0, raised=0, curse=0, flesh=0, sight=0)
    pool = 0
    for char in casters():
        for spell in memory(char):
            if spell in (3, 58): pool += dice(s, 2, 8) + 1
            elif spell == 71: pool += dice(s, 3, 8) + 3
            elif spell == 53: pool += dice(s, 4, 8) + 5; n['heal'] += 1
            else:
                key = {67: 'poison', 75: 'raised', 43: 'curse', 89: 'curse', 66: 'flesh', 37: 'sight'}.get(spell)
                if key: n[key] += 1
    pool &= 65535
    light = serious = critical = heal_slots = cleric = druid = ser = cri = hea = most = 0
    score = FIX_INITIAL_SCORE
    able = casters()
    for char in s.chars():
        minutes = 0
        if any(char is c for c in able) and ability(char, 2) > 3:
            light += slot_count(char, 0, 1) + slot_count(char, 1, 2)
            cleric, druid = 15 * slot_count(char, 0, 1), 30 * slot_count(char, 1, 2)
            serious += slot_count(char, 0, 4); ser = 60 * slot_count(char, 0, 4)
            critical += slot_count(char, 0, 5); cri = 75 * slot_count(char, 0, 5)
            heal_slots += slot_count(char, 0, 6); hea = 90 * slot_count(char, 0, 6)
        if cleric: minutes = 240; score += 27
        if druid: minutes = 240; score += 27
        if ser + cri: minutes = 360; score += 78 if cri else 34
        if hea: minutes = 480; score += 90
        most = max(most, minutes + cleric + druid + ser + cri + hea)
    score &= 65535
    wounds = missing(s)
    if wounds < score:
        divisor = score // wounds & 255
        if divisor: most //= divisor
    saved = rest[:]
    set_rest(rest, most)
    if camp_rest(game, rest, False, fixing=True): return True
    for count, roll in ((light, (1, 8, 0)), (serious, (2, 8, 1)), (critical, (3, 8, 3)), (heal_slots, (4, 8, 3))):
        for _ in range(count & 255): pool += dice(s, *roll[:2]) + roll[2]
    pool &= 65535

    def cure():
        for char in s.chars():
            healed = False
            if n['heal'] and effects.has(char, 61):
                effects.remove_effect(game, char, 61)
                if effects.has(char, 33): effects.remove_effect(game, char, 33)
                healed = True; n['heal'] -= 1
                ack(game, 'is healed', char)
            if n['flesh'] and char.b[F['status']] == 7:
                char.b[F['status']], char.b[F['active']], char.b[F['hp']] = 0, 1, 1
                n['flesh'] -= 1
                ack(game, 'is changed back to flesh', char)
            if n['poison'] and effects.has(char, 55):
                if not char.b[F['hp']]: char.b[F['hp']] = 1
                locked_remove(game, char, 55, 22, 15)
                char.b[F['active']], char.b[F['status']] = 1, 0
                n['poison'] -= 1
                ack(game, 'is detoxified', char)
            if n['raised'] and char.b[F['status']] == 6 and char.b[F['race']] not in (0, 1, 2):
                locked_remove(game, char, 55)
                raise_dead(char)
                n['raised'] -= 1
                ack(game, 'has been raised from the dead', char)
            if n['curse'] and effects.has(char, 36):
                remove_curse(game, char)
                n['curse'] -= 1
                ack(game, 'is relieved of a curse', char)
            if not healed and n['sight'] and effects.has(char, 33):
                effects.remove_effect(game, s.selc(), 33)
                ack(game, 'regains sight', s.selc())

    cure()
    for char in s.chars():
        need = min(char.b[F['hp_max']] - char.b[F['hp']], pool)
        if need > 0 and restore_hit_points(game, char, need): pool -= need
    game.vm.party_drawn()
    game.vm.paint_location()
    rest[:] = saved
    for char in casters():
        n['heal'] += slot_count(char, 0, 6); n['flesh'] += slot_count(char, 3, 6); n['raised'] += slot_count(char, 0, 5)
        n['poison'] += slot_count(char, 0, 4); n['curse'] += slot_count(char, 3, 4) + slot_count(char, 0, 3)
        n['sight'] += slot_count(char, 0, 3)
    p = s.chars()
    dead = sum(c.b[F['status']] == 6 and c.b[F['race']] > 1 for c in p)
    feeble = sum(effects.has(c, 61) for c in p)
    needs = ((n['heal'], feeble, 90), (n['flesh'], sum(c.b[F['status']] == 7 for c in p), 90), (n['raised'], dead, 75),
             (n['poison'], sum(effects.has(c, 55) for c in p), 60),
             (n['sight'], sum(effects.has(c, 33) and not effects.has(c, 61) for c in p), 45),
             (n['curse'], sum(effects.has(c, 36) for c in p), 45))
    set_rest(rest, sum(min(have, want) * minutes for have, want, minutes in needs))
    if camp_rest(game, rest, False, fixing=True): return True
    cure()
    game.vm.party_drawn()
    game.vm.paint_location()
    rest[:] = saved
    return False


FIXED_EFFECT_NAMES = {2: "olin's quaterstaff", 4: 'Dispel Evil', 9: 'Boots Of Speed', 27: 'Fumbling', 31: 'Helpless',
    35: 'Confused', 44: 'Cause Disease', 50: 'Hot Fire Shield', 54: 'Cold Fire Shield', 55: 'Poisoned', 60: 'iron skin',
    61: 'Fire Resistance', 68: 'enfeebled', 69: 'invisible to animals', 71: 'Invisible', 72: 'Camouflaged',
    73: 'protected from dragon breath', 74: 'fire touch', 77: 'berserk', 89: 'Displaced'}
SPELL_NAMED_EFFECTS = frozenset((1, 5, 8, 10, 11, 12, 14, 16, 17, *range(19, 26), 28, 29, 32, 33, 34, 36, 37, 38, 39,
                                 41, 42, 45, 46, 49, 51, 52, 53, 59, 63))


def display(game):
    t = tables(game.assets)
    rows = [' ']
    for char in game.s.chars():
        rows.append(name(char))
        shown = []
        for e in char.effects:
            if e[0] in SPELL_NAMED_EFFECTS:
                spell = next((k for k in range(1, 64) if t.spells[(k - 1) * 16 + 10] == e[0]), None)
                shown.append(t.names[spell - 1] if spell else 'Funky--%d' % e[0])
            elif e[0] in FIXED_EFFECT_NAMES: shown.append(FIXED_EFFECT_NAMES[e[0]])
        rows += [' ' + n for n in shown] or [' <No Spell Effects>']
        rows.append(' ')
    game.ask(Kind.ACK.value, (EXIT,), prompt='', lines=tuple(rows), rows='\n'.join(rows), window='1 4 38 22', menu='')
    redraw_camp(game)


def magic_menu(game, rest):
    entries = ('Cast', 'Memorize', 'Scribe', 'Display', 'Rest')
    start = 0
    while True:
        pick = member_menu(game, '', entries, start=start, preserve_message=True)
        if pick is None: return False
        start = game.menu_highlight
        if pick == 1: memorize(game, game.s.selc())
        elif pick == 4:
            if rest_for_prep(game, rest): return True
        elif pick == 3: display(game)
        else: game.vm.service('magic', 'cast_menu' if pick == 0 else 'scribe', game.s.selc())


def run(game):
    from . import magic, services_alter
    s = game.s
    rest = s.g['camp.rest'] = [0] * 7
    previous, s.mode = s.mode, CAMPING
    s.g['camp.heal_ticks'] = 0
    runtime = s.g.setdefault('dkk.runtime', {})
    runtime['saved_picture_name'] = runtime.get('picture_name', '')
    runtime['saved_picture_id'] = runtime.get('picture_id', 255)
    redraw_camp(game)
    reset_scribing(game)
    interrupted, start, first = False, 0, True
    try:
        while not interrupted and s.chars() and not s.stop:
            pick = member_menu(game, 'Camp', ('Save', 'View', 'Magic', 'Rest', 'Alter', 'Fix'), start=start,
                               query='', camp_main=True, preserve_message=True,
                               message=game.assets.text('partyMakesCamp') if first else '')
            first = False
            if pick is None: break
            start = game.menu_highlight
            if pick == 0:
                s.r0[0x1F6] = (s.r0[0x1F6] + 1) & 255
                if s.r0[0x1F6] >= 10: s.r0[0x1F6] = 0
                game.vm.service('creation', 'save_menu')
                if yes_no(game, Kind.CONFIRM, game.assets.text('quitToDosPrompt'), start=1):
                    s.stop = 1
                    game.exit_game = True
                    break
            elif pick == 1: game.vm.service('inventory', 'view', s.selc())
            elif pick == 2: interrupted = magic_menu(game, rest)
            elif pick == 3: interrupted = rest_for_prep(game, rest)
            elif pick == 4: services_alter.run(game)
            else: interrupted = fix(game, rest)
    finally:
        if runtime['saved_picture_name'].startswith('PIC'):
            game.vm.archive(runtime['saved_picture_name'], runtime['saved_picture_id'])
        reset_scribing(game)
        magic.reset_target(game)
        s.mode = previous
        game.vm.paint_location()
        game.vm.clear_text()
    return interrupted


def test():
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from .menu import Game
    from ._creation_test import create_party
    results = []
    for _ in range(2):
        with TemporaryDirectory() as tmp:
            game = Game(None)
            game.roster_directory = Path(tmp)
            create_party(game)
            game.player = lambda kind, options, state, **info: 0
            cleric = game.s.party[1]
            t = tables(game.assets)
            assert can_cast(cleric, 3, t) and slots_remaining(cleric, 1, 0, t)[0] > 0
            cleric.b[F['memorized']] = 131
            rest = [0] * 7
            set_rest(rest, prep_minutes(cleric, t))
            assert rest[3] == 4 and rest[2] == 1 and rest[1] == 5
            assert not camp_rest(game, rest, False)
            assert memory(cleric)[0] == 3 and not any(rest)
            fighter = game.s.party[0]
            fighter.b[F['hp']] -= 10
            effects.add_effect(fighter, 55, 0, 255, False)
            fix(game, rest)
            assert not game.s.g['camp.rest_active'] and not game.s.g['no_border']
            reset_scribing(game)
            results.append((game.s.hash(), tuple(game.trace)))
    assert results[0] == results[1]
