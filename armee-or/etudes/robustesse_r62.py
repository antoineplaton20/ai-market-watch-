"""Robustesse du stop suiveur 3 ATR avec rachat et du verrou de gain (R6.2), moteur de l'équipe, risque égal par
famille : frais triplés, financement −5 %/an, réglages voisins (2,5 et 3,5 ATR : plateau, pas choix), règle 200 jours,
200 sous-paniers, périodes de 5 ans.
Usage : python etudes/robustesse_r62.py DOSSIER_YAHOO RACINE_ARMEE DOSSIER_ETUDES"""
import copy
import datetime as dt
import sys

import numpy as np

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[3])
from armee_or import marches as M   # noqa: E402
from charger import charger          # noqa: E402

SUIVEUR = {"suiveur": 3.0, "rachat": True}
VERROU = {"verrou": (2.0, 0.5), "rachat": True}
base = charger(sys.argv[1], M)


def duel(nom, marches, regle="momentum_12m", sorties=SUIVEUR):
    r = M.banc(marches, strategies=(regle, "toujours_acheter"))
    s = M.banc(marches, strategies=(regle,), sorties=sorties)[regle]
    a, n = r[regle], r["toujours_acheter"]
    mieux = s["moitie1"]["sharpe"] > a["moitie1"]["sharpe"] and s["moitie2"]["sharpe"] > a["moitie2"]["sharpe"]
    bat = s["moitie1"]["sharpe"] > n["moitie1"]["sharpe"] and s["moitie2"]["sharpe"] > n["moitie2"]["sharpe"]
    if nom:
        print(f"{nom:36}| sans {a['moitie1']['sharpe']:+.2f}/{a['moitie2']['sharpe']:+.2f} ({a['tout']['pire_baisse']*100:.0f} %) | "
              f"avec {s['moitie1']['sharpe']:+.2f}/{s['moitie2']['sharpe']:+.2f} ({s['tout']['pire_baisse']*100:.0f} %, "
              f"{s['trades']['gagnants']*100:.0f} % gagnants) | {'✅ mieux' if mieux else '✖ pas mieux'} · "
              f"{'bat le naïf' if bat else 'NE bat PAS le naïf'}")
    return mieux, bat


print("Stop suiveur 3 ATR avec rachat")
duel("34 marchés, momentum", base)
duel("34 marchés, règle 200 jours", base, "sma200")
for k in (2.5, 3.5):
    duel(f"réglage voisin {k} ATR", base, sorties={"suiveur": k, "rachat": True})
for nom, fe, fs in (("écarts × 3", 3, 1), ("écarts × 5", 5, 1), ("financement −5 %/an", 1, 5 / 3)):
    m = copy.deepcopy(base)
    for d in m.values():
        d["cout"] = {"ecart": d["cout"]["ecart"] * fe, "swap_long": d["cout"]["swap_long"] * fs}
    duel(nom, m)
rng = np.random.default_rng(62)
cles, mieux, bat = sorted(base), 0, 0
for _ in range(200):
    a, b = duel("", {s: base[s] for s in rng.choice(cles, 17, replace=False)})
    mieux += a
    bat += b
print(f"200 sous-paniers : mieux que sans suiveur sur les 2 moitiés {mieux}/200 ; bat le naïf {bat}/200")
s0 = M.banc(base, strategies=("momentum_12m",), serie=True)["momentum_12m"]["serie"]
s1 = M.banc(base, strategies=("momentum_12m",), sorties=SUIVEUR, serie=True)["momentum_12m"]["serie"]
annees = np.array([dt.date.fromtimestamp(int(x) * 86400).year for x in s0[0]])
sh = lambda y: y.mean() / y.std() * np.sqrt(252)
for debut in range(2001, 2026, 5):
    k = (annees >= debut) & (annees < debut + 5)
    print(f"   {debut}-{min(debut + 4, 2026)} : sans {sh(s0[1][k]):+.2f} | avec suiveur {sh(s1[1][k]):+.2f}")
print("Verrou de gain (+2 ATR → +0,5 ATR) avec rachat")
duel("34 marchés, momentum", base, sorties=VERROU)
m = copy.deepcopy(base)
for d in m.values():
    d["cout"] = {"ecart": d["cout"]["ecart"] * 3, "swap_long": d["cout"]["swap_long"]}
duel("écarts × 3", m, sorties=VERROU)
