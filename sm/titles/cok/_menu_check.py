import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='sm-cok-menu-'))
    os.environ.update(SM_CONFIG_HOME=str(work / 'config'), SM_SAVE_ROOT=str(work / 'saves'))
    from sm.engine import Session
    from sm.titles import cok
    from sm.titles.cok.menu import render
    from sm.titles.cok.creation import Kind
    from sm.ui.art import PALETTE
    observations = []
    for _ in range(2):
        session = Session(profile=cok, slot=None, directory=args.folder, auto_resolve=False)
        try:
            game, decision = session.game, session.decision
            assert decision and decision['kind'] == Kind.MAIN_MENU.value
            assert game.menu_ids == (0, 6, 8, 11, 12)
            assert tuple(decision['options']) == tuple(game.assets.labels[i] for i in game.menu_ids)
            assert game.s.dataset == 1 and game.s.block == 0 and not game.s.party
            assert game.s.r0[0x1F4] == 3 and game.s.r0[0x1F9:0x1FC] == [2, 2, 2]
            assert not game.trace
            frame = render(game)
            pixels = b''.join(frame.rows)
            assert len(pixels) == 64000 and max(pixels) < 16
            assert sum(value != 0 for value in pixels) > 3000
            observations.append(dict(decision=decision['i'], kind=decision['kind'],
                                     state_hash=decision['hash'], option_ids=list(game.menu_ids),
                                     frame_sha256=hashlib.sha256(pixels).hexdigest()))
            raw = b''.join(b'\0' + b''.join(bytes(PALETTE[value]) for value in row) for row in frame.rows)
            chunks = ((b'IHDR', struct.pack('>2I5B', 320, 200, 8, 2, 0, 0, 0)),
                      (b'IDAT', zlib.compress(raw)), (b'IEND', b''))
            png = b'\x89PNG\r\n\x1a\n' + b''.join(struct.pack('>I', len(data)) + kind + data
                        + struct.pack('>I', zlib.crc32(kind + data)) for kind, data in chunks)
            (work / 'main-menu.png').write_bytes(png)
            game.s.party = [object()]
            assert game.assets.choices(game.s) == (0, 1, 2, 5, 6, 7, 9, 10, 12)
            game.s.r1[0x2A8] = 1
            assert game.assets.choices(game.s) == (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 12)
            game.s.party = []
        finally:
            session.close()
        assert not session._worker.is_alive()
    assert observations[0] == observations[1]
    report = dict(result='PASS', milestone='initial main menu only', gameplay_decisions=0,
                  replay_equal=True, observations=observations, external_frames=str(work),
                  first_town='BLOCKED: native character-load rule binding requires scope review')
    (ROOT / 'herdr/reports/COK_MENU_GATE.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
