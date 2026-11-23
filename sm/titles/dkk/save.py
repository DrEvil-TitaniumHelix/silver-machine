from dataclasses import dataclass
import struct
from sm.files import file_index
from sm.titles.cok.save import member_stems, member_names
from .records import Character, Item, Effect, Spells, SavedGame, split_records
from .save_chars import iter_party_stems, party_stems, read_native, read_imported

SIDEcars = (('GAM', Character), ('WIZ', Spells), ('JNK', Item), ('EFF', Effect))


def valid_slot(slot):
    slot = str(slot).upper()
    if len(slot) != 1 or slot not in 'ABCDEFGHIJ':
        raise ValueError('Death Knights save slot must be A through J')
    return slot


def check_directory(game):
    from pathlib import Path
    from .faults import BindingRequired
    from .intake import require_folder
    filesystem = getattr(game, 'save_filesystem', None)
    if filesystem is None:
        raise BindingRequired('save.check_directory requires DOS search, creation, volume label and path bindings')
    if 'save.file_format' not in game.s.g:
        raise BindingRequired('Save directory format has not been selected')
    selected = game.s.g['save.file_format']
    native = filesystem.save_path if selected == 1 else filesystem.champions_path
    if not native: raise BindingRequired('Empty save path has an unspecified drive character')
    directory = native[:-1]
    folder = Path(filesystem.host_path(directory))
    if folder.resolve().is_relative_to(require_folder().resolve()):
        raise ValueError('Death Knights originals are read-only; use a separate save directory')
    drive = native[0]
    def pause(name, suffix=''):
        game.ask('ACK', ('Continue',), prompt=game.assets.text(name) + suffix,
                 message_colour=14)
    while filesystem.volume_label(drive) == 'CHAMP' and drive < 'C':
        pause('saveDirectoryName', drive + ':')
    while True:
        error = filesystem.search(directory)
        if error == 0: return folder
        if error in (2, 18):
            if drive.upper() < 'C':
                prefix = 'askSaveDiskPrefix' if selected == 1 else 'askChampionsDiskPrefix'
                prompt = game.assets.text(prefix) + drive + game.assets.text('askDiskSuffix')
                if game.ask('CONFIRM', tuple(game.assets.text('yesNoOptions').split()),
                            prompt=prompt, start=0) != 0:
                    pause('saveDirectoryName', drive + ':')
            if filesystem.mkdir(directory) in (0, 5): return folder
        elif drive.upper() < 'C':
            pause('saveDirectoryName', drive + ':')
            if error == 5: return folder
        else:
            pause('noChampionsDirectoryMessage' if selected == 0 else 'noSaveDirectoryMessage')
            return None


@dataclass
class MemberFiles:
    entries: tuple

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return (stem for stem, files in self.entries)

    def __getitem__(self, stem):
        found = [files for name, files in self.entries if name == stem]
        if not found: raise KeyError(stem)
        if len(found) != 1: raise ValueError('Repeated member filename requires ordered access')
        return found[0]

    def items(self):
        return iter(self.entries)

    def values(self):
        return (files for stem, files in self.entries)


@dataclass
class Snapshot:
    slot: str
    game: SavedGame
    members: dict | MemberFiles

    def dump(self):
        if tuple(self.members) != member_stems(self.game):
            raise ValueError('save roster and member files disagree')
        output = {'SAVGAM' + valid_slot(self.slot) + '.PTY': bytes(self.game)}
        for stem, files in self.members.items():
            for suffix, records in files.items():
                output[stem + '.' + suffix] = b''.join(bytes(r) for r in records)
        return output


def read_members(directory, source, *, imported=False, game=None):
    members = []
    reader = read_imported if imported else read_native
    index = None
    if game is not None:
        game.s.r1[0x33E] = 0
    stems = party_stems(source) if game is None else iter_party_stems(source)
    for stem in stems:
        if index is None: index = file_index(directory)
        files = reader(index, stem)
        if files is None: continue
        if not imported or files['GAM'][0].get('npc') < 128:
            members.append((stem, files))
            if game is not None:
                restore_member(game, files)
        if game is not None:
            directory = load_directory(game, directory)
            if directory is None: return None
            index = None
    return MemberFiles(tuple(members))


