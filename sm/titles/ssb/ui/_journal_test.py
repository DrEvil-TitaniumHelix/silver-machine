import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

from sm.engine import Session
from sm.ui.web import Server
from sm.ui.journal import Book, references, PAGES
from sm.titles.ssb.ui._web_test import Browser
from sm.titles.ssb.ui.screen import SAVE_ROOT


def test():
    assert references('Read JOURNAL ENTRY #37. Journal entry 5. Entry 12. Journal entry 999.') == [5, 37]
    assert len(PAGES) == 72 and PAGES[1] == 16 and PAGES[37] == 19 and PAGES[72] == 24
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='sm-journal-', dir=SAVE_ROOT) as directory, patch.dict(os.environ, SM_CONFIG_HOME=directory):
        root = Path(directory)
        with Server(Session(engines=True), 0, save_root=root / 'saves') as server:
            worker = Thread(target=server.serve, daemon=True); worker.start()
            browser = Browser(server.server_port)
            try:
                for _ in range(6): browser.request('/key', {'keysym': 'Return', 'char': ''})
                game = server.controller.session.game
                before = (game.s.hash(game.vm), game.s.seed, list(game.trace))
                snapshot = json.loads(browser.request('/journal')[0])
                assert any(e['number'] == 37 for e in snapshot['entries']), snapshot['entries']
                assert json.loads(browser.request('/layout')[0])['journal'] == [37]
                browser.request('/journal/note', {'text': 'Remember this square.', 'pin': True})
                assert server.controller.journal.history[-1]['pin'] is True
                for bad in ({'text': ''}, {'text': 'x' * 4001}, {'text': 'x', 'pin': 1}, []):
                    browser.request('/journal/note', bad, status=400)
                browser.request('/journal/note', {'text': 'x'}, headers={'Origin': 'https://example.invalid'}, status=403)
                browser.request('/journal/note', {'text': 'x'}, headers={'X-SM-Build': 'old'}, status=409)
                assert before == (game.s.hash(game.vm), game.s.seed, list(game.trace))
                from sm.ui import folders
                with patch.object(folders.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='{"ok":true,"folder":"","cancelled":true}')) as picker:
                    browser.request('/intake')
                    assert not picker.called
                    assert json.loads(browser.request('/browse', {})[0])['cancelled']
                    browser.request('/browse', {}, headers={'Origin': 'https://example.invalid'}, status=403)
                    assert picker.call_count == 1
                with patch.object(folders.subprocess, 'run', side_effect=OSError):
                    assert 'Type the folder path' in json.loads(browser.request('/browse', {}, status=503)[0])['message']
                from sm.titles.ssb.ui._test import townhall
                townhall(server.controller)
                for key in ('F10', 's', 'c', 'Escape'): browser.request('/key', {'keysym': key, 'char': key if len(key) == 1 else ''})
                browser.request('/journal/note', {'text': 'Unsaved later observation.'})
                for key in ('F10', 'l', 'c'): browser.request('/key', {'keysym': key, 'char': key if len(key) == 1 else ''})
                loaded = json.loads(browser.request('/journal')[0])
                assert loaded['slot'] == 'C'
                assert any(n['text'] == 'Remember this square.' for n in loaded['history'])
                assert all(n['text'] != 'Unsaved later observation.' for n in loaded['history'])
                stub = SimpleNamespace(_active={'folder': directory})
                book = Book(stub)
                assert book.info() == dict(available=False, mapped=False, machine=True)
                (root / 'Adventurers Journal.pdf').write_bytes(b'%PDF-1.4\n% synthetic test only\n')
                assert book.info()['available'] and not book.info()['mapped']
                with patch.object(server.controller.journal, 'book', book):
                    assert browser.request('/journal.pdf')[0].startswith(b'%PDF-')
                    assert all(e['page'] is None for e in json.loads(browser.request('/journal')[0])['entries'])
                (root / 'Adventurers Journal.pdf').unlink()
                with patch.object(server.controller.journal, 'book', book): browser.request('/journal.pdf', status=404)
                from sm.ui import journal as J
                words, lock_file = {'5': 'An invented entry.\nSecond line, with an accent: café.', '12': 'Another one.'}, root / 'lock.json'
                (root / 'ecl2.dax').write_bytes(b'invented game file' * 99)
                lock = J.seal(words, 'ssb', (root / 'ecl2.dax').read_bytes())
                assert lock['count'] == 2 and not any(w.encode().hex() in json.dumps(lock) for w in ('invented', 'Another'))
                lock_file.write_text(json.dumps(lock), encoding='utf-8')
                entry = lambda n: json.loads(browser.request('/journal/entry?n=%s' % n)[0])
                with patch.object(server.controller.journal, 'book', book), patch.object(J, 'lock_path', lambda title: lock_file):
                    assert entry(5) == dict(number=5, text=words['5']) and entry(12)['text'] == words['12']
                    assert entry(6)['text'] is None and entry('x')['text'] is None and entry('')['text'] is None
                    (root / 'ecl2.dax').write_bytes(b'another game file' * 99)
                    assert entry(5)['text'] is None
                    (root / 'ecl2.dax').write_bytes(b'invented game file' * 99)
                    assert entry(5)['text'] == words['5']
                    damaged = dict(lock, entries=dict(lock['entries']))
                    blob = bytearray.fromhex(damaged['entries']['5']); blob[-1] ^= 1; damaged['entries']['5'] = blob.hex()
                    lock_file.write_text(json.dumps(damaged), encoding='utf-8')
                    assert entry(5)['text'] is None and entry(12)['text'] == words['12']
                    lock_file.write_text('not a container', encoding='utf-8')
                    assert entry(5)['text'] is None
                    lock_file.unlink()
                    assert entry(5)['text'] is None
            finally:
                server.stopping = True; worker.join(3); browser.close()
    from sm.files import file_path
    for title, variable in (('ssb', 'SM_SECRET'), ('cok', 'SM_COK')):
        folder = os.environ.get(variable, '').strip()
        if not J.lock_path(title).is_file() or not folder:
            print('Journal text %s: no container or no game folder, skipped' % title); continue
        lock = json.loads(J.lock_path(title).read_text(encoding='utf-8'))
        key = J.lock_key(bytes.fromhex(lock['salt']), title, file_path(folder, lock['key_file']).read_bytes())
        opened = sum(J.unseal(lock, key, n) is not None for n in lock['entries'])
        assert opened == len(lock['entries']) == lock['count'] > 0, (title, opened, lock['count'])
        print('Journal text %s: %d entries open with the game file' % (title, opened))
    print('Journal: real entry 37, notes, native slot isolation, PDF fallback, sealed entry text, Browse gating and unchanged state PASS')
