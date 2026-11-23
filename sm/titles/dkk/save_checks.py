from pathlib import Path
from tempfile import TemporaryDirectory
import struct


def test():
    from sm.files import file_index
    from sm.titles.ssb.state import State
    from sm.titles.cok.records import SavedGame as ImportedGame, Character as ImportedCharacter
    from . import save, save_vault, rules
    from .menu import Game
    from .records import Character, Spells, Item, Effect
    from .intake import require_folder
    from types import SimpleNamespace
    from unittest.mock import patch
    from .faults import BindingRequired
    bare = rules.character(bytes(Character()))
    caster = rules.character(bytes(Character()), (bytes(Item()),) * 2,
                             (bytes(Effect()),) * 3, spells=bytes(Spells()))
    rules.record(bare).set('spells_pointer', 123)
    rules.record(caster).set('spells_pointer', 0)
    unchanged = tuple(rules.write_character(char) for char in (bare, caster))
    assert save.party_size(()) == 0
    assert save.space_required((), True) == 0 and save.space_required((), False) == 2568
    assert save.party_size((bare,)) == 216
    assert save.party_size((caster,)) == 589
    assert save.party_size(iter((bare, caster))) == 805
    assert save.space_required((bare, caster), True) == 805
    assert save.space_required((bare, caster), False) == 3373
    assert save.party_size((caster,) * 112) == 432
    assert save.space_required((caster,) * 112, False) == 3000
    assert save.party_size((bare,) * 292) == 63072
    assert save.space_required((bare,) * 292, False) == 104
    assert save.space_required((bare,) * 292, True) == 63072
    assert save.party_size((bare,) * 8192) == 0
    assert save.space_required((bare,) * 8192, False) == 2568
    assert tuple(rules.write_character(char) for char in (bare, caster)) == unchanged
    texts = {'yesNoOptions': 'Yes No'}
    assets = SimpleNamespace(text=lambda name: texts.get(name, '<' + name + '>'))
    for drive, selected, searches, creations, labels, answers, expected in (
            ('C', 1, (0,), (), ('CHAMP',), (), ('label', 'search')),
            ('A', 1, (0,), (), ('CHAMP', 'CHAMP', ''), (), ('label', 'pause', 'label', 'pause', 'label', 'search')),
            ('a', 1, (0,), (), ('CHAMP',), (), ('label', 'search')),
            ('C', 1, (2,), (0,), ('',), (), ('label', 'search', 'mkdir')),
            ('C', 0, (18,), (5,), ('',), (), ('label', 'search', 'mkdir')),
            ('A', 1, (2,), (0,), ('',), (0,), ('label', 'search', 'confirm', 'mkdir')),
            ('b', 0, (18,), (5,), ('CHAMP',), (1,), ('label', 'search', 'confirm', 'pause', 'mkdir')),
            ('A', 1, (2, 0), (3,), ('',), (1,), ('label', 'search', 'confirm', 'pause', 'mkdir', 'search')),
            ('A', 0, (2, 18), (3, 0), ('',), (0, 1), ('label', 'search', 'confirm', 'mkdir', 'search', 'confirm', 'pause', 'mkdir')),
            ('C', 1, (18, 0), (3,), ('',), (), ('label', 'search', 'mkdir', 'search')),
            ('C', 0, (5,), (), ('',), (), ('label', 'search', 'pause')),
            ('C', -1, (3,), (), ('',), (), ('label', 'search', 'pause')),
            ('A', 1, (5,), (), ('',), (), ('label', 'search', 'pause')),
            ('B', 0, (3, 0), (), ('',), (), ('label', 'search', 'pause', 'search'))):
        calls = []
        native = drive + ':\\NATIVE\\'
        imported = drive + ':\\IMPORTED\\'
        chosen = native if selected == 1 else imported
        search_results, creation_results, label_results, replies = map(iter, (searches, creations, labels, answers))
        def search(path):
            assert path == chosen[:-1]
            calls.append('search')
            return next(search_results)
        def mkdir(path):
            assert path == chosen[:-1]
            calls.append('mkdir')
            return next(creation_results)
        def label(letter):
            assert letter == drive
            calls.append('label')
            return next(label_results)
        def host_path(path):
            assert path == chosen[:-1]
            return Path('local') / 'compare' / 'dkk' / 'save' / 'directory-check'
        def ask(kind, options, **info):
            if kind == 'CONFIRM':
                calls.append('confirm')
                prefix = 'askSaveDiskPrefix' if selected == 1 else 'askChampionsDiskPrefix'
                assert info == dict(prompt=assets.text(prefix) + drive + assets.text('askDiskSuffix'), start=0)
                assert options == ('Yes', 'No')
                return next(replies)
            calls.append('pause')
            assert kind == 'ACK' and options == ('Continue',)
            prompt = assets.text('saveDirectoryName') + drive + ':'
            if drive.upper() >= 'C':
                prompt = assets.text('noChampionsDirectoryMessage' if selected == 0 else 'noSaveDirectoryMessage')
            assert info == dict(prompt=prompt, message_colour=14)
            return 0
        filesystem = SimpleNamespace(save_path=native, champions_path=imported, search=search,
                                     mkdir=mkdir, volume_label=label, host_path=host_path)
        state = State()
        state.g['save.file_format'] = selected
        state.treasure_money[4] = 12345
        state.treasure_items.append(bytearray(63))
        game = SimpleNamespace(s=state, assets=assets, ask=ask, save_filesystem=filesystem)
        result = save.check_directory(game)
        failed = drive.upper() >= 'C' and searches[-1] not in (0, 2, 18)
        assert result == (None if failed else host_path(chosen[:-1]))
        assert calls == list(expected)
        assert state.g == {'save.file_format': selected}
        assert state.treasure_money[4] == 12345 and state.treasure_items == [bytearray(63)]
    game = SimpleNamespace(s=State())
    for filesystem in (None, SimpleNamespace()):
        game.save_filesystem = filesystem
        try: save.check_directory(game)
        except BindingRequired: pass
        else: raise AssertionError('Missing directory binding accepted')
    game.s.g['save.file_format'] = 1
    game.save_filesystem = SimpleNamespace(save_path='')
    try: save.check_directory(game)
    except BindingRequired: pass
    else: raise AssertionError('Empty directory path accepted')
    for suffix in ('', 'SAVE'):
        game.save_filesystem = SimpleNamespace(save_path='C:\\SAVE\\',
                                               host_path=lambda path: require_folder() / suffix)
        try: save.check_directory(game)
        except ValueError: pass
        else: raise AssertionError('Original directory accepted')
    for drive, search_error, exists, available, party, admitted in (
            ('c', 5, False, 10000, (bare, caster), False),
            ('C', 0, True, 804, (bare, caster), False),
            ('C', 0, True, 805, (bare, caster), True),
            ('C', 0, True, 806, (bare, caster), True),
            ('b', 0, False, 3372, (bare, caster), False),
            ('b', 0, False, 3373, (bare, caster), True),
            ('C', 0, False, 3374, (bare, caster), True),
            ('C', 0, True, -1, (), False),
            ('C', 0, True, 0, (), True),
            ('C', 0, True, 432, (caster,) * 112, True),
            ('C', 0, False, 104, (bare,) * 292, True)):
        with TemporaryDirectory(prefix='sm-dkk-admission-') as folder:
            root = Path(folder)
            state = State()
            state.party = list(party)
            state.r0[0xFC:0x100] = b'\x09\x08\x07\x06'
            state.r1[0x312] = 11
            state.r1[0x33E] = 255
            state.g.update({'save.file_format': 0, 'save.recent': 0, 'dkk.delay': 3,
                            'vault.pending': 1, 'vault.letter': 'Q'})
            state.treasure_money[4] = 456
            unchanged = (bytes(state.r0), bytes(state.r1), bytes(state.r2), dict(state.g),
                         tuple(rules.write_character(char) for char in state.party))
            trace = []
            native = drive + ':\\SAVES\\'
            def record_call(name, value, result):
                assert state.g['save.file_format'] == 1
                trace.append((name, value))
                return result
            filesystem = SimpleNamespace(save_path=native,
                host_path=lambda path: record_call('path', path, root),
                volume_label=lambda letter: record_call('label', letter, ''),
                search=lambda path: record_call('search', path, search_error),
                exists=lambda path: record_call('exists', path, exists),
                disk_free=lambda number: record_call('free', number, available))
            game = SimpleNamespace(s=state, assets=assets, save_filesystem=filesystem,
                ask=lambda kind, options, **info: record_call('pause', (kind, options, info), 0))
            if admitted: assert save.admit_save(game, 'j') == root
            else: assert save.save_game(game, 'j') is None
            expected = [('path', native[:-1]), ('label', drive), ('search', native[:-1])]
            if not search_error:
                expected.extend((('exists', native + assets.text('saveGameStem') + 'J.pty'),
                                 ('free', ord(drive.upper()) - 64)))
            if not admitted:
                message = 'noSaveDirectoryMessage' if search_error else 'diskFullMessage'
                expected.append(('pause', ('ACK', ('Continue',),
                                          dict(prompt=assets.text(message), message_colour=14))))
            assert trace == expected
            assert (bytes(state.r0), bytes(state.r1), bytes(state.r2)) == unchanged[:3]
            assert state.g == dict(unchanged[3], **{'save.file_format': 1})
            assert tuple(rules.write_character(char) for char in state.party) == unchanged[4]
            assert state.treasure_money[4] == 456 and not list(root.iterdir())
    state = State()
    pauses = []
    game = SimpleNamespace(s=state, assets=assets,
        ask=lambda kind, options, **info: pauses.append((kind, options, info)))
    try: save.admit_save(game, 'K')
    except ValueError: pass
    else: raise AssertionError('Invalid admission slot accepted')
    assert not state.g
    from . import creation
    state.g['save.file_format'] = 0
    def refused_directory(folder):
        assert state.g == {'save.file_format': 1}
        raise OSError('Directory unavailable')
    with patch.object(creation, 'save_directory', refused_directory):
        try: save.save_game(game, 'K')
        except ValueError: pass
        else: raise AssertionError('Invalid save slot accepted')
        assert state.g == {'save.file_format': 0}
        assert save.save_game(game, 'A') is None
        assert pauses == [('ACK', ('Continue',), dict(prompt=assets.text('noSaveDirectoryMessage'), message_colour=14))]
    assert state.g == {'save.file_format': 1}
    for filesystem in (SimpleNamespace(), SimpleNamespace(exists=lambda path: True)):
        game.save_filesystem = filesystem
        with patch.object(save, 'check_directory', return_value=Path('local')):
            try: save.admit_save(game, 'A')
            except BindingRequired: pass
            else: raise AssertionError('Missing admission disk binding accepted')
    with TemporaryDirectory(prefix='sm-dkk-space-') as folder:
        root = Path(folder)
        game = Game(None)
        state, assets = game.s, game.assets
        game.ask = lambda kind, options, **info: pauses.append((kind, options, info))
        game.roster_directory = root
        state.party = [bare]
        state.g.update({'save.recent': 0, 'vault.pending': 1, 'dkk.delay': 7})
        for name in ('tmpvault.dat', 'savgamj.pty', 'chrdatj1.gam', 'vaultj.dat'):
            (root / name).write_bytes(b'previous')
        before = {path.name: path.read_bytes() for path in root.iterdir()}
        zones = bytes(state.r0), bytes(state.r1)
        for slot, capacity in (('A', SimpleNamespace(free=2783)), ('J', SimpleNamespace(free=215)), ('J', OSError())):
            pauses.clear()
            with patch('shutil.disk_usage', side_effect=[capacity]) as usage:
                assert creation.save_game(game, slot) is None
                usage.assert_called_once_with(root)
            assert pauses == [('ACK', ('Continue',), dict(prompt=assets.text('diskFullMessage'), message_colour=14))]
            assert (bytes(state.r0), bytes(state.r1)) == zones
            assert state.g['save.recent'] == 0 and state.g['vault.pending'] == 1
            assert {path.name: path.read_bytes() for path in root.iterdir()} == before
        for slot, available in (('J', 216), ('A', 2784)):
            with patch('shutil.disk_usage', return_value=SimpleNamespace(free=available)):
                assert creation.save_game(game, slot).slot == slot
            assert len(save.load(root, slot).members) == 1 and state.g['save.recent'] == 1
        game.roster_directory = root / 'unused'
        game.save_filesystem = SimpleNamespace(save_path='C:\\SAVES\\', host_path=lambda path: root,
            volume_label=lambda drive: '', search=lambda path: 0, exists=lambda path: False,
            disk_free=lambda number: 2784)
        assert creation.save_game(game, 'B').slot == 'B' and not game.roster_directory.exists()
        assert len(save.load(root, 'B').members) == 1
        (root / 'VAULTC.DAT').write_bytes(b'old')
        available = iter((2784, 216, 11))
        game.save_filesystem.disk_free = lambda drive: next(available)
        pauses.clear()
        assert creation.save_game(game, 'C').slot == 'C'
        assert pauses == [('ACK', ('Continue',), dict(prompt=assets.text(message), message_colour=14))
                          for message in ('noRoomMessage', 'insertDiskMessage')]
        assert (root / 'VAULTC.DAT').read_bytes() == (root / 'VAULTB.DAT').read_bytes()
        assert state.g['vault.letter'] == 'C' and state.g['vault.pending'] == 0
        game.roster_directory = root
        game.save_filesystem = None
        occupied = root / 'SAVGAMH.PTY'
        occupied.mkdir()
        state.r0[0xFC], state.g['dkk.delay'] = 3, 7
        state.r1[0x312], state.dataset = 1, 3
        state.g.update({'save.recent': 0, 'vault.pending': 1})
        (root / 'TMPVAULT.DAT').write_bytes(b'pending')
        old_files = {name: path.read_bytes() for name, path in file_index(root).items()}
        zones = bytes(state.r0), bytes(state.r1)
        pauses.clear()
        assert creation.save_game(game, 'H') is None
        assert pauses == [('ACK', ('Continue',), dict(prompt=assets.text('noSaveDirectoryMessage'), message_colour=14))]
        assert zones == (bytes(state.r0), bytes(state.r1))
        assert state.g['save.recent'] == 0 and state.g['vault.pending'] == 1
        assert {name: path.read_bytes() for name, path in file_index(root).items()} == old_files
        game.save_filesystem = SimpleNamespace(save_path='b:\\SAVES\\', host_path=lambda path: root,
            volume_label=lambda drive: '', search=lambda path: 0, exists=lambda path: False,
            disk_free=lambda number: 2784)
        def change_disk(kind, choices, **info):
            assert (kind, choices) == ('ACK', ('Continue',))
            assert info == dict(prompt=assets.text('saveDirectoryName') + 'b:', message_colour=14)
            assert zones == (bytes(state.r0), bytes(state.r1))
            occupied.rmdir()
            (root / 'savgamh.pty').write_bytes(b'old slot')
        game.ask = change_disk
        assert creation.save_game(game, 'H').slot == 'H'
        assert len(save.load(root, 'H').members) == 1
        assert state.r0[0xFC] == 7 and state.r1[0x312] == 3
        assert state.g['save.recent'] == 1 and state.g['vault.pending'] == 0
        game.save_filesystem = None
        state.party = [bare] * 9
        state.r0[0xFC] = 3
        old_files = {name: path.read_bytes() for name, path in file_index(root).items()}
        try: creation.save_game(game, 'H')
        except ValueError: pass
        else: raise AssertionError('Unrepresentable party accepted')
        assert {name: path.read_bytes() for name, path in file_index(root).items()} == old_files
        assert state.r0[0xFC] == 3
    with TemporaryDirectory(prefix='sm-dkk-member-order-') as folder:
        root = Path(folder)
        game = Game(None)
        game.roster_directory = root
        for name in (b'CHRDATA2', b'CHRDATA1'):
            char = rules.character(bytes(Character()), [bytes(Item())], [bytes(Effect())], spells=bytes(Spells()))
            rules.record(char).set('name', (bytes([len(name)]) + name).ljust(16, b'\0'))
            game.s.party.append(char)
        for stem in ('chrdata1', 'chrdata2'):
            for suffix in ('pc', 'wiz', 'jnk', 'eff'):
                (root / (stem + '.' + suffix)).write_bytes(b'old')
        for _ in range(2):
            snapshot = creation.save_game(game, 'A')
            restored = save.load(root, 'A')
            assert set(restored.members['CHRDATA1']) == {'GAM'}
            assert set(restored.members['CHRDATA2']) == {'GAM', 'WIZ', 'JNK', 'EFF'}
            for suffix, records in restored.members['CHRDATA2'].items():
                assert tuple(map(bytes, records)) == tuple(map(bytes, snapshot.members['CHRDATA2'][suffix]))
            assert not any(name.endswith('.PC') for name in file_index(root))
    with TemporaryDirectory(prefix='sm-dkk-member-open-') as folder:
        root = Path(folder)
        game = Game(None)
        game.roster_directory = root
        for name in (b'FIRST', b'SECOND'):
            char = rules.character(bytes(Character()), [bytes(Item())])
            rules.record(char).set('name', (bytes([len(name)]) + name).ljust(16, b'\0'))
            game.s.party.append(char)
            (root / (name.decode() + '.PC')).write_bytes(b'roster')
        blocked = root / 'CHRDATA1.GAM'
        blocked.mkdir()
        old_items = root / 'CHRDATA1.JNK'
        old_items.write_bytes(b'old items')
        notices = []
        def acknowledge(kind, options, **info):
            assert (kind, options) == ('ACK', ('Continue',))
            assert (root / 'SAVGAMA.PTY').is_file() and not (root / 'CHRDATA2.GAM').exists()
            notices.append(info)
        game.ask = acknowledge
        assert creation.save_game(game, 'A').slot == 'A'
        assert notices == [dict(prompt=game.assets.text('noSaveDirectoryMessage'), message_colour=14)]
        assert blocked.is_dir() and old_items.read_bytes() == b'old items'
        assert tuple(save.load(root, 'A').members) == ('CHRDATA2',)
        assert not (root / 'FIRST.PC').exists() and not (root / 'SECOND.PC').exists()
        assert game.s.g['save.recent'] == 1
        game.save_filesystem = SimpleNamespace(save_path='a:', host_path=lambda path: root,
            volume_label=lambda drive: '', search=lambda path: 0, exists=lambda path: True,
            disk_free=lambda drive: 8192)
        def replace_disk(kind, options, **info):
            assert (kind, options) == ('ACK', ('Continue',))
            assert info == dict(prompt=game.assets.text('saveDirectoryName') + 'a:', message_colour=14)
            blocked.rmdir()
            (root / 'chrdata1.gam').write_bytes(b'previous member')
        game.ask = replace_disk
        assert creation.save_game(game, 'A').slot == 'A'
        assert tuple(save.load(root, 'A').members) == ('CHRDATA1', 'CHRDATA2')
        assert len(old_items.read_bytes()) == Item.SIZE
    with TemporaryDirectory(prefix='sm-dkk-character-space-') as folder:
        root = Path(folder)
        game = Game(None)
        game.s.party = [caster]
        game.s.g['save.file_format'] = 0
        searches, notices = [], []
        space = iter((3373, 368, -1, 368, 12))
        game.save_filesystem = SimpleNamespace(save_path='b:', host_path=lambda path: root,
            volume_label=lambda drive: '', search=lambda path: searches.append(path) or 0,
            exists=lambda path: False, disk_free=lambda drive: next(space))
        choices = iter((1, 2, 0))
        def choose_disk(kind, options, **info):
            assert game.s.g['save.file_format'] == 1 and (root / 'SAVGAMA.PTY').exists()
            assert not (root / 'CHRDATA1.GAM').exists()
            notices.append(kind)
            if kind == 'ACK':
                assert options == ('Continue',) and info == dict(prompt=game.assets.text('diskFullMessage'), message_colour=14)
                return 0
            assert options == (*game.assets.text('tryAnotherDiskMenu').split(' ', 1), 'escape')
            prompt = game.assets.text('loseCharacterPrompt')
            assert info == dict(prompt=prompt, query=prompt, start=0)
            return next(choices)
        game.ask = choose_disk
        assert creation.save_game(game, 'A').slot == 'A'
        assert notices == ['ACK', 'MENU'] * 3 and len(searches) == 4
        assert len((root / 'CHRDATA1.WIZ').read_bytes()) == Spells.SIZE
        assert len((root / 'CHRDATA1.JNK').read_bytes()) == 2 * Item.SIZE
        assert len((root / 'CHRDATA1.EFF').read_bytes()) == 3 * Effect.SIZE
        for member, available in ((caster, 369), (SimpleNamespace(items=[None] * 1040, effects=()), 200)):
            game.save_filesystem.disk_free = lambda drive: available
            assert save.admit_character(game, member) == root
    for orders, count, npc, expected in (((), 0, 0, 0), ((0, 2), 5, 127, 1),
            (tuple(range(8)), 255, 128, 8), ((255, 9, 1), 7, 255, 0)):
        appended = SimpleNamespace(s=State())
        for order in orders:
            existing = rules.character(bytes(Character()))
            rules.record(existing).set('order', order)
            appended.s.party.append(existing)
        appended.s.r1[0x33E] = count
        char = rules.character(bytes(Character()))
        rules.record(char).set('npc', npc)
        rules.record(char).set('order', expected)
        seen = []
        def observe(member):
            seen.append((member is char, appended.s.selc() is char,
                         rules.record(member).get('order'), appended.s.r1[0x33E]))
        with patch.object(rules, 'recalc_class_stats', observe), patch.object(rules, 'recalc_stats') as stats:
            save.append_character(appended, char)
            stats.assert_not_called()
        assert appended.s.party[-1] is char and appended.s.selc() is char
        assert [rules.record(member).get('order') for member in appended.s.party] == [*orders, expected]
        assert appended.s.r1[0x33E] == (count + 1) & 255
        assert seen == ([(True, True, expected, (count + 1) & 255)] if npc > 127 else [])
    source = save.load(require_folder() / 'SAVE')
    with TemporaryDirectory(prefix='sm-dkk-linked-add-') as directory:
        folder = Path(directory)
        game = Game(None)
        game.roster_directory = folder
        party = list(source.members.values())[:3]
        for files in party[:2]:
            save.restore_member(game, files)
        first, second = game.s.party
        game.s.monsters.append(game.s.party.pop())
        save.restore_member(game, party[2])
        third = game.s.selc()
        assert game.s.chars() == [first, second, third] and game.s.sel == 2
        assert rules.record(third).get('order') == 2 and game.s.r1[0x33E] == 3
        with patch.object(save, 'free_space', return_value=save.space_required([first, second], False)):
            game.ask = lambda *args, **kwargs: 0
            assert save.save_game(game, 'B') is None and not list(folder.iterdir())
        saved = save.save_game(game, 'B')
        assert saved.game.get('party_count') == 3
        reloaded = Game(None)
        snapshot = save.load_game(reloaded, 'B', folder)
        assert reloaded.s.selc() is reloaded.s.party[0]
        held = [item for char in reloaded.s.party for item in char.items]
        filed = [item for files in snapshot.members.values() for item in files.get('JNK', ())]
        assert held and len(held) == len(filed)
        assert all(item is reloaded.item_pool.slots[i] for i, item in enumerate(held))
        assert all(item is not record.data for item, record in zip(held, filed))
        assert [rules.record(c).get('name') for c in reloaded.s.chars()] == [
            files['GAM'][0].get('name') for files in party]
        game.s.mode = 5
        assert save.game_image(game.s, 'B').get('party_count') == 1
    state = State()
    state.g.update({'save.recent': 1, 'untouched': 37})
    state.seed = 4660
    save.apply_image(state, source.game)
    assert state.g['save.recent'] == 1 and state.g['untouched'] == 37 and state.seed == 4660
    assert state.g['dkk.delay'] == state.r0[0xFC]
    assert state.g['dkk.pictures'] == state.r0[0xFF] // 2
    state.party = list(source.members)
    pairs = (4, 3, 8, 2, 65535, 65535, 0, 1)
    source.game.set('walls', struct.pack('<8H', *pairs))
    save.apply_image(state, source.game)
    image = save.game_image(state, 'a')
    assert image.get('walls') == struct.pack('<8H', *pairs)
    state.walls[1] = 9
    assert struct.unpack('<8H', save.game_image(state, 'B').get('walls'))[2:4] == (9, 1)
    state.g.update({'dkk.delay': 257, 'dkk.pictures': 127, 'dkk.animations': 1})
    state.dataset, state.x, state.y = 257, -1, -128
    image = save.game_image(state, 'B')
    assert image.get('disk') == image.get('zone1')[0x312] == 1
    assert image.get('zone0')[0xFC] == 1 and image.get('zone0')[0xFF] == 255
    assert image.get('position')[:2] == b'\xff\x80'
    with TemporaryDirectory(prefix='sm-dkk-options-') as folder:
        fresh = Game(None)
        fresh.roster_directory = Path(folder)
        fresh.s.party = [bare]
        assert (fresh.s.r0[0xFC], fresh.s.r0[0xFF]) == (0, 0)
        for options in (None, (0, 0, 0), (9, 0, 1), (2, 1, 0)):
            if options is not None:
                fresh.s.g['dkk.delay'], fresh.s.g['dkk.pictures'], fresh.s.g['dkk.animations'] = options
            save.save_game(fresh, 'A')
            loaded = Game(None)
            loaded.roster_directory = fresh.roster_directory
            snapshot = save.load_game(loaded, 'A')
            delay, pictures, animations = (4, 1, 1) if options is None else options
            zone = snapshot.game.get('zone0')
            assert (zone[0xFC], zone[0xFF]) == (delay, 2 * pictures + animations)
            assert (loaded.s.g['dkk.delay'], loaded.s.g['dkk.pictures'], loaded.s.g['dkk.animations']) == (delay, pictures, animations)
            fresh = loaded
    with TemporaryDirectory(prefix='sm-dkk-codec-') as folder:
        root = Path(folder)
        state.party = [None]
        record = Character(); record.set('name', b'\x04HERO' + bytes(11))
        one = save.Snapshot('B', save.game_image(state, 'B'), {'CHRDATB1': {'GAM': (record,), 'WIZ': (Spells(),), 'JNK': (Item(),), 'EFF': (Effect(),)}})
        save.write_snapshot(root, one)
        assert len(file_index(root)) == 5
        one.members['CHRDATB1'] = {'GAM': (record,)}
        save.write_snapshot(root, one)
        assert set(file_index(root)) == {'SAVGAMB.PTY', 'CHRDATB1.GAM'}
        (root / 'CHRDATB1.GAM').write_bytes(b'\x04HERO')
        loaded = save.load(root, 'b')
        assert loaded.members['CHRDATB1']['GAM'][0].get('name') == b'\x04HERO' + bytes(11)
        (root / 'CHRDATB1.GAM').unlink()
        assert not save.load(root, 'B').members
        from .records import SavedGame
        for kind, suffix, extension, raw_char in (
                (SavedGame, 'PTY', 'GAM', record),
                (ImportedGame, 'DAT', 'SAV', ImportedCharacter())):
            raw_char.set('class', 2)
            unusual = kind()
            raw_names = (b'a....b', b'abcdefghij', b'..H/E\\R:O..', b'H  ERO', b'', b'absent')
            stems = ('A.B', 'ABCDEFGH', 'HERO', 'H ERO', '')
            unusual.set('party_count', len(raw_names))
            unusual.set('party_names', b''.join((bytes([len(name)]) + name).ljust(41, b'\0')
                                               for name in raw_names).ljust(328, b'\0'))
            path = root / ('SAVGAME.' + suffix)
            path.write_bytes(bytes(unusual))
            for stem in stems: (root / (stem + '.' + extension)).write_bytes(bytes(raw_char))
            members = save.load(root, 'E').members if suffix == 'PTY' else save.load_imported(root, 'E')[1]
            assert tuple(members) == stems
            assert path.read_bytes() == bytes(unusual)
            unusual.set('party_count', 2)
            unusual.set('party_names', (b'\x03a.b' + bytes(37) + b'\x02ab' + bytes(38)).ljust(328, b'\0'))
            path.write_bytes(bytes(unusual))
            members = save.load(root, 'E').members if suffix == 'PTY' else save.load_imported(root, 'E')[1]
            assert not members
            (root / ('AB.' + extension)).write_bytes(bytes(raw_char))
            unique_char = type(raw_char)(bytes(raw_char))
            unique_char.set('age', 7)
            (root / ('HERO.' + extension)).write_bytes(bytes(unique_char))
            repeated = (b'a.b', b'absent', b'HERO', b'ab', b'AB')
            unusual.set('party_count', len(repeated))
            unusual.set('party_names', b''.join((bytes([len(name)]) + name).ljust(41, b'\0')
                                               for name in repeated).ljust(328, b'\0'))
            path.write_bytes(bytes(unusual))
            members = save.load(root, 'E').members if suffix == 'PTY' else save.load_imported(root, 'E')[1]
            assert tuple(members) == ('AB', 'HERO', 'AB', 'AB') and len(members) == 4
            ordered = tuple(members.values())
            assert len({id(files['GAM'][0]) for files in ordered}) == 4
            assert bytes(ordered[0]['GAM'][0]) == bytes(ordered[2]['GAM'][0])
            assert members['HERO'] is ordered[1]
            try:
                members['AB']
            except ValueError: pass
            else: raise AssertionError('Repeated member lookup selected an arbitrary occurrence')
            ordered[0]['GAM'][0].set('age', 39)
            assert ordered[2]['GAM'][0].get('age') == 0
            repeated_game = Game(None)
            repeated_game.roster_directory = root
            if suffix == 'PTY': save.load_game(repeated_game, 'E')
            else: save.load_imported_game(repeated_game, root, 'E')
            party = repeated_game.s.party
            assert len(party) == repeated_game.s.r1[0x33E] == 4
            assert [rules.record(char).get('order') for char in party] == list(range(4))
            assert [rules.record(char).get('age') for char in party] == [0, 7, 0, 0]
            assert len({id(char.b) for char in party}) == 4
            rules.record(party[0]).set('age', 39)
            assert rules.record(party[2]).get('age') == 0
            partial = Game(None)
            partial.roster_directory = root
            partial.s.mode = 4
            partial.vm.resuming = suffix == 'DAT'
            partial.vm.icons[0] = ('CPIC', 48, 5)
            unusual.set('party_names', unusual.get('party_names')[:123] + bytes([41]) + bytes(204))
            if suffix == 'PTY':
                unusual.set('disk', 5)
                unusual.set('mode', 2)
                zone = bytearray(1024)
                zone[0x312] = 3
                unusual.set('zone1', bytes(zone))
            path.write_bytes(bytes(unusual))
            sentinel = root / 'HERO.PC'
            sentinel.write_bytes(b'roster')
            raw_char.set('name', bytes([4]) + b'HERO' + bytes(11))
            (root / ('AB.' + extension)).write_bytes(bytes(raw_char))
            checked = []
            def search_load(directory):
                checked.append((directory, len(partial.s.party), partial.s.sel))
                return 5 if len(partial.s.party) == 2 else 0
            partial.save_filesystem = SimpleNamespace(save_path='C:/NATIVE/', champions_path='C:/CHAMPIONS/',
                    host_path=lambda directory: root, volume_label=lambda drive: '', search=search_load)
            pauses = []
            partial.ask = lambda kind, choices, **info: pauses.append((kind, info))
            if suffix == 'PTY':
                assert save.load_game(partial, 'E', root) is None
                assert (partial.s.mode, partial.s.dataset, partial.s.g['vault.letter']) == (2, 5, 'E')
                native_dir, message = 'C:/NATIVE', 'noSaveDirectoryMessage'
            else:
                assert save.load_imported_game(partial, root, 'E') is None
                assert partial.s.mode == 4
                native_dir, message = 'C:/CHAMPIONS', 'noChampionsDirectoryMessage'
            assert partial.vm.resuming == (suffix == 'PTY')
            assert checked == [(native_dir, 1, 0), (native_dir, 2, 1)]
            assert partial.s.r1[0x33E] == 2 and partial.s.sel == 1
            assert [rules.record(char).get('age') for char in partial.s.party] == [0, 7]
            assert pauses == [('ACK', dict(prompt=partial.assets.text(message), message_colour=14))]
            assert partial.vm.icons[0] == ('CPIC', 48, 5) and sentinel.read_bytes() == b'roster'
            changed_disk = Game(None)
            checks = []
            new_member = root / ('absent.' + extension)
            def removable_search(directory):
                checks.append((directory, len(changed_disk.s.party)))
                return 3 if len(checks) == 1 else 0
            def replace_disk(kind, choices, **info):
                assert kind == 'ACK' and info['prompt'] == changed_disk.assets.text('saveDirectoryName') + 'A:'
                new_member.write_bytes(bytes(unique_char))
            changed_disk.ask = replace_disk
            changed_disk.save_filesystem = SimpleNamespace(save_path='A:/NATIVE/', champions_path='A:/CHAMPIONS/',
                    host_path=lambda directory: root, volume_label=lambda drive: '', search=removable_search)
            unusual.set('party_count', 2)
            path.write_bytes(bytes(unusual))
            if suffix == 'PTY': swapped = save.load_game(changed_disk, 'E', root).members
            else: swapped = save.load_imported_game(changed_disk, root, 'E')[1]
            assert tuple(swapped) == ('AB', 'ABSENT')
            assert checks == [('A' + native_dir[1:], count) for count in (1, 1, 2)]
            assert [rules.record(char).get('age') for char in changed_disk.s.party] == [0, 7]
            assert changed_disk.s.sel == 0 and not sentinel.exists()
            new_member.unlink()
            repeated_game.s.g['save.file_format'] = 0
            rewritten = save.save_game(repeated_game, 'F')
            assert repeated_game.s.g['save.file_format'] == 1
            assert tuple(rewritten.members) == ('CHRDATF1', 'CHRDATF2', 'CHRDATF3', 'CHRDATF4')
            repeated_game.s.party.clear()
            save.load_game(repeated_game, 'F')
            assert [rules.record(char).get('age') for char in repeated_game.s.party] == [39, 7, 0, 0]
        old_game = ImportedGame()
        old_game.set('party_count', 2)
        names = b''.join((bytes([8]) + name).ljust(41, b'\0') for name in (b'CHRDATC1', b'CHRDATC2'))
        old_game.set('party_names', names.ljust(328, b'\0'))
        old_game.data[615:617] = bytes((2, 129))
        (root / 'SAVGAMC.DAT').write_bytes(bytes(old_game))
        old_char = ImportedCharacter(); old_char.set('class', 2); old_char.set('npc', 128)
        (root / 'CHRDATC1.SAV').write_bytes(bytes(old_char))
        funds, imported = save.load_imported(root, 'c')
        assert funds == 0x8102 and list(imported) == ['CHRDATC1']
        assert imported['CHRDATC1']['GAM'][0].get('npc') == 0
        imported_game = Game(None)
        imported_game.vm.resuming = True
        imported_game.s.r0[0x100] = 17
        imported_game.s.r1[0x379] = 29
        imported_game.s.r0[0xF2] = 16
        imported_game.s.x, imported_game.s.y = 2, 3
        imported_game.vm.icons[0] = ('CPIC', 48, 1)
        imported_game.s.r0[0xE6] = 0
        imported_game.vm.load_big(114)
        native_roster = root / 'native-roster'
        imported_game.roster_directory = native_roster
        save.load_imported_game(imported_game, root, 'C')
        assert not native_roster.exists() and len(imported_game.s.party) == 1
        assert imported_game.s.r0[0x133:0x135] == [2, 129]
        assert save_vault.load_vault(imported_game.s, native_roster) == (True, False)
        assert imported_game.s.treasure_money[4:7] == [0x8102 * 100, 0, 0]
        native_roster.write_bytes(b'occupied')
        second_import = Game(None)
        second_import.roster_directory = native_roster
        second_import.s.dataset = 4
        second_import.s.g['dkk.previous_disk'] = 2
        save.load_imported_game(second_import, root, 'C')
        assert native_roster.read_bytes() == b'occupied'
        assert len(second_import.s.party) == 1 and second_import.s.mode == 0
        assert second_import.s.dataset == second_import.s.g['dkk.previous_disk'] == 4
        assert not imported_game.vm.resuming and imported_game.s.mode == 0
        assert imported_game.s.g['dkk.runtime']['big_id'] == 114
        assert 0 not in imported_game.vm.icons
        assert (imported_game.s.x, imported_game.s.y, imported_game.s.r0[0xF2]) == (2, 3, 16)
        imported_game.vm.load_block(16)
        imported_game.vm.init_vm()
        assert not any(imported_game.s.r0[0x100:0x120]) and not any(imported_game.s.r1[0x379:0x383])
        game = Game(None)
        game.roster_directory = root
        game.age_pass = True
        save.apply_image(game.s, source.game)
        game.vm.load_wall(0, 0)
        assert struct.unpack('<8H', save.game_image(game.s, 'D').get('walls'))[:2] == (0, 0)
        game.vm.load_wall(65535, 0)
        assert struct.unpack('<8H', save.game_image(game.s, 'D').get('walls'))[:2] == (65535, 65535)
        save.apply_image(game.s, source.game)
        rules.restore(game.s, source)
        for char in game.s.party:
            name = bytes(char.b[1:1 + char.b[0]]).decode('cp437')
            from sm.titles.cok.creation import dos_stem
            (root / (dos_stem(name) + '.PC')).write_bytes(bytes(char.b[:216]))
        game.s.r0[0xC5] = 36
        snapshot = save.save_game(game, 'D')
        assert game.age_pass and game.s.g['save.recent'] == 1
        assert (root / 'VAULTD.DAT').is_file()
        assert not any(name.endswith('.PC') for name in file_index(root))
        for name, raw in snapshot.dump().items(): assert (root / name).read_bytes() == raw
        game.s.party.clear()
        game.s.g['save.recent'] = 0
        save.load_game(game, 'D')
        assert len(game.s.party) == 6 and game.s.r1[0x33E] == 6
        assert game.s.mode == 0 and game.s.prev_mode == snapshot.game.get('previous_mode')
        assert game.vm.resuming and game.s.g['vault.letter'] == 'D'
        assert game.geo.map is not None
        assert game.age_pass and game.s.g['save.recent'] == 0
        assert [rules.record(char).get('order') for char in game.s.party] == list(range(6))
        for char in game.s.party:
            assert rules.record(char).get('next_pointer') == 0
        from .ui import screen
        icons_game = Game(None)
        icons_game.roster_directory = root
        save.load_game(icons_game, 'D')
        for char, npc in zip(icons_game.s.party, (0, 127, 128, 255, 0, 0)):
            rules.record(char).set('npc', npc)
            rules.record(char).set('creature_id', 48)
        save.save_game(icons_game, 'H')
        party_file = root / 'SAVGAMH.PTY'
        image = SavedGame(party_file.read_bytes())
        image.set('disk', 5)
        party_file.write_bytes(bytes(image))
        icons_game = Game(None)
        icons_game.roster_directory = root
        icons_game.vm.icons.update({i: ('CPIC', 1, 5) for i in range(8)})
        save.load_game(icons_game, 'H')
        assert icons_game.s.g['dkk.previous_disk'] == 5 and icons_game.s.dataset == image.get('zone1')[0x312]
        assert icons_game.vm.icons == {2: ('CPIC', 48, 5),
                                      3: ('CPIC', 48, 5),
                                      6: ('CPIC', 1, 5), 7: ('CPIC', 1, 5)}
        assert icons_game.s.sel == 0 and icons_game.s.r1[0x33E] == 6
        icons_game.s.g['dkk.battle'] = {'actors': [{'facing': 0}] * 6}
        icon_assets = screen.Assets()
        for index in (2, 3):
            for pose in (0, 1):
                pixels, palette = icon_assets.combat_icon(icons_game, index, pose)
                assert pixels == icon_assets.combat_picture('CPIC1', 48 + 128 * pose)[0]
                assert palette == tuple(icon_assets.view_tables['icon_palette'])
        for char in icons_game.s.party: rules.record(char).set('npc', 128)
        icons_game.s.g['dkk.previous_disk'] = 2
        save.restore_icons(icons_game)
        assert icons_game.s.g['dkk.previous_disk'] == 2
        from types import SimpleNamespace
        for dungeon, block, slot, map_id in ((1, 0, 0, 36), (1, 32768, 0, 36),
                (1, 65535, 0, 36), (0, 1, 0, 36), (0, 65535, 0, 36), (1, 1, 0, 0),
                (1, 257, 258, 36), (1, 1, 255, 36), (255, 32767, 3, 36)):
            restored = Game(None)
            restored.roster_directory = root
            image = SavedGame()
            zone0, zone1 = bytearray(1024), bytearray(1024)
            zone0[0xE6], zone0[0xC5], zone1[0x312] = dungeon, map_id, 3
            image.set('zone0', zone0)
            image.set('zone1', zone1)
            image.set('disk', 1)
            image.set('previous_mode', 3)
            image.set('walls', struct.pack('<8H', block, slot, 65535, 65535, 65535, 65535, 65535, 65535))
            save.write_snapshot(root, save.Snapshot('G', image, {}))
            calls = []
            restored.geo = SimpleNamespace(load=lambda s, ident: calls.append((s.dataset, ident)))
            restored.vm.load_big(114)
            display = dict(restored.vm.display)
            save.load_game(restored, 'G')
            reload = bool(dungeon and 0 < block < 32768)
            assert calls == ([(3, map_id)] if reload else [])
            assert restored.s.g['dkk.runtime']['big_id'] == (112 if not dungeon else 255 if reload and (slot & 255) < 4 else 114)
            assert restored.vm.display == display
            assert restored.s.dataset == 3 and restored.s.mode == 0 and restored.s.prev_mode == 3
            expected = [(block, slot)] + [(65535, 65535)] * 3
            if reload and (slot & 255) < 4: expected[slot & 255] = (block & 255, slot & 255)
            assert restored.s.g['save.wall_pairs'] == tuple(expected)
        original = {name: path.read_bytes() for name, path in file_index(require_folder() / 'SAVE').items()}
        try: save.write_snapshot(require_folder() / 'SAVE', snapshot)
        except ValueError: pass
        else: raise AssertionError('original save folder was writable')
        assert all(path.read_bytes() == original[name] for name, path in file_index(require_folder() / 'SAVE').items())
