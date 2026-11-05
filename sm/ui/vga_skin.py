"""Read just the player's VGA frame and font, without loading a title engine."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .hlib import Library
from . import vga_tile as tile


def config_path():
    base = os.environ.get('SM_CONFIG_HOME')
    if not base:
        parent = (os.environ.get('APPDATA') or Path.home()/'AppData/Roaming') if os.name == 'nt' else (
            os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
        base = Path(parent)/'runtime-data'
    return Path(base).expanduser()/'dqk-intake.json'


def configured():
    if root := os.environ.get('DQK_ROOT', '').strip(): return root
    try:
        value = json.loads(config_path().read_text(encoding='utf-8'))
        root = value.get('folder') if isinstance(value, dict) else None
        return root if isinstance(root, str) and root.strip() else None
    except (OSError, ValueError): return None


def remember(folder):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(folder=folder), stream)
            stream.write('\n')
        temporary.replace(path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


# Executable fingerprints label the edition only; Skin.load is the frame check.
EDITIONS = {
    (449664, '3b41fb06a045568b0c35098a104499d489d8a5c0ef0dd48a039387ba2393ba58'): "Collector's CD",
    (449664, '6b0a9ac5c873997087f1f3f626334a71092fe7c8d1e92ce7f72869a59931f837'): 'GOG',
}


class Skin:
    def __init__(self, root):
        try: self.load(Path(root).expanduser())
        except (KeyError, IndexError, AttributeError) as error:
            raise ValueError('The configured copy lacks the required Dark Queen frame records') from error
        self.edition = None
        try:
            exe = Path(root).expanduser()/'DQK.EXE'
            if exe.stat().st_size == 449664:
                self.edition = EDITIONS.get((449664, hashlib.sha256(exe.read_bytes()).hexdigest()))
        except OSError: pass

    def load(self, root):
        self.font = (root/'DISK1/GAME.FON').read_bytes()
        if len(self.font) != 96*12: raise ValueError('Dark Queen GAME.FON must contain 96 twelve-row glyphs')
        self.frame = Library((root/'DISK3/FRAME.TLB').read_bytes())
        always = Library((root/'DISK1/ALWAYS.TLB').read_bytes())
        palette = [(0, 0, 0)]*256
        for library in (always, self.frame):
            colours = tile.palette(library.entries[0].data)
            palette[colours.first:colours.first+len(colours.rgb)] = colours.rgb
        self.palette = tuple(tuple((c >> 2)*255//63 for c in rgb) for rgb in palette)
        for leaf in (1, 2, 3, 4, 5, 6, 7, 12): self.picture(leaf)

    @lru_cache(maxsize=32)
    def picture(self, leaf):
        return tile.decode(self.frame.entries[leaf].data, lambda i: self.frame.entries[i].data)

    @lru_cache(maxsize=4)
    def rows(self, mode):
        canvas = bytearray([8])*(320*200)
        for leaf in (1, 2, 3, 4): self.picture(leaf).draw(canvas, 320, 200)
        if mode == 'combat':
            for leaf in (5, 6): self.picture(leaf).draw(canvas, 320, 200)
        elif mode != 'party': self.picture(7).draw(canvas, 320, 200, y=128)
        if mode == 'explore': self.picture(12).draw(canvas, 320, 200)
        return tuple(bytes(canvas[y*320:(y+1)*320]) for y in range(200))
