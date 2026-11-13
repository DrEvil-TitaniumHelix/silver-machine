from dataclasses import dataclass, field
import hashlib

from sm.files import DataError
from . import rules
from .creation import F, dice
from .faults import BindingRequired
from .records import Item

I = {name: offset for name, (offset, _) in Item.FIELDS.items()}
TYPE, DURATION, STRENGTH_BYTE, ON_REMOVE = 0, 1, 3, 4
OKAY, ANIMATED_STATUS, DEAD, UNCONSCIOUS, DYING = 0, 1, 6, 4, 5
AI_NPC = 0xB3
STR, INT, WIS, DEX, CON, CHA = range(6)
POISON_DAMAGE, SLOW_POISON, ANIMATED_EFFECT, HASTED, POISONED, HELPLESS = 15, 22, 32, 39, 55, 31
HP_ZERO_IDS = dict(offset=51732, size=16, sha256='1a40f73783bfa88c29ee03d2a4fce28000fc3c760207120a80a8ef62efd953df')
HIT_POINTS_ZERO = 13
EMPTY, ROLL, RECORD, COMBAT = 'empty', 'roll', 'record', 'combat'

HANDLER_NAMES = {
    1: 'Bless', 2: 'Curse', 3: 'SticksToSnakes', 5: 'None', 7: 'SetAttackDamage', 8: 'ProtEvil', 9: 'ProtGood', 10: 'ResistCold', 11: 'Charm', 12: 'StrengthBonus',
    13: 'ReviveAsMad', 14: 'Friends', 15: 'SlowPoisonHit', 16: 'ReadMagic', 17: 'Shield', 18: 'HalfElfResistance', 19: 'None', 20: 'ResistFire', 21: 'Silence',
    22: 'SlowPoisonEnd', 23: 'SpiritualHammer', 24: 'None', 25: 'Invisible', 26: 'DwarfHitBonus', 27: 'Helpless', 28: 'MirrorImage', 29: 'Enfeeble', 30: 'Coughing',
    31: 'Helpless', 32: 'TransformOnDeath', 33: 'Blind', 34: 'Diseased', 35: 'Confusion', 36: 'BestowCurse', 37: 'Blinking', 38: 'StrengthBonus', 39: 'Hasted',
    40: 'ClearStinkingCloud', 41: 'ProtNormalMissiles', 42: 'Slow', 43: 'DiseaseStrength', 44: 'DiseaseHitPoints', 45: 'ProtEvil', 46: 'ProtGood', 47: 'DwarfGiantDefense',
    48: 'Immolate', 49: 'Prayer', 50: 'FireVulnerable', 51: 'Helpless', 52: 'Helpless', 53: 'Helpless', 54: 'ColdVulnerable', 55: 'Poisoned', 56: 'RenewInvisibility',
    57: 'CombatBonus', 58: 'EndTransformation', 59: 'CancelDamage', 60: 'ExplodeOnRemoval', 61: 'RingFireRes', 62: 'ConRegeneration', 63: 'MinorGlobe', 64: 'PoisonAttack',
    65: 'WeakPoisonAttack', 66: 'ZapNearbyEnemy', 67: 'DisarmAttacker', 68: 'QueueExplosion', 69: 'ParalyzingHit', 70: 'CreateAcidPool', 71: 'ReflectSpell', 72: 'DragonFear',
    73: 'ImmuneBreath', 74: 'RandomDispelMagic', 75: 'DragonSlayer', 76: 'GateInDeadAllies', 77: 'Berserk', 79: 'EvilStench', 80: 'RemoveAcidPool', 81: 'ParalyzingStrike',
    82: 'FrightenAllEnemies', 86: 'StrongPoisonAttack', 87: 'SlightPoisonAttack', 88: 'GhoulPara', 89: 'Displaced', 91: 'Taunted', 92: 'None', 93: 'HalfPierceBash',
    94: 'ConSpellSave', 95: 'ElfResistance', 96: 'ImmuneSleepCharm', 97: 'ImmuneParalysis', 98: 'ImmuneCold', 99: 'ImmuneParalysisPoison', 100: 'HalfSlashPierce', 101: 'HolyWater',
    102: 'NoneB', 103: 'NeedMagicWeapon', 105: 'RangerDamageBonus', 106: 'EndActions', 107: 'ConfusedBerserk', 108: 'LastingInvisibility', 109: 'NoneC', 110: 'RecalcLevelBucket',
    111: 'Fear', 112: 'ZapAttacker', 113: 'GiantStrength', 114: 'Dragonlance', 115: 'TypeDamageBonus', 116: 'PoisonResistance', 117: 'Disruption', 118: 'AttackPenaltyTwo', 119: 'AttackPenaltyOne'}
