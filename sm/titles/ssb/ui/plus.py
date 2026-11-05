"""GU-117: CBODY selection at icon composition, never in a native record."""
import hashlib
from sm.titles.ssb import rec

# Inspected CBODY 0..31 in all four blocks (small/large, idle/action).
# Each pair is bare hand / shield; missing shield art retains the weapon.
BODIES = dict(unarmed=(0, 21), bow=(1, 1), sword=(7, 24), dagger=(5, 21),
              spear=(3, 4), mace=(9, 23), flail=(8, 25), hammer=(2, 20),
              axe=(10, 26), sling=(16, 16), staff=(19, 19), pick=(6, 22))
# ITEMS type, not a localized item name. Crossbow -> bow, two-handed sword
# -> sword, dart -> dagger. Polearms -> spear; morning star -> mace.
WEAPONS = {
    1: 'axe', 2: 'axe', 3: 'mace', 4: 'dagger', 5: 'dagger', 6: 'hammer',
    7: 'spear', 8: 'mace', 9: 'mace', 10: 'pick', 11: 'spear', 13: 'sword',
    14: 'spear', 15: 'staff', 16: 'sword', 17: 'sword', 18: 'sword',
    19: 'sword', 20: 'sword', 21: 'spear', 22: 'bow', 23: 'bow', 24: 'bow',
    25: 'bow', 26: 'bow', 27: 'bow', 28: 'sling', 29: 'sling',
    60: 'mace', 63: 'sword', 66: 'dagger', 67: 'staff', 69: 'pick',
    70: 'flail', 71: 'spear', 94: 'mace', 97: 'sword', 100: 'dagger', 101: 'sling',
}


def identity(b):
    """Presentation-only identity survives save/load, level and equipment changes."""
    return hashlib.sha256(bytes(b[:1 + b[0]]) + bytes((b[0x6B], b[0x11F]))).hexdigest()


def default_body(b):
    # ov19:39E7..3AA8 default, read without calling the mutating creation helper.
    return 23 if b[0x111] else 1 if b[0x115] else 24 if b[0x114] or b[0x113] else 29 if b[0x116] else 5


def body(character, manual):
    b = character.b
    if b[0x154] != default_body(b) or manual.get(identity(b)) == b[0x154]:
        return b[0x154]
    slots = rec.readied(character)
    weapon, shield = slots[0], slots[1] is not None
    kind = 'unarmed' if weapon is None else WEAPONS.get(weapon[0x2E])
    if kind is None: return b[0x154]  # Unknown/special attacks retain native art.
    if b[0x116] and not any(b[0x111:0x116]) and not shield:
        return {'unarmed': 27, 'staff': 28, 'dagger': 29, 'sling': 31}.get(kind, BODIES[kind][0])
    return BODIES[kind][int(shield)]


def area_map(game):
    """Read both sides of every GEO cell, including this visit's door changes."""
    s, grid = game.s, game.geo.map
    result = dict(source='Current area from your GEO data; opened doors from this visit.',
                  area=f'{s.dataset}/{s.block}', x=s.x, y=s.y, facing=s.dir,
                  directions=['North', 'East', 'South', 'West'])
    if grid is None or not s.r0[0xE6]:
        return dict(result, available=False, message='This location has no loaded 3D area grid.')
    return dict(result, available=True, width=16, height=16, record=grid.id,
                cells=[dict(x=x, y=y, walls=list(grid.cells[y*16+x].walls),
                            passages=[game.geo.passage(s, x, y, f) for f in (0, 2, 4, 6)],
                            attribute=grid.cells[y*16+x].attr) for y in range(16) for x in range(16)])


def rules():
    """Decoded tables are fetched from the selected executable, never bundled."""
    from sm.titles.ssb import data
    from sm.titles.ssb.units import magic
    from .screen import string
    ds = data.stexe()
    classes = [string(0xB8B + 27*i, 26) for i in range(7)]
    return dict(source='Your executable, read through the engine attack, saving throw and spell tables.',
                classes=classes,
                attacks=[dict(level=lv, values=[60-ds[0x4C0C+19*c+lv] for c in range(7)]) for lv in range(1, 19)],
                saves=[dict(class_name=classes[c], level=lv, values=list(ds[0x5592+90*c+5*lv:0x5597+90*c+5*lv]))
                       for c in range(7) for lv in range(1, 18)],
                spells=[dict(id=i, name=magic.spell_name(i), class_name=classes[{0:0, 1:1, 3:5}.get(magic.spell(i)[0], 6)]
                             if magic.spell(i)[0] in (0, 1, 3) else 'Special', level=magic.spell(i)[1],
                             camp=bool(magic.spell(i)[7]), combat=bool(magic.spell(i)[11])) for i in range(1, 118)])


def gallery():
    """Enumerate existing picture records; no names or image bytes in source."""
    import re
    from sm import dax
    from sm.titles.ssb.data import SECRET
    from sm.files import file_index
    return dict(source='Picture archives in your selected game folder.', pictures=[dict(file=name, record=rid)
                for name in sorted(file_index(SECRET)) if re.fullmatch(r'(PIC|BIGPIC|FINAL|SPRIT)\d+\.DAX', name)
                for rid in sorted(dax.load(name[:-4], SECRET))])


