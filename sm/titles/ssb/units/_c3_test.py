from sm.titles.ssb import data as ssb_data
from sm.titles.ssb import host, route; from sm.titles.ssb import rec
from sm.titles.ssb.state import State, Char
from sm.titles.ssb.vm import VM
from sm.titles.ssb.units import camp, shops, creation


def fresh(policy):
    g = host.Game.__new__(host.Game); g.s = State(); g.trace = []; g.player = policy; g.hashing = True; g.engines = True
    g.geo = host.Geo(); g.vm = VM(g.s, g.ask, g.geo); g.vm.host = g
    return g


def scripted(entries):
    pending = iter(entries)
    def answer(kind, options, game, **info):
        if kind == 'INPUT': return 0
        wanted, value = next(pending)
        assert kind == wanted, (kind, wanted, options)
        return options.index(value) if options is not None else value
    return answer


def replayed(setup, action, policy):
    first = fresh(policy); setup(first); action(first); answers = iter(first.trace)
    def replay(kind, options, game, **info):
        row = next(answers); assert row[1] == kind
        return row[6]
    second = fresh(replay); setup(second); action(second)
    assert first.trace == second.trace and first.s.hash(first.vm) == second.s.hash(second.vm)
    return first


def caster_setup(g):
    c = Char(bytes(439)); b = c.b
    b[0x111] = b[0xEE] = b[0x1A7] = b[0x73] = b[0x132] = 1
    b[0x70], b[0x1B5], b[0x15], b[0x6B], b[0xED] = 20, 4, 12, 6, 12
    g.s.party = [c]; g.s.r1[0x33E] = 1


def check_camp():
    entries = [('CAMP_MENU', 'magic'), ('CAMP_MENU', 'memorize'), ('SPELL', 3), ('SPELL', 'done'), ('SPELL', 'exit'), ('SPELL', 'yes'),
               ('CAMP_MENU', 'rest'), ('CAMP_MENU', 'rest')] + [('CAMP_MENU', 'exit')] * 2
    g = replayed(caster_setup, camp.run, scripted(entries))
    assert 3 in g.s.party[0].b[0x1E:0x69] and g.s.party[0].b[0x1B5] == 4
    assert g.s.r0[0xC7:0xCA] == [5, 1, 4] and g.s.g['camp.rested'] == 1
    for pending_answer in (None, 'continue', 'stop'):
        polled = []
        def setup_rest(h):
            caster_setup(h); h.s.party[0].b[0x1E] = 0x83; camp.rest_need(h.s.party[0])
        def rest_input(kind, options, h, **info):
            if kind == 'INPUT':
                polled.append(info['remaining']); return int(len(polled) == 1 and pending_answer is not None)
            assert info.get('purpose') == 'resting' and pending_answer is not None, 'unsolicited stop prompt'
            return options.index(pending_answer)
        h = replayed(setup_rest, lambda h: camp.rest(h, 420, True), rest_input)
        stopped = pending_answer == 'stop'
        assert h.s.r0[0xC7:0xCA] == [0, 0, 0 if stopped else 7]
        assert h.s.party[0].b[0x1E] == (0x83 if stopped else 3)
        assert len(polled) == (1 if stopped else 84), 'native five-minute polling cadence'
    for interrupted in (False, True):
        entries = [('CAMP_MENU', 'rest'), ('CAMP_MENU', 'minutes'), ('CAMP_MENU', 'add'), ('CAMP_MENU', 'rest')]
        if not interrupted: entries.append(('CAMP_MENU', 'exit'))
        h = fresh(scripted(entries)); caster_setup(h)
        h.s.r1[0x2D2], h.s.r1[0x2D3] = int(interrupted), 100
        assert camp.run(h) is interrupted and h.s.g['camp.rested'] == 1


def check_temple():
    g = fresh(lambda *a, **k: 0); caster_setup(g); c = g.s.party[0]
    shops.set_money(c, 123); purse = shops.coins(c); expected = State().random(8) + 1
    assert shops.cure(g, c, 2) and c.b[0x1B5] == 4 + expected and shops.coins(c) == purse
    c.b[0x1A6] = 6; before = c.b[0x1B5]; assert not shops.cure(g, c, 2) and c.b[0x1B5] == before
    c.b[0x6B] = 1; assert not shops.cure(g, c, 7)
    c.b[0x6B], c.b[0x19], c.b[0x131] = 6, 16, 20
    assert shops.cure(g, c, 7) and (c.b[0x1B5], c.b[0x1A6], c.b[0x1A7], c.b[0x19]) == (1, 0, 1, 15)
    c.b[0x1A6] = 7; assert shops.cure(g, c, 9) and c.b[0x1A6] == 0
    from sm.titles.ssb.units import magic
    magic.add_effect(g, c, 0x37, 0); c.b[0x1B5] = c.b[0x1A7] = 0
    assert shops.cure(g, c, 6) and c.b[0x1B5] == 1 and c.b[0x1A7] == 1 and not rec.has_effect(c, 0x37)
    magic.add_effect(g, c, 0x24, 0); c.b[0x1A7] = 0; g.s.r0[0xE5] = 1
    assert shops.cure(g, c, 8) and not rec.has_effect(c, 0x24)
    assert shops.coins(c) == purse
    for temple, maximum in ((True, 30), (False, 20)):
        b = c.b; b[0x1A6], b[0x19], b[0x70], b[0x131] = 6, 14, 30, 20
        if temple: shops.cure(g, c, 7)
        else: camp.fix_status(g, dict.fromkeys(('raise', 'curse', 'sight', 'disease', 'heal', 'poison', 'stone'), 1))
        assert (b[0x19], b[0x70], b[0x1B5]) == (13, maximum, 1)
    entries = [('SHOP_MENU', 'heal'), ('LIST', 2), ('LIST', None), ('SHOP_MENU', 'exit')]
    replayed(caster_setup, shops.temple, scripted(entries))


