"""Build the review cut: python -m sm.release (stdlib only, no game folder needed)."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'sm/release_manifest.json'
FORBIDDEN = {'.dat', '.exe', '.png', '.avi', '.bin'}
MARKS = re.compile(r'Gold\s+Box|\b(?:A\s*)?D\s*&\s*D\b|(?:Advanced\s+)?Dungeons\s*(?:&|and)\s*Dragons|'
                  r'Forgotten\s+Realms|Dragon\s*lance|Wizards\s+of\s+the\s+Coast|'
                  r'Secret\s+of\s+the\s+Silver\s+Blades|Dark\s+Queen\s+of\s+Krynn|'
                  r'(?:Champions|Death\s+Knights)\s+of\s+Krynn|Pool(?:s)?\s+of\s+(?:Radiance|Darkness)|'
                  r'Curse\s+of\s+the\s+Azure\s+Bonds|(?:Treasures|Gateway)\s+of\s+the\s+Savage\s+Frontier', re.I)


def collect(root=ROOT):
    """Fail closed on unlisted runtime files, forbidden paths/assets, symlinks and unapproved marks."""
    root = Path(root).resolve()
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf8'))
    names = manifest['files']
    if len(names) != len(set(names)): raise ValueError('Duplicate manifest path')
    required = {'README.md', 'LICENSE', 'docs/ALPHA_BUG_REPORT.md', MANIFEST}
    if not required <= set(names): raise ValueError('Manifest omits a required release file')
    def excluded(name):
        return any(name == entry.rstrip('/') or (entry.endswith('/') and name.startswith(entry))
                   for entry in manifest.get('excluded', ()))
    errors, files = [], {}
    actual = {p.relative_to(root).as_posix() for p in (root / 'sm').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and not excluded(p.relative_to(root).as_posix())}
    errors += ['Outside manifest: ' + n for n in sorted(actual - set(names))]
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or path.as_posix() != name
                or not (name.startswith('sm/') or name in required)):
            errors.append('Disallowed manifest path: ' + name); continue
        if excluded(name): errors.append('Excluded manifest path: ' + name); continue
        source = root / name
        if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != root and p.is_relative_to(root)) or not source.resolve().is_relative_to(root):
            errors.append('Link or escaped path: ' + name); continue
        if source.suffix.lower() in FORBIDDEN:
            errors.append('Forbidden extension: ' + name); continue
        if source.suffix.lower() not in {'.py', '.js', '.java', '.html', '.css', '.json', '.md'} and name != 'LICENSE':
            errors.append('Unsupported source type: ' + name); continue
        if not source.is_file(): errors.append('Missing file: ' + name); continue
        raw = source.read_bytes()
        try: text = raw.decode('utf8')
        except UnicodeDecodeError: errors.append('Not UTF-8 source: ' + name); continue
        for allowance in manifest['allowed_phrases']:
            if name in allowance['paths']: text = text.replace(allowance['text'], '')
        for match in MARKS.finditer(text):
            errors.append('Unapproved mark: %s: %s' % (name, match.group()))
        files[name] = raw
    if errors: raise ValueError('\n'.join(errors))
    return files


def build(root=ROOT):
    root = Path(root).resolve()
    files = collect(root)  # Validate the exact bytes to be archived, before creating output.
    output = root / 'local/silvermachine-alpha-0.1.2.zip'
    if output.parent.is_symlink() or not output.resolve().is_relative_to(root): raise ValueError('Release output escaped local/')
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.zip.tmp')
    if temporary.is_symlink(): raise ValueError('Release staging path is a link')
    try:
        with ZipFile(temporary, 'w', compression=ZIP_DEFLATED) as archive:
            for name, raw in sorted(files.items()):
                info = ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
        temporary.replace(output)
    finally: temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.files.json').write_text(json.dumps({n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}, indent=2) + '\n', encoding='utf8')
    print('%s: %d files; SHA-256 %s' % (output, len(files), digest))
    return output


def test():
    from sm._release_test import test as check
    check()


if __name__ == '__main__':
    try: build()
    except (OSError, ValueError) as error: sys.exit(str(error))
