import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def check():
    from sm.titles.ssb.ui import start_session
    from sm.titles.ssb.ui.screen import Assets, Controller, SAVE_ROOT, load_slot, render
    from sm.titles.ssb.ui._fight_test import press
    from sm.titles.ssb import intake
    source = Path(intake.require_folder())
    before = {p.name: intake.fingerprint(p) for p in source.iterdir()}
    session = start_session()
    controller = Controller(session)
    assets = Assets()
    try:
        assert session.decision['kind'] == 'CREATE_MENU' and not session.game.s.party
        assert session.game.directory == str(SAVE_ROOT.resolve())
        assert session.game.s.r0[0xF2] == 0 and session.game.s.r0[0x1F4] == 2
        assert session.game.s.dataset == 1 and not session.game.vm.resuming
        for _ in range(70):
            d = session.decision
            assert d is not None, session.result
            render(controller, assets)
            kind, options = d['kind'], d['options']
            if kind == 'MOVE': break
            if kind == 'CREATE_MENU': value = 'begin' if session.game.s.party else 'add' if 'character.ALPHA' in session.game.s.g else 'create'
            elif kind == 'CREATE_RACE': value = 6
            elif kind == 'CREATE_CLASS': value = 2
            elif kind == 'CREATE_ROLL': value = 'keep'
            elif kind == 'CREATE_NAME': press(controller, 'ALPHA'); continue
            elif kind == 'CREATE_ICON':
                controller.key('e', 'e'); controller.key('y', 'y'); continue
            elif kind == 'CREATE_ADD':
                controller.key('e', 'e') if session.game.s.party else controller.key('Return')
                continue
            elif kind == 'SHOP_MENU': value = 'no' if d['info'].get('purpose') == 'treasure leave' else 'exit'
            else: value = options[0] if options else 0
            press(controller, options.index(value) if options else value)
        else: raise AssertionError('new party did not reach exploration')
        state = session.game.s
        assert (SAVE_ROOT / 'ALPHA.WHO').is_file()
        assert (state.dataset, state.block, state.x, state.y) == (1, 16, 3, 3)
        first = state.x, state.y
        press(controller, session.decision['options'].index('forward'))
        assert (state.x, state.y) != first, 'first forward did not move'
        at = state.x, state.y, state.dir
        controller.key('F10'); controller.key('s', 's'); controller.key('z', 'z')
        assert (SAVE_ROOT / 'Z/SAVGAMZ.DAT').is_file()
        restored = load_slot('Z')
        try:
            assert restored.decision['kind'] == 'MOVE', restored.result
            assert (restored.game.s.x, restored.game.s.y, restored.game.s.dir) == at
            assert len(restored.game.s.party) == 1 and bytes(restored.game.s.party[0].b[:16]) == bytes(state.party[0].b[:16])
        finally: restored.close()
        controller.autosave_enabled = True
        controller.autosave()
        restored = start_session()
        try:
            assert restored.decision['kind'] == 'MOVE'
            assert (restored.game.s.x, restored.game.s.y, restored.game.s.dir) == at
        finally: restored.close()
        assert {p.name: intake.fingerprint(p) for p in source.iterdir()} == before
        print('New party: creation, add, begin, area 1/16, forward, Z reload, autosave reload, immutable input PASS')
    finally: session.close()


def test():
    check_party()
    from sm.titles.ssb.intake import require_folder, inspect_folder, file_path
    original = require_folder()
    version = inspect_folder(str(original))['version_id']
    from sm.titles.ssb.intake import catalog
    entry = next(v for v in catalog()['versions'] if v['id'] == version)
    with TemporaryDirectory(prefix='new-party-') as temporary:
        root = Path(temporary); content = root / 'game'; content.mkdir()
        for name in entry['files']: shutil.copyfile(file_path(original, name), content / name)
        env = dict(os.environ, SM_SECRET=str(content), SM_CONFIG_HOME=str(root / 'config'), SM_SAVE_ROOT=str(root / 'saves'))
        code = "import sys; sys.path.insert(0, %r); from sm.titles.ssb._start_test import check; check()" % str(Path(__file__).resolve().parents[3])
        result = subprocess.run([sys.executable, '-I', '-c', code], env=env, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())


def check_party():
    from unittest.mock import patch
    from sm.titles.ssb import rec, save, host
    from sm.titles.ssb.ui import screen
    from sm.titles.ssb.state import State
    screen.SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='seed-party-', dir=screen.SAVE_ROOT) as temporary:
        root = Path(temporary)
        with patch.object(save, 'load', side_effect=AssertionError('seed read a saved game')):
            assert rec.seed_max_party(root)
        directory = root / 'A'
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        data = save.load(directory, 'A')
        assert [bytes(r)[1:1 + bytes(r)[0]].decode('latin1') for r in data['party']] == [r[0] for r in rec.MAX_PARTY_RECIPE]
        assert [r.get('hp') for r in data['party']] == [144, 142, 70, 111, 112, 70]
        assert [list(r.get('level')) for r in data['party']] == [
            [0, 0, 0, 15, 0, 0, 0], [0, 0, 0, 0, 15, 0, 0], [0, 0, 0, 0, 0, 15, 0],
            [0, 0, 9, 0, 0, 0, 18], [15, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 15, 0]]
        fresh = host.Game(None, slot=None, directory=root).s
        assert data['pos'] == [fresh.x, fresh.y, fresh.dir, fresh.ahead, fresh.attr]
        save.sync_globals(fresh)
        assert data['r0'] == fresh.r0 and data['dataset'] == 2 and data['r0'][0xF2] == 0
        loaded = State(); save.restore(loaded, data)
        for r, c in zip(data['party'], loaded.party):
            assert bytes(r) == bytes(c.b), 'load changed derived stats'
            assert len(c.items) == 4 and all(i[0x34] for i in c.items)
            assert c.b[0x199] <= 2
        marker = directory / 'keep.txt'; marker.write_text('player-owned')
        assert not rec.seed_max_party(root)
        assert {p.name: p.read_bytes() for p in directory.iterdir() if p != marker} == before
        (directory / 'SAVGAMA.DAT').unlink()
        assert not rec.seed_max_party(root) and not (directory / 'SAVGAMA.DAT').exists()
        (directory / 'SAVGAMA.DAT').write_bytes(before['SAVGAMA.DAT'])
        session = host.Session(slot=None, engines=True, directory=root)
        try:
            assert not session.game.s.party and session.decision['kind'] == 'CREATE_MENU'
            session.step(session.decision['options'].index('load'))
            assert 'A' in session.decision['options']
            session.step(session.decision['options'].index('A'))
            assert session.decision is not None, session.result
            assert len(session.game.s.party) == 6 and session.error is None
            session.step(session.decision['options'].index('begin'))
            assert session.decision is not None and session.error is None, session.result
            assert session.game.entry == (2, 17, 0x8014)
        finally: session.close()


if __name__ == '__main__': check()
