from enum import Enum
from functools import lru_cache
import hashlib

from sm.files import DataError
from .creation import EXIT, F, choose, dice, yes_no
from . import alter, creation, effects, magic
from .effects import age_effects
from .faults import BindingRequired


class Kind(str, Enum):
    MENU = 'CAMP_MENU'
    WHO = 'WHO'
    SPELL = 'SPELL'
    REST = 'CAMP_REST'
    RESTING = 'CAMP_RESTING'
    CONFIRM = 'CAMP_CONFIRM'
    ACK = 'ACK'


CLERIC, RANGER, MAGE, THIEF, KNIGHT = 0, 4, 5, 6, 7
HUMAN, ANIMATED, UNCONSCIOUS, DYING, CAMPING = 6, 1, 4, 5, 2
PENDING, SPELL_MASK, MEMORY_SLOTS = 0x80, 0x7F, 58
CLOCK_CELL, REST_PERIOD_CELL, REST_CHANCE_CELL = 0xC6, 0x2D2, 0x2D3
SPELL_NAMES = dict(offset=56576, size=4387, sha256='2a1f5974edf77e34ef70cf13cec85e5d3eeab2b10586b4a80f17eb2676838975')
CAMP_MENU = ('Save', 'View', 'Magic', 'Rest', 'Alter', 'Fix')
MAGIC_MENU = ('Cast', 'Memorize', 'Scribe', 'Display', 'Rest')
SAVES_CELL = 0x13C
SPELL_NAMED_EFFECTS = frozenset((1, 2, 5, 8, 9, 10, 11, 12, 14, 16, 17, *range(19, 26), 28, 29, 32, 33, 34, 36, 37, 38, 39, 41, 42, 45, 46, 49, 51, 52, 53))
FIXED_EFFECT_LABELS = {4: 'Dispel Evil', 27: 'Fumbling', 31: 'Helpless', 35: 'Confused', 44: 'Cause Disease', 50: 'Hot Fire Shield', 54: 'Cold Fire Shield', 55: 'Poisoned',
                       59: 'Regenerating', 61: 'Fire Resistance', 63: 'Minor Globe of Invulnerability', 68: 'enfeebled', 69: 'invisible to animals', 71: 'Invisible',
                       72: 'Camouflaged', 73: 'protected from dragon breath', 77: 'berserk', 89: 'Displaced'}
REST_MENU = ('Rest', 'Days', 'Hours', 'Mins', 'Add', 'Subtract', 'Exit')
DAYS, HOURS, TENS, MINUTES = 4, 3, 2, 1
MEMBER_KEYS = ('char-up', 'char-down')
MEMORIZE_PAGE = 11
MEMORIZED_CURES = {3: (1, 8, 0), 58: (2, 8, 1), 71: (3, 8, 3)}


class Tables:
    def __init__(self, assets):
        raw = assets.resident[SPELL_NAMES['offset']:SPELL_NAMES['offset'] + SPELL_NAMES['size']]
        if hashlib.sha256(raw).hexdigest() != SPELL_NAMES['sha256']:
            raise DataError('Champions spell-name table differs')
        self.names = tuple(raw[i + 1:i + 1 + raw[i]].decode('cp437') for i in range(0, len(raw), 41))
        self.spells, self.scale = assets.table('spellTbl'), assets.table('unitScale')

    def spell_class(self, spell):
        return self.spells[(spell - 1) * 16]

    def level(self, spell):
        return self.spells[(spell - 1) * 16 + 1]


@lru_cache(maxsize=4)
def tables(assets):
    return Tables(assets)


def name(char):
    return bytes(char.b[1:1 + char.b[0]]).decode('cp437')


def ack(game, text):
    game.ask(Kind.ACK.value, ('Continue',), prompt=text)


def memory(char):
    return char.b[F['memorized']:F['memorized'] + MEMORY_SLOTS]


def ability(char, index):
    return char.b[F['abilities'] + index * 2 + 1]


def level_of(char, cls):
    return char.b[F['levels'] + cls]


