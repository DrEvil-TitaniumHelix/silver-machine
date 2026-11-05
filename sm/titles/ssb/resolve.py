"""GU-59 outcomes applied before the VM resumes; original bytes stay in memory.
Combat post-fight cells await GATE.md item 3 and herdr/reports/STATIC.md section 4.
"""
from sm.titles.ssb.vm import Halt, HPMAX, HP, STATUS, ACTIVE, MONEY, rdw, wrw


def resolve(kind, game):
    """Mutate game.s; treasure prefers inventories below 16, then overflows round-robin."""
    s = game.s
    match kind:
        case 'COMBAT':
            for monster in s.monsters: s.treasure_items.extend(monster.items)
            s.monsters = []; s.g['monsters'] = 0
            if not 0 <= s.sel < len(s.party): s.sel = 0
            # GATE-3: no post-fight cell writes until the decode/static evidence lands.
        case 'TREASURE':                                              # Take ov07:0FB0 -> TakeItems/GiveItem (ov08:0338), TakeMoney (ov24)
            if not s.treasure_items and not any(s.treasure_money): return   # Take is offered only with treasure (ov07:0B2F)
            dest = s.selc() if 0 <= s.sel < len(s.party) else (s.party[0] if s.party else None)
            if dest is None:
                if s.treasure_items or any(s.treasure_money): raise Halt('TREASURE: no party to receive loot')
                return
            dest.items.extend(s.treasure_items)                       # all to the selected character (ponytail: overload test ov21:392A not ported)
            from sm.titles.ssb import rec; rec.recalc_character(dest, s.r1[0x372])  # GiveItem ov08:0338 -> RecalcCharacter
            for k, amount in enumerate(s.treasure_money):
                off = MONEY + 2 * k; wrw(dest.b, off, min(0xFFFF, rdw(dest.b, off) + amount))
            s.treasure_items, s.treasure_money = [], [0] * 7
        case 'CAMP':
            for c in s.party: c.b[HP], c.b[STATUS], c.b[ACTIVE] = c.b[HPMAX], 0, 1
            game.vm.advance_clock(8, 3)                                # 8 hours via AdvanceClock ov22 (camp unit ov18 is CUT; rest length M)
        case 'SHOP' | 'TEMPLE' | 'VAULT' | 'CREATE' | 'ACK': return
        case _: raise Halt('resolver: unknown decision kind %r' % (kind,))


def test():
    """Synthetic combat loot, inventory saturation, money caps, rest and exhaustive dispatch."""
    from pickle import dumps
    from struct import pack_into, unpack_from
    from types import SimpleNamespace
    from sm.titles.ssb.state import State, Char

    def item(tag): return bytearray([tag] + [0] * 66)
    s = State(); game = SimpleNamespace(s=s)
    s.party = [Char(bytes((i + j) % 256 for i in range(439)), [item(k) for k in range(n)], [bytes(9)])
               for j, n in enumerate((15, 13))]
    s.monsters = [Char(bytes(439), [item(110 + 2 * j), item(111 + 2 * j)]) for j in range(3)]
    s.sel, s.g, s.clock = 4, {'monsters': 1, 'unrelated': 7}, 123
    s.treasure_items = [item(100), item(101)]
    s.treasure_money = [2, 5, 1, 0x1234, 65535, 0, 500]
    pack_into('<7H', s.party[0].b, 0x103, 1, 0xFFFE, 0xFFFF, 0x1234, 0, 400, 42)
    s.r0[0x1D9], s.r1[0x2E2], s.r1[0x36C] = 7, 8, 9
    party_before, memory_before = dumps(s.party), dumps((s.r0, s.r1, s.r2, s.code))
    loot = s.treasure_items[:] + [i for m in s.monsters for i in m.items]
    coins = s.treasure_money[:]
    assert resolve('COMBAT', game) is None
    assert s.monsters == [] and s.g == {'monsters': 0, 'unrelated': 7} and s.sel == 0
    assert dumps(s.party) == party_before and s.treasure_money == coins and s.clock == 123
    assert dumps((s.r0, s.r1, s.r2, s.code)) == memory_before  # GATE-3: no guessed cells.
    assert len(s.treasure_items) == len(loot) and all(a is b for a, b in zip(s.treasure_items, loot))
    s.sel = 1; before = dumps(s)
    resolve('COMBAT', game)
    assert dumps(s) == before  # Valid party selection survives; no duplicate loot.
    for sel in (-1, len(s.party), 99):
        s.sel = sel; resolve('COMBAT', game); assert s.sel == 0

    inventories = [c.items[:] for c in s.party]; records = [bytes(c.b) for c in s.party]
    assert resolve('TREASURE', game) is None
    expected = [inventories[0] + loot, inventories[1]]                  # Take: everything to the selected character (sel 0)
    for c, items in zip(s.party, expected):
        assert len(c.items) == len(items) and all(a is b for a, b in zip(c.items, items))
        assert all(isinstance(i, bytearray) and len(i) == 67 for i in c.items)
    assert unpack_from('<7H', s.party[0].b, 0x103) == (3, 65535, 65535, 0x2468, 65535, 400, 542)
    # party[0]'s derived fields are recomputed by RecalcCharacter (GiveItem); money and items are asserted above
    assert bytes(s.party[1].b) == records[1] and s.treasure_items == [] and s.treasure_money == [0] * 7
    before = dumps(s); resolve('TREASURE', game); assert dumps(s) == before

    # CAMP restores only the specified party bytes and advances the clock cells by 8 hours.
    s.monsters = [Char(bytes(439), [item(200)])]; monsters_before = dumps(s.monsters)
    for c, hp_max in zip(s.party, (42, 255)):
        c.b[0x70], c.b[0x1B5], c.b[0x1A6], c.b[0x1A7] = hp_max, 1, 7, 0
    records = [bytearray(c.b) for c in s.party]; inventory_before = dumps([(c.items, c.effects) for c in s.party])
    from sm.titles.ssb.vm import VM
    game.vm = VM(s, None); s.r0[0xC6:0xCD] = [0] * 7
    assert resolve('CAMP', game) is None and s.r0[0xC6:0xCD] == [0, 0, 0, 8, 0, 0, 0] and s.clock == 123
    for c, record in zip(s.party, records):
        record[0x1B5], record[0x1A6], record[0x1A7] = record[0x70], 0, 1
        assert c.b == record
    assert dumps([(c.items, c.effects) for c in s.party]) == inventory_before
    assert dumps(s.monsters) == monsters_before
    before = dumps(s)
    for kind in ('SHOP', 'TEMPLE', 'VAULT', 'CREATE', 'ACK'):
        assert resolve(kind, game) is None and dumps(s) == before
    for kind in ('MENU', 'WHO', 'NUMBER', 'STRING', 'PARLAY', 'MOVE', 'TRAIN', 'unknown', '', None):
        try: resolve(kind, game)
        except Halt: pass
        else: raise AssertionError('accepted unknown kind %r' % (kind,))
        assert dumps(s) == before

    game.s = empty = State(); before = dumps(empty)
    resolve('TREASURE', game); assert dumps(empty) == before
    for items, money in (([item(201)], [0] * 7), ([], [1] + [0] * 6)):
        empty.treasure_items, empty.treasure_money = items, money; before = dumps(empty)
        try: resolve('TREASURE', game)
        except Halt: pass
        else: raise AssertionError('discarded treasure without a party')
        assert dumps(empty) == before
