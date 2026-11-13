import hashlib
import os
from pathlib import Path
import struct
import sys
from unittest import SkipTest

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sm import sound

ORIGINAL = {2: (240, 233, '3619e7290cbdc542'), 3: (35, 35, 'a0670eb2fe383afd'), 4: (210, 210, '7f87b716874b2d46'), 5: (176, 176, '5c086292c0ff99e8'),
            6: (150, 121, '3b34578eec06bdae'), 7: (65, 65, 'e04b3a17e1578e96'), 8: (600, 600, 'bb2eaffa48aee308'), 9: (9, 3, '89e853227bdf088b'),
            10: (8, 8, 'db4cc505c9c95804'), 11: (340, 328, '1d49fd26d2a36df0'), 12: (30, 30, '35662c88dff7fb7c')}
digest = lambda rows: hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()[:16]


def synthetic():
    seg = bytearray(0x10000); data, script, quiet = 0x100, 0x1000, 0x1100
    seg[quiet:quiet + 8] = bytes([0xFF, sound.LEVEL, 0, 0, 0xFF, sound.TICKS, 0, 0])
    loop = script + 12
    body = bytes([0xFF, sound.LEVEL, 3, 0, 0xFF, sound.PITCH]) + struct.pack('<H', 1000) + bytes([0xFF, 0x26, 3, 0,
                  0xFF, sound.SLIDE, 10, 0, 0xFF, sound.TICKS, 2, 0, 0xFE, 0x26]) + struct.pack('<H', loop) + seg[quiet:quiet + 8]
    seg[script:script + len(body)] = body
    struct.pack_into('<4H', seg, data + sound.SOUNDS + 8, script, quiet, quiet, quiet)
    real = sound._segment; sound._segment = lambda folder: (bytes(seg), data)
    try:
        got = sound.ticks('none', 2)
        assert got == [(0x10000, 3), (1010, 3), (1020, 3), (1030, 3), (1040, 3), (1050, 3)], got
        played = sound.cue('none', 2)
        assert len(played) == 6 and played[1] == (round(sound.PIT_HZ / 1010, 2), round(sound.TICK_MS, 3)), played
        assert sound.cue('none', 0) == sound.cue('none', 1) == sound.cue('none', 13) == sound.cue('none', 255) == []
    finally: sound._segment = real


def check(folder):
    for command, (count, runs, sha) in ORIGINAL.items():
        ticks, cue = sound.ticks(folder, command), sound.cue(folder, command)
        assert (len(ticks), len(cue), digest(ticks)) == (count, runs, sha), (command, len(ticks), len(cue), digest(ticks))
        assert abs(sum(ms for _, ms in cue) - count * sound.TICK_MS) < 0.01 * runs and all(hz >= 0 and ms > 0 for hz, ms in cue), command
    assert [sound.cue(folder, c) for c in (0, 1, 13, 14, 15, 255)] == [[]] * 6


def test(folder=None):
    synthetic()
    from sm.titles.ssb import intake
    folders = [f for f in (folder or os.environ.get('SM_COK'), intake.configured()) if f and Path(f).is_dir()]
    if not folders: raise SkipTest('no Champions or Silver Blades folder configured')
    for f in folders: check(f)
    return 'sound: 11 cues in %d copies, %d ticks each equal to the original' % (len(folders), sum(c for c, _, _ in ORIGINAL.values()))

if __name__ == '__main__':
    print(test(sys.argv[1] if len(sys.argv) > 1 else None))
