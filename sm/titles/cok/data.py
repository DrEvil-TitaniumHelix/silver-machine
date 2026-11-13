import hashlib
import json
import math
import struct
from pathlib import Path

from sm import dax, ecl
from sm.files import DataError, file_path
from .intake import require_folder


class Assets:
    def __init__(self, directory=None):
        self.root = require_folder(directory)
        self.layout = json.loads(Path(__file__).with_name('tables.json').read_text(encoding='utf-8'))
        self.resident = dax.unpack_exepack(file_path(self.root, 'START.EXE').read_bytes())
        if (len(self.resident) != self.layout['resident_bytes'] or
                hashlib.sha256(self.resident).hexdigest() != self.layout['resident_sha256']):
            raise DataError('Champions resident image does not match the verified layout')

    def records(self, name):
        return dax.load(name, self.root)

    def table(self, name):
        table = self.layout['tables'][name]
        start, size = table['offset'], table['size']
        raw = self.resident[start:start + size]
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != table['sha256']:
            raise DataError('Champions table fingerprint differs: ' + name)
        return struct.unpack('<' + str(math.prod(table['shape'])) + table['format'], raw)

    def scripts(self):
        return {(dataset, block): raw[2:] for dataset in (1, 2, 3)
                for block, raw in self.records('ECL%d' % dataset).items()}

    def script_census(self):
        rows, used = [], set()
        for (dataset, block), code in self.scripts().items():
            vectors, instructions = ecl.trace(code)
            unknown = [(pc, op) for pc, (op, operands, _) in instructions.items() if operands is None]
            used.update(op for op, operands, _ in instructions.values() if operands is not None)
            rows.append(dict(dataset=dataset, block=block, bytes=len(code), vectors=vectors,
                             instructions=len(instructions), undecoded=unknown,
                             sha256=hashlib.sha256(code).hexdigest()))
        return dict(records=len(rows), instructions=sum(row['instructions'] for row in rows),
                    opcodes=len(used), undecoded=sum(len(row['undecoded']) for row in rows), blocks=rows)
