"""PORT2 camp ov18 and rest ov22 (ENGINE_READ2_g3/g1, ENGINE_READ_w6).

Rest advances five-minute ticks. Natural healing is ONE HP per 288 ticks,
not full restoration. Magic owns spell menus/effect callbacks; camp owns study
countdowns. All persistent counters live in State.g and participate in replay.
"""
from sm.titles.ssb import rec
from sm.titles.ssb.units import shops, creation
from sm.titles.ssb.units.shops import choose, message


def pending(c):
    """ov22:095E/089C: pending scribe powers precede pending memorized spells."""
    for root, group in shops.groups(c.items):
        for j, it in enumerate(group[1:] if group[0][0x2E] == 0x49 else group):
            if it[0x2E] in (0x27, 0x28):
                index = root + j + (group[0][0x2E] == 0x49)
                for o in range(0x3C, 0x3F):
                    if it[o] > 128: yield ('scribe', index, o, it[o] & 127)
    for o in range(0x1E, 0x69):
        if c.b[o] > 127: yield ('memorize', 0, o, c.b[o] & 127)


def spell_level(sid):
    """ov18:0023: memorization id's spell-table level (zero treated as one)."""
    from sm.titles.ssb.units import magic
    return magic.spell(sid)[1] if 1 <= sid <= 117 else 0


def rest_need(c):
    """ov18:0023: 4h sleep, 6h if any pending level >2, plus 15min per spell level."""
    levels = [max(1, spell_level(sid)) if kind == 'memorize' else spell_level(sid) for kind, _, _, sid in pending(c)]
    hours = (6 if max(levels, default=0) > 2 else 4) if sum(levels) else 0
    c.b[0x69] = hours
    return hours * 60 + 15 * sum(levels)


def clear_marks(c):
    """ov18:05C9/060C: cancel pending memory slots, unmark scrolls, clear rest_need."""
    for o in range(0x1E, 0x69):
        if c.b[o] > 127: c.b[o] = 0
    c.b[0x69] = 0
    for _, group in shops.groups(c.items):
        for it in group:
            if it[0x2E] in (0x27, 0x28):
                for o in range(0x3C, 0x3F): it[o] &= 127


def consume_scroll(c, index, offset):
    """ov23:647F: use charge, unlink exhausted scroll, collapse one-member bundle."""
    root, group = next((r, g) for r, g in shops.groups(c.items) if r <= index < r + len(g))
    it = c.items[index]; it[offset] = 0; it[0x2F] = (it[0x2F] - 1) & 255
    if it[0x2F] >= 100: return
    del c.items[index]
    if group[0][0x2E] == 0x49:
        head = c.items[root]; head[0x39] -= 1
        if head[0x39] == 1:
            child = c.items.pop(root + 1); child[0x3F:0x43] = bytes(4); c.items[root] = child
    shops.recalc(c)


def study_tick(c, complete=False):
    """ov22:095E/089C: consume at most one pending operation; return next level."""
    work = list(pending(c))
    if work and complete:
        kind, index, offset, sid = work[0]
        if kind == 'scribe':
            if not 1 <= sid <= 117: raise ValueError('invalid scribe spell')
            c.b[0x70 + sid] = 1; consume_scroll(c, index, offset)
        else: c.b[offset] &= 127
        work = list(pending(c))
    return spell_level(work[0][3]) if work else 0