def read_party_file(directory, slot, *, imported=False):
    from sm.titles.cok.records import SavedGame as ImportedGame
    from .faults import BindingRequired
    suffix = '.DAT' if imported else '.PTY'
    raw = file_index(directory)['SAVGAM' + valid_slot(slot) + suffix].read_bytes()
    if not imported: return SavedGame(raw)
    if len(raw) < 5469: raise BindingRequired('Short imported party file has unspecified unread fields')
    return ImportedGame(raw[:5469])


def load(directory, slot='A'):
    slot = valid_slot(slot)
    source = read_party_file(directory, slot)
    return Snapshot(slot, source, read_members(directory, source))


def apply_saved_options(state, game):
    zone = game.get('zone0')
    state.r0[0xFC], state.r0[0xFF] = zone[0xFC], zone[0xFF]
    state.r1[0x312] = game.get('disk')


def save_roster(state):
    return state.party if state.mode == 5 else state.chars()


def game_image(state, slot, *, update_zones=True):
    slot = valid_slot(slot)
    game = SavedGame()
    zone0 = bytearray(v & 255 for v in state.r0)
    zone1 = bytearray(v & 255 for v in state.r1)
    zone0[0xFC] = state.g.get('dkk.delay', 4) & 255
    pictures = state.g.get('dkk.pictures', 1)
    animations = state.g.get('dkk.animations', 1)
    zone0[0xFF] = (pictures * 2 + animations) & 255
    zone1[0x312] = state.dataset & 255
    game.set('disk', state.dataset & 255)
    game.set('zone0', bytes(zone0))
    game.set('zone1', bytes(zone1))
    game.set('zone2', bytes(v & 255 for v in state.r2))
    game.set('position', bytes(v & 255 for v in (state.x, state.y, state.dir, state.ahead, state.attr)))
    game.set('previous_mode', state.prev_mode & 255)
    game.set('mode', state.mode & 255)
    previous = state.g.get('save.wall_pairs', ())
    pairs = []
    for i, wall in enumerate(state.walls):
        wall &= 65535
        filed = previous[i] if i < len(previous) else None
        slot_id = filed[1] if filed and filed[0] == wall else 65535 if wall == 65535 else 1 if i == wall == 0 else i
        pairs.extend((wall, slot_id & 65535))
    game.set('walls', struct.pack('<8H', *pairs))
    names = member_names(slot, len(save_roster(state)))
    game.set('party_count', len(names))
    game.set('party_names', b''.join((bytes([len(n)]) + n.encode('ascii')).ljust(41, b'\0') for n in names).ljust(328, b'\0'))
    if update_zones: apply_saved_options(state, game)
    return game


def apply_image(state, game):
    for attr, name in (('r0', 'zone0'), ('r1', 'zone1'), ('r2', 'zone2')):
        setattr(state, attr, list(game.get(name)))
    x, y, state.dir, state.ahead, state.attr = game.get('position')
    state.x, state.y = (v - 256 if v > 127 else v for v in (x, y))
    state.mode, state.prev_mode = game.get('mode'), game.get('previous_mode')
    state.walls = list(struct.unpack('<8H', game.get('walls'))[::2])
    pairs = struct.unpack('<8H', game.get('walls'))
    state.g['save.wall_pairs'] = tuple(zip(pairs[::2], pairs[1::2]))
    state.g['dkk.pictures'], state.g['dkk.animations'] = state.r0[0xFF] // 2, state.r0[0xFF] & 1
    state.g['dkk.delay'] = state.r0[0xFC]
    state.dataset, state.block = state.r1[0x312], state.r0[0xF2]


def load_imported(directory, slot='A'):
    source = read_party_file(directory, slot, imported=True)
    return int.from_bytes(source.data[615:617], 'little'), read_members(directory, source, imported=True)


