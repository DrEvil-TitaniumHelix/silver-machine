from pathlib import Path
from . import title

_SOURCE = Path(__file__).resolve().parents[2] / 'cok' / 'ui' / 'screen.py'
exec(compile(_SOURCE.read_text(encoding='utf-8').replace("'cok.", "'dkk.").replace("    places = step['actors'] if isinstance(step,dict) and 'actors' in step else [(r['x'],r['y'],r['size']) for r in data['actors']]", "    places = step['actors'] if isinstance(step,dict) and 'actors' in step else string_places(controller,progress) or [(r['x'],r['y'],r['size']) for r in data['actors']]").replace("'Stop Resting? '", "'Stop resting? '").replace("'Range = %d'%distance", "'Range = %d'%decision['info'].get('range',distance)").replace("i = marked if target_mode and marked>=0 else data['actor']; c,r", "i = marked if (target_mode or spell_aim) and marked>=0 else panel_of(data:=step_data(data,step)); c,r").replace('    if not target_mode or marked>=0:', '    if (marked>=0 if target_mode or spell_aim else data.get("panel", 0)>=0) and draw_panel(frame,assets,game,battle,data,i,(target_mode or spell_aim) and marked>=0):').replace('    elif isinstance(step,str):\n        frame.rect(184,80,128,96,0)\n        for y,text in enumerate(textwrap.wrap(step,16)[:6],11): frame.text(23,y,text,assets,10,16)\n', '    elif isinstance(step,str): draw_fight_message(frame,assets,battle,step)\n').replace('if cursor and (target_mode or spell_aim or int(elapsed*100)%80<30):', 'if cursor and not battle_over(game,decision) and not move_stepped(controller,decision) and aim_rows(controller,progress) is None:').replace('tile = battle.terrain(battle.tile(x+ox,y+oy),3)', 'tile = arena_code(battle,x+ox,y+oy)').replace('frame.blit(8+x*24,8+y*24,pixels)\n', 'frame.blit(8+x*24,8+y*24,pixels); arena_overlay(frame,assets,battle,x+ox,y+oy,8+x*24,8+y*24)\n').replace("'and is Dying'", "', and is dying'").replace('magic.spell(spell).name', 'magic.spell(game, spell).name').replace("'The party makes camp...'", "'the party makes camp'").replace("if game.s.mode == 6 else game.vm.display", "if game.s.mode == 6 else dict(kind='PIC', id=59, dataset=game.s.dataset) if game.s.mode == 2 else game.vm.display").replace("big = game.s.mode != 6 and", "big = game.s.mode not in (2, 6) and").replace("if game.s.mode != 6 and not game.vm.display.get('blank'): draw_view", "if game.s.mode not in (2, 6) and not game.vm.display.get('blank'): draw_view").replace("13 if prompt == 'Character name: ' else 10", "entry_colour(decision)").replace("frame = menu.render(game, -1)", "frame = menu.frame(game) if member_who(decision) else menu.render(game, -1)").replace("if controller.entry and at < 40: frame.text(at, 24, controller.entry, assets, 15, 40-at)", "if entry_text(controller, decision) and at < 40: frame.text(at, 24, entry_text(controller, decision), assets, 15, 40-at)").replace("frame.text(15, 24, 'Select', assets, 0, background=15); frame.text(22, 24, 'Exit', assets, 10)", "frame.text(15, 24, 'Select', assets, 0, background=15)").replace("if spell: info = dict(info, window=", "if spell: info = spell_info(info, spell) if listed(decision) else dict(info, window=").replace("assets.combat_picture('COMSPR',25)[0],transparent=0,clip=(8,8,176,176))", "assets.combat_picture('COMSPR',25)[0],transparent=0,clip=(8,8,176,176),colours=assets.view_tables['icon_palette'])").replace("frame.text(len(label)+1,24,'Done',assets,0,background=15)", "frame.text(len(label),24,'Done',assets,0,background=15)").replace("col=len('Move/Attack, Move Left = %d'%(actor['movement']//2))+1", "col=len('Move/Attack, Move Left = %d'%(actor['movement']//2))").replace("frame.text(0,24,'Aim:',assets,13); col=4", "frame.text(0,24,'aim: ',assets,13); col=5").replace('            col=4\n            for label in controller.aim_options():', '            col=5\n            for label in controller.aim_options():').replace("wrapped = town.wrapped_text(('  ' if past else '')+paragraph.lstrip() if damage else paragraph)", "wrapped = town.wrapped_text(('  ' if past else '')+paragraph.lstrip() if damage else paragraph) or ['']").replace("and game.vm.display.get('kind') == 'BIGPIC'", "and shown_display(game).get('kind') == 'BIGPIC'").replace("and vm.display.get('kind') == 'BIGPIC'", "and shown_display(game).get('kind') == 'BIGPIC'").replace("if game.s.mode == 2 else game.vm.display", "if game.s.mode == 2 else shown_display(game)").replace("decision['kind'] == 'ALTER_SPEED' and 'speed' in decision['info']", "decision['kind'] == 'ALTER_SPEED' and 'cok_speed' in decision['info']").replace("elif icon_screen(controller): draw_icon_screen(frame, game, assets)", "elif icon_screen(controller): draw_icon_screen(frame, game, assets, controller)").replace('marked=battle.occupancy().get(cursor,-1)', 'marked=aim_marked(battle,data,cursor) if spell_aim else battle.occupancy().get(cursor,-1)').replace("size=1 if spell_aim or target_mode and controller.aim_manual or marked<0 else battle.record(marked)['size']\n    if cursor and not battle_over(game,decision) and not move_stepped(controller,decision) and aim_rows(controller,progress) is None:\n        for dx,dy in battle.footprint(size or 1):", "size=(1 if spell_aim or controller.aim_manual or marked<0 else battle.record(marked)['size'] or 1) if target_mode or spell_aim else battle.record(data['actor'])['size']\n    if cursor and not battle_over(game,decision) and not move_stepped(controller,decision) and aim_rows(controller,progress) is None:\n        for dx,dy in battle.footprint(size):").replace("frame.text(18,24,'Target' if 'Target' in decision['options'] else 'Exit',assets,0,background=15)\n", "frame.text(18,24,'Target' if 'Target' in decision['options'] else 'Exit',assets,0,background=15)\n            if 'range' in decision['info']: frame.text(0,23,'Range = %d'%decision['info']['range'],assets,10,40)\n").replace("for y,text in enumerate(textwrap.wrap(str(decision['info'].get('prompt','')),16)[:6],11): frame.text(23,y,text,assets,10,16)", "draw_fight_message(frame,assets,battle,str(decision['info'].get('prompt','')))").replace("        row=13\n        for text in textwrap.wrap(step['result'],16)[:3]:", "        row=13 if step['result'] else 11\n        for text in attack_result_lines(step):").replace("    bolt = None\n", "    bolt = None\n    shot = missile_shot(controller, step, progress, (ox, oy))\n    shot = shot[:2] + ([shot[2:]],) if shot else scatter_shot(controller, step, progress) or fall_view(step)\n    if shot: ox, oy = shot[:2]\n").replace("    if isinstance(step,dict) and step['kind']=='bolt':\n", "    if isinstance(step,dict) and step['kind']=='bolt' and not shot:\n").replace("    if bolt:\n", "    for _sx, _sy, _pic in (shot[2] if shot else ()): frame.blit(8+_sx*8,8+_sy*8,_pic,transparent=0,colours=assets.view_tables['icon_palette'],clip=(8,8,176,176))\n    if bolt:\n").replace("        if not fighting and s.g.get('dkk.battle', {}).get('active'): self.report.insert(0, dict(kind='begin'))\n", "").replace("wild,random = assets.combat_picture('DUNGCOM' if game.vm.is3d() else 'WILDCOM',1),assets.combat_picture('RANDCOM',1)", "wild,random = combat_sheet(game,assets),()").replace("    if isinstance(step,dict) and step['kind']=='move' and step.get('actors'):", "    if isinstance(step,dict) and 'view' in step and not shot: ox,oy = step['view'][:2]\n    elif isinstance(step,str) and (seen:=ended_view(controller.report,progress[0])) is not None: ox,oy = seen\n    elif isinstance(step,dict) and step['kind']=='move' and step.get('actors'):").replace("assets.combat_icon(game,i,1 if isinstance(step,dict) and step['kind']=='attack' and step.get('actor')==i else 0)", "posed_icon(assets,game,step,i)").replace("        if not top_list: draw_picture(frame, game, assets, elapsed)", "        if not top_list: draw_picture(frame, game, assets, elapsed, controller, True)").replace("    draw_picture(frame, game, assets, elapsed)\n    lines, colours = script_text(game)", "    draw_picture(frame, game, assets, elapsed, controller)\n    lines, colours = script_text(game)").replace('    progress = report_step(controller)\n    step = controller.report[progress[0]]', '    progress = report_step(controller)\n    if progress is not None and progress[0] >= len(controller.report): progress = None\n    step = controller.report[progress[0]]').replace("decision['kind'] in ('MOVE', 'CAMP_MENU') or at_outpost(self.session)", "decision['kind'] in ('MOVE', 'CAMP_MENU') or decision['info'].get('world_menu') or at_outpost(self.session)").replace('else controller.aim_cell if target_mode else', "else (controller.aim_cell or battle.position(data['actor'])) if target_mode else").replace('    if cursor and not battle_over(game,decision) and not move_stepped(controller,decision) and aim_rows(controller,progress) is None:\n        for dx,dy in battle.footprint(size):', '    cursor,size = turn_box(controller,progress,cursor,size)\n    if cursor and not battle_over(game,decision) and not move_stepped(controller,decision) and aim_rows(controller,progress) is None:\n        for dx,dy in battle.footprint(size):').replace('panel_of(data:=step_data(data,step))', 'panel_of(data:=step_data(data,stamped(controller.report,progress,step)))'), str(_SOURCE), 'exec'))

TABLES = {
    'sky': (50038, 16, '0810d61cad4464243dadeb745b1812cb695527ee358356450bde20a9a92bfc9b'),
    'slices': (50086, 70, '439f69253bc8097c9bd594b2974c322929a1d79df74eac4c6bc89ab2979cb416'),
    'icon_palette': (65486, 16, 'b17985999b92f7d2fd75c1ec625f7c1ae28fa559b935a826b557effff6df1dcb'),
    'icon_colors': (77710, 6, '2d21540386a1918e89ab038633ba8cf97aa68712c59f856fa03ba8faccc05e98'),
}
_FamilyAssets = Assets
_town = town


class _Town:
    wrapped_text = staticmethod(menu.wrapped_text)
    def __getattr__(self, name): return getattr(_town, name)


town = _Town()
NO_PICTURE = __import__('types').SimpleNamespace(parts=[__import__('types').SimpleNamespace(frames=[()])])


PICTURE_DISKS = {'PIC': {59: 4, 60: 4, 78: 4, 5: 5, 24: 5, 77: 5, 96: 5, 16: 6, 17: 6, 19: 6, 74: 6, 80: 6, 83: 7},
                 'SPRIT': {2: 4, 64: 4, 66: 4, 70: 4}}


WALL_DISKS = {1: 1, 2: 4, 3: 2, 4: 2, 5: 3, 6: 3, 7: 5}


def symbol_frames(raw):
    from sm.ui.art import _NIBBLES
    stride, size = raw[2] * 4, raw[0] * raw[2] * 4
    return tuple(tuple(b''.join(_NIBBLES[b] for b in raw[at + row:at + row + stride]) for row in range(0, size, stride)) for at in range(17, len(raw) - size + 1, size))


def picture_disk(family, ident, disk):
    if family == 'BIGPIC': return 1 if disk == 5 else disk
    return PICTURE_DISKS.get(family, {}).get(ident, disk)


class Assets(_FamilyAssets):
    def __init__(self, directory=None):
        super().__init__(directory)
        self.symbols = self.border
        self.border = [self.symbols[7]] * 20 + list(self.symbols)
        self.view_tables['combat_sides'] = self.part('dualPaneColumn')
        self.view_tables['spell_headings'] = b''.join(bytes([len(label)]) + label.encode('cp437').ljust(40, b'\0') for label in self.names('spellLevelLabels'))

    def picture(self, family, ident, dataset=1):
        if family == 'SKY': return NO_PICTURE
        return super().picture(family, ident, picture_disk(family, ident, dataset))

    @lru_cache(maxsize=16)
    def wall_sets(self, dataset, ids, filed=()):
        blocks, symbols = {}, ()
        for wallset, ident in enumerate(ids):
            if not 0 < ident < 0x8000: continue
            raw = self.records('WALLDEF%d' % WALL_DISKS.get(ident, dataset))[ident]
            for k in range(min(len(raw) // 780, 4 - wallset)):
                blocks[wallset + k + 1] = __import__('types').SimpleNamespace(types=tuple(tuple(raw[780 * k + t:780 * k + t + 156]) for t in range(0, 780, 156)))
            if wallset == 0: symbols = symbol_frames(self.records('8X8D%d' % WALL_DISKS.get(ident, dataset))[ident])
        return blocks, symbols

    def wall_tile(self, state, symbol, filed=()):
        _, symbols = self.wall_sets(state.dataset, tuple(state.walls), filed)
        if 0 < symbol < len(symbols) and symbol < 256: return symbols[symbol]
        return self.symbols[symbol - 256] if 256 <= symbol < 256 + len(self.symbols) else None

    @lru_cache(maxsize=8)
    def backdrop(self, ident, dataset):
        if not ident: return (decode(self.records('SKYGRND')[2]).parts[0].frames[0], decode(self.records('SKYGRND')[1]).parts[0].frames[0])
        return (decode(self.records('BACK%d' % WALL_DISKS.get(ident, dataset))[ident]).parts[0].frames[0],)

    def combat_picture(self, family, ident):
        if family == 'RANDCOM': return ()
        if family.startswith('CPIC'): family = 'CPIC1'
        return super().combat_picture(family,15 if (family, ident) == ('COMSPR', 25) else ident)

    def part(self, name):
        return super().part('borderTopRow' if name == 'topEdgeTiles' else name)


FIGHT_KEYS = ('space', 'Alt-m', 'Alt-q', 'Alt-a', 'Alt-r', 'Alt-d', 'Alt-x')
MOVE_KEYS = {'Up': 'forward', 'Left': 'turn-left', 'Right': 'turn-right', 'Down': 'turn-around'}
COMPASS_KEYS = {'Up': 'north', 'Prior': 'northeast', 'Right': 'east', 'Next': 'southeast', 'Down': 'south', 'End': 'southwest',
                'Left': 'west', 'Home': 'northwest'}
REST_EXIT_KEYS = ('Home', 'End', 'Prior', 'Next', 'Clear', 'Insert', 'Delete', 'KP_Begin', *('F%d' % n for n in range(1, 13) if n != 10))
EXTENDED_KEYS = (*COMPASS_KEYS, *REST_EXIT_KEYS, 'F10')
SCAN_CODES = dict(Home=0x47, Up=0x48, Prior=0x49, Left=0x4B, Clear=0x4C, KP_Begin=0x4C, Right=0x4D, End=0x4F, Down=0x50, Next=0x51,
                  Insert=0x52, Delete=0x53, F11=0x85, F12=0x86, **{'F%d' % n: 0x3A + n for n in range(1, 11)},
                  **{'Alt-' + c: n for row, first in (('qwertyuiop', 0x10), ('asdfghjkl', 0x1E), ('zxcvbnm', 0x2C), ('1234567890', 0x78))
                     for n, c in enumerate(row, first)})
STEP_KEYS = ('Clear', 'Insert', 'Delete', 'KP_Begin', *('F%d' % n for n in range(1, 13) if n != 10))
HIDDEN = ('char-up', 'char-down', 'char-first', 'escape', 'menu-left', 'menu-right', 'extended', *FIGHT_KEYS, *MOVE_KEYS.values(),
          *COMPASS_KEYS.values(), 'step')
YES_FIRST = frozenset(('scribe these spells?', 'save character?', 'is this icon ok?', 'do you wish to train?', 'stop resting?',
                       'use it?', 'abort spell', 'abort spell?', 'is it a deal?'))


SLOT_PROMPTS = ('save which game: ', 'load which game: ')


def menu_items(decision):
    if not decision or decision['options'] is None: return []
    slots = decision['kind'] == 'CREATE_SLOT' and decision['info'].get('prompt') in SLOT_PROMPTS
    items = [(i, str(value) if value is not None else 'Exit') for i, value in enumerate(decision['options'])
             if value not in HIDDEN and not (slots and value in (None, 'Exit')) and not (decision['kind'] == 'ALTER_LEVEL' and value == 'Exit')]
    if decision['kind'] == 'MENU' and len(items) == 1 and items[0][1] == OLD_CONTINUE: items = [(items[0][0], NEW_CONTINUE)]
    return items


def draw_location(frame, game, assets):
    from ..menu import misc_info
    display = game.vm.display
    text = display['misc_info'] if 'misc_info' in display else misc_info(game)
    if text: frame.text(17, 15, text, assets, 10, 22)


def yes_no_menu(decision):
    return bool(decision and decision['kind'] != 'MENU' and decision['options'] is not None
                and [label for _, label in menu_items(decision)] == ['Yes', 'No'] and 'char-up' not in decision['options']
                and not leave_question(decision))


def leave_question(decision):
    if not decision or decision['options'] is None or [label for _, label in menu_items(decision)] != ['Yes', 'No']: return None
    text = str(decision['info'].get('offer', ''))+str(decision['info'].get('prompt', ''))
    at = text.lower().find('do you want to go back')
    cleared = tuple(decision['info'].get('clear_first') or (True, False))
    return (text[:at], text[at:], not cleared[-1]) if at >= 0 else None


_family_pick_who, _family_draw_question = pick_who, draw_question


def member_who(decision):
    return bool(decision and decision['kind'] == 'VIEW_WHO' and decision['options'] and decision['options'][-1] == 'Exit')


def pick_who(decision):
    return _family_pick_who(decision) or member_who(decision)


def draw_question(frame, controller, assets):
    d = controller.session.decision
    if file_name(controller):
        prompt = str(d['info'].get('prompt', ''))
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, prompt, assets, 10, 40)
        if controller.entry: frame.text(len(prompt) + 1, 24, controller.entry, assets, 15, 39 - len(prompt))
        return
    if not member_who(d): return _family_draw_question(frame, controller, assets)
    query = str(d['info']['prompt']) + ' '
    frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, query, assets, 13); frame.text(len(query), 24, 'Select', assets, 0, background=15)


