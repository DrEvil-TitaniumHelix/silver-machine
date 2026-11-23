import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from sm.engine import Session
from .menu import Game
from . import creation
from .faults import BindingRequired


PARTY = 7, 3, 0, 5, 4, 2
WISHES = {2: ['Bless', 'Bless'] + ['Cure Light Wounds'] * 3 + ['Hold Person'] * 3 + ['Prayer'] * 3 + ['Cure Serious Wounds'] * 2,
          3: ['Magic Missile'] * 4 + ['Shield'] + ['Fireball'] * 3}
COMBAT_SPELLS = {2: ('Bless', 'Prayer'), 3: ('Fireball', 'Magic Missile')}


class OpeningChoices:
    def __init__(self):
        self.created = 0
        self.camped = False
        self.viewed = False
        self.memorized = set()
        self.rested = False
        self.picks = {}

    def member(self, game, label):
        return next((k for k in range(len(PARTY)) if label == 'DKK%d' % (k + 1)), None)

    def __call__(self, decision, game):
        kind, options, info = decision['kind'], decision['options'], decision['info']
        if info.get('action') == 'main-menu':
            action = creation.CREATE if self.created < 6 else creation.ADD if len(game.s.party) < 6 else creation.BEGIN
            return game.menu_ids.index(action)
        if kind == creation.Kind.RACE.value: return 6
        if kind in (creation.Kind.GENDER.value, creation.Kind.ALIGNMENT.value): return 0
        if kind == creation.Kind.ICON.value or info.get('prompt') == game.assets.text('iconOkQuery'):
            return next((options.index(label) for label in ('Yes','Exit','Keep') if label in options),0)
        if kind == creation.Kind.CLASS.value: return options.index(game.assets.names('classNames')[PARTY[self.created]])
        if kind == creation.Kind.ROLL.value: return options.index('No')
        if kind == creation.Kind.DEITY.value: return options.index('Majere') if 'Majere' in options else 0
        if kind == creation.Kind.NAME.value: return 'DKK%d' % (self.created + 1)
        if kind == creation.Kind.SAVE.value:
            self.created += 1
            return 0
        if kind == creation.Kind.ADD.value:
            return next(i for i, label in enumerate(options) if not label.startswith('*') and label != 'Exit')
        if kind == 'MENU' and options == ('Yes', 'No') and not self.camped:
            self.camped = True
            return 0
        if kind == 'CAMP_MENU':
            want = next((k for k in WISHES if k not in self.memorized), None)
            if info.get('prompt') == 'Camp':
                if not self.viewed:
                    self.viewed = True
                    return options.index('View')
                return options.index('Magic' if want is not None or not self.rested else 'Exit')
            if want is None:
                if self.rested: return options.index('Exit')
                self.rested = True
                return options.index('Rest')
            if self.member(game, info.get('member')) != want: return options.index('char-down')
            self.memorized.add(want)
            return options.index('Memorize')
        if kind == 'SPELL' and 'Keep' in options: return options.index('Keep')
        if kind == 'SPELL':
            who = game.s.sel
            k = self.picks.get(who, 0)
            self.picks[who] = k + 1
            wishes = WISHES.get(who, [])
            bare = [o.strip(' *').split(' (')[0] for o in options]
            while k < len(wishes) and wishes[k] not in bare: k += 1
            if k >= len(wishes): return bare.index('Exit')
            self.picks[who] = k + 1
            return bare.index(wishes[k])
        if kind == 'CAMP_CONFIRM' and 'emorize' in str(info.get('prompt')): return 0
        if kind == 'CREATE_VIEW': return options.index('Exit')
        if kind == 'CAMP_REST': return options.index('Rest')
        if kind == 'COMBAT_ACTION':
            k = info.get('actor', -1)
            if k in COMBAT_SPELLS and 'Cast' in options:
                from .magic import castable, spell
                held = [spell(game, i).name for i, _ in castable(game, game.s.party[k], True)]
                if any(n in held for n in COMBAT_SPELLS[k]):
                    battle = game.current_battle
                    if k == 2 or any(battle.distance(k, j) <= 18 for j in battle.targets(k)): return options.index('Cast')
                    return options.index('Guard' if 'Guard' in options else 'End')
            return options.index('Quick')
        if kind == 'COMBAT_SPELL':
            k = info.get('actor', -1)
            bare = [o.lstrip(' *').split(' (')[0] for o in options]
            return next(bare.index(n) for n in COMBAT_SPELLS.get(k, ()) + ('Exit',) if n in bare)
        if kind == 'TARGET' and info.get('spell'):
            return self.aim(game, info, options)
        if kind == 'COMBAT_CONFIRM' and info.get('prompt') == game.assets.text('abortSpellPrompt'): return 0
        if kind == 'COMBAT_AUTO': return 0
        if kind == 'ACK': return 0
        if options and 'No' in options: return options.index('No')
        if options and 'Exit' in options: return options.index('Exit')
        if options is None: raise BindingRequired('unplanned typed choice ' + kind)
        return 0

    def aim(self, game, info, options):
        battle = game.current_battle
        caster = info['actor']
        targets = [int(o.rsplit('#', 1)[1]) for o in options if '#' in o]
        friendly = [j for j in targets if battle.chars[j].b[creation.F['side']] == 0]
        enemies = [j for j in targets if battle.chars[j].b[creation.F['side']] != 0]
        from .magic import spell
        if not spell(game, info['spell']).hostile: return targets.index(caster) if caster in targets else options.index('Exit')
        if not enemies: return options.index('Exit')
        party = [j for j in range(len(battle.chars)) if battle.chars[j].b[creation.F['side']] == 0 and battle.chars[j].b[creation.F['active']]]
        return targets.index(max(enemies, key=lambda j: min(battle.distance(j, p) for p in party)))


