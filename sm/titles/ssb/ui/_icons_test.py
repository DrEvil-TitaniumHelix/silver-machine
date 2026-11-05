"""Per-character BuildCombatIcon checks: ENGINE_READ_w6 ov20:0937..0C24."""
from sm.titles.ssb import data as ssb_data
from types import SimpleNamespace

from sm import dax; from sm.titles.ssb import save
from sm.titles.ssb.state import Char
from sm.titles.ssb.ui.screen import icon
from sm.titles.ssb.ui.screen import Assets, Frame, LOCAL


def expected(character, pose):
    """ov20:0937/0A91/0B1D oracle: OR packed source bytes, remap then unpack."""
    b, ds = character.b, ssb_data.stexe()
    offset = (64 if ds[0x9D7 + b[0x156]] == ord('T') else 0) + 128 * pose
    head = dax.load('CHEAD', d=ssb_data.SECRET)[(b[0x153] + offset) & 255]
    body = dax.load('CBODY', d=ssb_data.SECRET)[(b[0x154] + offset) & 255]
    merged = bytearray(body[17:])
    for i, byte in enumerate(head[17:]):
        merged[i] |= byte
    width = int.from_bytes(body[2:4], 'little') * 8
    pixels = bytes(v for byte in merged for v in (byte >> 4, byte & 15))
    remap = dict(zip(ds[0x19A4:0x19B4], ds[0x19B4:0x19C4]))
    colours = dict((i, i) for i in range(16))
    for i, source in enumerate(ds[0x4CB0:0x4CB6], 0x157):
        colours[source], colours[source + 8] = b[i] & 15, b[i] >> 4
    # Background 5 distinguishes transparent pixels from opaque recoloured black.
    return tuple(bytes(5 if v == 0 else colours[remap[v]] for v in pixels[y:y + width])
                 for y in range(0, len(pixels), width))


def test(screenshot=False):
    """UI2 follow-up: six record-specific icons, both poses, every colour pair and mirror."""
    game = SimpleNamespace(vm=SimpleNamespace(icons={}))
    party = [Char(bytes(c)) for c in save.load()['party']]
    sheet, assets, different = Frame(), Assets(), set()
    for i, c in enumerate(party):
        name = bytes(c.b[1:1 + c.b[0]]).decode('latin1')
        sheet.text(1, 1 + i * 4, name, assets, 15, 15)
        for pose in (0, 1):
            for facing in (0, 4):
                pixels, palette = icon(game, c, facing, pose)
                frame = Frame()
                frame.rect(0, 0, 320, 200, 5)
                frame.blit(0, 0, pixels, transparent=0, colours=palette)
                want = expected(c, pose)
                if facing > 3:
                    want = tuple(row[::-1] for row in want)
                assert tuple(bytes(row[:len(want[0])]) for row in frame.rows[:len(want)]) == want
            pixels, palette = icon(game, c, 0, pose)
            sheet.blit(144 + pose * 48, 8 + i * 32, pixels, transparent=0, colours=palette)
        different.add(expected(c, 0))
    assert len(different) == len(party) == 6, 'starter records collapsed to a shared icon'
    original = expected(party[0], 0)
    for part in range(6):
        c = Char(party[0].b)
        c.b[0x157 + part] = 0x50
        pixels, palette = icon(game, c)
        frame = Frame()
        frame.rect(0, 0, 320, 200, 5)
        frame.blit(0, 0, pixels, transparent=0, colours=palette)
        want = expected(c, 0)
        assert tuple(bytes(row[:len(want[0])]) for row in frame.rows[:len(want)]) == want
        assert expected(party[0], 0) == original, 'one member recoloured another'
    if screenshot:
        sheet.save(LOCAL / 'ui_party_icons.png')
    print('UI icons: six distinct original compositions, both poses, EGA masks/colours/mirrors: PASS')
