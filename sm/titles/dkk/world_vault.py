from . import combat, inventory, save_vault, shop


LABELS = ('View', 'Take', 'Pool', 'Money', 'Items', 'Exit')
EXTENDED = ('char-up', 'char-down', 'escape', 'extended')


def choices(state):
    char = state.selc()
    coins, items = combat.treasure_flags(state)
    enabled = [0]
    if coins or items: enabled.append(1)
    enabled.append(2)
    if any(shop.coins(char)[4:7]): enabled.append(3)
    if char.items: enabled.append(4)
    enabled.append(5)
    return tuple(enabled), coins, items


def interact(game, directory):
    s, vm = game.s, game.vm
    s.treasure_items.clear()
    save_vault.load_vault(s, directory)
    s.g['treasure_active'] = 0
    selected = 0
    while True:
        enabled, coins, items = choices(s)
        if not 0 <= selected < len(enabled): selected = 0
        options = tuple(LABELS[index] for index in enabled)
        game.menu_highlight = selected
        answer = game.ask('MENU', options + EXTENDED, prompt='', start=selected,
                          selected=selected, vault_menu=True, menu_labels=LABELS,
                          enabled=enabled, animation=False, enter_ok=True,
                          escape_choice=len(options) + EXTENDED.index('escape'))
        if answer >= len(options):
            selected = game.menu_highlight
            action = EXTENDED[answer - len(options)]
            if action == 'escape': break
            if action in ('char-up', 'char-down'):
                s.sel = (s.sel + (-1 if action == 'char-up' else 1)) % len(s.chars())
            continue
        selected = answer
        action, char = options[answer], s.selc()
        if action == 'Exit': break
        if action == 'View': inventory.view(game, char)
        elif action == 'Take': combat.loot_take(game, coins, items)
        elif action == 'Pool': shop.pool_money(s)
        elif action == 'Money':
            inventory.drop_coins(game, char, on_sheet=False)
            vm.clear_text()
        elif action == 'Items':
            inventory.items_menu(game, char)
            vm.interface_redraw_epoch += 1
            vm.clear_text()
    save_vault.write_vault(s, directory, game=game)


def run(game):
    game.s.mode = 7
    game.s.g.setdefault('dkk.runtime', {})['noncombat_prepared'] = 1
    game.vm.interface_redraw_epoch += 1
    game.vm.clear_text()
    if getattr(game, 'save_filesystem', None) is None:
        from .creation import save_directory
        directory = save_directory(getattr(game, 'roster_directory', None))
    else: directory = game.service(game, 'save', 'check_directory')
    if directory is not None: interact(game, directory)


def test():
    from ._town_test import vault_loop
    vault_loop()
