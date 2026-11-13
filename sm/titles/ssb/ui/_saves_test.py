from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os

from sm.titles.ssb import save
from sm.titles import ssb
from sm.engine import Session
from sm.titles.ssb.ui.screen import SAVE_ROOT, slot_directory, snapshot, write_slot_files
from sm.titles.ssb.ui._fight_test import press
from sm.titles.ssb.ui.screen import Assets, Controller, LOCAL, render


def same_saved_fields(a, b):
    for field in ('r0', 'r1', 'r2', 'dataset', 'x', 'y', 'dir', 'ahead', 'attr', 'mode', 'prev_mode', 'walls'):
        assert getattr(a, field) == getattr(b, field), field
    assert len(a.party) == len(b.party)
    for first, second in zip(a.party, b.party):
        assert (first.b, first.items, first.effects) == (second.b, second.items, second.effects)


def test(screenshot=False):
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    test_sidecars()
    test_autosave()
    ui, reference = Session(engines=True), None
    original = Path(save.SECRET) / 'SAVGAMA.DAT'
    original_bytes = original.read_bytes()
    with TemporaryDirectory(prefix='.test-', dir=SAVE_ROOT) as temporary:
        controller = Controller(ui, save_root=Path(temporary))
        try:
            taken = False
            for _ in range(40):
                decision = ui.decision
                if decision['kind'] == 'MOVE':
                    break
                if decision['kind'] == 'SHOP_MENU':
                    purpose = decision['info'].get('purpose')
                    action = ('no' if purpose == 'treasure leave' else 'take' if purpose == 'treasure' and not taken else
                              'items' if not taken else 'exit')
                    answer = decision['options'].index(action)
                elif decision['kind'] == 'LIST':
                    answer = decision['options'].index(None) if taken else 0
                    taken = True
                else:
                    answer = 0
                press(controller, answer)
            assert ui.decision['kind'] == 'MOVE'
            controller.key('m', 'm')
            for key in ('Left', 'Right', 'Up', 'Left', 'Right', 'Up'):
                assert controller.key(key)
            assert any(c.items for c in ui.game.s.party) and any(c.effects for c in ui.game.s.party)
            saved, count, state_hash = ui.game.s.copy(), len(ui.game.trace), ui.game.s.hash(ui.game.vm)
            controller.key('F10')
            if screenshot:
                render(controller, Assets()).save(LOCAL / 'ui_file_menu.png')
            controller.key('s', 's')
            if screenshot:
                render(controller, Assets()).save(LOCAL / 'ui_save.png')
            controller.key('t', 't')
            assert controller.files.message == 'Saved slot T'
            assert ui.game.s.hash(ui.game.vm) == state_hash and len(ui.game.trace) == count
            target = slot_directory('T', temporary)
            native = save.load(target, 'T')
            names = ['CHRDATT%d' % i for i in range(1, len(saved.party) + 1)]
            assert native['names'] == names
            assert save.dump(native) == snapshot(ui.game, 'T')
            assert (target / 'SAVGAMT.DAT').stat().st_size == 0x155D
            assert (target / (names[0] + '.STF')).stat().st_size > 0
            assert (target / (names[0] + '.SFX')).stat().st_size > 0
            controller.key('Escape')
            assert controller.key('Up')
            assert ui.game.s.y != saved.y
            controller.key('F10'); controller.key('l', 'l')
            if screenshot:
                render(controller, Assets()).save(LOCAL / 'ui_load.png')
            controller.key('t', 't')
            loaded = controller.session
            assert loaded is not ui and ui.decision is None
            same_saved_fields(saved, loaded.game.s)
            assert save.dump(native) == snapshot(loaded.game, 'T')
            reference = Session(engines=True, directory=target, slot='T')
            assert loaded.decision == reference.decision
            controller.key('m', 'm')
            for key, value in (('Left', 'turn-left'), ('Right', 'turn-right')):
                answer = loaded.decision['options'].index(value)
                controller.key(key)
                reference.step(answer)
                assert loaded.decision == reference.decision
            assert loaded.game.trace == reference.game.trace
            press(controller, loaded.decision['options'].index('camp'))
            press(controller, loaded.decision['options'].index('save'))
            assert loaded.decision['kind'] == 'CREATE_SLOT'
            picker = controller.file_picker()
            assert picker.native and picker.details['T'][0].endswith('Guy de Valois'), picker.details
            assert picker.rows()[0][0] == 'A' and picker.rows()[-1][0] == 'J'
            render(controller, Assets())
            from sm.titles.ssb.ui.screen import layout
            assert [r['key']['char'] for r in layout(controller)['regions'] if r['key']['char']] == list('abcdefghij')
            press(controller, loaded.decision['options'].index('J'))
            camp_files = dict(loaded.game.s.g['save.J'])
            assert save.dump(save.load(slot_directory('J', temporary), 'J')) == camp_files
            assert loaded.decision['info']['purpose']=='quit to DOS' and controller.selected==1
            assert controller.key('Return') and loaded.decision['kind']=='CAMP_MENU'
            before = loaded.game.s.hash(loaded.game.vm)
            controller.key('F10'); controller.key('l', 'l'); controller.key('z', 'z')
            assert controller.session is loaded and loaded.decision is not None
            assert controller.files.message and before == loaded.game.s.hash(loaded.game.vm)
            check_replace(target, temporary, native)
            controller.key('Escape'); controller.key('q', 'q')
            assert controller.quit_requested and loaded.decision is None
            assert original.read_bytes() == original_bytes
            print('UI saves: %d decisions -> native slot -> new Session; all saved fields equal; camp Save/Load/Quit: PASS' % count)
        finally:
            controller.session.close()
            ui.close()
            if reference:
                reference.close()


