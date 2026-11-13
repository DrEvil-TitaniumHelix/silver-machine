import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Thread
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from sm.titles.cok import town
from sm.titles.cok._town_test import outpost_session, area_session
from sm.titles.cok.ui import screen


def digest(frame): return hashlib.sha256(b''.join(frame.rows)).hexdigest()


def check_geometry():
    session = area_session()
    try:
        game, c = session.game, screen.Controller(session)
        assert (game.s.dataset,game.s.block,game.s.x,game.s.y,game.s.dir) == (1,32,7,15,0)
        assert game.geo.map.id == 32 and game.s.walls == [1,65535,65535]
        raw = game.assets.records('GEO1')[32]
        placements = screen.placements(game,c.assets)
        assert len(screen.pieces(game,c.assets)) == 24 and len(placements) == 190
        witness = hashlib.sha256(json.dumps(placements,separators=(',',':')).encode()).hexdigest()
        assert witness == '4610076384e7f15a525761d10298c76511040d58e4e201704511950cffcdd65e'
        walls = game.assets.records('WALLDEF1')[1]
        for col,row,symbol,wall,piece,index,x,y,facing in placements:
            x = 0 if x>15 else 15 if x<0 else x
            y = 0 if y>15 else 15 if y<0 else y
            packed = raw[2+y*16+x+(256 if facing>=4 else 0)]
            assert wall == (packed>>4 if facing in (0,4) else packed&15)
            assert symbol == walls[(wall-1)*156+index]
            assert 0 <= col < 11 and 0 <= row < 11
        before = game.state_hash()
        frame = screen.render(c)
        assert digest(frame) == '85b0d7b770a6b5e54444460c87e453b15f2761fa7680b0faeaccda816218c337'
        assert game.state_hash() == before
        expected = {}
        for col,row,symbol,*_ in placements:
            tile = c.assets.wall_tile(game.s,symbol)
            for y,pixels in enumerate(tile):
                for x,value in enumerate(pixels):
                    if value != 13: expected[24+col*8+x,24+row*8+y] = value
        assert len(expected) > 4000
        assert all(frame.rows[y][x] == value for (x,y),value in expected.items())
        return dict(pieces=24,tiles=190,placement_hash=witness,frame_hash=digest(frame))
    finally: session.close()


def check_picture_after_dungeon():
    session, dungeon=outpost_session(),area_session()
    try:
        game=session.game; controller=screen.Controller(session)
        expected=digest(screen.render(controller))
        game.geo.map=dungeon.game.geo.map; game.s.walls=[5,65535,65535]
        before=game.state_hash()
        assert not game.vm.is3d() and digest(screen.render(controller))==expected
        assert game.state_hash()==before
    finally: session.close(); dungeon.close()


def check_keyboard():
    left, right = area_session(), area_session()
    try:
        c = screen.Controller(left)
        state = left.game.state_hash()
        c.key('F2'); assert c.area_map and left.game.state_hash() == state
        c.key('F2'); assert not c.area_map
        for key,command in (('Left','turn-left'),('Right','turn-right'),('Up','forward')):
            c.key(key)
            right.step(right.decision['options'].index(command))
            assert left.game.state_hash() == right.game.state_hash()
        assert (left.game.s.x,left.game.s.y) == (7,14)
        assert left.game.trace == right.game.trace
        assert left.error is None
    finally: left.close(); right.close()


