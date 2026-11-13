from sm.titles.ssb import data as ssb_data
import struct

from sm import dax; from sm.titles.ssb import rec
from sm.titles.ssb.state import Char
from sm.titles.ssb.units import shops, creation, magic
from sm.titles.ssb.units._c3_test import fresh, scripted, replayed, caster_setup


def setup(game):
    caster_setup(game)
    game.s.party[0].b[:16] = bytes([4]) + b'TEST' + bytes(11)
    game.s.party[0].b[0x11] = 18
    game.s.r1[0x36D] = 16


def item(value=10, weight=1):
    result = bytearray(67)
    result[0x2E] = 5
    rec.wrw(result, 0x3A, value); rec.wrw(result, 0x37, weight)
    return result


def output(game):
    return ''.join(game.vm.out)


def check_take():
    def pile(game):
        setup(game); game.s.party.append(Char(bytes(game.s.party[0].b)))
        game.s.treasure_money[5] = 20; game.s.treasure_items = [item()]
    entries = [('SHOP_MENU', 'items'), ('LIST', None), ('SHOP_MENU', 'money'), ('LIST', None),
               ('SHOP_MENU', 'char-down'), ('SHOP_MENU', 'money'), ('LIST', 5), ('NUMBER', 3),
               ('LIST', None), ('SHOP_MENU', 'items'), ('LIST', None), ('SHOP_MENU', 'exit')]
    game = replayed(pile, shops.take, scripted(entries))
    assert shops.coins(game.s.party[0])[5] == 0 and shops.coins(game.s.party[1])[5] == 3
    assert game.s.treasure_money[5] == 17 and len(game.s.treasure_items) == 1
    game = replayed(pile, shops.take, scripted([('SHOP_MENU', 'money'), ('LIST', 5), ('NUMBER', 20)]))
    assert not any(game.s.treasure_money) and game.s.treasure_items
    game = replayed(pile, shops.take, scripted([('SHOP_MENU', 'items'), ('LIST', 0)]))
    assert not game.s.treasure_items and game.s.treasure_money[5] == 20
    game = fresh(scripted([('LIST', 5), ('NUMBER', 20), ('LIST', None)])); pile(game)
    c = game.s.party[0]; c.items = [item(weight=65535)]
    shops.coin_menu(game, c)
    assert 'Overloaded' in output(game) and game.s.treasure_money[5] == 20 and not shops.coins(c)[5]


def check_training():
    game = fresh(scripted([('CREATE_TRAIN', 'cancel'), ('CREATE_TRAIN', 'train')])); setup(game)
    c = game.s.party[0]; game.s.r1[0x2A8] = ssb_data.stexe()[0x4C99]
    c.b[0x1A6] = 4
    assert not creation.train(game, c) and 'we only train conscious people' in output(game)
    c.b[0x1A6] = 0; game.s.r1[0x2A8] = 0
    assert not creation.train(game, c) and "We don't train that class here" in output(game)
    assert '8DBB' not in game.s.g
    game.s.r1[0x2A8] = ssb_data.stexe()[0x4C99]
    assert not creation.train(game, c) and 'Not Enough Experience' in output(game)
    struct.pack_into('<i', c.b, 0x12C, creation.xp_for(0, 2))
    assert not creation.train(game, c) and c.b[0x111] == 1
    assert creation.train(game, c) and c.b[0x111] == 2 and 'Congratulations...' in output(game)
    c.b[0x6B], c.b[0x111] = 1, 7
    struct.pack_into('<i', c.b, 0x12C, 1000000)
    assert not creation.train(game, c) and game.s.g['8DBB'] == 1


