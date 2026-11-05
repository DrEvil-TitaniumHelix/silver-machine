"""Ordered paths, cycles, multiple roots and honest bounded-search outcomes."""
from sm.search import SearchLimit, PrioritySearch, breadth_first, distances, shortest_path


def test():
    graph = {'a': [('left','b'), ('right','c')], 'b': [('back','a'), ('end','d')],
             'c': [('other','d')], 'd': [], 'isolated': []}
    assert shortest_path('a', lambda n:n=='d', graph.__getitem__) == ['left','end']
    assert shortest_path('a', lambda n:n=='a', graph.__getitem__, limit=1) == []
    assert shortest_path('a', lambda n:n=='isolated', graph.__getitem__) is None
    assert [n for n,_,_,_ in breadth_first(('a',),graph.__getitem__)] == ['a','b','c','d']
    assert distances(('a','c','a'),lambda n:(v for _,v in graph[n])) == {'a':0,'c':0,'b':1,'d':1}
    for bound in (0,1,3):
        try: shortest_path('a',lambda n:n=='isolated',graph.__getitem__,limit=bound)
        except SearchLimit: pass
        else: raise AssertionError('bounded search was reported unreachable')
    assert shortest_path('a',lambda n:n=='d',graph.__getitem__,limit=4)==['left','end']
    # Stop at a found goal before evaluating its outgoing edges.
    def terminal(_): raise AssertionError('goal expanded')
    assert shortest_path(None,lambda n:n is None,terminal)==[]
    priority_checks()


def priority_checks():
    # Stable ties must never compare the opaque state values themselves.
    a,b,c=object(),object(),object()
    search=PrioritySearch(2)
    for value,rank in ((a,(0,)),(b,(0,)),(c,(-1,))): search.push(value,rank)
    assert list(search.run())==[c,a] and search.expanded==2 and search
    search.limit=3
    assert list(search.run())==[b] and not search
    for bound in (0,1):
        search=PrioritySearch(bound);search.push(a,(0,))
        assert list(search.run())==([] if bound==0 else [a])
        assert bool(search)==(bound==0)
    # Stop a multi-result consumer before another pop consumes its budget.
    search=PrioritySearch(10);search.push(a,(0,));search.push(b,(0,))
    found=[]
    for value in search.run(lambda:not found): found.append(value)
    assert found==[a] and search.expanded==1 and search
    # Admission at pop counts duplicates as expansions, unlike admission at push.
    for at_pop in (False,True):
        search=PrioritySearch(10)
        for value in (a,a,b):
            if at_pop or search.admit(value): search.push(value,(0,))
        found=[]
        for value in search.run():
            if not at_pop or search.admit(value): found.append(value)
        assert found==[a,b] and search.expanded==(3 if at_pop else 2)
        assert search.seen=={a,b}
    ticks=iter([0,.5,1]).__next__
    search=PrioritySearch(10,seconds=1,started=0,clock=ticks)
    for value in (a,b,c): search.push(value,(0,))
    assert list(search.run())==[a,b] and search.expanded==2 and search
