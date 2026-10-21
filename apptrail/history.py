"""Persistent, local snapshot library with owned JSON copies and a SQLite catalog."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .core import atomic_write, load_snapshot


def history_directory():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'AppTrail' / 'history'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'AppTrail' / 'history'


class SnapshotHistory:
    def __init__(self, directory=None):
        self.directory = Path(directory if directory is not None else history_directory()).resolve()
        self.snapshots = self.directory / 'snapshots'
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'history.sqlite3'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY, label TEXT NOT NULL, root TEXT NOT NULL,
                captured_at TEXT NOT NULL, captured_ts REAL NOT NULL,
                file_count INTEGER NOT NULL, issues INTEGER NOT NULL)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def path(self, identity):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Invalid history snapshot ID.')
        return self.snapshots / f'{identity}.json'

    def add(self, snapshot, label=None):
        # A canonical copy gives identical imports the same ID, irrespective of formatting.
        content = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2)
        identity = hashlib.sha256(content.encode('utf-8')).hexdigest()
        captured = datetime.fromisoformat(snapshot['completed_at'])
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        timestamp = captured.timestamp()
        target = self.path(identity)
        # Write before cataloging: a failed write must never create a usable-looking row.
        atomic_write(target, content)
        issues = len(snapshot['warnings']) + sum(bool(f.get('error')) for f in snapshot['files'])
        label = label or Path(snapshot['root']).name or snapshot['root']
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (identity, label, snapshot['root'], snapshot['completed_at'], timestamp,
                        len(snapshot['files']), issues))
        return identity

    def import_file(self, path):
        snapshot = load_snapshot(path)
        return self.add(snapshot)

    def entries(self, query=''):
        with self.connect() as db:
            entries = [dict(row) for row in db.execute('SELECT * FROM snapshots ORDER BY captured_ts DESC, rowid DESC')]
        query = query.strip().casefold()
        for entry in entries:
            entry['available'] = self.path(entry['id']).is_file()
        return [entry for entry in entries if query in (entry['label'] + ' ' + entry['root'] + ' ' + entry['captured_at']).casefold()]

    def load(self, identity):
        path = self.path(identity)
        try:
            content = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            raise ValueError('This history snapshot is missing. Import its JSON again to restore it.') from None
        if hashlib.sha256(content.encode('utf-8')).hexdigest() != identity:
            raise ValueError('This history snapshot changed outside AppTrail. Import the changed JSON as a new snapshot.')
        return load_snapshot(path)

    def load_path(self, path):
        path = Path(path).resolve()
        if path.parent == self.snapshots:
            return self.load(path.stem)
        return load_snapshot(path)

    def compare_pair(self, identities):
        if len(identities) != 2 or len(set(identities)) != 2:
            raise ValueError('Select exactly two different snapshots to compare.')
        entries = {e['id']: e for e in self.entries()}
        if any(identity not in entries for identity in identities):
            raise ValueError('The selected snapshot is no longer in history. Refresh the list.')
        # Older capture is Before; newer is After. Preserve selection order on ties.
        ordered = sorted(identities, key=lambda identity: entries[identity]['captured_ts'])
        return [(identity, self.load(identity)) for identity in ordered]