def check_creation():
    def setup(g):
        g.s.g['creation.roster_loaded'] = 1
    entries = [('CREATE_MENU', 'create'), ('CREATE_RACE', 6), ('CREATE_GENDER', 0), ('CREATE_CLASS', 2),
               ('CREATE_ALIGNMENT', 0), ('CREATE_ROLL', 'keep'), ('CREATE_NAME', 'PortTest'), ('CREATE_ICON', 'keep'),
               ('CREATE_SAVE', 'save'), ('CREATE_MENU', 'add'), ('CREATE_ADD', 'character.PORTTEST'), ('CREATE_ADD', None), ('CREATE_MENU', 'begin')]
    g = replayed(setup, creation.run, scripted(entries)); c = g.s.party[0]
    assert c.b[0x113] == 8 and c.b[0x1B5] == c.b[0x70] and c.b[0x70] > 1
    assert rec.rdw(c.b, 0x109) == 0 and g.s.r1[0x33E] == 1


def check_inventory():
    g = fresh(scripted([('SHOP_MENU', 'cancel')])); caster_setup(g); c = g.s.party[0]
    it = bytearray(67); it[0x2E], it[0x39] = 0x1E, 31; rec.wrw(it, 0x3A, 100)
    c.items = [it]; assert not shops.sell(g, c, 0) and len(c.items) == 1
    shops.halve(c, 0); assert [i[0x39] for i in c.items] == [16, 15]
    head = bytearray(67); head[0x2E], head[0x39] = 0x49, 3
    children = []
    for sid, value in ((3, 100), (15, 200), (18, 300)):
        child = bytearray(67); child[0x2E], child[0x2F], child[0x3C] = 0x27, 100, sid
        rec.wrw(child, 0x3A, value); children.append(child)
    c.items = [head] + children; shops.halve(c, 0)
    assert [(i[0][0x2E], len(i)) for _, i in shops.groups(c.items)] == [(0x49, 3), (0x27, 1)]
    assert sum(rec.rdw(i[0], 0x3A) for _, i in shops.groups(c.items)) == 600
    camp.consume_scroll(c, 1, 0x3C)
    assert [(i[0x2E], i[0x3C]) for i in c.items] == [(0x27, 18), (0x27, 3)]
    c.items[0][0x35] = 7; shops.set_money(c, 101)
    g.player = scripted([('SHOP_MENU', 'identify')])
    assert shops.identify(g, c, c.items[0]) and shops.total(shops.coins(c)) == 1 and c.items[0][0x35] == 0
    ring = bytearray(67); ring[0x2E], ring[0x3D], ring[0x3E] = 0x2E, 1, 0x80
    c.items = [ring]; c.b[0x130] = 1
    assert shops.ready(g, c, ring) and rec.has_effect(c, 1) and g.s.g['8DB8'] == 0
    assert shops.ready(g, c, ring) and not rec.has_effect(c, 1)
    from sm import dax
    ring[0x3E] = 0x81; c.b[0x116], c.b[0x14B] = 9, 2
    assert shops.ready(g, c, ring) and c.b[0x14B] == 4
    assert shops.ready(g, c, ring) and c.b[0x14B] == ssb_data.stexe()[0x544D + 7 * 9]
    ring[0x34]=1; before=bytes(ring)
    for command in ('trade','drop'):
        g.player=scripted([('LIST',0),('SHOP_MENU',command),('LIST',None)])
        shops.item_menu(g,c,'camp')
        assert c.items==[ring] and bytes(ring)==before
        assert g.vm.service_bottom[2]=='Must be unreadied'
    g.player=scripted([('LIST',0),('SHOP_MENU','sell'),('LIST',None)]); g.vm.service_bottom=None
    shops.item_menu(g,c,'shop')
    assert c.items==[ring] and bytes(ring)==before and g.vm.service_bottom[2]=='Must be unreadied'
    held,spare=bytearray(ring),bytearray(ring); held[0x2E]=spare[0x2E]=0x1E; held[0x34],spare[0x34]=1,0; c.items=[held,spare]; klass=c.b[0x130]
    c.b[0x130]=255; assert not shops.ready(g,c,spare) and g.vm.service_bottom[2].startswith('already using') and not spare[0x34]
    c.b[0x130]=0; assert not shops.ready(g,c,spare) and g.vm.service_bottom[2]=='Wrong Class' and not spare[0x34]
    c.b[0x130]=klass; c.items=[ring]
    ring[0x34]=0
    for count in (1,16):
        c.items=[bytearray(ring) for _ in range(count)]; before=[bytes(it) for it in c.items]
        g.player=scripted([('LIST',0),('SHOP_MENU','trade'),('TARGET',0),('LIST',None)])
        shops.item_menu(g,c,'camp')
        assert [bytes(it) for it in c.items]==before and g.s.sel==0
    recipient=Char(bytes(c.b)); g.s.party.append(recipient); c.items=[bytearray(ring)]; cursor=[0]
    g.player=scripted([('LIST',0),('SHOP_MENU','trade'),('TARGET',1),('LIST',None)])
    shops.item_menu(g,c,'camp',cursor)
    assert g.s.sel==0 and cursor==[1] and not c.items and len(recipient.items)==1


