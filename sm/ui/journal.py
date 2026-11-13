import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import parse_qs, urlsplit
import zlib

from sm.files import file_index

PDF_SHA256 = 'f26c90627c1cdb2dfacf92ad3f795545a659c7b8c6d0f44a8996f8f3a9a48a74'
PAGE_RANGES = ((1, 7, 16), (8, 18, 17), (19, 28, 18), (29, 37, 19),
               (38, 44, 20), (45, 50, 21), (51, 56, 22), (57, 66, 23), (67, 72, 24))
PAGES = {n: page for low, high, page in PAGE_RANGES for n in range(low, high + 1)}
BOOKS = dict(ssb=dict(file='adventurers journal.pdf', sha256=PDF_SHA256, pages=PAGES, highest=72, machine_read=True),
             cok=dict(file='journal.pdf', sha256=None, pages={}, highest=88))
REFERENCE = re.compile(r'\bjournal\s+entr(?:y|ies)\s*(?:number\s*|no\.?\s*|#\s*)?(\d{1,3})\b', re.I)


LOCK_FILE = 'ECL2.DAX'


def lock_path(title):
    return Path(__file__).parents[1] / 'titles' / title / 'journal_lock.json'


def lock_key(salt, title, raw):
    return hashlib.sha256(salt + b'|SilverMachine journal v1|' + title.encode() + b'|' + raw).digest()


def _mask(key, nonce, tag, data):
    return bytes(a ^ b for a, b in zip(data, hashlib.shake_256(key + nonce + tag).digest(len(data))))


def seal(texts, title, raw, key_file=LOCK_FILE):
    salt = secrets.token_bytes(16)
    key, entries = lock_key(salt, title, raw), {}
    for number, text in texts.items():
        nonce, tag = secrets.token_bytes(16), str(int(number)).encode()
        data = _mask(key, nonce, tag, zlib.compress(text.encode('utf-8'), 9))
        entries[tag.decode()] = (nonce + hmac.new(key, nonce + tag + data, 'sha256').digest() + data).hex()
    return dict(format=1, title=title, salt=salt.hex(), key_file=key_file, count=len(entries), entries=entries)


def unseal(lock, key, number):
    try:
        blob, tag = bytes.fromhex(lock['entries'][str(number)]), str(number).encode()
        nonce, mac, data = blob[:16], blob[16:48], blob[48:]
        if not hmac.compare_digest(mac, hmac.new(key, nonce + tag + data, 'sha256').digest()): return None
        return zlib.decompress(_mask(key, nonce, tag, data)).decode('utf-8')
    except (KeyError, TypeError, ValueError, zlib.error): return None


def references(text, highest=72):
    return sorted({int(m[1]) for m in REFERENCE.finditer(text) if 1 <= int(m[1]) <= highest})


class Book:
    def __init__(self, intake, title='ssb'):
        self.intake, self.signature, self.mapped = intake, None, False
        self.spec, self.title, self.key, self.key_signature = BOOKS[title], title, None, None

    def entry_text(self, number):
        try:
            if not self.intake._active: return None
            lock = json.loads(lock_path(self.title).read_text(encoding='utf-8'))
            path = file_index(self.intake._active['folder'])[str(lock['key_file']).upper()]
            stat = path.stat()
            signature = (str(path), stat.st_size, stat.st_mtime_ns, lock['salt'])
            if signature != self.key_signature:
                self.key = lock_key(bytes.fromhex(lock['salt']), self.title, path.read_bytes())
                self.key_signature = signature
            return unseal(lock, self.key, number)
        except (OSError, KeyError, TypeError, ValueError): return None

    def path(self):
        if not self.intake._active: return None
        root = Path(self.intake._active['folder'])
        try:
            return next((p for p in root.iterdir() if p.name.casefold() == self.spec['file'] and p.is_file()), None)
        except OSError: return None

    def info(self):
        path = self.path()
        if path is None: return dict(available=False, mapped=False, machine=bool(self.spec.get('machine_read')))
        try:
            stat = path.stat()
            signature = (str(path), stat.st_size, stat.st_mtime_ns)
            if signature != self.signature:
                with path.open('rb') as stream:
                    self.mapped = hashlib.file_digest(stream, 'sha256').hexdigest() == self.spec['sha256']
                self.signature = signature
            return dict(available=True, mapped=self.mapped, file=path.name, machine=bool(self.spec.get('machine_read')))
        except OSError: return dict(available=False, mapped=False)