def earlier_class_active(char):
    levels = char.b[F['levels']:F['levels'] + 8]
    level = levels[next((i for i in range(7) if levels[i]), 7)] if char.b[F['race']] == HUMAN else 0
    return level > char.b[F['dual_threshold']]


def can_cast(char, spell, t):
    return magic.can_cast(char, spell)


def reset_memorize(char):
    for at in range(F['memorized'], F['memorized'] + MEMORY_SLOTS):
        if char.b[at] > SPELL_MASK: char.b[at] = 0
    char.b[F['preparation']] = 0


def prep_minutes(char, t):
    levels = [max(t.level(n & SPELL_MASK), 1) for n in memory(char) if n > SPELL_MASK]
    scribed_high, scribed_total = magic.scribed_levels(char)
    memorized_total, scribed_total = sum(levels) & 255, scribed_total & 255
    hours = 6 if max(levels, default=0) > 2 or scribed_high > 2 else 4 if memorized_total or scribed_total else 0
    char.b[F['preparation']] = hours
    return hours * 60 + (memorized_total + scribed_total) * 15


def slot_count(char, cls, level):
    return char.b[F['spell_slots'] + cls * 5 + level - 1]


def slots_remaining(char, level, cls, t):
    if cls == 2:
        allowance = {4: 3, 6: 0}.get(char.b[F['deity']], 1) if level_of(char, CLERIC) > 0 else 0
        return (allowance - sum(100 < n & SPELL_MASK < 108 for n in memory(char))) & 255, 0
    used = sum(1 for n in memory(char) if n and t.level(n & SPELL_MASK) == level and t.spell_class(n & SPELL_MASK) == cls)
    count = slot_count(char, cls, level)
    return count - min(count, used), used


SLOT_LABELS = ('    Cleric Spells:', '     Druid Spells:', '   Special Spells:', 'Magic-User Spells:')


def slot_row(label, values):
    return (label.ljust(19) + ''.join(v.ljust(3) for v in values)).rstrip()


def slot_display(game, char, t):
    special = level_of(char, CLERIC) > 0 and char.b[F['deity']] != 6
    any_slots, lines = special, []
    for cls in (0, 1, 2, 3):
        if cls == 2:
            if special: lines.append(slot_row(SLOT_LABELS[2], [str(slots_remaining(char, 0, 2, t)[0])]))
            continue
        row = [str(slots_remaining(char, level, cls, t)[0]) if slot_count(char, cls, level) else ' ' for level in range(1, 6)]
        if any(v != ' ' for v in row):
            any_slots = True
            lines.append(slot_row(SLOT_LABELS[cls], row))
    bonus = 0
    if level_of(char, MAGE) > 0 and char.b[F['robe_order']] > 0:
        value = game.s.r0[0x1F8 + char.b[F['robe_order']]]
        bonus = value if value in (1, 2) else 0
        for level in range(1, 6):
            if bonus:
                over = slots_remaining(char, level, 3, t)[1] - slot_count(char, 3, level)
                if over > 0: bonus = 0 if over > bonus else bonus - over
        any_slots = any_slots or bonus > 0
    if bonus: lines.append(slot_row('     Bonus Spells', [str(bonus)]))
    return bonus, any_slots, chr(10).join(lines)


def memorizable(char, t):
    held = {n & SPELL_MASK for n in memory(char)[1:]}
    return sorted((s for s in range(1, 108) if char.b[F['known_spells'] + s - 1] and can_cast(char, s, t) and not (t.spell_class(s) == 2 and s in held)), key=t.level)


def sort_memory(char):
    b, base = char.b, F['memorized']
    for left in range(MEMORY_SLOTS - 1):
        for right in range(left, MEMORY_SLOTS):
            if b[base + left] & SPELL_MASK > b[base + right] & SPELL_MASK: b[base + left], b[base + right] = b[base + right], b[base + left]


def pending_names(char, t):
    rows = magic.castable(char, pending=True)
    return tuple(' *' + t.names[s - 1] + (' (%d)' % n if n > 1 else '') for s, n in rows), tuple(t.level(s) for s, _ in rows)


