import sys, os, json
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'local')


def serve(profile, arguments):
    from sm.engine import Session
    s = Session(profile=profile, engines='--engines' in arguments)
    while s.decision is not None:
        print(json.dumps(s.decision), flush=True)
        line = sys.stdin.readline()
        if not line: s.close(); break
        s.step(json.loads(line))
    print(json.dumps({'result': s.result}), flush=True)


def main(arguments=None, *, local=LOCAL):
    from sm.titles import startup
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    command = arguments.pop(0) if arguments else 'test'
    profile, arguments = startup(arguments)
    if command not in profile.commands: raise ValueError('command unavailable for title: ' + command)
    if hasattr(profile, 'require_content'): profile.require_content()
    if command == 'serve': return serve(profile, arguments)
    return profile.run_cli(command, arguments, local)


if __name__ == '__main__':
    try: sys.exit(main())
    except ValueError as error: sys.exit(str(error))
