from sm.titles.ssb import data as ssb_data
from functools import lru_cache
from collections import deque
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib
import os
import struct
import textwrap
import time
import zlib
from zipfile import BadZipFile, ZipFile

from sm import dax; from sm.titles.ssb import rec; from sm.titles.ssb import save; from sm import ecl
from sm.engine import Session
from sm.titles import ssb
from sm.titles.ssb.units import magic, shops
from sm.titles.ssb.units.combat import footprint
from sm.titles.ssb import art; from sm.titles.ssb.ui import view3d
from sm.titles.ssb.ui import plus

WIDTH, HEIGHT, SCALE = 320, 200, 3
LOCAL = Path(__file__).resolve().parents[4] / 'local'
PALETTE = tuple((r, g, b) for r, g, b in (
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)))



MEASURED_HOLD_MS = {30: 31.9, 50: 51.0, 70: 70.7, 400: 405.0}


def measured_hold(seconds):
    return MEASURED_HOLD_MS.get(round(seconds * 1000), seconds * 1000) / 1000


GAP_MS = {
    ('swing', 'spell', 'step', 'redraw'): 283.7,
    ('swing', 'spell', 'redraw', ''): 283.7,
    ('step', '', 'step', ''): 4.9,
    ('step', '', 'erase', ''): 4.9,
    ('flash', '', 'flash', ''): 4.4,
    ('flash', '', 'restore', ''): 4.4,
    ('death', '', 'death', ''): 6.7,
    ('restore', '', 'message', ''): 12.2,
    ('restore', '', 'death', ''): 12.2,
    ('death', 'hold', 'clear', 'redraw'): 52.2,
    ('erase', '', 'message', ''): 16.7,
    ('erase', '', 'flash', ''): 16.7,
    ('clear', '', 'step', 'redraw'): 300.4,
    ('clear', '', 'step', 'recenter'): 133.5,
    ('erase', '', 'step', 'redraw'): 250.3,
}
SAMPLE_MS = 1000 / 59.93


def gap_ms(event, queue):
    merged, nxt = [], None
    for e in queue:
        if e.get('merge'): merged.append(e)
        else: nxt = e; break
    redraws = [e for e in merged if e['kind'] == 'redraw']
    path = 'recenter' if any(e.get('recenter') for e in redraws) else 'redraw' if redraws else ''
    kind = lambda e: 'step' if e and e['kind'] in ('missile', 'bolt') else e['kind'] if e else None
    tag = 'spell' if event['kind'] == 'swing' and event.get('spell') else 'hold' if event['kind'] == 'death' and event.get('delay', 0) >= .1 else ''
    return GAP_MS.get((kind(event), tag, kind(nxt), path), 0.0)
@lru_cache(maxsize=128)
def party_icon(head, body, size, colours, pose=0):
    ds = ssb_data.stexe()
    shift = (64 if ds[0x9D7 + size] == ord('T') else 0) + pose * 128
    head_pixels = art.picture('CHEAD', (head + shift) & 255)[2][0]
    body_pixels = art.picture('CBODY', (body + shift) & 255)[2][0]
    palette = list(range(16))
    for i, colour in enumerate(colours, 1):
        base = ds[0x4CAF + i]
        palette[base], palette[base + 8] = colour & 15, colour >> 4
    ega = dict(zip(ds[0x19A4:0x19B4], ds[0x19B4:0x19C4]))
    palette = [palette[ega.get(value, value)] for value in range(16)]
    pixels = tuple(bytes(value | (head_pixels[y][x] if y < len(head_pixels) else 0)
                         for x, value in enumerate(row)) for y, row in enumerate(body_pixels))
    return pixels, tuple(palette)


def icon(game, character, facing=0, pose=0, *, controller=None):
    b = character.b
    source = getattr(game.vm, 'icons', {}).get(b[0x155])
    if source is not None:
        family, rid, dataset = source
        pixels = art.picture(family, (rid + pose * 128) & 255, dataset)[2][0]
        ds = ssb_data.stexe()
        palette = list(range(16))
        if family not in ('COMSPR', 'ICON'):
            for old, new in zip(ds[0x19A4:0x19B4], ds[0x19B4:0x19C4]):
                palette[old] = new
    else:
        body = plus.body(character, controller.manual_bodies) if getattr(controller, 'equipment_icon', False) else b[0x154]
        pixels, palette = party_icon(b[0x153], body, b[0x156], tuple(b[0x157:0x15D]), pose)
    pixels = tuple(row[::-1] for row in pixels) if facing > 3 else pixels
    return pixels, palette


def actor_index(game, decision):
    info = decision['info'] if decision else {}
    order = game.s.g.get('combat.order', ())
    cursor = game.s.g.get('combat.cursor', 0)
    current = order[cursor] if 0 <= cursor < len(order) else game.s.sel
    return info.get('actor', info.get('caster', current))


def target_position(game, value):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return tuple(value)
    positions = game.s.g.get('combat.positions', ())
    if isinstance(value, int) and 0 <= value < len(positions):
        return tuple(positions[value][:2])
    return None


def viewport(game, decision, selected=0):
    position = target_position(game, actor_index(game, decision)) or (3, 3)
    if decision and decision['kind'] == 'TARGET' and decision['options']:
        position = target_position(game, decision['options'][selected]) or position
    return max(0, min(43, position[0] - 3)), max(0, min(18, position[1] - 3))


def draw_battle(frame, controller, assets):
    game, decision = controller.session.game, controller.session.decision
    state = game.s
    x0, y0 = player_viewport(controller)
    tiles = art.picture('DUNGCOM', 1)[2]
    ds, terrain = ssb_data.stexe(), state.g['combat.tiles']
    clip = (8, 8, 176, 176)
    for row in range(7):
        for col in range(7):
            tile = terrain[(y0 + row) * 50 + x0 + col]
            number = ds[0x1AA1 + 4 * tile]
            if number < len(tiles):
                frame.blit(8 + col * 24, 8 + row * 24, tiles[number], clip=clip)
    positions, records = state.g['combat.positions'], state.g['combat.records']
    chars = state.chars()
    actor = actor_index(game, decision)
    event = getattr(controller, 'presentation_event', None) or {}
    if decision and (decision['kind'] == 'TARGET' or decision['info'].get('action') == 'attack-ally'):
        position = cursor(controller)
    else:
        position = target_position(game, actor)
    if 'cursor_cell' in event: position = event['cursor_cell'][:2] if event['cursor_cell'] else None
    if (position and decision and decision['info'].get('action') != 'continue-battle'
            and decision['info'].get('cursor', True)
            and (not event or event.get('cursor') or event.get('cursor_cell'))):
        size = positions[actor][2] if 0 <= actor < len(chars) and tuple(positions[actor][:2]) == tuple(position) else 1
        if event.get('cursor_cell'): size = event['cursor_cell'][2]
        for dx, dy in footprint(size or 1):
            frame.blit(8 + (position[0] + dx - x0) * 24, 8 + (position[1] + dy - y0) * 24,
                       art.picture('COMSPR', 0x19)[2][0], transparent=0, clip=clip)
    if hasattr(frame, 'begin_icons'): frame.begin_icons()
    for i, character in enumerate(chars):
        x, y, size = positions[i]
        if not size or not character.b[0x1A7]:
            continue
        event = getattr(controller, 'presentation_event', None) or {}
        pose = event.get('poses', {}).get(i, 0)
        facing = event.get('facing', records[i][9]) if i == event.get('actor') else records[i][9]
        pixels, palette = icon(game, character, facing, pose, controller=controller)
        if hasattr(frame, 'draw_icon'):
            frame.draw_icon(controller, game, character, i, facing, pose,
                            8 + (x-x0)*24, 8 + (y-y0)*24, pixels, palette, clip)
        else:
            frame.blit(8 + (x - x0) * 24, 8 + (y - y0) * 24,
                       pixels, transparent=0, colours=palette, clip=clip)
    frame.text(23, 1, 'Round %d' % (state.g.get('8DC7', 0) + 1), assets, 15, 16)
    if 0 <= actor < len(chars):
        b = chars[actor].b
        name = bytes(b[1:1 + b[0]]).decode('latin1')
        frame.text(23, 3, name, assets, 15, 16)
        for row, label in enumerate(('HP %d/%d' % (b[0x1B5], b[0x70]), 'AC %d' % (60 - b[0x1AB]),
                                     'Move %d' % records[actor][6]), 5):
            frame.text(23, row, label, assets, 10, 16)
    return x0, y0


PAGE_SIZE = 10
EXITS = ('exit', 'cancel', 'done')


def pstring(data, offset=0, maximum=255):
    return bytes(data[offset + 1:offset + 1 + min(data[offset], maximum)]).decode('latin1')


def item_name(item, party=()):
    b, ds = item, ssb_data.stexe()
    count, kind, shown = b[0x39], b[0x2E], 0
    result = '*' if any(e[0] == 5 for c in party for e in c.effects) and (
        rec.sx(b[0x32]) > 0 or rec.sx(b[0x33]) > 0 or b[0x36]) else ''
    if count and kind != 0x49:
        result += '%d ' % count
    for k in range(1, 4):
        if b[0x2E + k] and not (b[0x35] >> (3 - k)) & 1:
            shown |= 1 << (k - 1)
    plural = False
    for k in range(3, 0, -1):
        if not shown & (1 << (k - 1)):
            continue
        result += str(count) if kind == 0x49 and k == 2 else pstring(ds, 0xF0D + 21 * b[0x2E + k], 20)
        if count >= 2 and not plural and ((1 << (k - 1)) == shown or (k == 1 and (shown > 4 or kind == 0x49))
                or (k == 2 and not shown & 1) or (k == 3 and kind in (0x1E, 5, 0xC) and b[0x31] != 0x5D)):
            result += 's'
            plural = True
        result += ' '
    return (result.strip() or pstring(b, maximum=40) or 'Item')[:40]


def decision_labels(game, decision):
    kind, info = decision['kind'], decision['info']
    state = game.s
    who = info.get('actor', info.get('caster', state.sel))
    chars = state.chars()
    character = chars[who] if 0 <= who < len(chars) else None
    result = []
    for value in decision['options'] or ():
        label = 'Exit' if value is None else str(value)
        purpose = info.get('purpose', '')
        if kind == 'MOVE':
            label = {'turn-left': 'Left', 'turn-right': 'Right', 'forward': 'Forward', 'camp': 'Encamp'}.get(value, label.title())
        elif kind == 'CAMP_MENU' and value == 'select':
            label = 'Sel'
        elif kind == 'TARGET':
            if isinstance(value, int) and 0 <= value < len(chars):
                label = pstring(chars[value].b, maximum=15)
            elif isinstance(value, (tuple, list)) and len(value) == 2:
                label = '%d,%d' % tuple(value)
        elif kind == 'SPELL' and isinstance(value, int) and not info.get('prompt', '').startswith('Blast delay'):
            label = magic.spell_name(value)
        elif kind == 'LIST' and isinstance(value, (tuple, list)) and purpose == 'scribe':
            label = '%s: %s' % (value[0] + 1, magic.spell_name(value[1]))
        elif kind == 'LIST' and isinstance(value, int):
            if purpose == 'temple service':
                label = shops.SERVICES[value]
            elif 'money' in purpose:
                values = state.treasure_money if purpose.startswith('take') else shops.coins(character)
                label = '%s %d' % (shops.COINS[value], values[value])
            else:
                items = state.treasure_items if purpose in ('buy', 'take item') else character.items if character else ()
                if 0 <= value < len(items):
                    item = items[value]
                    label = item_name(item, state.party)
                    if purpose == 'buy':
                        multiplier = state.r1[0x36D]
                        price = max(1, rec.rdw(item, 0x3A))
                        if multiplier in (1, 2, 4, 8, 16, 32, 64, 128):
                            price = price * multiplier // 16
                        label = '%s  %d GP' % (label, price)
                    elif item[0x34]:
                        label = '* ' + label
        elif kind == 'CREATE_GENDER' and isinstance(value, int):
            label = ('Male', 'Female')[value]
        elif kind == 'CREATE_RACE' and isinstance(value, int):
            label = pstring(ssb_data.stexe(), 0xD71 + 9 * value, 8)
        elif kind == 'CREATE_CLASS' and isinstance(value, int):
            label = string(0xB8B + 27 * value, 26)
        elif kind == 'CREATE_ALIGNMENT' and isinstance(value, int):
            label = string(0xDB9 + 17 * value, 16)
        elif kind == 'CREATE_ADD' and isinstance(value, str):
            label = ('* ' if value in info.get('added','').split('|') else '') + value.removeprefix('character.')
        label = prompt_label(value, label, decision)
        result.append(player_label(value, label, decision))
    return result


def is_roster(decision):
    return bool(decision and (decision['kind'] == 'WHO' or
                decision['kind'] == 'TARGET' and decision['info'].get('purpose') == 'party member'))


def is_list(decision, labels_):
    if decision['info'].get('purpose')=='load game': return False
    if decision['kind'] == 'SPELL' and not any(isinstance(v, (int, tuple, list)) for v in decision['options'] or ()):
        return False
    return not is_roster(decision) and (decision['kind'] in (
        'LIST', 'SPELL', 'TARGET', 'CREATE_MENU', 'CREATE_ADD', 'CREATE_RACE',
        'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT', 'CREATE_SLOT',
        'CREATE_HP', 'CREATE_ABILITY') or decision['info'].get('vertical'))


def is_ack(decision):
    options = [v for v in decision['options'] or () if v not in (*shops.ROSTER, 'char-first')]
    return len(options) == 1 and 'PRESS' in str(options[0]).upper() and 'RETURN' in str(options[0]).upper()


def is_yes_no(decision, items):
    info = decision['info']
    if decision['kind'] == 'MENU' and not info.get('purpose') and not info.get('action') or info.get('action') == 'abort-spell':
        return False
    return sorted(label for _, _, label in items) == ['No', 'Yes']


def menu_pages(items):
    pages, row, width = [], [], 0
    for index, key, label in items:
        label = label[:40]
        if row and width + len(label) > 40:
            pages.append(row); row, width = [], 0
        row.append((index, key, label)); width += len(label) + 1
    return pages + [row]


def list_geometry(decision, combat=False):
    if decision['kind'] == 'MENU' and decision['info'].get('vertical'):
        top = min(22, 17 + len(wrapped_text(decision['info'].get('prompt', ''))))
        return 1, 38, top, 23 - top
    if decision['info'].get('purpose') == 'buy': return 1, 38, 1, 22
    if decision['info'].get('purpose') == 'temple service': return 2, 37, 4, 12
    if decision['kind']=='CREATE_ADD': return 1,38,2,21
    if decision['kind'] in ('CREATE_RACE', 'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT'):
        if decision['info'].get('purpose') == 'dual class': return (1, 38, 3, 20)
        return (3, 36, 3, 20)
    return (17, 1, 24, 10) if native_slots(decision) else (9, 30, 12, 11) if decision['kind'] == 'CREATE_MENU' else (23, 16, 10, 10) if combat else (1, 38, 3, 10)


def native_slots(decision):
    return bool(decision and decision['kind'] == 'CREATE_SLOT' and decision['options'][:26] == list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))


def decision_title(decision):
    info = decision['info']
    if info.get('purpose') == 'coin amount':
        return 'How many will you take? (0-%d)' % info.get('max', 0)
    return (info.get('prompt') or info.get('purpose') or info.get('place') or
            {'CAMP_MENU': 'Encamp', 'SHOP_MENU': 'Shop', 'SPELL': 'Choose spell',
             'LIST': 'Choose item', 'TARGET': 'Choose target', 'NUMBER': 'Enter number',
             'STRING': 'Enter text', 'COMBAT_ACTION': 'Combat'}.get(decision['kind'], decision['kind'].replace('_', ' ')))


def draw_status(frame, game, decision, assets):
    if decision['kind'] == 'CAMP_MENU' or decision['info'].get('purpose') == 'take' or decision['info'].get('place') in ('shop', 'temple', 'vault', 'treasure'):
        return
    state = game.s
    frame.rect(8, 8, 120, 120, 0)
    frame.text(1, 2, decision_title(decision), assets, 15, 15)
    if not state.party:
        return
    character = state.party[min(state.sel, len(state.party) - 1)]
    frame.text(1, 4, pstring(character.b, maximum=15), assets, 10, 15)
    take = decision['info'].get('purpose', '').startswith('take')
    for row, coin, amount in zip(range(6, 13), shops.COINS, state.treasure_money if take else shops.coins(character)):
        frame.text(1, row, '%s %d' % (coin, amount), assets, 10, 15)
    info = decision['info']
    if 'minutes' in info or 'remaining' in info:
        frame.text(1, 14, '%d min' % info.get('remaining', info.get('minutes', 0)), assets, 14, 15)


