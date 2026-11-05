"""Release boundary negatives use synthetic files in disposable directories."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from sm import release


def test():
    with TemporaryDirectory(prefix='release-guard-') as temporary:
        root = Path(temporary); (root / 'sm').mkdir(); (root / 'docs').mkdir()
        names = ['README.md', 'LICENSE', 'docs/ALPHA_BUG_REPORT.md', release.MANIFEST, 'sm/example.py']
        manifest = dict(files=names, excluded=['sm/titles/dqk/'], allowed_phrases=[])
        for name in names: (root / name).write_text('synthetic source\n', encoding='utf8')
        def write(): (root / release.MANIFEST).write_text(json.dumps(manifest), encoding='utf8')
        def refused(reason):
            write()
            try: release.collect(root)
            except ValueError as error: assert reason in str(error), error
            else: raise AssertionError('Release guard accepted ' + reason)
        write()
        assert set(release.collect(root)) == set(names)
        excluded = root / 'sm/titles/dqk/nested/private.bin'
        excluded.parent.mkdir(parents=True); excluded.write_bytes(b'synthetic')
        assert set(release.collect(root)) == set(names)
        names.append('sm/titles/dqk/nested/private.bin'); refused('Excluded manifest path'); names.pop()
        sibling = root / 'sm/titles/dqk_other.py'; sibling.write_text('synthetic')
        refused('Outside manifest'); sibling.unlink()
        for suffix in release.FORBIDDEN:
            name = 'sm/leak' + suffix; names.append(name); (root / name).write_bytes(b'synthetic')
            refused('Forbidden extension'); names.pop(); (root / name).unlink()
        for name in ('../outside.py', 'herdr/private.md', 'local/private.md', 'CLAUDE.md', 'RULINGS.md', 'sm/../private.py', 'C:/escape.py'):
            names.append(name); refused('Disallowed manifest path'); names.pop()
        (root / 'sm/unlisted.py').write_text('synthetic'); refused('Outside manifest'); (root / 'sm/unlisted.py').unlink()
        for term in ('Gold' + ' Box', 'D' + '&D', 'Advanced Dungeons ' + '& Dragons', 'Forgotten' + ' Realms', 'Dark Queen of ' + 'Krynn'):
            (root / 'sm/example.py').write_text(term); refused('Unapproved mark')
        (root / 'sm/example.py').write_text('synthetic source\n'); write()
        archive = release.build(root)
        with ZipFile(archive) as z:
            assert set(z.namelist()) == set(names)
            assert all(z.read(name) == raw for name, raw in release.collect(root).items())
