from contextlib import contextmanager
import base64
import hashlib
from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from unittest.mock import patch

from sm.titles.ssb import save
from sm.engine import Session
from sm.titles.ssb.route import RESOLVED, Walk
from sm.titles.ssb.ui._fight_test import fight_answer, press
from sm.titles.ssb.ui._test import townhall
from sm.titles.ssb.ui._view_test import view_bytes
from sm.titles.ssb.ui.screen import Assets, Controller, LOCAL, PALETTE, SAVE_ROOT, render, slot_directory
from sm.ui.web import BUILD_ID, PAGE, Server; from sm.titles.ssb.ui.screen import layout


PAGE_DRIVER = r'''
const fs = require("node:fs"), vm = require("node:vm"), readline = require("node:readline");
const windowEvents = new Map(), canvasEvents = new Map(), timers = new Map();
let pending = 0, maximum = 0, posts = [], errors = [], scale = 1, wake, fetchReply, drawn = 0, focused = 0, reloads = 0, yellow = 0, clockAdvance = 0;
const storage = new Map();
const focusHint = {hidden: true};
const lookStatus = {hidden: true, textContent: ''};
const canvas = {width: 320, height: 200, style: {},
  focus: () => {focused++;},
  getBoundingClientRect: () => ({left: 37, top: 19, width: 320 * scale, height: 200 * scale}),
  addEventListener: (name, fn) => canvasEvents.set(name, fn),
  removeEventListener: name => canvasEvents.delete(name),
  getContext: () => ({createImageData: () => ({data: new Uint8ClampedArray(256000)}),
    putImageData: image => {drawn++; yellow = 0; for (let i = 192 * 320 * 4; i < 256000; i += 4) if (image.data[i] === 255 && image.data[i + 1] === 255 && image.data[i + 2] === 85) yellow++;}})};
function startPage() { vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8").replaceAll("__SM_BUILD_ID__", process.argv[2]), {
  document: {querySelector: selector => selector === "canvas" ? canvas : selector === "#look-status" ? lookStatus : focusHint},
  performance: {now: () => performance.now() + clockAdvance}, Uint8Array,
  window: {innerWidth: 960, innerHeight: 600,
    addEventListener: (name, fn) => windowEvents.set(name, fn),
    removeEventListener: name => windowEvents.delete(name)},
  setInterval: (fn, ms) => {timers.set(ms, fn); return ms;},
  clearInterval: ms => timers.delete(ms), location: {reload: () => {reloads++;}}, AbortSignal,
  sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
  console: {error: (...args) => errors.push(args.map(String).join(" "))},
  fetch: async (path, options) => {
    maximum = Math.max(maximum, ++pending);
    try {
      // Python owns the only HTTPConnection, including requests made by app.js.
      // Stdio carries bytes unchanged; Node never opens a second socket/pool.
      const response = await new Promise(resolve => {
        fetchReply = resolve;
        process.stdout.write(JSON.stringify({request: path, options}) + "\n");
      });
      if (response.error) throw new Error(response.error);
      const body = Buffer.from(response.body, "base64");
      const json = () => JSON.parse(body.toString("utf8"));
      if (options?.method === "POST") posts.push({key: JSON.parse(options.body), result: json()});
      return {ok: (response.status || 200) < 400, status: response.status || 200, json: async () => json(),
        arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength)};
    } finally {pending--; wake?.(); wake = undefined;}
  }
}); }
startPage();
async function settle() {
  // Yield through the page's promise continuations, then await real network
  // completion instead of a clock tick (Windows timers can cost 15 ms each).
  do {
    await new Promise(setImmediate);
    if (!pending) break;
    await new Promise(resolve => {wake = resolve;});
  } while (true);
}
const input = readline.createInterface({input: process.stdin});
input.on("line", async line => {
  const command = JSON.parse(line);
  if (command.response) {
    const reply = fetchReply; fetchReply = undefined; reply(command.response); return;
  }
  const watchdog = setTimeout(() => process.exit(2), 5000);
  try {
    clockAdvance += command.advance || 0;
    await settle();
    if (command.restart) {timers.clear(); windowEvents.clear(); canvasEvents.clear(); startPage(); await settle();}
    timers.get(command.tick || 100)?.(); await settle();
    posts = []; drawn = 0; scale = command.scale || 1;
    for (const event of command.events) {
      const common = {preventDefault() {}, ...event};
      if (event.type && windowEvents.has(event.type)) windowEvents.get(event.type)?.();
      else if (event.key) windowEvents.get("keydown")?.(common);
      else canvasEvents.get(event.type || "click")?.({button: 0, detail: 1,
        clientX: 37 + event.x * scale, clientY: 19 + event.y * scale, ...common});
    }
    await settle();
    process.stdout.write(JSON.stringify({posts, maximum, drawn, yellow, cursor: canvas.style.cursor, focused, hint: !focusHint.hidden, hintText: focusHint.textContent,
      errors, reloads, listening: windowEvents.has("keydown"), reconnecting: timers.has(1000)}) + "\n");
  } catch (error) {process.stdout.write(JSON.stringify({error: String(error)}) + "\n");}
  finally {clearTimeout(watchdog);}
});
input.on("close", () => process.exit(0));
'''


