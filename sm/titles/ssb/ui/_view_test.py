import hashlib
from types import SimpleNamespace

from sm.engine import Session
from sm.titles.ssb.ui import view3d
from sm.titles.ssb.ui._test import townhall
from sm.titles.ssb.ui.screen import Assets, Controller, Frame, LOCAL, render


def view_bytes(frame):
    return b''.join(row[24:112] for row in frame.rows[24:112])


def test(screenshot=False):
    session, assets = Session(engines=True), Assets()
    try:
        controller = Controller(session)
        townhall(controller)
        state, map_ = session.game.s, session.game.geo.map
        before = state.hash(session.game.vm)
        first, second = Frame(), Frame()
        view3d.draw(first, state, map_, assets)
        view3d.draw(second, state, map_, Assets())
        original = view_bytes(first)
        assert original == view_bytes(second) and len(set(original)) > 4
        assert all(not any(row[:24] + row[112:]) for row in first.rows)
        assert all(not any(row) for row in first.rows[:24] + first.rows[112:])
        views = set()
        for facing in (0, 2, 4, 6):
            copy = state.copy()
            copy.dir = facing
            frame = Frame()
            view3d.draw(frame, copy, map_, assets)
            views.add(view_bytes(frame))
            copy.g['door %d %d %d' % (copy.x, copy.y, facing)] = 1
            opened = Frame()
            view3d.draw(opened, copy, map_, assets)
            assert frame.rows == opened.rows
        assert len(views) == 4
        copy = state.copy()
        copy.r0[0xFB], copy.r0[0x1FD] = 0, 255
        area = Frame()
        view3d.draw(area, copy, map_, assets, area=True)
        x0, y0 = max(0, min(5, copy.x - 5)), max(0, min(5, copy.y - 5))
        x, y = 24 + (copy.x - x0) * 8, 24 + (copy.y - y0) * 8
        assert tuple(bytes(row[x:x + 8]) for row in area.rows[y:y + 8]) == assets.border(0x100 + copy.dir // 2)
        assert view_bytes(area) != original
        assert before == state.hash(session.game.vm)
        frame = render(controller, assets)
        assert view_bytes(frame) == original, 'live explore view covered by a stale picture'
        if screenshot:
            frame.save(LOCAL / 'ui_townhall.png')
            view3d.area_map(frame, state, map_, assets)
            frame.save(LOCAL / 'ui_area_map.png')
        check_cone()
        print('UI 3D town hall: deterministic %s; four facings, clipping, doors, area map: PASS' %
              hashlib.sha256(original).hexdigest()[:16])
    finally:
        session.close()


def check_cone():
    walls = {(8, 6, 0): 1, (8, 7, 0): 2, (8, 8, 0): 3}
    map_ = SimpleNamespace(walls=lambda x, y, f: walls.get((x, y, f), 0))
    state = SimpleNamespace(x=8, y=8, dir=0, block=16)
    assert view3d.pieces(map_, state) == [(1, 0, 5, 4), (1, 0, 5, 4),
                                        (2, 3, 4, 3), (2, 3, 4, 3), (3, 6, 2, 1), (3, 6, 2, 1)]
    walls[(7, 6, 0)] = 4
    assert view3d.pieces(map_, state)[:3] == [(1, 0, 5, 4), (1, 9, 4, 4), (4, 0, 3, 4)]
    walls[(15, 8, 0)] = 5
    assert view3d.wall_at(map_, 16, -1, 8, 0) == 5
    assert view3d.wall_at(map_, 0x50, -1, 8, 0) == 0
    assert view3d.sky_pictures(0, 11, 2, 3) == [(251, 9, 4), (252, 2, 7)]
    assert view3d.sky_pictures(128, 11, 2, 3) == [(252, 2, 7)]
    assert view3d.sky_pictures(0, 11, 0, 0) == [(250, 2, 2), (252, 2, 7)]