def execute(directory=None, *, choices=None, limit=10000, seed=0, interactive=None):
    with TemporaryDirectory(prefix='sm-dkk-route-') as tmp:
        game = Game(None, directory=directory)
        game.s.seed = seed
        game.roster_directory = Path(tmp)
        session = Session(profile='dkk', game=game, limit=limit)
        policy, decisions = OpeningChoices(), []
        try:
            while session.decision is not None:
                d = session.decision
                if len(decisions) >= limit: raise BindingRequired('Death Knights route decision limit')
                if choices is not None:
                    if len(decisions) >= len(choices): raise ValueError('replay ran out of choices')
                    saved = choices[len(decisions)]
                    if (d['kind'], d['hash']) != (saved['kind'], saved['hash']):
                        raise ValueError('replay diverged at decision %d' % len(decisions))
                    answer = saved['choice']
                elif interactive is not None: answer = interactive(d, game)
                else: answer = policy(d, game)
                decisions.append(dict(kind=d['kind'], hash=d['hash'], choice=answer))
                session.step(answer)
            if session.error is not None: raise session.error
            if choices is not None and len(decisions) != len(choices): raise ValueError('replay has unused choices')
            if session.result not in ('FIRST_FIGHT_WON','DEFEAT'): raise BindingRequired('Death Knights ended: ' + str(session.result))
            battle = game.s.g['dkk.battle']
            summary = dict(result=session.result, hash=game.state_hash(), decisions=len(decisions),
                           seed=game.s.seed,
                           rounds=battle['round'], enemy_survivors=battle['enemy_survivors'],
                           experience=battle['experience'], difficulty=game.s.r0[0x1F4],
                           block=[game.s.dataset, game.s.block], position=[game.s.x, game.s.y],
                           active_party=sum(bool(c.b[creation.F['active']]) for c in game.s.party),
                           combat_hash=hashlib.sha256(json.dumps(game.combat_log, sort_keys=True).encode()).hexdigest())
            return dict(version=1, seed=seed, choices=decisions, summary=summary)
        finally: session.close()


def test():
    for seed in (0,4660,22136):
        first = execute(seed=seed)
        second = execute(choices=first['choices'],seed=seed)
        assert first == second
        assert first['summary']['difficulty'] == 3
        if first['summary']['result'] == 'FIRST_FIGHT_WON': assert first['summary']['enemy_survivors'] == 0
        else: assert first['summary']['active_party'] == 0
        assert {'CAMP_MENU', 'CAMP_REST', 'CREATE_VIEW', 'COMBAT_ACTION'} <= {d['kind'] for d in first['choices']}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(arguments)
    first = execute(args.folder, seed=args.seed)
    second = execute(args.folder, choices=first['choices'], seed=args.seed)
    summary = first['summary']
    print('Death Knights: %(result)s after %(rounds)d combat rounds, %(enemy_survivors)d enemies left, %(decisions)d decisions' % summary)
    print('Hash %s; replay %s' % (summary['hash'], second['summary']['hash']))
    if first != second: raise SystemExit('replay differs')
    print('Replay equal')
    return 0
