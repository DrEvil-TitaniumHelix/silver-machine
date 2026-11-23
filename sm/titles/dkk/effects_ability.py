from . import effects, rules
from .faults import BindingRequired
from .records import Item

F = rules.F
I = {key: offset for key, (offset, _) in Item.FIELDS.items()}
WARRIORS = (2, 3, 4, 7)


def encode_strength(base, exceptional):
    return (exceptional + 1 if base == 18 else base + 100) & 255


def decode_strength(value):
    value &= 127
    return (18, value - 1 & 255) if value <= 101 else (value - 100, 0)


def improved_strength(char, base, exceptional, previous):
    better = base > char.b[F['abilities']] or base == 18 and exceptional > char.b[F['strength_extra_base']]
    return better, encode_strength(base, exceptional) if better else previous


def stronger(current, candidate):
    return candidate if candidate[0] > current[0] or candidate[0] == 18 and candidate[1] > current[1] else current


def constitution(game, char, value):
    limits = game.assets.table('firstFixedHpLevel')
    levels = list(char.b[F['levels']:F['levels'] + 8])
    count = sum(level > 0 for level in levels)
    if not count: raise BindingRequired('Constitution recalculation divides by zero without active classes')
    total = 0
    for cls, level in enumerate(levels):
        if not level or not limits[cls]: continue
        factor = min(level, limits[cls] - 1) + int(cls == 4)
        if cls in WARRIORS:
            rate = value - 14 if 15 <= value <= 19 else 5 if value == 20 else 6 if 21 <= value <= 23 else 7 if 24 <= value <= 25 else 0
        else: rate = 2 if value > 15 else int(value == 15)
        total = (total + factor * rate) & 255
    old = char.b[F['hp_max']]
    new = (char.b[F['hp_rolled']] + total // count) & 255
    char.b[F['hp_max']] = new
    char.b[F['hp']] = (char.b[F['hp']] + new - old) & 255 if new >= old else max(0, char.b[F['hp']] - old + new)
    char.b[F['abilities'] + 9] = value
    if value >= 20:
        if not effects.has(char, 62): effects.add_effect(char, 62, 60, 255, True)
    else: effects.remove_effect(game, char, 62)


def recalculate(game, char, stat):
    if not 0 <= stat <= 5: raise ValueError('ability outside character record')
    if stat in (1, 2): return
    base = char.b[F['abilities'] + stat * 2]
    value = base
    strength = (base, char.b[F['strength_extra_base']])
    candidate, override = (0, 0), None
    for item in char.items:
        if not item[I['readied']] or item[I['powers'] + 2] <= 128: continue
        code, detail = item[I['powers'] + 2] & 127, item[I['powers'] + 1]
        if stat == 0:
            if code == 3 or code == 5 and detail == 0: candidate = (18, 100)
            elif code == 5 and 1 <= detail <= 6: candidate = (18 + detail, candidate[1])
            elif code == 8 and detail == 0 and base < 18: candidate = (base + 1, 0)
            elif code == 13: override = 3
            strength = stronger(strength, candidate)
        elif stat == 3:
            if code == 2: value += 4 if base <= 6 else 2 if base <= 13 else 1
            elif code == 8 and detail == 3 and base < 18: value += 1
            elif code == 10: value -= 2
        elif stat == 4:
            if code == 6 or code == 8 and detail == 4 and base < 18: value += 1
        else:
            if code == 6: value -= 1
            elif code == 8 and detail == 5 and base < 18: value += 1
        value &= 255
    if stat == 0:
        node = effects.has_effect(char, 38)
        if node is not None:
            candidate = decode_strength(node[3])
            if strength[0] <= 18 and strength[1] < 100:
                boosted = (strength[0] + candidate[0]) & 255
                extra = candidate[1]
                if boosted > 18:
                    if any(rules._s8(char.b[F['levels'] + cls]) > 0 for cls in WARRIORS):
                        extra = min((char.b[F['strength_extra']] + (boosted - 18) * 10) & 255, 100)
                    boosted = 18
                candidate = boosted, extra
            strength = stronger(strength, candidate)
        for ident in (113, 12):
            node = effects.has_effect(char, ident)
            if node is not None: strength = stronger(strength, decode_strength(node[3]))
        value, extra = (override, 0) if override is not None else strength
        char.b[F['strength_extra']] = extra
    elif stat == 4:
        return constitution(game, char, value)
    elif stat == 5:
        node = effects.has_effect(char, 14)
        if node is not None: value = (value + node[3]) & 255
    char.b[F['abilities'] + stat * 2 + 1] = value


def test():
    from ._effects_test import test_abilities
    test_abilities()
