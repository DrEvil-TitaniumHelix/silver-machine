from importlib import import_module
import re
from sm.titles.ssb import vm as retained
from sm.titles.ssb.walk import Map, DELTAS
from sm.titles.cok.town import VM as FamilyVM
from . import ecl, rules
from .records import Character, Item, Effect, split_records
from .faults import BindingRequired


def wrapped_text(text, width=38):
    if width < 1: raise ValueError('text width must be positive')
    lines = []
    for paragraph in text.rstrip().splitlines():
        row, wrapped = '', False
        for match in re.finditer(r'[!,\-.:;?]*[^!,\-.:;? ]*(?:[!,\-.:;?]+| |$)', paragraph):
            token = match.group()
            if wrapped: token = token.lstrip(' ')
            if not token: continue
            if len(row) + len(token) > width:
                lines.append(row.rstrip())
                row, wrapped, token = '', True, token.lstrip(' ')
            row += token
            if token: wrapped = False
        lines.append(row.rstrip())
    return lines


def buffer(character):
    return character.b if hasattr(character, 'b') else character.data


def field(char, name, index=0, *, width=1, signed=False):
    if name in ('memorized', 'known_spells', 'spell_slots'):
        book = rules.spellbook(char)
        if book is None: return 0
        raw = book.get(name)
        return int.from_bytes(raw[index:index + width], 'little', signed=signed)
    offset, size = Character.FIELDS[name]
    if index < 0 or index + width > size: raise ValueError('character field bounds')
    return int.from_bytes(char.b[offset + index:offset + index + width], 'little', signed=signed)


def put(char, name, value, index=0, *, width=1):
    if name in ('memorized', 'known_spells', 'spell_slots'):
        book = rules.spellbook(char)
        if book is None: raise BindingRequired('spell write to a character without a spell block')
        offset, size = book.FIELDS[name]
        buffer = book.data
    else:
        offset, size = Character.FIELDS[name]
        buffer = char.b
    if index < 0 or index + width > size: raise ValueError('character field bounds')
    buffer[offset + index:offset + index + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, 'little')


def script_menu(items):
    raw = ' '.join('~' + item for item in items)[:50]
    rendered, keys, starts = [], [], []
    cursor = 0
    while cursor < len(raw):
        char = raw[cursor]
        if char == '~':
            cursor += 1
            if cursor == len(raw): raise BindingRequired('script menu ends with an incomplete shortcut')
            char = raw[cursor]
            char = char.upper() if 'a' <= char <= 'z' else char
            keys.append(char)
            starts.append(len(rendered))
        elif '0' <= char <= '9' or 'A' <= char <= 'Z': char = chr(ord(char) + 32)
        rendered.append(char)
        cursor += 1
    text = ''.join(rendered)
    ends = starts[1:] + [len(text)]
    return text, tuple(keys), tuple(text[a:b].rstrip(' ') for a, b in zip(starts, ends))


