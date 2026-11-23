HELP = [
    ('Menus', 'Press the highlighted letter of a word, or move the highlight with Left and Right and press Enter. '
              'In an item list, Up and Down move the bar, Left and Right move along the words on the bottom line, '
              'Enter takes the highlighted word for that item and Escape leaves.'),
    ('Exploring', 'Up and Down choose the character. Move switches to walking: Up steps forward, Left and Right turn, '
                  'Down turns around, and Exit or Escape returns to the menu. Area shows the small map (Not Here in some '
                  'places); Look searches the square you stand on and takes time; Search turns searching on or off; '
                  'Encamp opens the camp; View shows the character; Cast casts a spell.'),
    ('Overland', 'The menu offers Move and Encamp. In Move the arrow keys walk the party marker north, south, east and west; '
                 'Home walks north-west, Page Up north-east, End south-west and Page Down south-east. Exit or Escape stops walking.'),
    ('Combat: the menu', 'The words sit on two rows: Left and Right move the highlight, Up and Down change rows, Enter takes '
                         'the highlighted word, or press its first letter. A word shows only when it applies: Move, Aim, Use, '
                         'Cast, Turn, Guard, Quick, Delay, Bandage, Yell, View, Speed, End. Alt-Q puts the whole party on quick '
                         'fight, Alt-M turns spell casting on quick fight on or off, Alt-D gives every character back to you.'),
    ('Combat: moving', 'Arrow keys move the active character; Home, Page Up, End and Page Down move diagonally (north-west, '
                       'north-east, south-west, south-east). Moving into an enemy attacks it. Enter or D ends the move; Escape undoes it.'),
    ('Combat: aiming', 'Aim shows Next, Prev, Manual, Target (when the one named can be taken), Center and Exit: N and P step '
                       'through the targets, T attacks or casts at the one named, C centres the view, E or Escape leaves; '
                       'Left and Right move the highlight and Enter takes it. M (Manual) opens the free cursor: the arrow and '
                       'diagonal keys move it, T or Enter takes the square while Target shows, Space centres the view, E or '
                       'Escape goes back to the words. A character on quick fight acts by itself: Space returns it to you, '
                       'Alt-M turns its spell casting on or off.'),
    ('Camp', 'Save, View, Magic, Rest, Alter and Fix. Rest shows Rest, Days, Hours, Mins, Add, Subtract and Exit: Days, Hours and '
             'Mins choose what changes, Up adds and Down subtracts, Left and Right move the highlight, Rest starts resting.'),
    ('Save and load', 'F10 opens Save, Quit and Resume (Load too at the first menu, before a party is formed). Save while '
                      'exploring or in camp, then press a letter; in camp Save is also on the menu. Your saves and characters '
                      'stay in your SilverMachine folder, never in the game folder.'),
    ('Plus', 'Journal lists every journal entry number the game has cited, with the scene, shows the entry when your copy '
             'opens it, and opens your own Journal.pdf. Area map shows the current area while the party walks a grid. '
             'Plus options: Effect time scales the pauses, the combat replay and the letter-by-letter story text (×1 is the '
             'original timing; the Speed setting, in camp under Alter or in a fight, sets their length).'),
]


def area_map(game):
    from sm.titles.ssb.ui.plus import area_map as cells
    return cells(game)


def tab_data(controller, tab, query):
    if tab == 'map': return area_map(controller.session.game)
    raise ValueError('Unknown Plus tab')


def test():
    text = ' '.join(t for _, t in HELP)
    assert all(k in text for k in ('Home', 'Page Up', 'End', 'Page Down', 'Alt-Q', 'Alt-M', 'Alt-D', 'F10', 'Journal.pdf'))
    assert len({title for title, _ in HELP}) == len(HELP)
    try: tab_data(None, 'rules', {})
    except ValueError: pass
    else: raise AssertionError('unknown tab accepted')
    return 'PASS help'
