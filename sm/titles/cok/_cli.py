import argparse
import hashlib
import json
import os
from pathlib import Path
from . import creation
from .faults import BindingRequired


def at_outpost(session):
    return (session.game.s.dataset, session.game.s.block) == (1, 17) and bool(
        session.decision and session.decision['info'].get('at') == 0x86BF)


class FirstChoices:
    def __init__(self): self.created = False

    def __call__(self, session):
        d, game = session.decision, session.game
        kind, options = d['kind'], d['options']
        if d['info'].get('action') == 'main-menu':
            ident = creation.BEGIN if game.s.party else creation.ADD if self.created else creation.CREATE
            return game.menu_ids.index(ident)
        if kind == creation.Kind.ROLL.value: return options.index('No')
        if kind == creation.Kind.SAVE.value: self.created = True
        if kind == creation.Kind.ADD.value and game.s.party: return options.index(creation.EXIT)
        if options is None: return 0 if kind == 'NUMBER' else 'HERO'
        return 0


def arrive(session, *, limit=256, policy=None):
    from .ui.screen import Controller, render
    controller, policy = Controller(session), policy or FirstChoices()
    frames = []
    while session.decision is not None:
        controller.capture_text()
        for page in range(max(1, (len(controller.lines)+5)//6)):
            controller.text_page = page
            frames.append(hashlib.sha256(b''.join(render(controller).rows)).hexdigest())
        if at_outpost(session):
            return dict(block=[session.game.s.dataset, session.game.s.block], decisions=len(session.game.trace),
                        hash=session.game.state_hash(), frame=frames[-1], frames=tuple(frames))
        if len(session.game.trace) >= limit: raise BindingRequired('Champions arrival decision limit reached')
        session.step(policy(session))
    if session.error: raise session.error
    raise BindingRequired('Champions stopped before the Outpost: '+str(session.result))


def run(arguments, local):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder')
    parser.add_argument('--limit', type=int, default=1_000_000)
    parser.add_argument('--slot', choices=creation.SLOTS, help='continue a native frontier save')
    parser.add_argument('--record', type=Path, help='optionally save decisions from the complete run')
    parser.add_argument('--replay', type=Path, help='replay a saved decision record, checking every state and frame checkpoint')
    args = parser.parse_args(arguments)
    if args.folder: os.environ['SM_COK'] = args.folder
    game=None
    def onward(session, frame=lambda label:None):
        nonlocal game
        from ._town_test import inside_gargath, continue_story
        game=session.game
        game.roster_directory=Path(local)/'saves'/'cok'
        if not args.slot: inside_gargath(session)
        return continue_story(session)
    try:
        from ._town_test import throtl_route, replay_route, starter_game, Game, Session, cok
        if args.replay:
            record=json.loads(args.replay.read_text(encoding='utf-8'))
            final=replay_route(record,args.folder); result=record['summary']|final
        elif args.slot:
            from . import town
            game=Game(None,directory=args.folder)
            game.roster_directory=Path(local)/'saves'/'cok'
            town.load_game(game,args.slot)
            session=Session(profile=cok,game=game,limit=args.limit)
            try: result=onward(session)
            finally: session.close()
        else:
            game=starter_game(args.folder)
            game.roster_directory=Path(local)/'saves'/'cok'
            session=Session(profile=cok,game=game,limit=args.limit)
            record={}
            try: result=throtl_route(args.folder,onward=onward,limit=args.limit,record=record,session=session)
            finally: session.close()
            if args.record:
                record['summary']={key:result[key] for key in ('furthest','block','position','overland')}
                args.record.parent.mkdir(parents=True,exist_ok=True)
                args.record.write_text(json.dumps(record,separators=(',',':'))+'\n',encoding='utf-8')
            replay_route(record,args.folder)
            print('Replay equal: '+result['state'])
        print('Champions: furthest block %d/%d; position %s; %d decisions' %
              (*result['furthest'],result['position'],result['decisions']))
        if game is not None and hasattr(game,'frontier'): print('Frontier save: '+str(game.frontier))
        if game is not None: print('State: %s; ending 4C3A=%d'%(game.state_hash(),game.vm.m0(0x4C3A)))
        if args.replay: print('Replay equal: '+str(args.replay))
        elif args.record: print('Decision record: '+str(args.record))
        return 0
    except Exception as error:
        if game is not None:
            furthest=max(((disk,block) for disk,block,_,_ in getattr(game,'script_log',()) if block>=32 and block!=36),default=(game.s.dataset,game.s.block))
            print('Champions: furthest block %d/%d; at %d/%d (%d,%d); %d decisions'%
                  (*furthest,game.s.dataset,game.s.block,game.s.x,game.s.y,len(game.trace)))
            if hasattr(game,'frontier'): print('Frontier save: '+str(game.frontier))
        print('STOP: '+str(error))
        return 1


def test():
    from ._town_test import test as check
    check()