def show_pending(game, char, t):
    lines, levels = pending_names(char, t)
    if lines: choose(game, Kind.SPELL, '', [], title='to Memorize', lines=lines, levels=levels)
    return bool(lines)


def opening_row(levels, page):
    rows, last = [], 0
    for level in levels:
        if not rows or level > last: rows.append(None)
        rows.append(level)
        last = level
    at = min(page, len(rows)) - 1
    while rows[at] is None: at -= 1
    return sum(row is not None for row in rows[:at])


def memorize(game, char):
    t = tables(game.assets)
    if char.b[F['status']] == ANIMATED or not char.b[F['active']]:
        ack(game, name(char) + ' is in no condition to memorize spells')
        return
    if show_pending(game, char, t):
        if yes_no(game, Kind.CONFIRM, 'Memorize These Spells? ', spells=pending_names(char, t)[0]): return
        reset_memorize(char)
    picked, start = False, None
    while True:
        bonus, any_slots, left = slot_display(game, char, t)
        if not any_slots:
            ack(game, name(char) + ' cannot memorize any spells')
            break
        ids = memorizable(char, t)
        if not ids: break
        picked = True
        if start is None: start = opening_row([t.level(s) for s in ids], MEMORIZE_PAGE)
        pick = choose(game, Kind.SPELL, 'memorize', [t.names[s - 1] for s in ids], slots=left, bonus=bonus, start=min(start, len(ids) - 1))
        if pick is None: break
        start = pick
        spell = ids[pick]
        if slots_remaining(char, t.level(spell), t.spell_class(spell), t)[0] > 0 or t.spell_class(spell) == 3 and bonus > 0:
            at = next((i for i, n in enumerate(memory(char)) if n == 0), None)
            if at is not None:
                char.b[F['memorized'] + at] = spell | PENDING
                sort_memory(char)
    if picked and show_pending(game, char, t) and not yes_no(game, Kind.CONFIRM, 'Memorize these spells? ', spells=pending_names(char, t)[0]):
        reset_memorize(char)


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
                for char in s.party:
                    age = F['age']
                    char.b[age:age + 2] = ((int.from_bytes(char.b[age:age + 2], 'little') + 1) & 0xFFFF).to_bytes(2, 'little')
            else:
                clock[i + 1] += 1
                clock[i] -= scale[i]
                if i == 3: advance_junctions(s)


def validate_rest(game, rest):
    validate_clock(game, rest)
    if rest[5]:
        rest[4] = min(rest[4] + tables(game.assets).scale[4] * rest[5], 99)
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
                rest[k] -= 1
                rest[k - 1] += scale[k - 1]
    rest[unit] -= count
    validate_rest(game, rest)


def advance_time(game, flags):
    effects.advance(game, 5, 1, flags)


def restore_hit_points(game, char, amount):
    if char.b[F['status']] not in (0, ANIMATED, UNCONSCIOUS, DYING): return False
    char.b[F['hp']] = min((char.b[F['hp']] + amount) & 255, char.b[F['hp_max']])
    if not char.b[F['active']]:
        if char.b[F['status']] == DYING: char.b[F['status']] = UNCONSCIOUS
        if char.b[F['status']] == UNCONSCIOUS:
            char.b[F['status']], char.b[F['active']] = 0, 1
    return True


def heal_tick(game):
    g = game.s.g
    g['camp.heal_ticks'] = g.get('camp.heal_ticks', 0) + 1
    if g['camp.heal_ticks'] >= 288:
        for char in game.s.party: restore_hit_points(game, char, 1)
        ack(game, 'The Whole Party Is Healed')
        g['camp.heal_ticks'] = 0


def next_pending(game, char, finish, t):
    level, at = 0, F['memorized']
    for i in range(MEMORY_SLOTS):
        if level: break
        if char.b[at + i] > SPELL_MASK:
            if finish: level = t.level(char.b[at + i] & SPELL_MASK)
            else:
                char.b[at + i] -= PENDING
                ack(game, name(char) + ' has memorized ' + t.names[(char.b[at + i] & SPELL_MASK) - 1])
                finish = True
    return level, finish


