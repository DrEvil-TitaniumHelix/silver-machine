import json
import os
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
import zlib

from sm.engine import Session
from sm.ui.plus import Settings
from sm.ui.png import decode, encode, edge_alpha
from sm.ui.web import Server
from . import screen, vga
from ._web_test import Browser


def png(rows, colour=6, extra=()):
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    def chunk(kind, data): return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n' + b''.join(chunk(k, d) for k, d in [
        (b'IHDR', struct.pack('>IIBBBBB', len(rows[0])//channels, len(rows), 8, colour, 0, 0, 0)),
        *extra, (b'IDAT', zlib.compress(b''.join(b'\0'+bytes(row) for row in rows))), (b'IEND', b'')])


def check_png():
    assert decode(png([[17, 83, 149, 255, 200, 3, 4, 0]])) == ((0xff115395, 0),)
    assert decode(png([[17, 83, 149]], 2)) == ((0xff115395,),)
    assert decode(png([[7, 8]], 0, [(b'tRNS', b'\0\7')])) == ((0, 0xff080808),)
    assert decode(png([[20, 128]], 4)) == ((0x80141414,),)
    assert decode(png([[0, 1]], 3, [(b'PLTE', b'\x11\x53\x95\0\0\0'), (b'tRNS', b'\xff\0')])) == ((0xff115395, 0),)
    rows = ((0xff010101,)*5, (0xff000000, 0xffcc0000, 0xffcc0000, 0xffcc0000, 0xff000000),
            (0xff000000, 0xffcc0000, 0xff000000, 0xffcc0000, 0xff000000),
            (0xff000000, 0xffcc0000, 0xffcc0000, 0xffcc0000, 0xff000000), (0xff000000,)*5)
    edged = edge_alpha(rows, 0, 8)
    assert not any(edged[0]) and edged[2][2] == 0xff000000, 'enclosed black armour became a hole'
    assert decode(encode(edged)) == edged
    rgba = ((0x80123456, 0xff000000, 0),)
    assert decode(encode(rgba)) == rgba, 'source alpha changed'
    for broken in (b'', png([[1, 2, 3, 4]])[:-1], png([[1, 2, 3, 4]])[:40]+b'broken', png([[2]], 3, [(b'PLTE', b'\0\0\0')])):
        try: decode(broken)
        except ValueError: pass
        else: raise AssertionError('Malformed PNG accepted')


def test():
    check_png()
    screen.SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='vga-', dir=screen.SAVE_ROOT) as temporary:
        root = Path(temporary)
        (root/'pixel.png').write_bytes(png([[17, 83, 149, 255, 99, 88, 77, 0], [13, 27, 51, 128, 12, 13, 14, 255]]))
        (root/'mods.json').write_text(json.dumps([dict(file='CPIC1.DAX', id=6, png='pixel.png')]))
        assets = vga.Assets(screen.Assets(), dict(vga_frame='ssb', mods_folder=str(root)))
        frame = vga.Frame(assets)
        frame.rect(0, 0, 320, 200, 4)
        frame.mod(10, 10, 'CPIC', 6, 1, (b'\1\1', b'\1\1'), transparent=0, colours=[15]*16)
        assert frame.rows[10][10] == 0xff115395 and frame.rows[10][11] == 4, 'recolour or transparency lost'
        assert frame.rows[11][10] == vga.blend(0x800d1b33, 4, assets.palette)
        assert vga.layer(0x80112233, 0, assets.palette) == 0x80112233
        assert vga.layer(0, 0x80112233, assets.palette) == 0x80112233
        assert vga.layer(0x80ff0000, 0x800000ff, assets.palette) == 0xc0aa0055
        frame.rect(10, 10, 1, 1, 3)
        assert frame.rows[10][10] == 3, 'later native drawing failed to occlude mod'
        packet = frame.packet(['synthetic'])
        assert len(packet) == 256784 and packet[10:12] == b'\1\0'
        assert packet[64784+(11*320+11)*3:64784+(11*320+11)*3+3] == bytes((12, 13, 14))
        frame = vga.Frame(assets)
        mod = assets.mods.picture('CPIC', 6, 1, 2, 2)
        frame.blit(-1, -1, mod, clip=(0, 0, 1, 1))
        assert frame.rows[0][0] == 0xff0c0d0e and frame.rows[0][1] == 0
        with patch.dict(os.environ, SM_CONFIG_HOME=str(root/'config'), DQK_ROOT=''):
            check_http(root)
            check_presentation(root)
            check_overlay(root)
        with patch.dict(os.environ, SM_CONFIG_HOME=str(root/'copy-config'), DQK_ROOT=''):
            check_dqk_copy(root)
    print('VGA: EGA identity, PNG alpha/colour/clip, packet, persistence and Original round-trip PASS')


def check_look_note(browser):
    note = json.loads(browser.request('/preferences')[0])['look_note']
    assert all(text in note for text in ('full-colour PNG mods', 'row below', 'frame and font', 'only mods look different'))
    page = browser.request('/plus')[0]
    assert all(text in page for text in (b'Dark Queen copy', b'id="dqk-browse"', b'Verify and save', b'id="dqk-clear"'))
    assert b'id="dqk-folder" type="text"' in page and b'Program Files (x86)' in page