class Journal:
    def __init__(self, controller, intake, title='ssb'):
        self.controller, self.book = controller, Book(intake, title)
        self.root = Path(controller.files.root)
        self.session, self.slot, self.cursor = None, 'New game', 0
        self.history, self.entries, self.error = [], {}, ''
        self.observe()

    def sidecar(self, slot):
        if slot != 'resume' and slot not in tuple('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
            raise ValueError('Invalid journal slot')
        return self.root / ('journal-' + slot + '.json')

    def observe(self):
        controller = self.controller
        session, game = controller.session, controller.session.game
        if self.session is not session:
            self.session, self.cursor = session, 0
            self.slot = getattr(session, 'journal_slot', None) or getattr(game, 'slot', None) or 'New game'
            self.history, self.entries, self.error = [], {}, ''
            if self.slot != 'New game':
                try:
                    saved = json.loads(self.sidecar(self.slot).read_text(encoding='utf-8'))
                    if not isinstance(saved, dict) or not isinstance(saved.get('history'), list) or not isinstance(saved.get('entries'), dict):
                        raise ValueError('Invalid journal data')
                    self.history, self.entries = saved['history'], saved['entries']
                except FileNotFoundError: pass
                except (OSError, ValueError): self.error = 'Saved journal could not be read; new observations are kept for this session.'
        output = game.vm.out
        if len(output) <= self.cursor: return
        delta = ''.join(output[self.cursor:]).strip()
        self.cursor = len(output)
        if not delta: return
        meta = self.place()
        scene = ''.join(output[getattr(game.vm, 'text_start', 0):]).strip()
        cited = references(scene, self.book.spec['highest'])
        note = dict(kind='text', text=delta, **meta)
        if not self.history or any(self.history[-1].get(k) != v for k, v in note.items()):
            self.history.append(note)
        for number in cited:
            key = str(number)
            citation = dict(text=scene, order=len(self.history), **meta)
            citations = self.entries.setdefault(key, [])
            marker = (getattr(game.vm, 'text_epoch', 0), key)
            if getattr(self, 'scene_session', None) is not session:
                self.scene_session, self.scenes = session, {}
            if marker in self.scenes:
                citations[self.scenes[marker]] = citation
            else:
                self.scenes[marker] = len(citations)
                citations.append(citation)

    def place(self):
        s = self.controller.session.game.s
        return dict(area=s.dataset, block=s.block, x=s.x, y=s.y,
                    day=s.r0[0xCA], hour=s.r0[0xC9], minute=s.r0[0xC8] * 10 + s.r0[0xC7])

    def save(self, slot, *, selected=False):
        self.observe()
        temporary = None
        try:
            path = self.sidecar(slot)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(history=self.history, entries=self.entries), stream)
            temporary.replace(path)
            if selected: self.slot = slot
            self.error = ''
        except OSError:
            self.error = 'Journal could not be saved; observations and notes are kept for this session.'
        finally:
            if temporary: temporary.unlink(missing_ok=True)

    def add_note(self, value):
        if not isinstance(value, dict) or not isinstance(value.get('text'), str) or not 1 <= len(value['text'].strip()) <= 4000:
            raise ValueError('Enter a note of 1 to 4000 characters.')
        if type(value.get('pin', False)) is not bool: raise ValueError('Invalid pin setting')
        self.observe()
        self.history.append(dict(kind='personal', text=value['text'].strip(), pin=value.get('pin', False), **self.place()))
        self.save('resume')

    def current(self):
        self.observe()
        return references(self.controller.text, self.book.spec['highest'])

    def snapshot(self):
        self.observe()
        book = self.book.info()
        pages, highest = self.book.spec['pages'], self.book.spec['highest']
        entries = [dict(number=int(n), citations=c, page=pages[int(n)] if book['mapped'] else None)
                   for n, c in self.entries.items() if n.isdigit() and (int(n) in pages or not pages and 1 <= int(n) <= highest) and c]
        return dict(slot=self.slot, book=book, entries=entries, history=self.history[-400:],
                    history_count=len(self.history), current=self.current(), error=self.error)


def get(handler, path):
    if path not in ('/journal', '/journal.pdf', '/journal/entry'): return False
    journal = getattr(handler.server.controller, 'journal', None)
    if journal is None:
        handler.json(dict(error='Start SSB with your own game folder to read the journal.'), status=409)
    elif path == '/journal': handler.json(journal.snapshot())
    elif path == '/journal/entry':
        number = parse_qs(urlsplit(handler.path).query).get('n', [''])[0]
        number = int(number) if number.isascii() and number.isdigit() and len(number) <= 3 else 0
        handler.json(dict(number=number, text=journal.book.entry_text(number)))
    else:
        pdf = journal.book.path()
        try:
            if pdf is None: raise FileNotFoundError
            handler.reply(pdf.read_bytes(), 'application/pdf')
        except OSError: handler.json(dict(error='No journal PDF is available. See your printed Adventurer\'s Journal.'), status=404)
    return True


def post(handler, body):
    journal = getattr(handler.server.controller, 'journal', None)
    if journal is None:
        handler.json(dict(error='Start SSB first.'), status=409)
        return
    try:
        journal.add_note(json.loads(body))
        handler.json(journal.snapshot())
    except (ValueError, UnicodeError) as error: handler.json(dict(error=str(error)), status=400)
