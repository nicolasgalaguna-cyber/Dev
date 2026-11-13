"""Durable station configuration. No third-party dependencies."""
import copy
import json
import sqlite3
import threading
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        (self.root / 'media').mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'station.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        row = self.db.execute('SELECT body FROM state WHERE id=1').fetchone()
        self.data = json.loads(row[0]) if row else dict(tracks=[], playlists=[], schedules=[], dossiers={}, scripts=[], history=[], active_playlist=None)
        self.save()

    def save(self):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (json.dumps(self.data),))

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def track(self, ident):
        with self.lock:
            return next((copy.deepcopy(t) for t in self.data['tracks'] if t['id'] == ident), None)

    def close(self):
        self.db.close()