def yes_no_start(decision):
    if decision['info'].get('start') in (0, 1): return decision['info']['start']
    return 0 if str(decision['info'].get('prompt', '')).strip().lower() in YES_FIRST else 1


def fight_rows(decision):
    return bool(decision and decision['kind'] == 'COMBAT_ACTION' and decision['options'] and 'Quick' in decision['options'])


_family_compact = compact


def compact(decision):
    return fight_rows(decision) or yes_no_menu(decision) or bool(leave_question(decision)) or _family_compact(decision)


def fight_split(items):
    return next((n for n, (_, label) in enumerate(items) if label == 'Quick'), len(items)-1)+1


def draw_fight_rows(frame, controller, assets):
    items = menu_items(controller.session.decision); split = fight_split(items)
    frame.rect(0, 184, 320, 16, 0)
    for row, part in ((23, items[:split]), (24, items[split:])):
        col = 0
        for index, label in part: draw_word(frame, assets, col, label, index == controller.selected, row=row); col += len(label)+1


def fight_key(controller, decision, keysym, char):
    options, items = decision['options'], menu_items(decision)
    if keysym == 'space': return False
    if keysym.lower() == 'alt-d' or char == '5': keysym = 'space'
    if keysym in options: return controller.choose(options.index(keysym))
    indexes = [i for i, _ in items]; split = fight_split(items)
    at = indexes.index(controller.selected) if controller.selected in indexes else 0
    letter = char.upper() if len(char) == 1 else ''
    if letter and not letter.isdigit():
        hit = next((i for i, label in items if label[:1].upper() == letter), None)
        if hit is not None: return controller.choose(hit)
    if keysym in ('Return', 'KP_Enter'): return controller.choose(indexes[at])
    if keysym in ('Left', 'Right') or char in ('4', '6'):
        at = (at+(1 if keysym == 'Right' or char == '6' else -1)) % len(indexes)
    elif keysym in ('Up', 'Down') or letter in ('2', '8', 'H', 'P'):
        at = min(at+split, len(indexes)-1) if at < split else min(at-split, split-1)
    else: return False
    controller.selected = indexes[at]; controller.horizontal_choice = at
    return False


def sheet_info(game, char, info):
    from ..creation import F, CLERIC, MAGE, KNIGHT
    names, b = game.assets.names, char.b
    def name(table, index): return dict(enumerate(names(table))).get(index, '')
    levels = b[F['levels']:F['levels'] + 8]
    label = name('classNames', b[F['class']])
    if 0 < levels[CLERIC] < 128: label = name('deityNames', b[F['deity']]) + ' ' + label
    if 0 < levels[MAGE] < 128:
        at = next((i for i in range(len(label)) if label[i] == 'M' and label[i + 2:i + 3] == 'g'), len(label))
        label = label[:at] + name('robeOrderNames', b[F['robe_order']]) + ' ' + label[at:]
    if 0 < levels[KNIGHT] < 128: label += {1: ' of the Crown', 2: ' of the Sword', 3: ' of the Rose'}.get(b[F['knight_order']], '')
    return dict(info, status=b[F['status']], gender=name('genderNames', b[F['gender']]), age=int.from_bytes(b[F['age']:F['age'] + 2], 'little'),
                alignment=name('alignmentNames', b[F['alignment']]), race=name('raceNames', b[F['race']]), description=label,
                levels='/'.join(str(v) for v in levels if 0 < v < 128) or '0', experience=int.from_bytes(b[F['experience']:F['experience'] + 4], 'little', signed=True),
                hp_now=info['hp'], hp=info['hp_max'])


def viewed(game, name, index=None):
    named = lambda m: m is not None and bytes(m.b[1:1 + m.b[0]]).decode('cp437') == name
    chars = game.s.chars() if hasattr(game.s, 'chars') else game.s.party
    c = chars[index] if isinstance(index, int) and 0 <= index < len(chars) else getattr(game, 'trade_character', None)
    return c if named(c) else next((m for m in game.s.party if named(m)), None) or game.s.selc()


def sheet_view(controller):
    d, game = controller.session.decision, controller.session.game
    if not d: return None
    from .. import creation, inventory, rules
    if d['kind'] == 'CREATE_VIEW':
        c = viewed(game, d['info'].get('name'), d['info'].get('view_index'))
        return sheet_info(game, c, d['info']), c, None
    if coin_list(d):
        c = game.s.selc()
        copy = own_copy(c.b, c.items, c.effects)
        seen = getattr(controller, 'sheet_seen', None)
        if seen and seen.get('name') == bytes(c.b[1:1 + c.b[0]]).decode('cp437'): return sheet_info(game, copy, seen), copy, None
        return sheet_info(game, copy, inventory.sheet(game, copy)), copy, None
    if d['kind'] == 'CREATE_MODIFY':
        c = game.s.selc()
        copy = own_copy(c.b, c.items, c.effects)
        info = sheet_info(game, copy, inventory.sheet(game, copy))
        if d['info'].get('display_hp') is not None: info = dict(info, hp_now=d['info']['display_hp'])
        return info, copy, int(d['info'].get('field', 0))
    if d['kind'] not in ('CREATE_ROLL', 'CREATE_SAVE', 'CREATE_NAME') or icon_screen(controller): return None
    if creation.PENDING not in game.s.g: return None
    copy = own_copy(*game.s.g[creation.PENDING])
    return sheet_info(game, copy, inventory.sheet(game, copy)), copy, None


def own_copy(raw, items=(), effects=()):
    from .. import rules
    size = rules.Character.SIZE
    return rules.character(bytes(raw[:size]), tuple(bytes(i) for i in items), tuple(bytes(e) for e in effects), spells=bytes(raw[size:]) if len(raw) > size else None)


def sheet_frame(frame, game, assets):
    window_frame(frame, game, assets, 23)
    for x in range(1, 39):
        for y in (8, 16, 20): frame.blit(x * 8, y * 8, assets.symbols[4])
    left, right, middle = assets.part('combatLeftColumn') + assets.part('combatRightColumn')[:1], assets.part('combatRightColumn'), assets.part('combatMidColumn')
    for y in range(1, 23): frame.blit(0, y * 8, assets.symbols[left[y]]); frame.blit(39 * 8, y * 8, assets.symbols[right[y]])
    for y in range(8, 21): frame.blit(19 * 8, y * 8, assets.symbols[middle[y - 8]])


_family_sheet = draw_sheet


def draw_sheet(frame, game, assets, info, char=None, field=None):
    assets.view_tables.setdefault('sheet_sides', b''); assets.view_tables.setdefault('sheet_divider', b'')
    if 'status' in info:
        _family_sheet(frame, game, assets, info, char, field)
        from ..creation import F
        b = (char or game.s.selc()).b
        if b[F['active']] and b[F['level_up_ready']] and field != 6: frame.text(1, 1, info['name'], assets, 13)
        if field is not None and 0 <= field < 6:
            base, cur = b[F['abilities'] + 2 * field], b[F['abilities'] + 2 * field + 1]
            if cur != base or field == 0 and b[F['strength_extra']] != b[F['strength_extra_base']]: frame.text(12, 9 + field, '*', assets, 13)
    else: frame.rect(0, 0, 320, 192, 0)
    sheet_frame(frame, game, assets)


_family_icon_screen = icon_screen


def icon_screen(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'CREATE_ICON' and getattr(controller, 'icon_old', None)) or _family_icon_screen(controller)


def icon_record(game):
    from .. import creation
    c = own_copy(game.s.g[creation.PENDING][0] if creation.PENDING in game.s.g else game.s.selc().b)
    return tuple(town.field(c, k) for k in ('icon_head', 'icon_body', 'icon_size')) + tuple(town.field(c, 'icon_colors', j) for j in range(6))


def icon_seen(self, d):
    if not (d and d['kind'] == 'CREATE_ICON'): self.icon_old = self.icon_editing = None
    elif not d['info'].get('icon_state'): self.icon_editing = None
    elif not getattr(self, 'icon_editing', None): self.icon_old, self.icon_editing = icon_record(self.session.game), True


def draw_icon_screen(frame, game, assets, controller=None):
    d = controller and controller.session.decision
    new = icon_record(game)
    old = controller.icon_old if d and d['kind'] == 'CREATE_ICON' else new
    frame.rect(0, 0, 320, 192, 0); draw_frame(frame, game, assets, True, True)
    backdrop = assets.combat_picture('COMSPR', 25)[0]
    for icon, cell, row, label in ((old, 2, 6, 'old'), (new, 4, 12, 'new')):
        frames, palette = assets.party_icon(*icon[:3], icon[3:])
        for x, pose in ((32, 0), (104, 1)):
            frame.blit(x, 8+cell*24, backdrop, transparent=0, colours=assets.view_tables['icon_palette']); frame.blit(x, 8+cell*24, frames[pose], transparent=0, colours=palette)
        frame.text(8, row, label, assets, 15); frame.text(3, row+4, 'ready   action', assets, 15)


_family_spell_kind = spell_kind


def listed(decision):
    from ..magic_lists import TITLES
    return bool(decision and decision['kind'] in ('SPELL', 'COMBAT_SPELL') and decision['info'].get('title') in TITLES and 'selection' in decision['info'])


def spell_kind(decision):
    if not listed(decision): return _family_spell_kind(decision)
    from ..magic_lists import TITLES
    return TITLES.index(decision['info']['title']), decision['info']['title'], str(decision['info'].get('menu', ''))


def query_colour(query):
    return 13


def entry_colour(decision):
    return 13 if decision['kind'] == 'CREATE_NAME' else 10


def spell_info(info, spell):
    return dict(info, query=str(info.get('prompt', '')), menu=spell[2])


def listed_rows(controller, items, d):
    from .. import magic, magic_lists
    from ..inventory import IN_COMBAT
    game, char, mode = controller.session.game, spell_character(controller), spell_kind(d)[0]
    at = getattr(controller, 'view_item', None)
    item = char.items[at] if mode == 2 and at is not None and at < len(char.items) else None
    entries = magic_lists.generate_list(game, char, mode, item, d['kind'] == 'COMBAT_SPELL' or game.s.mode == IN_COMBAT)
    from sm.titles.cok.magic import list_start
    picks = [index for index, _ in items] if d['info'].get('menu') and int(d['info'].get('selection', 0)) != 5 else []
    if entries and not picks:
        top, bottom = map(int, str(d['info'].get('window', '1 5 38 22')).split()[1::2])
        mark = list_start(tuple(magic.spell(game, e.ident).level for e in entries), -1, mode in (2, 3, 6), bottom - top + 1)[0]
        picks = [0 if n == mark else -1 for n in range(len(entries))]
    headings, nodes, previous = controller.assets.view_tables['spell_headings'], [], 0 if mode in (2, 3, 6) else None
    for n, entry in enumerate(entries):
        level, label = magic.spell(game, entry.ident).level, magic_lists.line(game, entry)
        if previous is None or (level != previous if mode in (2, 3, 6) else level > previous):
            at = level * 41; nodes.append((None, headings[at + 1:at + 1 + headings[at]].decode('cp437')))
        previous = level
        nodes.append((picks[n] if n < len(picks) else -1, label))
    return nodes


def spell_rows(controller, items, decision=None):
    from .. import camp, magic
    game, d = controller.session.game, decision or controller.session.decision
    if listed(d): return listed_rows(controller, items, d)
    char, (kind, _, command) = spell_character(controller), spell_kind(d)
    table, counts, ids = magic._table(game.assets), [], None
    if d['info'].get('spell_ids'): ids = [int(value) for value in str(d['info']['spell_ids']).split()]
    elif kind == 0:
        held = magic.castable(game, char, d['kind'] == 'COMBAT_SPELL'); ids = [value for value, _ in held]; counts = [n for _, n in held]
    elif kind == 1: ids = camp.memorizable(char, camp.tables(game.assets))
    elif kind in (5, 6):
        pending = {}
        for value in camp.memory(char):
            if value > 127: pending[value & 127] = pending.get(value & 127, 0)+1
        ids = sorted(pending, key=lambda value: table[value-1].level); counts = [pending[value] for value in ids]; ids = [value | 128 for value in ids]
    if ids is not None and not command:
        items = [(-1, table[(value & 127)-1].name+(' (%d)' % counts[n] if counts and counts[n] > 1 else '')) for n, value in enumerate(ids)]
    if ids is None or len(ids) != len(items):
        ids = []
        for _, label in items:
            label = label.lstrip(' *').split(' (')[0]
            matches = [row for row in table if row.name == label]
            ids.append(matches[0].id if matches and len({row.level for row in matches}) == 1 else None)
    nodes, previous = [], 0 if kind in (2, 3, 6) else None
    headings = controller.assets.view_tables['spell_headings']
    for (index, label), value in zip(items, ids):
        if value is not None:
            level = table[(value & 127)-1].level
            if previous is None or (level != previous if kind in (2, 3, 6) else level > previous):
                at = level*41; nodes.append((None, headings[at+1:at+1+headings[at]].decode('cp437')))
            previous = level
        prefix = ' *' if value is not None and value > 127 or label.startswith(' *') else '  '
        nodes.append((index, prefix+label.lstrip(' *')))
    return nodes


_family_hold = render_hold


def render_hold(controller, event, elapsed=0):
    if 'frame' in event: return typed_hold_frame(controller, event)
    scene = event.get('scene')
    if 'state' not in event and scene is not None:
        from copy import copy
        from ..inventory import IN_COMBAT
        state = scene.s
        if state.mode != IN_COMBAT and getattr(state, 'monsters', None):
            painted = event['linked_shown'] if 'linked_shown' in event else len(state.party)
            state = copy(state); state.monsters = state.monsters[:max(0, painted - len(state.party))] if painted is not None else list(state.monsters)
        event = dict(event, state=state, display=scene.vm.display, map=scene.geo.map, walls_filed=())
    frame = _family_hold(controller, event, elapsed)
    if event.get('loading_notice'):
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, controller.session.game.assets.text('loadingMessage'), controller.assets, 10, 40)
    return frame


_family_held = Controller.held


def loaded_picture(self):
    game = getattr(self.session, 'game', None)
    runtime = getattr(getattr(game, 's', None), 'g', {}).get('dkk.runtime', {})
    if 'loads' in runtime: return runtime['loads']
    d = getattr(getattr(game, 'vm', None), 'display', None) or {}
    return (d.get('kind'), d.get('id')) if d.get('kind') in ('PIC', 'SPRIT') else None


def flush_on_load(self):
    picture = loaded_picture(self)
    if getattr(self, 'typeahead', None) and picture is not None and picture != getattr(self, 'typeahead_seen', picture): self.typeahead = []
    self.typeahead_seen = picture


