"""Registre du labo (runtime/labo.db) : chaque essai est conservé, réussi ou raté.

Le nombre total d'essais est affiché dans l'application : plus on teste d'idées, plus une réussite peut être due
au hasard. Rien n'est effacé pour « faire joli ».
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

BASE = Path("runtime") / "labo.db"
_verrou = threading.RLock()


@contextmanager
def _conn(base=None):
    """Connexion courte : transaction validée (ou annulée) puis connexion FERMÉE."""
    c = _ouvrir(base)
    try:
        with c:
            yield c
    finally:
        c.close()


def _ouvrir(base=None):
    chemin = Path(base or BASE)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(chemin, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS essais(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, idee TEXT, source TEXT,
            statut TEXT, spec TEXT, resultat TEXT, erreur TEXT, remarques TEXT, valide INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS suivi(essai_id INTEGER PRIMARY KEY, actif INTEGER, depuis REAL, etat TEXT,
            trades TEXT, maj REAL, erreur TEXT);
    """)
    return c


def _json(x, defaut=None):
    try:
        return json.loads(x) if x else defaut
    except ValueError:
        return defaut


def _essai(r, complet=True):
    if r is None:
        return None
    d = dict(r)
    d["spec"] = _json(d.get("spec"))
    d["resultat"] = _json(d.get("resultat")) if complet else None
    d["valide"] = bool(d.get("valide"))
    return d


def nouvel_essai(idee, source, base=None):
    with _verrou, _conn(base) as c:
        return c.execute("INSERT INTO essais(ts, idee, source, statut) VALUES(?,?,?,?)",
                         (time.time(), (idee or "")[:2000], source, "en_cours")).lastrowid


def terminer(essai_id, spec, resultat, remarques="", base=None):
    with _verrou, _conn(base) as c:
        c.execute("UPDATE essais SET statut='fini', spec=?, resultat=?, remarques=?, valide=? WHERE id=?",
                  (json.dumps(spec), json.dumps(resultat), remarques, int(bool(resultat.get("valide"))), essai_id))


def echec(essai_id, erreur, spec=None, base=None):
    with _verrou, _conn(base) as c:
        c.execute("UPDATE essais SET statut='erreur', erreur=?, spec=? WHERE id=?",
                  (str(erreur)[:500], json.dumps(spec) if spec else None, essai_id))


def essai(essai_id, base=None):
    with _conn(base) as c:
        return _essai(c.execute("SELECT * FROM essais WHERE id=?", (int(essai_id),)).fetchone())


def essais(limite=20, base=None):
    with _conn(base) as c:
        lignes = c.execute("SELECT id, ts, idee, source, statut, spec, erreur, valide FROM essais "
                           "ORDER BY id DESC LIMIT ?", (int(limite),)).fetchall()
    return [_essai(r, complet=False) for r in lignes]


def compte(base=None):
    with _conn(base) as c:
        r = c.execute("SELECT COUNT(*) AS n, SUM(valide) AS v FROM essais WHERE statut='fini'").fetchone()
    return {"testes": r["n"] or 0, "valides": r["v"] or 0}


def appels_ia_depuis(ts, base=None):
    with _conn(base) as c:
        return c.execute("SELECT COUNT(*) FROM essais WHERE source='ia' AND ts >= ?", (ts,)).fetchone()[0]


def orphelins(base=None):
    """Essais restés « en cours » après un redémarrage de l'API : marqués en erreur."""
    with _verrou, _conn(base) as c:
        c.execute("UPDATE essais SET statut='erreur', erreur='interrompu par un redémarrage' WHERE statut='en_cours'")


# ------------------------------------------------------------------ test en direct (papier)
def activer_suivi(essai_id, actif, base=None):
    with _verrou, _conn(base) as c:
        if actif:
            c.execute("INSERT INTO suivi(essai_id, actif, depuis, etat, trades, maj) VALUES(?,1,?,?,?,?) "
                      "ON CONFLICT(essai_id) DO UPDATE SET actif=1, erreur=NULL",
                      (essai_id, time.time(), "{}", "[]", time.time()))
        else:
            c.execute("UPDATE suivi SET actif=0 WHERE essai_id=?", (essai_id,))


def suivis(actifs_seulement=False, base=None):
    with _conn(base) as c:
        lignes = c.execute("SELECT s.*, e.spec AS spec FROM suivi s JOIN essais e ON e.id = s.essai_id "
                           + ("WHERE s.actif=1 " if actifs_seulement else "") + "ORDER BY s.depuis DESC").fetchall()
    out = []
    for r in lignes:
        d = dict(r)
        d["spec"], d["etat"], d["trades"] = _json(d["spec"]), _json(d["etat"], {}), _json(d["trades"], [])
        d["actif"] = bool(d["actif"])
        out.append(d)
    return out


def maj_suivi(essai_id, etat, trades, erreur=None, base=None):
    with _verrou, _conn(base) as c:
        c.execute("UPDATE suivi SET etat=?, trades=?, maj=?, erreur=? WHERE essai_id=?",
                  (json.dumps(etat), json.dumps(trades[-500:]), time.time(), erreur, essai_id))