def rest(game, minutes, interactive=False):
    """ov22:0D25: clock/heal/study/hour/encounter order; return whether interrupted."""
    from sm.titles.ssb.units import magic
    if not isinstance(minutes, int) or minutes < 0: raise ValueError('rest minutes must be nonnegative')
    s = game.s; countdown = [0] * len(s.party); hour = 0; elapsed = 0; interrupted = False
    s.g['8DB4'] = 1; s.g['camp.remaining'] = minutes; s.g['camp.countdown'] = tuple(countdown)
    try:
        while minutes > 0:
            # ov22:0DED..0DFA polls AnyInput before EACH five-minute tick; no input means no prompt.
            if interactive and game.ask('INPUT', ['none', 'pending'], purpose='rest', remaining=minutes, at=0x0DF3):
                if game.ask('CAMP_MENU', ['continue', 'stop'], purpose='resting', remaining=minutes,
                            prompt='Stop Resting?'): break  # ov22:0DED: Y stops, N resumes.
            minutes = max(0, minutes - 5); elapsed += 5
            game.vm.advance_clock(5, 1)
            s.g['camp.rested'] = 1
            s.g['8DB2'] = s.g.get('8DB2', 0) + 1
            if s.g['8DB2'] >= 288:
                for c in s.party: magic.heal(game, c, 1)
                if interactive: message(game, 'The Whole Party Is Healed')  # ov22:0839..0885
                s.g['8DB2'] = 0
            for i, c in enumerate(s.party):
                if countdown[i]: countdown[i] -= 1
                if countdown[i] == 0 and c.b[0x69] == 0:
                    work = next(pending(c), None)
                    countdown[i] = 3 * study_tick(c, True)
                    if work:
                        verb = 'has scribed' if work[0] == 'scribe' else 'has memorized'
                        message(game, '%s %s %s' % (shops.name(c), verb, magic.spell_name(work[3])))  # ov22:089C/095E
            hour += 1
            if hour >= 12:
                hour = 0
                for i, c in enumerate(s.party):
                    if c.b[0x69]:
                        c.b[0x69] -= 1
                        if not c.b[0x69]: countdown[i] = 3 * study_tick(c)
            s.g['camp.countdown'] = tuple(countdown); s.g['camp.hour'] = hour; s.g['camp.remaining'] = minutes
            interval = s.r1[0x2D2]
            if interval:
                s.g['67F1'] = s.g.get('67F1', 0) + 1
                if s.g['67F1'] >= interval:
                    s.g['67F1'] = 0
                    if s.random(100) + 1 <= s.r1[0x2D3]:
                        interrupted = True
                        message(game, 'Your repose is suddenly interrupted!')  # ov22:0E7E..0EED
                        break
    finally: s.g['8DB4'] = 0
    game.vm.clear_text()  # ov22:0EF5..0F01 clears the rest/study message rectangle on every return.
    s.g['camp.interrupted'] = int(interrupted)
    return interrupted


def rest_menu(game):
    """ov18:0CE7 / ov22:0691: clock editor; ov22:0D8B..0D97 clears its message area."""
    minutes = max((rest_need(c) for c in game.s.party), default=0)
    game.vm.clear_text()
    field = 'minutes'
    while True:
        game.s.g['camp.remaining'] = minutes
        options = ['rest', 'days', 'hours', 'minutes', 'exit', 'add', 'subtract']
        action = options[game.ask('CAMP_MENU', options, purpose='rest duration', minutes=minutes, field=field)]
        if action == 'exit': return False
        if action == 'rest': return rest(game, minutes, True)
        if action in ('days', 'hours', 'minutes'): field = action
        else:
            scale = {'days': 1440, 'hours': 60, 'minutes': 5}[field]
            minutes = max(0, minutes + (scale if action == 'add' else -scale))  # ov22:0307/03E0 normalize/borrow


def fix_needs(s):
    """ov18:2E41: count raise, curse, sight, disease, heal, poison, stone needs."""
    result = dict.fromkeys(('raise', 'curse', 'sight', 'disease', 'heal', 'poison', 'stone'), 0)
    for c in s.party:
        result['raise'] += c.b[0x1A6] == 6 and c.b[0x6B] not in (1, 2)
        result['stone'] += c.b[0x1A6] == 7
        result['curse'] += rec.has_effect(c, 0x24); result['poison'] += rec.has_effect(c, 0x37)
        if rec.has_effect(c, 0x44): result['heal'] += 1
        else: result['sight'] += rec.has_effect(c, 0x21); result['disease'] += rec.has_effect(c, 0x22)
    return result


