import struct, functools
from sm.files import file_path


def rle(src):
    out, i = bytearray(), 0
    while i < len(src):
        c = src[i]
        if c < 0x7F: out += src[i+1:i+2+c]; i += c + 2
        elif c > 0x80: out += src[i+1:i+2] * (256 - c); i += 2
        else: raise ValueError('RLE control %02X at %d' % (c, i))
    return bytes(out)


@functools.lru_cache(maxsize=None)
def load(name, d):
    b = open(file_path(d, name + '.DAX'), 'rb').read()
    n, = struct.unpack_from('<H', b); base, out = 2 + n, {}
    for k in range(n // 9):
        rid, off, raw, comp = struct.unpack_from('<BIHH', b, 2 + 9 * k)
        if rid in out: continue
        r = rle(b[base + off: base + off + comp])
        if len(r) != raw: raise ValueError('%s/%d raw %d != %d' % (name, rid, len(r), raw))
        out[rid] = r
    return out


def unpack_exepack(raw):
    cblp, cp, _, hdr = struct.unpack_from('<4H', raw, 2); cs = struct.unpack_from('<H', raw, 0x16)[0]
    lm = raw[hdr * 16:((cp - 1) * 512 + cblp) if cblp else cp * 512]; eh = cs * 16
    dest = struct.unpack_from('<H', lm, eh + 0xC)[0] * 16
    skip = struct.unpack_from('<H', lm, eh + 0xE)[0] if lm[eh + 16:eh + 18] == b'RB' else 1
    end = cs * 16 - (skip - 1) * 16
    buf = bytearray(max(dest, end)); buf[:end] = lm[:end]
    s = end - 1
    while buf[s] == 0xFF and end - s <= 16: s -= 1
    dst = dest
    while True:
        cmd, n = buf[s], buf[s - 1] << 8 | buf[s - 2]; s -= 3
        if cmd & 0xFE == 0xB0: buf[dst - n:dst] = bytes([buf[s]]) * n; s -= 1
        elif cmd & 0xFE == 0xB2: buf[dst - n:dst] = buf[s - n + 1:s + 1]; s -= n
        else: raise ValueError('EXEPACK command %02X' % cmd)
        dst -= n
        if cmd & 1: break
    return bytes(buf[:dest])


def test_duplicate_id():
    from unittest.mock import mock_open, patch
    header = struct.pack('<H', 27) + b''.join(struct.pack('<BIHH', rid, offset, 1, 2) for rid, offset in ((7, 0), (7, 2), (8, 4)))
    for duplicate in (b'\x00B', b'\x7fB'):
        with patch('builtins.open', mock_open(read_data=header + b'\x00A' + duplicate + b'\x00C')):
            assert load.__wrapped__('SYNTHETIC', '.') == {7: b'A', 8: b'C'}


def test():
    test_duplicate_id()
    assert rle(bytes([1, 7, 8, 0xFE, 9])) == bytes([7, 8, 9, 9])
