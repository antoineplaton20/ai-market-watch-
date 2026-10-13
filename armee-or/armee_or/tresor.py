"""TRÉSOR AMÉRICAIN — taux officiels publiés chaque jour (home.treasury.gov), gratuits, depuis 2003.

Le moteur le mieux documenté de l'or est le TAUX RÉEL (Erb & Harvey 2013) : quand le rendement d'une obligation
protégée contre l'inflation monte, garder de l'or (qui ne rapporte rien) coûte plus cher. Séries tirées :
- reel_10a      taux réel à 10 ans (obligations indexées sur l'inflation) ;
- nominal_10a   taux nominal à 10 ans ;
- inflation_10a inflation attendue sur 10 ans = nominal − réel (« point mort ») ;
- pente_10_2    pente de la courbe = 10 ans − 2 ans (négative avant les récessions, en général).

Chaque valeur est rangée à l'instant où elle était CONNUE : le Trésor publie en fin de journée à New York, on la
considère connue le lendemain à 6 h UTC (jamais avant).
"""
from __future__ import annotations

import calendar
import csv
import io
import time

from . import base

URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{an}/all"
TYPES = {"nominal": "daily_treasury_yield_curve", "reel": "daily_treasury_real_yield_curve"}
DELAI_CONNU_S = 86400 + 6 * 3600
NOMS = {"reel_10a": "Taux réel 10 ans", "nominal_10a": "Taux nominal 10 ans",
        "inflation_10a": "Inflation attendue 10 ans", "pente_10_2": "Pente 10 ans − 2 ans"}


def lire_csv(texte):
    """CSV du Trésor -> {jour (UTC, s): {colonne: valeur}}."""
    out = {}
    for ligne in csv.DictReader(io.StringIO(texte)):
        try:
            jour = calendar.timegm(time.strptime(ligne["Date"], "%m/%d/%Y"))
        except (KeyError, ValueError):
            continue
        valeurs = {}
        for k, v in ligne.items():
            try:
                valeurs[k.strip().upper()] = float(v)
            except (TypeError, ValueError):
                pass
        out[jour] = valeurs
    return out


def annee(type_, an, session=None):
    from .veille import _get
    r = _get(URL.format(an=an), session, {"type": TYPES[type_], "field_tdr_date_value": an, "page": "",
                                          "_format": "csv"}, timeout=40)
    return lire_csv(r.text)


def series(nominal, reel):
    """-> {nom: [(jour, valeur)]} triées par date."""
    out = {k: [] for k in NOMS}
    for jour in sorted(set(nominal) | set(reel)):
        n, r = nominal.get(jour, {}), reel.get(jour, {})
        if "10 YR" in r:
            out["reel_10a"].append((jour, r["10 YR"]))
        if "10 YR" in n:
            out["nominal_10a"].append((jour, n["10 YR"]))
            if "2 YR" in n:
                out["pente_10_2"].append((jour, n["10 YR"] - n["2 YR"]))
            if "10 YR" in r:
                out["inflation_10a"].append((jour, n["10 YR"] - r["10 YR"]))
    return out


def resume(s):
    """Dernières valeurs et variation sur 5 séances (en points de %), pour l'écran et le brief."""
    out = {"ts": time.time()}
    for nom, pts in s.items():
        if pts:
            out[nom] = pts[-1][1]
            out[f"{nom}_5j"] = pts[-1][1] - pts[-6][1] if len(pts) > 5 else None
            out["date"] = time.strftime("%Y-%m-%d", time.gmtime(pts[-1][0]))
    return out


def rattraper(session=None, maintenant=None):
    """10 ans d'historique la première fois, puis l'année en cours chaque jour. -> {série: nombre de points}."""
    from . import apprentissage as A
    m = maintenant or time.time()
    an = time.gmtime(m).tm_year
    deja = A.cles().get("tresor:reel_10a", 0)
    annees = list(range(an - 10, an + 1)) if deja < 2000 else ([an - 1, an] if time.gmtime(m).tm_yday < 15 else [an])
    nominal, reel = {}, {}
    for a in annees:
        nominal.update(annee("nominal", a, session))
        reel.update(annee("reel", a, session))
    s = series(nominal, reel)
    bilan = {}
    for nom, pts in s.items():
        connus = [(j + DELAI_CONNU_S, v) for j, v in pts if j + DELAI_CONNU_S <= m]
        bilan[f"tresor:{nom}"] = A.enregistrer(f"tresor:{nom}", connus)
    complet = {nom: [(t - DELAI_CONNU_S, v) for t, v in zip(*A.serie(f"tresor:{nom}"))] for nom in NOMS}
    base.ecrire("tresor", resume(complet))
    return bilan


def texte(t=None):
    t = t if t is not None else base.lire("tresor")
    if not t or t.get("reel_10a") is None:
        return "Trésor US : pas encore relevé (une fois par jour)."
    morceaux = []
    for nom, lib in NOMS.items():
        if t.get(nom) is not None:
            v5 = t.get(f"{nom}_5j")
            morceaux.append(f"{lib} {t[nom]:.2f} %" + (f" ({v5:+.2f} pt/5 j)" if v5 is not None else ""))
    return f"Trésor US ({t.get('date')}) : " + " · ".join(morceaux)
