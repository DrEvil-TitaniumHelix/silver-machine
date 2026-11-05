"""Six-bit script text shared by the Pascal and C engine families."""


def packed_text(data):
    # Six-bit codes are MSB-first; native strcat ignores each zero code.
    word, remaining, out = 0, 0, []
    for byte in data:
        word = (word << 8) | byte
        remaining += 8
        while remaining >= 6:
            remaining -= 6
            code = (word >> remaining) & 63
            if not code:
                continue
            out.append(chr(code + 64 if code < 32 else code))
    return ''.join(out)


def test():
    # All code values, dropped zeroes and truncated groups; no original text.
    for code in range(64):
        expected = '' if code == 0 else chr(code + 64 if code < 32 else code)
        assert packed_text(bytes([code << 2])) == expected
    assert packed_text(b'') == packed_text(b'\0\0\0') == ''
    assert packed_text(bytes.fromhex('0420c4')) == 'ABCD'
    assert packed_text(bytes.fromhex('0420')) == 'AB'
    assert packed_text(bytes.fromhex('040003')) == 'AC'
