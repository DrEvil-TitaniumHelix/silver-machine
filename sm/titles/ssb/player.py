"""The total player (PLAN.md 1.2): answers every decision from the proven route; resolvers apply outcomes. run -> trace with
sha256(State) per decision (local/trace.json, gitignored); replay -> first decision whose hash differs (V6). GU-60: the first
decision the route cannot answer = blockage, reported, never patched."""
import json, os, sys, subprocess, time
from sm.replay import Replay, Divergence
from sm.titles.ssb import host, vm as V
from sm.titles.ssb.resolve import resolve
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'local')

class Blocked(Exception): pass

def player(route):
    it = iter(route)
    def answer(kind, options, g, **info):
        try: c = next(it)
        except StopIteration: raise Blocked('route exhausted at a %s decision (options %r)' % (kind, options))
        if not g.engines and kind in ('COMBAT', 'TREASURE', 'CAMP', 'SHOP', 'TEMPLE', 'VAULT', 'CREATE', 'ACK'): resolve(kind, g)
        return c
    return answer

def run(route, slot='A', engines=False, directory=None, maxrun=False, seed=0, retry_journal=None):
    """Replay choices with the initial System.Random seed (0C5D:0CDF); finale = [4CD9]."""
    g = host.Game(player(route), slot, engines, directory)
    g.initial_seed = g.s.seed = seed & 0xFFFFFFFF
    from sm.titles.ssb.units import combat
    original_combat = combat.run
    if retry_journal is not None:
        from sm.titles.ssb.route import replaying
        g.replay_journal, g.replay_consumed = retry_journal, 0
        combat.run = replaying(original_combat)
    try:
        if maxrun:
            from sm.titles.ssb.route import observed_play
            # Replay is bounded by the recorded choices, not this machine's wall-clock speed.
            # A time-limited original run must still compare every recorded decision.
            r = observed_play(g, seconds=float('inf'), limit=len(route) + 1)
        else:
            from sm.engine import play
            from sm.titles import ssb
            r = play(g, g.player, profile=ssb, limit=len(route) + 1)
    except (Blocked, V.Halt) as e:
        s = g.s; r = 'BLOCKED at decision %d (data set %d, block %d, x %d y %d, state %s): %s' % (len(g.trace), s.dataset, s.block, s.x, s.y, s.hash(), e)
    finally: combat.run = original_combat
    if retry_journal is not None and g.replay_consumed != len(retry_journal) and not hasattr(g, 'replay_error'):
        g.replay_error = 'retry journal not fully consumed'
    return r, g

def save_trace(g, path=None):
    """Record ov03:3DB9 decision states and the System.Random (0C5D:0CDF) initial seed."""
    path = path or os.path.join(LOCAL, 'trace.json'); os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({'choices': [t[6] for t in g.trace], 'hashes': [t[5] for t in g.trace], 'where': [list(t[1:5]) for t in g.trace],
               'slot': getattr(g, 'slot', 'A'), 'engines': g.engines, 'directory': getattr(g, 'directory', None),
               'maxrun': getattr(g, 'maxrun', False), 'seed': getattr(g, 'initial_seed', 0),
               'final_hash': g.s.hash(g.vm), 'retry_journal': getattr(g, 'retry_journal', None)}, open(path, 'w'))
    return path

def divergence(path):
    """V6 / ov03:3DB9: compare decision identity and terminal state, as well as hashes:
    {'i', 'recorded': (kind, data set, block, pc), 'now': (kind, data set, block, pc) or None (the re-run ended earlier)}."""
    t = json.load(open(path)); _, g = run(t['choices'], **{k: t[k] for k in ('slot', 'engines', 'directory', 'maxrun', 'seed', 'retry_journal') if k in t})
    where = t.get('where') or [None] * len(t['hashes'])
    check = Replay((value, tuple(where[i]) if where[i] is not None else None) for i,value in enumerate(t['hashes']))
    try:
        for row in g.trace: check.check(row[5], row[1:5])
        check.finish(g.s.hash(g.vm), **({'expected_hash': t['final_hash']} if 'final_hash' in t else {}))
    except Divergence as error:
        result = {'i': error.index, 'recorded': error.expected[1] or None if error.expected else None,
                  'now': error.actual[1] if error.actual else None}
        if error.reason == 'terminal state': result['reason'] = 'terminal state differs'
        return result
    if hasattr(g, 'replay_error'):
        return {'i': check.index, 'recorded': None, 'now': None, 'reason': g.replay_error}
    return None

def replay(path):
    """ov03:3DB9 replay: first divergent decision or terminal observation, else None."""
    d = divergence(path)
    if d: print('divergence at decision %d: recorded %r, this run %r%s' % (d['i'], d['recorded'], d['now'],
                                                                        '; ' + d['reason'] if 'reason' in d else ''))
    return d and d['i']

def test():
    """V6 / ov03:3DB9: newly recorded route prefix, nonzero System.Random seed (0C5D:0CDF), replay in a
    fresh one (`python -m sm replay`): zero divergence, same hash list, < 3 s."""
    from sm.titles.ssb.route import Walk, load_steps
    from unittest import SkipTest
    from pathlib import Path
    fixtures = ['local/answers.json']
    if not (Path(LOCAL).parent / 'herdr/route/steps.json').is_file():
        fixtures += ['herdr/route/steps_%s.json' % t for t in ('T1', 'T2', 'T2b', 'T3', 'T3b')]
    missing = [p for p in fixtures if not (Path(LOCAL).parent / p).is_file()]
    if missing: raise SkipTest('requires route fixtures: ' + ', '.join(missing))
    t0 = time.time(); steps, answers = load_steps(); recorded = host.Game(Walk(steps, answers))
    recorded.play(limit=600)  # Record with the current RNG semantics; local/route.json may predate a byte-proved engine correction.
    route = [t[6] for t in recorded.trace]
    assert len(route) == 600, 'fresh replay prefix stopped early'
    r, g = run(route); n = len(g.trace)
    assert r == 'DONE' or n >= len(route), 'route stopped early: %s' % r                  # a halt inside the route = V5 problem, reported as is
    assert g.trace == recorded.trace, 'freshly recorded decision/state sequence did not replay'
    path = save_trace(g, os.path.join(LOCAL, 'trace_test.json'))
    assert divergence(path) is None, 'in-process replay diverges: %r' % divergence(path)
    p = subprocess.run([sys.executable, '-m', 'sm', 'replay', path], cwd=os.path.dirname(LOCAL), capture_output=True, text=True)
    assert p.returncode == 0, 'cross-process replay: %s %s' % (p.stdout.strip(), p.stderr.strip()[-300:])
    from unittest.mock import patch
    # Cheap negative checks reuse the already executed game, with one altered observation.
    with patch(__name__ + '.run', return_value=(r, g)):
        row = g.trace[0]; g.trace[0] = (row[0], 'WRONG_KIND', *row[2:])
        assert divergence(path)['i'] == 0, 'decision identity not checked'
        g.trace[0] = row; g.s.seed ^= 1
        assert divergence(path)['reason'] == 'terminal state differs', 'final mutation not checked'
        g.s.seed ^= 1
    _, seeded = run([0], seed=0x12345678)
    seeded_path = save_trace(seeded, os.path.join(LOCAL, 'trace_seed_test.json'))
    assert divergence(seeded_path) is None, 'initial nonzero seed not replayed'
    assert time.time() - t0 < 3, 'replay test took %.1f s for %d decisions' % (time.time() - t0, n)
