from sm.titles.ssb import data as ssb_data
from sm.search import shortest_path
from functools import lru_cache
from typing import NamedTuple

from sm import dax

FACINGS = (0, 2, 4, 6)
DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))


class Cell(NamedTuple):
    walls: tuple
    passages: tuple
    attr: int


def _index(x, y):
    if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < 16 and 0 <= y < 16):
        raise ValueError('coordinates must be integers in 0..15')
    return y * 16 + x


def _direction(facing):
    if not isinstance(facing, int) or facing not in FACINGS:
        raise ValueError('facing must be 0, 2, 4 or 6 (N/E/S/W)')
    return facing // 2


@lru_cache(maxsize=3)
def _records(dataset):
    return dax.load('GEO%d' % dataset, d=ssb_data.SECRET)


def open_wall(map, x, y, facing):
    return map.walls(x, y, facing) == 0 or map.passages(x, y, facing) == 1


def _choices(map, x, y, facing, passable):
    result = [('turn-left', (x, y, (facing - 2) % 8)),
              ('turn-right', (x, y, (facing + 2) % 8))]
    if passable(map, x, y, facing):
        dx, dy = DELTAS[facing // 2]
        result.append(('forward', ((x + dx) % 16, (y + dy) % 16, facing)))
    return result


class Map:
    def __init__(self, dataset, id, *, record=None):
        if not isinstance(dataset, int) or dataset not in (1, 2, 3):
            raise ValueError('dataset must be 1, 2 or 3')
        self.dataset, self.id = dataset, id
        if record is None:
            record = _records(dataset)[id]
        if len(record) != 1026:
            raise ValueError('GEO%d/%s: expected 1026 bytes, got %d' %
                             (dataset, id, len(record)))
        self.header = int.from_bytes(record[:2], 'little')
        cells = []
        for i in range(256):
            ne, sw, attr, passage = (record[2 + i + 256 * p] for p in range(4))
            cells.append(Cell((ne >> 4, ne & 15, sw >> 4, sw & 15),
                              tuple((passage >> f) & 3 for f in FACINGS), attr))
        self.cells = tuple(cells)
        self.graph = {(x, y, f): tuple(_choices(self, x, y, f, open_wall))
                      for y in range(16) for x in range(16) for f in FACINGS}

    def walls(self, x, y, facing):
        return self.cells[_index(x, y)].walls[_direction(facing)]

    def attr(self, x, y):
        return self.cells[_index(x, y)].attr

    def passages(self, x, y, facing):
        return self.cells[_index(x, y)].passages[_direction(facing)]


def moves(map, x, y, facing, passable=open_wall):
    _index(x, y)
    _direction(facing)
    if passable is open_wall:
        return list(map.graph[x, y, facing])
    return _choices(map, x, y, facing, passable)


def path(map, start, goal, passable=open_wall):
    start, goal = tuple(start), tuple(goal)
    if len(start) != 3 or len(goal) not in (2, 3):
        raise ValueError('start needs x/y/facing; goal needs x/y or x/y/facing')
    _index(*start[:2])
    _direction(start[2])
    _index(*goal[:2])
    if len(goal) == 3:
        _direction(goal[2])
    return shortest_path(start, lambda state: state[:len(goal)] == goal,
                         lambda state: moves(map, *state, passable=passable))


def test():
    from time import perf_counter

    began = perf_counter()
    _records.cache_clear()
    maps = [Map(ds, rid) for ds in (1, 2, 3) for rid in sorted(_records(ds))]
    assert len(maps) == 17, 'expected 17 GEO records'
    for m in maps:
        assert len(m.cells) == 256 and len(m.graph) == 1024
        ew = sum(bool(m.walls(x, y, 2)) == bool(m.walls(x + 1, y, 6))
                 for y in range(16) for x in range(15))
        ns = sum(bool(m.walls(x, y, 4)) == bool(m.walls(x, y + 1, 0))
                 for y in range(15) for x in range(16))
        assert min(ew, ns) >= 0.8 * 240, (m.dataset, m.id, ew, ns)

    m = next(m for m in maps if (m.dataset, m.id) == (1, 16))
    start, target = next((state, target) for state, edges in m.graph.items()
                         for choice, target in edges if choice == 'forward')
    start = (start[0], start[1], (start[2] + 4) % 8)
    route = path(m, start, target[:2])
    assert route is not None and len(route) == 3, 'turn twice, then step'
    state = start
    for choice in route:
        state = dict(moves(m, *state))[choice]
    assert state[:2] == target[:2], 'BFS choices must replay to the goal'
    incoming = {target[:2] for edges in m.graph.values()
                for choice, target in edges if choice == 'forward'}
    sealed = next(((x, y) for y in range(16) for x in range(16)
                  if (x, y) not in incoming and (x, y) != start[:2]), None)
    assert sealed is None or path(m, start, sealed) is None, 'walled-off target must be unreachable'

    raw = bytearray(1026)
    raw[:2] = (0x1234).to_bytes(2, 'little')
    i = 5 * 16 + 3
    for plane, value in enumerate((0x12, 0x34, 0xA5, 0xE4)):
        raw[2 + i + 256 * plane] = value
    packed = Map(1, 0, record=raw)
    assert packed.header == 0x1234 and packed.attr(3, 5) == 0xA5
    assert tuple(packed.walls(3, 5, f) for f in FACINGS) == (1, 2, 3, 4)
    assert tuple(packed.passages(3, 5, f) for f in FACINGS) == (0, 1, 2, 3)
    for wall in range(1, 16):
        raw[2 + wall] = raw[258 + wall] = wall * 17
    blocked = Map(1, 0, record=raw)
    assert all(len(moves(blocked, wall, 0, f)) == 2
               for wall in range(1, 16) for f in FACINGS)

    torus = Map(1, 0, record=bytes(1026))
    for start, target in (((0, 0, 0), (0, 15, 0)), ((15, 0, 2), (0, 0, 2)),
                          ((0, 15, 4), (0, 0, 4)), ((0, 0, 6), (15, 0, 6))):
        assert moves(torus, *start)[-1] == ('forward', target)
        assert path(torus, start, target) == ['forward']
    assert path(torus, (0, 0, 0), (0, 0)) == []
    assert path(torus, (0, 0, 0), (0, 0, 6)) == ['turn-left']
    assert path(torus, (0, 0, 6), (0, 0, 0)) == ['turn-right']
    assert len(path(torus, (0, 0, 0), (8, 8))) == 17
    deny = lambda m, x, y, f: False
    assert path(torus, (0, 0, 0), (1, 0), passable=deny) is None
    assert path(torus, (0, 0, 0), (0, 0, 2), passable=deny) == ['turn-right']
    allow = lambda m, x, y, f: m.attr(x, y) == 0xA5 and m.passages(x, y, f) == 1
    assert path(packed, (3, 5, 2), (4, 5), passable=allow) == ['forward']
    assert len(moves(packed, 3, 5, 2)) == 3 and len(moves(packed, 3, 5, 4)) == 2, 'GATE-2: passage 1 opens a wall, 2 does not'

    for size in (0, 1025, 1027):
        try:
            Map(1, 0, record=bytes(size))
        except ValueError:
            pass
        else:
            raise AssertionError('accepted an invalid GEO record length')
    for x, y, f in ((-1, 0, 0), (16, 0, 0), (0, 16, 0), (0, 0, 1), (0, 0, 8)):
        try:
            moves(torus, x, y, f)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted an invalid position/facing')
    elapsed = perf_counter() - began
    assert elapsed < 1, 'walk.test took %.3fs (limit 1s)' % elapsed
