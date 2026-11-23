from . import effects
from .effects_handlers import say

F = effects.F


def refresh_area(battle):
    for cloud in battle.data.get('clouds', ()):
        for x, y, under in cloud['cells']:
            battle.put_tile(x, y, cloud['terrain'])


def count_down_area(battle, immediate=False):
    clouds = battle.data.get('clouds', [])
    expired = []
    for cloud in clouds:
        duration = (cloud['countdown'] + 128) % 256 - 128
        if duration == -1 if immediate else duration <= 1:
            expired.append(cloud)
        elif not immediate:
            cloud['countdown'] = duration - 1
    if not expired: return
    bodies, owners, count = battle.body_state()
    corpses = {(x, y) for (x, y, under), who in zip(bodies[:count], owners[:count]) if who >= 0}
    for cloud in expired:
        for x, y, under in cloud['cells']:
            battle.put_tile(x, y, 31 if (x, y) in corpses else under)
    removed = {id(cloud) for cloud in expired}
    clouds[:] = [cloud for cloud in clouds if id(cloud) not in removed]
    refresh_area(battle)
    battle.context().call('bottom_line', battle.game.assets.text('explosionMessage'))


def terrain_effects(battle, index, moved=True):
    char = battle.chars[index]
    if not char.b[F['active']]: return
    tiles = {battle.tile(x, y) for x, y in battle.cells(index)}
    game = battle.game
    roll = battle.context(char)
    if moved and 29 in tiles:
        roll.call('terrain_view', char)
        if not char.b[F['undead']] and not effects.has(char, 31) and not effects.has(char, 99):
            saved = roll.call('saving_throw', char, 0, 0)
            kind, key = (30, 'startsCoughing') if saved else (31, 'chokesFromNausea')
            current, selected = battle.data['actor'], game.s.sel
            try:
                duration = effects.roll_dice(game.s, 1, 4) + 1
                battle.add_with_message(index, kind, duration, 255, False, game.assets.text(key), saved, 0)
                node = effects.has_effect(char, kind)
                if node is not None:
                    effects.call_handler(game, char, kind, node, False, roll)
                    state = battle.record(index)
                    if saved and state['casting'] > 0:
                        from .magic import forget
                        say(game, char, 'lostSpellMessage', roll)
                        forget(char, state['casting'])
                        roll.call('end_actions', char)
            finally:
                battle.data['actor'], game.s.sel = current, selected
    if 28 not in tiles or not char.b[F['active']]: return
    level = char.b[F['highest_level']]
    if level > 6: return
    if level >= 5 and roll.call('saving_throw', char, 0, 252 if level == 5 else 0): return
    say(game, char, 'poisonedMessage', roll, False)
    roll.call('pause')
    effects.add_effect(char, 55, 0, 255, False)
    battle.kill(index, 6, game.assets.text('killedMessage'))


def test():
    from ._effects_test import test_area
    test_area()
