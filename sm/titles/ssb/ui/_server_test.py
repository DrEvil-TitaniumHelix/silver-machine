import json
from pathlib import Path
import shutil
import subprocess
import sys
import select
from http.client import HTTPException
from threading import Event, Thread
from unittest.mock import Mock, patch

from sm.engine import Session
from sm.titles.ssb.ui._web_test import Browser, running, view_and_saves
from sm.ui.web import BUILD_ID, Server


def rest_input(root):
    from sm.titles.ssb.host import Game
    from sm.titles.ssb.units import camp
    def rest_game(game, **_):
        game.s.r1[0x2D2] = 0
        game.ask('CAMP_MENU', ['rest'], purpose='rest duration', minutes=420)
        camp.rest(game, 420, interactive=True)
        game.ask('CAMP_MENU', ['exit'], purpose='magic')
    for key, remaining, polls in (('y', 385, 8), ('n', 0, 84)):
        with patch.object(Game, 'play', rest_game): session = Session(engines=True)
        with Server(session, 0, save_root=Path(root) / key) as server:
            browser, other = Browser(server.server_port), Browser(server.server_port)
            boundary, release = Event(), Event()
            capture = server.controller.capture_text
            def at_boundary():
                capture()
                decision = session.decision
                if decision and decision['kind'] == 'INPUT' and decision['info']['remaining'] == 385 and not boundary.is_set():
                    boundary.set()
                    assert release.wait(2), 'HTTP input blocked behind the rest frame'
            server.controller.capture_text = at_boundary
            worker = Thread(target=server.serve, daemon=True); worker.start()
            frame = None
            try:
                browser.key('r', 'r')
                frame = Thread(target=lambda: browser.request('/frame'), daemon=True); frame.start()
                assert boundary.wait(1), 'rest did not reach tick7'
                other.request('/key', dict(keysym='y', char='y'), headers={'Origin': 'https://example.invalid'}, status=403)
                assert not server.controller.held_keys, 'rejected key reached rest'
                assert other.key(key, key) == dict(queued=True, quit=False)
                assert frame.is_alive(), 'key waited for the frame to finish'
                release.set(); frame.join(2)
                assert not frame.is_alive() and not server.controller.rest_active
                assert session.game.s.g['camp.remaining'] == remaining
                assert sum(row[1] == 'INPUT' for row in session.game.trace) == polls
                assert session.decision['info']['purpose'] == 'magic'
            finally:
                release.set()
                if frame is not None: frame.join(2)
                browser.close(); other.close()
                server.stopping = True; worker.join(3)
                assert not worker.is_alive()


def blocking_path(root):
    session = Session(engines=True)
    with Server(session, 0, save_root=root) as server:
        browser, other = Browser(server.server_port), Browser(server.server_port)
        worker = Thread(target=server.serve, daemon=True)
        worker.start()
        try:
            for _ in range(4):
                browser.request('/frame')
                other.request('/frame')
            delivered = Event()
            with patch.object(session._a, 'put', side_effect=lambda _: delivered.set()):
                browser.connection.request('POST', '/key', json.dumps(dict(keysym='Return')),
                                           {'Content-Type': 'application/json'})
                assert delivered.wait(1), 'key did not reach the game queue'
                other.connection.request('GET', '/frame')
                assert not select.select([browser.connection.sock, other.connection.sock], [], [], .02)[0]
                session._q.put(session.decision)
                for client in (browser, other):
                    reply = client.connection.getresponse()
                    assert reply.status == 200
                    reply.read()
            print('#31 reproduction: idle closed connections pass; stalled game queue blocks BOTH pages')
        finally:
            browser.close(); other.close()
            server.stopping = True
            worker.join(3)
            assert not worker.is_alive()


