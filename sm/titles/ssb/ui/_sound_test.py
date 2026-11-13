from unittest.mock import patch

from sm.titles.ssb.ui import screen
from sm.titles.ssb.ui._presentation_test import scene
from sm.titles.ssb.units import magic


def played(ui):
    start, t = ui.sound_seq, 0.0
    while ui.session.game.presentation or ui.presentation_event:
        t += 10; ui.advance_presentation(t)
    return [c for n, c in ui.sound_events if n > start]


def check_walk():
    from sm.engine import Session
    from sm.titles.ssb.ui._test import townhall
    ui, reference = Session(engines=True), Session(engines=True)
    try:
        c = screen.Controller(ui); townhall(c, reference); assert not c.key('m', 'm')
        s, n = ui.game.s, c.sound_seq
        for key, sent in (('Left', [10]), ('Down', []), ('Right', [10])):
            assert c.key(key) and [cmd for seq, cmd in c.sound_events if seq > n] == sent, (key, list(c.sound_events)); n = c.sound_seq
        before = (s.x, s.y); assert c.key('Up')
        assert [cmd for seq, cmd in c.sound_events if seq > n] == ([10] if (s.x, s.y) != before else []), (before, (s.x, s.y))
    finally: ui.close(); reference.close()


def test():
    check_walk()
    game, battle, ui = scene(); a, b = battle.chars
    battle.attack(a, b); got = played(ui)
    assert got and set(got) <= {7, 9, 5} and got[0] in (7, 9), got
    assert screen.layout(ui)['sound'][-1][1] == got[-1]
    battle.record(a)[6] = 20; battle.move(a, battle.legal_moves(a)[0])
    assert played(ui) == [10]
    battle.kill(b); assert played(ui) == [5]
    for typ, second in ((5, 12), (3, 9), (28, 6), (4, 9)):
        item = bytearray(67); item[0x2E] = typ; battle.missile(a, b, item)
        assert played(ui) == [12, second], typ
    for sid, cue in ((47, 11), (51, 8), (15, 2)):
        game, battle, ui = scene(); a, b = battle.chars; a.b[0x116] = 9
        with patch.object(magic._Magic, 'save', return_value=False): magic.cast(game, a, sid, [b], combat=True, consume=False)
        got = played(ui); assert got[0] == cue, (sid, got)
        if sid in (15, 47): assert 4 in got or 3 in got, (sid, got)
    game, battle, ui = scene(); magic._Magic(game).effect(battle.chars[1], 1, 5, text='is Blessed')
    assert played(ui) == [4]
    assert screen.event_sounds(dict(kind='sound', cue='cast'), (None,) * 4) == [2]
    ev = dict(kind='message', text='HERO\nAttacks\nFOE\nHitting for 3 points of damage\n\nFOE\nis killed')
    assert screen.event_sounds(ev, ('message', 0, 'HERO\nAttacks\nFOE\nHitting for 3 points of damage', False)) == []
    return 'ssb sound: melee, move, death, missiles, spells, flashes send their cues'


if __name__ == '__main__':
    print(test())
