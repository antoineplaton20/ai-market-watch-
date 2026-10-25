"""R7 : le momentum relatif (seule méthode nouvelle à passer le permis) face aux contrôles, contre le naïf ET contre
le momentum 12 mois de l'équipe : réglages voisins (plateau, pas choix), frais, financement, 200 sous-paniers,
périodes de 5 ans, sans cryptos, avec les historiques écartés, 44 marchés ; double momentum (Antonacci).

Usage : python etudes/robustesse_r7.py YAHOO YAHOO_EXTRA RACINE_ARMEE
"""
import datetime as dt
import json
import os
import sys

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, sys.argv[3])
import moteur_r7 as M          # noqa: E402
import speciales_r7 as SP      # noqa: E402
from armee_or import marches as MM, qualite as Q   # noqa: E402
from charger import charger    # noqa: E402

YAHOO, EXTRA = sys.argv[1], sys.argv[2]


def relatif(marches, tiers=1 / 3, retro=252, saut=21, absolu=False, facteur_frais=1.0, financement=M.FINANCEMENT):
    """Momentum relatif paramétrable (mêmes conventions que speciales_r7.momentum_relatif)."""
    jours = np.array(sorted({int(x) for d in marches.values() for x in SP._jour(d["ts"])}))
    noms = list(marches)
    P = np.full((len(noms), len(jours)), np.nan)
    for k, s in enumerate(noms):
        ix = np.searchsorted(jours, SP._jour(marches[s]["ts"]))
        P[k, ix] = marches[s]["c"]
        for i in range(1, len(jours)):
            if not np.isfinite(P[k, i]):
                P[k, i] = P[k, i - 1]
    poids = np.zeros_like(P)
    choix = np.zeros(len(noms))
    for i in range(retro + saut, len(jours)):
        if (jours[i] // 30) != (jours[i - 1] // 30):
            score = P[:, i - saut] / P[:, i - saut - retro] - 1
            ok = np.isfinite(score)
            choix = np.zeros(len(noms))
            if ok.sum() >= 6:
                k = max(1, int(round(ok.sum() * tiers)))
                meilleurs = np.argsort(np.where(ok, -score, np.inf))[:k]
                choix[meilleurs] = 1
                if absolu:
                    choix[score <= 0] = 0
        poids[:, i] = choix
    series = {}
    for k, s in enumerate(noms):
        d = marches[s]
        ix = np.searchsorted(jours, SP._jour(d["ts"]))
        w = poids[k, ix] * SP.taille_vol(d)
        frais = MM.FRAIS_DEFAUT.get(d["famille"], 0.0005) * facteur_frais
        series[s] = (SP._jour(d["ts"]), SP.rendement_position(d, w, frais, financement), d["famille"])
    return M.portefeuille(series)


def equipe(marches, strat="momentum_12m"):
    r = MM.banc(marches, strategies=(strat, "toujours_acheter"), sorties=MM.SORTIES, serie=True)
    return r[strat]["serie"], r["toujours_acheter"]["serie"]


def moities(serie, coupe):
    j, p = serie
    j, p = np.asarray(j), np.asarray(p)
    return M.sharpe(p[j < coupe]), M.sharpe(p[j >= coupe]), M.pire_baisse(p)


def ligne(nom, rel, eq, nv):
    coupe = rel[0][len(rel[0]) // 2]
    a, b, c = moities(rel, coupe), moities(eq, coupe), moities(nv, coupe)
    bat_n = a[0] > c[0] and a[1] > c[1]
    bat_e = a[0] > b[0] and a[1] > b[1]
    print(f"{nom:46} | relatif {a[0]:+.2f} / {a[1]:+.2f} ({a[2] * 100:5.1f} %) | équipe {b[0]:+.2f} / {b[1]:+.2f} | "
          f"naïf {c[0]:+.2f} / {c[1]:+.2f} | {'bat le naïf' if bat_n else 'NE bat PAS le naïf'} · "
          f"{'bat l’équipe' if bat_e else 'ne bat pas l’équipe'}", flush=True)
    return bat_n, bat_e


def verdicts(tous):
    v = {}
    for nom, d in tous.items():
        r = json.load(open(os.path.join(YAHOO, nom + ".json")))["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        v[nom] = Q.controler([(t * 1000, *x) for t, *x in zip(r["timestamp"], q["open"], q["high"], q["low"],
                                                                 q["close"])], famille=d["famille"])["verdict"]
    return v


