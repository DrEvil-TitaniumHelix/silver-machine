"""B1 browser transport: herdr/assignments/B1.md, shared screen.Controller/render.

Stdlib HTTPServer serves one player on loopback. Original art is decoded only
in memory by screen.Assets; the page receives palette indices, never asset files.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import struct
from threading import RLock
from urllib.parse import parse_qs, urlsplit
import webbrowser
import uuid
from datetime import datetime
from sm.ui.plus import Settings, DEFAULTS, validate


PAGE = Path(__file__).with_suffix('')
# GU-77 #13: freeze page bytes with the running code, even when another build
# replaces files on disk before this process is restarted.
PAGE_BYTES = {name: (PAGE / name).read_bytes() for name in ('index.html', 'app.js', 'setup.html', 'setup.js', 'plus.html', 'plus.js', 'plus.css', 'journal.js', 'journal.css')}
BUILD_ID = hashlib.sha256(b''.join(
    p.read_bytes() for p in sorted(PAGE.parent.parent.rglob('*.py'))
    if not p.name.endswith('_test.py')
) + b''.join(PAGE_BYTES.values()) + b''.join(p.read_bytes() for p in sorted((PAGE.parent.parent / 'titles').glob('*/supported_versions.json')))).hexdigest()[:16]


class Server(ThreadingHTTPServer):
    """ov22:0DF3: serialize game access; accept keyboard input while a rest frame runs."""
    daemon_threads = False  # Join request handlers before saving and closing their Session.
    def __init__(self, session=None, port=8320, *, save_root=None, presentation=True, log_path=None, session_factory=None, profile=None):
        """ov26:173F playback; ov28:03C9 / GU-80 #45 logging is opt-in for tests."""
        from importlib import import_module
        from sm.titles import select
        self.profile = profile or (session.profile if session is not None else select())
        if not getattr(self.profile, 'presentation', None):
            raise ValueError('This title has no browser presentation yet')
        self.screen = import_module(self.profile.presentation)
        self.intake = self.profile.intake
        self.plus = Settings(self.intake.config_path().with_name('plus.json')) if hasattr(self.screen.Controller, 'apply_plus') else None
        self.controller, self.assets = None, None
        self.session_factory = session_factory
        self.save_root, self.presentation = save_root, presentation
        self.intake_error = ''
        self.state_lock = RLock()
        self.log_lock = RLock()
        self.log_path = Path(log_path) if log_path is not None else None
        self.logged_decision = None
        self.stopping = False
        self.overlays = {}
        self.instance = uuid.uuid4().hex
        super().__init__(('127.0.0.1', port), Handler)
        self.timeout = 0.1
        try:
            if session is not None: self.attach(session)
            elif session_factory is not None: self.start_game()
        except Exception:
            self.server_close()
            raise

    def attach(self, session):
        """Only called after intake; no game objects exist on the empty setup page."""
        try:
            if session.profile is not self.profile: raise ValueError('Session and presentation profiles differ')
            self.controller = self.screen.Controller(session, save_root=self.save_root, presentation=self.presentation)
            if self.plus: self.controller.apply_plus(self.plus)
            if self.profile.name == 'ssb':
                from sm.ui.journal import Journal
                self.controller.journal = Journal(self.controller, self.intake)
            self.assets = self.screen.Assets()
            self.controller.decision_observer = self.log_decision
            self.controller.autosave_enabled = True
            self.controller.remember()
            self.log_decision()
        except Exception:
            session.close()
            self.controller = None
            raise

    def start_game(self):
        try:
            if not self.intake.configured():
                self.intake_error = 'Choose your game folder to begin.'
                return
            self.intake.require_folder()
            self.attach(self.session_factory())
            self.intake_error = ''
        except (OSError, ValueError, KeyError) as error:
            self.intake_error = 'Cannot start the game: %s' % error

    def preferences(self):
        options = self.plus.options if self.plus else dict(DEFAULTS)
        if not self.plus and self.controller: options['effect_scale'] = self.controller.effect_scale
        extra = {}
        if self.plus:
            copy = self.dqk_copy()
            extra = dict(dqk_frame=copy['ok'], dqk_copy=copy,
                         look_note='VGA enables full-colour PNG mods. With a verified Dark Queen copy in the row below, '
                         'you can use its frame and font. Without one, the Silver Blades frame and font stay the same; '
                         'only mods look different. SSB scenery and pictures stay SSB\'s.')
            if warning := getattr(getattr(self.controller, '_vga_assets', None), 'warning', ''):
                extra['look_note'] += ' ' + warning
        return dict(options=options, persistent=self.plus is not None, **extra,
                    supported=list(DEFAULTS) if self.plus else ['effect_scale'] if self.controller else [])

    def dqk_copy(self, folder=None):
        from sm.titles.ssb.ui.vga import configured_dqk, skin
        folder = (configured_dqk() or '') if folder is None else folder
        result = dict(ok=False, folder=folder, edition=None,
                      source='DQK_ROOT' if os.environ.get('DQK_ROOT', '').strip() else 'settings',
                      message='No Dark Queen copy set. Browse to your copy, then verify and save.')
        if not folder: return result
        try:
            native, _, _ = skin(folder)
            result.update(ok=True, edition=native.edition,
                          message=(native.edition or 'Unknown edition') + ' — Dark Queen frame and font verified.')
        except OSError:
            result['message'] = 'Cannot read the Dark Queen frame and font. Choose the game folder containing DISK1 and DISK3.'
        except ValueError:
            result['message'] = 'The Dark Queen frame or font could not be decoded. Choose another copy.'
        if result['source'] == 'DQK_ROOT':
            result['message'] += ' DQK_ROOT sets this folder. Unset it and restart to use the Plus controls.'
        return result

    def choose_dqk_copy(self, folder):
        from sm.ui import vga_skin
        from sm.titles.ssb.ui.vga import skin
        if os.environ.get('DQK_ROOT', '').strip():
            return dict(ok=False, message='DQK_ROOT overrides this folder. Unset it and restart to use the Plus controls.'), 409
        folder = str(Path(folder.strip()).expanduser().resolve()) if folder.strip() else ''
        # Reverify even a previously cached folder; then invalidate the live renderer.
        skin.cache_clear()
        vga_skin.Skin.picture.cache_clear()
        vga_skin.Skin.rows.cache_clear()
        result = self.dqk_copy(folder)
        if folder and not result['ok']: return result, 422
        vga_skin.remember(folder)
        if self.controller:
            self.controller._vga_key = None
            self.controller._vga_assets = None
        return dict(ok=True, message=result['message'] if folder else 'Dark Queen copy cleared.',
                    **self.preferences()), 200

    def set_preferences(self, values):
        validate(values)
        if self.plus is None: raise ValueError('Plus settings are unavailable for this title')
        if 'mods_folder' in values:
            from sm.titles.ssb.ui.vga import Mods
            mods = Mods(values['mods_folder'])
            # Fail at selection time, with an actionable error on the Plus page.
            mods.validate()
        self.plus.update(values)
        if self.controller: self.controller.apply_plus(self.plus)

    def intake_state(self):
        try:
            folder = self.intake.configured() or ''
            error = self.intake_error
        except self.intake.DataError as failure:
            folder, error = '', str(failure)
        return dict(folder=folder, error=error, ready=self.controller is not None,
                    source=self.intake.ENV if os.environ.get(self.intake.ENV, '').strip() else 'settings',
                    version=self.intake.VERSION, content=self.intake._active and self.intake._active['version'],
                    expected=[v['label'] for v in self.intake.catalog()['versions']],
                    missing=self.intake.catalog()['missing'], build=BUILD_ID)

    def choose_folder(self, folder):
        """Persist verified settings. Live games retain their pinned data until restart."""
        if os.environ.get(self.intake.ENV, '').strip():
            return dict(ok=False, message=self.intake.ENV + ' overrides folder settings. Change or unset it, then restart the server.'), 409
        result = self.intake.inspect_folder(folder)
        if not result['ok']: return result, 422
        try:
            self.intake.remember(result['folder'])
        except OSError as error:
            return dict(ok=False, message='Cannot save folder settings: %s' % error), 500
        if self.controller is not None or self.intake._active is not None:
            result.update(restart=True, message='Folder saved. Restart the server to use it. Your current game keeps its current copy.')
        else:
            self.start_game()
            if self.controller is None:
                result.update(ok=False, message=self.intake_error)
                return result, 422
        return result, 200

    def log(self, event, **fields):
        """ov28:03C9 / GU-80 #45: append timestamped JSON lines, flush each line."""
        if self.log_path is None: return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_lock, self.log_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(time=datetime.now().astimezone().isoformat(timespec='milliseconds'),
                                         event=event, instance=self.instance, **fields), separators=(',', ':')) + '\n')
            stream.flush()

    def log_decision(self):
        """ov28:03C9 / GU-80 #45: initial, replaced-session and terminal decisions."""
        if journal := getattr(self.controller, 'journal', None): journal.observe()
        session = self.controller.session
        decision = session.decision
        marker = (id(session), decision and decision.get('kind'), decision and decision.get('i'), decision and decision.get('hash'))
        if marker != self.logged_decision:
            self.logged_decision = marker
            self.log('decision', kind=marker[1], i=marker[2], hash=marker[3])

    def log_input(self, body):
        """ov28:03C9 / GU-80 #45: even rejected/stale POSTs have a timestamped key record."""
        if self.log_path is None: return
        try: value = json.loads(body)
        except (ValueError, UnicodeError): value = {}
        if not isinstance(value, dict): value = {}
        batch = value.get('keys', [value])
        if not isinstance(batch, list) or not batch: batch = [{}]
        stale = False
        if 'revision' in value:
            with self.state_lock: stale = value['revision'] != self.screen.layout(self.controller)['revision']
        for key in batch:
            key = key if isinstance(key, dict) else {}
            self.log('key', keysym=key.get('keysym'), char=key.get('char', ''), stale=stale)

    @property
    def url(self):
        """B1 default-browser URL, including the actual port after a port-0 bind."""
        return 'http://127.0.0.1:%d/' % self.server_port

    def get_request(self):
        """http.server socket contract: bound an idle browser connection's wait."""
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def serve(self):
        """B1 Quit: finish its JSON response, then leave the request loop."""
        while not self.stopping and not (self.controller and self.controller.quit_requested):
            self.handle_request()

    def server_close(self):
        """Session.close contract: also release a replacement session after Load."""
        self.stopping = True
        try:
            super().server_close()
        finally:
            try:
                if self.controller: self.controller.autosave()
            finally:
                if self.controller: self.controller.session.close()


