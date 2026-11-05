"""GU-124 presentation only: EGA indices 0..15, optional DQK chrome, PNG art.

The indexed plane stays lossless. Combat mods use a separate display-resolution
overlay; non-combat pictures can use the packet's optional RGB plane.
"""
from functools import lru_cache
import base64
import json
from pathlib import Path
import re
import struct
import zlib

from sm.ui.png import decode, encode, edge_alpha
from sm.titles.ssb import art
from . import screen


def rgb(pixel, palette):
    return ((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255) if pixel > 255 else palette[pixel]


def revision_id(revision):
    return zlib.crc32(json.dumps(revision, separators=(',', ':')).encode())


def blend(source, dest, palette):
    alpha = source >> 24
    if not alpha: return dest
    if alpha == 255: return source
    a, b = rgb(source, palette), rgb(dest, palette)
    r, g, blue = ((x*alpha+y*(255-alpha)+127)//255 for x, y in zip(a, b))
    return 0xff000000 | r << 16 | g << 8 | blue


def layer(source, dest, palette):
    """Compose icon layers while retaining alpha for the eventual terrain blit."""
    if not dest: return source
    if dest <= 255: return blend(source, dest, palette)
    a, b = source >> 24, dest >> 24
    denominator = a*255 + b*(255-a)
    if not denominator: return 0
    red, green, blue = ((x*a*255+y*b*(255-a)+denominator//2)//denominator
                        for x, y in zip(rgb(source, palette), rgb(dest, palette)))
    return ((denominator+127)//255) << 24 | red << 16 | green << 8 | blue


class ModPixels(tuple):
    """Marker: these pixels have already bypassed the record's EGA colour map."""


@lru_cache(maxsize=32)
def read_png(path, modified, size):
    if size > 16*1024*1024: raise ValueError('Mod PNG exceeds 16 MiB')
    return decode(path.read_bytes())


@lru_cache(maxsize=96)
def image_uri(rows):
    return 'data:image/png;base64,' + base64.b64encode(encode(rows)).decode('ascii')


class Mods:
    def __init__(self, folder):
        self.entries, self.icons, self.cache = {}, {}, {}
        if not folder: return
        root = Path(folder).expanduser().resolve()
        try:
            path = root / 'mods.json'
            if path.stat().st_size > 1024*1024: raise ValueError('Mods index exceeds 1 MiB')
            entries = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(entries, list) or len(entries) > 4096: raise ValueError('Expected a list of at most 4096 mods')
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError('Invalid mod entry')
                if 'transparent' in entry:
                    raise ValueError('Global colour keys are unsupported; use RGBA alpha or the temporary edge_background option')
                if entry.get('kind') == 'icon':
                    if set(entry) - {'kind', 'slot', 'head', 'body', 'png', 'edge_background', 'edge_tolerance'}:
                        raise ValueError('Invalid icon entry')
                    if 'slot' in entry and not set(entry) & {'head', 'body'}:
                        slot = entry['slot']
                        if type(slot) is not int or not 0 <= slot < 6: raise ValueError('Party slot must be 0..5')
                        key = ('slot', slot)
                    elif 'slot' not in entry and all(k in entry for k in ('head', 'body')):
                        if any(type(entry[k]) is not int or not 0 <= entry[k] < 64 for k in ('head', 'body')):
                            raise ValueError('Use base CHEAD/CBODY ids 0..63')
                        key = ('pair', entry['head'], entry['body'])
                    else: raise ValueError('Icon needs either a party slot or a head/body pair')
                    target = self.icons
                else:
                    if set(entry) - {'file', 'id', 'frame', 'png', 'edge_background', 'edge_tolerance'}: raise ValueError('Invalid mod entry')
                    name = entry['file'].upper().removesuffix('.DAX')
                    ident, frame = entry['id'], entry.get('frame', 0)
                    if not re.fullmatch('[A-Z0-9]+', name) or type(ident) is not int or not 0 <= ident <= 255:
                        raise ValueError('Use a container basename and record id 0..255')
                    if name in ('CHEAD', 'CBODY'): raise ValueError('Use one full-figure kind: icon entry for a head/body pair')
                    if type(frame) is not int or not 0 <= frame <= 255: raise ValueError('Invalid mod frame')
                    key, target = (name, ident, frame), self.entries
                if key in target: raise ValueError('Duplicate mod key')
                png = Path(entry['png']).expanduser()
                if png.suffix.lower() != '.png': raise ValueError('Mod images must be PNGs')
                png = (root / png).resolve()
                edge = entry.get('edge_background')
                if edge is not None and (not isinstance(edge, str) or not re.fullmatch('#[0-9a-fA-F]{6}', edge)):
                    raise ValueError('Edge background must be #RRGGBB')
                tolerance = entry.get('edge_tolerance', 0)
                if type(tolerance) is not int or not 0 <= tolerance <= 32 or tolerance and edge is None:
                    raise ValueError('Edge tolerance must be 0..32 with an edge background')
                target[key] = png, int(edge[1:], 16) if edge else None, tolerance
        except (OSError, KeyError, TypeError, AttributeError, ValueError) as error:
            raise ValueError('Cannot load Mods folder: ' + str(error)) from error

    def read(self, entry):
        if entry not in self.cache:
            path, edge, tolerance = entry
            stat = path.stat()
            rows = read_png(path, stat.st_mtime_ns, stat.st_size)
            self.cache[entry] = edge_alpha(rows, edge, tolerance) if edge is not None else rows
        return self.cache[entry]

    def validate(self):
        for entry in (*self.entries.values(), *self.icons.values()): self.read(entry)

    def icon(self, controller, game, character, pose):
        b = character.b
        slot = next((i for i, c in enumerate(game.s.party) if c is character), None)
        body = screen.plus.body(character, controller.manual_bodies) if getattr(controller, 'equipment_icon', False) else b[0x154]
        source = getattr(game.vm, 'icons', {}).get(b[0x155])
        entry = self.icons.get(('slot', slot))
        if entry is None and source is None: entry = self.icons.get(('pair', b[0x153], body))
        if entry is None and source is not None:
            family, ident, dataset = source
            ident = (ident+pose*128)&255
            entry = self.entries.get((art.source(family, ident, dataset), ident, 0))
        if entry is None: return None
        key = ('sprite', entry)
        if key not in self.cache:
            rows = self.read(entry)
            occupied = [(x, y) for y, row in enumerate(rows) for x, p in enumerate(row) if p >> 24]
            if not occupied: raise ValueError('Icon PNG is entirely transparent')
            left, right = min(x for x, y in occupied), max(x for x, y in occupied)+1
            top, bottom = min(y for x, y in occupied), max(y for x, y in occupied)+1
            self.cache[key] = image_uri(tuple(row[left:right] for row in rows[top:bottom]))
        return self.cache[key]

    def picture(self, name, ident, dataset, width, height, frame=0):
        key = art.source(name, ident, dataset), ident, frame
        if key not in self.entries: return None
        cache_key = key, width, height
        if cache_key not in self.cache:
            rows = self.read(self.entries[key])
            h, w = len(rows), len(rows[0])
            self.cache[cache_key] = ModPixels(tuple(
                p
                for x in range(width) for p in (rows[min(h-1, (2*y+1)*h//(2*height))][min(w-1, (2*x+1)*w//(2*width))],))
                for y in range(height))
        return self.cache[cache_key]


def configured_dqk():
    """Explicit player configuration only; never the developer's default root."""
    from sm.ui.vga_skin import configured
    return configured()


@lru_cache(maxsize=4)
def skin(root):
    from sm.ui.vga_skin import Skin
    assets = Skin(root)
    palette = list(screen.PALETTE)
    mapping = []
    for colour in assets.palette:
        if colour not in palette: palette.append(colour)
        mapping.append(palette.index(colour))
    if len(palette) > 256: raise ValueError('Dark Queen frame palette exceeds VGA capacity')
    return assets, tuple(palette + [(0, 0, 0)]*(256-len(palette))), tuple(mapping)


class Assets:
    def __init__(self, original, settings):
        self.original = original
        self.warning = ''
        try: self.mods = Mods(settings.get('mods_folder', ''))
        except ValueError as error: self.mods, self.warning = Mods(''), str(error)
        self.native, self.mapping = None, None
        self.palette = screen.PALETTE + ((0, 0, 0),)*240
        if settings.get('vga_frame', 'dqk') == 'dqk' and (root := configured_dqk()):
            try: self.native, self.palette, self.mapping = skin(root)
            except (OSError, ValueError) as error: self.warning = str(error)

    def __getattr__(self, name): return getattr(self.original, name)

    def glyph(self, ch):
        if self.native is None: return self.original.glyph(ch)
        code = ch.encode('cp437', errors='replace')[0] & 127
        return tuple(self.native.font[(code-32)*12+y] if 32 <= code <= 127 else 0 for y in (0, 1, 3, 4, 6, 8, 9, 10))

    def border(self, symbol):
        if self.native is None: return self.original.border(symbol)
        x, y = {0x134: (0, 8), 0x135: (0, 48), 0x136: (0, 176), 0x137: (160, 0),
                0x138: (16, 24), 0x139: (16, 48), 0x13a: (16, 104), 0x13b: (48, 16)}[symbol]
        rows = self.native.rows('explore')
        return tuple(bytes(self.mapping[p] for p in row[x:x+8]) for row in rows[y:y+8])

    def chrome(self, frame, mode):
        if self.native is None: return False
        rows = self.native.rows(mode)
        # Keep SSB's content rectangles and menu coordinates. Only chrome is
        # taken from DQK; no DQK scenery, roster, compass or moon widgets.
        areas = [(0, 0, 320, 8), (0, 8, 8, 184), (312, 8, 320, 184)]
        if mode == 'combat': areas += [(176, 8, 184, 176), (0, 176, 320, 184)]
        else: areas += [(0, 184, 320, 192)]
        if mode not in ('party', 'combat'): areas += [(0, 128, 320, 136)]
        if mode == 'explore': areas += [(128, 8, 136, 128), (16, 16, 120, 24), (16, 112, 120, 120), (16, 24, 24, 112), (112, 24, 120, 112)]
        for x0, y0, x1, y1 in areas:
            for y in range(y0, y1): frame.rows[y][x0:x1] = [self.mapping[p] for p in rows[y][x0:x1]]
        if mode == 'party': frame.rect(8, 8, 304, 176, 0)
        return True


def assets_for(controller, original):
    settings = getattr(controller, 'plus_settings', None)
    options = settings.options if settings else {}
    if getattr(controller, '_look_override', options.get('look', 'original')) != 'vga': return original.original if isinstance(original, Assets) else original
    if isinstance(original, Assets): return original
    key = tuple(options.items()), configured_dqk()
    if getattr(controller, '_vga_key', None) != key:
        controller._vga_assets, controller._vga_key = Assets(original, options), key
    return controller._vga_assets


class Frame(screen.Frame):
    def __init__(self, assets):
        self.rows = [[0]*320 for _ in range(200)]
        self.assets, self.palette = assets, assets.palette
        self.revision = 0
        self.overlay = None
        self.record_overlay = True

    def begin_icons(self):
        mods = self.assets.mods
        if not mods.icons and not any(k[0].startswith(('CPIC', 'ICON', 'COMSPR')) for k in mods.entries): return
        rows = tuple(tuple(0xff000000 | r << 16 | g << 8 | b for p in row[8:176]
                           for r, g, b in (rgb(p, self.palette),)) for row in self.rows[8:176])
        self.overlay = dict(clip=[8, 8, 168, 168], draws=[dict(image=image_uri(rows), rect=[8, 8, 168, 168])], icons=[])

    def draw_icon(self, controller, game, character, index, facing, pose, x, y, pixels, palette, clip):
        replacement = None
        if self.overlay is not None:
            try: replacement = self.assets.mods.icon(controller, game, character, pose)
            except (OSError, ValueError) as error:
                self.assets.warning = 'Mod image unavailable; original art is shown: ' + str(error)
        self.record_overlay = replacement is None
        self.blit(x, y, pixels, transparent=0, colours=palette, clip=clip)
        self.record_overlay = True
        if replacement is not None:
            # Full figure: feet remain on the native tile baseline; head gets
            # ten extra native pixels, rendered only at browser display scale.
            width, height = len(pixels[0]), len(pixels)
            rect = [x, y-10, width, height+10]
            self.overlay['draws'].append(dict(image=replacement, rect=rect, fit=True, mirror=facing > 3))
            self.overlay['icons'].append(dict(index=index, rect=rect, facing=facing, pose=pose))

    def rect(self, x, y, w, h, colour):
        super().rect(x, y, w, h, colour)
        if self.overlay is not None and x < 176 and y < 176 and x+w > 8 and y+h > 8:
            self.overlay['draws'].append(dict(rect=[x, y, w, h], fill='#%02x%02x%02x' % rgb(colour, self.palette)))

    def blit(self, x, y, pixels, transparent=None, clip=None, colours=None):
        x0, y0, x1, y1 = clip or (0, 0, 320, 200)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(320, x1), min(200, y1)
        mod = isinstance(pixels, ModPixels)
        if self.overlay is not None and self.record_overlay and x < 176 and y < 176 and x+len(pixels[0]) > 8 and y+len(pixels) > 8:
            rows = tuple(tuple(0 if p is None or p == transparent or mod and p == 0 else
                         p if p > 255 else 0xff000000 | r << 16 | g << 8 | b
                         for p in row for r, g, b in (rgb(colours[p] if p is not None and p <= 255 and colours is not None and not mod else p or 0, self.palette),))
                         for row in pixels)
            self.overlay['draws'].append(dict(image=image_uri(rows), rect=[x, y, len(pixels[0]), len(pixels)], clip=[x0, y0, x1-x0, y1-y0]))
        for yy in range(max(y, y0), min(y+len(pixels), y1)):
            row = pixels[yy-y]
            for xx in range(max(x, x0), min(x+len(row), x1)):
                p = row[xx-x]
                if p is None or p == transparent or mod and p == 0: continue
                if p > 255: p = blend(p, self.rows[yy][xx], self.palette)
                elif colours is not None and not mod: p = colours[p]
                self.rows[yy][xx] = p

    def mod(self, x, y, name, ident, dataset, pixels, *, frame=0, **kwargs):
        replacement = replacement_for(self.assets, name, ident, dataset, len(pixels[0]), len(pixels), frame)
        self.blit(x, y, replacement if replacement is not None else pixels, **kwargs)

    def packet(self, revision):
        values = [p for row in self.rows for p in row]
        full_colour = any(p > 255 for p in values)
        body = (struct.pack('<4sHHHHI', b'SMV1', 320, 200, 256, int(full_colour), revision_id(revision)) +
                bytes(c for colour in self.palette for c in colour) + bytes(p if p <= 255 else 0 for p in values))
        if full_colour: body += bytes(c for p in values for c in rgb(p, self.palette))
        return body

    def save(self, path=screen.LOCAL/'ui_townhall.png', scale=screen.SCALE):
        path = Path(path).resolve()
        if not path.is_relative_to(screen.LOCAL.resolve()): raise ValueError('screenshots must stay under local/')
        raw = b''.join((b'\0' + b''.join(bytes(rgb(p, self.palette))*scale for p in row))*scale for row in self.rows)
        def chunk(kind, data): return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 320*scale, 200*scale, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b''))
        return path


def replacement_for(assets, *args):
    try: return assets.mods.picture(*args)
    except (OSError, ValueError) as error:
        assets.warning = 'Mod image unavailable; original art is shown: ' + str(error)
        return None


def capture(controller, renderer=None):
    """Native retained backgrounds keep both looks, including their original bytes."""
    from copy import copy
    renderer = renderer or screen.render
    if not getattr(controller, 'plus_settings', None): return renderer(controller, screen.Assets())
    original, enhanced = copy(controller), copy(controller)
    original._look_override, enhanced._look_override = 'original', 'vga'
    original._vga_key = enhanced._vga_key = None
    a, b = renderer(original, screen.Assets()), renderer(enhanced, screen.Assets())
    a.vga_variant, b.original_variant = b, a
    return a


def background_rows(background, assets):
    if isinstance(assets, Assets): return getattr(background, 'vga_variant', background).rows
    return getattr(background, 'original_variant', background).rows


class Footer(tuple):
    """Native footer bytes with an optional presentation-only VGA companion."""


def capture_footer(controller, clear_top=False):
    captured = capture(controller, screen.render_player)
    original = tuple(bytes(row) for row in captured.rows[184:])
    if clear_top: original = (bytes(320),)*8 + original[8:]
    if not hasattr(captured, 'vga_variant'): return original
    footer = Footer(original)
    footer.vga = tuple(tuple(row) for row in captured.vga_variant.rows[184:])
    if clear_top: footer.vga = (bytes(320),)*8 + footer.vga[8:]
    return footer


def footer_rows(footer, assets):
    return getattr(footer, 'vga', footer) if isinstance(assets, Assets) else footer
