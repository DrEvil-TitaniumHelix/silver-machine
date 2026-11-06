"""Alpha content intake: metadata fingerprints, profile config and read-only paths."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from sm.files import DataError, file_index, file_path

VERSION = 'Alpha 0.1.2'
ENV = 'SM_SECRET'
TABLE = Path(__file__).with_name('supported_versions.json')
HELP = 'Run python -m sm.ui --web to choose your own copy, or set SM_SECRET to its folder.'
# GU-106: same EXEPACK layout and DS tables; only the resident filename varies.
RESIDENT_FILES = {'collectors-cd': 'ST.EXE', 'gog': 'START.EXE'}
_active = None


def catalog():
    return json.loads(TABLE.read_text(encoding='utf-8'))


def config_path():
    """SM_CONFIG_HOME isolates tests; the default directory has no product name."""
    root = os.environ.get('SM_CONFIG_HOME')
    if root:
        return Path(root).expanduser() / 'intake.json'
    base = (os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') if os.name == 'nt' else (
        os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return Path(base) / 'runtime-data' / 'intake.json'


def configured():
    """The environment override takes precedence, including over a broken config."""
    override = os.environ.get(ENV, '').strip()
    if override:
        return override
    path = config_path()
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise DataError('Cannot read folder settings at %s: %s. Choose a folder again.' % (path, error)) from error
    if not isinstance(value, dict) or not isinstance(value.get('folder'), str) or not value['folder'].strip():
        raise DataError('Invalid folder settings at %s. Choose a folder again.' % path)
    return value['folder']


def remember(folder):
    """Atomic profile write; never stores content or changes the source folder."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'folder': str(Path(folder).expanduser().resolve())}, stream)
            stream.write('\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return dict(size=path.stat().st_size, sha256=digest.hexdigest())


def inspect_folder(folder, table=None):
    """Return the closest supported entry's complete differences; never execute data."""
    table = catalog() if table is None else table
    result = dict(ok=False, folder=str(folder), version=None, differences=[],
                  expected=[v['label'] for v in table['versions']], missing=table['missing'])
    try:
        if not isinstance(folder, str) or not folder.strip():
            raise DataError('Enter the folder containing your own copy.')
        root = Path(folder).expanduser().resolve()
        result['folder'] = str(root)
        files = file_index(root)
        wanted = {name for version in table['versions'] for name in version['files']}
        actual = {name: fingerprint(files[name]) for name in wanted if name in files}
        comparisons, matches = [], []
        for version in table['versions']:
            differences = []
            for name, expected in version['files'].items():
                found = actual.get(name)
                if found != expected:
                    differences.append(dict(name=name, expected=expected, found=found))
            if not differences:
                matches.append(version)
            comparisons.append((len(differences), version['label'], differences))
        if matches:
            # Identical data cannot identify its distributor; retain the first mapping and show every match.
            result.update(ok=True, version=' / '.join(v['label'] for v in matches),
                          version_id=matches[0]['id'], version_ids=[v['id'] for v in matches],
                          message='Supported copy verified.')
            return result
        if comparisons:
            _, closest, differences = min(comparisons)
            result.update(closest=closest, differences=differences)
        result['message'] = 'This folder does not match a supported version. Expected: %s. Choose another folder.' % ', '.join(result['expected'])
    except (OSError, ValueError) as error:
        result['message'] = 'Cannot use this folder: %s Expected: %s. Choose another folder.' % (error, ', '.join(result['expected']))
    return result


def require_folder():
    """Pin a verified root for the life of this process; changing settings needs restart."""
    global _active
    if _active is None:
        folder = configured()
        if not folder:
            raise DataError('No game folder is configured. ' + HELP)
        result = inspect_folder(folder)
        if not result['ok']:
            details = []
            for diff in result['differences']:
                expected, found = diff['expected'], diff['found']
                details.append('%s: expected %d bytes / SHA-256 %s; found %s' % (
                    diff['name'], expected['size'], expected['sha256'],
                    'missing' if found is None else '%d bytes / SHA-256 %s' % (found['size'], found['sha256'])))
            raise DataError('\n'.join([result['message'], *details, HELP]))
        _active = result
    return Path(_active['folder'])


def resident_path(folder):
    """Select the resident file from the verified edition, never from file presence."""
    root = Path(folder).resolve()
    edition = _active if _active and root == Path(_active['folder']) else inspect_folder(str(root))
    if not edition['ok']:
        raise DataError(edition['message'])
    return file_path(root, RESIDENT_FILES.get(edition['version_id'], 'ST.EXE'))


class ContentFolder(os.PathLike):
    """Compatibility with save.SECRET and old default arguments, without import I/O."""
    def __fspath__(self):
        return str(require_folder())


def test():
    from sm.titles.ssb._intake_test import test as check
    check()