def key_value(key):
    return dict(keysym=key, char=key if len(key) == 1 else '')


class Browser:
    def __init__(self, port, build=BUILD_ID):
        self.port = port
        self.build = build
        self.page = None
        self.connection = HTTPConnection('127.0.0.1', port, timeout=3)
        self.connections = 0

    def request(self, path, value=None, *, body=None, headers=None, status=200):
        headers = dict(headers or {})
        if value is not None:
            body = json.dumps(value).encode()
            headers['Content-Type'] = 'application/json'
        connection = self.connection
        if connection.sock is None:
            connection.connect()
            self.connections += 1
        connection.request('POST' if body is not None else 'GET', path, body, headers)
        response = connection.getresponse()
        data = response.read()
        assert response.status == status, (path, response.status, data[:120])
        assert response.version == 11
        assert (response.getheader('Connection') or '').lower() == 'close', 'response kept the connection (blocks other pages)'
        if status == 200:
            assert int(response.getheader('Content-Length')) == len(data)
            assert response.getheader('Cache-Control') == 'no-store'
        else:
            assert response.getheader('Connection') == 'close'
        return data, dict(response.getheaders())

    def decision(self):
        return json.loads(self.request('/decision')[0])

    def key(self, keysym, char=''):
        return json.loads(self.request('/key', {'keysym': keysym, 'char': char})[0])

    def layout(self):
        return json.loads(self.request('/layout')[0])

    def clicks(self, events, scale=1, *, tick=100, restart=False, expect_errors=False, advance=0):
        node = shutil.which('node')
        if node:
            if self.page is None:
                self.page = subprocess.Popen(
                    [node, '-e', PAGE_DRIVER, str(PAGE / 'app.js'), self.build],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.page.stdin.write(json.dumps(dict(events=events, scale=scale, tick=tick, restart=restart, advance=advance)) + '\n')
            self.page.stdin.flush()
            while True:
                line = self.page.stdout.readline()
                assert line, 'page driver stopped: ' + self.page.stderr.read()
                result = json.loads(line)
                if 'request' not in result:
                    break
                response = self.page_request(result['request'], result.get('options') or {})
                self.page.stdin.write(json.dumps(dict(response=response)) + '\n')
                self.page.stdin.flush()
            assert 'error' not in result, result
            assert expect_errors or not result['errors'], result
            assert result['maximum'] == 1, 'page overlapped HTTP requests'
            self.page_stats = result
            return result['posts']
        assert len(events) == 1
        event, current = events[0], self.layout()
        if event.get('button', 0) or event.get('detail', 1) > 1:
            return []
        for region in current['regions']:
            x, y, width, height = region['rect']
            if not (x <= event['x'] < x + width and y <= event['y'] < y + height):
                continue
            if 'keys' in region:
                keys = region['keys']
            elif 'key' in region:
                keys = [region['key']]
            else:
                roster = 'roster' in region
                delta = region['roster' if roster else 'select'] - current['roster_selected' if roster else 'selected']
                keys = [key_value('Up' if delta < 0 else 'Down')] * abs(delta)
                if not roster:
                    keys.append(key_value('Return'))
            if not keys: return []
            value = dict(keys=keys, revision=current['revision'])
            return [dict(key=value, result=json.loads(self.request('/key', value)[0]))]
        return []

    def page_request(self, path, options):
        body = options.get('body')
        status = 409 if path != '/version' and options.get('headers', {}).get('X-SM-Build', BUILD_ID) != BUILD_ID else 200
        try:
            data, _ = self.request(path, body=body.encode() if body is not None else None,
                                   headers=options.get('headers'), status=status)
            return dict(body=base64.b64encode(data).decode('ascii'), status=status)
        except (OSError, EOFError, HTTPException) as error:
            self.connection.close()
            return dict(error=str(error))

    def close(self):
        self.connection.close()
        if self.page is not None:
            self.page.stdin.close()
            try:
                self.page.wait(3)
            except subprocess.TimeoutExpired:
                self.page.kill()
                self.page.wait()
            self.page.stdout.close()
            self.page.stderr.close()


class Mirror:
    def __init__(self, controller, browser):
        self.controller, self.browser = controller, browser

    @property
    def session(self):
        return self.controller.session

    def key(self, keysym, char=''):
        response = self.browser.key(keysym, char)
        advanced = self.controller.key(keysym, char)
        assert response == normalized({'decision': self.session.decision, 'quit': self.controller.quit_requested})
        return advanced

    def click(self, x, y, expected, *, scale=1, events=None, **event):
        posts = self.browser.clicks(events or [dict(x=x, y=y, **event)], scale)
        assert [key for post in posts for key in post['key'].get('keys', [post['key']])] == [key_value(key) for key in expected], posts
        for post in posts:
            for key in post['key'].get('keys', [post['key']]): self.controller.key(**key)
            assert post['result'] == normalized(dict(decision=self.session.decision, quit=self.controller.quit_requested))
        if not self.controller.quit_requested:
            assert self.browser.decision() == normalized(self.session.decision)


def normalized(value):
    return json.loads(json.dumps(value))


@contextmanager
def running(save_root, session=None):
    with Server(session or Session(engines=True), 0, save_root=save_root, presentation=False) as server:
        browser = Browser(server.server_port)
        worker = Thread(target=server.serve, daemon=True)
        worker.start()
        try:
            yield browser, worker
        finally:
            browser.close()
            server.stopping = True
            worker.join(3)
            assert not worker.is_alive(), 'HTTP server did not stop'


def frame_equal(mirror, elapsed=0):
    before = mirror.browser.decision()
    frame = render(mirror.controller, Assets(), elapsed)
    expected = b''.join(frame.rows)
    data, headers = mirror.browser.request('/frame?t=%s' % (elapsed * 1000))
    assert len(data) == 64000 and data == expected
    assert headers['Content-Type'] == 'application/octet-stream'
    assert headers['X-Frame-Hash'] == hashlib.sha256(expected).hexdigest()
    assert mirror.browser.decision() == before == normalized(mirror.session.decision)
    remote_layout = mirror.browser.layout()
    remote_layout.pop('journal', None)
    assert remote_layout.pop('look_status') == ''
    assert remote_layout.pop('key_hint') == []
    assert remote_layout == normalized(layout(mirror.controller))
    assert mirror.browser.decision() == before, 'layout advanced the game'
    return frame


def file_click(mirror, hotkey):
    regions = mirror.browser.layout()['regions']
    if not any(r.get('key') == key_value(hotkey) for r in regions):
        file_click(mirror, 'Next')
        return file_click(mirror, hotkey)
    region = next(r for r in regions if r.get('key') == key_value(hotkey))
    x, y, w, h = region['rect']
    mirror.click(x + w / 2, y + h / 2, [hotkey])


def oversized_body(browser):
    browser.connection.close()
    connection = HTTPConnection('127.0.0.1', browser.port, timeout=3)
    try:
        connection.putrequest('POST', '/key')
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', '4097')
        connection.endheaders(b' ' * 64)
        assert not select.select([connection.sock], [], [], .02)[0], 'rejected before draining the body'
        connection.send(b' ' * (4097 - 64))
        response = connection.getresponse()
        data = response.read()
        assert response.status == 400, (response.status, data[:120])
        assert len(data) == int(response.getheader('Content-Length'))
        assert response.getheader('Connection') == 'close'
        assert connection.sock is None, 'rejected request kept its connection open'
    finally:
        connection.close()


def protocol(browser, root):
    assert json.loads(browser.request('/palette')[0]) == normalized(PALETTE)
    page = Path(root) / 'page'
    page.mkdir()
    with patch('sm.ui.web.PAGE', page):
        for route, name, kind, data in (
                ('/', 'index.html', 'text/html', b'<canvas></canvas>'),
                ('/app.js', 'app.js', 'text/javascript', b'"use strict";')):
            (page / name).write_bytes(data)
            body, headers = browser.request(route)
            assert body == data and headers['Content-Type'].startswith(kind)
        for path in ('/screen.py', '/index.html', '/../screen.py', '/local/saves/A/SAVGAMA.DAT'):
            browser.request(path, status=404)
    before = browser.decision()
    for path, value in (('/layout', None), ('/key', key_value('Return'))):
        body, _ = browser.request(path, value, headers={'X-SM-Build': 'old-build'}, status=409)
        assert json.loads(body)['build'] == BUILD_ID
    assert browser.decision() == before, 'stale build changed the game'
    for value in ([], {'keysym': 3}, {'keysym': ''}, {'keysym': 'a', 'char': 'ab'}, {'keysym': 'a', 'char': None},
                  {'keys': []}, {'keys': [key_value('Return'), {'keysym': 3}]}, {'keys': [key_value('Down')] * 65}):
        browser.request('/key', value, status=400)
    browser.request('/key', {'keys': [key_value('Return')], 'revision': ['stale']})
    browser.request('/key', body=b'{', headers={'Content-Type': 'application/json'}, status=400)
    browser.request('/key', body=b'{}', status=415)
    oversized_body(browser)
    browser.request('/unknown', {}, status=404)
    browser.request('/key', {'keysym': 'Return'}, headers={'Origin': 'https://example.invalid'}, status=403)
    browser.request('/decision', headers={'Host': 'example.invalid'}, status=403)
    browser.request('/layout', headers={'Origin': 'https://example.invalid'}, status=403)
    browser.request('/layout', {}, status=404)
    for elapsed in ('nan', 'inf', '-1', 'bad'):
        browser.request('/frame?t=' + elapsed, status=400)
    assert browser.decision() == before, 'invalid request changed the game'


def click_paths(root):
    controller = Controller(Session(engines=True), save_root=Path(root) / 'keys')
    remote = Session(engines=True)
    try:
        with running(Path(root) / 'clicks', remote) as (browser, _):
            mirror = Mirror(controller, browser)

            def equal():
                assert remote.game.trace == mirror.session.game.trace, 'click/key decision traces differ'
                assert remote.game.s.hash(remote.game.vm) == mirror.session.game.s.hash(mirror.session.game.vm)
                frame_equal(mirror)

            def word(hotkey):
                region = next(r for r in browser.layout()['regions'] if r.get('key') == key_value(hotkey))
                x, y, w, h = region['rect']
                mirror.click(x + w / 2, y + h / 2, [hotkey], scale=3)

            if shutil.which('node'):
                mirror.click(160, 148, ['Return'], events=[dict(x=160, y=148)] * 2)
            while mirror.session.decision['kind'] != 'SHOP_MENU':
                mirror.click(160, 148, ['Return'])
            assert mirror.session.decision['info']['purpose'] == 'treasure'
            word('t')
            assert mirror.session.decision['info']['purpose'] == 'take'
            equal()
            mirror.click(200, 52, ['Down', 'Down'], scale=2)
            assert remote.game.s.sel == 2
            if shutil.which('node'):
                assert len(browser.page_stats['posts']) == browser.page_stats['drawn'] == 1, 'roster click drew intermediate frames'
            mirror.click(200, 52, [])
            mirror.click(200, 36, ['Up', 'Up'], scale=3)
            mirror.click(200, 44, ['Down'], scale=2.5)
            assert remote.game.s.sel == 1
            equal()

            word('i')
            assert mirror.session.decision['kind'] == 'LIST' and len(mirror.session.decision['options']) > 12
            assert not any('roster' in r for r in browser.layout()['regions']), 'covered roster remained clickable'
            assert not any(r.get('key') in (key_value('n'),key_value('p')) for r in browser.layout()['regions'])
            mirror.click(160, 28, ['Down', 'Down', 't'], scale=3)
            if shutil.which('node'):
                assert len(browser.page_stats['posts']) == browser.page_stats['drawn'] == 1, 'list click drew intermediate frames'
            equal()
            if mirror.session.decision['kind'] == 'LIST':
                mirror.key('Escape')
            if mirror.session.decision['kind'] == 'SHOP_MENU':
                word('e')
            townhall(mirror)
            equal()

            if shutil.which('node'):
                before = remote.game.s.hash(remote.game.vm)
                cursors = []
                for x in (30, 68, 105):
                    assert browser.clicks([dict(type='mousemove', x=x, y=60)], 2.5) == []
                    cursors.append(browser.page_stats['cursor'])
                    assert browser.page_stats['drawn'] == 0
                assert len(set(cursors)) == 3 and all('svg' in cursor for cursor in cursors)
                assert browser.clicks([dict(type='mouseleave', x=0, y=0)]) == []
                assert browser.page_stats['cursor'] == 'default'
                down, up = dict(type='mousedown', x=30, y=60), dict(x=30, y=60)
                browser.clicks([dict(type='blur')]); assert browser.page_stats['hint']
                browser.clicks([down, up]); assert not browser.page_stats['posts'] and not browser.page_stats['hint'], browser.page_stats
                browser.clicks([dict(type='focus'), dict(type='blur')]); browser.clicks([dict(type='focus'), down, up])
                assert not browser.page_stats['posts'], browser.page_stats
                browser.clicks([dict(type='blur')]); assert browser.page_stats['hint']
                focused = browser.page_stats['focused']
                browser.clicks([dict(type='focus')])
                assert not browser.page_stats['hint'] and browser.page_stats['focused'] > focused
                remote.game.s.r0[0xFB] = 1
                browser.clicks([dict(key='a')]); assert browser.page_stats['yellow'] > 0, browser.page_stats
                browser.clicks([],advance=500); assert browser.page_stats['yellow'] == 0, browser.page_stats
                remote.game.s.r0[0xFB] = 0
                assert remote.game.s.hash(remote.game.vm) == before

            start = (remote.game.s.x, remote.game.s.y)
            if shutil.which('node'): browser.clicks([],advance=450)
            mirror.click(30, 60, ['m', 'Left'], scale=3, **(dict(events=[dict(type='mousedown', x=30, y=60), dict(x=30, y=60)]) if shutil.which('node') else {}))
            mirror.click(105, 60, ['Right'], scale=2)
            mirror.click(68, 60, ['Up'], scale=1)
            assert (remote.game.s.x, remote.game.s.y) != start
            if shutil.which('node'):
                mirror.click(0, 0, ['Left'], events=[dict(key='ArrowLeft'), dict(x=105, y=60)])
            for x, y, options in ((0, 0, {}), (320, 196, {}), (112, 60, {}),
                                  (30, 60, dict(button=2)), (30, 60, dict(detail=2))):
                mirror.click(x, y, [], **options)
            mirror.key('F2')
            mirror.click(68, 60, [])
            mirror.key('F2')
            equal()

            press(mirror, mirror.session.decision['options'].index('camp'))
            press(mirror, mirror.session.decision['options'].index('rest'))
            press(mirror, mirror.session.decision['options'].index('hours'))
            if mirror.session.decision['kind'] == 'NUMBER':
                mirror.key('0', '0'); mirror.click(160, 196, ['Return'])
            else:
                assert mirror.session.decision['info']['field'] == 'hours'
                press(mirror, mirror.session.decision['options'].index('add'))
                press(mirror, mirror.session.decision['options'].index('subtract'))
            press(mirror, mirror.session.decision['options'].index('exit'))
            assert mirror.session.decision['kind'] == 'CAMP_MENU'
            caster = next(i for i, c in enumerate(mirror.session.game.s.party) if c.b[0x111])
            delta = caster - mirror.session.game.s.sel
            mirror.click(160, 36 + caster * 8, ['Down' if delta > 0 else 'Up'] * abs(delta), scale=3)
            assert remote.game.s.sel == caster
            press(mirror, mirror.session.decision['options'].index('magic'))
            press(mirror, mirror.session.decision['options'].index('memorize'))
            assert mirror.session.decision['kind'] == 'SPELL'
            word('n')
            row = next(r for r in browser.layout()['regions'] if 'select' in r)
            assert 40 <= row['rect'][1] <= 120 and row['keys'][-1] == key_value('m')
            mirror.click(160, row['rect'][1]+4, [k['keysym'] for k in row['keys']], scale=2)
            equal()
            mirror.key('F10')
            assert {r['key']['keysym'] for r in browser.layout()['regions']} == {'s', 'l', 'q', 'r', 'Escape'}
            mirror.click(160, 36, [])
            mirror.key('Escape')
            equal()
            if shutil.which('node'):
                row = next(r for r in browser.layout()['regions'] if 'select' in r)
                y = row['rect'][1]+4
                mirror.click(160, y, [k['keysym'] for k in row['keys']], events=[dict(x=160, y=y), dict(type='pagehide')])
                assert browser.page_stats['drawn'] == 0
                equal()
            assert browser.connections >= 1
    finally:
        controller.session.close()
        remote.close()


def view_and_saves(root, *, mouse=False):
    controller = Controller(Session(engines=True), save_root=Path(root) / 'harness')
    try:
        with running(Path(root) / 'browser') as (browser, worker):
            protocol(browser, root)
            connections = browser.connections
            mirror = Mirror(controller, browser)
            choose = (lambda key: file_click(mirror, key)) if mouse else (lambda key: mirror.key(key, key))
            townhall(mirror)
            original = frame_equal(mirror)
            views = set()
            mirror.key('m', 'm')
            for _ in range(4):
                assert mirror.key('Left')
                views.add(view_bytes(frame_equal(mirror)))
            assert len(views) == 4 and view_bytes(original) in views
            mirror.key('F10'); frame_equal(mirror)
            choose('r')
            mirror.key('F10')
            choose('s'); frame_equal(mirror)
            choose('t'); frame_equal(mirror)
            target = slot_directory('T', Path(root) / 'browser')
            expected = slot_directory('T', Path(root) / 'harness')
            assert target.is_relative_to(SAVE_ROOT.resolve())
            assert {p.name: p.read_bytes() for p in target.iterdir()} == {
                p.name: p.read_bytes() for p in expected.iterdir()}
            saved = save.load(target, 'T')
            mirror.key('Escape'); mirror.key('Up')
            mirror.key('F10'); choose('l'); frame_equal(mirror)
            choose('t'); frame_equal(mirror)
            assert [controller.session.game.s.x, controller.session.game.s.y] == saved['pos'][:2]
            mirror.key('m', 'm')
            assert mirror.key('Left')
            mirror.key('F10'); choose('q')
            worker.join(3)
            assert not worker.is_alive(), 'F10 Quit did not stop HTTP serving'
            assert browser.connections >= connections
        assert (Path(root) / 'browser' / 'autosave.zip').is_file(), 'F10 Quit lost its autosave'
    finally:
        controller.session.close()


def fight(root):
    controller = Controller(Session(engines=True))
    walker = Walk(json.loads((LOCAL.parent / 'herdr/route/derived.json').read_text()), {})
    fighting, seen, clicked = False, set(), set()
    remote = Session(engines=True)
    try:
        with running(root, remote) as (browser, worker):
            mirror = Mirror(controller, browser)
            assert browser.decision() == normalized(mirror.session.decision)
            for _ in range(1000):
                game, decision = mirror.session.game, mirror.session.decision
                assert decision is not None, mirror.session.result
                active = bool(game.s.g.get('combat.active'))
                if fighting and not active:
                    break
                fighting |= active
                kind = 'combat' if decision['kind'] == 'COMBAT_ACTION' else 'target' if active else game.vm.display.get('kind')
                if kind not in seen:
                    frame_equal(mirror)
                    if kind == 'PIC':
                        frame_equal(mirror, .25)
                    seen.add(kind)
                if active:
                    answer = fight_answer(game, decision)
                elif decision['kind'] in ('SHOP_MENU', 'CAMP_MENU'):
                    answer = decision['options'].index('no' if decision['info'].get('purpose') == 'treasure leave' else 'exit')
                else:
                    assert decision['kind'] not in RESOLVED
                    answer = walker(decision['kind'], decision['options'], game, **decision['info'])
                target = ('cell' if isinstance(decision['options'][answer], (tuple, list)) else 'monster') if (
                    active and decision['kind'] == 'TARGET') else None
                regions = browser.layout()['regions'] if target and target not in clicked else []
                region = next((r for r in regions if r.get('select') == answer and r['rect'][0] < 176), None)
                if region:
                    x, y, width, height = region['rect']
                    delta = answer - controller.selected
                    expected = ([str(answer + 1)] if decision['info'].get('action') == 'move' else
                                ['Up' if delta < 0 else 'Down'] * abs(delta) + ['Return'])
                    mirror.click(x + width - 1, y + height - 1, expected, scale=3)
                    assert remote.game.trace == mirror.session.game.trace
                    clicked.add(target)
                else:
                    press(mirror, answer)
            else:
                raise AssertionError('HTTP fight exceeded 1000 decisions')
            state = mirror.session.game.s
            assert fighting and {'combat', 'target'} <= seen and state.g['combat.attacks'] > 0
            assert clicked == {'cell', 'monster'}, clicked
            assert not state.monsters and not state.party_dead and state.g['87CD'] == 0
            assert mirror.session.game.combat is None
            assert browser.decision()['hash'] == state.hash(mirror.session.game.vm)
            assert remote.game.trace == mirror.session.game.trace, 'combat click trace differs'
            frame_equal(mirror)
            count = len(mirror.session.game.trace)
            mirror.key('F10'); mirror.key('q', 'q')
            worker.join(3)
            assert not worker.is_alive()
            assert browser.connections >= 1
            return count
    finally:
        controller.session.close()
        remote.close()


def test():
    started = time.perf_counter()
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    original = Path(save.SECRET) / 'SAVGAMA.DAT'
    before = original.read_bytes()
    with TemporaryDirectory(prefix='.web-test-', dir=SAVE_ROOT) as root:
        view_and_saves(root)
        click_paths(root)
        count = fight(root)
    assert original.read_bytes() == before and 'tkinter' not in sys.modules
    print('HTTP: town/roster/item/spell/member/map/monster clicks, %d-decision fight hashes, Save/Load/Quit: PASS (%.2fs; %s; one connection/replay)' %
          (count, time.perf_counter() - started, 'app.js' if shutil.which('node') else 'stdlib click driver'))