def request(server, path, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = Request(server.url.rstrip('/')+path,data=data,headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=5) as response: return response.read(),response.headers


def check_http():
    from sm.ui.web import Server
    from sm.titles import cok
    session = outpost_session()
    server = Server(session,port=0,profile=cok,presentation=True)
    worker = Thread(target=server.serve_forever,kwargs={'poll_interval':0.01})
    worker.start()
    try:
        controller = server.controller
        state = session.game.state_hash()
        native = b''.join(screen.render(controller).rows)
        body,headers = request(server,'/frame?t=0')
        assert len(body) == 64000 and body == native
        assert headers['X-Frame-Hash'] == hashlib.sha256(body).hexdigest()
        assert json.loads(request(server,'/version')[0])['content']
        assert json.loads(request(server,'/intake')[0])['ready']
        assert b'<canvas' in request(server,'/')[0]
        layout = json.loads(request(server,'/layout')[0])
        assert session.game.state_hash() == state and layout['regions']
        request(server,'/key',dict(keysym='n',char='n',revision=['stale']))
        assert session.game.state_hash() == state
        request(server,'/key',dict(keysym='n',char='n',revision=layout['revision']))
        assert session.decision['options'][:3] == ['VAULT','TEMPLE','BAR']
        direct = outpost_session()
        try:
            direct.step(4)
            assert direct.game.state_hash() == session.game.state_hash()
            mirror = screen.Controller(direct)
            assert controller.selected == 0
            mirror.selected = controller.selected
            assert b''.join(screen.render(mirror).rows) == request(server,'/frame?t=0')[0]
        finally: direct.close()
        request(server,'/key',dict(keysym='p',char='p'))
        assert session.decision['options'][0] == 'INN'
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close()
        assert not worker.is_alive()


def check_icon_frames():
    from sm.titles.cok import town
    session = outpost_session()
    try:
        a, c = screen.Assets(session.game.assets.root), session.game.s.party[0]
        head, body, size = (town.field(c, k) for k in ('icon_head', 'icon_body', 'icon_size'))
        frames, _ = a.party_icon(head, body, size, tuple(town.field(c, 'icon_colors', j) for j in range(6)))
        assert len(frames) == 2 and frames[0] != frames[1]
        for n, attack in enumerate((0, 128)):
            bias = (64 if size == 2 else 0) + attack
            hp, bp = a.combat_picture('CHEAD', (head+bias) & 255)[0], a.combat_picture('CBODY', (body+bias) & 255)[0]
            for y, row in enumerate(frames[n]):
                for x, v in enumerate(row):
                    h = hp[y][x] if y < len(hp) and x < len(hp[y]) else 0
                    assert (v == 0) == (h == 0 and bp[y][x] == 0) and v == h | bp[y][x]
    finally: session.close()


def check_files():
    from sm.titles.cok import rules, save, town
    from sm.titles.cok._cli import at_outpost
    from sm.titles.cok.ui import start_session
    with TemporaryDirectory(prefix='cok-ui-save-') as directory:
        c = screen.Controller(outpost_session(), save_root=directory)
        try:
            game = c.session.game
            original = game.assets.root / 'SAVE' / 'SAVGAMA.DAT'
            original_hash = hashlib.sha256(original.read_bytes()).digest()
            town.put(game.s.party[0], 'hp', 3); game.s.r0[0xC7] = 4
            c.key('F10'); c.key('s', 's')
            assert ('Save Which Game: ', 13) in [(v, colour) for _, row, v, colour in drawn_text(c, colours=True) if row == 24]
            c.key('b', 'b')
            assert not c.file_menu and not c.file_message and (0, 24, 'Saving...Please Wait') in drawn_text(c)
            snapshot = rules.load_slot(Path(directory)/'B', 'B')
            assert bytes(snapshot.game) == bytes(save.game_image(game.s, 'B'))
            assert 'l' not in [k for k, _ in c.file_items()]
            c.key('F10'); c.key('l', 'l'); assert c.file_mode == 'game'
            town.put(game.s.party[0], 'hp', 3); game.s.r0[0xC7] = 4
            c.key('s', 's'); c.key('b', 'b')
            assert (Path(directory)/'B'/'SAVGAMB.DAT').exists() and not c.file_menu
            c.clock = lambda: 1e9; assert 'Saving...Please Wait' not in [v for _, _, v in drawn_text(c)]
        finally: c.session.close()
        c = screen.Controller(start_session(root=directory), save_root=directory)
        try:
            assert c.session.decision['info'].get('action') == 'main-menu' and not c.session.game.s.party
            c.key('F10'); assert 'l' in [k for k, _ in c.file_items()]
            c.key('l', 'l'); assert ('Load Which Game: ', 13) in [(v, colour) for _, row, v, colour in drawn_text(c, colours=True) if row == 24]
            old = c.session; c.key('j', 'j'); assert c.file_mode == 'load' and c.file_menu
            assert 'J' not in [label for _, label in c.file_items()] and 'B' in [label for _, label in c.file_items()]
            c.key('b', 'b')
            assert c.session is old and not c.file_menu and c.session.decision['info'].get('action') == 'main-menu'
            assert len(c.session.game.s.party) == 6 and (0, 24, 'Loading...Please Wait') in drawn_text(c)
            c.key('F10'); assert 'l' not in [k for k, _ in c.file_items()]; c.key('Escape')
            click(c, 'Begin Adventuring')
            for _ in range(16):
                if at_outpost(c.session): break
                assert c.session.decision and not c.session.error
                c.choose(0)
            assert at_outpost(c.session)
            assert town.field(c.session.game.s.party[0], 'hp') == 3 and c.session.game.s.r0[0xC7] == 4
            startup = start_session(slot='A', root=directory)
            try: assert len(startup.game.s.party) == 6 and startup.game.s.dataset == 1
            finally: startup.close()
            assert hashlib.sha256(original.read_bytes()).digest() == original_hash
        finally: c.session.close()


def check_camp():
    session = outpost_session()
    try:
        session.step(0); session.step(0)
        c = screen.Controller(session)
        assert session.decision['options'] == ('Save', 'View', 'Magic', 'Rest', 'Alter', 'Fix', 'Exit', 'char-up', 'char-down')
        assert (1, 18, 'The party makes camp...') in drawn_text(c)
        c.key('Down'); assert (1, 18, 'The party makes camp...') in drawn_text(c); c.key('Up')
        c.key('r', 'r')
        assert session.decision['kind'] == 'CAMP_REST' and not session.error
        assert c.lines and screen.render(c).rows
        c.key('Left'); c.key('Up')
        assert session.decision['info']['hours'] >= 1, session.decision
        session.game.rest_poll = True
        now = [0.0]; c.clock = lambda: now[0]; c.key('r', 'r')
        assert session.decision['kind'] == 'CAMP_RESTING', session.decision
        seen = drawn_text(c); assert (1, 17, 'Rest Time:') in seen and not any(r == 24 and t for _, r, t in seen), seen
        first = session.decision['i']; now[0] += 1; screen.render(c)
        assert session.decision['kind'] == 'CAMP_RESTING' and session.decision['i'] > first
        c.key('x', 'x'); assert session.decision['info'].get('prompt') == 'Stop Resting? ', session.decision
        c.key('y', 'y'); c.clock = __import__('time').monotonic
        assert session.decision['kind'] == 'CAMP_MENU' and session.decision['info'].get('prompt') == 'Camp', session.decision
        assert session.decision['kind'] == 'CAMP_MENU'
        assert session.decision['info'].get('prompt') == 'Camp' and (1, 18, 'The party makes camp...') not in drawn_text(c)
        c.key('m', 'm'); [c.key('Down') for _ in range(4)]; c.key('m', 'm')
        assert session.decision['kind'] == 'SPELL' and session.game.s.sel == 4 and c.selected == session.decision['info']['start'] > 0, c.selected
        seen = drawn_text(c); slots = session.decision['info']['slots'].split(chr(10))
        assert (1, 18, slots[0]) in seen and slots[0].lstrip().startswith(('Cleric', 'Magic-User')), seen
        assert (0, 24, 'Choose Spell: ') in seen and (14, 24, 'Memorize') in seen, seen
        assert all(5 <= r <= 15 for col, r, t in seen if t in session.decision['options'] and t != 'Exit'), seen
        row = c.selected
        c.key('Return')
        assert session.decision['kind'] == 'SPELL' and c.selected == row and not session.error, (c.selected, row)
    finally: session.close()


def check_shop():
    from sm.titles.cok import shop
    from sm.titles.cok._cli import at_outpost
    from sm.titles.ssb.ui import screen as base
    session = outpost_session()
    try:
        c = screen.Controller(session)
        def select(label):
            while c.text_page*6+6 < len(c.lines): c.key('Return')
            index = next(i for i, value in enumerate(session.decision['options']) if label in value)
            listed = screen.is_vertical(c)
            if listed and label == 'Exit': c.key('e', 'e'); assert not session.error, session.error; return
            for _ in session.decision['options']:
                if c.selected == index: break
                c.key('Down' if listed else 'Right')
            assert c.selected == index
            c.key('Return')
            assert not session.error, session.error
        select('ARMOURY')
        assert session.decision['kind'] == 'SHOP_MENU'
        char = session.game.s.party[session.game.s.sel]
        pooled, count = sum(shop.coins(c)[shop.STEEL] for c in session.game.s.party), len(char.items)
        sword = next(item for item in session.game.s.treasure_items if 'Long Sword' in shop.item_name(session.game, item))
        price = shop.price_of(session.game.s, sword)
        assert pooled >= price
        select('Pool')
        assert session.game.s.treasure_money[shop.STEEL] == pooled
        select('Buy')
        assert session.decision['kind'] == 'LIST' and not session.error
        select('Long Sword')
        assert len(char.items) == count+1 and session.game.s.treasure_money[shop.STEEL] == pooled-price
        assert ' buys a ' in session.decision['info']['message']
        drawn, text = [], base.Frame.text
        base.Frame.text = lambda self, col, row, value, *a, **k: (drawn.append((row, str(value))), text(self, col, row, value, *a, **k))[1]
        try: screen.render(c)
        finally: base.Frame.text = text
        assert any(row == 24 and ' buys a ' in value for row, value in drawn), drawn
        assert len(b''.join(screen.render(c).rows)) == 64000
        select('Exit'); select('Share'); select('Exit')
        assert at_outpost(session)
        assert sum(shop.coins(c)[shop.STEEL] for c in session.game.s.party) == pooled-price
    finally: session.close()


def click(c, label):
    d, regions = c.session.decision, screen.layout(c)['regions']
    name = lambda r: 'Exit' if d['options'][r['select']] is None else str(d['options'][r['select']])
    own = next(r for r in regions if ('select' in r and label in name(r)) or r.get('label') == label)
    x, y = own['rect'][0]+own['rect'][2]/2, own['rect'][1]+own['rect'][3]/2
    r = next(r for r in regions if r['rect'][0] <= x < r['rect'][0]+r['rect'][2] and r['rect'][1] <= y < r['rect'][1]+r['rect'][3])
    if 'keys' in r: [c.key(k['keysym'], k['char']) for k in r['keys']]
    elif 'key' in r: c.key(r['key']['keysym'], r['key']['char'])
    else:
        delta = r['select']-c.selected
        for _ in range(abs(delta)): c.key('Up' if delta < 0 else 'Down')
        c.key('Return')
    assert not c.session.error, c.session.error


def check_clicks():
    from sm.titles.cok import shop
    from sm.titles.cok.ui import start_session
    from sm.titles.ssb.ui import screen as base
    session = outpost_session()
    try:
        c = screen.Controller(session)
        click(c, 'ARMOURY'); click(c, 'Pool'); click(c, 'Buy')
        assert session.decision['kind'] == 'LIST' and session.decision['info']['window'] == '1 1 38 22'
        char, count = session.game.s.party[0], len(session.game.s.party[0].items)
        click(c, 'Long Sword')
        assert len(char.items) == count+1 and 'Long Sword' in shop.item_name(session.game, bytearray(char.items[-1]))
        click(c, 'Exit'); assert session.decision['kind'] == 'SHOP_MENU'
        click(c, 'View'); click(c, 'Items'); click(c, 'Long Sword')
        assert screen.compact(session.decision) and 'Id' in session.decision['options']
        click(c, 'Exit'); click(c, 'Exit'); click(c, 'Exit')
        click(c, 'Share'); click(c, 'Exit')
        click(c, 'INN'); c.key('Return'); click(c, 'View')
        drawn, text = [], base.Frame.text
        base.Frame.text = lambda self, col, row, value, *a, **k: (drawn.append(str(value)), text(self, col, row, value, *a, **k))[1]
        try: screen.render(c)
        finally: base.Frame.text = text
        assert session.decision['kind'] == 'CREATE_VIEW' and {'Hit Points', 'Armor Class', 'THAC0', 'STR'} <= set(drawn), drawn
        def texts():
            drawn = []
            base.Frame.text = lambda self, col, row, value, *a, **k: (drawn.append(str(value)), text(self, col, row, value, *a, **k))[1]
            try: screen.render(c)
            finally: base.Frame.text = text
            return drawn
        assert any(t.endswith(' camping') for t in texts())
        click(c, 'Exit'); click(c, 'Alter'); click(c, 'Level')
        assert c.selected == max(0, session.decision['info']['level']-1)
        click(c, 'Exit'); click(c, 'Speed')
        assert any(t.startswith('Game Speed = ') for t in texts())
        click(c, 'Exit'); click(c, 'Exit'); click(c, 'Magic'); click(c, 'Display')
        assert texts().count(' <No Spell Effects>') == len(session.game.s.party)
        click(c, 'Exit'); click(c, 'Exit'); click(c, 'Exit'); click(c, 'NEXT'); click(c, 'TEMPLE'); click(c, 'Heal')
        click(c, 'Stone to Flesh')
        assert session.decision['kind'] == 'TEMPLE_CONFIRM' and 'is not stoned' in ' '.join(c.lines), c.lines
        click(c, 'No'); click(c, 'Exit'); click(c, 'Exit')
        click(c, 'HALL'); click(c, 'Begin Adventuring')
        assert session.decision['kind'] == 'MENU' and 'HALL' in session.decision['options'], session.decision['kind']
    finally: session.close()
    session = start_session()
    try:
        c = screen.Controller(session)
        click(c, 'Create New Character'); click(c, 'Human')
        assert session.decision['kind'] == 'CREATE_GENDER' and session.decision['info']['window'] == '1 2 38 22'
        click(c, 'Male'); click(c, 'Fighter'); click(c, 'Lawful Good')
        assert session.decision['kind'] == 'CREATE_ROLL'
        before, drawn, text = session.game.state_hash(), [], base.Frame.text
        base.Frame.text = lambda self, col, row, value, *a, **k: (drawn.append((row, str(value))), text(self, col, row, value, *a, **k))[1]
        try: screen.render(c)
        finally: base.Frame.text = text
        assert (24, 'Reroll stats? ') in drawn and any(v.startswith('Experience') for _, v in drawn), drawn
        assert session.game.state_hash() == before
        click(c, 'Yes'); assert session.decision['kind'] == 'CREATE_ROLL'
    finally: session.close()


def drawn_text(c, colours=False, elapsed=0):
    from sm.titles.ssb.ui import screen as base
    drawn, text = [], base.Frame.text
    base.Frame.text = lambda self, col, row, value, assets, colour=15, *a, **k: (
        drawn.append((col, row, str(value)) + ((colour,) if colours else ())), text(self, col, row, value, assets, colour, *a, **k))[1]
    try: screen.render(c, elapsed=elapsed)
    finally: base.Frame.text = text
    return drawn


def check_read_12_4():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        click(c, 'INN'); c.key('Return'); click(c, 'View')
        assert session.decision['kind'] == 'CREATE_VIEW'
        before = session.game.state_hash(); frame = screen.render(c)
        assert session.game.state_hash() == before
        sides = c.assets.resident[52066:52089]; divider = c.assets.resident[52089:52100]
        old_sides = bytearray(c.assets.part('leftEdgeTiles')[:23])
        for row in (8, 16, 20): old_sides[row] = 0
        assert [row for row, (old, new) in enumerate(zip(old_sides, sides)) if old != new] == [7, 9, 19, 21]
        expected = {(col, row): c.assets.border[20+tile] for row, tile in enumerate(sides) for col in (0, 39)}
        expected.update({(19, row): c.assets.border[20+tile] for row, tile in enumerate(divider, 9)})
        for (col, row), tile in expected.items():
            actual = tuple(bytes(line[col*8:(col+1)*8]) for line in frame.rows[row*8:(row+1)*8])
            assert actual == tile, ('sheet tile', col, row)
        for row in (8, 16, 20, 23):
            assert tuple(bytes(line[8:16]) for line in frame.rows[row*8:(row+1)*8]) == c.assets.border[20]
        assert {'Hit Points', 'Armor Class', 'STR', 'THAC0'} <= {text for _, _, text in drawn_text(c)}
    finally: session.close()


def check_read_script_sprites():
    session = area_session()
    try:
        game = session.game; c = screen.Controller(session); c.clock = lambda: 0.0
        pixels = lambda: b''.join(screen.render(c).rows)
        before = game.state_hash(); shown = dict(game.vm.display)
        sprite = min(game.assets.records('SPRIT%d' % game.s.dataset)); picture = min(game.assets.records('PIC%d' % game.s.dataset))
        game.vm.display = {'kind': None}; plain = pixels()
        frames = []
        for distance in (2, 1, 0):
            game.vm.display = dict(kind='SPRIT', dataset=game.s.dataset, id=sprite, pic=picture, frame=distance, head=None); frames.append(pixels())
        assert len({plain, *frames}) == 4, 'sprite frames not drawn'
        game.vm.display = dict(kind='PIC', dataset=game.s.dataset, id=picture, frame=0, head=None)
        assert frames[2] == pixels(), 'distance 0 is the close-up picture'
        game.vm.display = dict(kind='SPRIT', dataset=game.s.dataset, id=sprite, pic=picture, frame=0, head=None, menu=1)
        assert pixels() not in (frames[2], plain), 'the encounter menu keeps the sprite at distance 0'
        game.vm.display = shown; assert game.state_hash() == before
    finally: session.close()


def check_read_script_screens():
    session = outpost_session()
    real = session.decision
    try:
        game = session.game; now = [0.0]
        c = screen.Controller(session); c.clock = lambda: now[0]
        pixels = lambda: b''.join(screen.render(c).rows)
        def stand_in(kind, options, **info):
            session.decision = dict(real, kind=kind, options=options, info=info); c.selected = 0; c.capture_text()
            return drawn_text(c, True)
        before = game.state_hash()
        game.vm.clear_text(); game.vm.out.append('HELD FOR A MOMENT'); game.vm.hold(0.4)
        game.vm.clear_text(); game.vm.out.append('LATER TEXT'); c.capture_text()
        held = drawn_text(c); assert (1, 17, 'HELD FOR A MOMENT') in held and not any(row == 24 for _, row, _ in held), held
        assert screen.layout(c)['animating']
        now[0] = 0.39; assert (1, 17, 'HELD FOR A MOMENT') in drawn_text(c)
        now[0] = 0.41; later = drawn_text(c); assert (1, 17, 'LATER TEXT') in later and (0, 24, 'INN') in later, later
        game.vm.hold(0.4); mark = session.decision; assert c.key('Return') is False and session.decision is mark and not game.presentation
        assert (0, 24, 'INN') in drawn_text(c)
        names = [bytes(town.buffer(m)[1:1+town.buffer(m)[0]]).decode('cp437') for m in game.s.party]
        who = stand_in('WHO', names, at=1, prompt='WHO WILL TRY?')
        assert (0, 24, 'WHO WILL TRY? ', 13) in who and (14, 24, 'Select', 0) in who and not any(17 <= row <= 22 for _, row, _, _ in who), who
        assert (17, 4, names[0][:15], 15) in who
        c.key('Down'); assert (17, 5, names[1][:15], 15) in drawn_text(c, True)
        menu = stand_in('MENU', ['FIRST ANSWER', 'SECOND ANSWER'], at=1, prompt='WHAT DO YOU DO?', vertical=1)
        assert (1, 17, 'WHAT DO YOU DO?', 10) in menu and (1, 18, 'FIRST ANSWER', 0) in menu and (1, 19, 'SECOND ANSWER', 10) in menu, menu
        assert (0, 24, screen.NEW_CONTINUE, 0) in stand_in('MENU', [screen.OLD_CONTINUE, 'char-up', 'char-down'], at=1)
        door = stand_in('MENU', ['Bash', 'Exit'], door=2); assert (0, 24, 'Locked. ', 13) in door and (8, 24, 'Bash', 0) in door, door
        coins = stand_in('VIEW_COIN', ['Steel          455', 'Exit'], prompt='Select type of coin ')
        assert (20, 9, 'Steel          455', 0) in coins and (0, 24, 'Select type of coin ', 13) in coins and (21, 24, 'Select', 0) in coins, coins[-6:]
        assert any(text == 'Hit Points' for _, _, text, _ in coins), 'the sheet stays up under the coin list'
        items = stand_in('VIEW_ITEMS', [' No   Thing ', 'Exit'], prompt='Items', window='1 5 38 22', title=names[0]+"'s Items", caption='Ready Item')
        assert (1, 1, names[0]+"'s", 11) in items and (len(names[0])+4, 1, 'Items', 10) in items, items[:4]
        assert (1, 22, 'Potion', 10) in stand_in('ACK', ['Continue'], prompt=names[0]+' uses an item', item='Potion ')
        assert game.state_hash() == before, 'drawing changed the state'
    finally:
        session.decision = real; session.close()


def check_screens_two():
    from sm.titles.cok import creation
    session = outpost_session()
    try:
        c = screen.Controller(session)
        click(c, 'HALL')
        assert (1, 4, 'SIR STRONGSWORD') in drawn_text(c)
        click(c, 'Begin Adventuring')
        c.key('F10'); assert [k for k, _ in c.file_items()] == ['s', 'q', 'r']; c.key('Escape')
        click(c, 'ARMOURY'); click(c, 'Pool'); click(c, 'Take'); click(c, 'Steel'); c.key('5', '5')
        assert session.decision['kind'] == 'NUMBER'
        assert {(0, 24, 'How much steel  will you take? ', 10), (31, 24, '5', 15)} <= set(drawn_text(c, True)), drawn_text(c)
        real = session.decision
        try:
            session.decision = dict(real, kind='CREATE_TRAIN', options=('Yes', 'No'),
                                    info=dict(prompt='Do you wish to train? ', character='KAL', levels='a level 7 Knight; a level 5 Mage'))
            c.capture_text(); seen = drawn_text(c)
            assert (4, 4, 'KAL') in seen and (6, 5, '    a level 7 Knight') in seen and (6, 6, 'and a level 5 Mage') in seen, seen
            assert (0, 24, 'Do you wish to train? ') in seen
            char = session.game.s.party[0]; name = bytes(char.b[1:1+char.b[0]]).decode('cp437')
            from sm.titles.cok.creation import F
            order, char.b[F['knight_order']] = char.b[F['knight_order']], 1
            session.decision = dict(real, kind='CREATE_KNIGHT', options=('Change', 'Exit'), info=dict(prompt=name+' may become a Knight Of The Sword'))
            c.capture_text(); seen = drawn_text(c); char.b[F['knight_order']] = order
            assert (19-len(name)//2, 3, name) in seen and (7, 5, 'is petitioning to become a') in seen and (10, 7, 'Knight Of The sword') in seen, seen
            assert (19-(len(name)+13)//2, 9, name+' may become a') in seen and (10, 11, 'Knight Of The Sword') in seen, seen
            session.decision = dict(real, kind='ACK', options=('Continue',), info=dict(message='The party has found Treasure! Each character receives 1278 experience points.'))
            c.capture_text(); seen = drawn_text(c)
            assert {(1, 3, 'The party has found Treasure!'), (1, 5, 'Each character receives 1278'), (1, 7, 'experience points.'),
                    (0, 24, 'press <enter>/<return> to continue')} <= set(seen), seen
            assert screen.layout(c)['regions'][0]['rect'] == (0, 192, 320, 8)
            session.decision = dict(real, kind='ACK', options=('Continue',), info=dict(message='KAL takes and hides his share.\nTIKA takes and hides her share.'))
            c.capture_text(); seen = drawn_text(c)
            assert {(5, 5, 'KAL takes and hides his share.'), (5, 7, 'TIKA takes and hides her'), (5, 8, 'share.'),
                    (0, 24, 'press <enter>/<return> to continue')} <= set(seen), seen
        finally: session.decision = real
    finally: session.close()


def check_text_pages():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        c.lines = ['line %d' % n for n in range(8)]; c.text_page = 0
        assert (0, 24, 'Press any key to continue') in drawn_text(c)
        c.key('x', 'x'); assert c.text_page == 1 and (1, 17, 'line 6') in drawn_text(c)
        c.lines = ['line %d' % n for n in range(6)] + ['KAL is hit FOR 4 points of Damage.']; c.text_page = 0
        assert (0, 24, 'Press any key to continue') in drawn_text(c)
        c.lines = ['line %d' % n for n in range(6)] + ['  KAL is hit FOR 4 points of Damage.']; c.text_page = 0
        assert (0, 24, 'press <enter>/<return> to continue') in drawn_text(c)
    finally: session.close()


def check_appraise():
    from sm.titles.cok import shop
    session = outpost_session()
    try:
        c = screen.Controller(session)
        char = session.game.s.party[0]; money = shop.coins(char); money[shop.GEMS], money[shop.JEWELRY] = 2, 1; shop.put_coins(char, money)
        click(c, 'ARMOURY'); s = session.game.s
        c.key('Down'); assert session.decision['kind'] == 'SHOP_MENU' and s.sel == 1
        c.key('Up'); assert s.sel == 0
        click(c, 'Appraise'); assert session.decision['info']['prompt'] == 'Appraise : '
        seen = drawn_text(c)
        assert (1, 7, 'You have a fine collection of:') in seen and (1, 9, '2 Gems') in seen and (1, 10, '1 piece of Jewelry') in seen, seen
        assert (0, 24, 'Appraise : ') in seen and (11, 24, 'Gems') in seen and (1, 1, 'SIR STRONGSWORD') in seen, seen
        click(c, 'Gems'); seen = drawn_text(c)
        assert any(r == 12 and t.startswith('The Gem is Valued at ') for _, r, t in seen) and (1, 9, '2 Gems') in seen, seen
        assert (0, 24, 'You can : ') in seen and (10, 24, 'Sell') in seen, seen
        assert session.decision['options'] == ('Sell', 'Keep'), session.decision['options']
    finally: session.close()


def check_plus():
    from unittest.mock import patch
    from sm.titles import select
    from sm.ui.web import Server
    from sm.ui import journal
    from sm.titles.cok.ui import plus
    with TemporaryDirectory(prefix='cok-plus-') as root, patch.dict(os.environ, SM_CONFIG_HOME=root, SM_SAVE_ROOT=root):
        session = area_session()
        server = Server(None, 0, profile=select('cok'), session_factory=lambda: session)
        try:
            c = server.controller
            prefs = server.preferences()
            assert prefs['tabs'] == ['journal', 'map', 'help'] and prefs['supported'] == ['effect_scale', 'sound'] and prefs['persistent']
            assert prefs['help'] == plus.HELP and 'dqk_frame' not in prefs
            plus.test()
            server.plus.update(dict(effect_scale=2)); c.apply_plus(server.plus)
            assert c.effect_scale == 2 and (Path(root)/'cok-plus.json').is_file() and not (Path(root)/'plus.json').exists()
            assert c.journal.book.info()['file'].lower() == 'journal.pdf'
            session.game.vm.out.append('YOU RECORD THE REST OF HIS SPEECH AS JOURNAL ENTRY 38.')
            c.capture_text(); snap = c.journal.snapshot()
            assert [e['number'] for e in snap['entries']] == [38] and snap['entries'][0]['page'] is None, snap['entries']
            area = plus.tab_data(c, 'map', {})
            assert area['available'] and len(area['cells']) == 256 and area['area'] == '1/32'
        finally: server.server_close(); session.close()
    assert journal.references('JOURNAL ENTRY 79') == [] and journal.references('JOURNAL ENTRY 79', 999) == [79]
    assert journal.BOOKS['ssb']['pages'] is journal.PAGES and journal.BOOKS['ssb']['sha256'] == journal.PDF_SHA256


def check_aim_click():
    from sm.titles.cok.combat import DX, DY
    names = ('Up', 'Prior', 'Right', 'Next', 'Down', 'End', 'Left', 'Home')
    for start, cell in (((27, 13), (23, 11)), ((0, 0), (6, 6)), ((10, 10), (10, 4)), ((49, 24), (43, 18))):
        x, y = start
        for k in screen.walk_keys(start, cell): d = names.index(k['keysym']); x, y = x+DX[d], y+DY[d]
        assert (x, y) == cell, (start, cell, x, y)
    assert screen.walk_keys((5, 5), (5, 5)) == [dict(keysym='Return', char='')]


def check_replay_hold():
    from sm.titles.cok._combat_test import ambush
    session = ambush(); now = [0.0]
    try:
        c = screen.Controller(session); c.clock = lambda: now[0]
        for _ in range(60):
            d = session.decision
            if d['kind'] == 'COMBAT_ACTION': c.choose(d['options'].index('Done')); c.choose(session.decision['options'].index('Guard'))
            else: c.choose(0)
            if screen.holding(c): break
        else: raise AssertionError('no replay of others reached')
        d, i = session.decision, session.decision['i']
        assert not any(v.strip() and v not in screen.BOTTOM_LINE for _, row, v in drawn_text(c) if row in (23, 24)), 'menu drawn during the replay'
        regions = screen.layout(c)['regions']; assert len(regions) == 1 and regions[0]['rect'] == (0, 0, 320, 200)
        c.key('m', 'm')
        assert session.decision['i'] == i and not screen.holding(c)
        if d['kind'] == 'COMBAT_ACTION':
            c.key('m', 'm'); assert session.decision['kind'] == 'COMBAT_MOVE'
    finally: session.close()


def check_battle_begins():
    session = outpost_session(); now = [0.0]
    try:
        session.step(5); session.step(session.decision['options'].index('NO')); session.step(session.decision['options'].index('northeast'))
        c = screen.Controller(session); c.clock = lambda: now[0]
        c.choose(0); assert session.decision['kind'] == 'COMBAT_ACTION' and c.report[0] == dict(kind='begin')
        now[0] = c.report_at + .01
        assert (0, 24, 'A battle begins...') in drawn_text(c) and screen.holding(c), drawn_text(c)
        now[0] = c.report_at + sum(screen.report_hold(e) for e in c.report) + .01
        assert (0, 24, 'A battle begins...') not in drawn_text(c) and not screen.holding(c)
    finally: session.close()


def check_guarding():
    from sm.titles.cok._combat_test import ambush
    session = ambush(); now = [0.0]
    try:
        c = screen.Controller(session); c.clock = lambda: now[0]
        c.choose(session.decision['options'].index('Done')); c.choose(session.decision['options'].index('Guard'))
        k = c.report.index('Guarding'); now[0] = c.report_at + sum(screen.report_hold(e) for e in c.report[:k]) + .01
        seen = drawn_text(c)
        assert (0, 24, 'Guarding') in seen and not any(v == 'Guarding' for col, _, v in seen if col == 23), seen
        assert screen.step_sounds('Guarding') == [] and screen.step_sounds('Your Teammate is Dying') == []
    finally: session.close()


def check_fight_keys_frame():
    from sm.titles.cok import combat, creation
    from sm.titles.cok._combat_test import ambush
    session = ambush()
    try:
        c = screen.Controller(session); c.clock = lambda: 0.0
        game = session.game; battle = combat.Battle(game)
        words = [label for _, label in screen.menu_items(session.decision)]
        assert screen.compact(session.decision) and not set(words) & set(combat.FIGHT_KEYS)
        seen = drawn_text(c)
        assert all(any(row == 24 and text == word for _, row, text in seen) for word in words)
        regions = screen.layout(c)['regions']
        assert all(session.decision['options'][r['select']] not in combat.FIGHT_KEYS for r in regions if 'select' in r)
        for char in game.s.party: town.put(char, 'auto_combat', 1)
        index = session.decision['i']; c.key('space', ' ')
        assert session.decision['i'] == index+1 and not any(town.field(char, 'auto_combat') for char in game.s.party)
        battle.data['magic_enabled'] = False
        for message in ('Magic On', 'Magic Off'):
            c.key('Alt-m'); assert c.report == [message]
            assert (0, 24, message, 10) in drawn_text(c, True)
            assert not any(text == message and col == 23 for col, _, text in drawn_text(c))
            assert screen.step_sounds(message) == [] and screen.holding(c)
            c.key('Return')
        game.s.g[creation.DELAY] = 4
        click(c, 'Done'); done = session.decision['options']; click(c, 'Speed')
        for delay, choice in ((4, 'Slower'), (5, 'Faster'), (4, 'Exit')):
            query = 'GameSpeed (%d) :' % delay
            assert (0, 24, query, 13) in drawn_text(c, True)
            assert (len(query), 24, 'Slower', 0 if c.selected == 0 else 10) in drawn_text(c, True)
            region = next(r for r in screen.layout(c)['regions'] if r.get('select') == 0)
            assert region['rect'] == (len(query)*8, 192, 6*8, 8)
            click(c, choice)
        assert session.decision['kind'] == 'COMBAT_DONE' and session.decision['options'] == done
    finally: session.close()
    for key in ('Alt-q', 'Alt-a'):
        session = ambush()
        try:
            c = screen.Controller(session); c.clock = lambda: 0.0
            c.key(key)
            assert session.decision['kind'] == 'COMBAT_AUTO'
            assert all(town.field(char, 'auto_combat') for char in session.game.s.chars())
            combat.Battle(session.game).data['magic_enabled'] = False
            c.key('Alt-m')
            assert 'Magic On' in c.report and (0, 24, 'Magic On', 10) in drawn_text(c, True)
            c.key('Return'); c.key('space', ' ')
            assert not any(town.field(char, 'auto_combat') for char in session.game.s.party)
        finally: session.close()


def check_sound():
    import sys, types
    from unittest.mock import patch
    from sm.titles import select
    from sm.ui.web import Server
    fake = types.ModuleType('sm.sound')
    fake.cue = lambda folder, command: [(100 + command, 20), (0, 5)] if 2 <= command <= 14 else (_ for _ in ()).throw(KeyError(command))
    assert screen.step_sounds(dict(kind='attack', result='Hitting for 6 points of damage')) == [7]
    assert screen.step_sounds(dict(kind='attack', result='and Misses', down='killed')) == [9, 5]
    assert [screen.step_sounds(dict(kind='bolt', spell=s)) for s in (47, 51, 15)] == [[11], [8], [2]]
    assert screen.step_sounds('KAL takes 8 spell damage') == [3] and screen.step_sounds('SIRRION is Slowed') == [4]
    assert screen.step_sounds(dict(kind='move', actor=3)) == [10]
    assert [screen.step_sounds('KAL'+t) for t in (' Goes Down', ' Goes Down, and is Dying', ' is killed', ' Is destroyed', ' explodes.')] == [[5]]*5
    with TemporaryDirectory(prefix='cok-sound-') as root, patch.dict(os.environ, SM_CONFIG_HOME=root, SM_SAVE_ROOT=root),             patch.dict(sys.modules, {'sm.sound': fake}):
        session = area_session()
        server = Server(None, 0, profile=select('cok'), session_factory=lambda: session)
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}); worker.start()
        try:
            c, s = server.controller, session.game.s
            assert server.preferences()['options']['sound'] is True
            before = (s.x, s.y, s.dir); c.key('Left'); c.key('Down'); assert (s.x, s.y, s.dir) != before
            assert [cmd for _, cmd in c.sound_events] == [10]
            step = session.step; session.step = lambda a: (session.game.__dict__.setdefault('script_sounds', []).append(11), step(a))[1]
            try: c.key('Left'); assert [cmd for _, cmd in c.sound_events][-2:] == [10, 11], c.sound_events
            finally: session.step = step
            c.key('Right')
            body, _ = request(server, '/sound'); cues = json.loads(body)['cues']
            assert cues['10'] == [[110, 20], [0, 5]] and set(cues) == {str(n) for n in range(2, 13)}
            layout = json.loads(request(server, '/layout')[0]); assert layout['sound'][-1][1] == 10
            server.plus.update(dict(sound=False)); c.apply_plus(server.plus); n = c.sound_seq
            c.key('Left'); assert c.sound_seq == n and 'sound' not in screen.layout(c)
        finally: server.shutdown(); worker.join(5); server.server_close(); session.close()
    assert 'sound' not in json.loads(request_layout_without_reader())


def request_layout_without_reader():
    import sys
    from unittest.mock import patch
    from sm.titles import select
    from sm.ui.web import Server
    with patch.dict(sys.modules, {'sm.sound': None}):
        session = area_session(); server = Server(None, 0, profile=select('cok'), session_factory=lambda: session)
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}); worker.start()
        try: return request(server, '/layout')[0]
        finally: server.shutdown(); worker.join(5); server.server_close(); session.close()


