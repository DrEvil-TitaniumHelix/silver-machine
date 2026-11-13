import json, os, sys, time
from pathlib import Path
from collections import Counter, deque
from sm.search import shortest_path
from sm.titles.ssb import host, walk, vm as V
from sm.titles.ssb.resolve import resolve
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RESOLVED = ('COMBAT', 'TREASURE', 'CAMP', 'SHOP', 'TEMPLE', 'VAULT', 'CREATE', 'ACK')
DOOR = ('Bash', 'Knock', 'Pick')

class Stop(Exception): pass


def prompt_line(kind, options, info, g):
    return 'kind %s options %r info %r block %d/%d pc %04X' % (
        kind, options, info, g.s.dataset, g.s.block, info.get('at', getattr(g.vm, 'at', 0)))


def write_json(path, value):
    path = Path(path); temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8'); os.replace(temporary, path)

def load_steps(path=None):
    path = path or os.environ.get('SM_STEPS') or os.path.join(ROOT, 'herdr', 'route', 'steps.json')
    if os.path.exists(path): steps = json.load(open(path))
    else:
        steps = [w for t in ('T1', 'T2', 'T2b', 'T3', 'T3b') if os.path.exists(f := os.path.join(ROOT, 'herdr', 'route', 'steps_%s.json' % t)) for w in json.load(open(f))]
    ans = os.environ.get('SM_ANSWERS') or os.path.join(ROOT, 'local', 'answers.json')
    return steps, (json.load(open(ans)) if os.path.exists(ans) else {})

