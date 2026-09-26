"""Base SQLite de l'armée (runtime/or.db, mode WAL : lecteurs et écrivain en parallèle).

Connexions courtes (ouvertes, validées, FERMÉES) : plusieurs services écrivent sans se bloquer longtemps.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS bougies(source TEXT, tf TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
    PRIMARY KEY(source, tf, ts)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS kv(cle TEXT PRIMARY KEY, valeur TEXT, maj REAL);
CREATE TABLE IF NOT EXISTS pronostics(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, bot TEXT, horizon INTEGER,
    p_hausse REAL, prix_ref REAL, cible_ts INTEGER, issue INTEGER, brier REAL);
CREATE INDEX IF NOT EXISTS idx_prono_ouverts ON pronostics(issue, cible_ts);
CREATE INDEX IF NOT EXISTS idx_prono_bot ON pronostics(bot, ts);
CREATE TABLE IF NOT EXISTS rapports(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, bot TEXT, ok INTEGER, duree REAL,
    message TEXT);
CREATE INDEX IF NOT EXISTS idx_rapports ON rapports(bot, ts);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, profil TEXT, sens INTEGER, entree_ts INTEGER,
    prix_entree REAL, notionnel REAL, levier REAL, stop REAL, objectif REAL, liquidation REAL, sortie_ts INTEGER,
    prix_sortie REAL, motif TEXT, pnl REAL, frais REAL, financement REAL, capital_apres REAL);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, p_consensus REAL, sens INTEGER,
    details TEXT);
"""


@contextmanager
def connexion(chemin=None):
    chemin = Path(chemin or config.BASE)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(chemin, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        with c:
            yield c
    finally:
        c.close()


def lire(cle, defaut=None, chemin=None):
    with connexion(chemin) as c:
        r = c.execute("SELECT valeur FROM kv WHERE cle=?", (cle,)).fetchone()
    if r is None:
        return defaut
    try:
        return json.loads(r["valeur"])
    except ValueError:
        return defaut


def ecrire(cle, valeur, chemin=None):
    with connexion(chemin) as c:
        c.execute("INSERT INTO kv(cle, valeur, maj) VALUES(?,?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur,"
                  " maj=excluded.maj", (cle, json.dumps(valeur, default=float), time.time()))