def write_snapshot(directory, snapshot, *, roster=None):
    from .creation import save_directory
    output = snapshot.dump()
    allowed = {suffix for suffix, _ in SIDEcars}
    for stem, files in snapshot.members.items():
        if not set(files) <= allowed: raise ValueError('Unexpected character sidecar')
    if roster is not None and len(roster) != len(snapshot.members):
        raise ValueError('Save roster and snapshot have different sizes')
    folder = save_directory(directory)
    index = file_index(folder)
    party_file = 'SAVGAM' + valid_slot(snapshot.slot) + '.PTY'
    index.get(party_file, folder / party_file).write_bytes(output[party_file])
    write_member_files(folder, index, snapshot.members, output, roster)


def write_member_files(folder, index, members, output, roster, *, game=None):
    for position, stem in enumerate(members):
        if game is not None:
            destination = admit_character(game, roster[position])
            if destination is None:
                try: index = file_index(folder)
                except OSError: index = {}
                writable = False
            else:
                folder = destination
                index, writable = member_destination(game, folder, stem + '.GAM')
            if not writable:
                forget_character(index, roster[position])
                continue
        for suffix, _ in SIDEcars:
            name = stem + '.' + suffix
            key = name.upper()
            if name in output:
                index.setdefault(key, folder / name).write_bytes(output[name])
            elif suffix != 'GAM' and key in index:
                index.pop(key).unlink(missing_ok=True)
        if roster is not None:
            forget_character(index, roster[position])
    return folder


def forget_character(index, char):
    from sm.titles.cok.creation import dos_stem
    stem = dos_stem(bytes(char.b[1:1 + char.b[0]]).decode('cp437'))
    for suffix in ('PC', 'WIZ', 'JNK', 'EFF'):
        path = index.pop(stem + '.' + suffix, None)
        if path is not None: path.unlink(missing_ok=True)


def forget_roster(directory, party):
    from .creation import save_directory
    folder = save_directory(directory, create=False)
    try:
        index = file_index(folder)
    except OSError:
        return
    for char in party:
        forget_character(index, char)


def party_size(party):
    from .rules import spellbook
    return sum(Character.SIZE + (Spells.SIZE if spellbook(char) is not None else 0) +
               Item.SIZE * len(char.items) + Effect.SIZE * len(char.effects)
               for char in party) & 65535


def space_required(party, slot_exists):
    return (party_size(party) + (0 if slot_exists else 2568)) & 65535


def free_space(game, folder):
    from shutil import disk_usage
    from .faults import BindingRequired
    filesystem = getattr(game, 'save_filesystem', None)
    if filesystem is not None:
        if not callable(getattr(filesystem, 'disk_free', None)):
            raise BindingRequired('Save requires a native disk-free binding')
        return filesystem.disk_free(ord(filesystem.save_path[0].upper()) - 64)
    try:
        return disk_usage(folder).free
    except OSError:
        return -1


def admit_save(game, slot):
    from .creation import save_directory
    from .faults import BindingRequired
    slot = valid_slot(slot)
    game.s.g['save.file_format'] = 1
    filesystem = getattr(game, 'save_filesystem', None)
    if filesystem is None:
        try:
            folder = save_directory(getattr(game, 'roster_directory', None))
            exists = 'SAVGAM' + slot + '.PTY' in file_index(folder)
        except OSError:
            game.ask('ACK', ('Continue',), prompt=game.assets.text('noSaveDirectoryMessage'), message_colour=14)
            return None
    else:
        folder = check_directory(game)
        if folder is None: return None
        if not callable(getattr(filesystem, 'exists', None)) or not callable(getattr(filesystem, 'disk_free', None)):
            raise BindingRequired('save.admit_save requires native file existence and signed disk-free bindings')
        native = filesystem.save_path
        exists = filesystem.exists(native + game.assets.text('saveGameStem') + slot + '.pty')
    if space_required(save_roster(game.s), exists) <= free_space(game, folder): return folder
    game.ask('ACK', ('Continue',), prompt=game.assets.text('diskFullMessage'), message_colour=14)
    return None