class Handler(BaseHTTPRequestHandler):
    """Fixed routes; only the same-origin intake endpoint accepts a content folder."""
    protocol_version = 'HTTP/1.1'
    disable_nagle_algorithm = True  # Send each small response without delayed-ACK stalls.

    def log_message(self, *_):
        """B1 polling runs at 10 Hz; avoid flooding the local console."""

    def local_request(self):
        """B1 loopback scope: accept only the page's host and same-origin requests."""
        origin = self.server.url.rstrip('/')
        if (self.headers.get('Host') != origin.removeprefix('http://') or
                self.headers.get('Origin', origin) != origin):
            self.send_error(403, 'Use the local game URL')
            return False
        return True

    def reply(self, body, kind, *, frame_hash=None, status=200, overlay=None):
        """GU-77 #13 / B1: identify the running build before any game input."""
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')                      # live blocker 11/01: one connection per request, so a page's keep-alive
        self.send_header('X-SM-Build', BUILD_ID)
        self.close_connection = True                                 # poll cannot hold the single-threaded server while other pages wait
        if frame_hash is not None:
            self.send_header('X-Frame-Hash', frame_hash)
        if overlay is not None: self.send_header('X-SM-Overlay', overlay)
        self.end_headers()
        self.wfile.write(body)

    def json(self, value, *, status=200):
        """B1 JSON API preserves Session.decision's existing field/value shape."""
        self.reply(json.dumps(value, separators=(',', ':')).encode('utf-8'), 'application/json', status=status)

    def matching_build(self):
        """GU-77 #13: stale pages cannot advance a different server build."""
        if self.headers.get('X-SM-Build', BUILD_ID) == BUILD_ID:
            return True
        self.json(dict(error='build-mismatch', build=BUILD_ID, instance=self.server.instance), status=409)
        return False

    def do_GET(self):
        """ov22:0DF3 / ov28:03C9: snapshots and game advancement share one state lock."""
        with self.server.state_lock: self.get()

    def get(self):
        """ov26:173F / ov22:0DF3: GET frame/decision snapshots under exclusive game access."""
        if not self.local_request():
            return
        request = urlsplit(self.path)
        if request.path == '/version':
            self.json(dict(build=BUILD_ID, instance=self.server.instance, version=self.server.intake.VERSION,
                           content=self.server.intake._active and self.server.intake._active['version'],
                           **({'frame_format': self.server.screen.FRAME_FORMAT}
                              if hasattr(self.server.screen, 'FRAME_FORMAT') else {})))
            return
        if not self.matching_build():
            return
        if request.path == '/intake':
            self.json(self.server.intake_state())
            return
        if request.path == '/preferences':
            self.json(self.server.preferences())
            return
        from sm.ui.journal import get as journal_get
        if journal_get(self, request.path): return
        if request.path == '/journal.css':
            self.reply(PAGE_BYTES['journal.css'], 'text/css; charset=utf-8')
            return
        if request.path == '/plus/data':
            if self.server.profile.name != 'ssb' or self.server.controller is None:
                self.json(dict(error='Start SSB with your own game folder to use these tabs.'), status=409)
                return
            from sm.titles.ssb.ui.plus import tab_data
            query = parse_qs(request.query)
            try: self.json(tab_data(self.server.controller, query.get('tab', [''])[0], query))
            except (ValueError, KeyError, IndexError): self.json(dict(error='This Plus data is unavailable.'), status=400)
            except OSError: self.json(dict(error='Cannot read the selected game files.'), status=422)
            return
        if request.path == '/plus.css':
            self.reply(PAGE_BYTES['plus.css'], 'text/css; charset=utf-8')
            return
        if request.path == '/speed' and self.server.plus:
            self.json(dict(scale=self.server.plus.options['effect_scale']))
            return
        if request.path in ('/', '/setup', '/plus', '/app.js', '/setup.js', '/plus.js', '/journal.js'):
            if request.path in ('/', '/setup', '/plus'):
                name, kind = ('plus.html' if request.path == '/plus' else 'setup.html' if request.path == '/setup' or self.server.controller is None else 'index.html'), 'text/html'
            else:
                name, kind = request.path[1:], 'text/javascript'
            try:
                body = PAGE_BYTES[name] if PAGE == Path(__file__).with_suffix('') else (PAGE / name).read_bytes()
                body = body.replace(b'__SM_BUILD_ID__', BUILD_ID.encode('ascii'))
                body = body.replace(b'__SM_VERSION__', self.server.intake.VERSION.encode('ascii'))
                body = body.replace(b'__SM_CONTENT__', (self.server.intake._active['version'] if self.server.intake._active else 'No copy selected').encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, 'Page asset not installed')
                return
            self.reply(body, kind + '; charset=utf-8')
        elif self.server.controller is None:
            self.json(dict(error='Choose a supported game folder first.', setup='/setup'), status=409)
        elif request.path == '/palette':
            self.json(self.server.screen.PALETTE)
        elif request.path == '/decision':
            self.json(self.server.controller.session.decision)
        elif request.path == '/speed':
            self.json(dict(scale=self.server.controller.effect_scale))
        elif request.path == '/layout':
            layout = self.server.screen.layout(self.server.controller)
            layout['look_status'] = ''
            if self.server.plus and self.server.plus.options['look'] == 'vga':
                from sm.titles.ssb.ui.vga import revision_id
                layout['frame_revision'] = revision_id(layout['revision'])
                if not self.server.dqk_copy()['ok']:
                    layout['look_status'] = ('VGA is using the Silver Blades frame (no Dark Queen copy set on the Plus page). '
                                             'Only mods will look different.')
            if journal := getattr(self.server.controller, 'journal', None): layout['journal'] = journal.current()
            self.json(layout)
        elif request.path == '/overlay':
            token = parse_qs(request.query).get('id', [''])[0]
            payload = self.server.overlays.get(token)
            if payload is None: self.send_error(404, 'Frame overlay expired')
            else: self.reply(payload, 'application/json')
        elif request.path == '/frame':
            try:
                elapsed = float(parse_qs(request.query).get('t', ['0'])[0]) / 1000
                if not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError('invalid elapsed time')
            except ValueError:
                self.send_error(400, 't must be finite nonnegative milliseconds')
                return
            frame = self.server.screen.render(self.server.controller, self.server.assets, elapsed)
            body = frame.packet(self.server.screen.layout(self.server.controller)['revision']) if hasattr(frame, 'packet') else b''.join(frame.rows)
            if not hasattr(frame, 'packet') and getattr(self.server.screen, 'FRAME_FORMAT', None) == 'indexed-vga-v1':
                # One locked snapshot: palette-only changes affect the packet hash.
                body = (struct.pack('<4sHHHHI', b'SMV1', 320, 200, 256, 0, frame.revision) +
                        bytes(c for rgb in frame.palette for c in rgb) + body)
            overlay = getattr(frame, 'overlay', None)
            token = None
            if overlay and overlay['icons']:
                payload = json.dumps(overlay, separators=(',', ':')).encode('utf-8')
                token = hashlib.sha256(payload).hexdigest()
                self.server.overlays[token] = payload
                while len(self.server.overlays) > 8: del self.server.overlays[next(iter(self.server.overlays))]
            options = dict(overlay=token) if token else {}
            self.reply(body, 'application/octet-stream', frame_hash=hashlib.sha256(body).hexdigest(), **options)
        else:
            self.send_error(404)

    def do_POST(self):
        """ov28:03C9/13EE input adapter: validate a key/batch, apply keys in order, return once."""
        # Drain the declared body before *any* rejection, including route/origin
        # and content-type errors. Closing with unread bytes can reset the TCP
        # connection on Windows before the client receives send_error's reply.
        try:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(max(0, min(length, 65536)))
        except (ValueError, OSError):
            self.send_error(400, 'Invalid request body')  # Includes Connection: close.
            return
        if not self.local_request():
            return
        if urlsplit(self.path).path in ('/browse', '/journal/note'):
            if not self.matching_build(): return
            if self.headers.get_content_type() != 'application/json':
                self.send_error(415, 'Expected application/json')
                return
            if not 0 < length <= 16384 or len(body) != length:
                self.json(dict(error='Invalid body size'), status=400)
                return
            if urlsplit(self.path).path == '/browse':
                from sm.ui.folders import browse
                result, status = browse()
                self.json(result, status=status)
            else:
                from sm.ui.journal import post as journal_post
                with self.server.state_lock: journal_post(self, body)
            return
        if urlsplit(self.path).path == '/plus/bug':
            if not self.matching_build(): return
            if self.headers.get_content_type() != 'application/json':
                self.send_error(415, 'Expected application/json')
                return
            from sm.ui.plus import bug_report
            try:
                if not 0 < length <= 32768 or len(body) != length: raise ValueError('Invalid body size')
                with self.server.state_lock: result = bug_report(self.server, json.loads(body), BUILD_ID)
                self.json(result)
            except (ValueError, UnicodeError) as error: self.json(dict(error=str(error)), status=400)
            except OSError: self.json(dict(error='Cannot write the local bug report.'), status=500)
            return
        if urlsplit(self.path).path in ('/intake', '/dqk-intake'):
            if not self.matching_build(): return
            if self.headers.get_content_type() != 'application/json':
                self.send_error(415, 'Expected application/json')
                return
            try:
                if not 0 < length <= 16384 or len(body) != length: raise ValueError('Invalid body size')
                value = json.loads(body)
                if (not isinstance(value, dict) or not isinstance(value.get('folder'), str)
                        or len(value['folder']) > 4096 or '\0' in value['folder']): raise ValueError('Expected folder')
            except (ValueError, UnicodeError):
                self.json(dict(ok=False, message='Enter a folder path.'), status=400)
                return
            with self.server.state_lock:
                if urlsplit(self.path).path == '/dqk-intake':
                    if not self.server.plus:
                        self.json(dict(ok=False, message='Dark Queen frame settings are unavailable for this title.'), status=409)
                        return
                    try: result, status = self.server.choose_dqk_copy(value['folder'])
                    except OSError: result, status = dict(ok=False, message='Cannot save Dark Queen folder settings.'), 500
                    except ValueError: result, status = dict(ok=False, message='Enter a valid folder path.'), 400
                else: result, status = self.server.choose_folder(value['folder'])
                self.json(result, status=status)
            return
        if urlsplit(self.path).path in ('/preferences', '/speed') and self.server.plus:
            if not self.matching_build(): return
            if self.headers.get_content_type() != 'application/json':
                self.send_error(415, 'Expected application/json')
                return
            try:
                if not 0 < length <= 4096 or len(body) != length: raise ValueError('Invalid body size')
                value = json.loads(body)
                speed = urlsplit(self.path).path == '/speed'
                if speed: value = dict(effect_scale=value['scale'])
                with self.server.state_lock:
                    self.server.set_preferences(value)
                    result = dict(scale=self.server.plus.options['effect_scale']) if speed else self.server.preferences()
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                self.json(dict(error=str(error)), status=400)
                return
            except OSError:
                self.json(dict(error='Cannot save Plus settings'), status=500)
                return
            self.json(result)
            return
        if self.server.controller is None:
            self.json(dict(error='Choose a supported game folder first.', setup='/setup'), status=409)
            return
        if urlsplit(self.path).path == '/speed':                            # overlay setting, not game input: never logged as a key, never advances the game
            if not self.matching_build(): return
            try:
                with self.server.state_lock: self.server.controller.set_effect_scale(json.loads(body)['scale'])
            except (ValueError, KeyError, TypeError, UnicodeError):
                self.send_error(400, 'Expected {"scale": number from 0 to 10}')
                return
            self.json(dict(scale=self.server.controller.effect_scale))
            return
        if urlsplit(self.path).path != '/key':
            self.send_error(404)
            return
        self.server.log_input(body)
        if not self.matching_build():
            return
        if self.headers.get_content_type() != 'application/json':
            self.send_error(415, 'Expected application/json')
            return
        try:
            if not 0 < length <= 4096 or len(body) != length:
                raise ValueError('invalid body size')
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError('expected an object')
            batch = value.get('keys', [value])
            if not isinstance(batch, list) or not 0 < len(batch) <= 64: raise ValueError('invalid key batch')
            for key in batch:
                if not isinstance(key, dict): raise ValueError('invalid key')
                keysym, char = key.get('keysym'), key.get('char', '')
                if (not isinstance(keysym, str) or not 0 < len(keysym) <= 64 or
                        not isinstance(char, str) or len(char) > 1):
                    raise ValueError('invalid key')
        except (ValueError, UnicodeError):
            self.send_error(400, 'Expected keysym and a single character or empty char')
            return
        controller = self.server.controller
        # ov22:0DF3/0E1E: only append to the input FIFO during rest. Never run a
        # second Session.step or read a mutable frame from this request thread.
        if 'revision' not in value and controller.rest_active:
            controller.held_keys.extend(tuple((key['keysym'], key.get('char', '')) for key in batch))
            self.json({'queued': True, 'quit': False})
            return
        with self.server.state_lock: self.apply_keys(value, batch)

    def apply_keys(self, value, batch):
        """ov28:03C9: ordered decisions and revision checks run with exclusive game access."""
        controller = self.server.controller
        if 'revision' in value and value['revision'] != self.server.screen.layout(controller)['revision']:
            self.json({'decision': controller.session.decision, 'quit': controller.quit_requested})
            return
        try:
            for key in batch:
                controller.key(key['keysym'], key.get('char', ''))
                self.server.log_decision()
                if controller.quit_requested: break
        except TimeoutError as error:
            self.server.stopping = True
            print(str(error), flush=True)
            self.json(dict(error=str(error), quit=True), status=503)
            return
        self.json({'decision': controller.session.decision, 'quit': controller.quit_requested})


