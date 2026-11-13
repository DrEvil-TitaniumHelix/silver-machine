import hashlib
from functools import lru_cache
from pathlib import Path
import struct

from sm.titles.ssb.ui.screen import Frame, PALETTE
from sm.titles.ssb.art import decode_walls
from sm.titles.ssb.walk import DELTAS
from sm.ui.art import decode
from .. import menu, town

LOCAL = Path(__file__).resolve().parents[4] / 'local'
ORIGIN, SIZE = 24, 88
CLIP = (24, 24, 112, 112)

TABLES = {
    'spell_headings': (51290, 410, '917be6628b512e8b0523483b6e43349a4848d4af21a4c6d5af2a11d18e0f6bb9'),
    'sky': (51748, 16, '0810d61cad4464243dadeb745b1812cb695527ee358356450bde20a9a92bfc9b'),
    'slices': (51796, 70, '439f69253bc8097c9bd594b2974c322929a1d79df74eac4c6bc89ab2979cb416'),
    'divider': (51930, 17, '69826e5edb6ec8c36ece13d1dc21805b03633be60ae2d102945edde733315fba'),
    'insets': (51971, 26, 'b2c328a8fd89612556f0351e396a3cf908f5b4e29f6cd46521caa4c62f9d75de'),
    'combat_sides': (51997, 23, 'e3da111a7715cc970b749d33d620e499c5665e3c3c1b0b6455bbc44368a79619'),
    'sheet_sides': (52066, 23, '8fecdc44070b9430fa6ae24d2c6ba996c52e64e249216af261771ca4aba33228'),
    'sheet_divider': (52089, 11, 'de8149e25615b37f16c38cc68903496def7e0439f641096da3ab97786f569e5b'),
    'icon_palette': (55958, 16, 'b17985999b92f7d2fd75c1ec625f7c1ae28fa559b935a826b557effff6df1dcb'),
    'icon_colors': (62827, 6, '2d21540386a1918e89ab038633ba8cf97aa68712c59f856fa03ba8faccc05e98'),
}


class Assets(menu.MenuAssets):
    def __init__(self, directory=None):
        super().__init__(directory)
        self.view_tables = {}
        for name, (offset, size, digest) in TABLES.items():
            raw = self.resident[offset:offset+size]
            if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Champions view table differs: '+name)
            self.view_tables[name] = raw
        raw = self.view_tables['slices']
        xs, ys = struct.unpack_from('<10H', raw, 30), struct.unpack_from('<10H', raw, 50)
        self.slices = tuple((raw[i], raw[i+10], raw[i+20], xs[i], ys[i]) for i in range(10))

    @lru_cache(maxsize=96)
    def picture(self, family, ident, dataset=1):
        name = family if family == 'SKY' else family+str(dataset)
        return decode(self.records(name)[ident], delta=family in ('PIC', 'FINAL'))

    @lru_cache(maxsize=32)
    def wall_sets(self, dataset, ids, filed=()):
        blocks = {}
        symbols = [self.picture('8X8D', 203, 1).parts[0].frames, None, None, None, self.border]
        for slot, ident in enumerate(ids, 1):
            if ident == 0xFFFF or ident == 0 and slot in filed: continue
            for block in decode_walls(self.records('WALLDEF%d' % dataset)[ident], ident, slot):
                blocks[block.slot] = block
                symbols[block.slot] = self.picture('8X8D', block.symbol_set, dataset).parts[0].frames
        return blocks, symbols

    def wall_symbol(self, state, wall, index, filed=()):
        blocks, _ = self.wall_sets(state.dataset, tuple(state.walls), filed)
        slot, kind = divmod(wall-1, 5)
        return blocks[slot+1].types[kind][index] if slot+1 in blocks else 0

    def wall_tile(self, state, symbol, filed=()):
        _, slots = self.wall_sets(state.dataset, tuple(state.walls), filed)
        starts = (1, 46, 116, 186, 256)
        if symbol == 0: return None
        slot = next(i for i in range(4, -1, -1) if symbol >= starts[i])
        if slots[slot] is None: raise ValueError('Champions wall symbol refers to an unloaded set')
        return slots[slot][symbol-starts[slot]]

    @lru_cache(maxsize=32)
    def combat_picture(self, family, ident): return decode(self.records(family)[ident]).parts[0].frames

    @lru_cache(maxsize=128)
    def party_icon(self, head, body, size, colors):
        bias = 64 if size == 2 else 0
        frames = []
        for attack in (0, 128):
            hp = self.combat_picture('CHEAD',(head+bias+attack)&255)[0]
            bp = self.combat_picture('CBODY',(body+bias+attack)&255)[0]
            frames.append(tuple(bytes(v|(hp[y][x] if y<len(hp) and x<len(hp[y]) else 0) for x,v in enumerate(row)) for y,row in enumerate(bp)))
        recolor = list(range(16))
        for base,color in zip(self.view_tables['icon_colors'],colors): recolor[base],recolor[base+8] = color&15,color>>4
        return tuple(frames),tuple(recolor[v] for v in self.view_tables['icon_palette'])

    def combat_icon(self, game, index, frame=0):
        c,r = game.s.chars()[index],game.s.g['cok.battle']['actors'][index]
        source = next((v for v in game.s.g.get('cok.monster_icons',[]) if v[0] == index),None)
        npc = game.vm.icons.get(town.field(c,'order'))
        if not source and npc and npc[0]=='CPIC' and town.field(c,'npc')>127:
            source=index,npc[2],npc[1],town.field(c,'order')
        if source:
            _,dataset,picture,_ = source
            pixels,palette = self.combat_picture('CPIC%d'%dataset,(picture+128*frame)&255)[0],tuple(self.view_tables['icon_palette'])
        else:
            frames,palette = self.party_icon(*(town.field(c,k) for k in ('icon_head','icon_body','icon_size')),
                                           tuple(town.field(c,'icon_colors',j) for j in range(6)))
            pixels = frames[frame]
        return (tuple(row[::-1] for row in pixels) if r['facing']>3 else pixels),palette