def _held(self):
    flush_on_load(self)
    queue = self.queue()
    if queue and not queue[-1].get('typed_seen'):
        kept = typed_script_holds(self, queue); queue.clear(); queue.extend(kept)
    ending = getattr(self, 'hold_event', None)
    event = _family_held(self)
    if ending is not None and ending is not event and ending.get('flush_keys'): self.typeahead = []
    elif ending is not None and ending is not event and ending.get('discard'): discard_reads(self, ending['discard'])
    if event is None and getattr(self, 'typeahead', None) and not getattr(self, 'typing', False):
        self.typing = True
        try:
            while self.typeahead and _family_held(self) is None and self.session.decision is not None:
                asked = self.session.decision; self.key(*self.typeahead.pop(0))
                if self.session.decision is not asked and not (damage_page(asked) and asked['info'].get('color') == 15): self.typeahead = []
                flush_on_load(self)
        finally: self.typing = False
        event = _family_held(self)
    return event


def discard_reads(self, count):
    pending = list(getattr(self, 'typeahead', None) or [])
    while pending and count > 0:
        keysym, char = pending.pop(0)
        reads = [chr(0), chr(SCAN_CODES.get(keysym, 0))] if keysym in EXTENDED_KEYS or keysym.startswith('Alt-') else [char]
        for read in reads[:count]: control_key(self, read)
        if reads[count:] and keysym in SCAN_CODES: pending.insert(0, (reads[count], reads[count]))
        count -= len(reads[:count])
    self.typeahead = pending


Controller.held = _held




_family_picture = draw_picture


def shown_display(game):
    display = game.vm.display
    if display.get('kind') is None and not display.get('blank') and not game.vm.is3d() and game.s.r0[0x1F7] == 1 and game.s.mode != 6:
        return dict(display, kind='BIGPIC', id=112, dataset=game.s.dataset, frame=0, head=None, map_cursor=True)
    return display


def draw_picture(frame, game, assets, elapsed, controller=None, menu=False):
    still = dict(kind='PIC', id=60, dataset=game.s.dataset) if game.s.mode == 6 else dict(kind='PIC', id=59, dataset=game.s.dataset) if game.s.mode == 2 else game.vm.display
    if still.get('kind') == 'PIC': draw_still(frame, assets, still, controller, game, menu)
    else: _family_picture(frame, game, assets, elapsed)
    display = shown_display(game)
    if display.get('kind') == 'BIGPIC' and display.get('id') == 112 and display.get('map_cursor') and not game.vm.is3d() and game.s.mode not in (2, 6):
        marker = decode(assets.records('8X8D1')[204]).parts[0].frames[0]
        frame.blit((game.s.r0[0xC3] + 1) * 8, (game.s.r0[0xC4] + 1) * 8, marker)


def draw_still(frame, assets, display, controller=None, game=None, menu=False):
    try: record = assets.picture('PIC', display['id'], display['dataset'])
    except (KeyError, OSError): return
    frames = [(part, pixels) for part in record.parts for pixels in part.frames]
    if not frames: return
    index = max(display.get('frame', 0) - 1, 0) % len(frames) if controller is None else picture_frame(controller, game, display, frames, menu)
    part, pixels = frames[index]
    frame.blit(24 + part.x * 8, 24 + part.y * 8, pixels)


ANIMATED_MENUS = {2: ('CAMP_MENU', 'ALTER', 'ALTER_ORDER', 'ALTER_LEVEL', 'ALTER_SPEED', 'WHO'), 6: ('COMBAT_LOOT', 'WHO')}


def picture_frame(controller, game, display, frames, menu):
    count, calls = len(frames), display.get('frame', 0)
    key = (display.get('id'), display.get('dataset'), getattr(game.s, 'g', {}).get('dkk.runtime', {}).get('loads'))
    shown = getattr(controller, 'picture_shown', None)
    if shown is None or shown['key'] != key or calls < shown['calls']:
        shown = controller.picture_shown = dict(key=key, calls=0, current=0, drawn=0, menu=None, tick=0, on=False)
    while shown['calls'] < calls:
        shown['drawn'], shown['current'], shown['calls'] = shown['current'], (shown['current'] + 1) % count, shown['calls'] + 1
    d = controller.session.decision
    if not (menu and d and (d['info'].get('animate') if game.s.mode in (3, 4) else d['kind'] in ANIMATED_MENUS.get(game.s.mode, ())) and not controller.file_menu
            and controller.text_page * 6 + 6 >= len(controller.lines)):
        return shown['drawn']
    now, waiting = int(controller.clock() * 100 + 1e-6), d.get('i', id(d))
    if shown['menu'] != waiting:
        shown.update(menu=waiting, tick=now, on=count > 1, drawn=shown['current'])
    for _ in range(count):
        duration = frames[shown['current']][0].delay * 10
        if not shown['on'] or now - shown['tick'] < duration: break
        shown['tick'] += duration
        shown['current'] = shown['drawn'] = (shown['current'] + 1) % count
        if frames[shown['current']][0].delay == 99: shown['on'] = False
    return shown['drawn']