def check_replay_follows():
    import hashlib
    from sm.titles.cok._combat_test import ambush
    session = ambush(); now = [0.0]
    try:
        c = screen.Controller(session); c.clock = lambda: now[0]
        for _ in range(30):
            d = session.decision
            if d['kind'] == 'COMBAT_ACTION': c.choose(d['options'].index('Done')); c.choose(session.decision['options'].index('Guard'))
            else: c.choose(0)
            if any(isinstance(e, dict) and e['kind'] == 'move' for e in c.report): break
        moves = [k for k, e in enumerate(c.report) if isinstance(e, dict) and e['kind'] == 'move']
        start = {k: sum(screen.report_hold(e) for e in c.report[:k]) for k in moves[:4]}
        arenas = set()
        for k, at in start.items():
            now[0] = c.report_at + at + .01; frame = screen.render(c)
            arenas.add(hashlib.sha256(b''.join(bytes(r[8:176]) for r in frame.rows[8:176])).hexdigest())
        assert len(arenas) == len(start) > 1, 'move steps not seen'
    finally: session.close()


def check_slot_start():
    from unittest.mock import patch
    from sm.engine import Session
    from sm.titles.cok import save
    from sm.titles.cok._cli import at_outpost
    from sm.titles.cok._town_test import starter_game
    from sm.titles.cok.menu import Game
    with TemporaryDirectory(prefix='cok-slot-start-') as directory, patch.dict(os.environ, SM_SAVE_ROOT=directory):
        expected, game = starter_game(), Game(None, slot='A')
        assert bytes(save.game_image(game.s, 'A')) == bytes(save.game_image(expected.s, 'A'))
        assert game.vm.resuming and len(game.s.party) == 6
        session = Session(profile='cok', game=game)
        try:
            for _ in range(16):
                if at_outpost(session): break
                assert session.decision and not session.error
                session.step(0)
            assert at_outpost(session)
        finally: session.close()


