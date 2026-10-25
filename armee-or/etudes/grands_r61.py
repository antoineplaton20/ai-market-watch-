"""R6.1 (25/10/2026) : les méthodes PUBLIQUES des plus grandes maisons de gestion, testées comme le reste (moteur de
l'équipe : ouverture suivante, stop 5 ATR, taille à 10 % de volatilité, frais ; deux moitiés ; naïf du même panier).

1. CFM (Paris, Bouchaud et al., « Two Centuries of Trend Following », 2014) : signal = prix − moyenne exponentielle
   de 5 mois (hors prix du jour), divisé par la volatilité ; ici acheteur seulement (le signe suffit).
2. Bridgewater (Dalio, « 15 à 20 sources de rendement peu corrélées ») : même risque pour chaque FAMILLE d'actifs au
   lieu de chaque marché (le forex pèse 12 marchés sur 34).
3. Millennium / Citadel (limites de perte des équipes, ~5 % puis ~7,5 %, presse spécialisée) : taille divisée par deux
   quand l'équipe perd 0,5 fois sa volatilité annuelle depuis son sommet, rétablie sous 0,25 fois.
4. Plus de sources : 8 indices d'Asie et d'Europe (Hong Kong, Australie, Corée, Singapour, Inde, Shanghai, Suisse,
   Espagne) et 2 obligations américaines (10 et 30 ans), Yahoo 2000-2026.

Usage : python etudes/grands_r61.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA RACINE_ARMEE DOSSIER_ETUDES
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, sys.argv[3])
sys.path.insert(0, sys.argv[4])
from armee_or import marches as M   # noqa: E402
from charger import FAMILLES, charger  # noqa: E402

EXTRA = {"indices": ["HSI", "AXJO", "KS11", "STI", "NSEI", "000001SS", "SSMI", "IBEX"], "obligations": ["ZNF", "ZBF"]}
EMA_CFM = 105                                    # 5 mois de bourse

_signal = M.signal


def signal(c, strategie):
    """Ajoute au moteur de l'équipe la règle CFM, sans toucher au module."""
    if strategie == "tendance_cfm":
        c = np.asarray(c, dtype=float)
        e = np.empty(len(c))
        e[0] = c[0]
        a = 1 / EMA_CFM
        for i in range(1, len(c)):
            e[i] = (1 - a) * e[i - 1] + a * c[i]
        s = np.zeros(len(c))
        s[1:] = c[1:] > e[:-1]                    # prix du jour contre la moyenne d'HIER (hors prix du jour)
        s[:200] = 0
        return s
    return _signal(c, strategie)


M.signal = signal


def charger_extra(dossier):
    out = {}
    for fam, noms in EXTRA.items():
        for nom in noms:
            r = json.load(open(os.path.join(dossier, nom + ".json")))["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            rows = [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])
                    if None not in (o, h, l, c) and min(o, h, l, c) > 0 and l <= min(o, c) and h >= max(o, c)]
            a = np.array(rows, dtype=float)
            out[nom] = {"ts": (a[:, 0] * 1000).astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4],
                        "cout": M.couts({}, "indices", a[-1, 4]), "famille": fam}
    return out