def draw_view(frame, game, assets, area=False):
    s, geo = game.s, game.geo
    if geo.map is None or not game.vm.is3d(): return
    try:
        if (area or s.g.get('world.automap')) and not s.r0[0xFB]:
            x0, y0 = max(0, min(5, s.x - 5)), max(0, min(5, s.y - 5))
            for y in range(11):
                for x in range(11):
                    mask = sum(1 << i for i in range(4) if geo.wall(s, x + x0, y + y0, i * 2))
                    frame.blit(24 + x * 8, 24 + y * 8, assets.symbols[25 + mask])
            frame.blit(24 + (s.x - x0) * 8, 24 + (s.y - y0) * 8, assets.symbols[41 + s.dir // 2])
            return
        event = geo.attr(s, s.x, s.y)
        frame.rect(24, 24, 88, 44, assets.view_tables['sky'][s.r0[0xFD if event > 127 else 0xFE]]); frame.rect(24, 68, 88, 2, 0); frame.rect(24, 70, 88, 42, 8)
        loaded = [ident for ident in s.walls if 0 < ident < 0x8000]
        backdrop = assets.backdrop(loaded[-1] if loaded else 0, s.dataset) if event > 127 else assets.backdrop(0, s.dataset)[:1 + (s.r0[0xC9] >= 14)]
        if event > 127 and not loaded: backdrop = ()
        for picture in backdrop: frame.blit(24, 24, picture, clip=CLIP)
        for col, row, symbol, *_ in placements(game, assets):
            tile = assets.wall_tile(s, symbol)
            if tile: frame.blit(24 + col * 8, 24 + row * 8, tile, transparent=13, clip=CLIP)
    except (KeyError, IndexError, OSError): frame.rect(24, 24, 88, 88, 0)


def draw_party(frame, game, assets, col=17, selected=None):
    from ..creation import F
    from ..inventory import IN_COMBAT, LOOT
    frame.text(col, 2, 'Name', assets); frame.text(33, 2, 'AC  HP', assets)
    live = game.s.mode == LOOT
    if selected is None and not live: selected = getattr(game.vm, 'roster_shown', None)
    shown = None if live else getattr(game.vm, 'ready_shown', None)
    linked = list(game.s.party) + list(getattr(game.s, 'monsters', ()))
    painted = None if live else getattr(game.vm, 'linked_shown', None)
    rows = {} if live else getattr(game.vm, 'rows_shown', None) or {}
    if not linked and 'demo_shown' in game.__dict__: linked, rows = game.demo_shown
    for i, c in enumerate(linked[:min(21, len(linked) if painted is None else painted)]):
        b = c.b
        ready = shown[i] if shown is not None and i < len(shown) and not (READY_LIVE.get('shown') is shown and i in READY_LIVE['members']) else b[F['level_up_ready']]
        name = bytes(b[1:1 + min(15, b[0])]).decode('cp437')
        if NAMES_SHOWN.get('game') is game and i < len(NAMES_SHOWN['names']): name = NAMES_SHOWN['names'][i]
        colour = 15 if i == (game.s.sel if selected is None else selected) else 12 if not b[F['active']] else 14 if b[F['side']] and game.s.mode == IN_COMBAT else 13 if ready else 11
        frame.text(col, i + 4, name, assets, colour, 15)
        kept = rows.get(i, (b[F['hp']], b[F['ac']]))
        points = HP_HELD['hp'] if HP_HELD.get('game') is game and HP_HELD['member'] == i else kept[0]
        ac, hp = str(60 - kept[1]), str(points)
        frame.text(35 - len(ac), i + 4, ac, assets, 10)
        frame.text(39 - len(hp), i + 4, hp, assets, 14 if points < b[F['hp_max']] else 10)


def text_delay(controller):
    return controller.session.game.s.g.get('dkk.delay', 4)


def pause(controller, scaled=True):
    return text_delay(controller)*0.1*(controller.effect_scale if scaled else 1)


def revealed(controller):
    slow = getattr(controller, 'slow', None)
    if not slow: return None
    count, kept, at = slow
    step = text_delay(controller)*0.003*controller.effect_scale
    if step <= 0: return None
    shown = kept+int((controller.clock()-at)/step)
    return None if shown >= sum(len(line) for line in controller.lines[:min(count, controller.text_page*6+6)]) else shown


def script_text(game):
    import re
    from ..shop import member_name
    vm = game.vm
    names = {member_name(char) for char in game.s.chars()}
    display = getattr(vm, 'display', None)
    prefix = display.get('damage_prefix') if isinstance(display, dict) else None
    kept = int(prefix[1]) if prefix and prefix[0] == getattr(vm, 'text_epoch', None) else 0
    lines, colours, listed = [], [], False
    for paragraph in (after_fight_prefix(game) + ''.join(vm.out[vm.text_start:])).rstrip().splitlines():
        hit = re.match(r'(.+?) (?:is hit FOR |dies\.)', paragraph.lstrip())
        damage = bool(hit and hit[1] in names)
        listed = listed or damage
        wrapped = town.wrapped_text(paragraph) or ['']
        colours.extend([15 if damage else int(prefix[2]) if not listed and len(lines) + n < kept else getattr(vm, 'text_color', 10) for n in range(len(wrapped))])
        lines.extend(wrapped)
    return lines, colours


def damage_page(decision):
    return bool(decision and decision['kind'] == 'MENU' and decision['info'].get('purpose') == 'script damage')


def page_prompt(controller, page=None):
    page = controller.text_page if page is None else page
    following = controller.lines[(page+1)*6:][:1]
    damage = following and following[0].startswith('  ') and (' is hit FOR ' in following[0] or following[0].rstrip().endswith(' dies.'))
    return ('press <enter>/<return> to continue', 15) if damage else ('press any key to continue', 13)


_family_render = render


def items_screen(decision, game):
    if not decision or decision['kind'] != 'VIEW_ITEMS' or 'window' in decision['info']: return
    from ..shop import member_name
    text, who = game.assets.text, member_name(game.s.selc())
    if decision['info'].get('prompt') == 'Items': decision['info'].update(window='1 5 38 22', title=who + "'s " + text('itemsLabel'), caption=text('readyItemLabel'))


def items_list(decision):
    return bool(decision and decision['kind'] == 'VIEW_ITEMS' and decision['info'].get('prompt') == 'Items')


def item_words(decision):
    return bool(decision and decision['kind'] == 'VIEW_ACTION' and decision['info'].get('prompt') == 'Item' and ITEMS_SHOWN)


ITEMS_SHOWN = {}
_family_pending = pending_question


def items_offer(decision):
    return bool(decision and decision['kind'] in ('SHOP_CONFIRM', 'ACK') and str(decision['info'].get('window', '')).startswith('1 21') and ITEMS_SHOWN)


def pending_question(decision):
    if heal_confirm(decision): return HEAL_SHOWN['decision']
    return ITEMS_SHOWN['decision'] if item_words(decision) or items_offer(decision) else _family_pending(decision)


HEAL_SHOWN = {}


def heal_confirm(decision):
    return bool(decision and decision['kind'] == 'TEMPLE_CONFIRM' and HEAL_SHOWN and not leave_question(decision))


def draw_creature_message(frame, controller, info):
    member = str(HEAL_SHOWN['decision']['info'].get('member', ''))
    frame.rect(8, 136, 304, 48, 0)
    frame.text(1, 18, member, controller.assets, name_colour(controller.session.game.s.selc()), 38)
    for row, line in enumerate(town.wrapped_text(str(info.get('offer', ''))[len(member):].strip())[:4], 19): frame.text(1, row, line, controller.assets, 10, 38)


def draw_offer(frame, controller, info):
    frame.rect(8, 168, 304, 16, 0)
    for row, line in enumerate(town.wrapped_text(str(info.get('offer') or info.get('prompt', '')))[:2], 21): frame.text(1, row, line, controller.assets, int(info.get('colour', 14)), 38)


def bottom_message(decision):
    return bool(decision and decision['kind'] == 'ACK' and decision['info'].get('message_colour') is not None)


_family_own_window = own_window


def own_window(decision):
    return _family_own_window(decision) or bottom_message(decision) or bool(decision and (decision['kind'] == 'CREATE_VIEW' or coin_list(decision) or decision['kind'] == 'NUMBER' and COIN_SHOWN))


def draw_modify(frame, assets, info, green=False):
    name, field = str(info.get('name', '')), int(info.get('field', 0))
    if field == 6:
        frame.rect(8, 8, (len(name) + 1) * 8, 8, 0); frame.text(1, 1, name, assets, 13)
        at = int(info.get('cursor', 1))
        mark = name[at - 1] if 0 < at <= len(name) else ' '
        frame.text(at, 1, '%' if mark == ' ' else mark, assets, 15)
    elif green or '6' in str(info.get('dirty', '')).split(): frame.text(1, 1, name, assets, 10)
    frame.rect(0, 192, 320, 8, 0)
    query = str(info.get('query', '')); frame.text(0, 24, query, assets, 13); col = len(query)
    for n, word in enumerate(str(info.get('menu', '')).split()):
        draw_word(frame, assets, col, word, n == int(info.get('choice', 0))); col += len(word) + 1


def buying(decision):
    return bool(decision and decision['info'].get('purpose') == 'buy')


def taking(decision):
    return bool(decision and decision['info'].get('purpose') == 'take')


TAKE_SHOWN = {}


def panel_print(battle, data, i, aimed):
    c = battle.chars[i]
    if not aimed and i == data.get('panel') and 'panel_print' in data: return data['panel_print']
    weapon = battle.weapon(i)
    return dict(hp=town.field(c, 'hp'), hp_max=town.field(c, 'hp_max'), ac=town.field(c, 'ac'), active=town.field(c, 'active'), side=town.field(c, 'side'), level_up_ready=town.field(c, 'level_up_ready'), status=town.field(c, 'status'),
                helpless=battle.disabled(i), casting=battle.record(i)['casting'], weapon=bytes(weapon) if weapon is not None else None)


def panel_rows(printed, texts):
    from ..combat import I
    weapon, lines = printed['weapon'], []
    for token in filter(None, menu.TOKEN.findall(weapon[I['name'] + 1:I['name'] + 1 + weapon[I['name']]].decode('cp437')) if weapon is not None else ()):
        if not lines or len(lines[-1]) + len(token) > 16: lines.append('')
        lines[-1] += token
    row = 6 + len(lines) + (len(lines[-1]) == 16) if lines else 5
    word = STATUS_NAMES[printed['status']] if not printed['active'] else texts('helplessText') if printed['helpless'] else texts('castingText') if printed['casting'] else ''
    return lines[:3], row + 2, word


def draw_panel(frame, assets, game, battle, data, i, aimed):
    from ..combat import name
    c, printed = battle.chars[i], panel_print(battle, data, i, aimed)
    frame.text(23, 1, name(c), assets, 12 if not printed['active'] else 14 if printed['side'] else 13 if printed['level_up_ready'] else 11, 16)
    frame.text(23, 3, game.assets.text('hitPointsHeader'), assets, 10)
    frame.text(33, 3, str(printed['hp']), assets, 14 if printed['hp'] < printed['hp_max'] else 10)
    frame.text(23, 5, game.assets.text('armorClassHeader'), assets, 10); frame.text(26, 5, str(60 - printed['ac']), assets, 10)
    lines, row, word = panel_rows(printed, game.assets.text)
    for y, text in enumerate(lines, 7): frame.text(23, y, text, assets, 10, 16)
    frame.text(23, row, word, assets, 15, 16)


def step_data(data, step):
    if not isinstance(step, dict) or 'panel' not in step: return data
    shown = {k: v for k, v in data.items() if k != 'panel_print'}
    shown.update((k, step[k]) for k in ('panel', 'panel_print') if k in step)
    return shown


def panel_of(data):
    return data['actor'] if data.get('panel', 0) < 0 else data.get('panel', data['actor'])


def aim_marked(battle, data, cursor):
    x, y = cursor
    if not battle.walk(*battle.position(data['actor']), x, y)[0]: return -1
    marked = battle.occupancy().get((x, y), -1)
    if marked < 0 and battle.tile(x, y) == 31:
        bodies, owners = battle.data.get('downed', []), battle.data.get('downed_who', [])
        marked = next((owners[k] for k in reversed(range(min(battle.data.get('downed_count', len(bodies)), len(bodies), len(owners)))) if tuple(bodies[k][:2]) == (x, y)), -1)
    return marked


def draw_fight_message(frame, assets, battle, step):
    import textwrap
    from ..combat import name
    found = max(((i, name(c)) for i, c in enumerate(battle.chars) if step.startswith(name(c) + ' ')), key=lambda m: len(m[1]), default=None)
    if found is None:
        frame.rect(184, 80, 128, 96, 0)
        for y, text in enumerate(textwrap.wrap(step, 16)[:11], 11): frame.text(23, y, text, assets, 10, 16)
        return
    i, who = found; c = battle.chars[i]
    text = step[len(who) + 1:]
    row = 12 if text == assets.text('lostSpellMessage') else 10
    frame.rect(184, 8 * row, 128, 8 * (22 - row), 0)
    colour = 12 if not town.field(c, 'active') else 14 if town.field(c, 'side') else 13 if town.field(c, 'level_up_ready') else 11
    frame.text(23, row, who, assets, colour, 16)
    for y, line in enumerate(textwrap.wrap(text, 16)[:21 - row], row + 1): frame.text(23, y, line, assets, 10, 16)


def message_window(source, left, top, right, bottom, col, row, clear=True):
    if clear or not (left <= col <= right and top <= row <= bottom): col, row = left, top
    cells, n, idx, s = {}, len(source), 1, ' ' + source
    def put(i, end):
        nonlocal col
        while i <= end: cells[col, row] = s[i]; i += 1; col += 1
        return i
    while n and idx <= n:
        end = idx
        while end < n and s[end] in BREAK_CHARS: end += 1
        while end < n and s[end] not in BREAK_CHARS and s[end] != ' ': end += 1
        if s[end] != ' ':
            while end + 1 < n and s[end + 1] in BREAK_CHARS: end += 1
        if end - idx + col > right:
            if end - idx + col == right and s[end] == ' ': idx = put(idx, end - 1)
            col, row = left, row + 1
            while idx < n and s[idx] == ' ': idx += 1
            if row > bottom and idx < n: col, row, cells = left, top, {}; idx = put(idx, end)
        else: idx = put(idx, end)
    if col > right: col, row = left, row + 1
    lines = {}
    for (c, r), ch in cells.items(): lines.setdefault(r, [' '] * (right - left + 1))[c - left] = ch
    return {r: ''.join(v).rstrip() for r, v in sorted(lines.items())}, col, row


BREAK_CHARS = frozenset('!,-.:;?')


def attack_result(step):
    return step['result'].replace(' of damage', '  of damage') if 'Hitting for ' in step['result'] else step['result']


def attack_result_lines(step):
    return list(message_window(attack_result(step), 23, 13, 38, 16, 23, 13)[0].values())


def fight_cursor(game):
    from ..combat import name
    names = sorted({name(c) for c in game.s.chars()}, key=len, reverse=True)
    report, lost = list(getattr(game, 'combat_report', ())), game.assets.text('lostSpellMessage')
    for k in range(len(report) - 1, -1, -1):
        step = report[k]
        if isinstance(step, dict) and step['kind'] == 'attack':
            _, col, row = message_window(step['lead'], 23, 11, 38, 21, 23, 11)
            if step['result']: _, col, row = message_window(attack_result(step), 23, 13, 38, 16, col, row)
            if 'down' not in step: return message_window(lost, 23, 13, 38, 21, 23, 13)[1:] if k and report[k - 1] == step['target'] + ' ' + lost else (col, row)
            top = row + 1
            _, col, row = message_window(game.assets.text('goesDown'), 23, top + 1, 38, 21, col, row)
            if step['down'] == 'killed': _, col, row = message_window(game.assets.text('killedMessage'), 23, top + 3, 38, 21, col, row)
            return col, row
        if isinstance(step, dict) or step in BOTTOM_LINE: continue
        who = next((n for n in names if step.startswith(n + ' ')), None)
        if who is None: return None
        text = step[len(who) + 1:]
        top = 13 if text == game.assets.text('lostSpellMessage') else 11
        return message_window(text, 23, top, 38, 21, 23, top)[1:]
    return None


def after_fight_prefix(game):
    vm = game.vm
    fight = game.__dict__.get('fight_epoch')
    if fight is None or fight != vm.text_epoch or game.s.g.get('dkk.battle', {}).get('active'): return ''
    cursor = game.__dict__.get('left_cursor') or fight_cursor(game)
    if not cursor or not (1 <= cursor[0] <= 38 and 17 <= cursor[1] <= 22): return ''
    return '\n' * (cursor[1] - 17) + ' ' * (cursor[0] - 1)


def notice_end(decision, rect):
    info = decision['info']
    text = info['creature_text'] if 'creature_name' in info else info.get('offer') or info.get('prompt', '')
    return message_window(str(text), *rect, rect[0], rect[1])[1:]


def left_cursor(decision):
    first, second, _ = leave_question(decision)
    col, row = message_window(first, 1, 17, 38, 22, 1, 17)[1:]
    return message_window(second, 1, 17, 38, 22, col, row, False)[1:]


SCRIBE_SHOWN = {}
CAST_SHOWN = {}


def shown_under(controller):
    d, game = controller.session.decision, controller.session.game
    if not d: return None
    text, info = game.assets.text, d['info']
    if d['kind'] == 'ACK': return (ITEMS_SHOWN['decision'], None, True) if info.get('item') and ITEMS_SHOWN and not game.s.g.get('dkk.battle', {}).get('active') else None
    if d['kind'] != 'CAMP_CONFIRM': return None
    if SCRIBE_SHOWN and info.get('prompt') == text('scribeConfirmPrompt'): return SCRIBE_SHOWN['decision'], (), False
    if (CAST_SHOWN or ITEMS_SHOWN) and 'spell' in info and info.get('prompt') == text('useItemPrompt'): return (CAST_SHOWN or ITEMS_SHOWN)['decision'], (text('itemLabel'), text('combatOnlyItemText')), not CAST_SHOWN
    if CAST_SHOWN and 'spell' in info and info.get('prompt') == text('loseQuery'): return CAST_SHOWN['decision'], (str(info['spell']), text('cantCastHereText')), False
    return None


def draw_item_notice(frame, controller, info):
    c = controller.session.game.s.selc(); who = bytes(c.b[1:1 + c.b[0]]).decode('cp437')
    draw_character_message(frame, controller.assets, dict(creature_name=who, creature_colour=name_colour(c), creature_column=1, creature_row=18, creature_text=str(info.get('prompt', ''))[len(who) + 1:]))
    frame.text(1, 22, str(info['item']).strip(), controller.assets, 10, 38)


def spell_message(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'ACK' and str(d['info'].get('spell', '')).isdigit()
                and not controller.session.game.s.g.get('dkk.battle', {}).get('active'))


def speaker(party, head, member=None):
    named = lambda m: bytes(m.b[1:1 + m.b[0]]).decode('cp437')
    if isinstance(member, int) and 0 <= member < len(party) and head.startswith(named(party[member]) + ' '): return party[member]
    return max((m for m in party if head.startswith(named(m) + ' ')), key=lambda m: len(named(m)), default=None)


def draw_spell_message(frame, controller, d):
    from .. import magic
    game, assets = controller.session.game, controller.assets
    spell = magic.spell(game, int(d['info']['spell'])).name
    text = str(d['info'].get('prompt', ''))
    head = text[:len(text) - len(spell)].rstrip() if text.endswith(spell) else text
    c = speaker(game.s.party, head, d['info'].get('member'))
    if c is None: return
    who = bytes(c.b[1:1 + c.b[0]]).decode('cp437')
    frame.rect(8, 144, 304, 40, 0)
    frame.text(1, 19, who, assets, name_colour(c), 38)
    frame.text(len(who) + 2, 19, head[len(who) + 1:], assets, 10, max(0, 37 - len(who)))
    frame.text(1, 20, spell, assets, 10, 38)


def rest_hold(d):
    return bool(d and d['kind'] == 'ACK' and d['info'].get('rest') and d['info'].get('timed'))


def draw_rest_hold(frame, assets, info):
    frame.rect(0, 192, 320, 8, 0)
    if 'row' in info:
        frame.rect(8, 136, 304, 48, 0)
        frame.text(int(info.get('column', 1)), int(info['row']), str(info.get('prompt', '')), assets, int(info.get('colour', 10)), 38)
    if 'days' in info: draw_rest_time(frame, assets, info)


def bottom_note(controller):
    d = controller.session.decision
    return bool(d and d['info'].get('message') and (buying(d) or d['kind'] == 'SHOP_MENU') and showing_message(controller))


def move_note(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'COMBAT_MOVE' and d['info'].get('prompt') and showing_message(controller))


@lru_cache(maxsize=64)
def flight(view, start, aim):
    sign = lambda v: (v > 0) - (v < 0)
    centred = lambda x, y: (max(0, min(43, x - 3)), max(0, min(18, y - 3)))
    sx, sy, ex, ey = max(0, min(49, start[0])), max(0, min(24, start[1])), max(0, min(49, aim[0])), max(0, min(24, aim[1]))
    wide, tall, path, err = abs(ex - sx) * 3, abs(ey - sy) * 3, [], 0
    for _ in range(max(wide, tall)):
        err += 2 * min(wide, tall); turn = err >= max(wide, tall)
        if turn: err -= 2 * max(wide, tall)
        path.append((sign(ex - sx) * (wide >= tall or turn), sign(ey - sy) * (wide < tall or turn)))
    path.append((0, 0))
    if len(path) < 4: return ()
    count, (ox, oy) = len(path) - 2, view
    inside = lambda x, y: 0 <= x - ox <= 6 and 0 <= y - oy <= 6
    last = True
    if not inside(sx, sy) or not inside(ex, ey):
        if abs(ex - sx) <= 6 and abs(ey - sy) <= 6: ox, oy = centred(sx + int((ex - sx) / 2), sy + int((ey - sy) / 2))
        else: last = False
    shots, at, ax, ay = [], 0, 0, 0
    for _ in range(64):
        px, py = (sx - ox) * 3 + ax, (sy - oy) * 3 + ay
        while True:
            dx, dy = path[at]; px += dx; py += dy; at += 1
            shots.append((ox, oy, px, py))
            out = not (0 <= px <= 18 and 0 <= py <= 18)
            if not out and at < count:
                ax += dx; ay += dy
                if abs(ax) == 3: sx += sign(ax); ax = 0
                if abs(ay) == 3: sy += sign(ay); ay = 0
            if at >= count or out: break
        if at >= count:
            if abs(ex - ox - 3) > 3: ox = centred(ex, ey)[0]
            if abs(ey - oy - 3) > 3: oy = centred(ex, ey)[1]
            return tuple(shots + [(ox, oy, (ex - ox) * 3, (ey - oy) * 3)])
        ax = ay = 0; sx, sy = ex, ey
        ox, oy = centred(ex + (ex - 49 if ex + 3 > 49 else 3 - ex if ex < 3 else 0), ey + (ey - 24 if ey + 3 > 24 else 3 - ey if ey < 3 else 0))
        px, py, at = (ex - ox) * 3, (ey - oy) * 3, count
        while at >= 0:
            dx, dy = -path[at][0], -path[at][1]; px += dx; py += dy
            if px > 18: sx = ox + 6
            elif px < 0: sx = ox
            if py > 18: sy = oy + 6
            elif py < 0: sy = oy
            if not (0 <= px <= 18 and 0 <= py <= 18): break
            ax += dx; ay += dy
            if abs(ax) == 3: sx += sign(ax); ax = 0
            if abs(ay) == 3: sy += sign(ay); ay = 0
            at -= 1
        at = max(at, 0)
    return tuple(shots)


def missile_frames(assets, step):
    def picture(half, mirror):
        pixels = assets.combat_picture('COMSPR', step['picture'] - 13 + 128 * half)[0]
        return tuple(row[::-1] for row in pixels) if mirror else pixels
    if step['frames'] == 4: return [picture(0, False), picture(0, True), picture(1, True), picture(1, False)]
    if step['frames'] == 2: return [picture(0, False), picture(1, False)]
    return [picture(step.get('facing', 0), step.get('mirror', False))]


def flown(step):
    return step if isinstance(step, dict) and step['kind'] in ('missile', 'flight', 'bolt') and 'start' in step else None


def missile_shot(controller, step, progress, view):
    step = flown(step)
    if not step: return None
    shots = flight(tuple(step.get('view', view)), tuple(step['start']), tuple(step['aim']))
    if not shots: return None
    k = min(len(shots) - 1, int(progress[1] * 1000 / step['pace']))
    return shots[k] + (missile_frames(controller.assets, step)[k % step['frames']],)


SCATTER_RING = 0.05


def scatter_shot(controller, step, progress):
    if not (isinstance(step, dict) and step['kind'] == 'scatter'): return None
    assets, (tx, ty) = controller.assets, step['aim']
    picture = lambda half: assets.combat_picture('COMSPR', step['cell'] - 13 + 128 * half)[0]
    pictures = [picture(0), tuple(row[::-1] for row in picture(0)), picture(1), tuple(row[::-1] for row in picture(1))]
    shown = min(len(step['rings']), int(progress[1] / SCATTER_RING) + 1)
    return max(0, min(43, tx - 3)), max(0, min(18, ty - 3)), [(x, y, pictures[v]) for ring in step['rings'][:shown] for x, y, v in ring]


RESULT_FEEL = 1.0
MISSILE_SOUNDS = {5: 12, 7: 12, 12: 12, 30: 12, 66: 12, 2: 9, 3: 9, 6: 9, 54: 6, 55: 6, 28: 6, 29: 6, 67: 6}
_family_report_hold, _family_step_sounds = report_hold, step_sounds


def falling(step):
    if not isinstance(step, dict): return None
    return step.get('fall') if step['kind'] == 'attack' else step if step['kind'] == 'fall' else None


def posed_icon(assets, game, step, i):
    posed = isinstance(step, dict) and (step['kind'] == 'attack' or step.get('posed')) and step.get('actor') == i
    pixels, palette = assets.combat_icon(game, i, 1 if posed else 0)
    if posed and 'facing' in step and step['facing'] // 4 != game.s.g['dkk.battle']['actors'][i]['facing'] // 4: pixels = tuple(row[::-1] for row in pixels)
    return pixels, palette


def fall_view(step):
    fall = falling(step)
    return tuple(fall['view'][:2]) + ((),) if fall else None


def fall_time(fall):
    return len(fall['frames']) * fall['pace'] / 1000


def draw_fall(frame, controller, battle, step, progress):
    fall = falling(step)
    if not fall: return
    assets = controller.assets; sheet = combat_sheet(controller.session.game, assets)
    colours, (ox, oy) = assets.view_tables['icon_palette'], fall['view'][:2]
    k = min(len(fall['frames']) - 1, int(progress[1] * 1000 / fall['pace']))
    picture = assets.combat_picture('COMSPR', fall['picture'] - 13 + 128 * fall['frames'][k])[0]
    for x, y, ground, overlay in fall['cells']:
        if not (0 <= x - ox < 7 and 0 <= y - oy < 7): continue
        px, py = 8 + (x - ox) * 24, 8 + (y - oy) * 24
        if ground < len(sheet): frame.blit(px, py, sheet[ground])
        if overlay is not None: frame.blit(px, py, assets.combat_picture('COMSPR', overlay)[0], transparent=0, colours=colours, clip=(8, 8, 176, 176))
        frame.blit(px, py, picture, transparent=0, colours=colours, clip=(8, 8, 176, 176))
    if fall.get('creature_message'): draw_character_message(frame, assets, fall['creature_message'])
    elif step['kind'] == 'fall' and step.get('text'): draw_fight_message(frame, assets, battle, step['text'])


def place_falls(report, falls):
    for at, text in reversed(falls):
        if not (0 < at <= len(report) and isinstance(report[at - 1], dict) and report[at - 1]['kind'] == 'fall'): continue
        pair = report[at:at + 2]
        if len(pair) == 2 and all(isinstance(e, dict) and e['kind'] == 'attack' for e in pair) and 'down' in pair[1]:
            report[at + 1] = dict(pair[1], fall=report[at - 1]); del report[at - 1]
        else: report[at - 1] = dict(report[at - 1], text=text)


def report_hold(entry, *rest):
    fall = falling(entry)
    if fall: return fall_time(fall) + _family_report_hold(entry, *rest)
    if (shot := flown(entry)) is not None:
        return len(flight(tuple(shot['view']), tuple(shot['start']), tuple(shot['aim']))) * shot['pace'] / 1000 if 'view' in shot else 0
    if isinstance(entry, dict) and entry['kind'] == 'move' and entry.get('still'): return 0
    if isinstance(entry, dict) and entry['kind'] == 'scatter': return len(entry['rings']) * SCATTER_RING
    if isinstance(entry, dict) and entry['kind'] == 'clear': return 0
    if isinstance(entry, dict) and entry['kind'] == 'flash': return entry['frames'] * FLASH_STEP + (_family_report_hold(entry, *rest) if entry['hit'] else 0)
    return _family_report_hold(entry, *rest)


def step_sounds(entry):
    if isinstance(entry, dict) and entry['kind'] == 'missile': return [12, MISSILE_SOUNDS.get(entry['item'], 9)]
    if isinstance(entry, dict) and (entry['kind'] == 'move' and entry.get('still') or entry['kind'] == 'flight'): return []
    if isinstance(entry, dict) and entry['kind'] == 'scatter': return [11]
    if isinstance(entry, dict) and entry['kind'] == 'fall': return [5]
    if isinstance(entry, dict) and entry['kind'] == 'flash': return _family_step_sounds(entry['text']) if entry.get('said') else []
    if isinstance(entry, dict) and entry['kind'] == 'clear': return []
    return _family_step_sounds(entry)


def left_line(report, at):
    for entry in reversed(report[:at + 1]):
        if isinstance(entry, dict) and (entry['kind'] == 'begin' or entry['kind'] == 'clear' and entry['bottom']): return None
        if isinstance(entry, dict) and entry['kind'] == 'move' and entry.get('left') is not None: return entry['left']
    return None


_family_report_step = report_step


def clear_combat_text(battle, bottom=False):
    battle.show('clear', bottom=bool(bottom))


def report_step(controller):
    for entry in controller.report:
        if isinstance(entry, dict) and entry['kind'] == 'missile' and 'view' not in entry: entry['view'] = tuple(combat_view(controller))
    step = _family_report_step(controller)
    if step is None and (bottom_note(controller) and not controller.session.game.s.g.get('dkk.battle', {}).get('active') or move_note(controller)):
        return len(controller.report), controller.clock() - controller.decided_at
    return step


_family_vertical = vertical


def vertical(controller, decision=None):
    v = _family_vertical(controller, decision)
    if coin_list(decision or controller.session.decision) and v['words']: v['words'][0] = (v['words'][0][0].strip(), v['words'][0][1])
    if buying(decision or controller.session.decision) or taking(decision or controller.session.decision): v['query'] = str(v['info'].get('prompt', ''))
    return v


def draw_shop_money(frame, controller, info):
    from ..shop import coins, STEEL
    game = controller.session.game; col, text = int(info.get('money_column', 1)), game.assets.text
    steel, pool = coins(game.s.selc())[STEEL], game.s.treasure_money[STEEL]
    if bottom_note(controller) and getattr(controller, 'money_seen', None): steel, pool = controller.money_seen
    frame.text(col, 20, text('goldLabel') + str(steel).rjust(10), controller.assets, 15)
    frame.text(col, 21, text('poolLabel') + str(pool).rjust(10), controller.assets, 15)


def name_colour(c):
    from ..creation import F
    return 12 if not c.b[F['active']] else 13 if c.b[F['level_up_ready']] else 11


def draw_items_title(frame, controller):
    from ..shop import member_name
    game = controller.session.game; c = game.s.selc(); who = member_name(c)
    frame.rect(8, 8, 304, 8, 0)
    frame.text(1, 1, who + "'s", controller.assets, name_colour(c), 38)
    frame.text(len(who) + 4, 1, game.assets.text('itemsLabel'), controller.assets, 10, max(0, 35 - len(who)))


def party_destroyed(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'ACK' and d['info'].get('message') == controller.session.game.assets.text('partyDestroyed'))


def draw_destroyed(controller):
    game, assets, d = controller.session.game, controller.assets, controller.session.decision
    frame = Frame(); draw_frame(frame, game, assets, True, True)
    for row, line in enumerate(town.wrapped_text(str(d['info']['message']), 36), 5): frame.text(2, row, line, assets, 10, 36)
    frame.text(0, 24, str(d['info'].get('prompt', '')), assets, 13, 40)
    return frame


def battle_summary(decision):
    return bool(decision and decision['kind'] == 'ACK' and 'experience' in decision['info'])


def draw_summary(controller):
    from ..combat import treasure_flags
    game, assets, info = controller.session.game, controller.assets, controller.session.decision['info']
    text, message = game.assets.text, str(info.get('message', ''))
    frame = Frame(); draw_frame(frame, game, assets, True, True)
    lines = [] if game.s.r0[0x1F5] else [(5, text('eachReceives') + str(info['experience'])), (7, text('experiencePoints'))]
    outcome = message[:len(message) - sum(len(line) + 1 for _, line in lines)] if lines else message
    lines = [(3, outcome)] + lines + [(10, text('msgPartyTreasure' if any(treasure_flags(game.s)) else 'msgNoTreasure'))]
    for row, line in lines: frame.text(1, row, line, assets, 10, 38)
    draw_word(frame, assets, 0, str(info.get('prompt', '')), True)
    return frame


def draw_hp_row(frame, assets, info):
    row, col, hp = int(info['hp_row']), int(info.get('hp_column', 18)), str(info.get('hp', ''))
    frame.rect(8, row * 8, 304, 8, 0)
    frame.text(1, row, str(info.get('member', '')), assets, 15)
    frame.text(col, row, hp, assets, int(info.get('hp_colour', 15)))
    frame.text(col + len(hp), row, '/' + str(info.get('hp_max', '')), assets, 15)


def full_render(controller, assets=None, elapsed=0):
    title.update(controller)
    if getattr(controller, 'fight_keys', None) and not controller.session.game.s.g.get('dkk.battle', {}).get('active'): poll_fight_keys(controller)
    if title.active(controller): return title.draw(controller, controller.assets)
    kept = None if controller.file_menu or getattr(controller, 'scribe_drawing', False) else shown_under(controller)
    if kept:
        session = controller.session; asked, selected = session.decision, controller.selected; controller.scribe_drawing = True
        try:
            session.decision, controller.selected = kept[0], None; under = render(controller, assets, elapsed)
            session.decision, controller.selected = asked, selected; frame = render(controller, assets, elapsed)
        finally: session.decision, controller.selected = asked, selected; controller.scribe_drawing = False
        frame.rows[:192] = under.rows[:192]
        if kept[2]: frame.rect(8, 136, 304, 48, 0)
        if kept[1] is None: draw_item_notice(frame, controller, asked['info'])
        for row, line in enumerate(kept[1] or (), 19): frame.text(1, row, line, controller.assets, 10, len(line))
        return frame
    if coin_amount(controller) and not controller.file_menu and not getattr(controller, 'coin_drawing', False):
        session = controller.session; asked, selected = session.decision, controller.selected; controller.coin_drawing = True
        try:
            session.decision, controller.selected = COIN_SHOWN['decision'], None; under = render(controller, assets, elapsed)
            session.decision, controller.selected = asked, selected; frame = render(controller, assets, elapsed)
        finally: session.decision, controller.selected = asked, selected; controller.coin_drawing = False
        frame.rows[:192] = under.rows[:192]
        return frame
    if calibration_pause(controller.session.decision) and not controller.file_menu:
        return draw_calibration(controller, assets, elapsed, str(controller.session.decision['info'].get('prompt', '')).split(chr(10) * 2))
    if battle_summary(controller.session.decision) and not controller.file_menu: return draw_summary(controller)
    if party_destroyed(controller) and not controller.file_menu: return draw_destroyed(controller)
    items_screen(controller.session.decision, controller.session.game)
    frame = _family_render(controller, assets, elapsed)
    d = controller.session.decision
    if d and d['info'].get('vault_menu') and not controller.file_menu: frame.text(1, 15, 'bank of gargath', controller.assets, 10, 15)
    if appraise_value(d) and not controller.file_menu: draw_appraisal(frame, controller.session.game, controller.assets, d)
    if d and d['kind'] == 'CREATE_INIT' and d['info'].get('caption') and not controller.file_menu: frame.text(1, 3, str(d['info']['caption']), controller.assets, 13, 38)
    if bottom_message(d) and not controller.file_menu:
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, str(d['info'].get('prompt', '')), controller.assets, int(d['info']['message_colour']), 40)
    if buying(d) and not controller.file_menu: draw_shop_money(frame, controller, d['info'])
    if d and d['options'] is None and getattr(controller, 'take_number', False) and TAKE_SHOWN and not controller.file_menu:
        frame.rect(8, 8, 304, 176, 0); window_frame(frame, controller.session.game, controller.assets, 23)
        shown = __import__('types').SimpleNamespace(session=controller.session, selected=None, spell_top=TAKE_SHOWN.get('top', 0))
        draw_vertical(frame, shown, controller.assets, TAKE_SHOWN['decision'])
    if spell_message(controller) and not controller.file_menu: draw_spell_message(frame, controller, d)
    if rest_hold(d) and not controller.file_menu: draw_rest_hold(frame, controller.assets, d['info'])
    if aging_page(controller.session.game, d) and not controller.file_menu: draw_aging(frame, controller, d['info'])
    if d and d['kind'] == 'ACK' and 'creature_name' in d['info'] and not controller.file_menu: draw_character_message(frame, controller.assets, d["info"])
    if taking(d) and not controller.file_menu:
        frame.rect(8, 128, 304, 8, 0)
        for x in (0, 312): frame.blit(x, 128, controller.assets.symbols[7])
    if damage_page(d) and not controller.file_menu:
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, str(d['options'][0]), controller.assets, int(d['info'].get('color', 13)), 40)
    if d and d['kind'] == 'SHOP_MENU' and bottom_note(controller) and not controller.file_menu:
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, str(d['info']['message']), controller.assets, 10, 40)
    if d and d['info'].get('hp_row') and not controller.file_menu: draw_hp_row(frame, controller.assets, d['info'])
    if d and d['kind'] == 'CREATE_MODIFY' and not controller.file_menu: draw_modify(frame, controller.assets, d['info'], getattr(controller, 'name_green', False))
    if items_list(d) and not controller.error:
        frame.rect(0, 192, 320, 8, 0); col = 0
        for n, label in enumerate(item_menu(controller)): draw_word(frame, controller.assets, col, label, n == getattr(controller, 'item_word', 0)); col += len(label) + 1
    if (item_words(d) or items_offer(d)) and not controller.error:
        shown = __import__('types').SimpleNamespace(session=controller.session, selected=None if items_offer(d) else ITEMS_SHOWN['index'], spell_top=ITEMS_SHOWN.get('top', 0))
        draw_vertical(frame, shown, controller.assets, ITEMS_SHOWN['decision'])
    if item_words(d) and not controller.error:
        frame.rect(0, 192, 320, 8, 0); col = 0
        for index, label in menu_items(d): draw_word(frame, controller.assets, col, label, index == controller.selected); col += len(label) + 1
    if (items_list(d) or item_words(d) or items_offer(d)) and not controller.error: draw_items_title(frame, controller)
    if items_offer(d) and not controller.error: draw_offer(frame, controller, d['info'])
    if heal_confirm(d) and not controller.error:
        shown = __import__('types').SimpleNamespace(session=controller.session, selected=HEAL_SHOWN['index'], spell_top=HEAL_SHOWN.get('top', 0))
        draw_vertical(frame, shown, controller.assets, HEAL_SHOWN['decision'])
        for x, tile in enumerate(controller.assets.part('dividerRow')): frame.blit(x * 8, 128, controller.assets.symbols[tile])
        draw_creature_message(frame, controller, d['info'])
    if listed(d) and not controller.error:
        from ..creation import F
        from ..shop import member_name
        c = spell_character(controller); who = member_name(c)
        frame.rect(8, 8, 304, 8, 0)
        frame.text(1, 1, who + "'s", controller.assets, name_colour(c), 38)
        frame.text(len(who) + 4, 1, 'Spells ' + d['info']['title'], controller.assets, 10, max(0, 35 - len(who)))
    if d and (d['info'].get('source') or d['info'].get('prompt') == controller.session.game.assets.text('loadWhichGamePrompt')) and not controller.file_menu:
        frame.rect(8, 8, 304, 176, 0); window_frame(frame, controller.session.game, controller.assets, 23)
    if (items_list(d) or item_words(d) or items_offer(d) or listed(d)) and not controller.error:
        y = 128 if listed(d) and int(d['info'].get('selection', 0)) == 2 else 16
        for x, tile in enumerate(controller.assets.part('dividerRow')): frame.blit(x * 8, y, controller.assets.symbols[tile])
        if listed(d):
            for x in (0, 39): frame.blit(x * 8, 24, controller.assets.symbols[7])
    if (elapsed > 0 and controller.text_page and controller.held() is None and not controller.file_menu
            and not controller.session.game.s.g.get('dkk.battle', {}).get('active')
            and controller.text_page*6 < len(controller.lines) and revealed(controller) is not None):
        text, colour = page_prompt(controller, controller.text_page-1)
        frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, text, controller.assets, colour)
    return frame


