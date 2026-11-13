from sm.titles.ssb import data as ssb_data
import struct
from sm.titles.ssb import rec; from sm.titles.ssb import save
from sm.titles.ssb.state import Char

COINS = ('copper', 'silver', 'electrum', 'gold', 'platinum', 'gems', 'jewelry')
ASKED = ('Copper', 'silver', 'electrum', 'Gold', 'Platinum', 'Gems', 'Jewelry')
SERVICES = ('cure blindness', 'cure disease', 'cure light wounds', 'cure serious wounds',
            'cure critical wounds', 'heal', 'neutralize poison', 'raise dead', 'remove curse', 'stone to flesh')
DISEASE = (0x1F, 0x22, 0x2B, 0x2C)


def make_treasure_item(s, typ):
    from sm import dax
    d = ssb_data.stexe(); it = bytearray(67); R = lambda n: s.random(n) + 1
    it[0x2E], it[0x35] = typ, 6; special = 0
    if 1 <= typ <= 0x25 or typ in (0x32, 0x46, 0x47, 0x3B):
        r = R(10); it[0x32] = 1 if r <= 6 else 2 if r <= 9 else 3
        bonus = it[0x32]
        if typ == 0x1D: it[0x2F:0x32] = bytes((110+bonus, 0x1C, 0x1D)); it[0x35] = 4
        elif typ == 7:
            if R(5) == 5: special = 0x31
            it[0x30:0x32] = bytes((110+bonus, 7))
        elif typ in (0x0C, 0x1E): it[0x30:0x32] = bytes((110+bonus, typ))
        elif typ == 0x1F: it[0x2F:0x32] = bytes((110+bonus, 0x30, typ)); it[0x35] = 4
        elif 0x20 <= typ <= 0x24: it[0x2F:0x32] = bytes((110+bonus, 0x2F, typ)); it[0x35] = 4
        elif typ == 0x32: it[0x2F:0x33] = bytes((0x6B, 0x5A, 0x32, 4))
        elif typ == 0x3B: it[0x2F:0x34] = bytes((0x6F, 0x31, 0x2E, 1, 1))
        else: it[0x30:0x32] = bytes((110+bonus, typ))
        weights = {1:75, 0x11:75, 6:50, 0x0E:50, 0x0F:50, 0x17:50, 0x19:50, 0x25:50, 0x1D:50,
                   9:125, 8:100, 0x10:100, 0x18:100, 0x46:150, 0x1F:150, 0x47:175, 4:10, 0x32:10,
                   5:5, 0x0A:60, 0x12:60, 0x16:80, 7:20, 0x0D:40, 0x13:35, 0x14:250, 0x20:250,
                   0x21:400, 0x22:300, 0x23:350, 0x24:450, 0x1C:1, 0x3B:1}
        rec.wrw(it, 0x37, weights.get(typ, 4))
        if typ == 5 or typ not in weights: it[0x39] = 20
        multiplier = 50 if typ in (0x0C,5,0x1E) else {0x25:1250,0x20:1500,0x21:1500,0x22:1750,0x23:2000,0x24:2500,0x32:1500}.get(typ,1000)
        rec.wrw(it, 0x3A, it[0x32] * multiplier)
    elif typ in (0x27, 0x28):
        count = R(3); it[0x2F:0x33] = bytes((99+count,0x27,0x28 if typ==0x27 else 0x26,1))
        rec.wrw(it,0x37,25)
        for n in range(count):
            if typ == 0x27:
                level = R(7); it[0x35] = 4
                offset, bound = 0x5851 + 11*level, (10,7,11,10,4,5,3)[level-1]
            else:
                level = R(6); it[0x35] = 0
                offset, bound = 0x5802 + 10*level, (8,7,8,6,6,2)[level-1]
            it[0x3C+n] = d[offset+R(bound)]
            rec.wrw(it,0x3A,rec.rdw(it,0x3A)+150*level)
    elif typ in (0x34,0x35): special = 0x21 if typ==0x34 else 9
    elif typ == 0x2F: special = (1,0x11,0x19,0x29)[(R(8)-1)//2]
    if special:
        word = lambda n: rec.rdw(d,0xA28+2*(special+n))
        it[0x2F:0x32] = bytes(word(n)&255 for n in range(3)); it[0x32:0x34] = bytes((1,0))
        rec.wrw(it,0x37,word(3)); it[0x39] = 0; rec.wrw(it,0x3A,word(4))
        it[0x3C:0x3F] = bytes(word(n)&255 for n in range(5,8))
    return it


def message(game, text, *, bottom=False, actor=None, delay=None, display_text=None, spell=None, names=(), status=False, continuation=False, display=True, merge=False, blank=True, after=None):
    vm = getattr(game, 'vm', None)
    if vm is not None:
        vm.out.append('\n' + text + '\n')
        vm.service_bottom = (len(vm.out), getattr(vm, 'text_epoch', 0), text, after) if bottom else None
    if display and getattr(game, 'presentation', None) is not None:
        shown=text if display_text is None else display_text
        if continuation and game.presentation_text:
            from textwrap import wrap
            row=int(blank)+sum(len(wrap(p,16)) or 1 for p in game.presentation_text.splitlines())
            names=tuple(getattr(game,'presentation_names',()))+tuple((n[0]+row,*n[1:]) for n in names)
            shown=game.presentation_text+('\n\n' if blank else '\n')+shown
        game.present('message', actor=actor, delay=game.s.g.get('67D6', 0) / 10 if delay is None else delay,
                     text=shown, spell=spell, names=names, status=status, **({'merge': True} if merge else {}))


def item_name(item, party=()):
    from sm.titles.ssb.ui.screen import item_name as build_name
    return build_name(item, party)


ROSTER = ('char-up', 'char-down')
def choose(game, kind, options, **info):
    party = game.s.party
    if kind in ('SHOP_MENU', 'CAMP_MENU') and len(party) > 1 and info.get('roster', True):
        while True:
            k = (options + list(ROSTER))[game.ask(kind, options + list(ROSTER), **info)]
            if k not in ROSTER: return k
            game.s.sel = (min(game.s.sel, len(party) - 1) + (-1 if k == 'char-up' else 1)) % len(party)
    return options[game.ask(kind, options, **info)]


def name(c):
    return bytes(c.b[1:1 + min(c.b[0], 15)]).decode('latin1')


def name_message(game, c, text, *, clear=True):
    vm = game.vm; colour = 12 if not c.b[0x1A7] else 14 if c.b[0x1A8] else 11
    message(game, name(c) + ' ' + text, display=False)
    vm.clear_text()
    notice = (len(vm.out), name(c), text, colour, clear, 18 if game.s.g.get('8DB4') else 17, vm.text_epoch)
    queue = getattr(vm, 'service_names', [])
    if queue and not queue[-1][4]: queue.pop()
    queue.append(notice); vm.service_names = queue; vm.service_name = notice


def pick_member(game):
    opts = list(range(len(game.s.party))) + [None]
    i = choose(game, 'TARGET', opts, purpose='party member', names=[name(c) for c in game.s.party])
    if i is not None: game.s.sel = i; return game.s.party[i]


def coins(c):
    return [rec.rdw(c.b, 0x103 + 2 * k) for k in range(7)]


def put_coins(c, values):
    for k, v in enumerate(values): rec.wrw(c.b, 0x103 + 2 * k, v)
    recalc(c)


def total(values):
    value = sum(n * rate for n, rate in zip(values, (1, 10, 100, 200, 1000))) & 0xFFFFFFFF
    if value >= 0x80000000: value -= 0x100000000
    return value // 200 if value >= 0 else -(-value // 200)


def set_money(c, gp):
    gp &= 65535
    for k, v in enumerate((0, 0, 0, gp % 5, gp // 5)): rec.wrw(c.b, 0x103 + 2 * k, v)


def set_pool(s, gp):
    gp &= 65535
    s.treasure_money[:5] = [0, 0, 0, gp % 5, gp // 5]


def groups(items):
    i = 0
    while i < len(items):
        n = 1 + (items[i][0x39] if items[i][0x2E] == 0x49 else 0)
        if i + n > len(items): raise ValueError('truncated scroll bundle')
        yield i, items[i:i + n]
        i += n


def recalc(c):
    original = c.items
    c.items = [g[0] for _, g in groups(original)]
    try: rec.recalc_character(c)
    finally: c.items = original


def room(c):
    recalc(c)
    return max(0, rec.carry(c) + 1500 - rec.rdw(c.b, 0x19B))


def can_carry(c, item):
    return room(c) >= rec.rdw(item, 0x37) * max(1, item[0x39]) and c.b[0x160] <= 15


def give(c, group):
    if not can_carry(c, group[0]): return False
    copied = [bytearray(it) for it in group]
    for it in copied: it[0x2A:0x2E] = bytes(4)
    c.items.extend(copied); recalc(c)
    return True


def price(item, multiplier=16):
    v = rec.rdw(item, 0x3A)
    if not v: v = 1; rec.wrw(item, 0x3A, v)
    return v * multiplier // 16 if multiplier in (1, 2, 4, 8, 16, 32, 64, 128) else v


def buy(game, c, stock):
    cost = price(stock[0], game.s.r1[0x36D]); own = total(coins(c)); pool = total(game.s.treasure_money)
    if own < cost and pool < cost:
        message(game, 'Not enough Money.', bottom=True); return False
    if not give(c, stock):
        message(game, 'OverLoaded', bottom=True); return False
    if own >= cost: set_money(c, own - cost)
    else: set_pool(game.s, pool - cost)
    message(game, name(c) + (' buys ' if stock[0][0x39] else ' buys a ') + item_name(stock[0], game.s.party), bottom=True)
    return True


def pool_money(s):
    for c in s.party:
        if c.b[0xFF] not in (0, 0xB3): continue
        for k, n in enumerate(coins(c)): s.treasure_money[k] += n
        put_coins(c, [0] * 7)
    s.g['8D9A'] = 1


def take_coins(s, c, k, n):
    v = coins(c); n = max(0, min(n, s.treasure_money[k], room(c), 65535 - v[k]))
    s.treasure_money[k] -= n; v[k] += n; put_coins(c, v)
    return n


def share(s):
    n = sum(c.b[0xFF] in (0, 0xB3) for c in s.party)
    if not n: return
    q, r = zip(*(divmod(m, n) if m > 0 else (0, 0) for m in s.treasure_money)); r = list(r)
    def add(c, k, amount):
        rec.wrw(c.b, 0x103 + 2 * k, (coins(c)[k] + amount) & 0xFFFF)
        rec.wrw(c.b, 0x19B, (rec.rdw(c.b, 0x19B) + amount) & 0xFFFF)
    cap = lambda c: rec.carry(c) + 1500
    for c in s.party:
        if c.b[0xFF] >= 0x80: continue
        for k in range(6, -1, -1):
            wt = rec.rdw(c.b, 0x19B)
            if wt + q[k] > cap(c):
                fits = max(0, cap(c) - wt); add(c, k, fits); r[k] += q[k] - fits
            else:
                add(c, k, q[k])
                if r[k] and wt + q[k] + 1 <= cap(c): add(c, k, 1); r[k] -= 1
    for k in range(6, -1, -1):
        for c in s.party:
            room = (cap(c) - rec.rdw(c.b, 0x19B)) & 0xFFFF
            if room and r[k]:
                fits = min(room, r[k]); add(c, k, fits); r[k] -= fits
    s.treasure_money[:] = r
    s.g['8D9A'] = int(any(r))


def deposit(s, c, k, n):
    v = coins(c); n = max(0, min(n, v[k])); v[k] -= n; s.treasure_money[k] += n; put_coins(c, v)
    return n


def add_gold(s, c, gp):
    for k, n in ((4, gp // 5), (3, gp % 5)):
        v = coins(c); fits = min(n, room(c), 65535 - v[k]); v[k] += fits
        s.treasure_money[k] += n - fits; put_coins(c, v)


def sell(game, c, index):
    group = next(g for i, g in groups(c.items) if i == index); it = group[0]
    if it[0x34] and it[0x36]: return False
    amount = rec.rdw(it, 0x3A) // 2
    if it[0x39] > 1 and it[0x2E] != 0x49:
        amount = (amount * it[0x39] & 65535) // (20 if it[0x2E] in (0x0C, 0x1E) else 1)
    label = item_name(it, game.s.party)
    if amount:
        offer = "I'll give you %d gold pieces for your %s" % (amount, label)
        question = 'Will you sell %s? ' % ('it' if it[0x39] < 2 or it[0x2E] == 0x49 else 'them')
    else:
        offer = 'Your %s %s' % (label, 'is worthless to me.' if it[0x39] < 2 else 'are worthless.')
        question = 'Shall I dispose of it for you? ' if it[0x39] < 2 else 'Would you like to discard them? '
    message(game, offer)
    if choose(game, 'SHOP_MENU', ['cancel', 'sell'], purpose='confirm sale', price=amount,
              prompt=question, offer=offer, actor=game.s.party.index(c), roster=False) != 'sell': return False
    result = 'Sold!' if amount else 'I will give it to one of my sons.' if it[0x39] < 2 else "Very well.  I'll take them."
    message(game, result, bottom=True)
    pooled = tuple(game.s.treasure_money)
    del c.items[index:index + len(group)]; recalc(c); add_gold(game.s, c, amount)
    if tuple(game.s.treasure_money) != pooled: message(game, 'Overloaded.  Money will be put in pool.', bottom=True, after=result)
    return True


def identify(game, c, it):
    if it[0x2E] == 0x49:
        message(game, 'Fool! You must remove them from the bundle first!'); return False
    offer="For 100 gold pieces I'll identify your " + item_name(it, game.s.party); message(game,offer)
    if choose(game, 'SHOP_MENU', ['identify', 'cancel'], purpose='confirm identification', prompt='Is It a Deal? ', offer=offer, roster=False) != 'identify': return False
    own, pooled = total(coins(c)), total(game.s.treasure_money)
    if own >= 100: set_money(c, own - 100)
    elif pooled >= 100: set_pool(game.s, pooled - 100)
    else:
        message(game, 'Not Enough Money'); return False
    changed = bool(it[0x35] & 7); it[0x35] &= 0xF8
    message(game, ('It looks like some sort of ' if changed else "I can't tell anything new about your ") + item_name(it, game.s.party))
    return changed


def ready(game, c, it, *, recalculate=True):
    from sm.titles.ssb.units import magic
    from sm import dax
    if recalculate: recalc(c)
    unready = bool(it[0x34]); table = ssb_data.items_table(); row = table[it[0x2E] * 16:it[0x2E] * 16 + 16]
    if unready:
        if it[0x36]:
            message(game, "It's Cursed!", bottom=True); return False
    else:
        occupied = rec.readied(c); slot = row[0]; refusal = None
        if row[1] + c.b[0x199] > 2: refusal = 'Your hands are full!'
        if slot <= 8 and occupied[slot] is not None: refusal = 'already using ' + item_name(occupied[slot], (c,))
        if slot == 9 and occupied[10] is not None: refusal = 'already using ' + item_name(occupied[9], (c,))
        if it[0x2E] == 0x1E and occupied[11] is not None: refusal = 'already using ' + item_name(occupied[11], (c,))
        if it[0x2E] == 0x0C and occupied[12] is not None: refusal = 'already using ' + item_name(occupied[12], (c,))
        if not row[13] & c.b[0x130]: refusal = 'Wrong Class'
        if refusal:
            if refusal != 'Your hands are full!' or not (game.s.g.get('combat.active') and c.b[0x1A9]): message(game, refusal, bottom=True)
            return False
    it[0x34] = 0 if unready else 1
    if it[0x3E] > 127:
        power = it[0x3E] & 127
        if power == 1:
            if unready:
                level = c.b[0x116] + c.b[0x11D] * rec.dual(c)
                c.b[0x14B] = sum(ssb_data.stexe()[0x544D + 7 * k] for k in range(9, level + 1)) & 255
                remaining = c.b[0x14B]
                for o in range(0x1E, 0x69):
                    sid = c.b[o] & 127
                    if sid and magic.spell(sid)[:2] == bytes((3, 5)):
                        if remaining: remaining -= 1
                        else: c.b[o] = 0
            else: c.b[0x14B] = c.b[0x14B] * 2 & 255
        elif power in (3, 5): magic.recalc_ability(game, c, 0)
        elif power == 9 and unready: magic.remove_effect(game, c, 0x17)
        elif power == 0:
            game.s.g['8DB8'] = 1
            magic.effect_callback(game, c, it, int(unready))
    if recalculate: recalc(c)
    return True


def halve(c, index):
    group = next(g for i, g in groups(c.items) if i == index); it = group[0]; half = it[0x39] // 2
    if not half: return False
    if it[0x2E] != 0x49:
        other = bytearray(it); other[0x39] = half; other[0x34] = 0; other[0x2A:0x2E] = bytes(4)
        it[0x39] -= half; c.items.insert(index + 1, other)
    else:
        def bundle(children, readied):
            if len(children) == 1:
                child = bytearray(children[0]); child[0x3F:0x43] = bytes(4); child[0x34] = readied; return [child]
            head = bytearray(it); head[0x39] = head[0x30] = len(children); head[0x34] = readied
            rec.wrw(head, 0x37, len(children)); rec.wrw(head, 0x3A, sum(rec.rdw(n, 0x3A) for n in children))
            return [head] + children
        c.items[index:index + len(group)] = bundle(group[1 + half:], it[0x34]) + bundle(group[1:1 + half], 0)
    recalc(c); return True


def use_item(game, c, index):
    from sm.titles.ssb.units import magic, camp
    group = next(g for i, g in groups(c.items) if i == index); it = group[0]
    if not it[0x34]:
        message(game, 'Must be Readied', bottom=True); return False
    def spent(sid):
        if game.s.g.get('combat.active') or magic.spell(sid)[7]: return magic.cast(game, c, sid, consume=False)
        return choose(game, 'SHOP_MENU', ['cancel', 'use'], purpose='use refusal', prompt='Use it? ', roster=False,
                      text='is only useful on locked doors.' if sid == 31 else 'is a combat-only item...') == 'use'
    if it[0x2E] in (0x27, 0x28, 0x49):
        choices = magic.scroll_spells(c, range(index, index + len(group)), bool(game.s.g.get('combat.active')))
        if not choices: return False
        selected = choose(game, 'SPELL', choices + [None], purpose='use scroll')
        if selected is None: return False
        idx, offset, sid = selected
        can_read = c.b[0x111] or c.b[0x116] or c.b[0x6B] == 6 and (c.b[0x118] or c.b[0x11D])
        if not can_read and (c.b[0x117] < 10 or game.s.random(100) + 1 > 75):
            if not game.s.g.get('combat.active'): name_message(game, c, 'oops!')
            return False
        if not spent(sid): return False
        camp.consume_scroll(c, idx, offset)
    else:
        if it[0x3E] >= 128 or not 1 <= it[0x3D] <= 117: return False
        if not game.s.g.get('combat.active'): name_message(game, c, 'uses an item', clear=False)
        if not spent(it[0x3D]): return False
        if it[0x3C]:
            if it[0x39] > 1: it[0x39] -= 1
            else:
                it[0x3C] -= 1
                if not it[0x3C]: del c.items[index:index + len(group)]
    recalc(c); return True


def appraise(game, c):
    s = game.s
    if not any(coins(c)[5:]):
        message(game, 'No Gems or Jewelry', bottom=True); return
    while True:
        collection = coins(c)[5:]
        if not any(collection): return
        opts = [COINS[k] for k in (5, 6) if coins(c)[k]] + [None]
        chosen = choose(game, 'SHOP_MENU', opts, purpose='appraise', gems=collection[0], jewelry=collection[1], character=name(c), roster=False)
        if chosen is None: return
        k = COINS.index(chosen)
        rec.wrw(c.b, 0x103 + 2 * k, coins(c)[k] - 1); r = s.random(100) + 1
        if k == 5:
            value = next(v for lim, v in ((25, 5), (50, 25), (70, 50), (90, 250), (99, 500), (100, 2500)) if r <= lim)
        else:
            width, base = next((w, b) for lim, w, b in ((10, 450, 50), (20, 500, 100), (40, 750, 150),
                (50, 1250, 250), (70, 2500, 500), (90, 3000, 1000), (100, 5000, 1000)) if r <= lim)
            value = s.random(width) + base
        it = bytearray(67); it[0x2E] = 0x2F; it[0x31] = 0x7A if k == 5 else 0x7B
        rec.wrw(it, 0x37, 1); rec.wrw(it, 0x3A, value)
        fits = rec.rdw(c.b, 0x19B) + 1 <= (rec.carry(c) + 1500) & 65535
        opts = ['sell'] + (['keep'] if fits and c.b[0x160] < 16 else [])
        if choose(game, 'SHOP_MENU', opts, purpose='appraisal', value=value, valuable='Gem' if k == 5 else 'Jewel',
                  gems=collection[0], jewelry=collection[1], character=name(c), roster=False) == 'keep': give(c, [it])
        else:
            pooled = tuple(s.treasure_money)
            add_gold(s, c, value // 5 * 5)
            if tuple(s.treasure_money) != pooled: message(game, 'Overloaded.  Money will be put in Pool.', bottom=True)
        recalc(c)


def coin_menu(game, c, depositing=False):
    s = game.s
    while True:
        values = coins(c) if depositing else s.treasure_money
        k = choose(game, 'LIST', [k for k, v in enumerate(values) if v > 0] + [None],
                   purpose='deposit money' if depositing else 'take money', coin_names=COINS, actor=s.chars().index(c))
        if k is None: return
        verb = 'deposit' if depositing and s.mode == 8 else 'drop' if depositing else 'take'
        prompt = ('How Many ' if k == 5 and not depositing else 'How much ') + ASKED[k] + ('' if depositing else ' ') + ' will you ' + verb + '? '
        n = game.ask('NUMBER', None, min=0, max=values[k], purpose='coin amount', prompt=prompt, number_prompt=True,
                     money_picker='deposit' if depositing else 'take')
        if not isinstance(n, int) or not 0 <= n <= values[k]: raise ValueError('coin amount outside legal bounds')
        if not depositing and n > room(c):
            message(game, 'Overloaded', bottom=True)
        else:
            if depositing and s.mode not in (1, 6, 8):
                purse = coins(c); purse[k] -= n; put_coins(c, purse)
            else: (deposit if depositing else take_coins)(s, c, k, n)
        s.g['8D9A'] = int(any(s.treasure_money))
        if not any(coins(c) if depositing else s.treasure_money): return


def join_items(game, c, index):
    grouped = [group for _, group in groups(c.items)]
    target = c.items[index]
    own = next(group for group in grouped if group[0] is target)
    if target[0x2E] in (0x27, 0x28, 0x49):
        if target[0x39] >= 10:
            message(game, 'Bundles are limited to 10 scrolls.', bottom=True); return
        candidates = [group for group in grouped if group is not own and (
            group[0][0x2E] in (0x27, 0x28) or group[0][0x2E] == 0x49 and group[0][0x39] < 10)]
        if not candidates:
            message(game, 'There are no similar items to join with.', bottom=True); return
        if target[0x2E] != 0x49:
            child = bytearray(target); child[0x3F:0x43] = bytes(4); own.append(child)
            target[0x2E:0x32] = bytes((0x49, 0x27, 1, 0x4D))
            target[0x34] = target[0x35] = 0; target[0x39] = 1; target[0x3C:0x3F] = bytes(3)
        for group in candidates:
            children = group[1:] if group[0][0x2E] == 0x49 else group
            if target[0x39] + len(children) > 10: continue
            own.extend(children); target[0x39] += len(children)
            target[0x30] = target[0x39]; rec.wrw(target, 0x37, target[0x39])
            rec.wrw(target, 0x3A, (rec.rdw(target, 0x3A) + rec.rdw(group[0], 0x3A)) & 65535)
            grouped = [g for g in grouped if g is not group]
    elif not target[0x39]:
        message(game, 'That cannot be joined with other items.', bottom=True); return
    else:
        total = target[0x39]
        for group in grouped[:]:
            other = group[0]
            if other is target or other[0x3C] >= 2 or any(other[o] != target[o] for o in (0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x36)):
                continue
            if total + other[0x39] <= 255:
                total += other[0x39]; grouped = [g for g in grouped if g is not group]
            else:
                target[0x39] = 255; total += other[0x39] - 255; target = other
        target[0x39] = total
    c.items = [node for group in grouped for node in group]; recalc(c)


def item_actions(game, c, place):
    opts = ['ready', 'use', 'trade', 'halve', 'deposit' if place == 'vault' else 'drop', 'exit'] + (['sell', 'identify'] if place in ('shop', 'temple') else [])
    opts.append('join')
    mode = 1 if place in ('shop', 'temple') else 8 if place == 'vault' else game.s.mode
    can_trade = (c.b[0xFF] < 128 or not c.b[0x1A7]) and mode != 5
    can_use = c.b[0x1A7] and not game.s.r0[0xE5] and (mode in (2, 4) or mode == 5 and
        game.s.g.get('combat.records', [])[game.s.chars().index(c)][2])
    available = [v for v in opts if not (v == 'use' and not can_use or v in ('trade', 'sell') and not can_trade
                 or v == 'halve' and sum(1 for _ in groups(c.items)) >= 16)]
    return opts, available


def item_menu(game, c, place, target_cursor=None):
    if target_cursor is None: target_cursor=[game.s.chars().index(c)]
    while True:
        index = choose(game, 'LIST', [i for i, _ in groups(c.items)] + [None], purpose='items', actor=game.s.chars().index(c), place=place)
        if index is None: return
        it = c.items[index]; opts, available = item_actions(game, c, place)
        action = choose(game, 'SHOP_MENU', opts, purpose='item', place=place, available=available, roster=False)
        if action == 'ready': ready(game, c, it)
        elif action == 'use': use_item(game, c, index)
        elif action == 'halve':
            if not it[0x39] // 2: message(game, "Can't halve that", bottom=True)
            else: halve(c, index)
        elif action == 'join': join_items(game, c, index)
        elif action in ('trade', 'drop', 'sell', 'deposit') and it[0x34]:
            message(game, 'Must be unreadied', bottom=True)
        elif action in ('trade', 'drop', 'sell', 'deposit') and it[0x2E] in (0x27, 0x28) and any(v > 127 for v in it[0x3C:0x3F]) and choose(
                game, 'SHOP_MENU', ['cancel', 'lose'], purpose='lose scribe scroll', prompt='is it Okay to lose it? ', name=name(c),
                offer=name(c) + ' was going to scribe from that scroll', roster=False) != 'lose': pass
        elif action in ('trade', 'drop'):
            group = next(g for i, g in groups(c.items) if i == index)
            if action == 'trade':
                game.vm.clear_text(); giver=game.s.party.index(c)
                dest = choose(game,'TARGET',[i for i,p in enumerate(game.s.party) if p is not c]+[None,giver],
                              purpose='party member',action='trade item',prompt='Trade with Whom?',recipient=target_cursor[0])
                if dest is None: continue
                target_cursor[0]=dest
                if not give(game.s.party[dest],group): message(game,'Overloaded',bottom=True); continue
            elif choose(game, 'SHOP_MENU', ['cancel', 'drop'], purpose='drop item', prompt='Drop It? ',
                        item_name=item_name(it, (c,)), actor=game.s.chars().index(c)) != 'drop': continue
            del c.items[index:index + len(group)]; recalc(c)
        elif action == 'sell': sell(game, c, index)
        elif action == 'identify': identify(game, c, it)
        elif action == 'deposit':
            group = next(g for i, g in groups(c.items) if i == index)
            game.vm.service_window = (getattr(game.vm, 'service_window', (0,))[0] + 1, 'Your ' + item_name(it, game.s.party) + ' will be left in the vault')
            game.s.treasure_items.extend(bytearray(n) for n in group); del c.items[index:index + len(group)]; recalc(c)


def paladin_actions(game, c):
    if game.s.mode == 5 or c.b[0x1A6] or not (c.b[0x6C] == 3 or rec.sx(c.b[0x11B]) > 0 and rec.dual(c)):
        return []
    return ([] if rec.has_effect(c, 0x6D) else ['heal']) + (['cure'] if c.b[0x6D] else [])


def view_notice(game, c, text):
    message(game, text, bottom=True)


def paladin_power(game, c, action):
    from sm.titles.ssb.units import magic
    ids = list(range(len(game.s.party))) + [None]
    index = choose(game, 'TARGET', ids, purpose='party member', prompt='Heal whom?' if action == 'heal' else 'Cure whom?')
    if index is None: return
    target = game.s.party[index]
    if action == 'heal':
        amount = 2 * (c.b[0x114] + c.b[0x11B] * rec.dual(c))
        result = name(target) + (' feels better' if magic.heal(game, target, amount) else ' is unaffected')
        magic.add_effect(game, c, 0x6D, 0x5A0)
    else:
        diseased = any(rec.has_effect(target, t) for t in DISEASE)
        if not diseased:
            combat = bool(game.s.g.get('combat.active'))
            if not combat: name_message(game, target, 'is not diseased', clear=False)
            prompt = name(target) + ' is not diseased; cure anyway:' if combat else 'cure anyway: '
            answer = choose(game, 'MENU', ['yes', 'no'], purpose='cure healthy', prompt=prompt)
            if not combat: game.vm.clear_text()
            if answer == 'no': return
        game.s.g['87DC'] = 1
        for typ in DISEASE: magic.remove_effect(game, target, typ)
        game.s.g['87DC'] = 0
        c.b[0x6D] = max(0, c.b[0x6D] - 1)
        if not rec.has_effect(c, 0x6E): magic.add_effect(game, c, 0x6E, 0x2760, call_on_remove=True)
        result = name(target) + ' is cured' if diseased else name(c) + ' cures the healthy'
    view_notice(game, c, result)


def trade_money(game, c, target_cursor=None):
    if target_cursor is None: target_cursor=[game.s.party.index(c)]
    index = choose(game, 'TARGET', list(range(len(game.s.party))) + [None], purpose='party member', prompt='Trade to?',recipient=target_cursor[0])
    if index is None: return
    target_cursor[0]=index
    target = game.s.party[index]
    while any(coins(c)):
        k = choose(game, 'LIST', [i for i, n in enumerate(coins(c)) if n] + [None], purpose='trade money')
        if k is None: return
        n = game.ask('NUMBER', None, min=0, max=coins(c)[k], number_prompt=True,
                     prompt='How much %s will you trade? ' % ASKED[k])
        if not isinstance(n, int) or not 0 <= n <= coins(c)[k]: raise ValueError('trade amount outside legal bounds')
        if n > room(target):
            view_notice(game, c, 'Overloaded'); continue
        purse = coins(c); purse[k] -= n; put_coins(c, purse)
        purse = coins(target); purse[k] = (purse[k] + n) & 65535; put_coins(target, purse)


def view(game, place='camp', character=None):
    c = character if character is not None else pick_member(game)
    if c is None: return
    target_cursor=[game.s.chars().index(c)]
    while True:
        game.vm.clear_text()
        recalc(c); rec.compute_move(c, game.s.r1[0x372])
        spells = sorted({sid & 127 for sid in c.b[0x1E:0x69] if 1 <= sid & 127 <= 117})
        options = ['items', 'deposit money', 'exit'] if place in ('shop', 'temple', 'vault') else ['items', 'exit']
        if spells: options.append('spells')
        if any(coins(c)):
            if game.s.mode != 5 and (c.b[0xFF] < 128 or not c.b[0x1A7]): options.append('trade')
            if 'deposit money' not in options: options.append('drop money')
        options += paladin_actions(game, c)
        available = [action for action in options if not (action == 'items' and not c.items)
                     and not (action == 'deposit money' and not any(coins(c)))]
        action = choose(game, 'SHOP_MENU' if place != 'camp' else 'CAMP_MENU',
                        options,
                        purpose='view', character=name(c), record=bytes(c.b).hex(), roster=False, place=place,
                        available=available,available_text='|'.join(available))
        if action == 'exit': return
        if action == 'items': item_menu(game, c, place,target_cursor)
        elif action in ('deposit money', 'drop money'): coin_menu(game, c, True)
        elif action == 'trade': trade_money(game, c,target_cursor)
        elif action in ('heal', 'cure'): paladin_power(game, c, action)
        elif action == 'spells':
            choose(game, 'SPELL', spells + ['exit'], purpose='view spells', caster=game.s.chars().index(c))


def take_items(game, c):
    while game.s.treasure_items:
        index = choose(game, 'LIST', [i for i, _ in groups(game.s.treasure_items)] + [None], purpose='take item')
        if index is None: return
        group = next(g for i, g in groups(game.s.treasure_items) if i == index)
        if not give(c, group):
            message(game, 'OverLoaded', bottom=True); continue
        del game.s.treasure_items[index:index + len(group)]


def take(game):
    s = game.s
    while s.treasure_items or any(s.treasure_money):
        c = s.selc() or s.party[0]
        has_c, has_i = any(s.treasure_money), bool(s.treasure_items)
        if not has_c: take_items(game, c); return
        if not has_i: coin_menu(game, c); return
        k = choose(game, 'SHOP_MENU', ['money', 'items', 'exit'], purpose='take')
        if k == 'exit': return
        c = s.selc() or s.party[0]
        (coin_menu if k == 'money' else take_items)(game, c)
        game.vm.clear_text()
        if not (any(s.treasure_money) if k == 'money' else s.treasure_items): return


def treasure(game):
    s = game.s
    while True:
        c = s.selc(); has_coins, has_items = any(s.treasure_money), bool(s.treasure_items)
        detect = next((spell for spell in c.b[0x1E:0x69] if spell in (5, 11, 77)), None) if c and c.b[0x1A7] and has_items else None
        options = ['view'] + (['take'] if has_coins or has_items else []) + ['pool']
        if has_coins: options.append('share')
        if detect: options.append('detect')
        options.append('exit'); game.vm.clear_text()
        action = choose(game, 'SHOP_MENU', options, purpose='treasure', place='treasure')
        if action == 'view': view(game, 'treasure', s.selc())
        elif action == 'take': take(game)
        elif action == 'pool': pool_money(s)
        elif action == 'share': share(s)
        elif action == 'detect':
            from sm.titles.ssb.units import magic
            magic.cast(game, s.selc(), detect)
        elif action == 'exit':
            if not (s.treasure_items or any(s.treasure_money)): return
            if choose(game, 'SHOP_MENU', ['yes', 'no'], purpose='treasure leave', place='treasure', roster=False) == 'no': return


def cure(game, c, service, *, result_text=None):
    from sm.titles.ssb.units import magic
    b = c.b
    def result(text, success=True):
        name_message(game, c, text if result_text is None else result_text)
        return success
    def remove(*types, temple=False):
        if temple: game.s.g['87DC'] = 1
        try:
            for t in types: magic.remove_effect(game, c, t)
        finally:
            if temple: game.s.g['87DC'] = 0
    if service == 0:
        if not rec.has_effect(c, 0x21): return result('is not blind')
        remove(0x21); return result('can see!')
    elif service == 1:
        if not any(rec.has_effect(c, t) for t in DISEASE): return result('is not Diseased', False)
        remove(*DISEASE, temple=True); magic.recalc_ability(game, c, 0)
        return result('is cured')
    elif service in (2, 3, 4, 5):
        full = b[0x1B5] == b[0x70]; amount = 0
        if b[0x1A6] in (6, 7, 8):
            text = {6: 'must be raised from dead', 7: 'can only be healed by a stonemason', 8: 'is not here'}[b[0x1A6]]
            return result('has no need of healing' if full else text, False)
        text = 'has no need of healing' if full else 'is healed'
        if not full:
            if service == 5: amount = b[0x70] - b[0x1B5] - (game.s.random(4) + 1)
            else: amount = sum(game.s.random(8) + 1 for _ in range(service - 1)) + (0, 1, 3)[service - 2]
        if service == 5:
            cured = any(rec.has_effect(c, t) for t in (0x21, 0x44, *DISEASE))
            remove(0x21, 0x44, *DISEASE)
            if cured:
                result('is cured')
                if not full: text = 'is fully healed'
            magic.recalc_ability(game, c, 1); magic.recalc_ability(game, c, 2)
        if not full: magic.heal(game, c, amount & 255)
        return result(text)
    elif service == 6:
        if not rec.has_effect(c, 0x37): return result('is not poisoned', False)
        if b[0x1B5] == 0: b[0x1B5] = 1
        remove(0x37, 0x16, 0x0F, temple=True); b[0x1A6], b[0x1A7] = 0, 1
        return result('is no longer poisoned')
    elif service == 7:
        if b[0x1A6] != 6: return result('is not dead yet', False)
        if b[0x6B] == 1: return result('cannot be raised', False)
        remove(0x37, temple=True); b[0x1B5], b[0x1A6], b[0x1A7] = 1, 0, 1
        b[0x19] = max(0, b[0x19] - 1); con = b[0x19]; d = max(0, b[0x70] - b[0x131])
        if con >= 14:
            w = sum(lv * (con - 14 if i in (2, 3, 4) else 2 if con > 15 else 1)
                    for i, lv in enumerate(b[0x111:0x119]) if 0 < rec.sx(lv)) & 255
            if w > 0: d //= w
            if con < 17 or rec.sx(b[0x113]) > 0 or rec.sx(b[0x113]) > rec.sx(b[0xEF]): b[0x70] = (b[0x70] - d) & 255
            recalc(c)
        return result('is ressurected')
    elif service == 8:
        if not any(it[0x36] for it in c.items) and not rec.has_effect(c, 0x24): return result('is not cursed')
        magic.remove_curse(game, c)
        return result('rejoices.  The curse has been lifted!')
    elif service == 9:
        if b[0x1A6] != 7: return result('is not petrified', False)
        b[0x1A6], b[0x1A7], b[0x1B5] = 0, 1, 1
        return result('is turned to flesh')
    else: raise ValueError('unknown temple service')
    return True


def service_menu(game, place):
    s = game.s; s.mode = 1; s.treasure_money = [0] * 7; s.g['8D9A'] = 0
    while True:
        if not s.party: return
        c = s.selc() or s.party[0]
        opts = ['buy' if place == 'shop' else 'heal', 'view', 'pool', 'appraise', 'select', 'exit']
        if any(s.treasure_money): opts[2:2] = ['take', 'share']
        action = choose(game, 'SHOP_MENU', opts, place=place)
        c = s.selc() or s.party[0]
        if action == 'exit':
            if any(s.treasure_money):
                warning = ('As you leave a priest says, "Excuse me but you have left some money here" ' if place == 'temple' else
                           'As you Leave the Shopkeeper says, "Excuse me but you have Left Some Money here."  ')
                message(game,warning)
                question = 'Do you want to go back and retrieve your money?' if place == 'temple' else 'Do you want to go back and get your Money?'
                if choose(game,'SHOP_MENU',['retrieve','leave'],purpose='money left behind',prompt=question,warning=warning,place=place,roster=False)=='retrieve':
                    game.vm.clear_text(); continue
            return
        if action == 'select': pick_member(game)
        elif action == 'view': view(game, place, character=c)
        elif action == 'pool': pool_money(s)
        elif action == 'share': share(s)
        elif action == 'take': coin_menu(game, c)
        elif action == 'appraise': appraise(game, c)
        elif action == 'heal':
            while True:
                service = choose(game, 'LIST', list(range(10)) + [None], purpose='temple service', services=SERVICES,
                                 prompt=name(c) + ', how can we help you?')
                if service is None: break
                cure(game, c, service)
        elif action == 'buy':
            game.vm.clear_text()
            while True:
                stock = list(groups(s.treasure_items))
                for _, group in stock: price(group[0], s.r1[0x36D])
                index = choose(game, 'LIST', [i for i, _ in stock] + [None], purpose='buy',
                               prices=[price(g[0], s.r1[0x36D]) for _, g in stock])
                game.vm.clear_text()
                if index is None: break
                buy(game, c, next(g for i, g in stock if i == index))


def shop(game):
    service_menu(game, 'shop')


def temple(game):
    service_menu(game, 'temple')


def vault_data(s, directory=None, slot='A'):
    if 'vault.image' not in s.g:
        v = save.load(directory,slot)['vault'] or {'header': bytes(28), 'items': []}
        s.g['vault.image'] = v['header'] + b''.join(bytes(i) for i in v['items'])
    image = s.g['vault.image']
    if len(image) < 28 or (len(image) - 28) % 67: raise ValueError('invalid vault image')
    return list(struct.unpack('<7i', image[:28])), [bytearray(image[i:i + 67]) for i in range(28, len(image), 67)]


def vault(game):
    s = game.s; s.mode = 8; s.treasure_money, s.treasure_items = vault_data(s,getattr(game,'directory',None),getattr(game,'slot','A')); s.g['8D9A'] = 0
    game.vm.clear_text()
    while True:
        opts = ['view', 'pool', 'select', 'exit']
        if any(s.treasure_money) or s.treasure_items: opts.insert(1, 'take')
        action = choose(game, 'SHOP_MENU', opts, place='vault')
        if action == 'exit': break
        if action == 'view': view(game, 'vault', character=s.selc())
        elif action == 'pool': pool_money(s)
        elif action == 'select': pick_member(game)
        elif action == 'take' and s.party:
            take(game)
    s.g['vault.image'] = struct.pack('<7i', *s.treasure_money) + b''.join(bytes(i) for i in s.treasure_items)
    s.treasure_items = []


def test_take():
    from types import SimpleNamespace
    from sm.titles.ssb.state import State, Char
    st = State(); st.party = [Char(bytes(439))]; it = bytearray(67); it[0x2E] = 5; st.treasure_items = [it]
    answers = iter([0, 0])
    g = SimpleNamespace(s=st, ask=lambda kind, options, **i: next(answers))
    take(g); assert not st.treasure_items and len(st.party[0].items) == 1
    st.treasure_money = [0, 7, 0, 0, 0, 0, 0]; seen = []; answers = iter([0, 7])
    g.ask = lambda kind, options, **i: seen.append(i.get('prompt')) or next(answers)
    g.vm = SimpleNamespace(out=[], text_epoch=0); coin_menu(g, st.party[0])
    assert seen[1] == 'How much silver  will you take? ' and coins(st.party[0])[1] == 7, seen
    g.ask = lambda kind, options, **i: next(answers)
    worn = bytearray(it); worn[0x34] = 1; st.party[0].items = [worn]; st.treasure_items = []; answers = iter([0, 0])
    g.ask = lambda kind, options, **i: options.index({'LIST': 0, 'SHOP_MENU': 'deposit'}[kind]) if next(answers, None) is not None else options.index(None)
    g.vm.clear_text = lambda: None; item_menu(g, st.party[0], 'vault')
    assert st.party[0].items == [worn] and worn[0x34] == 1 and not st.treasure_items and g.vm.service_bottom[2] == 'Must be unreadied'
    g.vm.service_names = []; assert not use_item(g, st.party[0], 0) and not g.vm.service_names
    scroll = bytearray(67); scroll[0x2E], scroll[0x34], scroll[0x35], scroll[0x3C] = 0x27, 1, 4, 15; st.party[0].items = [scroll]
    g.ask = None; assert not use_item(g, st.party[0], 0) and scroll[0x3C] == 15
    from sm.titles.ssb.units import magic
    wand = bytearray(67); wand[0x2E], wand[0x34], wand[0x3C] = 5, 1, 2; wand[0x3D] = next(i for i in range(1, 118) if not magic.spell(i)[7])
    st.party[0].items = [wand]; seen = []; answers = iter(['cancel', 'use'])
    g.ask = lambda kind, options, **i: (seen.append(i.get('purpose')), options.index(next(answers)))[1]
    assert not use_item(g, st.party[0], 0) and wand[0x3C] == 2 and use_item(g, st.party[0], 0) and wand[0x3C] == 1 and seen == ['use refusal'] * 2
    scroll[0x34], scroll[0x3C] = 0, 0x80 | 15; st.party[0].items = [scroll]; seen = []; answers = iter([0, 'drop', 'cancel', None])
    item_menu(g, st.party[0], 'camp'); assert seen[2] == 'lose scribe scroll' and st.party[0].items == [scroll], seen
    st.party.append(Char(bytes(439))); rec.wrw(st.party[0].b, 0x103 + 2, 3); seen = []; answers = iter([1, 0, 3])
    g.ask = lambda kind, options, **i: seen.append(i.get('prompt')) or next(answers)
    trade_money(g, st.party[0]); assert seen[0] == 'Trade to?' and seen[2] == 'How much silver will you trade? ', seen
    assert coins(st.party[1])[1] == 3; st.party.pop(); st.party[0].items = []
    st.party[0].items = [bytearray(it) for _ in range(16)]; st.treasure_items = [bytearray(it)]
    answers = iter([0, 1]); calls = []
    g.ask = lambda kind, options, **i: calls.append((kind, options)) or next(answers)
    take(g)
    assert calls == [('LIST', [0, None]), ('LIST', [0, None])]
    assert len(st.party[0].items) == 16 and len(st.treasure_items) == 1

def test():
    test_take()
    from sm.titles.ssb.units._services_test import test as check_services
    from sm.titles.ssb.ui._prompts_test import test as check_prompts
    check_services(); check_prompts()
    from sm.titles.ssb.state import State
    from types import SimpleNamespace
    s = State(); c = Char(bytes(439)); c.b[0x11] = 10; c.b[0xED] = 12; s.party = [c]
    game = SimpleNamespace(s=s); s.r1[0x36D] = 16
    it = bytearray(67); rec.wrw(it, 0x3A, 320); rec.wrw(it, 0x37, 10)
    assert [price(it, m) for m in (1, 2, 4, 8, 16, 32, 64, 128, 3)] == [20, 40, 80, 160, 320, 640, 1280, 2560, 320]
    set_money(c, 500); assert buy(game, c, [it]) and total(coins(c)) == 180 and len(c.items) == 1
    s.treasure_money[3] = 320; assert buy(game, c, [it]) and total(coins(c)) == 180 and total(s.treasure_money) == 0
    set_money(c, 100); s.treasure_money[3] = 220; assert not buy(game, c, [it])
    set_money(c, 500); recalc(c); rec.wrw(it, 0x37, 65535); before = bytes(c.b)
    assert not buy(game, c, [it]) and bytes(c.b) == before
    pool_money(s); assert total(coins(c)) == 0 and total(s.treasure_money) == 720
    share(s); assert total(coins(c)) == 720 and total(s.treasure_money) == 0
    from sm.titles.ssb.ui.screen import buy_notice
    drawn = []; flash = SimpleNamespace(rect=lambda *a: None, text=lambda *a: drawn.append(a[2]))
    vm = SimpleNamespace(service_bottom=(1, 0, 'OverLoaded'))
    ui = SimpleNamespace(effect_scale=1, session=SimpleNamespace(decision=dict(kind='LIST', info=dict(purpose='buy')),
                         game=SimpleNamespace(vm=vm, s=SimpleNamespace(g={'67D6': 5}))))
    buy_notice(ui, flash, None, 1e6); assert not drawn
    buy_notice(ui, flash, None, 10); buy_notice(ui, flash, None, 10.4); assert drawn == ['OverLoaded'] * 2
    buy_notice(ui, flash, None, 10.6); assert drawn == ['OverLoaded'] * 2
    drawn.clear(); vm.service_bottom = (2, 0, 'Overloaded', 'Sold!')
    for t in (20, 20.4, 20.6, 21): buy_notice(ui, flash, None, t)
    assert drawn == ['Sold!', 'Sold!', 'Overloaded']
    buy_notice(ui, flash, None, 0); assert len(drawn) == 3
    heavy = bytearray(it); rec.wrw(heavy, 0x37, 65535); taker = SimpleNamespace(s=s, vm=SimpleNamespace(out=[], text_epoch=0))
    s.treasure_items = [heavy]; lists = iter([0, None])
    taker.ask = lambda kind, options, **i: options.index(next(lists))
    take_items(taker, c); assert taker.vm.service_bottom[2] == 'OverLoaded' and s.treasure_items == [heavy]; s.treasure_items = []
    from sm.titles.ssb.ui.screen import name_notice
    drawn.clear(); vm.service_name = (1, 'GUY', 'is not blind', 12); ui.session.decision = dict(kind='LIST', info=dict(purpose='temple service'))
    flash.rows = [bytearray(320) for _ in range(200)]; flash.rows[32][16:18] = bytes((15, 0)); ui.selected = 0
    name_notice(ui, flash, None, 1e6); assert not drawn
    name_notice(ui, flash, None, 10); assert drawn == ['GUY', 'is not blind'] and flash.rows[32][16:18] == bytes((0, 10))
    name_notice(ui, flash, None, 10.6); assert drawn == ['GUY', 'is not blind']
    from sm.titles.ssb.ui.screen import not_here
    drawn.clear(); ui.not_here_seen = False
    not_here(ui, flash, None, 1e6); assert not drawn
    not_here(ui, flash, None, 10); assert drawn == ['Not Here']
    not_here(ui, flash, None, 10.6); assert drawn == ['Not Here'] and ui.not_here_seen is None
    six = SimpleNamespace(party=[Char(bytes(439)) for _ in range(6)], treasure_money=[0, 0, 0, 2004, 1000, 120, 6], g={})
    rec.wrw(six.party[0].b, 0x19B, rec.carry(six.party[0]) + 1500 - 224); share(six)
    assert [coins(m)[3:] for m in six.party] == [[36, 167, 20, 1], [628, 167, 20, 1], [335, 167, 20, 1], [335, 167, 20, 1], [335, 166, 20, 1], [335, 166, 20, 1]]
    assert six.treasure_money == [0] * 7 and rec.rdw(six.party[0].b, 0x19B) == rec.carry(six.party[0]) + 1500
    assert total([199, 0, 0, 0, 0, 999, 999]) == 0 and total([200, 0, 0, 0, 0, 0, 0]) == 1
    assert total([1, 1, 1, 1, 1, 999, 999]) == 6
    assert total([-199, 0, 0, 0, 0, 0, 0]) == 0 and total([-201, 0, 0, 0, 0, 0, 0]) == -1
    assert total([0x7FFFFFFF, 1, 0, 0, 0, 0, 0]) == -10737418
    set_money(c, 65536 + 9); assert total(coins(c)) == 9
    s.g['vault.image'] = struct.pack('<7i', 1, 2, 3, 4, 5, 6, 7) + bytes(it)
    money, items = vault_data(s); assert money == list(range(1, 8)) and bytes(items[0]) == bytes(it)
    assert s.copy().hash() == s.hash()
