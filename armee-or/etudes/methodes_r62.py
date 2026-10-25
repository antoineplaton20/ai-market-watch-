"""R6.2 (25/10/2026) : méthodes qui visent « au moins un petit gain par trade », testées sur le moteur de l'équipe
(ouverture suivante, stop 5 ATR, 10 % de volatilité, frais, risque égal par famille), sur les 34 marchés PUIS sur les
seuls marchés aux données propres (armee_or/qualite.py). Réglages standards, fixés d'avance :
- verrou de gain : dès une clôture à +2 ATR, stop remonté à +0,5 ATR (le trade ne peut plus finir en perte, sauf trou
  de cotation), rachat si la règle tient encore ;
- stop suiveur de LeBeau (« chandelier ») : plus haut atteint − 3 ATR, avec et sans rachat ;
- ensemble : moitié momentum 12 mois, moitié règle 200 jours.
Usage : python etudes/methodes_r62.py DOSSIER_YAHOO RACINE_ARMEE DOSSIER_ETUDES"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[3])
from armee_or import marches as M, qualite as Q   # noqa: E402
from charger import FAMILLES, charger             # noqa: E402

base = charger(sys.argv[1], M)
propres = {}
for nom, d in base.items():
    r = json.load(open(os.path.join(sys.argv[1], nom + ".json")))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    v = Q.controler([(t * 1000, *x) for t, *x in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])],
                    famille=d["famille"])["verdict"]
    if v != "écarté":
        propres[nom] = d

VARIANTES = [("momentum 12 mois (référence)", "momentum_12m", None),
             ("+ verrou de gain (+2 ATR → +0,5 ATR), rachat", "momentum_12m", {"verrou": (2.0, 0.5), "rachat": True}),
             ("+ stop suiveur 3 ATR, rachat", "momentum_12m", {"suiveur": 3.0, "rachat": True}),
             ("+ stop suiveur 3 ATR, sans rachat", "momentum_12m", {"suiveur": 3.0}),
             ("règle 200 jours (référence)", "sma200", None)]


def serie(marches, regle, sorties):
    """Rendement quotidien du portefeuille (risque égal par famille) et trades, via le banc de l'équipe."""
    r = M.banc(marches, strategies=(regle,), sorties=sorties)[regle]
    return r


for titre, panier in (("34 marchés", base), (f"{len(propres)} marchés aux données propres", propres)):
    naif = M.banc(panier, strategies=("toujours_acheter",))["toujours_acheter"]
    print(f"== {titre} · naïf (même panier, par famille) : Sharpe {naif['moitie1']['sharpe']:+.2f} / "
          f"{naif['moitie2']['sharpe']:+.2f}, pire baisse {naif['tout']['pire_baisse'] * 100:.0f} %")
    for nom, regle, sorties in VARIANTES:
        r = serie(panier, regle, sorties)
        t = r["trades"]
        bat = r["moitie1"]["sharpe"] > naif["moitie1"]["sharpe"] and r["moitie2"]["sharpe"] > naif["moitie2"]["sharpe"]
        print(f"{nom:46}| {r['moitie1']['sharpe']:+.2f} / {r['moitie2']['sharpe']:+.2f} | pire baisse "
              f"{r['tout']['pire_baisse'] * 100:4.0f} % | {t['n']:5} trades, {t['gagnants'] * 100:4.1f} % gagnants, gain moy "
              f"{t['gain_moyen'] * 100:+.2f} %, perte moy {t['perte_moyenne'] * 100:+.2f} % | {'✅' if bat else '✖'}")
    # ensemble : deux demi-équipes, séries moyennées jour par jour (même agrégation par famille)
    s = M.banc(panier, strategies=("momentum_12m", "sma200"), serie=True)
    (j, a), (_, b) = s["momentum_12m"]["serie"], s["sma200"]["serie"]
    p = (a + b) / 2
    coupe = j[len(j) // 2]
    s1, s2, tout = M.statistiques(p[j < coupe]), M.statistiques(p[j >= coupe]), M.statistiques(p)
    bat = s1["sharpe"] > naif["moitie1"]["sharpe"] and s2["sharpe"] > naif["moitie2"]["sharpe"]
    print(f"{'ensemble ½ momentum + ½ règle 200 jours':46}| {s1['sharpe']:+.2f} / {s2['sharpe']:+.2f} | pire baisse "
          f"{tout['pire_baisse'] * 100:4.0f} % | {'✅' if bat else '✖'}")
