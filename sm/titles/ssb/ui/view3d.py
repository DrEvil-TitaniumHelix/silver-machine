"""Original 88x88 view: ENGINE_READ2_f2.md ov31:0000/017B/0429/0815.

Sources are in GoldBoxUnified/decode/secret; wall loading is GATE.md section 1,
view colour selection is ENGINE_READ_w6 ov29. All drawing is presentation only.
"""
from sm.titles.ssb import data as ssb_data
from sm import dax
from sm.titles.ssb import art
from sm.titles.ssb.walk import DELTAS

ORIGIN, SIZE = 24, 88
CLIP = (24, 24, 112, 112)


def wall_at(map_, block, x, y, facing):
    """GATE.md section 2, ov31:0697: wrap to the edge; blocks 0/50h are bounded."""
    if map_ is None:
        return 0
    if not (0 <= x < 16 and 0 <= y < 16):
        if block in (0, 0x50):
            return 0
        x = 0 if x > 15 else 15 if x < 0 else x
        y = 0 if y > 15 else 15 if y < 0 else y
    return map_.walls(x, y, facing)


def pieces(map_, state):
    """ENGINE_READ2_f2 section 1, ov31:0815: (wall, piece, x, y), far to near."""
    layout = art.wall_layout()
    f = state.dir
    dx, dy = DELTAS[f // 2]
    left, right = (f + 6) % 8, (f + 2) % 8
    result = []

    def put(x, y, direction, piece, offset):
        """ov31:0C93..0F62: sample a face/side before stamping its piece."""
        wall = wall_at(map_, state.block, x, y, direction)
        if wall:
            p = layout[piece]
            result.append((wall, piece, p.x + offset, p.y))

    x, y = state.x + 2 * dx, state.y + 2 * dy
    # ov31:08C5..0AFE: left/right far faces, previous-wall seams and edge quirk.
    for side, other, stride in ((left, right, -2), (right, left, 2)):
        sx, sy = DELTAS[side // 2]
        previous = 0
        for i in range(4):
            cx, cy, offset = x + i * sx, y + i * sy, i * stride
            wall = wall_at(map_, state.block, cx, cy, f)
            if not (0 <= cx < 16 and 0 <= cy < 16) and not wall_at(map_, state.block, cx, cy, other):
                previous = 0
            if previous and (wall or wall_at(map_, state.block, cx - sx, cy - sy, side)):
                p = layout[9]
                result.append((previous, 9, p.x + offset + (1 if stride < 0 else -1), p.y))
            if wall:
                result.append((wall, 0, layout[0].x + offset, layout[0].y))
            previous = wall
    # ov31:0B01..0C2C: far side walls overwrite the faces/seams beneath them.
    for side, piece, stride in ((left, 1, -2), (right, 2, 2)):
        sx, sy = DELTAS[side // 2]
        for i in range(3):
            put(x + i * sx, y + i * sy, side, piece,
                i * stride + ((-1 if stride < 0 else 1) if i else 0))
    # ov31:0C39..0F90: each mid/near half-row runs from its outer cell to centre.
    for depth, front, count, span, side_pieces in ((1, 3, 3, 3, (4, 5)), (0, 6, 2, 7, (7, 8))):
        x, y = state.x + depth * dx, state.y + depth * dy
        for side, piece in zip((left, right), side_pieces):
            sx, sy = DELTAS[side // 2]
            sign = -1 if side == left else 1
            for lateral in range(count - 1, -1, -1):
                cx, cy, offset = x + lateral * sx, y + lateral * sy, sign * lateral * span
                put(cx, cy, f, front, offset)
                put(cx, cy, side, piece, offset)
    return result


def sky_pictures(attr, sky, facing, hour):
    """ov31:0296..0420: SKY id and buffer column/row; 02A4 jb means attr <80h."""
    result = []
    if attr < 128 and sky == 11:
        if 1 <= hour <= 5:
            if facing == 2:
                result.append((251, 9, 7 - hour))
            elif facing == 4 and hour > 2:
                result.append((251, hour - 1, 7 - hour))
        elif 13 <= hour <= 18:
            if facing == 6:
                result.append((251, 2, hour - 11))
            elif facing == 4 and hour < 16:
                result.append((251, hour - 6, hour - 11))
        if facing == 0:
            result.append((250, 2, 2))
    return result + [(252, 2, 7)]


def backdrop(frame, state, map_, sky_choices=None):
    """ENGINE_READ2_f2 section 3, ov31:017B: sky, horizon/ground, masked SKY art."""
    attr = map_.attr(state.x, state.y)
    choice = (state.r0[0xFD:0xFF] if sky_choices is None else sky_choices)[int(attr >= 128)]
    sky = ssb_data.stexe()[(0xAA8 + choice) & 65535]
    frame.rect(ORIGIN, ORIGIN, SIZE, 44, sky)
    # Foreman 2026-10-31: 89D4 starts at zero; 89D5 := 8 on the normal update path.
    frame.rect(ORIGIN, ORIGIN + 44, SIZE, 2, 0)
    frame.rect(ORIGIN, ORIGIN + 46, SIZE, 42, 8)
    for rid, col, row in sky_pictures(attr, sky, state.dir, state.r0[0xC9]):
        frame.blit(8 + col * 8, 8 + row * 8, art.picture('SKY', rid)[2][0], transparent=13, clip=CLIP)


def area_map(frame, state, map_, assets):
    """ENGINE_READ2_f2 section 4, ov31:0000: 11x11 wall bitmasks and party arrow."""
    x0, y0 = max(0, min(5, state.x - 5)), max(0, min(5, state.y - 5))
    for row in range(11):
        for col in range(11):
            mask = sum(1 << i for i, side in enumerate((0, 2, 4, 6))
                       if wall_at(map_, state.block, x0 + col, y0 + row, side))
            frame.blit(ORIGIN + col * 8, ORIGIN + row * 8, assets.border(0x104 + mask))
    frame.blit(ORIGIN + (state.x - x0) * 8, ORIGIN + (state.y - y0) * 8,
               assets.border(0x100 + state.dir // 2))


def draw(frame, state, map_, assets, *, area=False, sky_choices=None):
    """ENGINE_READ2_f2 sections 1/2, ov31:0815/0429: masked symbol grids, clipped."""
    if map_ is None:
        return
    if area and not state.r0[0xFB] and state.r0[0x1FD] == 255:
        area_map(frame, state, map_, assets)
        return
    backdrop(frame, state, map_, sky_choices)
    layout = art.wall_layout()
    for wall, piece, col, row in pieces(map_, state):
        p = layout[piece]
        for ty in range(p.height):
            for tx in range(p.width):
                if not (0 <= col + tx < 11 and 0 <= row + ty < 11):
                    continue
                tile = assets.wall_tile(state, wall, p.offset + ty * p.width + tx)
                if tile is not None:
                    frame.blit(ORIGIN + (col + tx) * 8, ORIGIN + (row + ty) * 8, tile, transparent=13)