_plain_choose, _family_key, _family_poll = Controller.choose, Controller.key, Controller.poll


def _family_choose(self, index):
    answered = self.session.decision
    result = _plain_choose(self, index)
    following = self.session.decision
    if timed(following) and answered and not timed(answered):
        shown = [i for i, _ in menu_items(answered)] if compact(answered) else []
        self.timed_carry = shown.index(index) if index in shown else None
    elif timed(answered) and not timed(following):
        carry, self.timed_carry = getattr(self, 'timed_carry', None), None
        if aim_menu(following) and carry is not None and following['info'].get('highlight') not in self.aim_options() and carry < len(self.aim_options()): self.horizontal_choice = carry
    return result


def timed(decision):
    return bool(decision and decision['kind'] == 'ACK' and decision['info'].get('timed'))


def name_flash(self, frame, i, hit=False):
    import copy
    ox, oy = combat_view(self); r = self.session.game.s.g['dkk.battle']['actors'][i]; x, y = r['x'], r['y']
    holds = []
    for _ in range(1 if hit else text_delay(self) + 1):
        for k in range(4):
            pixels = self.assets.combat_picture('COMSPR', (11 if hit else 9) + (128 if k > 1 else 0))[0]
            if k in (1, 2): pixels = tuple(row[::-1] for row in pixels)
            shown = copy.copy(frame); shown.rows = [bytearray(row) for row in frame.rows]
            if 0 <= x - ox < 7 and 0 <= y - oy < 7:
                shown.blit(8 + (x - ox) * 24, 8 + (y - oy) * 24, pixels, transparent=0, colours=self.assets.view_tables['icon_palette'], clip=(8, 8, 176, 176))
            holds.append(dict(kind='script-hold', frame=shown, delay=0.07 * self.effect_scale))
    return holds + [dict(kind='script-hold', frame=frame, delay=pause(self))] * bool(hit)


def bottom_line(frame, assets, text):
    frame.rect(0, 192, 320, 8, 0); frame.text(0, 24, str(text), assets, 10, 40)
    return frame


APPRAISE_SHOWN = {}


def appraise_value(decision):
    return bool(decision and decision['info'].get('purpose') == 'appraise-value' and APPRAISE_SHOWN)


def draw_appraisal(frame, game, assets, decision):
    info = APPRAISE_SHOWN['info'] if appraise_value(decision) else decision['info']
    text, char = game.assets.text, game.s.selc()
    frame.rect(8, 8, 304, 176, 0)
    frame.text(int(info.get('name_column', 1)), int(info.get('name_row', 1)), str(info.get('member', '')), assets, name_colour(char), 38)
    frame.text(1, int(info.get('collection_row', 7)), str(info.get('collection', '')), assets, 15, 38)
    frame.text(1, 9, text('gemsCountLabel') + str(int(info.get('gems', 0))), assets, 15, 38)
    frame.text(1, 10, text('jewelryCountLabel') + str(int(info.get('jewelry', 0))), assets, 15, 38)
    if appraise_value(decision): frame.text(int(decision['info']['value_column']), int(decision['info']['value_row']), str(decision['info']['value_line']), assets, 15, 38)


