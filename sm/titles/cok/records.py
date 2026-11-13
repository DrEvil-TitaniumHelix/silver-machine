from sm.rec import Record


def fields(parts, size):
    result, offset = {}, 0
    for name, width in parts:
        if name in result:
            raise ValueError('duplicate field: ' + name)
        result[name] = offset, width
        offset += width
    if offset != size:
        raise ValueError('layout size does not match its disk record')
    return result


class Character(Record):
    SIZE = 409
    FIELDS = fields((
        ('name', 16), ('abilities', 12), ('strength_extra', 1), ('strength_extra_base', 1),
        ('memorized', 58), ('preparation', 1), ('base_thac0', 1), ('race', 1), ('class', 1),
        ('knight_order', 1), ('deity', 1), ('robe_order', 1), ('knight_bracket', 1),
        ('age', 2), ('hp_max', 1), ('known_spells', 107), ('attack_level', 1),
        ('dimensions', 1), ('saves', 5), ('base_move', 1), ('highest_level', 1),
        ('dual_threshold', 1), ('drained_levels', 1), ('drained_hp', 1), ('undead', 1),
        ('thief_skills', 8), ('effects_pointer', 4), ('npc', 1), ('modified', 1),
        ('reserved_e9', 2), ('money', 14), ('levels', 8), ('former_levels', 8),
        ('gender', 1), ('alignment', 1), ('attacks', 1), ('second_attacks', 1),
        ('unarmed_rolls', 2), ('unarmed_dice', 2), ('unarmed_bonus', 2),
        ('base_ac', 1), ('use_strength', 1), ('creature_id', 1), ('experience', 4),
        ('class_mask', 1), ('hp_rolled', 1), ('spell_slots', 20), ('xp_award', 2),
        ('xp_per_hp', 1), ('reserved_133', 2), ('icon_head', 1), ('icon_body', 1),
        ('order', 1), ('icon_size', 1), ('icon_colors', 6), ('creature_type', 1),
        ('target_flags', 1), ('reserved_target', 1), ('item_count', 1), ('items_pointer', 4),
        ('equipped_pointers', 52), ('hands_used', 1), ('save_bonus', 1), ('weight', 2),
        ('next_pointer', 4), ('combat_pointer', 4), ('magic_resistance', 1), ('status', 1),
        ('active', 1), ('side', 1), ('auto_combat', 1), ('thac0', 1), ('ac', 2),
        ('attacks_left', 2), ('damage_rolls', 2), ('damage_dice', 2), ('damage_bonus', 2),
        ('hp', 1), ('move', 1),
    ), SIZE)
    BLOCKS = frozenset(('reserved_e9', 'unarmed_rolls', 'unarmed_dice', 'unarmed_bonus',
                        'reserved_133', 'ac', 'attacks_left', 'damage_rolls',
                        'damage_dice', 'damage_bonus'))


class Item(Record):
    SIZE = 63
    FIELDS = fields((
        ('name', 41), ('in_use', 1), ('next_pointer', 4), ('type', 1), ('name_ids', 3),
        ('bonus', 1), ('save_bonus', 1), ('readied', 1), ('unidentified', 1),
        ('cursed', 1), ('weight', 2), ('quantity', 1), ('value', 2), ('powers', 3),
    ), SIZE)


class Effect(Record):
    SIZE = 9
    FIELDS = fields((('type', 1), ('duration', 2), ('strength', 1),
                     ('on_remove', 1), ('next_pointer', 4)), SIZE)


class SavedGame(Record):
    SIZE = 5469
    FIELDS = fields((('disk', 1), ('zone0', 2048), ('zone1', 2048), ('zone2', 1024),
                     ('position', 5), ('previous_mode', 1), ('mode', 1), ('walls', 12),
                     ('party_count', 1), ('party_names', 328)), SIZE)


def split_records(raw, record_type):
    if len(raw) % record_type.SIZE:
        raise ValueError('partial ' + record_type.__name__ + ' record')
    return tuple(record_type(raw[i:i + record_type.SIZE])
                 for i in range(0, len(raw), record_type.SIZE))