EMPTY_IDS = frozenset((5, 12, 14, 16, 19, 24, 38, 55, 91, 92, 102, 109, 113, 116))

CONDITIONS = {1: (37, 25), 2: (88, 87, 86, 81, 69, 64, 65), 3: (69, 64, 65, 81, 86, 87), 4: (7, 29, 75, 105, 114, 115, 117), 5: (59, 28, 41, 100, 103, 93, 101, 112),
              6: (71, 59, 61, 10, 20, 102, 17, 28, 98, 73, 63), 7: (51, 52, 53, 31, 3, 27), 8: (82, 89, 56), 9: (71, 116, 92, 59, 95, 96, 97, 98, 99, 18, 63),
              10: (7, 118, 119, 57, 1, 2, 33, 36, 49, 26, 75), 11: (33, 17, 8, 9, 45, 46, 30), 12: (94, 8, 9, 10, 17, 20, 33, 36, 45, 46, 49, 61, 99, 50, 54),
              13: (68, 67, 13, 32, 70), 14: (6, 85, 84, 83, 78, 74, 4, 90, 104), 15: (79, 76, 72, 66, 48, 21, 30, 11, 77), 16: (25, 37, 47, 89), 17: (1, 2, 11),
              18: (39, 42), 19: (23, 56, 11), 20: (50, 54), 21: (35,), 24: (82,)}
AURA_IDS = frozenset((21, 45, 46, 49))


@dataclass
class Roll:
    attacker: object = None
    attack: int = 0
    save: int = 0
    damage: int = 0
    element: int = 0
    effect: int = 0
    spell: int = 0
    multi_target: int = 0
    morale: int = 0
    save_type: int = 0
    save_passed: bool = False
    dice_count: int = 0
    multiplier: int = 1
    target_veto: bool = False
    in_combat: bool = False
    services: dict = field(default_factory=dict)

    def call(self, name, *args):
        if name not in self.services: raise BindingRequired('Champions combat service not bound: ' + name)
        return self.services[name](*args)


def has_effect(char, kind):
    return next((e for e in char.effects if e[TYPE] == kind), None)


def add_effect(char, kind, minutes, strength, on_remove):
    char.effects.append(bytearray([kind, minutes & 255, minutes >> 8 & 255, strength & 255, int(on_remove), 0, 0, 0, 0]))


def _hp_zero_ids(game):
    raw = game.assets.resident[HP_ZERO_IDS['offset']:HP_ZERO_IDS['offset'] + HP_ZERO_IDS['size']]
    if hashlib.sha256(raw).hexdigest() != HP_ZERO_IDS['sha256']: raise DataError('Champions effect table differs')
    return raw


def _drop(char, node):
    for at, effect in enumerate(char.effects):
        if effect is node:
            del char.effects[at]
            return


def remove_effect(game, char, kind, node=None):
    node = node if node is not None else has_effect(char, kind)
    if node is None: return
    if node[ON_REMOVE]: call_handler(game, char, kind, node, True)
    _drop(char, node)
    if kind == 14: recalc_ability(game, char, CHA)
    if kind in (12, 38): recalc_ability(game, char, STR)


def effect_kind(kind):
    if kind not in HANDLER_NAMES: return None
    if kind in EMPTY_IDS: return EMPTY
    return RECORD if kind in _RECORD else ROLL if kind in _ROLL else COMBAT


def call_handler(game, char, kind, node, removed, roll=None):
    roll = roll or (game.battle.context(char) if getattr(game, 'battle', None) is not None else
                    Roll(services={'message': lambda who, text: window_message(game, who, text)}))
    state = effect_kind(kind)
    if state == COMBAT and kind not in _CALLABLE and (handler := getattr(game, 'combat_effect', None)):
        return handler(char, kind, node, removed, roll)
    if kind == 80 and not roll.in_combat: return
    if kind in (89, 105, 114, 115, 117) and not roll.in_combat: return
    if kind == 7 and not roll.in_combat:
        dice(game.s, 1, 6); return
    if state is None or state == COMBAT and kind not in _CALLABLE:
        raise BindingRequired('Champions effect handler not bound: %d %s' % (kind, HANDLER_NAMES.get(kind, '(none in the original)')))
    if state != EMPTY: _handlers()[kind](game, char, node, removed, roll)


