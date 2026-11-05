"""GU-103/104 intake checks: isolated settings, synthetic fingerprints, loopback HTTP."""
from contextlib import contextmanager
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import Mock, patch

from sm.titles.ssb import intake


@contextmanager
def isolated(root):
    env = dict(os.environ, SM_CONFIG_HOME=str(root))
    env.pop('SM_SECRET', None)
    with patch.dict(os.environ, env, clear=True), patch.object(intake, '_active', None):
        yield


def config(root):
    with isolated(root):
        assert intake.configured() is None
        intake.remember(root / 'first')
        assert intake.configured() == str((root / 'first').resolve())
        intake.remember(root / 'second')
        assert intake.configured() == str((root / 'second').resolve())
        intake.config_path().write_text('{broken', encoding='utf-8')
        with patch.dict(os.environ, SM_SECRET=str(root / 'override')):
            assert intake.configured() == str(root / 'override')
        try: intake.configured()
        except intake.DataError as error: assert 'Choose a folder again' in str(error)
        else: raise AssertionError('Broken config accepted')
        intake.remember(root / 'repaired')
        assert intake.configured() == str((root / 'repaired').resolve())
    env = dict(os.environ, APPDATA=str(root), XDG_CONFIG_HOME=str(root))
    env.pop('SM_CONFIG_HOME', None)
    with patch.dict(os.environ, env, clear=True):
        assert intake.config_path() == root / 'runtime-data' / 'intake.json'


def fingerprints(root):
    root.mkdir()
    path = root / 'dAtA.dAx'
    path.write_bytes(b'synthetic fixture')
    expected = intake.fingerprint(path)
    table = dict(versions=[dict(id='fixture', label='Fixture', files={'DATA.DAX': expected})], missing=[])
    assert intake.inspect_folder(str(root), table)['ok'], 'case-insensitive matching'
    assert intake.file_path(root, 'DATA.DAX').read_bytes() == b'synthetic fixture'
    path.write_bytes(b'Synthetic fixture')
    result = intake.inspect_folder(str(root), table)
    assert not result['ok'] and result['differences'][0]['found']['size'] == expected['size']
    assert result['differences'][0]['found']['sha256'] != expected['sha256']
    path.write_bytes(b'short')
    assert intake.inspect_folder(str(root), table)['differences'][0]['found']['size'] == 5
    path.unlink()
    assert intake.inspect_folder(str(root), table)['differences'][0]['found'] is None
    assert not intake.inspect_folder(str(root / 'absent'), table)['ok']
    assert not intake.inspect_folder('', table)['ok']
    path.write_bytes(b'synthetic fixture')
    generator = Path(__file__).resolve().parents[3] / 'herdr/tools/fingerprint_version.py'
    if generator.is_file():
        script = runpy.run_path(str(generator))
        with patch.dict(script['entry'].__globals__, catalog=lambda: table):
            assert script['entry'](root, 'fixture', 'Fixture') == table['versions'][0]
    else: print('SKIP intake fingerprint generator: herdr/tools/fingerprint_version.py is not shipped')
    # A case-sensitive filesystem may contain both spellings. Refuse ambiguity.
    a, b = Mock(name='first'), Mock(name='second')
    a.name, b.name = 'Data.dax', 'DATA.DAX'
    with patch.object(Path, 'iterdir', return_value=iter([a, b])):
        try: intake.file_index(root)
        except intake.DataError: pass
        else: raise AssertionError('Case-colliding filenames accepted')


