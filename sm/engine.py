"""Shared decision protocol and headless/session execution for title profiles.

Profiles keep their native loop, rules and hash serialization. The core owns
request/reply delivery, input validation, limits and the transport watchdog.
"""
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Thread


def legal_choice(options, value, *, strict=False):
    integer = type(value) is int if strict else isinstance(value, int)
    return options is None or integer and 0 <= value < len(options)


@dataclass(frozen=True)
class Decision:
    kind: str
    options: tuple = None
    info: dict = field(default_factory=dict)

    def validate(self, value, *, strict=False):
        if not legal_choice(self.options, value, strict=strict):
            raise ValueError('decision choice outside options')
        integer = type(value) is int if strict else isinstance(value, int)
        if self.kind == 'NUMBER' and (not integer or not 0 <= value <= 65535):
            raise ValueError('number outside unsigned word range')
        if self.kind == 'STRING' and (not isinstance(value, str) or len(value) > 40):
            raise ValueError('string exceeds input limit')


class Session:
    """One worker, one pending decision; profiles use the same step() transport.

The default profile preserves existing SSB callers. Startup code passes its
already selected profile. Explicit game instances support replay/search proofs.
"""
    queue_factory = Queue
    worker_factory = Thread

    def __init__(self, slot='A', engines=False, limit=1_000_000, directory=None,
                 timeout=10, *, profile=None, game=None, auto_resolve=True, **options):
        from sm.titles import select
        self.profile = select(profile) if profile is None or isinstance(profile, str) else profile
        self._q, self._a = self.queue_factory(), self.queue_factory()
        self.result = self.decision = self.error = None
        self.timeout, self.pending, self.check = timeout, True, False
        def player(kind, choices, current, **info):
            if auto_resolve and kind in self.profile.automatic:
                self.profile.resolve_decision(kind, current)
                return 0
            decision = Decision(kind, choices, info)
            self._q.put({'kind': decision.kind, 'options': decision.options,
                         'info': {k: v for k, v in decision.info.items() if isinstance(v, (int, str))},
                         'i': len(current.trace), 'hash': current.state_hash()})
            answer = self._a.get()
            if isinstance(answer, BaseException): raise answer
            return answer
        self.game = game if game is not None else self.profile.create_game(
            player, slot=slot, engines=engines, directory=directory, **options)
        self.game.player = player
        def run():
            try: self.result = self.game.play(limit=limit)
            except BaseException as error:
                self.error, self.result = error, 'STOP %s' % error
            self._q.put(None)
        self._worker = self.worker_factory(target=run, daemon=True)
        self._worker.start()
        self.decision = self._next()

    def _next(self):
        """Bound transport waits; presentation checks are not game decisions."""
        try:
            decision = self._q.get(timeout=self.timeout)
            if decision is not None and decision['kind'] == 'AI_CHECK':
                self.check = True
                return None
            self.pending = False
            return decision
        except Empty:
            self.result = 'STOP: game decision watchdog expired after %gs' % self.timeout
            self._a.put(SystemExit(self.result))
            self.decision = None
            raise TimeoutError(self.result) from None

    def step(self, answer):
        if self.decision is None: raise self.profile.Fault('session finished: %s' % self.result)
        if not legal_choice(self.decision['options'], answer, strict=self.profile.strict_choices):
            raise ValueError('answer outside the legal options')
        if self.profile.typed_inputs:
            Decision(self.decision['kind'], self.decision['options']).validate(
                answer, strict=self.profile.strict_choices)
        self.pending = True
        self._a.put(answer)
        self.decision = self._next()
        return self.decision

    def ai_check_wait(self):
        """The simulation waits while a renderer consumes its preceding frames."""
        self._q.put({'kind': 'AI_CHECK'})
        answer = self._a.get()
        if isinstance(answer, BaseException): raise answer
        return answer

    def resume_check(self, key):
        self.check = False
        self._a.put(key)
        self.decision = self._next()

    def close(self):
        if self.decision is not None or self.check:
            self._a.put(SystemExit('closed'))
            self.decision, self.check = None, False
        self._worker.join(timeout=self.timeout)


def play(game, policy, *, profile, limit=100_000):
    """Drive either title with a policy; propagate failures to headless callers."""
    previous = getattr(game, 'player', None)
    session = None
    try:
        session = Session(profile=profile, game=game, limit=limit, auto_resolve=False)
        while session.decision is not None:
            decision = session.decision
            answer = policy(decision['kind'], decision['options'], game, **decision['info'])
            session.step(answer)
        if session.error is not None: raise session.error
        return session.result
    finally:
        if session is not None: session.close()
        game.player = previous


def test():
    from sm._engine_test import test as check
    check()