def check_look_status(browser, visible):
    expected = ('VGA is using the Silver Blades frame (no Dark Queen copy set on the Plus page). '
                'Only mods will look different.')
    assert browser.layout()['look_status'] == (expected if visible else '')
    assert b'id="look-status" role="status" hidden' in browser.request('/')[0]


def check_dqk_copy(root):
    from sm.ui import vga_skin
    with Server(Session(engines=True), 0, save_root=root/'copy-saves') as server:
        worker = Thread(target=server.serve, daemon=True); worker.start()
        browser = Browser(server.server_port)
        try:
            original = browser.request('/frame?t=0')[0]
            state = server.controller.session.game.state_hash()
            check_look_note(browser)
            check_look_status(browser, False)
            assert json.loads(browser.request('/preferences')[0])['dqk_copy']['folder'] == ''
            browser.request('/preferences', dict(look='vga'))
            fallback = browser.request('/frame?t=0')[0]
            assert fallback[784:] == original
            check_look_status(browser, True)
            fake = root/'wrong-copy'; fake.mkdir()
            wrong = dict(folder=str(fake))
            failed = json.loads(browser.request('/dqk-intake', wrong, status=422)[0])
            assert not failed['ok'] and 'DISK1 and DISK3' in failed['message']
            assert not vga_skin.config_path().exists()
            browser.request('/dqk-intake', wrong, headers={'Origin': 'https://example.invalid'}, status=403)
            browser.request('/dqk-intake', wrong, headers={'X-SM-Build': 'old'}, status=409)
            for value in ({}, {'folder': 1}, {'folder': '\0'}, []):
                browser.request('/dqk-intake', value, status=400)
            with patch('sm.ui.folders.browse', return_value=(dict(ok=True, folder=str(fake), cancelled=False), 200)) as picker:
                assert json.loads(browser.request('/browse', {})[0])['folder'] == str(fake)
                picker.assert_called_once()
            with patch.dict(os.environ, DQK_ROOT=str(fake)):
                assert json.loads(browser.request('/preferences')[0])['dqk_copy']['source'] == 'DQK_ROOT'
                browser.request('/dqk-intake', dict(folder=''), status=409)
                check_look_status(browser, True)
            candidates = [Path(os.environ.get('SM_DQK_TEST_ROOT', ''))] if os.environ.get('SM_DQK_TEST_ROOT') else [
                Path('C:/Program Files/GOG Galaxy/Games/The Dark Queen of Krynn'),
                Path('C:/Program Files (x86)/GOG Galaxy/Games/The Dark Queen of Krynn')]
            copy = next((p for p in candidates if (p/'DISK1/GAME.FON').is_file()), None)
            if copy is None:
                print('SKIP Dark Queen copy success: no installed copy; failure/clear/status checks passed')
            else:
                result = json.loads(browser.request('/dqk-intake', dict(folder=str(copy)))[0])
                assert result['dqk_frame'] and result['dqk_copy']['edition'] in ('GOG', "Collector's CD")
                assert vga_skin.configured() == str(copy.resolve())
                assert json.loads(vga_skin.config_path().read_text()) == dict(folder=str(copy.resolve()))
                check_look_note(browser)
                check_look_status(browser, False)
                changed = browser.request('/frame?t=0')[0]
                assert changed != fallback and server.controller._vga_assets.native is not None
                native = server.controller._vga_assets.native
                browser.request('/dqk-intake', dict(folder=str(copy)))
                assert browser.request('/frame?t=0')[0] == changed
                assert server.controller._vga_assets.native is not native
                browser.request('/dqk-intake', wrong, status=422)
                assert vga_skin.configured() == str(copy.resolve())
                assert browser.request('/frame?t=0')[0] == changed
                browser.request('/preferences', dict(look='original'))
                assert browser.request('/frame?t=0')[0] == original
                check_look_status(browser, False)
                browser.request('/preferences', dict(look='vga'))
            browser.request('/dqk-intake', dict(folder=''))
            assert vga_skin.configured() is None
            assert browser.request('/frame?t=0')[0] == fallback
            check_look_status(browser, True)
            browser.request('/preferences', dict(look='original'))
            assert browser.request('/frame?t=0')[0] == original
            check_look_status(browser, False)
            assert state == server.controller.session.game.state_hash()
        finally:
            server.stopping = True; worker.join(3); browser.close()


