"""New-party regression using only fingerprinted content, never installed saves."""
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
    from sm.titles.ssb.intake import require_folder, inspect_folder, file_path
    original = require_folder()
    version = inspect_folder(str(original))['version_id']
    # Resolve the current edition's fingerprint set; executable naming belongs to its loader.
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


if __name__ == '__main__': check()