def pieces(game, assets):
    s, geo = game.s, game.geo
    forward, left, right = s.dir, (s.dir+6)%8, (s.dir+2)%8
    dx, dy = DELTAS[forward//2]
    result = []

    def add(x, y, direction, piece, offset=0, wall=None):
        wall = geo.wall(s, x, y, direction) if wall is None else wall
        if wall:
            _, _, _, col, row = assets.slices[piece]
            result.append((wall, piece, col+offset, row, x, y, direction))

    x, y = s.x+2*dx, s.y+2*dy
    for side, other, sign in ((left, right, -1), (right, left, 1)):
        sx, sy = DELTAS[side//2]
        previous = 0
        for lateral in range(4):
            cx, cy, offset = x+lateral*sx, y+lateral*sy, sign*lateral*2
            wall = geo.wall(s, cx, cy, forward)
            if not (0 <= cx < 16 and 0 <= cy < 16) and not geo.wall(s, cx, cy, other): previous = 0
            if previous and (wall or geo.wall(s, cx-sx, cy-sy, side)):
                add(cx-sx, cy-sy, forward, 9, offset-sign, previous)
            add(cx, cy, forward, 0, offset)
            previous = wall
    for side, piece, sign in ((left, 1, -1), (right, 2, 1)):
        sx, sy = DELTAS[side//2]
        for lateral in range(3):
            add(x+lateral*sx, y+lateral*sy, side, piece, sign*(2*lateral+bool(lateral)))
    for depth, front, count, span, side_pieces in ((1, 3, 3, 3, (4, 5)), (0, 6, 2, 7, (7, 8))):
        for side, piece, sign in ((left, side_pieces[0], -1), (right, side_pieces[1], 1)):
            sx, sy = DELTAS[side//2]
            for lateral in reversed(range(count)):
                cx, cy = s.x+depth*dx+lateral*sx, s.y+depth*dy+lateral*sy
                add(cx, cy, forward, front, sign*lateral*span)
                add(cx, cy, side, piece, sign*lateral*span)
    return result


def placements(game, assets):
    result = []
    for wall, piece, col, row, x, y, direction in pieces(game, assets):
        start, width, height, _, _ = assets.slices[piece]
        for index in range(width*height):
            tx, ty = col+index%width, row+index//width
            if 0 <= tx < 11 and 0 <= ty < 11:
                symbol = assets.wall_symbol(game.s, wall, start+index, tuple(getattr(game, 'walls_filed', ())))
                if symbol: result.append((tx, ty, symbol, wall, piece, start+index, x, y, direction))
    return result


def draw_view(frame, game, assets, area=False):
    s, geo = game.s, game.geo
    if geo.map is None or not game.vm.is3d(): return
    if area and not s.r0[0xFB]:
        x0, y0 = max(0, min(5, s.x-5)), max(0, min(5, s.y-5))
        for y in range(11):
            for x in range(11):
                mask = sum(1 << i for i in range(4) if geo.wall(s, x+x0, y+y0, i*2))
                frame.blit(24+x*8, 24+y*8, assets.border[4+mask])
        frame.blit(24+(s.x-x0)*8, 24+(s.y-y0)*8, assets.border[s.dir//2])
        return
    sky = assets.view_tables['sky'][s.r0[0xFD+int(geo.attr(s, s.x, s.y) >= 128)]]
    frame.rect(24, 24, 88, 44, sky); frame.rect(24, 68, 88, 2, 0); frame.rect(24, 70, 88, 42, 8)
    sky_pictures = [(252, 2, 7)]
    if geo.attr(s, s.x, s.y) < 128 and sky == 11:
        hour = s.r0[0xC9]
        if s.dir == 0: sky_pictures.insert(0, (250, 2, 2))
        if 1 <= hour <= 5:
            if s.dir == 2: sky_pictures.insert(0, (251, 9, 7-hour))
            elif s.dir == 4 and hour > 2: sky_pictures.insert(0, (251, hour-1, 7-hour))
        elif 13 <= hour <= 18:
            if s.dir == 6: sky_pictures.insert(0, (251, 2, hour-11))
            elif s.dir == 4 and hour < 16: sky_pictures.insert(0, (251, hour-6, hour-11))
    for rid, col, row in sky_pictures:
        frame.blit(8+col*8, 8+row*8, assets.picture('SKY', rid).parts[0].frames[0], transparent=13, clip=CLIP)
    for col, row, symbol, *_ in placements(game, assets):
        frame.blit(24+col*8, 24+row*8, assets.wall_tile(s, symbol, tuple(getattr(game, 'walls_filed', ()))), transparent=13)


def draw_frame(frame, game, assets, big=False, window=False):
    top = bytearray(assets.part('topEdgeTiles'))
    for col, index, bias in ((8, 0x1F9, 10), (19, 0x1FA, 6), (30, 0x1FB, 14)): top[col] = game.s.r0[index]+bias
    cells = [(x, 0, tile) for x, tile in enumerate(top)]
    cells += [(x, y, 4 if window and 15 <= y <= 17 else tile) for y, tile in enumerate(assets.part('leftEdgeTiles')) for x in (0, 39)]
    cells += [(x, y, 0) for x in range(40) for y in ((23,) if window else (16, 23))]
    if not big:
        cells += [(16, y, tile) for y, tile in enumerate(assets.view_tables['divider'])]
        cells += [(x, y, 0) for x in range(2, 15) for y in (2, 14)]
        cells += [(x, y+2, tile) for x, start in ((2, 0), (14, 13))
                  for y, tile in enumerate(assets.view_tables['insets'][start:start+13])]
    for x, y, tile in cells: frame.blit(x*8, y*8, assets.border[20+tile])


SPRITE_COLOURS = tuple(0 if colour == 13 else colour for colour in range(16))


def draw_portrait(frame, assets, head, body, dataset):
    for family, ident, y in (('HEAD', head, 24), ('BODY', body, 64)):
        if ident == 255: continue
        try: record = assets.picture(family, ident, dataset)
        except (KeyError, OSError): continue
        frame.blit(24, y, record.parts[0].frames[0], clip=CLIP)


def draw_picture(frame, game, assets, elapsed):
    display = dict(kind='PIC', id=60, dataset=game.s.dataset) if game.s.mode == 6 else game.vm.display
    kind, dataset = display.get('kind'), display.get('dataset', game.s.dataset)
    if kind == 'SPRIT':
        if not game.vm.is3d(): return
        distance = display.get('frame', 0)
        head = display['head'] if display.get('head') is not None else game.vm.m1(0x7EE1)
        if distance == 0 and not display.get('menu'):
            if head != 255: return draw_portrait(frame, assets, head, display.get('pic', 255), dataset)
            if display.get('pic', 255) != 255: kind, display = 'PIC', dict(display, kind='PIC', id=display['pic'])
        if kind == 'SPRIT':
            if display.get('id', 255) == 255: return
            try: parts = assets.picture('SPRIT', display['id'], dataset).parts
            except (KeyError, OSError): return
            if distance < len(parts):
                part = parts[distance]
                frame.blit(24+part.x*8, 24+part.y*8, part.frames[0], transparent=0, colours=SPRITE_COLOURS, clip=CLIP)
            return
    if kind == 'HEAD_BODY': return draw_portrait(frame, assets, display.get('head', 255), display.get('id', 255), dataset)
    if kind not in ('PIC', 'BIGPIC'): return
    try: record = assets.picture(kind, display['id'], display['dataset'])
    except (KeyError, OSError): return
    frames = [(part, pixels) for part in record.parts for pixels in part.frames]
    ticks = int(elapsed*100)
    duration = sum(max(1, part.delay or 1) for part, _ in frames)
    tick = ticks % duration
    chosen = frames[0]
    for part, pixels in frames:
        chosen = part, pixels
        tick -= max(1, part.delay or 1)
        if tick < 0: break
    part, pixels = chosen
    origin = 8 if kind == 'BIGPIC' else 24
    frame.blit(origin+part.x*8, origin+part.y*8, pixels)
    if kind == 'BIGPIC' and display['id']==121 and game.s.mode == 3 and not game.vm.is3d():
        marker=assets.combat_picture('CURSOR',1)[0]
        frame.blit((game.s.r0[0xC3]+1)*8,(game.s.r0[0xC4]+1)*8,marker,transparent=13)


def draw_party(frame, game, assets, col=17, selected=None):
    frame.text(col, 2, 'Name', assets); frame.text(33, 2, 'AC  HP', assets)
    for i, c in enumerate(game.s.party):
        raw = town.buffer(c)
        name = bytes(raw[1:1+min(15, raw[0])]).decode('cp437')
        colour = 15 if i == (game.s.sel if selected is None else selected) else 12 if not town.field(c, 'active') else 14 if town.field(c, 'side') else 11
        frame.text(col, i+4, name, assets, colour, 15)
        ac, hp = str(60-town.field(c, 'ac')), str(town.field(c, 'hp'))
        frame.text(35-len(ac), i+4, ac, assets, 10)
        frame.text(39-len(hp), i+4, hp, assets, 10)


STATUS_NAMES = ('Okay', 'Animated', 'tempgone', 'Running', 'Unconscious', 'Dying', 'Dead', 'Stoned', 'Gone')


SHEET_KINDS = ('CREATE_ROLL', 'CREATE_SAVE', 'CREATE_MODIFY')


def coin_list(decision):
    return bool(decision and decision['kind'] == 'VIEW_COIN' and decision['options'] is not None and 'window' not in decision['info'])


def sheet_view(controller):
    d, game = controller.session.decision, controller.session.game
    if not d: return None
    if d['kind'] == 'CREATE_VIEW' and 'status' in d['info']: return d['info'], None, None
    if coin_list(d):
        from .. import inventory, rules
        c = game.s.selc()
        copy = rules.character(bytes(c.b), tuple(bytes(i) for i in c.items), tuple(bytes(e) for e in c.effects))
        return inventory.sheet(game, copy), copy, None
    from .. import creation, inventory, rules, training
    creating = creation.PENDING in game.s.g
    if d['kind'] not in SHEET_KINDS+('CREATE_NAME',) or d['kind'] in ('CREATE_SAVE', 'CREATE_NAME') and not creating or icon_screen(controller): return None
    field = None
    if d['kind'] == 'CREATE_MODIFY':
        c = next((m for m in game.s.party if bytes(m.b[1:1+m.b[0]]).decode('cp437') == d['info'].get('name')), None)
        if c is None: return None
        raw, items, effects = bytes(c.b), tuple(bytes(i) for i in c.items), tuple(bytes(e) for e in c.effects)
        field = training.FIELD_LABELS.index(d['info']['field']) if d['info'].get('field') in training.FIELD_LABELS else None
    elif creation.PENDING in game.s.g: raw, items, effects = game.s.g[creation.PENDING]
    else: return None
    copy = rules.character(raw, items, effects)
    return inventory.sheet(game, copy), copy, field


def icon_screen(controller):
    from .. import creation
    d = controller.session.decision
    return bool(d and d['kind'] in ('CREATE_SAVE', 'CREATE_OVERWRITE', 'CREATE_FILE_NAME') and creation.PENDING in controller.session.game.s.g)


def draw_icon_screen(frame, game, assets):
    from .. import creation, rules
    c = rules.character(*game.s.g[creation.PENDING])
    frames, palette = assets.party_icon(*(town.field(c, k) for k in ('icon_head', 'icon_body', 'icon_size')),
                                        tuple(town.field(c, 'icon_colors', j) for j in range(6)))
    frame.rect(0, 0, 320, 192, 0); draw_frame(frame, game, assets, True, True)
    backdrop = assets.combat_picture('COMSPR', 25)[0]
    for row, label in ((6, 'old'), (12, 'new')):
        for col, pose in ((3, 0), (12, 1)):
            frame.blit(col*8, row*8, backdrop, transparent=0); frame.blit(col*8, row*8, frames[pose], transparent=0, colours=palette)
        frame.text(8, row, label, assets, 15); frame.text(3, row+4, 'ready   action', assets, 15)


def summary_screen(decision):
    text = str(decision['info'].get('message', '')) if decision and decision['kind'] == 'ACK' else ''
    return ' receives ' in text and summary_cut(text) > 0


def summary_cut(text):
    return min((i+1 for i in (text.find('. '), text.find('! ')) if i >= 0), default=0)


def share_window(decision):
    text = str(decision['info'].get('message', '')) if decision and decision['kind'] == 'ACK' else ''
    lines = text.splitlines()
    return lines if lines and all(' takes and hides ' in line for line in lines) else []


def bottom_query(controller):
    d = controller.session.decision
    if not d or not compact(d): return ''
    if d['info'].get('prompt') == 'Stop Resting? ': return 'Stop Resting? '
    if d['kind'] == 'COMBAT_LOOT' and d['info'].get('prompt') in ('Take:', 'Take: '): return 'Take: '
    if d['kind'] == 'MENU' and d['info'].get('door'): return 'Locked. '
    q = appraisal(d) or str(d['info'].get('query') or (d['info'].get('prompt', '') if d['kind'] in SHEET_KINDS[:2]+('CREATE_TRAIN', 'CREATE_SLOT') or yes_no_menu(d) else ''))
    return q if len(q)+sum(len(label)+1 for _, label in menu_items(d)) <= 41 else ''


YELLOW_QUERIES = frozenset(('Memorize These Spells?', 'Memorize these spells?', 'Scribe These Spells?', 'Scribe these spells?', 'quit TO DOS:',
                            'Drop from party?', 'Quit TO DOS', 'Quit to DOS', 'Game NOT saved.  Quit anyway?', 'Are you sure?', 'Abort Spell?'))


def query_colour(query):
    text = str(query).strip()
    return 14 if text in YELLOW_QUERIES or text.startswith('Overwrite ') or text.startswith('Drop ') and text.endswith(' forever?') else 13


def draw_sheet(frame, game, assets, info, char=None, field=None):
    from .. import rules, shop
    from ..creation import F
    from ..shop import I, COIN_NAMES
    party = game.s.party
    c = char or next((m for m in party if bytes(m.b[1:1+m.b[0]]).decode('cp437') == info.get('name')), None) or game.s.selc()
    b = c.b
    frame.rect(0, 0, 320, 192, 0)
    top = bytearray(assets.part('topEdgeTiles'))
    for col, index, bias in ((8, 0x1F9, 10), (19, 0x1FA, 6), (30, 0x1FB, 14)): top[col] = game.s.r0[index]+bias
    for x, tile in enumerate(top): frame.blit(x*8, 0, assets.border[20+tile])
    for y in (8, 16, 20, 23):
        for x in range(40): frame.blit(x*8, y*8, assets.border[20])
    for y, tile in enumerate(assets.view_tables['sheet_sides']):
        for x in (0, 39): frame.blit(x*8, y*8, assets.border[20+tile])
    for y, tile in enumerate(assets.view_tables['sheet_divider'], 9): frame.blit(19*8, y*8, assets.border[20+tile])
    white, green = 15, 10
    frame.text(1, 1, info['name'], assets, 11 if b[F['active']] else 12)
    frame.text(20, 1, 'Status:', assets, white)
    frame.text(27, 1, STATUS_NAMES[info['status']] if info['status'] < len(STATUS_NAMES) else '', assets, green)
    frame.text(1, 3, info['gender'], assets, white); frame.text(8, 3, '%d years' % info['age'], assets, white)
    frame.text(20, 3, 'Hit Points', assets, white)
    hp = str(info['hp_now']); frame.text(31, 3, hp, assets, 14 if info['hp_now'] < info['hp'] else green)
    frame.text(31+len(hp), 3, '/%d' % info['hp'], assets, green)
    frame.text(1, 4, info['alignment'], assets, white); frame.text(20, 4, info['race'], assets, white)
    frame.text(1, 5, info['description'], assets, white, 38)
    frame.text(1, 7, 'Level', assets, white); frame.text(7, 7, info['levels'], assets, white, 12)
    frame.text(20, 7, 'Experience %d' % info['experience'], assets, white)
    for i, label in enumerate(('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHA')):
        base, cur = b[F['abilities']+2*i], b[F['abilities']+2*i+1]
        frame.text(1, 9+i, label, assets, green); frame.text(5 if cur >= 10 else 6, 9+i, str(cur), assets, green)
        extra = i == 0 and cur == 18 and b[F['strength_extra']]
        if extra: frame.text(7, 9, '(%02d)' % (b[F['strength_extra']] % 100), assets, green)
        if cur != base or i == 0 and b[F['strength_extra']] != b[F['strength_extra_base']]: frame.text(12, 9+i, '*', assets, green)
    row = 9
    for kind, amount in enumerate(shop.coins(c)[1:7], 1):
        if amount: frame.text(20, row, COIN_NAMES[kind], assets, green); frame.text(38-len(str(amount)), row, str(amount), assets, green); row += 1
    ac = b[F['ac']]
    frame.text(1, 17, 'Armor Class', assets, white)
    frame.text(16 if 1 <= ac <= 50 or 61 <= ac <= 69 else 17 if 51 <= ac <= 60 else 15, 17, str(info['ac_shown']), assets, green)
    frame.text(20, 17, 'Encumbrance', assets, white); frame.text(33, 17, '%5d' % info['encumbrance'], assets, green)
    frame.text(1, 18, 'THAC0', assets, white); frame.text(16, 18, '%2d' % info['thac0_shown'], assets, green)
    frame.text(20, 18, 'Movement', assets, white); frame.text(35, 18, '%3d' % info['move'], assets, green)
    frame.text(1, 19, 'Damage', assets, white); frame.text(11, 19, '%7s' % info['damage'], assets, green)
    worn = {}
    for raw in c.items:
        if raw[I['readied']]: worn.setdefault(rules.tables().base_item(raw[I['type']])[rules.SLOT], raw)
    for slot, row in ((0, 21), (2, 22)):
        if slot in worn: frame.text(1, row, shop.item_name(game, bytearray(worn[slot])).strip(), assets, green, 38)
    if field is not None and field < 6:
        cur = b[F['abilities']+2*field+1]
        frame.text(5 if cur >= 10 else 6, 9+field, str(cur), assets, 13)
        if field == 0 and cur == 18 and b[F['strength_extra']]: frame.text(7, 9, '(%02d)' % (b[F['strength_extra']] % 100), assets, 13)
    elif field == 6: frame.text(1, 1, info['name'], assets, 13)
    elif field == 7: frame.text(31, 3, str(info['hp_now']), assets, 13)


def draw_vertical(frame, controller, assets, decision=None):
    v = vertical(controller, decision); left, top, right, bottom = v['window']; info = v['info']
    width = right-left+1
    frame.rect(left*8, (top-(1 if info.get('header') else 0))*8, width*8, (bottom-top+1+(1 if info.get('header') else 0))*8, 0)
    if info.get('header'): frame.text(left, top-1, str(info['header']), assets, 13, width)
    if info.get('title'): frame.rect(8, 8, 304, (top-1)*8, 0)
    if info.get('title') and controller.session.decision['kind'] == 'VIEW_ITEMS' and str(info['title']).endswith("'s Items"):
        who, char = str(info['title'])[:-8], controller.session.game.s.selc()
        frame.text(1, 1, who+"'s", assets, 11 if char is None or town.field(char, 'active') else 12, 38)
        frame.text(len(who)+4, 1, 'Items', assets, 10, max(0, 35-len(who)))
    elif info.get('title'): frame.text(1, 1, str(info['title']), assets, 15, 38)
    if info.get('caption'): frame.text(1, 3, str(info['caption']), assets, 15, 38)
    if v.get('spell'):
        char = spell_character(controller)
        from ..camp import name
        who = name(char)
        frame.rect(8, 8, 304, 24, 0)
        frame.text(1, 1, who+"'s", assets, 11 if town.field(char, 'active') else 12, 38)
        frame.text(len(who)+4, 1, 'Spells '+v['spell'][1], assets, 10, 35-len(who))
        if v['spell'][0] != 1:
            for col in range(40): frame.blit(col*8, 16, assets.border[20])
            for col in (0, 39): frame.blit(col*8, 24, assets.border[23])
    indent = info.get('indent', 0)
    for row, line in enumerate(str(info.get('rows', '')).split('\n')[:bottom-top+1] if info.get('rows') else [], top):
        frame.text(left, row, line, assets, 11 if line[:1].strip() else 10, width)
    for row, (index, label) in enumerate(v['visible'], top):
        if index is None: frame.text(left, row, label, assets, 13, width)
        elif index == controller.selected:
            lead = len(label)-len(label.lstrip())
            frame.text(left+indent+lead, row, label.strip(), assets, 0, width-indent-lead, background=15)
        else: frame.text(left+indent, row, label, assets, 10, width-indent)
    if info.get('slots'):
        frame.rect(8, 136, 304, 48, 0)
        for row, line in enumerate(str(info['slots']).splitlines()[:5], 18): frame.text(1, row, line, assets, 10, 38)
    if decision is not None: return
    frame.rect(0, 192, 320, 8, 0)
    if info.get('message') and showing_message(controller):
        frame.text(0, 24, str(info['message']), assets, 10, 40); return
    draw_words(frame, controller, assets, v)


def draw_word(frame, assets, col, word, selected=False, script=False, row=24):
    if selected: frame.text(col, row, word, assets, 0, background=15); return
    frame.text(col, row, word, assets, 10)
    for n, ch in enumerate(word):
        if ch.isascii() and (ch.isalnum() and n == 0 if script else ch.isupper() or ch.isdigit()): frame.text(col+n, row, ch, assets, 15)


def draw_words(frame, controller, assets, v):
    frame.text(0, 24, v['query'], assets, 13)
    col = len(v['query']); at = controller.horizontal_choice if controller.horizontal_choice < len(v['words']) else 0
    for n, (word, _) in enumerate(v['words']):
        lead = len(word)-len(word.lstrip())
        draw_word(frame, assets, col+lead, word.strip(), n == at); col += len(word)+1


START_PAUSE = 0.4


def pause(controller, scaled=True):
    from ..creation import DELAY, game_setting
    return game_setting(controller.session.game.s, DELAY)*0.1*(controller.effect_scale if scaled else 1)


def page_prompt(controller):
    following = controller.lines[(controller.text_page+1)*6:][:1]
    damage = following and following[0].startswith('  ') and (' is hit FOR ' in following[0] or following[0].rstrip().endswith(' dies.'))
    return ('press <enter>/<return> to continue', 15) if damage else ('Press any key to continue', 13)


def revealed(controller):
    slow = getattr(controller, 'slow', None)
    if not slow: return None
    from ..creation import DELAY, game_setting
    count, kept, at = slow
    step = game_setting(controller.session.game.s, DELAY)*0.003*controller.effect_scale
    if step <= 0: return None
    shown = kept+int((controller.clock()-at)/step)
    return None if shown >= sum(len(line) for line in controller.lines[:min(count, controller.text_page*6+6)]) else shown


def showing_message(controller):
    return controller.clock()-controller.decided_at < pause(controller)


def script_text(game):
    import re
    from ..camp import name
    names = {name(char) for char in game.s.chars()}
    lines, colours = [], []
    text = ''.join(game.vm.out[game.vm.text_start:])
    for paragraph in text.rstrip().splitlines():
        hit = re.fullmatch(r'(.+?)(?: is hit FOR \d+ points of Damage\.| dies\.) *', paragraph.lstrip())
        damage = hit and hit[1] in names
        past = damage and lines and len(lines) % 6 == 0 and len(lines[-1]) == 38
        wrapped = town.wrapped_text(('  ' if past else '')+paragraph.lstrip() if damage else paragraph)
        lines.extend(wrapped)
        colours.extend([15 if damage else getattr(game.vm, 'text_color', 10)]*len(wrapped))
    return lines, colours


OLD_CONTINUE, NEW_CONTINUE = 'PRESS BUTTON OR RETURN TO CONTINUE.', 'PRESS <ENTER>/<RETURN> TO CONTINUE'


def menu_items(decision):
    if not decision or decision['options'] is None: return []
    from ..combat import FIGHT_KEYS
    slots = decision['kind'] == 'CREATE_SLOT' and decision['info'].get('prompt') in ('Save Which Game: ', 'Load Which Game: ')
    items = [(i, str(value) if value is not None else 'Exit') for i, value in enumerate(decision['options'])
             if value not in ('char-up', 'char-down', 'char-first', *FIGHT_KEYS) and not (slots and value in (None, 'Exit'))]
    if decision['kind'] == 'MENU' and len(items) == 1 and items[0][1] == OLD_CONTINUE: items = [(items[0][0], NEW_CONTINUE)]
    return items


def leave_question(decision):
    if not decision or decision['options'] is None or [label for _, label in menu_items(decision)] != ['Yes', 'No']: return None
    text = str(decision['info'].get('offer', ''))+str(decision['info'].get('prompt', ''))
    at = text.find('Do you want to go back')
    return (text[:at], text[at:], 'retrieve your money' not in text[at:]) if at >= 0 else None


def yes_no_menu(decision):
    return bool(decision and decision['kind'] != 'MENU' and decision['options'] is not None
                and [label for _, label in menu_items(decision)] == ['Yes', 'No'] and 'char-up' not in decision['options']
                and decision['info'].get('prompt') != 'Abort spell? ' and not leave_question(decision))


def script_who(decision):
    return bool(decision and decision['kind'] == 'WHO' and 'at' in decision['info'] and decision['options'] is not None)


def pick_who(decision):
    return bool(decision and decision['kind'] == 'CREATE_WHO' and decision['options'] and decision['options'][-1] == 'Exit'
                and decision['info'].get('prompt') == 'Pick Character ')


def menu_screen(controller):
    d, game = controller.session.decision, controller.session.game
    return bool(d and game.s.mode == 0 and d['info'].get('action') != 'main-menu' and not sheet_view(controller)
                and (pick_who(d) or yes_no_menu(d) and bottom_query(controller)))


def draw_question(frame, controller, assets):
    d = controller.session.decision
    frame.rect(0, 192, 320, 8, 0)
    if pick_who(d):
        frame.text(0, 24, 'Pick Character ', assets, 13); frame.text(15, 24, 'Select', assets, 0, background=15); frame.text(22, 24, 'Exit', assets, 10)
        return
    query = bottom_query(controller); frame.text(0, 24, query, assets, query_colour(query)); col = len(query)
    for index, label in menu_items(d):
        draw_word(frame, assets, col, label, index == controller.selected, d['kind'] == 'MENU'); col += len(label)+1


def script_list(decision):
    return bool(decision and decision['kind'] == 'MENU' and decision['info'].get('vertical') and 'window' not in decision['info'])


def appraisal(decision):
    if not decision or decision['kind'] != 'LIST': return ''
    prompt = str(decision['info'].get('prompt', ''))
    return 'Appraise : ' if prompt == 'Appraise : ' else 'You can : ' if ' is Valued at ' in prompt else ''


def draw_appraisal(frame, game, assets, decision):
    from .. import shop
    char, prompt = game.s.party[game.s.sel], str(decision['info']['prompt'])
    money = shop.coins(char); gems, jewels = money[shop.GEMS], money[shop.JEWELRY]
    if prompt != 'Appraise : ': gems, jewels = (gems+1, jewels) if prompt.startswith('The Gem') else (gems, jewels+1)
    frame.rect(8, 8, 304, 176, 0)
    frame.text(1, 1, shop.member_name(char), assets, 11, 38)
    frame.text(1, 7, 'You have a fine collection of:', assets, 15)
    frame.text(1, 9, '' if not gems else '%d Gem' % gems + ('s' if gems > 1 else ''), assets, 15)
    frame.text(1, 10, '' if not jewels else '%d piece%s of Jewelry' % (jewels, 's' if jewels > 1 else ''), assets, 15)
    if prompt != 'Appraise : ': frame.text(1, 12, prompt, assets, 15, 38)


def draw_petition(frame, game, assets, verdict):
    from .. import shop
    from ..creation import F
    char = max((c for c in game.s.party if verdict.startswith(shop.member_name(c))), key=lambda c: len(shop.member_name(c)), default=None)
    if char is None: return
    name, order = shop.member_name(char), char.b[F['knight_order']]
    frame.rect(8, 8, 304, 176, 0)
    frame.text(19-len(name)//2, 3, name, assets, 10)
    frame.text(7, 5, 'is petitioning to become a', assets, 10)
    frame.text(10, 7, 'Knight Of The ' + {1: 'sword', 2: 'rose'}.get(order, ''), assets, 10)
    base = 19 if order == 1 else 20
    if verdict.endswith(('is too inexperienced.', 'is too inexperienced')): col = base-(len(name)+21)//2
    elif verdict.endswith('does not qualify.'): col = base-(len(name)+18)//2
    else:
        col = 19-(len(name)+13)//2
        frame.text(10, 11, verdict[len(name)+len(' may become a '):], assets, 10); verdict = name+' may become a'
    frame.text(col, 9, verdict, assets, 10, 38-col)


def compact(decision):
    if spell_kind(decision) or pick_who(decision): return False
    if coin_list(decision): return False
    if appraisal(decision): return True
    return bool(decision and decision['options'] is not None and not decision['info'].get('vertical') and 'window' not in decision['info']
                and decision['kind'] not in ('CREATE_MENU', 'WHO', 'LIST')
                and sum(len(label)+1 for _, label in menu_items(decision)) <= 41)


def spell_kind(decision):
    if not decision: return None
    kind, prompt = decision['kind'], decision['info'].get('prompt')
    if not prompt and decision['info'].get('title') in ('to Memorize', 'to Scribe'): prompt = 'Spells '+decision['info']['title']
    if kind in ('SPELL', 'COMBAT_SPELL', 'CREATE_SPELL'):
        return {'Cast': (0, 'in Memory', 'Cast'), 'memorize': (1, 'in Grimoire', 'Memorize'),
                'Scribe': (3, 'on Scrolls', 'Scribe'), 'Learn': (4, 'to Choose', 'Learn'),
                'Spells to Memorize': (5, 'to Memorize', ''), 'Spells to Scribe': (6, 'to Scribe', '')}.get(prompt)
    if kind == 'VIEW_ITEMS':
        return {'Spells on Scroll': (2, 'on Scroll', 'Cast'), 'Spells in Memory': (0, 'in Memory', '')}.get(prompt)
    return None


def pending_question(decision):
    if not yes_no_menu(decision): return None
    title = {'memorize these spells?': 'to Memorize', 'scribe these spells?': 'to Scribe'}.get(str(decision['info'].get('prompt', '')).strip().lower())
    return dict(decision, kind='SPELL', options=['Exit'], info=dict(title=title)) if title else None


def spell_character(controller):
    game, d = controller.session.game, controller.session.decision
    actor = d['info'].get('actor', -1) if d['kind'] == 'COMBAT_SPELL' else -1
    return game.s.chars()[actor] if actor >= 0 else game.s.selc()


def spell_rows(controller, items, decision=None):
    from .. import camp, magic, rules
    game, d = controller.session.game, decision or controller.session.decision
    char, (kind, _, command) = spell_character(controller), spell_kind(d)
    counts = []
    if d['info'].get('spell_ids'):
        ids = [int(value) for value in str(d['info']['spell_ids']).split()]
    elif kind == 0:
        held = magic.castable(char, d['kind'] == 'COMBAT_SPELL'); ids = [value for value, _ in held]; counts = [n for _, n in held]
    elif kind == 1: ids = camp.memorizable(char, camp.tables(game.assets))
    elif kind in (3, 6):
        copy = rules.character(bytes(char.b), tuple(bytes(i) for i in char.items), tuple(bytes(e) for e in char.effects))
        ids = magic.scroll_spells(copy, kind == 6)
    elif kind == 2:
        at = getattr(controller, 'view_item', None)
        raw = char.items[at] if at is not None and at < len(char.items) else None
        ids = [raw[n] for n in magic._spell_bytes(raw) if raw[n]] if raw is not None else []
    elif kind == 4:
        ids = [next(row.id for row in magic.table() if row.cast_class == 3 and row.name == label) for _, label in items]
    else:
        copy = rules.character(bytes(char.b), (), ())
        base = camp.F['memorized']
        copy.b[base:base+camp.MEMORY_SLOTS] = bytes(value & 127 if value > 127 else 0 for value in camp.memory(char))
        held = magic.castable(copy); ids = [value | 128 for value, _ in held]; counts = [n for _, n in held]
    if not command:
        items = [(-1, magic.spell(value).name+(' (%d)' % counts[n] if counts and counts[n] > 1 else '')) for n, value in enumerate(ids)]
    if len(ids) != len(items):
        ids = []
        for _, label in items:
            label = label.lstrip(' *').split(' (')[0]
            matches = [row for row in magic.table() if row.name == label]
            ids.append(matches[0].id if matches and len({row.level for row in matches}) == 1 else None)
    nodes, previous = [], 0 if kind in (2, 3, 6) else None
    table = controller.assets.view_tables['spell_headings']
    for (index, label), value in zip(items, ids):
        if value is not None:
            level = magic.spell(value).level
            if previous is None or (level != previous if kind in (2, 3, 6) else level > previous):
                at = level*41; nodes.append((None, table[at+1:at+1+table[at]].decode('cp437')))
            previous = level
        prefix = ' *' if value is not None and value > 127 or label.startswith(' *') else '  '
        nodes.append((index, prefix+label.lstrip(' *')))
    return nodes


def vertical(controller, decision=None):
    decision = decision or controller.session.decision; info = decision['info']
    items = menu_items(decision)
    exit_index = items[-1][0] if items and items[-1][1] == 'Exit' else None
    if exit_index is not None: items = items[:-1]
    spell = spell_kind(decision)
    if spell: info = dict(info, window='1 5 38 '+('15' if spell[0] == 1 else '22'), menu=spell[2], query='Choose Spell: ' if spell[2] else '')
    if coin_list(decision): info = dict(info, window='20 9 38 15', query=str(info.get('prompt', '')), menu=' Select')
    left, top, right, bottom = map(int, info.get('window', '1 17 38 22').split())
    if script_list(decision): top = min(22, top+len(town.wrapped_text(str(info.get('prompt', '')))))
    if info.get('header'): top += 1
    rows = bottom-top+1
    nodes = spell_rows(controller, items, decision) if spell else items
    position = next((n for n, (i, _) in enumerate(nodes) if i == controller.selected), None)
    first = min(getattr(controller, 'spell_top', 0), max(0, len(nodes)-rows))
    if position is not None and not first <= position < first+rows:
        first = min(position//rows*rows, max(0, len(nodes)-rows))
    page = first//rows
    labels = next((n for n, (i, _) in enumerate(nodes) if i is not None), len(nodes))
    words = [(info.get('menu', 'Select'), dict(keysym=str(info.get('menu', 'Select')).strip()[:1].lower(), char=str(info.get('menu', 'Select')).strip()[:1].lower()))] if info.get('menu', 'Select') else []
    if first+rows < len(nodes): words.append(('Next', dict(keysym='n', char='n')))
    if first > labels: words.append(('Prev', dict(keysym='p', char='p')))
    if exit_index is not None: words.append(('Exit', dict(keysym='e', char='e')))
    return dict(items=items, page=page, rows=rows, visible=nodes[first:first+rows], window=(left, top, right, bottom),
                words=words, exit=exit_index, query=str(info.get('query', '')), info=info, spell=spell, nodes=nodes, first=first)


def own_window(decision):
    return bool(decision and decision['options'] is not None and int(str(decision['info'].get('window', '1 17')).split()[1]) < 16)


def is_list(controller):
    d = controller.session.decision
    if spell_kind(d): return True
    return bool(d and d['options'] is not None and d['kind'] != 'MOVE' and d['info'].get('action') != 'main-menu'
                and not script_who(d) and not pick_who(d) and not compact(d) and menu_items(d))


def is_vertical(controller):
    d = controller.session.decision
    return is_list(controller) and (spell_kind(d) is not None or own_window(d) or not controller.session.game.s.g.get('cok.battle', {}).get('active'))


KEYPAD = {'1':'End', '2':'Down', '3':'Next', '4':'Left', '5':'Clear', '6':'Right', '7':'Home', '8':'Up', '9':'Prior', '\\':'Home'}


class Controller:
    def __init__(self, session, *, save_root=None, presentation=True):
        self.session, self.save_root = session, save_root
        self.assets = Assets(session.game.assets.root)
        self.selected = self.page = self.text_page = self.spell_top = 0
        self.horizontal_choice = 0
        self.entry = self.error = ''
        self.area_map = self.move_mode = self.quit_requested = self.file_menu = False
        self.view_item = None
        self.file_mode, self.file_message, self.file_wait = 'game', '', ('', 0.0)
        self.generation = 0
        self.rest_active = self.autosave_enabled = False
        self.held_keys = []
        self.effect_scale = 1.0
        self.decision_observer = None
        self.aim_cell = None
        self.aim_manual = self.aim_blank = False
        self.aim_view = self.aim_saved = None
        self.report, self.report_at = [], 0.0
        self.presentation_enabled, self.hold_event, self.hold_until, self.hold_seq = presentation, None, 0.0, 0
        import time
        self.clock = time.monotonic
        from collections import deque
        self.sound_on, self.sound_seq, self.sound_events, self.report_sounded = True, 0, deque(maxlen=64), 0
        self.story, self.story_chars, self.slow = '', 0, None
        self.capture_text()
        self.slow = None
        self.queue()

    plus_options = ('effect_scale', 'sound')
    plus_file = 'cok-plus.json'
    plus_tabs = ('journal', 'map', 'help')

    def apply_plus(self, settings):
        self.set_effect_scale(settings.options['effect_scale'])
        self.sound_on = settings.options.get('sound', True)

    def emit(self, command):
        if self.sound_on: self.sound_seq += 1; self.sound_events.append((self.sound_seq, command))

    @property
    def text(self):
        return ' '.join(self.lines)

    @property
    def files(self):
        from types import SimpleNamespace
        from .. import creation
        return SimpleNamespace(root=Path(self.save_root) if self.save_root else creation.save_directory(None))

    def remember(self): pass
    def autosave(self): pass
    def presenting(self): return False

    def queue(self):
        game = self.session.game
        if not self.presentation_enabled: return None
        if getattr(game, 'presentation', None) is None:
            from collections import deque
            game.presentation = deque()
        return game.presentation

    def held(self):
        queue, now = self.queue(), self.clock()
        if self.hold_event is not None and now < self.hold_until: return self.hold_event
        ended, self.hold_event = self.hold_event is not None, None
        while queue:
            event = queue.popleft()
            if event.get('kind') != 'script-hold': continue
            delay = pause(self) if event.get('message') else event['delay']
            if delay <= 0: continue
            self.hold_event, self.hold_seq = event, self.hold_seq+1
            self.hold_until = (self.hold_until if 0 <= now-self.hold_until < 0.05 else now)+delay
            break
        if ended and self.hold_event is None: self.report_at = self.decided_at = now
        return self.hold_event

    def drop_holds(self):
        queue = self.queue()
        if queue or self.hold_event is not None: self.report_at = self.decided_at = self.clock()
        if queue: queue.clear()
        self.hold_event = None

    def set_effect_scale(self, value):
        if type(value) not in (int, float) or not 0 <= value <= 10: raise ValueError('effect scale outside 0..10')
        self.effect_scale = value

    def capture_text(self):
        vm = self.session.game.vm
        self.lines, self.line_colours = script_text(self.session.game)
        script_lines, story = self.lines, ''.join(vm.out[vm.text_start:])
        decision = self.session.decision
        self.white_from = None
        shown = (decision['kind'], str(decision['info'].get('prompt') or decision['info'].get('title') or '')) if decision and is_list(self) else None
        if shown and shown != getattr(self, 'list_shown', None): self.spell_top = 0
        if shown: self.list_shown = shown
        if is_vertical(self): self.horizontal_choice = 0
        if decision and decision['kind'] == 'CAMP_RESTING': self.rest_info = decision['info']
        if script_who(decision): self.lines, self.line_colours = [], []
        elif pick_who(decision): pass
        elif script_list(decision):
            self.lines = town.wrapped_text(str(decision['info'].get('prompt', ''))); self.line_colours = [10]*len(self.lines)
        elif leaving := leave_question(decision):
            sentence, question, shown = leaving
            self.lines = town.wrapped_text((sentence if shown else '')+question); self.line_colours = [10]*len(self.lines)
            if shown:
                left = len(sentence.replace(' ', ''))
                for index, line in enumerate(self.lines):
                    inked = len(line.replace(' ', ''))
                    if left < inked:
                        col = next(n for n in range(len(line)+1) if len(line[:n].replace(' ', '')) == left and line[n:n+1] != ' ')
                        self.white_from = (index, col); self.line_colours[index+1:] = [15]*(len(self.lines)-index-1); break
                    left -= inked
        elif decision and decision['options'] is not None:
            for name in ('prompt', 'offer', 'message'):
                if (text := decision['info'].get(name)) and not (name == 'prompt' and bottom_query(self) == str(text)):
                    self.lines += town.wrapped_text(str(text))
        self.text_page = 0
        self.decided_at = self.clock()
        camp = bool(decision) and decision['kind'] == 'CAMP_MENU' and decision['info'].get('prompt') == 'Camp'
        self.camp_intro = camp and (not getattr(self, 'was_camping', False) or getattr(self, 'camp_intro', False))
        self.was_camping = self.session.game.s.mode == 2
        if self.session.game.s.g.get('cok.battle',{}).get('active'): self.lines = []
        if spell_kind(decision): self.lines = []
        if decision and decision['info'].get('prompt') == 'Stop Resting? ': self.lines = []
        if own_window(decision): self.lines = []
        if coin_list(decision): self.lines = []
        was_ground, view = getattr(self, 'ground_aim', False), getattr(self, 'aim_view', None)
        self.aim_cell, self.aim_manual, self.aim_view, self.ground_aim, self.aim_blank = None, False, None, False, False
        if decision and decision['kind']=='TARGET':
            from ..combat import Battle
            battle=Battle(self.session.game)
            self.aim_cell=battle.position(battle.data['actor'])
            self.aim_view=battle.data['view']
            if was_ground and self.aim_saved is not None:
                self.aim_cell,self.aim_view,self.aim_blank,self.horizontal_choice=self.aim_saved,view,True,2
                self.center_aim(0)
            self.aim_word()
        elif decision and decision['kind']=='COMBAT_SPELL_AIM':
            data=self.session.game.s.g['cok.battle']
            self.aim_cell,self.aim_view,self.ground_aim=tuple(data['aim']),view or tuple(data['aim_view']),True
            self.center_aim(2)

        total = sum(len(line) for line in script_lines)
        kept = min(total, self.story_chars) if story.startswith(self.story) else 0
        self.slow = (len(script_lines), kept, self.clock()) if self.lines is script_lines and kept < total else None
        self.story, self.story_chars = story, total

    def poll(self):
        d = self.session.decision
        if (d and d['kind']=='COMBAT_AUTO' and report_step(self) is None and
                self.clock()-self.decided_at >= AUTO_BEAT*self.effect_scale):
            self.choose(d['options'].index('Continue'))
        elif d and d['kind']=='CAMP_RESTING' and self.clock()-self.decided_at >= REST_BEAT*self.effect_scale:
            self.choose(d['options'].index('Continue'))

    def center_aim(self, margin):
        x,y=self.aim_cell; ox,oy=self.aim_view
        if abs(x-ox-3)>margin: ox=max(0,min(43,x-3))
        if abs(y-oy-3)>margin: oy=max(0,min(18,y-3))
        self.aim_view=ox,oy

    def aim_options(self):
        options=['Next','Prev','Manual']
        if not self.aim_blank and self.aim_choice() is not None: options.append('Target')
        return options+['Center','Exit']

    def aim_word(self):
        words=self.aim_options()
        if self.horizontal_choice>=len(words): self.horizontal_choice=0
        return words,self.horizontal_choice

    def aim_choice(self):
        from ..combat import Battle
        battle=Battle(self.session.game)
        for index,label in enumerate(self.session.decision['options']):
            if '#' not in label: continue
            who=int(label.rsplit('#',1)[1])
            if self.aim_cell in battle.cells(who) or not battle.record(who)['size'] and battle.position(who)==self.aim_cell: return index
        return None

    def aim_key(self, keysym, char):
        from ..combat import Battle, DX, DY
        battle=Battle(self.session.game); options=self.session.decision['options']
        self.error=''
        if self.aim_manual:
            if char!='\\': keysym=KEYPAD.get(char,keysym)
            direction={'Up':0,'Prior':1,'Right':2,'Next':3,'Down':4,'End':5,'Left':6,'Home':7}.get(keysym)
            if direction is not None:
                x,y=self.aim_cell
                self.aim_cell=max(0,min(49,x+DX[direction])),max(0,min(24,y+DY[direction]))
                self.center_aim(2); return False
            if keysym in ('space','Clear'): self.center_aim(0); return False
            choice,enter=self.aim_choice(),keysym in ('Return','KP_Enter')
            if keysym!='Escape' and choice is not None and (enter or char.lower()=='t'): return self.choose(choice)
            if keysym=='Escape' or choice is None and (enter or char.lower()=='e'):
                self.aim_cell=self.aim_saved; self.center_aim(0)
                self.aim_manual,self.aim_blank,self.horizontal_choice=False,True,2
            return False
        words,at=self.aim_word()
        if char in ('4','6'): keysym,char=KEYPAD[char],''
        if keysym in ('Left','Right'): self.horizontal_choice=(at+(1 if keysym=='Right' else -1))%len(words); return False
        key='e' if keysym=='Escape' else words[at][0].lower() if keysym in ('Return','KP_Enter') else char.lower()
        word=next((n for n,label in enumerate(words) if label[0].lower()==key),None)
        if word is None: return False
        if keysym!='Escape': self.horizontal_choice=word
        if key in ('n','p'):
            targets=battle.targets(battle.data['actor'],127,allies=True)
            cells=[battle.position(i) for i in targets]
            if cells:
                at=cells.index(self.aim_cell) if self.aim_cell in cells else -1 if key=='n' else 0
                self.aim_cell=cells[(at+(1 if key=='n' else -1))%len(cells)]
                self.center_aim(3)
            self.aim_blank=False
        elif key=='m':
            if 'Ground' in options:
                from ..combat import direction_to
                start=self.aim_cell; self.choose(options.index('Ground'))
                for _ in range(64):
                    d=self.session.decision
                    if not d or d['kind']!='COMBAT_SPELL_AIM' or self.aim_cell==start: break
                    self.choose(direction_to(*self.aim_cell,*start))
                self.aim_saved=start
                return True
            self.aim_manual,self.aim_saved=True,self.aim_cell
        elif key=='c': self.center_aim(0)
        elif key=='e': return self.choose(options.index('Exit'))
        elif key=='t': return self.choose(self.aim_choice())
        self.aim_word(); return False

    def choose(self, index):
        log = self.session.game.__dict__.setdefault('combat_report', []); seen = len(log)
        decision, s = self.session.decision, self.session.game.s
        if decision and decision['kind'] == 'VIEW_ITEMS' and decision['info'].get('prompt') == 'Items':
            self.view_item = index if index < len(s.selc().items) else None
        if compact(decision):
            indexes = [i for i, _ in menu_items(decision)]
            if index in indexes: self.horizontal_choice = indexes.index(index)
        if decision and decision['info'].get('action') == 'main-menu': self.menu_row = index
        before = (s.x, s.y, s.dir, tuple(s.r0[0xC3:0xC5]))
        queued = len(getattr(self.session.game, 'script_sounds', ()))
        fighting = s.g.get('cok.battle', {}).get('active')
        self.hold_resting = bool(decision) and (decision['kind'] in ('CAMP_REST', 'CAMP_RESTING') or decision['info'].get('prompt') == 'Stop Resting? ')
        self.drop_holds(); self.queue()
        self.session.step(index)
        if getattr(self.session.game, 'exit_game', False): self.quit_requested = True
        if decision and decision['kind'] == 'CREATE_SLOT' and decision['options'][index] in tuple('ABCDEFGHIJ'):
            prompt = decision['info'].get('prompt', '')
            if prompt in ('Save Which Game: ', 'Load Which Game: '):
                self.file_wait = ('Saving...Please Wait' if prompt.startswith('Save') else 'Loading...Please Wait', self.clock())
        if decision and decision['kind'] == 'MOVE':
            label = decision['options'][index] if decision['options'] else None
            after = (s.x, s.y, s.dir, tuple(s.r0[0xC3:0xC5]))
            if (label == 'forward' and after[:2] != before[:2] or label in ('turn-left', 'turn-right') and after[2] != before[2]
                    or 'north' in decision['options'] and after[3] != before[3]): self.emit(10)
        for command in getattr(self.session.game, 'script_sounds', ())[queued:]: self.emit(command)
        self.report_sounded = 0
        self.report, self.report_at = log[seen:], self.clock()
        if not fighting and s.g.get('cok.battle', {}).get('active'): self.report.insert(0, dict(kind='begin'))
        self.report_for = (self.session.decision or {}).get('i')
        following = self.session.decision
        self.selected = (following or {}).get('info', {}).get('start', 0)
        if script_who(following): self.selected = min(s.sel, len(following['options'])-1)
        if pick_who(following): self.selected = min(s.sel, len(following['options'])-2)
        if following and following['info'].get('action') == 'main-menu':
            self.selected = min(getattr(self, 'menu_row', 0), len(following['options'])-1)
        carried = self.horizontal_choice
        if compact(following):
            items = menu_items(following)
            if following['kind'] in ('MENU', 'COMBAT_ACTION') or self.horizontal_choice >= len(items): self.horizontal_choice = 0
            if yes_no_menu(following): self.horizontal_choice = 1
            if items and 'start' not in following['info']: self.selected = items[self.horizontal_choice][0]
        else: self.horizontal_choice = 0
        if following and following['kind'] == 'TARGET': self.horizontal_choice = carried
        self.page = self.selected // 6; self.entry = self.error = ''
        self.capture_text()
        if self.session.error: self.error = str(self.session.error)
        if self.decision_observer: self.decision_observer()
        return True

    def loadable(self):
        from .. import creation
        game = self.session.game
        if self.save_root: game.roster_directory = Path(self.save_root)
        return creation.available_slots(game)

    def can_load(self):
        d = self.session.decision
        return bool(d and d['info'].get('action') == 'main-menu' and not self.session.game.s.party and self.loadable())

    def file_items(self):
        if self.file_mode == 'load': return [(c.lower(), c) for c in self.loadable()]
        if self.file_mode != 'game': return [(c.lower(), c) for c in 'ABCDEFGHIJ']
        return [('s', 'Save')] + ([('l', 'Load')] if self.can_load() else []) + [('q', 'Quit'), ('r', 'Resume')]

    def file_key(self, keysym, char):
        from .. import creation
        game, decision = self.session.game, self.session.decision
        key = char.lower()
        if keysym == 'Escape' or self.file_mode == 'game' and (key in ('r', 'e') or keysym in ('Return', 'KP_Enter')):
            self.file_menu = False; return False
        try:
            if self.file_mode == 'game':
                if key == 'q': self.quit_requested = True
                elif key == 's':
                    from .._cli import at_outpost
                    if not decision or not (decision['kind'] in ('MOVE', 'CAMP_MENU') or at_outpost(self.session)):
                        raise ValueError('Save from exploration, camp or the Outpost menu.')
                    self.file_mode, self.file_message = 'save', ''
                elif key == 'l' and self.can_load(): self.file_mode, self.file_message = 'load', ''
                return False
            if len(key) != 1 or key not in 'abcdefghij': return False
            slot = key.upper()
            if self.save_root: game.roster_directory = Path(self.save_root)
            if self.file_mode == 'save':
                creation.save_game(game, slot)
                if journal := getattr(self, 'journal', None): journal.save(slot, selected=True)
                self.file_menu, self.file_wait = False, ('Saving...Please Wait', self.clock())
                return False
            if slot not in self.loadable(): return False
            self.choose(game.menu_ids.index(creation.LOAD))
            self.choose(self.session.decision['options'].index(slot))
            if self.session.error: raise self.session.error
            self.file_menu, self.file_wait = False, ('Loading...Please Wait', self.clock())
            self.generation += 1
            return True
        except (OSError, ValueError, KeyError, town.retained.Halt) as error:
            self.file_message = str(error)
            return False

    def wait_line(self):
        text, at = getattr(self, 'file_wait', ('', 0.0))
        return text if text and self.clock()-at < WAIT_HOLD else ''

    def key(self, keysym, char=''):
        if self.held() is not None:
            self.drop_holds()
            return False
        if holding(self):
            self.report = []
            return False
        if keysym == 'F10':
            self.file_menu = not self.file_menu
            self.file_mode, self.file_message = 'game', ''; return False
        if self.file_menu:
            return self.file_key(keysym, char)
        decision = self.session.decision
        if not decision: return False
        if keysym == ' ': keysym = 'space'
        if self.text_page*6+6 < len(self.lines):
            if keysym not in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R'):
                self.text_page += 1
                if self.slow: self.slow = (self.slow[0], sum(len(line) for line in self.lines[:self.text_page*6]), self.clock())
            return False
        options, kind = decision['options'], decision['kind']
        if options is not None and keysym in options: return self.choose(options.index(keysym))
        if kind == 'COMBAT_LOOT' and decision['info'].get('prompt', '') in ('', 'Take:', 'Take: ') and compact(decision):
            keysym = KEYPAD.get(char, keysym)
            taking = decision['info'].get('prompt') in ('Take:', 'Take: ')
            if taking and keysym == 'Prior' and 'Items' in options: return self.choose(options.index('Items'))
            if keysym in ('Up', 'Down'):
                command = 'char-up' if keysym == 'Up' else 'char-down'
                return self.choose(options.index(command)) if command in options else False
            if keysym in ('Home', 'End', 'Next', 'Prior', 'Clear'):
                return self.choose(options.index('char-first')) if not taking and 'char-first' in options else False
        if kind=='CAMP_REST' and keysym in ('Up','Down','Left','Right'):
            if keysym in ('Up','Down'): return self.choose(options.index('Add' if keysym=='Up' else 'Subtract'))
            unit = decision['info']['field']+(1 if keysym=='Left' else -1)
            unit = 2 if unit>4 else 4 if unit<2 else unit
            return self.choose(options.index({4:'Days',3:'Hours',2:'Mins'}[unit]))
        if kind=='CAMP_RESTING': return self.choose(options.index('Stop'))
        if kind=='COMBAT_AUTO' and keysym=='space': return self.choose(options.index('Manual'))
        if kind=='COMBAT_AUTO' and (keysym.lower() == 'alt-m' or char == '2'): return self.choose(options.index('Magic'))
        if kind == 'TARGET': return self.aim_key(keysym,char)
        if kind in ('COMBAT_MOVE','COMBAT_SPELL_AIM'):
            if kind == 'COMBAT_MOVE' or char != '\\': keysym = KEYPAD.get(char, keysym)
            direction = {'Up':0,'Prior':1,'Right':2,'Next':3,'Down':4,'End':5,'Left':6,'Home':7}.get(keysym)
            if direction is not None: return self.choose(direction)
            if kind=='COMBAT_MOVE':
                if keysym in ('Return','KP_Enter') or char.lower()=='d': return self.choose(options.index('Done'))
                if keysym=='Escape': return self.choose(options.index('Undo'))
                return False
            if keysym in ('space', 'Clear'): self.center_aim(0); return False
            word = 'Target' if 'Target' in options else 'Exit'
            if keysym == 'Escape': return self.choose(options.index('Exit'))
            if keysym in ('Return','KP_Enter') or char.lower() == word[0].lower(): return self.choose(options.index(word))
            return False
        if options is None:
            limit = decision['info'].get('max') if kind == 'NUMBER' else None
            if keysym in ('Return', 'KP_Enter', 'Escape'):
                value = self.entry
                if limit is not None: value = 0 if keysym == 'Escape' or not value else int(value)
                elif kind == 'NUMBER':
                    import re
                    if not re.fullmatch(r' *[+-]?[0-9]+', value) or not 0 <= int(value) <= 65536: self.entry = ''; return False
                    value = int(value) & 65535
                return self.choose(value)
            if keysym == 'BackSpace': self.entry = self.entry[:-1]
            elif limit is not None:
                if len(char) == 1 and char in '0123456789':
                    self.entry = (self.entry+char)[:6]
                    if int(self.entry) > limit: self.entry = str(limit)
            elif len(char) == 1 and ' ' <= char <= 'z' and len(self.entry) < (6 if kind == 'NUMBER' else decision['info'].get('max_length', 40)):
                self.entry += char
            return False
        if kind == 'MOVE':
            if keysym == 'F2' or char.lower() == 'a':
                if 'north' in options: return False
                if not self.session.game.s.r0[0xFB]: self.area_map = not self.area_map
                else: self.error = 'Not Here'
                return False
            if char.lower() == 'm': self.move_mode = True; return False
            if self.move_mode and (char.lower() == 'e' or keysym=='Escape'): self.move_mode = False; return False
            if self.move_mode: keysym = KEYPAD.get(char, keysym)
            command = {'Up': 'forward', 'Left': 'turn-left', 'Right': 'turn-right', 'Down': 'turn-around'}.get(keysym)
            if 'north' in options: command = {'Up':'north','Prior':'northeast','Right':'east','Next':'southeast','Down':'south','End':'southwest','Left':'west','Home':'northwest'}.get(keysym)
            command = command or {'l':'look', 's':'search', 'e':'camp', 'v':'view', 'c':'cast'}.get(char.lower())
            if command in options: return self.choose(options.index(command))
            return False
        items = menu_items(decision)
        if not items: return False
        if decision['info'].get('action') == 'main-menu':
            keysym = KEYPAD.get(char, keysym)
            if keysym in ('Up', 'Down'): self.selected = (self.selected+(-1 if keysym == 'Up' else 1)) % len(items); return False
            return self.choose(self.selected) if keysym in ('Return', 'KP_Enter', 'space') or char.lower() == 's' else False
        if script_who(decision):
            if keysym in ('Up', 'Down'): self.selected = (self.selected+(-1 if keysym == 'Up' else 1)) % len(options); return False
            if keysym in ('Return', 'KP_Enter', 'Escape') or char.lower() in ('s', 'e'): return self.choose(self.selected)
            return False
        if pick_who(decision):
            members = len(options)-1; keysym = KEYPAD.get(char, keysym)
            if keysym in ('Up', 'Down'): self.selected = (self.selected+(-1 if keysym == 'Up' else 1)) % members; return False
            if keysym in ('Home', 'End', 'Next', 'Prior', 'Clear'): self.selected = 0; return False
            if keysym in ('Return', 'KP_Enter') or char.lower() == 's': return self.choose(self.selected)
            if keysym == 'Escape' or char.lower() == 'e': return self.choose(members)
            return False
        if script_list(decision) and keysym == 'Escape': return self.choose(self.selected)
        if is_list(self):
            v = vertical(self); key = char.lower(); nodes, rows = v['nodes'], v['rows']
            if char in ('8', '2', '9', '3', '4', '6'): keysym, key = KEYPAD[char], ''
            words = [word.strip() for word, _ in v['words']]
            at = self.horizontal_choice if self.horizontal_choice < len(words) else 0
            if keysym in ('Left', 'Right'):
                if len(words) > 1: self.horizontal_choice = (at+(1 if keysym == 'Right' else -1)) % len(words)
                return False
            if keysym in ('Return', 'KP_Enter'):
                if not words: return self.choose(self.selected)
                key = words[at][:1].lower()
            if key:
                hit = next((n for n, word in enumerate(words) if word[:1].lower() == key), None)
                if hit is None: return False
                self.horizontal_choice = hit
            down = key == 'n' or keysym == 'Next' and 'Next' in words
            if down or key == 'p' or keysym == 'Prior' and 'Prev' in words:
                first = max(0, min(len(nodes)-rows, v['first']+(rows if down else -rows)))
                position = next((n for n, (i, _) in enumerate(nodes) if i == self.selected), v['first'])
                last = min(first+rows, len(nodes))-1; spot = min(first+position-v['first'], last)
                for _ in range(rows):
                    index = nodes[spot][0]
                    if index is not None and index >= 0: self.selected = index; break
                    spot += 1 if down else -1
                    if not first <= spot <= last: spot = first if down else last
                self.spell_top = first; return False
            if keysym in ('Up', 'Down'):
                indexes = [i for i, _ in v['visible'] if i is not None and i >= 0]
                if indexes:
                    pos = indexes.index(self.selected) if self.selected in indexes else 0
                    self.selected = indexes[(pos+(-1 if keysym == 'Up' else 1)) % len(indexes)]
                return False
            if key == 'e' or keysym == 'Escape': return self.choose(v['exit']) if v['exit'] is not None else False
            return self.choose(self.selected) if key else False
        if compact(decision) and char in ('4', '6', '8', '2') and not any(label.startswith(char) for _, label in items):
            if char in '46' or 'char-up' in options: keysym, char = KEYPAD[char], ''
        if compact(decision) and keysym in ('Up', 'Down') and 'char-up' in options:
            return self.choose(options.index('char-up' if keysym == 'Up' else 'char-down'))
        if compact(decision) and keysym in ('Home', 'End', 'Next', 'Prior') and 'char-first' in options:
            return self.choose(options.index('char-first'))
        if keysym in ('Up', 'Left', 'Down', 'Right'):
            indexes = [i for i, _ in items]
            position = indexes.index(self.selected) if self.selected in indexes else 0
            self.selected = indexes[(position+(-1 if keysym in ('Up', 'Left') else 1))%len(items)]
            self.page = self.selected//6
            return False
        if keysym in ('Return', 'KP_Enter'): return self.choose(self.selected)
        if keysym == 'Escape' and kind != 'MENU':
            exit_index = next((i for i, value in enumerate(options) if value is None or str(value).lower() in ('exit', 'leave', 'cancel')), None)
            if exit_index is not None: return self.choose(exit_index)
        if char:
            hit = next((i for i, label in items if label[:1].lower() == char.lower()), None)
            if hit is not None: return self.choose(hit)
        return False


def combat_view(controller):
    data = controller.session.game.s.g['cok.battle']
    focus = data['actor']
    decision = controller.session.decision
    if decision and decision['kind']=='COMBAT_SPELL_AIM':
        return controller.aim_view or data['aim_view']
    if data.get('flash'):
        x,y=data['flash']['aim']; return max(0,min(43,x-3)),max(0,min(18,y-3))
    if decision and decision['kind'] == 'TARGET' and controller.aim_cell is not None:
        return controller.aim_view
    if focus == data['actor']: return data['view']
    r = data['actors'][max(0,focus)]
    return max(0,min(43,r['x']-3)),max(0,min(18,r['y']-3))


FILE_QUERY = dict(save='Save Which Game: ', load='Load Which Game: ')
WAIT_HOLD = 0.5


def draw_file_menu(frame, controller, assets):
    if wait := controller.wait_line():
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, wait, assets, 10)
    if not controller.file_menu: return
    frame.rect(0, 192, 320, 8, 0)
    query = FILE_QUERY.get(controller.file_mode, '')
    frame.text(0, 24, query, assets, 13); col = len(query)
    for _, label in controller.file_items():
        draw_word(frame, assets, col, label); col += len(label)+1
    if controller.file_message:
        frame.rect(8, 136, 304, 48, 0)
        for row, line in enumerate(town.wrapped_text(controller.file_message)[:6], 17): frame.text(1, row, line, assets, 14, 38)


def draw_battle(controller, elapsed=0):
    from ..combat import Battle, name, line
    import textwrap
    from .. import shop
    game,assets,decision = controller.session.game,controller.assets,controller.session.decision
    battle,frame = Battle(game),Frame(); data = battle.data
    top = bytearray(assets.part('topEdgeTiles'))
    for column,cell,bias in ((8,0x1F9,10),(19,0x1FA,6),(30,0x1FB,14)): top[column] = game.s.r0[cell]+bias
    for x,tile in enumerate(top): frame.blit(x*8,0,assets.border[20+tile])
    for x in (0,22,39):
        for y,tile in enumerate(assets.view_tables['combat_sides']): frame.blit(x*8,y*8,assets.border[20+tile])
    for x in range(40): frame.blit(x*8,176,assets.border[20])
    ox,oy = combat_view(controller)
    progress = report_step(controller)
    step = controller.report[progress[0]] if progress is not None else None
    bolt = None
    if isinstance(step,dict) and step['kind']=='move' and step.get('actors'):
        x,y = step['actors'][step['actor']][:2]
        if abs(x-ox-3)>2 or abs(y-oy-3)>2: ox,oy = max(0,min(43,x-3)),max(0,min(18,y-3))
    if isinstance(step,dict) and step['kind']=='bolt':
        sx,sy=step['actors'][step['actor']][:2]
        path=list(line(sx,sy,*step['aim']))
        cell,part=divmod(int(progress[1]/BOLT_STEP)*4,24); cell=min(cell,len(path)-1)
        x,y,_=path[cell]; nx,ny,_=path[min(cell+1,len(path)-1)]
        if not (ox<=x<ox+7 and oy<=y<oy+7): ox,oy=max(0,min(43,x-3)),max(0,min(18,y-3))
        bolt=(x,y,(nx-x)*part,(ny-y)*part,int(progress[1]/BOLT_STEP)%4)
    wild,random = assets.combat_picture('DUNGCOM' if game.vm.is3d() else 'WILDCOM',1),assets.combat_picture('RANDCOM',1)
    for y in range(7):
        for x in range(7):
            tile = battle.terrain(battle.tile(x+ox,y+oy),3)
            pixels = wild[tile] if tile<len(wild) else random[tile-34] if 34<=tile<40 else None
            if pixels is None: raise ValueError('Champions combat tile %d has no loaded image'%tile)
            frame.blit(8+x*24,8+y*24,pixels)
    target_mode=decision and decision['kind']=='TARGET'
    spell_aim=decision and decision['kind']=='COMBAT_SPELL_AIM'
    cursor=data['aim'] if spell_aim else controller.aim_cell if target_mode else battle.position(data['actor'])
    marked=battle.occupancy().get(cursor,-1)
    if target_mode and marked<0 and (choice:=controller.aim_choice()) is not None:
        marked=int(decision['options'][choice].rsplit('#',1)[1])
    size=1 if spell_aim or target_mode and controller.aim_manual or marked<0 else battle.record(marked)['size']
    if cursor and (target_mode or spell_aim or int(elapsed*100)%80<30):
        for dx,dy in battle.footprint(size or 1):
            frame.blit(8+(cursor[0]+dx-ox)*24,8+(cursor[1]+dy-oy)*24,
                       assets.combat_picture('COMSPR',25)[0],transparent=0,clip=(8,8,176,176))
    places = step['actors'] if isinstance(step,dict) and 'actors' in step else [(r['x'],r['y'],r['size']) for r in data['actors']]
    for i,(x,y,size) in enumerate(places):
        if not size or i>=len(data['actors']): continue
        pixels,palette = assets.combat_icon(game,i,1 if isinstance(step,dict) and step['kind']=='attack' and step.get('actor')==i else 0)
        frame.blit(8+(x-ox)*24,8+(y-oy)*24,pixels,transparent=0,colours=palette,clip=(8,8,176,176))
    if bolt:
        x,y,dx,dy,frame_no=bolt
        px=8+(x-ox)*24+dx; py=8+(y-oy)*24+dy
        ident=(6 if step['spell']==51 else 5)+(128 if frame_no>1 else 0)
        pixels=assets.combat_picture('COMSPR',ident)[0]
        if frame_no in (1,2): pixels=tuple(row[::-1] for row in pixels)
        frame.blit(px,py,pixels,transparent=0,clip=(8,8,176,176))
    i = marked if target_mode and marked>=0 else data['actor']; c,r = battle.chars[i],battle.record(i)
    if not target_mode or marked>=0:
        frame.text(23,1,name(c),assets,12 if not town.field(c,'active') else 14 if town.field(c,'side') else 11,16)
        frame.text(23,3,'Hitpoints',assets,10)
        frame.text(33,3,str(town.field(c,'hp')),assets,14 if town.field(c,'hp')<town.field(c,'hp_max') else 10)
        frame.text(23,5,'AC',assets,10); frame.text(26,5,str(60-town.field(c,'ac')),assets,10)
        weapon=battle.weapon(i)
        lines=textwrap.wrap(shop.item_name(game,bytearray(weapon)).strip(),16) if weapon is not None else []
        for y,text in enumerate(lines[:3],7): frame.text(23,y,text,assets,10,16)
        if battle.disabled(i): frame.text(23,9+len(lines[:3]),'(Helpless)',assets,15,16)
        elif r['casting']: frame.text(23,9+len(lines[:3]),'(Casting)',assets,15,16)
    if isinstance(step,str) and step in BOTTOM_LINE: frame.text(0,24,step,assets,10)
    elif isinstance(step,str):
        frame.rect(184,80,128,96,0)
        for y,text in enumerate(textwrap.wrap(step,16)[:6],11): frame.text(23,y,text,assets,10,16)
    elif step and step['kind']=='attack':
        frame.rect(184,80,128,96,0)
        frame.text(23,10,step['attacker'],assets,step['attacker_colour'],16)
        frame.text(23,11,step['lead'],assets,10,16)
        frame.text(23,12,step['target'],assets,step['target_colour'],16)
        row=13
        for text in textwrap.wrap(step['result'],16)[:3]: frame.text(23,row,text,assets,10,16); row+=1
        if 'down' in step:
            row+=1
            frame.text(23,row,step['target'],assets,12,16); frame.text(23,row+1,'goes down',assets,10,16)
            if step['down']=='Dying': frame.text(23,row+2,'and is Dying',assets,10,16)
            elif step['down']=='killed':
                frame.text(23,row+2,step['target'],assets,12,16); frame.text(23,row+3,'is killed',assets,10,16)
    if isinstance(step,dict) and step['kind']=='begin': frame.text(0,24,'A battle begins...',assets,10)
    if isinstance(step,dict) and step['kind']=='move' and step.get('left') is not None and holding(controller):
        frame.text(0,24,'Move/Attack, Move Left = %d '%step['left'],assets,10)
    if decision and decision['kind']=='COMBAT_AUTO': decision = None
    if holding(controller): decision = None
    if decision:
        items = menu_items(decision)
        if decision['kind']=='COMBAT_MOVE':
            label='Move/Attack, Move Left = %d'% (r['movement']//2)
            if decision['info'].get('prompt') and showing_message(controller):
                frame.text(0,24,str(decision['info']['prompt']),assets,10,40)
            else:
                frame.text(0,24,label,assets,13)
                frame.text(len(label)+1,24,'Done',assets,0,background=15)
        elif spell_aim:
            frame.text(0,24,'(Use Cursor keys) ',assets,13)
            frame.text(18,24,'Target' if 'Target' in decision['options'] else 'Exit',assets,0,background=15)
        elif target_mode:
            if controller.aim_manual:
                frame.text(0,24,'(Use Cursor keys) ',assets,13)
                frame.text(18,24,'Target' if controller.aim_choice() is not None else 'Exit',assets,0,background=15)
            else:
                frame.text(0,24,'Aim:',assets,13); col=4
                words=controller.aim_options(); at=controller.horizontal_choice if controller.horizontal_choice<len(words) else 0
                for n,label in enumerate(words):
                    draw_word(frame,assets,col,label,n==at); col+=len(label)+1
            distance=list(line(*battle.position(data['actor']),*cursor))[-1][2]//2
            if 'spell' not in decision['info']: frame.text(0,23,'Range = %d'%distance,assets,10,40)
        elif compact(decision):
            query = bottom_query(controller); frame.text(0,24,query,assets,query_colour(query)); col = len(query)
            for index,label in items:
                draw_word(frame,assets,col,label,index == controller.selected); col += len(label)+1
        else:
            frame.rect(184,72,128,96,0)
            v = vertical(controller)
            for y,(index,label) in enumerate(v['visible'],10):
                selected = index == controller.selected
                frame.text(23,y,label,assets,0 if selected else 10,15,background=15 if selected else 0)
            draw_words(frame, controller, assets, v)
        if decision['kind']=='ACK' and decision['info'].get('item'):
            frame.rect(184,80,128,96,0)
            for y,text in enumerate(textwrap.wrap(str(decision['info'].get('prompt','')),16)[:6],11): frame.text(23,y,text,assets,10,16)
            frame.text(0,23,'Item:',assets,10); frame.text(5,23,str(decision['info']['item']).strip(),assets,10,35)
        elif not target_mode and not spell_aim and decision['kind'] not in ('COMBAT_ACTION','COMBAT_CONFIRM','COMBAT_MOVE'):
            frame.text(0,23,str(decision['info'].get('prompt','')),assets,15,40)
    pending=controller.session.decision or {}
    spell=(casting_spell(controller.report,progress[0]) if progress else None) or (
        pending['info'].get('spell') if pending.get('kind') in ('TARGET','COMBAT_SPELL_AIM') else None)
    if spell:
        from .. import magic
        frame.text(0,23,'Spell:'+magic.spell(spell).name,assets,10,40)
    if controller.error: frame.text(0,23,controller.error,assets,14,40)
    draw_file_menu(frame, controller, assets)
    return frame


def render(controller, assets=None, elapsed=0):
    assets = controller.assets
    game, decision = controller.session.game, controller.session.decision
    event = controller.held()
    if event is not None and not controller.file_menu: return render_hold(controller, event, elapsed)
    if decision and decision['kind'] == 'CAMP_RESTING': controller.poll(); decision = controller.session.decision
    if game.s.g.get('cok.battle',{}).get('active') and not spell_kind(decision) and not own_window(decision):
        controller.poll()
        if game.s.g.get('cok.battle',{}).get('active'): return draw_battle(controller,elapsed)
        decision = controller.session.decision
    if decision and decision['info'].get('action') == 'main-menu':
        frame = menu.render(game, controller.selected)
        if game.s.party: draw_party(frame, game, controller.assets, col=1)
        frame.text(len(game.assets.text('query')), 24, game.assets.text('select').strip(), controller.assets, 0, background=15)
        if decision['info'].get('message') and showing_message(controller):
            frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, str(decision['info']['message']), controller.assets, 10, 40)
    elif menu_screen(controller):
        frame = menu.render(game, -1)
        if game.s.party: draw_party(frame, game, controller.assets, col=1, selected=controller.selected if pick_who(decision) else None)
        draw_question(frame, controller, assets)
    else:
        frame = Frame()
        pending = pending_question(decision)
        top_list = bool(pending) or is_vertical(controller) and vertical(controller)['window'][1] < 16
        window = bool(pending) or top_list and vertical(controller)['window'][3] > 16
        big = game.s.mode != 6 and game.vm.display.get('kind') == 'BIGPIC' or top_list
        draw_frame(frame, game, assets, big, window)
        if not big:
            draw_party(frame, game, assets, selected=controller.selected if script_who(decision) or pick_who(decision) else None)
            if game.s.mode != 6 and not game.vm.display.get('blank'): draw_view(frame, game, assets, controller.area_map)
        if not top_list: draw_picture(frame, game, assets, elapsed)
        shown = revealed(controller) if elapsed > 0 else None
        for row, line in enumerate([] if top_list else controller.lines[controller.text_page*6:controller.text_page*6+6], 17):
            at = controller.text_page*6+row-17
            if shown is not None:
                if at >= controller.slow[0]: continue
                line = line[:max(0, shown-sum(len(text) for text in controller.lines[:at]))]
            colour = controller.line_colours[at] if at < len(controller.line_colours) else getattr(game.vm, 'text_color', 10)
            frame.text(1, row, line, assets, colour, 38)
            if getattr(controller, 'white_from', None) and controller.white_from[0] == at:
                frame.text(1+controller.white_from[1], row, line[controller.white_from[1]:], assets, 15, 38-controller.white_from[1])
        if getattr(controller, 'camp_intro', False): frame.rect(8, 136, 304, 48, 0); frame.text(1, 18, 'The party makes camp...', assets, 10)
        if decision and (decision['kind'] in ('CAMP_REST', 'CAMP_RESTING') or decision['info'].get('prompt') == 'Stop Resting? '):
            draw_rest_time(frame, assets, getattr(controller, 'rest_info', {}) if decision['info'].get('prompt') == 'Stop Resting? ' else decision['info'])
        if controller.text_page*6+6 < len(controller.lines): text, colour = page_prompt(controller); frame.text(0, 24, text, assets, colour)
        elif decision and decision['kind'] != 'CAMP_RESTING':
            items = menu_items(decision)
            if decision['kind'] == 'MOVE':
                labels='Move Encamp' if 'north' in decision['options'] else 'Move Area Cast View Encamp Search Look'
                col = 0
                for word in ('Exit' if controller.move_mode else labels).split(): draw_word(frame, assets, col, word); col += len(word)+1
            elif script_who(decision):
                query = str(decision['info'].get('prompt', ''))+' '
                frame.text(0, 24, query, assets, 13, 40); frame.text(len(query), 24, 'Select', assets, 0, background=15)
            elif pending: draw_vertical(frame, controller, assets, pending); draw_question(frame, controller, assets)
            elif pick_who(decision) or compact(decision): draw_question(frame, controller, assets)
            elif items:
                draw_vertical(frame, controller, assets)
            else:
                prompt = str(decision['info'].get('prompt', ''))
                at = len(prompt)+(0 if decision['kind'] == 'NUMBER' and 'max' in decision['info'] else 1)
                frame.text(0, 24, prompt, assets, 13 if prompt == 'Character name: ' else 10, 40)
                if controller.entry and at < 40: frame.text(at, 24, controller.entry, assets, 15, 40-at)
        if not big: draw_location(frame, game, assets)
    if decision and decision['kind'] == 'ALTER_SPEED' and 'speed' in decision['info'] and not controller.error:
        frame.text(1, 18, 'Game Speed = %d (0=fastest 9=slowest)' % decision['info']['speed'], assets, 10, 38)
    if summary_screen(decision):
        frame = Frame(); draw_frame(frame, game, assets, True, True)
        text = str(decision['info']['message']); cut = summary_cut(text)
        rest = text[cut:].strip().removesuffix(' experience points.')
        for row, line in ((3, text[:cut]), (5, rest), (7, 'experience points.')):
            frame.text(1, row, line, assets, 10, 38)
        frame.text(0, 24, 'press <enter>/<return> to continue', assets, 15)
        return frame
    if share_window(decision):
        import textwrap
        frame = Frame(); draw_frame(frame, game, assets, True, True)
        for n, line in enumerate(share_window(decision)):
            for i, part in enumerate(textwrap.wrap(line, 30)): frame.text(5, 5+2*n+i, part, assets, 10, 30)
        frame.text(0, 24, 'press <enter>/<return> to continue', assets, 15)
        return frame
    if decision and decision['kind'] == 'CREATE_TRAIN' and decision['info'].get('levels'):
        frame.rect(8, 8, 304, 176, 0)
        who = str(decision['info'].get('character', ''))
        frame.text(4, 4, who, assets, 11); frame.text(len(who)+4, 4, ' will become:', assets, 10)
        for n, part in enumerate(str(decision['info']['levels']).split('; ')):
            frame.text(6, 5+n, ('    ' if n == 0 else 'and ')+part, assets, 10, 33)
    if decision and decision['kind'] == 'ACK' and decision['info'].get('item') and not summary_screen(decision):
        frame.text(1, 22, str(decision['info']['item']).strip(), assets, 10, 38)
    if appraisal(decision): draw_appraisal(frame, game, assets, decision)
    if decision and decision['kind'] == 'CREATE_KNIGHT': draw_petition(frame, game, assets, str(decision['info'].get('prompt', '')))
    sheet = sheet_view(controller)
    if sheet: draw_sheet(frame, game, assets, *sheet)
    elif icon_screen(controller): draw_icon_screen(frame, game, assets)
    if coin_list(decision): draw_vertical(frame, controller, assets)
    if decision and decision['info'].get('service') == 'view':
        c = game.s.selc()
        frame.rect(8, 8, 304, 120, 0)
        raw = town.buffer(c)
        frame.text(1, 2, bytes(raw[1:1+raw[0]]).decode('cp437'), assets)
        for row, (label, value) in enumerate(zip(('STR','INT','WIS','DEX','CON','CHA'),
                (town.field(c,'abilities',i*2+1) for i in range(6))), 4):
            frame.text(1, row, '%s %2d' % (label,value), assets,10)
        frame.text(20, 4, 'HP %d/%d' % (town.field(c,'hp'), town.field(c,'hp_max')), assets,10)
        frame.text(20, 5, 'AC %d' % (60-town.field(c,'ac')), assets,10)
        frame.text(20, 6, 'Age %d' % town.field(c,'age',width=2), assets,10)
        frame.text(20, 7, 'XP %d' % town.field(c,'experience',width=4), assets,10)
    if controller.error:
        frame.rect(8,136,304,48,0)
        for row, line in enumerate(town.wrapped_text(controller.error),17): frame.text(1,row,line,assets,14,38)
    draw_file_menu(frame, controller, assets)
    return frame


def draw_location(frame, game, assets):
    s = game.s
    if s.mode == 3: return
    direction = ('N','NE','E','SE','S','SW','W','NW')[(s.dir+s.r0[0x1FF]*(2 if s.r0[0xE6] else 1))%8]
    location = ('' if s.r0[0xFB] else '%d,%d ' % (s.x,s.y))+direction+' %02d:%02d' % (s.r0[0xC9],s.r0[0xC8]*10+s.r0[0xC7])
    location += ' camping' if s.mode == 2 else ' search' if game.vm.m1(0x7ECA) & 1 else ''
    frame.text(17, 15, location, assets, 10, 22)


def draw_rest_time(frame, assets, info):
    frame.rect(8, 136, 304, 8, 0); frame.text(1, 17, 'Rest Time:', assets, 10)
    for col, key, unit in ((12, 'days', 4), (15, 'hours', 3), (18, 'minutes', 2)):
        frame.text(col, 17, '%02d' % info[key], assets, 15 if info.get('field') == unit else 10)
        if key != 'minutes': frame.text(col+2, 17, ':', assets, 10)


def render_hold(controller, event, elapsed=0):
    from types import SimpleNamespace
    import copy
    live, assets, s = controller.session.game, controller.assets, event['state']
    geo = copy.copy(live.geo); geo.map = event['map']
    vm = SimpleNamespace(display=event['display'], out=[event['text']], text_start=0, text_color=event['colour'],
                         is3d=lambda: bool(s.r0[0xE6]), m1=lambda address: s.r1[address-0x7C00])
    game = SimpleNamespace(s=s, vm=vm, geo=geo, assets=live.assets, walls_filed=event['walls_filed'])
    frame = Frame(); big = s.mode != 6 and vm.display.get('kind') == 'BIGPIC'
    draw_frame(frame, game, assets, big, False)
    if not big:
        draw_party(frame, game, assets)
        if s.mode != 6 and not vm.display.get('blank'): draw_view(frame, game, assets, controller.area_map)
    draw_picture(frame, game, assets, elapsed)
    lines, colours = script_text(game); first = max(0, (len(lines)-1)//6*6)
    if event.get('message'):
        who, text = event['message']; resting = getattr(controller, 'hold_resting', False); top = 18 if resting else 17
        waiting = controller.session.decision; info = waiting['info'] if waiting and waiting['kind'] == 'CAMP_RESTING' else getattr(controller, 'rest_info', None)
        if resting and info: draw_rest_time(frame, assets, info)
        char = next((c for c in s.party if bytes(c.b[1:1+c.b[0]]).decode('cp437') == who), None)
        frame.text(1, top+1, who, assets, 11 if char is None or town.field(char, 'active') and not town.field(char, 'side') else 14 if town.field(char, 'active') else 12, 38)
        lines, colours, first = [''] * (top-15) + town.wrapped_text(text), [10] * 6, 0
    for row, (line, colour) in enumerate(zip(lines[first:first+6], colours[first:first+6]), 17): frame.text(1, row, line, assets, colour, 38)
    if not big: draw_location(frame, game, assets)
    return frame


REST_BEAT = 0.2
AUTO_BEAT = 0.3
MOVE_HOLD = 0.15


BOLT_STEP = 0.03


def report_hold(entry, result=START_PAUSE):
    if isinstance(entry, dict) and entry['kind'] == 'move': return MOVE_HOLD
    if isinstance(entry, dict) and entry['kind'] == 'bolt':
        from ..combat import line
        x, y = entry['actors'][entry['actor']][:2]
        return max(1, len(list(line(x, y, *entry['aim']))) - 1) * 6 * BOLT_STEP
    return result*RESULT_FEEL


RESULT_FEEL = 5.0


def report_step(controller):
    if not controller.report or controller.effect_scale <= 0: return None
    left = (controller.clock()-controller.report_at)/controller.effect_scale
    for index, entry in enumerate(controller.report):
        hold = report_hold(entry, pause(controller, False))
        if left < hold: return index, max(0.0, left)
        left -= hold
    return None


def casting_spell(report, at):
    cast = lambda e: isinstance(e,str) and e.endswith(' Casts a Spell')
    for k in range(at, -1, -1):
        e = report[k]
        if cast(e) or isinstance(e,dict) and e['kind']=='bolt': break
        if isinstance(e,dict) or e=='Spell Aborted' and k<at: return None
    else: return None
    for e in report[k+cast(report[k]):]:
        if isinstance(e,dict): return e['spell'] if e['kind']=='bolt' else None
        if cast(e): return None
    return None


def holding(controller):
    if report_step(controller) is None: return False
    if getattr(controller, 'report_for', None) != (controller.session.decision or {}).get('i'): return False
    data = controller.session.game.s.g.get('cok.battle', {})
    return any(not (isinstance(e, dict) and e['kind'] == 'move' and e.get('actor') == data.get('actor')) for e in controller.report)


BOTTOM_LINE = frozenset(('Guarding', 'Escape is blocked', 'Nothing Happens...', 'Already been targeted', 'Cannot target yourself',
                         'Camp Only Spell', 'Your Teammate is Dying', 'Not with that weapon', 'The air clears a little...', 'Spell Aborted',
                         'Magic On', 'Magic Off',
                         'The acid drains away..', 'OverLoaded'))


SOUND_COMMANDS = tuple(range(2, 13))


def step_sounds(entry):
    import re
    if isinstance(entry, str):
        if entry in BOTTOM_LINE: return []
        if re.search(r' (Goes Down(, and is Dying)?|is killed|Is destroyed|is disrupted|explodes[.!])$', entry): return [5]
        if re.search(r' takes \d+ .*damage', entry): return [3]
        if re.search(r' is [A-Z]', entry): return [4]
        return []
    kind = entry.get('kind')
    if kind == 'move': return [10]
    if kind == 'attack':
        hit = 'Miss' not in str(entry.get('result', ''))
        return ([7] if hit else [9]) + ([5] if 'down' in entry else [])
    if kind == 'bolt':
        return [{47: 11, 51: 8}.get(entry.get('spell'), 2)]
    return []


def due_sounds(controller):
    progress = report_step(controller)
    upto = len(controller.report) if progress is None else progress[0]+1
    for entry in controller.report[controller.report_sounded:upto]:
        for command in step_sounds(entry): controller.emit(command)
    controller.report_sounded = max(controller.report_sounded, upto)


def report_line(controller):
    step = report_step(controller)
    return None if step is None else step[0]


def walk_keys(cursor, cell):
    from ..combat import direction_to, DX, DY
    keys, (x, y) = [], cursor
    names = ('Up', 'Prior', 'Right', 'Next', 'Down', 'End', 'Left', 'Home')
    while (x, y) != cell and len(keys) < 63:
        d = direction_to(x, y, *cell); keys.append(dict(keysym=names[d], char='')); x, y = x+DX[d], y+DY[d]
    return keys or [dict(keysym='Return', char='')]


def layout(controller):
    decision = controller.session.decision
    regions = []
    result = dict(regions=regions, selected=controller.selected, roster_selected=controller.session.game.s.sel,
                  revision=[decision and decision['i'], decision and decision['hash'], controller.selected,
                            controller.page, controller.spell_top, controller.horizontal_choice, controller.text_page, controller.entry, controller.area_map, controller.file_menu, controller.move_mode,
                            controller.file_mode, controller.file_message, controller.generation, report_line(controller), controller.wait_line(),
                            controller.hold_seq if controller.held() is not None else 0],
                  animating=controller.held() is not None or revealed(controller) is not None or controller.session.game.s.mode == 6 or report_line(controller) is not None or bool(controller.wait_line()) or bool(decision and decision['kind'] in ('COMBAT_AUTO', 'CAMP_RESTING'))
                  or bool(decision and decision['info'].get('message') and (is_vertical(controller) or decision['info'].get('action') == 'main-menu')
                          and showing_message(controller))
                  or bool(decision and decision['kind'] == 'COMBAT_MOVE' and decision['info'].get('prompt') and showing_message(controller)))
    def key(rect, keysym, char=''): regions.append(dict(rect=rect, key=dict(keysym=keysym, char=char)))
    due_sounds(controller)
    if controller.held() is not None and not controller.file_menu:
        key((0, 0, 320, 200), 'Return'); return result
    if controller.sound_on: result['sound'] = [list(e) for e in controller.sound_events]
    if controller.file_menu:
        col = len(FILE_QUERY.get(controller.file_mode, ''))
        for hotkey, label in controller.file_items():
            key((col*8,192,len(label)*8,8), hotkey, hotkey); col += len(label)+1
        return result
    if not decision: return result
    if controller.session.game.s.g.get('cok.battle',{}).get('active') and holding(controller):
        key((0,0,320,200),'Return'); return result
    if decision['kind']=='COMBAT_MOVE':
        from ..combat import direction_to
        data=controller.session.game.s.g['cok.battle']; actor=data['actors'][data['actor']]
        ox,oy=combat_view(controller)
        keys=('Up','Prior','Right','Next','Down','End','Left','Home','Return')
        for y in range(7):
            for x in range(7): key((8+x*24,8+y*24,24,24),keys[direction_to(actor['x'],actor['y'],x+ox,y+oy)])
        col=len('Move/Attack, Move Left = %d'%(actor['movement']//2))+1
        key((col*8,192,32,8),'d','d')
        return result
    if decision['kind']=='COMBAT_SPELL_AIM':
        from ..combat import direction_to
        cursor=controller.session.game.s.g['cok.battle']['aim']; ox,oy=combat_view(controller)
        keys=('Up','Prior','Right','Next','Down','End','Left','Home','Return')
        for y in range(7):
            for x in range(7): regions.append(dict(rect=(8+x*24,8+y*24,24,24),keys=walk_keys(cursor,(x+ox,y+oy))))
        label='Target' if 'Target' in decision['options'] else 'Exit'
        regions.append(dict(rect=(18*8,192,len(label)*8,8),select=decision['options'].index(label)))
        result['revision'] += [controller.aim_view]
        return result
    if decision['kind']=='TARGET':
        from ..combat import Battle
        ox,oy=combat_view(controller); start,lead=controller.aim_cell,[]
        if controller.aim_manual:
            label='Target' if controller.aim_choice() is not None else 'Exit'
            key((18*8,192,len(label)*8,8),label[0].lower(),label[0].lower())
        else:
            col=4
            for label in controller.aim_options():
                key((col*8,192,len(label)*8,8),label[0].lower(),label[0].lower()); col+=len(label)+1
            lead=[dict(keysym='m',char='m')]
        for y in range(7):
            for x in range(7): regions.append(dict(rect=(8+x*24,8+y*24,24,24),keys=lead+walk_keys(start,(x+ox,y+oy))))
        result['revision'] += [controller.aim_cell,controller.aim_manual,controller.aim_view,controller.horizontal_choice,controller.aim_blank]
        return result
    paging = controller.text_page*6+6 < len(controller.lines)
    fallback = not controller.session.game.s.g.get('cok.battle',{}).get('active') and (paging or not is_vertical(controller))
    if paging: key((8,136,304,48), 'Return'); key((0,192,320,8), 'Return'); return result
    if decision['kind'] == 'CAMP_RESTING':
        key((0, 0, 320, 200), 'Return'); return result
    if decision['kind'] == 'MOVE':
        col = 0
        overland='north' in decision['options']
        labels=('Move','Encamp') if overland else ('Move','Area','Cast','View','Encamp','Search','Look')
        for word in ('Exit',) if controller.move_mode else labels:
            key((col*8,192,len(word)*8,8), word[0].lower(), word[0].lower()); col += len(word)+1
        if overland:
            from ..combat import direction_to
            x,y=controller.session.game.s.r0[0xC3:0xC5]
            keys=('Up','Prior','Right','Next','Down','End','Left','Home')
            for row in range(15):
                for column in range(38):
                    direction=direction_to(x,y,column,row)
                    if direction<8: key(((column+1)*8,(row+1)*8,8,8),keys[direction])
        else:
            for i, direction in enumerate(('Left','Up','Right')):
                key((24+i*88/3,24,88/3,88), direction)
    elif decision['info'].get('action') == 'main-menu':
        for index, label in menu_items(decision): regions.append(dict(rect=(72,(12+index)*8,len(label)*8,8),select=index))
    elif summary_screen(decision) or share_window(decision):
        regions.append(dict(rect=(0, 192, 320, 8), select=0))
    elif pick_who(decision):
        left = 8 if menu_screen(controller) else 136
        for index in range(len(decision['options'])-1): regions.append(dict(rect=(left, (index+4)*8, 120, 8), select=index))
        key((15*8, 192, 48, 8), 'Return'); regions.append(dict(rect=(22*8, 192, 32, 8), select=len(decision['options'])-1))
    elif script_who(decision):
        game = controller.session.game
        if not (game.s.mode != 6 and game.vm.display.get('kind') == 'BIGPIC'):
            for index in range(len(decision['options'])): regions.append(dict(rect=(136, (index+4)*8, 120, 8), select=index))
        key((0, 192, 320, 8), 'Return')
    elif compact(decision):
        col, items = len(bottom_query(controller)), menu_items(decision)
        indexes = [i for i, _ in items]
        here = indexes.index(controller.selected) if controller.selected in indexes else 0
        for position, (index, label) in enumerate(items):
            step = dict(keysym='Left' if position < here else 'Right', char='')
            keys = [step]*abs(position-here)+[dict(keysym='Return', char='')]
            if decision['kind'] == 'CAMP_REST': keys = [dict(keysym=label[0].lower(), char=label[0].lower())]
            regions.append(dict(rect=(col*8,192,len(label)*8,8),select=index,keys=keys)); col += len(label)+1
    elif is_vertical(controller):
        v = vertical(controller); left, top, right, _ = v['window']
        for row, (index, _) in enumerate(v['visible'], top):
            if index is None or index < 0: continue
            regions.append(dict(rect=(left*8, row*8, (right-left+1)*8, 8), select=index))
        col = len(v['query'])
        for word, k in v['words']:
            if word == 'Exit': regions.append(dict(rect=(col*8, 192, 32, 8), select=v['exit'], keys=[k]))
            else: regions.append(dict(rect=(col*8, 192, len(word)*8, 8), key=k))
            col += len(word)+1
    else:
        v = vertical(controller); col = len(v['query'])
        for row, (index, _) in enumerate(v['visible'], 10):
            regions.append(dict(rect=(184,row*8,128,8),select=index))
        for word, k in v['words']:
            if word == 'Exit': regions.append(dict(rect=(col*8, 192, 32, 8), select=v['exit'], keys=[k]))
            else: regions.append(dict(rect=(col*8, 192, len(word)*8, 8), key=k))
            col += len(word)+1
    single = len([o for o in (decision.get('options') or ()) if not str(o).startswith('char-')]) <= 1
    if fallback and single: key((8,136,304,48), 'Return')
    return result


def test():
    from ._screen_test import test as check
    return check(quick=True)
