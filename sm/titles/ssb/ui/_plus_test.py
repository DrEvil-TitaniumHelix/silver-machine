"""GU-117: persistence, manual precedence, native bytes and timed display boundaries."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch

from sm.engine import Session
from sm.titles.ssb import rec
from sm.titles.ssb.host import Game
from sm.titles.ssb.units import creation, shops
from sm.titles.ssb.ui import screen, plus
from sm.ui.plus import DEFAULTS, Settings
from sm.ui.web import Server
from sm.titles.ssb.ui._web_test import Browser
from sm.titles.ssb.ui._presentation_test import scene


def test():
    screen.SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='sm-plus-', dir=screen.SAVE_ROOT) as temporary:
        root = Path(temporary)
        with patch.dict(os.environ, SM_CONFIG_HOME=str(root)):
            check_http(root)
            check_icons(root)
            check_holds()
    print('Plus: persisted options, manual body precedence, native bytes/hash/seed and service timings PASS')


def check_http(root):
    with Server(Session(engines=True), 0, save_root=root / 'saves') as server:
        worker = Thread(target=server.serve, daemon=True); worker.start()
        browser = Browser(server.server_port)
        try:
            game = server.controller.session.game
            before = (game.s.hash(game.vm), game.s.seed, list(game.trace), screen.snapshot(game, 'A', state=game.s.copy()))
            assert json.loads(browser.request('/preferences')[0])['options'] == DEFAULTS
            assert b'href="/plus"' in browser.request('/')[0]
            page = browser.request('/plus')[0]
            assert page.count(b'title="coming:') == 2 and b'Alpha' in page
            assert page.count(b'data-tab=') == 7 and b'id="journal-panel"' in page
            grid = json.loads(browser.request('/plus/data?tab=map')[0])
            if grid['available']:
                assert len(grid['cells']) == 256 and (grid['x'], grid['y'], grid['facing']) == (game.s.x, game.s.y, game.s.dir)
                assert grid['cells'][0]['walls'] == list(game.geo.map.cells[0].walls)
            rules = json.loads(browser.request('/plus/data?tab=rules')[0])
            assert len(rules['spells']) == 117 and len(rules['attacks']) == 18
            pictures = json.loads(browser.request('/plus/data?tab=gallery')[0])['pictures']
            assert pictures
            pic = pictures[0]
            image = json.loads(browser.request('/plus/data?tab=picture&file=%s&record=%s' % (pic['file'], pic['record']))[0])
            assert len(image['pixels']) == image['height'] and len(image['pixels'][0]) == image['width']
            browser.request('/plus/data?tab=picture&file=../ST.EXE&record=0', status=400)
            assert len(json.loads(browser.request('/plus/data?tab=guide')[0])['areas']) == 22
            assert len(json.loads(browser.request('/plus/data?tab=roster')[0])['party']) == len(game.s.party)
            report = dict(slot='A', steps='Open Plus, choose a tab.', expected='The tab opens.', actual='Test report.')
            written = json.loads(browser.request('/plus/bug', report)[0])
            assert Path(written['path']).is_relative_to(root) and json.loads(Path(written['path']).read_text()) == written['report']
            assert written['report']['title'] == 'ssb' and written['report']['slot'] == 'A'
            browser.request('/plus/bug', dict(report, path='../escape'), status=400)
            browser.request('/plus/bug', report, headers={'Origin': 'https://example.invalid'}, status=403)
            browser.request('/plus/bug', report, headers={'X-SM-Build': 'old'}, status=409)
            assert b'id="speed"' not in browser.request('/')[0]
            browser.request('/speed', {'scale': 4})
            browser.request('/preferences', {'message_hold': 2000, 'equipment_icon': True})
            assert server.controller.effect_scale == 4 and server.controller.equipment_icon
            for bad in ({'message_hold': True}, {'message_hold': 401}, {'equipment_icon': 1}, {'mods': True}, []):
                browser.request('/preferences', bad, status=400)
            browser.request('/preferences', {'equipment_icon': False}, headers={'Origin': 'https://example.invalid'}, status=403)
            browser.request('/preferences', {'equipment_icon': False}, headers={'X-SM-Build': 'old'}, status=409)
            browser.request('/frame')
            assert before == (game.s.hash(game.vm), game.s.seed, list(game.trace), screen.snapshot(game, 'A', state=game.s.copy()))
            saved = Settings(root / 'plus.json')
            assert saved.options == dict(DEFAULTS, effect_scale=4, message_hold=2000, equipment_icon=True)
        finally:
            server.stopping = True; worker.join(2); browser.close()
    with Server(Session(engines=True), 0, save_root=root / 'saves') as restarted:
        assert restarted.controller.equipment_icon and restarted.controller.message_hold == 2000
        restarted.set_preferences(DEFAULTS)


def check_icons(root):
    settings = Settings(root / 'plus.json')
    def edit(game, **_):
        creation.icon(game, game.s.party[0])
        game.ask('CAMP_MENU', ['exit'])
    with patch.object(Game, 'play', edit): session = Session(engines=True)
    try:
        ui = screen.Controller(session, save_root=root / 'saves')
        ui.apply_plus(settings)
        # Explicitly keep even the default body, then accept the icon.
        for key in ('p', 'w', 'k', 'e', 'e', 'y'): ui.key(key, key)
        c = session.game.s.party[0]
        assert settings.data['manual_bodies'][plus.identity(c.b)] == c.b[0x154]
        assert plus.body(c, Settings(root / 'plus.json').data['manual_bodies']) == c.b[0x154]
        settings.update({'equipment_icon': True}); ui.apply_plus(settings)
        original = (bytes(c.b), tuple(map(bytes, c.items)), session.game.s.hash(session.game.vm))
        for facing in (0, 4):
            for pose in (0, 1):
                assert screen.icon(session.game, c, facing, pose, controller=ui) == screen.icon(session.game, c, facing, pose)
        assert original == (bytes(c.b), tuple(map(bytes, c.items)), session.game.s.hash(session.game.vm))
        # Use native readied slots and every declared type without invoking recalc.
        from sm.titles.ssb.state import Char
        fighter = Char(c.b); fighter.b[0x111:0x118] = bytes((0, 0, 8, 0, 0, 0, 0))
        fighter.b[0x154] = plus.default_body(fighter.b)
        for kind, expected in ((18, 24), (27, 1), (20, 24), (5, 21)):
            weapon, shield = bytearray(67), bytearray(67)
            weapon[0x2E], weapon[0x34] = kind, 1
            shield[0x2E], shield[0x34] = 37, 1
            fighter.items = [weapon, shield]
            raw = bytes(fighter.b), tuple(map(bytes, fighter.items))
            assert plus.body(fighter, {}) == expected
            assert raw == (bytes(fighter.b), tuple(map(bytes, fighter.items)))
        fighter.b[0x154] = 12
        assert plus.body(fighter, {}) == 12, 'imported custom icon lost'
    finally: session.close()


def check_holds():
    assets = screen.Assets()
    for hold in (400, 800, 1200, 2000):
        game, _, ui = scene(); ui.message_hold = hold; game.s.g['67D6'] = 4
        before = game.s.hash(game.vm), game.s.seed
        ui.not_here_seen = False
        a = screen.Frame(); screen.not_here(ui, a, assets, 10)
        b = screen.Frame(); screen.not_here(ui, b, assets, 10 + (.38 if hold == 400 else hold / 1000 - .01))
        assert a.rows == b.rows
        after = screen.Frame(); screen.not_here(ui, after, assets, 10 + hold / 1000 + .01)
        assert a.rows != after.rows
        shops.name_message(game, game.s.party[0], 'service result')
        a = screen.Frame(); screen.name_notice(ui, a, assets, 20)
        b = screen.Frame(); screen.name_notice(ui, b, assets, 20 + hold / 1000 - .01)
        assert a.rows == b.rows
        after = screen.Frame(); screen.name_notice(ui, after, assets, 20 + hold / 1000 + .01)
        assert a.rows != after.rows
        shops.message(game, 'menu result', bottom=True, display=False)
        a = screen.Frame(); screen.buy_notice(ui, a, assets, 30)
        b = screen.Frame(); screen.buy_notice(ui, b, assets, 30 + hold / 1000 - .01)
        assert a.rows == b.rows
        after = screen.Frame(); screen.buy_notice(ui, after, assets, 30 + hold / 1000 + .01)
        assert a.rows != after.rows
        assert before == (game.s.hash(game.vm), game.s.seed)