def next_preparation(game, char, finish, t):
    level, finish = magic.finish_scribe(game, char, finish)
    return level or next_pending(game, char, finish, t)[0]


def camp_rest(game, rest, interactive):
    s, t = game.s, tables(game.assets)
    timers, flags, tick, steps = [0] * len(s.party), [True] * len(s.party), 0, 0
    if interactive and not rest_menu(game, rest): return False
    while any(rest[1:5]):
        if interactive and steps and steps % 5 == 0 and getattr(game, 'rest_poll', False):
            if (game.ask(Kind.RESTING.value, ('Continue', 'Stop'), days=rest[DAYS], hours=rest[HOURS], minutes=10 * rest[TENS] + rest[MINUTES])
                    and yes_no(game, Kind.CONFIRM, 'Stop Resting? ')): break
        steps += 1
        decrement_rest(game, rest, 5, 1)
        advance_time(game, flags)
        heal_tick(game)
        for index, char in enumerate(s.party):
            if timers[index]: timers[index] -= 1
            if timers[index] == 0 and char.b[F['preparation']] == 0:
                timers[index] = next_preparation(game, char, False, t) * 3
        tick += 1
        if tick >= 12:
            tick = 0
            for index, char in enumerate(s.party):
                if char.b[F['preparation']]:
                    char.b[F['preparation']] -= 1
                    if not char.b[F['preparation']]: timers[index] = next_preparation(game, char, True, t) * 3
        if s.r1[REST_PERIOD_CELL]:
            s.g['camp.rest_ticks'] = s.g.get('camp.rest_ticks', 0) + 1
            if s.g['camp.rest_ticks'] >= s.r1[REST_PERIOD_CELL]:
                s.g['camp.rest_ticks'] = 0
                if dice(s, 1, 100) <= s.r1[REST_CHANCE_CELL]:
                    ack(game, 'Your repose is suddenly interrupted!')
                    return True
    return False


def rest_menu(game, rest):
    selected = TENS
    while True:
        pick = REST_MENU[game.ask(Kind.REST.value, REST_MENU, prompt='Rest Time', days=rest[DAYS], hours=rest[HOURS],
                                  minutes=10 * rest[TENS] + rest[MINUTES], field=selected)]
        if pick == 'Rest': return True
        if pick == 'Exit': return False
        if pick in ('Days', 'Hours', 'Mins'): selected = {'Days': DAYS, 'Hours': HOURS, 'Mins': TENS}[pick]
        elif pick == 'Add':
            if selected == TENS: rest[MINUTES] += 5
            else: rest[selected] += 1
            validate_rest(game, rest)
        else:
            if selected == TENS: decrement_rest(game, rest, 5, MINUTES)
            else: decrement_rest(game, rest, 1, selected)
            validate_rest(game, rest)


def set_rest(rest, minutes):
    rest[HOURS], rest[TENS], rest[MINUTES] = minutes // 60, (minutes % 60) // 10, minutes % 10


def rest_for_prep(game, rest):
    set_rest(rest, max(prep_minutes(char, tables(game.assets)) for char in game.s.party))
    interrupted = camp_rest(game, rest, True)
    rest[:] = [0] * 7
    return interrupted


def missing(s):
    return sum(char.b[F['hp_max']] - char.b[F['hp']] for char in s.party)


