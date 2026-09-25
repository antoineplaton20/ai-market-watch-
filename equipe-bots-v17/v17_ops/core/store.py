"""Stockage SQLite de la V17 : événements, signaux, ordres, instantanés + petit registre clé/valeur
(portefeuille fictif, dernière bougie traitée, pause...). Lu en parallèle par l'API et par /v17 (Telegram)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

TABLES = {"events", "signals", "orders", "snapshots"}


class OpsStore:
    def __init__(self, path="runtime/v17_ops.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._init()

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            with c:                                   # commit / rollback automatiques
                yield c
        finally:
            c.close()

    def _init(self):
        with self.lock, self._conn() as c:
            try:
                c.execute("PRAGMA journal_mode=WAL")  # lecteurs (API, /v17) sans bloquer le moteur
            except sqlite3.DatabaseError:
                pass
            c.executescript('''
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, type TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, symbol TEXT, side TEXT, score REAL, payload TEXT);
            CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, intent_id TEXT, symbol TEXT, side TEXT, qty REAL, price REAL, status TEXT, exchange_id TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, symbol TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS bot_scores(bot_id TEXT PRIMARY KEY, score REAL, n INTEGER, updated REAL);
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT, updated REAL);
            CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(ts);
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
            ''')

    def _insert(self, sql, params):
        with self.lock, self._conn() as c:
            c.execute(sql, params)

    # --------------------------------------------------------------- journaux
    def event(self, typ, payload):
        self._insert('INSERT INTO events(ts,type,payload) VALUES(?,?,?)',
                     (time.time(), typ, json.dumps(payload, default=str)))

    def signal(self, symbol, side, score, payload):
        self._insert('INSERT INTO signals(ts,symbol,side,score,payload) VALUES(?,?,?,?,?)',
                     (time.time(), symbol, side, score, json.dumps(payload, default=str)))

    def order(self, intent_id, symbol, side, qty, price, status, exchange_id=None, payload=None):
        self._insert('INSERT INTO orders(ts,intent_id,symbol,side,qty,price,status,exchange_id,payload) '
                     'VALUES(?,?,?,?,?,?,?,?,?)',
                     (time.time(), intent_id, symbol, side, qty, price, status, exchange_id,
                      json.dumps(payload or {}, default=str)))

    def snapshot(self, symbol, payload):
        self._insert('INSERT INTO snapshots(ts,symbol,payload) VALUES(?,?,?)',
                     (time.time(), symbol, json.dumps(payload, default=str)))

    def recent(self, table, limit=50):
        if table not in TABLES:
            raise ValueError(table)
        with self._conn() as c:
            return [dict(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT ?', (int(limit),))]

    def orders_since(self, ts, statuses=("filled", "submitted")):
        marks = ",".join("?" * len(statuses))
        with self._conn() as c:
            rows = c.execute(f'SELECT * FROM orders WHERE ts >= ? AND status IN ({marks}) ORDER BY id',
                             (ts, *statuses)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.get("payload") or "{}")
            except ValueError:
                d["payload"] = {}
            out.append(d)
        return out

    def purge(self, days=90):
        """Garde la base légère sur un petit serveur : on efface les journaux de plus de `days` jours."""
        limite = time.time() - days * 86400
        with self.lock, self._conn() as c:
            for t in ("events", "signals", "snapshots"):
                c.execute(f'DELETE FROM {t} WHERE ts < ?', (limite,))

    # ------------------------------------------------------------ clé / valeur
    def get(self, key, default=None):
        with self._conn() as c:
            row = c.execute('SELECT value FROM kv WHERE key = ?', (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set(self, key, value):
        self._insert('INSERT INTO kv(key,value,updated) VALUES(?,?,?) '
                     'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated',
                     (key, json.dumps(value, default=str), time.time()))

    def finish_execution(self, book_key, book, pending_key):
        """Book and removal of the pending marker share one durable transaction."""
        with self.lock, self._conn() as c:
            c.execute('INSERT INTO kv(key,value,updated) VALUES(?,?,?) '
                      'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated',
                      (book_key, json.dumps(book), time.time()))
            c.execute('DELETE FROM kv WHERE key=?', (pending_key,))
