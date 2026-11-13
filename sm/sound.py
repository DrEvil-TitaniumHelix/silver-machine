from functools import lru_cache
from pathlib import Path
import struct

from sm.dax import unpack_exepack

PIT_HZ = 1193182
TICK_DIVISOR = 0x13B1
TICK_MS = TICK_DIVISOR * 1000 / PIT_HZ
CUES = range(2, 13)
NOTES, VOICES, SOUNDS, VOICE = 0x1D6, 0x56, 0x388, 48
TICKS, SCRIPT, PITCH, SLIDE, DIVISOR, LEVEL, LEVEL_STEP, TEMPO, TRANSPOSE, GATE = 0, 2, 4, 6, 8, 0xA, 0xC, 0xE, 0x12, 0x14
ENVELOPE, ENV_INDEX, ENV_TICKS, WAVE, PHASE, PHASE_STEP, DEPTH, WAVE_LENGTH = 0x16, 0x18, 0x1A, 0x1C, 0x1E, 0x20, 0x22, 0x24
CLEARED = (4, 6, 8, 0xA, 0xC, 0x10, 0x12, 0x16, 0x18, 0x1A, 0x1C, 0x1E, 0x20, 0x22, 0x24)


def _exe(folder):
    for p in Path(folder).iterdir():
        if p.name.upper() in ('START.EXE', 'ST.EXE'): return p
    raise FileNotFoundError('START.EXE not in %s' % folder)


@lru_cache(maxsize=4)
def _segment(folder):
    image = unpack_exepack(_exe(folder).read_bytes())
    want = [PIT_HZ / (32.7032 * 2 ** (n / 12)) for n in range(12)]
    for at in range(NOTES, len(image) - 24):
        got = struct.unpack_from('<12H', image, at)
        if sum(abs(a - b) > 3 for a, b in zip(got, want)) <= 1 and all(abs(a - b) < 80 for a, b in zip(got, want)): break
    else: raise ValueError('sound driver not found (unsupported edition)')
    for data in range((at - NOTES) % 16, 0x800, 16):
        base = at - NOTES - data
        if base < 0: break
        seg = image[base:base + 0x10000].ljust(0x10000, bytes(1))
        starts = struct.unpack_from('<%dH' % (4 * 12), seg, data + SOUNDS)
        if bytes([0xBE]) + struct.pack('<H', data + NOTES) in seg[data + SOUNDS:] and all(seg[p] >= 0xFA for p in starts): return seg, data
    raise ValueError('sound driver layout differs (unsupported edition)')


def ticks(game_folder, command, limit=60000):
    if command not in CUES: return []
    seg, data = _segment(str(game_folder)); m = bytearray(seg)
    r = lambda a: m[a & 0xFFFF] | m[a + 1 & 0xFFFF] << 8
    def w(a, v): m[a & 0xFFFF] = v & 0xFF; m[a + 1 & 0xFFFF] = v >> 8 & 0xFF
    s16 = lambda v: v - 0x10000 if v & 0x8000 else v
    voices = [data + VOICES + VOICE * v for v in range(4)]
    for v, si in enumerate(voices):
        start = r(data + SOUNDS + 8 * (command - 1) + 2 * v)
        if start: m[si:si + VOICE] = bytes(VOICE); w(si + SCRIPT, start); w(si + TICKS, 1)
    call_return = [0]

    def clear(si):
        for f in CLEARED: w(si + f, 0)

    def run(si):
        di, cur = r(si + SCRIPT), si
        if not di: return
        for _ in range(limit):
            b = m[di]; di += 1
            if b == 0xFF:
                w(si + m[di], r(di + 1)); field = m[di]; di += 3
                if field == TICKS: break
            elif b == 0xFE:
                a, to = si + m[di], r(di + 1); di += 3; n = r(a)
                if n: w(a, n - 1)
                if n != 1: di = to
            elif b == 0xFD: si = voices[0] + r(di); di += 2; clear(si)
            elif b == 0xFC: call_return[0] = di + 2; di = r(di)
            elif b == 0xFB: di = call_return[0]
            elif b == 0xFA: clear(si)
            else:
                tempo = m[si + TEMPO]; length = tempo * m[di + 1] & 0xFFFF if tempo > 1 else m[di + 1]
                w(si + TICKS, length); tone = m[di] & 0x7F
                if tone != 0x7F and not b >> 5:
                    t = voices[0]; w(t + TICKS, length); w(t + GATE, length); w(t + ENV_INDEX, 0); w(t + ENV_TICKS, 1)
                    tone = tone + r(t + TRANSPOSE) & 0xFFFF; shift = tone // 12 & 0xFF
                    d = r(data + NOTES + 2 * (tone % 12)) >> shift if shift < 16 else 0
                    w(t + PITCH, d); w(t + DIVISOR, d)
                last = m[di] & 0x80; di += 2
                if last: break
        else: raise ValueError('sound script does not wait')
        if not r(cur + TICKS): di = 0
        w(cur + SCRIPT, di)

    def step(si):
        w(si + LEVEL, r(si + LEVEL) + r(si + LEVEL_STEP)); w(si + PITCH, r(si + PITCH) + r(si + SLIDE))
        vibrato, phase = 0, r(si + PHASE) + r(si + PHASE_STEP) & 0xFFFF
        if phase:
            if phase >= r(si + WAVE_LENGTH): phase = phase - r(si + WAVE_LENGTH) & 0xFFFF
            w(si + PHASE, phase)
            vibrato = s16(m[(s16(phase) >> 4) + r(si + WAVE) & 0xFFFF] << 8) * s16(r(si + DEPTH)) >> 16
        w(si + DIVISOR, vibrato + r(si + PITCH))
        gate = r(si + GATE)
        if gate:
            w(si + GATE, gate - 1)
            if gate == 1: w(si + ENV_INDEX, 0x10); w(si + ENV_TICKS, 1)
        w(si + TICKS, r(si + TICKS) - 1)
        if not r(si + TICKS): run(si)
        left = r(si + ENV_TICKS)
        if left:
            w(si + ENV_TICKS, left - 1)
            for _ in range(limit if left == 1 else 0):
                e = r(si + ENVELOPE) + r(si + ENV_INDEX); w(si + ENV_INDEX, r(si + ENV_INDEX) + 4)
                if r(e + 2) != 0xFFFF: w(si + LEVEL_STEP, r(e)); w(si + ENV_TICKS, r(e + 2)); break
                w(si + LEVEL, r(e))
                if not r(e): w(si + LEVEL_STEP, 0)

    out = []
    for _ in range(limit):
        speaker = None
        for si in voices:
            if not r(si + TICKS): continue
            step(si)
            if speaker is None and r(si + LEVEL) and r(si + TICKS): speaker = si
        if not any(r(si + TICKS) for si in voices): break
        out.append((r(speaker + DIVISOR) or 0x10000, r(speaker + LEVEL) & 3) if speaker is not None else (0, 0))
    else: raise ValueError('sound cue does not end')
    while out and out[-1][1] != 3: out.pop()
    return out


def cue(game_folder, command):
    out = []
    for divisor, gate in ticks(game_folder, command):
        hz = round(PIT_HZ / divisor, 2) if gate == 3 else 0.0
        if out and out[-1][0] == hz: out[-1][1] += 1
        else: out.append([hz, 1])
    return [(hz, round(n * TICK_MS, 3)) for hz, n in out]


def test():
    from sm import _sound_test
    return _sound_test.test()