class Walk:
    def __init__(self, steps, answers, rules_path=None, *, recover_damage=True):
        self.steps, self.answers, self.i, self.mq, self.buyq = steps, answers, 0, None, None
        self.recover_damage = recover_damage
        self.rules = None; self.model_answers = 0
        if rules_path is not None:
            self.rules_path = Path(rules_path); self.local = self.rules_path.parent; self.local.mkdir(parents=True, exist_ok=True)
            self.rules = json.loads(self.rules_path.read_text(encoding='utf-8')) if self.rules_path.exists() else [
                {'kind': 'NUMBER', 'purpose': '*', 'answer': {'info': 'max'}, 'reason': 'Rule: engine numeric inputs take the offered maximum'},
                {'kind': 'STRING', 'purpose': '*', 'answer': '', 'reason': 'Rule: engine string inputs are empty'},
                {'kind': 'MENU', 'options': ['continue', 'end'], 'answer': {'option': 'end'}, 'reason': 'Rule: end a won battle'},
                {'kind': 'ACK', 'options': ['ok'], 'answer': {'option': 'ok'}, 'reason': 'Acknowledge the game message'}]
            for rule in self.rules: self.validate_rule(rule)
            write_json(self.rules_path, self.rules)
            for name in ('ask.json', 'answer.json'): (self.local / name).unlink(missing_ok=True)

    @staticmethod
    def validate_rule(rule):
        if not isinstance(rule, dict) or set(rule) - {'kind', 'purpose', 'prompt', 'options', 'answer', 'reason'}:
            raise ValueError('rule matches may use kind, purpose, prompt and option texts only; never position')
        if rule.get('kind') not in host.DECISION_KINDS or rule['kind'] == 'COMBAT_ACTION': raise ValueError('invalid rule kind; Quick cannot be overridden')
        if 'answer' not in rule or not any(k in rule for k in ('purpose', 'prompt', 'options')): raise ValueError('rule needs prompt, purpose or options')

    @staticmethod
    def matches(rule, kind, options, info):
        return (rule['kind'] == kind and ('purpose' not in rule or 'purpose' in info and rule['purpose'] in ('*', info['purpose']))
                and ('prompt' not in rule or rule['prompt'] == info.get('prompt'))
                and ('options' not in rule or rule['options'] == options))

    @staticmethod
    def rule_answer(rule, options, info):
        answer = rule['answer']
        if isinstance(answer, dict):
            if set(answer) == {'option'}: return options.index(answer['option'])
            if set(answer) == {'each_then'}:
                seen = info.get('_seen', set()); left = [i for i, o in enumerate(options) if o != answer['each_then'] and repr(o) not in seen]
                return left[0] if left else options.index(answer['each_then'])
            if answer == {'info': 'max'}: return info['max']
            raise ValueError('rule answer must be a value, an option text, or info max')
        return answer

    def log_answer(self, kind, options, info, g, answer, reason, source):
        entry = dict(kind=kind, options=options, info=info, block=[g.s.dataset, g.s.block], pc=getattr(g.vm, 'at', 0),
                     step=self.steps[min(self.i, len(self.steps)-1)]['n'] if self.steps else 'end', answer=answer, reason=reason, source=source)
        with (self.local / 'maxrun_answers.log').open('a', encoding='utf-8') as f: f.write(json.dumps(entry) + '\n')
        return answer

    def ask_model(self, kind, options, info, g):
        from sm.titles.ssb.units.shops import name
        if g.s.g.get('combat.active'):
            raise Finding('Quick raised an uncovered combat prompt; no model action inside a fight; ' + prompt_line(kind, options, info, g))
        if os.environ.get('SM_ASK') == 'stop':
            write_json(self.local / 'ask.json', dict(kind=kind, options=options, info={k: v for k, v in info.items() if k != '_seen'},
                       block=[g.s.dataset, g.s.block], pc=getattr(g.vm, 'at', 0), step=self.steps[min(self.i, len(self.steps)-1)]['n'] if self.steps else 'end',
                       text=''.join(g.vm.out)[-1200:]))
            raise Stop('PAUSE unknown prompt ' + prompt_line(kind, options, info, g))
        watch = g.run_watch; start = time.monotonic(); watch.wait_start = start
        request = dict(kind=kind, options=options, info=info, block=[g.s.dataset, g.s.block], pc=getattr(g.vm, 'at', 0),
                       decision=len(g.trace),
                       step=self.steps[min(self.i, len(self.steps)-1)]['n'] if self.steps else 'end',
                       party=[dict(name=name(c), hp=c.b[0x1B5], max=c.b[0x70], status=c.b[0x1A6]) for c in g.s.party],
                       text=''.join(g.vm.out)[-2500:])
        try:
            write_json(self.local / 'ask.json', request)
            while True:
                try: response = json.loads((self.local / 'answer.json').read_text(encoding='utf-8-sig'))
                except (FileNotFoundError, json.JSONDecodeError): time.sleep(0.05); continue
                (self.local / 'answer.json').unlink()
                try:
                    rule, answer, reason = response['rule'], response['answer'], response['reason']; self.validate_rule(rule)
                    if not isinstance(reason, str) or not reason.strip(): raise ValueError('answer needs a reason')
                    if not self.matches(rule, kind, options, info) or self.rule_answer(rule, options, info) != answer:
                        raise ValueError('generalized rule must match this prompt and produce the submitted answer')
                    if options is not None and (not isinstance(answer, int) or not 0 <= answer < len(options)): raise ValueError('answer outside options')
                    if kind == 'NUMBER' and (not isinstance(answer, int) or not info.get('min', answer) <= answer <= info.get('max', answer)): raise ValueError('number outside bounds')
                    if kind == 'STRING' and not isinstance(answer, str): raise ValueError('string answer required')
                except (KeyError, ValueError, TypeError) as e:
                    request['error'] = str(e); write_json(self.local / 'ask.json', request); continue
                rule['reason'] = reason; self.rules.append(rule); write_json(self.rules_path, self.rules)
                self.model_answers += 1; (self.local / 'ask.json').unlink(missing_ok=True)
                return self.log_answer(kind, options, info, g, answer, reason, 'model')
        finally: watch.waited += time.monotonic() - start; watch.wait_start = None

    def stop(self, g, kind, why, n=None):
        s = g.s; st = self.steps[self.i] if self.i < len(self.steps) else {'n': 'end'}
        raise Stop('step %s: %s; at block %d/%d pc %04X x%d y%d facing %d, a %s decision%s' % (
            st['n'], why, s.dataset, s.block, getattr(g.vm, 'at', 0), s.x, s.y, s.dir, kind, '' if n is None else ' with %d options' % n))

    def path(self, g, to):
        s, geo = g.s, g.geo; start = (s.x, s.y, s.dir); goal = tuple(to)
        def edges(p):
            x, y, f = p
            nxt = [('turn-left', (x, y, (f + 6) % 8)), ('turn-right', (x, y, (f + 2) % 8))]
            dx, dy = walk.DELTAS[f // 2]
            if geo.map and geo.passage(s, x, y, f) and 0 <= x + dx < 16 and 0 <= y + dy < 16:
                nxt.append(('forward', (x + dx, y + dy, f)))
            return nxt
        return shortest_path(start, lambda p: p[:len(goal)] == goal, edges)

    def __call__(self, kind, options, g, **info):
        if kind == 'INPUT': return 0
        if self.rules is None or not g.engines: return self.walk_answer(kind, options, g, **info)
        if kind not in host.DECISION_KINDS: self.stop(g, kind, 'outside host closed decision set')
        if kind == 'NUMBER' and info.get('spell') == 115:
            return self.log_answer(kind, options, info, g, max(info.get('min', 0), min(0, info['max'])),
                                   'ov23:5D90: immediate blast, same legal zero as the simulation', 'strategy')
        if kind == 'MENU' and info.get('action')=='abort-spell' and getattr(self,'fight_no',0) in getattr(self,'strategy',()) and self.modes.get(self.fight_no)!='quick':
            return self.log_answer(kind,options,info,g,options.index('yes'),
                                   'ov15:3B7F/3B95: confirm the opening policy\'s cancelled target selection', 'strategy')
        if g.s.g.get('combat.active') and getattr(self, 'fight_no', 0) in getattr(self, 'strategy', ()) and kind in ('COMBAT_ACTION', 'SPELL', 'TARGET') and self.modes.get(self.fight_no) != 'quick':
            a = self.opening(kind, options, g, info)
            if a is None and kind != 'COMBAT_ACTION':
                shep('   fight %d live: opening had no answer for %s %s -> option 0' % (self.fight_no, kind, str(options)[:80])); a = 0
            if a is not None:
                if g.s.g.get('8DC7', 0) <= 1 and options: shep('   fight %d live r%s %s:%s' % (self.fight_no, g.s.g.get('8DC7'), _nm(g.combat.chars[info['actor']]) if 'actor' in info else '', options[a]))
                return self.log_answer(kind, options, info, g, a, 'opening', 'strategy')
        if kind == 'COMBAT_ACTION':
            return self.log_answer(kind, options, info, g, options.index('quick'), 'Rule: the game controls every combat action through Quick', 'quick')
        if g.s.g.get('combat.active') and info.get('action') != 'continue-battle':
            raise Finding('Quick raised an uncovered combat prompt; no model action inside a fight; ' + prompt_line(kind, options, info, g))
        if kind == 'MOVE': self.seen = {}; self.take_progress = {}; self.treasure_progress = None
        if kind == 'SHOP_MENU' and info.get('purpose') == 'treasure':
            progress = (tuple(g.s.treasure_money), tuple(bytes(item) for item in g.s.treasure_items))
            action = 'take' if 'take' in options and progress != getattr(self, 'treasure_progress', None) else 'exit'
            self.treasure_progress = progress
            return self.log_answer(kind, options, info, g, options.index(action),
                                   'Take by the existing category/list rules; exit when the pile makes no further progress', 'rule')
        if kind == 'SHOP_MENU' and info.get('purpose') == 'treasure leave':
            return self.log_answer(kind, options, info, g, options.index('no'),
                                   'ov07:1251..1258: decline going back to an untakeable pile', 'rule')
        if kind == 'SHOP_MENU' and info.get('purpose') == 'take':
            return self.log_answer(kind, options, info, g, self.take_answer(options, g),
                                   'ov07:0E6A/0E9D: move on when the selected category makes no progress', 'rule')
        st = self.steps[self.i]['n'] if self.steps and self.i < len(self.steps) else None
        if kind == 'MOVE' and 'camp' in options and st in BUFF_STEPS and getattr(self, 'buffed_step', None) != st and not g.s.g.get('combat.active'):
            self.buffed_step = st; self.cast_queue = buff_plan(g.s.party); self.buff_camp = True; self.camp_seq = ['magic', 'exit']; self.mem_queue = []
            shep('step %s: known hard fight ahead -> pre-fight buffs %s' % (st, [(_nm(g.s.party[h]), sp) for h, sp, t in self.cast_queue]))
            return self.log_answer(kind, options, info, g, options.index('camp'), 'expert: buff outside the door', 'shepherd')
        if kind == 'MOVE' and 'camp' in options and not g.s.g.get('combat.active'):
            fights = g.run_watch.fights if getattr(g, 'run_watch', None) else 0
            hurt = [c for c in g.s.party if c.b[0x1A6] != 0 or c.b[0x1B5] < c.b[0x70] // 2]
            spent = [c for c in g.s.party if key_spent(c)]
            if not hasattr(self, 'camps'): self.camps = Counter()
            if (hurt or spent) and self.camps[fights] < 3:
                self.camps[fights] += 1; self.healed_at = fights; self.camp_seq = ['magic', 'exit']; self.mem_queue = None; self.heal_casts = 0; self.heal_plan = None; self.heal_fail = set(); self.heal_last = None; self.healer_fail = set()
                shep('after fight %d: hurt %s; spells to relearn %s -> camp: Fix, memorize the loadout, rest' % (fights,
                     ', '.join('%s %d/%d' % (_nm(c), c.b[0x1B5], c.b[0x70]) for c in hurt) or '-', ', '.join(_nm(c) for c in spent) or '-'))
                return self.log_answer(kind, options, info, g, options.index('camp'), 'shepherd: heal after a fight', 'shepherd')
        a = self.camp_answer(kind, options, g, info)
        if a is not None: return self.log_answer(kind, options, info, g, a, 'shepherd camp: Fix, memorize the expert loadout (ov18:0E3D), rest (ov18:0CE7)', 'shepherd')
        for rule in reversed(self.rules):
            if self.matches(rule, kind, options, info):
                if not hasattr(self, 'seen'): self.seen = {}
                seen = self.seen.setdefault((kind, info.get('purpose'), str(info.get('prompt'))), set())
                a = self.rule_answer(rule, options, dict(info, _seen=seen))
                if options is not None and isinstance(a, int) and 0 <= a < len(options): seen.add(repr(options[a]))
                return self.log_answer(kind, options, info, g, a, rule.get('reason', 'saved prompt rule'), 'rule')
        if kind in ('MOVE', 'MENU', 'NUMBER', 'STRING', 'PARLAY', 'WHO') and not g.s.g.get('combat.active'):
            try: answer = self.walk_answer(kind, options, g, **info)
            except Stop:
                if kind == 'MOVE': raise
            else: return self.log_answer(kind, options, info, g, answer, 'Completionist walkthrough step', 'walkthrough')
        return self.ask_model(kind, options, info, g)

    def take_answer(self, options, g):
        if not hasattr(self, 'take_progress'): self.take_progress = {}
        if not hasattr(self, 'seen'): self.seen = {}
        for category, contents, purpose in (('money', tuple(g.s.treasure_money), 'take money'),
                                             ('items', tuple(bytes(i) for i in g.s.treasure_items), 'take item')):
            if any(contents) and self.take_progress.get(category) != contents:
                self.take_progress[category] = contents
                self.seen.pop(('LIST', purpose, 'None'), None)
                return options.index(category)
        self.take_progress.clear()
        return options.index('exit')

    def camp_answer(self, kind, options, g, info):
        from sm.titles.ssb import rec
        purpose = info.get('purpose')
        if kind == 'CAMP_MENU' and purpose is None and options and 'fix' in options:
            seq = getattr(self, 'camp_seq', None) or ['fix', 'magic', 'exit']; a = seq.pop(0) if len(seq) > 1 else seq[0]; self.camp_seq = seq
            return options.index(a)
        if kind == 'CAMP_MENU' and purpose == 'magic':
            if getattr(self, 'cast_queue', None):
                h, sp, t = self.cast_queue[0]
                if getattr(self, 'mem_sel', None) != h: self.mem_want = h; return options.index('select')
                self.cast_queue.pop(0); self.heal_plan = (sp, t); self.heal_last = None; self.heal_asked = False; return options.index('cast')
            if getattr(self, 'buff_camp', False):
                self.buff_camp = False; self.heal_plan = None; return options.index('exit')
            CURES = (36, 71, 58, 3)
            party = g.s.party
            last = getattr(self, 'heal_last', None)
            if last and not getattr(self, 'heal_asked', False): self.healer_fail = getattr(self, 'healer_fail', set()) | {self.mem_sel}
            elif last and (party[last[0]].b[0x1B5], party[last[0]].b[0x1A6]) == last[1:]: self.heal_fail = getattr(self, 'heal_fail', set()) | {last[0]}
            self.heal_asked = False
            self.heal_last = None
            if g.s.r0[0xE5]: self.heal_fail = set(range(len(party)))
            wounded = sorted((i for i, c in enumerate(party) if c.b[0x1A6] in (0, 4, 5) and c.b[0x1B5] < c.b[0x70] and i not in getattr(self, 'heal_fail', ())),
                             key=lambda i: party[i].b[0x1B5] * 100 // max(1, party[i].b[0x70]))
            for st, sp in ((7, 113), (6, 75)):
                vic = [i for i, c in enumerate(party) if c.b[0x1A6] == st and i not in getattr(self, 'heal_fail', ())]
                casters = [i for i, c in enumerate(party) if c.b[0x1A6] == 0 and sp in c.b[0x1E:0x69] and i not in getattr(self, 'healer_fail', ())]
                if vic and casters and getattr(self, 'heal_casts', 0) < 24:
                    self.heal_plan = (sp, vic[0])
                    if getattr(self, 'mem_sel', None) != casters[0]: self.mem_want = casters[0]; return options.index('select')
                    self.heal_casts += 1; self.heal_last = (vic[0], party[vic[0]].b[0x1B5], party[vic[0]].b[0x1A6]); return options.index('cast')
            healers = [i for i, c in enumerate(party) if c.b[0x1A6] == 0 and any(n in CURES for n in c.b[0x1E:0x69]) and i not in getattr(self, 'healer_fail', ())]
            if wounded and healers and getattr(self, 'heal_casts', 0) < 24:
                h = healers[0]; c = party[h]; t = party[wounded[0]]; deficit = t.b[0x70] - t.b[0x1B5]
                have = [sp for sp in CURES if sp in c.b[0x1E:0x69]]
                sp = next((x for x in have if x == 36 and deficit > 40), None) or next((x for x in have if x != 36), have[0])
                self.heal_plan = (sp, wounded[0])
                if getattr(self, 'mem_sel', None) != h: self.mem_want = h; return options.index('select')
                self.heal_casts += 1; self.heal_last = (wounded[0], t.b[0x1B5], t.b[0x1A6]); return options.index('cast')
            self.heal_plan = None
            if self.mem_queue is None: self.mem_queue = [i for i, c in enumerate(g.s.party) if needs_memorize(c)]; self.mem_sel = None
            if self.mem_queue:
                if self.mem_sel != self.mem_queue[0]: self.mem_want = self.mem_queue[0]; return options.index('select')
                self.mem_queue.pop(0); return options.index('memorize')
            self.mem_queue = None
            return options.index('rest') if any(n > 127 for c in g.s.party for n in c.b[0x1E:0x69]) else options.index('exit')
        if kind == 'TARGET' and purpose == 'party member' and getattr(self, 'mem_want', None) is not None:
            self.mem_sel = self.mem_want; self.mem_want = None; return self.mem_sel
        if getattr(self, 'heal_plan', None) and not g.s.g.get('combat.active'):
            if kind == 'SPELL' and options and 'cancel' in options:
                end=options.index('cancel')
                if getattr(self,'heal_asked',False): return end
                self.heal_asked = True
                return options.index(self.heal_plan[0]) if self.heal_plan[0] in options[:end] else end
            if kind == 'TARGET' and options and options[-1] in ('cancel', None):
                return options.index(self.heal_plan[1]) if self.heal_plan[1] in options else len(options) - 1
        if kind == 'CAMP_MENU' and purpose == 'rest duration': return options.index('rest')
        if kind == 'CAMP_MENU' and purpose == 'resting': return options.index('continue')
        if kind == 'SPELL' and purpose == 'memorize':
            options=options[:options.index('done')+1]
            pri = [x for cls in (0, 3) for L in range(1, 8) for x in rec.LOADOUT[cls][L]]
            for x in pri:
                if x in options: return options.index(x)
            return 0 if len(options) > 1 else len(options) - 1
        if kind == 'SPELL' and options in (['keep', 'replace'], ['yes', 'no']): return 0
        if kind == 'SPELL' and purpose == 'memorize summary': return options.index('exit')
        return None

    AREA = (115, 47, 92, 87, 51, 91, 34)
    def caster_turn(self, kind, options, g, info, globes=False):
        from sm.titles.ssb.units import magic
        cb = g.combat; side = lambda c: c.b[V.SIDE]
        enemies = [m for m in cb.chars if side(m) != 0 and m.b[V.ACTIVE]]
        party = [c for c in cb.chars if side(c) == 0 and c.b[V.ACTIVE]]
        pos = cb.position
        def near(p, r, who): return sum(1 for m in who if max(abs(pos(m)[0]-p[0]), abs(pos(m)[1]-p[1])) <= r)
        def radius(sp): m = magic.spell(sp)[6] & 15; return (m & 7) if 8 <= m <= 14 else 1
        if kind == 'COMBAT_ACTION':
            actor = cb.chars[info['actor']]; self.plan = None; self.plan_target = None
            if actor.b[0x6C] not in (0, 3, 5): return None
            key = (getattr(self, 'fight_no', 0), info['actor'], info.get('round'))
            spells = cb.spells(actor) if 'cast' in options and key not in self.tried else []
            downed = [c for c in cb.chars if side(c) == 0 and c.b[0x1A6] in (0, 4, 5)]
            wounded = sorted((p for p in downed if p.b[V.HP] < p.b[V.HPMAX] // 2), key=lambda p: p.b[V.HP] * 100 // max(1, p.b[V.HPMAX]))
            cure = next((sp for sp in (36, 71, 58, 3) if sp in spells), None)
            if cure and wounded: self.plan, self.plan_target = cure, wounded[0]
            if globes and self.plan is None:
                done = getattr(self, 'buffed', set())
                for sp in (112, 88, 42):
                    if sp in spells and (getattr(self, 'fight_no', 0), info['actor'], sp) not in done:
                        self.buffed = done | {(getattr(self, 'fight_no', 0), info['actor'], sp)}; self.plan = sp; break
                if self.plan is None and 94 in spells and enemies: self.plan, self.plan_target = 94, max(enemies, key=lambda e: e.b[V.HP])
            if actor.b[0x6C] == 3 and self.plan is None: return None
            if self.plan is None and enemies:
                for sp in Walk.AREA:
                    if sp in spells and max(near(pos(e), radius(sp), enemies) for e in enemies) >= 3: self.plan = sp; break
            if self.plan is None and enemies:
                single = next((sp for sp in (94, 49, 23, 15) if sp in spells), None)
                if single: self.plan, self.plan_target = single, max(enemies, key=lambda e: e.b[V.HP])
            if self.plan is not None: self.tried.add(key); return options.index('cast')
            if 'attack' in options and (key, 'attack') not in self.tried: self.tried.add((key, 'attack')); return options.index('attack')
            return options.index('guard') if 'guard' in options else None
        if kind == 'SPELL': return options.index(self.plan) if self.plan in options else None
        if kind == 'TARGET':
            last = len(options) - 1 if options and options[-1] in ('cancel', 'done') else None
            if getattr(self, 'plan_target', None) is not None:
                t = cb.index(self.plan_target)
                if t in options: self.plan_target = None; return options.index(t)
                if any(isinstance(o, tuple) for o in options) and pos(self.plan_target) in options: p = pos(self.plan_target); self.plan_target = None; return options.index(p)
                return last
            cells = [(i, o) for i, o in enumerate(options) if isinstance(o, tuple)]
            if cells:
                r = radius(self.plan) if self.plan else 1
                best = max(((near(o, r, enemies), i) for i, o in cells if not near(o, r, party)), default=None)
                return best[1] if best and best[0] else last
            ids = [(cb.chars[o].b[V.HP], i) for i, o in enumerate(options) if isinstance(o, int) and side(cb.chars[o]) != 0]
            return max(ids)[1] if ids else last
        return None

    CASTERS = ('CLERIC', 'PRIEST', 'NECROMANCER', 'WARLOCK', 'WIZARD', 'MAGE', 'DRIDER')
    def opening(self, kind, options, g, info, mode=None):
        from sm.titles.ssb import rec
        from sm.titles.ssb.units.shops import name
        mode = mode or self.modes.get(getattr(self, 'fight_no', 0), 'silence-hold-focus')
        if mode == 'casters': return Walk.caster_turn(self, kind, options, g, info)
        if mode == 'globe-casters': return Walk.caster_turn(self, kind, options, g, info, globes=True)
        cb = g.combat; side = lambda c: c.b[V.SIDE]
        enemies = [m for m in cb.chars if side(m) != 0 and m.b[V.ACTIVE]]
        casters = [m for m in enemies if any(w in name(m).upper() for w in Walk.CASTERS) and not rec.has_effect(m, 0x15)]
        ids = [cb.index(m) for m in casters]
        def near(p, r, who): return sum(1 for m in who if max(abs(cb.position(m)[0]-p[0]), abs(cb.position(m)[1]-p[1])) <= r)
        if kind == 'COMBAT_ACTION':
            actor = cb.chars[info['actor']]; key = (getattr(self, 'fight_no', 0), info['actor'], info.get('round'))
            self.plan = None
            if not casters: return None
            order = (25, 47, 34, 51, 23, 49) if mode == 'cluster' else (25, 23, 49)
            spells = [sp for sp in order if sp in cb.spells(actor)] if 'cast' in options else []
            if spells and key not in self.tried:
                self.tried.add(key); self.plan = spells[0]; return options.index('cast')
            if 'attack' in options and (key, 'attack') not in self.tried and any(cb.index(t) in ids for t in cb.attack_targets(actor)):
                self.tried.add((key, 'attack')); return options.index('attack')
            return None
        if kind == 'SPELL': return options.index(self.plan) if self.plan in options else None
        if kind == 'TARGET':
            last = len(options) - 1 if options and options[-1] in ('cancel', 'done') else None
            cells = [(i, o) for i, o in enumerate(options) if isinstance(o, tuple)]
            if cells:
                r = {47: 3, 34: 1}.get(self.plan, 1 if self.plan == 25 else 0)
                party = [c for c in cb.chars if side(c) == 0 and c.b[V.ACTIVE]]
                best = max(((near(o, r, casters), near(o, r, enemies), i) for i, o in cells if not (r and near(o, r, party))), default=None)
                return best[2] if best and best[0] else last
            picks = [(near(cb.position(cb.chars[o]), 1, casters), i) for i, o in enumerate(options) if o in ids]
            if picks: return max(picks)[1]
            return last
        return None

    def walk_answer(self, kind, options, g, **info):
        if not g.engines and self.recover_damage:
            if info.get('purpose')=='script damage': self.damage_heal=True
            if kind=='MOVE' and getattr(self,'damage_heal',False):
                self.damage_heal=False
                if any(c.b[V.STATUS] or c.b[V.HP]<c.b[V.HPMAX] for c in g.s.party):
                    return options.index('camp')
        if kind == 'INPUT': return 0
        if g.engines and self.rules is None:
            if kind not in host.DECISION_KINDS: self.stop(g, kind, 'outside host closed decision set')
            if 'purpose' in info:
                if kind == 'NUMBER': return info['max']
                if kind == 'STRING': return ''
            if kind == 'MENU' and info.get('action') == 'continue-battle':
                return options.index('end')
            if kind == 'COMBAT_ACTION':
                if 'quick' not in options: self.stop(g, kind, 'Quick is unavailable')
                return options.index('quick')
            if g.s.g.get('combat.active') or kind not in ('MOVE', 'MENU', 'NUMBER', 'STRING', 'PARLAY', 'WHO'):
                return 0
        if kind == 'SHOP':
            st = self.steps[min(self.i, len(self.steps) - 1)] if self.steps else {}
            if self.buyq is None or self.buyq[0] != self.i: self.buyq = (self.i, list(st.get('buy', [])))
            return self.buyq[1].pop(0) if self.buyq[1] else 0
        if kind in RESOLVED: resolve(kind, g); return 0
        if self.i >= len(self.steps): self.stop(g, kind, 'walkthrough exhausted before the finale')
        st = self.steps[self.i]
        if self.mq is None or self.mq[0] != self.i: self.mq = (self.i, list(st.get('menus', [])))
        if kind == 'MOVE':
            self.active_step = st['n']
            s = g.s
            if (s.dataset, s.block) != tuple(st['block']): self.stop(g, kind, 'the walkthrough expects block %d/%d' % tuple(st['block']))
            p = self.path(g, st['to'])
            if p is None: self.stop(g, kind, 'no walkable path to %r' % (st['to'],))
            ahead = s.dir
            for move in p:
                if move == 'forward': break
                ahead = (ahead + (6 if move == 'turn-left' else 2)) % 8
            if 'forward' in p and g.geo.passage(s, s.x, s.y, ahead) in (2, 3) and not s.g.get('bash', 1):
                def open_edges(q):
                    x, y, f = q; dx, dy = walk.DELTAS[f // 2]
                    nxt = [('turn-left', (x, y, (f + 6) % 8)), ('turn-right', (x, y, (f + 2) % 8))]
                    if g.geo.passage(s, x, y, f) == 1 and 0 <= x + dx < 16 and 0 <= y + dy < 16: nxt.append(('forward', (x + dx, y + dy, f)))
                    return nxt
                back = shortest_path((s.x, s.y, s.dir), lambda q: q[:2] != (s.x, s.y), open_edges)
                if back:
                    tries = self.__dict__.setdefault('door_returns', {}); key = (s.dataset, s.block, s.x, s.y, ahead)
                    tries[key] = tries.get(key, 0) + (back[0] == 'forward' or len(back) == 1)
                    if tries[key] > 12: self.stop(g, kind, 'held door at %d,%d cannot be opened by this party' % (s.x, s.y))
                    return options.index(back[0])
            if p: return options.index(p[0])
            self.i += 1
            if not st.get('act'): return self(kind, options, g, **info)
            return options.index(st['act'])
        if options is None:
            k = st.get('input')
            if k is None or k not in self.answers: self.stop(g, kind, 'an input the walkthrough step does not give')
            return self.answers[k]
        if len([o for o in options if o not in ('char-up', 'char-down', 'char-first')]) == 1: return 0
        if info.get('door'):
            return next((i for d in DOOR for i, o in enumerate(options) if o == d), options.index('Exit'))
        if self.mq[1]:
            i = self.mq[1].pop(0)
            if not 0 <= i < len(options): self.stop(g, kind, 'menu index %d out of range' % i, len(options))
            return i
        for want in st.get('pick', []):
            want = self.answers.get(want[1:], want) if want.startswith('@') else want
            for i, o in enumerate(options):
                if want.upper() in o.upper(): return i
        if 'default' in st: return st['default']
        self.stop(g, kind, 'a menu the walkthrough step does not cover', len(options))


class Finding(Stop): pass


EXPERT = os.path.join(ROOT, 'herdr', 'expert')
STRATEGIES_PATH = os.path.join(EXPERT, 'rosters.json')
STRATEGIES = {'rosters': json.load(open(STRATEGIES_PATH)) if os.path.exists(STRATEGIES_PATH) else {}}
def signature(monsters):
    c = Counter(m.rid for m in monsters if m.rid is not None)
    return 'MON1CHA ' + ' '.join('%d x%d' % (r, n) for r, n in sorted(c.items()))

KEY_SPELLS = {5: (115, 47), 0: (71, 36, 58)}
def key_spent(c):
    keys = KEY_SPELLS.get(c.b[0x6C])
    return bool(keys) and c.b[0x1A6] == 0 and not any(n in keys for n in c.b[0x1E:0x69]) and needs_memorize(c)

BUFF_PATH = os.path.join(EXPERT, 'buff_steps.json')
BUFF_STEPS = set(json.load(open(BUFF_PATH))) if os.path.exists(BUFF_PATH) else set()
BUFFS = {5: (112, 88, 85), 0: (42, 1), 3: (1,)}
def buff_plan(party):
    out, haste = [], False
    for i, c in enumerate(party):
        if c.b[0x1A6]: continue
        for sp in BUFFS.get(c.b[0x6C], ()):
            if sp in c.b[0x1E:0x69] and not (sp == 48 and haste): out.append((i, sp, i)); haste = haste or sp == 48
    return out

def needs_memorize(c):
    from sm.titles.ssb.units import magic
    if c.b[0x1A6] or 0 not in c.b[0x1E:0x69]: return False
    return any(c.b[0x70 + i] and magic.free_slots(c, i) for i in range(1, 118))

def take_back(s, casters_only=False):
    for c in s.party:
        if not casters_only or c.b[0x6C] in (0, 3, 5): c.b[V.CTRL] = 0

class _Sim:
    def __init__(self, game, seed, mode):
        import copy
        self._g = game; self.s = copy.deepcopy(game.s); self.s.seed = seed; self.geo = game.geo; self.engines = True; self.combat = None
        self.vm = V.VM(self.s, self.ask, game.geo); self.vm.host = self
        self.mode = mode; self.tried, self.plan, self.modes, self.buffed = set(), None, {}, set()
        if mode != 'quick': take_back(self.s)
        self.actions = []
    def __getattr__(self, k): return getattr(self._g, k)
    def ask(self, kind, options, **info):
        if kind == 'MENU' and info.get('action') == 'continue-battle': return options.index('end')
        if self.mode != 'quick' and kind in ('COMBAT_ACTION', 'SPELL', 'TARGET'):
            a = Walk.opening(self, kind, options, self, info, self.mode)
            if a is not None:
                if len(self.actions) < 40: self.actions.append('r%s %s:%s' % (self.s.g.get('8DC7'), _nm(self.combat.chars[info['actor']]) if 'actor' in info else '', options[a]))
                return a
        if kind == 'COMBAT_ACTION': return options.index('quick')
        return 0

OPENINGS = ('quick', 'silence-hold-focus', 'cluster', 'casters', 'globe-casters')
ACTIONS = {}
def choose_opening(game, cached=None, seeds=10):
    from sm.titles.ssb.units import combat
    if cached: return max(cached, key=lambda k: (cached[k][0], -cached[k][1])), cached
    scores = {}
    for mode in OPENINGS:
        wins = deaths = 0
        for k in range(seeds):
            sim = _Sim(game, (game.s.seed + 7919 * (k + 1)) & 0xFFFFFFFF, mode)
            try: combat.run(sim); crashed = False
            except Exception: crashed = True
            if k == 0: first_actions = list(sim.actions)
            if crashed: deaths += 6; continue
            d = sum(1 for c in sim.s.party if c.b[0x1A6] in (6, 7, 8)); deaths += d
            wins += d == 0 and not any(c.b[V.ACTIVE] for c in sim.s.monsters)
        scores[mode] = (wins, deaths); ACTIONS[mode] = first_actions
    return max(OPENINGS, key=lambda k: (scores[k][0], -scores[k][1])), scores

def _nm(c): return bytes(c.b[1:1 + min(c.b[0], 15)]).decode('latin1').strip()
def shep(line):
    with open(os.path.join(ROOT, 'local', 'maxrun.log'), 'a', encoding='utf-8') as f: f.write(time.strftime('%H:%M:%S ') + line + chr(10))

class RunWatch:
    def __init__(self, game, walk=None, seconds=20, started=None):
        from sm.titles.ssb import rec
        from sm.titles.ssb.units import combat, magic, shops
        self.game, self.walk, self.name = game, walk, shops.name
        self.started = time.monotonic() if started is None else started; self.seconds = seconds
        self.waited = 0; self.wait_start = None; self.finished = None; self.repeats = [None, 0, None, 0]
        self.recent_prompts, self.prompt_counts = deque(), Counter()
        self.ages = {id(c): rec.rdw(c.b, 0x6E) for c in game.s.party}
        self.fights = self.won = 0; self.fight = ''; self.hit = 'no damaging attack recorded'; self.rounds = []
        self.last_kind = 'BOOT'
        self.last_prompt = prompt_line('BOOT', None, {}, game)
        self.start_code = combat.run.__code__; self.finish_code = combat.Combat.finish.__code__
        self.ask_code = host.Game.ask.__code__; self.word_codes = {rec.wrw.__code__, V.wrw.__code__}
        self.damage_codes = {combat.Combat.apply_damage.__code__, magic._Magic.damage.__code__}
        self.kill_codes = {combat.Combat.kill.__code__, magic._Magic.kill.__code__}
        self.codes = self.damage_codes | self.word_codes | {self.finish_code, combat.Combat.kill.__code__,
            magic._Magic.kill.__code__, combat.Combat.end_round.__code__, combat.Combat.do_turn.__code__, V.VM.advance_clock.__code__}

    def place(self, kind=None):
        g = self.game; w = self.walk
        step = w.steps[min(w.i, len(w.steps) - 1)]['n'] if w is not None and w.steps else 'replay'
        if kind == 'COMBAT' and w is not None: step = getattr(w, 'active_step', step)
        return 'step %s block %d/%d pc %04X kind %s' % (step, g.s.dataset, g.s.block, getattr(g.vm, 'at', 0), kind or self.last_kind)

    def report(self, why):
        s = self.game.s
        hp = ', '.join('%s %d/%d' % (self.name(c), c.b[0x1B5], c.b[0x70]) for c in s.party)
        return '%s; %s; round %d; %s; party HP %s' % (why, self.fight or self.place(), s.g.get('8DC7', 0), self.hit, hp)

    def elapsed(self):
        now = self.finished if self.finished is not None else time.monotonic()
        return now - self.started - self.waited - (now - self.wait_start if self.wait_start is not None else 0)

    def guard(self, kind, options, info):
        self.last_prompt = prompt_line(kind, options, info, self.game)
        previous=self.game.trace[-1][6] if self.game.trace else None
        keys = [(kind, repr(options), self.game.s.hash(self.game.vm), repr(previous)),
                (kind, repr(options), repr({k: info[k] for k in sorted(info) if k != 'round'}), repr(previous))]
        for i, (key, maximum) in enumerate(zip(keys, (5, 50))):
            n = 2*i; self.repeats[n + 1] = self.repeats[n + 1] + 1 if self.repeats[n] == key else 1; self.repeats[n] = key
            if self.repeats[n + 1] >= maximum:
                raise Finding('loop guard: %d consecutive %s; %s' % (maximum, 'identical states' if i == 0 else 'prompts ignoring round', self.last_prompt))
        if kind in ('CAMP_MENU', 'SPELL', 'TARGET') and not self.game.s.g.get('combat.active'): return
        key = keys[1]; self.recent_prompts.append(key); self.prompt_counts[key] += 1
        if len(self.recent_prompts) > 200:
            expired = self.recent_prompts.popleft(); self.prompt_counts[expired] -= 1
            if not self.prompt_counts[expired]: del self.prompt_counts[expired]
        if self.prompt_counts[key] >= 50:
            raise Finding('cycle guard: same prompt 50 times within last 200 decisions (ignoring round); ' + self.last_prompt)

    def check(self):
        from sm.titles.ssb import rec
        for c in self.game.s.party:
            age = rec.rdw(c.b, 0x6E)
            if c.b[0x1A6] in (6, 7, 8): raise Finding(self.report('%s is %s' % (self.name(c), {6: 'dead', 7: 'turned to stone', 8: 'gone'}[c.b[0x1A6]])))
            if age > self.ages.setdefault(id(c), age): raise Finding(self.report('%s aged from %d to %d' % (self.name(c), self.ages[id(c)], age)))
        if self.elapsed() >= self.seconds: raise Finding('time cap %g s; %s; last decision %s' % (self.seconds, self.place(), self.last_prompt))

    def observe(self, frame, event, result):
        code = frame.f_code
        if event == 'call':
            if code is self.ask_code:
                self.last_kind = frame.f_locals['kind']
                if self.walk is not None: self.guard(self.last_kind, frame.f_locals['options'], frame.f_locals['info'])
                else: self.last_prompt = prompt_line(self.last_kind, frame.f_locals['options'], frame.f_locals['info'], self.game)
                self.check()
                if self.last_kind not in host.DECISION_KINDS: raise Stop(self.place() + ': outside host closed decision set')
            elif code is self.start_code: self.on_start()
            return
        if event != 'return' or code not in self.codes: return
        if code in self.word_codes and frame.f_locals['o'] != 0x6E: return
        if code in self.damage_codes | self.kill_codes:
            local = frame.f_locals; self.on_hit(local.get('character', local.get('c')), local.get('n', local.get('amount', 0)))
        self.check()
        if code is self.finish_code: self.on_finish(result)

    def on_ask(self, kind, options, info):
        self.last_kind = kind
        if self.walk is not None: self.guard(kind, options, info)
        else: self.last_prompt = prompt_line(kind, options, info, self.game)
        self.check()
        if kind not in host.DECISION_KINDS: raise Stop(self.place() + ': outside host closed decision set')

    def on_start(self):
        if True:
            if True:
                self.fights += 1
                entry = dict(boundary(self.game), tries=[])
                if hasattr(self.game, 'replay_journal'):
                    if self.fights > len(self.game.replay_journal): replay_fault(self.game, 'extra fight')
                    recorded = self.game.replay_journal[self.fights - 1]
                    check_boundary(self.game, recorded)
                    if recorded['take_back']: take_back(self.game.s)
                    for _ in range(recorded['draws']): self.game.s.random(0)
                shep('fight %d START party %s' % (self.fights, ' '.join('%s %d/%d%s' % (_nm(c), c.b[0x1B5], c.b[0x70], '' if not c.b[0x1A6] else ' st%d' % c.b[0x1A6]) for c in self.game.s.party)))
                if self.walk is not None:
                    self.walk.fight_no = self.fights; sig = signature(self.game.s.monsters)
                    if not hasattr(self.walk, 'fight_step'): self.walk.fight_step = {}
                    self.walk.fight_step[self.fights] = getattr(self.walk, 'active_step', None)
                    self.walk.rosters[self.fights] = sig
                    known = STRATEGIES['rosters'].get(sig, {}).get('opening')
                    if known and known != 'quick':
                        self.walk.strategy.add(self.fights); self.walk.modes[self.fights] = known
                        shep('fight %d roster known (%s): opening %s' % (self.fights, sig, known))
                    elif not known and any(any(w in self.name(m).upper() for w in Walk.CASTERS) for m in self.game.s.monsters):
                        t = time.monotonic(); best, scores = choose_opening(self.game, self.walk.sims.get((sig, self.fights))); self.walk.sims[(sig, self.fights)] = scores; self.walk.sims[sig] = scores
                        self.waited += time.monotonic() - t
                        if best != 'quick': self.walk.strategy.add(self.fights); self.walk.modes[self.fights] = best
                        names = ', '.join('%s x%d' % (k, v) for k, v in sorted(Counter(self.name(m) for m in self.game.s.monsters).items()))
                        shep('fight %d %s [%s] simulated %s -> %s (%.1fs)' % (self.fights, sig, names, scores, best, time.monotonic() - t))
                        for m in OPENINGS[1:]: shep('   %s first sim actions: %s' % (m, ' | '.join(ACTIONS.get(m, [])[:14]) or 'none'))
                    if self.fights in self.walk.strategy and self.walk.modes.get(self.fights, 'silence-hold-focus') != 'quick': take_back(self.game.s)
                    if self.fights in self.walk.forced:
                        self.walk.strategy.add(self.fights); self.walk.modes[self.fights] = self.walk.forced[self.fights]
                        shep('fight %d strategy change after the retry budget: opening %s' % (self.fights, self.walk.forced[self.fights])); take_back(self.game.s)
                    for _ in range(getattr(self.walk, 'dice', {}).get(self.fights, 0)): self.game.s.random(0)
                    if hasattr(self.walk, 'budget'):
                        if not hasattr(self.game, 'retry_journal'): self.game.retry_journal = []
                        entry.update(take_back=(self.fights in self.walk.strategy and self.walk.modes.get(self.fights, 'silence-hold-focus') != 'quick')
                                     or self.fights in self.walk.forced, draws=self.walk.dice.get(self.fights, 0))
                        self.game.retry_journal.append(entry)
                self.fight = '%s monsters %s' % (self.place('COMBAT'), ', '.join(self.name(c) for c in self.game.s.monsters))
                self.hit = 'no damaging attack recorded'

    def on_hit(self, target, amount):
        if target is None: return
        g = self.game; attacker = g.s.selc(); cb = getattr(g, 'combat', None)
        try: attacker = cb.chars[g.s.g['combat.order'][g.s.g['combat.cursor']]]
        except Exception: pass
        if True:
            if amount > 0 or target.b[0x1A6] in (6, 8):
                self.hit = '%s %s %s; damage %d' % (self.name(attacker) if attacker else 'unknown attacker',
                    'killed' if target.b[0x1A6] in (6, 8) else 'hit', self.name(target), amount)
        self.check()

    def on_finish(self, result):
        if True:
            g = self.game; rounds = g.s.g.get('8DC7', 0); self.rounds.append(rounds)
            shep('fight %d %s: result %s | rounds %d%s | party %s' % (self.fights, ', '.join(sorted({_nm(c) for c in g.s.monsters})), result, rounds,
                '',
                ' '.join('%s %d/%d%s' % (_nm(c), c.b[0x1B5], c.b[0x70], '' if not c.b[0x1A6] else ' st%d' % c.b[0x1A6]) for c in g.s.party)))
            down = [c for c in g.s.party if c.b[0x1A6] != 0]
            healer = any(c.b[0x1A6] == 0 and (c.b[0x6C] in (0, 3) or any(n in (36, 71, 58, 3) for n in c.b[0x1E:0x69])) for c in g.s.party)
            if result in (0, 1) and down and not healer and (self.walk is not None and hasattr(self.walk, 'budget') or hasattr(g, 'replay_journal')):
                raise Finding(self.report('won, but %d members are down and no conscious member can cure them' % len(down)))
            if result in (0, 1): self.won += 1
            else: raise Finding(self.report('party lost the fight (result %02X)' % (result or 0)))


def observed_play(g, walk=None, seconds=20, limit=100_000, started=None):
    watch = g.run_watch = RunWatch(g, walk, seconds, started); previous = sys.getprofile()
    undo = install_watch(watch)
    try:
        result = g.play(limit=limit)
        watch.check()
        if result != 'DONE': result = 'BLOCKED %s: decision limit %d reached' % (watch.place(), limit)
    except Finding as e: result = 'STOP %s' % e
    except (Stop, V.Halt, ValueError, IndexError) as e: result = 'BLOCKED %s: %s' % (watch.place(), e)
    finally: undo(); watch.finished = time.monotonic()
    return result

def install_watch(watch):
    from sm.titles.ssb import rec
    from sm.titles.ssb.units import combat, magic
    g0 = watch.game; saved = []; calendar = False
    def patch(owner, name, make):
        old = getattr(owner, name); saved.append((owner, name, old)); setattr(owner, name, make(old))
    def mine(obj): return getattr(obj, 'game', obj) is g0
    patch(host.Game, 'ask', lambda old: lambda self, kind, options, **info: (watch.on_ask(kind, options, info) if self is g0 else None, old(self, kind, options, **info))[1])
    patch(combat, 'run', lambda old: lambda game: (watch.on_start() if game is g0 else None, old(game))[1])
    for owner in (combat.Combat, magic._Magic):
        patch(owner, 'kill', lambda old: lambda self, c, *a, **k: (lambda r: (watch.on_hit(c, 0), watch.check(), r)[2] if mine(self) else r)(old(self, c, *a, **k)))
    patch(combat.Combat, 'apply_damage', lambda old: lambda self, c, amount: (lambda r: (watch.on_hit(c, amount), watch.check(), r)[2] if mine(self) else r)(old(self, c, amount)))
    patch(magic._Magic, 'damage', lambda old: lambda self, c, amount, *a, **k: (lambda r: (watch.on_hit(c, amount), watch.check(), r)[2] if mine(self) else r)(old(self, c, amount, *a, **k)))
    patch(combat.Combat, 'finish', lambda old: lambda self: (lambda r: (watch.check(), watch.on_finish(r), r)[2] if mine(self) else r)(old(self)))
    for name in ('end_round', 'do_turn'):
        patch(combat.Combat, name, lambda old: lambda self, *a: (lambda r: (watch.check(), r)[1] if mine(self) else r)(old(self, *a)))
    def age_write(old, birthday=False):
        def write(b, o, v):
            result = old(b, o, v)
            if o == 0x6E:
                for c in g0.s.party:
                    if c.b is b:
                        if birthday and calendar: watch.ages[id(c)] = rec.rdw(b, o)
                        else: watch.check()
                        break
            return result
        return write
    patch(rec, 'wrw', age_write)
    patch(V, 'wrw', lambda old: age_write(old, birthday=True))
    def clock_hook(old):
        def advance(self, *a):
            nonlocal calendar
            previous = calendar; calendar = self is g0.vm
            try:
                result = old(self, *a)
                if self is g0.vm: watch.check()
                return result
            finally: calendar = previous
        return advance
    patch(V.VM, 'advance_clock', clock_hook)
    def undo():
        for owner, name, old in reversed(saved): setattr(owner, name, old)
    return undo


def maxrun(dice=None, strategy=None, sims=None, forced=None, budget=None, seconds=20, seed=0, directory=None):
    from sm.titles.ssb import rec
    start = time.monotonic()
    directory = directory or os.path.join(ROOT, 'local', 'saves')
    rec.max_party(root=directory)
    steps = [w for t in ('T1', 'T2', 'T2b', 'T3', 'T3b') for w in json.load(open(os.path.join(ROOT, 'herdr', 'route', 'steps_%s.json' % t)))]
    answers = json.load(open(os.path.join(ROOT, 'local', 'answers.json')))
    w = Walk(steps, answers, os.path.join(ROOT, 'local', 'maxrun_rules.json')); w.dice, w.strategy, w.rosters = dict(dice or {}), set(strategy or ()), {}
    w.modes, w.tried, w.plan, w.sims, w.forced = {}, set(), None, dict(sims or {}), dict(forced or {})
    w.fight_tries = {}
    if budget: w.budget = budget
    g = host.Game(w, slot='M', engines=True, directory=directory)
    g.initial_seed = g.s.seed = seed & 0xFFFFFFFF
    g.maxrun = True
    return observed_play(g, w, seconds=seconds, started=start), g

def boundary(game):
    return dict(at=len(game.trace), hash=game.s.hash(game.vm))


def replay_fault(game, reason):
    game.replay_error = 'retry replay: ' + reason
    raise Stop(game.replay_error)


def check_boundary(game, expected):
    if boundary(game) != {k: expected[k] for k in ('at', 'hash')}:
        replay_fault(game, 'boundary differs at decision %d (expected %d)' % (len(game.trace), expected['at']))


def retrying(orig):
    import copy
    from sm.titles.ssb import rec
    def run(game):
        w, watch = game.player, getattr(game, 'run_watch', None)
        if watch is None or not hasattr(w, 'budget') or game is not watch.game: return orig(game)
        f = watch.fights; snap = copy.deepcopy(game.s); tries = 0; won0 = watch.won
        entries = game.retry_journal[f - 1]['tries']
        while True:
            try:
                res = orig(game)
                entries.append(dict(boundary(game), failed=False, result=res))
                if tries: shep('fight %d won on try %d (opening %s)' % (f, tries + 1, w.modes.get(f, 'quick') if f in w.strategy else 'quick'))
                w.fight_tries[f] = tries + 1; return res
            except Finding as e:
                entry = dict(boundary(game), failed=True); entries.append(entry)
                if 'time cap' in str(e): raise
                tries += 1; w.fight_tries[f] = tries
                if tries >= 2 * w.budget: raise
                shep('fight %d try %d lost: %s' % (f, tries, str(e).split(';')[0][:90]))
                game.s.__dict__.update(copy.deepcopy(snap).__dict__); game.combat = None; watch.won = won0
                watch.ages = {id(c): rec.rdw(c.b, 0x6E) for c in game.s.party}; w.tried = set()
                sig = w.rosters.get(f)
                if tries == 1 and (sig, f) not in w.sims:
                    t = time.monotonic(); best, scores = choose_opening(game); w.sims[(sig, f)] = w.sims[sig] = scores; watch.waited += time.monotonic() - t
                    shep('fight %d lost once: simulated %s -> %s' % (f, scores, best))
                    if scores[best][0] <= 5 and getattr(w, 'fight_step', {}).get(f) is not None:
                        BUFF_STEPS.add(w.fight_step[f]); json.dump(sorted(BUFF_STEPS, key=str), open(BUFF_PATH, 'w'))
                        shep('step %s learned as a hard fight: pre-fight buffs on the next run' % w.fight_step[f])
                    if best != 'quick': w.strategy.add(f); w.modes[f] = best; take_back(game.s)
                if tries == w.budget:
                    picked = w.modes.get(f, 'quick') if f in w.strategy else 'quick'; sc = w.sims.get((sig, f)) or {}
                    ranked = sorted((m for m in OPENINGS if m != picked), key=lambda m: (-(sc.get(m, (0, 99))[0]), sc.get(m, (0, 99))[1]))
                    w.strategy.add(f); w.modes[f] = ranked[0]; take_back(game.s)
                    shep('fight %d strategy change after %d tries: opening %s' % (f, tries, w.modes[f]))
                elif f in w.strategy and w.modes.get(f) != 'quick': take_back(game.s)
                entry.update(take_back=tries == w.budget or f in w.strategy and w.modes.get(f) != 'quick', draws=tries % w.budget)
                for _ in range(tries % w.budget): game.s.random(0)
                pass
    return run


def replaying(orig):
    import copy
    from sm.titles.ssb import rec
    def run(game):
        watch = getattr(game, 'run_watch', None)
        if watch is None or watch.game is not game: return orig(game)
        expected = game.replay_journal[watch.fights - 1]['tries']
        snap, won0 = copy.deepcopy(game.s), watch.won
        for entry in expected:
            error = None
            try: result = orig(game)
            except Finding as caught: error = caught
            check_boundary(game, entry)
            if bool(error) != entry['failed'] or error is None and result != entry['result']:
                replay_fault(game, 'fight outcome differs at decision %d' % len(game.trace))
            if 'draws' not in entry:
                game.replay_consumed = watch.fights
                if error is not None: raise error
                return result
            game.s.__dict__.update(copy.deepcopy(snap).__dict__); game.combat = None; watch.won = won0
            watch.ages = {id(c): rec.rdw(c.b, 0x6E) for c in game.s.party}
            if entry['take_back']: take_back(game.s)
            for _ in range(entry['draws']): game.s.random(0)
        replay_fault(game, 'fight journal has no terminal outcome')
    return run

def maxrun_retry(budget=20, seconds=20, seed=0, directory=None):
    from sm.titles.ssb.units import combat
    t0 = time.monotonic(); orig = combat.run; combat.run = retrying(orig)
    try:
        for attempt in range(4):
            known = set(BUFF_STEPS)
            shep('=== maxrun attempt %d (budget %d per opening, in-process retries; buff steps %s)' % (attempt + 1, budget, sorted(BUFF_STEPS, key=str)))
            r, g = maxrun(budget=budget, seconds=seconds, seed=seed, directory=directory)
            if not r.startswith('STOP') or 'time cap' in r or BUFF_STEPS == known: break
    finally: combat.run = orig
    w = g.player; tries = {f: n for f, n in w.fight_tries.items() if n > 1 or (f == g.run_watch.fights and r.startswith('STOP'))}
    for f, n in sorted(tries.items()):
        sig = w.rosters.get(f); won = not (f == g.run_watch.fights and r.startswith('STOP'))
        if sig: STRATEGIES['rosters'][sig] = dict(opening=w.modes.get(f, 'quick') if f in w.strategy else 'quick', tries=n, won=won,
                                                 simulated=w.sims.get(sig), date=time.strftime('%Y-%m-%d'), title='SSB')
    for f in w.strategy:
        sig = w.rosters.get(f)
        if sig and sig not in STRATEGIES['rosters']: STRATEGIES['rosters'][sig] = dict(opening=w.modes.get(f), tries=1, won=True, simulated=w.sims.get(sig), date=time.strftime('%Y-%m-%d'), title='SSB')
    os.makedirs(os.path.join(EXPERT, 'log'), exist_ok=True)
    json.dump(STRATEGIES['rosters'], open(STRATEGIES_PATH, 'w'), indent=1, sort_keys=True)
    rd = g.run_watch.rounds
    info = dict(seconds=round(time.monotonic() - t0, 1), fights_won=g.run_watch.won, avg_rounds=round(sum(rd) / len(rd), 2) if rd else None,
                retries=sum(n - 1 for n in w.fight_tries.values()), strategy_fights=sorted(w.strategy))
    with open(os.path.join(EXPERT, 'log', 'SSB_%s.log' % time.strftime('%Y%m%d_%H%M')), 'w') as fh:
        fh.write('%s | result: %s' % (info, r.split(';')[0][:60]) + chr(10))
        for k in sorted(w.rosters): fh.write('fight %d %s tries %d opening %s' % (k, w.rosters[k], w.fight_tries.get(k, 1), w.modes.get(k, 'quick') if k in w.strategy else 'quick') + chr(10))
    step = g.player.steps[min(g.player.i, len(g.player.steps) - 1)]['n'] if g.player.steps else '?'
    end = 'END %s | fights won %d | furthest step %s | play %.1f s | %s' % (r.split(' ')[0], g.run_watch.won, step,
          (g.run_watch.finished or time.monotonic()) - g.run_watch.started - g.run_watch.waited, r[:160])
    shep('=== maxrun end: %s | %s' % (end, info))
    os.makedirs(os.path.join(ROOT, 'local', 'logs'), exist_ok=True); runs = os.path.join(EXPERT, 'log')
    n = 1 + max([int(f[4:7]) for f in os.listdir(runs) if f.startswith('run-')] or [0])
    full = open(os.path.join(ROOT, 'local', 'maxrun.log'), encoding='utf-8').read()
    open(os.path.join(ROOT, 'local', 'logs', 'run-%03d.log' % n), 'w', encoding='utf-8').write(end + chr(10) + full)
    with open(os.path.join(runs, 'run-%03d.log' % n), 'w') as fh:
        fh.write(end.split(' | ')[0:4] and ' | '.join(end.split(' | ')[:4]) + chr(10))
        fh.write('%s' % {k: v for k, v in info.items()} + chr(10))
        for k in sorted(w.rosters): fh.write('fight %d %s tries %d opening %s' % (k, w.rosters[k], w.fight_tries.get(k, 1), w.modes.get(k, 'quick') if k in w.strategy else 'quick') + chr(10))
    info['end'] = end
    return r, g, info

def play(steps=None, answers=None, slot='A', *, recover_damage=True):
    if steps is None: steps, answers = load_steps()
    w = Walk(steps, answers or {}, recover_damage=recover_damage); g = host.Game(w, slot)
    from sm.engine import play as execute
    from sm.titles import ssb
    try: r = execute(g, w, profile=ssb, limit=500_000)
    except (Stop, V.Halt) as e: r = 'STOP %s' % e
    g.step = steps[min(w.i, len(steps) - 1)]['n'] if steps else None
    return r, g

def test():
    r, g = play([{'n': 0, 'block': [1, 16], 'to': [5, 3], 'act': None}], {})
    assert r.startswith('STOP step end: walkthrough exhausted'), r
    assert (g.s.x, g.s.y) == (5, 3), (g.s.x, g.s.y)
    test_maxrun_policy()
    test_model_prompts()
    test_retry_replay()


def test_model_prompts():
    import tempfile, threading
    from sm.titles.ssb.units._combat_test import fixture
    g, _ = fixture(); g.engines = True; g.s.g['combat.active'] = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); w = Walk([], {}, root / 'maxrun_rules.json'); g.run_watch = RunWatch(g, w)
        def respond():
            while not (root / 'ask.json').exists(): time.sleep(0.001)
            time.sleep(0.06)
            write_json(root / 'answer.json', dict(answer=1, reason='Leave the synthetic shop',
                rule=dict(kind='SHOP_MENU', options=['buy', 'exit'], answer={'option': 'exit'})))
        worker = threading.Thread(target=respond, daemon=True); worker.start()
        assert w('SHOP_MENU', ['buy', 'exit'], g, place='shop') == 1
        worker.join(timeout=1); assert not worker.is_alive()
        assert w.model_answers == 1 and g.run_watch.waited >= 0.05 and not (root / 'ask.json').exists()
        elapsed = g.run_watch.elapsed(); assert elapsed < time.monotonic() - g.run_watch.started - 0.05
        g.s.block += 1
        assert w('SHOP_MENU', ['buy', 'exit'], g, place='shop') == 1 and w.model_answers == 1, 'rule must generalize across locations'
        assert len((root / 'maxrun_answers.log').read_text().splitlines()) == 2
        try: w.validate_rule(dict(kind='MENU', block=33, options=['a'], answer=0))
        except ValueError: pass
        else: raise AssertionError('positional rule accepted')
        w.rules += [dict(kind='LIST', purpose=p, answer={'each_then': None}) for p in ('take money', 'take item')]
        g.player = w; g.s.sel = 0; g.s.treasure_money = [20, 0, 0, 0, 0, 0, 0]
        item = bytearray(67); item[0x2E] = 5; item[0x37] = 1; g.s.treasure_items = [item]
        from sm.titles.ssb.units import shops
        from unittest.mock import patch
        with patch.object(shops, 'room', return_value=0): shops.take(g)
        assert g.trace[-1][1] == 'SHOP_MENU' and g.trace[-1][6] == 2, 'full receiver did not exit Take'
        assert g.s.treasure_money[0] == 20 and len(g.s.treasure_items) == 1, 'player changed treasure instead of choosing'
        outer = ['view','take','pool','share','exit','char-up','char-down']
        assert w('SHOP_MENU',outer,g,purpose='treasure')==1
        assert w('SHOP_MENU',outer,g,purpose='treasure')==4, 'unchanged pile reopened forever'
        g.s.treasure_money[0]-=1
        assert w('SHOP_MENU',outer,g,purpose='treasure')==1, 'changed pile was not offered another take'
        assert w('SHOP_MENU',['yes','no'],g,purpose='treasure leave')==1
        w.heal_plan=(36,0);w.heal_asked=False
        assert w.camp_answer('SPELL',[3,36,'cancel',23],g,{})==1
        assert w.camp_answer('SPELL',[3,36,'cancel',23],g,{})==2, 'planned cure did not return for reassessment'
        w.heal_plan=None
        assert w.camp_answer('SPELL',['done',36,3],g,{'purpose':'memorize'})==0, 'selected an unavailable grimoire row'
        assert w.camp_answer('SPELL',['exit'],g,{'purpose':'memorize summary'})==0
        g.s.g['combat.active'] = 1
        assert w('NUMBER', None, g, spell=115, min=0, max=50, at=0x5D90) == 0
        w.fight_no=1;w.strategy={1};w.modes={1:'cluster'}
        assert w('MENU',['yes','no'],g,action='abort-spell')==0
    for maximum in (5, 50):
        watch = RunWatch(g)
        for n in range(maximum):
            if maximum == 50: g.s.g['8DC7'] = n
            try: watch.guard('MENU', ['a', 'b'], {'round': n} if maximum == 50 else {})
            except Finding as e:
                assert n == maximum - 1 and str(maximum) in str(e) and "options ['a', 'b']" in str(e), str(e)
                break
        else: raise AssertionError('loop guard did not stop')
    watch=RunWatch(g);old_trace=g.trace[:]
    for index in range(100):
        g.trace.append((index,'LIST',1,16,0,'',index))
        watch.guard('LIST',list(range(100))+[None],{'purpose':'take item'})
    g.trace[:]=old_trace
    watch = RunWatch(g)
    for n in range(99):
        g.s.g['8DC7'] = n
        try: watch.guard('MENU', ['a' if n % 2 == 0 else 'b'], {'round': n})
        except Finding as e:
            assert n == 98 and '50 times within last 200 decisions' in str(e), str(e)
            break
    else: raise AssertionError('alternating prompt cycle was missed')
    watch = RunWatch(g)
    for n in range(298):
        option = 'a' if n < 98 and n % 2 == 0 else 'unique %d' % n
        watch.guard('MENU', [option], {'round': n})
    for n in range(49):
        watch.guard('MENU', ['a'], {'round': n})
        watch.guard('MENU', ['new %d' % n], {'round': n})
    assert len(watch.recent_prompts) == 200 and max(watch.prompt_counts.values()) == 49, 'expired prompts still counted'
    watch = RunWatch(g); watch.started -= 21
    try: watch.check()
    except Finding as e: assert 'time cap 20 s' in str(e) and 'last decision' in str(e)
    else: raise AssertionError('time cap did not stop')


def test_retry_replay():
    import copy
    from unittest.mock import patch
    from sm.titles.ssb.units import combat as C, magic
    from sm.titles.ssb.units._combat_test import fixture
    def make():
        g, _ = fixture(); g.engines = True; g.s.seed = 0; g.s.party[0].b[V.CTRL] = 1
        return g
    for outcome in ('win', 'dead', 'nohealer'):
        def fight(g):
            g.ask('COMBAT_ACTION', ['quick'], at=0x0A05)
            if g.s.random(65535) == 0 or outcome == 'dead': magic._Magic(g).kill(g.s.party[0])
            if outcome == 'nohealer':
                g.s.party[0].b[V.STATUS] = 4
                g.run_watch.on_finish(0)
            return 0
        g = make(); w = Walk([], {}); g.player = w
        w.budget = 2; w.dice = {}; w.strategy = {1}; w.modes = {1: 'casters'}; w.forced = {}; w.rosters = {}
        w.fight_tries = {}; w.sims = {(signature(g.s.monsters), 1): {}}; w.tried = set()
        def play(limit):
            C.run(g); return 'DONE'
        with patch.object(C, 'run', retrying(fight)), patch.object(g, 'play', side_effect=play): recorded = observed_play(g, w)
        journal = copy.deepcopy(g.retry_journal); expected = g.s.hash(g.vm)
        def again(entries):
            h = make(); h.player = lambda *a, **k: 0
            h.replay_journal, h.replay_consumed = entries, 0
            def play_again(limit):
                C.run(h); return 'DONE'
            with patch.object(C, 'run', replaying(fight)), patch.object(h, 'play', side_effect=play_again): result = observed_play(h)
            return result, h
        result, h = again(journal)
        assert result == recorded and h.trace == g.trace and h.s.hash(h.vm) == expected, (result, recorded)
        assert h.replay_consumed == 1 and not hasattr(h, 'replay_error')
        broken = copy.deepcopy(journal); broken[0]['tries'][0]['draws'] = 0
        _, h = again(broken)
        assert hasattr(h, 'replay_error'), 'missing retry RNG advance was accepted'


def test_maxrun_policy():
    from unittest.mock import patch
    from sm.titles.ssb import rec
    from sm.titles.ssb.units._combat_test import fixture
    g, combat = fixture(); g.engines = True; w = Walk([], {})
    assert w('COMBAT_ACTION', ['attack', 'quick', 'done'], g) == 1
    assert w('MENU', ['continue', 'end'], g, action='continue-battle') == 1
    for kind in ('TARGET', 'SPELL', 'LIST', 'CAMP_MENU', 'SHOP_MENU', 'ACK'):
        assert w(kind, ['first', 'second'], g) == 0
    try: w('UNKNOWN_ENGINE_KIND', ['first'], g)
    except Stop as e: assert 'UNKNOWN_ENGINE_KIND' in str(e) and 'closed decision set' in str(e)
    else: raise AssertionError('unknown kind accepted')
    from sm.titles.ssb.units import shops
    g.s.g['combat.active'] = 0; g.s.sel = 0
    w = Walk([{'n': 'input', 'input': 'script'}], {'script': 7}); g.player = w
    g.s.treasure_money = [20, 0, 0, 0, 0, 0, 0]; shops.take(g)
    assert shops.coins(g.s.party[0])[0] == 20 and not any(g.s.treasure_money)
    assert [t[6] for t in g.trace if t[1] == 'NUMBER'] == [20]
    assert w('NUMBER', None, g, purpose='rest hours', max=23) == 23
    w.heal_plan = (58, 0)
    assert w.camp_answer('TARGET', [0, None], g, {'purpose': 'party member'}) == 0, 'ov18:1253 cure target lost at None exit'
    assert w('STRING', None, g, purpose='engine input') == ''
    assert w('NUMBER', None, g) == 7
    w.answers['script'] = 'script text'; assert w('STRING', None, g) == 'script text'
    w.answers.clear()
    try: w('NUMBER', None, g)
    except Stop as e: assert 'an input the walkthrough step does not give' in str(e)
    else: raise AssertionError('unspecified script input accepted')
    from sm.titles.ssb.units import combat as C
    g, combat = fixture(); g.engines = True; g.player = Walk([], {})
    g.s.monsters[0].b[0x1B5] = 1
    def battle(limit): C.run(g); return 'DONE'
    with patch.object(g, 'play', side_effect=battle): result = observed_play(g)
    assert result == 'DONE' and (g.run_watch.fights, g.run_watch.won) == (1, 1), result
    assert g.trace[-1][1] == 'MENU' and g.trace[-1][6] == 1, 'won fight did not choose End'
    for aged in (False, True):
        g, combat = fixture(); c = g.s.party[0]; c.b[:7] = bytes([6]) + b'Victim'
        g.s.monsters[0].b[:7] = bytes([6]) + b'Killer'; g.s.sel = 1
        old_profile = sys.getprofile()
        def action(limit):
            if aged: rec.wrw(c.b, 0x6E, 1)
            else: combat.apply_damage(c, 55)
            raise AssertionError('run continued after the first fatal change')
        with patch.object(g, 'play', side_effect=action): result = observed_play(g)
        assert result.startswith('STOP '), result
        assert ('aged from 0 to 1' if aged else 'Killer killed Victim; damage 55') in result, result
        assert sys.getprofile() is old_profile, 'profiler not restored'
    g, combat = fixture(); c = g.s.party[0]
    old_writers = rec.wrw, V.wrw
    def birthdays(limit):
        foreign = bytearray(c.b); rec.wrw(foreign, 0x6E, 99)
        g.s.r0[0xCC] = 99; g.vm.advance_clock(1, 6)
        assert rec.rdw(c.b, 0x6E) == 1
        V.wrw(c.b, 0x6E, 2)
        raise AssertionError('non-calendar vm age write was missed')
    with patch.object(g, 'play', side_effect=birthdays): result = observed_play(g)
    assert 'aged from 1 to 2' in result, result
    assert (rec.wrw, V.wrw) == old_writers, 'age hooks not restored'
    from sm.titles.ssb.units import magic
    g, combat = fixture(); c = g.s.party[0]
    def haste(limit):
        magic._Magic(g).callback(c, bytearray([0x27, 1, 0, 0, 0, 0, 0, 0, 0]))
        raise AssertionError('Haste continued after aging')
    with patch.object(g, 'play', side_effect=haste): result = observed_play(g)
    assert 'aged from 0 to 1' in result, result