def draw_list(frame, controller, items, assets, *, combat=False):
    decision = controller.session.decision
    x, width, top, count = list_geometry(decision, combat)
    page = min(controller.page, max(0, (len(items) - 1) // count))
    if decision['kind'] == 'MENU' and decision['info'].get('vertical'):
        frame.rect(8, 136, 304, 48, 0)
        for row, text in enumerate(wrapped_text(decision['info'].get('prompt', '')), 17):
            if row < top: frame.text(1, row, text, assets, 10, 38)
        for row, (index, _, label) in enumerate(items[page*count:(page+1)*count], top):
            selected = index == controller.selected
            frame.text(1, row, label, assets, 0 if selected else 10, 38, background=15 if selected else 0)
        frame.text(0, 24, 'Select', assets, 0, background=15)
        return
    title_rows = 0 if decision['kind'] == 'CREATE_MENU' else 2
    frame.rect(x * 8, (top - title_rows) * 8, width * 8, (count + title_rows) * 8, 0)
    if title_rows: frame.text(x, top - 2, decision_title(decision), assets, 15, width)
    for row, (index, _, label) in enumerate(items[page * count:(page + 1) * count], top):
        selected = index == controller.selected
        frame.text(x, row, label, assets, 0 if selected else 10, width, background=15 if selected else 0)
    pages = max(1, (len(items) + count - 1) // count)
    can_exit = any(v is None or v in EXITS for v in decision['options'])
    if decision['kind'] == 'CREATE_MENU':
        frame.text(0, 24, 'Choose a FUNCTION ', assets, 13); frame.text(18, 24, 'Select ', assets, 0, background=15)
    else:
        frame.text(0, 24, 'Next Prev %s %d/%d Enter:select' % ('Exit' if can_exit else '    ', page + 1, pages), assets, 10, 40)


def current_picture(game):
    if game.s.mode == 6: return dict(kind='PIC', id=0x3C, dataset=game.s.dataset, frame=0)
    display=getattr(game.vm,'display',{})
    return {'kind':None} if display.get('portrait_hidden') else display


def frame_number(parts, elapsed):
    durations = [max(1, (part.delay or 0) * 10) for part in parts]
    if len(parts) == 1:
        return 0
    clock = int(elapsed * 100) % sum(durations)
    for i, duration in enumerate(durations):
        if clock < duration:
            return i
        clock -= duration
    return 0


def draw_picture(frame, game, elapsed=0):
    display = current_picture(game)
    kind, rid, dataset = display.get('kind'), display.get('id'), display.get('dataset', game.s.dataset)
    if not kind:
        return False
    if kind == 'SPRIT' and display.get('frame', 0) == 0 and display.get('pic', 255) != 255:
        kind, rid = 'PIC', display['pic']
    if rid == 255:
        return False
    if kind == 'HEAD_BODY':
        picture_blit(frame, 24, 24, 'HEAD', rid, dataset, art.picture('HEAD', rid, dataset)[2][0])
        picture_blit(frame, 24, 64, 'BODY', display['head'], dataset, art.picture('BODY', display['head'], dataset)[2][0])
        return True
    decoded = art.record(kind, rid, dataset)
    if kind == 'SPRIT':
        index = min(display.get('frame', 0), len(decoded.parts) - 1)
        part = decoded.parts[index]
        ds = ssb_data.stexe()
        palette = list(range(16))
        for old, new in zip(ds[0xAB8:0xAC8], ds[0xAC8:0xAD8]):
            palette[old] = new
        picture_blit(frame, 24 + part.x * 8, 24 + part.y * 8, kind, rid, dataset, part.frames[0], index,
                     transparent=0, colours=palette, clip=(24, 24, 112, 112))
    else:
        index = frame_number(decoded.parts, elapsed)
        part = decoded.parts[index]
        origin, clip = (8, (8, 8, 312, 128)) if kind == 'BIGPIC' else (24, (24, 24, 112, 112))
        picture_blit(frame, origin, origin, kind, rid, dataset, part.frames[0], index, clip=clip)
    return True


SAVE_ROOT = Path(os.environ.get('SM_SAVE_ROOT') or Path(__file__).resolve().parents[4] / 'local' / 'saves')


def slot_directory(slot, root=SAVE_ROOT):
    slot = str(slot).upper()
    if len(slot) != 1 or not 'A' <= slot <= 'Z':
        raise ValueError('Choose a slot from A to Z')
    path = (Path(root) / slot).resolve()
    if not path.is_relative_to(SAVE_ROOT.absolute()) or path.is_relative_to(Path(save.SECRET).resolve()):
        raise ValueError('Save directory must stay inside local/saves')
    return path


def snapshot(game, slot, *, state=None):
    slot = slot_directory(slot).name
    s, party = game.s if state is None else state, []; save.sync_globals(s)
    for c in s.party:
        record = rec.Rec(bytes(c.b))
        record.items = [rec.Item(bytes(i)) for i in c.items]
        record.effects = [rec.Effect(bytes(e)) for e in c.effects]
        party.append(record)
    data = dict(slot=slot, dataset=s.dataset, r0=s.r0[:], r1=s.r1[:], r2=s.r2[:],
                pos=[s.x, s.y, s.dir, s.ahead, s.attr], prev_mode=s.prev_mode, mode=s.mode,
                walls=[(v & 65535, i + 1) for i, v in enumerate(s.walls)],
                names=['CHRDAT%s%d' % (slot, i + 1) for i in range(len(party))], party=party)
    if 'vault.image' in s.g:
        vault = s.g['vault.image']
        data['vault'] = dict(header=vault[:28], items=[rec.Item(vault[i:i + 67]) for i in range(28, len(vault), 67)])
    return save.dump(data)


def write_slot_files(files, slot, root=SAVE_ROOT):
    target = slot_directory(slot, root)
    slot = target.name
    files = dict(files)
    allowed = {f'CHRDAT{slot}{i}.{ext}' for i in range(1, 9) for ext in ('SAV', 'STF', 'SFX')}
    allowed |= {f'SAVGAM{slot}.DAT', 'VAULT.DAT'}
    if not files.keys() <= allowed or f'SAVGAM{slot}.DAT' not in files:
        raise ValueError('Invalid native save file set')
    files = {name: data for name, data in files.items() if data or Path(name).suffix not in ('.STF', '.SFX')}
    save._load(files.get, slot)
    target.mkdir(parents=True, exist_ok=True)
    managed = allowed - ({'VAULT.DAT'} if 'VAULT.DAT' not in files else set())
    paths = {name: target / name for name in managed}
    if any(p.is_symlink() or not p.resolve().is_relative_to(target) for p in paths.values()):
        raise ValueError('Save files must stay inside their slot directory')
    previous = {name: p.read_bytes() if p.exists() else None for name, p in paths.items()}
    with TemporaryDirectory(prefix='.write-', dir=target.parent) as temporary:
        stage = Path(temporary)
        for name, data in files.items():
            (stage / name).write_bytes(data)
        changed = []
        try:
            for name in sorted(managed):
                if Path(name).suffix in ('.STF', '.SFX') and paths[name].exists():
                    paths[name].unlink(); changed.append(name)
            for name in sorted(managed, key=lambda n: (n.startswith('SAVGAM'), n)):
                if name in files:
                    os.replace(stage / name, paths[name])
                elif paths[name].exists():
                    paths[name].unlink()
                if name not in changed: changed.append(name)
        except OSError:
            for name in reversed(changed):
                if previous[name] is None:
                    paths[name].unlink(missing_ok=True)
                else:
                    (stage / name).write_bytes(previous[name])
                    os.replace(stage / name, paths[name])
            raise
    return target


def write_slot(session, slot, root=SAVE_ROOT):
    decision, state = session.decision, session.game.s
    if not decision or not state.party or state.g.get('combat.active') or decision['kind'] not in ('MOVE', 'CAMP_MENU'):
        raise ValueError('Save while exploring or in camp')
    return write_slot_files(snapshot(session.game, slot), slot, root)


def write_created_character(game, name, root=SAVE_ROOT):
    root = slot_directory('A', root).parent
    if not name or name in ('.', '..') or any(c in name for c in '<>:"/\\|?*') or name.endswith(('.', ' ')):
        raise ValueError('Character name cannot be used as a save filename')
    raw, items, effects = game.s.g['character.' + name.upper()]
    files = {name + '.WHO': raw, name + '.STF': b''.join(items), name + '.SFX': b''.join(effects)}
    if any((root / filename).is_symlink() or not (root / filename).resolve().is_relative_to(root) for filename in files):
        raise ValueError('Character files must stay inside the save directory')
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.character-', dir=root) as temporary:
        for filename, data in files.items():
            staged = Path(temporary) / filename
            if data:
                staged.write_bytes(data); os.replace(staged, root / filename)
            else: (root / filename).unlink(missing_ok=True)


def available_slots(root=SAVE_ROOT):
    return [chr(c) for c in range(65, 91) if (slot_directory(chr(c), root) / ('SAVGAM%s.DAT' % chr(c))).is_file()]


def slot_details(root=SAVE_ROOT):
    result = {}
    for slot in available_slots(root):
        directory = slot_directory(slot, root)
        try:
            saved = save.load(directory, slot)
            clock, pos = saved['r0'], saved['pos']
            stamp = datetime.fromtimestamp((directory / ('SAVGAM%s.DAT' % slot)).stat().st_mtime)
            lead = pstring(saved['party'][0].data).strip() if saved['party'] else 'No party'
            result[slot] = (stamp.strftime('%Y-%m-%d %H:%M') + ' ' + lead,
                            'Day %d %02d:%02d Area %d/%d (%d,%d)' % (
                                clock[0xCA], clock[0xC9], clock[0xC8] * 10 + clock[0xC7],
                                saved['dataset'], clock[0xF2], pos[0], pos[1]))
        except (OSError, ValueError, KeyError) as error:
            result[slot] = ('Unreadable save', str(error))
    return result


def load_slot(slot, root=SAVE_ROOT):
    path = slot_directory(slot, root)
    session = Session(profile=ssb, slot=path.name, directory=path, engines=True)
    if session.decision is None:
        session.close()
        raise ValueError(session.result or 'Unable to load this slot')
    return session


def write_autosave(files, root=SAVE_ROOT):
    root = slot_directory('A', root).parent
    save._load(files.get, 'A')
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.autosave-', dir=root) as temporary:
        staged = Path(temporary) / 'autosave.zip'
        with ZipFile(staged, 'w') as archive:
            for name, data in files.items(): archive.writestr(name, data)
        os.replace(staged, root / 'autosave.zip')


def load_autosave(root=SAVE_ROOT):
    root = slot_directory('A', root).parent
    with ZipFile(root / 'autosave.zip') as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    with TemporaryDirectory(prefix='.resume-', dir=root) as temporary:
        write_slot_files(files, 'A', temporary)
        session = load_slot('A', temporary)
    session.game.directory = str(root)
    session.journal_slot = 'resume'
    return session


@lru_cache(maxsize=64)
def placeholder_tile(colour):
    return tuple(tuple(colour if x and y else 0 for x in range(8)) for y in range(8))


class Assets:
    def __init__(self):
        try:
            self.art = importlib.import_module('sm.titles.ssb.art')
        except ModuleNotFoundError as error:
            if error.name != 'sm.titles.ssb.art':
                raise
            self.art = None

    @lru_cache(maxsize=128)
    def glyph(self, ch):
        if self.art is not None:
            return self.art.glyph(ch)
        index = ord(ch.upper()[0]) & 63
        raw = dax.load('8X8D5', d=ssb_data.SECRET)[201]
        return tuple(raw[index * 8:index * 8 + 8])

    def border(self, symbol):
        if self.art is not None:
            return self.art.symbols(202, 1)[symbol - 0x100]
        return placeholder_tile(6)

    def wall_tile(self, state, wall, index):
        if self.art is None:
            return placeholder_tile((wall - 1) % 6 + 1)
        return self._wall_tile(state.dataset, tuple(state.walls), wall, index)

    @lru_cache(maxsize=16)
    def wall_sets(self, dataset, ids):
        blocks = {}
        symbols = [self.art.symbols(203, 1), None, None, None, self.art.symbols(202, 1)]
        for slot, rid in enumerate(ids, 1):
            if rid == 0xFFFF:
                continue
            for block in self.art.walls(rid, dataset, slot):
                blocks[block.slot] = block
                symbols[block.slot] = self.art.symbols(block.symbol_set, dataset)
        return blocks, symbols

    def _wall_tile(self, dataset, ids, wall, index):
        blocks, symbols = self.wall_sets(dataset, ids)
        slot, kind = divmod(wall - 1, 5)
        block = blocks.get(slot + 1)
        if block is None:
            return None
        symbol = block.types[kind][index]
        return self.art.symbol(symbol, symbols) if symbol else None


@lru_cache(maxsize=2048)
def glyph_pixels(glyph, colour, background):
    row = tuple if colour is None or background is None else bytes
    return tuple(row(colour if bits & (128 >> x) else background for x in range(8)) for bits in glyph)


class Frame:
    def __init__(self):
        self.rows = [bytearray(WIDTH) for _ in range(HEIGHT)]

    def rect(self, x, y, w, h, colour):
        left, right = max(0, x), min(WIDTH, x + w)
        if left < right:
            fill = bytes([colour]) * (right - left)
            for row in range(max(0, y), min(HEIGHT, y + h)):
                self.rows[row][left:right] = fill

    def blit(self, x, y, pixels, transparent=None, clip=None, colours=None):
        left, top, right, bottom = clip or (0, 0, WIDTH, HEIGHT)
        left, top, right, bottom = max(0, left), max(0, top), min(WIDTH, right), min(HEIGHT, bottom)
        for yy, row in enumerate(pixels, y):
            if not top <= yy < bottom:
                continue
            if transparent is None and colours is None and (isinstance(row,(bytes,bytearray)) or None not in row):
                start, stop = max(0,left-x), min(len(row),right-x)
                if start < stop: self.rows[yy][x+start:x+stop] = bytes(row[start:stop])
                continue
            for xx, colour in enumerate(row, x):
                if left <= xx < right and colour != transparent:
                    self.rows[yy][xx] = colour if colours is None else colours[colour]

    def text(self, col, row, value, assets, colour=15, limit=None, background=0):
        for n, ch in enumerate(str(value)[:limit]):
            glyph = assets.glyph(ch)
            pixels = glyph_pixels(tuple(glyph), colour, background)
            self.blit((col + n) * 8, row * 8, pixels)

    def tk_rows(self, scale=SCALE):
        colours = ['#%02x%02x%02x' % rgb for rgb in PALETTE]
        rows = []
        for row in self.rows:
            line = '{' + ' '.join(colours[c] for c in row for _ in range(scale)) + '}'
            rows.extend([line] * scale)
        return ' '.join(rows)

    def save(self, path=LOCAL / 'ui_townhall.png', scale=SCALE):
        path = Path(path).resolve()
        if not path.is_relative_to(LOCAL.resolve()):
            raise ValueError('screenshots must stay under local/')
        raw = bytearray()
        for row in self.rows:
            line = b'\0' + b''.join(bytes(PALETTE[c]) * scale for c in row)
            raw.extend(line * scale)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as out:
            out.write(b'\x89PNG\r\n\x1a\n')
            for kind, data in ((b'IHDR', struct.pack('>2I5B', WIDTH * scale, HEIGHT * scale, 8, 2, 0, 0, 0)),
                               (b'IDAT', zlib.compress(raw)), (b'IEND', b'')):
                out.write(struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data)))
        return path


def new_frame(assets):
    from .vga import Assets as VGAAssets, Frame as VGAFrame
    return VGAFrame(assets) if isinstance(assets, VGAAssets) else Frame()


def capture_background(controller, renderer=None):
    from .vga import capture
    return capture(controller, renderer)


def capture_footer(controller, clear_top=False):
    from .vga import capture_footer as capture
    return capture(controller, clear_top)


def background_rows(background, assets):
    from .vga import background_rows as select_rows
    return select_rows(background, assets)


def picture_blit(frame, x, y, name, ident, dataset, pixels, index=0, **kwargs):
    if hasattr(frame, 'mod'): frame.mod(x, y, name, ident, dataset, pixels, frame=index, **kwargs)
    else: frame.blit(x, y, pixels, **kwargs)


def location(state, clock=None, painted=None):
    x, y = (state.x, state.y) if state.r0[0x1FD] == 255 else (state.r0[0x1FD], state.r0[0x1FE])
    direction = (state.dir + state.r0[0x1FF] * (2 if state.r0[0xE6] else 1)) % 8
    if painted is not None: x,y,direction=painted
    clock = state.r0[0xC6:0xCD] if clock is None else clock
    result = '%d,%d %s %02d:%02d' % (x, y, ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')[direction],
                                    clock[3], clock[2] * 10 + clock[1])
    return result + (' CAMPING' if state.mode == 2 else ' SEARCH' if state.r1[0x2CA] & 1 else '')


def menu_items(decision, game=None):
    if decision is None or decision['options'] is None:
        return []
    if decision['kind'] == 'CREATE_ROLL':
        return [(decision['options'].index(value), key, label) for value, key, label in
                (('reroll', 'y', 'Yes'), ('keep', 'n', 'No'))]
    if decision['kind'] == 'CREATE_SAVE':
        return [(i, key, label) for i, key, label in ((0, 'y', 'Yes'), (1, 'n', 'No'))]
    if decision['kind'] == 'CREATE_REMOVE':
        return [(1, 'y', 'Yes'), (0, 'n', 'No')]
    if decision['kind'] == 'CREATE_EXIT':
        return [(1, 'y', 'Yes'), (0, 'n', 'No')]
    if decision['info'].get('purpose') in ('drop item', 'lose scribe scroll', 'use refusal'):
        return [(1, 'y', 'Yes'), (0, 'n', 'No')]
    if native_slots(decision):
        return [(i, slot.lower(), slot) for i, slot in enumerate(decision['options'][:10])]
    native = player_menu(decision)
    if native is not None:
        return native
    labels = decision_labels(game, decision) if game is not None else [
        'Exit' if value is None else str(value) for value in decision['options']]
    if decision['kind'] == 'MENU' and is_ack(decision) and labels[0] == 'PRESS BUTTON OR RETURN TO CONTINUE.':
        labels[0] = 'PRESS <ENTER>/<RETURN> TO CONTINUE'
    if decision['kind'] == 'MOVE':
        options = decision['options']
        return [(-1, 'm', 'Move'), (-2, 'a', 'Area')] + [
            (options.index(value), label[0].lower(), label) for value, label in
            (('cast', 'Cast'), ('view', 'View'), ('camp', 'Encamp'), ('search', 'Search'), ('look', 'Look')) if value in options]
    hidden = {i for i, v in enumerate(decision['options']) if v in (*shops.ROSTER, 'char-first')}
    list_mode = is_list(decision, labels)
    used, result = set(), []
    for index, label in enumerate(labels):
        if decision['kind'] in ('CREATE_RACE', 'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT') and decision['options'][index] is None:
            continue
        if index in hidden:
            continue
        if list_mode and index and index % 10 == 0:
            used.clear()
        key = ('1234567890a'[index % 11] if decision['kind'] == 'CREATE_MENU' else
               str((index % 10 + 1) % 10)) if list_mode or is_roster(decision) else next(
            (c.lower() for c in label if c.isalnum() and c.lower() not in used), '')
        if not key:
            key = next((c for c in '1234567890abcdefghijklmnopqrstuvwxyz' if c not in used), '')
        used.add(key)
        result.append((index, key, label))
    return result


def compact_menu(items, decision):
    return not is_list(decision, [label for _, _, label in items])


class FileMenu:
    def __init__(self, controller, root=None):
        self.controller, self.root = controller, root or SAVE_ROOT
        self.active, self.mode, self.message, self.saved = False, 'game', '', []
        self.page, self.details = 0, {}
        self.native = False

    def rows(self):
        if self.native: return [(chr(65+i), 17+2*i, 24, 1, 1) for i in range(10)]
        return [(chr(65 + i), 2, 4 + (i % 8) * 2, 36, 2) for i in range(self.page * 8, min(26, (self.page + 1) * 8))]

    def regions(self):
        rows = ([('s', 3, 5, 16, 1), ('l', 3, 7, 16, 1), ('q', 3, 9, 16, 1), ('r', 3, 11, 16, 1)]
                if self.mode == 'game' else self.rows())
        regions = [dict(rect=(x * 8, y * 8, w * 8, h * 8), key=dict(keysym=slot.lower(), char=slot.lower()))
                   for slot, x, y, w, h in rows]
        if self.mode != 'game' and not self.native:
            regions += [dict(rect=(x, 192, 72, 8), key=dict(keysym=key, char=''))
                        for x, key in ((0, 'Prior'), (80, 'Next'))]
        if not self.native:
            regions.append(dict(rect=(0, 192, 320, 8) if self.mode == 'game' else (240, 192, 64, 8),
                                key=dict(keysym='Escape', char='')))
        return regions

    def key(self, keysym, char=''):
        if keysym == 'F10':
            self.active, self.mode = not self.active, 'game'
            return
        if keysym == 'Escape':
            if self.mode == 'game':
                self.active = False
            else:
                self.mode = 'game'
            return
        if self.mode != 'game' and keysym in ('Prior', 'Next', 'Home', 'End'):
            self.page = (0 if keysym == 'Home' else 3 if keysym == 'End' else
                         max(0, min(3, self.page + (-1 if keysym == 'Prior' else 1))))
            return
        key = char.lower()
        try:
            if self.mode == 'game':
                if key in ('s', 'l'):
                    self.mode = 'save' if key == 's' else 'load'
                    self.page, self.details = 0, slot_details(self.root)
                    self.saved = list(self.details)
                    self.message = ''
                elif key == 'q':
                    self.controller.quit_requested = True
                    self.controller.session.close()
                    self.active = False
                elif key == 'r' or keysym in ('Return', 'KP_Enter'):
                    self.active = False
            elif len(key) == 1 and 'a' <= key <= 'z':
                slot = key.upper()
                self.page = (ord(slot) - 65) // 8
                if self.mode == 'save':
                    write_slot(self.controller.session, slot, self.root)
                    if journal := getattr(self.controller, 'journal', None): journal.save(slot, selected=True)
                    self.mode, self.message = 'game', 'Saved slot ' + slot
                else:
                    new = load_slot(slot, self.root)
                    old = self.controller.session
                    self.controller.__init__(new, save_root=self.root, presentation=self.controller.presentation_enabled)
                    old.close()
        except (OSError, ValueError, KeyError) as error:
            self.message = str(error)

    def draw(self, frame, assets):
        if self.native:
            parent = getattr(self.controller, 'save_background', None)
            if parent is not None: frame.rows = [row[:] for row in background_rows(parent, assets)]
            frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, 'Save Which Game: ', assets, 13)
            for slot, x, row, width, _ in self.rows():
                selected = ord(slot)-65 == self.controller.selected
                frame.text(x, row, slot, assets, 0 if selected else 15, width, background=15 if selected else 0)
            return
        draw_frame(frame, assets, 'full')
        frame.rect(8, 8, 304, 176, 0)
        frame.text(2, 2, 'Game' if self.mode == 'game' else self.mode.title() + ' game', assets, 15)
        if self.mode == 'game':
            for row, label in ((5, 'S  Save'), (7, 'L  Load'), (9, 'Q  Quit'), (11, 'R  Resume')):
                frame.text(3, row, label, assets, 10)
                frame.text(3, row, label[0], assets, 15)
            frame.text(2, 15, 'F2 Area map    F12 Screenshot', assets, 10, 36)
        else:
            rows = self.rows()
            frame.text(28, 2, '%d/4 %s-%s' % (self.page + 1, rows[0][0], rows[-1][0]), assets, 15)
            for slot, x, row, width, _ in self.rows():
                first, second = self.details.get(slot, ('Empty', ''))
                selected = self.native and ord(slot) - 65 == self.controller.selected
                frame.text(x, row, slot + ' ' + first, assets, 0 if selected else 15 if slot in self.saved else 10, width,
                           background=15 if selected else None)
                frame.text(x, row + 1, '  ' + second, assets, 10, width)
        for row, line in enumerate(textwrap.wrap(self.message, 36)[:2], 21):
            frame.text(2, row, line, assets, 14, 36)
        frame.text(0, 24, 'Esc Resume' if self.mode == 'game' else 'PgUp Prev PgDn Next A-Z Slot' + ('' if self.native else '  Esc Back'), assets, 15, 40)


