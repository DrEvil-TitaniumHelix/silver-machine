from dataclasses import dataclass
import struct

from sm.files import file_index
from .records import Character, Item, Effect, SavedGame, split_records


def member_stems(game):
    count = game.get('party_count')
    if count > 8:
        raise ValueError('Champions save contains more than eight members')
    slots = game.get('party_names')
    result = []
    for i in range(count):
        slot = slots[41 * i:41 * (i + 1)]
        if not 1 <= slot[0] <= 40:
            raise ValueError('invalid member filename length')
        stem = slot[1:1 + slot[0]].decode('latin1')
        if stem in ('.', '..') or any(ch in stem for ch in '/\\:\0'):
            raise ValueError('unsafe member filename')
        if stem.upper() in {name.upper() for name in result}:
            raise ValueError('duplicate member filename')
        result.append(stem)
    return tuple(result)


@dataclass
class Snapshot:
    slot: str
    game: SavedGame
    members: dict

    def dump(self):
        stems = member_stems(self.game)
        if tuple(self.members) != stems:
            raise ValueError('save roster and member records disagree')
        output = {'SAVGAM' + self.slot + '.DAT': bytes(self.game)}
        for stem, files in self.members.items():
            for extension, records in files.items():
                output[stem + '.' + extension] = b''.join(bytes(record) for record in records)
        return output


def whole(raw, record_type):
    return split_records(raw[:len(raw) - len(raw) % record_type.SIZE], record_type)


def load(directory, slot='A'):
    slot = str(slot).upper()
    if len(slot) != 1 or slot not in 'ABCDEFGHIJ':
        raise ValueError('Champions native save slot must be A through J')
    index = file_index(directory)
    game = SavedGame(index['SAVGAM' + slot + '.DAT'].read_bytes())
    members = {}
    for stem in member_stems(game):
        if (stem + '.SAV').upper() not in index: continue
        members[stem] = {'SAV': (Character(index[(stem + '.SAV').upper()].read_bytes().ljust(Character.SIZE, bytes(1))[:Character.SIZE]),)}
        for extension, record_type in (('STF', Item), ('SFX', Effect)):
            path = index.get((stem + '.' + extension).upper())
            if path is not None:
                members[stem][extension] = whole(path.read_bytes(), record_type)
    return Snapshot(slot, game, members)


PARTY_NAME_SLOTS, PARTY_NAME_WIDTH = 8, 41
DISK_CELL, BLOCK_CELL = 0x312, 0xF2


def member_names(slot, count):
    return ['CHRDAT%s%d' % (slot, number + 1) for number in range(count)]


def _signed(value):
    return value - 256 if value > 127 else value


def game_image(state, slot):
    names = member_names(slot, len(state.party))
    game = SavedGame()
    game.set('disk', state.dataset & 255)
    game.set('zone0', struct.pack('<1024H', *(v & 0xFFFF for v in state.r0)))
    game.set('zone1', struct.pack('<1024H', *(v & 0xFFFF for v in state.r1)))
    game.set('zone2', struct.pack('<512H', *(v & 0xFFFF for v in state.r2)))
    game.set('position', bytes(v & 255 for v in (state.x, state.y, state.dir, state.ahead, state.attr)))
    game.set('previous_mode', state.prev_mode & 255)
    game.set('mode', state.mode & 255)
    game.set('walls', b''.join(struct.pack('<2H', wall & 0xFFFF, 0xFFFF if wall == 0xFFFF else row + 1) for row, wall in enumerate(state.walls)))
    game.set('party_count', len(names))
    game.set('party_names', b''.join(bytes([len(n)]) + n.encode('ascii') + bytes(PARTY_NAME_WIDTH - 1 - len(n)) for n in names).ljust(PARTY_NAME_SLOTS * PARTY_NAME_WIDTH, bytes(1)))
    return game


def apply_image(state, game):
    state.r0, state.r1 = list(struct.unpack('<1024H', game.get('zone0'))), list(struct.unpack('<1024H', game.get('zone1')))
    state.r2 = list(struct.unpack('<512H', game.get('zone2')))
    x, y, state.dir, state.ahead, state.attr = game.get('position')
    state.x, state.y = _signed(x), _signed(y)
    state.prev_mode, state.mode = game.get('previous_mode'), game.get('mode')
    state.walls = list(struct.unpack('<6H', game.get('walls'))[::2])
    state.dataset, state.block = state.r1[DISK_CELL] & 255, state.r0[BLOCK_CELL]