def answered_screen(self, under):
    session = self.session; asked, selected, cell, view = session.decision, self.selected, self.aim_cell, self.aim_view
    try:
        session.decision, self.selected = under, getattr(self, 'answered_index', selected) if compact(under) else None
        if aim_menu(under) and self.aim_cell is None:
            from ..combat import Battle
            self.aim_cell, self.aim_view = Battle(session.game).position(int(under['info']['selected'])), tuple(session.game.s.g['dkk.battle']['view'])
        return render(self).rows
    finally: session.decision, self.selected, self.aim_cell, self.aim_view = asked, selected, cell, view


def menu_bottom(self, under):
    session = self.session; asked, selected = session.decision, self.selected
    try: session.decision, self.selected = under, getattr(self, 'answered_index', selected); return render(self).rows[192:]
    finally: session.decision, self.selected = asked, selected


def bottom_text(frame, assets, text):
    shown = blank_bottom(frame); shown.text(0, 24, text, assets, 10, 40)
    return shown


def blank_bottom(frame):
    import copy
    shown = copy.copy(frame); shown.rows = [bytearray(row) for row in frame.rows]; shown.rect(0, 192, 320, 8, 0)
    return shown


INIT_SHOWN = {}


def calibration_pause(decision):
    return bool(decision and decision['kind'] == 'ACK' and decision['info'].get('window') == '1 3 38 5' and INIT_SHOWN)


def draw_calibration(controller, assets, elapsed, lines, row=3):
    session = controller.session; asked = session.decision
    try: session.decision = INIT_SHOWN['decision']; frame = render(controller, assets, elapsed)
    finally: session.decision = asked
    frame.rect(8, 8, 304, 176, 0)
    for n, line in enumerate(lines): frame.text(1, row + 2 * n, line, controller.assets, 13, 38)
    return frame


def pass_timed(self, under=None):
    shown, flush, bottom, behind, falls, last = [], False, None, None, [], None
    while timed(self.session.decision) and self.session.error is None:
        info = self.session.decision['info']
        flush = flush or bool(info.get('flush_keys'))
        if self.queue(): shown += typed_script_holds(self, self.queue()); self.queue().clear()
        if info.get('fall'): falls.append((len(getattr(self, 'report', ())), str(info.get('prompt', ''))))
        elif 'anim' in info and self.session.game.s.g.get('dkk.battle', {}).get('active'): self.report = flashed(list(getattr(self, 'report', ())), flash_entry(self, info))
        elif self.presentation_enabled:
            HP_HELD.update(healed(self, info)); self.capturing = True
            try: frame = render(self)
            finally: HP_HELD.clear(); self.capturing = False
            if info.get('clear_bottom'): frame.rect(0, 192, 320, 8, 0)
            elif ('creature_name' in info or info.get('item') and shown_under(self)) and under is not None and not timed(under):
                if bottom is None: bottom = menu_bottom(self, under)
                frame.rows[192:] = [bytearray(row) for row in bottom]
            if bottom_message(self.session.decision) and last is not None:
                frame.rows[:192] = [bytearray(row) for row in last.rows[:192]]
            elif bottom_message(self.session.decision) and under is not None and not timed(under):
                if behind is None: behind = answered_screen(self, under)[:192]
                frame.rows[:192] = [bytearray(row) for row in behind]
            last = frame
            hold = int(info['timed']) * pause(self)
            shown += name_flash(self, frame, info['anim'], info.get('hit')) if 'anim' in info else [typed_hold(self, frame, hold)]
            if info.get('blank_bottom_pause'): shown.append(dict(kind='script-hold', frame=blank_bottom(frame), delay=hold))
            if info.get('after_pause'): shown.append(dict(kind='script-hold', frame=bottom_text(frame, self.assets, info['after_pause']), delay=0))
            if info.get('discard_pending_reads'): shown[-1] = dict(shown[-1], discard=int(info['discard_pending_reads']))
        report = list(getattr(self, 'report', ()))
        _family_choose(self, 0)
        self.report = report + list(self.report)
        following = self.session.decision
        if self.presentation_enabled and calibration_pause({'kind': 'ACK', 'info': info}) and following and following['kind'] == 'CREATE_INIT' and following['info'].get('caption'):
            shown.append(dict(kind='script-hold', frame=draw_calibration(self, None, 0, [str(following['info']['caption'])]), delay=2.0 * self.effect_scale))
    if falls: place_falls(self.report, falls)
    if shown and flush: shown[-1] = dict(shown[-1], flush_keys=True)
    if shown: rest = list(self.queue()); self.queue().clear(); self.queue().extend(shown + rest)
    elif flush: self.typeahead = []


def keep_highlight(self, index):
    d = self.session.decision
    if not compact(d) or yes_no_menu(d) or fight_rows(d): return
    shown = [i for i, _ in menu_items(d)]
    self.session.game.menu_highlight = index if index in shown and not getattr(self, 'escaping', False) else self.selected


_family_menu_screen = menu_screen


def menu_screen(controller):
    d = controller.session.decision
    return _family_menu_screen(controller) or bool(d and controller.session.game.s.mode == 0 and d['kind'] == 'CREATE_SLOT' and bottom_query(controller)) or file_name(controller)


NAMES_SHOWN = {}
READY_LIVE = {}
HP_HELD = {}


def healed(controller, info):
    from ..creation import F
    seen = getattr(controller, 'hp_seen', None)
    if not seen or 'creature_name' not in info: return {}
    game = controller.session.game
    if game.s.g.get('dkk.battle', {}).get('active'): return {}
    if info.get('creature_text') not in (game.assets.text('fullyHealedText'), game.assets.text('partiallyHealedText')): return {}
    for i, c in enumerate(game.s.party[:len(seen)]):
        if bytes(c.b[1:1 + c.b[0]]).decode('cp437') == info['creature_name'] and c.b[F['hp']] != seen[i]:
            old, seen[i] = seen[i], c.b[F['hp']]
            return dict(game=game, member=i, hp=old)
    return {}


def roster_moved(game, members):
    shown = getattr(game.vm, 'ready_shown', None)
    if READY_LIVE.get('shown') is not shown: READY_LIVE.update(shown=shown, members=set())
    if shown is None: READY_LIVE.clear()
    else: READY_LIVE['members'].update(members)
    rows = getattr(game.vm, 'rows_shown', None)
    if rows: game.vm.rows_shown = {i: v for i, v in rows.items() if i not in members}


def roster_question(controller, d):
    return bool(d and d['kind'] in ('CREATE_OVERWRITE', 'CREATE_FILE_NAME') and controller.session.game.s.mode == 0 and creation_pending(controller) is False)


def creation_pending(controller):
    from .. import creation
    return creation.PENDING in controller.session.game.s.g


def control_key(controller, char):
    if char not in (chr(19), chr(21), chr(4), chr(26)): return False
    runtime = controller.session.game.s.g.setdefault('dkk.runtime', {})
    if char == chr(19) and controller.sound_on: runtime['sound_saved'], controller.sound_on = 4, False
    elif char == chr(19): controller.sound_on = runtime.get('sound_saved') in (3, 4)
    if char == chr(21): runtime['music_on'] = int(not runtime.get('music_on'))
    if char == chr(4): runtime['trace'] = int(not runtime.get('trace'))
    return True


COIN_SHOWN = {}


def coin_amount(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'NUMBER' and d['info'].get('purpose') == 'money' and COIN_SHOWN)


def move_stepped(controller, decision):
    return bool(decision and decision['kind'] == 'COMBAT_MOVE' and getattr(controller, 'stepped', False))


def file_name(controller):
    d = controller.session.decision
    return bool(d and d['kind'] == 'CREATE_FILE_NAME' and controller.session.game.s.mode == 0 and not icon_screen(controller))


VIEW_CALLERS = ('SHOP_MENU', 'TEMPLE', 'CAMP_MENU', 'COMBAT_ACTION', 'COMBAT_LOOT')


def view_start(self, answered, index):
    if answered and answered['kind'] == 'CREATE_VIEW':
        shown = [i for i, _ in menu_items(answered)]
        self.view_word = shown.index(index) if index in shown else 0
    following = self.session.decision
    if not following or following['kind'] != 'CREATE_VIEW' or 'start' in following['info']: return
    info = answered['info'] if answered else {}
    entry = not answered or answered['kind'] in VIEW_CALLERS or info.get('vault_menu') or info.get('world_menu') or info.get('action') == 'main-menu'
    shown = [i for i, _ in menu_items(following)]
    at = 0 if entry else getattr(self, 'view_word', 0)
    self.horizontal_choice = at if at < len(shown) else 0; self.selected = shown[self.horizontal_choice]


def _choose(self, index):
    answered = self.session.decision
    keep_highlight(self, index)
    if answered and answered['kind'] == 'CREATE_VIEW': self.sheet_seen = answered['info']
    if answered and answered['kind'] == 'CREATE_INIT': INIT_SHOWN.update(decision=answered)
    if answered and answered['info'].get('purpose') == 'appraise': APPRAISE_SHOWN.update(info=answered['info'])
    if compact(answered) and index in [i for i, _ in menu_items(answered)]: self.choice_global = [i for i, _ in menu_items(answered)].index(index)
    if items_list(self.session.decision): items_screen(self.session.decision, self.session.game); ITEMS_SHOWN.update(decision=self.session.decision, index=index, top=vertical(self)['first'])
    if answered and answered['kind'] == 'TEMPLE_LIST': HEAL_SHOWN.update(decision=answered, index=index, top=vertical(self)['first'])
    if taking(answered): TAKE_SHOWN.update(decision=answered, top=vertical(self)['first'])
    if listed(answered) and not answered['info'].get('menu'): SCRIBE_SHOWN.update(decision=answered)
    CAST_SHOWN.clear()
    if listed(answered) and answered['info'].get('menu'): CAST_SHOWN.update(decision=answered)
    self.word_carry = index if heal_confirm(answered) else None
    word = self.horizontal_choice if answered and answered['kind'] == 'TEMPLE_LIST' else None
    if _family_pick_who(answered) and index == len(answered['options']) - 1 and self.selected < index: self.session.game.s.sel = self.selected
    game = self.session.game
    shown = [bytes(c.b[1:1 + min(15, c.b[0])]).decode('cp437') for c in game.s.party]
    from ..creation import F
    self.hp_seen = [c.b[F['hp']] for c in game.s.party]
    if buying(answered):
        from ..shop import coins, STEEL
        self.money_seen = coins(game.s.selc())[STEEL], game.s.treasure_money[STEEL]
    moved, was = bool(answered and answered['options'] and 0 <= index < len(answered['options']) and answered['options'][index] in ('char-up', 'char-down')), game.s.sel
    self.answered_index = index
    aimed = (game.s.g['dkk.battle']['actor'], [bytearray(row) for row in render(self).rows[184:200]]) if aim_menu(answered) else None
    self.report_actor = game.s.g.get('dkk.battle', {}).get('actor') if answered and answered['kind'] != 'COMBAT_AUTO' else None
    if not game.s.g.get('dkk.battle', {}).get('active'): self.fight_keys, self.fight_key_times = [], []
    result = _family_choose(self, index)
    if moved: roster_moved(game, (was, game.s.sel))
    pass_timed(self, answered)
    self.aim_kept = (self.report,) + aimed if aimed else None
    following = self.session.decision
    self.stepped = bool(answered and following and answered['kind'] == following['kind'] == 'COMBAT_MOVE')
    if coin_list(answered) and following and following['kind'] == 'NUMBER': COIN_SHOWN.update(decision=answered)
    elif not (answered and following and answered['kind'] == following['kind'] == 'NUMBER'): COIN_SHOWN.clear()
    if not roster_question(self, following): NAMES_SHOWN.clear()
    elif not roster_question(self, answered): NAMES_SHOWN.update(game=game, names=shown)
    if member_who(following): self.selected = min(int(following['info'].get('start') or 0), len(following['options']) - 2)
    if member_who(answered) and coin_list(following):
        from .. import inventory
        char = self.session.game.s.selc(); self.sheet_seen = inventory.sheet(self.session.game, own_copy(char.b, char.items, char.effects))
    modifying = bool(following and following['kind'] == 'CREATE_MODIFY')
    self.name_green = modifying and (getattr(self, 'name_green', False) or '6' in str(following['info'].get('dirty', '')).split())
    if yes_no_menu(following):
        self.horizontal_choice = yes_no_start(following); self.selected = menu_items(following)[self.horizontal_choice][0]
    elif following and following['info'].get('world_menu') and not following['info'].get('extended_mode'):
        shown = [i for i, _ in menu_items(following)]
        if 0 <= int(following['info'].get('start') or 0) < len(shown):
            self.horizontal_choice = int(following['info'].get('start') or 0); self.selected = shown[self.horizontal_choice]
    elif following and following['kind'] == 'CREATE_ICON' and following['info'].get('icon_state'):
        shown = [i for i, _ in menu_items(following)]
        at = getattr(self, 'choice_global', 0)
        self.horizontal_choice = at if at < len(shown) else 0; self.selected = shown[self.horizontal_choice]
    view_start(self, answered, index)
    self.take_number = bool(taking(answered) and following and following['options'] is None)
    if following and following['info'].get('action') == 'main-menu' and answered and (answered['kind'] == 'MENU' or answered['kind'] == 'ACK' and answered['info'].get('message') == self.session.game.assets.text('partyDestroyed')):
        self.selected = self.menu_row = 0
    if following and following['info'].get('action') == 'main-menu' and following['info'].get('start') is not None:
        self.selected = self.menu_row = min(int(following['info']['start']), len(following['options']) - 1)
    if word is not None and following and following['kind'] == 'TEMPLE':
        shown = [i for i, _ in menu_items(following)]
        self.horizontal_choice = word if word < len(shown) else 0; self.selected = shown[self.horizontal_choice]
    if items_list(following) and answered and answered['kind'] == 'CREATE_VIEW': self.item_word = 0
    if items_list(following) and (item_words(answered) or items_offer(answered)):
        rows = [i for i, _ in vertical(self)['nodes'] if i is not None and following['options'][i] is not None]
        if rows: self.selected = rows[min(int(ITEMS_SHOWN['index']), len(rows) - 1)]
    if items_list(following) and following['info'].get('message') and self.presentation_enabled: self.queue().append(dict(kind='script-hold', frame=bottom_line(render(self), self.assets, following['info']['message']), delay=pause(self)))
    return result


def item_menu(controller):
    from ..inventory import item_actions, SHOP_TEMPLE
    game = controller.session.game
    return item_actions(game, game.s.selc(), game.s.mode == SHOP_TEMPLE) + ['Exit']


def item_key(self, d, keysym, char):
    words, at = item_menu(self), getattr(self, 'item_word', 0)
    if keysym in ('Up', 'Down', 'Home', 'End', 'Next', 'Prior'): return None
    if keysym in ('Left', 'Right'):
        self.item_word = (at + (1 if keysym == 'Right' else -1)) % len(words); return False
    if keysym == 'Escape': word = 'Exit'
    elif keysym in ('Return', 'KP_Enter'): word = words[min(at, len(words) - 1)]
    else:
        hits = [n for n, w in enumerate(words) if char and w[:1].lower() == char.lower()]
        if not hits: return False
        self.item_word, word = hits[-1], words[hits[0]]
    if word == 'Exit': return _choose(self, len(d['options']) - 1)
    item = self.selected
    _choose(self, item)
    following = self.session.decision
    if following and following['kind'] == 'VIEW_ACTION' and word in following['options']: _choose(self, list(following['options']).index(word))
    following = self.session.decision
    if items_list(following): self.selected = min(item, len(following['options']) - 2)
    return True


SCANS = dict(Up=72, Down=80, Left=75, Right=77, Home=71, End=79, Prior=73, Next=81, Delete=83)
TYPED = dict(Return=chr(13), KP_Enter=chr(13), Escape=chr(27), BackSpace=chr(8))


def modify_key(keysym, char):
    if keysym in TYPED: return TYPED[keysym]
    if keysym in SCANS: return '#%d' % SCANS[keysym]
    return char if len(char) == 1 and ' ' <= char <= '~' else None


def next_word(d, selected, right):
    shown = [i for i, _ in menu_items(d)]
    at = shown.index(selected) if selected in shown else 0
    return shown[(at + (1 if right else -1)) % len(shown)]


def steps_on(d, keysym, char):
    return bool(d['info'].get('overland')) and (char in ('5', chr(92)) or keysym in STEP_KEYS or keysym.startswith('Alt-'))


def demo_key(controller, keysym, char):
    d = controller.session.decision
    if not d or getattr(controller.session.game, 'battle', None) is None: return False
    return d['kind'] != 'COMBAT_AUTO' or keysym.lower() in ('space', 'alt-m') or char == '2'