def trigger_condition(game, condition, char, roll):
    if condition in (6, 9): check_spell_resistance(game, char, roll)
    for kind in CONDITIONS.get(condition, ()):
        node = has_effect(char, kind)
        if node is None and kind in AURA_IDS: node = aura_node(game, char, kind, roll)
        if node is not None: call_handler(game, char, kind, node, False, roll)


def aura_node(game, char, kind, roll):
    for other in (game.s.chars() if roll.in_combat else game.s.party):
        node = has_effect(other, kind)
        if node is not None and (not roll.in_combat or roll.call('in_aura_range', other, char, 6 if kind == 49 else 1)): return node
    return None


def check_spell_resistance(game, char, roll):
    resist = char.b[F['magic_resistance']]
    if not resist or not roll.effect or roll.damage and not roll.element & 8: return
    if dice(game.s, 1, 100) <= (resist + (11 - roll.call('caster_level', roll.spell)) * 5) & 255:
        roll.damage = 0
        if roll.effect not in (91, 82): roll.effect = 0


def nullify(roll, effect=0):
    if not effect or roll.effect == effect:
        roll.damage = 0
        roll.effect = 0


def add_if_no_lock(game, char, kind, strength, minutes):
    if getattr(game, 'effect_busy', False): return False
    add_effect(char, kind, minutes, strength, True)
    return True


def say(roll, char, text):
    if 'message' in roll.services: roll.call('message', char, text)


def window_message(game, char, text):
    queue, vm = getattr(game, 'presentation', None), getattr(game, 'vm', None)
    if queue is None or vm is None: return
    count = len(queue); vm.hold(1)
    if len(queue) > count: queue[-1]['message'] = (bytes(char.b[1:1 + char.b[0]]).decode('cp437'), text)


def small_damage(game, char, amount, roll):
    roll.damage = amount
    trigger_condition(game, 6, char, roll)
    trigger_condition(game, 20, char, roll)
    if roll.damage > 0 and char.b[F['active']]:
        char.b[F['hp']] -= min(roll.damage, char.b[F['hp']])


def kill(game, char, status, roll):
    if char.b[F['status']] in (6, 7, 8): return
    char.b[F['status']], char.b[F['active']], char.b[F['hp']] = status, 0, 0
    for kind in _hp_zero_ids(game): remove_effect(game, char, kind)
    if has_effect(char, 77) is not None and char.b[F['npc']] == AI_NPC: char.b[F['side']] = 0
    trigger_condition(game, HIT_POINTS_ZERO, char, roll)


def restore_hp(game, char, amount, in_combat=False):
    if char.b[F['status']] not in (OKAY, ANIMATED_STATUS, UNCONSCIOUS, DYING) or char.b[F['hp']] >= char.b[F['hp_max']]: return False
    char.b[F['hp']] = min((char.b[F['hp']] + amount) & 255, char.b[F['hp_max']])
    if not char.b[F['active']]:
        if char.b[F['status']] == DYING: char.b[F['status']] = UNCONSCIOUS
        if char.b[F['status']] == UNCONSCIOUS and not in_combat:
            char.b[F['status']], char.b[F['active']] = OKAY, 1
    return True


def _end_ai(char, keep_flag=False):
    if char.b[F['npc']] == AI_NPC:
        char.b[F['npc']] = 0
        if not keep_flag: char.b[F['auto_combat']] = 0


def _take_over(char):
    char.b[F['auto_combat']] = 1
    char.b[F['npc']] = AI_NPC if char.b[F['npc']] <= 0x7F or char.b[F['npc']] == AI_NPC else 0xB2


