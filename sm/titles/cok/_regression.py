import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / 'local/onecore/baseline'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slice')
    args = parser.parse_args()
    if not args.slice.replace('_', '').isalnum():
        parser.error('slice must be an alphanumeric label')
    target = ROOT / ('herdr/reports/COK_REGRESSION_' + args.slice + '.json')
    if target.exists():
        parser.error('refusing to replace existing regression evidence')
    work = Path(tempfile.mkdtemp(prefix='sm-cok-gate-'))
    originals = ROOT.parent / 're-targets/goldbox/adnd-collectors-cd/WIZWORKS'
    env = dict(os.environ, SM_SECRET=str(originals / 'SECRET'),
               SM_CONFIG_HOME=str(work / 'config'), SM_SAVE_ROOT=str(work / 'saves'),
               PYTHONDONTWRITEBYTECODE='1')
    report = dict(slice=args.slice, logs=str(work), checks={}, baseline_hashes={})
    for name in ('route-trace.json', 'dqk.json'):
        report['baseline_hashes'][name] = hashlib.sha256((BASELINE / name).read_bytes()).hexdigest()

    def run(name, code, timeout=300):
        start = time.monotonic()
        child = subprocess.run([sys.executable, '-I', '-B', '-u', '-c',
                                'import sys;sys.path.insert(0,' + repr(str(ROOT)) + ');' + code],
                               cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (work / (name + '.txt')).write_text(child.stdout + child.stderr, encoding='utf-8')
        report['checks'][name] = dict(exit=child.returncode, seconds=round(time.monotonic() - start, 3))
        if name == 'suite':
            report['checks'][name].update(passed=sum(line.startswith('ok  ') for line in child.stdout.splitlines()),
                                          failed=sum(line.startswith('FAIL') for line in child.stdout.splitlines()),
                                          skipped=sum(line.startswith('SKIP') for line in child.stdout.splitlines()))
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(name, json.dumps(report['checks'][name]), flush=True)
        if child.returncode:
            raise RuntimeError(name + ' failed; inspect external log ' + str(work / (name + '.txt')))

    run('ssb_route', "import json;from pathlib import Path;from sm.titles.ssb.route import play;"
        + 'baseline=json.loads(Path(' + repr(str(BASELINE / 'route-trace.json')) + ").read_text());"
        + "result,game=play();assert result=='DONE',result;"
        + "assert len(game.trace)==15511;assert [row[5] for row in game.trace]==baseline['hashes'];"
        + "assert game.s.hash(game.vm)==baseline['final_hash'];print('PASS 15511 decision hashes and terminal')")
    run('suite', 'from sm.titles.ssb import player;player.LOCAL=' + repr(str(work / 'suite')) + ';'
        + 'from sm.titles.ssb._cli import test;sys.exit(test([],' + repr(str(work / 'suite')) + '))')
    run('dqk_witness', "import json;from pathlib import Path;from sm.titles.dqk.player import run;"
        + 'baseline=json.loads(Path(' + repr(str(BASELINE / 'dqk.json')) + ").read_text());"
        + "result=run();assert result['status']=='DONE';assert result['decisions']==4522;"
        + "assert result['final_hash']==baseline['final_hash'];assert result['witness']==baseline['witness'];"
        + "assert result['replay'];print('PASS 4522 decision witness, replay and terminal')")
    run('source_guard', 'import runpy;runpy.run_path(' + repr(str(ROOT / 'herdr/tools/source_guard.py'))
        + ",run_name='__main__')")
    report['result'] = 'PASS'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
