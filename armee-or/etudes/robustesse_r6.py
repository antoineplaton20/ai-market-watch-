"""Robustesse du momentum 12 mois avant adoption (R6). Même moteur que l'équipe (marches.simuler_marche : ouverture
suivante, stop de catastrophe 5 ATR, taille à 10 % de volatilité), contre la règle des 200 jours et le naïf.
Usage : python etudes/robustesse_r6.py DOSSIER_YAHOO RACINE_ARMEE DOSSIER_ETUDES"""
import copy
import sys

import numpy as np

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[3])
from armee_or import marches as M    # noqa: E402
from charger import FAMILLES, charger  # noqa: E402

REGLES = ("toujours_acheter", "sma200", "momentum_12m")


def banc(marches):
    r = M.banc(marches, strategies=REGLES)
    return {s: (r[s]["moitie1"]["sharpe"], r[s]["moitie2"]["sharpe"], r[s]["tout"]["sharpe"],
                r[s]["tout"]["pire_baisse"], r[s]["trades"]) for s in REGLES}


def ligne(nom, r):
    n, s, m = r["toujours_acheter"], r["sma200"], r["momentum_12m"]
    bat = m[0] > n[0] and m[1] > n[1]
    print(f"{nom:34}| naïf {n[0]:+.2f}/{n[1]:+.2f} | 200 j {s[0]:+.2f}/{s[1]:+.2f} | momentum {m[0]:+.2f}/{m[1]:+.2f} "
          f"(total {m[2]:+.2f}, pire {m[3]*100:.0f} %) {'✅ bat le naïf' if bat else '✖'}")
    return bat


base = charger(sys.argv[1], M)
print("1) Moteur de l'équipe (stop 5 ATR compris), coûts standard")
r0 = banc(base)
ligne("34 marchés", r0)
t = r0["momentum_12m"][4]
print(f"   trades : {t['n']}, {t['gagnants']*100:.1f} % gagnants, gain moyen {t['gain_moyen']*100:+.2f} %, perte moyenne "
      f"{t['perte_moyenne']*100:+.2f} %, pire {t['pire']*100:+.1f} %")
s = r0["momentum_12m"][2]
print(f"   t-stat du Sharpe sur 26 ans ≈ {s*np.sqrt(26):.2f} (seuil Bonferroni pour 11 essais R6 + 10 essais antérieurs "
      f"≈ 3,0 en bilatéral à 5 %)")

print("2) Coûts")
for nom, fe, fs in (("écarts × 2", 2, 1), ("écarts × 3", 3, 1), ("financement −5 %/an", 1, 5 / 3), ("financement 0", 1, 0)):
    m = copy.deepcopy(base)
    for d in m.values():
        d["cout"] = {"ecart": d["cout"]["ecart"] * fe, "swap_long": d["cout"]["swap_long"] * fs}
    ligne(nom, banc(m))

print("3) Famille par famille (le naïf de la même famille)")
for fam, noms in FAMILLES.items():
    ligne(fam, banc({s: d for s, d in base.items() if s in noms}))

print("4) 200 sous-paniers tirés au hasard (17 marchés sur 34)")
rng = np.random.default_rng(2026)
cles, bat_naif, bat_200 = sorted(base), 0, 0
for _ in range(200):
    sous = {s: base[s] for s in rng.choice(cles, 17, replace=False)}
    r = banc(sous)
    n, s2, m = r["toujours_acheter"], r["sma200"], r["momentum_12m"]
    bat_naif += m[0] > n[0] and m[1] > n[1]
    bat_200 += m[2] > s2[2]
print(f"   momentum bat le naïf sur chaque moitié : {bat_naif}/200 ; meilleur Sharpe total que la règle 200 j : {bat_200}/200")

print("5) Périodes de 5 ans (Sharpe du portefeuille)")
jours = np.array(sorted({int(t) // 86_400_000 for d in base.values() for t in d["ts"]}))
pos = {j: k for k, j in enumerate(jours)}
series = {}
for regle in REGLES:
    somme, nb = np.zeros(len(jours)), np.zeros(len(jours))
    for d in base.values():
        net, _ = M.simuler_marche(d["o"], d["h"], d["l"], d["c"], regle, d["cout"])
        idx = np.array([pos[int(t) // 86_400_000] for t in d["ts"]])
        somme[idx] += net
        nb[idx] += 1
    series[regle] = np.where(nb > 0, somme / np.maximum(nb, 1), 0.0)
import datetime as dt  # noqa: E402
annees = np.array([dt.date.fromtimestamp(int(j) * 86400).year for j in jours])
for debut in range(2001, 2026, 5):
    k = (annees >= debut) & (annees < debut + 5)
    txt = " | ".join(f"{r} {series[r][k].mean() / series[r][k].std() * np.sqrt(252):+.2f}" for r in REGLES)
    print(f"   {debut}-{min(debut + 4, 2026)} : {txt}")
