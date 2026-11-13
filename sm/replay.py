_UNSET = object()


class Divergence(ValueError):
    def __init__(self, index, expected, actual, reason):
        self.index, self.expected, self.actual, self.reason = index, expected, actual, reason
        super().__init__('%s differs at decision %d' % (reason, index))


class Replay:
    def __init__(self, observations):
        self.rows = list(observations)
        self.index = 0

    def check(self, state_hash, identity=None):
        actual = state_hash, identity
        if self.index == len(self.rows):
            raise Divergence(self.index, None, actual, 'length')
        expected = self.rows[self.index]
        if state_hash != expected[0]:
            raise Divergence(self.index, expected, actual, 'hash')
        if expected[1] is not None and identity != expected[1]:
            raise Divergence(self.index, expected, actual, 'decision')
        self.index += 1

    def finish(self, state_hash=None, expected_hash=_UNSET):
        if self.index != len(self.rows):
            raise Divergence(self.index, self.rows[self.index], None, 'length')
        if expected_hash is not _UNSET and state_hash != expected_hash:
            raise Divergence(self.index, None, None, 'terminal state')


def test():
    from sm._replay_test import test as check
    check()