def check_cursors():
    from sm.titles.cok import combat
    from sm.titles.cok._combat_test import ambush
    result={}
    session=outpost_session()
    try:
        session.step(5); session.step(session.decision['options'].index('NO'))
        assert session.decision['kind']=='MOVE' and session.game.s.mode==3
        game,c=session.game,screen.Controller(session)
        before=game.state_hash(); frame=screen.render(c)
        marker=c.assets.combat_picture('CURSOR',1)[0]
        x,y=(game.s.r0[0xC3]+1)*8,(game.s.r0[0xC4]+1)*8
        assert (x,y)==(16,32) and (game.s.x,game.s.y)==(7,13)
        assert all(frame.rows[y+dy][x+dx]==v for dy,row in enumerate(marker) for dx,v in enumerate(row) if v!=13)
        assert game.state_hash()==before
        result['C1']=digest(frame)
    finally: session.close()

    session=ambush()
    try:
        game,c=session.game,screen.Controller(session); b=combat.Battle(game)
        before=game.state_hash(); seed=game.s.seed
        lit,dark=screen.render(c,elapsed=0),screen.render(c,elapsed=.4)
        i=b.data['actor']; ox,oy=screen.combat_view(c); cx,cy=b.position(i)
        icon,palette=c.assets.combat_icon(game,i); cursor=c.assets.combat_picture('COMSPR',25)[0]
        x,y=8+(cx-ox)*24,8+(cy-oy)*24
        for dy,row in enumerate(cursor):
            for dx,value in enumerate(row):
                if icon[dy][dx]: value=palette[icon[dy][dx]]
                elif not value: value=dark.rows[y+dy][x+dx]
                assert lit.rows[y+dy][x+dx]==value
        assert digest(lit)!=digest(dark) and game.state_hash()==before and game.s.seed==seed
        result['C2']=(digest(lit),digest(dark))

        c.key('a','a'); assert session.decision['kind']=='TARGET'
        before=game.state_hash(); original=c.aim_cell; frame=screen.render(c)
        c.key('Right'); assert c.aim_cell==original and not c.aim_manual and digest(screen.render(c))!=digest(frame)
        c.key('m','m'); c.key('Right'); assert c.aim_cell==(original[0]+1,original[1]) and c.aim_manual
        assert digest(screen.render(c))!=digest(frame) and game.state_hash()==before and game.s.seed==seed
        c.key('Escape'); assert c.aim_cell==original and not c.aim_manual
        c.key('n','n'); assert not c.aim_manual and game.state_hash()==before
        c.key('Escape'); c.key('m','m'); c.key('Up'); c.key('Up'); c.key('Left'); c.key('Escape')
        for _ in range(200):
            d=session.decision
            if d['kind']=='COMBAT_ACTION' and any(town.field(b.chars[j],'side')!=town.field(b.chars[b.data['actor']],'side') for j in b.attack_targets(b.data['actor'])): break
            choice='Done' if d['kind']=='COMBAT_ACTION' else 'Guard' if d['kind']=='COMBAT_DONE' and 'Guard' in d['options'] else d['options'][0]
            c.choose(d['options'].index(choice))
            if session.error: raise session.error
        else: raise AssertionError('Baaz never entered legal attack range')
        if screen.holding(c): c.key('space',' ')
        c.key('a','a')
        assert session.decision['kind']=='TARGET'
        choices=[v for v in session.decision['options'] if '#' in v and town.field(b.chars[int(v.rsplit('#',1)[1])],'side')!=town.field(b.chars[b.data['actor']],'side')]
        assert choices
        target=int(choices[0].rsplit('#',1)[1]); tx,ty=b.position(target)
        before=game.state_hash(); seed=game.s.seed
        c.key('m','m')
        while c.aim_cell[0]!=tx: c.key('Right' if c.aim_cell[0]<tx else 'Left')
        while c.aim_cell[1]!=ty: c.key('Down' if c.aim_cell[1]<ty else 'Up')
        assert c.aim_choice() is not None and 'Target' in c.aim_options()
        aimed=screen.render(c); ox,oy=screen.combat_view(c); x,y=8+(tx-ox)*24,8+(ty-oy)*24
        pixels,palette=c.assets.combat_icon(game,target)
        assert all(aimed.rows[y+dy][x+dx]==(palette[pixels[dy][dx]] if pixels[dy][dx] else value)
                   for dy,row in enumerate(cursor) for dx,value in enumerate(row))
        assert game.state_hash()==before and game.s.seed==seed
        result['C3']=digest(aimed)
        count=sum(e['event']=='attack' for e in game.combat_log)
        c.key('Return')
        assert not session.error and sum(e['event']=='attack' for e in game.combat_log)>count
    finally: session.close()
    return result


def check_spell_line():
    from sm.titles.cok._combat_test import ambush
    from sm.titles.cok import magic
    magic_missile = lambda: next(i for i in range(1, 108) if magic.spell(i).name == 'Magic Missile')
    assert screen.casting_spell(['A Casts a Spell', dict(kind='bolt', spell=2), 'B is blessed'], 2) == 2
    assert screen.casting_spell(['A Casts a Spell', dict(kind='bolt', spell=2), dict(kind='attack')], 2) is None
    assert screen.casting_spell(['A Casts a Spell', dict(kind='move', actor=1)], 0) is None
    session = ambush(); now = [0.0]
    try:
        c = screen.Controller(session); c.clock = lambda: now[0]
        c.choose(session.decision['options'].index('Cast')); c.choose(session.decision['options'].index('Bless'))
        c.choose(session.decision['options'].index('Cast')); c.choose(session.decision['options'].index('Magic Missile'))
        d = session.decision; assert d['kind'] == 'TARGET' and d['info']['spell'] == magic_missile(), d
        now[0] = c.report_at + sum(screen.report_hold(e) for e in c.report) + .01
        seen = drawn_text(c, True)
        assert (0, 23, 'Spell:Magic Missile', 10) in seen and not any(v.startswith('Range') for _, _, v, _ in seen), seen
        c.choose(next(n for n, v in enumerate(d['options']) if v.startswith('BAAZ')))
        k = next(n for n, e in enumerate(c.report) if isinstance(e, dict) and e['kind'] == 'bolt')
        now[0] = c.report_at + sum(screen.report_hold(e) for e in c.report[:k]) + .01
        assert (0, 23, 'Spell:Magic Missile', 10) in drawn_text(c, True), drawn_text(c)
        now[0] = c.report_at + sum(screen.report_hold(e) for e in c.report) + .01
        assert not any(v.startswith('Spell:') for _, _, v in drawn_text(c))
    finally: session.close()


def check_read_06_4():
    session = outpost_session()
    try:
        session.step(0); session.step(0)
        c = screen.Controller(session)
        click(c, 'Magic')
        for _ in range(4): c.key('Down')
        click(c, 'Memorize')
        seen = drawn_text(c, colours=True)
        slots = session.decision['info']['slots'].splitlines()
        assert slots and all((1, 18+n, line, 10) in seen for n, line in enumerate(slots)), seen
        assert all(row <= 15 for _, row, value, _ in seen if value.strip() in session.decision['options'] and value != 'Exit')
    finally: session.close()