def read_character(vm, address):
    c, offset = vm.s.selc(), address - 0x7C00
    if c is None: return None
    if 0 <= offset < 16:
        start = 1 + offset
        size = field(c, 'dimensions')
        if size > 2: raise BindingRequired('script name read exceeds a word')
        return int.from_bytes(c.b[start:start + size], 'little')
    if 0x14 <= offset <= 0x1A: return c.b[rules.F['abilities'] + 1 + (offset - 0x14) * 2]
    if 0x65 <= offset <= 0x6B: return c.b[rules.F['abilities'] + (offset - 0x65) * 2]
    if 0x1B <= offset <= 0x64: return field(c, 'memorized', offset - 0x1B)
    if 0x9A <= offset <= 0x9E: return field(c, 'saves', offset - 0x9A)
    if 0xA5 <= offset <= 0xAC: return field(c, 'thief_skills', offset - 0xA5)
    if 0xC3 <= offset <= 0xC8: return field(c, 'money', (offset - 0xC3) // 2 * 2, width=2)
    if offset in (0x2B1, 0x2B4): return vm.s.sel
    if offset == 0xEB: return sum(rules.tables().u8('classMaskBits', cls) for cls in (0, 2, 3, 4, 5, 6, 7) if field(c, 'levels', cls, signed=True) > 0) & 255
    if offset == 0x100: return 1 if field(c, 'active') else 128
    mapping = {0x71: 'base_thac0', 0x72: 'race', 0x76: 'hp_max', 0x9F: 'move', 0xB8: 'npc',
               0xBB: 'robe_order', 0xBC: 'deity', 0xBF: 'knight_order', 0xD3: 'magic_resistance',
               0xD6: 'gender', 0xD8: 'alignment', 0x10E: 'thac0', 0x119: 'hp', 0x11A: 'move'}
    if offset in mapping: return field(c, mapping[offset], signed=offset in (0x72, 0xBC, 0xD6, 0xD8)) & 65535
    if offset in (0x10F, 0x110): return field(c, 'ac', offset - 0x10F)
    if offset == 0x74: return field(c, 'age', width=2)
    return None


def write_character(vm, address, value):
    c, offset, s = vm.s.selc(), address - 0x7C00, vm.s
    if offset == 0x312:
        s.g['dkk.previous_disk'] = s.dataset
        s.dataset = ((value & 255) + 1) // 2
        return True
    if c is None: return False
    if offset == 0: s.g['A4B7'] = 1
    elif 0x1B <= offset <= 0x64:
        if rules.spellbook(c) is not None: put(c, 'memorized', value, offset - 0x1B)
    elif 0xC3 <= offset <= 0xC8: put(c, 'money', value, (offset - 0xC3) // 2 * 2, width=2)
    elif offset == 0xB8: put(c, 'npc', value)
    elif offset == 0x119: put(c, 'hp', value)
    elif offset == 0x100 and value == 1: put(c, 'status', 0); put(c, 'active', 1)
    elif offset == 0x10C and value in (0, 128, 129):
        put(c, 'side', int(value == 129)); put(c, 'auto_combat', int(value != 0))
    else: return False
    return True


class Geo:
    def __init__(self, records=None): self.records, self.map = records, None
    def load(self, state, ident):
        disk = 1 if state.dataset == 5 else state.dataset
        self.map = Map(disk, ident, record=self.records('GEO%d' % disk)[ident])
        for key in tuple(state.g):
            if key.startswith('door '): del state.g[key]
    def cell(self, state, x, y):
        if self.map is None or state.block in (0, 80) and not (0 <= x < 16 and 0 <= y < 16): return None
        return 0 if x > 15 else 15 if x < 0 else x, 0 if y > 15 else 15 if y < 0 else y
    def attr(self, state, x, y):
        cell = self.cell(state, x, y)
        return self.map.attr(*cell) if cell else 0
    def wall(self, state, x, y, facing):
        cell = self.cell(state, x, y)
        return self.map.walls(*cell, facing) if cell else 0
    def passage(self, state, x, y, facing):
        cell = self.cell(state, x, y)
        if cell is None: return 0
        if not self.wall(state, x, y, facing): return 1
        return state.g.get('door %d %d %d' % (*cell, facing), self.map.passages(*cell, facing))
    def approach(self, state):
        if not state.r0[0xE6]: state.r1[0x2C1] = 2; return 2
        x, y, distance = state.x, state.y, 0
        dx, dy = DELTAS[state.dir // 2]
        while self.map and distance < 2 and not self.wall(state, rules._s8(x), rules._s8(y), state.dir):
            x, y, distance = (x + dx) & 255, (y + dy) & 255, distance + 1
        return distance


def restart_requested(state):
    return bool(state.g.get('dkk.runtime', {}).get('restart_loop', 0))


class VM(retained.VM):
    def __init__(self, state, ask, geo=None, *, binding):
        super().__init__(state, ask, geo or Geo(), binding=binding)
        self.geo.records = binding.records
        self.high_bytes = []
        self.view_at, self.loading_notice, self.roster_shown, self.ready_shown, plain = None, False, None, None, self.ask
        self.linked_shown = None
        def asked(*arguments, **info):
            self.view_at, self.loading_notice = (self.s.x, self.s.y, self.s.dir), False
            return plain(*arguments, **info)
        self.ask = asked
        self.visual = dict(graphics=False, sprite=False, monster_sprite=False, monster_picture=False,
                           protection=False, colors=False, moved=False, sky=False,
                           wall_color=65, ceiling_color=9)
        self.icon_slot, self.breath_aim = 8, 0
        self.loaded_monster_count = self.monsters_loaded = self.undead_count = 0
        self.bottom_cleared = False
        self.files_loaded = self.map_loaded = self.pieces_loaded = False
        self.noncombat_redraw = False
        self.interface_redraw_epoch = 0
        self.portrait_clear_epoch = 0
        self.map_view_epoch = 0
        self.clear_box_epoch = 0
        self.clear_box_portrait = False
        self.info_line = None

    def run(self, address):
        self.pc, self.steps, self.s.stop = address, 0, 0
        while not (self.s.stop or self.s.party_dead or restart_requested(self.s)):
            self.steps += 1
            if self.steps > 200_000: raise retained.Halt('step limit at %04X' % self.pc)
            self.fetch()
            self.at = self.pc
            getattr(self, 'op%02X' % self.cur)()
        self.s.stop = 0

    def fetch(self):
        self.cur = self.s.code[self.pc - 0x8000]
        if self.cur not in ecl.OPS: raise BindingRequired('Death Knights opcode %02X at %04X' % (self.cur, self.pc))
        header = ecl.OPS[self.cur][1]
        values, self.next = ecl.operands(self.s.code, self.pc, header)
        self.ops = self.load_values(values)
        self.menu_prompt = self.strs[1] if self.cur == 0x15 else ''

    def load_tail(self, count):
        values, self.next = ecl.operands(self.s.code, self.next - 1, count)
        self.ops += self.load_values(values)

    def load_values(self, values):
        self.high_bytes.extend([0] * max(0, len(values) - len(self.high_bytes)))
        result = []
        for index, (kind, low, high, text) in enumerate(values):
            if kind in (1, 2, 3, 129): self.high_bytes[index] = high
            result.append((kind, low, self.high_bytes[index], text))
        self.read_strings(result)
        return result

    def getstr(self, address):
        address &= 65535
        if address == 0x7C00: return super().getstr(address)
        region = self.region(address)
        if region == 4: return ''
        memory, base = ((self.s.r0, 0x4B00), (self.s.r1, 0x7C00),
                        (self.s.r2, 0x7A00), (self.s.code, 0x8000))[region]
        start, output = address - base, []
        for at in range(start, min(len(memory), start + 255)):
            if not memory[at]: return ''.join(output)
            output.append(chr(memory[at] & 255))
        raise BindingRequired('unterminated script string')

    def code_addresses(self):
        return {a for pc, (_, _, following) in ecl.trace(bytes(self.s.code))[1].items() for a in range(pc, following)}

    def operand(self, operand):
        kind, low, high, _ = operand
        return low if kind == 0 else self.getmem(high * 256 + low, kind) if kind in (1, 3, 128) else high * 256 + low

    def v(self, index): return self.operand(self.ops[index - 1])
    def write(self, index, value): self.setmem(self.a(index), value, self.t(index))
    def set0(self, address, value): self.s.r0[address - 0x4B00] = value & 255
    def set1(self, address, value): self.s.r1[address - 0x7C00] = value & 255

    def getmem(self, address, kind=1):
        address &= 65535
        region, s = self.region(address), self.s
        if region == 0 and address in (0x4BEA, 0x4CF8): return s.dir if address == 0x4BEA else 1
        if region == 1:
            special = read_character(self, address)
            if special is not None: return special
        if region < 4:
            memory, base = ((s.r0, 0x4B00), (s.r1, 0x7C00), (s.r2, 0x7A00), (s.code, 0x8000))[region]
            at = address - base
            if kind > 1 and at + 1 >= len(memory): raise BindingRequired('word read crosses a script memory region')
            return memory[at] + (memory[at + 1] * 256 if kind > 1 else 0)
        return {0x33D: s.dir, 0xC04B: s.x & 65535, 0xC04C: s.y & 65535,
                0xC04D: s.dir // 2 if self.is3d() else s.dir, 0xC04E: s.ahead, 0xC04F: s.attr}.get(address, 0)

    def setmem(self, address, value, kind=1):
        address, value, s = address & 65535, value & 65535, self.s
        region = self.region(address)
        if region < 4:
            memory, base = ((s.r0, 0x4B00), (s.r1, 0x7C00), (s.r2, 0x7A00), (s.code, 0x8000))[region]
            at = address - base
            if address == 0x4BE6 and memory[at] != value: s.prev_mode, s.mode = s.mode, 4 if value else 3
            memory[at] = value & 255
            if kind > 1:
                if at + 1 >= len(memory): raise BindingRequired('word write crosses a script memory region')
                memory[at + 1] = value >> 8
            if region == 1: write_character(self, address, value)
            if region == 3: self.cache.clear()
        elif address == 0xC04B: s.x = rules._s8(value)
        elif address == 0xC04C: s.y = rules._s8(value)
        elif address == 0xC04D: s.dir = value % 4 * 2
        elif address in (0xC059, 0xC05F):
            self.visual['wall_color' if address == 0xC059 else 'ceiling_color'] = value & 255
            self.visual['colors'] = True
        if address in (0xC04B, 0xC04C, 0xC04D): self.visual['moved'] = True
        if address in (0x4BFD, 0x4BFE): self.visual['sky'] = True
        if address in (0xC04B, 0xC04C, 0xC04D, 0x4BFD, 0x4BFE, 0xC059, 0xC05F): self.display['view_dirty'] = True

    def load_block(self, ident):
        disk = 1 if self.s.dataset == 5 else self.s.dataset
        self.s.code[:] = bytes(ecl.BUFSIZE)
        raw = self.binding.records('ECL%d' % disk).get(ident & 255)
        if raw is None or len(raw) < 2: raise BindingRequired('script record unavailable')
        self.s.code[:len(raw) - 2] = raw[2:]
        self.cache.clear()
        self.s.g.pop('codemod', None)
        self.loading_notice = False

    def init_vm(self):
        self.pc, self.gosub, self.flags = 0x8000, [], [0] * 6
        self.vec = ecl.vectors(self.s.code)
        for _ in range(5):
            values, self.pc = ecl.operands(self.s.code, self.pc, 1)
            self.ops = self.load_values(values)
        self.visual.update(graphics=False, protection=False, monster_sprite=False, monster_picture=False,
                           wall_color=65, ceiling_color=9, colors=True)
        self.icon_slot, self.breath_aim = 8, 0
        self.s.r1[0x2D2:0x2D4] = [0, 0]
        self.s.g.update(A4B6=0, A4B7=0, **{'7603': 8})
        if not self.resuming:
            self.s.r0[0x100:0x120] = [0] * 32
            self.s.r1[0x379:0x383] = [0] * 10

    def op00(self):
        shown = self.s.sel if self.roster_shown is None else self.roster_shown
        super().op00()
        self.visual.update(graphics=False, protection=False, monster_sprite=False, monster_picture=False)
        self.text_cursor, self.box_cleared = (1, 17), False
        self.roster_shown = None if shown == self.s.sel else shown

    def load_big(self, ident):
        runtime = self.s.g.setdefault('dkk.runtime', {})
        runtime.update(picture_name='', picture_id=255)
        if runtime.get('big_id', 255) != ident: self.loading_notice = True
        runtime['big_id'] = ident

    def hold(self, seconds):
        queue = getattr(getattr(self, 'host', None), 'presentation', None)
        count = 0 if queue is None else len(queue)
        super().hold(seconds)
        if queue is None or len(queue) == count: return
        event = queue[-1]
        event['loading_notice'], event['linked_shown'] = self.loading_notice, self.linked_shown
        if self.roster_shown is not None: event['scene'].s.sel = self.roster_shown
        if self.view_at is not None: event['scene'].s.x, event['scene'].s.y, event['scene'].s.dir = self.view_at

    def redraw_view(self):
        self.view_at = self.s.x, self.s.y, self.s.dir
        if self.s.mode == 3: self.info_line = None
        self.display = dict(kind=None, sky=list(self.s.r0[0xFD:0xFF]),
                            wall_color=self.visual['wall_color'], ceiling_color=self.visual['ceiling_color'],
                            location=(self.s.x, self.s.y, self.s.dir))
        self.keep_info_line()

    def update_display(self):
        s = self.s
        s.attr = self.geo.attr(s, s.x, s.y)
        if any(self.visual[key] for key in ('graphics', 'sprite', 'colors', 'moved', 'sky')):
            self.redraw_view()
            self.paint_location()
            self.visual.update(graphics=False, sprite=False, monster_sprite=False, monster_picture=False,
                               colors=False, moved=False, sky=False)
            s.ahead = self.geo.wall(s, s.x, s.y, s.dir)

    def step(self):
        s = self.s
        if s.dir in (0, 2, 4, 6):
            axis, delta = ('x', 1 if s.dir == 2 else -1) if s.dir in (2, 6) else ('y', 1 if s.dir == 4 else -1)
            value = getattr(s, axis)
            value = value + delta if (delta > 0 and value < 15 or delta < 0 and value > 0) else (0 if delta > 0 else 15)
            setattr(s, axis, value)
        s.attr, s.ahead = self.geo.attr(s, s.x, s.y), self.geo.wall(s, s.x, s.y, s.dir)
        self.visual['moved'] = self.display['view_dirty'] = True

    def op04(self):
        self.pc = self.next
        a, b = self.v(1), self.v(2)
        if self.cur == 6:
            value, remainder = divmod(a, b)
            self.set1(0x7F3F, remainder)
        else: value = a + b if self.cur == 4 else b - a if self.cur == 5 else a * b
        self.write(3, value)
    op05 = op06 = op07 = op04
    def op08(self):
        self.pc = self.next
        self.write(2, self.s.random(min(255, (self.v(1) & 255) + 1)))
    def op09(self):
        self.pc = self.next
        if self.t(1) >= 128: self.setstr(self.a(2), self.strs[1])
        else: self.write(2, self.v(1))
    def op0B(self):
        self.pc = self.next
        if self.linked_shown is None: self.linked_shown = len(self.s.chars())
        return self.service('combat', 'load_monsters', *(self.v(i) & 255 for i in (1, 2, 3)))
    def op0C(self):
        self.pc = self.next
        self.set1(0x7EC0, self.v(2))
        self.set1(0x7EC1, min(self.m1(0x7EC0), self.geo.approach(self.s)))
        self.encounter_picture = (self.v(1) & 255, self.v(3) & 255)
        self.show_monster()
        self.s.g['combat.direction_flags'] = self.v(4) & 255
    def op0D(self):
        self.pc = self.next
        if self.m1(0x7EC1):
            self.set1(0x7EC1, self.m1(0x7EC1) - 1)
            self.show_monster()
    def show_monster(self):
        if self.visual['monster_picture']: return
        sprite, picture = getattr(self, 'encounter_picture', (255, 255))
        distance = self.m1(0x7EC1)
        if sprite != 255:
            if not self.visual['monster_sprite']:
                self.s.g['world.automap'] = 0
                self.display['automap'] = False
                if self.is3d():
                    self.visual.update(monster_sprite=True, sprite=True)
                    self.archive('SPRIT', sprite)
            else: self.redraw_view()
            if self.s.mode == 4:
                self.display.update(kind='SPRIT', dataset=self.s.dataset, id=sprite, pic=255, frame=distance, head=255)
        if picture != 255 and (distance == 0 or sprite == 255) and self.s.mode == 4:
            if not self.s.g.get('dkk.encounter_menu', 0) or self.s.g.get('dkk.monster_pictures', 0):
                self.visual.update(graphics=True, monster_picture=True)
                self.display = dict(kind='PIC', dataset=self.s.dataset, id=picture, frame=0, head=None)
                self.archive('PIC', picture)
                self.keep_info_line()
    def op0A(self):
        self.pc = self.next
        value = self.v(1) & 255
        index = value & 127
        self.s.g['47E2'] = 1
        missing = index >= len(self.s.chars())
        self.s.g['A4D1'] = self.s.g['8B6D'] = int(missing)
        if self.roster_shown is None: self.roster_shown = self.s.sel
        if not missing: self.s.sel = index
        if value & 128 and self.s.g.get('A4B6') and self.s.g.get('A4B7'):
            if self.s.sel == self.s.g.get('47E7', 0): self.s.g['47E2'] = 0
            self.remove_selected()
            self.party_drawn()
            self.s.g['A4B6'] = self.s.g['A4B7'] = 0
    def op0E(self):
        self.pc = self.next
        ident = self.v(1) & 255
        if ident == 255:
            if (self.s.prev_mode != 4 or self.s.mode == 4) and (self.visual['graphics'] or self.visual['sprite']):
                self.redraw_view()
                self.visual.update(graphics=False, sprite=False)
            self.visual.update(monster_sprite=False, monster_picture=False)
        else:
            self.visual.update(graphics=True, monster_picture=True)
            self.display = dict(kind='BIGPIC' if ident >= 112 else 'PIC', dataset=self.s.dataset,
                                id=ident, frame=0, head=None, map_cursor=ident == 112)
            if ident >= 112: self.info_line = None; self.load_big(ident)
            else: self.archive('PIC', ident); self.keep_info_line()
    op10 = FamilyVM.op10
    def archive(self, name, ident):
        runtime = self.s.g.setdefault('dkk.runtime', {})
        if ident == 255 or (runtime.get('picture_name'), runtime.get('picture_id')) == (name, ident): return
        runtime.update(picture_name=name, picture_id=ident, loads=runtime.get('loads', 0) + 1)
        if self.s.g.get('dkk.animations', 1): self.loading_notice = False
    def op0F(self):
        self.pc = self.next
        self.write(2, self.ask('NUMBER', None, at=self.at))
    def op11(self):
        self.bottom_cleared = False
        runtime = self.s.g.setdefault('dkk.runtime', {})
        runtime['slow_text'] = 1
        super().op11()
        runtime['slow_text'] = 0
    op12 = op11
    def op33(self):
        tail = ''.join(self.out[self.text_start:])
        lines = self.binding.wrapped_text(tail)
        full = lines and not tail.endswith('\n') and len(lines[-1]) + len(tail) - len(tail.rstrip(' ')) >= 38
        super().op33()
        if full: self.out.append('\n')
    def op15(self):
        header = ecl.OPS[self.cur][1]
        prompt = self.menu_prompt if self.cur == 0x15 else ''
        if self.cur == 0x31:
            self.text_color = 10
            self.out.append(self.host.assets.text('whatDoYouDoText'))
        count = self.v(header) & 255
        self.load_tail(count)
        self.pc = self.next
        if count > 10 or count >= len(self.strs): raise BindingRequired('script menu string slot unavailable')
        items = tuple(self.strs[1:count + 1])
        if self.cur == 0x15:
            self.bottom_cleared = False
            answer = self.ask('MENU', items, at=self.at, prompt=prompt or '', vertical=1)
            self.clear_text()
        else:
            text, shortcuts, labels = script_menu(items)
            roster = self.s.mode != 3 and self.m0(0x4CF7) == 1
            options = labels + (('char-up', 'char-down') if roster else ())
            while True:
                answer = self.ask('MENU', options, at=self.at, prompt='', vertical=0,
                                  script_menu=text, shortcuts=shortcuts, animate=self.visual['graphics'], enter_ok=False)
                if 0 <= answer < len(labels): break
                if roster and answer in (len(labels), len(labels) + 1) and self.s.chars():
                    from .camp import repaint_walking_row
                    repaint_walking_row(self.host, self.s.selc())
                    self.s.sel = (self.s.sel + (-1 if answer == len(labels) else 1)) % len(self.s.chars())
                    repaint_walking_row(self.host, self.s.selc())
        self.write(1, answer)
    op2B = op31 = op15
    def op13(self):
        if self.gosub: self.pc = self.gosub.pop()
        else:
            self.op00()
            self.pc += 1
    def op14(self):
        self.pc = self.next
        left = self.strs[1] == self.strs[2] if self.t(1) >= 128 else self.v(1) == self.v(2)
        if self.t(3) >= 128:
            start = 3 if self.t(1) >= 128 else 1
            right = self.strs[start] == self.strs[start + 1]
        else: right = self.v(3) == self.v(4)
        self.flags = [int(left and right), int(not (left and right)), 0, 0, 0, 0]
    def op16(self):
        self.pc = self.next
        if not self.flags[self.cur - 0x16]:
            self.cur = self.s.code[self.pc - 0x8000]
            count = ecl.SKIPCOUNT.get(self.cur, 0)
            if count:
                values, self.pc = ecl.operands(self.s.code, self.pc, count)
                self.ops = self.load_values(values)
            else: self.pc += 1
    op17 = op18 = op19 = op1A = op1B = op16
    def op1D(self):
        self.pc = self.next
        self.continue_menu()
    def continue_menu(self, **info):
        label = self.host.assets.text('pressToContinueMenu')[1:]
        roster = self.s.mode != 3 and self.m0(0x4CF7) == 1
        options = (label,) + (('char-up', 'char-down') if roster else ()) + ('escape',)
        self.display['bottom_line_cleared'] = False
        while True:
            choice = self.ask('MENU', options, at=self.at, script_continue=True, script_menu=label,
                              menu_labels=(label,), shortcuts=('P',), enter_ok=True,
                              animate=self.visual['graphics'], query_color=13, menu_color=10,
                              highlight_color=15, **info)
            if choice == 0 or not roster and choice == len(options) - 1: break
            if roster and choice in (1, 2) and self.s.chars():
                from .camp import repaint_walking_row
                repaint_walking_row(self.host, self.s.selc())
                self.s.sel = (self.s.sel + (-1 if choice == 1 else 1)) % len(self.s.chars())
                repaint_walking_row(self.host, self.s.selc())
        self.display['bottom_line_cleared'] = True
    def op1E(self):
        from .effects import has
        self.pc = self.next
        attribute = self.a(1) if self.t(1) == 1 else self.v(1)
        members, found = self.s.chars(), 0
        if attribute == 0:
            values = [0]
            found = int(any(has(c, self.v(2) & 255) for c in members))
        elif attribute == 0x7C19: values = [field(c, 'abilities', 11) for c in members]
        elif 0x7CA5 <= attribute <= 0x7CAC: values = [field(c, 'thief_skills', attribute - 0x7CA5) for c in members]
        elif attribute == 0x7C9F: values = [field(c, 'move') for c in members]
        else: return
        if not values: raise BindingRequired('party check requires a creature')
        for index, value in enumerate((min(values), max(values), sum(values) // len(values), found), 3):
            self.write(index, value)
    def op1C(self):
        from .combat import reset_monster_counters
        self.pc = self.next
        reset_monster_counters(self.host)
        self.s.treasure_money[:] = [0] * len(self.s.treasure_money)
        self.s.treasure_items.clear()
    def op1F(self):
        self.pc = self.next
        self.clear_text()
        self.text_color = 10
        self.out.append(self.host.assets.text('journalEntryPrefix') + str(self.v(1) & 255) + '.')
        self.continue_menu(journal=self.v(1))
    def op22(self):
        self.pc = self.next
        answer = self.ask('MENU', ('Yes', 'No'), at=self.at, start=0)
        self.flags = [int(answer == 0), int(answer == 1), 0, 0, 0, 0]
    def op23(self):
        self.clear_text()
        self.update_display()
        self.op00()
    def load_wall(self, ident, slot):
        pairs = list(self.s.g.get('save.wall_pairs', (
            (wall, 65535 if wall == 65535 else 1 if index == 0 and wall == 0 else index)
            for index, wall in enumerate(self.s.walls))))
        self.s.walls[slot] = ident
        if ident != 65535: self.loading_notice = True; self.s.g.setdefault('dkk.runtime', {})['big_id'] = 255
        pairs[slot] = (ident, 65535 if ident == 65535 else slot)
        self.s.g['save.wall_pairs'] = tuple(pairs)
    def op21(self):
        self.pc = self.next
        self.files_loaded = True
        ids = [self.v(i) & 255 for i in (1, 2, 3)]
        if self.cur == 0x21:
            self.map_loaded = True
            if ids[0] not in (127, 255) and self.is3d():
                self.set0(0x4BC5, ids[0]); self.geo.load(self.s, ids[0]); self.set1(0x7EC9, 0)
        else:
            self.pieces_loaded = True
            if ids[0] == 127: self.load_wall(0, 1)
            elif self.m0(0x4BE7) and self.m0(0x4BE8):
                self.load_wall(65535 if ids[0] == 255 else ids[0], 0)
                self.load_wall(65535 if ids[2] in (127, 255) else ids[2], 3)
            else:
                for slot, ident in enumerate(ids, 1): self.load_wall(65535 if ident == 255 else ident, slot)
        if self.pieces_loaded and self.map_loaded and self.s.prev_mode == 3:
            if self.s.mode != 3 and self.noncombat_redraw:
                self.interface_redraw_epoch += 1
                self.party_drawn()
            self.noncombat_redraw = False
    op37 = op21
    def op24(self):
        self.pc = self.next
        extended = self.s.g.get('world.extended', 0)
        self.s.g['world.extended'] = 0
        if self.monsters_loaded:
            distance = self.geo.approach(self.s)
            self.set1(0x7EC1, min(self.m1(0x7EC1), distance))
            self.s.g.setdefault('dkk.runtime', {}).update(picture_name='', picture_id=255, big_id=255)
            self.linked_shown = None
            self.loot_screen('run')
            self.s.g.setdefault('dkk.runtime', {})['big_id'] = 255
            if not self.is3d(): self.load_big(112)
        elif self.m0(0x4D00) == 1: self.set0(0x4D00, 0); self.interface('vault', 'run')
        elif self.m1(0x7F6C) == 1: self.set1(0x7F6C, 0); self.interface('shop', 'run', redraw=self.is3d())
        elif self.m1(0x7EE2) == 1: self.set1(0x7EE2, 0); self.interface('temple', 'run', redraw=self.is3d())
        else: self.loot_screen('treasure')
        self.s.mode = 4 if self.is3d() else 3
        self.set1(0x7ECA, self.m1(0x7ECA) & 1)
        self.visual.update(graphics=False, monster_picture=False, monster_sprite=False)
        self.s.g['world.extended'] = extended
    def op25(self):
        choice, count = self.v(1) & 255, self.v(2) & 255
        self.load_tail(count)
        self.pc = self.next
        if choice < count:
            if self.cur == 0x26: self.gosub.append(self.next)
            self.pc = self.a(choice + 3)
    op26 = op25
    def op27(self):
        from .shop import change_pool
        for i in range(3): change_pool(self.s, 4 + i, self.v(i + 1))
        count = self.v(4) & 255
        self.load_tail(count)
        self.pc = self.next
        templates = self.binding.records('ITEM0')[1]
        for i in range(count):
            ident = self.v(i + 5) & 255
            raw = templates[(ident - 1) * 17:ident * 17]
            if len(raw) == 17 and raw[0] != 255:
                item = Item(); item.data[46:] = raw
                self.s.treasure_items.insert(0, item.data)
    def op29(self): self.pc = self.next
    def op28(self):
        from . import inventory
        from .combat import roll
        self.pc = self.next
        whole, percent, chance = (self.v(i) & 255 for i in (1, 2, 3))
        if percent % 25: raise BindingRequired('script robbery Real fraction rounding is unverified')
        for char in self.s.chars() if whole else [self.s.selc()]:
            if char is None: continue
            for index in range(3):
                value = field(char, 'money', index * 2, width=2) * (100 - percent)
                put(char, 'money', (abs(value) // 100) * (-1 if value < 0 else 1), index * 2, width=2)
            remaining = chance
            for item in tuple(char.items):
                weight = int.from_bytes(item[inventory.I['weight']:inventory.I['weight'] + 2], 'little')
                remaining = max(0, remaining - (90 if weight > 255 else 50 if weight > 24 else 0))
                if roll(self.host, 1, 100, 'script robbery', self.s.chars().index(char)) <= remaining:
                    if item[inventory.I['readied']]: inventory.toggle_ready(self.host, self.s.selc(), item)
                    inventory.remove_item(char, item, self.host)
    def op2C(self):
        self.pc = self.next
        cue = self.v(1) & 255
        if cue & 128:
            if not hasattr(self.host, 'script_music'): self.host.script_music = []
            self.host.script_music.append(cue & 127)
        elif 1 <= cue <= 6: self.queue_sound(self.host.assets.table('soundCueTable')[cue - 1])
    def queue_sound(self, command):
        if not hasattr(self.host, 'script_sounds'): self.host.script_sounds = []
        self.host.script_sounds.append(command)
    def op2A(self):
        self.pc = self.next
        address = self.a(1) + (self.v(2) & 255)
        self.write(3, self.getmem(address, self.t(3)))
    def op35(self):
        self.pc = self.next
        address = self.a(2) + self.v(3)
        self.setmem(address, self.v(1), self.t(1))
    def dice(self, count, sides):
        from .effects import roll_dice
        return roll_dice(self.s, count & 255, sides & 255)
    def script_save(self, char, kind, modifier):
        from . import effects
        value = self.dice(1, 20)
        if effects.has(char, 57): value = 1
        if value in (1, 20): return value == 20
        if field(char, 'levels', 5, signed=True) > 0 and field(char, 'robe_order'):
            moon = self.s.r0[field(char, 'robe_order') + 0x1F8]
            modifier += -1 if moon == 0 else 1 if moon == 2 else 0
        roll = effects.camp_roll(self.host, save=(value + field(char, 'save_bonus', signed=True) + rules._s8(modifier & 255)) & 255,
                                 save_type=kind, save_passed=True)
        effects.trigger_condition(self.host, 12, char, roll)
        effects.remember(self.host, roll)
        return char.b[Character.FIELDS['saves'][0] + rules._s8(kind & 255)] <= roll.save & 255
    def script_hit(self, char, value):
        from . import effects
        natural = self.dice(1, 20)
        if natural <= 1: return False
        roll = effects.camp_roll(self.host, attack=100 if natural == 20 else natural)
        effects.trigger_condition(self.host, 16, char, roll)
        effects.remember(self.host, roll)
        return roll.attack >= 0 and roll.attack + (value & 255) > field(char, 'ac')
    def damage_wait(self, page=False):
        from sm.titles.cok.ui.screen import NEW_CONTINUE
        window = page is True
        label = NEW_CONTINUE if page == 'row' else self.host.assets.text('pressAnyKey' if window else 'pressToContinue')
        self.ask('MENU', (label,), at=self.at,
                 purpose='script damage', page=page, color=13 if window else 15, defeated=bool(self.s.party_dead))
    def script_damage(self, char, amount):
        from .shop import member_name
        status, hp = field(char, 'status'), field(char, 'hp')
        if status == 6: return
        text = member_name(char) + (' dies. ' if hp + 10 < amount else ' is hit FOR %s points of Damage.' % str(amount)[:3])
        lines = self.binding.wrapped_text(''.join(self.out[self.text_start:])) or ['']
        if self.display.get('damage_prefix', (None,))[0] != self.text_epoch:
            self.display['damage_prefix'] = self.text_epoch, len(lines), getattr(self, 'text_color', 15)
        exact, indent = len(lines[-1]) == 38, ''
        if exact and len(lines) >= 6:
            self.damage_wait(page='row')
            self.clear_text()
            lines, exact, indent = [], False, '  '
        for line in self.binding.wrapped_text(indent + text):
            if len(lines) + exact >= 6:
                self.damage_wait(page=True)
                self.clear_text()
                lines, exact = [], False
            self.out.append(('\n\n' if exact else '\n' if lines else '') + line)
            lines += [''] * exact + [line]
            exact = False
            self.text_color = 15
        damage = amount & 255
        remaining, overkill = (hp - damage, 0) if hp >= damage else (0, damage - hp)
        if overkill > 9 or remaining == 0 and status == 1: status = 6
        elif overkill: status = 5
        elif remaining == 0: status = 4
        put(char, 'status', status)
        if status in (0, 1): put(char, 'hp', remaining)
        else:
            put(char, 'active', 0)
            put(char, 'hp', 0)
        self.display['location_hidden'] = True
        self.display['misc_info'] = self.info_line = ''
        self.party_drawn()
    def op2E(self):
        self.pc = self.next
        s, chars = self.s, self.s.chars()
        attack, dice, sides, bonus, value = (self.v(index) & 255 for index in range(1, 6))
        amount = self.dice(dice, sides) + bonus
        def random_member():
            position = self.dice(1, self.m1(0x7F3E))
            if not 1 <= position <= len(chars): raise BindingRequired('script damage target beyond the creature list')
            return chars[position - 1]
        def saved_damage(char, kind):
            if not self.script_save(char, kind, attack & 15): self.script_damage(char, amount)
            elif attack & 16: self.script_damage(char, amount // 2)
        target = None if attack & 64 else random_member()
        if attack & 128:
            kind = value & 7
            if attack & 64:
                for char in chars:
                    if attack & 32: self.script_damage(char, amount)
                    else: saved_damage(char, kind)
            elif value & 128:
                if kind == 0: self.script_damage(s.selc(), amount)
                else: saved_damage(s.selc(), kind - 1)
            else: saved_damage(target, kind)
        else:
            for _ in range(attack):
                char = random_member()
                if self.script_hit(char, value): self.script_damage(char, amount)
                amount = self.dice(dice, sides) + bonus
        s.party_dead = int(not any(field(char, 'active') for char in chars))
        if s.party_dead:
            self.clear_text()
            self.text_color = 10
            self.out.append(self.host.assets.text('partyKilledText'))
            self.display = dict(kind=None, blank=True, party_killed=True)
            self.hold(3)
        self.damage_wait()
    def op36(self):
        from .combat import load_creature
        from .save import append_character
        self.pc = self.next
        ident = self.v(1) & 255
        if self.m1(0x7F3E) <= 7:
            char = load_creature(self.host, ident)
            for at, item in enumerate(char.items):
                slot = rules.allocate_item(self.host)
                if slot is None: raise BindingRequired('joining creature exceeds the party item slots')
                slot[:] = item
                char.items[at] = slot
            put(char, 'creature_id', ident)
            append_character(self.host, char)
            self.icons[field(char, 'order')] = ('CPIC', ident, self.s.dataset)
        char = self.s.selc()
        put(char, 'npc', (self.v(2) & 255) >> 1 | 128)
        rules.recalc_stats(char, self.s.r1[0x372])
        self.party_drawn()
    def op41(self):
        from .creation import refresh_level_up
        from .shop import member_name
        self.pc = self.next
        amount, whole = self.v(2) & 65535, self.v(1) & 255
        text = self.host.assets.text
        if whole: members, message = self.s.chars(), text('partyGainsText')
        else:
            member = self.s.selc()
            if not field(member, 'active'): return
            members, message = (member,), text('congratulationsText') + member_name(member) + text('gainsSuffix')
        if self.ready_shown is None: self.ready_shown = tuple(field(char, 'level_up_ready') for char in self.s.party)
        self.clear_text()
        self.text_color = 10
        self.out.append(message)
        self.hold(self.s.g.get('dkk.delay', 4) / 10)
        for char in members:
            if not field(char, 'active'): continue
            classes = sum(1 for index in range(8) if field(char, 'levels', index, signed=True) > 0)
            if not classes: raise BindingRequired('experience share for a creature without class levels')
            put(char, 'experience', field(char, 'experience', width=4) + amount // classes, width=4)
            refresh_level_up(char)
    def op2F(self):
        self.pc = self.next
        result = (self.v(1) & self.v(2) if self.cur == 0x2F else self.v(1) | self.v(2)) & 255
        self.cmp(0, result)
        self.write(3, result)
    op30 = op2F
    def op2D(self):
        self.pc = self.next
        address = self.a(1)
        if address == 0x2DCB: self.update_display()
        elif address == 0xC01E: self.step(); self.display['view_dirty'] = True
        elif address == 0xC018:
            if not self.is3d(): self.s.ahead = self.geo.wall(self.s, self.s.x, self.s.y, self.s.dir)
        elif address == 0x6803:
            self.display['frame'] = self.display.get('frame', 0) + 1
            self.hold(self.s.g.get('dkk.delay', 4) / 10)
        elif address == 0xB203: self.queue_sound(11 if getattr(self, 'sound_effect', 0) == 10 else 10)
    def op32(self):
        self.pc = self.next
        found = any(item[46] == (self.v(1) & 255) for char in self.s.chars() for item in char.items)
        self.flags = [int(found), int(not found), 0, 0, 0, 0]
    def op38(self):
        extended = self.s.g.get('world.extended', 0)
        self.s.g['world.extended'] = 0
        self.pc = self.next
        if self.s.g.get('47E2'):
            self.s.sel = self.s.g.get('47E7', 0)
            self.s.g['47E2'] = 0
        program = self.v(1) & 255
        if program == 0:
            mode = self.s.mode
            self.service('creation', 'run')
            if mode == 4:
                self.display.update(kind=None, blank=True)
                for key in ('clock', 'location'): self.display.pop(key, None)
                self.display['misc_info'] = self.info_line = ''
                self.party_drawn()
            if (self.s.g.get('dkk.runtime', {}).get('picture_id', 255) != 9 and
                    not self.is3d() and self.m0(0x4CF7) == 1 and not restart_requested(self.s)):
                self.interface_redraw_epoch += 1
                self.party_drawn()
                self.display['map_cursor'] = True
        elif program == 9:
            pc = self.pc; camp(self.host); self.pc = pc
            if self.m0(0x4CF7) == 1:
                self.op00()
                self.pc = (pc + 1) & 65535
        self.s.g['world.extended'] = extended
    def op39(self):
        from .shop import member_name
        extended = self.s.g.get('world.extended', 0)
        self.s.g['world.extended'] = 0
        self.s.g['A4D1'] = self.s.g['8B6D'] = 0
        self.pc = self.next
        self.clear_text()
        prompt = self.strs[1][:40] if len(self.strs) > 1 else ''
        self.s.sel = self.ask('WHO', tuple(member_name(char) for char in self.s.chars()),
                              at=self.at, prompt=prompt)
        self.party_drawn()
        self.s.g['world.extended'] = extended
    def op3A(self):
        self.pc = self.next
        self.hold(0.6)
    def op3D(self):
        self.pc = self.next
        runtime = self.s.g.setdefault('dkk.runtime', {})
        runtime['big_picture_shown'] = 0
        self.party_drawn()
        self.text_start = len(self.out)
        self.text_epoch += 1
        self.clear_box_epoch += 1
        self.clear_box_portrait = not runtime.get('demo', 0)
        self.display['blank'] = True
        if self.clear_box_portrait: self.display.pop('portrait_hidden', None)
        if self.display.get('kind') == 'BIGPIC' or not self.clear_box_portrait:
            self.display['kind'] = None
        if self.s.mode != 3:
            self.display['clock'] = self.s.r0[0xC6:0xCD]
            self.paint_location()
        else:
            self.display.pop('clock', None)
            self.display.pop('location', None)
            self.info_line = None
        self.noncombat_redraw = False
        self.box_cleared = True
    def op3B(self):
        self.pc = self.next
        slot, member = 255, max(0, len(self.s.chars()) - 1)
        for index, char in enumerate(self.s.chars()):
            book = rules.spellbook(char)
            if book is None or not field(char, 'active'): continue
            matches = [i for i, spell in enumerate(book.get('memorized')) if spell == (self.v(1) & 255)]
            if matches:
                slot, member = matches[0], index
                break
        self.write(2, slot)
        self.write(3, member)
    def op3C(self):
        self.pc = self.next
        stock = self.v(1) & 255
        stock = stock if 1 <= stock <= 8 else 1
        assets = self.host.assets
        start = assets.table('shopStockStart')[stock - 1] - 1
        count = assets.table('shopStockCount')[stock - 1]
        stock_items = assets.table('shopStockItems')
        if start + count > len(stock_items): raise BindingRequired('shop stock extends beyond the verified item table')
        templates = self.binding.records('ITEM0')[1]
        self.s.treasure_items = []
        for ident in stock_items[start:start + count]:
            raw = templates[(ident - 1) * 17:ident * 17]
            if len(raw) == 17 and raw[0] != 255:
                item = Item()
                item.data[46:] = raw
                item.data[Item.FIELDS['unidentified'][0]] &= 248
                self.s.treasure_items.insert(0, item.data)
        self.interface('shop', 'run')
    def remove_selected(self):
        s = self.s
        if s.selc() is None: return
        collection = s.party if s.sel < len(s.party) else s.monsters
        index = s.sel if collection is s.party else s.sel - len(s.party)
        self.icons.pop(field(collection.pop(index), 'order'), None)
        saved = s.g.get('47E7', 0)
        if saved > s.sel: s.g['47E7'] = saved - 1
        s.sel = max(0, s.sel - 1)
        self.set1(0x7F3E, self.m1(0x7F3E) - 1)
    def op3E(self):
        self.pc = self.next
        self.remove_selected()
        self.s.g['47E7'] = self.s.sel
        self.party_drawn()
    def op3F(self):
        from .effects import has
        self.pc = self.next
        found = has(self.s.selc(), self.v(1) & 255)
        self.flags = [int(found), int(not found), 0, 0, 0, 0]
    def op40(self):
        from . import inventory
        self.pc = self.next
        selected, target = self.s.sel, self.v(1) & 255
        try:
            for index, char in enumerate(self.s.chars()):
                for item in tuple(char.items):
                    if item[46] != target: continue
                    self.s.sel = index
                    if item[inventory.I['readied']]: inventory.toggle_ready(self.host, char, item)
                    inventory.remove_item(char, item, self.host)
                put(char, 'item_count', len(char.items))
                rules.recalc_stats(char, self.s.r1[0x372])
        finally: self.s.sel = selected
    def paint_location(self):
        from .menu import misc_info
        self.display['location'] = self.s.x, self.s.y, self.s.dir
        line = misc_info(self.host)
        if line is not None: self.info_line = line
        if self.s.mode == 4: self.display['misc_info'] = line
        elif self.s.mode != 3: self.display.pop('misc_info', None)
    def loot_screen(self, name):
        self.text_start = len(self.out)
        self.text_epoch += 1
        self.interface('combat', name, line='')
    def interface(self, unit, name, *arguments, line=None, redraw=True):
        if line is None: self.display.pop('misc_info', None)
        else: self.display['misc_info'] = line
        try: return self.service(unit, name, *arguments)
        finally:
            if redraw:
                self.party_drawn()
                self.paint_location()
    def party_drawn(self):
        self.roster_shown = self.ready_shown = self.linked_shown = self.rows_shown = None
    def keep_info_line(self):
        if self.s.mode in (3, 4) and self.info_line is not None: self.display['misc_info'] = self.info_line

    def advance_clock(self, amount, unit):
        from .camp import advance
        unit = rules._s8(unit)
        if not 0 <= unit <= 6: raise BindingRequired('clock unit outside native storage')
        advance(self.host, amount & 255, unit)


def service(game, unit, name, *arguments):
    module = 'sm.titles.dkk.' + ('world_vault' if unit == 'vault' else unit)
    try: provider = import_module(module)
    except ModuleNotFoundError as error:
        if error.name != module: raise
        raise BindingRequired('Death Knights service unverified: ' + unit + '.' + name) from None
    handler = getattr(provider, name, None)
    if handler is None: raise BindingRequired('Death Knights service unverified: ' + unit + '.' + name)
    return handler(game, *arguments)


def after_block(game):
    from .world_explore import refresh
    s, vm = game.s, game.vm
    for _ in range(256):
        vm.portrait_clear_epoch += 1
        vm.display['portrait_animation'] = False
        s.g.setdefault('dkk.runtime', {}).update(picture_name='', picture_id=255,
                                               saved_picture_name='', saved_picture_id=255)
        s.restart = 0
        s.attr = game.geo.attr(s, s.x, s.y)
        vm.set1(0x7ED5, 0)
        s.g['47E7'] = s.sel
        vm.run(vm.vec[4])
        if s.restart: continue
        vm.set0(0x4BF2, s.block)
        if ((s.prev_mode != 4 or s.mode == 4) and vm.files_loaded) or s.prev_mode == s.mode == 4:
            vm.map_view_epoch += 1
            if not s.party_dead: refresh(game)
        for vector in (0, 1):
            vm.run(vm.vec[vector])
            if s.restart: break
        if not s.restart:
            s.sel, s.prev_mode = s.g['47E7'], s.mode
            vm.party_drawn()
            return
    raise BindingRequired('Death Knights new-block transition limit')


def boot(game):
    s, vm = game.s, game.vm
    runtime = s.g.setdefault('dkk.runtime', {})
    runtime['restart_loop'] = 0
    demo = game.demo_mode = int(bool(runtime.get('demo', 0)))
    vm.files_loaded = vm.map_loaded = vm.pieces_loaded = False
    vm.noncombat_redraw = bool(s.r0[0xF2])
    s.mode, s.restart = 4 if vm.is3d() else 3, 0
    s.g['47E7'] = s.sel
    if not s.r0[0xF2]: s.dataset = 5 if demo else 1
    s.block = s.r0[0xF2] or (2 if demo else 16)
    vm.load_block(s.block)
    vm.init_vm()
    vm.run(vm.vec[4])
    if demo:
        from .creation import remove_creature
        for char in s.chars(): remove_creature(game, char, True, True)
        return
    if s.restart: after_block(game)
    else: vm.set0(0x4BF2, s.block)
    vm.resuming = False
    s.g.update({'world.extended': 0, 'world.choice': 1})


def camp(game):
    vm = game.vm
    vm.run(vm.vec[2])
    vm.text_start, vm.text_epoch = len(vm.out), vm.text_epoch + 1
    if vm.interface('camp', 'run'):
        if game.s.mode == 4 or game.s.mode == 3 and game.s.g.get('dkk.runtime', {}).get('picture_id', 255) != 9 and vm.m0(0x4CF7) == 1:
            vm.redraw_view()
            if game.s.mode == 4: vm.paint_location()
        vm.run(vm.vec[3])
    from .world_explore import refresh
    refresh(game)
    game.s.g['save.recent'] = 0


def turn(game):
    from .world_explore import turn as explore_turn
    return explore_turn(game)


def play(game, limit=100_000):
    boot(game)
    if game.s.g.get('dkk.runtime', {}).get('demo', 0): return 'DEMO'
    result = game.s.g.get('dkk.battle', {})
    if getattr(game, 'first_fight_only', True) and not result.get('active') and result.get('result') == 'won' and result.get('enemy_survivors') == 0:
        return 'FIRST_FIGHT_WON'
    game.s.g['world.extended'], game.s.g['world.choice'] = 0, 1
    while len(game.trace) < limit and not game.s.party_dead and not game.s.stop:
        turn(game)
        if restart_requested(game.s) and not game.s.party_dead and not game.s.stop: boot(game)
    if not game.s.party_dead: return 'LIMIT'
    from .creation import remove_creature
    game.s.party_dead = 0
    for char in list(game.s.party): remove_creature(game, char)
    return 'DEFEAT'


def test():
    from .menu import Game
    vm = Game(None).vm
    vm.setmem(0x4B01, 0x1234, 3)
    assert vm.getmem(0x4B01) == 0x34 and vm.getmem(0x4B02) == 0x12
    assert vm.getmem(0x4B01, 3) == 0x1234
    vm.setmem(0x4B01, 0x56)
    assert vm.getmem(0x4B01, 3) == 0x1256
