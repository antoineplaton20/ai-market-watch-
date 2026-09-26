"""ARCHIVISTE — historique de l'or dans la base, vérifié, et regroupements d'unités de temps.

Sources (voir donnees_initiales/PROVENANCE.md) :
- « OR » 1M : prix mensuel de l'once depuis 1833 ;
- « GC » 1d : or COMEX (contrat continu) depuis 2000 ;
- « PAXGUSDT » / « XAUUSDT » 15m : bougies Binance, empreintes SHA-256 vérifiées ; en direct : 1m.
Les unités 1h, 4h et 1d sont construites à partir des 15m (et des 1m en direct), alignées sur l'heure UTC.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import math
import zipfile
from pathlib import Path

import numpy as np

from . import base, config

MINUTES = {"1m": 1, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
MS = {tf: m * 60_000 for tf, m in MINUTES.items()}


class DonneesInvalides(RuntimeError):
    pass


def _bougie_valide(o, h, l, c, v):
    return (all(math.isfinite(x) for x in (o, h, l, c, v)) and min(o, h, l, c) > 0 and v >= 0
            and l <= min(o, c) and h >= max(o, c))


def lire_archive(brut):
    """Archive Binance (zip d'un CSV) -> lignes [ts_ms, o, h, l, c, v]. Horodatages en microsecondes convertis."""
    with zipfile.ZipFile(io.BytesIO(brut)) as z:
        noms = z.namelist()
        if len(noms) != 1:
            raise DonneesInvalides("archive inattendue")
        texte = z.read(noms[0]).decode()
    lignes = []
    for r in csv.reader(io.StringIO(texte)):
        if not r or not r[0].strip().isdigit():               # en-tête éventuel (archives futures)
            continue
        ts = int(r[0])
        if ts >= 100_000_000_000_000:
            ts //= 1000
        o, h, l, c, v = map(float, r[1:6])
        if not _bougie_valide(o, h, l, c, v):
            raise DonneesInvalides(f"bougie invalide à {ts}")
        lignes.append([ts, o, h, l, c, v])
    return lignes


def inserer(source, tf, lignes, chemin=None):
    if not lignes:
        return 0
    with base.connexion(chemin) as c:
        c.executemany("INSERT OR REPLACE INTO bougies(source, tf, ts, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)",
                      [(source, tf, int(r[0]), *map(float, r[1:6])) for r in lignes])
    return len(lignes)


def regrouper(lignes, minutes, pas_source_ms):
    """Regroupe des bougies (triées) en bougies de `minutes`, alignées sur l'époque UTC.
    Une bougie n'est produite que si elle est COMPLÈTE (toutes les sous-bougies présentes)."""
    pas = minutes * 60_000
    attendu = pas // pas_source_ms
    out, courant, n = [], None, 0
    for ts, o, h, l, c, v in lignes:
        debut = ts - ts % pas
        if courant is None or debut != courant[0]:
            if courant is not None and n == attendu:
                out.append(courant)
            courant, n = [debut, o, h, l, c, v], 1
        else:
            courant[2], courant[3] = max(courant[2], h), min(courant[3], l)
            courant[4], courant[5] = c, courant[5] + v
            n += 1
    if courant is not None and n == attendu:
        out.append(courant)
    return out


def consolider(source, chemin=None, depuis_ms=0):
    """(Re)construit 1h, 4h et 1d à partir des 15m ; et 15m à partir des 1m là où les 15m manquent (direct)."""
    une = charger_lignes(source, "1m", depuis_ms, chemin)
    if une:
        inserer(source, "15m", regrouper(une, 15, MS["1m"]), chemin)
    quinze = charger_lignes(source, "15m", depuis_ms - depuis_ms % MS["1d"] if depuis_ms else 0, chemin)
    for tf in ("1h", "4h", "1d"):
        inserer(source, tf, regrouper(quinze, MINUTES[tf], MS["15m"]), chemin)


def charger_lignes(source, tf, depuis_ms=0, chemin=None, limite=None):
    requete = "SELECT ts, o, h, l, c, v FROM bougies WHERE source=? AND tf=? AND ts>=? ORDER BY ts"
    params = [source, tf, int(depuis_ms)]
    if limite:
        requete = ("SELECT * FROM (SELECT ts, o, h, l, c, v FROM bougies WHERE source=? AND tf=? AND ts>=? "
                   "ORDER BY ts DESC LIMIT ?) ORDER BY ts")
        params.append(int(limite))
    with base.connexion(chemin) as c:
        return [tuple(r) for r in c.execute(requete, params)]


def charger(source, tf, depuis_ms=0, chemin=None, limite=None):
    """-> {'ts','o','h','l','c','v'} en tableaux numpy (vides si rien)."""
    lignes = charger_lignes(source, tf, depuis_ms, chemin, limite)
    t = np.array(lignes, dtype=float).reshape(-1, 6)
    return {"ts": t[:, 0].astype(np.int64), "o": t[:, 1], "h": t[:, 2], "l": t[:, 3], "c": t[:, 4], "v": t[:, 5]}


# ---------------------------------------------------------------------------- import des données livrées
def importer_binance(dossier=None, chemin=None):
    """Archives 15m livrées, contrôlées par SHA256SUMS. Une empreinte fausse arrête l'import (jamais de trou comblé)."""
    dossier = Path(dossier or config.DONNEES_INITIALES / "binance")
    sommes = {}
    for ligne in (dossier / "SHA256SUMS").read_text().splitlines():
        h, nom = ligne.split()
        sommes[nom] = h
    total = {}
    for nom, h in sorted(sommes.items()):
        brut = (dossier / nom).read_bytes()
        if hashlib.sha256(brut).hexdigest() != h:
            raise DonneesInvalides(f"empreinte incorrecte : {nom}")
        source = nom.split("-")[0]
        total[source] = total.get(source, 0) + inserer(source, "15m", lire_archive(brut), chemin)
    for source in total:
        consolider(source, chemin)
    return total


def importer_comex(fichier=None, chemin=None):
    fichier = Path(fichier or config.DONNEES_INITIALES / "comex_gc_quotidien_2000.csv")
    lignes = []
    with open(fichier, newline="") as f:
        for r in csv.DictReader(f):
            ts = int(dt.datetime.strptime(r["date"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
            o, h, l, c, v = (float(r[k]) for k in ("open", "high", "low", "close", "volume"))
            if _bougie_valide(o, h, l, c, v):
                lignes.append([ts, o, h, l, c, v])
    return inserer("GC", "1d", lignes, chemin)


def importer_long(fichier=None, chemin=None):
    """Prix mensuel depuis 1833 (une « bougie » par mois : o = h = l = c = prix)."""
    fichier = Path(fichier or config.DONNEES_INITIALES / "or_mensuel_1833.csv")
    lignes = []
    with open(fichier, newline="") as f:
        for r in csv.DictReader(f):
            a, m = map(int, r["Date"][:7].split("-"))
            ts = int(dt.datetime(a, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
            p = float(r["Price"])
            if p > 0:
                lignes.append([ts, p, p, p, p, 0.0])
    return inserer("OR", "1M", lignes, chemin)


def importer_tout(chemin=None):
    res = {"binance": importer_binance(chemin=chemin), "comex": importer_comex(chemin=chemin),
           "depuis_1833": importer_long(chemin=chemin)}
    base.ecrire("historique_importe", res, chemin)
    return res


def inventaire(chemin=None):
    with base.connexion(chemin) as c:
        return [dict(r) for r in c.execute(
            "SELECT source, tf, COUNT(*) AS n, MIN(ts) AS debut, MAX(ts) AS fin FROM bougies GROUP BY source, tf "
            "ORDER BY source, tf")]