def watchdog(root):
    session = Session(engines=True)
    session.timeout = .03
    with Server(session, 0, save_root=root) as server:
        safe_files = dict(server.controller.autosave_files)
        assert safe_files, 'no safe checkpoint before request'
        browser = Browser(server.server_port)
        worker = Thread(target=server.serve, daemon=True)
        worker.start()
        try:
            def pending_write(_):
                session.game.s.x ^= 1
            with patch.object(session._a, 'put', side_effect=pending_write):
                body, _ = browser.request('/key', dict(keysym='Return'), status=503)
                assert 'watchdog' in json.loads(body)['error']
            worker.join(1)
            assert not worker.is_alive() and server.stopping and session.decision is None
        finally:
            session._a.put(SystemExit('test finished'))
            browser.close()
            server.stopping = True
            worker.join(1)
    from zipfile import ZipFile
    with ZipFile(Path(root) / 'autosave.zip') as saved:
        assert {name: saved.read(name) for name in saved.namelist()} == safe_files, 'watchdog lost or replaced the safe save'


def builds(root):
    if not shutil.which('node'):
        print('#13 page reload check SKIPPED: node unavailable')
        return
    with running(root) as (browser, _):
        stale = Browser(browser.port, build='old-build')
        try:
            before = browser.decision()
            stale.clicks([], expect_errors=True)
            assert stale.page_stats['reloads'] == 1 and not stale.page_stats['listening']
            stale.clicks([], restart=True, expect_errors=True)
            stale.clicks([], tick=1000, expect_errors=True)
            assert stale.page_stats['reloads'] == 1 and stale.page_stats['hint']
            assert stale.page_stats['reconnecting'] and browser.decision() == before
            assert 'restart' not in (stale.page_stats.get('hintText') or '').lower(), 'told the player to restart'
        finally:
            stale.close()


KILL_SERVER = r'''
import sys
from threading import Event
from sm.engine import Session
from sm.ui import web
from sm.ui.web import Handler, Server
web.BUILD_ID = sys.argv[3]  # Lanes may edit sources while these child processes start.
class KillHandler(Handler):
    def reply(self, *args, **kwargs):
        if self.headers.get('X-Test-Stop'):
            if self.path.startswith('/frame'):
                self.send_response(200)
                self.send_header('Content-Length', str(len(args[0])))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(args[0][:32])
                self.wfile.flush()
            print('IN-FLIGHT', flush=True)
            Event().wait()
        return super().reply(*args, **kwargs)
with Server(Session(engines=True), int(sys.argv[1]), save_root=sys.argv[2]) as server:
    server.RequestHandlerClass = KillHandler
    print(server.server_port, flush=True)
    server.serve()
'''


def transient(root):
    if not shutil.which('node'):
        print('Row 89 page check SKIPPED: node unavailable')
        return
    with running(root) as (browser, _):
        exchange = browser.page_request; failing = []
        def flaky(path, options):
            if failing and path.split('?')[0] == failing[0]:
                failing.pop(0)
                return dict(error='transient')
            return exchange(path, options)
        browser.page_request = flaky
        browser.clicks([])
        for path in ('/frame', '/layout', '/frame'):
            failing.append(path)
            browser.clicks([], expect_errors=True)
            s = browser.page_stats
            assert s['reconnecting'] and not s['listening'] and s['reloads'] == 0, s
            browser.clicks([], tick=1000, expect_errors=True)
            s = browser.page_stats
            assert not s['reconnecting'] and s['listening'] and s['reloads'] == 0 and not s['hint'], s
            assert 'restart' not in (s.get('hintText') or '').lower(), s
        browser.clicks([dict(key='ArrowDown')], expect_errors=True)
        assert browser.page_stats['posts'], 'keys dead after resuming'
        for keysym, char in (('F10', ''), ('s', 's'), ('b', 'b'), ('F10', ''), ('l', 'l'), ('b', 'b')):
            browser.key(keysym, char)
        browser.clicks([], expect_errors=True)
        s = browser.page_stats
        assert s['reloads'] == 0 and not s['reconnecting'] and s['listening'], s
        browser.clicks([dict(key='ArrowDown')], expect_errors=True)
        assert browser.page_stats['posts'] and browser.page_stats['drawn'] > 0 and browser.page_stats['reloads'] == 0, 'page dead after API Load'


