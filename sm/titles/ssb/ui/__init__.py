from sm.titles import ssb
from sm.titles.ssb import data as ssb_data

START_SLOTS = ('A', 'B')
SAVE_SLOTS = tuple('ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def __getattr__(name):
    if name == 'slots':
        from sm.titles.ssb.ui import screen
        return screen
    raise AttributeError(name)


def test():
    from sm.titles.ssb.art import test as check_art
    from sm.titles.ssb.ui._test import test as check
    from sm.titles.ssb.ui._fight_test import test as check_fight
    from sm.titles.ssb.ui._panels_test import test as check_panels
    from sm.titles.ssb.ui._icons_test import test as check_icons
    from sm.titles.ssb.ui._plus_test import test as check_plus
    from sm.titles.ssb.ui._vga_test import test as check_vga
    from sm.titles.ssb.ui._journal_test import test as check_journal
    from sm.titles.ssb.ui._view_test import test as check_view
    from sm.titles.ssb.ui._saves_test import test as check_saves
    from sm.titles.ssb.ui._web_test import test as check_web
    from sm.titles.ssb.ui._presentation_test import test as check_presentation
    from sm.titles.ssb.ui._sound_test import test as check_sound
    from sm.titles.ssb.ui._combat_pass_test import test as check_combat_pass
    check_art()
    check()
    check_panels()
    check_icons()
    check_plus()
    check_vga()
    check_journal()
    check_view()
    check_saves()
    check_sound()
    check_presentation()
    check_combat_pass()
    from pathlib import Path
    if (Path(__file__).resolve().parents[4] / 'herdr/route/derived.json').is_file():
        check_fight()
        check_web()
    else: print('SKIP ui derived fight and web fight parity: herdr/route/derived.json is not shipped')


def start_session(slot=None, load=None, root=None, saves=None):
    from sm.engine import Session
    from pathlib import Path
    from sm.titles.ssb.ui.screen import SAVE_ROOT, BadZipFile, load_autosave, load_slot
    root = Path(root or SAVE_ROOT)
    if load and saves: return Session(profile=ssb, slot=load, directory=Path(saves) / load, engines=True)
    if load: return load_slot(load, root)
    if slot: return Session(profile=ssb, slot=slot, engines=True)
    if (root / 'autosave.zip').is_file():
        try:
            return load_autosave(root)
        except (OSError, ValueError, KeyError, BadZipFile) as error:
            print('Unable to reload autosave: %s; starting from the game folder.' % error)
    from sm.titles.ssb.intake import file_path
    if file_path(ssb_data.SECRET, 'SAVGAMA.DAT').is_file(): return Session(profile=ssb, engines=True)
    return Session(profile=ssb, slot=None, engines=True, directory=root)


def seed_at(session, text):
    first, _, text = text.rpartition(':')
    if first: session.game.s.seed = int(first, 0) & 0xFFFFFFFF
    value, _, cell = text.partition('@'); value = int(value, 0)
    if not cell:
        session.game.s.seed = value & 0xFFFFFFFF
        return
    where, step = tuple(map(int, cell.split(','))), session.step
    def seeded(answer):
        decision = step(answer); s = session.game.s
        if session.step is seeded and (s.x, s.y) == where:
            s.seed = value & 0xFFFFFFFF; session.step = step
        return decision
    session.step = seeded


def check(fight=False):
    if fight:
        from ._fight_test import test
        test(screenshot=True)
        return
    from ._test import test
    from ._panels_test import test as panels
    from ._icons_test import test as icons
    from ._view_test import test as view
    from ._saves_test import test as saves
    test(screenshot=True)
    panels(screenshot=True)
    icons(screenshot=True)
    view(screenshot=True)
    saves(screenshot=True)