def picture(file, record, frame=0):
    """Only catalogued pictures are addressable; palette indices remain in memory."""
    from sm.titles.ssb import art
    if dict(file=file, record=record) not in gallery()['pictures']: raise ValueError('Unknown gallery picture')
    width, height, frames = art.picture(file, record)
    if not 0 <= frame < len(frames): raise ValueError('Unknown picture frame')
    return dict(width=width, height=height, frames=len(frames), frame=frame,
                palette=art.PALETTE, pixels=[list(row) for row in frames[frame]])


def character(b):
    from .screen import pstring, string
    return dict(name=pstring(b, maximum=15), class_name=string(0xB8B+27*b[0x6C], 26),
                levels='/'.join(str(n) for n in b[0x111:0x118] if n), hp=b[0x1B5], max_hp=b[0x70],
                ac=60-b[0x1AB], thac0=60-b[0x1AA], saves=list(b[0xE8:0xED]))


def roster(controller):
    from pathlib import Path
    from sm.titles.ssb import save
    from .screen import available_slots, slot_directory
    root = controller.files.root
    saved = []
    for slot in available_slots(root):
        try:
            contents = save.load(slot_directory(slot, root), slot)
            saved.append(dict(slot=slot, members=[character(c.data) for c in contents['party']]))
        except (OSError, ValueError, KeyError, IndexError):
            saved.append(dict(slot=slot, error='This save cannot be read.'))
    individuals = []
    for file in sorted(Path(root).glob('*.WHO')):
        try:
            raw = file.read_bytes()
            if len(raw) != 439: raise ValueError('record size')
            individuals.append(dict(file=file.name, **character(raw)))
        except (OSError, ValueError, IndexError):
            individuals.append(dict(file=file.name, error='This character cannot be read.'))
    return dict(source='Current party and native saves in your selected save folder.',
                party=[character(c.b) for c in controller.session.game.s.party], saved=saved, characters=individuals,
                transfer='Party transfer needs another supported title and its verified import rules. This alpha offers the SSB roster.')


def guide(game):
    """Static sites from our decoder: possible events, never promised rewards."""
    import re
    from sm import ecl, dax
    from sm.titles.ssb import data
    from .screen import pstring, string
    monsters = dax.load('MON1CHA', data.SECRET)
    currencies = [string(0xE60 + 11*i, 10) for i in range(7)]
    literal = lambda operand: ecl.word(operand) if operand[0] in (0, 2) else None
    areas = []
    for (dataset, block), code in sorted(data.records().items()):
        sites = ecl.trace(code)[1]
        exits, entries, encounters, rewards = set(), set(), set(), []
        for op, operands, _ in sites.values():
            if operands is None: continue
            if op == 0x20 and operands[0][0] in (0, 2): exits.add(ecl.word(operands[0]))
            if op == 0x0B:
                rid, count = literal(operands[0]), literal(operands[1])
                name = pstring(monsters[rid], maximum=15) if rid in monsters else 'Variable encounter'
                encounters.add(name + (' × %d' % (count or 1) if count is not None else ' · variable count'))
            if op == 0x27:
                money = [('%d %s' % (literal(o), currencies[i])) if literal(o) is not None else ('Variable ' + currencies[i])
                         for i, o in enumerate(operands[:7]) if literal(o) != 0]
                item = literal(operands[7])
                if item != 255: money.append('Variable items' if item is None else 'Random items' if item >= 128 else 'Item group %d' % item)
                if money: rewards.append(', '.join(money))
            for operand in operands:
                if operand[3]:
                    entries.update(int(m) for m in re.findall(r'journal\s+entr(?:y|ies)\s*#?\s*(\d+)', operand[3], re.I))
        areas.append(dict(area=f'{dataset}/{block}', current=(dataset, block)==(game.s.dataset, game.s.block),
                          encounters=sum(op == 0x24 for op, _, _ in sites.values()),
                          treasures=sum(op == 0x27 for op, _, _ in sites.values()),
                          exits=sorted(exits), entries=sorted(entries), monsters=sorted(encounters), rewards=sorted(set(rewards))))
    return dict(source='Generated at runtime from your area scripts using our ECL decoder.', areas=areas,
                note='These are possible script events, not a walkthrough or a list of completed quests. Conditional events may never occur.')


def tab_data(controller, tab, query):
    game = controller.session.game
    if tab == 'map': return area_map(game)
    if tab == 'rules': return rules()
    if tab == 'gallery': return gallery()
    if tab == 'picture': return picture(query.get('file', [''])[0], int(query.get('record', ['-1'])[0]), int(query.get('frame', ['0'])[0]))
    if tab == 'guide': return guide(game)
    if tab == 'roster': return roster(controller)
    raise ValueError('Unknown Plus tab')