if __name__ == "__main__":
    tous = charger(YAHOO, MM)
    v = verdicts(tous)
    propres = {s: d for s, d in tous.items() if v[s] != "écarté"}
    eq, nv = equipe(propres)
    print(f"{len(propres)} marchés propres ; risque égal par famille ; deux moitiés")
    print("1) Réglages voisins (plateau, pas choix)")
    for tiers in (1 / 4, 1 / 3, 1 / 2):
        for retro, saut in ((126, 21), (189, 21), (252, 21), (252, 0)):
            ligne(f"tiers {tiers:.2f}, {retro // 21} mois, saut {saut // 21} mois",
                  relatif(propres, tiers, retro, saut), eq, nv)
    print("2) Double momentum (Antonacci) : le tiers le plus fort ET rendement 12 mois positif")
    ligne("double momentum", relatif(propres, absolu=True), eq, nv)
    print("3) Frais et financement")
    for f in (2.0, 3.0):
        ligne(f"frais × {f:g}", relatif(propres, facteur_frais=f), eq, nv)
    ligne("financement 5 %/an", relatif(propres, financement=0.05), eq, nv)
    print("4) Paniers")
    sans = {s: d for s, d in propres.items() if d["famille"] != "crypto"}
    e2, n2 = equipe(sans)
    ligne("sans cryptos", relatif(sans), e2, n2)
    sans_fx = {s: d for s, d in propres.items() if d["famille"] != "forex"}
    e3, n3 = equipe(sans_fx)
    ligne("sans forex", relatif(sans_fx), e3, n3)
    e4, n4 = equipe(tous)
    ligne("34 marchés (écartés compris, indicatif)", relatif(tous), e4, n4)
    print("5) 200 sous-paniers de la moitié des marchés propres")
    rng = np.random.default_rng(7)
    noms = sorted(propres)
    bn = be = 0
    for _ in range(200):
        sous = {s: propres[s] for s in rng.choice(noms, size=len(noms) // 2, replace=False)}
        e_s, n_s = equipe(sous)
        rel = relatif(sous)
        coupe = rel[0][len(rel[0]) // 2]
        a, b, c = moities(rel, coupe), moities(e_s, coupe), moities(n_s, coupe)
        bn += a[0] > c[0] and a[1] > c[1]
        be += a[0] > b[0] and a[1] > b[1]
    print(f"   bat le naïf sur les deux moitiés : {bn}/200 ; bat l'équipe sur les deux moitiés : {be}/200")
    print("6) Périodes de 5 ans (Sharpe)")
    rel = relatif(propres)
    for debut in range(2001, 2026, 5):
        a = (dt.date(debut, 1, 1) - dt.date(1970, 1, 1)).days
        b = (dt.date(debut + 5, 1, 1) - dt.date(1970, 1, 1)).days
        def sh(serie):
            j, p = map(np.asarray, serie)
            return M.sharpe(p[(j >= a) & (j < b)])
        print(f"   {debut}-{debut + 4} : relatif {sh(rel):+.2f} | équipe {sh(eq):+.2f} | naïf {sh(nv):+.2f}")
    j1, p1 = rel
    j2, p2 = map(np.asarray, eq)
    commun = np.intersect1d(j1, j2)
    x, y = p1[np.searchsorted(j1, commun)], p2[np.searchsorted(j2, commun)]
    print(f"   corrélation quotidienne relatif / équipe : {np.corrcoef(x, y)[0, 1]:+.2f}")
    moitie = 0.5 * x + 0.5 * y
    coupe = commun[len(commun) // 2]
    print(f"   moitié relatif + moitié équipe : {M.sharpe(moitie[commun < coupe]):+.2f} / "
          f"{M.sharpe(moitie[commun >= coupe]):+.2f}, pire baisse {M.pire_baisse(moitie) * 100:.1f} %")