def check_temple():
    game = fresh(lambda *a, **k: 0); setup(game); c = game.s.party[0]
    for service, text in ((0, 'is not blind'), (1, 'is not Diseased'), (6, 'is not poisoned'),
                          (7, 'is not dead yet'), (8, 'is not cursed'), (9, 'is not petrified')):
        shops.cure(game, c, service); assert 'TEST ' + text in output(game)
    for status, text in ((6, 'must be raised from dead'), (7, 'can only be healed by a stonemason'), (8, 'is not here')):
        c.b[0x1A6] = status; assert not shops.cure(game, c, 2); assert text in output(game)
    c.b[0x1A6] = 0; c.b[0x1B5] = c.b[0x70]
    shops.cure(game, c, 2); assert 'has no need of healing' in output(game)
    for service in (2, 3, 4, 5):
        c.b[0x1B5] = 1; shops.cure(game, c, service); assert 'TEST is healed' in output(game)
    for effect, service, text in ((0x21, 0, 'can see!'), (0x1F, 1, 'is cured'),
                                  (0x37, 6, 'is no longer poisoned'), (0x24, 8, 'The curse has been lifted!')):
        magic.add_effect(game, c, effect, 0)
        assert shops.cure(game, c, service); assert text in output(game)
    c.b[0x1A6] = 7; assert shops.cure(game, c, 9); assert 'is turned to flesh' in output(game)
    c.b[0x1A6], c.b[0x6B] = 6, 1; assert not shops.cure(game, c, 7); assert 'cannot be raised' in output(game)
    c.b[0x6B] = 6; assert shops.cure(game, c, 7); assert 'is ressurected' in output(game)
    game = replayed(setup, shops.temple, scripted([('SHOP_MENU', 'heal'), ('LIST', 0), ('LIST', 1), ('LIST', None), ('SHOP_MENU', 'exit')]))
    assert 'TEST is not blind' in output(game) and 'TEST is not Diseased' in output(game)


def check_shop_appraisal():
    game = fresh(scripted([('SHOP_MENU', 'sell'), ('SHOP_MENU', 'identify')])); setup(game); c = game.s.party[0]
    assert not shops.buy(game, c, [item()]) and 'Not enough Money.' in output(game)
    shops.set_money(c, 1000)
    assert not shops.buy(game, c, [item(weight=65535)]) and 'OverLoaded' in output(game)
    assert shops.buy(game, c, [item(10)]) and 'TEST buys a ' in output(game)
    assert shops.sell(game, c, 0) and 'Sold!' in output(game)
    it = item(); it[0x35] = 7; c.items = [it]
    assert shops.identify(game, c, it) and 'It looks like some sort of ' in output(game)
    shops.appraise(game, c); assert 'No Gems or Jewelry' in output(game)
    def valuables(game):
        setup(game); shops.put_coins(game.s.party[0], [0, 0, 0, 0, 0, 1, 1])
    entries = [('SHOP_MENU', 'gems'), ('SHOP_MENU', 'keep'), ('SHOP_MENU', 'jewelry'), ('SHOP_MENU', 'sell')]
    game = replayed(valuables, lambda g: shops.appraise(g, g.s.party[0]), scripted(entries))
    assert len(game.s.party[0].items) == 1 and game.s.party[0].items[0][0x31] == 0x7A
    assert shops.coins(game.s.party[0])[5:] == [0, 0] and shops.total(shops.coins(game.s.party[0])) > 0
    game = fresh(scripted([('LIST', 0), ('SHOP_MENU', 'sell'), ('SHOP_MENU', 'sell'), ('LIST', None)])); setup(game)
    game.s.party[0].items = [item()]
    shops.item_menu(game, game.s.party[0], 'temple')
    assert not game.s.party[0].items and 'Sold!' in output(game)


