from sm.titles.cok.faults import BindingRequired


def required(what):
    def stub(*args, **kwargs):
        raise BindingRequired('Death Knights binding unverified: ' + what)
    return stub


def test():
    try:
        required('test boundary')()
    except BindingRequired as error:
        assert 'Death Knights' in str(error)
    else:
        raise AssertionError('missing binding did not stop')
