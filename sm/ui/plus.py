import json
from pathlib import Path
import tempfile


DEFAULTS = dict(effect_scale=1.0, message_hold=400, equipment_icon=False,
                look='original', vga_frame='dqk', mods_folder='')


def validate(values):
    if not isinstance(values, dict) or set(values) - DEFAULTS.keys() - {'sound'}:
        raise ValueError('Unknown Plus setting')
    for key, value in values.items():
        if key == 'effect_scale':
            valid = type(value) in (int, float) and 0 <= value <= 10
        elif key == 'message_hold':
            valid = type(value) is int and value in (400, 800, 1200, 2000)
        elif key == 'look': valid = value in ('original', 'vga')
        elif key == 'vga_frame': valid = value in ('ssb', 'dqk')
        elif key == 'mods_folder': valid = isinstance(value, str) and len(value) <= 4096 and '\0' not in value
        else:
            valid = type(value) is bool
        if not valid: raise ValueError('Invalid ' + key)
    return values


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        try: self.data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError: self.data = {}
        if not isinstance(self.data, dict): raise ValueError('Invalid Plus settings')
        validate(self.data.get('options', {}))
        if not isinstance(self.data.get('manual_bodies', {}), dict): raise ValueError('Invalid icon choices')

    @property
    def options(self):
        return dict(DEFAULTS, **self.data.get('options', {}))

    def write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream)
                stream.write('\n')
            temporary.replace(self.path)
            self.data = data
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)

    def update(self, values):
        self.write(dict(self.data, options=dict(self.options, **validate(values))))

    def remember_body(self, key, body):
        self.write(dict(self.data, manual_bodies=dict(self.data.get('manual_bodies', {}), **{key: body})))


def bug_report(server, values, build):
    from datetime import datetime, timezone
    import uuid
    if not isinstance(values, dict) or set(values) != {'slot', 'steps', 'expected', 'actual'}:
        raise ValueError('Provide save slot, steps, expected and actual results')
    for key, value in values.items():
        if not isinstance(value, str) or len(value) > (32 if key == 'slot' else 8000):
            raise ValueError('Invalid ' + key)
    if not values['steps'].strip() or not values['actual'].strip():
        raise ValueError('Describe the steps and what happened')
    decision = server.controller.session.decision if server.controller else None
    report = dict(format=1, created=datetime.now(timezone.utc).isoformat(), version=server.intake.VERSION,
                  build=build, title=server.profile.name, **values,
                  decision={k: decision.get(k) for k in ('kind', 'i', 'hash')} if decision else None,
                  options=server.preferences()['options'])
    directory = server.intake.config_path().parent / 'bug-reports'
    directory.mkdir(parents=True, exist_ok=True)
    name = 'bug-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.json'
    path = directory / name
    with path.open('x', encoding='utf-8') as stream: json.dump(report, stream, indent=2); stream.write('\n')
    return dict(path=str(path), name=name, report=report)