def check_vault():
    def vault_setup(game):
        setup(game); game.s.g['vault.image'] = struct.pack('<7i', 0, 0, 0, 0, 0, 10, 0)
        shops.set_money(game.s.party[0], 3)
    entries = [('SHOP_MENU', 'view'), ('SHOP_MENU', 'deposit money'), ('LIST', 3), ('NUMBER', 3),
               ('SHOP_MENU', 'exit'), ('SHOP_MENU', 'take'), ('LIST', 5), ('NUMBER', 4), ('LIST', None), ('SHOP_MENU', 'exit')]
    game = replayed(vault_setup, shops.vault, scripted(entries))
    assert struct.unpack('<7i', game.s.g['vault.image']) == (0, 0, 0, 3, 0, 6, 0)
    assert shops.coins(game.s.party[0]) == [0, 0, 0, 0, 0, 4, 0]


def test():
    check_take(); check_training(); check_temple(); check_shop_appraisal(); check_vault(); check_vault_source(); check_name_callers()


def check_name_callers():
    from sm.titles.ssb.units import camp
    game = fresh(lambda *a, **k: 0); setup(game); c = game.s.party[0]; c.b[0x1A7] = 1
    for action, expected in ((camp.cast_command, 'has no spells memorized'),
                             (magic.memorize, 'cannot memorize any spells'), (magic.scribe, 'has no copyable scrolls')):
        c.b[0x1E:0x69] = bytes(75); c.b[0x132:0x14E] = bytes(28); c.items = []; action(game, c)
        assert game.vm.service_names[-1][2:5:2] == (expected, True)
        c.b[0x1A7] = 0; action(game, c)
        assert 'is in no condition to ' in game.vm.service_names[-1][2]; c.b[0x1A7] = 1
    for key, typ, status, text in (('heal',0x44,0,'is healed'), ('stone',None,7,'is changed back to flesh'),
            ('poison',0x37,0,'is detoxified'), ('raise',None,6,'has been raised from the dead'),
            ('curse',0x24,0,'is relieved of a curse'), ('disease',0x22,0,'is cured of disease'), ('sight',0x21,0,'regains sight')):
        c.effects = [bytearray([typ])+bytearray(8)] if typ else []; c.b[0x1A6] = status; c.b[0x6B] = 0
        have = dict.fromkeys(('heal','stone','poison','raise','curse','disease','sight'), 0); have[key] = 1
        camp.fix_status(game, have); assert game.vm.service_names[-1][2] == text
    c.effects = [bytearray([t])+bytearray(8) for t in (0x37,0x22)]; have.update(poison=1,disease=1)
    camp.fix_status(game, have); assert [n[2] for n in game.vm.service_names[-2:]] == ['is detoxified','is cured of disease']
    shops.name_message(game,c,'will be gone',clear=False)
    assert not game.vm.service_names[-1][4]
    shops.name_message(game,c,'bids you farewell')
    assert game.vm.service_names[-1][2]=='bids you farewell' and all(n[4] for n in game.vm.service_names)
    game,c = fresh(lambda *a,**k:0),None; setup(game); c=game.s.party[0]; game.s.g['combat.active']=1; c.effects=[]
    game.player=lambda kind,options,g,**info: options.index('no') if info.get('purpose')=='cure healthy' else 0
    shops.paladin_power(game,c,'cure'); assert not getattr(game.vm,'service_names',None)


def check_vault_source():
    import tempfile
    from pathlib import Path
    from sm.titles.ssb import save, host
    root=Path(__file__).resolve().parents[4]/'local'; root.mkdir(exist_ok=True)
    data=save.load(slot='B'); header=struct.pack('<7i',0,0,0,0,0,7,0)
    data['vault']=dict(header=header,items=[rec.Item(bytes(item()))])
    with tempfile.TemporaryDirectory(dir=root) as directory:
        for name,raw in save.dump(data).items(): (Path(directory)/name).write_bytes(raw)
        game=host.Game(lambda kind,options,g,**info:options.index('exit'),slot='B',directory=directory,engines=True)
        shops.vault(game)
        assert game.s.g['vault.image']==header+bytes(item())


if __name__ == '__main__':
    test()
    print('services: Take, training, temple, shop/appraisal, vault and replay PASS')