def fix_status(game, have):
    """ov18:28FE: automatic status cures, preserving non-decrementing disease/sight quirks."""
    from sm.titles.ssb.units import magic
    s = game.s
    for c in s.party:
        healed = have['heal'] > 0 and rec.has_effect(c, 0x44)
        if healed:
            for t in (0x44, 0x21, *shops.DISEASE): magic.remove_effect(game, c, t)
            have['heal'] -= 1
            shops.name_message(game, c, 'is healed')  # ov18:29F0.
        if have['stone'] and c.b[0x1A6] == 7:
            shops.cure(game, c, 9, result_text='is changed back to flesh'); have['stone'] -= 1  # ov18:2A47.
        if have['poison'] and rec.has_effect(c, 0x37):
            shops.cure(game, c, 6, result_text='is detoxified'); have['poison'] -= 1  # ov18:2B01.
        if have['raise'] and c.b[0x1A6] == 6 and c.b[0x6B] not in (1, 2):
            # ov18:2B0D..2C9D differs from the temple: seven class slots, penalty also below CON 14.
            b = c.b; s.g['87DC'] = 1; magic.remove_effect(game, c, 0x37); s.g['87DC'] = 0
            b[0x1B5], b[0x1A6], b[0x1A7] = 1, 0, 1; b[0x19] = max(0, b[0x19] - 1)
            con = b[0x19]; loss = max(0, b[0x70] - b[0x131]); divisor = 0
            if con >= 14:
                divisor = sum(lv * (con - 14 if i in (2, 3, 4) else 2 if con > 15 else 1)
                              for i, lv in enumerate(b[0x111:0x118]) if 0 < rec.sx(lv)) & 255
            if divisor: loss //= divisor
            if con < 17 or rec.sx(b[0x113]) > 0 or rec.sx(b[0x113]) > rec.sx(b[0xEF]): b[0x70] = (b[0x70] - loss) & 255
            have['raise'] -= 1
            shops.name_message(game, c, 'has been raised from the dead')  # ov18:2CBC.
        if have['curse'] and rec.has_effect(c, 0x24):
            shops.cure(game, c, 8, result_text='is relieved of a curse'); have['curse'] -= 1  # ov18:2D15.
        diseased = not healed and have['disease'] and any(rec.has_effect(c, t) for t in shops.DISEASE)
        if diseased: shops.cure(game, c, 1, result_text='is cured of disease')  # ov18:2DC4.
        elif not healed and have['sight'] and rec.has_effect(c, 0x21):
            magic.remove_effect(game, s.selc() or c, 0x21)   # sic: selected character, not patient
            shops.name_message(game, s.selc() or c, 'regains sight')  # ov18:2E23 uses SelectedChar too.