def _handlers():
    def add(field_name, amount):
        def run(g, c, n, r, x): setattr(x, field_name, getattr(x, field_name) + amount)
        return run

    def bless(g, c, n, r, x): x.morale += 5; x.attack += 1
    def curse(g, c, n, r, x): x.morale = max(x.morale - 5, 0); x.attack -= 1
    def prot(alignments):
        def run(g, c, n, r, x):
            if x.attacker is not None and x.attacker.b[F['alignment']] in alignments: x.save += 2; x.attack -= 2
        return run
    def resist_cold(g, c, n, r, x):
        if x.element & 2: x.damage >>= 1; x.save += 3
    def resist_fire(g, c, n, r, x):
        if not r and x.element & 1: x.damage >>= 1; x.save += 3
    def shield(g, c, n, r, x):
        if c.b[F['ac']] < 57: c.b[F['ac']] = 57
        x.save += 1
        if x.spell == 15: x.damage = 0
    def half_elf(g, c, n, r, x):
        if dice(g.s, 1, 100) <= 30: nullify(x, 11); nullify(x, 53)
    def elf(g, c, n, r, x):
        if dice(g.s, 1, 100) <= 90: nullify(x, 53); nullify(x, 11)
    def invisible(g, c, n, r, x):
        if not r and (x.attacker is None or has_effect(x.attacker, 24) is None): x.target_veto = True; x.attack -= 4
    def blind(g, c, n, r, x):
        x.attack -= 4; x.save -= 4; c.b[F['ac']] = (c.b[F['ac']] - 4) & 255; c.b[F['ac'] + 1] = (c.b[F['ac'] + 1] - 4) & 255
    def enfeeble(g, c, n, r, x): x.damage -= x.damage >> 2
    def bestow(g, c, n, r, x): x.attack -= 4; x.save -= 4
    def hasted(g, c, n, r, x):
        if not n[STRENGTH_BYTE] & 0x10:
            n[STRENGTH_BYTE] = (n[STRENGTH_BYTE] + 0x10) & 255
            say(x, c, 'ages')
            age = int.from_bytes(c.b[F['age']:F['age'] + 2], 'little') + 1
            c.b[F['age']:F['age'] + 2] = (age & 0xFFFF).to_bytes(2, 'little')
        x.multiplier *= 2
    def slow(g, c, n, r, x): x.multiplier >>= 1
    def dwarf_giant(g, c, n, r, x):
        if x.attacker is not None and x.attacker.b[F['creature_type']] & 4: x.attack -= 4
    def prayer(g, c, n, r, x):
        if c.b[F['side']] == n[STRENGTH_BYTE] >> 4 & 1: x.save += 1; x.attack += 1
        else: x.attack -= 1; x.save -= 1
    def fire_vuln(g, c, n, r, x):
        if x.element & 2: x.save += 2
        elif x.element & 1 and not x.save_passed: x.damage <<= 1
    def cold_vuln(g, c, n, r, x):
        if x.element & 1: x.save += 2
        elif x.element & 2 and not getattr(g, 'recently_saved', False): x.damage <<= 1
    def combat_bonus(g, c, n, r, x):
        x.attack += 2
        c.b[F['ac']] = (c.b[F['ac']] + 2) & 255; c.b[F['ac'] + 1] = (c.b[F['ac'] + 1] + 2) & 255
    def cancel(g, c, n, r, x): nullify(x); x.damage = 0
    def ring_fire(g, c, n, r, x):
        if x.element & 1:
            for _ in range(x.dice_count):
                x.damage = (x.damage - 2) & 255
                if x.damage < x.dice_count: x.damage = x.dice_count
            x.save += 4
            if not x.element & 8: nullify(x)
    def minor_globe(g, c, n, r, x):
        if x.spell > 0 and rules.tables().u8('spellTbl', (x.spell - 1) * 16 + 1) < 4: nullify(x)
    def immune_breath(g, c, n, r, x):
        if x.element & 0x20: nullify(x); say(x, c, 'is unaffected')
    def con_save(g, c, n, r, x):
        if x.save_type in (0, 2, 4):
            con = c.b[F['abilities'] + 2 * CON + 1]
            bonus = 1 if 4 <= con <= 6 else 2 if 7 <= con <= 10 else 3 if 11 <= con <= 13 else 4 if 14 <= con <= 17 else 5 if 18 <= con <= 20 else None
            if bonus is None: raise BindingRequired('Constitution outside the original save table: undefined there')
            x.save += bonus
    def immune_sleep(g, c, n, r, x): nullify(x, 11); nullify(x, 53)
    def immune_para(g, c, n, r, x): nullify(x, 52)
    def immune_cold(g, c, n, r, x):
        if x.element & 2: nullify(x)
    def immune_poison(g, c, n, r, x):
        nullify(x, POISONED); nullify(x, 52)
        if x.save_type == 0: x.save = 100

    def charm(g, c, n, r, x):
        if r:
            c.b[F['side']] = (n[STRENGTH_BYTE] & 0x40) // 64
            _end_ai(c)
        else:
            if not n[STRENGTH_BYTE] & 0x20:
                n[STRENGTH_BYTE] = (n[STRENGTH_BYTE] + 0x20 + c.b[F['side']] * 64) & 255
                c.b[F['side']], c.b[F['auto_combat']] = n[STRENGTH_BYTE] // 128, 1
                if c.b[F['npc']] <= 127: c.b[F['npc']] = AI_NPC
                x.call('clear_target', c)
            x.morale = 100
    def poison_tick(g, c, n, r, x):
        if add_if_no_lock(g, c, POISON_DAMAGE, n[STRENGTH_BYTE], 10) and c.b[F['hp']] > 1:
            x.element = 0
            small_damage(g, c, 1, x)
    def slow_poison_end(g, c, n, r, x):
        if has_effect(c, POISONED) is not None:
            kill(g, c, DEAD, x)
            remove_effect(g, c, POISONED)
        g.effect_busy = True
        try: remove_effect(g, c, POISON_DAMAGE)
        finally: g.effect_busy = False
    def hammer(g, c, n, r, x):
        if not r:
            from .magic import ensure_hammer
            return ensure_hammer(g, c)
        for item in c.items:
            if item[I['type']] == 6 and item[I['name_ids'] + 2] == 121:
                _drop_item(c, item)
                break
        rules.recalc_stats(c)
    def disease_strength(g, c, n, r, x):
        if add_if_no_lock(g, c, 43, n[STRENGTH_BYTE], 60):
            at = F['abilities'] + 2 * STR + 1
            if c.b[at] > 3: say(x, c, 'is weakened'); c.b[at] -= 1
            elif has_effect(c, HELPLESS) is None: add_effect(c, HELPLESS, 0, 255, False)
    def disease_hp(g, c, n, r, x):
        if add_if_no_lock(g, c, 44, n[STRENGTH_BYTE], 10):
            if c.b[F['hp']] > 1:
                x.element = 0
                small_damage(g, c, 1, x)
            elif has_effect(c, HELPLESS) is None: add_effect(c, HELPLESS, 0, 255, False)
    def diseased(g, c, n, r, x):
        call_handler(g, c, 43, n, r, x)
        call_handler(g, c, 44, n, r, x)
    def renew_invisibility(g, c, n, r, x): add_effect(c, 25, 1, 12, False)
    def lasting_invisibility(g, c, n, r, x): add_effect(c, 25, 255, 255, False)
    def end_transformation(g, c, n, r, x):
        if r:
            add_effect(c, 59, 0, 255, False); add_effect(c, 60, 3, 255, True)
            for kind in (4, ANIMATED_EFFECT, 48, 57): remove_effect(g, c, kind)
    def regeneration(g, c, n, r, x):
        if add_if_no_lock(g, c, 62, n[STRENGTH_BYTE], 60) and restore_hp(g, c, 1, x.in_combat):
            say(x, c, 'is fully healed' if c.b[F['hp']] == c.b[F['hp_max']] else 'is partially healed')
    def berserk(g, c, n, r, x):
        if not r:
            if getattr(g, 'battle', None) is not None: return g.battle.berserk(g.battle.index(c), 77, n)
            c.b[F['auto_combat']] = 1
            c.b[F['npc']] = AI_NPC if c.b[F['npc']] <= 0x7F or c.b[F['npc']] == AI_NPC else 0xB2
            return
        _end_ai(c)
        c.b[F['side']] = 0
    def confused_berserk(g, c, n, r, x):
        if not r:
            if getattr(g, 'battle', None) is None: raise BindingRequired('Champions effect handler not bound: 107 ConfusedBerserk outside combat')
            return g.battle.berserk(g.battle.index(c), 107, n)
        _end_ai(c, keep_flag=True)
        c.b[F['side']] = n[STRENGTH_BYTE]
    def level_bucket(g, c, n, r, x):
        if r:
            former = c.b[F['former_levels'] + 7] if rules._earlier_class_active(rules._view(rules.Character, c.b)) else 0
            c.b[F['knight_bracket']] = (former + c.b[F['levels'] + 7] - 1 & 0x7FFF) // 5 + 1
    def fear(g, c, n, r, x):
        if r:
            _end_ai(c)
            if x.in_combat: x.call('set_turned', c, 0)

    def revive_as_mad(g, c, n, r, x):
        if c.b[F['status']] == OKAY: return
        c.b[F['status']],c.b[F['active']]=OKAY,1
        if not x.call('revive',c,20,'goes mad!'): return
        for kind in (ANIMATED_EFFECT,48,57): add_effect(c,kind,0,255,False)
        add_effect(c,58,6,255,True)
        remove_effect(g,c,13,n)
        c.b[F['memorized']:F['memorized']+58]=bytes(58)

    def transform_on_death(g, c, n, r, x):
        if c.b[F['status']] != OKAY:
            c.b[F['status']], c.b[F['active']] = OKAY, 1
            if x.call('revive', c, 20, 'Arises in a new form'):
                add_effect(c, 59, 0, 255, False); add_effect(c, 60, 3, 255, False); add_effect(c, 66, 0, 255, False)
                for kind in (ANIMATED_EFFECT, 4, 48, 57, 58): remove_effect(g, c, kind)
    def disarm(g, c, n, r, x):
        item, attacker = x.call('damaging_weapon', x.attacker), x.attacker
        if (attacker.b[F['abilities'] + 2 * DEX + 1] - 3 <= dice(g.s, 1, 20) and x.spell == 0 and item is not None and not item[I['cursed']] and
                not x.services.get('exploding', lambda: 0)() and x.call('distance', attacker, c) == 1):
            say(x, attacker, 'loses his weapon')
            if item[I['type']] == 6 and item[I['name_ids'] + 2] == 121: return
            x.call('unready_item', attacker, item)
            x.call('bank_weapon', attacker, bytes(item))
            _drop_item(attacker, item)
            x.call('clear_weapon', attacker)
    def dragon_fear(g, c, n, r, x):
        for target in x.call('neighbours', c):
            if target.b[F['side']] != c.b[F['side']] and has_effect(target, 92) is None and not x.call('saving_throw', target, 4, 0):
                x.call('add_with_message', target, 111, 0, 0, 'is terrified')
                if has_effect(target, 111) is not None:
                    _take_over_flee(target, x)

    def helpless(g, c, n, r, x):
        x.call('end_actions', c)
    def silence(g, c, n, r, x): x.call('block_casting', c, 'is silenced')
    def coughing(g, c, n, r, x):
        x.call('block_casting', c, 'is coughing')
        rules.recalc_stats(c)
        ac = c.b[F['ac'] + 1]
        c.b[F['ac']] = c.b[F['ac'] + 1] = ac - 2 if ac > 52 else 50
    def mirror(g, c, n, r, x):
        if dice(g.s, 1, n[STRENGTH_BYTE] // 16 + 1) > 1 and (not x.spell or not x.multi_target):
            nullify(x)
            say(x, c, 'lost an image')
            n[STRENGTH_BYTE] = n[STRENGTH_BYTE] - 1 & 255
            if not n[STRENGTH_BYTE]: remove_effect(g, c, 28, n)
    def prot_missiles(g, c, n, r, x):
        item = x.call('damaging_weapon', x.attacker)
        if item is not None and not item[I['bonus']] and x.call('distance', x.attacker, c) > 1 and dice(g.s, 1, 100) <= 100:
            say(x, c, 'Avoids it')
            x.damage, x.attack = 0, -1
    def blinking(g, c, n, r, x):
        if g.battle.record(g.battle.index(c))['initiative'] == 0: x.attack, x.target_veto = -1, True
    def clear_cloud(g, c, n, r, x):
        if x.in_combat: x.call('clear_cloud', c, n[STRENGTH_BYTE] // 16)

    return {1: bless, 2: curse, 8: prot((2, 5, 8)), 9: prot((0, 3, 6)), 45: prot((2, 5, 8)), 46: prot((0, 3, 6)), 10: resist_cold, 20: resist_fire, 17: shield, 18: half_elf, 25: invisible,
            29: enfeeble, 33: blind, 36: bestow, 39: hasted, 42: slow, 47: dwarf_giant, 49: prayer, 50: fire_vuln, 54: cold_vuln, 57: combat_bonus, 59: cancel, 61: ring_fire, 63: minor_globe,
            73: immune_breath, 94: con_save, 95: elf, 96: immune_sleep, 97: immune_para, 98: immune_cold, 99: immune_poison, 118: add('attack', -2), 119: add('attack', -1),
            11: charm, 15: poison_tick, 22: slow_poison_end, 23: hammer, 34: diseased, 43: disease_strength, 44: disease_hp, 56: renew_invisibility, 58: end_transformation, 62: regeneration,
            77: berserk, 107: confused_berserk, 108: lasting_invisibility, 110: level_bucket, 111: fear, 13: revive_as_mad, 32: transform_on_death, 67: disarm, 72: dragon_fear,
            21: silence, 27: helpless, 28: mirror, 30: coughing, 31: helpless, 37: blinking, 40: clear_cloud, 41: prot_missiles,
            51: helpless, 52: helpless, 53: helpless, 106: helpless}


def _take_over_flee(target, roll):
    target.b[F['auto_combat']] = 1
    if target.b[F['npc']] <= 0x7F: target.b[F['npc']] = AI_NPC
    roll.call('clear_target', target)
    roll.call('set_turned', target, 1)


def _drop_item(char, item):
    for at, held in enumerate(char.items):
        if held is item:
            del char.items[at]
            return


_ROLL = frozenset((1, 2, 8, 9, 10, 17, 18, 20, 25, 29, 33, 36, 39, 42, 45, 46, 47, 49, 50, 54, 57, 59, 61, 63, 73, 94, 95, 96, 97, 98, 99, 118, 119))
_RECORD = frozenset((11, 15, 22, 23, 34, 43, 44, 56, 58, 62, 77, 107, 108, 110, 111))
_CALLABLE = frozenset((13, 21, 27, 28, 30, 31, 32, 37, 40, 41, 51, 52, 53, 67, 72, 106))


def recalc_ability(game, char, ability):
    b = char.b
    base_of = lambda a: b[F['abilities'] + 2 * a]
    value, extra = base_of(ability), b[F['strength_extra_base']]
    override, candidate, candidate_extra = None, 0, 0

    def clamp():
        nonlocal value, extra
        if candidate > value or candidate == 18 and candidate_extra > extra:
            value, extra = candidate, candidate_extra

    for item in char.items:
        special, effect = item[I['powers'] + 2], item[I['powers'] + 1]
        if special <= 0x80 or not item[I['readied']]: continue
        code = special & 0x7F
        if ability == STR:
            if code == 3: candidate, candidate_extra = 18, 100
            elif code == 5:
                if effect == 0: candidate, candidate_extra = 18, 100
                elif 1 <= effect <= 6: candidate = 18 + effect
            elif code == 8 and base_of(STR) < 18 and effect == STR: candidate, candidate_extra = base_of(STR) + 1, 0
            elif code == 13: override = 3
            clamp()
        elif ability == CON:
            if code == 6 or code == 8 and base_of(CON) < 18 and effect == CON: value += 1
        elif ability == INT:
            if code == 8 and base_of(INT) < 18 and effect == INT: value += 1
            elif code == 12: override = 7
            elif code == 13: override = 3
        elif ability == WIS:
            if code == 8 and effect == WIS and base_of(WIS) < 18: value += 1
        elif ability == DEX:
            if code == 2:
                base = base_of(DEX)
                value += 4 if base <= 6 else 2 if base <= 13 else 1
            elif code == 8 and base_of(DEX) < 18 and effect == DEX: value += 1
            elif code == 10: value -= 2
        elif ability == CHA:
            if code == 6: value -= 1
            elif code == 8 and base_of(CHA) < 18 and effect == CHA: value += 1

    at = F['abilities'] + 2 * ability + 1
    if ability == STR:
        node = has_effect(char, 38)
        if node is not None:
            candidate, candidate_extra = _decode_strength(node)
            if value <= 18 and extra < 100:
                candidate += value
                if candidate > 18:
                    if any(b[F['levels'] + c] > 0 or b[F['former_levels'] + c] > 0 for c in (2, 7, 4)):
                        candidate_extra = min(b[F['strength_extra']] + (candidate - 18) * 10, 100)
                    candidate = 18
            clamp()
        for kind in (113, 12):
            node = has_effect(char, kind)
            if node is not None:
                candidate, candidate_extra = _decode_strength(node)
                clamp()
        if override is not None: b[at], b[F['strength_extra']] = override, 0
        else: b[at], b[F['strength_extra']] = value, extra
    elif ability == CON: _set_constitution(game, char, value)
    elif ability == DEX: b[at] = override if override is not None else value
    elif ability == CHA:
        node = has_effect(char, 14)
        b[at] = value + (node[STRENGTH_BYTE] if node is not None else 0)


def _decode_strength(node):
    raw = node[STRENGTH_BYTE] & 0x7F
    return (18, raw - 1) if raw <= 101 else (raw - 100, 0)


def _set_constitution(game, char, value):
    from .creation import tables
    b, t = char.b, tables(game.assets)
    total, count, saved = 0, 0, b[F['hp_max']]

    def bonus(cls, level):
        nonlocal total
        if t.hitDiceLimit[cls] <= level: level = t.hitDiceLimit[cls] - 1
        if cls == 4 and (b[F['dual_threshold']] == 0 or b[F['former_levels'] + 4] == b[F['dual_threshold']]): level += 1
        if cls in (2, 4, 7):
            gain = (value - 14) * level if 15 <= value <= 19 else level * 5 if value == 20 else level * 6 if 21 <= value <= 23 else level * 7 if 24 <= value <= 25 else 0
        else:
            gain = level * 2 if value > 15 else level if value == 15 else 0
        total = (total + gain) & 255

    b[F['hp_max']] = b[F['hp_rolled']]
    for cls in range(8):
        former = b[F['former_levels'] + cls]
        if former > 0: bonus(cls, former)
        level = b[F['levels'] + cls]
        if level > 0: count += 1
        if t.hitDiceLimit[cls] < level: level = t.hitDiceLimit[cls]
        if level > b[F['dual_threshold']]: bonus(cls, level - b[F['dual_threshold']])
    b[F['hp_max']] = (b[F['hp_max']] + total // count) & 255
    if b[F['hp_max']] > saved: b[F['hp']] = (b[F['hp']] + b[F['hp_max']] - saved) & 255
    elif b[F['hp_max']] < saved:
        b[F['hp']] = b[F['hp']] - (saved - b[F['hp_max']]) if b[F['hp']] > saved - b[F['hp_max']] else 0
    b[F['abilities'] + 2 * CON + 1] = value
    if value >= 20:
        if has_effect(char, 62) is None: add_effect(char, 62, 60, 255, True)
    else: remove_effect(game, char, 62)


def age_effects(game, char, step):
    effects = char.effects
    def following(node):
        for at, effect in enumerate(effects):
            if effect is node: return effects[at + 1] if at + 1 < len(effects) else None
        return None
    timed = lambda effect: effect[DURATION] | effect[DURATION + 1] << 8
    tail, node, done, flag = effects[-1] if effects else None, effects[0] if effects else None, False, False
    while node is not None and not done:
        done = node is tail
        duration = timed(node)
        if duration == 0: node = following(node)
        elif step < duration:
            duration -= step
            node[DURATION], node[DURATION + 1] = duration & 255, duration >> 8
            flag = True
            node = following(node)
        else:
            after, was_second = following(node), len(effects) > 1 and effects[1] is node
            remove_effect(game, char, node[TYPE], node)
            node = effects[0] if was_second and effects else after if after is not None and any(after is e for e in effects) else None
    while node is not None:
        if timed(node): flag = True
        node = following(node)
    return flag


def advance(game, amount=5, unit=1, flags=None):
    from . import camp
    s, t = game.s, camp.tables(game.assets)
    clock = s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7]
    for _ in range(amount):
        clock[unit] += 1
        camp.validate_clock(game, clock)
    s.r0[camp.CLOCK_CELL:camp.CLOCK_CELL + 7] = clock
    if flags is None: flags = [True] * len(s.party)
    if not any(flags): return
    total = amount
    for u in range(unit, 1, -1): total *= t.scale[u - 1]
    while total > 0:
        step = min(total, 10)
        for index, char in enumerate(s.party):
            if flags[index]: flags[index] = age_effects(game, char, step)
        total -= step
