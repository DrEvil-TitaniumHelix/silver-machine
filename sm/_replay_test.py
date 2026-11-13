from sm.replay import Replay, Divergence


def mismatch(call, index, reason):
    try: call()
    except Divergence as error:
        assert (error.index,error.reason)==(index,reason)
        return error
    raise AssertionError('changed replay observation accepted')


def test():
    rows=[('one',('MENU',1,2)),('two',('MOVE',1,3))]
    check=Replay(rows)
    mismatch(lambda:check.check('wrong',rows[0][1]),0,'hash')
    mismatch(lambda:check.check('one',('STRING',1,2)),0,'decision')
    assert check.index==0
    check.check(*rows[0])
    assert mismatch(check.finish,1,'length').actual is None
    check.check(*rows[1]);check.finish('end','end')
    assert mismatch(lambda:check.check('extra'),2,'length').expected is None
    mismatch(lambda:check.finish('changed','end'),2,'terminal state')
    legacy=Replay([('hash',None)]);legacy.check('hash',('ANY',));legacy.finish()
    Replay([]).finish('empty','empty')
    mismatch(lambda:Replay([]).finish('empty',None),0,'terminal state')
    from importlib.util import find_spec
    if find_spec('sm.titles.dqk') is None: return
    from unittest.mock import patch
    from sm.titles.dqk import route
    from sm.titles.dqk._loop_test import fixture
    from sm.titles.dqk._vm_test import instruction
    from sm.titles.dqk.vm import Fault
    code=instruction(0x1D)+instruction(9,(0,7),(1,0x100))+instruction(0x1D)+b'\0'
    created=[]
    def fresh(**_):
        game=fixture(code);game.boot=game.drive;created.append(game);return game
    original=fresh();original.boot();original.answer(0)
    rows=original.trace;final=original.state_hash()
    with patch.object(route,'Host',side_effect=fresh):
        empty = route.replay([])
        assert empty.decision is not None and not empty.trace, 'empty checkpoint must boot without answering'
        assert route.replay(rows,final_hash=final).state_hash()==final
        for field,value in [('hash','changed'),('kind','WRONG')]:
            bad=[dict(rows[0],**{field:value})]
            try:route.replay(bad)
            except Fault:pass
            else:raise AssertionError('corrupt checkpoint accepted')
            assert not created[-1].trace, 'rejected observation consumed an answer'
        try:route.replay(rows,final_hash='changed')
        except Fault as error:assert 'final hash differs' in str(error)
        else:raise AssertionError('terminal mutation accepted')
