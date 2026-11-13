import hashlib, json, os, tempfile
from pathlib import Path
from sm.files import DataError, file_index

def _version():
    try: return 'Beta ' + json.loads((Path(__file__).parents[2] / 'release_manifest.json').read_text(encoding='utf-8'))['version']
    except (OSError, ValueError, KeyError): return 'Development'


VERSION = _version()
SETUP = {'supported-intro': 'Supported: the GOG release (recommended, buy it).',
         'recommend': '',
         'locations': ("Usual location: the game's folder under C:\\Program Files (x86)\\GOG Galaxy\\Games\\ or C:\\GOG Games\\: "
                       'the folder that holds START.EXE and the .DAX files. Browse opens the Windows folder dialog.')}
ENV = 'SM_COK'
TABLE = Path(__file__).with_name('supported_versions.json')
HELP = 'Run python -m sm.ui --web --title cok to choose your own copy, or set SM_COK to its folder.'
_active = None


def catalog(): return json.loads(TABLE.read_text(encoding='utf-8'))


def config_path():
    root = os.environ.get('SM_CONFIG_HOME')
    if root: return Path(root).expanduser() / 'cok-intake.json'
    base = (os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') if os.name == 'nt' else (
        os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return Path(base) / 'runtime-data' / 'cok-intake.json'


def configured():
    override = os.environ.get(ENV, '').strip()
    if override: return override
    try: value = json.loads(config_path().read_text(encoding='utf-8'))
    except FileNotFoundError: return None
    except (OSError, ValueError) as error: raise DataError('Cannot read Champions folder settings: %s. Choose a folder again.' % error) from error
    if not isinstance(value, dict) or not isinstance(value.get('folder'), str) or not value['folder'].strip():
        raise DataError('Invalid Champions folder settings. Choose a folder again.')
    return value['folder']


def remember(folder):
    path = config_path(); path.parent.mkdir(parents=True, exist_ok=True); temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name); json.dump({'folder': str(Path(folder).expanduser().resolve())}, stream); stream.write('\n')
        temporary.replace(path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def fingerprint(path):
    return dict(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def inspect_folder(folder, table=None):
    table = catalog() if table is None else table
    result = dict(ok=False, folder=str(folder or ''), version=None, differences=[],
                  expected=[v['label'] for v in table['versions']], missing=table['missing'])
    try:
        if not isinstance(folder, (str, os.PathLike)) or not str(folder).strip(): raise DataError('Enter the folder containing your own copy.')
        root = Path(folder).expanduser().resolve(); result['folder'] = str(root)
        files = file_index(root); best = None
        for version in table['versions']:
            differences = []
            for name, expected in version['files'].items():
                found = fingerprint(files[name]) if name in files else None
                if found != expected: differences.append(dict(name=name, expected=expected, found=found))
            if not differences:
                result.update(ok=True, version=version['label'], version_id=version['id'], message='Supported copy verified.'); return result
            if best is None or len(differences) < len(best[1]): best = (version['label'], differences)
        if best: result.update(closest=best[0], differences=best[1])
        if best and all(d['found'] is None for d in best[1]): result['differences'] = []
        result['message'] = refusal(best, sum(len(v['files']) for v in table['versions'][:1]), ', '.join(result['expected']))
    except (OSError, ValueError) as error:
        result['message'] = 'Cannot use this folder: %s Expected: %s. Choose another folder.' % (error, ', '.join(result['expected']))
    return result


def refusal(best, total, expected):
    differences = best[1] if best else []
    missing = [d['name'] for d in differences if d['found'] is None]
    changed = [d['name'] for d in differences if d['found'] is not None]
    if not best or len(missing) == total:
        return 'This folder does not match a supported Champions copy. Expected: %s. Choose another folder.' % expected
    if missing:
        return ('This Champions copy is missing %s (%s). Point to the complete game folder, or reinstall it, then choose it again.'
                % ('a file' if len(missing) == 1 else '%d files' % len(missing), ', '.join(missing[:3]) + (', ...' if len(missing) > 3 else '')))
    return ('This Champions copy has %s from the supported %s edition (%s): changed or damaged. Reinstall or verify it in your '
            'store, then choose it again.' % ('a file that differs' if len(changed) == 1 else '%d files that differ' % len(changed), best[0],
                                              ', '.join(changed[:3]) + (', ...' if len(changed) > 3 else '')))


def require_folder(folder=None):
    global _active
    if folder is not None:
        result = inspect_folder(folder)
        if not result['ok']: raise DataError(result['message'])
        return Path(result['folder'])
    if _active is None:
        configured_folder = configured()
        if not configured_folder: raise DataError('No Champions folder is configured. ' + HELP)
        result = inspect_folder(configured_folder)
        if not result['ok']: raise DataError(result['message'] + ' ' + HELP)
        _active = result
    return Path(_active['folder'])


def test():
    from ._intake_test import test as check
    return check()