def no_config(root):
    root.mkdir()
    env = dict(os.environ, SM_CONFIG_HOME=str(root), SM_SAVE_ROOT=str(root / 'saves'))
    env.pop('SM_SECRET', None)
    code = ("import sys, runpy; sys.path.insert(0, %r); import sm.dax; print('import OK'); "
            "sys.argv=['sm', 'route']; runpy.run_module('sm', run_name='__main__')") % str(Path(__file__).resolve().parents[3])
    result = subprocess.run([sys.executable, '-I', '-c', code], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'import OK' in result.stdout
    assert 'python -m sm.ui --web' in result.stderr and 'SM_SECRET' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not list(root.iterdir()), 'Import or failed CLI wrote settings/saves'


def edition_mapping(root, identity, label):
    """A verified edition selects its resident; an unrelated ST.EXE cannot override it."""
    root.mkdir()
    (root / 'data.dax').write_bytes(b'synthetic data')
    (root / 'start.exe').write_bytes(b'synthetic resident')
    (root / 'ST.EXE').write_bytes(b'wrong resident')
    baseline = dict(id='collectors-cd', label='CD', files={
        'DATA.DAX': intake.fingerprint(root / 'data.dax'),
        'ST.EXE': dict(size=1, sha256='0' * 64)})
    table = dict(versions=[baseline], missing=[])
    entry = dict(id=identity, label=label, files={
        'DATA.DAX': intake.fingerprint(root / 'data.dax'),
        'START.EXE': intake.fingerprint(root / 'start.exe')})
    generator = Path(__file__).resolve().parents[3] / 'herdr/tools/fingerprint_version.py'
    if generator.is_file():
        script = runpy.run_path(str(generator))
        with patch.dict(script['entry'].__globals__, catalog=lambda: table):
            assert script['entry'](root, identity, label) == entry
    else: print('SKIP edition fingerprint generator: herdr/tools/fingerprint_version.py is not shipped')
    table['versions'].append(entry)
    with patch.object(intake, 'catalog', return_value=table), patch.object(intake, '_active', None):
        assert intake.inspect_folder(str(root))['version_id'] == identity
        assert intake.resident_path(root).samefile(root / 'start.exe')
        # Two editions can share every fingerprinted file; both are named.
        alias_id, alias_label = 'alias', 'Alias'
        table['versions'].append(dict(entry, id=alias_id, label=alias_label))
        shared = intake.inspect_folder(str(root))
        assert shared['version'] == label + ' / ' + alias_label
        assert shared['version_ids'] == [identity, alias_id]
        assert shared['version_id'] == identity
        assert intake.resident_path(root).samefile(root / 'start.exe')
        (root / 'start.exe').write_bytes(b'altered resident')
        assert not intake.inspect_folder(str(root))['ok']
        try: intake.resident_path(root)
        except intake.DataError: pass
        else: raise AssertionError('Altered resident accepted')


def http(root, original, port=0):
    from sm.ui.web import Server, BUILD_ID
    from sm.titles.ssb.ui import start_session
    root.mkdir(parents=True, exist_ok=True)
    factory = Mock(side_effect=lambda: start_session(root=root / 'saves'))
    def request(server, path, body=None, *, status=200, headers=None):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               body=None if body is None else json.dumps(body),
                               headers=dict({'Content-Type': 'application/json', 'X-SM-Build': BUILD_ID}, **(headers or {})))
            response = connection.getresponse()
            raw = response.read()
            assert response.status == status, (path, response.status, raw[:300])
            return json.loads(raw) if response.getheader('Content-Type') == 'application/json' else raw.decode()
        finally:
            connection.close()
    with isolated(root / 'config'):
        intake.remember(root)
        with Server(port=0, save_root=root / 'saves', session_factory=factory) as refused:
            assert refused.controller is None and not factory.called
            assert 'does not match a supported version' in refused.intake_error
        intake.config_path().unlink()
        with Server(port=port, save_root=root / 'saves', session_factory=factory) as server:
            worker = Thread(target=server.serve)
            worker.start()
            try:
                page = request(server, '/')
                tagline = 'plays the SSI Gold Box games from your own copy.'
                line = 'Fan project; not affiliated with or endorsed by Wizards of the Coast, SSI or their successors. Requires your own copy of the games.'
                assert tagline in page and line in page and 'Alpha 0.1' in page and BUILD_ID in page
                assert 'folder-form' in page
                assert not factory.called and not intake.config_path().exists()
                request(server, '/decision', status=409)
                request(server, '/key', {'keysym': 'Return'}, status=409)
                request(server, '/intake', {'folder': original}, status=403, headers={'Origin': 'https://example.invalid'})
                request(server, '/intake', {'folder': original}, status=409, headers={'X-SM-Build': 'stale'})
                assert not factory.called and not intake.config_path().exists()
                wrong = request(server, '/intake', {'folder': str(root)}, status=422)
                assert not wrong['ok'] and wrong['differences'] and wrong['expected'] == [v['label'] for v in intake.catalog()['versions']]
                assert not factory.called and not intake.config_path().exists()
                correct = request(server, '/intake', {'folder': original})
                assert correct['ok'] and factory.call_count == 1 and server.controller is not None
                assert intake.configured() == str(Path(original).resolve())
                page = request(server, '/')
                assert tagline in page and line in page and '<canvas' in page and BUILD_ID in page
                state = request(server, '/version')
                assert state['version'] == intake.VERSION and state['content'] == intake.inspect_folder(original)['version']
                assert request(server, '/decision')['hash']
                assert 'folder-form' in request(server, '/setup')
                changed = request(server, '/intake', {'folder': original})
                assert changed['restart'] and factory.call_count == 1
                request(server, '/intake', {'folder': str(root)}, status=422)
                assert intake.configured() == str(Path(original).resolve()), 'Refusal replaced working config'
                with patch.dict(os.environ, SM_SECRET=original):
                    request(server, '/intake', {'folder': original}, status=409)
                # The shared endpoint follows the selected intake's environment name.
                with patch.object(intake, 'ENV', 'SM_SYNTHETIC'), patch.dict(os.environ, SM_SYNTHETIC=original):
                    assert request(server, '/intake')['source'] == 'SM_SYNTHETIC'
                    refused = request(server, '/intake', {'folder': original}, status=409)
                    assert refused['message'].startswith('SM_SYNTHETIC overrides')
            finally:
                server.stopping = True
                worker.join(3)
                assert not worker.is_alive()
        # A persisted valid folder starts next time without another prompt.
        factory.reset_mock()
        with Server(port=0, save_root=root / 'saves', session_factory=factory) as server:
            assert factory.call_count == 1 and server.controller is not None
    print('Alpha intake HTTP: empty / refused / verified / persisted / change / branding PASS (port %d)' % port)


def test():
    original = str(intake.require_folder())
    with TemporaryDirectory(prefix='intake-test-') as temporary:
        root = Path(temporary)
        config(root / 'config')
        fingerprints(root / 'files')
        for identity, label in (('gog', 'GOG'),):
            edition_mapping(root / identity, identity, label)
        no_config(root / 'empty')
    from sm.titles.ssb.ui.screen import SAVE_ROOT
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='intake-http-', dir=SAVE_ROOT) as temporary:
        http(Path(temporary), original)
