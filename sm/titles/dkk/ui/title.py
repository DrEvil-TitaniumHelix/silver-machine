import hashlib
from functools import lru_cache

MUSIC_RATE, SOUND_RATE = 100 * 0x10000 / 0x4000, 100 * 0x10000 / (0x13B1 * 13)
HOLDS = tuple(n * 100 / MUSIC_RATE for n in (5, 5, 5, 20))
CREDIT_HOLD = (10000 * 100 & 0xFFFF) / MUSIC_RATE
HELD = HOLDS + (CREDIT_HOLD,)
CREDITS, PLAY = 5, 6
DEMO_WAIT, AGAIN_WAIT = 3000 / MUSIC_RATE, 1000 / SOUND_RATE
KEPT = ('clock', 'effect_scale', 'sound_on', 'sound_seq', 'sound_events', 'decision_observer', 'autosave_enabled', 'hold_seq', 'journal')
CREDIT_BLOCK = (359, 481, '32312d87a60adaa7b7286de10055c9824eb8267195b54585b2d4d284c0d2f405')
CREDIT_PLACES = ((2, 1, 14), (11, 3, 15), (4, 4, 10), (13, 5, 15), (14, 6, 10), (1, 8, 15), (4, 9, 10), (4, 10, 10), (4, 11, 10),
                 (4, 12, 10), (1, 13, 15), (4, 14, 10), (4, 15, 10), (4, 16, 10), (1, 17, 15), (4, 18, 10), (4, 19, 10), (4, 20, 10),
                 (1, 21, 15), (4, 22, 10))


def strings(raw):
    out, at = [], 0
    while at < len(raw):
        out.append(raw[at + 1:at + 1 + raw[at]].decode('cp437')); at += 1 + raw[at]
    return out


@lru_cache(maxsize=4)
def credits(root):
    from sm.files import file_path
    offset, size, digest = CREDIT_BLOCK
    try: raw = file_path(root, 'GAME.OVR').read_bytes()[offset:offset + size]
    except OSError: return ()
    if hashlib.sha256(raw).hexdigest() != digest: return ()
    return tuple(strings(raw))


def picture(assets, ident):
    from sm.ui.art import decode
    return decode(assets.records('TITLE')[ident]).parts[0].frames[0]


def active(controller):
    return getattr(controller.session.game, 'title', None) is not None


def advance(controller, phase):
    controller.session.game.title, controller.title_at, controller.title_choice = phase, controller.clock(), 0


def tick(controller):
    game = controller.session.game
    if getattr(game, 'title', None) is None: return
    if not hasattr(controller, 'title_at'): advance(controller, game.title)
    while game.title is not None and game.title <= len(HELD) and controller.clock() - controller.title_at >= HELD[game.title - 1]:
        advance(controller, game.title + 1)
    if game.title == PLAY and controller.clock() - controller.title_at >= getattr(controller, 'title_wait', DEMO_WAIT): restart(controller, True)


def demo_on(game):
    return bool(getattr(game.s, 'g', {}).get('dkk.runtime', {}).get('demo', 0))


def update(controller):
    session = controller.session
    tick(controller)
    if demo_on(session.game) and session.decision is None and session.result == 'DEMO':
        from .screen import report_step
        if controller.held() is None and report_step(controller) is None: restart(controller, False)


def restart(controller, demo):
    from . import start_session
    from .screen import pass_timed
    old = controller.session
    game = old.game
    session = start_session(saves=getattr(game, 'roster_directory', None), directory=game.assets.root, seed=game.s.seed or None, title=not demo, demo=demo)
    kept = dict(controller.__dict__)
    old.close()
    type(controller).__init__(controller, session, save_root=kept.get('save_root'), presentation=kept['presentation_enabled'])
    controller.__dict__.update({k: v for k, v in kept.items() if k in KEPT})
    controller.generation = kept.get('generation', 0) + 1
    if demo: pass_timed(controller)
    else: controller.title_wait = AGAIN_WAIT; advance(controller, 1)


def words(assets):
    return assets.text('playDemoMenu').split()


def key(controller, keysym, char):
    game = controller.session.game
    tick(controller)
    if game.title < PLAY:
        advance(controller, PLAY if game.title == CREDITS else CREDITS); return False
    from .screen import EXTENDED_KEYS
    labels = words(controller.assets)
    step = {'Left': -1, 'Right': 1}.get(keysym)
    if step is None and keysym not in EXTENDED_KEYS and not keysym.startswith('Alt-'): step = {'4': -1, '6': 1}.get(char)
    if keysym == 'Escape' or keysym in EXTENDED_KEYS or keysym.startswith('Alt-'): hit = 0
    elif keysym in ('Return', 'KP_Enter'): hit = controller.title_choice
    else: hit = next((n for n, label in enumerate(labels) if char and label[:1].lower() == char.lower()), None)
    if step is not None:
        controller.title_choice, hit = (controller.title_choice + step) % len(labels), None
    if hit == 1: restart(controller, True)
    elif hit is not None: game.title = None
    return False


def draw(controller, assets):
    from .screen import Frame, window_frame, draw_word
    game = controller.session.game
    tick(controller)
    frame, phase = Frame(), game.title
    if phase == 1: frame.blit(0, 0, picture(assets, 1))
    elif phase <= len(HOLDS):
        frame.blit(0, 0, picture(assets, 2))
        for ident in range(3, phase + 1): frame.blit(0, 88, picture(assets, ident))
    elif phase == CREDITS:
        window_frame(frame, game, assets, 23)
        for (col, row, colour), text in zip(CREDIT_PLACES, credits(str(assets.root))): frame.text(col, row, text, assets, colour, 40 - col)
    else:
        query = assets.text('gameTitle'); frame.text(0, 24, query, assets, 13); col = len(query)
        for n, label in enumerate(words(assets)): draw_word(frame, assets, col, label, n == controller.title_choice); col += len(label) + 1
    return frame


def layout(controller):
    tick(controller)
    phase = controller.session.game.title
    return dict(regions=[dict(rect=(0, 0, 320, 200), key=dict(keysym='Return', char=''))], selected=0,
                roster_selected=controller.session.game.s.sel, revision=['title', phase, getattr(controller, 'title_choice', 0)],
                animating=phase is not None and phase <= len(HOLDS))


def test():
    raw = bytes((2,)) + b'AB' + bytes((0, 1)) + b'C'
    assert strings(raw) == ['AB', '', 'C']
    assert len(CREDIT_PLACES) == 20 and HOLDS == (1.25, 1.25, 1.25, 5.0) and CREDIT_HOLD == 42.4 and DEMO_WAIT == 7.5 and round(AGAIN_WAIT, 2) == 10.0