class Controller:
    def __init__(self, session, *, save_root=None, presentation=False):
        self.session, self.entry, self.error = session, '', ''
        self.text, self.out_index, self.page = '', 0, 0
        self.selected, self.animation_start = 0, time.monotonic()
        self.menu_selection = {}
        self.area_map = False
        self.move_mode, self.text_epoch, self.last_decision = False, -1, None
        self.files, self.quit_requested = FileMenu(self, save_root), False
        self.autosave_enabled = getattr(self, 'autosave_enabled', False)
        self.autosave_files = None
        self.slot_decision, self.slot_menu = None, None
        self.presentation_enabled = presentation
        self.sound_seq, self.sound_events, self.sound_last = 0, deque(maxlen=64), (None, None, '', False)
        if presentation and hasattr(session, 'ai_check_wait'): session.game.ai_check = session.ai_check_wait
        self.presentation_event, self.presentation_deadline = None, 0
        self.presentation_game, self.presentation_elapsed = None, None
        self.effect_scale = getattr(self, 'effect_scale', 1.0)
        self.message_hold = getattr(self, 'message_hold', 400)
        self.equipment_icon = getattr(self, 'equipment_icon', False)
        self.manual_bodies = getattr(self, 'manual_bodies', {})
        self.held_keys = deque()
        self.rest_active = False
        self.playing_key = False
        self.capture_text()

    def presenting(self):
        return bool(self.presentation_event or getattr(self.session.game, 'presentation', None) or self.held_keys or getattr(self.session, 'check', False)
                    or self.presentation_enabled and any(n[4] for n in getattr(self.session.game.vm, 'service_names', ()))
                    or self.session.decision and self.session.decision['kind'] == 'INPUT')

    def advance_rest(self):
        if not self.session.decision or self.session.decision['kind'] != 'INPUT': return
        self.rest_active = True
        try:
            while self.session.decision:
                if self.session.decision['kind'] == 'INPUT':
                    self.session.step(int(bool(self.held_keys)))
                    self.capture_text()
                elif self.held_keys:
                    self.playing_key = True
                    try: self.key(*self.held_keys.popleft())
                    finally: self.playing_key = False
                else: break
        finally:
            self.rest_active = False
        following = self.session.decision
        if following and following['kind'] == 'CAMP_MENU':
            value = self.menu_selection.get(('CAMP_MENU', following['info'].get('purpose')))
            if value in following['options']: self.selected = following['options'].index(value)

    def set_effect_scale(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10: raise ValueError('scale must be a number from 0 to 10')
        self.effect_scale = float(value)

    def apply_plus(self, settings):
        self.plus_settings = settings
        self._vga_key = None
        self.set_effect_scale(settings.options['effect_scale'])
        self.message_hold = settings.options['message_hold']
        self.equipment_icon = settings.options['equipment_icon']
        self.manual_bodies = dict(settings.data.get('manual_bodies', {}))

    def emit(self, command):
        self.sound_seq += 1; self.sound_events.append((self.sound_seq, command))

    def hear(self, event):
        for command in event_sounds(event, self.sound_last): self.emit(command)
        self.sound_last = (event['kind'], event.get('actor'), event.get('text') or '', bool(event.get('merge')))

    def advance_presentation(self, elapsed):
        self.advance_rest()
        if not self.presentation_enabled: return None
        self.capture_text()
        if self.presentation_elapsed is not None and elapsed < self.presentation_elapsed:
            self.presentation_deadline += elapsed - self.presentation_elapsed
        self.presentation_elapsed = elapsed
        if self.presentation_event and elapsed < self.presentation_deadline:
            return self.presentation_event
        self.presentation_event = None
        queue = self.session.game.presentation
        while not queue and getattr(self.session, 'check', False):
            first = self.held_keys[0][1] if self.held_keys else None
            self.held_keys.clear()
            self.session.resume_check(first)
            queue = self.session.game.presentation
        if not queue and self.held_keys and not any(n[4] for n in getattr(self.session.game.vm, 'service_names', ())):
            self.playing_key = True
            try: self.key(*self.held_keys.popleft())
            finally: self.playing_key = False
            queue = self.session.game.presentation
        if queue:
            self.presentation_event = queue.popleft()
            self.hear(self.presentation_event)
            merged = []
            while self.presentation_event.get('merge'):
                merged.append(self.presentation_event['kind'] + (':' + str(self.presentation_event.get('cue')) if self.presentation_event['kind'] == 'sound' else ''))
                if not queue and getattr(self.session, 'check', False):
                    first = self.held_keys[0][1] if self.held_keys else None
                    self.held_keys.clear(); self.session.resume_check(first)
                if not queue:
                    self.presentation_event = None
                    self.text = self.session.game.presentation_text
                    return None
                self.presentation_event = queue.popleft(); self.hear(self.presentation_event)
            if merged: self.presentation_event = dict(self.presentation_event, merged=merged)
            base = self.presentation_deadline if 0 <= elapsed - self.presentation_deadline < SAMPLE_MS / 1000 else elapsed
            self.presentation_deadline = base + (measured_hold(self.presentation_event['delay']) + gap_ms(self.presentation_event, queue) / 1000) * self.effect_scale
            if self.presentation_event['kind']=='script-death': self.presentation_deadline=base+3
            if self.presentation_event['kind']=='script-hold': self.presentation_deadline=base+self.presentation_event['delay']
        elif self.session.game.s.g.get('combat.active'):
            self.text = self.session.game.presentation_text
        return self.presentation_event

    def file_picker(self):
        decision = self.session.decision
        if not native_slots(decision): return None
        if self.slot_decision is not decision:
            self.slot_decision, self.slot_menu = decision, FileMenu(self, self.files.root)
            self.slot_menu.mode, self.slot_menu.native = 'save', True
            self.slot_menu.details = slot_details(self.files.root) if self.files.root.resolve().is_relative_to(SAVE_ROOT.resolve()) else {}
            self.slot_menu.saved = list(self.slot_menu.details)
        self.slot_menu.page = self.page
        return self.slot_menu

    def remember(self):
        if (self.autosave_enabled and self.session.decision and not getattr(self.session, 'pending', False) and self.session.game.s.party
                and not self.session.game.s.g.get('combat.active')):
            self.autosave_files = snapshot(self.session.game, 'A', state=self.session.game.s.copy())

    def autosave(self):
        self.remember()
        if self.autosave_enabled and self.autosave_files is not None:
            write_autosave(self.autosave_files, self.files.root)
            if journal := getattr(self, 'journal', None): journal.save('resume')

    def capture_text(self):
        game = self.session.game
        if self.presentation_enabled and self.presentation_game is not game:
            self.presentation_game = game
            game.presentation, game.presentation_text = deque(), ''
            game.presentation_poses = {}
            game.presentation_cursor = None
            game.presentation_view = None
            game.presentation_panel = None
            self.presentation_event, self.presentation_elapsed = None, None
            self.held_keys.clear()
        vm = self.session.game.vm
        self.remember()
        output = vm.out
        epoch = getattr(vm, 'text_epoch', 0)
        if epoch != self.text_epoch:
            self.text, self.out_index, self.text_epoch = '', getattr(vm, 'text_start', 0), epoch
        if len(output) > self.out_index:
            self.text = (self.text + ''.join(output[self.out_index:]))[-8192:]
            if game.s.g.get('combat.active'):
                self.text = self.text.rstrip().split('\n')[-1]
            self.out_index = len(output)
        decision = self.session.decision
        if decision is not self.last_decision:
            previous = self.last_decision
            self.last_decision = decision
            if decision and decision['kind'] == 'CREATE_ROLL':
                self.selected = decision['options'].index('reroll')
            if decision and decision['kind'] == 'CREATE_ICON':
                b = game.s.g['creation.pending'][0]; field = decision['info'].get('field')
                if not previous or previous['kind'] != 'CREATE_ICON':
                    self.icon_old, self.icon_phase = bytes(b), 'root'
                    self.icon_body_chosen = False
                    self.selected = getattr(self, 'creation_word', 0)
                    if previous and previous['info'].get('purpose') == 'alter': self.selected = previous['options'].index('icon')
                if field in ('head', 'weapon', 'size'):
                    self.icon_value = b[{'head': 0x153, 'weapon': 0x154, 'size': 0x156}[field]]
                elif field == 'color': self.icon_value = (b[0x157 + self.icon_part] >> (4 * self.icon_channel)) & 15
            if decision and decision['kind'] == 'CREATE_ADD':
                self.add_source = not (previous and previous['kind']=='CREATE_ADD')
                if self.add_source: self.add_start=0
                if not self.add_source: self.selected=decision['options'].index(decision['info']['last'])
            if decision and decision['kind'] == 'CREATE_MODIFY' and (not previous or previous['kind'] not in ('CREATE_ABILITY', 'CREATE_HP', 'CREATE_NAME')):
                self.modify_field, self.modify_cursor, self.selected = 0, 0, 1
                self.modify_name_visited = False
                self.modify_marks=set()
            if decision and decision['info'].get('action') == 'continue-battle': self.selected = 1
            if decision and decision['info'].get('action') == 'done' and 'guard' in decision['options']:
                self.selected = decision['options'].index('guard')
            if decision and decision['kind'] == 'COMBAT_ACTION' and not decision['info'].get('action'):
                turn = (game.s.g.get('combat.records'), decision['info'].get('round'), decision['info'].get('actor'))
                previous_turn = getattr(self, 'combat_menu_turn', None)
                if previous_turn is None or previous_turn[0] is not turn[0] or previous_turn[1:] != turn[1:]:
                    self.selected = menu_items(decision, game)[0][0]
                self.combat_menu_turn = turn
            if observer := getattr(self, 'decision_observer', None): observer()
            if decision and decision['info'].get('action') in ('attack-ally', 'flee-confirm', 'abort-spell'):
                self.selected = 1
            if decision and decision['info'].get('purpose') == 'cast refusal':
                self.selected = 1
            if decision and decision['info'].get('purpose') == 'resting':
                self.selected = decision['options'].index('stop')
            if decision and decision['info'].get('purpose') == 'quit to DOS': self.selected=1
            if decision and decision['info'].get('purpose') == 'drop from party': self.selected=1
            if decision and decision['info'].get('purpose') == 'treasure leave': self.selected=0
            if decision and decision['info'].get('purpose') == 'take' and previous and previous['info'].get('purpose') == 'treasure':
                value=self.menu_selection.get((previous['kind'],'treasure'))
                if isinstance(value,tuple) and value[0]=='word':
                    words=menu_items(decision,game); self.selected=words[min(value[1],len(words)-1)][0]
            if decision and decision['info'].get('purpose') == 'difficulty': self.selected=game.s.r0[0x1F4]
            if decision and decision['info'].get('purpose') == 'items':
                self.item_start, self.item_command = 0, 'r'
                if pending := getattr(self,'inventory_return',None):
                    selected,start,index=pending; self.inventory_return=None
                    self.selected=min(selected,len(decision['options'])-2); self.item_start=min(start,max(0,len(decision['options'])-19))
                    words=inventory_bar(self); self.item_command=words[index if index<len(words) else 0][0].lower()
            if decision and decision['info'].get('purpose')=='view':
                self.inventory_return=None
                if not previous or previous['info'].get('purpose')!='deposit money': self.purse_background=None
            if decision and decision['info'].get('purpose') in ('confirm sale','confirm identification'):
                self.selected=int(decision['info']['purpose']=='confirm sale')
            if decision and decision['info'].get('purpose') in ('take money','deposit money'):
                value=self.menu_selection.get((previous['kind'],previous['info'].get('purpose'))) if previous else None
                word=value[1] if isinstance(value,tuple) and value[0]=='word' else getattr(self,'coin_command',0) if previous and previous['info'].get('purpose')=='coin amount' else 0
                self.coin_command=word if decision['info']['purpose']=='take money' and word<2 else 0
                self.selected=coin_rows(self)[0] if coin_rows(self) else 0
            if decision and decision['info'].get('purpose')=='take item':
                self.take_start,self.take_command=0,0
                if previous and previous['info'].get('purpose')=='take item':
                    start,selected=self.take_return; count=len(decision['options'])-1
                    self.take_start=0 if count<=22 or start>count else min(start,selected)
                    self.selected=min(selected,count-1)
            if decision and decision['info'].get('purpose')=='effects':
                self.effects_start,self.effects_selected,self.effects_command=0,0,0
            if cast_list(decision):
                self.cast_start, self.cast_command = 0, decision['info'].get('command', 0)
                if decision['info'].get('purpose')=='scribe' and previous and previous['info'].get('purpose')=='scribe confirm': self.cast_command=min(1,len(cast_bar(self))-1)
                if decision['info'].get('purpose') == 'view spells': self.cast_command = min(1, len(cast_bar(self))-1)
                rows = cast_rows(self)[:cast_height(self)]
                kept = getattr(self, 'cast_row', 0) if decision['info'].get('at') == 0x1403 and previous and previous['kind'] in ('TARGET', 'SPELL') else 0
                self.selected = next((rows[n][0] for n in range(min(kept, len(rows) - 1), 0, -1) if rows[n][0] is not None),
                                     next(i for i, _ in reversed(rows) if i is not None))
            if (decision and decision['kind'] == 'TARGET' and self.session.game.s.g.get('combat.active')
                    and decision['info'].get('action') != 'move'):
                init_aim(self, previous)
            if is_roster(decision):
                index = decision['info'].get('recipient',self.session.game.s.sel)
                options = decision['options']
                self.selected = (options.index(index) if decision['kind'] == 'TARGET' and index in options
                                 else min(index, len(options) - 1))

    def roster_selected(self):
        decision = self.session.decision
        if is_roster(decision):
            return self.selected if decision['kind'] == 'WHO' else decision['options'][self.selected]
        return self.session.game.s.sel

    def roster_key(self, value):
        selected, page = self.selected, self.page
        self.session.step(self.session.decision['options'].index(value)); self.capture_text()
        self.selected, self.page = selected, page
        return True

    def roster_highlighted(self, index):
        game = self.session.game
        if not is_roster(self.session.decision) and game.s.g.get('47E2') and hasattr(game.vm, 'roster_highlights'):
            return index in game.vm.roster_highlights
        return index == self.roster_selected()

    def key(self, keysym, char=''):
        if self.presenting() and not self.playing_key:
            self.held_keys.append((keysym, char))
            return False
        if self.session.decision and self.session.decision['info'].get('purpose') in ('script damage', 'combat defeat'):
            self.session.step(0); self.capture_text(); return True
        if keysym == 'F10' or self.files.active:
            self.files.key(keysym, char)
            return False
        decision = self.session.decision
        if decision is None:
            return False
        if (decision['options'] and len(char) == 1 and char.isdigit() and is_list(decision, ()) and not native_slots(decision)
                and not (decision['kind'] == 'TARGET' and self.session.game.s.g.get('combat.active'))):
            if char not in '8293': return False
            keysym, char = {'8': 'Up', '2': 'Down', '9': 'Prior', '3': 'Next'}[char], ''
        handled = player_key(self, keysym, char)
        if handled is not None:
            return handled
        options, kind = decision['options'], decision['kind']
        slot_mode = native_slots(decision)
        if slot_mode and (keysym in ('Prior','Next') or len(char)==1 and 'k'<=char.lower()<='z'):
            return False
        self.error = ''
        if options and 'char-first' in options and (keysym in ('Home','End','Prior','Next','Insert','Delete') or is_ack(decision) and keysym in ('Left','Right')):
            return self.roster_key('char-first')
        if kind == 'MOVE' and (keysym == 'F2' or char.lower() == 'a'):
            state = self.session.game.s
            if not state.r0[0xFB] and state.r0[0x1FD] == 255:
                self.area_map = not self.area_map
            elif state.r0[0xFB]:
                self.not_here_seen = False
            self.selected = -2
            return False
        if kind == 'MOVE' and char.lower() == 'm':
            self.move_mode = True; self.selected = -1; return False
        if kind == 'MOVE' and self.move_mode and keysym == 'Escape': return False
        if kind == 'MOVE' and self.move_mode and (keysym in ('Return', 'KP_Enter') or char.lower() == 'e'):
            self.move_mode = False; self.selected = -1; return False
        if options is None:
            ready, answer = input_key(self, keysym, char)
            if not ready: return False
        else:
            game = self.session.game if hasattr(self.session.game, 's') else None
            items = menu_items(decision, game)
            if keysym == 'Escape' and is_yes_no(decision, items): return False
            if kind in ('CREATE_MENU', 'CREATE_RACE', 'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT') and (char == ' ' or char.lower() == 's'):
                keysym, char = 'Return', ''
            list_mode = not compact_menu(items, decision)
            roster = is_roster(decision)
            aim = kind == 'TARGET' and bool(self.session.game.s.g.get('combat.active'))
            if not list_mode and not roster and not (kind == 'MOVE' and self.move_mode):
                if char in ('4', '6') and len(items) > 1:
                    keysym, char = ('Left' if char == '4' else 'Right'), ''
                elif char in ('1','2','3','4','5','6','7','8','9','\\') and 'char-up' in options:
                    self.selected = next((i for i,key,_ in items if key == char), self.selected)
                    if char in ('2', '8'): return self.roster_key('char-down' if char == '2' else 'char-up')
                    if 'char-first' in options: return self.roster_key('char-first')
            pages = menu_pages(items)
            count = list_geometry(decision)[3]
            page_count = (len(items) + count - 1) // count if list_mode else len(pages)
            if keysym in ('Prior', 'Next') or (list_mode and not slot_mode and char.lower() in ('n', 'p') and char):
                delta = -1 if keysym == 'Prior' or char.lower() == 'p' else 1
                rows = [i for i, _, _ in items]; row = rows.index(self.selected) % count if list_mode and not aim and self.selected in rows else 0
                self.page = max(0, min(page_count - 1, self.page + delta))
                self.selected = items[min(len(items) - 1, self.page * count + row)][0] if list_mode else pages[self.page][0][0]
                return False
            if (not list_mode and not roster and keysym in ('Up', 'Down') and 'char-up' in options
                    and not (kind == 'MOVE' and self.move_mode)):
                return self.roster_key('char-up' if keysym == 'Up' else 'char-down')
            if list_mode and not aim and keysym in ('Home', 'End'): return False
            if list_mode and not aim and keysym in ('Up', 'Down'):
                rows = [i for i, _, _ in items][self.page * count:(self.page + 1) * count] or [i for i, _, _ in items]
                at = rows.index(self.selected) if self.selected in rows else 0
                self.selected = rows[(at + (-1 if keysym == 'Up' else 1)) % len(rows)]
                return False
            if (roster or list_mode and aim) and keysym in ('Up', 'Down', 'Home', 'End'):
                indices = [i for i, _, _ in items if not roster or options[i] is not None]
                if roster and kind=='TARGET': indices.sort(key=lambda i:options[i])
                last=len(indices)-1; position = indices.index(self.selected) if self.selected in indices else 0
                position = (0 if keysym == 'Home' else last if keysym == 'End'
                            else (position + (-1 if keysym == 'Up' else 1)) % (last + 1) if roster or kind=='CREATE_MENU'
                            else max(0, min(last, position + (-1 if keysym == 'Up' else 1))))
                self.selected = indices[position]; self.page = position // count
                return False
            if (not list_mode and not roster and len(items) > 1 and keysym in ('Left', 'Right')
                    and not (kind == 'MOVE' and self.move_mode)):
                indices = [i for i, _, _ in items]
                position = indices.index(self.selected) if self.selected in indices else 0
                self.selected = indices[(position + (-1 if keysym == 'Left' else 1)) % len(indices)]
                self.page = next(p for p, row in enumerate(pages) if any(i == self.selected for i, _, _ in row))
                return False
            if list_mode:
                items = items[self.page * count:(self.page + 1) * count]
            default = self.selected if list_mode or roster or any(i == self.selected for i, _, _ in items) else items[0][0]
            answer = default if options and keysym in ('Return', 'KP_Enter') else None
            if keysym == 'Escape' or ((list_mode or roster) and not slot_mode and char.lower() in ('e', 'x') and char):
                answer = next((i for i, value in enumerate(options) if value is None or value in EXITS), None)
            if kind == 'MOVE' and self.move_mode and keysym in ('Left', 'Right', 'Up', 'Down'):
                value = {'Left': 'turn-left', 'Right': 'turn-right', 'Up': 'forward', 'Down': 'turn-around'}[keysym]
                answer = options.index(value) if value in options else None
            elif char:
                answer = next((i for i, hotkey, _ in items if hotkey == char.lower()), answer)
                if roster and char.lower() == 's': answer = self.selected
            if answer is None:
                if keysym == 'F2': self.error = 'Press Return to continue.' if is_ack(decision) else 'Finish this prompt before using Area.'
                return False
            if kind == 'MOVE' and answer < 0:
                return self.key('m' if answer == -1 else 'a', 'm' if answer == -1 else 'a')
        if self.presentation_enabled and self.session.game.s.g.get('combat.active'):
            self.session.game.presentation_footer = getattr(self, 'footer_snapshot', None) or capture_footer(self)
            self.footer_snapshot = None
            self.session.game.presentation_view = player_viewport(self)
            self.session.game.presentation_command = None
            self.session.game.presentation_cursor = None
            panel = member(self)
            if isinstance(panel, rec.Rec):
                panel = next((c for c in self.session.game.s.chars() if bytes(c.b) == bytes(panel.data)),
                             SimpleNamespace(b=panel.data, items=panel.items, effects=panel.effects))
            if panel is not None:
                self.session.game.presentation_panel = SimpleNamespace(b=bytes(panel.b),
                    items=tuple(bytes(i) for i in panel.items), effects=tuple(bytes(e) for e in panel.effects))
                who = next((i for i,c in enumerate(self.session.game.s.chars()) if c is panel), None)
                self.session.game.presentation_panel_casting = bool(who is not None and
                    (self.session.game.s.g['combat.records'][who][0] or getattr(self.session.game, 'presentation_casting', None)==who))
        if kind in ('MOVE', 'CAMP_MENU', 'SHOP_MENU', 'CREATE_MENU') and options and isinstance(answer, int):
            key = (kind, decision['info'].get('purpose'))
            if options[answer] == 'exit': self.menu_selection.pop(key, None)
            elif kind == 'CREATE_MENU':
                self.menu_selection[key]=('row',next(n for n,(i,_,_) in enumerate(menu_items(decision,self.session.game)) if i==answer))
            elif kind == 'SHOP_MENU' and (decision['info'].get('purpose') == 'treasure' or
                    not decision['info'].get('purpose') and decision['info'].get('place') in ('shop', 'temple', 'vault')):
                words = menu_items(decision, self.session.game)
                cursor = self.selected if decision['info'].get('purpose') == 'treasure' and options[answer] in ('char-up', 'char-down') else answer
                self.menu_selection[key] = ('word', next((n for n, (i, _, _) in enumerate(words) if i == cursor), 0))
            else: self.menu_selection[key] = options[answer]
            if options[answer] == 'save':
                selected = self.selected; self.selected = -1
                self.save_background = capture_background(self); self.selected = selected
            if kind == 'CREATE_MENU':
                selected = self.selected; self.selected = -1
                self.creation_background = capture_background(self); self.selected = selected
        if kind == 'CREATE_ROLL': self.creation_word = 0 if answer == options.index('reroll') else 1
        if decision['info'].get('purpose')=='view' and options[answer] in ('deposit money','drop money'):
            self.purse_background=capture_background(self)
        if decision['info'].get('purpose') in ('take money','deposit money'):
            selected=self.selected; self.selected=-1; self.coin_background=capture_background(self); self.selected=selected
        if decision['info'].get('purpose')=='take item': self.take_return=(self.take_start,self.selected)
        if kind == 'CREATE_ICON':
            chosen = options[answer]
            if decision['info'].get('field') == 'weapon' and chosen is not None:
                self.icon_body_chosen = True
            if chosen == 'keep' and getattr(self, 'icon_body_chosen', False):
                b = self.session.game.s.g['creation.pending'][0]
                identity = plus.identity(b)
                self.manual_bodies[identity] = b[0x154]
                if getattr(self, 'plus_settings', None):
                    try: self.plus_settings.remember_body(identity, b[0x154])
                    except OSError: self.error = 'Cannot save icon preference.'
        s = self.session.game.s if kind == 'MOVE' else None; before = s and (s.x, s.y, s.dir, bool(s.g.get('combat.active')))
        self.session.step(answer)
        if s and not before[3]:
            value = options[answer]
            if value == 'forward' and (s.x, s.y) != before[:2] or value in ('turn-left', 'turn-right') and s.dir != before[2]: self.emit(10)
        following=self.session.decision
        if following and following['info'].get('purpose') == 'take' and decision['info'].get('purpose') in ('take item','take money'):
            self.menu_selection[('SHOP_MENU','take')] = ('word', self.take_command if decision['info']['purpose']=='take item' else self.coin_command)
        if following and following['info'].get('purpose') == 'treasure' and decision['info'].get('purpose') == 'take':
            cursor = self.selected if keysym == 'Escape' else answer
            word = next((n for n,(i,_,_) in enumerate(menu_items(decision,self.session.game)) if i==cursor),0)
            self.menu_selection[('SHOP_MENU','treasure')] = ('word',word)
        if following and following['kind']=='SHOP_MENU' and not following['info'].get('purpose') and following['info'].get('place') in ('shop','temple','vault') and (decision['info'].get('purpose') in ('view','take money','take item') or decision['info'].get('money_picker')=='take'):
            words=menu_items(decision,self.session.game); cursor=self.selected if keysym=='Escape' else answer
            word=self.take_command if decision['info']['purpose']=='take item' else self.coin_command if decision['info']['purpose']=='take money' or decision['info'].get('money_picker')=='take' else next((n for n,(i,_,_) in enumerate(words) if i==cursor),0)
            self.menu_selection[('SHOP_MENU',None)]=('word',word)
        if decision['info'].get('purpose')=='quit to DOS' and options[answer]=='yes': self.quit_requested=True
        if decision['info'].get('purpose') == 'take item' and (self.session.decision or {}).get('info', {}).get('purpose') == 'treasure':
            self.menu_selection[('SHOP_MENU', 'treasure')] = ('word', self.take_command)
        if decision['info'].get('purpose') in ('appraise', 'appraisal'):
            words = menu_items(decision, self.session.game)
            cursor = self.selected if keysym == 'Escape' else answer
            word = next((n for n, (i, _, _) in enumerate(words) if i == cursor), 0)
            self.menu_selection[('SHOP_MENU', None)] = ('word', word)
        self.entry, self.page, self.selected = '', 0, 0
        following = self.session.decision
        if following and following['options']:
            value = self.menu_selection.get((following['kind'], following['info'].get('purpose')))
            if following['info'].get('purpose') in ('appraise', 'appraisal'):
                value = self.menu_selection.get(('SHOP_MENU', None))
            if isinstance(value, tuple) and value[0] == 'row':
                words=menu_items(following,self.session.game); self.selected=words[min(value[1],len(words)-1)][0]
            elif isinstance(value, tuple) and value[0] == 'word':
                words = menu_items(following, self.session.game)
                self.selected = words[value[1] if value[1] < len(words) else 0][0]
            elif value is not None and value in following['options']: self.selected = following['options'].index(value)
            if decision['info'].get('purpose') == 'magic' and following['info'].get('purpose') == 'rest duration':
                words = menu_items(decision, self.session.game)
                word = next(n for n, (i, _, _) in enumerate(words) if i == answer)
                self.selected = menu_items(following, self.session.game)[word][0]
            if kind in ('CAMP_MENU', 'SHOP_MENU', 'COMBAT_ACTION') and not decision['info'].get('purpose') and decision['info'].get('place')!='vault' and following['info'].get('purpose') == 'view':
                words = menu_items(following, self.session.game)
                self.selected = words[min(1, len(words)-1)][0]
        self.animation_start = time.monotonic()
        self.capture_text()
        stored = getattr(self.session.game, 'stored_character', None)
        if stored: self.session.game.stored_character = None
        if stored and self.session.game.slot is None:
            try:
                write_created_character(self.session.game, stored, self.files.root)
            except (OSError, ValueError) as error:
                self.files.active, self.files.message = True, str(error)
        if kind == 'CREATE_SLOT':
            slot = options[answer]
            files = self.session.game.s.g.get('save.' + slot) if slot is not None else None
            if files is not None:
                try:
                    write_slot_files(files, slot, self.files.root)
                except (OSError, ValueError) as error:
                    self.files.active, self.files.message = True, str(error)
        return True


def draw_frame(frame, assets, mode='explore'):
    if hasattr(assets, 'chrome') and assets.chrome(frame, mode): return
    if mode == 'party':
        frame.rect(8, 8, 304, 176, 0)
    for col in range(40):
        for row in ((0, 22) if mode == 'combat' else (0, 23) if mode == 'party' else (0, 16, 23)):
            frame.blit(col * 8, row * 8, assets.border(0x137))
    for row in range(1, 22 if mode == 'combat' else 23):
        if row == 16 and mode in ('explore', 'full'): continue
        sym = (0x134 if row == 1 else 0x136 if row == (21 if mode == 'combat' else 22) else 0x135) if mode in ('party', 'combat') else (
            0x134 if row in (1, 17) else 0x136 if row in (15, 22) else 0x135)
        for col in (0, 39):
            frame.blit(col * 8, row * 8, assets.border(sym))
        if mode == 'combat':
            frame.blit(176, row * 8, assets.border(0x134 if row == 1 else 0x136 if row == 21 else 0x135))
        elif mode == 'explore' and row < 16:
            frame.blit(128, row * 8, assets.border(sym))
    if mode != 'explore':
        return
    for col in range(2, 15):
        for row in (2, 14):
            frame.blit(col * 8, row * 8, assets.border(0x13B))
    for row in range(3, 14):
        for col in (2, 14):
            frame.blit(col * 8, row * 8, assets.border(0x138 if row == 3 else 0x13A if row == 13 else 0x139))


def string(offset, maximum=255):
    data = ssb_data.stexe()
    return data[offset + 1:offset + 1 + min(data[offset], maximum)].decode('cp437')


def member(controller):
    game, decision = controller.session.game, controller.session.decision
    info = decision['info']
    if info.get('record'):
        return rec.Rec(bytes.fromhex(info['record']))
    chars = game.s.chars()
    index = info.get('target') if info.get('action') == 'attack-ally' and not info.get('moving') else info.get('actor', info.get('caster', game.s.sel))
    if game.s.g.get('combat.active') and decision['kind'] == 'TARGET' and info.get('action') != 'move':
        target = cursor(controller)
        if isinstance(target, int):
            index = target
        elif isinstance(target, (tuple, list)):
            x, y = target
            index = game.s.g['combat.occupancy'][50 * y + x] - 1
    return chars[index] if 0 <= index < len(chars) else None


def sheet(frame, character, assets, retained=None):
    b = character.b
    draw_frame(frame, assets, 'party')
    frame.rect(8, 8, 304, 176, 0)
    for row in (8, 16, 20):
        for col in range(40):
            frame.blit(col * 8, row * 8, assets.border(0x137))
        for col in (0, 39):
            frame.blit(col * 8, (row - 1) * 8, assets.border(0x136))
            frame.blit(col * 8, (row + 1) * 8, assets.border(0x134))
    for row in range(9, 20):
        if row != 16: frame.blit(19 * 8, row * 8, assets.border(0x134 if row == 9 else 0x136 if row == 19 else 0x135))
    frame.text(1, 1, pstring(b, maximum=15), assets, 11)
    frame.text(20, 1, 'Status:', assets, 15)
    frame.text(27, 1, string(0xEAD + 13 * b[0x1A6], 12), assets, 10, 12)
    frame.text(1, 3, string(0xE52 + 7 * b[0x11F], 6), assets, 15)
    frame.text(8, 3, '%d years' % rec.rdw(b, 0x6E), assets, 15, 11)
    frame.text(20, 3, 'Hit Points', assets, 15)
    frame.text(31, 3, '%d/%d' % (b[0x1B5], b[0x70]), assets, 10, 8)
    frame.text(1, 4, string(0xDB9 + 17 * b[0x120], 16), assets, 15)
    frame.text(20, 4, string(0xD71 + 9 * b[0x6B], 8), assets, 15)
    class_name = string(0xB8B + 27 * b[0x6C], 26)
    old = next((i for i in range(7) if b[0x118 + i]), None) if b[0x6B] == 6 else None
    if old is not None and rec.dual(character):
        class_name += '/' + string(0xB8B + 27 * old, 26)
    frame.text(1, 5, class_name, assets, 15, 38)
    levels = [b[0x111 + i] + (b[0x118 + i] if old is None else 0)
              for i in range(7) if b[0x111 + i]]
    if old is not None and rec.dual(character):
        levels.append(b[0x118 + old])
    frame.text(1, 7, 'Level ' + '/'.join(map(str, levels)), assets, 15, 18)
    frame.text(24, 6, 'Experience:', assets, 15)
    xp = format(int.from_bytes(b[0x12C:0x130], 'little'), ',')
    frame.text(20 + (20 - len(xp)) // 2, 7, xp, assets, 10, 19)
    for i, label in enumerate(('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHA')):
        value = '%2d' % b[0x11 + i * 2]
        if i == 0 and b[0x11] == 18 and b[0x1C]:
            value += '(%02d)' % (b[0x1C] % 100)
        frame.text(1, 9 + i, label, assets, 10)
        frame.text(5, 9 + i, value, assets, 10, 13)
        if b[0x10+2*i] != b[0x11+2*i] or i == 0 and b[0x1C] != b[0x1D]:
            frame.text(12,9+i,'*',assets,10)
    row = 9
    for i in range(7):
        amount = rec.rdw(b, 0x103 + 2 * i)
        if amount:
            frame.text(20, row, string(0xE60 + 11 * i, 10), assets, 10)
            frame.text(38 - len(str(amount)), row, str(amount), assets, 10)
            row += 1
    for x, y, label, value in (
            (1, 17, 'Armor Class', '%3d' % (60 - b[0x1AB])),
            (1, 18, 'THAC0', '%3d' % (60 - b[0x1AA])),
            (20, 17, 'Encumbrance', '%5d' % rec.rdw(b, 0x19B)),
            (20, 18, 'Movement', '%5d' % b[0x1B6])):
        frame.text(x, y, label, assets, 15)
        frame.text(15 if x == 1 else 33, y, value, assets, 10)
    bonus = rec.sx(b[0x1B3])
    frame.text(1, 19, 'Damage', assets, 15)
    damage = '%dd%d%s' % (b[0x1AF], b[0x1B1], '%+d' % bonus if bonus else '')
    frame.text(11, 19, damage.rjust(7), assets, 10, 24)
    for row, slot in ((21, 0), (22, 2)):
        item = rec.readied(character)[slot]
        if item is not None:
            frame.text(1, row, item_name(item, (character,)), assets, 10, 38)
    if retained is not None:
        for y,row in enumerate(background_rows(retained, assets)):
            if 72<=y<128: frame.rows[y][:160]=row[:160]; frame.rows[y][312:]=row[312:]
            else: frame.rows[y][:]=row
        frame.rect(0,192,320,8,0)


def effect_lines(game):
    lines = [(' ',10)]
    for character in game.s.party:
        lines.append((pstring(character.b, maximum=15), 11))
        names = [string(0x2227 + 38 * e[0], 37) for e in character.effects]
        names = [name for name in names if name]
        lines.extend((' ' + name, 10) for name in names or ['<No Magical Effects>'])
        lines.append((' ', 10))
    return lines


def effects_bar(controller):
    start=getattr(controller,'effects_start',0); count=len(effect_lines(controller.session.game)); col=1; result=[]
    for word in (['Next'] if start+19<count else [])+(['Prev'] if start else [])+['Exit']:
        result.append((col,word,word[0].lower())); col+=len(word)+1
    return result


def spell_list(decision):
    return (decision and decision['kind'] == 'SPELL'
            and not decision['info'].get('prompt', '').startswith('Blast delay')
            and any(isinstance(v, (int, tuple, list)) for v in decision['options'] or ()))


def cast_list(decision):
    return bool(decision and ((decision['kind']=='LIST' and decision['info'].get('purpose')=='scribe') or
                (spell_list(decision) and decision['info'].get('purpose', '') in
                 ('', 'use scroll', 'view spells', 'memorize', 'scribe summary', 'learn at training'))))


def cast_height(controller):
    return 11 if controller.session.decision['info'].get('purpose') == 'memorize' else 18


def cast_bar(controller):
    start = getattr(controller, 'cast_start', 0)
    purpose = controller.session.decision['info'].get('purpose')
    viewing = purpose in ('view spells', 'scribe summary')
    action = {'memorize':'Memorize', 'scribe':'Scribe', 'learn at training':'Learn'}.get(purpose,'Cast')
    words = ([] if viewing else [action]) + (['Next'] if start + cast_height(controller) < len(cast_rows(controller)) else [])
    words += (['Prev'] if start else []) + ([] if purpose == 'learn at training' else ['Exit'])
    result, col = ([], 1) if viewing else ([(0, 'Choose Spell:', '')], 14)
    for word in words:
        result.append((col, word, word[0].lower())); col += len(word) + 1
    return result


def cast_rows(controller):
    decision = controller.session.decision
    character = member(controller)
    rows, level = [], None
    entries = list(enumerate(decision['options']))
    purpose = decision['info'].get('purpose'); grimoire = purpose == 'memorize'
    scribing = purpose in ('scribe', 'scribe summary')
    if scribing:
        order=[(n,sid&127) for n,it in enumerate(character.items) if it[0x2E] in (0x27,0x28) for sid in it[0x3C:0x3F] if sid&127]
        entries.sort(key=lambda pair: order.index(tuple(pair[1])) if isinstance(pair[1],(tuple,list)) else len(order))
    elif purpose == 'learn at training': pass
    elif grimoire:
        entries.sort(key=lambda pair: pair[1] if isinstance(pair[1], int) else 256)
    elif character is not None:
        memory = list(character.b[0x1E:0x69])
        entries.sort(key=lambda pair: memory.index(pair[1]) if isinstance(pair[1], int) and pair[1] in memory else 256 + pair[0])
    for i, value in entries:
        if not isinstance(value, (int, tuple, list)): continue
        sid = value if isinstance(value, int) else value[-1]
        new_level = magic.spell(sid)[1]
        if new_level != level:
            rows.append((None, string(0x9E1 + 4 * new_level) + string(0x9DA))); level = new_level
        count = list(character.b[0x1E:0x69]).count(sid) if not grimoire and purpose != 'learn at training' and character is not None and isinstance(value, int) else 1
        marked = scribing and any(raw == (sid|128) for raw in character.items[value[0]][0x3C:0x3F])
        rows.append((i, (' *' if marked else '  ') + magic.spell_name(sid) + (' (%d)' % count if count > 1 else '')))
    return rows


def draw_cast(frame, controller, assets):
    purpose = controller.session.decision['info'].get('purpose')
    grimoire = purpose == 'memorize'
    draw_frame(frame, assets, 'full' if grimoire else 'party')
    viewing = purpose in ('view spells', 'scribe summary')
    character = member(controller)
    if character is not None:
        name = pstring(character.b, maximum=15)
        frame.text(1, 1, name + "'s", assets, 11, 38)
        suffix = {'memorize':'in Grimoire', 'use scroll':'on Scroll', 'scribe':'on Scrolls', 'scribe summary':'to Scribe', 'learn at training':'to Choose'}.get(purpose,'in Memory')
        frame.text(len(name) + 4, 1, 'Spells ' + suffix, assets, 10, 35 - len(name))
        if grimoire: spell_slots(frame, character, assets)
    start = getattr(controller, 'cast_start', 0)
    for y, (index, text) in enumerate(cast_rows(controller)[start:start + cast_height(controller)], 5):
        selected = index is not None and index == controller.selected
        indent = len(text)-len(text.lstrip()) if selected else 0
        frame.text(1+indent, y, text[indent:], assets, 0 if selected else 13 if index is None else 10, 38-indent,
                   background=15 if selected else 0)
    for n, (col, word, key) in enumerate(cast_bar(controller)):
        selected = bool(key) and n - (0 if viewing else 1) == getattr(controller, 'cast_command', 0)
        frame.text(col, 24, word, assets, 0 if selected else 13 if not key else 10, 40 - col,
                   background=15 if selected else 0)
        if key: frame.text(col, 24, word[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)


def inventory_bar(controller):
    game, d = controller.session.game, controller.session.decision
    c = game.s.chars()[d['info'].get('actor', game.s.sel)]
    opts, available = shops.item_actions(game, c, d['info'].get('place', 'camp'))
    words = [label for value, label in (('ready','Ready'),('use','Use'),('trade','Trade'),('drop','Drop'),('deposit','Deposit'),
                                      ('halve','Halve'),('join','Join'),('sell','Sell'),('identify','Id')) if value in available]
    start = getattr(controller, 'item_start', 0)
    if start + 18 < len(d['options']) - 1: words.append('Next')
    if start: words.append('Prev')
    return words + ['Exit']


def draw_inventory(frame, controller, assets):
    game, d = controller.session.game, controller.session.decision
    c = game.s.chars()[d['info'].get('actor', game.s.sel)]; name = pstring(c.b, maximum=15)
    draw_frame(frame, assets, 'party')
    frame.text(1, 1, name + "'s", assets, 11); frame.text(len(name)+4, 1, 'Items', assets, 10)
    frame.text(1, 3, 'Ready Item', assets, 15)
    start = getattr(controller, 'item_start', 0)
    for i, index in enumerate(d['options'][start:start+18], start):
        if index is None: continue
        it = c.items[index]; selected = i == controller.selected
        text = ('Yes' if it[0x34] else 'No').ljust(5) + item_name(it, (c,))
        frame.text(2, 5+i-start, text, assets, 0 if selected else 10, 36, background=15 if selected else 0)
    col = 0
    for word in inventory_bar(controller):
        selected = word[0].lower() == getattr(controller, 'item_command', 'r')
        frame.text(col, 24, word, assets, 0 if selected else 10, 40-col, background=15 if selected else 0)
        frame.text(col, 24, word[0], assets, 0 if selected else 15, 1, background=15 if selected else 0); col += len(word)+1


def service_bar(controller):
    d = controller.session.decision; buying = d['info']['purpose'] == 'buy'
    count = list_geometry(d)[3]; words = ['Buy' if buying else 'Heal']
    if (controller.page + 1) * count < len(d['options']) - 1: words.append('Next')
    if controller.page: words.append('Prev')
    return words + ['Exit']


def draw_service_list(frame, controller, assets):
    game, d = controller.session.game, controller.session.decision; buying = d['info']['purpose'] == 'buy'
    draw_frame(frame, assets, 'party' if buying else 'full')
    if not buying: frame.text(1, 1, d['info'].get('prompt', shops.name(game.s.selc()) + ', how can we help you?'), assets, 15, 38)
    x, width, top, count = list_geometry(d); start = controller.page * count
    for index in range(start, min(start + count, len(d['options']) - 1)):
        value = d['options'][index]
        if buying:
            item = game.s.treasure_items[value]; cost = max(1, rec.rdw(item, 0x3A)); multiplier = game.s.r1[0x36D]
            price = str(cost * multiplier // 16 if multiplier in (1, 2, 4, 8, 16, 32, 64, 128) else cost)
            label = item_name(item, game.s.party).ljust(38)
            label = label[:38-len(price)] + price
        else: label = shops.SERVICES[value]
        selected = index == controller.selected
        frame.text(x, top + index - start, label, assets, 0 if selected else 10, width, background=15 if selected else 0)
    if not buying:
        for row, line in enumerate(wrapped_text(controller.text)[-6:], 17):
            frame.text(1, row, line, assets, getattr(game.vm, 'text_color', 15), 38)
    col = 7 if buying else 0
    if buying: frame.text(0, 24, 'Items:', assets, 13)
    for index, word in enumerate(service_bar(controller)):
        selected = index == getattr(controller, 'service_command', 0)
        frame.text(col, 24, word, assets, 0 if selected else 10, 40-col, background=15 if selected else 0)
        frame.text(col, 24, word[0], assets, 0 if selected else 15, 1, background=15 if selected else 0); col += len(word)+1


def player_label(value, text, decision):
    info = decision['info']
    if decision['kind'] == 'SPELL' and isinstance(value, (tuple, list)) and len(value) == 3:
        return magic.spell_name(value[2])
    if decision['kind'] == 'SPELL' and value in ('keep', 'replace'):
        return 'Yes' if value == 'keep' else 'No'
    if decision['kind'] == 'COMBAT_ACTION' and value in ('attack', 'aim'):
        return 'Aim'
    if info.get('action') == 'continue-battle':
        return 'Yes' if value == 'continue' else 'No'
    if info.get('purpose') == 'resting':
        return 'No' if value == 'continue' else 'Yes'
    if info.get('purpose') == 'rest duration' and value == 'minutes':
        return 'Mins'
    if info.get('purpose') == 'difficulty' and isinstance(value, int):
        return ('Novice', 'Squire', 'Veteran', 'Adept', 'Champion')[value]
    return text


def player_menu(decision):
    purpose = decision['info'].get('purpose', '')
    options = decision['options'] or ()
    words = None
    if purpose == 'order':
        return [(i, v[0], v.title()) for i, v in enumerate(options) if v not in shops.ROSTER]
    if purpose=='load game': return [(i,v.lower(),v) for i,v in enumerate(options) if v is not None and 'A'<=v<='J']
    if purpose in ('memorize confirm', 'scribe confirm'):
        return [(0, 'y', 'Yes'), (1, 'n', 'No')]
    if purpose == 'resting':
        return [(1, 'y', 'Yes'), (0, 'n', 'No')]
    if decision['kind'] == 'CREATE_MENU':
        order = ('create', 'drop', 'modify', 'train', 'change class', 'view', 'add', 'remove', 'load', 'save', 'begin', 'initialize', 'exit')
        return [(options.index(value), pstring(ssb_data.stexe(),0x6C0+42*n,40)[0].lower(), pstring(ssb_data.stexe(),0x6C0+42*n,40))
                for n,value in enumerate(order) if value in options]
    if decision['kind'] == 'SHOP_MENU' and not purpose and decision['info'].get('place') in ('shop', 'temple'):
        words = (('buy', 'Buy'), ('heal', 'Heal'), ('view', 'View'), ('take', 'Take'),
                 ('pool', 'Pool'), ('share', 'Share'), ('appraise', 'Appraise'), ('exit', 'Exit'))
    elif decision['kind']=='SHOP_MENU' and not purpose and decision['info'].get('place')=='vault':
        words=(('view','View'),('take','Take'),('pool','Pool'),('exit','Exit'))
    elif purpose == 'item':
        words = (('ready', 'Ready'), ('use', 'Use'), ('trade', 'Trade'), ('deposit', 'Deposit'),
                 ('drop', 'Drop'), ('halve', 'Halve'), ('join', 'Join'), ('sell', 'Sell'), ('identify', 'Id'), ('exit', 'Exit'))
        allowed = decision['info'].get('available', options)
        words = [(value, text) for value, text in words if value in allowed]
    elif purpose == 'view':
        words = (('items', 'Items'), ('spells', 'Spells'), ('trade', 'Trade'),
                 ('deposit money', 'Deposit' if decision['info'].get('place') == 'vault' else 'Drop'),
                 ('drop money', 'Drop'), ('heal', 'Heal'), ('cure', 'Cure'), ('exit', 'Exit'))
        allowed = decision['info']['available_text'].split('|') if 'available_text' in decision['info'] else decision['info'].get('available', options)
        words = [(value, text) for value, text in words if value in allowed]
    elif decision['info'].get('action') == 'done':
        words = (('guard', 'Guard'), ('delay', 'Delay'), ('quit', 'Quit'), ('bandage', 'Bandage'),
                 ('speed', 'Speed'), ('exit', 'Exit'))
    elif decision['kind'] == 'COMBAT_ACTION' and decision['info'].get('action') in ('attack-ally', 'flee-confirm'):
        words = (('yes', 'Yes'), ('no', 'No'))
    elif decision['kind'] == 'COMBAT_ACTION':
        words = (('move', 'Move'), ('view', 'View'), ('attack' if 'attack' in options else 'aim', 'Aim'), ('use', 'Use'),
                 ('cast', 'Cast'), ('quick', 'Quick'), ('done', 'Done'))
    elif decision['kind'] == 'CAMP_MENU' and purpose in ('', 'magic', 'rest duration'):
        words = ({'': (('save', 'Save'), ('view', 'View'), ('magic', 'Magic'), ('rest', 'Rest'),
                       ('alter', 'Alter'), ('fix', 'Fix'), ('exit', 'Exit')),
                  'magic': (('cast', 'Cast'), ('memorize', 'Memorize'), ('scribe', 'Scribe'),
                            ('display', 'Display'), ('rest', 'Rest'), ('exit', 'Exit')),
                  'rest duration': (('rest', 'Rest'), ('days', 'Days'), ('hours', 'Hours'), ('minutes', 'Mins'),
                                    ('add', 'Add'), ('subtract', 'Subtract'), ('exit', 'Exit'))}[purpose])
    if words is not None:
        result=[]; col=0
        for value,text in words:
            if value not in options: continue
            if purpose=='view': text=text[:max(0,40-col)]
            if text: result.append((options.index(value),text[0].lower(),text)); col+=len(text)+1
        return result
    return None


def choices(frame, controller, assets):
    col = 0
    items = menu_items(controller.session.decision, controller.session.game)
    pages = menu_pages(items)
    chosen = controller.selected if any(i == controller.selected for i, _, _ in items) else items[0][0]
    for index, key, label in pages[min(controller.page, len(pages) - 1)]:
        selected = index == chosen
        frame.text(col, 24, label, assets, 0 if selected else 10, 40 - col, background=15 if selected else 0)
        offset = label.lower().find(key)
        if offset >= 0:
            frame.text(col + offset, 24, label[offset], assets, 0 if selected else 15, 1, background=15 if selected else 0)
        col += len(label) + 1


def spell_slots(frame, character, assets):
    colour = 12 if not character.b[0x1A7] else 14 if character.b[0x1A8] else 11
    draw_name_notice(frame, assets, (0, shops.name(character), '', colour, False, 17))
    row = 18
    for cls, label in ((0, '    Cleric Spells:'), (1, '     Druid Spells:'), (3, 'Magic-User Spells:')):
        slots = character.b[0x132 + 7 * cls:0x139 + 7 * cls]
        if not any(slots):
            continue
        frame.text(1, row, label, assets, 10)
        counts = [0] * 7
        for sid in character.b[0x1E:0x69]:
            if 1 <= sid & 127 <= 117:
                kind, level = magic.spell(sid & 127)[:2]
                if kind == cls and 1 <= level <= 7:
                    counts[level - 1] += 1
        for level, cap in enumerate(slots):
            frame.text(20 + level * 3, row, str(max(0, cap - counts[level])) if cap else ' ', assets, 10, 2)
        row += 1


def icon_bar(controller):
    field = controller.session.decision['info'].get('field'); phase = getattr(controller, 'icon_phase', 'root')
    words = ('Yes No' if phase == 'confirm' else
             ('Small' if controller.icon_value == 2 else 'Large') + ' Keep Exit' if field == 'size' else
             'Next Prev Keep Exit' if field in ('head', 'weapon', 'color') else
             'Weapon Body ' + ('Face' if controller.icon_channel else 'Hair') + ' Shield Arm Leg Exit' if field == 'part' else
             'Head Weapon Exit' if phase == 'parts' else 'Parts 1st-color 2nd-color Size Exit')
    return [(i, word[0].lower(), word) for i, word in enumerate(words.split())]


def icon_commit(controller, value):
    word = controller.selected
    controller.selected = controller.session.decision['options'].index(value); controller.icon_submitting = True
    result = controller.key('Return')
    if controller.session.decision and controller.session.decision['kind'] == 'CREATE_ICON':
        controller.selected = word if word < len(icon_bar(controller)) else 0
    return result


def icon_key(controller, keysym, char):
    decision = controller.session.decision; field = decision['info'].get('field')
    phase = getattr(controller, 'icon_phase', 'root'); bar = icon_bar(controller)
    if keysym in ('Left', 'Right'):
        controller.selected = (controller.selected + (-1 if keysym == 'Left' else 1)) % len(bar); return False
    key = 'e' if keysym == 'Escape' else bar[min(controller.selected, len(bar)-1)][1] if keysym in ('Return', 'KP_Enter') else char.lower()
    if key not in [k for _, k, _ in bar]: return False
    controller.selected = next(i for i,k,_ in bar if k == key)
    if phase == 'confirm':
        if key == 'y':
            controller.icon_background = capture_background(controller, render_creation)
            return icon_commit(controller, 'keep')
        controller.icon_phase, controller.selected = 'root', 0; return False
    if field in ('head', 'weapon', 'size', 'color'):
        if key in ('n', 'p'): controller.icon_value = (controller.icon_value + (1 if key == 'n' else -1)) % (14 if field == 'head' else 32 if field == 'weapon' else 16)
        elif key in ('s', 'l'): controller.icon_value = 1 if key == 's' else 2
        elif key in ('k', 'e'):
            controller.icon_phase = 'parts' if field in ('head', 'weapon') else 'root'
            value = controller.icon_value if key == 'k' else None
            result = icon_commit(controller, value)
            if field == 'color':
                result = icon_commit(controller, 'color')
            return result
        return False
    if field == 'part':
        if key == 'e': controller.icon_phase = 'root'; return icon_commit(controller, None)
        controller.icon_part = {'w': 5, 'b': 0, 'h': 3, 'f': 3, 's': 4, 'a': 1, 'l': 2}[key]
        icon_commit(controller, controller.icon_part)
        return icon_commit(controller, controller.icon_channel)
    if phase == 'parts':
        if key == 'e': controller.icon_phase = 'root'; return False
        return icon_commit(controller, 'head' if key == 'h' else 'weapon')
    if key == 'p': controller.icon_phase = 'parts'; return False
    if key in ('1', '2'):
        controller.icon_channel = int(key)-1; return icon_commit(controller, 'color')
    if key == 's': return icon_commit(controller, 'size')
    controller.icon_phase, controller.selected = 'confirm', 0; return False


def modify_commit(controller, value):
    options = controller.session.decision['options']; word = controller.selected
    if options is None: controller.entry = value
    else: controller.selected = options.index(value)
    controller.modify_submitting = True
    try: result = controller.key('Return')
    finally: controller.modify_submitting = False
    if controller.session.decision and controller.session.decision['kind'] == 'CREATE_MODIFY':
        controller.selected = word
        b=member(controller).b
        controller.modify_marks.update(i for i in range(6) if b[0x10+2*i]!=b[0x11+2*i] or i==0 and b[0x1C]!=b[0x1D])
    return result


def modify_key(controller, keysym, char):
    field = controller.modify_field; c = member(controller)
    if keysym == 'Escape': return modify_commit(controller, 'cancel')
    if keysym in ('Up', 'Down'):
        if field == 6: controller.modify_name_visited = True
        controller.modify_field = (field + (-1 if keysym == 'Up' else 1)) % 8; return False
    if field == 6:
        name = pstring(c.b, maximum=15); cursor = min(controller.modify_cursor, len(name)-1); word = controller.selected
        if keysym == 'Return': controller.modify_field = 7; controller.modify_name_visited = True; return False
        if char in ('A', 'S'): controller.modify_cursor = (cursor + (1 if char == 'A' else -1)) % len(name); return False
        if keysym == 'Delete' and len(name) > 1:
            name = name[:cursor] + name[cursor+1:]; controller.modify_cursor = min(cursor, len(name)-1)
        elif keysym == 'BackSpace' and cursor > 0:
            name = name[:cursor-1] + name[cursor:]; controller.modify_cursor = min(cursor, len(name)-1)
        elif len(char) == 1 and ' ' <= char <= 'z':
            name = (name[:cursor] + char + name[cursor+1:])[:15]; controller.modify_cursor = min(14, cursor+1)
            if controller.modify_cursor >= len(name): name += ' '
        else: return False
        modify_commit(controller, 'name'); result = modify_commit(controller, name); controller.selected = word; return result
    words = [(1, 'a'), (2, 's'), (0, 'k'), (4, 'e')]
    if keysym in ('Left', 'Right'):
        pos = next((n for n,(i,_) in enumerate(words) if i == controller.selected), 0)
        controller.selected = words[(pos + (-1 if keysym == 'Left' else 1)) % 4][0]; return False
    key = 'e' if keysym == 'Escape' else next((k for i,k in words if i == controller.selected),'a') if keysym == 'Return' else char.lower()
    if key in ('k', 'e'): return modify_commit(controller, 'keep' if key == 'k' else 'cancel')
    if key not in ('a', 's'): return False
    controller.selected = 1 if key == 'a' else 2
    current = c.b[0x11 + 2*field] if field < 6 else c.b[0x70]
    percent = c.b[0x1C]
    modify_commit(controller, 'ability' if field < 6 else 'hp')
    if field < 6: modify_commit(controller, field)
    delta = 0 if field == 0 and key == 's' and percent else 1 if key == 'a' else -1
    values = controller.session.decision['options']; value = max(values[0], min(values[-1], current + delta))
    result = modify_commit(controller, value)
    decision = controller.session.decision
    if decision and decision['kind'] == 'CREATE_ABILITY' and decision['info'].get('ability') == 'exceptional strength':
        percent += (1 if key == 'a' else -1) if current == 18 else 0
        result = modify_commit(controller, max(0, min(decision['options'][-1], percent)))
    controller.selected = 1 if key == 'a' else 2
    return result


def add_bar(controller):
    count=sum(v is not None for v in controller.session.decision['options']); start=getattr(controller,'add_start',0)
    words=['Add ']+(['Next'] if start+21<count else [])+(['Prev'] if start else [])+['Exit']
    result=[]; col=17
    for word in words: result.append((col,word)); col+=len(word)+1
    return result


def render_creation(controller, assets):
    game, decision = controller.session.game, controller.session.decision
    from .vga import assets_for
    assets = assets_for(controller, assets)
    kind = decision['kind']; frame = new_frame(assets)
    if decision['info'].get('purpose')=='load game':
        parent=getattr(controller,'creation_background',None)
        if parent is not None: frame.rows=[row[:] for row in background_rows(parent, assets)]
        frame.rect(0,192,320,8,0); frame.text(0,24,'Load Which Game: ',assets,13)
        for col,(index,_,label) in enumerate(menu_items(decision,game)):
            selected=index==controller.selected
            frame.text(17+col*2,24,label,assets,0 if selected else 15,background=15 if selected else 0)
        return frame
    if kind == 'CREATE_ADD' and getattr(controller, 'add_source', False):
        draw_frame(frame, assets, 'party'); frame.text(0, 24, 'Add from where? ', assets, 13)
        for index, col, word in ((0, 16, 'Secret'), (1, 23, 'Curse'), (2, 29, 'Exit')):
            selected = controller.selected == index
            frame.text(col, 24, word, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, word[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
        return frame
    if kind == 'CREATE_ADD':
        draw_frame(frame,assets,'party')
        items=sorted((item for item in menu_items(decision,game) if decision['options'][item[0]] is not None),key=lambda item:item[2].removeprefix('* '))
        start=getattr(controller,'add_start',0)
        for row,(index,_,label) in enumerate(items[start:start+21],2):
            selected=index==controller.selected
            frame.text(1,row,label.rstrip(),assets,0 if selected else 10,38,background=15 if selected else 0)
        frame.text(0,24,'Add a character: ',assets,13)
        for number,(col,word) in enumerate(add_bar(controller)):
            selected=number==getattr(controller,'add_command',0)
            frame.text(col,24,word,assets,0 if selected else 10,background=15 if selected else 0)
            frame.text(col,24,word[0],assets,0 if selected else 15,1,background=15 if selected else 0)
        return frame
    if kind == 'CREATE_MODIFY':
        character = member(controller); b = character.b; field = controller.modify_field
        sheet(frame, character, assets)
        for marked in controller.modify_marks: frame.text(12,9+marked,'*',assets,10)
        if getattr(controller, 'modify_name_visited', False): frame.text(1, 1, pstring(b, maximum=15), assets, 10)
        frame.text(31,3,str(b[0x1B5]),assets,13 if field==7 else 10)
        if field < 6:
            value = '%2d' % b[0x11 + 2*field]
            if field == 0 and b[0x11] == 18 and b[0x1C]: value += '(%02d)' % (b[0x1C] % 100)
            frame.text(5, 9+field, value, assets, 13, 7)
            if b[0x10+2*field] != b[0x11+2*field] or field == 0 and b[0x1C] != b[0x1D]: frame.text(12,9+field,'*',assets,13)
        elif field == 6:
            name = pstring(b, maximum=15); cursor = min(controller.modify_cursor, len(name))
            frame.rect(8, 8, 120, 8, 0); frame.text(1, 1, name, assets, 13)
            frame.text(1+cursor, 1, name[cursor] if cursor < len(name) and name[cursor] != ' ' else '%', assets, 15, 1)
        frame.text(0, 24, 'Modify: ', assets, 13); col = 8
        for index, label in ((1, 'Add'), (2, 'Subtract'), (0, 'Keep'), (4, 'Exit')):
            selected = controller.selected == index
            frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0); col += len(label)+1
        return frame
    picks = ('CREATE_RACE', 'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT')
    if kind in picks:
        draw_frame(frame, assets, 'party')
        dual = decision['info'].get('purpose') == 'dual class'
        frame.text(1, 2, 'Pick New Class' if dual else ('Pick Race', 'Pick Gender', 'Pick Class', 'Pick Alignment')[picks.index(kind)], assets, 13)
        for row, (index, _, label) in enumerate(menu_items(decision, game), 3):
            selected = index == controller.selected
            frame.text(1 if dual else 3, row, label, assets, 0 if selected else 10, 38 if dual else 36, background=15 if selected else 0)
        frame.text(0, 24, 'Select', assets, 0, background=15)
        frame.text(7, 24, 'Exit', assets, 10); frame.text(7, 24, 'E', assets, 15)
        return frame
    if kind in ('CREATE_REMOVE', 'CREATE_EXIT') and hasattr(controller, 'creation_background'):
        for y, row in enumerate(background_rows(controller.creation_background, assets)): frame.rows[y][:] = row
        info = decision['info']; prefix = (info.get('prompt', '') if kind == 'CREATE_EXIT' else
                'Are you sure? ' if info.get('confirmation') else
                'Drop ' + info['character'] + ' forever? ')
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, prefix, assets, 14)
        col = len(prefix)
        for index, key, label in menu_items(decision, game):
            selected = index == controller.selected
            frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0); col += len(label)+1
        return frame
    pending = game.s.g.get('creation.pending')
    if kind == 'CREATE_ICON' and pending:
        draw_frame(frame, assets, 'party')
        new = bytearray(pending[0]); field = decision['info'].get('field')
        if field in ('head', 'weapon', 'size'): new[{'head': 0x153, 'weapon': 0x154, 'size': 0x156}[field]] = controller.icon_value
        elif field == 'color':
            o, shift = 0x157 + controller.icon_part, 4 * controller.icon_channel
            new[o] = new[o] & (0x0F if shift else 0xF0) | controller.icon_value << shift
        for y, b in ((56, controller.icon_old), (104, new)):
            for x, pose in ((32, 0), (104, 1)):
                frame.blit(x, y, art.picture('COMSPR', 25)[2][0])
                pixels, palette = party_icon(b[0x153], b[0x154], b[0x156], tuple(b[0x157:0x15D]), pose)
                frame.blit(x, y, pixels, colours=palette, transparent=0)
        for row, label in ((6, 'old'), (12, 'new')): frame.text(8, row, label, assets, 15)
        for row in (10, 16): frame.text(3, row, 'ready   action', assets, 15)
        prefix = 'Is this icon ok? ' if getattr(controller, 'icon_phase', '') == 'confirm' else ''
        if prefix: frame.text(0, 24, prefix, assets, 13)
        col = len(prefix)
        for index, key, label in icon_bar(controller):
            selected = index == controller.selected
            frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
            col += len(label) + 1
        return frame
    if kind in ('CREATE_ROLL', 'CREATE_NAME', 'CREATE_SAVE') and pending:
        from sm.titles.ssb.units import creation
        if kind == 'CREATE_SAVE' and hasattr(controller, 'icon_background'):
            for y, row in enumerate(background_rows(controller.icon_background, assets)): frame.rows[y][:] = row
            frame.rect(0, 192, 320, 8, 0)
        else: sheet(frame, creation.from_image(pending), assets)
        if kind == 'CREATE_NAME':
            frame.text(0, 24, 'Character name: ', assets, 13)
            frame.text(17, 24, controller.entry, assets, 15, 15)
        else:
            prefix = 'Reroll stats? ' if kind == 'CREATE_ROLL' else 'Save ' + decision['info']['character'] + '? '
            frame.text(0, 24, prefix, assets, 13)
            for index, col, label in ((1 if kind == 'CREATE_ROLL' else 0, len(prefix), 'Yes'),
                                       (0 if kind == 'CREATE_ROLL' else 1, len(prefix)+4, 'No')):
                selected = controller.selected == index
                frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
                frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
        return frame
    return None


def coin_rows(controller):
    d=controller.session.decision; indices=[i for i,v in enumerate(d['options']) if v is not None]
    return indices[::-1] if d['info'].get('purpose')=='take money' else indices


def take_bar(controller):
    start=getattr(controller,'take_start',0); count=len(controller.session.decision['options'])-1
    words=['Take']+(['Next'] if start+22<count else [])+(['Prev'] if start else [])+['Exit']
    result=[]; col=7
    for word in words: result.append((col,word,word[0].lower())); col+=len(word)+1
    return result


def render_player(controller, assets):
    from .vga import assets_for
    assets = assets_for(controller, assets)
    game, decision = controller.session.game, controller.session.decision
    if not decision:
        return None
    if decision['kind'].startswith('CREATE_'):
        creation_frame = render_creation(controller, assets)
        if creation_frame is not None: return creation_frame
    purpose = decision['info'].get('purpose')
    if purpose=='take item':
        frame=new_frame(assets); draw_frame(frame,assets,'party'); start=getattr(controller,'take_start',0)
        for row,index in enumerate(range(start,min(start+22,len(decision['options'])-1)),1):
            it=game.s.treasure_items[decision['options'][index]]; selected=index==controller.selected
            frame.text(1,row,item_name(it,game.s.party),assets,0 if selected else 10,38,background=15 if selected else 0)
        frame.text(0,24,'Items: ',assets,13)
        for n,(col,word,key) in enumerate(take_bar(controller)):
            selected=n==getattr(controller,'take_command',0)
            frame.text(col,24,word,assets,0 if selected else 10,background=15 if selected else 0)
            frame.text(col,24,word[0],assets,0 if selected else 15,1,background=15 if selected else 0)
        return frame
    if purpose == 'combat defeat':
        frame = new_frame(assets); draw_frame(frame, assets, 'party')
        for row, line in enumerate(wrapped_text('The monsters rejoice for the party has been destroyed', 36), 5):
            frame.text(2, row, line, assets, 10, 36)
        frame.text(0, 24, decision['options'][0], assets, 13)
        return frame
    if purpose == 'npc share':
        frame = new_frame(assets); draw_frame(frame, assets, 'party')
        for n, text in enumerate(decision['info'].get('lines', ())):
            for row, line in enumerate(wrapped_text(text, 30), 5 + 2*n): frame.text(5, row, line, assets, 10, 30)
        frame.text(0, 24, decision['options'][0], assets, 0, background=15)
        return frame
    if purpose == 'combat result':
        frame = new_frame(assets); draw_frame(frame, assets, 'party'); info = decision['info']
        if info.get('outcome'): frame.text(1, 3, 'The party has '+info['outcome']+'.', assets, 10)
        if not info.get('no_xp'):
            frame.text(1, 5, 'Each character receives '+str(info['experience']), assets, 10)
            frame.text(1, 7, 'experience points.', assets, 10)
        frame.text(1, 10, string(0x310)+('' if info['treasure'] else 'no ')+string(0x326), assets, 10)
        frame.text(0, 24, decision['options'][0], assets, 0, background=15)
        return frame
    if purpose in ('take money','deposit money'):
        taking=purpose=='take money'; frame=new_frame(assets)
        if taking: draw_frame(frame,assets,'party')
        else: sheet(frame,member(controller),assets,getattr(controller,'purse_background',None))
        values=game.s.treasure_money if taking else shops.coins(member(controller))
        for row,index in enumerate(coin_rows(controller),2 if taking else 9):
            coin=decision['options'][index]; selected=index==controller.selected; amount=str(values[coin]); label=shops.COINS[coin]
            label=label+' '+amount if taking else label.ljust(18-len(amount))+amount
            frame.text(2 if taking else 20,row,label,assets,0 if selected else 10,14 if taking else 19,background=15 if selected else 0)
        frame.text(0,24,'Select type of coin ',assets,13)
        for command,col,word in ((0,20,'Select'),(1,27,'Exit')):
            col+=int(not taking)
            selected=command==getattr(controller,'coin_command',0)
            frame.text(col,24,word,assets,0 if selected else 10,background=15 if selected else 0)
            frame.text(col,24,word[0],assets,0 if selected else 15,1,background=15 if selected else 0)
        return frame
    if decision['info'].get('money_picker') in ('take','deposit') and hasattr(controller,'coin_background'):
        frame=new_frame(assets); frame.rows=[row[:] for row in background_rows(controller.coin_background, assets)]
        frame.rect(0,192,320,8,0); prompt=decision['info']['prompt']
        frame.text(0,24,prompt,assets,10); frame.text(len(prompt),24,controller.entry,assets,15)
        return frame
    if purpose in ('drop item','confirm sale','confirm identification','lose scribe scroll','use refusal') and hasattr(controller, 'inventory_background'):
        frame = new_frame(assets)
        for y, row in enumerate(background_rows(controller.inventory_background, assets)): frame.rows[y][:] = row
        frame.rect(8, 168, 304, 16, 0)
        notice=('Your ' + decision['info']['item_name'] + ' will be gone forever') if purpose=='drop item' else decision['info'].get('offer', '')
        for row, line in enumerate(wrapped_text(notice), 21):
            if row <= 22: frame.text(1, row, line, assets, 14, 38)
        if purpose == 'lose scribe scroll': frame.text(1, 21, decision['info']['name'], assets, 11, 15)
        if purpose == 'use refusal':
            frame.rect(8, 136, 304, 48, 0); frame.text(1, 19, 'That Item', assets, 10, 38); frame.text(1, 20, decision['info']['text'], assets, 10, 38)
        frame.rect(0, 192, 320, 8, 0); prefix = decision['info']['prompt']; frame.text(0, 24, prefix, assets, 13)
        yes=int(purpose!='confirm identification')
        for index, col, label in ((yes,len(prefix),'Yes'),(1-yes,len(prefix)+4,'No')):
            selected = index == controller.selected
            frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
        return frame
    if purpose == 'scribe confirm':
        character = member(controller)
        marks = [(n,raw&127) for n,it in enumerate(character.items) if it[0x2E] in (0x27,0x28)
                 for raw in it[0x3C:0x3F] if 128 < raw <= 245]
        picker = dict(kind='SPELL',options=['exit']+marks,info=dict(purpose='scribe summary',caster=decision['info']['caster']))
        view = SimpleNamespace(session=SimpleNamespace(game=game,decision=picker),selected=-1,
                               cast_start=getattr(controller,'cast_start',0),cast_command=-1)
        frame = new_frame(assets); draw_cast(frame,view,assets); frame.rect(0,192,320,8,0)
        prefix=decision['info']['prompt']; frame.text(0,24,prefix,assets,14); col=len(prefix)
        for i,key,label in menu_items(decision,game):
            selected=controller.selected==i
            frame.text(col,24,label,assets,0 if selected else 10,background=15 if selected else 0)
            frame.text(col,24,label[0],assets,0 if selected else 15,1,background=15 if selected else 0); col+=len(label)+1
        return frame
    if purpose in ('memorize summary', 'memorize confirm'):
        frame = new_frame(assets); draw_frame(frame, assets, 'party')
        character = member(controller); name = pstring(character.b, maximum=15)
        frame.text(1, 1, name + "'s", assets, 11, 38)
        frame.text(len(name)+4, 1, 'Spells to Memorize', assets, 10, 35-len(name))
        marks = [n & 127 for n in character.b[0x1E:0x69] if 128 < n <= 245]
        row, level = 5, None
        for sid in sorted(set(marks)):
            current = magic.spell(sid)[1]
            if current != level:
                frame.text(1,row,string(0x9E1+4*current)+string(0x9DA),assets,13,38); row += 1; level = current
            selected = purpose == 'memorize summary' and row == 6
            label = '*' + magic.spell_name(sid) + (' (%d)' % marks.count(sid) if marks.count(sid)>1 else '')
            if row < 23: frame.text(2,row,label,assets,0 if selected else 10,37,background=15 if selected else 0)
            row += 1
        if purpose == 'memorize summary': frame.text(1,24,'Exit',assets,0,background=15)
        else:
            prefix = decision['info']['prompt']; frame.text(0,24,prefix,assets,14); col=len(prefix)
            for i, key, label in menu_items(decision,game):
                selected = controller.selected == i
                frame.text(col,24,label,assets,0 if selected else 10,background=15 if selected else 0)
                frame.text(col,24,label[0],assets,0 if selected else 15,1,background=15 if selected else 0); col += len(label)+1
        return frame
    if purpose == 'cast refusal':
        character = member(controller)
        options = sorted({sid for sid in character.b[0x1E:0x69] if 0 < sid <= 117 and magic.can_cast(character, sid)}) + ['cancel']
        picker = dict(kind='SPELL', options=options, info=dict(caster=decision['info']['caster']))
        view = SimpleNamespace(session=SimpleNamespace(game=game, decision=picker), selected=-1,
                               cast_start=getattr(controller, 'cast_start', 0), cast_command=-1)
        frame = new_frame(assets); draw_cast(frame, view, assets)
        frame.text(1, 19, magic.spell_name(decision['info']['spell']), assets, 10, 38)
        frame.text(1, 20, "Can't be cast here...", assets, 10, 38)
        frame.rect(0, 192, 320, 8, 0)
        frame.text(0, 24, 'Lose it? ', assets, 13)
        for index, (col, word) in enumerate(((9, 'Yes'), (13, 'No'))):
            selected = controller.selected == index
            frame.text(col, 24, word, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, word[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
        return frame
    if is_roster(decision) and game.s.mode == 0 and hasattr(controller, 'creation_background'):
        frame = new_frame(assets)
        for y, row in enumerate(background_rows(controller.creation_background, assets)): frame.rows[y][:] = row
        for index, character in enumerate(game.s.party[:11]):
            frame.rect(8, (4+index)*8, 120, 8, 0)
            frame.text(1, 4+index, pstring(character.b, maximum=15), assets,
                       15 if index == controller.roster_selected() else 11, 15)
        frame.rect(0, 192, 320, 8, 0)
        frame.text(0, 24, 'Pick Character ', assets, 13)
        frame.text(15, 24, 'Select', assets, 0, background=15)
        frame.text(22, 24, 'Exit', assets, 10); frame.text(22, 24, 'E', assets, 15)
        return frame
    if purpose in ('buy', 'temple service'):
        frame = new_frame(assets); draw_service_list(frame, controller, assets); return frame
    if purpose == 'items':
        frame = new_frame(assets); draw_inventory(frame, controller, assets); return frame
    if purpose == 'view':
        frame = new_frame(assets)
        character = member(controller)
        if character is not None:
            live = next((c for c in game.s.chars() if bytes(c.b).hex() == decision['info'].get('record')), character)
            sheet(frame, live, assets,getattr(controller,'purse_background',None))
        choices(frame, controller, assets)
        return frame
    if purpose == 'effects':
        frame = new_frame(assets); draw_frame(frame,assets,'party')
        lines=effect_lines(game); start=getattr(controller,'effects_start',0)
        for index,(line,colour) in enumerate(lines[start:start+19],start):
            selected=index==getattr(controller,'effects_selected',0)
            indent=min(len(line)-1,len(line)-len(line.lstrip(' '))) if selected else 0
            frame.text(1+indent,4+index-start,(line.strip(' ') or ' ') if selected else line,assets,
                       0 if selected else colour,38-indent,background=15 if selected else 0)
        for number,(col,word,key) in enumerate(effects_bar(controller)):
            selected=number==getattr(controller,'effects_command',0)
            frame.text(col,24,word,assets,0 if selected else 10,background=15 if selected else 0)
            frame.text(col,24,word[0],assets,0 if selected else 15,1,background=15 if selected else 0)
        return frame
    if spell_list(decision) or cast_list(decision):
        frame = new_frame(assets)
        if cast_list(decision):
            draw_cast(frame, controller, assets)
            return frame
        draw_frame(frame, assets, 'full')
        draw_list(frame, controller, menu_items(decision, game), assets)
        character = member(controller)
        if character is not None:
            title = pstring(character.b, maximum=15) + "'s Spells"
            frame.rect(8, 8, 304, 8, 0)
            frame.text(1, 1, title, assets, 15, 38)
            if purpose == 'memorize':
                spell_slots(frame, character, assets)
        return frame
    if not game.s.g.get('combat.active'):
        return None
    frame = new_frame(assets)
    draw_frame(frame, assets, 'combat')
    draw_battle(frame, controller, assets)
    frame.rect(184, 8, 128, 168, 0)
    character = member(controller)
    event = getattr(controller, 'presentation_event', None)
    if event and event.get('panel_clear'): character = None
    elif event and event.get('panel') is not None: character = event['panel']
    elif decision['info'].get('action') == 'continue-battle': character = getattr(game,'presentation_panel',None) or character
    if character is not None:
        b = character.b
        frame.text(23, 1, pstring(b, maximum=15), assets, 12 if not b[0x1A7] else 14 if b[0x1A8] else 11, 16)
        frame.text(23, 3, 'Hitpoints', assets, 10)
        frame.text(33, 3, str(b[0x1B5]), assets, 14 if b[0x1B5] < b[0x70] else 10, 3)
        frame.text(23, 5, 'AC %d' % (60 - b[0x1AB]), assets, 10, 16)
        weapon = rec.readied(character)[0]
        if weapon is not None:
            for row, line in enumerate(textwrap.wrap(item_name(weapon, (event or {}).get('panel_party') or game.s.party), 16)[:2], 7):
                frame.text(23, row, line, assets, 10, 16)
        actor = next((i for i,c in enumerate(game.s.chars()) if c is character),actor_index(game,decision))
        status = (string(0xEAD + 13 * b[0x1A6], 12) if not b[0x1A7] else
                  '(Helpless)' if any(rec.has_effect(character, e) for e in (0x1F, 0x33, 0x34, 0x35)) else
                  '(Casting)' if ((event or {}).get('panel_casting', False) if event and event.get('panel') is not None
                                  else game.s.g['combat.records'][actor][0] or game.s.g.get('casting') == actor) else '')
        frame.text(23, 9, status, assets, 15, 16)
    if decision['kind'] == 'TARGET':
        if decision['info'].get('action') == 'move':
            for col, text, hotkey in target_bar(controller):
                frame.text(col, 24, text, assets, 0 if hotkey else 13, 40 - col,
                           background=15 if hotkey else 0)
            return frame
        position = cursor(controller)
        if decision['info'].get('spell'):
            frame.text(0, 23, 'Spell:' + magic.spell_name(decision['info']['spell']), assets, 10, 40)
        elif position:
            origin = target_position(game, actor_index(game, decision))
            dx, dy = abs(position[0] - origin[0]), abs(position[1] - origin[1])
            frame.text(0, 23, 'Range = %d' % (max(dx, dy) + min(dx, dy) // 2), assets, 10, 40)
        for col, text, hotkey in target_bar(controller):
            selected = hotkey and (manual(controller) or hotkey == getattr(controller, 'aim_command', 'm'))
            frame.text(col, 24, text, assets, 0 if selected else 10 if hotkey else 13, 40 - col, background=15 if selected else 0)
            if hotkey:
                frame.text(col, 24, text[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
    else:
        lines = []
        for paragraph in controller.text.rstrip().splitlines():
            lines.extend(textwrap.wrap(paragraph, 16) or [''])
        for row, line in enumerate(lines[-12:], 10):
            frame.text(23, row, line, assets, 10, 16)
        items = menu_items(decision, game)
        if decision['options'] is None:
            draw_input(frame, controller, assets)
        elif compact_menu(items, decision):
            choices(frame, controller, assets)
        elif items:
            draw_list(frame, controller, items, assets, combat=True)
        if decision['info'].get('action') == 'continue-battle':
            frame.rect(184, 80, 128, 96, 0)
            frame.rect(0,184,320,16,0)
            frame.text(0,24,'Continue Battle:',assets,13,16)
            yes=controller.selected==0
            frame.text(16,24,'Yes',assets,0 if yes else 10,3,background=15 if yes else 0)
            if not yes: frame.text(16,24,'Y',assets,15,1)
            frame.text(20,24,'No',assets,10 if yes else 0,2,background=0 if yes else 15)
            if yes: frame.text(20,24,'N',assets,15,1)
        elif decision['info'].get('action') in ('attack-ally', 'flee-confirm', 'abort-spell'):
            frame.rect(184, 80, 128, 96, 0)
            frame.rect(0, 184, 320, 16, 0)
            if decision['info'].get('action') == 'attack-ally' and not decision['info'].get('moving'):
                a, b = target_position(game, decision['info']['actor']), target_position(game, decision['info']['target'])
                dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
                frame.text(0, 23, 'Range = %d' % (max(dx, dy) + min(dx, dy) // 2), assets, 10, 40)
            aborting = decision['info'].get('action') == 'abort-spell'
            if aborting: frame.text(0,23,'Spell:'+magic.spell_name(decision['info']['spell']),assets,10,40)
            prompt = decision['info']['prompt'].rstrip() + ('' if decision['info'].get('action') == 'flee-confirm' else ' ')
            frame.text(0, 24, prompt, assets, 14 if aborting else 13, 40)
            for index, word, col in ((0, 'Yes', len(prompt)), (1, 'No', len(prompt) + 4)):
                selected = controller.selected == index
                frame.text(col, 24, word, assets, 0 if selected else 10, background=15 if selected else 0)
                frame.text(col, 24, word[0], assets, 0 if selected else 15, background=15 if selected else 0)
        elif decision['options'] is not None and (prompt := controller.error or decision['info'].get('prompt')):
            frame.rect(184, 80, 128, 96, 0)
            for row, line in enumerate(textwrap.wrap(prompt, 16)[-12:], 10):
                frame.text(23, row, line, assets, 15, 16)
    return frame


def target_bar(controller):
    decision, game = controller.session.decision, controller.session.game
    if decision['info'].get('action') == 'move':
        moves = game.s.g['combat.records'][actor_index(game, decision)][6] // 2
        prompt = 'Move/Attack, Move Left = %d' % moves
        return ((0, prompt, ''), (len(prompt)+1, 'Done', 'd'))
    valid = cursor_choice(controller) is not None
    if manual(controller):
        return ((0, '(Use Cursor keys)', ''), (18, 'Target' if valid else 'Exit', 't' if valid else 'e'))
    words = ['Next', 'Prev', 'Manual'] + (['Target'] if valid else []) + ['Center', 'Exit']
    result, col = [(0, 'Aim:', '')], 4
    for word in words:
        result.append((col, word, word[0].lower())); col += len(word) + 1
    return tuple(result)


def init_aim(controller, previous=None):
    from copy import copy
    from sm.titles.ssb.units.combat import Combat
    game, decision = controller.session.game, controller.session.decision
    shadow = copy(game); shadow.s = game.s.copy(); shadow.presentation = None
    shadow.vm = copy(game.vm); shadow.vm.s = shadow.s; shadow.vm.host = shadow; shadow.vm.out = list(game.vm.out)
    shadow.combat = Combat(shadow)
    battle = shadow.combat; actor = battle.chars[actor_index(game, decision)]
    entries = sorted(battle.target_entries(actor, 127), key=lambda e: e[0])
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if b[1] < a[1] or (b[1] == a[1] and b[2] < a[2] and b[2] % 2 <= a[2] % 2):
                entries[i], entries[j] = entries[j], entries[i]
    controller.aim_cycle = [battle.position(battle.chars[i]) for i, _, _ in entries
                            if battle.chars[i] is actor or battle.can_see(actor, battle.chars[i])]
    controller.aim_decision, controller.aim_cursor = decision, (controller.aim_cycle or [battle.position(actor)])[0]
    controller.aim_origin = controller.aim_cursor
    command = 'n' if decision['info'].get('spell') else 'm'
    if decision['info'].get('spell') and previous:
        if previous['info'].get('action') == 'abort-spell':
            command = 'p'
        elif (previous['kind'] == 'TARGET' and previous['info'].get('spell') == decision['info']['spell']
              and previous['info'].get('caster') == decision['info'].get('caster')):
            command = controller.aim_command
    controller.aim_command = command
    controller.manual_target = False
    index = next((i for i, value in enumerate(decision['options'])
                  if target_position(game, value) == controller.aim_cursor), None)
    if index is not None: controller.selected = index
    controller.aim_selected = controller.selected


def manual(controller):
    return (getattr(controller, 'target_decision', None) is controller.session.decision
            and getattr(controller, 'manual_target', False))


def cursor(controller):
    if manual(controller): return controller.target_cursor
    decision = controller.session.decision
    if decision and decision['info'].get('action') == 'attack-ally':
        return target_position(controller.session.game, decision['info']['actor' if decision['info'].get('moving') else 'target'])
    if decision and decision['kind'] == 'TARGET' and decision['info'].get('action') != 'move':
        if getattr(controller, 'aim_decision', None) is decision and controller.selected == controller.aim_selected:
            return controller.aim_cursor
        return target_position(controller.session.game, decision['options'][controller.selected])
    return target_position(controller.session.game, actor_index(controller.session.game, decision))


def cursor_choice(controller):
    position = cursor(controller)
    if position is None: return None
    decision = controller.session.decision
    allowed = decision['info'].get('attackable', '').split(',') if decision['info'].get('action') == 'aim' else None
    return next((i for i, v in enumerate(decision['options'])
                 if (allowed is None or str(v) in allowed) and target_position(controller.session.game, v) == position), None)


def player_viewport(controller):
    event = getattr(controller, 'presentation_event', None)
    if event is not None: return event['view']
    position = cursor(controller) or target_position(controller.session.game,
                                                           actor_index(controller.session.game, controller.session.decision)) or (3, 3)
    if getattr(controller, 'presentation_enabled', False):
        game = controller.session.game
        old = getattr(game, 'presentation_view', None)
        if old is not None:
            decision = controller.session.decision
            aiming = decision and (decision['kind'] == 'TARGET' and decision['info'].get('action') != 'move'
                                   or decision['info'].get('action') == 'attack-ally')
            margin = 3 if aiming and not manual(controller) else 2
            if not aiming and not getattr(game, 'presentation_redraw', True): return old
            game.presentation_view = tuple(max(0, min(bound, position[i]-3)) if abs(position[i]-old[i]-3)>margin else old[i]
                                           for i,bound in enumerate((43,18)))
            return game.presentation_view
    return max(0, min(43, position[0] - 3)), max(0, min(18, position[1] - 3))


def player_layout(controller, result):
    decision, game = controller.session.decision, controller.session.game
    if decision is None or controller.files.active:
        return result
    regions = result['regions']
    purpose = decision['info'].get('purpose')
    if purpose=='take item':
        start=getattr(controller,'take_start',0); regions[:]=[]
        for index in range(start,min(start+22,len(decision['options'])-1)):
            delta=index-controller.selected
            regions.append(dict(rect=(8,(index-start+1)*8,304,8),select=index,keys=[dict(keysym='Down' if delta>=0 else 'Up',char='')]*abs(delta)+[dict(keysym='t',char='t')]))
        regions.extend(dict(rect=(col*8,192,len(word)*8,8),key=dict(keysym=key,char=key)) for col,word,key in take_bar(controller))
    elif purpose in ('take money','deposit money'):
        indices=coin_rows(controller); regions[:]=[]; taking=purpose=='take money'
        for row,index in enumerate(indices,2 if taking else 9):
            delta=indices.index(index)-indices.index(controller.selected)
            regions.append(dict(rect=(16 if taking else 160,row*8,112 if taking else 152,8),select=index,keys=[dict(keysym='Down' if delta>=0 else 'Up',char='')]*abs(delta)+[dict(keysym='s',char='s')]))
        offset=0 if taking else 8
        regions.extend((dict(rect=(160+offset,192,48,8),key=dict(keysym='s',char='s')),dict(rect=(216+offset,192,32,8),key=dict(keysym='e',char='e'))))
    elif purpose=='load game':
        regions[:]=[dict(rect=((17+2*n)*8,192,8,8),key=dict(keysym=key,char=key)) for n,(_,key,_) in enumerate(menu_items(decision,game))]
    elif purpose == 'memorize summary':
        regions[:] = [dict(rect=(8,192,32,8), key=dict(keysym='Return',char=''))]
    elif purpose in ('memorize confirm', 'scribe confirm', 'resting', 'drop item', 'confirm sale', 'confirm identification', 'quit to DOS', 'lose scribe scroll', 'use refusal'):
        col = len(decision['info']['prompt']) + (purpose == 'resting')
        regions[:] = [dict(rect=(col*8,192,24,8), key=dict(keysym='y',char='y')),
                      dict(rect=((col+4)*8,192,16,8), key=dict(keysym='n',char='n'))]
    elif decision['info'].get('action') in ('attack-ally', 'flee-confirm', 'abort-spell'):
        col = len(decision['info']['prompt'].rstrip()) + (decision['info'].get('action') != 'flee-confirm')
        regions[:] = [dict(rect=(col * 8, 192, 24, 8), key=dict(keysym='y', char='y')),
                      dict(rect=((col + 4) * 8, 192, 16, 8), key=dict(keysym='n', char='n'))]
    elif decision['kind'] == 'CREATE_TRAIN':
        col = len(decision['info'].get('prompt', 'Do you wish to train? ').rstrip()) + 1
        regions[:] = [dict(rect=(col*8,192,24,8), key=dict(keysym='y',char='y')),
                      dict(rect=((col+4)*8,192,16,8), key=dict(keysym='n',char='n'))]
    elif purpose == 'view':
        regions[:] = [r for r in regions if r['rect'][1] == 192]
    elif decision['info'].get('action')=='trade item':
        regions[:]=[]; col=len(decision['info']['prompt'])+1
        for index,value in enumerate(decision['options']):
            if value is None: continue
            delta=value-controller.roster_selected(); keys=[dict(keysym='Down' if delta>=0 else 'Up',char='')]*abs(delta)
            regions.append(dict(rect=(136,(4+value)*8,176,8),select=index,keys=keys+[dict(keysym='Return',char='')]))
        regions.extend((dict(rect=(col*8,192,48,8),key=dict(keysym='Return',char='')),
                        dict(rect=((col+7)*8,192,32,8),key=dict(keysym='Escape',char=''))))
    elif decision['kind']=='CREATE_ADD':
        regions[:]=[]
        if getattr(controller,'add_source',False):
            regions.extend(dict(rect=(col*8,192,len(word)*8,8),key=dict(keysym=word[0].lower(),char=word[0].lower()))
                           for col,word in ((16,'Secret'),(23,'Curse'),(29,'Exit')))
        else:
            indices=sorted((i for i,v in enumerate(decision['options']) if v is not None),key=lambda i:decision['options'][i])
            start=getattr(controller,'add_start',0)
            for row,index in enumerate(indices[start:start+21],2):
                delta=indices.index(index)-indices.index(controller.selected)
                keys=[dict(keysym='Down' if delta>=0 else 'Up',char='')]*abs(delta)+[dict(keysym='a',char='a')]
                regions.append(dict(rect=(8,row*8,304,8),select=index,keys=keys))
            regions.extend(dict(rect=(col*8,192,len(word)*8,8),key=dict(keysym=word[0].lower(),char=word[0].lower()))
                           for col,word in add_bar(controller))
    elif is_roster(decision) and game.s.mode == 0 and hasattr(controller, 'creation_background'):
        regions[:] = []
        for index, value in enumerate(decision['options']):
            if value is None: continue
            delta = index - controller.selected
            keys = [dict(keysym='Down' if delta >= 0 else 'Up', char='')] * abs(delta)
            keys.append(dict(keysym='Return', char=''))
            regions.append(dict(rect=(8, (4+value)*8, 304, 8), select=index, keys=keys))
        regions += [dict(rect=(120,192,48,8), key=dict(keysym='Return',char='')),
                    dict(rect=(176,192,32,8), key=dict(keysym='Escape',char=''))]
    elif purpose in ('buy', 'temple service'):
        regions[:] = []
        x, width, top, count = list_geometry(decision); start = controller.page * count
        action = 'b' if purpose == 'buy' else 'h'
        for index in range(start, min(start + count, len(decision['options'])-1)):
            delta = index - controller.selected
            keys = [dict(keysym='Down' if delta >= 0 else 'Up', char='')] * abs(delta)
            keys.append(dict(keysym=action, char=action))
            regions.append(dict(rect=(x*8, (top+index-start)*8, width*8, 8), select=index, keys=keys))
        col = 7 if purpose == 'buy' else 0
        for word in service_bar(controller):
            key = word[0].lower()
            regions.append(dict(rect=(col*8, 192, len(word)*8, 8), key=dict(keysym=key, char=key)))
            col += len(word)+1
    elif purpose == 'items':
        regions[:] = []
        start = getattr(controller, 'item_start', 0)
        for index in range(start, min(start + 18, len(decision['options']) - 1)):
            delta = index - controller.selected
            keys = [dict(keysym='Down' if delta >= 0 else 'Up', char='')] * abs(delta)
            regions.append(dict(rect=(16, (5 + index - start) * 8, 288, 8), select=index, keys=keys))
        col = 0
        for word in inventory_bar(controller):
            key = word[0].lower()
            regions.append(dict(rect=(col * 8, 192, len(word) * 8, 8), key=dict(keysym=key, char=key)))
            col += len(word) + 1
    elif purpose == 'effects':
        regions[:] = [dict(rect=(x * 8, 192, len(word) * 8, 8), key=dict(keysym=key, char=key))
                      for x, word, key in effects_bar(controller)]
    elif spell_list(decision) or cast_list(decision):
        regions[:] = [r for r in regions if r['rect'][1] == 192]
        items = menu_items(decision, game)
        page = min(controller.page, max(0, (len(items) - 1) // 10))
        regions.extend(dict(rect=(8, (3 + row) * 8, 304, 8), select=index)
                       for row, (index, _, _) in enumerate(items[page * 10:(page + 1) * 10]))
        if cast_list(decision):
            start = getattr(controller, 'cast_start', 0)
            visible = [(i, text) for i, text in cast_rows(controller)[start:start + cast_height(controller)] if i is not None]
            selected = next((k for k, (i, _) in enumerate(visible) if i == controller.selected), 0)
            regions[:] = []
            for row, (index, _) in enumerate(cast_rows(controller)[start:start + cast_height(controller)], 5):
                if index is None: continue
                delta = next(k for k, (i, _) in enumerate(visible) if i == index) - selected
                keys = [dict(keysym='Down' if delta >= 0 else 'Up', char='')] * abs(delta)
                if purpose not in ('view spells', 'scribe summary'):
                    key = {'memorize':'m', 'scribe':'s'}.get(purpose,'c')
                    keys.append(dict(keysym=key, char=key))
                regions.append(dict(rect=(8, row * 8, 304, 8), select=index, keys=keys))
            regions.extend(dict(rect=(col * 8, 192, len(word) * 8, 8), key=dict(keysym=key, char=key))
                           for col, word, key in cast_bar(controller) if key)
    elif game.s.g.get('combat.active') and decision['kind'] == 'TARGET':
        regions[:] = [r for r in regions if 'select' in r and r['rect'][0] < 176]
        for region in regions:
            if decision['info'].get('action') == 'move':
                key = next(k for i, k, _ in menu_items(decision, game) if i == region['select'])
                region['keys'] = [dict(keysym=key, char=key)]
                continue
            index = region['select']
            pages = index // 10 - controller.selected // 10
            delta = index % 10 if pages else index - controller.selected
            region['keys'] = [dict(keysym='m', char='m')] if manual(controller) else []
            region['keys'] += [dict(keysym='Next' if pages > 0 else 'Prior', char='')] * abs(pages)
            region['keys'] += [dict(keysym='Down' if delta >= 0 else 'Up', char='')] * abs(delta)
            region['keys'].append(dict(keysym='Return', char=''))
        regions.extend(dict(rect=(col * 8, 192, min(len(word), 40 - col) * 8, 8), key=dict(keysym=key, char=key))
                       for col, word, key in target_bar(controller) if key)
        result['revision'].append(manual(controller))
        position = cursor(controller)
        result['revision'].append(list(position) if position else None)
    return result


def overlay(frame, controller, assets):
    decision = controller.session.decision
    if not decision:
        return
    info = decision['info']
    if info.get('purpose') == 'speed':
        frame.rect(8, 136, 304, 48, 0)
        frame.text(1, 18, 'Game Speed = %d (0=fastest 9=slowest)' % info['speed'], assets, 10, 38)
    if info.get('purpose') in ('quit to DOS', 'drop from party'):
        frame.rect(0,192,320,8,0); prefix=info.get('bottom_prompt', info.get('prompt')); frame.text(0,24,prefix,assets,14)
        for index,word,col in ((0,'Yes',len(prefix)),(1,'No',len(prefix)+4)):
            chosen=controller.selected==index
            frame.text(col,24,word,assets,0 if chosen else 10,background=15 if chosen else 0)
            frame.text(col,24,word[0],assets,0 if chosen else 15,1,background=15 if chosen else 0)
    if info.get('purpose') == 'order':
        frame.rect(0, 192, 320, 8, 0); prefix = 'Party Order: '; frame.text(0, 24, prefix, assets, 13)
        col = len(prefix)
        for index, key, label in menu_items(decision, controller.session.game):
            chosen = controller.selected == index
            frame.text(col, 24, label, assets, 0 if chosen else 10, background=15 if chosen else 0)
            frame.text(col, 24, label[0], assets, 0 if chosen else 15, 1, background=15 if chosen else 0)
            col += len(label) + 1
    if info.get('purpose') in ('rest duration', 'resting'):
        minutes = info.get('remaining', info.get('minutes', 0))
        days, rest = divmod(minutes, 1440)
        hours, mins = divmod(rest, 60)
        frame.rect(8, 136, 304, 48, 0)
        frame.text(1, 17, 'Rest Time: %02d:%02d:%02d' % (days, hours, mins), assets, 10, 38)
        if info.get('purpose') == 'resting':
            frame.rect(0,192,320,8,0)
            prompt = info['prompt'].rstrip() + ' '
            frame.text(0,24,prompt,assets,13); col = len(prompt)
            for index,key,label in menu_items(decision,controller.session.game):
                selected = controller.selected == index
                frame.text(col,24,label,assets,0 if selected else 10,background=15 if selected else 0)
                frame.text(col,24,label[0],assets,0 if selected else 15,1,background=15 if selected else 0)
                col += len(label)+1
        else:
            field = info.get('field', 'minutes')
            col, value = {'days': (12, days), 'hours': (15, hours), 'minutes': (18, mins)}[field]
            frame.text(col, 17, '%02d' % value, assets, 15, 2)


def player_key(controller, keysym, char):
    decision, game = controller.session.decision, controller.session.game
    if not hasattr(game, 's'):
        return None
    if decision and decision['info'].get('purpose')=='take item' and not getattr(controller,'take_submitting',False):
        count=len(decision['options'])-1; start=getattr(controller,'take_start',0); height=min(22,count-start)
        if keysym in ('Home','End'): return False
        if keysym in ('Up','Down') and height:
            controller.selected=start+(controller.selected-start+(-1 if keysym=='Up' else 1))%height; return False
        words=take_bar(controller)
        if keysym in ('Left','Right'):
            controller.take_command=(controller.take_command+(-1 if keysym=='Left' else 1))%len(words); return False
        key=words[controller.take_command][2] if keysym in ('Return','KP_Enter') else char.lower()
        if key=='e':
            controller.take_command=next(i for i,word in enumerate(words) if word[2]=='e')
            return controller.key('Escape')
        if key in ('n','p') or keysym in ('Next','Prior'):
            command='p' if key=='p' or keysym=='Prior' else 'n'
            index=next((i for i,word in enumerate(words) if word[2]==command),None)
            if index is None: return False
            offset=max(0,min(max(0,count-22),start+(-22 if key=='p' or keysym=='Prior' else 22)))
            controller.take_start=offset; controller.selected+=offset-start
            controller.take_command=index if index<len(take_bar(controller)) else 0; return False
        if key=='t' and height:
            controller.take_command=0
            controller.take_submitting=True
            try: return controller.key('Return')
            finally: controller.take_submitting=False
    if decision and decision['info'].get('purpose') in ('take money','deposit money') and not getattr(controller,'coin_submitting',False):
        indices=coin_rows(controller)
        if keysym in ('Up','Down','Home','End') and indices:
            at=indices.index(controller.selected)
            at=0 if keysym=='Home' else len(indices)-1 if keysym=='End' else (at+(-1 if keysym=='Up' else 1))%len(indices)
            controller.selected=indices[at]; return False
        if keysym in ('Left','Right'): controller.coin_command=1-controller.coin_command; return False
        key=('s','e')[controller.coin_command] if keysym in ('Return','KP_Enter') else char.lower()
        if key=='e':
            controller.coin_command=1; return controller.key('Escape')
        if key=='s' and indices:
            controller.coin_command=0
            controller.coin_submitting=True
            try: return controller.key('Return')
            finally: controller.coin_submitting=False
    if decision and decision['kind'] == 'CREATE_MODIFY':
        if getattr(controller, 'modify_submitting', False): return None
        return modify_key(controller, keysym, char)
    if decision and decision['kind'] == 'CREATE_ADD' and getattr(controller, 'add_source', False):
        if keysym in ('Left', 'Right'):
            controller.selected = (controller.selected + (-1 if keysym == 'Left' else 1)) % 3; return False
        key = 'e' if keysym == 'Escape' else 'sce'[controller.selected] if keysym == 'Return' else char.lower()
        if key == 'e': controller.add_source = False; return controller.key('Escape')
        if key == 's':
            controller.add_source, controller.add_command = False, 0
            if decision['options'] == [None]: return controller.key('Escape')
            controller.selected=min((i for i,v in enumerate(decision['options']) if v is not None),key=lambda i:decision['options'][i])
        return False
    if decision and decision['kind']=='CREATE_ADD':
        indices=sorted((i for i,v in enumerate(decision['options']) if v is not None),key=lambda i:decision['options'][i])
        start=getattr(controller,'add_start',0); height=min(21,len(indices)-start)
        if keysym in ('Home','End'): return False
        if keysym in ('Up','Down') and indices:
            at=indices.index(controller.selected)-start if controller.selected in indices else 0
            at=(at+(-1 if keysym=='Up' else 1))%height
            controller.selected=indices[start+at]; return False
        commands=[word[0].lower() for _,word in add_bar(controller)]
        if keysym in ('Left','Right'):
            controller.add_command=(getattr(controller,'add_command',0)+(-1 if keysym=='Left' else 1))%len(commands); return False
        key=commands[min(getattr(controller,'add_command',0),len(commands)-1)] if keysym in ('Return','KP_Enter') else char.lower()
        if key=='e': return controller.key('Escape')
        if key in ('n','p') or keysym in ('Next','Prior'):
            command='p' if key=='p' or keysym=='Prior' else 'n'
            if command not in commands: return False
            index=commands.index(command); offset=max(0,min(max(0,len(indices)-21),start+(-21 if command=='p' else 21)))
            controller.add_start=offset; controller.selected=indices[indices.index(controller.selected)+offset-start]
            controller.add_command=index if index<len(add_bar(controller)) else 0; return False
        if key=='a':
            controller.session.step(controller.selected)
            following=controller.session.decision
            if following and following['kind']=='CREATE_MENU':
                words=menu_items(following,controller.session.game); row=controller.menu_selection[('CREATE_MENU',None)][1]
                controller.selected=words[min(row,len(words)-1)][0]
                controller.page=0
            controller.capture_text(); return True
    if decision and decision['kind'] == 'CREATE_ICON':
        if getattr(controller, 'icon_submitting', False): controller.icon_submitting = False; return None
        return icon_key(controller, keysym, char)
    if decision and decision['kind'] == 'CREATE_MENU' and keysym == 'Escape':
        return False
    if (decision and decision['kind'] == 'SHOP_MENU' and not decision['info'].get('purpose')
            and decision['info'].get('place') in ('shop', 'temple', 'vault') and keysym == 'Escape'):
        return False
    if decision and decision['info'].get('purpose') in ('buy', 'temple service'):
        last = len(decision['options']) - 2; count = list_geometry(decision)[3]
        if keysym in ('Home', 'End'): return False
        if keysym in ('Up', 'Down'):
            first = controller.page * count; rows = min(count, last + 1 - first)
            if rows > 0: controller.selected = first + (controller.selected - first + (-1 if keysym == 'Up' else 1)) % rows
            return False
        words = service_bar(controller)
        if keysym in ('Left', 'Right'):
            controller.service_command = (getattr(controller, 'service_command', 0) + (-1 if keysym == 'Left' else 1)) % len(words); return False
        key = char.lower()
        if keysym in ('Return', 'KP_Enter'): key = words[min(getattr(controller, 'service_command', 0), len(words)-1)][0].lower()
        if key == words[0][0].lower():
            controller.session.step(controller.selected); controller.capture_text(); return True
        if key == 'e': return controller.key('Escape')
        if key in ('n', 'p') or keysym in ('Next', 'Prior'):
            delta = -1 if key == 'p' or keysym == 'Prior' else 1
            row = controller.selected % count
            controller.page = max(0, min(last // count, controller.page + delta)); controller.selected = min(last, controller.page * count + row); return False
    if decision and decision['info'].get('purpose') == 'items':
        last = len(decision['options']) - 2; start = getattr(controller, 'item_start', 0)
        if keysym in ('Up', 'Down', 'Home', 'End'):
            if last < 0: return False
            count = min(18, last + 1 - start)
            controller.selected = (start if keysym == 'Home' else start + count - 1 if keysym == 'End' else
                                   start + (controller.selected - start + (-1 if keysym == 'Up' else 1)) % count)
            return False
        if keysym in ('Next', 'Prior') or char and char.lower() in ('n', 'p'):
            delta = -1 if keysym == 'Prior' or char.lower() == 'p' else 1
            words = inventory_bar(controller); command = 'p' if delta < 0 else 'n'
            index = next((i for i, word in enumerate(words) if word[0].lower() == command), None)
            if index is None: return False
            controller.item_start = max(0, min(max(0, last + 1 - 18), start + delta * 18))
            controller.selected += controller.item_start - start
            words = inventory_bar(controller)
            controller.item_command = words[index if index < len(words) else 0][0].lower()
            return False
        words = inventory_bar(controller); key = char.lower()
        if keysym in ('Left', 'Right'):
            current = next((i for i,w in enumerate(words) if w[0].lower() == getattr(controller,'item_command','r')), 0)
            controller.item_command = words[(current + (-1 if keysym=='Left' else 1)) % len(words)][0].lower(); return False
        if keysym in ('Return', 'KP_Enter'): key = getattr(controller, 'item_command', 'r')
        action = next((w.lower() for w in words if w[0].lower()==key), None)
        if action == 'exit' or keysym == 'Escape': return None
        if action in ('next','prev'): return controller.key('Next' if action=='next' else 'Prior')
        if action:
            selected = controller.selected
            controller.inventory_return=(selected,start,next(i for i,w in enumerate(words) if w[0].lower()==key))
            controller.item_command=key
            if action in ('drop','sell','id','use','trade','deposit'):
                controller.selected = -1
                controller.inventory_background = capture_background(controller, render_player); controller.selected = selected
            controller.session.step(selected); controller.capture_text()
            following = controller.session.decision
            if not following or following['info'].get('purpose') != 'item': return True
            answer = 'identify' if action == 'id' else action
            hotkey = next(k for i,k,_ in menu_items(following,game) if following['options'][i] == answer)
            controller.key(hotkey,hotkey)
            if controller.session.decision and controller.session.decision['info'].get('purpose') == 'items':
                controller.selected = min(selected,len(controller.session.decision['options'])-2)
                controller.item_start = min(start, max(0, len(controller.session.decision['options']) - 19))
            return True
        return False
    if decision and decision['kind'] == 'COMBAT_ACTION' and not decision['info'].get('action') and keysym == 'Escape':
        return False
    if cast_list(decision):
        commands = [key for _, _, key in cast_bar(controller) if key]
        key = char.lower()
        if keysym in ('Left', 'Right'):
            controller.cast_command = (getattr(controller, 'cast_command', 0) + (-1 if keysym == 'Left' else 1)) % len(commands)
            return False
        if keysym in ('Return', 'KP_Enter'):
            key = commands[min(getattr(controller, 'cast_command', 0), len(commands)-1)]
        if key == 'e': return controller.key('Escape')
        rows = cast_rows(controller); start = getattr(controller, 'cast_start', 0); height = cast_height(controller)
        if keysym in ('Next', 'Prior') or key in ('n', 'p'):
            delta = -height if keysym == 'Prior' or key == 'p' else height
            if key in commands: controller.cast_command = commands.index(key)
            offset = next(n for n, (i, _) in enumerate(rows) if i == controller.selected) - start
            controller.cast_start = max(0, min(max(0, len(rows) - height), start + delta))
            visible = rows[controller.cast_start:controller.cast_start + height]
            for _ in visible:
                if visible[offset][0] is not None: break
                offset = (offset + (-1 if delta < 0 else 1)) % len(visible)
            controller.selected = visible[offset][0]
            return False
        if keysym in ('Home', 'End'): return False
        if keysym in ('Up', 'Down'):
            visible = [i for i, _ in rows[start:start + height] if i is not None]
            index = visible.index(controller.selected) if controller.selected in visible else 0
            controller.selected = visible[(index + (-1 if keysym == 'Up' else 1)) % len(visible)]
            return False
        if key == {'memorize':'m', 'scribe':'s', 'learn at training':'l'}.get(decision['info'].get('purpose'),'c') and key in commands:
            controller.cast_command = commands.index(key)
            selected, command = controller.selected, getattr(controller, 'cast_command', 0)
            controller.cast_row = next((n for n, (i, _) in enumerate(rows) if i == selected), 0)
            if getattr(controller, 'presentation_enabled', False) and controller.session.game.s.g.get('combat.active'):
                rows = capture_footer(controller, clear_top=True)
                g = controller.session.game.s.g; who = actor_index(controller.session.game, decision)
                controller.session.game.presentation_cursor = (who, tuple(g['combat.positions'][who]), g['combat.records'][who][9])
                controller.session.game.presentation_footer = rows
            controller.session.step(controller.selected)
            controller.entry, controller.page, controller.selected = '', 0, 0
            following = controller.session.decision
            if following and following['kind'] == 'CREATE_MENU':
                saved = controller.menu_selection.get(('CREATE_MENU', following['info'].get('purpose')))
                if saved and saved[0] == 'row':
                    words = menu_items(following, controller.session.game)
                    controller.selected = words[min(saved[1], len(words)-1)][0]
            controller.capture_text()
            if (decision['info'].get('purpose') in ('memorize','scribe') and cast_list(controller.session.decision)
                    and controller.session.decision['info'].get('purpose') == decision['info'].get('purpose')):
                old = decision['options'][selected]
                controller.selected = controller.session.decision['options'].index(old)
                controller.cast_start, controller.cast_command = start, command
            return True
    legacy = ('quick-off' if decision['kind'] == 'COMBAT_ACTION' and char == ' ' else None)
    if legacy is not None and legacy in (decision['options'] or ()):
        controller.session.step(decision['options'].index(legacy))
        controller.entry, controller.page, controller.selected = '', 0, 0
        controller.capture_text()
        return True
    if decision['info'].get('purpose') == 'rest duration':
        action = None
        if keysym in ('Up', 'Down'):
            action = 'add' if keysym == 'Up' else 'subtract'
        elif keysym in ('Left', 'Right'):
            fields = ('minutes', 'hours', 'days')
            index = fields.index(decision['info'].get('field', 'minutes'))
            action = fields[(index + (1 if keysym == 'Left' else -1)) % 3]
        if action:
            hotkey = next(key for i, key, _ in menu_items(decision, game) if decision['options'][i] == action)
            selected = controller.selected; menu_key = ('CAMP_MENU', 'rest duration')
            previous = controller.menu_selection.get(menu_key)
            advanced = controller.key(hotkey, hotkey)
            controller.selected = selected
            if previous is None: controller.menu_selection.pop(menu_key, None)
            else: controller.menu_selection[menu_key] = previous
            return advanced
    if decision['info'].get('purpose') == 'effects':
        lines=effect_lines(game); start=getattr(controller,'effects_start',0); commands=[key for _,_,key in effects_bar(controller)]
        if keysym in ('Left','Right'):
            controller.effects_command=(getattr(controller,'effects_command',0)+(-1 if keysym=='Left' else 1))%len(commands); return False
        key=commands[min(getattr(controller,'effects_command',0),len(commands)-1)] if keysym in ('Return','KP_Enter') else char.lower()
        if key=='e': return controller.key('Escape')
        if keysym in ('Next','Prior') or key in ('n','p'):
            delta=-19 if keysym=='Prior' or key=='p' else 19
            offset=getattr(controller,'effects_selected',0)-start
            controller.effects_start=start=max(0,min(max(0,len(lines)-19),start+delta))
            while lines[start+offset][1]==11: offset=(offset+(-1 if delta<0 else 1))%min(19,len(lines)-start)
            controller.effects_selected=start+offset
            if key in commands: controller.effects_command=commands.index(key)
            if controller.effects_command>=len(effects_bar(controller)): controller.effects_command=0
            return False
        if keysym in ('Up','Down'):
            visible=[i for i in range(start,min(start+19,len(lines))) if lines[i][1]!=11]
            at=visible.index(getattr(controller,'effects_selected',0)); controller.effects_selected=visible[(at+(-1 if keysym=='Up' else 1))%len(visible)]
            return False
    if game.s.g.get('combat.active') and decision['kind'] == 'TARGET':
        options = decision['options']
        directions = {'Left': (-1, 0), 'Right': (1, 0), 'Up': (0, -1), 'Down': (0, 1),
                      'Home': (-1, -1), 'Prior': (1, -1), 'End': (-1, 1), 'Next': (1, 1)}
        if decision['info'].get('action') == 'move':
            if keysym in ('Return', 'KP_Enter') or char.lower() == 'd':
                if 'done' not in options: return controller.key('Escape')
                hotkey = next(k for i, k, _ in menu_items(decision, game) if i == options.index('done'))
                return controller.key(hotkey, hotkey)
            if keysym in directions:
                x, y = cursor(controller); dx, dy = directions[keysym]
                if (x + dx, y + dy) not in options: return False
                index = options.index((x + dx, y + dy))
                hotkey = next(k for i, k, _ in menu_items(decision, game) if i == index)
                return controller.key(hotkey, hotkey)
            return None
        if char.lower() in ('n', 'p') and char:
            controller.aim_command = char.lower()
            delta = -1 if char.lower() == 'p' else 1
            cycle = getattr(controller, 'aim_cycle', [])
            if not cycle: return False
            position = cursor(controller)
            current = cycle.index(position) if position in cycle else -1
            controller.aim_cursor = cycle[(current + delta) % len(cycle)]
            index = next((i for i, value in enumerate(options) if target_position(game, value) == controller.aim_cursor), None)
            if index is not None: controller.selected = index
            controller.aim_selected = controller.selected
            controller.page = controller.selected // 10
            return False
        if char.lower() == 'm':
            controller.aim_command = 'm'
            position = cursor(controller)
            controller.manual_target = not manual(controller)
            controller.target_decision = decision
            controller.target_cursor = position or target_position(game, actor_index(game, decision)) or (0, 0)
            controller.manual_origin = controller.target_cursor
            return False
        if char.lower() == 'c':
            controller.aim_command = 'c'
            position = cursor(controller)
            if position is not None:
                game.presentation_view = tuple(max(0, min(bound, position[i] - 3)) for i, bound in enumerate((43, 18)))
            return False
        if manual(controller) and (keysym == 'Escape' or char.lower() == 'e'):
            controller.manual_target = False
            origin = controller.manual_origin
            game.presentation_view = tuple(max(0, min(bound, origin[i]-3)) for i, bound in enumerate((43, 18)))
            return False
        if keysym == 'Escape' or char.lower() == 'e':
            origin = controller.aim_origin if keysym == 'Escape' else cursor(controller)
            if origin is not None:
                game.presentation_view = tuple(max(0, min(bound, origin[i]-3)) for i, bound in enumerate((43, 18)))
        if keysym in directions and manual(controller):
            start = cursor(controller)
            dx, dy = directions[keysym]
            if start:
                controller.target_cursor = max(0, min(49, start[0] + dx)), max(0, min(24, start[1] + dy))
                index = cursor_choice(controller)
                if index is not None: controller.selected, controller.page = index, index // 10
            return False
        if keysym in ('Return', 'KP_Enter') or char.lower() == 't':
            index = cursor_choice(controller)
            if index is None: return False
            controller.aim_command = 't'
            controller.selected, controller.page = index, index // 10
            if getattr(controller, 'presentation_enabled', False) and getattr(controller, 'footer_snapshot', None) is None:
                controller.footer_snapshot = capture_footer(controller)
            controller.manual_target = False
        if char.lower() == 't':
            return controller.key('Return')
    return None


def prompt_label(value, fallback, decision):
    purpose = decision['info'].get('purpose')
    mapping = ({'train': 'Yes', 'cancel': 'No'} if decision['kind'] == 'CREATE_TRAIN' else
               {'sell': 'Yes', 'cancel': 'No'} if purpose == 'confirm sale' else
               {'identify': 'Yes', 'cancel': 'No'} if purpose == 'confirm identification' else
               {'retrieve': 'Yes', 'leave': 'No'} if purpose == 'money left behind' else {})
    return mapping.get(value, fallback) if isinstance(value, (str, int, type(None))) else fallback


def input_key(controller, keysym, char):
    decision = controller.session.decision
    kind, info = decision['kind'], decision['info']
    coin = bool(info.get('number_prompt'))
    if keysym == 'BackSpace':
        controller.entry = controller.entry[:-1]
        return False, None
    if keysym == 'Escape' and coin:
        return True, 0
    if keysym not in ('Return', 'KP_Enter', 'Escape'):
        maximum = info.get('max_length', 6 if kind == 'NUMBER' else 40)
        if kind == 'STRING' and char == ' ':
            if controller.entry and len(controller.entry) < 255: controller.entry += char
        elif len(char) == 1 and ' ' <= char <= 'z' and len(controller.entry) < maximum:
            if kind != 'NUMBER' or char in '0123456789':
                controller.entry += char
                if coin and int(controller.entry) > info['max']:
                    controller.entry = str(info['max'])[:5]
        return False, None
    answer = controller.entry.rstrip(' ') if kind == 'STRING' else controller.entry
    if kind == 'NUMBER':
        answer = int(answer or '0')
        if not info.get('min', 0) <= answer <= info.get('max', 65535):
            controller.error = 'Range %s..%s' % (info.get('min', 0), info.get('max', 65535))
            return False, None
    elif len(answer) < info.get('min_length', 0):
        controller.error = 'Enter at least %d characters' % info['min_length']
        return False, None
    return True, answer


def draw_input(frame, controller, assets):
    decision = controller.session.decision
    info = decision['info']
    prompt = info.get('prompt', 'Character name: ' if decision['kind'] == 'CREATE_NAME' else '')
    if prompt and not prompt.endswith(' '): prompt += ' '
    line = prompt + controller.entry
    start = max(0, len(line) - 39)
    visible = line[start:]
    frame.rect(0, 192, 320, 8, 0)
    frame.text(0, 24, visible, assets, 15, 39)
    frame.text(len(visible), 24, '%', assets, 15, 1)
    if controller.error:
        frame.rect(8, 176, 304, 8, 0)
        frame.text(1, 22, controller.error, assets, 14, 38)


def draw_service(frame, controller, assets):
    decision = controller.session.decision
    if not decision: return
    info = decision['info']
    purpose = info.get('purpose')
    if purpose=='money left behind':
        frame.rect(8,136,304,48,0); combined=info['warning']+info['prompt']; start=0
        for row,line in enumerate(wrapped_text(combined),17):
            start=combined.index(line,start); split=max(0,min(len(line),len(info['warning'])-start))
            frame.text(1,row,line,assets,10,38)
            frame.text(1+split,row,line[split:],assets,10 if info['place']=='temple' else 15,38-split)
            start+=len(line)
    elif purpose in ('appraise', 'appraisal'):
        frame.rect(8, 8, 304, 176, 0)
        frame.text(1, 1, info.get('character', ''), assets, 11, 38)
        frame.text(1, 7, 'You have a fine collection of:', assets, 15, 38)
        gems, jewelry = info.get('gems', 0), info.get('jewelry', 0)
        if gems: frame.text(1, 9, '%d Gem%s' % (gems, '' if gems == 1 else 's'), assets, 15, 38)
        if jewelry: frame.text(1, 10, '%d piece%s of Jewelry' % (jewelry, '' if jewelry == 1 else 's'), assets, 15, 38)
        if purpose == 'appraisal':
            frame.text(1, 12, 'The %s is Valued at %d gp.' % (info['valuable'], info['value']), assets, 15, 38)
        prefix = 'Appraise : ' if purpose == 'appraise' else 'You can : '
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, prefix, assets, 13, 40)
        col = len(prefix) + (2 if purpose == 'appraise' else 0)
        for index, key, label in menu_items(decision, controller.session.game):
            selected = index == controller.selected
            frame.text(col, 24, label, assets, 0 if selected else 10, 40-col, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
            col += len(label) + 1
    elif is_roster(decision) and (info.get('spell') or info.get('action')=='trade item'):
        frame.rect(0, 192, 320, 8, 0)
        prefix='Cast spell on whom ' if info.get('spell') else info['prompt']+' '; col=len(prefix)
        frame.text(0, 24, prefix, assets, 13, 40)
        frame.text(col, 24, 'Select', assets, 0, 6, background=15)
        frame.text(col+7, 24, 'Exit', assets, 10, 4); frame.text(col+7, 24, 'E', assets, 15, 1)
    elif decision['kind'] == 'CREATE_TRAIN':
        draw_frame(frame, assets, 'party')
        character = info.get('character', '')
        frame.text(4, 4, character, assets, 11, 35)
        frame.text(4 + len(character), 4, ' will become:', assets, 10, 35-len(character))
        for row, level in enumerate(info['level_text'].splitlines() if 'level_text' in info else info.get('levels', ()), 5):
            frame.text(6, row, ('    ' if row == 5 else 'and ') + level, assets, 10, 33)
        prefix = info.get('prompt', 'Do you wish to train? ').rstrip() + ' '
        frame.text(0, 24, prefix, assets, 13); col = len(prefix)
        for i, key, label in menu_items(decision, controller.session.game):
            selected = i == controller.selected
            frame.text(col, 24, label, assets, 0 if selected else 10, background=15 if selected else 0)
            frame.text(col, 24, label[0], assets, 0 if selected else 15, 1, background=15 if selected else 0)
            col += len(label) + 1


def render_presentation(controller, event, assets):
    if event['kind']=='script-death':
        frame=new_frame(assets);draw_frame(frame,assets,'party');frame.text(1,1,event['text'],assets,10,38)
        return frame
    if event['kind']=='script-hold':
        scene=event['scene']; state, display = scene.s, scene.vm.display; frame=new_frame(assets)
        bigpic = current_picture(scene).get('kind') == 'BIGPIC'
        draw_frame(frame, assets, 'full' if bigpic else 'explore')
        if not bigpic and not display.get('blank'):
            view3d.draw(frame, state, scene.geo.map, assets, area=controller.area_map, sky_choices=display.get('sky'))
        draw_picture(frame, scene)
        if not bigpic and state.party: draw_roster(frame, controller, state, display, assets)
        for row, line in enumerate(wrapped_text(event['text'])[-6:], 17): frame.text(1, row, line, assets, event['colour'], 38)
        if event.get('bottom'):
            frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, event['bottom'], assets, 10, 40)
        return frame
    decision = dict(kind='COMBAT_ACTION', options=['done'], info={'actor': event['actor']})
    view = SimpleNamespace(session=SimpleNamespace(game=event['scene'], decision=decision),
                           selected=0, page=0, text=event['text'], error='', presentation_event=event,
                           equipment_icon=controller.equipment_icon, manual_bodies=controller.manual_bodies,
                           plus_settings=getattr(controller, 'plus_settings', None),
                           _look_override=getattr(controller, '_look_override', getattr(controller, 'plus_settings', None).options['look'] if getattr(controller, 'plus_settings', None) else 'original'))
    frame = render_player(view, assets)
    for row, index, colour in event.get('names', ()):
        b = event['scene'].s.chars()[index].b
        frame.text(23,10+row,pstring(b,maximum=15),assets,colour,16)
    frame.rect(0, 184, 320, 16, 0)
    from .vga import footer_rows
    for row, pixels in enumerate(footer_rows(event.get('footer', ()), assets)): frame.rows[184+row][:] = pixels
    if event.get('command') is not None:
        frame.rect(0,184,320,16,0); frame.text(0,24,event['command'],assets,10,40)
    spell = event.get('spell') or (event['scene'].s.g.get('87D8') if not event.get('spell_row_cleared') else 0)
    if spell:
        frame.text(0, 23, 'Spell:' + magic.spell_name(spell), assets, 10, 40)
    if event.get('bottom'):
        frame.rect(0,192,320,8,0)
        frame.text(0, 24, event['bottom'], assets, 10, 40)
    if 'sprite' in event:
        x0, y0 = player_viewport(view)
        x, y = event['point']
        pixels = art.picture('COMSPR', event['sprite'])[2][event.get('sprite_pose', 0)]
        if event.get('mirror'): pixels = tuple(row[::-1] for row in pixels)
        if event.get('flip'): pixels = pixels[::-1]
        for dx, dy in event.get('cells', ((0, 0),)):
            frame.blit(8 + round((x + dx - x0) * 24), 8 + round((y + dy - y0) * 24),
                       pixels, transparent=0, clip=(8, 8, 176, 176))
    return frame


def wrapped_text(text, width=38):
    return ssb_data.wrapped_text(text,width)


def message_seconds(controller, original):
    hold = getattr(controller, 'message_hold', 400)
    return (original if hold == 400 else hold / 1000) * controller.effect_scale


def not_here(controller, frame, assets, elapsed):
    if getattr(controller, 'not_here_seen', None) is None or elapsed >= 1e6: return
    if not controller.not_here_seen:
        controller.not_here_seen = True
        controller.not_here_until = elapsed + message_seconds(controller, .39)
    if elapsed < controller.not_here_until:
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, 'Not Here', assets, 14, 40)
    else: controller.not_here_seen = None


def buy_notice(controller, frame, assets, elapsed):
    game = controller.session.game; decision = controller.session.decision; vm = getattr(game, 'vm', None)
    if not (decision and getattr(vm, 'service_bottom', None)) or elapsed >= 1e6: return
    if getattr(controller, 'buy_notice_seen', None) != vm.service_bottom:
        controller.buy_notice_seen = vm.service_bottom
        controller.buy_notice_start = elapsed
    lines = [line for line in vm.service_bottom[:1:-1] if line]
    hold = message_seconds(controller, game.s.g.get('67D6', 0) / 10)
    at = int((elapsed - controller.buy_notice_start) / hold) if hold else len(lines)
    if 0 <= at < len(lines):
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, lines[at], assets, 10, 40)


def window_notice(controller, frame, assets, elapsed):
    game = controller.session.game; decision = controller.session.decision; note = getattr(getattr(game, 'vm', None), 'service_window', None)
    if not (decision and note) or elapsed >= 1e6 or decision['info'].get('place') != 'vault': return
    if getattr(controller, 'window_notice_seen', None) != note: controller.window_notice_seen, controller.window_notice_start = note, elapsed
    if 0 <= elapsed - controller.window_notice_start < message_seconds(controller, game.s.g.get('67D6', 0) / 10):
        frame.rect(8, 168, 304, 16, 0)
        for row, line in enumerate(wrapped_text(note[1])[:2], 21): frame.text(1, row, line, assets, 14, 38)


def draw_name_notice(frame, assets, notice):
    r = notice[5]
    frame.rect(8, r * 8, 38 * 8, (23 - r) * 8, 0)
    frame.text(1, r + 1, notice[1], assets, notice[3], 38); frame.text(1, r + 2, notice[2], assets, 10, 38)


def name_notice(controller, frame, assets, elapsed):
    game = controller.session.game; vm = getattr(game, 'vm', None); decision = controller.session.decision
    if not decision: return
    queue = getattr(vm, 'service_names', None)
    legacy = getattr(vm, 'service_name', None)
    if queue is None: queue = [tuple(legacy[:4]) + (True, 18 if game.s.g.get('8DB4') else 17)] if legacy else []
    if elapsed >= 1e6:
        notice = queue[-1] if queue and not queue[-1][4] else None
        if notice is None or len(notice)>6 and (notice[6] != vm.text_epoch or notice[0] != len(vm.out)): return
    else:
        while queue:
            notice = queue[0]
            if not notice[4] and len(notice)>6 and (notice[6] != vm.text_epoch or notice[0] != len(vm.out)):
                queue.pop(0); continue
            if getattr(controller, 'name_notice_seen', None) != notice:
                controller.name_notice_seen, controller.name_notice_decision = notice, decision
                controller.name_notice_until = elapsed + message_seconds(controller, game.s.g.get('67D6', 0) / 10)
                break
            if notice[4] and elapsed >= controller.name_notice_until: queue.pop(0); continue
            break
        else: return
    prompt = decision['info'].get('prompt') if not notice[4] else None
    start = 8 * (23 - len(textwrap.wrap(str(prompt), 38)[-6:])) if prompt else 184
    question = [row[:] for row in frame.rows[start:184]]
    draw_name_notice(frame, assets, notice)
    frame.rows[start:184] = question
    if decision['kind']=='LIST' and decision['info'].get('purpose')=='temple service':
        for row in frame.rows[32 + 8 * controller.selected:40 + 8 * controller.selected]:
            end = max((x for x in range(16, 304) if row[x] == 15), default=0) | 7
            for x in range(16, end + 1): row[x] = 0 if row[x] == 15 else 10


def draw_roster(frame, controller, state, display, assets, top_menu=False):
    name_col = 1 if top_menu or state.mode == 0 else 17
    frame.text(name_col, 2, 'Name', assets)
    frame.text(33, 2, 'AC  HP', assets)
    for row, member in enumerate(state.party[:11], 4):
        b = member.b
        name = bytes(b[1:1 + min(b[0], 15)]).decode('latin1')
        colour = 15 if controller.roster_highlighted(row - 4) else 12 if not b[0x1A7] else 14 if state.mode == 5 and b[0x1A8] == 1 else 11
        frame.text(name_col, row, name, assets, colour, 15)
        frame.text(32, row, '%3d' % (60 - b[0x1AB]), assets, 10)
        frame.text(36, row, '%3d' % b[0x1B5], assets, 14 if b[0x1B5] < b[0x70] else 10)
    if not top_menu and state.mode != 6 and not display.get('location_hidden'): frame.text(17, 15, location(state, display.get('clock'), display.get('location')), assets, 10, 22)


def render(controller, assets=None, elapsed=0):
    from .vga import assets_for
    assets = assets_for(controller, assets or Assets())
    frame = render_screen(controller, assets, elapsed)
    buy_notice(controller, frame, assets, elapsed)
    window_notice(controller, frame, assets, elapsed)
    name_notice(controller, frame, assets, elapsed)
    not_here(controller, frame, assets, elapsed)
    return frame


def render_screen(controller, assets=None, elapsed=0):
    assets = assets or Assets()
    event = controller.advance_presentation(elapsed)
    if event is not None:
        return render_presentation(controller, event, assets)
    session, frame = controller.session, new_frame(assets)
    if controller.files.active:
        controller.files.draw(frame, assets)
        return frame
    picker = controller.file_picker()
    if picker is not None:
        picker.draw(frame, assets)
        return frame
    special = render_player(controller, assets)
    if special is not None:
        return special
    state, decision = session.game.s, session.decision
    if decision and decision['info'].get('purpose')=='script damage' and decision['info'].get('defeated'):
        draw_frame(frame,assets,'party')
        for row,line in enumerate(wrapped_text(controller.text),1): frame.text(1,row,line,assets,10,38)
        frame.text(0,24,decision['options'][0],assets,15,40)
        return frame
    combat = bool(state.g.get('combat.active'))
    top_menu = bool(decision and decision['kind'] == 'CREATE_MENU')
    bigpic = current_picture(session.game).get('kind') == 'BIGPIC' and not is_roster(decision) and not top_menu
    draw_frame(frame, assets, 'combat' if combat else 'party' if top_menu else 'full' if bigpic else 'explore')
    if combat:
        draw_battle(frame, controller, assets)
    else:
        if not bigpic and not top_menu and not session.game.vm.display.get('blank'):
            view3d.draw(frame, state, session.game.geo.map, assets, area=controller.area_map, sky_choices=session.game.vm.display.get('sky'))
        if not top_menu and (not is_roster(decision) or decision['info'].get('spell')): draw_picture(frame, session.game, elapsed)
        if not bigpic and (state.party or not top_menu):
            draw_roster(frame, controller, state, session.game.vm.display, assets, top_menu)
        if decision and decision['kind'] in ('CAMP_MENU', 'SHOP_MENU'):
            draw_status(frame, session.game, decision, assets)
    lines = wrapped_text('' if top_menu else controller.text)
    for row, line in enumerate(lines[-1:] if combat else lines[-6:], 23 if combat else 17):
        frame.text(1, row, line, assets, 10 if state.mode == 2 else getattr(session.game.vm, 'text_color', 15), 38)
        prefix=session.game.vm.display.get('damage_prefix')
        if not combat and prefix and prefix[0]==session.game.vm.text_epoch and row-17<prefix[1]:
            frame.text(1,row,line,assets,prefix[2],38)
    if decision and decision['info'].get('purpose') == 'treasure leave':
        warning = 'There is still treasure left.  '
        for row, line in enumerate(wrapped_text(warning + 'Do you want to go back and claim your treasure?'), 17):
            frame.text(1, row, line, assets, 15)
        frame.text(1, 17, warning, assets, 10)
    if decision is None:
        frame.text(0, 24, session.result or 'Closed', assets, 14, 40)
        return frame
    items = menu_items(decision, session.game)
    info = decision['info']
    if info.get('purpose')=='script damage':
        frame.text(0,24,decision['options'][0],assets,13 if info.get('page') else 15,40)
    elif is_roster(decision):
        frame.text(0, 24, 'Select Exit' if any(v is None for v in decision['options']) else 'Select', assets, 10)
        frame.text(0, 24, 'S', assets, 15)
    elif items:
        compact = compact_menu(items, decision)
        if compact:
            if decision['kind'] == 'MOVE' and controller.move_mode:
                items = [(-3, 'e', 'Exit')]
            pages = menu_pages(items)
            visible = pages[min(controller.page, len(pages) - 1)]
            col = 0
            if decision['info'].get('door'):
                frame.text(0, 24, 'Locked. ', assets, 13); col = 8
            elif decision['info'].get('purpose') == 'take':
                frame.text(0, 24, 'Take: ', assets, 13); col = 6
            chosen = controller.selected if any(i == controller.selected for i, _, _ in items) else items[0][0]
            for index, key, label in visible:
                selected = index == chosen
                frame.text(col, 24, label, assets, 0 if selected else 15 if is_ack(decision) else 10, background=15 if selected else 0)
                offset = label.lower().find(key)
                if offset >= 0 and not selected:
                    frame.text(col + offset, 24, label[offset], assets, 15)
                col += len(label) + 1
            if len(pages) > 1:
                frame.text(1, 22, 'PgUp/PgDn menu %d/%d' % (controller.page + 1, len(pages)), assets, 14, 38)
        else:
            if not combat and not top_menu and not info.get('vertical'):
                draw_frame(frame, assets, 'full')
                frame.rect(8, 8, 304, 120, 0)
            draw_list(frame, controller, items, assets, combat=combat)
    else:
        draw_input(frame, controller, assets)
    prompt = (controller.error or info.get('prompt', '') if compact_menu(items, decision) else '') if items else ''
    if is_roster(decision): prompt = controller.error or ('' if info.get('spell') or info.get('action')=='trade item' else info.get('prompt') or 'Choose a member: Up/Down, then Return.')
    if prompt and info.get('purpose') not in ('quit to DOS','money left behind'):
        lines = textwrap.wrap(str(prompt), 38)[-1 if combat else -6:]
        for row, line in enumerate(lines, (24 if combat else 23) - len(lines)):
            frame.text(1, row, line, assets, 14, 38)
    draw_service(frame, controller, assets)
    overlay(frame, controller, assets)
    return frame


class Window:
    def __init__(self, session, *, hidden=False):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.controller, self.assets = Controller(session, presentation=True), Assets()
        self.controller.autosave_enabled = True
        self.controller.remember()
        self.root.title('SilverMachine - F10 Save / Load / Quit - F2 Map')
        self.root.resizable(False, False)
        self.photo = tk.PhotoImage(master=self.root, width=WIDTH * SCALE, height=HEIGHT * SCALE)
        self.label = tk.Label(self.root, image=self.photo, borderwidth=0, highlightthickness=0)
        self.label.pack()
        self.root.bind('<KeyPress>', self.key)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.closed = False
        self.refresh()
        self.timer = self.root.after(100, self.animate)
        if not hidden:
            self.root.deiconify()

    def refresh(self):
        self.frame = render(self.controller, self.assets, time.monotonic())
        self.photo.put(self.frame.tk_rows(1), to=(0, 0))
        self.photo.tk.call(str(self.photo), 'copy', str(self.photo),
                           '-from', 0, 0, WIDTH, HEIGHT, '-to', 0, 0, '-zoom', SCALE, SCALE)

    def key(self, event):
        if event.keysym == 'F12':
            self.frame.save(LOCAL / 'ui_current.png')
        else:
            self.controller.key(event.keysym, event.char)
            if self.controller.quit_requested:
                self.close()
            else:
                self.refresh()
        return 'break'

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.root.after_cancel(self.timer)
        try:
            self.controller.autosave()
        finally:
            self.controller.session.close()
            self.root.destroy()

    def animate(self):
        if self.closed:
            return
        display = current_picture(self.controller.session.game)
        if self.controller.presenting() or display.get('kind') == 'PIC' or (display.get('kind') == 'SPRIT'
                and display.get('frame') == 0 and display.get('pic', 255) != 255):
            self.refresh()
        if self.controller.quit_requested:
            self.close()
            return
        self.timer = self.root.after(10 if self.controller.presenting() else 100, self.animate)

    def run(self):
        self.root.mainloop()


SOUND_COMMANDS = tuple(range(2, 13))
ARROW, STEP, DOWNED, HIT, MISS, STRIKE, SWING, SLING = 12, 10, 5, 4, 3, 7, 9, 6


def event_sounds(event, last):
    kind, actor, sprite = event['kind'], event.get('actor'), event.get('sprite', 0) & 127
    first = (last[0], last[1]) != (kind, actor)
    if kind == 'move': return [STEP]
    if kind == 'death' and first: return [DOWNED]
    if kind == 'flash' and first: return [HIT if sprite == 9 else MISS]
    if kind == 'swing' and event.get('spell'): return [{47: 11, 51: 8}.get(event['spell'], 2)]
    if kind == 'sound' and event.get('cue') == 'cast': return [2]
    if kind == 'missile' and not event.get('spell') and last[0] == 'redraw' and last[3] and sprite in (0, 1, 2, 3, 7, 8):
        return [ARROW, ARROW if sprite < 3 else SLING if sprite == 8 else SWING]
    if kind == 'message':
        text = event.get('text') or ''
        new = text[len(last[2]):] if text.startswith(last[2]) else text
        if 'Hitting for' in new or 'slays helpless' in new: return [STRIKE]
        if 'and Misses' in new: return [SWING]
    return []


def layout(controller):
    game, decision = controller.session.game, controller.session.decision
    regions = []
    result = dict(regions=regions, selected=controller.selected, roster_selected=game.s.sel,
                  revision=[decision and decision['i'], decision and decision['hash'],
                            controller.page, controller.selected, controller.entry,
                            controller.area_map, controller.files.active, controller.move_mode, controller.files.mode, controller.files.page])
    result['sound'] = [list(e) for e in controller.sound_events]
    if controller.presenting():
        result['animating'] = True
        return result
    if controller.files.active:
        regions.extend(controller.files.regions())
        return result
    picker = controller.file_picker()
    if picker is not None:
        regions.extend(picker.regions())
        return result
    if decision is None:
        return result
    if decision['info'].get('action') == 'continue-battle':
        regions.extend(dict(rect=(x,192,w,8),key=dict(keysym=k,char=k)) for x,w,k in ((128,24,'y'),(160,16,'n')))
        return result

    def add(rect, **action):
        regions.append(dict(rect=rect, **action))

    def key(rect, keysym, char=''):
        add(rect, key=dict(keysym=keysym, char=char))

    if decision['kind'] == 'CREATE_ICON':
        col = 17 if getattr(controller, 'icon_phase', '') == 'confirm' else 0
        for _, hotkey, label in icon_bar(controller):
            key((col*8, 192, len(label)*8, 8), hotkey, hotkey); col += len(label)+1
        return result
    if decision['kind'] == 'CREATE_ADD' and getattr(controller, 'add_source', False):
        for col, word in ((16, 'Secret'), (23, 'Curse'), (29, 'Exit')):
            key((col*8, 192, len(word)*8, 8), word[0].lower(), word[0].lower())
        return result
    if decision['kind'] == 'CREATE_MODIFY':
        col = 8
        for word in ('Add', 'Subtract', 'Keep', 'Exit'):
            key((col*8, 192, len(word)*8, 8), word[0].lower(), word[0].lower()); col += len(word)+1
        return result
    items = menu_items(decision, game)
    compact = compact_menu(items, decision)
    roster = is_roster(decision)
    combat = bool(game.s.g.get('combat.active'))
    bigpic = current_picture(game).get('kind') == 'BIGPIC'
    key((8, 184 if combat else 136, 304, 8 if combat else 48), 'Return')
    if roster:
        key((0, 192, 48, 8), 'Return')
        if None in decision['options']: key((56, 192, 32, 8), 'Escape')
        for index, value in enumerate(decision['options']):
            member = index if decision['kind'] == 'WHO' else value
            if member is not None:
                add((136, (4 + member) * 8, 176, 8), select=index)
    elif not items:
        key((0, 192, 320, 8), 'Return')
    elif compact:
        if decision['kind'] == 'MOVE' and controller.move_mode: items = [(-3, 'e', 'Exit')]
        pages = menu_pages(items)
        items = pages[min(controller.page, len(pages) - 1)]
        col = (14 if decision['kind'] == 'CREATE_ROLL' else
               len('Save ' + decision['info']['character'] + '? ') if decision['kind'] == 'CREATE_SAVE' else
               len('Are you sure? ' if decision['info'].get('confirmation') else 'Drop ' + decision['info']['character'] + ' forever? ') if decision['kind'] == 'CREATE_REMOVE' else
               len(decision['info'].get('prompt', '')) if decision['kind'] == 'CREATE_EXIT' else
               8 if decision['info'].get('door') else 0)
        for _, hotkey, label in items:
            key((col * 8, 192, min(len(label) * 8, 320 - col * 8), 8), hotkey, hotkey)
            col += len(label) + 1
    else:
        x, width, top, count = list_geometry(decision, combat)
        page = min(controller.page, max(0, (len(items) - 1) // count))
        if decision['kind'] == 'CREATE_MENU': regions.clear()
        for row, (index, _, _) in enumerate(items[page * count:(page + 1) * count], top):
            add((x * 8, row * 8, width * 8, 8), select=index)
        if decision['kind'] == 'MENU' and decision['info'].get('vertical'):
            key((0, 192, 48, 8), 'Return'); return result
        if decision['kind'] == 'CREATE_MENU' and len(items) <= count:
            key((144, 192, 48, 8), 'Return')
            return result
        if decision['kind'] in ('CREATE_RACE', 'CREATE_GENDER', 'CREATE_CLASS', 'CREATE_ALIGNMENT'):
            key((0, 192, 48, 8), 'Return'); key((56, 192, 32, 8), 'Escape')
            return result
        key((0, 192, 32, 8), 'n', 'n')
        key((40, 192, 32, 8), 'p', 'p')
        if any(v is None or v in EXITS for v in decision['options']):
            key((80, 192, 32, 8), 'e', 'e')
        pages = max(1, (len(items) + 9) // 10)
        col = len('Next Prev      %d/%d ' % (page + 1, pages))
        key((col * 8, 192, min(96, 320 - col * 8), 8), 'Return')
    covered = decision['info'].get('purpose') in ('view', 'effects', 'appraise', 'appraisal') or decision['kind'] == 'CREATE_TRAIN'
    if compact and not roster and not combat and not bigpic and not covered:
        if 'char-up' in (decision['options'] or ()):
            for index, _ in enumerate(game.s.party[:11]):
                add((136, (4 + index) * 8, 176, 8), roster=index)
        if decision['kind'] == 'MOVE' and not controller.area_map:
            origin, size = view3d.ORIGIN, view3d.SIZE
            for third, keysym in enumerate(('Left', 'Up', 'Right')):
                keys = ([] if controller.move_mode else [dict(keysym='m', char='m')]) + [dict(keysym=keysym, char='')]
                cursor = ('turn-left', 'forward', 'turn-right')[third]
                if third == 1 and game.geo.passage(game.s, game.s.x, game.s.y, game.s.dir) in (2, 3): cursor = 'door'
                add((origin + third * size / 3, origin, size / 3, size), keys=keys, cursor=cursor)
    if combat and decision['kind'] == 'TARGET':
        x0, y0 = player_viewport(controller)
        chars, records = game.s.chars(), game.s.g['combat.records']
        for index, value in reversed(list(enumerate(decision['options']))):
            position = target_position(game, value)
            if position is None:
                continue
            width = height = 24
            if isinstance(value, int):
                if not game.s.g['combat.positions'][value][2] or not chars[value].b[0x1A7]:
                    continue
                pixels, _ = icon(game, chars[value], records[value][9], controller=controller)
                width, height = len(pixels[0]), len(pixels)
            x, y = 8 + (position[0] - x0) * 24, 8 + (position[1] - y0) * 24
            left, top, right, bottom = max(8, x), max(8, y), min(176, x + width), min(176, y + height)
            if left < right and top < bottom:
                add((left, top, right - left, bottom - top), select=index)
    return player_layout(controller, result)
