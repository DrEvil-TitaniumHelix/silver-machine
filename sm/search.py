"""Shared graph traversal; profiles supply ordered edges and goal predicates."""
from collections import deque
from heapq import heappop, heappush
from itertools import count
from time import monotonic


class SearchLimit(RuntimeError):
    """A nonempty frontier remains; exhaustion does not prove unreachability."""


class PrioritySearch:
    """Stable priority order and bounded expansion; callers choose admission timing.

    DQK admits copied states before queueing; symbolic planning admits signatures
    after popping. Keeping admission explicit preserves both budget contracts.
    Truth tests report remaining work even after a bound stops run().
    """
    def __init__(self, limit=None, *, seconds=None, started=None, clock=monotonic):
        self.limit, self.seconds, self.clock = limit, seconds, clock
        self.started = clock() if started is None else started
        self.expanded, self.seen = 0, set()
        self._queue, self._sequence = [], count()

    def admit(self, key):
        if key in self.seen: return False
        self.seen.add(key)
        return True

    def push(self, value, priority):
        heappush(self._queue, (priority, next(self._sequence), value))

    def __bool__(self):
        return bool(self._queue)

    def run(self, proceed=None):
        while (self._queue and (proceed is None or proceed()) and
               (self.limit is None or self.expanded < self.limit) and
               (self.seconds is None or self.clock() - self.started < self.seconds)):
            _, _, value = heappop(self._queue)
            self.expanded += 1
            yield value


def breadth_first(roots, edges, *, limit=None):
    """Yield (node, parent, action, depth), once per node, in discovery order.

    Edges yield (action, node). Yield before expanding so a found goal consumes
    no further edges. A finite bound counts popped nodes, including roots.
    """
    seen, pending = set(), deque()
    for node in roots:
        if node not in seen:
            seen.add(node); pending.append((node, None, None, 0))
    expanded = 0
    while pending:
        if limit is not None and expanded >= limit:
            raise SearchLimit('bounded search exhausted with a nonempty frontier')
        node, parent, action, depth = pending.popleft(); expanded += 1
        yield node, parent, action, depth
        for action, target in edges(node):
            if target not in seen:
                seen.add(target); pending.append((target, node, action, depth + 1))


def distances(roots, neighbors, *, limit=None):
    """Minimum unweighted distance from any root; unreachable nodes are absent."""
    return {node: depth for node, _, _, depth in breadth_first(
        roots, lambda node: ((None, target) for target in neighbors(node)), limit=limit)}


def shortest_path(start, goal, edges, *, limit=None):
    """Ordered action list, [] at the goal, None only after frontier exhaustion."""
    parents = {}
    for node, parent, action, _ in breadth_first((start,), edges, limit=limit):
        parents[node] = parent, action
        if goal(node):
            result = []
            while node != start:
                node, action = parents[node]; result.append(action)
            return result[::-1]
    return None


def test():
    from sm._search_test import test as check
    check()
