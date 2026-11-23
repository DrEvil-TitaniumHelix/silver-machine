from sm.rec import Record
from sm.titles.cok.records import Item, Effect, fields, split_records


class Character(Record):
    SIZE = 216
    FIELDS = fields((
        ('name', 16), ('abilities', 12), ('strength_extra', 1), ('strength_extra_base', 1),
        ('preparation', 1), ('base_thac0', 1), ('race', 1), ('class', 1),
        ('knight_order', 1), ('deity', 1), ('robe_order', 1), ('cure_ability', 1),
        ('age', 2), ('hp_max', 1), ('dimensions', 1), ('saves', 5),
        ('base_move', 1), ('highest_level', 1), ('undead', 1), ('thief_skills', 8),
        ('effects_pointer', 4), ('npc', 1), ('money', 6), ('levels', 8), ('former_levels', 8),
        ('gender', 1), ('alignment', 1), ('attacks', 1), ('second_attacks', 1),
        ('unarmed_rolls', 2), ('unarmed_dice', 2), ('unarmed_bonus', 2),
        ('base_ac', 1), ('use_strength', 1), ('creature_id', 1), ('experience', 4),
        ('old_experience', 4), ('old_hp_max', 1), ('class_mask', 1), ('hp_rolled', 1),
        ('xp_award', 2), ('hp_roll_needed', 1), ('icon_head', 1), ('icon_body', 1),
        ('order', 1), ('icon_size', 1), ('icon_colors', 6), ('creature_type', 1),
        ('target_flags', 1), ('item_count', 1), ('items_pointer', 4),
        ('equipped_pointers', 52), ('hands_used', 1), ('save_bonus', 1), ('weight', 2),
        ('next_pointer', 4), ('combat_pointer', 4), ('magic_resistance', 1),
        ('spells_pointer', 4), ('level_up_ready', 1), ('status', 1), ('active', 1),
        ('side', 1), ('auto_combat', 1), ('thac0', 1), ('ac', 2),
        ('attacks_left', 2), ('damage_rolls', 2), ('damage_dice', 2), ('damage_bonus', 2),
        ('hp', 1), ('move', 1),
    ), SIZE)
    BLOCKS = frozenset(('unarmed_rolls', 'unarmed_dice', 'unarmed_bonus', 'ac',
                        'attacks_left', 'damage_rolls', 'damage_dice', 'damage_bonus'))


class Spells(Record):
    SIZE = 220
    FIELDS = fields((('memorized', 74), ('known_spells', 114), ('spell_slots', 32)), SIZE)


class SavedGame(Record):
    SIZE = 2913
    FIELDS = fields((('disk', 1), ('zone0', 1024), ('zone1', 1024), ('zone2', 512),
                     ('position', 5), ('previous_mode', 1), ('mode', 1), ('walls', 16),
                     ('party_count', 1), ('party_names', 328)), SIZE)


def test():
    from .data import Assets
    from sm.titles.cok.check import record_check
    assets = Assets()
    for name, kind in (('MON1CHA', Character), ('MON1WIZ', Spells), ('MON1ITM', Item), ('MON1SPC', Effect)):
        for raw in assets.records(name).values():
            for record in split_records(raw, kind):
                record_check(record)
    for kind in (Character, Spells, Item, Effect, SavedGame):
        try:
            split_records(bytes(kind.SIZE - 1), kind)
        except ValueError:
            pass
        else:
            raise AssertionError('partial record accepted')
