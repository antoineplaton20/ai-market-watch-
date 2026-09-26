"""Historique du labo : les archives Binance Spot 15 min déjà fournies (research/results/archives), vérifiées.

Chaque archive est contrôlée par son empreinte SHA-256 (provenance.json) et par la continuité des bougies
(research.validate.decode). Aucune collecte réseau : une archive absente ou altérée est une erreur, jamais
un trou comblé en silence. Les unités 1 h et 4 h sont construites à partir des bougies de 15 min.
"""
from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent / "research" / "results"
SYMBOLES = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MINUTES = {"15m": 15, "1h": 60, "4h": 240}


class DonneesInvalides(RuntimeError):
    pass


def _fichiers():
    try:
        prov = json.loads((RACINE / "provenance.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise DonneesInvalides(f"provenance.json illisible : {ex}")
    return prov.get("files") or []


@functools.lru_cache(maxsize=8)
def _quinze_minutes(symbole):
    from research.validate import decode
    lignes = []
    fichiers = sorted((f for f in _fichiers() if f.get("symbol") == symbole), key=lambda f: f["month"])
    if not fichiers:
        raise DonneesInvalides(f"aucune archive pour {symbole}")
    for f in fichiers:
        chemin = RACINE / "archives" / f"{symbole}-15m-{f['month']}.zip"
        try:
            brut = chemin.read_bytes()
        except OSError:
            raise DonneesInvalides(f"archive manquante : {chemin.name}")
        if hashlib.sha256(brut).hexdigest() != f["sha256"]:
            raise DonneesInvalides(f"empreinte incorrecte : {chemin.name}")
        lignes.extend(decode(brut, f["month"]))
    t = np.array(lignes, dtype=float)
    if np.any(np.diff(t[:, 0]) != 900_000):
        raise DonneesInvalides(f"série {symbole} non continue entre deux mois")
    return {"ts": t[:, 0].astype(np.int64), "o": t[:, 1], "h": t[:, 2], "l": t[:, 3], "c": t[:, 4], "v": t[:, 5]}


def regrouper(barres, minutes):
    """Bougies 15 min -> bougies de `minutes` (alignées sur l'heure UTC ; bougies incomplètes écartées)."""
    if minutes == 15:
        return barres
    n = minutes // 15
    pas = minutes * 60_000
    ts = barres["ts"]
    debut = int(np.argmax(ts % pas == 0))
    fin = debut + (len(ts) - debut) // n * n
    def bloc(x):
        return x[debut:fin].reshape(-1, n)
    return {"ts": bloc(ts)[:, 0], "o": bloc(barres["o"])[:, 0], "h": bloc(barres["h"]).max(axis=1),
            "l": bloc(barres["l"]).min(axis=1), "c": bloc(barres["c"])[:, -1], "v": bloc(barres["v"]).sum(axis=1)}


@functools.lru_cache(maxsize=12)
def charger(symbole, unite="1h"):
    if unite not in MINUTES:
        raise DonneesInvalides(f"unité inconnue : {unite}")
    return regrouper(_quinze_minutes(symbole), MINUTES[unite])


def periode():
    """(premier mois, dernier mois) de l'historique disponible."""
    mois = sorted({f["month"] for f in _fichiers()})
    return (mois[0], mois[-1]) if mois else (None, None)