def fix(game, rest):
    s = game.s
    if not missing(s): return False
    pool = 0
    for char in s.party:
        if char.b[F['status']] == 0:
            for spell in memory(char):
                if spell in MEMORIZED_CURES:
                    count, sides, bonus = MEMORIZED_CURES[spell]
                    pool += dice(s, count, sides) + bonus
    light = serious = critical = light_minutes = serious_minutes = critical_minutes = expected = required = 0
    for char in s.party:
        if char.b[F['status']] == 0:
            light += slot_count(char, 0, 1); light_minutes = slot_count(char, 0, 1) * 15
            serious += slot_count(char, 0, 4); serious_minutes = slot_count(char, 0, 4) * 60
            critical += slot_count(char, 0, 5); critical_minutes = slot_count(char, 0, 5) * 75
        minutes = 0
        if light_minutes:
            minutes = 240; expected += 27
        if serious_minutes + critical_minutes:
            minutes = 360; expected += 78 if critical_minutes else 34
        required = max(required, minutes + light_minutes + serious_minutes + critical_minutes)
    if missing(s) < expected:
        ratio = (expected // missing(s)) & 255
        if ratio: required //= ratio
    saved = rest[:]
    set_rest(rest, required)
    if camp_rest(game, rest, False): return True
    for count, roll, bonus in ((light, (1, 8), 0), (serious, (2, 8), 1), (critical, (3, 8), 3)):
        for _ in range(count): pool += dice(s, *roll) + bonus
    for char in s.party:
        need = min(char.b[F['hp_max']] - char.b[F['hp']], pool)
        if need > 0 and restore_hit_points(game, char, need): pool -= need
    rest[:] = saved
    return False


def reset_party(s):
    for char in s.party:
        reset_memorize(char)
        magic.reset_scribe(char)


def effect_label(effect_id, t):
    if effect_id in SPELL_NAMED_EFFECTS:
        spell = next((n for n in range(1, 57) if t.spells[(n - 1) * 16 + 10] == effect_id), None)
        return t.names[spell - 1] if spell else 'Funky--%d' % effect_id
    return FIXED_EFFECT_LABELS.get(effect_id)


def display_lines(s, t):
    lines = [' ']
    for char in s.party:
        labels = [label for label in (effect_label(e[0], t) for e in char.effects) if label is not None]
        lines += [name(char), *(' ' + label for label in labels or ('<No Spell Effects>',)), ' ']
    return tuple(lines)


def display(game):
    lines = display_lines(game.s, tables(game.assets))
    game.ask(Kind.ACK.value, (EXIT,), prompt=' / '.join(line.strip() for line in lines if line.strip()), lines=lines, rows='\n'.join(lines),
             window='1 4 38 22', menu='')


def member_menu(game, prompt, entries):
    s, options = game.s, entries + (EXIT,) + MEMBER_KEYS
    while True:
        pick = game.ask(Kind.MENU.value, options, prompt=prompt, member=name(s.party[s.sel]))
        if options[pick] not in MEMBER_KEYS: return None if pick == len(entries) else pick
        s.sel = (s.sel + (-1 if options[pick] == 'char-up' else 1)) % len(s.party)


def magic_menu(game, rest):
    while True:
        pick = member_menu(game, 'Magic', MAGIC_MENU)
        if pick is None: return False
        entry = MAGIC_MENU[pick]
        if entry == 'Display': display(game)
        elif entry == 'Rest':
            if rest_for_prep(game, rest): return True
        else: {'Cast': magic.cast_menu, 'Memorize': memorize, 'Scribe': magic.scribe}[entry](game, game.s.party[game.s.sel])


def save_entry(game):
    s = game.s
    s.r0[SAVES_CELL] += 1
    if s.r0[SAVES_CELL] >= 10: s.r0[SAVES_CELL] = 0
    creation.save_menu(game)
    if yes_no(game, Kind.CONFIRM, 'Quit TO DOS '):
        s.stop = 1
        game.exit_game = True
        return True
    return False


def run(game):
    s, rest = game.s, [0] * 7
    mode, s.mode = s.mode, CAMPING
    s.g['camp.heal_ticks'] = 0
    reset_party(s)
    interrupted = False
    try:
        while not interrupted:
            pick = member_menu(game, 'Camp', CAMP_MENU)
            if pick is None: break
            entry = CAMP_MENU[pick]
            if entry == 'Save':
                if save_entry(game): break
            elif entry == 'View': game.vm.service('explore', 'view')
            elif entry == 'Magic': interrupted = magic_menu(game, rest)
            elif entry == 'Rest': interrupted = rest_for_prep(game, rest)
            elif entry == 'Alter':
                if alter.run(game): break
            else: interrupted = fix(game, rest)
    finally:
        reset_party(s)
        s.mode = mode
    return interrupted