def open_browser(url):
    """GU-77 #30: Chrome/Edge app window, then the registered default browser."""
    for executable, relative in (('chrome', 'Google/Chrome/Application/chrome.exe'),
                                 ('msedge', 'Microsoft/Edge/Application/msedge.exe')):
        candidates = [shutil.which(executable), shutil.which(executable + '.exe')]
        candidates += [str(Path(os.environ[key]) / relative) for key in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)')
                       if os.environ.get(key) and (Path(os.environ[key]) / relative).is_file()]
        for candidate in dict.fromkeys(c for c in candidates if c):
            try:
                subprocess.Popen([candidate, '--app=' + url], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                return
            except OSError:
                continue
    webbrowser.open(url)


def run(session=None, port=8320, browser=True, *, session_factory=None, profile=None):
    """ov28:03C9 / GU-80 #45: log interactive play; GU-77 #30 browser launch."""
    from importlib import import_module
    from sm.titles import select
    profile = profile or (session.profile if session is not None else select())
    screen = import_module(profile.presentation)
    try:
        with Server(session, port, log_path=screen.LOCAL / 'web_play.log', session_factory=session_factory, profile=profile) as server:
            print('SilverMachine: ' + server.url + ' (F10 Save / Load / Quit; Ctrl+C stops the server)')
            if browser: open_browser(server.url)
            server.serve()
    except KeyboardInterrupt:
        pass
    finally:
        if session: session.close()
