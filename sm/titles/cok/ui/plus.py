
HELP = [
    ('Menus', 'Click a word, or press its white letter. Left/Right move the highlight and Enter chooses it. '
              'In a list: Up/Down move the bar, N and P (or Page Down and Page Up) turn the page, Left/Right move along the '
              'words on the bottom line and Enter takes the highlighted one (at first Select), E or Escape leaves. '
              'Click a row to choose it.'),
    ('Exploring', 'Up steps forward, Left and Right turn, Down turns around. Move switches to walking with the arrows; '
                  'Area or F2 shows the small map (Not Here in some places); Look searches this square; Search turns searching on '
                  'or off (the position line then ends in "search"); Encamp opens the camp; View shows the character; Cast casts a spell.'),
    ('Overland', 'The arrow keys and the diagonal keys walk the party marker: Home north-west, Page Up north-east, '
                 'End south-west, Page Down south-east. Clicking a square of the map steps toward it.'),
    ('Combat: moving', 'Arrow keys move the active character; Home, Page Up, End and Page Down move diagonally (north-west, '
                       'north-east, south-west, south-east). Moving into an enemy attacks it. Enter or D ends the move; Escape undoes it. '
                       'Clicking a square steps toward it.'),
    ('Combat: aiming', 'The Aim menu comes first: N and P step through the targets, T (when Target is shown) attacks or casts at '
                       'the one named, C centres the view, E or Escape leaves; Left/Right move the highlight and Enter takes it. '
                       'M (Manual) opens the free cursor: the arrow and diagonal keys move it, T or Enter takes the square while '
                       'Target shows, Space centres the view, E or Escape goes back to the menu. '
                       'A character on quick fight acts by itself: Space returns it to manual control, Alt-M toggles its spell casting.'),
    ('Camp', 'Save, View, Magic, Rest, Alter and Fix. In Rest, Up adds and Down subtracts, Left and Right move between days, '
             'hours and minutes; Rest starts resting.'),
    ('Save and load', 'F10 opens Save, Load, Quit and Resume. Save at the Outpost menu, while exploring or in camp; Load lists the '
                      'games you have saved. Your saves and characters stay in your SilverMachine folder, never in the game folder.'),
    ('Plus', 'Journal lists every JOURNAL ENTRY number the game has cited, with the scene, and opens your own Journal.pdf: '
             'find the entry number in it. Area map shows the current area. Plus options: Effect time scales the pauses, '
             'the combat replay and the letter-by-letter story text (×1 is the original timing; the Speed '
             'setting, in camp under Alter or in a fight, sets their length).'),
]


def area_map(game):
    from sm.titles.ssb.ui.plus import area_map as cells
    return cells(game)


def tab_data(controller, tab, query):
    if tab == 'map': return area_map(controller.session.game)
    raise ValueError('Unknown Plus tab')


def test():
    text = ' '.join(t for _, t in HELP)
    assert all(k in text for k in ('Home', 'Page Up', 'End', 'Page Down', 'Space'))
    return 'PASS help'