def check_read_06_5():
    session = outpost_session()
    try:
        session.step(0); session.step(0)
        c = screen.Controller(session)
        for key in ('Down', 'Up'):
            c.key(key)
            assert (1, 18, 'The party makes camp...', 10) in drawn_text(c, colours=True)
        click(c, 'Magic'); click(c, 'Exit')
        assert not any(t == 'The party makes camp...' for _, _, t in drawn_text(c))
    finally: session.close()


def check_read_07_2():
    from sm.titles.cok import shop
    session = outpost_session()
    try:
        c = screen.Controller(session)
        click(c, 'NEXT'); click(c, 'TEMPLE')
        c.key('Up'); assert session.game.s.sel == len(session.game.s.party)-1
        c.key('Down'); c.key('Down'); assert session.game.s.sel == 1
        name = shop.member_name(session.game.s.party[1])
        assert (17, 5, name[:15], 15) in drawn_text(c, colours=True)
        click(c, 'Heal')
        assert (1, 1, name+', how can we help you?') in drawn_text(c)
        assert session.decision['kind'] != 'WHO'
        click(c, 'Exit'); click(c, 'View')
        assert session.decision['kind'] == 'CREATE_VIEW'
        assert any(name in value for _, _, value in drawn_text(c))
    finally: session.close()


def check_read_08_3():
    from sm.titles.cok import shop
    for coin, label, query in ((shop.STEEL, 'Steel', 'How much steel  will you take? '),
                               (shop.GEMS, 'Gems', 'How Many Gems  will you take? ')):
        session = outpost_session()
        try:
            c = screen.Controller(session); click(c, 'ARMOURY'); click(c, 'Pool')
            session.game.s.treasure_money[coin] = 2
            click(c, 'Take'); click(c, label); c.key('1', '1')
            assert (0, 24, query) in drawn_text(c) and (len(query), 24, '1') in drawn_text(c)
        finally: session.close()


def check_read_08_4():
    check_appraise()


def check_read_08_6():
    from sm.titles.cok import shop
    session = outpost_session()
    try:
        c = screen.Controller(session); click(c, 'ARMOURY')
        c.key('Down'); assert session.game.s.sel == 1
        name = shop.member_name(session.game.s.party[1])
        assert (17, 5, name[:15], 15) in drawn_text(c, colours=True)
        click(c, 'Buy')
        assert session.decision['kind'] == 'LIST' and (0, 24, 'Items: ') in drawn_text(c)
        click(c, 'Exit'); click(c, 'View')
        assert session.decision['kind'] == 'CREATE_VIEW'
        assert any(name in value for _, _, value in drawn_text(c))
    finally: session.close()