def check_replace(target, root, native):
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    native['pos'][0] ^= 1
    changed = save.dump(native)
    replace = os.replace
    failed = False

    def fail_once(src, dst):
        nonlocal failed
        if Path(src).name == 'SAVGAMT.DAT' and not failed:
            failed = True
            raise OSError('test write failure')
        return replace(src, dst)

    with patch.object(os, 'replace', fail_once):
        try:
            write_slot_files(changed, 'T', root)
        except OSError:
            pass
        else:
            raise AssertionError('write failure was swallowed')
    assert failed and {p.name: p.read_bytes() for p in target.iterdir()} == before
    (target / 'CHRDATT8.STF').write_bytes(bytes(67))
    write_slot_files(changed, 'T', root)
    assert not (target / 'CHRDATT8.STF').exists()
    for slot, where in (('../A', root), ('A', save.SECRET)):
        try:
            slot_directory(slot, where)
        except ValueError:
            pass
        else:
            raise AssertionError('save path escaped local/saves')

def test_autosave():
    from zipfile import ZipFile
    from sm.titles.ssb.ui import start_session
    from sm.titles.ssb.ui._test import townhall
    from sm.titles.ssb.ui.screen import load_autosave, write_autosave, write_slot, slot_details, Frame
    from sm.ui.web import Server
    with TemporaryDirectory(prefix='.autosave-test-', dir=SAVE_ROOT) as temporary:
        root = Path(temporary)
        session = Session(engines=True)
        server = Server(session, 0, save_root=root)
        controller = server.controller
        townhall(controller)
        write_slot(session, 'T', root)
        manual = snapshot(session.game, 'T')
        os.utime(root / 'T' / 'SAVGAMT.DAT', (1700000000, 1700000000))
        details = slot_details(root)
        assert '2023-11-14' in details['T'][0]
        assert 'Guy de Valois' in details['T'][0]
        assert ('Day %d' % session.game.s.r0[0xCA]) in details['T'][1]
        assert 'Area 1/16 (3,3)' in details['T'][1]
        controller.key('F10'); controller.key('l', 'l')
        seen = []
        for page in range(4):
            rows = controller.files.rows()
            seen.extend(row[0] for row in rows)
            regions = controller.files.regions()
            assert all(r['rect'][1] + r['rect'][3] <= 200 for r in regions)
            frame = Frame()
            with patch.object(frame, 'text') as text:
                controller.files.draw(frame, Assets())
            words = [call.args[2] for call in text.call_args_list]
            assert '%d/4 %s-%s' % (page + 1, rows[0][0], rows[-1][0]) in words
            if page == 2:
                assert any(details['T'][0] in word for word in words)
                assert any(details['T'][1] in word for word in words)
            controller.key('Next')
        assert seen == list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        controller.key('Escape'); controller.key('Escape')
        from types import SimpleNamespace
        from unittest.mock import Mock
        for index, letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
            pending = dict(kind='CREATE_SLOT', options=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'), info={})
            fixture = SimpleNamespace(game=session.game, decision=pending, step=Mock())
            keys = Controller(fixture, save_root=root)
            assert keys.key(letter, letter)==(index<10)
            if index<10: fixture.step.assert_called_once_with(index)
            else: fixture.step.assert_not_called()
        controller.key('Left')
        expected = snapshot(session.game, 'A', state=session.game.s.copy())
        before = session.game.s.hash(session.game.vm)
        controller.remember()
        assert session.game.s.hash(session.game.vm) == before, 'autosave changed live state'
        server.server_close()
        assert (root / 'autosave.zip').is_file() and not (root / 'A').exists()
        assert save.dump(save.load(root / 'T', 'T')) == manual
        with ZipFile(root / 'autosave.zip') as archive:
            assert {name: archive.read(name) for name in archive.namelist()} == expected
        loaded = start_session(root=root)
        try:
            assert snapshot(loaded.game, 'A') == expected
        finally:
            loaded.close()
        explicit = start_session(load='T', root=root)
        try:
            assert snapshot(explicit.game, 'T') == manual
        finally:
            explicit.close()
        with patch('sm.engine.Session') as constructor, patch('sm.titles.ssb.ui.screen.load_autosave') as reload:
            start_session(slot='A', root=root)
            constructor.assert_called_once_with(slot='A', engines=True, profile=ssb)
            reload.assert_not_called()
        previous = (root / 'autosave.zip').read_bytes()
        with patch('sm.titles.ssb.ui.screen.os.replace', side_effect=OSError('injected disk failure')):
            try: write_autosave(expected, root)
            except OSError: pass
            else: raise AssertionError('failed autosave reported success')
        assert (root / 'autosave.zip').read_bytes() == previous
        restored = load_autosave(root)
        controller = Controller(restored, save_root=root)
        controller.autosave_enabled = True
        controller.remember()
        safe = controller.autosave_files
        restored.pending = True
        restored.game.s.x ^= 1
        controller.autosave()
        assert controller.autosave_files is safe
        restored.pending = False
        restored.game.s.g['combat.active'] = 1
        controller.autosave()
        assert controller.autosave_files is safe
        restored.close()


def test_sidecars():
    from sm.titles.ssb.host import Game
    g = Game(lambda *a, **k: 0); original = snapshot(g, 'T')
    g.s.party[0].items = [bytearray(67)]; g.s.party[0].effects = [bytearray(9)]
    full = snapshot(g, 'T'); g.s.party[0].effects = []
    partial = snapshot(g, 'T'); partial['CHRDATT1.SFX'] = b''
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.sidecars-', dir=SAVE_ROOT) as root:
        target = write_slot_files(full, 'T', root); replace = os.replace; seen = []
        def inspect(src, dst):
            if Path(src).name == 'CHRDATT1.STF':
                assert not (target / 'CHRDATT1.STF').exists(), 'old STF not deleted before writing'
                assert not (target / 'CHRDATT1.SFX').exists(), 'empty SFX not deleted'
                seen.append(True)
            return replace(src, dst)
        with patch.object(os, 'replace', side_effect=inspect): write_slot_files(partial, 'T', root)
        assert seen and (target / 'CHRDATT1.STF').stat().st_size == 67 and not (target / 'CHRDATT1.SFX').exists()
        assert original == snapshot(Game(lambda *a, **k: 0), 'T'), 'source game changed'
