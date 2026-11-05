"""Case-insensitive content paths; no title selection or import-time I/O."""
from pathlib import Path


class DataError(ValueError):
    """An actionable intake failure, safe to show before starting a session."""


def file_index(folder):
    """DOS filenames are case-insensitive, even on a case-sensitive filesystem."""
    result = {}
    for path in Path(folder).iterdir():
        if not path.is_file():
            continue
        key = path.name.upper()
        if key in result:
            raise DataError('Ambiguous filenames: %s and %s.' % (result[key].name, path.name))
        result[key] = path
    return result


def file_path(folder, name):
    path = Path(folder) / name
    if path.is_file():
        return path
    return file_index(folder).get(name.upper(), path)
