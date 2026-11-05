"""Journal boundaries: real citations, slot isolation, PDF fallback and read-only state."""
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
                # The real opening scene supplies the citation; no injected story.
                assert any(e['number'] == 37 for e in snapshot['entries']), snapshot['entries']
                assert json.loads(browser.request('/layout')[0])['journal'] == [37]
                browser.request('/journal/note', {'text': 'Remember this square.', 'pin': True})
                assert server.controller.journal.history[-1]['pin'] is True
                for bad in ({'text': ''}, {'text': 'x' * 4001}, {'text': 'x', 'pin': 1}, []):
                    browser.request('/journal/note', bad, status=400)
                browser.request('/journal/note', {'text': 'x'}, headers={'Origin': 'https://example.invalid'}, status=403)
                browser.request('/journal/note', {'text': 'x'}, headers={'X-SM-Build': 'old'}, status=409)
                # Read-only requests, personal notes and PDF inspection never change the game.
                assert before == (game.s.hash(game.vm), game.s.seed, list(game.trace))
                from sm.ui import folders
                with patch.object(folders.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='{"ok":true,"folder":"","cancelled":true}')) as picker:
                    browser.request('/intake')
                    assert not picker.called
                    assert json.loads(browser.request('/browse', {})[0])['cancelled']
                    browser.request('/browse', {}, headers={'Origin': 'https://example.invalid'}, status=403)
                    assert picker.call_count == 1
                with patch.object(folders.subprocess, 'run', side_effect=OSError):
                    assert 'type the folder path' in json.loads(browser.request('/browse', {}, status=503)[0])['message']
                # Saving another slot snapshots the journal; unsaved notes cannot leak on reload.
                from sm.titles.ssb.ui._test import townhall
                townhall(server.controller)
                for key in ('F10', 's', 'c', 'Escape'): browser.request('/key', {'keysym': key, 'char': key if len(key) == 1 else ''})
                browser.request('/journal/note', {'text': 'Unsaved later observation.'})
                for key in ('F10', 'l', 'c'): browser.request('/key', {'keysym': key, 'char': key if len(key) == 1 else ''})
                loaded = json.loads(browser.request('/journal')[0])
                assert loaded['slot'] == 'C'
                assert any(n['text'] == 'Remember this square.' for n in loaded['history'])
                assert all(n['text'] != 'Unsaved later observation.' for n in loaded['history'])
                # A changed/unknown PDF is readable without applying an incorrect known page map.
                stub = SimpleNamespace(_active={'folder': directory})
                book = Book(stub)
                assert book.info() == dict(available=False, mapped=False)
                (root / 'Adventurers Journal.pdf').write_bytes(b'%PDF-1.4\n% synthetic test only\n')
                assert book.info()['available'] and not book.info()['mapped']
                with patch.object(server.controller.journal, 'book', book):
                    assert browser.request('/journal.pdf')[0].startswith(b'%PDF-')
                    assert all(e['page'] is None for e in json.loads(browser.request('/journal')[0])['entries'])
                (root / 'Adventurers Journal.pdf').unlink()
                with patch.object(server.controller.journal, 'book', book): browser.request('/journal.pdf', status=404)
            finally:
                server.stopping = True; worker.join(3); browser.close()
    print('Journal: real entry 37, notes, native slot isolation, PDF fallback, Browse gating and unchanged state PASS')
