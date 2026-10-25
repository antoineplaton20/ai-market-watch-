"""Robustesse du risque égal PAR FAMILLE (Bridgewater) avant adoption : sans les cryptos, sans le forex, frais
triplés, financement −5 %/an, 200 sous-paniers, périodes de 5 ans. Toujours le moteur de l'équipe (stop 5 ATR).
Usage : python etudes/robustesse_r61.py DOSSIER_YAHOO RACINE_ARMEE DOSSIER_ETUDES"""
import copy
import datetime as dt
import sys

import numpy as np

sys.argv = [sys.argv[0], sys.argv[1], "", sys.argv[2], sys.argv[3]]
sys.path.insert(0, sys.argv[3])
sys.path.insert(0, sys.argv[4])
import grands_r61 as G                 # noqa: E402  (ajoute aussi la règle CFM au moteur)
from armee_or import marches as M     # noqa: E402
from charger import FAMILLES, charger  # noqa: E402

base = charger(sys.argv[1], M)
for nom, d in base.items():
    d["famille"] = next(f for f, noms in FAMILLES.items() if nom in noms)


def comparer(nom, marches):
    j, naif = G.series(marches, "toujours_acheter")
    _, mom = G.series(marches, "momentum_12m")
    (a1, a2), dda, ma = G.bilan(j, G.par_marche(mom))
    (b1, b2), ddb, mb = G.bilan(j, G.par_famille(mom))
    (n1, n2), _, _ = G.bilan(j, G.par_famille(naif))
    mieux = b1 > a1 and b2 > a2
    bat = b1 > n1 and b2 > n2
    print(f"{nom:30}| par marché {a1:+.2f}/{a2:+.2f} ({dda*100:.0f} %) | par famille {b1:+.2f}/{b2:+.2f} ({ddb*100:.0f} %) "
          f"| naïf famille {n1:+.2f}/{n2:+.2f} | {'✅ mieux' if mieux else '✖ pas mieux'} · {'bat le naïf' if bat else 'NE bat PAS le naïf'}")
    return mieux, bat


comparer("34 marchés", base)
comparer("sans les cryptos (32)", {s: d for s, d in base.items() if d["famille"] != "crypto"})
comparer("sans le forex (22)", {s: d for s, d in base.items() if d["famille"] != "forex"})
comparer("sans cryptos ni forex (20)", {s: d for s, d in base.items() if d["famille"] not in ("crypto", "forex")})
for nom, fe, fs in (("écarts × 3", 3, 1), ("financement −5 %/an", 1, 5 / 3)):
    m = copy.deepcopy(base)
    for d in m.values():
        d["cout"] = {"ecart": d["cout"]["ecart"] * fe, "swap_long": d["cout"]["swap_long"] * fs}
    comparer(nom, m)
rng = np.random.default_rng(61)
cles, mieux, bat = sorted(base), 0, 0
for _ in range(200):
    sous = {s: base[s] for s in rng.choice(cles, 17, replace=False)}
    j, naif = G.series(sous, "toujours_acheter")
    _, mom = G.series(sous, "momentum_12m")
    (a1, a2), _, _ = G.bilan(j, G.par_marche(mom))
    (b1, b2), _, _ = G.bilan(j, G.par_famille(mom))
    (n1, n2), _, _ = G.bilan(j, G.par_famille(naif))
    mieux += b1 > a1 and b2 > a2
    bat += b1 > n1 and b2 > n2
print(f"200 sous-paniers (17 marchés) : par famille mieux que par marché sur les 2 moitiés {mieux}/200 ; "
      f"bat le naïf par famille {bat}/200")
j, mom = G.series(base, "momentum_12m")
pm, pf = G.par_marche(mom), G.par_famille(mom)
annees = np.array([dt.date.fromtimestamp(int(x) * 86400).year for x in j])
for debut in range(2001, 2026, 5):
    k = (annees >= debut) & (annees < debut + 5)
    sh = lambda y: y.mean() / y.std() * np.sqrt(252)
    print(f"   {debut}-{min(debut + 4, 2026)} : par marché {sh(pm[k]):+.2f} | par famille {sh(pf[k]):+.2f}")
