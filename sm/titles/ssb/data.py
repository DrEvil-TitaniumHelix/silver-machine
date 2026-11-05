"""SSB content selection, resident tables and corpus checks; data stays external."""
import functools
from sm import dax, ecl
from sm.dax import unpack_exepack
from sm.ecl import trace
from .intake import ContentFolder, file_path, resident_path
SECRET = ContentFolder()


@functools.lru_cache(maxsize=None)
def stexe(d=SECRET):
    """Edition's resident data: EXEPACK-unpacked in memory (method = survey/tools/unexepack.py, LAYOUT.md 1), DS 0DE2 -> load-module
    offset 0DE20h. Tables the recalcs read (ENGINE_READ_w6 ov27): THAC0 4C0C, class masks 4C92, saves 5592, thief 4CAD/4D3D/4D48, caps 4CA9,
    spell table 449D, slot tables 50A1/52D2/538D/5448."""
    return unpack_exepack(resident_path(d).read_bytes())[0xDE20:]


@functools.lru_cache(maxsize=None)
def items_table(d=SECRET):
    """The ITEMS file block the game keeps at DS:7524: Seek(2) + BlockRead(810h) (ENGINE_READ_w5 ov13 StartupInit); the file holds 2 + 800h B = 128 item types x 16 B;
    columns used by the recalcs: +0 slot/class, +1 hands, +6 bonus class, +9/+A damage dice, +B damage bonus, +D class mask, +E weapon flags."""
    return open(file_path(d, 'ITEMS'), 'rb').read()[2:2 + 0x810]


def wrapped_text(text, width=38):
    """0540:0575..0719: wrap words including their trailing separator, shared by script waits and rendering."""
    bits = stexe()[0xB32:0xB36]
    punctuation = {chr(32+i) for i in range(32) if bits[i//8] & (1 << (i%8))}
    lines = []
    for paragraph in text.rstrip().splitlines():
        row = ''; start = 0
        while start < len(paragraph):
            stop = start
            while stop < len(paragraph)-1 and paragraph[stop] in punctuation: stop += 1
            while stop < len(paragraph)-1 and paragraph[stop] not in punctuation and paragraph[stop] != ' ': stop += 1
            if paragraph[stop] != ' ':
                while stop + 1 < len(paragraph) and paragraph[stop+1] in punctuation: stop += 1
            token = paragraph[start:stop+1]
            if len(row) + len(token) > width:
                lines.append(row.rstrip()); row = ''; token = token.lstrip(' ')
            row += token; start = stop+1
        lines.append(row.rstrip())
    return lines


def records():
    from sm import dax
    return {(f, r): b[2:] for f in (1, 2, 3) for r, b in dax.load('ECL%d' % f, SECRET).items()}


def test_dax():
    dax.test_duplicate_id()
    ds = stexe(); assert len(ds) == 79824 - 0xDE20 and ds[0x4C0C:0x4C12] == bytes.fromhex('28282828 2a2a'.replace(' ', '')), 'DS tables'
    assert ds[0x4BFE:0x4C0C] == bytes.fromhex('0a000a00060018001e000c006400'), 'clock limits (ENGINE_READ_w6 ov22)'
    assert len(items_table()) == 0x800
    e = {f: dax.load('ECL%d' % f, SECRET) for f in (1, 2, 3)}
    assert sum(len(r) for x in e.values() for r in x.values()) == 137962 and sum(map(len, e.values())) == 22, 'ECL_DELTA 5'
    assert all(r[:2] == b'\x88\x13' for x in e.values() for r in x.values())
    assert dax.rle(bytes([1, 7, 8, 0xFE, 9])) == bytes([7, 8, 9, 9])


def test_ecl():
    n, used, bad = 0, set(), 0
    for (f, r), code in records().items():
        vec, insns = trace(code)
        assert vec[4] == 0x8014, (f, r)
        n += len(insns); used |= {op for op, ops, _ in insns.values() if ops is not None}
        bad += sum(ops is None for _, ops, _ in insns.values())
    assert (n, len(used), bad) == (15322, 59, 0), ('V2', n, len(used), bad)


def test():
    test_dax()
    test_ecl()
