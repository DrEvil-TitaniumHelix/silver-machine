import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from sm.titles.cok import intake


def test():
    files = {'GAME.DAX': b'one', 'ECL1.DAX': b'two'}
    table = dict(missing='Choose the folder of your own copy.', versions=[dict(id='gog', label='GOG', files={
        n: dict(size=len(b), sha256=hashlib.sha256(b).hexdigest()) for n, b in files.items()})])
    with TemporaryDirectory() as root:
        root = Path(root)
        (root / 'other.txt').write_bytes(b'x')
        wrong = intake.inspect_folder(root, table)
        assert not wrong['ok'] and 'does not match a supported Champions copy' in wrong['message'] and not wrong['differences'], wrong
        for name, raw in files.items(): (root / name).write_bytes(raw)
        good = intake.inspect_folder(root, table)
        assert good['ok'] and good['version'] == 'GOG', good
        (root / 'ECL1.DAX').unlink()
        missing = intake.inspect_folder(root, table)
        assert not missing['ok'] and 'missing a file (ECL1.DAX)' in missing['message'], missing
        (root / 'ECL1.DAX').write_bytes(b'tw0')
        changed = intake.inspect_folder(root, table)
        assert not changed['ok'] and 'a file that differs from the supported GOG edition (ECL1.DAX)' in changed['message'], changed
        bad = intake.inspect_folder('', table)
        assert not bad['ok'] and bad['message'].startswith('Cannot use this folder'), bad
    return 'PASS wrong folder, missing, changed, accepted'


if __name__ == '__main__': print(test())