def check_overlay(root):
    from ._presentation_test import scene
    folder = root/'icons'; folder.mkdir()
    image = ((0, 0xff113355, 0), (0x80123456, 0xff000000, 0xff778899), (0, 0xff224466, 0))
    (folder/'hero.png').write_bytes(encode(image))
    (folder/'mods.json').write_text(json.dumps([dict(kind='icon', slot=0, png='hero.png')]))
    mods = vga.Mods(folder); mods.validate()
    assert mods.read(mods.icons[('slot', 0)]) == image
    game, battle, ui = scene()
    settings = Settings(root/'overlay.json')
    settings.update(dict(look='vga', vga_frame='ssb', mods_folder=str(folder))); ui.apply_plus(settings)
    assets = vga.assets_for(ui, screen.Assets())
    before = game.s.hash(game.vm)
    original = screen.render_player(ui, screen.Assets())
    frame = screen.render_player(ui, assets)
    assert frame.rows == [list(row) for row in original.rows] and game.s.hash(game.vm) == before
    assert len(frame.overlay['icons']) == 1 and frame.overlay['icons'][0]['rect'][2:] == [24, 34]
    assert frame.overlay['draws'][1]['fit'] and 'base64,' in frame.overlay['draws'][1]['image']
    actor = battle.chars[0]; battle.record(actor)[6] = 20
    battle.move(actor, battle.legal_moves(actor)[0])
    moved = next(e for e in game.presentation if e['kind'] == 'move')
    moved_frame = screen.render_presentation(ui, moved, assets)
    x0, y0 = screen.player_viewport(SimpleNamespace(session=SimpleNamespace(game=moved['scene'],
        decision=dict(kind='COMBAT_ACTION', options=['done'], info={'actor': 0})), selected=0))
    x, y, _ = moved['scene'].s.g['combat.positions'][0]
    assert moved_frame.overlay['icons'][0]['rect'] == [8+(x-x0)*24, -2+(y-y0)*24, 24, 34]
    assert moved_frame.rows == [list(row) for row in screen.render_presentation(ui, moved, screen.Assets()).rows]
    battle.kill(actor)
    death = next(e for e in game.presentation if e['kind'] == 'death')
    dying = screen.render_presentation(ui, death, assets)
    assert not dying.overlay['draws'][-1].get('fit'), 'native death effect must cover the mod'
    final = screen.render_presentation(ui, game.presentation[-1], assets)
    assert not final.overlay['icons'], 'dead icon persisted'
    settings.update(dict(look='original')); ui.apply_plus(settings)
    assert not hasattr(screen.render_player(ui, screen.Assets()), 'overlay')
    for entry in (dict(kind='icon', slot=True, png='hero.png'), dict(kind='icon', slot=6, png='hero.png'),
                  dict(kind='icon', slot=0, head=0, body=0, png='hero.png'),
                  dict(file='CHEAD', id=0, png='hero.png'), dict(kind='icon', slot=0, png='hero.png', transparent='#000000')):
        (folder/'mods.json').write_text(json.dumps([entry]))
        try: vga.Mods(folder)
        except ValueError: pass
        else: raise AssertionError('Invalid icon mapping accepted')


def check_presentation(root):
    from ._presentation_test import scene
    game, battle, ui = scene()
    settings = Settings(root/'presentation.json')
    settings.update(dict(look='vga', vga_frame='ssb')); ui.apply_plus(settings)
    game.presentation_footer = vga.capture_footer(ui)
    game.presentation_footer.vga = (bytes([17])*320,) + game.presentation_footer.vga[1:]
    battle.attack(*battle.chars)
    event = next(e for e in game.presentation if e['kind'] == 'swing')
    state = game.s.hash(game.vm)
    a = screen.render_presentation(ui, event, vga.assets_for(ui, screen.Assets()))
    assert a.rows[184] == [17]*320
    settings.update(dict(look='original')); ui.apply_plus(settings)
    b = screen.render_presentation(ui, event, screen.Assets())
    c = screen.render_presentation(ui, dict(event, footer=tuple(event['footer'])), screen.Assets())
    assert b.rows == c.rows and max(max(row) for row in b.rows) < 16
    assert game.s.hash(game.vm) == state


def check_http(root):
    with Server(Session(engines=True), 0, save_root=root/'saves') as server:
        worker = Thread(target=server.serve, daemon=True); worker.start()
        browser = Browser(server.server_port)
        try:
            original = browser.request('/frame?t=0')[0]
            state = server.controller.session.game.state_hash()
            browser.request('/preferences', dict(look='vga', vga_frame='ssb', mods_folder=str(root)))
            packet = browser.request('/frame?t=0')[0]
            assert len(packet) == 64784 and packet[784:] == original
            assert packet[16:64] == bytes(c for rgb in screen.PALETTE for c in rgb)
            layout = json.loads(browser.request('/layout')[0])
            assert struct.unpack_from('<I', packet, 12)[0] == layout['frame_revision']
            captured = vga.capture(server.controller)
            assert b''.join(vga.background_rows(captured, screen.Assets())) == original
            browser.request('/preferences', dict(look='original'))
            assert browser.request('/frame?t=0')[0] == original
            assert state == server.controller.session.game.state_hash()
            for values in (dict(look='bad'), dict(mods_folder=True), dict(vga_frame='bad'), dict(mods_folder=str(root/'missing'))):
                browser.request('/preferences', values, status=400)
            assert Settings(root/'config/plus.json').options['look'] == 'original'
        finally:
            server.stopping = True; worker.join(3); browser.close()