def check_read_09_2():
    from sm.titles.cok import creation, shop
    session = outpost_session()
    try:
        c = screen.Controller(session); char = session.game.s.party[0]; name = shop.member_name(char)
        for order, word, ending in ((1, 'sword', '.'), (2, 'rose', '')):
            char.b[creation.F['knight_order']] = order
            verdict = name+' is too inexperienced'+ending
            session.decision = dict(session.decision, kind='CREATE_KNIGHT', options=('Exit',), info=dict(prompt=verdict))
            c.capture_text(); seen = drawn_text(c)
            assert {(19-len(name)//2, 3, name), (7, 5, 'is petitioning to become a'),
                    (10, 7, 'Knight Of The '+word), (18+order-(len(name)+21)//2, 9, verdict)} <= set(seen), seen
    finally: session.close()


def check_read_11_2():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        for outcome in ('The party has fled.', 'You have lost the fight.', 'The party has won.', 'The party has found Treasure!'):
            session.decision = dict(session.decision, kind='ACK', options=('Continue',),
                                    info=dict(message=outcome+' Each character receives 0 experience points.'))
            c.capture_text()
            assert (1, 3, outcome, 10) in drawn_text(c, colours=True)
    finally: session.close()


def check_read_11_3():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        session.decision = dict(session.decision, kind='ACK', options=('Continue',),
                                info=dict(message='The party has won. Each character receives 1278 experience points.'))
        c.capture_text(); seen = drawn_text(c, colours=True)
        assert {(1, 5, 'Each character receives 1278', 10), (1, 7, 'experience points.', 10),
                (0, 24, 'press <enter>/<return> to continue', 15)} <= set(seen), seen
    finally: session.close()


def check_read_11_4():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        session.decision = dict(session.decision, kind='ACK', options=('Continue',),
                                info=dict(message='KAL takes and hides his share.\nTIKA takes and hides her share.'))
        c.capture_text(); seen = drawn_text(c, colours=True)
        assert {(5, 5, 'KAL takes and hides his share.', 10), (5, 7, 'TIKA takes and hides her', 10),
                (5, 8, 'share.', 10), (0, 24, 'press <enter>/<return> to continue', 15)} <= set(seen), seen
    finally: session.close()


def check_read_06_6():
    session = outpost_session()
    try:
        session.step(0); session.step(0); session.game.rest_poll = True
        c = screen.Controller(session); c.clock = lambda: 0
        click(c, 'Rest'); c.key('Left'); c.key('Up'); click(c, 'Rest')
        assert session.decision['kind'] == 'CAMP_RESTING'
        c.key('x', 'x'); seen = drawn_text(c, colours=True)
        assert {(1, 17, 'Rest Time:', 10), (0, 24, 'Stop Resting? ', 13)} <= set(seen), seen
        c.key('n', 'n'); assert session.decision['kind'] == 'CAMP_RESTING'
        c.key('Return'); assert (0, 24, 'Stop Resting? ') in drawn_text(c)
        c.key('y', 'y'); assert session.decision['kind'] == 'CAMP_MENU'
    finally: session.close()


def check_read_13_7():
    session = outpost_session()
    try:
        c = screen.Controller(session); step = session.step
        def sounded(answer):
            session.game.__dict__.setdefault('script_sounds', []).extend((10, 11))
            return step(answer)
        session.step = sounded
        c.choose(session.decision['options'].index('NEXT'))
        assert any(t == 'TEMPLE' for _, _, t in drawn_text(c))
        assert [command for _, command in screen.layout(c)['sound']] == [10, 11]
        drawn_text(c); assert len(screen.layout(c)['sound']) == 2
    finally: session.close()


def check_read_13_11():
    from sm.titles.cok import camp
    session = outpost_session()
    try:
        c = screen.Controller(session); vm = session.game.vm
        char = session.game.s.party[4]; name = camp.name(char)
        vm.out = ['\n'.join('line %d' % n for n in range(6))]; vm.text_start = 0
        vm.script_damage(char, 1); c.capture_text(); before = session.decision['i']
        assert (0, 24, 'Press any key to continue', 13) in drawn_text(c, colours=True)
        c.key('x', 'x')
        assert (1, 17, name+' is hit FOR 1 points of Damage.', 15) in drawn_text(c, colours=True)
        assert session.decision['i'] == before
        vm.out = ['\n'.join(['line %d' % n for n in range(5)]+['x'*38])]; vm.text_start = 0
        vm.script_damage(char, 1); c.capture_text()
        assert (0, 24, 'press <enter>/<return> to continue', 15) in drawn_text(c, colours=True)
        c.key('Return')
        assert (1, 17, '  '+name+' is hit FOR 1 points of Damage.', 15) in drawn_text(c, colours=True)
        c.lines = ['line %d' % n for n in range(7)]; c.text_page = 0
        assert (0, 24, 'Press any key to continue', 13) in drawn_text(c, colours=True)
    finally: session.close()


def check_read_13_14():
    session = outpost_session()
    try:
        c = screen.Controller(session)
        session.decision = dict(session.decision, kind='NUMBER', options=None, info=dict(prompt='Number: '))
        c.capture_text(); c.lines = []; answers = []; c.choose = answers.append
        for value in '0655367': c.key(value, value)
        assert {(0, 24, 'Number: ', 10), (9, 24, '065536', 15)} <= set(drawn_text(c, True)), drawn_text(c, True)
        c.key('Return'); assert answers == [0]
        c.entry = '65537'; c.key('Return'); assert answers == [0] and c.entry == '' and not c.error
        for value in '12x': c.key(value, value)
        assert c.entry == '12x'; c.key('Escape'); assert answers == [0] and c.entry == ''
        c.entry = '65535'; c.key('Return'); assert answers == [0, 65535]
        session.decision = dict(session.decision, info=dict(prompt='How much steel  will you take? ', max=455)); c.entry = ''
        for value in '4x56': c.key(value, value)
        assert c.entry == '455' and (31, 24, '455', 15) in drawn_text(c, True); c.key('Return'); c.entry = '9'; c.key('Escape')
        assert answers == [0, 65535, 455, 0], answers
        session.decision = dict(session.decision, kind='CREATE_NAME', info=dict(prompt='Character name: ', max_length=15)); c.entry = 'Bo'
        assert {(0, 24, 'Character name: ', 13), (17, 24, 'Bo', 15)} <= set(drawn_text(c, True))
    finally: session.close()


def check_read_20_9():
    from sm.titles.cok.ui import start_session
    session = area_session()
    try:
        c = screen.Controller(session); before = digest(screen.render(c))
        session.game.s.walls[1] = 0
        session.game.walls_filed = (2,)
        assert digest(screen.render(c)) == before
    finally: session.close()
    with TemporaryDirectory(prefix='cok-native-slots-') as directory:
        session = outpost_session()
        try:
            session.game.roster_directory = Path(directory)
            c = screen.Controller(session); click(c, 'INN'); c.key('Return'); click(c, 'Save')
            assert (0, 24, 'Save Which Game: ', 13) in drawn_text(c, colours=True)
            assert [label for _, label in screen.menu_items(session.decision)] == list('ABCDEFGHIJ')
            c.key('b', 'b')
            assert (0, 24, 'Saving...Please Wait', 10) in drawn_text(c, colours=True)
        finally: session.close()
        session = start_session(load='B', root=directory)
        try:
            c = screen.Controller(session)
            assert session.decision['info'].get('action') == 'main-menu' and len(session.game.s.party) == 6
            assert session.game.s.mode == 0 and session.game.s.prev_mode == 2
            assert (1, 4, 'SIR STRONGSWORD') in drawn_text(c)
        finally: session.close()


def check_read_19_7():
    from unittest.mock import patch
    session = outpost_session()
    try:
        c = screen.Controller(session); game = session.game; game.s.mode = 6
        main = dict(session.decision, kind='COMBAT_LOOT', options=('View', 'Take', 'Pool', 'Share', 'Exit', 'char-up', 'char-down'), info={})
        take = dict(main, options=('Money', 'Items', 'Exit'), info=dict(prompt='Take:'))
        session.decision = main; c.capture_text(); c.lines = []
        with patch.object(c.assets, 'picture', wraps=c.assets.picture) as picture:
            assert (0, 24, '') in drawn_text(c)
            picture.assert_called_with('PIC', 60, game.s.dataset)
        assert screen.layout(c)['animating']
        pixels = c.assets.picture('PIC', 60, game.s.dataset).parts[0].frames[0]
        frame = screen.render(c)
        assert tuple(bytes(row[24:112]) for row in frame.rows[24:112]) == pixels
        answers = []
        def step(answer):
            answers.append(answer)
            session.decision = take if session.decision is main else main
        session.step = step
        c.key('t', 't'); assert c.selected == 1
        assert (0, 24, 'Take: ', 13) in drawn_text(c, colours=True)
        c.key('Prior'); assert answers == [1, 1] and c.selected == 1
        c.key('Return'); c.key('9', '9'); assert answers[-2:] == [1, 1]
        c.key('8', '8'); assert answers[-1] == main['options'].index('char-up')
        session.decision = dict(main, options=main['options']+('char-first',)); c.capture_text()
        c.key('Home'); assert answers[-1] == 7
        session.decision = dict(main, kind='LIST', options=('One', 'Two', 'Exit'), info={}); c.capture_text()
        c.choose(0); assert c.selected == 0
        session.decision = dict(main, options=('Axe', 'Bow', 'Exit'), info=dict(prompt='Take which item?')); c.capture_text()
        c.key('Down'); assert c.selected == 1
    finally: session.close()


def check_read_18_5():
    from sm.titles.cok import camp, creation, magic
    from sm.titles.cok._magic_test import scroll
    session = outpost_session()
    try:
        game = session.game
        game.s.sel = next(n for n, char in enumerate(game.s.party) if char.b[creation.F['levels']+creation.MAGE])
        char = game.s.selc(); base = creation.F['memorized']; who = camp.name(char)
        char.b[base:base+58] = bytes((11, 49, 49))+bytes(55)
        c = screen.Controller(session); real = session.decision
        def show(kind, prompt, ids=None, labels=None, **info):
            if labels is None: labels = [magic.spell(n).name for n in ids]
            if ids is not None: info['spell_ids'] = ' '.join(map(str, ids))
            session.decision = dict(real, kind=kind, options=tuple(labels)+(() if prompt == 'Learn' else ('Exit',)), info=dict(prompt=prompt, **info))
            c.selected = c.page = 0; c.capture_text()
            before = game.state_hash(); seen = drawn_text(c, colours=True)
            assert game.state_hash() == before
            return seen
        seen = show('SPELL', 'Cast', labels=['Detect Magic', 'Hold Person (2)'])
        assert {(1, 1, who+"'s", 11), (len(who)+4, 1, 'Spells in Memory', 10),
                (1, 5, '1st Level', 13), (3, 6, 'Detect Magic', 0),
                (1, 7, '3rd Level', 13), (1, 8, '  Hold Person (2)', 10), (0, 24, 'Choose Spell: ', 13)} <= set(seen), seen
        assert {r['rect'][1] for r in screen.layout(c)['regions'] if 'select' in r and r['select'] < 2} == {48, 64}
        c.key('Up'); assert c.selected == 1
        answers = []; choose = c.choose; c.choose = answers.append
        click(c, 'Detect Magic'); assert answers == [0]; c.choose = choose
        ids = [row.id for row in magic.table() if row.level == 1][:20]
        seen = show('SPELL', 'memorize', ids, slots='Magic-User Spells:  4  3  2')
        assert (1, 18, 'Magic-User Spells:  4  3  2', 10) in seen
        assert screen.vertical(c)['window'] == (1, 5, 38, 15)
        assert all(40 <= r['rect'][1] <= 120 for r in screen.layout(c)['regions'] if 'select' in r and r['select'] < len(ids))
        c.key('n', 'n'); v = screen.vertical(c)
        assert v['first'] == len(v['nodes'])-11 and len(v['visible']) == 11
        c.key('p', 'p'); assert screen.vertical(c)['first'] == 0
        char.items.clear(); char.b[creation.F['robe_order']] = 1
        scroll(char, (49 | 128, 11, 49))
        seen = show('SPELL', 'Scribe', labels=[' *Hold Person', '  Detect Magic', '  Hold Person'])
        assert {(1, 5, '3rd Level', 13), (2, 6, '*Hold Person', 0), (1, 7, '1st Level', 13), (1, 9, '3rd Level', 13)} <= set(seen), seen
        c.view_item = 0
        seen = show('VIEW_ITEMS', 'Spells on Scroll', labels=['Hold Person', 'Detect Magic', 'Hold Person'])
        assert (len(who)+4, 1, 'Spells on Scroll', 10) in seen and (2, 6, '*Hold Person', 0) in seen
        seen = show('CREATE_SPELL', 'Learn', labels=['Detect Magic', 'Hold Person'])
        assert (len(who)+4, 1, 'Spells to Choose', 10) in seen
        assert [word for word, _ in screen.vertical(c)['words']] == ['Learn']
        seen = show('SPELL', 'Cast', [103, 5])
        assert (1, 5, 'Special', 13) in seen and (1, 7, '1st Level', 13) in seen
        for prompt, ending in (('Spells to Memorize', 'to Memorize'), ('Spells to Scribe', 'to Scribe')):
            seen = show('SPELL', prompt, [49 | 128])
            assert (len(who)+4, 1, 'Spells '+ending, 10) in seen
            assert [word for word, _ in screen.vertical(c)['words']] == ['Exit']
        game.s.g['cok.battle'] = dict(active=True)
        seen = show('COMBAT_SPELL', 'Cast', [11, 49], actor=game.s.sel)
        assert (1, 7, '3rd Level', 13) in seen and (0, 24, 'Choose Spell: ', 13) in seen
        assert screen.layout(c)['regions']
    finally: session.close()


def check_filed_wall_frame():
    session = area_session()
    try:
        game = session.game; c = screen.Controller(session)
        expected = digest(screen.render(c)); walls = list(game.s.walls)
        game.walls_filed = (1,); game.s.walls[0] = 0
        before = game.state_hash(); empty = screen.render(c)
        assert game.state_hash() == before and not screen.placements(game, c.assets)
        assert digest(empty) != expected and any(any(row[24:112]) for row in empty.rows[24:112])
        game.s.walls[:] = walls
        assert digest(screen.render(c)) == expected
        game.walls_filed = ()
        assert digest(screen.render(c)) == expected
    finally: session.close()


def check_loaded_view():
    from unittest.mock import patch
    from sm.titles.cok.ui import start_session
    kit = Path(__file__).resolve().parents[4] / 'local/kit/07_neraka'
    if not (kit / 'A/SAVGAMA.DAT').is_file():
        print('SKIP loaded-view frame: requires local/kit/07_neraka/A'); return
    witnesses = []
    for native in (False, True):
        with patch.object(town, 'refresh', wraps=town.refresh) as refresh:
            session = start_session(load=None if native else 'A', saves=kit, seed=0)
            try:
                c = screen.Controller(session, save_root=kit)
                assert session.decision['info'].get('action') == 'main-menu'
                if native:
                    click(c, 'Load Saved Game'); c.choose(session.decision['options'].index('A'))
                assert session.decision['info'].get('action') == 'main-menu' and refresh.call_count == 0
                game = session.game
                assert (game.s.dataset, game.s.block, game.s.x, game.s.y) == (2, 64, 13, 11)
                click(c, 'Begin Adventuring')
                assert session.decision['kind'] == 'MOVE' and refresh.call_count == 1
                assert not session.view_pending and not game.vm.display.get('blank')
                before = game.state_hash(); frame = screen.render(c)
                view = tuple(bytes(row[24:112]) for row in frame.rows[24:112])
                assert sum(bool(v) for row in view for v in row) > 4000
                assert game.state_hash() == before and refresh.call_count == 1
                assert (game.s.x, game.s.y) == (13, 11)
                c.key('Left'); c.key('Right')
                assert tuple(bytes(row[24:112]) for row in screen.render(c).rows[24:112]) == view
                witnesses.append(hashlib.sha256(b''.join(view)).hexdigest())
            finally: session.close()
    assert witnesses[0] == witnesses[1]
    return witnesses[0]


def check_read_21_menus():
    from sm.titles.cok.ui import start_session
    kind = lambda c: c.session.decision['kind']
    with TemporaryDirectory(prefix='cok-ui-menus-') as directory:
        c = screen.Controller(start_session(root=directory), save_root=directory)
        try:
            rows = c.session.decision['options']
            c.key('e', 'e'); assert kind(c) == 'CREATE_MENU'
            c.key('2', '2'); c.key('2', '2'); assert c.selected == 2
            c.key('8', '8'); assert c.selected == 1
            c.selected = rows.index('Exit to DOS'); c.key(' ', ' ')
            assert kind(c) == 'CREATE_QUIT' and c.session.decision['options'][c.selected] == 'No'
            c.key('Escape'); assert kind(c) == 'CREATE_QUIT'
            c.key('Return'); assert kind(c) == 'CREATE_MENU' and not getattr(c.session.game.s, 'stop', 0)
            assert c.selected == rows.index('Exit to DOS')
            c.selected = 0; c.key('s', 's'); assert kind(c) == 'CREATE_RACE'
            c.key('h', 'h'); c.key('2', '2'); assert kind(c) == 'CREATE_RACE' and c.selected == 1
            c.key(' ', ' '); assert kind(c) == 'CREATE_RACE'
            c.key('s', 's')
            while kind(c) != 'CREATE_ROLL': c.key('Return')
            assert c.session.decision['options'][c.selected] == 'No'
            c.key('Return'); assert kind(c) == 'CREATE_NAME'
            for ch in 'abcdefghijklmnopqrst': c.key(ch, ch)
            assert c.entry == 'abcdefghijklmno'
        finally: c.session.close()
    session = outpost_session()
    try:
        c = screen.Controller(session)
        c.key('Escape'); assert session.decision['options'][0] == 'INN'
        c.key('6', '6'); assert c.selected == 1
        c.key('n', 'n'); assert session.decision['options'][0] == 'VAULT' and c.selected == 0
        c.key('p', 'p'); c.key('a', 'a')
        assert kind(c) == 'SHOP_MENU' and session.decision['options'][c.selected] == 'Appraise'
        c.key('b', 'b'); assert kind(c) == 'LIST'
        items = len(session.game.s.party[session.game.s.sel].items); stay = session.decision['i']
        for ch in '214l': c.key(ch, ch)
        assert session.decision['i'] == stay and c.selected == 1
        c.key('b', 'b')
        assert session.decision['i'] != stay and len(session.game.s.party[session.game.s.sel].items) in (items, items+1)
    finally: session.close()
    session = area_session()
    try:
        c = screen.Controller(session); s = session.game.s; here = (s.x, s.y, s.dir)
        c.key('4', '4'); assert (s.x, s.y, s.dir) == here
        c.key('m', 'm'); c.key('4', '4'); assert s.dir == (here[2]+6) % 8
    finally: session.close()


def check_read_22_review():
    from sm.titles.cok import combat
    from sm.titles.cok._combat_test import ambush
    session = outpost_session(); real = session.decision
    try:
        game = session.game; c = screen.Controller(session); c.clock = lambda: 1e6
        def stand_in(kind, options, **info):
            session.decision = dict(real, kind=kind, options=options, info=info); c.selected = c.page = 0; c.capture_text()
        answers = []; choose = c.choose; c.choose = lambda index: answers.append(index) or True
        stand_in('VIEW_COIN', ['Platinum      3', 'Steel         50', 'Exit'], prompt='Select type of coin ')
        assert not screen.compact(session.decision) and screen.is_vertical(c)
        c.key('s', 's'); c.key('p', 'p'); c.key('2', '2'); c.key('s', 's'); assert answers == [0, 1], answers
        assert [r['rect'] for r in screen.layout(c)['regions'] if r.get('select') in (0, 1)] == [(160, 72, 152, 8), (160, 80, 152, 8)]
        stand_in('LIST', ['Exit']); assert c.key('Up') is False and c.key('2', '2') is False
        shown = dict(game.vm.display); session.decision = real; c.capture_text()
        for display in (dict(kind='SPRIT', dataset=1, id=0, pic=255, frame=1, head=None), dict(kind='PIC', dataset=1, id=9)):
            game.vm.display = display; game.vm.is3d, was = (lambda: True), game.vm.is3d
            try: screen.draw_picture(screen.Frame(), game, c.assets, 0)
            finally: game.vm.is3d = was
        game.vm.display = shown
        stand_in('CAMP_RESTING', ['Continue', 'Stop'], days=0, hours=1, minutes=0)
        regions = screen.layout(c)['regions']; assert len(regions) == 1 and regions[0]['key']['keysym'] == 'Return', regions
        c.choose = choose; session.decision = real; c.capture_text()
        c.key('a', 'a'); c.key('p', 'p'); c.key('e', 'e'); seen = drawn_text(c, True)
        assert (1, 17, 'As you Leave the Shopkeeper says,', 10) in seen and (15, 19, 'Do you want to go back', 15) in seen, seen
        assert (1, 20, 'and get your Money?', 15) in seen and (0, 24, 'Yes', 0) in seen and not any(t.startswith('51') for _, _, t, _ in seen)
        c.key('Escape'); assert session.decision['kind'] == 'SHOP_CONFIRM'; c.key('n', 'n'); assert session.decision['kind'] == 'MENU'
    finally: session.close()
    session = ambush(); now = [1e6]
    try:
        game = session.game; c = screen.Controller(session); c.clock = lambda: now[0]; b = combat.Battle(game)
        line = lambda: [t for t in drawn_text(c, True) if t[1] in (23, 24) and t[2] and not (len(t[2]) == 1 and t[3] == 15)]
        c.key('u', 'u'); assert session.decision['kind'] == 'VIEW_ITEMS' and screen.is_vertical(c)
        mark = session.decision['i']
        for key in ('2', 'y', ' ', 'n'): c.key(key, key)
        assert c.selected == 1 and session.decision['i'] == mark and (1, 3, 'Ready Item', 15) in drawn_text(c, True)
        c.key('Escape'); assert session.decision['kind'] == 'COMBAT_ACTION' and not any(row == 23 for _, row, _, _ in line()), line()
        c.key('a', 'a'); ally = next(int(v.rsplit('#', 1)[1]) for v in session.decision['options'] if '#' in v and not town.field(b.chars[int(v.rsplit('#', 1)[1])], 'side'))
        tx, ty = b.position(ally); c.key('m', 'm')
        while c.aim_cell[0] != tx: c.key('6' if c.aim_cell[0] < tx else '4', '6' if c.aim_cell[0] < tx else '4')
        while c.aim_cell[1] != ty: c.key('2' if c.aim_cell[1] < ty else '8', '2' if c.aim_cell[1] < ty else '8')
        c.key('Return'); assert line() == [(0, 24, 'Attack Ally: ', 13), (13, 24, 'Yes', 10), (17, 24, 'No', 0)], line()
        c.key('Return'); assert session.decision['kind'] == 'COMBAT_ACTION'
        c.key('m', 'm'); assert line() == [(0, 24, 'Move/Attack, Move Left = 9', 13), (27, 24, 'Done', 0)], line()
        real = session.decision; session.decision = dict(real, info=dict(real['info'], prompt="can't go there")); now[0] = c.decided_at+.1
        assert line() == [(0, 24, "can't go there", 10)] and screen.layout(c)['animating']
        now[0] = c.decided_at+60; assert line()[0][3] == 13; session.decision = real
        answers = []; choose = c.choose; c.choose = lambda index: answers.append(index) or True
        dirs = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest']
        b.data['aim'] = b.position(b.data['actor']); b.data['aim_view'] = (0, 0)
        session.decision = dict(real, kind='COMBAT_SPELL_AIM', options=dirs+['Target', 'Exit'], info=dict(real['info'], spell=21)); c.capture_text()
        assert [t for t in line() if t[1] == 24] == [(0, 24, '(Use Cursor keys) ', 13), (18, 24, 'Target', 0)], line()
        for key in '89632147': c.key(key, key)
        assert answers == list(range(8)), answers
        for key in ('e', 'n', 'h', chr(92)): c.key(key, key)
        assert answers == list(range(8)); view = c.aim_view; c.aim_view = (view[0]-2, view[1]); c.key('5', '5'); assert c.aim_view == view and answers == list(range(8))
        c.key('t', 't'); c.key('Return'); c.key('Escape'); assert answers[8:] == [8, 8, 9]
        session.decision = dict(session.decision, options=dirs+['Exit']); answers.clear()
        assert (18, 24, 'Exit', 0) in line(); c.key('t', 't'); assert not answers; c.key('e', 'e'); c.key('Return'); assert answers == [8, 8]
        c.choose = choose; session.decision = real; del b.data['aim'], b.data['aim_view']; c.capture_text(); c.key('Escape')
        c.key('Alt-q'); now[0] = c.report_at
        for _ in range(400):
            step = screen.report_step(c)
            if step is None:
                if session.decision['kind'] != 'COMBAT_AUTO': raise AssertionError('no computer move seen')
                c.choose(session.decision['options'].index('Continue')); now[0] = c.report_at; continue
            entry = c.report[step[0]]
            if isinstance(entry, dict) and entry['kind'] == 'move' and entry.get('left') is not None and screen.holding(c):
                assert (0, 24, 'Move/Attack, Move Left = %d ' % entry['left'], 10) in drawn_text(c, True); break
            now[0] += screen.report_hold(entry)*c.effect_scale+.001
        else: raise AssertionError('no computer move seen')
    finally: session.close()
    session = ambush()
    try:
        game = session.game; c = screen.Controller(session); c.clock = lambda: 1e6; b = combat.Battle(game)
        for name in ('status', 'active', 'hp'): town.put(b.chars[3], name, 5 if name == 'status' else 0)
        b.down(3); assert b.cells(3) == []
        c.key('c', 'c'); c.choose(next(n for n, v in enumerate(session.decision['options']) if str(v).startswith('Cure Light')))
        assert session.decision['kind'] == 'TARGET' and any(v.endswith('#3') for v in session.decision['options'])
        tx, ty = b.position(3)
        if screen.holding(c): c.key('space', ' ')
        c.key('m', 'm'); assert c.aim_manual
        while c.aim_cell[0] != tx: c.key('Right' if c.aim_cell[0] < tx else 'Left')
        while c.aim_cell[1] != ty: c.key('Down' if c.aim_cell[1] < ty else 'Up')
        assert 'Target' in c.aim_options(); c.key('Return'); assert town.field(b.chars[3], 'hp') > 0
    finally: session.close()
    from sm.titles.cok.ui import start_session
    kit = Path(__file__).resolve().parents[4] / 'local/kit/01_outpost'
    if not (kit / 'A/SAVGAMA.DAT').is_file():
        print('SKIP party-menu questions: requires local/kit/01_outpost/A'); return
    session = start_session(load='A', saves=kit, seed=0)
    try:
        c = screen.Controller(session, save_root=kit); c.clock = lambda: 1e6; rows = session.decision['options']
        c.selected = rows.index('View Character'); c.key('Return'); seen = drawn_text(c, True)
        assert session.decision['kind'] == 'CREATE_WHO' and (9, 15, 'View Character', 10) in seen and (15, 24, 'Select', 0) in seen, seen
        assert (0, 24, 'Pick Character ', 13) in seen and (1, 4, 'SIR STRONGSWORD', 15) in seen
        mark = session.decision['i']
        for key in ('2', 'i', 'g'): c.key(key, key)
        assert c.selected == 1 and session.decision['i'] == mark and (1, 5, 'ISTAN HORBIN', 15) in drawn_text(c, True)
        c.key('Up'); c.key('Up'); assert c.selected == len(session.game.s.party)-1
        c.key('e', 'e'); assert session.decision['info'].get('action') == 'main-menu'
        c.selected = rows.index('Exit to DOS'); c.key('Return'); seen = drawn_text(c, True)
        assert (0, 24, 'Quit to DOS ', 14) in seen and (16, 24, 'No', 0) in seen and (9, 20, 'Exit to DOS', 10) in seen, seen
        assert not any(col == 17 and row == 15 for col, row, _, _ in seen), 'the exploring frame under a party-menu question'
    finally: session.close()


def check_read_23_screens4():
    from sm.titles.cok import combat
    from sm.titles.cok._combat_test import ambush
    session = ambush()
    try:
        game = session.game; c = screen.Controller(session); c.clock = lambda: 1e6; b = combat.Battle(game)
        line = lambda: [t for t in drawn_text(c, True) if t[1] == 24 and t[2] and not (len(t[2]) == 1 and t[3] == 15)]
        from sm.titles.cok.creation import DELAY
        speed = game.s.g.get(DELAY); now = [1e6]; c.clock = lambda: now[0]
        assert abs(screen.pause(c)-.4) < 1e-9; game.s.g[DELAY] = 9; assert abs(screen.pause(c)-.9) < 1e-9
        c.report, c.report_at, c.report_for = ['Guarding'], 1e6, session.decision['i']
        now[0] = 1e6+.85; assert screen.report_step(c) is not None and screen.holding(c); now[0] = 1e6+.95; assert screen.report_step(c) is None
        game.s.g[DELAY] = 0; now[0] = 1e6; assert screen.report_step(c) is None and screen.pause(c) == 0
        c.effect_scale = 2; game.s.g[DELAY] = 4; assert abs(screen.pause(c)-.8) < 1e-9; c.effect_scale = 1
        c.report = []; c.clock = lambda: 1e6
        if speed is None: del game.s.g[DELAY]
        else: game.s.g[DELAY] = speed
        seen = drawn_text(c, True); assert {(0, 24, 'Move', 0), (5, 24, 'View', 10), (5, 24, 'V', 15), (10, 24, 'A', 15)} <= set(seen) and (0, 24, 'M', 15) not in seen, seen
        c.key('a', 'a'); start = c.aim_cell; mark = session.decision['i']
        seen = drawn_text(c, True); assert {(4, 24, 'N', 15), (9, 24, 'P', 15), (21, 24, 'C', 15), (28, 24, 'E', 15)} <= set(seen) and (14, 24, 'M', 15) not in seen, seen
        assert line() == [(0, 24, 'Aim:', 13), (4, 24, 'Next', 10), (9, 24, 'Prev', 10), (14, 24, 'Manual', 0), (21, 24, 'Center', 10), (28, 24, 'Exit', 10)], line()
        for key in ('Up', 'Down', 'Prior', '8', '2', '5', ' ', 't'): c.key(key, key if len(key) == 1 else '')
        assert c.aim_cell == start and not c.aim_manual and session.decision['i'] == mark
        c.key('6', '6'); assert (21, 24, 'Center', 0) in line(); c.key('Left'); c.key('4', '4'); assert (9, 24, 'Prev', 0) in line()
        c.key('Right'); c.key('Left'); assert c.aim_cell == start and (9, 24, 'Prev', 0) in line()
        c.key('n', 'n'); assert c.aim_cell != start and line()[1:5] == [(4, 24, 'Next', 0), (9, 24, 'Prev', 10), (14, 24, 'Manual', 10), (21, 24, 'Target', 10)], line()
        named = c.aim_cell
        c.key('m', 'm'); assert line() == [(0, 24, '(Use Cursor keys) ', 13), (18, 24, 'Target', 0)], line()
        c.key('e', 'e'); assert c.aim_manual; c.key('7', '7'); assert c.aim_cell == (named[0]-1, named[1]-1) and (18, 24, 'Exit', 0) in line()
        c.key('t', 't'); assert c.aim_manual; c.key('e', 'e')
        assert not c.aim_manual and c.aim_cell == named and line()[1:] == [(4, 24, 'Next', 10), (9, 24, 'Prev', 10), (14, 24, 'Manual', 0), (21, 24, 'Center', 10), (28, 24, 'Exit', 10)], line()
        c.key('Return'); assert c.aim_manual; c.key('Escape'); assert not c.aim_manual and session.decision['i'] == mark
        regions = screen.layout(c)['regions']
        assert regions[0] == dict(rect=(32, 192, 32, 8), key=dict(keysym='n', char='n')) and regions[-1]['keys'][0] == dict(keysym='m', char='m')
        c.key('Escape'); assert session.decision['kind'] == 'COMBAT_ACTION'
        c.key('c', 'c'); c.choose(next(n for n, v in enumerate(session.decision['options']) if str(v).startswith('Sleep')))
        if screen.holding(c): c.key('space', ' ')
        assert session.decision['kind'] == 'TARGET' and 'Ground' in session.decision['options'] and (4, 24, 'Next', 0) in line(), line()
        caster = c.aim_cell; c.key('n', 'n'); named = c.aim_cell; assert named != caster
        c.key('m', 'm'); assert session.decision['kind'] == 'COMBAT_SPELL_AIM' and c.aim_cell == named == tuple(b.data['aim'])
        assert [t for t in line() if t[0] == 0] == [(0, 24, '(Use Cursor keys) ', 13)], line()
        c.key('8', '8'); assert c.aim_cell == (named[0], named[1]-1)
        c.key('Escape'); assert session.decision['kind'] == 'TARGET' and c.aim_cell == named and c.aim_blank
        assert line() == [(0, 24, 'Aim:', 13), (4, 24, 'Next', 10), (9, 24, 'Prev', 10), (14, 24, 'Manual', 0), (21, 24, 'Center', 10), (28, 24, 'Exit', 10)], line()
        c.key('Return'); assert session.decision['kind'] == 'COMBAT_SPELL_AIM' and c.aim_cell == named; c.key('Escape')
        c.key('Escape'); assert line() == [(0, 24, 'Abort Spell? ', 14), (13, 24, 'Yes', 10), (17, 24, 'No', 0)], line()
    finally: session.close()
    from sm.titles.cok import camp
    session = outpost_session()
    try:
        c = screen.Controller(session); seen = drawn_text(c, True)
        assert {(0, 24, 'INN', 0), (4, 24, 'HALL', 10), (4, 24, 'H', 15)} <= set(seen) and not any(t[1] == 24 and t[0] in (5, 6, 7) and t[3] == 15 for t in seen), seen
        session.step(0); session.step(0)
        c = screen.Controller(session); c.clock = lambda: 1e6
        seen = drawn_text(c, True); assert {(0, 24, 'Save', 0), (5, 24, 'View', 10), (5, 24, 'V', 15)} <= set(seen), seen
        c.key('m', 'm'); [c.key('Down') for _ in range(4)]
        char = session.game.s.selc(); who = camp.name(char); base = camp.F['memorized']
        at = next(n for n in range(camp.MEMORY_SLOTS) if char.b[base+n]); char.b[base+at] |= camp.PENDING
        upper = lambda: [t for t in drawn_text(c, True) if t[1] <= 22 and t[2]]
        c.key('m', 'm'); listed = upper()
        assert session.decision['info'].get('title') == 'to Memorize' and (len(who)+4, 1, 'Spells to Memorize', 10) in listed, listed
        assert any(t[2].startswith(' *') and t[3] == 10 for t in listed), listed
        c.key('e', 'e'); seen = drawn_text(c, True)
        assert session.decision['info'].get('prompt') == 'Memorize These Spells? ' and upper() == listed, seen
        assert [t for t in seen if t[1] > 22 and t[2] and not (len(t[2]) == 1 and t[3] == 15)] == [(0, 24, 'Memorize These Spells? ', 14), (23, 24, 'Yes', 10), (27, 24, 'No', 0)], seen
        frame = screen.render(c); c.key('y', 'y'); assert session.decision['kind'] == 'CAMP_MENU' and digest(screen.render(c)) != digest(frame)
        from sm.titles.cok import effects, magic
        game = session.game; now = [1e6]; c.clock = lambda: now[0]
        effects.add_effect(char, 39, 10, 0, False); age = town.field(char, 'age', width=2)
        effects.call_handler(game, char, 39, effects.has_effect(char, 39), False)
        assert town.field(char, 'age', width=2) == age+1 and c.held() is not None and screen.layout(c)['animating']
        seen = [t for t in drawn_text(c, True) if t[1] >= 16 and t[2]]
        assert seen == [(1, 18, who, 11), (1, 19, 'ages', 10)], seen
        now[0] += screen.pause(c)+.01; assert c.held() is None and (1, 17, 'Magic', 10) in drawn_text(c, True)
        before = game.state_hash(); c.hold_resting = True
        effects.say(magic._roll(game, char, magic.spell(1)), char, 'is weakened')
        seen = [t for t in drawn_text(c, True) if t[1] >= 18 and t[2]]
        assert seen == [(1, 19, who, 11), (1, 20, 'is weakened', 10)] and game.state_hash() == before, seen
        c.key('Return'); assert c.held() is None and session.decision['kind'] == 'CAMP_MENU'
        queue, game.presentation = game.presentation, None
        effects.say(magic._roll(game, char, magic.spell(1)), char, 'is weakened'); game.presentation = queue; assert not queue
        real = session.decision; answers = []; choose = c.choose
        names = ['ITEM %02d' % n for n in range(30)]
        session.decision = dict(real, kind='LIST', options=names+['Exit'], info=dict(window='1 1 38 21', menu='Add')); c.selected = 0; c.capture_text()
        c.choose = lambda index: answers.append(index) or True
        rows = lambda: [(row, text) for col, row, text, colour in drawn_text(c, True) if col == 1 and row <= 21]
        words = lambda: [(text, colour) for col, row, text, colour in drawn_text(c, True) if row == 24 and text and not (len(text) == 1 and colour == 15)]
        assert words() == [('Add', 0), ('Next', 10), ('Exit', 10)], words()
        c.key('p', 'p'); c.key('Prior'); c.key('Up'); assert c.selected == 20 and rows()[0] == (1, 'ITEM 00'), (c.selected, rows()[:2])
        c.key('2', '2'); c.key('Down'); c.key('Down'); assert c.selected == 2
        c.key('3', '3'); assert c.selected == 11 and rows()[0] == (1, 'ITEM 09') and rows()[-1] == (21, 'ITEM 29'), (c.selected, rows()[0])
        assert words() == [('Add', 0), ('Prev', 10), ('Exit', 10)], words()
        c.key('n', 'n'); c.key('Next'); assert c.selected == 11
        c.key('9', '9'); assert c.selected == 2 and rows()[0] == (1, 'ITEM 00')
        c.key('Right'); assert c.selected == 2 and words() == [('Add', 10), ('Next', 0), ('Exit', 10)], words()
        c.key('Return'); assert c.selected == 11 and words() == [('Add', 10), ('Prev', 0), ('Exit', 10)] and not answers, words()
        c.key('6', '6'); c.key('Return'); assert answers == [30], answers
        c.key('4', '4'); c.key('Left'); c.key('Return'); assert answers == [30, 11] and words()[0] == ('Add', 0), (answers, words())
        c.key('i', 'i'); c.key('1', '1'); c.key(' ', ' '); assert answers == [30, 11]
        c.key('p', 'p'); c.key('a', 'a'); assert answers == [30, 11, 2] and words()[0] == ('Add', 0), (answers, words())
        c.choose = choose
        shown = dict(game.vm.display); game.vm.display = dict(kind='BIGPIC', id=255, dataset=1)
        session.decision = dict(real, kind='WHO', options=[camp.name(m) for m in game.s.party], info=dict(at=1, prompt='WHO GOES FIRST?')); c.capture_text()
        seen = drawn_text(c, True); answers.clear(); c.choose = lambda index: answers.append(index) or True
        assert (0, 24, 'WHO GOES FIRST? ', 13) in seen and (16, 24, 'Select', 0) in seen and not any(col == 17 for col, _, _, _ in seen), seen
        assert not any('select' in r for r in screen.layout(c)['regions'])
        c.selected = 0; c.key('Down'); c.key('Return'); assert answers == [1]
        game.vm.display = shown; c.choose = choose; session.decision = real; c.capture_text()
        from sm.titles.cok import creation
        def asked(kind, options, **info):
            session.decision = dict(real, kind=kind, options=options, info=info); c.selected = 1 if options else 0; c.entry = ''; c.capture_text()
            return drawn_text(c, True)
        plain = asked('CREATE_OVERWRITE', ['Yes', 'No'], prompt='Overwrite KAL? ')
        assert not any(text in ('old', 'new') for _, _, text, _ in plain), plain
        game.s.g[creation.PENDING] = bytes(char.b), tuple(bytes(i) for i in char.items), tuple(bytes(e) for e in char.effects)
        try:
            for kind, options, prompt, colour in (('CREATE_SAVE', ['Yes', 'No'], 'Save KAL? ', 13), ('CREATE_OVERWRITE', ['Yes', 'No'], 'Overwrite KAL? ', 14),
                                                  ('CREATE_FILE_NAME', None, 'New file name: ', 10)):
                seen = asked(kind, options, prompt=prompt, max_length=8)
                assert {(8, 6, 'old', 15), (3, 10, 'ready   action', 15), (8, 12, 'new', 15), (3, 16, 'ready   action', 15), (0, 24, prompt, colour)} <= set(seen), (kind, seen)
                assert not any(text == 'Hit Points' for _, _, text, _ in seen[-12:]), kind
            lit = screen.render(c); assert any(lit.rows[52][x] for x in range(24, 48)) and any(lit.rows[100][x] for x in range(96, 120))
            seen = asked('CREATE_NAME', None, prompt='Character name: ', max_length=15)
            assert any(text == 'Hit Points' for _, _, text, _ in seen) and (0, 24, 'Character name: ', 13) in seen and not any(text == 'old' for _, _, text, _ in seen[-40:])
        finally: del game.s.g[creation.PENDING]
        session.decision = real; c.capture_text()
        now[0] = 2e6; c.decided_at = c.report_at = now[0]; game.presentation.append(dict(kind='script-hold', delay=2.0))
        assert c.held() is not None; now[0] += 1.9; assert c.held() is not None
        now[0] += .2; assert c.held() is None and c.decided_at == c.report_at == now[0]
        game.presentation.append(dict(kind='script-hold', delay=2.0)); assert c.held() is not None
        mark = session.decision['i']; now[0] += .5; c.key('Return')
        assert c.held() is None and session.decision['i'] == mark and c.decided_at == now[0]
    finally: session.close()


def check_read_25_slow_text():
    from sm.titles.cok.creation import DELAY
    session = outpost_session()
    try:
        now = [1e6]; c = screen.Controller(session); c.clock = lambda: now[0]
        window = lambda elapsed: [t for t in drawn_text(c, True, elapsed) if 17 <= t[1] <= 22 and t[0] == 1 and t[2]]
        assert c.slow is None and window(1) == window(0) != [] and not screen.revealed(c)
        c.choose(0); whole = window(0); first = whole[0][2]
        assert c.slow and len(first) > 8 and window(1) == [] and screen.layout(c)['animating']
        now[0] += 5*.012+.001; assert window(1) == [(1, 17, first[:5], whole[0][3])] and window(0) == whole
        now[0] += .012*len(first); assert window(1)[0] == whole[0]
        now[0] += 60; assert window(1) == whole and screen.revealed(c) is None and not c.slow is None
        session.game.s.g[DELAY] = 0; c.slow = (c.slow[0], 0, now[0]); assert window(1) == whole
    finally: session.close()


def check_read_24_quit_to_dos():
    from sm.titles.cok.ui import start_session
    line = lambda c: [t for t in drawn_text(c, True) if t[1] == 24 and t[2] and not (len(t[2]) == 1 and t[3] == 15)][:3]
    with TemporaryDirectory(prefix='cok-ui-quit-') as directory:
        session = outpost_session(); session.game.roster_directory = Path(directory)
        try:
            c = screen.Controller(session, save_root=directory); c.clock = lambda: 1e6
            c.choose(0); c.choose(0); c.key('s', 's'); c.key('c', 'c')
            assert (Path(directory)/'C'/'SAVGAMC.DAT').exists() and line(c) == [(0, 24, 'Quit TO DOS ', 14), (12, 24, 'Yes', 10), (16, 24, 'No', 0)], line(c)
            c.key('Return'); assert session.decision['info'].get('prompt') == 'Camp' and not c.quit_requested
            c.key('s', 's'); c.key('c', 'c'); c.key('y', 'y'); assert c.quit_requested and session.game.exit_game
        finally: session.close()
        session = outpost_session(); session.game.roster_directory = Path(directory)
        try:
            c = screen.Controller(session, save_root=directory); c.clock = lambda: 1e6; game = session.game
            del game.s.party[1:]; game.s.sel = 0
            c.choose(0); c.choose(0); c.key('a', 'a'); c.key('d', 'd'); c.key('Return')
            assert line(c) == [(0, 24, 'quit TO DOS: ', 14), (13, 24, 'Yes', 10), (17, 24, 'No', 0)], line(c)
            c.key('n', 'n'); assert not c.quit_requested and len(game.s.party) == 1
            c.key('d', 'd'); c.key('Return'); c.key('y', 'y'); assert c.quit_requested and game.exit_game and not game.s.party
        finally: session.close()
        session = start_session(root=directory)
        try:
            c = screen.Controller(session, save_root=directory); c.clock = lambda: 1e6
            assert (18, 24, 'Select', 0) in drawn_text(c, True), [t for t in drawn_text(c, True) if t[1] == 24]
            c.selected = session.decision['options'].index('Exit to DOS'); c.key('Return')
            assert [t for t in drawn_text(c, True) if t[1] == 24 and t[2] and not (len(t[2]) == 1 and t[3] == 15)][-3:] == [(0, 24, 'Quit to DOS ', 14), (12, 24, 'Yes', 10), (16, 24, 'No', 0)]
            c.key('Return'); assert session.decision['info'].get('action') == 'main-menu' and not c.quit_requested
            c.selected = session.decision['options'].index('Exit to DOS'); c.key('Return'); c.key('y', 'y')
            assert c.quit_requested and session.game.exit_game
        finally: session.close()


def test(folder=None, quick=False):
    from . import screen
    feel, screen.RESULT_FEEL = screen.RESULT_FEEL, 1.0
    try: return checks(folder, quick)
    finally:
        screen.RESULT_FEEL = feel
        assert feel == 5.0 and screen.report_hold('X is hit', .4) == screen.report_hold(dict(kind='attack'), .4) == 2.0 and screen.report_hold(dict(kind='move'), .4) == screen.MOVE_HOLD


def checks(folder=None, quick=False):
    if folder: os.environ['SM_COK'] = str(folder)
    if not os.environ.get('SM_COK'): return 'skipped (no Champions copy)'
    if quick: return check_geometry()
    result = check_geometry(); check_keyboard(); check_http(); check_files(); check_icon_frames(); check_camp(); check_shop(); check_clicks(); check_screens_two(); check_appraise(); check_text_pages(); check_plus(); check_aim_click(); check_replay_hold(); check_battle_begins(); check_guarding(); check_spell_line(); check_replay_follows(); check_sound(); check_slot_start()
    result['cursors']=check_cursors()
    check_picture_after_dungeon()
    check_filed_wall_frame()
    check_fight_keys_frame()
    result['loaded_view'] = check_loaded_view()
    for name, check in sorted(globals().items()):
        if name.startswith('check_read_'): check()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--folder')
    print(test(parser.parse_args().folder))