def check_vault():
    def setup(g):
        caster_setup(g); it = bytearray(67); it[0x2E] = 8; rec.wrw(it, 0x37, 10)
        g.s.party[0].items = [it]; g.s.g['vault.image'] = bytes(28)
    def action(g):
        shops.vault(g); assert not g.s.party[0].items and len(g.s.g['vault.image']) == 95
        shops.vault(g)
    entries = [('SHOP_MENU', 'view'), ('SHOP_MENU', 'items'), ('LIST', 0), ('SHOP_MENU', 'deposit'),
               ('LIST', None), ('SHOP_MENU', 'exit'), ('SHOP_MENU', 'exit'), ('SHOP_MENU', 'take'),
               ('LIST', 0), ('SHOP_MENU', 'exit')]
    g = replayed(setup, action, scripted(entries))
    assert len(g.s.party[0].items) == 1 and g.s.g['vault.image'] == bytes(28)


def town_visit(recorded=None):
    from sm.titles.ssb.resolve import resolve
    policy_state = {'phase': 0, 'camp': 0}; replay = iter(recorded) if recorded is not None else None
    def answer(kind, options, g, **info):
        if kind == 'TREASURE': resolve(kind, g)
        if replay is not None:
            row = next(replay); assert row[1] == kind; return row[6]
        if kind == 'SHOP_MENU' and info.get('purpose') in ('take', 'treasure'): return options.index('exit')
        if kind == 'SHOP_MENU' and info.get('purpose') == 'treasure leave': return options.index('no')
        if kind == 'CAMP_MENU':
            action = ('rest', 'hours', 'add', 'rest', 'exit')[policy_state['camp']]; policy_state['camp'] += 1
            return options.index(action)
        if kind == 'MOVE': return options.index(policy_state['move'])
        if kind == 'SHOP_MENU' and info.get('place') == 'shop':
            phases = ('pool', 'buy', 'share', 'exit'); action = phases[policy_state['phase']]; policy_state['phase'] += 1
            return options.index(action)
        if kind == 'LIST' and info.get('purpose') == 'buy':
            if policy_state.get('bought'): return options.index(None)
            policy_state['bought'] = True
            return info['prices'].index(min(info['prices']))
        return 0
    g = host.Game(answer, engines=True); g.boot(); assert (g.s.dataset, g.s.block) == (1, 16)
    before = sum(len(c.items) for c in g.s.party); cash = sum(shops.total(shops.coins(c)) for c in g.s.party)
    g.camp()
    assert g.s.g['camp.rested'] == 1 and g.s.g['camp.interrupted'] == 0 and not g.s.monsters
    assert not any(row[1] == 'COMBAT_ACTION' for row in g.trace)
    cells = [(x, y) for y in range(16) for x in range(16) if g.geo.map.attr(x, y) & 63 == 1]
    walker = route.Walk([], {}); paths = [walker.path(g, xy) for xy in cells]
    commands = min((p for p in paths if p is not None), key=len)
    for command in commands: policy_state['move'] = command; g.turn()
    assert sum(len(c.items) for c in g.s.party) == before + 1
    assert sum(shops.total(shops.coins(c)) for c in g.s.party) == cash - 1
    return g


def check():
    check_camp(); check_temple(); check_creation(); check_inventory(); check_vault()
    first = town_visit(); second = town_visit(first.trace)
    assert first.trace == second.trace and first.s.hash(first.vm) == second.s.hash(second.vm)