def retry_save_open(game):
    filesystem = getattr(game, 'save_filesystem', None)
    drive = filesystem.save_path[0] if filesystem is not None else None
    if drive is None or drive.upper() >= 'C':
        game.ask('ACK', ('Continue',), prompt=game.assets.text('noSaveDirectoryMessage'), message_colour=14)
        return False
    game.ask('ACK', ('Continue',), prompt=game.assets.text('saveDirectoryName') + drive + ':', message_colour=14)
    return True


def admit_character(game, char):
    from .creation import save_directory
    game.s.g['save.file_format'] = 1
    while True:
        if getattr(game, 'save_filesystem', None) is None:
            try: folder = save_directory(getattr(game, 'roster_directory', None))
            except OSError:
                game.ask('ACK', ('Continue',), prompt=game.assets.text('noSaveDirectoryMessage'), message_colour=14)
                return None
        else:
            folder = check_directory(game)
            if folder is None: return None
        required = (Character.SIZE + Item.SIZE * len(char.items) + Effect.SIZE * len(char.effects)) & 65535
        if required <= free_space(game, folder): return folder
        game.ask('ACK', ('Continue',), prompt=game.assets.text('diskFullMessage'), message_colour=14)
        prompt = game.assets.text('loseCharacterPrompt')
        choices = tuple(game.assets.text('tryAnotherDiskMenu').split(' ', 1))
        if game.ask('MENU', choices + ('escape',), prompt=prompt, query=prompt, start=0) == 0:
            return folder


def member_destination(game, folder, name):
    while True:
        index = {}
        try:
            index = file_index(folder)
            path = index.get(name, folder / name)
            try:
                with path.open('r+b'):
                    pass
            except FileNotFoundError:
                pass
            return index, True
        except OSError:
            if not retry_save_open(game): return index, False


def open_party_file(game, folder, name):
    while True:
        try:
            index = file_index(folder)
            return index, index.get(name, folder / name).open('wb')
        except OSError:
            if not retry_save_open(game): return None


def save_game(game, slot):
    from . import rules
    from .save_vault import save_vault
    slot = valid_slot(slot)
    state = game.s
    folder = admit_save(game, slot)
    if folder is None: return None
    roster = save_roster(state)
    members = {}
    for stem, char in zip(member_names(slot, len(roster)), roster):
        members[stem] = {suffix: split_records(raw, kind) for (suffix, kind), raw in
                         zip(SIDEcars, rules.write_character(char)) if raw}
    snapshot = Snapshot(slot, game_image(state, slot, update_zones=False), members)
    output = snapshot.dump()
    name = 'SAVGAM' + slot + '.PTY'
    opened = open_party_file(game, folder, name)
    if opened is None: return None
    index, stream = opened
    with stream:
        apply_saved_options(state, snapshot.game)
        stream.write(output[name])
    folder = write_member_files(folder, index, members, output, roster, game=game)
    save_vault(state, folder, slot, game=game)
    state.g['save.recent'] = 1
    return snapshot


def append_character(game, char):
    from . import rules
    state = game.s
    record = rules.record(char)
    record.set('order', 255)
    linked = state.monsters if state.monsters else state.party
    linked.append(char)
    characters = state.chars()
    state.sel = len(characters) - 1
    used = {rules.record(member).get('order') for member in characters}
    record.set('order', next((i for i in range(8) if i not in used), 8))
    state.r1[0x33E] = state.r1[0x33E] + 1 & 255
    if record.get('npc') > 127: rules.recalc_class_stats(char)


def restore_member(game, files):
    from . import rules, effects
    from .save_chars import materialize
    char = materialize(files, game)
    slots = rules.recalc_stats(char, game.s.r1[0x372])
    effects.recalc_ability(game, char, 0)
    rules.recalc_class_stats(char, slots)
    append_character(game, char)


