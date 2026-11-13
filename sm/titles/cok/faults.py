from sm.titles.ssb.vm import Halt


class BindingRequired(Halt):
    pass


def required(what):
    def stub(*args, **kwargs):
        raise BindingRequired('Champions binding not implemented: ' + what)
    return stub
