import os
from pathlib import Path
from tempfile import TemporaryDirectory


def area_session():
    from . import start_session
    session = start_session(saves=None, title=False)
    s = session.game.s
    s.dataset, s.block, s.x, s.y, s.dir = 2, 48, 6, 10, 6
    session.game.geo.load(s, 48)
    s.r0[0xE6] = 1
    return session


def journal_container(folder, prefix):
    import json
    from sm.files import file_path
    from sm.ui import journal
    lock = json.loads(journal.lock_path('dkk').read_text(encoding='utf-8'))
    numbers = sorted(map(int, lock['entries']))
    assert lock['format'] == 1 and lock['title'] == 'dkk' and lock['key_file'] == 'ECL2.DAX'
    assert numbers == [n for n in range(1, 67) if n != 13] and lock['count'] == len(numbers)
    key = journal.lock_key(bytes.fromhex(lock['salt']), 'dkk', file_path(folder, lock['key_file']).read_bytes())
    assert all(journal.unseal(lock, key, n) for n in numbers) and journal.unseal(lock, key, 13) is None
    assert journal.unseal(lock, journal.lock_key(bytes.fromhex(lock['salt']), 'dkk', b''), 1) is None
    assert journal.references(prefix + '38.', 66) == [38] and journal.references(prefix + '67.', 66) == []


def test():
    from unittest import SkipTest
    from unittest.mock import patch
    from sm.titles import select
    from sm.ui.web import Server
    from .. import intake
    from . import plus
    folder = intake.configured()
    if not folder: raise SkipTest('no Death Knights folder')
    with TemporaryDirectory(prefix='dkk-plus-') as root, patch.dict(os.environ, SM_CONFIG_HOME=root, SM_SAVE_ROOT=root, SM_DKK=folder):
        session = area_session()
        server = Server(None, 0, profile=select('dkk'), session_factory=lambda: session)
        try:
            c = server.controller
            assert c is not None, server.intake_error
            prefs = server.preferences()
            assert prefs['tabs'] == ['journal', 'map', 'help'] and prefs['supported'] == ['effect_scale', 'sound'] and prefs['persistent']
            assert prefs['help'] == plus.HELP and 'dqk_frame' not in prefs
            plus.test()
            server.plus.update(dict(effect_scale=2)); c.apply_plus(server.plus)
            assert c.effect_scale == 2 and server.plus.path == Path(root) / 'dkk-plus.json' and server.plus.path.is_file()
            area = plus.tab_data(c, 'map', {})
            assert area['available'] and len(area['cells']) == 256 and area['area'] == '2/48' and (area['x'], area['y'], area['facing']) == (6, 10, 6)
            session.game.s.r0[0xE6] = 0
            assert not plus.tab_data(c, 'map', {})['available']
            prefix = session.game.assets.text('journalEntryPrefix')
            journal_container(folder, prefix)
            book = c.journal.book.info()
            assert book['available'] and book['file'].lower() == 'journal.pdf' and not book['machine']
            session.game.vm.out.append(prefix + '38.')
            c.capture_text(); snap = c.journal.snapshot()
            assert [e['number'] for e in snap['entries']] == [38] and snap['current'] == [38]
            assert c.journal.book.entry_text(38) and c.journal.book.entry_text(13) is None
        finally: server.server_close(); session.close()
    return 'PASS plus'