def restore_party(game, members):
    game.s.r1[0x33E] = 0
    for files in members.values():
        restore_member(game, files)
    game.s.sel = 0


def restore_dungeon(game):
    state = game.s
    block, slot = state.g['save.wall_pairs'][0]
    if not game.vm.is3d() or not 0 < block < 32768: return
    game.geo.load(state, state.r0[0xC5])
    slot &= 255
    if slot < 4: game.vm.load_wall(block & 255, slot)


def restore_icons(game):
    from . import rules
    for char in game.s.chars():
        record = rules.record(char)
        order = record.get('order')
        if record.get('npc') > 127:
            game.vm.icons[order] = ('CPIC', record.get('creature_id'), game.s.dataset)
        else:
            game.s.g['dkk.previous_disk'] = game.s.dataset
            game.vm.icons.pop(order, None)


def load_directory(game, directory=None):
    from os import scandir
    from .creation import save_directory
    from sm.titles.cok.creation import save_directory as champions_directory
    if getattr(game, 'save_filesystem', None) is not None:
        return check_directory(game)
    native = game.s.g['save.file_format'] == 1
    try:
        if native:
            folder = save_directory(directory if directory is not None else getattr(game, 'roster_directory', None))
        else:
            folder = champions_directory(directory if directory is not None else getattr(game, 'champions_directory', None))
        with scandir(folder):
            return folder
    except OSError:
        message = 'noSaveDirectoryMessage' if native else 'noChampionsDirectoryMessage'
        game.ask('ACK', ('Continue',), prompt=game.assets.text(message), message_colour=14)
        return None


def finish_load_party(game, roster):
    filesystem = getattr(game, 'save_filesystem', None)
    if filesystem is not None:
        roster = filesystem.host_path(filesystem.save_path[:-1])
    forget_roster(roster, game.s.chars())
    restore_icons(game)
    game.s.sel = 0


def load_game(game, slot, directory=None):
    slot = valid_slot(slot)
    game.s.g['save.file_format'] = 1
    folder = load_directory(game) if directory is None else directory
    if folder is None: return None
    source = read_party_file(folder, slot)
    game.vm.resuming = True
    game.s.g['vault.letter'] = slot
    apply_image(game.s, source)
    game.s.dataset = source.get('disk')
    members = read_members(folder, source, game=game)
    if members is None: return None
    finish_load_party(game, folder)
    game.s.dataset = game.s.r1[0x312]
    if game.vm.is3d(): restore_dungeon(game)
    else: game.vm.load_big(112)
    game.s.mode = 0
    return Snapshot(slot, source, members)


def load_imported_game(game, directory, slot='A'):
    state = game.s
    state.g['save.file_format'] = 0
    source = read_party_file(directory, slot, imported=True)
    funds = int.from_bytes(source.data[615:617], 'little')
    game.vm.resuming = False
    state.r0[0x133:0x135] = list(source.data[615:617])
    state.g['dkk.pictures'], state.g['dkk.animations'] = state.r0[0xFF] // 2, state.r0[0xFF] & 1
    state.g['dkk.delay'] = state.r0[0xFC]
    members = read_members(directory, source, imported=True, game=game)
    if members is None: return None
    finish_load_party(game, getattr(game, 'roster_directory', None))
    state.mode = 0
    return funds, members


def test():
    from .intake import require_folder
    from sm.titles.cok.check import record_check
    folder = require_folder() / 'SAVE'
    snapshot = load(folder)
    assert len(snapshot.members) == 6
    record_check(snapshot.game)
    for files in snapshot.members.values():
        for records in files.values():
            for record in records:
                record_check(record)
    original = file_index(folder)
    for name, raw in snapshot.dump().items():
        assert original[name.upper()].read_bytes() == raw
    from . import save_chars, save_vault, save_checks, save_start
    save_chars.test()
    save_vault.test()
    save_checks.test()
    save_start.test()