def reconnect(root):
    if not shutil.which('node'):
        print('#11 killed-server page check SKIPPED: node unavailable')
        return
    process = None
    browser = None

    def launch(port=0):
        child = subprocess.Popen([sys.executable, '-u', '-c', KILL_SERVER, str(port), str(root), BUILD_ID],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        line = child.stdout.readline()
        assert line, child.stderr.read()
        return child, int(line)

    def reap(child):
        child.kill()
        child.wait(3)
        child.stdout.close()
        child.stderr.close()

    try:
        process, port = launch()
        browser = Browser(port)
        requests = []
        exchange = browser.page_request
        kill_path = None

        def interrupt(path, options):
            nonlocal process, kill_path
            requests.append(path)
            if kill_path and path.split('?')[0] == kill_path:
                kill_path = None
                connection = browser.connection
                connection.request(options.get('method', 'GET'), path, options.get('body'),
                                   {**options.get('headers', {}), 'X-Test-Stop': '1'})
                assert process.stdout.readline().strip() == 'IN-FLIGHT'
                reap(process)
                process = None
                try:
                    connection.getresponse().read()
                    raise AssertionError('killed server returned a complete response')
                except (OSError, HTTPException) as error:
                    connection.close()
                    return dict(error=str(error))
            return exchange(path, options)

        browser.page_request = interrupt
        browser.clicks([])
        for path in ('/key', '/frame'):
            requests.clear()
            kill_path = path
            browser.clicks([dict(key='Enter')] if path == '/key' else [], expect_errors=True)
            assert process is None and browser.page_stats['reconnecting']
            assert not browser.page_stats['listening'], browser.page_stats
            before = browser.page_stats['reloads']
            process, actual_port = launch(port)
            assert actual_port == port
            browser.clicks([], tick=1000, expect_errors=True)
            assert browser.page_stats['reloads'] == before + 1
            browser.clicks([], restart=True, expect_errors=True)
            assert browser.page_stats['listening'] and browser.page_stats['drawn'] >= 0
            assert requests.count('/key') == (1 if path == '/key' else 0), 'uncertain key replayed'
    finally:
        if browser is not None: browser.close()
        if process is not None: reap(process)


def launch_browser():
    from sm.ui.web import open_browser, run
    url = 'http://127.0.0.1:12345/'
    with patch('sm.ui.web.subprocess.Popen') as spawn, patch('sm.ui.web.webbrowser.open') as default, \
            patch.dict('sm.ui.web.os.environ', {}, clear=True), patch('sm.ui.web.shutil.which') as which:
        for wanted in ('chrome', 'msedge', None):
            which.side_effect = lambda name: name + '-test' if name == wanted else None
            spawn.reset_mock(); default.reset_mock()
            open_browser(url)
            if wanted:
                assert spawn.call_args.args[0] == [wanted + '-test', '--app=' + url]
                default.assert_not_called()
            else:
                spawn.assert_not_called(); default.assert_called_once_with(url)
        which.side_effect = lambda name: name + '-test' if name in ('chrome', 'msedge') else None
        spawn.side_effect = OSError('injected launch failure')
        default.reset_mock()
        open_browser(url)
        default.assert_called_once_with(url)
        spawn.reset_mock(); default.reset_mock()
        with patch('sm.ui.web.Server') as server:
            server.return_value.__enter__.return_value.url = url
            run(Mock(), 0, browser=False)
        spawn.assert_not_called(); default.assert_not_called()
        server.return_value.__enter__.return_value.serve.assert_called_once()


def test(root):
    rest_input(Path(root) / 'rest-input')
    builds(Path(root) / 'builds')
    transient(Path(root) / 'transient')
    reconnect(Path(root) / 'reconnect')
    blocking_path(Path(root) / 'blocking')
    watchdog(Path(root) / 'watchdog')
    launch_browser()
    mouse = Path(root) / 'mouse'
    mouse.mkdir()
    view_and_saves(mouse, mouse=True)
    print('#13/#11/#31/#30/#37: build guard, killed server, two pages, watchdog, mocked launch and F10/slot clicks PASS')


if __name__ == '__main__':
    from tempfile import TemporaryDirectory
    from sm.titles.ssb.ui.screen import SAVE_ROOT
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.server-test-', dir=SAVE_ROOT) as root:
        test(root)
