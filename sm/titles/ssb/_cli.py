import sys, importlib, pkgutil, time, os, json

def test(arguments, local):
    import atexit, shutil, tempfile
    from sm.titles.ssb.intake import file_path, require_folder
    from unittest import SkipTest
    os.makedirs(local, exist_ok=True)
    os.environ['SM_SAVE_ROOT'] = tempfile.mkdtemp(prefix='suite-saves-'); atexit.register(shutil.rmtree, os.environ['SM_SAVE_ROOT'], True)
    t = time.time(); bad = 0
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    names = [n for _, n, _ in pkgutil.iter_modules([here]) if not n.startswith('_') and n != 'units']
    names += ['titles.ssb.units.' + n for _, n, _ in pkgutil.iter_modules([os.path.join(here, 'titles', 'ssb', 'units')]) if not n.startswith('_')]
    names += ['titles.ssb.' + n for _, n, _ in pkgutil.iter_modules([os.path.join(here, 'titles', 'ssb')]) if not n.startswith('_')]
    names += ['titles.ssb._start_test']
    installed = require_folder()
    fixtures = {m: ('A', 'B') for m in ('host', 'rec', 'save', 'ui', 'units.creation')}
    fixtures['units.shops'] = ('B',)
    fixtures.update({m: ('A',) for m in ('player', 'route', 'vm', 'units.camp')})
    fixtures = {('titles.ssb.' + m if m in ('host', 'rec', 'save', 'ui', 'player', 'route', 'vm') or m.startswith('units.') else m): slots
                for m, slots in fixtures.items()}
    for m in sorted(names):
        mod = importlib.import_module('sm.' + m)
        if hasattr(mod, 'test'):
            try:
                missing = [f'SAVGAM{s}.DAT' for s in fixtures.get(m, ()) if not file_path(installed, f'SAVGAM{s}.DAT').is_file()]
                if missing: raise SkipTest('requires installed save fixtures: ' + ', '.join(missing))
                mod.test(); print('ok  ', m)
            except SkipTest as e: print('SKIP', m, str(e))
            except Exception as e: bad += 1; print('FAIL', m, repr(e))
    print('%.2fs' % (time.time() - t)); return bool(bad)


def route(arguments, local):
    from sm.titles.ssb import route as R, player
    r, g = R.play(); os.makedirs(local, exist_ok=True)
    json.dump([t[6] for t in g.trace], open(os.path.join(local, 'route.json'), 'w'))
    print(r, '| last step', g.step, '| decisions', len(g.trace), '| block %d/%d' % (g.s.dataset, g.s.block), '| trace', player.save_trace(g))
    return r != 'DONE'


def maxrun(arguments, local):
    from sm.titles.ssb import route as R, player
    start = time.monotonic(); result, g = R.maxrun()
    player.save_trace(g, os.path.join(local, 'maxrun_trace.json'))
    player.save_trace(g)
    w = g.player
    step = w.steps[min(w.i, len(w.steps)-1)]['n'] if w.steps else 'end'
    line = '%s | prompts answered by model %d | fights won %d / fought %d | furthest step %s | finale %s | play seconds %.2f | decisions %d' % (
        result, w.model_answers, g.run_watch.won, g.run_watch.fights, step, 'yes' if g.vm.m0(0x4CD9) == 1 else 'no', g.run_watch.elapsed(), len(g.trace))
    with open(os.path.join(local, 'maxrun_result.txt'), 'w', encoding='utf-8') as f: f.write(line + '\n')
    with open(os.path.join(local, '..', 'herdr', 'lanes', 'sm-m1.status'), 'w', encoding='utf-8') as f:
        f.write(time.strftime('%H:%M') + ' DONE ' + line + '\n')
    print(line); return result != 'DONE'


def replay(arguments, local):
    from sm.titles.ssb import player
    i = player.replay(arguments[0] if arguments else os.path.join(local, 'trace.json'))
    print('replay: same hash at every decision' if i is None else 'replay: first divergence at decision %d' % i); return i is not None


def dump(arguments, local):
    from sm import ecl
    from sm.titles.ssb import data as ssb_data
    ds, rec = int(arguments[0]), int(arguments[1]); code = ssb_data.records()[(ds, rec)]; vec, ins = ecl.trace(code)
    os.makedirs(os.path.join(local, 'ecl'), exist_ok=True); path = os.path.join(local, 'ecl', 'ECL%d_%02d.txt' % (ds, rec))
    with open(path, 'w', encoding='utf-8') as f:
        f.write('vectors A B C D E = %s\n' % ' '.join('%04X' % v for v in vec))
        for pc in sorted(ins):
            op, ops, _ = ins[pc]
            f.write('%04X %-15s %s\n' % (pc, ecl.OPS.get(op, ('?',))[0], ', '.join('"%s"' % o[3] if o[0] == 0x80 else ('#%d' % ecl.word(o) if o[0] in (0, 2) else '[%04X]' % ecl.word(o)) for o in (ops or []))))
    print(path)


def cells(arguments, local):
    from sm.titles.ssb import walk
    ds, mid = int(arguments[0]), int(arguments[1]); m = walk.Map(ds, mid)
    os.makedirs(os.path.join(local, 'ecl'), exist_ok=True); path = os.path.join(local, 'ecl', 'GEO%d_%02d.txt' % (ds, mid))
    with open(path, 'w') as f:
        f.write('    ' + ' '.join('%3d' % x for x in range(16)) + '   (x right, y down; value = attr and 3Fh, + = attr >= 80h)\n')
        for y in range(16): f.write('%3d ' % y + ' '.join('%2d%s' % (m.attr(x, y) & 63, '+' if m.attr(x, y) & 0x80 else ' ') for x in range(16)) + '\n')
    print(path)


def run(arguments, local):
    import json
    from pathlib import Path
    from . import player
    result, game = player.run(json.loads((Path(local) / 'route.json').read_text()))
    print(result, '| decisions', len(game.trace), '| trace', player.save_trace(game))
    return result != 'DONE'