def series(marches, regle):
    """-> jours, {famille: (somme des rendements, nombre de marchés)} : de quoi agréger à volonté."""
    jours = np.array(sorted({int(t) // 86_400_000 for d in marches.values() for t in d["ts"]}))
    pos = {j: k for k, j in enumerate(jours)}
    fam = {}
    for d in marches.values():
        net, _ = M.simuler_marche(d["o"], d["h"], d["l"], d["c"], regle, d["cout"])
        idx = np.array([pos[int(t) // 86_400_000] for t in d["ts"]])
        s, n = fam.setdefault(d["famille"], (np.zeros(len(jours)), np.zeros(len(jours))))
        s[idx] += net
        n[idx] += 1
    return jours, fam


def par_marche(fam):
    s = sum(v[0] for v in fam.values())
    n = sum(v[1] for v in fam.values())
    return np.where(n > 0, s / np.maximum(n, 1), 0.0)


def par_famille(fam):
    moyennes = [np.where(n > 0, s / np.maximum(n, 1), np.nan) for s, n in fam.values()]
    m = np.array(moyennes)
    presentes = np.isfinite(m).sum(axis=0)
    return np.where(presentes > 0, np.nansum(m, axis=0) / np.maximum(presentes, 1), 0.0)


def bilan(jours, p):
    coupe = jours[len(jours) // 2]
    sh = [M.statistiques(p[jours < coupe])["sharpe"], M.statistiques(p[jours >= coupe])["sharpe"]]
    mois = {}
    for v, j in zip(p, jours):
        k = dt.date.fromtimestamp(int(j) * 86400).strftime("%Y-%m")
        mois[k] = mois.get(k, 0.0) + v
    c = np.cumsum(p)
    return sh, float((c - np.maximum.accumulate(c)).min()), float(np.mean([v > 0 for v in mois.values()]))


def limite_de_perte(p, demi=0.5, retour=0.25):
    """Taille ÷ 2 quand l'équipe (courbe sans limite) perd demi × sa volatilité annuelle (252 j) depuis son sommet ;
    rétablie quand la perte repasse sous retour × volatilité. Décidé à la clôture, appliqué le lendemain."""
    e, pic, f, out = 0.0, 0.0, 1.0, np.zeros(len(p))
    for i in range(len(p)):
        out[i] = f * p[i]
        e += p[i]
        pic = max(pic, e)
        vol = p[max(0, i - 251):i + 1].std() * np.sqrt(252) if i >= 60 else 0.0
        if vol > 0:
            if e - pic < -demi * vol:
                f = 0.5
            elif e - pic > -retour * vol:
                f = 1.0
    return out


def ligne(nom, jours, p, ref=None):
    (s1, s2), dd, mp = bilan(jours, p)
    txt = f"{nom:52}| {s1:+.2f} / {s2:+.2f} | pire baisse {dd*100:5.1f} % | mois + {mp*100:3.0f} %"
    if ref is not None:
        (r1, r2), _, _ = bilan(jours, ref)
        txt += "  ✅ bat le naïf" if s1 > r1 and s2 > r2 else "  ✖"
    print(txt)


if __name__ == "__main__":
    base = charger(sys.argv[1], M)
    for nom, d in base.items():
        d["famille"] = next(f for f, noms in FAMILLES.items() if nom in noms)
    print("1) CFM (Paris) : tendance exponentielle 5 mois, acheteur seulement — 34 marchés")
    j, naif = series(base, "toujours_acheter")
    _, mom = series(base, "momentum_12m")
    _, s200 = series(base, "sma200")
    _, cfm = series(base, "tendance_cfm")
    ligne("toujours acheter (naïf)", j, par_marche(naif))
    ligne("règle 200 jours", j, par_marche(s200), par_marche(naif))
    ligne("momentum 12 mois", j, par_marche(mom), par_marche(naif))
    ligne("CFM : prix au-dessus de sa moyenne exp. 5 mois", j, par_marche(cfm), par_marche(naif))
    print("2) Bridgewater : même risque par FAMILLE (6 familles) au lieu de par marché")
    ligne("naïf, par famille", j, par_famille(naif))
    ligne("règle 200 jours, par famille", j, par_famille(s200), par_famille(naif))
    ligne("momentum 12 mois, par famille", j, par_famille(mom), par_famille(naif))
    print("3) Millennium / Citadel : taille ÷ 2 après une perte de 0,5 volatilité annuelle")
    ligne("momentum 12 mois, sans limite", j, par_marche(mom), par_marche(naif))
    ligne("momentum 12 mois, avec limite de perte", j, limite_de_perte(par_marche(mom)), par_marche(naif))
    print("4) Plus de sources : + 8 indices Asie/Europe + 2 obligations US (44 marchés)")
    tous = {**base, **charger_extra(sys.argv[2])}
    j2, naif2 = series(tous, "toujours_acheter")
    _, mom2 = series(tous, "momentum_12m")
    ligne("naïf, 44 marchés", j2, par_marche(naif2))
    ligne("momentum 12 mois, 44 marchés", j2, par_marche(mom2), par_marche(naif2))
    ligne("naïf, 44 marchés, par famille (7)", j2, par_famille(naif2))
    ligne("momentum 12 mois, 44 marchés, par famille (7)", j2, par_famille(mom2), par_famille(naif2))
    cor = np.corrcoef(np.array([np.where(n > 0, s / np.maximum(n, 1), 0) for s, n in mom2.values()]))
    print(f"   corrélation moyenne entre familles (momentum) : {(cor.sum() - len(cor)) / (len(cor) ** 2 - len(cor)):+.2f}")