def _key(self, keysym, char=''):
    if keysym[:4].lower() == 'alt-': keysym = 'Alt-' + keysym[4:].lower()
    title.update(self)
    if title.active(self): return title.key(self, keysym, char)
    if title.demo_on(self.session.game) and not demo_key(self, keysym, char): return False
    if keysym != 'F10' and not self.file_menu and not getattr(self, 'typing', False) and self.held() is not None:
        self.typeahead = getattr(self, 'typeahead', []) + [(keysym, char)]; return False
    if fight_playback(self, keysym):
        if not getattr(self, 'fight_keys', None): self.fight_keys_seen, self.fight_key_times = loaded_picture(self), []
        self.fight_keys = getattr(self, 'fight_keys', []) + [(keysym, char)]
        self.fight_key_times = getattr(self, 'fight_key_times', []) + [(self.clock() - self.report_at) / self.effect_scale]; return False
    if control_key(self, char):
        if not one_key_pause(self): return False
        keysym, char = 'Return', ''
    d = self.session.decision
    if d and d['kind'] == 'CREATE_MODIFY' and d['options'] is None and not self.file_menu and self.held() is None:
        token = modify_key(keysym, char)
        return False if token is None else _choose(self, token)
    if pick_who(d) and not self.file_menu and keysym != 'Escape' and (KEYPAD.get(char, keysym) in ('Home', 'End', 'Next', 'Prior', 'Clear') or char.lower() == 'e'): return False
    if d and d['kind'] == 'CAMP_REST' and not self.file_menu and self.held() is None and not holding(self):
        keysym = KEYPAD.get(char, keysym)
        if keysym in ('Left', 'Right'):
            self.selected = next_word(d, self.selected, keysym == 'Right'); return False
        if keysym in ('Up', 'Down'):
            kept, result = self.selected, _choose(self, d['options'].index('Add' if keysym == 'Up' else 'Subtract'))
            if self.session.decision and self.session.decision['kind'] == 'CAMP_REST': self.selected = kept
            return result
        if keysym in REST_EXIT_KEYS or keysym.startswith('Alt-'): return _choose(self, d['options'].index('Exit'))
    if keysym == 'Escape': char = ''
    if is_list(self): self.list_top = vertical(self)['first']
    d = self.session.decision
    if items_list(d) and not self.file_menu and self.held() is None and not self.error:
        result = item_key(self, d, keysym, char)
        if result is not None: return result
    if pick_who(d) and char.lower() == 'e': return False
    if script_who(d) and char.lower() == 'e': return False
    if script_who(d) and char in ('8', '2'): keysym, char = ('Up' if char == '8' else 'Down'), ''
    if d and d['kind'] == 'MENU' and d['info'].get('extended_mode') and keysym != 'Escape' and not self.file_menu and self.held() is None:
        if steps_on(d, keysym, char): return _choose(self, d['options'].index('step')) if 'step' in d['options'] else False
        keysym = KEYPAD.get(char, keysym)
        command = (COMPASS_KEYS if d['info'].get('overland') else MOVE_KEYS).get(keysym)
        if command in d['options']: return _choose(self, d['options'].index(command))
        if keysym in KEYPAD.values(): return False
    if keysym == 'Escape' and d and d['kind'] == 'CREATE_ICON' and d['info'].get('icon_state') and not self.file_menu: return False
    if (keysym == 'Escape' and compact(d) and d['options'] is not None and not self.file_menu and self.held() is None
            and (d['info'].get('escape_choice') is not None or d['kind'] == 'CREATE_VIEW' and 'Exit' in d['options'])):
        self.escaping = True
        try: return _choose(self, int(list(d['options']).index('Exit') if d['info'].get('escape_choice') is None else d['info']['escape_choice']))
        finally: self.escaping = False
    if (keysym == 'Escape' and d and d['options'] is not None and 'escape' in d['options'] and not self.file_menu
            and self.held() is None and not holding(self) and self.text_page*6+6 >= len(self.lines)):
        return _choose(self, list(d['options']).index('escape'))
    if (d and d['options'] is not None and keysym != 'F10' and not self.file_menu and self.held() is None and not holding(self)
            and self.text_page*6+6 >= len(self.lines)):
        if keysym == ' ': keysym = 'space'
        if fight_rows(d): return fight_key(self, d, keysym, char)
        if d['kind'] == 'COMBAT_SPELL_AIM' and 'Center' in d['options'] and (keysym in ('space', 'Clear') or char == '5'):
            return False if keysym == 'Clear' and char != '5' else _choose(self, d['options'].index('Center'))
        if d['info'].get('action') == 'main-menu' and keysym == 'space': return False
        if (compact(d) and keysym in ('Up', 'Down') and 'char-up' not in d['options']
                and d['kind'] not in ('TARGET', 'COMBAT_MOVE', 'COMBAT_SPELL_AIM', 'MOVE', 'CAMP_REST', 'CAMP_RESTING', 'COMBAT_LOOT')):
            return False
    number_cells(self, d, keysym, char)
    result = _family_key(self, keysym, char)
    pass_timed(self, d)
    return result


MODIFIER_KEYS = ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R')


def fight_playback(self, keysym):
    game = self.session.game
    return (keysym != 'F10' and keysym not in MODIFIER_KEYS and not self.file_menu and getattr(game, 'battle', None) is not None
            and not title.demo_on(game) and holding(self))




ACTING = ('move', 'attack', 'missile', 'bolt')


def poll_times(self):
    actor, at, polls, previous = getattr(self, 'report_actor', None), 0.0, [], None
    for entry in self.report:
        who = entry.get('actor') if isinstance(entry, dict) and entry['kind'] in ACTING else None
        if who is not None and who != actor and (who != previous or entry['kind'] == 'move'): polls.append(at)
        if who is not None: previous = who
        at += report_hold(entry, pause(self, False))
    return polls


def turn_box(controller, progress, cursor, size):
    if getattr(controller, 'capturing', False) or progress is None or not holding(controller): return cursor, size
    actor, acted, seen = getattr(controller, 'report_actor', None), False, controller.report[:progress[0] + 1]
    for entry in seen:
        if isinstance(entry, dict) and entry['kind'] in ACTING and entry.get('actor') is not None:
            if entry['actor'] != actor: actor, acted = entry['actor'], False
            acted = acted or not (entry['kind'] == 'move' and entry.get('still'))
    places = next((e['actors'] for e in reversed(seen) if isinstance(e, dict) and 'actors' in e), None)
    if places is None: places = [(r['x'], r['y'], r['size']) for r in controller.session.game.s.g.get('dkk.battle', {}).get('actors', ())]
    if actor is None or acted or actor >= len(places) or not places[actor][2]: return None, size
    return tuple(places[actor][:2]), places[actor][2]


def stamped(report, progress, step):
    if isinstance(step, dict) or progress is None: return step
    return next((e for e in reversed(report[:progress[0]]) if isinstance(e, dict) and 'panel' in e), step)


def string_places(controller, progress):
    report = controller.report
    if progress is None or not isinstance(report[progress[0]], str): return None
    at = progress[0]
    entry = next((e for e in reversed(report[:at]) if isinstance(e, dict) and 'actors' in e), None)
    if entry is None: return None
    later = next((e['actors'] for e in report[at + 1:] if isinstance(e, dict) and 'actors' in e), None)
    if later is None: later = [(r['x'], r['y'], r['size']) for r in controller.session.game.s.g.get('dkk.battle', {}).get('actors', ())]
    falls = {fall.get('actor') for e in report[at + 1:] if (fall := falling(e))}
    gone = {entry.get('actor')} if entry['kind'] == 'fall' else set()
    return [(x, y, 0 if i in gone or i < len(later) and not later[i][2] and i not in falls else size) for i, (x, y, size) in enumerate(entry['actors'])]


def poll_read(key):
    keysym, char = key
    return 'manual' if keysym in (' ', 'space', 'Alt-d') or char == ' ' else 'magic' if keysym in ('2', 'Alt-m') or char == '2' else None


def poll_fight_keys(self):
    keys = getattr(self, 'fight_keys', None)
    d = self.session.decision
    if not keys or not d or (progress := report_step(self)) is not None and progress[0] < len(self.report): return False
    times = getattr(self, 'fight_key_times', None) or []
    timed_keys, reads, start = list(zip(keys, times if len(times) == len(keys) else [float('inf')] * len(keys))), [], 0
    for at in poll_times(self):
        polled = [key for key, t in timed_keys[start:] if t < at]
        if polled: reads, start = reads + [poll_read(polled[0])], start + len(polled)
    keys, self.fight_keys, self.fight_key_times = [key for key, _ in timed_keys[start:]], [], []
    auto = d['kind'] == 'COMBAT_AUTO'
    if auto: reads, keys, typed = reads + [poll_read(key) for key in keys[:1]], [], bool(keys)
    manual, magic = 'manual' in reads, reads.count('magic') % 2 == 1
    if auto:
        if not (typed or manual or magic): return False
        self.choose(d['options'].index('Manual' if manual else 'Magic' if magic else 'Continue'))
        manual, magic = False, magic and manual
    for word, wanted in (('space', manual), ('Alt-m', magic)):
        d = self.session.decision
        if wanted and fight_rows(d) and word in d['options']: self.choose(d['options'].index(word))
    if keys and loaded_picture(self) == getattr(self, 'fight_keys_seen', None): self.typeahead = getattr(self, 'typeahead', []) + keys
    return auto


def _poll(self):
    if not poll_fight_keys(self): _family_poll(self)


def number_cells(self, d, keysym, char):
    if not (d and d['kind'] == 'NUMBER' and d['options'] is None and 'max' in d['info']) or self.file_menu: return
    if getattr(self, 'cells_for', None) != d.get('i'): self.cells_for, self.cells, self.cell_column = d.get('i'), [], 0
    if keysym == 'BackSpace':
        if not self.entry: return
        if self.cell_column < len(self.cells): self.cells[self.cell_column] = ' '
        self.cell_column -= 1
    elif len(char) == 1 and char in '0123456789':
        text = (self.entry + char)[:6]
        if int(text) <= int(d['info']['max']): self.cell_column += 1
        else: text = str(d['info']['max']); self.cell_column = len(text)
        self.cells = list(text) + self.cells[len(text):]


def entry_text(controller, decision):
    return ''.join(controller.cells).rstrip() if decision.get('i') is not None and getattr(controller, 'cells_for', None) == decision.get('i') else controller.entry


def _loadable(self):
    from .. import creation
    game = self.session.game
    if self.save_root: game.roster_directory = Path(self.save_root)
    return [slot for slot in 'ABCDEFGHIJ' if creation.slot_folder(game, slot).is_file()]


_family_capture = Controller.capture_text


def list_entry_top(self):
    self.spell_top = 0
    mark = self.session.game.s.g.get('dkk.item_pool')
    if mark is not getattr(self, 'reset_mark', None): self.list_top, self.reset_mark = 1, mark
    v = vertical(self)
    nodes, top = v['nodes'], getattr(self, 'list_top', 1)
    position = next((n for n, (i, _) in enumerate(nodes) if i == self.selected), None)
    d = self.session.decision
    if d and 'entry' in d['info']: position = int(d['info']['entry'])
    if len(nodes) <= v['rows']: top = 0
    if position is not None and top > position: top = position
    return 0 if top > len(nodes) else top


def _capture_text(self):
    d = self.session.decision
    game = self.session.game
    game.clear_combat_text = clear_combat_text
    if title.demo_on(game) and game.s.party:
        from ..creation import F
        game.demo_shown = list(game.s.party), {i: (c.b[F['hp']], c.b[F['ac']]) for i, c in enumerate(game.s.party)}
    if game.s.g.get('dkk.battle', {}).get('active'): game.fight_epoch = game.vm.text_epoch; game.__dict__.pop('left_cursor', None)
    elif d and d['kind'] == 'MOVE': game.__dict__.pop('fight_epoch', None); game.__dict__.pop('left_cursor', None)
    elif 'fight_epoch' in game.__dict__ and leave_question(d): game.left_cursor = left_cursor(d)
    elif 'fight_epoch' in game.__dict__ and (rect := notice_rect(self, d) or items_offer(d) and (1, 21, 38, 22)): game.left_cursor = notice_end(d, rect)
    kept = self.horizontal_choice if d is not None and d.get('i') == getattr(self, 'captured_for', None) else None
    before = getattr(self, 'list_shown', None)
    hidden = d['info'].pop('message', None) if d and d['kind'] == 'SHOP_MENU' else None
    try: _family_capture(self)
    finally:
        if hidden is not None: d['info']['message'] = hidden
    if d and d['kind'] == 'CAMP_CONFIRM' and d['info'].get('rest'): self.rest_info = d['info']
    if kept is not None and is_vertical(self): self.horizontal_choice = kept
    elif d and d['kind'] == 'TEMPLE_LIST' and getattr(self, 'word_carry', None) is not None: self.horizontal_choice, self.word_carry = self.word_carry, None
    if is_list(self):
        if self.list_shown != before: self.spell_top = list_entry_top(self)
        self.list_top = vertical(self)['first']
    self.captured_for = d and d.get('i')
    icon_seen(self, d)
    if spell_message(self) or d and d['kind'] == 'ACK' and 'creature_name' in d['info']: self.lines, self.line_colours = [], []
    if not self.file_menu: keep_message(self, d)
    if aim_menu(d):
        from ..combat import Battle
        self.aim_cell = Battle(self.session.game).position(int(d['info']['selected'])); self.aim_view = tuple(self.session.game.s.g['dkk.battle']['view'])
        self.aim_blank, shown = bool(d['info'].get('blank')), self.aim_options()
        if d['info'].get('highlight') in shown: self.horizontal_choice = shown.index(d['info']['highlight'])
        elif self.horizontal_choice >= len(shown): self.horizontal_choice = 0
    elif d and d['kind'] == 'COMBAT_SPELL_AIM' and 'Center' in d['options']:
        self.aim_cell, self.aim_view = tuple(self.session.game.s.g['dkk.battle']['aim']), tuple(self.session.game.s.g['dkk.battle']['view'])
    slow_window(self, d)


def keep_message(self, d):
    info = d['info'] if d else {}
    epoch = getattr(getattr(self.session.game, 'vm', None), 'text_epoch', None)
    if epoch != getattr(self, 'painted_epoch', epoch): self.painted = ([], [])
    self.painted_epoch = epoch
    if info.get('preserve_message') or d and d['kind'] == 'CAMP_CONFIRM' and info.get('prompt') == self.session.game.assets.text('quitToDosPrompt'):
        own = str(info.get('message') or '')
        if own: self.lines = ['', own] if info.get('camp_main') else town.wrapped_text(own)
        else: self.lines = list(getattr(self, 'painted', ([], []))[0])
        self.line_colours, self.camp_intro, self.text_page = [10] * len(self.lines), False, 0
    kind = d and d['kind']
    if kind == 'ALTER_ORDER': order_message(self, info)
    else: self.order_placing = False
    if kind == 'ALTER_SPEED':
        lines, colours = (list(part) for part in getattr(self, 'painted', ([], [])))
        lines, colours, message = lines + [''] * (2 - len(lines)), colours + [10] * (2 - len(colours)), str(info.get('message') or '')
        lines[1], colours[1] = message + lines[1][len(message):], 10
        self.lines, self.line_colours, self.text_page = lines, colours, 0
    elif getattr(self, 'window_kind', None) == 'ALTER_SPEED': self.lines, self.line_colours = [], []
    self.window_kind = kind
    self.painted =([], []) if d and d['kind'] in ('CAMP_REST', 'CAMP_RESTING') else (list(self.lines), list(self.line_colours))


def order_message(self, info):
    from ..creation import F
    member, message = str(info.get('member', '')), str(info.get('message') or '')
    if message:
        c = self.session.game.s.selc()
        self.lines = ['', member, message[len(member):].strip()]
        self.line_colours = [10, name_colour(c), 10]
    elif getattr(self, 'order_placing', False): self.lines, self.line_colours = [], []
    else: self.lines, self.line_colours = (list(part) for part in getattr(self, 'painted', ([], [])))
    self.order_placing, self.text_page = bool(info.get('placing')), 0


_family_bottom_query = bottom_query


def bottom_query(controller):
    d = controller.session.decision
    return str(d['info'].get('prompt', '')) if d and (d['kind'] in ('ALTER_ORDER', 'ALTER_SPEED') or buying(d) or taking(d)) else _family_bottom_query(controller)