def fix(game):
    """ov18:2F86: spell-healing pool, rest for cures, then a second status-cure rest."""
    from sm.titles.ssb.units import magic
    s = game.s; missing = sum(c.b[0x70] - c.b[0x1B5] for c in s.party)
    if missing == 0: return False
    have = dict.fromkeys(('raise', 'curse', 'sight', 'disease', 'heal', 'poison', 'stone'), 0); pool = 0
    for c in s.party:
        if c.b[0x1A6]: continue
        for sid in c.b[0x1E:0x69]:
            if sid in (3, 98): pool += creation.roll(s, 1, 8)
            elif sid == 58: pool += creation.roll(s, 2, 8) + 1
            elif sid == 71: pool += creation.roll(s, 3, 8) + 3
            elif sid == 36: pool += creation.roll(s, 4, 8) + 5; have['heal'] += 1
            elif sid in (67, 75, 43, 89, 113, 37, 39):
                have[{67: 'poison', 75: 'raise', 43: 'curse', 89: 'curse', 113: 'stone', 37: 'sight', 39: 'disease'}[sid]] += 1
    slots = [0] * 4; times = [0] * 5; duration = 0
    # ov18:23D1 leaves its expected-healing stack word uninitialized. Deterministic
    # headless model supplies an explicit, hashed initial value (default zero).
    expected = s.g.get('camp.fix.expected', 0)
    for c in s.party:
        b = c.b; base = 0
        if b[0x1A6] == 0 and b[0x15] > 3:
            slots[0] += b[0x132] + b[0x13A]; slots[1] += b[0x135]; slots[2] += b[0x136]; slots[3] += b[0x137]
            times = [b[o] * t for o, t in ((0x132, 15), (0x13A, 30), (0x135, 60), (0x136, 75), (0x137, 90))]
        if times[0]: base = 240; expected += 27
        if times[1]: base = 240; expected += 27
        if times[2] + times[3]: base = 360; expected += 78 if times[3] else 34
        if times[4]: base = 480; expected += 90
        duration = max(duration, (base + sum(times)) & 65535)
    if 0 < missing < expected:
        divisor = (expected // missing) & 255
        if divisor: duration //= divisor
    if rest(game, duration): return True
    for tier, count in enumerate(slots):
        for _ in range(count & 255): pool += creation.roll(s, tier + 1, 8) + (0, 1, 3, 3)[tier]
    fix_status(game, have)
    for c in s.party:
        amount = min(c.b[0x70] - c.b[0x1B5], pool)
        if amount > 0 and magic.heal(game, c, amount): pool -= amount
    needs = fix_needs(s)
    for c in s.party:
        b = c.b
        if b[0x1A6]: continue
        for key, count in (('heal', b[0x137]), ('stone', b[0x14C]), ('raise', b[0x136]), ('poison', b[0x135]),
                           ('curse', b[0x14A] + b[0x134]), ('sight', b[0x134]), ('disease', b[0x134])): have[key] += count
    duration = sum(min(have[k], needs[k]) * t for k, t in (('heal', 90), ('stone', 90), ('raise', 75), ('poison', 60), ('disease', 45), ('sight', 45), ('curse', 45))) & 65535
    if rest(game, duration): return True
    fix_status(game, have)
    return False


def cast_command(game, caster=None):
    """ov18:09D1..0A87: noncombat picker repeats until Exit, including unavailable spells."""
    from sm.titles.ssb.units import magic
    c = caster or game.s.selc()
    if c is None: return
    if game.s.r0[0xE5]: shops.name_message(game, c, 'cannot cast spells in this area'); return  # ov18:08AD..09AB.
    if not c.b[0x1A7] or c.b[0x1A6] == 1:
        shops.name_message(game, c, 'is in no condition to cast any spells'); return
    if rec.has_effect(c, 0x44): return
    game.s.g['8D87'] = game.s.g['8D89'] = 0
    command = 0
    while True:
        memory = sorted({sid for sid in c.b[0x1E:0x69] if 0 < sid <= 117})
        if not memory: shops.name_message(game, c, 'has no spells memorized'); break  # ov18:0A6D.
        legal = magic.legal_spells(c)
        options = legal + ['cancel'] + [sid for sid in memory if sid not in legal]  # preserve existing legal/Cancel answer indices.
        game.vm.clear_text()  # ov21:3C63, called by ov18:0A0B, replaces the previous spell/result panel.
        sid = options[game.ask('SPELL', options, caster=game.s.party.index(c), command=command, at=0x1403)]
        if sid == 'cancel': break
        game.vm.clear_text()  # ov18:0A1D..0A29 before the target/refusal prompt.
        if sid not in legal:
            # ov23:1438..14B5: an unusable memorized spell is offered, with an explicit lose confirmation.
            command = game.ask('SPELL', ['yes', 'no'], purpose='cast refusal', spell=sid,
                               caster=game.s.party.index(c), prompt='Lose it?')
            if command == 0: magic.forget(c, sid)
        else:
            magic.cast(game, c, sid)
            command = 0
    game.vm.clear_text()  # ov18:0A78..0A83 -> ov26:3031 redraw after leaving the picker.


def magic_menu(game):
    """ov18:1757: Cast/Memorize/Scribe/Display/Rest; spell choices delegated to magic."""
    from sm.titles.ssb.units import magic
    s = game.s
    while True:
        action = choose(game, 'CAMP_MENU', ['cast', 'memorize', 'scribe', 'display', 'rest', 'select', 'exit'], purpose='magic')
        if action == 'exit': return False
        if action == 'select': shops.pick_member(game); continue
        c = s.selc()
        if action == 'rest':
            if rest_menu(game): return True
        elif c is not None:
            if action == 'cast': cast_command(game, c)  # ov18:17E7 -> 09D1, not a single CastSpell call.
            elif action == 'memorize': magic.memorize(game, c)
            elif action == 'scribe': magic.scribe(game, c)
            elif action == 'display':
                game.vm.clear_text()  # ov18:16C9/172E clears the replaced panel and redraws the caller on exit.
                choose(game, 'CAMP_MENU', ['exit'], purpose='effects', effects=[(shops.name(p), [e[0] for e in p.effects]) for p in s.party])
                game.vm.clear_text()


def speed(game, combat=False):
    """ov18:1ED8 / ov10:188C: Faster/Slower bounded 0..9, returning only on Exit."""
    while True:
        value = game.s.g.get('67D6', 0)
        options = (['slower'] if value < 9 else []) + (['faster'] if value else []) + ['exit']
        if not combat: options = sorted(options, key=lambda action: ('faster', 'slower', 'exit').index(action))
        action = options[game.ask('MENU' if combat else 'CAMP_MENU', options, purpose='speed', speed=value,
                                 prompt='GameSpeed (%d) :' % value if combat else 'Game Speed:')]
        if action == 'exit': return
        game.s.g['67D6'] = value + (1 if action == 'slower' else -1)


def alter(game):
    """ov18:2054: Order/Drop/Speed/Icon/Level; record and game-flag changes only."""
    s = game.s
    while True:
        action = choose(game, 'CAMP_MENU', ['order', 'drop', 'speed', 'icon', 'level', 'exit'], purpose='alter')
        if action == 'exit': return
        if action == 'level': s.r0[0x1F4] = choose(game, 'CAMP_MENU', list(range(5)), purpose='difficulty')
        elif action == 'speed': speed(game)  # ov18:1ED8
        elif action == 'drop':
            c = s.selc()  # ov18:1C53..1CD4 uses SelectedChar directly.
            shops.name_message(game, c, 'will be gone', clear=False)  # ov18:1CD4, stays under AskYesNo.
            if choose(game, 'CAMP_MENU', ['yes', 'no'], purpose='drop from party', bottom_prompt='Drop from party? ', roster=False) == 'yes':
                shops.name_message(game, c, 'bids you farewell' if c.b[0x1A7] else 'is dumped in a ditch')  # 1D29/1D4D.
                s.party.remove(c); s.sel = min(s.sel, max(0, len(s.party) - 1)); s.r1[0x33E] = len(s.party)
                if not s.party: s.stop = 1; return
            elif c.b[0x1A7]: shops.name_message(game, c, 'Breathes A sigh of relief')  # ov18:1DA6.
            else: game.vm.clear_text()
        elif action == 'icon':
            game.vm.clear_text()  # ov19:3DFC icon editor clears the prior message rectangle.
            dataset = s.dataset; s.dataset = 2  # ov18:2111..2124 selects the icon dataset only inside the editor.
            try: creation.icon(game, s.selc())  # ov18:211C edits SelectedChar directly.
            finally: s.dataset = dataset; s.g.pop('creation.pending', None)
        elif action == 'order':
            selected = False
            while True:  # ov18:1AD8..1BE4: Select/Place toggles; arrows select or move the same member.
                options = ['place' if selected else 'select', 'exit', *shops.ROSTER]
                command = options[game.ask('CAMP_MENU', options, purpose='order', roster=False)]
                if command == 'exit': break
                if command in shops.ROSTER:
                    old = s.sel; new = (old + (-1 if command == 'char-up' else 1)) % len(s.party)
                    if selected: s.party.insert(new, s.party.pop(old))  # ov18:182E/196F relink the selected record.
                    s.sel = new
                else:
                    selected = not selected
                    if selected: shops.name_message(game, s.selc(), 'has been selected', clear=False)  # 1BD2.
                    else: game.vm.clear_text()  # 1BD9 -> ov26:1827.


def run(game):
    """ov18:30DF Encamp/330A clear; interrupted controls host's vecD (ov22:0D25)."""
    s = game.s; mode = s.mode; s.mode = 2; s.g['8DB2'] = 0; s.g['camp.rested'] = 0
    s.g['camp.interrupted'] = 0
    picture = getattr(game.vm, 'display', {})
    game.vm.display = dict(kind='PIC', id=0x3B, dataset=s.dataset)  # ov26:308D..30B4.
    game.vm.clear_text()  # ov18:3122..312E clears the message rectangle before the introduction.
    message(game, 'The party makes camp...')  # ov18:30DF..3154
    for c in s.party: clear_marks(c)
    try:
        while True:
            action = choose(game, 'CAMP_MENU', ['save', 'view', 'magic', 'rest', 'alter', 'fix', 'select', 'exit'])
            if action == 'exit': break
            if action == 'select': shops.pick_member(game)
            elif action == 'save':
                s.r0[0x13C] = (s.r0[0x13C] + 1) % 30  # copy-protection title roots remain CUT (PORT2)
                creation.save_menu(game)  # ov20:2FF7..3013 also permits cancellation.
                if choose(game,'CAMP_MENU',['yes','no'],purpose='quit to DOS',prompt='Quit TO DOS ',roster=False)=='yes':
                    from sm.titles.ssb.vm import Halt
                    raise Halt('Quit to DOS')  # ov18:3227..3250: ask even after cancelled Save, then exit on Yes.
            elif action == 'view': shops.view(game, character=s.selc())  # ov18:316F -> ov21:0D0F
            elif action == 'alter': alter(game)
            elif action == 'rest':
                if rest_menu(game): break
            elif action == 'magic':
                if magic_menu(game): break
            elif action == 'fix':
                if fix(game): break
        return bool(s.g['camp.interrupted'])
    finally:
        for c in s.party: clear_marks(c)
        s.mode = mode
        game.vm.display = picture  # ov18:32B9..32EE restores the caller's picture.
        game.vm.clear_text()  # ov18:330A -> ov26:1827 clears the message window on leaving camp.


def test():
    """V-check ov22:07E1/089C/0B8E/0C3F/0D25; ov18:0023/05C9; exact clocks/RNG."""
    from sm.titles.ssb.state import State, Char
    from sm.titles.ssb.vm import VM
    from types import SimpleNamespace
    test_save_counter()
    test_fix_interrupt()
    s = State(); c = Char(bytes(439)); c.b[0x70] = 30; c.b[0x1B5] = 1; c.b[0x1A7] = 1; s.party = [c]
    game = SimpleNamespace(s=s, engines=True); game.vm = VM(s, lambda *a, **k: 0); game.vm.host = game
    assert not rest(game, 1435) and c.b[0x1B5] == 1
    assert not rest(game, 5) and c.b[0x1B5] == 2 and s.r0[0xCA] == 1
    c.b[0x1E] = 0x83; assert rest_need(c) == 255 and c.b[0x69] == 4
    rest(game, 255); assert c.b[0x1E] == 3 and c.b[0x69] == 0
    c.b[0x1F] = 0x80 | 47; assert rest_need(c) == 405
    s.r1[0x2D2], s.r1[0x2D3] = 1, 100; seed = s.seed
    assert rest(game, 60) and s.seed != seed and c.b[0x1F] > 127
    clear_marks(c); assert c.b[0x1E] == 3 and c.b[0x1F] == 0
    it = bytearray(67); it[0x2E], it[0x2F], it[0x3C] = 0x27, 100, 0x80 | 15; c.items = [it]
    s.r1[0x2D2] = 0; assert rest_need(c) == 255
    rest(game, 255); assert c.b[0x70 + 15] == 1 and c.items == []
    assert s.copy().hash() == s.hash()
    from sm.titles.ssb.units import _c3_test
    _c3_test.check()

def test_save_counter():
    """Encamp ov18:30DF: successful saves cycle [4C3C] through 1..29,0, then 1."""
    from sm.titles.ssb.host import Game
    from unittest.mock import patch
    remaining = 31; seen = []
    def answer(kind, options, game, **info):
        nonlocal remaining
        if kind == 'CREATE_SLOT': return 0
        if info.get('purpose')=='quit to DOS': return options.index('no')  # ov18:3244..3255 resumes Camp.
        action = 'save' if remaining else 'exit'; remaining -= bool(remaining)
        return options.index(action)
    g = Game(answer); g.s.r0[0x13C] = 0
    with patch.object(creation, 'snapshot', side_effect=lambda game, slot: seen.append(game.s.r0[0x13C])):
        run(g)
    assert seen == list(range(1, 30)) + [0, 1], seen

def test_fix_interrupt():
    """FixCommand ov18:2F86: interrupted first rest skips healing/re-memorizing; interrupted second rest skips status cures."""
    from sm.titles.ssb.host import Game
    from sm.titles.ssb.state import Char
    from unittest.mock import patch
    import sys
    for results in ([True], [False, True], [False, False]):
        g = Game(lambda *a, **k: 0); c = Char(bytes(439)); g.s.party = [c]
        c.b[0x70], c.b[0x1B5], c.b[0x1A7], c.b[0x15] = 20, 1, 1, 10
        c.b[0x132] = c.b[0x134] = 1; c.effects = [bytearray([0x22]) + bytearray(8)]
        with patch.object(sys.modules[__name__], 'rest', side_effect=results) as rests:
            assert fix(g) == results[-1]
        assert [call.args[1] for call in rests.call_args_list] == [255, 45][:len(results)]
        assert (c.b[0x1B5] == 1) == results[0], 'first interruption must skip HP healing'
        assert rec.has_effect(c, 0x22) == results[-1], 'second interruption must skip re-memorized cure'
