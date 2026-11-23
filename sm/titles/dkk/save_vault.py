from dataclasses import dataclass
from pathlib import Path
import struct
from sm.files import file_index
from .records import Item
from .save_chars import whole


def signed_pool(value):
    return (value + 0x80000000) % 0x100000000 - 0x80000000


@dataclass
class Vault:
    money: tuple
    items: tuple = ()
    has_money: bool = False
    has_items: bool = False

    def dump(self):
        return struct.pack('<3i', *(signed_pool(v) for v in self.money)) + b''.join(bytes(item) for item in self.items)


def decode(raw, funds=0, money=(0, 0, 0)):
    if raw is None:
        steel = (funds & 65535) * 100
        return Vault((steel, 0, 0), has_money=steel != 0)
    previous = struct.pack('<3i', *(signed_pool(v) for v in money))
    pool = struct.unpack('<3i', raw[:12] + previous[min(len(raw), 12):])
    items = whole(raw[12:], Item)
    return Vault(pool, items, False, bool(items))


def letter_name(letter):
    letter = str(letter).upper()
    if len(letter) != 1 or not 'A' <= letter <= 'Z': raise ValueError('Invalid vault letter')
    return 'VAULT' + letter + '.DAT'


def load_vault(state, directory):
    name = 'TMPVAULT.DAT' if state.g.get('vault.pending', 0) else letter_name(state.g.get('vault.letter', 'Q'))
    path = file_index(directory).get(name) if Path(directory).is_dir() else None
    funds = (state.r0[0x133] & 255) | (state.r0[0x134] & 255) << 8
    vault = decode(path.read_bytes() if path else None, funds, state.treasure_money[4:7])
    state.treasure_money[4:7] = vault.money
    state.treasure_items.extend(bytearray(bytes(item)) for item in vault.items)
    return vault.has_money, vault.has_items


def write_vault(state, directory, name='TMPVAULT.DAT', *, game=None):
    from .creation import save_directory
    from .save import free_space
    name = str(name).upper()
    if name != 'TMPVAULT.DAT' and (len(name) != 10 or name != letter_name(name[5])):
        raise ValueError('Invalid vault filename')
    folder = save_directory(directory)
    raw = Vault(tuple(state.treasure_money[4:7]), tuple(Item(bytes(item)) for item in state.treasure_items)).dump()
    path = file_index(folder).get(name, folder / name)
    path.unlink(missing_ok=True)
    if game is not None and (len(raw) & 65535) > free_space(game, folder):
        for message in ('noRoomMessage', 'insertDiskMessage'):
            game.ask('ACK', ('Continue',), prompt=game.assets.text(message), message_colour=14)
        path = file_index(folder).get(name, path)
    path.write_bytes(raw)
    state.g['vault.pending'] = 1


def save_vault(state, directory, slot, *, game=None):
    from .creation import save_directory
    from .save import valid_slot
    slot = valid_slot(slot)
    folder = save_directory(directory)
    index = file_index(folder)
    name = letter_name(slot)
    if state.g.get('vault.pending', 0):
        target = index.get(name, folder / name)
        target.unlink(missing_ok=True)
        temporary = index.get('TMPVAULT.DAT')
        if temporary is not None: temporary.rename(target)
    elif state.g.get('vault.letter', 'Q') != slot:
        load_vault(state, folder)
        write_vault(state, folder, name, game=game)
    state.g['vault.letter'], state.g['vault.pending'] = slot, 0


def test():
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace
    from unittest.mock import patch
    from sm.titles.ssb.state import State
    item = Item(); item.set('type', 8)
    vault = Vault((-1, 0x7fffffff, 0x80000000), (item,))
    decoded = decode(vault.dump() + b'x')
    assert decoded.money == (-1, 0x7fffffff, -0x80000000)
    assert not decoded.has_money and decoded.has_items and len(decoded.items) == 1
    assert decode(None, 65535).money == (6553500, 0, 0)
    assert decode(None, 65535).has_money and not decode(None).has_money
    assert decode(b'\x01', money=(-1, 2, 3)).money == (-255, 2, 3)
    with TemporaryDirectory(prefix='sm-dkk-vault-') as folder:
        root, state = Path(folder), State()
        state.r0[0x133:0x135] = [2, 1]
        assert load_vault(state, root) == (True, False)
        assert state.treasure_money[4:7] == [25800, 0, 0]
        state.treasure_items = [bytearray(bytes(item))]
        write_vault(state, root)
        assert state.g['vault.pending'] == 1
        (root / 'VAULTA.DAT').write_bytes(b'old')
        save_vault(state, root, 'a')
        assert not (root / 'TMPVAULT.DAT').exists()
        assert state.g['vault.letter'] == 'A' and state.g['vault.pending'] == 0
        expected = (root / 'VAULTA.DAT').read_bytes()
        state.treasure_items.clear()
        state.treasure_money[4:7] = [0, 0, 0]
        assert load_vault(state, root) == (False, True)
        assert state.treasure_money[4] == 25800
        state.treasure_items.clear()
        save_vault(state, root, 'B')
        assert (root / 'VAULTB.DAT').read_bytes() == expected
        state.treasure_money[4] = 999
        save_vault(state, root, 'B')
        assert (root / 'VAULTB.DAT').read_bytes() == expected
        state.g['vault.pending'] = 1
        save_vault(state, root, 'B')
        assert not (root / 'VAULTB.DAT').exists()
        target = root / 'tmpvault.dat'
        for count, available, prompts in ((0, 12, ()), (1, 74, ('noRoomMessage', 'insertDiskMessage')),
                                          (1041, 59, ()), (0, -1, ('noRoomMessage', 'insertDiskMessage'))):
            state.treasure_items = [bytes(item)] * count
            state.g['vault.pending'] = 0
            target.write_bytes(b'old')
            seen = []
            def capacity(drive):
                assert drive == 2 and not target.exists()
                return available
            def pause(kind, options, **info):
                assert not target.exists() and state.g['vault.pending'] == 0
                assert (kind, options, info['message_colour']) == ('ACK', ('Continue',), 14)
                seen.append(info['prompt'])
            device = SimpleNamespace(save_path='b:', disk_free=capacity)
            game = SimpleNamespace(save_filesystem=device, ask=pause, assets=SimpleNamespace(text=str))
            write_vault(state, root, game=game)
            assert tuple(seen) == prompts and state.g['vault.pending'] == 1
            assert len(target.read_bytes()) == 12 + Item.SIZE * count
        state.g['vault.pending'] = 0
        with patch.object(Path, 'write_bytes', side_effect=OSError('write failed')):
            try: write_vault(state, root, game=game)
            except OSError: pass
            else: raise AssertionError('Vault write failure lost')
        assert not target.exists() and state.g['vault.pending'] == 0
