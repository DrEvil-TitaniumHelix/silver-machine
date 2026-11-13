import argparse, sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    from importlib import import_module
    from sm.titles import startup
    try:
        profile, arguments = startup(sys.argv[1:])
        if not getattr(profile, 'ui_module', None):
            raise ValueError('This title has no graphics UI yet')
        ui = import_module(profile.ui_module)
        screen = import_module(profile.presentation)
    except ValueError as error: parser.exit(1, str(error) + '\n')
    parser.add_argument('--slot', choices=ui.START_SLOTS, help='explicit shipped save; overrides autosave')
    parser.add_argument('--load', metavar='SLOT', choices=ui.SAVE_SLOTS,
                        help='boot a native slot from local/saves/SLOT')
    parser.add_argument('--web', action='store_true', help='open the local browser UI')
    parser.add_argument('--no-browser', action='store_true', help='with --web: serve without opening a browser tab (the open tab reconnects)')
    parser.add_argument('--port', type=int, default=8320, help='browser server port (default: 8320)')
    parser.add_argument('--saves', metavar='DIR', help='check server only: load --load from this save root (the oracle fixture)')
    parser.add_argument('--seed', metavar='[A:]N[@X,Y]', help='check server only: set RandSeed at load (A), and now or on first reaching square X,Y (N)')
    parser.add_argument('--check', action='store_true', help='headless town-hall, menus and keyboard replay checks')
    parser.add_argument('--check-fight', action='store_true', help='headless real fight through screen keys and replay')
    args = parser.parse_args(arguments)
    if (args.seed or args.saves) and (not args.web or args.port == 8320): parser.error('--seed/--saves are for a check server: --web with a port other than 8320')
    try:
        if not args.web or args.check or args.check_fight: profile.require_content()
    except ValueError as error: parser.exit(1, str(error) + '\n')
    if args.check or args.check_fight:
        ui.check(fight=args.check_fight)
        return
    def create_session():
        session = ui.start_session(args.slot, args.load, saves=args.saves)
        if args.seed: ui.seed_at(session, args.seed)
        elif args.web and not profile.__name__.endswith('.ssb') and getattr(session.game.s, 'seed', None) == 0:
            import time
            session.game.s.seed = time.time_ns() & 0xFFFFFFFF or 1
        return session
    if args.web:
        from sm.ui.web import run
        run(port=args.port, browser=not args.no_browser, session_factory=create_session, profile=profile)
        return
    session = create_session()
    window = None
    try:
        window = screen.Window(session)
        window.run()
    finally:
        if window is not None:
            window.close()
        else:
            session.close()


if __name__ == '__main__':
    main()