Controller.choose, Controller.key, Controller.loadable, Controller.capture_text, Controller.poll = _choose, _key, _loadable, _capture_text, _poll
Controller.plus_file = 'dkk-plus.json'
AIM_KEYS = {'n': 'Next', 'p': 'Prev', 'm': 'Manual', 't': 'Target', 'c': 'Center', 'e': 'Exit'}
AIM_WORDS = ('Next', 'Prev', 'Manual', 'Target', 'Center', 'Exit')
_family_aim_key, _family_aim_options = Controller.aim_key, Controller.aim_options


def aim_menu(decision):
    return bool(decision and decision['kind'] == 'TARGET' and 'selected' in decision['info'] and 'Next' in decision['options'])


def aim_options(self):
    d = self.session.decision
    return [word for word in AIM_WORDS if word in d['options']] if aim_menu(d) else _family_aim_options(self)


def aim_key(self, keysym, char):
    d = self.session.decision
    if not aim_menu(d): return _family_aim_key(self, keysym, char)
    options, shown = d['options'], self.aim_options()
    if char in ('4', '6'): keysym = KEYPAD[char]
    if keysym in ('Left', 'Right'):
        self.horizontal_choice = (self.horizontal_choice + (1 if keysym == 'Right' else -1)) % len(shown); return False
    word = 'Escape' if keysym == 'Escape' else shown[self.horizontal_choice % len(shown)] if keysym in ('Return', 'KP_Enter') else AIM_KEYS.get(char.lower())
    if word not in options: return False
    if word in shown: self.horizontal_choice = shown.index(word)
    return self.choose(options.index(word))


Controller.aim_key, Controller.aim_options = aim_key, aim_options
_family_layout = layout


def layout(controller):
    title.update(controller)
    if title.active(controller): return title.layout(controller)
    result = _family_layout(controller)
    if typing(controller) is not None: result['animating'] = True
    return result


def window_frame(frame, game, assets, bottom):
    top = bytearray(assets.part('borderTopRow'))
    for column, cell, bias in ((8, 0x1F9, 21), (19, 0x1FA, 13), (30, 0x1FB, 17)): top[column] = game.s.r0[cell] + bias
    for x, tile in enumerate(top): frame.blit(x * 8, 0, assets.symbols[tile])
    for x, tile in enumerate(assets.part('borderBottomRow')): frame.blit(x * 8, bottom * 8, assets.symbols[tile])
    for y in range(1, bottom):
        for x in (0, 39): frame.blit(x * 8, y * 8, assets.symbols[7])


def draw_frame(frame, game, assets, big=False, window=False):
    window_frame(frame, game, assets, 23)
    if not window:
        for x, tile in enumerate(assets.part('dividerRow')): frame.blit(x * 8, 128, assets.symbols[tile])
    if big: return
    for y, tile in enumerate(assets.part('insetColumn')[:17]): frame.blit(128, y * 8, assets.symbols[tile])
    for (x, y), n in (((2, 2), 0), ((14, 2), 1), ((2, 14), 2), ((14, 14), 3)): frame.blit(x * 8, y * 8, assets.symbols[n])
    for i in range(3, 14):
        for x, y, n in ((i, 2, 4), (i, 14, 4), (2, i, 7), (14, i, 7)): frame.blit(x * 8, y * 8, assets.symbols[n])


def battle_over(game, decision):
    return bool(decision and decision['info'].get('prompt') == game.assets.text('continueBattle')) or aging_page(game, decision)


def aging_page(game, decision):
    return bool(decision and decision['kind'] == 'ACK' and 'message' in decision['info'] and 'experience' not in decision['info']
                and decision['info'].get('prompt') == game.assets.text('pressToContinue') and getattr(game, 'battle', None) is not None)


def draw_aging(frame, controller, info):
    text, message = controller.session.game.assets.text, str(info['message'])
    plain = message.startswith(text('ageStrainMsg')) or message.endswith(text('lastBreathMsg'))
    frame.rect(184, 112, 128, 64, 0); frame.rect(0, 184, 320, 16, 0)
    for row, line in enumerate(town.wrapped_text(message, 16)[:8], 14): frame.text(23, row, line, controller.assets, 15 if plain else 14, 16)
    frame.text(0, 24, str(info['prompt']), controller.assets, 13, 40)


def draw_character_message(frame, assets, info):
    column, row = int(info['creature_column']), int(info['creature_row'])
    width, (top, bottom) = 39 - column, (row, 21) if column == 23 else (row - 1, 22)
    frame.rect(column * 8, top * 8, width * 8, (bottom - top + 1) * 8, 0)
    frame.text(column, row, str(info['creature_name']), assets, int(info['creature_colour']), width)
    for y, line in enumerate(town.wrapped_text(str(info['creature_text']), width)[:bottom - row], row + 1): frame.text(column, y, line, assets, 10, width)


def combat_sheet(game, assets):
    sheet = getattr(game, 'combat_tile_frames', None)
    return sheet if sheet is not None else assets.combat_picture('DUNGCOM' if game.vm.is3d() else 'WILDCOM', 1)


def arena_code(battle, x, y):
    if hasattr(battle, 'ground_picture'): return battle.ground_picture(x, y)
    tile = battle.resolve_terrain(x, y) if 28 <= battle.tile(x, y) <= 31 else battle.tile(x, y)
    return battle.terrain(tile if 0 < tile <= 69 else 21, 3)


def arena_overlay(frame, assets, battle, x, y, px, py):
    if not 28 <= battle.tile(x, y) <= 31: return
    pixels = assets.combat_picture('COMSPR', battle.terrain(battle.tile(x, y), 3))[0]
    frame.blit(px, py, pixels, transparent=0, colours=assets.view_tables['icon_palette'], clip=(8, 8, 176, 176))


_family_battle = draw_battle
LEADERSHIP = 'Using leadership ability'


def draw_battle(controller, elapsed=0):
    game, assets = controller.session.game, controller.assets
    if 'tiles' not in game.s.g['dkk.battle']:
        frame = Frame(); window_frame(frame, game, assets, 23)
        decision = controller.session.decision or {'info': {}}
        if decision['info'].get('prompt') == LEADERSHIP:
            frame.text(1, 1, '  ' + LEADERSHIP + ' ', assets, 13, 38)
            led = [m for m in game.s.g['dkk.battle'].get('messages', ()) if isinstance(m, str) and ' leads ' in m]
            for row, text in enumerate(town.wrapped_text(led[-1] if led else '')[:20], 3): frame.text(1, row, text, assets, 15, 38)
            frame.text(0, 24, 'Press button or enter to continue', assets, 13, 40)
            return frame
        for row, text in enumerate(town.wrapped_text(str(decision['info'].get('prompt', '')))[:6], 17): frame.text(1, row, text, assets, 14, 38)
        return frame
    frame = _family_battle(controller, elapsed)
    window_frame(frame, game, assets, 22)
    progress = report_step(controller)
    if progress is not None and progress[0] < len(controller.report):
        from ..combat import Battle
        draw_fall(frame, controller, Battle(game), controller.report[progress[0]], progress)
        draw_flash(frame, controller, Battle(game), controller.report[progress[0]], progress)
    if (rows := aim_rows(controller, progress)) is not None: frame.rows[184:200] = [bytearray(row) for row in rows]
    left = left_line(controller.report, progress[0]) if progress is not None and holding(controller) else None
    if left is not None: frame.text(0, 24, 'Move/Attack, Move Left = %d ' % left, assets, 10)
    if fight_rows(controller.session.decision) and not holding(controller):
        draw_fight_rows(frame, controller, assets)
        if controller.error: frame.text(0, 23, controller.error, assets, 14, 40)
    for y, tile in enumerate(assets.part('dualPaneColumn')): frame.blit(22 * 8, y * 8, assets.symbols[tile])
    return frame


FLASH_STEP = 0.07
SPELL_SHOWS = ('flight', 'scatter', 'flash')


def flash_entry(self, info):
    data = self.session.game.s.g['dkk.battle']; r = data['actors'][info['anim']]; hit = bool(info.get('hit'))
    entry = dict(kind='flash', creature=info['anim'], hit=hit, at=(r['x'], r['y']), text=str(info.get('prompt', '')), frames=4 * (1 if hit else text_delay(self) + 1),
                 view=tuple(data['view']), panel=data.get('panel', -1), actors=tuple((a['x'], a['y'], a['size']) for a in data['actors']))
    if entry['panel'] >= 0 and 'panel_print' in data: entry['panel_print'] = dict(data['panel_print'])
    return entry


def flashed(report, entry):
    said = bool(report and entry['text'] and report[-1] == entry['text'])
    return report[:len(report) - said] + [dict(entry, said=said)]


def draw_flash(frame, controller, battle, step, progress):
    if not (isinstance(step, dict) and step['kind'] == 'flash'): return
    if step['text']: draw_fight_message(frame, controller.assets, battle, step['text'])
    k = int(progress[1] / FLASH_STEP)
    (ox, oy), (x, y) = step['view'][:2], step['at']
    if k >= step['frames'] or not (0 <= x - ox < 7 and 0 <= y - oy < 7): return
    pixels = controller.assets.combat_picture('COMSPR', (11 if step['hit'] else 9) + (128 if k % 4 > 1 else 0))[0]
    if k % 4 in (1, 2): pixels = tuple(row[::-1] for row in pixels)
    frame.blit(8 + (x - ox) * 24, 8 + (y - oy) * 24, pixels, transparent=0, colours=controller.assets.view_tables['icon_palette'], clip=(8, 8, 176, 176))


def ended_view(report, at):
    for entry in reversed(report[:at]):
        if not isinstance(entry, dict): continue
        if (shot := flown(entry)) is not None and 'view' in shot:
            shots = flight(tuple(shot['view']), tuple(shot['start']), tuple(shot['aim']))
            return shots[-1][:2] if shots else tuple(shot['view'][:2])
        return tuple(entry['view'][:2]) if 'view' in entry else None
    return None


_family_casting_spell = casting_spell


def casting_spell(report, at):
    shows = lambda e: isinstance(e, dict) and e['kind'] in SPELL_SHOWS
    kept = [e for e in report[:at + 1] if not shows(e)]
    return _family_casting_spell(kept + [e for e in report[at + 1:] if not shows(e)], len(kept) - 1) if kept else None


def aim_rows(controller, progress):
    kept = getattr(controller, 'aim_kept', None)
    if not kept or progress is None or kept[0] is not controller.report or not holding(controller): return None
    for entry in controller.report[:progress[0] + 1]:
        if isinstance(entry, str) and entry in BOTTOM_LINE: return None
        if isinstance(entry, dict) and (entry.get('actor', kept[1]) != kept[1] or entry['kind'] == 'begin' or entry['kind'] == 'clear' and entry.get('bottom')): return None
    return kept[2]


NOT_PRINTED = ('whatDoYouDoText', 'partyKilledText', 'partyGainsText')


def printed(game, parts):
    import re
    from ..shop import member_name
    text = game.assets.text
    names = tuple(member_name(c) + tail for c in game.s.chars() for tail in (' is hit FOR ', ' dies.'))
    plain_texts, gains = {text(key) for key in NOT_PRINTED}, text('congratulationsText') or None
    journal = re.compile(re.escape(text('journalEntryPrefix') or '') + r'\d+\.')
    damage = False
    for part in parts:
        plain = part.lstrip('\n ')
        damage = bool(names) and plain.startswith(names) or damage and part[:1] == '\n'
        if plain and not damage and plain not in plain_texts and not (gains and plain.startswith(gains)) and not journal.fullmatch(plain): return True
    return False


def typed_rect(controller, d):
    if leave_question(d): return (1, 17, 38, 22)
    if items_offer(d) and d['kind'] == 'SHOP_CONFIRM': return (1, 21, 38, 22)
    if heal_confirm(d): return (1, 19, 38, 22)
    if party_destroyed(controller): return (2, 5, 37, 22)
    if script_list(d) and d['info'].get('prompt'): return (1, 17, 38, min(22, 16 + len(town.wrapped_text(str(d['info']['prompt'])))))
    return None


def notice_rect(controller, d):
    info = d['info'] if d else {}
    if 'creature_name' in info and not controller.session.game.s.g.get('dkk.battle', {}).get('active'):
        column = int(info['creature_column'])
        return (column, int(info['creature_row']) + 1, 38, 21 if column == 23 else 22)
    if items_offer(d) and d['kind'] == 'ACK': return (1, 21, 38, 22)
    return None


def slow_on(controller):
    return bool(getattr(controller, 'slow_seen', (None, 0, 0, 0))[3])


def slow_window(self, d):
    game = self.session.game
    vm = getattr(game, 'vm', None)
    if not hasattr(vm, 'out'): return
    flag = int(game.s.g.get('dkk.runtime', {}).get('slow_text', 1))
    seen_vm, seen_len, seen_flag, on = getattr(self, 'slow_seen', (vm, vm.text_start, flag, flag))
    if seen_vm is not vm or seen_len > len(vm.out): seen_len, on = vm.text_start, flag
    if flag != seen_flag: on = flag
    if not flag and (battle_summary(d) or party_destroyed(self)): on = 1
    shown = printed(game, vm.out[seen_len:])
    if not shown and not on: self.slow = None
    self.typed = typed_rect(self, d) if on else None
    self.slow_seen = (vm, len(vm.out), flag, 0 if shown else on)


def typed_step(controller):
    return text_delay(controller) * 0.003 * controller.effect_scale


def row_lengths(frame, rect):
    left, top, right, bottom = rect
    lengths = []
    for row in range(top, bottom + 1):
        band = frame.rows[row * 8:row * 8 + 8]
        inked = [col for col in range(left, right + 1) if any(any(line[col * 8:col * 8 + 8]) for line in band)]
        lengths.append(inked[-1] - left + 1 if inked else 0)
    return lengths


def type_cells(frame, rect, count):
    left, top, right, _ = rect
    for row, length in enumerate(row_lengths(frame, rect), top):
        keep = max(0, min(count, length))
        for line in frame.rows[row * 8:row * 8 + 8]: line[(left + keep) * 8:(right + 1) * 8] = bytes((right + 1 - left - keep) * 8)
        count -= length
    return count >= 0


def typing(controller):
    step = typed_step(controller)
    if not getattr(controller, 'typed', None) or step <= 0 or controller.file_menu: return None
    return int((controller.clock() - controller.decided_at) / step)


def typed_hold(self, frame, delay):
    rect = notice_rect(self, self.session.decision) if slow_on(self) else None
    step = typed_step(self) if rect else 0
    cells = sum(row_lengths(frame, rect)) if step > 0 else 0
    return dict(kind='script-hold', frame=frame, delay=delay + cells * step, typed=rect) if cells else dict(kind='script-hold', frame=frame, delay=delay)


def typed_script_holds(self, events):
    out, last, known = [], getattr(self, 'script_typed', None), getattr(self, 'script_cells', None)
    for event in events:
        if event.get('typed_seen'): out.append(event); continue
        text = None if 'frame' in event else event.get('text')
        continuing = bool(text and last and text != last and text.startswith(last))
        if text and (continuing or not text.startswith(last or chr(0))) and typed_step(self) > 0 and event['delay'] > 0:
            frame = render_hold(self, event)
            cells = sum(row_lengths(frame, SCRIPT_TEXT))
            base = (cells if known is None else min(known, cells)) if continuing else 0
            if cells > base: event = dict(kind='script-hold', frame=frame, delay=event['delay'] + (cells - base) * typed_step(self), typed=SCRIPT_TEXT, typed_from=base)
            known = cells
        elif text is not None and text != last: known = None
        if text is not None: last = text
        out.append(dict(event, typed_seen=True))
    self.script_typed, self.script_cells = last, known
    return out


SCRIPT_TEXT = (1, 17, 38, 22)


def typed_hold_frame(controller, event):
    frame, step = event['frame'], typed_step(controller)
    if not event.get('typed') or step <= 0 or controller.hold_event is not event: return frame
    import copy
    shown = copy.copy(frame); shown.rows = [bytearray(row) for row in frame.rows]
    type_cells(shown, event['typed'], event.get('typed_from', 0) + int((controller.clock() - controller.hold_until + event['delay']) / step))
    return shown


def one_key_pause(controller):
    d, game = controller.session.decision, controller.session.game
    if controller.file_menu or not d: return False
    if controller.text_page * 6 + 6 < len(controller.lines): return True
    if d['kind'] == 'ACK' and 'message_colour' in d['info'] and not d['info'].get('timed'): return True
    return damage_page(d) or aging_page(game, d) or party_destroyed(controller) or d['info'].get('prompt') == LEADERSHIP


def render(controller, assets=None, elapsed=0):
    frame = full_render(controller, assets, elapsed)
    count = typing(controller) if elapsed > 0 and controller.held() is None else None
    if count is not None and type_cells(frame, controller.typed, count): controller.typed = None
    return frame


def test():
    from ._screen_test import test as check
    check()
